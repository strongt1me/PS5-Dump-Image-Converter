"""Tests fuer ps5_validator.utils.pkg_merger (Split-PKG-Reassemblierung)."""
import os
import shutil
import struct
import tempfile
import unittest

from ps5_validator.utils.pkg_merger import (
    PkgMergeError,
    discover_split_sets,
    merge_directory,
    merge_split_set,
    validate_split_set,
)
from ps5_validator.utils.pkg_reader import CNT_MAGIC, FIH_MAGIC


class PkgMergerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name: str, data: bytes) -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_discover_groups_numbered_and_meta_pieces(self) -> None:
        self._write("GAME_0.pkg", b"a")
        self._write("GAME_1.pkg", b"b")
        self._write("GAME_sc.pkg", b"c")
        self._write("OTHER_0.pkg", b"d")
        self._write("not-a-pkg.txt", b"e")

        sets = discover_split_sets(self.tmpdir)
        by_name = {s.base_name: s for s in sets}
        self.assertIn("GAME", by_name)
        self.assertIn("OTHER", by_name)
        game = by_name["GAME"]
        self.assertTrue(game.has_root)
        self.assertEqual(game.ordered_numbered, [
            os.path.join(self.tmpdir, "GAME_0.pkg"),
            os.path.join(self.tmpdir, "GAME_1.pkg"),
        ])
        self.assertEqual(game.meta, os.path.join(self.tmpdir, "GAME_sc.pkg"))

    def test_validate_and_merge_valid_split_set(self) -> None:
        # Wurzelteil trägt den FIH-Header; cnt_offset muss der tatsächlichen Dateigröße entsprechen,
        # da hier nur ein einziges nummeriertes Teil verwendet wird.
        piece0 = bytearray(0x100)
        piece0[0:4] = FIH_MAGIC
        piece0[0x05] = 0x00  # debug
        struct.pack_into("<H", piece0, 0x06, 3)
        struct.pack_into("<Q", piece0, 0x10, 0x10)   # pfs_offset
        struct.pack_into("<Q", piece0, 0x18, 0xF0)   # pfs_size
        struct.pack_into("<Q", piece0, 0x58, 0x100)  # cnt_offset == pfs_offset + pfs_size == Dateigröße
        piece0 = bytes(piece0)

        p0 = self._write("TITLE_0.pkg", piece0)
        meta = self._write("TITLE_sc.pkg", CNT_MAGIC + b"\x00" * 12)

        validation = validate_split_set([p0], meta)
        self.assertTrue(validation.is_valid, validation.errors)
        self.assertEqual(validation.package_type, "full_debug")
        self.assertEqual(validation.numbered_size, 0x100)
        self.assertEqual(validation.embedded_cnt_offset, 0x100)

        out_path = os.path.join(self.tmpdir, "TITLE-merged.pkg")
        result = merge_split_set([p0], meta, out_path, compute_digest=True)
        self.assertTrue(os.path.isfile(out_path))
        self.assertEqual(result.total_size, len(piece0) + len(CNT_MAGIC + b"\x00" * 12))
        self.assertEqual(result.base_name, "TITLE")
        self.assertIsNotNone(result.sha256)
        with open(out_path, "rb") as f:
            merged = f.read()
        self.assertEqual(merged, piece0 + CNT_MAGIC + b"\x00" * 12)

    def test_validate_rejects_size_mismatch(self) -> None:
        piece0 = bytearray(0x60)
        piece0[0:4] = FIH_MAGIC
        piece0[0x05] = 0x00
        struct.pack_into("<H", piece0, 0x06, 3)
        struct.pack_into("<Q", piece0, 0x10, 0x10)
        struct.pack_into("<Q", piece0, 0x18, 0x20)
        struct.pack_into("<Q", piece0, 0x58, 0x30)  # cnt_offset = 0x30, aber Datei ist nur 0x60 lang
        p0 = self._write("BAD_0.pkg", bytes(piece0))

        validation = validate_split_set([p0], None)
        self.assertFalse(validation.is_valid)
        self.assertTrue(any("entspricht nicht" in e for e in validation.errors))

        with self.assertRaises(PkgMergeError):
            merge_split_set([p0], None, os.path.join(self.tmpdir, "BAD-merged.pkg"))

    def test_validate_rejects_missing_piece(self) -> None:
        validation = validate_split_set([os.path.join(self.tmpdir, "GHOST_0.pkg")], None)
        self.assertFalse(validation.is_valid)
        self.assertTrue(any("fehlt" in e for e in validation.errors))

    def test_merge_directory_skips_set_without_root(self) -> None:
        self._write("NOROOT_1.pkg", b"x")
        results = merge_directory(self.tmpdir)
        self.assertEqual(results, [])


class PunktImBasisnamenTests(unittest.TestCase):
    """Regression: Basisnamen mit Punkt fielen komplett durchs Raster.

    Die Zerlegung suchte den ERSTEN Punkt im Dateinamen statt der Endung.
    Damit galt jeder Satz, dessen Name selbst einen Punkt enthaelt - etwa die
    Versionsklammer `(01.003.000)`, wie sie dieses Programm selbst vergibt -
    als "entspricht nicht dem Split-Namensschema" und wurde uebersprungen.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _write(self, name: str, data: bytes = b"x") -> str:
        path = os.path.join(self.tmpdir, name)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def test_versionsklammer_wird_erkannt(self) -> None:
        self._write("Arcade Game Zone (01.003.000)_0.pkg")
        self._write("Arcade Game Zone (01.003.000)_1.pkg")
        self._write("Arcade Game Zone (01.003.000)_sc.pkg")
        meldungen: list[str] = []
        sets = discover_split_sets(self.tmpdir, log=meldungen.append)
        self.assertEqual(len(sets), 1, f"nicht erkannt; Meldungen: {meldungen}")
        satz = sets[0]
        self.assertEqual(satz.base_name, "Arcade Game Zone (01.003.000)")
        self.assertEqual(len(satz.numbered), 2)
        self.assertTrue(satz.meta)

    def test_punkt_im_namen_ohne_klammer(self) -> None:
        self._write("Game.v1.00_0.pkg")
        sets = discover_split_sets(self.tmpdir)
        self.assertEqual([s.base_name for s in sets], ["Game.v1.00"])

    def test_einfacher_name_bleibt_unveraendert(self) -> None:
        self._write("GAME_0.pkg")
        self._write("GAME_sc.pkg")
        sets = discover_split_sets(self.tmpdir)
        self.assertEqual([s.base_name for s in sets], ["GAME"])
        self.assertTrue(sets[0].meta)

    def test_name_ohne_unterstrich_wird_weiterhin_verworfen(self) -> None:
        self._write("keinsplit.pkg")
        meldungen: list[str] = []
        sets = discover_split_sets(self.tmpdir, log=meldungen.append)
        self.assertEqual(sets, [])
        self.assertTrue(any("Split-Namensschema" in m for m in meldungen))

    def test_sonderzeichen_im_basisnamen(self) -> None:
        self._write("Matchbox™ Adventures (01.000.001)_0.pkg")
        sets = discover_split_sets(self.tmpdir)
        self.assertEqual([s.base_name for s in sets], ["Matchbox™ Adventures (01.000.001)"])


if __name__ == "__main__":
    unittest.main()
