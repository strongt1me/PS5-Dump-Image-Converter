# -*- coding: utf-8 -*-
"""zlib-ng ist auf 1.1.0 festgenagelt (Nutzerentscheidung 06.11.2026; vorher 1.0.0 seit 05.11.2026).

Warum ein Pin: zlib-ng 1.1.0 buendelt zlib-ng 2.3.3 statt 2.2.5. Am 05.11.2026 auf demselben Gut gemessen (64-KiB-Bloecke
wie PFSC, Stufen 1 bis 9, Text, Binaerdateien, PNG, PDF): 35 von 36 Stufen byte-gleich, **Stufe 9 weicht ab** - gleiche
Groesse, andere Bytes. Stufe 9 ist die Vorgabe von Aufgabe 1. Ob der Hardware-Entpacker der PS5 den neuen Datenstrom nimmt,
laesst sich nur an der Konsole pruefen (Vorbild: ISA-L, MkPFS-Issue #132, Kernel-Panic).

Geprueft am 06.11.2026 (Teardown, 4,2 GB): mit 1.1.0 auf Stufe 9 werden 333 von 67.925 Bloecken (86 Dateien, meist .dds)
anders gepackt. Das Abbild laesst sich am PC entpacken (5.103 Dateien byte-gleich), die PS5 mountet es, das Spiel
startet, und alle 86 betroffenen Dateien lieferte die Konsole byte-gleich zum Original zurueck. Nur dieses eine Spiel
und nur Stufe 9.

Die Bauskripte installieren mit ``--upgrade``; ohne Pin haette der naechste Bau die neueste Fassung geholt. Dieser
Waechter haelt die vier Stellen (``requirements.txt``, ``Build_EXE.ps1``, ``Build_Linux.sh``, ``Build_macOS.sh``) auf
derselben Fassung. Wer weiter anhebt, aendert alle vier und diesen Test - nach einem Konsolentest.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
#: Die festgenagelte Fassung - die einzige Stelle in diesem Test.
FASSUNG = "1.1.0"


def _lesen(name: str) -> str:
    return (PROJEKT / name).read_text(encoding="utf-8-sig")


class ZlibNgFestgenageltTests(unittest.TestCase):
    def test_requirements_nennt_die_fassung(self) -> None:
        zeilen = [z.strip() for z in _lesen("requirements.txt").splitlines()
                  if z.strip() and not z.strip().startswith("#")]
        zlib_zeilen = [z for z in zeilen if re.match(r"zlib-ng\b", z, re.I)]
        self.assertEqual(["zlib-ng==" + FASSUNG], zlib_zeilen)

    def test_jedes_bauskript_installiert_genau_diese_fassung(self) -> None:
        # (Datei, Muster fuer den Aufruf) - der Name ist dabei nie ohne Fassung zu haben
        for datei, muster in (
                ("Build_EXE.ps1", r"-m pip install (zlib-ng\S*) --upgrade"),
                ("Build_Linux.sh", r"^(?:pflicht|optional)_installieren (zlib-ng\S*)"),
                ("Build_macOS.sh", r"^(?:pflicht|optional)_installieren (zlib-ng\S*)")):
            with self.subTest(datei=datei):
                treffer = re.findall(muster, _lesen(datei), re.M)
                self.assertEqual(["zlib-ng==" + FASSUNG], treffer,
                                 "%s muss zlib-ng==%s installieren (genau einmal)" % (datei, FASSUNG))

    def test_kein_skript_laesst_zlib_ng_ohne_fassung_hochziehen(self) -> None:
        for datei in ("Build_EXE.ps1", "Build_Linux.sh", "Build_macOS.sh"):
            with self.subTest(datei=datei):
                text = _lesen(datei)
                self.assertNotRegex(text, r"(?:install|_installieren) +\"?zlib-ng\"?(?: |$)",
                                    "zlib-ng ohne Fassung wuerde mit --upgrade die neueste holen")


if __name__ == "__main__":
    unittest.main()
