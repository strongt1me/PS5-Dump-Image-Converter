# -*- coding: utf-8 -*-
"""Waechter fuer conftest.py: Testklassen raeumen nach sich auf.

Gemessen am 19.09.2026: Klassen hielten Syntaxbaeume des Hauptmoduls (je rund
80 MB) und ganze Programmfenster bis zum Laufende - der Volllauf wuchs auf
6,5 GB und scheiterte davor an Speichermangel. ``conftest.py`` gibt beides
nach jeder Klasse frei. Faellt das still weg, wuchse der Speicher wieder.

Die Pruefung laeuft in zwei Klassen; pytest haelt die Reihenfolge der Datei
ein. Die erste haelt einen Syntaxbaum und ein Programmfenster, die zweite
sieht nach, ob beides frei ist. Einzeln oder ohne pytest (dann laeuft
conftest.py nicht) hat die zweite nichts zu pruefen und wird uebersprungen.
"""
from __future__ import annotations

import ast
import gc
import sys
import tkinter as tk
import unittest
import weakref
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("pruefaufraeumen")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

try:
    _WURZEL = tk._default_root or tk.Tk()
    TK_DA = True
except tk.TclError:
    _WURZEL = None
    TK_DA = False

#: Was die erste Klasse hinterlaesst, damit die zweite nachsehen kann.
_SPUREN: dict = {}


def _unter_pytest_mit_conftest() -> bool:
    return "conftest" in sys.modules and hasattr(sys.modules["conftest"],
                                                 "_programmfenster_abbauen")


class AHaeltBeidesTests(unittest.TestCase):
    """Haelt einen Syntaxbaum und ein Programmfenster - wie die grossen Klassen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.baum = ast.parse("x = 1\n")
        _SPUREN["baum_klasse"] = cls
        if TK_DA:
            cls.app = APP.PS5ConverterGUI(_WURZEL)
            # Regel aus test_qualitaetslauf: Wer eine echte Oberflaeche baut,
            # legt die Sprache fest - sonst gilt die des zuletzt geladenen Moduls.
            cls.app._current_language = "de"
            _SPUREN["fenster"] = weakref.ref(cls.app)
            _SPUREN["fenster_klasse"] = cls

    def test_die_klasse_haelt_beides(self) -> None:
        self.assertIsInstance(self.baum, ast.AST)
        if TK_DA:
            self.assertIsNotNone(_SPUREN["fenster"]())


class BIstAufgeraeumtTests(unittest.TestCase):
    """Nach der Klasse davor: nichts davon lebt weiter."""

    def setUp(self) -> None:
        if not _unter_pytest_mit_conftest():
            self.skipTest("nur unter pytest - dort raeumt conftest.py auf")
        if "baum_klasse" not in _SPUREN:
            self.skipTest("nur im Zusammenlauf mit der Klasse davor")

    def test_der_syntaxbaum_ist_frei(self) -> None:
        self.assertNotIn("baum", vars(_SPUREN["baum_klasse"]))

    @unittest.skipUnless(TK_DA, "keine Anzeige")
    def test_das_programmfenster_ist_frei(self) -> None:
        gc.collect()
        self.assertIsNone(_SPUREN["fenster"](),
                          "Das Programmfenster lebt nach seiner Klasse weiter - "
                          "etwas haelt es fest (Fehlermelder der Wurzel? Befehle "
                          "seiner Variablen?)")
        self.assertNotIn("app", vars(_SPUREN["fenster_klasse"]))

    @unittest.skipUnless(TK_DA, "keine Anzeige")
    def test_die_wurzel_lebt_weiter(self) -> None:
        """Abgebaut wird das Fenster, nie die Wurzel - sonst kippt Tcl."""
        self.assertIs(tk._default_root, _WURZEL)
        self.assertTrue(_WURZEL.winfo_exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
