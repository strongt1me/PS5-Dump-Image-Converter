# -*- coding: utf-8 -*-
"""ShadowMount+ aktualisiert die AMPR-Datei von selbst: sichtbar machen und fuer ``ampr-emu-ng`` abstellen (Nutzerwunsch 16.11.2026).

ShadowMount+ (README und ``config.ini.example`` 1.7beta12, ``src/sm_ampr_updater.c``) kann die ``libSceAmpr.sprx`` im fakelib auf zwei
Wegen ueberschreiben:

* ``update_emulators`` (``[emulators] update_enabled``), **Vorgabe an**: ersetzt beim Spielstart die Datei im fakelib durch die aus dem
  Emulator-Ordner;
* ``auto_update_ampr`` (Vorgabe aus): holt 30 Sekunden nach dem Start und danach alle vier Stunden drakmors Fassung von GitHub und legt
  sie im Emulator-Ordner ab.

Fuer NG muss beides aus sein (ausser die NG-Datei liegt selbst im Emulator-Ordner: dort bleibt ``update_emulators`` an). Bisher stand
nur ein Hinweis auf ``update_emulators=0`` im Protokoll, nichts zeigte den Stand, und die Einrichtung verlangte fuer jede Generation
``update_emulators=1`` - wer nach dem Hinweis abgeschaltet hatte, wurde beim naechsten Lauf zum Zurueckstellen gefragt.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_ng_autoupdate")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import shadowmount_config as sm_cfg    # noqa: E402
from ps5_validator.utils import shadowmount_generation as sg    # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402
from ps5_validator.utils.ini_config import merge_flat_ini, parse_flat_ini, parse_flat_ini_multi    # noqa: E402

G = APP.PS5ConverterGUI
QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
SPRACHEN = ("de", "en", "es", "it", "fr")
NEUE_SCHLUESSEL = ("amprgen.auto_update_emulators", "amprgen.auto_update_ampr", "amprgen.zustand_an", "amprgen.zustand_aus",
                   "amprgen.zustand_vorgabe", "amprgen.auto_ng_grund")


class SollTests(unittest.TestCase):
    def test_im_spiel_und_global_muss_beides_aus_sein(self) -> None:
        for ort in (sg.ORT_SPIEL, sg.ORT_BACKPORT, sg.ORT_GLOBAL):
            with self.subTest(ort=ort):
                self.assertEqual({"update_emulators": "0", "auto_update_ampr": "0"}, sg.ng_config_soll(ort))

    def test_liegt_die_ng_datei_im_emulator_ordner_bleibt_update_emulators_an(self) -> None:
        """Dort ist ``update_emulators=1`` der Weg ins Spiel; abgestellt werden muss nur das Holen von drakmors Fassung."""
        self.assertEqual({"update_emulators": "1", "auto_update_ampr": "0"}, sg.ng_config_soll(sg.ORT_EMUS))

    def test_die_vorgaben_stimmen_mit_shadowmount_ueberein(self) -> None:
        self.assertEqual({"update_emulators": "1", "auto_update_ampr": "0"}, sg.NG_VORGABE)


class AbweichungenTests(unittest.TestCase):
    def test_ein_fehlender_eintrag_zaehlt_mit_seiner_vorgabe(self) -> None:
        """``update_emulators`` laeuft ohne Eintrag auf AN - genau das ueberschreibt NG."""
        self.assertEqual([("update_emulators", "1 (Vorgabe)", "0")], sg.ng_abweichungen({}, sg.ORT_SPIEL))

    def test_beides_aus_ist_in_ordnung(self) -> None:
        self.assertEqual([], sg.ng_abweichungen({"update_emulators": "0", "auto_update_ampr": "0"}, sg.ORT_SPIEL))

    def test_auto_update_ampr_an_wird_gemeldet(self) -> None:
        self.assertEqual([("auto_update_ampr", "1", "0")],
                         sg.ng_abweichungen({"update_emulators": "0", "auto_update_ampr": "1"}, sg.ORT_SPIEL))

    def test_beides_an(self) -> None:
        self.assertEqual({"update_emulators", "auto_update_ampr"},
                         {s for s, _i, _s in sg.ng_abweichungen({"update_emulators": "1", "auto_update_ampr": "1"}, sg.ORT_SPIEL)})

    def test_format_2_schreibweise_on_off_gilt_als_ja_nein(self) -> None:
        self.assertEqual([], sg.ng_abweichungen({"update_emulators": "off", "auto_update_ampr": "off"}, sg.ORT_SPIEL))
        self.assertEqual([("update_emulators", "on", "0")],
                         sg.ng_abweichungen({"update_emulators": "on", "auto_update_ampr": "off"}, sg.ORT_SPIEL))

    def test_ein_leerer_wert_zaehlt_wie_ein_fehlender(self) -> None:
        self.assertEqual([("update_emulators", "1 (Vorgabe)", "0")],
                         sg.ng_abweichungen({"update_emulators": "  ", "auto_update_ampr": ""}, sg.ORT_SPIEL))

    def test_im_emulator_ordner_meldet_nur_das_holen_von_drakmors_fassung(self) -> None:
        self.assertEqual([], sg.ng_abweichungen({}, sg.ORT_EMUS))
        self.assertEqual([("auto_update_ampr", "1", "0")], sg.ng_abweichungen({"auto_update_ampr": "1"}, sg.ORT_EMUS))

    def test_geschrieben_wird_auch_ein_bisher_fehlender_schluessel(self) -> None:
        """Die Einrichtung schreibt mit ``merge_flat_ini``: Ein Schluessel, den die Datei nicht aktiv kennt, kommt hinzu."""
        for text in ("# update_emulators = 1\nscanpath=/data/homebrew\n", "scanpath=/data/homebrew\n", ""):
            with self.subTest(text=text):
                aenderungen = {s: soll for s, _ist, soll in sg.ng_abweichungen(parse_flat_ini(text), sg.ORT_SPIEL)}
                neu = merge_flat_ini(text, {**parse_flat_ini_multi(text), **aenderungen})
                self.assertEqual("0", parse_flat_ini(neu)["update_emulators"])
                self.assertEqual([], sg.ng_abweichungen(parse_flat_ini(neu), sg.ORT_SPIEL), "danach ist nichts mehr umzustellen")


def _gui(format_: str = sm_cfg.FORMAT_V1):
    gui = G.__new__(G)
    gui._current_language = "de"
    gui._sm_format_gespeichert = lambda: format_
    gui._t = lambda schluessel, **w: schluessel + ("|" + "|".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")
    return gui


class EinrichtungTests(unittest.TestCase):
    """``_ampr_gen_auto_update`` - der Schritt "Stimmt die config.ini?" der AMPR-Einrichtung."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ng = os.path.join(tmp.name, "libSceAmpr.sprx")
        Path(self.ng).write_bytes(b"\x7fELF....ampr-emu-ng 0.4.1....")
        sonst = os.path.join(tmp.name, "drakmor")
        os.makedirs(sonst)
        self.drakmor = os.path.join(sonst, "libSceAmpr.sprx")
        Path(self.drakmor).write_bytes(b"\x7fELF....ampr_emu von drakmor....")
        self.zeilen: list[str] = []

    def _lauf(self, text: str, libs: list, ort: str = sg.ORT_SPIEL, generation: str = sg.NEU, vorher=None):
        gui = _gui()
        abweichungen = gui._ampr_gen_config_pruefen(generation, text) if vorher is None else vorher
        return gui, gui._ampr_gen_auto_update(generation, ort, text, [{"path": p} for p in libs], abweichungen, self.zeilen.append)

    def test_der_stand_steht_im_protokoll_auch_ohne_ng(self) -> None:
        _gui_, abw = self._lauf("update_emulators=0\n", [self.drakmor])
        self.assertEqual(2, len(self.zeilen))
        self.assertTrue(self.zeilen[0].startswith("amprgen.auto_update_emulators"))
        self.assertIn("amprgen.zustand_aus", self.zeilen[0])
        self.assertNotIn("zustand_vorgabe", self.zeilen[0], "der Schluessel steht ja in der Datei")
        self.assertTrue(self.zeilen[1].startswith("amprgen.auto_update_ampr"))
        self.assertIn("amprgen.zustand_vorgabe", self.zeilen[1], "auto_update_ampr fehlt: es gilt die Vorgabe")
        self.assertIn("amprgen.zustand_aus", self.zeilen[1])
        self.assertEqual([("update_emulators", "0", "1")], abw, "ohne NG bleibt das Soll der Generation, wie bisher")

    def test_ohne_eintraege_gilt_update_emulators_als_an_laut_vorgabe(self) -> None:
        self._lauf("", [self.drakmor])
        self.assertIn("amprgen.zustand_vorgabe", self.zeilen[0])
        self.assertIn("amprgen.zustand_an", self.zeilen[0])

    def test_ng_ohne_eintraege_fragt_nach_update_emulators(self) -> None:
        _gui_, abw = self._lauf("", [self.ng])
        self.assertEqual([("update_emulators", "1 (Vorgabe)", "0")], abw)
        self.assertIn("!! amprgen.auto_ng_grund", self.zeilen)

    def test_ng_mit_abgestelltem_update_emulators_wird_nicht_zurueckgefragt(self) -> None:
        """Der gemeldete Zielkonflikt: Das Soll der Generation (``update_emulators=1``) stellte NG wieder an."""
        text = "update_emulators=0\nauto_update_ampr=0\n"
        gui = _gui()
        alt = gui._ampr_gen_config_pruefen(sg.NEU, text)
        self.assertEqual([("update_emulators", "0", "1")], alt, "Ausgangslage: die Einrichtung wollte es zurueckstellen")
        _g, abw = self._lauf(text, [self.ng], vorher=alt)
        self.assertEqual([], abw)
        self.assertNotIn("!! amprgen.auto_ng_grund", self.zeilen, "es ist ja alles in Ordnung")

    def test_ng_mit_auto_update_ampr_an(self) -> None:
        _g, abw = self._lauf("update_emulators=0\nauto_update_ampr=1\n", [self.ng])
        self.assertEqual([("auto_update_ampr", "1", "0")], abw)

    def test_ng_im_emulator_ordner_laesst_update_emulators_an(self) -> None:
        _g, abw = self._lauf("", [self.ng], ort=sg.ORT_EMUS)
        self.assertEqual([], abw)

    def test_andere_abweichungen_bleiben_erhalten(self) -> None:
        text = "backport_fakelib=0\nupdate_emulators=0\n"
        _g, abw = self._lauf(text, [self.ng])
        self.assertEqual([("backport_fakelib", "0", "1")], abw)

    def test_die_alte_fassung_kennt_die_schluessel_nicht(self) -> None:
        _g, abw = self._lauf("", [self.ng], generation=sg.ALT, vorher=[])
        self.assertEqual([], abw)
        self.assertEqual([], self.zeilen, "kein Stand fuer Schluessel, die es dort nicht gibt")

    def test_nur_die_ng_datei_von_libsceampr_loest_es_aus(self) -> None:
        anderer_name = os.path.join(os.path.dirname(self.ng), "libScePlayGo.sprx")
        Path(anderer_name).write_bytes(b"ampr-emu-ng")
        _g, abw = self._lauf("update_emulators=0\n", [anderer_name], vorher=[])
        self.assertEqual([], abw, "nur die libSceAmpr.sprx wird ueberschrieben")


class TexteTests(unittest.TestCase):
    def test_die_neuen_texte_gibt_es_in_allen_sprachen(self) -> None:
        for schluessel in NEUE_SCHLUESSEL:
            for sprache in SPRACHEN:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].strip())
        for schluessel in ("amprgen.auto_update_emulators", "amprgen.auto_update_ampr", "amprgen.zustand_vorgabe"):
            for sprache in SPRACHEN:
                self.assertIn("{zustand}", STRINGS[schluessel][sprache])

    def test_der_ng_hinweis_nennt_beide_schalter(self) -> None:
        for sprache in SPRACHEN:
            with self.subTest(sprache=sprache):
                text = STRINGS["ampr.ng_update_emulators"][sprache]
                self.assertIn("update_emulators=0", text)
                self.assertIn("auto_update_ampr=0", text)

    def test_bei_format_2_stehen_die_schluessel_der_neuen_config(self) -> None:
        gui = G.__new__(G)
        gui._current_language = "de"
        gui._sm_format_gespeichert = lambda: sm_cfg.FORMAT_V2
        text = gui._t("amprgen.auto_update_ampr", zustand="aus")
        self.assertIn("[emulators] auto_update_ampr", text)
        text = gui._t("amprgen.auto_update_emulators", zustand="an")
        self.assertIn("[emulators] update_enabled", text)

    def test_bei_format_1_bleiben_die_alten_schluessel(self) -> None:
        gui = G.__new__(G)
        gui._current_language = "de"
        gui._sm_format_gespeichert = lambda: sm_cfg.FORMAT_V1
        self.assertIn("update_emulators = an", gui._t("amprgen.auto_update_emulators", zustand="an"))


class QuelltextTests(unittest.TestCase):
    def test_die_einrichtung_ruft_den_schritt_vor_der_frage_auf(self) -> None:
        """Die NG-Abweichungen muessen in der Frage "Diese Schluessel stehen anders" landen, nicht danach."""
        aufruf = QUELLE.index("self._ampr_gen_auto_update(generation, ort, text, gewaehlt_libs, abweichungen, melde)")
        frage = QUELLE.index('self._t("amprgen.q_config")', aufruf)
        pruefen = QUELLE.rindex("self._ampr_gen_config_pruefen(generation, text)", 0, aufruf)
        self.assertLess(pruefen, aufruf)
        self.assertLess(aufruf, frage)


if __name__ == "__main__":
    unittest.main()
