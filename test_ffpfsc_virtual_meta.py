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
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MKPFS_DIR = ROOT / "MkPFS-1.0.0"

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI  # noqa: E402


def _build_nested_ffpfsc(dest_dir: Path, mit_ampr: bool = False) -> Path:
    """Baut ein reales, zweistufiges .ffpfsc (Ordner -> rohes inneres PFS -> äußeres PFS).

    Args:
        dest_dir: Ordner, in dem gebaut wird.
        mit_ampr: Legt zusätzlich ``fakelib/libSceAmpr.sprx`` an - den Marker,
            an dem die Metadatenkette die AMPR-Emulation erkennt.
    """
    sys.path.insert(0, str(MKPFS_DIR))
    import mkpfs.cli as mkpfs_cli  # noqa: PLC0415

    src = dest_dir / "game"
    (src / "sce_sys").mkdir(parents=True)
    (src / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 60)
    param = {
        "titleId": "CUSA00001",
        "contentId": "UP0001-CUSA00001_00-TESTGAME00000001",
        "titleName": "Test Game",
        "masterVersion": "01.00",
        "systemVersion": "07.008.001",
        "region": "USA",
        "applicationCategoryType": 0,
    }
    (src / "sce_sys" / "param.json").write_text(json.dumps(param), encoding="utf-8")
    if mit_ampr:
        (src / "fakelib").mkdir()
        (src / "fakelib" / "libSceAmpr.sprx").write_bytes(b"\x7fELF" + b"\x00" * 60)

    inner_pfs = dest_dir / "pfs_image.dat"
    outer_ffpfsc = dest_dir / "out.ffpfsc"

    # Auch stderr abfangen: Dort schreibt die Fortschrittsanzeige der Engine.
    # Ohne das flutet der Aufbau den Bericht des Laufs.
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
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


class VorschauNimmtDenSchnellenWegTests(unittest.TestCase):
    """Der Weg dorthin, nicht nur der Leser selbst.

    Bis zum 03.09.2026 stand der Aufruf des virtuellen Lesers **in** der
    Schleife ueber die danebenliegenden Ordner. Lag die .ffpfsc allein - der
    Normalfall bei einem fertigen Abbild -, wurde er nie erreicht, und die
    Vorschau ging ueber ``mkpfs unpack``: Die ganze innere Datei wandert dabei
    in einen Temp-Ordner. An einem Abbild von 200 MB gemessen 4,97 s statt
    0,12 s, bei gleichem Ergebnis; der Aufwand waechst mit dem Abbild.

    Die Pruefungen dieser Datei darueber trafen das nicht: Sie rufen den Leser
    **direkt** auf. Geprueft war damit der Leser, nicht seine Anbindung.
    """

    def _gui_ohne_teuren_weg(self) -> PS5ConverterGUI:
        """Eine Instanz, die beim Betreten des teuren Weges auffliegt.

        ``_mkdtemp`` ist der erste Schritt des Unpack-Fallbacks. Wird es
        gerufen, war der schnelle Weg nicht erfolgreich - dann faellt die
        Pruefung mit einer Meldung, die genau das sagt.
        """
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        for name, wert in (
            ("mkpfs_dir", str(MKPFS_DIR.resolve())),
            ("is_running", False),
            ("_preview_cache", {}),
            ("_PREVIEW_CACHE_MAX", 20),
            ("_current_language", "de"),
            ("_preview_report_cache", {}),
            ("_preview_report_dir_cache", {}),
            ("_calc_generation", 0),
            ("_embedded_mkpfs_lock", threading.RLock()),
            ("_append_to_log", lambda *_a, **_k: None),
            ("root", types.SimpleNamespace(after=lambda *_a, **_k: None)),
        ):
            setattr(gui, name, wert)
        gui._extract_embedded_mkpfs = lambda: gui.mkpfs_dir
        gui._mkdtemp = lambda *_a, **_k: self.fail(
            "Die Vorschau hat das Abbild ausgepackt, statt es virtuell zu lesen.")
        return gui

    def test_ein_abbild_allein_im_ordner_wird_virtuell_gelesen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            allein = Path(td) / "allein"
            allein.mkdir()
            outer = _build_nested_ffpfsc(Path(td))
            ziel = allein / outer.name
            outer.replace(ziel)

            gui = self._gui_ohne_teuren_weg()
            meta, cover = gui._extract_meta_from_file(str(ziel), "unpack_to_exfat")

        self.assertEqual(meta.get("title_id"), "CUSA00001")
        self.assertIn("read-only", str(meta.get("_metadata_method", "")),
                      "Erwartet einen der virtuellen Leser, nicht den Unpack-Weg.")

    def test_neben_einem_dumpordner_bleibt_der_schnellpfad_vorn(self) -> None:
        """Liegt ein Ordner mit sce_sys daneben, gilt weiter dessen Angabe.

        Sonst waere die Aenderung ein Tausch statt einer Ergaenzung.
        """
        with tempfile.TemporaryDirectory() as td:
            outer = _build_nested_ffpfsc(Path(td))
            gui = self._gui_ohne_teuren_weg()
            meta, _cover = gui._extract_meta_from_file(str(outer), "unpack_to_exfat")

        self.assertEqual(meta.get("title_id"), "CUSA00001")


class NeueAngabenTests(unittest.TestCase):
    """``content_id`` und ``ampr_emu`` - dazugekommen am 03.09.2026.

    Angeregt von ``mkpfs.game_metadata`` aus MkPFS 1.0.0, das beides liest.
    Die Content-ID nennt zusaetzlich Region und Ausgabe, der Marker sagt, ob
    die Quelle die AMPR-Emulation mitbringt.
    """

    def _gui(self) -> PS5ConverterGUI:
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui.mkpfs_dir = str(MKPFS_DIR.resolve())
        gui._current_language = "de"
        gui._append_to_log = lambda *_a, **_k: None
        return gui

    def test_die_content_id_kommt_aus_dem_abbild(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            outer = _build_nested_ffpfsc(Path(td))
            meta, _cover = self._gui()._extract_meta_from_ffpfsc_virtual(str(outer))
        self.assertEqual(meta.get("content_id"), "UP0001-CUSA00001_00-TESTGAME00000001")

    def test_die_content_id_kommt_auch_aus_dem_ordner(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _build_nested_ffpfsc(Path(td))
            meta = self._gui()._read_game_meta(str(Path(td) / "game"))
        self.assertEqual(meta.get("content_id"), "UP0001-CUSA00001_00-TESTGAME00000001")

    def test_ein_abbild_mit_ampr_emulation_wird_erkannt(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            outer = _build_nested_ffpfsc(Path(td), mit_ampr=True)
            meta, _cover = self._gui()._extract_meta_from_ffpfsc_virtual(str(outer))
        self.assertEqual(meta.get("ampr_emu"), "vorhanden")

    def test_ein_ordner_ohne_ampr_emulation_sagt_das_auch(self) -> None:
        """Auf einem Ordner ist die Frage sicher zu beantworten.

        Im Abbild bricht der Durchgang ab, sobald die drei Zieldateien da
        sind - dort bleibt die Angabe im Zweifel leer, statt zu behaupten,
        es gebe die Emulation nicht.
        """
        with tempfile.TemporaryDirectory() as td:
            _build_nested_ffpfsc(Path(td))
            meta = self._gui()._read_game_meta(str(Path(td) / "game"))
        self.assertEqual(meta.get("ampr_emu"), "nicht vorhanden")

    def test_ein_ordner_mit_ampr_emulation_auch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _build_nested_ffpfsc(Path(td), mit_ampr=True)
            meta = self._gui()._read_game_meta(str(Path(td) / "game"))
        self.assertEqual(meta.get("ampr_emu"), "vorhanden")

    def test_beide_angaben_stehen_im_bedienzustand(self) -> None:
        """Sonst zeigte sie keine der beiden Oberflaechen an."""
        from ps5_validator.ui.bedienzustand import METADATENFELDER

        self.assertIn("content_id", METADATENFELDER)
        self.assertIn("ampr_emu", METADATENFELDER)


if __name__ == "__main__":
    unittest.main()
