# -*- coding: utf-8 -*-
"""Gemeinsame pytest-Einstellungen der Testreihe.

**Syntaxbaeume nach jeder Testklasse freigeben.** Rund zwanzig Testklassen
parsen in ``setUpClass`` das Hauptmodul und legen den Baum als
Klassenattribut ab (``cls.baum = ast.parse(...)``). Klassen leben bis zum
Ende des Laufs - ihre Baeume bisher auch. Gemessen am 19.09.2026: ein Baum
des Hauptmoduls (2,8 MB Quelltext, 266.898 Knoten) belegt rund 80 MB. Im
Volllauf wuchs der pytest-Prozess auf 6,5 GB privaten Speicher, frei blieben
zuletzt 25 MB; im Lauf davor scheiterte so der Aufbau von
``test_werkzeugfeinheiten`` mit ``MemoryError`` - zweimal sogar als
scheinbares ``SyntaxError: invalid syntax`` in einer gueltigen Zeile.

Freigegeben werden nur Werte, die ein ``ast.AST`` sind. Ein Klassenattribut
mit einer Tk-Wurzel oder -Variablen loszulassen koennte Tcl mitten im Lauf
abreissen (eine Wurzel je Prozess, nie zerstoeren - siehe ``pruefumgebung``).
"""
from __future__ import annotations

import ast

import pytest


@pytest.fixture(autouse=True, scope="class")
def _syntaxbaeume_freigeben(request: pytest.FixtureRequest):
    """Nach der letzten Pruefung einer Klasse: ihre Syntaxbaeume loslassen."""
    yield
    klasse = request.cls
    if klasse is None:
        return
    for name, wert in list(vars(klasse).items()):
        if isinstance(wert, ast.AST):
            delattr(klasse, name)
