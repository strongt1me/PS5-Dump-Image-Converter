# -*- coding: utf-8 -*-
"""Die gezeichneten Teile der Bibliothek - Farben, Bilder und Rechenregeln, ohne Tk (03.10.2026).

Der Nutzer schickte zwei Entwurfsbilder: Die Bibliothek soll aus Karten mit
Titelbild, Plaketten, Chips und allen Knoepfen bestehen, ohne Detailspalte
rechts. ``ps5_validator.utils.bibliothek_zeichnen`` zeichnet, was Tk nicht kann
(runde Ecken, Verlauf, Schein), und rechnet das Raster. Bewacht wird hier:

* Farben: in jedem der vier Designs lesbar (Chip-Texte mindestens 4,5 : 1 - bei
  Metallisch lagen sie vor der Korrektur bei 3,3), ein Zustand sieht anders aus
  als der andere, ein gesperrter Knopf hat keinen Schein.
* Bilder: durchsichtige Ecken, Rand innen, Verlauf von links nach rechts, Titelbild
  formatfuellend und nur oben rund, Schein unter dem Akzentknopf.
* Raster: Spaltenzahl, Umbruch von Titel und Chips, die Aufteilung einer Karte.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("bibliothek_zeichnen")

from PIL import Image                                       # noqa: E402

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek_zeichnen as z    # noqa: E402

THEMEN = APP.PS5ConverterGUI._THEMES


def _messen(text: str) -> int:
    """Zehn Pixel je Zeichen - Rechenregeln brauchen keine Schrift."""
    return len(text) * 10


class FarbenTests(unittest.TestCase):

    def test_hex_und_rgb_rundreise(self) -> None:
        self.assertEqual((46, 107, 230), z.hex_zu_rgb("#2E6BE6"))
        self.assertEqual("#2e6be6", z.rgb_zu_hex((46, 107, 230)))
        self.assertEqual("#ffffff", z.rgb_zu_hex((300, 255.4, 999)), "Werte werden begrenzt.")
        self.assertEqual("#000000", z.rgb_zu_hex((-5, -1, 0)))

    def test_kurzform_und_unsinn(self) -> None:
        self.assertEqual((255, 0, 0), z.hex_zu_rgb("#f00"))
        for unsinn in ("", "rot", "#12", None, "#gggggg"):
            with self.subTest(unsinn=unsinn):
                self.assertEqual((0, 0, 0), z.hex_zu_rgb(unsinn))

    def test_mischen_endpunkte_und_mitte(self) -> None:
        self.assertEqual("#102030", z.mischen("#102030", "#ffffff", 0))
        self.assertEqual("#ffffff", z.mischen("#102030", "#ffffff", 1))
        self.assertEqual("#808080", z.mischen("#000000", "#ffffff", 0.5))
        self.assertEqual("#000000", z.mischen("#000000", "#ffffff", -3), "Anteil wird begrenzt.")
        self.assertEqual("#ffffff", z.mischen("#000000", "#ffffff", 7))

    def test_der_farbton_dreht_blau_nach_violett(self) -> None:
        """Das Ende des Verlaufs von "Starten": aus dem Blau eines Designs wird Violett."""
        import colorsys
        blau = "#2E6BE6"
        violett = z.farbton_verschieben(blau, 32.0)
        h0 = colorsys.rgb_to_hsv(*(v / 255 for v in z.hex_zu_rgb(blau)))[0] * 360
        h1 = colorsys.rgb_to_hsv(*(v / 255 for v in z.hex_zu_rgb(violett)))[0] * 360
        self.assertAlmostEqual(32.0, (h1 - h0) % 360, delta=3.0)
        self.assertEqual(blau.lower(), z.farbton_verschieben(blau, 0.0).lower())
        self.assertEqual(blau.lower(), z.farbton_verschieben(blau, 360.0).lower())

    def test_kontrastfarbe(self) -> None:
        self.assertEqual("#ffffff", z.kontrastfarbe("#101010"))
        self.assertEqual("#ffffff", z.kontrastfarbe("#2E6BE6"))
        self.assertEqual("#101418", z.kontrastfarbe("#f0f0f0"))

    def test_welches_design_dunkel_ist(self) -> None:
        for name, dunkel in (("dunkel", True), ("futuristisch", True), ("metallisch", True),
                             ("hell", False)):
            with self.subTest(design=name):
                self.assertEqual(dunkel, z.ist_dunkel(THEMEN[name]))

    def test_kontrastverhaeltnis_nach_wcag(self) -> None:
        self.assertAlmostEqual(21.0, z.kontrastverhaeltnis("#000000", "#ffffff"), places=1)
        self.assertAlmostEqual(1.0, z.kontrastverhaeltnis("#336699", "#336699"), places=3)
        self.assertEqual(z.kontrastverhaeltnis("#123456", "#fedcba"),
                         z.kontrastverhaeltnis("#fedcba", "#123456"), "Die Reihenfolge zaehlt nicht.")

    def test_lesbar_auf_zieht_die_flaeche_bis_zum_mindestwert(self) -> None:
        text, flaeche = "#9FB6CC", "#525b66"            # gemessen am Design Metallisch: 3,29 : 1
        self.assertLess(z.kontrastverhaeltnis(text, flaeche), 4.5)
        besser = z.lesbar_auf(text, flaeche, "#000000")
        self.assertGreaterEqual(z.kontrastverhaeltnis(text, besser), 4.5)
        self.assertEqual(flaeche, z.lesbar_auf(text, flaeche, "#000000", mindest=1.0),
                         "Wer schon genug Kontrast hat, bleibt unveraendert.")
        # Bricht ab, wenn es nie reicht (Text und Flaeche beide fast schwarz)
        z.lesbar_auf("#000001", "#000000", "#000000", mindest=21.0)


class ChipFarbenTests(unittest.TestCase):

    ARTEN = ("neutral", "ampr", "playgo", "backport", "assetpack", "unbekannt")

    def test_jeder_chip_ist_in_jedem_design_lesbar(self) -> None:
        for name, palette in THEMEN.items():
            for art in self.ARTEN:
                f = z.chip_farben(palette, art)
                grund = f["fuellung"] or palette["bg_card"]
                with self.subTest(design=name, art=art):
                    self.assertGreaterEqual(z.kontrastverhaeltnis(f["text"], grund), 4.5)

    def test_unbekannt_ist_gestrichelt_und_ohne_fuellung(self) -> None:
        for name, palette in THEMEN.items():
            with self.subTest(design=name):
                f = z.chip_farben(palette, "unbekannt")
                self.assertTrue(f["gestrichelt"])
                self.assertEqual("", f["fuellung"])
                self.assertTrue(f["rand"])
                for art in self.ARTEN[:-1]:
                    self.assertFalse(z.chip_farben(palette, art)["gestrichelt"])

    def test_die_arten_sind_unterscheidbar(self) -> None:
        for name, palette in THEMEN.items():
            fuellungen = {art: z.chip_farben(palette, art)["fuellung"]
                          for art in ("neutral", "ampr", "playgo", "backport")}
            with self.subTest(design=name):
                self.assertEqual(4, len(set(fuellungen.values())), fuellungen)

    def test_ampr_und_assetpack_teilen_die_rolle_playgo_hat_seine_eigene(self) -> None:
        palette = THEMEN["dunkel"]
        self.assertEqual(z.chip_farben(palette, "ampr")["text"], z.chip_farben(palette, "assetpack")["text"])
        self.assertEqual(palette["fg_success"].lower(), z.chip_farben(palette, "playgo")["text"].lower())
        self.assertEqual(palette["fg_warning"].lower(), z.chip_farben(palette, "backport")["text"].lower())


class KnopfFarbenTests(unittest.TestCase):

    def test_die_zustaende_unterscheiden_sich(self) -> None:
        for name, palette in THEMEN.items():
            for stil in ("flaeche", "auswahl", "chip"):
                normal = z.knopf_farben(palette, stil, "normal")
                for zustand in ("hover", "gedrueckt", "gesperrt"):
                    with self.subTest(design=name, stil=stil, zustand=zustand):
                        self.assertNotEqual(normal["fuellung"], z.knopf_farben(palette, stil, zustand)["fuellung"])

    def test_normale_knoepfe_sind_lesbar(self) -> None:
        for name, palette in THEMEN.items():
            for stil in ("flaeche", "auswahl", "chip", "chip_an"):
                f = z.knopf_farben(palette, stil, "normal")
                with self.subTest(design=name, stil=stil):
                    self.assertGreaterEqual(z.kontrastverhaeltnis(f["text"], f["fuellung"]), 4.5)
            f = z.knopf_farben(palette, "akzent", "normal")
            mitte = z.mischen(f["links"], f["rechts"], 0.5)
            with self.subTest(design=name, stil="akzent"):
                self.assertGreaterEqual(z.kontrastverhaeltnis(f["text"], mitte), 4.5)

    def test_hover_und_druck_bleiben_lesbar(self) -> None:
        """Nicht so streng wie im Ruhezustand (grosse, fette Schrift): mindestens 3 : 1."""
        for name, palette in THEMEN.items():
            for stil in ("flaeche", "auswahl", "chip", "chip_an"):
                for zustand in ("hover", "gedrueckt"):
                    f = z.knopf_farben(palette, stil, zustand)
                    with self.subTest(design=name, stil=stil, zustand=zustand):
                        self.assertGreaterEqual(z.kontrastverhaeltnis(f["text"], f["fuellung"]), 3.0)
            for zustand in ("hover", "gedrueckt"):
                f = z.knopf_farben(palette, "akzent", zustand)
                with self.subTest(design=name, stil="akzent", zustand=zustand):
                    self.assertGreaterEqual(z.kontrastverhaeltnis(f["text"], z.mischen(f["links"], f["rechts"], 0.5)), 3.0)

    def test_der_akzentknopf_hat_einen_verlauf_und_einen_schein(self) -> None:
        for name, palette in THEMEN.items():
            normal = z.knopf_farben(palette, "akzent", "normal")
            with self.subTest(design=name):
                self.assertNotEqual(normal["links"], normal["rechts"], "Ein Verlauf, keine Flaeche.")
                self.assertTrue(normal["glow"])
                self.assertTrue(z.knopf_farben(palette, "akzent", "hover")["glow"])
                for zustand in ("gedrueckt", "gesperrt"):
                    self.assertEqual("", z.knopf_farben(palette, "akzent", zustand)["glow"],
                                     "%s: kein Schein." % zustand)
                self.assertGreater(z.helligkeit(z.knopf_farben(palette, "akzent", "hover")["links"]),
                                   z.helligkeit(normal["links"]), "Hover hellt auf.")
                self.assertLess(z.helligkeit(z.knopf_farben(palette, "akzent", "gedrueckt")["links"]),
                                z.helligkeit(normal["links"]), "Druck dunkelt ab.")

    @staticmethod
    def _grund(farben: dict) -> str:
        """Die Flaeche hinter dem Text - bei einem Verlauf seine Mitte."""
        return farben.get("fuellung") or z.mischen(farben["links"], farben["rechts"], 0.5)

    def test_gesperrt_ist_gedaempft(self) -> None:
        for name, palette in THEMEN.items():
            for stil in ("akzent", "flaeche", "auswahl", "chip"):
                normal = z.knopf_farben(palette, stil, "normal")
                gesperrt = z.knopf_farben(palette, stil, "gesperrt")
                with self.subTest(design=name, stil=stil):
                    self.assertGreater(
                        z.kontrastverhaeltnis(normal["text"], self._grund(normal)),
                        z.kontrastverhaeltnis(gesperrt["text"], self._grund(gesperrt)),
                        "Gesperrt liest sich leiser als bereit.")

    def test_der_gewaehlte_chip_hebt_sich_vom_ungewaehlten_ab(self) -> None:
        for name, palette in THEMEN.items():
            an = z.knopf_farben(palette, "chip_an", "normal")
            aus = z.knopf_farben(palette, "chip", "normal")
            with self.subTest(design=name):
                self.assertNotEqual(an["fuellung"], aus["fuellung"])
                self.assertNotEqual(an["rand"], aus["rand"])


class BilderTests(unittest.TestCase):

    def test_rund_rechteck_hat_durchsichtige_ecken_und_fuellung(self) -> None:
        bild = z.rund_rechteck(100, 40, 10, "#ff0000")
        self.assertEqual((100, 40), bild.size)
        self.assertEqual("RGBA", bild.mode)
        self.assertEqual(0, bild.getpixel((0, 0))[3], "Die Ecke ist durchsichtig.")
        self.assertEqual(0, bild.getpixel((99, 39))[3])
        self.assertEqual((255, 0, 0, 255), bild.getpixel((50, 20)))
        self.assertEqual(255, bild.getpixel((50, 0))[3], "Die gerade Kante ist voll.")

    def test_der_rand_liegt_innen(self) -> None:
        bild = z.rund_rechteck(100, 40, 10, "#ff0000", "#00ff00", 1)
        kante = bild.getpixel((50, 0))
        self.assertGreater(kante[1], kante[0], "Oben mittig ist der Rand: gruen vor rot.")
        self.assertEqual((255, 0, 0, 255), bild.getpixel((50, 5)), "Innen bleibt die Fuellung.")
        ohne = z.rund_rechteck(100, 40, 10, "#ff0000")
        self.assertGreater(ohne.getpixel((50, 0))[0], 250, "Ohne Rand reicht die Fuellung bis zur Kante.")

    def test_nur_rand_laesst_die_mitte_frei(self) -> None:
        bild = z.rund_rechteck(100, 40, 10, "", "#00ff00", 2)
        self.assertEqual(0, bild.getpixel((50, 20))[3])
        self.assertGreater(bild.getpixel((50, 0))[3], 200)

    def test_der_radius_wird_auf_die_halbe_kante_begrenzt(self) -> None:
        bild = z.rund_rechteck(40, 20, 999, "#ffffff")           # ein Stadion statt Unsinn
        self.assertEqual(255, bild.getpixel((20, 10))[3])
        self.assertEqual(0, bild.getpixel((0, 0))[3])

    def test_gestrichelt_hat_striche_und_luecken(self) -> None:
        bild = z.rund_rechteck(120, 30, 12, "", "#ffffff", 1, gestrichelt=True)
        alphas = [bild.getpixel((x, 0))[3] for x in range(16, 104)]
        self.assertTrue(any(a > 120 for a in alphas), "Es gibt Striche.")
        self.assertTrue(any(a < 20 for a in alphas), "Und Luecken dazwischen.")
        durchgezogen = z.rund_rechteck(120, 30, 12, "", "#ffffff", 1)
        self.assertTrue(all(durchgezogen.getpixel((x, 0))[3] > 120 for x in range(16, 104)))

    def test_der_verlauf_geht_von_links_nach_rechts(self) -> None:
        bild = z.verlauf_rechteck(100, 30, 8, "#ff0000", "#0000ff")
        links, rechts = bild.getpixel((2, 15)), bild.getpixel((97, 15))
        self.assertGreater(links[0], 230)
        self.assertLess(links[2], 25)
        self.assertGreater(rechts[2], 230)
        self.assertLess(rechts[0], 25)
        self.assertEqual(0, bild.getpixel((0, 0))[3])

    def test_der_akzentknopf_mit_schein_ist_groesser_und_meldet_seinen_versatz(self) -> None:
        bild, (ox, oy) = z.akzent_knopf(100, 30, 8, "#2e6be6", "#7b5be6", "#2e6be6",
                                        glow_unschaerfe=6, glow_versatz=4)
        self.assertEqual(100 + 2 * ox, bild.width)
        self.assertGreater(bild.height, 30 + oy, "Unten ist Platz fuer den Schein.")
        self.assertEqual(0, bild.getpixel((0, 0))[3], "Weit aussen: nichts.")
        innen = bild.getpixel((ox + 50, oy + 15))
        self.assertEqual(255, innen[3], "Im Knopf selbst deckt der Verlauf.")
        unter = bild.getpixel((ox + 50, oy + 30 + 3))
        self.assertGreater(unter[3], 30, "Direkt unter dem Knopf scheint es.")
        self.assertLess(unter[3], 255)
        weit_unten = bild.getpixel((ox + 50, bild.height - 1))
        self.assertLess(weit_unten[3], unter[3], "Der Schein klingt nach unten ab.")

    def test_der_akzentknopf_ohne_schein_ist_so_gross_wie_der_knopf(self) -> None:
        bild, versatz = z.akzent_knopf(100, 30, 8, "#2e6be6", "#7b5be6", "")
        self.assertEqual((100, 30), bild.size)
        self.assertEqual((0, 0), versatz)

    def test_das_titelbild_wird_zugeschnitten_nicht_verzerrt_und_nur_oben_rund(self) -> None:
        quelle = Image.new("RGB", (300, 100), (0, 0, 255))
        for x in range(100, 200):                               # die Mitte gruen
            for y in range(100):
                quelle.putpixel((x, y), (0, 255, 0))
        bild = z.poster_bild(quelle, 60, 60, 12)
        self.assertEqual((60, 60), bild.size)
        mitte = bild.getpixel((30, 30))
        self.assertGreater(mitte[1], 200, "Die Mitte der Vorlage bleibt stehen.")
        self.assertEqual(0, bild.getpixel((0, 0))[3])
        self.assertEqual(0, bild.getpixel((59, 0))[3])
        self.assertEqual(255, bild.getpixel((0, 59))[3], "Unten bleibt es eckig - dort schliesst die Karte an.")
        self.assertEqual(255, bild.getpixel((59, 59))[3])

    def test_ein_hochformat_wird_ebenso_beschnitten(self) -> None:
        quelle = Image.new("RGB", (100, 300), (255, 0, 0))
        for y in range(100, 200):
            for x in range(100):
                quelle.putpixel((x, y), (255, 255, 0))
        bild = z.poster_bild(quelle, 50, 50, 8)
        self.assertGreater(bild.getpixel((25, 25))[1], 200)

    def test_ein_titelbild_mit_durchsichtigkeit_bleibt_durchsichtig(self) -> None:
        quelle = Image.new("RGBA", (50, 50), (255, 255, 255, 0))
        bild = z.poster_bild(quelle, 40, 40, 6)
        self.assertEqual(0, bild.getpixel((20, 20))[3])

    def test_die_maske_des_titelbilds_wird_je_groesse_nur_einmal_gebaut(self) -> None:
        """Jede Karte einer Bibliothek braucht dieselbe Maske; sie kostete ein Drittel der Zeit eines Titelbilds."""
        z._poster_maske.cache_clear()
        quelle = Image.new("RGB", (80, 80), (10, 200, 30))
        z.poster_bild(quelle, 64, 64, 10)
        z.poster_bild(quelle, 64, 64, 10)
        z.poster_bild(quelle, 64, 64, 12)
        info = z._poster_maske.cache_info()
        self.assertEqual((2, 1), (info.misses, info.hits), "Zwei Groessen gebaut, eine davon wiederverwendet.")

    def test_die_gemerkte_maske_aendert_sich_beim_benutzen_nicht(self) -> None:
        quelle = Image.new("RGB", (80, 80), (10, 200, 30))
        maske = z._poster_maske(64, 64, 10.0, z.UEBERABTASTUNG)
        vorher = maske.tobytes()
        erstes = z.poster_bild(quelle, 64, 64, 10)
        zweites = z.poster_bild(quelle, 64, 64, 10)
        self.assertEqual(vorher, maske.tobytes())
        self.assertEqual(erstes.tobytes(), zweites.tobytes(), "Zweimal dasselbe Bild.")

    def test_plakette_und_pfeil(self) -> None:
        pl = z.plakette(40, 20)
        self.assertEqual((40, 20), pl.size)
        self.assertEqual(205, pl.getpixel((20, 10))[3], "Halb durchsichtig, nicht deckend.")
        self.assertEqual(0, pl.getpixel((0, 0))[3])
        pfeil = z.chevron(14, "#ffffff")
        self.assertEqual((14, 14), pfeil.size)
        self.assertTrue(any(pfeil.getpixel((x, y))[3] > 100 for x in range(14) for y in range(14)))
        self.assertEqual(0, pfeil.getpixel((0, 0))[3])


class RasterRechnenTests(unittest.TestCase):

    def test_spaltenzahl_und_kartenbreite(self) -> None:
        self.assertEqual((5, 267), z.spalten_berechnen(1400, 250, 16, 0))
        self.assertEqual((3, 256), z.spalten_berechnen(800, 250, 16, 0))
        self.assertEqual((1, 100), z.spalten_berechnen(100, 250, 16, 0),
                         "Schmaler als eine Karte: eine Spalte, so breit wie die Flaeche.")
        self.assertEqual((1, 250), z.spalten_berechnen(0, 250, 16, 0))

    def test_die_karten_fuellen_die_breite(self) -> None:
        for breite in range(400, 2600, 37):
            spalten, karte = z.spalten_berechnen(breite, 250, 16, 0)
            with self.subTest(breite=breite):
                belegt = spalten * karte + (spalten - 1) * 16
                self.assertLessEqual(belegt, breite)
                self.assertGreater(belegt, breite - spalten, "Hoechstens die Rundung bleibt uebrig.")
                if spalten > 1:
                    self.assertGreaterEqual(karte, 250)

    def test_text_umbrechen(self) -> None:
        self.assertEqual(["Hallo Welt"], z.text_umbrechen("Hallo Welt", _messen, 200))
        self.assertEqual(["Assassin's", "Creed Shadows"],
                         z.text_umbrechen("Assassin's Creed Shadows", _messen, 130))
        self.assertEqual([], z.text_umbrechen("", _messen, 200))
        self.assertEqual([], z.text_umbrechen("   ", _messen, 200))
        self.assertEqual([], z.text_umbrechen("etwas", _messen, 0))
        self.assertEqual([], z.text_umbrechen("etwas", _messen, 100, max_zeilen=0))

    def test_was_nicht_passt_endet_auf_punkte(self) -> None:
        zeilen = z.text_umbrechen("Ein sehr langer Titel der nicht passt", _messen, 100, 2)
        self.assertEqual(["Ein sehr", "langer…"], zeilen)
        self.assertEqual(["Hello…"], z.text_umbrechen("Hello World Foo", _messen, 100, 1))
        for zeile in zeilen:
            self.assertLessEqual(_messen(zeile), 100)

    def test_ein_zu_langes_wort_wird_getrennt(self) -> None:
        zeilen = z.text_umbrechen("Donaudampfschifffahrtsgesellschaft", _messen, 100, 2)
        self.assertEqual(2, len(zeilen))
        self.assertEqual("Donaudampf", zeilen[0])
        self.assertTrue(zeilen[1].endswith("…"))
        for zeile in zeilen:
            self.assertLessEqual(_messen(zeile), 100)

    def test_der_umbruch_haelt_immer_die_breite_ein(self) -> None:
        texte = ("Kurz", "Zwei Woerter", "Ein etwas laengerer Titel mit vielen kurzen Woertern darin",
                 "Supercalifragilisticexpialidocious Edition", "A B C D E F G H I J K L M N O P")
        for text in texte:
            for breite in (60, 100, 130, 250):
                for zeilen_max in (1, 2, 3):
                    with self.subTest(text=text, breite=breite, zeilen=zeilen_max):
                        zeilen = z.text_umbrechen(text, _messen, breite, zeilen_max)
                        self.assertLessEqual(len(zeilen), zeilen_max)
                        self.assertTrue(all(_messen(zl) <= breite for zl in zeilen))

    def test_chips_verteilen(self) -> None:
        self.assertEqual(([[0, 1], [2]], 0), z.chips_verteilen([100, 80, 120], 300, 10, 2))
        self.assertEqual(([[0, 1, 2]], 0), z.chips_verteilen([100, 80, 120], 400, 10, 2))
        self.assertEqual(([[0, 1]], 1), z.chips_verteilen([100, 80, 120], 300, 10, 1),
                         "Was in keine Zeile mehr passt, wird gezaehlt.")
        self.assertEqual(([], 0), z.chips_verteilen([], 300, 10, 2))

    def test_ein_breiter_chip_steht_allein_statt_zu_fehlen(self) -> None:
        zeilen, ausgelassen = z.chips_verteilen([500, 60], 300, 10, 2)
        self.assertEqual([[0], [1]], zeilen)
        self.assertEqual(0, ausgelassen)

    def test_chips_gehen_nie_ueber_die_zeilen_hinaus(self) -> None:
        breiten = [90, 70, 110, 60, 130, 80]
        for verfuegbar in (150, 220, 300, 500):
            zeilen, ausgelassen = z.chips_verteilen(breiten, verfuegbar, 8, 2)
            with self.subTest(verfuegbar=verfuegbar):
                self.assertLessEqual(len(zeilen), 2)
                self.assertEqual(len(breiten), sum(len(zl) for zl in zeilen) + ausgelassen)
                for zeile in zeilen:
                    if len(zeile) > 1:
                        self.assertLessEqual(sum(breiten[i] for i in zeile) + 8 * (len(zeile) - 1), verfuegbar)
                gesehen = [i for zl in zeilen for i in zl]
                self.assertEqual(sorted(gesehen), gesehen, "Die Reihenfolge bleibt.")

    def test_passt_alles_gibt_es_keinen_rest_chip(self) -> None:
        for breiten, verfuegbar in (([100, 80, 120], 300), ([100, 80, 120], 400), ([], 300)):
            with self.subTest(breiten=breiten, verfuegbar=verfuegbar):
                self.assertEqual((z.chips_verteilen(breiten, verfuegbar, 10, 2)[0], 0),
                                 z.chips_mit_rest(breiten, lambda n: 30, verfuegbar, 10, 2))

    def test_was_nicht_passt_steht_als_rest_chip_da_statt_still_zu_fehlen(self) -> None:
        """Fuenf Marken in zwei Zeilen: Die letzten verschwanden ohne jeden Hinweis."""
        breiten = [100, 100, 100, 100, 100]
        zeilen, versteckt = z.chips_mit_rest(breiten, lambda n: 30, 220, 10, 2)
        gezeigt = [i for zeile in zeilen for i in zeile]
        self.assertEqual(len(breiten), gezeigt[-1], "Der Rest-Chip steht zuletzt (Nummer = Anzahl der Chips).")
        echte = [i for i in gezeigt if i < len(breiten)]
        self.assertEqual(list(range(len(echte))), echte, "Von vorn und in Reihenfolge - ohne Luecke.")
        self.assertEqual(len(breiten) - len(echte), versteckt, "Der Rest-Chip zaehlt genau die fehlenden.")
        self.assertGreater(versteckt, 0)
        self.assertLessEqual(len(zeilen), 2)
        for zeile in zeilen:
            if len(zeile) > 1:
                summe = sum((breiten + [30])[i] for i in zeile) + 10 * (len(zeile) - 1)
                self.assertLessEqual(summe, 220, "Auch mit dem Rest-Chip bleibt jede Zeile in der Karte.")

    def test_der_rest_chip_verdraengt_notfalls_einen_echten(self) -> None:
        """Zwei Zeilen zu je 210: Der letzte echte Chip muss dem "+N" weichen, damit es noch passt."""
        zeilen, versteckt = z.chips_mit_rest([100, 100, 100, 100, 100, 100], lambda n: 50, 210, 10, 2)
        echte = [i for zeile in zeilen for i in zeile if i < 6]
        self.assertEqual(3, len(echte), "Zeile 1: zwei Chips; Zeile 2: ein Chip plus der Rest-Chip (100+10+50).")
        self.assertEqual(3, versteckt)

    def test_der_rest_chip_rechnet_mit_seiner_eigenen_breite(self) -> None:
        """Ab zehn versteckten Chips ist "+N" breiter (zwei Ziffern) - das entscheidet, wie viele echte bleiben."""
        def _breite(n: int) -> int:
            return 30 if n < 10 else 95

        zeilen, versteckt = z.chips_mit_rest([60] * 15, _breite, 200, 8, 2)
        echte = [i for zeile in zeilen for i in zeile if i < 15]
        self.assertEqual([0, 1, 2, 3], echte, "Bei \"+10\" (breit) haetten fuenf Chips keinen Platz neben ihm.")
        self.assertEqual(11, versteckt)


class KartenMasseTests(unittest.TestCase):

    def test_die_aufteilung_bei_100_prozent(self) -> None:
        """Die Zahlen des Entwurfs (Karte 284 breit) - als Dokumentation und Wachter."""
        a = z.KartenMasse(faktor=1.0, titel_zeile=20, chip_zeile=24).aufteilen(284)
        self.assertEqual(284, a.breite)
        self.assertEqual(280, a.poster_hoehe, "Quadratisch, ohne den Rand.")
        self.assertEqual((16, 252), (a.innen_x, a.innen_breite))
        self.assertEqual(296, a.titel_y)
        self.assertEqual(40, a.titel_hoehe, "Platz fuer zwei Zeilen.")
        self.assertEqual(346, a.chips_y)
        self.assertEqual(54, a.chips_hoehe, "Zwei Chipzeilen samt Abstand.")
        self.assertEqual((412, 462, 514), (a.info_y, a.start_y, a.aktion_y))
        self.assertEqual(566, a.hoehe)

    def test_alle_bereiche_folgen_aufeinander_ohne_ueberlappung(self) -> None:
        for faktor in (1.0, 1.25, 1.5, 2.0, 3.0):
            for breite in (200, 284, 330, 480):
                m = z.KartenMasse(faktor=faktor, titel_zeile=int(20 * faktor), chip_zeile=int(24 * faktor))
                a = m.aufteilen(breite)
                with self.subTest(faktor=faktor, breite=breite):
                    self.assertLess(a.poster_hoehe, a.titel_y)
                    self.assertLessEqual(a.titel_y + a.titel_hoehe, a.chips_y)
                    self.assertLessEqual(a.chips_y + a.chips_hoehe, a.info_y)
                    self.assertLessEqual(a.info_y + a.knopf_hoehe, a.start_y)
                    self.assertLessEqual(a.start_y + a.start_hoehe, a.aktion_y)
                    self.assertEqual(a.aktion_y + a.aktion_hoehe + m.polster, a.hoehe)
                    self.assertEqual(breite - 2 * m.polster, a.innen_breite)

    def test_die_masse_folgen_der_skalierung(self) -> None:
        eins = z.KartenMasse(faktor=1.0)
        anderthalb = z.KartenMasse(faktor=1.5)
        self.assertEqual(24, anderthalb.polster)
        self.assertEqual(375, anderthalb.karte_min)
        self.assertEqual(round(eins.karte_min * 1.5), anderthalb.karte_min)
        self.assertEqual(0, eins.rand, "Die Karten stehen buendig mit der Kopfkarte.")
        self.assertEqual(16, eins.abstand)

    def test_der_kartenrand_hat_immer_platz_fuer_zwei_pixel(self) -> None:
        """Gewaehlt ist der Rand 2 Pixel breit - der Platz ist immer da, eine Auswahl verschiebt nichts."""
        for faktor in (0.5, 1.0, 1.25, 2.0):
            self.assertGreaterEqual(z.KartenMasse(faktor=faktor).randbreite, 2)

    def test_die_hoehe_haengt_nicht_vom_titel_oder_den_chips_ab(self) -> None:
        m = z.KartenMasse(faktor=1.25, titel_zeile=25, chip_zeile=30)
        self.assertEqual(m.aufteilen(330).hoehe, m.aufteilen(330).hoehe)
        # Die Hoehe ist eine Funktion der Breite und der gemessenen Zeilen - nichts anderes.
        self.assertGreater(m.aufteilen(400).hoehe, m.aufteilen(300).hoehe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
