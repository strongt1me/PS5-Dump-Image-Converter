# -*- coding: utf-8 -*-
"""Die zwei Ablage-Mechaniken von ShadowMountPlus.

Der Umbau zwischen 1.7 alpha6 und 1.7 alpha8 macht eine Ablage, die vorher
richtig war, danach wirkungslos - und zwar ohne jede Meldung. Genau solche
Aenderungen gehoeren festgenagelt: Wenn hier etwas kippt, merkt man es sonst
erst an einem Spiel, das ohne seine Ersatzbibliotheken startet.

Quelle sind die beiden Anleitungen vom 22.08.2026, die am Quellcode beider
Fassungen geprueft wurden.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import shadowmount_generation as sg


class ProfilTests(unittest.TestCase):
    """Was die beiden Fassungen unterscheidet."""

    def test_beide_generationen_sind_da(self) -> None:
        self.assertEqual(set(sg.GENERATIONEN), {sg.ALT, sg.NEU})

    def test_eine_unbekannte_kennung_scheitert_laut(self) -> None:
        """Lieber ein Fehler als still die falsche Mechanik anwenden."""
        with self.assertRaises(KeyError):
            sg.profil("alpha7")

    def test_der_entscheidende_unterschied(self) -> None:
        """fakelib2 im Spielordner: frueher wirksam, heute nicht mehr."""
        self.assertTrue(sg.profil(sg.ALT)["spiel_fakelib2_wirkt"])
        self.assertFalse(sg.profil(sg.NEU)["spiel_fakelib2_wirkt"])

    def test_nur_die_neue_fassung_kennt_cache_und_emulatoren(self) -> None:
        self.assertFalse(sg.profil(sg.ALT)["hat_cache"])
        self.assertFalse(sg.profil(sg.ALT)["hat_emus"])
        self.assertTrue(sg.profil(sg.NEU)["hat_cache"])
        self.assertTrue(sg.profil(sg.NEU)["hat_emus"])

    def test_nur_die_alte_fassung_stapelt_schichten(self) -> None:
        self.assertTrue(sg.profil(sg.ALT)["stapelt_schichten"])
        self.assertFalse(sg.profil(sg.NEU)["stapelt_schichten"])


class SuchreihenfolgeTests(unittest.TestCase):
    """Die alte Fassung sucht nach Ordnernamen, die neue nach Pfaden."""

    def test_alt_entscheidet_am_ordnernamen(self) -> None:
        wege = sg.suchreihenfolge(sg.ALT)
        self.assertEqual(len(wege), 2)
        self.assertIn("app0/fakelib2/", wege[0])
        self.assertIn("app0/fakelib/", wege[1])

    def test_alt_bevorzugt_fakelib2(self) -> None:
        """Bis alpha6 gewinnt fakelib2 - auch wenn es leer ist."""
        wege = sg.suchreihenfolge(sg.ALT)
        self.assertLess(wege[0].index("fakelib2"), len(wege[0]))
        self.assertNotIn("fakelib2", wege[1])

    def test_neu_hat_drei_pfade_in_fester_reihenfolge(self) -> None:
        self.assertEqual(sg.suchreihenfolge(sg.NEU), (
            "<scanpath>/backports/<TITLE_ID>/fakelib2/",
            "<scanpath>/backports/<TITLE_ID>/fakelib/",
            "<Spielquelle>/fakelib/",
        ))

    def test_neu_nennt_den_spielordner_nur_mit_fakelib(self) -> None:
        """Der haeufigste Fehler beim Umstieg."""
        letzter = sg.suchreihenfolge(sg.NEU)[-1]
        self.assertIn("<Spielquelle>/fakelib/", letzter)
        self.assertNotIn("fakelib2", letzter)


class AblagezielTests(unittest.TestCase):
    """Wohin die Bibliotheken tatsaechlich gehoeren."""

    def test_backport_ist_bei_beiden_der_gleiche_pfad(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            with self.subTest(generation=gen):
                ziel = sg.ablageziel(gen, sg.ORT_BACKPORT,
                                     title_id="PPSA01234",
                                     scanpath="/data/homebrew")
                self.assertEqual(
                    ziel["pfad"],
                    "/data/homebrew/backports/PPSA01234/fakelib2")
                self.assertTrue(ziel["empfohlen"])

    def test_der_scanpath_darf_einen_schraegstrich_am_ende_haben(self) -> None:
        ziel = sg.ablageziel(sg.NEU, sg.ORT_BACKPORT, title_id="PPSA01234",
                             scanpath="/data/homebrew/")
        self.assertEqual(ziel["pfad"],
                         "/data/homebrew/backports/PPSA01234/fakelib2")

    def test_backport_ohne_angaben_scheitert(self) -> None:
        with self.assertRaises(ValueError):
            sg.ablageziel(sg.NEU, sg.ORT_BACKPORT)

    def test_im_spielordner_unterscheiden_sich_die_fassungen(self) -> None:
        alt = sg.ablageziel(sg.ALT, sg.ORT_SPIEL, wurzel="/mnt/usb0/Spiel")
        neu = sg.ablageziel(sg.NEU, sg.ORT_SPIEL, wurzel="/mnt/usb0/Spiel")
        self.assertTrue(alt["pfad"].endswith("fakelib2"))
        self.assertTrue(neu["pfad"].endswith("fakelib"))
        self.assertFalse(neu["pfad"].endswith("fakelib2"))

    def test_die_neue_fassung_raet_vom_spielordner_ab(self) -> None:
        neu = sg.ablageziel(sg.NEU, sg.ORT_SPIEL, wurzel="/mnt/usb0/Spiel")
        self.assertFalse(neu["empfohlen"])
        self.assertIn("ignoriert", neu["hinweis"])

    def test_windows_pfade_behalten_ihren_trenner(self) -> None:
        ziel = sg.ablageziel(sg.ALT, sg.ORT_SPIEL, wurzel=r"E:\Spiele\PPSA01234")
        self.assertEqual(ziel["pfad"], r"E:\Spiele\PPSA01234\fakelib2")

    def test_ein_unbekannter_ort_scheitert(self) -> None:
        with self.assertRaises(ValueError):
            sg.ablageziel(sg.ALT, "irgendwo", wurzel="/x")


class BeanstandungenTests(unittest.TestCase):
    """Was an einer bestehenden Ablage nicht wirkt."""

    def test_fakelib2_im_spielordner_wird_bei_neu_beanstandet(self) -> None:
        meldungen = sg.beanstandungen(sg.NEU, sg.ORT_SPIEL, ["fakelib2"])
        self.assertTrue(meldungen)
        self.assertTrue(any("ignoriert" in m for m in meldungen))

    def test_dieselbe_ablage_ist_bei_alt_in_ordnung(self) -> None:
        self.assertEqual(sg.beanstandungen(sg.ALT, sg.ORT_SPIEL, ["fakelib2"]), [])

    def test_beide_ordner_im_spiel_warnen_bei_alt(self) -> None:
        """fakelib2 gewinnt, fakelib bleibt ungenutzt - ohne Meldung."""
        meldungen = sg.beanstandungen(sg.ALT, sg.ORT_SPIEL,
                                      ["fakelib", "fakelib2"])
        self.assertTrue(any("ungenutzt" in m for m in meldungen))

    def test_grossschreibung_stoert_nicht(self) -> None:
        self.assertTrue(sg.beanstandungen(sg.NEU, sg.ORT_SPIEL, ["FakeLib2"]))

    def test_leere_liste_gibt_keine_beanstandung(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            for ort in (sg.ORT_SPIEL, sg.ORT_BACKPORT):
                with self.subTest(generation=gen, ort=ort):
                    self.assertEqual(sg.beanstandungen(gen, ort, []), [])

    def test_im_backport_wirken_bei_neu_beide_ordner(self) -> None:
        self.assertEqual(sg.beanstandungen(sg.NEU, sg.ORT_BACKPORT, ["fakelib"]), [])

    def test_beide_im_backport_nennen_den_gewinner(self) -> None:
        meldungen = sg.beanstandungen(sg.NEU, sg.ORT_BACKPORT,
                                      ["fakelib", "fakelib2"])
        self.assertTrue(any("gewinnt" in m for m in meldungen))


class ErkennungTests(unittest.TestCase):
    """Welche Fassung auf der Konsole laeuft - drei Anzeichen."""

    def test_ein_neuer_schluessel_genuegt(self) -> None:
        befund = sg.generation_erkennen(config_text="update_emulators=1")
        self.assertEqual(befund["generation"], sg.NEU)

    def test_eine_config_ohne_neue_schluessel_spricht_fuer_alt(self) -> None:
        befund = sg.generation_erkennen(
            config_text="backport_fakelib=1\nglobal_fakelib=1")
        self.assertEqual(befund["generation"], sg.ALT)

    def test_die_logzeile_genuegt_allein(self) -> None:
        befund = sg.generation_erkennen(
            log_text="[FAKELIB] using cache for PPSA01234: ...")
        self.assertEqual(befund["generation"], sg.NEU)

    def test_ein_fehlender_cache_beweist_nichts(self) -> None:
        """Der Cache entsteht erst, wenn er gebraucht wird."""
        befund = sg.generation_erkennen(cache_ordner_da=False)
        self.assertEqual(befund["generation"], "")
        self.assertEqual(befund["belege"], [])

    def test_ohne_anhaltspunkte_wird_nichts_behauptet(self) -> None:
        befund = sg.generation_erkennen()
        self.assertEqual(befund["generation"], "")
        self.assertFalse(befund["widerspruch"])

    def test_ein_widerspruch_wird_gemeldet_statt_geraten(self) -> None:
        befund = sg.generation_erkennen(
            config_text="backport_fakelib=1", cache_ordner_da=True)
        self.assertTrue(befund["widerspruch"])
        self.assertEqual(befund["generation"], "")
        self.assertEqual(len(befund["belege"]), 2)

    def test_die_belege_werden_mitgeliefert(self) -> None:
        """Ohne Beleg waere die Aussage nicht nachpruefbar."""
        befund = sg.generation_erkennen(config_text="auto_update_ampr=0")
        self.assertTrue(befund["belege"])
        self.assertIn("auto_update_ampr", befund["belege"][0][1])


class RangfolgeTests(unittest.TestCase):
    """Wer bei gleichen Dateinamen gewinnt."""

    def test_alt_stapelt_zwei_schichten(self) -> None:
        self.assertEqual(len(sg.rangfolge(sg.ALT, "game")), 2)

    def test_neu_kennt_drei_quellen(self) -> None:
        self.assertEqual(len(sg.rangfolge(sg.NEU, "game")), 3)

    def test_standard_laesst_das_spiel_gewinnen(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            with self.subTest(generation=gen):
                self.assertIn("Spiel-fakelib", sg.rangfolge(gen, "game")[:2])

    def test_global_stellt_die_globale_nach_vorn(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            with self.subTest(generation=gen):
                self.assertEqual(sg.rangfolge(gen, "global")[0],
                                 "globale fakelib")

    def test_emulatoren_gibt_es_nur_in_der_neuen_fassung(self) -> None:
        self.assertNotIn("Emulator-Dateien", sg.rangfolge(sg.ALT, "game"))
        self.assertIn("Emulator-Dateien", sg.rangfolge(sg.NEU, "game"))


class ConfigTests(unittest.TestCase):
    """Die Schluessel, die je Fassung gelten."""

    def test_die_neuen_schluessel_fehlen_in_der_alten_fassung(self) -> None:
        alte = {k for k, _ in sg.profil(sg.ALT)["config_schluessel"]}
        for schluessel in sg.NUR_NEU_SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertNotIn(schluessel, alte)

    def test_die_neue_fassung_kennt_sie_alle(self) -> None:
        neue = {k for k, _ in sg.profil(sg.NEU)["config_schluessel"]}
        for schluessel in sg.NUR_NEU_SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, neue)

    def test_der_master_schalter_gilt_in_beiden(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            with self.subTest(generation=gen):
                schluessel = {k for k, _ in sg.profil(gen)["config_schluessel"]}
                self.assertIn("backport_fakelib", schluessel)

    def test_der_ampr_download_ist_ab_werk_aus(self) -> None:
        """Ohne diese Option kein Netzzugriff - das muss so bleiben."""
        vorgaben = dict(sg.profil(sg.NEU)["config_schluessel"])
        self.assertEqual(vorgaben["auto_update_ampr"], "0")


class CacheUndFallenTests(unittest.TestCase):
    """Cache-Pfad und die Punkte, an denen es haengt."""

    def test_der_cache_pfad_stimmt(self) -> None:
        self.assertEqual(sg.cache_pfad("PPSA01234"),
                         "/data/shadowmount/cache/PPSA01234/fakelib")

    def test_beide_fassungen_nennen_stolperfallen(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            with self.subTest(generation=gen):
                self.assertTrue(sg.stolperfallen(gen))

    def test_der_cache_ordner_taucht_nur_bei_neu_auf(self) -> None:
        alt = " ".join(sg.stolperfallen(sg.ALT))
        neu = " ".join(sg.stolperfallen(sg.NEU))
        self.assertNotIn("Cache-Ordner", alt)
        self.assertIn("Cache-Ordner", neu)

    def test_backpork_wird_in_beiden_genannt(self) -> None:
        for gen in (sg.ALT, sg.NEU):
            with self.subTest(generation=gen):
                self.assertIn("BackPork", " ".join(sg.stolperfallen(gen)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
