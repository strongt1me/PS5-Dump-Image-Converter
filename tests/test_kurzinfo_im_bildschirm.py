# -*- coding: utf-8 -*-
"""Kurzinfos (``DelayedTooltip``) bleiben im sichtbaren Bildschirmbereich.

Meldung vom 16.11.2026: Die Kurzinfo am Haken BACKPORT war rechts abgeschnitten. Gemessen am echten Tk-Fenster: Steht der Haken am
rechten Bildschirmrand, ragt die Kurzinfo (431 Pixel breit) 397 Pixel ueber den Rand hinaus - sie wurde immer genau darunter
gesetzt, ohne den Bildschirm anzusehen. Jetzt gilt: rechts hinaus -> nach links rutschen, unten hinaus -> ueber den Haken.

Bewacht wird die reine Rechnung (``plattform.kurzinfo_ort``), die Frage nach dem Bildschirm am Punkt
(``plattform.arbeitsbereich_am_punkt``) und das echte Fenster samt Gegenprobe (ohne die Korrektur ragt die Kurzinfo hinaus).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("kurzinfo_bildschirm")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import plattform                   # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

BEREICH = (0, 0, 1920, 1152)                                # Bildschirm 1920 x 1200, Taskleiste unten (48)


class KurzinfoOrtTests(unittest.TestCase):
    """Die Rechnung: wohin kommt die linke obere Ecke?"""

    def test_was_passt_bleibt_wo_es_ist(self) -> None:
        self.assertEqual((936, 187), plattform.kurzinfo_ort(936, 187, 431, 94, BEREICH, 150))

    def test_rechts_hinaus_rutscht_nach_links(self) -> None:
        # Der gemessene Fall: Haken bei x=1868, Kurzinfo ab 1886, 431 breit.
        self.assertEqual((1920 - 431, 187), plattform.kurzinfo_ort(1886, 187, 431, 94, BEREICH, 150))

    def test_unten_hinaus_steht_sie_ueber_dem_haken(self) -> None:
        x, y = plattform.kurzinfo_ort(500, 1120, 431, 94, BEREICH, widget_oben=1090)
        self.assertEqual(1090 - 8 - 94, y)
        self.assertLessEqual(y + 94, 1090, "sie verdeckt den Haken nicht")
        self.assertEqual(500, x)

    def test_rechts_und_unten_zugleich(self) -> None:
        x, y = plattform.kurzinfo_ort(1886, 1126, 431, 94, BEREICH, widget_oben=1100)
        self.assertEqual((1489, 998), (x, y))

    def test_ist_oben_kein_platz_haelt_sie_am_oberen_rand(self) -> None:
        klein = (0, 0, 800, 100)
        self.assertEqual((10, 0), plattform.kurzinfo_ort(10, 90, 300, 94, klein, widget_oben=60))

    def test_nie_ueber_den_linken_rand(self) -> None:
        self.assertEqual((0, 187), plattform.kurzinfo_ort(-40, 187, 431, 94, BEREICH, 150))

    def test_zweiter_bildschirm_mit_negativem_ursprung(self) -> None:
        """Ein Bildschirm links vom ersten: seine Koordinaten beginnen bei einem negativen x."""
        links = (-1920, 0, 1920, 1080)
        self.assertEqual((-431, 200), plattform.kurzinfo_ort(-300, 200, 431, 94, links, 160), "rechts am zweiten Bildschirm")
        self.assertEqual((-1920, 200), plattform.kurzinfo_ort(-2000, 200, 431, 94, links, 160), "links davon")

    def test_breiter_als_der_bereich_gewinnt_der_linke_rand(self) -> None:
        self.assertEqual((0, 10), plattform.kurzinfo_ort(50, 10, 900, 40, (0, 0, 600, 400), 0))


class ArbeitsbereichAmPunktTests(unittest.TestCase):
    def test_ausserhalb_von_windows_gilt_der_erkannte_bildschirm(self) -> None:
        with mock.patch.object(plattform, "IST_WINDOWS", False):
            self.assertEqual((0, 0, 1280, 720), plattform.arbeitsbereich_am_punkt(5, 5, (1280, 720)))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_der_erste_bildschirm_ist_der_arbeitsbereich(self) -> None:
        """Der Punkt (1, 1) liegt immer auf dem ersten Bildschirm (Ursprung 0/0): Dort gilt dasselbe wie ``arbeitsbereich``."""
        erkannt = (1920, 1200)
        self.assertEqual(plattform.arbeitsbereich(erkannt), plattform.arbeitsbereich_am_punkt(1, 1, erkannt))

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_ein_punkt_weit_draussen_liefert_trotzdem_einen_bereich(self) -> None:
        links, oben, breite, hoehe = plattform.arbeitsbereich_am_punkt(99999, 99999, (1920, 1200))
        self.assertGreater(breite, 0)
        self.assertGreater(hoehe, 0)

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_scheitert_die_frage_gilt_der_erste_bildschirm(self) -> None:
        import ctypes
        falsch = mock.MagicMock()
        falsch.user32.MonitorFromPoint.return_value = 0             # kein Bildschirm gefunden
        with mock.patch.object(ctypes, "windll", falsch):
            self.assertEqual((0, 0, 800, 600), plattform.arbeitsbereich_am_punkt(10, 10, (800, 600)))


try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001 - ohne Anzeige entfallen die Fenstertests
    tk = None
    _WURZEL = None
    TK_DA = False


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class KurzinfoImFensterTests(unittest.TestCase):
    """``DelayedTooltip._show`` an echten Fenstern, die am Rand des Bildschirms stehen."""

    TEXT = STRINGS["main.integrate_backport_hint"]["de"]           # der Text, der gemeldet wurde (BACKPORT)

    def _knopf(self, x_fenster: int, y_fenster: int):
        fenster = tk.Toplevel(_WURZEL)
        fenster.geometry("260x80+%d+%d" % (x_fenster, y_fenster))
        self.addCleanup(fenster.destroy)
        knopf = tk.Checkbutton(fenster, text="BACKPORT")
        knopf.pack(padx=10, pady=10)
        fenster.update()
        return knopf

    def _zeigen(self, knopf):
        tipp = APP.DelayedTooltip(knopf, self.TEXT, delay_ms=900, wraplength=430)
        tipp._show()
        knopf.update()
        self.addCleanup(tipp._hide)
        return tipp._tip_window

    @staticmethod
    def _bereich(knopf):
        return plattform.arbeitsbereich_am_punkt(
            knopf.winfo_rootx() + knopf.winfo_width() // 2, knopf.winfo_rooty(),
            (knopf.winfo_screenwidth(), knopf.winfo_screenheight()))

    def _rechter_rand(self):
        return self._knopf(_WURZEL.winfo_screenwidth() - 260, 100)

    def test_am_rechten_rand_ragt_die_kurzinfo_nicht_hinaus(self) -> None:
        knopf = self._rechter_rand()
        links, oben, breite, hoehe = self._bereich(knopf)
        tip = self._zeigen(knopf)
        if tip.winfo_width() >= breite:
            self.skipTest("Bildschirm zu schmal fuer diese Kurzinfo")
        self.assertGreaterEqual(tip.winfo_rootx(), links)
        self.assertLessEqual(tip.winfo_rootx() + tip.winfo_width(), links + breite,
                             "rechte Kante %d, Bereich bis %d" % (tip.winfo_rootx() + tip.winfo_width(), links + breite))

    def test_gegenprobe_ohne_die_korrektur_ragt_sie_hinaus(self) -> None:
        """Die Meldung vom 16.11.2026 nachgestellt: Mit der alten Lage (genau unter dem Haken) steht die Kurzinfo ueber dem Rand."""
        knopf = self._rechter_rand()
        links, oben, breite, hoehe = self._bereich(knopf)
        with mock.patch.object(APP, "_system_kurzinfo_ort", lambda x, y, *a, **k: (x, y)):
            tip = self._zeigen(knopf)
        if tip.winfo_width() >= breite:
            self.skipTest("Bildschirm zu schmal fuer diese Kurzinfo")
        self.assertGreater(tip.winfo_rootx() + tip.winfo_width(), links + breite)

    def test_am_unteren_rand_steht_sie_ueber_dem_haken(self) -> None:
        probe = self._knopf(200, 200)
        links, oben, breite, hoehe = self._bereich(probe)
        knopf = self._knopf(300, oben + hoehe - 70)            # der Haken sitzt knapp ueber dem unteren Rand des Bereichs
        tip = self._zeigen(knopf)
        self.assertLessEqual(tip.winfo_rooty() + tip.winfo_height(), oben + hoehe, "nicht unter der Taskleiste")
        self.assertLessEqual(tip.winfo_rooty() + tip.winfo_height(), knopf.winfo_rooty(), "ueber dem Haken, ihn nicht verdeckend")

    def test_mitten_im_bild_bleibt_alles_wie_es_war(self) -> None:
        knopf = self._knopf(300, 200)
        tip = self._zeigen(knopf)
        self.assertEqual(knopf.winfo_rootx() + 18, tip.winfo_rootx())
        self.assertEqual(knopf.winfo_rooty() + knopf.winfo_height() + 8, tip.winfo_rooty())


class QuelltextTests(unittest.TestCase):
    def test_die_kurzinfo_fragt_den_bildschirm_und_rechnet_mit_der_labelgroesse(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        anfang = quelle.index("class DelayedTooltip:")
        koerper = quelle[anfang:quelle.index("class FlachButton", anfang)]
        self.assertIn("_system_arbeitsbereich_am_punkt(", koerper)
        self.assertIn("_system_kurzinfo_ort(", koerper)
        self.assertIn("label.winfo_reqwidth()", koerper, "die Groesse kommt vom Label")
        self.assertNotIn("update_idletasks", koerper, "das Fenster darf nicht an der alten Stelle erscheinen und dann springen")


if __name__ == "__main__":
    unittest.main()
