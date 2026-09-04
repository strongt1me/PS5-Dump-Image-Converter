# -*- coding: utf-8 -*-
"""Der macOS-Bau muss anspringen, wenn sich das Buendel aendert.

Am 04.09.2026 gelernt: Eine Berichtigung am Benutzerhandbuch wurde gepusht,
der Workflow blieb aus - seine ``paths``-Liste kannte
``BENUTZERHANDBUCH.html`` nicht. Das ausgelieferte Buendel haette die alte
Fassung behalten, denn der Knopf BENUTZERHANDBUCH im Programm oeffnet genau
diese **eingebettete** Datei. Aufgefallen ist es nur, weil jemand hinterher
ins Erzeugnis gesehen hat.

Der Fehler ist nicht "eine Datei vergessen", sondern dass **nichts** die
beiden Listen gegeneinander haelt. Diese Pruefung tut das:

* Aus ``PS5ImageConverter_Pro_macos.spec`` wird gelesen, welche Pfade unter
  ``_here`` eingesammelt werden - ueber den Syntaxbaum, nicht ueber
  Zeichenkettensuche (siehe [[project_quelltextsuche_tests]]: Suchen im
  Quelltext sterben still, wenn Code umzieht).
* Aus dem Workflow wird die ``paths``-Liste gelesen.
* Jeder eingebettete Pfad muss von einem Muster gedeckt sein.

Bewusst **keine** Gleichheit gefordert: Die Liste im Workflow darf mehr
enthalten (Bauskripte, Pruefdateien, requirements.txt), denn auch die
aendern das Erzeugnis, ohne selbst darin zu liegen.
"""
from __future__ import annotations

import ast
import fnmatch
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
SPEC = PROJEKT / "PS5ImageConverter_Pro_macos.spec"
WORKFLOW = PROJEKT / ".github" / "workflows" / "macos-buendel.yml"

#: Namen, die im Bauplan zwar unter ``_here`` stehen, aber nicht ins Buendel
#: gehen - sie werden gelesen, um daraus etwas anderes zu bauen.
KEINE_BEIGABE = {
    # Das Hauptprogramm ist die Startdatei, keine Beigabe. Es steht ohnehin
    # in der Liste.
    "PS5ImageConverter_Pro_FINAL_revised.py",
}


def _ist_here_join(knoten: ast.AST) -> ast.Call | None:
    """``os.path.join(_here, X)`` - oder nichts."""
    if not isinstance(knoten, ast.Call):
        return None
    if ast.unparse(knoten.func) != "os.path.join":
        return None
    if len(knoten.args) < 2 or ast.unparse(knoten.args[0]) != "_here":
        return None
    return knoten


def eingebettete_pfade() -> set[str]:
    """Die Namen, die der Bauplan unter ``_here`` einsammelt.

    Gesucht wird jedes ``os.path.join(_here, ...)``. Der zweite Teil ist
    meist eine Zeichenkette - kommt eine neue Beigabe dazu, faellt sie hier
    von selbst an.

    **Zwei Formen, nicht eine.** Beim Schreiben nur die erste beruecksichtigt,
    und die Pruefung meldete prompt, dass ``BENUTZERHANDBUCH.html`` fehlt -
    ausgerechnet die Datei, um die es geht. Sie steht naemlich in einer
    Schleife::

        for _doc in ('BENUTZERHANDBUCH.html', 'README.md', 'CHANGELOG.md'):
            _doc_pfad = os.path.join(_here, _doc)

    Dort ist das zweite Argument ein **Name**, keine Zeichenkette. Deshalb
    werden auch Schleifen ausgewertet, die ueber feste Zeichenketten laufen
    und in ihrem Rumpf mit ``_here`` verbinden.
    """
    baum = ast.parse(SPEC.read_text(encoding="utf-8", errors="replace"))
    raus: set[str] = set()

    # Form 1: os.path.join(_here, 'name')
    for knoten in ast.walk(baum):
        ruf = _ist_here_join(knoten)
        if ruf is None:
            continue
        arg = ruf.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            raus.add(arg.value)

    # Form 2: for <name> in ('a', 'b'): ... os.path.join(_here, <name>)
    for schleife in ast.walk(baum):
        if not isinstance(schleife, ast.For):
            continue
        if not isinstance(schleife.target, ast.Name):
            continue
        if not isinstance(schleife.iter, (ast.Tuple, ast.List)):
            continue
        werte = [k.value for k in schleife.iter.elts
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if not werte:
            continue
        benutzt = any(
            _ist_here_join(k) is not None
            and ast.unparse(_ist_here_join(k).args[1]) == schleife.target.id
            for rumpf in schleife.body for k in ast.walk(rumpf))
        if benutzt:
            raus.update(werte)

    return raus - KEINE_BEIGABE


def ausloeser_muster() -> list[str]:
    """Die ``paths``-Liste des Workflows."""
    import yaml  # noqa: PLC0415

    inhalt = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    # 'on' ist in YAML 1.1 ein Wahrheitswert - je nach Lader steht der
    # Abschnitt unter True statt unter 'on'. Beide Wege nehmen.
    abschnitt = inhalt.get("on", inhalt.get(True, {}))
    return list(abschnitt.get("push", {}).get("paths", []))


def gedeckt(pfad: str, muster: list[str]) -> bool:
    """Deckt eines der Muster diesen Pfad ab?

    ``Anleitungen/**`` deckt den Ordner ``Anleitungen``; GitHub versteht
    ``**`` als "alles darunter", und eine Aenderung an einer Datei darin
    traegt den Ordnernamen als Anfang.
    """
    for m in muster:
        if m == pfad or fnmatch.fnmatch(pfad, m):
            return True
        if m.endswith("/**") and fnmatch.fnmatch(pfad, m[:-3]):
            return True
    return False


class AusloeserTests(unittest.TestCase):
    """Was ins Buendel geht, muss den Bau ausloesen."""

    @classmethod
    def setUpClass(cls) -> None:
        if not SPEC.is_file():
            raise unittest.SkipTest("Kein macOS-Bauplan im Bestand.")
        if not WORKFLOW.is_file():
            raise unittest.SkipTest("Kein macOS-Workflow im Bestand.")
        cls.pfade = eingebettete_pfade()
        cls.muster = ausloeser_muster()

    def test_der_bauplan_gibt_ueberhaupt_etwas_her(self) -> None:
        """Ohne das saehe die Pruefung unten leer und meldete Erfolg."""
        self.assertGreaterEqual(
            len(self.pfade), 10,
            "Nur %d Pfade aus dem Bauplan gelesen - die Auswertung greift "
            "nicht mehr." % len(self.pfade))

    def test_die_ausloeserliste_ist_lesbar(self) -> None:
        self.assertGreaterEqual(
            len(self.muster), 10,
            "Nur %d Muster im Workflow gefunden." % len(self.muster))

    def test_jede_beigabe_loest_den_bau_aus(self) -> None:
        fehlend = sorted(p for p in self.pfade if not gedeckt(p, self.muster))
        self.assertEqual(
            [], fehlend,
            "Diese Dateien gehen ins Buendel, loesen den Bau aber nicht aus:\n"
            + "\n".join("  - %s" % p for p in fehlend))

    def test_das_handbuch_ist_dabei(self) -> None:
        """Der Fall, der die Pruefung ausgeloest hat - namentlich."""
        self.assertIn("BENUTZERHANDBUCH.html", self.pfade,
                      "Das Handbuch wird nicht mehr eingebettet - Test pruefen.")
        self.assertTrue(gedeckt("BENUTZERHANDBUCH.html", self.muster))

    def test_die_pruefung_wuerde_eine_luecke_melden(self) -> None:
        """Gegenprobe: Ohne sie waere nicht belegt, dass oben etwas gemessen wird."""
        ohne = [m for m in self.muster if m != "BENUTZERHANDBUCH.html"]
        self.assertFalse(
            gedeckt("BENUTZERHANDBUCH.html", ohne),
            "Ein anderes Muster deckt das Handbuch mit ab - dann sagt "
            "test_das_handbuch_ist_dabei nichts.")

    def test_der_workflow_prueft_sich_selbst_mit(self) -> None:
        """Wer die Liste aendert, soll den Lauf ausloesen."""
        self.assertTrue(
            gedeckt(".github/workflows/macos-buendel.yml", self.muster))

    def test_diese_pruefdatei_steht_in_der_liste(self) -> None:
        """Sonst liefe sie im macOS-Lauf nicht mit, wenn nur sie sich aendert."""
        self.assertTrue(gedeckt("test_macos_ausloeser.py", self.muster))


if __name__ == "__main__":
    unittest.main(verbosity=2)
