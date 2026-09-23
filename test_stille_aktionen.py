# -*- coding: utf-8 -*-
"""Kein langer Vorgang ohne Anzeige.

Auftrag des Nutzers (20.09.2026): *"es sollten überhaupt keine stille
aktionen durchgeführt werden die nicht angezeigt werden."*

Anlass waren zwei Stellen am selben Tag, beide beim Abliefern eines
Dump-Ordners:

* Das Vermessen der Quelle schrieb seinen Text einmal je Sekunde, und der
  Anzeige-Takt löschte ihn 100 ms später wieder – am Widget gemessen war er
  **5 % der Zeit** zu sehen.
* Das Verschieben ins Ziel war über Laufwerksgrenzen eine echte Kopie über
  zig Gigabyte – mit **null** Meldungen.

Diese Datei hält die Klasse fest, statt nur die zwei Fälle. Gesucht wird im
Syntaxbaum nach Aufrufen, die über einen ganzen Ordnerbaum laufen können;
für jeden wird geprüft, ob seine Funktion überhaupt irgendetwas meldet.

**Was der Test NICHT behauptet:** dass jeder Treffer ein Fehler ist. Ein
Durchlauf über ``sce_sys`` dauert Millisekunden und darf stumm bleiben.
Gemessen am größten echten Dump (Ghost of Yotei, 84.218 Dateien, 96,7 GB):
ein blanker ``os.walk`` 19,8 s kalt, die drei Durchläufe im Packweg
zusammen 2,0 s warm. Deshalb ist die Liste unten eine **Bestandsaufnahme**:
Was darin steht, ist bekannt und beurteilt. Kommt etwas Neues dazu, fällt
dieser Test – dann ist zu entscheiden, ob es melden muss oder in die Liste
gehört.
"""
from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PROJEKT = Path(__file__).resolve().parent
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
UTILS = PROJEKT / "ps5_validator" / "utils"

#: Aufrufe, die über beliebig viele Dateien laufen können.
LANGE_VORGAENGE = {
    "copytree": "shutil.copytree",
    "rmtree": "shutil.rmtree",
    "move": "shutil.move",
    "unpack_archive": "shutil.unpack_archive",
    "make_archive": "shutil.make_archive",
    "walk": "os.walk",
    "extractall": "ZipFile.extractall",
    "_get_path_size": "_get_path_size",
    "_move_tree_into": "_move_tree_into",
}

#: Woran erkennbar ist, dass eine Funktion sich meldet. Bewusst breit: Der
#: Test soll neue stumme Stellen finden, nicht über die Form streiten.
MELDER = (
    "_set_status", "_set_progress", "_append_to_log", "_teilschritt_melden",
    "progress_cb", "melden", "_melde", "fortschritt", "copy_function",
    "_copy_done_bytes", "_copy_total_bytes", "progress_callback",
    "_mess_infotext", "_pack_infotext", "status_label",
    "_update_info_box", "_groessenfeld_setzen_wenn_aktuell",
)

#: Funktionen, die nicht über Nutzdaten laufen oder selbst der Melder sind.
AUSGENOMMEN = {
    "_baumgroesse_still",
    "_sweep_stale_temp_dirs",
    "_snapshot_exit_cleanup_paths",
    "_temp_reste_nach_aufgabe_abraeumen",
    "_cleanup_stale_osfmounts",
    "_run_startup_temp_cleanup_scan",
}

#: Bestandsaufnahme vom 20.09.2026 (v1.9.33). Jeder Eintrag ist angesehen:
#: Er läuft über kleine, feste Ordner (Werkzeuge, sce_sys, Vorschaubilder)
#: oder räumt auf. Wer einen davon erledigt, nimmt ihn hier heraus.
BEKANNT_STUMM: set[tuple[str, str, str]] = {
    # Gemessen am 22.09.2026: Der Werkzeugordner ProsperoPkg-2.5/win-x64 hat
    # 7 Dateien und 1,4 MB; copytree braucht dafuer 13-17 ms (drei Laeufe).
    # Dazu geschieht es nur, wenn sich die eigene Bibliothek in libs geaendert
    # hat - danach folgt ein Bau von Minuten bis Stunden. Eine Meldung waere
    # hier Laerm, keine Auskunft. Welche Bibliothek gilt, sagt stattdessen der
    # Diagnosebericht (_diagnose_eigene_bibliotheken).
    ("eigene_bibliotheken.py", "einsatzordner", "shutil.copytree"),
    ("eigene_bibliotheken.py", "einsatzordner", "shutil.rmtree"),
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_art_wechseln", "shutil.move"),
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_do_build", "os.walk"),
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_doktor_werkzeuge_starten", "os.walk"),
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_estimate_compression_ratio", "os.walk"),
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_exfat_erwartete_dateizahl", "os.walk"),
    ("PS5ImageConverter_Pro_FINAL_revised.py", "_rmtree_force", "shutil.rmtree"),
    ("abbild_metadaten.py", "_load_cover_image", "os.walk"),
    ("abbild_metadaten.py", "_load_fallback_art_image", "os.walk"),
    ("abbild_pruefen.py", "_verify_ffpkg_file_count_via_mount", "os.walk"),
    ("ampr_assetpakete.py", "bestand_aufraeumen", "shutil.rmtree"),
    ("ampr_assetpakete.py", "direktleser_merkmale", "os.walk"),
    ("ampr_assetpakete.py", "filmordner_muster", "os.walk"),
    ("ampr_assetpakete.py", "systemdateien_muster", "os.walk"),
    ("diagnose_befund.py", "_ordnergroesse", "os.walk"),
    ("ffpkg_support.py", "validate_source_folder", "os.walk"),
    ("file_io.py", "get_all_files", "os.walk"),
    ("prosperopkg.py", "zeitgrenze_fuer", "os.walk"),
    ("ps5_backport.py", "kandidaten", "os.walk"),
    ("wee_tools.py", "kopie_anlegen", "shutil.copytree"),
    ("werkzeuge_bereitstellen.py", "_entpacken", "ZipFile.extractall"),
    ("werkzeuge_bereitstellen.py", "_mkpfs_eltern_finden", "os.walk"),
}


def _name_von(knoten: ast.AST) -> str:
    if isinstance(knoten, ast.Attribute):
        return knoten.attr
    if isinstance(knoten, ast.Name):
        return knoten.id
    return ""


def _stumme_stellen(pfad: Path) -> set[tuple[str, str, str]]:
    """(Datei, Funktion, Vorgang) für jede Stelle ohne jede Meldung."""
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    eltern: dict[ast.AST, ast.AST] = {}
    for knoten in ast.walk(baum):
        for kind in ast.iter_child_nodes(knoten):
            eltern[kind] = knoten

    def funktion_um(knoten: ast.AST):
        k = knoten
        while k in eltern:
            k = eltern[k]
            if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return k
        return None

    gefunden: set[tuple[str, str, str]] = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        name = _name_von(knoten.func)
        if name not in LANGE_VORGAENGE:
            continue
        funktion = funktion_um(knoten)
        if funktion is None or funktion.name in AUSGENOMMEN:
            continue
        if any(m in ast.unparse(funktion) for m in MELDER):
            continue
        gefunden.add((pfad.name, funktion.name, LANGE_VORGAENGE[name]))
    return gefunden


def _alle_stummen() -> set[tuple[str, str, str]]:
    gefunden: set[tuple[str, str, str]] = set()
    for pfad in [HAUPTDATEI, *sorted(UTILS.glob("*.py"))]:
        gefunden |= _stumme_stellen(pfad)
    return gefunden


class StilleAktionenTests(unittest.TestCase):
    """Die Klasse darf nicht wachsen."""

    def test_keine_neue_stumme_stelle(self):
        neu = _alle_stummen() - BEKANNT_STUMM
        self.assertFalse(
            neu,
            "Neue lange Vorgaenge ohne jede Anzeige:\n" + "\n".join(
                "  %s / %s / %s" % eintrag for eintrag in sorted(neu))
            + "\n\nEntweder melden lassen (Statuszeile, Balken oder Protokoll) "
              "oder - wenn der Vorgang wirklich Millisekunden dauert - in "
              "BEKANNT_STUMM aufnehmen, mit gemessener Begruendung.")

    def test_die_liste_enthaelt_nichts_erledigtes(self):
        """Wer eine Stelle repariert, nimmt sie hier heraus.

        Sonst wüchse die Liste zu einer Sammlung von Behauptungen über
        Code, den es so nicht mehr gibt.
        """
        veraltet = BEKANNT_STUMM - _alle_stummen()
        self.assertFalse(
            veraltet,
            "Diese Stellen melden sich inzwischen - Eintrag entfernen:\n"
            + "\n".join("  %s / %s / %s" % e for e in sorted(veraltet)))

    def test_das_vermessen_meldet_sich(self):
        """Der erste der beiden Fälle vom 20.09.2026."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("def _quellgroesse_mit_meldung")
        ende = quelle.index("def _get_path_size", anfang)
        self.assertIn("_mess_infotext", quelle[anfang:ende])

    def test_das_verschieben_meldet_sich(self):
        """Der zweite: über Laufwerksgrenzen ist es eine echte Kopie."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        rufe = [k for k in ast.walk(baum)
                if isinstance(k, ast.Call)
                and isinstance(k.func, ast.Attribute)
                and k.func.attr == "_move_tree_into"
                and any(s.arg == "melden" for s in k.keywords)]
        self.assertTrue(rufe, "Keine Aufrufstelle reicht einen Melder durch.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
