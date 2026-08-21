"""Regressionstests für den virtuellen (Unpack-freien) .ffpfsc-Metadaten-Lesepfad.

Deckt zwei Dinge ab:
  1. Der neue PFS-in-PFS-Lesepfad (_open_virtual_pfs_reader) liefert bei einem echten,
     via MkPFS gebauten verschachtelten .ffpfsc (Ordner -> rohes inneres PFS -> äußeres
     PFS) korrekte sce_sys/param.json-Metadaten, ohne den äußeren Container zu entpacken.
  2. Regressionsschutz für einen Bug, bei dem `virtual_fh.close()` (im finally-Block)
     eine AttributeError auslöste, weil `_LogicalFileView` kein close() besitzt – dadurch
     wurde JEDES erfolgreiche Ergebnis des schnellen Lesepfads verschluckt und es kam
     immer zum teuren Unpack-Fallback, unabhängig vom exFAT- oder PFS-in-PFS-Zweig.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MKPFS_DIR = ROOT / "MkPFS-0.0.9"

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI  # noqa: E402


def _build_nested_ffpfsc(dest_dir: Path) -> Path:
    """Baut ein reales, zweistufiges .ffpfsc (Ordner -> rohes inneres PFS -> äußeres PFS)."""
    sys.path.insert(0, str(MKPFS_DIR))
    import mkpfs.cli as mkpfs_cli  # noqa: PLC0415

    src = dest_dir / "game"
    (src / "sce_sys").mkdir(parents=True)
    (src / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 60)
    param = {
        "titleId": "CUSA00001",
        "titleName": "Test Game",
        "masterVersion": "01.00",
        "systemVersion": "07.008.001",
        "region": "USA",
        "applicationCategoryType": 0,
    }
    (src / "sce_sys" / "param.json").write_text(json.dumps(param), encoding="utf-8")

    inner_pfs = dest_dir / "pfs_image.dat"
    outer_ffpfsc = dest_dir / "out.ffpfsc"

    with contextlib.redirect_stdout(io.StringIO()):
        rc_inner = mkpfs_cli.main([
            "pack", "folder", "--raw", "--no-compress",
            "--no-verify-structure", "--no-adjust-output-file-extension",
            "--version", "PS5", "--inode-bits", "32", "--block-size", "65536",
            str(src), str(inner_pfs),
        ])
        rc_outer = mkpfs_cli.main([
            "pack", "file", "--no-compress",
            "--no-verify-structure", "--no-adjust-output-file-extension",
            "--version", "PS5", "--inode-bits", "32",
            "--cpu-count", "1", "--compression-level", "1", "--block-size", "65536",
            str(inner_pfs), str(outer_ffpfsc),
        ])
    if rc_inner != 0 or rc_outer != 0 or not outer_ffpfsc.is_file():
        raise RuntimeError(f"MkPFS-Fixture-Aufbau fehlgeschlagen (rc_inner={rc_inner}, rc_outer={rc_outer})")
    return outer_ffpfsc


class FfpfscVirtualMetaTests(unittest.TestCase):
    def _make_gui(self) -> PS5ConverterGUI:
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui.mkpfs_dir = str(MKPFS_DIR.resolve())
        return gui

    def test_nested_pfs_in_pfs_fast_path_reads_real_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            outer_ffpfsc = _build_nested_ffpfsc(Path(td))
            gui = self._make_gui()
            meta, _cover_img = gui._extract_meta_from_ffpfsc_virtual(str(outer_ffpfsc))

        self.assertEqual(meta.get("title_id"), "CUSA00001")
        self.assertEqual(meta.get("version"), "01.00")
        self.assertEqual(meta.get("region"), "USA")
        self.assertEqual(
            meta.get("_metadata_method"),
            "MkPFS PFSC + PFS-in-PFS-Reader (read-only)",
            "Erwartet den schnellen PFS-in-PFS-Lesepfad, nicht den teuren Unpack-Fallback.",
        )

    def test_virtual_reader_close_guard_does_not_swallow_result(self) -> None:
        """Regressionsschutz: ein fehlendes close() auf virtual_fh darf ein gefundenes
        Ergebnis nicht mehr verschlucken (siehe Moduldocstring)."""
        with tempfile.TemporaryDirectory() as td:
            outer_ffpfsc = _build_nested_ffpfsc(Path(td))
            gui = self._make_gui()
            meta, _cover_img = gui._extract_meta_from_ffpfsc_virtual(str(outer_ffpfsc))

        empty_placeholder_count = sum(
            1 for key in ("title_id", "version", "region", "category")
            if str(meta.get(key, "")).strip() in {"", "-", "–", "Unbekannt", "�"}
        )
        self.assertLess(
            empty_placeholder_count, 4,
            "Alle Felder leer -> der schnelle Lesepfad ist auf den Unpack-Fallback zurückgefallen.",
        )


if __name__ == "__main__":
    unittest.main()
