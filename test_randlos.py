# -*- coding: utf-8 -*-
"""Die Oberfläche bleibt randlos - und trotzdem lesbar.

Der Nutzer legt Wert auf ein randloses Erscheinungsbild mit durchgehendem
Hintergrundbild. Am 25.08.2026 zeigte ein Durchgang durch den laufenden
Widget-Baum **63 Stellen** mit sichtbarem Rand - fast alle an Elementen ohne
Namen (``!frame3``, ``!text``, ``!treeview``, ``PY_VAR3``). Eine Textsuche im
Quelltext hätte sie nie gefunden; deshalb prüfen diese Tests am echten Baum.

Zwei Ursachen, beide nicht offensichtlich:

1. **Tk liefert Vorgaben mit.** ``Text``, ``Entry`` und ``Listbox`` tragen von
   Haus aus ``relief="sunken"`` und ``borderwidth=1``. Bei 47 Erzeugungsstellen
   ist das nicht einzeln zu pflegen - eine vergessene Stelle genügt für einen
   Kasten zu viel. Deshalb die Option-Datenbank.
2. **Ränder stecken in ttk-Stilen**, nicht am Widget. ``Card.TFrame`` zog eine
   1 px starke Linie um jede Karte; es gab bereits eine randlose Variante
   (``PathCard.TFrame``), die aber nur an einer einzigen Karte hing.

**Die Gegenrichtung ist genauso wichtig:** Ohne Rand trägt allein die Fläche
die Information "hier kann man tippen". Beim ersten Anlauf waren Eingabefeld
und Karte exakt gleich (#18283D auf #18283D) - das Feld war unsichtbar. Ein
randloses Aussehen darf nicht damit erkauft werden, dass man Bedienelemente
nicht mehr findet.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Ab so vielen Helligkeitsstufen Unterschied ist eine Fläche von ihrem
#: Untergrund noch zu unterscheiden. Darunter verschwimmt es auf dem
#: Bildschirm - gemessen am hellen Design, wo 5,4 zu wenig waren.
MINDESTUNTERSCHIED = 6.0


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def helligkeit(hexfarbe) -> float:
    """Wahrgenommene Helligkeit einer #RRGGBB-Farbe."""
    h = str(hexfarbe).lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return 0.299 * r + 0.587 * g + 0.114 * b


class PaletteTests(unittest.TestCase):
    """Flächen müssen sich unterscheiden - in jedem Design."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def test_jedes_design_kennt_die_noetigen_farben(self) -> None:
        for name, palette in self.haupt.PS5ConverterGUI._THEMES.items():
            with self.subTest(design=name):
                for schluessel in ("bg_main", "bg_card", "console_bg"):
                    self.assertIn(schluessel, palette)

    def test_die_konsole_hebt_sich_von_der_karte_ab(self) -> None:
        """Der gemessene Fall: Im hellen Design lagen 5,4 Stufen dazwischen.

        Solange das Textfeld einen vertieften Rand hatte, war es abgegrenzt.
        Ohne ihn trägt allein die Fläche die Abgrenzung.
        """
        for name, palette in self.haupt.PS5ConverterGUI._THEMES.items():
            with self.subTest(design=name):
                unterschied = abs(helligkeit(palette["console_bg"])
                                  - helligkeit(palette["bg_card"]))
                self.assertGreaterEqual(
                    unterschied, MINDESTUNTERSCHIED,
                    "%s: Konsole %s auf Karte %s - nur %.1f Stufen"
                    % (name, palette["console_bg"], palette["bg_card"], unterschied))

    def test_die_karte_hebt_sich_vom_fenster_ab(self) -> None:
        for name, palette in self.haupt.PS5ConverterGUI._THEMES.items():
            with self.subTest(design=name):
                unterschied = abs(helligkeit(palette["bg_card"])
                                  - helligkeit(palette["bg_main"]))
                self.assertGreaterEqual(unterschied, MINDESTUNTERSCHIED,
                                        "%s: nur %.1f Stufen" % (name, unterschied))

    def test_das_eingabefeld_hebt_sich_von_der_karte_ab(self) -> None:
        """Die Füllung wird aus der Palette abgeleitet, nicht fest eingetragen.

        Deshalb muss sie für **jedes** Design nachgerechnet werden - auch für
        eines, das später dazukommt.
        """
        gui = self.haupt.PS5ConverterGUI
        for name, palette in gui._THEMES.items():
            with self.subTest(design=name):
                feld = gui._blend_hex_color(
                    palette["bg_card"], gui._hex_zu_rgb(palette["bg_main"]), 0.45)
                unterschied = abs(helligkeit(feld) - helligkeit(palette["bg_card"]))
                self.assertGreaterEqual(
                    unterschied, MINDESTUNTERSCHIED,
                    "%s: Feld %s auf Karte %s - nur %.1f Stufen"
                    % (name, feld, palette["bg_card"], unterschied))


class QuelltextTests(unittest.TestCase):
    """Was sich am Quelltext festhalten lässt, ohne ein Fenster zu öffnen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = HAUPTDATEI.read_text(encoding="utf-8", errors="replace")

    def test_die_zentrale_vorgabe_steht_da(self) -> None:
        """Ohne sie bringt jedes neue Text-, Entry- oder Listbox-Feld seinen
        eigenen Rand mit, ohne dass es irgendwo im Quelltext stünde."""
        self.assertIn('option_add("*%s.relief" % _klasse, "flat")', self.quelle)
        self.assertIn('option_add("*%s.borderWidth" % _klasse, 0)', self.quelle)

    def test_die_vorgabe_deckt_alle_betroffenen_klassen_ab(self) -> None:
        anfang = self.quelle.index('for _klasse in (')
        zeile = self.quelle[anfang:anfang + 90]
        for klasse in ("Text", "Entry", "Listbox"):
            self.assertIn('"%s"' % klasse, zeile)

    def test_der_fokusrahmen_bleibt_unangetastet(self) -> None:
        """highlightthickness zeigt bei Bedienung per Tastatur, wo man ist.

        Er gehört ausdrücklich NICHT zu den entfernten Rändern - sonst wäre
        das Programm ohne Maus nicht mehr sinnvoll bedienbar.
        """
        anfang = self.quelle.index('for _klasse in (')
        block = self.quelle[anfang - 900:anfang + 300]
        self.assertNotIn('highlightThickness', block)
        self.assertIn("Fokusrahmen", block)

    def test_kein_bauplan_setzt_die_karte_wieder_auf_solid(self) -> None:
        anfang = self.quelle.index('style.configure("Card.TFrame"')
        block = self.quelle[anfang:anfang + 260]
        self.assertIn('relief="flat"', block)
        self.assertIn("borderwidth=0", block)
        self.assertNotIn('relief="solid"', block)

    def test_die_knoepfe_tragen_keinen_rand_mehr(self) -> None:
        anfang = self.quelle.index('style.configure("TButton"')
        block = self.quelle[anfang:anfang + 420]
        self.assertIn("borderwidth=0", block)
        self.assertNotIn('relief="solid"', block)

    def test_das_eingabefeld_bekommt_eine_eigene_flaeche(self) -> None:
        """Sonst ist es ohne Rand nicht mehr zu sehen."""
        anfang = self.quelle.index('style.configure("TEntry"')
        block = self.quelle[anfang - 800:anfang + 200]
        self.assertIn("_feld_bg", block)
        self.assertIn("_blend_hex_color", block)

    def test_kein_widget_setzt_mehr_sunken(self) -> None:
        """Die acht Stellen mit relief="sunken", bd=1 sind umgestellt."""
        self.assertNotIn('relief="sunken", bd=1', self.quelle)


class WidgetbaumTests(unittest.TestCase):
    """Der eigentliche Beweis: am laufenden Fenster abgelesen.

    Nur so werden auch die namenlosen Elemente erfasst - und Ränder, die aus
    einem Stil statt aus dem Widget kommen.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        import tkinter as tk
        try:
            cls.wurzel = tk._default_root or tk.Tk()
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest("keine Anzeige: %s" % exc)
        cls.wurzel.geometry("1280x860")
        for n in ("showinfo", "showwarning", "showerror", "askyesno", "askokcancel"):
            setattr(cls.haupt.messagebox, n, lambda *a, **k: False)
        cls.app = cls.haupt.PS5ConverterGUI(cls.wurzel)
        cls.wurzel.update_idletasks()
        cls.wurzel.update()

    @classmethod
    def tearDownClass(cls) -> None:
        # Die Wurzel NICHT zerstoeren - eine Tk-Wurzel je Prozess.
        try:
            cls.wurzel.withdraw()
        except Exception:
            pass

    def _raender(self):
        from tkinter import ttk
        stil = ttk.Style()

        def zahl(w):
            try:
                return int(str(w))
            except (TypeError, ValueError):
                return 0

        # Tks eigene Vorgaben sind kein Befund.
        VORGABE = {"Label": 2, "Button": 2, "Text": 2, "Canvas": 2, "Entry": 2,
                   "Listbox": 2, "Checkbutton": 2, "Radiobutton": 2,
                   "Menubutton": 2, "Message": 2, "Spinbox": 2}
        treffer = []

        def gehe(w):
            try:
                if w.winfo_ismapped():
                    gruende = []
                    if isinstance(w, ttk.Widget):
                        name = w.cget("style") or w.winfo_class()
                        if zahl(stil.lookup(name, "borderwidth")) > 0:
                            gruende.append("Stil %s borderwidth" % name)
                        rel = str(stil.lookup(name, "relief") or "")
                        if rel and rel not in ("flat", ""):
                            gruende.append("Stil %s relief=%s" % (name, rel))
                    else:
                        klasse = w.winfo_class()
                        if "relief" in w.keys():
                            rel = str(w.cget("relief") or "")
                            if rel and rel not in ("flat", ""):
                                gruende.append("relief=%s" % rel)
                        if "borderwidth" in w.keys():
                            bd = zahl(w.cget("borderwidth"))
                            if bd > 0 and bd != VORGABE.get(klasse, 0):
                                gruende.append("borderwidth=%d" % bd)
                    if gruende:
                        treffer.append("%s %s" % (w.winfo_class(), ", ".join(gruende)))
            except Exception:
                pass
            for k in w.winfo_children():
                gehe(k)

        gehe(self.wurzel)
        return treffer

    def test_im_hauptfenster_ist_kein_rand_mehr(self) -> None:
        """Vorher: 5 Stellen - drei Pfadfelder, die Protokollkarte und das
        Protokollfeld. Alle namenlos."""
        treffer = self._raender()
        self.assertEqual(treffer, [], "noch %d Raender: %r" % (len(treffer), treffer[:6]))

    def test_die_pruefung_wuerde_einen_rand_auch_finden(self) -> None:
        """Gegenprobe - sonst bestünde der Test auch bei kaputter Suche."""
        import tkinter as tk
        stoerer = tk.Frame(self.wurzel, relief="solid", borderwidth=3,
                           width=40, height=40)
        stoerer.place(x=5, y=5)
        self.wurzel.update_idletasks()
        try:
            treffer = self._raender()
            self.assertTrue(any("relief=solid" in t for t in treffer),
                            "der eingebaute Rand wurde nicht gefunden")
        finally:
            stoerer.destroy()
            self.wurzel.update_idletasks()

    def test_das_eingabefeld_ist_sichtbar(self) -> None:
        """Am laufenden Fenster, nicht nur an der Palette gerechnet."""
        from tkinter import ttk
        stil = ttk.Style()
        feld = stil.lookup("TEntry", "fieldbackground")
        karte = self.app._COLORS["bg_card"]
        unterschied = abs(helligkeit(feld) - helligkeit(karte))
        self.assertGreaterEqual(
            unterschied, MINDESTUNTERSCHIED,
            "Feld %s auf Karte %s - nur %.1f Stufen" % (feld, karte, unterschied))


class FokusOhneRahmenTests(unittest.TestCase):
    """Der Fokusrahmen ist weg - aber nicht ersatzlos.

    ``highlightthickness`` zeichnet einen Rahmen, sobald ein Bedienelement
    den Tastaturfokus hat. Er fiel mit den übrigen Rändern weg. Ersatzlos
    dürfte er das nicht: Ohne jede Rückmeldung wäre nicht mehr zu erkennen,
    welches Element gerade dran ist, und das Programm ohne Maus nicht mehr
    sinnvoll zu bedienen. Statt einer Linie ändert sich die **Fläche**.

    Der Fallstrick, der beim ersten Anlauf auffiel: Aufhellen allein genügt
    nicht. Ein weißer Knopf im hellen Design lässt sich nicht weiter
    aufhellen - gemessen +0,0 Stufen, der Fokus wäre dort unsichtbar
    gewesen. Deshalb hängt die Richtung an der Helligkeit.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def fokusfarbe(self, basis: str) -> str:
        gui = self.haupt.PS5ConverterGUI
        ziel = (0, 0, 0) if helligkeit(basis) > gui._FOKUS_HELL_AB else (255, 255, 255)
        return gui._blend_hex_color(basis, ziel, gui._FOKUS_AUFHELLUNG)

    def test_der_fokus_ist_auf_jeder_flaeche_zu_sehen(self) -> None:
        """Auch auf Weiß - genau dort versagte der erste Anlauf."""
        gui = self.haupt.PS5ConverterGUI
        flaechen = ["#FFFFFF", "#000000"]
        for palette in gui._THEMES.values():
            flaechen += [palette["bg_main"], palette["bg_card"],
                         palette["accent_btn"]]
        for basis in flaechen:
            with self.subTest(flaeche=basis):
                unterschied = abs(helligkeit(self.fokusfarbe(basis))
                                  - helligkeit(basis))
                self.assertGreaterEqual(
                    unterschied, 12.0,
                    "%s -> %s: nur %.1f Stufen"
                    % (basis, self.fokusfarbe(basis), unterschied))

    def test_der_fokus_schreit_nicht(self) -> None:
        """Zu kräftig sähe aus wie 'gedrückt'. Beim ersten Anlauf +47,7."""
        gui = self.haupt.PS5ConverterGUI
        for palette in gui._THEMES.values():
            for basis in (palette["bg_main"], palette["bg_card"]):
                with self.subTest(flaeche=basis):
                    unterschied = abs(helligkeit(self.fokusfarbe(basis))
                                      - helligkeit(basis))
                    self.assertLessEqual(unterschied, 40.0,
                                         "%s: %.1f Stufen" % (basis, unterschied))

    def test_weiss_wird_abgedunkelt_statt_aufgehellt(self) -> None:
        self.assertLess(helligkeit(self.fokusfarbe("#FFFFFF")),
                        helligkeit("#FFFFFF"))

    def test_schwarz_wird_aufgehellt(self) -> None:
        self.assertGreater(helligkeit(self.fokusfarbe("#000000")),
                           helligkeit("#000000"))

    def test_die_bindung_wird_nur_einmal_gesetzt(self) -> None:
        """``_setup_styles`` läuft bei jedem Designwechsel erneut.

        Mit ``add="+"`` würden sich die Bindungen sonst stapeln - dieselbe
        Falle wie beim Mausrad.
        """
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _fokus_ohne_rahmen_einrichten")
        koerper = quelle[anfang:anfang + 3000]
        self.assertIn('getattr(self, "_fokus_bindung_steht", False)', koerper)
        self.assertIn("_fokus_bindung_steht = True", koerper)

    def test_die_bindung_gilt_fuer_die_klasse_nicht_fuer_alles(self) -> None:
        """``bind_all`` schreibt in die globale Tabelle und hat dem
        Hauptfenster schon einmal das Mausrad genommen."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _fokus_ohne_rahmen_einrichten")
        koerper = quelle[anfang:anfang + 3000]
        self.assertIn("bind_class", koerper)
        self.assertNotIn("bind_all", koerper)

    def test_die_farbe_kehrt_zurueck(self) -> None:
        """Sonst bliebe jeder einmal angetippte Knopf für immer hell."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _fokus_ohne_rahmen_einrichten")
        koerper = quelle[anfang:anfang + 3000]
        self.assertIn("<FocusOut>", koerper)
        self.assertIn("w.configure(bg=alt)", koerper)


class TooltipTests(unittest.TestCase):
    """Auch die Kurzinfo trägt keinen Rand mehr."""

    def test_die_kurzinfo_ist_randlos(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index('tip = tk.Toplevel(self.widget')
        koerper = quelle[anfang:anfang + 1200]
        self.assertIn('relief="flat"', koerper)
        self.assertIn("borderwidth=0", koerper)
        self.assertNotIn('relief="solid"', koerper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
