# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 15 (24.09.2026): Berichte.

Drei Berichte, die in einem Fenster stehen, aber fest deutsch geschrieben
wurden - auch auf der englischen Oberflaeche:

* **H1-12** - der Fortschrittswaechter im Diagnosebericht
  ("Messpunkte: ...", "Befund: keine Auffaelligkeit").
* **U2-8** - "Aktualisierungen pruefen" im Diagnosefenster
  ("Aktualisierungen: 1 Aktualisierung verfuegbar", "0.0.9 -> 1.0.0 verfuegbar").
* **H10-4** - der Befund im Fenster "App direkt installieren"
  ("Bauform", "Kennung", "Bereit zum Installieren.").

Die Module duerfen i18n nicht einbinden: Sie tragen ihre Saetze als
``MELDUNGEN`` (Vorgabe deutsch) und nehmen ueber ``texte=`` die uebersetzten
entgegen - dasselbe Muster wie ``anzeige_diagnose`` und ``payload_versand``.
Ohne ``texte`` bleibt alles wie bisher; darauf bauen die aelteren Tests.
"""
from __future__ import annotations

import ast
import re
import string
import sys
import types
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde15")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import aktualisierungen as ak      # noqa: E402
from ps5_validator.utils import app_install                 # noqa: E402
from ps5_validator.utils.i18n import STRINGS, translate     # noqa: E402

#: Woran ein deutscher Satz zu erkennen ist (Auswahl aus test_sprachlecks).
DEUTSCH = re.compile(
    r"[äöüÄÖÜß]|\b(?:der|die|das|und|nicht|über|Balken|Befund|Messpunkte|"
    r"verfügbar|Aktualisierungen?|Bauform|Kennung|Ordner|Bereit|Hinweis|FEHLER|"
    r"keine|aktuell|unbekannt|fehlt)\b")

_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _englisch(meldungen: dict, praefix: str) -> dict:
    return {k: STRINGS[praefix + k]["en"] for k in meldungen}


def _felder(vorlage: str) -> set:
    return {f for _t, f, _s, _k in string.Formatter().parse(vorlage) if f}


class _Platzhalter:
    def pruefe(self, meldungen: dict, praefix: str) -> None:
        for kennung, vorgabe in meldungen.items():
            for sprache in ("de", "en"):
                with self.subTest(kennung=kennung, sprache=sprache):
                    text = STRINGS[praefix + kennung][sprache]
                    self.assertTrue(text.strip())
                    self.assertEqual(_felder(vorgabe), _felder(text),
                                     "Platzhalter weichen von der Vorgabe ab")


class WaechterTests(unittest.TestCase, _Platzhalter):
    """H1-12: der Abschnitt "Fortschrittsanzeige" im Diagnosebericht."""

    def _lauf(self):
        """Ein Lauf, der moeglichst viele Befunde ausloest."""
        w = APP.FortschrittsWaechter()
        punkte = [(0, 10, "Phase 1/4 - 1.0 GB / 9.0 GB"),
                  (1, 5, "Phase 2/4 - 1.0 GB / 9.0 GB"),
                  (30, 60, "Phase 1/4 - 1.0 GB / 9.0 GB"),
                  (31, 120, "Phase 3/3 - 1.0 GB / 9.0 GB")]
        for zeit, balken, text in punkte:
            w.beobachte(balken, "50", text, jetzt=zeit)
        w.abschliessen(90)
        return w

    def test_ohne_texte_bleibt_es_deutsch(self) -> None:
        w = self._lauf()
        self.assertTrue(any("zurück" in b for b in w.befunde()))
        self.assertTrue(w.bericht()[0].startswith("Messpunkte"))
        self.assertEqual(["(seit dem Start lief keine Aufgabe - nichts gemessen)"],
                         APP.FortschrittsWaechter().bericht())

    def test_mit_englischen_texten_ist_nichts_deutsch(self) -> None:
        texte = _englisch(APP.FortschrittsWaechter.MELDUNGEN, "waechter.")
        w = self._lauf()
        befunde = w.befunde(texte=texte)
        self.assertGreaterEqual(len(befunde), 5)
        for zeile in w.bericht(texte=texte) + APP.FortschrittsWaechter().bericht(texte=texte):
            with self.subTest(zeile=zeile):
                self.assertIsNone(DEUTSCH.search(zeile), zeile)

    def test_texte_sind_zweisprachig(self) -> None:
        self.pruefe(APP.FortschrittsWaechter.MELDUNGEN, "waechter.")

    def test_der_diagnosebericht_gibt_sie_mit(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "utils" / "diagnose_befund.py").read_text(
            encoding="utf-8")
        baum = ast.parse(quelle)
        methode = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)
                       and k.name == "_diagnose_fortschritt")
        text = ast.unparse(methode)
        self.assertIn("bericht(texte=", text)
        self.assertIn("'waechter.'", text)


class AktualisierungenTests(unittest.TestCase, _Platzhalter):
    """U2-8: "Aktualisierungen pruefen" im Diagnosefenster."""

    BEFUNDE = [
        ak.Befund("MkPFS", "0.0.9", "1.0.0", ak.VERALTET, "https://x"),
        ak.Befund("zlib-ng", "2.2.4", "2.2.4", ak.AKTUELL),
        ak.Befund("lz4", "4.4.5", "4.4.0", ak.VORAUS),
        ak.Befund("ISA-L", "2.31", "", ak.FEHLER, "", "timeout"),
        ak.Befund("tkinterdnd2", "vorhanden", "0.4.2", ak.UNBEKANNT),
        ak.Befund("PyInstaller", "unbekannt", "", ak.UNBEKANNT),
    ]

    def test_ohne_texte_bleibt_es_deutsch(self) -> None:
        self.assertIn("verfügbar", str(self.BEFUNDE[0]))
        self.assertIn("1 Aktualisierung verfügbar", ak.zusammenfassung(self.BEFUNDE))

    def test_mit_englischen_texten_ist_nichts_deutsch(self) -> None:
        texte = _englisch(ak.MELDUNGEN, "aktualisierung.")
        zeilen = [ak.zusammenfassung(self.BEFUNDE, texte=texte),
                  ak.zusammenfassung([], texte=texte)]
        zeilen += [b.text(texte=texte) for b in self.BEFUNDE]
        for zeile in zeilen:
            with self.subTest(zeile=zeile):
                self.assertIsNone(DEUTSCH.search(zeile), zeile)
        self.assertIn("1.0.0", zeilen[2])
        self.assertIn("https://x", zeilen[2])

    def test_texte_sind_zweisprachig(self) -> None:
        self.pruefe(ak.MELDUNGEN, "aktualisierung.")

    def test_das_fenster_gibt_sie_mit(self) -> None:
        text = ast.unparse(_methode("_render_diagnostic_report_window"))
        self.assertIn("ak.MELDUNGEN", text)
        self.assertIn("'aktualisierung.'", text)
        self.assertNotIn("str(b) for b in befunde", text)


class AppInstallBerichtTests(unittest.TestCase):
    """H10-4: der Befund im Fenster "App direkt installieren"."""

    def _gui(self, sprache: str):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda key, **kw: translate(sprache, key, **kw)
        return gui

    def _angaben(self, art=app_install.ART_PROGRAMM):
        # SimpleNamespace statt Mock: Mock(name=...) setzt kein Attribut "name".
        return types.SimpleNamespace(art=art, ordner="C:/app", kennung="FAKE02932",
                                     name="Probe", huelle="", autoritaet="", icon="",
                                     uri="pslauncher://x")

    def test_englisch_ist_nichts_deutsch(self) -> None:
        gui = self._gui("en")
        for art in (app_install.ART_DEEPLINK, app_install.ART_PROGRAMM):
            angaben = self._angaben(art)
            with self.subTest(art=art):
                text = gui._appinstall_bericht(angaben, [], ["note"])
                self.assertIsNone(DEUTSCH.search(text), text)
                self.assertIn(STRINGS["appinstall.bericht.bereit"]["en"], text)
        fehler = gui._appinstall_bericht(None, ["boom"], [])
        self.assertIn(STRINGS["appinstall.bericht.fehler"]["en"], fehler)

    def test_die_spalten_bleiben_buendig(self) -> None:
        for sprache in ("de", "en"):
            text = self._gui(sprache)._appinstall_bericht(self._angaben(app_install.ART_PROGRAMM), [], [])
            spalten = {zeile.index(": ") for zeile in text.splitlines() if ": " in zeile}
            with self.subTest(sprache=sprache):
                self.assertEqual(1, len(spalten), text)
