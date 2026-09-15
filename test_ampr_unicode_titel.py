# -*- coding: utf-8 -*-
"""Asset-Pack-Bau vertraegt Sonderzeichen im Titel (z. B. "Ghost of Yotei").

Fehlerbericht 15.09.2026 (v1.9.20): Der Asset-Pack-Bau brach am Ende mit
"'charmap' codec can't encode character '\\u014d'" ab. Ursache: Der Kindprozess
(ampr_pack.py bzw. der EXE-Selbstaufruf) schreibt Fortschrittszeilen mit dem
aktuellen Dateipfad auf stderr; unter Windows stand der Strom auf cp1252, und
das o-Makron in "Yotei" (U+014D) liess sich dort nicht kodieren.

Zwei Absicherungen:
- _lauf gibt dem Subprozess PYTHONUTF8=1 / PYTHONIOENCODING=utf-8 mit.
- _stroeme_absichern stellt benutzbare Stroeme im Kind auf UTF-8 um.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault(
    "PS5CONV_KONFIGORDNER", tempfile.mkdtemp(prefix="ampr_unicode_kfg_"))

TITEL = "Ghost_of_Y\u014dtei_Deluxe_Edition"   # \u014d = o-Makron


class _FakeStrom:
    """Iterierbarer, schliessbarer Strom-Ersatz."""
    def __init__(self, zeilen):
        self._it = iter(zeilen)
    def __iter__(self):
        return self._it
    def close(self):
        pass


class _FakeProc:
    """Minimaler Ersatz fuer den Packprozess in _lauf."""
    def __init__(self):
        # stderr enthaelt eine Fortschrittszeile MIT Sonderzeichen im Pfad.
        self.stderr = _FakeStrom([
            "[pack  50%%] packing: current=/mnt/%s/eboot.bin\n" % TITEL,
            "",
        ])
        self.stdout = _FakeStrom(["{}"])
        self.returncode = 0

    def wait(self):
        return 0

    def terminate(self):
        pass


class LaufEnvTests(unittest.TestCase):
    """_lauf erzwingt UTF-8 im Subprozess."""

    def setUp(self):
        from ps5_validator.utils import ampr_assetpakete
        self.mod = ampr_assetpakete

    def test_lauf_setzt_utf8_umgebung(self):
        aufgezeichnet = {}

        def _fake_popen(*args, **kwargs):
            aufgezeichnet.update(kwargs)
            return _FakeProc()

        with mock.patch.object(self.mod, "werkzeug_finden",
                               return_value=r"C:\x\AMPR_PackTools-4.0\ampr_pack.py"), \
             mock.patch.object(self.mod, "_python_ruf",
                               return_value=["python", "ampr_pack.py"]), \
             mock.patch.object(self.mod.subprocess, "Popen",
                               side_effect=_fake_popen):
            self.mod._lauf(["verify", "--index", "x"], melden=lambda *_: None)

        env = aufgezeichnet.get("env")
        self.assertIsNotNone(env, "_lauf muss dem Subprozess eine env mitgeben")
        self.assertEqual("1", env.get("PYTHONUTF8"))
        self.assertEqual("utf-8", env.get("PYTHONIOENCODING"))
        # Die uebrige Umgebung bleibt erhalten (kein leeres env).
        self.assertGreater(len(env), 2)


class StroemeAbsichernTests(unittest.TestCase):
    """_stroeme_absichern stellt benutzbare Stroeme auf UTF-8 um."""

    @classmethod
    def setUpClass(cls):
        hd = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")
        if "hauptprogramm" in sys.modules:
            cls.haupt = sys.modules["hauptprogramm"]
        else:
            spec = importlib.util.spec_from_file_location("hauptprogramm", hd)
            cls.haupt = importlib.util.module_from_spec(spec)
            sys.modules["hauptprogramm"] = cls.haupt
            spec.loader.exec_module(cls.haupt)

    def test_cp1252_strom_wird_utf8_und_vertraegt_makron(self):
        class FakeStream:
            def __init__(self):
                self.encoding = "cp1252"
                self.reconfigured = None
            def reconfigure(self, encoding=None, errors=None):
                self.reconfigured = (encoding, errors)
                self.encoding = encoding or self.encoding
            def write(self, s):
                # cp1252 wuerde bei U+014D werfen - so wie beim Anwender.
                s.encode(self.encoding, "strict")
                return len(s)
            def flush(self):
                pass

        alt_out, alt_err = sys.stdout, sys.stderr
        fo, fe = FakeStream(), FakeStream()
        try:
            sys.stdout, sys.stderr = fo, fe
            self.haupt._stroeme_absichern()
        finally:
            sys.stdout, sys.stderr = alt_out, alt_err

        for strom in (fo, fe):
            self.assertEqual(("utf-8", "replace"), strom.reconfigured,
                             "Strom muss auf UTF-8 (errors=replace) gestellt werden")
            self.assertEqual("utf-8", strom.encoding)
            # Jetzt traegt der Strom das o-Makron, ohne zu werfen.
            strom.write("current=/mnt/%s/eboot.bin" % TITEL)


if __name__ == "__main__":
    unittest.main(verbosity=2)
