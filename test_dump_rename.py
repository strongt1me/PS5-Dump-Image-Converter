"""Tests fuer ps5_validator.utils.dump_rename (reine Namens-/Konfidenzlogik)."""
import unittest

from ps5_validator.utils.dump_rename import (
    CONFIDENCE_FAILED,
    CONFIDENCE_NEEDS_REVIEW,
    CONFIDENCE_READY,
    build_presets,
    compute_confidence,
    is_generic_folder_name,
    sanitize_name,
)


class DumpRenameTests(unittest.TestCase):
    def test_sanitize_name_strips_invalid_chars_and_whitespace(self) -> None:
        self.assertEqual(sanitize_name('My:Game<Title>?  Extra   Spaces'), "MyGameTitle Extra Spaces")

    def test_generic_folder_names_detected_case_insensitively(self) -> None:
        self.assertTrue(is_generic_folder_name("Downloads"))
        self.assertTrue(is_generic_folder_name("BACKUP"))
        self.assertFalse(is_generic_folder_name("Spider-Man 2"))

    def test_confidence_levels(self) -> None:
        self.assertEqual(compute_confidence(False, False, False), CONFIDENCE_FAILED)
        self.assertEqual(compute_confidence(True, False, False), CONFIDENCE_NEEDS_REVIEW)
        self.assertEqual(compute_confidence(True, True, False), CONFIDENCE_NEEDS_REVIEW)
        self.assertEqual(compute_confidence(True, True, True), CONFIDENCE_READY)

    def test_build_presets_without_ppsa_are_empty(self) -> None:
        presets = build_presets("", "Some Title", "01.00", has_ppsa=False, has_version=True)
        self.assertEqual(presets["PPSA only"], "")
        self.assertEqual(presets["PPSA + Title"], "")
        self.assertEqual(presets["PPSA + Title + Version"], "")

    def test_build_presets_with_full_metadata(self) -> None:
        presets = build_presets("PPSA01234", "Spider-Man", "01.005.000", has_ppsa=True, has_version=True)
        self.assertEqual(presets["PPSA only"], "PPSA01234")
        self.assertEqual(presets["PPSA + Title"], "PPSA01234 Spider-Man")
        self.assertEqual(presets["PPSA + Title + Version"], "PPSA01234 Spider-Man (01.005.000)")

    def test_build_presets_without_version_falls_back(self) -> None:
        presets = build_presets("PPSA01234", "Spider-Man", "–", has_ppsa=True, has_version=False)
        self.assertEqual(presets["PPSA + Title + Version"], "PPSA01234 Spider-Man")


if __name__ == "__main__":
    unittest.main()
