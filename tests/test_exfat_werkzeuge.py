# -*- coding: utf-8 -*-
"""Tests fuer ps5_validator/utils/exfat_werkzeuge.py (seit v1.9.83)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.exfat_werkzeuge import (
    MARKER_PRIMAER_OK,
    MARKER_REPARIERT,
    exfat_boot_sektor_reparieren,
    exfat_vbr_gueltig,
    mkpfs_eltern_suchen,
)

_SEKTOR = 512
_VBR = 12 * _SEKTOR


def _gueltig_vbr() -> bytes:
    vbr = bytearray(_VBR)
    vbr[3:11] = b"EXFAT   "
    vbr[510:512] = b"\x55\xAA"
    return bytes(vbr)


def _kaputt_vbr() -> bytes:
    return bytes(_VBR)


class VbrGueltigTests(unittest.TestCase):
    def test_gueltig(self) -> None:
        self.assertTrue(exfat_vbr_gueltig(_gueltig_vbr()))

    def test_falscher_oem_name(self) -> None:
        vbr = bytearray(_gueltig_vbr())
        vbr[3:11] = b"NTFS    "
        self.assertFalse(exfat_vbr_gueltig(bytes(vbr)))

    def test_falsche_signatur(self) -> None:
        vbr = bytearray(_gueltig_vbr())
        vbr[510:512] = b"\x00\x00"
        self.assertFalse(exfat_vbr_gueltig(bytes(vbr)))

    def test_zu_kurz(self) -> None:
        self.assertFalse(exfat_vbr_gueltig(b"\x00" * 100))

    def test_leere_bytes(self) -> None:
        self.assertFalse(exfat_vbr_gueltig(b""))


class BootSektorReparierenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _datei(self, inhalt: bytes) -> str:
        pfad = os.path.join(self._tmp.name, "test.exfat")
        with open(pfad, "wb") as fh:
            fh.write(inhalt)
        return pfad

    def test_bereits_gueltig(self) -> None:
        pfad = self._datei(_gueltig_vbr() + _gueltig_vbr())
        ok, marker = exfat_boot_sektor_reparieren(pfad)
        self.assertTrue(ok)
        self.assertEqual(MARKER_PRIMAER_OK, marker)

    def test_repariert_aus_backup(self) -> None:
        pfad = self._datei(_kaputt_vbr() + _gueltig_vbr())
        ok, marker = exfat_boot_sektor_reparieren(pfad)
        self.assertTrue(ok)
        self.assertEqual(MARKER_REPARIERT, marker)
        with open(pfad, "rb") as fh:
            primaer = fh.read(_VBR)
        self.assertTrue(exfat_vbr_gueltig(primaer))

    def test_beide_vbr_kaputt(self) -> None:
        pfad = self._datei(_kaputt_vbr() + _kaputt_vbr())
        ok, _ = exfat_boot_sektor_reparieren(pfad)
        self.assertFalse(ok)

    def test_primaer_vbr_zu_kurz(self) -> None:
        pfad = self._datei(b"\x00" * 100)
        ok, _ = exfat_boot_sektor_reparieren(pfad)
        self.assertFalse(ok)

    def test_kein_backup_vbr(self) -> None:
        pfad = self._datei(_kaputt_vbr())
        ok, _ = exfat_boot_sektor_reparieren(pfad)
        self.assertFalse(ok)

    def test_datei_existiert_nicht(self) -> None:
        pfad = os.path.join(self._tmp.name, "gibt_nicht.exfat")
        ok, msg = exfat_boot_sektor_reparieren(pfad)
        self.assertFalse(ok)
        self.assertIsInstance(msg, str)
        self.assertTrue(len(msg) > 0)


class MkpfsElternSuchenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _anlegen(self, name: str = "MkPFS-1.1.0") -> str:
        ordner = os.path.join(self._tmp.name, name, "mkpfs")
        os.makedirs(ordner, exist_ok=True)
        return self._tmp.name

    def test_findet_elternordner(self) -> None:
        eltern = self._anlegen()
        self.assertEqual(eltern, mkpfs_eltern_suchen([eltern]))

    def test_gibt_leeren_string_ohne_treffer(self) -> None:
        self.assertEqual("", mkpfs_eltern_suchen([self._tmp.name]))

    def test_leere_wurzeln(self) -> None:
        self.assertEqual("", mkpfs_eltern_suchen([]))

    def test_keine_wurzeln(self) -> None:
        self.assertEqual("", mkpfs_eltern_suchen(None))


if __name__ == "__main__":
    unittest.main()
