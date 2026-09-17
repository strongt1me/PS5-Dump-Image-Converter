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
import subprocess
import sys
import unittest
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


#: Laeuft in einem eigenen Prozess, damit sicher die mitgelieferte MkPFS
#: gemessen wird - im Gesamtlauf kann ``mkpfs`` schon aus einer anderen Kopie
#: geladen sein (die Oberflaeche entpackt die eingebettete Engine).
_AUFRAEUMSTELLE_AUSLOESEN = r'''
import sys, tempfile
from pathlib import Path
from unittest import mock
sys.path.insert(0, sys.argv[1])
from mkpfs import pfs
assert Path(pfs.__file__).resolve().is_relative_to(Path(sys.argv[1]).resolve()), pfs.__file__

def _scheitern(**_werte):
    raise OSError("die eigentliche Ursache")

def _belegt(self, *_a, **_k):
    raise PermissionError(32, "Der Prozess kann nicht auf die Datei zugreifen")

with tempfile.TemporaryDirectory() as ordner:
    quelle = Path(ordner) / "quelle.bin"
    quelle.write_bytes(b"x" * 16)
    spool = Path(ordner) / "spool.tmp"
    try:
        with mock.patch.object(pfs, "_encode_pfsc_into_handle", _scheitern), \
                mock.patch.object(type(spool), "unlink", _belegt):
            pfs._encode_pfsc_file_to_spool(
                abs_path=quelle, spool_path=spool, threshold_gain=0,
                min_file_gain=0, zlib_level=6, logical_block_size=65536)
    except BaseException as fehler:
        print(type(fehler).__name__ + ": " + str(fehler))
    else:
        print("keine Ausnahme")
'''


class VerhaltenTests(unittest.TestCase):
    """Und was das praktisch bedeutet - an einer echten Aufraeumstelle gemessen."""

    def test_permissionerror_beim_loeschen_verdeckt_nichts_mehr(self):
        """Der Fall aus Aufgabe 3, an ``_encode_pfsc_file_to_spool`` nachgestellt.

        Das Kodieren scheitert, das Loeschen der Zwischendatei scheitert mit
        ``PermissionError`` (WinError 32). Ankommen muss die urspruengliche
        Ausnahme. Bis zum 17.09.2026 pruefte dieser Test einen Nachbau und
        ``contextlib.suppress`` aus der Standardbibliothek - eine Rueckkehr zu
        ``suppress(FileNotFoundError)`` in pfs.py haette er nie bemerkt
        (Befund T24).
        """
        lauf = subprocess.run(
            [sys.executable, "-c", _AUFRAEUMSTELLE_AUSLOESEN, str(PROJEKT / "MkPFS-1.0.0")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        ausgabe = lauf.stdout.strip().splitlines()
        self.assertEqual(lauf.returncode, 0, lauf.stderr[-2000:])
        self.assertEqual(ausgabe[-1:], ["OSError: die eigentliche Ursache"], lauf.stdout)


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
