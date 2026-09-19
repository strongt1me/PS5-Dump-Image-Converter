# -*- coding: utf-8 -*-
"""Dokan: nur Dokan 2 taugt fuer mount_udf.

Die Laufzeit dokan2.dll spricht nur mit dem Kerneltreiber dokan2.sys. Bis
zum 19.09.2026 galt auch dokan1.sys oder dokan.sys als Treiber - ein Rest
aus Dokan 1 neben einer dokan2.dll hiess "einsatzbereit", Punkt 20
installierte nichts, und mount_udf scheiterte trotzdem. Gemessen auf dem
Entwicklungsrechner: Dokan 2.3.1 legt dokan2.sys und dokan2.dll ab.

Geprueft wird gegen ein nachgebautes SystemRoot. Die echte dokan2.dll des
Rechners darf dabei nicht mitzaehlen - sie liegt im Suchpfad und liesse
sich laden. Deshalb ist ``ctypes.WinDLL`` in jedem Fall ersetzt.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("dokan_erkennung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class DokanErkennungTests(unittest.TestCase):
    """``_find_dokan_driver`` gegen ein nachgebautes SystemRoot."""

    def setUp(self) -> None:
        self.wurzel = Path(tempfile.mkdtemp(prefix="sysroot_"))
        self.addCleanup(shutil.rmtree, self.wurzel, True)
        (self.wurzel / "System32" / "drivers").mkdir(parents=True)
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def _ablegen(self, *namen: str) -> None:
        for name in namen:
            ordner = self.wurzel / "System32"
            if name.endswith(".sys"):
                ordner = ordner / "drivers"
            (ordner / name).write_bytes(b"MZ")

    def _erkannt(self, *, dll_ladbar: bool = False) -> bool:
        """Misst mit dem nachgebauten SystemRoot - nie mit dem echten."""
        if dll_ladbar:
            laden = mock.Mock(return_value=object())
        else:
            laden = mock.Mock(side_effect=OSError("nicht gefunden"))
        with mock.patch.dict(os.environ, {"SystemRoot": str(self.wurzel)}), \
                mock.patch.object(APP.sys, "platform", "win32"), \
                mock.patch("ctypes.WinDLL", laden, create=True):
            return self.gui._find_dokan_driver()

    def test_dokan2_vollstaendig(self) -> None:
        self._ablegen("dokan2.sys", "dokan2.dll")
        self.assertTrue(self._erkannt())

    def test_dokan1_treiber_neben_dokan2_dll_ist_nicht_bereit(self) -> None:
        """Der Fall, der bis zum 19.09.2026 als "einsatzbereit" galt."""
        self._ablegen("dokan1.sys", "dokan2.dll")
        self.assertFalse(self._erkannt())

    def test_alter_dokan_treiber_neben_dokan2_dll_ist_nicht_bereit(self) -> None:
        self._ablegen("dokan.sys", "dokan2.dll")
        self.assertFalse(self._erkannt())

    def test_nur_dokan1_ist_nicht_bereit(self) -> None:
        self._ablegen("dokan1.sys", "dokan1.dll")
        self.assertFalse(self._erkannt())

    def test_treiber_ohne_laufzeit_ist_nicht_bereit(self) -> None:
        self._ablegen("dokan2.sys")
        self.assertFalse(self._erkannt())

    def test_laufzeit_ueber_den_suchpfad_zaehlt(self) -> None:
        """dokan2.dll muss nicht in System32 liegen - ladbar genuegt."""
        self._ablegen("dokan2.sys")
        self.assertTrue(self._erkannt(dll_ladbar=True))

    def test_ausserhalb_von_windows_nie(self) -> None:
        self._ablegen("dokan2.sys", "dokan2.dll")
        with mock.patch.dict(os.environ, {"SystemRoot": str(self.wurzel)}), \
                mock.patch.object(APP.sys, "platform", "linux"):
            self.assertFalse(self.gui._find_dokan_driver())


if __name__ == "__main__":
    unittest.main(verbosity=2)
