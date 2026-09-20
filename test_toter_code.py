# -*- coding: utf-8 -*-
"""Waechter gegen toten Code - und gegen das, was beim Entfernen schiefgeht.

Zwei Pruefungen wohnen hier, weil sie dieselbe Dateiliste brauchen: Was
niemand ruft (unten), und ein Dekorator, dessen Funktion entfernt wurde
(``DekoratorTests``).

## Funktionen, die im Programm niemand ruft

Warum eigens dafuer ein Test: Beim Debuglauf am 20.09.2026 lagen fuenf
solche Reste im Programm - eine Vorschau-Sammlung samt Auffrischer aus den
ausgebauten Bildeffekten, eine dritte Kopie der Bibliothekssuche, die
verworfene Fassung von ``_ist_hochformat``, ein Helfer fuer das
Autoloader-Bild und eine Zusammenfassung fuer den KLOG-Knopf, die dieser
seit dem 05.09.2026 nicht mehr nimmt. Toter Code ist nicht nur Ballast:
Er behauptet, zum Programm zu gehoeren. Wer ihn liest, haelt eine
verworfene Regel fuer die geltende.

Gezaehlt wird ueber den Syntaxbaum: jeder Name, jedes Attribut, jeder
Import - und zusaetzlich die Woerter in Zeichenketten, denn das Programm
verteilt Befehle auch als Namen (``_MORE_TOOLS_ENTRIES``, Fadennamen,
getattr), und die Testreihe sucht manche Stelle als Zeichenkette im
Quelltext. Ein Name, der nur an seiner eigenen Definition steht, wird von
nirgends gebraucht.

Nicht gezaehlt werden Kommentare und Docstrings. Das ist keine Feinheit,
sondern der Unterschied zwischen Messung und Selbstbestaetigung: Die
Gegenprobe zu diesem Waechter setzte das entfernte ``_bring_to_front``
wieder ein - und blieb gruen, weil an seiner alten Stelle ein Kommentar
den Namen nennt ("Hier stand ..."). Erklaerender Text haelt keinen Code
lebendig.

Bewusst gezaehlt werden auch die Tests: Sonst meldet die Pruefung 28
Funktionen, die das Programm nicht braucht, die Testreihe aber sehr wohl
prueft - geprueftes Beiwerk ist kein toter Code. Was dagegen niemand
nennt, ist eins.
"""
import ast
import re
import subprocess
import unittest
from collections import Counter
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent

#: Fremdbestand: liegt unveraendert bei und wird hier nicht beurteilt.
FREMD_ANFANG = (
    "PS5-Wee-Tools-", "AMPR_PackTools-", "MkPFS-", "ProsperoPkg-",
    "PS4FFPFSC-", "UFS2Tool-", "PS5-AppInstall/", "PS5 WebKit Autoloader/",
    "PlayGo & AMPR_EMU/", "PS5 SDK usw/", "helloworld/", "backport-helper",
)

#: Aus conftest.py kommen keine Definitionen: Fixtures ruft pytest ueber
#: die Anmeldung, nie beim Namen. Ihre Woerter zaehlen trotzdem mit.
OHNE_DEFINITIONEN = {"conftest.py"}

#: Erlaubte Ausnahmen, jede mit Grund - und derzeit keine.
#:
#: Am 20.09.2026 standen hier fuenf Funktionen des neutralen
#: Bedienzustands: API fuer eine zweite Oberflaeche, von der Tk-Fassung
#: nicht gebraucht. Sie sind jetzt in test_bedienzustand.py geprueft und
#: damit genannt - eine ungepruefte Zusage war der schlechtere Zustand.
#:
#: Wer hier etwas eintraegt, begruendet es. ``test_jede_ausnahme_ist_noch
#: _eine`` besteht darauf, dass der Grund noch gilt.
ERLAUBT: dict[tuple[str, str], str] = {}

WORT = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")


def _dateien() -> list[str]:
    """Alles, was zum Projekt gehoert - auch noch nicht Eingetragenes.

    Nicht nur der Git-Index: Eine gerade geschriebene Testdatei steht dort
    noch nicht, und ihre Aufrufe wuerden fehlen - die Pruefung erklaerte
    frisch geprueften Code fuer tot. Umgekehrt wird auch ein noch nicht
    eingetragenes Modul schon geprueft, also ab der ersten Minute.
    ``--exclude-standard`` haelt Ignoriertes heraus (Baukram, Sicherungen,
    .claude, tools/).
    """
    gefunden: list[str] = []
    for zusatz in (["--cached"], ["--others", "--exclude-standard"]):
        lauf = subprocess.run(["git", "ls-files", *zusatz, "*.py", "*.spec"],
                              cwd=PROJEKT, capture_output=True, text=True,
                              encoding="utf-8", check=True)
        gefunden.extend(lauf.stdout.splitlines())
    # Eine Datei kann in beiden Listen stehen; doppelt zaehlen wuerde jeden
    # Namen doppelt zaehlen und damit tote Funktionen verdecken.
    return sorted(set(gefunden))


def _dokustellen(baum: ast.AST) -> set[int]:
    """Die Docstrings des Baums, an ihrer Stelle im Speicher erkannt.

    Sie werden nicht mitgezaehlt: Ein Docstring, der einen Namen erwaehnt,
    ruft ihn nicht. Alle anderen Zeichenketten zaehlen mit - in ihnen
    stehen die Befehlsnamen, die das Programm herumgibt.
    """
    stellen: set[int] = set()
    for knoten in ast.walk(baum):
        koerper = getattr(knoten, "body", None)
        if not isinstance(knoten, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                   ast.AsyncFunctionDef)) or not koerper:
            continue
        erstes = koerper[0]
        if (isinstance(erstes, ast.Expr) and isinstance(erstes.value, ast.Constant)
                and isinstance(erstes.value.value, str)):
            stellen.add(id(erstes.value))
    return stellen


def _ist_eigen(rel: str) -> bool:
    """Gehoert die Datei uns? Fremdbestand wird nicht beurteilt."""
    return not rel.startswith(FREMD_ANFANG)


def _bringt_definitionen(rel: str) -> bool:
    """Werden aus dieser Datei Funktionen erwartet, die jemand ruft?

    Testdateien nicht: Ihre ``test_``-Methoden ruft pytest, und ihre
    Helfer nennt niemand ausserhalb. Geprueft wird das Programm.
    """
    name = rel.rsplit("/", 1)[-1]
    return (rel.endswith(".py") and not name.startswith("test_")
            and rel not in OHNE_DEFINITIONEN)


class ToterCodeTests(unittest.TestCase):
    """Jede Funktion des Programms muss von irgendwo gerufen werden."""

    @classmethod
    def setUpClass(cls):
        cls.dateien = [rel for rel in _dateien()
                       if _ist_eigen(rel) and (PROJEKT / rel).is_file()]
        cls.programmdateien = [rel for rel in cls.dateien if _bringt_definitionen(rel)]
        cls.woerter: Counter = Counter()
        cls.definitionen: Counter = Counter()
        cls.ort: dict = {}
        for rel in cls.dateien:
            text = (PROJEKT / rel).read_text(encoding="utf-8", errors="replace")
            baum = ast.parse(text)
            doku = _dokustellen(baum)
            mit_definitionen = _bringt_definitionen(rel)
            for knoten in ast.walk(baum):
                if isinstance(knoten, ast.Name):
                    cls.woerter[knoten.id] += 1
                elif isinstance(knoten, ast.Attribute):
                    cls.woerter[knoten.attr] += 1
                elif isinstance(knoten, ast.keyword) and knoten.arg:
                    cls.woerter[knoten.arg] += 1
                elif isinstance(knoten, ast.alias):
                    # ``from modul import name as anders`` nennt beide.
                    cls.woerter[knoten.name.rsplit(".", 1)[-1]] += 1
                    if knoten.asname:
                        cls.woerter[knoten.asname] += 1
                elif isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
                    if id(knoten) not in doku:
                        cls.woerter.update(WORT.findall(knoten.value))
                elif isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)):
                    cls.woerter[knoten.name] += 1
                    if (mit_definitionen and not isinstance(knoten, ast.ClassDef)
                            and not knoten.name.startswith("__")
                            and knoten.name != "main"):
                        cls.definitionen[knoten.name] += 1
                        cls.ort.setdefault(knoten.name,
                                           "%s:%d" % (rel, knoten.lineno))
            del text, baum, doku

    def test_die_pruefung_sieht_das_programm(self):
        """Ohne diese Schranke koennte alles Gruen ein Messfehler sein."""
        self.assertGreaterEqual(len(self.programmdateien), 40,
                                "zu wenige Programmdateien: %s" % self.programmdateien)
        self.assertIn("PS5ImageConverter_Pro_FINAL_revised.py", self.programmdateien)
        self.assertGreaterEqual(len(self.definitionen), 1000,
                                "der Syntaxbaum lieferte kaum Funktionen")
        # Die Testdateien muessen mitgezaehlt werden, sonst gilt geprueftes
        # Beiwerk als tot.
        self.assertGreater(len(self.dateien), len(self.programmdateien),
                           "die Testdateien fehlen in der Zaehlung")

    def test_keine_funktion_ruft_niemand(self):
        tot = []
        for name, anzahl in sorted(self.definitionen.items()):
            # Jede Definition nennt den Namen genau einmal. Steht er sonst
            # nirgends, gibt es keinen Aufrufer - auch keinen ueber getattr,
            # eine Befehlstabelle oder eine Pruefung.
            if self.woerter[name] > anzahl:
                continue
            ort = self.ort[name]
            schluessel = (ort.rsplit(":", 1)[0], name)
            if schluessel in ERLAUBT:
                continue
            tot.append("%s (%s)" % (name, ort))
        self.assertEqual([], tot,
                         "im Programm ruft niemand: " + ", ".join(tot))

    def test_jede_ausnahme_ist_noch_eine(self):
        """Wird eine Ausnahme doch gerufen, gehoert der Eintrag geloescht."""
        ueberholt = []
        for (rel, name), grund in sorted(ERLAUBT.items()):
            if name not in self.definitionen:
                ueberholt.append("%s/%s gibt es nicht mehr" % (rel, name))
            elif self.woerter[name] > self.definitionen[name]:
                ueberholt.append("%s/%s wird gerufen (%s)" % (rel, name, grund))
        self.assertEqual([], ueberholt, "; ".join(ueberholt))


class DekoratorTests(unittest.TestCase):
    """Kein Dekorator, der die falsche Funktion trifft.

    Wird eine Funktion entfernt und ihr ``@staticmethod`` bleibt stehen, ist
    das gueltiges Python: Der Dekorator wandert lautlos auf die naechste
    Funktion. Am 20.09.2026 wurde so aus ``_apply_card_tint_live`` eine
    statische Methode - drei Pruefungen fielen mit "missing 1 required
    positional argument: 'self'", und die Ursache stand 4000 Zeilen weiter
    oben. Ruff sieht das nicht, der Syntaxbaum schon.

    Die Regel ist streng und dafuer eindeutig: Zwischen dem letzten
    Dekorator und dem ``def`` steht nichts - keine Leerzeile, kein
    Kommentar. Wer dort etwas erklaeren will, schreibt es ueber den
    Dekorator.
    """

    @classmethod
    def setUpClass(cls):
        cls.dateien = [rel for rel in _dateien()
                       if _ist_eigen(rel) and rel.endswith(".py")
                       and (PROJEKT / rel).is_file()]

    def _dekorierte(self):
        for rel in self.dateien:
            text = (PROJEKT / rel).read_text(encoding="utf-8", errors="replace")
            zeilen = text.splitlines()
            for knoten in ast.walk(ast.parse(text)):
                if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                                           ast.ClassDef)) or not knoten.decorator_list:
                    continue
                letzter = max(d.end_lineno or d.lineno for d in knoten.decorator_list)
                yield rel, knoten, zeilen[letzter:knoten.lineno - 1]

    def test_zwischen_dekorator_und_def_steht_nichts(self):
        verdacht = ["%s:%d %s - dazwischen: %r"
                    % (rel, knoten.lineno, knoten.name, [z.strip() for z in zwischen][:3])
                    for rel, knoten, zwischen in self._dekorierte() if zwischen]
        self.assertEqual([], verdacht,
                         "Der Dekorator gehoert zur naechsten Definition - "
                         "sicher, dass er die meint? " + " | ".join(verdacht))

    def test_die_pruefung_sieht_die_dekoratoren(self):
        anzahl = sum(1 for _r, _k, _z in self._dekorierte())
        self.assertGreater(anzahl, 400,
                           "kaum dekorierte Definitionen gefunden: %d" % anzahl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
