# -*- coding: utf-8 -*-
"""Der Standard-Arbeitsordner: ohne Wahl des Anwenders ``<Systemlaufwerk>\\Temp - Dump-Image Converter``.

Nutzerwunsch (15.10.2026): Wird kein Temp-Ordner gewaehlt und eine Aufgabe im Bereich UMWANDELN gestartet,
legt das Programm im Wurzelverzeichnis des Systemlaufwerks (dort, wo Windows liegt, meist ``C:``) den Ordner
``Temp - Dump-Image Converter`` an und arbeitet darin. Bis v1.9.78 war es der Temp-Ordner des Systems, den Windows
von sich aus aufraeumt.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import arbeitsordner as ao  # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class StandardOrdnerTests(unittest.TestCase):
    def test_unter_windows_im_wurzelverzeichnis_des_systemlaufwerks(self) -> None:
        self.assertEqual("C:\\Temp - Dump-Image Converter", ao.standard_ordner("win32", {"SystemDrive": "C:"}))
        self.assertEqual("D:\\Temp - Dump-Image Converter", ao.standard_ordner("win32", {"SystemDrive": "D:"}))
        # Ein Schraegstrich oder Rueckstrich hinter dem Laufwerk stoert nicht, die Schreibung bleibt.
        self.assertEqual("e:\\Temp - Dump-Image Converter", ao.standard_ordner("win32", {"SystemDrive": "e:\\"}))

    def test_der_name_ist_der_gewuenschte(self) -> None:
        self.assertEqual("Temp - Dump-Image Converter", ao.NAME)

    def test_ohne_oder_mit_unbrauchbarem_systemlaufwerk_gilt_c(self) -> None:
        for wert in (None, "", "   ", "Windows", "C:\\Windows", "\\\\server\\freigabe", "1:"):
            with self.subTest(systemdrive=wert):
                umgebung = {} if wert is None else {"SystemDrive": wert}
                self.assertEqual("C:\\Temp - Dump-Image Converter", ao.standard_ordner("win32", umgebung))

    def test_unter_linux_und_macos_gilt_der_temp_ordner_des_systems(self) -> None:
        for plattform in ("linux", "darwin"):
            with self.subTest(plattform=plattform):
                self.assertEqual("", ao.standard_ordner(plattform, {"SystemDrive": "C:"}))

    def test_die_uebersteuerung_gilt_auf_jeder_plattform(self) -> None:
        eigener = os.path.join(tempfile.gettempdir(), "mein_arbeitsordner")
        for plattform in ("win32", "linux", "darwin"):
            with self.subTest(plattform=plattform):
                self.assertEqual(os.path.normpath(eigener),
                                 ao.standard_ordner(plattform, {ao.UEBERSTEUERUNG: eigener, "SystemDrive": "C:"}))

    def test_die_testreihe_lenkt_um(self) -> None:
        """Ohne diese Umlenkung schriebe die Testreihe in das echte Wurzelverzeichnis des Systemlaufwerks."""
        self.assertTrue(os.environ.get(ao.UEBERSTEUERUNG), "tests/conftest.py setzt PS5CONV_STANDARD_TEMP nicht.")
        self.assertNotEqual("C:\\Temp - Dump-Image Converter", ao.standard_ordner())

    def test_der_ordner_wird_beim_nachfragen_nicht_angelegt(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            ziel = os.path.join(basis, "gibts_noch_nicht")
            ao.standard_ordner("win32", {ao.UEBERSTEUERUNG: ziel})
            self.assertFalse(os.path.exists(ziel))


class _Var:
    def __init__(self, wert=""):
        self._wert = wert

    def get(self):
        return self._wert

    def set(self, wert):
        self._wert = wert


class ArbeitsordnerImProgrammTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="arbeitsordner_")
        self.standard = os.path.join(self.basis, "Temp - Dump-Image Converter")
        self._alt = os.environ.get(ao.UEBERSTEUERUNG)
        os.environ[ao.UEBERSTEUERUNG] = self.standard
        self.gespeichert: dict[str, str] = {}
        haupt = self.haupt

        class App:
            _TEMP_PRUEF_GUELTIG_S = haupt.PS5ConverterGUI._TEMP_PRUEF_GUELTIG_S
            _get_runtime_temp_dir = haupt.PS5ConverterGUI._get_runtime_temp_dir
            _load_runtime_temp_dir = haupt.PS5ConverterGUI._load_runtime_temp_dir

            def _load_setting(_selbst, schluessel, vorgabe=None):
                return self_test.gespeichert.get(schluessel, vorgabe)

            def _save_setting(_selbst, schluessel, wert):
                self_test.gespeichert[schluessel] = wert

        self_test = self
        self.app = App()
        self.app.temp_path = _Var("")

    def tearDown(self) -> None:
        if self._alt is None:
            os.environ.pop(ao.UEBERSTEUERUNG, None)
        else:
            os.environ[ao.UEBERSTEUERUNG] = self._alt
        shutil.rmtree(self.basis, ignore_errors=True)

    def test_ohne_wahl_wird_der_standardordner_angelegt_und_benutzt(self) -> None:
        self.assertFalse(os.path.isdir(self.standard))
        benutzt = self.app._get_runtime_temp_dir()
        self.assertEqual(os.path.normpath(self.standard), benutzt)
        self.assertTrue(os.path.isdir(self.standard), "Der Ordner muss beim ersten Gebrauch entstehen.")
        self.assertEqual([], [n for n in os.listdir(self.standard) if n.startswith(".ps5conv_tmp_write_test_")])

    def test_die_startarbeiten_legen_den_ordner_nicht_an(self) -> None:
        """Nutzerwunsch: Der Ordner entsteht mit der ersten Aufgabe, nicht schon beim Oeffnen des Programms."""
        self.assertEqual(os.path.normpath(tempfile.gettempdir()), self.app._get_runtime_temp_dir(anlegen=False))
        self.assertFalse(os.path.exists(self.standard))
        # Auch die Aufraeumpruefung (laeuft beim Start) legt ihn nicht an ...
        self.app._is_managed_temp_path = self.haupt.PS5ConverterGUI._is_managed_temp_path.__get__(self.app)
        self.app._is_managed_temp_path(os.path.join(tempfile.gettempdir(), "ps5conv_x"))
        self.assertFalse(os.path.exists(self.standard))
        # ... und sobald er da ist, gilt er auch fuer sie.
        self.app._get_runtime_temp_dir()
        self.assertEqual(os.path.normpath(self.standard), self.app._get_runtime_temp_dir(anlegen=False))

    def test_der_start_raeumt_im_standardordner_auf(self) -> None:
        """Die Reste-Suche beim Start muss den neuen Ordner kennen, sonst bleibt dort alles liegen."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        start = quelle.index("    def _temp_fallback_candidates(")
        rumpf = quelle[start:start + 3500]
        self.assertIn("_add(arbeitsordner.standard_ordner())", rumpf)

    def test_das_feld_bleibt_dabei_leer(self) -> None:
        """Die Regel vom 11.10.2026: Ein Nachfragen fuellt das Feld nicht - das tut erst der Start einer Aufgabe."""
        self.app._get_runtime_temp_dir()
        self.assertEqual("", self.app.temp_path.get())
        self.assertNotIn("temp_dir", self.gespeichert)

    def test_ein_gewaehlter_ordner_hat_vorrang(self) -> None:
        eigener = os.path.join(self.basis, "mein_ordner")
        self.app.temp_path.set(eigener)
        self.assertEqual(os.path.normpath(eigener), self.app._get_runtime_temp_dir())
        self.assertFalse(os.path.isdir(self.standard), "Mit eigener Wahl darf der Standardordner nicht entstehen.")

    def test_laesst_sich_der_standardordner_nicht_anlegen_gilt_der_systemtemp(self) -> None:
        # Unter einer Datei laesst sich kein Ordner anlegen.
        datei = os.path.join(self.basis, "datei.txt")
        Path(datei).write_text("x", encoding="utf-8")
        os.environ[ao.UEBERSTEUERUNG] = os.path.join(datei, "unter_einer_datei")
        benutzt = self.app._get_runtime_temp_dir()
        self.assertEqual(os.path.normpath(tempfile.gettempdir()), benutzt)
        self.assertEqual("", self.app.temp_path.get(), "Ohne eigene Wahl bleibt das Feld auch im Ausweichfall leer.")

    def test_das_startfeld_ohne_start_leer_nennt_den_standardordner(self) -> None:
        self.assertEqual(os.path.normpath(self.standard), self.app._load_runtime_temp_dir())

    def test_der_start_einer_aufgabe_traegt_den_ordner_ein(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        start = quelle.index("    def _launch_task(self)")
        ende = quelle.index("    def _kill_task(self)")
        rumpf = quelle[start:ende]
        self.assertIn("if not str(self.temp_path.get()).strip():", rumpf)
        self.assertIn("self.temp_path.set(effective_tmp)", rumpf)

    def test_der_aufraeumschutz_haelt_den_ordner_selbst_fest(self) -> None:
        """Nur ``ps5conv_*`` darunter gilt als verwaltet - der Ordner selbst und fremde Dateien nie."""
        haupt = self.haupt
        app = self.app
        app._is_managed_temp_path = haupt.PS5ConverterGUI._is_managed_temp_path.__get__(app)
        benutzt = app._get_runtime_temp_dir()
        self.assertFalse(app._is_managed_temp_path(benutzt))
        self.assertFalse(app._is_managed_temp_path(os.path.join(benutzt, "fremde_datei.bin")))
        self.assertTrue(app._is_managed_temp_path(os.path.join(benutzt, "ps5conv_abc123", "x")))


if __name__ == "__main__":
    unittest.main()
