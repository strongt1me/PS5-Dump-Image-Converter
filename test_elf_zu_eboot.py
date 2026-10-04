# -*- coding: utf-8 -*-
"""WEITERE TOOLS "ELF -> EBOOT.BIN" (Nutzerwunsch 04.10.2026).

Das Fenster verpackt ein ELF mit ``ps5_backport.elf_signieren`` (Nachbau von
make_fself) und meldet Erfolg erst, wenn die geschriebene Datei mit
``read_self`` wieder als SELF erscheint. Diese Tests laufen den ganzen Weg
mit ersetzten Dialogen durch.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import ps5_backport as bp
from ps5_validator.utils.i18n import STRINGS
from ps5_validator.utils.self_reader import CONTAINER_ELF, read_self
from test_backport import baue_elf


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui.root = None
    gui._current_language = "de"
    gui._get_source_dialog_initial_dir = lambda: ""
    gui._remember_source_dialog_path = lambda _p: None
    gui._set_status = mock.Mock()
    return gui


class MenueTests(unittest.TestCase):
    def test_eintrag_steht_im_menue(self) -> None:
        self.assertIn(("titlebar.elf_eboot", "_show_elf_zu_eboot"),
                      APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES)

    def test_alle_texte_zweisprachig(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        rumpf = quelle[quelle.index("def _show_elf_zu_eboot"):]
        rumpf = rumpf[:rumpf.index("\n    def ", 10)]
        import re
        schluessel = set(re.findall(r'"(elf_eboot\.[a-z_]+)"', rumpf))
        self.assertGreaterEqual(len(schluessel), 12)
        for s in schluessel:
            with self.subTest(schluessel=s):
                self.assertTrue(STRINGS[s]["de"] and STRINGS[s]["en"])


class AblaufTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def _lauf(self, quelle: str, ziel: str):
        gui = _gui()
        with mock.patch.object(APP.filedialog, "askopenfilename", return_value=quelle), \
             mock.patch.object(APP.filedialog, "asksaveasfilename", return_value=ziel), \
             mock.patch.object(APP.messagebox, "showinfo") as info, \
             mock.patch.object(APP.messagebox, "showerror") as fehler:
            gui._show_elf_zu_eboot()
        return info, fehler

    def test_elf_wird_zur_lesbaren_eboot(self) -> None:
        quelle = os.path.join(self.ordner, "app.elf")
        ziel = os.path.join(self.ordner, "eboot.bin")
        elf = baue_elf()
        Path(quelle).write_bytes(elf)
        info, fehler = self._lauf(quelle, ziel)
        fehler.assert_not_called()
        info.assert_called_once()
        roh = Path(ziel).read_bytes()
        self.assertEqual(roh, bp.elf_signieren(elf))
        self.assertEqual(bp.dateityp(roh), bp.TYP_SELF)
        self.assertNotEqual(read_self(ziel).container, CONTAINER_ELF)
        self.assertFalse(os.path.exists(ziel + ".tmp"))
        # Rundweg: das eingebettete ELF ist wieder das Original (ohne Abschnittskoepfe).
        self.assertEqual(bp.self_zu_elf(roh)[:4], b"\x7fELF")

    def test_self_wird_abgewiesen_ohne_zu_schreiben(self) -> None:
        quelle = os.path.join(self.ordner, "schon.bin")
        ziel = os.path.join(self.ordner, "eboot.bin")
        Path(quelle).write_bytes(bp.elf_signieren(baue_elf()))
        info, fehler = self._lauf(quelle, ziel)
        info.assert_not_called()
        fehler.assert_called_once()
        self.assertIn("bereits ein SELF", fehler.call_args[0][1])
        self.assertFalse(os.path.exists(ziel))

    def test_kein_elf_wird_abgewiesen(self) -> None:
        quelle = os.path.join(self.ordner, "text.elf")
        ziel = os.path.join(self.ordner, "eboot.bin")
        Path(quelle).write_bytes(b"kein elf" * 20)
        info, fehler = self._lauf(quelle, ziel)
        info.assert_not_called()
        self.assertIn("kein ELF", fehler.call_args[0][1])
        self.assertFalse(os.path.exists(ziel))

    def test_elf_ohne_programmkoepfe_meldet_fehler(self) -> None:
        quelle = os.path.join(self.ordner, "leer.elf")
        ziel = os.path.join(self.ordner, "eboot.bin")
        Path(quelle).write_bytes(b"\x7fELF" + bytes(4092))
        info, fehler = self._lauf(quelle, ziel)
        info.assert_not_called()
        fehler.assert_called_once()
        self.assertFalse(os.path.exists(ziel))

    def test_abbruch_im_speicherdialog_schreibt_nichts(self) -> None:
        quelle = os.path.join(self.ordner, "app.elf")
        Path(quelle).write_bytes(baue_elf())
        info, fehler = self._lauf(quelle, "")
        info.assert_not_called()
        fehler.assert_not_called()
        self.assertEqual(sorted(os.listdir(self.ordner)), ["app.elf"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
