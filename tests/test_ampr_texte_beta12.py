# -*- coding: utf-8 -*-
"""AMPR-Meldungen nennen bei ShadowMount+ ab 1.7beta12 die richtige Datei (Nutzerwunsch 16.11.2026).

Ab 1.7beta12 (Format 2) stehen Einstellungen je Spiel (``fakelib_exclude``, ``fakelib_mode``, ``global_fakelib_exclude`` ...) in der
``profiles.ini``, die Vorgaben fuer alle Spiele (``fakelib_default_mode``) bleiben in der ``config.ini``. Die Schluesselnamen in den
Meldungen uebersetzt ``_t`` schon (``shadowmount_config.uebersetzen``); die Dateiangabe aber lautete in drei Texten immer "In der
config.ini steht ...": ``amprgen.excluded``, ``amprmitschnitt.sm_excluded`` und ``amprmitschnitt.q_excluded_why``. Sie tragen jetzt
den Platzhalter ``{datei}``, den ``_sm_datei_des_eintrags`` fuellt.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_texte_beta12")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import shadowmount_config as sm_cfg   # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

G = APP.PS5ConverterGUI
QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
SCHLUESSEL = ("amprgen.excluded", "amprmitschnitt.sm_excluded", "amprmitschnitt.q_excluded_why")
SPRACHEN = ("de", "en", "es", "it", "fr")


def _gui(format_: str):
    gui = G.__new__(G)
    gui._current_language = "de"
    gui._sm_format_gespeichert = lambda: format_
    return gui


class DateiDesEintragsTests(unittest.TestCase):
    def test_format_2_je_spiel_steht_in_der_profiles_ini(self) -> None:
        gui = _gui(sm_cfg.FORMAT_V2)
        for eintrag in ("fakelib_exclude=PPSA01234", "fakelib_mode=PPSA01234:disabled", "global_fakelib_exclude=PPSA01234"):
            with self.subTest(eintrag=eintrag):
                self.assertEqual("profiles.ini", gui._sm_datei_des_eintrags(eintrag))

    def test_format_2_die_vorgabe_fuer_alle_bleibt_in_der_config_ini(self) -> None:
        self.assertEqual("config.ini", _gui(sm_cfg.FORMAT_V2)._sm_datei_des_eintrags("fakelib_default_mode=disabled"))

    def test_vor_beta12_ist_alles_die_config_ini(self) -> None:
        for format_ in (sm_cfg.FORMAT_V1, ""):
            for eintrag in ("fakelib_exclude=PPSA01234", "fakelib_mode=PPSA01234:disabled", "fakelib_default_mode=disabled"):
                with self.subTest(format=format_, eintrag=eintrag):
                    self.assertEqual("config.ini", _gui(format_)._sm_datei_des_eintrags(eintrag))

    def test_ein_leerer_oder_unbekannter_eintrag_bleibt_bei_der_config_ini(self) -> None:
        gui = _gui(sm_cfg.FORMAT_V2)
        for eintrag in ("", "irgendwas", "update_emulators=1"):
            with self.subTest(eintrag=eintrag):
                self.assertEqual("config.ini", gui._sm_datei_des_eintrags(eintrag))


class TexteTests(unittest.TestCase):
    def test_alle_drei_texte_haben_in_jeder_sprache_den_platzhalter_und_kein_festes_config_ini(self) -> None:
        for schluessel in SCHLUESSEL:
            for sprache in SPRACHEN:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertIn("{datei}", text)
                    self.assertIn("{eintrag}", text)
                    self.assertNotIn("config.ini", text, "die Datei kommt aus dem Platzhalter")

    def test_format_2_nennt_die_profiles_ini(self) -> None:
        gui = _gui(sm_cfg.FORMAT_V2)
        text = gui._t("amprgen.excluded", title_id="PPSA01234", eintrag="fakelib_exclude=PPSA01234",
                      datei=gui._sm_datei_des_eintrags("fakelib_exclude=PPSA01234"))
        self.assertTrue(text.startswith("In der profiles.ini von ShadowMount+ steht"), text)
        self.assertNotIn("In der config.ini", text)

    def test_vor_beta12_bleibt_es_wie_es_war(self) -> None:
        gui = _gui(sm_cfg.FORMAT_V1)
        text = gui._t("amprgen.excluded", title_id="PPSA01234", eintrag="fakelib_exclude=PPSA01234",
                      datei=gui._sm_datei_des_eintrags("fakelib_exclude=PPSA01234"))
        self.assertEqual("In der config.ini von ShadowMount+ steht „fakelib_exclude=PPSA01234“ – ab ShadowMount+ 1.7beta4 wird für "
                         "PPSA01234 dadurch keine fakelib eingehängt.", text)

    def test_die_vorgabe_fuer_alle_spiele_nennt_auch_bei_beta12_die_config_ini(self) -> None:
        gui = _gui(sm_cfg.FORMAT_V2)
        text = gui._t("amprmitschnitt.sm_excluded", title_id="PPSA01234", eintrag="fakelib_default_mode=disabled",
                      datei=gui._sm_datei_des_eintrags("fakelib_default_mode=disabled"))
        self.assertTrue(text.startswith("In der config.ini steht"), text)

    def test_der_hinweistext_im_dialog_nennt_die_datei_des_eintrags(self) -> None:
        gui = _gui(sm_cfg.FORMAT_V2)
        text = gui._t("amprmitschnitt.q_excluded_why", title_id="PPSA01234", eintrag="fakelib_mode=PPSA01234:disabled",
                      datei=gui._sm_datei_des_eintrags("fakelib_mode=PPSA01234:disabled"))
        self.assertTrue(text.startswith("In der profiles.ini steht"), text)


class AufrufTests(unittest.TestCase):
    def test_jede_stelle_gibt_die_datei_mit(self) -> None:
        """Ohne ``datei=`` bliebe im Text der Platzhalter ``{datei}`` stehen (und ``format`` scheiterte)."""
        for schluessel in SCHLUESSEL:
            anfang = 0
            gefunden = 0
            while True:
                anfang = QUELLE.find('self._t("%s"' % schluessel, anfang)
                if anfang < 0:
                    break
                gefunden += 1
                aufruf = QUELLE[anfang:QUELLE.index(")", QUELLE.index("sperr_eintrag", anfang) + 60) + 1]
                with self.subTest(schluessel=schluessel, stelle=gefunden):
                    self.assertIn("datei=self._sm_datei_des_eintrags(sperr_eintrag)", aufruf)
                anfang += 10
            self.assertGreaterEqual(gefunden, 1, schluessel)

    def test_nur_diese_drei_stellen_benutzen_die_texte(self) -> None:
        """Wer einen der drei Schluessel ohne ``datei`` aufriefe, bekaeme ``{datei}`` im Text - es gibt genau die drei Aufrufe."""
        for schluessel in SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertEqual(1, QUELLE.count('self._t("%s"' % schluessel))


if __name__ == "__main__":
    unittest.main()
