# -*- coding: utf-8 -*-
"""Ein gesperrter Knopf muss anders aussehen als ein bedienbarer.

Am 22.09.2026 in der fertigen EXE v1.9.40 gesehen: Im Fenster "PKG
entpacken" sind "Abbrechen" und "Zielordner oeffnen" im Leerlauf gesperrt,
sahen aber genauso aus wie "Schliessen". Die Sperre selbst stimmte (ein Klick
tat nichts) - nur der Stil ``TButton`` kannte keinen Zustand "disabled".
``Accent.TButton`` und ``Error.TButton`` hatten ihn laengst.

Die Klasse, nicht der Einzelfall: Geprueft wird **jeder** Knopfstil, den
``_setup_styles`` anlegt, in **jedem** Design - am echten ``ttk.Style``, nicht
am Quelltext. Kommt ein neuer Knopfstil ohne gesperrten Zustand dazu, faellt
dieser Test.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def _knopfstile() -> list[str]:
    """Alle Knopfstile, die ``_setup_styles`` konfiguriert - aus dem Quelltext.

    Nur die **Namen** kommen aus dem Quelltext; geprueft wird am laufenden
    Stil. So faellt ein neu hinzugekommener Stil automatisch mit hinein.
    """
    with open(HAUPTDATEI, encoding="utf-8") as datei:
        quelle = datei.read()
    anfang = quelle.index("    def _setup_styles(self)")
    ende = quelle.index("\n    def ", anfang + 10)
    return sorted(set(re.findall(r'style\.configure\("([A-Za-z.]*TButton)"',
                                 quelle[anfang:ende])))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class GesperrteKnoepfeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        klasse = cls.haupt.PS5ConverterGUI
        # Attrappe statt ganzem Programmfenster: _setup_styles braucht nur
        # root und die Palette. Eine einzige Attrappe fuer alle Designs, damit
        # die Fokus-Bindung nicht mehrfach gesetzt wird.
        cls.app = klasse.__new__(klasse)
        cls.app.root = _WURZEL
        cls.designs = list(klasse._THEMES)
        cls.stile = _knopfstile()

    @classmethod
    def tearDownClass(cls):
        # Den Stil so hinterlassen, wie das Programm ab Werk startet.
        cls.app._COLORS = dict(cls.haupt.PS5ConverterGUI._THEMES["dunkel"])
        cls.app._setup_styles()

    def test_es_gibt_etwas_zu_pruefen(self):
        """Anker: Findet die Suche nichts, waere der Test klaglos gruen."""
        self.assertIn("TButton", self.stile)
        self.assertGreaterEqual(len(self.stile), 3)
        self.assertGreaterEqual(len(self.designs), 4)

    def test_gesperrt_sieht_anders_aus(self):
        style = ttk.Style()
        for design in self.designs:
            self.app._COLORS = dict(self.haupt.PS5ConverterGUI._THEMES[design])
            self.app._setup_styles()
            for stil in self.stile:
                with self.subTest(design=design, stil=stil):
                    normal = style.lookup(stil, "foreground")
                    gesperrt = style.lookup(stil, "foreground", ["disabled"])
                    self.assertTrue(gesperrt, "kein Zustand 'disabled'")
                    self.assertNotEqual(
                        normal.lower(), gesperrt.lower(),
                        "gesperrt und bedienbar gleich (%s)" % normal)

    def test_gesperrt_gewinnt_auch_unter_der_maus(self):
        """ttk nimmt den ersten passenden Zustand - die Reihenfolge zaehlt."""
        style = ttk.Style()
        for design in self.designs:
            self.app._COLORS = dict(self.haupt.PS5ConverterGUI._THEMES[design])
            self.app._setup_styles()
            for stil in self.stile:
                with self.subTest(design=design, stil=stil):
                    gesperrt = style.lookup(stil, "foreground", ["disabled"])
                    beides = style.lookup(stil, "foreground", ["disabled", "active"])
                    self.assertEqual(gesperrt.lower(), beides.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
