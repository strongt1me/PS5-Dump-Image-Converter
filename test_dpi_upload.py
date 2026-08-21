"""Tests fuer ps5_validator.utils.dpi_upload."""
from __future__ import annotations

import unittest

from ps5_validator.utils import dpi_upload


class DpiUploadTests(unittest.TestCase):
    def test_content_type_header_default_boundary(self) -> None:
        self.assertEqual(
            dpi_upload.content_type_header(),
            f"multipart/form-data; boundary={dpi_upload.DEFAULT_BOUNDARY}",
        )

    def test_content_type_header_custom_boundary(self) -> None:
        self.assertEqual(
            dpi_upload.content_type_header("XYZ"),
            "multipart/form-data; boundary=XYZ",
        )

    def test_build_multipart_frame_header_contains_filename(self) -> None:
        header, footer, total = dpi_upload.build_multipart_frame("game.pkg", 1000, boundary="B1")
        self.assertIn(b'filename="game.pkg"', header)
        self.assertIn(b"--B1\r\n", header)
        self.assertIn(b"Content-Type: application/octet-stream\r\n\r\n", header)
        self.assertEqual(footer, b"\r\n--B1--\r\n")
        self.assertEqual(total, len(header) + 1000 + len(footer))

    def test_build_multipart_frame_total_size_matches_zero_payload(self) -> None:
        header, footer, total = dpi_upload.build_multipart_frame("x.pkg", 0)
        self.assertEqual(total, len(header) + len(footer))


if __name__ == "__main__":
    unittest.main()
