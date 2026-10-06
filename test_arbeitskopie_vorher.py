# -*- coding: utf-8 -*-
"""Kaestchen "Dump-Ordner: Arbeitskopie vorher anlegen" (Nutzer 06.10.2026).

Angehakt: Vor einem Einbau in einen vorhandenen Dump-Ordner entsteht ohne Rueckfrage eine Kopie bzw. Sicherung,
das Original bleibt unveraendert. Nicht angehakt: Es wird wie bisher gefragt. Gelesen wird die gespeicherte
Einstellung - der Aufgabenfaden darf keine Tk-Variable lesen.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")


def _gui(an: bool):
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui._load_setting = lambda schluessel, vorgabe=None: an if schluessel == "arbeitskopie_vorher" else vorgabe
    gui.zeilen = []
    gui._append_to_log = gui.zeilen.append
    return gui


class EinbauWahlTests(unittest.TestCase):
    def test_angehakt_ohne_frage_die_sicherung(self) -> None:
        gui = _gui(True)
        with mock.patch.object(gui, "_im_hauptfaden") as frage:
            self.assertEqual("sicherung", gui._ordner_einbau_wahl("D:/Spiel", "E:/Ziel/Spiel"))
        frage.assert_not_called()
        self.assertIn("ohne Rückfrage", "".join(gui.zeilen))

    def test_nicht_angehakt_wird_gefragt(self) -> None:
        gui = _gui(False)
        with mock.patch.object(gui, "_im_hauptfaden", return_value="sicherung") as frage:
            self.assertEqual("sicherung", gui._ordner_einbau_wahl("D:/Spiel", "E:/Ziel/Spiel"))
        frage.assert_called_once()


class ArbeitskopieTests(unittest.TestCase):
    def test_die_rueckfrage_wird_bei_angehakt_uebersprungen(self) -> None:
        """Im Weg zur Arbeitskopie steht die Abfrage vor der Rueckfrage (Textsuche im Syntaxbaum)."""
        baum = ast.parse(QUELLE)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef) and "dialog.title.integration_workcopy" in ast.unparse(k))
        text = ast.unparse(methode)
        self.assertLess(text.index("self._arbeitskopie_vorher_aktiv()"),
                        text.index("dialog.title.integration_workcopy"))

    def test_gelesen_wird_die_einstellung(self) -> None:
        self.assertTrue(_gui(True)._arbeitskopie_vorher_aktiv())
        self.assertFalse(_gui(False)._arbeitskopie_vorher_aktiv())

    def test_texte_zweisprachig(self) -> None:
        for schluessel in ("main.arbeitskopie_vorher", "arbeitskopie.log_an", "arbeitskopie.log_aus",
                           "main.integrate_arbeitskopie_automatisch", "ordner_einbau.log_automatisch_sicherung"):
            with self.subTest(schluessel=schluessel):
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])

    def test_das_kaestchen_steht_unter_dem_dump_ordner_kaestchen(self) -> None:
        self.assertLess(QUELLE.index("self.dump_ordner_check.grid(row=13"),
                        QUELLE.index("self.arbeitskopie_check.grid(row=14"))


if __name__ == "__main__":
    unittest.main()
