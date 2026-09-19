# -*- coding: utf-8 -*-
"""PS5 Wee Tools - mitgeliefert, als eigenes Programm gestartet (seit v1.9.29).

Geprueft wird, was sonst erst im gebauten Programm oder beim Anwender
auffiele:

* der mitgelieferte Ordner ist unveraendert (``herkunft.json``),
* jeder Import des Werkzeugs steht in den ``hiddenimports`` aller drei
  ``.spec`` - PyInstaller sieht sie nicht, weil das Werkzeug als Datenordner
  beiliegt (so fehlten schon ``tomllib`` und ``lz4`` in der EXE),
* der interne Modus laeuft wirklich - ausgefuehrt, nicht nachgelesen: mit
  Sprachdateien auch bei gesetztem ``sys.frozen``, mit "Beenden" auch ohne
  das eingebaute ``quit()``, und ohne dass ein fremdes ``tools`` dazwischen-
  funkt,
* der Knopf fragt vorher (Vorgabe Nein) und startet mit eigenem
  Konsolenfenster.
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("wee_tools")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import wee_tools                    # noqa: E402
from ps5_validator.utils.diagnose_befund import Diagnosebericht  # noqa: E402

ORDNER = PROJEKT / wee_tools.ORDNER
SPECS = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
         "PS5ImageConverter_Pro_macos.spec")
#: Neben den Dateien des Werkzeugs liegen nur diese beiden von uns.
EIGENE_BEIGABEN = {"UPSTREAM.md", "herkunft.json"}
#: Importe, die es nur unter Windows gibt (das Werkzeug faengt ihr Fehlen ab).
NUR_WINDOWS = {"winsound"}


def _werkzeug_importe() -> set[str]:
    """Was das Werkzeug importiert - am Syntaxbaum, auch in Funktionen."""
    eigene = set(wee_tools.EIGENE_PAKETE)
    namen: set[str] = set()
    for datei in ORDNER.rglob("*.py"):
        for knoten in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.Import):
                namen.update(a.name for a in knoten.names
                             if a.name.split(".")[0] not in eigene)
            elif (isinstance(knoten, ast.ImportFrom) and knoten.level == 0
                  and knoten.module and knoten.module.split(".")[0] not in eigene):
                namen.add(knoten.module)
                # "from serial.tools import list_ports" holt ein Untermodul -
                # das muss PyInstaller ebenso kennen.
                for alias in knoten.names:
                    voll = "%s.%s" % (knoten.module, alias.name)
                    try:
                        if importlib.util.find_spec(voll) is not None:
                            namen.add(voll)
                    except (ImportError, ValueError):
                        continue
    return namen


def _hauptmodul_importe() -> set[str]:
    """Was das Hauptmodul auf oberster Ebene importiert - das steckt ohnehin im Bau."""
    baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
                     .read_text(encoding="utf-8"))
    namen: set[str] = set()
    stapel = list(baum.body)
    while stapel:
        knoten = stapel.pop()
        if isinstance(knoten, ast.Import):
            namen.update(a.name for a in knoten.names)
        elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0 and knoten.module:
            namen.add(knoten.module)
        elif isinstance(knoten, ast.Try):
            stapel.extend(knoten.body + knoten.orelse + knoten.finalbody)
            for zweig in knoten.handlers:
                stapel.extend(zweig.body)
    return namen


def _hiddenimports(spec: str) -> set[str]:
    baum = ast.parse((PROJEKT / spec).read_text(encoding="utf-8"))
    for knoten in ast.walk(baum):
        if (isinstance(knoten, ast.keyword) and knoten.arg == "hiddenimports"
                and isinstance(knoten.value, ast.List)):
            return {e.value for e in knoten.value.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    return set()


class OrdnerTests(unittest.TestCase):
    """Der mitgelieferte Ordner - vollstaendig und unveraendert."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.herkunft = json.loads((ORDNER / "herkunft.json").read_text(encoding="utf-8"))

    def test_jede_datei_ist_byte_gleich_mit_dem_quellarchiv(self) -> None:
        dateien = self.herkunft["dateien"]
        self.assertGreaterEqual(len(dateien), 42)
        for rel, soll in dateien.items():
            with self.subTest(datei=rel):
                daten = (ORDNER / rel).read_bytes()
                self.assertEqual(soll["bytes"], len(daten))
                self.assertEqual(soll["sha256"], hashlib.sha256(daten).hexdigest())

    def test_nichts_liegt_zusaetzlich_im_ordner(self) -> None:
        vorhanden = {p.relative_to(ORDNER).as_posix() for p in ORDNER.rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts}
        self.assertEqual(set(self.herkunft["dateien"]) | EIGENE_BEIGABEN, vorhanden)

    def test_die_lizenz_liegt_bei(self) -> None:
        kopf = (ORDNER / "LICENSE").read_text(encoding="utf-8")[:200]
        self.assertIn("GNU GENERAL PUBLIC LICENSE", kopf)
        self.assertIn("Version 3", kopf)

    def test_die_fassung_wird_gelesen(self) -> None:
        self.assertEqual("0.1.8", wee_tools.fassung_lesen(str(ORDNER)))
        self.assertEqual("0.1.8", self.herkunft["fassung"])
        self.assertTrue(wee_tools.ORDNER.endswith("0.1.8"))

    def test_ohne_ordner_keine_fassung(self) -> None:
        self.assertEqual("", wee_tools.fassung_lesen(""))


class BauTests(unittest.TestCase):
    """Was PyInstaller nicht sieht, muss in den drei Bauplaenen stehen."""

    def test_die_pruefung_findet_ueberhaupt_importe(self) -> None:
        """Anker - sonst waere der Test darunter stumm richtig."""
        importe = _werkzeug_importe()
        for erwartet in ("serial", "serial.tools.list_ports", "winsound", "locale"):
            with self.subTest(modul=erwartet):
                self.assertIn(erwartet, importe)
        for spec in SPECS:
            with self.subTest(spec=spec):
                self.assertGreater(len(_hiddenimports(spec)), 20)

    def test_jeder_import_des_werkzeugs_steht_im_bauplan(self) -> None:
        schon_da = _hauptmodul_importe() | {"os", "sys"}
        benoetigt = _werkzeug_importe() - schon_da
        self.assertIn("serial", benoetigt)
        for spec in SPECS:
            with self.subTest(spec=spec):
                noetig = benoetigt if spec == SPECS[0] else benoetigt - NUR_WINDOWS
                fehlend = sorted(noetig - _hiddenimports(spec))
                self.assertEqual([], fehlend,
                                 "%s: Importe des Werkzeugs fehlen in hiddenimports - "
                                 "im Bau brach der interne Modus sonst mit "
                                 "ModuleNotFoundError ab." % spec)

    def test_jeder_bauplan_bettet_den_ordner_ein(self) -> None:
        aufruf = "_dateien_ohne_pycache(_wee_tools, '%s')" % wee_tools.ORDNER
        for spec in SPECS:
            with self.subTest(spec=spec):
                text = (PROJEKT / spec).read_text(encoding="utf-8")
                self.assertGreaterEqual(text.count(aufruf), 1)

    def test_pyserial_ist_festgenagelt_und_wird_installiert(self) -> None:
        anforderungen = (PROJEKT / "requirements.txt").read_text(encoding="utf-8")
        self.assertRegex(anforderungen, r"(?m)^pyserial==\d")
        for skript in ("Build_EXE.ps1", "Build_Linux.sh", "Build_macOS.sh"):
            with self.subTest(skript=skript):
                text = (PROJEKT / skript).read_text(encoding="utf-8-sig")
                self.assertGreaterEqual(text.count("pyserial"), 1)


class StartbefehlTests(unittest.TestCase):
    """Wie der Kindprozess gestartet wird - je Plattform."""

    def test_gebaut_ruft_die_programmdatei_sich_selbst(self) -> None:
        self.assertEqual(["C:/p/app.exe", wee_tools.SELBSTAUFRUF],
                         wee_tools.startbefehl(eingefroren=True, programm="C:/p/app.exe",
                                               hauptskript="egal.py"))

    def test_aus_dem_quelltext_mit_hauptskript(self) -> None:
        self.assertEqual(["py", "haupt.py", wee_tools.SELBSTAUFRUF],
                         wee_tools.startbefehl(eingefroren=False, programm="py",
                                               hauptskript="haupt.py"))

    def test_windows_braucht_keinen_umweg(self) -> None:
        befehl = ["a.exe", wee_tools.SELBSTAUFRUF]
        self.assertEqual(befehl, wee_tools.terminal_befehl(befehl, "win32", lambda _n: None))

    def test_linux_nimmt_das_erste_gefundene_terminal(self) -> None:
        gefunden = {"konsole": "/usr/bin/konsole", "xterm": "/usr/bin/xterm"}
        befehl = wee_tools.terminal_befehl(["/opt/app", wee_tools.SELBSTAUFRUF], "linux",
                                           gefunden.get)
        self.assertEqual(["/usr/bin/konsole", "-e", "/opt/app", wee_tools.SELBSTAUFRUF],
                         befehl)

    def test_linux_ohne_terminal_meldet_none(self) -> None:
        self.assertIsNone(wee_tools.terminal_befehl(["/opt/app"], "linux", lambda _n: None))

    def test_macos_maskiert_fuer_applescript(self) -> None:
        befehl = wee_tools.terminal_befehl(['/Apps/Mein "PS5".app/x', wee_tools.SELBSTAUFRUF],
                                           "darwin")
        self.assertEqual("osascript", befehl[0])
        skript = befehl[2]
        self.assertTrue(skript.startswith('tell application "Terminal" to do script "'))
        self.assertIn(r'\"PS5\"', skript)
        self.assertTrue(skript.endswith(wee_tools.SELBSTAUFRUF + '"'))

    def test_kindumgebung_setzt_den_neustart_von_pyinstaller(self) -> None:
        basis = {"PATH": "x"}
        umgebung = wee_tools.kindumgebung(basis, sprache="de", arbeitsordner="C:/w")
        self.assertEqual("1", umgebung[wee_tools.UMGEBUNG_PYINSTALLER_NEU])
        self.assertEqual("de", umgebung[wee_tools.UMGEBUNG_SPRACHE])
        self.assertEqual("C:/w", umgebung[wee_tools.UMGEBUNG_ARBEITSORDNER])
        self.assertEqual({"PATH": "x"}, basis, "Die Vorlage bleibt unveraendert")


class KopieTests(unittest.TestCase):
    """Die Programmkopie im Arbeitsordner und ihre config.ini."""

    def setUp(self) -> None:
        self.arbeit = Path(tempfile.mkdtemp(prefix="wee_arbeit_"))
        self.addCleanup(shutil.rmtree, self.arbeit, True)

    def _kopie(self, sprache: str) -> Path:
        return Path(wee_tools.kopie_anlegen(str(ORDNER), str(self.arbeit), sprache))

    def test_kopie_mit_einstellungen_in_der_sprache_des_programms(self) -> None:
        kopie = self._kopie("de")
        self.assertTrue((kopie / wee_tools.EINSTIEG).is_file())
        self.assertTrue((kopie / "i18n" / "de.json").is_file())
        text = (kopie / "config.ini").read_text(encoding="utf-8")
        self.assertIn("lang = de", text)
        self.assertIn("sound = 1", text)

    def test_die_einstellungen_des_anwenders_bleiben(self) -> None:
        kopie = self._kopie("de")
        (kopie / "config.ini").write_text("lang = fr\nport-spi = COM7\n", encoding="utf-8")
        self._kopie("de")
        self.assertEqual("lang = fr\nport-spi = COM7\n",
                         (kopie / "config.ini").read_text(encoding="utf-8"))

    def test_unbekannte_sprache_laesst_das_werkzeug_waehlen(self) -> None:
        self.assertNotIn("lang", (self._kopie("xx") / "config.ini").read_text(encoding="utf-8"))

    def test_die_mitgelieferte_config_ini_ueberstimmt_nichts(self) -> None:
        """Sie steht auf "lang = en" - kopiert, ueberstimmte sie jede Sprache."""
        self.assertIn("lang = en", (ORDNER / "config.ini").read_text(encoding="utf-8"))
        self.assertNotIn("lang = en",
                         (self._kopie("") / "config.ini").read_text(encoding="utf-8"))


class AusfuehrenTests(unittest.TestCase):
    """Der interne Modus - in einem eigenen Prozess ausgefuehrt, wie im Betrieb."""

    def setUp(self) -> None:
        self.arbeit = Path(tempfile.mkdtemp(prefix="wee_lauf_"))
        self.addCleanup(shutil.rmtree, self.arbeit, True)

    def _lauf(self, argumente: list[str], sprache: str = "en", eingabe: str = "\n",
              vorbereitung: str = "") -> subprocess.CompletedProcess:
        code = "\n".join([
            "import sys",
            "sys.path.insert(0, %r)" % str(PROJEKT),
            vorbereitung,
            "from ps5_validator.utils import wee_tools",
            "sys.exit(wee_tools.ausfuehren(%r, %r, %r, %r))" % (
                str(ORDNER), str(self.arbeit), argumente, sprache),
        ])
        umgebung = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run([sys.executable, "-c", code], input=eingabe,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", cwd=str(PROJEKT), env=umgebung,
                              timeout=120)

    def test_die_hilfe_laeuft(self) -> None:
        lauf = self._lauf(["help"])
        self.assertEqual(0, lauf.returncode, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertIn("PS5 Wee Tools v0.1.8", lauf.stdout)
        self.assertIn("Usage", lauf.stdout)
        self.assertTrue((self.arbeit / wee_tools.KOPIE_NAME / wee_tools.EINSTIEG).is_file())

    def test_sprachdateien_auch_bei_gesetztem_frozen(self) -> None:
        """Im Bau suchte wee-tools sie neben sys.executable - und faende keine."""
        anderswo = self.arbeit / "anderswo" / "programm.exe"
        vorbereitung = "sys.frozen = True\nsys.executable = %r" % str(anderswo)
        lauf = self._lauf(["help"], "de", vorbereitung=vorbereitung)
        self.assertEqual(0, lauf.returncode, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertIn("Verwendung", lauf.stdout)

    def test_beenden_ohne_eingebautes_quit(self) -> None:
        """Im Bau legt das site-Modul quit() nicht an; Menuepunkt 6 ruft es."""
        vorbereitung = "\n".join([
            "import builtins",
            "for _name in ('quit', 'exit'):",
            "    if hasattr(builtins, _name):",
            "        delattr(builtins, _name)",
        ])
        lauf = self._lauf([], eingabe="6\n", vorbereitung=vorbereitung)
        self.assertEqual(0, lauf.returncode, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertNotIn("NameError", lauf.stdout + lauf.stderr)

    def test_beenden_im_hauptmenue_endet_sauber(self) -> None:
        """Der Normalfall: Knopf, Hauptmenue, "Beenden" - ohne Fehlerausdruck.

        wee-tools leert sys.argv mit pop(0). runpy.run_path wollte beim
        Verlassen sys.argv[0] zurueckschreiben und scheiterte mit IndexError -
        am 19.09.2026 von diesem Test gefunden.
        """
        lauf = self._lauf([], eingabe="6\n")
        self.assertEqual(0, lauf.returncode, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertNotIn("Traceback", lauf.stdout + lauf.stderr)

    def test_ein_fremdes_tools_funkt_nicht_dazwischen(self) -> None:
        """Das Werkzeug nennt seine Pakete tools/utils/lang/data - Allerweltsnamen.

        Das fremde ``tools`` ist ein gewoehnliches Paket (mit __init__.py),
        steht ganz **hinten** im Suchpfad und ist schon importiert. Nach PEP
        420 gewaenne es gegen das Namensraum-Paket des Werkzeugs, obwohl die
        Kopie vorn steht; und ``tools.Tools`` laege schon in sys.modules.
        """
        fremd = self.arbeit / "fremd"
        (fremd / "tools").mkdir(parents=True)
        (fremd / "tools" / "__init__.py").write_text("", encoding="utf-8")
        (fremd / "tools" / "Tools.py").write_text(
            "def _falsch(*_a, **_k):\n"
            "    print('falsches tools')\n"
            "    return True\n"
            "screenHelp = screenMainMenu = launchTool = _falsch\n"
            "screenFileSelect = screenCompareFiles = _falsch\n", encoding="utf-8")
        vorbereitung = "sys.path.append(%r)\nimport tools.Tools" % str(fremd)
        lauf = self._lauf(["help"], vorbereitung=vorbereitung)
        self.assertEqual(0, lauf.returncode, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertIn("PS5 Wee Tools v0.1.8", lauf.stdout)
        self.assertNotIn("falsches tools", lauf.stdout + lauf.stderr)

    def test_ende_zu_ende_ueber_das_hauptmodul(self) -> None:
        """Der Schalter im Startblock - so, wie der Knopf ihn aufruft."""
        umgebung = dict(os.environ, PYTHONIOENCODING="utf-8")
        umgebung[wee_tools.UMGEBUNG_ARBEITSORDNER] = str(self.arbeit)
        umgebung[wee_tools.UMGEBUNG_SPRACHE] = "en"
        lauf = subprocess.run(
            [sys.executable, str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"),
             wee_tools.SELBSTAUFRUF, "help"],
            input="\n", capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=str(PROJEKT), env=umgebung, timeout=300)
        self.assertEqual(0, lauf.returncode, lauf.stdout[-2000:] + lauf.stderr[-2000:])
        self.assertIn("PS5 Wee Tools v0.1.8", lauf.stdout)


class HauptmodulTests(unittest.TestCase):
    """Startblock und die beiden Ortsbestimmungen des Hauptmoduls."""

    def test_der_interne_modus_steht_vor_der_rechtepruefung(self) -> None:
        """Wie --ps4ffpsc: Eine zweite UAC-Abfrage haette niemanden, der sie beantwortet."""
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        block = quelle[quelle.index('if __name__ == "__main__":'):]
        self.assertLess(block.index("wee_tools.SELBSTAUFRUF"),
                        block.index("_register_mit_license_runtime()"))

    def test_der_ordner_wird_gefunden(self) -> None:
        self.assertEqual(os.path.normcase(str(ORDNER)),
                         os.path.normcase(APP._wee_tools_wurzel()))

    def test_arbeitsordner_neben_dem_programm(self) -> None:
        erwartet = os.path.join(os.path.dirname(os.path.abspath(APP.__file__)),
                                wee_tools.ARBEITSORDNER_NAME)
        self.assertEqual(erwartet, APP._wee_tools_arbeitsordner())

    def test_gebaut_neben_der_programmdatei(self) -> None:
        programm = os.path.join(str(PROJEKT), "irgendwo", "app.exe")
        with mock.patch.object(APP.sys, "frozen", True, create=True), \
                mock.patch.object(APP.sys, "executable", programm):
            self.assertEqual(os.path.join(os.path.dirname(programm),
                                          wee_tools.ARBEITSORDNER_NAME),
                             APP._wee_tools_arbeitsordner())

    def test_nie_in_ein_macos_buendel(self) -> None:
        """Schreiben in Contents/MacOS bricht die Signatur des Buendels."""
        programm = "/Programme/X.app/Contents/MacOS/x"
        with mock.patch.object(APP.sys, "frozen", True, create=True), \
                mock.patch.object(APP.sys, "executable", programm), \
                mock.patch.object(APP.sys, "platform", "darwin"):
            ziel = APP._wee_tools_arbeitsordner()
        self.assertNotIn("Contents", ziel)
        self.assertTrue(ziel.endswith(wee_tools.ARBEITSORDNER_NAME))


class KnopfTests(unittest.TestCase):
    """Der Knopf unter WEITERE TOOLS - ohne echtes Fenster, Dialoge aufgezeichnet."""

    def setUp(self) -> None:
        self.arbeit = Path(tempfile.mkdtemp(prefix="wee_knopf_"))
        self.addCleanup(shutil.rmtree, self.arbeit, True)
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        self.gui._t = lambda k, **w: k + "".join("|%s=%s" % (a, b) for a, b in sorted(w.items()))
        self.gui.root = None
        self.gui._current_language = "de"
        self.protokoll: list = []
        self.gui._append_to_log = self.protokoll.append
        self.gui._set_status = self.protokoll.append
        self.gestartet: list = []
        self.fragen: list = []

    def _klicken(self, *, antwort: bool, finden=importlib.util.find_spec) -> None:
        def _frage(_titel, text, **optionen):
            self.fragen.append((text, optionen))
            return antwort

        ziel = str(self.arbeit / wee_tools.ARBEITSORDNER_NAME)
        with mock.patch.object(APP, "_wee_tools_arbeitsordner", lambda: ziel), \
                mock.patch.object(APP.messagebox, "askyesno", _frage), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda *a, **_k: self.protokoll.append(("fehler",) + a)), \
                mock.patch.object(APP.messagebox, "showinfo",
                                  lambda *a, **_k: self.protokoll.append(("info",) + a)), \
                mock.patch.object(APP.subprocess, "Popen",
                                  lambda befehl, **k: self.gestartet.append((befehl, k))), \
                mock.patch("importlib.util.find_spec", finden):
            self.gui._show_wee_tools()

    def test_der_menueeintrag(self) -> None:
        self.assertIn(("titlebar.wee_tools", "_show_wee_tools"),
                      APP.PS5ConverterGUI._MORE_TOOLS_ENTRIES)

    def test_ohne_zustimmung_startet_nichts(self) -> None:
        self._klicken(antwort=False)
        self.assertEqual([], self.gestartet)
        self.assertEqual(1, len(self.fragen))

    def test_die_frage_nennt_den_ordner_und_ist_nein_vorbelegt(self) -> None:
        self._klicken(antwort=False)
        text, optionen = self.fragen[0]
        self.assertIn("weetools.frage", text)
        self.assertIn(str(self.arbeit / wee_tools.ARBEITSORDNER_NAME), text)
        self.assertEqual(APP.messagebox.NO, optionen.get("default"))

    @unittest.skipUnless(os.name == "nt", "ein eigenes Konsolenfenster gibt es so nur unter Windows")
    def test_mit_zustimmung_ein_eigenes_konsolenfenster(self) -> None:
        self._klicken(antwort=True)
        self.assertEqual(1, len(self.gestartet))
        befehl, anlauf = self.gestartet[0]
        self.assertEqual(wee_tools.startbefehl(eingefroren=False, programm=sys.executable,
                                               hauptskript=os.path.abspath(APP.__file__)),
                         befehl)
        self.assertEqual(wee_tools.CREATE_NEW_CONSOLE, anlauf["creationflags"])
        self.assertEqual("1", anlauf["env"][wee_tools.UMGEBUNG_PYINSTALLER_NEU])
        self.assertEqual("de", anlauf["env"][wee_tools.UMGEBUNG_SPRACHE])
        self.assertEqual(anlauf["cwd"], anlauf["env"][wee_tools.UMGEBUNG_ARBEITSORDNER])
        self.assertTrue(os.path.isdir(anlauf["cwd"]))
        self.assertTrue(any("weetools.gestartet" in str(z) for z in self.protokoll))

    def test_ohne_pyserial_eine_klare_meldung_vor_der_frage(self) -> None:
        echt = importlib.util.find_spec

        def _finden(name, *argumente, **optionen):
            return None if name == "serial" else echt(name, *argumente, **optionen)

        self._klicken(antwort=True, finden=_finden)
        self.assertEqual([], self.gestartet)
        self.assertEqual([], self.fragen)
        self.assertTrue(any(isinstance(z, tuple) and "weetools.kein_pyserial" in str(z)
                            for z in self.protokoll))


class BerichtTests(unittest.TestCase):
    """Werkzeugbestand, Pruefliste und Lizenzdatei."""

    def test_der_werkzeugbestand_nennt_fassung_und_quelle(self) -> None:
        bericht = Diagnosebericht(mitgeliefert_finden=lambda rel: str(PROJEKT / rel))
        teile = {t.name: t for t in bericht._bestandteile_sammeln()}
        self.assertIn("PS5 Wee Tools", teile)
        self.assertEqual("0.1.8", teile["PS5 Wee Tools"].fassung)
        self.assertEqual(wee_tools.QUELLE, teile["PS5 Wee Tools"].quelle)

    def test_pyserial_steht_in_der_pruefliste(self) -> None:
        self.assertIn(("pyserial", "serial", "pyserial"),
                      APP.PS5ConverterGUI._GEPRUEFTE_BIBLIOTHEKEN)

    def test_die_lizenzdatei_nennt_werkzeug_und_bibliothek(self) -> None:
        text = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("PS5 Wee Tools 0.1.8", text)
        self.assertIn("**pyserial**", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
