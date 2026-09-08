# -*- coding: utf-8 -*-
"""Prueft die Deckung eines Spiels gegen einen entpackten Firmware-Stand.

**Warum es diese Pruefung gibt.** Bis zum 07.09.2026 sagte das Programm vor
einem Backport nichts darueber, ob die Zielfirmware ueberhaupt liefert, was
das Spiel verlangt. Aufgefallen waere eine Luecke erst auf der Konsole - und
zwar ohne Meldung: Das Spiel startet dann einfach nicht.

**Warum auf NID-Ebene und nicht auf Bibliotheksebene.** Ein Vergleich ganzer
Bibliotheksnamen taugt dafuer nicht. Gemessen an zehn Dumps meldete er fuer
Firmware 12.00 dieselbe Liste wie fuer 7.01, obwohl ein SDK-10-Spiel auf
12.00 laeuft: Namen wie ``libScePosix`` oder ``libSceAudioOut2`` haben gar
keine eigene Datei, sie stecken in einem Nachbarmodul. Erst der Vergleich
einzelner Funktionen trennt echte Luecken von scheinbaren.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps5_backport as b  # noqa: E402


class FirmwareBestandErkennen(unittest.TestCase):
    """``ist_firmware_bestand`` und die Wahl des vollstaendigsten Standes."""

    def _stand(self, wurzel: Path, name: str, anzahl: int) -> Path:
        ordner = wurzel / name / "system" / "common" / "lib"
        ordner.mkdir(parents=True)
        for i in range(anzahl):
            (ordner / ("libSce%02d.sprx" % i)).write_bytes(b"\x7fELF" + b"\x00" * 60)
        return wurzel / name

    def test_leerer_ordner_ist_kein_bestand(self):
        with tempfile.TemporaryDirectory() as basis:
            self.assertFalse(b.ist_firmware_bestand(basis))
            self.assertFalse(b.ist_firmware_bestand(""))

    def test_ordner_ohne_module_ist_kein_bestand(self):
        with tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "system" / "common" / "lib").mkdir(parents=True)
            self.assertFalse(b.ist_firmware_bestand(basis),
                             "Ein leerer lib-Ordner ist noch kein Bestand")

    def test_bestand_wird_erkannt(self):
        with tempfile.TemporaryDirectory() as basis:
            stand = self._stand(Path(basis), "9.40", 3)
            self.assertTrue(b.ist_firmware_bestand(str(stand)))

    def test_vollstaendigster_stand_gewinnt(self):
        """Der duennere Stand meldete sonst reihenweise Falschbefunde.

        Echte Entpackungen sind unterschiedlich vollstaendig: 9.60 fuehrt
        273 Bibliotheken, 9.40 dagegen 543. Wer den duenneren nimmt, haelt
        vorhandene Funktionen faelschlich fuer fehlend.
        """
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            self._stand(wurzel, "9.00", 2)
            self._stand(wurzel, "9.40", 9)
            self._stand(wurzel, "9.60", 3)
            gewaehlt = b.firmware_ordner_fuer(str(wurzel), 9)
            self.assertEqual(os.path.basename(gewaehlt), "9.40")

    def test_falsche_hauptversion_wird_uebergangen(self):
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            self._stand(wurzel, "7.61", 5)
            self.assertEqual(b.firmware_ordner_fuer(str(wurzel), 9), "")
            self.assertTrue(b.firmware_ordner_fuer(str(wurzel), 7))

    def test_zehn_ist_nicht_eins(self):
        """``10.01`` darf nicht als Hauptversion 1 durchgehen."""
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            self._stand(wurzel, "10.01", 4)
            self.assertEqual(b.firmware_ordner_fuer(str(wurzel), 1), "")
            self.assertTrue(b.firmware_ordner_fuer(str(wurzel), 10))

    def test_fehlende_basis_ist_kein_fehler(self):
        self.assertEqual(b.firmware_ordner_fuer("", 9), "")
        self.assertEqual(b.firmware_ordner_fuer(r"X:\gibt-es-nicht", 9), "")


class DeckungOhneBestand(unittest.TestCase):
    """Ohne lesbaren Bestand darf nichts behauptet werden."""

    def test_leerer_bestand_meldet_nichts(self):
        with tempfile.TemporaryDirectory() as basis:
            ergebnis = b.firmware_deckung([], basis)
            self.assertEqual(ergebnis["bestand"], 0)
            self.assertEqual(ergebnis["fehlend"], {})
            self.assertEqual(ergebnis["verlangt"], 0)


class SdkTabelle(unittest.TestCase):
    """Die Firmware-Profile - Form und Grenzen."""

    def test_elf_bis_zwoelf_vorhanden(self):
        for stand in range(1, 13):
            self.assertIn(stand, b.SDK_PAARE)

    def test_hauptbyte_ist_bcd_firmware(self):
        """``0x11000043`` gehoert zu Firmware 11, nicht 17."""
        for stand, (ps5, _ps4) in b.SDK_PAARE.items():
            hoch = (ps5 >> 24) & 0xFF
            erwartet = int("%d" % stand, 16) if stand < 10 else int(str(stand), 16)
            self.assertEqual(hoch, erwartet,
                             "FW %d traegt 0x%02X im Hauptbyte" % (stand, hoch))

    def test_nebenversion_ist_null(self):
        """Alle Eintraege zielen auf x.00 - so wie die Vorlage es tut."""
        for stand, (ps5, _ps4) in b.SDK_PAARE.items():
            self.assertEqual((ps5 >> 16) & 0xFF, 0,
                             "FW %d hat eine Nebenversion != 00" % stand)

    def test_ps4_seite_steigt_streng(self):
        werte = [paar[1] for _s, paar in sorted(b.SDK_PAARE.items())]
        self.assertEqual(werte, sorted(werte),
                         "Die PS4-Partnerwerte muessen monoton steigen")

    def test_firmware_text(self):
        self.assertEqual(b.firmware_text(0x11000043), "11.00")
        self.assertEqual(b.firmware_text(0x07000038), "7.00")


class FakelibBestand(unittest.TestCase):
    """``firmwares_mit_bestand`` - die Auswahl folgt den Dateien."""

    def test_ohne_basis_leer(self):
        self.assertEqual(b.firmwares_mit_bestand(""), ())
        self.assertEqual(b.firmwares_mit_bestand(r"X:\gibt-es-nicht"), ())

    def test_selbst_ergaenzter_satz_zaehlt(self):
        """Der eigentliche Zweck: 8 und 10 ohne Codeaenderung waehlbar."""
        with tempfile.TemporaryDirectory() as basis:
            for stand in (4, 8, 10):
                ordner = Path(basis) / str(stand) / "fakelib"
                ordner.mkdir(parents=True)
                (ordner / "libSceAgc.sprx").write_bytes(b"\x7fELF")
            self.assertEqual(b.firmwares_mit_bestand(basis), (4, 8, 10))

    def test_ordner_ohne_bibliothek_zaehlt_nicht(self):
        with tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "9" / "fakelib").mkdir(parents=True)
            (Path(basis) / "9" / "fakelib" / "liesmich.txt").write_text("x")
            self.assertEqual(b.firmwares_mit_bestand(basis), ())

    def test_stand_ohne_sdk_paar_wird_uebergangen(self):
        """Ohne SDK-Paar liesse sich der Modulkopf nicht schreiben."""
        with tempfile.TemporaryDirectory() as basis:
            ordner = Path(basis) / "13" / "fakelib"
            ordner.mkdir(parents=True)
            (ordner / "libSceAgc.sprx").write_bytes(b"\x7fELF")
            self.assertNotIn(13, b.firmwares_mit_bestand(basis))


if __name__ == "__main__":
    unittest.main(verbosity=2)
