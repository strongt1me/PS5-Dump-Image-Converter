# -*- coding: utf-8 -*-
"""Das Feld KOMPRESSION (PFS) ist gesperrt, wo das Zielformat keine Stufe kennt (Nutzerwunsch 12.11.2026).

Die Stufe geht nur an ``mkpfs pack ... --compress --compression-level`` und damit nur in den komprimierten Container
``.ffpfsc``. ``.ffpfs`` wird mit ``--no-compress`` gebaut, ``.exfat`` und ``.ffpkg`` kennen keine Stufe, ein Dump-Ordner
wird nicht gepackt. Bis v1.9.97 stand das Feld bei ``.exFAT`` bedienbar da und tat nichts.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("kompression_wirkt")

from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


def _lade():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class QuelltextTests(unittest.TestCase):
    def test_texte_in_allen_sprachen(self):
        for schluessel in ("main.kompression_hint", "main.kompression_gesperrt"):
            for sprache in ("de", "en", "es", "it", "fr"):
                self.assertTrue(STRINGS[schluessel][sprache], "%s/%s" % (schluessel, sprache))

    def test_der_formatwechsel_ruft_die_schaltung(self):
        text = HAUPT.read_text(encoding="utf-8")
        koerper = text.split("def _format_hinweis_setzen")[1][:1500]
        self.assertIn("self._kompression_schalten()", koerper)

    def test_der_sprachwechsel_zieht_den_tooltip_nach(self):
        text = HAUPT.read_text(encoding="utf-8")
        stelle = text.split("self.compression_level_var.set(_new_label)")[1][:200]
        self.assertIn("self._kompression_schalten()", stelle)


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _ziel(self, modus: str, schluessel: str) -> None:
        app = self.app
        app.current_mode.set(modus)
        app._refresh_target_format_options(modus)
        app.target_format.set(app._zielformat_label(schluessel, modus))
        app._format_hinweis_setzen(modus)

    def _zustand(self) -> str:
        return str(self.app.compression_combo.cget("state"))

    def test_nur_beim_komprimierten_container_ist_das_feld_bedienbar(self):
        for modus in ("pack_folder", "pack_file", "unpack_to_exfat", "universal_convert"):
            optionen = self.app._get_target_options(modus, "")
            for ziel in ("ffpfsc", "ffpfs", "exfat", "ffpkg", "folder"):
                if ziel not in optionen:
                    continue
                with self.subTest(modus=modus, ziel=ziel):
                    self._ziel(modus, ziel)
                    soll = "readonly" if ziel == "ffpfsc" else "disabled"
                    self.assertEqual(soll, self._zustand())

    def test_aufgaben_ohne_zielformat_bleiben_bedienbar(self):
        app = self.app
        app.current_mode.set("ampr_manager")
        app._format_hinweis_setzen("ampr_manager")
        self.assertEqual("readonly", self._zustand())

    def test_die_gewaehlte_stufe_geht_beim_sperren_nicht_verloren(self):
        app = self.app
        self.addCleanup(app._save_setting, "zstd_level", 6)
        self._ziel("pack_folder", "ffpfsc")
        neu = next(t for t, s in app._zstd_level_options.items() if s == 9)
        app.compression_level_var.set(neu)
        app._on_compression_level_changed()
        self._ziel("pack_folder", "exfat")
        self.assertEqual("disabled", self._zustand())
        self.assertEqual(9, app.zstd_level, "die Stufe bleibt gemerkt")
        self.assertEqual(neu, app.compression_level_var.get(), "und steht weiter im Feld")
        self._ziel("pack_folder", "ffpfsc")
        self.assertEqual("readonly", self._zustand())
        self.assertEqual(9, app.zstd_level)

    def test_der_tooltip_sagt_warum_gesperrt(self):
        app = self.app
        tipp = app._kompression_tooltip
        self._ziel("pack_folder", "ffpfsc")
        self.assertEqual(app._t("main.kompression_hint"), tipp.text)
        self._ziel("pack_folder", "exfat")
        self.assertEqual(app._t("main.kompression_gesperrt"), tipp.text)
        self.assertIn(".ffpfsc", tipp.text)

    def test_ohne_gewaehltes_format_bleibt_das_feld_bedienbar(self):
        app = self.app
        app.current_mode.set("pack_folder")
        app.target_format.set("")
        app._format_hinweis_setzen("pack_folder")
        self.assertEqual("readonly", self._zustand())


if __name__ == "__main__":
    unittest.main()
