"""Regressionstest: gleiches Quell- und Zielformat.

Gefunden beim Durchtesten aller Aufgaben: Aufgabe 4 bietet in der
Auswahlliste ausdrücklich „.ffpkg (Neuvalidierung)" an – gemeint ist das
bewusste Extrahieren, Neu-Bauen und Neu-Validieren einer `.ffpkg`. Der Start
brach jedoch mit „Quelle und Zielformat sind identisch" ab, weil die Sperre
pauschal für alle Aufgaben galt. Die angebotene Funktion war damit nicht
erreichbar – weder in der Oberfläche noch im CLI-Modus.

Überall sonst bleibt ein Selbst-Ziel gesperrt: dort wäre es sinnlos.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI


class SelbstZielTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gui = PS5ConverterGUI.__new__(PS5ConverterGUI)

    def test_aufgabe_4_erlaubt_ffpkg_neuvalidierung(self):
        self.assertEqual(self.gui._conversion_block_reason("ffpkg", "ffpkg", "ffpkg_to_ffpfsc"), "")

    def test_aufgabe_4_normale_ziele_bleiben_offen(self):
        for ziel in ("folder", "ffpfsc", "exfat"):
            with self.subTest(ziel=ziel):
                self.assertEqual(self.gui._conversion_block_reason("ffpkg", ziel, "ffpkg_to_ffpfsc"), "")

    def test_selbst_ziel_bleibt_sonst_gesperrt(self):
        for mode, art in (("pack_folder", "folder"), ("unpack_to_exfat", "ffpfsc"),
                          ("pack_file", "exfat"), ("universal_convert", "exfat"),
                          ("batch_convert", "ffpkg")):
            with self.subTest(aufgabe=mode):
                grund = self.gui._conversion_block_reason(art, art, mode)
                self.assertIn("identisch", grund)

    def test_ohne_aufgabe_bleibt_es_gesperrt(self):
        """Ohne Modusangabe gilt weiterhin die strenge Regel."""
        self.assertIn("identisch", self.gui._conversion_block_reason("ffpkg", "ffpkg"))

    def test_die_auswahlliste_bietet_den_weg_ueberhaupt_an(self):
        """Die Sperre muss zu dem passen, was die Oberfläche anbietet."""
        self.assertIn("ffpkg", PS5ConverterGUI._MODE_TARGET_OPTIONS["ffpkg_to_ffpfsc"])

    def test_unbekannter_quelltyp_wird_weiterhin_abgelehnt(self):
        self.assertIn("Quelltyp", self.gui._conversion_block_reason("", "ffpfsc", "pack_folder"))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class KomprimiertGegenUnkomprimiertTests(unittest.TestCase):
    """`.ffpfs` und `.ffpfsc` sind nicht dasselbe Zielformat.

    Lauf 20 des Praxistests: Aufgabe 6 lehnte
    `Wer wird Millionaer.ffpfs` -> `.ffpfsc` mit "Quelle und Zielformat sind
    identisch" ab. Ursache ist `_detect_source_type`, das beide Endungen zu
    "ffpfsc" zusammenfasst - fuer die Aufgabenzuordnung richtig, fuer die
    Identitaetsfrage zu grob. Eine unkomprimierte Datei nachtraeglich zu
    komprimieren (oder umgekehrt) ist eine sinnvolle Aufgabe.
    """

    def setUp(self) -> None:
        import tempfile
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
        self.GUI = PS5ConverterGUI
        self.gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        self._tmp = tempfile.TemporaryDirectory(prefix="ffpfs_")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _datei(self, name: str) -> str:
        import os
        pfad = os.path.join(self._tmp.name, name)
        with open(pfad, "wb") as fh:
            fh.write(b"x")
        return pfad

    def _grund(self, name: str, ziel: str) -> str:
        pfad = self._datei(name)
        typ = self.GUI._detect_source_type(self.gui, pfad)
        return self.GUI._conversion_block_reason(self.gui, typ, ziel, "universal_convert", pfad)

    def test_unkomprimiert_nach_komprimiert_ist_moeglich(self) -> None:
        """Umpacken zwischen den beiden Kompressionsformen ist erlaubt.

        Zwei Stufen Geschichte: Erst hiess es "Quelle und Zielformat sind
        identisch" (irrefuehrend - die Endungen unterscheiden sich), dann kam
        ein Hinweis "geht nicht, nimm Aufgabe 1". Beides ist ueberholt: Seit
        Aufgabe 2 jede Bauform vollstaendig auspackt, laeuft das Umpacken ueber
        den Dump-Ordner - genau wie .ffpfsc -> .ffpkg schon immer.
        """
        self.assertEqual(self._grund("spiel.ffpfs", "ffpfsc"), "")

    def test_komprimiert_nach_unkomprimiert_ist_moeglich(self) -> None:
        self.assertEqual(self._grund("spiel.ffpfsc", "ffpfs"), "")

    def test_ffpkg_nach_unkomprimiert_ist_moeglich(self) -> None:
        """Aufgabe 6 bot .ffpkg -> .ffpfs an, der Verteiler kannte es nicht."""
        self.assertEqual(self._grund("spiel.ffpkg", "ffpfs"), "")

    def test_jede_angebotene_kombination_hat_einen_weg(self) -> None:
        """Kein angebotenes Ziel darf mitten im Lauf an der Verteilung scheitern."""
        import inspect
        import re as _re
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as G
        quelle = inspect.getsource(G._execute_conversion_by_type)
        verdrahtet = set(_re.findall(
            r'source_type == "(\w+)" and target_type == "(\w+)"', quelle))
        for quelltyp in ("folder", "ffpfsc", "exfat", "ffpkg"):
            for ziel in G._MODE_TARGET_OPTIONS["universal_convert"]:
                if quelltyp == ziel:
                    continue
                offen = (quelltyp, ziel) not in verdrahtet
                erklaert = any(schluessel[1] == ziel and schluessel[0].startswith(quelltyp[:5])
                               for schluessel in G._UNSUPPORTED_TARGET_HINTS)
                with self.subTest(von=quelltyp, nach=ziel):
                    self.assertFalse(
                        offen and not erklaert,
                        f"{quelltyp} -> {ziel} wird angeboten, aber weder verdrahtet noch erklaert")

    def test_echtes_selbst_ziel_bleibt_gesperrt(self) -> None:
        self.assertIn("identisch", self._grund("spiel.ffpfsc", "ffpfsc"))
        self.assertIn("identisch", self._grund("spiel.ffpfs", "ffpfs"))

    def test_andere_formate_unveraendert(self) -> None:
        self.assertEqual(self._grund("spiel.exfat", "ffpfsc"), "")
        self.assertIn("identisch", self._grund("spiel.exfat", "exfat"))
        self.assertIn("identisch", self._grund("spiel.ffpkg", "ffpkg"))

    def test_genaue_erkennung_trennt_die_beiden_endungen(self) -> None:
        for name, erwartet_typ, erwartet_genau in (
            ("a.ffpfs", "ffpfsc", "ffpfs"),
            ("a.ffpfsc", "ffpfsc", "ffpfsc"),
            ("a.exfat", "exfat", "exfat"),
        ):
            with self.subTest(name=name):
                pfad = self._datei(name)
                self.assertEqual(self.GUI._detect_source_type(self.gui, pfad), erwartet_typ)
                self.assertEqual(self.GUI._detect_source_format(self.gui, pfad), erwartet_genau)

    def test_ohne_pfad_bleibt_das_alte_verhalten(self) -> None:
        """Aufrufer ohne Pfadangabe duerfen sich nicht anders verhalten als frueher."""
        self.assertIn("identisch",
                      self.GUI._conversion_block_reason(self.gui, "ffpfsc", "ffpfsc", "universal_convert"))
