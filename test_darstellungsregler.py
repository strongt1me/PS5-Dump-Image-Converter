"""Tests für die Regler in den Einstellungen (Durchsicht, Helligkeit, Kontrast).

Sieben Werte, die bis v1.9.0 fest verdrahtet waren, hängen jetzt an
Schiebereglern:

* wie stark das Hintergrundbild durch **Pfad-Karte**, **Knopfleiste** und
  **Status-Log** scheint,
* **Helligkeit** und **Kontrast** der beiden Hintergrundbilder.

Zwei Dinge sind dabei leicht zu übersehen und werden deshalb geprüft:

1. **Die Vorgaben müssen genau die alten Konstanten sein.** Wer nichts
   verstellt, darf keinen Unterschied sehen.
2. **Beim Lesen muss begrenzt werden, nicht nur beim Setzen.** In der
   Einstellungsdatei kann alles stehen; ein Wert außerhalb des Bereichs fiele
   sonst erst als schwarzes Bild oder als Ausnahme aus PIL auf.

Das Status-Log ist ein ``tk.Text`` und damit deckend – dort kann das Bild
nicht wirklich durchscheinen. Der Regler zieht stattdessen seine Flächenfarbe
zur Farbe des Bildes hin; auch das wird hier festgehalten, damit es später
niemand für einen Fehler hält.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PIL import Image, ImageStat

import PS5ImageConverter_Pro_FINAL_revised as haupt
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils.i18n import STRINGS


def _gui(**werte) -> PS5ConverterGUI:
    """Prüfling ohne Tk; die Regler kommen aus einer Attrappe."""
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gespeichert = dict(werte)
    g._load_setting = lambda schluessel, vorgabe=None: gespeichert.get(
        schluessel, vorgabe)
    g._save_setting = lambda schluessel, wert: gespeichert.__setitem__(
        schluessel, wert)
    g._gespeichert = gespeichert
    g._current_theme = "dunkel"
    g._COLORS = {"bg_card": "#18283D", "bg_main": "#0B1220",
                 "console_bg": "#09111B"}
    return g


def _mittel(img: "Image.Image") -> float:
    return sum(ImageStat.Stat(img).mean[:3]) / 3


#: Ein Bild mit Struktur - eine einfarbige Fläche zeigte weder bei Kontrast
#: noch bei Deckkraft einen Unterschied.
def _testbild(breite: int = 60, hoehe: int = 40) -> "Image.Image":
    img = Image.new("RGB", (breite, hoehe), "#202020")
    for x in range(breite):
        for y in range(hoehe):
            if (x // 6 + y // 6) % 2:
                img.putpixel((x, y), (200, 190, 170))
    return img


class VorgabenTests(unittest.TestCase):
    """Wer nichts verstellt, sieht den Stand von vorher."""

    def test_vorgaben_sind_die_alten_konstanten(self) -> None:
        self.assertEqual(haupt.REGLER_VORGABEN["karte_deckkraft"],
                         round(haupt.BG_CARD_IMAGE_OPACITY * 100))
        self.assertEqual(haupt.REGLER_VORGABEN["leiste_deckkraft"],
                         round((1.0 - haupt.ACTION_BAR_DECKKRAFT) * 100))
        self.assertEqual(haupt.REGLER_VORGABEN["protokoll_deckkraft"],
                         round((1.0 - haupt.CONSOLE_BG_DECKKRAFT) * 100))
        for schluessel in ("bg_helligkeit", "bg_kontrast",
                           "sidebar_helligkeit", "sidebar_kontrast"):
            with self.subTest(schluessel):
                self.assertEqual(haupt.REGLER_VORGABEN[schluessel], 100)

    def test_ohne_gespeicherten_wert_gilt_die_vorgabe(self) -> None:
        g = _gui()
        for schluessel, vorgabe in haupt.REGLER_VORGABEN.items():
            with self.subTest(schluessel):
                self.assertEqual(g._regler(schluessel), vorgabe)

    def test_jeder_regler_hat_einen_bereich(self) -> None:
        self.assertEqual(set(haupt.REGLER_VORGABEN),
                         set(haupt.REGLER_GRENZEN))
        for schluessel, (klein, gross) in haupt.REGLER_GRENZEN.items():
            with self.subTest(schluessel):
                self.assertLess(klein, gross)
                self.assertLessEqual(klein, haupt.REGLER_VORGABEN[schluessel])
                self.assertLessEqual(haupt.REGLER_VORGABEN[schluessel], gross)


class GrenzenTests(unittest.TestCase):
    """Begrenzt wird beim Lesen, nicht erst beim Setzen."""

    def test_zu_grosse_werte_werden_gekappt(self) -> None:
        g = _gui(karte_deckkraft=500, bg_helligkeit=9999)
        self.assertEqual(g._regler("karte_deckkraft"), 100)
        self.assertEqual(g._regler("bg_helligkeit"), 200)

    def test_zu_kleine_werte_ebenfalls(self) -> None:
        g = _gui(karte_deckkraft=-40, bg_kontrast=0)
        self.assertEqual(g._regler("karte_deckkraft"), 0)
        self.assertEqual(g._regler("bg_kontrast"), 20)

    def test_unsinn_faellt_auf_die_vorgabe_zurueck(self) -> None:
        for kaputt in ("", "viel", None, [1, 2]):
            with self.subTest(kaputt=kaputt):
                g = _gui(karte_deckkraft=kaputt)
                self.assertEqual(g._regler("karte_deckkraft"),
                                 haupt.REGLER_VORGABEN["karte_deckkraft"])

    def test_zahlen_als_text_gehen_auch(self) -> None:
        """Die Einstellungsdatei liefert je nach Weg Zahl oder Zeichenkette."""
        self.assertEqual(_gui(karte_deckkraft="75")._regler("karte_deckkraft"), 75)
        self.assertEqual(_gui(karte_deckkraft=75.4)._regler("karte_deckkraft"), 75)


class BildreglerTests(unittest.TestCase):
    """Helligkeit und Kontrast am Bild nachgemessen."""

    def test_hundert_prozent_laesst_das_bild_in_ruhe(self) -> None:
        g = _gui()
        img = _testbild()
        self.assertIs(g._bild_regler_anwenden(img, "bg_helligkeit", "bg_kontrast"),
                      img, "Bei 100/100 darf nicht gerechnet werden")

    def test_helligkeit_wirkt_in_beide_richtungen(self) -> None:
        img = _testbild()
        dunkel = _gui(bg_helligkeit=40)._bild_regler_anwenden(
            img, "bg_helligkeit", "bg_kontrast")
        hell = _gui(bg_helligkeit=180)._bild_regler_anwenden(
            img, "bg_helligkeit", "bg_kontrast")
        self.assertLess(_mittel(dunkel), _mittel(img))
        self.assertGreater(_mittel(hell), _mittel(img))

    def test_kontrast_veraendert_die_streuung(self) -> None:
        img = _testbild()

        def streuung(bild):
            return sum(ImageStat.Stat(bild).stddev[:3]) / 3

        flau = _gui(bg_kontrast=40)._bild_regler_anwenden(
            img, "bg_helligkeit", "bg_kontrast")
        hart = _gui(bg_kontrast=180)._bild_regler_anwenden(
            img, "bg_helligkeit", "bg_kontrast")
        self.assertLess(streuung(flau), streuung(img))
        self.assertGreater(streuung(hart), streuung(img))

    def test_seitenleiste_hat_ihr_eigenes_paar(self) -> None:
        """Der Regler des Hauptbilds darf die Seitenleiste nicht anfassen."""
        img = _testbild()
        g = _gui(bg_helligkeit=180)
        self.assertIs(
            g._bild_regler_anwenden(img, "sidebar_helligkeit", "sidebar_kontrast"),
            img, "Die Seitenleiste hat den Wert des Hauptbilds uebernommen")


class FlaechenTests(unittest.TestCase):
    """Die drei Flächen reagieren auf ihren jeweiligen Regler."""

    def test_karte_wird_mit_hoeherem_regler_bildlastiger(self) -> None:
        img = _testbild()
        ohne = _gui(karte_deckkraft=0)._blend_bg_image_for_card(img)
        voll = _gui(karte_deckkraft=100)._blend_bg_image_for_card(img)
        self.assertAlmostEqual(_mittel(ohne),
                               _mittel(Image.new("RGB", img.size, "#18283D")),
                               delta=1.0)
        self.assertAlmostEqual(_mittel(voll), _mittel(img), delta=1.0)

    def test_knopfleiste_ebenso(self) -> None:
        img = _testbild()
        ohne = _gui(leiste_deckkraft=0)._blend_bg_image_for_action_bar(img)
        voll = _gui(leiste_deckkraft=100)._blend_bg_image_for_action_bar(img)
        self.assertAlmostEqual(_mittel(ohne),
                               _mittel(Image.new("RGB", img.size, "#0B1220")),
                               delta=1.0)
        self.assertAlmostEqual(_mittel(voll), _mittel(img), delta=1.0)

    def test_helles_design_mischt_die_karte_schwaecher(self) -> None:
        """Sonst wirkt die weiße Karte bei gleichem Regler gräulich."""
        img = _testbild()
        dunkel = _gui(karte_deckkraft=100)
        hell = _gui(karte_deckkraft=100)
        hell._current_theme = "hell"
        # Bei gleichem Regler muss im hellen Design weniger Bild ankommen.
        abstand_dunkel = abs(_mittel(dunkel._blend_bg_image_for_card(img))
                             - _mittel(img))
        abstand_hell = abs(_mittel(hell._blend_bg_image_for_card(img))
                           - _mittel(img))
        self.assertGreater(abstand_hell, abstand_dunkel)

    def test_das_protokoll_bleibt_deckend(self) -> None:
        """Es ist ein Textfeld - dort wandert nur die Farbe, nicht das Bild.

        Festgehalten, damit niemand die schwächere Wirkung später für einen
        Fehler hält: Der Hinweistext im Einstellungsfenster sagt es auch.
        """
        for fassung in STRINGS["settings_dialog.regler_protokoll_hint"].values():
            self.assertTrue(fassung.strip())
        self.assertIn("Textfeld",
                      STRINGS["settings_dialog.regler_protokoll_hint"]["de"])


class UebernehmenTests(unittest.TestCase):
    """Was nach einem Reglerwechsel neu gezeichnet wird."""

    def _prueffling(self):
        g = _gui()
        g.gerufen: list[str] = []
        for name in ("_load_bg_image_cache", "_apply_card_tint_live",
                     "_refresh_bg_label", "_load_sidebar_bg_image_cache",
                     "_refresh_sidebar_bg_label"):
            setattr(g, name, (lambda n=name: g.gerufen.append(n)))
        return g

    def test_jeder_regler_hat_eine_wirkung(self) -> None:
        self.assertEqual(set(PS5ConverterGUI._REGLER_WIRKUNG),
                         set(haupt.REGLER_VORGABEN))

    def test_bildregler_laedt_das_bild_neu(self) -> None:
        g = self._prueffling()
        g._regler_uebernehmen("bg_helligkeit", 150)
        self.assertIn("_load_bg_image_cache", g.gerufen)
        self.assertIn("_refresh_bg_label", g.gerufen)
        self.assertEqual(g._regler("bg_helligkeit"), 150)

    def test_seitenleiste_ruehrt_das_hauptbild_nicht_an(self) -> None:
        g = self._prueffling()
        g._regler_uebernehmen("sidebar_kontrast", 120)
        self.assertIn("_load_sidebar_bg_image_cache", g.gerufen)
        self.assertNotIn("_load_bg_image_cache", g.gerufen,
                         "Das Hauptbild wurde unnoetig neu gerechnet")

    def test_protokoll_zieht_nur_die_toenung_nach(self) -> None:
        g = self._prueffling()
        g._regler_uebernehmen("protokoll_deckkraft", 60)
        self.assertEqual(g.gerufen, ["_apply_card_tint_live"])

    def test_uebernehmen_begrenzt_ebenfalls(self) -> None:
        g = self._prueffling()
        g._regler_uebernehmen("karte_deckkraft", 400)
        self.assertEqual(g._gespeichert["karte_deckkraft"], 100)


class VorschauTests(unittest.TestCase):
    """Die Miniaturansicht der Hintergrundbilder."""

    def test_fehlender_pfad_gibt_nichts_zurueck(self) -> None:
        g = _gui()
        self.assertIsNone(g._vorschaubild(""))
        self.assertIsNone(g._vorschaubild(str(PROJEKT / "gibtesnicht.png")))

    def test_hochformat_gilt_als_seitenleistenbild(self) -> None:
        """Sonst bekäme ein selbst gewähltes Bild die falschen Regler."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as ordner:
            hoch = os.path.join(ordner, "eigenes.png")
            Image.new("RGB", (40, 90), "#334455").save(hoch)
            quer = os.path.join(ordner, "anderes.png")
            Image.new("RGB", (90, 40), "#334455").save(quer)
            self.assertTrue(PS5ConverterGUI._ist_sidebar_bild(hoch))
            self.assertFalse(PS5ConverterGUI._ist_sidebar_bild(quer))

    def test_der_name_entscheidet_zuerst(self) -> None:
        self.assertTrue(PS5ConverterGUI._ist_sidebar_bild("sidebar_20_glas.png"))


class TexteTests(unittest.TestCase):
    """Alle neuen Texte müssen zweisprachig sein."""

    def test_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS if k.startswith("settings_dialog.regler")]
        self.assertGreaterEqual(len(schluessel), 12)
        for name in schluessel:
            with self.subTest(name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
