# -*- coding: utf-8 -*-
"""Ein Instanzattribut darf keine Methode ueberdecken (Fehlerklasse aus dem Protokoll vom 17.11.2026).

Am 17.11.2026 um 23:10 stand im Protokoll zweimal ``TypeError: 'str' object is not callable`` aus dem Balken der
Knopfleiste: Die Unterklasse (``leisten_balken``) hatte eine Methode ``_grund``, die Basisklasse
(``ps4_ota_bausteine``) setzte im Konstruktor ``self._grund = <Farbname>``. Der Aufruf ``self._grund(b, h)`` traf den Text,
und jedes ``<Configure>``-Ereignis warf den Fehler erneut. Der Fehler lag nur in einem Zwischenstand (die Methode heisst seit
dem Commit 7eb5741 ``_ausschnitt``), aber nichts haette ihn bemerkt, solange das Fenster nicht gezeichnet wird.

Gesucht wird ueber den Syntaxbaum: Jede Klasse des Projekts, in der ``self.X = ...`` (auch ``+=`` und Typangabe) einen Namen
belegt, den dieselbe Klasse oder eine Basisklasse des Projekts als **Methode** definiert. Eigenschaften (``@property`` mit
``setter``, ``cached_property``) zaehlen nicht - dort ist die Zuweisung gewollt. Basisklassen aus fremden Paketen (``tk.Canvas``)
kennt die Suche nicht.
"""
from __future__ import annotations

import ast
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: ``"Klasse.Name"`` -> Grund. Nur eintragen, wenn die Zuweisung die Methode **mit Absicht** ersetzt (dann steht hier warum).
ERLAUBT: dict[str, str] = {}


def _ist_eigenschaft(f: "ast.FunctionDef | ast.AsyncFunctionDef") -> bool:
    for d in f.decorator_list:
        text = ast.unparse(d)
        if text in ("property", "cached_property", "functools.cached_property") or text.endswith((".setter", ".getter", ".deleter")):
            return True
    return False


def _klassen_lesen(dateien: "list[Path]") -> "dict[str, list[tuple]]":
    """Name -> [(Datei, Basen, Methoden {Name: Zeile}, Attribute {Name: Zeile}, Zeile)] fuer jede Klasse jeder Datei."""
    klassen: "dict[str, list[tuple]]" = {}
    for datei in dateien:
        baum = ast.parse(datei.read_text(encoding="utf-8-sig"))
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.ClassDef):
                continue
            basen = [b.id if isinstance(b, ast.Name) else b.attr for b in knoten.bases if isinstance(b, (ast.Name, ast.Attribute))]
            methoden: dict = {}
            for stelle in knoten.body:
                if isinstance(stelle, (ast.FunctionDef, ast.AsyncFunctionDef)) and not _ist_eigenschaft(stelle):
                    methoden[stelle.name] = stelle.lineno
            attribute: dict = {}
            for f in ast.walk(knoten):
                if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for a in ast.walk(f):
                    if isinstance(a, ast.Assign):
                        ziele = a.targets
                    elif isinstance(a, (ast.AnnAssign, ast.AugAssign)):
                        ziele = [a.target]
                    else:
                        continue
                    for z in ziele:
                        for t in ast.walk(z):
                            if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
                                    and isinstance(t.ctx, ast.Store)):
                                attribute.setdefault(t.attr, a.lineno)
            klassen.setdefault(knoten.name, []).append((datei, basen, methoden, attribute, knoten.lineno))
    return klassen


def _basen(name: str, klassen: dict, gesehen: "set | None" = None) -> "list[str]":
    gesehen = gesehen if gesehen is not None else set()
    ergebnis: "list[str]" = []
    for eintrag in klassen.get(name, []):
        for b in eintrag[1]:
            if b not in gesehen:
                gesehen.add(b)
                ergebnis.append(b)
                ergebnis.extend(_basen(b, klassen, gesehen))
    return ergebnis


def ueberdeckungen(dateien: "list[Path]") -> "list[str]":
    """Eine Zeile je Fund: ``Datei:Zeile Klasse.Name ...``."""
    klassen = _klassen_lesen(dateien)
    funde: "list[str]" = []
    for name, eintraege in klassen.items():
        for datei, basen, methoden, attribute, zeile in eintraege:
            alle: "list[str]" = []
            gesehen: set = set()
            for b in basen:
                if b not in gesehen:
                    gesehen.add(b)
                    alle.append(b)
                    alle.extend(_basen(b, klassen, gesehen))
            # Eine Instanz der Klasse traegt die Attribute der Klasse UND ihrer Basen und kennt die Methoden beider: der Fall vom
            # 17.11. entstand, weil die Basis das Attribut setzte und erst die Unterklasse die Methode gleichen Namens hatte.
            attribute_alle = {a: (name, z) for a, z in attribute.items()}
            methoden_alle = {m: (name, z) for m, z in methoden.items()}
            for b in alle:
                for e in klassen.get(b, []):
                    for a, z in e[3].items():
                        attribute_alle.setdefault(a, (b, z))
                    for m, z in e[2].items():
                        methoden_alle.setdefault(m, (b, z))
            for attr in sorted(set(attribute_alle) & set(methoden_alle)):
                if "%s.%s" % (name, attr) in ERLAUBT:
                    continue
                (aklasse, azeile), (mklasse, _mzeile) = attribute_alle[attr], methoden_alle[attr]
                funde.append("%s:%d  %s: self.%s = ... (%s, Zeile %d) ueberdeckt die Methode %s.%s"
                             % (datei.name, zeile, name, attr, aklasse, azeile, mklasse, attr))
    return sorted(funde)


class ErkennungTests(unittest.TestCase):
    """Die Suche muss den echten Fehler finden und Erlaubtes durchlassen (Gegenprobe zum Waechter unten)."""

    def setUp(self) -> None:
        self.ordner = Path(tempfile.mkdtemp(prefix="namensueberdeckung_"))
        self.addCleanup(shutil.rmtree, self.ordner, True)

    def _suchen(self, **quelltexte: str) -> "list[str]":
        dateien = []
        for name, text in quelltexte.items():
            pfad = self.ordner / (name + ".py")
            pfad.write_text(text, encoding="utf-8")
            dateien.append(pfad)
        return ueberdeckungen(dateien)

    def test_der_fall_vom_17_11_basis_setzt_text_unterklasse_hat_die_methode(self) -> None:
        funde = self._suchen(
            basis="class Pille:\n    def __init__(self, grund):\n        self._grund = grund\n",
            balken="from basis import Pille\n\nclass Balken(Pille):\n    def _grund(self, b, h):\n        return b\n")
        self.assertEqual(1, len(funde), funde)
        self.assertIn("Balken: self._grund = ... (Pille, Zeile 3)", funde[0], "das Attribut kommt aus der Basis")
        self.assertIn("Methode Balken._grund", funde[0], "die Methode aus der Unterklasse")

    def test_dieselbe_klasse_methode_und_attribut(self) -> None:
        funde = self._suchen(a="class A:\n    def __init__(self):\n        self.lauf = None\n    def lauf(self):\n        pass\n")
        self.assertEqual(1, len(funde), funde)

    def test_erweiterte_zuweisung_und_typangabe_zaehlen_auch(self) -> None:
        funde = self._suchen(
            a="class A:\n    def zaehler(self):\n        pass\n    def f(self):\n        self.zaehler += 1\n",
            b="class B:\n    def name(self):\n        pass\n    def __init__(self):\n        self.name: str = 'x'\n")
        self.assertEqual(2, len(funde), funde)

    def test_eine_eigenschaft_mit_setter_ist_erlaubt(self) -> None:
        funde = self._suchen(a=(
            "class A:\n    def __init__(self):\n        self.wert = 1\n"
            "    @property\n    def wert(self):\n        return self._w\n"
            "    @wert.setter\n    def wert(self, v):\n        self._w = v\n"))
        self.assertEqual([], funde)

    def test_verschiedene_namen_und_fremde_basis_sind_kein_fund(self) -> None:
        funde = self._suchen(a=(
            "import tkinter as tk\n\nclass A:\n    def __init__(self):\n        self._farbe = 'rot'\n"
            "    def _zeichnen(self):\n        pass\n\nclass B(A, tk.Canvas):\n    def _bild(self):\n        self._cache = 1\n"))
        self.assertEqual([], funde)

    def test_ueber_zwei_basisstufen_wird_die_methode_gefunden(self) -> None:
        funde = self._suchen(a=(
            "class A:\n    def zeichne(self):\n        pass\n\nclass B(A):\n    pass\n\n"
            "class C(B):\n    def __init__(self):\n        self.zeichne = 'x'\n"))
        self.assertEqual(1, len(funde), funde)
        self.assertIn("C: self.zeichne = ... (C, Zeile", funde[0])
        self.assertIn("Methode A.zeichne", funde[0])


class ProjektTests(unittest.TestCase):
    def test_im_projekt_ueberdeckt_kein_attribut_eine_methode(self) -> None:
        dateien = [HAUPTDATEI] + sorted((PROJEKT / "ps5_validator").rglob("*.py"))
        funde = ueberdeckungen(dateien)
        self.assertEqual([], funde, "Ein Attribut, das eine Methode ueberdeckt, macht jeden Aufruf zum TypeError (Fall 17.11.2026):\n"
                         + "\n".join(funde))

    def test_die_suche_sieht_das_hauptmodul_und_die_oberflaeche(self) -> None:
        """Gegenprobe gegen eine leere Suche: Es gibt Klassen in beiden Teilen."""
        klassen = _klassen_lesen([HAUPTDATEI] + sorted((PROJEKT / "ps5_validator").rglob("*.py")))
        self.assertGreater(len(klassen), 200)
        self.assertIn("PS5ConverterGUI", klassen)
        self.assertIn("FortschrittsPille", klassen)


if __name__ == "__main__":
    unittest.main()
