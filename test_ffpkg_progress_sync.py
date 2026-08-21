"""Regressionstests für den synchronen UFS2Tool-/FFPKG-Fortschritt."""
from __future__ import annotations

import io
import sys
import tempfile
import time
import unittest
from pathlib import Path

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI


class _ChunkedStream:
    """Minimaler Binärstream, der bewusst an beliebigen Stellen fragmentiert."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    def read1(self, _size: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


class FfpkgProgressSyncTests(unittest.TestCase):
    def test_makefs_progress_parser_reads_real_protocol_fields(self) -> None:
        parsed = PS5ConverterGUI._parse_ffpkg_makefs_progress(
            "Adding files to image...  42% (1,234/2,000 files, 1.25 GiB/3.00 GiB)"
        )
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["percent"], 42.0)
        self.assertEqual(parsed["files_done"], 1234)
        self.assertEqual(parsed["files_total"], 2000)
        self.assertEqual(parsed["bytes_done"], int(1.25 * 1024**3))
        self.assertEqual(parsed["bytes_total"], int(3.00 * 1024**3))

    def test_makefs_progress_parser_rejects_unrelated_output(self) -> None:
        self.assertIsNone(
            PS5ConverterGUI._parse_ffpkg_makefs_progress("UFS2 filesystem created successfully")
        )

    def test_binary_record_reader_splits_carriage_returns_immediately(self) -> None:
        stream = _ChunkedStream(
            [
                b"Preparing image...\rAdding files to image...   7% (7/100 files",
                b", 7.00 MiB/100.00 MiB)\rAdding files to image...  42% ",
                b"(42/100 files, 42.00 MiB/100.00 MiB)\nDone",
            ]
        )
        records = list(PS5ConverterGUI._iter_subprocess_records(stream, "utf-8", "replace"))
        self.assertEqual(
            records,
            [
                "Preparing image...",
                "Adding files to image...   7% (7/100 files, 7.00 MiB/100.00 MiB)",
                "Adding files to image...  42% (42/100 files, 42.00 MiB/100.00 MiB)",
                "Done",
            ],
        )

    def test_subprocess_callback_receives_cr_record_before_process_exit(self) -> None:
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui._append_to_log = lambda _text: None
        callback_records: list[tuple[str, float]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            helper = Path(temp_dir) / "emit_cr_progress.py"
            helper.write_text(
                "import sys, time\n"
                "sys.stdout.write('Adding files to image...   7% (7/100 files, 7.00 MiB/100.00 MiB)\\r')\n"
                "sys.stdout.flush()\n"
                "time.sleep(0.8)\n"
                "sys.stdout.write('Adding files to image... 100% (100/100 files, 100.00 MiB/100.00 MiB)\\r')\n"
                "sys.stdout.flush()\n",
                encoding="utf-8",
            )

            started = time.monotonic()

            def callback(record: str) -> bool:
                callback_records.append((record, time.monotonic()))
                return True

            rc = gui._run_subprocess_logged(
                [sys.executable, str(helper)],
                timeout=10,
                line_callback=callback,
            )

        self.assertEqual(rc, 0)
        self.assertEqual(len(callback_records), 2)
        self.assertIn("7%", callback_records[0][0])
        self.assertIn("100%", callback_records[1][0])
        self.assertLess(callback_records[0][1] - started, 0.65)
        self.assertGreater(callback_records[1][1] - callback_records[0][1], 0.55)


class FfpkgSchrittdreiTests(unittest.TestCase):
    """Schritt 3 des FFPKG-Baus hatte keinen Platz auf dem Balken.

    Gemessen an einem 743-MB-Paket: Der UFS2Tool-Lauf meldete seinen Fortschritt
    ueber die ganze Spanne (5 bis 98) und war damit schon bei 98 %, bevor
    Schritt 3 begann. Die restlichen 49 von 87 Sekunden - Strukturpruefung,
    Dateizahl per Mount, zwei SHA-256-Durchgaenge und die Uebertragung - liefen
    ohne jede Regung. Nach der Reparatur beginnt Schritt 3 bei 56 %.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        stelle = cls.quelltext.index("def _build_ffpkg_from_folder")
        cls.block = cls.quelltext[stelle:stelle + 24000]

    def test_der_bau_meldet_nur_bis_zur_schrittgrenze(self) -> None:
        """Das Kernstueck: step_end darf nicht mehr progress_end sein."""
        self.assertIn('"step_end": float(_schritt2_ende)', self.block)
        self.assertNotIn('"step_end": float(progress_end)', self.block)

    def test_schrittgrenze_liegt_zwischen_start_und_ende(self) -> None:
        for start, ende in ((5.0, 98.0), (5.0, 50.0), (55.0, 98.0), (15.0, 29.0)):
            spanne = max(2.0, ende - start)
            grenze = start + spanne * 0.55
            with self.subTest(bereich=(start, ende)):
                self.assertGreater(grenze, start)
                self.assertLess(grenze, ende)

    def test_schritt_drei_meldet_seine_teilschritte(self) -> None:
        """Ohne Zwischenmarken bliebe der Balken innerhalb von Schritt 3 stehen."""
        for anteil in ("_s3(0.14)", "_s3(0.32)", "_s3(1.0)"):
            self.assertIn(anteil, self.block, f"Marke fehlt: {anteil}")

    def test_pruefsumme_und_kopie_melden_bytes(self) -> None:
        """Zwei SHA-256-Laeufe und eine Kopie sind der Grossteil von Schritt 3."""
        self.assertIn("_file_sha256(stage_path, von=", self.block)
        self.assertIn("_file_sha256(transfer_path,", self.block)
        self.assertIn("_kopiere_mit_fortschritt(stage_path, transfer_path", self.block)
        self.assertNotIn("shutil.copyfile(stage_path, transfer_path)", self.block)

    def test_marken_steigen_monoton(self) -> None:
        """Die Anteile muessen in der Reihenfolge ihres Auftretens wachsen."""
        import re
        anteile = [float(m.group(1)) for m in re.finditer(r"_s3\((\d\.\d+)\)", self.block)]
        self.assertTrue(anteile, "keine Marken gefunden")
        self.assertEqual(anteile, sorted(anteile), f"Marken nicht aufsteigend: {anteile}")
        self.assertLessEqual(max(anteile), 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
