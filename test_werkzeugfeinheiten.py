# -*- coding: utf-8 -*-
"""Sechs Befunde aus der Werkzeugpruefung, die sich am Aufbau festmachen lassen.

Alle vom 04.09.2026, alle am Quelltext nachgewiesen:

* Der Autoloader-Schnappschuss legte jede Zieldatei mit ``open(..., "wb")``
  an, **bevor** das ``RETR`` lief - dieselbe Klasse wie beim ``debug.log``.
  Brach die Uebertragung ab, blieb eine 0-Byte- oder halbe Datei im
  Schnappschussordner liegen; gezaehlt wurde sie nicht, zu sehen war sie
  trotzdem, und beim Zurueckspielen ginge sie mit auf die Konsole.
* Fehler einzelner Dateien vermerkte er nur mit ``logger.debug``. Der Logger
  schreibt im Auslieferungsstand nichts - der Anwender erfuhr also nie, dass
  etwas fehlt.
* Bei FileZilla stand der ganze Auswahlblock eine Ebene zu weit links und lief
  auch dann, wenn die automatische Installation geglueckt war.
* Schlug sie fehl, blieb "FileZilla wird installiert..." dauerhaft in der
  Statuszeile stehen.
* Der JS Loader trug einen deutschen Knopftext fest im Quelltext, obwohl er
  seit jeher zweisprachig in ``i18n.py`` liegt.
* Sein Sendefaden meldete ueber ``win.after`` statt ueber
  ``_spaeter_im_fenster`` - schliesst der Anwender das Fenster waehrend des
  Sendens, wirft Tk im Faden.

Dazu die Credits-Bildlaufleiste: Sie wurde nach der Flaeche gepackt und war
deshalb ein Stummel in der Ecke.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung

pruefumgebung.umlenken("werkzeugfeinheiten")

from ps5_validator.utils.i18n import STRINGS

HAUPTDATEI = os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py")


class _Quelltext(unittest.TestCase):
    """Gemeinsamer Zugriff auf den Syntaxbaum des Hauptmoduls."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(HAUPTDATEI, encoding="utf-8", errors="replace") as datei:
            cls.quelle = datei.read()
        cls.baum = ast.parse(cls.quelle)

    def _methode(self, name: str):
        klasse = next(k for k in self.baum.body
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        for k in klasse.body:
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s nicht gefunden" % name)


class AutoloaderSchnappschussTests(_Quelltext):
    """Kein RETR darf direkt in die Zieldatei gehen."""

    def test_es_wird_daneben_geschrieben(self) -> None:
        fenster = self._methode("_show_autoloader")
        # Jedes open(..., "wb") in diesem Fenster muss auf einen Pfad gehen,
        # der nicht das Ziel selbst ist - erkennbar am Namen "zwischen".
        offen = [k for k in ast.walk(fenster)
                 if isinstance(k, ast.Call) and getattr(k.func, "id", "") == "open"
                 and any(isinstance(a, ast.Constant) and a.value == "wb"
                         for a in k.args)]
        self.assertTrue(offen, "Kein Schreibzugriff gefunden - Pruefung greift nicht.")
        for aufruf in offen:
            ziel = aufruf.args[0]
            with self.subTest(zeile=aufruf.lineno):
                self.assertTrue(
                    isinstance(ziel, ast.Name) and ziel.id == "zwischen",
                    "Zeile %d schreibt direkt in die Zieldatei - bricht die "
                    "Uebertragung ab, bleibt eine halbe Datei liegen."
                    % aufruf.lineno)

    def test_am_ende_wird_umbenannt(self) -> None:
        fenster = self._methode("_show_autoloader")
        umbenannt = [k for k in ast.walk(fenster)
                     if isinstance(k, ast.Call)
                     and getattr(k.func, "attr", "") == "replace"
                     and getattr(getattr(k.func, "value", None), "id", "") == "os"]
        self.assertTrue(umbenannt,
                        "Die Zwischendatei wird nirgends an ihren Platz gerueckt.")

    def test_misslungene_dateien_werden_gemeldet(self) -> None:
        """Frueher nur logger.debug - und der schreibt ausgeliefert nichts."""
        self.assertIn("autoloader.snapshot_incomplete", self.quelle)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = STRINGS["autoloader.snapshot_incomplete"][sprache]
                self.assertIn("{count}", text)
                self.assertIn("{names}", text)


class FileZillaAuswahlTests(_Quelltext):
    """Der Auswahldialog gehoert in das "wenn nichts gefunden"."""

    def test_der_dialogblock_liegt_im_richtigen_zweig(self) -> None:
        weiter = self._methode("_filezilla_weiter")
        # Die Dateidialoge duerfen nicht auf der obersten Ebene der Methode
        # stehen, sondern muessen unterhalb eines "if" liegen.
        oberste = [k for k in weiter.body
                   if isinstance(k, ast.Expr) or isinstance(k, ast.Assign)]
        namen = []
        for knoten in oberste:
            for k in ast.walk(knoten):
                if isinstance(k, ast.Call) and getattr(k.func, "attr", "") in (
                        "askdirectory", "askopenfilename"):
                    namen.append(k.lineno)
        self.assertEqual(
            [], namen,
            "In Zeile(n) %s steht ein Auswahldialog unbedingt - er erscheint "
            "dann auch nach einer geglueckten Installation." % namen)

    def test_die_statuszeile_wird_zurueckgenommen(self) -> None:
        """Sonst steht dort dauerhaft 'FileZilla wird installiert...'."""
        weiter = self._methode("_filezilla_weiter")
        bereit = [k for k in ast.walk(weiter)
                  if isinstance(k, ast.Constant) and k.value == "main.status_ready"]
        self.assertTrue(
            bereit,
            "Auf dem Fehlschlagweg bleibt die Installationsmeldung stehen.")


class JsLoaderTests(_Quelltext):
    """Fester Text und ein ungesicherter Rueckweg."""

    def test_der_knopftext_kommt_aus_i18n(self) -> None:
        self.assertNotIn('text="Log-Server starten', self.quelle)
        self.assertIn("jsloader.start_logserver_button", self.quelle)

    def test_der_sendefaden_meldet_ueber_spaeter_im_fenster(self) -> None:
        fenster = self._methode("_show_js_loader")
        senden = [f for f in ast.walk(fenster)
                  if isinstance(f, ast.FunctionDef) and f.name == "_do_send"]
        self.assertEqual(1, len(senden), "Der Sendefaden wurde umbenannt.")
        ueber_after = [k.lineno for k in ast.walk(senden[0])
                       if isinstance(k, ast.Call)
                       and getattr(k.func, "attr", "") == "after"]
        self.assertEqual(
            [], ueber_after,
            "Zeile(n) %s melden ueber win.after. Schliesst der Anwender das "
            "Fenster waehrend des Sendens, wirft Tk im Faden." % ueber_after)
        abgesichert = [k for k in ast.walk(senden[0])
                       if isinstance(k, ast.Call)
                       and getattr(k.func, "attr", "") == "_spaeter_im_fenster"]
        self.assertGreaterEqual(len(abgesichert), 2,
                                "Erfolgs- und Fehlerzweig brauchen beide den "
                                "abgesicherten Rueckweg.")


class CreditsLeisteTests(_Quelltext):
    """Die Bildlaufleiste muss vor der Flaeche gepackt werden."""

    def test_die_leiste_kommt_zuerst(self) -> None:
        fenster = self._methode("_show_credits")
        reihenfolge = []
        for k in ast.walk(fenster):
            if not (isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "pack"):
                continue
            ziel = getattr(getattr(k.func, "value", None), "id", "")
            if ziel in ("vsb", "scroll_canvas"):
                reihenfolge.append((k.lineno, ziel))
        reihenfolge.sort()
        namen = [n for _z, n in reihenfolge]
        self.assertEqual(
            ["vsb", "scroll_canvas"], namen[:2],
            "Der Canvas wird vor der Leiste gepackt und nimmt den Hohlraum "
            "zuerst - die Leiste bleibt ein Stummel in der Ecke. Gefunden: %s"
            % namen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
