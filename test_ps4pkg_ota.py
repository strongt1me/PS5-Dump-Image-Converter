# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.ps4pkg_ota`` - Pakete ueber das Netzwerk auf die Konsole.

Es gibt keine Konsole in der Testreihe. Die beiden Gegenstellen werden
nachgebaut - nach denselben Quellen wie die Clients:

* **Remote Package Installer** (PS4, Port 12800): ``POST /api/install`` mit
  ``{"type": "direct", "packages": [...]}``, danach ``get_task_progress``. Die
  Nachbildung holt die Pakete wirklich vom Dateiserver, so wie es die Konsole
  taete - der Test prueft also auch den Server, nicht nur den Client.
* **OnionHEN-Paketmanager** (DPI v2): ``GET /ping``, ``GET /staged-size``,
  ``POST /install?name=&offset=&total=[&head256=]`` und ``&finalize=1``. Die
  Form stammt aus der Weboberflaeche, die in ``dpiv2-13.60-1.00.elf`` steckt.

**Nichts davon ist an einer echten Konsole geprueft.**
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps4pkg_ota as ota   # noqa: E402

LOKAL = "127.0.0.1"


def _datei(wo: Path, name: str = "spiel.pkg", groesse: int = 300_000) -> Path:
    pfad = wo / name
    inhalt = bytearray()
    zaehler = 0
    while len(inhalt) < groesse:
        inhalt += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    pfad.write_bytes(bytes(inhalt[:groesse]))
    return pfad


def _sha(daten: bytes) -> str:
    return hashlib.sha256(daten).hexdigest()


def _holen(port: int, pfad: str, methode: str = "GET", kopf: "dict | None" = None):
    verbindung = http.client.HTTPConnection(LOKAL, port, timeout=10)
    try:
        verbindung.request(methode, pfad, headers=kopf or {})
        antwort = verbindung.getresponse()
        return antwort.status, dict(antwort.getheaders()), antwort.read()
    finally:
        verbindung.close()


class BereichTests(unittest.TestCase):

    def test_ohne_kopf_ganze_datei(self) -> None:
        self.assertIsNone(ota.bereich_auswerten("", 100))

    def test_von_bis(self) -> None:
        self.assertEqual((10, 19), ota.bereich_auswerten("bytes=10-19", 100))
        self.assertEqual((0, 99), ota.bereich_auswerten("bytes=0-999", 100), "Das Ende wird gekappt.")

    def test_offenes_ende(self) -> None:
        self.assertEqual((50, 99), ota.bereich_auswerten("bytes=50-", 100))

    def test_die_letzten_n_bytes(self) -> None:
        self.assertEqual((90, 99), ota.bereich_auswerten("bytes=-10", 100))
        self.assertEqual((0, 99), ota.bereich_auswerten("bytes=-500", 100))

    def test_ungueltige_bereiche(self) -> None:
        for kopf in ("bytes=100-", "bytes=60-50", "bytes=-0", "bytes=-", "bytes=abc", "items=0-5",
                     "bytes=0-5,10-20"):
            with self.subTest(kopf=kopf):
                self.assertEqual("ungueltig", ota.bereich_auswerten(kopf, 100))
        self.assertEqual("ungueltig", ota.bereich_auswerten("bytes=-5", 0), "Eine leere Datei hat keine Bytes.")


class AdressenTests(unittest.TestCase):

    def test_gueltigkeit(self) -> None:
        for gut in ("192.168.0.10", "10.0.0.1", "0.0.0.0", "255.255.255.255"):
            self.assertTrue(ota.adresse_gueltig(gut), gut)
        for schlecht in ("", "1.2.3", "1.2.3.4.5", "256.1.1.1", "a.b.c.d", "1.2.3.-4", " ", "1..3.4"):
            self.assertFalse(ota.adresse_gueltig(schlecht), repr(schlecht))

    def test_eigene_adresse_fuer_loopback(self) -> None:
        adresse = ota.eigene_adresse_fuer(LOKAL)
        self.assertTrue(adresse == "" or ota.adresse_gueltig(adresse))

    def test_lokale_adressen_ohne_loopback(self) -> None:
        for adresse in ota.lokale_adressen():
            self.assertFalse(adresse.startswith("127."))
            self.assertTrue(ota.adresse_gueltig(adresse))


class PaketServerTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        self.datei = _datei(self.wo, "Mein Spiel [CUSA00001].pkg", 700_000)
        self.inhalt = self.datei.read_bytes()
        self.server = ota.PaketServer(adresse=LOKAL)
        self.name = self.server.datei_anbieten(str(self.datei))
        self.port = self.server.starten()
        self.pfad = "/%s/%s" % (self.server.token, urllib.parse.quote(self.name))

    def tearDown(self) -> None:
        self.server.anhalten()
        self._tmp.cleanup()

    def test_die_datei_kommt_unveraendert_an(self) -> None:
        status, kopf, daten = _holen(self.port, self.pfad)
        self.assertEqual(200, status)
        self.assertEqual(self.inhalt, daten)
        self.assertEqual(str(len(self.inhalt)), kopf["Content-Length"])
        self.assertEqual("bytes", kopf["Accept-Ranges"])
        self.assertEqual("application/octet-stream", kopf["Content-Type"])

    def test_head_liefert_nur_die_koepfe(self) -> None:
        # ``BaseHTTPRequestHandler`` ruft ``do_<METHODE>`` ueber den Namen - ohne ``do_HEAD`` antwortete der
        # Server auf HEAD mit 501 (HTTP/1.1 verlangt, dass er es wie GET ohne Inhalt bedient).
        self.assertTrue(callable(ota._Handler.do_HEAD))
        status, kopf, daten = _holen(self.port, self.pfad, "HEAD")
        self.assertEqual(200, status)
        self.assertEqual(b"", daten)
        self.assertEqual(str(len(self.inhalt)), kopf["Content-Length"])

    def test_ein_bereich_kommt_als_206(self) -> None:
        status, kopf, daten = _holen(self.port, self.pfad, kopf={"Range": "bytes=1000-1999"})
        self.assertEqual(206, status)
        self.assertEqual(self.inhalt[1000:2000], daten)
        self.assertEqual("bytes 1000-1999/%d" % len(self.inhalt), kopf["Content-Range"])
        self.assertEqual("1000", kopf["Content-Length"])

    def test_offenes_ende_und_ende_der_datei(self) -> None:
        _, _, ab = _holen(self.port, self.pfad, kopf={"Range": "bytes=%d-" % (len(self.inhalt) - 50)})
        self.assertEqual(self.inhalt[-50:], ab)
        _, _, letzte = _holen(self.port, self.pfad, kopf={"Range": "bytes=-77"})
        self.assertEqual(self.inhalt[-77:], letzte)

    def test_ein_bereich_hinter_dem_ende_ist_416(self) -> None:
        status, kopf, _ = _holen(self.port, self.pfad, kopf={"Range": "bytes=%d-" % (len(self.inhalt) + 10)})
        self.assertEqual(416, status)
        self.assertEqual("bytes */%d" % len(self.inhalt), kopf["Content-Range"])

    def test_falscher_token_und_unbekannter_name_sind_404(self) -> None:
        self.assertEqual(404, _holen(self.port, "/falsch/" + urllib.parse.quote(self.name))[0])
        self.assertEqual(404, _holen(self.port, "/%s/gibt_es_nicht.pkg" % self.server.token)[0])
        self.assertEqual(404, _holen(self.port, "/")[0])
        self.assertEqual(404, _holen(self.port, "/%s" % self.server.token)[0])

    def test_kein_ausbruch_aus_der_freigabe(self) -> None:
        (self.wo / "geheim.txt").write_text("geheim")
        for versuch in ("/%s/../geheim.txt" % self.server.token, "/%s/%%2e%%2e/geheim.txt" % self.server.token,
                        "/%s/..%%2fgeheim.txt" % self.server.token, "/%s/geheim.txt" % self.server.token):
            with self.subTest(versuch=versuch):
                status, _, daten = _holen(self.port, versuch)
                self.assertEqual(404, status)
                self.assertNotIn(b"geheim", daten)

    def test_nur_die_konsole_darf_laden(self) -> None:
        self.server.nur_ip = "10.99.99.99"
        self.assertEqual(403, _holen(self.port, self.pfad)[0])
        self.server.nur_ip = LOKAL
        self.assertEqual(200, _holen(self.port, self.pfad)[0])

    def test_die_zaehler(self) -> None:
        _holen(self.port, self.pfad)
        _holen(self.port, self.pfad, kopf={"Range": "bytes=0-99"})
        self.assertEqual(len(self.inhalt) + 100, self.server.gesendet(self.name))
        self.assertEqual(self.server.gesendet(self.name), self.server.gesendet())
        methoden = [a[0] for a in self.server.anfragen]
        self.assertEqual(["GET", "GET"], methoden)
        self.assertEqual((0, 99), self.server.anfragen[-1][2:])

    def test_mehrere_gleichzeitige_anfragen(self) -> None:
        ergebnisse: dict[int, bytes] = {}

        def _lade(n: int) -> None:
            von, bis = n * 100_000, n * 100_000 + 99_999
            ergebnisse[n] = _holen(self.port, self.pfad, kopf={"Range": "bytes=%d-%d" % (von, bis)})[2]

        faeden = [threading.Thread(target=_lade, args=(n,)) for n in range(7)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join(20)
        zusammen = b"".join(ergebnisse[n] for n in range(7))
        self.assertEqual(self.inhalt, zusammen)

    def test_die_url_traegt_token_und_kodierten_namen(self) -> None:
        url = self.server.url(self.name, "192.168.0.5")
        self.assertTrue(url.startswith("http://192.168.0.5:%d/%s/" % (self.port, self.server.token)))
        self.assertIn("Mein%20Spiel%20%5BCUSA00001%5D.pkg", url)

    def test_gleiche_dateinamen_bekommen_einen_zaehler(self) -> None:
        zweite = self.wo / "unter" / self.datei.name
        zweite.parent.mkdir()
        zweite.write_bytes(b"anders")
        name2 = self.server.datei_anbieten(str(zweite))
        self.assertNotEqual(self.name, name2)
        self.assertEqual(self.name, self.server.datei_anbieten(str(self.datei)), "Dieselbe Datei behaelt ihren Namen.")
        status, _, daten = _holen(self.port, "/%s/%s" % (self.server.token, urllib.parse.quote(name2)))
        self.assertEqual((200, b"anders"), (status, daten))

    def test_anhalten_gibt_den_port_frei(self) -> None:
        self.server.anhalten()
        self.assertFalse(self.server.laeuft)
        with self.assertRaises(OSError):
            http.client.HTTPConnection(LOKAL, self.port, timeout=2).request("GET", "/")

    def test_ein_belegter_port_gibt_einen_klaren_fehler(self) -> None:
        zweiter = ota.PaketServer(adresse=LOKAL, port=self.port)
        with self.assertRaises(ota.OtaFehler) as ctx:
            zweiter.starten()
        self.assertEqual("server_start", ctx.exception.schluessel)


# ---------------------------------------------------------------------------
# Nachbildung: Remote Package Installer
# ---------------------------------------------------------------------------

class _RpiNachbildung:
    """Ein Remote Package Installer, der Pakete wirklich per HTTP holt."""

    def __init__(self, *, chunk: int = 64 * 1024, verzoegerung: float = 0.0) -> None:
        self.anfragen: list[tuple[str, dict]] = []
        self.aufgaben: dict[int, dict] = {}
        self.installiert: set[str] = set()
        self.chunk = chunk
        self.verzoegerung = verzoegerung
        self.fehlercode = 0
        self.install_antwort: "dict | None" = None
        self.http_status = 200
        self.rohantwort: "bytes | None" = None
        self.erhalten: dict[int, bytes] = {}
        nachbildung = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a) -> None:
                return

            def do_POST(self) -> None:   # noqa: N802
                laenge = int(self.headers.get("Content-Length", 0))
                koerper = json.loads(self.rfile.read(laenge) or b"{}")
                endpunkt = self.path.rsplit("/", 1)[-1]
                nachbildung.anfragen.append((endpunkt, koerper))
                if nachbildung.rohantwort is not None:
                    antwort = nachbildung.rohantwort
                    status = nachbildung.http_status
                else:
                    status = nachbildung.http_status
                    antwort = json.dumps(nachbildung._beantworten(endpunkt, koerper)).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(antwort)))
                self.end_headers()
                self.wfile.write(antwort)

        self.server = ThreadingHTTPServer((LOKAL, 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()

    def schliessen(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    # --- Verhalten ---
    def _beantworten(self, endpunkt: str, k: dict) -> dict:
        if endpunkt == "install":
            if self.install_antwort is not None:
                return self.install_antwort
            nummer = 100 + len(self.aufgaben)
            self.aufgaben[nummer] = {"laenge": 0, "geholt": 0, "fertig": False, "gestoppt": False}
            threading.Thread(target=self._holen, args=(nummer, k["packages"]), daemon=True).start()
            return {"status": "success", "task_id": nummer}
        if endpunkt == "get_task_progress":
            a = self.aufgaben[k["task_id"]]
            return {"status": "success", "bits": 0, "error": self.fehlercode,
                    "length": a["laenge"], "transferred": a["geholt"],
                    "length_total": a["laenge"], "transferred_total": a["geholt"],
                    "rest_sec": 3, "rest_sec_total": 3, "preparing_percent": 0}
        if endpunkt == "stop_task":
            self.aufgaben[k["task_id"]]["gestoppt"] = True
            return {"status": "success"}
        if endpunkt == "is_exists":
            return {"status": "success", "exists": "true" if k["title_id"] in self.installiert else "false"}
        if endpunkt.startswith("uninstall_"):
            return {"status": "success"}
        return {"status": "fail", "error": "unbekannt: " + endpunkt}

    def _holen(self, nummer: int, adressen: list[str]) -> None:
        try:
            self._holen_wirklich(nummer, adressen)
        except OSError:
            # Der Dateiserver ist weg (Test beendet, Versand abgebrochen) - wie bei
            # der Konsole kein Absturz, nur ein Abbruch der Aufgabe.
            self.aufgaben[nummer]["gestoppt"] = True

    def _holen_wirklich(self, nummer: int, adressen: list[str]) -> None:
        a = self.aufgaben[nummer]
        gesamt = bytearray()
        for adresse in adressen:
            teile = urllib.parse.urlsplit(adresse)
            verbindung = http.client.HTTPConnection(teile.hostname, teile.port, timeout=20)
            verbindung.request("HEAD", teile.path)
            kopf = verbindung.getresponse()
            kopf.read()
            a["laenge"] += int(kopf.getheader("Content-Length", "0"))
            verbindung.close()
        for adresse in adressen:
            teile = urllib.parse.urlsplit(adresse)
            versatz = 0
            while not a["gestoppt"]:
                verbindung = http.client.HTTPConnection(teile.hostname, teile.port, timeout=20)
                verbindung.request("GET", teile.path, headers={"Range": "bytes=%d-%d" % (versatz, versatz + self.chunk - 1)})
                antwort = verbindung.getresponse()
                stueck = antwort.read()
                verbindung.close()
                if antwort.status not in (200, 206) or not stueck:
                    break
                gesamt += stueck
                versatz += len(stueck)
                a["geholt"] += len(stueck)
                if self.verzoegerung:
                    time.sleep(self.verzoegerung)
                if antwort.status == 200:
                    break
        self.erhalten[nummer] = bytes(gesamt)
        a["fertig"] = True


class RpiClientTests(unittest.TestCase):

    def setUp(self) -> None:
        self.konsole = _RpiNachbildung()
        self.client = ota.RpiClient(LOKAL, self.konsole.port, zeit=5)

    def tearDown(self) -> None:
        self.konsole.schliessen()

    def test_erreichbar(self) -> None:
        self.assertTrue(self.client.erreichbar())
        self.konsole.schliessen()
        self.assertFalse(ota.RpiClient(LOKAL, self.konsole.port, zeit=1).erreichbar())
        self.konsole = _RpiNachbildung()

    def test_installieren_sendet_die_adressen_direkt(self) -> None:
        nummer = self.client.installieren(["http://pc/a.pkg", "http://pc/b.pkg"])
        self.assertEqual(100, nummer)
        endpunkt, koerper = self.konsole.anfragen[-1]
        self.assertEqual("install", endpunkt)
        self.assertEqual({"type": "direct", "packages": ["http://pc/a.pkg", "http://pc/b.pkg"]}, koerper)

    def test_fortschritt_wird_gelesen(self) -> None:
        self.konsole.aufgaben[7] = {"laenge": 1000, "geholt": 250, "fertig": False, "gestoppt": False}
        f = self.client.fortschritt(7)
        self.assertEqual((1000, 250), (f.laenge, f.uebertragen))
        self.assertAlmostEqual(25.0, f.prozent)
        self.assertEqual(3, f.rest_sekunden)
        self.assertEqual(0, ota.RpiFortschritt().prozent)

    def test_ist_installiert(self) -> None:
        self.konsole.installiert.add("CUSA00001")
        self.assertTrue(self.client.ist_installiert("CUSA00001"))
        self.assertFalse(self.client.ist_installiert("CUSA00002"))

    def test_deinstallieren_nutzt_je_art_den_richtigen_schluessel(self) -> None:
        self.client.deinstallieren("game", "CUSA00001")
        self.client.deinstallieren("patch", "CUSA00001")
        self.client.deinstallieren("ac", "UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA")
        self.client.deinstallieren("theme", "UP0000-CUSA00001_00-BBBBBBBBBBBBBBBB")
        self.assertEqual([
            ("uninstall_game", {"title_id": "CUSA00001"}),
            ("uninstall_patch", {"title_id": "CUSA00001"}),
            ("uninstall_ac", {"content_id": "UP0000-CUSA00001_00-AAAAAAAAAAAAAAAA"}),
            ("uninstall_theme", {"content_id": "UP0000-CUSA00001_00-BBBBBBBBBBBBBBBB"}),
        ], self.konsole.anfragen)
        with self.assertRaises(ValueError):
            self.client.deinstallieren("alles", "x")

    def test_eine_abgelehnte_anfrage_wirft(self) -> None:
        self.konsole.install_antwort = {"status": "fail", "error_code": 5}
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.installieren(["http://pc/a.pkg"])
        self.assertEqual("abgelehnt", ctx.exception.schluessel)

    def test_eine_antwort_ohne_aufgabennummer_wirft(self) -> None:
        self.konsole.install_antwort = {"status": "success"}
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.installieren(["http://pc/a.pkg"])
        self.assertEqual("antwort", ctx.exception.schluessel)

    def test_http_fehler_und_unsinn(self) -> None:
        self.konsole.http_status = 500
        self.konsole.rohantwort = b"{}"
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.installieren(["x"])
        self.assertEqual("http", ctx.exception.schluessel)
        self.konsole.http_status = 200
        self.konsole.rohantwort = b"<html>kein json</html>"
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.installieren(["x"])
        self.assertEqual("antwort", ctx.exception.schluessel)

    def test_keine_verbindung_ist_ein_netzfehler(self) -> None:
        tot = ota.RpiClient(LOKAL, 1, zeit=1)
        with self.assertRaises(ota.OtaFehler) as ctx:
            tot.installieren(["x"])
        self.assertEqual("netz", ctx.exception.schluessel)


class RpiSendenTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        self.datei = _datei(self.wo, "Spiel Eins.pkg", 400_000)
        self.zweite = _datei(self.wo, "Update.pkg", 150_000)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_die_konsole_holt_die_pakete_und_der_versand_endet(self) -> None:
        konsole = _RpiNachbildung(chunk=32 * 1024)
        self.addCleanup(konsole.schliessen)
        meldungen: list[tuple[float, int]] = []
        nummer = ota.rpi_senden(
            LOKAL, [str(self.datei), str(self.zweite)], port=konsole.port, eigene_ip=LOKAL,
            abfrage_sekunden=0.05,
            fortschritt=lambda f, gesendet: meldungen.append((f.prozent if f else 0.0, gesendet)))
        self.assertEqual(100, nummer)
        gesamt = self.datei.read_bytes() + self.zweite.read_bytes()
        self.assertEqual(_sha(gesamt), _sha(konsole.erhalten[100]))
        self.assertTrue(meldungen)
        self.assertEqual(100.0, meldungen[-1][0])
        self.assertEqual(len(gesamt), meldungen[-1][1])

    def test_die_adressen_zeigen_auf_den_eigenen_server(self) -> None:
        konsole = _RpiNachbildung()
        self.addCleanup(konsole.schliessen)
        ota.rpi_senden(LOKAL, [str(self.zweite)], port=konsole.port, eigene_ip=LOKAL, abfrage_sekunden=0.05)
        endpunkt, koerper = [a for a in konsole.anfragen if a[0] == "install"][0]
        adresse = koerper["packages"][0]
        self.assertTrue(adresse.startswith("http://%s:" % LOKAL))
        self.assertTrue(adresse.endswith("/Update.pkg"))

    def test_der_server_laeuft_nach_dem_versand_nicht_mehr(self) -> None:
        konsole = _RpiNachbildung()
        self.addCleanup(konsole.schliessen)
        ota.rpi_senden(LOKAL, [str(self.zweite)], port=konsole.port, eigene_ip=LOKAL, abfrage_sekunden=0.05)
        adresse = [a for a in konsole.anfragen if a[0] == "install"][0][1]["packages"][0]
        teile = urllib.parse.urlsplit(adresse)
        with self.assertRaises(OSError):
            http.client.HTTPConnection(teile.hostname, teile.port, timeout=2).request("GET", teile.path)

    def test_der_abbruch_stoppt_die_aufgabe_der_konsole(self) -> None:
        konsole = _RpiNachbildung(chunk=8 * 1024, verzoegerung=0.05)
        self.addCleanup(konsole.schliessen)
        aufrufe = [0]

        def _abbruch() -> bool:
            aufrufe[0] += 1
            return aufrufe[0] > 3

        with self.assertRaises(ota.OtaAbgebrochen):
            ota.rpi_senden(LOKAL, [str(self.datei)], port=konsole.port, eigene_ip=LOKAL,
                           abfrage_sekunden=0.05, abbruch=_abbruch)
        self.assertIn("stop_task", [a[0] for a in konsole.anfragen])

    def test_ein_fehlercode_der_konsole_bricht_ab(self) -> None:
        konsole = _RpiNachbildung(chunk=8 * 1024, verzoegerung=0.05)
        konsole.fehlercode = 0x80A3000B
        self.addCleanup(konsole.schliessen)
        with self.assertRaises(ota.OtaFehler) as ctx:
            ota.rpi_senden(LOKAL, [str(self.datei)], port=konsole.port, eigene_ip=LOKAL, abfrage_sekunden=0.05)
        self.assertEqual("konsole_fehler", ctx.exception.schluessel)
        self.assertIn("80A3000B", ctx.exception.text)

    def test_ohne_erreichbare_konsole_netzfehler_und_server_wird_aufgeraeumt(self) -> None:
        with self.assertRaises(ota.OtaFehler) as ctx:
            ota.rpi_senden(LOKAL, [str(self.zweite)], port=1, eigene_ip=LOKAL)
        self.assertEqual("netz", ctx.exception.schluessel)

    def test_ohne_eigene_adresse_klarer_fehler(self) -> None:
        with mock.patch.object(ota, "eigene_adresse_fuer", return_value=""):
            with self.assertRaises(ota.OtaFehler) as ctx:
                ota.rpi_senden("10.0.0.5", [str(self.zweite)])
        self.assertEqual("keine_adresse", ctx.exception.schluessel)

    def test_die_zeitgrenze(self) -> None:
        konsole = _RpiNachbildung(chunk=1024, verzoegerung=0.2)
        self.addCleanup(konsole.schliessen)
        with self.assertRaises(ota.OtaFehler) as ctx:
            ota.rpi_senden(LOKAL, [str(self.datei)], port=konsole.port, eigene_ip=LOKAL,
                           abfrage_sekunden=0.05, zeitgrenze=0.4)
        self.assertEqual("zeit", ctx.exception.schluessel)


# ---------------------------------------------------------------------------
# Nachbildung: OnionHEN-Paketmanager
# ---------------------------------------------------------------------------

class _DpiNachbildung:
    """Der Paketmanager so, wie ihn die eigene Weboberflaeche anspricht."""

    def __init__(self) -> None:
        self.abgelegt: dict[str, bytearray] = {}
        self.bloecke: list[tuple[str, int, int, str]] = []   # name, offset, laenge, head256
        self.abschluesse: list[str] = []
        self.ping_name = "pkg-server"
        self.busy_zaehler = 0
        self.ablehnen: "set[int]" = set()          # Versaetze, die ein Mal abgelehnt werden
        self.abgelehnt_gesehen: "list[int]" = []
        self.kopf_header: list[dict[str, str]] = []
        nachbildung = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a) -> None:
                return

            def _json(self, status: int, daten: dict) -> None:
                roh = json.dumps(daten).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

            def do_GET(self) -> None:   # noqa: N802
                teile = urllib.parse.urlsplit(self.path)
                abfrage = urllib.parse.parse_qs(teile.query)
                if teile.path == "/ping":
                    nachbildung.busy_zaehler += 1
                    self._json(200, {"ok": True, "name": nachbildung.ping_name, "version": "1.0", "fw": 1200,
                                     "port": nachbildung.port, "busy": nachbildung.busy_zaehler in (2, 3)})
                elif teile.path == "/staged-size":
                    name = abfrage.get("name", [""])[0]
                    self._json(200, {"ok": True, "size": len(nachbildung.abgelegt.get(name, b""))})
                elif teile.path == "/api/config":
                    self._json(200, {"ok": True, "api_port": nachbildung.port})
                else:
                    self._json(404, {"ok": False, "error": "not_found"})

            def do_POST(self) -> None:   # noqa: N802
                teile = urllib.parse.urlsplit(self.path)
                abfrage = {k: v[0] for k, v in urllib.parse.parse_qs(teile.query).items()}
                if teile.path != "/install":
                    self._json(404, {"ok": False, "error": "not_found"})
                    return
                laenge = int(self.headers.get("Content-Length", 0))
                nachbildung.kopf_header.append({k: v for k, v in self.headers.items()})
                daten = self.rfile.read(laenge)
                name, versatz, gesamt = abfrage["name"], int(abfrage["offset"]), int(abfrage["total"])
                if abfrage.get("finalize") == "1":
                    nachbildung.abschluesse.append(name)
                    self._json(200, {"ok": True, "installed": False, "phase": "accepted", "staged": "kept"})
                    return
                if versatz in nachbildung.ablehnen:
                    nachbildung.ablehnen.discard(versatz)
                    nachbildung.abgelehnt_gesehen.append(versatz)
                    self._json(500, {"ok": False, "error": "block"})
                    return
                puffer = nachbildung.abgelegt.setdefault(name, bytearray(gesamt))
                if len(puffer) != gesamt:
                    puffer.extend(b"\x00" * (gesamt - len(puffer)))
                puffer[versatz:versatz + len(daten)] = daten
                nachbildung.bloecke.append((name, versatz, len(daten), abfrage.get("head256", "")))
                self._json(200, {"ok": True})

        self.server = ThreadingHTTPServer((LOKAL, 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True).start()

    def schliessen(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class DpiBloeckeTests(unittest.TestCase):

    def test_erster_block_dann_grosse_bloecke(self) -> None:
        with mock.patch.object(ota, "DPI_ERSTER_BLOCK", 10), mock.patch.object(ota, "DPI_BLOCK", 40):
            self.assertEqual([(0, 10), (10, 40), (50, 40), (90, 10)], ota.dpi_bloecke(100))
            self.assertEqual([(0, 7)], ota.dpi_bloecke(7))
            self.assertEqual([(0, 10)], ota.dpi_bloecke(10))
            self.assertEqual([(0, 10), (10, 1)], ota.dpi_bloecke(11))
            self.assertEqual([], ota.dpi_bloecke(0))

    def test_die_echten_groessen(self) -> None:
        bloecke = ota.dpi_bloecke(300 * 1024 * 1024)
        self.assertEqual((0, 1024 * 1024), bloecke[0])
        self.assertEqual(128 * 1024 * 1024, bloecke[1][1])
        self.assertEqual(300 * 1024 * 1024, sum(b[1] for b in bloecke))
        self.assertEqual(50 * 1024 ** 3, ota.DPI_HOECHSTGROESSE)

    def test_lueckenlos_und_ohne_ueberlappung(self) -> None:
        with mock.patch.object(ota, "DPI_ERSTER_BLOCK", 13), mock.patch.object(ota, "DPI_BLOCK", 37):
            for groesse in (1, 12, 13, 14, 50, 99, 1000):
                bloecke = ota.dpi_bloecke(groesse)
                ende = 0
                for versatz, laenge in bloecke:
                    self.assertEqual(ende, versatz)
                    ende = versatz + laenge
                self.assertEqual(groesse, ende)


class DpiClientTests(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.wo = Path(self._tmp.name)
        self.datei = _datei(self.wo, "Spiel Eins.pkg", 300_000)
        self.inhalt = self.datei.read_bytes()
        self.konsole = _DpiNachbildung()
        self.client = ota.DpiClient(LOKAL, self.konsole.port, web_port=self.konsole.port, zeit=5)
        self._klein = [mock.patch.object(ota, "DPI_ERSTER_BLOCK", 16 * 1024),
                       mock.patch.object(ota, "DPI_BLOCK", 100 * 1024)]
        for m in self._klein:
            m.start()

    def tearDown(self) -> None:
        for m in self._klein:
            m.stop()
        self.konsole.schliessen()
        self._tmp.cleanup()

    def test_ping_erkennt_den_manager(self) -> None:
        self.assertEqual("pkg-server", self.client.ping()["name"])

    def test_ein_fremder_dienst_wird_abgewiesen(self) -> None:
        self.konsole.ping_name = "etwas-anderes"
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.ping()
        self.assertEqual("fremd", ctx.exception.schluessel)

    def test_konfiguration_nennt_den_api_port(self) -> None:
        self.assertEqual(self.konsole.port, self.client.konfiguration()["api_port"])
        ohne = ota.DpiClient(LOKAL, self.konsole.port)
        with self.assertRaises(ota.OtaFehler):
            ohne.konfiguration()

    def test_der_kopfhash_ist_sha256_der_ersten_mebibyte(self) -> None:
        with mock.patch.object(ota, "DPI_ERSTER_BLOCK", 1000):
            self.assertEqual(_sha(self.inhalt[:1000]), ota.kopfhash(str(self.datei)))
        with mock.patch.object(ota, "DPI_ERSTER_BLOCK", 10 * 1024 * 1024):
            self.assertEqual(_sha(self.inhalt), ota.kopfhash(str(self.datei)), "Eine kleinere Datei zaehlt ganz.")

    def test_hochladen_liefert_dieselben_bytes(self) -> None:
        meldungen: list[tuple[int, int]] = []
        antwort = self.client.hochladen(str(self.datei), fortschritt=lambda a, g: meldungen.append((a, g)))
        self.assertTrue(antwort["ok"])
        self.assertEqual("accepted", antwort["phase"])
        self.assertEqual(self.inhalt, bytes(self.konsole.abgelegt["Spiel Eins.pkg"]))
        self.assertEqual(["Spiel Eins.pkg"], self.konsole.abschluesse)
        self.assertEqual((len(self.inhalt), len(self.inhalt)), meldungen[-1])
        self.assertTrue(all(a <= b for (a, _), (b, _) in zip(meldungen, meldungen[1:])), "Der Fortschritt lief rueckwaerts.")

    def test_der_erste_block_traegt_den_kopfhash_die_anderen_nicht(self) -> None:
        self.client.hochladen(str(self.datei))
        bloecke = sorted(self.konsole.bloecke, key=lambda b: b[1])
        self.assertEqual(_sha(self.inhalt[:16 * 1024]), bloecke[0][3])
        self.assertEqual("", "".join(b[3] for b in bloecke[1:]))
        self.assertEqual([0, 16384, 16384 + 102400, 16384 + 2 * 102400], [b[1] for b in bloecke])

    def test_die_anfrage_traegt_text_plain_und_laenge(self) -> None:
        self.client.hochladen(str(self.datei))
        # Der Abschluss (``finalize=1``) hat wie in der Weboberflaeche keinen Koerper.
        bloecke = [k for k in self.konsole.kopf_header if int(k.get("Content-Length", "0")) > 0]
        self.assertEqual(len(self.konsole.bloecke), len(bloecke))
        for kopf in bloecke:
            self.assertEqual("text/plain", kopf.get("Content-Type"))
        self.assertEqual(len(self.inhalt), sum(int(k["Content-Length"]) for k in bloecke))

    def test_ist_die_datei_schon_da_wird_nicht_noch_einmal_gesendet(self) -> None:
        self.konsole.abgelegt["Spiel Eins.pkg"] = bytearray(self.inhalt)
        meldungen: list[tuple[int, int]] = []
        self.client.hochladen(str(self.datei), fortschritt=lambda a, g: meldungen.append((a, g)))
        self.assertEqual([], self.konsole.bloecke, "Es wurden Bloecke gesendet, obwohl die Datei schon da war.")
        self.assertEqual(["Spiel Eins.pkg"], self.konsole.abschluesse)
        self.assertEqual((len(self.inhalt), len(self.inhalt)), meldungen[-1])

    def test_eine_abgelegte_datei_falscher_groesse_wird_neu_gesendet(self) -> None:
        self.konsole.abgelegt["Spiel Eins.pkg"] = bytearray(b"x" * 1000)
        self.client.hochladen(str(self.datei))
        self.assertEqual(self.inhalt, bytes(self.konsole.abgelegt["Spiel Eins.pkg"]))

    def test_ein_abgelehnter_block_wird_wiederholt(self) -> None:
        self.konsole.ablehnen = {16 * 1024}
        with mock.patch.object(ota.time, "sleep", lambda s: None):
            self.client.hochladen(str(self.datei))
        self.assertEqual([16 * 1024], self.konsole.abgelehnt_gesehen)
        self.assertEqual(self.inhalt, bytes(self.konsole.abgelegt["Spiel Eins.pkg"]))

    def test_ein_dauerhaft_abgelehnter_block_gibt_auf(self) -> None:
        class _Immer(set):
            def __contains__(self, x):   # noqa: D105
                return x == 16 * 1024
            def discard(self, x):   # noqa: D102
                pass
        self.konsole.ablehnen = _Immer()
        with mock.patch.object(ota.time, "sleep", lambda s: None):
            with self.assertRaises(ota.OtaFehler) as ctx:
                self.client.hochladen(str(self.datei), versuche=2)
        self.assertEqual("abgelehnt", ctx.exception.schluessel)
        self.assertEqual([], self.konsole.abschluesse, "Ohne alle Bloecke darf nichts abgeschlossen werden.")

    def test_der_abbruch_beendet_den_versand_ohne_abschluss(self) -> None:
        aufrufe = [0]

        def _abbruch() -> bool:
            aufrufe[0] += 1
            return aufrufe[0] > 2

        with self.assertRaises(ota.OtaAbgebrochen):
            self.client.hochladen(str(self.datei), abbruch=_abbruch)
        self.assertEqual([], self.konsole.abschluesse)

    def test_nur_pkg_nicht_leer_nicht_zu_gross(self) -> None:
        text = self.wo / "datei.txt"
        text.write_text("x")
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.hochladen(str(text))
        self.assertEqual("keine_pkg", ctx.exception.schluessel)
        leer = self.wo / "leer.pkg"
        leer.write_bytes(b"")
        with self.assertRaises(ota.OtaFehler) as ctx:
            self.client.hochladen(str(leer))
        self.assertEqual("leer", ctx.exception.schluessel)
        with mock.patch.object(ota, "DPI_HOECHSTGROESSE", 1000):
            with self.assertRaises(ota.OtaFehler) as ctx:
                self.client.hochladen(str(self.datei))
        self.assertEqual("zu_gross", ctx.exception.schluessel)
        self.assertEqual([], self.konsole.bloecke)

    def test_ein_eigener_name(self) -> None:
        self.client.hochladen(str(self.datei), name="Anderer Name.pkg")
        self.assertIn("Anderer Name.pkg", self.konsole.abgelegt)

    def test_dateinamen_mit_sonderzeichen(self) -> None:
        datei = _datei(self.wo, "Pokémon & Co [CUSA1].pkg", 50_000)
        self.client.hochladen(str(datei))
        self.assertEqual(datei.read_bytes(), bytes(self.konsole.abgelegt["Pokémon & Co [CUSA1].pkg"]))

    def test_warten_endet_wenn_der_manager_nicht_mehr_beschaeftigt_ist(self) -> None:
        gesehen: list[bool] = []
        letzter = self.client.warten(abfrage_sekunden=0.01, bei_ping=lambda p: gesehen.append(bool(p.get("busy"))),
                                     zeitgrenze=30)
        self.assertIn(True, gesehen)
        self.assertFalse(letzter.get("busy"))

    def test_warten_laesst_sich_abbrechen(self) -> None:
        with self.assertRaises(ota.OtaAbgebrochen):
            self.client.warten(abfrage_sekunden=0.01, abbruch=lambda: True)

    def test_keine_verbindung_ist_ein_netzfehler(self) -> None:
        with self.assertRaises(ota.OtaFehler) as ctx:
            ota.DpiClient(LOKAL, 1, zeit=1).ping()
        self.assertEqual("netz", ctx.exception.schluessel)


class ErkennenTests(unittest.TestCase):

    def test_paketmanager_am_api_port(self) -> None:
        konsole = _DpiNachbildung()
        self.addCleanup(konsole.schliessen)
        self.assertEqual(ota.ART_DPI_API, ota.erkennen(LOKAL, konsole.port))

    def test_remote_package_installer(self) -> None:
        konsole = _RpiNachbildung()
        self.addCleanup(konsole.schliessen)
        self.assertEqual(ota.ART_RPI, ota.erkennen(LOKAL, konsole.port))

    def test_nichts_dort(self) -> None:
        self.assertEqual("", ota.erkennen(LOKAL, 1, zeit=1))

    def test_ein_fremder_webserver_wird_nicht_erkannt(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a) -> None:
                return

            def do_GET(self) -> None:   # noqa: N802
                roh = b"<html>hallo</html>"
                self.send_response(200)
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

            do_POST = do_GET   # noqa: N815

        server = ThreadingHTTPServer((LOKAL, 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.assertEqual("", ota.erkennen(LOKAL, server.server_address[1], zeit=2))


if __name__ == "__main__":
    unittest.main()
