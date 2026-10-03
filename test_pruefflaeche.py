# -*- coding: utf-8 -*-
"""Haelt die abgeschriebenen Randmasse von pruefflaeche.py gegen das Programm.

``pruefflaeche.RAND_BREIT`` und ``RAND_HOCH`` stehen im Programm in
``_fenster_auf_inhalt_wachsen`` als ``grenze_b = <Bildschirmbreite> - 40`` und
``grenze_h = <Bildschirmhoehe> - 80``. Bis zum 02.10.2026 stand dort
``winfo_screenwidth() - 40``; seit die gewaehlte Aufloesung die Groesse begrenzt
(Einstellungen, Abschnitt Anzeige), kommt die Breite aus
``_bildschirm_fuer_fenster()``. Der Rand ist derselbe geblieben, nur die Quelle
der Zahl nicht - deshalb wird jetzt die Zuweisung gelesen. pruefflaeche.py
kuendigte diese Pruefung seit seiner Entstehung an - die Datei gab es bis zum
17.09.2026 nicht, und kein Test nannte die beiden Namen (Befund T35).
Abgeschriebene Zahlen laufen sonst irgendwann still auseinander.

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

    def _abzug(self, ziel: str) -> list[int]:
        """Alle Zahlen N aus ``<ziel> = <irgendwas> - N`` in der Funktion."""
        werte: list[int] = []
        for funktion in self.funktionen:
            for k in ast.walk(funktion):
                if (isinstance(k, ast.Assign) and len(k.targets) == 1
                        and getattr(k.targets[0], "id", "") == ziel
                        and isinstance(k.value, ast.BinOp)
                        and isinstance(k.value.op, ast.Sub)
                        and isinstance(k.value.right, ast.Constant)
                        and isinstance(k.value.right.value, int)):
                    werte.append(k.value.right.value)
        return werte

    def test_die_funktion_gibt_es_genau_einmal(self) -> None:
        self.assertEqual(len(self.funktionen), 1,
                         "_fenster_auf_inhalt_wachsen fehlt oder steht doppelt.")

    def test_der_rand_in_der_breite_stimmt(self) -> None:
        werte = self._abzug("grenze_b")
        self.assertTrue(werte, "Die Breitengrenze ist nicht mehr zu finden.")
        self.assertEqual(set(werte), {pruefflaeche.RAND_BREIT})

    def test_der_rand_in_der_hoehe_stimmt(self) -> None:
        werte = self._abzug("grenze_h")
        self.assertTrue(werte, "Die Hoehengrenze ist nicht mehr zu finden.")
        self.assertEqual(set(werte), {pruefflaeche.RAND_HOCH})

    def test_die_grenze_kommt_vom_angenommenen_bildschirm(self) -> None:
        """Eine gewaehlte, kleinere Aufloesung muss die Grenze senken - nicht der rohe Bildschirm."""
        aufrufe = {getattr(k.func, "attr", "") for f in self.funktionen for k in ast.walk(f)
                   if isinstance(k, ast.Call)}
        self.assertIn("_bildschirm_fuer_fenster", aufrufe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
