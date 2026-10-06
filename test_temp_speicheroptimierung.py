# -*- coding: utf-8 -*-
"""Arbeitskopie im Windows-Temp gegen die Speicheroptimierung (Befund vom 06.10.2026, Dirt 5).

Bei knappem Platz loeschte die Windows-Speicheroptimierung waehrend eines .ffpkg-Baus 67 226 von 67 230 Dateien
der Arbeitskopie in %TEMP% - genau die kopierten mit altem Datum; frisch geschriebene blieben. Geprueft:
Arbeitskopien in ps5conv_*-Ordnern bekommen ein frisches Datum, Sicherungen woanders behalten ihres; der Bau
erkennt eine geschrumpfte Quelle; die Warnung beim Laufstart greift nur im Windows-Temp.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

ALT = time.mktime((2025, 1, 2, 3, 4, 5, 0, 0, -1))


def _gui(temp_basis: str):
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.root = None
    gui.is_running = True
    gui._append_to_log = lambda *_a, **_k: None
    gui._get_runtime_temp_dir = lambda: temp_basis
    return gui


class DatumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="speicheropt_")
        self.addCleanup(shutil.rmtree, self.basis, True)
        self.quelle = os.path.join(self.basis, "Quelle")
        os.makedirs(os.path.join(self.quelle, "data"))
        for name in ("eboot.bin", os.path.join("data", "a.bin")):
            pfad = os.path.join(self.quelle, name)
            Path(pfad).write_bytes(b"x" * 100)
            os.utime(pfad, (ALT, ALT))

    def _kopieren(self, ziel: str) -> None:
        gui = _gui(self.basis)
        gui._kopieren_mit_fortschritt(self.quelle, ziel, 200)

    def test_arbeitskopie_im_verwalteten_temp_bekommt_frisches_datum(self) -> None:
        ziel = os.path.join(self.basis, "ps5conv_integration_test", "Quelle")
        self._kopieren(ziel)
        for name in ("eboot.bin", os.path.join("data", "a.bin")):
            with self.subTest(name=name):
                self.assertGreater(os.path.getmtime(os.path.join(ziel, name)), time.time() - 3600)

    def test_sicherung_ausserhalb_behaelt_das_datum(self) -> None:
        ziel = os.path.join(self.basis, "Zielordner", "Quelle")
        self._kopieren(ziel)
        self.assertAlmostEqual(ALT, os.path.getmtime(os.path.join(ziel, "eboot.bin")), delta=2)

    def test_dateien_zaehlen(self) -> None:
        self.assertEqual(2, APP.PS5ConverterGUI._dateien_zaehlen(self.quelle))
        self.assertEqual(-1, APP.PS5ConverterGUI._dateien_zaehlen(os.path.join(self.basis, "fehlt")))


class SammelAufraeumenTests(unittest.TestCase):
    """Nach jedem Spiel einer Sammelkonvertierung geht seine Arbeitskopie weg - nicht erst beim Programmende."""

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="sammel_raeumen_")
        self.addCleanup(shutil.rmtree, self.basis, True)

    def _kopie(self, name: str) -> str:
        pfad = os.path.join(self.basis, name)
        os.makedirs(os.path.join(pfad, "Spiel"))
        Path(pfad, "Spiel", "eboot.bin").write_bytes(b"x")
        return pfad

    def test_kopien_des_spiels_werden_entfernt(self) -> None:
        gui = _gui(self.basis)
        zeilen = []
        gui._append_to_log = zeilen.append
        gui._integration_ordner = [self._kopie("ps5conv_integration_a"), self._kopie("ps5conv_integration_b")]
        gui._batch_arbeitskopien_raeumen("G:/homebrew/Spiel.ffpkg")
        self.assertEqual([], [n for n in os.listdir(self.basis) if n.startswith("ps5conv_integration_")])
        self.assertEqual([], gui._integration_ordner)
        self.assertEqual(2, len(zeilen))

    def test_ergebnis_in_der_kopie_bleibt(self) -> None:
        gui = _gui(self.basis)
        kopie = self._kopie("ps5conv_integration_c")
        gui._integration_ordner = [kopie]
        gui._batch_arbeitskopien_raeumen(os.path.join(kopie, "Spiel"))
        self.assertTrue(os.path.isdir(kopie))

    def test_der_lauf_raeumt_nach_jedem_spiel(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        stelle = quelle.index("self._batch_arbeitskopien_raeumen(output_path)")
        self.assertLess(quelle.index('item_ok = converted and bool(verification.get("ok", False))'), stelle)
        self.assertIn('setdefault("_integration_ordner", []).append(ziel)', quelle)


class BauTests(unittest.TestCase):
    def test_geschrumpfte_quelle_bricht_ab_statt_weitere_profile(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        stelle = quelle.index('"ffpkg.quelle_geschrumpft"')
        davor = quelle[stelle - 1500:stelle]
        danach = quelle[stelle:stelle + 400]
        self.assertIn("self._dateien_zaehlen(source_dir)", davor)
        self.assertIn("return False", danach)
        self.assertLess(stelle, quelle.index("self._append_to_log(self._t('log.auto.0099'"))


class WarnungTests(unittest.TestCase):
    def test_eigener_ordner_ausserhalb_des_windows_temp_nie(self) -> None:
        self.assertFalse(APP.PS5ConverterGUI._temp_von_speicheroptimierung_bedroht(str(PROJEKT)))

    def test_ohne_windows_nie(self) -> None:
        with mock.patch.object(APP, "IST_WINDOWS", False):
            self.assertFalse(APP.PS5ConverterGUI._temp_von_speicheroptimierung_bedroht(tempfile.gettempdir()))

    @unittest.skipUnless(sys.platform == "win32", "nur Windows")
    def test_windows_temp_mit_eingeschalteter_loeschung(self) -> None:
        import winreg
        werte = {"01": 1, "04": 1}

        class _Schluessel:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        with mock.patch.object(winreg, "OpenKey", return_value=_Schluessel()), \
                mock.patch.object(winreg, "QueryValueEx", side_effect=lambda _s, name: (werte[name], 4)):
            self.assertTrue(APP.PS5ConverterGUI._temp_von_speicheroptimierung_bedroht(tempfile.gettempdir()))
            werte["04"] = 0
            self.assertFalse(APP.PS5ConverterGUI._temp_von_speicheroptimierung_bedroht(tempfile.gettempdir()))


if __name__ == "__main__":
    unittest.main()
