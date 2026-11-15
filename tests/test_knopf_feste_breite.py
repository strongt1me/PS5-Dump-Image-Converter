# -*- coding: utf-8 -*-
"""Ein runder Knopf mit fester Breite bleibt breit genug fuer seine Beschriftung.

Gefunden am 15.11.2026 beim Durchmessen aller Seiten in allen fuenf Sprachen (125 %): In der franzoesischen
Oberflaeche ist "Choisir les sources" 159 px breit, der Knopf aber fest 150 px - die Beschriftung wurde an beiden Enden
abgeschnitten. Spanisch "Carpeta de dump" stand mit 150 px genau auf dem Rand, franzoesisch "Choisir le dossier" mit
3 px Luft. An der deutschen, englischen und italienischen Oberflaeche bleibt **kein** Knopf hinter seiner festen Breite
zurueck (gemessen bei 125 % und 200 %), dort aendert sich also nichts.

Die feste Breite bleibt das Mass des Aufrufers; sie waechst nur, wenn die Beschriftung samt Luft nicht hineinpasst, und
geht beim Sprachwechsel auf kuerzeren Text wieder zurueck.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

SCHRIFT = (APP.UI_SCHRIFT, APP.pt(9))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FesteBreiteTests(unittest.TestCase):

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)

    def _knopf(self, text: str, breite: int = 150, **optionen) -> "APP.RoundedButton":
        knopf = APP.RoundedButton(self.top, text=text, font=SCHRIFT, width=breite, height=44, **optionen)
        knopf.pack()
        self.top.update()
        return knopf

    def _text(self, knopf) -> int:
        return knopf._textbreite()

    def test_kurzer_text_bleibt_beim_mass_des_aufrufers(self) -> None:
        knopf = self._knopf("Ordner wählen")
        self.assertEqual(APP.knopfmass(150, self.top), knopf.winfo_reqwidth())

    def test_langer_text_macht_den_knopf_breiter(self) -> None:
        text = "Choisir les sources de la conversion"
        knopf = self._knopf(text)
        luft = 2 * APP.knopfmass(APP.RoundedButton._TEXT_RAND_MIN, self.top)
        self.assertGreater(self._text(knopf) + luft, APP.knopfmass(150, self.top), "Voraussetzung des Tests")
        self.assertEqual(self._text(knopf) + luft, knopf.winfo_reqwidth())

    def test_die_beschriftung_hat_immer_luft_am_rand(self) -> None:
        for text in ("Choisir les sources", "Carpeta de dump", "Choisir le dossier", "x", "Ordner wählen"):
            with self.subTest(text=text):
                knopf = self._knopf(text)
                self.assertGreaterEqual(knopf.winfo_reqwidth(), self._text(knopf) + 2 * APP.RoundedButton._TEXT_LUFT_X + 8)

    def test_sprachwechsel_nimmt_die_breite_wieder_zurueck(self) -> None:
        knopf = self._knopf("Choisir les sources de la conversion")
        breit = knopf.winfo_reqwidth()
        knopf.configure(text="Quellen wählen")
        self.top.update()
        self.assertLess(knopf.winfo_reqwidth(), breit)
        self.assertEqual(APP.knopfmass(150, self.top), knopf.winfo_reqwidth())

    def test_spaeter_gesetzte_breite_ist_das_neue_mass(self) -> None:
        knopf = self._knopf("Quellen wählen")
        knopf.configure(width=300)
        self.top.update()
        self.assertEqual(300, knopf.winfo_reqwidth())

    def test_knopf_ohne_feste_breite_bleibt_unberuehrt(self) -> None:
        knopf = APP.RoundedButton(self.top, text="Choisir les sources de la conversion", font=SCHRIFT, height=44)
        self.assertEqual(0, knopf._feste_breite)
        knopf.pack()
        self.top.update()          # darf nicht werfen; die Breite macht der Aufrufer (Raster, fill)

    def test_knopf_mit_breite_nach_text_bleibt_unberuehrt(self) -> None:
        knopf = APP.RoundedButton(self.top, text="Choisir les sources", font=SCHRIFT, height=44, breite_nach_text=True)
        self.assertEqual(0, knopf._feste_breite)


class QuelltextTests(unittest.TestCase):
    def test_init_und_configure_sichern_die_breite(self) -> None:
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "PS5ImageConverter_Pro_FINAL_revised.py"), encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertEqual(2, quelle.count("self._breite_sichern()"), "__init__ und configure (Text, Schrift, Breite)")
        self.assertIn("def _breite_sichern(self)", quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
