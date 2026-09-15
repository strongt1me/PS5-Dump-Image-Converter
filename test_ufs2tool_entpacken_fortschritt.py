# -*- coding: utf-8 -*-
"""Das Entpacken einer .ffpkg per UFS2Tool meldet sich - und laesst sich abbrechen.

Pruefmatrix vom 14.09.2026, Faelle F1, F3 und F5 (.ffpkg aus einem 51-GB-Titel):
``UFS2Tool extract`` schreibt ohne jede Zwischenmeldung, eine halbe Stunde und
laenger. Statuszeile und Balken standen still, die Aufhaenger-Erkennung schrieb
in allen drei **erfolgreichen** Laeufen einen Fehler samt Stapelabzug ins
Protokoll, und Abbrechen ging in dieser Zeit nicht.

Seitdem misst ein Beobachter die Groesse der Dateien im Zielordner und meldet
sie. Hier wird er mit einem gestellten Zielordner gefahren, in den der Test
selbst schreibt - UFS2Tool wird dafuer nicht gebraucht.
"""
from __future__ import annotations

import ast
import io
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ufs2tool_entpacken")

from ps5_validator.utils import i18n                        # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class _Lauf:
    """So viel von subprocess.Popen, wie der Beobachter anfasst."""

    def __init__(self) -> None:
        self.beendet = False

    def kill(self) -> None:
        self.beendet = True


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._t = lambda schluessel, **werte: "%s|%s|%s" % (
        schluessel, werte.get("erledigt", ""), werte.get("gesamt", ""))
    gui.status = []
    gui.protokoll = []
    gui._set_status = gui.status.append
    gui._append_to_log = gui.protokoll.append
    gui.task_progress = 10.0
    gui.is_running = True
    gui._ENTPACK_TAKT_S = 0.05
    return gui


class BeobachtenTests(unittest.TestCase):
    """Was der Beobachter waehrend des Entpackens meldet."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ufs2tool_fortschritt_")
        self.ziel = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _laufen_lassen(self, gui, erwartet: int, schreiben) -> _Lauf:
        stopp = threading.Event()
        lauf = _Lauf()
        faden = threading.Thread(
            target=gui._entpacken_beobachten,
            args=(lauf, str(self.ziel), erwartet, "Aufgabe 4 - ", 80.0, stopp))
        faden.start()
        try:
            schreiben()
        finally:
            stopp.set()
            faden.join(timeout=10)
        self.assertFalse(faden.is_alive(), "Der Beobachter endet nicht.")
        return lauf

    def test_meldet_die_geschriebene_menge(self):
        gui = _gui()

        def schreiben():
            (self.ziel / "sce_sys").mkdir()
            for i in range(4):
                (self.ziel / "sce_sys" / ("teil%d.bin" % i)).write_bytes(b"x" * 256 * 1024)
                time.sleep(0.15)

        self._laufen_lassen(gui, 1024 * 1024, schreiben)
        self.assertTrue(gui.status, "Waehrend des Entpackens kam keine Meldung.")
        for meldung in gui.status:
            self.assertTrue(meldung.startswith("Aufgabe 4 - ffpkg.extract_fortschritt|"),
                            meldung)

    def test_der_balken_bleibt_in_seinem_abschnitt(self):
        gui = _gui()

        def schreiben():
            (self.ziel / "eboot.bin").write_bytes(b"y" * 512 * 1024)
            time.sleep(0.4)

        self._laufen_lassen(gui, 1024 * 1024, schreiben)
        self.assertGreater(gui.task_progress, 10.0, "Der Balken bewegt sich nicht.")
        self.assertLessEqual(gui.task_progress, 10.0 + 80.0)

    def test_ohne_soll_groesse_nur_die_menge(self):
        """Ohne Soll gibt es nichts, woran sich ein Balken messen liesse."""
        gui = _gui()

        def schreiben():
            (self.ziel / "a.bin").write_bytes(b"z" * 1024)
            time.sleep(0.4)

        self._laufen_lassen(gui, 0, schreiben)
        self.assertTrue(gui.status)
        for meldung in gui.status:
            self.assertIn("ffpkg.extract_fortschritt_offen|", meldung)
        self.assertEqual(10.0, gui.task_progress,
                         "Ohne Soll-Groesse darf der Balken nicht raten.")

    def test_abbrechen_beendet_ufs2tool(self):
        gui = _gui()
        gui.is_running = False
        lauf = self._laufen_lassen(gui, 1024, lambda: time.sleep(0.4))
        self.assertTrue(lauf.beendet, "UFS2Tool laeuft nach dem Abbrechen weiter.")
        self.assertIn("ffpkg.extract_abgebrochen||", gui.protokoll)


class VerdrahtungTests(unittest.TestCase):
    """Der Beobachter haengt wirklich am Entpacken."""

    @classmethod
    def setUpClass(cls):
        with io.open(APP.__file__, "rb") as fh:
            cls.baum = ast.parse(fh.read().decode("utf-8"))

    def _text(self, name: str) -> str:
        knoten = next(k for k in ast.walk(self.baum)
                      if isinstance(k, ast.FunctionDef) and k.name == name)
        return ast.unparse(knoten)

    def test_das_entpacken_startet_den_beobachter(self):
        text = self._text("_ffpkg_ueber_unterbefehl_entpacken")
        self.assertIn("target=self._entpacken_beobachten", text)
        self.assertIn("stopp.set()", text,
                      "Der Beobachter wird nach UFS2Tool nicht angehalten.")

    def test_der_windows_weg_gibt_die_soll_groesse_mit(self):
        self.assertIn("erwartet_bytes=total_bytes[0]",
                      self._text("_extract_ffpkg_to_folder_via_ufs2tool"))

    def test_die_texte_gibt_es_in_beiden_sprachen(self):
        for schluessel in ("ffpkg.extract_fortschritt",
                           "ffpkg.extract_fortschritt_offen",
                           "ffpkg.extract_abgebrochen"):
            eintrag = i18n.STRINGS[schluessel]
            self.assertTrue(eintrag.get("de"), schluessel)
            self.assertTrue(eintrag.get("en"), schluessel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
