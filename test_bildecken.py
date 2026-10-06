# -*- coding: utf-8 -*-
"""Runde Ecken fuer Spielbilder (``bildecken``) - wie die Kacheln im Homescreen der PS5 (Nutzer 06.10.2026).

Gemessen an Pixeln: Ecke zeigt den Grund, Mitte und Kantenmitte das Bild, der Uebergang ist geglaettet. Dazu
Waechter, dass alle Stellen mit Spielbildern die Rundung benutzen.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

from PIL import Image

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import bildecken  # noqa: E402

ROT = (200, 20, 20)
BLAU = (10, 30, 200)


class RundungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.bild = Image.new("RGB", (200, 200), ROT)

    def test_radius_wie_die_ps5_kacheln(self) -> None:
        self.assertEqual(15, bildecken.radius_fuer((200, 200)))
        self.assertEqual(15, bildecken.radius_fuer((200, 400)), "die kuerzere Kante zaehlt")

    def test_ecke_zeigt_den_grund_mitte_das_bild(self) -> None:
        rund = bildecken.runde_ecken(self.bild, BLAU)
        self.assertEqual("RGB", rund.mode)
        self.assertEqual((200, 200), rund.size)
        for ecke in ((0, 0), (199, 0), (0, 199), (199, 199)):
            with self.subTest(ecke=ecke):
                self.assertEqual(BLAU, rund.getpixel(ecke))
        for punkt in ((100, 100), (100, 0), (0, 100), (199, 100)):
            with self.subTest(punkt=punkt):
                self.assertEqual(ROT, rund.getpixel(punkt))

    def test_uebergang_ist_geglaettet(self) -> None:
        maske = bildecken.maske((200, 200), 15)
        werte = {maske.getpixel((i, i)) for i in range(0, 10)}
        self.assertTrue(any(0 < w < 255 for w in werte), "harte Treppe statt glatter Rundung")

    def test_ohne_grund_durchsichtig(self) -> None:
        rund = bildecken.runde_ecken(self.bild)
        self.assertEqual("RGBA", rund.mode)
        self.assertEqual(0, rund.getpixel((0, 0))[3])
        self.assertEqual(255, rund.getpixel((100, 100))[3])

    def test_grund_als_bild(self) -> None:
        grund = Image.new("RGB", (200, 200), BLAU)
        self.assertEqual(BLAU, bildecken.runde_ecken(self.bild, grund).getpixel((0, 0)))

    def test_hochformat_bleibt_hochformat(self) -> None:
        self.assertEqual((120, 200), bildecken.runde_ecken(Image.new("RGB", (120, 200)), BLAU).size)


class StellenTests(unittest.TestCase):
    """Jede Stelle, die ein Spielbild zeigt, rundet es (Textsuche im Quelltext)."""

    def test_alle_stellen_runden(self) -> None:
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        for methode in ("def _sidebar_cover_foto", "def _apply_info_cover", "def _bibliothek_minibild",
                        "def _cover_setzen"):
            with self.subTest(stelle=methode):
                start = haupt.index(methode)
                self.assertIn("bildecken.runde_ecken(", haupt[start:start + 2500])
        ota = (PROJEKT / "ps5_validator" / "ui" / "ps4_ota.py").read_text(encoding="utf-8")
        self.assertIn("bildecken.runde_ecken(", ota)

    def test_das_cover_der_leiste_zieht_die_ecken_nach(self) -> None:
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn("self._sidebar_cover_ecken_nachziehen]", haupt)


if __name__ == "__main__":
    unittest.main()
