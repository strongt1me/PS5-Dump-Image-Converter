# -*- coding: utf-8 -*-
"""Pillenform der Oberflaeche (seit v1.9.62) - Waechter fuer die Fallen dieser Runde.

Nutzerwuensche vom 04.10.2026: Knoepfe, Felder und Klapplisten als Pillen wie in
der Bibliothek, die Seiten der Ansicht KONSOLE ebenso und schmalere Knoepfe in der
Seitenleiste. Wieder abbestellt am 05.10.2026: der pillenfoermige
Texthintergrund hinter Ueberschrift, Untertitel, Statuszeile und den
Beschriftungen der Karte (Variante A) - die Texte stehen direkt auf dem
Hintergrundbild, und auch der Drehknopf WORKER traegt keine Kachel mehr, sondern
den Ausschnitt des Bildes -, dazu die vier runden Ecken der Seitenleiste (sie
zeigten das Hauptbild, als laege es unter der Leiste) und die gemeinsame
Startlinie der Knopftexte in der Seitenleiste (der Text steht wieder mittig).

Geprueft wird, was dabei schiefging oder leicht wieder schiefgeht:

* Stil-, Element- und Bildnamen der Pillenfelder gelten im ganzen
  Tk-Interpreter. Ein Zaehler je Programmobjekt stiess beim zweiten Objekt auf
  derselben Wurzel auf "Pille1.field" - der Aufbau der Seite "Konsole &
  Payloads" brach ab (im Gesamtlauf: 26 Fehlschlaege in test_konsole_suche).
* Zwei Beschriftungen der Karte hatten keine Farbrolle und behielten nach einem
  Designwechsel die Schrift des Startdesigns - auf der hellen Pille unsichtbar.
* Die Seitenleiste haelt ihre Breite, obwohl die Knoepfe sie nicht mehr fuellen.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("pillenform")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek_raster            # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk

    from PIL import Image, ImageTk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

KLASSE = "PS5ConverterGUI"


def _palette() -> dict:
    return dict(APP.PS5ConverterGUI._THEMES["dunkel"])


def _nackt():
    """Ein Programmobjekt ohne Aufbau - nur Wurzel und Palette."""
    objekt = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    objekt.root = _WURZEL
    objekt._COLORS = _palette()
    return objekt


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class BausteinTests(unittest.TestCase):
    """Die neuen Bausteine ohne Hauptfenster."""

    def setUp(self) -> None:
        self.rahmen = tk.Frame(_WURZEL, bg="#0B0B0E")
        self.addCleanup(self.rahmen.destroy)

    def test_breite_nach_text_folgt_der_beschriftung(self) -> None:
        knopf = APP.RoundedButton(self.rahmen, text="Kurz", pille=True,
                                  breite_nach_text=True, polster_x=20)
        polster = APP.knopfmass(20, self.rahmen)
        self.assertEqual(knopf._textbreite() + 2 * polster, knopf.winfo_reqwidth())
        vorher = knopf.winfo_reqwidth()
        knopf.configure(text="Eine deutlich laengere Beschriftung")
        self.assertEqual(knopf._textbreite() + 2 * polster, knopf.winfo_reqwidth())
        self.assertGreater(knopf.winfo_reqwidth(), vorher, "Sprachwechsel zieht die Breite nach.")

    def test_ohne_breite_nach_text_bleibt_die_breite_stehen(self) -> None:
        knopf = APP.RoundedButton(self.rahmen, text="Kurz", width=150)
        vorher = knopf.winfo_reqwidth()
        knopf.configure(text="Eine deutlich laengere Beschriftung")
        self.assertEqual(vorher, knopf.winfo_reqwidth())

    def test_pillenfelder_zweier_programmobjekte_auf_einer_wurzel(self) -> None:
        """Vorher zaehlte jedes Objekt ab 1 - das zweite stiess auf 'Pille1.field'."""
        erstes, zweites = _nackt(), _nackt()
        stile = []
        for objekt in (erstes, zweites):
            feld = ttk.Entry(self.rahmen)
            objekt._pillenfeld(feld, mit_pfeil=False)             # darf nicht werfen
            stile.append(feld._pille["stil"])
        self.assertNotEqual(stile[0], stile[1])

    def test_pillenfelder_zweier_modulkopien_auf_einer_wurzel(self) -> None:
        """test_fensterlayout laedt das Hauptprogramm ein zweites Mal als Modul.

        Die beiden Klassen zaehlen dann getrennt - ein Klassenzaehler lieferte
        beiden "Pille1.field" (Gesamtlauf 04.10.2026).
        """
        spec = importlib.util.spec_from_file_location(
            "pillenform_zweitkopie", PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
        kopie = importlib.util.module_from_spec(spec)
        sys.modules["pillenform_zweitkopie"] = kopie
        self.addCleanup(sys.modules.pop, "pillenform_zweitkopie", None)
        spec.loader.exec_module(kopie)
        self.assertIsNot(kopie.PS5ConverterGUI, APP.PS5ConverterGUI)
        zweites = kopie.PS5ConverterGUI.__new__(kopie.PS5ConverterGUI)
        zweites.root = _WURZEL
        zweites._COLORS = _palette()
        stile = []
        for objekt in (_nackt(), zweites):
            feld = ttk.Entry(self.rahmen)
            objekt._pillenfeld(feld, mit_pfeil=False)             # darf nicht werfen
            stile.append(feld._pille["stil"])
        self.assertNotEqual(stile[0], stile[1])

    def test_die_runde_karte_kann_eine_pille_sein(self) -> None:
        zeichner = bibliothek_raster.Zeichner(_WURZEL, _palette, "Segoe UI")
        karte = bibliothek_raster.RundeKarte(self.rahmen, zeichner, radius=None)
        with mock.patch.object(karte, "winfo_width", return_value=200), \
                mock.patch.object(karte, "winfo_height", return_value=40):
            karte._bild_neu()
        bild = ImageTk.getimage(karte._foto)
        # (5, 5) liegt bei Radius 20 ausserhalb der Rundung, bei 16 x Faktor nicht.
        self.assertLess(bild.getpixel((5, 5))[3], 128)
        such = bibliothek_raster.SuchFeld(self.rahmen, zeichner, tk.StringVar(master=_WURZEL), "x")
        self.assertIsNone(such._radius, "Das Suchfeld ist eine Pille wie die Felder.")

    def test_knoepfe_der_bibliothek_sind_pillen(self) -> None:
        zeichner = bibliothek_raster.Zeichner(_WURZEL, _palette, "Segoe UI")
        foto, _versatz = zeichner.knopf_foto("flaeche", "normal", 120, 34)
        bild = ImageTk.getimage(foto)
        # (5, 3): bei Radius 10 innen, bei Radius 17 (halbe Hoehe) aussen.
        self.assertLess(bild.getpixel((5, 3))[3], 128)

    # --- Drehknopf: der Ausschnitt des Bildes statt einer Kachel (05.10.2026) -------------

    def _drehknopf(self, **kw):
        wert = tk.IntVar(master=_WURZEL, value=4)
        knopf = APP.Drehknopf(self.rahmen, variable=wert, von=1, bis=8, durchmesser=38, **kw)
        knopf.pack()
        _WURZEL.update_idletasks()
        return knopf, wert

    @staticmethod
    def _bilder(knopf) -> list:
        return [i for i in knopf.find_all() if knopf.type(i) == "image"]

    def test_drehknopf_traegt_den_ausschnitt_des_bildes(self) -> None:
        """Ein Canvas malt immer seine Farbe - als Kachel stand der Knopf auf dem Bild."""
        fragen = []

        def grund(_knopf, breite, hoehe):
            fragen.append((breite, hoehe))
            return Image.new("RGB", (breite, hoehe), (200, 30, 30))

        knopf, _wert = self._drehknopf(hintergrund=grund)
        self.assertEqual(1, len(self._bilder(knopf)))
        self.assertEqual("image", knopf.type(knopf.find_all()[0]), "Der Ausschnitt liegt UNTER dem Ring.")
        foto = ImageTk.getimage(knopf._grund_merker[1])
        self.assertEqual((200, 30, 30), foto.convert("RGB").getpixel((1, 1)))
        self.assertEqual([(38, 38)], fragen)
        # Beim Ziehen zeichnet der Knopf oft - gefragt wird nur einmal.
        for neu in (5, 6, 7, 3):
            knopf._wert_setzen(neu)
        self.assertEqual(1, len(fragen))
        # Nach dem Verschieben holt ``nachziehen`` einen neuen Ausschnitt.
        knopf.nachziehen()
        self.assertEqual(2, len(fragen))

    def test_drehknopf_holt_bei_neuer_groesse_einen_neuen_ausschnitt(self) -> None:
        fragen = []

        def grund(_knopf, breite, hoehe):
            fragen.append((breite, hoehe))
            return Image.new("RGB", (breite, hoehe), (1, 2, 3))

        knopf, _wert = self._drehknopf(hintergrund=grund)
        knopf.durchmesser_setzen(30, breite=60)
        self.assertEqual([(38, 38), (60, 30)], fragen)

    def test_drehknopf_ohne_ausschnitt_bleibt_wie_vorher(self) -> None:
        knopf, _wert = self._drehknopf()
        self.assertEqual([], self._bilder(knopf))

    def test_ein_fehlschlagender_ausschnitt_stoert_den_drehknopf_nicht(self) -> None:
        def kaputt(_knopf, _breite, _hoehe):
            raise ValueError("kein Bild")

        knopf, wert = self._drehknopf(hintergrund=kaputt)
        self.assertEqual([], self._bilder(knopf))
        knopf._wert_setzen(6)                       # zeichnet weiter
        self.assertEqual(6, wert.get())

    def test_drehknopf_fragt_ohne_hintergrundbild_nicht_bei_jedem_zeichnen(self) -> None:
        fragen = []

        def keins(_knopf, _breite, _hoehe):
            fragen.append(1)
            return None

        knopf, _wert = self._drehknopf(hintergrund=keins)
        for neu in (2, 3, 5):
            knopf._wert_setzen(neu)
        self.assertEqual(1, len(fragen))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class HauptfensterTests(unittest.TestCase):
    """Am wirklichen Programm - ein Objekt fuer alle Tests."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def test_die_seitenleiste_behaelt_ihre_breite(self) -> None:
        app = self.app
        erwartet = int(round(_WURZEL.winfo_fpixels("10c"))) + 20
        self.assertEqual(erwartet, app._seitenleiste_breite)
        self.assertEqual(erwartet, int(_WURZEL.grid_columnconfigure(0)["minsize"]))

    def test_die_knoepfe_der_seitenleiste_sind_gleich_breit_und_schmaler(self) -> None:
        app = self.app
        knoepfe = app._seitenleiste_knoepfe()
        self.assertGreaterEqual(len(knoepfe), 15, "Umschalter, 8 Aufgaben, 4 KONSOLE, 2 im Fuss")
        breiten = {int(k.winfo_reqwidth()) for k in knoepfe}
        self.assertEqual(1, len(breiten), breiten)
        luft = APP.knopfmass(app._SEITENLEISTE_LUFT, _WURZEL)
        soll = min(max(k._textbreite() for k in knoepfe) + 2 * luft,
                   app._seitenleiste_breite - 20)
        self.assertEqual({soll}, breiten)
        self.assertLess(soll, app._seitenleiste_breite - 20,
                        "Bei deutschem Text bleibt links und rechts Platz in der Leiste.")

    def test_nach_dem_sprachwechsel_weiter_gleich_breit(self) -> None:
        app = self.app
        app._toggle_language()
        self.addCleanup(app._toggle_language)
        self.assertEqual(1, len({int(k.winfo_reqwidth()) for k in app._seitenleiste_knoepfe()}))

    def test_die_seitenleiste_hat_zeilen_und_einen_umschalter(self) -> None:
        """13.10.2026 (Nutzerwahl, Entwurf A "Linienliste mit Balken"): Aufgaben, Konsolenseiten und Fuss sind
        Zeilen mit linksbuendiger Schrift; nur der Umschalter der Ansichten bleibt eine Pille - hoeher, mit
        kleiner Kopfzeile ueber der mittig stehenden Beschriftung.

        Gezeichnet wird direkt (``_pille_zeichnen``): Die KONSOLE-Knoepfe sind in UMWANDELN nicht eingeblendet und
        haben dort keine Breite.
        """
        app = self.app
        zeilen = [k for k in app._seitenleiste_knoepfe() if k is not app._ansicht_knopf]
        self.assertGreaterEqual(len(zeilen), 19)
        for knopf in zeilen:
            with self.subTest(text=knopf._text):
                self.assertTrue(knopf._zeile)
                knopf.delete("all")
                knopf._pille_zeichnen(300, 38, "#202020", "#ffffff", False)
                texte = [i for i in knopf.find_all() if knopf.type(i) == "text"]
                self.assertIn(len(texte), (1, 2, 3), "Nummer, Beschriftung und Pfeil")
                for i in texte:
                    self.assertEqual(19.0, float(knopf.coords(i)[1]), "Die Schrift steht nicht auf halber Hoehe")
                erster = min(texte, key=lambda i: float(knopf.coords(i)[0]))
                self.assertEqual("w", knopf.itemcget(erster, "anchor"))
                self.assertGreaterEqual(float(knopf.coords(erster)[0]), 10.0, "Die Schrift klebt am Rand")
        umschalter = app._ansicht_knopf
        self.assertFalse(umschalter._zeile)
        self.assertGreaterEqual(int(umschalter.winfo_reqheight()), int(zeilen[0].winfo_reqheight()) + 8,
                                "Der Umschalter muss hoeher sein als eine Zeile.")
        umschalter.delete("all")
        umschalter._pille_zeichnen(300, 58, "#202020", "#ffffff", False)
        texte = [i for i in umschalter.find_all() if umschalter.type(i) == "text"]
        self.assertEqual(2, len(texte), "Kopfzeile und Beschriftung")
        for i in texte:
            self.assertEqual(150.0, float(umschalter.coords(i)[0]), "Der Text steht nicht in der Mitte")
            self.assertEqual("center", umschalter.itemcget(i, "anchor"))
        gezeigt = sorted(umschalter.itemcget(i, "text") for i in texte)
        self.assertIn(app._t("ansicht.kopfzeile"), gezeigt)
        for knopf in app._seitenleiste_knoepfe():     # nichts bleibt zurueck: neu zeichnen wie im Betrieb
            knopf.nachziehen()

    def test_gewaehlt_ist_die_zeile_mit_der_akzentfarbe(self) -> None:
        app = self.app
        farben = app._zeilen_farben()
        gewaehlt = [k for k, _m in app.mode_buttons if k._als_hex(k._bg) == k._als_hex(farben["balken"])]
        self.assertEqual(1, len(gewaehlt), "Genau eine Aufgabe ist gewaehlt (Balken und Toenung links).")

    def test_der_umschalter_ist_in_jedem_design_eine_dunkle_pille(self) -> None:
        """Die Leiste zeigt ihr dunkles Bild in jedem Design; ein cremeweisser Umschalter im hellen Design stand
        als heller Klotz darauf (am 13.10.2026 abgelehnt)."""
        app = self.app
        for theme in ("dunkel", "futuristisch", "hell", "metallisch"):
            with self.subTest(theme=theme), mock.patch.dict(app._COLORS, APP.PS5ConverterGUI._THEMES[theme]):
                u = app._umschalter_farben()
                self.assertLess(APP.bibliothek_zeichnen.helligkeit(u["bg"]), 0.35, u)
                self.assertGreaterEqual(APP.kontrastverhaeltnis(u["text"], u["bg"]), 4.5, u)

    @staticmethod
    def _zeilenfarben(theme: str) -> dict:
        c = APP.PS5ConverterGUI._THEMES[theme]
        return {"text": c["fg_primary"], "nummer": c["fg_secondary"], "balken": c["fg_accent"],
                "linie": c["border"], "gesperrt": c["fg_secondary"]}

    def _zeile_ueber_dunklem_bild(self, theme: str) -> tuple["Image.Image", list[str]]:
        """Bild und Schriftfarben, die eine nicht gewaehlte Zeile ueber dunkelblauem Leistenbild zeichnet."""
        app = self.app
        knopf = next(k for k, _m in app.mode_buttons
                     if k._als_hex(k._bg) != k._als_hex(app._COLORS["fg_accent"]))
        alt_farben = knopf._zeile_farben
        knopf._zeile_farben = self._zeilenfarben(theme)
        knopf._grund_holen = lambda w, h: Image.new("RGB", (w, h), "#0b1a3c")

        def zurueck() -> None:
            knopf._zeile_farben = alt_farben
            knopf.__dict__.pop("_grund_holen", None)
            knopf.nachziehen()
        self.addCleanup(zurueck)
        erfasst: list = []
        echt = APP.ImageTk.PhotoImage

        def erfassen(bild, *a, **k):
            erfasst.append(bild.copy())
            return echt(bild, *a, **k)
        knopf.delete("all")
        with mock.patch.object(APP.ImageTk, "PhotoImage", erfassen):
            knopf._zeile_zeichnen(300, 38, False)
        schriften = [str(knopf.itemcget(i, "fill")).lower() for i in knopf.find_all() if knopf.type(i) == "text"]
        return erfasst[-1], schriften

    def test_die_zeile_bleibt_durchsichtig_und_ihre_schrift_passt_sich_dem_bild_an(self) -> None:
        """13.10.2026, im Rundgang aller Designs gefunden: im hellen Design stand die dunkle Schrift der Zeilen auf
        dem dunkelblauen Leistenbild - kaum zu lesen. Eine Flaeche dahinter wurde als "weisse Kloetze" abgelehnt:
        Die Zeile bleibt in allen Designs durchsichtig, nur die Schrift wird hell. Dunkle Designs bleiben, wie sie sind."""
        grund = "#0b1a3c"
        bild, schriften = self._zeile_ueber_dunklem_bild("hell")
        self.assertEqual((11, 26, 60), bild.convert("RGB").getpixel((150, 4)), "Keine Flaeche hinter der Zeile")
        self.assertTrue(schriften)
        for farbe in schriften:
            self.assertGreaterEqual(APP.kontrastverhaeltnis(farbe, grund), 3.0,
                                    "Helles Design: Schrift %s ist auf dem dunklen Bild nicht lesbar" % farbe)
        for dunkel in ("dunkel", "futuristisch", "metallisch"):
            with self.subTest(theme=dunkel):
                palette = APP.PS5ConverterGUI._THEMES[dunkel]
                bild, schriften = self._zeile_ueber_dunklem_bild(dunkel)
                self.assertEqual((11, 26, 60), bild.convert("RGB").getpixel((150, 4)))
                self.assertEqual({palette["fg_primary"].lower(), palette["fg_secondary"].lower()}, set(schriften),
                                 "Die Schrift eines dunklen Designs bleibt unveraendert")

    def test_seitenleisten_beschriftung_wird_auf_dem_bild_lesbar_gestellt(self) -> None:
        """Das Leistenbild gehoert nicht zum Design: dunkle Schrift auf dunklem Bild wird hell, helle auf hellem dunkel."""
        app = self.app

        class Attrappe:
            _caption_fg_role = "fg_primary"
            farbe = ""

            def configure(self, **kw) -> None:
                self.farbe = kw["fg"]

        dunkles_bild = Image.new("RGB", (40, 12), "#0b1a3c")
        helles_bild = Image.new("RGB", (40, 12), "#f0f0f0")
        for theme, bild, erwartet in (
                ("hell", dunkles_bild, "#ffffff"),
                ("dunkel", dunkles_bild, APP.PS5ConverterGUI._THEMES["dunkel"]["fg_primary"]),
                ("dunkel", helles_bild, "#101418")):
            with self.subTest(theme=theme, erwartet=erwartet), mock.patch.dict(
                    app._COLORS, APP.PS5ConverterGUI._THEMES[theme]):
                label = Attrappe()
                app._beschriftung_lesbar_machen(label, bild)
                self.assertEqual(erwartet, label.farbe)

    def test_jede_beschriftung_mit_bildausschnitt_hat_eine_farbrolle(self) -> None:
        """Sonst zieht ein Designwechsel ihre Schrift nicht nach (_apply_caption_colors)."""
        app = self.app
        ueber_stil = {id(app.header_label), id(app.subtitle_label)}
        ohne = [str(label.cget("text")) or str(label)
                for label in app._card_caption_labels + app._content_caption_labels
                if id(label) not in ueber_stil and not getattr(label, "_caption_fg_role", "")]
        self.assertEqual([], ohne)

    def test_der_designwechsel_faerbt_alle_kartenbeschriftungen(self) -> None:
        app = self.app
        alt = app._current_theme
        neu = "hell" if alt != "hell" else "dunkel"
        app._apply_theme(neu)
        self.addCleanup(app._apply_theme, alt)
        falsch = [str(label.cget("text")) for label in app._card_caption_labels
                  if str(label.cget("foreground")).lower()
                  != str(app._COLORS[label._caption_fg_role]).lower()]
        self.assertEqual([], falsch)

    @staticmethod
    def _ruhen(sekunden: float) -> None:
        import time
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            _WURZEL.update()
            time.sleep(0.01)

    def test_die_rollflaeche_folgt_dem_wachsenden_inhalt(self) -> None:
        """Waechst die Karte nach dem ersten Zeichnen, folgt der Rahmen der Spalte.

        Gemessen am 04.10.2026 bei 1366 x 820: Rahmenhoehe 1000, Bedarf 1070 - und
        unter WSLg meldete die Darstellungspruefung den Hinweistext der Karte um
        25 px zu tief. Der Rahmen der Inhaltsspalte hat eine feste Hoehe und
        bekommt vom Wachsen seines Inhalts kein Configure; die Karte bestellt
        deshalb die Rollpruefung.
        """
        app = self.app
        _WURZEL.deiconify()
        zusatz = None
        try:
            _WURZEL.state("normal")
            _WURZEL.geometry("1300x700")
            self._ruhen(1.5)
            vorher = int(float(app.content_scroll.itemcget(app._content_fenster, "height")))
            self.assertEqual(vorher, app._inhalt_mindesthoehe(), "Ausgangslage: Rahmen = Bedarf")
            # Eine weitere Zeile in der Karte - wie ein spaeter wachsender Text.
            zusatz = tk.Frame(app.path_card, height=40, width=1)
            zusatz.grid(row=99, column=0, columnspan=3)
            self._ruhen(0.8)
            nachher = int(float(app.content_scroll.itemcget(app._content_fenster, "height")))
            self.assertGreaterEqual(nachher, vorher + 35,
                                    "Der Rahmen der Spalte ist dem wachsenden Inhalt nicht gefolgt.")
            self.assertEqual(nachher, app._inhalt_mindesthoehe())
        finally:
            if zusatz is not None:
                zusatz.destroy()
            self._ruhen(0.3)
            _WURZEL.withdraw()

    def test_die_beschriftungen_stehen_ohne_pille_auf_dem_bild(self) -> None:
        """Hinweis des Nutzers am 05.10.2026: Hinter den Texten soll keine Kachel liegen.

        Der Bildausschnitt unter einer Beschriftung ist genau so gross wie ihr
        Text. Eine Pille waere um ihre Luft groesser gewesen (Feldfarbe, Rand,
        gut eine halbe Zeilenhoehe links und rechts).
        """
        app = self.app
        _WURZEL.deiconify()
        try:
            _WURZEL.state("normal")
            _WURZEL.geometry("1300x900")
            self._ruhen(1.2)
            app._redraw_card_captions()
            app._redraw_content_captions()
            self._ruhen(0.2)
            geprueft = []
            for label in app._card_caption_labels + app._content_caption_labels:
                foto = getattr(label, "_caption_bg_photo", None)
                if foto is None or not label.winfo_ismapped():
                    continue
                with self.subTest(text=str(label.cget("text"))):
                    self.assertEqual(tuple(label._caption_natural_size), (foto.width(), foto.height()))
                geprueft.append(label)
            self.assertGreaterEqual(len(geprueft), 5, "Zu wenige Beschriftungen waren sichtbar.")
            titel = [l for l in geprueft if l is app.src_title]
            self.assertTrue(titel, "QUELLE gehoert zu den geprueften Beschriftungen.")
        finally:
            _WURZEL.withdraw()

    def test_der_worker_knopf_traegt_den_ausschnitt_des_bildes(self) -> None:
        """Der Drehknopf stand als dunkle Kachel auf dem Bild (Hinweis 05.10.2026)."""
        knopf = self.app.worker_knob
        self.assertIsNotNone(knopf._hintergrund)
        self.assertEqual(self.app._rund_hintergrund, knopf._hintergrund)

    def test_die_seitenleiste_hat_wieder_eckige_ecken(self) -> None:
        """Nutzerwunsch 05.10.2026: "die Ecken ... bei den 4 Sidebar Ecken bitte wieder normal machen".

        Das Bild der Leiste ist das Seitenleistenbild selbst, formatfuellend: ohne Rundung und ohne Fremdbild in
        den Ecken. Die runden Ecken hatten dort Teile des Hauptbilds gezeigt - als laege es unter der Leiste.
        Der Ausschnitt ueber die ganze Leiste muss deshalb Byte fuer Byte dem skalierten Bild gleichen.
        """
        app = self.app
        if app._sidebar_bg_image_cache is None:
            self.skipTest("kein Seitenleistenbild geladen")
        breite, hoehe = 300, 600
        roh = app._bild_fuellen(app._sidebar_bg_image_cache, breite, hoehe).convert("RGB")
        with mock.patch.object(app.sidebar, "winfo_width", return_value=breite), \
                mock.patch.object(app.sidebar, "winfo_height", return_value=hoehe):
            ausschnitt = app._compute_sidebar_bg_crop(app.sidebar, breite, hoehe)
        self.assertIsNotNone(ausschnitt)
        self.assertEqual(roh.tobytes(), ausschnitt.convert("RGB").tobytes(),
                         "Das Leistenbild weicht vom Seitenleistenbild ab (Ecken, Fremdbild)")
        for ecke in ((0, 0), (breite - 1, 0), (0, hoehe - 1), (breite - 1, hoehe - 1)):
            with self.subTest(ecke=ecke):
                self.assertEqual(roh.getpixel(ecke), ausschnitt.convert("RGB").getpixel(ecke))

    def test_hauptbild_und_seitenleistenbild_liegen_getrennt_nebeneinander(self) -> None:
        """Zwei Bilder, zwei Flaechen: Das Hauptbild nur rechts, das Seitenleistenbild nur links.

        Hinweis vom 05.10.2026: "Es sollten zwei Hintergrundbilder sein, da ich das getrennt moechte."
        Das Hauptbild-Label haengt an der Inhaltsflaeche, das der Leiste an der Leiste - und keines reicht
        in die Flaeche des anderen.
        """
        app = self.app
        if app._bg_image_cache is None or app._sidebar_bg_image_cache is None:
            self.skipTest("kein Hintergrundbild geladen")
        _WURZEL.deiconify()
        try:
            _WURZEL.state("normal")
            _WURZEL.geometry("1300x900")
            self._ruhen(1.2)
            self.assertIs(app.sidebar_bg_label.master, app.sidebar)
            self.assertIs(app.content_bg_label.master, app.content_area)
            leiste = (app.sidebar_bg_label.winfo_rootx(),
                      app.sidebar_bg_label.winfo_rootx() + app.sidebar_bg_label.winfo_width())
            inhalt = (app.content_bg_label.winfo_rootx(),
                      app.content_bg_label.winfo_rootx() + app.content_bg_label.winfo_width())
            self.assertLessEqual(leiste[1], inhalt[0] + 1, "Das Hauptbild reicht unter die Seitenleiste")
            self.assertLess(app.content_bg_label.winfo_width(), _WURZEL.winfo_width(),
                            "Das Hauptbild fuellt das ganze Fenster")
            self.assertLessEqual(app.sidebar_bg_label.winfo_width(), int(app._seitenleiste_breite) + 2)
        finally:
            _WURZEL.withdraw()

    def test_die_einstellungen_nennen_die_flaeche_rechts_der_leiste(self) -> None:
        """Die Mindestgroesse des Hauptbilds ist die Fensterbreite minus Seitenleiste - nicht der ganze Schirm.

        Nutzerhinweis 05.10.2026: "Das Hauptbild darf nur den Platz einnehmen, der uebrig bleibt (1427x1111)
        nach der Sidebar (493x1111)." Genaue Zahlen, die das Fenster liefert: Fenster 1920 x 1111 maximiert.
        """
        app = self.app
        with mock.patch.object(APP, "_system_maximierte_flaeche", return_value=(1920, 1111)), \
                mock.patch.object(app, "_aufloesung_manuell", None, create=True), \
                mock.patch.object(app, "_seitenleiste_breite", 493):
            self.assertEqual((1427, 1111, 493), app._hintergrund_sollmasse())

    def test_die_zahlen_der_einstellungen_sind_die_des_maximierten_fensters(self) -> None:
        """Gegenprobe am echten Fenster: maximiert, dann gemessen - genau die Zahlen der Einstellungen.

        Die Rechnung (Arbeitsbereich minus Titelleiste, Seitenleiste aus der Spaltenbreite) ist nur etwas wert,
        wenn sie das trifft, was das Fenster wirklich zeigt: Inhaltsflaeche und Seitenleiste nebeneinander.
        """
        if sys.platform != "win32":
            self.skipTest("die genaue Rechnung gibt es nur unter Windows")
        app = self.app
        if getattr(app, "_aufloesung_manuell", None):
            self.skipTest("eine Aufloesung von Hand gilt - dann rechnet die feste Reserve")
        _WURZEL.deiconify()
        try:
            _WURZEL.state("zoomed")
            self._ruhen(1.8)
            if _WURZEL.state() != "zoomed":
                self.skipTest("das Fenster liess sich hier nicht maximieren")
            breite, hoehe, leiste = app._hintergrund_sollmasse()
            gemessen = (int(app.content_area.winfo_width()), int(_WURZEL.winfo_height()),
                        int(app.sidebar.winfo_width()))
            self.assertEqual((breite, hoehe, leiste), gemessen,
                             "Soll (Einstellungen) und Ist (maximiertes Fenster) weichen ab")
        finally:
            _WURZEL.state("normal")
            _WURZEL.withdraw()

    def test_die_konsolenseite_besteht_aus_pillen(self) -> None:
        app = self.app
        if getattr(app, "_konsole_tafel", None) is None:
            app._konsole_tafel_bauen()
        knoepfe = app._konsole_tafel_knoepfe
        self.assertTrue(all(isinstance(k, APP.RoundedButton) and k._pille for k in knoepfe))
        self.assertTrue(knoepfe[0]._akzent, "'Konsole pruefen' im Akzentstil")
        self.assertIsInstance(app._konsole_tafel_protokoll.master.master,
                              bibliothek_raster.RundeKarte)


@unittest.skipUnless(_TK_DA, "kein Tk")
class AuswahldialogOrtTests(unittest.TestCase):
    """14.10.2026: "Quellentyp waehlen" ging in der Ecke oben links des Bildschirms auf. Kleine Fenster stehen dort,
    wo geklickt wurde - im Elternfenster gehalten, ohne Maus darueber mittig."""

    def setUp(self) -> None:
        self.eltern = tk.Toplevel(_WURZEL)
        self.eltern.geometry("900x600+150+120")
        self.eltern.update()
        self.addCleanup(self.eltern.destroy)
        self.dlg = tk.Toplevel(self.eltern)
        tk.Label(self.dlg, text="x", width=40, height=8).pack()
        self.dlg.withdraw()

    def _ort(self, maus: tuple[int, int]) -> tuple[int, int, int, int]:
        with mock.patch.object(tk.Misc, "winfo_pointerx", return_value=maus[0]), \
                mock.patch.object(tk.Misc, "winfo_pointery", return_value=maus[1]):
            APP.PS5ConverterGUI._dialog_an_maus(self.dlg, self.eltern)
        self.dlg.update_idletasks()
        teile = self.dlg.geometry().replace("x", "+").split("+")
        return int(teile[2]), int(teile[3]), self.dlg.winfo_reqwidth(), self.dlg.winfo_reqheight()

    def test_das_fenster_geht_dort_auf_wo_geklickt_wurde(self) -> None:
        mx, my = self.eltern.winfo_rootx() + 600, self.eltern.winfo_rooty() + 300
        x, y, b, h = self._ort((mx, my))
        self.assertLessEqual(abs(x + b // 2 - mx), 1, "Die Mitte des Fensters liegt auf der Maus")
        self.assertEqual(my - h // 4, y)
        self.assertNotEqual((0, 0), (x, y), "Nicht in der Ecke oben links")

    def test_am_rand_bleibt_es_im_elternfenster(self) -> None:
        rechts = self.eltern.winfo_rootx() + self.eltern.winfo_width()
        unten = self.eltern.winfo_rooty() + self.eltern.winfo_height()
        x, y, b, h = self._ort((rechts - 2, unten - 2))
        self.assertLessEqual(x + b, rechts - 8)
        self.assertLessEqual(y + h, unten - 8)
        x, y, b, h = self._ort((self.eltern.winfo_rootx() + 1, self.eltern.winfo_rooty() + 1))
        self.assertGreaterEqual(x, self.eltern.winfo_rootx() + 8)
        self.assertGreaterEqual(y, self.eltern.winfo_rooty() + 8)

    def test_ohne_maus_ueber_dem_elternfenster_geht_es_mittig_auf(self) -> None:
        x, y, b, h = self._ort((5, 5))
        links = self.eltern.winfo_rootx()
        self.assertEqual(links + (self.eltern.winfo_width() - b) // 2, x)
        self.assertGreater(y, self.eltern.winfo_rooty())


class QuelltextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
                         .read_text(encoding="utf-8"))
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef) and k.name == KLASSE)
        cls.methoden = {k.name: k for k in klasse.body if isinstance(k, ast.FunctionDef)}

    def _ruft(self, methode: str, name: str) -> bool:
        return any(isinstance(k, ast.Attribute) and k.attr == name
                   for k in ast.walk(self.methoden[methode]))

    def test_kein_zeichenweg_legt_eine_pille_hinter_den_text(self) -> None:
        """Seit dem 05.10.2026 wieder abbestellt - und mit ihr alles, was nur ihr diente."""
        for methode in ("_redraw_card_captions", "_redraw_content_captions"):
            with self.subTest(methode=methode):
                rumpf = ast.unparse(self.methoden[methode])
                self.assertNotIn("_texthintergrund", rumpf)
                self.assertNotIn("_beschriftungen_nachlauf", rumpf)
        for name in ("_texthintergrund_masse", "_texthintergrund_auftragen", "_texthintergrund_groesse_merken",
                     "_beschriftungen_nachlauf", "_beschriftungen_nachlauf_ausfuehren",
                     "_beschriftung_zeilenhoehe", "_worker_ueberstand"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.methoden)

    def test_der_drehknopf_wird_mit_den_pillen_nachgezogen(self) -> None:
        """Wandert eine Flaeche oder wechselt das Bild, zieht ``_runde_flaechen_jetzt`` ihn nach."""
        self.assertIn("Drehknopf", ast.unparse(self.methoden["_runde_flaechen_jetzt"]))

    def test_es_gibt_keine_gemeinsame_textstartlinie_mehr(self) -> None:
        """Seit dem 05.10.2026 abbestellt (Text wieder mittig) - samt allem, was nur ihr diente."""
        quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        for name in ("textgruppe", "_textlage", "_aufgaben_textgruppe", "_konsole_textgruppe"):
            with self.subTest(name=name):
                self.assertNotIn(name, quelltext)

    def test_alle_wege_zum_seitenleistenbild_nehmen_das_bild_selbst(self) -> None:
        """Hintergrund, Ausschnitte und Nachziehen nehmen das Seitenleistenbild formatfuellend - ohne Ecken."""
        for methode in ("_compute_sidebar_bg_crop", "_apply_sidebar_bg_resize",
                        "_refresh_sidebar_bg_label"):
            with self.subTest(methode=methode):
                self.assertIn("_bild_fuellen(self._sidebar_bg_image_cache",
                              ast.unparse(self.methoden[methode]))
        quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        for name in ("_seitenleistenbild", "_seitenleiste_ecken_nachziehen", "_seitenleiste_eckgrund_schluessel",
                     "_seitenleiste_oberkante", "_SEITENLEISTE_ECKE"):
            with self.subTest(name=name):
                self.assertNotIn(name, quelltext, "Die runden Ecken der Seitenleiste sind abbestellt")

    def test_die_pillennummer_kommt_aus_dem_interpreter(self) -> None:
        """Ein Zaehler in Python (je Objekt oder je Klasse) kennt die Namen der anderen Kopie nicht."""
        self.assertTrue(self._ruft("_pillenfeld", "_pillen_nummer"))
        self.assertIn("incr", ast.unparse(self.methoden["_pillen_nummer"]))
        self.assertNotIn("_pillen_zaehler", ast.unparse(self.methoden["_pillenfeld"]))


if __name__ == "__main__":
    unittest.main()
