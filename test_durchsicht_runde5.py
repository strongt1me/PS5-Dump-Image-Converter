# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 5 (24.09.2026).

* **H5-12** - Der Herunterfahr-Countdown zaehlte zu Ende, obwohl inzwischen
  neue Arbeit lief (Aufgabe, PKG-Merger, Uebertragung zur Konsole).
* **H10-2** - Die AMPR-EMU-Automatik legte die Bibliotheken eines Spiels, das
  die Konsole nur aus appmeta kennt, in deren Systembereich.
* **H3-7** - Das Aufraeumen beim Start haengte auch fremde Laufwerke aus, die
  den Buchstaben eines frueheren Abbilds geerbt hatten.
* **U2-1** - Eine abgebrochene Uebernahme liess einen halben Asset-Satz im
  Spielordner.
* **U2-3** - Ein eigener fakelib-/Emulator-Ordner galt als Abweichung.
* **U2-4** - Ein verschluesselter SELF zaehlte beim BACKPORT als
  "uebersprungen" statt als Fehler.
* **U3-5/U3-14** - Beim Payload-Versand galt die Zeitgrenze fuer den ganzen
  Versand; ``app_install`` verwarf sie ganz.
* **U3-7** - Der SDK-Bau hatte fest zwei Stunden.
* **U3-8** - Der Selbsttest eigener Bibliotheken suchte unter Linux und macOS
  ``prosperopkg.exe``.
* **H2-1/H5-15** - Der 5-s-Checkpoint ueberschrieb die Fortsetzungsstufe.

U2-2 steht in ``test_shadowmount_generation``, U3-4, U3-6 und H3-9 in
``test_konsole_stufe4``.
"""
from __future__ import annotations

import ast
import collections
import os
import socket
import struct
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde5")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ampr_assetpakete as ap      # noqa: E402
from ps5_validator.utils import app_install as ai           # noqa: E402
from ps5_validator.utils import eigene_bibliotheken as eb   # noqa: E402
from ps5_validator.utils import payload_versand as pv       # noqa: E402
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils import shadowmount_generation as sg  # noqa: E402


class _Attrappe:
    def __getattr__(self, _name):
        return lambda *a, **k: None


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.is_running = False
    gui.root = mock.Mock()
    gui.status_label = mock.Mock()
    gui.progress_engine = _Attrappe()
    return gui


_BAUM: list = []


def _methode(name: str) -> ast.FunctionDef:
    """Eine Methode des Hauptprogramms als Syntaxbaum."""
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return next(k for k in ast.walk(_BAUM[0])
                if isinstance(k, ast.FunctionDef) and k.name == name)


class HerunterfahrenTests(unittest.TestCase):
    """H5-12: Neue Arbeit haelt das Herunterfahren an."""

    def _bereit(self):
        gui = _gui()
        gui._shutdown_after_success_cli = True
        gui._last_task_ok = True
        gui._shutdown_pending = False
        return gui

    def test_merger_und_uebertragung_zaehlen_als_arbeit(self) -> None:
        for merkmal in ("_pkg_merge_laeuft", "_bibliothek_uebertragungen"):
            with self.subTest(merkmal=merkmal):
                gui = self._bereit()
                self.assertTrue(gui._should_shutdown_after_task())
                setattr(gui, merkmal, 1)
                self.assertTrue(gui._arbeit_laeuft())
                self.assertFalse(gui._should_shutdown_after_task())

    def test_neue_arbeit_haelt_den_countdown_an(self) -> None:
        """Bis zum 24.09.2026 zaehlte er zu Ende - mitten in die neue Arbeit."""
        gui = self._bereit()
        gui._COLORS = collections.defaultdict(lambda: "#000000")
        gui._build_modern_toplevel = mock.MagicMock()
        gui._run_shutdown_sequence = mock.MagicMock()
        with mock.patch.object(APP.tk, "Label", mock.MagicMock()), \
                mock.patch.object(APP, "flach_knopf", mock.MagicMock()):
            gui._start_shutdown_countdown()
            # Der erste Takt lief sofort und hat den naechsten bestellt.
            naechster = gui.root.after.call_args[0][1]
            gui._pkg_merge_laeuft = 1
            naechster()
        self.assertTrue(gui._shutdown_aborted)
        self.assertFalse(gui._shutdown_pending)
        gui._run_shutdown_sequence.assert_not_called()
        self.assertTrue(any(gui._t("shutdown.log_neue_arbeit") in zeile
                            for zeile in gui.protokoll))


class SystembereichTests(unittest.TestCase):
    """H10-2: Die Automatik schreibt nie in den Systembereich der Konsole."""

    def test_systembereiche_werden_erkannt(self) -> None:
        pruefe = APP.PS5ConverterGUI._ampr_gen_systembereich
        for pfad in ("/system_data/priv/appmeta/PPSA01234/fakelib",
                     "system_ex/app/PPSA01234", "//system/common/lib",
                     "/data/../system_data/x", "/preinst", "/system"):
            with self.subTest(pfad=pfad):
                self.assertTrue(pruefe(pfad))
        for pfad in ("/data/shadowmount/fakelib",
                     "/mnt/usb0/backports/PPSA01234/fakelib",
                     "/system_datax", "/mnt/ext0/system_ex", ""):
            with self.subTest(pfad=pfad):
                self.assertFalse(pruefe(pfad))

    def test_ein_appmeta_spiel_ohne_scanpfad_bekommt_nichts(self) -> None:
        gui = _gui()
        ftp = mock.MagicMock()
        gui._smgen_texte = lambda: None
        gui._ampr_gen_adresse_finden = lambda *_a: "10.0.0.5"
        gui._ampr_ftp_connect = lambda *_a: ftp
        gui._ps5_ftp_port = lambda: 2121
        gui._ampr_gen_config_lesen = lambda _ftp: ""
        gui._ampr_ftp_is_dir = lambda *_a: False
        gui._ampr_gen_log_lesen = lambda _ftp: ""
        gui._ampr_ablage_wahl = lambda: sg.ORT_BACKPORT
        gui._ampr_gen_spiele_finden = lambda _ftp: [{
            "pfad": "/system_data/priv/appmeta/PPSA01234", "title_id": "PPSA01234",
            "scanpath": "", "name": "Spiel", "quelle": "appmeta"}]
        gui._ampr_ftp_ensure_dir = mock.MagicMock(return_value=True)
        meldungen: list = []
        gui._ampr_gen_automatik(sg.NEU, None, meldungen.append)
        gui._ampr_ftp_ensure_dir.assert_not_called()
        ftp.storbinary.assert_not_called()
        erwartet = "!! " + gui._t("amprgen.no_scanpath", title_id="PPSA01234",
                                  pfade=", ".join(gui._AMPR_GEN_SCANPFADE))
        self.assertIn(erwartet, meldungen)

    def test_die_automatik_prueft_vor_dem_ersten_schreibzugriff(self) -> None:
        text = ast.unparse(_methode("_ampr_gen_automatik"))
        i_sperre = text.find("self._ampr_gen_systembereich(ziel['pfad'])")
        i_schreiben = text.find("self._ampr_ftp_ensure_dir(")
        self.assertGreater(i_sperre, 0, "Die letzte Sperre fehlt.")
        self.assertLess(i_sperre, i_schreiben)


class StartaufraeumenTests(unittest.TestCase):
    """H3-7: Beim Start nur OSFMounts eigener Befehl."""

    def _aushaengen(self, nur_osfmount: bool):
        gui = _gui()
        befehle: list = []

        def _lauf(befehl, **_k):
            befehle.append(list(befehl))
            return SimpleNamespace(returncode=1)          # OSFMount scheitert

        with mock.patch.object(APP.sys, "platform", "win32"), \
                mock.patch.object(APP.PS5ConverterGUI, "_volume_handles_freigeben") as frei, \
                mock.patch.object(APP.subprocess, "run", _lauf), \
                mock.patch.object(APP.time, "sleep"), \
                mock.patch.object(APP, "ctypes", mock.MagicMock()):
            gui._safe_dismount_drive("X", "osfmount.com", log=False, retries=1,
                                     nur_osfmount=nur_osfmount)
        return frei, befehle

    def test_nur_osfmount_fasst_fremde_laufwerke_nicht_an(self) -> None:
        frei, befehle = self._aushaengen(nur_osfmount=True)
        frei.assert_not_called()
        self.assertFalse([b for b in befehle if b and b[0] == "mountvol"])
        self.assertIn(["osfmount.com", "-d", "-m", "X:"], befehle)

    def test_ohne_die_sperre_bleibt_der_volle_weg(self) -> None:
        """Gegenrichtung: das eigene, aktive Abbild wird weiter ganz geloest."""
        frei, befehle = self._aushaengen(nur_osfmount=False)
        frei.assert_called_once_with("X")
        self.assertTrue([b for b in befehle if b and b[0] == "mountvol"])

    def test_das_startaufraeumen_setzt_die_sperre_ueberall(self) -> None:
        aufrufe = [k for k in ast.walk(_methode("_cleanup_stale_osfmounts"))
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_safe_dismount_drive"]
        self.assertEqual(3, len(aufrufe))
        for aufruf in aufrufe:
            with self.subTest(zeile=aufruf.lineno):
                werte = {kw.arg: kw.value for kw in aufruf.keywords}
                self.assertIn("nur_osfmount", werte)
                self.assertIs(True, getattr(werte["nur_osfmount"], "value", None))


class BestandUebernahmeTests(unittest.TestCase):
    """U2-1: alles oder nichts im Spielordner."""

    BAENDER = ["ampr_assets-t-lane00-vol00-000.pak",
               "ampr_assets-t-lane00-vol01-001.pak",
               "ampr_assets-t-lane00-vol02-002.pak"]

    def _vorbereiten(self, basis: str) -> tuple[Path, Path]:
        raus = Path(basis) / "raus"
        app0 = Path(basis) / "app0"
        raus.mkdir()
        app0.mkdir()
        for name in (ap.MANIFEST_NAME, ap.LAUFZEIT_NAME, ap.PRUEFSUMMEN_NAME,
                     *self.BAENDER):
            (raus / name).write_bytes(("neu:" + name).encode("ascii"))
        # Ein frueherer Satz liegt schon im Spiel.
        (app0 / ap.MANIFEST_NAME).write_bytes(b"alt")
        return raus, app0

    def test_ein_fehler_mittendrin_laesst_keinen_halben_satz(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde5_") as basis:
            raus, app0 = self._vorbereiten(basis)
            # Seit Runde 19 (U2-5) kopiert die Uebernahme blockweise und
            # abbrechbar - gestoert wird deshalb diese Kopie, nicht copy2.
            echt = ap._kopieren_mit_abbruch
            zaehler = {"n": 0}

            def _kopie(quelle, ziel, *a, **k):
                zaehler["n"] += 1
                if zaehler["n"] == 4:
                    # Mittendrin voll: ein halber Zwischenstand bleibt liegen.
                    Path(ziel).write_bytes(b"halb")
                    raise OSError(28, "No space left on device")
                return echt(quelle, ziel, *a, **k)

            with mock.patch.object(ap, "_kopieren_mit_abbruch", _kopie):
                with self.assertRaises(ap.PackFehler):
                    ap.bestand_uebernehmen(str(raus), str(app0), baender=self.BAENDER)
            self.assertEqual(4, zaehler["n"], "Die Stoerung traf gar nicht.")
            self.assertEqual([ap.MANIFEST_NAME], sorted(os.listdir(app0)))
            self.assertEqual(b"alt", (app0 / ap.MANIFEST_NAME).read_bytes())

    def test_ohne_fehler_kommt_der_ganze_satz(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde5_") as basis:
            raus, app0 = self._vorbereiten(basis)
            anzahl = ap.bestand_uebernehmen(str(raus), str(app0), baender=self.BAENDER)
            self.assertEqual(6, anzahl)
            namen = sorted(os.listdir(app0))
            self.assertEqual(sorted([ap.MANIFEST_NAME, ap.LAUFZEIT_NAME,
                                     ap.PRUEFSUMMEN_NAME, *self.BAENDER]), namen)
            self.assertEqual(("neu:" + ap.MANIFEST_NAME).encode("ascii"),
                             (app0 / ap.MANIFEST_NAME).read_bytes())


class EigenerPfadTests(unittest.TestCase):
    """U2-3: Ein eigener Ordner ist eine Wahl, keine Abweichung."""

    def test_eigene_ordner_sind_keine_abweichung(self) -> None:
        gui = _gui()
        text = ("global_fakelib_path=/mnt/usb0/fakelib\n"
                "emulators_path=/mnt/usb0/emus\n")
        for generation in (sg.ALT, sg.NEU):
            with self.subTest(generation=generation):
                self.assertEqual([], gui._ampr_gen_config_pruefen(generation, text))
        # Gegenrichtung: ein abgeschalteter Schalter bleibt eine Abweichung.
        abw = gui._ampr_gen_config_pruefen(sg.NEU, text + "backport_fakelib=0\n")
        self.assertEqual(["backport_fakelib"], [k for k, _i, _s in abw])

    def test_der_editor_setzt_eigene_ordner_nicht_zurueck(self) -> None:
        aussen = _methode("_show_ampr_generation")
        innen = next(k for k in ast.walk(aussen)
                     if isinstance(k, ast.FunctionDef) and k.name == "_config")
        text = ast.unparse(innen)
        self.assertIn("k not in sm_gen.PFAD_SCHLUESSEL", text)
        self.assertIn("vorrang_werte=fassungswerte", text)


class VerschluesseltesSelfTests(unittest.TestCase):
    """U2-4: Ein verschluesselter SELF ist ein Fehler, kein "nichts zu tun"."""

    @staticmethod
    def _self_ohne_sdk(verschluesselt: bool) -> bytes:
        from test_backport import baue_elf
        roh = bytearray(bp.elf_signieren(baue_elf(mit_param=False)))
        if verschluesselt:
            anzahl = struct.unpack_from("<H", roh, 0x18)[0]
            for index in range(anzahl):
                stelle = 0x20 * (1 + index)
                props = struct.unpack_from("<Q", roh, stelle)[0]
                if (props >> bp.PROPS_HAS_BLOCKS_SHIFT) & 0x1:
                    struct.pack_into("<Q", roh, stelle, props | bp.PROPS_VERSCHLUESSELT)
        return bytes(roh)

    def test_verschluesselt_ist_ein_fehler(self) -> None:
        ziel_ps5, ziel_ps4 = bp.sdk_paar(7)
        roh = self._self_ohne_sdk(verschluesselt=True)
        self.assertTrue(bp.self_segmente_verschluesselt(roh))
        kennung, neu, grund = bp.datei_verarbeiten(roh, ziel_ps5=ziel_ps5,
                                                   ziel_ps4=ziel_ps4)
        self.assertEqual(bp.ERG_FEHLER, kennung)
        self.assertEqual(roh, neu)
        self.assertEqual(bp.MELDUNGEN["self_verschluesselt"], grund)

    def test_unverschluesselt_bleibt_es_beim_ueberspringen(self) -> None:
        ziel_ps5, ziel_ps4 = bp.sdk_paar(7)
        roh = self._self_ohne_sdk(verschluesselt=False)
        self.assertFalse(bp.self_segmente_verschluesselt(roh))
        kennung, _neu, grund = bp.datei_verarbeiten(roh, ziel_ps5=ziel_ps5,
                                                    ziel_ps4=ziel_ps4)
        self.assertEqual(bp.ERG_UEBERSPRUNGEN, kennung)
        self.assertEqual(bp.MELDUNGEN["keine_sdk_angabe"], grund)

    def test_die_analyse_nennt_es_auch(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        self.assertIn('self._t("backport.row_self_encrypted")', quelle)
        self.assertIn("ps5_backport.self_segmente_verschluesselt(roh)", quelle)


class PayloadVersandTests(unittest.TestCase):
    """U3-5/U3-14: Die Zeitgrenze gilt je Stueck und kommt durch."""

    class _Buchse:
        def __init__(self) -> None:
            self.angeboten: list = []
            self.angekommen = bytearray()

        def send(self, daten) -> int:
            self.angeboten.append(len(daten))
            anzahl = min(len(daten), 40_000)          # nimmt nie alles auf einmal
            self.angekommen += bytes(daten[:anzahl])
            return anzahl

        def sendall(self, _daten) -> None:
            raise AssertionError("sendall: Zeitgrenze fuer den ganzen Versand")

    def test_gesendet_wird_stueckweise_und_vollstaendig(self) -> None:
        daten = bytes(range(256)) * 2000
        buchse = self._Buchse()
        pv.stueckweise_senden(buchse, daten)
        self.assertEqual(daten, bytes(buchse.angekommen))
        self.assertLessEqual(max(buchse.angeboten), pv.SENDESTUECK)

    def test_eine_stehende_leitung_faellt_auf(self) -> None:
        buchse = self._Buchse()
        buchse.send = lambda _daten: 0
        with self.assertRaises(ConnectionError):
            pv.stueckweise_senden(buchse, b"x" * 10)

    def test_ueber_elfldr_sendet_stueckweise(self) -> None:
        horcher = socket.socket()
        horcher.bind(("127.0.0.1", 0))
        horcher.listen(1)
        port = horcher.getsockname()[1]
        empfangen = bytearray()

        def _gegenstelle() -> None:
            verbindung, _ = horcher.accept()
            with verbindung:
                while True:
                    stueck = verbindung.recv(65536)
                    if not stueck:
                        break
                    empfangen.extend(stueck)
                verbindung.sendall(b"geladen\n")

        faden = threading.Thread(target=_gegenstelle, daemon=True)
        faden.start()
        daten = os.urandom(300_000)
        try:
            with mock.patch.object(pv, "stueckweise_senden",
                                   wraps=pv.stueckweise_senden) as gewickelt:
                antwort = pv.ueber_elfldr("127.0.0.1", daten, port=port, timeout=10.0)
        finally:
            faden.join(10)
            horcher.close()
        self.assertEqual("geladen", antwort)
        self.assertEqual(daten, bytes(empfangen))
        gewickelt.assert_called_once()

    def test_senden_reicht_die_zeitgrenze_durch(self) -> None:
        gefangen: dict = {}

        def _elfldr(*_a, **k):
            gefangen.update(k)
            return "ok"

        with mock.patch.object(pv, "port_offen", return_value=True), \
                mock.patch.object(pv, "ueber_elfldr", _elfldr):
            pv.senden("10.0.0.5", b"x", "a.elf", timeout=99.0)
        self.assertEqual(99.0, gefangen.get("timeout"))

    def test_app_install_verliert_die_zeitgrenze_nicht(self) -> None:
        gefangen: dict = {}

        def _senden(*_a, **k):
            gefangen.update(k)
            return "elfldr", "ausgabe", ""

        with mock.patch.object(ai.payload_versand, "senden", _senden):
            self.assertEqual("ausgabe", ai.payload_senden("10.0.0.5", b"x", timeout=77.0))
        self.assertEqual(77.0, gefangen.get("timeout"))

    def test_das_hauptprogramm_sendet_nirgends_mit_sendall(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        self.assertNotIn("s.sendall(data)", quelle)
        self.assertEqual(2, quelle.count("payload_versand.stueckweise_senden(s, data)"))


class SdkZeitgrenzeTests(unittest.TestCase):
    """U3-7: Der SDK-Bau bekommt dieselbe mitwachsende Grenze."""

    def test_der_sdk_bau_bekommt_die_mitwachsende_grenze(self) -> None:
        gui = _gui()
        gefangen: dict = {}

        def _bauen(*_a, **k):
            gefangen.update(k)
            return 0, []

        with tempfile.TemporaryDirectory(prefix="runde5_") as basis:
            wurzel = Path(basis) / "dump"
            ziel = Path(basis) / "ziel"
            wurzel.mkdir()
            ziel.mkdir()
            param = Path(basis) / "param.json"
            param.write_text('{"contentId": "UP0000-PPSA01234_00-0000000000000000"}',
                             encoding="utf-8")
            with mock.patch.object(APP.sony_sdk, "pruefen",
                                   return_value=SimpleNamespace(vorhanden=True)), \
                    mock.patch.object(APP.sony_sdk, "namen_pruefen", return_value=[]), \
                    mock.patch.object(APP.sony_sdk, "projekt_schreiben"), \
                    mock.patch.object(APP.sony_sdk, "bauen", _bauen), \
                    mock.patch.object(APP.prosperopkg, "zeitgrenze_fuer",
                                      return_value=54321.0) as grenze:
                gui._sdk_bauweg(str(wurzel), str(ziel), basis, str(param),
                                lambda _t: None, {})
        self.assertEqual(54321.0, gefangen.get("zeitgrenze"))
        grenze.assert_called_once_with(str(wurzel))


class EigeneBibliothekTests(unittest.TestCase):
    """U3-8: Der Selbsttest sucht das Programm dieser Plattform."""

    def test_der_selbsttest_sucht_das_programm_der_plattform(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde5_") as ordner:
            for plattform, name in (("linux", "prosperopkg"),
                                    ("darwin", "prosperopkg"),
                                    ("win32", "prosperopkg.exe")):
                with self.subTest(plattform=plattform), \
                        mock.patch.object(eb.sys, "platform", plattform):
                    taugt, grund = eb.kopie_taugt(ordner)
                    self.assertFalse(taugt)
                    self.assertEqual("%s fehlt in der Arbeitskopie" % name, grund)

    def test_alte_befunde_werden_neu_gemessen(self) -> None:
        """Merkzettel von vorher tragen das falsche "untauglich"."""
        self.assertGreaterEqual(eb.MERKZETTEL_FASSUNG, 3)


class CheckpointTaktTests(unittest.TestCase):
    """H2-1/H5-15: Der 5-s-Takt laesst die Fortsetzungsstufe stehen."""

    def _gui(self, basis: str, quelle: str, ziel: str):
        gui = _gui()
        gui._get_config_path = lambda: os.path.join(basis, "paths.json")
        gui.current_mode = SimpleNamespace(get=lambda: "unpack_to_exfat")
        gui.source_path = SimpleNamespace(get=lambda: quelle)
        gui.dest_path = SimpleNamespace(get=lambda: ziel)
        gui.task_displayed = 42.0
        gui._checkpoint_last_save_ts = 0.0
        gui.is_running = True
        return gui

    def test_der_takt_laesst_die_stufe_stehen(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde5_") as basis:
            quelle = os.path.join(basis, "spiel.ffpfsc")
            ziel = os.path.join(basis, "ziel")
            zwischen = os.path.join(basis, "zwischen")
            os.makedirs(zwischen)
            Path(zwischen, "inneres.exfat").write_bytes(b"")
            gui = self._gui(basis, quelle, ziel)
            gui._save_runtime_checkpoint(
                mode="unpack_to_exfat", src=quelle, dst=ziel, state="in_progress",
                extra={"stage": "task2_step1_done", "tmp_dir": zwischen})
            gui._lauf_checkpoint_takt()
            stand = gui._load_runtime_checkpoint("unpack_to_exfat", quelle, ziel)
            self.assertEqual("task2_step1_done", stand.get("stage"))
            self.assertEqual(42.0, stand.get("task_displayed"))
            self.assertTrue(gui._checkpoint_supports_resume("unpack_to_exfat", stand))

    def test_nach_dem_abschluss_legt_der_takt_nichts_neu_an(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde5_") as basis:
            quelle = os.path.join(basis, "spiel.ffpfsc")
            ziel = os.path.join(basis, "ziel")
            gui = self._gui(basis, quelle, ziel)
            gui._save_runtime_checkpoint(
                mode="unpack_to_exfat", src=quelle, dst=ziel, state="success",
                extra={"stage": "completed"})
            gui._clear_runtime_checkpoint(mode="unpack_to_exfat", src=quelle, dst=ziel)
            gui._lauf_checkpoint_takt()
            self.assertIsNone(gui._load_runtime_checkpoint("unpack_to_exfat", quelle, ziel))

    def test_ohne_lauf_schreibt_der_takt_nicht(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde5_") as basis:
            quelle = os.path.join(basis, "spiel.ffpfsc")
            ziel = os.path.join(basis, "ziel")
            gui = self._gui(basis, quelle, ziel)
            gui._save_runtime_checkpoint(
                mode="unpack_to_exfat", src=quelle, dst=ziel, state="aborted",
                extra={"stage": "aborted"})
            gui.is_running = False
            gui._lauf_checkpoint_takt()
            stand = gui._load_runtime_checkpoint("unpack_to_exfat", quelle, ziel)
            self.assertEqual("aborted", stand.get("state"))
            self.assertNotIn("task_displayed", stand)


if __name__ == "__main__":
    unittest.main(verbosity=2)
