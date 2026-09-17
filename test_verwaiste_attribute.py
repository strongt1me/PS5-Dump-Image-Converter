# -*- coding: utf-8 -*-
"""Sucht ``getattr(self, "name", vorgabe)`` fuer Attribute, die es nicht gibt.

Diese Schreibweise wirft nicht. Fehlt das Attribut, liefert sie stumm die
Vorgabe - und der Zweig dahinter laeuft nie. Das Projekt hatte den Fehler
schon zweimal:

* ``getattr(self, "_settings", {})`` las ins Leere; das Attribut gab es nie.
* ``getattr(self, "_engine_done_event", None)`` in ``_kill_task``: Der
  dokumentierte Schritt 3 ("file_monitor-Thread stoppen") tat deshalb
  nichts. Das Ereignis entstand als lokale Variable und hiess auf ``self``
  anders. Der Messfaden pollte nach einem Abbruch alle 150 ms weiter, bis
  mkpfs von sich aus fertig war - bei grossen Abbildern minutenlang.
  Gefunden am 23.08.2026.

Beide Male half kein Test, weil nichts abstuerzt. Diese Pruefung sucht die
Faelle strukturell.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _gelesen_und_gesetzt(quelle: str) -> tuple[dict[str, list[int]], set[str]]:
    """Sammelt gelesene ``getattr``-Namen und alle je gesetzten Attribute."""
    baum = ast.parse(quelle)
    gelesen: dict[str, list[int]] = {}
    gesetzt: set[str] = set()

    for knoten in ast.walk(baum):
        if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name)
                and knoten.func.id == "getattr" and len(knoten.args) == 3
                and isinstance(knoten.args[0], ast.Name)
                and knoten.args[0].id == "self"
                and isinstance(knoten.args[1], ast.Constant)
                and isinstance(knoten.args[1].value, str)):
            gelesen.setdefault(knoten.args[1].value, []).append(knoten.lineno)

        # x.name = ... - der Traeger ist egal. Attribute werden auch von
        # aussen gesetzt (app._cli_param_online = ...), nicht nur ueber self.
        if isinstance(knoten, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            ziele = (knoten.targets if isinstance(knoten, ast.Assign)
                     else [knoten.target])
            for ziel in ziele:
                if isinstance(ziel, ast.Attribute):
                    gesetzt.add(ziel.attr)
                elif isinstance(ziel, ast.Name):
                    gesetzt.add(ziel.id)      # Klassenvariable

        # setattr(self, name, ...) - der Name kann eine Variable sein.
        if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name)
                and knoten.func.id == "setattr" and len(knoten.args) >= 2):
            if isinstance(knoten.args[1], ast.Constant):
                gesetzt.add(knoten.args[1].value)

    return gelesen, gesetzt


class VerwaisteAttributeTests(unittest.TestCase):
    """Kein ``getattr`` darf auf ein Attribut zeigen, das nie entsteht."""

    #: Diese Namen werden ueber eine Schleife mit ``setattr`` gesetzt, deren
    #: Namensliste erst zur Laufzeit feststeht - der Scan sieht sie nicht.
    #: Am 23.08.2026 einzeln von Hand nachgeprueft.
    UEBER_SCHLEIFE_GESETZT = {
        "verify_title",         # Zeile 4958, Schleife ueber Kartentitel
        "worker_title",         # Zeile 4957, dieselbe Schleife
    }

    #: Diese sind Methoden. ``getattr(self, "name", None)`` fragt dort nach
    #: einer Faehigkeit, nicht nach einem Wert - das ist Absicht.
    METHODEN = {"_load_setting"}

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = HAUPTDATEI.read_text(encoding="utf-8")
        cls.gelesen, cls.gesetzt = _gelesen_und_gesetzt(cls.quelle)

    def test_es_gibt_ueberhaupt_solche_zugriffe(self) -> None:
        """Sonst prueft der Test unbemerkt nichts mehr."""
        self.assertGreater(len(self.gelesen), 50,
                           "So wenige Zugriffe? Vermutlich greift der Scan "
                           "nicht mehr.")

    def test_kein_zugriff_laeuft_ins_leere(self) -> None:
        verwaist = {}
        for name, zeilen in self.gelesen.items():
            if name in self.gesetzt:
                continue
            if name in self.UEBER_SCHLEIFE_GESETZT or name in self.METHODEN:
                continue
            if ("def %s(" % name) in self.quelle:
                continue      # doch eine Methode
            verwaist[name] = zeilen

        self.assertEqual(
            verwaist, {},
            "Diese Attribute werden gelesen, aber nie gesetzt - der Zweig "
            "dahinter laeuft nie:\n" + "\n".join(
                "   %s (Zeilen %s)" % (n, z) for n, z in sorted(verwaist.items())))

    def _methode(self, name: str) -> ast.FunctionDef:
        klasse = next(k for k in ast.walk(ast.parse(self.quelle))
                      if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        return next(m for m in klasse.body
                    if isinstance(m, ast.FunctionDef) and m.name == name)

    def test_der_abbruch_erreicht_den_messfaden(self) -> None:
        """Der konkrete Fall von damals, festgehalten - ueber den Baum.

        ``_kill_task`` nennt in seiner Ablaufbeschreibung Schritt 3
        ausdruecklich. Damit der nicht wieder still ins Leere greift, muss
        das Ereignis dort entstehen, wo mkpfs laeuft, auf ``self`` liegen und
        vom Messfaden abgefragt werden.

        Es darf aber NICHT das Fertig-Ereignis der Engine sein. Bis v1.9.24
        war es dasselbe: Der Abbruch meldete "Engine fertig", obwohl mkpfs im
        Prozess weiterlief. Die Warteschleife endete ohne abort_requested,
        der Abbruchzweig lief nie, und ein Neustart geriet an den noch
        schreibenden alten Lauf.
        """
        methode = self._methode("_execute_mkpfs")

        veroeffentlicht = [
            k.value.id for k in ast.walk(methode)
            if isinstance(k, ast.Assign) and isinstance(k.value, ast.Name)
            and any(isinstance(z, ast.Attribute) and z.attr == "_engine_done_event"
                    and isinstance(z.value, ast.Name) and z.value.id == "self"
                    for z in k.targets)]
        self.assertEqual(
            len(veroeffentlicht), 1,
            "_execute_mkpfs veroeffentlicht das Abbruch-Ereignis nicht mehr "
            "(genau eine Zuweisung self._engine_done_event = <Ereignis>) - "
            "der Abbruch kann den Messfaden dann nicht stoppen.")
        griff = veroeffentlicht[0]

        gewartet = [
            k.test.operand.func.value.id for k in ast.walk(methode)
            if isinstance(k, ast.While) and isinstance(k.test, ast.UnaryOp)
            and isinstance(k.test.op, ast.Not)
            and isinstance(k.test.operand, ast.Call)
            and isinstance(k.test.operand.func, ast.Attribute)
            and k.test.operand.func.attr == "wait"
            and isinstance(k.test.operand.func.value, ast.Name)]
        self.assertTrue(
            gewartet,
            "Die Warteschleife 'while not <fertig>.wait(...)' fehlt - der "
            "Test misst sonst nichts.")
        self.assertNotIn(
            griff, gewartet,
            "Das veroeffentlichte Abbruch-Ereignis ist dasselbe, auf das die "
            "Warteschleife als 'Engine fertig' wartet. Ein Abbruch beendet "
            "dann die Schleife ohne abort_requested, obwohl mkpfs weiterlaeuft.")

        abgefragt = any(
            isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
            and k.func.attr in ("is_set", "wait")
            and isinstance(k.func.value, ast.Name) and k.func.value.id == griff
            for innen in ast.walk(methode)
            if isinstance(innen, ast.FunctionDef) and innen is not methode
            for k in ast.walk(innen))
        self.assertTrue(
            abgefragt,
            "Kein innerer Faden fragt das Abbruch-Ereignis '%s' ab - der "
            "Messfaden laeuft nach einem Abbruch weiter." % griff)

        for name in ("_kill_task", "on_closing", "_shutdown_cleanup_and_execute"):
            with self.subTest(abbruchweg=name):
                liest = any(
                    isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
                    and k.func.id == "getattr" and len(k.args) >= 2
                    and isinstance(k.args[1], ast.Constant)
                    and k.args[1].value == "_engine_done_event"
                    for k in ast.walk(self._methode(name)))
                self.assertTrue(
                    liest, "%s liest das Abbruch-Ereignis nicht mehr." % name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
