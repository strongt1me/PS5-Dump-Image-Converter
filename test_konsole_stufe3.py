# -*- coding: utf-8 -*-
"""Stufe 3 der Ansicht KONSOLE: holen, zurueckspielen, Spielstaende.

Geprueft wird gegen einen **echten** kleinen FTP-Server auf diesem Rechner
(``_FtpStube``), nicht gegen eine Nachbildung von ``ftplib``. Grund: Die
Regeln, um die es hier geht, stehen zwischen den Zeilen des Protokolls -
wann eine Datenverbindung aufgemacht wird, wann eine Datei vollstaendig
angekommen ist, und vor allem: dass ein Abbruch erst **nach** der laufenden
Datei greift. Ein Mock haette genau das nicht gezeigt.

Die wichtigste Pruefung ist :meth:`AbbruchTests.test_abbruch_beendet_erst_die_laufende_datei`:
Ein mitten im ``RETR`` abgebrochener Download legt ftpsrv auf der echten
Konsole lahm (17.08.2026, nur ein Neustart half). Der Test setzt den
Abbruch **waehrend** der ersten Datei und misst, dass sie trotzdem
vollstaendig auf der Platte liegt und erst danach Schluss ist.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import konsole_dienste as kd       # noqa: E402
from ps5_validator.utils import konsole_ftp as kf           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PROJEKT = Path(__file__).resolve().parent

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001 - ohne Anzeige laufen nur die anderen Tests
    _WURZEL = None
    _TK_DA = False


class _FtpStube:
    """Ein winziger FTP-Server auf 127.0.0.1 - genug fuer ftplib.

    Beherrscht, was ``konsole_ftp`` braucht: Anmeldung ohne Kennwort,
    ``TYPE``, ``PASV``, ``MLSD``, ``RETR``, ``STOR``, ``MKD``, ``QUIT``.
    Er bedient **eine** Steuerverbindung nach der anderen; mehr braucht es
    nicht, weil jede Funktion des Moduls ihre Verbindung selbst auf- und
    abbaut.
    """

    def __init__(self, wurzel: Path) -> None:
        self.wurzel = Path(wurzel)
        self.horcher = socket.socket()
        self.horcher.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(4)
        self.port = self.horcher.getsockname()[1]
        self.laeuft = True
        #: Welche Dateien wurden tatsaechlich abgeholt? Das ist die Messung.
        self.geholt: list[str] = []
        self.faden = threading.Thread(target=self._bedienen, daemon=True,
                                      name="ftp-stube")
        self.faden.start()

    # -- Dienst -------------------------------------------------------

    def __enter__(self) -> "_FtpStube":
        return self

    def __exit__(self, *_rest) -> None:
        self.schliessen()

    def schliessen(self) -> None:
        self.laeuft = False
        try:
            self.horcher.close()
        except OSError:
            pass

    def _bedienen(self) -> None:
        while self.laeuft:
            try:
                verbindung, _ = self.horcher.accept()
            except OSError:
                return
            threading.Thread(target=self._sitzung, args=(verbindung,),
                             daemon=True, name="ftp-sitzung").start()

    # -- eine Sitzung -------------------------------------------------

    def _sitzung(self, steuer: socket.socket) -> None:
        steuer.settimeout(10.0)
        datei = steuer.makefile("rwb")
        datenhorcher: "socket.socket | None" = None
        try:
            self._sagen(datei, "220 ftp-stube bereit")
            while True:
                zeile = datei.readline()
                if not zeile:
                    return
                befehl, _, rest = zeile.decode("utf-8", "replace").strip(
                ).partition(" ")
                befehl = befehl.upper()

                if befehl in ("USER", "PASS"):
                    self._sagen(datei, "230 angemeldet" if befehl == "PASS"
                                else "331 weiter")
                elif befehl == "TYPE":
                    self._sagen(datei, "200 Typ gesetzt")
                elif befehl == "PWD":
                    self._sagen(datei, '257 "/"')
                elif befehl == "PASV":
                    datenhorcher = socket.socket()
                    datenhorcher.bind(("127.0.0.1", 0))
                    datenhorcher.listen(1)
                    datenhorcher.settimeout(10.0)
                    port = datenhorcher.getsockname()[1]
                    self._sagen(datei, "227 Entering Passive Mode "
                                       "(127,0,0,1,%d,%d)"
                                % (port // 256, port % 256))
                elif befehl in ("MLSD", "RETR", "STOR"):
                    if datenhorcher is None:
                        self._sagen(datei, "425 kein PASV")
                        continue
                    self._uebertragen(datei, datenhorcher, befehl, rest)
                    datenhorcher = None
                elif befehl == "MKD":
                    (self.wurzel / rest.strip("/")).mkdir(parents=True,
                                                          exist_ok=True)
                    self._sagen(datei, '257 "%s"' % rest)
                elif befehl == "QUIT":
                    self._sagen(datei, "221 tschuess")
                    return
                else:
                    self._sagen(datei, "502 kenne ich nicht")
        except (OSError, ValueError):
            return
        finally:
            try:
                datei.close()
            except OSError:
                pass
            try:
                steuer.close()
            except OSError:
                pass

    def _uebertragen(self, steuer, datenhorcher, befehl: str, rest: str) -> None:
        self._sagen(steuer, "150 Datenverbindung offen")
        try:
            daten, _ = datenhorcher.accept()
        except OSError:
            self._sagen(steuer, "425 keine Datenverbindung")
            return
        try:
            if befehl == "MLSD":
                for zeile in self._mlsd(rest):
                    daten.sendall(zeile.encode("utf-8"))
            elif befehl == "RETR":
                pfad = self._ortsteil(rest)
                self.geholt.append(rest.strip())
                with open(pfad, "rb") as quelle:
                    while True:
                        brocken = quelle.read(8192)
                        if not brocken:
                            break
                        daten.sendall(brocken)
            else:  # STOR
                pfad = self._ortsteil(rest)
                pfad.parent.mkdir(parents=True, exist_ok=True)
                with open(pfad, "wb") as ziel:
                    while True:
                        brocken = daten.recv(8192)
                        if not brocken:
                            break
                        ziel.write(brocken)
        except OSError:
            pass
        finally:
            try:
                daten.close()
            except OSError:
                pass
            try:
                datenhorcher.close()
            except OSError:
                pass
        self._sagen(steuer, "226 fertig")

    def _ortsteil(self, fern: str) -> Path:
        return self.wurzel / str(fern).strip().lstrip("/")

    def _mlsd(self, fern: str):
        ordner = self._ortsteil(fern)
        if not ordner.is_dir():
            return
        for eintrag in sorted(ordner.iterdir(), key=lambda p: p.name):
            if eintrag.is_dir():
                yield "type=dir;size=0; %s\r\n" % eintrag.name
            else:
                yield "type=file;size=%d; %s\r\n" % (
                    eintrag.stat().st_size, eintrag.name)

    @staticmethod
    def _sagen(datei, text: str) -> None:
        datei.write((text + "\r\n").encode("utf-8"))
        datei.flush()


def _baum_anlegen(wurzel: Path) -> None:
    """Ein kleiner Spielordner, wie ihn der App-Dumper hinterlaesst."""
    (wurzel / "PPSA01234" / "sce_sys").mkdir(parents=True, exist_ok=True)
    (wurzel / "PPSA01234" / "eboot.bin").write_bytes(b"E" * 200000)
    (wurzel / "PPSA01234" / "zweite.bin").write_bytes(b"Z" * 1000)
    (wurzel / "PPSA01234" / "sce_sys" / "param.json").write_bytes(b"{}")


class HilfenTests(unittest.TestCase):
    """Die kleinen Rechnungen - ohne Netz."""

    def test_hoehere_ebene(self):
        for eingabe, erwartet in (("/mnt/usb0/dump", "/mnt/usb0"),
                                  ("/mnt/usb0", "/mnt"),
                                  ("/mnt", "/"),
                                  ("/", "/"),
                                  ("", "/"),
                                  ("/mnt/usb0/", "/mnt")):
            with self.subTest(pfad=eingabe):
                self.assertEqual(erwartet, kf.hoehere_ebene(eingabe))

    def test_menge_lesbar(self):
        self.assertEqual("512 B", kf.menge_lesbar(512))
        self.assertEqual("1.0 KB", kf.menge_lesbar(1024))
        self.assertEqual("1.5 MB", kf.menge_lesbar(int(1.5 * 1024 * 1024)))
        self.assertEqual("0 B", kf.menge_lesbar(-5))

    def test_dauer_nach_gemessener_leitung(self):
        """1,1 MB/s ist die am 20.09.2026 gemessene Leitung zur Konsole."""
        sekunden = kf.dauer_schaetzen(1.1 * 1024 * 1024)
        self.assertAlmostEqual(1.0, sekunden, places=2)
        self.assertEqual(0.0, kf.dauer_schaetzen(0))

    def test_bekannte_orte_beginnen_beim_usb(self):
        """Der App-Dumper schreibt auf USB - deshalb steht der oben."""
        self.assertEqual("/mnt/usb0", kf.BEKANNTE_ORTE[0][0])

    def test_port_ist_2121(self):
        self.assertEqual(2121, kf.FTP_PORT)
        self.assertEqual(kd.dienst("ftpsrv").port, kf.FTP_PORT)


class UebertragungTests(unittest.TestCase):
    """Gegen den echten kleinen Server."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.fern = Path(self._tmp.name) / "konsole"
        self.lokal = Path(self._tmp.name) / "pc"
        self.fern.mkdir(parents=True)
        self.lokal.mkdir(parents=True)
        _baum_anlegen(self.fern)
        self.stube = _FtpStube(self.fern)

    def tearDown(self):
        self.stube.schliessen()
        self._tmp.cleanup()

    def test_auflisten_trennt_ordner_und_dateien(self):
        verbindung = kf.verbinden("127.0.0.1", self.stube.port)
        try:
            eintraege = kf.auflisten(verbindung, "/PPSA01234")
        finally:
            kf.schliessen(verbindung)
        namen = [e.name for e in eintraege]
        self.assertEqual(["sce_sys", "eboot.bin", "zweite.bin"], namen)
        self.assertTrue(eintraege[0].ordner)
        self.assertEqual(200000, eintraege[1].groesse)

    def test_groesse_schaetzen_zaehlt_den_ganzen_baum(self):
        zwischen: list[tuple[int, int]] = []
        dateien, bytes_ = kf.groesse_schaetzen(
            "127.0.0.1", "/PPSA01234", self.stube.port,
            melden=lambda d, b: zwischen.append((d, b)))
        self.assertEqual(3, dateien)
        self.assertEqual(200000 + 1000 + 2, bytes_)
        self.assertTrue(zwischen, "der Schritt muss sich melden")

    def test_ordner_holen_bringt_alles_mit_unterordner(self):
        meldungen: list[str] = []
        stand = kf.ordner_holen(
            "127.0.0.1", "/PPSA01234", self.lokal / "spiel", self.stube.port,
            auf_fortschritt=lambda f: meldungen.append(f.aktuell))
        self.assertFalse(stand.abgebrochen)
        self.assertEqual(3, stand.dateien)
        self.assertEqual(200000 + 1000 + 2, stand.bytes)
        self.assertTrue((self.lokal / "spiel" / "eboot.bin").is_file())
        self.assertEqual(
            b"{}", (self.lokal / "spiel" / "sce_sys" / "param.json").read_bytes())
        self.assertTrue(meldungen, "ohne Meldung waere es ein stiller Vorgang")

    def test_ordner_senden_legt_ordner_an(self):
        quelle = self.lokal / "fertig"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "sce_sys" / "param.json").write_bytes(b"{}")
        (quelle / "app.bin").write_bytes(b"A" * 4096)

        stand = kf.ordner_senden("127.0.0.1", quelle, "/ziel", self.stube.port)
        self.assertEqual(2, stand.dateien)
        self.assertEqual(4098, stand.bytes)
        self.assertEqual(b"A" * 4096, (self.fern / "ziel" / "app.bin").read_bytes())
        self.assertTrue((self.fern / "ziel" / "sce_sys" / "param.json").is_file())

    def test_fortschritt_anteil(self):
        stand = kf.Fortschritt(bytes=50, bytes_gesamt=200)
        self.assertAlmostEqual(0.25, stand.anteil)
        self.assertEqual(0.0, kf.Fortschritt(bytes=5).anteil)


class AbbruchTests(unittest.TestCase):
    """Die Regel, die auf der echten Konsole Geld gekostet hat."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.fern = Path(self._tmp.name) / "konsole"
        self.lokal = Path(self._tmp.name) / "pc"
        self.fern.mkdir(parents=True)
        self.lokal.mkdir(parents=True)
        (self.fern / "dump").mkdir()
        # Drei gleich grosse Dateien; die erste ist gross genug, dass der
        # Abbruch waehrend ihrer Uebertragung faellt.
        for name in ("a.bin", "b.bin", "c.bin"):
            (self.fern / "dump" / name).write_bytes(b"X" * 300000)
        self.stube = _FtpStube(self.fern)

    def tearDown(self):
        self.stube.schliessen()
        self._tmp.cleanup()

    def test_abbruch_beendet_erst_die_laufende_datei(self):
        """Abbruch mitten in der ersten Datei - sie muss ganz ankommen.

        Ein abgebrochener RETR legt ftpsrv lahm; nur ein Neustart der
        Konsole hilft. Deshalb darf der Abbruch die laufende Uebertragung
        nicht unterbrechen, sondern erst danach greifen.
        """
        schalter = {"aus": False}

        def _fortschritt(fort) -> None:
            # Mitten in der ersten Datei umlegen.
            if fort.bytes > 1000:
                schalter["aus"] = True

        stand = kf.ordner_holen(
            "127.0.0.1", "/dump", self.lokal / "ziel", self.stube.port,
            auf_fortschritt=_fortschritt,
            abbruch=lambda: schalter["aus"],
            dateien_gesamt=3, bytes_gesamt=900000)

        self.assertTrue(stand.abgebrochen, "der Abbruch muss ankommen")
        self.assertEqual(1, stand.dateien, "genau die laufende Datei zu Ende")
        erste = self.lokal / "ziel" / "a.bin"
        self.assertEqual(300000, erste.stat().st_size,
                         "die laufende Datei muss vollstaendig sein")
        self.assertFalse((self.lokal / "ziel" / "b.bin").exists())
        # Und der Server hat auch wirklich nur eine Datei ausgeliefert.
        self.assertEqual(1, len([p for p in self.stube.geholt
                                 if p.endswith(".bin")]))

    def test_abbruch_vor_der_ersten_datei_holt_nichts(self):
        stand = kf.ordner_holen(
            "127.0.0.1", "/dump", self.lokal / "ziel2", self.stube.port,
            abbruch=lambda: True)
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(0, stand.dateien)
        self.assertEqual([], [p for p in self.stube.geholt
                              if p.endswith(".bin")])

    def test_senden_bricht_ebenfalls_zwischen_dateien_ab(self):
        quelle = self.lokal / "raus"
        quelle.mkdir()
        for name in ("a.bin", "b.bin"):
            (quelle / name).write_bytes(b"Y" * 200000)
        schalter = {"aus": False}

        def _fortschritt(fort) -> None:
            if fort.bytes > 1000:
                schalter["aus"] = True

        stand = kf.ordner_senden("127.0.0.1", quelle, "/rein", self.stube.port,
                                 auf_fortschritt=_fortschritt,
                                 abbruch=lambda: schalter["aus"])
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(1, stand.dateien)
        self.assertEqual(200000, (self.fern / "rein" / "a.bin").stat().st_size)


class FehlerTests(unittest.TestCase):

    def test_ohne_adresse_kein_versuch(self):
        with self.assertRaises(kf.FtpFehler):
            kf.verbinden("   ")

    def test_geschlossener_port_meldet_ftpsrv(self):
        horcher = socket.socket()
        horcher.bind(("127.0.0.1", 0))
        port = horcher.getsockname()[1]
        horcher.close()
        with self.assertRaises(kf.FtpFehler) as fehler:
            kf.verbinden("127.0.0.1", port, zeit=1.0)
        self.assertIn("ftpsrv", str(fehler.exception))

    def test_senden_ohne_ordner(self):
        with self.assertRaises(kf.FtpFehler):
            kf.ordner_senden("127.0.0.1", "/gibt/es/nicht", "/ziel")


class TexteTests(unittest.TestCase):
    """Jeder benutzte Schluessel muss zweisprachig dastehen."""

    SCHLUESSEL = (
        "holen.window_title", "holen.subtitle", "holen.hint_dumper",
        "holen.label_remote", "holen.label_local", "holen.col_name",
        "holen.col_art", "holen.col_groesse", "holen.art_ordner",
        "holen.art_datei", "holen.btn_dump", "holen.btn_list", "holen.btn_up",
        "holen.btn_size", "holen.btn_fetch", "holen.btn_cancel",
        "holen.choose_local", "holen.need_local", "holen.no_dumper",
        "holen.status_idle", "holen.status_dumping", "holen.status_dumped",
        "holen.status_listing", "holen.status_listed", "holen.status_sizing",
        "holen.status_sized", "holen.status_fetching", "holen.status_file",
        "holen.status_done", "holen.status_cancelled", "holen.status_failed",
        "holen.size_running", "holen.size_done", "holen.log_dumper",
        "holen.log_start", "holen.log_done", "holen.log_cancelled",
        "zurueck.window_title", "zurueck.subtitle", "zurueck.label_local",
        "zurueck.label_remote", "zurueck.choose_local", "zurueck.hint_ftp",
        "zurueck.hint_move", "zurueck.btn_send", "zurueck.btn_cancel",
        "zurueck.btn_webfm_start", "zurueck.btn_webfm", "zurueck.need_local",
        "zurueck.need_remote", "zurueck.no_webfm", "zurueck.status_idle",
        "zurueck.status_sending", "zurueck.status_file", "zurueck.status_done",
        "zurueck.status_cancelled", "zurueck.status_failed",
        "zurueck.status_webfm", "zurueck.size_line", "zurueck.log_start",
        "zurueck.log_done", "zurueck.log_cancelled", "zurueck.log_webfm",
        "zurueck.log_webfm_port", "zurueck.log_webfm_kein_port",
        "spielstaende.window_title", "spielstaende.subtitle",
        "spielstaende.usage", "spielstaende.warn_backup",
        "spielstaende.warn_benutzer", "spielstaende.btn_check",
        "spielstaende.btn_start", "spielstaende.btn_open",
        "spielstaende.status_idle", "spielstaende.status_checking",
        "spielstaende.status_starting", "spielstaende.status_failed",
        "spielstaende.running", "spielstaende.stopped", "spielstaende.opened",
        "spielstaende.no_file", "spielstaende.log_start",
        "konsoleftp.log_ftp_aus", "konsoleftp.log_ftp_stumm",
        "konsoleftp.log_abbruch_gemerkt",
    )

    def test_alle_schluessel_zweisprachig(self):
        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))

    def test_abbruchhinweis_nennt_den_grund(self):
        """Der Anwender soll wissen, warum nicht sofort Schluss ist."""
        self.assertIn("ftpsrv", STRINGS["konsoleftp.log_abbruch_gemerkt"]["de"])


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):
    """Die drei Fenster oeffnen - am wirklichen Programm."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        pfad = str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
        spec = importlib.util.spec_from_file_location("hauptprogramm", pfad)
        cls.modul = importlib.util.module_from_spec(spec)
        sys.modules["hauptprogramm"] = cls.modul
        spec.loader.exec_module(cls.modul)
        cls.app = cls.modul.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _fenster_oeffnen(self, name: str):
        vorher = set(_WURZEL.winfo_children())
        getattr(self.app, name)()
        _WURZEL.update()
        neu = [w for w in _WURZEL.winfo_children() if w not in vorher]
        self.assertTrue(neu, "%s hat kein Fenster geoeffnet" % name)
        return neu[-1]

    @staticmethod
    def _beschriftungen(fenster) -> list[str]:
        texte: list[str] = []

        def _durch(widget):
            for kind in widget.winfo_children():
                try:
                    texte.append(str(kind.cget("text")))
                except Exception:  # noqa: BLE001
                    pass
                _durch(kind)

        _durch(fenster)
        return texte

    def test_alle_drei_kennungen_sind_verdrahtet(self):
        karte = self.modul.PS5ConverterGUI._KONSOLE_FENSTER
        for kennung, methode in (("spiel_holen", "_show_konsole_spiel_holen"),
                                 ("zurueckspielen", "_show_konsole_zurueckspielen"),
                                 ("spielstaende", "_show_konsole_spielstaende")):
            with self.subTest(kennung=kennung):
                self.assertEqual(methode, karte.get(kennung))
                self.assertTrue(hasattr(self.app, methode))

    def test_jede_kennung_der_seitenleiste_hat_ihr_ziel(self):
        """Kein Knopf der Ansicht darf auf eine fehlende Methode zeigen."""
        for _schluessel, kennung in self.modul.PS5ConverterGUI._KONSOLE_KNOEPFE:
            methode = self.modul.PS5ConverterGUI._KONSOLE_FENSTER.get(kennung)
            if not methode:
                continue  # sagt noch "kommt in einer der naechsten Stufen"
            with self.subTest(kennung=kennung):
                self.assertTrue(callable(getattr(self.app, methode, None)))

    def test_spiel_holen_zeigt_seine_drei_schritte(self):
        fenster = self._fenster_oeffnen("_show_konsole_spiel_holen")
        try:
            texte = self._beschriftungen(fenster)
            for schluessel in ("holen.btn_dump", "holen.btn_list",
                               "holen.btn_size", "holen.btn_fetch",
                               "holen.btn_cancel"):
                with self.subTest(knopf=schluessel):
                    self.assertIn(self.app._t(schluessel), texte)
        finally:
            fenster.destroy()
            _WURZEL.update()

    def test_zurueckspielen_hat_uebertragen_und_dateimanager(self):
        fenster = self._fenster_oeffnen("_show_konsole_zurueckspielen")
        try:
            texte = self._beschriftungen(fenster)
            for schluessel in ("zurueck.btn_send", "zurueck.btn_webfm_start",
                               "zurueck.btn_webfm", "zurueck.btn_cancel"):
                with self.subTest(knopf=schluessel):
                    self.assertIn(self.app._t(schluessel), texte)
        finally:
            fenster.destroy()
            _WURZEL.update()

    def test_spielstaende_warnt_vor_dem_schreiben(self):
        fenster = self._fenster_oeffnen("_show_konsole_spielstaende")
        try:
            texte = self._beschriftungen(fenster)
            self.assertIn(self.app._t("spielstaende.warn_backup"), texte)
            self.assertIn(self.app._t("spielstaende.btn_start"), texte)
        finally:
            fenster.destroy()
            _WURZEL.update()

    def test_kein_arbeitsfaden_bleibt_stehen(self):
        """Die Fenster duerfen beim Oeffnen keinen Faden starten."""
        vorher = {t.name for t in threading.enumerate()}
        for name in ("_show_konsole_spiel_holen",
                     "_show_konsole_zurueckspielen",
                     "_show_konsole_spielstaende"):
            fenster = self._fenster_oeffnen(name)
            fenster.destroy()
            _WURZEL.update()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertEqual(set(), {n for n in neu if n.startswith("konsole-")})


if __name__ == "__main__":
    unittest.main()
