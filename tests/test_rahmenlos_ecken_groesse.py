# -*- coding: utf-8 -*-
"""Rahmenlose Fenster: runde Ecken und ziehbarer Rand (Nutzerauftrag 11.11.2026).

Anlass: "Spiel-Info - Updates & Patches" hatte eckige Ecken, und man konnte es nicht vergroessern. Ein Fenster ohne
Rahmen (``overrideredirect``) rundet Windows nicht von allein und bietet auch keinen Rand zum Ziehen;
``resizable(True, True)`` allein aendert daran nichts. Gemessen am 11.11.2026 unter Windows 11 (Build 26200) am echten
Bildschirm: Mit ``DwmSetWindowAttribute(..., 33, ROUND)`` zeigt die Ecke den Untergrund, ohne das Attribut volles Gruen.
"""
from __future__ import annotations

import ast
import sys
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import fenster_vorn                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Stellen mit ``overrideredirect(True)``, die bewusst keine runden Ecken bekommen (Funktionsname -> Grund).
OHNE_RUNDUNG = {
    "_go_fullscreen": "Vollbild-Rueckfall: das Fenster fuellt den ganzen Bildschirm",
    "_show_splash": "eigene Region mit Radius 22 (``_runde_fensterecken``)",
}
RUNDUNGS_AUFRUFE = ("ecken_runden", "_rahmenlos_rund_und_ziehbar", "_runde_fensterecken")


def rahmenlose_ohne_rundung(quelltext: str) -> list[str]:
    """Funktionen, die ``overrideredirect(True)`` aufrufen, aber nirgends eine Rundung anstossen."""
    baum = ast.parse(quelltext)
    offen: list[str] = []

    def _besuche(knoten, funktion):
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funktion = knoten
        if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                and knoten.func.attr in ("overrideredirect", "wm_overrideredirect")
                and knoten.args and isinstance(knoten.args[0], ast.Constant) and knoten.args[0].value is True
                and funktion is not None):
            text = ast.get_source_segment(quelltext, funktion) or ""
            if not any(a in text for a in RUNDUNGS_AUFRUFE) and funktion.name not in OHNE_RUNDUNG:
                offen.append("%s:%d" % (funktion.name, knoten.lineno))
        for kind in ast.iter_child_nodes(knoten):
            _besuche(kind, funktion)

    _besuche(baum, None)
    return offen


class WaechterTests(unittest.TestCase):

    def test_gegenprobe_erkennt_ein_eckiges_rahmenloses_fenster(self):
        schlecht = "def a(w):\n    w.overrideredirect(True)\n\ndef b(w):\n    w.overrideredirect(True)\n    ecken_runden(w)\n"
        self.assertEqual(["a:2"], rahmenlose_ohne_rundung(schlecht))

    def test_jedes_rahmenlose_fenster_wird_gerundet(self):
        offen = rahmenlose_ohne_rundung(HAUPT.read_text(encoding="utf-8"))
        self.assertEqual([], offen, "rahmenloses Fenster ohne runde Ecken (Ausnahmen: OHNE_RUNDUNG)")

    def test_die_ausnahmen_gibt_es_noch(self):
        text = HAUPT.read_text(encoding="utf-8")
        for name in OHNE_RUNDUNG:
            self.assertIn("def %s(" % name, text, "Ausnahme ohne Funktion - aus OHNE_RUNDUNG streichen")

    def test_rahmenlose_fenster_mit_resizable_true_sind_ziehbar(self):
        """``resizable(True, True)`` an einem rahmenlosen Fenster ist wirkungslos - es braucht den Groessengriff."""
        quelltext = HAUPT.read_text(encoding="utf-8")
        zeilen = quelltext.splitlines()
        baum = ast.parse(quelltext)
        offen = []
        for knoten in ast.walk(baum):
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Zeilenbereich statt get_source_segment: das rechnet bei jedem Aufruf die Zeilenversaetze neu (101 s).
            text = "\n".join(zeilen[knoten.lineno - 1:knoten.end_lineno])
            if "overrideredirect(True)" in text and "resizable(True, True)" in text \
                    and "_rahmenlos_rund_und_ziehbar" not in text:
                offen.append(knoten.name)
        self.assertEqual([], offen)


@unittest.skipUnless(sys.platform == "win32", "Ecken und Region sind nur unter Windows gemessen")
class EckenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk._default_root or tk.Tk()

    def _fenster(self):
        fenster = tk.Toplevel(self.root, bg="#00ff00")
        fenster.overrideredirect(True)
        fenster.geometry("300x200+90+90")
        fenster.update()
        self.addCleanup(fenster.destroy)
        return fenster

    def test_ohne_dwm_greift_die_region(self):
        fenster = self._fenster()
        with mock.patch.object(fenster_vorn, "_dwm_ecken_runden", return_value=False):
            self.assertEqual("region", fenster_vorn.ecken_runden(fenster, 14))
        self._region_pruefen(fenster)

    def test_region_erzwungen(self):
        fenster = self._fenster()
        self.assertEqual("region", fenster_vorn.ecken_runden(fenster, 14, verfahren="region"))
        self._region_pruefen(fenster)

    def _region_pruefen(self, fenster) -> None:
        """Windows kennt zu dem Fenster eine zusammengesetzte Region (also nicht das volle Rechteck)."""
        import ctypes

        benutzer, gdi = ctypes.windll.user32, ctypes.windll.gdi32
        gdi.CreateRectRgn.restype = ctypes.c_void_p
        benutzer.GetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        hwnd = fenster_vorn._oberstes_handle(fenster)
        region = gdi.CreateRectRgn(0, 0, 0, 0)
        try:
            art = benutzer.GetWindowRgn(ctypes.c_void_p(hwnd), ctypes.c_void_p(region))
        finally:
            gdi.DeleteObject(ctypes.c_void_p(region))
        self.assertEqual(3, art, "Region ist nicht gesetzt oder nicht gerundet (1 leer, 2 einfach, 3 zusammengesetzt)")

    def test_region_folgt_der_groesse(self):
        fenster = self._fenster()
        fenster_vorn.ecken_runden(fenster, 14, verfahren="region")
        fenster.geometry("500x320+90+90")
        for _ in range(8):
            fenster.update()
            fenster.after(30)
        self._region_pruefen(fenster)

    def test_ohne_beides_bleibt_es_eckig(self):
        fenster = self._fenster()
        with mock.patch.object(fenster_vorn, "_dwm_ecken_runden", return_value=False), \
                mock.patch.object(fenster_vorn, "_region_runden", return_value=False):
            self.assertEqual("", fenster_vorn.ecken_runden(fenster, 14))

    def test_windows_11_nimmt_das_dwm_attribut(self):
        if sys.getwindowsversion().build < 22000:
            self.skipTest("Windows 10: das Attribut gibt es nicht, die Region springt ein")
        self.assertEqual("dwm", fenster_vorn.ecken_runden(self._fenster(), 14))


class AndereSystemeTests(unittest.TestCase):

    def test_ausserhalb_von_windows_bleibt_alles_wie_es_ist(self):
        with mock.patch.object(fenster_vorn.sys, "platform", "linux"):
            self.assertEqual("", fenster_vorn.ecken_runden(object(), 14))


class GriffTests(unittest.TestCase):
    """Der Groessengriff mit einem echten, rahmenlosen Fenster (400x300 bei +100+100)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk._default_root or tk.Tk()

    def setUp(self) -> None:
        self.fenster = tk.Toplevel(self.root)
        self.fenster.overrideredirect(True)
        self.fenster.geometry("400x300+100+100")
        self.fenster.update()
        self.addCleanup(self.fenster.destroy)
        self.griff = fenster_vorn.GroessenGriff(self.fenster, 250, 180, rand=6, ecke=18)
        self.x0, self.y0 = self.fenster.winfo_rootx(), self.fenster.winfo_rooty()

    def _zone(self, dx: int, dy: int) -> str:
        return self.griff.zone(self.x0 + dx, self.y0 + dy)

    def test_zonen(self):
        self.assertEqual("", self._zone(200, 150))      # Mitte
        self.assertEqual("", self._zone(200, 2))        # Oberkante: dort liegt die Titelleiste zum Verschieben
        self.assertEqual("e", self._zone(397, 150))
        self.assertEqual("w", self._zone(2, 150))
        self.assertEqual("s", self._zone(200, 297))
        self.assertEqual("se", self._zone(397, 297))
        self.assertEqual("sw", self._zone(2, 297))
        self.assertEqual("e", self._zone(397, 20))      # auch neben der Titelleiste
        self.assertEqual("se", self._zone(385, 297))    # Ecke reicht ein Stueck an der Unterkante entlang
        self.assertEqual("se", self._zone(397, 285))    # und an der Seitenkante hinauf

    def _ziehen(self, start: tuple[int, int], ziel: tuple[int, int]) -> str:
        sx, sy = self.x0 + start[0], self.y0 + start[1]
        self.griff._gedrueckt(SimpleNamespace(x_root=sx, y_root=sy))
        self.griff._gezogen(SimpleNamespace(x_root=self.x0 + ziel[0], y_root=self.y0 + ziel[1]))
        self.griff._losgelassen()
        self.fenster.update()
        return self.fenster.geometry()

    def test_rechts_unten_vergroessert(self):
        self.assertEqual("500x380+100+100", self._ziehen((397, 297), (497, 377)))

    def test_links_ziehen_haelt_die_rechte_kante(self):
        # 100 px nach links: 100 breiter, Fenster 100 weiter links - die rechte Kante (x = 500) bleibt stehen.
        self.assertEqual("500x300+0+100", self._ziehen((2, 150), (-98, 150)))

    def test_mindestgroesse_gilt(self):
        self.assertEqual("250x180+100+100", self._ziehen((397, 297), (0, 0)))

    def test_von_links_verkleinert_haelt_die_rechte_kante(self):
        # Rechte Kante bei x = 500; das Fenster schrumpft nur bis zur Mindestbreite 250 und endet bei x = 250.
        self.assertEqual("250x300+250+100", self._ziehen((2, 150), (900, 150)))

    def test_ein_klick_in_der_mitte_aendert_nichts(self):
        self.assertEqual("400x300+100+100", self._ziehen((200, 150), (300, 250)))

    def test_zeiger_am_rand(self):
        self.griff._bewegt(SimpleNamespace(x_root=self.x0 + 397, y_root=self.y0 + 150))
        self.assertEqual("size_we" if sys.platform == "win32" else self.griff._zeiger, self.griff._zeiger)
        self.assertNotEqual("", self.griff._zeiger)
        self.griff._bewegt(SimpleNamespace(x_root=self.x0 + 200, y_root=self.y0 + 150))
        self.assertEqual("", self.griff._zeiger)

    def test_die_echte_maus_erreicht_den_griff_auch_ueber_kindern(self):
        """Ein Kind im Fenster ueberdeckt den Rand - die Bindung am Toplevel sieht es trotzdem."""
        kind = tk.Frame(self.fenster, bg="#222222")
        kind.pack(fill="both", expand=True)
        self.fenster.update()
        kind.event_generate("<Motion>", rootx=self.x0 + 397, rooty=self.y0 + 150)
        self.fenster.update()
        self.assertNotEqual("", self.griff._zeiger)


if __name__ == "__main__":
    unittest.main()
