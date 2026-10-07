# -*- coding: utf-8 -*-
"""Aufgabe 7 als Seite im rechten Bereich der Ansicht UMWANDELN (``ui/ampr_seite.py``, seit 07.10.2026).

Gemessen werden die Ablaeufe, die der Nutzer sieht: Der Knopf zeigt die Seite statt eines Fensters, eine
andere Aufgabe blendet sie aus und stellt die Rollflaeche wieder her, ein zweiter Druck aendert nichts,
und die Methodenwahl wechselt zum Ablauf, ohne dass ein Fenster entsteht.
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

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

from ps5_validator.ui import ampr_seite                    # noqa: E402
from ps5_validator.utils import shadowmount_generation as sm_gen   # noqa: E402



@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class SeitenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._ampr_seite_verbergen()

    def _toplevels(self) -> set:
        return {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}

    def test_der_knopf_zeigt_die_seite_ohne_fenster(self) -> None:
        vorher = self._toplevels()
        self.app._show_ampr_auswahl()
        _WURZEL.update()
        s = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
        self.assertTrue(self.app._ampr_seite_sichtbar)
        self.assertEqual("grid", s.rahmen.winfo_manager())
        self.assertEqual((1, 1), (int(s.rahmen.grid_info()["row"]), int(s.rahmen.grid_info()["column"])))
        self.assertEqual("", self.app.content_scroll.winfo_manager(), "Die Rollflaeche ist ausgeblendet.")
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein Fenster.")
        self.assertEqual("ampr_manager", self.app.current_mode.get())

    def test_ein_zweiter_druck_aendert_nichts(self) -> None:
        self.app._show_ampr_auswahl()
        s = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
        self.app._show_ampr_auswahl()
        _WURZEL.update()
        self.assertTrue(self.app._ampr_seite_sichtbar)
        self.assertEqual("grid", s.rahmen.winfo_manager())

    def test_eine_andere_aufgabe_blendet_die_seite_aus(self) -> None:
        self.app._show_ampr_auswahl()
        self.app._set_mode_from_sidebar("pack_folder")
        _WURZEL.update()
        s = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
        self.assertFalse(self.app._ampr_seite_sichtbar)
        self.assertEqual("", s.rahmen.winfo_manager())
        self.assertEqual("grid", self.app.content_scroll.winfo_manager(), "Die Rollflaeche ist wieder da.")

    def test_die_methode_wechselt_zum_ablauf_und_startet_von_selbst(self) -> None:
        laeufe: list = []

        def attrappe(self_, generation, fenster, melde):
            laeufe.append((generation, fenster))
            melde("[Test] Lauf")

        vorher = self._toplevels()
        with mock.patch.object(self.haupt.PS5ConverterGUI, "_ampr_gen_automatik", attrappe):
            self.app._show_ampr_neue_methode()
            for _ in range(60):
                _WURZEL.update()
                if laeufe:
                    break
            import time
            time.sleep(0.2)
        s = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
        self.assertEqual([(sm_gen.NEU, self.app.root)], laeufe, "Der Lauf startet mit dem Hauptfenster als Besitzer.")
        self.assertEqual("pack", s.ablauf.winfo_manager())
        self.assertEqual("", s.auswahl.winfo_manager())
        # Meldungen des Arbeitsfadens laufen ueber die Hauptschleife (im Test gibt es keine); das Feld selbst:
        s.protokoll("[Test] Zeile")
        self.assertIn("[Test] Zeile", s.feld.get("1.0", "end"))
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein Fenster.")
        s.zeigen_auswahl()
        self.assertEqual("pack", s.auswahl.winfo_manager())
        self.assertEqual("", s.ablauf.winfo_manager())

    def test_der_weg_der_ablage_traegt_einen_haken(self) -> None:
        self.app._show_ampr_auswahl()
        s = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
        aktuell = self.app._ampr_ablage_wahl()
        self.assertTrue(s.wegknoepfe[aktuell].cget("text").startswith("✓"))
        for kennung, knopf in s.wegknoepfe.items():
            if kennung != aktuell:
                self.assertFalse(knopf.cget("text").startswith("✓"))

    def test_die_ansicht_konsole_nimmt_die_seite_weg(self) -> None:
        self.app._show_ampr_auswahl()
        self.app._ansicht_setzen("konsole")
        try:
            self.assertFalse(self.app._ampr_seite_sichtbar)
            s = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
            self.assertEqual("", s.rahmen.winfo_manager())
        finally:
            self.app._ansicht_setzen("umwandeln")


if __name__ == "__main__":
    unittest.main()
