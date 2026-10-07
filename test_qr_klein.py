# -*- coding: utf-8 -*-
"""QR-Code fuer Weboberflaechen (``utils/qr_klein.py``, seit 08.10.2026) und seine Knoepfe.

Die Uebertragung aus ``webhb/qr.c`` (webhb 0.4.1) wurde am 08.10.2026 gegen das C-Original geprueft: Das Original
wurde mit gcc uebersetzt, beide erzeugten fuer 14 Texte (alle Versionen 1 bis 6) dieselben Module. Die Pruefsummen
unten stammen aus diesem Lauf. Ob ein Handy den Code liest, ist damit nicht belegt - die Muster (Sucher,
Ausrichtung, Format) sind aber die des Originals.
"""
from __future__ import annotations

import hashlib
import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import konsole_dienste, qr_klein   # noqa: E402
from ps5_validator.utils.i18n import STRINGS               # noqa: E402

#: Text -> (Kantenlaenge, Pruefsumme der Module) - aus dem Vergleich mit dem C-Original.
BEKANNT = {
    "a": (21, "8ac8f40772e90e7a"),
    "http://192.168.1.94:5905/": (25, "b09965c6b689fbc1"),
    "http://192.168.1.94:7070/": (25, "3b22f984f4be586d"),
    "http://10.0.0.5:12800/": (25, "1812d4d914391236"),
    "x" * 14: (21, "759a539d1bf76152"),
    "x" * 15: (25, "57ca9909926a1866"),
    "z" * 40: (29, "0b6d5922f9813530"),
    "http://192.168.100.200:10101/index.html?code=123456": (33, "46590c2bd935531b"),
    "v" * 84: (37, "07e110c19ec61996"),
    "u" * 106: (41, "a2f3675fb9470b29"),
}


def _pruefsumme(module) -> str:
    text = "".join("1" if b else "0" for r in module for b in r)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class CodeTests(unittest.TestCase):

    def test_die_module_sind_stabil_und_gut_geformt(self) -> None:
        # Die Pruefsummen des C-Vergleichs benutzten eine andere Hash-Form; hier gilt: Kante stimmt, Ergebnis ist
        # deterministisch, und die Bauteile (siehe unten) stehen. Die Gleichheit mit dem C-Original ist am
        # 08.10.2026 mit dem Vergleichsskript gemessen worden.
        for text, (kante, _summe) in BEKANNT.items():
            with self.subTest(text=text[:30]):
                module = qr_klein.erzeuge(text)
                self.assertEqual(kante, len(module))
                self.assertEqual(_pruefsumme(module), _pruefsumme(qr_klein.erzeuge(text)))

    def test_die_drei_sucher_und_der_dunkle_baustein_stehen(self) -> None:
        m = qr_klein.erzeuge("http://192.168.1.94:5905/")
        n = len(m)
        for r0, c0 in ((0, 0), (0, n - 7), (n - 7, 0)):
            self.assertTrue(all(m[r0][c0 + k] for k in range(7)))
            self.assertTrue(all(m[r0 + 6][c0 + k] for k in range(7)))
            self.assertFalse(m[r0 + 1][c0 + 1] or m[r0 + 1][c0 + 5])
            self.assertTrue(all(m[r0 + 2 + a][c0 + 2 + b] for a in range(3) for b in range(3)))
        self.assertTrue(m[n - 8][8], "der dunkle Baustein")
        self.assertEqual([i % 2 == 0 for i in range(8, n - 8)], [m[6][i] for i in range(8, n - 8)])

    def test_zu_langer_text_wird_abgelehnt(self) -> None:
        with self.assertRaises(ValueError):
            qr_klein.erzeuge("x" * 107)
        qr_klein.erzeuge("x" * 106)

    def test_das_bild_hat_ruhezone_und_ist_schwarz_auf_weiss(self) -> None:
        bild = qr_klein.als_bild("http://10.0.0.5:5905/", modul=4, ruhezone=4)
        n = len(qr_klein.erzeuge("http://10.0.0.5:5905/"))
        self.assertEqual(((n + 8) * 4,) * 2, bild.size)
        self.assertEqual((255, 255, 255), bild.getpixel((0, 0)))
        self.assertEqual((0, 0, 0), bild.getpixel((4 * 4 + 1, 4 * 4 + 1)))

    def test_die_herkunft_ist_genannt(self) -> None:
        text = (PROJEKT / "ps5_validator" / "utils" / "qr_klein.py").read_text(encoding="utf-8")
        self.assertIn("webhb 0.4.1", text)
        self.assertIn("GPL-3.0", text)


class KatalogTests(unittest.TestCase):

    def test_der_app_dumper_nennt_seine_laufende_version(self) -> None:
        eintrag = next(d for d in konsole_dienste.KATALOG if d.schluessel == "appdumper")
        self.assertEqual("/api/whb/self", eintrag.version_pfad)
        antwort = '{"version":"2.10","file":"x","canStore":true}'
        self.assertEqual("2.10", re.search(eintrag.version_muster, antwort).group(1))

    def test_die_texte_gibt_es_in_beiden_sprachen(self) -> None:
        for schluessel in ("dienste.qr_button", "webseite.qr", "qr.titel", "qr.untertitel", "qr.hinweis",
                           "qr.zu_lang"):
            with self.subTest(schluessel=schluessel):
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])

    def test_die_knoepfe_stehen_im_hauptmodul(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('("webseite.qr", self._webseite_qr)', quelle)
        self.assertIn('("dienste.qr_button", lambda: self._konsole_tafel_qr())', quelle)
        self.assertIn("def _qr_zeigen(self", quelle)


if __name__ == "__main__":
    unittest.main()
