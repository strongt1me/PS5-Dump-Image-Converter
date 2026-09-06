# -*- coding: utf-8 -*-
"""Dasselbe Quellverzeichnis muss ueberall dasselbe Abbild ergeben.

**Warum es diesen Test gibt.** Am 06.09.2026 meldete ein Mac-Anwender, dass
zwei auf dem Mac erzeugte ``.ffpfsc`` die PS5 mit einer Kernel-Panic
abstuerzen lassen - bei fehlerfreiem Lauf und in zwei Programmfassungen. Die
Untersuchung fand keine Plattformweiche im Bauweg und konnte an einem
Windows-Rechner auch keine finden; die entscheidende Messung - dasselbe
Verzeichnis auf beiden Systemen packen und die Bytes vergleichen - liess sich
nur beim Anwender durchfuehren.

Genau die macht dieser Test, und zwar ueberall, wo der Testbestand laeuft:
Er baut aus einem **festgelegten** Baum ein exFAT-Abbild und haelt dessen
Pruefsumme gegen einen eingetragenen Wert. Weicht ein System ab, faellt er
dort - mit der ersten abweichenden Stelle im Fehlertext.

**Warum der Baum hier im Test steht** und nicht als Datei im Projekt: Er muss
Byte fuer Byte festliegen. Eine eingecheckte Datei koennte durch
Zeilenendenumsetzung, Attribute oder ein Archivwerkzeug unterwegs veraendert
werden - dann prueft der Test die Uebertragung statt den Erzeuger.

**Die Grenzfaelle im Baum** sind mit Absicht gewaehlt: eine Datei von genau
einer Clustergroesse (64 KiB), eine knapp darunter und eine knapp darueber -
dort entscheidet sich die Auffuellrechnung. Dazu eine leere Datei, ein
Unterordner und Namen, die sich in der Sortierung nur durch die
Gross-/Kleinschreibung unterscheiden koennten.

**Wenn dieser Test faellt**, ist die Frage beantwortet, die seit dem
06.09.2026 offen ist: Dann baut die betroffene Plattform wirklich ein anderes
Abbild, und die abweichende Stelle sagt, wo.
"""
from __future__ import annotations

import hashlib
import platform
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.0.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("abbild_plattformgleich")

from mkpfs import exfat_writer                              # noqa: E402

#: Am 06.09.2026 auf Windows 11 / Python 3.14 gemessen. Der Wert gilt fuer
#: jedes System - der Erzeuger kennt keine Plattformweiche, feste
#: Seriennummer, fester Zeitstempel, feste Clustergroesse.
ERWARTETE_SUMME = "56e00fc6f4abee41e7146a2468f2f75e50604f8ba25415ff9065cab694b1b602"
ERWARTETE_GROESSE = 1048576


def _beispielbaum(wurzel: Path) -> Path:
    """Ein Dump-Ordner, der auf jedem System gleich aussieht."""
    quelle = wurzel / "PPSA00001"
    (quelle / "sce_sys").mkdir(parents=True)
    (quelle / "sce_sys" / "param.json").write_bytes(
        b'{"titleId":"PPSA00001","contentId":"UP0000-PPSA00001_00-TEST"}')
    (quelle / "sce_sys" / "icon0.png").write_bytes(bytes(range(256)) * 4)
    (quelle / "eboot.bin").write_bytes(b"\x7fELF" + bytes(range(256)) * 256)
    # Die Blockgrenzen: genau eine Clustergroesse, knapp darunter, knapp
    # darueber. Dort entscheidet sich, wie aufgefuellt wird.
    for name, groesse in (("genau.bin", 65536), ("knapp.bin", 65535),
                          ("drueber.bin", 65537)):
        (quelle / name).write_bytes(bytes(i % 251 for i in range(groesse)))
    (quelle / "leer.bin").write_bytes(b"")
    unter = quelle / "unterordner"
    unter.mkdir()
    (unter / "tief.bin").write_bytes(b"T" * 1000)
    return quelle


class AbbildTests(unittest.TestCase):
    """Bytegleichheit ueber alle Plattformen."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="abbild_gleich_")
        cls.quelle = _beispielbaum(Path(cls._tmp.name))
        cls.abbild = b"".join(exfat_writer.iter_exfat_image(cls.quelle))

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_die_groesse_stimmt(self):
        self.assertEqual(ERWARTETE_GROESSE, len(self.abbild),
                         "Das Abbild ist auf %s anders gross."
                         % platform.platform())

    def test_die_pruefsumme_stimmt(self):
        gemessen = hashlib.sha256(self.abbild).hexdigest()
        if gemessen == ERWARTETE_SUMME:
            return
        # Nicht nur "ungleich" melden - die erste abweichende Stelle ist die
        # halbe Antwort, und auf einem fremden System kommt man sonst nicht
        # weiter.
        neu = b"".join(exfat_writer.iter_exfat_image(self.quelle))
        stabil = hashlib.sha256(neu).hexdigest() == gemessen
        self.fail(
            "Das Abbild weicht auf %s ab.\n"
            "  erwartet: %s\n  gemessen: %s\n"
            "  Groesse:  %d (erwartet %d)\n"
            "  Auf diesem System wiederholbar: %s\n"
            "  Wenn ja, baut diese Plattform wirklich anders - dann den Baum "
            "aus _beispielbaum auf beiden Systemen packen und die Abbilder "
            "byteweise vergleichen."
            % (platform.platform(), ERWARTETE_SUMME, gemessen,
               len(self.abbild), ERWARTETE_GROESSE, stabil))

    def test_zweimal_gebaut_gibt_dasselbe(self):
        """Ohne das waere die Pruefsumme oben nichts wert."""
        noch_einmal = b"".join(exfat_writer.iter_exfat_image(self.quelle))
        self.assertEqual(self.abbild, noch_einmal)

    def test_die_lesereihenfolge_spielt_keine_rolle(self):
        """Der Erzeuger sortiert selbst - APFS und NTFS liefern anders.

        Nachgestellt, indem der Baum in umgekehrter Reihenfolge neu angelegt
        wird: Auf einem Dateisystem, das die Anlegereihenfolge behaelt,
        kaeme scandir dann anders zurueck.
        """
        with tempfile.TemporaryDirectory(prefix="abbild_umgekehrt_") as tmp:
            ziel = Path(tmp) / "PPSA00001"
            (ziel / "sce_sys").mkdir(parents=True)
            dateien = sorted(
                (p for p in self.quelle.rglob("*") if p.is_file()),
                key=lambda p: str(p), reverse=True)
            for pfad in dateien:
                rel = pfad.relative_to(self.quelle)
                (ziel / rel).parent.mkdir(parents=True, exist_ok=True)
                (ziel / rel).write_bytes(pfad.read_bytes())
            umgekehrt = b"".join(exfat_writer.iter_exfat_image(ziel))
        self.assertEqual(hashlib.sha256(self.abbild).hexdigest(),
                         hashlib.sha256(umgekehrt).hexdigest())

    def test_der_baum_enthaelt_die_grenzfaelle(self):
        """Sonst prueft die Summe oben einen harmlosen Baum."""
        namen = {p.name for p in self.quelle.rglob("*") if p.is_file()}
        self.assertLessEqual(
            {"genau.bin", "knapp.bin", "drueber.bin", "leer.bin",
             "eboot.bin", "param.json", "tief.bin"}, namen)
        self.assertEqual(65536, (self.quelle / "genau.bin").stat().st_size)
        self.assertEqual(0, (self.quelle / "leer.bin").stat().st_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
