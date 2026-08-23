# -*- coding: utf-8 -*-
"""Der Drehknopf tritt an die Stelle der Worker-Spinbox.

Gewuenscht am 23.08.2026: Die winzigen Pfeilchen der Spinbox waren schwer zu
treffen und sahen zwischen den runden Bedienteilen fremd aus.

Ein Drehknopf hat einen bekannten Nachteil - man trifft einen bestimmten Wert
schlechter als mit einem Zahlenfeld. Deshalb pruefen diese Tests vor allem,
dass die genauen Wege erhalten bleiben: Mausrad, Pfeiltasten, Doppelklick auf
die Voreinstellung, und die Zahl gross in der Mitte.
"""
from __future__ import annotations

import math
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    # Vorhandene Wurzel weiterbenutzen: Je Prozess darf es nur eine geben.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "ohne Tk nicht messbar")
class DrehknopfTests(unittest.TestCase):
    """Gemessen am gezeichneten Knopf, nicht am Quelltext."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def _knopf(self, wert=4, von=1, bis=8, vorgabe=4):
        self.var = tk.IntVar(value=wert)
        self.gerufen = []
        knopf = self.haupt.Drehknopf(
            _WURZEL, variable=self.var, von=von, bis=bis, vorgabe=vorgabe,
            command=lambda: self.gerufen.append(self.var.get()))
        knopf.update_idletasks()
        return knopf

    # ── Die genauen Wege ────────────────────────────────────────────────
    def test_pfeiltasten_aendern_um_eins(self) -> None:
        k = self._knopf(4)
        k._verschieben(1)
        self.assertEqual(self.var.get(), 5)
        k._verschieben(-1)
        self.assertEqual(self.var.get(), 4)

    def test_grenzen_halten(self) -> None:
        """Ohne Anschlag liefe der Knopf ueber - eine Spinbox tut das nicht."""
        k = self._knopf(4, von=1, bis=8)
        for _ in range(20):
            k._verschieben(1)
        self.assertEqual(self.var.get(), 8)
        for _ in range(20):
            k._verschieben(-1)
        self.assertEqual(self.var.get(), 1)

    def test_doppelklick_setzt_auf_die_voreinstellung(self) -> None:
        k = self._knopf(8, vorgabe=4)
        k._auf_vorgabe()
        self.assertEqual(self.var.get(), 4)

    def test_rueckruf_meldet_jede_aenderung(self) -> None:
        k = self._knopf(4)
        k._verschieben(1)
        k._verschieben(1)
        self.assertEqual(self.gerufen, [5, 6])

    def test_kein_rueckruf_ohne_aenderung(self) -> None:
        """Am Anschlag darf nichts gemeldet werden - sonst speichert das
        Programm bei jedem weiteren Rasten denselben Wert neu."""
        k = self._knopf(8, bis=8)
        k._verschieben(1)
        self.assertEqual(self.gerufen, [])

    # ── Drehen ──────────────────────────────────────────────────────────
    def test_ziehen_bildet_den_ganzen_bereich_ab(self) -> None:
        """Anfang, Mitte und Ende des Bogens muessen erreichbar sein."""
        k = self._knopf(4, von=1, bis=8)
        d = k._durchmesser
        mitte = d / 2.0
        versatz = (k._breite - d) / 2.0
        for grad, erwartet in ((k._BOGEN_START, 1),
                               (k._BOGEN_START - k._BOGEN_WEITE / 2, 4),
                               (k._BOGEN_START - k._BOGEN_WEITE, 8)):
            with self.subTest(grad=grad):
                x = versatz + mitte + (mitte - 6) * math.cos(math.radians(grad))
                y = mitte - (mitte - 6) * math.sin(math.radians(grad))
                k._aus_zeigerstand(x, y)
                self.assertEqual(self.var.get(), erwartet)

    # ── Darstellung ─────────────────────────────────────────────────────
    def test_die_zahl_steht_in_der_mitte(self) -> None:
        """Ohne sie waere der Wert nur zu schaetzen - der Hauptvorwurf an
        Drehknoepfe."""
        k = self._knopf(6)
        texte = [k.itemcget(i, "text") for i in k.find_all()
                 if k.type(i) == "text"]
        self.assertIn("6", texte)

    def test_von_aussen_gesetzter_wert_zieht_nach(self) -> None:
        k = self._knopf(4)
        self.var.set(7)
        k.update_idletasks()
        texte = [k.itemcget(i, "text") for i in k.find_all()
                 if k.type(i) == "text"]
        self.assertIn("7", texte)

    def test_flaeche_darf_breiter_sein_als_der_kreis(self) -> None:
        """Sonst stoesst die Beschriftung an die des Nachbarn.

        Beim ersten Anlauf war die Flaeche so breit wie der Kreis hoch;
        "WORKER" ragte darueber hinaus und las sich mit "PRUEFUNG"
        zusammen als ein Wort.
        """
        k = self._knopf(4)
        k.durchmesser_setzen(37, breite=68)
        self.assertEqual(k.winfo_reqheight(), 37)
        self.assertEqual(k.winfo_reqwidth(), 68)

    def test_die_spinbox_ist_verschwunden(self) -> None:
        quelltext = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertNotIn("worker_spin", quelltext)
        self.assertNotIn("Perf.TSpinbox", quelltext)


if __name__ == "__main__":
    unittest.main(verbosity=2)
