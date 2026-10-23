# -*- coding: utf-8 -*-
"""Fenster bleiben vor ihrem Eltern-Fenster (Nutzerauftrag 21.10.2026).

Vorfall: "Spiel-Info - Updates & Patches" erschien nicht im Vordergrund, und nach einem Klick neben das Fenster
verschwand es hinter dem Hauptfenster; der Knopf wirkte dann wie "zweimal klicken". Gemessen an der
Z-Reihenfolge unter Windows: Ein rahmenloses Fenster (``overrideredirect``) bleibt auch nach ``transient`` **nicht**
oben, mit einem Win32-Besitzer (``fenster_vorn``) schon.

Dazu: Meldungen und Dateidialoge gehoeren dem Fenster mit dem Fokus, nicht stets dem Hauptfenster.
"""
from __future__ import annotations

import ast
import ctypes
import sys
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import filedialog
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.ui import meldungen                      # noqa: E402
from ps5_validator.utils import fenster_vorn                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _z_oben_nach_unten(fenster: dict) -> list[str]:
    """Namen der Fenster in Z-Reihenfolge, oberstes zuerst (nur Windows)."""
    from ctypes import wintypes

    benutzer = ctypes.windll.user32
    benutzer.GetAncestor.restype = wintypes.HWND
    benutzer.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    ziel = {benutzer.GetAncestor(w.winfo_id(), 2): n for n, w in fenster.items()}
    reihe: list[str] = []

    def _cb(h, _l):
        if h in ziel:
            reihe.append(ziel[h])
        return True

    benutzer.EnumWindows(proc(_cb), 0)
    return reihe


@unittest.skipUnless(sys.platform == "win32", "Z-Reihenfolge ist nur unter Windows gemessen")
class ZReihenfolgeTests(unittest.TestCase):
    """Mit echten Fenstern: Ein Klick (Anheben) des Hauptfensters darf das Fenster nicht verdecken."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk._default_root or tk.Tk()

    def _paar(self, rahmenlos: bool, besitzer: bool):
        haupt = tk.Toplevel(self.root)
        haupt.geometry("400x300+80+80")
        haupt.update()
        fenster = tk.Toplevel(haupt)
        if rahmenlos:
            fenster.overrideredirect(True)
        fenster.geometry("200x150+120+120")
        fenster.update()
        if besitzer:
            self.assertTrue(fenster_vorn.besitzer_setzen(fenster, haupt))
        fenster.lift()
        fenster.update()
        self.addCleanup(haupt.destroy)
        return haupt, fenster

    def _nach_klick(self, haupt, fenster) -> list[str]:
        haupt.lift()
        haupt.focus_force()
        for _ in range(6):
            haupt.update()
            haupt.after(30)
        return _z_oben_nach_unten({"haupt": haupt, "fenster": fenster})

    def test_rahmenlos_ohne_besitzer_faellt_dahinter_gegenprobe(self) -> None:
        haupt, fenster = self._paar(rahmenlos=True, besitzer=False)
        self.assertEqual(["haupt", "fenster"], self._nach_klick(haupt, fenster),
                         "Die Gegenprobe: Ohne Besitzer verschwindet ein rahmenloses Fenster.")

    def test_rahmenlos_mit_besitzer_bleibt_oben(self) -> None:
        haupt, fenster = self._paar(rahmenlos=True, besitzer=True)
        self.assertEqual(["fenster", "haupt"], self._nach_klick(haupt, fenster))

    def test_rahmenlos_vorn_halten_setzt_den_besitzer(self) -> None:
        haupt = tk.Toplevel(self.root)
        haupt.geometry("400x300+80+80")
        haupt.update()
        fenster = tk.Toplevel(haupt)
        fenster.overrideredirect(True)
        fenster.geometry("200x150+120+120")
        fenster.update()
        self.addCleanup(haupt.destroy)
        self.assertTrue(fenster_vorn.rahmenlos_vorn_halten(fenster, haupt))
        fenster.lift()
        fenster.update()
        self.assertEqual(["fenster", "haupt"], self._nach_klick(haupt, fenster))


class AktivesFensterTests(unittest.TestCase):
    def test_nimmt_das_fenster_mit_dem_fokus(self) -> None:
        oben = mock.Mock()
        oben.winfo_exists.return_value = True
        oben.winfo_viewable.return_value = True
        fokus = mock.Mock()
        fokus.winfo_toplevel.return_value = oben
        wurzel = mock.Mock()
        wurzel.focus_displayof.return_value = fokus
        self.assertIs(oben, fenster_vorn.aktives_fenster(wurzel))

    def test_ohne_fokus_oder_unsichtbar_die_wurzel(self) -> None:
        wurzel = mock.Mock()
        wurzel.focus_displayof.return_value = None
        self.assertIs(wurzel, fenster_vorn.aktives_fenster(wurzel))
        oben = mock.Mock()
        oben.winfo_exists.return_value = True
        oben.winfo_viewable.return_value = False
        fokus = mock.Mock()
        fokus.winfo_toplevel.return_value = oben
        wurzel.focus_displayof.return_value = fokus
        self.assertIs(wurzel, fenster_vorn.aktives_fenster(wurzel))

    def test_tk_fehler_gibt_die_wurzel(self) -> None:
        wurzel = mock.Mock()
        wurzel.focus_displayof.side_effect = tk.TclError("weg")
        self.assertIs(wurzel, fenster_vorn.aktives_fenster(wurzel))


class MeldungenUndDialogeTests(unittest.TestCase):
    def tearDown(self) -> None:
        meldungen.aufheben()

    def test_meldung_ohne_parent_gehoert_dem_aktiven_fenster(self) -> None:
        gui = mock.Mock()
        aktiv = object()
        gegeben = {}

        class _Attrappe:
            def __init__(self, gui_, art, titel, text, eltern=None, vorgabe=""):
                gegeben["eltern"] = eltern

            def zeigen(self):
                return "ok"

        with mock.patch.object(meldungen, "Meldung", _Attrappe), \
                mock.patch.object(meldungen.fenster_vorn, "aktives_fenster", return_value=aktiv):
            meldungen.zeigen(gui, "showinfo", "T", "M")
            self.assertIs(aktiv, gegeben["eltern"])
            eigener = object()
            meldungen.zeigen(gui, "showinfo", "T", "M", parent=eigener)
            self.assertIs(eigener, gegeben["eltern"], "Ein ausdruecklicher parent geht vor.")

    def test_dateidialoge_bekommen_den_aktiven_besitzer_und_werden_zurueckgestellt(self) -> None:
        originale = {n: getattr(filedialog, n) for n in meldungen.DATEIDIALOGE}
        gui = mock.Mock()
        aktiv = object()
        aufrufe = []
        for n in meldungen.DATEIDIALOGE:
            setattr(filedialog, n, lambda *a, _n=n, **k: aufrufe.append((_n, k)) or "x")
        try:
            with mock.patch.object(meldungen.fenster_vorn, "aktives_fenster", return_value=aktiv):
                meldungen.einrichten(gui)
                filedialog.askdirectory(title="a")
                filedialog.askopenfilename(parent="eigen")
            self.assertIs(aktiv, aufrufe[0][1]["parent"])
            self.assertEqual("eigen", aufrufe[1][1]["parent"])
            meldungen.aufheben()
            self.assertNotEqual("askdirectory", getattr(filedialog, "askdirectory").__name__
                                if getattr(filedialog.askdirectory, "__name__", "") == "askdirectory"
                                and filedialog.askdirectory.__module__ == meldungen.__name__ else "x")
        finally:
            for n, f in originale.items():
                setattr(filedialog, n, f)


class QuelltextTests(unittest.TestCase):
    """Wer ein rahmenloses Fenster baut, haelt es vorn - sonst faellt es nach einem Klick dahinter."""

    #: Ausnahmen mit Grund: Der Starttext steht vor dem Hauptfenster, das Tooltip lebt Sekunden.
    AUSNAHMEN = {"_show_splash"}

    def test_jedes_rahmenlose_toplevel_wird_vorn_gehalten(self) -> None:
        quelle = HAUPT.read_text(encoding="utf-8")
        baum = ast.parse(quelle)
        fehlt = []
        for funktion in ast.walk(baum):
            if not isinstance(funktion, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            text = ast.get_source_segment(quelle, funktion) or ""
            if ".overrideredirect(True)" not in text:
                continue
            if funktion.name in self.AUSNAHMEN or "_rahmenlos_vorn_halten" in text:
                continue
            # Das Hauptfenster selbst (root.overrideredirect) ist kein Toplevel mit Eltern.
            if "self.root.overrideredirect(True)" in text and "tk.Toplevel(" not in text:
                continue
            fehlt.append(funktion.name)
        self.assertEqual([], fehlt)

    def test_paketfenster_binden_ihr_toplevel(self) -> None:
        for name in ("pkg_datei_browser.py", "spiel_detail_fenster.py"):
            text = (PROJEKT / "ps5_validator" / "ui" / name).read_text(encoding="utf-8")
            self.assertIn("_fenster_an_hauptfenster_binden", text, name)


if __name__ == "__main__":
    unittest.main()
