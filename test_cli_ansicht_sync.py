# -*- coding: utf-8 -*-
"""Der CLI-Modus muss die Konfig-Anzeige an die echte Aufgabe angleichen.

Hintergrund (13.09.2026): Das CLI-Fortschrittsfenster zeigte den Standard-
Aufbauzustand - Kopf "1. Dump-Ordner konvertieren" und die BAUFORM-Auswahl -,
obwohl in Wahrheit eine andere Aufgabe mit einem anderen Zielformat lief.
Ursache: ``_run_cli`` setzte ``current_mode.set(mode)`` statt
``_set_mode_from_sidebar(mode)`` und zog nach dem Setzen des Zielformats die
BAUFORM-Sichtbarkeit nicht nach.

Zwei Waechter:
* verhaltensbasiert - die CLI-Setup-Folge erzeugt eine stimmige Ansicht;
* quelltextbasiert - ``_run_cli`` benutzt diese Folge wirklich.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class CliAnsichtSyncVerhalten(unittest.TestCase):
    """Die Folge, die _run_cli fahren soll, ergibt eine stimmige Ansicht."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.dummy = tempfile.mkdtemp(prefix="cli_sync_")

    def _cli_setup(self, mode, fmt):
        """Bildet die (reparierte) CLI-Setup-Folge nach."""
        self.app.source_path.set(self.dummy)
        self.app._set_mode_from_sidebar(mode)
        if fmt:
            self.app.target_format.set(self.app._t("format." + fmt))
            self.app._format_hinweis_setzen(mode)
        _WURZEL.update_idletasks()

    def test_kopf_folgt_der_aufgabe(self):
        self._cli_setup("pack_file", "ffpkg")  # Aufgabe 3, exFAT -> .ffpkg
        erwartet = self.app._t("mode.pack_file").split(" (")[0]
        self.assertEqual(self.app.header_label.cget("text"), erwartet)

    def test_bauform_verborgen_bei_ffpkg(self):
        self._cli_setup("pack_file", "ffpkg")
        self.assertFalse(self.app.bauform_combo.winfo_ismapped(),
                         "BAUFORM darf bei .ffpkg nicht sichtbar sein")

    def test_bauform_sichtbar_bei_ffpfsc(self):
        self._cli_setup("pack_folder", "ffpfsc")  # Aufgabe 1 -> .ffpfsc
        self.assertTrue(self.app.bauform_combo.winfo_ismapped(),
                        "BAUFORM muss bei .ffpfsc sichtbar sein")


class RunCliNutztAnsichtsSync(unittest.TestCase):
    """_run_cli muss die Ansicht wirklich angleichen (nicht nur current_mode.set)."""

    @classmethod
    def setUpClass(cls):
        quelle = open(HAUPTDATEI, encoding="utf-8").read()
        m = re.search(r"\ndef _run_cli\(.*?\n(?=\ndef |\Z)", quelle, re.S)
        assert m, "_run_cli nicht gefunden"
        cls.rumpf = m.group(0)

    def test_setzt_modus_ueber_sidebar_helfer(self):
        self.assertIn("_set_mode_from_sidebar(", self.rumpf,
                      "_run_cli soll _set_mode_from_sidebar nutzen, damit Kopf/"
                      "Formatoptionen/BAUFORM zur echten Aufgabe passen.")

    def test_zieht_bauform_nach_dem_zielformat_nach(self):
        # Nach target_format.set(...) muss die Sichtbarkeit neu gesetzt werden.
        pos_format = self.rumpf.find("target_format.set(")
        self.assertGreater(pos_format, -1, "target_format.set fehlt in _run_cli")
        rest = self.rumpf[pos_format:]
        self.assertTrue(
            "_format_hinweis_setzen(" in rest or "_bauform_sichtbarkeit_setzen(" in rest,
            "Nach dem Setzen des Zielformats muss die BAUFORM-Sichtbarkeit "
            "nachgezogen werden.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
