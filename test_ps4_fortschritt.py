# -*- coding: utf-8 -*-
"""Gesamtfortschritt und Restzeit fuer „PS4 PKG -> ffpfsc/exFAT“ (seit 07.10.2026).

Vorher lief der Balken je Teilschritt von 0 bis 100 und eine Restzeit gab es nicht. Die Aufteilung der
fuenf Stufen auf eine Skala stammt aus PS4 FFPFSC 0.2.9 (``gui.py``, GPL-3.0-or-later).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps4_fortschritt as pf   # noqa: E402
from ps5_validator.utils.i18n import STRINGS             # noqa: E402


class _Uhr:
    def __init__(self) -> None:
        self.t = 100.0

    def __call__(self) -> float:
        return self.t


class StufenTests(unittest.TestCase):
    def test_stufenzeile_wird_gelesen(self) -> None:
        self.assertEqual((3, 5), pf.stufe_aus_zeile("2026 INFO stage 3/5: creating compressed FFPFSC image"))
        self.assertIsNone(pf.stufe_aus_zeile("extracting a -> b"))
        self.assertIsNone(pf.stufe_aus_zeile(""))

    def test_die_skala_ist_lueckenlos_und_steigend(self) -> None:
        werte = [pf.STUFEN_START[n] for n in sorted(pf.STUFEN_START)]
        self.assertEqual(sorted(werte), werte)
        self.assertAlmostEqual(pf.STUFEN_START[1] + pf.BREITE_ENTPACKEN, pf.STUFEN_START[2])
        self.assertAlmostEqual(pf.STUFEN_START[2] + pf.BREITE_ZUSAMMEN, pf.STUFEN_START[3])
        self.assertAlmostEqual(pf.STUFEN_START[3] + pf.BREITE_PACKEN, pf.STUFEN_START[4])
        self.assertAlmostEqual(pf.STUFEN_START[4] + pf.BREITE_PRUEFEN, pf.STUFEN_START[5])


class RechnungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uhr = _Uhr()
        self.fp = pf.Gesamtfortschritt(jetzt=self.uhr)

    def test_entpacken_belegt_zwei_bis_dreissig_prozent(self) -> None:
        self.fp.zeile("stage 1/5: extracting")
        self.fp.ereignis({"scope": "extract", "current": 50, "total": 100})
        self.assertAlmostEqual(16.0, self.fp.prozent)
        self.fp.ereignis({"scope": "extract", "current": 100, "total": 100})
        self.assertAlmostEqual(30.0, self.fp.prozent)

    def test_der_balken_springt_nie_zurueck(self) -> None:
        self.fp.zeile("stage 3/5: packing")
        self.fp.ereignis({"scope": "mkpfs", "phase": "compress", "current": 80, "total": 100})
        hoch = self.fp.prozent
        self.fp.ereignis({"scope": "extract", "current": 10, "total": 100})   # verspaetet
        self.assertGreaterEqual(self.fp.prozent, hoch)

    def test_packen_und_pruefen_haengen_an_der_stufe(self) -> None:
        self.fp.zeile("stage 3/5: x")
        self.fp.ereignis({"scope": "mkpfs", "phase": "write", "current": 1, "total": 2})
        self.assertAlmostEqual(55.0 + 33.0 * 0.5, self.fp.prozent)
        self.fp.zeile("stage 4/5: verify")
        self.fp.ereignis({"scope": "mkpfs", "phase": "verify", "current": 1, "total": 1})
        self.assertAlmostEqual(96.0, self.fp.prozent)

    def test_mkpfs_ohne_stufe_wird_ignoriert(self) -> None:
        self.fp.ereignis({"scope": "mkpfs", "phase": "scan", "current": 1, "total": 2})
        self.assertEqual(0.0, self.fp.prozent)

    def test_statusmeldungen_und_unbekanntes_aendern_nichts(self) -> None:
        self.fp.ereignis({"scope": "mkpfs", "action": "status", "message": "x"})
        self.fp.ereignis({"scope": "irgendwas", "current": 1, "total": 2})
        self.fp.ereignis({"scope": "extract", "current": "kaputt", "total": None})
        self.assertAlmostEqual(2.0, self.fp.prozent)

    def test_mehrere_spiele_zaehlen_je_hundert(self) -> None:
        fp = pf.Gesamtfortschritt(spiel_gesamt=2, jetzt=self.uhr)
        fp.zeile("stage 5/5: publishing")
        self.assertAlmostEqual(48.0, fp.prozent)
        fp.naechstes_spiel()
        self.assertAlmostEqual(50.0, fp.prozent)
        self.assertEqual(100.0, fp.abschluss().prozent)

    def test_abschluss_ist_hundert_mit_rest_null(self) -> None:
        s = self.fp.abschluss()
        self.assertEqual(100.0, s.prozent)
        self.assertEqual(0.0, s.rest)


class RestzeitTests(unittest.TestCase):
    def test_ohne_brauchbare_grundlage_keine_schaetzung(self) -> None:
        self.assertIsNone(pf.rest_sekunden(2.0, 50.0))      # zu kurz gelaufen
        self.assertIsNone(pf.rest_sekunden(60.0, 1.0))      # zu wenig geschafft

    def test_hochrechnung(self) -> None:
        self.assertAlmostEqual(60.0, pf.rest_sekunden(60.0, 50.0))
        self.assertAlmostEqual(20.0, pf.rest_sekunden(60.0, 75.0))
        self.assertEqual(0.0, pf.rest_sekunden(60.0, 100.0))

    def test_stand_traegt_zeit_und_rest(self) -> None:
        uhr = _Uhr()
        fp = pf.Gesamtfortschritt(jetzt=uhr)
        fp.zeile("stage 1/5: x")
        fp.ereignis({"scope": "extract", "current": 1, "total": 1})
        uhr.t += 30.0
        s = fp.stand()
        self.assertAlmostEqual(30.0, s.verstrichen)
        self.assertAlmostEqual(30.0 * 70.0 / 30.0, s.rest)
        self.assertEqual(100, s.teil_prozent)

    def test_dauertext(self) -> None:
        self.assertEqual("00:00", pf.dauer_text(-5))
        self.assertEqual("01:05", pf.dauer_text(65))
        self.assertEqual("1:01:01", pf.dauer_text(3661))


class FensterAnbindungTests(unittest.TestCase):
    """Die Aufgabe fuettert den Gesamtstand, das Fenster zeigt ihn samt Restzeit (statt Teilschritt-Balken)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.aufgabe = (PROJEKT / "ps5_validator" / "utils" / "ps4_abbild.py").read_text(encoding="utf-8")
        cls.fenster = (PROJEKT / "ps5_validator" / "ui" / "ps4_dump_image.py").read_text(encoding="utf-8")

    def test_gesamtfortschritt_wird_gefuettert(self) -> None:
        for muster in ("ps4_fortschritt.Gesamtfortschritt()", "fp.zeile(sauber)", "fp.ereignis(daten)"):
            with self.subTest(muster=muster):
                self.assertIn(muster, self.aufgabe)
        self.assertIn('t("ps4dib.status_gesamt"', self.fenster)

    def test_alter_teilschrittbalken_ist_weg(self) -> None:
        self.assertNotIn("ps4pkg.status_stage", self.aufgabe + self.fenster)
        self.assertNotIn("_balken(aktuell / gesamt * 100.0)", self.aufgabe + self.fenster)

    def test_texte_sind_zweisprachig(self) -> None:
        for schluessel in ("ps4dib.status_gesamt", "ps4pkg.zeit_berechnet"):
            with self.subTest(schluessel=schluessel):
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])
        self.assertNotIn("ps4pkg.status_stage", STRINGS)
        self.assertNotIn("ps4pkg.status_gesamt", STRINGS)


if __name__ == "__main__":
    unittest.main()
