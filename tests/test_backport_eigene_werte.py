# -*- coding: utf-8 -*-
"""Eigene Zielwerte im BACKPORT: SDK-Zahlen (PS5/PS4) und verlangte Firmware der ``param.json`` frei vorgeben.

Vorbild ist der PS5-App-Dumper v2.10 (``min_ps5_sdk_version`` / ``min_ps4_sdk_version`` in der ``config.ini``);
dazu die verlangte Firmware mit Nebenversion: Der FW-4.xx-Release von Assassin's Creed Black Flag traegt in der
``param.json`` ``requiredSystemSoftwareVersion = 0x0450000000000000`` bei ``sdkVersion = 0x0400000000000000``.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("backport_eigene_werte")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ps5_backport as b           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PARAM = (b'{"requiredSystemSoftwareVersion": "0x1360000000000000", '
         b'"sdkVersion": "0x1100000000000000", "titleId": "PPSA00000"}')


class WerteLesen(unittest.TestCase):
    def test_sdk_zahl_mit_und_ohne_praefix(self):
        self.assertEqual(b.sdk_wert_lesen("0x04000031"), 0x04000031)
        self.assertEqual(b.sdk_wert_lesen("04000031"), 0x04000031)
        self.assertEqual(b.sdk_wert_lesen("  0X0900001a "), 0x0900001A)

    def test_leer_heisst_tabellenwert(self):
        self.assertIsNone(b.sdk_wert_lesen(""))
        self.assertIsNone(b.sdk_wert_lesen("   "))
        self.assertIsNone(b.firmware_version_lesen(""))

    def test_unbrauchbare_sdk_zahlen_scheitern_laut(self):
        # Abgeschnitten (0x4), zu lang, kein Hex, null: keiner darf still als SDK 0.00 durchgehen.
        for text in ("0x4", "0x040000311", "vier", "0x0400003G", "0x00000000", "4.00"):
            with self.subTest(text=text):
                with self.assertRaises(b.BackportFehler):
                    b.sdk_wert_lesen(text, "PS5-SDK")

    def test_firmwareversion_als_bcd_wort(self):
        self.assertEqual(b.firmware_version_lesen("4.50"), 0x0450)
        self.assertEqual(b.firmware_version_lesen("10.01"), 0x1001)
        self.assertEqual(b.firmware_version_lesen("4.05"), 0x0405)

    def test_unbrauchbare_firmwareversionen(self):
        for text in ("4.5", "450", "4,50", "x.50", "4.50.1", "100.00"):
            with self.subTest(text=text):
                with self.assertRaises(b.BackportFehler):
                    b.firmware_version_lesen(text)


class ZielWerte(unittest.TestCase):
    def test_ohne_eigene_werte_gilt_die_tabelle(self):
        z = b.ziel_werte(4)
        self.assertEqual((z.ps5_sdk, z.ps4_sdk, z.verlangt_fw), (0x04000031, 0x09040001, None))
        self.assertEqual(b.ziel_werte(4, b.EigeneWerte()), z)

    def test_einzelne_felder_ersetzen_nur_sich(self):
        z = b.ziel_werte(4, b.EigeneWerte(ps5_sdk="0x04500031"))
        self.assertEqual((z.ps5_sdk, z.ps4_sdk), (0x04500031, 0x09040001))
        z = b.ziel_werte(4, b.EigeneWerte(ps4_sdk="0x09590001", verlangt_fw="4.50"))
        self.assertEqual((z.ps5_sdk, z.ps4_sdk, z.verlangt_fw), (0x04000031, 0x09590001, 0x0450))

    def test_unbekannte_firmware_und_schlechter_wert_scheitern(self):
        with self.assertRaises(b.BackportFehler):
            b.ziel_werte(99)
        with self.assertRaises(b.BackportFehler):
            b.ziel_werte(4, b.EigeneWerte(ps4_sdk="kaputt"))


class ParamJson(unittest.TestCase):
    def test_ohne_eigene_werte_wie_bisher(self):
        neu, aend = b.param_json_herabsetzen(PARAM, 4)
        self.assertIn(b'"requiredSystemSoftwareVersion": "0x0400000000000000"', neu)
        self.assertIn(b'"sdkVersion": "0x0400000000000000"', neu)
        self.assertEqual(len(aend), 2)

    def test_verlangte_firmware_4_50_wie_im_ac_release(self):
        neu, aend = b.param_json_herabsetzen(PARAM, 4, b.EigeneWerte(verlangt_fw="4.50"))
        self.assertIn(b'"requiredSystemSoftwareVersion": "0x0450000000000000"', neu)
        self.assertIn(b'"sdkVersion": "0x0400000000000000"', neu)       # SDK bleibt bei der Stufe
        self.assertEqual([(f, n) for f, _a, n in aend],
                         [("requiredSystemSoftwareVersion", "0x0450000000000000"),
                          ("sdkVersion", "0x0400000000000000")])
        self.assertTrue(neu.endswith(b'"titleId": "PPSA00000"}'))       # Rest Byte fuer Byte unveraendert

    def test_nie_anheben_auch_nicht_mit_nebenversion(self):
        niedrig = PARAM.replace(b"0x1360000000000000", b"0x0430000000000000")
        neu, aend = b.param_json_herabsetzen(niedrig, 4, b.EigeneWerte(verlangt_fw="4.50"))
        self.assertIn(b'"requiredSystemSoftwareVersion": "0x0430000000000000"', neu)
        self.assertEqual([f for f, _a, _n in aend], ["sdkVersion"])
        gleich = PARAM.replace(b"0x1360000000000000", b"0x0450000000000000")
        self.assertEqual(b.param_json_herabsetzen(gleich, 4, b.EigeneWerte(verlangt_fw="4.50"))[0].count(b"0x0450"), 1)

    def test_gleiche_hauptversion_hoehere_nebenversion_wird_gesenkt(self):
        # Ohne eigene Version bleibt 4.70 (Hauptversion gleich); mit verlangt_fw 4.50 wird sie gesenkt.
        p = PARAM.replace(b"0x1360000000000000", b"0x0470000000000000")
        self.assertIn(b"0x0470", b.param_json_herabsetzen(p, 4)[0])
        self.assertIn(b'"requiredSystemSoftwareVersion": "0x0450000000000000"',
                      b.param_json_herabsetzen(p, 4, b.EigeneWerte(verlangt_fw="4.50"))[0])

    def test_sdkversion_folgt_der_eigenen_ps5_zahl(self):
        neu, _ = b.param_json_herabsetzen(PARAM, 4, b.EigeneWerte(ps5_sdk="0x05000033"))
        self.assertIn(b'"sdkVersion": "0x0500000000000000"', neu)
        self.assertIn(b'"requiredSystemSoftwareVersion": "0x0500000000000000"', neu)

    def test_datei_und_ordnerbau(self):
        ordner = Path(tempfile.mkdtemp(prefix="bp_eigene_"))
        self.addCleanup(shutil.rmtree, ordner, True)
        (ordner / "spiel" / "sce_sys").mkdir(parents=True)
        (ordner / "spiel" / "sce_sys" / "param.json").write_bytes(PARAM)
        eigene = b.EigeneWerte(verlangt_fw="4.50")
        erg = b.backport_ordner_bauen(str(ordner / "spiel"), str(ordner / "aus"), "PPSA00000", 4,
                                      str(ordner / "keine_libs"), eigene=eigene,
                                      ziel_ordner=str(ordner / "ziel"))
        self.assertEqual(erg["fehler"], 0)
        geschrieben = (ordner / "ziel" / "sce_sys" / "param.json").read_bytes()
        self.assertIn(b'"requiredSystemSoftwareVersion": "0x0450000000000000"', geschrieben)
        # Das Spiel selbst bleibt unberuehrt.
        self.assertEqual((ordner / "spiel" / "sce_sys" / "param.json").read_bytes(), PARAM)
        with self.assertRaises(b.BackportFehler):
            b.backport_ordner_bauen(str(ordner / "spiel"), str(ordner / "aus"), "PPSA00000", 4,
                                    str(ordner / "keine_libs"), eigene=b.EigeneWerte(ps5_sdk="0x4"),
                                    ziel_ordner=str(ordner / "ziel2"))


def _gui(einstellungen: dict):
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._load_setting = lambda schluessel, vorgabe=None: einstellungen.get(schluessel, vorgabe)
    return gui


class Hauptmodul(unittest.TestCase):
    def test_einstellungen_werden_gelesen_und_gekuerzt(self):
        gui = _gui({"backport_sdk_ps5": " 0x04500031 ", "backport_verlangte_fw": "4.50"})
        self.assertEqual(gui._backport_eigene(), b.EigeneWerte("0x04500031", "", "4.50"))
        self.assertEqual(_gui({})._backport_eigene(), b.EigeneWerte())

    def test_fehlerpruefung(self):
        self.assertEqual(_gui({"backport_verlangte_fw": "4.50"})._backport_eigene_fehler(), "")
        grund = _gui({"backport_sdk_ps4": "zzz"})._backport_eigene_fehler()
        self.assertIn("PS4-SDK", grund)

    def test_einbau_bricht_bei_unbrauchbarem_wert_ab_und_aendert_nichts(self):
        ordner = Path(tempfile.mkdtemp(prefix="bp_einbau_"))
        self.addCleanup(shutil.rmtree, ordner, True)
        (ordner / "sce_sys").mkdir()
        (ordner / "sce_sys" / "param.json").write_bytes(PARAM)
        gui = _gui({"backport_sdk_ps5": "0x4"})
        gui._tk_wert = lambda name, vorgabe=None: 4
        gui._set_status = lambda *_a, **_k: None
        self.assertFalse(gui._integration_backport(str(ordner)))
        self.assertTrue(any("Eigener Zielwert unbrauchbar" in zeile for zeile in gui.protokoll), gui.protokoll)
        self.assertEqual((ordner / "sce_sys" / "param.json").read_bytes(), PARAM)

    def test_param_json_nimmt_die_eigene_firmware(self):
        ordner = Path(tempfile.mkdtemp(prefix="bp_param_"))
        self.addCleanup(shutil.rmtree, ordner, True)
        (ordner / "sce_sys").mkdir()
        (ordner / "sce_sys" / "param.json").write_bytes(PARAM)
        gui = _gui({"backport_verlangte_fw": "4.50"})
        self.assertEqual(gui._backport_param_json(str(ordner), 4), 2)
        self.assertIn(b"0x0450000000000000", (ordner / "sce_sys" / "param.json").read_bytes())


class Texte(unittest.TestCase):
    def test_alle_schluessel_in_fuenf_sprachen_mit_platzhaltern(self):
        for schluessel in ("backport.eigene_label", "backport.eigene_ps5", "backport.eigene_ps4",
                           "backport.eigene_fw", "backport.eigene_hint", "backport.eigene_ungueltig"):
            self.assertEqual(set(STRINGS[schluessel]), {"de", "en", "es", "it", "fr"}, schluessel)
        for sprache, text in STRINGS["backport.eigene_ungueltig"].items():
            self.assertIn("{error}", text, sprache)


if __name__ == "__main__":
    unittest.main()
