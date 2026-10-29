# -*- coding: utf-8 -*-
"""Backport als eigener Ordner ``backports/<TITLE_ID>`` fuer ShadowMount+ (28.10.2026).

Die Form folgt dem README und dem Quelltext von ShadowMountPlus 1.7beta2 (``resolve_backport_path_for_title``,
``mount_backport_overlay_for_title``): ``<Suchpfad>/backports/<TITLE_ID>/`` wird ueber das Spiel gelegt, darin zaehlt
``fakelib2`` vor ``fakelib``. Das Spiel selbst bleibt unveraendert.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests"))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402
from test_backport import baue_elf                          # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
BASIS = str(PROJEKT / "Backport_Fakelibs")
PARAM = {"titleId": "PPSA01234", "contentId": "UP0000-PPSA01234_00-TESTSPIEL0000000",
         "requiredSystemSoftwareVersion": "0x1001000000000000", "sdkVersion": "0x0900000000000000"}


class _Spiel(unittest.TestCase):
    def setUp(self) -> None:
        self.wurzel = tempfile.mkdtemp(prefix="bp_ordner_")
        self.addCleanup(shutil.rmtree, self.wurzel, True)
        self.spiel = os.path.join(self.wurzel, "spiel")
        self.ausgabe = os.path.join(self.wurzel, "ausgabe")
        os.makedirs(os.path.join(self.spiel, "sce_sys"))
        os.makedirs(os.path.join(self.spiel, "sce_module"))
        os.makedirs(self.ausgabe)
        self._schreibe("eboot.bin", baue_elf(ps5_sdk=0x09000040))
        self._schreibe("sce_module/libtest.prx", baue_elf(ps5_sdk=0x09000040))
        self._schreibe("sce_module/schon_niedrig.prx", baue_elf(ps5_sdk=0x04000031))
        self._schreibe("sce_sys/param.json", json.dumps(PARAM).encode("ascii"))
        self._schreibe("daten/bild.dat", b"nicht anfassen")

    def _schreibe(self, rel: str, daten: bytes) -> None:
        pfad = os.path.join(self.spiel, rel)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "wb") as datei:
            datei.write(daten)

    def _stand(self) -> dict:
        stand = {}
        for wurzel, _o, dateien in os.walk(self.spiel):
            for name in dateien:
                pfad = os.path.join(wurzel, name)
                with open(pfad, "rb") as datei:
                    stand[os.path.relpath(pfad, self.spiel)] = datei.read()
        return stand


class PfadTests(unittest.TestCase):
    def test_der_ordner_heisst_genau_wie_die_title_id(self) -> None:
        self.assertEqual(os.path.join("x", "backports", "PPSA01234"), bp.backport_ordner_pfad("x", "PPSA01234"))

    def test_unbrauchbare_title_ids_werden_abgelehnt(self) -> None:
        for kennung in ("", "ppsa01234", "PPSA1234", "PPSA01234 Spiel", "../PPSA01234", "PPSA012345"):
            with self.subTest(kennung=kennung), self.assertRaises(bp.BackportFehler):
                bp.backport_ordner_pfad("x", kennung)

    def test_die_title_id_kommt_aus_der_param_json(self) -> None:
        wurzel = tempfile.mkdtemp(prefix="bp_tid_")
        self.addCleanup(shutil.rmtree, wurzel, True)
        self.assertEqual("", bp.titel_id_aus_param(wurzel))
        os.makedirs(os.path.join(wurzel, "sce_sys"))
        pfad = os.path.join(wurzel, "sce_sys", "param.json")
        with open(pfad, "w", encoding="utf-8") as datei:
            json.dump({"contentId": "EP0000-PPSA09999_00-ABC"}, datei)
        self.assertEqual("PPSA09999", bp.titel_id_aus_param(wurzel), "Ohne titleId gilt die contentId.")
        with open(pfad, "w", encoding="utf-8") as datei:
            json.dump(PARAM, datei)
        self.assertEqual("PPSA01234", bp.titel_id_aus_param(wurzel))


class BauenTests(_Spiel):
    def _bauen(self, **kw) -> dict:
        return bp.backport_ordner_bauen(self.spiel, self.ausgabe, "PPSA01234", 4, BASIS, **kw)

    def test_das_spiel_bleibt_byte_gleich(self) -> None:
        vorher = self._stand()
        self._bauen()
        self.assertEqual(vorher, self._stand(), "Der Dump darf nicht angefasst werden - auch keine .bak/.neu-Dateien.")

    def test_der_ordner_liegt_unter_backports_und_title_id(self) -> None:
        erg = self._bauen()
        soll = os.path.join(self.ausgabe, "backports", "PPSA01234")
        self.assertEqual(soll, erg["ziel"])
        self.assertTrue(os.path.isdir(soll))

    def test_nur_geaenderte_dateien_mit_demselben_pfad_wie_im_spiel(self) -> None:
        erg = self._bauen()
        ziel = erg["ziel"]
        self.assertEqual(2, erg["gepatcht"], "eboot.bin und libtest.prx; die schon niedrige Datei bleibt draussen.")
        self.assertEqual(0, erg["fehler"], erg["fehlermeldungen"])
        self.assertTrue(os.path.isfile(os.path.join(ziel, "eboot.bin")))
        self.assertTrue(os.path.isfile(os.path.join(ziel, "sce_module", "libtest.prx")))
        self.assertFalse(os.path.exists(os.path.join(ziel, "sce_module", "schon_niedrig.prx")))
        self.assertFalse(os.path.exists(os.path.join(ziel, "daten")), "Unveraenderte Dateien gehoeren nicht hinein.")

    def test_die_dateien_sind_auf_die_zielfirmware_herabgesetzt(self) -> None:
        ziel = self._bauen()["ziel"]
        with open(os.path.join(ziel, "eboot.bin"), "rb") as datei:
            roh = datei.read()
        elf = bp.self_zu_elf(roh) if bp.dateityp(roh) == bp.TYP_SELF else roh
        ps5, _ps4 = bp.sdk_lesen(elf)
        self.assertEqual(bp.sdk_paar(4)[0], ps5)

    def test_param_json_ist_eine_herabgesetzte_kopie(self) -> None:
        ziel = self._bauen()["ziel"]
        with open(os.path.join(ziel, "sce_sys", "param.json"), "r", encoding="utf-8") as datei:
            neu = json.load(datei)
        self.assertTrue(neu["requiredSystemSoftwareVersion"].lower().startswith("0x04"))
        with open(os.path.join(self.spiel, "sce_sys", "param.json"), "r", encoding="utf-8") as datei:
            self.assertEqual(PARAM, json.load(datei), "Das Original bleibt.")

    def test_fakelib_traegt_den_satz_samt_ampr_und_playgo(self) -> None:
        ziel = self._bauen()["ziel"]
        bib = os.path.join(ziel, "fakelib")
        soll = {os.path.basename(p) for p in bp.fakelib_dateien(BASIS, 4)}
        self.assertEqual(soll, set(os.listdir(bib)))
        self.assertIn("libSceAmpr.sprx", soll)
        self.assertIn("libScePlayGo.sprx", soll)
        self.assertFalse(os.path.exists(os.path.join(ziel, "fakelib2")),
                         "Nur fakelib: ein fakelib2 wirkt exklusiv und braucht ShadowMount+ ab alpha10.")

    def test_die_eigene_fakelib_des_spiels_geht_mit(self) -> None:
        """ShadowMount+ nimmt NUR den Ordner des Backports - sonst waere das AMPR EMU des Spiels verloren."""
        self._schreibe("fakelib/dlc_emu.ini", b"[x]")
        self._schreibe("fakelib/libSceAmpr.sprx", b"\x7fELF.....[AMPR_EMU] 0.4.2.1")
        self._schreibe("fakelib/libSceAmpr.sprx.orig", b"original")
        ziel = self._bauen()["ziel"]
        bib = os.path.join(ziel, "fakelib")
        self.assertTrue(os.path.isfile(os.path.join(bib, "dlc_emu.ini")))
        self.assertFalse(os.path.exists(os.path.join(bib, "libSceAmpr.sprx.orig")))
        with open(os.path.join(bib, "libSceAmpr.sprx"), "rb") as datei:
            self.assertTrue(datei.read().endswith(b"0.4.2.1"), "Ein mitgebrachtes AMPR EMU bleibt.")

    def test_ein_fremdes_ampr_des_spiels_wird_ersetzt(self) -> None:
        self._schreibe("fakelib/libSceAmpr.sprx", b"\x7fELF fremd")
        bib = os.path.join(self._bauen()["ziel"], "fakelib")
        with open(os.path.join(bib, "libSceAmpr.sprx"), "rb") as datei:
            self.assertNotEqual(b"\x7fELF fremd", datei.read())

    def test_ein_ausgabeordner_im_spiel_wird_abgelehnt(self) -> None:
        with self.assertRaises(bp.BackportFehler):
            bp.backport_ordner_bauen(self.spiel, os.path.join(self.spiel, "raus"), "PPSA01234", 4, BASIS)
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "raus")))

    def test_unbekannte_firmware_bricht_ab(self) -> None:
        with self.assertRaises(bp.BackportFehler):
            bp.backport_ordner_bauen(self.spiel, self.ausgabe, "PPSA01234", 99, BASIS)

    def test_abbruch_haelt_an(self) -> None:
        erg = self._bauen(abbruch=lambda: True)
        self.assertTrue(erg["abgebrochen"])


class EinfuegenTests(_Spiel):
    """Der Ordner zum Hineinkopieren: derselbe Inhalt, nur ohne ``backports/`` davor (30.10.2026)."""

    def _bauen(self, **kw) -> dict:
        ziel = bp.einfuegen_ordner_pfad(self.ausgabe, "PPSA01234", 4)
        return bp.backport_ordner_bauen(self.spiel, self.ausgabe, "PPSA01234", 4, BASIS, ziel_ordner=ziel, **kw)

    def test_der_ordner_traegt_title_id_und_firmware_im_namen(self) -> None:
        self.assertEqual(os.path.join("x", "PPSA01234 Backport FW4"), bp.einfuegen_ordner_pfad("x", "PPSA01234", 4))
        self.assertEqual(os.path.join(self.ausgabe, "PPSA01234 Backport FW4"), self._bauen()["ziel"])
        self.assertFalse(os.path.exists(os.path.join(self.ausgabe, "backports")))

    def test_unbrauchbare_title_ids_werden_abgelehnt(self) -> None:
        with self.assertRaises(bp.BackportFehler):
            bp.einfuegen_ordner_pfad("x", "../PPSA01234", 4)

    def test_der_bibliotheksordner_heisst_wie_vorgegeben(self) -> None:
        erg = self._bauen(fakelib_name="fakelib2")
        self.assertTrue(os.path.isdir(os.path.join(erg["ziel"], "fakelib2")))
        self.assertFalse(os.path.exists(os.path.join(erg["ziel"], "fakelib")))

    def test_in_den_spielordner_kopiert_ergibt_den_backport_im_spiel(self) -> None:
        erg = self._bauen()
        self.assertEqual(0, erg["fehler"], erg["fehlermeldungen"])
        stand_vorher = {k.replace(os.sep, "/"): v for k, v in self._stand().items()}
        unberuehrt = stand_vorher["daten/bild.dat"]
        shutil.copytree(erg["ziel"], self.spiel, dirs_exist_ok=True)       # "Dateien ersetzen"
        stand = {k.replace(os.sep, "/"): v for k, v in self._stand().items()}
        def _sdk(roh: bytes) -> int:
            return bp.sdk_lesen(bp.self_zu_elf(roh) if bp.dateityp(roh) == bp.TYP_SELF else roh)[0]

        self.assertEqual(bp.sdk_paar(4)[0], _sdk(stand["eboot.bin"]), "eboot.bin ist herabgesetzt")
        self.assertEqual(bp.sdk_paar(4)[0], _sdk(stand["sce_module/libtest.prx"]))
        self.assertEqual(unberuehrt, stand["daten/bild.dat"], "Was der Backport nicht anfasst, bleibt.")
        self.assertTrue(any(name.startswith("fakelib/") for name in stand), "Der Satz liegt im Spielordner.")
        self.assertIn(bp.param_json_herabsetzen(json.dumps(PARAM).encode("ascii"), 4)[0].decode("ascii"),
                      stand["sce_sys/param.json"].decode("ascii"))


class FirmwareVorschlagTests(unittest.TestCase):
    """Die Vorauswahl der Zielfirmware (29.10.2026): nie ueber der Konsole, sonst so hoch wie moeglich."""

    def test_die_hoechste_stufe_unter_der_konsole(self) -> None:
        for konsole, soll in (("4.03", 4), ("5.50", 5), ("6.00", 6), ("7.61", 7), ("9.60", 7), ("12.00", 7),
                              ("04030000", 4), ("0x07000000", 7), ("12000020", 7)):
            with self.subTest(konsole=konsole):
                self.assertEqual(soll, bp.firmware_vorschlag(konsole, (4, 5, 6, 7)))

    def test_unbekannt_oder_zu_niedrig_gibt_keinen_vorschlag(self) -> None:
        for konsole in ("", "unbekannt", "3.20", None):
            with self.subTest(konsole=konsole):
                self.assertIsNone(bp.firmware_vorschlag(konsole, (4, 5, 6, 7)))

    def test_nur_waehlbare_stufen(self) -> None:
        self.assertEqual(5, bp.firmware_vorschlag("6.50", (4, 5)))
        self.assertIsNone(bp.firmware_vorschlag("6.50", ()))


@unittest.skipUnless(os.environ.get("PS5CONV_KONFIGORDNER") is not None, "Konfigordner nicht umgelenkt")
class FensterVorauswahlTests(unittest.TestCase):
    """Das BACKPORT-Fenster waehlt die Firmware passend zur Konsole vor."""

    @classmethod
    def setUpClass(cls) -> None:
        import tkinter as tk
        from unittest import mock
        try:
            cls.wurzel = tk._default_root or tk.Tk()
            cls.wurzel.withdraw()
        except Exception:                                  # noqa: BLE001
            raise unittest.SkipTest("Keine Anzeige")
        from test_fensterlayout import _lade_hauptprogramm, _sammle
        cls._sammle = staticmethod(_sammle)
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(cls.wurzel)
        cls.app._current_language = "de"
        cls.mock = mock

    def _box(self, konsole: str):
        spiel = tempfile.mkdtemp(prefix="bp_vor_")
        self.addCleanup(shutil.rmtree, spiel, True)
        vorher = {str(w) for w in self.wurzel.winfo_children()}
        with self.mock.patch.object(self.app, "_konsole_firmware", return_value=konsole):
            self.app._render_backport_window(spiel)
        self.wurzel.update_idletasks()
        fenster = [w for w in self.wurzel.winfo_children()
                   if str(w) not in vorher and w.winfo_class() == "Toplevel"][-1]
        self.addCleanup(fenster.destroy)
        return self._sammle(fenster, "Combobox")[0].get()

    def test_konsole_4_03_waehlt_firmware_4(self) -> None:
        self.assertIn("4.00", self._box("4.03"))

    def test_konsole_12_waehlt_den_standard(self) -> None:
        self.assertIn("%d.00" % bp.FIRMWARE_STANDARD, self._box("12.00"))

    def test_unbekannte_konsole_waehlt_den_standard(self) -> None:
        self.assertIn("%d.00" % bp.FIRMWARE_STANDARD, self._box(""))


class VerdrahtungTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(HAUPTDATEI, "r", encoding="utf-8") as datei:
            cls.quelle = datei.read()

    def test_knopf_und_arbeiter_sind_verdrahtet(self) -> None:
        self.assertIn("ps5_backport.backport_ordner_bauen(", self.quelle)
        self.assertIn('self._t("backport.action_folder")', self.quelle)
        self.assertIn("ps5_backport.titel_id_aus_param(ordner)", self.quelle)
        self.assertIn("ps5_backport.einfuegen_ordner_pfad(gewaehlt, tid, firmware)", self.quelle)
        self.assertIn("fakelib_name=fakelib_name", self.quelle,
                      "Der Bibliotheksordner heisst wie beim Backport im Spielordner.")
        self.assertNotIn("backport.folder_upload_frage", self.quelle, "Kein Upload nach backports/ mehr.")
        self.assertIn("ps5_backport.firmware_vorschlag(konsole_fw, firmwares)", self.quelle)

    def test_alle_texte_sind_in_allen_sprachen_da(self) -> None:
        for schluessel in ("backport.action_folder", "backport.action_folder_hint", "backport.folder_pick_title",
                           "backport.folder_no_id", "backport.folder_inside_game", "backport.folder_exists",
                           "backport.folder_status", "backport.folder_log_start", "backport.folder_log_done",
                           "backport.folder_done_title", "backport.folder_done_message",
                           "backport.fw_vorschlag"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache))

    def test_die_platzhalter_stimmen_in_allen_sprachen_ueberein(self) -> None:
        import re
        for schluessel in ("backport.folder_log_start", "backport.folder_log_done", "backport.folder_done_message",
                           "backport.folder_exists"):
            sollen = set(re.findall(r"\{(\w+)\}", STRINGS[schluessel]["de"]))
            for sprache in ("en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertEqual(sollen, set(re.findall(r"\{(\w+)\}", STRINGS[schluessel][sprache])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
