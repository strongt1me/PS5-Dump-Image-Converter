# -*- coding: utf-8 -*-
"""Live-Anzeige des freien Arbeitsspeichers waehrend eines Laufs (11.10.2026).

Wunsch des Nutzers: eine Live-Anzeige des freien Arbeitsspeichers waehrend des Laufs. Die Telemetrie (CPU/RAM/Temp je Sekunde)
gab es schon; sie nennt jetzt den **freien** Speicher vorn, unter 1 GB heisst es "nur noch x frei".

(Die vier Voreinstellungs-Knoepfe, die zusammen mit der Anzeige eingebaut wurden, hat der Nutzer am selben Tag wieder
herausnehmen lassen - Kompression und Kernzahl stellt er an ihren Feldern ein. Die Anzeige blieb.)
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ram_anzeige")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class RamAnzeigeTests(unittest.TestCase):
    """Die Telemetrie waehrend eines Laufs nennt den freien Arbeitsspeicher."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _tick(self, frei: int, gesamt: int = 24 * 1024 ** 3) -> str:
        probe = {"cpu_percent": 12.0, "ram_used": gesamt - frei, "ram_total": gesamt, "ram_free": frei}
        alt = self.app.is_running
        self.app.is_running = True
        try:
            with mock.patch.object(self.app, "_sample_system_telemetry", return_value=probe), \
                    mock.patch.object(self.app.root, "after"):
                self.app._telemetry_tick()
            return str(self.app.telemetry_label.cget("text"))
        finally:
            self.app.is_running = alt

    def test_der_freie_speicher_steht_vorn(self) -> None:
        text = self._tick(frei=9 * 1024 ** 3)
        self.assertIn("RAM: 9.00 GB frei (15.00 GB / 24.00 GB)", text)
        self.assertIn("CPU: 12%", text)

    def test_unter_einem_gigabyte_heisst_es_nur_noch(self) -> None:
        text = self._tick(frei=int(0.8 * 1024 ** 3))
        self.assertIn("RAM: nur noch", text)
        self.assertIn("frei", text)

    def test_genau_an_der_schwelle_ist_es_noch_nicht_knapp(self) -> None:
        self.assertNotIn("nur noch", self._tick(frei=self.app._RAM_VERDACHT_BYTES))

    def test_die_probe_liefert_den_freien_speicher(self) -> None:
        fake = mock.Mock(total=16 * 1024 ** 3, available=5 * 1024 ** 3)
        with mock.patch.object(APP, "_PSUTIL_AVAILABLE", True), \
                mock.patch.object(APP.psutil, "virtual_memory", return_value=fake), \
                mock.patch.object(APP.psutil, "cpu_percent", return_value=1.0):
            probe = self.app._sample_system_telemetry()
        self.assertEqual(5 * 1024 ** 3, probe["ram_free"])
        self.assertEqual(11 * 1024 ** 3, probe["ram_used"])

    def test_ohne_lauf_bleibt_die_anzeige_leer(self) -> None:
        alt = self.app.is_running
        self.app.is_running = False
        try:
            with mock.patch.object(self.app.root, "after"):
                self.app._telemetry_tick()
            self.assertEqual("", str(self.app.telemetry_label.cget("text")))
        finally:
            self.app.is_running = alt

    def test_die_voreinstellungs_knoepfe_gibt_es_nicht_mehr(self) -> None:
        """Nutzerwunsch 11.10.2026: wieder herausgenommen - kein Rest im Hauptfenster."""
        for name in ("_voreinstellung_knoepfe", "_voreinstellung_titel", "_voreinstellungen_setzen"):
            self.assertFalse(hasattr(self.app, name), name)
        self.assertFalse(any(schluessel.startswith("preset.") for schluessel in STRINGS), "Uebersetzungen uebrig")


if __name__ == "__main__":
    unittest.main()
