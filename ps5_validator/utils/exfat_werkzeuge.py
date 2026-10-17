# -*- coding: utf-8 -*-
"""Hilfswerkzeuge fuer exFAT-Abbilder (seit v1.9.83):
- Boot-Sektor-Reparatur aus dem Backup-VBR
- Inhalt entpacken und neu aufbauen (ueber MkPFS CLI)
"""
from __future__ import annotations

import glob
import os
import subprocess
import sys
from typing import Callable

# exFAT VBR-Struktur: 12 Sektoren a 512 Bytes
_VBR_SEKTOREN = 12
_SEKTOR_BYTES = 512
_VBR_BYTES = _VBR_SEKTOREN * _SEKTOR_BYTES

_OEM_VERSATZ = 3
_OEM_NAME = b"EXFAT   "
_SIG_VERSATZ = 510
_BOOT_SIG = b"\x55\xAA"

#: Rueckgabe-Marker von :func:`exfat_boot_sektor_reparieren`.
MARKER_PRIMAER_OK = "primaer_ok"
MARKER_REPARIERT = "repariert"

#: Zeitgrenzen fuer MkPFS-Unterprozesse (Sekunden).
TIMEOUT_ENTPACKEN = 300
TIMEOUT_AUFBAUEN = 600


def exfat_vbr_gueltig(vbr: bytes) -> bool:
    """True wenn OEM-Name und Boot-Signatur eines exFAT-VBR stimmen."""
    if len(vbr) < _SEKTOR_BYTES:
        return False
    return (
        vbr[_OEM_VERSATZ : _OEM_VERSATZ + 8] == _OEM_NAME
        and vbr[_SIG_VERSATZ : _SIG_VERSATZ + 2] == _BOOT_SIG
    )


def exfat_boot_sektor_reparieren(pfad: str) -> tuple[bool, str]:
    """Stellt den primaeren VBR (Sektoren 0-11) aus dem Backup-VBR (12-23) wieder her.

    Gibt ``(True, MARKER_PRIMAER_OK)`` zurueck, wenn der primaere VBR bereits gueltig ist.
    Gibt ``(True, MARKER_REPARIERT)`` zurueck, wenn der Backup erfolgreich eingespielt wurde.
    Gibt ``(False, Fehlermeldung)`` zurueck, wenn die Reparatur nicht moeglich ist.
    """
    try:
        with open(pfad, "rb") as fh:
            primaer = fh.read(_VBR_BYTES)
            backup = fh.read(_VBR_BYTES)
    except OSError as exc:
        return False, str(exc)

    if len(primaer) < _VBR_BYTES:
        return False, "Datei zu klein fuer einen vollstaendigen primaeren VBR."
    if len(backup) < _VBR_BYTES:
        return False, "Kein Backup-VBR vorhanden (Datei zu kurz)."

    if exfat_vbr_gueltig(primaer):
        return True, MARKER_PRIMAER_OK
    if not exfat_vbr_gueltig(backup):
        return False, "Weder primaerer noch Backup-VBR ist gueltig – Reparatur nicht moeglich."

    try:
        with open(pfad, "r+b") as fh:
            fh.seek(0)
            fh.write(backup)
    except OSError as exc:
        return False, str(exc)

    return True, MARKER_REPARIERT


def mkpfs_eltern_suchen(wurzeln: list[str]) -> str:
    """Gibt den Elternordner des ``MkPFS-*``-Verzeichnisses zurueck, sonst ``""``."""
    for wurzel in wurzeln or []:
        for treffer in glob.glob(os.path.join(wurzel, "MkPFS-*")):
            if os.path.isdir(os.path.join(treffer, "mkpfs")):
                return wurzel
    return ""


def _mkpfs_ausfuehren(
    mkpfs_eltern: str,
    argumente: list[str],
    timeout: int,
    ausgabe_cb: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Fuehrt MkPFS CLI als Unterprozess aus und gibt (Erfolg, Ausgabe) zurueck."""
    treffer_liste = glob.glob(os.path.join(mkpfs_eltern, "MkPFS-*"))
    mkpfs_ordner = next(
        (t for t in treffer_liste if os.path.isdir(os.path.join(t, "mkpfs"))), ""
    )
    if not mkpfs_ordner:
        return False, "MkPFS-Ordner nicht gefunden."

    umgebung = {**os.environ, "PYTHONPATH": mkpfs_ordner}
    try:
        ergebnis = subprocess.run(
            [sys.executable, "-m", "mkpfs"] + argumente,
            capture_output=True, text=True, timeout=timeout,
            cwd=mkpfs_ordner, env=umgebung,
        )
        ausgabe = (ergebnis.stdout + ergebnis.stderr).strip()
        if ausgabe_cb:
            for zeile in ausgabe.splitlines():
                ausgabe_cb(zeile)
        return ergebnis.returncode == 0, ausgabe
    except subprocess.TimeoutExpired:
        return False, f"Zeitüberschreitung ({timeout} s)."
    except OSError as exc:
        return False, str(exc)


def exfat_entpacken(
    wurzeln: list[str],
    quelle: str,
    ziel: str,
    ausgabe_cb: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Entpackt ein ``.exfat``-Abbild in einen Ordner (MkPFS ``unpack``)."""
    eltern = mkpfs_eltern_suchen(wurzeln)
    if not eltern:
        return False, "MkPFS-Ordner nicht gefunden."
    return _mkpfs_ausfuehren(
        eltern, ["unpack", "--overwrite", quelle, ziel], TIMEOUT_ENTPACKEN, ausgabe_cb
    )


def exfat_aufbauen(
    wurzeln: list[str],
    ordner: str,
    ziel: str,
    ausgabe_cb: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Baut ein ``.exfat``-Abbild aus einem Ordner (MkPFS ``pack exfat``)."""
    eltern = mkpfs_eltern_suchen(wurzeln)
    if not eltern:
        return False, "MkPFS-Ordner nicht gefunden."
    return _mkpfs_ausfuehren(
        eltern,
        ["pack", "exfat", "--overwrite", ordner, ziel],
        TIMEOUT_AUFBAUEN,
        ausgabe_cb,
    )
