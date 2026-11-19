# -*- coding: utf-8 -*-
"""Pruefung beim Waehlen einer Quelle: was ist schon eingebaut, braucht das Spiel PlayGo? (Nutzer 06.10.2026)

An echten kleinen Dump-Ordnern im Temp-Verzeichnis: AMPR EMU/BACKPORT/PlayGo erkannt, "nichts eingebaut" samt
PlayGo-Empfehlung, wenn das Spiel PlayGo-Dateien traegt. Nichts wird eingeschaltet.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui._calc_generation = 7
    gui.is_running = False
    gui.zeilen = []
    gui._append_to_log = gui.zeilen.append
    gui._hauptfaden_planen = lambda *a, **k: None
    return gui


class PruefungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wurzel = Path(tempfile.mkdtemp(prefix="einbau_pruefung_"))
        self.addCleanup(shutil.rmtree, self.wurzel, True)
        self.spiel = self.wurzel / "PPSA01234"
        (self.spiel / "sce_sys").mkdir(parents=True)
        (self.spiel / "eboot.bin").write_bytes(b"x")

    def _pruefen(self) -> str:
        gui = _gui()
        gui._quelle_einbauten_pruefen(str(self.spiel), 7)
        return "".join(gui.zeilen)

    def test_nichts_eingebaut_und_playgo_nicht_noetig(self) -> None:
        text = self._pruefen()
        self.assertIn("noch nichts eingebaut", text)
        self.assertIn("PlayGo nicht nötig", text)

    def test_nichts_eingebaut_aber_playgo_empfohlen(self) -> None:
        (self.spiel / "sce_sys" / "playgo-scenario.json").write_text("{}", encoding="utf-8")
        text = self._pruefen()
        self.assertIn("noch nichts eingebaut", text)
        # Der Hinweis steht seit 18.11.2026 so im Protokoll, wie ihn Seite 7 unter der Quelle zeigte (orange, "⚠").
        self.assertIn("⚠ PlayGo-Dateien gefunden (sce_sys/playgo-scenario.json) – PlayGo beim Backup einbinden!", text)

    def test_ampr_und_backport_erkannt(self) -> None:
        fakelib = self.spiel / "fakelib"
        (fakelib / "fw11").mkdir(parents=True)
        (fakelib / "fw11" / "libSceRtc.sprx").write_bytes(b"x")
        (fakelib / "libSceAmpr.sprx").write_bytes(b"x")
        text = self._pruefen()
        self.assertIn("bereits eingebaut", text)
        self.assertIn("AMPR EMU", text)
        self.assertIn("BACKPORT (fw11)", text)

    def test_playgo_schon_drin_keine_empfehlung(self) -> None:
        (self.spiel / "fakelib").mkdir()
        (self.spiel / "fakelib" / "libScePlayGo.sprx").write_bytes(b"x")
        (self.spiel / "sce_sys" / "playgo-scenario.json").write_text("{}", encoding="utf-8")
        text = self._pruefen()
        self.assertIn("PlayGo", text)
        self.assertNotIn("PlayGo-Dateien gefunden", text)

    def test_veraltete_auswahl_meldet_nichts(self) -> None:
        gui = _gui()
        gui._calc_generation = 8          # inzwischen eine andere Quelle
        gui._quelle_einbauten_pruefen(str(self.spiel), 7)
        self.assertEqual([], gui.zeilen)

    def test_nichts_wird_eingeschaltet(self) -> None:
        (self.spiel / "sce_sys" / "playgo-scenario.json").write_text("{}", encoding="utf-8")
        gui = _gui()
        with mock.patch.object(APP.PS5ConverterGUI, "_playgo_einschalten") as einschalten:
            gui._quelle_einbauten_pruefen(str(self.spiel), 7)
        einschalten.assert_not_called()


class AnstossTests(unittest.TestCase):
    def test_einmal_je_quelle_und_nicht_im_lauf(self) -> None:
        gui = _gui()
        ordner = tempfile.mkdtemp(prefix="einbau_anstoss_")
        self.addCleanup(shutil.rmtree, ordner, True)
        with mock.patch.object(APP.threading, "Thread") as faden:
            gui._quelle_einbauten_anstossen(ordner, "pack_folder", 7)
            gui._quelle_einbauten_anstossen(ordner, "pack_folder", 8)
            gui._quelle_einbauten_anstossen(ordner, "batch_convert", 9)
            gui.is_running = True
            gui._einbauten_geprueft_fuer = None
            gui._quelle_einbauten_anstossen(ordner, "pack_folder", 10)
        self.assertEqual(1, faden.call_count)


class MarkeDerPruefungTests(unittest.TestCase):
    """Die Pruefung der Einbauten gilt, solange ihre Marke die aktuelle ist - nicht, solange ``_calc_generation`` stimmt.

    ``_on_source_path_changed`` laeuft beim Wechsel der Aufgabe zweimal (sofort und, entprellt, 180 ms spaeter) und zaehlt die Generation
    jedes Mal hoch; der zweite Lauf findet denselben Schluessel und startet keine zweite Pruefung. Die erste galt dann als veraltet:
    Bei einer Quelle, die laenger als 180 ms zu lesen war, gab es weder ``[Pruefung]``-Zeilen noch Haken (Gegenlese 19.11.2026)."""

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="einbau_marke_")
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.gui = _gui()
        self.frei = threading.Event()
        self.addCleanup(self.frei.set)

        def zeilen(src, aktuell=None, haken_gilt=None):
            self.frei.wait(10)
            return ["[Prüfung] %s\n" % Path(src).name] if aktuell is None or aktuell() else None
        self.gui._quelle_einbauten_zeilen = zeilen

    def _faden(self):
        return [t for t in threading.enumerate() if t.name == "quelle-einbauten"]

    def _beenden(self) -> str:
        self.frei.set()
        for t in self._faden():
            t.join(10)
        return "".join(self.gui.zeilen)

    def test_ein_zweiter_lauf_mit_derselben_quelle_macht_die_pruefung_nicht_veraltet(self) -> None:
        self.gui._quelle_einbauten_anstossen(self.ordner, "pack_folder", 7)
        self.gui._calc_generation += 1                       # der zweite Lauf von ``_on_source_path_changed`` (180 ms spaeter)
        self.gui._quelle_einbauten_anstossen(self.ordner, "pack_folder", self.gui._calc_generation)   # gleicher Schluessel: nichts startet
        self.assertEqual(1, len(self._faden()))
        self.assertIn(Path(self.ordner).name, self._beenden(), "die erste Pruefung meldet trotzdem")

    def test_eine_andere_quelle_macht_die_erste_pruefung_veraltet(self) -> None:
        anderer = tempfile.mkdtemp(prefix="einbau_marke_b_")
        self.addCleanup(shutil.rmtree, anderer, True)
        self.gui._quelle_einbauten_anstossen(self.ordner, "pack_folder", 7)
        self.gui._quelle_einbauten_anstossen(anderer, "pack_folder", 8)
        text = self._beenden()
        self.assertNotIn(Path(self.ordner).name, text)
        self.assertIn(Path(anderer).name, text)

    def test_zuruecknehmen_macht_die_laufende_pruefung_veraltet(self) -> None:
        self.gui._quelle_einbauten_anstossen(self.ordner, "pack_folder", 7)
        self.gui._haken_auto_zuruecknehmen()                 # leere Quelle oder eine Aufgabe ohne Einzelspiel
        self.assertEqual("", self._beenden())

    def test_ein_lauf_macht_sie_veraltet(self) -> None:
        self.gui._quelle_einbauten_anstossen(self.ordner, "pack_folder", 7)
        self.gui.is_running = True
        self.assertEqual("", self._beenden())

    def test_ohne_marke_gilt_wie_frueher_die_generation(self) -> None:
        self.frei.set()
        gui = self.gui
        gui._calc_generation = 8
        gui._quelle_einbauten_pruefen(self.ordner, 7)        # ohne Marke, veraltete Generation
        self.assertEqual([], gui.zeilen)
        gui._quelle_einbauten_pruefen(self.ordner, 8)
        self.assertIn(Path(self.ordner).name, "".join(gui.zeilen))

    def test_eine_vorhandene_aber_ungueltige_quelle_nimmt_die_haken_zurueck(self) -> None:
        """Quelle da, aber fuer die Aufgabe nicht brauchbar (ein Ordner bei Aufgabe 2): Der Zweig "Kein gueltiger Quellpfad" von
        ``_on_source_path_changed`` ruft ``_haken_auto_zuruecknehmen`` - fuer Aufgaben ausser Seite 7."""
        import ast
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8-sig")
        funktion = next(f for f in ast.walk(ast.parse(quelle))
                        if isinstance(f, ast.FunctionDef) and f.name == "_on_source_path_changed")
        else_zweig = next(n.orelse for n in ast.walk(funktion) if isinstance(n, ast.If) and n.orelse
                          and any(isinstance(m, ast.AugAssign) and isinstance(m.target, ast.Attribute)
                                  and m.target.attr == "_calc_generation" for m in n.orelse))
        aufrufe = [c.func.attr for s in else_zweig for c in ast.walk(s)
                   if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)]
        self.assertIn("_haken_auto_zuruecknehmen", aufrufe)


if __name__ == "__main__":
    unittest.main()
