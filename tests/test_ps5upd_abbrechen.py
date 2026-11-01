# -*- coding: utf-8 -*-
"""ABBRECHEN im Fenster "PS5-Update laden" (gemeldet 31.10.2026: "passiert gar nichts").

Der Faden merkt den Abbruch erst, wenn die laufende Anfrage antwortet (Verzeichnis: bis 20 s). Der Knopf muss darum
sofort sichtbar wirken: Abbruch gesetzt, Knopf gesperrt, Status "Abgebrochen".
"""
from __future__ import annotations

import sys
import threading
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None


def _alle(w):
    for k in w.winfo_children():
        yield k
        yield from _alle(k)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class AbbrechenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def test_abbrechen_wirkt_sofort_auch_waehrend_das_verzeichnis_laedt(self) -> None:
        app, haupt = self.app, self.haupt
        frei = threading.Event()
        gesehen: dict = {}

        def haengt(url, abbruch=None):
            frei.wait(5)
            gesehen["abbruch"] = bool(abbruch and abbruch())
            raise haupt.ps5_updates.UpdateFehler("ps5upd.abgebrochen")

        info = {"name": "X", "version": "01.000.000", "dateiname": "x.pkg", "manifest_url": "https://x/m.json",
                "gesamt": 0}
        with mock.patch.object(haupt.ps5_updates, "manifest_holen", side_effect=haengt):
            app._sony_ladefenster(info, "x.pkg")
            win = app._sony_lauf["win"]
            try:
                text = app._t("ps5upd.knopf_abbrechen")
                knoepfe = [w for w in _alle(win) if getattr(w, "_text", None) == text]
                self.assertTrue(knoepfe, "Anker: der Knopf ABBRECHEN ist da.")
                knoepfe[0].invoke()
                fertig = time.time() + 2
                while time.time() < fertig:
                    _WURZEL.update()
                    time.sleep(0.02)
                texte = [str(w.cget("text")) for w in _alle(win) if isinstance(w, tk.Label)]
                self.assertIn(app._t("ps5upd.abgebrochen"), texte, "Der Status zeigt gleich 'Abgebrochen'.")
                self.assertEqual("disabled", getattr(knoepfe[0], "_state", ""))
            finally:
                frei.set()
                for _ in range(30):
                    _WURZEL.update()
                    time.sleep(0.02)
                try:
                    win.destroy()
                except tk.TclError:
                    pass
        self.assertTrue(gesehen.get("abbruch"), "Der Faden sieht den gesetzten Abbruch.")


if __name__ == "__main__":
    unittest.main()
