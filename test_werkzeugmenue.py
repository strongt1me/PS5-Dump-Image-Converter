"""Tests fuer die Werkzeuge im Menue "WEITERE TOOLS".

Beim Praxistest fiel auf, dass vier Module zwar in die EXE gebuendelt wurden
(hiddenimports in der .spec), vom Programm aus aber gar nicht erreichbar waren:
`self_reader`, `pkg_writer`, `dpi_upload` und `dump_rename` hatten ausser ihren
eigenen Unittests keinen Aufrufer.

Aufgeloest wurde das so:
- `self_reader`, `dump_rename` und `pkg_writer` haben jeweils ein Fenster bekommen.
- `dpi_upload` bleibt als Quelltext liegen, wandert aber nicht mehr in die EXE:
  der etaHEN-Dienst, gegen den es arbeiten wuerde, war nie erprobbar.

Diese Tests halten beides fest.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP

SPEC = PROJEKT / "PS5ImageConverter_Pro.spec"


class MenueVerdrahtungTests(unittest.TestCase):
    """Jeder Menueeintrag muss auf eine tatsaechlich vorhandene Methode zeigen."""

    def test_alle_eintraege_haben_eine_methode(self) -> None:
        for schluessel, methode in APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES:
            with self.subTest(eintrag=schluessel):
                self.assertTrue(hasattr(APP.PS5ConverterGUI, methode),
                                f"{methode} fehlt")
                self.assertTrue(callable(getattr(APP.PS5ConverterGUI, methode)))

    def test_alle_beschriftungen_sind_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel, _methode in APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES:
            with self.subTest(eintrag=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))

    def test_die_drei_wiederbelebten_werkzeuge_sind_dabei(self) -> None:
        methoden = {m for _k, m in APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES}
        for erwartet in ("_show_self_inspector", "_show_dump_rename", "_show_debug_pkg_builder"):
            with self.subTest(methode=erwartet):
                self.assertIn(erwartet, methoden)


class ErreichbarkeitTests(unittest.TestCase):
    """Kein Modul soll ungenutzt mitgeliefert werden."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        cls.spec = SPEC.read_text(encoding="utf-8")

    def test_wiederbelebte_module_werden_importiert(self) -> None:
        for modul in ("self_reader", "dump_rename", "pkg_writer"):
            with self.subTest(modul=modul):
                self.assertIn(f"ps5_validator.utils.{modul} import", self.quelltext)

    def test_gebuendelt_wird_nur_was_erreichbar_ist(self) -> None:
        for modul in ("self_reader", "dump_rename", "pkg_writer"):
            with self.subTest(modul=modul):
                self.assertIn(f"'ps5_validator.utils.{modul}'", self.spec)

    def test_dpi_upload_wandert_nicht_in_die_exe(self) -> None:
        self.assertNotIn("'ps5_validator.utils.dpi_upload'", self.spec)

    def test_dpi_upload_bleibt_als_quelltext_erhalten(self) -> None:
        self.assertTrue((PROJEKT / "ps5_validator" / "utils" / "dpi_upload.py").is_file())
        self.assertTrue((PROJEKT / "test_dpi_upload.py").is_file())


class DumpUmbenennenTests(unittest.TestCase):
    """Die Namensbildung, wie das Fenster sie verwendet."""

    def setUp(self) -> None:
        from ps5_validator.utils import dump_rename
        self.dr = dump_rename

    def test_vorschlaege_aus_vollstaendigen_metadaten(self) -> None:
        vorschlaege = self.dr.build_presets("PPSA18089", "Matchbox™ Driving Adventures",
                                            "01.000.001", True, True)
        self.assertEqual(vorschlaege[self.dr.PRESET_PPSA_ONLY], "PPSA18089")
        self.assertTrue(vorschlaege[self.dr.PRESET_PPSA_TITLE].startswith("PPSA18089 "))
        self.assertIn("(01.000.001)", vorschlaege[self.dr.PRESET_PPSA_TITLE_VERSION])

    def test_ohne_title_id_keine_vorschlaege(self) -> None:
        vorschlaege = self.dr.build_presets("", "Irgendwas", "01.000.000", False, True)
        self.assertEqual(set(vorschlaege.values()), {""})

    def test_einschaetzung_haengt_an_den_metadaten(self) -> None:
        self.assertEqual(self.dr.compute_confidence(True, True, True), self.dr.CONFIDENCE_READY)
        self.assertEqual(self.dr.compute_confidence(True, False, True), self.dr.CONFIDENCE_NEEDS_REVIEW)
        self.assertEqual(self.dr.compute_confidence(False, True, True), self.dr.CONFIDENCE_FAILED)

    def test_ungueltige_pfadzeichen_verschwinden(self) -> None:
        self.assertEqual(self.dr.sanitize_name('Spiel: "Teil/2"'), "Spiel Teil2")


class DebugPaketTests(unittest.TestCase):
    """Der Bau schreibt ein Paket, das der eigene Reader wieder versteht."""

    def test_rundlauf_mit_echter_param_json(self) -> None:
        from ps5_validator.utils.pkg_writer import build_debug_pkg
        from ps5_validator.utils import pkg_reader

        param = {
            "titleId": "PPSA18089",
            "contentId": "EP0001-PPSA18089_00-MATCHBOX00000000",
            "contentVersion": "01.000.001",
            "localizedParameters": {"defaultLanguage": "de-DE",
                                    "de-DE": {"titleName": "Testtitel"}},
        }
        with tempfile.TemporaryDirectory() as ordner:
            ziel = os.path.join(ordner, "test.pkg")
            ergebnis = build_debug_pkg(ziel, param["contentId"], param)
            self.assertTrue(os.path.isfile(ziel))
            self.assertEqual(ergebnis["content_id"], param["contentId"])
            self.assertGreater(ergebnis["size"], 0)

            info = pkg_reader.read_pkg(ziel)
            self.assertIsNotNone(info.header)
            assert info.header is not None
            self.assertEqual(info.header.content_id, param["contentId"])
            self.assertGreater(len(info.entries), 0)


class SammelkonvertierungTests(unittest.TestCase):
    """Eine gemischte Auswahl darf nicht am ersten passenden Eintrag scheitern.

    Lauf 17 des Praxistests: drei Quellen (.ffpfsc, .exfat, .ffpkg) nach
    .ffpfsc. Die Vorabpruefung lehnte den GESAMTEN Lauf ab, weil die erste
    Quelle bereits das Zielformat hatte - die beiden anderen waeren sauber
    konvertierbar gewesen.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

    def _pruefer(self, quellen: list[str]):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._batch_sources = quellen
        return gui

    def test_gemischte_auswahl_wird_zugelassen(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfade = []
            for name in ("a.ffpfsc", "b.exfat", "c.ffpkg"):
                p = os.path.join(ordner, name)
                Path(p).write_bytes(b"x")
                pfade.append(p)
            gui = self._pruefer(pfade)
            grund = APP.PS5ConverterGUI._validate_requested_conversion(
                gui, "batch_convert", "", "ffpfsc")
            self.assertEqual(grund, "", f"unerwartet abgelehnt: {grund}")

    def test_wenn_alles_schon_passt_bleibt_es_eine_ablehnung(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfade = []
            for name in ("a.ffpfsc", "b.ffpfsc"):
                p = os.path.join(ordner, name)
                Path(p).write_bytes(b"x")
                pfade.append(p)
            gui = self._pruefer(pfade)
            grund = APP.PS5ConverterGUI._validate_requested_conversion(
                gui, "batch_convert", "", "ffpfsc")
            self.assertIn("identisch", grund)

    def test_leere_auswahl_bleibt_ein_hinweis(self) -> None:
        gui = self._pruefer([])
        grund = APP.PS5ConverterGUI._validate_requested_conversion(
            gui, "batch_convert", "", "ffpfsc")
        self.assertIn("Quelldateien", grund)

    def test_ueberspringer_gilt_nicht_als_fehlschlag(self) -> None:
        block = self.quelltext[self.quelltext.index("bereits_im_zielformat"):][:900]
        self.assertIn("batch.skipped_same_format", block)
        # all_ok darf im Ueberspringer-Zweig nicht angefasst werden
        vor_else = block[:block.index("else:")]
        self.assertNotIn("all_ok = False", vor_else)

    def test_lauf_ohne_jede_arbeit_meldet_fehler(self) -> None:
        self.assertIn("batch.nothing_to_do", self.quelltext)


class KontextmenueTests(unittest.TestCase):
    """Das Kontextmenue stand bis v1.8.47 fest auf Deutsch im Quelltext.

    Ein Abgleich der Uebersetzungstabelle konnte das nicht finden, weil die
    Woerter gar nicht darin standen - nur der Blick auf den Erzeugungscode.
    Diese Tests halten fest, dass die Beschriftungen aus der Tabelle kommen.
    """

    @classmethod
    def setUpClass(cls) -> None:
        from ps5_validator.utils.i18n import STRINGS
        cls.strings = STRINGS
        cls.eintraege = APP.PS5ConverterGUI._CONTEXT_MENU_ENTRIES

    def test_kein_fester_deutscher_text_mehr(self) -> None:
        quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        for wort in ('label="Vollbild"', 'label="Verkleinern / Zentrieren"'):
            self.assertNotIn(wort, quelltext)

    def test_jeder_schluessel_liegt_in_beiden_sprachen_vor(self) -> None:
        for schluessel, _befehl in self.eintraege:
            if schluessel is None:
                continue
            self.assertIn(schluessel, self.strings, f"Schluessel fehlt: {schluessel}")
            for sprache in ("de", "en"):
                text = self.strings[schluessel].get(sprache, "")
                self.assertTrue(text.strip(), f"{schluessel} ohne {sprache}-Text")

    def test_englisch_unterscheidet_sich_vom_deutschen(self) -> None:
        """Sonst waere der Eintrag nur scheinbar uebersetzt."""
        for schluessel, _befehl in self.eintraege:
            if schluessel is None:
                continue
            eintrag = self.strings[schluessel]
            self.assertNotEqual(eintrag["de"], eintrag["en"], schluessel)

    def test_jeder_befehl_existiert(self) -> None:
        for schluessel, befehl in self.eintraege:
            if schluessel is None:
                continue
            self.assertTrue(hasattr(APP.PS5ConverterGUI, befehl),
                            f"Methode fehlt: {befehl}")

    def test_trennstrich_hat_keinen_befehl(self) -> None:
        for schluessel, befehl in self.eintraege:
            if schluessel is None:
                self.assertEqual(befehl, "")

    def test_sprachwechsel_erfasst_das_kontextmenue(self) -> None:
        quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        stelle = quelltext.index("def _apply_language")
        block = quelltext[stelle:stelle + 6000]
        self.assertIn("_CONTEXT_MENU_ENTRIES", block)


class DesignwechselTests(unittest.TestCase):
    """Vier Widget-Gruppen wurden vom Designwechsel nicht erfasst.

    Gemessen an der laufenden Oberflaeche: 14 Elemente behielten die Farben des
    dunklen Designs, im hellen Design mit Kontrasten bis herunter auf 1,19.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        stelle = cls.quelltext.index("def _apply_theme")
        cls.block = cls.quelltext[stelle:stelle + 6000]

    def test_alle_vier_nachzieher_werden_aufgerufen(self) -> None:
        for name in ("_theme_titelleiste_nachziehen", "_theme_rundknoepfe_nachziehen",
                     "_theme_sidebar_fuss_nachziehen", "_theme_menues_nachziehen"):
            self.assertIn(f"self.{name}()", self.block, f"{name} wird nicht gerufen")

    def test_titelleiste_kennt_jeden_knopf(self) -> None:
        tabelle = APP.PS5ConverterGUI._TITELLEISTE_SCHRIFTFARBEN
        import re
        erzeugt = set(re.findall(r"self\.(_btn_[a-z0-9_]*title[a-z0-9_]*)\s*=\s*tk\.Button",
                                 self.quelltext))
        fehlen = sorted(erzeugt - set(tabelle))
        self.assertEqual(fehlen, [], f"nicht in der Farbtabelle: {fehlen}")

    def test_farbschluessel_gibt_es_in_allen_designs(self) -> None:
        themes = APP.PS5ConverterGUI._THEMES
        for knopf, schluessel in APP.PS5ConverterGUI._TITELLEISTE_SCHRIFTFARBEN.items():
            for name, palette in themes.items():
                self.assertIn(schluessel, palette, f"{name} kennt {schluessel} nicht ({knopf})")

    def test_rundknopf_faerbt_die_flaeche_nicht_die_fuellung(self) -> None:
        """bg= waere die Fuellfarbe - das wuerde die Aufgaben-Hervorhebung loeschen."""
        stelle = self.quelltext.index("def _theme_rundknoepfe_nachziehen")
        block = self.quelltext[stelle:stelle + 1400]
        self.assertIn("configure(background=neu)", block)
        self.assertNotIn("configure(bg=", block)

    def test_alle_designs_haben_denselben_satz_schluessel(self) -> None:
        themes = APP.PS5ConverterGUI._THEMES
        saetze = {name: set(p) for name, p in themes.items()}
        alle = set().union(*saetze.values())
        for name, s in saetze.items():
            self.assertEqual(sorted(alle - s), [], f"{name} fehlen Schluessel")


if __name__ == "__main__":
    unittest.main(verbosity=2)
