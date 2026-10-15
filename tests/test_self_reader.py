"""Tests fuer ps5_validator.utils.self_reader (synthetische SELF-Container)."""
from __future__ import annotations

import os
import struct
import tempfile
import unittest

from ps5_validator.utils import self_reader


def _build_synthetic_self(num_segments: int = 2, phnum: int = 0, magic: int | None = None) -> bytes:
    """Baut einen minimalen, aber strukturell gueltigen synthetischen SELF-Container."""
    header_size = 0x20
    seg_table_size = num_segments * 0x20
    elf_start = header_size + seg_table_size

    # Minimaler ELF-Header (0x40 Bytes), phnum Programmheader direkt danach.
    elf = bytearray(0x40)
    elf[0:4] = b"\x7fELF"
    elf[4] = 2   # 64-bit
    elf[5] = 1   # little-endian
    elf[6] = 1   # ELF-Version
    elf[7] = 9   # FreeBSD ABI
    struct.pack_into("<H", elf, 0x10, 0x0002)       # e_type = ET_EXEC
    struct.pack_into("<H", elf, 0x12, 0x003E)       # e_machine = x86-64
    struct.pack_into("<I", elf, 0x14, 1)            # e_version
    struct.pack_into("<Q", elf, 0x18, 0x400000)     # e_entry
    struct.pack_into("<Q", elf, 0x20, 0x40)          # e_phoff
    struct.pack_into("<H", elf, 0x38, phnum)        # e_phnum
    elf += bytes(phnum * 0x38)

    elf_region_len = max(0x40 + phnum * 0x38, 0x40)
    ext_start = (elf_start + elf_region_len + 0xF) // 0x10 * 0x10
    pad = ext_start - (elf_start + len(elf))

    ext_info = bytearray(0x40)
    struct.pack_into("<Q", ext_info, 0x00, 0x3100000000000001)  # Authority-ID (fake exec)
    struct.pack_into("<Q", ext_info, 0x08, 1)                    # program_type
    struct.pack_into("<Q", ext_info, 0x10, 0x0100)               # app_version
    struct.pack_into("<Q", ext_info, 0x18, 0x0200)               # firmware_version
    ext_info[0x20:0x40] = bytes(range(32))                       # Digest (Platzhalter)

    body = bytearray()
    body += b"\x00" * pad
    body += ext_info

    total_size = elf_start + len(elf) + len(body)

    header = bytearray(header_size)
    struct.pack_into("<I", header, 0x00, self_reader.SELF_MAGIC if magic is None else magic)
    header[0x04] = 0x00  # version
    header[0x05] = 0x01  # mode
    header[0x06] = 0x01  # endian
    header[0x07] = 0x12  # attributes
    struct.pack_into("<I", header, 0x08, 0x0101)  # key_type
    struct.pack_into("<H", header, 0x0C, header_size)
    struct.pack_into("<H", header, 0x0E, 0x0110)
    struct.pack_into("<Q", header, 0x10, total_size)
    struct.pack_into("<H", header, 0x18, num_segments)
    struct.pack_into("<H", header, 0x1A, 0x0022)

    seg_table = bytearray()
    for i in range(num_segments):
        flags = SEGMENT_FLAGS[i] if i < len(SEGMENT_FLAGS) else (0x4 | (i << 20))
        seg_table += struct.pack("<QQQQ", flags, 0x1000 * i, 0x100, 0x100)

    return bytes(header) + bytes(seg_table) + bytes(elf) + bytes(body)


SEGMENT_FLAGS = [0x10004, 0x2804 | (1 << 20)]  # Digest-Segment, Data-Segment (Beispielwerte)


class SelfReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="self_reader_test_")

    def tearDown(self) -> None:
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def _write(self, data: bytes, name: str = "test.self") -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_detect_self_true(self) -> None:
        path = self._write(_build_synthetic_self())
        self.assertTrue(self_reader.detect_self(path))

    def test_detect_self_false_for_unrelated_file(self) -> None:
        path = self._write(b"NOT A SELF FILE" + b"\x00" * 32, name="other.bin")
        self.assertFalse(self_reader.detect_self(path))

    def test_read_header_fields(self) -> None:
        path = self._write(_build_synthetic_self(num_segments=2))
        info = self_reader.read_self(path)
        self.assertEqual(info.header.segment_count, 2)
        self.assertEqual(info.header.header_size, 0x20)
        self.assertEqual(len(info.segments), 2)

    def test_segment_flag_properties(self) -> None:
        path = self._write(_build_synthetic_self(num_segments=2))
        info = self_reader.read_self(path)
        digest_seg, data_seg = info.segments
        self.assertTrue(digest_seg.signed)
        self.assertFalse(digest_seg.encrypted)
        self.assertTrue(data_seg.signed)
        self.assertTrue(data_seg.blocked)
        self.assertEqual(data_seg.segment_id, 1)

    def test_elf_header_parsed(self) -> None:
        path = self._write(_build_synthetic_self())
        info = self_reader.read_self(path)
        self.assertIsNotNone(info.elf_header)
        assert info.elf_header is not None
        self.assertTrue(info.elf_header.is_64bit)
        self.assertEqual(info.elf_header.e_machine, 0x003E)
        self.assertEqual(info.elf_header.type_name, "ET_EXEC (ausführbar)")

    def test_ext_info_authority_category(self) -> None:
        path = self._write(_build_synthetic_self())
        info = self_reader.read_self(path)
        self.assertIsNotNone(info.ext_info)
        assert info.ext_info is not None
        self.assertEqual(info.ext_info.authority_category, self_reader.AUTHORITY_CATEGORY_FAKE)
        self.assertEqual(info.ext_info.authority_category_name, "Fake/Debug")
        self.assertEqual(len(info.ext_info.digest), 32)

    def test_unknown_file_raises(self) -> None:
        path = self._write(b"\x00" * 64, name="unknown.bin")
        with self.assertRaises(self_reader.SelfParseError):
            self_reader.read_self(path)


class ZweiteMagicTests(unittest.TestCase):
    """Reale PS5-Dumps tragen zwei gleichwertige SELF-Magics.

    An sechs echten eboot.bin nachgemessen: drei mit 0x1D3D154F, zwei mit
    0xEEF51454, bei identischem Kopflayout. Wer nur die erste kennt, weist
    einen erheblichen Teil regulaerer Backups als 'unbekannte Magic' ab.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="self_reader_alt_")

    def tearDown(self) -> None:
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def _write(self, data: bytes, name: str = "alt.self") -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_beide_magics_gelten_als_self(self) -> None:
        for magic in (self_reader.SELF_MAGIC, self_reader.SELF_MAGIC_ALT):
            path = self._write(_build_synthetic_self(magic=magic))
            self.assertTrue(self_reader.detect_self(path), f"Magic 0x{magic:08X}")

    def test_zweite_magic_liefert_dieselben_felder(self) -> None:
        erste = self_reader.read_self(self._write(
            _build_synthetic_self(num_segments=2), name="a.self"))
        zweite = self_reader.read_self(self._write(
            _build_synthetic_self(num_segments=2, magic=self_reader.SELF_MAGIC_ALT), name="b.self"))
        self.assertEqual(erste.header.segment_count, zweite.header.segment_count)
        self.assertEqual(len(erste.segments), len(zweite.segments))
        self.assertEqual(erste.elf_header.e_machine, zweite.elf_header.e_machine)
        self.assertEqual(erste.ext_info.authority_id, zweite.ext_info.authority_id)

    def test_magic_wird_benannt(self) -> None:
        info = self_reader.read_self(self._write(
            _build_synthetic_self(magic=self_reader.SELF_MAGIC_ALT)))
        self.assertEqual(info.magic, self_reader.SELF_MAGIC_ALT)
        self.assertIn("EEF51454", info.magic_name)
        self.assertTrue(info.is_self)

    def test_fremde_magic_bleibt_ein_fehler(self) -> None:
        path = self._write(_build_synthetic_self(magic=0xDEADBEEF), name="fremd.self")
        with self.assertRaises(self_reader.SelfParseError):
            self_reader.read_self(path)


class ReinesElfTests(unittest.TestCase):
    """Manche Dumps legen eboot.bin unsigniert als reines ELF ab (z. B. The Precinct)."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="self_reader_elf_")

    def tearDown(self) -> None:
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def _elf_datei(self, extra: bytes = b"") -> str:
        elf = bytearray(0x40)
        elf[0:4] = b"\x7fELF"
        elf[4] = 2
        elf[5] = 1
        elf[6] = 1
        elf[7] = 9
        struct.pack_into("<H", elf, 0x10, 0xFE10)      # ET_SCE_DYNEXEC
        struct.pack_into("<H", elf, 0x12, 0x003E)
        struct.pack_into("<Q", elf, 0x18, 0x80)
        struct.pack_into("<H", elf, 0x38, 14)
        path = os.path.join(self.tmpdir, "eboot.bin")
        with open(path, "wb") as f:
            f.write(bytes(elf) + extra)
        return path

    def test_reines_elf_wird_gelesen_statt_abgewiesen(self) -> None:
        info = self_reader.read_self(self._elf_datei())
        self.assertEqual(info.container, self_reader.CONTAINER_ELF)
        self.assertFalse(info.is_self)
        self.assertEqual(info.magic_name, "ELF")

    def test_elf_hat_keinen_container_kopf(self) -> None:
        info = self_reader.read_self(self._elf_datei())
        self.assertIsNone(info.header)
        self.assertIsNone(info.ext_info)
        self.assertEqual(info.segments, [])

    def test_elf_kopf_wird_ausgewertet(self) -> None:
        info = self_reader.read_self(self._elf_datei())
        self.assertIsNotNone(info.elf_header)
        assert info.elf_header is not None
        self.assertEqual(info.elf_header.type_name, "ET_SCE_DYNEXEC")
        self.assertEqual(info.elf_header.e_phnum, 14)
        self.assertTrue(info.elf_header.is_64bit)

    def test_detect_elf_unterscheidet_sauber(self) -> None:
        elf = self._elf_datei()
        self.assertTrue(self_reader.detect_elf(elf))
        self.assertFalse(self_reader.detect_self(elf))


class LesebudgetTests(unittest.TestCase):
    """Ein eboot.bin kann dreistellige MB gross sein - der Kopf reicht zur Anzeige."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="self_reader_budget_")

    def tearDown(self) -> None:
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def test_grosse_datei_wird_nicht_komplett_eingelesen(self) -> None:
        anhang = b"\x5A" * (4 * 1024 * 1024)
        path = os.path.join(self.tmpdir, "gross.self")
        with open(path, "wb") as f:
            f.write(_build_synthetic_self(num_segments=2) + anhang)

        gelesen = []
        echtes_open = open

        class Mitzaehler:
            def __init__(self, fh):
                self._fh = fh

            def read(self, n=-1):
                daten = self._fh.read(n)
                gelesen.append(len(daten))
                return daten

            def __getattr__(self, name):
                return getattr(self._fh, name)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return self._fh.__exit__(*a)

        import builtins
        builtins.open = lambda *a, **k: Mitzaehler(echtes_open(*a, **k))
        try:
            info = self_reader.read_self(path)
        finally:
            builtins.open = echtes_open

        self.assertEqual(info.header.segment_count, 2)
        self.assertLessEqual(sum(gelesen), self_reader.MAX_HEADER_READ + self_reader.EXT_INFO_SIZE)
        self.assertLess(sum(gelesen), os.path.getsize(path))


if __name__ == "__main__":
    unittest.main()
