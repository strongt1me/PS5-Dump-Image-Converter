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
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("downloads_speicherort")

from ps5_validator.utils import ps5_downloads as dl         # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Zwei echte Paketadressen. Erfundene weist ``parse_pkg_url`` ab, und der
#: Test praefe dann den Ungueltig-Zweig statt den Speicherort-Zweig.
ZWEI_ADRESSEN = (
    "http://gst.prod.dl.playstation.net/gst/prod/00/PPSA19015_00/app/pkg/5/"
    "f_2f6a8429bc090a765d66f5d3d46b0db710967ef4b40c57005ba8e5ce4b6abff4/"
    "UP8016-PPSA19015_00-0489895718491618.pkg\n"
    "http://gst.prod.dl.playstation.net/gst/prod/00/PPSA19016_00/app/pkg/5/"
    "f_3f6a8429bc090a765d66f5d3d46b0db710967ef4b40c57005ba8e5ce4b6abff4/"
    "UP8016-PPSA19016_00-0489895718491619.pkg"
)


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
        """Drei stumme Wege gab es: kein Ort, Ordner weg, Dateimanager
        startet nicht. Jeder braucht eine Meldung.

        Gezaehlt werden auch Aufrufe von ``_oeffnen_oder_melden``: Der
        dritte Weg geht seit dem 06.09.2026 darueber, weil der blosse
        Rueckgabewert von ``datei_oeffnen`` nie Misserfolg meldete. Dass
        der Helfer wirklich meldet, sichert ``test_systemoeffner``.
        """
        m = self._innere("_show_downloads_manager", "_ordner_oeffnen")
        meldungen = [k for k in ast.walk(m) if isinstance(k, ast.Call)
                     and getattr(k.func, "attr", "") in
                     ("showwarning", "showerror", "showinfo",
                      "_oeffnen_oder_melden")]
        self.assertGreaterEqual(len(meldungen), 3, [
            getattr(k.func, "attr", "") for k in ast.walk(m)
            if isinstance(k, ast.Call)])

    def test_ein_fehlender_ort_wird_erst_angeboten(self):
        """Meckern hilft niemandem - erst den Ordner anbieten."""
        m = self._innere("_show_downloads_manager", "_ordner_oeffnen")
        aufrufe = [getattr(k.func, "attr", "") for k in ast.walk(m)
                   if isinstance(k, ast.Call)]
        self.assertIn("_download_basis_waehlen", aufrufe)


class StapelTests(unittest.TestCase):
    """Ein Klick auf "Einfuegen" darf nicht drei Fenster oeffnen.

    Wer mehrere Adressen einfuegt und noch keinen Speicherort gesetzt hat,
    bekam bis zum 06.09.2026 nacheinander: den Ordnerwaehler (aus der
    ersten Adresse heraus), die Warnung "kein Speicherort" und danach die
    Zusammenfassung "0 von N uebernommen". Die letzten beiden sagten
    dasselbe, und gefragt wurde aus der Schleife heraus - bei zehn
    Adressen also moeglicherweise zehnmal.

    Jetzt wird der Ordner **einmal vorher** geklaert; verneint der Anwender,
    bleibt es bei einer Meldung.
    """

    def _gui(self, hat_basis: bool, waehlt: bool):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda s, **kw: s
        # Die Dialoge sind gepatcht, aber "parent or self.root" wird vorher
        # ausgewertet - ohne dieses Attribut stuerzt der Aufruf ab.
        gui.root = None
        gui._append_to_log = lambda _t: self.protokoll.append(_t)
        gui._download_basis = lambda: "C:/Ziel" if hat_basis else ""
        self.gefragt: list = []
        self.protokoll: list = []

        def _waehlen(parent=None):
            self.gefragt.append(parent)
            return "C:/Gewaehlt" if waehlt else ""
        gui._download_basis_waehlen = _waehlen
        self.aufgenommen: list = []

        def _aufnehmen(adresse, parent=None, sammel=False, **kw):
            self.aufgenommen.append(adresse)
            return "neu"
        gui._download_aufnehmen = _aufnehmen
        return gui

    def _lauf(self, gui, still=False):
        with mock.patch.object(APP.messagebox, "showwarning") as warnung, \
             mock.patch.object(APP.messagebox, "showinfo") as info:
            anzahl = gui._downloads_uebernehmen(
                ZWEI_ADRESSEN,
                parent=None, still=still)
        return anzahl, warnung.call_count + info.call_count

    def test_ohne_speicherort_wird_genau_einmal_gefragt(self):
        gui = self._gui(hat_basis=False, waehlt=False)
        self._lauf(gui)
        self.assertEqual(1, len(self.gefragt),
                         "Der Ordnerwaehler ging %dx auf" % len(self.gefragt))

    def test_ein_verneinter_ordner_gibt_genau_eine_meldung(self):
        gui = self._gui(hat_basis=False, waehlt=False)
        anzahl, fenster = self._lauf(gui)
        self.assertEqual(0, anzahl)
        self.assertEqual(1, fenster, "%d Fenster statt einem" % fenster)

    def test_dabei_wird_keine_adresse_angefasst(self):
        gui = self._gui(hat_basis=False, waehlt=False)
        self._lauf(gui)
        self.assertEqual([], self.aufgenommen)

    def test_die_zusammenfassung_steht_trotzdem_im_protokoll(self):
        # Sie ist die Spur fuer den Anwender, auch wenn kein Fenster kommt.
        gui = self._gui(hat_basis=False, waehlt=False)
        self._lauf(gui)
        self.assertIn("downloads.batch_summary", self.protokoll)

    def test_still_heisst_wirklich_still(self):
        # Die Zwischenablage-Ueberwachung laeuft im Hintergrund; dort waere
        # ein Fenster aufdringlich.
        gui = self._gui(hat_basis=False, waehlt=False)
        _anzahl, fenster = self._lauf(gui, still=True)
        self.assertEqual(0, fenster)

    def test_mit_gewaehltem_ordner_laeuft_der_stapel_durch(self):
        gui = self._gui(hat_basis=False, waehlt=True)
        anzahl, _f = self._lauf(gui)
        self.assertEqual(2, anzahl)
        self.assertEqual(2, len(self.aufgenommen))

    def test_mit_vorhandenem_ordner_wird_gar_nicht_gefragt(self):
        gui = self._gui(hat_basis=True, waehlt=False)
        anzahl, _f = self._lauf(gui)
        self.assertEqual([], self.gefragt)
        self.assertEqual(2, anzahl)

    def test_die_einzelaufnahme_fragt_im_stapel_nicht_mehr(self):
        """Die andere Haelfte: auch aus der Schleife heraus kein Dialog.

        Sonst haette der Umbau nur die Reihenfolge verschoben.
        """
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda s, **kw: s
        gui._download_basis = lambda: ""
        gefragt = []
        gui._download_basis_waehlen = lambda parent=None: gefragt.append(1) or ""
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            ergebnis = gui._download_aufnehmen(
                ZWEI_ADRESSEN.splitlines()[0], sammel=True)
        self.assertEqual("abgebrochen", ergebnis)
        self.assertEqual([], gefragt, "Es wurde aus der Schleife gefragt")
        warnung.assert_not_called()


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
