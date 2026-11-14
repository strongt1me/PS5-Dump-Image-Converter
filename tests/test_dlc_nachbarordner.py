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


class GroesseTests(unittest.TestCase):
    """``groesse_der_nachbarn``: Was ``nachbarn_einbauen`` kopieren wuerde, in Bytes - ohne die Oberflaeche festzuhalten."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = Path(tmp.name)

    def _dlc(self, content_id: str, dateien: "dict[str, int]") -> "tuple[str, str]":
        ordner = self.wurzel / (content_id + "-ac")
        for rel, groesse in dateien.items():
            ziel = ordner / rel
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(b"x" * groesse)
        return content_id, str(ordner)

    def test_summe_ueber_alle_ordner_und_unterordner(self) -> None:
        a = self._dlc(ID_DLC, {"a.pak": 1000, "tief/er/b.pak": 2000})
        b = self._dlc(ID_DLC2, {"c.pak": 4000})
        self.assertEqual(7000, dlc_emu.groesse_der_nachbarn([a, b]))

    def test_leere_liste_ist_null(self) -> None:
        self.assertEqual(0, dlc_emu.groesse_der_nachbarn([]))

    def test_nur_die_ersten_elf_zaehlen_wie_beim_einbauen(self) -> None:
        nachbarn = [self._dlc("EP1001-PPSA14299_00-%016d" % i, {"a.pak": 10}) for i in range(13)]
        self.assertEqual(10 * dlc_emu.MAX_EINHAENGEPUNKTE, dlc_emu.groesse_der_nachbarn(nachbarn))

    def test_fehlender_ordner_zaehlt_nicht_und_wirft_nicht(self) -> None:
        a = self._dlc(ID_DLC, {"a.pak": 500})
        weg = (ID_DLC2, str(self.wurzel / "gibtsnicht"))
        self.assertEqual(500, dlc_emu.groesse_der_nachbarn([weg, a]))

    def test_zeitgrenze_beendet_das_zaehlen(self) -> None:
        """Gegenprobe zur Summe: Ohne Zeit bleibt es bei dem, was gezaehlt war (hier nichts), statt zu haengen."""
        a = self._dlc(ID_DLC, {"a.pak": 500})
        self.assertEqual(0, dlc_emu.groesse_der_nachbarn([a], zeit=0.0))


class PlatzbedarfMitDlcTests(unittest.TestCase):
    """Die Platzpruefung kennt die DLC-Ordner neben dem Spiel (Befund 14.11.2026).

    ``_integration_dlc`` kopiert sie in den Arbeitsstand - im Strom in den Ueberlagerungsordner (``_PLATZFAKTOR_STROM_TEMP`` 5 %
    der Quelle), sonst in die Arbeitskopie - und sie kommen ins Ergebnis. Die Rechnung nahm sie bisher nirgends mit.
    """

    GIB = 1024 ** 3

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = Path(tmp.name)
        self.spiel = self.wurzel / "PPSA14299-app0"
        (self.spiel / "sce_sys").mkdir(parents=True)
        (self.spiel / "sce_sys" / "param.json").write_text(json.dumps({"titleId": "PPSA14299"}), encoding="utf-8")
        self.dlc_bytes = 3 * 1024 * 1024
        ordner = self.wurzel / (ID_DLC + "-ac")
        ordner.mkdir()
        (ordner / "a.pak").write_bytes(b"x" * self.dlc_bytes)

    def _gui(self, *, dlc: bool, strom: bool, kopie: bool = True) -> "GUI":
        g = GUI.__new__(GUI)
        g._quellgroesse_ermitteln = lambda src: 150 * self.GIB
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: kopie
        g._umhuellt_neu_packen = False
        g._strom_fuer_ordner_gewaehlt = lambda: strom
        g._lz4_strom_im_voraus_ausgeschlossen = lambda src, ordner: False
        if dlc:
            g.dlc_integrate_var = type("V", (), {"get": staticmethod(lambda: True)})()
        return g

    def test_strom_zaehlt_die_dlc_ordner_in_temp_und_ziel(self) -> None:
        ohne = self._gui(dlc=False, strom=True)._platzbedarf_je_quelle(str(self.spiel), "exfat")
        mit = self._gui(dlc=True, strom=True)._platzbedarf_je_quelle(str(self.spiel), "exfat")
        self.assertEqual(self.dlc_bytes, mit[0] - ohne[0], "Temp: der Ueberlagerungsordner nimmt die DLC-Ordner auf")
        self.assertEqual(self.dlc_bytes, mit[1] - ohne[1], "Ziel: die DLC-Ordner gehoeren zum Ergebnis")
        self.assertEqual(ohne[2], mit[2])

    def test_arbeitskopie_zaehlt_die_dlc_ordner_in_temp_und_ziel(self) -> None:
        ohne = self._gui(dlc=False, strom=False)._platzbedarf_je_quelle(str(self.spiel), "exfat")
        mit = self._gui(dlc=True, strom=False)._platzbedarf_je_quelle(str(self.spiel), "exfat")
        self.assertEqual(self.dlc_bytes, mit[0] - ohne[0])
        self.assertEqual(self.dlc_bytes, mit[1] - ohne[1])

    def test_ohne_arbeitskopie_kein_dlc_in_temp_aber_im_ziel(self) -> None:
        """Ohne Einbau-Arbeitskopie (Quelle bleibt, nichts wird kopiert) waechst Temp nicht; das Ziel zaehlt sie."""
        ohne = self._gui(dlc=False, strom=False, kopie=False)._platzbedarf_je_quelle(str(self.spiel), "exfat")
        mit = self._gui(dlc=True, strom=False, kopie=False)._platzbedarf_je_quelle(str(self.spiel), "exfat")
        self.assertEqual(0, mit[0] - ohne[0])
        self.assertEqual(self.dlc_bytes, mit[1] - ohne[1])

    def test_ohne_haken_aendert_sich_nichts(self) -> None:
        """Gegenprobe: DLC EMU nicht angehakt, also kommt nichts in den Arbeitsstand."""
        g = self._gui(dlc=False, strom=True)
        self.assertEqual(0, g._dlc_nachbarn_bytes(str(self.spiel)))

    def test_fremde_dlc_ordner_zaehlen_nicht(self) -> None:
        (self.wurzel / (ID_DLC + "-ac")).rename(self.wurzel / "EP1001-PPSA99999_00-ABCDEFGHIJKLMNOP-ac")
        self.assertEqual(0, self._gui(dlc=True, strom=True)._dlc_nachbarn_bytes(str(self.spiel)))

    def test_ein_abbild_als_quelle_hat_keine_nachbarn(self) -> None:
        abbild = self.wurzel / "spiel.exfat"
        abbild.write_bytes(b"x")
        self.assertEqual(0, self._gui(dlc=True, strom=True)._dlc_nachbarn_bytes(str(abbild)))

    def test_ein_fehler_beim_zaehlen_haelt_den_start_nicht_auf(self) -> None:
        g = self._gui(dlc=True, strom=True)
        original = dlc_emu.nachbar_dlc
        dlc_emu.nachbar_dlc = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kaputt"))
        try:
            self.assertEqual(0, g._dlc_nachbarn_bytes(str(self.spiel)))
        finally:
            dlc_emu.nachbar_dlc = original


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
