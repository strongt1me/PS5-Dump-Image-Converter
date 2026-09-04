"""Gezielte Regressionstests für die UFS2-basierten FFPKG-Buildhilfen."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ps5_validator.utils.ffpkg_support import (
    FfpkgBuildProfile,
    FfpkgNewfsProfile,
    build_makefs_command,
    build_newfs_directory_command,
    build_readonly_validation_commands,
    calculate_makefs_image_size,
    calculate_makefs_inode_density,
    compatibility_newfs_profile,
    default_build_profile,
    normalize_output_path,
    primary_newfs_profile,
    validate_source_folder,
)


class FfpkgBuildSupportTests(unittest.TestCase):
    def test_default_profile_is_valid_and_conservative(self) -> None:
        profile = default_build_profile()
        self.assertEqual(profile.block_size, 65536)
        self.assertEqual(profile.fragment_size, 65536)
        self.assertEqual(profile.sector_size, 512)
        self.assertEqual(profile.min_free_percent, 0)
        self.assertEqual(profile.inode_density, 65536)

    def test_invalid_profile_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            FfpkgBuildProfile(block_size=12345).normalized()
        with self.assertRaises(ValueError):
            FfpkgBuildProfile(fragment_size=1024, block_size=4096, sector_size=777).normalized()
        with self.assertRaises(ValueError):
            FfpkgNewfsProfile("invalid", 65536, 4096).normalized()

    def test_primary_newfs_command_matches_64k_reference_profile(self) -> None:
        """``-S 4096``, nicht 512.

        ShadowMount+ haengt UFS-Abbilder ueber sein Standard-Backend LVD mit
        4096-Byte-Sektoren ein und empfiehlt genau diesen Befehl. Bis v1.9.5
        baute dieses Projekt mit 512; ein so gebautes .ffpkg hing an echter
        Hardware sauber ein - fsck fehlerfrei, Dateizahl bestaetigt - und der
        Titel stuerzte eine Sekunde nach dem Start ab (04.09.2026 gemessen).
        Dasselbe Spiel als exFAT-in-.ffpfsc lief.
        """
        profile = primary_newfs_profile()
        self.assertEqual(profile.identifier, "newfs-64k-reference")
        command = build_newfs_directory_command(
            "C:/Tools/UFS2Tool.exe",
            "C:/Source/Game",
            "C:/Out/Game",
            profile=profile,
        )
        self.assertEqual(
            command,
            [
                "C:/Tools/UFS2Tool.exe",
                "newfs",
                "-O",
                "2",
                "-b",
                "65536",
                "-f",
                "65536",
                "-S",
                "4096",
                "-m",
                "0",
                "-i",
                "262144",
                "-D",
                "C:/Source/Game",
                "C:/Out/Game.ffpkg",
            ],
        )

    def test_compatibility_newfs_command_matches_32k_4k_reference_profile(self) -> None:
        profile = compatibility_newfs_profile()
        self.assertEqual(profile.identifier, "newfs-32k-4k-compatibility")
        command = build_newfs_directory_command(
            "C:/Tools/UFS2Tool.exe",
            "C:/Source/Game",
            "C:/Out/Game",
            profile=profile,
        )
        self.assertEqual(
            command,
            [
                "C:/Tools/UFS2Tool.exe",
                "newfs",
                "-O",
                "2",
                "-b",
                "32768",
                "-f",
                "4096",
                "-S",
                "512",
                "-D",
                "C:/Source/Game",
                "C:/Out/Game.ffpkg",
            ],
        )
        self.assertNotIn("-m", command)
        self.assertNotIn("-i", command)

    def test_makefs_size_uses_headroom_metadata_reserve_and_block_alignment(self) -> None:
        profile = default_build_profile()
        source_bytes = 648_398_581
        file_count = 15_001
        image_size = calculate_makefs_image_size(source_bytes, file_count, profile)
        self.assertGreaterEqual(
            image_size,
            source_bytes
            + file_count * (profile.fragment_size - 1)
            + 128 * 1024 * 1024
            + file_count * 16 * 1024,
        )
        self.assertEqual(image_size % profile.block_size, 0)

    def test_makefs_size_accounts_for_many_tiny_files(self) -> None:
        profile = default_build_profile()
        source_bytes = 5000 * 64
        file_count = 5000
        image_size = calculate_makefs_image_size(source_bytes, file_count, profile)
        previous_underestimate = source_bytes + 128 * 1024 * 1024 + file_count * 16 * 1024
        self.assertGreater(image_size, previous_underestimate + 300 * 1024 * 1024)
        self.assertGreaterEqual(
            image_size,
            source_bytes + file_count * (profile.fragment_size - 1),
        )

    def test_makefs_inode_density_reserves_entries(self) -> None:
        image_size = calculate_makefs_image_size(648_398_581, 15_000)
        density = calculate_makefs_inode_density(image_size, 15_000)
        self.assertGreaterEqual(density, 4096)
        self.assertLessEqual(density, default_build_profile().inode_density)
        self.assertGreaterEqual(image_size // density, 15_000 * 2 + 2048)

    def test_makefs_command_uses_explicit_ufs2_geometry(self) -> None:
        command = build_makefs_command(
            "C:/Tools/UFS2Tool.exe",
            "C:/Source/Game",
            "C:/Out/Game",
            source_size_bytes=648_398_581,
            file_count=200,
        )
        self.assertEqual(command[0:4], ["C:/Tools/UFS2Tool.exe", "makefs", "-t", "ffs"])
        self.assertIn("-s", command)
        self.assertIn("-o", command)
        options = command[command.index("-o") + 1]
        self.assertIn("version=2", options)
        self.assertIn("bsize=65536", options)
        self.assertIn("fsize=65536", options)
        self.assertIn("density=", options)
        self.assertIn("optimization=time", options)
        self.assertEqual(command[-2], "C:/Out/Game.ffpkg")
        self.assertEqual(command[-1], "C:/Source/Game")
        self.assertNotIn("newfs", command)
        self.assertNotIn("-D", command)
        self.assertNotIn("fsck_ufs", command)

    def test_output_path_requires_ffpkg_extension(self) -> None:
        self.assertEqual(normalize_output_path("out/game").name, "game.ffpkg")
        self.assertEqual(normalize_output_path("out/GAME.FFPKG").suffix, ".FFPKG")
        with self.assertRaises(ValueError):
            normalize_output_path(".ffpkg")

    def test_source_validation_counts_regular_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dump"
            nested = root / "nested"
            nested.mkdir(parents=True)
            (root / "a.bin").write_bytes(b"abc")
            (nested / "b.bin").write_bytes(b"12345")
            self.assertEqual(validate_source_folder(root), (2, 8))

    def test_empty_source_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "dump"
            root.mkdir()
            with self.assertRaises(ValueError):
                validate_source_folder(root)

            target = Path(temp_dir) / "payload.bin"
            target.write_bytes(b"payload")
            (root / "linked.bin").symlink_to(target)
            with self.assertRaises(ValueError):
                validate_source_folder(root)

    def test_validation_commands_are_read_only(self) -> None:
        info, fsck = build_readonly_validation_commands("UFS2Tool.exe", "game.ffpkg")
        self.assertEqual(info, ["UFS2Tool.exe", "info", "game.ffpkg"])
        self.assertEqual(fsck, ["UFS2Tool.exe", "fsck_ufs", "-fn", "game.ffpkg"])
        self.assertNotIn("-y", fsck)
        self.assertNotIn("--repair", fsck)


if __name__ == "__main__":
    unittest.main(verbosity=2)
