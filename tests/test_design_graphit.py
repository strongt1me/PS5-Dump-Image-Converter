# -*- coding: utf-8 -*-
"""Das Design "Ruhig Graphit" (Entwurf A, v1.9.79) - und dass die vier aelteren Designs bleiben, wie sie waren.

Nutzerauftrag (15.10.2026): die Oberflaeche "einheitlich, harmonisch, ruhig, professionell und modern" gestalten, nach
dem Umbau muesse alles "noch so funktionieren wie jetzt". Gewaehlt wurde Entwurf A, umgesetzt als **zusaetzliches**
Design: Wer es nicht will, waehlt ein anderes; die alten Paletten sind hier mit Pruefsumme festgehalten.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: SHA-256 von ``json.dumps(palette, sort_keys=True)`` je altem Design, gemessen am 15.10.2026. Aendert jemand mit
#: Absicht eine dieser Paletten, wird die Summe hier nachgezogen - ohne Absicht faellt sie auf.
ALTE_PALETTEN = {
    "futuristisch": "6eaff161419b0ca245a6330e5f7fb467226d09ef546cfd1ee8b8b47e20a56cb2",
    "dunkel": "bb572fcce994c4ddd26f1f747c51d8b497afb424f1875fdd94aac222201d719e",
    "hell": "777eb08207512fc2517a93e88fadfc0d9ed07901abc3ded7f8cdc8f6ae7bca25",
    "metallisch": "288cb8e086b115f064ccb1001cd54a0e7de205c88621d93cf236cfc7605564ba",
}


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class PaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls.klasse = cls.haupt.PS5ConverterGUI

    def test_die_vier_alten_paletten_sind_unveraendert(self) -> None:
        for name, soll in ALTE_PALETTEN.items():
            with self.subTest(design=name):
                roh = json.dumps(self.klasse._THEMES[name], sort_keys=True).encode()
                self.assertEqual(soll, hashlib.sha256(roh).hexdigest(),
                                 "Die Palette von %s hat sich geaendert." % name)

    def test_graphit_hat_dieselben_schluessel_wie_die_anderen(self) -> None:
        soll = set(self.klasse._THEMES["metallisch"])
        self.assertEqual(soll, set(self.klasse._THEMES["graphit"]))

    def test_graphit_ist_ein_zusaetzliches_design(self) -> None:
        self.assertEqual({"futuristisch", "dunkel", "hell", "metallisch", "graphit"}, set(self.klasse._THEMES))

    def test_die_vorgabe_bleibt_dunkel(self) -> None:
        """Wer nichts waehlt, sieht wie bisher das dunkle Design - "Ruhig Graphit" ist eine Wahl, kein Zwang."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn('self._load_setting_static("theme", "dunkel")', quelle)
        self.assertIn('_THEMES["dunkel"])', quelle)

    def test_farbschwaeche_kennt_graphit(self) -> None:
        for satz in (self.klasse._FARBSCHWAECHE_ROTGRUEN, self.klasse._FARBSCHWAECHE_ACHROMAT):
            self.assertIn("graphit", satz)
            self.assertEqual(set(satz["dunkel"]), set(satz["graphit"]))

    def test_ein_akzent_und_ruhige_nebenknoepfe(self) -> None:
        """Der Kern von Entwurf A: Der Nebenknopf ist kein Tuerkis mehr, sondern ein Schiefergrau - Gruen ist es nicht."""
        pal = self.klasse._THEMES["graphit"]
        r, g, b = (int(pal["tuerkis_btn"][i:i + 2], 16) for i in (1, 3, 5))
        self.assertLess(abs(g - r), 40, "Der Nebenknopf soll grau-blau sein, nicht tuerkis: %s" % pal["tuerkis_btn"])
        self.assertGreater(b, r)


class RuhigeOberflaecheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls.klasse = cls.haupt.PS5ConverterGUI

    def test_nur_graphit_ist_ruhig(self) -> None:
        self.assertEqual(frozenset({"graphit"}), self.klasse._RUHIGE_DESIGNS)

    def _gui(self, design: str):
        g = self.klasse.__new__(self.klasse)
        g._current_theme = design
        g._COLORS = dict(self.klasse._THEMES[design])
        return g

    def test_die_menueleiste_hat_in_graphit_eine_farbe(self) -> None:
        g = self._gui("graphit")
        soll = g._COLORS["fg_secondary"]
        for rolle in ("fg_accent", "fg_warning", "fg_success", "fg_secondary"):
            with self.subTest(rolle=rolle):
                self.assertEqual(soll, g._titelleisten_schrift(rolle))

    def test_die_menueleiste_bleibt_in_den_alten_designs_bunt(self) -> None:
        for design in ("futuristisch", "dunkel", "hell", "metallisch"):
            g = self._gui(design)
            with self.subTest(design=design):
                for rolle in ("fg_accent", "fg_warning", "fg_success"):
                    self.assertEqual(g._COLORS[rolle], g._titelleisten_schrift(rolle),
                                     "%s/%s: die Leiste hat sich veraendert" % (design, rolle))

    def test_die_leiste_ist_in_graphit_lesbar(self) -> None:
        g = self._gui("graphit")
        k = self.haupt.kontrastverhaeltnis(g._titelleisten_schrift("fg_accent"), g._COLORS["header_bg"])
        self.assertGreaterEqual(k, 4.5)

    def test_die_ueberschrift_folgt_dem_design(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn('foreground=(c["fg_primary"] if getattr(self, "_current_theme", "") in self._RUHIGE_DESIGNS',
                      quelle)

    def test_credits_und_js_loader_nehmen_die_leistenfarbe(self) -> None:
        """Sonst bliebe beim Start CREDITS blau und JS LOADER orange, obwohl das Nachziehen sie vereinheitlicht."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        for name, rolle in (("_btn_credits_title", "fg_accent"), ("_btn_jsloader_title", "fg_warning")):
            with self.subTest(knopf=name):
                self.assertIn('fg=self._titelleisten_schrift("%s"),' % rolle, quelle)
                self.assertIn('%s.config(fg=self._titelleisten_schrift("%s")' % (name, rolle), quelle)

    def test_der_designdialog_listet_das_neue_design(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn('("graphit", self._t("theme_dialog.theme_graphit_label")', quelle)
        for schluessel in ("theme_dialog.theme_graphit_label", "theme_dialog.theme_graphit_desc"):
            for sprache in ("de", "en"):
                self.assertTrue(STRINGS[schluessel][sprache].strip(), "%s/%s fehlt" % (schluessel, sprache))
        self.assertEqual("Ruhig Graphit", STRINGS["theme_dialog.theme_graphit_label"]["de"])


if __name__ == "__main__":
    unittest.main()
