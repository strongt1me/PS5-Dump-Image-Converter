# -*- coding: utf-8 -*-
"""Die Pruefumgebung vergisst eine gespeicherte Anzeigesprache vor jeder Testklasse (14.11.2026).

Befund: Im Gesamtlauf teilen sich die Pruefstaende einen Einstellungsordner, der von Lauf zu Lauf stehen bleibt. Ein Test, der
``language`` speicherte (Sprachknopf, ``_save_setting``), liess jede spaetere Klasse ihr Fenster in dieser Sprache bauen -
``test_kartenzeilen`` mass die Karte auf Englisch, wo der Drehknopf 8 px breiter ist, und fiel nur im Gesamtlauf durch.
``conftest._gespeicherte_sprache_vergessen`` raeumt davor auf; hier wird die Hilfe und ihr Einsatz geprueft.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402


def _paths_json() -> Path:
    return Path(os.environ[pruefumgebung.UMGEBUNGSNAME]) / "paths.json"


class HilfeTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ordner = Path(tmp.name)
        self.datei = self.ordner / "paths.json"

    def test_entfernt_nur_die_sprache(self) -> None:
        self.datei.write_text(json.dumps({"language": "en", "theme": "dunkel", "temp_dir": "E:\\X"}), encoding="utf-8")
        self.assertTrue(pruefumgebung.gespeicherte_sprache_vergessen(str(self.ordner)))
        self.assertEqual({"theme": "dunkel", "temp_dir": "E:\\X"}, json.loads(self.datei.read_text(encoding="utf-8")))

    def test_bom_bleibt_erhalten(self) -> None:
        self.datei.write_bytes(b"\xef\xbb\xbf" + json.dumps({"language": "fr", "a": 1}).encode("utf-8"))
        self.assertTrue(pruefumgebung.gespeicherte_sprache_vergessen(str(self.ordner)))
        roh = self.datei.read_bytes()
        self.assertTrue(roh.startswith(b"\xef\xbb\xbf"))
        self.assertEqual({"a": 1}, json.loads(roh.decode("utf-8-sig")))

    def test_ohne_sprache_bleibt_die_datei_wie_sie_ist(self) -> None:
        roh = b'{"theme":"hell"}'
        self.datei.write_bytes(roh)
        self.assertFalse(pruefumgebung.gespeicherte_sprache_vergessen(str(self.ordner)))
        self.assertEqual(roh, self.datei.read_bytes())

    def test_fehlende_und_kaputte_datei_bleiben_unberuehrt(self) -> None:
        self.assertFalse(pruefumgebung.gespeicherte_sprache_vergessen(str(self.ordner)))
        kaputt = b'{"language": "en", '
        self.datei.write_bytes(kaputt)
        self.assertFalse(pruefumgebung.gespeicherte_sprache_vergessen(str(self.ordner)))
        self.assertEqual(kaputt, self.datei.read_bytes())
        self.datei.write_bytes(b'["language"]')
        self.assertFalse(pruefumgebung.gespeicherte_sprache_vergessen(str(self.ordner)))

    def test_ohne_ordner_geschieht_nichts(self) -> None:
        gemerkt = os.environ.pop(pruefumgebung.UMGEBUNGSNAME, None)
        try:
            self.assertFalse(pruefumgebung.gespeicherte_sprache_vergessen())
        finally:
            if gemerkt is not None:
                os.environ[pruefumgebung.UMGEBUNGSNAME] = gemerkt


class ASpeichertEineSprache(unittest.TestCase):
    """Absichtlich ohne Aufraeumen: Hier entsteht das Leck, das die naechste Klasse nicht sehen darf."""

    def test_speichert_englisch_in_den_gemeinsamen_ordner(self) -> None:
        datei = _paths_json()
        datei.parent.mkdir(parents=True, exist_ok=True)
        try:
            daten = json.loads(datei.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            daten = {}
        daten["language"] = "en"
        datei.write_text(json.dumps(daten), encoding="utf-8")
        self.assertEqual("en", json.loads(datei.read_text(encoding="utf-8"))["language"])


class BSiehtDieSpracheNichtMehr(unittest.TestCase):
    """Folgt in der Datei auf Klasse A: Ohne ``conftest._gespeicherte_sprache_vergessen`` stuende hier noch ``en``."""

    def test_die_gespeicherte_sprache_ist_weg(self) -> None:
        datei = _paths_json()
        daten = {}
        if datei.is_file():
            daten = json.loads(datei.read_text(encoding="utf-8-sig"))
        self.assertNotIn("language", daten, "Eine Sprache aus einer frueheren Klasse gilt noch: %r" % daten.get("language"))


if __name__ == "__main__":
    unittest.main()
