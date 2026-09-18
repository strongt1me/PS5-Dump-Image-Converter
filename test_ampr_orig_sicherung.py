# -*- coding: utf-8 -*-
"""Eine .orig-Sicherung ist nur, was vom Spiel stammt - kein frueherer Emulator.

Gemessen am 18.09.2026 an Ghost of Yotei: Der Quell-Dump trug in
fakelib/ schon den AMPR EMU aus einem Einbau vom 12.09. Beim naechsten Bau
wurde er als ``libSceAmpr.sprx.orig`` "gesichert" - im fertigen Abbild lag
danach eine .orig, byte-gleich mit dem Emulator daneben. "Zuruecksetzen"
haette den alten Emulator als Original des Spiels zurueckgelegt.

Betroffen waren zwei Stellen: ``_ampr_apply_library`` (Einbau beim Erstellen,
Aufgabe 7) und ``_ampr_gen_ablegen_mit_ergebnis`` (lokales Ablegen der
Fenster "AMPR EMU - alte/neue Methode"). Die Pruefungen laufen gegen die
echten Dateien im Bestand, nicht gegen Nachbildungen.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_orig_sicherung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import shadowmount_generation as sg  # noqa: E402

GUI = APP.PS5ConverterGUI
BESTAND = PROJEKT / "PlayGo & AMPR_EMU"
EMUS = sorted((BESTAND / "AMPR_EMU").rglob("libSceAmpr.sprx"))
STUBS = sorted(BESTAND.rglob("libScePlayGo.sprx"))
SONY = sorted((PROJEKT / "Backport_Fakelibs").rglob("*.sprx"))
EMU_PACK = BESTAND / "AMPR_EMU" / "0.4.2.1 test-pack" / "libSceAmpr.sprx"
EMU_DEBUG = BESTAND / "AMPR_EMU" / "0.4.2.1 test-debug-pack" / "libSceAmpr.sprx"


class KennzeichenAmBestandTests(unittest.TestCase):
    """Die Messung, auf der die Regel beruht - als Waechter.

    Kaeme eine Fassung ohne das Kennzeichen dazu, wuerde sie wieder als
    Original gesichert; faende sich das Kennzeichen in einer Sony-Bibliothek,
    ginge deren Sicherung verloren.
    """

    def test_der_bestand_ist_da(self) -> None:
        self.assertGreaterEqual(len(EMUS), 10, "Kaum AMPR-Fassungen gefunden")
        self.assertGreaterEqual(len(STUBS), 2, "PlayGo-Stubs fehlen")
        self.assertGreaterEqual(len(SONY), 10, "BACKPORT-Saetze fehlen")

    def test_jeder_emulator_und_jeder_stub_ist_ersatz(self) -> None:
        for datei in EMUS + STUBS:
            with self.subTest(datei=str(datei.relative_to(PROJEKT))):
                self.assertTrue(GUI._ist_ersatzbibliothek(datei))

    def test_keine_sony_bibliothek_ist_ersatz(self) -> None:
        for datei in SONY:
            with self.subTest(datei=str(datei.relative_to(PROJEKT))):
                self.assertFalse(GUI._ist_ersatzbibliothek(datei))

    def test_fehlende_datei_ist_kein_ersatz(self) -> None:
        self.assertFalse(GUI._ist_ersatzbibliothek(PROJEKT / "gibt_es_nicht.sprx"))


class _Ordner(unittest.TestCase):
    def setUp(self) -> None:
        self.basis = Path(tempfile.mkdtemp(prefix="ampr_orig_"))
        self.addCleanup(shutil.rmtree, self.basis, True)
        self.protokoll: list = []

    def _gui(self) -> GUI:
        gui = GUI.__new__(GUI)
        gui._t = lambda schluessel, **_w: schluessel
        gui._append_to_log = self.protokoll.append
        gui._ampr_ablage_pruefen = lambda _wurzel: []
        gui._load_setting = lambda _schluessel, vorgabe: vorgabe
        return gui


class EinbauSichertKeinenEmulatorTests(_Ordner):
    """``_ampr_apply_library`` - der Weg beim Erstellen und in Aufgabe 7."""

    def _spiel_mit(self, vorhanden: bytes | None) -> Path:
        spiel = self.basis / "spiel"
        (spiel / "fakelib").mkdir(parents=True)
        if vorhanden is not None:
            (spiel / "fakelib" / "libSceAmpr.sprx").write_bytes(vorhanden)
        return spiel

    def test_ein_frueherer_emulator_wird_nicht_als_original_gesichert(self) -> None:
        """Der Ghost-Fall: alter Emulator liegt schon da, neuer kommt drueber."""
        spiel = self._spiel_mit(EMU_PACK.read_bytes())
        self.assertTrue(self._gui()._ampr_apply_library(
            str(spiel), str(EMU_DEBUG), "libSceAmpr.sprx"))
        fakelib = spiel / "fakelib"
        self.assertFalse((fakelib / "libSceAmpr.sprx.orig").exists(),
                         "Der alte Emulator liegt als .orig da")
        self.assertEqual(EMU_DEBUG.read_bytes(),
                         (fakelib / "libSceAmpr.sprx").read_bytes())
        self.assertIn("log.manual.ampr_backup_ersatz", self.protokoll)

    def test_derselbe_emulator_noch_einmal(self) -> None:
        spiel = self._spiel_mit(EMU_PACK.read_bytes())
        self._gui()._ampr_apply_library(str(spiel), str(EMU_PACK), "libSceAmpr.sprx")
        self.assertFalse((spiel / "fakelib" / "libSceAmpr.sprx.orig").exists())

    def test_ein_frueherer_playgo_stub_ebenso(self) -> None:
        spiel = self.basis / "spiel"
        (spiel / "fakelib").mkdir(parents=True)
        (spiel / "fakelib" / "libScePlayGo.sprx").write_bytes(STUBS[0].read_bytes())
        self._gui()._ampr_apply_library(str(spiel), str(STUBS[-1]), "libScePlayGo.sprx")
        self.assertFalse((spiel / "fakelib" / "libScePlayGo.sprx.orig").exists())

    def test_ein_echtes_original_wird_weiter_gesichert(self) -> None:
        spiel = self._spiel_mit(b"\x7fELF-SONY-ORIGINAL")
        self._gui()._ampr_apply_library(str(spiel), str(EMU_PACK), "libSceAmpr.sprx")
        self.assertEqual(b"\x7fELF-SONY-ORIGINAL",
                         (spiel / "fakelib" / "libSceAmpr.sprx.orig").read_bytes())
        self.assertIn("log.manual.ampr_backup_created", self.protokoll)

    def test_ohne_vorhandene_datei_keine_sicherung(self) -> None:
        spiel = self._spiel_mit(None)
        self._gui()._ampr_apply_library(str(spiel), str(EMU_PACK), "libSceAmpr.sprx")
        self.assertFalse((spiel / "fakelib" / "libSceAmpr.sprx.orig").exists())

    def test_eine_vorhandene_sicherung_bleibt_unangetastet(self) -> None:
        spiel = self._spiel_mit(EMU_PACK.read_bytes())
        (spiel / "fakelib" / "libSceAmpr.sprx.orig").write_bytes(b"ALTE-SICHERUNG")
        self._gui()._ampr_apply_library(str(spiel), str(EMU_DEBUG), "libSceAmpr.sprx")
        self.assertEqual(b"ALTE-SICHERUNG",
                         (spiel / "fakelib" / "libSceAmpr.sprx.orig").read_bytes())


class AblegenSichertKeinenEmulatorTests(_Ordner):
    """``_ampr_gen_ablegen`` - die Fenster "alte/neue Methode", lokal."""

    def _ablegen(self, vorhanden: bytes) -> tuple[Path, list]:
        ziel = self.basis / "spiel" / "fakelib"
        ziel.mkdir(parents=True)
        (ziel / "libSceAmpr.sprx").write_bytes(vorhanden)
        zeilen = self._gui()._ampr_gen_ablegen(
            sg.NEU, sg.ORT_SPIEL, lokal=True, ziel=str(ziel),
            dateien=[str(EMU_DEBUG)])
        return ziel, zeilen

    def test_ein_frueherer_emulator_wird_nicht_gesichert(self) -> None:
        ziel, zeilen = self._ablegen(EMU_PACK.read_bytes())
        self.assertFalse((ziel / "libSceAmpr.sprx.orig").exists())
        self.assertIn("amprgen.keine_sicherung_ersatz", zeilen)
        self.assertEqual(EMU_DEBUG.read_bytes(), (ziel / "libSceAmpr.sprx").read_bytes())

    def test_ein_echtes_original_weiter_schon(self) -> None:
        ziel, _zeilen = self._ablegen(b"\x7fELF-SONY-ORIGINAL")
        self.assertEqual(b"\x7fELF-SONY-ORIGINAL",
                         (ziel / "libSceAmpr.sprx.orig").read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
