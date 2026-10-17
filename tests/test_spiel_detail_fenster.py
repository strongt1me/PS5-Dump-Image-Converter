# -*- coding: utf-8 -*-
"""Tests fuer die Hilfsfunktionen des Spiel-Detail-Fensters (seit v1.9.83)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.ui.spiel_detail_fenster import (  # noqa: E402
    _activity_lesen,
    _groesse_text,
    _self_dateien_suchen,
    _trophy_sets_suchen,
)


class GruesseTextTests(unittest.TestCase):
    def test_bytes(self) -> None:
        self.assertEqual("512 B", _groesse_text(512))

    def test_kilobytes(self) -> None:
        self.assertIn("KB", _groesse_text(2048))

    def test_megabytes(self) -> None:
        self.assertIn("MB", _groesse_text(2 * 1024 ** 2))

    def test_null(self) -> None:
        self.assertEqual("0 B", _groesse_text(0))


class SelfDateienSuchenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _schreib(self, pfad: str, inhalt: bytes = b"\x7fELF") -> None:
        p = Path(self.ordner) / pfad
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(inhalt)

    def test_findet_elf_in_app0(self) -> None:
        self._schreib("app0/eboot.bin")
        gefunden = _self_dateien_suchen(self.ordner)
        self.assertTrue(any("eboot.bin" in f for f in gefunden))

    def test_findet_prx_in_sce_module(self) -> None:
        self._schreib("sce_module/libSce.prx")
        gefunden = _self_dateien_suchen(self.ordner)
        self.assertTrue(any("libSce.prx" in f for f in gefunden))

    def test_ignoriert_andere_endungen(self) -> None:
        self._schreib("app0/data.txt", b"Hallo")
        gefunden = _self_dateien_suchen(self.ordner)
        self.assertFalse(any("data.txt" in f for f in gefunden))

    def test_leerer_ordner_liefert_nichts(self) -> None:
        self.assertEqual([], _self_dateien_suchen(self.ordner))


class ActivityLesenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _schreib_activity(self, daten) -> None:
        sce = Path(self.ordner) / "sce_sys"
        sce.mkdir(parents=True, exist_ok=True)
        (sce / "activity.json").write_text(json.dumps(daten), encoding="utf-8")

    def test_liest_liste_von_eintraegen(self) -> None:
        self._schreib_activity([{"activityId": "act01", "type": "EARN"}, {"activityId": "act02"}])
        eintraege = _activity_lesen(self.ordner)
        self.assertEqual(2, len(eintraege))
        self.assertEqual("act01", eintraege[0]["activityId"])

    def test_liest_dict_mit_activities_schluessel(self) -> None:
        self._schreib_activity({"activities": [{"activityId": "x"}]})
        eintraege = _activity_lesen(self.ordner)
        self.assertEqual(1, len(eintraege))

    def test_fehlende_datei_liefert_leere_liste(self) -> None:
        self.assertEqual([], _activity_lesen(self.ordner))

    def test_kaputte_json_liefert_leere_liste(self) -> None:
        sce = Path(self.ordner) / "sce_sys"
        sce.mkdir(parents=True, exist_ok=True)
        (sce / "activity.json").write_bytes(b"{kaputt}")
        self.assertEqual([], _activity_lesen(self.ordner))


class TrophySetsSuchenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _schreib(self, pfad: str) -> None:
        p = Path(self.ordner) / pfad
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"TROPHY_DUMMY")

    def test_findet_trp_in_sce_sys_trophy(self) -> None:
        self._schreib("sce_sys/trophy/trophy00.trp")
        gefunden = _trophy_sets_suchen(self.ordner)
        self.assertTrue(any("trophy00.trp" in f for f in gefunden))

    def test_findet_trp_in_sce_trophy(self) -> None:
        self._schreib("sce_trophy/trophy00.trp")
        gefunden = _trophy_sets_suchen(self.ordner)
        self.assertTrue(any("trophy00.trp" in f for f in gefunden))

    def test_ignoriert_andere_endungen(self) -> None:
        self._schreib("sce_sys/trophy/readme.txt")
        gefunden = _trophy_sets_suchen(self.ordner)
        self.assertFalse(any("readme.txt" in f for f in gefunden))

    def test_leerer_ordner_liefert_nichts(self) -> None:
        self.assertEqual([], _trophy_sets_suchen(self.ordner))


if __name__ == "__main__":
    unittest.main()
