# -*- coding: utf-8 -*-
"""Vor einem .ffpfsc/.ffpfs wird auf viele Daten und Texture-Streaming geprueft (Nutzerauftrag 21.10.2026).

Die Grenzen sind Zahlen im Modul; hier wird mit einer Attrappe fuer die Verzeichnisse gerechnet, damit kein Test
50 GiB anlegen muss. Gepruft wird: Urteil, Merkmale, Zeitgrenze, Abbruch, Formatwege - und die Rueckfrage im
Programm (Ja = weiter, Nein = Abbruch, nichts Auffaelliges = keine Frage).
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import streaming_pruefung as sp  # noqa: E402

GIB = sp.GIB


def _baum(struktur):
    """Attrappe: ``{ordner: [(name, ist_ordner, groesse, kind)]}``."""
    def auflisten(ordner):
        return struktur[ordner]
    return auflisten


class UrteilTests(unittest.TestCase):
    def test_wenig_daten_ohne_merkmal_ist_unauffaellig(self):
        b = sp.Befund(groesse=30 * GIB)
        self.assertFalse(b.auffaellig)

    def test_sehr_viele_daten_allein_genuegen(self):
        b = sp.Befund(groesse=sp.GROESSE_VIELE_DATEN)
        self.assertTrue(b.viele_daten)
        self.assertTrue(b.auffaellig)
        self.assertEqual("viele_daten", b.gruende()[0][0])

    def test_streaming_merkmal_zaehlt_erst_mit_nennenswerter_menge(self):
        klein = sp.Befund(groesse=5 * GIB, merkmale={"Unity (.resS)": ["a.resS"]})
        gross = sp.Befund(groesse=25 * GIB, merkmale={"Unity (.resS)": ["a.resS"]})
        self.assertFalse(klein.auffaellig)
        self.assertTrue(gross.auffaellig)
        self.assertEqual("streaming", gross.gruende()[0][0])

    def test_gegenprobe_grenze_genau_darunter(self):
        self.assertFalse(sp.Befund(groesse=sp.GROESSE_VIELE_DATEN - 1).auffaellig)
        self.assertFalse(sp.Befund(groesse=sp.GROESSE_MIT_STREAMING - 1,
                                   merkmale={"x": ["y"]}).auffaellig)


class DurchsehenTests(unittest.TestCase):
    def test_erkennt_endungen_namen_und_ordner(self):
        baum = {
            "w": [("Content", True, 0, "c"), ("StreamingAssets", True, 0, "s"),
                  ("game.exe", False, 1 * GIB, None)],
            "c": [("Textures.pak", False, 2 * GIB, None), ("a.ubulk", False, 20 * GIB, None),
                  ("music_stream.bin", False, 300 * 1024 ** 2, None)],
            "s": [],
        }
        b = sp.durchsehen("w", _baum(baum))
        self.assertEqual(23 * GIB + 300 * 1024 ** 2, b.groesse)
        self.assertIn("Unreal Engine (.ubulk)", b.merkmale)
        self.assertIn("StreamingAssets/", b.merkmale)
        self.assertIn("texture*", b.merkmale)
        self.assertIn("stream*", b.merkmale)
        self.assertTrue(b.streaming)

    def test_kleine_datei_mit_stream_im_namen_zaehlt_nicht(self):
        baum = {"w": [("stream_helper.dll", False, 1024, None)]}
        self.assertEqual({}, sp.durchsehen("w", _baum(baum)).merkmale)

    def test_stoppt_sobald_das_urteil_feststeht(self):
        gesehen = []

        def auflisten(ordner):
            gesehen.append(ordner)
            if ordner == "w":
                return [("a", True, 0, "a"), ("b", True, 0, "b")]
            return [("big.bin", False, 60 * GIB, None)]

        b = sp.durchsehen("w", auflisten)
        self.assertTrue(b.viele_daten)
        self.assertEqual(2, len(gesehen), "Nach dem ersten grossen Ordner steht das Urteil fest.")

    def test_zeitgrenze_macht_unvollstaendig(self):
        zeit = iter(range(0, 100))
        baum = {"w": [("a", True, 0, "a")], "a": [("x", False, 1, None)]}
        b = sp.durchsehen("w", _baum(baum), zeit=0.5, uhr=lambda: float(next(zeit)))
        self.assertFalse(b.vollstaendig)

    def test_abbruch_macht_unvollstaendig(self):
        baum = {"w": [("a", True, 0, "a")], "a": []}
        b = sp.durchsehen("w", _baum(baum), abbruch=lambda: True)
        self.assertFalse(b.vollstaendig)

    def test_nicht_lesbarer_ordner_stoppt_nicht(self):
        def auflisten(ordner):
            if ordner == "w":
                return [("kaputt", True, 0, "k"), ("f", False, 100, None)]
            raise OSError("weg")

        b = sp.durchsehen("w", auflisten)
        self.assertEqual(100, b.groesse)
        self.assertFalse(b.vollstaendig)


class FormatWegeTests(unittest.TestCase):
    def test_ordner_echt_gemessen(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "Content"))
            with open(os.path.join(tmp, "Content", "a.ubulk"), "wb") as fh:
                fh.write(b"x" * 1000)
            b = sp.ordner_pruefen(tmp)
        self.assertEqual(1000, b.groesse)
        self.assertIn("Unreal Engine (.ubulk)", b.merkmale)
        self.assertFalse(b.auffaellig, "Ein kleines Spiel mit einer .ubulk ist kein Fall.")

    def test_datei_nur_groesse_und_untergrenze(self):
        with tempfile.NamedTemporaryFile(suffix=".ffpfsc", delete=False) as fh:
            fh.write(b"y" * 2048)
            pfad = fh.name
        try:
            b = sp.datei_pruefen(pfad)
        finally:
            os.remove(pfad)
        self.assertEqual(2048, b.groesse)
        self.assertTrue(b.nur_dateigroesse)
        self.assertFalse(b.vollstaendig)

    def test_exfat_ohne_leser_faellt_auf_die_dateigroesse_zurueck(self):
        with tempfile.NamedTemporaryFile(suffix=".exfat", delete=False) as fh:
            fh.write(b"z" * 512)
            pfad = fh.name
        try:
            b = sp.exfat_pruefen(pfad, "")
        finally:
            os.remove(pfad)
        self.assertEqual(512, b.groesse)
        self.assertTrue(b.nur_dateigroesse)


class RueckfrageTests(unittest.TestCase):
    """Die Frage im Programm: nur bei den Zielen .ffpfsc/.ffpfs und nur bei einem Treffer.

    Drei Antworten (Nutzerwunsch 21.10.2026): trotzdem erstellen ("weiter"), anderes Format ("anderes") oder
    abbrechen ("abbruch").
    """

    @classmethod
    def setUpClass(cls):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        cls.APP = APP
        cls.M = APP.meldungen

    def _gui(self):
        gui = self.APP.PS5ConverterGUI.__new__(self.APP.PS5ConverterGUI)
        gui._cli_mode = False
        gui._current_language = "de"
        gui._batch_sources = []
        gui._set_status_fluechtig = mock.Mock()
        gui._append_to_log = mock.Mock()
        gui.root = mock.Mock()
        gui._fmt_bytes = lambda n: "%d B" % n
        gui._get_target_options = lambda mode, src="": ("ffpfsc", "ffpfs", "exfat", "ffpkg")
        gui._validate_requested_conversion = lambda mode, src, ziel: ""
        gui._zielformat_label = lambda schluessel, mode="", quelle="": ".%s-Label" % schluessel
        return gui

    def _treffer(self, gui, groesse=60 * GIB):
        gui._ruckler_befund = lambda pfad, zeit: sp.Befund(groesse=groesse)

    def _antwort(self, wert):
        return mock.patch.object(self.M, "frage_streaming", return_value=wert)

    def test_trotzdem_geht_weiter_abbrechen_bricht_ab(self):
        gui = self._gui()
        self._treffer(gui)
        with tempfile.TemporaryDirectory() as tmp:
            with self._antwort(self.M.STREAMING_TROTZDEM) as frage:
                self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc"))
            frage.assert_called_once()
            with self._antwort(self.M.STREAMING_ABBRUCH):
                self.assertEqual(("abbruch", ""), gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfs"))

    def test_anderes_format_wird_gewaehlt_und_zurueckgegeben(self):
        gui = self._gui()
        self._treffer(gui)
        gui._auswahl_dialog = mock.Mock(return_value=".exfat-Label")
        with tempfile.TemporaryDirectory() as tmp, self._antwort(self.M.STREAMING_ANDERES):
            self.assertEqual(("anderes", "exfat"), gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc"))
        angebot = gui._auswahl_dialog.call_args.args[2]
        self.assertEqual([".exfat-Label", ".ffpkg-Label"], angebot,
                         "Angeboten werden alle Formate ausser .ffpfsc und .ffpfs.")

    def test_abgebrochene_formatwahl_fuehrt_zur_frage_zurueck(self):
        gui = self._gui()
        self._treffer(gui)
        gui._auswahl_dialog = mock.Mock(return_value="")
        antworten = iter([self.M.STREAMING_ANDERES, self.M.STREAMING_ABBRUCH])
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(self.M, "frage_streaming", side_effect=lambda *a, **k: next(antworten)) as frage:
            self.assertEqual(("abbruch", ""), gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc"))
        self.assertEqual(2, frage.call_count, "Nach der abgebrochenen Wahl wird erneut gefragt.")

    def test_ohne_alternative_gibt_es_nur_zwei_wege(self):
        gui = self._gui()
        self._treffer(gui)
        gui._validate_requested_conversion = lambda mode, src, ziel: "nicht moeglich"
        with tempfile.TemporaryDirectory() as tmp, self._antwort(self.M.STREAMING_TROTZDEM) as frage:
            gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc")
        self.assertIs(False, frage.call_args.kwargs["mit_alternative"])

    def test_text_nennt_format_spiel_und_grund(self):
        gui = self._gui()
        self._treffer(gui)
        with tempfile.TemporaryDirectory() as tmp, self._antwort(self.M.STREAMING_TROTZDEM) as frage:
            gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc")
        titel, text = frage.call_args.args[1:3]
        self.assertEqual("Ruckler möglich", titel)
        self.assertIn(".ffpfsc", text)
        self.assertIn(os.path.basename(tmp), text)
        self.assertIn("sehr viele Daten", text)
        self.assertIn("Wie soll es weitergehen?", text)

    def test_andere_ziele_und_aufgaben_fragen_nicht(self):
        gui = self._gui()
        self._treffer(gui)
        with tempfile.TemporaryDirectory() as tmp, self._antwort(self.M.STREAMING_ABBRUCH) as frage:
            for ziel in ("exfat", "ffpkg", "folder"):
                self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage("pack_folder", tmp, ziel))
            self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage("inspect", tmp, "ffpfsc"))
            frage.assert_not_called()

    def test_ohne_treffer_keine_frage(self):
        gui = self._gui()
        self._treffer(gui, groesse=1 * GIB)
        with tempfile.TemporaryDirectory() as tmp, self._antwort(self.M.STREAMING_ABBRUCH) as frage:
            self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc"))
            frage.assert_not_called()

    def test_kommandozeile_fragt_nie(self):
        gui = self._gui()
        gui._cli_mode = True
        self._treffer(gui)
        with tempfile.TemporaryDirectory() as tmp, self._antwort(self.M.STREAMING_ABBRUCH) as frage:
            self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage("pack_folder", tmp, "ffpfsc"))
            frage.assert_not_called()

    def test_sammelkonvertierung_eine_frage_mit_liste(self):
        gui = self._gui()
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            gui._batch_sources = [a, b]
            gui._ruckler_befund = lambda pfad, zeit: sp.Befund(groesse=60 * GIB if pfad == a else GIB)
            with self._antwort(self.M.STREAMING_TROTZDEM) as frage:
                self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage("batch_convert", "", "ffpfsc"))
            frage.assert_called_once()
            text = frage.call_args.args[2]
            self.assertIn("1 von 2", text)
            self.assertIn(os.path.basename(a), text)
            self.assertNotIn(os.path.basename(b), text)

    def test_paketfenster_nutzt_nur_groessen_und_reicht_die_alternativen_durch(self):
        gui = self._gui()
        gui._auswahl_dialog = mock.Mock(return_value="Dump")
        alternativen = [("dump", "Dump"), ("exfat", "exFAT")]
        with self._antwort(self.M.STREAMING_ANDERES) as frage:
            self.assertEqual(("anderes", "dump"), gui._ruckler_rueckfrage_groessen(
                [("Spiel", 70 * GIB)], "ffpfsc", parent=None, alternativen=alternativen))
            self.assertEqual(("weiter", ""), gui._ruckler_rueckfrage_groessen(
                [("Klein", GIB)], "ffpfsc", parent=None, alternativen=alternativen))
        frage.assert_called_once()
        self.assertIn("mindestens", frage.call_args.args[2])

    def test_aufgabe_stellt_das_andere_format_ein_und_beginnt_von_vorn(self):
        """``_launch_task`` stellt das gewaehlte Format ein und ruft sich selbst neu auf."""
        import ast
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        funktion = next(n for n in ast.walk(ast.parse(quelle))
                        if isinstance(n, ast.FunctionDef) and n.name == "_launch_task")
        text = ast.get_source_segment(quelle, funktion)
        self.assertIn('aktion == "anderes"', text)
        self.assertIn("self.target_format.set(", text)
        self.assertLess(text.index("_ruckler_rueckfrage"), text.index("_run_preflight_checks"))
        self.assertLess(text.index("_ampr_originale_klaeren"), text.index("_ruckler_rueckfrage"))


class FrageFensterTests(unittest.TestCase):
    """Das Fenster: drei Knoepfe, mit Alternative; sonst zwei."""

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        cls.tk = tk
        cls.root = tk._default_root or tk.Tk()

    def _frage(self, mit_alternative, antwort):
        from ps5_validator.ui import meldungen
        gebaut = {}

        class _Attrappe:
            def __init__(self, gui, art, titel, text, eltern=None, vorgabe="", knoepfe_eigen=None):
                gebaut.update(art=art, vorgabe=vorgabe, knoepfe=knoepfe_eigen)

            def zeigen(self):
                return antwort

        gui = mock.Mock()
        with mock.patch.object(meldungen, "Meldung", _Attrappe):
            ergebnis = meldungen.frage_streaming(gui, "T", "X", mit_alternative=mit_alternative, eltern=object())
        return ergebnis, gebaut

    def test_drei_knoepfe_mit_vorgabe_anderes_format(self):
        ergebnis, gebaut = self._frage(True, "other")
        self.assertEqual("other", ergebnis)
        self.assertEqual(["yes", "other", "cancel"], [a for a, _t in gebaut["knoepfe"]])
        self.assertEqual("other", gebaut["vorgabe"])

    def test_zwei_knoepfe_ohne_alternative_vorgabe_abbrechen(self):
        ergebnis, gebaut = self._frage(False, "yes")
        self.assertEqual("yes", ergebnis)
        self.assertEqual(["yes", "cancel"], [a for a, _t in gebaut["knoepfe"]])
        self.assertEqual("cancel", gebaut["vorgabe"])

    def test_alles_andere_gilt_als_abbruch(self):
        for roh in (None, "no", "", "cancel"):
            self.assertEqual("cancel", self._frage(True, roh)[0], repr(roh))

    def test_knopftexte_in_allen_sprachen(self):
        from ps5_validator.ui import meldungen
        for schluessel in ("trotzdem", "anderes_format", "abbrechen"):
            self.assertEqual({"de", "en", "es", "it", "fr"}, set(meldungen.TEXTE[schluessel]))

    def test_echtes_fenster_hat_drei_knoepfe_und_antwortet(self):
        """Mit echtem Tk: Der mittlere Knopf liefert "other"."""
        from ps5_validator.ui import meldungen

        gui = mock.Mock()
        gui.root = self.root
        gui._COLORS = {"bg_main": "#202020", "fg_primary": "#ffffff", "fg_accent": "#44aaff",
                       "fg_warning": "#ffaa00", "error_btn": "#ff4444"}
        gui._current_language = "de"
        gui._pw = mock.Mock()
        gui._pw.F = "Segoe UI"
        gui._pw.pt = lambda n: n
        knoepfe = {}

        def _knopf(eltern, text="", command=None, style=""):
            b = self.tk.Button(eltern, text=text, command=command)
            knoepfe[text] = b
            return b

        gui._pw.Button = _knopf
        gui._apply_icon_to_toplevel = lambda w: None
        m = meldungen.Meldung(gui, "askyesnocancel", "T", "Text", eltern=self.root, vorgabe="other",
                              knoepfe_eigen=(("yes", "trotzdem"), ("other", "anderes_format"),
                                             ("cancel", "abbrechen")))
        self.assertEqual({"Trotzdem erstellen", "Anderes Format wählen", "Abbrechen"}, set(knoepfe))
        knoepfe["Anderes Format wählen"].invoke()
        self.assertEqual("other", m.antwort)


if __name__ == "__main__":
    unittest.main()
