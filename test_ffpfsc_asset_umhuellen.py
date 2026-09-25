# -*- coding: utf-8 -*-
"""ffpfsc -> ffpfsc (Aufgabe 2) nur mit AMPR-EMU-Asset-Pack.

Wunsch des Anwenders vom 15.09.2026: Aufgabe 2 soll ffpfsc -> ffpfsc anbieten,
aber die Auswahl nur zeigen, wenn das AMPR-EMU-Asset-Pack gewaehlt ist. Ist es
gewaehlt, soll der Start entpacken -> Asset-Pack in den Dump-Ordner einbauen ->
als .ffpfsc neu packen (wie es die Entwickler-Anleitung beschreibt), ohne eine
Ja/Nein-Rueckfrage.

Gemessen wird am laufenden Fenster (Sichtbarkeit ueber die tatsaechliche
Zielliste) und an der Verdrahtung (welcher Modus-Weg aufgerufen wird).
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

# Vor dem Laden des Hauptprogramms den Konfigordner umlenken - sonst schriebe
# der Lauf in den Einstellungsordner des Nutzers (siehe project_testaufbau).
_TMP_KFG = tempfile.mkdtemp(prefix="ffpfsc_asset_kfg_")
os.environ["PS5CONV_KONFIGORDNER"] = _TMP_KFG

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


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FfpfscAssetTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.AP = cls.haupt.AMPR_METHODE_ASSETPACK
        cls.NORMAL = cls.haupt.AMPR_METHODE_NORMAL

    def _methode_setzen(self, wert):
        for text, w in self.app._ampr_methode_options.items():
            if w == wert:
                self.app.ampr_methode_var.set(text)
                return
        self.fail("Methode nicht in den Optionen: %s" % wert)

    def _asset_an(self):
        self.app.ampr_integrate_var.set(True)
        self._methode_setzen(self.AP)

    def _asset_aus(self):
        self.app.ampr_integrate_var.set(False)
        self._methode_setzen(self.NORMAL)

    def test_einhuellende_wege_kennen_ffpfsc_ffpfsc(self):
        self.assertIn(("ffpfsc", "ffpfsc"), self.app._EINHUELLENDE_WEGE)

    def test_ohne_assetpack_keine_ffpfsc_option(self):
        self._asset_aus()
        ziele = self.app._get_target_options("unpack_to_exfat", "")
        self.assertNotIn("ffpfsc", ziele,
                         "Ohne Asset-Pack darf ffpfsc->ffpfsc nicht angeboten "
                         "werden: %r" % (ziele,))

    def test_mit_assetpack_erscheint_ffpfsc(self):
        self._asset_an()
        ziele = self.app._get_target_options("unpack_to_exfat", "")
        self.assertIn("ffpfsc", ziele,
                      "Mit Asset-Pack muss ffpfsc->ffpfsc angeboten werden: %r"
                      % (ziele,))

    def test_ampr_normal_zeigt_ffpfsc_nicht(self):
        """AMPR angehakt, aber Methode Normal - das ist KEIN Asset-Pack."""
        self.app.ampr_integrate_var.set(True)
        self._methode_setzen(self.NORMAL)
        ziele = self.app._get_target_options("unpack_to_exfat", "")
        self.assertNotIn("ffpfsc", ziele)

    def test_andere_aufgaben_bleiben_unberuehrt(self):
        """Die Sonderregel gilt nur fuer Aufgabe 2 (unpack_to_exfat)."""
        self._asset_aus()
        # Aufgabe 1 bietet ffpfsc unabhaengig vom Asset-Pack an.
        self.assertIn("ffpfsc", self.app._get_target_options("pack_folder", ""))

    def test_umhuellen_packt_ohne_rueckfrage_neu(self):
        """ffpfsc->ffpfsc setzt den Neu-Packen-Merker, ohne Ja/Nein zu fragen."""
        self._asset_an()
        self.app._umhuellt_neu_packen = False
        with mock.patch.object(self.app, "_ask_yesno_threadsafe",
                               side_effect=AssertionError("darf nicht fragen")) as frage, \
             mock.patch.object(self.app, "_resolve_mode_source_type",
                               return_value="ffpfsc"), \
             mock.patch.object(self.app, "_append_to_log"):
            darf = self.app._umhuellenden_weg_klaeren(
                "unpack_to_exfat", "Spiel.ffpfsc", "ffpfsc")
        frage.assert_not_called()
        self.assertTrue(darf)
        self.assertTrue(self.app._umhuellt_neu_packen)

    def test_routing_mit_merker_geht_ueber_dump_ordner(self):
        self.app._umhuellt_neu_packen = True
        with mock.patch.object(self.app, "_mode_abbild_zu_ffpfs",
                               return_value=True) as neu, \
             mock.patch.object(self.app, "_mode_ffpfsc_umpacken",
                               return_value=True) as um:
            self.app._execute_conversion_by_type("ffpfsc", "ffpfsc", "S.ffpfsc", "Z")
        self.assertTrue(neu.called)
        self.assertEqual("ffpfsc", neu.call_args.kwargs.get("quelle"))
        self.assertFalse(neu.call_args.kwargs.get("uncompressed", True))
        self.assertFalse(um.called)

    def test_routing_ohne_merker_bleibt_reines_umpacken(self):
        self.app._umhuellt_neu_packen = False
        with mock.patch.object(self.app, "_mode_abbild_zu_ffpfs",
                               return_value=True) as neu, \
             mock.patch.object(self.app, "_mode_ffpfsc_umpacken",
                               return_value=True) as um:
            self.app._execute_conversion_by_type("ffpfsc", "ffpfsc", "S.ffpfsc", "Z")
        self.assertTrue(um.called)
        self.assertFalse(neu.called)

    def test_abbild_zu_ffpfs_entpackt_ffpfsc_ueber_game_folder(self):
        """quelle='ffpfsc' nutzt den .ffpfsc-Entpacker, nicht den exFAT/ffpkg-Weg."""
        with mock.patch.object(self.app, "_mkdtemp", return_value=self._tmpdir()), \
             mock.patch.object(self.app, "_mode_unpack_to_game_folder",
                               return_value=True) as ug, \
             mock.patch.object(self.app, "_mode_exfat_to_folder",
                               return_value=True) as ex, \
             mock.patch.object(self.app, "_mode_ffpkg_to_folder",
                               return_value=True) as fp, \
             mock.patch.object(self.app, "_integration_anwenden",
                               return_value="") as _ia:
            # _integration_anwenden gibt "" zurueck -> Abbruch nach dem Entpacken,
            # das reicht, um den Entpackzweig zu pruefen ohne echtes Packen.
            self.app._mode_abbild_zu_ffpfs(
                os.path.join(self._tmpdir(), "Spiel.ffpfsc"),
                self._tmpdir(), quelle="ffpfsc", uncompressed=False)
        self.assertTrue(ug.called, "quelle='ffpfsc' muss _mode_unpack_to_game_folder rufen")
        self.assertFalse(ex.called)
        self.assertFalse(fp.called)

    def _tmpdir(self):
        if not hasattr(self, "_td"):
            self._td = tempfile.mkdtemp(prefix="ffpfsc_asset_test_")
            os.makedirs(os.path.join(self._td, "Spiel"), exist_ok=True)
        return self._td

    def test_wiring_refresh_haengt_an_asset_umschaltung(self):
        """Beim Umschalten von AMPR/Methode wird die Zielliste neu bewertet."""
        with open(HAUPTDATEI, encoding="utf-8") as f:
            quelle = f.read()
        # AMPR-Kaestchen: _on_integration_changed frischt die Liste auf.
        i = quelle.index("def _on_integration_changed(")
        block = quelle[i:i + 4000]
        self.assertIn("_refresh_target_format_options", block)
        # Methodenwahl: der Bind ruft nach dem Wechsel den Refresh.
        j = quelle.index('self.ampr_methode_combo.bind(')
        self.assertIn("_refresh_target_format_options",
                      quelle[j:j + 400])


if __name__ == "__main__":
    unittest.main(verbosity=2)
