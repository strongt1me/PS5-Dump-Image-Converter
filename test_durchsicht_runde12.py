# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 12 (24.09.2026): root.after aus Faeden.

Arbeitsfaeden planten ihre Rueckmeldungen mit ``self.root.after`` ein. Nach
dem Ende der Hauptschleife wirft das "main thread is not in main loop", nach
dem Zerstoeren der Wurzel TclError - der Faden endete mitten in seiner
Arbeit (vor Bericht, Checkpoint, Aufraeumen), und im Fehlerbericht stand ein
Absturz, der keiner war. Jetzt gehen sie ueber ``_hauptfaden_planen``, an
ein Fenster gebundene ueber ``_spaeter_im_fenster``.

Befunde: H5-3, H5-11, H10-8, H10-9, H2-8, H3-19, H6-9, H6-10, H7-8, H8-16,
H4-4, H4-7, H4-12, H4-14, H4-16 (root.after), H2-9 (Generation im
Rueckruf), H6-8 (Statuszeile im Faden gelesen).
"""
from __future__ import annotations

import ast
import sys
import threading
import tkinter as tk
import types
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde12")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

_BAUM: list = []

#: Funktionen, die (auch) aus Arbeitsfaeden laufen - dort kein root.after.
FADENFUNKTIONEN = (
    "_set_progress", "_reset_ui_after_task", "_run_engine_thread",
    "_fetch_patches_async", "_run_startup_temp_cleanup_scan",
    "_cleanup_startup_temp_candidates", "_auto_cleanup_startup_temp",
    "_run_background_installer", "_extract_exfat_to_folder_mkpfs",
    "_finalize_staged_pack_output", "_backfill_preview_from_dir_for_source",
    "_schaetzung_neu_berechnen", "_download_worker", "_on_source_path_changed",
    "_mode_pack_folder", "_mode_folder_to_exfat", "_mode_ffpkg_to_folder",
    "_backport_worker", "_ampr_updates_arbeiten", "_groessenfeld_setzen_wenn_aktuell",
    "_extract_meta_from_file", "on_closing",
)


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    return gui


class _WurzelVorbei:
    """Wurzel nach dem Ende der Hauptschleife."""

    def after(self, *_a, **_k):
        raise RuntimeError("main thread is not in main loop")

    after_idle = after


class _WurzelZerstoert:
    def after(self, *_a, **_k):
        raise tk.TclError('can\'t invoke "after" command: application has been destroyed')


class _Schlange:
    """Wurzel, die Rueckrufe sammelt; der Test fuehrt sie selbst aus."""

    def __init__(self) -> None:
        self.rueckrufe: list = []

    def after(self, _ms, rueckruf, *werte):
        self.rueckrufe.append((rueckruf, werte))
        return "after#%d" % len(self.rueckrufe)


class HelferTests(unittest.TestCase):
    def test_wirft_nie_beim_beenden(self) -> None:
        for wurzel in (_WurzelVorbei(), _WurzelZerstoert()):
            with self.subTest(wurzel=type(wurzel).__name__):
                gui = _gui()
                gui.root = wurzel
                self.assertFalse(gui._hauptfaden_planen(lambda: None))

    def test_plant_ein(self) -> None:
        gui = _gui()
        gui.root = _Schlange()
        self.assertTrue(gui._hauptfaden_planen(print, "x", ms=250))
        self.assertEqual([(print, ("x",))], gui.root.rueckrufe)

    def test_andere_fehler_bleiben_sichtbar(self) -> None:
        """AssertionError einer Test-Attrappe darf nicht verschluckt werden."""
        gui = _gui()

        class _Verboten:
            def after(self, *_a):
                raise AssertionError("verboten")

        gui.root = _Verboten()
        with self.assertRaises(AssertionError):
            gui._hauptfaden_planen(lambda: None)


class KeinRootAfterImFadenTests(unittest.TestCase):
    """Die Fadenfunktionen planen nicht mehr direkt ueber root.after."""

    def test_ueber_den_helfer(self) -> None:
        """Nur Aufrufe als eigene Anweisung zaehlen.

        Eine Zuweisung (``self._job = self.root.after(...)``) braucht ihren
        Rueckgabewert fuer ``after_cancel`` - so plant das Entprellen in
        ``_on_source_path_changed`` im Hauptfaden.
        """
        gefunden = {}
        for knoten in ast.walk(_baum()):
            if isinstance(knoten, ast.FunctionDef) and knoten.name in FADENFUNKTIONEN:
                direkt = [k.value.lineno for k in ast.walk(knoten)
                          if isinstance(k, ast.Expr) and isinstance(k.value, ast.Call)
                          and getattr(k.value.func, "attr", "") in ("after", "after_idle")
                          and ast.unparse(k.value.func.value) == "self.root"]
                gefunden[knoten.name] = direkt
        self.assertEqual(sorted(FADENFUNKTIONEN), sorted(gefunden),
                         "Eine der Fadenfunktionen wurde umbenannt.")
        for name, zeilen in sorted(gefunden.items()):
            with self.subTest(funktion=name):
                self.assertEqual([], zeilen)


class VerhaltenTests(unittest.TestCase):
    """Stichproben: beim Beenden laufen die Faeden durch, statt zu werfen."""

    def test_zuruecksetzen_und_fortschritt_nach_dem_ende(self) -> None:
        for wurzel in (_WurzelVorbei(), _WurzelZerstoert()):
            with self.subTest(wurzel=type(wurzel).__name__):
                gui = _gui()
                gui.root = wurzel
                gui._reset_ui_after_task()
                gui._set_progress(42.0)

    def test_statuszeile_wirft_nicht(self) -> None:
        gui = _gui()
        gui.root = _WurzelZerstoert()
        gui._set_status("egal")


class GroessenfeldTests(unittest.TestCase):
    """H2-9: Die Generation wird im Rueckruf noch einmal geprueft."""

    def test_neue_quelle_zwischen_einplanen_und_ausfuehren(self) -> None:
        gui = _gui()
        gui.root = _Schlange()
        gui._calc_generation = 5
        gesetzt: list = []
        gui._set_size_label_idle = gesetzt.append
        gui._groessenfeld_setzen_wenn_aktuell(5, "51 GB")
        gui._calc_generation = 6          # neue Quelle gewaehlt
        for rueckruf, werte in gui.root.rueckrufe:
            rueckruf(*werte)
        self.assertEqual([], gesetzt, "Die Groesse der alten Quelle wurde gesetzt.")

    def test_gueltige_messung_kommt_an(self) -> None:
        gui = _gui()
        gui.root = _Schlange()
        gui._calc_generation = 5
        gesetzt: list = []
        gui._set_size_label_idle = gesetzt.append
        gui._groessenfeld_setzen_wenn_aktuell(5, "51 GB")
        for rueckruf, werte in gui.root.rueckrufe:
            rueckruf(*werte)
        self.assertEqual(["51 GB"], gesetzt)


class PhasenstatusTests(unittest.TestCase):
    """H6-8: Im Faden wird die Statuszeile nicht gelesen."""

    def test_im_faden_ohne_widget(self) -> None:
        gui = _gui()

        class _NurHauptfaden:
            def cget(self, *_a):
                raise AssertionError("Widget im Faden gelesen")

        gui.status_label = _NurHauptfaden()
        gui.task_num_steps, gui.task_current_step = 4, 2
        gui._status_text_zuletzt = "Phase 3/5 – packen"
        ergebnis: list = []
        faden = threading.Thread(target=lambda: ergebnis.append(
            gui._format_phase_status("schreibt noch")))
        faden.start()
        faden.join(10)
        self.assertEqual(["Phase 3/5 – schreibt noch"], ergebnis)


class AmprAktualisierungTests(unittest.TestCase):
    """H7-8: Ein geschlossener Dialog laesst den Rueckruf nicht werfen."""

    def test_rueckruf_auf_geschlossenen_dialog(self) -> None:
        text = ast.unparse(next(k for k in ast.walk(_baum())
                                if isinstance(k, ast.FunctionDef)
                                and k.name == "_ampr_updates_arbeiten"))
        self.assertIn("tk.TclError", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
