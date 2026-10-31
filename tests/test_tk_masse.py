"""Tk-Masse als Pixel lesen: gleiche Antworten unter Tk 8.6 und Tk 9."""
import tkinter as tk
import unittest

from ps5_validator.utils.tk_masse import cget_pixel, pixel, pixel_ganz

try:
    _WURZEL = tk.Tk()
    _WURZEL.withdraw()
except tk.TclError:  # pragma: no cover - ohne Anzeige
    _WURZEL = None


@unittest.skipIf(_WURZEL is None, "keine Tk-Anzeige")
class TkMasseTests(unittest.TestCase):
    def test_zahl_und_zahlentext_bleiben_unveraendert(self) -> None:
        self.assertEqual(140.0, pixel(_WURZEL, "140"))
        self.assertEqual(7, pixel_ganz(_WURZEL, 7))

    def test_vorgabe_in_bildschirmeinheiten_wird_zur_pixelzahl(self) -> None:
        leinwand = tk.Canvas(_WURZEL)  # Tk liefert hier "10c"
        self.addCleanup(leinwand.destroy)
        self.assertGreater(cget_pixel(leinwand, "width"), 100)
        self.assertEqual(round(_WURZEL.winfo_fpixels("2c")),
                         pixel_ganz(_WURZEL, "2c"))

    def test_gesetzter_wert_und_leere_vorgabe(self) -> None:
        leinwand = tk.Canvas(_WURZEL, width=140)
        self.addCleanup(leinwand.destroy)
        self.assertEqual(140, cget_pixel(leinwand, "width"))
        self.assertEqual(5, pixel_ganz(_WURZEL, "", 5))
        self.assertEqual(9, pixel_ganz(_WURZEL, "unsinn", 9))


if __name__ == "__main__":
    unittest.main()
