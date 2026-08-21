"""Tests fuer ps5_validator.utils.gp5_project (GP5-Projektdatei lesen/schreiben)."""
import os
import tempfile
import unittest

from ps5_validator.utils.gp5_project import (
    DEFAULT_PASSCODE,
    Gp5Dir,
    Gp5File,
    Gp5Project,
    Gp5RootDir,
    Gp5VolumeType,
    create_project,
    read_from,
    write_to,
)


class Gp5ProjectTests(unittest.TestCase):
    def _roundtrip(self, project: Gp5Project) -> Gp5Project:
        with tempfile.NamedTemporaryFile(suffix=".gp5", delete=False) as f:
            path = f.name
        try:
            write_to(project, path)
            self.assertTrue(os.path.isfile(path))
            with open(path, "r", encoding="utf-8") as fh:
                content = fh.read()
            self.assertIn("<?xml", content)
            self.assertIn("<psproject", content)
            return read_from(path)
        finally:
            os.remove(path)

    def test_create_app_project_has_chunk_info(self) -> None:
        project = create_project(
            Gp5VolumeType.APP, src_path=r"C:\dumps\MyGame", content_id="UP0000-PPSA00000_00-0000000000000000"
        )
        self.assertIsNotNone(project.volume.chunk_info)
        self.assertEqual(project.volume.package.passcode, DEFAULT_PASSCODE)
        self.assertFalse(project.is_flat_layout)

        loaded = self._roundtrip(project)
        self.assertEqual(loaded.volume.volume_type, Gp5VolumeType.APP)
        self.assertEqual(loaded.volume.package.content_id, "UP0000-PPSA00000_00-0000000000000000")
        self.assertEqual(loaded.rootdir.src_path, r"C:\dumps\MyGame")
        self.assertIsNotNone(loaded.volume.chunk_info)
        self.assertEqual(loaded.volume.chunk_info.chunks[0].label, "Chunk #0")
        self.assertEqual(loaded.volume.chunk_info.scenarios[0].chunks, "0")

    def test_create_ac_nodata_project_has_no_chunk_info(self) -> None:
        project = create_project(Gp5VolumeType.AC_NODATA, src_path=r"C:\dumps\Dlc")
        self.assertIsNone(project.volume.chunk_info)

        loaded = self._roundtrip(project)
        self.assertIsNone(loaded.volume.chunk_info)
        self.assertEqual(loaded.volume.volume_type, Gp5VolumeType.AC_NODATA)

    def test_flat_layout_roundtrip(self) -> None:
        project = Gp5Project()
        project.volume.package.content_id = "UP0000-PPSA00001_00-0000000000000000"
        project.files = [
            Gp5File(src_path=r"C:\src\eboot.bin", dst_path="eboot.bin"),
            Gp5File(src_path=r"C:\src\sce_sys\param.json", dst_path="sce_sys/param.json"),
        ]
        project.folders = [Gp5Dir(src_path=r"C:\src\data", dst_path="data")]
        self.assertTrue(project.is_flat_layout)

        loaded = self._roundtrip(project)
        self.assertTrue(loaded.is_flat_layout)
        self.assertEqual(len(loaded.files), 2)
        self.assertEqual(loaded.files[0].dst_path, "eboot.bin")
        self.assertEqual(loaded.files[1].src_path, r"C:\src\sce_sys\param.json")
        self.assertEqual(len(loaded.folders), 1)
        self.assertEqual(loaded.folders[0].dst_path, "data")
        # Flat-Layout: kein rootdir/global_exclude erwartet
        self.assertEqual(loaded.rootdir.src_path, "")

    def test_rootdir_excludes_roundtrip(self) -> None:
        project = create_project(Gp5VolumeType.PATCH, src_path=r"C:\dumps\Patch")
        project.rootdir = Gp5RootDir(
            src_path=r"C:\dumps\Patch", dir_exclude="*.tmp", file_exclude="*.log"
        )
        project.global_exclude = "*.bak"

        loaded = self._roundtrip(project)
        self.assertEqual(loaded.rootdir.dir_exclude, "*.tmp")
        self.assertEqual(loaded.rootdir.file_exclude, "*.log")
        self.assertEqual(loaded.global_exclude, "*.bak")

    def test_read_hand_written_gp5(self) -> None:
        xml = (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<psproject fmt="gp5" version="1000">\n'
            "  <volume>\n"
            "    <volume_type>prospero_ac</volume_type>\n"
            '    <package content_id="UP0000-PPSA00002_00-0000000000000000" '
            'passcode="00000000000000000000000000000000"/>\n'
            "  </volume>\n"
            '  <rootdir src_path="C:\\dumps\\Dlc2"/>\n'
            "</psproject>\n"
        )
        with tempfile.NamedTemporaryFile(mode="w", suffix=".gp5", delete=False, encoding="utf-8") as f:
            f.write(xml)
            path = f.name
        try:
            project = read_from(path)
            self.assertEqual(project.volume.volume_type, Gp5VolumeType.AC)
            self.assertEqual(project.volume.package.content_id, "UP0000-PPSA00002_00-0000000000000000")
            self.assertEqual(project.rootdir.src_path, "C:\\dumps\\Dlc2")
            self.assertIsNone(project.volume.chunk_info)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
