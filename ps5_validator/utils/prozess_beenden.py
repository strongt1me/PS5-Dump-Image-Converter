# -*- coding: utf-8 -*-
"""Einen Prozess samt allen Nachkommen beenden (seit v1.9.71).

Warum nicht ``Popen.terminate()``: Das Programm startet seine Werkzeuge zum Teil als Selbstaufruf
(``PS5_Dump_Image_Converter.exe --ps4ffpsc``, darin ``--ps4-mkpfs`` und dessen Arbeiter). Eine PyInstaller-Onefile-EXE
besteht aber aus **zwei** Prozessen - dem Starter, den ``Popen`` kennt, und dem eigentlichen Programm darunter. Wer nur den
Starter beendet, laesst das Programm weiterlaufen; es haelt auch die Ausgabeleitung offen, und das lesende Fenster
wartet dann, bis der ganze Lauf von selbst zu Ende ist. Gemessen am 09.10.2026 mit einer gebauten Onefile-Probe:
nach ``terminate()`` lebten drei von vier Prozessen weiter (unter der ``.venv`` nicht, deren Starter nimmt seinen
Kindprozess in einen Job mit - deshalb fiel es in der Entwicklung nie auf).

:func:`baum_beenden` merkt sich erst alle Nachkommen und beendet dann von oben nach unten, damit niemand Arbeiter
nachstartet; danach sucht es noch einmal nach Prozessen, die in der Zwischenzeit entstanden sind.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time

logger = logging.getLogger("PS5Converter.prozess_beenden")

#: Wie oft nach neu entstandenen Nachkommen gesucht wird, nachdem die erste Runde beendet wurde.
_NACHSUCHEN = 4


def _psutil():
    try:
        import psutil
    except ImportError:         # pragma: no cover - psutil gehoert zu den Abhaengigkeiten, ist aber optional
        return None
    return psutil


def _einfach_beenden(prozess) -> None:
    """Fuer Objekte ohne brauchbare Kennung (Tests, Attrappen): wenigstens ``terminate()``."""
    try:
        prozess.terminate()
    except Exception as exc:  # noqa: BLE001 - ein Prozess, der schon weg ist, ist kein Fehler
        logger.debug("terminate() fehlgeschlagen: %s", exc)


def _mit_psutil(psutil, prozess, pid: int, frist: float) -> bool:
    bekannt: dict = {}                 # pid -> Process (die Kennung enthaelt die Startzeit, PID-Wiederverwendung faellt auf)
    reihenfolge: list = []

    def aufnehmen(p) -> bool:
        if p.pid in bekannt or p.pid == os.getpid():
            return False
        bekannt[p.pid] = p
        reihenfolge.append(p)
        return True

    try:
        wurzel = psutil.Process(pid)
    except psutil.NoSuchProcess:
        wurzel = None
    if wurzel is not None:
        aufnehmen(wurzel)
        try:
            for kind in wurzel.children(recursive=True):
                aufnehmen(kind)
        except psutil.NoSuchProcess:
            pass

    def beenden(runde: list) -> None:
        for p in runde:                # von oben nach unten: Wer Arbeiter nachstartet, ist dann schon tot
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied as exc:
                logger.warning("Prozess %s nicht beendbar: %s", p.pid, exc)

    beenden(list(reihenfolge))
    ende = time.monotonic() + max(0.5, float(frist))
    for _ in range(_NACHSUCHEN):
        psutil.wait_procs(list(reihenfolge), timeout=min(1.0, max(0.05, ende - time.monotonic())))
        neu: list = []
        try:
            for q in psutil.process_iter(["pid", "ppid", "create_time"]):
                eltern = bekannt.get(q.info.get("ppid"))
                if eltern is None or q.pid in bekannt:
                    continue
                try:
                    jung_genug = (q.info.get("create_time") or 0.0) >= eltern.create_time() - 0.01
                except psutil.Error:
                    jung_genug = False
                if jung_genug and aufnehmen(q):
                    neu.append(q)
        except psutil.Error as exc:
            logger.debug("Prozessliste nicht lesbar: %s", exc)
        if not neu:
            break
        beenden(neu)
    uebrig = [p for p in reihenfolge if _lebt(psutil, p)]
    if uebrig and time.monotonic() < ende:
        _gesamt, uebrig = psutil.wait_procs(uebrig, timeout=max(0.05, ende - time.monotonic()))
        uebrig = [p for p in uebrig if _lebt(psutil, p)]
    if uebrig:
        logger.warning("Nach dem Beenden leben noch %d Prozesse: %s", len(uebrig), [p.pid for p in uebrig])
    else:
        logger.info("Prozessbaum beendet (%d Prozesse)", len(reihenfolge))
    _abholen(prozess, frist=0.5)
    return not uebrig


def _lebt(psutil, p) -> bool:
    try:
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _abholen(prozess, frist: float) -> None:
    """Holt den Rueckgabewert des eigenen Kindes ab (sonst bleibt unter Linux/macOS ein Zombie stehen)."""
    try:
        prozess.wait(timeout=frist)
    except Exception as exc:  # noqa: BLE001
        logger.debug("wait() nach dem Beenden: %s", exc)


def _ohne_psutil(prozess, pid: int, frist: float) -> bool:
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False,
                           timeout=max(1.0, frist), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            try:
                if os.getpgid(pid) == pid:      # eigene Prozessgruppe: ganze Gruppe
                    os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass
            prozess.kill()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Beenden ohne psutil: %s", exc)
        _einfach_beenden(prozess)
    try:
        prozess.wait(timeout=max(0.5, frist))
    except Exception:  # noqa: BLE001
        return False
    return True


def baum_beenden(prozess, *, frist: float = 10.0) -> bool:
    """Beendet ``prozess`` und alle seine Nachkommen (Kinder, Enkel, ...).

    Args:
        prozess: Ein ``subprocess.Popen``. Ein Objekt ohne ``pid`` bekommt nur ``terminate()``.
        frist: So lange wird hoechstens darauf gewartet, dass alle weg sind (Sekunden).

    Returns:
        ``True``, wenn danach keiner der Prozesse mehr lebt.
    """
    pid = getattr(prozess, "pid", None)
    if not isinstance(pid, int) or pid <= 0:
        _einfach_beenden(prozess)
        return True
    abfrage = getattr(prozess, "poll", None)
    if callable(abfrage):
        try:
            if abfrage() is not None:
                # Schon beendet und abgeholt: Die Kennung kann inzwischen einem fremden Prozess gehoeren (eine Ablage
                # haelt den Prozess der vorigen Stufe, bis die naechste einen neuen anmeldet).
                return True
        except Exception as exc:  # noqa: BLE001
            logger.debug("poll() fehlgeschlagen: %s", exc)
    psutil = _psutil()
    if psutil is not None:
        try:
            return _mit_psutil(psutil, prozess, pid, frist)
        except Exception:  # noqa: BLE001 - dann mit den Bordmitteln des Systems
            logger.exception("Prozessbaum nicht mit psutil beendet")
    return _ohne_psutil(prozess, pid, frist)
