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

PROJEKT = Path(__file__).resolve().parent.parent
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

    def test_der_auswahldialog_des_programms_ist_im_test_gesperrt(self) -> None:
        """Er ist ein eigenes Toplevel mit ``wait_window``, kein tkinter-Dialog: Am 17.11.2026 hielt er einen Test mit der echten
        Befehlszeile von Dump Forge fuer immer an (die einmalige Frage nach der Firmware der Konsole vor dem Paketbau)."""
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self.skipTest("Die Sperre setzt conftest.py - nur unter pytest.")
        haupt = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        sperre = haupt.PS5ConverterGUI.__dict__["_auswahl_dialog"]
        self.assertNotEqual("PS5ConverterGUI._auswahl_dialog", getattr(sperre, "__qualname__", ""),
                            "Der echte Auswahldialog ist im Test erreichbar.")
        self.assertEqual("_auswahl_sperre", sperre.__name__)

    def test_die_sperre_des_auswahldialogs_wirft_und_merkt_sich_den_titel(self) -> None:
        geoeffnet: list[str] = []
        with self.assertRaises(conftest.EchterDialogImTest):
            conftest._auswahlsperre(geoeffnet)(object(), "Firmware deiner PS5", "Frage", ["7.xx"])
        self.assertEqual(["PS5ConverterGUI._auswahl_dialog('Firmware deiner PS5')"], geoeffnet)

    def test_ein_vom_test_ersetzter_auswahldialog_bleibt(self) -> None:
        """Wie bei den anderen Dialogen: Die Sperre ersetzt nur das Echte, nie die Antwort eines Tests."""
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            self.skipTest("Die Sperre setzt conftest.py - nur unter pytest.")
        from unittest import mock
        haupt = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        with mock.patch.object(haupt.PS5ConverterGUI, "_auswahl_dialog", return_value="7.xx"):
            self.assertEqual("7.xx", haupt.PS5ConverterGUI.__new__(haupt.PS5ConverterGUI)._auswahl_dialog("t", "f", ["7.xx"]))

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
