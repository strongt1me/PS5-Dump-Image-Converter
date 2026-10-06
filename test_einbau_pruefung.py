# -*- coding: utf-8 -*-
"""Pruefung beim Waehlen einer Quelle: was ist schon eingebaut, braucht das Spiel PlayGo? (Nutzer 06.10.2026)

An echten kleinen Dump-Ordnern im Temp-Verzeichnis: AMPR EMU/BACKPORT/PlayGo erkannt, "nichts eingebaut" samt
PlayGo-Empfehlung, wenn das Spiel PlayGo-Dateien traegt. Nichts wird eingeschaltet.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
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
        self.assertIn("PlayGo empfohlen", text)
        self.assertIn("playgo-scenario.json", text)

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
        self.assertNotIn("PlayGo empfohlen", text)

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


if __name__ == "__main__":
    unittest.main()
