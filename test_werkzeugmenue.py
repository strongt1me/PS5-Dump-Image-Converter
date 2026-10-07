"""Tests fuer die Werkzeuge im Menue "WEITERE TOOLS".

Beim Praxistest fiel auf, dass vier Module zwar in die EXE gebuendelt wurden
(hiddenimports in der .spec), vom Programm aus aber gar nicht erreichbar waren:
`self_reader`, `pkg_writer`, `dpi_upload` und `dump_rename` hatten ausser ihren
eigenen Unittests keinen Aufrufer.

Aufgeloest wurde das so:
- `self_reader`, `dump_rename` und `pkg_writer` haben jeweils ein Fenster bekommen.
- `dpi_upload` bleibt als Quelltext liegen, wandert aber nicht mehr in die EXE:
  der etaHEN-Dienst, gegen den es arbeiten wuerde, war nie erprobbar.

Am 22.09.2026 ist das Fenster von `pkg_writer` ("DEBUG-PKG BAUEN") samt Modul
wieder ausgebaut worden: ein unsignierter Eigenbau, an der Konsole nie
getestet - der schwaechere Doppelgaenger von "PKG bauen" (LibProsperoPkg).

Am 02.10.2026 folgte "PKG bauen" selbst, samt SDK-Bauweg (`sony_sdk`) und
GP5-Projekt (`gp5_project`): Die Pakete installierten sich, starteten auf der
Konsole aber nicht (CE-100096-6). Uebrig sind "PS4 & PS5 PKG lesen" und
"PS4 PKG -> Dump Ordner" (Nutzerwunsch, neue Namen).

Diese Tests halten alles fest.
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

    def test_die_wiederbelebten_werkzeuge_sind_dabei(self) -> None:
        methoden = {m for _k, m in APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES}
        for erwartet in ("_show_self_inspector", "_show_dump_rename"):
            with self.subTest(methode=erwartet):
                self.assertIn(erwartet, methoden)

    def test_pkg_bauen_ist_ausgebaut(self) -> None:
        """Seit dem 02.10.2026 baut das Programm keine PKG mehr (Nutzerentscheid).

        Davor gab es "DEBUG-PKG BAUEN" und "Abbild -> PKG" (bis v1.9.41),
        danach ein Fenster "PKG bauen". Keins davon kommt zurueck - auch
        nicht als Methode ohne Menueeintrag.
        """
        methoden = {m for _k, m in APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES}
        schluessel = {k for k, _m in APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES}
        self.assertNotIn("titlebar.pkg_bauen", schluessel)
        for weg in ("_show_pkg_bauen", "_show_debug_pkg_builder",
                    "_show_exfat_pkg_builder", "_sdk_bauweg", "_abbild_zu_dumpordner"):
            with self.subTest(methode=weg):
                self.assertNotIn(weg, methoden)
                self.assertFalse(hasattr(APP.PS5ConverterGUI, weg))

    def test_micromount_ist_ausgebaut(self) -> None:
        """Nutzerwunsch 05.10.2026: "Der Knopf MicroMount inkl. Funktion ... wieder entfernen."

        Weg sind der Menueeintrag, das Fenster samt Vorgaben und der Sendeblock im
        Editor der Konfiguration, der nur fuer MicroMount da war
        (``payload_default_port``). Der Editor selbst bleibt: Er gehoert zu ShadowMount+.
        """
        import inspect
        from ps5_validator.utils.i18n import STRINGS
        gui = APP.PS5ConverterGUI
        eintraege = [(k, m) for k, m in gui._MORE_TOOLS_ENTRIES
                     if "micromount" in (k + m).lower()]
        self.assertEqual([], eintraege, "Der Menueeintrag ist zurueckgekommen.")
        reste = sorted(n for n in vars(gui) if "micromount" in n.lower())
        self.assertEqual([], reste, "Ein Rest des ausgebauten Werkzeugs im Programm.")
        texte = sorted(k for k, t in STRINGS.items()
                       if "micromount" in k.lower()
                       or any("micromount" in str(t.get(s, "")).lower() for s in ("de", "en")))
        self.assertEqual([], texte, "Ein Text spricht noch von dem ausgebauten Werkzeug.")
        parameter = inspect.signature(gui._show_remote_ini_editor).parameters
        self.assertNotIn("payload_default_port", parameter,
                         "Der Sendeblock des Editors gehoerte nur zu MicroMount.")
        self.assertTrue(callable(getattr(gui, "_show_shadowmount_editor", None)),
                        "Der Editor bleibt - er gehoert zu ShadowMount+.")

    def test_unter_weitere_tools_steht_nur_ein_knopf_fuer_ps4_pakete(self) -> None:
        """Nutzerwunsch 05.10.2026: "Nicht dass mehrere PS4 PKG ... Knoepfe in der Liste zu sehen sind."

        Der eine Knopf heisst "PS4 PKG -> OTA". "PS4 PKG -> ffpfsc", "PS4 PKG -> Dump
        Ordner" und "PS4 & PS5 PKG lesen" sind als Eintraege weg - ihre Fenster bleiben
        ueber "PS4 PKG -> OTA" erreichbar (-> ffpfsc, Entpacken ohne OrbisPkgTool, Paketkopf
        lesen im Mehr-Menue); der Leser ist der einzige Weg, ein **PS5**-Paket zu lesen.
        """
        from ps5_validator.utils.i18n import STRINGS
        paare = dict(APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES)
        self.assertEqual("_show_ps4_pkg_converter", paare["titlebar.ps4pkg"])
        self.assertEqual("PS4 PKG Dump & Image Converter", STRINGS["titlebar.ps4pkg"]["de"])
        self.assertEqual("PS4 PKG Dump & Image Converter", STRINGS["titlebar.ps4pkg"]["en"])
        for weg in ("titlebar.ps4_ota", "titlebar.pkg_entpacken", "titlebar.pkg_reader"):
            with self.subTest(eintrag=weg):
                self.assertNotIn(weg, paare)
                self.assertNotIn(weg, STRINGS, "Ein Text ohne Eintrag waere ein toter Schluessel.")
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                nennen_ps4_pakete = [k for k in paare if "PS4 PKG" in STRINGS[k][sprache]]
                self.assertEqual(["titlebar.ps4pkg"], nennen_ps4_pakete)
        for methode in ("_show_ps4_pkg_converter", "_show_pkg_entpacken", "_show_pkg_reader"):
            with self.subTest(methode=methode):
                self.assertTrue(callable(getattr(APP.PS5ConverterGUI, methode, None)),
                                "Das alte Fenster ist ueber das neue noch erreichbar.")


class ErreichbarkeitTests(unittest.TestCase):
    """Kein Modul soll ungenutzt mitgeliefert werden."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        cls.spec = SPEC.read_text(encoding="utf-8")

    def test_wiederbelebte_module_werden_importiert(self) -> None:
        for modul in ("self_reader", "dump_rename"):
            with self.subTest(modul=modul):
                self.assertIn(f"ps5_validator.utils.{modul} import", self.quelltext)

    def test_pkg_writer_ist_ganz_weg(self) -> None:
        self.assertNotIn("pkg_writer", self.quelltext)
        self.assertNotIn("'ps5_validator.utils.pkg_writer'", self.spec)
        self.assertFalse((PROJEKT / "ps5_validator" / "utils" / "pkg_writer.py").exists())

    def test_bauwege_von_pkg_bauen_sind_ganz_weg(self) -> None:
        """Mit "PKG bauen" gingen am 02.10.2026 auch SDK-Bauweg und GP5-Projekt."""
        for modul in ("sony_sdk", "gp5_project"):
            with self.subTest(modul=modul):
                self.assertNotIn(modul, self.quelltext)
                for spec in PROJEKT.glob("PS5ImageConverter_Pro*.spec"):
                    self.assertNotIn("'ps5_validator.utils.%s'" % modul,
                                     spec.read_text(encoding="utf-8"), spec.name)
                self.assertFalse((PROJEKT / "ps5_validator" / "utils"
                                  / ("%s.py" % modul)).exists())
        from ps5_validator.utils import prosperopkg
        for weg in ("bauen", "homebrew_bauen", "pruefen", "zeitgrenze_fuer"):
            with self.subTest(funktion=weg):
                self.assertFalse(hasattr(prosperopkg, weg))

    def test_gebuendelt_wird_nur_was_erreichbar_ist(self) -> None:
        for modul in ("self_reader", "dump_rename"):
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
        # Seit 05.10.2026 "Quellen" statt "Quelldateien": Dump-Ordner sind auch Quellen.
        self.assertIn("Quellen", grund)
        self.assertIn("Dump-Ordner", grund)

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
        """Jeder Titelknopf braucht seinen Eintrag in der Farbtabelle.

        Diese Pruefung war bis zum 06.09.2026 tot. Sie suchte nach
        ``= tk.Button`` - die zwoelf Titelknoepfe entstehen aber ueber
        ``flach_knopf(...)``, seit dem Umbau auf die flache Optik. Der
        Ausdruck traf null Stellen, ``erzeugt`` war leer, ``fehlen`` immer
        ``[]``, und ``assertEqual`` konnte gar nicht mehr fehlschlagen.

        Deshalb steht jetzt eine Zahl daneben: Ohne sie merkt niemand,
        wenn der naechste Umbau den Ausdruck wieder ins Leere laufen laesst.
        Seit dem 25.09.2026 sind es elf: BIBLIOTHEK ist in die Ansicht
        KONSOLE umgezogen (test_bibliothek_seite).
        """
        tabelle = APP.PS5ConverterGUI._TITELLEISTE_SCHRIFTFARBEN
        import re
        erzeugt = set(re.findall(
            r"self\.(_btn_[a-z0-9_]*title[a-z0-9_]*)\s*=\s*(?:tk\.Button|flach_knopf)",
            self.quelltext))
        self.assertGreaterEqual(
            len(erzeugt), 11,
            "Nur %d Titelknoepfe gefunden - der Suchausdruck passt nicht "
            "mehr zum Quelltext, und die Pruefung darunter sieht nichts an."
            % len(erzeugt))
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
