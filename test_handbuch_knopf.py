"""Tests fuer den Knopf BENUTZERHANDBUCH und die Fusszeile der Einstellungen.

1. Knopf: Links neben EN in der Titelleiste, oeffnet ``BENUTZERHANDBUCH.html``.
   Die Datei muss auch in der EXE gefunden werden - dort liegt sie unter
   ``sys._MEIPASS``, weshalb sie in der ``.spec`` eingebettet sein muss.
2. Fusszeile der Einstellungen: Hinweistext und Knoepfe standen in derselben
   Zeile. Bei 520 px Dialogbreite nehmen die beiden Knoepfe gut 200 davon; der
   Hinweis lief mit fester ``wraplength=300`` unter sie und wurde abgeschnitten.
"""
from __future__ import annotations

import ast
import sys
import tkinter as tk
import unittest
import webbrowser
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import plattform
from ps5_validator.utils.i18n import STRINGS, translate

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
SPEC = PROJEKT / "PS5ImageConverter_Pro.spec"


def _tk_verfuegbar() -> bool:
    try:
        wurzel = tk.Tk()
    except Exception:
        return False
    wurzel.destroy()
    return True


class UebersetzungTests(unittest.TestCase):
    """Beide Sprachen muessen den Knopf und die Fehlermeldung kennen."""

    def test_knopfbeschriftung_in_beiden_sprachen(self):
        self.assertIn("titlebar.manual", STRINGS)
        self.assertEqual(translate("de", "titlebar.manual"), "BENUTZERHANDBUCH")
        self.assertEqual(translate("en", "titlebar.manual"), "USER MANUAL")

    def test_fehlermeldung_in_beiden_sprachen(self):
        self.assertIn("dialog.msg.manual_missing", STRINGS)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = translate(sprache, "dialog.msg.manual_missing")
                self.assertIn("BENUTZERHANDBUCH.html", text)
                self.assertNotEqual(text, "dialog.msg.manual_missing")


class AuslieferungTests(unittest.TestCase):
    """Ohne Einbettung waere der Knopf in der EXE wirkungslos."""

    def test_handbuch_liegt_im_projekt(self):
        self.assertTrue((PROJEKT / "BENUTZERHANDBUCH.html").is_file())

    def test_spec_bettet_handbuch_ein(self):
        text = SPEC.read_text(encoding="utf-8")
        self.assertIn("BENUTZERHANDBUCH.html", text)

    def test_spec_bettet_die_verlinkten_dateien_ein(self):
        """Das Handbuch verweist auf README und CHANGELOG - sonst tote Links."""
        text = SPEC.read_text(encoding="utf-8")
        for datei in ("README.md", "CHANGELOG.md"):
            with self.subTest(datei=datei):
                self.assertIn(datei, text)

    def test_bundled_resource_findet_das_handbuch(self):
        pfad = APP._bundled_resource("BENUTZERHANDBUCH.html")
        self.assertTrue(pfad)
        self.assertTrue(Path(pfad).is_file())


class OeffnenTests(unittest.TestCase):
    """Der Knopf ruft das Standardprogramm mit der gefundenen Datei auf."""

    def _app_ohne_fenster(self):
        """Instanz ohne __init__ - hier wird nur die eine Methode gebraucht."""
        return APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def test_oeffnet_die_gefundene_datei(self):
        """Der Knopf reicht den gefundenen Pfad an die Plattformschicht weiter.

        Frueher rief er selbst ``os.startfile``. Das gibt es nur unter Windows;
        welcher Befehl das System zum Oeffnen nimmt, entscheidet jetzt
        ``ps5_validator.utils.plattform``.
        """
        app = self._app_ohne_fenster()
        with mock.patch.object(APP, "_system_datei_oeffnen", return_value=True) as oeffnen:
            APP.PS5ConverterGUI._open_benutzerhandbuch(app)
        oeffnen.assert_called_once()
        self.assertTrue(str(oeffnen.call_args[0][0]).endswith("BENUTZERHANDBUCH.html"))

    def test_faellt_auf_den_browser_zurueck(self):
        """Laesst sich die Datei nicht dem System uebergeben, greift der Browser.

        Geprueft wird an der Plattformschicht selbst, weil dort seit der
        Portierung die Rueckfallebene sitzt. Der erste Weg wird je nach System
        unterschiedlich lahmgelegt: unter Windows ``os.startfile``, sonst der
        fehlende ``xdg-open``/``open``-Befehl.
        """
        ziel = str(PROJEKT / "BENUTZERHANDBUCH.html")
        with mock.patch.object(webbrowser, "open", return_value=True) as browser:
            if plattform.IST_WINDOWS:
                with mock.patch.object(APP.os, "startfile", create=True,
                                       side_effect=OSError("nein")):
                    self.assertTrue(plattform.datei_oeffnen(ziel))
            else:
                with mock.patch.object(plattform.shutil, "which", return_value=None):
                    self.assertTrue(plattform.datei_oeffnen(ziel))
        browser.assert_called_once()

    def test_fehlende_datei_meldet_statt_zu_schweigen(self):
        app = self._app_ohne_fenster()
        app.root = None
        app._current_language = "de"
        with mock.patch.object(APP, "_bundled_resource", return_value=""), \
             mock.patch.object(APP.messagebox, "showwarning") as box, \
             mock.patch.object(APP.os, "startfile", create=True) as startfile:
            APP.PS5ConverterGUI._open_benutzerhandbuch(app)
        box.assert_called_once()
        startfile.assert_not_called()


class QuelltextTests(unittest.TestCase):
    """Was sich nur am Aufbau zeigt - ohne Fenster geprueft."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUELLDATEI.read_text(encoding="utf-8")

    def test_knopf_wird_nach_dem_sprachknopf_gepackt(self):
        """Reihenfolge entscheidet: bei side='right' sitzt das letzte ganz links."""
        sprache = self.text.index('self._btn_language_title.pack(side="right"')
        handbuch = self.text.index('self._btn_manual_title.pack(side="right"')
        self.assertLess(sprache, handbuch,
                        "Der Handbuch-Knopf muss nach dem EN-Knopf gepackt werden")

    def test_knopf_wird_beim_sprachwechsel_neu_beschriftet(self):
        self.assertIn('("_btn_manual_title", "titlebar.manual")', self.text)

    def test_hinweis_hat_keine_feste_umbruchbreite_mehr(self):
        """Die feste wraplength=300 war die Ursache des Abschneidens."""
        self.assertNotIn("wraplength=300, justify=\"left\", anchor=\"w\"", self.text)

    def test_hinweis_und_knoepfe_in_getrennten_zeilen(self):
        self.assertIn("hint_row = tk.Frame(body", self.text)
        knopfzeile = self.text.index('close_row.pack(fill="x", side="bottom"')
        hinweiszeile = self.text.index('hint_row.pack(fill="x", side="bottom"')
        self.assertLess(knopfzeile, hinweiszeile,
                        "Knopfzeile muss zuerst gepackt werden, damit der Hinweis darueber steht")

    def test_quelltext_bleibt_gueltiges_python(self):
        ast.parse(self.text)


@unittest.skipUnless(_tk_verfuegbar(), "keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):
    """Am laufenden Fenster: Der Knopf existiert und steht links neben EN."""

    def setUp(self):
        self.wurzel = tk.Tk()
        self.wurzel.withdraw()
        # tkinter merkt sich die ERSTE Wurzel als _default_root und behaelt
        # sie, auch wenn sie laengst zerstoert ist. ImageTk.PhotoImage ohne
        # master baut sein Bild dann im alten Interpreter, waehrend das Label
        # im neuen entsteht - Tk meldet 'image "pyimage269" doesn't exist'.
        # Allein laeuft diese Datei deshalb durch, in der vollen Reihe hinter
        # anderen Fenstertests nicht. Fuer die Dauer des Tests ist diese
        # Wurzel die Standardwurzel.
        self._vorherige_wurzel = getattr(tk, "_default_root", None)
        tk._default_root = self.wurzel
        self.app = APP.PS5ConverterGUI(self.wurzel)
        self.wurzel.update_idletasks()

    def tearDown(self):
        try:
            self.wurzel.destroy()
        except Exception:
            pass
        tk._default_root = self._vorherige_wurzel

    def test_knopf_existiert_mit_richtiger_beschriftung(self):
        self.assertTrue(hasattr(self.app, "_btn_manual_title"))
        self.assertEqual(self.app._btn_manual_title.cget("text"), "BENUTZERHANDBUCH")

    def test_knopf_steht_links_vom_sprachknopf(self):
        """Gemessen am Fenster, ersatzweise ueber die Packreihenfolge.

        Unter X11 rechnet Tk das Raster eines zurueckgezogenen Fensters nicht
        aus - beide Knoepfe meldeten dort x=0, der Test schlug fehl, obwohl die
        Titelleiste richtig aufgebaut war. Erst ein kurz eingeblendetes Fenster
        liefert echte Koordinaten. Bleibt auch das ohne Ergebnis, entscheidet
        die Packreihenfolge: Beide Knoepfe haengen mit side="right" in derselben
        Zeile, der zuletzt gepackte sitzt also weiter links.
        """
        self.wurzel.deiconify()
        self.wurzel.update()
        handbuch = self.app._btn_manual_title.winfo_x()
        sprache = self.app._btn_language_title.winfo_x()
        self.wurzel.withdraw()

        if handbuch or sprache:
            self.assertLess(handbuch, sprache)
            return

        geschwister = self.app._btn_manual_title.master.pack_slaves()
        self.assertIn(self.app._btn_manual_title, geschwister)
        self.assertIn(self.app._btn_language_title, geschwister)
        for knopf in (self.app._btn_manual_title, self.app._btn_language_title):
            self.assertEqual(knopf.pack_info()["side"], "right",
                             "Die Ersatzpruefung gilt nur fuer rechts gepackte Knoepfe")
        self.assertGreater(geschwister.index(self.app._btn_manual_title),
                           geschwister.index(self.app._btn_language_title),
                           "BENUTZERHANDBUCH muss nach EN gepackt werden, um links davon zu landen")

    def test_beschriftung_folgt_der_sprache(self):
        self.app._current_language = "en"
        self.app._apply_language()
        self.assertEqual(self.app._btn_manual_title.cget("text"), "USER MANUAL")
        self.app._current_language = "de"
        self.app._apply_language()
        self.assertEqual(self.app._btn_manual_title.cget("text"), "BENUTZERHANDBUCH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
