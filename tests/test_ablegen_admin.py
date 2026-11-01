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


class _Programm:
    """Steht fuer das Programmfenster: Die Behandler sind gebundene Methoden wie im Hauptmodul."""

    def __init__(self, wurzel):
        import tkinter as tk
        self.feld = tk.Entry(wurzel)
        self.feld.pack()
        self.abgelegt: list = []

    def abgelegt_bei(self, ereignis):
        self.abgelegt.append(ereignis.data)


@unittest.skipUnless(sys.platform == "win32", "nur Windows")
class MehrfachEinrichtenTests(unittest.TestCase):
    """Volllauf 01.11.2026 als Administrator: Jeder Programmaufbau auf derselben Wurzel hing eine weitere
    Fensterprozedur vor das Hauptfenster (Absturz in update()) und hielt das vorige Programmfenster fest."""

    def setUp(self):
        import ctypes
        import tkinter as tk
        self.wurzel = tk._default_root or tk.Tk()
        self.wurzel.withdraw()
        self.user32 = ctypes.windll.user32
        self.user32.GetWindowLongPtrW.restype = ctypes.c_void_p
        self.user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self.user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        self.user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        self.user32.GetAncestor.restype = ctypes.c_void_p
        self.user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.assertIsNone(getattr(self.wurzel, "_ablegen_admin_zustand", None), "Anker: noch nichts eingehaengt.")
        self.addCleanup(self._aushaengen)

    def _aushaengen(self):
        # Erst die alten Prozeduren zurueck, dann den Zustand (und damit den Rueckruf) freigeben.
        zustand = getattr(self.wurzel, "_ablegen_admin_zustand", None)
        if zustand is None:
            return
        for hwnd, vorher in zustand["alte"].items():
            self.user32.SetWindowLongPtrW(hwnd, ab.GWL_WNDPROC, vorher)
        del self.wurzel._ablegen_admin_zustand

    def _prozedur_des_hauptfensters(self):
        self.wurzel.update_idletasks()
        innen = self.wurzel.winfo_id()
        return self.user32.GetWindowLongPtrW(self.user32.GetAncestor(innen, ab.GA_ROOT) or innen, ab.GWL_WNDPROC)

    def test_zweimal_einrichten_haengt_eine_prozedur_und_laesst_das_alte_programm_frei(self):
        import gc
        import weakref
        erstes = _Programm(self.wurzel)
        self.assertTrue(ab.installieren(self.wurzel, [(erstes.feld, erstes.abgelegt_bei)]))
        prozedur = self._prozedur_des_hauptfensters()
        spur = weakref.ref(erstes)
        erstes.feld.destroy()
        del erstes
        zweites = _Programm(self.wurzel)
        self.addCleanup(zweites.feld.destroy)
        self.assertTrue(ab.installieren(self.wurzel, [(zweites.feld, zweites.abgelegt_bei)]))
        self.assertEqual(prozedur, self._prozedur_des_hauptfensters(),
                         "Das Hauptfenster bekam eine zweite Prozedur vorgehaengt.")
        gc.collect()
        self.assertIsNone(spur(), "Die Ablage haelt das vorige Programmfenster fest.")
        ziele = ab.lebende_ziele(self.wurzel._ablegen_admin_zustand)
        self.assertEqual([(zweites.feld, zweites.abgelegt_bei)], ziele)
        self.wurzel.update()      # Nachrichten laufen durch die eingehaengte Prozedur, ohne Absturz


if __name__ == "__main__":
    unittest.main()
