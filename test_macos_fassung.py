"""Tests fuer die macOS-Fassung.

Geprueft wird, was sich ohne einen Mac pruefen laesst - und das ist mehr, als es
zunaechst aussieht:

1. **Plattformschicht.** ``ps5_validator/utils/plattform.py`` legt seine
   Konstanten beim Import fest. Der Test laedt das Modul deshalb ein zweites
   Mal unter eigenem Namen und mit ``sys.platform = "darwin"``, statt das
   bereits geladene umzubiegen. So bleiben die macOS-Zweige pruefbar, ohne dass
   der Rest der Testsitzung ein verbogenes Modul erbt.
2. **Bauvorschrift.** Die .spec-Datei ist Python und laesst sich damit
   einlesen, ohne PyInstaller zu starten. Zusaetzlich wird sie gegen die
   Linux-Fassung gehalten: Die beiden Listen versteckter Importe duerfen nicht
   auseinanderlaufen, sonst faellt ein Modul erst auf einem der beiden Systeme
   zur Laufzeit aus.
3. **Skripte.** Zeilenenden und Shell-Syntax. Ein einziges CRLF im Skript
   quittiert macOS mit ``bad interpreter: /usr/bin/env bash^M`` - ein Fehler,
   der auf dem Windows-Rechner, auf dem die Datei entsteht, unsichtbar ist.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

SPEC_MACOS = PROJEKT / "PS5ImageConverter_Pro_macos.spec"
SPEC_LINUX = PROJEKT / "PS5ImageConverter_Pro_linux.spec"
SKRIPTE = ("Build_macOS.sh", "Install_macOS.sh")


def _spec_lesen(pfad: Path) -> ast.Module:
    return ast.parse(pfad.read_text(encoding="utf-8"))


def _schluesselwort(baum: ast.Module, aufruf: str, name: str) -> ast.expr | None:
    """Wert eines Schluesselwortarguments aus einem Aufruf der .spec-Datei."""
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        ziel = knoten.func
        if not (isinstance(ziel, ast.Name) and ziel.id == aufruf):
            continue
        for arg in knoten.keywords:
            if arg.arg == name:
                return arg.value
    return None


class BauvorschriftTests(unittest.TestCase):
    """Die .spec-Datei fuer macOS."""

    @classmethod
    def setUpClass(cls):
        cls.baum = _spec_lesen(SPEC_MACOS)
        cls.quelle = SPEC_MACOS.read_text(encoding="utf-8")

    def test_vorhanden_und_lesbar(self):
        self.assertTrue(SPEC_MACOS.is_file())

    def test_erzeugt_ein_buendel(self):
        # Ohne BUNDLE gaebe es nur einen Ordner voller Dateien: kein Symbol im
        # Dock, kein Name in der Menueleiste, keine Info.plist.
        namen = {k.func.id for k in ast.walk(self.baum)
                 if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)}
        for pflicht in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE"):
            self.assertIn(pflicht, namen, f"{pflicht}() fehlt in der macOS-.spec")

    def test_exe_liefert_die_bibliotheken_ans_buendel(self):
        # exclude_binaries=True ist die Bedingung dafuer, dass COLLECT die
        # Bibliotheken neben das Programm legen kann.
        wert = _schluesselwort(self.baum, "EXE", "exclude_binaries")
        self.assertIsInstance(wert, ast.Constant)
        self.assertTrue(wert.value)

    def test_kein_argv_emulation(self):
        # argv_emulation faengt Apple-Events mit einer eigenen Ereignisschleife
        # ab, bevor Tk seine eigene startet - das Fenster bleibt danach bis zum
        # ersten Klick taub.
        wert = _schluesselwort(self.baum, "EXE", "argv_emulation")
        self.assertIsInstance(wert, ast.Constant)
        self.assertFalse(wert.value)

    def test_info_plist_deckt_die_darstellung_ab(self):
        for eintrag in ("NSHighResolutionCapable", "NSRequiresAquaSystemAppearance",
                        "CFBundleShortVersionString", "LSMinimumSystemVersion",
                        "CFBundleDisplayName"):
            self.assertIn(eintrag, self.quelle, f"{eintrag} fehlt in der Info.plist")

    def test_version_ohne_fuehrendes_v(self):
        # CFBundleShortVersionString erlaubt nur Ziffern und Punkte.
        self.assertIn("lstrip('vV')", self.quelle)

    def test_symbol_ist_icns(self):
        self.assertIn("app_icon.icns", self.quelle)
        self.assertNotIn("icon='app_icon.ico'", self.quelle)

    def test_windows_nutzlast_ausgeschlossen(self):
        """Seit v1.8.72 gibt es das alte Windows-Modul nicht mehr.

        UFS2Tool liegt stattdessen als eigenstaendiger Bau je Plattform bei -
        das macOS-Buendel nimmt nur die beiden Apple-Fassungen mit, nicht die
        Windows-Datei.
        """
        self.assertNotIn("ps5_ufs2tool_data", self.quelle)
        self.assertIn("osx-arm64", self.quelle)
        self.assertIn("osx-x64", self.quelle)
        self.assertNotIn("'win-x64'", self.quelle)

    def test_versteckte_importe_wie_unter_linux(self):
        """Beide Fassungen muessen dieselben Module kennen.

        Laufen die Listen auseinander, faellt das erst zur Laufzeit auf - und
        zwar nur auf einem der beiden Systeme, was die Suche unnoetig teuer
        macht.
        """
        def importe(pfad: Path) -> set[str]:
            wert = _schluesselwort(_spec_lesen(pfad), "Analysis", "hiddenimports")
            self.assertIsInstance(wert, ast.List, f"hiddenimports fehlt in {pfad.name}")
            return {e.value for e in wert.elts if isinstance(e, ast.Constant)}

        macos, linux = importe(SPEC_MACOS), importe(SPEC_LINUX)
        self.assertEqual(macos - linux, set(), "nur in der macOS-.spec")
        self.assertEqual(linux - macos, set(), "fehlt in der macOS-.spec")

    def test_pil_tkinter_bruecke_gebuendelt(self):
        # Ohne diesen Eintrag baut das Programm anstandslos und stuerzt beim
        # ersten Bild im Fenster ab. Unter Linux hat genau das einen Anlauf
        # gekostet.
        self.assertIn("'PIL._tkinter_finder',", self.quelle)


class SpecAusfuehrungTests(unittest.TestCase):
    """Die .spec einmal wirklich ausfuehren - mit Attrappen statt PyInstaller.

    Die reine Syntaxpruefung sieht nicht, ob ein eingebetteter Ordner falsch
    geschrieben ist: ``glob``/``os.path.isfile`` schlucken jeden Tippfehler
    stillschweigend, die Datei fehlt dann einfach im fertigen Buendel. Hier
    laeuft die Datei mit denselben Attrappen fuer ``Analysis`` und Freunde
    durch, die PyInstaller sonst stellt - danach lassen sich die
    zusammengebauten Listen einzeln nachsehen.
    """

    @classmethod
    def setUpClass(cls):
        cls.aufrufe = cls._ausfuehren(SPEC_MACOS)

    @staticmethod
    def _ausfuehren(pfad: Path) -> dict[str, list[tuple]]:
        aufrufe: dict[str, list[tuple]] = {}

        class Ergebnis:
            """Steht fuer 'a', 'pyz', 'coll' - liefert jedes Attribut."""

            def __getattr__(self, name):
                return f"<{name}>"

        class Attrappe:
            def __init__(self, name):
                self.name = name

            def __call__(self, *args, **kwargs):
                aufrufe.setdefault(self.name, []).append((args, kwargs))
                return Ergebnis()

        namensraum = {
            "SPEC": str(pfad),
            "__file__": str(pfad),
            "Analysis": Attrappe("Analysis"),
            "PYZ": Attrappe("PYZ"),
            "EXE": Attrappe("EXE"),
            "COLLECT": Attrappe("COLLECT"),
            "BUNDLE": Attrappe("BUNDLE"),
        }
        exec(compile(pfad.read_text(encoding="utf-8"), str(pfad), "exec"), namensraum)
        return aufrufe

    def _kwargs(self, aufruf: str) -> dict:
        self.assertIn(aufruf, self.aufrufe, f"{aufruf}() wurde nicht aufgerufen")
        return self.aufrufe[aufruf][0][1]

    def test_laeuft_ohne_fehler_durch(self):
        for name in ("Analysis", "PYZ", "EXE", "COLLECT", "BUNDLE"):
            self.assertIn(name, self.aufrufe)

    def test_eingebettete_dateien_existieren(self):
        """Jeder Quellpfad in datas muss auf dem Datentraeger liegen.

        Die .spec prueft das selbst mit isfile/isdir - genau deshalb faellt ein
        Tippfehler dort nicht auf, sondern fuehrt nur dazu, dass der Eintrag
        stillschweigend wegbleibt. Hier wird umgekehrt geprueft: Was drinsteht,
        muss es auch geben.
        """
        datas = self._kwargs("Analysis")["datas"]
        self.assertTrue(datas, "datas ist leer")
        for quelle, _ziel in datas:
            with self.subTest(quelle=quelle):
                self.assertTrue(os.path.exists(quelle), f"{quelle} gibt es nicht")

    def test_pflichtdateien_im_buendel(self):
        # Ein Eintrag zaehlt, wenn er auf der Quellseite so heisst (Einzeldatei
        # oder ganzer Ordner) oder auf der Zielseite dort landet. Ordner mit
        # Python-Quellen kommen Datei fuer Datei ins Buendel, damit __pycache__
        # draussen bleibt - dort steht der Ordnername nur noch auf der Zielseite.
        datas = self._kwargs("Analysis")["datas"]
        ziele = {os.path.basename(q) for q, _z in datas}
        ziele |= {Path(z).as_posix().split("/")[0] for _q, z in datas}
        for pflicht in ("app_icon.ico", "helloworld", "MkPFS-1.0.0",
                        "Hintergrundbilder", "BENUTZERHANDBUCH.html",
                        "THIRD_PARTY_LICENSES.md", "Backport_Fakelibs"):
            self.assertIn(pflicht, ziele, f"{pflicht} wird nicht eingebettet")

    def test_ampr_ordner_wird_eingebettet(self):
        """Der AMPR-/PlayGo-Ordner steckt im Buendel, nicht daneben.

        Zwischen v1.8.94 und v1.8.95 lag er daneben, damit sich eine neue
        AMPR-Fassung hineinlegen laesst, ohne neu zu bauen. Auf macOS war das
        besonders unerfreulich: Ein ``.app``-Buendel versiegelt
        ``Contents/MacOS`` nicht - dort erwartet das System ausschliesslich
        ausfuehrbaren Code -, und der CI-Lauf brach mit ``a sealed resource is
        missing or invalid`` ab. Auf Apple Silicon startet ein Buendel mit
        ungueltiger Signatur gar nicht.

        Eingebettet stellt sich die Frage nach dem Ort nicht mehr.
        """
        ziele = {os.path.basename(q) for q, _z in self._kwargs("Analysis")["datas"]}
        self.assertIn("PlayGo & AMPR_EMU", ziele,
                      "Der Ordner wird nicht eingebettet")

    def test_das_bauskript_legt_ihn_nicht_mehr_ins_buendel(self):
        """Sonst laegen dieselben 3 MB zweimal im .app - und der Ordner in
        Contents/MacOS wuerde zusaetzlich die Signatur brechen."""
        skript = (Path(__file__).resolve().parent / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertNotIn('cp -r "PlayGo & AMPR_EMU" "$BUENDEL', skript)

    def test_im_buendel_wird_nichts_geloescht(self):
        """Der teuerste Fehler dieser Aenderung - gemessen im CI-Lauf.

        Der erste Anlauf raeumte im Buendel "Reste aus dem Bau von v1.8.94"
        weg, aus ``Contents/MacOS`` und ``Contents/Resources``. Der Lauf auf
        echter Apple-Hardware brach ab::

            WARNUNG: Signatur gesetzt, Pruefung meldet Beanstandungen
            dist/PS5 Dump & Image Converter.app: No such file or directory

        PyInstaller legt eingebettete Daten im ``.app`` genau nach
        ``Contents/Resources`` und verknuepft sie von anderer Stelle. Die
        Aufraeumzeile loeschte also den frisch eingebetteten AMPR-Ordner und
        liess tote Verweise zurueck - die Mac-Fassung haette ueberhaupt keine
        AMPR-Versionen mehr gehabt.

        Reste kann es hier nicht geben: Das Buendel entsteht bei jedem Lauf
        neu.
        """
        skript = (Path(__file__).resolve().parent / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertNotIn('rm -rf "$BUENDEL/Contents/Resources/PlayGo & AMPR_EMU"',
                         skript)
        self.assertNotIn('rm -rf "$BUENDEL/Contents/MacOS/PlayGo & AMPR_EMU"',
                         skript)

    def test_im_buendel_wird_ueberhaupt_nichts_geloescht(self):
        """Weiter gefasst: kein ``rm`` auf einen Pfad im Buendel.

        Der Fall oben war eine bestimmte Zeile; die Regel dahinter ist
        allgemeiner. Was PyInstaller ins Buendel legt, gehoert dorthin - und
        was danach fehlt, macht die Signatur ungueltig.
        """
        skript = (Path(__file__).resolve().parent / "Build_macOS.sh").read_text(encoding="utf-8")
        for nummer, zeile in enumerate(skript.split("\n"), 1):
            nackt = zeile.strip()
            if nackt.startswith("#") or not nackt:
                continue
            if nackt.startswith(("rm -rf", "rm -f", "rm ")) and "$BUENDEL" in nackt:
                self.fail("Zeile %d loescht im Buendel: %s" % (nummer, nackt))

    def test_das_programm_sieht_auch_in_contents_resources_nach(self):
        """Bleibt als Rueckfallweg bestehen.

        Gebraucht wird er derzeit nicht - eingebettete Daten findet
        ``_MEIPASS`` zuerst. Er kostet nichts und ist die richtige Antwort,
        falls je wieder etwas neben das Programm gelegt wird: ``Contents/MacOS``
        waere dafuer der falsche Ort, weil es beim Signieren nicht versiegelt
        wird (CI-Lauf vom 25.08.2026).
        """
        quelle = (Path(__file__).resolve().parent
                  / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        anfang = quelle.index("def _mitgeliefert_finden")
        koerper = quelle[anfang:anfang + 2600]
        self.assertIn('"Resources"', koerper)
        self.assertIn('sys.platform == "darwin"', koerper)
        self.assertIn('"MacOS"', koerper)

    def test_der_suchpfad_greift_nur_im_buendel(self):
        """Ausserhalb eines .app-Buendels darf sich nichts aendern."""
        quelle = (Path(__file__).resolve().parent
                  / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        anfang = quelle.index("def _mitgeliefert_finden")
        koerper = quelle[anfang:anfang + 2600]
        self.assertIn('os.path.basename(neben) == "MacOS"', koerper)

    def test_symbol_zeigt_auf_eine_vorhandene_datei(self):
        for aufruf in ("EXE", "BUNDLE"):
            with self.subTest(aufruf=aufruf):
                symbol = self._kwargs(aufruf).get("icon")
                self.assertIsNotNone(symbol, f"{aufruf}() ohne icon=")
                self.assertTrue(str(symbol).endswith("app_icon.icns"))
                self.assertTrue(os.path.isfile(str(symbol)))

    def test_buendelname_und_ordnername(self):
        buendel = self._kwargs("BUNDLE")["name"]
        self.assertTrue(buendel.endswith(".app"), buendel)
        # Der Name im Programme-Ordner traegt bewusst keine Version: Eine neue
        # Fassung soll die alte ersetzen, nicht danebenliegen.
        self.assertNotIn("v1.", buendel)

        ordner = self._kwargs("COLLECT")["name"]
        self.assertIn("macos", ordner)
        # Der Zwischenordner dagegen schon - damit sich Baustaende nicht
        # gegenseitig ueberschreiben.
        self.assertRegex(ordner, r"v\d+\.\d+")

    def test_info_plist_werte(self):
        plist = self._kwargs("BUNDLE")["info_plist"]
        self.assertIsInstance(plist, dict)
        self.assertIs(plist["NSHighResolutionCapable"], True)
        self.assertIs(plist["NSRequiresAquaSystemAppearance"], False)
        # CFBundleShortVersionString erlaubt nur Ziffern und Punkte.
        self.assertRegex(plist["CFBundleShortVersionString"], r"^\d+(\.\d+)*$")
        self.assertEqual(plist["CFBundleExecutable"], "PS5_Dump_Image_Converter")

    def test_kennung_des_buendels(self):
        kennung = self._kwargs("BUNDLE")["bundle_identifier"]
        # Umgekehrte Domain, kleingeschrieben - macOS verlangt das Format.
        self.assertRegex(kennung, r"^[a-z0-9.-]+$")
        self.assertGreaterEqual(kennung.count("."), 2)


class SkriptTests(unittest.TestCase):
    """Bau- und Installationsskript."""

    def test_vorhanden(self):
        for name in SKRIPTE:
            self.assertTrue((PROJEKT / name).is_file(), f"{name} fehlt")

    def test_zeilenenden_sind_lf(self):
        # Der Rest des Projekts ist CRLF. Ein CRLF im Shell-Skript quittiert
        # macOS mit "bad interpreter: /usr/bin/env bash^M".
        for name in SKRIPTE:
            with self.subTest(skript=name):
                roh = (PROJEKT / name).read_bytes()
                self.assertNotIn(b"\r", roh, f"{name} enthaelt CRLF")

    def test_shebang(self):
        for name in SKRIPTE:
            with self.subTest(skript=name):
                erste = (PROJEKT / name).read_bytes().split(b"\n", 1)[0]
                self.assertEqual(erste, b"#!/usr/bin/env bash")

    @unittest.skipUnless(shutil.which("bash"), "bash nicht verfuegbar")
    def test_shell_syntax(self):
        for name in SKRIPTE:
            with self.subTest(skript=name):
                ergebnis = subprocess.run(
                    [shutil.which("bash") or "bash", "-n", str(PROJEKT / name)],
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(ergebnis.returncode, 0, ergebnis.stderr)

    def test_bauskript_prueft_die_tk_version(self):
        # Apples System-Tk 8.5 zeichnet Rahmen falsch und stuerzt bei mehreren
        # Fenstern ab. Der Bau muss daran scheitern, nicht erst der Betrieb.
        text = (PROJEKT / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertIn("tkinter.TkVersion", text)
        self.assertIn("8.6", text)

    def test_bauskript_signiert_nach_dem_aufraeumen(self):
        # codesign legt Signaturen mitgelieferter Dateien in erweiterten
        # Attributen ab; ein 'xattr -c' danach macht das Buendel unbrauchbar.
        text = (PROJEKT / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertLess(text.index("xattr -cr"), text.index("codesign --force"),
                        "xattr -cr muss VOR codesign laufen")

    def test_kein_gnu_only_schalter(self):
        # find -printf und readlink -f gibt es in den BSD-Fassungen nicht, die
        # macOS mitbringt. Beides steht im Linux-Skript und darf nicht
        # mitkopiert worden sein.
        for name in SKRIPTE:
            with self.subTest(skript=name):
                text = (PROJEKT / name).read_text(encoding="utf-8")
                self.assertNotIn("-printf", text)
                self.assertNotIn("readlink -f", text)
    def test_installer_liegt_im_abbild(self):
        """Stand bis zum 03.09.2026 in TranslokationTests.

        Sie prueft aber ``Build_macOS.sh``, nicht die Translokation -
        beim Heraustrennen der Plattformschicht ist sie deshalb hier
        gelandet, wo die uebrigen Skriptpruefungen stehen.
        """
        # Bis v1.8.58 wanderte allein das Buendel ins .dmg - der
        # Installer, der die Quarantaene abraeumt, kam nie beim Nutzer an.
        bau = (PROJEKT / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertIn("Erste Installation.command", bau)
        self.assertIn("com.apple.quarantine", bau)
        self.assertIn("ln -s /Applications", bau)
        self.assertNotIn(chr(39) + "-srcfolder " + chr(34) + "$BUENDEL"
                         + chr(34) + chr(39), bau,
                         "Das Abbild enthaelt wieder nur das Buendel.")


class SymbolTests(unittest.TestCase):
    """app_icon.icns und das Skript, das es erzeugt."""

    def test_skript_vorhanden(self):
        self.assertTrue((PROJEKT / "extract_icon_icns.py").is_file())

    def test_icns_liegt_bei_und_ist_lesbar(self):
        pfad = PROJEKT / "app_icon.icns"
        self.assertTrue(pfad.is_file(), "app_icon.icns fehlt - 'python extract_icon_icns.py'")
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow nicht verfuegbar")
        with Image.open(pfad) as bild:
            bild.load()
            # 1024 ist die groesste Kachel, die macOS im Finder anzeigt.
            self.assertEqual(bild.size, (1024, 1024))
            self.assertEqual(bild.format, "ICNS")

    def test_skript_kommt_ohne_iconutil_aus(self):
        # iconutil gibt es nur auf einem Mac; die Datei soll sich auch auf dem
        # Windows-Rechner erzeugen lassen, auf dem der Quelltext gepflegt wird.
        text = (PROJEKT / "extract_icon_icns.py").read_text(encoding="utf-8")
        self.assertNotIn("subprocess", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
