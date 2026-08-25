# -*- coding: utf-8 -*-
"""Die Temp-Ordner-Prüfung darf nicht bei jedem Aufruf auf die Platte gehen.

Mit ``cProfile`` an einer echten Konvertierung gemessen (24.08.2026, Dump mit
0,24 GB, 41 s Laufzeit): ``_get_runtime_temp_dir`` wurde **374 Mal** gerufen -
neunmal je Sekunde -, weil ``_mkpfs_line_visible`` sie für jede Ausgabezeile
der Packmaschine aufruft. Jeder Aufruf legte eine Schreibprobe an, löschte sie
wieder und schrieb die Einstellungsdatei mit ``os.fsync`` auf die Platte:

    nt.open     375 Aufrufe   0,77 s
    nt.remove   375 Aufrufe   1,44 s
    nt.fsync    374 Aufrufe   0,80 s
    nt.replace  375 Aufrufe   0,48 s
    ---------------------------------
    zusammen                  3,50 s

Nach der Behebung: 3 / 3 / 0 / 0 Aufrufe, zusammen 0,01 s. Nebenbei
verschwinden die ``.ps5conv_tmp_write_test_*``-Dateien, die bei einem hart
beendeten Lauf liegenblieben - elf davon fanden sich im Testordner.

Geprüft wird weiterhin, nur nicht mehr im Sekundentakt.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Var:
    """Ein Ersatz für die Tk-Variable des Temp-Pfads."""

    def __init__(self, wert=""):
        self._wert = wert

    def get(self):
        return self._wert

    def set(self, wert):
        self._wert = wert


class TempPruefungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="tempprobe_")
        self.gespeichert: dict[str, str] = {}
        self.schreibvorgaenge = 0

        haupt = self.haupt

        class App:
            _TEMP_PRUEF_GUELTIG_S = haupt.PS5ConverterGUI._TEMP_PRUEF_GUELTIG_S
            _get_runtime_temp_dir = haupt.PS5ConverterGUI._get_runtime_temp_dir

            def _load_setting(_selbst, schluessel, vorgabe=None):
                return self.gespeichert.get(schluessel, vorgabe)

            def _save_setting(_selbst, schluessel, wert):
                self.schreibvorgaenge += 1
                self.gespeichert[schluessel] = wert

        self.app = App()
        self.app.temp_path = _Var(self.ordner)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def _proben(self) -> int:
        """Wie viele Schreibproben liegen noch im Ordner?"""
        return len([n for n in os.listdir(self.ordner)
                    if n.startswith(".ps5conv_tmp_write_test_")])

    # ── Der Kern ────────────────────────────────────────────────────────
    def test_wiederholte_aufrufe_gehen_nicht_auf_die_platte(self) -> None:
        """Der gemessene Fall: neun Aufrufe je Sekunde."""
        erster = self.app._get_runtime_temp_dir()
        for _ in range(200):
            self.assertEqual(self.app._get_runtime_temp_dir(), erster)
        self.assertLessEqual(
            self.schreibvorgaenge, 1,
            "201 Aufrufe ergaben %d Schreibvorgaenge" % self.schreibvorgaenge)

    def test_keine_schreibprobe_bleibt_liegen(self) -> None:
        for _ in range(30):
            self.app._get_runtime_temp_dir()
        self.assertEqual(self._proben(), 0)

    def test_derselbe_wert_wird_nicht_erneut_gespeichert(self) -> None:
        """Dieselbe Zeichenkette abzulegen kostet ein fsync und bringt nichts."""
        self.app._get_runtime_temp_dir()
        vorher = self.schreibvorgaenge
        self.app._temp_pruefung = None          # Zwischenstand verwerfen
        self.app._get_runtime_temp_dir()
        self.assertEqual(self.schreibvorgaenge, vorher)

    # ── Es wird weiterhin geprüft ───────────────────────────────────────
    def test_ein_anderer_ordner_wird_sofort_geprueft(self) -> None:
        """Sonst zeigte die Anzeige nach dem Umstellen auf den alten Ordner."""
        erster = self.app._get_runtime_temp_dir()
        zweiter_ordner = tempfile.mkdtemp(prefix="tempprobe2_")
        try:
            self.app.temp_path.set(zweiter_ordner)
            self.assertEqual(os.path.normpath(zweiter_ordner),
                             self.app._get_runtime_temp_dir())
            self.assertNotEqual(erster, self.app._get_runtime_temp_dir())
        finally:
            import shutil
            shutil.rmtree(zweiter_ordner, ignore_errors=True)

    def test_nach_der_gueltigkeit_wird_neu_geprueft(self) -> None:
        """Ein Datenträger, der mitten im Lauf wegfällt, muss auffallen."""
        self.app._get_runtime_temp_dir()
        merker, _pfad, _zeit = self.app._temp_pruefung
        # Zwischenstand künstlich altern lassen
        self.app._temp_pruefung = (merker, _pfad,
                                   time.monotonic() - self.app._TEMP_PRUEF_GUELTIG_S - 1)
        vorher = self._proben()
        self.app._get_runtime_temp_dir()
        self.assertEqual(self._proben(), vorher,
                         "die neue Schreibprobe wurde nicht aufgeraeumt")
        self.assertGreater(self.app._temp_pruefung[2],
                           time.monotonic() - self.app._TEMP_PRUEF_GUELTIG_S,
                           "der Zwischenstand wurde nicht erneuert")

    def test_ein_unbeschreibbarer_ordner_faellt_auf_das_system_zurueck(self) -> None:
        self.app.temp_path = _Var(os.path.join(self.ordner, "datei_statt_ordner"))
        with open(self.app.temp_path.get(), "wb") as f:
            f.write(b"x")
        ergebnis = self.app._get_runtime_temp_dir()
        self.assertEqual(ergebnis, os.path.normpath(tempfile.gettempdir()))

    def test_die_gueltigkeit_ist_kurz_genug(self) -> None:
        """Eine halbe Minute ist die Obergrenze - länger wäre unaufmerksam."""
        self.assertLessEqual(self.haupt.PS5ConverterGUI._TEMP_PRUEF_GUELTIG_S, 30.0)
        self.assertGreater(self.haupt.PS5ConverterGUI._TEMP_PRUEF_GUELTIG_S, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
