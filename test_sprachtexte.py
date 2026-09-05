# -*- coding: utf-8 -*-
"""Texte, die an ``self._t()`` vorbeiliefen.

Die Werkzeugpruefung vom 04.09.2026 fand fuenf Stellen derselben Art: fertige
Saetze aus den Helfermodulen oder fest im Quelltext, die ungefiltert in der
Oberflaeche landeten. Wer das Programm auf Englisch stellte, bekam dort
trotzdem Deutsch - oder umgekehrt, denn ``dump_rename`` traegt seine
Konstanten fest auf Englisch.

**Die Trennung, die dabei gilt:** Keines der 33 Module unter
``ps5_validator/utils`` bindet ``i18n`` ein, und das soll so bleiben - sie
sind sprachfrei und auch ohne Oberflaeche benutzbar. Uebersetzt wird deshalb
erst beim Anzeigen. Wo ein Helfer Text liefern muss (``pkg_merger``), nimmt er
Vorlagen entgegen und traegt die eigenen nur als Vorgabe.

Geprueft wird beides: dass die Trennung haelt, und dass die Uebersetzung
wirklich ankommt.
"""
from __future__ import annotations

import os
import sys
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung

pruefumgebung.umlenken("sprachtexte")

from ps5_validator.utils import pkg_merger
from ps5_validator.utils.i18n import STRINGS, translate

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm

G = hauptprogramm.PS5ConverterGUI


def _gui(sprache: str):
    """Eine Oberflaeche ohne Fenster - nur zum Uebersetzen."""
    gui = G.__new__(G)
    gui._t = lambda schluessel, **werte: translate(sprache, schluessel, **werte)
    return gui


class HelferBleibenSprachfreiTests(unittest.TestCase):
    """Kein Helfermodul darf i18n einbinden."""

    def test_kein_helfer_bindet_i18n_ein(self) -> None:
        ordner = os.path.join(PROJEKT, "ps5_validator", "utils")
        schuldige = []
        for name in sorted(os.listdir(ordner)):
            if not name.endswith(".py") or name == "i18n.py":
                continue
            with open(os.path.join(ordner, name), encoding="utf-8",
                      errors="replace") as datei:
                text = datei.read()
            if "import i18n" in text or "from .i18n" in text \
                    or "utils.i18n import" in text:
                schuldige.append(name)
        self.assertEqual(
            [], schuldige,
            "Diese Helfer binden i18n ein: %s. Sie sollen sprachfrei bleiben "
            "und auch ohne Oberflaeche benutzbar sein - uebersetzt wird beim "
            "Anzeigen." % schuldige)


class DumpRenameTests(unittest.TestCase):
    """Einschaetzung und Vorlagen kamen fest auf Englisch durch."""

    def test_die_einschaetzung_wird_uebersetzt(self) -> None:
        for sprache, erwartet in (("de", "Bereit"), ("en", "Ready")):
            with self.subTest(sprache=sprache):
                text = _gui(sprache)._dump_rename_uebersetzen(
                    hauptprogramm.dump_rename_bereit)
                self.assertIn(erwartet, text)

    def test_die_vorlagen_werden_uebersetzt(self) -> None:
        for sprache, erwartet in (("de", "PPSA + Titel"), ("en", "PPSA + Title")):
            with self.subTest(sprache=sprache):
                self.assertEqual(
                    erwartet,
                    _gui(sprache)._dump_rename_uebersetzen(
                        hauptprogramm.dump_rename_ppsa_titel))

    def test_unbekanntes_bleibt_unveraendert(self) -> None:
        """Der Helfer darf neue Werte liefern, ohne dass hier etwas bricht."""
        self.assertEqual("etwas Neues",
                         _gui("de")._dump_rename_uebersetzen("etwas Neues"))

    def test_die_konstanten_selbst_bleiben_unangetastet(self) -> None:
        """Sie dienen als Schluessel und Vergleichswert - auch in Pruefungen."""
        from ps5_validator.utils import dump_rename

        self.assertEqual("🟢 Ready", dump_rename.CONFIDENCE_READY)
        self.assertEqual("PPSA + Title", dump_rename.PRESET_PPSA_TITLE)


class UebersetzerWerdenAuchBenutztTests(unittest.TestCase):
    """Ein Uebersetzer, den niemand ruft, aendert nichts.

    Beim Schreiben dieser Datei gemessen: Nimmt man den Aufruf von
    ``_dump_rename_uebersetzen`` aus dem Fenster heraus, bleiben alle
    Pruefungen oben gruen - sie fassen nur den Uebersetzer selbst an. Geprueft
    wird deshalb am Syntaxbaum, dass die Fenster ihn wirklich benutzen.
    """

    @classmethod
    def setUpClass(cls) -> None:
        import ast

        cls.ast = ast
        with open(os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py"),
                  encoding="utf-8", errors="replace") as datei:
            cls.baum = ast.parse(datei.read())

    def _methode(self, name: str):
        ast = self.ast
        klasse = next(k for k in self.baum.body
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        for k in klasse.body:
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s nicht gefunden" % name)

    def _ruft(self, methode, name: str) -> int:
        ast = self.ast
        return sum(1 for k in ast.walk(methode)
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == name)

    def test_dump_rename_uebersetzt_einschaetzung_und_vorlagen(self) -> None:
        # Der Inhalt steckt in _render_dump_rename_window, nicht in
        # _show_dump_rename - jenes oeffnet nur.
        fenster = self._methode("_render_dump_rename_window")
        self.assertGreaterEqual(
            self._ruft(fenster, "_dump_rename_uebersetzen"), 2,
            "Die Einschaetzung und die Vorlagen muessen beide durch den "
            "Uebersetzer - sonst steht im Fenster wieder fest Englisches.")

    def test_der_self_inspector_uebersetzt_den_elf_typ(self) -> None:
        bericht = self._methode("_build_self_report_text")
        self.assertGreaterEqual(self._ruft(bericht, "_elf_typ_text"), 1)
        # Und nicht mehr der rohe Wert aus dem Helfer.
        ast = self.ast
        roh = [k for k in ast.walk(bericht)
               if isinstance(k, ast.Attribute) and k.attr == "type_name"]
        self.assertEqual([], roh,
                         "Der Bericht greift wieder direkt auf type_name zu.")

    def test_der_pkg_merger_bekommt_seine_vorlagen(self) -> None:
        """Zwei Stellen: das Suchen der Saetze und das Zusammenfuehren -
        und sie liegen in zwei verschiedenen Methoden."""
        for name in ("_show_pkg_merger_dialog", "_render_pkg_merger_window"):
            with self.subTest(methode=name):
                self.assertGreaterEqual(
                    self._ruft(self._methode(name), "_pkg_merger_texte"), 1,
                    "Ohne die Vorlagen faellt das Protokoll auf die "
                    "deutsche Vorgabe des Helfers zurueck.")


class SelfInspectorTests(unittest.TestCase):
    """Der ELF-Typ kam als fertiger deutscher Text aus dem Helfer."""

    class _Elf:
        def __init__(self, e_type: int) -> None:
            self.e_type = e_type
            self.type_name = "unuebersetzt"

    def test_bekannte_typen_werden_uebersetzt(self) -> None:
        for sprache, erwartet in (("de", "ausführbar"), ("en", "executable")):
            with self.subTest(sprache=sprache):
                self.assertIn(erwartet,
                              _gui(sprache)._elf_typ_text(self._Elf(0x0002)))

    def test_unbekannte_typen_kommen_durch(self) -> None:
        """ET_SCE_EXEC und rohe Zahlen gibt es nicht zu uebersetzen."""
        self.assertEqual("unuebersetzt",
                         _gui("de")._elf_typ_text(self._Elf(0xFE00)))


class PkgMergerTests(unittest.TestCase):
    """Die Protokollzeilen kamen fest auf Deutsch aus dem Helfer."""

    def test_zu_jeder_meldung_gibt_es_einen_text(self) -> None:
        """Sonst faellt eine Zeile stillschweigend auf die Vorgabe zurueck."""
        for kennung in pkg_merger.MELDUNGEN:
            with self.subTest(kennung=kennung):
                schluessel = "pkg_merger.log_" + kennung
                self.assertIn(schluessel, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[schluessel].get(sprache, "").strip())

    def test_die_platzhalter_passen_zur_vorgabe(self) -> None:
        """Ein fehlender Platzhalter liesse die Zeile beim Formatieren fallen."""
        import re

        for kennung, vorgabe in pkg_merger.MELDUNGEN.items():
            erwartet = set(re.findall(r"\{(\w+)\}", vorgabe))
            for sprache in ("de", "en"):
                with self.subTest(kennung=kennung, sprache=sprache):
                    text = STRINGS["pkg_merger.log_" + kennung][sprache]
                    self.assertEqual(erwartet, set(re.findall(r"\{(\w+)\}", text)))

    def test_die_oberflaeche_reicht_alle_vorlagen_herein(self) -> None:
        texte = _gui("en")._pkg_merger_texte()
        self.assertEqual(set(pkg_merger.MELDUNGEN), set(texte))
        self.assertIn("skipped", texte["kein_muster"])

    def test_ohne_vorlagen_bleibt_die_vorgabe(self) -> None:
        """Andere Aufrufer - und Pruefungen - sollen unveraendert laufen."""
        zeilen: list[str] = []
        pkg_merger._melde(zeilen.append, None, "fertig_alle")
        self.assertEqual([pkg_merger.MELDUNGEN["fertig_alle"]], zeilen)

    def test_mit_vorlagen_kommt_die_uebersetzung_an(self) -> None:
        zeilen: list[str] = []
        pkg_merger._melde(zeilen.append, _gui("en")._pkg_merger_texte(),
                          "kein_muster", name="Spiel_9.pkg")
        self.assertEqual(1, len(zeilen))
        self.assertIn("Spiel_9.pkg", zeilen[0])
        self.assertIn("skipped", zeilen[0])


class KopfzeileTests(unittest.TestCase):
    """Die Kopfzeile der config.ini stand fest auf Deutsch im Quelltext."""

    def test_sie_wird_uebersetzt(self) -> None:
        for sprache, erwartet in (("de", "geschrieben von"), ("en", "written by")):
            with self.subTest(sprache=sprache):
                text = translate(sprache, "remote_ini.written_by",
                                 title="ShadowMount+", programm="Programm")
                self.assertIn(erwartet, text)
                self.assertIn("ShadowMount+", text)

    def test_der_alte_feste_text_ist_weg(self) -> None:
        with open(os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py"),
                  encoding="utf-8", errors="replace") as datei:
            quelle = datei.read()
        self.assertNotIn("– geschrieben von PS5 Dump & Image Converter", quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
