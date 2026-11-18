# -*- coding: utf-8 -*-
"""``scripts/testlauf_versteckt.py``: Ein relativer Befehl gilt ab ``--ordner`` - wie unter Linux und macOS, auch unter Windows.

``CreateProcessW`` loest einen relativen Programmpfad gegen den Ordner des *Aufrufers* auf, nicht gegen ``lpCurrentDirectory``: Mit
``--ordner X`` scheiterte ``.venv\\Scripts\\python.exe`` mit ``OSError 2`` (Pruefung 18.11.2026). ``befehl_aufloesen`` rechnet den Pfad
vorher aus.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent


def _modul():
    spec = importlib.util.spec_from_file_location("testlauf_versteckt_skript", PROJEKT / "scripts" / "testlauf_versteckt.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class BefehlAufloesenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.m = _modul()
        self.tmp = tempfile.mkdtemp(prefix="testlauf_versteckt_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        os.makedirs(os.path.join(self.tmp, "sub"))
        Path(self.tmp, "sub", "werkzeug.cmd").write_text("@echo off\r\necho hallo\r\n", encoding="ascii")

    def test_ein_relativer_pfad_gilt_ab_dem_ordner(self) -> None:
        rel = os.path.join("sub", "werkzeug.cmd")
        erg = self.m.befehl_aufloesen([rel, "-x", "y"], self.tmp)
        self.assertEqual([os.path.abspath(os.path.join(self.tmp, rel)), "-x", "y"], erg)

    def test_ein_name_ohne_ordnerteil_bleibt_wie_er_ist(self) -> None:
        self.assertEqual(["python", "-m", "pytest"], self.m.befehl_aufloesen(["python", "-m", "pytest"], self.tmp))

    def test_ein_absoluter_pfad_bleibt(self) -> None:
        absolut = os.path.abspath(os.path.join(self.tmp, "sub", "werkzeug.cmd"))
        self.assertEqual([absolut, "a"], self.m.befehl_aufloesen([absolut, "a"], self.tmp))

    def test_ein_pfad_den_es_ab_dem_ordner_nicht_gibt_bleibt_wie_er_ist(self) -> None:
        rel = os.path.join("sub", "fehlt.cmd")
        self.assertEqual([rel], self.m.befehl_aufloesen([rel], self.tmp))

    def test_die_eingabe_wird_nicht_veraendert(self) -> None:
        eingabe = [os.path.join("sub", "werkzeug.cmd")]
        self.m.befehl_aufloesen(eingabe, self.tmp)
        self.assertEqual([os.path.join("sub", "werkzeug.cmd")], eingabe)

    @unittest.skipUnless(sys.platform == "win32", "der unsichtbare Desktop gibt es nur unter Windows")
    def test_unter_windows_laeuft_ein_relativer_befehl_mit_ordner(self) -> None:
        """Am echten Aufruf: der Befehl liegt nur ab ``--ordner``, nicht im Ordner dieses Prozesses."""
        aus = os.path.join(self.tmp, "aus.txt")
        rc = self.m.main(["--ordner", self.tmp, "--ausgabe", aus, "--", os.path.join("sub", "werkzeug.cmd")])
        self.assertEqual(0, rc)
        self.assertIn("hallo", Path(aus).read_text(encoding="utf-8", errors="replace"))


if __name__ == "__main__":
    unittest.main()
