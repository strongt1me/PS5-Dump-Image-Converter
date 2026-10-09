# -*- coding: utf-8 -*-
"""Archive (``.zip``, ``.7z``, ``.rar``) als Quelle fuer Aufgabe 1 - seit v1.9.70.

Ein Archiv mit einem Spielordner wird in einen Arbeitsordner entpackt; das Programm arbeitet danach mit dem
entpackten Dump-Ordner wie mit jedem anderen. Die Idee stammt aus PS5 FFPFSC PRO 1.3.0 ("supports .zip, .rar and
.7z") und aus PS5 Upload ("uploads of games, folders, disk images and .zip / .7z / .rar archives"); der Code ist neu.

* ``.zip`` entpackt die Standardbibliothek (``zipfile``), mit Pfadpruefung gegen ``..`` und absolute Pfade.
* ``.7z`` und ``.rar`` entpackt **7-Zip** (LGPL; fuer RAR gilt zusaetzlich die unRAR-Einschraenkung, die nur das
  Nachbauen des RAR-Packers verbietet): das mitgelieferte (``7-Zip-26.00/``) oder, wenn das fehlt, eines im
  Suchpfad bzw. unter ``C:\\Program Files\\7-Zip``.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

ENDUNGEN = (".zip", ".7z", ".rar")
#: Name des mitgelieferten 7-Zip-Ordners.
ORDNER = "7-Zip-26.00"

_Melder = Callable[[str], None]


class ArchivFehler(Exception):
    """Entpacken gescheitert; die Meldung ist fuer das Protokoll gedacht."""


def ist_archiv(pfad: str) -> bool:
    return os.path.isfile(pfad) and os.path.splitext(pfad)[1].lower() in ENDUNGEN


def _unterordner() -> str:
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux-x64"


def siebenzip_suchen(wurzeln: list[str] | None = None) -> str:
    """Pfad zu einem 7-Zip, das ``.7z`` und ``.rar`` kann, sonst ``""``.

    ``7za`` und ``7zr`` (die schlanken Fassungen) koennen kein RAR und gelten deshalb nicht.
    """
    exe = "7z.exe" if sys.platform == "win32" else "7zz"
    for wurzel in wurzeln or []:
        kandidat = os.path.join(wurzel, ORDNER, _unterordner(), exe)
        if os.path.isfile(kandidat):
            return kandidat
    namen = ("7z", "7zz", "7zzs") if sys.platform != "win32" else ("7z",)
    for name in namen:
        gefunden = shutil.which(name)
        if gefunden:
            return gefunden
    if sys.platform == "win32":
        for basis in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                      os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            kandidat = os.path.join(basis, "7-Zip", "7z.exe")
            if os.path.isfile(kandidat):
                return kandidat
    return ""


def hat_spiel(ordner: str) -> bool:
    """Liegt in ``ordner`` ein Spiel (``sce_sys/param.json``)?"""
    return os.path.isfile(os.path.join(ordner, "sce_sys", "param.json"))


def spielwurzel(ordner: str) -> str:
    """Der Ordner im entpackten Baum, der ein Spiel enthaelt (``sce_sys/param.json``).

    Archive legen den Spiel-Ordner oft eine Ebene tiefer ab (``Spiel/sce_sys/...``). Gesucht wird, hoechstens
    drei Ebenen tief, zuerst am Stamm, dann ueber Ordner mit nur einem Eintrag nach unten, zuletzt breit. Findet
    sich nichts, bleibt der Stamm.
    """
    if hat_spiel(ordner):
        return ordner
    aktuell = ordner
    for _ in range(3):
        try:
            eintraege = [e for e in os.scandir(aktuell)]
        except OSError:
            break
        unter = [e.path for e in eintraege if e.is_dir()]
        if len(eintraege) == 1 and len(unter) == 1:
            aktuell = unter[0]
            if hat_spiel(aktuell):
                return aktuell
            continue
        break
    for tiefe_wurzel, _dirs, _files in os.walk(ordner):
        rel = os.path.relpath(tiefe_wurzel, ordner)
        if rel != "." and rel.count(os.sep) >= 3:
            _dirs[:] = []
            continue
        if hat_spiel(tiefe_wurzel):
            return tiefe_wurzel
    return ordner


def _zip_entpacken(archiv: str, ziel: str, melden: _Melder | None, abbruch: Callable[[], bool] | None) -> None:
    ziel_abs = os.path.realpath(ziel)
    try:
        with zipfile.ZipFile(archiv) as z:
            eintraege = z.infolist()
            gesamt = max(1, len(eintraege))
            letzte = -1
            for i, info in enumerate(eintraege, 1):
                if abbruch and abbruch():
                    raise ArchivFehler("abgebrochen")
                ziel_pfad = os.path.realpath(os.path.join(ziel_abs, info.filename))
                if ziel_pfad != ziel_abs and not ziel_pfad.startswith(ziel_abs + os.sep):
                    raise ArchivFehler("Unzulaessiger Pfad im Archiv: %s" % info.filename)
                z.extract(info, ziel_abs)
                prozent = i * 100 // gesamt
                if melden and prozent != letzte and prozent % 5 == 0:
                    letzte = prozent
                    melden("%d%%" % prozent)
    except zipfile.BadZipFile as exc:
        raise ArchivFehler("Kein gueltiges ZIP-Archiv: %s" % exc) from exc
    except OSError as exc:
        raise ArchivFehler("ZIP nicht entpackbar: %s" % exc) from exc


def _siebenzip_entpacken(archiv: str, ziel: str, programm: str, melden: _Melder | None,
                         abbruch: Callable[[], bool] | None, popen_extra: dict | None) -> None:
    if sys.platform != "win32":
        try:
            os.chmod(programm, os.stat(programm).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
    # -y: keine Rueckfragen, -bsp1: Fortschritt in Prozent auf stdout, -bso0/-bse1: nur Fehler auf stderr
    befehl = [programm, "x", "-y", "-bsp1", "-bso0", "-bse1", "-o" + ziel, archiv]
    try:
        prozess = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, **(popen_extra or {}))
    except OSError as exc:
        raise ArchivFehler("7-Zip laesst sich nicht starten: %s" % exc) from exc
    ausgabe: list[str] = []
    letzte = -1
    assert prozess.stdout is not None
    puffer = b""
    while True:
        if abbruch and abbruch():
            prozess.kill()
            prozess.wait()
            raise ArchivFehler("abgebrochen")
        stueck = prozess.stdout.read(256)
        if not stueck:
            break
        puffer += stueck
        text = puffer.decode("utf-8", errors="replace")
        for treffer in re.finditer(r"(\d{1,3})%", text):
            wert = int(treffer.group(1))
            if wert != letzte and wert % 5 == 0 and melden:
                letzte = wert
                melden("%d%%" % wert)
        puffer = puffer[-16:]
        ausgabe.append(stueck.decode("utf-8", errors="replace"))
    rc = prozess.wait()
    if rc != 0:
        rest = re.sub(r"\s*\d{1,3}%[^\n]*", " ", "".join(ausgabe))
        zeilen = [z.strip() for z in rest.splitlines() if z.strip()]
        raise ArchivFehler("7-Zip meldet Fehler (Code %d): %s" % (rc, " | ".join(zeilen[-4:])[:400]))


def entpacken(archiv: str, ziel: str, *, wurzeln: list[str] | None = None, melden: _Melder | None = None,
              abbruch: Callable[[], bool] | None = None, popen_extra: dict | None = None) -> str:
    """Entpackt ``archiv`` nach ``ziel`` und gibt den Spiel-Ordner darin zurueck.

    Raises:
        ArchivFehler: Archiv unlesbar, 7-Zip fehlt (bei ``.7z``/``.rar``), Abbruch oder Fehler beim Entpacken.
    """
    endung = os.path.splitext(archiv)[1].lower()
    if endung not in ENDUNGEN or not os.path.isfile(archiv):
        raise ArchivFehler("Kein Archiv: %s" % archiv)
    Path(ziel).mkdir(parents=True, exist_ok=True)
    if endung == ".zip":
        _zip_entpacken(archiv, ziel, melden, abbruch)
    else:
        programm = siebenzip_suchen(wurzeln)
        if not programm:
            raise ArchivFehler("7-Zip nicht gefunden")
        _siebenzip_entpacken(archiv, ziel, programm, melden, abbruch, popen_extra)
    return spielwurzel(ziel)
