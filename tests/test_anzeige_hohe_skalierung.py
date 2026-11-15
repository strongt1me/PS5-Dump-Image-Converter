# -*- coding: utf-8 -*-
"""Vier Anzeigefehler bei hoher Windows-Skalierung und in anderen Sprachen (gemessen am 15.11.2026).

Die Messung lief am laufenden Programm, **nacheinander** (parallele Laeufe lieferten andere Ergebnisse: die verzoegerten
Anpassungen fehlten), je Seite und Sprache, mit einer Selbstprobe aus absichtlich Kaputtem:

* **Statuszeile** unter dem Protokoll: ein langer Einzeiler wurde ab 150 % rechts abgeschnitten (bei 200 % fehlten
  1773 - 1049 px).
* **Haken** (``RunderHaken``): Die Breite kam vom Systemhaken, das gezeichnete Kaestchen waechst staerker; "AMPR EMU",
  "BACKPORT", "Quelle nach Erfolg loeschen" standen bei 200 % 8-9 px zu breit im Feld.
* **Labels mit fester Zeichenbreite** (``width=16``): spanisch "Destino (ID de título):" und franzoesisch "Destination (ID de
  titre) :" wurden abgeschnitten.
* **Mindestgroesse** des Hauptfensters: blieb bei 150 % und mehr auf dem bei 125 % geeichten Mass; im kleinsten Fenster ragte
  alles ueber den Rand (99 Befunde, bei 100 und 125 % keiner).

Bis 125 % bleibt jedes Mass, wie es war - das ist der Eichpunkt, an dem alle Pixelzusicherungen des Pruefbestands stehen.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import unittest
from unittest import mock

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJEKT)

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

SCHRIFT = (APP.UI_SCHRIFT, APP.pt(9))
#: ``tk scaling`` bei 125 % (der Eichpunkt) und bei 200 %.
SK_125, SK_150, SK_200 = 1.6683, 2.0, 2.6667


class _Skalierung:
    """Stellt ``tk scaling`` um und gibt es danach zurueck (die Wurzel gehoert allen Tests)."""

    def __init__(self, wert: float) -> None:
        self.wert = wert

    def __enter__(self):
        self.vorher = float(_WURZEL.tk.call("tk", "scaling"))
        _WURZEL.tk.call("tk", "scaling", self.wert)
        return self

    def __exit__(self, *_a) -> None:
        _WURZEL.tk.call("tk", "scaling", self.vorher)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class HakenBreiteTests(unittest.TestCase):

    TEXTE = ("AMPR EMU", "BACKPORT", "PlayGo", "DLC EMU", "Vollständige Prüfung", "Quelle nach Erfolg löschen",
             "Rechner nach erfolgreichem Abschluss herunterfahren")

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)

    def _haken(self, text: str, fett: bool = False) -> "APP.RunderHaken":
        schrift = (APP.UI_SCHRIFT, APP.pt(9), "bold") if fett else SCHRIFT
        haken = APP.RunderHaken(self.top, text=text, variable=tk.BooleanVar(master=self.top), font=schrift)
        haken.pack()
        self.top.update()
        return haken

    def test_bei_200_prozent_passt_die_beschriftung_ins_feld(self) -> None:
        with _Skalierung(SK_200):
            for text in self.TEXTE:
                with self.subTest(text=text):
                    haken = self._haken(text)
                    self.assertGreaterEqual(haken.winfo_reqwidth(), haken._breite_fuer_text(haken.winfo_reqheight()))

    def test_bei_125_prozent_bleibt_die_breite_die_des_zwillings(self) -> None:
        """Der Eichpunkt: Dort passt der Zwilling schon, es darf sich kein Pixel aendern."""
        with _Skalierung(SK_125):
            for text in self.TEXTE:
                with self.subTest(text=text):
                    haken = self._haken(text)
                    zwilling = tk.Checkbutton(self.top, text=text, font=SCHRIFT)
                    breite = zwilling.winfo_reqwidth()
                    zwilling.destroy()
                    if APP._tk_hauptfassung(haken) >= 9:
                        breite -= APP._TK9_CHECKBUTTON_ZUGABE
                    self.assertGreaterEqual(breite, haken._breite_fuer_text(haken.winfo_reqheight()))
                    self.assertEqual(breite, haken.winfo_reqwidth())

    def test_der_wunschwert_waechst_mit_der_skalierung(self) -> None:
        with _Skalierung(SK_125):
            klein = self._haken("BACKPORT", fett=True)._breite_fuer_text(40)
        with _Skalierung(SK_200):
            gross = self._haken("BACKPORT", fett=True)._breite_fuer_text(40)
        self.assertGreater(gross, klein)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class LabelBreiteTests(unittest.TestCase):

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)

    def _label(self, text: str, breite: int = 16, **optionen) -> tk.Label:
        label = tk.Label(self.top, text=text, width=breite, anchor="w", font=SCHRIFT, **optionen)
        label.pack()
        self.top.update()
        return label

    def test_zu_langer_text_macht_das_label_breiter(self) -> None:
        label = self._label("Destination (ID de titre) : mit viel Zusatztext")
        vorher = label.winfo_reqwidth()
        APP.PS5ConverterGUI._label_breite_sichern(label)
        self.top.update()
        self.assertGreater(label.winfo_reqwidth(), vorher)
        schrift = tk.font.Font(root=_WURZEL, font=SCHRIFT)
        self.assertGreaterEqual(label.winfo_reqwidth(), schrift.measure(label.cget("text")))

    def test_kurzer_text_bleibt_beim_eingetragenen_mass(self) -> None:
        label = self._label("Ziel:")
        vorher = label.winfo_reqwidth()
        APP.PS5ConverterGUI._label_breite_sichern(label)
        self.assertEqual(vorher, label.winfo_reqwidth())

    def test_nach_dem_sprachwechsel_geht_die_breite_zurueck(self) -> None:
        label = self._label("Ziel:")
        grundmass = label.winfo_reqwidth()
        label.configure(text="Destination (ID de titre) : mit viel Zusatztext")
        APP.PS5ConverterGUI._label_breite_sichern(label)
        self.top.update()
        self.assertGreater(label.winfo_reqwidth(), grundmass)
        label.configure(text="Ziel:")
        APP.PS5ConverterGUI._label_breite_sichern(label)
        self.top.update()
        self.assertEqual(grundmass, label.winfo_reqwidth())

    def test_ein_label_ohne_feste_breite_oder_mit_bild_bleibt_unberuehrt(self) -> None:
        ohne = tk.Label(self.top, text="Ein sehr langer Text ohne feste Breite")
        ohne.pack()
        APP.PS5ConverterGUI._label_breite_sichern(ohne)          # width=0: nichts zu tun, wirft nicht
        self.assertEqual("0", str(ohne.cget("width")))
        APP.PS5ConverterGUI._label_breite_sichern(tk.Frame(self.top))       # kein Label: wirft nicht

    def test_registrierung_und_neubeschriftung_sichern_die_breite(self) -> None:
        with open(os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py"), encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertEqual(2, quelle.count("self._label_breite_sichern(widget)"), "Registrierung und _apply_language")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class MindestgroesseTests(unittest.TestCase):

    def _gui(self) -> object:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)
        gui.root = self.top
        gui._aufloesung_manuell = None          # keine Aufloesung von Hand gewaehlt
        return gui

    def test_bis_125_prozent_bleibt_das_eichmass(self) -> None:
        gui = self._gui()
        with _Skalierung(SK_125), mock.patch.object(APP, "IST_MACOS", False):
            self.top.minsize(APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT)
            gui._mindestgroesse_setzen()
            self.assertEqual((APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT), self.top.minsize())

    def test_bei_150_prozent_waechst_das_minimum(self) -> None:
        gui = self._gui()
        with _Skalierung(SK_150), mock.patch.object(APP, "IST_MACOS", False):
            self.top.minsize(APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT)
            gui._mindestgroesse_setzen()
            breite, hoehe = self.top.minsize()
            schirm_b, schirm_h = self.top.winfo_screenwidth(), self.top.winfo_screenheight()
            self.assertGreater(breite, APP.WINDOW_MIN_WIDTH if schirm_b > APP.WINDOW_MIN_WIDTH else 0)
            self.assertLessEqual(breite, schirm_b, "nie ueber den Bildschirm")
            self.assertLessEqual(hoehe, schirm_h - 72, "unten bleibt Platz fuer die Taskleiste")
            self.assertGreaterEqual(hoehe, APP.WINDOW_MIN_HEIGHT)

    def test_das_minimum_ist_nie_kleiner_als_das_eichmass(self) -> None:
        gui = self._gui()
        with _Skalierung(SK_200), mock.patch.object(APP, "IST_MACOS", False):
            gui._mindestgroesse_setzen()
            breite, hoehe = self.top.minsize()
            self.assertGreaterEqual(breite, APP.WINDOW_MIN_WIDTH)
            self.assertGreaterEqual(hoehe, APP.WINDOW_MIN_HEIGHT)

    def test_unter_linux_waechst_das_minimum_ebenfalls(self) -> None:
        """Unter Linux gemessen (WSL, 15.11.2026): im kleinsten Fenster bei 150 % derselbe Fehler wie unter Windows."""
        gui = self._gui()
        with _Skalierung(SK_150), mock.patch.object(APP, "IST_MACOS", False), \
                mock.patch.object(APP, "IST_WINDOWS", False), mock.patch.object(APP, "IST_LINUX", True):
            self.top.minsize(APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT)
            gui._mindestgroesse_setzen()
            breite, hoehe = self.top.minsize()
            self.assertGreaterEqual(breite, APP.WINDOW_MIN_WIDTH)
            if self.top.winfo_screenwidth() > APP.WINDOW_MIN_WIDTH * 1.2:
                self.assertGreater(breite, APP.WINDOW_MIN_WIDTH)

    def test_unter_macos_unveraendert(self) -> None:
        gui = self._gui()
        with _Skalierung(SK_200), mock.patch.object(APP, "IST_MACOS", True):
            self.top.minsize(APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT)
            gui._mindestgroesse_setzen()
            self.assertEqual((APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT), self.top.minsize())

    def test_der_aufruf_steht_nach_der_skalierung_im_konstruktor(self) -> None:
        with open(os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py"), encoding="utf-8") as datei:
            quelle = datei.read()
        a = quelle.index("self._anzeige_einstellungen_anwenden()\n        self._mindestgroesse_setzen()")
        self.assertGreater(a, 0)


class StatuszeileQuelltextTests(unittest.TestCase):
    """Die Statuszeile bricht um: Behaelter-Ereignis, Zelle des Rasters, Zuschnitt des Hintergrundbilds verwerfen."""

    def test_umbruch_haengt_am_behaelter_und_verwirft_den_zuschnitt(self) -> None:
        with open(os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py"), encoding="utf-8") as datei:
            quelle = datei.read()
        anfang = quelle.index("def _statuszeile_anwenden() -> None:")
        block = quelle[anfang:anfang + 1800]
        self.assertIn("content_area.grid_bbox(0, 5)", block)
        self.assertIn('self.status_label.configure(wraplength=neu)', block)
        self.assertIn("self.status_label._caption_natural_size = None", block)
        self.assertIn('content_area.bind("<Configure>", _statuszeile_umbrechen, add="+")', quelle)
        self.assertIn('self.status_label.bind("<Configure>", _statuszeile_umbrechen, add="+")', quelle)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class StatuszeileTests(unittest.TestCase):
    """Am echten Programmfenster: Ein sehr langer Statustext wird umbrochen statt abgeschnitten."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk.Toplevel(_WURZEL)
        try:
            cls.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.app = APP.PS5ConverterGUI(cls.root)
        cls.app._current_language = "de"
        cls.app._apply_language()
        cls.app._online_nachschlag_erlaubt = lambda: False
        cls.root.geometry("1400x900")
        cls._ruhen(1.5)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def _ruhen(cls, sekunden: float) -> None:
        import time
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            cls.root.update()
            time.sleep(0.01)

    def test_langer_text_wird_umbrochen_und_nicht_abgeschnitten(self) -> None:
        lang = "Extrahiert eine .ffpfsc/.ffpfs-Datei und baut daraus wieder den Dump-Ordner auf " * 6
        self.app.status_label.config(text=lang)
        self._ruhen(1.0)
        label = self.app.status_label
        self.assertGreater(int(float(str(label.cget("wraplength")))), 100, "Umbruch gesetzt")
        self.assertGreaterEqual(label.winfo_width(), label.winfo_reqwidth() - 1, "nicht schmaler als bestellt")
        self.assertGreater(label.winfo_height(), 40, "mehrzeilig")

    def test_kurzer_text_bleibt_einzeilig(self) -> None:
        self.app.status_label.config(text="Bereit.")
        self._ruhen(0.6)
        self.assertLess(self.app.status_label.winfo_height(), 40)

    def test_werkzeugfenster_halten_labels_mit_fester_breite_breit_genug(self) -> None:
        """``_fenster_auf_inhalt_wachsen`` sichert vor dem Messen alle Labels mit fester Zeichenbreite (unjail, JS Loader ...)."""
        fenster = tk.Toplevel(self.root)
        self.addCleanup(fenster.destroy)
        label = tk.Label(fenster, text="Destination (ID de titre) : mit viel Zusatztext", width=8, anchor="w", font=SCHRIFT)
        label.pack()
        fenster.update()
        schmal = label.winfo_reqwidth()
        self.app._fenster_auf_inhalt_wachsen(fenster, 300, 200, True)
        fenster.update()
        self.assertGreater(label.winfo_reqwidth(), schmal)


    def test_langer_fenstertitel_bricht_um_statt_abgeschnitten_zu_werden(self) -> None:
        """Der PKG-Merger traegt den ganzen Ordnerpfad im Titel (2014 px bei 150 %, Platz 1840 px)."""
        fenster = tk.Toplevel(self.root)
        self.addCleanup(fenster.destroy)
        fenster.geometry("700x300")
        kopf = self.app._build_modern_header(fenster, "PKG-Merger – " + "C:\\sehr\\langer\\Pfad\\" * 20)
        self._ruhen(0.6)
        titel = kopf.winfo_children()[0]
        self.assertGreater(int(float(str(titel.cget("wraplength")))), 100, "Umbruch gesetzt")
        self.assertGreaterEqual(titel.winfo_width(), titel.winfo_reqwidth() - 1, "nicht schmaler als bestellt")
        self.assertGreater(titel.winfo_height(), 50, "mehrzeilig")

    def test_kurzer_fenstertitel_bleibt_einzeilig(self) -> None:
        fenster = tk.Toplevel(self.root)
        self.addCleanup(fenster.destroy)
        fenster.geometry("700x300")
        kopf = self.app._build_modern_header(fenster, "Diagnose")
        self._ruhen(0.4)
        self.assertLess(kopf.winfo_children()[0].winfo_height(), 50)


class WerkzeugfensterQuelltextTests(unittest.TestCase):
    """Die Fenster, die bei hoher Skalierung auffielen (AMPR Picker, unjail, Spiel-Details)."""

    def test_spiel_detail_packt_die_knopfleiste_vor_dem_notebook(self) -> None:
        with open(os.path.join(PROJEKT, "ps5_validator", "ui", "spiel_detail_fenster.py"), encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertLess(quelle.index('leiste.pack(side="bottom", fill="x")'),
                        quelle.index('nb.pack(fill="both", expand=True'),
                        "Pack kuerzt, was zuletzt kommt: Die Knopfleiste darf nicht nach dem Notebook stehen")

    @staticmethod
    def _quelle() -> str:
        with open(os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py"), encoding="utf-8") as datei:
            return datei.read()

    def test_der_picker_waechst_mit_seinem_inhalt(self) -> None:
        quelle = self._quelle()
        anfang = quelle.index("    def _show_ampr_ftp_picker(")
        ende = quelle.index("\n    def ", anfang + 10)
        block = quelle[anfang:ende]
        self.assertIn("win.minsize(w, h)", block)
        self.assertIn("self._fenster_auf_inhalt_wachsen(win, w, h, True)", block)

    def test_die_labelsicherung_steht_vor_der_messung_des_platzbedarfs(self) -> None:
        quelle = self._quelle()
        anfang = quelle.index("    def _fenster_auf_inhalt_wachsen(")
        block = quelle[anfang:anfang + 6000]
        self.assertLess(block.index("_labels_sichern(win)"), block.index("noetig_b, noetig_h = win.winfo_reqwidth()"))

    def test_unjail_packt_die_statuszeile_vor_dem_protokoll(self) -> None:
        quelle = self._quelle()
        anfang = quelle.index("    def _show_unjail_sender(")
        block = quelle[anfang:anfang + 9000]
        status = block.index('textvariable=status_var')
        protokoll = block.index("protokoll.pack(fill=\"both\", expand=True")
        self.assertLess(status, protokoll, "Pack kuerzt, was zuletzt kommt: Die Statuszeile darf nicht zuletzt stehen")
        self.assertIn('.pack(side="bottom", fill="x")', block[status:protokoll])


if __name__ == "__main__":
    unittest.main(verbosity=2)
