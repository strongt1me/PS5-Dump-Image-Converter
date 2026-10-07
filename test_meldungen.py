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

    def test_die_frage_fuer_alle_liefert_die_vier_antworten(self) -> None:
        for knopf, erwartet in (("yes", "yes"), ("no", "no"), ("yes_all", "yes_all"), ("no_all", "no_all")):
            with self.subTest(knopf=knopf):
                m = meldungen.Meldung(self.app, "askyesno", "T", "X", knoepfe_eigen=meldungen.FUER_ALLE)
                self.addCleanup(lambda m=m: m.win.winfo_exists() and m.win.destroy())
                self.assertEqual({"yes", "no", "yes_all", "no_all"}, set(m.knoepfe))
                m.win.after(30, lambda k=knopf, m=m: m._fertig(k))
                with mock.patch.object(meldungen, "_blinken"):
                    self.assertEqual(erwartet, m.zeigen())

    def test_das_fenster_x_gilt_bei_der_frage_fuer_alle_als_nein(self) -> None:
        m = meldungen.Meldung(self.app, "askyesno", "T", "X", knoepfe_eigen=meldungen.FUER_ALLE)
        self.addCleanup(lambda: m.win.winfo_exists() and m.win.destroy())
        m.win.after(30, lambda: m._fertig(meldungen._ohne_antwort("askyesno")))
        with mock.patch.object(meldungen, "_blinken"):
            self.assertEqual("no", m.zeigen())

    def test_param_frage_im_stapel_merkt_die_antwort_fuer_alle(self) -> None:
        """Anwenderbericht 07.10.2026: Bei zwoelf Titeln wurde bei jedem einzeln gefragt."""
        app = self.app
        app._param_batch_aktiv, app._param_antworten = True, {}
        self.addCleanup(lambda: setattr(app, "_param_batch_aktiv", False))
        with mock.patch.object(meldungen, "frage_fuer_alle", return_value="yes_all") as frage,                 mock.patch.object(app, "_append_to_log") as protokoll:
            self.assertTrue(app._param_frage("Titel A", "Text"))
            self.assertTrue(app._param_frage("Titel A", "Text"))
            self.assertTrue(app._param_frage("Titel A", "Text"))
            self.assertEqual(1, frage.call_count, "Nach \"Ja, fuer alle\" wird nicht mehr gefragt.")
            self.assertEqual(2, protokoll.call_count)
            frage.return_value = "no"
            self.assertFalse(app._param_frage("Titel B", "Text"))
            self.assertFalse(app._param_frage("Titel B", "Text"))
            self.assertEqual(3, frage.call_count, "Ein einfaches Nein wird nicht gemerkt.")
            frage.return_value = "no_all"
            self.assertFalse(app._param_frage("Titel C", "Text"))
            self.assertFalse(app._param_frage("Titel C", "Text"))
            self.assertEqual(4, frage.call_count, "Auch \"Nein, fuer alle\" wird gemerkt.")

    def test_die_online_frage_bleibt_im_stapel_einzeln(self) -> None:
        app = self.app
        app._param_batch_aktiv, app._param_antworten = True, {}
        self.addCleanup(lambda: setattr(app, "_param_batch_aktiv", False))
        with mock.patch.object(meldungen, "frage_fuer_alle") as alle,                 mock.patch.object(app, "_ask_yesno_threadsafe", return_value=True) as einzel:
            self.assertTrue(app._param_frage("Online", "Text", online=True))
            alle.assert_not_called()
            einzel.assert_called_once()

    def test_ohne_stapel_gilt_die_einfache_frage(self) -> None:
        app = self.app
        app._param_batch_aktiv = False
        with mock.patch.object(meldungen, "frage_fuer_alle") as alle,                 mock.patch.object(app, "_ask_yesno_threadsafe", return_value=False) as einzel:
            self.assertFalse(app._param_frage("Titel", "Text"))
            alle.assert_not_called()
            einzel.assert_called_once()

    def test_die_meldung_kommt_nach_vorn(self) -> None:
        """Meldung 07.10.2026: Eine Rueckfrage aus einem langen Lauf stand hinter anderen Fenstern."""
        m = self._meldung("askyesno")
        with mock.patch.object(meldungen, "_blinken") as blinken:
            m._nach_vorn()
        self.assertTrue(m.win.attributes("-topmost"))
        blinken.assert_called_once_with(self.app.root)

    def test_eine_offene_meldung_wird_gezaehlt(self) -> None:
        m = self._meldung("askyesno")
        gesehen: list[int] = []

        def antworten() -> None:
            gesehen.append(meldungen.offene_meldungen())
            m._fertig("yes")

        vorher = meldungen.offene_meldungen()
        m.win.after(50, antworten)
        with mock.patch.object(meldungen, "_blinken"):
            m.zeigen()
        self.assertEqual([vorher + 1], gesehen)
        self.assertEqual(vorher, meldungen.offene_meldungen())

    def test_der_stillstandwaechter_kennt_offene_meldungen(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        anfang = quelle.index("def _stillstand_uhr(self")
        rumpf = quelle[anfang:quelle.index("    def _balken_anzeigewert", anfang)]
        self.assertIn("meldungen.offene_meldungen()", rumpf)
        self.assertLess(rumpf.index("meldungen.offene_meldungen()"), rumpf.index("_stapelabzug_bei_stillstand(seit)"))

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
