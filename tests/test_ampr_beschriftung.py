# -*- coding: utf-8 -*-
"""Klappliste neben dem Kaestchen AMPR EMU: ``test-nopack`` steht als "0.4.2.1" da (25.10.2026).

``test-nopack`` ist die normale Fassung des AMPR EMU (ohne Asset-Pack-Bau). Die Liste der Methode Normal zeigt deshalb nur die
Nummer; die Packbauten (``test-pack``, ``test-debug-pack``) gehoeren zur Methode Asset-Pack und behalten ihre Variante.
Nur die Anzeige aendert sich - der Schluessel der Liste ist die Beschriftung, Ordner und Dateien heissen wie bisher.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def _eintrag(version: str, variante: str, lib: str = "libSceAmpr.sprx") -> dict:
    return {"lib": lib, "version": version, "variant": variante, "path": "/x/%s %s/%s" % (version, variante, lib)}


VORRAT = [
    _eintrag("0.4.2.1", "test-nopack"), _eintrag("0.4.2.1", "test-pack"), _eintrag("0.4.2.1", "test-debug-pack"),
    _eintrag("0.3.6.6", "no debug"), _eintrag("0.3.6.6", "debug"),
    _eintrag("0.6", "nolog", "libScePlayGo.sprx"),
]


class _Var:
    def __init__(self) -> None:
        self.wert = ""

    def get(self) -> str:
        return self.wert

    def set(self, wert: str) -> None:
        self.wert = wert


class BeschriftungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.modul = _lade_hauptprogramm()
        self.G = self.modul.PS5ConverterGUI

    def _app(self, methode: str, gemerkt: str = ""):
        app = self.G.__new__(self.G)
        app.ampr_version_combo = mock.Mock()
        app.ampr_version_var = _Var()
        app._ampr_methode = lambda: methode
        app._load_setting = lambda schluessel, vorgabe=None: gemerkt if schluessel == "integrate_ampr_version" else vorgabe
        app._append_to_log = lambda text: None
        app._t = lambda schluessel, **w: schluessel
        app._ampr_fassungen_gelesen = list(VORRAT)
        app._on_integration_changed = lambda *a, **k: None
        return app

    def _fuellen(self, app) -> list[str]:
        app._ampr_versionsliste_fuellen(eintraege=list(VORRAT))
        return list(app.ampr_version_combo.configure.call_args.kwargs["values"])

    def test_einzelne_beschriftungen(self) -> None:
        f = self.G._ampr_beschriftung
        self.assertEqual("0.4.2.1", f(_eintrag("0.4.2.1", "test-nopack")))
        self.assertEqual("0.4.2.1 test-pack", f(_eintrag("0.4.2.1", "test-pack")))
        self.assertEqual("0.4.2.1 test-debug-pack", f(_eintrag("0.4.2.1", "test-debug-pack")))
        self.assertEqual("0.3.6.6 no debug", f(_eintrag("0.3.6.6", "no debug")))
        self.assertEqual("0.3.6.6 debug", f(_eintrag("0.3.6.6", "debug")))
        self.assertEqual("0.5", f(_eintrag("0.5", "")), "ohne Variante nur die Nummer, ohne Leerzeichen am Ende")

    def test_methode_normal_zeigt_0_4_2_1_ohne_zusatz_und_oben(self) -> None:
        app = self._app(self.modul.AMPR_METHODE_NORMAL)
        werte = self._fuellen(app)
        self.assertEqual(["0.4.2.1", "0.3.6.6 no debug", "0.3.6.6 debug"], werte)
        self.assertEqual("0.4.2.1", app.ampr_version_var.get(), "voreingestellt ist die oberste = neueste")
        # Der Schluessel der Auswahl ist die Beschriftung und fuehrt auf die Datei der Variante test-nopack.
        self.assertEqual("test-nopack", app._ampr_versionsauswahl["0.4.2.1"]["variant"])

    def test_methode_assetpack_behaelt_die_varianten(self) -> None:
        app = self._app(self.modul.AMPR_METHODE_ASSETPACK)
        self.assertEqual(["0.4.2.1 test-pack", "0.4.2.1 test-debug-pack"], self._fuellen(app))

    def test_die_alte_gemerkte_wahl_gilt_weiter(self) -> None:
        app = self._app(self.modul.AMPR_METHODE_NORMAL, gemerkt="0.4.2.1 test-nopack")
        self._fuellen(app)
        self.assertEqual("0.4.2.1", app.ampr_version_var.get())

    def test_eine_andere_gemerkte_wahl_bleibt(self) -> None:
        app = self._app(self.modul.AMPR_METHODE_NORMAL, gemerkt="0.3.6.6 debug")
        self._fuellen(app)
        self.assertEqual("0.3.6.6 debug", app.ampr_version_var.get())


if __name__ == "__main__":
    unittest.main()
