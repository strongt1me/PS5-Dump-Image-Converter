# -*- coding: utf-8 -*-
"""Die Reihe "Feld + Knoepfe" bricht um, wenn die Breite nicht reicht (Seite "Y2JB Updater").

Gefunden am 15.11.2026 beim Durchmessen aller Seiten bei 150 % und 200 % Windows-Skalierung: Die Knoepfe neben der
Klappliste wachsen mit der Skalierung, die Klappliste bekam bei 200 % auf einem 1920er Schirm 26 statt 329 Pixel.

Gesichert wird die Regel (``ps5_validator.ui.schmale_zeile``) an echten Tk-Elementen: breit = eine Reihe wie bisher,
schmal = Feld ueber der ganzen Breite und die Knoepfe darunter, und der Weg zurueck. Dazu im Quelltext, dass beide
Karten der Seite die Regel benutzen und die Schritt-Ueberschrift umbricht.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import unittest
from tkinter import ttk

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJEKT)

from ps5_validator.ui.schmale_zeile import (  # noqa: E402
    hinweise_bei_platzmangel_ausblenden,
    knoepfe_unter_liste,
    zeile_umbrechen,
)

HAUPTDATEI = os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class UmbruchTests(unittest.TestCase):

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)
        self.zeile = tk.Frame(self.top)
        self.zeile.pack(fill="x")
        self.zeile.columnconfigure(0, weight=1)
        self.feld = ttk.Combobox(self.zeile, state="readonly", width=20)
        self.feld.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.laden = tk.Button(self.zeile, text="Fassungen laden", width=12)
        self.laden.grid(row=0, column=1, padx=(0, 8))
        self.holen = tk.Button(self.zeile, text="Herunterladen", width=12)
        self.holen.grid(row=0, column=2)
        self.anordnen = zeile_umbrechen(self.zeile, self.feld, (self.laden, self.holen))

    def _breite(self, pixel: int) -> None:
        self.top.geometry("%dx120" % pixel)
        for _ in range(4):
            self.top.update()

    def _noetig(self) -> int:
        self.top.update_idletasks()
        return self.feld.winfo_reqwidth() + sum(k.winfo_reqwidth() + 8 for k in (self.laden, self.holen))

    def test_breit_bleibt_es_eine_reihe(self) -> None:
        self._breite(self._noetig() + 200)
        self.assertEqual(0, int(self.feld.grid_info()["row"]))
        self.assertEqual(1, int(self.feld.grid_info()["columnspan"]))
        for spalte, knopf in ((1, self.laden), (2, self.holen)):
            info = knopf.grid_info()
            self.assertEqual((0, spalte), (int(info["row"]), int(info["column"])))

    def test_schmal_steht_das_feld_ueber_allem_und_die_knoepfe_darunter(self) -> None:
        self._breite(self._noetig() - 100)
        info = self.feld.grid_info()
        self.assertEqual((0, 0, 3), (int(info["row"]), int(info["column"]), int(info["columnspan"])))
        i1, i2 = self.laden.grid_info(), self.holen.grid_info()
        self.assertEqual((1, 0, "w"), (int(i1["row"]), int(i1["column"]), str(i1["sticky"])))
        self.assertEqual((1, 2, "e"), (int(i2["row"]), int(i2["column"]), str(i2["sticky"])))

    def test_schmal_hat_das_feld_wieder_seine_ganze_breite(self) -> None:
        """Das war der Fehler: Das Feld wurde auf 26 Pixel zusammengedrueckt."""
        self._breite(self._noetig() - 100)
        self.assertGreaterEqual(self.feld.winfo_width(), self._noetig() - 100 - 4)
        self.assertGreaterEqual(self.feld.winfo_width(), self.feld.winfo_reqwidth() - 1)

    def test_der_weg_zurueck_stellt_die_reihe_her(self) -> None:
        self._breite(self._noetig() - 100)
        self._breite(self._noetig() + 200)
        self.assertEqual(0, int(self.laden.grid_info()["row"]))
        self.assertEqual(1, int(self.laden.grid_info()["column"]))
        self.assertEqual(2, int(self.holen.grid_info()["column"]))
        self.assertEqual(1, int(self.feld.grid_info()["columnspan"]))

    def test_vor_dem_anlegen_wird_nichts_umgestellt(self) -> None:
        """Eine Breite von 1 (noch nicht angelegt) ist kein Platzmangel."""
        roh = tk.Frame(self.top)          # nie gepackt: Breite 1
        feld = ttk.Combobox(roh)
        feld.grid(row=0, column=0)
        knopf = tk.Button(roh, text="x")
        knopf.grid(row=0, column=1)
        zeile_umbrechen(roh, feld, (knopf,))()
        self.assertEqual(0, int(knopf.grid_info()["row"]))

    def test_zerstoerte_elemente_werfen_nicht(self) -> None:
        self.zeile.destroy()
        self.anordnen()                   # darf nicht werfen


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FusszeileTests(unittest.TestCase):
    """Statuszeile links, ein Knopf rechts: schmal steht der Knopf rechtsbuendig darunter."""

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)
        self.zeile = tk.Frame(self.top)
        self.zeile.pack(fill="x")
        self.zeile.columnconfigure(0, weight=1)
        self.text = tk.Label(self.zeile, text="Noch keine Datei gewaehlt.", wraplength=40, justify="left", anchor="w")
        self.text.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.knopf = tk.Button(self.zeile, text="Auf den USB-Stick hochladen", width=24)
        self.knopf.grid(row=0, column=1)
        zeile_umbrechen(self.zeile, self.text, (self.knopf,), abstand=10, mindestbreite=170, rechts=True)

    def _breite(self, pixel: int) -> None:
        self.top.geometry("%dx120" % pixel)
        for _ in range(4):
            self.top.update()

    def test_schmal_steht_der_knopf_rechtsbuendig_unter_dem_text(self) -> None:
        self._breite(self.knopf.winfo_reqwidth() + 100)          # Text bekaeme nur ~100 px
        info = self.knopf.grid_info()
        self.assertEqual((1, 1, "e"), (int(info["row"]), int(info["column"]), str(info["sticky"])))
        self.assertEqual(2, int(self.text.grid_info()["columnspan"]))

    def test_breit_bleibt_es_eine_reihe(self) -> None:
        self._breite(self.knopf.winfo_reqwidth() + 170 + 60)
        self.assertEqual(0, int(self.knopf.grid_info()["row"]))
        self.assertEqual(1, int(self.text.grid_info()["columnspan"]))

    def test_die_mindestbreite_zaehlt_nicht_die_wunschbreite_des_umbrechenden_textes(self) -> None:
        """Ein Text mit wraplength meldet eine winzige Wunschbreite - daran darf die Entscheidung nicht haengen."""
        self.assertLess(self.text.winfo_reqwidth(), 170)
        self._breite(self.knopf.winfo_reqwidth() + 100)
        self.assertEqual(1, int(self.knopf.grid_info()["row"]))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class HinweisTests(unittest.TestCase):
    """Hinweisabsaetze gehen zuerst, wenn die Seite zu hoch wird - und kommen mit Platz zurueck."""

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)
        self.seite = tk.Frame(self.top)
        self.seite.pack(fill="both", expand=True)
        self.anker = tk.Frame(self.seite, height=100, width=200)
        self.anker.pack(fill="x")
        self.hinweis = tk.Label(self.seite, text="Erklaerung", height=5)
        self.hinweis.pack(fill="x", pady=(6, 2))
        self.unten = tk.Frame(self.seite, height=100, width=200)
        self.unten.pack(fill="x")
        self.top.geometry("300x600")
        for _ in range(4):
            self.top.update()
        self.voll = self.seite.winfo_reqheight()          # Platzbedarf mit Hinweis, vor jedem Eingriff
        self.assertGreater(self.voll, 200)
        self.pruefen = hinweise_bei_platzmangel_ausblenden(self.seite, ((self.hinweis, self.anker),))

    def _hoehe(self, pixel: int) -> None:
        self.top.geometry("300x%d" % pixel)
        for _ in range(4):
            self.top.update()
        self.pruefen()
        self.top.update()

    def test_reicht_die_hoehe_bleibt_der_hinweis(self) -> None:
        self._hoehe(self.voll + 100)
        self.assertEqual("pack", self.hinweis.winfo_manager())

    def test_reicht_sie_nicht_geht_der_hinweis(self) -> None:
        self._hoehe(self.voll - 40)
        self.assertEqual("", self.hinweis.winfo_manager())

    def test_mit_platz_kommt_er_an_seine_alte_stelle_zurueck(self) -> None:
        vorher = self.hinweis.pack_info()
        voll = self.voll
        self._hoehe(voll - 40)
        self.assertEqual("", self.hinweis.winfo_manager())
        self._hoehe(voll + 100)
        self.assertEqual("pack", self.hinweis.winfo_manager())
        nachher = self.hinweis.pack_info()
        for schluessel in ("fill", "pady", "side"):
            self.assertEqual(vorher[schluessel], nachher[schluessel], schluessel)
        # an der alten Stelle: zwischen Anker und unterem Element
        reihenfolge = [str(k) for k in self.seite.pack_slaves()]
        self.assertEqual([str(self.anker), str(self.hinweis), str(self.unten)], reihenfolge)

    def test_kein_flackern_an_der_grenze(self) -> None:
        """Knapp unter dem Bedarf: aus, und bei jeder weiteren Pruefung bleibt es aus."""
        voll = self.voll
        self._hoehe(voll - 5)
        for _ in range(5):
            self.pruefen()
            self.top.update()
        self.assertEqual("", self.hinweis.winfo_manager())


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ListeTests(unittest.TestCase):
    """Beschriftung - Liste - Knoepfe (Scan-Ordner der Bibliothek): Die Liste schrumpft nie auf einen Streifen."""

    MINDEST = 160

    def setUp(self) -> None:
        self.top = tk.Toplevel(_WURZEL)
        self.top.attributes("-alpha", 0.0)
        self.addCleanup(self.top.destroy)
        self.zeile = tk.Frame(self.top)
        self.zeile.pack(fill="x")
        self.titel = tk.Label(self.zeile, text="SCAN-ORDNER")
        self.titel.pack(side="left", anchor="n", padx=(0, 8))
        self.karte = tk.Frame(self.zeile, bg="gray")
        self.karte.pack(side="left", fill="x", expand=True)
        tk.Listbox(self.karte, height=2, width=10).pack(fill="x", expand=True)
        self.knoepfe = tk.Frame(self.zeile)
        self.knoepfe.pack(side="right", padx=(8, 0), before=self.karte)
        for text in ("Ordner hinzufuegen...", "Entfernen", "Neu scannen"):
            tk.Button(self.knoepfe, text=text).pack(side="left", padx=2)
        self.anordnen = knoepfe_unter_liste(self.zeile, self.knoepfe, self.karte, self.titel, self.MINDEST)

    def _breite(self, pixel: int) -> None:
        self.top.geometry("%dx200" % pixel)
        for _ in range(4):
            self.top.update()

    def _noetig(self) -> int:
        self.top.update_idletasks()
        return self.titel.winfo_reqwidth() + 8 + self.MINDEST + self.knoepfe.winfo_reqwidth() + 8

    def test_breit_stehen_die_knoepfe_rechts_neben_der_liste(self) -> None:
        self._breite(self._noetig() + 150)
        self.assertEqual("right", str(self.knoepfe.pack_info()["side"]))
        self.assertEqual([str(self.titel), str(self.knoepfe), str(self.karte)],
                         [str(k) for k in self.zeile.pack_slaves()])

    def test_schmal_stehen_sie_rechtsbuendig_darunter(self) -> None:
        self._breite(self._noetig() - 120)
        info = self.knoepfe.pack_info()
        self.assertEqual("bottom", str(info["side"]))
        self.assertEqual("e", str(info["anchor"]))
        self.assertEqual(str(self.knoepfe), str(self.zeile.pack_slaves()[0]), "zuerst gepackt: ueber die ganze Breite")

    def test_schmal_hat_die_liste_ihre_mindestbreite(self) -> None:
        """Das war der Fehler: Der Liste blieben 6 Pixel."""
        self._breite(self._noetig() - 120)
        self.assertGreaterEqual(self.karte.winfo_width(), self.MINDEST)

    def test_der_weg_zurueck_stellt_die_reihe_her(self) -> None:
        self._breite(self._noetig() - 120)
        self._breite(self._noetig() + 150)
        self.assertEqual("right", str(self.knoepfe.pack_info()["side"]))
        self.assertEqual([str(self.titel), str(self.knoepfe), str(self.karte)],
                         [str(k) for k in self.zeile.pack_slaves()])

    def test_ohne_die_regel_blieben_der_liste_nur_wenige_pixel(self) -> None:
        """Der Beleg, dass der Test den alten Fehler misst: gleiche Breite, aber ohne Regel (nie angewendet)."""
        top = tk.Toplevel(_WURZEL)
        top.attributes("-alpha", 0.0)
        self.addCleanup(top.destroy)
        zeile = tk.Frame(top)
        zeile.pack(fill="x")
        titel = tk.Label(zeile, text="SCAN-ORDNER")
        titel.pack(side="left", padx=(0, 8))
        karte = tk.Frame(zeile)
        karte.pack(side="left", fill="x", expand=True)
        tk.Listbox(karte, height=2, width=10).pack(fill="x", expand=True)
        knoepfe = tk.Frame(zeile)
        knoepfe.pack(side="right", padx=(8, 0), before=karte)
        for text in ("Ordner hinzufuegen...", "Entfernen", "Neu scannen"):
            tk.Button(knoepfe, text=text).pack(side="left", padx=2)
        top.geometry("%dx200" % (self._noetig() - 120))
        for _ in range(4):
            top.update()
        self.assertLess(karte.winfo_width(), self.MINDEST)


class QuelltextTests(unittest.TestCase):
    @staticmethod
    def _seite() -> str:
        with open(HAUPTDATEI, encoding="utf-8") as datei:
            quelle = datei.read()
        anfang = quelle.index("    def _konsole_y2jb_bauen(self)")
        ende = quelle.index("\n    def ", anfang + 10)
        return quelle[anfang:ende]

    def test_beide_karten_benutzen_die_regel(self) -> None:
        seite = self._seite()
        # je Karte die Auswahlzeile und die Fusszeile
        self.assertEqual(4, seite.count("zeile_umbrechen("))
        self.assertIn("zeile_umbrechen(zeile_rel, release_box,", seite)
        self.assertIn("zeile_umbrechen(zeile_update_rel, update_box,", seite)
        self.assertIn("zeile_umbrechen(fuss_datei, status_datei,", seite)
        self.assertIn("zeile_umbrechen(fuss_update, status_update,", seite)

    def test_die_scan_ordner_der_bibliothek_benutzen_die_regel(self) -> None:
        with open(HAUPTDATEI, encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertEqual(1, quelle.count("knoepfe_unter_liste(folders_row, folders_btns, ordner_karte, ordner_titel,"))

    def test_die_hinweise_gehen_bei_platzmangel_zuerst(self) -> None:
        seite = self._seite()
        self.assertEqual(1, seite.count("hinweise_bei_platzmangel_ausblenden("))
        self.assertIn("(hinweis_ziel, zeile_ziel), (hinweis_usb, zeile_usb)", seite)

    def test_die_schritt_ueberschrift_bricht_um(self) -> None:
        seite = self._seite()
        anfang = seite.index("def _beschriftung(")
        block = seite[anfang:seite.index("def _statuszeile(", anfang)]
        self.assertIn("wraplength", block)
        self.assertIn('<Configure>', block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
