"""Regressionstest: Protokollspiegelung im CLI-Modus darf nie abbrechen.

Gefunden beim Durchtesten aller Aufgaben: Leitet man die Ausgabe des
CLI-Modus in eine Datei um, wählt Windows dafür die Codepage der Konsole
(meist cp1252). Eine Protokollzeile mit „→" – etwa die Größenangabe
„618.4 MB → ~347.6 MB" – löste dort einen UnicodeEncodeError aus. Der schlug
bis in den Aufgaben-Thread durch und beendete die Konvertierung als
„Unerwarteter Fehler", obwohl die Arbeit bereits fertig war.

Zwei Ebenen sichern das ab:
  1. `_prepare_cli_streams()` stellt stdout/stderr auf UTF-8 um.
  2. `_append_to_log()` fängt Kodierfehler zusätzlich ab und ersetzt die
     Zeichen, statt die Aufgabe scheitern zu lassen.
"""
from __future__ import annotations

import io
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI, _prepare_cli_streams

PFEIL_ZEILE = "618.4 MB → ~347.6 MB\n"


class _Root:
    """Minimaler Ersatz für das Tk-Fenster."""

    @staticmethod
    def after(*_args, **_kwargs) -> None:
        return None


def _gui_im_cli_modus() -> PS5ConverterGUI:
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._cli_mode = True
    gui._cli_quiet = False
    gui._clean_log_text = lambda text: text
    gui.root = _Root()
    return gui


class CliProtokollTests(unittest.TestCase):
    def setUp(self) -> None:
        self._stdout = sys.stdout

    def tearDown(self) -> None:
        sys.stdout = self._stdout

    def _mit_kodierung(self, kodierung: str, fehlerbehandlung: str = "strict") -> io.BytesIO:
        puffer = io.BytesIO()
        sys.stdout = io.TextIOWrapper(puffer, encoding=kodierung, errors=fehlerbehandlung, newline="")
        return puffer

    def test_pfeil_bricht_cp1252_ausgabe_nicht_ab(self):
        """Der eigentliche Fehlerfall: umgeleitete Ausgabe unter Windows."""
        puffer = self._mit_kodierung("cp1252")
        gui = _gui_im_cli_modus()
        gui._append_to_log(PFEIL_ZEILE)          # darf nicht werfen
        sys.stdout.flush()
        ausgabe = puffer.getvalue().decode("cp1252")
        self.assertIn("618.4 MB", ausgabe)
        self.assertIn("347.6 MB", ausgabe)

    def test_utf8_erhaelt_das_zeichen(self):
        puffer = self._mit_kodierung("utf-8")
        gui = _gui_im_cli_modus()
        gui._append_to_log(PFEIL_ZEILE)
        sys.stdout.flush()
        self.assertIn("→", puffer.getvalue().decode("utf-8"))

    def test_ascii_ausgabe_bricht_nicht_ab(self):
        """Auch die engste Kodierung darf die Aufgabe nicht scheitern lassen."""
        puffer = self._mit_kodierung("ascii")
        gui = _gui_im_cli_modus()
        gui._append_to_log("Fortschritt: 50 % → fertig\n")
        sys.stdout.flush()
        self.assertIn("Fortschritt", puffer.getvalue().decode("ascii", errors="replace"))

    def test_stille_gibt_gar_nichts_aus(self):
        puffer = self._mit_kodierung("cp1252")
        gui = _gui_im_cli_modus()
        gui._cli_quiet = True
        gui._append_to_log(PFEIL_ZEILE)
        sys.stdout.flush()
        self.assertEqual(puffer.getvalue(), b"")

    def test_stroeme_werden_auf_utf8_gestellt(self):
        puffer = self._mit_kodierung("cp1252")
        _prepare_cli_streams()
        self.assertEqual(sys.stdout.encoding.lower().replace("-", ""), "utf8")
        gui = _gui_im_cli_modus()
        gui._append_to_log(PFEIL_ZEILE)
        sys.stdout.flush()
        self.assertIn("→", puffer.getvalue().decode("utf-8"))


class RechtepruefungTests(unittest.TestCase):
    """Ohne Administratorrechte darf der CLI-Modus keinen Erfolg melden.

    Gemessen am 22.08.2026: Ein Aufruf wie
    ``--cli --task 3 --source ... --dest ...`` beendete sich unter Windows
    ohne erhoehte Rechte mit **Rueckgabe 0**, ohne irgendetwas getan zu
    haben. Das Programm ruft dort ShellExecuteW mit "runas" auf; der
    abgekoppelte Prozess kann seine Ausgabe und seinen Rueckgabewert nicht
    an den Aufrufer zurueckgeben, und ein Skript hielt die Aufgabe fuer
    erledigt.

    Der Zweig laesst sich hier nicht ausfuehren - er haengt an
    ``_is_admin()`` und beendet den Prozess. Geprueft wird deshalb der
    Quelltext an genau dieser Stelle.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def _rechteblock(self) -> str:
        anfang = self.quelltext.index("    if sys.platform == \"win32\" and not _is_admin():")
        ende = self.quelltext.index("sys.exit(0)", anfang) + len("sys.exit(0)")
        return self.quelltext[anfang:ende]

    def test_der_cli_modus_wird_vorher_abgefangen(self) -> None:
        block = self._rechteblock()
        self.assertIn('if "--cli" in sys.argv[1:]:', block,
                      "Der CLI-Modus laeuft wieder in die Neustartlogik.")
        # Die Abfrage muss VOR dem Neustart stehen, sonst ist sie wirkungslos.
        self.assertLess(block.index('if "--cli"'), block.index("_request_elevation()"),
                        "Die CLI-Abfrage steht hinter dem Neustart.")

    def test_der_rueckgabewert_ist_nicht_null(self) -> None:
        block = self._rechteblock()
        cli_teil = block[block.index('if "--cli"'):block.index("_request_elevation()")]
        self.assertIn("sys.exit(3)", cli_teil)
        self.assertNotIn("sys.exit(0)", cli_teil,
                         "Der stille Erfolg ist zurueck.")

    def test_die_meldung_sagt_was_zu_tun_ist(self) -> None:
        cli_teil = self._rechteblock()
        self.assertIn("[FEHLER]", cli_teil)
        self.assertIn("Administrator", cli_teil)

    def test_die_stroeme_stehen_vor_der_meldung(self) -> None:
        """Sonst scheitert der Umlaut, sobald jemand umleitet.

        Genau dafuer gibt es _prepare_cli_streams - die Meldung erscheint
        aber, bevor _run_cli sie sonst aufruft.
        """
        cli_teil = self._rechteblock()
        self.assertIn("_prepare_cli_streams()", cli_teil)
        self.assertLess(cli_teil.index("_prepare_cli_streams()"),
                        cli_teil.index("[FEHLER]"))


class CliRueckfragenTests(unittest.TestCase):
    """Jede Rueckfrage des Systems, die das Programm stellt, bekommt im CLI-Modus eine Antwort.

    Gemessen am 03.11.2026 (Matrixlauf der Aufgaben 1-8): ``--cli --task 1 --yes`` mit einem Dump, der
    Preflight-Warnungen ausloeste, blieb stehen. ``_launch_task`` fragt dann mit ``messagebox.askokcancel``; ``_run_cli``
    ersetzte aber nur askyesno/askquestion/showerror/showwarning/showinfo. Der echte Dialog blieb ohne sichtbares Fenster
    offen, und der Lauf wartete fuer immer (im Skript ohne jede Meldung).
    """

    @classmethod
    def setUpClass(cls) -> None:
        import ast  # noqa: PLC0415
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"))
        cls.baum = baum
        cls.run_cli = next(k for k in baum.body if isinstance(k, ast.FunctionDef) and k.name == "_run_cli")

    @staticmethod
    def _messagebox_namen(knoten) -> set:
        import ast  # noqa: PLC0415
        return {n.attr for n in ast.walk(knoten) if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == "messagebox"}

    def _ersetzt(self) -> set:
        import ast  # noqa: PLC0415
        namen = set()
        for k in ast.walk(self.run_cli):
            if isinstance(k, ast.Assign):
                for ziel in k.targets:
                    if (isinstance(ziel, ast.Attribute) and isinstance(ziel.value, ast.Name)
                            and ziel.value.id == "messagebox"):
                        namen.add(ziel.attr)
        return namen

    def test_jede_benutzte_rueckfrage_wird_im_cli_modus_ersetzt(self) -> None:
        benutzt = {n for n in self._messagebox_namen(self.baum) if n.startswith("ask")}
        self.assertGreaterEqual(len(benutzt), 3, "der Syntaxbaum zeigt die benutzten Funktionen nicht mehr")
        self.assertEqual(set(), benutzt - self._ersetzt(),
                         "Diese messagebox-Funktionen sind im CLI-Modus nicht ersetzt - der Lauf wuerde an einem "
                         "unsichtbaren Dialog haengen bleiben")

    def test_gegenprobe_der_alte_stand_faellt_auf(self) -> None:
        """Mit dem Stand vor der Korrektur (ohne askokcancel) schluege der Waechter an."""
        benutzt = {n for n in self._messagebox_namen(self.baum) if n.startswith("ask")}
        alt = self._ersetzt() - {"askokcancel", "askyesnocancel", "askretrycancel"}
        self.assertIn("askokcancel", benutzt - alt)

    def test_ohne_zusage_gilt_nie_weiter(self) -> None:
        """Ohne --yes antworten die neuen Ersatzfunktionen mit Abbrechen, nie mit Weiter."""
        import ast  # noqa: PLC0415
        quelle = ast.get_source_segment((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"),
                                        self.run_cli)
        self.assertIn("messagebox.askyesnocancel = lambda *a, **k: (True if yes else None)", quelle)
        self.assertIn("messagebox.askretrycancel = lambda *a, **k: False", quelle)
        self.assertIn("messagebox.askokcancel = lambda *a, **k: yes", quelle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
