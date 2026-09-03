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
    def gefangen(argumente, melden=None, zeitgrenze=None):
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

        def gefangen(argumente, melden=None, zeitgrenze=None):
            gemerkt["argumente"] = argumente
            return (0, ["RESULT: " + self.pkg])

        with mock.patch.object(pp, "_laufen_lassen", gefangen):
            pp.bauen("quelle", self.ordner)
        self.assertIn("--license-free", gemerkt["argumente"])
        self.assertNotIn("--fake-sign", gemerkt["argumente"])

    def test_fake_signieren_laesst_sich_zuschalten(self) -> None:
        gemerkt = {}

        def gefangen(argumente, melden=None, zeitgrenze=None):
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
