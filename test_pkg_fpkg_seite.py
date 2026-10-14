# -*- coding: utf-8 -*-
"""Aufgabe 7 "PKG / FPKG" als Seite im rechten Bereich der Ansicht UMWANDELN (``ui/pkg_fpkg_seite.py``,
seit 12.10.2026, bis zum selben Abend noch ein reiner Platzhalter ohne Funktion).

Wunsch des Nutzers: Aufgabe 7 (AMPR EMU Manager) wandert zum Knopf "9." der Ansicht KONSOLE, an ihrer Stelle in der
Seitenleiste UMWANDELN steht "7. PKG / FPKG" mit zwei Knoepfen, **PKG** und **FPKG**. "PKG" zeigt die Oberflaeche
von ``ui/ps4_dump_image.py`` (bis dahin das Popup "PS4 PKG Dump & Image Converter"), "FPKG" die von
``ui/ps5_pkg_fenster.py`` (bis dahin "PS5 PKG Dump & Image Converter") - beide eingebettet statt als eigenes
Fenster, die zwei Knoepfe dafuer unter WEITERE TOOLS sind entfallen.
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.ui import ampr_seite                     # noqa: E402
from ps5_validator.ui import pkg_fpkg_seite                 # noqa: E402
from ps5_validator.ui import ps4_dump_image                 # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster                 # noqa: E402


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class SeitenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._ansicht_setzen("umwandeln")
        self.app._pkg_fpkg_seite_verbergen()

    def _toplevels(self) -> set:
        return {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}

    def test_der_knopf_zeigt_die_seite_ohne_fenster(self) -> None:
        vorher = self._toplevels()
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertTrue(self.app._pkg_fpkg_seite_sichtbar)
        self.assertEqual("grid", s.rahmen.winfo_manager())
        self.assertEqual((1, 1), (int(s.rahmen.grid_info()["row"]), int(s.rahmen.grid_info()["column"])))
        self.assertEqual("", self.app.content_scroll.winfo_manager(), "Die Rollflaeche ist ausgeblendet.")
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein Fenster.")
        self.assertEqual("pkg_fpkg", self.app.current_mode.get())

    def test_ein_zweiter_druck_aendert_nichts(self) -> None:
        self.app._show_pkg_fpkg_seite()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        self.assertTrue(self.app._pkg_fpkg_seite_sichtbar)
        self.assertEqual("grid", s.rahmen.winfo_manager())

    def test_eine_andere_aufgabe_blendet_die_seite_aus(self) -> None:
        self.app._show_pkg_fpkg_seite()
        self.app._set_mode_from_sidebar("pack_folder")
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertFalse(self.app._pkg_fpkg_seite_sichtbar)
        self.assertEqual("", s.rahmen.winfo_manager())
        self.assertEqual("grid", self.app.content_scroll.winfo_manager(), "Die Rollflaeche ist wieder da.")

    def test_die_ampr_seite_und_diese_seite_schliessen_sich_aus(self) -> None:
        """Diese Seite liegt in der Zelle (1, 1) der Ansicht UMWANDELN, die AMPR-Seite in
        derselben Zelle der Ansicht KONSOLE - der Wechsel der Ansicht blendet die eine weg,
        bevor die andere erscheint (seit 12.10.2026: AMPR ist Knopf "9." der Ansicht KONSOLE)."""
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        pkg = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertTrue(self.app._pkg_fpkg_seite_sichtbar)
        self.app._ansicht_setzen("konsole")
        self.app._konsole_amprmgr_zeigen()
        _WURZEL.update()
        try:
            self.assertFalse(self.app._pkg_fpkg_seite_sichtbar)
            self.assertEqual("", pkg.rahmen.winfo_manager())
            ampr = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
            self.assertEqual("grid", ampr.rahmen.winfo_manager())
        finally:
            self.app._ansicht_setzen("umwandeln")

    def test_die_ansicht_konsole_nimmt_die_seite_weg(self) -> None:
        self.app._show_pkg_fpkg_seite()
        self.app._ansicht_setzen("konsole")
        try:
            self.assertFalse(self.app._pkg_fpkg_seite_sichtbar)
            s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
            self.assertEqual("", s.rahmen.winfo_manager())
        finally:
            self.app._ansicht_setzen("umwandeln")

    def test_der_knopf_der_seitenleiste_traegt_die_sieben(self) -> None:
        modi = [m for _n, m in self.app._MODE_OPTIONS]
        namen = [n for n, _m in self.app._MODE_OPTIONS]
        self.assertNotIn("ampr_manager", modi, "Aufgabe 7 ist aus der Seitenleiste UMWANDELN verlegt")
        self.assertIn("7. PKG / FPKG", namen)
        self.assertIn("8. Validator", namen)
        self.assertNotIn("7. AMPR EMU Manager", namen)

    def test_der_konsole_knopf_neun_zeigt_dieselbe_ampr_seite(self) -> None:
        kennungen = [k for _s, k in self.app._KONSOLE_KNOEPFE]
        # Knopf 9; seit 14.10.2026 folgt Knopf 10 "AMPR-Mitschnitt".
        self.assertEqual("amprmgr", kennungen[8])
        self.assertEqual("amprmitschnitt", kennungen[9])
        self.assertEqual("_konsole_amprmgr_zeigen", self.app._KONSOLE_SEITEN["amprmgr"])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class PkgFpkgUnterseitenTests(unittest.TestCase):
    """Die beiden eingebetteten Oberflaechen "PKG" (``ps4_dump_image``) und "FPKG" (``ps5_pkg_fenster``)."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._ansicht_setzen("umwandeln")
        self.app._pkg_fpkg_seite_verbergen()
        # Jeder Test faengt frisch an: die Seite (und mit ihr "PKG"/"FPKG", als ihre Kinder) ganz zerstoeren,
        # statt sie nur auszublenden - sonst stuende "FPKG" noch gewaehlt, wenn ein spaeterer Test "zuerst PKG"
        # erwartet (``_bei_zerstoerung`` setzt die beiden ``FENSTER_ATTRIBUT`` beim Zerstoeren selbst zurueck).
        seite = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT, None)
        if seite is not None:
            try:
                seite.rahmen.destroy()
            except tk.TclError:
                pass
            delattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)

    def _toplevels(self) -> set:
        return {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}

    def test_die_seite_zeigt_zuerst_pkg_ohne_fenster(self) -> None:
        vorher = self._toplevels()
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        ps4 = getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT)
        self.assertIsNotNone(ps4)
        self.assertFalse(isinstance(ps4.win, tk.Toplevel), "Die Oberflaeche liegt in einem Rahmen, nicht in einem Fenster.")
        self.assertIs(s.inhalt, ps4.win.master, "Der Rahmen gehoert der Seite 'PKG / FPKG'.")
        self.assertEqual("pack", ps4.win.winfo_manager())
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein Fenster.")

    def test_der_fpkg_knopf_wechselt_die_unterseite(self) -> None:
        self.app._show_pkg_fpkg_seite()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        s.knoepfe[pkg_fpkg_seite.UNTERSEITE_FPKG].cget("command")()      # derselbe Befehl wie ein echter Klick
        _WURZEL.update()
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite)
        ps4 = getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT)
        ps5 = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)
        self.assertEqual("", ps4.win.winfo_manager(), "PKG ist jetzt ausgeblendet.")
        self.assertEqual("pack", ps5.win.winfo_manager())
        self.assertFalse(isinstance(ps5.win, tk.Toplevel))

    def test_ein_erneuter_druck_auf_sieben_merkt_sich_fpkg(self) -> None:
        self.app._show_pkg_fpkg_seite()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        s.fpkg_zeigen()
        self.app._set_mode_from_sidebar("pack_folder")                 # eine andere Aufgabe blendet die Seite aus
        _WURZEL.update()
        self.app._show_pkg_fpkg_seite()                                # erneut "7." - FPKG soll stehen bleiben
        _WURZEL.update()
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite)
        ps5 = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)
        self.assertEqual("pack", ps5.win.winfo_manager())

    def test_die_knoepfe_tragen_einen_haken_fuer_die_gewaehlte_unterseite(self) -> None:
        self.app._show_pkg_fpkg_seite()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertTrue(s.knoepfe[pkg_fpkg_seite.UNTERSEITE_PKG].cget("text").startswith("✓"))
        self.assertFalse(s.knoepfe[pkg_fpkg_seite.UNTERSEITE_FPKG].cget("text").startswith("✓"))
        s.fpkg_zeigen()
        self.assertFalse(s.knoepfe[pkg_fpkg_seite.UNTERSEITE_PKG].cget("text").startswith("✓"))
        self.assertTrue(s.knoepfe[pkg_fpkg_seite.UNTERSEITE_FPKG].cget("text").startswith("✓"))

    def test_der_ps4_konverter_zeigt_sich_eingebettet_statt_in_einem_fenster(self) -> None:
        """``_show_ps4_pkg_converter`` ist der Weg der Bibliothek (Paket zum Umwandeln) - bis zum 12.10.2026
        abends oeffnete er ein Popup-Fenster, jetzt waehlt er "PKG" dieser Seite."""
        vorher = self._toplevels()
        self.app._ps4pkg_vorgabe = ""
        self.app._show_ps4_pkg_converter()
        _WURZEL.update()
        self.assertEqual("umwandeln", self.app._ansicht)
        self.assertEqual("pkg_fpkg", self.app.current_mode.get())
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein eigenes Fenster mehr.")

    def test_der_ps5_konverter_zeigt_sich_eingebettet_statt_in_einem_fenster(self) -> None:
        vorher = self._toplevels()
        self.app._show_ps5_pkg_converter()
        _WURZEL.update()
        self.assertEqual("umwandeln", self.app._ansicht)
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite)
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein eigenes Fenster mehr.")

    def test_die_weitere_tools_knoepfe_sind_entfernt(self) -> None:
        ziele = [z for _s, z in self.app._MORE_TOOLS_ENTRIES]
        self.assertNotIn("_show_ps4_pkg_converter", ziele)
        self.assertNotIn("_show_ps5_pkg_converter", ziele)
        from ps5_validator.utils.i18n import STRINGS
        self.assertNotIn("titlebar.ps4pkg", STRINGS)
        self.assertNotIn("titlebar.ps5pkg", STRINGS)


if __name__ == "__main__":
    unittest.main()
