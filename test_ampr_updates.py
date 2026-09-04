# -*- coding: utf-8 -*-
"""Neuere AMPR-EMU-Fassungen holen - ohne Netz geprueft.

Das Holen wird als Rueckruf hereingereicht, nicht fest eingebaut. Deshalb
laesst sich jede Regel hier mit einer Nachbildung messen: Was als neuer gilt,
wohin es gehoert, was bei einem halben Download passiert.

Die Antwort der Schnittstelle ist echt - am 04.09.2026 von
``api.github.com/repos/drakmor/ampr_emu/releases`` abgelesen und hier
gekuerzt hinterlegt. Eine erfundene Antwort haette die Eigenheit nicht
getroffen, um die es geht: **Unter der Marke 0.3.6 haengen Anhaenge bis
0.3.6.4.** Wer die Marke liest statt den Anhangsnamen, uebersieht sie.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ampr_updates as au  # noqa: E402


#: Gekuerzte, aber echte Antwort - Aufbau und Namen unveraendert.
ANTWORT = json.dumps([
    {"tag_name": "0.3.6.6", "name": "AMPR Emu 0.3.6.6", "assets": [
        {"name": "libSceAmpr.sprx-0.3.6.6-test", "size": 255126,
         "browser_download_url": "https://example.invalid/0366"},
        {"name": "libSceAmpr.sprx-0.3.6.6-test-debug", "size": 414614,
         "browser_download_url": "https://example.invalid/0366d"},
    ]},
    {"tag_name": "0.3.6", "name": "AMPR Emu 0.3.6 / 0.3.6.1-3", "assets": [
        {"name": "libSceAmpr.sprx-0.3.6-test", "size": 220630,
         "browser_download_url": "https://example.invalid/036"},
        {"name": "libSceAmpr.sprx-0.3.6.4-test", "size": 236278,
         "browser_download_url": "https://example.invalid/0364"},
        {"name": "libSceAmpr.sprx-0.3.6.4-test-debug", "size": 389734,
         "browser_download_url": "https://example.invalid/0364d"},
        {"name": "Quelltext.zip", "size": 999,
         "browser_download_url": "https://example.invalid/zip"},
    ]},
])


class LesenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.angebote = au.angebote_lesen(ANTWORT)

    def test_fremde_anhaenge_bleiben_draussen(self) -> None:
        """Quelltextarchive und Lesetexte sind keine Bibliotheken."""
        namen = [a.anhang for a in self.angebote]
        self.assertNotIn("Quelltext.zip", namen)

    def test_die_fassung_kommt_aus_dem_anhang_nicht_aus_der_marke(self) -> None:
        """Der Kern: Unter der Marke 0.3.6 haengt eine 0.3.6.4.

        Wer die Marke liest, findet 0.3.6.4 nie - und bietet dem Anwender
        eine Fassung nicht an, die es gibt.
        """
        fassungen = {a.fassung for a in self.angebote}
        self.assertIn("0.3.6.4", fassungen)
        self.assertIn("0.3.6.6", fassungen)

    def test_variante_wird_am_namen_erkannt(self) -> None:
        debug = {a.fassung for a in self.angebote if a.variante == au.DEBUG}
        still = {a.fassung for a in self.angebote if a.variante == au.OHNE_DEBUG}
        self.assertIn("0.3.6.6", debug)
        self.assertIn("0.3.6.6", still)
        self.assertIn("0.3.6", still)
        self.assertNotIn("0.3.6", debug)

    def test_neueste_steht_oben(self) -> None:
        self.assertEqual("0.3.6.6", self.angebote[0].fassung)

    def test_beschriftung_passt_zum_bestand(self) -> None:
        """Sie muss aussehen wie ein Ordner im mitgelieferten Speicher."""
        a = next(x for x in self.angebote
                 if x.fassung == "0.3.6.6" and x.variante == au.OHNE_DEBUG)
        self.assertEqual("0.3.6.6 no debug", a.beschriftung)

    def test_unbrauchbare_antwort_wirft_nicht(self) -> None:
        for text in ("", "kein json", "[]", "null", '{"assets": null}'):
            self.assertEqual([], au.angebote_lesen(text), text)


class FassungsvergleichTests(unittest.TestCase):
    def test_zahlenweise_nicht_alphabetisch(self) -> None:
        """0.3.6.10 ist neuer als 0.3.6.9 - alphabetisch stuende es davor."""
        self.assertGreater(au.fassung_teile("0.3.6.10"), au.fassung_teile("0.3.6.9"))

    def test_unbrauchbares_gibt_leer(self) -> None:
        for text in ("", "keine Zahl", None):
            self.assertEqual((), au.fassung_teile(text))

    def test_nur_echt_neueres_wird_angeboten(self) -> None:
        angebote = au.angebote_lesen(ANTWORT)
        neu = au.neuere(angebote, ["0.3.6.2", "0.3.5.1", "0.3.4"])
        fassungen = {a.fassung for a in neu}
        self.assertEqual({"0.3.6.4", "0.3.6.6"}, fassungen)

    def test_gegen_die_hoechste_verglichen_nicht_gegen_jede(self) -> None:
        """Eine Fassung zwischen zwei vorhandenen ist nichts Neues."""
        angebote = au.angebote_lesen(ANTWORT)
        neu = au.neuere(angebote, ["0.3.6.6"])
        self.assertEqual([], neu)

    def test_leerer_bestand_macht_alles_neu(self) -> None:
        angebote = au.angebote_lesen(ANTWORT)
        self.assertEqual(len(angebote), len(au.neuere(angebote, [])))


class AblageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ampr_upd_")
        self.wurzel = self._tmp.name
        self.angebot = au.Angebot("0.3.6.6", au.OHNE_DEBUG,
                                  "libSceAmpr.sprx-0.3.6.6-test",
                                  "https://example.invalid/0366", 10)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_der_aufbau_passt_zum_mitgelieferten_speicher(self) -> None:
        """Nur so findet der vorhandene Scanner die geholte Fassung."""
        pfad = au.zielpfad(self.wurzel, "0.3.6.6", au.OHNE_DEBUG)
        self.assertEqual(
            os.path.join(self.wurzel, "AMPR_EMU", "0.3.6.6 no debug",
                         "libSceAmpr.sprx"),
            pfad)

    def test_ablegen_schreibt_die_datei(self) -> None:
        ziel = au.ablegen(self.wurzel, self.angebot, b"0123456789")
        self.assertTrue(os.path.isfile(ziel))
        self.assertEqual(b"0123456789", Path(ziel).read_bytes())

    def test_halber_download_wird_abgelehnt(self) -> None:
        """Sonst boete der Scanner eine kaputte Bibliothek als Fassung an."""
        with self.assertRaises(ValueError):
            au.ablegen(self.wurzel, self.angebot, b"012")
        self.assertFalse(os.path.isfile(
            au.zielpfad(self.wurzel, "0.3.6.6", au.OHNE_DEBUG)))

    def test_leerer_inhalt_wird_abgelehnt(self) -> None:
        with self.assertRaises(ValueError):
            au.ablegen(self.wurzel, self.angebot, b"")

    def test_keine_teildatei_bleibt_liegen(self) -> None:
        try:
            au.ablegen(self.wurzel, self.angebot, b"012")
        except ValueError:
            pass
        reste = list(Path(self.wurzel).rglob("*.teil"))
        self.assertEqual([], reste, "Teildatei uebrig: %s" % reste)

    def test_schon_da_erkennt_die_abgelegte(self) -> None:
        self.assertFalse(au.schon_da(self.wurzel, self.angebot))
        au.ablegen(self.wurzel, self.angebot, b"0123456789")
        self.assertTrue(au.schon_da(self.wurzel, self.angebot))


class HolenTests(unittest.TestCase):
    """Das Netz ist eine Nachbildung - geprueft wird das Verhalten drumherum."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ampr_hol_")
        self.wurzel = self._tmp.name
        self.angebote = au.neuere(au.angebote_lesen(ANTWORT), ["0.3.6.2"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_alle_werden_abgelegt(self) -> None:
        abgelegt, fehler = au.holen(
            self.wurzel, self.angebote, lambda _a: b"x" * 500000)
        self.assertEqual([], fehler)
        self.assertEqual(len(self.angebote), len(abgelegt))
        for pfad in abgelegt:
            self.assertTrue(os.path.isfile(pfad))

    def test_ein_fehlschlag_haelt_die_uebrigen_nicht_auf(self) -> None:
        """Wer drei holt und bei einem scheitert, behaelt die anderen zwei."""
        def lade(adresse):
            if adresse.endswith("0364"):
                raise OSError("Verbindung abgebrochen")
            return b"x" * 500000

        abgelegt, fehler = au.holen(self.wurzel, self.angebote, lade)
        self.assertEqual(1, len(fehler))
        self.assertEqual(len(self.angebote) - 1, len(abgelegt))
        self.assertIn("Verbindung abgebrochen", fehler[0])

    def test_das_modul_geht_von_selbst_nie_ins_netz(self) -> None:
        """Netzzugriff nur auf Knopfdruck - die Regel seit v1.8.74.

        Geprueft am Quelltext: Das Modul darf nichts importieren oder rufen,
        was von sich aus eine Verbindung aufbaut. Das Holen kommt als
        Rueckruf herein.
        """
        quelle = Path(au.__file__).read_text(encoding="utf-8")
        for verboten in ("urlopen", "urllib.request", "requests.", "socket.",
                         "http.client"):
            self.assertNotIn(verboten, quelle,
                             "%s steht im Modul - es koennte von selbst laden"
                             % verboten)


if __name__ == "__main__":
    unittest.main(verbosity=2)
