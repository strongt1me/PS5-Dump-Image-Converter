# -*- coding: utf-8 -*-
"""Aufgabe 7 "PKG / FPKG" steht durchsichtig auf dem Hauptbild (``ui/seitenbild.py``, seit 31.10.2026).

Nutzerwunsch: "durchsichtig ueber dem Hintergrundbild wie bei Aufgabe 1". Rahmen, Beschriftungen, gezeichnete Teile und
runde Karten bekommen den Bildausschnitt hinter sich; die Karten mit eigener Flaeche (Felder, Protokoll, Kacheln) bleiben.
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.ui import pkg_fpkg_seite                 # noqa: E402
from ps5_validator.utils import bibliothek_raster as raster  # noqa: E402


def _durchlauf(s) -> None:
    """Zwingt einen Durchlauf des Unterlegens und lässt Tk die Folgen verarbeiten."""
    for _ in range(3):
        _WURZEL.update()
        s.bild.jetzt()
    _WURZEL.update()


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class SeitenbildTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.geometry("1500x950+10+10")
        _WURZEL.deiconify()
        _WURZEL.update()

    @classmethod
    def tearDownClass(cls) -> None:
        _WURZEL.withdraw()

    def setUp(self) -> None:
        self.app._ansicht_setzen("umwandeln")
        self.app._show_pkg_fpkg_seite()
        self.s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        _durchlauf(self.s)
        if getattr(self.app, "_bg_image_cache", None) is None:
            self.skipTest("Ohne Hauptbild gibt es nichts zu unterlegen")

    def _unter(self, rahmen):
        return getattr(rahmen, "_sb_unter", None)

    def test_der_inhalt_ist_ein_rahmen_ohne_karte(self) -> None:
        s = self.s
        self.assertIsInstance(s.inhalt, tk.Frame)
        self.assertNotIsInstance(s.inhalt, raster.RundeKarte, "Keine feste Flaeche mehr um Quelle und Bereich.")

    def test_rahmen_bekommen_ihren_bildausschnitt_ganz_unten(self) -> None:
        s = self.s
        unter = self._unter(s.inhalt)
        self.assertIsNotNone(unter, "Der Rahmen hat sein Unterlegbild.")
        self.assertTrue(str(unter.cget("image")), "Das Unterlegbild zeigt den Bildausschnitt.")
        kinder = s.inhalt.tk.splitlist(s.inhalt.tk.call("winfo", "children", str(s.inhalt)))
        self.assertEqual(str(unter), str(kinder[0]), "Es liegt unter allen anderen Teilen.")

    def test_das_unterlegbild_bleibt_unten_auch_nach_einem_lower_des_kindes(self) -> None:
        s = self.s
        kind = s._sichtbar
        self.assertIsNotNone(kind)
        kind.lower()                      # wie beim verdeckten Vorbauen eines Bereichs
        _durchlauf(s)
        unter = self._unter(s.bereich)
        kinder = s.bereich.tk.splitlist(s.bereich.tk.call("winfo", "children", str(s.bereich)))
        self.assertEqual(str(unter), str(kinder[0]))

    def test_ein_label_hat_den_ausschnitt_in_der_groesse_seines_textes(self) -> None:
        s = self.s
        label = s._hinweis                # ein Label der Seite selbst (eigene Beschriftung, nicht das Muster)
        self.assertTrue(getattr(label, "_sb_eigen", False) is False)
        gefunden = []
        stapel = [s.inhalt]
        while stapel:
            knoten = stapel.pop()
            for k in knoten.winfo_children():
                if (isinstance(k, tk.Label) and not getattr(k, "_sb_eigen", False)
                        and getattr(k, "_sb_foto", None) is not None and k.winfo_ismapped()):
                    gefunden.append(k)
                stapel.append(k)
        self.assertGreater(len(gefunden), 5, "Die Beschriftungen des Bereichs tragen ihren Ausschnitt.")
        for k in gefunden:
            self.assertEqual("center", str(k.cget("compound")))
            self.assertEqual((0, 0), (int(str(k.cget("padx"))), int(str(k.cget("pady")))),
                             "Rand und Polsterung stecken im Bild, sonst saehe man einen Kasten ringsum.")
            self.assertEqual((k._sb_foto.width(), k._sb_foto.height()), (k.winfo_width(), k.winfo_height()),
                             "Das Bild deckt das Label genau: %r (%s)" % (self.s.bild._text(k), k))

    def test_ein_gestrecktes_label_wird_auf_seinen_text_zurueckgenommen(self) -> None:
        s = self.s
        zeile = tk.Frame(s.inhalt)
        zeile.pack(fill="x")
        label = tk.Label(zeile, text="Breite Zeile", anchor="w", bg="#000000", fg="#ffffff", padx=2, pady=3)
        label.pack(fill="x")
        _durchlauf(s)
        self.assertEqual("none", str(label.pack_info()["fill"]), "Das Label fuellt die Zeile nicht mehr aus.")
        self.assertEqual("w", str(label.pack_info()["anchor"]), "Es steht weiter links, wie sein Anker es wollte.")
        self.assertLess(label.winfo_width(), zeile.winfo_width() // 2)
        zeile.destroy()

    def test_ein_label_mit_eigenem_bild_wird_nicht_angefasst(self) -> None:
        s = self.s
        zeile = tk.Frame(s.inhalt)
        zeile.pack(fill="x")
        foto = tk.PhotoImage(master=_WURZEL, width=20, height=20)
        label = tk.Label(zeile, image=foto)
        label.pack()
        _durchlauf(s)
        self.assertEqual(str(foto), str(label.cget("image")))
        zeile.destroy()

    def test_runde_karten_malen_ihre_ecken_ueber_dem_bild(self) -> None:
        s = self.s
        p = s.g._bibliothek_zeichner()
        karte = raster.RundeKarte(s.inhalt, p, fuellung="console_bg", rand="border", grund="bg_main", radius=None,
                                  polster=(4, 3))
        tk.Label(karte.innen, text="x").pack()
        karte.pack(fill="x")
        _durchlauf(s)
        self.assertIsNotNone(karte._untergrund_bild(40, 30), "Die Karte findet den Ausschnitt ueber den Seitenrahmen.")
        foto = karte._foto
        pixel = foto.width(), foto.height()
        self.assertEqual(pixel, (karte.winfo_width(), karte.winfo_height()))
        # Die Ecke ist nicht mehr die einfarbige Grundfarbe, sondern ein Stueck des Bildes.
        r, g, b = (int(v) for v in _WURZEL.tk.call(str(foto), "get", 0, 0))
        grund = _WURZEL.winfo_rgb(s.c["bg_main"])
        self.assertNotEqual((r, g, b), tuple(v // 257 for v in grund), "Die Ecke zeigt das Bild, nicht die Grundfarbe.")
        karte.destroy()

    def test_ohne_seitenrahmen_bleibt_die_karte_wie_sie_war(self) -> None:
        fenster = tk.Toplevel(_WURZEL)
        try:
            karte = raster.RundeKarte(fenster, self.s.g._bibliothek_zeichner(), fuellung="bg_card", rand="border",
                                      grund="bg_main")
            self.assertIsNone(karte._untergrund_bild(40, 30), "Gegenprobe: ohne Seite auf dem Bild keine Aenderung.")
        finally:
            fenster.destroy()

    def test_der_bildausschnitt_eines_teils_ueber_dem_rand_wird_nicht_gedehnt(self) -> None:
        s = self.s
        gross = s.bild_hinter(s.inhalt, 400, s.rahmen.winfo_height() + 500)
        self.assertEqual((400, s.rahmen.winfo_height() + 500), gross.size, "Immer genau die verlangte Groesse.")
        # Die Ueberstand-Zone ist schwarz aufgefuellt, nicht mit dem Bild gestreckt.
        self.assertEqual((0, 0, 0), gross.getpixel((10, gross.size[1] - 5)))

    def test_der_versatz_verschiebt_den_ausschnitt(self) -> None:
        s = self.s
        a = s.bild_hinter(s.inhalt, 60, 40)
        b = s.bild_hinter(s.inhalt, 60, 40, (-10, 0))
        self.assertNotEqual(a.tobytes(), b.tobytes())

    # ------------------------------------------------------------------
    # Die Karte (``karte_bauen``): getoentes Bild, runde Ecken - wie ``path_card`` der Aufgabe 1
    # ------------------------------------------------------------------
    def _karte(self, kennung: str = "fpkg"):
        s = self.s
        (s.fpkg_zeigen if kennung == "fpkg" else s.pkg_zeigen)()
        _durchlauf(s)
        karte = s._quellsaetze[kennung]["zeile"].master.master
        self.assertTrue(getattr(karte, "_sb_karte", False))
        return karte

    def test_die_karte_traegt_das_getoente_bild_und_zeigt_in_den_ecken_das_hauptbild(self) -> None:
        from unittest import mock
        s, app = self.s, self.app
        karte = self._karte()
        b, h = int(karte.winfo_width()), int(karte.winfo_height())
        with mock.patch.object(app, "_regler_anteil", return_value=0.3):
            bild = s.bild_karte(karte, b, h)
            roh = s._ausschnitt(karte, b, h, (0, 0), True)
            hinten = s._ausschnitt(karte, b, h, (0, 0), False)
            erwartet = app._blend_bg_image_for_card(roh).convert("RGB")
        self.assertEqual((b, h), bild.size)
        self.assertEqual(hinten.getpixel((0, 0)), bild.getpixel((0, 0)), "Die Ecke zeigt das Bild hinter der Karte.")
        mitte = (b // 2, h // 2)
        self.assertEqual(erwartet.getpixel(mitte), bild.getpixel(mitte), "Die Mitte ist das getoente Bild.")
        self.assertNotEqual(hinten.getpixel(mitte), bild.getpixel(mitte), "Gegenprobe: getoent heisst anders als das Bild.")

    def test_teile_in_der_karte_bekommen_den_getoenten_ausschnitt_teile_davor_nicht(self) -> None:
        from unittest import mock
        s, app = self.s, self.app
        karte = self._karte()
        innen = s._quellsaetze["fpkg"]["zeile"]
        self.assertTrue(s._in_karte(innen))
        self.assertFalse(s._in_karte(s._titel), "Der Titel steht auf dem Hauptbild, nicht in der Karte.")
        with mock.patch.object(app, "_regler_anteil", return_value=0.3):
            drin = s.bild_hinter(innen, 80, 30)
            roh = s._ausschnitt(innen, 80, 30, (0, 0), True)
            soll = app._blend_bg_image_for_card(roh).convert("RGB")
            draussen = s.bild_hinter(s._titel, 80, 30)
            plain = s._ausschnitt(s._titel, 80, 30, (0, 0), False)
        self.assertEqual(soll.tobytes(), drin.convert("RGB").tobytes())
        self.assertEqual(plain.tobytes(), draussen.tobytes())

    def test_die_karte_hat_beim_ersten_zeigen_schon_ihr_unterlegbild(self) -> None:
        karte = self._karte("pkg")
        unter = self._unter(karte)
        self.assertIsNotNone(unter)
        self.assertTrue(str(unter.cget("image")))


if __name__ == "__main__":                            # pragma: no cover
    unittest.main()
