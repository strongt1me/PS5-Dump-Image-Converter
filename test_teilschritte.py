# -*- coding: utf-8 -*-
"""Teilschritte der Fortschrittsanzeige (Nutzer 06.10.2026: "man hat das Gefuehl, das Programm ist eingefroren").

Lange Schritte zeigen in der Statuszeile ihre Laufzeit, mit Mengenangabe Prozent und Restzeit, und schreiben
Beginn, je 10 % einen Stand und das Ende ins Statusprotokoll. Kurze Schritte (< 2 s) bleiben still.
Die Uhr ist nachgestellt - kein Test wartet echt.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

TEXTE = {"seit": STRINGS["progress.teil_seit"]["de"],
         "prozent": STRINGS["progress.teil_prozent"]["de"],
         "prozent_ohne_rest": STRINGS["progress.teil_prozent_ohne_rest"]["de"]}


class _Uhr:
    def __init__(self) -> None:
        self.jetzt = 1000.0

    def __call__(self) -> float:
        return self.jetzt


class TeilschrittTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uhr = _Uhr()
        flicken = mock.patch.object(APP.time, "monotonic", self.uhr)
        flicken.start()
        self.addCleanup(flicken.stop)
        self.engine = APP.ProgressEngine(fertig_text="fertig", teil_texte=TEXTE)
        self.engine.start_task(0, "Aufgabe")

    def _status(self) -> str:
        return self.engine.tick()[1]

    def test_kurz_ohne_uhr_und_ohne_dauer_aber_im_protokoll(self) -> None:
        """Jeder Schritt steht im Protokoll; Laufzeit und Dauer nur bei langen."""
        self.engine.begin_validate("Abschluss...")
        self.uhr.jetzt += 1.0
        self.assertEqual("Abschluss...", self._status())
        self.engine.teilschritt_ende()
        self.assertEqual([("start", {"text": "Abschluss"})], self.engine.ereignisse_holen())

    def test_ohne_menge_laeuft_die_uhr(self) -> None:
        self.engine.begin_validate("UFS2-Struktur prüfen...")
        self.uhr.jetzt += 83
        self.assertEqual("UFS2-Struktur prüfen – läuft seit 1:23", self._status())

    def test_mit_menge_prozent_und_restzeit(self) -> None:
        self.engine.teilschritt("Prüfsumme bilden")
        self.uhr.jetzt += 30
        self.engine.teilschritt_stand(25, 100)
        self.assertEqual("Prüfsumme bilden – 25 % · noch ca. 1:30", self._status())

    def test_restzeit_erst_nach_anlauf(self) -> None:
        self.engine.teilschritt("Kopieren")
        self.uhr.jetzt += 2.5
        self.engine.teilschritt_stand(50, 100)
        self.assertEqual("Kopieren – 50 %", self._status())

    def test_protokoll_beginn_staende_ende(self) -> None:
        self.engine.teilschritt("Übertragen")
        for prozent in range(5, 101, 5):
            self.uhr.jetzt += 10
            self.engine.teilschritt_stand(prozent, 100)
        self.engine.teilschritt_ende()
        arten = [art for art, _w in self.engine.ereignisse_holen()]
        self.assertEqual("start", arten[0])
        self.assertEqual("ende", arten[-1])
        self.assertEqual(9, arten.count("stand"), "je 10 % eine Zeile (10..90)")

    def test_langer_schritt_ohne_menge_meldet_beginn_und_ende(self) -> None:
        self.engine.begin_validate("fsck")
        self.uhr.jetzt += 5
        self.assertEqual([("start", {"text": "fsck"})], self.engine.ereignisse_holen())
        self.engine.begin_validate("Abschluss")
        ende = self.engine.ereignisse_holen()
        self.assertEqual(["ende", "start"], [a for a, _w in ende])
        self.assertAlmostEqual(5.0, ende[0][1]["dauer"])

    def test_die_datenphase_steht_im_protokoll(self) -> None:
        self.engine.begin_payload(100, "Packe Dateien...")
        self.assertIn(("start", {"text": "Packe Dateien"}), self.engine.ereignisse_holen())

    def test_neuer_schritt_beendet_den_alten(self) -> None:
        self.engine.teilschritt("A")
        self.uhr.jetzt += 3
        self.engine.teilschritt("B")
        self.assertEqual([("start", "A"), ("ende", "A"), ("start", "B")],
                         [(a, w["text"]) for a, w in self.engine.ereignisse_holen()])
        self.assertEqual("B", self.engine.status)

    def test_dauertext(self) -> None:
        self.assertEqual("0:05", APP.ProgressEngine.dauer_text(5))
        self.assertEqual("12:00", APP.ProgressEngine.dauer_text(720))
        self.assertEqual("1:02:05", APP.ProgressEngine.dauer_text(3725))

    def test_ohne_vorlagen_unveraendert(self) -> None:
        engine = APP.ProgressEngine()
        engine.start_task(0, "x")
        engine.teilschritt("Schritt")
        self.uhr.jetzt += 10
        self.assertEqual("Schritt", engine.tick()[1])


class ProgrammTests(unittest.TestCase):
    def test_protokollzeilen_uebersetzt(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        zeilen = []
        gui._append_to_log = zeilen.append
        gui.progress_engine = mock.Mock()
        gui.progress_engine.ereignisse_holen.return_value = [
            ("start", {"text": "Übertragen"}),
            ("stand", {"text": "Übertragen", "prozent": 40, "rest": 90.0}),
            ("stand", {"text": "Übertragen", "prozent": 50, "rest": None}),
            ("ende", {"text": "Übertragen", "dauer": 125.0})]
        gui._teil_ereignisse_protokollieren()
        self.assertEqual(["[…] Übertragen …\n", "[…] Übertragen: 40 % · noch ca. 1:30\n",
                          "[…] Übertragen: 50 %\n", "[Info] Übertragen – beendet nach 2:05\n"], zeilen)

    def test_statuszeile_im_lauf_ins_protokoll_ohne_zahlenwiederholung(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        gui.root = None
        gui.is_running = True
        zeilen = []
        gui._append_to_log = zeilen.append
        gui._set_status("Arbeitskopie anlegen...  1,2 GB / 47,8 GB")
        gui._set_status("Arbeitskopie anlegen...  3,4 GB / 47,8 GB")
        gui._set_status("Prüfe UFS2-Struktur...")
        self.assertEqual(["[…] Arbeitskopie anlegen...  1,2 GB / 47,8 GB\n", "[…] Prüfe UFS2-Struktur...\n"],
                         zeilen)

    def test_statuszeile_ausserhalb_eines_laufs_nicht(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        gui.root = None
        gui.is_running = False
        zeilen = []
        gui._append_to_log = zeilen.append
        gui._set_status("Bereit.")
        self.assertEqual([], zeilen)

    def test_ohne_fortschrittssteuerung_still(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._teil_melden("teilschritt", "x")          # darf nicht werfen

    def test_die_ffpkg_pruefungen_melden_ihren_stand(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertEqual(2, quelle.count("abbruch=lambda: not self.is_running, fortschritt="))
        for schluessel in ("progress.teil.dateizahl", "progress.teil.pruefsumme_staging",
                           "progress.teil.uebertragen", "progress.teil.pruefsumme_ziel"):
            self.assertIn('self._teil_melden("teilschritt", self._t("%s"))' % schluessel, quelle)


if __name__ == "__main__":
    unittest.main()
