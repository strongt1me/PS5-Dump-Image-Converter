# -*- coding: utf-8 -*-
"""Beim Start ist die QUELLE leer, das ZIEL zeigt den letzten Ordner.

Gewuenscht am 23.08.2026. Der Grund fuer die Ungleichbehandlung:

* Stuende in der Quelle noch der Dump der letzten Sitzung, wandelte ein
  unbedachter Klick auf START den falschen um - und das faellt erst auf,
  wenn das Ergebnis da ist.
* Ein falsches Ziel faellt dagegen sofort auf: Es entsteht eine Datei am
  falschen Ort, verwechselt wird nichts.

Bequem bleibt es trotzdem: Der Durchsuchen-Dialog oeffnet weiter im zuletzt
benutzten Quellordner (eigene Einstellung ``last_source_dir``), es ist also
nur ein Klick mehr statt einer Navigation von vorn.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    # Vorhandene Wurzel weiterbenutzen: Je Prozess darf es nur eine geben,
    # und im Gesamtlauf hat meist eine andere Testdatei schon eine angelegt.
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
class StartpfadeTests(unittest.TestCase):
    """Gemessen an einer frisch gebauten Oberflaeche, nicht am Quelltext."""

    #: Beide muessen WIRKLICH existieren. Ein Quellpfad, den es nicht gibt,
    #: wird von _set_mode_from_sidebar verworfen und das Feld dadurch geleert
    #: - mit erfundenen Pfaden bestuende diese Pruefung auch ohne die
    #: Korrektur und wuerde nichts messen. Am 23.08.2026 genau darauf
    #: hereingefallen.
    QUELLE_ALT = ""
    ZIEL_ALT = ""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls._ordner = tempfile.mkdtemp(prefix="startpfade_ordner_")
        cls.QUELLE_ALT = os.path.join(cls._ordner, "ein-alter-dump")
        cls.ZIEL_ALT = os.path.join(cls._ordner, "mein-zielordner")
        os.makedirs(cls.QUELLE_ALT, exist_ok=True)
        os.makedirs(cls.ZIEL_ALT, exist_ok=True)
        for name in ("askopenfilename", "askdirectory", "asksaveasfilename"):
            setattr(cls.haupt.filedialog, name, lambda *a, **k: "")
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(cls.haupt.messagebox, name, lambda *a, **k: None)

    def _oberflaeche_mit_stand(self, src: str, dst: str):
        """Baut eine Oberflaeche, die einen vorbereiteten Stand vorfindet.

        Der echte Konfigurationspfad des Nutzers wird dabei nicht angefasst -
        die Pruefung darf nicht davon abhaengen, was dort gerade steht.
        """
        ordner = tempfile.mkdtemp(prefix="startpfade_")
        datei = os.path.join(ordner, "paths.json")
        with open(datei, "w", encoding="utf-8") as strom:
            json.dump({"src": src, "dst": dst}, strom)
        with mock.patch.object(self.haupt.PS5ConverterGUI, "_get_config_path",
                               lambda selbst: datei):
            return self.haupt.PS5ConverterGUI(_WURZEL)

    def test_quelle_startet_leer(self) -> None:
        app = self._oberflaeche_mit_stand(self.QUELLE_ALT, self.ZIEL_ALT)
        self.assertEqual(
            app.source_path.get(), "",
            "Die Quelle darf nicht vorbelegt sein - sonst wandelt ein "
            "unbedachter Klick den Dump der letzten Sitzung um.")

    def test_ziel_zeigt_den_letzten_ordner(self) -> None:
        app = self._oberflaeche_mit_stand(self.QUELLE_ALT, self.ZIEL_ALT)
        self.assertEqual(app.dest_path.get(), self.ZIEL_ALT)

    def test_ohne_gespeicherten_stand_sind_beide_leer(self) -> None:
        app = self._oberflaeche_mit_stand("", "")
        self.assertEqual(app.source_path.get(), "")
        self.assertEqual(app.dest_path.get(), "")

    def test_der_quelldialog_merkt_sich_seinen_ordner_weiter(self) -> None:
        """Sonst waere das leere Feld eine echte Verschlechterung.

        Die Bequemlichkeit steckt nicht im Feld, sondern im Startordner des
        Durchsuchen-Dialogs - und der haengt an einer eigenen Einstellung.
        """
        quelltext = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn('self._save_setting("last_source_dir"', quelltext)
        self.assertIn('self._load_setting("last_source_dir"', quelltext)


if __name__ == "__main__":
    unittest.main(verbosity=2)
