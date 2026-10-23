# -*- coding: utf-8 -*-
"""DLC-Ordner des PS5-App-Dumpers neben dem Spielordner (23.10.2026).

ps5-app-dumper 2.10 legt Zusatzinhalte mit eigenen Dateien als Ordner ``<Region>-<TITEL-ID>_00-<LABEL>-ac`` neben das
Spiel (README: "each as a folder of its own next to the game's"). Die meisten Zusatzinhalte schalten nur etwas frei,
das schon im Spiel steckt - fuer sie gibt es keinen Ordner und in der dlc_emu.ini einen ``[PSAL]``-Eintrag.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as GUI   # noqa: E402
from ps5_validator.utils import dlc_emu                     # noqa: E402

ID_DLC = "EP1001-PPSA14299_00-ABCDEFGHIJKLMNOP"
ID_DLC2 = "EP1001-PPSA14299_00-ZZZZZZZZZZZZZZZ9"
ID_LIZENZ = "JP0036-PPSA23000_00-DDREVIVECOLOR000"


class NachbarTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = Path(tmp.name)
        self.spiel = self.wurzel / "PPSA14299-app0"
        (self.spiel / "sce_sys").mkdir(parents=True)
        (self.spiel / "sce_sys" / "param.json").write_text(json.dumps({"titleId": "PPSA14299"}), encoding="utf-8")
        (self.spiel / "eboot.bin").write_bytes(b"x")

    def _dlc(self, content_id: str, datei: str = "a.pak") -> Path:
        ordner = self.wurzel / (content_id + "-ac")
        ordner.mkdir()
        (ordner / datei).write_bytes(b"daten")
        return ordner

    def test_findet_die_dlc_ordner_neben_dem_spiel(self) -> None:
        a = self._dlc(ID_DLC)
        b = self._dlc(ID_DLC2)
        self.assertEqual([(ID_DLC, str(a)), (ID_DLC2, str(b))], dlc_emu.nachbar_dlc(str(self.spiel)))

    def test_andere_titel_und_fremde_ordner_zaehlen_nicht(self) -> None:
        self._dlc("EP1001-PPSA99999_00-ABCDEFGHIJKLMNOP")      # anderes Spiel
        (self.wurzel / "irgendein-ordner").mkdir()
        (self.wurzel / (ID_DLC + "-ac.dump-info.json")).write_text("{}", encoding="utf-8")   # Datei, kein Ordner
        self.assertEqual([], dlc_emu.nachbar_dlc(str(self.spiel)))

    def test_ordnername_muss_dem_schema_entsprechen(self) -> None:
        for name in ("EP1001-PPSA14299_00-KURZ-ac", "EP1001-PPSA14299_00-ABCDEFGHIJKLMNOP", "xx-PPSA14299_00-ABCDEFGHIJKLMNOP-ac"):
            with self.subTest(name=name):
                (self.wurzel / name).mkdir(exist_ok=True)
        self.assertEqual([], dlc_emu.nachbar_dlc(str(self.spiel)))

    def test_hauptmodul_nennt_den_nachbarordner_als_merkmal(self) -> None:
        self._dlc(ID_DLC)
        self.assertEqual(ID_DLC + "-ac", GUI._titel_hat_dlc(str(self.spiel)))

    def test_einbauen_kopiert_nach_addcont_n_und_zaehlt_hoch(self) -> None:
        a = self._dlc(ID_DLC, "a.pak")
        b = self._dlc(ID_DLC2, "b.pak")
        meldungen: list = []
        fertig = dlc_emu.nachbarn_einbauen(str(self.spiel), dlc_emu.nachbar_dlc(str(self.spiel)),
                                           lambda name, ziel, n: meldungen.append((name, ziel, n)))
        self.assertEqual([(ID_DLC, 0), (ID_DLC2, 1)], fertig)
        self.assertEqual(b"daten", (self.spiel / "addcont0" / "a.pak").read_bytes())
        self.assertEqual(b"daten", (self.spiel / "addcont1" / "b.pak").read_bytes())
        self.assertTrue(a.is_dir() and b.is_dir(), "Die Originale bleiben liegen.")
        self.assertEqual([(a.name, "addcont0", 0), (b.name, "addcont1", 1)], meldungen)

    def test_ein_vorhandener_addcont_ordner_wird_nicht_ueberschrieben(self) -> None:
        (self.spiel / "addcont0").mkdir()
        (self.spiel / "addcont0" / "mein.pak").write_bytes(b"meins")
        self._dlc(ID_DLC)
        fertig = dlc_emu.nachbarn_einbauen(str(self.spiel), dlc_emu.nachbar_dlc(str(self.spiel)), lambda *_a: None)
        self.assertEqual([(ID_DLC, 1)], fertig)
        self.assertEqual(b"meins", (self.spiel / "addcont0" / "mein.pak").read_bytes())

    def test_hoechstens_elf_einhaengepunkte(self) -> None:
        nachbarn = [("EP1001-PPSA14299_00-%016d" % i, str(self._dlc("EP1001-PPSA14299_00-%016d" % i))) for i in range(13)]
        fertig = dlc_emu.nachbarn_einbauen(str(self.spiel), nachbarn, lambda *_a: None)
        self.assertEqual(dlc_emu.MAX_EINHAENGEPUNKTE, len(fertig))
        self.assertLessEqual(len("/app0/addcont%d" % (len(fertig) - 1)), 15)


class EinbauAblaufTests(unittest.TestCase):
    """``_integration_dlc`` im Ganzen: Bibliotheken, DLC-Ordner der Herkunft, ``dlc_emu.ini``."""

    def test_arbeitskopie_bekommt_ordner_der_herkunft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wurzel = Path(tmp)
            herkunft = wurzel / "PPSA14299-app0"
            (herkunft / "sce_sys").mkdir(parents=True)
            (herkunft / "sce_sys" / "param.json").write_text(json.dumps({"titleId": "PPSA14299"}), encoding="utf-8")
            dlc = wurzel / (ID_DLC + "-ac")
            dlc.mkdir()
            (dlc / "a.pak").write_bytes(b"daten")
            kopie = wurzel / "arbeit" / "PPSA14299-app0"
            (kopie / "sce_sys").mkdir(parents=True)
            g = GUI.__new__(GUI)
            g._log: list = []
            g._append_to_log = g._log.append
            g._t = lambda schluessel, **w: schluessel
            g._set_status = lambda *_a, **_k: None
            g._ampr_resolve_store = lambda explicit="": str(PROJEKT / "PlayGo & AMPR_EMU")
            g._fakelib_pfad = lambda ordner: Path(ordner) / "fakelib"
            g._ampr_quelle_original = str(herkunft)
            self.assertTrue(g._integration_dlc(str(kopie)))
            self.assertEqual(b"daten", (kopie / "addcont0" / "a.pak").read_bytes())
            self.assertEqual(3, len(list((kopie / "fakelib").glob("*.sprx"))))
            ini = (kopie / "dlc_emu.ini").read_text(encoding="utf-8")
            self.assertIn("content_id=%s\nmount_point=/app0/addcont0" % ID_DLC, ini)
            self.assertIn("main.integrate_dlc_nachbar", g._log)

    def test_ohne_herkunftsordner_keine_nachbarn(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            kopie = Path(tmp) / "PPSA14299-app0"
            (kopie / "sce_sys").mkdir(parents=True)
            (Path(tmp) / (ID_DLC + "-ac")).mkdir()
            g = GUI.__new__(GUI)
            g._append_to_log = lambda *_a: None
            g._t = lambda schluessel, **w: schluessel
            g._set_status = lambda *_a, **_k: None
            g._ampr_resolve_store = lambda explicit="": str(PROJEKT / "PlayGo & AMPR_EMU")
            g._fakelib_pfad = lambda ordner: Path(ordner) / "fakelib"
            g._ampr_quelle_original = ""
            self.assertTrue(g._integration_dlc(str(kopie)))
            self.assertFalse((kopie / "addcont0").exists())


class IniTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dump = Path(tmp.name)

    def test_ordner_bekommen_psac_mit_einhaengepunkt_und_lizenzen_psal(self) -> None:
        (self.dump / "dlcmap.json").write_text(
            json.dumps({"dlcmap": {ID_LIZENZ: "DLC_PreOrder", ID_DLC: "Pack"}}), encoding="utf-8")
        stand, anzahl = dlc_emu.ini_anlegen(str(self.dump), [(ID_DLC, 0)])
        self.assertEqual(("angelegt", 2), (stand, anzahl))
        text = (self.dump / "dlc_emu.ini").read_text(encoding="utf-8")
        self.assertEqual(
            "[PSAC]\ncontent_id=%s\nmount_point=/app0/addcont0\n\n[PSAL]\ncontent_id=%s\n" % (ID_DLC, ID_LIZENZ), text)

    def test_nur_ordner_ohne_karte(self) -> None:
        stand, anzahl = dlc_emu.ini_anlegen(str(self.dump), [(ID_DLC, 3)])
        self.assertEqual(("angelegt", 1), (stand, anzahl))
        self.assertIn("mount_point=/app0/addcont3", (self.dump / "dlc_emu.ini").read_text(encoding="utf-8"))

    def test_ohne_ordner_bleibt_es_bei_psal(self) -> None:
        (self.dump / "dlcmap.json").write_text(json.dumps({"dlcmap": {ID_LIZENZ: "x"}}), encoding="utf-8")
        self.assertEqual(("angelegt", 1), dlc_emu.ini_anlegen(str(self.dump)))
        self.assertTrue((self.dump / "dlc_emu.ini").read_text(encoding="utf-8").startswith("[PSAL]"))

    def test_vorhandene_ini_bleibt_auch_mit_ordnern(self) -> None:
        (self.dump / "dlc_emu.ini").write_text("[PSAC]\n", encoding="utf-8")
        self.assertEqual(("vorhanden", 0), dlc_emu.ini_anlegen(str(self.dump), [(ID_DLC, 0)]))


if __name__ == "__main__":
    unittest.main()
