# -*- coding: utf-8 -*-
"""Farbsehschwächen: die Oberfläche passt sich an, und es lässt sich belegen.

Rund 6 % der Männer haben eine Deuteranopie, etwa 1 % eine Protanopie;
Tritanopie und Achromatopsie sind selten. Für sie fallen Farben zusammen, die
für alle anderen deutlich verschieden aussehen.

**Am 25.08.2026 gemessen**, kleinster Abstand zwischen zwei
bedeutungstragenden Farben (unter 20 gilt als verwechselbar):

===============  ============  ===========  ===========  =============
Design           Deuteranopie  Protanopie   Tritanopie   Achromatopsie
===============  ============  ===========  ===========  =============
dunkel                   17,5         22,0          6,2            7,5
mittel                   15,0         23,3          9,3            3,8
hell                      6,8          6,1          8,7            2,9
===============  ============  ===========  ===========  =============

Neun von zwölf Kombinationen lagen unter der Schwelle - im hellen Design waren
Warnung und Fehler mit 6,8 praktisch dasselbe.

Zwei Gedanken tragen die Lösung:

* **Eine andere Achse.** Rot gegen Grün ist genau die Richtung, die bei
  Deuteranopie und Protanopie ausfällt. Blau gegen Gelb bleibt dort erhalten.
* **Helligkeit als zweites Merkmal.** Sie ist von der Farbe unabhängig und
  trägt auch dort, wo gar keine Farbe wahrgenommen wird.

Bei **Achromatopsie** stösst das an eine Grenze, die keine Farbwahl aufhebt:
Vier Stufen, die auf einem Untergrund alle lesbar bleiben, passen nicht mit je
20 Abstand in den verfügbaren Helligkeitsbereich. Deshalb zählt dort der
ELF-Knopf nicht mit - er trägt eine Beschriftung, seine Farbe sagt nichts aus.
"""
from __future__ import annotations

import itertools
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Unter diesem Abstand gelten zwei nebeneinanderliegende Flächen als nicht
#: mehr sicher zu unterscheiden.
SCHWELLE = 20.0

#: Die Farben, die eine Bedeutung tragen. Alles andere ist Gestaltung.
BEDEUTUNG = ["fg_success", "fg_warning", "error_btn", "elf_btn"]


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class SimulationTests(unittest.TestCase):
    """Die Rechnung selbst - sie trägt alles Übrige."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def test_grau_bleibt_grau(self) -> None:
        """Eine unbunte Farbe kann sich bei keiner Form ändern."""
        for form in self.haupt.FARBSCHWAECHEN:
            with self.subTest(form=form):
                ergebnis = self.haupt.farbe_wie_gesehen("#808080", form)
                r, g, b = self.haupt.hex_zu_rgb(ergebnis)
                self.assertLessEqual(max(r, g, b) - min(r, g, b), 6,
                                     "%s ergab %s" % (form, ergebnis))

    def test_blau_bleibt_bei_rotgruenschwaeche_erhalten(self) -> None:
        """Der Grund, warum Blau die tragende Achse ist."""
        for form in ("deuteranopie", "protanopie"):
            with self.subTest(form=form):
                abstand = self.haupt.farbabstand(
                    self.haupt.farbe_wie_gesehen("#2B5FD9", form), "#2B5FD9")
                self.assertLess(abstand, 30.0,
                                "%s veraendert Blau um %.1f" % (form, abstand))

    def test_gruen_und_rot_fallen_zusammen(self) -> None:
        """Die Gegenprobe: Genau das ist ja das Problem."""
        gruen, rot = "#4CC38A", "#D65B57"
        normal = self.haupt.farbabstand(gruen, rot)
        deut = self.haupt.farbabstand(
            self.haupt.farbe_wie_gesehen(gruen, "deuteranopie"),
            self.haupt.farbe_wie_gesehen(rot, "deuteranopie"))
        self.assertGreater(normal, 90.0)
        self.assertLess(deut, 30.0,
                        "die Simulation zeigt den Effekt gar nicht")

    def test_achromatopsie_laesst_nur_helligkeit(self) -> None:
        for farbe in ("#FF0000", "#00FF00", "#0000FF"):
            ergebnis = self.haupt.farbe_wie_gesehen(farbe, "achromatopsie")
            r, g, b = self.haupt.hex_zu_rgb(ergebnis)
            self.assertEqual((r, g), (g, b), "%s -> %s" % (farbe, ergebnis))

    def test_unsinn_wirft_nicht(self) -> None:
        """Die Rechnung läuft beim Erstellen des Diagnoseberichts mit."""
        for farbe in ("", "#", "#XYZ", "blau", None, "#12345"):
            for form in self.haupt.FARBSCHWAECHEN:
                with self.subTest(farbe=farbe, form=form):
                    try:
                        self.haupt.farbe_wie_gesehen(str(farbe), form)
                        self.haupt.farbabstand(str(farbe), "#000000")
                    except Exception as exc:
                        self.fail("%r/%s: %s" % (farbe, form, type(exc).__name__))

    def test_eine_unbekannte_form_aendert_nichts(self) -> None:
        self.assertEqual(self.haupt.farbe_wie_gesehen("#4CC38A", "quatsch"),
                         "#4CC38A")


class PalettenTests(unittest.TestCase):
    """Jede Kombination aus Design und Farbschwäche muss tragen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls.gui = cls.haupt.PS5ConverterGUI

    def engster_abstand(self, palette, form):
        schluessel = BEDEUTUNG[:3] if form == "achromatopsie" else BEDEUTUNG
        schluessel = [k for k in schluessel if palette.get(k)]
        eng, paar = 999.0, ""
        for a, b in itertools.combinations(schluessel, 2):
            d = self.haupt.farbabstand(
                self.haupt.farbe_wie_gesehen(palette[a], form),
                self.haupt.farbe_wie_gesehen(palette[b], form))
            if d < eng:
                eng, paar = d, "%s/%s" % (a, b)
        return eng, paar

    def test_jede_kombination_bleibt_unterscheidbar(self) -> None:
        """Zwölf Kombinationen - drei Designs mal vier Formen."""
        for design in self.gui._THEMES:
            for form in self.haupt.FARBSCHWAECHEN:
                if form == "keine":
                    continue
                with self.subTest(design=design, form=form):
                    palette = dict(self.gui._THEMES[design])
                    palette.update(self.gui._farbschwaeche_satz(form, design))
                    eng, paar = self.engster_abstand(palette, form)
                    self.assertGreaterEqual(
                        eng, SCHWELLE,
                        "%s/%s: %s nur %.1f auseinander"
                        % (design, form, paar, eng))

    def test_ohne_anpassung_waere_es_wirklich_zu_eng(self) -> None:
        """Die Gegenprobe - sonst prüfte der Test oben nichts.

        Ohne die Anpassung liegen neun von zwölf Kombinationen unter der
        Schwelle. Bestünde auch der Urzustand, wäre der Test wertlos.
        """
        schlecht = 0
        for design in self.gui._THEMES:
            for form in self.haupt.FARBSCHWAECHEN:
                if form == "keine":
                    continue
                eng, _ = self.engster_abstand(self.gui._THEMES[design], form)
                if eng < SCHWELLE:
                    schlecht += 1
        self.assertGreaterEqual(schlecht, 6,
                                "nur %d Kombinationen waren vorher zu eng - "
                                "misst der Test noch das Richtige?" % schlecht)

    def test_ohne_farbschwaeche_bleibt_alles_wie_es_war(self) -> None:
        for design, palette in self.gui._THEMES.items():
            with self.subTest(design=design):
                self.assertEqual(self.gui._farbschwaeche_satz("keine", design), {})

    def test_die_saetze_ersetzen_nur_bedeutungstragende_farben(self) -> None:
        """Hintergründe und Schrift bleiben - sonst wäre es ein anderes Design."""
        erlaubt = set(BEDEUTUNG) | {"error_btn_hover", "elf_btn_hover",
                                    "remote_dir"}
        for form in ("deuteranopie", "achromatopsie"):
            for design in self.gui._THEMES:
                with self.subTest(form=form, design=design):
                    satz = self.gui._farbschwaeche_satz(form, design)
                    self.assertTrue(set(satz) <= erlaubt,
                                    "unerwartet: %s" % (set(satz) - erlaubt))

    def test_jedes_design_hat_fuer_jede_form_einen_satz(self) -> None:
        for form in self.haupt.FARBSCHWAECHEN:
            if form == "keine":
                continue
            for design in self.gui._THEMES:
                with self.subTest(form=form, design=design):
                    self.assertTrue(self.gui._farbschwaeche_satz(form, design))

    def test_die_farben_bleiben_gegen_ihren_untergrund_lesbar(self) -> None:
        """Eine unterscheidbare Farbe nützt nichts, wenn man sie nicht sieht."""
        for form in self.haupt.FARBSCHWAECHEN:
            if form == "keine":
                continue
            for design, palette in self.gui._THEMES.items():
                mit = dict(palette)
                mit.update(self.gui._farbschwaeche_satz(form, design))
                grund = self.haupt.farbe_wie_gesehen(mit["bg_card"], form)
                for schluessel in BEDEUTUNG:
                    if not mit.get(schluessel):
                        continue
                    with self.subTest(form=form, design=design, farbe=schluessel):
                        d = self.haupt.farbabstand(
                            self.haupt.farbe_wie_gesehen(mit[schluessel], form),
                            grund)
                        self.assertGreaterEqual(
                            d, SCHWELLE,
                            "%s auf der Karte nur %.1f" % (schluessel, d))


class EinstellungTests(unittest.TestCase):
    """Die Auswahl muss ankommen und erhalten bleiben."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls.quelle = HAUPTDATEI.read_text(encoding="utf-8")

    def test_die_palette_entsteht_an_einer_stelle(self) -> None:
        """Vorher stand ``dict(self._THEMES[...])`` an zwei Stellen.

        Wer nur eine davon anfasst, bekommt ein Programm, das sich beim
        Designwechsel anders verhält als beim Start.
        """
        self.assertEqual(self.quelle.count("dict(self._THEMES[theme_key])"), 0)
        self.assertGreaterEqual(self.quelle.count("self._palette_bauen("), 2)

    def test_die_einstellung_wird_gespeichert(self) -> None:
        self.assertIn('self._save_setting("farbschwaeche"', self.quelle)
        self.assertIn('self._load_setting_static("farbschwaeche", "keine")',
                      self.quelle)

    def test_eine_unsinnige_einstellung_faellt_auf_keine_zurueck(self) -> None:
        anfang = self.quelle.index('_saved_schwaeche = self._load_setting_static')
        block = self.quelle[anfang:anfang + 260]
        self.assertIn("not in FARBSCHWAECHEN", block)
        self.assertIn('_saved_schwaeche = "keine"', block)

    def test_die_auswahl_wirkt_sofort(self) -> None:
        anfang = self.quelle.index("def _schwaeche_gewaehlt")
        block = self.quelle[anfang:anfang + 900]
        self.assertIn("self._apply_theme(self._current_theme)", block)

    def test_alle_formen_sind_uebersetzt(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for form in self.haupt.FARBSCHWAECHEN:
            with self.subTest(form=form):
                eintrag = STRINGS["settings_dialog.farbschwaeche_%s" % form]
                self.assertIn("de", eintrag)
                self.assertIn("en", eintrag)
                self.assertTrue(eintrag["de"].strip())

    def test_die_haeufigste_form_ist_benannt(self) -> None:
        """Wer die Liste sieht, soll wissen, was er wählt."""
        from ps5_validator.utils.i18n import STRINGS
        self.assertIn("Grün",
                      STRINGS["settings_dialog.farbschwaeche_deuteranopie"]["de"])

    def test_die_diagnose_prueft_alle_formen(self) -> None:
        """Nicht nur die eingestellte - sonst fällt eine neue Farbe erst auf,
        wenn jemand mit genau dieser Form sie sieht."""
        anfang = self.quelle.index("# -- Farbschwaeche ---")
        block = self.quelle[anfang:anfang + 1800]
        self.assertIn("for form in FARBSCHWAECHEN", block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
