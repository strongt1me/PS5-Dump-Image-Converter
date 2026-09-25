# -*- coding: utf-8 -*-
"""Waechter: Das Programm greift nicht in die Sicherheit des Rechners ein.

Bis v1.9.43 legte der Programmstart ungefragt ein selbst signiertes
Code-Signatur-Zertifikat (Schluessel exportierbar, zwischendurch als PFX mit
festem Passwort in %TEMP%) in LocalMachine\\Root und TrustedPublisher und trug
Virenschutz-Ausnahmen fuer den ganzen Programmordner ein - Defender per
Add-MpPreference, dazu Registry-Werte fuer sechs weitere Hersteller. Benutzt
hat das Programm das Zertifikat nie: Die EXE wird nicht damit signiert
(``codesign_identity=None`` in allen drei .spec, keine Signatur in
Build_EXE.ps1). Auf Entscheidung des Nutzers am 23.09.2026 entfernt.

Gelesen wird ueber den Syntaxbaum: Zeichenketten im Code zaehlen, Kommentare
nicht - der Erklaerkommentar an der alten Stelle nennt die Befehle absichtlich.
"""
from __future__ import annotations

import ast
import os
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

#: Befehle und Speicherorte, mit denen ein Programm Vertrauen oder Ausnahmen
#: auf dem Rechner anlegt. Keiner davon hat in diesem Programm etwas zu suchen.
MARKEN = (
    "Add-MpPreference",
    "Set-MpPreference",
    "New-SelfSignedCertificate",
    "Import-PfxCertificate",
    "Import-Certificate",
    "Export-PfxCertificate",
    "Cert:\\LocalMachine\\Root",
    "Cert:\\LocalMachine\\TrustedPublisher",
    "Windows Defender\\Exclusions",
    "certutil",
)


def _programmdateien() -> list[Path]:
    dateien = [HAUPTDATEI]
    for wurzel, _ordner, namen in os.walk(PROJEKT / "ps5_validator"):
        if "vendor" in Path(wurzel).parts or "__pycache__" in wurzel:
            continue
        dateien += [Path(wurzel) / n for n in namen if n.endswith(".py")]
    return dateien


def _zeichenketten(baum: ast.AST) -> list[tuple[int, str]]:
    """Alle Zeichenketten im Code, ohne Docstrings."""
    docstrings = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            erster = knoten.body[0] if knoten.body else None
            if (isinstance(erster, ast.Expr) and isinstance(erster.value, ast.Constant)
                    and isinstance(erster.value.value, str)):
                docstrings.add(id(erster.value))
    return [(k.lineno, k.value) for k in ast.walk(baum)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
            and id(k) not in docstrings]


class KeineSicherheitseingriffeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.baeume = {}
        for pfad in _programmdateien():
            cls.baeume[pfad] = ast.parse(pfad.read_bytes().decode("utf-8"))

    def test_die_pruefung_sieht_das_programm(self) -> None:
        self.assertIn(HAUPTDATEI, self.baeume)
        self.assertGreaterEqual(len(self.baeume), 30, "utils-Module nicht gefunden")
        anzahl = sum(len(_zeichenketten(b)) for b in self.baeume.values())
        self.assertGreater(anzahl, 10000, "Zeichenketten nicht gelesen - der Test mass nichts")

    def test_kein_zertifikat_und_keine_virenschutz_ausnahme(self) -> None:
        funde = []
        for pfad, baum in self.baeume.items():
            for zeile, text in _zeichenketten(baum):
                for marke in MARKEN:
                    if marke.lower() in text.lower():
                        funde.append("%s:%d %s" % (pfad.name, zeile, marke))
        self.assertEqual(funde, [], "Das Programm legt wieder Vertrauen/Ausnahmen an")

    def test_der_programmstart_ruft_nichts_dergleichen(self) -> None:
        namen = {k.id for k in ast.walk(self.baeume[HAUPTDATEI]) if isinstance(k, ast.Name)}
        namen |= {k.name for k in ast.walk(self.baeume[HAUPTDATEI])
                  if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for alt in ("_ensure_self_signed_cert_installed", "_ensure_av_exclusion"):
            self.assertNotIn(alt, namen)


if __name__ == "__main__":
    unittest.main()
