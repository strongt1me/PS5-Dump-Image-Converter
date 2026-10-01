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
            if not eintrag.payload_muster:
                continue
            with self.subTest(dienst=eintrag.schluessel):
                self.assertTrue(
                    list(ordner.glob(eintrag.payload_muster)),
                    "keine Datei zu %s" % eintrag.payload_muster)

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
            for datei in ordner.glob(eintrag.payload_muster) if eintrag.payload_muster else ():
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
