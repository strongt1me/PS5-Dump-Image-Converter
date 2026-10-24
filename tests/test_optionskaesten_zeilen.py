# -*- coding: utf-8 -*-
"""Die Optionskaesten unter der Pfad-Karte duerfen sich keine Gitterzeile teilen (23.10.2026).

Meldung des Anwenders: Nach dem Lauf kam keine Frage, ob das Ergebnis an die PS5 gesendet werden soll. Der Haken
"Ergebnis nach erfolgreichem Abschluss an PS5 senden" lag in Zeile 13 - genau wie "Dump-Ordner im Arbeitsordner" - und
war von diesem verdeckt. Die Funktion war da, nur nicht zu sehen.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

HAUPT = Path(__file__).resolve().parent.parent / "PS5ImageConverter_Pro_FINAL_revised.py"
KAESTEN = ("shutdown_check", "senden_check", "dump_ordner_check", "arbeitskopie_check")


class ZeilenTests(unittest.TestCase):
    def test_jeder_haken_hat_eine_eigene_zeile(self) -> None:
        text = HAUPT.read_text(encoding="utf-8")
        zeilen: dict[str, int] = {}
        for name in KAESTEN:
            treffer = re.findall(r"self\.%s\.grid\(row=(\d+)," % name, text)
            self.assertEqual(1, len(treffer), name)
            zeilen[name] = int(treffer[0])
        self.assertEqual(len(KAESTEN), len(set(zeilen.values())), zeilen)

    def test_die_reihenfolge_bleibt(self) -> None:
        text = HAUPT.read_text(encoding="utf-8")
        reihe = [int(re.findall(r"self\.%s\.grid\(row=(\d+)," % n, text)[0]) for n in KAESTEN]
        self.assertEqual(sorted(reihe), reihe)


if __name__ == "__main__":
    unittest.main()
