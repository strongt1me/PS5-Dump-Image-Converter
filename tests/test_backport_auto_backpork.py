# -*- coding: utf-8 -*-
"""Abgleich mit Auto-Backpork (Nazky, 0.0.1): libc-Regel und Dateiauswahl (22.10.2026).

* libc.prx wird nur bis Ziel-Firmware 6 gepatcht; bei 7 und hoeher nimmt Auto-Backpork den Patch zurueck.
* Auto-Backpork bearbeitet jede Datei mit ELF- oder SELF-Kennung, nicht nur eboot.bin und ``*.prx``/``*.sprx``.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import ps5_backport as bp          # noqa: E402
from test_backport import LOAD_OFFSET, baue_elf             # noqa: E402


def _quelle_mit_alt() -> bytes:
    elf = bytearray(baue_elf(0x10000040, 0x12090001))
    elf[LOAD_OFFSET + 0x150:LOAD_OFFSET + 0x150 + len(bp.LIBC_ALT)] = bp.LIBC_ALT
    return bp.elf_signieren(bytes(elf))


def _quelle_mit_neu() -> bytes:
    elf = bytearray(baue_elf(0x10000040, 0x12090001))
    elf[LOAD_OFFSET + 0x150:LOAD_OFFSET + 0x150 + len(bp.LIBC_NEU)] = bp.LIBC_NEU
    return bp.elf_signieren(bytes(elf))


class LibcRegelTests(unittest.TestCase):
    def test_regel_je_ziel(self) -> None:
        for fw in (1, 4, 6):
            self.assertEqual(bp.LIBC_PATCHEN, bp.libc_regel(bp.sdk_paar(fw)[0]), fw)
        for fw in (7, 8, 10):
            self.assertEqual(bp.LIBC_ZURUECK, bp.libc_regel(bp.sdk_paar(fw)[0]), fw)

    def test_zuruecksetzen_ist_die_umkehrung(self) -> None:
        daten = b"xx" + bp.LIBC_ALT + b"yy"
        gepatcht, stelle = bp.libc_patchen(daten)
        self.assertEqual(2, stelle)
        zurueck, stelle2 = bp.libc_zuruecksetzen(gepatcht)
        self.assertEqual(2, stelle2)
        self.assertEqual(daten, zurueck)

    def test_zuruecksetzen_ohne_patch_aendert_nichts(self) -> None:
        daten = b"nichts" + bp.LIBC_ALT
        self.assertEqual((daten, -1), bp.libc_zuruecksetzen(daten))

    def _verarbeiten(self, quelle: bytes, firmware: int) -> tuple[str, bytes, str]:
        ps5, ps4 = bp.sdk_paar(firmware)
        return bp.datei_verarbeiten(quelle, ziel_ps5=ps5, ziel_ps4=ps4, libc_zusatz=True, ist_libc_datei=True)

    def test_ziel_6_patcht(self) -> None:
        kennung, neu, grund = self._verarbeiten(_quelle_mit_alt(), 6)
        self.assertEqual(bp.ERG_GEPATCHT, kennung)
        self.assertIn(bp.LIBC_NEU, bp.self_zu_elf(neu))
        self.assertIn("libc", grund)

    def test_ziel_7_laesst_unverbrauchtes_in_ruhe(self) -> None:
        kennung, neu, grund = self._verarbeiten(_quelle_mit_alt(), 7)
        self.assertEqual(bp.ERG_GEPATCHT, kennung)
        elf = bp.self_zu_elf(neu)
        self.assertIn(bp.LIBC_ALT, elf)
        self.assertNotIn(bp.LIBC_NEU, elf)
        self.assertNotIn("libc", grund)

    def test_ziel_7_nimmt_einen_frueheren_patch_zurueck(self) -> None:
        kennung, neu, grund = self._verarbeiten(_quelle_mit_neu(), 7)
        self.assertEqual(bp.ERG_GEPATCHT, kennung)
        elf = bp.self_zu_elf(neu)
        self.assertIn(bp.LIBC_ALT, elf)
        self.assertNotIn(bp.LIBC_NEU, elf)
        self.assertIn("libc", grund)


class DateiauswahlTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = Path(tmp.name)

    def _datei(self, relativ: str, inhalt: bytes) -> str:
        pfad = self.wurzel / relativ
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(inhalt)
        return str(pfad)

    def _relativ(self) -> set[str]:
        return {os.path.relpath(p, self.wurzel).replace("\\", "/") for p in bp.kandidaten(str(self.wurzel))}

    def test_programmdateien_mit_anderem_namen_zaehlen(self) -> None:
        self._datei("helper.elf", b"\x7fELF" + b"\0" * 60)
        self._datei("tool.self", b"\x54\x14\xf5\xee" + b"\0" * 60)
        self._datei("ps4.bin", b"\x4f\x15\x3d\x1d" + b"\0" * 60)
        self._datei("ohne_endung", b"\x7fELF" + b"\0" * 60)
        self.assertEqual({"helper.elf", "tool.self", "ps4.bin", "ohne_endung"}, self._relativ())

    def test_daten_und_sicherungen_zaehlen_nicht(self) -> None:
        self._datei("daten.bin", b"\x00\x01\x02\x03" * 16)
        self._datei("text.txt", b"hallo")
        self._datei("leer.dat", b"")
        self._datei("alt.bak", b"\x7fELF" + b"\0" * 60)
        self.assertEqual(set(), self._relativ())

    def test_namen_gelten_weiter(self) -> None:
        self._datei("eboot.bin", b"irgendwas")
        self._datei("sce_module/libc.prx", b"irgendwas")
        self._datei("sce_module/x.sprx", b"irgendwas")
        self.assertEqual({"eboot.bin", "sce_module/libc.prx", "sce_module/x.sprx"}, self._relativ())

    def test_fakelib_ordner_bleiben_aussen_vor(self) -> None:
        self._datei("fakelib/libSceAgc.sprx", b"\x7fELF" + b"\0" * 60)
        self._datei("fakelib2/libX.sprx", b"\x7fELF" + b"\0" * 60)
        self._datei("fakelib/helfer.elf", b"\x7fELF" + b"\0" * 60)
        self.assertEqual(set(), self._relativ())


if __name__ == "__main__":
    unittest.main()
