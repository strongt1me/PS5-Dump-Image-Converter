# -*- coding: utf-8 -*-
"""Vorabpruefung einer Quelle vor dem Start: alle Befunde auf einmal, bevor etwas geschrieben wird.

Nach Dump Forge (Nutzerwahl 13.11.2026: "Vorabpruefung mit allen Befunden"): Der exFAT-Schreiber lehnte bisher Namen
ausserhalb von ASCII und symbolische Verknuepfungen erst ab, wenn er an die Arbeit ging - bei einem Dump, der vorher
Stunden lang kopiert wurde. Hier wird die Quelle einmal durchsehen, und der Anwender bekommt **alle** Befunde zugleich,
mit den betroffenen Pfaden, statt den ersten.

Das Modul rechnet nur: Es kennt weder Fenster noch Texte. ``scan`` liest den Ordner, ``quellbefunde`` urteilt ueber die
Namen, ``ausgabename_befund`` ueber den Namen des Ergebnisses, ``fat32_befund`` ueber das Ziellaufwerk. Die Befunde tragen
eine Art, eine Schwere und die betroffenen Pfade; der Aufrufer macht Texte daraus.

Schwere: ``fehler`` nur dort, wo der Schreiber des Zielformats es nachweislich nicht kann (exFAT: Nicht-ASCII-Namen und
Verknuepfungen lehnt ``mkpfs.exfat_writer`` ab, ein Name mit ``:`` oder ``?`` ist in exFAT nicht zulaessig, zwei Namen,
die sich nur in der Schreibung unterscheiden, sind dort derselbe). Alles andere ist ``warnung``: Der Anwender entscheidet.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable

#: Zielformate, die ein Abbild sind (Namen und Tiefe zaehlen dort; ein Ordner nimmt, was das Dateisystem nimmt).
ABBILD_FORMATE: tuple[str, ...] = ("exfat", "ffpkg", "ffpfs", "ffpfsc")

#: Hoechste Zahl Ordnerebenen unter der Wurzel, die gaengige Lesewerkzeuge fuer exFAT-/PFS-Abbilder durchlaufen.
TIEFE_MAX = 32

#: Die groesste Datei, die FAT32 haelt.
FAT32_DATEI_MAX = 4 * 1024 ** 3 - 1

#: Hoechstens so viele Pfade je Befund in der Liste; die Zahl der uebrigen steht in ``mehr``.
LISTE_MAX = 200

#: In exFAT nicht zulaessige Zeichen in einem Namen (dazu alles unter Leerzeichen).
EXFAT_VERBOTEN = frozenset('"*/:<>?\\|')

#: ShadowMount+ haengt ein Abbild unter ``/mnt/shadowmnt/<Name>_<8 Zeichen>`` ein, ``/mnt/shadowmnt/pfsc/...`` bei einem
#: .ffpfsc; FreeBSD 11 erlaubt dafuer 87 Bytes. Daraus folgt die Hoechstlaenge des Namens ohne Endung, in UTF-8-Bytes.
_MOUNT_MAX = 87
_MOUNT_ZUSATZ = len("_xxxxxxxx")


def name_max(zielformat: str) -> int:
    """Die laengste Name ohne Endung (UTF-8-Bytes), den ShadowMount+ fuer dieses Abbildformat einhaengen kann."""
    wurzel = "/mnt/shadowmnt/pfsc/" if zielformat == "ffpfsc" else "/mnt/shadowmnt/"
    return _MOUNT_MAX - len(wurzel) - _MOUNT_ZUSATZ


@dataclass
class Befund:
    """Ein Fund: ``art`` (Schluessel), ``schwere`` (``fehler``/``warnung``), betroffene Pfade, Zahl der uebrigen."""
    art: str
    schwere: str
    eintraege: list[str] = field(default_factory=list)
    mehr: int = 0
    zusatz: dict = field(default_factory=dict)

    @property
    def anzahl(self) -> int:
        return len(self.eintraege) + self.mehr


@dataclass
class Abtastung:
    """Was ``scan`` an einer Quelle gesehen hat."""
    dateien: list[tuple[str, int]] = field(default_factory=list)     # (relativer Pfad mit "/", Groesse)
    ordner: list[str] = field(default_factory=list)                  # relative Pfade aller Ordner
    verweise: list[str] = field(default_factory=list)                # symbolische Verknuepfungen
    gesamt: int = 0
    groesste: int = 0
    vollstaendig: bool = True


def scan(wurzel: str, *, ignoriert: Callable[[str], bool] | None = None, zeitgrenze: float | None = None,
         laeuft: Callable[[], bool] | None = None) -> Abtastung:
    """Liest einen Ordnerbaum einmal, ohne in Verknuepfungen hineinzugehen.

    Was ``ignoriert`` meldet (``mkpfs.utils.is_ignored_name``), laesst der Schreiber ebenfalls weg und zaehlt hier nicht.
    Ueberschreitet das Lesen ``zeitgrenze`` Sekunden oder meldet ``laeuft`` False, endet es mit ``vollstaendig=False``.
    """
    ergebnis = Abtastung()
    ende = time.monotonic() + zeitgrenze if zeitgrenze else None
    stapel: list[tuple[str, str]] = [(wurzel, "")]
    gezaehlt = 0
    while stapel:
        pfad, rel = stapel.pop()
        try:
            with os.scandir(pfad) as eintraege:
                liste = list(eintraege)
        except OSError:
            continue
        for e in liste:
            gezaehlt += 1
            if gezaehlt % 256 == 0 and ((ende is not None and time.monotonic() > ende)
                                        or (laeuft is not None and not laeuft())):
                ergebnis.vollstaendig = False
                return ergebnis
            if ignoriert is not None and ignoriert(e.name):
                continue
            kind = rel + "/" + e.name if rel else e.name
            try:
                if e.is_symlink():
                    ergebnis.verweise.append(kind)
                    continue
                if e.is_dir(follow_symlinks=False):
                    ergebnis.ordner.append(kind)
                    stapel.append((e.path, kind))
                elif e.is_file(follow_symlinks=False):
                    groesse = e.stat(follow_symlinks=False).st_size
                    ergebnis.dateien.append((kind, groesse))
                    ergebnis.gesamt += groesse
                    ergebnis.groesste = max(ergebnis.groesste, groesse)
            except OSError:
                continue
    return ergebnis


def _kuerzen(pfade: Iterable[str]) -> tuple[list[str], int]:
    liste = sorted(pfade)
    return liste[:LISTE_MAX], max(0, len(liste) - LISTE_MAX)


def _befund(art: str, schwere: str, pfade: Iterable[str], **zusatz) -> Befund | None:
    zeigen, mehr = _kuerzen(pfade)
    if not zeigen:
        return None
    return Befund(art=art, schwere=schwere, eintraege=zeigen, mehr=mehr, zusatz=dict(zusatz))


def quellbefunde(a: Abtastung, zielformat: str) -> list[Befund]:
    """Urteilt ueber die Namen und die Tiefe einer abgetasteten Quelle fuer ein Abbildformat.

    Fuer andere Zielformate (Ordner, PKG) gibt es nichts zu sagen: Dort gilt, was das Dateisystem des Ziels nimmt.
    """
    if zielformat not in ABBILD_FORMATE:
        return []
    exfat = zielformat == "exfat"
    alle = [rel for rel, _ in a.dateien] + list(a.ordner)
    befunde: list[Befund | None] = []

    befunde.append(_befund("nicht_ascii", "fehler" if exfat else "warnung",
                           (p for p in alle if not p.isascii()), format=zielformat))
    if exfat:
        befunde.append(_befund("verweis", "fehler", a.verweise))
        befunde.append(_befund(
            "zeichen", "fehler",
            (p for p in alle if any((c in EXFAT_VERBOTEN) for part in p.split("/") for c in part)
             or any(ord(c) < 32 for c in p)),
        ))
    gruppen: dict[str, list[str]] = {}
    for p in alle:
        gruppen.setdefault(p.lower(), []).append(p)
    befunde.append(_befund("kollision", "fehler" if exfat else "warnung",
                           (p for namen in gruppen.values() if len(namen) > 1 for p in namen), format=zielformat))
    tief = [rel for rel, _ in a.dateien if rel.count("/") > TIEFE_MAX]
    tief += [d for d in a.ordner if d.count("/") + 1 > TIEFE_MAX]
    befunde.append(_befund("tiefe", "warnung", tief, grenze=TIEFE_MAX, format=zielformat))
    return [b for b in befunde if b is not None]


def ausgabename_befund(name_ohne_endung: str, zielformat: str) -> Befund | None:
    """Der Name des Ergebnisses ist zu lang fuer das Einhaengen durch ShadowMount+ (nur Abbildformate)."""
    if zielformat not in ABBILD_FORMATE:
        return None
    laenge = len(name_ohne_endung.encode("utf-8", "replace"))
    grenze = name_max(zielformat)
    if laenge <= grenze:
        return None
    return Befund(art="name_lang", schwere="warnung", eintraege=[name_ohne_endung],
                  zusatz={"laenge": laenge, "grenze": grenze, "format": zielformat})


def fat32_befund(dateisystem: str, zielformat: str, gesamt: int, groesste: int, ziel: str = "") -> Befund | None:
    """Ein FAT32-Ziel haelt keine Datei ueber 4 GiB: fuer einen Ordner zaehlt die groesste Datei, fuer ein Abbild die Summe.

    Ein .ffpfsc wird gepackt, seine Groesse ist vorher nicht bekannt - dort sagt die Pruefung nichts.
    """
    if (dateisystem or "").upper() not in ("FAT32", "FAT", "FAT16"):
        return None
    if zielformat == "ffpfsc":
        return None
    noetig = groesste if zielformat in ("folder", "") else gesamt
    if noetig <= FAT32_DATEI_MAX:
        return None
    return Befund(art="fat32", schwere="fehler", eintraege=[ziel] if ziel else [],
                  zusatz={"noetig": noetig, "format": zielformat})
