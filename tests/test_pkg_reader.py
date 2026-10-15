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

    @staticmethod
    def _fih_paket(seed: bytes, *, kopf: "int | None" = None, kennung: bool = True,
                   im_kopfbereich: bytes = b"") -> bytes:
        """Ein FIH-Paket mit kleinem PFS-Abbild: PFS-Kopf mit Kennung und Seed.

        Aufbau wie am 24.09.2026 an einem LibProsperoPkg-Paket gemessen: PFS
        ab 0x10000, FIH+0x20 = absolute Lage eines PFS-Kopfs, darin die
        Kennung 0x01332A0B bei +0x08 und der Seed bei +0x370.
        """
        from ps5_validator.utils.pkg_reader import PFS_MAGIC

        pfs_anfang, pfs_groesse = 0x10000, 0x1000
        cnt = _build_meta_cnt("UP0000-TEST00000_00-0000000000000000", b'{"x":true}')
        vorspann = bytearray(pfs_anfang)
        vorspann[0:4] = FIH_MAGIC
        vorspann[0x05] = 0x00
        struct.pack_into("<H", vorspann, 0x06, 3)
        struct.pack_into("<Q", vorspann, 0x10, pfs_anfang)
        struct.pack_into("<Q", vorspann, 0x18, pfs_groesse)
        struct.pack_into("<Q", vorspann, 0x20, pfs_anfang if kopf is None else kopf)
        struct.pack_into("<Q", vorspann, 0x58, pfs_anfang + pfs_groesse)
        if im_kopfbereich:
            vorspann[0x400:0x400 + len(im_kopfbereich)] = im_kopfbereich
        pfs = bytearray(pfs_groesse)
        struct.pack_into("<Q", pfs, 0x00, 2)
        if kennung:
            struct.pack_into("<Q", pfs, 0x08, PFS_MAGIC)
        pfs[0x370:0x370 + len(seed)] = seed
        return bytes(vorspann) + bytes(pfs) + cnt

    @staticmethod
    def _lesen(inhalt: bytes):
        with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as f:
            f.write(inhalt)
            path = f.name
        try:
            return read_pkg(path)
        finally:
            os.remove(path)

    def test_klartextmarke_wird_erkannt(self) -> None:
        """Die Marke des Klartext-Profils (PPRPLAIN-NOAUTH!) wird gemeldet.

        Gefunden am 18.09.2026 in einem fremden Baukasten, der Pakete mit dem
        SDK-Publisher baut und danach als Klartext kennzeichnet. Ohne die Marke
        versucht ein gewoehnlicher Leser AES-XTS - mit ihr weiss er Bescheid.
        Uebernommen ist nur diese Formattatsache, kein fremder Code. Sie steht
        an der Seed-Stelle im PFS-Kopf, nicht im Kopfbereich davor (U1-7).
        """
        from ps5_validator.utils.pkg_reader import PLAINTEXT_SEED

        for seed, mit_marke in ((PLAINTEXT_SEED, True), (bytes(range(16)), False)):
            with self.subTest(marke=mit_marke):
                info = self._lesen(self._fih_paket(seed))
                self.assertEqual(info.plaintext_marker, mit_marke)
                # Der Rest muss unveraendert gelesen werden.
                self.assertEqual(info.type, "full_debug")
                self.assertEqual(len(info.entries), 2)

    def test_klartextmarke_nur_an_der_seed_stelle(self) -> None:
        """Im Kopfbereich vor dem PFS zaehlt sie nicht - dort suchte die alte Pruefung."""
        from ps5_validator.utils.pkg_reader import PLAINTEXT_SEED

        info = self._lesen(self._fih_paket(bytes(16), im_kopfbereich=PLAINTEXT_SEED))
        self.assertFalse(info.plaintext_marker)

    def test_klartextmarke_ohne_pfs_kopf_nicht_feststellbar(self) -> None:
        """Zeigt FIH+0x20 nicht auf einen PFS-Kopf, ist "nein" geraten - also None."""
        from ps5_validator.utils.pkg_reader import PLAINTEXT_SEED

        for fall, paket in (
                ("keine PFS-Kennung", self._fih_paket(PLAINTEXT_SEED, kennung=False)),
                ("vor dem PFS", self._fih_paket(PLAINTEXT_SEED, kopf=0x100)),
                ("hinter dem PFS", self._fih_paket(PLAINTEXT_SEED, kopf=0x10F00))):
            with self.subTest(fall=fall):
                self.assertIsNone(self._lesen(paket).plaintext_marker)

    def test_update_paket_wird_erkannt_aber_nicht_gedeutet(self) -> None:
        """Ein PS5-Update-Paket (Delta) traegt die Kennung LIH.

        Seit 23.09.2026 erkannt (Formattatsache aus fpkg-builder, kein Code
        uebernommen). Sein Kopf ist anders aufgebaut als der FIH-Kopf - der
        Leser meldet deshalb nur die Art und deutet keine Felder, auch wenn
        an FIH-Stellen Werte stehen, die plausibel aussehen.
        """
        from ps5_validator.utils.pkg_reader import LIH_MAGIC

        kopf = bytearray(0x200)
        kopf[0:4] = LIH_MAGIC
        struct.pack_into("<Q", kopf, 0x58, 0x100)  # saehe wie ein CNT-Versatz aus
        with tempfile.NamedTemporaryFile(suffix=".pkg", delete=False) as f:
            f.write(bytes(kopf))
            path = f.name
        try:
            self.assertEqual(detect_pkg_type(path), "delta")
            info = read_pkg(path)
            self.assertEqual(info.type, "delta")
            self.assertIsNone(info.fih)
            self.assertIsNone(info.header)
            self.assertEqual(info.entries, [])
            self.assertIsNone(info.plaintext_marker)
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
