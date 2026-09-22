# -*- coding: utf-8 -*-
"""Das zusammengelegte Fenster "PKG bauen" (seit v1.9.41).

Bis v1.9.40 gab es "PKG bauen" (Dump-Ordner) und "Abbild -> PKG" (Abbilder)
als zwei Fenster mit demselben Bau dahinter, dazu "DEBUG-PKG BAUEN" als
unsignierten Eigenbau. Jetzt nimmt ein Fenster Ordner **oder** Abbild.

Geprueft am echten Fenster, der Bau selbst (``prosperopkg``) ist ersetzt:

* Bei einem **Ordner** sind Ziel-Firmware und PlayGo gesperrt - beide
  schreiben in ``param.json``, und das waere der Ordner des Anwenders.
  "Pruefen" ist frei. Bei einem **Abbild** umgekehrt.
* Ein Ordner wird **ohne Entpacken** gebaut, und seine ``param.json`` bleibt
  bytegleich.
* "Homebrew" sperrt "Lizenzfrei bauen" und baut ueber ``homebrew_bauen``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

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


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class PkgBauenFensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        # Im Volllauf gilt sonst die Sprache des zuletzt importierten Moduls.
        cls.app._current_language = "de"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ordner = os.path.join(self._tmp.name, "PPSA01234")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        self.param = os.path.join(self.ordner, "sce_sys", "param.json")
        with open(self.param, "w", encoding="utf-8") as datei:
            json.dump({"titleId": "PPSA01234", "contentVersion": "01.000.000",
                       "requiredSystemSoftwareVersion": "0x0700000000000000"}, datei)
        self.abbild = os.path.join(self._tmp.name, "spiel.exfat")
        with open(self.abbild, "wb") as datei:
            datei.write(b"\0" * 64)
        self.ziel = os.path.join(self._tmp.name, "aus")
        vorher = set(_WURZEL.winfo_children())
        with mock.patch.object(self.haupt.prosperopkg, "werkzeug_finden",
                               return_value="prosperopkg"):
            self.app._show_pkg_bauen()
        _WURZEL.update_idletasks()
        neu = [w for w in _WURZEL.winfo_children()
               if w not in vorher and isinstance(w, tk.Toplevel)]
        self.assertTrue(neu, "Kein Fenster geoeffnet.")
        self.win = neu[0]

    def tearDown(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self._tmp.cleanup()

    # -- Hilfen ------------------------------------------------------------
    def _alle(self, widget=None):
        for kind in (widget or self.win).winfo_children():
            yield kind
            yield from self._alle(kind)

    def _mit_text(self, klasse, schluessel):
        text = self.app._t(schluessel)
        for w in self._alle():
            if isinstance(w, klasse):
                try:
                    if str(w.cget("text")) == text:
                        return w
                except tk.TclError:
                    continue
        self.fail("%s mit Text %r fehlt" % (klasse.__name__, text))

    def _eingaben(self):
        return [w for w in self._alle() if isinstance(w, tk.Entry)]

    def _quelle_setzen(self, pfad):
        feld = self._eingaben()[0]
        feld.delete(0, "end")
        feld.insert(0, pfad)
        _WURZEL.update_idletasks()

    def _zustand(self, widget):
        return str(widget.cget("state"))

    def _bauen_und_warten(self, bauen=None, homebrew_bauen=None):
        """Druckt "Paket bauen" und wartet, bis der Knopf wieder frei ist."""
        self._eingaben()[1].insert(0, self.ziel)
        knopf = self._mit_text(ttk.Button, "pkgbau.build_button")
        aufrufe = []

        def _bau(name):
            def _fake(quelle, ziel, **kwargs):
                aufrufe.append((name, quelle, ziel, kwargs))
                os.makedirs(ziel, exist_ok=True)
                pfad = os.path.join(ziel, "x.pkg")
                open(pfad, "wb").close()
                return pfad
            return _fake

        def _nie(*_a, **_k):
            raise AssertionError("Ein Ordner darf nicht entpackt werden.")

        with mock.patch.object(self.haupt.prosperopkg, "bauen", bauen or _bau("bauen")), \
                mock.patch.object(self.haupt.prosperopkg, "homebrew_bauen",
                                  homebrew_bauen or _bau("homebrew_bauen")), \
                mock.patch.object(self.app, "_abbild_zu_dumpordner", _nie), \
                mock.patch.object(self.haupt, "messagebox"):
            knopf.invoke()
            ende = time.monotonic() + 10
            while time.monotonic() < ende:
                _WURZEL.update()
                if aufrufe and self._zustand(knopf) == "normal":
                    break
                time.sleep(0.02)
            for _ in range(10):
                _WURZEL.update()
        return aufrufe

    # -- Pruefungen --------------------------------------------------------
    def test_ordner_sperrt_firmware_und_playgo_und_gibt_pruefen_frei(self):
        self._quelle_setzen(self.ordner)
        firmware = next(w for w in self._alle() if isinstance(w, ttk.Combobox))
        playgo = self._mit_text(tk.Checkbutton, "exfatpkg.playgo_fix")
        pruefen = self._mit_text(ttk.Button, "pkgbau.check_button")
        self.assertEqual("disabled", self._zustand(firmware))
        self.assertEqual("disabled", self._zustand(playgo))
        self.assertEqual("normal", self._zustand(pruefen))

    def test_abbild_gibt_firmware_und_playgo_frei_und_sperrt_pruefen(self):
        self._quelle_setzen(self.abbild)
        firmware = next(w for w in self._alle() if isinstance(w, ttk.Combobox))
        playgo = self._mit_text(tk.Checkbutton, "exfatpkg.playgo_fix")
        pruefen = self._mit_text(ttk.Button, "pkgbau.check_button")
        self.assertEqual("normal", self._zustand(firmware))
        self.assertEqual("normal", self._zustand(playgo))
        self.assertEqual("disabled", self._zustand(pruefen))

    def test_ordner_wird_ohne_entpacken_und_unveraendert_gebaut(self):
        vorher = open(self.param, "rb").read()
        self._quelle_setzen(self.ordner)
        aufrufe = self._bauen_und_warten()
        self.assertEqual(1, len(aufrufe), aufrufe)
        name, quelle, ziel, kwargs = aufrufe[0]
        self.assertEqual("bauen", name)          # ab Werk Spiel-Backup
        self.assertEqual(os.path.normcase(self.ordner), os.path.normcase(quelle))
        self.assertEqual(self.ziel, ziel)
        self.assertTrue(kwargs.get("lizenzfrei"))
        self.assertEqual(vorher, open(self.param, "rb").read())

    def test_homebrew_sperrt_lizenzfrei_und_baut_als_homebrew(self):
        self._mit_text(tk.Radiobutton, "pkgbau.kind_homebrew").invoke()
        lizenzfrei = self._mit_text(tk.Checkbutton, "pkgbau.license_free")
        self.assertEqual("disabled", self._zustand(lizenzfrei))
        self._quelle_setzen(self.ordner)
        aufrufe = self._bauen_und_warten()
        self.assertEqual(["homebrew_bauen"], [a[0] for a in aufrufe])
        self.assertNotIn("lizenzfrei", aufrufe[0][3])

    def test_keine_quelle_wird_abgewiesen(self):
        self._quelle_setzen(os.path.join(self._tmp.name, "gibt_es_nicht"))
        with mock.patch.object(self.haupt, "messagebox") as box:
            self._mit_text(ttk.Button, "pkgbau.build_button").invoke()
        box.showwarning.assert_called_once()
        self.assertEqual(self.app._t("pkgbau.need_source_any"),
                         box.showwarning.call_args[0][1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
