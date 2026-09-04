"""Verzoegerte Rueckrufe duerfen die Ausnahmevariable nicht einfangen.

Python loescht den Namen aus ``except ... as exc`` beim Verlassen des Blocks
(implizites ``del``). Ein Lambda, das ihn liest, wird hier ueber
``root.after(0, ...)`` oder ``win.after(0, ...)`` erst spaeter in der
Tk-Schleife ausgefuehrt - dann ist der Name weg und der Rueckruf stirbt an
einem ``NameError``.

Das traf vier Fehlerpfade, in denen genau die Fehlermeldung gesetzt werden
sollte: Backport fehlgeschlagen sowie Laden, Schreiben und Debug-Log-Holen der
Remote-INI. Sichtbar war davon nichts - die Statuszeile blieb einfach stehen.
Das umgebende ``try/except`` schuetzt nur das Einplanen, nicht die spaetere
Ausfuehrung.

Richtig ist, die Meldung noch im ``except``-Block zu bilden und nur den
fertigen Text einzufangen; alternativ die Vorgabewert-Bindung
``lambda e=str(exc): ...``, die an einer Stelle schon vorher so stand.

Geprueft wird die Regel allgemein ueber den Syntaxbaum, nicht nur an den vier
bekannten Zeilen - sonst faellt der naechste Fall wieder durch.
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
HAUPTQUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _quelldateien() -> list[Path]:
    dateien = [HAUPTQUELLE]
    dateien += sorted(PROJEKT.glob("ps5_validator/**/*.py"))
    dateien += sorted(PROJEKT.glob("tools/*.py"))
    return [p for p in dateien if p.is_file() and "__pycache__" not in str(p)]


def _gebundene_namen(args: ast.arguments) -> set[str]:
    """Namen, die der Rueckruf selbst bindet - die sind unbedenklich."""
    namen = {a.arg for a in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)}
    if args.vararg:
        namen.add(args.vararg.arg)
    if args.kwarg:
        namen.add(args.kwarg.arg)
    return namen


def _liest(knoten: ast.AST, name: str) -> bool:
    return any(isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
               for n in ast.walk(knoten))


def finde_einfaenge(quelle: str) -> list[tuple[int, str, str]]:
    """Liefert (Zeile, Ausnahmename, Art) fuer jeden Fund."""
    funde: list[tuple[int, str, str]] = []
    for handler in ast.walk(ast.parse(quelle)):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        name = handler.name
        for knoten in ast.walk(handler):
            if isinstance(knoten, ast.Lambda):
                # Vorgabewerte werden sofort ausgewertet und sind sicher -
                # geprueft wird nur der Rumpf.
                if name in _gebundene_namen(knoten.args):
                    continue
                if _liest(knoten.body, name):
                    funde.append((knoten.lineno, name, "lambda"))
            elif isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if name in _gebundene_namen(knoten.args):
                    continue
                if any(_liest(k, name) for k in knoten.body):
                    funde.append((knoten.lineno, name, f"def {knoten.name}"))
    return funde


class AusnahmeEinfangTests(unittest.TestCase):
    def test_kein_rueckruf_faengt_die_ausnahmevariable_ein(self):
        beanstandet = []
        for pfad in _quelldateien():
            for zeile, name, art in finde_einfaenge(pfad.read_text(encoding="utf-8")):
                beanstandet.append(f"{pfad.name}:{zeile} ({art} liest '{name}')")
        self.assertEqual(
            beanstandet, [],
            "Diese Rueckrufe lesen die Ausnahmevariable, die beim Verlassen des "
            "except-Blocks geloescht wird - sie sterben an einem NameError, sobald "
            "sie laufen:\n  " + "\n  ".join(beanstandet))

    def test_regel_erkennt_den_fehler_ueberhaupt(self):
        """Gegenprobe: Ohne sie koennte der Test stumm immer bestehen."""
        schlecht = (
            "def f(w):\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as exc:\n"
            "        w.after(0, lambda: print(exc))\n"
        )
        self.assertEqual(len(finde_einfaenge(schlecht)), 1)

    def test_regel_meldet_die_sichere_bindung_nicht(self):
        gut = (
            "def f(w):\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as exc:\n"
            "        w.after(0, lambda e=str(exc): print(e))\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as exc:\n"
            "        text = str(exc)\n"
            "        w.after(0, lambda: print(text))\n"
        )
        self.assertEqual(finde_einfaenge(gut), [])


class BehobeneStellenTests(unittest.TestCase):
    """Die vier bekannten Fehlerpfade bilden die Meldung jetzt vorher."""

    #: Backport fehlgeschlagen sowie Laden, Schreiben und Debug-Log-Holen der
    #: Remote-INI - die vier Stellen, an denen der Fehler auftrat.
    SCHLUESSEL = ("backport.state_error",
                  "remote_ini.status_load_failed",
                  "remote_ini.status_write_failed",
                  "remote_ini.status_fetch_failed")

    @classmethod
    def setUpClass(cls):
        cls.text = HAUPTQUELLE.read_text(encoding="utf-8")

    def test_alle_vier_melden_ueber_eine_vorher_gebildete_meldung(self):
        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                stelle = self.text.index(schluessel)
                zeile = self.text.rfind("\n", 0, stelle) + 1
                self.assertIn("meldung = ", self.text[zeile:stelle + len(schluessel) + 80],
                              f"{schluessel} sollte ueber eine vorher gebildete Meldung laufen")

    def test_die_meldung_wird_auch_zugestellt(self):
        """Gebildet allein genuegt nicht - sie muss in den Fensterfaden.

        Geprueft wird die **Eigenschaft**, nicht die Schreibweise: Im selben
        ``except``-Block muss ein ``after(...)`` stehen, das die vorher
        gebildete ``meldung`` weiterreicht. Ob das ein
        ``lambda: status_var.set(meldung)`` tut oder eine Funktion, die sie
        als Argument bekommt, ist gleichgueltig.

        Die Vorfassung zaehlte ``lambda: status_var.set(meldung)`` und
        verlangte genau drei Stueck. Am 04.09.2026 wurde der Ladeweg auf
        ``_load_failed(meldung, fragen, fehlertext)`` umgebaut - dieselbe
        Eigenschaft, andere Form -, und der Test fiel, obwohl nichts kaputt
        war. Solche Zaehlungen sind in diesem Projekt schon mehrfach zum
        Stolperstein geworden.
        """
        baum = ast.parse(self.text)
        gefunden = {}
        for handler in ast.walk(baum):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            for schluessel in self.SCHLUESSEL:
                if not any(isinstance(k, ast.Constant) and k.value == schluessel
                           for k in ast.walk(handler)):
                    continue
                # Ein after(...) im selben Block, das "meldung" mitnimmt.
                gefunden[schluessel] = any(
                    isinstance(k, ast.Call)
                    and getattr(k.func, "attr", "") == "after"
                    and _liest(ast.Module(body=[ast.Expr(a) for a in k.args],
                                          type_ignores=[]), "meldung")
                    for k in ast.walk(handler))

        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, gefunden,
                              "Der Fehlerpfad ist verschwunden - die Pruefung "
                              "greift nicht mehr.")
                self.assertTrue(
                    gefunden[schluessel],
                    "Die Meldung wird gebildet, aber nirgends ueber after() "
                    "zugestellt - die Statuszeile bleibt stehen.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
