# -*- coding: utf-8 -*-
"""Unsignierte PS5-Programme (einfache ELF) in fake-signierte SELF verwandeln.

Der Lader der PS5 lehnt ein einfaches ELF ab: Ein Spiel, dessen ``eboot.bin`` und Module als blosse ELF-Dateien
vorliegen (``e_type`` ``0xFE10`` oder ``0xFE18``), startet nie. ps5-dump-forge schreibt solche Programme seit v0.5.4
bei jeder Umwandlung als fake-signierte SELF; hier ist dieselbe Arbeit, mit dem vorhandenen Nachbau von
``make_fself`` (:func:`ps5_validator.utils.ps5_backport.elf_signieren`: Programm-Autoritaet ``0x3100000000000002``,
Typ 1 = fake, keine echte Signatur).

Welche Dateien gepruft werden, entscheidet nur der Name - wie bei Forge: ``.elf``, ``.self``, ``.prx``, ``.sprx`` und
eine ``.bin`` nur, wenn sie ``eboot…`` heisst (ein Spiel hat tausende Datendateien ``*.bin``). ``fakelib/`` und
``fakelib2/`` zaehlen mit, der Lader laedt sie ebenfalls.

Nichts hier entschluesselt etwas oder ersetzt eine echte Signatur; ein bereits signiertes SELF bleibt unberuehrt.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Callable

from ps5_validator.utils import ps5_backport

ENDUNGEN = (".elf", ".self", ".prx", ".sprx")
#: ``e_type`` der PS5-Programme: ausfuehrbar mit ASLR und dynamisches Modul.
ET_SCE_EXEC_ASLR = 0xFE10
ET_SCE_DYNAMIC = 0xFE18
ELF_KENNUNG = b"\x7fELF"
#: Wie bei Forge: nicht mehr als so viele Programme je Durchgang (ein Spiel hat einige Dutzend).
MAX_PROGRAMME = 4096
#: Kleinste Datei, die ein ELF-Kopf sein kann, und groesste, die wir im Speicher signieren.
GROESSE_MIN = 0x40
GROESSE_MAX = 3 << 30
#: Name der Zwischendatei beim Schreiben (liegt neben dem Ziel, damit ``os.replace`` auf demselben Laufwerk bleibt).
_ZWISCHEN = ".ps5conv_fself"
#: SELF-Kennungen: ``4F 15 3D 1D`` schreibt make_fself (und damit der Nachbau), ``54 14 F5 EE`` ist die PS5-Schreibweise.
SELF_KENNUNGEN = (b"\x4f\x15\x3d\x1d", b"\x54\x14\xf5\xee")


@dataclass
class Ergebnis:
    """Was ein Signierdurchgang getan hat."""

    signiert: list[str] = field(default_factory=list)
    fehler: list[tuple[str, str]] = field(default_factory=list)
    gesichert: list[str] = field(default_factory=list)


def ist_ausfuehrbar(name: str) -> bool:
    """Ob die Datei nach ihrem Namen ein Programm sein kann (``.bin`` nur als ``eboot*``)."""
    klein = os.path.basename(name).lower()
    if klein.endswith(ENDUNGEN):
        return True
    return klein.endswith(".bin") and klein.startswith("eboot")


def ist_unsigniert(kopf: bytes) -> bool:
    """Ob die ersten Bytes ein einfaches PS5-ELF sind (ELF-Kennung und ``e_type`` ``0xFE10``/``0xFE18``)."""
    if len(kopf) < 0x12 or kopf[:4] != ELF_KENNUNG:
        return False
    return int.from_bytes(kopf[0x10:0x12], "little") in (ET_SCE_EXEC_ASLR, ET_SCE_DYNAMIC)


def unsignierte_finden(ordner: str, abbruch: Callable[[], bool] = lambda: False,
                       melden: Callable[[str], None] | None = None) -> list[str]:
    """Die unsignierten Programme im Ordner als relative Pfade (``/``), sortiert.

    Liest je Kandidat nur die ersten 18 Bytes. Verknuepfungen und Dateien unter 64 Byte werden uebergangen.
    ``melden(ordner)`` wird vor dem Durchgang gerufen (ein grosser Spielordner braucht zum Auflisten Sekunden).
    """
    gefunden: list[str] = []
    wurzel = os.path.abspath(ordner)
    if melden is not None:
        melden(wurzel)
    for pfad, unter, dateien in os.walk(wurzel):
        if abbruch():
            break
        unter.sort()
        for name in sorted(dateien):
            if len(gefunden) >= MAX_PROGRAMME:
                return gefunden
            if not ist_ausfuehrbar(name):
                continue
            voll = os.path.join(pfad, name)
            try:
                if os.path.islink(voll) or os.path.getsize(voll) < GROESSE_MIN:
                    continue
                with open(voll, "rb") as fh:
                    kopf = fh.read(0x12)
            except OSError:
                continue
            if ist_unsigniert(kopf):
                gefunden.append(os.path.relpath(voll, wurzel).replace(os.sep, "/"))
    return gefunden


def signieren(ordner: str, pfade: list[str], *, sicherung: bool = False,
              abbruch: Callable[[], bool] = lambda: False,
              fortschritt: Callable[[int, int, str], None] | None = None) -> Ergebnis:
    """Schreibt die genannten Programme als fake-signierte SELF an Ort und Stelle.

    Jede Datei entsteht erst neben dem Ziel unter einem Zwischennamen und ersetzt es erst, wenn sie fertig ist und
    mit der SELF-Kennung beginnt - ein Fehler mitten drin laesst das Original stehen. Ein Fehler bei einer Datei
    haelt die uebrigen nicht auf; er steht in :attr:`Ergebnis.fehler`.

    Args:
        ordner:   Wurzel, relativ zu der ``pfade`` gelten.
        pfade:    Relative Pfade aus :func:`unsignierte_finden`.
        sicherung: ``True`` legt vorher ``<Datei>.orig`` an (wenn der Ordner das Original des Anwenders ist).
        abbruch:  Wird vor jeder Datei gefragt.
        fortschritt: ``(Nummer, Gesamt, Pfad)`` vor jeder Datei.
    """
    ergebnis = Ergebnis()
    wurzel = os.path.abspath(ordner)
    gesamt = len(pfade)
    for nummer, rel in enumerate(pfade, 1):
        if abbruch():
            break
        if fortschritt is not None:
            fortschritt(nummer, gesamt, rel)
        voll = os.path.normpath(os.path.join(wurzel, *rel.split("/")))
        if os.path.commonpath([wurzel, voll]) != wurzel:
            ergebnis.fehler.append((rel, "Pfad liegt ausserhalb des Ordners"))
            continue
        zwischen = voll + _ZWISCHEN
        try:
            groesse = os.path.getsize(voll)
            if groesse > GROESSE_MAX:
                ergebnis.fehler.append((rel, "zu gross zum Signieren (%d Byte)" % groesse))
                continue
            with open(voll, "rb") as fh:
                daten = fh.read()
            if not ist_unsigniert(daten[:0x12]):
                continue          # inzwischen schon ein SELF (oder kein ELF mehr): nichts zu tun
            signiert = ps5_backport.elf_signieren(daten)
            if signiert[:4] not in SELF_KENNUNGEN:
                raise ps5_backport.BackportFehler("Ergebnis hat keine SELF-Kennung.")
            with open(zwischen, "wb") as aus:
                aus.write(signiert)
            if sicherung:
                alt = voll + ".orig"
                if not os.path.exists(alt):
                    shutil.copy2(voll, alt)          # kopieren, nicht verschieben: Faellt der naechste Schritt aus, steht das Original noch da
                    ergebnis.gesichert.append(rel)
            os.replace(zwischen, voll)
            ergebnis.signiert.append(rel)
        except (OSError, ps5_backport.BackportFehler, MemoryError) as exc:
            ergebnis.fehler.append((rel, str(exc) or exc.__class__.__name__))
            try:
                if os.path.exists(zwischen):
                    os.remove(zwischen)
            except OSError:
                pass
    return ergebnis
