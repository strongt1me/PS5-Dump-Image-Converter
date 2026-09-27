# -*- coding: utf-8 -*-
"""Die neu gestaltete Bibliothek (27.09.2026) - und warum die Kacheln sprangen.

Vom Nutzer mit Bild gemeldet: "warum springen die Covers, wenn ich ein Spiel
anklicke das kein Cover hat? Es springt aber auch ab und zu, wenn es ein Cover
hat." Gemessen bei 1245 x 700 und 125 %: Die Detailspalte war vor der ersten
Auswahl 193, ohne Titelbild 211, mit einem Bild im Hochformat 236 und mit einem
quadratischen 280 Pixel breit - ihr Bildfeld hatte keine feste Groesse. Die
Kachelflaeche daneben schwankte zwischen 405 und 492 Pixeln, und weil die
Spalten des Rasters mitwachsen, rutschten die Kacheln bei jedem Klick.

Bewacht wird hier:

* Das Bildfeld der Detailspalte misst in jedem Zustand gleich (Bild
  quadratisch, quer, hoch, kein Bild, laedt, nichts gewaehlt), und die Spalte
  reserviert mehr, als ihr Inhalt je verlangt - ihre Breite haengt an keiner
  Auswahl.
* Das Bildfeld einer Kachel misst in jedem Zustand genau ``kante + 2``. Tk
  polstert ein Label nur, wenn neben dem Bild ein Text steht ("laedt ...",
  "kein Titelbild") - das waren nach der ersten Behebung noch 2 Pixel.
* ``_bibliothek_spaltenbreite`` ist die wirkliche Breite einer Kachelspalte
  (vorher rechneten Aufbau und Umordnen rund zehn Pixel zu wenig).
* Die Liste zeigt Vorschaubilder, die der Kachellader mitliefert.
* Umschalter (Quelle, Ansicht), Trefferzahl und das Nachfaerben nach einem
  Designwechsel.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("bibliothek_gestaltung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
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


def _abstand_gesamt(wert) -> int:
    """``padx`` aus grid_info() als Summe beider Seiten: 3 -> 6, (12, 0) -> 12."""
    if isinstance(wert, (tuple, list)):
        return sum(int(x) for x in wert)
    teile = str(wert).strip("()").replace(",", " ").split()
    return sum(int(t) for t in teile) if len(teile) > 1 else 2 * int(teile[0])


class TexteTests(unittest.TestCase):

    def test_die_neuen_texte_gibt_es_zweisprachig(self) -> None:
        for schluessel, platzhalter in (("library.sortiert_nach", {"spalte"}),
                                        ("library.sort_absteigend", set()),
                                        ("library.anzahl_titel", {"count"}),
                                        ("library.anzahl_treffer", {"sichtbar", "gesamt"})):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertTrue(text)
                    gefunden = {teil.split("}")[0] for teil in text.split("{")[1:]}
                    self.assertEqual(platzhalter, gefunden)

    def test_der_designwechsel_ruft_die_bibliothek(self) -> None:
        """_recolor_widget kennt keine Ringe und Raender - die Seite faerbt selbst nach."""
        self.assertIn("bibliothek['farben']()", ast.unparse(_methode("_apply_theme")))

    def test_nirgends_mehr_image_leer_im_bildkasten(self) -> None:
        """image="" laesst ein Label wieder in Zeichen messen - der Kasten fiele zusammen."""
        text = ast.unparse(_methode("_render_library_window"))
        self.assertNotIn("cover_label.configure(image='')", text)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class KachelMassTests(unittest.TestCase):
    """Die Kacheln selbst - ohne die Seite."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = GUI.__new__(GUI)
        cls.app._COLORS = dict(GUI._THEMES["dunkel"])
        cls.app._current_language = "de"
        cls._ordner = tempfile.TemporaryDirectory()
        cls.basis = Path(cls._ordner.name)
        cls.bilder = {}
        for name, groesse in (("quadrat", (512, 512)), ("quer", (512, 288)),
                              ("hoch", (288, 512))):
            datei = cls.basis / ("%s.png" % name)
            datei.write_bytes(_png(*groesse))
            cls.bilder[name] = str(datei)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._ordner.cleanup()

    def setUp(self) -> None:
        self.innen = tk.Frame(_WURZEL)
        self.addCleanup(self.innen.destroy)

    def _kacheln(self, titel: str = "Spiel", bei_bild=None) -> list:
        eintraege = [{"path": str(self.basis / "spiel.ffpfsc"), "kind": "ffpfsc",
                      "name": "spiel", "meta": {"title": titel, "title_id": "PPSA00001"}}]
        self.app._bibliothek_kacheln_setzen(self.innen, eintraege, gewaehlt="",
                                            bei_auswahl=lambda _e: None,
                                            bei_start=lambda _e: None,
                                            bei_bild=bei_bild)
        _WURZEL.update_idletasks()
        return eintraege

    def test_das_bildfeld_misst_in_jedem_zustand_gleich(self) -> None:
        feld = self._kacheln()[0]["_bildfeld"]
        kante = APP.pt(GUI._KACHEL_BILD_PT)
        generation = getattr(self.app, "_bibliothek_generation", 0)
        masse = {"laedt": (feld.winfo_reqwidth(), feld.winfo_reqheight())}
        self.app._bibliothek_bild_setzen(feld, "", kante, generation)
        _WURZEL.update_idletasks()
        masse["kein Bild"] = (feld.winfo_reqwidth(), feld.winfo_reqheight())
        for name, datei in self.bilder.items():
            self.app._bibliothek_bild_setzen(feld, datei, kante, generation)
            _WURZEL.update_idletasks()
            masse[name] = (feld.winfo_reqwidth(), feld.winfo_reqheight())
        self.assertEqual({(kante + 2, kante + 2)}, set(masse.values()), masse)

    def test_die_spaltenbreite_ist_die_wirkliche(self) -> None:
        """Mit langem Titel, der umbricht - er darf die Kachel nicht verbreitern."""
        kachel = self._kacheln("Tetris Effect Connected Deluxe Edition")[0]["_kachel"]
        kante = APP.pt(GUI._KACHEL_BILD_PT)
        abstand = _abstand_gesamt(kachel.grid_info()["padx"])
        self.assertEqual(kachel.winfo_reqwidth() + abstand,
                         GUI._bibliothek_spaltenbreite(kante))

    def test_markieren_aendert_die_groesse_nicht(self) -> None:
        """Gewaehlt wird die Farbe des Rings, nie seine Breite oder die Polsterung.

        Geprueft an den Angaben selbst, nicht an winfo_reqwidth(): Aendert
        sich der Ring eines Rahmens, meldet Tk die neue Groesse erst ueber
        ein Fensterereignis - und das gibt es nur fuer abgebildete Fenster.
        Die Tk-Wurzel der Tests ist verborgen; die Gegenprobe (Ring 3 statt
        2 px beim Waehlen) blieb am 27.09.2026 an der Groesse gemessen gruen.
        """
        eintraege = [{"path": str(self.basis / name), "kind": "ffpfsc", "name": name,
                      "meta": {"title": name}} for name in ("eins.ffpfsc", "zwei.ffpfsc")]
        self.app._bibliothek_kacheln_setzen(self.innen, eintraege, gewaehlt="",
                                            bei_auswahl=lambda _e: None,
                                            bei_start=lambda _e: None)

        def _masse(kachel) -> tuple:
            return tuple(str(kachel.cget(o)) for o in ("highlightthickness", "padx", "pady"))

        vorher = [_masse(e["_kachel"]) for e in eintraege]
        self.assertEqual(1, len(set(vorher)), vorher)
        self.app._bibliothek_kacheln_markieren(eintraege, eintraege[0]["path"])
        self.assertEqual(vorher, [_masse(e["_kachel"]) for e in eintraege])
        self.assertEqual(self.app._COLORS["fg_accent"],
                         str(eintraege[0]["_kachel"].cget("highlightbackground")))
        self.assertEqual(self.app._COLORS["border"],
                         str(eintraege[1]["_kachel"].cget("highlightbackground")))

    def test_das_geladene_bild_geht_auch_an_die_liste(self) -> None:
        geliefert: list = []
        eintraege = self._kacheln(bei_bild=lambda pfad, bild: geliefert.append((pfad, bild)))
        feld = eintraege[0]["_bildfeld"]
        kante = APP.pt(GUI._KACHEL_BILD_PT)
        generation = getattr(self.app, "_bibliothek_generation", 0)
        self.app._bibliothek_bild_setzen(feld, self.bilder["quer"], kante, generation)
        self.app._bibliothek_bild_setzen(feld, "", kante, generation)
        self.assertEqual([eintraege[0]["path"]] * 2, [p for p, _b in geliefert])
        self.assertIsNotNone(geliefert[0][1], "Das Titelbild kam nicht mit.")
        self.assertIsNone(geliefert[1][1], "'Kein Titelbild' muss None liefern.")

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
        cls._ordner = tempfile.TemporaryDirectory()
        basis = Path(cls._ordner.name)
        speicher = cls.app._bibliothek_bildspeicher()
        cls.eintraege = []
        # "laedt" steht nicht im Bildspeicher - die Detailspalte zeigt dann
        # "laedt ..." und holt das Bild im Faden.
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
        cls._speichern.stop()
        cls._laden.stop()
        cls._ordner.cleanup()

    def setUp(self) -> None:
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        self.zustand = self.app._bibliothek
        self.zustand["eintraege"][:] = self.eintraege
        self.zustand["filtern"]()
        _WURZEL.update_idletasks()

    def tearDown(self) -> None:
        self.zustand["eintraege"].clear()
        self.zustand["filtern"]()

    def test_die_detailspalte_haengt_an_keiner_auswahl(self) -> None:
        cover, detail = self.zustand["cover"], self.zustand["detail"]
        bildkasten = {"nichts gewaehlt": self.vorher[:2]}
        breiten = {"nichts gewaehlt": self.vorher[2]}
        for eintrag in self.eintraege:
            self.zustand["details"](eintrag)
            _WURZEL.update()      # wie im Programm: auch Fensterereignisse
            bildkasten[eintrag["name"]] = (cover.winfo_reqwidth(), cover.winfo_reqheight())
            breiten[eintrag["name"]] = detail.winfo_reqwidth()
        self.assertEqual(1, len(set(bildkasten.values())), bildkasten)
        # Das Raster zaehlt den Abstand zur Kachelflaeche (padx=12) in die
        # Spalte. Verlangt der Inhalt nie mehr als reserviert, bleibt die
        # Spalte so breit, wie reserviert ist - bei jeder Auswahl.
        abstand = _abstand_gesamt(detail.grid_info()["padx"])
        reserviert = int(detail.master.grid_columnconfigure(1)["minsize"])
        self.assertLessEqual(max(breiten.values()) + abstand, reserviert, breiten)

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
                            "Das Titelbild der Kachel kam in der Liste nicht an.")

    def test_die_umschalter(self) -> None:
        seite = self.app._bibliothek_seite
        knoepfe = {str(w.cget("value")): w for w in _alle(seite)
                   if w.winfo_class() == "Radiobutton"}
        self.assertEqual({"pc", "ps5", "kacheln", "liste"}, set(knoepfe))
        for wert, knopf in knoepfe.items():
            with self.subTest(wert=wert):
                self.assertEqual(0, int(knopf.cget("indicatoron")), "Kreis statt Knopfstil")
        liste_rahmen = self.zustand["liste"].master
        knoepfe["liste"].invoke()
        try:
            self.assertEqual("liste", self.zustand["ansicht"]["art"])
            self.assertTrue(liste_rahmen.winfo_manager())
            self.assertEqual("liste", self._einstellungen["library_ansicht"])
            c = self.app._COLORS
            self.assertEqual(c["fg_primary"], str(knoepfe["liste"].cget("fg")))
            self.assertEqual(c["fg_secondary"], str(knoepfe["kacheln"].cget("fg")))
        finally:
            knoepfe["kacheln"].invoke()
        self.assertEqual("kacheln", self.zustand["ansicht"]["art"])
        self.assertFalse(liste_rahmen.winfo_manager())

    def test_die_trefferzahl(self) -> None:
        seite = self.app._bibliothek_seite
        suche = next(w for w in _alle(seite) if w.winfo_class() == "TEntry")

        def _texte() -> set:
            return {str(w.cget("text")) for w in _alle(seite) if w.winfo_class() == "Label"}

        gesamt = len(self.eintraege)
        self.assertIn(self.app._t("library.anzahl_titel", count=gesamt), _texte())
        suche.insert(0, "quer")
        try:
            self.assertIn(self.app._t("library.anzahl_treffer", sichtbar=1, gesamt=gesamt),
                          _texte())
        finally:
            suche.delete(0, "end")

    def test_nachfaerben_erreicht_ringe_und_raender(self) -> None:
        alt = self.app._COLORS
        hell = dict(GUI._THEMES["hell"])
        self.app._COLORS = hell
        try:
            self.zustand["farben"]()
            gewaehlt = self.zustand["ansicht"]["gewaehlt"]
            for eintrag in self.eintraege:
                with self.subTest(eintrag=eintrag["name"]):
                    ring = hell["fg_accent"] if eintrag["path"] == gewaehlt else hell["border"]
                    self.assertEqual(ring, str(eintrag["_kachel"].cget("highlightbackground")))
                    self.assertEqual(hell["console_bg"], str(eintrag["_bildfeld"].cget("bg")))
            self.assertEqual(hell["border"], str(self.zustand["detail"].cget("highlightbackground")))
            self.assertEqual(hell["console_bg"], str(self.zustand["cover"].cget("bg")))
            self.assertEqual(hell["console_bg"], str(self.zustand["kachelflaeche"].cget("bg")))
        finally:
            self.app._COLORS = alt
            self.zustand["farben"]()


if __name__ == "__main__":
    unittest.main(verbosity=2)
