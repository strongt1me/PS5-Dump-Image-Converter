# -*- coding: utf-8 -*-
"""Unsignierte PS5-ELF erkennen und fake-signieren (wie ps5-dump-forge v0.5.4)."""
from __future__ import annotations

import os
import shutil
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

from ps5_validator.utils import fake_signieren as fs   # noqa: E402
from ps5_validator.utils import ps5_backport as bp      # noqa: E402
from test_backport import baue_elf                       # noqa: E402


def _elf(e_type: int = fs.ET_SCE_EXEC_ASLR) -> bytes:
    """Ein einfaches PS5-ELF (``e_type`` gesetzt), das sich signieren laesst."""
    daten = bytearray(baue_elf())
    struct.pack_into("<H", daten, 0x10, e_type)
    return bytes(daten)


class ErkennenTests(unittest.TestCase):
    def test_namen(self) -> None:
        for name in ("eboot.bin", "EBOOT.BIN", "eboot_alt.bin", "a.elf", "libx.prx", "liby.SPRX", "m.self", "sub/x.elf"):
            with self.subTest(name=name):
                self.assertTrue(fs.ist_ausfuehrbar(name), name)
        for name in ("data.bin", "textur.dds", "a.txt", "ebootx", "elf", "x.elf.bak", "param.json"):
            with self.subTest(name=name):
                self.assertFalse(fs.ist_ausfuehrbar(name), name)

    def test_nur_die_ps5_typen_gelten_als_unsigniert(self) -> None:
        self.assertTrue(fs.ist_unsigniert(_elf(fs.ET_SCE_EXEC_ASLR)[:0x12]))
        self.assertTrue(fs.ist_unsigniert(_elf(fs.ET_SCE_DYNAMIC)[:0x12]))
        self.assertFalse(fs.ist_unsigniert(_elf(2)[:0x12]), "gewoehnliches ELF-Programm (ET_EXEC)")
        self.assertFalse(fs.ist_unsigniert(_elf(3)[:0x12]), "gewoehnliche Bibliothek (ET_DYN)")
        self.assertFalse(fs.ist_unsigniert(b"\x54\x14\xf5\xee" + bytes(0x20)), "schon ein SELF")
        self.assertFalse(fs.ist_unsigniert(b""))
        self.assertFalse(fs.ist_unsigniert(b"\x7fELF"))


class _Ordner(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.w = Path(tmp.name)
        (self.w / "sce_sys").mkdir()
        (self.w / "fakelib").mkdir()
        (self.w / "eboot.bin").write_bytes(_elf())
        (self.w / "fakelib" / "libSceAmpr.sprx").write_bytes(_elf(fs.ET_SCE_DYNAMIC))
        (self.w / "libgut.prx").write_bytes(bp.elf_signieren(_elf()))         # schon signiert
        (self.w / "alt.elf").write_bytes(_elf(2))                              # kein PS5-Typ
        (self.w / "daten.bin").write_bytes(_elf())                             # Name sagt: Datendatei
        (self.w / "sce_sys" / "param.json").write_text("{}")


class FindenTests(_Ordner):
    def test_findet_genau_die_unsignierten_programme(self) -> None:
        self.assertEqual(["eboot.bin", "fakelib/libSceAmpr.sprx"], fs.unsignierte_finden(str(self.w)))

    def test_verknuepfung_und_winzige_dateien_zaehlen_nicht(self) -> None:
        (self.w / "klein.prx").write_bytes(b"\x7fELF")
        self.assertEqual(["eboot.bin", "fakelib/libSceAmpr.sprx"], fs.unsignierte_finden(str(self.w)))
        try:
            os.symlink(self.w / "eboot.bin", self.w / "link.elf")
        except (OSError, NotImplementedError):
            self.skipTest("Verknuepfung nicht anlegbar (Rechte)")
        self.assertNotIn("link.elf", fs.unsignierte_finden(str(self.w)))

    def test_abbruch_beendet_den_durchgang(self) -> None:
        self.assertEqual([], fs.unsignierte_finden(str(self.w), abbruch=lambda: True))

    def test_obergrenze(self) -> None:
        with mock.patch.object(fs, "MAX_PROGRAMME", 1):
            self.assertEqual(1, len(fs.unsignierte_finden(str(self.w))))

    def test_leerer_oder_fehlender_ordner(self) -> None:
        self.assertEqual([], fs.unsignierte_finden(str(self.w / "gibt_es_nicht")))


class SignierenTests(_Ordner):
    def test_signiert_und_laesst_das_signierte_in_ruhe(self) -> None:
        vorher = (self.w / "libgut.prx").read_bytes()
        erg = fs.signieren(str(self.w), ["eboot.bin", "fakelib/libSceAmpr.sprx"])
        self.assertEqual(["eboot.bin", "fakelib/libSceAmpr.sprx"], erg.signiert)
        self.assertEqual([], erg.fehler)
        for rel in erg.signiert:
            daten = (self.w / rel).read_bytes()
            self.assertIn(daten[:4], fs.SELF_KENNUNGEN, rel)
            # das SELF traegt den urspruenglichen ELF-Inhalt: zurueckgewandelt ist es wieder das ELF
            self.assertEqual(bp.self_zu_elf(daten)[:0x40], _elf(fs.ET_SCE_EXEC_ASLR if rel == "eboot.bin"
                                                                  else fs.ET_SCE_DYNAMIC)[:0x40])
        self.assertEqual(vorher, (self.w / "libgut.prx").read_bytes())
        self.assertEqual([], fs.unsignierte_finden(str(self.w)), "danach ist nichts mehr unsigniert")

    def test_zweiter_durchgang_aendert_nichts(self) -> None:
        fs.signieren(str(self.w), fs.unsignierte_finden(str(self.w)))
        erg = fs.signieren(str(self.w), ["eboot.bin"])
        self.assertEqual([], erg.signiert)
        self.assertEqual([], erg.fehler)

    def test_sicherung_legt_orig_daneben(self) -> None:
        original = (self.w / "eboot.bin").read_bytes()
        erg = fs.signieren(str(self.w), ["eboot.bin"], sicherung=True)
        self.assertEqual(["eboot.bin"], erg.gesichert)
        self.assertEqual(original, (self.w / "eboot.bin.orig").read_bytes())
        # eine vorhandene .orig wird nicht ueberschrieben
        (self.w / "eboot.bin").write_bytes(_elf())
        (self.w / "eboot.bin.orig").write_bytes(b"VORHER")
        fs.signieren(str(self.w), ["eboot.bin"], sicherung=True)
        self.assertEqual(b"VORHER", (self.w / "eboot.bin.orig").read_bytes())

    def test_ohne_sicherung_keine_orig(self) -> None:
        fs.signieren(str(self.w), ["eboot.bin"])
        self.assertFalse((self.w / "eboot.bin.orig").exists())

    def test_ein_fehler_haelt_die_uebrigen_nicht_auf_und_laesst_das_original(self) -> None:
        kaputt = self.w / "kaputt.elf"
        kaputt.write_bytes(_elf()[:0x50])            # ELF-Kopf ohne Programmkopftabelle
        erg = fs.signieren(str(self.w), ["kaputt.elf", "eboot.bin"])
        self.assertEqual(["eboot.bin"], erg.signiert)
        self.assertEqual(1, len(erg.fehler))
        self.assertEqual("kaputt.elf", erg.fehler[0][0])
        self.assertEqual(_elf()[:0x50], kaputt.read_bytes(), "das Original bleibt")
        self.assertFalse((self.w / ("kaputt.elf" + fs._ZWISCHEN)).exists(), "keine Zwischendatei bleibt liegen")

    def test_pfade_ausserhalb_werden_abgelehnt(self) -> None:
        aussen = self.w.parent / "aussen.elf"
        aussen.write_bytes(_elf())
        try:
            erg = fs.signieren(str(self.w), ["../aussen.elf"])
            self.assertEqual([], erg.signiert)
            self.assertEqual(1, len(erg.fehler))
            self.assertEqual(_elf(), aussen.read_bytes())
        finally:
            aussen.unlink(missing_ok=True)

    def test_fortschritt_und_abbruch(self) -> None:
        gesehen: list[tuple] = []
        erg = fs.signieren(str(self.w), ["eboot.bin", "fakelib/libSceAmpr.sprx"],
                           fortschritt=lambda n, g, r: gesehen.append((n, g, r)))
        self.assertEqual([(1, 2, "eboot.bin"), (2, 2, "fakelib/libSceAmpr.sprx")], gesehen)
        self.assertEqual(2, len(erg.signiert))
        shutil.rmtree(self.w / "fakelib")
        (self.w / "eboot.bin").write_bytes(_elf())
        erg = fs.signieren(str(self.w), ["eboot.bin"], abbruch=lambda: True)
        self.assertEqual([], erg.signiert)

    def test_zu_grosse_datei_wird_uebersprungen(self) -> None:
        with mock.patch.object(fs, "GROESSE_MAX", 10):
            erg = fs.signieren(str(self.w), ["eboot.bin"])
        self.assertEqual([], erg.signiert)
        self.assertEqual(1, len(erg.fehler))


if __name__ == "__main__":
    unittest.main()
