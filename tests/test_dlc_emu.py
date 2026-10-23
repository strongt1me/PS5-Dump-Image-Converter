# -*- coding: utf-8 -*-
"""DLC EMU (drakmor/dlc_emu 0.3) als Kaestchen beim Erstellen (21.10.2026)."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import dlc_emu                     # noqa: E402

SPEICHER = str(PROJEKT / "PlayGo & AMPR_EMU")
HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
#: Release 0.3 von drakmor/dlc_emu: SHA-256 der Anhaenge ``nolog`` (aus dem Zip ``dlc_emu_0.3.zip``).
NOLOG_SHA = {
    "libSceAppContent.sprx": "53e485e22970c693ab70c05bd78b8f627442ed41ca9a49692b38615046494a6b",
    "libSceGameUpdate.sprx": "1e31ddbe4809b7c5ec117e9b7e1227befe757c31d1f5f73e6c7d5a3d2d238973",
    "libSceNpEntitlementAccess.sprx": "3f1826f20e174ff0f7aaa8d7f3f7e386dfcca1136c9e4c0e72a49e041c0b1488",
}
ID_A = "UP9000-PPSA01234_00-SAMPLECONTENT001"
ID_B = "EP0000-PPSA09999_00-ZUSATZINHALT0001"
EIGENE = "EP0000-PPSA09999_00-SPIELSELBST00001"


class MitgelieferterSatzTests(unittest.TestCase):
    def test_fassung_0_3_liegt_bei(self) -> None:
        self.assertIn("0.3", dlc_emu.fassungen(SPEICHER))

    def test_nolog_ist_das_original_des_release(self) -> None:
        ordner = Path(dlc_emu.bibliotheksordner(SPEICHER))
        self.assertEqual("nolog", ordner.name)
        for name, soll in NOLOG_SHA.items():
            self.assertEqual(soll, hashlib.sha256((ordner / name).read_bytes()).hexdigest(), name)

    def test_log_wird_nur_auf_wunsch_genommen(self) -> None:
        self.assertEqual("log", Path(dlc_emu.bibliotheksordner(SPEICHER, protokoll=True)).name)

    def test_unbekannter_speicher_gibt_leer(self) -> None:
        with tempfile.TemporaryDirectory() as leer:
            self.assertEqual([], dlc_emu.fassungen(leer))
            self.assertEqual("", dlc_emu.bibliotheksordner(leer))

    def test_neueste_fassung_gewinnt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for fassung in ("0.3", "0.10", "0.9"):
                ordner = Path(tmp, dlc_emu.ORDNER, fassung, "nolog")
                ordner.mkdir(parents=True)
                for name in dlc_emu.BIBLIOTHEKEN:
                    (ordner / name).write_bytes(b"x")
            self.assertEqual(["0.10", "0.9", "0.3"], dlc_emu.fassungen(tmp))
            self.assertEqual("0.10", dlc_emu.fassung_aus_ordner(dlc_emu.bibliotheksordner(tmp)))


class EinbauTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dump = Path(self.tmp.name)
        self.quelle = dlc_emu.bibliotheksordner(SPEICHER)

    def test_drei_bibliotheken_kommen_in_den_fakelib_ordner(self) -> None:
        meldungen: list[str] = []
        namen = dlc_emu.bibliotheken_einbauen(self.quelle, self.dump / "fakelib", meldungen.append)
        self.assertEqual(sorted(dlc_emu.BIBLIOTHEKEN), sorted(namen))
        for name, soll in NOLOG_SHA.items():
            self.assertEqual(soll, hashlib.sha256((self.dump / "fakelib" / name).read_bytes()).hexdigest())
        self.assertEqual([], meldungen)

    def test_ein_spieloriginal_wird_einmal_gesichert(self) -> None:
        fakelib = self.dump / "fakelib"
        fakelib.mkdir()
        (fakelib / "libSceAppContent.sprx").write_bytes(b"ORIGINAL")
        meldungen: list[str] = []
        dlc_emu.bibliotheken_einbauen(self.quelle, fakelib, meldungen.append)
        self.assertEqual(["libSceAppContent.sprx.orig"], meldungen)
        self.assertEqual(b"ORIGINAL", (fakelib / "libSceAppContent.sprx.orig").read_bytes())
        # Zweiter Lauf: Die Datei ist jetzt unsere, die Sicherung bleibt das Original.
        dlc_emu.bibliotheken_einbauen(self.quelle, fakelib, meldungen.append)
        self.assertEqual(b"ORIGINAL", (fakelib / "libSceAppContent.sprx.orig").read_bytes())
        self.assertEqual(1, len(meldungen))

    def test_eine_eigene_fassung_wird_nicht_als_original_gesichert(self) -> None:
        fakelib = self.dump / "fakelib"
        dlc_emu.bibliotheken_einbauen(self.quelle, fakelib, lambda _n: None)
        meldungen: list[str] = []
        dlc_emu.bibliotheken_einbauen(self.quelle, fakelib, meldungen.append)
        self.assertEqual([], meldungen)
        self.assertEqual([], list(fakelib.glob("*.orig")))


class IniTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dump = Path(self.tmp.name)

    def _eboot(self, *ids: str) -> None:
        (self.dump / "eboot.bin").write_bytes(b"\x00junk\x00" + b"\x00".join(i.encode() for i in ids) + b"\x00")

    def test_vorhandene_ini_bleibt(self) -> None:
        (self.dump / "dlc_emu.ini").write_text("[PSAC]\ncontent_id=%s\n" % ID_A, encoding="utf-8")
        self._eboot(ID_B)
        self.assertEqual(("vorhanden", 0), dlc_emu.ini_anlegen(str(self.dump)))
        self.assertIn(ID_A, (self.dump / "dlc_emu.ini").read_text(encoding="utf-8"))
        self.assertNotIn(ID_B, (self.dump / "dlc_emu.ini").read_text(encoding="utf-8"))

    def test_ini_aus_eboot_ohne_die_id_des_spiels(self) -> None:
        self._eboot(ID_A, EIGENE, ID_B, ID_A)
        (self.dump / "sce_sys").mkdir()
        (self.dump / "sce_sys" / "param.json").write_text(json.dumps({"contentId": EIGENE}), encoding="utf-8")
        self.assertEqual(("angelegt", 2), dlc_emu.ini_anlegen(str(self.dump)))
        text = (self.dump / "dlc_emu.ini").read_text(encoding="utf-8")
        self.assertEqual("[PSAL]\ncontent_id=%s\n\n[PSAL]\ncontent_id=%s\n" % (ID_A, ID_B), text)

    def test_ini_aus_der_dlcmap_des_dumpers(self) -> None:
        """Gemessen am echten Dump von Double Dragon Revive (Laufwerk E, Ordner Game Dumps): Der Schluessel ist die Content-ID."""
        self._eboot(ID_A)
        (self.dump / "dlcmap.json").write_text(
            json.dumps({"dlcmap": {"JP0036-PPSA23000_00-DDREVIVECOLOR000": "DLC_PreOrder", "kein-id": "x"}}),
            encoding="utf-8")
        self.assertEqual(("angelegt", 1), dlc_emu.ini_anlegen(str(self.dump)))
        self.assertEqual("[PSAL]\ncontent_id=JP0036-PPSA23000_00-DDREVIVECOLOR000\n",
                         (self.dump / "dlc_emu.ini").read_text(encoding="utf-8"))

    def test_ohne_dlcmap_gilt_die_eboot(self) -> None:
        self._eboot(ID_A)
        self.assertEqual(("angelegt", 1), dlc_emu.ini_anlegen(str(self.dump)))

    def test_ohne_ids_wird_nichts_geschrieben(self) -> None:
        self._eboot()
        self.assertEqual(("keine", 0), dlc_emu.ini_anlegen(str(self.dump)))
        self.assertFalse((self.dump / "dlc_emu.ini").exists())

    def test_ohne_eboot_wird_nichts_geschrieben(self) -> None:
        self.assertEqual(("keine", 0), dlc_emu.ini_anlegen(str(self.dump)))

    def test_id_ueber_eine_blockgrenze_wird_gefunden(self) -> None:
        luft = b"\x00" * (4 * 1024 * 1024 - 10)
        (self.dump / "eboot.bin").write_bytes(luft + ID_A.encode() + b"\x00")
        self.assertEqual([ID_A], dlc_emu.content_ids_in(str(self.dump / "eboot.bin")))

    def test_zu_lange_zeichenfolgen_zaehlen_nicht(self) -> None:
        (self.dump / "eboot.bin").write_bytes(b"A" + ID_A.encode() + b"B")
        self.assertEqual([], dlc_emu.content_ids_in(str(self.dump / "eboot.bin")))

    def test_die_ini_bleibt_unter_der_grenze_der_bibliothek(self) -> None:
        viele = ["UP9000-PPSA01234_00-%016d" % i for i in range(3000)]
        text = dlc_emu.ini_text(viele)
        self.assertLessEqual(len(text.encode("utf-8")), dlc_emu.INI_MAX_BYTES)
        self.assertGreater(text.count("[PSAL]"), 500)


class QuelltextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = HAUPT.read_text(encoding="utf-8")

    def test_dlc_kommt_vor_ampr_und_nach_dem_backport(self) -> None:
        anfang = self.quelle.index("def _integration_anwenden(")
        text = self.quelle[anfang:anfang + 9000]
        self.assertLess(text.index("_integration_backport(arbeitsordner)"), text.index("_integration_dlc(arbeitsordner)"))
        self.assertLess(text.index("_integration_dlc(arbeitsordner)"), text.index("_integration_ampr(arbeitsordner"))

    def test_das_kaestchen_steht_in_einer_zweiten_zeile_und_nicht_in_der_kette(self) -> None:
        """Mit dem Kaestchen braucht die Einbauzeile bei Mindestbreite 755 px, die Karte hat 672."""
        anfang = self.quelle.index("def _kartenzeilen(self)")
        kette = self.quelle[anfang:self.quelle.index("_KARTEN_INNENRAND = 30", anfang)]
        self.assertNotIn("dlc_integrate_check", kette)
        self.assertIn("self._dlc_zeile_setzen()", self.quelle)

    def test_der_lauf_haelt_das_kaestchen_fest(self) -> None:
        anfang = self.quelle.index("_LAUF_VARIABLEN: tuple[str, ...]")
        self.assertIn("dlc_integrate_var", self.quelle[anfang:anfang + 400])


if __name__ == "__main__":
    unittest.main()
