# -*- coding: utf-8 -*-
"""Tests für die Rollfläche der Inhaltsspalte.

Hintergrund: Überschrift, Untertitel, Pfad-Karte, Knopfleiste,
Protokollfläche und Statuszeile wollen zusammen 1356 Pixel Höhe. Die
Protokollfläche gibt nach und fängt das normalerweise auf – alles andere ist
starr und braucht 844 Pixel. Bei einem kürzeren Fenster schob das Raster den
Rest unter den Fensterrand: Am 20.08.2026 gemessen stand bei 768 Pixeln
Fensterhöhe die Knopfleiste mit STARTEN und ABBRECHEN 26 Pixel außerhalb –
unsichtbar und nicht anklickbar.

Der erste Teil prüft am Quelltext, dass der Aufbau stimmt und die
Rollprüfung nicht im Kreis läuft. Der zweite öffnet ein echtes Fenster und
misst über die Höhen 700 bis 1080, ob noch etwas herausragt; ohne verfügbare
Anzeige wird er übersprungen.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    # Die vorhandene Wurzel nehmen, wenn ein anderes Testmodul schon eine
    # angelegt hat. ``ImageTk.PhotoImage`` ohne ``master`` bindet an
    # ``tk._default_root``; auf einer zweiten Wurzel meldet Tk beim Aufbau
    # dann "image pyimageNNN doesn't exist". Und offen halten, nicht
    # zerstoeren: Ein zweites tk.Tk() nach einem zerstoerten meldet
    # "tk wasn't installed properly".
    _WURZEL = getattr(tk, "_default_root", None)
    if _WURZEL is None:
        _WURZEL = tk.Tk()
        _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    for zusatz in (os.path.dirname(HAUPTDATEI),
                   os.path.join(os.path.dirname(HAUPTDATEI), "MkPFS-0.0.9")):
        if zusatz not in sys.path:
            sys.path.insert(0, zusatz)
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class AufbauTests(unittest.TestCase):
    """Was sich am Quelltext festmachen lässt."""

    @classmethod
    def setUpClass(cls):
        with open(HAUPTDATEI, "r", encoding="utf-8") as datei:
            cls.quelltext = datei.read()

    def _methode(self, name: str) -> str:
        anfang = self.quelltext.index("    def %s(self" % name)
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        return self.quelltext[anfang:weiter]

    def test_inhalt_liegt_in_der_rollflaeche(self):
        self.assertIn("self.content_scroll = tk.Canvas(", self.quelltext)
        self.assertIn("content_area = tk.Frame(self.content_scroll", self.quelltext)
        self.assertIn("self.content_scroll.create_window(", self.quelltext)

    def test_leiste_haengt_nicht_fest_im_raster(self):
        """Sie darf nur erscheinen, wenn wirklich gerollt werden muss."""
        rumpf = self._methode("_rollflaeche_pruefen")
        self.assertIn("self.content_scrollbar.grid(row=1, column=2", rumpf)
        self.assertIn("self.content_scrollbar.grid_remove()", rumpf)

    def test_pruefung_laeuft_nicht_im_kreis(self):
        """itemconfigure loest selbst ein Configure aus.

        Ohne den Vergleich vorher bestellte jede Anpassung die naechste.
        """
        rumpf = self._methode("_rollflaeche_pruefen")
        self.assertIn("flaeche.itemcget(", rumpf)
        self.assertLess(rumpf.index("flaeche.itemcget("),
                        rumpf.index("flaeche.itemconfigure("))
        # Und der Anstoss vom Inhalt her ist entprellt.
        self.assertIn("after_cancel", self._methode("_on_inhalt_configure"))

    def test_mausrad_laesst_die_protokollflaeche_in_ruhe(self):
        """Sonst rollte ein Rad über der Konsole zwei Dinge gleichzeitig."""
        rumpf = self._methode("_on_inhalt_mausrad")
        for klasse in ("Text", "Listbox", "TCombobox", "TSpinbox"):
            with self.subTest(klasse=klasse):
                self.assertIn('"%s"' % klasse, rumpf)
        # Und gar nichts tun, solange die Spalte ohnehin ganz sichtbar ist.
        self.assertIn("_inhalt_rollt", rumpf)

    def test_mausrad_auch_unter_linux(self):
        """X11 meldet das Rad als Button 4 und 5, nicht als delta."""
        self.assertIn('"<Button-4>", "<Button-5>"', self.quelltext)


@unittest.skipUnless(TK_DA, "keine Anzeige verfuegbar")
class HoehenTests(unittest.TestCase):
    """Am laufenden Fenster: ragt bei kleiner Höhe noch etwas heraus?"""

    #: Die gemessenen Grenzfälle. 768 ist ein verbreiteter Laptop-Schirm,
    #: 700 die Mindesthöhe des Fensters, 1080 ein voller Bildschirm.
    HOEHEN = (700, 768, 800, 840, 880, 991, 1080)

    @classmethod
    def setUpClass(cls):
        modul = _lade_hauptprogramm()
        cls.root = _WURZEL
        cls.root.deiconify()
        try:
            cls.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.app = modul.PS5ConverterGUI(cls.root)
        cls.app._online_nachschlag_erlaubt = lambda: False
        cls._ruhen(1.5)

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.withdraw()
        except Exception:
            pass

    @classmethod
    def _ruhen(cls, sekunden: float) -> None:
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            cls.root.update()
            time.sleep(0.01)

    def _einstellen(self, hoehe: int) -> None:
        try:
            self.root.state("normal")
        except Exception:
            pass
        self.root.geometry("1600x%d" % hoehe)
        self._ruhen(1.2)

    def test_alles_liegt_im_rollbereich(self):
        """Jede Zeile der Spalte muss durch Rollen erreichbar sein.

        Geprueft wird gegen den Rollbereich, nicht ueber die Darstellungs-
        pruefung: Die laeuft ueber den ganzen Tk-Baum, und im Gesamtlauf der
        Testreihe haengt an derselben Wurzel noch eine zweite Oberflaeche aus
        einem anderen Testmodul.
        """
        for hoehe in self.HOEHEN:
            with self.subTest(hoehe=hoehe):
                self._einstellen(hoehe)
                sicht = self.app.content_scroll
                bereich = str(sicht.cget("scrollregion")).split()
                self.assertEqual(4, len(bereich), "kein Rollbereich gesetzt")
                unten = int(float(bereich[3]))
                spalte = self.app.content_area
                for kind in spalte.grid_slaves():
                    if not kind.winfo_ismapped():
                        continue
                    kante = (kind.winfo_rooty() - spalte.winfo_rooty()
                             + kind.winfo_height())
                    self.assertLessEqual(
                        kante, unten + 2,
                        "%s endet bei %d, Rollbereich reicht nur bis %d "
                        "(Fensterhoehe %d)"
                        % (kind.winfo_class(), kante, unten, hoehe))

    def test_leiste_erscheint_nur_wenn_noetig(self):
        self._einstellen(700)
        self.assertTrue(self.app._inhalt_rollt,
                        "bei 700 px muesste gerollt werden")
        self.assertTrue(self.app.content_scrollbar.winfo_ismapped())

        self._einstellen(1080)
        self.assertFalse(self.app._inhalt_rollt,
                         "bei 1080 px passt alles ohne Rollen")
        self.assertFalse(self.app.content_scrollbar.winfo_ismapped())

    def test_knopfleiste_bleibt_erreichbar(self):
        """Der eigentliche Zweck: An STARTEN muss man herankommen."""
        self._einstellen(768)
        leiste = self.app.action_bar
        sicht = self.app.content_scroll
        # Ganz nach unten rollen - dann muss die Leiste im Sichtfeld liegen.
        sicht.yview_moveto(1.0)
        self._ruhen(0.6)
        oben = leiste.winfo_rooty() - sicht.winfo_rooty()
        unten = oben + leiste.winfo_height()
        self.assertGreaterEqual(oben, -2, "Knopfleiste liegt ueber dem Sichtfeld")
        self.assertLessEqual(unten, sicht.winfo_height() + 2,
                             "Knopfleiste liegt unter dem Sichtfeld")

    def test_ohne_rollen_sitzt_alles_wie_vorher(self):
        """Bei genug Platz darf die Rollflaeche nichts veraendern."""
        self._einstellen(991)
        self.assertFalse(self.app._inhalt_rollt)
        self.assertEqual(self.app.content_area.winfo_height(),
                         self.app.content_scroll.winfo_height())


if __name__ == "__main__":
    unittest.main(verbosity=2)
