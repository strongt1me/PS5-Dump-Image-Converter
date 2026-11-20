"""Waechter: die Einstellung ``backport_firmware_referenz`` hat ein Feld im BACKPORT-Fenster.

Bis 20.11.2026 las ``_backport_ziel_deckung_melden`` diese Einstellung, aber keine Stelle der Oberflaeche setzte sie
(nur von Hand in der Einstellungsdatei). Das Feld steht im erweiterten Bereich neben dem Firmware-Analyse-Ordner,
meldet aber nur Luecken und kopiert nichts - die beiden Einstellungen bleiben getrennt.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.i18n import STRINGS  # noqa: E402

QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

SPRACHEN = ("de", "en", "es", "it", "fr")
SCHLUESSEL = ("backport.fw_referenz_label", "backport.fw_referenz_hint")


def _rumpf(name: str) -> str:
    anfang = QUELLE.index("    def %s(" % name)
    ende = QUELLE.find("\n    def ", anfang + 10)
    return QUELLE[anfang:ende]


class FeldTexteTests(unittest.TestCase):
    def test_texte_in_allen_fuenf_sprachen(self) -> None:
        for schluessel in SCHLUESSEL:
            eintrag = STRINGS[schluessel]
            for sprache in SPRACHEN:
                self.assertTrue(str(eintrag.get(sprache, "")).strip(), "%s fehlt in %s" % (schluessel, sprache))

    def test_hinweis_nennt_das_nichtkopieren(self) -> None:
        # Der Unterschied zum Analyse-Ordner (kopiert wirklich) muss im Hinweis stehen.
        self.assertIn("kopiert nichts", STRINGS["backport.fw_referenz_hint"]["de"])


class FeldVerdrahtungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fenster = _rumpf("_render_backport_window")

    def test_feld_speichert_dieselbe_einstellung_wie_die_pruefung_liest(self) -> None:
        self.assertIn('self._save_setting("backport_firmware_referenz", wert)', self.fenster)
        self.assertIn('self._load_setting("backport_firmware_referenz", "")',
                      _rumpf("_backport_ziel_deckung_melden"))

    def test_gesetzter_wert_klappt_den_erweiterten_bereich_auf(self) -> None:
        self.assertRegex(self.fenster, r"erweitert_offen = tk\.BooleanVar\(value=bool\([^)]*_fw_referenz_wert_vorab")

    def test_feld_nutzt_die_gleiche_spur_wie_die_anderen_ordnerfelder(self) -> None:
        self.assertIn("bibliothek_raster.spur_bis_zerstoert(win, fw_referenz_var, _fw_referenz_speichern)", self.fenster)

    def test_referenz_kopiert_nichts(self) -> None:
        # Die Pruefung darf nie in den Dump schreiben: kein Kopieraufruf in ihrem Rumpf.
        rumpf = _rumpf("_backport_ziel_deckung_melden")
        self.assertIsNone(re.search(r"fakelibs_aus_firmware_kopieren|shutil\.copy", rumpf))

    def test_beide_ordner_einstellungen_bleiben_getrennt(self) -> None:
        self.assertIn('"backport_fw_analyse_ordner"', _rumpf("_backport_fw_analyse_basis"))
        self.assertNotIn("backport_firmware_referenz", _rumpf("_backport_fw_analyse_basis"))


class LandeplatzHakenTests(unittest.TestCase):
    """Haken ``backport_stubs_landeplatz`` (Versuch, Vorgabe Nein) unter "Erweiterte Einstellungen"."""

    def test_texte_in_allen_fuenf_sprachen(self) -> None:
        for schluessel in ("backport.option_landeplatz", "backport.option_landeplatz_kurz",
                           "backport.option_landeplatz_hint", "backport.korr_landeplatz"):
            for sprache in SPRACHEN:
                self.assertTrue(str(STRINGS[schluessel].get(sprache, "")).strip(), "%s fehlt in %s" % (schluessel, sprache))

    def test_vorgabe_ist_nein_und_die_einstellung_wird_gespeichert(self) -> None:
        self.assertIn('self._load_setting("backport_stubs_landeplatz", False)', _rumpf("_backport_landeplatz_an"))
        fenster = _rumpf("_render_backport_window")
        self.assertIn('self._save_setting("backport_stubs_landeplatz", landeplatz_var.get())', fenster)

    def test_gesetzter_haken_klappt_den_erweiterten_bereich_auf(self) -> None:
        self.assertRegex(_rumpf("_render_backport_window"),
                         r"(?s)erweitert_offen = tk\.BooleanVar\(value=bool\(.{0,300}?self\._backport_landeplatz_an\(\)")

    def test_modus_erreicht_die_stub_funktion(self) -> None:
        rumpf = _rumpf("_backport_korrekturen_anwenden")
        self.assertIn("landeplatz = self._backport_landeplatz_an()", rumpf)
        self.assertIn("landeplatz=landeplatz", rumpf)


if __name__ == "__main__":
    unittest.main()
