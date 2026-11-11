# -*- coding: utf-8 -*-
"""Packverfahren (LZ4 / zstd) unter der Methode in der AMPR-Einbauzeile (Nutzerwunsch 11.11.2026).

Das Feld sitzt in der zweiten Zeile unter "Normal"/"Asset-Pack" und schreibt dieselbe Einstellung wie das Feld in den
Einstellungen. Regeln:

* Waehlbar nur bei angehaktem AMPR EMU **und** Methode Asset-Pack; bei Normal bleibt es ausgegraut (der gespeicherte Wert
  steht weiter darin), und es wird nichts mit LZ4 oder zstd gepackt.
* zstd: Die Versionsliste zeigt nur ampr-emu-ng, und ist die gewaehlte Fassung nicht NG, wird die neueste normale
  NG-Fassung gewaehlt (nicht die Debug-Fassung). Eine schon von Hand gewaehlte NG-Fassung bleibt.
* LZ4: Alles bleibt frei.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("packverfahren_feld")

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

    @classmethod
    def setUpClass(cls) -> None:
        import ast
        text = HAUPT.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        cls.f = {}
        for k in ast.walk(ast.parse(text)):
            if isinstance(k, ast.FunctionDef):
                cls.f[k.name] = "\n".join(zeilen[k.lineno - 1:k.end_lineno])

    def test_das_feld_haengt_an_methode_und_haken(self):
        quelle = self.f["_ampr_pack_combo_schalten"]
        self.assertIn("AMPR_METHODE_ASSETPACK", quelle)
        self.assertIn("ampr_integrate_var", quelle)

    def test_die_integrationsschaltung_ruft_es(self):
        self.assertIn("_ampr_pack_combo_schalten()", self.f["_on_integration_changed"])

    def test_der_einstellungsdialog_zieht_das_feld_nach(self):
        text = HAUPT.read_text(encoding="utf-8")
        self.assertIn("self._ampr_pack_combo_schalten()", text.split("def _verfahren_gewaehlt")[1][:900])

    def test_texte(self):
        for sprache in ("de", "en", "es", "it", "fr"):
            self.assertTrue(STRINGS["ampr_pack.verfahren_hint"][sprache])


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        app = self.app
        app._save_setting("ampr_pack_verfahren", "lz4")
        app._save_setting("integrate_ampr_version", "")
        app.ampr_integrate_var.set(False)
        app.ampr_methode_var.set(next(t for t, k in app._ampr_methode_options.items()
                                      if k == self.haupt.AMPR_METHODE_NORMAL))
        app._ampr_versionsliste_fuellen()
        app._on_integration_changed(speichern=False)
        self.addCleanup(self._zurueck)

    def _zurueck(self) -> None:
        self.app._save_setting("ampr_pack_verfahren", "lz4")

    def _methode(self, neu: str) -> None:
        """Waehlt die Methode ueber die Tabelle der Oberflaeche (Anzeigetext -> Kennung), unabhaengig von der Sprache."""
        app = self.app
        ziel = self.haupt.AMPR_METHODE_ASSETPACK if neu == "pack" else self.haupt.AMPR_METHODE_NORMAL
        text = next(t for t, kennung in app._ampr_methode_options.items() if kennung == ziel)
        app.ampr_methode_var.set(text)
        app._on_ampr_methode_changed()
        app._ampr_pack_combo_schalten()

    def _zustand(self) -> str:
        return str(self.app.ampr_pack_combo.cget("state"))

    def test_ohne_haken_gesperrt(self):
        self.assertEqual("disabled", self._zustand())

    def test_bei_normal_gesperrt_auch_mit_haken(self):
        self.app.ampr_integrate_var.set(True)
        self.app._on_integration_changed(speichern=False)
        self.assertEqual("disabled", self._zustand())

    def test_bei_asset_pack_und_haken_waehlbar(self):
        self.app.ampr_integrate_var.set(True)
        self.app._on_integration_changed(speichern=False)
        self._methode("pack")
        self.assertEqual("readonly", self._zustand())

    def test_zurueck_auf_normal_sperrt_wieder_und_zeigt_den_gespeicherten_wert(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self._methode("normal")
        self.assertEqual("disabled", self._zustand())
        self.assertEqual("zstd", app._ampr_pack_var.get())

    def test_zstd_waehlt_die_neueste_normale_ng_fassung(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app.ampr_version_var.set(next(iter(app._ampr_versionsauswahl)))          # irgendeine packfaehige, nicht NG
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        wahl = app._ampr_versionsauswahl[app.ampr_version_var.get()]
        self.assertEqual("ng", str(wahl["variant"]).lower(), "neueste normale NG-Fassung, nicht die Debug-Fassung")
        alle = [e for e in app._ampr_versionsauswahl.values() if str(e["variant"]).lower() == "ng"]
        self.assertEqual(alle[0]["version"], wahl["version"], "die neueste steht in der Liste oben")
        self.assertEqual("zstd", app._ampr_pack_verfahren())
        self.assertTrue(all(str(e["variant"]).lower() in ("ng", "ng-debug")
                            for e in app._ampr_versionsauswahl.values()), "bei zstd bietet die Liste nur NG an")

    def test_eine_von_hand_gewaehlte_ng_fassung_bleibt(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        ng = [b for b, e in app._ampr_versionsauswahl.items() if str(e["variant"]).lower() == "ng"]
        waehlen = ng[1] if len(ng) > 1 else ng[0]
        app.ampr_version_var.set(waehlen)
        app._save_setting("integrate_ampr_version", waehlen)
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self.assertEqual(waehlen, app.ampr_version_var.get())

    def test_lz4_laesst_die_wahl_frei(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        app._ampr_pack_var.set("LZ4")
        app._ampr_pack_gewaehlt()
        self.assertEqual("lz4", app._ampr_pack_verfahren())
        varianten = {str(e["variant"]).lower() for e in app._ampr_versionsauswahl.values()}
        self.assertTrue(varianten - {"ng", "ng-debug"}, "bei LZ4 stehen wieder alle packfaehigen Fassungen da")

    def test_der_tooltip_sagt_beim_gesperrten_feld_wann_es_frei_wird(self):
        app = self.app
        tipp = app._ampr_pack_tooltip
        self.assertEqual(app._t("ampr_pack.verfahren_gesperrt"), tipp.text)       # ohne Haken, Normal
        self.assertIn("Asset-Pack", tipp.text)
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self.assertEqual(app._t("ampr_pack.verfahren_gesperrt"), tipp.text)       # Haken, aber Normal
        self._methode("pack")
        self.assertEqual(app._t("ampr_pack.verfahren_hint"), tipp.text)           # frei: die Erklaerung
        self._methode("normal")
        self.assertEqual(app._t("ampr_pack.verfahren_gesperrt"), tipp.text)

    def test_der_tooltip_zeigt_sich_auch_am_gesperrten_feld(self):
        """Ein ttk-Feld im Zustand disabled bekommt weiter <Enter>; ``_show`` baut das Hinweisfenster mit dem Text."""
        tipp = self.app._ampr_pack_tooltip
        tipp._show()
        try:
            self.assertIsNotNone(tipp._tip_window, "der Hinweis erscheint, auch wenn das Feld gesperrt ist")
        finally:
            tipp._hide()

    def test_unbekannte_auswahl_aendert_nichts(self):
        app = self.app
        app._ampr_pack_var.set("irgendwas")
        with mock.patch.object(app, "_save_setting") as speichern:
            app._ampr_pack_gewaehlt()
        speichern.assert_not_called()


if __name__ == "__main__":
    unittest.main()
