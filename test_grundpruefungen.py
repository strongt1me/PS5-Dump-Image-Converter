# -*- coding: utf-8 -*-
"""Die vier Pruefungen, die sonst nirgends stehen.

Sie kommen aus ``test_all_quality_new.py``. Diese Datei war ein
Blindgaenger: Ihre Pruefungen standen als Funktionen auf **Modulebene**,
und ``unittest`` sammelt nur Methoden in ``TestCase``-Klassen ein. Sie
liefen deshalb nur, wenn jemand die Datei von Hand aufrief - im
Gesamtlauf stand sie als "LEER". Neun ihrer vierzehn Pruefungen sind
inzwischen in ``test_qualitaetslauf.py`` aufgegangen, eine weitere
(Bau-Voraussetzungen) in ``test_build_ready.py``. Die vier hier waren
der Rest.

Ihr Wert ist unterschiedlich, und das soll hier auch stehen:

* Die **Abhaengigkeiten** sind die einzige echte Pruefung. Fehlt ein
  Paket in der Umgebung, faellt sie mit dessen Namen - das ist mehr,
  als ein beliebiger anderer Test dazu sagen wuerde.
* **Syntax** und **Hauptdatei** sind beinahe Selbstverstaendlichkeiten;
  jede andere Pruefdatei importiert das Programm und faellt vorher.
  Sie kosten nichts und bleiben deshalb.
* Das **Fortschrittswerk** ist eine Quelltextsuche und damit von der
  Sorte, die einen Umzug nicht ueberlebt - siehe die Lehre in
  ``test_qualitaetslauf.KeineTotenPruefungenTests``. Sie steht hier,
  weil sie Bestand ist, nicht weil sie ein gutes Muster waere. Wer
  eines dieser Merkmale verschiebt, passt sie mit an.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _quelltext() -> str:
    return HAUPTDATEI.read_text(encoding="utf-8", errors="replace")


class SyntaxTests(unittest.TestCase):
    """Laesst sich die Hauptdatei ueberhaupt lesen?"""

    def test_die_hauptdatei_parst(self) -> None:
        try:
            ast.parse(_quelltext())
        except SyntaxError as fehler:
            self.fail("Zeile %s: %s" % (fehler.lineno, fehler.msg))


class AbhaengigkeitenTests(unittest.TestCase):
    """Die Pakete, ohne die das Programm nicht startet.

    Geprueft wird ueber ``find_spec``, nicht ueber ``import``: Ein
    tatsaechlicher Import zoege bei ``tkinter`` eine Anzeigeverbindung
    nach sich, und die gibt es auf einem Bauserver nicht.
    """

    #: Was ``import`` in der Hauptdatei verlangt. ``PIL`` und
    #: ``zstandard`` stehen hier, obwohl sie nicht in der
    #: Standardauslieferung sind - genau darum.
    PAKETE = (
        "tkinter", "PIL", "cryptography", "zstandard",
        "time", "os", "sys", "json", "threading",
        "subprocess", "hashlib", "struct", "re", "shutil",
    )

    def test_jedes_paket_ist_auffindbar(self) -> None:
        for name in self.PAKETE:
            with self.subTest(paket=name):
                self.assertIsNotNone(
                    importlib.util.find_spec(name),
                    "%s fehlt in dieser Umgebung." % name)


class FortschrittswerkTests(unittest.TestCase):
    """Quelltextsuche - siehe die Warnung im Kopf dieser Datei."""

    MERKMALE = (
        "class ProgressEngine",
        "_estimate_eta_seconds",
        "PROGRESS_EASING",
        "task_progress",
        "_update_progress_gui",
    )

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = _quelltext()

    def test_die_teile_des_fortschrittswerks_sind_da(self) -> None:
        for merkmal in self.MERKMALE:
            with self.subTest(merkmal=merkmal):
                self.assertIn(merkmal, self.quelle)

    def test_der_zeitstempel_der_engine_wird_nicht_ueberschrieben(self) -> None:
        """Rueckfallpruefung zum Keepalive.

        ``_last_engine_output_ts`` darf nicht mit der allgemeinen Uhr
        gleichgesetzt werden - sonst meldet das Keepalive nie, dass die
        Engine schweigt. Die Wirkung prueft
        ``test_qualitaetslauf.KeepaliveTests``; hier steht nur die
        Schreibweise, die den Fehler zurueckbraechte.
        """
        self.assertNotIn("self._last_engine_output_ts = _now", self.quelle)


class HauptdateiTests(unittest.TestCase):
    """Grobe Kennzahlen der Hauptdatei.

    Bewusst weite Grenzen: Die Pruefung soll anschlagen, wenn die Datei
    abgeschnitten oder vertauscht wurde - nicht bei jedem Wachsen oder
    Schrumpfen. Genau das ist einmal passiert: ``i18n.py`` schrumpfte
    durch einen fehlerhaften Schnitt von 252 KB auf 69 KB.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = _quelltext()
        cls.zeilen = cls.quelle.splitlines()

    def test_die_datei_ist_nicht_abgeschnitten(self) -> None:
        groesse = len(self.quelle.encode("utf-8"))
        self.assertGreater(groesse, 1_000_000,
                           "Nur %.2f MB - abgeschnitten?" % (groesse / 1024 / 1024))

    def test_die_zeilenzahl_passt_zur_groesse(self) -> None:
        self.assertGreater(len(self.zeilen), 10_000)

    def test_es_stehen_klassen_und_methoden_darin(self) -> None:
        baum = ast.parse(self.quelle)
        klassen = [k for k in ast.walk(baum) if isinstance(k, ast.ClassDef)]
        methoden = [f for f in ast.walk(baum) if isinstance(f, ast.FunctionDef)]
        self.assertTrue(klassen, "Keine einzige Klasse gefunden.")
        self.assertTrue(methoden, "Keine einzige Funktion gefunden.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
