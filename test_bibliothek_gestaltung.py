# -*- coding: utf-8 -*-
"""Die gestaltete Bibliothek (27.09.2026; als Karten ohne Detailspalte seit 03.10.2026).

Am 27.09.2026 meldete der Nutzer: "warum springen die Covers, wenn ich ein Spiel
anklicke das kein Cover hat?" Gemessen bei 1245 x 700 und 125 %: Die Detailspalte war
vor der ersten Auswahl 193, ohne Titelbild 211, mit einem Bild im Hochformat 236 und mit
einem quadratischen 280 Pixel breit - ihr Bildfeld hatte keine feste Groesse. Die
Kachelflaeche daneben schwankte zwischen 405 und 492 Pixeln, und weil die Spalten des
Rasters mitwachsen, rutschten die Kacheln bei jedem Klick.

Am 03.10.2026 schickte er zwei Entwurfsbilder: Die Bibliothek soll aus Karten bestehen
(Titelbild, Plakette, Chips, "Infos & Metadaten", "Starten", "Kopieren",
"Konvertieren"), ueber die ganze Breite, **ohne Spalte rechts**. Die Detailspalte ist
seitdem ein Infofenster, das unter "Infos & Metadaten" aufklappt; die Liste hat statt
ihrer einen Streifen mit denselben Knoepfen. Das Springen darf nicht wiederkommen -
auch ein aufklappendes Fenster aendert seine Groesse bei keiner Auswahl.

Bewacht wird hier:

* Das Titelbild-Feld des Infofensters misst in jedem Zustand gleich, und das Fenster
  selbst ist bei jeder Auswahl gleich breit.
* Die Kopfkarte hat Hoehe (am 03.10.2026 fehlte sie, weil ein Fenster auf einer
  Zeichenflaeche ohne Groessenereignis eine Zeile hoch blieb).
* Es gibt keine Detailspalte mehr; das Infofenster liegt ueber der Seite und schliesst
  sich bei Klick daneben, Wechsel der Karte, Ansicht und Quelle.
* Umschalter (Quelle, Ansicht), Zaehlzeile, die vier Filter und das Nachfaerben nach
  einem Designwechsel; die Listenvorschau bekommt ihre Bilder von den Karten.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("bibliothek_gestaltung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek_raster as raster  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    from PIL import Image
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
GUI = APP.PS5ConverterGUI


def _methode(name: str) -> ast.FunctionDef:
    baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
    klasse = next(k for k in baum.body
                  if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    return next(k for k in klasse.body
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _png(breite: int, hoehe: int) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), (120, 60, 30)).save(puffer, "PNG")
    return puffer.getvalue()


def _alle(widget):
    offen = [widget]
    while offen:
        w = offen.pop()
        offen.extend(w.winfo_children())
        yield w


class TexteTests(unittest.TestCase):

    def test_die_neuen_texte_gibt_es_zweisprachig(self) -> None:
        for schluessel, platzhalter in (
                ("library.sort_absteigend", set()), ("library.sort_label", set()),
                ("library.such_platzhalter", set()), ("library.kopf_leer", set()),
                ("library.kopf_spiele", {"count"}), ("library.kopf_treffer", {"sichtbar", "gesamt"}),
                ("library.kopf_ps5", {"count"}), ("library.kopf_ps4", {"count"}),
                ("library.kopf_einbauten", {"count"}),
                ("library.filter_alle", set()), ("library.filter_ps5", set()),
                ("library.filter_ps4", set()), ("library.filter_einbau", set()),
                ("library.karte_info", set()), ("library.karte_starten", set()),
                ("library.karte_kopieren", set()), ("library.karte_konvertieren", set()),
                ("library.chip_ordner", set()), ("library.chip_installiert_ps4", set()),
                ("library.chip_installiert_ps5", set()), ("library.chip_unbekannt", set()),
                ("library.chip_ampr_verdeckt", set()),
                ("library.gesperrt_start", set()), ("library.gesperrt_kopieren_installiert", set()),
                ("library.gesperrt_konvertieren", set())):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertTrue(text)
                    gefunden = {teil.split("}")[0] for teil in text.split("{")[1:]}
                    self.assertEqual(platzhalter, gefunden)

    def test_die_alten_texte_der_werkzeugzeile_sind_weg(self) -> None:
        """Die Trefferzahl und der Sortierknopf mit Beschriftung gingen in die Kopfkarte auf."""
        for schluessel in ("library.anzahl_titel", "library.anzahl_treffer", "library.sortiert_nach",
                           "library.search_label", "library.btn_starten", "library.upload_knopf",
                           "library.download_knopf"):
            # Nicht assertNotIn(schluessel, STRINGS): Bei einem Fehlschlag druckt das den ganzen Katalog.
            self.assertFalse(schluessel in STRINGS, schluessel + " wird nirgends mehr gebraucht.")

    def test_der_designwechsel_ruft_die_bibliothek(self) -> None:
        """_recolor_widget kennt keine Ringe und Raender - die Seite faerbt selbst nach."""
        self.assertIn("bibliothek['farben']()", ast.unparse(_methode("_apply_theme")))

    def test_nirgends_mehr_image_leer_im_bildkasten(self) -> None:
        """image="" laesst ein Label wieder in Zeichen messen - der Kasten fiele zusammen."""
        text = ast.unparse(_methode("_render_library_window"))
        self.assertNotIn("cover_label.configure(image='')", text)

    def test_es_gibt_keine_detailspalte_mehr(self) -> None:
        text = ast.unparse(_methode("_render_library_window"))
        self.assertNotIn("body.grid_columnconfigure(1", text, "Rechts steht keine Spalte mehr.")
        self.assertNotIn("detail.grid(", text, "Das Infofenster liegt ueber der Seite (place), nicht im Raster.")
        self.assertIn("detail.place(", text)
        for alt in ("_bibliothek_kachelflaeche", "_bibliothek_kacheln_setzen", "_bibliothek_kacheln_anordnen",
                    "_bibliothek_kacheln_markieren", "_bibliothek_kachel_marken", "_bibliothek_segmente",
                    "_bibliothek_spaltenbreite"):
            with self.subTest(alt=alt):
                self.assertFalse(hasattr(GUI, alt), alt + " ist durch das Kartenraster ersetzt.")


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class BildfeldTests(unittest.TestCase):
    """Die Bildlader sprechen das Titelbild einer Karte ueber ``PosterFeld`` an."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = GUI.__new__(GUI)
        cls.app._COLORS = dict(GUI._THEMES["dunkel"])
        cls.app._current_language = "de"
        cls.app._bibliothek_generation = 7
        cls._ordner = tempfile.TemporaryDirectory()
        cls.datei = os.path.join(cls._ordner.name, "bild.png")
        Path(cls.datei).write_bytes(_png(512, 288))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._ordner.cleanup()

    def setUp(self) -> None:
        self.rahmen = tk.Frame(_WURZEL)
        self.addCleanup(self.rahmen.destroy)
        palette = dict(GUI._THEMES["dunkel"])
        zeichner = raster.Zeichner(_WURZEL, lambda: palette, APP.UI_SCHRIFT, APP.pt)
        self.raster = raster.KartenRaster(
            zeichner, self.rahmen,
            inhalt=lambda e: {"titel": "Spiel", "plattform": "PS5", "chips": [], "knoepfe": []},
            aktion=lambda *a: None, bei_auswahl=lambda e: None, bei_start=lambda e: None)
        self._breite = mock.patch.object(self.raster.flaeche, "winfo_width", return_value=900)
        self._breite.start()
        self.addCleanup(self._breite.stop)
        self.eintrag = {"path": "/data/homebrew/spiel", "kind": "folder", "meta": {"title": "Spiel"}}
        self.raster.setzen([self.eintrag])
        self.feld = self.eintrag["_bildfeld"]
        self.geliefert: list = []
        self.feld._mini_rueckruf = lambda vorschau: self.geliefert.append(vorschau)

    def test_das_bild_geht_an_die_karte_und_die_liste(self) -> None:
        kante = APP.pt(GUI._KACHEL_BILD_PT)
        self.app._bibliothek_bild_setzen(self.feld, self.datei, kante, 7)
        self.assertEqual("da", self.raster.karten[0].bildzustand)
        self.assertEqual(self.datei, self.raster.karten[0].bilddatei)
        self.assertEqual(1, len(self.geliefert))
        self.assertIsNotNone(self.geliefert[0], "Das Titelbild kam in der Liste nicht an.")
        self.assertLessEqual(max(self.geliefert[0].size), kante, "Die Vorschau ist klein, nicht das Original.")

    def test_kein_titelbild_geht_als_none_an_die_liste(self) -> None:
        self.app._bibliothek_bild_setzen(self.feld, "", 100, 7)
        self.assertEqual("leer", self.raster.karten[0].bildzustand)
        self.assertEqual([None], self.geliefert)

    def test_eine_kaputte_datei_gilt_als_kein_titelbild(self) -> None:
        kaputt = os.path.join(self._ordner.name, "kaputt.png")
        Path(kaputt).write_bytes(b"kein Bild")
        self.app._bibliothek_bild_setzen(self.feld, kaputt, 100, 7)
        self.assertEqual("leer", self.raster.karten[0].bildzustand)
        self.assertEqual([None], self.geliefert)

    def test_ein_veraltetes_ergebnis_wird_verworfen(self) -> None:
        """Ein neuer Suchlauf hat begonnen - das Bild des alten gehoert nicht mehr auf die Karte."""
        self.app._bibliothek_bild_setzen(self.feld, self.datei, 100, 6)
        self.assertEqual("laedt", self.raster.karten[0].bildzustand)
        self.assertEqual([], self.geliefert)

    def test_eine_verschwundene_karte_wird_nicht_angefasst(self) -> None:
        self.raster.setzen([])
        self.app._bibliothek_bild_setzen(self.feld, self.datei, 100, 7)
        self.assertEqual([], self.geliefert)

    def test_vorschaubilder_sind_immer_gleich_gross(self) -> None:
        kante = 30
        for vorlage in (None, Image.new("RGB", (60, 20)), Image.new("RGB", (20, 60)),
                        Image.new("P", (40, 40))):
            with self.subTest(vorlage=vorlage):
                foto = self.app._bibliothek_minibild(vorlage, kante)
                self.assertEqual((kante, kante), (foto.width(), foto.height()))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeitenTests(unittest.TestCase):
    """Die Seite am wirklichen Programm."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = GUI(_WURZEL)
        cls.app._current_language = "de"
        cls._einstellungen = {"library_scan_folders": [], "library_quelle": "pc",
                              "library_ansicht": "kacheln"}
        cls._laden = mock.patch.object(
            cls.app, "_load_setting",
            side_effect=lambda k, v=None, _alt=cls.app._load_setting:
            cls._einstellungen.get(k, _alt(k, v)))
        cls._laden.start()
        cls._speichern = mock.patch.object(cls.app, "_save_setting",
                                           lambda k, v: cls._einstellungen.__setitem__(k, v))
        cls._speichern.start()
        # Das Infofenster fragt sonst nach Updates - und ginge dafuer ins Netz.
        cls._online = mock.patch.object(cls.app, "_metadaten_online_erlaubt", return_value=False)
        cls._online.start()
        cls._ordner = tempfile.TemporaryDirectory()
        basis = Path(cls._ordner.name)
        speicher = cls.app._bibliothek_bildspeicher()
        cls.eintraege = []
        # "laedt" steht nicht im Bildspeicher - das Infofenster zeigt dann "laedt ..."
        # und holt das Bild im Faden.
        for name, groesse in (("quadrat", (512, 512)), ("quer", (512, 288)),
                              ("hoch", (288, 512)), ("ohne", None), ("laedt", "-")):
            pfad = basis / ("%s.ffpfsc" % name)
            pfad.write_bytes(b"kein echtes Abbild")
            if groesse is None:
                speicher.schreiben(str(pfad), None)
            elif groesse != "-":
                speicher.schreiben(str(pfad), _png(*groesse))
            cls.eintraege.append({"path": str(pfad), "kind": "ffpfsc", "name": name,
                                  "meta": {"title": "Spiel %s" % name,
                                           "title_id": "PPSA0000%d" % len(cls.eintraege)},
                                  "size": None})
        # Die Seite einmal frisch bauen - vor jeder Auswahl messen.
        cls.app._ansicht_setzen("konsole")
        cls.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        zustand = cls.app._bibliothek
        cls.vorher = (zustand["cover"].winfo_reqwidth(), zustand["cover"].winfo_reqheight(),
                      zustand["detail"].winfo_reqwidth())

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app._konsole_seite_setzen("uebersicht")
        cls.app._ansicht_setzen("umwandeln")
        _WURZEL.update()
        cls._online.stop()
        cls._speichern.stop()
        cls._laden.stop()
        cls._ordner.cleanup()

    def setUp(self) -> None:
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        self.zustand = self.app._bibliothek
        self.zustand["ansicht"]["einbauten"].clear()
        self.zustand["ansicht"]["angezeigt"] = None
        self.zustand["ansicht"]["gewaehlt"] = ""
        baum = self.zustand["liste"]
        baum.selection_remove(*baum.get_children())
        self.zustand["eintraege"][:] = self.eintraege
        self.zustand["filtern"]()
        self.zustand["streifen_neu"]()
        _WURZEL.update_idletasks()

    def tearDown(self) -> None:
        self.zustand["info_schliessen"]()
        self.zustand["suche"].set("")
        self.zustand["filter"].set("alle")
        self.zustand["filter_gewaehlt"]()
        self.zustand["ansicht"]["gewaehlt"] = ""
        self.zustand["ansicht"]["einbauten"].clear()
        self.zustand["eintraege"].clear()
        self.zustand["filtern"]()

    # --- Aufbau ----------------------------------------------------------------------------------------
    def test_die_kopfkarte_hat_hoehe(self) -> None:
        """Am 03.10.2026 fehlte die Kopfkarte: Ihre Hoehe haengte an einem Ereignis, das nie kam."""
        kopf = self.zustand["kopf"]
        self.assertGreater(kopf.winfo_reqheight(), 100)
        self.assertTrue(kopf.winfo_manager())
        titel = self.zustand["zaehlzeile"]
        self.assertTrue(titel.winfo_manager(), "Die Zaehlzeile steht in der Kopfkarte.")

    @staticmethod
    def _rechtes_polster(info: dict) -> int:
        """Das rechte Ende von ``padx`` aus pack_info()/grid_info(): ``(0, 21)`` -> 21, ``3`` -> 3."""
        return int(str(info["padx"]).strip("()").replace(",", " ").split()[-1])

    def test_rechts_steht_keine_spalte_und_das_infofenster_liegt_ueber_der_seite(self) -> None:
        seite = self.app._bibliothek_seite
        body = self.zustand["raster"].rahmen.master
        self.assertEqual(0, int(self.zustand["raster"].rahmen.grid_info()["column"]))
        self.assertEqual(1, body.grid_size()[0], "Eine Spalte - rechts ist nichts.")
        self.zustand["kopf_gruppen"]["ansicht"].chips[1].invoke()          # die Liste liegt an derselben Stelle
        try:
            self.assertEqual(0, int(self.zustand["listenkarte"].grid_info()["column"]))
            self.assertEqual(1, body.grid_size()[0])
        finally:
            self.zustand["kopf_gruppen"]["ansicht"].chips[0].invoke()
        detail = self.zustand["detail"]
        self.assertIs(seite, detail.master)
        self.assertNotIn(detail.winfo_manager(), ("grid", "pack"))

    def test_die_karten_und_die_kopfkarte_enden_an_derselben_kante(self) -> None:
        """Kopfkarte, Karten, Liste und Streifen lassen rechts dieselbe Breite frei: den Rollbalken."""
        sb = self.zustand["raster"].balken.winfo_reqwidth()
        self.assertGreater(sb, 5)
        self.assertEqual(sb, self._rechtes_polster(self.zustand["kopf"].pack_info()))
        self.zustand["kopf_gruppen"]["ansicht"].chips[1].invoke()
        try:
            self.assertEqual(sb, self._rechtes_polster(self.zustand["listenkarte"].grid_info()))
            self.assertEqual(sb, self._rechtes_polster(self.zustand["streifen"].pack_info()))
        finally:
            self.zustand["kopf_gruppen"]["ansicht"].chips[0].invoke()

    # --- Infofenster ---------------------------------------------------------------------------------------
    def test_das_infofenster_haengt_an_keiner_auswahl(self) -> None:
        cover, detail = self.zustand["cover"], self.zustand["detail"]
        bildkasten = {"nichts gewaehlt": self.vorher[:2]}
        breiten = {"nichts gewaehlt": self.vorher[2]}
        konsole = dict(self.eintraege[0], ps5=True, path="/data/homebrew/auf_der_konsole",
                       name="konsole", kind="folder")
        for eintrag in self.eintraege + [konsole]:
            self.zustand["details"](eintrag)
            _WURZEL.update()      # wie im Programm: auch Fensterereignisse
            bildkasten[eintrag["name"]] = (cover.winfo_reqwidth(), cover.winfo_reqheight())
            breiten[eintrag["name"]] = detail.winfo_reqwidth()
        self.assertEqual(1, len(set(bildkasten.values())), bildkasten)
        self.assertEqual(1, len(set(breiten.values())),
                         "Die Breite haengt an keiner Auswahl - auch nicht an Rechner oder Konsole: %s" % breiten)

    def test_das_infofenster_klappt_auf_und_zu(self) -> None:
        zustand, eintrag = self.zustand, self.eintraege[0]
        detail = zustand["detail"]
        self.assertEqual("", detail.winfo_manager())
        zustand["aktion"]("info", eintrag)
        self.assertEqual(eintrag["path"], zustand["ansicht"]["info_fuer"])
        self.assertEqual("place", detail.winfo_manager())
        self.assertEqual(eintrag["path"], zustand["ansicht"]["gewaehlt"], "Die Karte ist dabei gewaehlt.")
        self.assertIn("Spiel quadrat", zustand["zeilen"]["titel"].cget("text"))
        zustand["aktion"]("info", eintrag)
        self.assertEqual("", zustand["ansicht"]["info_fuer"])
        self.assertEqual("", detail.winfo_manager())

    def test_eine_andere_karte_schliesst_das_infofenster(self) -> None:
        zustand = self.zustand
        zustand["aktion"]("info", self.eintraege[0])
        self.assertTrue(zustand["ansicht"]["info_fuer"])
        zustand["raster"]._bei_auswahl(self.eintraege[1])           # Klick auf eine andere Karte
        self.assertEqual("", zustand["ansicht"]["info_fuer"])
        self.assertEqual("", zustand["detail"].winfo_manager())

    def test_ein_anderer_knopf_der_karte_schliesst_es_ebenfalls(self) -> None:
        zustand = self.zustand
        for name in ("start", "kopieren", "konvertieren"):
            zustand["aktion"]("info", self.eintraege[0])
            self.assertTrue(zustand["ansicht"]["info_fuer"])
            with mock.patch.object(APP.messagebox, "askyesno", return_value=False), \
                    mock.patch.object(APP.messagebox, "showinfo"), \
                    mock.patch.object(APP.filedialog, "askdirectory", return_value=""), \
                    mock.patch.object(self.app, "_bibliothek_hochladen"), \
                    mock.patch.object(self.app, "_validate_source_path", return_value=""):
                zustand["aktion"](name, self.eintraege[0])
            with self.subTest(knopf=name):
                self.assertEqual("", zustand["ansicht"]["info_fuer"])
        self.app.source_path.set("")
        self.app._ansicht_setzen("konsole")

    def test_ein_klick_daneben_schliesst_es_ein_klick_darin_nicht(self) -> None:
        zustand = self.zustand
        zustand["aktion"]("info", self.eintraege[0])
        darin = types.SimpleNamespace(widget=zustand["zeilen"]["titel"])
        zustand["info_ausserhalb"](darin)
        self.assertTrue(zustand["ansicht"]["info_fuer"], "Ein Klick im Fenster laesst es offen.")
        auf_den_karten = types.SimpleNamespace(widget=zustand["raster"].flaeche)
        zustand["info_ausserhalb"](auf_den_karten)
        self.assertTrue(zustand["ansicht"]["info_fuer"],
                        "Klicks auf die Karten entscheidet das Raster (Knopf Infos schaltet um).")
        daneben = types.SimpleNamespace(widget=zustand["such_feld"].eingabe)
        zustand["info_ausserhalb"](daneben)
        self.assertEqual("", zustand["ansicht"]["info_fuer"])

    def test_wechsel_von_ansicht_quelle_und_filter_schliesst_es(self) -> None:
        zustand = self.zustand
        for aktion in (lambda: zustand["filter_gewaehlt"](),
                       lambda: zustand["kopf_gruppen"]["ansicht"].chips[1].invoke(),
                       lambda: zustand["kopf_gruppen"]["ansicht"].chips[0].invoke()):
            zustand["aktion"]("info", self.eintraege[0])
            self.assertTrue(zustand["ansicht"]["info_fuer"])
            aktion()
            self.assertEqual("", zustand["ansicht"]["info_fuer"])

    def test_die_pc_knoepfe_im_infofenster_nur_fuer_den_rechner(self) -> None:
        zustand = self.zustand
        konsole = dict(self.eintraege[0], ps5=True, path="/data/homebrew/auf_der_konsole", kind="folder")
        pfad = [k for k in _alle(zustand["detail"]) if k.winfo_class() == "TButton"
                and str(k.cget("text")) in (self.app._t("library.btn_umbenennen"),
                                           self.app._t("library.reveal_in_explorer_button"))]
        self.assertEqual(2, len(pfad))
        zustand["details"](self.eintraege[0])
        self.assertTrue(all(k.winfo_manager() == "pack" for k in pfad))
        zustand["details"](konsole)
        self.assertTrue(all(k.winfo_manager() == "" for k in pfad), "Auf der Konsole wird nichts umbenannt.")

    # --- Liste und Streifen ------------------------------------------------------------------------------
    def test_die_liste_zeigt_vorschaubilder(self) -> None:
        baum = self.zustand["liste"]
        zeilen = {baum.set(iid, "path"): iid for iid in baum.get_children()}
        self.assertEqual(len(self.eintraege), len(zeilen))
        self.assertTrue(all(baum.item(iid, "image") for iid in zeilen.values()),
                        "Zeilen ohne Bild - auch waehrend des Ladens gehoert ein Platzhalter hin.")
        eintrag = self.eintraege[0]
        vorher = baum.item(zeilen[eintrag["path"]], "image")
        self.app._bibliothek_bild_setzen(
            eintrag["_bildfeld"], self.app._bibliothek_bildspeicher().lesen(eintrag["path"]),
            APP.pt(GUI._KACHEL_BILD_PT), self.app._bibliothek_generation)
        self.assertNotEqual(vorher, baum.item(zeilen[eintrag["path"]], "image"),
                            "Das Titelbild der Karte kam in der Liste nicht an.")

    def test_der_streifen_gehoert_zur_liste_und_zur_gewaehlten_zeile(self) -> None:
        zustand = self.zustand
        streifen = zustand["streifen"]
        self.assertEqual("", streifen.winfo_manager(), "Bei den Karten tragen die Karten ihre Knoepfe selbst.")
        zustand["kopf_gruppen"]["ansicht"].chips[1].invoke()
        try:
            self.assertEqual("pack", streifen.winfo_manager())
            knoepfe = zustand["streifen_knoepfe"]
            self.assertEqual(["info", "start", "kopieren", "konvertieren"], list(knoepfe))
            self.assertEqual("normal", str(knoepfe["info"].cget("state")))
            for name in ("start", "kopieren", "konvertieren"):
                self.assertEqual("disabled", str(knoepfe[name].cget("state")), "Nichts gewaehlt: nichts zu tun.")
            self.zustand["details"](self.eintraege[0])
            _WURZEL.update_idletasks()
            for name in ("start", "kopieren", "konvertieren"):
                self.assertEqual("normal", str(knoepfe[name].cget("state")), name)
        finally:
            zustand["kopf_gruppen"]["ansicht"].chips[0].invoke()
        self.assertEqual("", streifen.winfo_manager())

    def test_der_streifen_nennt_die_gewaehlte_zeile(self) -> None:
        zustand = self.zustand
        zustand["details"](self.eintraege[2])
        titel = next(w for w in _alle(zustand["streifen"]) if w.winfo_class() == "Label")
        self.assertEqual("Spiel hoch", titel.cget("text"))

    def test_der_streifen_wirkt_auf_die_gewaehlte_zeile(self) -> None:
        zustand = self.zustand
        zustand["details"](self.eintraege[1])
        zustand["ansicht"]["gewaehlt"] = self.eintraege[1]["path"]
        with mock.patch.object(self.app, "_validate_source_path", return_value=""):
            zustand["streifen_knoepfe"]["konvertieren"].invoke()
        _WURZEL.update()
        self.assertEqual(self.eintraege[1]["path"], self.app.source_path.get())
        self.assertFalse(self.app._ansicht_ist_konsole())
        self.app.source_path.set("")

    # --- Umschalter, Zaehlzeile, Filter ---------------------------------------------------------------------------
    def test_die_umschalter(self) -> None:
        gruppen = self.zustand["kopf_gruppen"]
        for name, werte in (("quelle", ["pc", "ps5"]), ("ansicht", ["kacheln", "liste"]),
                            ("filter", ["alle", "ps5", "ps4", "einbau"])):
            with self.subTest(gruppe=name):
                self.assertEqual(werte, [w for w, _t, _c in gruppen[name]._chips])
        self.assertEqual([True, False], [c.an for c in gruppen["ansicht"].chips])
        liste = self.zustand["listenkarte"]
        raster_rahmen = self.zustand["raster"].rahmen
        gruppen["ansicht"].chips[1].invoke()
        try:
            self.assertEqual("liste", self.zustand["ansicht"]["art"])
            self.assertTrue(liste.winfo_manager())
            self.assertFalse(raster_rahmen.winfo_manager())
            self.assertEqual("liste", self._einstellungen["library_ansicht"])
            self.assertEqual([False, True], [c.an for c in gruppen["ansicht"].chips])
            self.assertEqual("chip_an", gruppen["ansicht"].chips[1].stil)
        finally:
            gruppen["ansicht"].chips[0].invoke()
        self.assertEqual("kacheln", self.zustand["ansicht"]["art"])
        self.assertFalse(liste.winfo_manager())
        self.assertTrue(raster_rahmen.winfo_manager())

    def test_die_zaehlzeile(self) -> None:
        zeile = self.zustand["zaehlzeile"]
        gesamt = len(self.eintraege)
        text = zeile.cget("text")
        self.assertTrue(text.startswith(self.app._t("library.kopf_spiele", count=gesamt)), text)
        self.assertIn(self.app._t("library.kopf_ps5", count=gesamt), text)
        self.assertNotIn("PS4", text, "Null PS4 wird nicht aufgezaehlt.")
        self.zustand["suche"].set("quer")
        self.assertIn(self.app._t("library.kopf_treffer", sichtbar=1, gesamt=gesamt), zeile.cget("text"))

    def test_die_zaehlzeile_zaehlt_einbauten_erst_wenn_welche_da_sind(self) -> None:
        zeile = self.zustand["zaehlzeile"]
        self.assertNotIn("Backport", zeile.cget("text"))
        einb = self.zustand["ansicht"]["einbauten"]
        einb[self.eintraege[0]["path"]] = {"zustand": "ok", "ampr": True}
        einb[self.eintraege[1]["path"]] = {"zustand": "ok", "playgo": True}
        einb[self.eintraege[2]["path"]] = {"zustand": "ok"}                      # nichts eingebaut
        einb[self.eintraege[3]["path"]] = {"zustand": "unbekannt", "grund": "format"}
        self.zustand["filtern"]()
        self.assertIn(self.app._t("library.kopf_einbauten", count=2), zeile.cget("text"))

    def test_die_filter(self) -> None:
        zustand = self.zustand
        filter_var, einb = zustand["filter"], zustand["ansicht"]["einbauten"]
        ps4 = dict(self.eintraege[0], path=self.eintraege[0]["path"] + ".ps4",
                   meta={"title": "Alt", "title_id": "CUSA12345"})
        zustand["eintraege"].append(ps4)
        einb[self.eintraege[1]["path"]] = {"zustand": "ok", "ampr": True}

        def _sichtbar(wahl: str) -> int:
            filter_var.set(wahl)
            zustand["filter_gewaehlt"]()
            return len(zustand["ansicht"]["sichtbar"])

        self.assertEqual(6, _sichtbar("alle"))
        self.assertEqual(5, _sichtbar("ps5"))
        self.assertEqual(1, _sichtbar("ps4"))
        self.assertEqual(1, _sichtbar("einbau"))
        self.assertEqual(self.eintraege[1]["path"], zustand["ansicht"]["sichtbar"][0]["path"])
        self.assertEqual(1, len(zustand["liste"].get_children()), "Die Liste filtert mit.")
        self.assertEqual(1, len(zustand["raster"].karten), "Und die Karten ebenfalls.")
        self.assertEqual([False, False, False, True], [c.an for c in zustand["kopf_gruppen"]["filter"].chips])

    def test_ein_eintrag_ohne_erkennbare_plattform_gehoert_zu_keinem_der_beiden_filter(self) -> None:
        zustand = self.zustand
        ohne = dict(self.eintraege[0], path=self.eintraege[0]["path"] + ".x",
                    meta={"title": "Ohne", "title_id": ""})
        zustand["eintraege"].append(ohne)
        for wahl, erwartet in (("ps5", 5), ("ps4", 0), ("alle", 6)):
            zustand["filter"].set(wahl)
            zustand["filter_gewaehlt"]()
            self.assertEqual(erwartet, len(zustand["ansicht"]["sichtbar"]), wahl)

    def test_der_einbau_filter_wartet_auf_die_ergebnisse(self) -> None:
        """Die Einbauten kommen einzeln; ein einziges Neufiltern fasst sie zusammen.

        Ohne das Neufiltern bliebe die Liste mit dem Filter "mit Einbau" leer, obwohl
        die Ergebnisse da sind - oder sie baute bei jedem einzelnen Ergebnis alle
        Karten neu.
        """
        zustand = self.zustand
        zustand["filter"].set("einbau")
        zustand["filter_gewaehlt"]()
        self.assertEqual(0, len(zustand["ansicht"]["sichtbar"]))
        geplant: list = []
        with mock.patch.object(self.app._bibliothek_seite, "after",
                               side_effect=lambda ms, fn: geplant.append((ms, fn))):
            zustand["einbauten_da"](self.eintraege[0], {"zustand": "ok", "ampr": True})
            zustand["einbauten_da"](self.eintraege[1], {"zustand": "ok", "playgo": True})
        self.assertEqual(1, len(geplant), "Zwei Ergebnisse, ein Neufiltern.")
        self.assertTrue(zustand["ansicht"]["filter_geplant"])
        geplant[0][1]()
        self.assertFalse(zustand["ansicht"]["filter_geplant"])
        self.assertEqual({self.eintraege[0]["path"], self.eintraege[1]["path"]},
                         {e["path"] for e in zustand["ansicht"]["sichtbar"]})

    def test_ohne_den_einbau_filter_wird_nicht_neu_gefiltert(self) -> None:
        zustand = self.zustand
        with mock.patch.object(self.app._bibliothek_seite, "after") as plan:
            zustand["einbauten_da"](self.eintraege[0], {"zustand": "ok", "ampr": True})
        plan.assert_not_called()
        self.assertIn(self.eintraege[0]["path"], zustand["ansicht"]["einbauten"])

    def test_ein_neues_einbauergebnis_zeichnet_die_chips_der_karte(self) -> None:
        zustand, eintrag = self.zustand, self.eintraege[0]
        karte = zustand["raster"].karte_von(eintrag)
        vorher = len(karte.chip_ids)
        zustand["einbauten_da"](eintrag, {"zustand": "ok", "ampr": True, "playgo": True,
                                          "backport": ["12.00"], "assetpack": True})
        self.assertGreater(len(karte.chip_ids), vorher)
        texte = [zustand["raster"].flaeche.itemcget(i, "text") for i in karte.chip_ids
                 if zustand["raster"].flaeche.type(i) == "text"]
        self.assertEqual(["ffpfsc", "AMPR EMU", "PlayGo", "BACKPORT (12.00)", "Asset-Pack"], texte)
        zustand["einbauten_da"](eintrag, {"zustand": "unbekannt", "grund": "format"})
        texte = [zustand["raster"].flaeche.itemcget(i, "text") for i in karte.chip_ids
                 if zustand["raster"].flaeche.type(i) == "text"]
        self.assertEqual(["ffpfsc", self.app._t("library.chip_unbekannt")], texte)

    def test_die_sortierauswahl_nennt_spalte_und_richtung(self) -> None:
        knopf = self.zustand["sortier_knopf"]
        self.assertEqual("Titel  ▴", knopf.cget("text"))
        self.assertTrue(knopf._chevron)

    # --- Designwechsel -----------------------------------------------------------------------------------------
    def test_nachfaerben_erreicht_karten_kopf_und_infofenster(self) -> None:
        alt = self.app._COLORS
        hell = dict(GUI._THEMES["hell"])
        karte_vorher = self.zustand["raster"].karten[0].fotos["karte"]
        self.app._COLORS = hell
        try:
            self.zustand["farben"]()
            z = self.zustand
            self.assertEqual(hell["bg_main"], str(z["raster"].flaeche.cget("bg")))
            self.assertEqual(hell["bg_card"], str(z["kopf"].innen.cget("bg")))
            self.assertEqual(hell["bg_main"], str(z["kopf"].cget("bg")))
            self.assertEqual(hell["bg_card"], str(z["zaehlzeile"].cget("bg")))
            self.assertEqual(hell["fg_secondary"], str(z["zaehlzeile"].cget("fg")))
            for gruppe in z["kopf_gruppen"].values():
                for chip in gruppe.chips:
                    self.assertEqual(hell["bg_card"], str(chip.cget("bg")))
            self.assertEqual(hell["fg_accent"], str(z["detail"].cget("highlightbackground")),
                             "Das Infofenster traegt den Akzentrand der gewaehlten Karte.")
            self.assertEqual(hell["console_bg"], str(z["cover"].cget("bg")))
            self.assertEqual(hell["fg_primary"],
                             z["raster"].flaeche.itemcget(z["raster"].karten[0].ids["titel"], "fill"))
            self.assertIsNot(karte_vorher, z["raster"].karten[0].fotos["karte"])
            self.assertEqual(hell["bg_card"], str(z["liste"].tag_configure("gerade", "background")))
            self.assertNotEqual(str(z["liste"].tag_configure("ungerade", "background")), hell["bg_card"],
                                "Die Streifen der Liste bleiben zwei Toene.")
            self.assertEqual(hell["bg_card"], str(z["streifen"].innen.cget("bg")))
        finally:
            self.app._COLORS = alt
            self.zustand["farben"]()


if __name__ == "__main__":
    unittest.main(verbosity=2)
