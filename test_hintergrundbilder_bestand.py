# -*- coding: utf-8 -*-
"""Wächter für die mitgelieferten Hintergrundbilder und ihre Verwendung.

Am 02.10.2026 wurden alle 40 mitgelieferten Bilder durch andere ersetzt: 20
für den Hauptbereich (1920x1200) und 20 für die Seitenleiste (500x1200),
benannt nach dem Schema ``bg_NN_<name>`` und ``sidebar_NN_<name>``. Was hier
steht, sind die Zusicherungen, an denen die Auslieferung hängt:

* Der Bestand folgt dem Schema und hat genau die Maße, auf die Handbuch und
  Darstellungsdiagnose gerechnet sind - ein Bild in anderer Größe würde auf
  einem 1920x1200-Schirm hochgerechnet (die alten Seitenleisten um 54 %).
* Eine gespeicherte Wahl, die auf ein entfallenes mitgeliefertes Bild zeigt,
  fällt auf die Vorgabe zurück statt auf nichts. Gemessen an der
  Einstellungsdatei des Entwicklers: ``bundled:sidebar_20_glass-panels.png``
  hätte die Seitenleiste ohne Bild gelassen.
* Die Vorgaben sind dunkel. Die helle Schrift der dunklen Designs steht direkt
  auf dem Bild; auf einem hellen verschwindet sie. Gemessen an Aufnahmen des
  Hauptfensters: 34 und 103 von 255 lesen sich gut, 120/122 grenzwertig,
  202/206 gar nicht (siehe ``anzeige_diagnose.BILD_HELL_HINWEIS``).
* Die Prüfung ``pruefe_bildhelligkeit`` und der Hinweis im Einstellungsfenster
  melden das, statt es dem Anwender zu überlassen.
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as mod  # noqa: E402
from ps5_validator.utils import anzeige_diagnose as ad  # noqa: E402

ORDNER = PROJEKT / "Hintergrundbilder"
SCHEMA = re.compile(r"^(bg|sidebar)_(\d{2})_([a-z0-9]+(?:-[a-z0-9]+)*)\.png$")
GUI = mod.PS5ConverterGUI

#: Was der Bestand an Platte höchstens belegen darf. Die 40 Bilder liegen
#: (nach verlustfreier Neukodierung) bei rund 37 MB; die vorigen waren 44 MB.
#: Jede Datei steckt in jeder Programmdatei - die Grenze hält die EXE schlank.
BESTAND_GRENZE_BYTES = 50 * 1024 * 1024


def _gui(design: str = "dunkel", **einstellungen):
    """Eine Oberfläche ohne Fenster, nur mit dem, was die Helligkeitsregeln brauchen."""
    gui = GUI.__new__(GUI)
    gui._current_theme = design
    gui._load_setting = lambda schluessel, vorgabe: einstellungen.get(schluessel, vorgabe)
    return gui


def _bild_speichern(ordner: str, name: str, farbe, groesse=(64, 40)) -> str:
    pfad = os.path.join(ordner, name)
    Image.new("RGB", groesse, farbe).save(pfad)
    return pfad


class BestandTests(unittest.TestCase):
    """Der mitgelieferte Ordner ``Hintergrundbilder``."""

    @classmethod
    def setUpClass(cls):
        assert ORDNER.is_dir(), "Ordner Hintergrundbilder fehlt"
        cls.dateien = sorted(p for p in ORDNER.iterdir() if p.is_file())
        cls.haupt = [p for p in cls.dateien if p.name.startswith("bg_")]
        cls.seite = [p for p in cls.dateien if p.name.startswith("sidebar_")]

    def test_jede_datei_folgt_dem_schema(self):
        for pfad in self.dateien:
            with self.subTest(datei=pfad.name):
                self.assertRegex(pfad.name, SCHEMA)

    def test_beide_reihen_sind_da(self):
        self.assertGreaterEqual(len(self.haupt), 20)
        self.assertGreaterEqual(len(self.seite), 20)

    def test_masse_stimmen(self):
        """1920x1200 für den Hauptbereich, 500x1200 für die Seitenleiste."""
        for pfad in self.haupt:
            with self.subTest(datei=pfad.name), Image.open(pfad) as bild:
                self.assertEqual(bild.size, (1920, 1200))
        for pfad in self.seite:
            with self.subTest(datei=pfad.name), Image.open(pfad) as bild:
                self.assertEqual(bild.size, (500, 1200))

    def test_nur_rgb_ohne_alphakanal(self):
        """Der Lader macht ``convert("RGB")`` und verwirft den Alphakanal.

        Läge in einer Lieferung Durchsichtigkeit, schiene darunter beliebiges
        RGB durch. Die gelieferten Dateien trugen einen Alphakanal, der
        überall 255 war; er ist bei der Neukodierung entfallen (41 % kleiner,
        Pixel unverändert).
        """
        for pfad in self.dateien:
            with self.subTest(datei=pfad.name), Image.open(pfad) as bild:
                self.assertEqual(bild.mode, "RGB")

    def test_nummern_und_namen_sind_eindeutig(self):
        for reihe in (self.haupt, self.seite):
            treffer = [SCHEMA.match(p.name) for p in reihe]
            nummern = [int(t.group(2)) for t in treffer]
            namen = [t.group(3) for t in treffer]
            with self.subTest(vorsatz=treffer[0].group(1)):
                self.assertEqual(len(set(nummern)), len(nummern), "Nummer doppelt")
                self.assertEqual(len(set(namen)), len(namen), "Name doppelt")
                self.assertEqual(sorted(nummern), list(range(1, len(nummern) + 1)),
                                 "Nummern sollen lückenlos bei 01 beginnen")

    def test_paare_tragen_nummer_und_namen_gemeinsam(self):
        """Gleiche Nummer und gleicher Name heißt: gehört zusammen.

        Die zehn ruhigen Bilder (01-10) wurden als Paare erzeugt, vier weitere
        passen farblich (11-15); die übrigen fünf Haupt- und fünf Seitenbilder
        haben kein Gegenstück und tragen verschiedene Namen.
        """
        haupt = {SCHEMA.match(p.name).group(2): SCHEMA.match(p.name).group(3) for p in self.haupt}
        seite = {SCHEMA.match(p.name).group(2): SCHEMA.match(p.name).group(3) for p in self.seite}
        paare = sorted(n for n in haupt if seite.get(n) == haupt[n])
        self.assertEqual(paare, ["%02d" % i for i in range(1, 16)])
        for nummer in sorted(set(haupt) & set(seite) - set(paare)):
            with self.subTest(nummer=nummer):
                self.assertNotEqual(haupt[nummer], seite[nummer])

    def test_gesamtgroesse_haelt_den_rahmen(self):
        summe = sum(p.stat().st_size for p in self.dateien)
        self.assertLess(summe, BESTAND_GRENZE_BYTES,
                        "Der Bildbestand belegt %.1f MB - und steckt in jeder Programmdatei"
                        % (summe / 1048576))

    def test_handbuch_nennt_stueckzahl_und_masse(self):
        """Das Handbuch hat die Zahlen schon einmal 15 Releases lang nicht mitgeführt."""
        html = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        self.assertIn("(%d Stück)" % len(self.haupt), html)
        self.assertIn("(%d Stück)" % len(self.seite), html)
        self.assertIn("1920 × 1200", html)
        self.assertIn("500 × 1200", html)

    def _helligkeit(self, pfad: Path) -> float:
        with Image.open(pfad) as bild:
            return GUI._bild_helligkeit_messen(bild.convert("RGB"))

    def test_handbuch_nennt_die_hellen_bilder(self):
        """Welche Bilder hell sind, steht im Handbuch - gemessen, nicht geschätzt.

        Jedes Bild über ``BILD_HELL_HINWEIS`` muss dort genannt sein, jedes dort
        genannte muss die Schwelle auch wirklich überschreiten: oberhalb von
        ``BILD_HELL_WARNUNG`` (Schrift verschwindet) vor dem Wort "Grenzwertig",
        dazwischen dahinter.
        """
        html = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        anfang = html.index("Helle Bilder gehören zum Design Hell")
        kasten = html[anfang:html.index("</div>", anfang)]
        sehr, grenzwertig = kasten.split("Grenzwertig sind", 1)
        genannt_sehr = set(re.findall(r"<code>((?:bg|sidebar)_\d{2}_[a-z0-9-]+)</code>", sehr))
        genannt_grenz = set(re.findall(r"<code>((?:bg|sidebar)_\d{2}_[a-z0-9-]+)</code>", grenzwertig))
        gemessen_sehr, gemessen_grenz = set(), set()
        for pfad in self.dateien:
            hell = self._helligkeit(pfad)
            if hell > ad.BILD_HELL_WARNUNG:
                gemessen_sehr.add(pfad.stem)
            elif hell > ad.BILD_HELL_HINWEIS:
                gemessen_grenz.add(pfad.stem)
        self.assertEqual(genannt_sehr, gemessen_sehr, "sehr helle Bilder: Handbuch und Messung weichen ab")
        self.assertEqual(genannt_grenz, gemessen_grenz, "grenzwertige Bilder: Handbuch und Messung weichen ab")

    def test_liste_zeigt_je_art_nur_das_passende_format(self):
        haupt = [os.path.basename(p) for p in GUI._bundled_background_images("haupt")]
        seite = [os.path.basename(p) for p in GUI._bundled_background_images("sidebar")]
        self.assertEqual(haupt, [p.name for p in self.haupt])
        self.assertEqual(seite, [p.name for p in self.seite])


class VorgabeTests(unittest.TestCase):
    """Die beiden Vorgabebilder."""

    def _helligkeit(self, wert: str) -> float:
        pfad = GUI._decode_background_setting(wert)
        self.assertTrue(pfad, "nicht auflösbar: %s" % wert)
        with Image.open(pfad) as bild:
            return GUI._bild_helligkeit_messen(bild.convert("RGB"))

    def test_vorgaben_sind_dunkel(self):
        """Sonst wären die Beschriftungen ab dem ersten Start schwer zu lesen."""
        for wert in (mod.STANDARD_HINTERGRUND, mod.STANDARD_SIDEBAR_HINTERGRUND):
            with self.subTest(wert=wert):
                self.assertLess(self._helligkeit(wert), ad.BILD_HELL_HINWEIS)

    def test_vorgaben_sind_ein_paar(self):
        marke = GUI._BUNDLED_IMAGE_MARKER
        haupt = SCHEMA.match(mod.STANDARD_HINTERGRUND[len(marke):])
        seite = SCHEMA.match(mod.STANDARD_SIDEBAR_HINTERGRUND[len(marke):])
        self.assertEqual((haupt.group(2), haupt.group(3)), (seite.group(2), seite.group(3)))


class EntfallenesBildTests(unittest.TestCase):
    """Eine gespeicherte Wahl, die es nicht mehr gibt, fällt auf die Vorgabe zurück."""

    def _vorgabe(self, wert: str) -> str:
        return os.path.normcase(GUI._decode_background_setting(wert))

    def test_altes_hauptbild_wird_zur_hauptvorgabe(self):
        """Der alte Vorgabewert aus v1.9.56 und früher."""
        self.assertEqual(self._vorgabe("bundled:bg_19_ray-burst.png"),
                         self._vorgabe(mod.STANDARD_HINTERGRUND))

    def test_alte_seitenleiste_wird_zur_seitenvorgabe(self):
        """Genau der Wert, der in der Einstellungsdatei des Entwicklers stand."""
        ergebnis = self._vorgabe("bundled:sidebar_20_glass-panels.png")
        self.assertTrue(ergebnis)
        self.assertEqual(ergebnis, self._vorgabe(mod.STANDARD_SIDEBAR_HINTERGRUND))

    def test_vorhandenes_bild_bleibt_unberuehrt(self):
        haupt = [os.path.basename(p) for p in GUI._bundled_background_images("haupt")]
        wahl = haupt[-1]
        self.assertNotEqual("bundled:" + wahl, mod.STANDARD_HINTERGRUND)
        self.assertEqual(os.path.basename(self._vorgabe("bundled:" + wahl)), wahl)

    def test_fremder_name_bleibt_ohne_bild(self):
        """Ein Name außerhalb des Schemas ist weiterhin "kein Bild"."""
        self.assertEqual(GUI._decode_background_setting("bundled:gibtsnicht.png"), "")

    def test_abwahl_bleibt_abwahl(self):
        self.assertEqual(GUI._decode_background_setting(""), "")
        self.assertEqual(GUI._decode_background_setting("   "), "")

    def test_ohne_ordner_gibt_es_keinen_ersatz(self):
        self.assertEqual(GUI._ersatz_fuer_entfallenes_bild("bg_19_ray-burst.png", ""), "")

    def test_ersatz_richtet_sich_nach_dem_vorsatz(self):
        ordner = GUI._bundled_background_dir()
        haupt = GUI._ersatz_fuer_entfallenes_bild("bg_99_irgendwas.png", ordner)
        seite = GUI._ersatz_fuer_entfallenes_bild("sidebar_99_irgendwas.png", ordner)
        self.assertTrue(os.path.basename(haupt).startswith("bg_"))
        self.assertTrue(os.path.basename(seite).startswith("sidebar_"))


class HelligkeitTests(unittest.TestCase):
    """Wie hell ein Bild ist - und wann das im dunklen Design stört."""

    def test_messung_an_den_eckwerten(self):
        weiss = GUI._bild_helligkeit_messen(Image.new("RGB", (300, 200), (255, 255, 255)))
        schwarz = GUI._bild_helligkeit_messen(Image.new("RGB", (300, 200), (0, 0, 0)))
        self.assertAlmostEqual(weiss, 255.0, delta=0.5)
        self.assertAlmostEqual(schwarz, 0.0, delta=0.5)

    def test_gewichtung_wie_die_farbhelligkeit(self):
        """Grün wirkt heller als Blau - dieselben Gewichte wie ``_helligkeit``."""
        gruen = GUI._bild_helligkeit_messen(Image.new("RGB", (64, 64), (0, 255, 0)))
        blau = GUI._bild_helligkeit_messen(Image.new("RGB", (64, 64), (0, 0, 255)))
        self.assertAlmostEqual(gruen, GUI._helligkeit("#00ff00"), delta=1.0)
        self.assertAlmostEqual(blau, GUI._helligkeit("#0000ff"), delta=1.0)
        self.assertGreater(gruen, blau)

    def test_kein_bild_oder_unbrauchbares_gibt_none(self):
        self.assertIsNone(GUI._bild_helligkeit_messen(None))
        self.assertIsNone(GUI._bild_helligkeit_messen("kein Bild"))

    def test_datei_fehlt_oder_leer_gibt_none(self):
        gui = _gui()
        self.assertIsNone(gui._bild_helligkeit(""))
        self.assertIsNone(gui._bild_helligkeit(os.path.join(tempfile.gettempdir(), "gibtsnicht_xyz.png")))

    def test_helles_bild_im_dunklen_design(self):
        with tempfile.TemporaryDirectory() as ordner:
            hell = _bild_speichern(ordner, "hell.png", (230, 230, 230))
            dunkel = _bild_speichern(ordner, "dunkel.png", (20, 30, 50))
            for design in ("dunkel", "futuristisch", "metallisch"):
                with self.subTest(design=design):
                    gui = _gui(design)
                    self.assertTrue(gui._helles_bild_im_dunklen_design(hell, "haupt"))
                    self.assertFalse(gui._helles_bild_im_dunklen_design(dunkel, "haupt"))

    def test_im_hellen_design_ist_nichts_zu_melden(self):
        with tempfile.TemporaryDirectory() as ordner:
            hell = _bild_speichern(ordner, "hell.png", (230, 230, 230))
            self.assertFalse(_gui("hell")._helles_bild_im_dunklen_design(hell, "haupt"))

    def test_abgedunkeltes_bild_gilt_als_dunkel(self):
        """Wer ein helles Bild mit dem Regler abdunkelt, bekommt keinen Hinweis mehr."""
        with tempfile.TemporaryDirectory() as ordner:
            hell = _bild_speichern(ordner, "hell.png", (230, 230, 230))
            ohne = _gui("dunkel")
            mit = _gui("dunkel", bg_helligkeit=40)
            self.assertTrue(ohne._helles_bild_im_dunklen_design(hell, "haupt"))
            self.assertFalse(mit._helles_bild_im_dunklen_design(hell, "haupt"))
            # Der Regler der Seitenleiste ist ein anderer: Das Hauptbild-Paar fasst sie nicht an.
            self.assertTrue(mit._helles_bild_im_dunklen_design(hell, "sidebar"))

    def test_hinweis_wird_ein_und_ausgeblendet(self):
        class Etikett:
            def __init__(self):
                self.aufrufe = []

            def pack(self, **optionen):
                self.aufrufe.append(("pack", optionen))

            def pack_forget(self):
                self.aufrufe.append(("pack_forget", {}))

        with tempfile.TemporaryDirectory() as ordner:
            hell = _bild_speichern(ordner, "hell.png", (230, 230, 230))
            dunkel = _bild_speichern(ordner, "dunkel.png", (20, 30, 50))
            gui = _gui("dunkel")
            vorschau = object()
            etikett = Etikett()
            gui._hell_hinweis_zeigen(etikett, vorschau, hell, "haupt")
            gui._hell_hinweis_zeigen(etikett, vorschau, dunkel, "haupt")
            self.assertEqual([a[0] for a in etikett.aufrufe], ["pack", "pack_forget"])
            self.assertIs(etikett.aufrufe[0][1]["after"], vorschau)


class BildhelligkeitPruefungTests(unittest.TestCase):
    """``pruefe_bildhelligkeit`` mit den gemessenen Zahlen."""

    def test_gemessene_faelle(self):
        faelle = (
            (34.0, None),            # navy-curves: die Vorgabe
            (103.0, None),           # azure-veil: gut lesbar
            (120.0, ad.HINWEIS),     # sunset-silk: grenzwertig
            (122.0, ad.HINWEIS),     # mist-blue: grenzwertig
            (202.0, ad.WARNUNG),     # porcelain: Beschriftungen weg
            (206.0, ad.WARNUNG),     # ice-light
        )
        for hell, erwartet in faelle:
            with self.subTest(helligkeit=hell):
                befunde = ad.pruefe_bildhelligkeit({"Hintergrundbild": hell}, True)
                self.assertEqual([b.schwere for b in befunde], [erwartet] if erwartet else [])

    def test_grenzen_sind_strikt(self):
        self.assertEqual(ad.pruefe_bildhelligkeit({"x": ad.BILD_HELL_HINWEIS}, True), [])
        self.assertEqual([b.schwere for b in ad.pruefe_bildhelligkeit({"x": ad.BILD_HELL_WARNUNG}, True)],
                         [ad.HINWEIS])
        self.assertEqual([b.schwere for b in ad.pruefe_bildhelligkeit({"x": ad.BILD_HELL_WARNUNG + 0.1}, True)],
                         [ad.WARNUNG])

    def test_im_hellen_design_nie(self):
        self.assertEqual(ad.pruefe_bildhelligkeit({"Hintergrundbild": 230.0}, False), [])

    def test_fehlende_messung_meldet_nichts(self):
        self.assertEqual(ad.pruefe_bildhelligkeit({"Hintergrundbild": None, "Seitenleistenbild": None}, True), [])

    def test_jedes_bild_einzeln(self):
        befunde = ad.pruefe_bildhelligkeit({"Hintergrundbild": 30.0, "Seitenleistenbild": 214.0}, True)
        self.assertEqual([b.kennung for b in befunde], ["bild_zu_hell"])
        self.assertIn("Seitenleistenbild", befunde[0].text)

    def test_pruefe_alles_reicht_es_durch(self):
        warnung = ad.pruefe_alles(bildhelligkeit={"Hintergrundbild": 206.0}, dunkles_design=True)
        self.assertFalse(warnung.sauber)
        hinweis = ad.pruefe_alles(bildhelligkeit={"Hintergrundbild": 121.0}, dunkles_design=True)
        self.assertTrue(hinweis.sauber)       # ein Hinweis zählt nicht als Mangel
        self.assertEqual([b.schwere for b in hinweis.befunde], [ad.HINWEIS])
        hell = ad.pruefe_alles(bildhelligkeit={"Hintergrundbild": 206.0}, dunkles_design=False)
        self.assertEqual(hell.befunde, [])


class QuelltextTests(unittest.TestCase):
    """Dass Messung und Hinweis auch wirklich verdrahtet sind."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        cls.i18n = (PROJEKT / "ps5_validator" / "utils" / "i18n.py").read_text(encoding="utf-8")

    def test_die_pruefung_bekommt_helligkeit_und_design(self):
        stelle = self.quelle.index("    def _diagnose_pruefen(self")
        rumpf = self.quelle[stelle:stelle + 1800]
        self.assertIn("bildhelligkeit=self._diagnose_bildhelligkeit_messen()", rumpf)
        self.assertIn("dunkles_design=self._design_ist_dunkel()", rumpf)

    def test_beide_vorschauen_zeigen_den_hinweis(self):
        self.assertEqual(self.quelle.count("self._hell_hinweis_zeigen("), 2)
        self.assertIn("'settings_dialog.bild_hell_hinweis':", self.i18n)

    def test_bericht_nennt_die_bildhelligkeit(self):
        self.assertIn('z("Bildhelligkeit (0-255)"', self.quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
