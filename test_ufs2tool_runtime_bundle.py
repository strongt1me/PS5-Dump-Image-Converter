# -*- coding: utf-8 -*-
"""Tests für die mitgelieferte UFS2Tool-Laufzeit.

Bis v1.8.71 lag nur ein Windows-Bau bei, als Base64 in ``ps5_ufs2tool_data.py``.
Der war **framework-abhängig**: Seine ``runtimeconfig.json`` verlangte
``Microsoft.NETCore.App 8.0.0``. Auf einem Rechner ohne installiertes .NET 8
scheiterte ``.ffpkg`` deshalb, ohne dass irgendetwas den Grund nannte – auf dem
Entwicklungsrechner fiel es nie auf, weil dort .NET liegt.

Seit v1.8.72 liegt in ``UFS2Tool-4.1/`` für jede Plattform ein **eigenständiger**
Bau: getrimmt, als eine Datei, ohne Globalisierung. Letzteres ist kein Detail –
mit Globalisierung verlangt der Start unter Linux ``libicu`` und bricht sonst mit
„Couldn't find a valid ICU package" ab.

Das Werkzeug selbst konnte immer schon mehr, als wir zugelassen haben: Sein
README nennt Windows, macOS und Linux, und alle Abbild-Operationen (``newfs``,
``makefs``, ``extract``, ``info``, ``fsck_ufs``) arbeiten auf Dateien. Nur
``mount_udf`` braucht den Dokan-Treiber und bleibt Windows vorbehalten.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

ORDNER = PROJEKT / hauptprogramm.UFS2TOOL_ORDNER

#: Was mitgeliefert sein muss, und wie die Datei dort heißt.
ERWARTET = {
    "win-x64": "UFS2Tool.exe",
    "linux-x64": "UFS2Tool",
    "osx-x64": "UFS2Tool",
    "osx-arm64": "UFS2Tool",
}


class BestandTests(unittest.TestCase):
    """Der Ordner muss vollständig sein."""

    def test_ordner_ist_da(self) -> None:
        self.assertTrue(ORDNER.is_dir(), f"{ORDNER} fehlt")

    def test_jede_plattform_hat_ihren_bau(self) -> None:
        for kennung, datei in ERWARTET.items():
            with self.subTest(plattform=kennung):
                pfad = ORDNER / kennung / datei
                self.assertTrue(pfad.is_file(), f"{pfad} fehlt")
                self.assertGreater(pfad.stat().st_size, 5 * 1024 * 1024,
                                   "zu klein für einen eigenständigen Bau")

    def test_lizenz_liegt_bei(self) -> None:
        """BSD-2-Clause verlangt die Weitergabe des Lizenztextes."""
        lizenz = ORDNER / "LICENSE"
        self.assertTrue(lizenz.is_file())
        self.assertIn("BSD 2-Clause", lizenz.read_text(encoding="utf-8",
                                                       errors="replace"))

    def test_keine_framework_abhaengigkeit_mehr(self) -> None:
        """Eine runtimeconfig.json wäre das Kennzeichen des alten Baus.

        Ein eigenständiger Einzeldatei-Bau bringt sie nicht mit; läge sie hier,
        wäre wieder ein .NET 8 auf dem Zielrechner nötig.
        """
        for uebrig in ORDNER.rglob("*.runtimeconfig.json"):
            self.fail(f"framework-abhängiger Bau: {uebrig}")

    def test_alte_base64_einbettung_ist_weg(self) -> None:
        """714 KB toter Base64-Text, den niemand mehr liest."""
        self.assertFalse((PROJEKT / "ps5_ufs2tool_data.py").exists(),
                         "ps5_ufs2tool_data.py wird nicht mehr verwendet")


class PruefsummenTests(unittest.TestCase):
    """Die Liste muss zu den Dateien passen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.liste = ORDNER / "pruefsummen.json"
        cls.daten = json.loads(cls.liste.read_text(encoding="utf-8"))

    def test_liste_nennt_fassung_und_herkunft(self) -> None:
        self.assertEqual("4.1.0", self.daten.get("fassung"))
        self.assertIn("SvenGDK/UFS2Tool", self.daten.get("herkunft", ""))
        self.assertEqual("BSD-2-Clause", self.daten.get("lizenz"))

    def test_bauweise_ist_festgehalten(self) -> None:
        """Ohne diese Zeile ließe sich der Bau nicht nachvollziehen."""
        befehl = self.daten.get("gebaut_mit", "")
        for schalter in ("--self-contained true", "PublishTrimmed",
                         "PublishSingleFile", "InvariantGlobalization"):
            with self.subTest(schalter=schalter):
                self.assertIn(schalter, befehl)

    def test_jede_pruefsumme_stimmt(self) -> None:
        for kennung, datei in ERWARTET.items():
            with self.subTest(plattform=kennung):
                eintrag = (self.daten.get("plattformen") or {}).get(kennung)
                self.assertIsNotNone(eintrag, f"{kennung} fehlt in der Liste")
                roh = (ORDNER / kennung / datei).read_bytes()
                self.assertEqual(eintrag["sha256"], hashlib.sha256(roh).hexdigest())
                self.assertEqual(eintrag["bytes"], len(roh))


class PlattformwahlTests(unittest.TestCase):
    """Welcher Bau für welches System genommen wird."""

    def test_wahl_trifft_die_laufende_plattform(self) -> None:
        kennung = PS5ConverterGUI._ufs2tool_plattform()
        self.assertIn(kennung, ERWARTET, "kein Bau für diese Plattform")
        self.assertTrue((ORDNER / kennung / ERWARTET[kennung]).is_file())

    def test_verfaelschte_datei_wird_abgelehnt(self) -> None:
        """Eine falsche Prüfsumme darf nie bis zum Aufruf durchkommen."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            wurzel = Path(tmp)
            (wurzel / "win-x64").mkdir()
            gefaelscht = wurzel / "win-x64" / "UFS2Tool.exe"
            gefaelscht.write_bytes(b"nicht das echte Werkzeug")
            (wurzel / "pruefsummen.json").write_text(json.dumps({
                "plattformen": {"win-x64": {"sha256": "0" * 64}},
            }), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                PS5ConverterGUI._ufs2tool_pruefsumme(
                    str(wurzel), "win-x64", str(gefaelscht))

    def test_fehlende_liste_blockiert_nicht(self) -> None:
        """Ein fehlender Prüfwert ist kein Grund, das Werkzeug abzulehnen."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            datei = Path(tmp) / "UFS2Tool.exe"
            datei.write_bytes(b"x")
            PS5ConverterGUI._ufs2tool_pruefsumme(tmp, "win-x64", str(datei))


class PlattformfreigabeTests(unittest.TestCase):
    """Was das Programm noch auf Windows beschränkt – und was nicht mehr."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def test_ufs2tool_gilt_nicht_mehr_als_windows_werkzeug(self) -> None:
        from ps5_validator.utils import plattform

        self.assertNotIn("UFS2Tool", plattform.NUR_WINDOWS_WERKZEUGE)
        self.assertIn("Dokan", plattform.NUR_WINDOWS_WERKZEUGE,
                      "das Einhängen als Laufwerk bleibt Windows")

    def test_bauen_bricht_nicht_mehr_an_der_plattform_ab(self) -> None:
        """newfs und makefs schreiben eine Datei – sie hängen nichts ein."""
        self.assertNotIn("log.manual.ffpkg_build_windows_only", self.quelle)

    def test_rechtepruefung_bleibt_windows(self) -> None:
        """Nur dort verlangt das Programmmanifest die Erhöhung."""
        self.assertIn("if IST_WINDOWS and not _is_admin():", self.quelle)

    def test_entpacken_hat_einen_weg_ohne_dokan(self) -> None:
        self.assertIn("_ffpkg_ueber_unterbefehl_entpacken", self.quelle)
        anfang = self.quelle.index("def _ffpkg_ueber_unterbefehl_entpacken")
        rumpf = self.quelle[anfang:self.quelle.index("\n    def ", anfang + 10)]
        # Reihenfolge laut README: extract <abbild> <ausgabeordner>
        self.assertIn('"extract", src, dest_folder', rumpf)
        self.assertNotIn("mount_udf", rumpf)
        # Rückgabe 0 auf einem leeren Ordner ist kein Erfolg.
        self.assertIn("ffpkg.extract_empty", rumpf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
