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

PLATTFORM_DATEI = PROJEKT / "ps5_validator" / "utils" / "plattform.py"
SPEC_MACOS = PROJEKT / "PS5ImageConverter_Pro_macos.spec"
SPEC_LINUX = PROJEKT / "PS5ImageConverter_Pro_linux.spec"
SKRIPTE = ("Build_macOS.sh", "Install_macOS.sh")


def _plattform_als(system: str):
    """Laedt die Plattformschicht frisch, als liefe sie auf ``system``.

    Bewusst ueber ``spec_from_file_location`` statt ``importlib.reload``: Ein
    reload traegt das umgebogene Modul in ``sys.modules`` ein, und jeder
    spaetere Test - auch in einer anderen Datei desselben Laufs - saehe dann
    ein Modul, das sich fuer macOS haelt.
    """
    ladeplan = importlib.util.spec_from_file_location(f"plattform_test_{system}", PLATTFORM_DATEI)
    assert ladeplan is not None and ladeplan.loader is not None
    modul = importlib.util.module_from_spec(ladeplan)
    with mock.patch.object(sys, "platform", system):
        ladeplan.loader.exec_module(modul)
    return modul


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


class PlattformschichtTests(unittest.TestCase):
    """Die macOS-Zweige der Betriebssystem-Abstraktion."""

    @classmethod
    def setUpClass(cls):
        cls.mac = _plattform_als("darwin")

    def test_erkennung(self):
        self.assertTrue(self.mac.IST_MACOS)
        self.assertFalse(self.mac.IST_WINDOWS)
        self.assertFalse(self.mac.IST_LINUX)
        self.assertTrue(self.mac.IST_POSIX)
        self.assertEqual(self.mac.systemname(), "macOS")

    def test_prozessflags_leer(self):
        # creationflags/startupinfo kennt nur die Windows-Implementierung von
        # subprocess; ein von null verschiedener Wert loest dort einen
        # ValueError aus.
        self.assertEqual(self.mac.prozess_flags(), {})

    def test_konfigurationsordner_folgt_apple(self):
        ordner = self.mac.konfigurationsordner()
        self.assertIn(os.path.join("Library", "Application Support"), ordner)
        self.assertTrue(ordner.endswith("PS5ImageConverterPro"))

    def test_windows_hinweis_nennt_das_system(self):
        """Geprueft am Dokan-Treiber - er ist wirklich Windows-gebunden.

        UFS2Tool stand hier bis v1.8.71 mit, war aber nie eine Grenze des
        Werkzeugs: Es laeuft auf allen drei Systemen, nur lag bei uns bloss
        der Windows-Bau bei. Einzig das Einhaengen als Laufwerk braucht Dokan.
        """
        text = self.mac.nur_windows_hinweis("Dokan")
        self.assertIn("Dokan", text)
        self.assertIn("macOS", text)
        # Der Hinweis soll den Zweck nennen, nicht nur den Namen des Werkzeugs.
        self.assertIn("Laufwerk", text)

    def test_ufs2tool_ist_keine_windows_grenze_mehr(self):
        self.assertNotIn("UFS2Tool", self.mac.NUR_WINDOWS_WERKZEUGE)


class SchriftwahlTests(unittest.TestCase):
    """Die Schriftwahl sieht in den Schriftordnern des Systems nach."""

    @classmethod
    def setUpClass(cls):
        cls.mac = _plattform_als("darwin")

    def test_erster_vorhandener_gewinnt(self):
        with tempfile.TemporaryDirectory() as ordner:
            # Nur Helvetica Neue liegt vor - Segoe UI steht davor, fehlt aber.
            Path(ordner, "HelveticaNeue.ttc").write_bytes(b"")
            with mock.patch.object(self.mac, "_MACOS_SCHRIFTORDNER", (ordner,)):
                gewaehlt = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
        self.assertEqual(gewaehlt, "Helvetica Neue")

    def test_segoe_ui_hat_vorrang(self):
        # Wer Microsoft Office installiert hat, soll exakt das Schriftbild
        # bekommen, fuer das die Abstaende im Fensteraufbau ausgelegt sind.
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "HelveticaNeue.ttc").write_bytes(b"")
            Path(ordner, "segoeui.ttf").write_bytes(b"")
            with mock.patch.object(self.mac, "_MACOS_SCHRIFTORDNER", (ordner,)):
                gewaehlt = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
        self.assertEqual(gewaehlt, "Segoe UI")

    def test_ersatzname_wenn_nichts_gefunden(self):
        with tempfile.TemporaryDirectory() as ordner:
            with mock.patch.object(self.mac, "_MACOS_SCHRIFTORDNER", (ordner,)):
                flaeche = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
                mono = self.mac._macos_familie(self.mac._MACOS_MONO_KANDIDATEN, "Courier")
        self.assertEqual(flaeche, "Helvetica")
        self.assertEqual(mono, "Courier")

    def test_unlesbarer_ordner_bricht_nicht_ab(self):
        # Ein Schriftordner auf einem abgemeldeten Netzlaufwerk darf den Start
        # nicht verhindern - die Schriftwahl laeuft schon beim Import.
        with mock.patch.object(self.mac.os.path, "isfile", side_effect=OSError("weg")):
            gewaehlt = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
        self.assertEqual(gewaehlt, "Helvetica")

    def test_kein_tkinter_beim_import(self):
        # Die Schriftnamen stehen in Vorgabewerten von Funktionssignaturen und
        # werden deshalb schon beim Import gebraucht - da gibt es noch kein
        # Tk-Fenster, ueber das sich Familien abfragen liessen.
        quelle = PLATTFORM_DATEI.read_text(encoding="utf-8")
        self.assertNotIn("import tkinter", quelle)


class SystembefehleTests(unittest.TestCase):
    """Oeffnen, Anzeigen und Herunterfahren nehmen die Apple-Befehle."""

    @classmethod
    def setUpClass(cls):
        cls.mac = _plattform_als("darwin")

    def test_datei_oeffnen_nutzt_open(self):
        with mock.patch.object(self.mac.shutil, "which", return_value="/usr/bin/open"), \
             mock.patch.object(self.mac.subprocess, "Popen") as popen:
            self.assertTrue(self.mac.datei_oeffnen("/tmp/handbuch.html"))
        self.assertEqual(popen.call_args[0][0], ["open", "/tmp/handbuch.html"])

    def test_im_dateimanager_zeigen_markiert_die_datei(self):
        with mock.patch.object(self.mac.subprocess, "Popen") as popen:
            self.assertTrue(self.mac.im_dateimanager_zeigen(str(PROJEKT / "README.md")))
        befehl = popen.call_args[0][0]
        self.assertEqual(befehl[:2], ["open", "-R"])

    def test_herunterfahren_probiert_beide_wege(self):
        # Der erste Weg braucht die Erlaubnis, andere Programme zu steuern.
        # Wird sie verweigert, muss der zweite drankommen.
        aufrufe = []

        class Ergebnis:
            def __init__(self, code):
                self.returncode = code
                self.stdout = ""
                self.stderr = "nicht erlaubt"

        def laeuft(befehl, **_kwargs):
            aufrufe.append(befehl[0])
            return Ergebnis(1 if befehl[0] == "osascript" else 0)

        with mock.patch.object(self.mac.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
             mock.patch.object(self.mac.subprocess, "run", side_effect=laeuft):
            erfolg, meldung = self.mac.herunterfahren()

        self.assertTrue(erfolg)
        self.assertEqual(aufrufe, ["osascript", "shutdown"])
        self.assertIn("shutdown", meldung)


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
        ziele = {os.path.basename(q) for q, _z in self._kwargs("Analysis")["datas"]}
        for pflicht in ("app_icon.ico", "helloworld", "MkPFS-0.0.9",
                        "Hintergrundbilder", "BENUTZERHANDBUCH.html",
                        "THIRD_PARTY_LICENSES.md", "Backport_Fakelibs"):
            self.assertIn(pflicht, ziele, f"{pflicht} wird nicht eingebettet")

    def test_ampr_ordner_liegt_daneben_statt_drin(self):
        """Seit v1.8.94 wird der AMPR-/PlayGo-Ordner NICHT eingebettet.

        Er soll sich austauschen lassen, ohne das Programm neu zu bauen.
        Eingebettete Daten landen unter sys._MEIPASS, einem Ordner, den
        PyInstaller beim Beenden loescht - dort etwas hineinzulegen waere
        zwecklos.

        Das Bauskript muss ihn deshalb ins Buendel kopieren - und zwar nach
        **Contents/Resources**, nicht nach Contents/MacOS.

        Der erste Anlauf legte ihn nach Contents/MacOS, weil das Programm
        seine Beilagen neben ``sys.argv[0]`` sucht. Das brachte am 25.08.2026
        den CI-Lauf auf echter Apple-Hardware zu Fall::

            a sealed resource is missing or invalid
            file added: .../Contents/MacOS/PlayGo & AMPR_EMU/PlayGo_v0.5

        Ein .app-Buendel versiegelt beim Signieren nur bestimmte Orte, und
        Contents/MacOS gehoert nicht dazu - dort erwartet das System
        ausschliesslich ausfuehrbaren Code. Auf Apple Silicon startet ein
        Buendel mit ungueltiger Signatur gar nicht erst.

        Zweite Bedingung, unveraendert: **vor** dem Signieren. codesign
        erfasst das Buendel als Ganzes; wer danach etwas hineinlegt, macht die
        eben gesetzte Signatur ungueltig.
        """
        ziele = {os.path.basename(q) for q, _z in self._kwargs("Analysis")["datas"]}
        self.assertNotIn("PlayGo & AMPR_EMU", ziele,
                         "Der Ordner soll neben der Programmdatei liegen, nicht darin")

        skript = (Path(__file__).resolve().parent / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertIn('cp -r "PlayGo & AMPR_EMU" "$BUENDEL/Contents/Resources/', skript,
                      "Das Bauskript legt den Ordner nicht nach Contents/Resources")
        self.assertNotIn('cp -r "PlayGo & AMPR_EMU" "$BUENDEL/Contents/MacOS/', skript,
                         "Contents/MacOS wird beim Signieren nicht versiegelt")
        kopieren = skript.index('cp -r "PlayGo & AMPR_EMU"')
        signieren = skript.index("codesign --force")
        self.assertLess(kopieren, signieren,
                        "Der Ordner muss VOR dem Signieren im Buendel liegen")

    def test_das_programm_sieht_auch_in_contents_resources_nach(self):
        """Sonst faende es den Ordner an seinem neuen Platz nicht.

        Die Gegenprobe zum Bauskript: Beides muss zusammenpassen, sonst liegt
        der Ordner zwar korrekt im Buendel, und Aufgabe 7 findet trotzdem
        keine Versionen.
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


class SchriftskalierungTests(unittest.TestCase):
    """Punktgroessen bedeuten auf Aqua etwas anderes als auf Windows.

    Gemeldet am 19.08.2026 an einem Mac mini: "Die Schrift ist teilweise
    verdammt klein und extrem schwer zu lesen."
    """

    def _gui(self, *, macos: bool, einstellung=None, scaling=1.0):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gerufen = []

        class _Tk:
            def call(self, *args):
                if args[:2] == ("tk", "scaling") and len(args) == 2:
                    return scaling
                gerufen.append(args)
                return ""

        class _Wurzel:
            tk = _Tk()

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.root = _Wurzel()
        gui._load_setting = lambda name, vorgabe=None: (
            vorgabe if einstellung is None else einstellung)
        return APP, gui, gerufen

    def test_auf_windows_passiert_nichts(self):
        from unittest import mock

        APP, gui, gerufen = self._gui(macos=False)
        with mock.patch.object(APP, "IST_MACOS", False):
            gui._macos_schrift_skalieren()
        self.assertEqual(gerufen, [], "Windows und Linux bleiben unberuehrt")

    def test_auf_macos_wird_hochgesetzt(self):
        from unittest import mock

        APP, gui, gerufen = self._gui(macos=True, scaling=1.0)
        with mock.patch.object(APP, "IST_MACOS", True):
            gui._macos_schrift_skalieren()
        self.assertEqual(len(gerufen), 1, gerufen)
        self.assertEqual(gerufen[0][:2], ("tk", "scaling"))
        self.assertAlmostEqual(gerufen[0][2], APP.MACOS_SCHRIFT_SKALIERUNG, places=6)

    def test_eigener_wert_aus_den_einstellungen(self):
        from unittest import mock

        APP, gui, gerufen = self._gui(macos=True, einstellung="1.6", scaling=1.0)
        with mock.patch.object(APP, "IST_MACOS", True):
            gui._macos_schrift_skalieren()
        self.assertAlmostEqual(gerufen[0][2], 1.6, places=6)

    def test_unsinniger_wert_wird_abgelehnt(self):
        from unittest import mock

        for wert in ("0", "12", "-3", "kaese"):
            APP, gui, gerufen = self._gui(macos=True, einstellung=wert)
            with mock.patch.object(APP, "IST_MACOS", True):
                gui._macos_schrift_skalieren()
            if wert == "kaese":
                # Unlesbar -> Vorgabe, nicht abgeschaltet.
                self.assertEqual(len(gerufen), 1, wert)
            else:
                self.assertEqual(gerufen, [], "Wert %r haette abgelehnt werden muessen" % wert)

    def test_steht_vor_dem_aufbau_der_oberflaeche(self):
        # Tk rechnet Punktgroessen beim Anlegen einer Schrift in Pixel um.
        # Wird die Skalierung erst hinterher gesetzt, bleiben alle bereits
        # erzeugten Schriften klein - der Aufruf muss vor _create_widgets
        # stehen.
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        anfang = quelle.index("    def __init__(self, root: tk.Tk) -> None:")
        block = quelle[anfang:anfang + 40000]
        self.assertLess(block.index("self._macos_schrift_skalieren()"),
                        block.index("self._create_widgets()"),
                        "Die Skalierung wirkt nicht mehr auf die Schriften.")


class TranslokationTests(unittest.TestCase):
    """macOS startet quarantaenebehaftete Programme aus einem Schattenordner.

    Im Protokoll vom 19.08.2026 stand der mkpfs-Pfad unter
    ".../T/AppTranslocation/7997DEE9-.../d/..." - niemand konnte die
    Ursache benennen. Einstellungen und Protokolle gehen dort beim
    Beenden verloren.
    """

    SCHATTEN = ("/private/var/folders/2k/T/AppTranslocation/7997DEE9/d/"
                "PS5 Dump & Image Converter.app/Contents/Frameworks")
    ORDENTLICH = ("/Applications/PS5 Dump & Image Converter.app/"
                  "Contents/Frameworks")

    def setUp(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        self.APP = APP

    def _pruefen(self, macos, pfad):
        from unittest import mock

        with mock.patch.object(self.APP, "IST_MACOS", macos):
            with mock.patch.object(self.APP.sys, "_MEIPASS", pfad,
                                   create=True):
                return self.APP.PS5ConverterGUI._macos_translokation()

    def test_ausserhalb_von_macos_immer_falsch(self):
        self.assertFalse(self._pruefen(False, self.SCHATTEN))

    def test_schattenordner_wird_erkannt(self):
        self.assertTrue(self._pruefen(True, self.SCHATTEN))

    def test_normaler_ort_wird_nicht_gemeldet(self):
        self.assertFalse(self._pruefen(True, self.ORDENTLICH))

    def test_installer_liegt_im_abbild(self):
        # Bis v1.8.58 wanderte allein das Buendel ins .dmg - der
        # Installer, der die Quarantaene abraeumt, kam nie beim Nutzer an.
        bau = (PROJEKT / "Build_macOS.sh").read_text(encoding="utf-8")
        self.assertIn("Erste Installation.command", bau)
        self.assertIn("com.apple.quarantine", bau)
        self.assertIn("ln -s /Applications", bau)
        self.assertNotIn(chr(39) + "-srcfolder " + chr(34) + "$BUENDEL"
                         + chr(34) + chr(39), bau,
                         "Das Abbild enthaelt wieder nur das Buendel.")

    def test_hinweis_ist_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS

        for schluessel in ("macos.translocation_title",
                           "macos.translocation_hint"):
            self.assertIn(schluessel, STRINGS)
            for sprache in ("de", "en"):
                self.assertTrue(STRINGS[schluessel].get(sprache), schluessel)


class AquaKnopfTests(unittest.TestCase):
    """Auf Aqua ignoriert ein ``tk.Button`` seine Hintergrundfarbe.

    Uebrig blieb die helle Systemflaeche, auf der die hellen Schriftfarben
    dieses Programms stehen. Im Mitschnitt vom 20.08.2026 war der Fussknopf
    "Was man sonst ev. noch braucht" (fg_primary auf Weiss) nicht mehr zu
    entziffern, und die Titelleiste zeigte eine Reihe heller Pillen.
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def test_titelleistenknoepfe_gehen_ueber_die_weiche(self):
        """Jeder Knopf der Titelleiste muss ueber flach_knopf entstehen.

        Hier stand bis zum 22.08.2026 die feste Zahl 13. Die bricht bei
        jedem neuen Knopf, ohne dass etwas kaputt waere - gemeint war nie
        die Anzahl, sondern dass **keiner** an der Weiche vorbeigeht.
        Genau das wird jetzt geprueft, unabhaengig davon, wie viele es
        sind.
        """
        import re

        anfang = self.quelle.index("self._titlebar_right = tk.Frame(")
        ende = self.quelle.index("        # 8. Bindings", anfang)
        block = self.quelle[anfang:ende]

        zuweisungen = re.findall(r"self\.(_btn_\w+)\s*=\s*(\w+)\(", block)
        self.assertTrue(zuweisungen, "In der Titelleiste entsteht kein Knopf.")
        falsch = [name for name, weiche in zuweisungen if weiche != "flach_knopf"]
        self.assertEqual(falsch, [],
                         "Diese Knoepfe gehen an flach_knopf vorbei: %s" % falsch)
        self.assertNotIn(" = tk.Button(", block,
                         "In der Titelleiste steht wieder ein Systemknopf.")

    def test_fussknoepfe_gehen_ueber_die_weiche(self):
        for name in ("self.info_toggle_btn = ", "self.resources_btn = "):
            stelle = self.quelle.index(name)
            self.assertTrue(
                self.quelle[stelle:stelle + len(name) + 12].endswith("flach_knopf("),
                f"{name.strip()} entsteht nicht ueber flach_knopf.")

    def test_weiche_liefert_je_system_das_richtige(self):
        import tkinter as tk

        import PS5ImageConverter_Pro_FINAL_revised as APP

        try:
            wurzel = tk._default_root or tk.Tk()
        except tk.TclError:
            self.skipTest("keine Anzeige verfuegbar")
        with mock.patch.object(APP, "IST_MACOS", True):
            self.assertIsInstance(APP.flach_knopf(wurzel, text="x"), APP.FlachButton)
        with mock.patch.object(APP, "IST_MACOS", False):
            self.assertIsInstance(APP.flach_knopf(wurzel, text="x"), tk.Button)

    def test_flachbutton_traegt_seine_farbe_und_ruft_auf(self):
        import tkinter as tk

        import PS5ImageConverter_Pro_FINAL_revised as APP

        try:
            wurzel = tk._default_root or tk.Tk()
        except tk.TclError:
            self.skipTest("keine Anzeige verfuegbar")
        gerufen = []
        knopf = APP.FlachButton(wurzel, text="Probe", bg="#123456", fg="#abcdef",
                                command=lambda: gerufen.append(1))
        # Der Punkt der ganzen Uebung: die Farbe bleibt, wie sie gesetzt wurde.
        self.assertEqual(str(knopf.cget("bg")), "#123456")
        self.assertEqual(str(knopf.cget("fg")), "#abcdef")
        knopf.invoke()
        self.assertEqual(gerufen, [1])
        # Abgeschaltet loest er nicht aus - wie ein tk.Button auch nicht.
        knopf.config(state=tk.DISABLED)
        knopf.invoke()
        self.assertEqual(gerufen, [1])
        knopf.config(state=tk.NORMAL)
        knopf.invoke()
        self.assertEqual(gerufen, [1, 1])
        # config(command=...) muss den Aufruf austauschen, nicht abstuerzen.
        anders = []
        knopf.config(command=lambda: anders.append(1), text="Neu")
        knopf.invoke()
        self.assertEqual((anders, str(knopf.cget("text"))), ([1], "Neu"))
        knopf.destroy()

    def test_pt_laesst_windows_und_linux_unberuehrt(self):
        """Ausserhalb von macOS muss die Zahl unveraendert durchgehen."""
        import PS5ImageConverter_Pro_FINAL_revised as APP

        if APP.IST_MACOS:
            self.skipTest("laeuft auf macOS")
        self.assertEqual(APP._MACOS_SCHRIFTFAKTOR, 1.0)
        for punkte in (7, 8, 9, 10, 12, 16, 24):
            self.assertEqual(APP.pt(punkte), punkte)

    def test_alle_schriftangaben_gehen_ueber_pt(self):
        """Sonst faellt die naechste neue Beschriftung wieder aus dem Raster.

        Die Umstellung war mechanisch (288 Stellen). Genau deshalb braucht sie
        eine Sperre: Eine einzelne nackte Punktzahl faellt beim Lesen nicht auf,
        auf dem Mac aber sofort - sie stuende dann bei 60 % der Groesse ihrer
        Nachbarn.
        """
        nackt = re.findall(r"\((?:UI_SCHRIFT|MONO_SCHRIFT), \d", self.quelle)
        self.assertEqual(nackt, [],
                         f"{len(nackt)} Schriftangabe(n) ohne pt() im Quelltext.")
        # Gegenprobe, dass das Muster ueberhaupt greift.
        self.assertGreater(
            len(re.findall(r"\((?:UI_SCHRIFT|MONO_SCHRIFT), pt\(", self.quelle)), 250)

    def test_faktor_trifft_die_windows_pixelhoehen(self):
        """Ziel der Umstellung: dasselbe Schriftbild wie unter Windows.

        Vergleichsmass ist die Anzeigeskalierung, mit der die Fassung dort
        laeuft (125 %, ``tk scaling`` 1,6683). Rundung darf einen Bildpunkt
        abweichen - mehr nicht.
        """
        import PS5ImageConverter_Pro_FINAL_revised as APP

        faktor = APP.MACOS_SCHRIFT_SKALIERUNG
        for punkte in (7, 8, 9, 10, 12, 14, 16, 18, 24):
            auf_mac = max(1, round(punkte * faktor))
            auf_windows = round(punkte * 1.6683)
            self.assertLessEqual(
                abs(auf_mac - auf_windows), 1,
                f"{punkte} pt: Mac {auf_mac} px gegen Windows {auf_windows} px")

    def test_faktor_kommt_aus_der_einstellungsdatei(self):
        """``macos_font_scaling`` muss ohne neuen Bau wirken - und zwar auf pt()."""
        import PS5ImageConverter_Pro_FINAL_revised as APP

        with tempfile.TemporaryDirectory() as ordner:
            with open(os.path.join(ordner, "paths.json"), "w", encoding="utf-8") as f:
                f.write('{"macos_font_scaling": 2.0}')
            with mock.patch.object(APP, "IST_MACOS", True),                     mock.patch.object(APP, "_system_konfigurationsordner",
                                      lambda *a, **k: ordner):
                self.assertEqual(APP._macos_schriftfaktor(), 2.0)
            # Unsinnige Werte fallen auf die Vorgabe zurueck.
            with open(os.path.join(ordner, "paths.json"), "w", encoding="utf-8") as f:
                f.write('{"macos_font_scaling": 99}')
            with mock.patch.object(APP, "IST_MACOS", True),                     mock.patch.object(APP, "_system_konfigurationsordner",
                                      lambda *a, **k: ordner):
                self.assertEqual(APP._macos_schriftfaktor(),
                                 APP.MACOS_SCHRIFT_SKALIERUNG)

    def test_tk_scaling_bleibt_wegen_der_seitenleiste(self):
        """Der Aufruf wirkt nicht auf Schriften - aber auf Tks cm-Vorgaben.

        An denen haengt die Standardbreite eines Canvas (10c) und damit ueber
        die Aufgabenknoepfe die Breite der Seitenleiste. Faellt der Aufruf weg,
        schrumpft sie auf dem Mac von 487 auf 283 Pixel.
        """
        anfang = self.quelle.index("    def _macos_schrift_skalieren(self)")
        ende = self.quelle.index("\n    @staticmethod", anfang)
        block = self.quelle[anfang:ende]
        self.assertIn('self.root.tk.call("tk", "scaling", vorher * faktor)', block)


if __name__ == "__main__":
    unittest.main(verbosity=2)
