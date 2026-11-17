# -*- coding: utf-8 -*-
"""``archiv_quelle.entpackte_groesse``: wie viel Platz ein Archiv entpackt braucht (17.11.2026).

Gemessen an einem echten Spiele-Archiv: ein 7z von 36 GB (``Astro Bot``, 166.734 Dateien) belegt entpackt 160 GB. Die Platzpruefung vor dem
Entpacken rechnete bis dahin mit der Dateigroesse und liess das Entpacken beginnen, bis das Laufwerk voll war.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import archiv_quelle as aq   # noqa: E402

#: Die Schlusszeile von ``7z l`` an einem echten Archiv (gekuerzt um die Dateizeilen davor).
ECHT = (
    "   Date      Time    Attr         Size   Compressed  Name\n"
    "------------------- ----- ------------ ------------  ------------------------\n"
    "2026-09-30 01:06:10 ....A        95932               PPSA21567-app\\data\\prein\\haptics\\temp_sponge_squeeze_water_oneshot.wav\n"
    "2026-09-30 01:06:10 ....A       288044               PPSA21567-app\\data\\prein\\haptics\\weather_wind.wav\n"
    "------------------- ----- ------------ ------------  ------------------------\n"
    "2026-10-05 15:12:31       160133151363  37949990584  166734 files, 2151 folders\n"
)


class SummeAusListeTests(unittest.TestCase):

    def test_die_schlusszeile_eines_echten_archivs(self) -> None:
        self.assertEqual(160133151363, aq.summe_aus_liste(ECHT))

    def test_ohne_die_spalte_der_gepackten_groesse(self) -> None:
        self.assertEqual(12345, aq.summe_aus_liste("2026-10-05 15:12:31        12345  7 files, 1 folders\n"))

    def test_ohne_datum_und_ohne_ordner(self) -> None:
        self.assertEqual(777, aq.summe_aus_liste("            777         100  3 files\n"))

    def test_eine_dateizeile_ist_keine_summe(self) -> None:
        self.assertIsNone(aq.summe_aus_liste("2026-09-30 01:06:10 ....A       288044               PPSA21567-app\\x\\weather_wind.wav\n"))

    def test_ohne_schlusszeile_ist_die_groesse_unbekannt(self) -> None:
        for text in ("", "ERROR: Can not open the file as archive\n", "Enter password (will not be echoed):"):
            with self.subTest(text=text[:20]):
                self.assertIsNone(aq.summe_aus_liste(text))

    def test_mehrere_schlusszeilen_zaehlt_die_letzte(self) -> None:
        self.assertEqual(2000, aq.summe_aus_liste("2026-10-05 15:12:31   1000  500  3 files, 1 folders\n2026-10-05 15:12:31   2000  900  5 files\n"))


class EntpackteGroesseTests(unittest.TestCase):

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = tmp.name

    def _siebenzip(self) -> str:
        programm = aq.siebenzip_suchen([str(PROJEKT)])
        if not programm:
            self.skipTest("kein 7-Zip gefunden")
        return programm

    def test_zip_summiert_die_groessen_im_verzeichnis(self) -> None:
        pfad = os.path.join(self.t, "spiel.zip")
        with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("a/eboot.bin", b"\0" * 1000)           # packt sich auf wenige Bytes: die Dateigroesse ist nicht die Antwort
            z.writestr("a/sce_sys/param.json", b"{}" * 1250)
            z.writestr("leer/", b"")
        self.assertEqual(3500, aq.entpackte_groesse(pfad))
        self.assertLess(os.path.getsize(pfad), 3500, "Gegenprobe: das Archiv ist kleiner als der entpackte Inhalt")

    def test_ein_beschaedigtes_zip_ist_unbekannt(self) -> None:
        pfad = os.path.join(self.t, "kaputt.zip")
        Path(pfad).write_bytes(b"kein zip")
        self.assertIsNone(aq.entpackte_groesse(pfad))

    def test_kein_archiv_ist_unbekannt(self) -> None:
        text = os.path.join(self.t, "a.txt")
        Path(text).write_bytes(b"x")
        self.assertIsNone(aq.entpackte_groesse(text))
        self.assertIsNone(aq.entpackte_groesse(os.path.join(self.t, "gibt-es-nicht.7z")))

    def test_ein_7z_wird_ueber_die_liste_von_7zip_gemessen(self) -> None:
        programm = self._siebenzip()
        quelle = os.path.join(self.t, "spiel")
        os.makedirs(os.path.join(quelle, "sce_sys"))
        Path(quelle, "eboot.bin").write_bytes(b"\0" * 50000)              # packt sich fast auf nichts
        Path(quelle, "sce_sys", "param.json").write_bytes(b"{}" * 5000)
        archiv = os.path.join(self.t, "spiel.7z")
        lauf = subprocess.run([programm, "a", "-t7z", "-bso0", archiv, os.path.join(quelle, "*")], capture_output=True, timeout=120)
        self.assertEqual(0, lauf.returncode, lauf.stderr)
        self.assertEqual(60000, aq.entpackte_groesse(archiv, wurzeln=[str(PROJEKT)]))
        self.assertLess(os.path.getsize(archiv), 60000)

    def test_ein_kaputtes_7z_ist_unbekannt(self) -> None:
        self._siebenzip()
        pfad = os.path.join(self.t, "kaputt.7z")
        Path(pfad).write_bytes(b"x")
        self.assertIsNone(aq.entpackte_groesse(pfad, wurzeln=[str(PROJEKT)]))

    def test_meldet_7zip_einen_fehler_zaehlt_auch_eine_vorhandene_summe_nicht(self) -> None:
        """Ein Archiv, das 7-Zip nur teilweise lesen kann (Code 2), hat vielleicht eine unvollstaendige Summe: lieber unbekannt."""
        class Fertig:
            def __init__(self, rc: int, *_a, **_k) -> None:
                self._rc = rc
                self.stdout = iter(ECHT.encode("utf-8").splitlines(keepends=True))

            def kill(self) -> None:
                pass

            def wait(self, timeout=None) -> int:
                return self._rc

            def poll(self):
                return self._rc

        pfad = os.path.join(self.t, "teilweise.7z")
        Path(pfad).write_bytes(b"7z")
        with mock.patch.object(aq, "siebenzip_suchen", return_value="7z"):
            with mock.patch.object(aq.subprocess, "Popen", lambda *a, **k: Fertig(0)):
                self.assertEqual(160133151363, aq.entpackte_groesse(pfad), "Gegenprobe: mit Code 0 zaehlt die Summe")
            with mock.patch.object(aq.subprocess, "Popen", lambda *a, **k: Fertig(2)):
                self.assertIsNone(aq.entpackte_groesse(pfad))

    def test_ohne_7zip_ist_die_groesse_unbekannt(self) -> None:
        pfad = os.path.join(self.t, "spiel.rar")
        Path(pfad).write_bytes(b"Rar!")
        with mock.patch.object(aq, "siebenzip_suchen", return_value=""):
            self.assertIsNone(aq.entpackte_groesse(pfad))

    def test_ein_7zip_das_nicht_antwortet_wird_nach_der_frist_beendet(self) -> None:
        class Haengt:
            """Ein 7-Zip, das nichts ausgibt, bis es beendet wird."""
            def __init__(self, *_a, **_k) -> None:
                self._ende = threading.Event()
                self.stdout = self._zeilen()

            def _zeilen(self):
                self._ende.wait(15)
                yield from ()                                  # keine Zeile, nur das Ende

            def kill(self) -> None:
                self._ende.set()

            def wait(self, timeout=None) -> int:
                return -9

            def poll(self):
                return -9 if self._ende.is_set() else None

        pfad = os.path.join(self.t, "gross.7z")
        Path(pfad).write_bytes(b"7z")
        with mock.patch.object(aq, "siebenzip_suchen", return_value="7z"), mock.patch.object(aq.subprocess, "Popen", Haengt):
            start = time.monotonic()
            self.assertIsNone(aq.entpackte_groesse(pfad, frist=1.0))
            self.assertLess(time.monotonic() - start, 8.0, "die Frist beendet das Warten")


if __name__ == "__main__":
    unittest.main()
