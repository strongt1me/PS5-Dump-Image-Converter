# -*- coding: utf-8 -*-
"""Archive (``.zip``, ``.7z``, ``.rar``) als Quelle fuer Aufgabe 1 - seit v1.9.70.

Ein Archiv mit einem Spielordner wird in einen Arbeitsordner entpackt; das Programm arbeitet danach mit dem
entpackten Dump-Ordner wie mit jedem anderen. Die Idee stammt aus PS5 FFPFSC PRO 1.3.0 ("supports .zip, .rar and
.7z") und aus PS5 Upload ("uploads of games, folders, disk images and .zip / .7z / .rar archives"); der Code ist neu.

* ``.zip`` entpackt die Standardbibliothek (``zipfile``), mit Pfadpruefung gegen ``..`` und absolute Pfade.
* ``.7z`` und ``.rar`` entpackt **7-Zip** (LGPL; fuer RAR gilt zusaetzlich die unRAR-Einschraenkung, die nur das
  Nachbauen des RAR-Packers verbietet): das mitgelieferte (``7-Zip-26.06/``) oder, wenn das fehlt, eines im
  Suchpfad bzw. unter ``C:\\Program Files\\7-Zip``.
"""
from __future__ import annotations

import lzma
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import time
import zipfile
import zlib
from pathlib import Path
from typing import Callable

from ps5_validator.utils.dlc_emu import ist_dlc_ordnername

ENDUNGEN = (".zip", ".7z", ".rar")
#: Name des mitgelieferten 7-Zip-Ordners.
ORDNER = "7-Zip-26.06"

_Melder = Callable[[str], None]

#: So viel Platz muss auf dem Ziellaufwerk nach dem Entpacken noch frei sein (Gesamtpruefung 11.11.2026, SEC5): Die Pruefung
#: vor dem Start sah nur die Groesse der Archivdatei - ein Archiv, das ausgepackt ein Vielfaches braucht (oder absichtlich
#: aufgeblaeht ist), fuellte das Laufwerk, auf dem auch Windows liegt.
PLATZ_RESERVE = 1 << 30


def _platz_pruefen(ziel: str, benoetigt: int, reserve: int) -> None:
    """Bricht ab, wenn ``benoetigt`` plus ``reserve`` nicht mehr auf das Laufwerk von ``ziel`` passt."""
    try:
        frei = shutil.disk_usage(ziel).free
    except OSError:
        return                       # nicht pruefbar - dann gilt die Pruefung des Aufrufers
    if frei - benoetigt < reserve:
        raise ArchivFehler("Zu wenig Platz auf dem Ziellaufwerk: %d Byte frei, %d Byte muessten entpackt werden "
                           "(%d Byte bleiben mindestens frei)" % (frei, benoetigt, reserve))


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
        # Ab 7-Zip 26.06 gibt es fuer macOS je Architektur ein eigenes Paket (26.05 war ein Universal-Binary).
        return "macos-arm64" if platform.machine().lower() in ("arm64", "aarch64") else "macos-x64"
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
    # Alle Treffer bis drei Ebenen tief, dann wie beim ZIP (archiv_baum.spielwurzel_aus_namen): der flachste, ein DLC-Ordner des
    # PS5-App-Dumpers ("EP9000-PPSA01234_00-...-ac") nach einem Spiel, dann nach dem Namen. Die Tiefensuche nahm den ersten Treffer -
    # ein DLC-Ordner mit eigener param.json in "A_DLC/" kam vor dem Spiel in "Z_Spiel/" (Gesamtpruefung 14.11.2026, R2-P5, R3-A2).
    treffer: "list[tuple[int, bool, str]]" = []
    for tiefe_wurzel, _dirs, _files in os.walk(ordner):
        rel = os.path.relpath(tiefe_wurzel, ordner)
        tiefe = 0 if rel == "." else rel.count(os.sep) + 1
        if tiefe > 3:
            _dirs[:] = []
            continue
        if tiefe and hat_spiel(tiefe_wurzel):
            # Mit "/" verglichen wie beim ZIP: "\" sortiert anders ("Games\..." nach "Games2\..."; R4-1).
            treffer.append((tiefe, ist_dlc_ordnername(os.path.basename(tiefe_wurzel)), rel.replace(os.sep, "/")))
            _dirs[:] = []                                   # in einem Spiel liegt kein zweites
    if treffer:
        return os.path.join(ordner, *sorted(treffer)[0][2].split("/"))
    return ordner


def zip_ist_aes(archiv: str) -> bool:
    """Ob ein ZIP-Archiv AES-verschluesselte Eintraege hat (Packverfahren 99); ein unlesbares Archiv gilt als nicht AES."""
    try:
        with zipfile.ZipFile(archiv) as z:
            return any(i.compress_type == 99 for i in z.infolist())
    except (zipfile.BadZipFile, OSError):
        return False


#: Die Packverfahren, die ``zipfile`` entpacken kann: Stored, Deflate, BZip2, LZMA.
_ZIPFILE_VERFAHREN = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED, zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA)


def zip_braucht_7zip(archiv: str) -> bool:
    """Ob ein ZIP ein Packverfahren nutzt, das ``zipfile`` nicht kann (AES 99, Deflate64 9, PPMd 98, ...) - dann entpackt 7-Zip.

    Gesamtpruefung 14.11.2026 (R2-P1): Nur AES ging an 7-Zip. Ein ZipCrypto-Archiv mit Deflate64 oder PPMd scheiterte in ``zipfile`` mit
    "nicht unterstuetzt" - und die Passwortprobe hielt das fuer ein falsches Passwort: Der Anwender wurde immer wieder gefragt.
    """
    try:
        with zipfile.ZipFile(archiv) as z:
            return any(i.compress_type not in _ZIPFILE_VERFAHREN for i in z.infolist() if not i.is_dir())
    except (zipfile.BadZipFile, OSError):
        return False


def _zip_passwort_passt(z: zipfile.ZipFile, eintraege: "list[zipfile.ZipInfo]", kennwort: "bytes | None") -> bool:
    """Liest die kleinste verschluesselte Datei ganz: passt das Passwort? Ohne verschluesselte Datei immer ``True``.

    Gesamtpruefung 14.11.2026 (A2): Ein falsches Passwort trifft das Pruefbyte von ZipCrypto in 1 von 256 Faellen. Dann entschluesselt
    ``zipfile`` Unsinn, und das Entpacken scheitert mit zlib.error, LZMAError oder einer falschen Pruefsumme statt mit "Bad password" -
    die Liste der Passwoerter brach dort ab, statt das naechste zu probieren. Erst die ganze Datei samt Pruefsumme entscheidet.
    """
    verschluesselt = [i for i in eintraege if i.flag_bits & 0x1 and i.file_size > 0 and not i.is_dir()]
    if not verschluesselt:
        return True
    if kennwort is None:
        return False
    probe = min(verschluesselt, key=lambda i: i.file_size)
    try:
        with z.open(probe, pwd=kennwort) as quelle:
            while quelle.read(1 << 20):
                pass
    except Exception:  # noqa: BLE001 - jeder Fehler hier heisst: dieses Passwort passt nicht
        return False
    return True


def _zip_entpacken(archiv: str, ziel: str, melden: _Melder | None, abbruch: Callable[[], bool] | None,
                   passwort: str = "", reserve: int = PLATZ_RESERVE) -> None:
    ziel_abs = os.path.realpath(ziel)
    kennwort = passwort.encode("utf-8") if passwort else None
    try:
        with zipfile.ZipFile(archiv) as z:
            eintraege = z.infolist()
            if not _zip_passwort_passt(z, eintraege, kennwort):
                raise PasswortFehler("Bad password for file %s" % os.path.basename(archiv))
            # Die entpackte Groesse steht im Verzeichnis des Archivs (``file_size``); ``zipfile`` liest nie mehr, als dort steht.
            _platz_pruefen(ziel_abs, sum(max(0, i.file_size) for i in eintraege), reserve)
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
    except (OSError, zlib.error, lzma.LZMAError, EOFError, NotImplementedError) as exc:
        raise ArchivFehler("ZIP nicht entpackbar: %s" % exc) from exc


def _siebenzip_entpacken(archiv: str, ziel: str, programm: str, melden: _Melder | None,
                         abbruch: Callable[[], bool] | None, popen_extra: dict | None, passwort: str = "",
                         reserve: int = PLATZ_RESERVE) -> None:
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
    platz_geprueft = float("-inf")
    while True:
        if abbruch and abbruch():
            prozess.kill()
            prozess.wait()
            raise ArchivFehler("abgebrochen")
        # Die entpackte Groesse nennt 7-Zip vorab nicht: Waehrend des Entpackens nachsehen, ob das Laufwerk noch Platz
        # fuer die Reserve hat, und sonst anhalten, bevor es voll ist.
        jetzt = time.monotonic()
        if jetzt - platz_geprueft >= 1.0:
            platz_geprueft = jetzt
            try:
                _platz_pruefen(ziel, 0, reserve)
            except ArchivFehler:
                prozess.kill()
                prozess.wait()
                raise
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
              passwort: str = "", platz_reserve: int = PLATZ_RESERVE,
              weitere_passwoerter: "list[str] | tuple[str, ...]" = ()) -> str:
    """Entpackt ``archiv`` nach ``ziel`` und gibt den Spiel-Ordner darin zurueck.

    Args:
        platz_reserve: Soviel Platz bleibt auf dem Ziellaufwerk mindestens frei; wird es knapp, bricht das Entpacken ab.
        weitere_passwoerter: Die Passwortliste des Anwenders (Einstellung ``archiv_passwoerter``); sie wird nach den bekannten
            probiert, wenn kein ``passwort`` angegeben ist.

    Raises:
        PasswortFehler: Das Archiv ist verschluesselt, ``passwort`` fehlt oder stimmt nicht.
        ArchivFehler: Archiv unlesbar, 7-Zip fehlt (bei ``.7z``/``.rar``), zu wenig Platz, Abbruch oder Fehler beim
            Entpacken.
    """
    endung = os.path.splitext(archiv)[1].lower()
    if endung not in ENDUNGEN or not os.path.isfile(archiv):
        raise ArchivFehler("Kein Archiv: %s" % archiv)
    Path(ziel).mkdir(parents=True, exist_ok=True)
    programm = ""
    # Ein Packverfahren, das ``zipfile`` nicht kann - AES (WinZip, 99), Deflate64, PPMd ... -, entpackt 7-Zip (Gesamtpruefung
    # 14.11.2026, A6 und R2-P1).
    mit_zipfile = endung == ".zip" and not zip_braucht_7zip(archiv)
    if not mit_zipfile:
        programm = siebenzip_suchen(wurzeln)
        if not programm:
            raise ArchivFehler("7-Zip nicht gefunden")
    # Ohne Angabe: erst ohne Passwort, dann die bekannten, dann die Liste des Anwenders. Mit Angabe nur dieses - ein falsches
    # Passwort des Anwenders soll nicht still durch ein anderes ersetzt werden, sondern ihn noch einmal fragen lassen.
    kandidaten = [passwort] if passwort else list(dict.fromkeys(["", *BEKANNTE_PASSWOERTER,
                                                                  *(p for p in weitere_passwoerter if p)]))
    letzter: PasswortFehler | None = None
    for kandidat in kandidaten:
        try:
            if mit_zipfile:
                _zip_entpacken(archiv, ziel, melden, abbruch, kandidat, platz_reserve)
            else:
                _siebenzip_entpacken(archiv, ziel, programm, melden, abbruch, popen_extra, kandidat, platz_reserve)
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
