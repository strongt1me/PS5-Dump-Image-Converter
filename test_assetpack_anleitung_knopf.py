# -*- coding: utf-8 -*-
"""Tests fuer den Knopf ASSET-PACK-ANLEITUNG in der Titelleiste (30.09.2026).

Nutzerwunsch: "die neue HTML links neben den Benutzerhandbuch Knopf
platzieren [...] es soll auch so geoeffnet werden wie das Benutzerhandbuch".
Baugleich zu ``_btn_manual_title``/``_open_benutzerhandbuch``
(test_handbuch_knopf.py) - hier nur das Notwendige, keine Wiederholung der
dortigen, dort schon bewachten historischen Fallen (Fusszeile, wraplength).
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
import webbrowser
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import plattform
from ps5_validator.utils.i18n import STRINGS, translate

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
ANLEITUNG = PROJEKT / "Anleitungen" / "AMPR_Asset_Packs_Mitschnitt_Assistent.html"

_WURZEL = None


def _tk_verfuegbar() -> bool:
    """Wie in test_handbuch_knopf.py: eine Wurzel anlegen und behalten."""
    global _WURZEL
    if _WURZEL is not None:
        return True
    try:
        _WURZEL = tk._default_root or tk.Tk()
        _WURZEL.withdraw()
    except Exception:
        _WURZEL = None
        return False
    return True


class UebersetzungTests(unittest.TestCase):
    def test_knopfbeschriftung_in_beiden_sprachen(self):
        self.assertIn("titlebar.assetpack_anleitung", STRINGS)
        self.assertEqual(translate("de", "titlebar.assetpack_anleitung"), "Asset Packs Anleitung")
        self.assertEqual(translate("en", "titlebar.assetpack_anleitung"), "Asset Packs Guide")

    def test_fehlermeldung_in_beiden_sprachen(self):
        self.assertIn("dialog.msg.assetpack_guide_missing", STRINGS)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = translate(sprache, "dialog.msg.assetpack_guide_missing")
                self.assertIn("AMPR_Asset_Packs_Mitschnitt_Assistent.html", text)
                self.assertNotEqual(text, "dialog.msg.assetpack_guide_missing")


class AuslieferungTests(unittest.TestCase):
    """Ohne Einbettung waere der Knopf in der EXE wirkungslos."""

    def test_anleitung_liegt_im_projekt(self):
        self.assertTrue(ANLEITUNG.is_file())

    def test_alle_drei_spec_betten_den_ordner_ein(self):
        """Bettet den ganzen Ordner ein - kein Einzeleintrag noetig (anders als beim Handbuch)."""
        for spec in ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
                    "PS5ImageConverter_Pro_macos.spec"):
            with self.subTest(spec=spec):
                text = (PROJEKT / spec).read_text(encoding="utf-8")
                self.assertIn("'Anleitungen'", text)

    def test_bundled_resource_findet_die_anleitung(self):
        pfad = APP._bundled_resource("Anleitungen", "AMPR_Asset_Packs_Mitschnitt_Assistent.html")
        self.assertTrue(pfad)
        self.assertTrue(Path(pfad).is_file())


class OeffnenTests(unittest.TestCase):
    """Derselbe Weg wie beim Handbuch-Knopf: _bundled_resource -> _oeffnen_oder_melden."""

    def _app_ohne_fenster(self):
        return APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def test_oeffnet_die_gefundene_datei(self):
        app = self._app_ohne_fenster()
        with mock.patch.object(APP, "_system_oeffnen_versuchen",
                               return_value=(True, "")) as oeffnen:
            APP.PS5ConverterGUI._open_assetpack_anleitung(app)
        oeffnen.assert_called_once()
        self.assertTrue(str(oeffnen.call_args[0][0]).endswith(
            "AMPR_Asset_Packs_Mitschnitt_Assistent.html"))

    def test_faellt_auf_den_browser_zurueck(self):
        ziel = str(ANLEITUNG)
        with mock.patch.object(webbrowser, "open", return_value=True) as browser:
            if plattform.IST_WINDOWS:
                with mock.patch.object(APP.os, "startfile", create=True,
                                       side_effect=OSError("nein")):
                    self.assertTrue(plattform.datei_oeffnen(ziel))
            else:
                with mock.patch.object(plattform.shutil, "which", return_value=None):
                    self.assertTrue(plattform.datei_oeffnen(ziel))
        browser.assert_called_once()

    def test_fehlende_datei_meldet_statt_zu_schweigen(self):
        app = self._app_ohne_fenster()
        app.root = None
        app._current_language = "de"
        with mock.patch.object(APP, "_bundled_resource", return_value=""), \
             mock.patch.object(APP.messagebox, "showwarning") as box, \
             mock.patch.object(APP.os, "startfile", create=True) as startfile:
            APP.PS5ConverterGUI._open_assetpack_anleitung(app)
        box.assert_called_once()
        startfile.assert_not_called()


class QuelltextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = QUELLDATEI.read_text(encoding="utf-8")

    def test_knopf_wird_nach_dem_handbuch_knopf_gepackt(self):
        """Bei side='right' sitzt das zuletzt gepackte Widget am weitesten links."""
        handbuch = self.text.index('self._btn_manual_title.pack(side="right"')
        anleitung = self.text.index('self._btn_assetpack_anleitung_title.pack(side="right"')
        self.assertLess(handbuch, anleitung,
                        "Der Anleitung-Knopf muss nach dem Handbuch-Knopf gepackt werden")

    def test_knopf_wird_beim_sprachwechsel_neu_beschriftet(self):
        self.assertIn(
            '("_btn_assetpack_anleitung_title", "titlebar.assetpack_anleitung")',
            self.text)

    def test_knopf_steht_in_der_klappliste(self):
        self.assertIn(
            '("_btn_assetpack_anleitung_title", "titlebar.assetpack_anleitung", '
            '"_open_assetpack_anleitung")',
            self.text)

    def test_knopf_hat_eine_schriftfarbe_im_designwechsel(self):
        """Sonst bleibt die Schrift beim Designwechsel auf der alten Farbe stehen."""
        block = self.text[self.text.index("_TITELLEISTE_SCHRIFTFARBEN: dict"):]
        block = block[:block.index("}")]
        self.assertIn('"_btn_assetpack_anleitung_title"', block)

    def test_knopf_geht_nicht_ueber_den_werkzeugknopf(self):
        """Fremdprogramm wie FileZilla/Handbuch - kein eigenes Tk-Fenster."""
        self.assertIn("command=self._open_assetpack_anleitung,", self.text)
        self.assertNotIn('self._werkzeugknopf("_open_assetpack_anleitung")', self.text)


@unittest.skipUnless(_tk_verfuegbar(), "keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wurzel = _WURZEL
        cls.app = APP.PS5ConverterGUI(cls.wurzel)
        cls.wurzel.update_idletasks()

    def test_knopf_existiert_mit_richtiger_beschriftung(self):
        self.assertTrue(hasattr(self.app, "_btn_assetpack_anleitung_title"))
        erwartet = translate(self.app._current_language, "titlebar.assetpack_anleitung")
        self.assertEqual(self.app._btn_assetpack_anleitung_title.cget("text"), erwartet)
        self.assertIn(erwartet, ("Asset Packs Anleitung", "Asset Packs Guide"),
                      "Unerwartete Beschriftung fuer Sprache %r"
                      % self.app._current_language)

    def test_knopf_steht_links_vom_handbuch_knopf(self):
        """Wie in test_handbuch_knopf.py: Fenster-Koordinaten, ersatzweise Packreihenfolge."""
        self.wurzel.deiconify()
        self.wurzel.update()
        handbuch = self.app._btn_manual_title.winfo_x()
        anleitung = self.app._btn_assetpack_anleitung_title.winfo_x()
        self.wurzel.withdraw()

        if handbuch or anleitung:
            self.assertLess(anleitung, handbuch)
            return

        geschwister = self.app._btn_manual_title.master.pack_slaves()
        self.assertIn(self.app._btn_manual_title, geschwister)
        self.assertIn(self.app._btn_assetpack_anleitung_title, geschwister)
        for knopf in (self.app._btn_manual_title, self.app._btn_assetpack_anleitung_title):
            self.assertEqual(knopf.pack_info()["side"], "right",
                             "Die Ersatzpruefung gilt nur fuer rechts gepackte Knoepfe")
        self.assertGreater(geschwister.index(self.app._btn_assetpack_anleitung_title),
                           geschwister.index(self.app._btn_manual_title),
                           "Die Anleitung muss nach dem Handbuch gepackt werden, "
                           "um links davon zu landen")

    def test_beschriftung_folgt_der_sprache(self):
        self.app._current_language = "en"
        self.app._apply_language()
        self.assertEqual(self.app._btn_assetpack_anleitung_title.cget("text"), "Asset Packs Guide")
        self.app._current_language = "de"
        self.app._apply_language()
        self.assertEqual(self.app._btn_assetpack_anleitung_title.cget("text"), "Asset Packs Anleitung")

    def test_designwechsel_faerbt_den_knopf_um(self):
        """Gegenprobe zur Farbtabelle oben - am echten Knopf gemessen."""
        self.app._theme_titelleiste_nachziehen()
        farbe = self.app._titelleisten_schrift("fg_secondary")
        self.assertEqual(self.app._btn_assetpack_anleitung_title.cget("fg"), farbe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
