# -*- coding: utf-8 -*-
"""Archive (``.zip``, ``.7z``, ``.rar``) als Quelle fuer Aufgabe 1 - seit v1.9.70.

Ein Archiv mit einem Spielordner wird in einen Arbeitsordner entpackt; das Programm arbeitet danach mit dem
entpackten Dump-Ordner wie mit jedem anderen. Die Idee stammt aus PS5 FFPFSC PRO 1.3.0 ("supports .zip, .rar and
.7z") und aus PS5 Upload ("uploads of games, folders, disk images and .zip / .7z / .rar archives"); der Code ist neu.

* ``.zip`` entpackt die Standardbibliothek (``zipfile``), mit Pfadpruefung gegen ``..`` und absolute Pfade.
* ``.7z`` und ``.rar`` entpackt **7-Zip** (LGPL; fuer RAR gilt zusaetzlich die unRAR-Einschraenkung, die nur das
  Nachbauen des RAR-Packers verbietet): das mitgelieferte (``7-Zip-26.05/``) oder, wenn das fehlt, eines im
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
ORDNER = "7-Zip-26.05"

_Melder = Callable[[str], None]


class ArchivFehler(Exception):
    """Entpacken gescheitert; die Meldung ist fuer das Protokoll gedacht."""


class PasswortFehler(ArchivFehler):
    """Das Archiv ist verschluesselt und ein Passwort fehlt oder ist falsch.

    Ohne diese Unterscheidung meldete 7-Zip "Break signaled" (Code 255): Es fragt auf der Konsole nach dem Passwort,
    liest aber nichts (``stdin`` ist ``NUL``, das Programm hat keine Konsole) - Meldung des Anwenders am 14.10.2026 mit
    einer passwortgeschuetzten .rar.
    """


#: Passwoerter, mit denen Spiel-Archive aus der Szene ueblicherweise verschluesselt sind (Angabe des Anwenders,
#: 14.10.2026). Sie werden der Reihe nach probiert, bevor das Programm den Anwender fragt.
BEKANNTE_PASSWOERTER = ("pippo", "DLPSGAME.COM")

#: Woran sich bei 7-Zip ein fehlendes oder falsches Passwort erkennen laesst.
_PASSWORT_MUSTER = re.compile(r"wrong password|encrypted archive|data error in encrypted|enter password|break signaled",
                              re.IGNORECASE)


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


def _zip_entpacken(archiv: str, ziel: str, melden: _Melder | None, abbruch: Callable[[], bool] | None,
                   passwort: str = "") -> None:
    ziel_abs = os.path.realpath(ziel)
    kennwort = passwort.encode("utf-8") if passwort else None
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
                z.extract(info, ziel_abs, pwd=kennwort)
                prozent = i * 100 // gesamt
                if melden and prozent != letzte and prozent % 5 == 0:
                    letzte = prozent
                    melden("%d%%" % prozent)
    except zipfile.BadZipFile as exc:
        raise ArchivFehler("Kein gueltiges ZIP-Archiv: %s" % exc) from exc
    except RuntimeError as exc:
        # zipfile meldet "File ... is encrypted, password required" bzw. "Bad password for file ..."
        if "password" in str(exc).lower():
            raise PasswortFehler(str(exc)) from exc
        raise ArchivFehler("ZIP nicht entpackbar: %s" % exc) from exc
    except OSError as exc:
        raise ArchivFehler("ZIP nicht entpackbar: %s" % exc) from exc


def _siebenzip_entpacken(archiv: str, ziel: str, programm: str, melden: _Melder | None,
                         abbruch: Callable[[], bool] | None, popen_extra: dict | None, passwort: str = "") -> None:
    if sys.platform != "win32":
        try:
            os.chmod(programm, os.stat(programm).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except OSError:
            pass
    # -y: keine Rueckfragen, -bsp1: Fortschritt in Prozent auf stdout, -bso0/-bse1: nur Fehler auf stderr.
    # -p<Passwort> immer mitgeben (leer = keines): Sonst fragt 7-Zip bei einem verschluesselten Archiv auf der Konsole
    # nach, bekommt von stdin nichts und bricht mit "Break signaled" ab.
    befehl = [programm, "x", "-y", "-bsp1", "-bso0", "-bse1", "-p" + passwort, "-o" + ziel, archiv]
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
        roh = "".join(ausgabe)
        # 7-Zip schreibt den Fortschritt mit \r in dieselbe Zeile wie die Fehlermeldung: nur bis \r oder \n wegschneiden
        # ("0%\rERROR: Wrong password" ging sonst samt Meldung verloren).
        rest = re.sub(r"\s*\d{1,3}%[^\r\n]*", " ", roh.replace("\r", "\r\n"))
        zeilen = [z.strip() for z in rest.splitlines() if z.strip()]
        if _PASSWORT_MUSTER.search(roh):
            raise PasswortFehler(" | ".join(zeilen[-4:])[:400])
        raise ArchivFehler("7-Zip meldet Fehler (Code %d): %s" % (rc, " | ".join(zeilen[-4:])[:400]))


def entpacken(archiv: str, ziel: str, *, wurzeln: list[str] | None = None, melden: _Melder | None = None,
              abbruch: Callable[[], bool] | None = None, popen_extra: dict | None = None,
              passwort: str = "") -> str:
    """Entpackt ``archiv`` nach ``ziel`` und gibt den Spiel-Ordner darin zurueck.

    Raises:
        PasswortFehler: Das Archiv ist verschluesselt, ``passwort`` fehlt oder stimmt nicht.
        ArchivFehler: Archiv unlesbar, 7-Zip fehlt (bei ``.7z``/``.rar``), Abbruch oder Fehler beim Entpacken.
    """
    endung = os.path.splitext(archiv)[1].lower()
    if endung not in ENDUNGEN or not os.path.isfile(archiv):
        raise ArchivFehler("Kein Archiv: %s" % archiv)
    Path(ziel).mkdir(parents=True, exist_ok=True)
    programm = ""
    if endung != ".zip":
        programm = siebenzip_suchen(wurzeln)
        if not programm:
            raise ArchivFehler("7-Zip nicht gefunden")
    # Ohne Angabe: erst ohne Passwort, dann die bekannten. Mit Angabe nur dieses - ein falsches Passwort des Anwenders
    # soll nicht still durch ein anderes ersetzt werden, sondern ihn noch einmal fragen lassen.
    kandidaten = [passwort] if passwort else ["", *BEKANNTE_PASSWOERTER]
    letzter: PasswortFehler | None = None
    for kandidat in kandidaten:
        try:
            if endung == ".zip":
                _zip_entpacken(archiv, ziel, melden, abbruch, kandidat)
            else:
                _siebenzip_entpacken(archiv, ziel, programm, melden, abbruch, popen_extra, kandidat)
            letzter = None
            break
        except PasswortFehler as exc:
            letzter = exc
            _ziel_leeren(ziel)          # was vor dem Fehler entpackt war, wird nicht gebraucht
    if letzter is not None:
        raise letzter
    verknuepfung_nach_aussen(ziel)
    return spielwurzel(ziel)


def verknuepfung_nach_aussen(ziel: str) -> None:
    """Bricht ab, wenn das entpackte Archiv eine Verknuepfung enthaelt, die aus dem Ordner herauszeigt.

    ZIP legt beim Entpacken nie Verknuepfungen an (und prueft jeden Pfad vorher); 7-Zip dagegen kann sie aus
    7z- und RAR-Archiven wiederherstellen. Ein Spiele-Dump hat solche Verknuepfungen nicht - zeigt eine nach
    ``/etc`` oder in den Benutzerordner, wuerde das Programm beim Einlesen, Packen oder Loeschen
    dort hineinlaufen. Deshalb gilt: Verknuepfung, die ausserhalb von ``ziel`` endet = Fehler.

    Raises:
        ArchivFehler: Mit dem Namen der ersten gefundenen Verknuepfung.
    """
    wurzel = os.path.realpath(ziel)
    ist_knoten = getattr(os.path, "isjunction", lambda _pfad: False)
    offen = [ziel]
    while offen:
        ordner = offen.pop()
        try:
            eintraege = list(os.scandir(ordner))
        except OSError:
            continue
        for eintrag in eintraege:
            # DirEntry kennt Verknuepfung und Ordner schon aus dem Auflisten - kein weiterer Aufruf je Datei.
            ist_link = eintrag.is_symlink() or ist_knoten(eintrag.path)
            if ist_link:
                echt = os.path.realpath(eintrag.path)
                if echt != wurzel and not echt.startswith(wurzel + os.sep):
                    raise ArchivFehler("Unzulaessige Verknuepfung im Archiv: %s -> %s"
                                       % (os.path.relpath(eintrag.path, ziel), echt))
            elif eintrag.is_dir(follow_symlinks=False):
                offen.append(eintrag.path)


def _ziel_leeren(ziel: str) -> None:
    """Raeumt den Inhalt des Entpackordners weg (der Ordner selbst bleibt)."""
    try:
        for eintrag in os.scandir(ziel):
            if eintrag.is_dir(follow_symlinks=False):
                shutil.rmtree(eintrag.path, ignore_errors=True)
            else:
                try:
                    os.unlink(eintrag.path)
                except OSError:
                    pass
    except OSError:
        pass
