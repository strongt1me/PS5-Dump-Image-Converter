# -*- coding: utf-8 -*-
"""Das Undo-Journal fuer "Direkt aendern" (exFAT, UFS2, PFS) und die gemeinsamen Ausnahmen der drei Editoren.

Ein Editor aendert ein fertiges Abbild an Ort und Stelle. Damit ein Abbruch (Absturz, Strom weg, Fehler mitten im Schreiben) nie ein
halbes Abbild hinterlaesst, schreibt er vorher die **alten** Bytes jeder Stelle, die er aendern wird, in ``<Abbild>.undo``:

* Das Journal entsteht als ``<Abbild>.undo.neu``, wird auf die Platte gezwungen und erst dann umbenannt. Gueltig ist es nur mit der
  Ende-Marke; jede Stelle traegt eine CRC32.
* Waechst das Abbild beim Schreiben (PFS haengt neue Daten hinten an), steht die alte Laenge als eigener Satz darin: Beim Zurueckspielen
  wird das Abbild wieder auf sie gekuerzt.
* Findet das Programm beim naechsten Oeffnen ein vollstaendiges Journal, spielt es die alten Bytes zurueck - das Abbild ist wieder wie
  vorher. Ein unvollstaendiges heisst: Es wurde noch nichts geaendert; es wird nur entfernt.

Das Format ist das von ``exfat_bearbeiten`` seit dem 14.11.2026 (gleiche Kennung): Ein dort liegengebliebenes Journal laesst sich hier
zurueckspielen und umgekehrt.
"""
from __future__ import annotations

import os
import struct
import zlib

JOURNAL_ENDUNG = ".undo"
_MAGIC = b"PS5CONV-EXFAT-UNDO1\n"
_ENDE = b"ENDE-DES-JOURNALS!"
#: Offset des Satzes "Laenge des Abbilds vorher" (8 Bytes Nutzlast); kein echtes Abbild ist so gross.
_LAENGE_SATZ = 0xFFFFFFFFFFFFFFFF


class DirektFehler(RuntimeError):
    """Das Abbild laesst sich so nicht direkt aendern (Format, Name unzulaessig, Pfad fehlt, beschaedigt)."""


class DirektPlatzFehlt(DirektFehler):
    """Im Abbild ist nicht genug Platz (oder die Verwaltung des Formats ist voll) - dann bleibt nur, es neu zu bauen."""


def journal_pfad(abbild: str) -> str:
    """Wo das Undo-Journal zu ``abbild`` liegt."""
    return abbild + JOURNAL_ENDUNG


def journal_schreiben(pfad: str, stellen: "list[tuple[int, bytes]]", *, laenge_vorher: "int | None" = None) -> None:
    """Schreibt ``(Offset, alte Bytes)`` ins Journal und zwingt es auf die Platte; die Ende-Marke kommt zuletzt und macht es gueltig.

    ``laenge_vorher``: die Laenge des Abbilds vor dem Schreiben, wenn es wachsen wird (beim Zurueckspielen wird es darauf gekuerzt).
    """
    saetze = list(stellen)
    if laenge_vorher is not None:
        saetze.append((_LAENGE_SATZ, struct.pack("<Q", int(laenge_vorher))))
    teil = pfad + ".neu"
    with open(teil, "wb") as fh:
        fh.write(_MAGIC)
        fh.write(struct.pack("<Q", len(saetze)))
        for offset, alt in saetze:
            fh.write(struct.pack("<QII", offset, len(alt), zlib.crc32(alt) & 0xFFFFFFFF))
            fh.write(alt)
        fh.write(_ENDE)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(teil, pfad)


def journal_lesen(pfad: str) -> "list[tuple[int, bytes]] | None":
    """Die Saetze eines vollstaendigen Journals (samt Laengensatz), sonst ``None`` (fehlt, abgeschnitten, Pruefsumme falsch)."""
    try:
        with open(pfad, "rb") as fh:
            if fh.read(len(_MAGIC)) != _MAGIC:
                return None
            kopf = fh.read(8)
            if len(kopf) < 8:
                return None
            anzahl = struct.unpack("<Q", kopf)[0]
            stellen: "list[tuple[int, bytes]]" = []
            for _ in range(anzahl):
                satz = fh.read(16)
                if len(satz) < 16:
                    return None
                offset, laenge, crc = struct.unpack("<QII", satz)
                alt = fh.read(laenge)
                if len(alt) < laenge or (zlib.crc32(alt) & 0xFFFFFFFF) != crc:
                    return None
                stellen.append((offset, alt))
            if fh.read(len(_ENDE)) != _ENDE:
                return None
            return stellen
    except OSError:
        return None


def journal_zurueckspielen(abbild: str) -> bool:
    """Spielt ein vollstaendiges Journal zurueck (die alten Bytes, dann die alte Laenge) und entfernt es. ``True``, wenn etwas
    zurueckgespielt wurde.

    Ein unvollstaendiges Journal heisst, dass der Lauf vor dem ersten Schreiben ins Abbild abbrach: Es wird nur entfernt.
    """
    pfad = journal_pfad(abbild)
    if not os.path.exists(pfad):
        return False
    stellen = journal_lesen(pfad)
    if stellen is not None:
        laenge: "int | None" = None
        with open(abbild, "r+b") as fh:
            for offset, alt in reversed(stellen):
                if offset == _LAENGE_SATZ:
                    if len(alt) == 8:
                        laenge = struct.unpack("<Q", alt)[0]
                    continue
                fh.seek(offset)
                fh.write(alt)
            if laenge is not None:
                fh.truncate(laenge)
            fh.flush()
            os.fsync(fh.fileno())
    for datei in (pfad, pfad + ".neu"):
        try:
            os.remove(datei)
        except OSError:
            pass
    return stellen is not None
