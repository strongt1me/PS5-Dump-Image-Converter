# -*- coding: utf-8 -*-
"""Meldungen und Rueckfragen in Pillenoptik (``ps5_validator/ui/meldungen.py``, Nutzer 06.10.2026).

Kern: Jede Rueckfrage liefert genau, was ``tkinter.messagebox`` geliefert haette - die rund 290 Aufrufer im
Programm verlassen sich darauf. Dazu: Umleiten und Wiederherstellen, Rueckfall auf den Systemdialog, nur der
echte Programmstart leitet um (Kommandozeile und Testreihe nicht).
"""
from __future__ import annotations

import sys
import threading
import tkinter as tk
import unittest
from pathlib import Path
from tkinter import messagebox
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import meldungen                      # noqa: E402


class ErgebnisTests(unittest.TestCase):
    """Dieselben Rueckgabewerte wie tkinter.messagebox."""

    def test_meldungen_geben_ok(self) -> None:
        for art in ("showinfo", "showwarning", "showerror"):
            self.assertEqual("ok", meldungen.ergebnis(art, "ok"))
            self.assertEqual("ok", meldungen.ergebnis(art, None))

    def test_ja_nein(self) -> None:
        self.assertIs(True, meldungen.ergebnis("askyesno", "yes"))
        self.assertIs(False, meldungen.ergebnis("askyesno", "no"))
        self.assertIs(False, meldungen.ergebnis("askyesno", None))

    def test_frage_als_text(self) -> None:
        self.assertEqual("yes", meldungen.ergebnis("askquestion", "yes"))
        self.assertEqual("no", meldungen.ergebnis("askquestion", "no"))

    def test_ja_nein_abbrechen(self) -> None:
        self.assertIs(True, meldungen.ergebnis("askyesnocancel", "yes"))
        self.assertIs(False, meldungen.ergebnis("askyesnocancel", "no"))
        self.assertIsNone(meldungen.ergebnis("askyesnocancel", "cancel"))
        self.assertIsNone(meldungen.ergebnis("askyesnocancel", None))

    def test_ok_abbrechen_und_wiederholen(self) -> None:
        self.assertIs(True, meldungen.ergebnis("askokcancel", "ok"))
        self.assertIs(False, meldungen.ergebnis("askokcancel", "cancel"))
        self.assertIs(True, meldungen.ergebnis("askretrycancel", "retry"))
        self.assertIs(False, meldungen.ergebnis("askretrycancel", "cancel"))

    def test_fenster_x_heisst_abbrechen_oder_nein(self) -> None:
        self.assertEqual("cancel", meldungen._ohne_antwort("askyesnocancel"))
        self.assertEqual("no", meldungen._ohne_antwort("askyesno"))
        self.assertEqual("ok", meldungen._ohne_antwort("showinfo"))

    def test_jede_art_von_tkinter_ist_abgedeckt(self) -> None:
        self.assertEqual({"showinfo", "showwarning", "showerror", "askquestion", "askyesno", "askokcancel",
                          "askyesnocancel", "askretrycancel"}, set(meldungen.ARTEN))


class FensterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
        cls.root = tk._default_root or tk.Tk()
        cls.root.withdraw()
        cls.app = APP.PS5ConverterGUI(cls.root)
        cls.app._current_language = "de"
        cls.root.withdraw()
        for kind in cls.root.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    def _meldung(self, art: str, **optionen):
        m = meldungen.Meldung(self.app, art, "Titel", "Text", **optionen)
        self.addCleanup(lambda: m.win.winfo_exists() and m.win.destroy())
        return m

    def test_knoepfe_je_art_und_vorgabe_hervorgehoben(self) -> None:
        m = self._meldung("askyesnocancel")
        self.assertEqual({"yes", "no", "cancel"}, set(m.knoepfe))
        self.assertEqual("yes", m._vorgabe)

    def test_vorgabe_aus_der_option_default(self) -> None:
        self.assertEqual("no", self._meldung("askyesno", vorgabe=messagebox.NO)._vorgabe)

    def test_klick_auf_nein_gibt_false(self) -> None:
        m = self._meldung("askyesno")
        m.knoepfe["no"].invoke() if hasattr(m.knoepfe["no"], "invoke") else m._fertig("no")
        self.assertIs(False, meldungen.ergebnis("askyesno", m.antwort))
        self.assertFalse(m.win.winfo_exists())

    def test_englische_knoepfe(self) -> None:
        with mock.patch.object(self.app, "_current_language", "en"):
            m = self._meldung("askyesno")
        self.assertIn("Yes", [meldungen.TEXTE[k]["en"] for k in ("ja",)])
        self.assertEqual({"yes", "no"}, set(m.knoepfe))


class UmleitungTests(unittest.TestCase):
    def tearDown(self) -> None:
        meldungen.aufheben()
        meldungen._ORIGINALE.clear()

    def test_einrichten_leitet_um_aufheben_stellt_her(self) -> None:
        vorher = messagebox.askyesno
        gui = mock.Mock()
        meldungen.einrichten(gui)
        self.assertIsNot(vorher, messagebox.askyesno)
        with mock.patch.object(meldungen, "zeigen", return_value=True) as zeigen:
            self.assertIs(True, messagebox.askyesno("T", "M", parent=None))
        zeigen.assert_called_once_with(gui, "askyesno", "T", "M", parent=None)
        meldungen.aufheben()
        self.assertIs(vorher, messagebox.askyesno)

    def test_aus_einem_faden_gilt_der_systemdialog(self) -> None:
        original = mock.Mock(return_value=True)
        meldungen._ORIGINALE["askyesno"] = original
        ergebnis = {}
        faden = threading.Thread(target=lambda: ergebnis.update(
            wert=meldungen.zeigen(mock.Mock(), "askyesno", "T", "M")))
        faden.start()
        faden.join(5)
        self.assertIs(True, ergebnis["wert"])
        original.assert_called_once_with("T", "M")

    def test_ohne_hauptfenster_gilt_der_systemdialog(self) -> None:
        original = mock.Mock(return_value="ok")
        meldungen._ORIGINALE["showinfo"] = original
        self.assertEqual("ok", meldungen.zeigen(None, "showinfo", "T", "M"))
        original.assert_called_once_with("T", "M")


class StartTests(unittest.TestCase):
    def test_nur_der_echte_programmstart_leitet_um(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertEqual(1, quelle.count("meldungen.einrichten(app)"))
        stelle = quelle.index("meldungen.einrichten(app)")
        davor = quelle[max(0, stelle - 600):stelle]
        self.assertIn("# --- GUI aufbauen ---", davor)
        self.assertNotIn("_cli_mode = True", quelle[stelle - 300:stelle + 300])


if __name__ == "__main__":
    unittest.main()
