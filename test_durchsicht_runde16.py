# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 16 (25.09.2026): feste Texte.

Saetze, die auf der englischen Oberflaeche deutsch ankamen:

* **H6-13** - FFPKG-Bau: fuenf Aufgabenbezeichnungen, drei
  Profilbeschreibungen (log.auto.0095), die Gruende verworfener
  Bauversuche und die Statuszeile ("UFS2-Dateisystem im Temp-Staging
  erstellen ...").
* **zlib-ng** - die Selbstinstallation im MkPFS-Lauf schrieb sieben feste
  Zeilen ueber ``writer.write``.
* **H8-12** - Entpacken: Ausnahmetexte ("Gemountetes Laufwerk ... erschien
  nicht rechtzeitig"), die ueber ``v0=exc`` ins Protokoll gehen.
* **abbild_pruefen** - 23 Einzelheiten der Ergebnispruefung, obwohl der
  Pruefstand seinen Uebersetzer (``text=``) laengst bekam.
* **U1-4** - PKG Merger: sechs Pruefgruende ausserhalb der ``MELDUNGEN``.
* **UFS2Tool** - zwei Fehlermeldungen beim Start einer .ffpkg-Aufgabe; die
  Pruefsummenmeldung sogar in Umschrift.
* **"unbekannt"** als Rueckfall beim Fortsetzen (log.auto.0039).

Den Rundumschlag in ``test_sprachlecks`` gibt es seit dieser Runde auch fuer
``writer.write`` und Ausnahme-Konstruktoren. Hier stehen die Stellen, die er
nicht sehen kann: Hilfsmodule, Tupelglieder, dict-Werte, Rueckfallwerte.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde16")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import abbild_pruefen              # noqa: E402
from ps5_validator.utils import pkg_merger                  # noqa: E402
from ps5_validator.utils import werkzeuge_bereitstellen as wb  # noqa: E402
from ps5_validator.utils.i18n import STRINGS, translate     # noqa: E402

#: Enthaelt der Text ein Wort? Wie in test_sprachlecks: Gesucht wird nicht
#: nach deutschen Woertern - die Suche danach fand nur die Haelfte.
EIN_WORT = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}")

_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _englisch(schluessel: str, **werte) -> str:
    return translate("en", schluessel, **werte)


def _fester_text(knoten: ast.AST) -> str:
    """Der feste Textanteil eines Ausdrucks - leer, wenn er keinen hat."""
    if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
        return knoten.value
    if isinstance(knoten, ast.JoinedStr):
        return "".join(w.value for w in knoten.values
                       if isinstance(w, ast.Constant) and isinstance(w.value, str))
    if isinstance(knoten, ast.BinOp):
        return _fester_text(knoten.left) + _fester_text(knoten.right)
    return ""


# ---------------------------------------------------------------- abbild_pruefen

class ErgebnispruefungTests(unittest.TestCase):
    """Die Einzelheiten der Ergebnispruefung kommen aus dem Uebersetzer."""

    def _stand(self) -> abbild_pruefen.Pruefstand:
        return abbild_pruefen.Pruefstand(text=_englisch)

    def test_fehlender_ausgabepfad(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            befund = self._stand()._verify_output_artifact(
                "pack_file", os.path.join(ordner, "gibt_es_nicht.ffpfsc"))
        self.assertEqual("The output path does not exist.", befund["detail"])

    def test_leere_datei(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, "leer.bin")
            open(pfad, "wb").close()
            befund = self._stand()._verify_output_artifact("pack_file", pfad)
        self.assertEqual("The file is empty (0 bytes).", befund["detail"])

    def test_ordnerzaehlung(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            for name, groesse in (("a.bin", 3), ("b.bin", 4)):
                with open(os.path.join(ordner, name), "wb") as datei:
                    datei.write(b"x" * groesse)
            befund = self._stand()._verify_output_artifact("pack_file", ordner)
        self.assertEqual("Files: 2, bytes: 7", befund["detail"])

    def test_pruefsumme_einer_datei(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, "daten.bin")
            with open(pfad, "wb") as datei:
                datei.write(b"PS5")
            befund = self._stand()._verify_output_artifact("pack_file", pfad)
        self.assertTrue(befund["ok"])
        self.assertEqual("Verification successful.", befund["detail"])

    def test_exfat_zaehlung_ohne_engine(self) -> None:
        befund = self._stand()._verify_exfat_file_count("gibt_es_nicht.exfat", 3)
        self.assertEqual("skipped (MkPFS engine not available)", befund["detail"])

    def test_keine_feste_einzelheit_im_modul(self) -> None:
        """Jede Zuweisung an ``detail`` geht durch den Uebersetzer."""
        baum = ast.parse(Path(abbild_pruefen.__file__).read_text(encoding="utf-8"))
        funde, gesehen = [], 0
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Assign):
                continue
            for ziel in knoten.targets:
                heisst_detail = (
                    (isinstance(ziel, ast.Name) and ziel.id == "detail")
                    or (isinstance(ziel, ast.Subscript)
                        and isinstance(ziel.slice, ast.Constant)
                        and ziel.slice.value == "detail"))
                if not heisst_detail:
                    continue
                gesehen += 1
                text = _fester_text(knoten.value)
                if EIN_WORT.search(text):
                    funde.append((knoten.lineno, text))
        self.assertGreaterEqual(gesehen, 20, "Die Suche findet die Zuweisungen nicht mehr.")
        self.assertEqual([], funde)


# ---------------------------------------------------------------- pkg_merger

class PkgMergerTests(unittest.TestCase):
    """U1-4: Die Pruefgruende gehen durch MELDUNGEN und ``texte=``."""

    def _texte(self) -> dict:
        return {k: STRINGS["pkg_merger.log_" + k]["en"] for k in pkg_merger.MELDUNGEN}

    def test_fehlendes_teil(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            wurzel = os.path.join(ordner, "Spiel_0.pkg")
            with open(wurzel, "wb") as datei:
                datei.write(b"\0" * 0x60)
            fehlt = os.path.join(ordner, "Spiel_1.pkg")
            befund = pkg_merger.validate_split_set([wurzel, fehlt], None,
                                                   texte=self._texte())
        self.assertIn("Part missing: “%s”." % fehlt, befund.errors)

    def test_fehlender_metadatenteil(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            wurzel = os.path.join(ordner, "Spiel_0.pkg")
            with open(wurzel, "wb") as datei:
                datei.write(b"\0" * 0x60)
            meta = os.path.join(ordner, "Spiel_sc.pkg")
            befund = pkg_merger.validate_split_set([wurzel], meta, texte=self._texte())
        self.assertIn("Metadata part missing: “%s”." % meta, befund.errors)

    def test_ohne_wurzelteil(self) -> None:
        with self.assertRaises(ValueError) as fall:
            pkg_merger.validate_split_set([], None, texte=self._texte())
        self.assertEqual("At least the root part (_0) is required.", str(fall.exception))

    def test_zusammenfuegen_meldet_den_grund(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            wurzel = os.path.join(ordner, "Spiel_0.pkg")
            with open(wurzel, "wb") as datei:
                datei.write(b"\0" * 0x60)
            with self.assertRaises(pkg_merger.PkgMergeError) as fall:
                pkg_merger.merge_split_set([wurzel], None,
                                           os.path.join(ordner, "aus.pkg"),
                                           texte=self._texte())
        self.assertTrue(str(fall.exception).startswith("The split set fails validation: "),
                        str(fall.exception))

    def test_ohne_texte_bleibt_die_vorgabe(self) -> None:
        """Aufrufer ohne ``texte`` bekommen den bisherigen Wortlaut."""
        with self.assertRaises(ValueError) as fall:
            pkg_merger.validate_split_set([], None)
        self.assertEqual(pkg_merger.MELDUNGEN["wurzelteil_fehlt"], str(fall.exception))

    def test_kein_fester_pruefgrund_ausserhalb_der_meldungen(self) -> None:
        """``errors.append(...)`` und ``raise ...(...)`` tragen keinen festen Satz."""
        baum = ast.parse(Path(pkg_merger.__file__).read_text(encoding="utf-8"))
        funde, gesehen = [], 0
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
                    and knoten.func.attr == "append"
                    and getattr(knoten.func.value, "id", "") == "errors"):
                argumente = knoten.args
            elif isinstance(knoten, ast.Raise) and isinstance(knoten.exc, ast.Call):
                argumente = knoten.exc.args
            else:
                continue
            gesehen += 1
            for argument in argumente:
                text = _fester_text(argument)
                if EIN_WORT.search(text):
                    funde.append((knoten.lineno, text))
        self.assertGreaterEqual(gesehen, 10, "Die Suche findet die Stellen nicht mehr.")
        self.assertEqual([], funde)


# ---------------------------------------------------------------- UFS2Tool

class Ufs2ToolTests(unittest.TestCase):
    """Die Meldungen beim Start einer .ffpkg-Aufgabe."""

    def setUp(self) -> None:
        self.kennung = wb.ufs2tool_kennung()
        if not self.kennung:
            self.skipTest("fuer diese Plattform liefert das Programm kein UFS2Tool")

    def _falscher_bau(self, ordner: str) -> str:
        unter = Path(ordner) / self.kennung
        unter.mkdir()
        datei = unter / wb._ufs2tool_dateiname(self.kennung)
        datei.write_bytes(b"nicht das echte Werkzeug")
        (Path(ordner) / "pruefsummen.json").write_text(json.dumps(
            {"plattformen": {self.kennung: {"sha256": "0" * 64}}}), encoding="utf-8")
        return str(datei)

    def test_fehlende_datei(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            with self.assertRaises(RuntimeError) as fall:
                wb.ufs2tool_bereitstellen(lambda _n: ordner, text=_englisch)
        self.assertTrue(str(fall.exception).startswith("UFS2Tool v4.1 is missing: "),
                        str(fall.exception))

    def test_falsche_pruefsumme(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            self._falscher_bau(ordner)
            with self.assertRaises(RuntimeError) as fall:
                wb.ufs2tool_bereitstellen(lambda _n: ordner, text=_englisch)
        self.assertTrue(str(fall.exception).startswith(
            "UFS2Tool v4.1 integrity check for %s failed" % self.kennung), str(fall.exception))

    def test_das_bauskript_behaelt_die_vorgabe(self) -> None:
        """Ohne Uebersetzer (ufs2tool_buendel_pruefen im Bauskript) wie bisher."""
        with tempfile.TemporaryDirectory() as ordner:
            pfad = self._falscher_bau(ordner)
            with self.assertRaises(RuntimeError) as fall:
                wb.ufs2tool_pruefsumme(ordner, self.kennung, pfad)
        self.assertIn("Integritaetspruefung", str(fall.exception))


# ---------------------------------------------------------------- FFPKG-Bau (H6-13)

class FfpkgBauTests(unittest.TestCase):
    """Bezeichnungen, Profile, Gruende und Status gehen durch ``self._t``."""

    def test_jede_aufgabenbezeichnung_ist_uebersetzt(self) -> None:
        aufrufe = [k for k in ast.walk(_baum()) if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_build_ffpkg_from_folder"]
        self.assertGreaterEqual(len(aufrufe), 5, "Die Suche findet die Aufrufer nicht mehr.")
        for aufruf in aufrufe:
            wert = next((w.value for w in aufruf.keywords if w.arg == "task_label"), None)
            with self.subTest(zeile=aufruf.lineno):
                self.assertIsNotNone(wert)
                self.assertFalse(EIN_WORT.search(_fester_text(wert)), ast.unparse(wert))

    def test_profile_gruende_status_und_rueckfallwerte(self) -> None:
        funktion = _methode("_build_ffpkg_from_folder")
        funde = []

        def _pruefe(knoten: ast.AST, ausdruck: ast.AST) -> None:
            text = _fester_text(ausdruck)
            if EIN_WORT.search(text):
                funde.append((knoten.lineno, text))

        versuche = 0
        for knoten in ast.walk(funktion):
            # build_attempts steht mit Typangabe da (AnnAssign) - eine Suche
            # nur nach Assign fand die Versuche nicht (erster Lauf: 0 von 3).
            if isinstance(knoten, (ast.Assign, ast.AnnAssign)):
                ziele = knoten.targets if isinstance(knoten, ast.Assign) else [knoten.target]
                namen = {getattr(z, "id", "") for z in ziele}
                if "build_attempts" in namen:
                    for tupel in knoten.value.elts:
                        versuche += 1
                        _pruefe(tupel, tupel.elts[1])      # die Beschreibung
                if "detail" in namen:
                    _pruefe(knoten, knoten.value)        # Grund des Verwerfens
            if isinstance(knoten, ast.Dict):
                for schluessel, wert in zip(knoten.keys, knoten.values):
                    if isinstance(schluessel, ast.Constant) and schluessel.value == "status":
                        _pruefe(knoten, wert)
            if (isinstance(knoten, ast.Call) and getattr(knoten.func, "attr", "") == "get"
                    and len(knoten.args) == 2):
                _pruefe(knoten, knoten.args[1])           # Rueckfallwert
        self.assertEqual(3, versuche, "Die Bauversuche sind nicht mehr zu finden.")
        self.assertEqual([], funde)


# ---------------------------------------------------------------- Fortsetzen

class FortsetzenTests(unittest.TestCase):
    def test_kein_festes_unbekannt_im_protokoll(self) -> None:
        """Der Zustand eines Checkpoints landet in log.auto.0039."""
        feste = [k.lineno for k in ast.walk(_methode("_launch_task"))
                 if isinstance(k, ast.Constant) and k.value == "unbekannt"]
        self.assertEqual([], feste)


if __name__ == "__main__":
    unittest.main()
