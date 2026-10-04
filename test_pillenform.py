# -*- coding: utf-8 -*-
"""Pillenform der Oberflaeche (seit v1.9.62) - Waechter fuer die Fallen dieser Runde.

Nutzerwuensche vom 04.10.2026: Knoepfe, Felder und Klapplisten als Pillen wie in
der Bibliothek, die Seiten der Ansicht KONSOLE ebenso, schmalere Knoepfe in der
Seitenleiste, vier runde Ecken der Seitenleiste und ein pillenfoermiger
Texthintergrund hinter Ueberschrift,
Untertitel, Statuszeile und den Beschriftungen der Karte (Variante A: Feldfarbe
mit duennem Rand).

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

PROJEKT = Path(__file__).resolve().parent
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

    def test_runder_balken_versteht_value(self) -> None:
        balken = APP.RunderBalken(self.rahmen, palette=_palette, maximum=100)
        balken["value"] = 40
        self.assertEqual(40.0, float(balken["value"]))
        balken.configure(value=0)
        self.assertEqual(0.0, float(balken.cget("value")))
        self.assertEqual(100.0, float(balken.cget("maximum")))

    def test_runder_balken_zeichnet_den_anteil(self) -> None:
        balken = APP.RunderBalken(self.rahmen, palette=_palette, maximum=100)
        with mock.patch.object(balken, "winfo_width", return_value=200), \
                mock.patch.object(balken, "winfo_height", return_value=14):
            balken.configure(value=50)
        bild = ImageTk.getimage(balken._foto).convert("RGB")
        gefuellt, rinne = bild.getpixel((50, 7)), bild.getpixel((150, 7))
        tief = Image.new("RGB", (1, 1), _palette()["console_bg"]).getpixel((0, 0))
        self.assertEqual(tief, rinne, "Rechts vom Anteil die Rinne in der Feldfarbe.")
        self.assertNotEqual(rinne, gefuellt, "Links vom Anteil der Balken.")

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

    def test_texthintergrund_masse(self) -> None:
        app = self.app
        zeile = app._beschriftung_zeilenhoehe(app.src_title)
        self.assertGreater(zeile, 0)
        breite, hoehe, radius = app._texthintergrund_masse(app.src_title, 60, zeile)
        self.assertGreater(breite, 60)
        self.assertGreater(hoehe, zeile)
        self.assertEqual(hoehe / 2.0, radius, "einzeilig eine Pille")
        breite, hoehe, radius = app._texthintergrund_masse(app.src_title, 300, 3 * zeile)
        self.assertEqual(float(zeile), radius, "mehrzeilig ein rundes Rechteck, keine Linse")

    @staticmethod
    def _ruhen(sekunden: float) -> None:
        import time
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            _WURZEL.update()
            time.sleep(0.01)

    def test_die_rollflaeche_folgt_dem_wachsenden_inhalt(self) -> None:
        """Seit die Beschriftungen auf Pillen stehen, waechst die Spalte nach dem ersten Zeichnen.

        Gemessen bei 1366 x 820: Rahmenhoehe 1000, Bedarf 1070 - und unter WSLg
        meldete die Darstellungspruefung den Hinweistext der Karte um 25 px zu
        tief. Der Rahmen der Inhaltsspalte hat eine feste Hoehe und bekommt vom
        Wachsen seines Inhalts kein Configure; die Karte und der zweite
        Beschriftungsdurchgang bestellen deshalb die Rollpruefung.
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

    def test_texthintergrund_liegt_in_der_feldfarbe(self) -> None:
        app = self.app
        grund = Image.new("RGB", (120, 30), (255, 0, 0))
        bild = app._texthintergrund_auftragen(grund, 15.0)
        tief = Image.new("RGB", (1, 1), app._farbe_als_hex(app._COLORS["console_bg"])).getpixel((0, 0))
        self.assertEqual(tief, bild.getpixel((60, 15)), "Mitte: Feldfarbe")
        self.assertEqual((255, 0, 0), bild.getpixel((0, 0)), "Ecke: der Untergrund")

    def test_die_seitenleiste_hat_vier_runde_ecken(self) -> None:
        """Nutzerwunsch 04.10.2026 - die Ecken stecken im Bild der Leiste selbst."""
        app = self.app
        if app._sidebar_bg_image_cache is None:
            self.skipTest("kein Seitenleistenbild geladen")
        breite, hoehe = 300, 600
        roh = app._bild_fuellen(app._sidebar_bg_image_cache, breite, hoehe).convert("RGB")
        with mock.patch.object(app, "_ansicht_ist_konsole", return_value=True):
            bild = app._seitenleistenbild(breite, hoehe)
        oben = app._seitenleiste_oberkante()
        grund = Image.new("RGB", (1, 1), app._COLORS["bg_main"]).getpixel((0, 0))
        for ecke in ((0, oben), (breite - 1, oben), (0, hoehe - 1), (breite - 1, hoehe - 1)):
            with self.subTest(ecke=ecke):
                self.assertEqual(grund, bild.getpixel(ecke), "In KONSOLE die Farbe der Seite")
        self.assertEqual(roh.getpixel((150, 300)), bild.getpixel((150, 300)), "Die Mitte bleibt das Bild")

    def test_der_eckgrund_folgt_der_ansicht(self) -> None:
        app = self.app
        with mock.patch.object(app, "_ansicht_ist_konsole", return_value=True):
            konsole = app._seitenleiste_eckgrund_schluessel()
        self.assertEqual("farbe", konsole[0])
        if app._bg_image_cache is not None and app.content_area.winfo_width() > 1:
            with mock.patch.object(app, "_ansicht_ist_konsole", return_value=False):
                self.assertEqual("bild", app._seitenleiste_eckgrund_schluessel()[0])

    def test_die_konsolenseite_besteht_aus_pillen(self) -> None:
        app = self.app
        if getattr(app, "_konsole_tafel", None) is None:
            app._konsole_tafel_bauen()
        knoepfe = app._konsole_tafel_knoepfe
        self.assertTrue(all(isinstance(k, APP.RoundedButton) and k._pille for k in knoepfe))
        self.assertTrue(knoepfe[0]._akzent, "'Konsole pruefen' im Akzentstil")
        self.assertIsInstance(app._konsole_tafel_protokoll.master.master,
                              bibliothek_raster.RundeKarte)


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

    def test_beide_zeichenwege_legen_die_pille_auf(self) -> None:
        for methode in ("_redraw_card_captions", "_redraw_content_captions"):
            with self.subTest(methode=methode):
                self.assertTrue(self._ruft(methode, "_texthintergrund_auftragen"))
                self.assertTrue(self._ruft(methode, "_beschriftungen_nachlauf"),
                                "Ohne zweiten Durchgang passt der Ausschnitt nach dem Wachsen nicht.")

    def test_alle_wege_zum_seitenleistenbild_tragen_die_ecken(self) -> None:
        """Hintergrund, Ausschnitte und Nachziehen muessen dasselbe gerundete Bild nehmen."""
        for methode in ("_compute_sidebar_bg_crop", "_apply_sidebar_bg_resize",
                        "_refresh_sidebar_bg_label"):
            with self.subTest(methode=methode):
                self.assertTrue(self._ruft(methode, "_seitenleistenbild"))
                self.assertNotIn("_bild_fuellen(self._sidebar_bg_image_cache",
                                 ast.unparse(self.methoden[methode]))
        for methode in ("_ansicht_setzen", "_apply_content_bg_resize"):
            with self.subTest(methode=methode):
                self.assertTrue(self._ruft(methode, "_seitenleiste_ecken_nachziehen"))

    def test_die_pillennummer_kommt_aus_dem_interpreter(self) -> None:
        """Ein Zaehler in Python (je Objekt oder je Klasse) kennt die Namen der anderen Kopie nicht."""
        self.assertTrue(self._ruft("_pillenfeld", "_pillen_nummer"))
        self.assertIn("incr", ast.unparse(self.methoden["_pillen_nummer"]))
        self.assertNotIn("_pillen_zaehler", ast.unparse(self.methoden["_pillenfeld"]))


if __name__ == "__main__":
    unittest.main()
