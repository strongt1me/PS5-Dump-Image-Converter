# -*- coding: utf-8 -*-
"""Waechter: keine Oberflaeche aus einem Arbeitsfaden.

Tk ist an seinen Faden gebunden. Ein ``messagebox.askyesno`` aus einem
Arbeitsfaden wartet auf eine Antwort, die nur die Ereignisschleife geben
kann - und die wartet auf den Faden: das Fenster steht. Eine Tk-Variable
aus dem Faden zu lesen bringt den Interpreter im schlimmsten Fall ganz
zum Absturz, im besten liefert sie einen veralteten Wert. Beides ist in
diesem Projekt schon vorgekommen.

Der richtige Weg ist ``self.root.after(0, ...)``: Die verschachtelte
Funktion, die dort uebergeben wird, laeuft im Hauptfaden. Deshalb prueft
dieser Waechter nur den *eigenen* Rumpf einer Faden-Funktion und laesst
alles aus, was in ihr erst wieder als Funktion definiert wird.

Das Ziel eines Fadens wird lexikalisch aufgeloest, nicht ueber den Namen:
Im Hauptmodul gibt es drei verschachtelte ``_senden``, von denen nur eines
in einem Faden laeuft. Ein Namensvergleich meldete zwei Fehlbefunde.
"""
import ast
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

FUNKTION = (ast.FunctionDef, ast.AsyncFunctionDef)

#: Module, deren Aufrufe ein Fenster oeffnen und auf Antwort warten.
DIALOGMODULE = ("messagebox", "filedialog", "simpledialog")

#: Fadenziele, die keine Funktion dieses Moduls sind - und warum.
FREMDE_ZIELE = {
    "serve_forever": "Methode des mitgelieferten HTTP-Servers (http.server)",
}


class _Baum:
    """Der Syntaxbaum des Hauptmoduls samt Elternkette."""

    def __init__(self, quelle: str) -> None:
        self.wurzel = ast.parse(quelle)
        self.eltern: dict[int, ast.AST] = {}
        for knoten in ast.walk(self.wurzel):
            for kind in ast.iter_child_nodes(knoten):
                self.eltern[id(kind)] = knoten

    def umgebungen(self, knoten: ast.AST):
        """Von innen nach aussen alles, was diesen Knoten umgibt."""
        aktuell = self.eltern.get(id(knoten))
        while aktuell is not None:
            yield aktuell
            aktuell = self.eltern.get(id(aktuell))

    def defs_in(self, knoten: ast.AST) -> dict:
        """Funktionen, die in diesem Rumpf definiert werden.

        Auch die in einem ``if``/``try``/``with``/``for`` darin - sie
        gehoeren zum selben Namensraum.
        """
        gefunden: dict[str, ast.AST] = {}
        for innen in ast.walk(knoten):
            if not isinstance(innen, FUNKTION) or innen is knoten:
                continue
            eltern = self.eltern.get(id(innen))
            if eltern is knoten or isinstance(eltern, (ast.If, ast.Try, ast.With,
                                                       ast.For, ast.While)):
                gefunden.setdefault(innen.name, innen)
        return gefunden

    def ziel_aufloesen(self, aufruf: ast.Call, name: str):
        """Die Funktion, die dieser ``Thread(target=...)`` wirklich startet."""
        for umgebung in self.umgebungen(aufruf):
            if isinstance(umgebung, (*FUNKTION, ast.ClassDef, ast.Module)):
                treffer = self.defs_in(umgebung).get(name)
                if treffer is not None:
                    return treffer
        return None


def _zielname(aufruf: ast.Call) -> str:
    for kw in aufruf.keywords:
        if kw.arg == "target":
            return getattr(kw.value, "id", "") or getattr(kw.value, "attr", "")
    if aufruf.args:
        return getattr(aufruf.args[0], "id", "") or getattr(aufruf.args[0], "attr", "")
    return ""


def _eigener_rumpf(funktion):
    """Alles im Rumpf - ausser den Funktionen, die darin entstehen.

    Die laufen ueber ``after`` im Hauptfaden und duerfen alles.
    """
    stapel = list(funktion.body)
    while stapel:
        knoten = stapel.pop()
        if isinstance(knoten, (*FUNKTION, ast.Lambda)):
            continue
        yield knoten
        stapel.extend(ast.iter_child_nodes(knoten))


class FadenhygieneTests(unittest.TestCase):
    """Was in einem Arbeitsfaden laeuft, ruehrt die Oberflaeche nicht an."""

    @classmethod
    def setUpClass(cls):
        cls.baum = _Baum(HAUPTDATEI.read_text(encoding="utf-8"))
        cls.faeden = []      # (Zeile des Starts, Name, Zielfunktion)
        cls.offen = []       # nicht aufgeloeste Ziele
        for knoten in ast.walk(cls.baum.wurzel):
            if not isinstance(knoten, ast.Call):
                continue
            if (getattr(knoten.func, "attr", "")
                    or getattr(knoten.func, "id", "")) != "Thread":
                continue
            name = _zielname(knoten)
            if not name:
                continue
            ziel = cls.baum.ziel_aufloesen(knoten, name)
            if ziel is None:
                cls.offen.append((knoten.lineno, name))
            else:
                cls.faeden.append((knoten.lineno, name, ziel))

    def test_keine_dialoge_aus_einem_arbeitsfaden(self):
        gefunden = []
        for zeile, name, ziel in self.faeden:
            for innen in _eigener_rumpf(ziel):
                if (isinstance(innen, ast.Call)
                        and isinstance(innen.func, ast.Attribute)
                        and isinstance(innen.func.value, ast.Name)
                        and innen.func.value.id in DIALOGMODULE):
                    gefunden.append(
                        "Faden ab Zeile %d (%s) ruft %s.%s in Zeile %d"
                        % (zeile, name, innen.func.value.id, innen.func.attr,
                           innen.lineno))
        self.assertEqual([], gefunden,
                         "Dialog aus dem Arbeitsfaden - das Fenster steht: "
                         + " | ".join(gefunden))

    def test_keine_tk_variablen_aus_einem_arbeitsfaden(self):
        gefunden = []
        for zeile, name, ziel in self.faeden:
            for innen in _eigener_rumpf(ziel):
                if (not isinstance(innen, ast.Call)
                        or not isinstance(innen.func, ast.Attribute)
                        or innen.func.attr not in ("get", "set")):
                    continue
                wurzel = innen.func.value
                benannt = getattr(wurzel, "id", "") or getattr(wurzel, "attr", "")
                if benannt.endswith("_var"):
                    gefunden.append("Faden ab Zeile %d (%s) fasst %s.%s() an, Zeile %d"
                                    % (zeile, name, benannt, innen.func.attr,
                                       innen.lineno))
        self.assertEqual([], gefunden,
                         "Tk-Variable aus dem Arbeitsfaden: " + " | ".join(gefunden))

    def test_die_pruefung_sieht_die_faeden(self):
        """Sonst waere jedes Gruen oben ein Messfehler."""
        self.assertGreater(len(self.faeden), 50,
                           "kaum Faden-Starts gefunden: %d" % len(self.faeden))
        mit_rumpf = [z for z in self.faeden if list(_eigener_rumpf(z[2]))]
        self.assertEqual(len(mit_rumpf), len(self.faeden),
                         "eine Zielfunktion kam ohne Rumpf zurueck")

    def test_jedes_fadenziel_ist_bekannt(self):
        """Ein unbekanntes Ziel wird nicht geprueft - das muss auffallen."""
        unerwartet = ["Zeile %d: %s" % (zeile, name) for zeile, name in self.offen
                      if name not in FREMDE_ZIELE]
        self.assertEqual([], unerwartet,
                         "Fadenziel nicht aufloesbar, also ungeprueft: "
                         + " | ".join(unerwartet))


if __name__ == "__main__":
    unittest.main(verbosity=2)
