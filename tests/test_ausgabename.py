# -*- coding: utf-8 -*-
"""Ausgabename per Vorlage (nach Dump Forge, Nutzerwahl 13.11.2026)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ausgabename")

from ps5_validator.utils import ausgabename as an            # noqa: E402

SPIEL = {"title": "Astro Bot", "title_id": "PPSA01234", "version": "01.000.000",
         "required_firmware": "09.00.00.00", "content_id": "UP9000-PPSA01234_00-ASTROBOT00000000", "region": "–"}


class PruefenTests(unittest.TestCase):
    def test_gueltige_vorlagen(self):
        for vorlage in ("{name}", "[{title}]-[{title_id}]", "{title_id}", "{titleid}", "{title} [{title_id}] v{version}",
                        "{name}-{pack}", "x{fw}{title}"):
            self.assertIsNone(an.vorlage_pruefen(vorlage), vorlage)

    def test_die_gruende(self):
        faelle = {
            "": ("leer", ""),
            "{title": ("offen", ""),
            "title}": ("zu", ""),
            "{titel}": ("unbekannt", "titel"),
            "{title}-{title}": ("doppelt", "title"),
            "{title_id}/{title}": ("zeichen", "/"),
            "{title}:{title_id}": ("zeichen", ":"),
            "{title}\n": ("steuerzeichen", ""),
            "{version}-{region}": ("braucht_namen", ""),
            "nur Text": ("braucht_namen", ""),
            "{title}" + "x" * 130: ("lang", ""),
        }
        for vorlage, (art, wert) in faelle.items():
            p = an.vorlage_pruefen(vorlage)
            self.assertIsNotNone(p, repr(vorlage))
            self.assertEqual((art, wert), (p.art, p.wert), repr(vorlage))

    def test_ein_alias_zaehlt_als_derselbe_teil(self):
        self.assertEqual("doppelt", an.vorlage_pruefen("{title_id}{titleid}").art)

    def test_die_laenge_der_vorlage_zaehlt_bytes(self):
        self.assertIsNone(an.vorlage_pruefen("{title}" + "x" * (an.VORLAGE_MAX - 7)))
        self.assertEqual("lang", an.vorlage_pruefen("{title}" + "é" * 64).art)       # 128 Bytes Text + Token


class RendernTests(unittest.TestCase):
    W = {"name": "Spiel", "title": "Astro Bot", "title_id": "PPSA01234", "version": "1.0.0", "region": "US",
         "fw": "9.00", "pack": "zstd"}

    def test_die_vorgabe_aus_forge(self):
        self.assertEqual("[Astro Bot]-[PPSA01234]", an.rendern("[{title}]-[{title_id}]", self.W))

    def test_text_zwischen_den_teilen(self):
        self.assertEqual("Astro Bot [PPSA01234] v1.0.0", an.rendern("{title} [{title_id}] v{version}", self.W))

    def test_ein_leerer_teil_faellt_weg_samt_leerer_klammer(self):
        w = dict(self.W, title="")
        self.assertEqual("PPSA01234", an.rendern("[{title}]-[{title_id}]", w) .replace("[", "").replace("]", ""))
        self.assertEqual("[PPSA01234]", an.rendern("[{title}]-[{title_id}]", w))
        self.assertEqual("PPSA01234", an.rendern("({title}) {title_id}", w))

    def test_verschachtelte_leere_klammern_gehen_alle_weg(self):
        w = dict(self.W, title="", version="")
        self.assertEqual("PPSA01234", an.rendern("[({title}{version})]{title_id}", w))

    def test_folgen_gleicher_trenner_werden_einer(self):
        w = dict(self.W, version="")
        self.assertEqual("Astro Bot-PPSA01234", an.rendern("{title}-{version}-{title_id}", w))
        self.assertEqual("Astro Bot_PPSA01234", an.rendern("{title}__{title_id}", w))
        self.assertEqual("Astro Bot PPSA01234", an.rendern("{title}  {title_id}", w))

    def test_verschiedene_trenner_bleiben(self):
        self.assertEqual("Astro Bot-_PPSA01234", an.rendern("{title}-_{title_id}", self.W))

    def test_die_raender_werden_getrimmt(self):
        w = dict(self.W, version="", pack="")
        self.assertEqual("PPSA01234", an.rendern("{pack}-{version}_.{title_id}. _", w))
        self.assertEqual("Astro Bot", an.rendern("--{title}..", w))

    def test_ein_wert_wird_nie_aufgeraeumt(self):
        w = dict(self.W, title="  -A--B- ")
        self.assertEqual("  -A--B- ", an.rendern("{title}", w))

    def test_eine_ungueltige_vorlage_ergibt_nichts(self):
        self.assertEqual("", an.rendern("{gibt_es_nicht}", self.W))
        self.assertEqual("", an.rendern("", self.W))

    def test_der_text_der_vorlage_wird_nfc(self):
        self.assertEqual("é".encode("utf-8").decode() and "é-PPSA01234",
                         an.rendern("é-{title_id}", self.W))


class WerteTests(unittest.TestCase):
    def test_werte_aus_den_angaben(self):
        w = an.werte_aus_angaben(SPIEL, name="Quellname", pack="zstd")
        self.assertEqual({"name": "Quellname", "title": "Astro Bot", "title_id": "PPSA01234", "version": "1.0.0",
                          "region": "US", "fw": "9.00", "pack": "zstd"}, w)

    def test_fehlendes_ist_leer(self):
        w = an.werte_aus_angaben({"title": "–", "title_id": "–", "version": "–", "required_firmware": "–"}, name="Q")
        self.assertEqual({"name": "Q", "title": "", "title_id": "", "version": "", "region": "", "fw": "", "pack": ""}, w)

    def test_eine_ungueltige_kennung_gilt_nicht(self):
        self.assertEqual("", an.werte_aus_angaben({"title_id": "../x"}, name="q")["title_id"])

    def test_unzulaessige_zeichen_im_titel_fallen_weg(self):
        self.assertEqual("Was Soll Das", an.werte_aus_angaben({"title": "Was: Soll  Das?"})["title"])
        self.assertEqual("ab", an.bereinigen("a\x00b"))

    def test_die_region_aus_dem_regionsnamen(self):
        self.assertEqual("EU", an.werte_aus_angaben({"region": "EUR"})["region"])


class AusgabenameTests(unittest.TestCase):
    def test_die_vorgabe_aendert_nichts(self):
        e = an.ausgabename(an.STANDARD, SPIEL, name="Mein Ordner " + "x" * 80, zielformat="exfat")
        self.assertEqual("Mein Ordner " + "x" * 80, e.name)
        self.assertFalse(e.gekuerzt)
        self.assertEqual("Q", an.ausgabename("", SPIEL, name="Q").name)

    def test_eine_vorlage_erzeugt_den_namen(self):
        e = an.ausgabename("[{title}]-[{title_id}]", SPIEL, name="Q", zielformat="exfat")
        self.assertEqual("[Astro Bot]-[PPSA01234]", e.name)
        self.assertIsNone(e.problem)

    def test_eine_schlechte_vorlage_laesst_den_namen_der_quelle_und_nennt_das_problem(self):
        e = an.ausgabename("{unsinn}", SPIEL, name="Q")
        self.assertEqual("Q", e.name)
        self.assertEqual("unbekannt", e.problem.art)

    def test_ohne_angaben_bleibt_der_name_der_quelle(self):
        e = an.ausgabename("[{title}]-[{title_id}]", {}, name="Q", zielformat="exfat")
        self.assertEqual("Q", e.name)

    def test_nur_title_id_vorhanden(self):
        e = an.ausgabename("[{title}]-[{title_id}]", {"title_id": "PPSA01234"}, name="Q")
        self.assertEqual("[PPSA01234]", e.name)

    def test_ein_zu_langer_name_wird_gekuerzt_und_zwar_zuerst_der_titel(self):
        spiel = dict(SPIEL, title="Ein sehr langer Titel " * 6)
        e = an.ausgabename("{title} [{title_id}]", spiel, name="Q", zielformat="exfat")
        self.assertTrue(e.gekuerzt)
        self.assertLessEqual(len(e.name.encode("utf-8")), 63)
        self.assertTrue(e.name.endswith(" [PPSA01234]"), e.name)
        self.assertTrue(e.name.startswith("Ein sehr langer Titel"))

    def test_die_grenze_gilt_je_zielformat(self):
        spiel = dict(SPIEL, title="T" * 70)
        self.assertEqual(63, len(an.ausgabename("{title}", spiel, name="Q", zielformat="exfat").name))
        e = an.ausgabename("{title}", spiel, name="Q", zielformat="ffpfsc")
        self.assertEqual(58, len(e.name))
        self.assertTrue(e.gekuerzt)
        self.assertEqual(70, len(an.ausgabename("{title}", spiel, name="Q", zielformat="folder").name),
                         "ein Ordner hat keine Grenze")
        self.assertFalse(an.ausgabename("{title}", spiel, name="Q", zielformat="pkg").gekuerzt)

    def test_gekuerzt_wird_an_der_zeichengrenze_in_bytes(self):
        spiel = dict(SPIEL, title="é" * 60)          # 120 Bytes
        e = an.ausgabename("{title}", spiel, name="Q", zielformat="exfat")
        self.assertLessEqual(len(e.name.encode("utf-8")), 63)
        self.assertEqual(31, len(e.name))
        e.name.encode("utf-8").decode("utf-8")

    def test_ist_ohne_titel_noch_zu_lang_wird_der_ganze_name_gekuerzt(self):
        e = an.ausgabename("{name}-{title_id}", SPIEL, name="N" * 100, zielformat="exfat")
        self.assertTrue(e.gekuerzt)
        self.assertLessEqual(len(e.name.encode("utf-8")), 63)

    def test_am_ende_bleiben_weder_punkt_noch_leerzeichen(self):
        spiel = dict(SPIEL, title="a" * 61 + ". b")
        e = an.ausgabename("{title}", spiel, name="Q", zielformat="exfat")
        self.assertFalse(e.name.endswith((".", " ")))


class WindowsNamenTests(unittest.TestCase):
    """Ein erzeugter Name taugt unter Windows als Datei- und Ordnername (Pruefbericht 14.11.2026)."""

    def test_geraetename_bekommt_einen_unterstrich(self):
        for titel in ("Aux", "CON", "nul", "COM1", "lpt9", "Aux.txt", "NUL.v2"):
            with self.subTest(titel):
                e = an.ausgabename("{title}", dict(SPIEL, title=titel), name="Q")
                self.assertTrue(e.name.split(".", 1)[0].endswith("_"), e.name)

    def test_der_unterstrich_steht_vor_dem_ersten_punkt(self):
        """Windows liest ``Aux.Game`` wie ``AUX``: ``Aux.Game_`` hiesse weiter so."""
        self.assertEqual("Aux_.Game", an.ausgabename("{title}", dict(SPIEL, title="Aux.Game"), name="Q").name)
        self.assertEqual("NUL_.v2", an.ausgabename("{title}", dict(SPIEL, title="NUL.v2"), name="Q").name)
        self.assertEqual("Aux_", an.ausgabename("{title}", dict(SPIEL, title="Aux"), name="Q").name)

    def test_aehnliche_namen_bleiben(self):
        for titel in ("Console", "Auxiliary", "COM10", "Nullpunkt"):
            with self.subTest(titel):
                self.assertEqual(titel, an.ausgabename("{title}", dict(SPIEL, title=titel), name="Q").name)

    def test_punkt_und_leerzeichen_am_ende_fallen_weg(self):
        e = an.ausgabename("{title}", dict(SPIEL, title="Ende mit Punkt. . "), name="Q")
        self.assertEqual("Ende mit Punkt", e.name)

    def test_formatzeichen_aus_der_param_json_fallen_weg(self):
        e = an.ausgabename("{title}", dict(SPIEL, title="A\u202eB\u200bC"), name="Q")
        self.assertEqual("ABC", e.name)


class GekuerztWindowsTests(unittest.TestCase):
    def test_gekuerzt_gilt_auch_wenn_nur_der_geraetename_gekuerzt_hat(self):
        """Genau 63 Bytes mit einem Geraetenamen vorn: Der Unterstrich schiebt den Namen ueber die Grenze, das letzte Zeichen faellt weg."""
        e = an.ausgabename("{title}", dict(SPIEL, title="Con." + "x" * 59), name="Q", zielformat="exfat")
        self.assertTrue(e.gekuerzt)
        self.assertEqual(an.grenze_fuer("exfat"), len(e.name.encode("utf-8")))
        self.assertTrue(e.name.startswith("Con_."), e.name)
        kurz = an.ausgabename("{title}", dict(SPIEL, title="Con.x"), name="Q", zielformat="exfat")
        self.assertFalse(kurz.gekuerzt)


    def test_ein_gekuerzter_name_mit_geraetenamen_wird_auch_windows_tauglich(self):
        e = an.ausgabename("{title}", dict(SPIEL, title="CON." + "x" * 90), name="Q", zielformat="exfat")
        self.assertTrue(e.gekuerzt)
        self.assertTrue(e.name.startswith("CON_."), e.name)
        self.assertLessEqual(len(e.name.encode("utf-8")), an.grenze_fuer("exfat"))


class OhneAngabenTests(unittest.TestCase):
    """Liefert kein Teil der Vorlage einen Wert, bleibt der Name der Quelle."""

    def test_nur_eigener_text_bleibt_der_name_der_quelle(self):
        for angaben in ({}, {"title": ""}):
            with self.subTest(angaben):
                self.assertEqual("Quelle", an.ausgabename("PS5 {title}", angaben, name="Quelle").name)

    def test_das_pack_allein_macht_keinen_namen(self):
        """``{pack}`` kommt aus der Auswahl und ist immer gesetzt: Es darf den Namen der Quelle nicht verdraengen."""
        for vorlage in ("{title} [{pack}]", "{title_id}-{pack}", "{title}{pack}"):
            with self.subTest(vorlage):
                self.assertEqual("Quelle", an.ausgabename(vorlage, {}, name="Quelle", pack="lz4").name)
        self.assertEqual("Astro Bot [lz4]", an.ausgabename("{title} [{pack}]", SPIEL, name="Q", pack="lz4").name)

    def test_ein_format_zeichen_im_text_der_vorlage_ist_ein_fehler(self):
        for vorlage in ("{title}\u202e", "A\u200b{title}"):
            with self.subTest(vorlage):
                problem = an.vorlage_pruefen(vorlage)
                self.assertIsNotNone(problem)
                self.assertEqual("steuerzeichen", problem.art)

    def test_ein_teil_mit_wert_genuegt(self):
        self.assertEqual("PS5 Astro Bot", an.ausgabename("PS5 {title}", SPIEL, name="Q").name)

    def test_leere_klammerreste_fallen_weg(self):
        spiel = {"title": "Astro Bot", "title_id": "PPSA01234", "required_firmware": "9.00"}
        e = an.ausgabename("{title} [{region} {fw}]", spiel, name="Q")
        self.assertNotIn("[ ", e.name)
        self.assertNotIn(" ]", e.name)
        self.assertEqual("Astro Bot [9.00]", e.name)

    def test_nur_leere_teile_in_klammern_fallen_ganz_weg(self):
        spiel = {"title": "Astro Bot", "title_id": "PPSA01234"}
        self.assertEqual("Astro Bot", an.ausgabename("{title} [{region} {fw}]", spiel, name="Q").name)


class GrenzenTests(unittest.TestCase):
    def test_die_grenzen_kommen_aus_der_vorabpruefung(self):
        from ps5_validator.utils import vorabpruefung
        for fmt in vorabpruefung.ABBILD_FORMATE:
            self.assertEqual(vorabpruefung.name_max(fmt), an.grenze_fuer(fmt))
        self.assertIsNone(an.grenze_fuer("folder"))

    def test_die_beispiele_taugen(self):
        for vorlage in an.BEISPIELE:
            self.assertIsNone(an.vorlage_pruefen(vorlage), vorlage)
        self.assertEqual(an.STANDARD, an.BEISPIELE[0])

    def test_jeder_teil_hat_einen_wert(self):
        self.assertEqual(set(an.TEILE), set(an.werte_aus_angaben(SPIEL, name="n", pack="p")))


if __name__ == "__main__":
    unittest.main()
