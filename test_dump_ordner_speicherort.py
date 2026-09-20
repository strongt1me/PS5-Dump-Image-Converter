# -*- coding: utf-8 -*-
"""Dump-Ordner-Speicherort: Arbeitsordner statt Ziel (Wunsch 15.09.2026).

Die Umpack-Wege legen ihren voruebergehenden Dump-Ordner normalerweise im
Zielordner an. Auf Wunsch soll eine Einstellung ihn in den Arbeitsordner
umlenken, damit am Ziel nur das Ergebnis liegt. Reine Entpack-Aufgaben, deren
Dump-Ordner das Ergebnis IST, bleiben davon unberuehrt.

Geprueft wird das Verhalten der Entscheidung (_dump_ordner_basis /
_dump_im_arbeitsordner), die Platzbuchung (Arbeitsordner statt Ziel) und die
Verdrahtung der sechs Umpack-Wege.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

# Konfigordner umlenken, bevor das Hauptprogramm laedt (siehe project_testaufbau).
_TMP_KFG = tempfile.mkdtemp(prefix="dumpordner_kfg_")
os.environ["PS5CONV_KONFIGORDNER"] = _TMP_KFG

try:
    import tkinter as tk
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


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class DumpOrdnerEntscheidungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def setUp(self):
        # Jeder Test startet ohne CLI-Ueberschreibung und mit der Vorgabe (aus).
        self.app._dump_im_arbeitsordner_cli = None
        self.app._save_setting("dump_in_arbeitsordner", False)

    def test_vorgabe_ist_ziel(self):
        """Ohne Einstellung bleibt der Dump-Ordner beim Ziel (bisheriges Verhalten)."""
        self.assertFalse(self.app._dump_im_arbeitsordner())
        self.assertEqual("Z:/ziel", self.app._dump_ordner_basis("Z:/ziel"))

    def test_gespeicherte_einstellung_lenkt_um(self):
        self.app._save_setting("dump_in_arbeitsordner", True)
        try:
            self.assertTrue(self.app._dump_im_arbeitsordner())
            self.assertIsNone(self.app._dump_ordner_basis("Z:/ziel"))
        finally:
            self.app._save_setting("dump_in_arbeitsordner", False)

    def test_cli_hat_vorrang(self):
        # CLI True lenkt um, auch wenn die Datei False sagt.
        self.app._dump_im_arbeitsordner_cli = True
        self.assertTrue(self.app._dump_im_arbeitsordner())
        self.assertIsNone(self.app._dump_ordner_basis("Z:/ziel"))
        # CLI False bleibt beim Ziel, auch wenn die Datei True sagt.
        self.app._save_setting("dump_in_arbeitsordner", True)
        try:
            self.app._dump_im_arbeitsordner_cli = False
            self.assertFalse(self.app._dump_im_arbeitsordner())
            self.assertEqual("Z:/ziel", self.app._dump_ordner_basis("Z:/ziel"))
        finally:
            self.app._save_setting("dump_in_arbeitsordner", False)

    def test_platz_bucht_dump_auf_temp_bei_umlenkung(self):
        """Bei aktivem Umlenken faellt der Dump-Bedarf auf Temp statt aufs Ziel."""
        self.app._umhuellt_neu_packen = True
        with mock.patch.object(self.app, "_quellgroesse_ermitteln", return_value=1000), \
             mock.patch.object(self.app, "_estimate_unpack_space_requirement",
                               return_value=None), \
             mock.patch.object(self.app, "_integration_gewuenscht", return_value=False):
            self.app._dump_im_arbeitsordner_cli = False
            temp_aus, ziel_aus = self.app._platzbedarf_schaetzen(
                "unpack_to_exfat", "D:/dir", "ffpfsc")
            self.app._dump_im_arbeitsordner_cli = True
            temp_an, ziel_an = self.app._platzbedarf_schaetzen(
                "unpack_to_exfat", "D:/dir", "ffpfsc")
        self.app._umhuellt_neu_packen = False
        self.assertGreater(temp_an, temp_aus,
                           "Umgelenkt muss der Temp-Bedarf steigen")
        self.assertLess(ziel_an, ziel_aus,
                        "Umgelenkt muss der Ziel-Bedarf sinken")
        # Der Dump-Anteil wandert vollstaendig - Summe bleibt gleich.
        self.assertEqual(temp_aus + ziel_aus, temp_an + ziel_an)


class DumpOrdnerVerdrahtungTests(unittest.TestCase):
    """Quelltextpruefung: die sechs Zwischen-Dump-Wege lenken um, die reine
    Entpack-Aufgabe nicht."""

    @classmethod
    def setUpClass(cls):
        with open(HAUPTDATEI, encoding="utf-8") as f:
            cls.quelle = f.read()

    def _rumpf(self, defname: str) -> str:
        i = self.quelle.index("def %s(" % defname)
        j = self.quelle.index("\n    def ", i + 1)
        return self.quelle[i:j]

    def test_sechs_umpack_wege_lenken_um(self):
        # _mode_exfat_umpacken ist der sechste, seit v1.9.34: ein
        # .exFAT-Backup mit Asset-Pack nachruesten laeuft ebenfalls
        # ueber einen Zwischen-Dump-Ordner.
        for defname in ("_mode_ffpfsc_to_ffpkg", "_mode_ffpfsc_umpacken",
                        "_mode_abbild_zu_ffpfs", "_mode_exfat_to_ffpkg",
                        "_mode_ffpkg_to_ffpkg", "_mode_exfat_umpacken"):
            rumpf = self._rumpf(defname)
            self.assertIn("_dump_ordner_basis(dst)", rumpf,
                          "%s muss den Dump-Ordner umlenkbar anlegen" % defname)

    def test_reines_entpacken_bleibt_beim_ziel(self):
        """_mode_unpack_to_game_folder liefert den Dump-Ordner selbst ab."""
        rumpf = self._rumpf("_mode_unpack_to_game_folder")
        self.assertIn("dir_path=dst", rumpf)
        self.assertNotIn("_dump_ordner_basis", rumpf,
                         "Die reine Entpack-Aufgabe darf NICHT umgelenkt werden")

    def test_genau_sechs_aufrufstellen(self):
        self.assertEqual(6, self.quelle.count("self._dump_ordner_basis(dst)"),
                         "Es sollen genau die sechs Umpack-Wege umlenken")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class DumpOrdnerCliTests(unittest.TestCase):
    """Der CLI-Schalter ist ein Drei-Zustand: ohne ihn gilt die gespeicherte
    Einstellung (default None), mit ihm wird erzwungen."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def test_default_ist_none(self):
        parser = self.haupt._build_cli_parser()
        args = parser.parse_args(["--cli", "--task", "1", "--source", "x"])
        self.assertIsNone(getattr(args, "dump_im_arbeitsordner", "fehlt"))

    def test_schalter_setzt_true(self):
        parser = self.haupt._build_cli_parser()
        args = parser.parse_args(
            ["--cli", "--task", "1", "--source", "x", "--dump-im-arbeitsordner"])
        self.assertTrue(args.dump_im_arbeitsordner)

    def test_run_cli_verdrahtet_den_schalter(self):
        """_run_cli setzt den Vorrang-Merker nur, wenn der Schalter kam."""
        quelle = self.__class__.__dict__.get("_q")
        if quelle is None:
            with open(HAUPTDATEI, encoding="utf-8") as f:
                quelle = f.read()
        i = quelle.index("def _run_cli(")
        rumpf = quelle[i:i + 8000]
        self.assertIn('getattr(args, "dump_im_arbeitsordner", None)', rumpf)
        self.assertIn("app._dump_im_arbeitsordner_cli = bool(_dump_cli)", rumpf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
