# -*- coding: utf-8 -*-
"""Der Knopf „exFAT → PKG" unter WEITERE TOOLS.

Der Weg verkettet zwei Dinge, die das Programm schon einzeln kann: ein
.exfat-Abbild nativ entpacken (wie Aufgabe 3) und aus dem Dump-Ordner ein
Debug-Paket bauen (wie „PKG bauen"). Neu ist nur die Ziel-Firmware, die vor
dem Bauen in ``param.json`` gesetzt wird.

Geprüft wird das Nachvollziehbare ohne echten Lauf: das BCD-Packmass der
Firmware, das Umschreiben der ``param.json`` (Felder gesetzt, Reihenfolge und
übrige Angaben unberührt), das Finden der Spielwurzel, die Verdrahtung im
Menü und dass jeder Text zweisprachig vorliegt. Ein Rauchtest öffnet das
Fenster wirklich.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

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
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


PARAM_VORLAGE = {
    "applicationCategoryType": 0,
    "contentId": "EP0001-PPSA10528_00-MEMORYRETAIL0000",
    "titleId": "PPSA10528",
    "contentVersion": "01.004.001",
    "masterVersion": "01.00",
    "requiredSystemSoftwareVersion": "0x1001000000000000",
    "sdkVersion": "0x0700000000000000",
    "localizedParameters": {"defaultLanguage": "de-DE",
                            "de-DE": {"titleName": "Messung"}},
}


class SdkBcdTests(unittest.TestCase):
    """Das Packmass, das die Konsole in param.json erwartet."""

    @classmethod
    def setUpClass(cls):
        cls.G = _lade_hauptprogramm().PS5ConverterGUI

    def test_bekannte_werte(self):
        self.assertEqual("0x1001000000000000", self.G._sdk_bcd(10, 1))
        self.assertEqual("0x0900000000000000", self.G._sdk_bcd(9, 0))
        self.assertEqual("0x1200000000000000", self.G._sdk_bcd(12, 0))

    def test_ausserhalb_wird_abgewiesen(self):
        with self.assertRaises(ValueError):
            self.G._sdk_bcd(100, 0)

    def test_firmware_lesen(self):
        self.assertEqual((10, 1), self.G._exfat_pkg_firmware_lesen("10.01"))
        self.assertEqual((9, 0), self.G._exfat_pkg_firmware_lesen("9"))
        self.assertIsNone(self.G._exfat_pkg_firmware_lesen(""))
        self.assertIsNone(
            self.G._exfat_pkg_firmware_lesen("(Original behalten)"))

    def test_firmware_unsinn_wirft(self):
        for text in ("abc", "10.0.1", "-1"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    self.G._exfat_pkg_firmware_lesen(text)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ParamUndWurzelTests(unittest.TestCase):
    """param.json umschreiben und die Spielwurzel finden."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def _dump(self, unterordner: bool):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        wurzel = os.path.join(tmp.name, "spiel") if unterordner else tmp.name
        sce = os.path.join(wurzel, "sce_sys")
        os.makedirs(sce)
        with open(os.path.join(sce, "param.json"), "w", encoding="utf-8") as f:
            json.dump(PARAM_VORLAGE, f, ensure_ascii=False, indent=2)
        return tmp.name, wurzel

    def test_param_setzen_aendert_nur_zwei_felder(self):
        _basis, wurzel = self._dump(unterordner=False)
        param = os.path.join(wurzel, "sce_sys", "param.json")
        hexwert = self.app._sdk_bcd(10, 0)
        alt_sdk, alt_req = self.app._exfat_pkg_param_setzen(param, hexwert)
        self.assertEqual("0x0700000000000000", alt_sdk)
        self.assertEqual("0x1001000000000000", alt_req)
        with open(param, encoding="utf-8") as f:
            neu = json.load(f)
        self.assertEqual(hexwert, neu["sdkVersion"])
        self.assertEqual(hexwert, neu["requiredSystemSoftwareVersion"])
        # Alles andere unberührt, Reihenfolge erhalten.
        self.assertEqual(list(PARAM_VORLAGE.keys()), list(neu.keys()))
        self.assertEqual(PARAM_VORLAGE["contentId"], neu["contentId"])
        self.assertEqual(PARAM_VORLAGE["localizedParameters"],
                         neu["localizedParameters"])

    def test_spielwurzel_direkt(self):
        _basis, wurzel = self._dump(unterordner=False)
        self.assertEqual(os.path.realpath(wurzel),
                         os.path.realpath(self.app._exfat_pkg_spielwurzel(wurzel)))

    def test_spielwurzel_eine_ebene_tiefer(self):
        basis, wurzel = self._dump(unterordner=True)
        self.assertEqual(os.path.realpath(wurzel),
                         os.path.realpath(self.app._exfat_pkg_spielwurzel(basis)))

    def test_spielwurzel_ohne_param_bleibt_beim_ordner(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        os.makedirs(os.path.join(tmp.name, "leer"))
        self.assertEqual(os.path.realpath(tmp.name),
                         os.path.realpath(self.app._exfat_pkg_spielwurzel(tmp.name)))


class MenueUndTexteTests(unittest.TestCase):
    """Verdrahtung im Menü und vollständige Zweisprachigkeit."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.quelle = open(HAUPTDATEI, encoding="utf-8").read()

    def test_eintrag_im_menue(self):
        baum = ast.parse(self.quelle)
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")

        def _ist_eintragsliste(z) -> bool:
            # _MORE_TOOLS_ENTRIES traegt eine Typ-Annotation, ist also ein
            # AnnAssign; ein schlichtes Assign gaebe es auch. Beide abdecken.
            if isinstance(z, ast.AnnAssign):
                return getattr(z.target, "id", "") == "_MORE_TOOLS_ENTRIES"
            if isinstance(z, ast.Assign):
                return any(getattr(t, "id", "") == "_MORE_TOOLS_ENTRIES"
                           for t in z.targets)
            return False

        eintraege = next(z for z in klasse.body if _ist_eintragsliste(z))
        paare = ast.literal_eval(eintraege.value)
        self.assertIn(("titlebar.exfat_pkg", "_show_exfat_pkg_builder"), paare)

    def test_alle_texte_zweisprachig(self):
        from ps5_validator.utils import i18n
        schluessel = [k for k in i18n.STRINGS
                      if k.startswith("exfatpkg.")] + ["titlebar.exfat_pkg"]
        self.assertGreaterEqual(len(schluessel), 20)
        for k in schluessel:
            with self.subTest(key=k):
                eintrag = i18n.STRINGS[k]
                self.assertTrue(eintrag.get("de"), "de fehlt: " + k)
                self.assertTrue(eintrag.get("en"), "en fehlt: " + k)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class FensterRauchtest(unittest.TestCase):
    """Das Fenster baut sich wirklich auf, ohne Interaktion."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def test_fenster_oeffnet_und_schliesst(self):
        vorher = set(_WURZEL.winfo_children())
        # messagebox abfangen: fehlt prosperopkg, käme sonst ein blockierender
        # Dialog. Auf diesem Rechner ist es zwar gebaut, aber der Test soll
        # nicht daran hängen.
        with mock.patch.object(self.haupt, "messagebox"):
            self.app._show_exfat_pkg_builder()
            _WURZEL.update_idletasks()
            neu = [w for w in _WURZEL.winfo_children()
                   if w not in vorher and isinstance(w, tk.Toplevel)]
            try:
                self.assertTrue(neu, "Kein Fenster geöffnet.")
                texte = self._sammle_text(neu[0])
                self.assertTrue(any("exFAT" in t for t in texte))
            finally:
                for w in neu:
                    w.destroy()

    @staticmethod
    def _sammle_text(widget):
        gefunden = []
        for kind in widget.winfo_children():
            try:
                wert = kind.cget("text")
                if wert:
                    gefunden.append(str(wert))
            except tk.TclError:
                pass
            gefunden.extend(FensterRauchtest._sammle_text(kind))
        return gefunden


if __name__ == "__main__":
    unittest.main(verbosity=2)
