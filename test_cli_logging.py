"""Regressionstest: Protokollspiegelung im CLI-Modus darf nie abbrechen.

Gefunden beim Durchtesten aller Aufgaben: Leitet man die Ausgabe des
CLI-Modus in eine Datei um, wählt Windows dafür die Codepage der Konsole
(meist cp1252). Eine Protokollzeile mit „→" – etwa die Größenangabe
„618.4 MB → ~347.6 MB" – löste dort einen UnicodeEncodeError aus. Der schlug
bis in den Aufgaben-Thread durch und beendete die Konvertierung als
„Unerwarteter Fehler", obwohl die Arbeit bereits fertig war.

Zwei Ebenen sichern das ab:
  1. `_prepare_cli_streams()` stellt stdout/stderr auf UTF-8 um.
  2. `_append_to_log()` fängt Kodierfehler zusätzlich ab und ersetzt die
     Zeichen, statt die Aufgabe scheitern zu lassen.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI, _prepare_cli_streams

PFEIL_ZEILE = "618.4 MB → ~347.6 MB\n"


class _Root:
    """Minimaler Ersatz für das Tk-Fenster."""

    @staticmethod
    def after(*_args, **_kwargs) -> None:
        return None


def _gui_im_cli_modus() -> PS5ConverterGUI:
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._cli_mode = True
    gui._cli_quiet = False
    gui._clean_log_text = lambda text: text
    gui.root = _Root()
    return gui


class CliProtokollTests(unittest.TestCase):
    def setUp(self) -> None:
        self._stdout = sys.stdout

    def tearDown(self) -> None:
        sys.stdout = self._stdout

    def _mit_kodierung(self, kodierung: str, fehlerbehandlung: str = "strict") -> io.BytesIO:
        puffer = io.BytesIO()
        sys.stdout = io.TextIOWrapper(puffer, encoding=kodierung, errors=fehlerbehandlung, newline="")
        return puffer

    def test_pfeil_bricht_cp1252_ausgabe_nicht_ab(self):
        """Der eigentliche Fehlerfall: umgeleitete Ausgabe unter Windows."""
        puffer = self._mit_kodierung("cp1252")
        gui = _gui_im_cli_modus()
        gui._append_to_log(PFEIL_ZEILE)          # darf nicht werfen
        sys.stdout.flush()
        ausgabe = puffer.getvalue().decode("cp1252")
        self.assertIn("618.4 MB", ausgabe)
        self.assertIn("347.6 MB", ausgabe)

    def test_utf8_erhaelt_das_zeichen(self):
        puffer = self._mit_kodierung("utf-8")
        gui = _gui_im_cli_modus()
        gui._append_to_log(PFEIL_ZEILE)
        sys.stdout.flush()
        self.assertIn("→", puffer.getvalue().decode("utf-8"))

    def test_ascii_ausgabe_bricht_nicht_ab(self):
        """Auch die engste Kodierung darf die Aufgabe nicht scheitern lassen."""
        puffer = self._mit_kodierung("ascii")
        gui = _gui_im_cli_modus()
        gui._append_to_log("Fortschritt: 50 % → fertig\n")
        sys.stdout.flush()
        self.assertIn("Fortschritt", puffer.getvalue().decode("ascii", errors="replace"))

    def test_stille_gibt_gar_nichts_aus(self):
        puffer = self._mit_kodierung("cp1252")
        gui = _gui_im_cli_modus()
        gui._cli_quiet = True
        gui._append_to_log(PFEIL_ZEILE)
        sys.stdout.flush()
        self.assertEqual(puffer.getvalue(), b"")

    def test_stroeme_werden_auf_utf8_gestellt(self):
        puffer = self._mit_kodierung("cp1252")
        _prepare_cli_streams()
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")
        gui = _gui_im_cli_modus()
        gui._append_to_log(PFEIL_ZEILE)
        sys.stdout.flush()
        self.assertIn("→", puffer.getvalue().decode("utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
