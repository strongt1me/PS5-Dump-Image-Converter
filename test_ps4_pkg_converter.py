"""Tests für „PS4 PKG → ffpfsc" – das eingebettete PS4-FFPFSC 0.2.8.

Das Werkzeug wandelt PS4-PKG (Basis, Patch, wahlweise DLC) oder ein bereits
entpacktes PS4-Spiel in ein ShadowMountPlus-Abbild. Es liegt als Quellauszug
unter ``PS4FFPFSC-0.2.8/`` im Projekt; seine Qt-Oberfläche bleibt außen vor,
die Arbeit treibt ein eigenes Fenster über die Kommandozeile an.

Geprüft wird hier dreierlei:

  1. **Die Einbettung trägt** – Ordner gefunden, interne Modi verdrahtet,
     Menüeintrag und Texte vollständig.
  2. **Die beiden behobenen Fehler bleiben behoben.** Beide stammen aus der
     Vorlage und traten erst durch die Einbettung zutage:
     * ``doctor`` verlangte Compiler und CMake, obwohl der fertige Entpacker
       daneben liegt – und meldete deshalb immer „nicht bereit";
     * ``inspect`` mit Prüfsumme wertete den Rückgabewert des Entpackers nicht
       aus. Stürzt der ab (gemessen: Stapelüberlauf 0xC00000FD an mehreren
       PKG), kam „PKG nicht unterstützt" heraus – ein Fehler in der Datei
       also, wo einer im Werkzeug vorlag.
  3. **Der Schutz vor zu langen Arbeitspfaden** – der PKG-Entpacker bricht
     sonst mit „Failed to write extracted PKG entry" ab.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils.i18n import STRINGS

PS4_ORDNER = PROJEKT / hauptprogramm.PS4FFPFSC_ORDNER


class EinbettungTests(unittest.TestCase):
    """Der Quellauszug muss vollständig und auffindbar sein."""

    def test_ordner_wird_gefunden(self) -> None:
        self.assertTrue(hauptprogramm._ps4ffpsc_wurzel(), "PS4-Ordner nicht gefunden")

    def test_arbeitsteile_sind_da(self) -> None:
        for rel in ("ps4ffpsc/cli.py", "ps4ffpsc/pipeline.py", "ps4ffpsc/inventory.py",
                    "mkpfs_1_0_0/mkpfs/__init__.py", "UPSTREAM.md", "LICENSE"):
            with self.subTest(datei=rel):
                self.assertTrue((PS4_ORDNER / rel).is_file(), f"{rel} fehlt")

    def test_qt_oberflaeche_ist_nicht_dabei(self) -> None:
        """PySide6 wird nicht gebraucht - die Oberfläche stellt dieses Programm."""
        for rel in ("ps4ffpsc/gui.py", "ps4ffpsc/gui_model.py"):
            with self.subTest(datei=rel):
                self.assertFalse((PS4_ORDNER / rel).exists(), f"{rel} sollte fehlen")

    def test_mkpfs_liegt_ausserhalb_des_suchmusters(self) -> None:
        """Sonst greift der Validator zur falschen Engine.

        Das Programm und ``ffpfs_validator._ensure_mkpfs_importable`` suchen
        ihre eigene Fassung über ``MkPFS-*`` im Projektstamm. Läge die 1.0.0
        des PS4-Werkzeugs dort, gewänne sie die Sortierung.
        """
        treffer = sorted(p.name for p in PROJEKT.glob("MkPFS-*") if p.is_dir())
        self.assertEqual(treffer, [f"MkPFS-{hauptprogramm.MKPFS_REQUIRED_VERSION}"])

    def test_menueeintrag_und_methode(self) -> None:
        eintraege = dict(PS5ConverterGUI._MORE_TOOLS_ENTRIES)
        self.assertIn("titlebar.ps4pkg", eintraege)
        self.assertEqual(eintraege["titlebar.ps4pkg"], "_show_ps4_pkg_converter")
        self.assertTrue(callable(getattr(PS5ConverterGUI, "_show_ps4_pkg_converter", None)))

    def test_texte_sind_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS if k.startswith("ps4pkg.")]
        self.assertGreaterEqual(len(schluessel), 20)
        for name in [*schluessel, "titlebar.ps4pkg"]:
            with self.subTest(schluessel=name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))


class InterneModiTests(unittest.TestCase):
    """Die beiden Schalter, über die das Werkzeug angetrieben wird."""

    def _aufruf(self, *argumente: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"), *argumente],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
        )

    def test_mkpfs_modus_startet_die_geprüfte_fassung(self) -> None:
        """--ps4-mkpfs muss 1.0.0 liefern, nicht die 0.0.9 des Programms."""
        ergebnis = self._aufruf("--ps4-mkpfs", "-V")
        self.assertEqual(ergebnis.returncode, 0, ergebnis.stderr[-400:])
        self.assertIn("1.0.0", ergebnis.stdout + ergebnis.stderr)

    def test_doctor_meldet_bereit(self) -> None:
        """Der erste behobene Fehler: doctor verlangte einen Compiler.

        Die Vorlage koppelte Compiler-, CMake- und Quelltextprüfung an
        ``is_frozen()``. Aus der Quelle heraus – also genau hier – meldete sie
        deshalb „nicht bereit", obwohl der fertige Entpacker danebenliegt.
        """
        ergebnis = self._aufruf("--ps4ffpsc", "doctor", "--json")
        daten = json.loads(ergebnis.stdout)
        pruefungen = daten["checks"]
        self.assertTrue(pruefungen["extractor"]["ok"], "Entpacker nicht gefunden")
        self.assertTrue(pruefungen["mkpfs"]["ok"], pruefungen["mkpfs"])
        self.assertFalse(pruefungen["compiler"]["required"],
                         "Mit fertigem Entpacker darf kein Compiler verlangt werden")
        self.assertFalse(pruefungen["cmake"]["required"])
        self.assertTrue(pruefungen["shadps4_source"]["ok"])
        self.assertTrue(daten["ok"], daten)


class InspectAbsturzTests(unittest.TestCase):
    """Der zweite behobene Fehler: ein Absturz galt als „PKG nicht unterstützt".

    Statt eines echten PKG tritt hier ein Ersatz-Entpacker an, der den
    gemessenen Fall nachstellt: Mit Prüfsummenlauf bricht er ohne Ausgabe ab,
    mit ``--fast`` liefert er JSON. So ist der Test unabhängig davon, welche
    PKG auf dem Rechner liegen.
    """

    def setUp(self) -> None:
        if str(PS4_ORDNER) not in sys.path:
            sys.path.insert(0, str(PS4_ORDNER))
        self._tmp = TemporaryDirectory(prefix="ps4_inspect_")
        self.basis = Path(self._tmp.name)
        self.paket = self.basis / "spiel.pkg"
        self.paket.write_bytes(b"\x7fCNT" + os.urandom(4096))
        self.extractor = self.basis / "extractor.py"
        self.extractor.write_text(
            "import json, sys\n"
            "if '--fast' not in sys.argv:\n"
            "    sys.exit(3221225725)\n"
            "print(json.dumps({'path': sys.argv[2], 'supported': True,\n"
            "                  'title_id': 'CUSA00001', 'title': 'Test',\n"
            "                  'kind': 'base', 'sha256': None}))\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _inspizieren(self, compute_sha256: bool):
        from ps4ffpsc.inventory import inspect_package  # noqa: PLC0415

        # Der Ersatz-Entpacker ist ein Python-Skript; ein Startskript daneben
        # macht daraus einen aufrufbaren "Entpacker".
        starter = self.basis / ("start.cmd" if os.name == "nt" else "start.sh")
        if os.name == "nt":
            starter.write_text(f'@"{sys.executable}" "{self.extractor}" %*\n', encoding="utf-8")
        else:
            starter.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{self.extractor}" "$@"\n',
                               encoding="utf-8")
            starter.chmod(0o755)
        return inspect_package(starter, self.paket, compute_sha256=compute_sha256)

    def test_absturz_gilt_nicht_mehr_als_nicht_unterstuetzt(self) -> None:
        befund = self._inspizieren(compute_sha256=True)
        self.assertTrue(befund.get("supported"),
                        f"Absturz wurde wieder als Dateifehler gedeutet: {befund}")
        self.assertEqual(befund.get("title_id"), "CUSA00001")

    def test_pruefsumme_wird_nachgerechnet(self) -> None:
        """Weicht der Aufruf auf --fast aus, rechnet Python die Summe nach."""
        import hashlib  # noqa: PLC0415

        befund = self._inspizieren(compute_sha256=True)
        erwartet = hashlib.sha256(self.paket.read_bytes()).hexdigest()
        self.assertEqual(befund.get("sha256"), erwartet)

    def test_ohne_pruefsumme_bleibt_es_beim_schnellen_weg(self) -> None:
        befund = self._inspizieren(compute_sha256=False)
        self.assertTrue(befund.get("supported"))
        self.assertIsNone(befund.get("sha256"))


class PlattformTests(unittest.TestCase):
    """Nur wo ein lauffaehiger Entpacker liegt, darf das Fenster oeffnen.

    Fertige Programmdateien gibt es beim Hersteller nur fuer Windows x64 und
    macOS ARM64. Beide Saetze liegen zusammen in ``bin/``: ``*.exe`` fuer
    Windows, endungslos fuer Apple Silicon. Eine Suche allein ueber den
    Dateinamen fand unter Linux die Mach-O-Datei und hielt sie fuer brauchbar -
    ausfuehren laesst sie sich dort nicht ("Exec format error").
    """

    def test_beide_saetze_liegen_bei(self) -> None:
        for name in ("ps4_pkg_extract.exe", "ps4-dlc-patch.exe",
                     "ps4_pkg_extract", "ps4-dlc-patch"):
            with self.subTest(datei=name):
                self.assertTrue((PS4_ORDNER / "bin" / name).is_file(), f"{name} fehlt")

    def test_windows_nimmt_die_exe(self) -> None:
        if not hauptprogramm.IST_WINDOWS:
            self.skipTest("nur unter Windows aussagekraeftig")
        self.assertTrue(hauptprogramm._ps4ffpsc_entpacker().endswith("ps4_pkg_extract.exe"))

    def test_fremde_plattform_meldet_keinen_entpacker(self) -> None:
        """Linux und Intel-Macs duerfen die Mach-O-Datei nicht annehmen."""
        import platform as _platform  # noqa: PLC0415

        merker = (hauptprogramm.IST_WINDOWS, sys.platform, _platform.machine)
        try:
            hauptprogramm.IST_WINDOWS = False
            sys.platform = "linux"
            self.assertEqual(hauptprogramm._ps4ffpsc_entpacker(), "")
            sys.platform = "darwin"
            _platform.machine = lambda: "x86_64"
            self.assertEqual(hauptprogramm._ps4ffpsc_entpacker(), "")
            _platform.machine = lambda: "arm64"
            self.assertTrue(hauptprogramm._ps4ffpsc_entpacker().endswith("ps4_pkg_extract"))
        finally:
            hauptprogramm.IST_WINDOWS, sys.platform, _platform.machine = merker


class LangePfadeTests(unittest.TestCase):
    """Der Arbeitsordner darf den Entpacker nicht an die Pfadgrenze treiben."""

    def test_grenze_ist_gesetzt_und_konservativ(self) -> None:
        grenze = hauptprogramm._PS4FFPSC_MAX_ARBEITSPFAD
        self.assertIsInstance(grenze, int)
        # Unter dem Arbeitsordner entstehen noch rund 100 Zeichen
        # (unpacked/<Title-ID>/<Paket>/sce_sys/...), Windows endet bei 260.
        self.assertLessEqual(grenze, 150)
        self.assertGreaterEqual(grenze, 60)

    def test_hinweistext_nennt_laenge_und_ausweichpfad(self) -> None:
        from ps5_validator.utils.i18n import translate  # noqa: PLC0415

        text = translate("de", "ps4pkg.short_workdir", laenge=180, pfad=r"C:\ps4ffpsc_arbeit")
        self.assertIn("180", text)
        self.assertIn("ps4ffpsc_arbeit", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
