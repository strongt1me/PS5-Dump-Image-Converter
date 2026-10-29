# -*- coding: utf-8 -*-
"""Hinweistext in leeren Pfadfeldern (``hinweisfeld``) und seine Texte je Aufgabe im Hauptprogramm."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import tkinter as tk  # noqa: E402
from tkinter import ttk  # noqa: E402

from ps5_validator.utils import hinweisfeld as hf  # noqa: E402
from ps5_validator.utils import i18n  # noqa: E402


class HinweisfeldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wurzel = tk._default_root or tk.Tk()
        cls.wurzel.withdraw()

    def setUp(self) -> None:
        self.var = tk.StringVar(master=self.wurzel)
        # Ein eigenes Fenster: In die gemeinsame Wurzel zu packen stoert Tests, die dort mit grid arbeiten.
        self.fenster = tk.Toplevel(self.wurzel)
        self.addCleanup(self.fenster.destroy)
        self.feld = ttk.Entry(self.fenster, textvariable=self.var)
        self.feld.pack()
        self.fenster.update_idletasks()
        self.text = "hierher ziehen"
        self.h = hf.Hinweisfeld(self.feld, self.var, lambda: self.text)

    def test_leeres_feld_zeigt_den_hinweis_ohne_den_inhalt_zu_beruehren(self) -> None:
        self.assertEqual("hierher ziehen", self.h.etikett.cget("text"))
        self.assertTrue(self.h.etikett.winfo_manager())
        self.assertEqual("", self.var.get())

    def test_ein_pfad_im_feld_verbirgt_den_hinweis(self) -> None:
        self.var.set("C:/Spiel")
        self.assertFalse(self.h.etikett.winfo_manager())
        self.var.set("")
        self.assertTrue(self.h.etikett.winfo_manager())

    def test_der_text_wird_beim_aktualisieren_nachgezogen(self) -> None:
        self.text = "anderer Text"
        self.h.aktualisieren()
        self.assertEqual("anderer Text", self.h.etikett.cget("text"))

    def test_ohne_text_gibt_es_keinen_hinweis(self) -> None:
        self.text = ""
        self.h.aktualisieren()
        self.assertFalse(self.h.etikett.winfo_manager())


class TexteTests(unittest.TestCase):
    def test_alle_hinweistexte_gibt_es_in_jeder_sprache_und_sagen_ziehen(self) -> None:
        for schluessel in ("main.hint_src_folder", "main.hint_src_file", "main.hint_src_any",
                           "main.hint_dest", "main.hint_temp"):
            for sprache in ("de", "en", "es", "it", "fr"):
                text = i18n.translate(sprache, schluessel, art=".ffpfsc")
                self.assertTrue(text and text != schluessel, (schluessel, sprache))
        self.assertIn("ziehen", i18n.translate("de", "main.hint_dest"))


if __name__ == "__main__":
    unittest.main()
