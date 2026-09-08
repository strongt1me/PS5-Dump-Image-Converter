# -*- coding: utf-8 -*-
"""Jedes Fenster laesst sich schliessen - und die Knoepfe liegen nicht uebereinander.

Vier Meldungen eines Anwenders am 06.09.2026, alle an einem echten Mac
gesehen und hier nachgerechnet:

* **Der SCHLIESSEN-Knopf warf einen ``NameError``.** In drei Fenstern stand
  ``command=lambda: _beim_schliessen()``, ohne dass es diese Funktion in
  der Methode gab. Jeder Druck schrieb "Unbehandelter Fehler in der
  Oberflaeche: NameError: name '_beim_schliessen' is not defined" ins
  Protokoll, das Fenster blieb stehen. Nur das X der Fensterleiste half -
  das hat einen eigenen Weg (Tk raeumt dann selbst ab).
* **Das Y2JB-Fenster hatte gar keinen SCHLIESSEN-Knopf.** Der Handler
  ``_on_close`` gab es laengst, er haengt am X - nur ein Knopf fehlte.
* **Das WebKit-Fenster ueberlappte sich selbst.** Seine Hoehe stand fest
  auf 392 px, waehrend der Inhalt mit geladenem Bild bis 382 px reicht und
  der SCHLIESSEN-Knopf bei 353 beginnt: **29 px Ueberlappung**, und der
  Dank darunter wurde mitten im Wort abgeschnitten. Keine Eigenheit einer
  Plattform - schlicht falsch addiert.
* **Aufgabe 7 blieb offen stehen.** Sie ist die einzige Aufgabe der
  Seitenleiste, die ein Fenster oeffnet. Wer danach Aufgabe 1 anklickte,
  hatte beides.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("fensterknoepfe")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

G = APP.PS5ConverterGUI


def _baum() -> ast.Module:
    with io.open(APP.__file__, "rb") as fh:
        return ast.parse(fh.read().decode("utf-8"))


class SchliessenFunktioniertTests(unittest.TestCase):
    """Kein Knopf darf eine Funktion rufen, die es nicht gibt."""

    def test_kein_fenster_ruft_ein_fehlendes_beim_schliessen(self):
        baum = _baum()
        schlecht = []
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.FunctionDef):
                continue
            if knoten.name == "_beim_schliessen":
                continue
            quelltext = ast.unparse(knoten)
            if "_beim_schliessen" not in quelltext:
                continue
            definiert = any(isinstance(k, ast.FunctionDef)
                            and k.name == "_beim_schliessen"
                            for k in ast.walk(knoten))
            if not definiert:
                schlecht.append("%s:%d" % (knoten.name, knoten.lineno))
        self.assertEqual(
            [], schlecht,
            "Diese Methoden rufen ein _beim_schliessen, das sie nicht "
            "definieren - jeder Druck auf SCHLIESSEN wirft dort einen "
            "NameError: %s" % schlecht)

    #: Fenster, die einen eigenen SCHLIESSEN-Knopf tragen muessen. Die ersten
    #: vier waren am 06.09.2026 gemeldet oder standen daneben.
    #:
    #: Der AMPR-Index-Builder kam am 08.09.2026 dazu: Beim Durchgehen aller
    #: zweiundzwanzig Werkzeugfenster war er das einzige mit echten Knoepfen
    #: ("Durchsuchen", "Index bauen") und ohne einen zum Schliessen - er liess
    #: sich nur ueber das X der Fensterleiste loswerden. Die vier davor hatten
    #: dasselbe Problem, es war nur schon gemeldet worden.
    #:
    #: Nicht in der Liste steht das WebKit-Fenster, obwohl es ebenfalls keinen
    #: Knopf-Widget hat: Es zeichnet seine Knoepfe auf eine Canvas. Wer diese
    #: Liste erweitert, muss also erst nachsehen, ob das Fenster ueberhaupt
    #: mit Widgets arbeitet.
    MIT_KNOPF = ("_show_ps4_pkg_converter", "_show_debug_pkg_builder",
                 "_render_dump_rename_window", "_show_js_loader",
                 "_show_ampr_index_builder")

    def test_diese_fenster_haben_einen_schliessen_knopf(self):
        baum = _baum()
        ohne = []
        for name in self.MIT_KNOPF:
            knoten = next(k for k in ast.walk(baum)
                          if isinstance(k, ast.FunctionDef) and k.name == name)
            if "action.close" not in ast.unparse(knoten):
                ohne.append(name)
        self.assertEqual([], ohne,
                         "Diese Fenster lassen sich nur ueber das X der "
                         "Fensterleiste schliessen: %s" % ohne)

    def test_die_rueckfragen_gibt_es_in_beiden_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("ps4pkg.abort_confirm",
                           "debug_pkg.close_while_building"):
            with self.subTest(text=schluessel):
                eintrag = STRINGS[schluessel]
                self.assertTrue(eintrag.get("de"))
                self.assertTrue(eintrag.get("en"))
                self.assertNotEqual(eintrag["de"], eintrag["en"])


class WebkitFensterTests(unittest.TestCase):
    """Die Hoehe wird gerechnet, nicht geraten."""

    RAND = 14

    def _masse(self, mit_bild: bool) -> tuple[int, int, int]:
        """(Hoehe, Unterkante des letzten Knopfes, Oberkante SCHLIESSEN).

        Dieselbe Rechnung wie im Fenster - wer sie dort aendert, muss sie
        hier nachziehen, und genau das ist der Zweck.
        """
        versatz = (G._WEBKIT_BILD_KANTE + 16) if mit_bild else 0
        knopf_oben = self.RAND + 134 + versatz
        knopf_unten = knopf_oben + 2 * 56 + 44 // 2
        hoehe = knopf_unten + 16 + 26 + self.RAND
        schliessen_oben = hoehe - self.RAND - 12 - 13
        return hoehe, knopf_unten, schliessen_oben

    def test_die_knoepfe_ueberlappen_nicht(self):
        for mit_bild in (True, False):
            with self.subTest(bild=mit_bild):
                _hoehe, unten, schliessen = self._masse(mit_bild)
                self.assertGreater(
                    schliessen, unten,
                    "Der SCHLIESSEN-Knopf liegt auf dem letzten Wege-Knopf.")

    def test_die_alte_feste_hoehe_haette_ueberlappt(self):
        """Gegenprobe zur Rechnung: 392 px reichten nicht."""
        _hoehe, unten, _s = self._masse(True)
        alt_schliessen = 392 - self.RAND - 12 - 13
        self.assertLess(alt_schliessen, unten,
                        "Die Gegenprobe trifft nicht mehr - dann sagt der "
                        "Test oben auch nichts mehr.")
        self.assertEqual(29, unten - alt_schliessen)

    def test_die_hoehe_steht_nicht_mehr_fest_im_quelltext(self):
        baum = _baum()
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_show_webkit_autoloader")
        text = ast.unparse(knoten)
        self.assertNotIn("breite, hoehe, rand = 520, 392, 14", text)
        self.assertIn("hoehe = knopf_unten", text)


class AufgabeSiebenTests(unittest.TestCase):
    """Ihr Fenster geht zu, wenn eine andere Aufgabe drankommt."""

    def test_der_aufgabenwechsel_raeumt_das_fenster_weg(self):
        baum = _baum()
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_set_mode_from_sidebar")
        text = ast.unparse(knoten)
        self.assertIn("_werkzeugfenster_schliessen('_show_ampr_auswahl')", text,
                      "Aufgabe 7 laesst ihr Fenster wieder stehen, wenn man "
                      "eine andere Aufgabe waehlt.")

    def test_es_wird_nur_bei_einem_wechsel_geschlossen(self):
        """Wer Aufgabe 7 erneut waehlt, soll sein Fenster behalten."""
        baum = _baum()
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_set_mode_from_sidebar")
        text = ast.unparse(knoten)
        self.assertIn("if mode != 'ampr_manager'", text)

    def test_der_schliesser_oeffnet_nichts(self):
        """Sonst ginge beim Aufgabenwechsel ein Fenster auf statt zu."""
        baum = _baum()
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_werkzeugfenster_schliessen")
        text = ast.unparse(knoten)
        self.assertNotIn("getattr(self, befehl)()", text)
        self.assertIn("_fenster_schliessen", text)


class MacKnoepfeTests(unittest.TestCase):
    """Auf Aqua faerbt sich ein ``tk.Button`` nicht.

    ``flach_knopf`` gibt es dafuer seit v1.8.x: Unter Windows und X11 ein
    gewoehnlicher ``tk.Button``, auf macOS ein ``FlachButton`` (ein Label,
    das seine Farbe selbst malt). Im Y2JB-Fenster stand noch der rohe
    ``tk.Button`` - die helle Schrift des Programms auf der hellen
    Systemflaeche, und "Konsole leeren" war gar nicht mehr zu lesen.
    """

    def test_das_y2jb_fenster_nutzt_flach_knopf(self):
        baum = _baum()
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_show_js_loader")
        text = ast.unparse(knoten)
        self.assertEqual(0, text.count("tk.Button("),
                         "Rohe tk.Button im Y2JB-Fenster - auf dem Mac "
                         "bleiben die Beschriftungen unlesbar.")
        self.assertGreaterEqual(text.count("flach_knopf("), 6)

    def test_flach_knopf_vertraegt_dieselben_angaben(self):
        """Ein Label kennt alle Optionen, die die Aufrufstellen setzen."""
        import tkinter as tk
        wurzel = tk._default_root or tk.Tk()
        wurzel.withdraw()
        label = tk.Label(wurzel)
        for option in ("bg", "fg", "activebackground", "activeforeground",
                       "relief", "cursor", "font", "padx", "pady", "state"):
            with self.subTest(option=option):
                self.assertIn(option, label.keys())


if __name__ == "__main__":
    unittest.main(verbosity=2)
