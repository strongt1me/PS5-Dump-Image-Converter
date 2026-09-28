# -*- coding: utf-8 -*-
"""Die Warnungen beim Einbau folgen ShadowMount+ 1.7beta1/beta2.

Am 27.09.2026 am Quelltext gemessen (``sm_fakelib.c``,
``resolve_game_fakelib_source_for_path``): Ab 1.7beta1 liest ShadowMount+
im Spielordner wieder erst ``fakelib2``, dann ``fakelib`` - nur 1.7 alpha8
bis alpha13fix1 lasen dort ausschliesslich ``fakelib``. Bibliothek und
Infobox zeigten das schon; die Warnungen beim Einbau
(``_ampr_ablage_pruefen``, ``_fakelib_kollision``) nannten ein ``fakelib2``
im Spielordner bis zum 28.09.2026 noch "ignoriert". In der beiliegenden
1.7beta2 gewinnt es und verdeckt, was das Programm nach ``fakelib`` legt.

Geschrieben wird weiter nach ``fakelib`` - den Namen liest jede Fassung.
Auch das haelt diese Datei fest: Beim Umstellen durfte die Ablage nicht
mitkippen.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("einbau_warnungen")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek as bib           # noqa: E402
from ps5_validator.utils import shadowmount_generation as sg  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

ANLEITUNG_NEU = PROJEKT / "Anleitungen" / "ShadowMountPlus_fakelib_neue_Methode.html"
ANLEITUNG_ALT = PROJEKT / "Anleitungen" / "ShadowMountPlus_fakelib_alte_Methode.html"
HANDBUCH = PROJEKT / "BENUTZERHANDBUCH.html"


def _gui(sprache: str = "de"):
    """Eine Instanz ohne Fenster, die in der gewuenschten Sprache spricht."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._t = lambda k, _s=sprache, **kw: APP.i18n_translate(_s, k, **kw)
    return gui


class _MitSpielordner(unittest.TestCase):
    """Legt je Test einen Spielordner mit den genannten Unterordnern an."""

    def _spiel(self, *ordner: str) -> str:
        wurzel = tempfile.mkdtemp(prefix="einbau_warn_")
        self.addCleanup(_wegraeumen, wurzel)
        for name in ordner:
            os.makedirs(os.path.join(wurzel, name))
        # Ein Spiel hat mehr als seine Bibliotheken - die Pruefung darf sich
        # an den uebrigen Ordnern nicht stossen.
        os.makedirs(os.path.join(wurzel, "sce_sys"))
        return wurzel


def _wegraeumen(pfad: str) -> None:
    import shutil
    shutil.rmtree(pfad, ignore_errors=True)


class PruefungVorDemEinbauTests(_MitSpielordner):
    """``_ampr_ablage_pruefen`` - laeuft, bevor der AMPR EMU abgelegt wird."""

    def test_nur_fakelib_bleibt_still(self) -> None:
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertEqual(
                    _gui(sprache)._ampr_ablage_pruefen(self._spiel("fakelib")), [])

    def test_ohne_bibliotheksordner_bleibt_es_still(self) -> None:
        self.assertEqual(_gui()._ampr_ablage_pruefen(self._spiel()), [])

    def test_nur_fakelib2_warnt_einmal_mit_beiden_stufen(self) -> None:
        """Das Programm legt gleich nach ``fakelib`` - daneben gewinnt fakelib2.

        Bis zum 28.09.2026 kamen hier zwei Saetze: "ab 1.7 alpha8 ignoriert"
        und "Keiner der gefundenen Ordner wirkt". Fuer die beiliegende
        1.7beta2 war beides falsch.
        """
        zeilen = _gui()._ampr_ablage_pruefen(self._spiel("fakelib2"))
        self.assertEqual(len(zeilen), 1, zeilen)
        self.assertIn("1.7beta1", zeilen[0])
        self.assertIn("alpha13fix1", zeilen[0])
        self.assertIn("bliebe dann ungenutzt", zeilen[0])
        self.assertIn("umbenennen nach 'fakelib'", zeilen[0])
        self.assertNotIn("ignoriert", zeilen[0])

    def test_beide_ordner_ergeben_genau_einen_satz(self) -> None:
        """Beide Generationen sagen dasselbe - also einmal, nicht zweimal."""
        zeilen = _gui()._ampr_ablage_pruefen(self._spiel("fakelib", "fakelib2"))
        self.assertEqual(len(zeilen), 1, zeilen)
        self.assertIn("'fakelib2' gewinnt", zeilen[0])
        self.assertIn("ungenutzt", zeilen[0])

    def test_englisch_ohne_deutsche_saetze(self) -> None:
        for ordner in (("fakelib2",), ("fakelib", "fakelib2")):
            with self.subTest(ordner=ordner):
                zeilen = _gui("en")._ampr_ablage_pruefen(self._spiel(*ordner))
                self.assertEqual(len(zeilen), 1, zeilen)
                for deutsch in ("Spielordner", "gewinnt", "übergehen",
                                "Beide Ordner", "ungenutzt"):
                    self.assertNotIn(deutsch, zeilen[0])
                self.assertIn("1.7beta1", zeilen[0])


class KollisionTests(_MitSpielordner):
    """``_fakelib_kollision`` - laeuft nach dem Kopieren im BACKPORT."""

    def test_ein_ordner_allein_ist_keine_kollision(self) -> None:
        for ordner in ("fakelib", "fakelib2"):
            with self.subTest(ordner=ordner):
                self.assertEqual(_gui()._fakelib_kollision(self._spiel(ordner)), "")

    def test_beide_ordner_eine_zeile_und_der_eindeutige_schritt(self) -> None:
        """Nicht mehr "einen entfernen - welchen, entscheidet die Fassung".

        Der Schritt, der in jeder Fassung eindeutig ist: fehlende Dateien
        nach ``fakelib`` uebernehmen und ``fakelib2`` entfernen.
        """
        text = _gui("de")._fakelib_kollision(self._spiel("fakelib", "fakelib2"))
        self.assertTrue(text.startswith("[WARNUNG]"), text)
        self.assertEqual(text.count("\n  - "), 1, text)
        self.assertIn("Eindeutig in jeder Fassung", text)
        self.assertIn("„fakelib2“ entfernen", text)
        self.assertNotIn("welchen, entscheidet die Fassung", text)

    def test_englisch(self) -> None:
        text = _gui("en")._fakelib_kollision(self._spiel("fakelib", "fakelib2"))
        self.assertTrue(text.startswith("[WARNING]"), text)
        self.assertIn("Unambiguous in every version", text)
        self.assertNotIn("which one depends on the version", text)


class AblageBleibtTests(_MitSpielordner):
    """Die Umstellung betrifft die Warnungen, nicht das Ziel."""

    def test_geschrieben_wird_weiter_nach_fakelib(self) -> None:
        gui = _gui()
        self.assertEqual(gui._fakelib_ordnername(), "fakelib")
        self.assertEqual(gui._fakelib_pfad(self._spiel()).name, "fakelib")

    def test_der_hinweis_neben_dem_ordner_nennt_die_regel(self) -> None:
        text = STRINGS["fakelib.folder_fixed"]
        self.assertIn("alle Fassungen", text["de"])
        self.assertIn("1.7beta1", text["de"])
        self.assertIn("Every ShadowMountPlus version", text["en"])
        self.assertIn("1.7beta1", text["en"])


class EineRegelTests(unittest.TestCase):
    """Anzeige und Warnungen lesen dieselbe Reihenfolge."""

    def test_bibliothek_und_warnungen_lesen_dieselbe_reihenfolge(self) -> None:
        self.assertEqual(bib.FAKELIB_REIHENFOLGE,
                         tuple(sg.profil(sg.NEU)["spiel_ordner"]))

    def test_regelnummer_haengt_an_der_reihenfolge(self) -> None:
        """Stolperdraht: Aendert sich die Reihenfolge, muss EINBAU_REGEL mit.

        Sonst zeigt die Bibliothek gemerkte Ergebnisse nach der alten Regel
        weiter an, bis jemand "Neu suchen" drueckt.
        """
        self.assertEqual((bib.EINBAU_REGEL, bib.FAKELIB_REIHENFOLGE),
                         (2, ("fakelib2", "fakelib")),
                         "Reihenfolge geaendert? Dann EINBAU_REGEL erhoehen "
                         "und diesen Test nachziehen.")

    def test_anzeige_und_warnung_nennen_denselben_gewinner(self) -> None:
        bewertung = bib.einbauten_bewerten(
            ["fakelib/libSceAmpr.sprx", "fakelib2/libSceAgc.sprx"])
        self.assertEqual(bewertung["ordner"], "fakelib2")
        self.assertTrue(bewertung["ampr_verdeckt"])
        warnung = sg.beanstandungen(sg.NEU, sg.ORT_SPIEL, ["fakelib", "fakelib2"])
        self.assertIn("'%s' gewinnt" % bewertung["ordner"], warnung[0])


class KeinAlpha8SatzMehrTests(unittest.TestCase):
    """Kein Text behauptet mehr "fakelib2 im Spiel: ab alpha8 ignoriert"."""

    _AB_ALPHA8 = re.compile(r"\b(ab|from)\s+(ShadowMountPlus\s+)?(1\.7\s+)?alpha8\b",
                            re.IGNORECASE)

    def _alpha8_ignoriert(self, text: str) -> bool:
        return ("fakelib2" in text and bool(self._AB_ALPHA8.search(text))
                and "ignor" in text.lower())

    def test_die_pruefung_haette_die_alten_saetze_gefunden(self) -> None:
        """Gegenprobe am Wortlaut, der bis zum 28.09.2026 dastand."""
        for alt in ("Im Spielordner liegt {fakelib2!r}. Ab 1.7 alpha8 wird der "
                    "dort ignoriert – umbenennen nach {fakelib!r}.",
                    "Ab ShadowMountPlus 1.7 alpha8 zählt im Spielordner "
                    "ausschließlich dieser Ordner; ein „fakelib2“ daneben wird "
                    "wortlos ignoriert.",
                    "A {fakelib2!r} in the game folder is ignored from alpha8 "
                    "onwards – silently."):
            with self.subTest(alt=alt[:30]):
                self.assertTrue(self._alpha8_ignoriert(alt))

    def test_kein_programmtext(self) -> None:
        treffer = [(schluessel, sprache)
                   for schluessel, texte in STRINGS.items()
                   for sprache, text in texte.items()
                   if isinstance(text, str) and self._alpha8_ignoriert(text)]
        treffer += [("MELDUNGEN." + k, "de") for k, text in sg.MELDUNGEN.items()
                    if self._alpha8_ignoriert(text)]
        self.assertEqual(treffer, [])

    def test_die_anleitungen(self) -> None:
        neu = ANLEITUNG_NEU.read_text(encoding="utf-8")
        self.assertNotIn("wird übergangen!", neu)
        self.assertNotIn("hier zählt <b>nur</b>", neu)
        for stelle in ("&lt;Spielquelle&gt;/fakelib2/", "1.7beta1", "alpha13fix1"):
            with self.subTest(stelle=stelle):
                self.assertIn(stelle, neu)
        alt = ANLEITUNG_ALT.read_text(encoding="utf-8")
        self.assertNotIn("wird nur noch im Backport-Ordner gesucht", alt)

    def test_die_anleitung_nennt_die_beiliegende_fassung(self) -> None:
        """Stand bis zum 28.09.2026 auf 1.7beta1 - beigelegt ist seit v1.9.48 beta2."""
        elfs = sorted((PROJEKT / "helloworld").glob("shadowmountplus_v*.elf"))
        if len(elfs) != 1:
            self.skipTest("nicht genau eine ShadowMount+-ELF beigelegt: %s" % elfs)
        fassung = elfs[0].stem.split("_v", 1)[1]
        text = ANLEITUNG_NEU.read_text(encoding="utf-8")
        self.assertIn("Mitgeliefert ist ShadowMountPlus %s (" % fassung, text)

    def test_das_handbuch(self) -> None:
        text = HANDBUCH.read_text(encoding="utf-8")
        self.assertIn("<code>&lt;Spiel&gt;/fakelib2</code>", text)
        self.assertNotIn("<td><strong>wird ignoriert</strong></td>", text)
        self.assertIn("Warum trotzdem immer <code>fakelib</code>?", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
