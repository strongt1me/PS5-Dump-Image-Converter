# -*- coding: utf-8 -*-
"""Der UFS2-Leser fuer ``.ffpkg`` (29.10.2026): Dateien aus dem Abbild lesen, ohne Mount und ohne Administratorrechte.

Zwei Wege: ein selbst gebautes Mini-Abbild (Aufbau von Hand nach ``fs.h``/``dinode.h``, damit der Leser an einer bekannten
Antwort gemessen wird) und - wenn auf dem Rechner vorhanden - echte ``.ffpkg`` des Entwicklers.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ufs2_leser as u             # noqa: E402

BS = 4096
SB = u.SUPERBLOCK_LAGE


def _dirent(ino: int, name: str, typ: int, reclen: int) -> bytes:
    roh = struct.pack("<IHBB", ino, reclen, typ, len(name)) + name.encode()
    return roh.ljust(reclen, b"\0")


def _verzeichnis(eintraege: list[tuple[int, str, int]]) -> bytes:
    """Ein Verzeichnisblock aus einem 512-Byte-Abschnitt; der letzte Eintrag fuellt den Rest."""
    teile = []
    for ino, name, typ in eintraege:
        laenge = (8 + len(name) + 3) & ~3
        teile.append((ino, name, typ, laenge))
    letzter = teile[-1]
    teile[-1] = (letzter[0], letzter[1], letzter[2], 512 - sum(t[3] for t in teile[:-1]))
    return b"".join(_dirent(*t) for t in teile).ljust(BS, b"\0")


def _inode(modus: int, groesse: int, direkt: list[int], indirekt: list[int] = ()) -> bytes:
    roh = bytearray(256)
    struct.pack_into("<H", roh, 0, modus)
    struct.pack_into("<Q", roh, 16, groesse)
    for i, zeiger in enumerate(direkt):
        struct.pack_into("<Q", roh, 112 + 8 * i, zeiger)
    for i, zeiger in enumerate(indirekt):
        struct.pack_into("<Q", roh, 208 + 8 * i, zeiger)
    return bytes(roh)


def baue_abbild(pfad: str) -> dict[str, bytes]:
    """Schreibt ein Mini-UFS2: ``eboot.bin``, ``sce_sys/param.json`` und eine Datei mit einfach-indirektem Block."""
    param = json.dumps({"titleId": "PPSA00001", "requiredSystemSoftwareVersion": "0x0960000000000000"}).encode()
    gross = bytes((i * 7 + 3) % 251 for i in range(14 * BS - 100))       # 14 Bloecke: 12 direkt + 2 ueber den Zeigerblock
    eboot = b"ELF" * 100
    inhalte = {"sce_sys/param.json": param, "sce_sys/gross.bin": gross, "eboot.bin": eboot}

    bloecke: dict[int, bytes] = {}
    bloecke[30] = _verzeichnis([(2, ".", 4), (2, "..", 4), (3, "sce_sys", 4), (4, "eboot.bin", 8)])
    bloecke[31] = _verzeichnis([(3, ".", 4), (2, "..", 4), (5, "param.json", 8), (6, "gross.bin", 8)])
    bloecke[32] = param.ljust(BS, b"\0")
    bloecke[33] = eboot.ljust(BS, b"\0")
    gross_bloecke = [gross[i:i + BS].ljust(BS, b"\0") for i in range(0, len(gross), BS)]
    direkt = list(range(34, 46))
    for zeiger, block in zip(direkt, gross_bloecke[:12]):
        bloecke[zeiger] = block
    bloecke[46] = struct.pack("<512Q", 47, 48, *([0] * 510))
    bloecke[47], bloecke[48] = gross_bloecke[12], gross_bloecke[13]

    inodes = {2: _inode(0x41ED, BS, [30]), 3: _inode(0x41ED, BS, [31]),
              4: _inode(0x81A4, len(eboot), [33]), 5: _inode(0x81A4, len(param), [32]),
              6: _inode(0x81A4, len(gross), direkt, [46])}
    inodeblock = bytearray(2 * BS)
    for nummer, roh in inodes.items():
        inodeblock[nummer * 256:(nummer + 1) * 256] = roh

    sb = bytearray(0x600)
    struct.pack_into("<i", sb, 16, 20)             # fs_iblkno (Fragmente)
    struct.pack_into("<i", sb, 24, 0)              # fs_old_cgoffset
    struct.pack_into("<i", sb, 28, -1)             # fs_old_cgmask
    struct.pack_into("<i", sb, 48, BS)             # fs_bsize
    struct.pack_into("<i", sb, 52, BS)             # fs_fsize
    struct.pack_into("<i", sb, 56, 1)              # fs_frag
    struct.pack_into("<i", sb, 116, BS // 8)       # fs_nindir
    struct.pack_into("<I", sb, 120, BS // 256)     # fs_inopb
    struct.pack_into("<I", sb, 184, 32)            # fs_ipg
    struct.pack_into("<i", sb, 188, 64)            # fs_fpg
    struct.pack_into("<I", sb, u.MAGIC_LAGE, u.UFS2_MAGIC)

    abbild = bytearray(64 * BS)
    abbild[SB:SB + len(sb)] = sb
    abbild[20 * BS:20 * BS + len(inodeblock)] = inodeblock
    for nummer, block in bloecke.items():
        abbild[nummer * BS:nummer * BS + BS] = block
    with open(pfad, "wb") as datei:
        datei.write(abbild)
    return inhalte


class MiniAbbildTests(unittest.TestCase):
    def setUp(self) -> None:
        ordner = tempfile.TemporaryDirectory()
        self.addCleanup(ordner.cleanup)
        self.pfad = os.path.join(ordner.name, "test.ffpkg")
        self.inhalte = baue_abbild(self.pfad)

    def test_erkennt_ufs2(self) -> None:
        self.assertTrue(u.ist_ufs2(self.pfad))
        self.assertFalse(u.ist_ufs2(os.path.join(os.path.dirname(self.pfad), "gibt-es-nicht")))

    def test_liest_die_dateien_byte_genau(self) -> None:
        with u.Ufs2Leser(self.pfad) as leser:
            for pfad, soll in self.inhalte.items():
                with self.subTest(pfad=pfad):
                    self.assertEqual(soll, leser.datei_lesen(pfad))

    def test_auch_mit_fuehrendem_schraegstrich_und_rueckstrich(self) -> None:
        with u.Ufs2Leser(self.pfad) as leser:
            self.assertEqual(self.inhalte["sce_sys/param.json"], leser.datei_lesen("/sce_sys\\param.json"))

    def test_auflisten(self) -> None:
        with u.Ufs2Leser(self.pfad) as leser:
            self.assertEqual({("sce_sys", True), ("eboot.bin", False)},
                             {(n, d) for n, d, _s in leser.auflisten("")})
            sce = {n: s for n, _d, s in leser.auflisten("sce_sys")}
            self.assertEqual(len(self.inhalte["sce_sys/gross.bin"]), sce["gross.bin"])

    def test_hoechstens_begrenzt_das_lesen(self) -> None:
        with u.Ufs2Leser(self.pfad) as leser:
            kopf = leser.datei_lesen("sce_sys/gross.bin", 5000)
        self.assertEqual(self.inhalte["sce_sys/gross.bin"][:5000], kopf)

    def test_fehlende_datei_und_falsche_art(self) -> None:
        with u.Ufs2Leser(self.pfad) as leser:
            with self.assertRaises(FileNotFoundError):
                leser.datei_lesen("sce_sys/icon0.png")
            with self.assertRaises(u.Ufs2Fehler):
                leser.datei_lesen("sce_sys")                    # ein Ordner
            with self.assertRaises(u.Ufs2Fehler):
                leser.auflisten("eboot.bin")                    # eine Datei

    def test_der_leser_veraendert_die_datei_nicht(self) -> None:
        vorher = Path(self.pfad).read_bytes()
        with u.Ufs2Leser(self.pfad) as leser:
            leser.datei_lesen("sce_sys/param.json")
        self.assertEqual(vorher, Path(self.pfad).read_bytes())


class FremdeDateienTests(unittest.TestCase):
    def _datei(self, daten: bytes) -> str:
        ordner = tempfile.TemporaryDirectory()
        self.addCleanup(ordner.cleanup)
        pfad = os.path.join(ordner.name, "x.ffpkg")
        Path(pfad).write_bytes(daten)
        return pfad

    def test_zu_kurz_oder_kein_ufs2(self) -> None:
        for daten in (b"", b"\0" * 100, b"\0" * (u.SUPERBLOCK_LAGE + 0x700), os.urandom(200_000)):
            with self.subTest(laenge=len(daten)):
                pfad = self._datei(daten)
                self.assertFalse(u.ist_ufs2(pfad))
                with self.assertRaises(u.Ufs2Fehler):
                    u.Ufs2Leser(pfad)

    def test_ein_unplausibler_superblock_wird_abgelehnt(self) -> None:
        daten = bytearray(u.SUPERBLOCK_LAGE + 0x700)
        struct.pack_into("<I", daten, u.SUPERBLOCK_LAGE + u.MAGIC_LAGE, u.UFS2_MAGIC)
        with self.assertRaises(u.Ufs2Fehler):
            u.Ufs2Leser(self._datei(bytes(daten)))

    def test_ein_abgeschnittenes_abbild_gibt_einen_fehler_statt_unsinn(self) -> None:
        ordner = tempfile.TemporaryDirectory()
        self.addCleanup(ordner.cleanup)
        pfad = os.path.join(ordner.name, "kurz.ffpkg")
        baue_abbild(pfad)
        Path(pfad).write_bytes(Path(pfad).read_bytes()[:25 * BS])         # hinter den Inodes abgeschnitten
        with u.Ufs2Leser(pfad) as leser:
            with self.assertRaises((u.Ufs2Fehler, FileNotFoundError)):
                leser.datei_lesen("sce_sys/param.json")


def _echte_ffpkg() -> list[str]:
    gefunden = []
    wurzel = r"D:\PS5 TEMP"
    if os.path.isdir(wurzel):
        for ordner, _d, dateien in os.walk(wurzel):
            for name in dateien:
                if name.lower().endswith(".ffpkg") and not name.startswith("$"):
                    gefunden.append(os.path.join(ordner, name))
            if len(gefunden) >= 3:
                break
    return gefunden[:3]


@unittest.skipUnless(_echte_ffpkg(), "keine echte .ffpkg auf diesem Rechner")
class EchteAbbilderTests(unittest.TestCase):
    """Gemessen am 29.10.2026 an drei echten ``.ffpkg`` (700 MB und 1,2 GB): param.json und icon0.png ohne Mount."""

    def test_param_json_und_icon_lassen_sich_lesen(self) -> None:
        for pfad in _echte_ffpkg():
            with self.subTest(datei=os.path.basename(pfad)), u.Ufs2Leser(pfad) as leser:
                param = json.loads(leser.datei_lesen("sce_sys/param.json").decode("utf-8-sig"))
                self.assertRegex(str(param.get("titleId")), r"^[A-Z]{4}\d{5}$")
                icon = leser.datei_lesen("sce_sys/icon0.png")
                self.assertTrue(icon.startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
