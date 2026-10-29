# -*- coding: utf-8 -*-
"""Ablage als Administrator (``ablegen_admin``): Zielwahl, Tcl-Liste und das Verhalten ausserhalb von Windows."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ablegen_admin as ab  # noqa: E402


class _Feld:
    def __init__(self, x, y, b, h):
        self._g = (x, y, b, h)

    def winfo_rootx(self): return self._g[0]
    def winfo_rooty(self): return self._g[1]
    def winfo_width(self): return self._g[2]
    def winfo_height(self): return self._g[3]


class ZielwahlTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = _Feld(0, 0, 100, 20), _Feld(0, 30, 100, 20)
        self.ziele = [(self.a, "quelle"), (self.b, "ziel")]

    def test_der_punkt_im_feld_waehlt_dessen_behandler(self):
        self.assertEqual("ziel", ab.ziel_waehlen((10, 40), self.ziele))
        self.assertEqual("quelle", ab.ziel_waehlen((10, 5), self.ziele))

    def test_ausserhalb_aller_felder_gilt_das_erste(self):
        self.assertEqual("quelle", ab.ziel_waehlen((500, 500), self.ziele))

    def test_ohne_ziele_gibt_es_keinen_behandler(self):
        self.assertIsNone(ab.ziel_waehlen((1, 1), []))

    def test_pfade_mit_leerzeichen_bleiben_beim_zerlegen_heil(self):
        import tkinter as tk
        # Die gemeinsame Wurzel der Testreihe: eine eigene zu zerstoeren nimmt den anderen Tests die Standardwurzel.
        wurzel = tk._default_root or tk.Tk()
        wurzel.withdraw()
        daten = ab.pfade_in_liste(["C:/Mein Spiel", "C:/a"], wurzel.tk)
        self.assertEqual(("C:/Mein Spiel", "C:/a"), tuple(wurzel.tk.splitlist(daten)))

    def test_ausserhalb_von_windows_wird_nichts_eingerichtet(self):
        with mock.patch.object(ab.sys, "platform", "linux"):
            self.assertFalse(ab.installieren(object(), []))


if __name__ == "__main__":
    unittest.main()
