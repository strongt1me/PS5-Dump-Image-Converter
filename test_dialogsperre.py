# -*- coding: utf-8 -*-
"""Waechter fuer die Dialogsperre in conftest.py (``_keine_echten_dialoge``).

Ein Test, der ein echtes modales Fenster oeffnet, haelt die ganze Testreihe
an: am 17.09.2026 den Adminlauf eine halbe Stunde ("param.json beanstandet"),
am 23.09.2026 den Volllauf ("Content-ID fehlt"). Seit dem 24.09.2026 ersetzt
conftest.py die Dialoge in jedem Test durch eine Sperre, die sofort wirft.
Diese Pruefungen stellen sicher, dass die Sperre wirklich greift.
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import conftest                                             # noqa: E402


class DialogsperreTests(unittest.TestCase):

    def test_im_test_ist_kein_dialog_der_echte(self) -> None:
        """Entweder die Sperre oder eine Antwort des Tests - nie das echte Fenster."""
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self.skipTest("Die Sperre setzt conftest.py - nur unter pytest.")
        self.assertGreaterEqual(len(conftest._ORIGINALE), 15,
                                "conftest.py hat die Dialoge nicht erfasst.")
        for (modulname, name), original in conftest._ORIGINALE.items():
            modul = importlib.import_module(modulname)
            with self.subTest(dialog="%s.%s" % (modulname, name)):
                self.assertIsNot(getattr(modul, name), original,
                                 "Der echte Dialog ist im Test erreichbar.")

    def test_die_sperre_wirft_und_merkt_sich_den_titel(self) -> None:
        geoeffnet: list[str] = []
        sperre = conftest._dialogsperre("tkinter.messagebox.askyesno", geoeffnet)
        with self.assertRaises(conftest.EchterDialogImTest):
            sperre("Content-ID fehlt", "Platzhalter eintragen?")
        with self.assertRaises(AssertionError):
            sperre(title="Benannt")
        self.assertEqual(geoeffnet, ["tkinter.messagebox.askyesno('Content-ID fehlt')",
                                     "tkinter.messagebox.askyesno('Benannt')"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
