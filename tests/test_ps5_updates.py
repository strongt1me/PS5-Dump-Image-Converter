# -*- coding: utf-8 -*-
"""Offizielle PS5-Updates (``utils/ps5_updates``): lesen, pruefen, laden.

Die Netzpruefungen laufen gegen einen kleinen lokalen HTTP-Server, der
Bereichsanfragen beantwortet; ``ERLAUBTE_HOSTS`` zeigt dafuer auf 127.0.0.1.
Echte Sony-Server werden nicht angefasst. Die Aufbauten von ``version.xml`` und
Manifest sind am 15.10.2026 an Sonys Auslieferungsnetz nachgemessen (PPSA01650,
YouTube: ein Paket, zwei Teile).
"""
from __future__ import annotations

import errno
import hashlib
import http.server
import json
import os
import socketserver
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps5_updates as pu  # noqa: E402

VERXML = """<?xml version="1.0" encoding="UTF-8"?><title_patch ac_set_rev="0" nptitleid="PPSA01650_00" schema_ver="1.0">
    <app_tag content_id="UP4381-PPSA01650_00-YOUTUBESIEA00000" name="x" revision="33">
        <package bootable_content_ver="01.009.371" content_ver="01.009.371" delta_url="http://gst.prod.dl.playstation.net/gst/a/DP.pkg" digest="db22f628ca80e9191ae3a3a9c4f854c1612991caef40312a6186a412ca49f072" mandatory="true" manifest_url="https://sgst.prod.dl.playstation.net/sgst/prod/00/PPSA01650_00/app/info/33/x/UP4381.json" metadata_ver="33" pfs_revision="32" system_ver="325058567"/>
        <package content_ver="01.009.100" manifest_url="https://sgst.prod.dl.playstation.net/m100.json" system_ver="285212672"/>
        <package content_ver="01.010.002" manifest_url="https://sgst.prod.dl.playstation.net/m1002.json" system_ver="369098752"/>
    </app_tag>
</title_patch>"""


class _Server:
    """Ein Server, der Teile ausliefert - mit Bereichsanfragen, wenn gewuenscht."""

    def __init__(self, teile: dict[str, bytes], bereiche: bool = True):
        self.teile = teile
        self.bereiche = bereiche
        self.anfragen: list[tuple[str, str]] = []
        self.kaputt: set[str] = set()
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):  # noqa: N802
                daten = server.teile.get(self.path)
                if daten is None:
                    self.send_error(404)
                    return
                kopf = self.headers.get("Range", "")
                server.anfragen.append((self.path, kopf))
                if self.path in server.kaputt:
                    daten = bytes(b ^ 0xFF for b in daten)
                ab = 0
                if kopf.startswith("bytes=") and server.bereiche:
                    ab = int(kopf[6:].split("-")[0])
                    self.send_response(206)
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (ab, len(daten) - 1, len(daten)))
                else:
                    self.send_response(200)
                stueck = daten[ab:]
                self.send_header("Content-Length", str(len(stueck)))
                self.end_headers()
                try:
                    self.wfile.write(stueck)
                except OSError:
                    pass

        class Ruhig(socketserver.ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self.httpd = Ruhig(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def url(self, pfad: str) -> str:
        return "http://127.0.0.1:%d%s" % (self.port, pfad)

    def ende(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _manifest(server: _Server, teile: list[bytes]) -> pu.Manifest:
    liste = []
    versatz = 0
    for n, daten in enumerate(teile):
        liste.append(pu.Teil(server.url("/t%d.bin" % n), versatz, len(daten),
                             hashlib.sha256(daten).hexdigest()))
        versatz += len(daten)
    return pu.Manifest(versatz, liste)


class LesenTests(unittest.TestCase):

    def test_firmware_aus_system_ver(self):
        self.assertEqual("13.60", pu.firmware_text(325058567))
        self.assertEqual("11.60", pu.firmware_text(0x11600000))
        self.assertEqual("12.00", pu.firmware_text(0x12000000))

    def test_fassungen_absteigend_nach_zahlen(self):
        f = pu.fassungen_lesen(VERXML)
        self.assertEqual(["01.010.002", "01.009.371", "01.009.100"], [x.inhalt for x in f])
        self.assertEqual("13.60", f[1].firmware)
        self.assertTrue(f[1].pflicht)
        self.assertTrue(f[1].manifest_url.startswith("https://sgst.prod.dl"))

    def test_fassung_wird_als_zahl_verglichen_nicht_als_text(self):
        xml = ('<title_patch><package content_ver="01.009.371" system_ver="1"/>'
               '<package content_ver="01.1000.001" system_ver="1"/></title_patch>')
        self.assertEqual("01.1000.001", pu.fassungen_lesen(xml)[0].inhalt)

    def test_neueste_mit_und_ohne_firmware(self):
        f = pu.fassungen_lesen(VERXML)
        self.assertEqual("01.010.002", pu.neueste(f).inhalt)
        # Firmware 13.60 (0x13600007): die 01.010.002 verlangt mehr.
        self.assertEqual("01.009.371", pu.neueste(f, 0x13600007).inhalt)
        self.assertIsNone(pu.neueste(f, 1))

    def test_ps4_schreibweise_version(self):
        f = pu.fassungen_lesen('<title_patch><package version="01.50" system_ver="0x5050000"/></title_patch>')
        self.assertEqual("01.50", f[0].inhalt)

    def test_doctype_und_entity_werden_abgelehnt(self):
        for xml in ('<!DOCTYPE x [<!ENTITY a "b">]><title_patch/>',
                    '<title_patch><!ENTITY a "b"></title_patch>'):
            with self.subTest(xml=xml[:20]):
                with self.assertRaises(pu.UpdateFehler):
                    pu.fassungen_lesen(xml)

    def test_kaputtes_xml(self):
        with self.assertRaises(pu.UpdateFehler):
            pu.fassungen_lesen("<title_patch><package")

    def test_leeres_xml_ohne_pakete(self):
        self.assertEqual([], pu.fassungen_lesen("<title_patch/>"))


class AdressenTests(unittest.TestCase):

    def test_erlaubt(self):
        for url in ("https://sgst.prod.dl.playstation.net/a/b-version.xml",
                    "http://gst.prod.dl.playstation.net/a.pkg",
                    "https://gs2.ww.prod.dl.playstation.net/x",
                    "http://edge1.gst.prod.dl.playstation.net/x"):
            with self.subTest(url=url):
                self.assertTrue(pu.url_erlaubt(url))

    def test_abgelehnt(self):
        for url in ("https://evil.example/a", "ftp://gst.prod.dl.playstation.net/a",
                    "https://gst.prod.dl.playstation.net.evil.example/a",
                    "https://notgst.prod.dl.playstation.net/a", "", "javascript:alert(1)",
                    "https://user@evil.example/", "file:///C:/x"):
            with self.subTest(url=url):
                self.assertFalse(pu.url_erlaubt(url))

    def test_verxml_adresse(self):
        self.assertTrue(pu.verxml_url_gueltig("https://sgst.prod.dl.playstation.net/x/y-version.xml"))
        self.assertFalse(pu.verxml_url_gueltig("https://sgst.prod.dl.playstation.net/x/y.json"))
        self.assertFalse(pu.verxml_url_gueltig("https://evil.example/y-version.xml"))

    def test_kontext_kennt_genau_die_sony_wurzel(self):
        kontext = pu.ssl_kontext()
        self.assertEqual(1, kontext.cert_store_stats()["x509_ca"])
        self.assertTrue(kontext.check_hostname)
        import ssl
        self.assertEqual(ssl.CERT_REQUIRED, kontext.verify_mode)


def _teile_manifest(url_basis: str = "https://sgst.prod.dl.playstation.net/p", **aend) -> dict:
    daten = {
        "originalFileSize": 300,
        "packageDigest": "7" * 64,
        "pieces": [
            {"url": url_basis + "/a.pkg", "fileOffset": 0, "fileSize": 100, "hashValue": "a" * 64},
            {"url": url_basis + "/b.pkg", "fileOffset": 100, "fileSize": 200, "hashValue": "b" * 64},
        ],
    }
    daten.update(aend)
    return daten


class ManifestTests(unittest.TestCase):

    def test_gueltiges_manifest(self):
        m = pu.manifest_lesen(json.dumps(_teile_manifest()))
        self.assertEqual(300, m.gesamt)
        self.assertEqual([0, 100], [t.versatz for t in m.teile])
        self.assertEqual("7" * 64, m.paket_digest)

    def test_das_gemessene_manifest_von_sony(self):
        roh = ('{"originalFileSize":107675648,"packageDigest":"7AF627661FB2AEE4E30001E38F2FEF79EDB0A010E8E2F0778B785E63D7EE830B",'
               '"numberOfSplitFiles":2,"pieces":[{"url":"http://gst.prod.dl.playstation.net/gst/prod/00/PPSA01650_00/a.pkg",'
               '"fileOffset":0,"fileSize":81985536,"hashValue":"3bb7fc51b8a1cf21cfa5ca1513e1447225ad04330651b0d3051c67f20183c6b2"},'
               '{"url":"https://sgst.prod.dl.playstation.net/sgst/prod/00/PPSA01650_00/b_sc.pkg","fileOffset":81985536,'
               '"fileSize":25690112,"hashValue":"818aa9e510d367ea31a01654a0c88b6b5b807e4c03b2dc5631a1d5b28236dceb"}],'
               '"playgoChunkCrcHashValue":"7b1b0ea750853e2eb380716d665574c8f3e5341e16c1ef53e8bb9427e96f8062"}')
        m = pu.manifest_lesen(roh)
        self.assertEqual(107675648, m.gesamt)
        self.assertEqual(2, len(m.teile))
        self.assertEqual(m.gesamt, sum(t.groesse for t in m.teile))

    def test_abweichungen_werden_abgelehnt(self):
        faelle = {
            "Luecke": _teile_manifest(pieces=[
                {"url": "https://sgst.prod.dl.playstation.net/a", "fileOffset": 0, "fileSize": 100, "hashValue": "a" * 64},
                {"url": "https://sgst.prod.dl.playstation.net/b", "fileOffset": 150, "fileSize": 150, "hashValue": "b" * 64}]),
            "Summe": _teile_manifest(originalFileSize=299),
            "Hash zu kurz": _teile_manifest(pieces=[
                {"url": "https://sgst.prod.dl.playstation.net/a", "fileOffset": 0, "fileSize": 300, "hashValue": "abc"}]),
            "fremder Host": _teile_manifest(url_basis="https://evil.example"),
            "ohne Teile": _teile_manifest(pieces=[]),
            "keine Liste": _teile_manifest(pieces="x"),
            "Teil null": _teile_manifest(originalFileSize=200, pieces=[
                {"url": "https://sgst.prod.dl.playstation.net/a", "fileOffset": 0, "fileSize": 0, "hashValue": "a" * 64},
                {"url": "https://sgst.prod.dl.playstation.net/b", "fileOffset": 0, "fileSize": 200, "hashValue": "b" * 64}]),
            "zu gross": _teile_manifest(originalFileSize=pu.MAX_GESAMT_BYTES + 1),
            "Text statt Zahl": _teile_manifest(originalFileSize="viel"),
        }
        for name, daten in faelle.items():
            with self.subTest(fall=name):
                with self.assertRaises(pu.UpdateFehler):
                    pu.manifest_lesen(json.dumps(daten))

    def test_kein_json(self):
        for roh in (b"<html>", "", b"[]", b"null"):
            with self.subTest(roh=roh):
                with self.assertRaises(pu.UpdateFehler):
                    pu.manifest_lesen(roh)

    def test_zu_viele_teile(self):
        stuecke = [{"url": "https://sgst.prod.dl.playstation.net/a", "fileOffset": i, "fileSize": 1,
                    "hashValue": "a" * 64} for i in range(pu.MAX_TEILE + 1)]
        with self.assertRaises(pu.UpdateFehler):
            pu.manifest_lesen(json.dumps(_teile_manifest(originalFileSize=len(stuecke), pieces=stuecke)))


class LadenTests(unittest.TestCase):

    def setUp(self):
        self.teile = [os.urandom(3_000_000), os.urandom(120_000), os.urandom(50_000)]
        self.server = _Server({"/t%d.bin" % n: d for n, d in enumerate(self.teile)})
        self.addCleanup(self.server.ende)
        hosts = mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",))
        hosts.start()
        self.addCleanup(hosts.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="ps5upd_test_")
        self.addCleanup(self.tmp.cleanup)
        self.ziel = os.path.join(self.tmp.name, "Update", "Spiel.pkg")
        self.manifest = _manifest(self.server, self.teile)

    def _gesamt(self) -> bytes:
        return b"".join(self.teile)

    def test_laden_setzt_die_teile_zusammen(self):
        meldungen: list[tuple[int, int]] = []
        pu.paket_laden(self.manifest, self.ziel, fortschritt=lambda a, b: meldungen.append((a, b)))
        with open(self.ziel, "rb") as datei:
            self.assertEqual(self._gesamt(), datei.read())
        self.assertFalse(os.path.exists(pu.teildatei(self.ziel)))
        self.assertFalse(os.path.exists(pu.merkdatei(self.ziel)))
        self.assertEqual((len(self._gesamt()), len(self._gesamt())), max(meldungen))
        self.assertEqual(len(self._gesamt()), self.manifest.gesamt)

    def test_ein_faden_geht_auch(self):
        pu.paket_laden(self.manifest, self.ziel, faeden=1)
        self.assertEqual(self._gesamt(), Path(self.ziel).read_bytes())

    def test_abbruch_laesst_den_stand_und_der_zweite_lauf_setzt_fort(self):
        stand = {"geladen": 0}

        def abbruch() -> bool:
            return stand["geladen"] >= 1_000_000       # mitten im ersten, grossen Teil

        with self.assertRaises(pu.UpdateFehler) as ctx:
            pu.paket_laden(self.manifest, self.ziel, abbruch=abbruch, faeden=1,
                           fortschritt=lambda a, _b: stand.update(geladen=a))
        self.assertEqual("ps5upd.abgebrochen", str(ctx.exception))
        self.assertTrue(os.path.exists(pu.teildatei(self.ziel)))
        self.assertFalse(os.path.exists(self.ziel), "Eine halbe Datei darf nicht fertig heissen")
        self.server.anfragen.clear()
        pu.paket_laden(self.manifest, self.ziel, faeden=1)
        self.assertEqual(self._gesamt(), Path(self.ziel).read_bytes())
        bereiche = [k for _p, k in self.server.anfragen if k]
        self.assertTrue(bereiche, "Die Fortsetzung muss eine Bereichsanfrage stellen")

    def test_server_ohne_bereiche_laedt_von_vorn(self):
        self.server.bereiche = False
        stand = {"geladen": 0}

        def abbruch() -> bool:
            return stand["geladen"] >= 1_000_000

        with self.assertRaises(pu.UpdateFehler):
            pu.paket_laden(self.manifest, self.ziel, abbruch=abbruch, faeden=1,
                           fortschritt=lambda a, _b: stand.update(geladen=a))
        pu.paket_laden(self.manifest, self.ziel, faeden=1)
        self.assertEqual(self._gesamt(), Path(self.ziel).read_bytes())

    def test_falsche_pruefsumme_wird_erkannt_und_nicht_fertig_gemeldet(self):
        self.server.kaputt.add("/t1.bin")
        with self.assertRaises(pu.UpdateFehler) as ctx:
            pu.paket_laden(self.manifest, self.ziel)
        self.assertTrue(str(ctx.exception).startswith("ps5upd.pruefsumme|2"), str(ctx.exception))
        self.assertFalse(os.path.exists(self.ziel))

    def test_einmal_falsch_dann_richtig_wird_neu_geladen(self):
        """Ein einzelner Uebertragungsfehler kostet nur den Teil, nicht den Lauf."""
        zaehler = {"n": 0}
        echt = self.server.teile["/t2.bin"]

        class Einmal(dict):
            def get(inner, schluessel, vorgabe=None):  # noqa: N805
                if schluessel == "/t2.bin":
                    zaehler["n"] += 1
                    return bytes(b ^ 0xFF for b in echt) if zaehler["n"] == 1 else echt
                return dict.get(inner, schluessel, vorgabe)

        self.server.teile = Einmal(self.server.teile)
        pu.paket_laden(self.manifest, self.ziel, faeden=1)
        self.assertEqual(self._gesamt(), Path(self.ziel).read_bytes())
        self.assertGreaterEqual(zaehler["n"], 2)

    def test_zu_wenig_platz(self):
        with mock.patch.object(pu.shutil, "disk_usage",
                               return_value=mock.Mock(free=1000)):
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.paket_laden(self.manifest, self.ziel)
        self.assertEqual("ps5upd.platz", str(ctx.exception))
        self.assertFalse(os.path.exists(pu.teildatei(self.ziel)), "Nichts anlegen, wenn kein Platz ist")

    def test_fremder_merkstand_wird_verworfen(self):
        os.makedirs(os.path.dirname(self.ziel))
        with open(pu.teildatei(self.ziel), "wb") as datei:
            datei.write(b"\0" * self.manifest.gesamt)
        pu._merk_schreiben(pu.merkdatei(self.ziel), "andere-kennung",
                           [t.groesse for t in self.manifest.teile])
        pu.paket_laden(self.manifest, self.ziel)
        self.assertEqual(self._gesamt(), Path(self.ziel).read_bytes(),
                         "Ein Merkstand zu einem anderen Manifest darf nichts als geladen gelten lassen")

    def test_fremder_host_im_manifest_wird_nicht_besucht(self):
        m = pu.Manifest(10, [pu.Teil("http://evil.example/x", 0, 10, "a" * 64)])
        with self.assertRaises(pu.UpdateFehler):
            pu.paket_laden(m, self.ziel)

    def test_404_wird_zum_fehler(self):
        m = pu.Manifest(10, [pu.Teil(self.server.url("/gibtsnicht"), 0, 10, "a" * 64)])
        with mock.patch.object(pu.time, "sleep"):
            with self.assertRaises(pu.UpdateFehler):
                pu.paket_laden(m, self.ziel, versuche=1)


class HolenTests(unittest.TestCase):

    def test_host_fremd(self):
        with self.assertRaises(pu.UpdateFehler) as ctx:
            pu.holen("https://evil.example/a", 100)
        self.assertEqual("ps5upd.host_fremd", str(ctx.exception))

    def test_obergrenze_und_inhalt(self):
        server = _Server({"/klein": b"x" * 100, "/gross": b"y" * 5000})
        self.addCleanup(server.ende)
        with mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",)):
            self.assertEqual(b"x" * 100, pu.holen(server.url("/klein"), 1000))
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.holen(server.url("/gross"), 1000)
            self.assertEqual("ps5upd.zu_gross", str(ctx.exception))
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.holen(server.url("/fehlt"), 1000)
            self.assertEqual("ps5upd.http|404", str(ctx.exception))

    def test_umleitung_zu_fremdem_host_wird_verweigert(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_a):
                pass

            def do_GET(self):  # noqa: N802
                self.send_response(302)
                self.send_header("Location", "http://evil.example/steal")
                self.end_headers()

        httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        with mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",)):
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.holen("http://127.0.0.1:%d/x" % httpd.server_address[1], 1000)
        self.assertEqual("ps5upd.umleitung_fremd", str(ctx.exception))

    def test_abbruch_waehrend_des_lesens(self):
        server = _Server({"/x": b"z" * 500_000})
        self.addCleanup(server.ende)
        with mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",)):
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.holen(server.url("/x"), 10_000_000, abbruch=lambda: True)
        self.assertEqual("ps5upd.abgebrochen", str(ctx.exception))


def _eigener_server(antwort) -> tuple:
    """Ein Server, dessen Antwort ``antwort(handler)`` selbst schreibt. Gibt ``(httpd, port)`` zurueck."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def do_GET(self):  # noqa: N802
            antwort(self)

    class Ruhig(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    httpd = Ruhig(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, httpd.server_address[1]


class RobustheitTests(unittest.TestCase):
    """Antworten, die ``urllib`` nicht als ``URLError``/``OSError`` melden (``http.client.HTTPException``),
    ein Fehler in einem Faden und ein volles Laufwerk."""

    def setUp(self):
        hosts = mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",))
        hosts.start()
        self.addCleanup(hosts.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="ps5upd_robust_")
        self.addCleanup(self.tmp.cleanup)
        self.ziel = os.path.join(self.tmp.name, "Update", "Spiel.pkg")

    def _starten(self, antwort) -> int:
        httpd, port = _eigener_server(antwort)
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return port

    def test_abgerissene_chunked_antwort_wird_wiederholt(self):
        daten = os.urandom(200_000)
        zaehler = [0]

        def antwort(h):
            zaehler[0] += 1
            h.send_response(200)
            h.send_header("Transfer-Encoding", "chunked")
            h.end_headers()
            if zaehler[0] == 1:
                h.wfile.write(b"%x\r\n" % 1000 + daten[:1000] + b"\r\n")   # ein Stueck, dann reisst es ab
                return
            h.wfile.write(b"%x\r\n" % len(daten) + daten + b"\r\n0\r\n\r\n")

        port = self._starten(antwort)
        manifest = pu.Manifest(len(daten), [pu.Teil("http://127.0.0.1:%d/t" % port, 0, len(daten),
                                                    hashlib.sha256(daten).hexdigest())])
        with mock.patch.object(pu.time, "sleep"):
            pu.paket_laden(manifest, self.ziel, faeden=1, versuche=2)
        self.assertEqual(daten, Path(self.ziel).read_bytes())
        self.assertEqual(2, zaehler[0])

    def test_kaputte_statuszeile_wird_zum_updatefehler(self):
        port = self._starten(lambda h: h.wfile.write(b"KEIN HTTP\r\n\r\n"))
        with self.assertRaises(pu.UpdateFehler) as ctx:
            pu.holen("http://127.0.0.1:%d/x" % port, 1000)
        self.assertTrue(str(ctx.exception).startswith("ps5upd.netz|"), str(ctx.exception))

    def test_fehler_in_einem_teil_haelt_die_anderen_faeden_an(self):
        gross = 24 * 1024 * 1024

        def antwort(h):
            if h.path == "/schnell":
                h.send_error(404)
                return
            h.send_response(200)
            h.send_header("Content-Length", str(gross))
            h.end_headers()
            block = b"x" * (1024 * 1024)
            try:
                for _ in range(gross // len(block)):
                    h.wfile.write(block)
                    h.wfile.flush()
                    time.sleep(0.25)
            except OSError:
                pass

        port = self._starten(antwort)
        manifest = pu.Manifest(10 + gross, [
            pu.Teil("http://127.0.0.1:%d/schnell" % port, 0, 10, "a" * 64),
            pu.Teil("http://127.0.0.1:%d/langsam" % port, 10, gross, "b" * 64)])
        start = time.monotonic()
        with self.assertRaises(pu.UpdateFehler) as ctx:
            pu.paket_laden(manifest, self.ziel, faeden=2, versuche=0)
        dauer = time.monotonic() - start
        self.assertTrue(str(ctx.exception).startswith(("ps5upd.netz|", "ps5upd.http|")), str(ctx.exception))
        # Ohne den Halt liefe der zweite Faden die ganzen 24 Blocke zu Ende (rund 6 s).
        self.assertLess(dauer, 3.0, "der zweite Faden lief weiter: %.1f s" % dauer)

    def test_volles_laufwerk_ist_kein_netzfehler_und_wird_nicht_wiederholt(self):
        daten = os.urandom(100_000)
        port = self._starten(lambda h: (h.send_response(200),
                                        h.send_header("Content-Length", str(len(daten))),
                                        h.end_headers(), h.wfile.write(daten)))
        manifest = pu.Manifest(len(daten), [pu.Teil("http://127.0.0.1:%d/t" % port, 0, len(daten),
                                                    hashlib.sha256(daten).hexdigest())])
        echt = open

        class _Voll:
            def __init__(self, datei):
                self.datei = datei

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                self.datei.close()
                return False

            def seek(self, *a):
                return self.datei.seek(*a)

            def write(self, _block):
                raise OSError(errno.ENOSPC, "No space left on device")

            def flush(self):
                self.datei.flush()

        def falsches_open(pfad, modus="r", *a, **k):
            if modus == "r+b":
                return _Voll(echt(pfad, modus, *a, **k))
            return echt(pfad, modus, *a, **k)

        with mock.patch.object(pu, "open", falsches_open, create=True), \
                mock.patch.object(pu.time, "sleep") as schlaf:
            with self.assertRaises(pu.UpdateFehler) as ctx:
                pu.paket_laden(manifest, self.ziel, faeden=1, versuche=3)
        self.assertTrue(str(ctx.exception).startswith("ps5upd.platz"), str(ctx.exception))
        schlaf.assert_not_called()


if __name__ == "__main__":
    unittest.main()
