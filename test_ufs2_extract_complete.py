"""Regressionstest: Vollstaendigkeit der .ffpkg-Extraktion (Aufgabe 4 -> Dump-Ordner).

Gefunden beim Durchtesten mit echten Backups: Aus einer .ffpkg mit 196 Dateien
kamen 195 heraus. Es fehlte `sce_sys/about/right.sprx` - eine Datei, die in
allen 32 Dump-Ordnern der Sammlung vorkommt.

Ursache war nicht das Bauen (die .ffpkg enthielt den Eintrag nachweislich),
sondern das Extrahieren: robocopy lief mit `/MT:8 /R:1 /W:1` gegen einen
Dokan-Mount, der unter Last `ERROR_NO_SYSTEM_RESOURCES` (0x5AA) lieferte. Bei
nur einem Wiederholungsversuch gab robocopy ein ganzes Verzeichnis auf und
meldete das lediglich als `rc=9` - ohne zu sagen, was fehlt.

Behoben durch: weniger Parallelitaet, mehr Wiederholungen, und vor allem einen
Abgleich gegen die Soll-Liste des gemounteten Abbilds statt blindem Vertrauen
in den Rueckgabewert.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _funktionsblock(quelltext: str, name: str) -> str:
    """Schneidet den Rumpf einer Methode aus dem Quelltext heraus."""
    start = quelltext.index(f"def {name}(")
    rest = quelltext[start:]
    treffer = re.search(r"\n    def \w+\(", rest[10:])
    return rest[: treffer.start() + 10] if treffer else rest


class SollAbgleichTests(unittest.TestCase):
    """Die Vergleichsregel selbst - ohne Mount, ohne Oberflaeche."""

    @classmethod
    def setUpClass(cls) -> None:
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        # Ueber die Klasse aufrufen: als Klassenattribut abgelegt wuerde die
        # Funktion beim Zugriff ueber self erneut gebunden.
        cls.GUI = PS5ConverterGUI

    def fehlende(self, dest_folder: str, soll: dict[str, int]) -> list[str]:
        return self.GUI._fehlende_zieldateien(dest_folder, soll)

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ufs2_soll_")
        self.ziel = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _anlegen(self, rel_path: str, groesse: int) -> None:
        voll = os.path.join(self.ziel, rel_path)
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(b"\x00" * groesse)

    def test_vollstaendiges_ergebnis_meldet_nichts(self):
        soll = {"eboot.bin": 10, "sce_sys/param.json": 20}
        for pfad, groesse in soll.items():
            self._anlegen(pfad, groesse)
        self.assertEqual(self.fehlende(self.ziel, soll), [])

    def test_fehlende_datei_wird_erkannt(self):
        soll = {"eboot.bin": 10, "sce_sys/about/right.sprx": 12768}
        self._anlegen("eboot.bin", 10)
        self.assertEqual(self.fehlende(self.ziel, soll), ["sce_sys/about/right.sprx"])

    def test_leeres_verzeichnis_rettet_die_datei_nicht(self):
        """Genau der Fehlerfall: das Verzeichnis entsteht, die Datei fehlt."""
        soll = {"sce_sys/about/right.sprx": 12768}
        os.makedirs(os.path.join(self.ziel, "sce_sys", "about"), exist_ok=True)
        self.assertEqual(self.fehlende(self.ziel, soll), ["sce_sys/about/right.sprx"])

    def test_abgebrochene_datei_gilt_als_fehlend(self):
        soll = {"Media/level27": 216_000_000}
        self._anlegen("Media/level27", 1024)
        self.assertEqual(self.fehlende(self.ziel, soll), ["Media/level27"])

    def test_mehrere_fehlende_kommen_sortiert(self):
        soll = {"z.bin": 1, "a.bin": 1, "m.bin": 1}
        self.assertEqual(self.fehlende(self.ziel, soll), ["a.bin", "m.bin", "z.bin"])

    def test_leere_sollliste_ist_kein_fehler(self):
        self.assertEqual(self.fehlende(self.ziel, {}), [])


class RobocopyAufrufTests(unittest.TestCase):
    """Die Parameter, mit denen der Dokan-Mount ausgelesen wird."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = QUELLDATEI.read_text(encoding="utf-8")
        cls.block = _funktionsblock(cls.quelltext, "_extract_ffpkg_to_folder_via_ufs2tool")

    def test_weniger_parallelitaet_auf_dem_dokan_mount(self):
        self.assertIn('"/MT:4"', self.block)
        self.assertNotIn('"/MT:8"', self.block)

    def test_mehr_wiederholungen_als_eine(self):
        self.assertIn('"/R:3"', self.block)
        self.assertNotIn('"/R:1"', self.block)

    def test_teilfehler_bricht_nicht_mehr_sofort_ab(self):
        """rc 8..15 heisst 'einzelnes misslang' - das entscheidet der Abgleich."""
        self.assertIn("rc >= 16", self.block)
        self.assertIn("ufs2_extract.robocopy_partial", self.block)

    def test_abgleich_und_nachholen_sind_verdrahtet(self):
        self.assertIn("_fehlende_zieldateien", self.block)
        self.assertIn("ufs2_extract.incomplete_failed", self.block)
        self.assertIn("ufs2_extract.complete", self.block)


class MeldungsTests(unittest.TestCase):
    """Der Fehlertext muss die fehlenden Dateien benennen, nicht nur eine Nummer."""

    def test_alle_schluessel_sind_zweisprachig_vorhanden(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in (
            "ufs2_extract.source_listed",
            "ufs2_extract.robocopy_partial",
            "ufs2_extract.incomplete_found",
            "ufs2_extract.retrying",
            "ufs2_extract.retry_failed",
            "ufs2_extract.incomplete_failed",
            "ufs2_extract.complete",
        ):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))

    def test_fehlermeldung_nennt_dateinamen(self):
        from ps5_validator.utils.i18n import translate
        text = translate("de", "ufs2_extract.incomplete_failed",
                         count=1, total=196, names="sce_sys/about/right.sprx")
        self.assertIn("sce_sys/about/right.sprx", text)
        self.assertIn("196", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
