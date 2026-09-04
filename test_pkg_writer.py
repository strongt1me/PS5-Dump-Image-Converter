"""Tests fuer ps5_validator.utils.pkg_writer (Rundlauf gegen pkg_reader)."""
from __future__ import annotations

import os
import tempfile
import unittest

from ps5_validator.utils import pkg_reader, pkg_writer


class PkgWriterMetaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="pkgwriter_test_")

    def tearDown(self) -> None:
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def test_meta_only_roundtrip(self) -> None:
        out_path = os.path.join(self.tmpdir, "test_meta.pkg")
        param = {"contentId": "IV0000-TEST00000_00-0000000000000000", "titleId": "TEST00000"}
        result = pkg_writer.build_debug_pkg(
            out_path, content_id="IV0000-TEST00000_00-0000000000000000", param_json=param,
        )
        self.assertEqual(result["type"], "meta")
        self.assertEqual(pkg_reader.detect_pkg_type(out_path), "meta")

        info = pkg_reader.read_pkg(out_path)
        self.assertEqual(info.type, "meta")
        self.assertIsNotNone(info.header)
        self.assertEqual(info.header.content_id, "IV0000-TEST00000_00-0000000000000000")
        names_entry = info.find_entry(0x0200)
        self.assertIsNotNone(names_entry)
        self.assertEqual(names_entry.name, "entry_names")

        parsed_param = pkg_reader.try_read_param_json(out_path, info)
        self.assertEqual(parsed_param, param)

    def test_digests_and_general_digests_present(self) -> None:
        out_path = os.path.join(self.tmpdir, "test_digests.pkg")
        param = {"titleId": "TEST00001"}
        pkg_writer.build_debug_pkg(out_path, content_id="TEST00001", param_json=param)
        info = pkg_reader.read_pkg(out_path)

        digests_entry = info.find_entry(0x0001)
        general_entry = info.find_entry(0x0080)
        self.assertIsNotNone(digests_entry)
        self.assertIsNotNone(general_entry)
        # digests deckt param.json entry ab -> genau ein 32-Byte SHA3-256-Digest
        self.assertEqual(digests_entry.data_size, 32)
        self.assertEqual(general_entry.data_size, 32)

    def test_extra_entries_roundtrip(self) -> None:
        out_path = os.path.join(self.tmpdir, "test_extra.pkg")
        icon_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        pkg_writer.build_debug_pkg(
            out_path,
            content_id="TEST00002",
            param_json={"titleId": "TEST00002"},
            extra_entries=[(0x1200, "icon0.png", icon_bytes)],
        )
        info = pkg_reader.read_pkg(out_path)
        icon_entry = info.find_entry(0x1200)
        self.assertIsNotNone(icon_entry)
        payload = pkg_reader.read_entry_payload(out_path, info, icon_entry)
        self.assertEqual(payload, icon_bytes)


class PkgWriterFullDebugTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="pkgwriter_full_test_")
        self.pfs_path = os.path.join(self.tmpdir, "fake_inner.pfs")
        with open(self.pfs_path, "wb") as f:
            f.write(b"\x55\xAA" * 40000)  # ~156 KB Platzhalter-Nutzlast

    def tearDown(self) -> None:
        for name in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, name))
        os.rmdir(self.tmpdir)

    def test_full_debug_pkg_roundtrip(self) -> None:
        out_path = os.path.join(self.tmpdir, "test_full.pkg")
        ekpfs = b"\x01" * 32
        param = {"titleId": "TEST00003", "applicationDrmType": "free"}
        result = pkg_writer.build_debug_pkg(
            out_path,
            content_id="TEST00003",
            param_json=param,
            pfs_image_path=self.pfs_path,
            ekpfs=ekpfs,
        )
        self.assertEqual(result["type"], "full_debug")
        self.assertEqual(pkg_reader.detect_pkg_type(out_path), "full_debug")

        info = pkg_reader.read_pkg(out_path)
        self.assertTrue(info.fih.is_debug)
        self.assertFalse(info.fih.is_retail)
        self.assertEqual(info.fih.pfs_image_size, os.path.getsize(self.pfs_path))
        self.assertEqual(info.fih.format_version, pkg_reader.FIH_REQUIRED_FORMAT_VERSION)

        image_key_entry = info.find_entry(0x0020)
        self.assertIsNotNone(image_key_entry)
        payload = pkg_reader.read_entry_payload(out_path, info, image_key_entry)
        self.assertEqual(payload, ekpfs)

        parsed_param = pkg_reader.try_read_param_json(out_path, info)
        self.assertEqual(parsed_param, param)


class EintragszahlTests(unittest.TestCase):
    """``entry_count`` muss in der Rueckgabe stehen - und stimmen.

    Der Docstring von :func:`build_debug_pkg` sagt sie seit jeher zu, geliefert
    wurde sie bis zum 05.09.2026 nicht. Das Fenster "Debug PKG Builder" fragt
    sie ab und zeigte deshalb bei **jedem** Paket "Eintraege: -"; der Anwender
    hielt das fuer ein leeres Paket oder einen Fehler.

    Geprueft wird gegen das, was wirklich in der Datei steht - gelesen vom
    ``pkg_reader``, nicht vom Schreiber selbst.
    """

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="pkgwriter_anzahl_")
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self) -> None:
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_meta_paket_meldet_seine_eintraege(self) -> None:
        ziel = os.path.join(self.tmpdir, "meta.pkg")
        ergebnis = pkg_writer.build_debug_pkg(
            ziel, "UP9000-CUSA00000_00-TESTTESTTEST0000",
            {"titleId": "CUSA00000"})
        self.assertIn("entry_count", ergebnis,
                      "Der Schluessel fehlt - das Fenster zeigt dann '-'.")
        info = pkg_reader.read_pkg(ziel)
        self.assertEqual(
            len(info.entries), ergebnis["entry_count"],
            "Die gemeldete Zahl passt nicht zu dem, was in der Datei steht.")
        self.assertGreater(ergebnis["entry_count"], 0)

    def test_mehr_eintraege_ergeben_eine_hoehere_zahl(self) -> None:
        """Sonst koennte eine feste Zahl den Test bestehen."""
        ziel_a = os.path.join(self.tmpdir, "a.pkg")
        ziel_b = os.path.join(self.tmpdir, "b.pkg")
        kennung = "UP9000-CUSA00000_00-TESTTESTTEST0000"
        param = {"titleId": "CUSA00000"}
        a = pkg_writer.build_debug_pkg(ziel_a, kennung, param)
        b = pkg_writer.build_debug_pkg(
            ziel_b, kennung, param,
            extra_entries=[(0x1000, "zusatz.bin", b"xyz")])
        self.assertEqual(a["entry_count"] + 1, b["entry_count"])


if __name__ == "__main__":
    unittest.main()
