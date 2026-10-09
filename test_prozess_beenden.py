# -*- coding: utf-8 -*-
"""Abbrechen beendet den ganzen Prozessbaum (``utils/prozess_beenden.py``, seit v1.9.71).

Der Anlass (Nutzermeldung 09.10.2026): "Das Abbrechen im PS4 PKG Dump & Image Converter funktioniert nicht
korrekt, es haengt dabei fest." Die Ursache war ``Popen.terminate()``: Das Werkzeug laeuft als Selbstaufruf der
gebauten EXE (Starter + Programm + Arbeiter). Nach ``terminate()`` lebten in einer gebauten Onefile-Probe drei von
vier Prozessen weiter und hielten die Ausgabeleitung offen - das Fenster wartete, bis der Lauf von selbst endete.
Unter der ``.venv`` fiel es nie auf, weil deren Starter seine Nachkommen in einen Job nimmt.

Die Pruefungen starten deshalb den **Basis**-Interpreter (``sys._base_executable``), der keinen Job mitbringt:
Ein Baum aus Eltern, Kind und Enkel, die alle die Ausgabeleitung erben - genau die Lage in der EXE.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import psutil                                                    # noqa: E402

from ps5_validator.utils import ps4_werkzeug, ps4pkg_aufgaben as au, prozess_beenden as pb   # noqa: E402

#: Jede Stufe meldet ihre Kennung, startet die naechste (sie erbt die Ausgabeleitung) und schlaeft.
BAUM = """\
import os, subprocess, sys, time
stufe = int(sys.argv[-1])
print("PID", stufe, os.getpid(), flush=True)
if stufe < 2:
    subprocess.Popen([sys.executable, __file__, str(stufe + 1)])
time.sleep(120)
"""


def _python() -> str:
    """Der Interpreter ohne Venv-Starter (der nimmt Nachkommen in einen Job und versteckt den Fehler)."""
    return getattr(sys, "_base_executable", "") or sys.executable


def _bis(bedingung, grenze: float = 10.0) -> bool:
    ende = time.monotonic() + grenze
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def _lebt(pid: int, start: float) -> bool:
    try:
        p = psutil.Process(pid)
        return abs(p.create_time() - start) < 0.01 and p.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


class _BaumTest(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.skript = self.tmp / "baum.py"
        self.skript.write_text(BAUM, encoding="utf-8")
        self._alle: list[tuple[int, float]] = []
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self) -> None:
        for pid, start in self._alle:
            try:
                if _lebt(pid, start):
                    psutil.Process(pid).kill()
            except psutil.Error:
                pass

    def _merken(self, pids: list[int]) -> None:
        for pid in pids:
            try:
                self._alle.append((pid, psutil.Process(pid).create_time()))
            except psutil.Error:
                pass

    def _zeilen(self, prozess, anzahl: int, frist: float = 30.0) -> list[str]:
        """Liest ``anzahl`` Zeilen aus der Ausgabe - in einem Faden, damit ein Fehler den Test nicht aufhaengt."""
        eingang: "queue.Queue[str]" = queue.Queue()

        def lesen() -> None:
            for zeile in prozess.stdout:
                eingang.put(zeile.strip())

        #: Endet erst, wenn die Ausgabeleitung zu ist - also wenn kein Nachkomme sie mehr offen haelt.
        self.leser = threading.Thread(target=lesen, daemon=True)
        self.leser.start()
        erg: list[str] = []
        ende = time.monotonic() + frist
        while len(erg) < anzahl and time.monotonic() < ende:
            try:
                erg.append(eingang.get(timeout=0.2))
            except queue.Empty:
                pass
        self.assertEqual(anzahl, len(erg), "Der Prozessbaum meldete sich nicht: %r" % erg)
        return erg

    def _baum_starten(self, **extra) -> "tuple[subprocess.Popen, list[int]]":
        p = subprocess.Popen([_python(), str(self.skript), "0"], stdout=subprocess.PIPE, text=True, **extra)
        self.addCleanup(lambda: p.poll() is None and p.kill())
        zeilen = self._zeilen(p, 3)
        pids = sorted(int(z.split()[2]) for z in zeilen)
        self._merken([p.pid] + pids)
        return p, pids

    def _alle_weg(self, grenze: float = 10.0) -> None:
        self.assertTrue(_bis(lambda: not any(_lebt(pid, start) for pid, start in self._alle), grenze),
                        "Es leben noch: %s" % [pid for pid, start in self._alle if _lebt(pid, start)])


class BaumBeendenTests(_BaumTest):

    def test_beendet_kind_und_enkel_und_die_leitung_schliesst_sich(self) -> None:
        p, pids = self._baum_starten()
        beginn = time.monotonic()
        self.assertTrue(pb.baum_beenden(p, frist=10))
        self.assertLess(time.monotonic() - beginn, 8.0)
        self._alle_weg()
        # Die Leitung ist zu: Wer sie liest, kommt ans Ende (vorher wartete das Fenster auf den Lauf des Enkels).
        self.leser.join(10)
        self.assertFalse(self.leser.is_alive(), "Die Ausgabeleitung ist noch offen - ein Nachkomme lebt")

    def test_ohne_psutil_greift_der_rueckfall(self) -> None:
        extra = {} if os.name == "nt" else {"start_new_session": True}     # unter Linux/macOS: eigene Gruppe
        p, pids = self._baum_starten(**extra)
        with mock.patch.object(pb, "_psutil", return_value=None):
            self.assertTrue(pb.baum_beenden(p, frist=10))
        self._alle_weg()

    def test_ein_schon_beendeter_prozess_wird_nicht_ueber_seine_alte_kennung_angefasst(self) -> None:
        """Die Ablage haelt den Prozess der vorigen Stufe; seine Kennung kann inzwischen einem fremden gehoeren."""
        p = subprocess.Popen([_python(), "-c", "pass"])
        p.wait()
        ersatz = mock.Mock()
        with mock.patch.object(pb, "_psutil", return_value=ersatz):
            self.assertTrue(pb.baum_beenden(p))
        ersatz.Process.assert_not_called()

    def test_ein_objekt_ohne_kennung_bekommt_wenigstens_terminate(self) -> None:
        aufrufe: list[str] = []

        class Attrappe:
            def terminate(self) -> None:
                aufrufe.append("terminate")

        self.assertTrue(pb.baum_beenden(Attrappe()))
        self.assertEqual(["terminate"], aufrufe)


class LaufAbbruchTests(_BaumTest):
    """``ps4_werkzeug.lauf`` mit dem Hilfsbaum statt PS4 FFPFSC."""

    def setUp(self) -> None:
        super().setUp()
        patcher = mock.patch.object(ps4_werkzeug, "befehl",
                                    lambda hauptdatei="": [_python(), str(self.skript), "--ps4ffpsc"])
        patcher.start()
        self.addCleanup(patcher.stop)

    def _lauf(self, ablage: dict, zeilen: list):
        return ps4_werkzeug.lauf(["0"], arbeitsordner=str(self.tmp), zeile_callback=zeilen.append,
                                 prozess_ablage=ablage, umgebung_bauen=lambda _ordner: dict(os.environ))

    def test_ein_gesetzter_abbruch_startet_gar_keinen_prozess(self) -> None:
        stopp = threading.Event()
        stopp.set()
        ablage = {"abbruch": stopp}
        rc, text = self._lauf(ablage, [])
        self.assertEqual(ps4_werkzeug.RC_ABGEBROCHEN, rc)
        self.assertNotIn("prozess", ablage)

    def test_ein_abbruch_zwischen_frage_und_anmeldung_beendet_den_neuen_prozess(self) -> None:
        """Der Abbruch kam, nachdem die Aufgabe nach dem Prozess gesucht hatte und bevor er angemeldet war."""
        class Spaet(threading.Event):
            def __init__(self) -> None:
                super().__init__()
                self.fragen = 0

            def is_set(self) -> bool:
                self.fragen += 1
                return self.fragen > 1            # die erste Frage (vor dem Start) sagt nein, jede weitere ja

        zeilen: list[str] = []
        beginn = time.monotonic()
        rc, _text = self._lauf({"abbruch": Spaet()}, zeilen)
        self.assertLess(time.monotonic() - beginn, 25.0, "Der Lauf ging nach dem Abbruch weiter")
        self.assertNotEqual(0, rc)
        self._merken([int(z.split()[2]) for z in zeilen if z.startswith("PID")])
        self._alle_weg()

    def test_abbrechen_beendet_den_lauf_samt_enkeln_und_die_aufgabe_endet(self) -> None:
        """Ende zu Ende: Warteschlange -> lauf -> Prozessbaum. Mit ``terminate()`` allein haengt das ~2 Minuten."""
        zeilen: list[str] = []

        def arbeit(a: au.Aufgabe) -> None:
            self._lauf(a.prozess_ablage, zeilen)
            a.pruefen_abbruch()

        schlange = au.Warteschlange()
        self.addCleanup(schlange.alle_abbrechen)
        aufgabe = schlange.hinzufuegen("test", "Baum", arbeit)
        self.assertTrue(_bis(lambda: len([z for z in zeilen if z.startswith("PID")]) >= 3, 30), zeilen)
        self._merken([int(z.split()[2]) for z in zeilen if z.startswith("PID")])
        beginn = time.monotonic()
        schlange.abbrechen(aufgabe.kennung)
        self.assertTrue(_bis(lambda: aufgabe.status in au.ENDZUSTAENDE, 20),
                        "Die Aufgabe endete nicht - der Lauf wartet auf seine Nachkommen")
        self.assertEqual(au.ABGEBROCHEN, aufgabe.status)
        self.assertLess(time.monotonic() - beginn, 15.0)
        self._alle_weg()


if __name__ == "__main__":
    unittest.main()
