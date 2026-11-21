"""Waechter: Im BACKPORT-Fenster gibt der Anwender nur die Firmware an - der Rest geschieht automatisch.

Nutzerwunsch 21.11.2026: "Der User soll einfach die gewuenschte FW angeben, der Rest soll automatisch erfolgen." Vorher
standen im Fenster Haken (Sicherung, nur benoetigte Bibliotheken, Stubs, Korrekturprofil, Landeplatz), Ordnerfelder
(eigener Bibliotheksordner, Firmware-Ordner fuer die NID-Analyse, Firmware-Referenz) und eigene Zielwerte. Jetzt:
  * Stubs, Korrekturprofil und Landeplatz sind immer an, "nur benoetigte" immer aus, die Sicherung laeuft immer;
  * Haken und Felder sind entfallen; was in der Einstellungsdatei noch steht, gilt weiter und wird genannt.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("backport_automatik")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
SPRACHEN = ("de", "en", "es", "it", "fr")

#: Texte der entfallenen Haken und Felder - sie duerfen weder in der Uebersetzungstabelle noch im Hauptmodul stehen.
TOTE_SCHLUESSEL = (
    "backport.advanced_toggle_open", "backport.advanced_toggle_closed", "backport.option_backup",
    "backport.option_backup_hint", "backport.options_auto", "backport.option_minimal", "backport.option_minimal_hint",
    "backport.option_stubs", "backport.option_stubs_hint", "backport.option_profile", "backport.option_profile_hint",
    "backport.option_korr_hinweis", "backport.fakelib_basis_choose", "backport.fakelib_basis_hint",
    "backport.fw_analyse_choose", "backport.fw_analyse_hint", "backport.fw_referenz_hint", "backport.eigene_ps5",
    "backport.eigene_ps4", "backport.eigene_fw", "backport.eigene_hint", "backport.option_landeplatz",
    "backport.option_landeplatz_kurz", "backport.option_landeplatz_hint",
    # Entwurf A (21.11.2026): Kopfzeilen und lange Erklaerung ersetzt durch Pillen und kurze Zeilen.
    "backport.field_title", "backport.field_title_id", "backport.field_version", "backport.target_label",
    "backport.fw_vorschlag",
)

#: Neue Texte des aufgeraeumten Fensters (Entwurf A) und ihre Platzhalter.
PILLENTEXTE = {
    "backport.chip_version": "{version}",
    "backport.konsole_stand": "{konsole}",
    "backport.auto_bibliotheken": "{ordner}",
    "backport.required_firmware_hint": "{fw}",
    "backport.subtitle": "{path}",
    "backport.auto_sicherung": "",
    "backport.auto_param": "",
    "backport.auto_funktionen": "",
    "backport.hint_unsigned": "",
}

with io.open(HAUPTDATEI, encoding="utf-8") as _fh:
    QUELLE = _fh.read()
_BAUM = ast.parse(QUELLE)
_KLASSE = next(k for k in ast.walk(_BAUM) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")


def _methode(name: str) -> str:
    return ast.unparse(next(m for m in _KLASSE.body if isinstance(m, ast.FunctionDef) and m.name == name))


def _gui(einstellungen: dict | None = None):
    gui = GUI.__new__(GUI)
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._t = lambda schluessel, **w: schluessel + str(sorted(w.items()))
    einstellungen = einstellungen or {}
    gui._load_setting = lambda schluessel, vorgabe=None: einstellungen.get(schluessel, vorgabe)
    return gui


class AutomatikWerteTests(unittest.TestCase):
    def test_zusaetze_sind_immer_an_und_nur_benoetigt_immer_aus(self) -> None:
        alt_gespeichert = {"backport_stubs": False, "backport_profile": False, "backport_stubs_landeplatz": False,
                           "backport_fakelib_nur_benoetigt": True}
        for name, einstellungen in (("leer", {}), ("frueher abgewaehlt", alt_gespeichert)):
            gui = _gui(dict(einstellungen))
            with self.subTest(einstellungen=name):
                self.assertTrue(gui._backport_stubs_an())
                self.assertTrue(gui._backport_profile_an())
                self.assertTrue(gui._backport_landeplatz_an())
                self.assertFalse(gui._backport_fakelib_minimal())

    def test_ohne_exporttabelle_meldet_es_der_lauf_jetzt_statt_still_zu_schweigen(self) -> None:
        """Vorher (Stubs aus) kehrte die Anwendung ohne ein Wort zurueck; jetzt laeuft sie immer und sagt, was fehlt."""
        with tempfile.TemporaryDirectory() as t:
            dump, basis = Path(t, "dump"), Path(t, "basis")
            dump.mkdir()
            basis.mkdir()
            gui = _gui({})
            neutral = gui._backport_korrekturen_anwenden(str(dump), 9, str(basis), [], None)
            self.assertEqual(neutral, set())
            self.assertEqual([z.split("[")[0] for z in gui.protokoll], ["backport.korr_stub_ohne_tabelle"])


class EigeneEinstellungenTests(unittest.TestCase):
    """Was in der Einstellungsdatei steht, aber im Fenster nicht mehr gesetzt werden kann, wirkt nicht still."""

    def test_nichts_gesetzt_nichts_genannt(self) -> None:
        self.assertEqual(_gui({})._backport_eigene_einstellungen(), [])

    def test_vorhandene_ordner_und_werte_werden_genannt(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            gui = _gui({"backport_fakelib_ordner": t, "backport_fw_analyse_ordner": t,
                        "backport_firmware_referenz": t, "backport_sdk_ps5": "0x04500031"})
            genannt = gui._backport_eigene_einstellungen()
            self.assertEqual(len(genannt), 4, genannt)
            for schluessel in ("backport.fakelib_basis_label", "backport.fw_analyse_label",
                               "backport.fw_referenz_label", "backport.eigene_label"):
                self.assertTrue(any(g.startswith(schluessel) for g in genannt), (schluessel, genannt))

    def test_nicht_vorhandener_ordner_wirkt_nicht_und_wird_nicht_genannt(self) -> None:
        gui = _gui({"backport_fakelib_ordner": os.path.join(tempfile.gettempdir(), "gibt-es-nicht-xyz"),
                    "backport_fw_analyse_ordner": "   "})
        self.assertEqual(gui._backport_eigene_einstellungen(), [])


class FensterVerdrahtungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fenster = _methode("_render_backport_window")

    def test_kein_haken_kein_feld_keine_gespeicherte_wahl(self) -> None:
        for alt in ("Checkbutton(", "Entry(", "BooleanVar(", "_save_setting(", "sicherung_var", "minimal_var",
                    "erweitert", "landeplatz_var", "stubs_var", "profil_var"):
            self.assertNotIn(alt, self.fenster, alt)

    def test_nur_die_firmware_ist_waehlbar(self) -> None:
        self.assertEqual(self.fenster.count("Combobox("), 1)
        self.assertIn("fw_box", self.fenster)

    def test_hinweis_und_eigene_werte_stehen_im_fenster(self) -> None:
        # ast.unparse schreibt Zeichenketten mit einfachen Anfuehrungszeichen.
        # Entwurf A (21.11.2026): Die Beschreibung der Schritte steht als Tooltip an den Haken-Pillen.
        self.assertIn("self._tooltip(pille, 'backport.auto_hinweis'", self.fenster)
        self.assertIn("self._backport_eigene_einstellungen()", self.fenster)
        self.assertIn("self._t('backport.eigene_aktiv'", self.fenster)

    def test_vier_haken_pillen_und_ein_satz_warnung(self) -> None:
        for schluessel in ("backport.auto_sicherung", "backport.auto_param",
                           "backport.auto_bibliotheken", "backport.auto_funktionen"):
            self.assertIn(f"'{schluessel}'", self.fenster, schluessel)
        self.assertIn("gruen=True", self.fenster)
        self.assertIn("self._t('backport.hint_unsigned')", self.fenster)
        self.assertIn("ordner=self._fakelib_ordnername()", self.fenster,
                      "Die Pille der Ersatzbibliotheken nennt den Ablageordner nicht mehr")

    def test_die_langen_erklaerungen_stehen_nicht_mehr_im_fenster(self) -> None:
        """Bibliotheksordner-Zeile samt "fakelib2"-Erklaerung stehen im Handbuch, nicht im Fenster."""
        for alt in ("backport.fakelib_folder_label", "fakelib.folder_fixed", "backport.target_label",
                    "backport.field_title", "backport.fw_vorschlag", "backport.auto_hinweis')"):
            self.assertNotIn(alt, self.fenster, alt)

    def test_sicherung_laeuft_immer(self) -> None:
        """Der Worker bekommt ``sichern`` ohne Haken; nur der Platz entscheidet (und fragt)."""
        self.assertIn("self._backport_platz_entscheiden(ordner, win, messung)", self.fenster)
        self.assertNotIn("if not sicherung", self.fenster)

    def test_beide_wege_nennen_eigene_werte_im_protokoll(self) -> None:
        for name in ("_integration_backport", "_backport_worker"):
            with self.subTest(methode=name):
                text = _methode(name)
                self.assertIn("self._backport_eigene_einstellungen()", text)
                self.assertIn("'backport.eigene_aktiv'", text)


class TexteTests(unittest.TestCase):
    def test_neue_texte_in_fuenf_sprachen(self) -> None:
        for schluessel in ("backport.auto_hinweis", "backport.eigene_aktiv"):
            self.assertEqual(set(STRINGS[schluessel]), set(SPRACHEN), schluessel)
            for sprache in SPRACHEN:
                self.assertTrue(STRINGS[schluessel][sprache].strip(), (schluessel, sprache))
        for sprache in SPRACHEN:
            self.assertIn("{liste}", STRINGS["backport.eigene_aktiv"][sprache], sprache)
        self.assertNotEqual(STRINGS["backport.auto_hinweis"]["de"], STRINGS["backport.auto_hinweis"]["en"])

    def test_texte_des_aufgeraeumten_fensters_in_fuenf_sprachen_mit_platzhaltern(self) -> None:
        for schluessel, platzhalter in PILLENTEXTE.items():
            self.assertEqual(set(STRINGS[schluessel]), set(SPRACHEN), schluessel)
            for sprache in SPRACHEN:
                text = STRINGS[schluessel][sprache]
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(text.strip())
                    if platzhalter:
                        self.assertIn(platzhalter, text)

    def test_die_warnung_ist_ein_kurzer_satz(self) -> None:
        """Sie war ein Absatz mit zwei Aufforderungen; die Sicherung laeuft seit 21.11.2026 ohnehin immer."""
        for sprache in SPRACHEN:
            text = STRINGS["backport.hint_unsigned"][sprache]
            with self.subTest(sprache=sprache):
                self.assertLessEqual(len(text), 150, text)

    def test_tote_texte_sind_weg(self) -> None:
        for schluessel in TOTE_SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertNotIn(schluessel, STRINGS)
                self.assertNotIn('"%s"' % schluessel, QUELLE)

    def test_noch_benutzte_namen_der_eigenen_werte_bleiben(self) -> None:
        """Die Beschriftungen der entfallenen Felder dienen jetzt der Meldung "eigene Werte aus der Einstellungsdatei"."""
        for schluessel in ("backport.fakelib_basis_label", "backport.fw_analyse_label", "backport.fw_referenz_label",
                           "backport.eigene_label", "backport.eigene_ungueltig"):
            self.assertIn(schluessel, STRINGS)
            self.assertIn('"%s"' % schluessel, QUELLE)


if __name__ == "__main__":
    unittest.main()
