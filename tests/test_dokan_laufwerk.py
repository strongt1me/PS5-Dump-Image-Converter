# -*- coding: utf-8 -*-
"""Dokan-Laufwerke sauber ein- und aushaengen (``dokan_laufwerk``) und der Abbruch von ``_run_subprocess_logged``.

Fenstermessung vom 04.11.2026 (Aufgabe 4, zweimal wiederholt, mit Programmprotokoll):

* G4-ffpkg-folder scheiterte zweimal von drei Laeufen sofort: "Laufwerk W: bereit" nach 0,1 s, dann 13 statt 1166
  Dateien, dann robocopy "Zugriff auf Quellverzeichnis W:\\ ... Pfad nicht gefunden". Die Vorschau der Metadaten hatte
  dieselbe Datei auf demselben Buchstaben eingehaengt und hing sie wieder aus.
* Ein Abbruch in Aufgabe 4 liess robocopy 54 Minuten haengen ("0 B geschrieben"); mount_udf wurde hart beendet und
  das Laufwerk blieb im Explorer stehen.
"""
from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("dokan_laufwerk")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import dokan_laufwerk as dl        # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class _Prozess:
    """Stand-in fuer subprocess.Popen: lebt, bis terminate() gerufen wird."""

    def __init__(self, lebt: bool = True):
        self.lebt = lebt
        self.ereignisse: list[str] = []

    def poll(self):
        return None if self.lebt else 0

    def terminate(self):
        self.ereignisse.append("terminate")
        self.lebt = False

    def kill(self):
        self.ereignisse.append("kill")
        self.lebt = False

    def wait(self, timeout=None):
        self.ereignisse.append("wait")
        return 0


class BereitWartenTests(unittest.TestCase):

    def _listen(self, *folge):
        """os.listdir liefert nacheinander die Listen der Folge (danach immer die letzte)."""
        it = iter(folge)
        letzte = {"liste": []}

        def listdir(_pfad):
            try:
                letzte["liste"] = next(it)
            except StopIteration:
                pass
            return list(letzte["liste"])
        return listdir

    def _lauf(self, proc, folge, **kw):
        with mock.patch.object(dl.os.path, "exists", return_value=True), \
                mock.patch.object(dl.os, "listdir", self._listen(*folge)), \
                mock.patch.object(dl.time, "sleep", lambda _s: None):
            return dl.bereit_warten(proc, "W:", **kw)

    def test_stabile_liste_ist_bereit(self):
        self.assertTrue(self._lauf(_Prozess(), [["eboot.bin", "sce_sys"], ["eboot.bin", "sce_sys"]]))

    def test_eine_noch_wachsende_liste_ist_nicht_bereit(self):
        """Das Laufwerk der Vorschau zeigte 13 statt 1166 Dateien - eine Liste, die sich noch aendert, zaehlt nicht."""
        folge = [["a"], ["a", "b"], ["a", "b", "c"], ["a", "b", "c", "d"], ["a", "b", "c", "d", "e"]]
        self.assertFalse(self._lauf(_Prozess(), folge, versuche=5))

    def test_leeres_laufwerk_ist_nicht_bereit(self):
        self.assertFalse(self._lauf(_Prozess(), [[]], versuche=4))

    def test_beendeter_prozess_ist_nie_bereit(self):
        """os.path.exists haette das Laufwerk eines ANDEREN Prozesses als eigenes genommen."""
        self.assertFalse(self._lauf(_Prozess(lebt=False), [["a"], ["a"]]))

    def test_prozess_endet_waehrend_des_wartens(self):
        proc = _Prozess()
        aufrufe = {"n": 0}
        original = proc.poll

        def poll():
            aufrufe["n"] += 1
            if aufrufe["n"] > 2:
                proc.lebt = False
            return original()
        proc.poll = poll
        self.assertFalse(self._lauf(proc, [[], [], [], []], versuche=10))

    def test_abbruch_beendet_das_warten(self):
        self.assertFalse(self._lauf(_Prozess(), [["a"], ["a"]], abbruch=lambda: True))

    def test_unlesbares_laufwerk_wird_wie_leer_behandelt(self):
        def kaputt(_p):
            raise OSError("Dokan beschaeftigt")
        with mock.patch.object(dl.os.path, "exists", return_value=True), \
                mock.patch.object(dl.os, "listdir", kaputt), \
                mock.patch.object(dl.time, "sleep", lambda _s: None):
            self.assertFalse(dl.bereit_warten(_Prozess(), "W:", versuche=3))


class AushaengenTests(unittest.TestCase):

    def test_reihenfolge_erst_aushaengen_dann_prozess(self):
        proc = _Prozess()
        aufrufe: list = []

        def run(cmd, **_kw):
            aufrufe.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        belegt = iter([True, False])
        with mock.patch.object(dl, "IST_WINDOWS", True), \
                mock.patch.object(dl, "dokanctl_pfad", return_value="dokanctl.exe"), \
                mock.patch.object(dl.subprocess, "run", run), \
                mock.patch.object(dl, "laufwerk_belegt", lambda _b: next(belegt)), \
                mock.patch.object(dl.time, "sleep", lambda _s: None):
            self.assertTrue(dl.aushaengen("W:", proc))
        self.assertEqual(aufrufe, [["dokanctl.exe", "/u", "W"]])
        self.assertEqual(proc.ereignisse[:1], ["terminate"])

    def test_bleibt_der_buchstabe_belegt_kommt_mountvol_als_letzter_rueckfall(self):
        aufrufe: list = []

        def run(cmd, **_kw):
            aufrufe.append(cmd)
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch.object(dl, "IST_WINDOWS", True), \
                mock.patch.object(dl, "dokanctl_pfad", return_value=""), \
                mock.patch.object(dl.subprocess, "run", run), \
                mock.patch.object(dl, "laufwerk_belegt", lambda _b: True), \
                mock.patch.object(dl.time, "sleep", lambda _s: None), \
                mock.patch.object(dl.time, "monotonic", side_effect=[0.0, 0.0, 99.0, 99.0, 99.0]):
            self.assertFalse(dl.aushaengen("W:", None, warte_s=1.0))
        self.assertEqual(aufrufe, [["mountvol", "W:\\", "/D"]])

    def test_ein_haengender_prozess_wird_hart_beendet_und_haelt_nicht_auf(self):
        class Stur(_Prozess):
            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("mount_udf", timeout)

        proc = Stur()
        with mock.patch.object(dl, "IST_WINDOWS", True), \
                mock.patch.object(dl, "dokanctl_pfad", return_value=""), \
                mock.patch.object(dl, "laufwerk_belegt", lambda _b: False):
            self.assertTrue(dl.aushaengen("W:", proc, warte_s=0.5))
        self.assertIn("kill", proc.ereignisse)

    def test_ohne_dokanctl_und_ohne_prozess_schadet_es_nicht(self):
        with mock.patch.object(dl, "IST_WINDOWS", True), \
                mock.patch.object(dl, "dokanctl_pfad", return_value=""), \
                mock.patch.object(dl, "laufwerk_belegt", lambda _b: False):
            self.assertTrue(dl.aushaengen("W:", None))

    def test_ausserhalb_von_windows_tut_es_nichts(self):
        with mock.patch.object(dl, "IST_WINDOWS", False):
            self.assertFalse(dl.aushaengen("W:", _Prozess()))
            self.assertFalse(dl.laufwerk_belegt("W"))


class BuchstabenTests(unittest.TestCase):

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_ein_echtes_laufwerk_ist_belegt_ein_ungueltiges_auch(self):
        system = os.environ.get("SystemDrive", "C:")[0]
        self.assertTrue(dl.laufwerk_belegt(system))
        self.assertTrue(dl.laufwerk_belegt("1"), "kein Buchstabe: nie als frei behandeln")

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_der_freie_buchstabe_ist_wirklich_frei_und_kommt_von_hinten(self):
        buchstabe = dl.freier_buchstabe()
        if buchstabe is None:
            self.skipTest("kein Buchstabe frei")
        self.assertRegex(buchstabe, r"^[E-Z]:$")
        self.assertFalse(dl.laufwerk_belegt(buchstabe[0]))
        nochmal = dl.freier_buchstabe(ausser=(buchstabe,))
        self.assertNotEqual(nochmal, buchstabe)
        self.assertLess(nochmal, buchstabe if nochmal else "Z:") if nochmal else None

    def test_buchstabe_mit_liegengebliebener_zuordnung_zaehlt_als_belegt(self):
        """X:/Y:/Z: standen als OSFMount-Reste in der Geraeteliste, ohne in GetLogicalDrives zu erscheinen."""
        ok = {"Z"}
        with mock.patch.object(dl, "IST_WINDOWS", True), \
                mock.patch.object(dl, "laufwerk_belegt", lambda b: b.upper() in ok):
            self.assertEqual(dl.freier_buchstabe(), "Y:")
            self.assertEqual(dl.freier_buchstabe(ausser=("Y",)), "X:")

    def test_gemeinsame_sperre_ist_ein_rlock(self):
        self.assertIs(type(dl.SPERRE), type(threading.RLock()))
        with dl.SPERRE:
            with dl.SPERRE:
                pass

    def test_dokanctl_pfad_findet_eine_vorhandene_datei_oder_nichts(self):
        pfad = dl.dokanctl_pfad()
        self.assertIsInstance(pfad, str)
        if pfad:
            self.assertTrue(os.path.isfile(pfad))


class AbbruchTests(unittest.TestCase):
    """``_run_subprocess_logged``: bei_abbruch vor dem Beenden, und kein Haengen beim Schliessen der Ausgabe."""

    def _gui(self):
        gui = GUI.__new__(GUI)
        gui.protokoll = []
        gui._append_to_log = gui.protokoll.append
        gui._t = lambda schluessel, **w: schluessel
        return gui

    def test_bei_abbruch_wird_einmal_vor_dem_beenden_gerufen(self):
        gui = self._gui()
        with tempfile.TemporaryDirectory() as t:
            pidfile = os.path.join(t, "pid.txt")
            code = "import os,time;open(%r,'w').write(str(os.getpid()));time.sleep(30)" % pidfile
            zustand = {"n": 0, "lebte": None}

            def bei_abbruch():
                zustand["n"] += 1
                import psutil
                try:
                    zustand["lebte"] = psutil.pid_exists(int(Path(pidfile).read_text()))
                except Exception:  # noqa: BLE001
                    zustand["lebte"] = None

            fertig = threading.Event()

            def abbruch():
                return os.path.isfile(pidfile) and bool(Path(pidfile).read_text())   # erst, wenn der Prozess laeuft

            beginn = time.monotonic()
            rc = gui._run_subprocess_logged([sys.executable, "-c", code], timeout=60, line_callback=lambda _l: True,
                                            abbruch=abbruch, bei_abbruch=bei_abbruch)
            dauer = time.monotonic() - beginn
            fertig.set()
            self.assertEqual(rc, 130)
            self.assertEqual(zustand["n"], 1)
            self.assertTrue(zustand["lebte"], "bei_abbruch muss laufen, solange der Prozess noch lebt")
            self.assertLess(dauer, 15)
            import psutil
            pid = int(Path(pidfile).read_text())
            for _ in range(40):
                if not psutil.pid_exists(pid):
                    break
                time.sleep(0.25)
            self.assertFalse(psutil.pid_exists(pid), "der Prozess ist nach dem Abbruch beendet")

    def test_der_abbruch_kehrt_erst_zurueck_wenn_der_prozess_weg_ist(self):
        """Ein mehrfaediges robocopy schrieb nach terminate() noch weiter und lief dem Aufraeumen davon: Bei einem
        Abbruch nach 2 s blieben 26 MB im Zielordner liegen (gemessen 04.11.2026)."""
        import psutil
        gui = self._gui()
        with tempfile.TemporaryDirectory() as t:
            pidfile = os.path.join(t, "pid.txt")
            code = "import os,time;open(%r,'w').write(str(os.getpid()));time.sleep(30)" % pidfile
            # Der Basis-Interpreter: In einer venv ist sys.executable ein Startprogramm, das den eigentlichen Python als
            # Kind startet - die PID in der Datei waere dann nicht die des beendeten Prozesses.
            basis = getattr(sys, "_base_executable", None) or sys.executable
            rc = gui._run_subprocess_logged(
                [basis, "-c", code], timeout=60, line_callback=lambda _l: True,
                abbruch=lambda: os.path.isfile(pidfile) and bool(Path(pidfile).read_text()))
            pid = int(Path(pidfile).read_text())
            self.assertEqual(rc, 130)
            self.assertFalse(psutil.pid_exists(pid), "Der Prozess lebte beim Zurueckkehren noch")

    def test_ein_kindprozess_der_die_ausgabe_offen_haelt_blockiert_den_abbruch_nicht(self):
        """Der alte Code schloss stdout, waehrend der Lesefaden noch darauf wartete - und stand, bis der Kindprozess
        endete (gemessen: 894 s bei einem haengenden robocopy)."""
        gui = self._gui()
        with tempfile.TemporaryDirectory() as t:
            pidfile = os.path.join(t, "pid.txt")
            kind = "import time;time.sleep(12)"
            code = ("import os,sys,subprocess,time;open(%r,'w').write(str(os.getpid()));"
                    "subprocess.Popen([sys.executable,'-c',%r]);time.sleep(60)") % (pidfile, kind)
            beginn = time.monotonic()
            rc = gui._run_subprocess_logged(
                [sys.executable, "-c", code], timeout=120, line_callback=lambda _l: True,
                abbruch=lambda: os.path.isfile(pidfile) and bool(Path(pidfile).read_text()))
            dauer = time.monotonic() - beginn
        self.assertEqual(rc, 130)
        self.assertLess(dauer, 8, "Der Abbruch wartete auf das Ende des Kindprozesses (%.1f s)" % dauer)

    def test_ein_fehler_in_bei_abbruch_haelt_das_beenden_nicht_auf(self):
        gui = self._gui()

        def kaputt():
            raise RuntimeError("dokanctl weg")

        rc = gui._run_subprocess_logged([sys.executable, "-c", "import time;time.sleep(30)"], timeout=60,
                                        line_callback=lambda _l: True, abbruch=lambda: True, bei_abbruch=kaputt)
        self.assertEqual(rc, 130)


class VerdrahtungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            baum = ast.parse(fh.read())
        klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        cls.methoden = {m.name: ast.unparse(m) for m in klasse.body if isinstance(m, ast.FunctionDef)}

    def test_alle_einhaengestellen_nutzen_das_gemeinsame_modul(self):
        extraktion = self.methoden["_extract_ffpkg_to_folder_via_ufs2tool"]
        for name in ("dokan_laufwerk.SPERRE", "dokan_laufwerk.freier_buchstabe(", "dokan_laufwerk.bereit_warten(",
                     "dokan_laufwerk.aushaengen("):
            self.assertIn(name, extraktion, name)
        for datei in ("abbild_metadaten.py", "abbild_pruefen.py"):
            text = (PROJEKT / "ps5_validator" / "utils" / datei).read_text(encoding="utf-8")
            for name in ("dokan_laufwerk.SPERRE", "dokan_laufwerk.freier_buchstabe(", "dokan_laufwerk.bereit_warten(",
                         "dokan_laufwerk.aushaengen("):
                with self.subTest(datei=datei, name=name):
                    self.assertIn(name, text)
            self.assertNotIn("GetLogicalDrives", text, "Buchstabenwahl nur ueber dokan_laufwerk")
            self.assertNotIn("mountvol", text, "Aushaengen nur ueber dokan_laufwerk")

    def test_die_sperre_der_vorschau_ist_die_gemeinsame(self):
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        self.assertIn("self._ffpkg_preview_lock = dokan_laufwerk.SPERRE", quelle)

    def test_die_extraktion_haelt_die_sperre_bis_zum_ende_und_gibt_sie_im_finally_frei(self):
        text = self.methoden["_extract_ffpkg_to_folder_via_ufs2tool"]
        i_erwerb = text.find("sperre.acquire(")
        i_wahl = text.find("dokan_laufwerk.freier_buchstabe(")
        i_frei = text.rfind("sperre.release()")
        i_finally = text.rfind("finally:")
        self.assertGreater(i_erwerb, 0)
        self.assertLess(i_erwerb, i_wahl, "erst die Sperre, dann der Buchstabe")
        self.assertGreater(i_frei, i_finally, "die Sperre wird im letzten finally freigegeben")
        # Kein Weg zwischen Erwerb und try darf die Sperre vergessen: der Rueckweg ohne Buchstaben gibt sie frei.
        self.assertIn("sperre.release()", text[i_wahl:i_wahl + 200])

    def test_ein_abbruch_haengt_das_laufwerk_aus_bevor_robocopy_beendet_wird(self):
        text = self.methoden["_extract_ffpkg_to_folder_via_ufs2tool"]
        i_robo = text.find("robo_cmd,")
        self.assertGreater(i_robo, 0)
        self.assertIn("bei_abbruch=lambda: dokan_laufwerk.aushaengen(drive, mount_proc", text[i_robo:i_robo + 1500])

    def test_im_finally_wird_erst_ausgehaengt_dann_der_prozess_beendet(self):
        text = self.methoden["_extract_ffpkg_to_folder_via_ufs2tool"]
        # Das letzte "run['on'] = False" steht im aeusseren finally; darin ist die Freigabe der Sperre noch einmal verschachtelt.
        letztes_finally = text[text.rfind("run['on'] = False"):]
        self.assertIn("dokan_laufwerk.aushaengen(drive, mount_proc)", letztes_finally)
        self.assertLess(letztes_finally.find("aushaengen("), letztes_finally.find("sperre.release()"))
        self.assertNotIn("mount_proc.terminate()", letztes_finally, "kein harter Abschuss ohne Aushaengen")


if __name__ == "__main__":
    unittest.main()
