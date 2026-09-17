# -*- coding: utf-8 -*-
"""Tests fuer die Bruecke zu ``prosperopkg``.

Das Werkzeug baut PS5-Pakete und laeuft als eigener Prozess, weil die
Bibliothek darunter unter GPL-3 steht (siehe
``ProsperoPkg-2.5/UPSTREAM.md``). Geprueft wird hier vor allem das
Zusammenspiel: Wie die Ausgabe gelesen wird und was bei einem Abbruch
geschieht.

Die Ausgabe wird nachgestellt, damit die Tests ohne das Werkzeug laufen.
Am Ende steht ein Test, der das echte Werkzeug benutzt, falls es liegt -
er ueberspringt sich sonst selbst.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

from ps5_validator.utils import prosperopkg as pp

BEREIT_AUSGABE = [
    "AppRoot              : F:\\Game Dumps\\Arkanoid Eternal Battle",
    "IsLaunchReady        : True",
    "HasEboot             : True",
    "HasParamJson         : True",
    "RequiresDebugConsole : True",
    "Modules              : 5",
    "RESULT: READY",
]

BLOCKIERT_AUSGABE = [
    "Modules              : 20",
    "BLOCKER: SignedEncrypted\tfakelib/libSceAgc.sprx",
    "BLOCKER: SignedEncrypted\tfakelib/libSceAgcDriver.sprx",
    "ISSUE: Module 'fakelib/libSceAgc.sprx' is signed and encrypted;"
    " it will not start on a debug-mode console.",
    "RESULT: NOT_READY",
]


def _lauf(zeilen, code=0):
    """Ersetzt _laufen_lassen durch eine feste Ausgabe."""
    def gefangen(argumente, melden=None, zeitgrenze=None,
                 prozess_ablage=None, texte=None):
        if melden is not None:
            for z in zeilen:
                melden(z)
        return (code, list(zeilen))
    return gefangen


class ErgebniszeileTest(unittest.TestCase):
    """Die letzte RESULT-Zeile traegt das Ergebnis."""

    def test_sie_wird_gefunden(self) -> None:
        self.assertEqual(pp._ergebniszeile(BEREIT_AUSGABE), "READY")

    def test_die_letzte_gewinnt(self) -> None:
        """Ein Pfad kann selbst 'RESULT:' enthalten - die letzte zaehlt."""
        zeilen = ["RESULT: alt", "irgendwas", "RESULT: neu"]
        self.assertEqual(pp._ergebniszeile(zeilen), "neu")

    def test_ohne_ergebniszeile_kommt_nichts(self) -> None:
        self.assertEqual(pp._ergebniszeile(["nur", "Fortschritt"]), "")

    def test_ein_pfad_mit_doppelpunkt_bleibt_heil(self) -> None:
        """Unter Windows steht im Pfad ein Doppelpunkt."""
        self.assertEqual(
            pp._ergebniszeile([r"RESULT: E:\Test\Spiel.pkg"]),
            r"E:\Test\Spiel.pkg")


class PruefenTest(unittest.TestCase):
    """Was ``inspect`` liefert."""

    def test_ein_startbereites_backup(self) -> None:
        with mock.patch.object(pp, "_laufen_lassen", _lauf(BEREIT_AUSGABE)):
            erg = pp.pruefen("egal")
        self.assertTrue(erg["bereit"])
        self.assertEqual(erg["blocker"], [])
        self.assertEqual(erg["hinweise"], [])

    def test_ein_blockiertes_backup(self) -> None:
        with mock.patch.object(pp, "_laufen_lassen",
                               _lauf(BLOCKIERT_AUSGABE)):
            erg = pp.pruefen("egal")
        self.assertFalse(erg["bereit"])
        self.assertEqual(len(erg["blocker"]), 2)
        self.assertEqual(erg["blocker"][0],
                         ("SignedEncrypted", "fakelib/libSceAgc.sprx"))
        self.assertEqual(len(erg["hinweise"]), 1)

    def test_jede_zeile_wird_weitergereicht(self) -> None:
        """Der Fortschritt gehoert unveraendert ins Protokollfenster."""
        gesehen = []
        with mock.patch.object(pp, "_laufen_lassen", _lauf(BEREIT_AUSGABE)):
            pp.pruefen("egal", melden=gesehen.append)
        self.assertEqual(gesehen, BEREIT_AUSGABE)

    def test_ein_abbruch_wird_gemeldet(self) -> None:
        with mock.patch.object(pp, "_laufen_lassen",
                               _lauf(["[FEHLER] kaputt"], code=3)):
            with self.assertRaises(pp.ProsperoFehler) as fall:
                pp.pruefen("egal")
        self.assertIn("3", str(fall.exception))


class BauenTest(unittest.TestCase):
    """Was ``build`` liefert."""

    def setUp(self) -> None:
        import tempfile

        self.ordner = tempfile.mkdtemp(prefix="ps5conv_pkgbau_")
        self.pkg = os.path.join(self.ordner, "Spiel.pkg")
        with open(self.pkg, "wb") as datei:
            datei.write(b"\x7fFIH")

    def tearDown(self) -> None:
        import shutil

        shutil.rmtree(self.ordner, ignore_errors=True)

    def test_der_pfad_kommt_zurueck(self) -> None:
        with mock.patch.object(pp, "_laufen_lassen",
                               _lauf(["Baue ...", "RESULT: " + self.pkg])):
            self.assertEqual(pp.bauen("quelle", self.ordner), self.pkg)

    def test_ein_pfad_der_nicht_existiert_ist_ein_fehler(self) -> None:
        with mock.patch.object(pp, "_laufen_lassen",
                               _lauf(["RESULT: C:\\gibtsnicht.pkg"])):
            with self.assertRaises(pp.ProsperoFehler):
                pp.bauen("quelle", self.ordner)

    def test_ohne_ergebniszeile_ist_es_ein_fehler(self) -> None:
        with mock.patch.object(pp, "_laufen_lassen", _lauf(["fertig?"])):
            with self.assertRaises(pp.ProsperoFehler):
                pp.bauen("quelle", self.ordner)

    def test_lizenzfrei_ist_die_vorgabe(self) -> None:
        """Ein echter rif laesst sich am Rechner nicht erzeugen."""
        gemerkt = {}

        def gefangen(argumente, melden=None, zeitgrenze=None,
                     prozess_ablage=None, texte=None):
            gemerkt["argumente"] = argumente
            return (0, ["RESULT: " + self.pkg])

        with mock.patch.object(pp, "_laufen_lassen", gefangen):
            pp.bauen("quelle", self.ordner)
        self.assertIn("--license-free", gemerkt["argumente"])
        self.assertNotIn("--fake-sign", gemerkt["argumente"])

    def test_fake_signieren_laesst_sich_zuschalten(self) -> None:
        gemerkt = {}

        def gefangen(argumente, melden=None, zeitgrenze=None,
                     prozess_ablage=None, texte=None):
            gemerkt["argumente"] = argumente
            return (0, ["RESULT: " + self.pkg])

        with mock.patch.object(pp, "_laufen_lassen", gefangen):
            pp.bauen("quelle", self.ordner, fake_signieren=True)
        self.assertIn("--fake-sign", gemerkt["argumente"])


class FehlendesWerkzeugTest(unittest.TestCase):
    """Fehlt das Werkzeug, steht das im Klartext da."""

    def test_die_meldung_nennt_den_erwarteten_ort(self) -> None:
        with mock.patch.object(pp, "werkzeug_finden", return_value=""):
            with self.assertRaises(pp.ProsperoFehler) as fall:
                pp._laufen_lassen(["inspect"])
        text = str(fall.exception)
        self.assertIn(pp.WERKZEUGORDNER, text)


class EchtesWerkzeugTest(unittest.TestCase):
    """Mit dem wirklich mitgelieferten Werkzeug - sonst uebersprungen."""

    def setUp(self) -> None:
        self.programm = pp.werkzeug_finden()
        if not self.programm:
            self.skipTest("prosperopkg liegt nicht bereit")

    def test_es_laesst_sich_starten(self) -> None:
        code, zeilen = pp._laufen_lassen(["--help"], zeitgrenze=60.0)
        self.assertTrue(zeilen, "Das Werkzeug hat nichts gesagt.")
        self.assertTrue(any("inspect" in z for z in zeilen),
                        "Die Hilfe nennt inspect nicht: %s" % zeilen[:3])

    def test_ein_unsinniger_ordner_wird_abgewiesen(self) -> None:
        with self.assertRaises(pp.ProsperoFehler):
            pp.pruefen(os.path.join(os.path.dirname(self.programm),
                                    "gibtsnicht"))


class AuslieferungTests(unittest.TestCase):
    """Was im Ordner ``win-x64`` liegen darf - und was nicht.

    Am 01.09.2026 fand ein Durchgang zwei ``.pdb`` im ausgelieferten
    Ordner. Fehlersuchangaben tragen zweierlei nach draussen: den
    absoluten Baupfad des Rechners, auf dem gebaut wurde, und eine
    SourceLink-Karte auf das Repository, aus dem gebaut wurde.
    ``prosperopkg.pdb`` zeigte damit auf ein bereits geloeschtes
    Repository, ``LibProsperoPkg.pdb`` (571 KB) auf ein zweites.

    Gebraucht wurden sie nirgends: Der Ordner steht nicht in
    ``PS5ImageConverter_Pro.spec``, kommt also gar nicht in die EXE,
    und die Huelle gibt bei einem Fehler nur ``ex.GetType().Name`` und
    ``ex.Message`` aus - nie eine Stapelspur. Die Ausgabe von
    ``prosperopkg.exe`` war mit und ohne sie dieselbe.

    Sie kommen aber zurueck, sobald jemand nach der Anleitung neu baut -
    deshalb steht dort jetzt ``-p:DebugType=none``, und deshalb wird das
    hier festgehalten.
    """

    ORDNER = os.path.join("ProsperoPkg-2.5", "win-x64")

    def test_keine_fehlersuchangaben_im_ordner(self) -> None:
        import glob

        gefunden = glob.glob(os.path.join(self.ORDNER, "*.pdb"))
        self.assertEqual(
            gefunden, [],
            "Fehlersuchangaben im Auslieferungsordner: %s. Sie tragen "
            "den Baupfad und das Baurepository nach draussen und werden "
            "hier nicht gebraucht. Mit -p:DebugType=none bauen."
            % ", ".join(os.path.basename(p) for p in gefunden))

    def test_was_gebraucht_wird_liegt_noch_da(self) -> None:
        """Die Gegenrichtung: nicht zuviel weggeraeumt."""
        for name in ("prosperopkg.exe", "prosperopkg.dll",
                     "prosperopkg.runtimeconfig.json",
                     "LibProsperoPkg.dll"):
            with self.subTest(datei=name):
                self.assertTrue(
                    os.path.isfile(os.path.join(self.ORDNER, name)),
                    "%s fehlt - ohne sie laeuft das Werkzeug nicht." % name)

    def test_die_anleitung_baut_ohne_sie(self) -> None:
        """Sonst kommen sie beim naechsten Neubau zurueck."""
        text = io.open(os.path.join("ProsperoPkg-2.5", "UPSTREAM.md"),
                       encoding="utf-8", errors="replace").read()
        # Im Befehlsblock nachsehen, nicht im Fliesstext: Die Erklaerung
        # darunter nennt den Schalter ebenfalls, und eine Suche ueber die
        # ganze Datei bliebe gruen, wenn er aus dem Befehl verschwaende.
        anfang = text.index("dotnet build")
        block = text[anfang:text.index("```", anfang)]
        self.assertIn("-p:DebugType=none", block,
                      "Der Neubaubefehl legt wieder .pdb an.")


class ZeitgrenzeTests(unittest.TestCase):
    """Die zugesagte Zeitgrenze muss auch greifen, wenn das Werkzeug haengt.

    Bis zum 05.09.2026 hing sie allein an ``lauf.wait(timeout=...)`` - und
    dorthin kommt der Ablauf erst, wenn die Leseschleife darueber fertig ist.
    ``for zeile in lauf.stdout`` blockiert aber ohne jede Frist: Bleibt das
    Werkzeug stehen, ohne seine Ausgabe zu schliessen, wartete der Aufrufer
    unbegrenzt. Der ``TimeoutExpired``-Zweig war damit unerreichbar.

    Nachgemessen an einem Prozess, der eine Zeile schreibt und dann fuenf
    Minuten schlaeft: alter Stand ohne Abbruch bis mindestens 25 s, neuer
    bricht nach 3,1 s ab.

    Gefahren wird mit dem Python-Interpreter als "Werkzeug" - so braucht die
    Pruefung weder prosperopkg noch .NET und ist in Sekunden durch.
    """

    HAENGER = ("import sys, time\n"
               "print('los', flush=True)\n"
               "time.sleep(300)\n")

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="prospero_zeit_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)
        self.skript = os.path.join(self.ordner, "haenger.py")
        with open(self.skript, "w", encoding="utf-8") as datei:
            datei.write(self.HAENGER)
        self._echtes_werkzeug = pp.werkzeug_finden
        pp.werkzeug_finden = lambda: sys.executable
        self.addCleanup(
            setattr, pp, "werkzeug_finden", self._echtes_werkzeug)

    def test_haengendes_werkzeug_wird_abgebrochen(self) -> None:
        start = time.perf_counter()
        with self.assertRaises(pp.ProsperoFehler) as gefangen:
            pp._laufen_lassen([self.skript], zeitgrenze=3.0)
        gebraucht = time.perf_counter() - start
        self.assertIn("Zeitgrenze", str(gefangen.exception))
        self.assertLess(
            gebraucht, 30.0,
            "Erst nach %.0f s abgebrochen - die Zeitgrenze greift nicht "
            "waehrend des Lesens." % gebraucht)

    def test_die_grenze_eines_spielbaus_waechst_mit_der_quelle(self) -> None:
        """Fest zwei Stunden beendeten jeden Bau ab etwa 23 GB (17.09.2026).

        Gemessen sind 3,3 MB/s; ein 50-GB-Titel braucht rund vier Stunden.
        Geprueft an 30 kB mit einem auf 1 B/s gesetzten Durchsatz.
        """
        quelle = os.path.join(self.ordner, "dump")
        os.makedirs(os.path.join(quelle, "sce_sys"))
        for name, groesse in (("eboot.bin", 20_000), ("sce_sys/param.json", 10_000)):
            with open(os.path.join(quelle, name), "wb") as datei:
                datei.write(b"x" * groesse)
        gemerkt = {}

        def gefangen(argumente, melden=None, zeitgrenze=None,
                     prozess_ablage=None, texte=None):
            gemerkt["zeitgrenze"] = zeitgrenze
            return (0, ["RESULT: " + self.skript])

        with mock.patch.object(pp, "MINDESTDURCHSATZ_BYTES_S", 1), \
                mock.patch.object(pp, "MINDESTZEITGRENZE_S", 10.0), \
                mock.patch.object(pp, "_laufen_lassen", gefangen):
            self.assertEqual(30_000.0, pp.zeitgrenze_fuer(quelle))
            self.assertEqual(10.0, pp.zeitgrenze_fuer(self.ordner + "_gibts_nicht"))
            pp.bauen(quelle, self.ordner)
            self.assertEqual(30_000.0, gemerkt["zeitgrenze"],
                             "bauen() reicht die feste Grenze durch.")
            # Wer eine Grenze nennt, bekommt genau die.
            pp.bauen(quelle, self.ordner, zeitgrenze=5.0)
            self.assertEqual(5.0, gemerkt["zeitgrenze"])

    def test_ein_kurzer_lauf_wird_nicht_abgebrochen(self) -> None:
        """Gegenrichtung: Der Wecker darf nicht zu frueh zuschlagen."""
        kurz = os.path.join(self.ordner, "kurz.py")
        with open(kurz, "w", encoding="utf-8") as datei:
            datei.write("print('fertig')\n")
        rc, zeilen = pp._laufen_lassen([kurz], zeitgrenze=30.0)
        self.assertEqual(0, rc)
        self.assertIn("fertig", zeilen)


class ProzessAblageTests(unittest.TestCase):
    """Der laufende Prozess muss von aussen erreichbar sein.

    Sonst laesst sich ein Bau nicht abbrechen: Der Schliessen-Knopf des
    Fensters rief nur ``win.destroy``, der prosperopkg-Prozess lief mit seiner
    Zeitgrenze von bis zu zwei Stunden weiter und schrieb weiter in den
    Zielordner. Protokoll und Statuszeile liefen dabei ins Leere - der
    Anwender glaubte abgebrochen zu haben.
    """

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="prospero_ablage_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)
        self.skript = os.path.join(self.ordner, "lang.py")
        with open(self.skript, "w", encoding="utf-8") as datei:
            datei.write("import time\nprint('laeuft', flush=True)\ntime.sleep(60)\n")
        self._echtes_werkzeug = pp.werkzeug_finden
        pp.werkzeug_finden = lambda: sys.executable
        self.addCleanup(setattr, pp, "werkzeug_finden", self._echtes_werkzeug)

    def test_der_prozess_landet_in_der_ablage_und_laesst_sich_beenden(self) -> None:
        import threading

        ablage: dict = {}

        def _lauf() -> None:
            try:
                pp._laufen_lassen([self.skript], zeitgrenze=120.0,
                                  prozess_ablage=ablage)
            except pp.ProsperoFehler:
                pass

        faden = threading.Thread(target=_lauf, daemon=True)
        faden.start()
        frist = time.perf_counter() + 10.0
        while time.perf_counter() < frist and "prozess" not in ablage:
            time.sleep(0.05)
        self.assertIn("prozess", ablage,
                      "Der Prozess ist von aussen nicht erreichbar - ein "
                      "Abbruch waere unmoeglich.")

        ablage["prozess"].terminate()
        faden.join(15)
        self.assertFalse(faden.is_alive(),
                         "Der Lauf ging nach terminate() weiter.")


class FassungsangabeTests(unittest.TestCase):
    """Welche LibProsperoPkg eingebaut ist, muss ablesbar sein.

    Der Ordner heisst weiterhin ``ProsperoPkg-2.5``, enthaelt seit v1.9.21
    aber **LibProsperoPkg 2.6.0** - die Zahl im Namen ist als Versionsangabe
    also irrefuehrend. Gerade sie entscheidet aber, ob ein gebautes Paket die
    Konsolenkorrekturen der 2.6.0 traegt. An der fertigen Programmdatei war
    das bis zum 16.09.2026 ueberhaupt nicht abzulesen: Im Diagnosebericht
    standen MkPFS, UFS2Tool, AMPR EMU und ein Dutzend Bibliotheken - nur
    ausgerechnet die, die das PKG baut, fehlte.
    """

    WURZEL = os.path.dirname(os.path.abspath(__file__))

    def _angaben(self) -> dict:
        import json

        pfad = os.path.join(self.WURZEL, pp.WERKZEUGORDNER, "fassung.json")
        self.assertTrue(os.path.isfile(pfad),
                        "fassung.json fehlt neben den Plattformbauten: %s" % pfad)
        with io.open(pfad, encoding="utf-8") as datei:
            return json.load(datei)

    def test_die_fassungsdatei_nennt_die_bibliothek(self):
        angaben = self._angaben()
        fassung = str(angaben.get("fassung") or "").strip()
        self.assertTrue(fassung, "fassung.json nennt keine Fassung.")
        self.assertNotEqual("2.5", fassung,
                            "Die Datei gibt die Ordnerzahl wieder statt der "
                            "wirklich eingebauten Bibliotheksfassung.")
        self.assertTrue(str(angaben.get("quelle") or "").strip(),
                        "Ohne Quelle laesst sich die Fassung nicht einordnen.")

    def test_der_ordnername_weicht_bewusst_ab(self):
        """Gegenprobe: Die Abweichung ist Absicht, kein Versehen.

        Wer den Ordner umbenennt, muss .spec, prosperopkg.py und die Tests
        mitziehen. Dieser Test haelt fest, dass die Zahl im Namen **nicht**
        die Bibliotheksversion meint - damit sie niemand "korrigiert".
        """
        self.assertEqual("ProsperoPkg-2.5", pp.WERKZEUGORDNER)
        self.assertNotIn(str(self._angaben().get("fassung")),
                         pp.WERKZEUGORDNER)

    def test_die_diagnose_liest_die_fassungsdatei(self):
        """Ohne den Leseblock stuende die Angabe nirgends im Bericht."""
        pfad = os.path.join(self.WURZEL, "ps5_validator", "utils",
                            "diagnose_befund.py")
        with io.open(pfad, encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertIn("fassung.json", quelle,
                      "Der Diagnosebericht liest die Fassungsdatei nicht mehr.")
        self.assertIn("LibProsperoPkg (PKG-Bau)", quelle,
                      "Der Eintrag im Werkzeuginventar heisst anders - dann "
                      "misst dieser Test nichts.")

    def test_lizenzliste_und_oberflaeche_nennen_keine_andere_fassung(self):
        """Die Lizenzliste nannte bis zum 17.09.2026 noch 2.5, ebenso der
        Hinweis im PKG-Reader - eingebaut ist seit v1.9.21 die 2.6.0."""
        import re

        from ps5_validator.utils.i18n import STRINGS

        fassung = str(self._angaben().get("fassung"))
        with io.open(os.path.join(self.WURZEL, "THIRD_PARTY_LICENSES.md"),
                     encoding="utf-8") as datei:
            lizenzen = datei.read()
        self.assertIn("LibProsperoPkg %s" % fassung, lizenzen)
        genannt = re.compile(r"LibProsperoPkg (\d+(?:\.\d+)+)", re.I)
        falsch = sorted({"%s: %s" % (name, treffer)
                         for name, text in [("THIRD_PARTY_LICENSES.md", lizenzen)]
                         + [("%s/%s" % (k, s), t) for k, v in STRINGS.items()
                            for s, t in v.items()]
                         for treffer in genannt.findall(text)
                         if treffer != fassung})
        self.assertEqual([], falsch, "Nennt eine andere als die eingebaute Fassung.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
