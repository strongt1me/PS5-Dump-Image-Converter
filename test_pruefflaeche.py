# -*- coding: utf-8 -*-
"""Haelt die abgeschriebenen Randmasse von pruefflaeche.py gegen das Programm.

``pruefflaeche.RAND_BREIT`` und ``RAND_HOCH`` stehen im Programm in
``_fenster_auf_inhalt_wachsen`` als ``winfo_screenwidth() - 40`` und
``winfo_screenheight() - 80``. pruefflaeche.py kuendigte diese Pruefung seit
seiner Entstehung an - die Datei gab es bis zum 17.09.2026 nicht, und kein
Test nannte die beiden Namen (Befund T35). Abgeschriebene Zahlen laufen sonst
irgendwann still auseinander.

Gelesen wird ueber den Syntaxbaum, nicht ueber eine Textsuche: Die Stelle
darf umformatiert werden, ohne dass die Pruefung stirbt.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefflaeche  # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class RandmasseTests(unittest.TestCase):
    """Die Grenzen, bis zu denen ein Fenster mit seinem Inhalt waechst."""

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        funktionen = [k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_fenster_auf_inhalt_wachsen"]
        cls.funktionen = funktionen

    def _abzug(self, methode: str) -> list[int]:
        """Alle Zahlen N aus ``<irgendwas>.<methode>() - N`` in der Funktion."""
        werte: list[int] = []
        for funktion in self.funktionen:
            for k in ast.walk(funktion):
                if (isinstance(k, ast.BinOp) and isinstance(k.op, ast.Sub)
                        and isinstance(k.left, ast.Call)
                        and getattr(k.left.func, "attr", "") == methode
                        and isinstance(k.right, ast.Constant)
                        and isinstance(k.right.value, int)):
                    werte.append(k.right.value)
        return werte

    def test_die_funktion_gibt_es_genau_einmal(self) -> None:
        self.assertEqual(len(self.funktionen), 1,
                         "_fenster_auf_inhalt_wachsen fehlt oder steht doppelt.")

    def test_der_rand_in_der_breite_stimmt(self) -> None:
        werte = self._abzug("winfo_screenwidth")
        self.assertTrue(werte, "Die Breitengrenze ist nicht mehr zu finden.")
        self.assertEqual(set(werte), {pruefflaeche.RAND_BREIT})

    def test_der_rand_in_der_hoehe_stimmt(self) -> None:
        werte = self._abzug("winfo_screenheight")
        self.assertTrue(werte, "Die Hoehengrenze ist nicht mehr zu finden.")
        self.assertEqual(set(werte), {pruefflaeche.RAND_HOCH})


if __name__ == "__main__":
    unittest.main(verbosity=2)
