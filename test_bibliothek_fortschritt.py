# -*- coding: utf-8 -*-
"""Tests fuer den Fortschritt des Suchlaufs der Bibliothek (``bibliothek_fortschritt``) - ohne Fenster.

Geprueft wird die Rechnung, auf die sich die Anzeige verlaesst: Stufen mit Gewichten werden zu einer
Prozentzahl, der Balken geht nie zurueck, eine Stufe ohne bekannte Gesamtzahl ist "unbestimmt", und die
Drossel haelt die Rueckmeldungen der Arbeitsfaeden in einem Takt.
"""
from __future__ import annotations

import threading
import unittest

from ps5_validator.utils import bibliothek_fortschritt as fs


class PhasenTests(unittest.TestCase):

    def test_die_gewichte_der_beiden_wege_ergeben_hundert(self) -> None:
        self.assertAlmostEqual(100.0, sum(g for _n, g in fs.PC_STUFEN))
        self.assertAlmostEqual(100.0, sum(g for _n, g in fs.PS5_STUFEN))

    def test_der_anfang_jeder_stufe_ist_das_ende_der_vorigen(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        self.assertEqual(0, p.setzen("ordner", 0, 10).prozent)
        self.assertEqual(5, p.setzen("angaben", 0, 10).prozent)
        self.assertEqual(40, p.setzen("bilder", 0, 10).prozent)
        self.assertEqual(80, p.setzen("einbauten", 0, 10).prozent)

    def test_innerhalb_einer_stufe_waechst_der_balken_mit_dem_verhaeltnis(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        halb = p.setzen("angaben", 5, 10)
        self.assertEqual(5 + 17, halb.prozent)        # 35 % Gewicht, halb getan: 17,5 -> 22
        self.assertEqual((5, 10), (halb.getan, halb.gesamt))
        self.assertFalse(halb.unbestimmt)
        ende = p.setzen("angaben", 10, 10)
        self.assertEqual(40, ende.prozent, "Das Ende der Stufe ist der Anfang der naechsten: 5 + 35.")

    def test_vorige_stufen_zaehlen_als_erledigt_auch_wenn_sie_nie_gemeldet_wurden(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        self.assertEqual(80, p.setzen("einbauten", 0, 4).prozent)

    def test_der_balken_geht_nie_zurueck(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        p.setzen("bilder", 8, 10)
        zurueck = p.setzen("angaben", 1, 10)            # eine alte Stufe meldet sich spaet
        self.assertGreaterEqual(zurueck.prozent, 40 + 32 - 1)
        wieder = p.setzen("bilder", 2, 10)
        self.assertGreaterEqual(wieder.prozent, zurueck.prozent)

    def test_eine_wachsende_gesamtzahl_laesst_den_balken_nicht_zucken(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        erst = p.setzen("angaben", 5, 10).prozent
        dann = p.setzen("angaben", 5, 40).prozent       # es waren doch mehr Eintraege
        self.assertGreaterEqual(dann, erst)

    def test_ohne_gesamtzahl_ist_die_stufe_unbestimmt(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        for gesamt in (None, 0, -3):
            with self.subTest(gesamt=gesamt):
                stand = p.setzen("ordner", 7, gesamt)
                self.assertTrue(stand.unbestimmt)
                self.assertIsNone(stand.getan)
                self.assertIsNone(stand.gesamt)

    def test_zu_viel_getan_wird_auf_die_gesamtzahl_begrenzt(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        stand = p.setzen("angaben", 99, 10)
        self.assertEqual((10, 10), (stand.getan, stand.gesamt))
        stand = fs.Phasen(fs.PC_STUFEN).setzen("angaben", -5, 10)
        self.assertEqual(0, stand.getan)

    def test_vor_fertig_steht_der_balken_nie_auf_hundert(self) -> None:
        p = fs.Phasen(fs.PC_STUFEN)
        self.assertLess(p.setzen("einbauten", 10, 10).prozent, 100)
        self.assertEqual(100, p.fertig().prozent)

    def test_eine_unbekannte_stufe_faellt_auf(self) -> None:
        with self.assertRaises(ValueError):
            fs.Phasen(fs.PC_STUFEN).setzen("tippfehler", 1, 2)

    def test_falsche_gewichte_und_doppelte_namen_werden_abgelehnt(self) -> None:
        with self.assertRaises(ValueError):
            fs.Phasen([])
        with self.assertRaises(ValueError):
            fs.Phasen([("a", 1), ("a", 2)])
        with self.assertRaises(ValueError):
            fs.Phasen([("a", 0)])
        with self.assertRaises(ValueError):
            fs.Phasen([("a", -1), ("b", 2)])

    def test_die_gewichte_muessen_nicht_hundert_ergeben(self) -> None:
        p = fs.Phasen([("eins", 1), ("zwei", 3)])
        self.assertEqual(25, p.setzen("zwei", 0, 5).prozent)
        self.assertEqual(("eins", "zwei"), p.namen)

    def test_die_konsole_hat_ihre_eigenen_stufen(self) -> None:
        p = fs.Phasen(fs.PS5_STUFEN)
        self.assertEqual(10, p.setzen("ablagen", 0, 60).prozent)
        self.assertEqual(25, p.setzen("angaben", 0, 6).prozent)
        self.assertEqual(45, p.setzen("installiert", 0, 9).prozent)
        self.assertEqual(60, p.setzen("bilder", 0, 9).prozent)
        self.assertEqual(90, p.setzen("einbauten", 0, 9).prozent)


class DrosselTests(unittest.TestCase):

    def test_die_erste_meldung_kommt_durch_die_naechste_im_takt_nicht(self) -> None:
        zeit = [10.0]
        d = fs.Drossel(0.1, uhr=lambda: zeit[0])
        self.assertTrue(d.darf())
        zeit[0] += 0.05
        self.assertFalse(d.darf())
        zeit[0] += 0.06
        self.assertTrue(d.darf())

    def test_die_letzte_meldung_kommt_immer_durch(self) -> None:
        zeit = [0.0]
        d = fs.Drossel(5.0, uhr=lambda: zeit[0])
        self.assertTrue(d.darf())
        self.assertFalse(d.darf())
        self.assertTrue(d.darf(letzte=True))

    def test_mehrere_faeden_teilen_sich_einen_takt(self) -> None:
        d = fs.Drossel(60.0)
        durch: list[bool] = []
        sperre = threading.Lock()

        def lauf() -> None:
            ok = d.darf()
            with sperre:
                durch.append(ok)

        faeden = [threading.Thread(target=lauf) for _ in range(16)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join()
        self.assertEqual(1, sum(durch), "In einem Takt von 60 s darf genau ein Faden durch.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
