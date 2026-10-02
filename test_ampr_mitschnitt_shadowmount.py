# -*- coding: utf-8 -*-
"""Mitschnitt-Assistent und ShadowMount+: laedt die Konsole die Aufnahme-Bibliothek?

Anlass (01.10.2026, Frage eines Anwenders): "Wie macht das Dein Tool - die
Aktivierung des Debug-Emus, auch wenn das global per ShadowMount
ueberschrieben wird? Dann muss ja die config angepasst werden?"

Im Code nachgesehen stimmte das: Der Assistent legte die Aufnahme-Bibliothek
immer in den Spielordner und fasste die config.ini nicht an. Drei Wege
machten die Aufnahme so wirkungslos (am Quelltext von ShadowMount+ belegt,
siehe ``shadowmount_generation``):

* Ein Backport-Ordner ``<scanpath>/backports/<TITLE_ID>/`` geht dem
  Spielordner vor - und genau dorthin legt Aufgabe 7 ab.
* Mit ``update_emulators=1`` ersetzt eine ``libSceAmpr.sprx`` aus
  ``emulators_path`` die des Spiels im Cache; ebenso die globale fakelib mit
  ``global_fakelib_priority=global``; ``backport_fakelib=0`` haengt gar
  nichts ein.
* Hat das Spiel ``fakelib`` und ``fakelib2``, nimmt jede Fassung einen
  anderen.

Bewacht wird die reine Regel (ohne Netz) und der Ablauf gegen eine **echte**
FTP-Stube auf 127.0.0.1 (ftplib spricht mit einem kleinen Server ueber einem
Testordner): pruefen, umstellen, hochladen, zurueckstellen - Byte fuer Byte.
"""
from __future__ import annotations

import ast
import os
import posixpath
import queue
import socket
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_mitschnitt_shadowmount")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import shadowmount_generation as sm  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PS5ConverterGUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
TITEL = "PPSA01234"
SPIEL = "/data/homebrew/GAME"
EMUS = "/data/shadowmount/emus"
GLOBAL = "/data/shadowmount/fakelib"
CONFIG = "/data/shadowmount/config.ini"

#: So liefert ShadowMount+ seine config.ini aus: alles auskommentiert.
VORLAGE = (
    "# ShadowMountPlus configuration\r\n"
    "# backport_fakelib=1\r\n"
    "# update_emulators=1\r\n"
    "# emulators_path=/data/shadowmount/emus\r\n"
    "# global_fakelib=1\r\n"
    "# global_fakelib_priority=game\r\n"
    "scanpath=/data/homebrew\r\n"
)


class _FtpStube:
    """Ein winziger FTP-Server auf 127.0.0.1 ueber einem Testordner.

    Gebaut nach ``test_konsole_stufe3._FtpStube``, dazu ``RNFR``/``RNTO``
    (das atomare Hochladen ueber ``.tmp``) und ``DELE``. ``size_kaputt``
    beantwortet ``SIZE`` mit 502 wie ein Server, der es nicht kennt.
    """

    def __init__(self, wurzel: Path, *, size_kaputt: bool = False) -> None:
        self.wurzel = Path(wurzel)
        self.size_kaputt = size_kaputt
        self.anmeldungen = 0
        self.horcher = socket.socket()
        self.horcher.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.horcher.bind(("127.0.0.1", 0))
        self.horcher.listen(8)
        self.port = self.horcher.getsockname()[1]
        self.laeuft = True
        threading.Thread(target=self._bedienen, daemon=True,
                         name="ftp-stube-sm").start()

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
                             daemon=True, name="ftp-sitzung-sm").start()

    def _ort(self, fern: str) -> Path:
        return self.wurzel / str(fern).strip().lstrip("/")

    def _sitzung(self, steuer: socket.socket) -> None:
        steuer.settimeout(10.0)
        datei = steuer.makefile("rwb")
        daten_h: "socket.socket | None" = None
        cwd = "/"
        von: "Path | None" = None
        try:
            self._sagen(datei, "220 bereit")
            while True:
                zeile = datei.readline()
                if not zeile:
                    return
                befehl, _, rest = zeile.decode("utf-8", "replace").strip().partition(" ")
                befehl = befehl.upper()
                if befehl == "USER":
                    self._sagen(datei, "331 weiter")
                elif befehl == "PASS":
                    self.anmeldungen += 1
                    self._sagen(datei, "230 angemeldet")
                elif befehl == "TYPE":
                    self._sagen(datei, "200 Typ")
                elif befehl == "PWD":
                    self._sagen(datei, '257 "%s"' % cwd)
                elif befehl == "CWD":
                    ziel = rest.strip() or "/"
                    neu = posixpath.normpath(
                        ziel if ziel.startswith("/") else posixpath.join(cwd, ziel))
                    if self._ort(neu).is_dir():
                        cwd = neu
                        self._sagen(datei, "250 OK")
                    else:
                        self._sagen(datei, "550 No such directory")
                elif befehl == "PASV":
                    daten_h = socket.socket()
                    daten_h.bind(("127.0.0.1", 0))
                    daten_h.listen(1)
                    daten_h.settimeout(10.0)
                    port = daten_h.getsockname()[1]
                    self._sagen(datei, "227 Entering Passive Mode (127,0,0,1,%d,%d)"
                                % (port // 256, port % 256))
                elif befehl in ("MLSD", "RETR", "STOR"):
                    if daten_h is None:
                        self._sagen(datei, "425 kein PASV")
                        continue
                    pfad = rest.strip() or cwd
                    if befehl == "RETR" and not self._ort(pfad).is_file():
                        self._sagen(datei, "550 No such file")
                        daten_h.close()
                        daten_h = None
                        continue
                    self._uebertragen(datei, daten_h, befehl, pfad)
                    daten_h = None
                elif befehl == "SIZE":
                    if self.size_kaputt:
                        self._sagen(datei, "502 SIZE kenne ich nicht")
                    elif self._ort(rest).is_file():
                        self._sagen(datei, "213 %d" % self._ort(rest).stat().st_size)
                    else:
                        self._sagen(datei, "550 No such file")
                elif befehl == "MKD":
                    self._ort(rest).mkdir(parents=True, exist_ok=True)
                    self._sagen(datei, '257 "%s"' % rest)
                elif befehl == "RNFR":
                    von = self._ort(rest) if self._ort(rest).exists() else None
                    self._sagen(datei, "350 weiter" if von else "550 No such file")
                elif befehl == "RNTO":
                    if von is None:
                        self._sagen(datei, "503 erst RNFR")
                    else:
                        ziel = self._ort(rest)
                        ziel.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(von, ziel)        # wie rename(2): ersetzt
                        von = None
                        self._sagen(datei, "250 umbenannt")
                elif befehl == "DELE":
                    if self._ort(rest).is_file():
                        self._ort(rest).unlink()
                        self._sagen(datei, "250 geloescht")
                    else:
                        self._sagen(datei, "550 No such file")
                elif befehl == "QUIT":
                    self._sagen(datei, "221 tschuess")
                    return
                else:
                    self._sagen(datei, "502 kenne ich nicht")
        except (OSError, ValueError):
            return
        finally:
            for ding in (datei, steuer):
                try:
                    ding.close()
                except OSError:
                    pass

    def _uebertragen(self, steuer, daten_h, befehl: str, pfad: str) -> None:
        self._sagen(steuer, "150 offen")
        try:
            daten, _ = daten_h.accept()
        except OSError:
            self._sagen(steuer, "425 keine Datenverbindung")
            return
        try:
            if befehl == "MLSD":
                ordner = self._ort(pfad)
                if ordner.is_dir():
                    for eintrag in sorted(ordner.iterdir(), key=lambda p: p.name):
                        art = "dir" if eintrag.is_dir() else "file"
                        groesse = 0 if eintrag.is_dir() else eintrag.stat().st_size
                        daten.sendall(("type=%s;size=%d; %s\r\n"
                                       % (art, groesse, eintrag.name)).encode("utf-8"))
            elif befehl == "RETR":
                daten.sendall(self._ort(pfad).read_bytes())
            else:
                ziel = self._ort(pfad)
                ziel.parent.mkdir(parents=True, exist_ok=True)
                with open(ziel, "wb") as aus:
                    while True:
                        brocken = daten.recv(8192)
                        if not brocken:
                            break
                        aus.write(brocken)
        except OSError:
            pass
        finally:
            for ding in (daten, daten_h):
                try:
                    ding.close()
                except OSError:
                    pass
        self._sagen(steuer, "226 fertig")

    @staticmethod
    def _sagen(datei, text: str) -> None:
        datei.write((text + "\r\n").encode("utf-8"))
        datei.flush()


def _pruefling(testfall: unittest.TestCase) -> PS5ConverterGUI:
    """Ein Programm ohne Oberflaeche - Konsole und Dateien sind echt."""
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    g._current_language = "de"
    g._log_lines = []
    g._append_to_log = g._log_lines.append
    g._set_status = lambda *_a, **_k: None
    g.engine_output_queue = queue.Queue()
    g.is_running = True
    # Jede Rueckfrage, die ein Test nicht ausdruecklich beantwortet, ist ein
    # Fehler im Test. Weil ein except Exception sie schlucken koennte, wird
    # am Ende auch von aussen geprueft (test_qualitaetslauf).
    g._ampr_gen_frage = mock.Mock(side_effect=AssertionError("unerwartete Frage"))
    testfall.addCleanup(g._ampr_gen_frage.assert_not_called)
    return g


def _text(kennung: str, /, **werte) -> str:
    # Positionsgebunden: Ein Platzhalter darf {schluessel} heissen.
    return STRINGS[kennung]["de"].format(**werte)


class RegelTests(unittest.TestCase):
    """aufnahme_ablage / aufnahme_gefahren / schalter_an - ohne Netz."""

    def test_schalter(self) -> None:
        self.assertTrue(sm.schalter_an({}, "update_emulators"))
        self.assertFalse(sm.schalter_an({}, "update_emulators", vorgabe=False))
        self.assertTrue(sm.schalter_an({"update_emulators": "  "}, "update_emulators"))
        for aus in ("0", "false", "No", " OFF "):
            with self.subTest(wert=aus):
                self.assertFalse(sm.schalter_an({"x": aus}, "x"))
        for an in ("1", "true", "yes", "on"):
            with self.subTest(wert=an):
                self.assertTrue(sm.schalter_an({"x": an}, "x", vorgabe=False))

    def test_ablage_neue_fassung(self) -> None:
        fall = sm.aufnahme_ablage
        e, g = sm.VERDRAENGT_EMUS, sm.VERDRAENGT_GLOBAL
        # (Backport-Unterordner, Spiel-Unterordner) -> (Ort, Ordner, anlegen, verdraengbar)
        erwartungen = [
            (((), ()), (sm.ORT_SPIEL, ("fakelib",), "fakelib", (e, g))),
            (((), ("fakelib",)), (sm.ORT_SPIEL, ("fakelib",), "", (e, g))),
            (((), ("fakelib2",)), (sm.ORT_SPIEL, ("fakelib2",), "", ())),
            (((), ("fakelib", "fakelib2")), (sm.ORT_SPIEL, ("fakelib2", "fakelib"), "", (e, g))),
            ((("fakelib2",), ("fakelib",)), (sm.ORT_BACKPORT, ("fakelib2",), "", ())),
            ((("fakelib",), ("fakelib2",)), (sm.ORT_BACKPORT, ("fakelib",), "", (e, g))),
            ((("fakelib", "fakelib2"), ()), (sm.ORT_BACKPORT, ("fakelib2",), "", ())),
        ]
        for generation in (sm.NEU, ""):
            for (bp, sp), (ort, ordner, anlegen, verdraengbar) in erwartungen:
                with self.subTest(generation=generation, backport=bp, spiel=sp):
                    ergebnis = fall(generation, backport=bp, spiel=sp)
                    self.assertEqual(ort, ergebnis["ort"])
                    self.assertEqual(ordner, ergebnis["ordner"])
                    self.assertEqual(anlegen, ergebnis["anlegen"])
                    self.assertEqual(verdraengbar, ergebnis["verdraengbar"])

    def test_ablage_alte_fassung(self) -> None:
        """Bis alpha6: Backport nur als fakelib2, im Spiel fakelib2 vor fakelib,
        keine Emulator-Dateien - die globale fakelib liegt als Schicht darueber."""
        g = (sm.VERDRAENGT_GLOBAL,)
        nur_fakelib_im_backport = sm.aufnahme_ablage(sm.ALT, backport=("fakelib",),
                                                     spiel=("fakelib",))
        self.assertEqual((sm.ORT_SPIEL, ("fakelib",), g),
                         (nur_fakelib_im_backport["ort"], nur_fakelib_im_backport["ordner"],
                          nur_fakelib_im_backport["verdraengbar"]))
        beide = sm.aufnahme_ablage(sm.ALT, spiel=("fakelib", "fakelib2"))
        self.assertEqual(("fakelib2",), beide["ordner"])
        leer = sm.aufnahme_ablage(sm.ALT)
        self.assertEqual(("fakelib2", "fakelib2", g),
                         (leer["ordner"][0], leer["anlegen"], leer["verdraengbar"]))
        self.assertEqual(sm.ORT_BACKPORT,
                         sm.aufnahme_ablage(sm.ALT, backport=("fakelib2",))["ort"])

    def test_ordnernamen_ohne_ruecksicht_auf_schreibung(self) -> None:
        self.assertEqual(("fakelib2",),
                         sm.aufnahme_ablage(sm.NEU, spiel=("FakeLib2",))["ordner"])

    def test_gefahren(self) -> None:
        e, g = sm.VERDRAENGT_EMUS, sm.VERDRAENGT_GLOBAL

        def arten(generation=sm.NEU, werte=None, **k):
            return [x["art"] for x in sm.aufnahme_gefahren(
                generation, werte or {}, **k)]

        self.assertEqual([], arten())
        # Emulator-Datei bei Vorgabe update_emulators=1 - aber nur, wo sie greift.
        self.assertEqual([e], arten(verdraengbar=(e, g), emus_hat_ampr=True))
        self.assertEqual([], arten(verdraengbar=(), emus_hat_ampr=True))
        self.assertEqual([], arten(werte={"update_emulators": "0"},
                                   verdraengbar=(e, g), emus_hat_ampr=True))
        self.assertEqual([], arten(sm.ALT, verdraengbar=(e, g), emus_hat_ampr=True))
        # Globale fakelib nur mit priority=global, an, nicht ausgenommen.
        global_an = {"global_fakelib_priority": "global"}
        self.assertEqual([g], arten(werte=global_an, verdraengbar=(g,), global_hat_ampr=True))
        self.assertEqual([], arten(werte=global_an, verdraengbar=(g,), global_hat_ampr=True,
                                   titel_ausgeschlossen=True))
        self.assertEqual([], arten(verdraengbar=(g,), global_hat_ampr=True))
        self.assertEqual([], arten(werte=dict(global_an, global_fakelib="off"),
                                   verdraengbar=(g,), global_hat_ampr=True))
        # Hauptschalter - unabhaengig vom Ordner.
        self.assertEqual(["aus"], arten(werte={"backport_fakelib": "0"}))
        alles = arten(werte=dict(global_an, backport_fakelib="no"),
                      verdraengbar=(e, g), emus_hat_ampr=True, global_hat_ampr=True)
        self.assertEqual(["aus", e, g], alles)

    def test_abhilfen(self) -> None:
        abhilfe = {x["art"]: (x["schluessel"], x["vorlaeufig"]) for x in sm.aufnahme_gefahren(
            sm.NEU, {"backport_fakelib": "0", "global_fakelib_priority": "global"},
            verdraengbar=(sm.VERDRAENGT_EMUS, sm.VERDRAENGT_GLOBAL),
            emus_hat_ampr=True, global_hat_ampr=True)}
        self.assertEqual({"aus": ("backport_fakelib", "1"),
                          "emus": ("update_emulators", "0"),
                          "global": ("global_fakelib_priority", "game")}, abhilfe)


class _KonsolenTest(unittest.TestCase):
    """Ein Testordner als Konsole, dahinter eine echte FTP-Stube."""

    SIZE_KAPUTT = False

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="mitschnitt_sm_")
        self.basis = Path(self._tmp.name)
        self.konsole = self.basis / "konsole"
        self.spiel = self.konsole / SPIEL.lstrip("/")
        (self.spiel / "sce_sys").mkdir(parents=True)
        (self.spiel / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 64)
        (self.spiel / "sce_sys" / "param.json").write_text(
            '{"titleId": "%s"}' % TITEL, encoding="utf-8")
        self.stube = _FtpStube(self.konsole, size_kaputt=self.SIZE_KAPUTT)
        self.addCleanup(self.stube.schliessen)
        self.addCleanup(self._tmp.cleanup)

        self.dump = self.basis / "dump"
        self.dump.mkdir()
        (self.dump / "ampr_emu.index").write_bytes(b"NEUER-INDEX")
        self.debug = self.basis / "libSceAmpr_debug.sprx"
        self.debug.write_bytes(b"DEBUG-BAU")

        self.app = _pruefling(self)
        self.app._ps5_ftp_port = lambda: self.stube.port
        self.ftp = self.app._ampr_ftp_connect("127.0.0.1", self.stube.port)
        self.addCleanup(self._schliessen)
        self.rueckweg = {"config": None, "dateien": [],
                         "sicherung": str(self.basis / "vorher")}
        self.zeilen: list[str] = []

    def _schliessen(self) -> None:
        try:
            self.ftp.quit()
        except Exception:  # noqa: BLE001
            pass

    # -- Hilfen -------------------------------------------------------

    def _ablegen(self, fern: str, inhalt: "bytes | str") -> Path:
        pfad = self.konsole / fern.lstrip("/")
        pfad.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(inhalt, str):
            pfad.write_bytes(inhalt.encode("utf-8"))
        else:
            pfad.write_bytes(inhalt)
        return pfad

    def _lesen(self, fern: str) -> bytes:
        return (self.konsole / fern.lstrip("/")).read_bytes()

    def _da(self, fern: str) -> bool:
        return (self.konsole / fern.lstrip("/")).exists()

    def _pruefen(self, antwort: "str | None" = None):
        if antwort is not None:
            self.app._ampr_gen_frage = mock.Mock(return_value=antwort)
        spiel = {"pfad": SPIEL, "title_id": TITEL, "scanpath": "/data/homebrew",
                 "quelle": "Ordner"}
        return self.app._ampr_mitschnitt_shadowmount_pruefen(
            None, self.ftp, spiel, TITEL, self.rueckweg, self.zeilen.append)

    def _hochladen(self, ziele) -> bool:
        return self.app._ampr_mitschnitt_upload_vorbereiten(
            self.ftp, SPIEL, str(self.dump), {"path": str(self.debug)},
            self.zeilen.append, ziele=ziele, rueckweg=self.rueckweg)

    def _zurueck(self) -> bool:
        return self.app._ampr_mitschnitt_zurueckstellen(
            "127.0.0.1", self.rueckweg, self.zeilen.append)


class AblaufTests(_KonsolenTest):

    def test_emulator_datei_wird_vorruebergehend_abgeschaltet(self) -> None:
        """Der Fall aus der Anwenderfrage - und am Ende alles wie vorher."""
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        self._ablegen(SPIEL + "/fakelib/libSceAmpr.sprx", b"ORIGINAL")
        self._ablegen(SPIEL + "/ampr_emu.index", b"ALTER-INDEX")
        vorher_config = self._lesen(CONFIG)

        ziele = self._pruefen("umstellen")
        self.assertEqual([SPIEL + "/fakelib"], ziele)
        frage = self.app._ampr_gen_frage.call_args.args
        self.assertIn(EMUS, frage[2])
        self.assertIn("update_emulators", frage[2])
        self.assertIn("update_emulators=0", self._lesen(CONFIG).decode("utf-8"))
        self.assertTrue(Path(self.rueckweg["sicherung"], "shadowmount_config.ini").is_file())

        self.assertTrue(self._hochladen(ziele), "\n".join(self.zeilen))
        self.assertEqual(b"DEBUG-BAU", self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx"))
        self.assertEqual(b"NEUER-INDEX", self._lesen(SPIEL + "/ampr_emu.index"))

        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertEqual(b"ORIGINAL", self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx"))
        self.assertEqual(b"ALTER-INDEX", self._lesen(SPIEL + "/ampr_emu.index"))
        self.assertEqual(vorher_config, self._lesen(CONFIG),
                         "Die config.ini ist nicht Byte fuer Byte zurueck.")
        self.assertIn(_text("amprmitschnitt.restore_done") + "\n", self.app._log_lines,
                      "Das Ergebnis gehoert auch ins Hauptprotokoll.")

    def test_backport_ordner_aus_aufgabe_7_geht_vor(self) -> None:
        """Dort sucht ShadowMount+ zuerst; ein fakelib2 wird allein eingehaengt,
        die Emulator-Datei stoert dann nicht - keine Frage."""
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        backport = "/data/homebrew/backports/%s/fakelib2" % TITEL
        self._ablegen(backport + "/libSceAmpr.sprx", b"RELEASE-AUFGABE7")

        ziele = self._pruefen()
        self.assertEqual([backport], ziele)
        self.assertIn(_text("amprmitschnitt.sm_ok"), self.zeilen)
        self.assertNotIn("update_emulators=0", self._lesen(CONFIG).decode("utf-8"))

        self.assertTrue(self._hochladen(ziele), "\n".join(self.zeilen))
        self.assertEqual(b"DEBUG-BAU", self._lesen(backport + "/libSceAmpr.sprx"))
        self.assertFalse(self._da(SPIEL + "/fakelib"),
                         "Der Spielordner wird nicht angefasst, wenn ein Backport gewinnt.")
        self.assertTrue(self._zurueck())
        self.assertEqual(b"RELEASE-AUFGABE7", self._lesen(backport + "/libSceAmpr.sprx"))

    def test_backport_ordner_in_einem_anderen_scanpfad(self) -> None:
        """Ein Backport wirkt aus jedem Scan-Pfad - auch ohne Eintrag in der config."""
        self._ablegen(CONFIG, VORLAGE.replace("scanpath=/data/homebrew\r\n", ""))
        backport = "/data/etaHEN/games/backports/%s/fakelib" % TITEL
        self._ablegen(backport + "/libSceAmpr.sprx", b"X")
        self.assertEqual([backport], self._pruefen())

    def test_data_homebrew_bleibt_rueckfall_fuer_backports(self) -> None:
        """Ab 1.7beta3 sucht ShadowMount+ zuletzt immer in /data/homebrew -
        auch wenn eigene scanpath-Eintraege ihn auslassen
        (get_backport_scan_path in sm_config_mount.c, Commit f0d15ffc)."""
        config = VORLAGE.replace("scanpath=/data/homebrew\r\n", "scanpath=/mnt/usb0\r\n")
        self.assertIn("scanpath=/mnt/usb0", config)
        spiel = {"pfad": "/mnt/usb0/GAME", "title_id": TITEL, "scanpath": "/mnt/usb0",
                 "quelle": "Ordner"}
        rueckfall = "/data/homebrew/backports/%s" % TITEL
        self._ablegen(rueckfall + "/fakelib2/libSceAmpr.sprx", b"X")
        ordner, da = self.app._ampr_mitschnitt_backport_finden(self.ftp, spiel, TITEL, config)
        self.assertEqual(rueckfall, ordner)
        self.assertIn("fakelib2", da)
        # Der eigene Suchpfad des Spiels geht dem Rueckfall vor.
        eigener = "/mnt/usb0/backports/%s" % TITEL
        self._ablegen(eigener + "/fakelib/libSceRtc.sprx", b"R")
        self.assertEqual(eigener, self.app._ampr_mitschnitt_backport_finden(
            self.ftp, spiel, TITEL, config)[0])

    def test_neu_angelegter_ordner_wird_stillgelegt(self) -> None:
        """Den fakelib-Ordner gab es vorher nicht: Er wird am Ende umbenannt.

        ShadowMount+ wertet schon einen leeren Ordner aus (1.7beta2,
        ``resolve_game_fakelib_source_for_path``: ``stat`` + ``S_ISDIR``).
        Bliebe er mit der stillgelegten Bibliothek darin stehen, bekaeme das
        Spiel danach die zusammengesetzte fakelib samt Emulator-Dateien -
        vorher nur die globale. Bis zum 01.10.2026 blieb er stehen.
        """
        self._ablegen(CONFIG, VORLAGE)
        ziele = self._pruefen()
        self.assertEqual([SPIEL + "/fakelib"], ziele)
        self.assertTrue(self._hochladen(ziele))
        self.assertEqual(b"DEBUG-BAU", self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx"))
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertFalse(self._da(SPIEL + "/fakelib"), "Der neue Ordner steht noch.")
        self.assertEqual(b"DEBUG-BAU",
                         self._lesen(SPIEL + "/fakelib.mitschnitt/libSceAmpr.sprx"),
                         "Umbenannt, nicht geloescht.")
        self.assertIn(_text("amprmitschnitt.restore_ordner_still", path=SPIEL + "/fakelib",
                            name="fakelib.mitschnitt"), self.zeilen)
        self.assertEqual(b"NEUER-INDEX", self._lesen(SPIEL + "/ampr_emu.index"),
                         "Ohne vorherigen Index bleibt der neue liegen.")

    def test_vorhandener_ordner_ohne_bibliothek_bleibt(self) -> None:
        """Wo der Ordner schon da war, wird nur die Bibliothek stillgelegt."""
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(SPIEL + "/fakelib/libSceRtc.sprx", b"RTC")
        ziele = self._pruefen()
        self.assertTrue(self._hochladen(ziele))
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertEqual(b"RTC", self._lesen(SPIEL + "/fakelib/libSceRtc.sprx"))
        self.assertFalse(self._da(SPIEL + "/fakelib/libSceAmpr.sprx"))
        self.assertEqual(b"DEBUG-BAU",
                         self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx.mitschnitt"))

    def test_frueher_stillgelegtes_bleibt_stehen(self) -> None:
        """Ein zweiter Lauf ueberschreibt nichts aus dem ersten - Datei wie Ordner."""
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(SPIEL + "/fakelib/libSceRtc.sprx", b"RTC")
        self._ablegen(SPIEL + "/fakelib/libSceAmpr.sprx.mitschnitt", b"ERSTER-LAUF")
        self.assertTrue(self._hochladen([SPIEL + "/fakelib"]))
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertEqual(b"ERSTER-LAUF",
                         self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx.mitschnitt"))
        self.assertEqual(b"DEBUG-BAU",
                         self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx.mitschnitt2"))

        self.rueckweg["dateien"].clear()
        self._ablegen(SPIEL + "/fakelib2.mitschnitt/libSceAmpr.sprx", b"ERSTER-ORDNER")
        self.assertTrue(self._hochladen([SPIEL + "/fakelib2"]))
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertFalse(self._da(SPIEL + "/fakelib2"))
        self.assertEqual(b"ERSTER-ORDNER",
                         self._lesen(SPIEL + "/fakelib2.mitschnitt/libSceAmpr.sprx"))
        self.assertEqual(b"DEBUG-BAU",
                         self._lesen(SPIEL + "/fakelib2.mitschnitt2/libSceAmpr.sprx"))

    def test_neuer_ordner_mit_fremdem_inhalt_bleibt(self) -> None:
        """Legt waehrenddessen jemand etwas hinein, wird der Ordner gebraucht."""
        self._ablegen(CONFIG, VORLAGE)
        self.assertTrue(self._hochladen([SPIEL + "/fakelib"]))
        self._ablegen(SPIEL + "/fakelib/libSceRtc.sprx", b"RTC")
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertEqual(b"RTC", self._lesen(SPIEL + "/fakelib/libSceRtc.sprx"))
        self.assertFalse(self._da(SPIEL + "/fakelib/libSceAmpr.sprx"))
        self.assertEqual(b"DEBUG-BAU",
                         self._lesen(SPIEL + "/fakelib/libSceAmpr.sprx.mitschnitt"))
        self.assertIn(_text("amprmitschnitt.restore_ordner_bleibt", path=SPIEL + "/fakelib",
                            names="libSceRtc.sprx"), self.zeilen)

    def test_nie_angelegter_ordner_ist_kein_auftrag(self) -> None:
        """Scheitert das Hochladen vor dem Anlegen, bleibt nichts zu tun."""
        self._ablegen(CONFIG, VORLAGE)
        self.app._ampr_ftp_upload_file = mock.Mock(return_value=False)
        self.assertFalse(self._hochladen([SPIEL + "/fakelib"]))
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        self.assertFalse(self._da(SPIEL + "/fakelib"))
        self.assertFalse(self._da(SPIEL + "/fakelib.mitschnitt"))

    def test_ordner_fehlt_nur_nachweislich(self) -> None:
        """Nur eine gelungene Auflistung zaehlt - sonst wuerde am Ende ein
        Ordner umbenannt, den es vorher schon gab."""
        self._ablegen(SPIEL + "/fakelib2/libSceAmpr.sprx", b"X")
        fehlt = self.app._ampr_mitschnitt_ordner_fehlt
        self.assertTrue(fehlt(self.ftp, SPIEL + "/fakelib"))
        self.assertFalse(fehlt(self.ftp, SPIEL + "/fakelib2"))
        self.assertFalse(fehlt(self.ftp, "/gibt/es/nicht/fakelib"),
                         "Ordner darueber nicht lesbar: unbekannt, nicht 'fehlt'.")
        tot = self.app._ampr_ftp_connect("127.0.0.1", self.stube.port)
        tot.close()
        self.assertFalse(fehlt(tot, SPIEL + "/fakelib"), "Tote Verbindung: unbekannt.")
        self.assertTrue(self._hochladen([SPIEL + "/fakelib2"]))
        self.assertEqual([False], [e.get("ordner_neu", False)
                                   for e in self.rueckweg["dateien"]])

    def test_fakelib_und_fakelib2_bekommen_beide_die_aufnahme(self) -> None:
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(SPIEL + "/fakelib/libSceRtc.sprx", b"RTC")
        self._ablegen(SPIEL + "/fakelib2/libSceAmpr.sprx", b"ORIGINAL2")
        ziele = self._pruefen()
        self.assertEqual([SPIEL + "/fakelib2", SPIEL + "/fakelib"], ziele)
        self.assertIn(_text("amprmitschnitt.sm_beide"), self.zeilen)
        self.assertTrue(self._hochladen(ziele))
        for ordner in ("fakelib", "fakelib2"):
            with self.subTest(ordner=ordner):
                self.assertEqual(b"DEBUG-BAU",
                                 self._lesen(SPIEL + "/%s/libSceAmpr.sprx" % ordner))
        self.assertTrue(self._zurueck())
        self.assertEqual(b"ORIGINAL2", self._lesen(SPIEL + "/fakelib2/libSceAmpr.sprx"))
        self.assertFalse(self._da(SPIEL + "/fakelib/libSceAmpr.sprx"))

    def test_nicht_umstellen_laesst_alles_stehen(self) -> None:
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        vorher = self._lesen(CONFIG)
        self.assertEqual([SPIEL + "/fakelib"], self._pruefen("lassen"))
        self.assertEqual(vorher, self._lesen(CONFIG))
        self.assertIsNone(self.rueckweg["config"])
        self.assertIn(_text("amprmitschnitt.sm_kept"), self.zeilen)

    def test_abbrechen_aendert_nichts(self) -> None:
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        vorher = self._lesen(CONFIG)
        for antwort in ("stop", ""):
            with self.subTest(antwort=antwort):
                self.assertIsNone(self._pruefen(antwort))
                self.assertEqual(vorher, self._lesen(CONFIG))
                self.assertIsNone(self.rueckweg["config"])

    def test_globale_fakelib_mit_vorrang(self) -> None:
        self._ablegen(CONFIG, VORLAGE + "global_fakelib_priority=global\r\n")
        self._ablegen(GLOBAL + "/libSceAmpr.sprx", b"GLOBAL")
        self.assertEqual([SPIEL + "/fakelib"], self._pruefen("umstellen"))
        self.assertIn(GLOBAL, self.app._ampr_gen_frage.call_args.args[2])
        text = self._lesen(CONFIG).decode("utf-8")
        self.assertIn("global_fakelib_priority=game", text)
        self.assertNotIn("global_fakelib_priority=global", text)
        self.assertTrue(self._zurueck())
        self.assertIn("global_fakelib_priority=global", self._lesen(CONFIG).decode("utf-8"))

    def test_ausgenommener_titel_fragt_nicht(self) -> None:
        self._ablegen(CONFIG, VORLAGE + "global_fakelib_priority=global\r\n"
                      "global_fakelib_exclude=CUSA00001\r\n"
                      "global_fakelib_exclude=%s\r\n" % TITEL)
        self._ablegen(GLOBAL + "/libSceAmpr.sprx", b"GLOBAL")
        self.assertEqual([SPIEL + "/fakelib"], self._pruefen())
        self.assertIn(_text("amprmitschnitt.sm_ok"), self.zeilen)

    def test_hauptschalter_aus(self) -> None:
        self._ablegen(CONFIG, VORLAGE + "backport_fakelib=0\r\n")
        self._pruefen("umstellen")
        self.assertIn(_text("amprmitschnitt.sm_grund_aus"),
                      self.app._ampr_gen_frage.call_args.args[2])
        self.assertIn("backport_fakelib=1", self._lesen(CONFIG).decode("utf-8"))
        self.assertTrue(self._zurueck())
        self.assertIn("backport_fakelib=0", self._lesen(CONFIG).decode("utf-8"))

    def test_zwischendurch_geaenderte_config_behaelt_fremde_aenderung(self) -> None:
        """Nur die eigenen Schluessel zuruecksetzen, wenn die Datei sich bewegt hat."""
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        self._pruefen("umstellen")
        pfad = self.konsole / CONFIG.lstrip("/")
        pfad.write_bytes(pfad.read_bytes() + b"kstuff_delay=5\r\n")
        self.assertTrue(self._zurueck(), "\n".join(self.zeilen))
        werte = APP.parse_flat_ini(self._lesen(CONFIG).decode("utf-8"))
        self.assertNotIn("update_emulators", werte, "Der eigene Schluessel ist nicht weg.")
        self.assertEqual("5", werte.get("kstuff_delay"), "Fremde Aenderung verloren.")
        self.assertEqual("/data/homebrew", werte.get("scanpath"))

    def test_ohne_config_gelten_die_vorgaben(self) -> None:
        """Keine config.ini: update_emulators steht auf der Vorgabe 1."""
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        self._pruefen("lassen")
        self.assertIn(_text("amprmitschnitt.sm_config_fehlt"), self.zeilen)
        self.app._ampr_gen_frage.assert_called_once()


class OhneSizeTests(_KonsolenTest):
    """Ein Server, der SIZE nicht kennt (502), ist kein "Datei fehlt"."""

    SIZE_KAPUTT = True

    def test_datei_wird_ueber_die_auflistung_gefunden(self) -> None:
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        self.assertTrue(self.app._ampr_mitschnitt_datei_da(self.ftp, EMUS + "/libSceAmpr.sprx"))
        self.assertFalse(self.app._ampr_mitschnitt_datei_da(self.ftp, EMUS + "/fehlt.sprx"))


class ZurueckstellenTests(_KonsolenTest):

    def test_ohne_verbindung_steht_im_hauptprotokoll_was_zu_tun_ist(self) -> None:
        self._ablegen(CONFIG, VORLAGE)
        self._ablegen(EMUS + "/libSceAmpr.sprx", b"RELEASE-EMUS")
        # Ein vorhandenes fakelib (zusammengesetzt - die Emulator-Datei
        # verdraengt) und ein neues fakelib2: je eine Sorte Auftrag.
        self._ablegen(SPIEL + "/fakelib/libSceAmpr.sprx", b"ORIGINAL")
        self.assertEqual([SPIEL + "/fakelib"], self._pruefen("umstellen"))
        self.assertTrue(self._hochladen([SPIEL + "/fakelib", SPIEL + "/fakelib2"]))
        self.stube.schliessen()
        self.app._ps5_ftp_port = lambda: 1          # dort horcht niemand
        self.assertFalse(self._zurueck())
        protokoll = "".join(self.app._log_lines)
        self.assertIn("(3/3)", protokoll)
        # In der VORLAGE steht update_emulators nur auskommentiert.
        self.assertIn(_text("amprmitschnitt.restore_todo_entfernen", config=CONFIG,
                            schluessel="update_emulators"), protokoll)
        self.assertIn(_text("amprmitschnitt.restore_todo_lib",
                            path=SPIEL + "/fakelib/libSceAmpr.sprx"), protokoll)
        self.assertIn(_text("amprmitschnitt.restore_todo_ordner",
                            path=SPIEL + "/fakelib2"), protokoll)
        self.assertIn(self.rueckweg["sicherung"], protokoll)

    def test_nichts_zu_tun_heisst_keine_verbindung(self) -> None:
        anmeldungen = self.stube.anmeldungen
        self.assertTrue(self._zurueck())
        self.assertEqual(anmeldungen, self.stube.anmeldungen)
        self.assertEqual([], self.zeilen)


class AbholungTests(_KonsolenTest):
    """Je Versuch eine frische Verbindung - die vom Anfang ist nach einer
    Spielrunde bei ftpsrv laengst weg."""

    def test_zweiter_versuch_mit_neuer_verbindung(self) -> None:
        for name, inhalt in (("ampr_commands.bin", b"C" * 2048),
                             ("ampr_emu.index", b"I"), ("ampr_emu.log", b"L")):
            self._ablegen(SPIEL + "/" + name, inhalt)
        versuche = []

        def _verbinden():
            versuche.append(1)
            if len(versuche) == 1:
                raise OSError("Verbindung weg")
            return self.app._ampr_ftp_connect("127.0.0.1", self.stube.port)

        self.app._ampr_gen_frage = mock.Mock(return_value="retry")
        ordner = self.basis / "lauf_01"
        ergebnis = self.app._ampr_mitschnitt_lauf_herunterladen(
            None, _verbinden, SPIEL, str(ordner), "Test", self.zeilen.append)
        self.assertEqual("ok", ergebnis)
        self.assertEqual(2, len(versuche))
        self.assertEqual(b"C" * 2048, (ordner / "ampr_commands.bin").read_bytes())
        self.assertIn("Verbindung weg", self.app._ampr_gen_frage.call_args.args[2])


class VerdrahtungTests(unittest.TestCase):
    """Was am Syntaxbaum zu sehen ist."""

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        cls.methoden = {k.name: k for k in ast.walk(baum)
                        if isinstance(k, ast.FunctionDef)}

    def test_zurueckstellen_steht_im_finally(self) -> None:
        automatik = self.methoden["_ampr_mitschnitt_automatik"]
        versuch = next(k for k in automatik.body if isinstance(k, ast.Try))
        aufrufe = [k for teil in versuch.finalbody for k in ast.walk(teil)
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_ampr_mitschnitt_zurueckstellen"]
        self.assertTrue(aufrufe, "Ohne finally bliebe die Konsole nach Abbruch umgestellt.")

    def test_pruefung_kommt_vor_dem_hochladen(self) -> None:
        automatik = self.methoden["_ampr_mitschnitt_automatik"]
        zeilen = {}
        for knoten in ast.walk(automatik):
            if isinstance(knoten, ast.Call) and getattr(knoten.func, "attr", "") in (
                    "_ampr_mitschnitt_shadowmount_pruefen",
                    "_ampr_mitschnitt_upload_vorbereiten"):
                zeilen[knoten.func.attr] = knoten.lineno
        self.assertLess(zeilen["_ampr_mitschnitt_shadowmount_pruefen"],
                        zeilen["_ampr_mitschnitt_upload_vorbereiten"])

    def test_texte_zweisprachig_und_schritte_zaehlen_bis_sieben(self) -> None:
        for schluessel in [k for k in STRINGS if k.startswith("amprmitschnitt.")]:
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))
        for nummer, schritt in enumerate(("dump", "console", "match", "shadowmount",
                                          "prepare", "segments", "profile"), start=1):
            for sprache in ("de", "en"):
                with self.subTest(schritt=schritt, sprache=sprache):
                    self.assertTrue(STRINGS["amprmitschnitt.step_" + schritt][sprache]
                                    .startswith("[%d/7]" % nummer))

    def test_jeder_grund_hat_einen_text(self) -> None:
        for art, schluessel in PS5ConverterGUI._AMPR_MITSCHNITT_GRUENDE.items():
            with self.subTest(art=art):
                self.assertIn(schluessel, STRINGS)

    def test_kein_platzhalter_heisst_key(self) -> None:
        """``_t(self, key, **werte)``: Ein Platzhalter ``key=`` wirft TypeError.

        Beim Bau dieses Wegs gefunden (restore_todo_*), danach im ganzen
        Hauptmodul gesucht: ``amprgen.place_key_off`` in Aufgabe 7 warf
        genau so, sobald ein Ablage-Schalter auf "aus" stand.
        """
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        funde = [knoten.lineno for knoten in ast.walk(baum)
                 if isinstance(knoten, ast.Call)
                 and getattr(knoten.func, "attr", "") == "_t"
                 and any(k.arg == "key" for k in knoten.keywords)]
        self.assertEqual([], funde)
        vorlagen = [s for s, texte in STRINGS.items()
                    if any("{key}" in str(t) for t in texte.values())]
        self.assertEqual([], vorlagen, "Ein Text erwartet {key} - das liesse sich "
                                       "ueber _t nie fuellen.")
        app = _pruefling(self)
        self.assertIn("update_emulators", app._t("amprgen.place_key_off",
                                                 schluessel="update_emulators"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
