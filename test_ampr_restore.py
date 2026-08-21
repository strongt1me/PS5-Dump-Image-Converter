"""Regressionstest: „nichts wiederherzustellen" ist kein Fehlschlag.

Gefunden beim Durchtesten aller Aufgaben: `--ampr-action ampr_restore` endete
mit Exit-Code 1 und der Meldung „Keine Sicherung für libSceAmpr.sprx vorhanden".
Das war der erwartete Zustand – das Spiel brachte die Bibliothek nie selbst mit,
also legte `ampr_apply` sie neu an und es gab nichts zu sichern.

Der ps5-exfat-builder löst dieselbe Frage anders: Er sichert die Originale vorab
in ein ZIP; wählt man beim Wiederherstellen keins aus, passiert schlicht nichts –
ohne Fehlermeldung.

`_ampr_restore_library` unterscheidet deshalb drei Ausgänge:
`restored`, `no_backup` (kein Fehler) und `failed` (echter Fehler).
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI


def _gui(fakelib_ordner: str = "fakelib") -> PS5ConverterGUI:
    """Baut eine Prueflings-Instanz mit festgelegtem Bibliotheksordner.

    Wichtig: ``_load_setting`` wird abgefangen. Ohne diesen Stub laesst
    ``_fakelib_ordnername()`` die echte paths.json des Nutzers lesen - stand dort
    "fakelib2", suchte der Test seine Sicherung im falschen Ordner und meldete
    "no_backup". Ein Test darf nicht davon abhaengen, was der Nutzer eingestellt
    hat.
    """
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._append_to_log = lambda *_a, **_k: None
    gui._t = lambda schluessel, **kw: schluessel
    gui._load_setting = lambda schluessel, vorgabe: (
        fakelib_ordner if schluessel == "fakelib_variante" else vorgabe)
    return gui


class AmprWiederherstellenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ampr_restore_")
        self.wurzel = Path(self._tmp.name)
        self.fakelib = self.wurzel / "fakelib"
        self.fakelib.mkdir()
        self.gui = _gui()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ohne_sicherung_kein_fehler(self):
        (self.fakelib / "libSceAmpr.sprx").write_bytes(b"AMPR")
        self.assertEqual(
            self.gui._ampr_restore_library(str(self.wurzel), "libSceAmpr.sprx"),
            "no_backup",
        )

    def test_mit_sicherung_wird_zurueckgespielt(self):
        ziel = self.fakelib / "libSceAmpr.sprx"
        ziel.write_bytes(b"AMPR-EMU")
        (self.fakelib / "libSceAmpr.sprx.orig").write_bytes(b"ORIGINAL")
        self.assertEqual(
            self.gui._ampr_restore_library(str(self.wurzel), "libSceAmpr.sprx"),
            "restored",
        )
        self.assertEqual(ziel.read_bytes(), b"ORIGINAL")
        self.assertFalse((self.fakelib / "libSceAmpr.sprx.orig").exists(),
                         "die verbrauchte Sicherung muss verschwinden")

    def test_schreibgeschuetzte_zieldatei_wird_ueberschrieben(self):
        ziel = self.fakelib / "libSceAmpr.sprx"
        ziel.write_bytes(b"AMPR-EMU")
        (self.fakelib / "libSceAmpr.sprx.orig").write_bytes(b"ORIGINAL")
        os.chmod(ziel, stat.S_IREAD)
        try:
            self.assertEqual(
                self.gui._ampr_restore_library(str(self.wurzel), "libSceAmpr.sprx"),
                "restored",
            )
        finally:
            os.chmod(ziel, stat.S_IWRITE | stat.S_IREAD)

    def test_echter_fehler_bleibt_ein_fehler(self):
        """Sicherung vorhanden, Zurückspielen scheitert – das muss FAILED bleiben."""
        import shutil as _shutil

        (self.fakelib / "libSceAmpr.sprx").write_bytes(b"AMPR-EMU")
        (self.fakelib / "libSceAmpr.sprx.orig").write_bytes(b"ORIGINAL")

        original_copy2 = _shutil.copy2

        def _kracht(*_args, **_kwargs):
            raise OSError("Datenträger schreibgeschützt")

        _shutil.copy2 = _kracht
        try:
            self.assertEqual(
                self.gui._ampr_restore_library(str(self.wurzel), "libSceAmpr.sprx"),
                "failed",
            )
        finally:
            _shutil.copy2 = original_copy2
        self.assertTrue((self.fakelib / "libSceAmpr.sprx.orig").exists(),
                        "nach einem Fehlschlag muss die Sicherung erhalten bleiben")

    def test_die_drei_ausgaenge_sind_unterscheidbar(self):
        """Ohne die Unterscheidung wäre 'nichts zu tun' wieder ein Fehlschlag."""
        ausgaenge = set()
        (self.fakelib / "a.sprx").write_bytes(b"x")
        ausgaenge.add(self.gui._ampr_restore_library(str(self.wurzel), "a.sprx"))
        (self.fakelib / "b.sprx.orig").write_bytes(b"y")
        ausgaenge.add(self.gui._ampr_restore_library(str(self.wurzel), "b.sprx"))
        self.assertEqual(ausgaenge, {"no_backup", "restored"})


class AmprWiederherstellenMitFakelib2Tests(unittest.TestCase):
    """Derselbe Ablauf, wenn fakelib2 gewaehlt ist.

    ShadowMount+ haengt nur einen der beiden Ordner ein und bevorzugt fakelib2;
    der AMPR EMU Manager muss deshalb in beiden Ordnern zuhause sein.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ampr_restore2_")
        self.wurzel = Path(self._tmp.name)
        self.fakelib = self.wurzel / "fakelib2"
        self.fakelib.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_sicherung_wird_auch_aus_fakelib2_zurueckgespielt(self) -> None:
        ziel = self.fakelib / "libSceAmpr.sprx"
        ziel.write_bytes(b"AMPR-EMU")
        (self.fakelib / "libSceAmpr.sprx.orig").write_bytes(b"ORIGINAL")
        gui = _gui("fakelib2")
        ergebnis = PS5ConverterGUI._ampr_restore_library(
            gui, str(self.wurzel), "libSceAmpr.sprx")
        self.assertEqual(ergebnis, "restored")
        self.assertEqual(ziel.read_bytes(), b"ORIGINAL")

    def test_der_andere_ordner_wird_nicht_angefasst(self) -> None:
        """Liegt daneben ein fakelib, darf die Wahl fakelib2 es ignorieren."""
        alt = self.wurzel / "fakelib"
        alt.mkdir()
        (alt / "libSceAmpr.sprx").write_bytes(b"FALSCH")
        (alt / "libSceAmpr.sprx.orig").write_bytes(b"FALSCH-ORIG")
        (self.fakelib / "libSceAmpr.sprx").write_bytes(b"AMPR-EMU")
        (self.fakelib / "libSceAmpr.sprx.orig").write_bytes(b"ORIGINAL")
        gui = _gui("fakelib2")
        PS5ConverterGUI._ampr_restore_library(gui, str(self.wurzel), "libSceAmpr.sprx")
        self.assertEqual((self.fakelib / "libSceAmpr.sprx").read_bytes(), b"ORIGINAL")
        self.assertEqual((alt / "libSceAmpr.sprx").read_bytes(), b"FALSCH")


if __name__ == "__main__":
    unittest.main(verbosity=2)
