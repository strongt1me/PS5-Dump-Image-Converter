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

    # ERST das Hauptprogramm laden, DANN die Wurzel: Sein Import setzt unter
    # Windows die DPI-Kenntnis des Prozesses (SetProcessDpiAwareness ganz oben
    # in der Datei). Eine vorher angelegte Tk-Wurzel sieht noch 96 dpi und
    # bekommt "tk scaling" 1.335 statt der 1.668, mit denen das Programm
    # wirklich laeuft - an der Diagnose des laufenden Programms nachgemessen
    # (05.09.2026: tk scaling 1.6683, TkDefaultFont 20 px hoch).
    #
    # Die Reihenfolge entschied bisher darueber, ob diese Datei besteht: allein
    # gestartet mass sie gegen eine Skalierung, die es im Betrieb nicht gibt;
    # hinter einer anderen Testdatei - die das Hauptprogramm schon geladen
    # hatte - gegen die richtige. Der Fehlschlag im Gesamtlauf war also der
    # ehrlichere von beiden.
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
_WURZEL = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    for zusatz in (os.path.dirname(HAUPTDATEI),
                   os.path.join(os.path.dirname(HAUPTDATEI), "MkPFS-1.0.0")):
        if zusatz not in sys.path:
            sys.path.insert(0, zusatz)
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def _wurzel_holen():
    """Die Tk-Wurzel - aber erst, nachdem das Hauptprogramm geladen ist.

    Die Reihenfolge ist der Punkt: Der Import setzt unter Windows die
    DPI-Kenntnis des Prozesses. Eine vorher angelegte Wurzel sieht 96 dpi und
    bekommt ``tk scaling`` 1.335 statt der 1.668, mit denen das Programm
    wirklich laeuft (an der Diagnose des laufenden Programms nachgemessen,
    05.09.2026). Die Spalte braucht dann 821 px statt 999 - und die Pruefung
    unten urteilte ueber ein Fenster, das es so nicht gibt.

    Genau daran entschied sich bisher, ob diese Datei besteht: allein
    gestartet legte sie die Wurzel zuerst an und lief gruen; hinter einer
    anderen Testdatei, die das Hauptprogramm schon geladen hatte, fiel sie.
    Der Fehlschlag im Gesamtlauf war der ehrlichere von beiden.
    """
    global _WURZEL
    _lade_hauptprogramm()
    if _WURZEL is None:
        # Eine vorhandene Wurzel weiterbenutzen: ``ImageTk.PhotoImage`` ohne
        # ``master`` bindet an ``tk._default_root``, auf einer zweiten Wurzel
        # meldet Tk "image pyimageNNN doesn't exist". Und nie zerstoeren - ein
        # zweites tk.Tk() danach meldet "tk wasn't installed properly".
        _WURZEL = getattr(tk, "_default_root", None)
        if _WURZEL is None:
            _WURZEL = tk.Tk()
            _WURZEL.withdraw()
    return _WURZEL


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
        # Ein eigenes Fenster, nicht die geteilte Wurzel. Die Rollfrage
        # entscheidet sich an ``flaeche.winfo_height()`` - also daran, wieviel
        # Platz die Inhaltsspalte bekommt. Hat ein alphabetisch frueheres
        # Testmodul schon eine Oberflaeche an die Wurzel gepackt, teilen sich
        # beide dort den Platz, die eigene Spalte wird kuerzer und rollt schon
        # bei Hoehen, bei denen sie es nicht sollte. Genau daran fiel
        # test_ohne_rollen_sitzt_alles_wie_vorher im Gesamtlauf ueber Wochen,
        # waehrend die Datei allein gruen durchlief - ein Fehlschlag, der
        # keiner war und einen echten verdeckt haette.
        #
        # Ein Toplevel derselben Wurzel, keine zweite Tk-Wurzel: Die Bilder
        # haengen an ``tk._default_root`` (das Hauptprogramm ruft
        # ``ImageTk.PhotoImage`` an vielen Stellen ohne ``master``), und eine
        # zweite Wurzel liesse den Aufbau mit "image pyimageNNN doesn't exist"
        # scheitern.
        cls.root = tk.Toplevel(_wurzel_holen())
        try:
            cls.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.app = modul.PS5ConverterGUI(cls.root)
        cls.app._online_nachschlag_erlaubt = lambda: False
        cls._ruhen(1.5)

    @classmethod
    def tearDownClass(cls):
        # Das eigene Fenster darf weg - die Wurzel bleibt, wie sie war.
        try:
            cls.root.destroy()
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
        """Bei genug Platz darf die Rollflaeche nichts veraendern.

        "Genug Platz" wird gemessen, nicht gesetzt. Hier stand bis zum
        05.09.2026 die feste Zahl 991 - abgelesen an einer Skalierung von
        1.335, die im Betrieb gar nicht vorkommt. Mit den echten 1.668 braucht
        die Spalte 999 px und rollt bei 991 zu Recht; die Zusicherung
        behauptete also etwas Falsches ueber das laufende Programm.

        Der gemessene Weg haelt auch, wenn jemand die Schriftgroesse aendert
        oder das Fenster auf einen Bildschirm mit anderer DPI wandert.
        """
        noetig = self.app._inhalt_mindesthoehe()
        self.assertTrue(noetig, "Die Mindesthoehe liess sich nicht ermitteln")
        # Etwas Luft drauf, damit nicht die Rundung ueber das Ergebnis
        # entscheidet - und nicht ueber die Bildschirmhoehe hinaus, sonst
        # bekommt das Fenster gar nicht, was es anfordert.
        hoehe = min(noetig + 40, self.root.winfo_screenheight())
        self._einstellen(hoehe)
        self.assertFalse(
            self.app._inhalt_rollt,
            "Bei %d px (noetig sind %d) wird gerollt." % (hoehe, noetig))
        self.assertEqual(self.app.content_area.winfo_height(),
                         self.app.content_scroll.winfo_height())


if __name__ == "__main__":
    unittest.main(verbosity=2)
