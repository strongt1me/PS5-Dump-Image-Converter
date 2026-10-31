# -*- coding: utf-8 -*-
"""Bindungen am Toplevel, die ein kurzlebiges Widget beim Zerstoeren wieder abnimmt (``utils/tk_bindungen.py``)."""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.utils.tk_bindungen import an_toplevel_binden, bindung_loesen    # noqa: E402


def _skripte(oben: tk.Misc, sequenz: str) -> list:
    return [z for z in str(oben.tk.call("bind", oben._w, sequenz)).split("\n") if z.strip()]


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ToplevelBindungenTests(unittest.TestCase):

    def setUp(self) -> None:
        self.oben = tk.Toplevel(_WURZEL)
        self.addCleanup(self.oben.destroy)

    def _widget(self) -> tk.Canvas:
        return tk.Canvas(tk.Frame(self.oben))

    def test_die_bindung_verschwindet_mit_dem_widget(self) -> None:
        rahmen = tk.Frame(self.oben)
        leinwand = tk.Canvas(rahmen)
        gerufen = []
        an_toplevel_binden(leinwand, "<<Probe>>", lambda e: gerufen.append(1))
        self.assertEqual(1, len(_skripte(self.oben, "<<Probe>>")))
        rahmen.destroy()
        self.assertEqual([], _skripte(self.oben, "<<Probe>>"), "Die Bindung ist mit dem Widget gegangen.")

    def test_gegenprobe_eine_gewoehnliche_bindung_bleibt_stehen(self) -> None:
        """Das ist der Fehler, den der Helfer behebt: ``bind`` am Toplevel ueberlebt das Widget, das sie gebaut hat."""
        rahmen = tk.Frame(self.oben)
        leinwand = tk.Canvas(rahmen)
        leinwand.winfo_toplevel().bind("<<Probe>>", lambda e: None, add="+")
        rahmen.destroy()
        self.assertEqual(1, len(_skripte(self.oben, "<<Probe>>")))

    def test_die_bindungen_anderer_widgets_bleiben(self) -> None:
        a, b = tk.Canvas(tk.Frame(self.oben)), tk.Canvas(tk.Frame(self.oben))
        gerufen = []
        an_toplevel_binden(a, "<<Probe>>", lambda e: gerufen.append("a"))
        an_toplevel_binden(b, "<<Probe>>", lambda e: gerufen.append("b"))
        self.assertEqual(2, len(_skripte(self.oben, "<<Probe>>")))
        a.master.destroy()
        self.assertEqual(1, len(_skripte(self.oben, "<<Probe>>")), "Nur die Bindung des zerstoerten Widgets ging.")
        self.oben.event_generate("<<Probe>>")
        self.oben.update()
        self.assertEqual(["b"], gerufen)

    def test_das_tcl_kommando_wird_mit_freigegeben(self) -> None:
        leinwand = self._widget()
        kennung = an_toplevel_binden(leinwand, "<<Probe>>", lambda e: None)
        self.assertIn(kennung, self.oben.tk.splitlist(self.oben.tk.call("info", "commands")))
        leinwand.master.destroy()
        self.assertNotIn(kennung, self.oben.tk.splitlist(self.oben.tk.call("info", "commands")))

    def test_bindung_loesen_nimmt_nur_die_eine_ab(self) -> None:
        k1 = self.oben.bind("<<Probe>>", lambda e: None, add="+")
        k2 = self.oben.bind("<<Probe>>", lambda e: None, add="+")
        self.assertEqual(2, len(_skripte(self.oben, "<<Probe>>")))
        bindung_loesen(self.oben, "<<Probe>>", k1)
        rest = _skripte(self.oben, "<<Probe>>")
        self.assertEqual(1, len(rest))
        self.assertIn(k2, rest[0])


if __name__ == "__main__":                           # pragma: no cover
    unittest.main()
