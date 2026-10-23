# -*- coding: utf-8 -*-
"""DLC EMU: Hinweis, wenn das Spiel Zusatzinhalte hat - wie bei PlayGo (22.10.2026).

Wer die Kaestchen beim Erstellen nicht kennt, soll genau dann gefragt werden, wenn DLC EMU gebraucht wird: bei einem
Dump-Ordner und bei einem Abbild, vor der eigentlichen Arbeit.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as GUI   # noqa: E402

LEER = [" " * 19] * 7


class MerkmalOrdnerTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dump = Path(tmp.name)

    def _param(self, eintraege) -> None:
        (self.dump / "sce_sys").mkdir(exist_ok=True)
        (self.dump / "sce_sys" / "param.json").write_text(
            json.dumps({"titleId": "PPSA00001", "addcont": {"serviceIdForSharing": eintraege}}), encoding="utf-8")

    def test_ohne_zusatzinhalt_ist_es_leer(self) -> None:
        self._param(LEER)
        (self.dump / "eboot.bin").write_bytes(b"x")
        self.assertEqual("", GUI._titel_hat_dlc(str(self.dump)))

    def test_dlc_emu_ini_zaehlt(self) -> None:
        (self.dump / "dlc_emu.ini").write_text("[PSAC]\n", encoding="utf-8")
        self.assertEqual("dlc_emu.ini", GUI._titel_hat_dlc(str(self.dump)))

    def test_addcont_ordner_mit_inhalt_zaehlt(self) -> None:
        (self.dump / "addcont0").mkdir()
        (self.dump / "addcont0" / "datei.pak").write_bytes(b"x")
        self.assertEqual("addcont0/", GUI._titel_hat_dlc(str(self.dump)))

    def test_leerer_addcont_ordner_zaehlt_nicht(self) -> None:
        (self.dump / "addcont").mkdir()
        self.assertEqual("", GUI._titel_hat_dlc(str(self.dump)))

    def test_ausgefuellter_eintrag_in_der_param_json_ist_kein_merkmal(self) -> None:
        """Gemessen an 48 Dumps: ``serviceIdForSharing`` traegt PS4-Kennungen (CUSA...), keine Zusatzinhalte."""
        self._param(LEER[:3] + ["EP0002-CUSA23470_00"] + LEER[4:])
        self.assertEqual("", GUI._titel_hat_dlc(str(self.dump)))

    def test_dlcmap_mit_eintraegen_zaehlt(self) -> None:
        (self.dump / "dlcmap.json").write_text(
            json.dumps({"dlcmap": {"JP0036-PPSA23000_00-DDREVIVECOLOR000": "DLC_PreOrder"}}), encoding="utf-8")
        self.assertEqual("dlcmap.json", GUI._titel_hat_dlc(str(self.dump)))

    def test_leere_oder_kaputte_dlcmap_zaehlt_nicht(self) -> None:
        for inhalt in ('{"dlcmap": {}}', "{kaputt", "[]", '{"dlcmap": {"kein-id": "x"}}'):
            with self.subTest(inhalt=inhalt):
                (self.dump / "dlcmap.json").write_text(inhalt, encoding="utf-8")
                self.assertEqual("", GUI._titel_hat_dlc(str(self.dump)))

    def test_kaputte_param_json_ist_kein_fund_und_kein_absturz(self) -> None:
        (self.dump / "sce_sys").mkdir()
        (self.dump / "sce_sys" / "param.json").write_text("{kaputt", encoding="utf-8")
        self.assertEqual("", GUI._titel_hat_dlc(str(self.dump)))

    def test_ordner_gibt_es_nicht(self) -> None:
        self.assertEqual("", GUI._titel_hat_dlc(str(self.dump / "fehlt")))

    def test_echter_dump_ohne_dlc(self) -> None:
        echt = Path(r"D:\PS5 TEMP\A1_Ausgabe\AMPR_EMU__folder\PPSA19015 Arcade Game Zone")
        if not (echt / "sce_sys" / "param.json").is_file():
            self.skipTest("kein echter Dump vorhanden")
        self.assertEqual("", GUI._titel_hat_dlc(str(echt)))


class MerkmalAbbildTests(unittest.TestCase):
    def test_pfadlisten(self) -> None:
        fall = {
            "": ["eboot.bin", "sce_sys/param.json", "sce_module/libc.prx"],
            "dlc_emu.ini": ["eboot.bin", "dlc_emu.ini"],
            "dlcmap.json": ["eboot.bin", "dlcmap.json"],
            "addcont0/": ["eboot.bin", "addcont0/a.pak"],
            "addcont/": ["PPSA1/eboot.bin", "PPSA1/addcont/b.pak"],
        }
        for erwartet, pfade in fall.items():
            with self.subTest(erwartet=erwartet):
                self.assertEqual(erwartet, GUI._dlc_merkmal_in(pfade))

    def test_pfade_mit_rueckstrich_und_grossschreibung(self) -> None:
        self.assertEqual("ADDCONT1/", GUI._dlc_merkmal_in(["ADDCONT1\\x.pak"]))
        self.assertEqual("dlc_emu.ini", GUI._dlc_merkmal_in(["DLC_EMU.INI"]))

    def test_ein_ordnername_allein_ohne_datei_zaehlt_nicht(self) -> None:
        self.assertEqual("", GUI._dlc_merkmal_in(["addcont0"]))


class FrageTests(unittest.TestCase):
    @staticmethod
    def _gui(*, merkmal="addcont0/", dlc_an=False, cli=False):
        g = GUI.__new__(GUI)
        g._tk_wert = lambda name, vorgabe=None: dlc_an if name == "dlc_integrate_var" else vorgabe
        g._set_status = lambda *_a, **_k: None
        g._log: list = []
        g._append_to_log = g._log.append
        g._t = lambda schluessel, **w: schluessel
        g._cli_mode = cli
        g.is_running = True
        g._dlc_merkmal_der_quelle = lambda src: merkmal
        g._dlc_einschalten = mock.Mock()
        g._ask_yesno_threadsafe = mock.Mock(return_value=True)
        return g

    def test_ja_schaltet_ein(self) -> None:
        g = self._gui()
        g._dlc_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_called_once()
        g._dlc_einschalten.assert_called_once()
        self.assertEqual(["main.dlc_eingeschaltet"], g._log)

    def test_nein_bleibt_aus(self) -> None:
        g = self._gui()
        g._ask_yesno_threadsafe.return_value = False
        g._dlc_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._dlc_einschalten.assert_not_called()
        self.assertEqual(["main.dlc_bleibt_aus"], g._log)

    def test_kein_fund_keine_frage(self) -> None:
        g = self._gui(merkmal="")
        g._dlc_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)

    def test_schon_angehakt_keine_frage(self) -> None:
        g = self._gui(dlc_an=True)
        g._dlc_merkmal_der_quelle = mock.Mock(side_effect=AssertionError("nicht noetig"))
        g._dlc_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()

    def test_sammelkonvertierung_fragt_nie(self) -> None:
        g = self._gui()
        g._dlc_vor_dem_lauf_klaeren("batch_convert", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()

    def test_nicht_einsehbar_gibt_hinweis_ohne_frage(self) -> None:
        g = self._gui(merkmal=None)
        g._dlc_vor_dem_lauf_klaeren("pack_folder", "C:/x.ffpkg")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(["main.dlc_nicht_pruefbar"], g._log)

    def test_kommandozeile_fragt_nie(self) -> None:
        g = self._gui(cli=True)
        g._dlc_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(["main.integrate_dlc_empfohlen"], g._log)


class QuelltextTests(unittest.TestCase):
    def test_aufruf_steht_nach_playgo_und_vor_der_arbeit(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        a = text.index("self._playgo_vor_dem_lauf_klaeren(mode, src)")
        b = text.index("self._dlc_vor_dem_lauf_klaeren(mode, src)")
        c = text.index("success = self._run_flexible_conversion(mode, src, dst)", b)
        self.assertLess(a, b)
        self.assertLess(b, c)


if __name__ == "__main__":
    unittest.main()
