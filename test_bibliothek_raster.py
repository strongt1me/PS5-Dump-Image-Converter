# -*- coding: utf-8 -*-
"""Die gezeichneten Bausteine der Bibliothek mit Tk: Knoepfe, Chips, Karten und das Raster (03.10.2026).

``ps5_validator.utils.bibliothek_raster`` kennt das Hauptprogramm nicht - Palette,
Schrift und Texte kommen als Rueckrufe herein. Deshalb laesst sich alles mit einem
verborgenen Tk-Fenster pruefen, ohne die Seite zu bauen. Bewacht wird:

* ``KartenKnopf``: Breite folgt dem Text, ein gesperrter Knopf tut nichts (sagt aber
  auf Wunsch, dass er gesperrt ist), Chips schalten um, der Fokus ist zu sehen.
* ``RundeKarte``: Die Hoehe folgt dem Inhalt - am 03.10.2026 fehlte die Kopfkarte, weil
  ein Fenster auf einer Zeichenflaeche ausserhalb des sichtbaren Bereichs kein
  Groessenereignis bekommt.
* ``FlussZeile``: bricht um statt zu quetschen; das Suchfeld waechst, der rechte
  Rand bleibt rechts.
* ``KartenRaster``: Karten gleich gross und buendig, Treffer und Klick, Hover, Auswahl
  verschiebt nichts, Chips kommen nach, ohne dass etwas springt.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("bibliothek_raster")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import bibliothek_raster as raster  # noqa: E402
from ps5_validator.utils import bibliothek_zeichnen as zeichnen  # noqa: E402

try:
    import tkinter as tk
    from PIL import Image
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

THEMEN = APP.PS5ConverterGUI._THEMES


def _ereignis(x: int = 5, y: int = 5):
    return types.SimpleNamespace(x=x, y=y, delta=0, widget=None)


class _Palette:
    """Eine umschaltbare Palette - wie ``PS5ConverterGUI._COLORS`` beim Designwechsel."""

    def __init__(self, name: str = "dunkel") -> None:
        self.farben = dict(THEMEN[name])

    def __call__(self) -> dict:
        return self.farben

    def setzen(self, name: str) -> None:
        self.farben = dict(THEMEN[name])


def _zeichner(name: str = "dunkel") -> tuple["raster.Zeichner", _Palette]:
    palette = _Palette(name)
    return raster.Zeichner(_WURZEL, palette, APP.UI_SCHRIFT, APP.pt), palette


def _png(ordner: str, name: str, groesse=(512, 512), farbe=(120, 60, 30)) -> str:
    pfad = os.path.join(ordner, name)
    Image.new("RGB", groesse, farbe).save(pfad)
    return pfad


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class ZeichnerTests(unittest.TestCase):

    def test_die_skalierung_kommt_von_tk_scaling(self) -> None:
        z, _p = _zeichner()
        erwartet = float(_WURZEL.tk.call("tk", "scaling")) / (96.0 / 72.0)
        self.assertAlmostEqual(erwartet, z.faktor, places=6)
        self.assertEqual(round(10 * erwartet), z.px(10))

    def test_der_faktor_wird_gemerkt_und_laesst_sich_neu_messen(self) -> None:
        z, _p = _zeichner()
        echt = z.faktor
        z._faktor = 2.0                          # was gemerkt ist, wird nicht noch einmal erfragt
        self.assertEqual(2.0, z.faktor)
        self.assertEqual(20, z.px(10))
        z.neu_messen()
        self.assertIsNone(z._faktor)
        self.assertEqual(echt, z.faktor)

    def test_schriften_werden_einmal_angelegt(self) -> None:
        z, _p = _zeichner()
        self.assertIs(z.schrift("titel"), z.schrift("titel"))
        self.assertGreater(z.messen("titel", "Assassin's Creed"), z.messen("titel", "Tetris"))
        self.assertGreater(z.zeilenhoehe("titel"), 8)
        for rolle in z.SCHRIFTEN:
            with self.subTest(rolle=rolle):
                familie, groesse, gewicht = z.schrift_angabe(rolle)
                self.assertEqual(APP.UI_SCHRIFT, familie)
                self.assertGreater(groesse, 5)

    def test_fotos_kommen_aus_dem_speicher_und_folgen_der_palette(self) -> None:
        z, palette = _zeichner()
        baut = []

        def _erzeuger():
            baut.append(1)
            return Image.new("RGBA", (6, 6), (255, 0, 0, 255))

        eins = z.foto(("test", 1), _erzeuger)
        zwei = z.foto(("test", 1), _erzeuger)
        self.assertIs(eins, zwei)
        self.assertEqual(1, len(baut))
        palette.setzen("hell")                    # Designwechsel: kein altes Bild trifft mehr
        drei = z.foto(("test", 1), _erzeuger)
        self.assertIsNot(eins, drei)
        self.assertEqual(2, len(baut))
        z.leeren()
        z.foto(("test", 1), _erzeuger)
        self.assertEqual(3, len(baut))

    def test_titelbilder_kommen_aus_dem_speicher(self) -> None:
        """Filtern, Sortieren und Rollen zeichnen dieselben Karten immer wieder - 10 ms je Titelbild."""
        z, _p = _zeichner()
        with tempfile.TemporaryDirectory() as ordner:
            datei = _png(ordner, "a.png")
            eins = z.poster_foto(datei, 80, 80, 8)
            zwei = z.poster_foto(datei, 80, 80, 8)
            self.assertIs(eins, zwei, "Dasselbe Titelbild in derselben Groesse wird nicht noch einmal gebaut.")
            self.assertEqual((80, 80), (eins.width(), eins.height()))
            drei = z.poster_foto(datei, 90, 90, 8)
            self.assertIsNot(eins, drei, "Eine andere Groesse ist ein anderes Bild.")
            self.assertEqual((90, 90), (drei.width(), drei.height()))

    def test_ein_neu_geladenes_titelbild_trifft_das_alte_nicht(self) -> None:
        z, _p = _zeichner()
        with tempfile.TemporaryDirectory() as ordner:
            datei = _png(ordner, "a.png", farbe=(200, 0, 0))
            alt = z.poster_foto(datei, 40, 40, 6)
            _png(ordner, "a.png", farbe=(0, 0, 200))
            stand = os.stat(datei)
            os.utime(datei, ns=(stand.st_atime_ns, stand.st_mtime_ns + 5_000_000_000))
            neu = z.poster_foto(datei, 40, 40, 6)
            self.assertIsNot(alt, neu, "Gleicher Name, neuer Inhalt: ein neues Bild.")

    def test_ein_unlesbares_oder_fehlendes_titelbild_gibt_none_und_wird_nicht_gemerkt(self) -> None:
        z, _p = _zeichner()
        with tempfile.TemporaryDirectory() as ordner:
            kaputt = os.path.join(ordner, "x.png")
            Path(kaputt).write_bytes(b"kein Bild")
            self.assertIsNone(z.poster_foto(kaputt, 40, 40, 6))
            self.assertIsNone(z.poster_foto(os.path.join(ordner, "gibt_es_nicht.png"), 40, 40, 6))
        self.assertEqual((0, 0), (len(z._poster), z._poster_bytes))

    def test_der_bildspeicher_der_titelbilder_ist_nach_bytes_begrenzt(self) -> None:
        z, _p = _zeichner()
        z.POSTER_SPEICHER = 2 * 50 * 50 * 4 + 100          # Platz fuer zwei Titelbilder zu 50 x 50
        with tempfile.TemporaryDirectory() as ordner:
            dateien = [_png(ordner, "b%d.png" % n, farbe=(10 * n, 20, 30)) for n in range(3)]
            fotos = [z.poster_foto(d, 50, 50, 6) for d in dateien]
            self.assertEqual(2, len(z._poster), "Das dritte verdraengt das aelteste.")
            self.assertEqual(2 * 50 * 50 * 4, z._poster_bytes)
            self.assertIs(fotos[2], z.poster_foto(dateien[2], 50, 50, 6))
            self.assertIs(fotos[1], z.poster_foto(dateien[1], 50, 50, 6))
            self.assertIsNot(fotos[0], z.poster_foto(dateien[0], 50, 50, 6), "Das aelteste war weg und wird neu gebaut.")
            self.assertEqual(2, len(z._poster))
            z.POSTER_SPEICHER = 10                         # ein einzelnes Bild bleibt auch dann
            neu = z.poster_foto(dateien[2], 50, 50, 6)     # (dieses war verdraengt: wird gebaut und eingefuegt)
            self.assertEqual(1, len(z._poster))
            self.assertIs(neu, z.poster_foto(dateien[2], 50, 50, 6))

    def test_ein_designwechsel_laesst_die_titelbilder_stehen_eine_neue_skalierung_nicht(self) -> None:
        z, palette = _zeichner()
        with tempfile.TemporaryDirectory() as ordner:
            datei = _png(ordner, "a.png")
            eins = z.poster_foto(datei, 40, 40, 6)
            palette.setzen("hell")
            z.leeren()
            self.assertIs(eins, z.poster_foto(datei, 40, 40, 6), "Ein Titelbild kennt keine Palette.")
            z.neu_messen()
            self.assertEqual((0, 0), (len(z._poster), z._poster_bytes))

    def test_der_versatz_des_scheins_stimmt_mit_dem_bild_ueberein(self) -> None:
        """``glow_versatz`` rechnet, ohne das Bild zu bauen - es darf dem gebauten nie widersprechen."""
        z, _p = _zeichner()
        for zustand in ("normal", "hover", "gedrueckt", "gesperrt"):
            foto, versatz = z.knopf_foto("akzent", zustand, 200, 40)
            with self.subTest(zustand=zustand):
                self.assertEqual(z.glow_versatz(zustand), versatz)
                if zustand in ("normal", "hover"):
                    links, oben, unten = z.glow_rand("akzent")
                    self.assertEqual((200 + 2 * links, 40 + oben + unten), (foto.width(), foto.height()))
                    self.assertEqual((links, oben), versatz)
                else:
                    self.assertEqual((200, 40), (foto.width(), foto.height()))
                    self.assertEqual((0, 0), versatz)

    def test_flache_knoepfe_haben_keinen_scheinrand(self) -> None:
        z, _p = _zeichner()
        for stil in ("flaeche", "auswahl", "chip", "chip_an"):
            foto, versatz = z.knopf_foto(stil, "normal", 120, 34)
            self.assertEqual((120, 34, (0, 0)), (foto.width(), foto.height(), versatz))
            self.assertEqual((0, 0, 0), z.glow_rand(stil))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class KartenKnopfTests(unittest.TestCase):

    def setUp(self) -> None:
        self.z, self.palette = _zeichner()
        self.rahmen = tk.Frame(_WURZEL)
        self.addCleanup(self.rahmen.destroy)

    def _knopf(self, **kw) -> "raster.KartenKnopf":
        knopf = raster.KartenKnopf(self.rahmen, self.z, kw.pop("text", "Kopieren"), **kw)
        return knopf

    def test_die_breite_folgt_dem_text(self) -> None:
        kurz, lang = self._knopf(text="OK"), self._knopf(text="Infos & Metadaten verwalten")
        self.assertGreater(int(lang.cget("width")), int(kurz.cget("width")))
        kurz.configure(text="Ein deutlich laengerer Text")
        self.assertGreater(int(kurz.cget("width")), int(self._knopf(text="OK").cget("width")))
        self.assertEqual("Ein deutlich laengerer Text", kurz.cget("text"))

    def test_eine_feste_breite_bleibt(self) -> None:
        knopf = self._knopf(text="Sehr langer Text ueber die Breite hinaus", breite=140)
        self.assertEqual(140, int(knopf.cget("width")))
        knopf.configure(text="x")
        self.assertEqual(140, int(knopf.cget("width")))

    def test_der_akzentknopf_reserviert_platz_fuer_den_schein(self) -> None:
        flach = self._knopf(stil="flaeche", breite=200, hoehe=40)
        akzent = self._knopf(stil="akzent", breite=200, hoehe=40)
        self.assertGreater(int(akzent.cget("width")), int(flach.cget("width")))
        self.assertGreater(int(akzent.cget("height")), int(flach.cget("height")))

    @staticmethod
    def _abgebildet(knopf):
        """Ein verborgenes Fenster misst 1 x 1 - so gross, wie der Knopf waere, wenn man ihn sehen koennte."""
        return (mock.patch.object(knopf, "winfo_width", return_value=int(knopf.cget("width"))),
                mock.patch.object(knopf, "winfo_height", return_value=int(knopf.cget("height"))))

    def test_ein_klick_loest_aus(self) -> None:
        aufrufe = []
        knopf = self._knopf(command=lambda: aufrufe.append(1))
        breite, hoehe = self._abgebildet(knopf)
        with breite, hoehe:
            knopf._druecken(_ereignis())
            self.assertEqual("gedrueckt", knopf._zustand())
            knopf._loslassen(_ereignis())
        self.assertEqual([1], aufrufe)
        knopf.invoke()
        self.assertEqual([1, 1], aufrufe)

    def test_loslassen_ausserhalb_loest_nicht_aus(self) -> None:
        aufrufe = []
        knopf = self._knopf(command=lambda: aufrufe.append(1), breite=100, hoehe=30)
        with mock.patch.object(knopf, "winfo_width", return_value=100), \
                mock.patch.object(knopf, "winfo_height", return_value=30):
            knopf._druecken(_ereignis())
            knopf._loslassen(_ereignis(x=400, y=5))
        self.assertEqual([], aufrufe)

    def test_ein_gesperrter_knopf_tut_nichts_sagt_aber_warum(self) -> None:
        aufrufe, gesperrt = [], []
        knopf = self._knopf(command=lambda: aufrufe.append(1), state="disabled",
                            gesperrt_befehl=lambda: gesperrt.append(1))
        breite, hoehe = self._abgebildet(knopf)
        with breite, hoehe:
            knopf._druecken(_ereignis())
            knopf._loslassen(_ereignis())
        knopf.invoke()
        self.assertEqual([], aufrufe)
        self.assertEqual([1], gesperrt)
        self.assertEqual("gesperrt", knopf._zustand())
        self.assertEqual("disabled", knopf.cget("state"))
        knopf.configure(state="normal")
        knopf.invoke()
        self.assertEqual([1], aufrufe)

    def test_der_hover_zeigt_sich(self) -> None:
        knopf = self._knopf()
        self.assertEqual("normal", knopf._zustand())
        knopf._betreten()
        self.assertEqual("hover", knopf._zustand())
        knopf._verlassen()
        self.assertEqual("normal", knopf._zustand())

    def test_chips_schalten_um(self) -> None:
        chip = self._knopf(stil="chip")
        self.assertEqual("chip", chip.stil)
        chip.configure(an=True)
        self.assertEqual("chip_an", chip.stil)
        self.assertTrue(chip.an)
        flaeche = self._knopf(stil="flaeche")
        flaeche.configure(an=True)
        self.assertEqual("flaeche", flaeche.stil, "Nur Chips zeigen eine Wahl.")

    def test_tastatur_leertaste_und_eingabe(self) -> None:
        aufrufe = []
        knopf = self._knopf(command=lambda: aufrufe.append(1))
        self.assertEqual("break", knopf._taste())
        self.assertEqual([1], aufrufe)
        self.assertEqual("1", str(knopf.cget("takefocus")))

    def test_der_fokus_ist_zu_sehen(self) -> None:
        knopf = self._knopf()
        ohne = len(knopf.find_all())
        knopf._fokus_ein()
        self.assertEqual(ohne + 1, len(knopf.find_all()), "Ein Strich als Fokusanzeige.")
        knopf._fokus_aus()
        self.assertEqual(ohne, len(knopf.find_all()))
        gesperrt = self._knopf(state="disabled")
        gesperrt._fokus_ein()
        self.assertEqual(len(self._knopf(state="disabled").find_all()), len(gesperrt.find_all()),
                         "Ein gesperrter Knopf zeigt keinen Fokus.")

    def test_nach_einem_designwechsel_stimmen_grund_und_bild(self) -> None:
        knopf = self._knopf(grund="bg_card")
        self.assertEqual(self.palette()["bg_card"], str(knopf.cget("bg")))
        vorher = knopf._knopf.fotos["bild"]
        self.palette.setzen("hell")
        knopf.neu_faerben()
        self.assertEqual(self.palette()["bg_card"], str(knopf.cget("bg")))
        self.assertIsNot(vorher, knopf._knopf.fotos["bild"])

    def test_die_pruefung_kann_ihn_vermessen(self) -> None:
        knopf = self._knopf(text="Konvertieren")
        self.assertEqual("Konvertieren", knopf.diagnose_beschriftung())
        breite, hoehe = knopf.diagnose_wunschmass()
        self.assertGreater(breite, 30)
        self.assertGreater(hoehe, 8)
        self.assertLessEqual(breite, int(knopf.cget("width")), "Der Text passt in den Knopf.")
        self.assertLessEqual(hoehe, int(knopf.cget("height")))

    def test_alte_aufrufer_mit_bg_und_fg_stoeren_nicht(self) -> None:
        knopf = self._knopf()
        knopf.configure(bg="#123456", fg="#abcdef", text="Neu")
        self.assertEqual("Neu", knopf.cget("text"))
        self.assertEqual(self.palette()["bg_card"], str(knopf.cget("bg")), "Die Rolle zaehlt, nicht der Wert.")


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class ChipGruppeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.z, self.palette = _zeichner()
        self.rahmen = tk.Frame(_WURZEL)
        self.addCleanup(self.rahmen.destroy)
        self.var = tk.StringVar(master=_WURZEL, value="b")
        self.gerufen: list = []
        self.sprache = {"a": "Alle"}
        self.gruppe = raster.ChipGruppe(
            self.rahmen, self.z, [("a", lambda: self.sprache["a"]), ("b", "Zwei"), ("c", "Drei")],
            self.var, befehl=lambda: self.gerufen.append(self.var.get()))

    def test_die_variable_bewegt_die_auswahl(self) -> None:
        self.assertEqual([False, True, False], [c.an for c in self.gruppe.chips])
        self.var.set("c")
        self.assertEqual([False, False, True], [c.an for c in self.gruppe.chips])

    def test_ein_klick_setzt_die_variable_und_ruft_den_befehl(self) -> None:
        self.gruppe.chips[0].invoke()
        self.assertEqual("a", self.var.get())
        self.assertEqual(["a"], self.gerufen, "Die Variable steht schon, wenn der Befehl laeuft.")
        self.assertEqual([True, False, False], [c.an for c in self.gruppe.chips])

    def test_ein_zweiter_klick_auf_dasselbe_ruft_den_befehl_trotzdem(self) -> None:
        self.gruppe.chips[1].invoke()
        self.assertEqual(["b"], self.gerufen)

    def test_texte_folgen_dem_sprachwechsel(self) -> None:
        self.sprache["a"] = "All"
        self.gruppe.beschriften()
        self.assertEqual("All", self.gruppe.chips[0].cget("text"))
        self.assertEqual("Zwei", self.gruppe.chips[1].cget("text"), "Feste Texte bleiben.")

    def test_designwechsel_faerbt_alle_chips(self) -> None:
        self.palette.setzen("hell")
        self.gruppe.neu_faerben()
        self.assertEqual(self.palette()["bg_card"], str(self.gruppe.cget("bg")))
        for chip in self.gruppe.chips:
            self.assertEqual(self.palette()["bg_card"], str(chip.cget("bg")))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class RundeKarteTests(unittest.TestCase):

    def setUp(self) -> None:
        self.z, self.palette = _zeichner()
        self.eltern = tk.Frame(_WURZEL)
        self.addCleanup(self.eltern.destroy)

    def test_die_hoehe_folgt_dem_inhalt(self) -> None:
        """Die Kopfkarte fehlte, weil ihre Hoehe an einem Groessenereignis hing, das nie kam."""
        karte = raster.RundeKarte(self.eltern, self.z, polster=(20, 16))
        karte.pack(fill="x")
        py = 2 * self.z.px(16)
        zeile = tk.Frame(karte.innen, width=100, height=80)
        zeile.pack()
        _WURZEL.update_idletasks()
        self.assertEqual(80 + py, karte.winfo_reqheight())
        zeile.configure(height=150)
        _WURZEL.update_idletasks()
        self.assertEqual(150 + py, karte.winfo_reqheight(), "Die Karte waechst mit - ohne Ereignis.")

    def test_das_polster_umgibt_den_inhalt(self) -> None:
        karte = raster.RundeKarte(self.eltern, self.z, polster=(20, 16))
        karte.pack()
        tk.Frame(karte.innen, width=100, height=50).pack()
        _WURZEL.update_idletasks()
        self.assertEqual(100 + 2 * self.z.px(20), karte.winfo_reqwidth())
        self.assertEqual(50 + 2 * self.z.px(16), karte.winfo_reqheight())

    def test_das_bild_hat_die_groesse_der_karte(self) -> None:
        karte = raster.RundeKarte(self.eltern, self.z)
        with mock.patch.object(karte, "winfo_width", return_value=300), \
                mock.patch.object(karte, "winfo_height", return_value=120):
            karte._bild_neu()
        self.assertEqual((300, 120), (karte._foto.width(), karte._foto.height()))
        self.assertEqual((300, 120), karte._groesse_gemalt)

    def test_ein_winziges_fenster_malt_nichts(self) -> None:
        karte = raster.RundeKarte(self.eltern, self.z)
        with mock.patch.object(karte, "winfo_width", return_value=1), \
                mock.patch.object(karte, "winfo_height", return_value=1):
            karte._bild_neu()
        self.assertIsNone(karte._foto)

    def test_die_farben_folgen_dem_design(self) -> None:
        karte = raster.RundeKarte(self.eltern, self.z)
        self.assertEqual(self.palette()["bg_card"], str(karte.innen.cget("bg")))
        self.assertEqual(self.palette()["bg_main"], str(karte.cget("bg")))
        self.palette.setzen("hell")
        with mock.patch.object(karte, "winfo_width", return_value=200), \
                mock.patch.object(karte, "winfo_height", return_value=80):
            karte.neu_faerben()
        self.assertEqual(self.palette()["bg_card"], str(karte.innen.cget("bg")))
        self.assertEqual(self.palette()["bg_main"], str(karte.cget("bg")))
        self.assertEqual(self.palette()["bg_main"], str(karte._hintergrund.cget("bg")),
                         "Die Ecken zeigen den Grund, auf dem die Karte steht.")

    def test_eine_fuellende_karte_gibt_dem_inhalt_den_platz(self) -> None:
        karte = raster.RundeKarte(self.eltern, self.z, fuellend=True)
        info = karte.innen.pack_info()
        self.assertEqual("both", str(info["fill"]))
        self.assertEqual(1, int(info["expand"]))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FlussZeileTests(unittest.TestCase):

    def setUp(self) -> None:
        self.z, _p = _zeichner()
        self.eltern = tk.Frame(_WURZEL)
        self.addCleanup(self.eltern.destroy)
        self.zeile = raster.FlussZeile(self.eltern, self.z, abstand=(10, 10))
        self.zeile.pack(fill="x")
        #: Die Abstaende wachsen mit der Anzeigeskalierung - die Erwartungen rechnen mit.
        self.luft = self.z.px(10)

    def _kind(self, b: int, h: int = 20) -> tk.Frame:
        return tk.Frame(self.zeile, width=b, height=h)

    def _verteilen(self, breite: int) -> None:
        _WURZEL.update_idletasks()
        with mock.patch.object(self.zeile, "winfo_width", return_value=breite):
            self.zeile.neu_verteilen()

    @staticmethod
    def _lage(kind) -> tuple[int, int]:
        info = kind.place_info()
        return int(info["x"]), int(info["y"])

    def test_was_passt_steht_nebeneinander(self) -> None:
        a, b = self._kind(100), self._kind(100)
        self.zeile.hinzufuegen(a)
        self.zeile.hinzufuegen(b)
        self._verteilen(300)
        self.assertEqual((0, 0), self._lage(a))
        self.assertEqual((100 + self.luft, 0), self._lage(b))

    def test_was_nicht_passt_bricht_um(self) -> None:
        a, b = self._kind(100), self._kind(100)
        self.zeile.hinzufuegen(a)
        self.zeile.hinzufuegen(b)
        self._verteilen(150)
        self.assertEqual((0, 0), self._lage(a))
        self.assertEqual((0, 20 + self.luft), self._lage(b), "Zeile 2: Hoehe 20 plus Abstand.")
        self.assertEqual(40 + self.luft, int(float(self.zeile.cget("height"))),
                         "Die Zeile meldet ihre Hoehe selbst.")

    def test_das_flexkind_waechst_bis_zur_zeilenbreite(self) -> None:
        such, knopf = self._kind(10), self._kind(80)
        self.zeile.hinzufuegen(such, flex=True, min_breite=40)
        self.zeile.hinzufuegen(knopf)
        self._verteilen(400)
        self.assertEqual(400 - 80 - self.luft, int(such.place_info()["width"]))
        self.assertEqual(400 - 80, self._lage(knopf)[0], "Der Knopf endet am rechten Rand.")

    def test_reicht_es_nur_fuer_das_flexkind_bekommt_es_die_ganze_zeile(self) -> None:
        such, knopf = self._kind(10), self._kind(300)
        self.zeile.hinzufuegen(such, flex=True, min_breite=200)
        self.zeile.hinzufuegen(knopf)
        self._verteilen(350)
        self.assertEqual(350, int(such.place_info()["width"]))
        self.assertEqual((0, 20 + self.luft), self._lage(knopf))

    def test_rechts_sitzt_am_rechten_rand_und_behaelt_die_reihenfolge(self) -> None:
        titel = self._kind(120)
        eins, zwei = self._kind(60), self._kind(80)
        self.zeile.hinzufuegen(titel)
        self.zeile.hinzufuegen(eins, rechts=True)
        self.zeile.hinzufuegen(zwei, rechts=True)
        self._verteilen(500)
        self.assertEqual(0, self._lage(titel)[0])
        self.assertEqual(500 - 80, self._lage(zwei)[0])
        self.assertEqual(500 - 80 - self.luft - 60, self._lage(eins)[0],
                         "Zuerst Hinzugefuegtes steht links davon.")

    def test_kinder_werden_in_der_zeile_mittig_ausgerichtet(self) -> None:
        hoch, flach = self._kind(50, 40), self._kind(50, 20)
        self.zeile.hinzufuegen(hoch)
        self.zeile.hinzufuegen(flach)
        self._verteilen(300)
        self.assertEqual(0, self._lage(hoch)[1])
        self.assertEqual(10, self._lage(flach)[1])

    def test_ein_gleicher_zustand_rechnet_nicht_neu(self) -> None:
        a = self._kind(100)
        self.zeile.hinzufuegen(a)
        self._verteilen(300)
        with mock.patch.object(a, "place") as gesetzt, \
                mock.patch.object(self.zeile, "winfo_width", return_value=300):
            self.zeile._verteilen()
        gesetzt.assert_not_called()


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SuchFeldTests(unittest.TestCase):

    def setUp(self) -> None:
        self.z, self.palette = _zeichner()
        self.eltern = tk.Frame(_WURZEL)
        self.addCleanup(self.eltern.destroy)
        self.var = tk.StringVar(master=_WURZEL)
        self.feld = raster.SuchFeld(self.eltern, self.z, self.var, "Titel suchen")
        self.feld.pack(fill="x")

    def test_der_platzhalter_steht_im_leeren_feld(self) -> None:
        self.assertTrue(self.feld._platz.place_info())
        self.assertEqual("Titel suchen", self.feld._platz.cget("text"))
        self.assertEqual("", self.var.get(), "Der Platzhalter ist kein Text im Feld.")

    def test_getippter_text_verdraengt_den_platzhalter(self) -> None:
        self.var.set("elden")
        self.assertFalse(self.feld._platz.place_info())
        self.assertEqual("elden", self.feld.eingabe.get())
        self.var.set("")
        self.assertTrue(self.feld._platz.place_info())

    def test_ein_klick_auf_den_platzhalter_fokussiert_das_feld(self) -> None:
        with mock.patch.object(self.feld.eingabe, "focus_set") as fokus:
            self.feld._platzhalter_klick(_ereignis())
        fokus.assert_called_once()
        self.assertTrue(self.feld._platz.bind("<Button-1>"), "Der Platzhalter ist wirklich gebunden.")

    def test_der_platzhalter_folgt_dem_sprachwechsel(self) -> None:
        self.feld.beschriften("Search title")
        self.assertEqual("Search title", self.feld._platz.cget("text"))

    def test_designwechsel(self) -> None:
        self.palette.setzen("hell")
        with mock.patch.object(self.feld, "winfo_width", return_value=200), \
                mock.patch.object(self.feld, "winfo_height", return_value=40):
            self.feld.neu_faerben()
        hell = self.palette()
        self.assertEqual(hell["console_bg"], str(self.feld.eingabe.cget("bg")))
        self.assertEqual(hell["fg_primary"], str(self.feld.eingabe.cget("fg")))
        self.assertEqual(hell["fg_secondary"], str(self.feld._platz.cget("fg")))
        self.assertEqual(hell["console_bg"], str(self.feld._platz.cget("bg")))


# ---------------------------------------------------------------------------
# Das Kartenraster
# ---------------------------------------------------------------------------

def _eintrag(nummer: int, titel: str | None = None, **zusatz) -> dict:
    eintrag = {"path": "/data/homebrew/spiel%02d" % nummer, "kind": "folder",
               "meta": {"title": titel or "Spiel %d" % nummer, "title_id": "PPSA%05d" % nummer},
               "title_id": "PPSA%05d" % nummer, "ps5": True, "size": None}
    eintrag.update(zusatz)
    return eintrag


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class KartenRasterTests(unittest.TestCase):

    BREITE = 1400
    HOEHE = 900

    def setUp(self) -> None:
        self.z, self.palette = _zeichner()
        self.eltern = tk.Frame(_WURZEL)
        self.addCleanup(self.eltern.destroy)
        self.ereignisse: list = []
        self.chips: dict = {}
        self.sperren: set = set()
        self.raster = raster.KartenRaster(
            self.z, self.eltern, inhalt=self._inhalt,
            aktion=lambda n, e: self.ereignisse.append(("aktion", n, e["path"])),
            bei_auswahl=lambda e: self.ereignisse.append(("auswahl", e["path"])),
            bei_start=lambda e: self.ereignisse.append(("start", e["path"])),
            bei_gesperrt=lambda n, e: self.ereignisse.append(("gesperrt", n, e["path"])),
            symbol=lambda g, f: Image.new("RGBA", (g, g), (255, 255, 255, 80)),
            texte=lambda k: {"laedt": "laedt ...", "ohne_bild": "kein Titelbild"}[k])
        self.raster.rahmen.pack(fill="both", expand=True)
        self._breite = mock.patch.object(self.raster.flaeche, "winfo_width", side_effect=lambda: self.BREITE)
        self._hoehe = mock.patch.object(self.raster.flaeche, "winfo_height", side_effect=lambda: self.HOEHE)
        self._breite.start()
        self._hoehe.start()
        self.addCleanup(self._breite.stop)
        self.addCleanup(self._hoehe.stop)

    def _inhalt(self, eintrag: dict) -> dict:
        pfad = eintrag["path"]
        return {
            "titel": eintrag["meta"]["title"], "plattform": "PS5",
            "chips": self.chips.get(pfad, [("Dump-Ordner", "neutral")]),
            "knoepfe": [raster.KnopfSpec("info", "Infos & Metadaten", "auswahl", True, chevron=True),
                        raster.KnopfSpec("start", "Starten", "akzent", True, fett=True),
                        raster.KnopfSpec("kopieren", "Kopieren", "flaeche", (pfad, "kopieren") not in self.sperren),
                        raster.KnopfSpec("konvertieren", "Konvertieren", "flaeche",
                                         (pfad, "konvertieren") not in self.sperren)]}

    def _setzen(self, anzahl: int = 9, gewaehlt: str = "") -> list[dict]:
        eintraege = [_eintrag(n) for n in range(anzahl)]
        self.raster.setzen(eintraege, gewaehlt)
        return eintraege

    def _knopf(self, nummer: int, name: str):
        karte = self.raster.karten[nummer]
        return next(k for k in karte.knoepfe if k.spec.name == name)

    # --- Aufbau und Raster -----------------------------------------------------------------------
    def test_das_raster_fuellt_die_breite_mit_gleich_grossen_karten(self) -> None:
        self._setzen(9)
        spalten, breite = zeichnen.spalten_berechnen(self.BREITE, self.raster._masse.karte_min,
                                                     self.raster._masse.abstand, 0)
        self.assertEqual(spalten, self.raster.spalten)
        self.assertEqual(breite, self.raster.kartenbreite)
        self.assertEqual({(k.b, k.h) for k in self.raster.karten}, {(breite, self.raster.kartenhoehe)},
                         "Alle Karten sind gleich gross.")
        erste, letzte_der_reihe = self.raster.karten[0], self.raster.karten[spalten - 1]
        self.assertEqual(0, erste.x, "Buendig mit der Kopfkarte: kein eigener Rand.")
        self.assertLessEqual(letzte_der_reihe.x + letzte_der_reihe.b, self.BREITE)
        self.assertGreater(letzte_der_reihe.x + letzte_der_reihe.b, self.BREITE - spalten)

    def test_die_karten_stehen_zeilenweise_ohne_ueberlappung(self) -> None:
        self._setzen(9)
        m, spalten = self.raster._masse, self.raster.spalten
        for karte in self.raster.karten:
            zeile, spalte = divmod(karte.nummer, spalten)
            self.assertEqual(spalte * (karte.b + m.abstand), karte.x)
            self.assertEqual(zeile * (karte.h + m.abstand), karte.y)

    def test_jeder_eintrag_bekommt_sein_bildfeld_und_seine_karte(self) -> None:
        eintraege = self._setzen(3)
        for eintrag, karte in zip(eintraege, self.raster.karten):
            self.assertIsInstance(eintrag["_bildfeld"], raster.PosterFeld)
            self.assertIs(karte, eintrag["_kachel"])
            self.assertTrue(eintrag["_bildfeld"].winfo_exists())

    def test_der_rollbereich_umfasst_alle_zeilen(self) -> None:
        self._setzen(9)
        m, a = self.raster._masse, self.raster._auf
        zeilen = -(-9 // self.raster.spalten)
        region = [float(v) for v in str(self.raster.flaeche.cget("scrollregion")).split()]
        self.assertEqual(0, region[0])
        self.assertEqual(self.BREITE, region[2])
        self.assertEqual(max(zeilen * (a.hoehe + m.abstand), self.HOEHE), region[3])

    def test_wenige_karten_rollen_nicht(self) -> None:
        self._setzen(2)
        region = [float(v) for v in str(self.raster.flaeche.cget("scrollregion")).split()]
        self.assertGreaterEqual(region[3], self.HOEHE, "Nie kleiner als die Flaeche - sonst rollt sie ins Leere.")

    def test_eine_neue_breite_verteilt_die_karten_neu(self) -> None:
        self._setzen(9)
        vorher = self.raster.spalten
        type(self).BREITE = 700
        self.addCleanup(setattr, type(self), "BREITE", 1400)
        self.raster._nachziehen()
        self.assertLess(self.raster.spalten, vorher)
        self.assertEqual(self.raster.kartenbreite, self.raster.karten[0].b)
        zeilen = {k.y for k in self.raster.karten}
        self.assertGreater(len(zeilen), -(-9 // vorher), "Mehr Zeilen bei weniger Spalten.")

    def test_dieselbe_breite_zeichnet_nicht_neu(self) -> None:
        self._setzen(4)
        ids = [k.ids["karte"] for k in self.raster.karten]
        self.raster._nachziehen()
        self.assertEqual(ids, [k.ids["karte"] for k in self.raster.karten])

    def test_ein_aufbau_bei_unbekannter_breite_nimmt_eine_vorgabe(self) -> None:
        self._breite.stop()
        with mock.patch.object(self.raster.flaeche, "winfo_width", return_value=1):
            self._setzen(3)
        self.assertGreaterEqual(self.raster.spalten, 1)
        self._breite.start()

    def test_zwischen_der_letzten_spalte_und_dem_rollbalken_ist_eine_luecke(self) -> None:
        """03.10.2026: Die letzte Spalte klebte am Rollbalken (Nutzer: mehr Abstand, vor allem rechts)."""
        luecke = self.z.px(raster.KartenRaster.BALKEN_LUECKE)
        self.assertGreater(luecke, 0)
        links = int(str(self.raster.balken.grid_info()["padx"]).strip("()").replace(",", " ").split()[0])
        self.assertEqual(luecke, links, "Die Luecke steht links vom Balken, nicht rechts davon.")
        self.assertEqual(luecke + self.raster.balken.winfo_reqwidth(), self.raster.rechts_frei())

    def test_die_luecke_zum_rollbalken_ist_so_gross_wie_der_kartenabstand(self) -> None:
        """Beide Masse stehen an zwei Stellen - dieser Test haelt sie zusammen."""
        self.assertEqual(zeichnen.KartenMasse(faktor=self.z.faktor).abstand,
                         self.z.px(raster.KartenRaster.BALKEN_LUECKE))

    # --- Titelbild ---------------------------------------------------------------------------------
    def test_das_titelbild_hat_die_groesse_der_karte_ohne_rand(self) -> None:
        eintraege = self._setzen(2)
        with tempfile.TemporaryDirectory() as ordner:
            self.raster.bild_setzen(eintraege[0], _png(ordner, "a.png", (512, 288)))
            karte = self.raster.karten[0]
            rb = self.raster._masse.randbreite
            foto = karte.fotos["poster"]
            self.assertEqual((karte.b - 2 * rb, karte.b - 2 * rb), (foto.width(), foto.height()),
                             "Quadratisch, auch aus einem Querformat.")
            self.assertEqual("da", karte.bildzustand)

    def test_kein_titelbild_zeigt_das_zeichen_und_den_text(self) -> None:
        eintraege = self._setzen(2)
        self.raster.bild_setzen(eintraege[0], "")
        karte = self.raster.karten[0]
        self.assertEqual("leer", karte.bildzustand)
        self.assertIn("symbol", karte.ids)
        self.assertEqual("kein Titelbild", self.raster.flaeche.itemcget(karte.ids["poster_text"], "text"))

    def test_waehrend_das_bild_laedt_steht_der_platzhalter(self) -> None:
        self._setzen(1)
        karte = self.raster.karten[0]
        self.assertEqual("laedt", karte.bildzustand)
        self.assertEqual("laedt ...", self.raster.flaeche.itemcget(karte.ids["poster_text"], "text"))
        self.assertNotIn("symbol", karte.ids)

    def test_das_bild_aendert_die_geometrie_nicht(self) -> None:
        eintraege = self._setzen(4)
        vorher = [(k.x, k.y, k.b, k.h) for k in self.raster.karten]
        with tempfile.TemporaryDirectory() as ordner:
            for nummer, form in enumerate(((512, 512), (512, 288), (288, 512))):
                self.raster.bild_setzen(eintraege[nummer], _png(ordner, "b%d.png" % nummer, form))
            self.raster.bild_setzen(eintraege[3], "")
        self.assertEqual(vorher, [(k.x, k.y, k.b, k.h) for k in self.raster.karten])

    def test_eine_kaputte_bilddatei_gilt_als_kein_titelbild(self) -> None:
        eintraege = self._setzen(1)
        with tempfile.TemporaryDirectory() as ordner:
            kaputt = os.path.join(ordner, "x.png")
            Path(kaputt).write_bytes(b"das ist kein Bild")
            self.raster.bild_setzen(eintraege[0], kaputt)
        self.assertEqual("leer", self.raster.karten[0].bildzustand)

    def test_ein_bild_ueberlebt_das_neue_setzen(self) -> None:
        """Filtern und Sortieren bauen die Karten neu - das Titelbild blitzt nicht auf "laedt ..."."""
        eintraege = self._setzen(3)
        with tempfile.TemporaryDirectory() as ordner:
            datei = _png(ordner, "c.png")
            self.raster.bild_setzen(eintraege[1], datei)
            self.raster.setzen(list(reversed(eintraege)))
            karte = self.raster.karte_von(eintraege[1])
            self.assertEqual("da", karte.bildzustand)
            self.assertEqual(datei, karte.bilddatei)
            self.assertIn("poster", karte.fotos)

    def test_das_poster_feld_spricht_mit_dem_raster(self) -> None:
        eintraege = self._setzen(2)
        feld = eintraege[0]["_bildfeld"]
        feld.ohne_bild()
        self.assertEqual("leer", self.raster.karten[0].bildzustand)
        with tempfile.TemporaryDirectory() as ordner:
            feld.bild_setzen(_png(ordner, "d.png"))
            self.assertEqual("da", self.raster.karten[0].bildzustand)
        self.assertTrue(str(feld).startswith("poster:"))
        self.raster.setzen([])                   # die Karte ist weg
        self.assertFalse(feld.winfo_exists())

    # --- Treffer, Klick, Hover ---------------------------------------------------------------------------
    def test_treffer_findet_karte_und_knopf(self) -> None:
        self._setzen(9)
        karte = self.raster.karten[1]
        start = self._knopf(1, "start")
        gefunden, knopf = self.raster.treffer(start.x + 3, start.y + 3)
        self.assertIs(karte, gefunden)
        self.assertEqual("start", knopf.spec.name)
        gefunden, knopf = self.raster.treffer(karte.x + 3, karte.y + 3)
        self.assertIs(karte, gefunden)
        self.assertIsNone(knopf, "Auf dem Titelbild ist kein Knopf.")

    def test_zwischen_den_karten_ist_nichts(self) -> None:
        self._setzen(9)
        k0, k1 = self.raster.karten[0], self.raster.karten[1]
        self.assertEqual((None, None), self.raster.treffer(k0.x + k0.b + 3, k0.y + 40))
        self.assertEqual((None, None), self.raster.treffer(k1.x + 10, k1.y - 3), "Auch nicht ueber der ersten Reihe.")
        self.assertEqual((None, None), self.raster.treffer(-5, 5))

    def test_jeder_knopf_loest_seine_aktion_aus(self) -> None:
        eintraege = self._setzen(4)
        for name in ("info", "start", "kopieren", "konvertieren"):
            knopf = self._knopf(2, name)
            self.raster.klick(knopf.x + 4, knopf.y + 4)
        self.assertEqual([("aktion", n, eintraege[2]["path"]) for n in ("info", "start", "kopieren", "konvertieren")],
                         self.ereignisse)

    def test_ein_klick_auf_die_karte_waehlt_sie_und_loest_keinen_knopf_aus(self) -> None:
        eintraege = self._setzen(4)
        karte = self.raster.karten[3]
        self.raster.klick(karte.x + 10, karte.y + 10)
        self.assertEqual([("auswahl", eintraege[3]["path"])], self.ereignisse)

    def test_ein_gesperrter_knopf_meldet_nur_dass_er_gesperrt_ist(self) -> None:
        eintraege = self._setzen(3)
        self.sperren.add((eintraege[1]["path"], "kopieren"))
        self.raster.aktualisieren(eintraege[1])
        knopf = self._knopf(1, "kopieren")
        self.assertFalse(knopf.spec.aktiv)
        self.assertEqual("gesperrt", knopf.zustand)
        self.raster.klick(knopf.x + 4, knopf.y + 4)
        self.assertEqual([("gesperrt", "kopieren", eintraege[1]["path"])], self.ereignisse)

    def test_druecken_und_woanders_loslassen_loest_nichts_aus(self) -> None:
        self._setzen(3)
        knopf = self._knopf(0, "start")
        self.raster._druecken_bei(knopf.x + 4, knopf.y + 4)
        self.assertEqual("gedrueckt", knopf.zustand)
        self.raster._loslassen_bei(knopf.x + 4, knopf.y - 60)
        self.assertEqual([], self.ereignisse)
        self.assertEqual("normal", knopf.zustand)

    def test_der_doppelklick_startet_nur_auf_der_karte(self) -> None:
        eintraege = self._setzen(3)
        karte = self.raster.karten[0]
        start = self._knopf(0, "start")
        self.raster.flaeche.canvasx = lambda x: x      # keine Rollung
        self.raster.flaeche.canvasy = lambda y: y
        self.raster._doppelt(_ereignis(karte.x + 10, karte.y + 10))
        self.raster._doppelt(_ereignis(start.x + 4, start.y + 4))
        self.assertEqual([("start", eintraege[0]["path"])], self.ereignisse)

    def test_hover_faerbt_den_knopf_und_stellt_ihn_zurueck(self) -> None:
        self._setzen(3)
        self.raster.flaeche.canvasx = lambda x: x
        self.raster.flaeche.canvasy = lambda y: y
        knopf = self._knopf(0, "start")
        self.raster._bewegt(_ereignis(knopf.x + 4, knopf.y + 4))
        self.assertEqual("hover", knopf.zustand)
        self.assertEqual("hand2", str(self.raster.flaeche.cget("cursor")))
        andere = self._knopf(0, "kopieren")
        self.raster._bewegt(_ereignis(andere.x + 4, andere.y + 4))
        self.assertEqual("normal", knopf.zustand)
        self.assertEqual("hover", andere.zustand)
        self.raster._verlassen()
        self.assertEqual("normal", andere.zustand)

    def test_ein_gesperrter_knopf_hat_keinen_hover_und_keine_hand(self) -> None:
        eintraege = self._setzen(2)
        self.sperren.add((eintraege[0]["path"], "konvertieren"))
        self.raster.aktualisieren(eintraege[0])
        self.raster.flaeche.canvasx = lambda x: x
        self.raster.flaeche.canvasy = lambda y: y
        knopf = self._knopf(0, "konvertieren")
        self.raster._bewegt(_ereignis(knopf.x + 4, knopf.y + 4))
        self.assertEqual("gesperrt", knopf.zustand)
        self.assertEqual("arrow", str(self.raster.flaeche.cget("cursor")))

    def test_ueber_dem_nichts_ist_der_zeiger_ein_pfeil(self) -> None:
        self._setzen(2)
        self.raster.flaeche.canvasx = lambda x: x
        self.raster.flaeche.canvasy = lambda y: y
        self.raster._bewegt(_ereignis(self.BREITE - 2, self.HOEHE - 2))
        self.assertEqual("arrow", str(self.raster.flaeche.cget("cursor")))

    # --- Auswahl, Chips, Farben ----------------------------------------------------------------------------
    def test_die_auswahl_verschiebt_nichts(self) -> None:
        eintraege = self._setzen(6)
        vorher = [(k.x, k.y, k.b, k.h) for k in self.raster.karten]
        alt = self.raster.karten[2].fotos["karte"]
        self.raster.markieren(eintraege[2]["path"])
        self.assertEqual(vorher, [(k.x, k.y, k.b, k.h) for k in self.raster.karten])
        gewaehlt = self.raster.karten[2].fotos["karte"]
        self.assertIsNot(alt, gewaehlt)
        self.assertEqual((alt.width(), alt.height()), (gewaehlt.width(), gewaehlt.height()),
                         "Ein anderer Ring, dieselbe Groesse.")
        self.assertEqual(self.palette()["fg_accent"],
                         self.raster.flaeche.itemcget(self.raster.karten[2].ids["titel"], "fill"))
        self.assertEqual(self.palette()["fg_primary"],
                         self.raster.flaeche.itemcget(self.raster.karten[3].ids["titel"], "fill"))
        self.raster.markieren("")
        self.assertEqual(self.palette()["fg_primary"],
                         self.raster.flaeche.itemcget(self.raster.karten[2].ids["titel"], "fill"))

    def test_die_gewaehlte_karte_bleibt_beim_neu_setzen_gewaehlt(self) -> None:
        self._setzen(4, gewaehlt="/data/homebrew/spiel01")
        self.assertEqual(self.palette()["fg_accent"],
                         self.raster.flaeche.itemcget(self.raster.karten[1].ids["titel"], "fill"))

    def test_chips_kommen_nach_ohne_dass_etwas_springt(self) -> None:
        eintraege = self._setzen(3)
        vorher = [(k.x, k.y, k.b, k.h) for k in self.raster.karten]
        knoepfe_vorher = [(k.x, k.y, k.b, k.h) for k in self.raster.karten[0].knoepfe]
        anzahl = len(self.raster.karten[0].chip_ids)
        self.chips[eintraege[0]["path"]] = [("Dump-Ordner", "neutral"), ("AMPR EMU", "ampr"),
                                            ("PlayGo", "playgo"), ("BACKPORT (12.00)", "backport")]
        self.raster.aktualisieren(eintraege[0])
        self.assertGreater(len(self.raster.karten[0].chip_ids), anzahl)
        self.assertEqual(vorher, [(k.x, k.y, k.b, k.h) for k in self.raster.karten])
        self.assertEqual(knoepfe_vorher, [(k.x, k.y, k.b, k.h) for k in self.raster.karten[0].knoepfe],
                         "Die Knoepfe bleiben, wo sie sind - zwei Chipzeilen sind reserviert.")

    def test_die_chips_brechen_um_und_bleiben_in_der_karte(self) -> None:
        eintraege = self._setzen(2)
        self.chips[eintraege[0]["path"]] = [("Dump-Ordner", "neutral"), ("AMPR EMU", "ampr"),
                                            ("PlayGo", "playgo"), ("BACKPORT (12.00)", "backport"),
                                            ("Asset-Pack", "assetpack"), ("Noch einer", "neutral")]
        self.raster.aktualisieren(eintraege[0])
        karte, a = self.raster.karten[0], self.raster._auf
        bilder = [i for i in karte.chip_ids if self.raster.flaeche.type(i) == "image"]
        zeilen_y = sorted({int(self.raster.flaeche.coords(i)[1]) for i in bilder})
        self.assertLessEqual(len(zeilen_y), self.raster._masse.chip_zeilen)
        for i in bilder:
            x, y = self.raster.flaeche.coords(i)
            self.assertGreaterEqual(x, karte.x + a.innen_x)
            self.assertLessEqual(y + self.raster._masse.chip_zeile, karte.y + a.chips_y + a.chips_hoehe + 1)

    def test_ein_zu_langer_knopftext_endet_auf_punkte_statt_herauszuragen(self) -> None:
        """Text auf einer Zeichenflaeche wird nie abgeschnitten - er ragte sonst aus dem Knopf."""
        c, z = self.raster.flaeche, self.z
        schmal = raster.knopf_zeichnen(c, z, raster.KnopfSpec("k", "Konvertieren", "flaeche", True), 10, 10, 60, 30)
        text = c.itemcget(schmal.text, "text")
        self.assertTrue(text.endswith("…"), text)
        self.assertLessEqual(z.messen("knopf", text), 60 - 2 * z.px(8))
        breit = raster.knopf_zeichnen(c, z, raster.KnopfSpec("k", "Konvertieren", "flaeche", True), 10, 60, 400, 30)
        self.assertEqual("Konvertieren", c.itemcget(breit.text, "text"), "Was passt, bleibt unveraendert.")
        info = raster.knopf_zeichnen(c, z, raster.KnopfSpec("info", "Infos & Metadaten", "auswahl", True,
                                                            chevron=True), 10, 100, 120, 30)
        text = c.itemcget(info.text, "text")
        self.assertTrue(text.endswith("…"), text)
        self.assertLessEqual(z.messen("knopf", text), 120 - z.px(44), "Der Pfeil rechts bleibt frei.")

    def test_ein_chip_der_allein_breiter_ist_als_die_karte_wird_gekuerzt(self) -> None:
        eintraege = self._setzen(1)
        self.chips[eintraege[0]["path"]] = [("Ein Chip mit einem unmoeglich langen Text, der nie in die Karte passt",
                                             "neutral")]
        self.raster.aktualisieren(eintraege[0])
        karte, a = self.raster.karten[0], self.raster._auf
        texte = [self.raster.flaeche.itemcget(i, "text") for i in karte.chip_ids
                 if self.raster.flaeche.type(i) == "text"]
        self.assertEqual(1, len(texte))
        self.assertTrue(texte[0].endswith("…"), texte[0])
        self.assertLessEqual(self.z.messen("chip", texte[0]), a.innen_breite - 2 * self.z.px(10))

    def test_aktualisieren_zeichnet_die_knopfzustaende_neu(self) -> None:
        eintraege = self._setzen(2)
        knopf = self._knopf(0, "kopieren")
        self.assertTrue(knopf.spec.aktiv)
        self.sperren.add((eintraege[0]["path"], "kopieren"))
        self.raster.aktualisieren(eintraege[0])
        self.assertFalse(self._knopf(0, "kopieren").spec.aktiv)
        self.sperren.clear()
        self.raster.aktualisieren(eintraege[0])
        self.assertTrue(self._knopf(0, "kopieren").spec.aktiv)

    def test_aktualisieren_einer_unbekannten_karte_tut_nichts(self) -> None:
        self._setzen(1)
        self.raster.aktualisieren(_eintrag(99))

    def test_lange_titel_brechen_auf_zwei_zeilen_um_und_enden_auf_punkte(self) -> None:
        eintraege = [_eintrag(0, "Hogwarts Legacy mit einem sehr langen Titelnamen zum Umbruch in der Karte"),
                     _eintrag(1, "Tetris")]
        self.raster.setzen(eintraege)
        lang = self.raster.flaeche.itemcget(self.raster.karten[0].ids["titel"], "text")
        kurz = self.raster.flaeche.itemcget(self.raster.karten[1].ids["titel"], "text")
        self.assertEqual(2, len(lang.split("\n")))
        self.assertTrue(lang.endswith("…"))
        self.assertEqual("Tetris", kurz)
        a = self.raster._auf
        for zeile in lang.split("\n"):
            self.assertLessEqual(self.z.messen("titel", zeile), a.innen_breite)

    def test_die_plakette_zeigt_die_plattform(self) -> None:
        self._setzen(1)
        karte = self.raster.karten[0]
        self.assertEqual("PS5", self.raster.flaeche.itemcget(karte.ids["plakette_text"], "text"))

    def test_ohne_plattform_keine_plakette(self) -> None:
        raster2 = raster.KartenRaster(
            self.z, self.eltern, inhalt=lambda e: dict(self._inhalt(e), plattform=""),
            aktion=lambda *a: None, bei_auswahl=lambda e: None, bei_start=lambda e: None)
        with mock.patch.object(raster2.flaeche, "winfo_width", return_value=900):
            raster2.setzen([_eintrag(0)])
        self.assertNotIn("plakette", raster2.karten[0].ids)

    def test_der_designwechsel_malt_alles_in_den_neuen_farben(self) -> None:
        self._setzen(3)
        alt = self.raster.karten[0].fotos["karte"]
        self.palette.setzen("hell")
        self.raster.farben_neu()
        self.assertIsNot(alt, self.raster.karten[0].fotos["karte"])
        self.assertEqual(self.palette()["bg_main"], str(self.raster.flaeche.cget("bg")))
        self.assertEqual(self.palette()["fg_primary"],
                         self.raster.flaeche.itemcget(self.raster.karten[0].ids["titel"], "fill"))
        self.assertEqual(3, len(self.raster.karten))

    def test_ohne_neu_zeichnen_wechselt_nur_der_grund(self) -> None:
        self._setzen(2)
        ids = [k.ids["karte"] for k in self.raster.karten]
        self.palette.setzen("hell")
        self.raster.farben_neu(neu_zeichnen=False)
        self.assertEqual(ids, [k.ids["karte"] for k in self.raster.karten])
        self.assertEqual(self.palette()["bg_main"], str(self.raster.flaeche.cget("bg")))

    def test_die_lage_des_infoknopfs_fuer_das_infofenster(self) -> None:
        eintraege = self._setzen(3)
        lage = self.raster.knopf_lage(eintraege[1], "info")
        info = self._knopf(1, "info")
        self.assertEqual((info.b, info.h), lage[2:])
        self.assertEqual(self.raster.flaeche.winfo_rootx() + info.x, lage[0])
        self.assertIsNone(self.raster.knopf_lage(eintraege[1], "gibt_es_nicht"))
        self.assertIsNone(self.raster.knopf_lage(_eintrag(99), "info"))

    def test_sichtbar_machen_rollt_zur_karte(self) -> None:
        eintraege = self._setzen(30)
        letzte = eintraege[-1]
        self.raster.sichtbar_machen(letzte)
        _WURZEL.update_idletasks()
        karte = self.raster.karte_von(letzte)
        oben = self.raster.flaeche.canvasy(0)
        self.assertGreater(oben, 0)
        self.assertLessEqual(oben, karte.y)

    def test_das_mausrad_rollt_mit_der_vorgegebenen_regel(self) -> None:
        self._setzen(30)
        with mock.patch.object(self.raster.flaeche, "yview_scroll") as rollen:
            self.raster._mausrad(types.SimpleNamespace(delta=-120))
        rollen.assert_called_once_with(3, "units")
        self.assertEqual(-3, raster._rad_einheiten_vorgabe(types.SimpleNamespace(delta=120)))
        self.assertEqual(0, raster._rad_einheiten_vorgabe(types.SimpleNamespace(delta=0)))
        self.assertEqual(3, raster._rad_einheiten_vorgabe(types.SimpleNamespace(delta=-1)),
                         "Auch kleine Werte (macOS, Touchpad) rollen.")

    # --- Titelbilder nur in der Naehe des sichtbaren Bereichs ------------------------------------------------
    def _bilder(self, anzahl: int, ordner: str) -> list[dict]:
        """``anzahl`` Titel, jeder mit eigenem Titelbild (eigene Datei, eigene Farbe)."""
        eintraege = self._setzen(anzahl)
        for nummer, eintrag in enumerate(eintraege):
            self.raster.bild_setzen(eintrag, _png(ordner, "t%02d.png" % nummer, farbe=(nummer * 6, 90, 140)))
        return eintraege

    def _rollen_auf(self, oben: float) -> None:
        """Tut, als stuende der sichtbare Bereich bei ``oben`` - die Flaeche ist im Test nicht abgebildet."""
        patch = mock.patch.object(self.raster.flaeche, "canvasy", side_effect=lambda y=0: oben + y)
        patch.start()
        self.addCleanup(patch.stop)

    def test_nur_titelbilder_nahe_am_sichtbaren_bereich_werden_gebaut(self) -> None:
        """Bei Hunderten von Titeln waere alles zu bauen langsam und frisst je Karte 0,4 MB."""
        with tempfile.TemporaryDirectory() as ordner:
            self._bilder(40, ordner)
            karten = self.raster.karten
            gebaut = [k for k in karten if k.poster_da]
            self.assertTrue(karten[0].poster_da)
            self.assertFalse(karten[-1].poster_da)
            self.assertTrue(0 < len(gebaut) < 40, "Einige, nicht alle: %d von 40." % len(gebaut))
            self.assertEqual(len(gebaut), len(self.z._poster), "Nur gebaute Titelbilder liegen im Bildspeicher.")
            for karte in karten:
                self.assertEqual("da", karte.bildzustand, "Auch ein fernes Bild ist da - nur noch nicht gebaut.")
            fern = karten[-1]
            self.assertIn("poster", fern.ids)
            self.assertNotIn("poster_text", fern.ids, "Kein 'laedt ...' fuer ein Bild, das nur wartet.")

    def test_rollen_baut_die_naechsten_titelbilder_und_gibt_ferne_frei(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            self._bilder(40, ordner)
            karten = self.raster.karten
            ende = karten[-1]
            self._rollen_auf(ende.y + ende.h - self.HOEHE)                      # ganz unten
            self.raster._rollt("0.9", "1.0")
            self.assertEqual((0.9, 1.0), tuple(self.raster.balken.get()), "Der Rollbalken folgt weiter.")
            self.assertTrue(ende.poster_da)
            self.assertFalse(karten[0].poster_da, "Ganz oben ist weit weg: freigegeben.")
            self.assertEqual("da", karten[0].bildzustand)
            self.assertNotIn("poster_text", karten[0].ids)
            self._rollen_auf(0)
            self.raster._rollt("0.0", "0.1")
            self.assertTrue(karten[0].poster_da)
            self.assertFalse(ende.poster_da)

    def test_ein_kleines_hin_und_herrollen_baut_nichts_neu(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            self._bilder(40, ordner)
            karte = self.raster.karten[0]
            foto = karte.fotos["poster"]
            self._rollen_auf(2 * karte.h)                      # zwei Kartenhoehen weiter: noch nahe genug
            self.raster._posters_nachziehen()
            self.assertTrue(karte.poster_da)
            self.assertIs(foto, karte.fotos["poster"], "Nicht neu gebaut.")

    def test_ein_bild_fuer_eine_ferne_karte_wird_erst_beim_heranrollen_gebaut(self) -> None:
        eintraege = self._setzen(40)
        fern = self.raster.karten[-1]
        with tempfile.TemporaryDirectory() as ordner:
            datei = _png(ordner, "t.png")
            self.raster.bild_setzen(eintraege[-1], datei)
            self.assertEqual(("da", False, datei), (fern.bildzustand, fern.poster_da, fern.bilddatei))
            self.assertEqual(0, len(self.z._poster), "Nichts gebaut, nichts im Bildspeicher.")
            self._rollen_auf(fern.y)
            self.raster._rollt("0.8", "1.0")
            self.assertTrue(fern.poster_da)
            self.assertEqual(1, len(self.z._poster))

    def test_ohne_gemessene_hoehe_gilt_alles_als_sichtbar(self) -> None:
        self._hoehe.stop()
        try:
            with mock.patch.object(self.raster.flaeche, "winfo_height", return_value=1), \
                    tempfile.TemporaryDirectory() as ordner:
                self._bilder(40, ordner)
                self.assertTrue(all(k.poster_da for k in self.raster.karten),
                                "Eine Seite, die noch nicht abgebildet ist, hat keinen 'sichtbaren Bereich'.")
        finally:
            self._hoehe.start()

    def test_nur_geladene_bilder_werden_nachgezogen(self) -> None:
        eintraege = self._setzen(40)
        self.raster.bild_setzen(eintraege[1], "")              # kein Titelbild
        ende = self.raster.karten[-1]
        self._rollen_auf(ende.y)
        self.raster._rollt("0.8", "1.0")
        self.assertFalse(ende.poster_da)
        self.assertEqual("laedt", ende.bildzustand)
        self.assertEqual("laedt ...", self.raster.flaeche.itemcget(ende.ids["poster_text"], "text"))
        self.assertEqual("leer", self.raster.karten[1].bildzustand)

    def test_eine_rollung_fragt_die_flaeche_nur_einmal(self) -> None:
        """Zwei Tk-Aufrufe je Rollung statt zwei je Karte - bei Hunderten von Karten waeren es Tausende."""
        with tempfile.TemporaryDirectory() as ordner:
            self._bilder(40, ordner)
            flaeche = self.raster.flaeche
            fragen: list = []
            hoehe, oben = flaeche.winfo_height, flaeche.canvasy
            flaeche.winfo_height = lambda: fragen.append("hoehe") or hoehe()
            flaeche.canvasy = lambda y=0: fragen.append("oben") or oben(y)
            self.raster._posters_nachziehen()
            self.assertEqual(["hoehe", "oben"], fragen)
            fragen.clear()
            self.raster._zeichnen_alles(self.BREITE)
            viele = list(fragen)                               # (der Rollbereich fragt die Hoehe selbst noch einmal)
            self.assertEqual(1, viele.count("oben"), "Auch ein ganzer Neuaufbau fragt den Stand nur einmal.")
            fragen.clear()
            self.raster.karten = self.raster.karten[:4]
            self.raster._zeichnen_alles(self.BREITE)
            self.assertEqual(viele, fragen, "Die Zahl der Fragen haengt nicht an der Zahl der Karten.")

    def test_ein_neues_setzen_liest_nichts_noch_einmal_von_der_platte(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            eintraege = self._bilder(40, ordner)
            gebaut = len(self.z._poster)
            self.assertLess(gebaut, 40)
            with mock.patch.object(raster.Image, "open") as lesen:
                self.raster.setzen(eintraege)
                self.raster._nachziehen()
            lesen.assert_not_called()                          # von aussen: ein except im Programm schluckte sonst den Fehler
            self.assertEqual(gebaut, len(self.z._poster))
            self.assertTrue(all(k.poster_da for k in self.raster.karten[:self.raster.spalten]))

    def test_ein_hoeheres_fenster_baut_die_nun_sichtbaren_titelbilder(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            self._bilder(40, ordner)
            ende = self.raster.karten[-1]
            self.assertFalse(ende.poster_da)
            type(self).HOEHE = ende.y + ende.h
            self.addCleanup(setattr, type(self), "HOEHE", 900)
            self.raster._nachziehen()                          # dieselbe Breite: nur der Bereich wird nachgezogen
            self.assertTrue(ende.poster_da)

    # --- Groessenaenderung: erst zeichnen, wenn das Ziehen ruht -------------------------------------------
    def test_viele_groessenmeldungen_ergeben_eine_neuzeichnung(self) -> None:
        """Tk meldet beim Ziehen der Fensterkante jeden Pixel; jedes Mal alles neu zu zeichnen ruckelt."""
        zaehler = iter(range(1, 100))
        geplant: list = []
        abgebrochen: list = []
        with mock.patch.object(self.raster.rahmen, "after",
                               side_effect=lambda ms, fn: geplant.append((ms, fn)) or "nach%d" % next(zaehler)), \
                mock.patch.object(self.raster.rahmen, "after_cancel", side_effect=abgebrochen.append):
            for _ in range(5):
                self.raster._groesse_geaendert(None)
        self.assertEqual(5, len(geplant))
        self.assertEqual(["nach1", "nach2", "nach3", "nach4"], abgebrochen, "Jede neue Meldung ersetzt die vorige.")
        self.assertEqual("nach5", self.raster._nach)
        self.assertEqual({raster.KartenRaster.RUHE_MS}, {ms for ms, _fn in geplant})

    def test_ein_langes_ziehen_wartet_hoechstens_die_laengste_zeit(self) -> None:
        self.raster._nach = "ausstehend"
        self.raster._nach_seit = time.monotonic() - raster.KartenRaster.LAENGSTE_WARTEZEIT - 0.1
        with mock.patch.object(self.raster.rahmen, "after") as neu, \
                mock.patch.object(self.raster.rahmen, "after_cancel") as ab:
            self.raster._groesse_geaendert(None)
        neu.assert_not_called()
        ab.assert_not_called()
        self.assertEqual("ausstehend", self.raster._nach, "Das Anstehende laeuft gleich - nicht noch einmal verschieben.")

    def test_nach_dem_zeichnen_steht_nichts_mehr_aus(self) -> None:
        self._setzen(3)
        self.raster._nach = "x"
        self.raster._nachziehen()
        self.assertIsNone(self.raster._nach)

    # --- Findings des Gegenlesens (03.10.2026) ---------------------------------------------------------------
    def test_der_zeiger_wird_nur_bei_aenderung_gesetzt(self) -> None:
        """Jedes ``configure`` der Flaeche malt sie neu und meldet die Rollbalken - bei jeder Mausbewegung ein Dauerfeuer."""
        self._setzen(3)
        c = self.raster.flaeche
        c.canvasx = lambda x: x
        c.canvasy = lambda y: y
        aufrufe: list = []
        echt = c.configure
        c.configure = lambda *a, **k: (aufrufe.append(k) if "cursor" in k else None) or echt(*a, **k)
        knopf = self._knopf(0, "start")
        for dx in (4, 6, 8):
            self.raster._bewegt(_ereignis(knopf.x + dx, knopf.y + 4))
        self.assertEqual([{"cursor": "hand2"}], aufrufe, "Dreimal derselbe Knopf: ein einziges Mal gesetzt.")
        self.raster._bewegt(_ereignis(self.BREITE - 2, self.HOEHE - 2))
        self.assertEqual([{"cursor": "hand2"}, {"cursor": "arrow"}], aufrufe, "Bei einem anderen Zeiger wird gesetzt.")

    def test_gesperrt_meldet_nur_ein_klick_der_auf_dem_knopf_beginnt(self) -> None:
        eintraege = self._setzen(3)
        self.sperren.add((eintraege[0]["path"], "konvertieren"))
        self.raster.aktualisieren(eintraege[0])
        knopf, karte = self._knopf(0, "konvertieren"), self.raster.karten[0]
        self.raster._druecken_bei(karte.x + 10, karte.y + 10)            # Druck auf dem Titelbild ...
        self.raster._loslassen_bei(knopf.x + 4, knopf.y + 4)             # ... Loslassen auf dem gesperrten Knopf
        self.assertNotIn("gesperrt", [e[0] for e in self.ereignisse], "Ein Ziehen von woanders ist kein Klick darauf.")
        self.ereignisse.clear()
        self.raster.klick(knopf.x + 4, knopf.y + 4)
        self.assertEqual([("gesperrt", "konvertieren", eintraege[0]["path"])], self.ereignisse)

    def test_ein_druck_ueberlebt_das_neuzeichnen_der_knoepfe(self) -> None:
        """Eine Einbaupruefung meldet sich oft genau dann, wenn jemand klickt - der Klick ging verloren."""
        eintraege = self._setzen(3)
        alt = self._knopf(0, "start")
        self.raster._druecken_bei(alt.x + 4, alt.y + 4)
        self.assertEqual("gedrueckt", alt.zustand)
        self.chips[eintraege[0]["path"]] = [("Dump-Ordner", "neutral"), ("AMPR EMU", "ampr")]
        self.raster.aktualisieren(eintraege[0])
        neu = self._knopf(0, "start")
        self.assertIsNot(alt, neu, "Die Knoepfe sind neu gezeichnet worden.")
        self.assertEqual("gedrueckt", neu.zustand)
        self.raster._loslassen_bei(neu.x + 4, neu.y + 4)
        self.assertEqual([("aktion", "start", eintraege[0]["path"])], self.ereignisse)

    def test_der_hover_ueberlebt_das_neuzeichnen_der_knoepfe(self) -> None:
        eintraege = self._setzen(3)
        c = self.raster.flaeche
        c.canvasx = lambda x: x
        c.canvasy = lambda y: y
        alt = self._knopf(0, "kopieren")
        self.raster._bewegt(_ereignis(alt.x + 4, alt.y + 4))
        self.assertEqual("hover", alt.zustand)
        self.raster.aktualisieren(eintraege[0])
        neu = self._knopf(0, "kopieren")
        self.assertEqual("hover", neu.zustand, "Der Zeiger steht noch darauf - der Hover-Ton bleibt.")
        self.assertIs(neu, self.raster._hover[1])

    def test_ein_knopf_der_zwischen_druck_und_loslassen_gesperrt_wird_loest_nichts_aus(self) -> None:
        eintraege = self._setzen(3)
        alt = self._knopf(0, "kopieren")
        self.raster._druecken_bei(alt.x + 4, alt.y + 4)
        self.sperren.add((eintraege[0]["path"], "kopieren"))
        self.raster.aktualisieren(eintraege[0])
        neu = self._knopf(0, "kopieren")
        self.assertFalse(neu.spec.aktiv)
        self.assertIsNone(self.raster._druck, "Der Druck gilt dem alten, freien Knopf - der neue ist gesperrt.")
        self.raster._loslassen_bei(neu.x + 4, neu.y + 4)
        self.assertEqual([], self.ereignisse, "Weder die Aktion noch die Meldung: Gedrueckt war er noch frei.")

    def test_zu_viele_chips_werden_als_plus_n_angedeutet(self) -> None:
        """Mehr Marken als zwei Zeilen fassen verschwanden still (Asset-Pack, BACKPORT, ...)."""
        eintraege = self._setzen(2)
        namen = ["Dump-Ordner", "AMPR EMU", "PlayGo", "BACKPORT (12.00)", "Asset-Pack", "Noch einer",
                 "Und noch einer", "Letzter"]
        pfad = eintraege[0]["path"]
        c = self.raster.flaeche

        def _texte() -> list:
            return [c.itemcget(i, "text") for i in self.raster.karten[0].chip_ids if c.type(i) == "text"]

        self.chips[pfad] = [(n, "neutral") for n in namen]
        self.raster.aktualisieren(eintraege[0])
        texte = _texte()
        self.assertTrue(texte[-1].startswith("+"), texte)
        gezeigt = texte[:-1]
        self.assertEqual(namen[:len(gezeigt)], gezeigt, "Die ersten, in ihrer Reihenfolge.")
        self.assertEqual(len(namen) - len(gezeigt), int(texte[-1][1:]), "Das \"+N\" zaehlt genau die fehlenden.")
        self.chips[pfad] = [("Dump-Ordner", "neutral")]
        self.raster.aktualisieren(eintraege[0])
        self.assertEqual(["Dump-Ordner"], _texte(), "Passt alles, steht kein \"+N\" da.")

    def test_ein_zerstoertes_raster_wirft_nichts(self) -> None:
        eintraege = self._setzen(2)
        self.raster.rahmen.destroy()
        self.assertFalse(self.raster.lebt())
        self.raster.bild_setzen(eintraege[0], "")
        self.raster.aktualisieren(eintraege[0])
        self.raster.markieren("x")
        self.assertEqual(0, self.raster.setzen(eintraege), "Ein spaeter Suchlauf nach dem Schliessen wirft nichts.")


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SuchlaufAnzeigeTests(unittest.TestCase):
    """Das Fortschrittsfenster des Suchlaufs (03.10.2026): erscheint erst bei langer Dauer, zeigt Balken und Prozent."""

    TEXTE = {"action.cancel": "ABBRECHEN", "library.scan_hinweis": "Das kann dauern.",
             "library.scan_zaehlung": "{getan} von {gesamt}",
             "s.ordner": "Ordner durchsuchen", "s.angaben": "Angaben lesen", "s.bilder": "Titelbilder laden"}
    STUFEN = {"ordner": "s.ordner", "angaben": "s.angaben", "bilder": "s.bilder"}

    def setUp(self) -> None:
        self.z, _p = _zeichner()
        self.seite = tk.Frame(_WURZEL)
        self.addCleanup(self.seite.destroy)
        self.fenster: list = []
        self.abgebrochen: list[bool] = []
        self.anzeige: raster.SuchlaufAnzeige | None = None

    def _bauen(self):
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.fenster.append(fenster)
        self.addCleanup(lambda f=fenster: f.winfo_exists() and f.destroy())
        return fenster

    def _anzeige(self, verzoegerung_ms: int = 0, nur_sichtbar: bool = False):
        from ps5_validator.utils import bibliothek_fortschritt as fs
        text = lambda schluessel, **werte: self.TEXTE[schluessel].format(**werte)       # noqa: E731
        # nur_sichtbar=False: Die Test-Wurzel ist verborgen, die Seite also nie "zu sehen".
        anzeige = raster.SuchlaufAnzeige(
            self.seite, self.z, fs.Phasen([("ordner", 10), ("angaben", 40), ("bilder", 50)]),
            bauen=self._bauen, text=text, abbrechen=lambda: self.abgebrochen.append(True),
            stufen=self.STUFEN, verzoegerung_ms=verzoegerung_ms, drossel=fs.Drossel(0.0),
            nur_sichtbar=nur_sichtbar)
        self.anzeige = anzeige
        self.addCleanup(anzeige.beenden)
        return anzeige

    def _texte(self) -> dict[str, str]:
        return {name: str(label.cget("text")) for name, label in self.anzeige._labels.items()}

    def _laufen(self) -> None:
        for _ in range(3):
            _WURZEL.update()

    def test_ohne_verzoegerung_erscheint_das_fenster_sofort(self) -> None:
        anzeige = self._anzeige(0)
        self._laufen()
        self.assertTrue(anzeige.offen)
        self.assertEqual(1, len(self.fenster))

    def test_ein_kurzer_suchlauf_laesst_kein_fenster_aufblitzen(self) -> None:
        """Wer binnen der Verzoegerung fertig wird, zeigt gar nichts."""
        anzeige = self._anzeige(60000)
        anzeige.melden("angaben", 1, 3, "x")
        anzeige.beenden()
        self._laufen()
        self.assertEqual([], self.fenster, "Das Fenster wurde gebaut, obwohl der Lauf kurz war.")
        self.assertFalse(anzeige.offen)

    def test_die_verzoegerung_wird_abgewartet(self) -> None:
        anzeige = self._anzeige(250)
        self._laufen()
        self.assertFalse(anzeige.offen, "Nach 0 ms darf noch nichts da sein.")
        zeit = time.monotonic() + 3
        while not anzeige.offen and time.monotonic() < zeit:
            _WURZEL.update()
            time.sleep(0.02)
        self.assertTrue(anzeige.offen, "Nach der Verzoegerung muss das Fenster da sein.")

    def test_balken_und_prozent_folgen_den_meldungen(self) -> None:
        anzeige = self._anzeige(0)
        anzeige.melden("angaben", 5, 10, "Dirt 5")
        self._laufen()
        stand = self._texte()
        self.assertEqual("Angaben lesen", stand["stufe"])
        self.assertEqual("5 von 10   ·   Dirt 5", stand["detail"])
        self.assertEqual("30 %", stand["prozent"])           # 10 + 40 * 0,5
        self.assertAlmostEqual(30.0, float(str(anzeige._balken.cget("value"))), places=3)
        self.assertEqual("determinate", str(anzeige._balken.cget("mode")))
        anzeige.melden("bilder", 10, 10, "")
        self._laufen()
        self.assertEqual("Titelbilder laden", self._texte()["stufe"])
        self.assertEqual("99 %", self._texte()["prozent"], "Vor dem Ende steht der Balken nie auf 100 %.")
        self.assertGreaterEqual(float(str(anzeige._balken.cget("value"))), 90.0)

    def test_eine_stufe_ohne_gesamtzahl_laeuft_als_laufbalken(self) -> None:
        anzeige = self._anzeige(0)
        anzeige.melden("ordner", None, None, "12 Spiele gefunden")
        self._laufen()
        self.assertEqual("indeterminate", str(anzeige._balken.cget("mode")))
        self.assertEqual("…", self._texte()["prozent"])
        self.assertEqual("12 Spiele gefunden", self._texte()["detail"])
        anzeige.melden("angaben", 1, 4, "")
        self._laufen()
        self.assertEqual("determinate", str(anzeige._balken.cget("mode")), "Mit bekannter Zahl wieder ein echter Balken.")

    def test_vor_der_ersten_meldung_zeigt_das_fenster_die_erste_stufe(self) -> None:
        anzeige = self._anzeige(0)
        self._laufen()
        self.assertEqual("Ordner durchsuchen", self._texte()["stufe"])
        self.assertEqual("…", self._texte()["prozent"])
        self.assertEqual("Das kann dauern.", self._texte()["hinweis"])

    def test_beenden_schliesst_das_fenster_und_spaetere_meldungen_verpuffen(self) -> None:
        anzeige = self._anzeige(0)
        self._laufen()
        fenster = self.fenster[0]
        anzeige.beenden()
        self._laufen()
        self.assertFalse(fenster.winfo_exists())
        self.assertFalse(anzeige.offen)
        anzeige.melden("angaben", 1, 2, "zu spaet")           # darf weder werfen noch ein Fenster bauen
        self._laufen()
        self.assertEqual(1, len(self.fenster))
        anzeige.beenden()                                      # mehrfach ist erlaubt

    def test_schliessen_macht_das_fenster_sofort_zu_auch_ohne_hauptschleife(self) -> None:
        """Fuer die Seite, die zugeht: ``beenden`` ginge ueber ``after`` der Seite und kaeme nie an."""
        anzeige = self._anzeige(0)
        self._laufen()
        fenster = self.fenster[0]
        self.seite.destroy()
        anzeige.schliessen()
        self.assertFalse(fenster.winfo_exists(), "Das Fenster ist ein eigenes Toplevel und blieb mit der Seite stehen.")
        self.assertTrue(anzeige.beendet)
        anzeige.schliessen()                                   # mehrfach ist erlaubt

    def test_abbrechen_verstaendigt_die_seite_einmal_und_schliesst(self) -> None:
        anzeige = self._anzeige(0)
        self._laufen()
        anzeige._abbrechen()
        anzeige._abbrechen()
        self.assertEqual([True], self.abgebrochen, "Zweimal Abbrechen darf die Seite nur einmal verstaendigen.")
        self.assertFalse(self.fenster[0].winfo_exists())
        self.assertTrue(anzeige.beendet)

    def test_das_kreuz_des_fensters_ist_ein_abbrechen(self) -> None:
        self._anzeige(0)
        self._laufen()
        befehl = self.fenster[0].protocol("WM_DELETE_WINDOW")
        self.assertTrue(befehl, "Das X des Fensters hat keinen Befehl - es schlosse wortlos und liesse die Faeden laufen.")
        self.fenster[0].tk.call(befehl)
        self.assertEqual([True], self.abgebrochen)

    @staticmethod
    def _alle(widget) -> list:
        gefunden = [widget]
        for kind in widget.winfo_children():
            gefunden.extend(SuchlaufAnzeigeTests._alle(kind))
        return gefunden

    def test_der_abbrechen_knopf_steht_im_fenster(self) -> None:
        from tkinter import ttk
        self._anzeige(0)
        self._laufen()
        knoepfe = [w for w in self._alle(self.fenster[0]) if isinstance(w, ttk.Button)]
        self.assertEqual(["ABBRECHEN"], [str(k.cget("text")) for k in knoepfe])
        knoepfe[0].invoke()
        self.assertEqual([True], self.abgebrochen)

    def test_eine_unbekannte_stufe_stoert_nicht(self) -> None:
        anzeige = self._anzeige(0)
        anzeige.melden("gibtesnicht", 1, 2, "x")
        self._laufen()
        self.assertTrue(anzeige.offen)

    def test_eine_geschlossene_seite_wirft_nichts(self) -> None:
        anzeige = self._anzeige(0)
        self.seite.destroy()
        anzeige.melden("angaben", 1, 2, "x")
        anzeige.beenden()
        self.assertTrue(anzeige.beendet)

    def test_aus_einem_faden_gemeldet_ohne_hauptschleife_wirft_nichts(self) -> None:
        """Ein Arbeitsfaden, der nach dem Programmende meldet, darf nicht abstuerzen (``after`` wirft RuntimeError)."""
        import threading
        anzeige = self._anzeige(0)
        fehler: list[BaseException] = []

        def faden() -> None:
            try:
                anzeige.melden("angaben", 1, 2, "x")
                anzeige.beenden()
            except BaseException as exc:  # noqa: BLE001
                fehler.append(exc)

        t = threading.Thread(target=faden)
        t.start()
        zeit = time.monotonic() + 3
        while t.is_alive() and time.monotonic() < zeit:
            _WURZEL.update()
            time.sleep(0.01)
        t.join(1)
        self.assertEqual([], fehler)

    def test_der_takt_schliesst_das_fenster_wenn_ein_faden_ohne_hauptschleife_beendet(self) -> None:
        """Ohne Hauptschleife kam ``beenden`` ueber ``after`` aus einem Faden nie an (03.10.2026 gemessen).

        Dann stand das Fenster fuer den Rest des Volllaufs sichtbar auf dem Schirm. Jetzt setzt der Faden nur
        das Merkmal, und der Takt im Fensterfaden schliesst.
        """
        import threading
        anzeige = self._anzeige(0)
        self._laufen()
        fenster = self.fenster[0]
        self.assertTrue(fenster.winfo_exists())
        t = threading.Thread(target=anzeige.beenden)
        t.start()
        t.join(5)
        zeit = time.monotonic() + 3
        while fenster.winfo_exists() and time.monotonic() < zeit:
            _WURZEL.update()
            time.sleep(0.02)
        self.assertFalse(fenster.winfo_exists(), "Das Fenster blieb stehen, obwohl die Anzeige beendet ist.")
        self.assertFalse(anzeige.offen)

    def test_ein_beendeter_lauf_baut_sein_fenster_nicht_mehr(self) -> None:
        """Beendet, bevor die Verzoegerung um ist (auch aus einem Faden): kein Fenster, auch nicht spaeter."""
        import threading
        anzeige = self._anzeige(150)
        t = threading.Thread(target=anzeige.beenden)
        t.start()
        t.join(5)
        zeit = time.monotonic() + 0.6
        while time.monotonic() < zeit:
            _WURZEL.update()
            time.sleep(0.02)
        self.assertEqual([], self.fenster)

    def test_meldungen_aus_einem_faden_fassen_tk_nicht_an_und_kommen_ueber_den_takt(self) -> None:
        """Ein Faden darf ohne Hauptschleife nicht warten: Frueher hing jede Meldung eine Sekunde (``after`` aus
        dem Faden wartet auf die Hauptschleife und gibt dann auf). Der Takt zeigt die letzte Meldung an."""
        import threading
        anzeige = self._anzeige(0)
        self._laufen()
        dauer: list[float] = []

        def faden() -> None:
            beginn = time.monotonic()
            for n in range(1, 6):
                anzeige.melden("angaben", n, 5, "Spiel %d" % n)
            dauer.append(time.monotonic() - beginn)

        t = threading.Thread(target=faden)
        t.start()
        t.join(10)
        self.assertLess(dauer[0], 0.5, "Meldungen aus dem Faden warten auf die Hauptschleife.")
        zeit = time.monotonic() + 2
        while "5 von 5" not in self._texte().get("detail", "") and time.monotonic() < zeit:
            _WURZEL.update()
            time.sleep(0.02)
        self.assertEqual("5 von 5   ·   Spiel 5", self._texte()["detail"])

    def test_ohne_sichtbare_seite_geht_kein_fenster_auf(self) -> None:
        """Das Fenster gehoert zur Seite: Ist sie nicht zu sehen (hier: Wurzel verborgen), bleibt es zu."""
        anzeige = self._anzeige(0, nur_sichtbar=True)
        zeit = time.monotonic() + 0.4
        while time.monotonic() < zeit:
            _WURZEL.update()
            time.sleep(0.02)
        self.assertEqual([], self.fenster)
        self.assertFalse(anzeige.offen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
