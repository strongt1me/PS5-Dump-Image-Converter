# -*- coding: utf-8 -*-
"""Ein misslungenes Aufräumen darf die eigentliche Ursache nicht verdecken.

MkPFS räumt seine Zwischendateien in ``except``-Blöcken weg und reicht die
ursprüngliche Ausnahme danach weiter. Der Kommentar der Vorlage sagt es
selbst:

    Re-raise the original exception after removing the temp file so callers
    observe the original traceback.

Abgesichert war das mit ``suppress(FileNotFoundError)``. Unter Windows ist
aber nicht "Datei weg" der Normalfall, sondern **"Datei noch belegt"**:
``PermissionError: [WinError 32]`` – ein Virenscanner, der Indexdienst, ein
Handle, das das Betriebssystem noch hält. Den fängt
``suppress(FileNotFoundError)`` nicht; er ersetzt die Ausnahme, die
weitergereicht werden sollte.

Am 10.09.2026 in Aufgabe 3 gemessen: Gemeldet wurde ein PermissionError beim
Aufräumen, die Ursache (ein ``RuntimeError`` aus ``multiprocessing``) stand
nur noch als "During handling of the above exception" im Stapel.

Diese Datei ist der Wächter für die fünfte Abweichung in
``MkPFS-1.0.0/UPSTREAM.md``. Sie muss bei jedem Fassungswechsel erneut
anschlagen, wenn die Zutat verlorengeht.
"""
from __future__ import annotations

import ast
import io
import sys
import unittest
from contextlib import suppress
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
PFS_PY = PROJEKT / "MkPFS-1.0.0" / "mkpfs" / "pfs.py"


class AufraeumenFaengtOSErrorTests(unittest.TestCase):
    """Die Zutat selbst - am Syntaxbaum, nicht an einer Textsuche."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = io.open(PFS_PY, encoding="utf-8", errors="replace").read()
        cls.baum = ast.parse(cls.quelle)

    def _suppress_aufrufe(self):
        """Alle ``with suppress(...)``-Blöcke, die etwas löschen."""
        treffer = []
        for knoten in ast.walk(self.baum):
            if not isinstance(knoten, (ast.With, ast.AsyncWith)):
                continue
            for eintrag in knoten.items:
                ruf = eintrag.context_expr
                if not isinstance(ruf, ast.Call):
                    continue
                name = getattr(ruf.func, "id", None) or getattr(ruf.func, "attr", None)
                if name != "suppress":
                    continue
                loescht = any(
                    getattr(k.func, "attr", "") in ("unlink", "remove", "rmtree")
                    for k in ast.walk(knoten) if isinstance(k, ast.Call))
                if not loescht:
                    continue
                gefangen = [getattr(a, "id", getattr(a, "attr", "?"))
                            for a in ruf.args]
                treffer.append((knoten.lineno, gefangen))
        return treffer

    def test_kein_loeschen_faengt_nur_filenotfounderror(self):
        """Wer löscht, muss jeden OSError schlucken - nicht nur den einen."""
        schlecht = [(z, g) for z, g in self._suppress_aufrufe()
                    if g == ["FileNotFoundError"]]
        self.assertEqual(
            [], schlecht,
            "Aufraeumen faengt nur FileNotFoundError - ein PermissionError "
            "(WinError 32) wuerde die eigentliche Ausnahme ersetzen:\n  "
            + "\n  ".join("Zeile %d: suppress(%s)" % (z, ", ".join(g))
                          for z, g in schlecht))

    def test_es_gibt_ueberhaupt_solche_stellen(self):
        """Gegenprobe: Die Messung oben muss etwas sehen können.

        Ohne diese Prüfung wäre die vorige auch dann grün, wenn die Datei
        umgebaut würde und gar keine Aufräumblöcke mehr enthielte - die
        Zusicherung wäre dann leer, ohne dass es jemandem auffiele.
        """
        self.assertGreaterEqual(
            len(self._suppress_aufrufe()), 5,
            "Kaum noch Aufraeumbloecke gefunden - die Vorlage hat sich "
            "geaendert, diese Pruefung misst nichts mehr.")

    def test_der_hinweis_steht_dabei(self):
        """Die Abweichung ist im Quelltext als solche kenntlich gemacht."""
        self.assertIn("Abweichung von der Vorlage: OSError statt FileNotFoundError",
                      self.quelle)


class VerhaltenTests(unittest.TestCase):
    """Und was das praktisch bedeutet - an einer echten Datei gemessen."""

    def test_permissionerror_beim_loeschen_verdeckt_nichts_mehr(self):
        """Der Fall aus Aufgabe 3, nachgestellt.

        Nicht am Quelltext von MkPFS, sondern am Muster: ``suppress(OSError)``
        lässt die ursprüngliche Ausnahme durch, ``suppress(FileNotFoundError)``
        nicht.
        """
        class _Belegt:
            def unlink(self):
                raise PermissionError(
                    32, "Der Prozess kann nicht auf die Datei zugreifen")

        tmp = _Belegt()

        def _mit(faenger):
            try:
                raise RuntimeError("die eigentliche Ursache")
            except Exception:
                with suppress(faenger):
                    tmp.unlink()
                raise

        # So war es: der PermissionError ersetzt die Ursache.
        with self.assertRaises(PermissionError):
            _mit(FileNotFoundError)

        # So ist es: die Ursache kommt durch.
        with self.assertRaises(RuntimeError) as gefangen:
            _mit(OSError)
        self.assertIn("die eigentliche Ursache", str(gefangen.exception))


class UpstreamNotizTests(unittest.TestCase):
    """Die Abweichung steht in UPSTREAM.md - sonst geht sie beim
    Fassungswechsel verloren."""

    def test_upstream_fuehrt_die_abweichung(self):
        notiz = io.open(PROJEKT / "MkPFS-1.0.0" / "UPSTREAM.md",
                        encoding="utf-8", errors="replace").read()
        self.assertIn("test_mkpfs_aufraeumen.py", notiz,
                      "Diese Datei steht nicht als Waechter in UPSTREAM.md.")
        self.assertIn("OSError", notiz)


if __name__ == "__main__":
    unittest.main(verbosity=2)
