# -*- coding: utf-8 -*-
"""Die Kachel der Knopfleiste beginnt erst hinter ABBRECHEN (v1.9.63).

Nutzerwunsch vom 04.10.2026, mit Bild von STARTEN und ABBRECHEN: "Hinter diesen
Knoepfen moechte ich bitte keine Kachel sehen bzw. soll die Kachel erst nach dem
Knopf ABBRECHEN (rechts daneben mit 8px Spaltenbreite) beginnen."

Gemessen am Stand des Nutzers: Der Regler "Knopfleiste unten" stand auf 19 %. Die
Flaeche der Leiste mischt das Hintergrundbild dann zu 81 % mit der Fensterfarbe -
ein dunkler Kasten, der auch hinter beiden Knoepfen lag.
"""
from __future__ import annotations

import ast
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("knopfleiste_kachel")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

try:
    import tkinter as tk
    from PIL import Image
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

KLASSE = APP.PS5ConverterGUI
BLAU, ROT = (0, 0, 255), (255, 0, 0)


def _nackt(kachel_x):
    """Ein Programmobjekt ohne Aufbau; die Mischung ist eine rote Flaeche."""
    objekt = KLASSE.__new__(KLASSE)
    objekt._blend_bg_image_for_action_bar = lambda bild: Image.new("RGB", bild.size, ROT)
    objekt._knopfleiste_kachel_x = lambda: kachel_x
    return objekt


class MischenTests(unittest.TestCase):
    """Die Teilung des Ausschnitts - ohne Fenster."""

    @staticmethod
    def _bild(breite: int = 300, hoehe: int = 20) -> "Image.Image":
        return Image.new("RGB", (breite, hoehe), BLAU)

    @staticmethod
    def _farben(ergebnis) -> tuple:
        return ergebnis.getpixel((0, 5)), ergebnis.getpixel((ergebnis.width - 1, 5))

    def test_links_vom_beginn_bleibt_das_bild_rechts_davon_die_kachel(self) -> None:
        bild = _nackt(100)._knopfleiste_mischen(self._bild(), 0)
        self.assertEqual((BLAU, ROT), self._farben(bild))
        self.assertEqual(BLAU, bild.getpixel((99, 5)))
        self.assertEqual(ROT, bild.getpixel((100, 5)), "ab dem Beginn die Kachel")

    def test_ein_ausschnitt_mit_versatz_wird_an_derselben_stelle_geteilt(self) -> None:
        """Eine Groessenanzeige, die erst bei x=60 liegt, schneidet die Grenze bei 40."""
        bild = _nackt(100)._knopfleiste_mischen(self._bild(), 60)
        self.assertEqual(BLAU, bild.getpixel((39, 5)))
        self.assertEqual(ROT, bild.getpixel((40, 5)))

    def test_ein_ausschnitt_ganz_rechts_ist_ganz_kachel(self) -> None:
        bild = _nackt(100)._knopfleiste_mischen(self._bild(), 100)
        self.assertEqual((ROT, ROT), self._farben(bild))

    def test_ein_ausschnitt_ganz_links_ist_ganz_bild(self) -> None:
        """Die Pille von ABBRECHEN liegt links vom Beginn: ihre Ecken zeigen das Bild."""
        bild = _nackt(100)._knopfleiste_mischen(self._bild(60), 0)
        self.assertEqual((BLAU, BLAU), self._farben(bild))

    def test_ohne_stehende_knoepfe_gilt_die_ganze_leiste_als_kachel(self) -> None:
        bild = _nackt(None)._knopfleiste_mischen(self._bild(), 0)
        self.assertEqual((ROT, ROT), self._farben(bild))

    def test_der_eingang_bleibt_unveraendert(self) -> None:
        ausschnitt = self._bild()
        _nackt(100)._knopfleiste_mischen(ausschnitt, 0)
        self.assertEqual(BLAU, ausschnitt.getpixel((250, 5)))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class LeisteTests(unittest.TestCase):
    """Am wirklichen Programm: der Regler des Nutzers (19 %) und die Leiste."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = KLASSE(_WURZEL)
        cls.app._current_language = "de"
        if cls.app._bg_image_cache is None:
            raise unittest.SkipTest("kein Hintergrundbild geladen")
        _WURZEL.deiconify()
        try:
            _WURZEL.state("normal")
        except tk.TclError:
            pass
        _WURZEL.geometry("%dx%d" % (APP.WINDOW_MIN_WIDTH + 200, 900))
        cls._ruhen(2.0)

    @classmethod
    def tearDownClass(cls) -> None:
        _WURZEL.withdraw()

    @staticmethod
    def _ruhen(sekunden: float) -> None:
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            _WURZEL.update()
            time.sleep(0.01)

    def _ausschnitt(self, deckkraft: int):
        """Der Bildausschnitt der ganzen Leiste bei einem Reglerstand."""
        app = self.app
        werte = {"leiste_deckkraft": deckkraft}
        with mock.patch.object(app, "_load_setting",
                               lambda schluessel, vorgabe=None: werte.get(schluessel, vorgabe)):
            return app._compute_content_bg_crop(
                app.action_bar, app.action_bar.winfo_width(), app.action_bar.winfo_height())

    def _grenze(self) -> int:
        """Beginn der Kachel in Pixeln der Leiste."""
        app = self.app
        return (app._knopfleiste_kachel_x()
                - (app.action_bar.winfo_rootx() - app.content_area.winfo_rootx()))

    def test_der_beginn_liegt_acht_pixel_rechts_von_abbrechen(self) -> None:
        app = self.app
        abbrechen_rechts = (app.abort_btn.winfo_rootx() + app.abort_btn.winfo_width()
                            - app.content_area.winfo_rootx())
        self.assertEqual(8, app._knopfleiste_kachel_x() - abbrechen_rechts)
        # Und vor der Groessenanzeige - die Kachel umschliesst, was rechts steht.
        self.assertLess(app._knopfleiste_kachel_x(),
                        app.size_label.winfo_rootx() - app.content_area.winfo_rootx())

    def test_hinter_den_knoepfen_liegt_bei_jedem_reglerstand_dasselbe_bild(self) -> None:
        grenze = self._grenze()
        self.assertGreater(grenze, 100, "ABBRECHEN steht noch nicht")
        voll, nutzer, leer = (self._ausschnitt(w) for w in (100, 19, 0))
        for name, bild in (("19 %", nutzer), ("0 %", leer)):
            with self.subTest(regler=name):
                self.assertEqual(
                    voll.crop((0, 0, grenze, voll.height)).tobytes(),
                    bild.crop((0, 0, grenze, bild.height)).tobytes(),
                    "Hinter STARTEN und ABBRECHEN darf der Regler nichts mischen.")

    def test_hinter_dem_beginn_wirkt_der_regler(self) -> None:
        app = self.app
        grenze = self._grenze()
        leer = self._ausschnitt(0)
        flaeche = Image.new("RGB", (1, 1), app._COLORS["bg_main"]).getpixel((0, 0))
        mitte = leer.height // 2
        # Rechts vom Beginn nur die Fensterfarbe (der Schein um STARTEN reicht nicht so weit).
        self.assertEqual(flaeche, leer.getpixel((grenze + 5, mitte)))
        self.assertEqual(flaeche, leer.getpixel((leer.width - 1, mitte)))
        self.assertNotEqual(flaeche, leer.getpixel((grenze - 5, mitte)),
                            "Links vom Beginn steht das Bild, nicht die Fensterfarbe.")

    def test_die_pillenecken_der_knoepfe_zeigen_das_bild_nicht_die_kachel(self) -> None:
        app = self.app
        for name in ("run_btn", "abort_btn"):
            knopf = getattr(app, name)
            with self.subTest(knopf=name):
                grund = {}
                for deckkraft in (0, 100):
                    werte = {"leiste_deckkraft": deckkraft}
                    with mock.patch.object(app, "_load_setting",
                                           lambda schluessel, vorgabe=None, w=werte: w.get(schluessel, vorgabe)):
                        grund[deckkraft] = app._rund_hintergrund(
                            knopf, knopf.winfo_width(), knopf.winfo_height())
                self.assertEqual(grund[100].tobytes(), grund[0].tobytes())

    def test_das_bild_der_leiste_merkt_sich_den_beginn(self) -> None:
        """``_knopfleiste_nachziehen`` rechnet nur neu, wenn der Beginn gewandert ist."""
        app = self.app
        self.assertEqual(app._knopfleiste_kachel_x(), app._kachel_x_gezeichnet)
        with mock.patch.object(app, "_apply_action_bar_bg_resize") as neu:
            app._knopfleiste_nachziehen()
            neu.assert_not_called()
            app._kachel_x_gezeichnet = -1
            app._knopfleiste_nachziehen()
            neu.assert_called_once()
        app._kachel_x_gezeichnet = app._knopfleiste_kachel_x()


class QuelltextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"))
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        cls.methoden = {k.name: k for k in klasse.body if isinstance(k, ast.FunctionDef)}

    def test_der_ausschnitt_der_leiste_geht_durch_die_teilung(self) -> None:
        rufe = {k.func.attr for k in ast.walk(self.methoden["_compute_content_bg_crop"])
                if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)}
        self.assertIn("_knopfleiste_mischen", rufe)
        self.assertNotIn("_blend_bg_image_for_action_bar", rufe,
                         "Direkt gemischt: dann liegt die Kachel wieder hinter den Knoepfen.")

    def test_der_abstand_ist_acht_pixel(self) -> None:
        self.assertEqual(8, KLASSE._KACHEL_ABSTAND)

    def test_das_bild_der_leiste_wird_nachgezogen(self) -> None:
        """Beim ersten Aufbau steht ABBRECHEN noch nicht - die runden Flaechen rechnen nach."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn("self._runde_nachzieher.append(self._knopfleiste_nachziehen)", quelle)
        self.assertIn("_kachel_x_gezeichnet", ast.unparse(self.methoden["_apply_action_bar_bg_resize"]),
                      "Ohne den Merker rechnet das Nachziehen bei jedem Lauf neu.")


if __name__ == "__main__":
    unittest.main()
