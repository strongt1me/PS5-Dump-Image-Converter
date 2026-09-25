# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 18 (25.09.2026): param_check.

Die inhaltliche Pruefung der ``param.json`` meldete nur ihre Zusammenfassung
uebersetzt ("param.json: 2 Fehler"). Die Befundzeilen selbst, die
Reparaturschritte, die Typnamen und die Vorsaetze "[FEHLER]/[WARNUNG]/
[HINWEIS]" standen fest deutsch im Modul - im Protokoll, im Reparaturdialog,
in der Bibliothek und als "param.json: ..." im Dump-Validator.

Umgestellt per Syntaxbaum-Skript: 105 Meldungsstellen, 104 Vorlagen (Kennung
= Pruefung_Schweregrad_Nummer), dazu 9 Vorlagen fuer Typnamen und Vorsaetze.
Die deutschen Vorgaben sind wortgleich mit dem frueheren Text (per Skript
gegen die Sicherung belegt) - test_param_check liest sie.

**Neue Fehlerklasse dabei:** Der Platzhalter ``{kennung}`` hiess wie der
zweite Parameter von ``_satz(texte, kennung, **werte)``. Als Schluesselwort
uebergeben endete das in "got multiple values for argument 'kennung'" - die
Reparatur brach ab. Alle Vorlagen-Helfer haben deshalb nur-positionelle
Parameter (``/``); der Waechter unten prueft das fuer jedes Modul.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import os
import re
import string
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde18")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.core import dispatcher, validator_base   # noqa: E402
from ps5_validator.modules.dump_validator import DumpValidator  # noqa: E402
from ps5_validator.utils import param_check                 # noqa: E402
from ps5_validator.utils.i18n import translate              # noqa: E402

PARAM_EN = {k: translate("en", "paramcheck." + k) for k in param_check.MELDUNGEN}
VALIDATOR_EN = {k: translate("en", "validator." + k) for k in dispatcher.MELDUNGEN}

_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _param_json(ordner: str, inhalt: bytes) -> str:
    sce_sys = os.path.join(ordner, "sce_sys")
    os.makedirs(sce_sys, exist_ok=True)
    pfad = os.path.join(sce_sys, "param.json")
    with open(pfad, "wb") as datei:
        datei.write(inhalt)
    return pfad


# ---------------------------------------------------------------- Befunde

class BefundTests(unittest.TestCase):
    """Mit englischen Vorlagen kommt jeder Befund englisch heraus."""

    def test_bom(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = _param_json(ordner, b"\xef\xbb\xbf{}")
            befund = param_check.pruefe_datei(pfad, texte=PARAM_EN)
        self.assertIn("The file starts with a UTF-8 BOM - that alone is enough for "
                      "'invalid param.json'. It must be saved without a BOM.", befund.fehler)
        self.assertIn("Required field 'titleId' is missing", befund.fehler)

    def test_syntaxfehler(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = _param_json(ordner, b'{"titleId": "PPSA12345",}')
            befund = param_check.pruefe_datei(pfad, texte=PARAM_EN)
        self.assertTrue(befund.fehler[0].startswith("JSON syntax error in line 1, column"),
                        befund.fehler)
        self.assertIn("  -> there is at least one comma before a closing bracket",
                      befund.fehler)

    def test_typnamen_und_vorsaetze(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = _param_json(ordner, b'{"titleId": 5, "applicationCategoryType": 0,'
                                       b' "localizedParameters": {}}')
            befund = param_check.pruefe_datei(pfad, texte=PARAM_EN)
        self.assertIn("titleId: expected string, found integer (5)", befund.fehler)
        self.assertIn("[ERROR] titleId: expected string, found integer (5)",
                      befund.als_text())
        zusammenfassung = befund.zusammenfassung()
        self.assertIn("error(s)", zusammenfassung,
                      "Die Zusammenfassung nimmt die Vorlagen des Befunds.")
        self.assertNotIn("Fehler", zusammenfassung)

    def test_ohne_texte_bleibt_die_vorgabe(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = _param_json(ordner, b"\xef\xbb\xbf{}")
            befund = param_check.pruefe_datei(pfad)
        self.assertIn("Pflichtfeld 'titleId' fehlt", befund.fehler)
        self.assertTrue(befund.als_text()[0].startswith("[FEHLER] "))


class ReparaturTests(unittest.TestCase):
    def test_schritte_englisch(self) -> None:
        _neu, schritte = param_check.repariere({"titleId": "PPSA12345"}, texte=PARAM_EN)
        self.assertIn("localizedParameters created", schritte)
        self.assertIn("ageLevel created with all countries (level 0)", schritte)

    def test_kennung_als_platzhalter(self) -> None:
        """Der Fall, an dem die Reparatur mit TypeError abbrach."""
        _neu, schritte = param_check.repariere(
            {"titleId": "ppsa1234",
             "contentId": "UP0000-PPSA12345_00-ABCDEFGHIJKLMNOP"}, texte=PARAM_EN)
        self.assertIn("titleId corrected from 'ppsa1234' to 'PPSA12345' (from the contentId)",
                      schritte)


class DumpValidatorTests(unittest.TestCase):
    """Die param.json-Zeilen im Dump-Validator (Aufgabe 8)."""

    def test_param_zeilen_englisch(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            _param_json(ordner, b"\xef\xbb\xbf{}")
            ergebnis = dispatcher.validate(ordner, "dump", texte=VALIDATOR_EN,
                                           param_texte=PARAM_EN)
        self.assertIn("param.json: Required field 'titleId' is missing", ergebnis.errors)
        self.assertFalse([e for e in ergebnis.errors if "Pflichtfeld" in e])

    def test_aufgabe_8_reicht_sie_durch(self) -> None:
        aufrufe = [k for k in ast.walk(_methode("_mode_dump_validator"))
                   if isinstance(k, ast.Call) and getattr(k.func, "id", "") == "_validate"]
        self.assertEqual(1, len(aufrufe))
        self.assertIn("param_texte", {w.arg for w in aufrufe[0].keywords})


# ---------------------------------------------------------------- Struktur

class KeinFesterBefundTests(unittest.TestCase):
    def test_jede_meldung_kommt_aus_einer_vorlage(self) -> None:
        baum = ast.parse(Path(param_check.__file__).read_text(encoding="utf-8"))
        feste, gesehen = [], 0
        for k in ast.walk(baum):
            if not (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)):
                continue
            empfaenger = getattr(k.func.value, "id", "")
            if not ((k.func.attr in ("fehler_melden", "warnen", "hinweis")
                     and empfaenger == "befund")
                    or (k.func.attr == "append" and empfaenger == "aenderungen")):
                continue
            gesehen += 1
            if not (k.args and isinstance(k.args[0], ast.Call)):
                feste.append((k.lineno, ast.unparse(k.args[0])[:80] if k.args else ""))
        self.assertGreaterEqual(gesehen, 100, "Die Suche findet die Stellen nicht mehr.")
        self.assertEqual([], feste)


class PlatzhalterUndParameterTests(unittest.TestCase):
    """Kein Platzhalter darf heissen wie ein Parameter seines Helfers.

    Sonst endet ``_satz(texte, "x", kennung=...)`` in "got multiple values
    for argument" - gemessen in Runde 18 an ``{kennung}``.
    """

    @staticmethod
    def _platzhalter(modul) -> set:
        namen = set()
        for name, wert in vars(modul).items():
            if name.endswith("MELDUNGEN") and isinstance(wert, dict):
                for vorlage in wert.values():
                    namen |= {f for _t, f, _s, _k in string.Formatter().parse(vorlage) if f}
        return namen

    @staticmethod
    def _per_name_uebergebbar(helfer) -> set:
        return {p.name for p in inspect.signature(helfer).parameters.values()
                if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)}

    def test_alle_vorlagen_module(self) -> None:
        from test_sprachlecks import VorlagenHabenSchluesselTests
        faelle = [(modulname, helfer)
                  for modulname, helfer, *_rest in VorlagenHabenSchluesselTests.PROBEN]
        self.assertGreaterEqual(len(faelle), 12)
        for modulname, helfername in faelle:
            modul = importlib.import_module(modulname)
            helfer = getattr(modul, helfername)
            with self.subTest(modul=modulname, helfer=helfername):
                self.assertEqual(set(), self._platzhalter(modul)
                                 & self._per_name_uebergebbar(helfer))

    def test_befund_und_validatoren(self) -> None:
        for helfer, modul in ((param_check.Befund.satz, param_check),
                              (validator_base.BaseValidator._text, dispatcher),
                              (validator_base.vorlage_fuellen, dispatcher)):
            with self.subTest(helfer=helfer.__qualname__):
                self.assertEqual(set(), self._platzhalter(modul)
                                 & self._per_name_uebergebbar(helfer))


if __name__ == "__main__":
    unittest.main()
