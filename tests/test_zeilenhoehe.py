# -*- coding: utf-8 -*-
"""Die Zeilen der Listen (``ttk.Treeview``) wachsen mit der Schrift mit.

Gemeldet von einem Anwender mit Windows-Skalierung 200 % (2880x1800): Im Fenster
ABBILD BEARBEITEN waren die Zeilen der Dateiliste oben und unten abgeschnitten.

Ursache (15.11.2026 gemessen): ``rowheight`` war eine feste Pixelzahl (24), die
Schrift der Liste ist in Punkt angegeben und waechst mit ``tk scaling`` - bei 200 %
ist eine Textzeile 37 px hoch, die Zeile blieb bei 24 px. Bei 125 % (dort geeicht)
passte es gerade noch, darum ist es nie aufgefallen.

Gesichert wird:

* die Rechenregel (``zeilenhoehe``) ohne Fenster;
* am echten ``ttk.Style`` des Programms bei 100 / 125 / 150 / 200 / 250 %, dass die
  Zeile nie niedriger ist als die Textzeile der Listenschrift - und dass sie bei
  100 % und am Eichpunkt (125 %) bei 24 px bleibt;
* im Quelltext, dass keine Listenstufe wieder mit einer festen Zahl eingetragen wird
  (die Klasse, nicht der Einzelfall: eine neue Liste mit ``rowheight=22`` faellt auf).
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJEKT)

from ps5_validator.ui import zeilenhoehe as zh  # noqa: E402

HAUPTDATEI = os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    import tkinter.font as tkfont
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


#: Windows-Skalierung in Prozent -> ``tk scaling`` (100 % = 96 dpi = 4/3).
PROZENTE = (100, 125, 150, 200, 250)


class RechenregelTests(unittest.TestCase):
    """``zeilenhoehe`` ohne Fenster."""

    def test_passt_die_schrift_bleibt_das_eingetragene_mass(self) -> None:
        self.assertEqual(24, zh.zeilenhoehe(24, 17))   # 100 %
        self.assertEqual(24, zh.zeilenhoehe(24, 23))   # 125 %, der Eichpunkt
        self.assertEqual(20, zh.zeilenhoehe(20, 15))

    def test_ist_die_schrift_hoeher_waechst_die_zeile_mit(self) -> None:
        self.assertEqual(29, zh.zeilenhoehe(24, 28))   # 150 %
        self.assertEqual(38, zh.zeilenhoehe(24, 37))   # 200 %
        self.assertEqual(46, zh.zeilenhoehe(24, 45))   # 250 %

    def test_nie_niedriger_als_die_textzeile(self) -> None:
        for basis in (20, 22, 24):
            for zeile in range(10, 80):
                with self.subTest(basis=basis, zeile=zeile):
                    soll = zh.zeilenhoehe(basis, zeile)
                    self.assertGreaterEqual(soll, zeile + zh.LUFT)
                    self.assertGreaterEqual(soll, basis)

    def test_nicht_gemessen_heisst_das_eingetragene_mass(self) -> None:
        for unbrauchbar in (None, 0, -5, "x", [], 0.0):
            with self.subTest(wert=unbrauchbar):
                self.assertEqual(24, zh.zeilenhoehe(24, unbrauchbar))

    def test_ungueltige_schrift_verhindert_nichts(self) -> None:
        """Eine ungueltige Schrift darf den Fensteraufbau nie verhindern."""
        if not TK_DA:
            self.skipTest("Keine Anzeige verfuegbar")
        self.assertIsNone(zh.schrift_linienhoehe(("Segoe UI", "kein-mass")))
        self.assertEqual(24, zh.treeview_zeilenhoehe(24, ("Segoe UI", "kein-mass")))


class _SkalierungMixin:
    """Stellt ``tk scaling`` der gemeinsamen Wurzel um und gibt sie danach zurueck."""

    def setUp(self) -> None:
        self._skalierung_vorher = float(_WURZEL.tk.call("tk", "scaling"))
        self.addCleanup(self._zurueck)

    def _zurueck(self) -> None:
        _WURZEL.tk.call("tk", "scaling", self._skalierung_vorher)

    @staticmethod
    def _skalierung(prozent: int) -> None:
        _WURZEL.tk.call("tk", "scaling", prozent / 75.0)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class MessungTests(_SkalierungMixin, unittest.TestCase):
    """``treeview_zeilenhoehe`` an der echten Schrift."""

    def test_die_zeile_ist_nie_niedriger_als_die_textzeile(self) -> None:
        from ps5_validator.utils.plattform import UI_SCHRIFT
        for prozent in PROZENTE:
            self._skalierung(prozent)
            for basis, punkt in ((24, 10), (24, 9), (22, 9), (20, 9)):
                schrift = (UI_SCHRIFT, punkt)
                textzeile = tkfont.Font(root=_WURZEL, font=schrift).metrics("linespace")
                with self.subTest(prozent=prozent, basis=basis, punkt=punkt):
                    self.assertGreaterEqual(
                        zh.treeview_zeilenhoehe(basis, schrift, _WURZEL), textzeile + zh.LUFT,
                        "Zeile niedriger als die Textzeile (%d px)" % textzeile)

    def test_bei_100_prozent_bleibt_es_beim_eingetragenen_mass(self) -> None:
        from ps5_validator.utils.plattform import UI_SCHRIFT
        self._skalierung(100)
        for basis, punkt in ((24, 10), (24, 9), (22, 9), (20, 9)):
            with self.subTest(basis=basis, punkt=punkt):
                self.assertEqual(basis, zh.treeview_zeilenhoehe(basis, (UI_SCHRIFT, punkt), _WURZEL))

    def test_bei_200_prozent_ist_die_zeile_deutlich_hoeher_als_24(self) -> None:
        """Genau der Fall des Anwenders: bei 200 % blieb sie vorher bei 24 px."""
        from ps5_validator.utils.plattform import UI_SCHRIFT
        self._skalierung(200)
        self.assertGreater(zh.treeview_zeilenhoehe(24, (UI_SCHRIFT, 10), _WURZEL), 30)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class StilTests(_SkalierungMixin, unittest.TestCase):
    """Der echte Stil ``Treeview`` des Programms (``_setup_styles``)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        klasse = cls.haupt.PS5ConverterGUI
        # Attrappe statt ganzem Programmfenster: _setup_styles braucht nur root und die Palette.
        cls.app = klasse.__new__(klasse)
        cls.app.root = _WURZEL
        cls.app._COLORS = dict(klasse._THEMES["dunkel"])

    @classmethod
    def tearDownClass(cls) -> None:
        # Den Stil so hinterlassen, wie das Programm ab Werk startet.
        cls.app._setup_styles()

    def _zeile(self) -> int:
        return int(ttk.Style().lookup("Treeview", "rowheight"))

    def test_die_zeile_des_standardstils_passt_zur_schrift(self) -> None:
        for prozent in PROZENTE:
            self._skalierung(prozent)
            self.app._setup_styles()
            schrift = ttk.Style().lookup("Treeview", "font")
            textzeile = tkfont.Font(root=_WURZEL, font=schrift).metrics("linespace")
            with self.subTest(prozent=prozent):
                self.assertGreaterEqual(self._zeile(), textzeile + zh.LUFT,
                                        "Zeile %d px, Textzeile %d px" % (self._zeile(), textzeile))

    def test_bis_125_prozent_bleibt_die_zeile_bei_24(self) -> None:
        """Wer bei 100/125 % nichts bemerkt hat, soll auch nichts anderes sehen."""
        for prozent in (100, 125):
            self._skalierung(prozent)
            self.app._setup_styles()
            with self.subTest(prozent=prozent):
                self.assertEqual(24, self._zeile())

    def test_bei_200_prozent_wird_die_zeile_hoeher(self) -> None:
        self._skalierung(200)
        self.app._setup_styles()
        self.assertGreater(self._zeile(), 30)


class QuelltextTests(unittest.TestCase):
    """Keine Liste darf wieder mit einer festen Pixelzahl eingetragen werden."""

    DATEIEN = (
        HAUPTDATEI,
        os.path.join(PROJEKT, "ps5_validator", "ui", "pkg_datei_browser.py"),
        os.path.join(PROJEKT, "ps5_validator", "ui", "spiel_detail_fenster.py"),
        os.path.join(PROJEKT, "ps5_validator", "ui", "abbild_bearbeiten_fenster.py"),
    )

    @staticmethod
    def _lesen(pfad: str) -> str:
        with open(pfad, encoding="utf-8") as datei:
            return datei.read()

    def test_keine_feste_zeilenhoehe_im_quelltext(self) -> None:
        for pfad in self.DATEIEN:
            treffer = re.findall(r"rowheight\s*=\s*\d+", self._lesen(pfad))
            with self.subTest(datei=os.path.basename(pfad)):
                self.assertEqual([], treffer, "feste Zeilenhoehe: %s" % treffer)

    def test_die_vier_stellen_rechnen_ueber_die_hilfe(self) -> None:
        haupt = self._lesen(HAUPTDATEI)
        self.assertEqual(2, haupt.count("rowheight=treeview_zeilenhoehe("))
        self.assertEqual(1, self._lesen(self.DATEIEN[1]).count("rowheight=treeview_zeilenhoehe("))
        self.assertEqual(3, self._lesen(self.DATEIEN[2]).count("rowheight=treeview_zeilenhoehe("))

    def test_ankerstellen_existieren(self) -> None:
        """Findet die Suche nichts, waere der Test klaglos gruen."""
        for pfad in self.DATEIEN:
            self.assertTrue(os.path.isfile(pfad), pfad)
        self.assertIn("ttk.Treeview", self._lesen(self.DATEIEN[1]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
