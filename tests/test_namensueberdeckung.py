# -*- coding: utf-8 -*-
"""Ein Instanzattribut darf keine Methode ueberdecken (Fehlerklasse aus dem Protokoll vom 17.11.2026).

Am 17.11.2026 um 23:10 stand im Protokoll zweimal ``TypeError: 'str' object is not callable`` aus dem Balken der
Knopfleiste: Die Unterklasse (``leisten_balken``) hatte eine Methode ``_grund``, die Basisklasse
(``ps4_ota_bausteine``) setzte im Konstruktor ``self._grund = <Farbname>``. Der Aufruf ``self._grund(b, h)`` traf den Text,
und jedes ``<Configure>``-Ereignis warf den Fehler erneut. Der Fehler lag nur in einem Zwischenstand (die Methode heisst seit
dem Commit 7eb5741 ``_ausschnitt``), aber nichts haette ihn bemerkt, solange das Fenster nicht gezeichnet wird.

Gesucht wird ueber den Syntaxbaum: Jede Klasse des Projekts, in der ``self.X = ...`` (auch ``+=`` und Typangabe) einen Namen
belegt, den dieselbe Klasse oder eine Basisklasse des Projekts als **Methode** definiert. Eigenschaften (``@property`` mit
``setter``, ``cached_property``) zaehlen nicht - dort ist die Zuweisung gewollt. Eine Eigenschaft **ohne** ``setter`` zaehlt
dagegen: ``self.X = ...`` wirft dort ``AttributeError``. Basisklassen aus fremden Paketen (``tk.Canvas``) kennt die Suche nicht;
``Basis[str]`` (Generics) wird wie ``Basis`` gelesen.

Massgebend ist die **naechste** Definition des Namens in der Reihenfolge Klasse, Basen: Eine Unterklasse, die eine Eigenschaft der
Basis mit Setter neu definiert oder sie durch ein Klassenattribut ersetzt, entschaerft die Zuweisung; eine Unterklasse, die eine
Eigenschaft ohne Setter definiert, wo die Basis ``self.X = ...`` setzt, ist ein Fund (Gegenlese 19.11.2026).

Grenzen (nicht gesucht): ``setattr(self, "x", ...)``, ``for self.x in ...``, ein anderer Name als ``self``, eine Klasse, die in
mehreren Modulen denselben Namen traegt (die Suche verschmilzt sie; ``ERLAUBT`` faengt einen daraus entstehenden Fehlalarm ab -
Basen aus der Standardbibliothek wie ``tk.Text`` fallen allerdings heraus), Basen, die ein Aufruf liefert.
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


def _dekorator(f: "ast.FunctionDef | ast.AsyncFunctionDef") -> str:
    """``eigenschaft`` / ``setter`` / ``cached`` / ``""`` - was der Dekorator einer Methode aus ihr macht."""
    for d in f.decorator_list:
        text = ast.unparse(d)
        if text == "property":
            return "eigenschaft"
        if text in ("cached_property", "functools.cached_property"):
            return "cached"
        if text.endswith((".setter", ".deleter")):
            return "setter"
        if text.endswith(".getter"):
            return "eigenschaft"
    return ""


def _wurzelname(b: ast.expr) -> "str | None":
    """Der linke Name eines Ausdrucks: ``tk`` in ``tk.Canvas``, ``Wert`` in ``Wert[str]``."""
    while isinstance(b, (ast.Attribute, ast.Subscript)):
        b = b.value
    return b.id if isinstance(b, ast.Name) else None


def _basenname(b: ast.expr, fremd: "set[str] | None" = None) -> "str | None":
    """Der einfache Name einer Basisklasse: ``Name``, ``modul.Name`` und ``Name[...]``.

    ``fremd``: Namen, die diese Datei aus der Standardbibliothek eingefuehrt hat (``tk`` fuer ``import tkinter as tk``): Eine Basis
    daraus (``tk.Text``) ist keine Klasse des Projekts, auch wenn dort eine Klasse ``Text`` heisst."""
    if fremd and _wurzelname(b) in fremd:
        return None
    if isinstance(b, ast.Subscript):
        return _basenname(b.value, fremd)
    if isinstance(b, ast.Name):
        return b.id
    if isinstance(b, ast.Attribute):
        return b.attr
    return None


def _fremde_namen(baum: ast.AST) -> "set[str]":
    """Namen, die eine Datei per ``import`` oder ``from ... import`` aus der Standardbibliothek bindet."""
    namen: "set[str]" = set()
    for k in ast.walk(baum):
        if isinstance(k, ast.Import):
            for a in k.names:
                if a.name.split(".")[0] in sys.stdlib_module_names:
                    namen.add(a.asname or a.name.split(".")[0])
        elif isinstance(k, ast.ImportFrom) and k.level == 0 and k.module and k.module.split(".")[0] in sys.stdlib_module_names:
            namen.update(a.asname or a.name for a in k.names)
    return namen


def _stellen(koerper: "list[ast.stmt]"):
    """Die Anweisungen eines Klassenkoerpers - auch die unter ``if``, ``try``, ``with`` und Schleifen, nicht die in Funktionen/Klassen."""
    for s in koerper:
        yield s
        if isinstance(s, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try)):
            teile = [s.body, getattr(s, "orelse", []), getattr(s, "finalbody", [])]
            teile += [h.body for h in getattr(s, "handlers", [])]
            for teil in teile:
                yield from _stellen(teil)


def _ohne_klassen(knoten: ast.AST):
    """Alle Knoten unter ``knoten``, ohne in eine verschachtelte Klasse zu steigen: Deren ``self`` ist ein anderes."""
    for kind in ast.iter_child_nodes(knoten):
        if isinstance(kind, ast.ClassDef):
            continue
        yield kind
        yield from _ohne_klassen(kind)


def _klassen_lesen(dateien: "list[Path]") -> "dict[str, list[tuple]]":
    """Name -> [(Datei, Basen, Methoden {Name: Zeile}, Attribute {Name: Zeile}, Zeile, Eigenschaften ohne Setter, Eigenschaften
    mit Setter und Klassenattribute)] je Klasse."""
    klassen: "dict[str, list[tuple]]" = {}
    for datei in dateien:
        baum = ast.parse(datei.read_text(encoding="utf-8-sig"))
        fremd = _fremde_namen(baum)
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.ClassDef):
                continue
            basen = [n for n in (_basenname(b, fremd) for b in knoten.bases) if n]
            methoden: dict = {}
            eigenschaften: set = set()
            setter: set = set()
            werte: set = set()                       # Klassenattribute und zwischengespeicherte Eigenschaften
            for stelle in _stellen(knoten.body):
                if isinstance(stelle, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    art = _dekorator(stelle)
                    if art == "eigenschaft":
                        eigenschaften.add(stelle.name)
                    elif art == "setter":
                        setter.add(stelle.name)
                    elif art == "cached":
                        werte.add(stelle.name)
                    else:
                        methoden[stelle.name] = stelle.lineno
                elif isinstance(stelle, ast.Assign):
                    werte.update(t.id for t in stelle.targets if isinstance(t, ast.Name))
                elif isinstance(stelle, ast.AnnAssign) and isinstance(stelle.target, ast.Name):
                    werte.add(stelle.target.id)
            attribute: dict = {}
            for f in _ohne_klassen(knoten):
                if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for a in _ohne_klassen(f):
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
            klassen.setdefault(knoten.name, []).append(
                (datei, basen, methoden, attribute, knoten.lineno, eigenschaften - setter, setter | werte))
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


def _wirksam(attr: str, eigene: tuple, basen: "list[str]", klassen: dict) -> "tuple[str, str] | None":
    """Wie ``attr`` fuer eine Instanz der Klasse gilt: ``("methode" | "ohne_setter" | "wert", Klasse)`` nach der naechsten Definition.

    ``eigene`` = (Name, Methoden, Eigenschaften ohne Setter, Eigenschaften mit Setter und Klassenattribute) der Klasse selbst, danach die
    Basen in ihrer Reihenfolge; ``None``, wenn kein Klassenteil den Namen definiert."""
    def pruefen(klasse: str, methoden: dict, nur_lesbar: set, werte: set) -> "tuple[str, str] | None":
        if attr in methoden:
            return "methode", klasse
        if attr in nur_lesbar:
            return "ohne_setter", klasse
        if attr in werte:
            return "wert", klasse
        return None
    treffer = pruefen(*eigene)
    if treffer:
        return treffer
    for b in basen:
        for e in klassen.get(b, []):
            treffer = pruefen(b, e[2], e[5], e[6])
            if treffer:
                return treffer
    return None


def ueberdeckungen(dateien: "list[Path]") -> "list[str]":
    """Eine Zeile je Fund: ``Datei:Zeile Klasse.Name ...``."""
    klassen = _klassen_lesen(dateien)
    funde: "list[str]" = []
    for name, eintraege in klassen.items():
        for datei, basen, methoden, attribute, zeile, nur_lesbar, werte in eintraege:
            alle: "list[str]" = []
            gesehen: set = set()
            for b in basen:
                if b not in gesehen:
                    gesehen.add(b)
                    alle.append(b)
                    alle.extend(_basen(b, klassen, gesehen))
            # Eine Instanz der Klasse traegt die Attribute der Klasse UND ihrer Basen: der Fall vom 17.11. entstand, weil die Basis das
            # Attribut setzte und erst die Unterklasse die Methode gleichen Namens hatte. Ob die Zuweisung scheitert, entscheidet die
            # naechste Definition des Namens (Klasse zuerst, dann die Basen).
            attribute_alle = {a: (name, z) for a, z in attribute.items()}
            for b in alle:
                for e in klassen.get(b, []):
                    for a, z in e[3].items():
                        attribute_alle.setdefault(a, (b, z))
            for attr in sorted(attribute_alle):
                wirkung = _wirksam(attr, (name, methoden, nur_lesbar, werte), alle, klassen)
                if wirkung is None or wirkung[0] == "wert" or "%s.%s" % (name, attr) in ERLAUBT:
                    continue
                art, definiert_in = wirkung
                aklasse, azeile = attribute_alle[attr]
                if art == "methode":
                    funde.append("%s:%d  %s: self.%s = ... (%s, Zeile %d) ueberdeckt die Methode %s.%s"
                                 % (datei.name, zeile, name, attr, aklasse, azeile, definiert_in, attr))
                else:
                    funde.append("%s:%d  %s: self.%s = ... (%s, Zeile %d) - %s.%s ist eine Eigenschaft ohne Setter (AttributeError)"
                                 % (datei.name, zeile, name, attr, aklasse, azeile, definiert_in, attr))
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

    def test_eine_eigenschaft_ohne_setter_wirft_beim_zuweisen_und_wird_gefunden(self) -> None:
        funde = self._suchen(
            a="class A:\n    @property\n    def wert(self):\n        return 1\n\nclass B(A):\n    def __init__(self):\n        self.wert = 2\n")
        self.assertEqual(1, len(funde), funde)
        self.assertIn("A.wert ist eine Eigenschaft ohne Setter", funde[0])

    def test_eine_zwischengespeicherte_eigenschaft_darf_zugewiesen_werden(self) -> None:
        funde = self._suchen(a=(
            "from functools import cached_property\n\nclass A:\n    @cached_property\n    def wert(self):\n        return 1\n"
            "    def setze(self):\n        self.wert = 2\n"))
        self.assertEqual([], funde)

    def test_basis_mit_typargument_wird_wie_die_basis_gelesen(self) -> None:
        """``class Text(Wert[str])`` (ui/zustand.py) - ohne das fiele die Basis aus der Suche."""
        funde = self._suchen(
            a="class Wert:\n    def __init__(self):\n        self.lesen = 'x'\n",
            b="from a import Wert\n\nclass Text(Wert[str]):\n    def lesen(self):\n        return 1\n")
        self.assertEqual(1, len(funde), funde)
        self.assertIn("Text: self.lesen = ... (Wert, Zeile 3)", funde[0])

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


    # ---- Gegenlese 19.11.2026: falscher Alarm und durchgelassene Faelle, mit konstruierten Quelltexten belegt ----
    def test_eine_verschachtelte_klasse_hat_ihr_eigenes_self(self) -> None:
        funde = self._suchen(a=(
            "class Aussen:\n    def foo(self):\n        pass\n\n"
            "    class Innen:\n        def __init__(self):\n            self.foo = 1\n"))
        self.assertEqual([], funde, "``self.foo`` gehoert zu Innen, nicht zu Aussen")

    def test_die_verschachtelte_klasse_wird_fuer_sich_geprueft(self) -> None:
        funde = self._suchen(a=(
            "class Aussen:\n    class Innen:\n        def foo(self):\n            pass\n\n"
            "        def __init__(self):\n            self.foo = 1\n"))
        self.assertEqual(1, len(funde), funde)
        self.assertIn("Innen: self.foo", funde[0])

    def test_die_basis_setzt_das_attribut_die_unterklasse_hat_eine_eigenschaft_ohne_setter(self) -> None:
        funde = self._suchen(a=(
            "class A:\n    def __init__(self):\n        self.wert = 1\n\n"
            "class B(A):\n    @property\n    def wert(self):\n        return 2\n"))
        self.assertEqual(1, len(funde), funde)
        self.assertIn("B.wert ist eine Eigenschaft ohne Setter", funde[0])
        self.assertIn("(A, Zeile 3)", funde[0], "die Zuweisung steht in der Basis")

    def test_eine_unterklasse_die_die_eigenschaft_mit_setter_neu_definiert_ist_in_ordnung(self) -> None:
        funde = self._suchen(a=(
            "class A:\n    @property\n    def x(self):\n        return 1\n\n"
            "class B(A):\n    def __init__(self):\n        self.x = 2\n\n"
            "    @property\n    def x(self):\n        return self._x\n\n"
            "    @x.setter\n    def x(self, v):\n        self._x = v\n"))
        self.assertEqual([], funde)

    def test_ein_klassenattribut_ersetzt_die_eigenschaft_der_basis(self) -> None:
        funde = self._suchen(a=(
            "class A:\n    @property\n    def x(self):\n        return 1\n\n"
            "class B(A):\n    x = None\n\n    def f(self):\n        self.x = 2\n"))
        self.assertEqual([], funde)

    def test_eine_basis_aus_der_standardbibliothek_wird_nicht_mit_einer_klasse_gleichen_namens_verschmolzen(self) -> None:
        """``fenster_pillen.Text(tk.Text)`` und ``zustand.Text(Wert[str])`` heissen gleich: ``tk.Text`` ist keine Klasse des Projekts."""
        funde = self._suchen(
            zustand="class Text:\n    def lesen(self):\n        return 1\n",
            pillen="import tkinter as tk\n\nclass Text(tk.Text):\n    def __init__(self):\n        self.lesen = 2\n")
        self.assertEqual([], funde)
        funde = self._suchen(
            zustand="class Text:\n    def lesen(self):\n        return 1\n",
            pillen="from zustand import Text\n\nclass Feld(Text):\n    def __init__(self):\n        self.lesen = 2\n")
        self.assertEqual(1, len(funde), "Gegenprobe: dieselbe Basis aus dem Projekt wird gefunden")

    def test_methoden_unter_einer_bedingung_im_klassenkoerper_zaehlen(self) -> None:
        funde = self._suchen(a=(
            "class A:\n    if True:\n        def foo(self):\n            pass\n\n    def f(self):\n        self.foo = 1\n"))
        self.assertEqual(1, len(funde), funde)


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
        # Klassen mit Typargument in der Basis (ui/zustand.py: ``class Text(Wert[str])``): Es gibt mehrere Klassen namens "Text"
        # (auch ``fenster_pillen`` hat eine) - die aus zustand.py muss mit der Basis "Wert" gelesen worden sein.
        zustand = [e for e in klassen["Text"] if e[0].name == "zustand.py"]
        self.assertTrue(zustand and zustand[0][1] == ["Wert"], zustand)


if __name__ == "__main__":
    unittest.main()
