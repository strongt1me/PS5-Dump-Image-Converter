# -*- coding: utf-8 -*-
"""Tests der Bequemlichkeitsfunktionen des neutralen Bedienzustands.

Diese fuenf Funktionen (vier am Behaelter, eine am Schalter) sind die API
fuer eine zweite Oberflaeche: Die Tk-Fassung setzt ihre Werte einzeln und
kommt ohne sie aus. Beim Debuglauf am 20.09.2026 fiel auf, dass sie damit
weder gerufen NOCH geprueft waren - eine ungepruefte Zusage an die
naechste Oberflaeche. Genau die wird hier eingeloest.

Ohne Tk und ohne Programmfenster: Der Behaelter kennt keine Oberflaeche,
und das ist der Grund, warum es ihn gibt.
"""
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.ui import bedienzustand  # noqa: E402
from ps5_validator.ui.zustand import Schalter  # noqa: E402

UNBEKANNT = bedienzustand.UNBEKANNT


class MetadatenTests(unittest.TestCase):
    """Die dreizehn Angaben zum erkannten Spiel."""

    def setUp(self):
        self.zustand = bedienzustand.Bedienzustand()

    def test_lesen_liefert_alle_felder_als_text(self):
        gelesen = self.zustand.metadaten_lesen()
        self.assertEqual(set(gelesen), set(bedienzustand.METADATENFELDER))
        self.assertTrue(all(isinstance(wert, str) for wert in gelesen.values()))
        self.assertEqual(set(gelesen.values()), {UNBEKANNT})

    def test_lesen_zeigt_den_aktuellen_stand(self):
        # Keine Momentaufnahme von vorhin: Wer die Zuordnung zweimal holt,
        # muss beim zweiten Mal den neuen Wert sehen.
        self.zustand.metadaten["title"].set("Astro's Playroom")
        self.assertEqual(self.zustand.metadaten_lesen()["title"],
                         "Astro's Playroom")

    def test_lesen_gibt_eine_kopie(self):
        # Die Oberflaeche darf an der Zuordnung nichts verbiegen koennen.
        gelesen = self.zustand.metadaten_lesen()
        gelesen["title"] = "verbogen"
        self.assertEqual(self.zustand.metadaten["title"].get(), UNBEKANNT)

    def test_zuruecksetzen_leert_jedes_feld(self):
        for schluessel in bedienzustand.METADATENFELDER:
            self.zustand.metadaten[schluessel].set("vom vorigen Spiel")
        self.zustand.metadaten_zuruecksetzen()
        self.assertEqual(set(self.zustand.metadaten_lesen().values()), {UNBEKANNT})

    def test_zuruecksetzen_meldet_die_aenderung(self):
        # Ohne Meldung erfaehrt eine WPF-Ansicht nichts davon und zeigt
        # weiter die Angaben des vorigen Spiels.
        gesehen = []
        self.zustand.metadaten["title"].beobachten(
            lambda _alt, neu: gesehen.append(neu))
        self.zustand.metadaten["title"].set("Spiel A")
        self.zustand.metadaten_zuruecksetzen()
        self.assertEqual(gesehen, ["Spiel A", UNBEKANNT])


class KerngrenzeTests(unittest.TestCase):
    """Die Obergrenze der Arbeitsvorgaenge steht erst zur Laufzeit fest."""

    def test_grenze_wird_nachgezogen(self):
        zustand = bedienzustand.Bedienzustand(kerne=8)
        zustand.kerngrenze_setzen(16)
        self.assertEqual(zustand.worker_count_var.groesster, 16)
        self.assertEqual(zustand.worker_count_var.kleinster, 1)

    def test_ein_zu_hoher_wert_wird_hereingezogen(self):
        zustand = bedienzustand.Bedienzustand(kerne=32)
        zustand.worker_count_var.set(24)
        zustand.kerngrenze_setzen(4)
        self.assertEqual(zustand.worker_count_var.get(), 4)

    def test_null_kerne_lassen_einen_vorgang_uebrig(self):
        # Die Kernzahl kommt aus os.cpu_count() und kann None oder 0 sein.
        # Eine Obergrenze 0 wuerde jeden Lauf unmoeglich machen.
        zustand = bedienzustand.Bedienzustand(kerne=8)
        zustand.kerngrenze_setzen(0)
        self.assertEqual(zustand.worker_count_var.get(), 1)
        self.assertEqual(zustand.worker_count_var.groesster, 1)


class NeuerLaufTests(unittest.TestCase):
    """Was zu einem einzelnen Durchlauf gehoert - und was stehen bleibt."""

    def setUp(self):
        self.zustand = bedienzustand.Bedienzustand(
            zielpfad=r"E:\Ziel", temp_pfad=r"E:\Temp", packstufe="6")
        self.zustand.progress_var.set(73.5)
        for name in ("_info_src_size_var", "_info_est_size_var",
                     "_info_format_var", "_info_method_var"):
            getattr(self.zustand, name).set("vom vorigen Lauf")

    def test_fortschritt_und_angaben_stehen_auf_anfang(self):
        self.zustand.zuruecksetzen_fuer_neuen_lauf()
        self.assertEqual(self.zustand.progress_var.get(), 0.0)
        for name in ("_info_src_size_var", "_info_est_size_var",
                     "_info_format_var", "_info_method_var"):
            self.assertEqual(getattr(self.zustand, name).get(), UNBEKANNT, name)

    def test_quelle_ziel_und_einstellungen_bleiben(self):
        # Wer zweimal hintereinander umwandelt, will sie nicht neu setzen.
        self.zustand.source_path.set(r"D:\Dump")
        self.zustand.zuruecksetzen_fuer_neuen_lauf()
        self.assertEqual(self.zustand.source_path.get(), r"D:\Dump")
        self.assertEqual(self.zustand.dest_path.get(), r"E:\Ziel")
        self.assertEqual(self.zustand.temp_path.get(), r"E:\Temp")
        self.assertEqual(self.zustand.compression_level_var.get(), "6")

    def test_die_angaben_zum_spiel_bleiben_ebenfalls(self):
        # Das Spiel wechselt nicht, weil ein neuer Lauf beginnt - dafuer
        # gibt es metadaten_zuruecksetzen.
        self.zustand.metadaten["title"].set("Astro's Playroom")
        self.zustand.zuruecksetzen_fuer_neuen_lauf()
        self.assertEqual(self.zustand.metadaten["title"].get(),
                         "Astro's Playroom")


class UmlegenTests(unittest.TestCase):
    """Der Schalter kippt sich selbst, statt ``set(not get())``."""

    def test_umlegen_liefert_den_neuen_stand(self):
        schalter = Schalter(False, "Probe")
        self.assertTrue(schalter.umlegen())
        self.assertTrue(schalter.get())
        self.assertFalse(schalter.umlegen())
        self.assertFalse(schalter.get())

    def test_umlegen_meldet_jede_aenderung(self):
        schalter = Schalter(False, "Probe")
        gesehen = []
        schalter.beobachten(lambda _alt, neu: gesehen.append(neu))
        schalter.umlegen()
        schalter.umlegen()
        self.assertEqual(gesehen, [True, False])

    def test_zwei_faeden_verschlucken_keine_umschaltung(self):
        # Der Grund fuer die Methode: ``set(not get())`` aus zwei Faeden
        # kann eine Umschaltung verlieren. Gerade Anzahl -> Anfangsstand.
        import threading

        schalter = Schalter(False, "Probe")
        laeufe = 200

        def _kippen():
            for _ in range(laeufe):
                schalter.umlegen()

        faeden = [threading.Thread(target=_kippen) for _ in range(2)]
        for faden in faeden:
            faden.start()
        for faden in faeden:
            faden.join()
        self.assertFalse(schalter.get(),
                         "2 x %d Umschaltungen muessen sich aufheben" % laeufe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
