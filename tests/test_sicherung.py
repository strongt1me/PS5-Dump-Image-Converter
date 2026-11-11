# -*- coding: utf-8 -*-
"""Gesamtpruefung 11.11.2026 (D1/D10): Eine ``.orig``-Sicherung gibt es ganz oder gar nicht.

Vorher: ``shutil.copy2(original, original + ".orig")``, und der naechste Lauf pruefte nur, ob es die ``.orig`` gibt.
Brach die Kopie mitten im Schreiben ab (Platte voll, Stromausfall), stand eine abgeschnittene ``.orig`` da, der
naechste Lauf ueberspringt die Sicherung und ersetzt das Original - es waere nur noch als Bruchstueck vorhanden.
"""
from __future__ import annotations

import os
import shutil
import stat
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "tests"))

from ps5_validator.utils import dlc_emu                    # noqa: E402
from ps5_validator.utils import fake_signieren as fs       # noqa: E402
from ps5_validator.utils import sicherung                  # noqa: E402
from test_backport import baue_elf                          # noqa: E402


def _halb_kopieren(quelle, ziel, *, follow_symlinks=True):
    """Ersatz fuer ``shutil.copyfile``: schreibt die Haelfte und bricht dann ab (Platte voll)."""
    daten = Path(quelle).read_bytes()
    Path(ziel).write_bytes(daten[: len(daten) // 2])
    raise OSError(28, "Auf dem Geraet ist kein Speicherplatz mehr verfuegbar")


def _abgeschnitten_kopieren(quelle, ziel, *, follow_symlinks=True):
    """Ersatz fuer ``shutil.copyfile``: schreibt nur die Haelfte, meldet aber Erfolg (still verlorene Bytes)."""
    daten = Path(quelle).read_bytes()
    Path(ziel).write_bytes(daten[: len(daten) // 2])
    return ziel


class _Ordner(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        self.quelle = self.w / "datei.bin"
        self.quelle.write_bytes(bytes(range(256)) * 400)
        self.ziel = self.w / "datei.bin.orig"

    def _reste(self) -> list[str]:
        return sorted(n for n in os.listdir(self.w) if n.endswith(sicherung.TEIL))


class SicherungAnlegenTests(_Ordner):
    def test_vollstaendige_kopie_mit_zeitstempel(self) -> None:
        os.utime(self.quelle, (1_700_000_000, 1_700_000_000))
        sicherung.sicherung_anlegen(self.quelle, self.ziel)
        self.assertEqual(self.quelle.read_bytes(), self.ziel.read_bytes())
        self.assertEqual(int(self.quelle.stat().st_mtime), int(self.ziel.stat().st_mtime))
        self.assertEqual([], self._reste())

    def test_abbruch_beim_schreiben_hinterlaesst_weder_orig_noch_rest(self) -> None:
        with mock.patch.object(shutil, "copyfile", _halb_kopieren):
            with self.assertRaises(OSError):
                sicherung.sicherung_anlegen(self.quelle, self.ziel)
        self.assertFalse(self.ziel.exists(), "eine halbe .orig darf nie als Sicherung dastehen")
        self.assertEqual([], self._reste())
        self.assertEqual(bytes(range(256)) * 400, self.quelle.read_bytes(), "das Original bleibt")

    def test_stillschweigend_abgeschnittene_kopie_wird_nicht_uebernommen(self) -> None:
        with mock.patch.object(shutil, "copyfile", _abgeschnitten_kopieren):
            with self.assertRaises(OSError) as ctx:
                sicherung.sicherung_anlegen(self.quelle, self.ziel)
        self.assertIn("unvollstaendig", str(ctx.exception))
        self.assertFalse(self.ziel.exists())
        self.assertEqual([], self._reste())

    def test_rest_eines_frueheren_abbruchs_stoert_nicht(self) -> None:
        rest = Path(str(self.ziel) + sicherung.TEIL)
        rest.write_bytes(b"halb")
        os.chmod(rest, stat.S_IREAD)                      # schreibgeschuetzt, wie eine mitkopierte Datei
        sicherung.sicherung_anlegen(self.quelle, self.ziel)
        self.assertEqual(self.quelle.read_bytes(), self.ziel.read_bytes())
        self.assertEqual([], self._reste())

    def test_schreibgeschuetzte_quelle_laesst_sich_sichern(self) -> None:
        os.chmod(self.quelle, stat.S_IREAD)
        self.addCleanup(os.chmod, self.quelle, stat.S_IWRITE | stat.S_IREAD)
        sicherung.sicherung_anlegen(self.quelle, self.ziel)
        self.assertEqual(self.quelle.read_bytes(), self.ziel.read_bytes())
        os.chmod(self.ziel, stat.S_IWRITE | stat.S_IREAD)
        self.assertEqual([], self._reste())

    def test_fehlende_quelle_ist_ein_oserror_ohne_reste(self) -> None:
        with self.assertRaises(OSError):
            sicherung.sicherung_anlegen(self.w / "gibt_es_nicht.bin", self.ziel)
        self.assertFalse(self.ziel.exists())
        self.assertEqual([], self._reste())


class FakeSignierenTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        daten = bytearray(baue_elf())
        struct.pack_into("<H", daten, 0x10, fs.ET_SCE_EXEC_ASLR)
        self.original = bytes(daten)
        (self.w / "eboot.bin").write_bytes(self.original)

    def test_scheitert_die_sicherung_bleibt_das_original_unberuehrt(self) -> None:
        with mock.patch.object(shutil, "copyfile", _halb_kopieren):
            erg = fs.signieren(str(self.w), ["eboot.bin"], sicherung=True)
        self.assertEqual([], erg.signiert)
        self.assertEqual("eboot.bin", erg.fehler[0][0])
        self.assertEqual(self.original, (self.w / "eboot.bin").read_bytes())
        self.assertFalse((self.w / "eboot.bin.orig").exists())
        self.assertEqual([], [n for n in os.listdir(self.w) if n.endswith((sicherung.TEIL, fs._ZWISCHEN))])

    def test_nach_dem_fehlschlag_klappt_der_naechste_lauf_mit_voller_sicherung(self) -> None:
        with mock.patch.object(shutil, "copyfile", _halb_kopieren):
            fs.signieren(str(self.w), ["eboot.bin"], sicherung=True)
        erg = fs.signieren(str(self.w), ["eboot.bin"], sicherung=True)
        self.assertEqual(["eboot.bin"], erg.gesichert)
        self.assertEqual(self.original, (self.w / "eboot.bin.orig").read_bytes())

    def test_signierte_datei_wird_vor_dem_ersetzen_geschrieben(self) -> None:
        """D10: ``fsync`` vor ``os.replace`` - sonst kann nach einem Stromausfall eine leere eboot.bin dastehen."""
        aufrufe: list[str] = []
        echt_fsync, echt_replace = os.fsync, os.replace

        def fsync(fd):
            aufrufe.append("fsync")
            return echt_fsync(fd)

        def replace(a, b):
            aufrufe.append("replace")
            return echt_replace(a, b)

        with mock.patch.object(fs.os, "fsync", fsync), mock.patch.object(fs.os, "replace", replace):
            erg = fs.signieren(str(self.w), ["eboot.bin"])
        self.assertEqual(["eboot.bin"], erg.signiert)
        self.assertIn("fsync", aufrufe)
        self.assertLess(aufrufe.index("fsync"), aufrufe.index("replace"))


class DlcEmuTests(unittest.TestCase):
    def test_scheitert_die_sicherung_gibt_es_keine_halbe_orig_und_das_original_bleibt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fakelib = Path(tmp) / "fakelib"
            fakelib.mkdir()
            (fakelib / "libSceAppContent.sprx").write_bytes(b"ORIGINAL" * 1000)
            quelle = dlc_emu.bibliotheksordner(PROJEKT / "PlayGo & AMPR_EMU" / dlc_emu.ORDNER)
            with mock.patch.object(shutil, "copyfile", _halb_kopieren):
                with self.assertRaises(OSError):
                    dlc_emu.bibliotheken_einbauen(quelle, fakelib, lambda _n: None)
            self.assertEqual(b"ORIGINAL" * 1000, (fakelib / "libSceAppContent.sprx").read_bytes())
            self.assertFalse((fakelib / "libSceAppContent.sprx.orig").exists())
            self.assertEqual([], [n for n in os.listdir(fakelib) if n.endswith(sicherung.TEIL)])


if __name__ == "__main__":
    unittest.main()
