# -*- coding: utf-8 -*-
"""Welcher Editor ein fertiges Abbild direkt aendert ("Direkt aendern" unter ABBILD BEARBEITEN, seit dem 14.11.2026).

Erkannt wird am **Inhalt**, nicht an der Endung: exFAT (Startsektor), UFS2 (Superblock bei 64 KiB) oder PFS (Kopf). Ein PFS wird weiter
unterschieden (:func:`pfs_bearbeiten.oeffnen`): flach, Huelle um ein exFAT, oder komprimiert (dann nicht direkt aenderbar).

Alle Editoren haben dieselbe Schnittstelle: ``auflisten``, ``umbenennen``, ``loeschen``, ``ersetzen``, ``hinzufuegen``,
``ordner_anlegen``, ``speichern``, ``pruefen``, ``freie_bytes``, ``schliessen`` und das Attribut ``art``; ihre Fehler sind
:class:`DirektFehler` (Platzmangel: :class:`DirektPlatzFehlt`). Ein liegengebliebenes Journal wird vor dem Erkennen zurueckgespielt.
"""
from __future__ import annotations

import os

from ps5_validator.utils.abbild_journal import (  # noqa: F401  (fuer die Oberflaeche an einer Stelle)
    DirektFehler,
    DirektPlatzFehlt,
    journal_pfad,
    journal_zurueckspielen,
)

#: Die Endungen, bei denen "Direkt aendern" angeboten wird (``.ffpfsc`` ist komprimiert und geht nie).
ENDUNGEN = (".exfat", ".ffpkg", ".ffpfs")


def _ist_exfat(pfad: str) -> bool:
    try:
        with open(pfad, "rb") as fh:
            return fh.read(11)[3:11] == b"EXFAT   "
    except OSError:
        return False


def oeffnen(pfad: str):  # noqa: ANN201 - ExfatAbbild, Ufs2Abbild oder PfsAbbild
    """Der Editor fuer ``pfad``. Ein Format, das sich nicht direkt aendern laesst, ist ein :class:`DirektFehler`."""
    from ps5_validator.utils import exfat_bearbeiten, pfs_bearbeiten, ufs2_bearbeiten  # noqa: PLC0415
    if not os.path.isfile(pfad):
        raise DirektFehler("Keine Datei: %s" % pfad)
    journal_zurueckspielen(pfad)
    if _ist_exfat(pfad):
        return exfat_bearbeiten.ExfatAbbild(pfad)
    if ufs2_bearbeiten.ist_ufs2(pfad):
        return ufs2_bearbeiten.Ufs2Abbild(pfad)
    if pfs_bearbeiten.ist_pfs(pfad):
        return pfs_bearbeiten.oeffnen(pfad)
    raise DirektFehler("Unbekanntes Format: weder exFAT noch UFS2 noch PFS")
