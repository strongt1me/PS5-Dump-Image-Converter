# -*- coding: utf-8 -*-
"""Stufe 2 der Ansicht KONSOLE: Dienste-Ampel und Payload-Startrampe.

Die haeufigste Ursache, wenn etwas mit der Konsole nicht klappt, ist ein
Payload, das gar nicht laeuft. Das Fenster "Konsole & Payloads" fragt alle
bekannten Ports ab und startet fehlende Dienste aus ``helloworld``.

Geprueft wird hier:

* die Abfrage gegen einen **echten** Port auf diesem Rechner (offen und zu),
* dass der Katalog in sich stimmt und zu den mitgelieferten Dateien passt,
* die Verdrahtung der Knoepfe der zweiten Ansicht,
* das Fenster selbst (oeffnet, Tabelle gefuellt, Knoepfe da).

Die Konsole selbst wird nicht gebraucht - und nichts an sie geschickt.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import konsole_dienste as kd      # noqa: E402
from ps5_validator.utils.i18n import STRINGS               # noqa: E402

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Horcher:
    """Ein echter, offener TCP-Port auf diesem Rechner.

    ``gruss`` schickt beim Verbinden etwas zurueck - damit laesst sich der
    haengende Dienst nachstellen (Port offen, aber stumm).
    """

    def __init__(self, gruss: bytes = b""):
        self._gruss = gruss

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self._faden = threading.Thread(target=self._annehmen, daemon=True)
        self._faden.start()
        return self

    def _annehmen(self):
        try:
            verbindung, _ = self.sock.accept()
            if self._gruss:
                verbindung.sendall(self._gruss)
            else:
                # Offen lassen und schweigen - wie der haengende ftpsrv.
                import time as _t
                _t.sleep(2.0)
            verbindung.close()
        except OSError:
            pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


def _freier_port() -> int:
    """Eine Portnummer, auf der sicher niemand horcht."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class KatalogTests(unittest.TestCase):

    def test_schluessel_und_ports_sind_eindeutig(self):
        schluessel = [d.schluessel for d in kd.KATALOG]
        self.assertEqual(len(schluessel), len(set(schluessel)))
        ports = [d.port for d in kd.KATALOG]
        self.assertEqual(len(ports), len(set(ports)))

    def test_die_bekannten_ports_stimmen(self):
        """Gegen das, was an der Konsole des Nutzers gemessen ist."""
        erwartet = {"elfldr9021": 9021, "pldmgr": 8084, "ftpsrv": 2121,
                    "klogsrv": 3232}
        for schluessel, port in erwartet.items():
            with self.subTest(dienst=schluessel):
                self.assertEqual(port, kd.dienst(schluessel).port)

    def test_ftpsrv_wird_am_gruss_gemessen(self):
        """Sonst meldet ein haengender ftpsrv faelschlich "laeuft"."""
        self.assertTrue(kd.dienst("ftpsrv").begruessung)

    def test_pkgmgr_haengt_an_seiner_weboberflaeche(self):
        """8844 = ``DEFAULT_HTTP_PORT`` aus der Quelle des PKG Managers.

        Die beiden anderen Ports (18841 Paketstrom, 18842 Direct Install)
        kommen mit demselben Payload hoch und werden nicht einzeln gefragt.
        """
        eintrag = kd.dienst("pkgmgr")
        self.assertEqual(8844, eintrag.port)
        self.assertEqual("http://10.0.0.5:8844/",
                         kd.web_adresse(eintrag, "10.0.0.5"))

    def test_shadowmount_hat_weboberflaeche_aber_kein_starten(self):
        """Bewusst ohne ``payload_muster`` (siehe Kommentar im Katalog): Ein
        TCP-Check kann "aus, weil api_bind_address=127.0.0.1" nicht von
        "laeuft wirklich nicht" unterscheiden - "Ausgewaehltes starten"
        haette sonst leicht eine zweite Instanz auf die Konsole geschickt.
        """
        eintrag = kd.dienst("shadowmount")
        self.assertIsNotNone(eintrag)
        self.assertEqual(10101, eintrag.port)
        self.assertEqual("/", eintrag.web)
        self.assertEqual("", eintrag.payload_muster)
        self.assertEqual("http://10.0.0.5:10101/",
                         kd.web_adresse(eintrag, "10.0.0.5"))

    def test_prosperomgr_hat_weboberflaeche_und_starten(self):
        """Anders als ShadowMount+: laeuft ueblicherweise nur auf Knopfdruck,
        ein TCP-Check kann "laeuft" hier also zuverlaessig von "laeuft nicht"
        unterscheiden - deshalb MIT ``payload_muster``.
        """
        eintrag = kd.dienst("prosperomgr")
        self.assertIsNotNone(eintrag)
        self.assertEqual(7070, eintrag.port)
        self.assertEqual("/", eintrag.web)
        self.assertTrue(eintrag.payload_muster)
        self.assertEqual("http://10.0.0.5:7070/",
                         kd.web_adresse(eintrag, "10.0.0.5"))

    def test_zu_jedem_muster_liegt_eine_datei_bei(self):
        """Faengt den Fall "Payload auf neue Fassung getauscht, Muster passt nicht mehr".

        Am 22.09.2026 wurde ``pkgmgr_v1.0.0.elf`` gegen ``pkgmgr_v1.2.2.elf``
        getauscht; ein auf die Fassung festgelegtes Muster haette danach still
        ins Leere gegriffen.
        """
        ordner = PROJEKT / "helloworld"
        for eintrag in kd.KATALOG:
            for muster in (eintrag.payload_muster, eintrag.datei_muster):
                if not muster:
                    continue
                with self.subTest(dienst=eintrag.schluessel, muster=muster):
                    self.assertTrue(
                        list(ordner.glob(muster)),
                        "keine Datei zu %s" % muster)

    def test_grundausstattung_steht_im_katalog(self):
        for schluessel in kd.GRUNDAUSSTATTUNG:
            with self.subTest(dienst=schluessel):
                eintrag = kd.dienst(schluessel)
                self.assertIsNotNone(eintrag)
                self.assertTrue(eintrag.payload_muster,
                                "ohne Datei laesst sich nichts starten")

    def test_jeder_dienst_ist_zweisprachig_beschriftet(self):
        for eintrag in kd.KATALOG:
            for schluessel in (eintrag.name_schluessel, eintrag.zweck_schluessel):
                with self.subTest(schluessel=schluessel):
                    self.assertIn(schluessel, STRINGS)
                    self.assertTrue(STRINGS[schluessel].get("de"))
                    self.assertTrue(STRINGS[schluessel].get("en"))

    def test_web_adresse(self):
        webfm = kd.dienst("webfm")
        self.assertEqual("http://10.0.0.5:8888/", kd.web_adresse(webfm, "10.0.0.5"))
        self.assertEqual("", kd.web_adresse(webfm, "   "))
        self.assertEqual("", kd.web_adresse(kd.dienst("ftpsrv"), "10.0.0.5"))


class WeitereDiensteTests(unittest.TestCase):
    """Die acht Dienste, die am 02.10.2026 dazukamen.

    Ports und Weboberflaechen stammen aus den Beschreibungen der Autoren (und
    bei CheatRunner, Game Compressor und gdbsrv zusaetzlich aus einer
    Zeichenkette im ELF); an der Konsole sind sie noch nicht nachgemessen.
    """

    #: (Schluessel, Port, Weboberflaeche, Muster der mitgelieferten Datei)
    ERWARTET = (
        ("cheatrunner", 9999, "/", "CheatRunner_v*.elf"),
        ("appdumper", 8081, "/", "ps5-app-dumper_v*.elf"),
        ("gamecompressor", 5910, "/", "game-compressor_v*.elf"),
        ("smplusgui", 7777, "/", "SMPlusGui_v*.elf"),
        ("aria2", 6800, "/", "aria2-v*.elf"),
        ("zftpd", 2120, "/", "zftpd-ps5-zhttp-v*.elf"),
        ("gdbsrv", 2159, "", "gdbsrv-ps5_v*.elf"),
        ("ps5debug", 744, "", "ps5debug-NG_v*.elf"),
    )

    def test_port_weboberflaeche_und_muster(self):
        for schluessel, port, web, muster in self.ERWARTET:
            with self.subTest(dienst=schluessel):
                eintrag = kd.dienst(schluessel)
                self.assertIsNotNone(eintrag, "%s fehlt im Katalog" % schluessel)
                self.assertEqual((port, web, muster),
                                 (eintrag.port, eintrag.web, eintrag.payload_muster))

    def test_web_adressen(self):
        erwartet = {"cheatrunner": "http://10.0.0.5:9999/", "appdumper": "http://10.0.0.5:8081/",
                    "gamecompressor": "http://10.0.0.5:5910/", "smplusgui": "http://10.0.0.5:7777/",
                    "aria2": "http://10.0.0.5:6800/", "zftpd": "http://10.0.0.5:2120/",
                    "gdbsrv": "", "ps5debug": ""}
        for schluessel, adresse in erwartet.items():
            with self.subTest(dienst=schluessel):
                self.assertEqual(adresse, kd.web_adresse(kd.dienst(schluessel), "10.0.0.5"))

    def test_die_version_der_mitgelieferten_datei_ist_lesbar(self):
        """Sonst stuende in der Spalte "Version" nur ein Strich."""
        ordner = PROJEKT / "helloworld"
        for schluessel, _port, _web, muster in self.ERWARTET:
            with self.subTest(dienst=schluessel):
                dateien = sorted(ordner.glob(muster))
                self.assertTrue(dateien, "keine Datei zu %s" % muster)
                self.assertTrue(kd.version_aus_dateiname(dateien[-1].name), dateien[-1].name)

    def test_zftpd_nimmt_nur_die_zhttp_fassung(self):
        """Nur sie traegt die Weboberflaeche; die schlanke FTP-Fassung darf das Muster nicht treffen."""
        eintrag = kd.dienst("zftpd")
        namen = [p.name for p in (PROJEKT / "helloworld").glob(eintrag.payload_muster)]
        self.assertTrue(namen)
        self.assertTrue(all("zhttp" in n for n in namen), namen)
        # Ohne Gruss gefragt: Die Fassung entscheidet bei einer Verbindung, ob FTP oder HTTP
        # gesprochen wird - ein erwarteter Gruss koennte einen laufenden Dienst als stumm melden.
        self.assertFalse(eintrag.begruessung)

    def test_bewusst_nicht_aufgenommen(self):
        """shsrv startet je Verbindung eine Shell (jede Abfrage wuerde einen Prozess erzeugen),
        MemDBG teilt sich TCP 9020 mit dem zweiten Port des ELF-Loaders, nanoDNS horcht auf UDP."""
        namen = {d.schluessel for d in kd.KATALOG}
        for fehlt in ("shsrv", "memdbg", "nanodns", "garlicworker"):
            with self.subTest(dienst=fehlt):
                self.assertNotIn(fehlt, namen)
        self.assertEqual(1, sum(1 for d in kd.KATALOG if d.port == 9020))


class AnyPadTests(unittest.TestCase):
    """AnyPad PS5 (04.10.2026): Bluetooth-Controller an der PS5, Weboberflaeche auf 8095.

    Wunsch des Nutzers: ueber "Konsole & Payloads" starten und die Weboberflaeche
    oeffnen. Port und Pfad stammen aus dem README des Autors (v0.5.5-beta) und aus
    dem ELF selbst; an der Konsole noch nicht nachgemessen.
    """

    def test_port_weboberflaeche_und_muster(self):
        eintrag = kd.dienst("anypad")
        self.assertIsNotNone(eintrag, "anypad fehlt im Katalog")
        self.assertEqual((8095, "/", "AnyPad-PS5-*.elf"),
                         (eintrag.port, eintrag.web, eintrag.payload_muster))
        self.assertEqual("http://10.0.0.5:8095/", kd.web_adresse(eintrag, "10.0.0.5"))

    def test_die_mitgelieferte_datei_nennt_ihre_seite_und_fassung(self):
        """Gegen die Datei selbst: Sie verweist auf ihre Seite unter 8095, und die
        Spalte "Version" bekommt eine Fassung aus dem Namen."""
        dateien = sorted((PROJEKT / "helloworld").glob(kd.dienst("anypad").payload_muster))
        self.assertEqual(1, len(dateien), dateien)
        self.assertIn(b"http://127.0.0.1:8095/", dateien[0].read_bytes())
        self.assertTrue(kd.version_aus_dateiname(dateien[0].name), dateien[0].name)


class AbfrageTests(unittest.TestCase):

    def test_offener_port_wird_erkannt(self):
        with _Horcher() as h:
            self.assertTrue(kd.port_offen("127.0.0.1", h.port, zeit=1.0))

    def test_geschlossener_port_wird_erkannt(self):
        self.assertFalse(kd.port_offen("127.0.0.1", _freier_port(), zeit=0.3))

    def test_uebersicht_an_echten_ports(self):
        with _Horcher() as h:
            zu = _freier_port()
            dienste = (kd.Dienst("offen", h.port, gruppe="elfldr"),
                       kd.Dienst("zu", zu))
            uebersicht = kd.pruefen("127.0.0.1", zeit=1.0, dienste=dienste)
            self.assertEqual(2, len(uebersicht))
            self.assertTrue(uebersicht.laeuft("offen"))
            self.assertFalse(uebersicht.laeuft("zu"))
            self.assertEqual(1, uebersicht.anzahl_laufend)
            self.assertEqual(h.port, uebersicht.loader_port)
            self.assertTrue(uebersicht.bereit)

    def test_ohne_adresse_wird_nichts_gefragt(self):
        uebersicht = kd.pruefen("   ")
        self.assertEqual(len(kd.KATALOG), len(uebersicht))
        self.assertEqual(0, uebersicht.anzahl_laufend)
        self.assertFalse(uebersicht.bereit)

    def test_haengender_dienst_gilt_nicht_als_laufend(self):
        """Port offen, kein Gruss: am 17.08.2026 an ftpsrv erlebt."""
        with _Horcher() as stumm:
            eintrag = kd.Dienst("ftpsrv", stumm.port, begruessung=True)
            laeuft, ist_stumm = kd.dienst_pruefen("127.0.0.1", eintrag, zeit=0.8)
            self.assertFalse(laeuft)
            self.assertTrue(ist_stumm)
            uebersicht = kd.pruefen("127.0.0.1", zeit=0.8, dienste=(eintrag,))
            self.assertFalse(uebersicht.laeuft("ftpsrv"))
            self.assertTrue(uebersicht.staende[0].stumm)

    def test_mit_gruss_gilt_der_dienst_als_laufend(self):
        with _Horcher(gruss=b"220 ftpsrv ready\r\n") as gut:
            eintrag = kd.Dienst("ftpsrv", gut.port, begruessung=True)
            self.assertEqual((True, False),
                             kd.dienst_pruefen("127.0.0.1", eintrag, zeit=0.8))

    def test_ohne_erwarteten_gruss_genuegt_der_offene_port(self):
        with _Horcher() as offen:
            eintrag = kd.Dienst("klogsrv", offen.port)
            self.assertEqual((True, False),
                             kd.dienst_pruefen("127.0.0.1", eintrag, zeit=0.8))

    def test_bereit_auch_ueber_den_payload_manager(self):
        dienste = (kd.Dienst("elfldr9021", 1, gruppe="elfldr"),
                   kd.Dienst("pldmgr", 2))
        uebersicht = kd.Uebersicht("1.2.3.4", [kd.Stand(dienste[0], False),
                                               kd.Stand(dienste[1], True)])
        self.assertTrue(uebersicht.bereit)
        self.assertIsNone(uebersicht.loader_port)


#: Wortgleich an der Konsole des Nutzers gemessen (26.09.2026).
FTPSRV_GRUSS = (b"220-Welcome to ftpsrv.elf running on pid 91\r\n",
                b"220-Version: 1.16-ng-stable (built Sep 20 2026 20:49:12)\r\n"
                b"220 Service is ready\r\n")
PLDMGR_TITEL = "Payload Manager v0.5.1 by PLK (eaa2d0a, built at 2026-08-02 13:18:31 UTC)"
#: Antwort des Payload-Managers auf "/version" (text/plain, 5 Bytes Rumpf).
PLDMGR_VERSION = b"0.5.1"


class _Gruesser:
    """Ein Dienst, der mehrzeilig gruesst - jede Verbindung, in Stuecken.

    ``danach_offen``: so lange bleibt die Verbindung nach dem letzten Stueck
    offen, ohne dass noch etwas kommt (ein langsamer oder stummer Dienst).
    """

    def __init__(self, teile, pause: float = 0.05, danach_offen: float = 0.0):
        self._teile, self._pause, self._offen = teile, pause, danach_offen

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._schleife, daemon=True).start()
        return self

    def _schleife(self):
        while True:
            try:
                verbindung, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._bedienen, args=(verbindung,), daemon=True).start()

    def _bedienen(self, verbindung):
        import time as _t
        with verbindung:
            try:
                for nummer, teil in enumerate(self._teile):
                    if nummer:
                        _t.sleep(self._pause)
                    verbindung.sendall(teil)
                _t.sleep(self._offen)
            except OSError:
                pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


class _Webseite:
    """Eine Weboberflaeche wie die des Payload-Managers.

    "/" ist eine grosse Seite (die echte hat 725.540 Bytes), "/version" nennt
    die Version (``version=None``: gibt es nicht, 404 wie bei einer aelteren
    Fassung). Eine Verbindung ohne Anfrage (die blosse Portpruefung) bleibt
    unbeantwortet.
    """

    def __init__(self, titel: str = PLDMGR_TITEL, groesse: int = 800_000,
                 verzoegerung: float = 0.0, version: "bytes | None" = PLDMGR_VERSION):
        self._titel, self._groesse, self._verzoegerung = titel, groesse, verzoegerung
        self._version = version

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._schleife, daemon=True).start()
        return self

    def _schleife(self):
        while True:
            try:
                verbindung, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._bedienen, args=(verbindung,), daemon=True).start()

    def _bedienen(self, verbindung):
        import time as _t
        with verbindung:
            try:
                verbindung.settimeout(3.0)
                anfrage = verbindung.recv(4096)
                if not anfrage:
                    return
                _t.sleep(self._verzoegerung)
                pfad = anfrage.split(b" ", 2)[1] if anfrage.count(b" ") >= 2 else b"/"
                if pfad == b"/version" and self._version is not None:
                    antwort = (b"HTTP/1.1 200 OK\r\nConnection: close\r\n"
                               b"Content-Type: text/plain\r\n\r\n" + self._version)
                elif pfad == b"/":
                    seite = ("<html><head><title>%s</title></head><body>"
                             % self._titel).encode()
                    antwort = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n"
                               b"Connection: close\r\n\r\n" + seite
                               + b"x" * self._groesse + b"</body></html>")
                else:
                    antwort = (b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n"
                               b"Content-Type: text/plain\r\n\r\n404 1.0 Not Found")
                # In zwei Stuecken mit Pause: Wer nach dem ersten aufhoert, faellt auf.
                verbindung.sendall(antwort[:2048])
                _t.sleep(0.05)
                verbindung.sendall(antwort[2048:])
            except OSError:
                pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


class _ShadowMountApi:
    """Die Schnittstelle von ShadowMount+ (docs/api.md): jede Anfrage ein POST mit JSON-Objekt.

    ``/api/v1/version`` antwortet mit ``shadowmount_version``; ein GET bekommt 405,
    jeder andere Pfad 404 - genau daran scheiterte der GET-Leser, der bis zum
    05.10.2026 der einzige Weg zur laufenden Version war. ``anfragen`` haelt fest,
    was ankam: (Methode, Pfad, Koerper).
    """

    def __init__(self, version: str = "1.7beta4", antwort: "bytes | None" = None):
        self._version = version
        self._antwort = antwort
        self.anfragen: "list[tuple[str, str, bytes]]" = []

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._schleife, daemon=True).start()
        return self

    def _schleife(self):
        while True:
            try:
                verbindung, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._bedienen, args=(verbindung,), daemon=True).start()

    def _bedienen(self, verbindung):
        import json as _json
        with verbindung:
            try:
                verbindung.settimeout(3.0)
                roh = b""
                while b"\r\n\r\n" not in roh:
                    stueck = verbindung.recv(4096)
                    if not stueck:
                        return          # blosse Portpruefung ohne Anfrage
                    roh += stueck
                kopf, _trenner, rest = roh.partition(b"\r\n\r\n")
                zeilen = kopf.split(b"\r\n")
                methode, pfad, _fassung = zeilen[0].split(b" ", 2)
                laenge = 0
                for zeile in zeilen[1:]:
                    if zeile.lower().startswith(b"content-length:"):
                        laenge = int(zeile.split(b":", 1)[1])
                while len(rest) < laenge:
                    stueck = verbindung.recv(4096)
                    if not stueck:
                        break
                    rest += stueck
                self.anfragen.append((methode.decode(), pfad.decode(), rest))
                json_typ = any(z.lower().startswith(b"content-type: application/json")
                               for z in zeilen[1:])
                if self._antwort is not None:
                    antwort = self._antwort
                elif methode == b"POST" and pfad == b"/api/v1/version" and json_typ:
                    koerper = _json.dumps({
                        "status": 0, "api_version": 1,
                        "shadowmount_version": self._version,
                        "capabilities": ["list_images", "list_games"]}).encode()
                    antwort = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                               b"Connection: close\r\n\r\n" + koerper)
                elif methode != b"POST":
                    antwort = (b"HTTP/1.1 405 Method Not Allowed\r\nConnection: close\r\n"
                               b"Content-Type: application/json\r\n\r\n"
                               b'{"status":1,"error":"POST required"}')
                else:
                    antwort = (b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n"
                               b"Content-Type: application/json\r\n\r\n"
                               b'{"status":2,"error":"no such route"}')
                verbindung.sendall(antwort)
            except OSError:
                pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


class VersionTests(unittest.TestCase):
    """Wunsch des Nutzers vom 26.09.2026: "Hier fehlt mir noch die Version der Payloads"."""

    def test_version_aus_dem_dateinamen(self):
        faelle = {
            "elfldr-ps5_v0.26.elf": "0.26",
            "ftpsrv-ps5_v1.16-ng-stable.elf": "1.16-ng-stable",
            "ftpsrv-ps5_v0.21.1.elf": "0.21.1",
            "klogsrv-ps5_v0.9.elf": "0.9",
            "pldmgr_v0.5.1.elf": "0.5.1",
            "web-file-mgr-v1.9.elf": "1.9",
            "ps5upload-5.33.2.elf": "5.33.2",
            "zftpd-ps5-v1.5.0.elf": "1.5.0",
            "kstuff_lite_v1.2-dr_Beta2.elf": "1.2-dr_Beta2",
            # Stufe ohne Trenner direkt hinter der Zahl (05.10.2026: "bei ShadowMount+
            # steht nie die Version" - das Muster verlangte vor "beta4" einen Strich).
            "shadowmountplus_v1.7beta4.elf": "1.7beta4",
            "shadowmountplus_v1.7alpha13fix1.elf": "1.7alpha13fix1",
            "AnyPad-PS5-0.5.5-beta.elf": "0.5.5-beta",
            "OnionHEN_v0.9.0-beta1.elf": "0.9.0-beta1",
            "dpiv2-13.60-1.00.elf": "1.00",
            # Mit Leerzeichen statt Unterstrich liest das Namensschema keine Fassung -
            # deshalb heisst die Datei im Ordner OnionHEN_v0.9.0-beta1.elf.
            "OnionHEN v0.9.0-beta1.elf": "",
            r"C:\irgendwo\helloworld\bfpilot_v0.4.4.elf": "0.4.4",
            "bdj_unpatch_1340.elf": "",
            "unjail-ps5app-payload.elf": "",
            "ProsperoMgr.elf": "",
            "": "",
        }
        for name, erwartet in faelle.items():
            with self.subTest(name=name):
                self.assertEqual(erwartet, kd.version_aus_dateiname(name))

    def test_jede_mitgelieferte_datei_nennt_eine_version(self):
        """Sonst bliebe die Spalte bei einem Dienst leer, obwohl eine Datei beiliegt."""
        ordner = PROJEKT / "helloworld"
        for eintrag in kd.KATALOG:
            muster = eintrag.payload_muster or eintrag.datei_muster
            for datei in ordner.glob(muster) if muster else ():
                with self.subTest(datei=datei.name):
                    self.assertTrue(kd.version_aus_dateiname(datei.name))

    def test_der_ftpsrv_nennt_seine_version_im_gruss(self):
        """Der Gruss kommt in zwei Stuecken - gelesen wird bis zur Version."""
        with _Gruesser(FTPSRV_GRUSS) as dienst:
            eintrag = kd.Dienst("ftpsrv", dienst.port, begruessung=True,
                                version_muster=kd.dienst("ftpsrv").version_muster)
            self.assertEqual("1.16-ng-stable",
                             kd.laufende_version("127.0.0.1", eintrag, zeit=1.0))

    @staticmethod
    def _pldmgr(port: int) -> kd.Dienst:
        vorbild = kd.dienst("pldmgr")
        return kd.Dienst("pldmgr", port, web="/", version_muster=vorbild.version_muster,
                         version_pfad=vorbild.version_pfad)

    def test_der_payload_manager_nennt_seine_version_unter_version(self):
        """Nicht aus der Startseite (725.540 Bytes, an der Konsole bis 6,5 s)."""
        self.assertEqual("/version", kd.dienst("pldmgr").version_pfad)
        with _Webseite() as seite:
            self.assertEqual("0.5.1", kd.laufende_version("127.0.0.1", self._pldmgr(seite.port),
                                                          zeit=1.0))

    def test_ohne_versionsabfrage_bleibt_die_version_leer(self):
        """Eine aeltere Fassung ohne "/version" antwortet 404 - das ist keine Version."""
        with _Webseite(version=None) as seite:
            self.assertEqual("", kd.laufende_version("127.0.0.1", self._pldmgr(seite.port),
                                                     zeit=1.0))

    def test_die_antwort_wird_bis_zum_ende_gelesen(self):
        """Nicht mittendrin abbrechen - die Antwort kommt hier in zwei Stuecken."""
        with _Webseite(groesse=50_000) as seite:
            text = kd._seite_lesen("127.0.0.1", seite.port, "/", 1.0)
        self.assertTrue(text.endswith("</body></html>"), text[-40:])
        self.assertGreater(len(text), 50_000)

    def test_eine_uebergrosse_antwort_wird_begrenzt(self):
        """Eine Versionsantwort hat 157 Bytes; was weit darueber geht, liest
        die Abfrage nicht bis zum Ende (SEITE_HOECHSTENS)."""
        with _Webseite(groesse=2_000_000) as seite:
            text = kd._seite_lesen("127.0.0.1", seite.port, "/", 1.0)
        self.assertLess(len(text), kd.SEITE_HOECHSTENS + 65536)

    def test_pruefen_traegt_die_versionen_ein(self):
        with _Gruesser(FTPSRV_GRUSS) as ftp, _Webseite() as web, _Horcher() as ohne:
            dienste = (kd.Dienst("ftpsrv", ftp.port, begruessung=True,
                                 version_muster=kd.dienst("ftpsrv").version_muster),
                       self._pldmgr(web.port),
                       kd.Dienst("klogsrv", ohne.port))
            uebersicht = kd.pruefen("127.0.0.1", zeit=1.0, dienste=dienste)
        self.assertEqual({"ftpsrv": (True, "1.16-ng-stable"), "pldmgr": (True, "0.5.1"),
                          "klogsrv": (True, "")},
                         {s.dienst.schluessel: (s.laeuft, s.version) for s in uebersicht})

    def test_ohne_version_im_gruss_laeuft_der_dienst_trotzdem(self):
        with _Gruesser((b"220 ftpsrv ready\r\n",), danach_offen=1.0) as dienst:
            eintrag = kd.Dienst("ftpsrv", dienst.port, begruessung=True,
                                version_muster=kd.dienst("ftpsrv").version_muster)
            stand = kd.pruefen("127.0.0.1", zeit=0.5, dienste=(eintrag,)).staende[0]
        self.assertEqual((True, False, ""), (stand.laeuft, stand.stumm, stand.version))

    def test_eine_langsame_version_haelt_den_zustand_nicht_auf(self):
        """Der Zustand steht vor der Versionsfrage fest; kommt sie zu spaet, fehlt nur sie."""
        import time as _t
        with _Webseite(groesse=1000, verzoegerung=3.0) as web:
            eintrag = self._pldmgr(web.port)
            beginn = _t.monotonic()
            stand = kd.pruefen("127.0.0.1", zeit=0.5, dienste=(eintrag,)).staende[0]
            dauer = _t.monotonic() - beginn
        self.assertTrue(stand.laeuft)
        self.assertEqual("", stand.version)
        self.assertLess(dauer, 2.5)

    def test_ohne_muster_wird_nicht_nach_der_version_gefragt(self):
        with mock.patch.object(kd, "_gruss_lesen") as gruss, \
                mock.patch.object(kd, "_seite_lesen") as seite:
            for schluessel in ("elfldr9021", "klogsrv", "websrv", "bfpilot"):
                with self.subTest(dienst=schluessel):
                    self.assertEqual("", kd.laufende_version("10.0.0.5", kd.dienst(schluessel)))
        gruss.assert_not_called()
        seite.assert_not_called()


class VersionOhneStartenTests(unittest.TestCase):
    """05.10.2026: "bei ShadowMount+ steht leider nie die Version bei Konsole & Payloads"
    und "bei elfldr 9020 ebenfalls".

    Beide Zeilen starten bewusst nichts aus der Tabelle (ShadowMount+ laeuft ueblicherweise
    aus dem Autoload, 9020 ist derselbe Dienst wie 9021); ohne Datei zum Starten stand bei
    ihnen aber immer ein Strich. Jetzt zeigt ``datei_muster`` die Version der beiliegenden
    Datei, und ShadowMount+ nennt - wenn seine Schnittstelle von diesem PC aus erreichbar
    ist - die laufende Fassung selbst.
    """

    def test_beide_zeilen_starten_nichts_und_zeigen_trotzdem_eine_version(self):
        for schluessel, muster in (("shadowmount", "shadowmountplus_v*.elf"),
                                   ("elfldr9020", "elfldr*.elf")):
            with self.subTest(dienst=schluessel):
                eintrag = kd.dienst(schluessel)
                self.assertEqual("", eintrag.payload_muster,
                                 "Die Zeile darf nichts aus der Tabelle starten.")
                self.assertEqual(muster, eintrag.datei_muster)
                dateien = sorted((PROJEKT / "helloworld").glob(eintrag.datei_muster))
                self.assertTrue(dateien, "keine Datei zu %s" % muster)
                self.assertTrue(kd.version_aus_dateiname(dateien[-1].name), dateien[-1].name)

    def test_dpiv2_steht_mit_weboberflaeche_in_der_tabelle(self):
        """Auftrag vom 05.10.2026: Was von den ELFs in helloworld/ eine Weboberflaeche hat,
        steht in "Konsole & Payloads" wie die anderen Payloads.

        Port 12800 = WebUI laut README des Autors (einstellbar; 9090 ist der
        Uebertragungsport desselben Plugins). Kein Start aus der Tabelle: Das Plugin
        liegt in /data/OnionHEN/plugins und wird von OnionHEN gestartet.
        """
        eintrag = kd.dienst("dpiv2")
        self.assertIsNotNone(eintrag, "DPI v2 fehlt im Katalog")
        self.assertEqual((12800, "/", "", "dpiv2-*.elf"),
                         (eintrag.port, eintrag.web, eintrag.payload_muster, eintrag.datei_muster))
        self.assertEqual("http://10.0.0.5:12800/", kd.web_adresse(eintrag, "10.0.0.5"))
        dateien = sorted((PROJEKT / "helloworld").glob(eintrag.datei_muster))
        self.assertEqual(1, len(dateien), dateien)
        # Gegen die Datei selbst: Sie traegt ihre Weboberflaeche und den Pfad ihrer Ablage.
        inhalt = dateien[0].read_bytes()
        self.assertIn(b"DPIV00001", inhalt)
        self.assertIn(b"<!doctype html", inhalt.lower())

    def test_shadowmount_nennt_die_laufende_version_per_post(self):
        """``POST /api/v1/version`` mit ``{}`` - nur so antwortet die Schnittstelle."""
        vorbild = kd.dienst("shadowmount")
        self.assertEqual("/api/v1/version", vorbild.version_post)
        with _ShadowMountApi("1.7beta4") as api:
            eintrag = kd.Dienst("shadowmount", api.port, web="/",
                                version_muster=vorbild.version_muster,
                                version_post=vorbild.version_post)
            self.assertEqual("1.7beta4", kd.laufende_version("127.0.0.1", eintrag, zeit=1.0))
        self.assertEqual([("POST", "/api/v1/version", b"{}")], api.anfragen)

    def test_pruefen_traegt_die_version_von_shadowmount_ein(self):
        vorbild = kd.dienst("shadowmount")
        with _ShadowMountApi("1.7") as api:
            eintrag = kd.Dienst("shadowmount", api.port, web="/",
                                version_muster=vorbild.version_muster,
                                version_post=vorbild.version_post)
            stand = kd.pruefen("127.0.0.1", zeit=1.0, dienste=(eintrag,)).staende[0]
        self.assertEqual((True, "1.7"), (stand.laeuft, stand.version))

    def test_ohne_brauchbare_antwort_bleibt_die_version_leer(self):
        """Fehlerseite, kein JSON, anderes Feld: Der Zustand bleibt, nur die Version fehlt."""
        vorbild = kd.dienst("shadowmount")
        antworten = {
            "404": (b"HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n"
                    b'{"status":2,"error":"no such route"}'),
            "kein JSON": b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n<html>Hallo</html>",
            "anderes Feld": (b"HTTP/1.1 200 OK\r\nConnection: close\r\n\r\n"
                             b'{"status":0,"version":"9.9"}'),
        }
        for name, antwort in antworten.items():
            with self.subTest(fall=name), _ShadowMountApi(antwort=antwort) as api:
                eintrag = kd.Dienst("shadowmount", api.port, web="/",
                                    version_muster=vorbild.version_muster,
                                    version_post=vorbild.version_post)
                self.assertEqual("", kd.laufende_version("127.0.0.1", eintrag, zeit=1.0))
                stand = kd.pruefen("127.0.0.1", zeit=1.0, dienste=(eintrag,)).staende[0]
                self.assertTrue(stand.laeuft, "Der Zustand haengt nicht an der Version.")

    def test_ein_get_leser_bekaeme_hier_keine_version(self):
        """Gegenprobe: Die Schnittstelle antwortet auf GET mit 405 - deshalb gibt es ``version_post``."""
        with _ShadowMountApi() as api:
            text = kd._seite_lesen("127.0.0.1", api.port, "/api/v1/version", 1.0)
        self.assertEqual("", text)
        self.assertEqual("GET", api.anfragen[0][0])

    def test_der_koerper_geht_mit_laenge_und_inhaltstyp_hinaus(self):
        with _ShadowMountApi() as api:
            text = kd._seite_lesen("127.0.0.1", api.port, "/api/v1/version", 1.0, post=b"{}")
        self.assertIn('"shadowmount_version"', text)

    def test_die_tabelle_zeigt_die_version_der_beiliegenden_datei(self):
        """Der Text der Spalte: ohne laufende Version die der Datei (aus ``datei_muster``)."""
        modul = _lade_hauptprogramm()
        app = modul.PS5ConverterGUI.__new__(modul.PS5ConverterGUI)
        app._t = lambda schluessel, **werte: STRINGS[schluessel]["de"].format(**werte)
        erwartet = {"shadowmount": "1.7beta4", "elfldr9020": "0.26", "dpiv2": "1.00",
                    "elfldr9021": "0.26"}
        for schluessel, version in erwartet.items():
            with self.subTest(dienst=schluessel):
                stand = kd.Stand(kd.dienst(schluessel))
                text = app._konsole_versionstext(stand)
                self.assertTrue(text and text != "–", "Die Spalte zeigt nur einen Strich.")
                if schluessel != "shadowmount":
                    self.assertEqual(version, text)
        # Nennt ShadowMount+ eine andere Fassung als die beiliegende, stehen beide da.
        stand = kd.Stand(kd.dienst("shadowmount"), laeuft=True, version="1.7")
        text = app._konsole_versionstext(stand)
        self.assertIn("1.7", text)
        self.assertIn(kd.version_aus_dateiname(
            sorted((PROJEKT / "helloworld").glob("shadowmountplus_v*.elf"))[-1].name), text)


class _CoolSysCentApi:
    """Die Weboberflaeche des PS5 Cooling & System Center: ``GET /api/v1/system`` nennt ``app_version``.

    Wie die echte Antwort ein JSON-Objekt (zusammengesetzt, mit der Fassung als eines von vielen Feldern);
    jeder andere Pfad antwortet 404. ``anfragen`` haelt (Methode, Pfad) fest.
    """

    def __init__(self, version: str = "1.48.0", kompakt: bool = True, antwort: "bytes | None" = None):
        self._version, self._kompakt, self._antwort = version, kompakt, antwort
        self.anfragen: "list[tuple[str, str]]" = []

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._schleife, daemon=True).start()
        return self

    def _schleife(self):
        while True:
            try:
                verbindung, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._bedienen, args=(verbindung,), daemon=True).start()

    def _bedienen(self, verbindung):
        import json as _json
        with verbindung:
            try:
                verbindung.settimeout(3.0)
                roh = verbindung.recv(4096)
                if not roh:
                    return                              # blosse Portpruefung ohne Anfrage
                methode, pfad = (roh.split(b" ", 2) + [b"", b""])[:2]
                self.anfragen.append((methode.decode(), pfad.decode()))
                if self._antwort is not None:
                    antwort = self._antwort
                elif methode == b"GET" and pfad == b"/api/v1/system":
                    daten = {"ok": True, "model": "CFI-1216A", "firmware_version": "12.00",
                             "uptime_sec": 3600, "app_version": self._version, "ip": "192.0.2.10"}
                    koerper = (_json.dumps(daten, separators=(",", ":")) if self._kompakt
                               else _json.dumps(daten, indent=2)).encode()
                    antwort = (b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
                               b"Connection: close\r\n\r\n" + koerper)
                else:
                    antwort = (b"HTTP/1.0 404 Not Found\r\nConnection: close\r\n\r\n"
                               b'{"ok":false,"error":"not_found"}')
                verbindung.sendall(antwort)
            except OSError:
                pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


class CoolSysCentTests(unittest.TestCase):
    """PS5 Cooling & System Center - Pro: die eigene App des Projektinhabers (05.10.2026).

    Auftrag: "Bitte bei Konsole & Payloads implementieren wie alle anderen auch, mit Version, Web UI Port usw.
    ... Knopf 5 ... wie der Prospero Manager im rechten Bereich die Web UI oeffnen. Laeuft die App noch nicht,
    soll die ELF an Port 9021 gesendet werden; ist der Port nicht offen, soll er geoeffnet werden."
    """

    @classmethod
    def setUpClass(cls):
        cls.dateien = sorted((PROJEKT / "helloworld").glob("PS5_Cooling_System_Center_v*.elf"))

    def test_der_katalog_kennt_die_app(self):
        eintrag = kd.dienst("coolsyscent")
        self.assertIsNotNone(eintrag, "PS5 Cooling & System Center fehlt im Katalog")
        self.assertEqual((8086, "/"), (eintrag.port, eintrag.web))
        self.assertEqual("PS5_Cooling_System_Center_v*.elf", eintrag.payload_muster,
                         "Mit payload_muster - die App startet auf Knopfdruck")
        self.assertEqual("/api/v1/system", eintrag.version_pfad)
        self.assertEqual("http://10.0.0.5:8086/", kd.web_adresse(eintrag, "10.0.0.5"))

    def test_die_datei_liegt_bei_und_nennt_ihre_version(self):
        self.assertEqual(1, len(self.dateien), self.dateien)
        self.assertEqual("1.48.0", kd.version_aus_dateiname(self.dateien[0].name))

    def test_die_elf_traegt_port_pfad_und_version_des_katalogs(self):
        """Gegen die Datei selbst: Wer die ELF austauscht und den Port aendert, faellt hier auf.

        Gemessen am 05.10.2026 an v1.48.0: ``"deeplinkUri": "http://127.0.0.1:8086"`` (Vorgabe von
        ``http_port``), die Route ``/api/v1/system`` mit dem Feld ``app_version`` und die Kopfzeile
        "PS5 Cooling & System Center - Pro 1.48.0".
        """
        eintrag = kd.dienst("coolsyscent")
        for datei in self.dateien:
            inhalt = datei.read_bytes()
            version = kd.version_aus_dateiname(datei.name)
            with self.subTest(datei=datei.name):
                self.assertIn(b'"deeplinkUri": "http://127.0.0.1:%d"' % eintrag.port, inhalt)
                self.assertIn(eintrag.version_pfad.encode(), inhalt)
                self.assertIn(b"app_version", inhalt)
                self.assertIn(("PS5 Cooling & System Center - Pro %s" % version).encode(), inhalt)
                self.assertIn(b"<!doctype html", inhalt.lower())

    def test_die_app_nennt_ihre_laufende_version(self):
        vorbild = kd.dienst("coolsyscent")
        for kompakt in (True, False):
            with self.subTest(kompakt=kompakt), _CoolSysCentApi("1.48.0", kompakt=kompakt) as api:
                eintrag = kd.Dienst("coolsyscent", api.port, web="/", version_muster=vorbild.version_muster,
                                    version_pfad=vorbild.version_pfad)
                self.assertEqual("1.48.0", kd.laufende_version("127.0.0.1", eintrag, zeit=1.0))
                self.assertEqual([("GET", "/api/v1/system")], api.anfragen)

    def test_pruefen_traegt_die_version_ein(self):
        vorbild = kd.dienst("coolsyscent")
        with _CoolSysCentApi("1.49.2") as api:
            eintrag = kd.Dienst("coolsyscent", api.port, web="/", version_muster=vorbild.version_muster,
                                version_pfad=vorbild.version_pfad)
            stand = kd.pruefen("127.0.0.1", zeit=1.0, dienste=(eintrag,)).staende[0]
        self.assertEqual((True, "1.49.2"), (stand.laeuft, stand.version))

    def test_ohne_brauchbare_antwort_bleibt_die_version_leer_und_der_dienst_laeuft(self):
        vorbild = kd.dienst("coolsyscent")
        antworten = {
            "404": b"HTTP/1.0 404 Not Found\r\nConnection: close\r\n\r\n{}",
            "ohne Feld": b'HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n{"ok":true,"model":"x"}',
            "Fehlerseite": b"HTTP/1.0 200 OK\r\nConnection: close\r\n\r\n<html>Abgelehnt</html>",
        }
        for name, antwort in antworten.items():
            with self.subTest(fall=name), _CoolSysCentApi(antwort=antwort) as api:
                eintrag = kd.Dienst("coolsyscent", api.port, web="/", version_muster=vorbild.version_muster,
                                    version_pfad=vorbild.version_pfad)
                self.assertEqual("", kd.laufende_version("127.0.0.1", eintrag, zeit=1.0))
                stand = kd.pruefen("127.0.0.1", zeit=1.0, dienste=(eintrag,)).staende[0]
                self.assertTrue(stand.laeuft, "Der Zustand haengt nicht an der Version.")

    def test_die_zeile_steht_mit_beiden_texten_und_ohne_strich_in_der_tabelle(self):
        eintrag = kd.dienst("coolsyscent")
        for schluessel in (eintrag.name_schluessel, eintrag.zweck_schluessel):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].strip())
        modul = _lade_hauptprogramm()
        app = modul.PS5ConverterGUI.__new__(modul.PS5ConverterGUI)
        app._t = lambda schluessel, **werte: STRINGS[schluessel]["de"].format(**werte)
        # Ohne laufende Version zeigt die Spalte die der beiliegenden Datei - nie nur einen Strich.
        text = app._konsole_versionstext(kd.Stand(eintrag))
        self.assertTrue(text and text != "–", "Die Spalte zeigt nur einen Strich.")
        self.assertIn("1.48.0", text)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self):
        # Knopf 1 sucht die PS5 selbst (Rundruf, notfalls das ganze Netz) -
        # im Test geht nichts ins Netz. Die Seite "Konsole & Payloads", die er
        # seit dem 26.09.2026 statt eines Fensters zeigt, pruefen die
        # SeitenTests in test_konsole_suche.
        flicken = mock.patch.object(self.app, "_konsole_ps5_finden",
                                    return_value=("", None, None, "dienste.suche_nichts"))
        flicken.start()
        self.addCleanup(flicken.stop)

    def test_die_knoepfe_der_ansicht_sind_verdrahtet(self):
        klasse = self.haupt.PS5ConverterGUI
        for kennung, methode in klasse._KONSOLE_FENSTER.items():
            with self.subTest(knopf=kennung):
                self.assertIn(kennung, [k for _s, k in klasse._KONSOLE_KNOEPFE])
                self.assertTrue(hasattr(klasse, methode), methode)

    def test_klog_steht_nur_noch_oben(self):
        """Seit dem 25.09.2026 steht an seiner Stelle die Bibliothek.

        So wollte es der Nutzer ("den Knopf oben (Bibliothek) in die neue
        Ansicht anstatt den Klog-Knopf"); KLOG bleibt in der Titelleiste.
        """
        klasse = self.haupt.PS5ConverterGUI
        kennungen = [k for _s, k in klasse._KONSOLE_KNOEPFE]
        self.assertNotIn("klog", kennungen)
        self.assertIn("bibliothek", kennungen)
        self.assertIn(("_btn_klog_title", "titlebar.klog", "_show_klog_window_geprueft"),
                      klasse._FALTBARE_TITELKNOEPFE)

    def test_bibliotheksknopf_zeigt_die_seite_statt_eines_fensters(self):
        with mock.patch.object(self.app, "_konsole_bibliothek_umschalten") as seite, \
                mock.patch.object(self.app, "_werkzeugfenster_umschalten") as fenster:
            self.app._konsole_knopf_gedrueckt("bibliothek", "konsole.btn_bibliothek")
        seite.assert_called_once_with()
        fenster.assert_not_called()

    def test_kennung_ohne_fenster_sagt_dass_es_folgt(self):
        """Das Auffangnetz fuer eine Kennung ohne Fenster.

        Seit Stufe 4 ist jeder Knopf der Seitenleiste verdrahtet - der Fall
        laesst sich also nicht mehr ueber einen Knopf ausloesen. Der Zweig
        im Code bleibt trotzdem: Er faengt einen Knopf ab, den jemand
        spaeter hinzufuegt, ohne ein Fenster dafuer zu bauen. Geprueft wird
        er deshalb direkt.
        """
        klasse = self.haupt.PS5ConverterGUI
        self.assertNotIn("gibt_es_noch_nicht", klasse._KONSOLE_FENSTER)
        with mock.patch.object(self.haupt, "messagebox") as box, \
                mock.patch.object(self.app, "_werkzeugfenster_umschalten") as um:
            self.app._konsole_knopf_gedrueckt("gibt_es_noch_nicht",
                                              "konsole.btn_dienste")
        um.assert_not_called()
        box.showinfo.assert_called_once()

    def test_verdrahtete_knoepfe_oeffnen_ihr_fenster(self):
        """Gegenstueck: Was in der Karte steht, muss auch aufgehen."""
        klasse = self.haupt.PS5ConverterGUI
        for kennung, methode in klasse._KONSOLE_FENSTER.items():
            with self.subTest(kennung=kennung):
                with mock.patch.object(self.app,
                                       "_werkzeugfenster_umschalten") as um:
                    self.app._konsole_knopf_gedrueckt(kennung, "konsole.btn_dienste")
                um.assert_called_once_with(methode)

    def test_payload_datei_nimmt_die_neueste_fassung(self):
        """helloworld traegt ftpsrv 0.21.1, 1.15 und 1.16 - 1.16 gewinnt."""
        pfad = self.app._konsole_payload_datei("ftpsrv-ps5*.elf")
        self.assertTrue(pfad, "keine ftpsrv-Datei in helloworld gefunden")
        self.assertIn("1.16", os.path.basename(pfad))
        self.assertEqual("", self.app._konsole_payload_datei(""))
        self.assertEqual("", self.app._konsole_payload_datei("gibtesnicht*.elf"))


class ProsperoMgrHinweisTests(unittest.TestCase):
    """Hinweis ohne Knopf waehrend des automatischen Sendens (Wunsch 01.10.2026).

    Erscheint nur, wenn der Dienst wirklich noch gesendet werden muss, und
    schliesst sich von selbst, sobald :meth:`_konsole_prosperomgr_oeffnen`
    fertig ist. Die Rueckrufe kommen aus dem Arbeitsfaden ueber
    ``root.after`` - die kommen nur an, solange eine echte Hauptschleife
    laeuft (``update()`` allein genuegt nicht; dasselbe Muster wie
    ``_schleife_bis`` in ``test_bibliothek_seite.py``).
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self):
        if getattr(self.app, "_konsole_tafel", None) is None:
            self.app._konsole_tafel_bauen()
        self.app._konsole_tafel_ip.set("127.0.0.1")
        self.app._konsole_webdienst_aktiv = False
        self.app._konsole_webdienst_hinweis_schliessen()

    def tearDown(self):
        self.app._konsole_webdienst_hinweis_schliessen()
        self.app._konsole_webdienst_aktiv = False

    @staticmethod
    def _uebersicht(laeuft: bool):
        u = mock.Mock()
        u.laeuft.side_effect = lambda schl: laeuft if schl == "prosperomgr" else False
        return u

    @staticmethod
    def _schleife(sekunden: float, beobachten=None, bis=None) -> None:
        """Eine echte Hauptschleife fuer hoechstens ``sekunden``.

        ``beobachten`` laeuft bei jedem Takt mit (haelt Zwischenstaende fest,
        etwa dass das Fenster kurz offen war); ``bis`` beendet die Schleife
        vorzeitig, sobald es wahr wird.
        """
        ende = time.monotonic() + sekunden

        def _takt() -> None:
            if beobachten is not None:
                beobachten()
            if (bis is not None and bis()) or time.monotonic() > ende:
                _WURZEL.quit()
            else:
                _WURZEL.after(10, _takt)

        _WURZEL.after(0, _takt)
        _WURZEL.mainloop()

    def test_hinweis_erscheint_nur_beim_wirklichen_senden_und_schliesst_sich(self):
        app = self.app

        def _elfldr_ersatz(_ip, _uebersicht, _texte):
            time.sleep(0.3)  # haelt den Arbeitsfaden kurz an, wie ein echter Versand
            return self._uebersicht(True)

        gesehen = {"ja": False}

        def _beobachten():
            if getattr(app, "_konsole_webdienst_hinweis_fenster", None) is not None:
                gesehen["ja"] = True

        with mock.patch.object(self.haupt.konsole_dienste, "pruefen",
                               return_value=self._uebersicht(False)), \
                mock.patch.object(app, "_konsole_elfldr_sicherstellen", _elfldr_ersatz), \
                mock.patch.object(app, "_webansicht_oeffnen") as web:
            app._konsole_prosperomgr_oeffnen()
            self._schleife(5.0, beobachten=_beobachten,
                           bis=lambda: gesehen["ja"] and web.called
                           and not app._konsole_webdienst_aktiv
                           and app._konsole_webdienst_hinweis_fenster is None)

        self.assertTrue(gesehen["ja"], "Der Hinweis ist nie erschienen.")
        web.assert_called_once()
        self.assertIsNone(app._konsole_webdienst_hinweis_fenster,
                          "Der Hinweis hat sich nicht von selbst geschlossen.")
        self.assertFalse(app._konsole_webdienst_aktiv)

    def test_kein_hinweis_wenn_der_dienst_schon_laeuft(self):
        """Wunsch vom 01.10.2026: "Ist der Payload bereits auf der PS5, soll
        die Meldung nicht erscheinen." Der Lauf muss dabei wirklich bis zur
        Weboberflaeche kommen - sonst bestuende der Test auch, wenn gar kein
        Rueckruf ankaeme."""
        app = self.app
        gesehen = {"ja": False}

        def _beobachten():
            if getattr(app, "_konsole_webdienst_hinweis_fenster", None) is not None:
                gesehen["ja"] = True

        with mock.patch.object(self.haupt.konsole_dienste, "pruefen",
                               return_value=self._uebersicht(True)), \
                mock.patch.object(app, "_konsole_elfldr_sicherstellen") as elfldr, \
                mock.patch.object(app, "_webansicht_oeffnen") as web:
            app._konsole_prosperomgr_oeffnen()
            self._schleife(5.0, beobachten=_beobachten,
                           bis=lambda: web.called and not app._konsole_webdienst_aktiv)
            # Noch ein paar Takte, damit auch der Abschluss aus ``finally``
            # durch ist, bevor geurteilt wird.
            self._schleife(0.2, beobachten=_beobachten)

        web.assert_called_once()
        elfldr.assert_not_called()
        self.assertFalse(gesehen["ja"], "Der Hinweis durfte hier nicht erscheinen - "
                                        "der Dienst lief schon.")
        self.assertIsNone(app._konsole_webdienst_hinweis_fenster)


if __name__ == "__main__":
    unittest.main(verbosity=2)
