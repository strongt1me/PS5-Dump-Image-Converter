"""Tests fuer ps5_validator.utils.pkg_reader anhand synthetischer CNT/FIH-Puffer.

Es liegt keine echte PS5-.pkg-Beispieldatei im Repo; die Tests bauen deshalb minimale,
aber layout-korrekte CNT- und FIH+CNT-Container von Hand zusammen und pruefen, dass der
Reader exakt die eingebetteten Werte zurückliefert.
"""
import json
import os
import struct
import tempfile
import unittest

from ps5_validator.utils.pkg_reader import (
    CNT_MAGIC,
    ENTRY_META_SIZE,
    FIH_MAGIC,
    HEADER_SIZE,
    PkgParseError,
    detect_pkg_type,
    read_pkg,
    try_read_param_json,
)


def _build_cnt_entry(entry_id: int, flags1: int, data_offset: int, data_size: int) -> bytes:
    return struct.pack(">IIIIII", entry_id, 0, flags1, 0, data_offset, data_size) + b"\x00" * 8


def _build_cnt_header(entry_count: int, entry_table_offset: int, content_id: str) -> bytes:
    header = bytearray(HEADER_SIZE)
    header[0:4] = CNT_MAGIC
    struct.pack_into(">I", header, 0x04, 0)  # flags
    struct.pack_into(">I", header, 0x10, entry_count)
    struct.pack_into(">H", header, 0x14, entry_count)
    struct.pack_into(">I", header, 0x18, entry_table_offset)
    struct.pack_into(">Q", header, 0x20, 0)  # body_offset
    struct.pack_into(">Q", header, 0x28, 0)  # body_size
    cid = content_id.encode("ascii")
    header[0x40:0x40 + len(cid)] = cid
    struct.pack_into(">I", header, 0x70, 1)   # drm_type
    struct.pack_into(">I", header, 0x74, 2)   # content_type
    struct.pack_into(">I", header, 0x78, 0)   # content_flags
    return bytes(header)


def _build_meta_cnt(content_id: str, param_json_bytes: bytes) -> bytes:
    entry_table_offset = HEADER_SIZE
    param_offset = entry_table_offset + 2 * ENTRY_META_SIZE
    entries = (
        _build_cnt_entry(0x2000, 0, param_offset, len(param_json_bytes))
        + _build_cnt_entry(0x0400, 0x80000000, param_offset + len(param_json_bytes), 16)
    )
    header = _build_cnt_header(entry_count=2, entry_table_offset=entry_table_offset, content_id=content_id)
    body = header + entries + param_json_bytes + (b"\xAB" * 16)
    return body


class PkgReaderTests(unittest.TestCase):
    def test_detect_type_meta(self) -> None:
        data = _build_meta_cnt("UP0000-TEST00000_00-0000000000000000", b'{"a":1}')
        with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            self.assertEqual(detect_pkg_type(path), "meta")
        finally:
            os.remove(path)

    def test_read_meta_header_and_entries(self) -> None:
        content_id = "UP0000-TEST00000_00-0000000000000000"
        param = json.dumps({"titleId": "TEST00000"}).encode("utf-8")
        data = _build_meta_cnt(content_id, param)
        with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            info = read_pkg(path)
            self.assertEqual(info.type, "meta")
            self.assertIsNotNone(info.header)
            self.assertEqual(info.header.content_id, content_id)
            self.assertEqual(info.header.entry_count, 2)
            self.assertEqual(len(info.entries), 2)

            param_entry = info.find_entry(0x2000)
            self.assertIsNotNone(param_entry)
            self.assertFalse(param_entry.encrypted)
            self.assertEqual(param_entry.name, "param.json")

            license_entry = info.find_entry(0x0400)
            self.assertIsNotNone(license_entry)
            self.assertTrue(license_entry.encrypted)

            decoded = try_read_param_json(path, info)
            self.assertEqual(decoded, {"titleId": "TEST00000"})
        finally:
            os.remove(path)

    def test_read_finalized_debug_image(self) -> None:
        cnt = _build_meta_cnt("UP0000-TEST00000_00-0000000000000000", b'{"x":true}')
        fih_cnt_offset = 0x10000
        fih = bytearray(fih_cnt_offset)
        fih[0:4] = FIH_MAGIC
        fih[0x05] = 0x00  # debug
        struct.pack_into("<H", fih, 0x06, 3)          # format version
        struct.pack_into("<Q", fih, 0x10, fih_cnt_offset)  # pfs offset (unused by reader beyond field)
        struct.pack_into("<Q", fih, 0x18, 0)           # pfs size
        struct.pack_into("<Q", fih, 0x58, fih_cnt_offset)  # embedded cnt offset
        data = bytes(fih) + cnt
        with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as f:
            f.write(data)
            path = f.name
        try:
            self.assertEqual(detect_pkg_type(path), "full_debug")
            info = read_pkg(path)
            self.assertEqual(info.type, "full_debug")
            self.assertTrue(info.fih.is_debug)
            self.assertFalse(info.fih.is_retail)
            self.assertEqual(info.fih.format_version, 3)
            self.assertEqual(info.fih.embedded_cnt_offset, fih_cnt_offset)
            self.assertIsNotNone(info.header)
            self.assertEqual(len(info.entries), 2)
        finally:
            os.remove(path)

    def test_unknown_file_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as f:
            f.write(b"NOT-A-PKG-FILE-AT-ALL")
            path = f.name
        try:
            self.assertIsNone(detect_pkg_type(path))
            with self.assertRaises(PkgParseError):
                read_pkg(path)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
