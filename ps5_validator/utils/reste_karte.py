# -*- coding: utf-8 -*-
"""Reste eines gescheiterten oder abgebrochenen Laufs: finden, anzeigen, auf Wunsch entfernen (Dump-Forge-Vorbild, 13.11.2026).

Bricht ein Lauf ab, kann im Zielordner etwas Unfertiges liegen: ein halb geschriebenes Abbild, ein halb verschobener Spielordner,
eine ``.teil``- oder ``.neu``-Datei. Das sieht beim naechsten Blick aus wie ein Ergebnis - und ein halber Spielordner mit
``eboot.bin`` und ``sce_sys`` laesst sich von ShadowMount+ sogar einhaengen. Dieses Modul sucht, was **dieser Lauf** angelegt
haben kann, zeigt es dem Anwender (die Karte im Hauptprogramm) und entfernt es nur auf dessen Wunsch.

Die Sicherung steht im Vordergrund: Nie angeboten, nie entfernt wird die Quelle selbst, ein Ordner, in dem die Quelle liegt,
oder ein Ordner, der in der Quelle liegt (``schuetzen``). Das gilt auch noch einmal beim Entfernen. Das Modul rechnet und loescht
nur ueber die Funktionen, die der Aufrufer reicht; es kennt weder Fenster noch Texte.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Callable

#: Was ein Lauf neben seinem Ergebnis hinterlassen kann (Teilbau, Bau neben der Quelle, Vorgaenger-Endungen).
NEBEN_ENDUNGEN: tuple[str, ...] = (".teil", ".neu", ".part", ".partial")

#: Die Dateien im Wurzelordner eines Spiels, an denen die Konsole und ShadowMount+ ein Spiel erkennen. Sie kommen beim Schreiben
#: oder Verschieben zuletzt, ``eboot.bin`` als Allerletzte: Bricht der Lauf ab, sieht der halbe Ordner nicht wie ein Spiel aus.
STARTDATEIEN_ZULETZT: frozenset = frozenset({"eboot.bin", "sce_sys"})


def startdateien_zuletzt(namen: "list[str]") -> "list[str]":
    """``namen`` (Eintraege im Wurzelordner) mit ``sce_sys`` und ganz am Ende ``eboot.bin``; sonst bleibt die Reihenfolge."""
    return sorted(namen, key=lambda n: (n.lower() in STARTDATEIEN_ZULETZT, n.lower() == "eboot.bin"))


ART_ERGEBNIS = "ergebnis"        # das Ergebnis selbst, unfertig
ART_NEBEN = "neben"              # eine Teil- oder Baudatei neben dem Ergebnis

#: So lange darf das Messen der Groessen hoechstens dauern (Sekunden); danach gilt "mindestens".
ZEITBUDGET_S = 5.0


@dataclass(frozen=True)
class Rest:
    pfad: str
    art: str
    bytes: int
    ordner: bool
    mindestens: bool = False


def _norm(pfad: str) -> str:
    return os.path.normcase(os.path.abspath(pfad))


def liegt_in(pfad: str, ordner: str) -> bool:
    """Ist ``pfad`` der ``ordner`` selbst oder liegt er darin?"""
    a, b = _norm(pfad), _norm(ordner)
    if a == b:
        return True
    try:
        return os.path.commonpath([a, b]) == b
    except ValueError:                       # verschiedene Laufwerke
        return False


def schuetzen(pfad: str, quelle: str) -> bool:
    """``True``, wenn ``pfad`` nie angeboten oder entfernt werden darf.

    Geschuetzt ist die Quelle selbst, alles, worin sie liegt (ein Ordner um die Quelle), und alles, was in ihr liegt
    (ein Ordner der Quelle als Ergebnis) - dazu ein Pfad ohne Namen (Laufwerkswurzel).
    """
    if not pfad or not os.path.basename(os.path.normpath(pfad)):
        return True
    if not quelle:
        return False
    return liegt_in(quelle, pfad) or liegt_in(pfad, quelle)


def _groesse(pfad: str, frist: float) -> tuple[int, bool]:
    if os.path.isfile(pfad):
        try:
            return os.path.getsize(pfad), False
        except OSError:
            return 0, False
    summe = 0
    for wurzel, _ordner, dateien in os.walk(pfad):
        for name in dateien:
            if time.monotonic() > frist:
                return summe, True
            try:
                summe += os.path.getsize(os.path.join(wurzel, name))
            except OSError:
                continue
    return summe, False


def finden(ausgabe: str, quelle: str, *, zielordner: str = "", zeitbudget: float = ZEITBUDGET_S) -> list[Rest]:
    """Die Reste, die ein Lauf mit dem Ergebnis ``ausgabe`` hinterlassen haben kann.

    Das Ergebnis selbst zaehlt, wenn es existiert - der Aufrufer ruft nur nach einem Lauf, der nicht gelungen ist, und ein Ergebnis
    aus frueherer Zeit hat der Lauf beim Start nach der Rueckfrage entfernt. Dazu kommen Dateien mit den ``NEBEN_ENDUNGEN`` daneben.
    ``zielordner``: Liegt ``ausgabe`` nicht direkt darin, gibt es keine Reste (ein ausdruecklich benannter Zielpfad gehoert dem
    Anwender). ``quelle`` schuetzt (siehe ``schuetzen``); eine Sammelkonvertierung hat keine einzelne Quelle und ruft hier nicht.
    """
    if not ausgabe:
        return []
    ausgabe = os.path.normpath(ausgabe)
    if zielordner and _norm(os.path.dirname(ausgabe)) != _norm(zielordner):
        return []
    frist = time.monotonic() + zeitbudget
    kandidaten: list[tuple[str, str]] = [(ausgabe, ART_ERGEBNIS)]
    kandidaten += [(ausgabe + endung, ART_NEBEN) for endung in NEBEN_ENDUNGEN]
    reste: list[Rest] = []
    for pfad, art in kandidaten:
        if not os.path.lexists(pfad) or schuetzen(pfad, quelle):
            continue
        ordner = os.path.isdir(pfad) and not os.path.islink(pfad)
        groesse, abgebrochen = _groesse(pfad, frist) if not os.path.islink(pfad) else (0, False)
        reste.append(Rest(pfad, art, groesse, ordner, abgebrochen))
    return reste


def entfernen(reste: list[Rest], quelle: str, *, ordner_loeschen: Callable[[str], bool],
              datei_loeschen: Callable[[str], None]) -> tuple[list[str], list[tuple[str, str]]]:
    """Entfernt die ``reste``. Rueckgabe: ``(entfernte Pfade, [(Pfad, Fehler)])``.

    ``ordner_loeschen(pfad)`` liefert ``False``, wenn der Ordner nicht ganz weg ist. Jeder Pfad wird vor dem Entfernen noch einmal
    gegen die Quelle geschuetzt; ein Pfad, den es nicht mehr gibt, zaehlt als entfernt.
    """
    weg: list[str] = []
    fehler: list[tuple[str, str]] = []
    for rest in reste:
        if schuetzen(rest.pfad, quelle):
            fehler.append((rest.pfad, "geschuetzt"))
            continue
        try:
            if os.path.isdir(rest.pfad) and not os.path.islink(rest.pfad):
                if not ordner_loeschen(rest.pfad) and os.path.exists(rest.pfad):
                    fehler.append((rest.pfad, "Ordner nicht ganz entfernt"))
                    continue
            elif os.path.lexists(rest.pfad):
                datei_loeschen(rest.pfad)
        except OSError as exc:
            fehler.append((rest.pfad, str(exc)))
            continue
        weg.append(rest.pfad)
    return weg, fehler
