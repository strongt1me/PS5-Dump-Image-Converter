# -*- coding: utf-8 -*-
"""Der Knopf „unjail senden" unter WEITERE TOOLS.

unjail ist ein Konsolen-Payload (SvenGDK). Das Fenster schickt die
mitgelieferte ``unjail-ps5app-payload.elf`` über denselben erprobten Weg wie
jeder andere Payload (``_send_payload_to_ps5``). Geprüft wird das
Nachvollziehbare ohne echten Versand: die Menü-Verdrahtung, die
Zweisprachigkeit, dass die ELF wirklich mitgeliefert wird, dass das Fenster
sich aufbaut und dass der Sende-Knopf am erprobten Versandweg hängt.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")
ELF = os.path.join("helloworld", "unjail-ps5app-payload.elf")

try:
    import tkinter as tk
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


class VerdrahtungUndTexteTests(unittest.TestCase):
    """Menü-Eintrag, mitgelieferte ELF und vollständige Zweisprachigkeit."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = open(HAUPTDATEI, encoding="utf-8").read()

    def test_eintrag_im_menue(self):
        baum = ast.parse(self.quelle)
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")

        def _ist_liste(z):
            if isinstance(z, ast.AnnAssign):
                return getattr(z.target, "id", "") == "_MORE_TOOLS_ENTRIES"
            if isinstance(z, ast.Assign):
                return any(getattr(t, "id", "") == "_MORE_TOOLS_ENTRIES"
                           for t in z.targets)
            return False

        eintraege = ast.literal_eval(next(z for z in klasse.body if _ist_liste(z)).value)
        self.assertIn(("titlebar.unjail", "_show_unjail_sender"), eintraege)

    def test_elf_wird_mitgeliefert(self):
        self.assertTrue(os.path.isfile(ELF),
                        "Der unjail-Payload fehlt in helloworld/.")
        with open(ELF, "rb") as f:
            self.assertEqual(b"\x7fELF", f.read(4), "Keine gültige ELF-Datei.")

    def test_sende_knopf_haengt_am_erprobten_versandweg(self):
        """Der Knopf muss _send_payload_to_ps5 nutzen, nicht einen Eigenbau."""
        baum = ast.parse(self.quelle)
        methode = next(k for k in ast.walk(baum)
                       if isinstance(k, ast.FunctionDef)
                       and k.name == "_show_unjail_sender")
        rumpf = ast.unparse(methode)
        self.assertIn("_send_payload_to_ps5", rumpf)
        self.assertIn("_UNJAIL_ELF", rumpf)

    def test_alle_texte_zweisprachig(self):
        from ps5_validator.utils import i18n
        schluessel = [k for k in i18n.STRINGS
                      if k.startswith("unjail.")] + ["titlebar.unjail"]
        self.assertGreaterEqual(len(schluessel), 14)
        for k in schluessel:
            with self.subTest(key=k):
                eintrag = i18n.STRINGS[k]
                self.assertTrue(eintrag.get("de"), "de fehlt: " + k)
                self.assertTrue(eintrag.get("en"), "en fehlt: " + k)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class FensterRauchtest(unittest.TestCase):
    """Das Fenster baut sich auf, ohne etwas an die Konsole zu senden."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def test_fenster_oeffnet_ohne_versand(self):
        vorher = set(_WURZEL.winfo_children())
        # _send_payload_to_ps5 wird gemockt: Der Rauchtest darf NIE wirklich
        # etwas an eine Konsole schicken.
        with mock.patch.object(self.haupt, "messagebox"), \
                mock.patch.object(self.app, "_send_payload_to_ps5",
                                  return_value=(True, "2.4 MB")) as versand:
            self.app._show_unjail_sender()
            _WURZEL.update_idletasks()
            neu = [w for w in _WURZEL.winfo_children()
                   if w not in vorher and isinstance(w, tk.Toplevel)]
            try:
                self.assertTrue(neu, "Kein Fenster geöffnet.")
                versand.assert_not_called()  # Öffnen darf nichts senden.
            finally:
                for w in neu:
                    w.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
