# -*- coding: utf-8 -*-
"""Waechter: ``widget.configure`` wird nie als Rueckruf mit Positionsargument weitergereicht.

``RoundedButton.configure`` nimmt nur Schluesselwoerter. ``after(0, knopf.configure, {"state": ...})`` oder
``_spaeter_im_fenster(fenster, knopf.configure, {...})`` wirft deshalb im Tk-Ereignis einen ``TypeError``, der erst im
Protokoll auffaellt (19.10.2026, BACKPORT-Senden). Richtig ist ``lambda: knopf.configure(state=...)``.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
_NAMEN = ("config", "configure", "itemconfig", "itemconfigure")


class ConfigRueckrufTests(unittest.TestCase):
    def test_kein_configure_als_rueckruf_mit_positionsargument(self) -> None:
        dateien = [PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py", *sorted((PROJEKT / "ps5_validator").rglob("*.py"))]
        funde = []
        for pfad in dateien:
            baum = ast.parse(pfad.read_text(encoding="utf-8-sig"))
            for knoten in ast.walk(baum):
                if not isinstance(knoten, ast.Call):
                    continue
                for i, arg in enumerate(knoten.args):
                    if isinstance(arg, ast.Attribute) and arg.attr in _NAMEN and i + 1 < len(knoten.args):
                        funde.append("%s:%d  %s" % (pfad.relative_to(PROJEKT), knoten.lineno, ast.unparse(knoten)[:100]))
        self.assertEqual([], funde, "configure als Rueckruf mit Argument - besser ein lambda mit Schluesselwoertern")

    def test_der_waechter_erkennt_den_alten_fehler(self) -> None:
        baum = ast.parse('self._spaeter_im_fenster(seite, knopf.configure, {"state": "normal"})')
        aufruf = next(k for k in ast.walk(baum) if isinstance(k, ast.Call))
        self.assertTrue(any(isinstance(a, ast.Attribute) and a.attr in _NAMEN and i + 1 < len(aufruf.args)
                            for i, a in enumerate(aufruf.args)))


if __name__ == "__main__":
    unittest.main()
