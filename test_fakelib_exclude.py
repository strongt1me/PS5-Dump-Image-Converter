# -*- coding: utf-8 -*-
"""ShadowMount+ ``fakelib_exclude``: Aufgabe 7 warnt, bevor sie wirkungslos ablegt.

Ab ShadowMount+ 1.7beta4 schaltet ``fakelib_exclude=<TITLE_ID>`` (wiederholbar)
fuer den Titel **jede** fakelib ab - die des Spiels, Backport, globale und den
Cache (Diff 1.7beta3...1.7beta4, 04.10.2026). Was Aufgabe 7 oder der
Mitschnitt-Assistent dann ablegt, laedt ShadowMount+ nicht - ohne Meldung.
Nutzerentscheid vom 04.10.2026: "Ja, warnen". Beide fragen deshalb nach
(Abbrechen / Trotzdem); umgestellt wird der Eintrag nicht.

Bewacht wird die Regel (``_ampr_titel_ohne_fakelib``) und der Ablauf der
Automatik mit nachgebildeter Konsole. Der Mitschnitt-Assistent laeuft gegen
eine echte FTP-Stube in ``test_ampr_mitschnitt_shadowmount.py``.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("fakelib_exclude")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ini_config                  # noqa: E402
from ps5_validator.utils import shadowmount_generation as sg  # noqa: E402

TITEL = "PPSA01234"
GUI = APP.PS5ConverterGUI


class RegelTests(unittest.TestCase):

    def test_der_schluessel_ist_der_von_shadowmount(self) -> None:
        self.assertEqual("fakelib_exclude", sg.FAKELIB_AUSSCHLUSS)
        self.assertIn(sg.FAKELIB_AUSSCHLUSS, ini_config.WIEDERHOLBARE_SCHLUESSEL)

    def test_eingetragener_titel(self) -> None:
        for config in ("fakelib_exclude=%s\n" % TITEL,
                       "fakelib_exclude=CUSA00001\r\nfakelib_exclude=%s\r\n" % TITEL,
                       "fakelib_exclude = %s \n" % TITEL.lower(),
                       "fakelib_exclude=CUSA00001, %s\n" % TITEL):
            for generation in (sg.NEU, "", None):
                with self.subTest(config=config, generation=generation):
                    self.assertTrue(GUI._ampr_titel_ohne_fakelib(config, TITEL, generation))

    def test_gegenproben(self) -> None:
        """Anderer Titel, auskommentiert, nur global, leer, alte Fassung."""
        faelle = (
            ("fakelib_exclude=CUSA00001\n", TITEL, sg.NEU),
            ("# fakelib_exclude=%s\n" % TITEL, TITEL, sg.NEU),
            ("global_fakelib_exclude=%s\n" % TITEL, TITEL, sg.NEU),
            ("", TITEL, sg.NEU),
            ("fakelib_exclude=%s\n" % TITEL, "", sg.NEU),
            # Bis alpha13fix1 gibt es den Schluessel nicht - er wirkt dort nicht.
            ("fakelib_exclude=%s\n" % TITEL, TITEL, sg.ALT),
        )
        for config, titel, generation in faelle:
            with self.subTest(config=config, titel=titel, generation=generation):
                self.assertFalse(GUI._ampr_titel_ohne_fakelib(config, titel, generation))

    def test_global_fakelib_exclude_bleibt_wie_es_war(self) -> None:
        """Die alte Abfrage (Vorgabe) liest weiter nur global_fakelib_exclude."""
        self.assertTrue(GUI._ampr_mitschnitt_titel_ausgenommen(
            "global_fakelib_exclude=%s\n" % TITEL, TITEL))
        self.assertFalse(GUI._ampr_mitschnitt_titel_ausgenommen(
            "fakelib_exclude=%s\n" % TITEL, TITEL))


def _gui(testfall: unittest.TestCase, config: str, antwort: "str | None"):
    """Die Automatik mit nachgebildeter Konsole - keine Datei wird geschrieben.

    ``antwort=None``: Jede Rueckfrage ist ein Fehler. Weil ``except Exception``
    in der Automatik den Fehler schlucken koennte, wird am Ende auch von aussen
    geprueft (``test_qualitaetslauf.VerschluckterStubfehlerTests``).
    """
    gui = GUI.__new__(GUI)
    gui._current_language = "de"
    gui.root = mock.Mock()
    ftp = mock.MagicMock()
    gui._smgen_texte = lambda: None
    gui._ampr_gen_adresse_finden = lambda *_a: "10.0.0.5"
    gui._ampr_ftp_connect = lambda *_a: ftp
    gui._ps5_ftp_port = lambda: 2121
    gui._ampr_gen_config_lesen = lambda _ftp: config
    gui._ampr_ftp_is_dir = lambda *_a: False
    gui._ampr_gen_log_lesen = lambda _ftp: ""
    gui._ampr_ablage_wahl = lambda: sg.ORT_BACKPORT
    gui._ampr_gen_spiele_finden = lambda _ftp: [{
        "pfad": "/data/homebrew/GAME", "title_id": TITEL,
        "scanpath": "/data/homebrew", "name": "Spiel", "quelle": "Ordner"}]
    gui._ampr_ftp_ensure_dir = mock.MagicMock(return_value=True)
    # Leerer Vorrat: Die Automatik endet mit "amprgen.no_store" - so zeigt sich,
    # ob sie hinter der Warnung weiterlief, ohne dass etwas abgelegt wird.
    gui._ampr_alle_fassungen = mock.MagicMock(return_value=[])
    if antwort is None:
        gui._ampr_gen_frage = mock.Mock(side_effect=AssertionError("unerwartete Frage"))
        testfall.addCleanup(gui._ampr_gen_frage.assert_not_called)
    else:
        gui._ampr_gen_frage = mock.Mock(return_value=antwort)
    return gui, ftp


class AutomatikTests(unittest.TestCase):

    def _lauf(self, config: str, antwort: "str | None", generation: str = sg.NEU):
        gui, ftp = _gui(self, config, antwort)
        meldungen: list[str] = []
        gui._ampr_gen_automatik(generation, None, meldungen.append)
        return gui, ftp, meldungen

    def test_abbrechen_legt_nichts_ab(self) -> None:
        gui, ftp, meldungen = self._lauf("fakelib_exclude=%s\n" % TITEL, "stop")
        gui._ampr_gen_frage.assert_called_once()
        frage = gui._ampr_gen_frage.call_args.args
        self.assertEqual(gui._t("amprgen.q_excluded"), frage[1])
        self.assertIn("fakelib_exclude=%s" % TITEL, frage[2])
        self.assertEqual(["stop", "weiter"], [o[0] for o in frage[3]])
        self.assertIn("!! " + gui._t("amprgen.excluded", title_id=TITEL), meldungen)
        self.assertIn(gui._t("amprgen.cancelled"), meldungen)
        gui._ampr_alle_fassungen.assert_not_called()
        gui._ampr_ftp_ensure_dir.assert_not_called()
        ftp.storbinary.assert_not_called()

    def test_abbruch_des_dialogs_zaehlt_als_abbrechen(self) -> None:
        gui, _ftp, meldungen = self._lauf("fakelib_exclude=%s\n" % TITEL, "")
        self.assertIn(gui._t("amprgen.cancelled"), meldungen)
        gui._ampr_alle_fassungen.assert_not_called()

    def test_trotzdem_laeuft_weiter(self) -> None:
        gui, _ftp, meldungen = self._lauf("fakelib_exclude=%s\n" % TITEL, "weiter")
        gui._ampr_alle_fassungen.assert_called_once()
        self.assertIn(gui._t("amprgen.no_store"), meldungen)
        self.assertNotIn(gui._t("amprgen.cancelled"), meldungen)

    def test_ohne_eintrag_keine_frage(self) -> None:
        """Gegenprobe: anderer Titel und global_fakelib_exclude - die Automatik fragt nicht."""
        gui, _ftp, meldungen = self._lauf(
            "fakelib_exclude=CUSA00001\nglobal_fakelib_exclude=%s\n" % TITEL, None)
        gui._ampr_gen_frage.assert_not_called()
        gui._ampr_alle_fassungen.assert_called_once()
        self.assertNotIn("!! " + gui._t("amprgen.excluded", title_id=TITEL), meldungen)

    def test_lokal_ohne_konsole_keine_frage(self) -> None:
        """Ohne Konsole gibt es keine config.ini - und damit nichts zu warnen."""
        gui, _ftp = _gui(self, "fakelib_exclude=%s\n" % TITEL, "lokal")
        gui._ampr_gen_adresse_finden = lambda *_a: ""
        gui._ampr_gen_ordner_fragen = lambda _f: ""
        meldungen: list[str] = []
        gui._ampr_gen_automatik(sg.NEU, None, meldungen.append)
        fragen = [c.args[1] for c in gui._ampr_gen_frage.call_args_list]
        self.assertNotIn(gui._t("amprgen.q_excluded"), fragen)

    def test_die_texte_nennen_beide_sprachen_und_den_weg(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for kennung in ("amprgen.q_excluded_why", "amprmitschnitt.q_excluded_why"):
            for sprache, weg in (("de", "WEITERE TOOLS"), ("en", "MORE TOOLS")):
                with self.subTest(kennung=kennung, sprache=sprache):
                    text = STRINGS[kennung][sprache]
                    self.assertIn("1.7beta4", text)
                    self.assertIn("{title_id}", text)
                    self.assertIn(weg, text)


if __name__ == "__main__":
    unittest.main()
