# -*- coding: utf-8 -*-
"""Vier Befunde aus einem echten Diagnosebericht vom 23.08.2026 (v1.8.92).

Der Bericht meldete oben "Darstellung: keine Auffaelligkeit" - und trug im
Abschnitt "Protokolldatei" trotzdem Zeilen, die siebzehnmal hintereinander
dasselbe sagten. Das sah nach einem Programmfehler aus. Es war keiner: Die
**Testreihe** schrieb in dieselbe Datei wie das laufende Programm des Nutzers.

Beim Nachgehen kamen drei weitere Dinge heraus. Diese Datei haelt alle vier
fest, damit keines davon unbemerkt zurueckkehrt.
"""
from __future__ import annotations

import logging
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    # Vorhandene Wurzel weiterbenutzen: Je Prozess darf es nur eine geben.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class ProtokollTests(unittest.TestCase):
    """Das Protokoll des Nutzers gehoert dem Nutzer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def test_ein_testlauf_wird_als_solcher_erkannt(self) -> None:
        """Genau hier laeuft einer - also muss die Erkennung anschlagen."""
        self.assertTrue(self.haupt._IM_TESTLAUF)

    def test_kein_dateihandler_im_testlauf(self) -> None:
        """Der Kern der Sache.

        Gemessen hatte eine einzige Testdatei 114 Zeilen in
        ``%TEMP%\\ps5converter.log`` geschrieben. Ueber zwei Wochen kamen so
        322.195 Zeilen und 22 MB zusammen, und der Diagnosebericht zeigte
        Testrauschen statt der Sitzung des Nutzers.
        """
        datei_handler = [h for h in self.haupt.logger.handlers
                         if isinstance(h, logging.FileHandler)]
        self.assertEqual(
            datei_handler, [],
            "Im Testlauf darf kein Datei-Handler am Logger haengen - sonst "
            "schreiben die Tests in das Protokoll des Nutzers.")

    def test_die_exe_behaelt_ihr_protokoll(self) -> None:
        """Die Sperre darf nur Testlaeufe treffen, nie die Auslieferung.

        ``sys.frozen`` ist in der gebauten EXE gesetzt. Ohne diesen Teil der
        Bedingung wuerde ein beliebiger Import von ``unittest`` im fertigen
        Programm das Protokoll des Nutzers stilllegen.
        """
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertTrue(
            '_IM_TESTLAUF = (not getattr(sys, "frozen", False))' in quelle,
            "Die Testerkennung muss die gebaute EXE ausdruecklich ausnehmen.")

    def test_das_protokoll_rollt_um(self) -> None:
        """22 MB in zwei Wochen, weil nichts begrenzt war."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertTrue("RotatingFileHandler" in quelle)
        self.assertTrue("maxBytes=4 * 1024 * 1024" in quelle)
        self.assertTrue("backupCount=3" in quelle)


class DiagnoseMeldetNurEchtesTests(unittest.TestCase):
    """Eine falsche Fehlmeldung ist schlimmer als keine."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls.quelle = HAUPTDATEI.read_text(encoding="utf-8")

    def test_keine_ungenutzte_bibliothek_in_der_pruefliste(self) -> None:
        """Der Bericht meldete "requests: fehlt".

        Das Programm benutzt ``requests`` nirgends - es geht ueber
        ``urllib.request`` ins Netz. Dasselbe galt fuer ``paramiko``. Wer den
        Bericht liest, sucht daraufhin einen Schaden, den es nicht gibt.
        """
        geprueft = self.haupt.PS5ConverterGUI._GEPRUEFTE_BIBLIOTHEKEN
        namen = {anzeige for anzeige, _imp, _pypi in geprueft}
        for tot in ("requests", "paramiko"):
            with self.subTest(bibliothek=tot):
                self.assertNotIn(tot, namen)
                # Und die Gegenprobe: wirklich nirgends benutzt.
                self.assertNotIn("import %s" % tot, self.quelle)

    def test_die_wirklich_benutzten_stehen_weiter_drin(self) -> None:
        """Sonst waere die Liste durch Wegstreichen wertlos geworden."""
        namen = {a for a, _i, _p in self.haupt.PS5ConverterGUI._GEPRUEFTE_BIBLIOTHEKEN}
        for gebraucht in ("Pillow", "cryptography", "zstandard", "psutil"):
            with self.subTest(bibliothek=gebraucht):
                self.assertIn(gebraucht, namen)


@unittest.skipUnless(TK_DA, "ohne Tk nicht messbar")
class MausradTests(unittest.TestCase):
    """Ein Fenster darf dem Hauptfenster nicht das Mausrad nehmen."""

    def test_unbind_all_loescht_fremde_bindungen_mit(self) -> None:
        """Die Ursache, festgehalten am nackten Tk.

        ``bind_all`` schreibt in die globale Tabelle ``all``. ``unbind_all``
        loescht dort **alles** fuer diese Sequenz - nicht nur den eigenen
        Eintrag. Diese Pruefung beschreibt das Verhalten von Tk selbst; sie
        schlaegt fehl, falls Tk es einmal aendert, und macht dann sichtbar,
        dass die Umgehung im Programm nicht mehr noetig ist.
        """
        rahmen = tk.Frame(_WURZEL)
        try:
            _WURZEL.bind_all("<MouseWheel>", lambda e: None, add="+")
            self.assertTrue(_WURZEL.tk.call("bind", "all", "<MouseWheel>").strip())
            rahmen.bind_all("<MouseWheel>", lambda e: None)
            rahmen.unbind_all("<MouseWheel>")
            self.assertFalse(
                _WURZEL.tk.call("bind", "all", "<MouseWheel>").strip(),
                "Wenn Tk das repariert hat, darf das Programm wieder "
                "bind_all benutzen.")
        finally:
            _WURZEL.unbind_all("<MouseWheel>")
            rahmen.destroy()

    def test_die_rollflaeche_fasst_die_globale_tabelle_nicht_an(self) -> None:
        """Deshalb bindet sie am Toplevel statt global.

        Die Bindetags eines Widgets sind (Widget, Klasse, Toplevel, all) -
        eine Bindung am Toplevel erreicht jedes Kind des Fensters, ohne die
        globale Tabelle zu beruehren.
        """
        import ast

        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        koerper = None
        for knoten in ast.walk(ast.parse(quelle)):
            if (isinstance(knoten, ast.FunctionDef)
                    and knoten.name == "_build_scrollable_body"):
                koerper = knoten
        self.assertIsNotNone(koerper, "_build_scrollable_body nicht gefunden")

        # Nach den *Aufrufen* suchen, nicht nach dem Wort: Der Kommentar an
        # dieser Stelle erklaert gerade, warum bind_all dort nicht mehr steht.
        gerufen = {k.func.attr for k in ast.walk(koerper)
                   if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)}
        self.assertNotIn("bind_all", gerufen)
        self.assertNotIn("unbind_all", gerufen)
        self.assertIn("winfo_toplevel", gerufen)

    def test_kein_neues_tcl_kommando_je_ueberfahrt(self) -> None:
        """Das alte Muster band bei jedem <Enter> ein frisches Lambda.

        Gemessen: +1 Tcl-Kommando je Ueberfahrt, nie wieder freigegeben.
        """
        haupt = _lade_hauptprogramm()
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        try:
            aussen, _innen = haupt.PS5ConverterGUI._build_scrollable_body(
                _SelbstAttrappe(), fenster)
            aussen.pack()
            fenster.update_idletasks()
            vorher = len(_WURZEL._tclCommands or [])
            leinwand = [k for k in aussen.winfo_children()
                        if isinstance(k, tk.Canvas)][0]
            for _ in range(25):
                leinwand.event_generate("<Enter>")
                leinwand.event_generate("<Leave>")
            fenster.update_idletasks()
            self.assertEqual(len(_WURZEL._tclCommands or []), vorher)
        finally:
            fenster.destroy()


class _SelbstAttrappe:
    """Reicht ``_build_scrollable_body`` genau das, was es anfasst."""

    _COLORS = {"bg_main": "#0d1117"}


if __name__ == "__main__":
    unittest.main(verbosity=2)
