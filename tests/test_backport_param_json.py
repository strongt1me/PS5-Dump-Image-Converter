# -*- coding: utf-8 -*-
"""Backport: ``requiredSystemSoftwareVersion`` und ``sdkVersion`` in ``sce_sys/param.json`` herabsetzen (23.10.2026).

Vorbild ist ``ps5_backport_param_json`` im PS5-App-Dumper 2.10 (EchoStretch): Ist die Hauptversion eines der beiden Felder
hoeher als das Ziel, wird der Wert zu ``0xMM00000000000000``. Die Beispielwerte stammen aus echten Dumps.
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
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from ps5_validator.utils import ps5_pkg_backport as pkg     # noqa: E402

#: Auszug einer echten param.json (Double Dragon Revive): CRLF, Einrueckung mit zwei Leerzeichen.
ECHT = (b'{\r\n  "applicationCategoryType": 0,\r\n  "contentId": "JP0036-PPSA23000_00-DDRAGONREVIVE000",\r\n'
        b'  "requiredSystemSoftwareVersion": "0x1120000000000000",\r\n  "sdkVersion": "0x1000000000000000",\r\n'
        b'  "titleId": "PPSA23000"\r\n}')


def _gelesen(daten: bytes) -> dict:
    return json.loads(daten.decode("utf-8"))


class ReinFunktionTests(unittest.TestCase):
    def test_beide_felder_werden_auf_das_ziel_gesetzt(self) -> None:
        neu, aenderungen = bp.param_json_herabsetzen(ECHT, 7)
        werte = _gelesen(neu)
        self.assertEqual("0x0700000000000000", werte["requiredSystemSoftwareVersion"])
        self.assertEqual("0x0700000000000000", werte["sdkVersion"])
        self.assertEqual([("requiredSystemSoftwareVersion", "0x1120000000000000", "0x0700000000000000"),
                          ("sdkVersion", "0x1000000000000000", "0x0700000000000000")], aenderungen)

    def test_der_rest_der_datei_bleibt_byte_fuer_byte(self) -> None:
        neu, _a = bp.param_json_herabsetzen(ECHT, 7)
        self.assertEqual(len(ECHT), len(neu))
        gleich = sum(1 for a, b in zip(ECHT, neu) if a != b)
        self.assertLessEqual(gleich, 2 * 16)            # nur die beiden Werte
        self.assertIn(b"\r\n", neu)
        self.assertEqual(_gelesen(ECHT)["titleId"], _gelesen(neu)["titleId"])

    def test_nur_ein_feld_ueber_dem_ziel(self) -> None:
        """Kingdom Come Deliverance 2: verlangt 11.60, SDK aber nur 9."""
        daten = b'{"requiredSystemSoftwareVersion": "0x1160000000000000", "sdkVersion": "0x0900000000000000"}'
        neu, aenderungen = bp.param_json_herabsetzen(daten, 9)
        self.assertEqual(["requiredSystemSoftwareVersion"], [a[0] for a in aenderungen])
        self.assertEqual("0x0900000000000000", _gelesen(neu)["requiredSystemSoftwareVersion"])
        self.assertEqual("0x0900000000000000", _gelesen(neu)["sdkVersion"])

    def test_gleiche_hauptversion_bleibt_auch_mit_hoeherer_nebenversion(self) -> None:
        """Wie beim Dumper: Verglichen wird nur die Hauptversion."""
        daten = b'{"requiredSystemSoftwareVersion": "0x0750000000000000", "sdkVersion": "0x0700000000000000"}'
        neu, aenderungen = bp.param_json_herabsetzen(daten, 7)
        self.assertEqual(daten, neu)
        self.assertEqual([], aenderungen)

    def test_niedrigere_werte_bleiben(self) -> None:
        """Oddworld: verlangt 1.00, SDK 1 - bei Ziel 4 wird nichts hochgesetzt."""
        daten = b'{"requiredSystemSoftwareVersion": "0x0100000000000000", "sdkVersion": "0x0100000000000000"}'
        self.assertEqual((daten, []), bp.param_json_herabsetzen(daten, 4))

    def test_ziel_10_vergleicht_wie_der_dumper_als_hexzahl(self) -> None:
        """Ziel 10 heisst ``0x10`` - 11.xx (``0x11``) ist hoeher, 10.01 (``0x10``) nicht."""
        daten = b'{"requiredSystemSoftwareVersion": "0x1160000000000000", "sdkVersion": "0x1001000000000000"}'
        neu, aenderungen = bp.param_json_herabsetzen(daten, 10)
        self.assertEqual(["requiredSystemSoftwareVersion"], [a[0] for a in aenderungen])
        self.assertEqual("0x1000000000000000", _gelesen(neu)["requiredSystemSoftwareVersion"])
        self.assertEqual("0x1001000000000000", _gelesen(neu)["sdkVersion"])

    def test_echte_werte_aus_den_dumps(self) -> None:
        faelle = [("0x1160000000000000", 7, "0x0700000000000000"), ("0x0403000000000000", 7, None),
                  ("0x0920000000000000", 4, "0x0400000000000000"), ("0x1200000000000000", 11, "0x1100000000000000")]
        for alt, ziel, soll in faelle:
            with self.subTest(alt=alt, ziel=ziel):
                daten = ('{"requiredSystemSoftwareVersion": "%s"}' % alt).encode()
                neu, _a = bp.param_json_herabsetzen(daten, ziel)
                erwartet = soll or alt
                self.assertEqual(erwartet, _gelesen(neu)["requiredSystemSoftwareVersion"])

    def test_fehlende_oder_andere_formate_werden_uebergangen(self) -> None:
        for daten in (b"{}", b'{"sdkVersion": 10}', b'{"sdkVersion": "0x10"}', b"kein json", b""):
            with self.subTest(daten=daten):
                self.assertEqual((daten, []), bp.param_json_herabsetzen(daten, 4))

    def test_nur_das_erste_vorkommen_je_feld(self) -> None:
        daten = (b'{"sdkVersion": "0x1000000000000000", "x": {"sdkVersion": "0x1000000000000000"}}')
        neu, aenderungen = bp.param_json_herabsetzen(daten, 4)
        self.assertEqual(1, len(aenderungen))
        self.assertEqual(1, neu.count(b"0x0400000000000000"))
        self.assertEqual(1, neu.count(b"0x1000000000000000"))

    def test_unbekannte_firmware(self) -> None:
        with self.assertRaises(bp.BackportFehler):
            bp.param_json_herabsetzen(ECHT, 99)


class DateiTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dump = Path(tmp.name)
        (self.dump / "sce_sys").mkdir()
        self.pfad = self.dump / "sce_sys" / "param.json"
        self.pfad.write_bytes(ECHT)

    def test_datei_wird_umgeschrieben_ohne_zwischendatei(self) -> None:
        aenderungen = bp.param_json_anpassen(str(self.dump), 7)
        self.assertEqual(2, len(aenderungen))
        self.assertEqual("0x0700000000000000", _gelesen(self.pfad.read_bytes())["sdkVersion"])
        self.assertEqual([], list((self.dump / "sce_sys").glob("*.bp_neu")))

    def test_zweiter_lauf_aendert_nichts(self) -> None:
        bp.param_json_anpassen(str(self.dump), 7)
        vorher = self.pfad.read_bytes()
        self.assertEqual([], bp.param_json_anpassen(str(self.dump), 7))
        self.assertEqual(vorher, self.pfad.read_bytes())

    def test_ohne_datei_ist_es_leer(self) -> None:
        self.pfad.unlink()
        self.assertEqual([], bp.param_json_anpassen(str(self.dump), 7))

    def test_schreibfehler_laesst_die_datei_unveraendert(self) -> None:
        with mock.patch.object(os, "replace", side_effect=OSError("gesperrt")):
            with self.assertRaises(OSError):
                bp.param_json_anpassen(str(self.dump), 7)
        self.assertEqual(ECHT, self.pfad.read_bytes())
        self.assertEqual([], list((self.dump / "sce_sys").glob("*.bp_neu")))

    def test_pkg_backport_setzt_die_param_json_herab(self) -> None:
        zeilen: list[str] = []
        (self.dump / "eboot.bin").write_bytes(b"kein programm")
        pkg.backport_einbauen(str(self.dump), 7, "", zeile=zeilen.append)
        self.assertTrue(any("param.json" in z for z in zeilen), zeilen)
        self.assertEqual("0x0700000000000000", _gelesen(self.pfad.read_bytes())["sdkVersion"])


class QuelltextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

    def test_fenster_und_einbau_rufen_es_auf(self) -> None:
        self.assertEqual(2, self.haupt.count("self._backport_param_json(ordner, firmware)"))

    def test_im_fenster_nach_den_dateien_und_vor_den_bibliotheken(self) -> None:
        a = self.haupt.index("# ---- 2b) param.json")
        self.assertLess(self.haupt.index("kandidaten(ordner)", self.haupt.index("def _backport_worker")), a)
        self.assertLess(a, self.haupt.index("# ---- 3) Ersatzbibliotheken danebenlegen ----"))


if __name__ == "__main__":
    unittest.main()
