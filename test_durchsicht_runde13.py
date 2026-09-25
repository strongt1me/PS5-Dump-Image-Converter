# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 13 (24.09.2026): feste Texte.

Die meisten Stellen dieser Runde bewacht jetzt ``test_sprachlecks.py``: Sein
Rundumschlag kennt seit heute auch die ``%``-Formatierung und die Schreiber
``protokoll`` und ``_format_phase_status`` - daran waren 28 Zeilen mit
"[FEHLER] %s" in den Konsolenfenstern vorbeigegangen (H2-12, H3-18), dazu
"PKG entpackt/gebaut" (H9-13, H11-9) und zwei Statuszeilen (H6-12).

Hier stehen die beiden Stellen, die der Rundumschlag nicht sieht:

* **H1-4** - die ``ProgressEngine`` hat keinen Uebersetzer und schrieb fest
  "Abgeschlossen." in die Statuszeile.
* **H6-14** - der Fehlgrund einer gescheiterten Sammeldatei stand in einem
  dict, fest "Konvertierung fehlgeschlagen.".
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde13")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


class FortschrittTextTests(unittest.TestCase):
    """H1-4: Der Fertig-Text kommt uebersetzt aus dem Programm."""

    def test_die_engine_nimmt_den_mitgegebenen_text(self) -> None:
        engine = APP.ProgressEngine(fertig_text="Finished.")
        engine.commit_task()
        self.assertIn("Finished.", engine.tick()[1])
        engine.finish_all()
        self.assertIn("Finished.", engine.tick()[1])

    def test_das_programm_gibt_ihn_ueberall_mit(self) -> None:
        aufrufe = [k for k in ast.walk(_baum())
                   if isinstance(k, ast.Call) and getattr(k.func, "id", "") == "ProgressEngine"]
        self.assertGreaterEqual(len(aufrufe), 2)
        for aufruf in aufrufe:
            with self.subTest(zeile=aufruf.lineno):
                werte = {kw.arg: ast.unparse(kw.value) for kw in aufruf.keywords}
                self.assertEqual('self._t(\'progress.abgeschlossen\')',
                                 werte.get("fertig_text"),
                                 "Die Statuszeile zeigt sonst fest 'Abgeschlossen.'")

    def test_der_text_ist_zweisprachig(self) -> None:
        self.assertEqual("Abgeschlossen.", STRINGS["progress.abgeschlossen"]["de"])
        self.assertEqual("Finished.", STRINGS["progress.abgeschlossen"]["en"])


class SammelFehlgrundTests(unittest.TestCase):
    """H6-14: Der Fehlgrund einer gescheiterten Sammeldatei ist uebersetzt."""

    def test_kein_fester_satz_im_ergebnis(self) -> None:
        feste = [k.lineno for k in ast.walk(_methode("_run_flexible_conversion"))
                 if isinstance(k, ast.Constant)
                 and k.value == "Konvertierung fehlgeschlagen."]
        self.assertEqual([], feste)
        text = ast.unparse(_methode("_run_flexible_conversion"))
        self.assertIn("self._t('batch.konvertierung_fehlgeschlagen')", text)


class TexteTests(unittest.TestCase):
    def test_zweisprachig_mit_platzhaltern(self) -> None:
        for schluessel, platzhalter in (
                ("log.fehler_zeile", ("{text}",)), ("log.gesperrt_zeile", ("{text}",)),
                ("pkgentpacken.log_fertig", ("{quelle}", "{ziel}")),
                ("pkgbau.log_gebaut", ("{pfad}",)),
                ("abbildpkg.log_extract_fehlt", ()),
                ("batch.konvertierung_fehlgeschlagen", ())):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel].get(sprache, "")
                    self.assertTrue(text.strip())
                    for stelle in platzhalter:
                        self.assertIn(stelle, text)
        self.assertTrue(STRINGS["log.fehler_zeile"]["en"].startswith("[ERROR]"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
