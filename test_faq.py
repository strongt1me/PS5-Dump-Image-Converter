"""Tests fuer den Knopf FAQ (seit 04.10.2026).

Wunsch des Nutzers: "Die FAQ Bitte im Programm links neben den Knopf
Benutzerhandbuch. Die FAQ soll auch in der Englischen Version anklickbar sein
(auf englisch uebersetzt natuerlich)". Der Knopf oeffnet je nach Sprache
``FAQ.html`` oder ``FAQ_EN.html``; beide muessen in allen drei .spec
eingebettet sein, sonst waere der Knopf in der fertigen Datei wirkungslos,
und als PDF gehen sie ins Auslieferungsbuendel. Dass Inhalt und PDF aktuell
sind, haelt ``test_dokumente_aktuell.py`` fest.
"""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils.i18n import STRINGS, translate

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
SPECS = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
         "PS5ImageConverter_Pro_macos.spec")
FAQ_HTML = ("FAQ.html", "FAQ_EN.html")
FAQ_PDF = ("FAQ.pdf", "FAQ_EN.pdf")

#: Die eine Tk-Wurzel dieser Datei. Wird angelegt und behalten.
_WURZEL = None


def _tk_verfuegbar() -> bool:
    """Ob eine Anzeige da ist - legt dabei die Wurzel an (wie test_handbuch_knopf)."""
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
        self.assertIn("titlebar.faq", STRINGS)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertEqual(translate(sprache, "titlebar.faq"), "FAQ")

    def test_fehlermeldung_nennt_die_datei(self):
        self.assertIn("dialog.msg.faq_missing", STRINGS)
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                text = translate(sprache, "dialog.msg.faq_missing", datei="FAQ_EN.html")
                self.assertIn("FAQ_EN.html", text)


class AuslieferungTests(unittest.TestCase):
    """Ohne Einbettung und Buendel waere die FAQ nur im Quelltextbetrieb da."""

    def test_dateien_liegen_im_projekt(self):
        for name in FAQ_HTML + FAQ_PDF:
            with self.subTest(datei=name):
                self.assertTrue((PROJEKT / name).is_file())

    def test_alle_drei_specs_betten_beide_sprachen_ein(self):
        for spec in SPECS:
            text = (PROJEKT / spec).read_text(encoding="utf-8")
            for name in FAQ_HTML:
                with self.subTest(spec=spec, datei=name):
                    self.assertIn("'%s'" % name, text)

    def test_buendel_nimmt_beide_pdf_mit(self):
        text = (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")
        for name in FAQ_PDF:
            with self.subTest(datei=name):
                self.assertIn('"%s"' % name, text)

    def test_mac_bau_laeuft_bei_aenderungen_an(self):
        text = (PROJEKT / ".github" / "workflows" / "macos-buendel.yml").read_text(encoding="utf-8")
        for name in FAQ_HTML:
            with self.subTest(datei=name):
                self.assertIn("- '%s'" % name, text)

    def test_bundled_resource_findet_beide(self):
        for name in FAQ_HTML:
            with self.subTest(datei=name):
                pfad = APP._bundled_resource(name)
                self.assertTrue(pfad and Path(pfad).is_file())

    def test_englische_fassung_ist_englisch(self):
        """Gegenprobe gegen eine versehentlich kopierte deutsche Datei."""
        de = (PROJEKT / "FAQ.html").read_text(encoding="utf-8")
        en = (PROJEKT / "FAQ_EN.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="de">', de)
        self.assertIn('<html lang="en">', en)
        self.assertIn("Frequently Asked Questions", en)
        self.assertNotIn("Häufige Fragen", en)
        self.assertEqual(de.count('class="frage"'), en.count('class="frage"'),
                         "Beide Sprachen sollen dieselben Fragen haben")


class OeffnenTests(unittest.TestCase):
    """Der Knopf waehlt die Datei nach der Sprache der Oberflaeche."""

    def _app(self, sprache):
        app = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        app.root = None
        app._current_language = sprache
        return app

    def _geoeffnet(self, sprache):
        with mock.patch.object(APP, "_system_oeffnen_versuchen",
                               return_value=(True, "")) as oeffnen:
            APP.PS5ConverterGUI._open_faq(self._app(sprache))
        oeffnen.assert_called_once()
        return Path(str(oeffnen.call_args[0][0])).name

    def test_deutsch_oeffnet_faq_html(self):
        self.assertEqual("FAQ.html", self._geoeffnet("de"))

    def test_englisch_oeffnet_faq_en_html(self):
        self.assertEqual("FAQ_EN.html", self._geoeffnet("en"))

    def test_unbekannte_sprache_nimmt_deutsch(self):
        self.assertEqual("FAQ.html", self._geoeffnet("fr"))

    def test_fehlende_datei_meldet_statt_zu_schweigen(self):
        app = self._app("en")
        with mock.patch.object(APP, "_bundled_resource", return_value=""), \
             mock.patch.object(APP.messagebox, "showwarning") as box, \
             mock.patch.object(APP, "_system_oeffnen_versuchen") as oeffnen:
            APP.PS5ConverterGUI._open_faq(app)
        box.assert_called_once()
        self.assertIn("FAQ_EN.html", box.call_args[0][1])
        oeffnen.assert_not_called()


class QuelltextTests(unittest.TestCase):
    """Was sich am Aufbau zeigt - ohne Fenster geprueft."""

    @classmethod
    def setUpClass(cls):
        cls.text = QUELLDATEI.read_text(encoding="utf-8")

    def test_zwischen_handbuch_und_anleitung_gepackt(self):
        """Bei side='right' sitzt das zuletzt gepackte Widget am weitesten links."""
        handbuch = self.text.index('self._btn_manual_title.pack(side="right"')
        faq = self.text.index('self._btn_faq_title.pack(side="right"')
        anleitung = self.text.index('self._btn_assetpack_anleitung_title.pack(side="right"')
        self.assertLess(handbuch, faq)
        self.assertLess(faq, anleitung)

    def test_steht_in_klappliste_sprachwechsel_und_farbliste(self):
        self.assertIn('("_btn_faq_title", "titlebar.faq", "_open_faq")', self.text)
        self.assertIn('("_btn_faq_title", "titlebar.faq")', self.text)
        block = self.text[self.text.index("_TITELLEISTE_SCHRIFTFARBEN: dict"):]
        self.assertIn('"_btn_faq_title"', block[:block.index("}")])

    def test_oeffnet_kein_eigenes_fenster(self):
        self.assertIn("command=self._open_faq,", self.text)
        self.assertNotIn('self._werkzeugknopf("_open_faq")', self.text)


@unittest.skipUnless(_tk_verfuegbar(), "keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        _WURZEL.update_idletasks()

    def test_knopf_traegt_faq(self):
        self.assertEqual("FAQ", self.app._btn_faq_title.cget("text"))

    def test_direkt_links_neben_dem_handbuch(self):
        """In der gemerkten Reihenfolge der Leiste: Handbuch, dann FAQ, dann Anleitung.

        ``_titelleiste_ordnung`` haelt alle Knoepfe fest, auch eingefaltete -
        anders als ``pack_slaves`` bei einem schmalen Fenster.
        """
        ordnung = [knopf for knopf, _polster in self.app._titelleiste_ordnung]
        handbuch = ordnung.index(self.app._btn_manual_title)
        self.assertIs(ordnung[handbuch + 1], self.app._btn_faq_title)
        self.assertIs(ordnung[handbuch + 2], self.app._btn_assetpack_anleitung_title)

    def test_beschriftung_folgt_der_sprache(self):
        alt = self.app._current_language
        try:
            for sprache in ("en", "de"):
                self.app._current_language = sprache
                self.app._apply_language()
                self.assertEqual("FAQ", self.app._btn_faq_title.cget("text"))
        finally:
            self.app._current_language = alt
            self.app._apply_language()


if __name__ == "__main__":
    unittest.main()
