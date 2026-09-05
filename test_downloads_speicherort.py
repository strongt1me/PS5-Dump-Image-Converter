# -*- coding: utf-8 -*-
"""Downloads-Verwaltung: was ohne gesetzten Speicherort passiert.

Befunde M013-M016 vom 04.09.2026.

Der Speicherort steht in den Einstellungen und kann dort auch **leer** sein -
"Zuruecksetzen" im Einstellungsdialog macht ihn leer, auch waehrend das
Download-Fenster offen steht. Ohne ihn liefert ``ps5_downloads.zielpfad`` aber
keinen Fehler, sondern einen **relativen** Pfad::

    >>> zielpfad("", ART_UPDATE, "spiel.pkg")
    'PS5 Spiele Updates\\\\spiel.pkg'

Wer damit schreibt, legt den Ordner unter dem Arbeitsverzeichnis an. Genau das
tat "Umsortieren": Es verschob die fertige Datei dorthin, wo sie niemand sucht.

Dazu zwei kleinere Sachen aus derselben Ecke: Der Knopf "Ordner oeffnen" tat
in drei Faellen wortlos nichts, und der Tooltip am Ueberwachungshaken
behauptete das Gegenteil dessen, was das Programm tut.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("downloads_speicherort")

from ps5_validator.utils import ps5_downloads as dl         # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class LeererSpeicherortTests(unittest.TestCase):
    """Das Helfermodul sucht nicht im Arbeitsverzeichnis herum."""

    def test_zielpfad_ist_ohne_basis_relativ(self):
        """Die Vorbedingung des Befunds - gemessen, nicht angenommen."""
        pfad = dl.zielpfad("", dl.ART_UPDATE, "spiel.pkg")
        self.assertFalse(os.path.isabs(pfad),
                         "Wenn das absolut waere, gaebe es den Befund nicht.")

    def test_vorhandene_dateien_liefert_ohne_basis_nichts(self):
        """Sonst listet es, was zufaellig im Arbeitsverzeichnis liegt."""
        for leer in ("", "   ", None):
            with self.subTest(basis=leer):
                self.assertEqual([], dl.vorhandene_dateien(leer))

    def test_bereits_vorhanden_sucht_ohne_basis_nicht(self):
        for leer in ("", "   ", None):
            with self.subTest(basis=leer):
                self.assertEqual("", dl.bereits_vorhanden(leer, "spiel.pkg"))

    def test_mit_basis_wird_weiterhin_gefunden(self):
        """Die Gegenrichtung - sonst waere die Sperre oben nur blind."""
        with tempfile.TemporaryDirectory(prefix="dl_basis_") as basis:
            ordner = dl.zielordner(basis, dl.ART_UPDATE)
            os.makedirs(ordner, exist_ok=True)
            name = "UP0001-PPSA99999_00-A0000000000000000_0-A0001.pkg"
            with io.open(os.path.join(ordner, name), "wb") as fh:
                fh.write(b"x" * 32)
            self.assertTrue(dl.bereits_vorhanden(basis, name))
            self.assertEqual(1, len(dl.vorhandene_dateien(basis)))


class _Quelltext(unittest.TestCase):
    """Gemeinsame Grundlage: der Syntaxbaum des Fensters."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()
        cls.baum = ast.parse(cls.quelle)

    def _innere(self, aussen: str, innen: str) -> ast.FunctionDef:
        for k in ast.walk(self.baum):
            if isinstance(k, ast.FunctionDef) and k.name == aussen:
                for j in ast.walk(k):
                    if isinstance(j, ast.FunctionDef) and j.name == innen:
                        return j
                self.fail("%s enthaelt kein %s mehr" % (aussen, innen))
        self.fail("Methode %s gibt es nicht mehr" % aussen)


class SchreibwegeTests(_Quelltext):
    """Jeder Weg, der Dateien verschiebt, prueft den Speicherort vorher."""

    def test_umsortieren_prueft_den_speicherort(self):
        m = self._innere("_show_downloads_manager", "_art_wechseln")
        # Die Pruefung muss VOR der Schleife stehen, sonst verschiebt der
        # erste Durchlauf schon.
        schleifen = [k for k in m.body if isinstance(k, ast.For)]
        self.assertTrue(schleifen, "Die Schleife ueber die Auswahl fehlt.")
        vorher = m.body[:m.body.index(schleifen[0])]
        aufrufe = [getattr(k.func, "attr", "") for stueck in vorher
                   for k in ast.walk(stueck) if isinstance(k, ast.Call)]
        self.assertIn("_download_basis", aufrufe,
                      "Ohne Speicherort verschiebt Umsortieren die Datei in "
                      "einen relativen Pfad unter dem Arbeitsverzeichnis.")
        rueckgaben = [k for stueck in vorher for k in ast.walk(stueck)
                      if isinstance(k, ast.Return)]
        self.assertTrue(rueckgaben,
                        "Es wird zwar geholt, aber nicht abgebrochen.")

    def test_umsortieren_holt_den_ort_nur_einmal(self):
        """Frueher stand der Aufruf IN der Schleife - je Eintrag einmal."""
        m = self._innere("_show_downloads_manager", "_art_wechseln")
        schleifen = [k for k in m.body if isinstance(k, ast.For)]
        drin = [k for k in ast.walk(schleifen[0]) if isinstance(k, ast.Call)
                and getattr(k.func, "attr", "") == "_download_basis"]
        self.assertEqual([], [k.lineno for k in drin])


class OrdnerOeffnenTests(_Quelltext):
    """Der Knopf sagt, warum er nichts tut."""

    def test_jeder_ausgang_meldet_sich(self):
        m = self._innere("_show_downloads_manager", "_ordner_oeffnen")
        meldungen = [k for k in ast.walk(m) if isinstance(k, ast.Call)
                     and getattr(k.func, "attr", "") in
                     ("showwarning", "showerror", "showinfo")]
        self.assertGreaterEqual(
            len(meldungen), 3,
            "Drei stumme Wege gab es: kein Ort, Ordner weg, Dateimanager "
            "startet nicht. Jeder braucht eine Meldung.")

    def test_ein_fehlender_ort_wird_erst_angeboten(self):
        """Meckern hilft niemandem - erst den Ordner anbieten."""
        m = self._innere("_show_downloads_manager", "_ordner_oeffnen")
        aufrufe = [getattr(k.func, "attr", "") for k in ast.walk(m)
                   if isinstance(k, ast.Call)]
        self.assertIn("_download_basis_waehlen", aufrufe)


class TooltipTests(unittest.TestCase):
    """Der Text am Haken muss sagen, was das Programm tut."""

    def test_er_behauptet_nicht_mehr_das_gegenteil(self):
        """Die Ueberwachung laeuft nach dem Schliessen weiter.

        So ausdruecklich gewuenscht - der Docstring von
        _zwischenablage_tick haelt fest: "Die erste Fassung endete mit dessen
        Schliessen; der Nutzer hat ausdruecklich das Gegenteil verlangt."
        Der Tooltip begann trotzdem mit "Solange dieses Fenster offen ist".
        """
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = STRINGS["downloads.watch_hint"][sprache]
                self.assertNotIn("Solange dieses Fenster offen ist", text)
                self.assertNotIn("While this window is open", text)

    def test_er_sagt_was_wirklich_gilt(self):
        de = STRINGS["downloads.watch_hint"]["de"]
        self.assertIn("Haken", de)
        self.assertIn("zu ist", de,
                      "Dass es auch bei geschlossenem Fenster weiterlaeuft, "
                      "ist der ueberraschende Teil - er gehoert in den Text.")

    def test_das_verhalten_ist_unveraendert(self):
        """Geaendert wurde der Text, nicht das Programm.

        _zwischenablage_tick plant sich selbst neu ein, ohne das Fenster
        anzusehen - genau das beschreibt der neue Text.
        """
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            baum = ast.parse(fh.read())
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_zwischenablage_tick")
        namen = {n.id for n in ast.walk(methode) if isinstance(n, ast.Name)}
        attribute = {n.attr for n in ast.walk(methode) if isinstance(n, ast.Attribute)}
        self.assertNotIn("_downloads_win", attribute | namen,
                         "Die Ueberwachung haengt wieder am Fenster - dann "
                         "stimmt der Tooltip nicht mehr.")


if __name__ == "__main__":
    unittest.main()
