# -*- coding: utf-8 -*-
"""Abbrechen beendet den eingebetteten mkpfs-Lauf wirklich - ohne die Fortschrittsanzeige zu stoeren.

Fenstermessung vom 04.11.2026 (Aufgaben 1-6, jeweils mit ABBRECHEN mitten im Lauf): Das Fenster
meldete "Abgebrochen.", der Aufgabenfaden endete nach einer halben Sekunde - und die Engine arbeitete
im Hintergrund weiter. Aufgabe 1 (.ffpfsc): Die ``.tmp``-Datei wuchs von 121 MB auf die vollen 437 MB
und wurde zur fertigen ``.ffpfsc`` im Ziel. Aufgabe 2 (Dump-Ordner): 500 MB mehr entpackt. Aufgabe 3:
die Arbeiterprozesse liefen weiter. Gemessen im Scratchpad: Eine Ausnahme aus ``Progress.step``
beendet Packen in 0,01 s und Entpacken in 0,07 s; mkpfs raeumt die ``.tmp``-Datei selbst weg.

**Die erste Fassung hat die Anzeige lahmgelegt.** Sie hing den Pruefer an ``mkpfs.pbar.default_listener``.
Hat eine ``Progress`` einen Hoerer, schreibt sie weder ihre Balkenzeilen noch ihre Statuszeilen nach
stderr - und genau die liest das Programm aus der Warteschlange. Gemessen im Fenster: Aufgabe 1 blieb bei
5 %, Aufgabe 3 bei 0,5 %, bis der Lauf zu Ende war. Diese Datei haelt deshalb beides fest: Der Lauf bricht ab,
und die Zeilen kommen weiter an (``test_die_balkenzeilen_kommen_weiter_an``).
"""
from __future__ import annotations

import ast
import contextlib
import io
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("engine_abbruch")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _mkpfs_da() -> bool:
    try:
        import mkpfs.cli  # noqa: F401
    except ImportError:
        return False
    return True


def _stub(laeuft: bool):
    gui = GUI.__new__(GUI)
    gui.is_running = laeuft
    return gui


def _im_faden(funktion):
    """Fuehrt ``funktion`` in einem eigenen Faden aus (ContextVar!) und gibt Ergebnis oder Ausnahme zurueck."""
    erg: dict = {}

    def lauf():
        try:
            erg["wert"] = funktion()
        except BaseException as exc:                              # noqa: BLE001
            erg["ausnahme"] = exc
    t = threading.Thread(target=lauf)
    t.start()
    t.join(120)
    assert not t.is_alive(), "Der Faden endete nicht."
    return erg


@unittest.skipUnless(_mkpfs_da(), "mkpfs nicht importierbar")
class PruefungTests(unittest.TestCase):

    def test_step_wirft_erst_nach_dem_abbruch(self):
        from mkpfs.pbar import Progress

        def lauf():
            gui = _stub(True)
            gui._engine_abbruch_hoerer_setzen()
            p = Progress(enabled=False)
            p.step("compress", 1, 10)                               # laeuft: nichts passiert
            gui.is_running = False
            p.step("compress", 2, 10)
        erg = _im_faden(lauf)
        self.assertIsInstance(erg.get("ausnahme"), APP._EngineAbbruch, erg)

    def test_ein_progress_ausserhalb_des_engine_fadens_bleibt_unberuehrt(self):
        """Der Validator (eigene ``Progress`` im eigenen Faden) darf nie von einem Abbruch erwischt werden."""
        from mkpfs.pbar import Progress
        _im_faden(lambda: _stub(False)._engine_abbruch_hoerer_setzen())   # Huelle ist jetzt installiert
        Progress(enabled=False).step("verify", 1, 10)                    # Hauptfaden: kein Pruefer gesetzt
        erg = _im_faden(lambda: Progress(enabled=False).step("verify", 1, 10))
        self.assertNotIn("ausnahme", erg, erg)

    def test_der_pruefer_gilt_auch_fuer_schritte_aus_hilfsfaeden(self):
        """mkpfs meldet Fortschritt auch aus Pool-Faeden; der Pruefer haengt deshalb an der Instanz."""
        from mkpfs.pbar import Progress

        def lauf():
            gui = _stub(False)
            gui._engine_abbruch_hoerer_setzen()
            p = Progress(enabled=False)
            return _im_faden(lambda: p.step("compress", 1, 10))
        erg = _im_faden(lauf)
        self.assertIsInstance(erg["wert"].get("ausnahme"), APP._EngineAbbruch, erg)

    def test_die_balkenzeilen_kommen_weiter_an(self):
        """Der Befund hinter dieser Datei: Die Anzeige liest stderr - der Pruefer darf es nicht verstummen lassen."""
        from mkpfs.pbar import Progress, default_listener

        def lauf():
            _stub(True)._engine_abbruch_hoerer_setzen()
            puffer = io.StringIO()
            with contextlib.redirect_stderr(puffer):
                p = Progress(enabled=True)
                p.step("compress", 5, 10, bytes_processed=5)
                p.status("Compressing 1 file")
            return p.listener, default_listener.get(None), puffer.getvalue()
        erg = _im_faden(lauf)
        self.assertNotIn("ausnahme", erg, erg)
        listener, standard, text = erg["wert"]
        self.assertIsNone(listener, "Ein Hoerer an der Progress unterdrueckt ihre Ausgabe.")
        self.assertIsNone(standard, "default_listener darf nicht gesetzt werden: Er stellt die Anzeige still.")
        self.assertRegex(text, r"\s50% compress")
        self.assertIn("Compressing 1 file", text)

    def test_die_ausnahme_ist_kein_fehler_im_sinn_von_mkpfs(self):
        # mkpfs faengt in der Auswertung nur OSError/ValueError (Durchsicht Runde 19) - die Ausnahme
        # muss deshalb weder davon abgeleitet sein noch von SystemExit/KeyboardInterrupt.
        self.assertTrue(issubclass(APP._EngineAbbruch, Exception))
        self.assertFalse(issubclass(APP._EngineAbbruch, (OSError, ValueError)))


@unittest.skipUnless(_mkpfs_da(), "mkpfs nicht importierbar")
class EchterLaufTests(unittest.TestCase):
    """Ein kleiner echter Packlauf - einmal ungestoert, einmal mit gesetztem Abbruch."""

    @classmethod
    def setUpClass(cls):
        cls.arbeit = tempfile.mkdtemp(prefix="ps5conv_engine_abbruch_")
        cls.dump = os.path.join(cls.arbeit, "dump")
        os.makedirs(os.path.join(cls.dump, "sce_sys"))
        with io.open(os.path.join(cls.dump, "sce_sys", "param.json"), "wb") as fh:
            fh.write(b'{"titleId":"PPSA99999"}')
        with io.open(os.path.join(cls.dump, "eboot.bin"), "wb") as fh:
            fh.write(b"ELF" + bytes(2_000_000))

    @classmethod
    def tearDownClass(cls):
        # Unter Windows haelt der gerade beendete Packlauf (oder ein Virenscanner) eboot.bin noch einen Augenblick
        # offen; ein einmaliges rmtree(ignore_errors=True) liess dann %TEMP%\ps5conv_engine_abbruch_* liegen
        # (Anzeige-Diagnose: reste_liegen_geblieben, Rueckgabe 1). Darum mit Wiederholung.
        import gc
        import time
        for _ in range(40):
            gc.collect()
            shutil.rmtree(cls.arbeit, ignore_errors=True)
            if not os.path.exists(cls.arbeit):
                return
            time.sleep(0.25)

    def _packen(self, laeuft: bool, ziel: str) -> dict:
        """Wie ``_run_engine``: stderr gehoert dem Lauf (die Anzeige liest es), der Pruefer ist gesetzt."""
        ergebnis: dict = {}

        def lauf():
            from mkpfs.cli import cli_mkpfs_main
            _stub(laeuft)._engine_abbruch_hoerer_setzen()
            puffer = io.StringIO()
            alt = sys.stderr
            sys.stderr = puffer
            try:
                ergebnis["rc"] = cli_mkpfs_main([
                    "pack", "folder", "--no-ampr-index", "--compress", "--no-adjust-output-file-extension",
                    "--version", "PS5", "--inode-bits", "32", "--cpu-count", "2", "--compression-level", "1",
                    "--block-size", "65536", self.dump, ziel])
            except BaseException as exc:                         # noqa: BLE001
                ergebnis["ausnahme"] = exc
            finally:
                sys.stderr = alt
            ergebnis["stderr"] = puffer.getvalue()
        t = threading.Thread(target=lauf)
        t.start()
        t.join(120)
        self.assertFalse(t.is_alive(), "Der Lauf endete nicht.")
        return ergebnis

    def test_ungestoert_entsteht_das_ergebnis_und_die_anzeige_bekommt_ihre_zeilen(self):
        ziel = os.path.join(self.arbeit, "ganz.ffpfsc")
        erg = self._packen(True, ziel)
        self.assertEqual(0, erg.get("rc"), erg)
        self.assertTrue(os.path.isfile(ziel))
        self.assertRegex(erg["stderr"], r"\d+% compress", "Die Balkenzeilen fehlen - die Anzeige stuende still.")

    def test_mit_abbruch_entsteht_nichts(self):
        ziel = os.path.join(self.arbeit, "abgebrochen.ffpfsc")
        erg = self._packen(False, ziel)
        self.assertIsInstance(erg.get("ausnahme"), APP._EngineAbbruch, erg)
        uebrig = [n for n in os.listdir(self.arbeit) if n.startswith("abgebrochen")]
        self.assertEqual([], uebrig, "mkpfs soll seine .tmp-Datei selbst wegraeumen.")


class VerdrahtungTests(unittest.TestCase):
    """Die Schleife im Programm: Abbruch ist kein Fehler und kein Ergebnis."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()
        baum = ast.parse(cls.quelle)
        klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        cls.methode = next(m for m in klasse.body
                           if isinstance(m, ast.FunctionDef) and m.name == "_execute_mkpfs_einmal")
        cls.text = ast.unparse(cls.methode)
        cls.setzen = ast.unparse(next(m for m in klasse.body if isinstance(m, ast.FunctionDef)
                                      and m.name == "_engine_abbruch_hoerer_setzen"))

    def test_der_hoerer_wird_vor_dem_lauf_gesetzt(self):
        i_hoerer = self.text.find("self._engine_abbruch_hoerer_setzen()")
        i_lauf = self.text.find("cli_mkpfs_main(args)")
        self.assertGreater(i_hoerer, 0, "Der Abbruchpruefer wird nie gesetzt.")
        self.assertLess(i_hoerer, i_lauf)

    def test_der_abbruch_steht_vor_den_allgemeinen_fehlerzweigen(self):
        i_abbruch = self.text.find("except _EngineAbbruch")
        i_exit = self.text.find("except SystemExit")
        i_allg = self.text.find("except Exception as exc")
        self.assertGreater(i_abbruch, 0)
        self.assertLess(i_abbruch, i_exit)
        self.assertLess(i_abbruch, i_allg)

    def test_ein_nach_dem_abbruch_beendeter_lauf_zaehlt_als_abbruch(self):
        i_schleife = self.text.find("while not engine_done.wait(timeout=0.2)")
        i_nachher = self.text.find("if not self.is_running:", self.text.find("self._emit_processing_keepalive()"))
        self.assertGreater(i_schleife, 0)
        self.assertGreater(i_nachher, i_schleife,
                           "Endet die Engine schneller als die Schleife hinschaut, gilt das als fehlgeschlagen.")
        self.assertIn("abort_requested = True", self.text[i_nachher:i_nachher + 200])

    def test_default_listener_wird_nicht_angefasst(self):
        """Der erste Entwurf setzte ihn und stellte damit die Anzeige still (siehe Kopf der Datei)."""
        # Namen und Attribute im Syntaxbaum - die Erklaerung im Docstring nennt ihn ja mit Absicht.
        code = ast.parse(self.setzen)
        namen = {n.id for n in ast.walk(code) if isinstance(n, ast.Name)} | \
            {n.attr for n in ast.walk(code) if isinstance(n, ast.Attribute)} | \
            {a.name for n in ast.walk(code) if isinstance(n, ast.ImportFrom) for a in n.names}
        self.assertNotIn("default_listener", namen, "default_listener.set(...) ist verboten.")


if __name__ == "__main__":
    unittest.main()
