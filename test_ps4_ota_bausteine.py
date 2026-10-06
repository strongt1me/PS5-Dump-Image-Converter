# -*- coding: utf-8 -*-
"""Tests fuer die runden Bausteine von „PS4 PKG -> OTA“ (``ps5_validator/ui/ps4_ota_bausteine.py``).

Die Bausteine stehen auf der gemeinsamen, verborgenen Tk-Wurzel; das Hauptprogramm liefert
Palette und Mass. Menues werden nicht geoeffnet (``tk_popup`` blockiert unter Windows) - der
Test greift sich das Menue ab und ruft seine Eintraege.
"""
from __future__ import annotations

import gc
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ps4_ota_bausteine")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import ps4_ota_bausteine as bs        # noqa: E402
from ps5_validator.utils import bibliothek_raster as raster  # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    from PIL import ImageTk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _bilder(canvas) -> list:
    return [i for i in canvas.find_all() if canvas.type(i) == "image"]


@unittest.skipUnless(_TK_DA, "Ohne Tk keine Fensterprobe.")
class BausteinTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.look = bs.Look(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        self.c = self.app._COLORS
        self.win = tk.Toplevel(_WURZEL, bg=self.c["bg_card"])
        self.win.withdraw()
        self.addCleanup(self.win.destroy)

    def tearDown(self) -> None:
        gc.collect()

    # --- Look ---------------------------------------------------------------------------
    def test_die_rolle_der_flaeche_folgt_der_farbe_des_elternteils(self) -> None:
        for rolle in ("bg_card", "bg_main", "console_bg"):
            rahmen = tk.Frame(self.win, bg=self.c[rolle])
            with self.subTest(rolle=rolle):
                self.assertEqual(rolle, self.look.grund_von(rahmen))
        fremd = tk.Frame(self.win, bg="#123456")
        self.assertEqual("bg_card", self.look.grund_von(fremd), "Ohne Treffer gilt die Kartenfarbe.")

    def test_knoepfe_stehen_auf_der_farbe_ihres_elternteils(self) -> None:
        rahmen = tk.Frame(self.win, bg=self.c["bg_main"])
        knopf = self.look.knopf(rahmen, "Text", lambda: None)
        self.assertEqual(self.c["bg_main"], str(knopf.cget("bg")))
        karte = self.look.karte(rahmen)
        self.assertEqual("bg_main", karte._rollen[2], "Die Ecken der Karte zeigen die Farbe dahinter.")

    def test_der_akzentknopf_hat_keinen_schein_und_ist_so_hoch_wie_ein_gewoehnlicher(self) -> None:
        flach = self.look.knopf(self.win, "Entpacken", lambda: None, hoehe=32)
        haupt = self.look.knopf(self.win, "Senden", lambda: None, akzent=True, hoehe=32)
        mit_schein = raster.KartenKnopf(self.win, self.app._bibliothek_zeichner(), "Senden", None, "akzent", hoehe=32)
        self.assertEqual((0, 0, 0), self.look.z.glow_rand("akzent"))
        self.assertEqual(flach.winfo_reqheight(), haupt.winfo_reqheight())
        self.assertGreater(mit_schein.winfo_reqheight(), flach.winfo_reqheight(),
                           "Gegenprobe: Mit dem Schein der Bibliothek waere der Knopf hoeher.")

    def test_der_akzentknopf_bleibt_ein_verlauf_und_ein_gesperrter_wird_grau(self) -> None:
        z = self.look.z
        foto, versatz = z.knopf_foto("akzent", "normal", 120, 34)
        self.assertEqual((0, 0), versatz)
        bild = ImageTk.getimage(foto).convert("RGB")
        links, rechts = bild.getpixel((8, 17)), bild.getpixel((110, 17))
        self.assertNotEqual(links, rechts, "Waagerechter Verlauf wie STARTEN.")
        gesperrt = ImageTk.getimage(z.knopf_foto("akzent", "gesperrt", 120, 34)[0]).convert("RGB")
        self.assertEqual(gesperrt.getpixel((8, 17)), gesperrt.getpixel((110, 17)))

    # --- Knoepfe sperren ------------------------------------------------------------------
    def test_freigeben_zeichnet_nur_bei_einer_aenderung_neu(self) -> None:
        knopf = self.look.knopf(self.win, "X", lambda: None)
        with mock.patch.object(raster.KartenKnopf, "_zeichnen") as zeichnen:
            bs.freigeben(knopf, True)       # ist schon frei
            self.assertEqual(0, zeichnen.call_count)
            bs.freigeben(knopf, False)
            self.assertEqual(1, zeichnen.call_count)
            bs.freigeben(knopf, False)
            self.assertEqual(1, zeichnen.call_count)
        self.assertFalse(bs.ist_frei(knopf))
        bs.freigeben(knopf, True)
        self.assertTrue(bs.ist_frei(knopf))

    def test_ein_gesperrter_knopf_tut_nichts(self) -> None:
        gerufen = []
        knopf = self.look.knopf(self.win, "X", lambda: gerufen.append(1))
        bs.freigeben(knopf, False)
        knopf.invoke()
        self.assertEqual([], gerufen)
        bs.freigeben(knopf, True)
        knopf.invoke()
        self.assertEqual([1], gerufen)

    def test_freigeben_und_ist_frei_vertragen_ein_zerstoertes_widget(self) -> None:
        knopf = self.look.knopf(self.win, "X", lambda: None)
        knopf.destroy()
        bs.freigeben(knopf, False)                # darf nicht werfen
        self.assertFalse(bs.ist_frei(knopf))

    # --- Eingabefeld ------------------------------------------------------------------------
    def test_das_eingabefeld_haengt_an_der_variablen_und_hat_die_breite_in_zeichen(self) -> None:
        var = tk.StringVar(master=_WURZEL, value="abc")
        feld = self.look.eingabe(self.win, var, 7)
        self.assertEqual(7, int(feld.eingabe.cget("width")))
        self.assertEqual("abc", feld.eingabe.get())
        feld.eingabe.insert("end", "d")
        self.assertEqual("abcd", var.get())
        var.set("neu")
        self.assertEqual("neu", feld.eingabe.get())

    def test_ein_breiteres_feld_ist_breiter(self) -> None:
        schmal = self.look.eingabe(self.win, tk.StringVar(master=_WURZEL), 6)
        breit = self.look.eingabe(self.win, tk.StringVar(master=_WURZEL), 30)
        _WURZEL.update_idletasks()
        self.assertGreater(breit.winfo_reqwidth(), schmal.winfo_reqwidth() + 100)

    def test_im_fokus_hat_das_feld_einen_rand_in_der_akzentfarbe(self) -> None:
        feld = self.look.eingabe(self.win, tk.StringVar(master=_WURZEL), 10)
        self.assertEqual("border", feld._rollen[1])
        feld._fokus_setzen(True)
        self.assertTrue(feld.hat_fokus)
        self.assertEqual("fg_accent", feld._rollen[1])
        feld._fokus_setzen(False)
        self.assertEqual("border", feld._rollen[1])
        self.assertFalse(feld.hat_fokus)

    def test_das_eingabefeld_meldet_fokus_und_verlust_an_die_pille(self) -> None:
        """Ein verborgenes Fenster bekommt keine Fokusereignisse - geprueft wird, dass die Bindungen da sind."""
        feld = self.look.eingabe(self.win, tk.StringVar(master=_WURZEL), 10)
        bindungen = feld.eingabe.bind()
        self.assertIn("<FocusIn>", bindungen)
        self.assertIn("<FocusOut>", bindungen)

    def test_das_feld_ist_eine_pille(self) -> None:
        feld = self.look.eingabe(self.win, tk.StringVar(master=_WURZEL), 10)
        self.assertIsNone(feld._radius, "Radius None heisst: halbe Hoehe.")

    # --- Klappliste ------------------------------------------------------------------------------
    def _auswahl(self, werte=("Alle", "Spiel", "Update"), befehl=None):
        var = tk.StringVar(master=_WURZEL, value=werte[0])
        return self.look.auswahl(self.win, var, list(werte), befehl=befehl), var

    def test_die_auswahl_zeigt_den_wert_und_folgt_der_variablen(self) -> None:
        box, var = self._auswahl()
        self.assertEqual("Alle", box.cget("text"))
        var.set("Update")
        self.assertEqual("Update", box.cget("text"))

    def test_die_breite_der_auswahl_haengt_nicht_vom_gewaehlten_wert_ab(self) -> None:
        box, var = self._auswahl(("A", "Ein sehr langer Eintrag der Liste", "B"))
        _WURZEL.update_idletasks()
        breit = box.winfo_reqwidth()
        var.set("B")
        _WURZEL.update_idletasks()
        self.assertEqual(breit, box.winfo_reqwidth(), "Sonst huepfte die Zeile bei jeder Wahl.")
        lang = box.cget("text")
        self.assertEqual("B", lang)
        text = self.look.z.messen("knopf", "Ein sehr langer Eintrag der Liste")
        self.assertGreaterEqual(breit, text + self.look.z.px(40))

    def test_waehlen_setzt_die_variable_und_ruft_den_befehl_einmal(self) -> None:
        gerufen = []
        box, var = self._auswahl(befehl=lambda: gerufen.append(var.get()))
        box.waehlen("Spiel")
        self.assertEqual("Spiel", var.get())
        self.assertEqual(["Spiel"], gerufen)
        box.waehlen("Spiel")                       # gleiche Wahl: der Befehl laeuft trotzdem (wie ein Klick)
        self.assertEqual(["Spiel", "Spiel"], gerufen)

    def test_werte_tauschen_zieht_die_breite_nach(self) -> None:
        box, _var = self._auswahl(("Alle",))
        _WURZEL.update_idletasks()
        klein = box.winfo_reqwidth()
        box.werte_setzen(["Alle", "Ein ziemlich langer Name fuer eine Region"])
        _WURZEL.update_idletasks()
        self.assertGreater(box.winfo_reqwidth(), klein)
        self.assertEqual(["Alle", "Ein ziemlich langer Name fuer eine Region"], box.werte)

    def test_das_menue_der_auswahl_nennt_alle_werte_und_setzt_beim_klick(self) -> None:
        erfasst = []
        box, var = self._auswahl(befehl=None)
        with mock.patch.object(tk.Menu, "tk_popup", lambda menue, x, y: erfasst.append(menue)):
            box.invoke()
        menue = erfasst[0]
        self.assertEqual(["Alle", "Spiel", "Update"],
                         [menue.entrycget(i, "label") for i in range(menue.index("end") + 1)])
        menue.invoke(2)
        self.assertEqual("Update", var.get())

    def test_eine_zerstoerte_auswahl_laesst_ihre_variable_in_ruhe(self) -> None:
        box, var = self._auswahl()
        box.destroy()
        var.set("Spiel")                           # darf nicht in ein totes Widget schreiben
        self.assertEqual("Spiel", var.get())

    # --- Menueknopf --------------------------------------------------------------------------------
    def test_der_menueknopf_holt_die_werte_beim_oeffnen(self) -> None:
        gewaehlt = []
        werte = ["eins"]
        knopf = self.look.menue_knopf(self.win, "Wählen", lambda: list(werte), gewaehlt.append)
        erfasst = []
        with mock.patch.object(tk.Menu, "tk_popup", lambda menue, x, y: erfasst.append(menue)):
            knopf.invoke()
            werte.append("zwei")
            knopf.invoke()
        self.assertEqual(1, erfasst[0].index("end") + 1)
        self.assertEqual(2, erfasst[1].index("end") + 1, "Die Liste wird bei jedem Oeffnen neu geholt.")
        erfasst[1].invoke(1)
        self.assertEqual(["zwei"], gewaehlt)

    # --- Fortschritt -----------------------------------------------------------------------------------
    def test_der_fortschrittsbalken_begrenzt_und_zeichnet(self) -> None:
        balken = self.look.balken(self.win, breite=200, hoehe=12)
        balken.place(x=0, y=0, width=200, height=20)
        _WURZEL.update()
        self.assertEqual(0.0, balken.wert)
        for eingabe, soll in ((50, 50.0), (-5, 0.0), (250, 100.0), ("x", 0.0), (33.5, 33.5)):
            with self.subTest(eingabe=eingabe):
                balken.setzen(eingabe)
                self.assertEqual(soll, balken.wert)
        balken.setzen(40)
        _WURZEL.update()
        self.assertEqual(1, len(_bilder(balken)), "Rinne und Fuellung sind ein Bild.")

    def test_die_fuellung_waechst_mit_dem_wert(self) -> None:
        balken = self.look.balken(self.win, breite=200, hoehe=12)
        balken.place(x=0, y=0, width=200, height=20)
        _WURZEL.update()
        fuellung = []
        for prozent in (1, 50, 100):
            balken.setzen(prozent)
            _WURZEL.update()
            bild = ImageTk.getimage(balken._foto).convert("RGB")
            mitte = bild.height // 2
            # So weit rechts liegt der letzte Punkt, der nicht die Farbe der Rinne hat.
            tief = bild.getpixel((bild.width - 6, mitte))
            gefuellt = max((x for x in range(6, bild.width - 3) if bild.getpixel((x, mitte)) != tief), default=0)
            fuellung.append(gefuellt)
        self.assertLess(fuellung[0], fuellung[1])
        self.assertLess(fuellung[1], fuellung[2])

    # --- Rollbalken, Rahmen, Texte ----------------------------------------------------------------------------
    def test_die_rollbalken_nutzen_die_schmalen_stile_des_programms(self) -> None:
        self.assertEqual("Karte.Vertical.TScrollbar", str(self.look.rollbalken(self.win, "vertical", None).cget("style")))
        self.assertEqual("Karte.Horizontal.TScrollbar", str(self.look.rollbalken(self.win, "horizontal", None).cget("style")))
        self.assertEqual("Tief.Vertical.TScrollbar", str(self.look.rollbalken(self.win, "vertical", None, tief=True).cget("style")))
        self.assertEqual("Karte.Horizontal.TScrollbar",
                         str(self.look.rollbalken(self.win, "horizontal", None, tief=True).cget("style")),
                         "Waagerecht gibt es nur die Kartenfarbe.")

    def test_der_baumrahmen_borgt_seine_groesse_nicht_von_der_tabelle(self) -> None:
        rahmen = self.look.baumrahmen(self.win, 100)
        rahmen.pack()
        baum = ttk.Treeview(rahmen, columns=("a", "b"), show="headings")
        baum.column("a", width=900)
        baum.column("b", width=900)
        baum.pack(fill="both", expand=True)
        _WURZEL.update_idletasks()
        self.assertLess(rahmen.winfo_reqwidth(), 200, "Sonst wuchs das Fenster mit seinen Tabellen.")

    def test_hinweis_bricht_mit_der_breite_um(self) -> None:
        # Ein verborgenes Fenster meldet keine Groesse: durchsichtig (alpha 0) einblenden, ohne dass der
        # Anwender etwas davon sieht.
        self.win.attributes("-alpha", 0.0)
        self.win.geometry("700x300+30+30")
        self.win.deiconify()
        hinweis = self.look.hinweis(self.win, "Wort " * 60)
        for breite, soll in ((300, 292), (600, 592), (50, 120)):
            with self.subTest(breite=breite):
                hinweis.place(x=0, y=0, width=breite, height=100)
                _WURZEL.update()
                self.assertEqual(soll, int(hinweis.cget("wraplength")),
                                 "Nie schmaler als 120: Sonst bricht jedes Wort um." if breite == 50 else "")
        self.win.withdraw()

    def test_beschriftung_traegt_die_farbe_des_elternteils(self) -> None:
        rahmen = tk.Frame(self.win, bg=self.c["bg_main"])
        text = self.look.beschriftung(rahmen, "Hallo")
        self.assertEqual(self.c["bg_main"], str(text.cget("bg")))
        warnung = self.look.beschriftung(rahmen, "Achtung", farbe="fg_warning")
        self.assertEqual(self.c["fg_warning"], str(warnung.cget("fg")))

    # --- Ankreuzfeld ---------------------------------------------------------------------------------------------------
    def test_das_ankreuzfeld_kommt_vom_hauptprogramm_und_schaltet_um(self) -> None:
        var = tk.BooleanVar(master=_WURZEL, value=False)
        gerufen = []
        haken = self.look.haken(self.win, "Text", var, command=lambda: gerufen.append(var.get()))
        self.assertIsInstance(haken, APP.RunderHaken)
        haken.invoke()
        self.assertTrue(var.get())
        self.assertEqual([True], gerufen)
        warnung = self.look.haken(self.win, "Achtung", var, farbe="fg_warning")
        self.assertEqual(self.c["fg_warning"], warnung.cget("fg"))

    # --- Chips ----------------------------------------------------------------------------------------------------------------------
    def test_chips_haengen_an_der_variablen(self) -> None:
        var = tk.StringVar(master=_WURZEL, value="a")
        gerufen = []
        chips = self.look.chips(self.win, [("a", "Eins"), ("b", "Zwei")], var, befehl=lambda: gerufen.append(var.get()))
        self.assertEqual([True, False], [chip.an for chip in chips.chips])
        chips.chips[1].invoke()
        self.assertEqual("b", var.get())
        self.assertEqual(["b"], gerufen)
        self.assertEqual([False, True], [chip.an for chip in chips.chips])
        var.set("a")
        self.assertEqual([True, False], [chip.an for chip in chips.chips])


class QuelltextTests(unittest.TestCase):
    """Das Modul bindet nichts vom Hauptprogramm ein und nutzt nur die runden Teile."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "ps5_validator" / "ui" / "ps4_ota_bausteine.py").read_text(encoding="utf-8") \
            if (PROJEKT / "ps5_validator" / "ui" / "ps4_ota_bausteine.py").exists() else \
            Path(bs.__file__).read_text(encoding="utf-8")

    def test_kein_import_des_hauptprogramms(self) -> None:
        self.assertNotIn("PS5ImageConverter", self.quelle)

    def test_keine_eckigen_teile(self) -> None:
        for name in ("ttk.Button", "ttk.Combobox", "ttk.Notebook", "ttk.Progressbar", "tk.Checkbutton", "tk.Radiobutton"):
            with self.subTest(name=name):
                self.assertNotIn(name + "(", self.quelle)


if __name__ == "__main__":
    unittest.main()
