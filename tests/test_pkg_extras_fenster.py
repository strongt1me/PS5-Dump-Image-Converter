# -*- coding: utf-8 -*-
"""Das Fenster "PKG-Extras" unter WEITERE TOOLS (Nutzerwunsch 30.10.2026).

Die vier Werkzeuge der frueheren FPKG-Seite "Extras" (DDS zu PNG, exFAT-Boot-Sektor reparieren, exFAT-Inhalt
entpacken/aufbauen, FFPKG-Metadaten reparieren) haben dort keinen Reiter mehr. Geprueft wird: der Menueeintrag, das
Fenster ohne geoeffneten PKG-Bereich, die vier Karten samt Knoepfen, das Oeffnen/Schliessen ueber den Umschalter und
ein Handler am wirklichen Fenster (Fehlerweg, ohne Werkzeug und ohne Dateidialog).
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("pkgextras")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import pkg_extras_fenster as pef      # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster as fz          # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

BEFEHL = "_show_pkg_extras"
SPRACHEN = ("de", "en", "es", "it", "fr")
#: i18n-Schluessel der vier Kartentitel und ihrer Knoepfe, wie sie die Seite "Extras" immer hatte.
KARTEN = ("ps5pkg.dds_title", "ps5pkg.exfat_repair_title", "ps5pkg.exfat_edit_title", "ps5pkg.ffpkg_repair_title")
KNOEPFE = ("ps5pkg.dds_btn_run", "ps5pkg.exfat_repair_btn_run", "ps5pkg.exfat_edit_btn_unpack",
           "ps5pkg.exfat_edit_btn_pack", "ps5pkg.ffpkg_repair_btn_copy")


def _pumpen(sekunden: float) -> None:
    ende = time.time() + sekunden
    while time.time() < ende:
        _WURZEL.update()
        time.sleep(0.02)


def _alle(widget):
    yield widget
    for kind in widget.winfo_children():
        yield from _alle(kind)


def _texte(fenster) -> list[str]:
    texte = []
    for w in _alle(fenster):
        try:
            text = w.cget("text")
        except (tk.TclError, AttributeError):
            continue
        if isinstance(text, str) and text:
            texte.append(text)
    return texte


class MenueTests(unittest.TestCase):
    def test_der_eintrag_steht_unter_weitere_tools_vor_den_wee_tools(self) -> None:
        eintraege = list(APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES)
        self.assertIn(("titlebar.pkg_extras", BEFEHL), eintraege)
        self.assertLess(eintraege.index(("titlebar.pkg_extras", BEFEHL)),
                        eintraege.index(("titlebar.wee_tools", "_show_wee_tools")))
        self.assertTrue(callable(getattr(APP.PS5ConverterGUI, BEFEHL)))

    def test_die_texte_liegen_in_allen_fuenf_sprachen_vor(self) -> None:
        for schluessel in ("titlebar.pkg_extras", "pkgextras.subtitle"):
            for sprache in SPRACHEN:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())
            self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])

    def test_die_vier_karten_hatten_ihre_texte_schon_vorher(self) -> None:
        for schluessel in (*KARTEN, *KNOEPFE):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def tearDown(self) -> None:
        self.app._werkzeugfenster_schliessen(BEFEHL)
        _pumpen(0.05)

    def _oeffnen(self) -> "tk.Toplevel":
        self.app._werkzeugfenster_umschalten(BEFEHL)
        _pumpen(0.3)
        win = self.app._werkzeugfenster.get(BEFEHL)
        self.assertIsNotNone(win, "Das Fenster ist nicht entstanden.")
        return win

    def test_das_fenster_baut_ohne_geoeffneten_pkg_bereich(self) -> None:
        self.assertIsNone(getattr(self.app, fz.FENSTER_ATTRIBUT, None), "Anker: kein PKG-Fenster offen")
        win = self._oeffnen()
        self.assertTrue(win.winfo_exists())
        self.assertEqual(self.app._t("titlebar.pkg_extras"), win.title())
        self.assertIsNone(getattr(self.app, fz.FENSTER_ATTRIBUT, None),
                          "Das Extras-Fenster darf kein PKG-Fenster erzeugen.")

    def test_alle_vier_karten_und_ihre_knoepfe_sind_da(self) -> None:
        win = self._oeffnen()
        texte = _texte(win)
        for schluessel in KARTEN:
            with self.subTest(karte=schluessel):
                self.assertIn(self.app._t(schluessel).upper(), texte)
        for schluessel in KNOEPFE:
            with self.subTest(knopf=schluessel):
                self.assertIn(self.app._t(schluessel), texte)

    def test_die_ueberschrift_steht_nur_einmal(self) -> None:
        """Die Seite brachte ihre eigene Ueberschrift "Extras" mit - im Fenster hat es schon eine."""
        win = self._oeffnen()
        self.assertNotIn(self.app._t("ps5pkg.nav_extras"), _texte(win))
        self.assertIn(self.app._t("pkgextras.subtitle"), _texte(win))

    def test_der_zweite_druck_schliesst_das_fenster(self) -> None:
        win = self._oeffnen()
        self.app._werkzeugfenster_umschalten(BEFEHL)
        _pumpen(0.1)
        self.assertFalse(win.winfo_exists())
        self.assertNotIn(BEFEHL, self.app._werkzeugfenster)

    def test_der_ffpkg_knopf_ohne_datei_meldet_den_fehler(self) -> None:
        """Ein Handler am wirklichen Fenster: ohne Datei kommt der alte Hinweis, es wird nichts gesucht oder kopiert."""
        win = self._oeffnen()
        knoepfe = [w for w in _alle(win) if hasattr(w, "invoke") and w.cget("text") == self.app._t("ps5pkg.ffpkg_repair_btn_copy")]
        self.assertEqual(1, len(knoepfe))
        knoepfe[0].invoke()
        self.assertIn(self.app._t("ps5pkg.ffpkg_repair_err_no_file"), _texte(win))

    def test_der_dds_knopf_ohne_werkzeug_oder_quelle_meldet_etwas(self) -> None:
        win = self._oeffnen()
        knoepfe = [w for w in _alle(win) if hasattr(w, "invoke") and w.cget("text") == self.app._t("ps5pkg.dds_btn_run")]
        self.assertEqual(1, len(knoepfe))
        knoepfe[0].invoke()
        gemeldet = {self.app._t("ps5pkg.dds_err_no_tool"), self.app._t("ps5pkg.dds_err_no_source")}
        self.assertTrue(gemeldet & set(_texte(win)), "Der Knopf blieb stumm.")

    def test_die_klasse_baut_nicht_die_ganze_fpkg_seite(self) -> None:
        win = self._oeffnen()
        self.assertTrue(issubclass(pef.PkgExtras, fz.Ps5PkgFenster))
        self.assertFalse(any(w.winfo_class() == "Treeview" for w in _alle(win)), "Keine Paketliste im Extras-Fenster.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
