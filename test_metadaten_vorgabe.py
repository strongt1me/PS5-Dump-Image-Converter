# -*- coding: utf-8 -*-
"""Der Online-Nachschlag ist ab Werk nur auf dem Mac gesperrt.

Der Verlauf dieser Entscheidung, damit sie nicht versehentlich
zurueckgedreht wird:

* Bis v1.8.73 fragte das Programm auf **allen** Systemen ungefragt bei
  store.playstation.com, prosperopatches.com und orbispatches.com nach.
  Dabei geht die Title-ID nach draussen.
* v1.8.74 stellte das ueberall ab - aufgefallen war es auf dem Mac, wo die
  Firewall jede Verbindung meldet.
* v1.8.92 nimmt die Sperre fuer Windows und Linux zurueck. Dort ueberwiegt
  der Nutzen, und es fragt ohnehin niemand nach.

Der Kern, den diese Pruefungen sichern: **Eine ausdrueckliche Wahl gilt auf
jedem System.** Nur wer nie etwas eingestellt hat, bekommt die Vorgabe.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    # Vorhandene Wurzel weiterbenutzen: Je Prozess darf es nur eine geben.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "ohne Tk nicht messbar")
class MetadatenVorgabeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(cls.haupt.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(cls.haupt.messagebox, name, lambda *a, **k: None)
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def _erlaubt(self, macos: bool, gespeichert) -> bool:
        """Fragt die Erlaubnis fuer ein bestimmtes System und einen Stand."""
        klasse = self.haupt.PS5ConverterGUI
        with mock.patch.object(self.haupt, "IST_MACOS", macos), \
             mock.patch.object(klasse, "_load_setting",
                               lambda selbst, k, v=None, g=gespeichert: g):
            self.app._meta_nachschlag_einmalig = False
            return self.app._metadaten_online_erlaubt()

    @property
    def _nie(self):
        return self.haupt.PS5ConverterGUI._NICHTS_EINGESTELLT

    def test_windows_und_linux_fragen_ab_werk_nach(self) -> None:
        self.assertTrue(self._erlaubt(macos=False, gespeichert=self._nie))

    def test_der_mac_fragt_ab_werk_nicht(self) -> None:
        self.assertFalse(self._erlaubt(macos=True, gespeichert=self._nie))

    def test_ein_ausdrueckliches_ja_gilt_auch_auf_dem_mac(self) -> None:
        self.assertTrue(self._erlaubt(macos=True, gespeichert=True))

    def test_ein_ausdrueckliches_nein_gilt_auch_unter_windows(self) -> None:
        """Sonst waere die Einstellung dort wirkungslos."""
        self.assertFalse(self._erlaubt(macos=False, gespeichert=False))

    def test_der_knopf_hebt_die_sperre_einmalig_auf(self) -> None:
        klasse = self.haupt.PS5ConverterGUI
        with mock.patch.object(self.haupt, "IST_MACOS", True), \
             mock.patch.object(klasse, "_load_setting",
                               lambda selbst, k, v=None: False):
            self.app._meta_nachschlag_einmalig = True
            try:
                self.assertTrue(self.app._metadaten_online_erlaubt())
            finally:
                self.app._meta_nachschlag_einmalig = False

    def test_nie_eingestellt_ist_von_ausdruecklich_nein_unterscheidbar(self) -> None:
        """Der Kern der Sache.

        Mit ``False`` als Vorgabe waeren beide Faelle gleich - ein bewusstes
        Nein auf dem Mac liesse sich nicht von der Werkseinstellung trennen,
        und die Vorgabe je System waere nicht umsetzbar.
        """
        self.assertIsNot(self._nie, False)
        self.assertIsNot(self._nie, None)
        self.assertNotEqual(self._erlaubt(macos=False, gespeichert=self._nie),
                            self._erlaubt(macos=False, gespeichert=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
