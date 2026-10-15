# -*- coding: utf-8 -*-
"""Das Nachziehen der gezeichneten Pillen laesst Unveraendertes aus (Messung vom 11.10.2026) - aber nie, was sich aendert.

Anlass: Jede Umschaltung der Ansicht oder Aufgabe zeichnete alle runden Flaechen neu - ``RoundedButton.nachziehen`` je
Knopf, ``_pillenfeld_zeichnen`` je Eingabefeld und Klappliste. Gemessen kostete eine Umschaltung zurueck nach UMWANDELN
1,6 s, davon gut die Haelfte fuers Neuzeichnen von Bildern, die sich nicht geaendert hatten. Seitdem gilt:

* ``RoundedButton.nachziehen`` zeichnet nur, wenn sich der Stand geaendert hat (Groesse, Farben, Hover, Sperre, Text,
  Schrift, Ausschnitt dahinter, Skalierung) oder das Bild fehlt;
* ``_pillenfeld_zeichnen`` ebenso (Groesse, Ausschnitt, Palette, Schriftfarben);
* ``rund_rechteck`` merkt sich kleine Bilder und gibt immer eine Kopie heraus (``test_bibliothek_zeichnen``).

Die Gegenprobe steht in jedem Test: Aendert sich etwas, wird gezeichnet.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("pillen_nachziehen")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from PIL import Image                                       # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _ruhen(sekunden: float, fenster=None) -> None:
    ende = time.perf_counter() + sekunden
    while time.perf_counter() < ende:
        (fenster or _WURZEL).update()
        time.sleep(0.01)


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class KnopfTests(unittest.TestCase):
    """``RoundedButton`` als Pille auf einem eigenen, unsichtbaren Fenster."""

    def setUp(self) -> None:
        self.fenster = tk.Toplevel(_WURZEL)
        try:
            self.fenster.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.addCleanup(self.fenster.destroy)
        self.grund = {"farbe": (30, 30, 40)}                  # der Ausschnitt dahinter - aenderbar wie ein Hintergrundbild
        self.knopf = APP.RoundedButton(
            self.fenster, text="Probe", command=lambda: None, font=("Segoe UI", 10, "bold"),
            bg="#222222", fg="#ffffff", activebackground="#3355aa", activeforeground="#ffffff", outline="#555555",
            radius=8, height=36, width=160, pille=True,
            hintergrund=lambda _w, b, h: Image.new("RGB", (b, h), self.grund["farbe"]))
        self.knopf.pack(padx=10, pady=10)
        _ruhen(0.4, self.fenster)
        self.zeichnungen: list[int] = []
        original = self.knopf._pille_zeichnen

        def zaehlen(*a, **k):
            self.zeichnungen.append(1)
            return original(*a, **k)

        self.knopf._pille_zeichnen = zaehlen

    def _nachziehen(self) -> int:
        vorher = len(self.zeichnungen)
        self.knopf.nachziehen()
        return len(self.zeichnungen) - vorher

    def test_unveraendert_wird_nicht_neu_gezeichnet(self) -> None:
        self.knopf.nachziehen()                              # setzt den Stand sicher
        self.assertEqual(0, self._nachziehen())
        self.assertEqual(0, self._nachziehen())
        self.assertTrue(self.knopf.find_all(), "das Bild steht noch da")

    def test_hover_wird_neu_gezeichnet(self) -> None:
        self.knopf.nachziehen()
        self.knopf._hovering = True
        self.assertEqual(1, self._nachziehen())

    def test_neue_farbe_wird_neu_gezeichnet(self) -> None:
        self.knopf.nachziehen()
        self.knopf._bg = "#334455"
        self.assertEqual(1, self._nachziehen())

    def test_neuer_text_wird_neu_gezeichnet(self) -> None:
        self.knopf.nachziehen()
        self.knopf._text = "Anderer Text"
        self.assertEqual(1, self._nachziehen())

    def test_anderer_ausschnitt_dahinter_wird_neu_gezeichnet(self) -> None:
        """Zieht der Knopf um oder wechselt das Hintergrundbild, aendert sich der Ausschnitt."""
        self.knopf.nachziehen()
        self.grund["farbe"] = (90, 20, 20)
        self.assertEqual(1, self._nachziehen())
        self.assertEqual(0, self._nachziehen(), "danach wieder unveraendert")

    def test_gesperrt_wird_neu_gezeichnet(self) -> None:
        self.knopf.nachziehen()
        self.knopf._state = tk.DISABLED
        self.assertEqual(1, self._nachziehen())

    def test_ein_geleertes_bild_wird_neu_gezeichnet(self) -> None:
        self.knopf.nachziehen()
        self.knopf.delete("all")
        self.assertEqual(1, self._nachziehen())
        self.assertTrue(self.knopf.find_all())

    def test_ein_neuer_knopf_zeichnet_beim_ersten_nachziehen(self) -> None:
        neu = APP.RoundedButton(self.fenster, text="Neu", command=lambda: None, font=("Segoe UI", 10), bg="#222222",
                                fg="#ffffff", outline="#555555", height=30, width=100, pille=True)
        neu._gezeichnet = None
        gezeichnet: list[int] = []
        original = neu._pille_zeichnen
        neu._pille_zeichnen = lambda *a, **k: (gezeichnet.append(1), original(*a, **k))[1]
        neu.pack()
        _ruhen(0.3, self.fenster)
        gezeichnet.clear()
        neu.nachziehen()
        neu.nachziehen()
        self.assertLessEqual(len(gezeichnet), 1, "hoechstens einmal, dann ist der Stand bekannt")

    def test_die_form_ohne_pille_wird_immer_gezeichnet(self) -> None:
        eckig = APP.RoundedButton(self.fenster, text="Eckig", command=lambda: None, font=("Segoe UI", 10), bg="#222222",
                                  fg="#ffffff", radius=8, height=30, width=100, pille=False)
        eckig.pack()
        _ruhen(0.2, self.fenster)
        gezeichnet: list[int] = []
        original = eckig._redraw
        eckig._redraw = lambda: (gezeichnet.append(1), original())[1]
        eckig.nachziehen()
        eckig.nachziehen()
        self.assertEqual(2, len(gezeichnet), "ohne Pillenform gibt es nichts zu sparen")


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class PillenfeldTests(unittest.TestCase):
    """Die Eingabefelder und Klapplisten des Hauptfensters (``_pillenfeld_zeichnen``)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fenster = tk.Toplevel(_WURZEL)
        try:
            cls.fenster.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.app = APP.PS5ConverterGUI(cls.fenster)
        cls.app._current_language = "de"
        _ruhen(2.0, cls.fenster)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.fenster.destroy()
        except Exception:  # noqa: BLE001
            pass

    def _feld(self):
        feld = self.app.compression_combo
        self.assertTrue(getattr(feld, "_pille", None), "die Klappliste ist ein Pillenfeld")
        return feld

    def _zeichnungen(self, aktion) -> int:
        z = APP.bibliothek_zeichnen
        original = z.rund_rechteck
        n: list[int] = []
        with mock.patch.object(z, "rund_rechteck", side_effect=lambda *a, **k: (n.append(1), original(*a, **k))[1]):
            aktion()
        return len(n)

    def test_unveraendert_wird_nichts_gerechnet(self) -> None:
        feld = self._feld()
        self.app._pillenfeld_zeichnen(feld)                    # sicher gezeichnet
        self.assertEqual(0, self._zeichnungen(lambda: self.app._pillenfeld_zeichnen(feld)))
        self.assertEqual(0, self._zeichnungen(lambda: self.app._pillenfeld_zeichnen(feld)))

    def test_andere_palette_wird_neu_gerechnet(self) -> None:
        feld = self._feld()
        self.app._pillenfeld_zeichnen(feld)
        alt = self.app._COLORS["border"]
        self.addCleanup(self.app._COLORS.__setitem__, "border", alt)
        self.app._COLORS["border"] = "#c0ffee" if alt != "#c0ffee" else "#facade"
        self.assertEqual(3, self._zeichnungen(lambda: self.app._pillenfeld_zeichnen(feld)),
                         "drei Zustaende: normal, hover, gesperrt")

    def test_die_ganze_umschaltung_kodiert_kein_pillenfeld_neu(self) -> None:
        """Alle Pillen nachziehen, ohne dass sich etwas aendert: kein Pillenfeld wird neu zum PNG gerechnet.

        Uebrig bleiben die sechs Haken-Kaestchen (je eine Rundung, jetzt aus dem Merker) - sie sind billig."""
        self.app._runde_flaechen_jetzt()                       # Ausgangsstand
        _ruhen(0.2, self.fenster)
        self.app._runde_flaechen_jetzt()
        kodiert: list[int] = []
        original = APP.PS5ConverterGUI._png64
        with mock.patch.object(APP.PS5ConverterGUI, "_png64",
                               staticmethod(lambda bild: (kodiert.append(1), original(bild))[1])):
            self.app._runde_flaechen_jetzt()
        self.assertEqual(0, len(kodiert), "es wurden %d Felderbilder neu kodiert" % len(kodiert))


if __name__ == "__main__":
    unittest.main()
