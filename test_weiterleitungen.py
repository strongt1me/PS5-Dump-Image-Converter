# -*- coding: utf-8 -*-
"""Weiterleitungen an ausgelagerte Helfer muessen zu deren Signatur passen.

Am 04.09.2026 an echten Konvertierungen gefunden: **Jeder** ``.ffpkg``-Bau
brach ab mit

    TypeError: Pruefstand._validate_ffpkg_artifact() got an unexpected
    keyword argument 'expected_file_count'

Die Weiterleitung im Hauptmodul nahm ``expected_file_count`` entgegen und
reichte es **immer** weiter, auch als ``None`` - die Zielmethode kannte den
Namen aber nicht. Entstanden beim Herausziehen der Pruefungen nach
``abbild_pruefen`` (v1.9.2): Dort wanderte die Dateizaehlung in eigene
Methoden (``_verify_ffpkg_file_count_via_mount``), der Parameter blieb in der
Weiterleitung stehen. Kein Aufrufer hat ihn je mitgegeben - der Fehler hing
allein an der Weiterleitung.

**Warum kein Test das gemerkt hat:** Die Pruefreihe deckt die Rechenwege ab,
faehrt aber keine echte ``.ffpkg``-Erzeugung - die braucht
Administratorrechte und ein reales Abbild. Ein Fehler, der erst beim Aufruf
auffaellt, bleibt so unsichtbar.

Diese Pruefung braucht dafuer nichts auszufuehren: Sie liest die Aufrufe aus
dem Syntaxbaum und haelt die uebergebenen Schluesselwoerter gegen die
tatsaechliche Signatur der Zielmethode. Die Helfer werden dabei **nicht**
von Hand gepflegt, sondern an ihrer Rueckgabeannotation erkannt - ein neuer
Helfer faellt so von selbst unter die Pruefung.
"""
from __future__ import annotations

import ast
import importlib
import inspect
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

QUELLE = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


UTILS = PROJEKT / "ps5_validator" / "utils"


def helfergriffe(baum) -> dict[str, tuple[str, str]]:
    """Griff -> (Modulname, Klassenname), aus den Rueckgabeannotationen.

    Ein Helfergriff ist eine Methode von ``PS5ConverterGUI``, deren Rueckgabe
    als ``"<modul>.<Klasse>"`` angegeben ist - etwa
    ``-> "abbild_pruefen.Pruefstand"``.

    **Gefiltert wird an der Datei, nicht am Namen.** Annotationen wie
    ``tk.Frame`` oder ``Image.Image`` sehen genauso aus; sie zeigen aber auf
    Fremdbibliotheken. Beim ersten Wurf standen deshalb neun Fehlalarme in
    der Liste. Genommen wird nur, wozu es ein Modul unter
    ``ps5_validator/utils/`` gibt.
    """
    klasse = next(k for k in baum.body
                  if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    raus: dict[str, tuple[str, str]] = {}
    for m in klasse.body:
        if not isinstance(m, ast.FunctionDef) or m.returns is None:
            continue
        if not (isinstance(m.returns, ast.Constant)
                and isinstance(m.returns.value, str)):
            continue
        text = m.returns.value.strip()
        if text.count(".") != 1:
            continue
        modul, name = text.split(".")
        if not (modul.isidentifier() and name.isidentifier()):
            continue
        if not name[:1].isupper():
            continue
        if not (UTILS / (modul + ".py")).is_file():
            continue
        raus[m.name] = (modul, name)
    return raus


def lade(modul: str, name: str):
    return getattr(importlib.import_module("ps5_validator.utils." + modul), name)


def weiterleitungen(baum, griffe):
    """Jeder Aufruf der Form ``self.<helfergriff>().<methode>(...)``."""
    for k in ast.walk(baum):
        if not isinstance(k, ast.Call):
            continue
        f = k.func
        if not (isinstance(f, ast.Attribute)
                and isinstance(f.value, ast.Call)
                and isinstance(f.value.func, ast.Attribute)):
            continue
        griff = f.value.func.attr
        if griff not in griffe:
            continue
        yield k.lineno, griff, f.attr, {kw.arg for kw in k.keywords if kw.arg}


class WeiterleitungTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.baum = ast.parse(QUELLE.read_text(encoding="utf-8", errors="replace"))
        cls.griffe = helfergriffe(cls.baum)
        cls.alle = list(weiterleitungen(cls.baum, cls.griffe))

    def test_es_gibt_ueberhaupt_weiterleitungen(self) -> None:
        """Ohne das saehe alles darunter leer aus und meldete Erfolg."""
        self.assertGreaterEqual(
            len(self.griffe), 2,
            "Nur %d Helfergriff(e) erkannt: %s"
            % (len(self.griffe), sorted(self.griffe)))
        self.assertGreaterEqual(
            len(self.alle), 4,
            "Nur %d Weiterleitung(en) gefunden - die Auswertung greift nicht "
            "mehr." % len(self.alle))

    def test_jeder_helfer_laesst_sich_laden(self) -> None:
        """Eine Annotation, die ins Leere zeigt, waere derselbe Fehlertyp."""
        fehler = []
        for griff, (modul, name) in sorted(self.griffe.items()):
            try:
                lade(modul, name)
            except Exception as exc:
                fehler.append("%s -> %s.%s: %s" % (griff, modul, name, exc))
        self.assertEqual([], fehler, "; ".join(fehler))

    def test_kein_unbekanntes_schluesselwort(self) -> None:
        """Der eigentliche Fall - genau hier brach jeder .ffpkg-Bau ab."""
        fehler = []
        for zeile, griff, methode, uebergeben in self.alle:
            modul, name = self.griffe[griff]
            ziel = getattr(lade(modul, name), methode, None)
            if ziel is None:
                fehler.append("Zeile %d: %s.%s existiert nicht"
                              % (zeile, griff, methode))
                continue
            erlaubt = set(inspect.signature(ziel).parameters)
            zuviel = sorted(uebergeben - erlaubt)
            if zuviel:
                fehler.append("Zeile %d: %s.%s kennt %s nicht"
                              % (zeile, griff, methode, zuviel))
        self.assertEqual([], fehler, "; ".join(fehler))

    def test_die_pruefung_wuerde_den_alten_fehler_melden(self) -> None:
        """Gegenprobe: die Signatur von damals, gegen die echte Zielmethode.

        Ohne sie waere nicht belegt, dass die Pruefung oben etwas misst - sie
        koennte auch nur bestaetigen, dass nichts Erfundenes uebergeben wird.
        """
        ziel = getattr(lade("abbild_pruefen", "Pruefstand"),
                       "_validate_ffpkg_artifact")
        erlaubt = set(inspect.signature(ziel).parameters)
        self.assertNotIn(
            "expected_file_count", erlaubt,
            "Die Zielmethode nimmt den Parameter jetzt an - dann sagt diese "
            "Gegenprobe nichts mehr aus.")
        self.assertIn("base_result", erlaubt,
                      "Die Signatur sieht ganz anders aus als erwartet.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
