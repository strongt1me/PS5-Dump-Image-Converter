# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 17 (25.09.2026): Validatoren.

Die vier Validatoren (Dump-Ordner, .ffpfs/.ffpfsc, .exfat, .ffpkg) und
``ffpkg_support`` schrieben ihre Befunde fest deutsch. Aufgabe 8 und die
Ergebnispruefung eines .ffpkg zeigten sie so auch auf der englischen
Oberflaeche - samt der Zusammenfassungswerte ("nesting: in Ordnung (...)").

Muster wie ueberall unter ``ps5_validator``: Die Module binden i18n nicht
ein, tragen ihre Saetze als ``MELDUNGEN`` und nehmen ueber ``texte=`` die
uebersetzten entgegen. Die deutschen Vorgaben sind wortgleich mit dem
frueheren Text - darauf bauen test_validator_nesting, test_ffpfs_bauform und
test_incomplete_dump. Der Dispatcher vereinigt die vier Tabellen unter dem
Praefix "validator.".

* **U4-9** - die Validatoren samt ``hashing.sha256_stream`` ("Lesefehler bei
  Byte ...").
* **U4-8** - ``ffpkg_support``: die Saetze, die ein Anwender erreicht
  (Quellordner, Groessen). Profil- und Pfadwaechter bleiben begruendet fest.
* Nebenbei: "nicht geprueft" in der Rechte-Meldung des .ffpkg-Validators
  stand in Umschrift.
"""
from __future__ import annotations

import ast
import os
import re
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde17")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.core import dispatcher                   # noqa: E402
from ps5_validator.modules.dump_validator import DumpValidator      # noqa: E402
from ps5_validator.modules.extfat_validator import ExtfatValidator  # noqa: E402
from ps5_validator.modules.ffpfs_validator import FfpfsValidator    # noqa: E402
from ps5_validator.modules.ffpkg_validator import FfpkgValidator    # noqa: E402
from ps5_validator.utils import abbild_pruefen              # noqa: E402
from ps5_validator.utils import ffpkg_support               # noqa: E402
from ps5_validator.utils import hashing                     # noqa: E402
from ps5_validator.utils.i18n import translate              # noqa: E402

#: Wie in test_sprachlecks: Gesucht wird nicht nach deutschen Woertern.
EIN_WORT = re.compile(r"[A-Za-zÄÖÜäöüß]{3,}")

#: Englische Vorlagen, so wie die Oberflaeche sie baut (_modul_texte).
VALIDATOR_EN = {k: translate("en", "validator." + k) for k in dispatcher.MELDUNGEN}
FFPKG_EN = {k: translate("en", "ffpkgsupport." + k) for k in ffpkg_support.MELDUNGEN}

_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


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


# ---------------------------------------------------------------- die Validatoren

class DumpValidatorTests(unittest.TestCase):
    def test_fehlender_ordner(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "gibt_es_nicht")
            ergebnis = DumpValidator(texte=VALIDATOR_EN).validate(pfad)
        self.assertEqual("MISSING", ergebnis.status)
        self.assertEqual(["Folder not found: %s" % pfad], ergebnis.errors)

    def test_leerer_ordner(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            ergebnis = DumpValidator(texte=VALIDATOR_EN).validate(basis)
        self.assertIn("Required folder missing: sce_sys/", ergebnis.errors)
        self.assertIn("Critical file missing: eboot.bin", ergebnis.errors)
        self.assertIn("Recommended file missing: sce_sys/pfs-version.dat", ergebnis.errors)

    def test_ohne_texte_bleibt_die_vorgabe(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            ergebnis = DumpValidator().validate(basis)
        self.assertIn("Kritische Datei fehlt: eboot.bin", ergebnis.errors)


class ExfatValidatorTests(unittest.TestCase):
    def test_leere_datei(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "leer.exfat")
            open(pfad, "wb").close()
            ergebnis = ExtfatValidator(texte=VALIDATOR_EN).validate(pfad)
        self.assertEqual(["File is empty (0 bytes)."], ergebnis.errors)

    def test_kein_exfat(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "falsch.exfat")
            with open(pfad, "wb") as datei:
                datei.write(b"X" * 600)
            ergebnis = ExtfatValidator(texte=VALIDATOR_EN).validate(pfad)
        self.assertIn("No exFAT OEM name found (found: 'XXXXXXXX'). Possibly not an "
                      "exFAT container, or damaged.", ergebnis.errors)


class FfpkgValidatorTests(unittest.TestCase):
    def test_fehlendes_werkzeug(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            abbild = os.path.join(basis, "spiel.ffpkg")
            with open(abbild, "wb") as datei:
                datei.write(b"x")
            werkzeug = os.path.join(basis, "UFS2Tool.exe")
            ergebnis = FfpkgValidator(werkzeug, texte=VALIDATOR_EN).validate(abbild)
        self.assertEqual(["UFS2Tool not found: %s" % werkzeug], ergebnis.errors)

    def test_die_rechte_meldung_ohne_umschrift(self) -> None:
        self.assertNotIn("geprueft", FfpkgValidator.MELDUNGEN["ffpkg_rechte"])


class FfpfsValidatorTests(unittest.TestCase):
    def test_unbekannter_kopf(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "spiel.ffpfsc")
            with open(pfad, "wb") as datei:
                datei.write(struct.pack("<qq", 1, 2) + b"\0" * 64)
            ergebnis = FfpfsValidator(texte=VALIDATOR_EN).validate(pfad)
        self.assertIn("Unknown PFS header: version=0x0000000000000001, "
                      "magic=0x0000000000000002", ergebnis.errors)
        self.assertEqual("unknown (version=0x0000000000000001, magic=0x0000000000000002)",
                         ergebnis.summary["magic"])
        # Welchen Weg die Tiefenpruefung auch nahm - deutsch ist er nicht.
        self.assertNotRegex(str(ergebnis.summary.get("nesting", "")),
                            r"geprüft|prüfbar|Ordnung|aufgebaut|verschachtelt")
        self.assertFalse([e for e in ergebnis.errors if "Ebene" in e])

    def test_leere_datei(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "leer.ffpfs")
            open(pfad, "wb").close()
            ergebnis = FfpfsValidator(texte=VALIDATOR_EN).validate(pfad)
        self.assertEqual(["File is empty (0 bytes)."], ergebnis.errors)


class LesefehlerTests(unittest.TestCase):
    """hashing.sha256_stream: der Eintrag fuer einen Lesefehler."""

    class _Kaputt:
        def read(self, _anzahl):
            raise OSError("kaputt")

    def test_mit_vorlage(self) -> None:
        _summe, fehler = hashing.sha256_stream(
            self._Kaputt(), lesefehler=VALIDATOR_EN["lesefehler_byte"])
        self.assertEqual(["Read error at byte 0: kaputt"], fehler)

    def test_ohne_vorlage_wie_bisher(self) -> None:
        _summe, fehler = hashing.sha256_stream(self._Kaputt())
        self.assertEqual(["Lesefehler bei Byte 0: kaputt"], fehler)


class DispatcherTests(unittest.TestCase):
    def test_reicht_die_texte_durch(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "fehlt.bin")
            for modus in ("ffpfs", "extfat"):
                with self.subTest(modus=modus):
                    ergebnis = dispatcher.validate(pfad, modus, texte=VALIDATOR_EN)
                    self.assertEqual(["File not found: %s" % pfad], ergebnis.errors)

    def test_unbekannter_modus(self) -> None:
        ergebnis = dispatcher.validate("x", "xyz", texte=VALIDATOR_EN)
        self.assertTrue(ergebnis.errors[0].startswith("Unknown mode: 'xyz'."),
                        ergebnis.errors)

    def test_eine_kennung_eine_vorlage(self) -> None:
        """Die Oberflaeche kennt je Kennung nur einen Schluessel "validator.<k>"."""
        for klasse in (DumpValidator, FfpfsValidator, ExtfatValidator, FfpkgValidator):
            for kennung, vorlage in klasse.MELDUNGEN.items():
                with self.subTest(klasse=klasse.__name__, kennung=kennung):
                    self.assertEqual(vorlage, dispatcher.MELDUNGEN[kennung])


# ---------------------------------------------------------------- ffpkg_support (U4-8)

class FfpkgSupportTests(unittest.TestCase):
    def test_leerer_quellordner(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            with self.assertRaises(ValueError) as fall:
                ffpkg_support.validate_source_folder(basis, texte=FFPKG_EN)
        self.assertEqual("The FFPKG source folder contains no files.", str(fall.exception))

    def test_zu_viele_dateien(self) -> None:
        with self.assertRaises(ValueError) as fall:
            ffpkg_support.calculate_makefs_inode_density(8 * 1024 * 1024, 100000,
                                                         texte=FFPKG_EN)
        self.assertTrue(str(fall.exception).startswith("The FFPKG source has too many"),
                        str(fall.exception))

    def test_dateiname(self) -> None:
        with self.assertRaises(ValueError) as fall:
            ffpkg_support.normalize_output_path(".ffpkg", texte=FFPKG_EN)
        self.assertEqual("A valid FFPKG file name is required.", str(fall.exception))

    def test_der_kommandobauer_reicht_weiter(self) -> None:
        """build_makefs_command rechnet die Groesse selbst - mit denselben Texten."""
        with self.assertRaises(ValueError) as fall:
            ffpkg_support.build_makefs_command("UFS2Tool", "quelle", "ziel.ffpkg",
                                               source_size_bytes=0, file_count=1,
                                               texte=FFPKG_EN)
        self.assertEqual("The FFPKG source size must be greater than 0 bytes.",
                         str(fall.exception))

    def test_ohne_texte_bleibt_die_vorgabe(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            with self.assertRaises(ValueError) as fall:
                ffpkg_support.validate_source_folder(basis)
        self.assertEqual("Der FFPKG-Quellordner enthält keine Dateien.", str(fall.exception))


# ---------------------------------------------------------------- Struktur

class KeinFesterBefundTests(unittest.TestCase):
    """Kein fester Satz mehr in Befunden, Zusammenfassung und Ausnahmen."""

    MODULE = (
        "ps5_validator/modules/dump_validator.py",
        "ps5_validator/modules/extfat_validator.py",
        "ps5_validator/modules/ffpkg_validator.py",
        "ps5_validator/modules/ffpfs_validator.py",
        "ps5_validator/core/dispatcher.py",
        "ps5_validator/utils/ffpkg_support.py",
    )
    SCHREIBER = {"add_error", "set_failed", "set_corrupted", "set_missing", "set_skipped"}
    #: Variablen, deren Wert als Text in der Zusammenfassung landet.
    ANZEIGEWERTE = {"magic_info", "art", "ver_name"}
    #: Hier bleiben feste Saetze, begruendet: Die Profile stehen fest im
    #: Programm, die Pfade der Kommandobauer setzt es selbst - kein Anwender
    #: erreicht diese Waechter.
    ERLAUBT = {"normalized", "build_newfs_directory_command", "build_makefs_command",
               "build_readonly_validation_commands"}
    #: Ein einzelnes kleingeschriebenes Wort ist ein Merker (inner_kind =
    #: "exfat"), in jeder Sprache derselbe.
    MERKER = re.compile(r"^[a-z0-9_]+$")

    def test_nichts_festes_mehr(self) -> None:
        funde, gesehen = [], 0
        for rel in self.MODULE:
            baum = ast.parse((PROJEKT / rel).read_text(encoding="utf-8"))
            for funktion in ast.walk(baum):
                if not isinstance(funktion, ast.FunctionDef) or funktion.name in self.ERLAUBT:
                    continue
                for knoten in ast.walk(funktion):
                    ausdruecke: list = []
                    if (isinstance(knoten, ast.Call)
                            and getattr(knoten.func, "attr", "") in self.SCHREIBER):
                        ausdruecke = list(knoten.args)
                    elif isinstance(knoten, ast.Raise) and isinstance(knoten.exc, ast.Call):
                        ausdruecke = list(knoten.exc.args)
                    elif isinstance(knoten, ast.Assign):
                        for ziel in knoten.targets:
                            if ((isinstance(ziel, ast.Subscript)
                                 and getattr(ziel.value, "attr", "") == "summary")
                                    or getattr(ziel, "id", "") in self.ANZEIGEWERTE):
                                ausdruecke = [knoten.value]
                    for ausdruck in ausdruecke:
                        gesehen += 1
                        text = _fester_text(ausdruck)
                        if EIN_WORT.search(text) and not self.MERKER.match(text):
                            funde.append((rel, knoten.lineno, text))
        self.assertGreaterEqual(gesehen, 80, "Die Suche findet die Stellen nicht mehr.")
        self.assertEqual([], sorted(set(funde)))


# ---------------------------------------------------------------- Oberflaeche

class OberflaecheTests(unittest.TestCase):
    """Die Vorlagen kommen auch an - an jeder Stelle, die validiert."""

    def test_aufgabe_8(self) -> None:
        aufrufe = [k for k in ast.walk(_methode("_mode_dump_validator"))
                   if isinstance(k, ast.Call) and getattr(k.func, "id", "") == "_validate"]
        self.assertEqual(1, len(aufrufe))
        self.assertIn("texte", {w.arg for w in aufrufe[0].keywords})

    def test_der_pruefstand(self) -> None:
        aufruf = next(k for k in ast.walk(_methode("_pruefstand"))
                      if isinstance(k, ast.Call)
                      and getattr(k.func, "attr", "") == "Pruefstand")
        self.assertIn("validator_texte", {w.arg for w in aufruf.keywords})
        baum = ast.parse(Path(abbild_pruefen.__file__).read_text(encoding="utf-8"))
        aufrufe = [k for k in ast.walk(baum) if isinstance(k, ast.Call)
                   and getattr(k.func, "id", "") == "validate_ffpkg"]
        self.assertEqual(1, len(aufrufe))
        self.assertIn("texte", {w.arg for w in aufrufe[0].keywords})

    def test_jeder_ffpkg_support_aufruf(self) -> None:
        namen = {"validate_source_folder", "normalize_output_path",
                 "calculate_makefs_image_size", "calculate_makefs_inode_density",
                 "build_makefs_command"}
        aufrufe = [k for k in ast.walk(_baum()) if isinstance(k, ast.Call)
                   and getattr(k.func, "id", "") in namen]
        self.assertGreaterEqual(len(aufrufe), 5, "Die Suche findet die Aufrufe nicht mehr.")
        ohne = [(k.lineno, k.func.id) for k in aufrufe
                if "texte" not in {w.arg for w in k.keywords}]
        self.assertEqual([], ohne)

    def test_englische_vorlagen(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "en"
        texte = APP.PS5ConverterGUI._validator_texte(gui)
        self.assertEqual(set(dispatcher.MELDUNGEN), set(texte))
        self.assertEqual("File is empty (0 bytes).", texte["datei_leer"])
        ffpkg = APP.PS5ConverterGUI._ffpkg_support_texte(gui)
        self.assertEqual("The FFPKG source folder contains no files.", ffpkg["quellordner_leer"])


if __name__ == "__main__":
    unittest.main()
