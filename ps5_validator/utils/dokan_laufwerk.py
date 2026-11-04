# -*- coding: utf-8 -*-
"""Dokan-Laufwerke (UFS2Tool ``mount_udf``) sauber ein- und aushaengen.

Drei Stellen haengen eine ``.ffpkg`` als Laufwerk ein: das Entpacken (Aufgabe 4), die Vorschau der Metadaten und die
Pruefung (Aufgabe 8). Gemessen am 04.11.2026 (Fenstermessung, zweimal wiederholt) gingen dabei zwei Dinge schief:

* **Wettlauf auf demselben Buchstaben.** Waehlt man die Datei und startet sofort, haengt die Vorschau sie auf dem
  hoechsten freien Buchstaben ein - und das Entpacken auf demselben. ``os.path.exists`` meldete "bereit", weil das
  Laufwerk der Vorschau dort stand; das las 13 Dateien statt 1166 und verschwand unter den Fuessen von robocopy
  ("Zugriff auf Quellverzeichnis W:\\ ... Pfad nicht gefunden"). Ein andermal blieb robocopy 54 Minuten haengen.
* **Harter Abschuss statt Aushaengen.** ``mount_udf`` wurde mit ``terminate()`` beendet, ohne das Laufwerk
  auszuhaengen. Das Laufwerk blieb stehen (der Nutzer fand ``W:`` im Explorer), und ein haengender robocopy liess sich
  nicht mehr beenden. ``dokanctl /u`` gibt die wartenden Anfragen frei - danach geht alles weiter.

Dieses Modul bindet kein Fenster und kein ``i18n`` ein.
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
import threading
import time
from typing import Callable

IST_WINDOWS = sys.platform == "win32"

#: Gemeinsame Sperre fuer alle ``mount_udf``-Einhaengungen dieses Prozesses. Wer ein Laufwerk braucht, haelt sie vom
#: Einhaengen bis zum Aushaengen - sonst wuerden zwei Einhaengungen denselben Buchstaben nehmen.
SPERRE = threading.RLock()


def _kein_fenster() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if IST_WINDOWS else 0


def laufwerk_belegt(buchstabe: str) -> bool:
    """True, wenn Windows den Buchstaben kennt - als Laufwerk **oder** als liegengebliebene Zuordnung.

    ``GetLogicalDrives`` zeigt nur fertige Laufwerke. Eine Zuordnung, die ein beendetes Einhaengewerkzeug
    zurueckgelassen hat, fehlt dort, steht aber noch in der Geraeteliste (``QueryDosDevice``).
    """
    if not IST_WINDOWS:
        return False
    import ctypes
    buchstabe = str(buchstabe or "")[:1].upper()
    if not buchstabe.isalpha():
        return True
    maske = ctypes.windll.kernel32.GetLogicalDrives()
    if maske & (1 << (ord(buchstabe) - 65)):
        return True
    puffer = ctypes.create_unicode_buffer(1024)
    return bool(ctypes.windll.kernel32.QueryDosDeviceW(buchstabe + ":", puffer, 1024))


def freier_buchstabe(ausser: "tuple[str, ...]" = ()) -> "str | None":
    """Der hoechste freie Laufwerksbuchstabe (``Z`` abwaerts bis ``E``) als ``"W:"``; ``None`` ohne einen freien.

    Wie bisher von hinten, damit die Einhaengung nicht die Buchstaben der echten Laufwerke belegt.
    """
    gesperrt = {str(a)[:1].upper() for a in ausser}
    for index in range(25, 3, -1):
        buchstabe = chr(65 + index)
        if buchstabe in gesperrt or laufwerk_belegt(buchstabe):
            continue
        return buchstabe + ":"
    return None


def dokanctl_pfad() -> str:
    """Pfad zu ``dokanctl.exe`` (Dokan-Installation, sonst neben UFS2Tool/im PATH); leer, wenn nicht gefunden."""
    kandidaten: list[str] = []
    for wurzel in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                   os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        kandidaten += sorted(glob.glob(os.path.join(wurzel, "Dokan", "DokanLibrary-*", "dokanctl.exe")), reverse=True)
        kandidaten.append(os.path.join(wurzel, "Dokan", "dokanctl.exe"))
    for pfad in kandidaten:
        if os.path.isfile(pfad):
            return pfad
    import shutil
    return shutil.which("dokanctl") or ""


def bereit_warten(mount_proc: "subprocess.Popen", laufwerk: str, *, versuche: int = 30, pause: float = 0.5,
                  abbruch: "Callable[[], bool] | None" = None) -> bool:
    """Wartet, bis das Laufwerk **unser** ist und stabil Dateien zeigt.

    Bereit heisst: Der Einhaengeprozess lebt noch, und das Wurzelverzeichnis liefert zweimal hintereinander dieselbe,
    nicht leere Liste. ``os.path.exists`` allein genuegte nicht (siehe Modulkopf): Es sagt nur, dass unter dem
    Buchstaben irgendetwas steht, nicht, dass es das eigene, fertige Laufwerk ist.

    Returns:
        ``True`` bereit; ``False`` bei Prozessende, Abbruch oder Zeitablauf.
    """
    wurzel = laufwerk + "\\"
    letzte: "list[str] | None" = None
    for _ in range(max(1, versuche)):
        if abbruch is not None and abbruch():
            return False
        if mount_proc.poll() is not None:
            return False
        try:
            eintraege = sorted(os.listdir(wurzel)) if os.path.exists(wurzel) else []
        except OSError:
            eintraege = []
        if eintraege and eintraege == letzte and mount_proc.poll() is None:
            return True
        letzte = eintraege or None
        time.sleep(pause)
    return False


def aushaengen(laufwerk: str, mount_proc: "subprocess.Popen | None" = None, warte_s: float = 10.0) -> bool:
    """Haengt ein Dokan-Laufwerk sauber aus und beendet danach den Einhaengeprozess.

    Reihenfolge: ``dokanctl /u`` (gibt auch eine haengende Anfrage frei, etwa die eines wartenden robocopy), dann der
    Prozess, dann Warten, bis der Buchstabe frei ist; zuletzt - wie bisher - ``mountvol /D``. Ruft man es fuer ein
    schon ausgehaengtes Laufwerk auf, schadet es nicht.

    Returns:
        ``True``, wenn der Buchstabe danach frei ist (``False`` auch ausserhalb von Windows).
    """
    if not IST_WINDOWS:
        return False
    buchstabe = str(laufwerk or "")[:1].upper()
    if not buchstabe.isalpha():
        return False
    ctl = dokanctl_pfad()
    if ctl:
        try:
            subprocess.run([ctl, "/u", buchstabe], timeout=15, capture_output=True, creationflags=_kein_fenster())
        except (OSError, subprocess.SubprocessError):
            pass
    if mount_proc is not None:
        try:
            if mount_proc.poll() is None:
                mount_proc.terminate()
            mount_proc.wait(timeout=warte_s)
        except Exception:  # noqa: BLE001 - ein nicht beendbarer Prozess darf das Aufraeumen nicht aufhalten
            try:
                mount_proc.kill()
            except Exception:  # noqa: BLE001
                pass
    ende = time.monotonic() + max(0.5, warte_s)
    while time.monotonic() < ende:
        if not laufwerk_belegt(buchstabe):
            return True
        time.sleep(0.25)
    try:
        subprocess.run(["mountvol", buchstabe + ":\\", "/D"], timeout=10, capture_output=True,
                       creationflags=_kein_fenster())
    except (OSError, subprocess.SubprocessError):
        pass
    return not laufwerk_belegt(buchstabe)
