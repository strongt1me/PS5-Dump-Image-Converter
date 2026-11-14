# -*- coding: utf-8 -*-
"""UFS2-Schreiber fuer ``.ffpkg`` - aus einer Dateiliste, ohne Zwischenordner und ohne UFS2Tool (Stufe 3, Etappe 13).

Bisher baute das Programm eine ``.ffpkg`` nur mit ``UFS2Tool newfs -D <Ordner> <Abbild>``: Das Spiel musste als Ordner auf der Platte liegen
(entpacktes Spiel im Temp-Ordner) und UFS2Tool brauchte erhoehte Rechte. Dieses Modul schreibt dasselbe Abbild aus einer Liste
``(Pfad, Groesse, Oeffner)`` - ein Lesebaum (:mod:`spielbaum`) und der zstd-Strom (:mod:`ampr_zstdpack`) liefern die Bytes.

**Massstab ist UFS2Tool.** Das Abbild soll **byteweise dasselbe** sein, das ``UFS2Tool newfs -D`` fuer denselben Ordner baut (ausser den
Feldern, die UFS2Tool aus der Uhr und der Prozessnummer ableitet: Zeitstempel und ``fs_id`` - sie lassen sich vorgeben). Ein Abbild, das die
Konsole schon mit UFS2Tool-Abbildern mountet, ist so kein neues Wagnis. Deshalb ist das hier ein Nachbau des Erzeugers von UFS2Tool 4.1
(``Ufs2ImageCreator.cs``: ``CreateImageFromDirectory`` / ``WriteFilesystem`` / ``PopulateFromDirectory`` / ``PatchCgAndSuperblock``), samt seinen
Eigenheiten (Groessenschaetzung mit 10 % und 10 MiB Zuschlag, Blockvergabe in der Reihenfolge des Durchlaufs, Verzeichnisbloecke nach
ihren Kindern, Zufallswerte fuer ``di_gen`` aus dem .NET-``Random``).

UFS2Tool 4.1 steht unter der BSD-2-Clause-Lizenz (Copyright (c) 2026, SvenGDK, https://github.com/SvenGDK/UFS2Tool); der Nachbau folgt seinem
Quelltext und behaelt dessen Hinweis bei, siehe ``THIRD_PARTY_LICENSES.md``.

Ablauf: :func:`planen` legt Aufbau und Blockvergabe fest (nur Rechnen, kein Lesen der Dateien), :meth:`Ufs2Plan.schreiben` schreibt zuerst die
Verwaltungsdaten (Superblock, Zylindergruppen, Inodes, Verzeichnisse), dann die Dateiinhalte aus den Oeffnern an ihre festen Plaetze. Das Ziel
muss seekbar sein. Die Reihenfolge, in der die Oeffner gerufen werden, laesst sich vorgeben (ein zstd-Strom ist nur vorwaerts lesbar).
"""
from __future__ import annotations

import os
import struct
import time
from array import array
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator

# Das Wissen ueber das Format teilen sich Schreiber und Leser: Ein Wert, der hier und dort verschieden waere, machte aus jedem Abbild einen
# Fehlerfall (``test_ufs2_schreiber`` liest es mit ``ufs2_dateisystem`` zurueck).
from ps5_validator.utils.ufs2_dateisystem import (  # noqa: E402
    INODE_GROESSE,
    N_DIREKT,
    S_IFDIR as IF_DIR,
    S_IFREG as IF_REG,
    SUPERBLOCK_OFFSET,
    UFS2_MAGIC,
    WURZEL_INODE,
)

Oeffner = Callable[[], Iterator[bytes]]

SUPERBLOCK_GROESSE = 8192              # so viel schreibt der Schreiber (der Leser braucht nur die ersten 1376 Bytes)
CG_MAGIC = 0x090255
DIRBLKSIZ = 512
MAX_BSIZE = 65536
MAX_CONTIG = 16
CG_KOPF_GRUNDGROESSE = 168
CSUM_GROESSE = 16
SEKTOR = 512                       # UFS2Tool legt jedes -S auf 512 zurueck (NormalizeSectorSizeForLayout)
DT_DIR = 4
DT_REG = 8
PERM = 0x16D                       # 0555
FS_FLAGS_UPDATED = 0x80
FS_44INODEFMT = 2
SCHAETZ_BYTES_JE_EINTRAG = 24
STANDARD_INODES_JE_GRUPPE = 2048
MAX_NAME = 255


class Ufs2SchreibFehler(ValueError):
    """Aus der Liste laesst sich kein UFS2-Abbild bauen (Name, Parameter, zu wenig Platz)."""


# ---------------------------------------------------------------------------------------------------------------------------
# Kleine Rechenhelfer: C#-Ganzzahlen kuerzen zur Null hin, Python rundet nach unten.
# ---------------------------------------------------------------------------------------------------------------------------
def _tdiv(a: int, b: int) -> int:
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def _hochrunden(wert: int, schritt: int) -> int:
    return _tdiv(wert + schritt - 1, schritt) * schritt


def _s32(wert: int) -> int:
    """Die unteren 32 Bit als vorzeichenbehaftete Zahl (C#: ``(int)(x & 0xFFFFFFFF)``)."""
    return ((wert + 0x80000000) & 0xFFFFFFFF) - 0x80000000


def _log2(wert: int) -> int:
    erg = 0
    while wert > 1:
        wert >>= 1
        erg += 1
    return erg


class _DotNetRandom:
    """``System.Random(seed)`` aus .NET (Knuth, ``Net5CompatSeedImpl``): UFS2Tool wuerfelt damit ``di_gen`` der vorbereiteten Inodes."""

    _MBIG = 2147483647
    _MSEED = 161803398

    def __init__(self, seed: int) -> None:
        subtraktion = self._MBIG if seed == -2147483648 else abs(seed)
        mj = self._MSEED - subtraktion
        feld = [0] * 56
        feld[55] = mj
        mk = 1
        for i in range(1, 55):
            ii = (21 * i) % 55
            feld[ii] = mk
            mk = mj - mk
            if mk < 0:
                mk += self._MBIG
            mj = feld[ii]
        for _k in range(1, 5):
            for i in range(1, 56):
                n = i + 30
                if n >= 55:
                    n -= 55
                feld[i] -= feld[1 + n]
                if feld[i] < 0:
                    feld[i] += self._MBIG
        self._feld = feld
        self._inext = 0
        self._inextp = 21

    def _stichprobe(self) -> int:
        feld = self._feld
        a = self._inext + 1
        if a >= 56:
            a = 1
        b = self._inextp + 1
        if b >= 56:
            b = 1
        wert = feld[a] - feld[b]
        if wert == self._MBIG:
            wert -= 1
        if wert < 0:
            wert += self._MBIG
        feld[a] = wert
        self._inext = a
        self._inextp = b
        return wert

    def naechste(self, minimum: int, maximum: int) -> int:
        """``Next(minValue, maxValue)`` fuer Spannen bis ``int.MaxValue``."""
        spanne = maximum - minimum
        return int(self._stichprobe() * (1.0 / self._MBIG) * spanne) + minimum


# ---------------------------------------------------------------------------------------------------------------------------
# Parameter
# ---------------------------------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Ufs2Profil:
    """Die ``newfs``-Parameter, die fuer ein ``.ffpkg`` zaehlen (``-O 2 -b -f -S -m -i``; UFS2 ohne Journal, ohne Soft Updates)."""

    block_size: int = 65536
    fragment_size: int = 65536
    sector_size: int = 4096                     # nur zur Anzeige: UFS2Tool normalisiert jeden Wert auf 512
    min_free_percent: int = 8
    bytes_per_inode: int = 0                    # 0: Standard (2048 Inodes je Gruppe)
    avg_file_size: int = 16384
    avg_files_per_dir: int = 64
    optimierung_platz: bool = False
    volume_name: str = ""

    def pruefen(self) -> None:
        bs, fs = self.block_size, self.fragment_size
        if bs <= 0 or bs & (bs - 1) or bs < 4096 or bs > 65536:
            raise Ufs2SchreibFehler("Blockgroesse muss eine Zweierpotenz von 4 KiB bis 64 KiB sein: %d" % bs)
        if fs <= 0 or fs & (fs - 1) or fs < 512 or fs > bs:
            raise Ufs2SchreibFehler("Fragmentgroesse muss eine Zweierpotenz von 512 B bis zur Blockgroesse sein: %d" % fs)
        if bs // fs not in (1, 2, 4, 8):
            raise Ufs2SchreibFehler("Block-/Fragmentverhaeltnis muss 1, 2, 4 oder 8 sein")
        if self.sector_size < 512 or self.sector_size & (self.sector_size - 1):
            raise Ufs2SchreibFehler("Sektorgroesse muss eine Zweierpotenz ab 512 sein")
        if fs < self.sector_size:
            raise Ufs2SchreibFehler("Fragmentgroesse darf nicht unter der Sektorgroesse liegen")
        if not 0 <= self.min_free_percent <= 99:
            raise Ufs2SchreibFehler("Minimalfreiraum muss zwischen 0 und 99 Prozent liegen")
        if self.bytes_per_inode < 0:
            raise Ufs2SchreibFehler("Bytes je Inode duerfen nicht negativ sein")


# ---------------------------------------------------------------------------------------------------------------------------
# Verzeichnisbaum aus der Liste
# ---------------------------------------------------------------------------------------------------------------------------
class _Knoten:
    __slots__ = ("name", "ordner", "groesse", "oeffner", "rel", "kinder", "inode")

    def __init__(self, name: str, ordner: bool, groesse: int = 0, oeffner: "Oeffner | None" = None, rel: str = "") -> None:
        self.name = name
        self.ordner = ordner
        self.groesse = groesse
        self.oeffner = oeffner
        self.rel = rel
        self.kinder: "dict[str, _Knoten]" = {}
        self.inode = 0


def _baum_bauen(eintraege: "Iterable[tuple[str, int, Oeffner]]", ordner: Iterable[str]) -> _Knoten:
    """Der Verzeichnisbaum aus ``(Pfad, Groesse, Oeffner)``; ``ordner`` nennt Verzeichnisse, die es auch ohne Datei darin geben soll.

    Abgelehnt statt stillschweigend geaendert: Nicht-ASCII-Namen, leere und ``.``/``..``-Namen, Rueckstriche, Namen ueber 255 Zeichen,
    doppelte Pfade und ein Name als Datei und als Verzeichnis. (Ein Unterschied nur in der Schreibung ist in UFS2 erlaubt.)
    """
    wurzel = _Knoten("", True)

    def _pruefen(pfad: str) -> list[str]:
        teile = pfad.split("/")
        for t in teile:
            if t in ("", ".", "..") or "\\" in t or any(ord(c) < 32 for c in t) or len(t) > MAX_NAME:
                raise Ufs2SchreibFehler("Unbrauchbarer Pfad: %r" % pfad)
            if not t.isascii():
                raise Ufs2SchreibFehler("Nicht-ASCII-Name im Pfad (UFS2Tool legt nur ASCII an): %r" % pfad)
        return teile

    def _ordner(teile: list[str]) -> _Knoten:
        knoten = wurzel
        for i, teil in enumerate(teile):
            kind = knoten.kinder.get(teil)
            if kind is None:
                kind = _Knoten(teil, True, rel="/".join(teile[:i + 1]))
                knoten.kinder[teil] = kind
            elif not kind.ordner:
                raise Ufs2SchreibFehler("%r ist Datei und Verzeichnis zugleich" % "/".join(teile[:i + 1]))
            knoten = kind
        return knoten

    for pfad, groesse, oeffner in eintraege:
        teile = _pruefen(pfad)
        eltern = _ordner(teile[:-1])
        if teile[-1] in eltern.kinder:
            raise Ufs2SchreibFehler("Pfad doppelt oder zugleich Datei und Verzeichnis: %r" % pfad)
        if groesse < 0:
            raise Ufs2SchreibFehler("Negative Groesse: %r" % pfad)
        eltern.kinder[teile[-1]] = _Knoten(teile[-1], False, int(groesse), oeffner, pfad)
    for pfad in ordner:
        if pfad:
            _ordner(_pruefen(pfad))
    return wurzel


def _sortiert(knoten: _Knoten) -> "list[_Knoten]":
    """Die Reihenfolge, in der UFS2Tool die Eintraege eines Verzeichnisses sieht: ``EnumerateFileSystemInfos`` auf NTFS - nach dem Namen in
    Grossschreibung."""
    return sorted(knoten.kinder.values(), key=lambda k: (k.name.upper(), k.name))


# ---------------------------------------------------------------------------------------------------------------------------
# Verzeichnisbloecke (struct direct)
# ---------------------------------------------------------------------------------------------------------------------------
def _reclen(namenslaenge: int) -> int:
    return (8 + namenslaenge + 1 + 3) & ~3


def _verzeichnisbloecke_noetig(eintraege: "list[tuple[str, int, int]]", bs: int) -> int:
    """``CalculateDirBlocksNeeded``: wie viele Bloecke die Eintraege samt ``.`` und ``..`` brauchen."""
    alle = [(1, _reclen(1), 8 + 1 + 1), (2, _reclen(2), 8 + 2 + 1)]
    for name, _ino, _typ in eintraege:
        alle.append((len(name), _reclen(len(name)), 8 + len(name) + 1))
    bloecke = 0
    idx = 0
    while idx < len(alle):
        bloecke += 1
        pos = 0
        while idx < len(alle):
            _laenge, reclen, min_groesse = alle[idx]
            if min_groesse > DIRBLKSIZ:
                raise Ufs2SchreibFehler("Verzeichniseintrag zu lang")
            rest = DIRBLKSIZ - pos % DIRBLKSIZ
            if min_groesse > rest:
                pos += rest
                if pos >= bs:
                    break
                rest = DIRBLKSIZ
            if pos + min_groesse > bs:
                break
            letzter = idx == len(alle) - 1
            if not letzter and idx + 1 < len(alle):
                naechster = alle[idx + 1][2]
                danach = pos + reclen
                danach_in = danach % DIRBLKSIZ
                letzter = (naechster > DIRBLKSIZ - danach_in and danach_in != 0) or (danach + naechster > bs)
            if letzter:
                pos += DIRBLKSIZ - pos % DIRBLKSIZ
            else:
                pos += reclen
            idx += 1
            if letzter and pos >= bs:
                break
    return max(1, bloecke)


def _eintrag(block: bytearray, pos: int, ino: int, reclen: int, typ: int, name: str) -> None:
    struct.pack_into("<IHBB", block, pos, ino, reclen, typ, len(name))
    if name:
        block[pos + 8:pos + 8 + len(name)] = name.encode("ascii")


def _verzeichnisbloecke(eigener: int, eltern: int, eintraege: "list[tuple[str, int, int]]", bs: int, anzahl: int) -> "list[bytes]":
    """``WriteDirBlocks``: die Bytes der Verzeichnisbloecke."""
    alle = [(eigener, DT_DIR, "."), (eltern, DT_DIR, "..")] + [(ino, typ, name) for name, ino, typ in eintraege]
    idx = 0
    ergebnis: list[bytes] = []
    for _b in range(anzahl):
        block = bytearray(bs)
        pos = 0
        while idx < len(alle):
            ino, typ, name = alle[idx]
            reclen = _reclen(len(name))
            min_groesse = 8 + len(name) + 1
            if min_groesse > DIRBLKSIZ:
                raise Ufs2SchreibFehler("Verzeichniseintrag %r zu lang" % name)
            rest = DIRBLKSIZ - pos % DIRBLKSIZ
            if min_groesse > rest:
                if pos + rest >= bs:
                    break
                _eintrag(block, pos, 0, rest, 0, "")
                pos += rest
                rest = DIRBLKSIZ
            if pos + min_groesse > bs:
                break
            letzter = idx == len(alle) - 1
            if not letzter and idx + 1 < len(alle):
                naechster = 8 + len(alle[idx + 1][2]) + 1
                danach = pos + reclen
                danach_in = danach % DIRBLKSIZ
                letzter = (naechster > DIRBLKSIZ - danach_in and danach_in != 0) or (danach + naechster > bs)
            if letzter:
                reclen = DIRBLKSIZ - pos % DIRBLKSIZ
            _eintrag(block, pos, ino, reclen, typ, name)
            pos += reclen
            idx += 1
            if letzter and idx < len(alle):
                if pos >= bs:
                    break
            elif letzter:
                break
        if pos == 0:
            raise Ufs2SchreibFehler("Verzeichnisblock ohne Eintrag (Fehler in der Blockzahl)")
        if pos % DIRBLKSIZ != 0:
            rest = DIRBLKSIZ - pos % DIRBLKSIZ
            _eintrag(block, pos, 0, rest, 0, "")
            pos += rest
        while pos + DIRBLKSIZ <= bs:
            _eintrag(block, pos, 0, DIRBLKSIZ, 0, "")
            pos += DIRBLKSIZ
        ergebnis.append(bytes(block))
    if idx < len(alle):
        raise Ufs2SchreibFehler("Nur %d von %d Verzeichniseintraegen untergebracht" % (idx, len(alle)))
    return ergebnis


# ---------------------------------------------------------------------------------------------------------------------------
# Bitmaps
# ---------------------------------------------------------------------------------------------------------------------------
def _bits_setzen(bm: bytearray, von: int, bis: int) -> None:
    """Die Bits ``von`` bis ``bis - 1`` auf 1 (frei)."""
    if bis <= von:
        return
    erstes, letztes = von >> 3, (bis - 1) >> 3
    if erstes == letztes:
        bm[erstes] |= ((1 << (bis - von)) - 1) << (von & 7)
        return
    bm[erstes] |= (0xFF << (von & 7)) & 0xFF
    if letztes > erstes + 1:
        bm[erstes + 1:letztes] = b"\xFF" * (letztes - erstes - 1)
    rest = bis - (letztes << 3)
    bm[letztes] |= (1 << rest) - 1


def _bit(bm: bytearray, f: int) -> bool:
    return bool(bm[f >> 3] & (1 << (f & 7)))


# ---------------------------------------------------------------------------------------------------------------------------
# Der Plan
# ---------------------------------------------------------------------------------------------------------------------------
@dataclass
class _Zuteilung:
    """Wo die Bloecke einer Datei (oder eines Verzeichnisses) liegen."""

    direkt: "list[int]" = field(default_factory=list)
    indirekt: int = 0
    doppelt: int = 0
    dreifach: int = 0
    meta_bloecke: int = 0
    letzter_datenblock: int = 0
    daten: "array" = field(default_factory=lambda: array("q"))            # alle Datenbloecke in Dateireihenfolge
    zeiger: "list[tuple[int, array]]" = field(default_factory=list)       # (Block, Zeiger) der Zeigerbloecke


@dataclass
class Ufs2Plan:
    """Aufbau und Blockvergabe eines Abbilds; :meth:`schreiben` legt es auf die Platte."""

    profil: Ufs2Profil
    groesse: int                                       # Bytes des fertigen Abbilds
    dateien_bytes: int                                 # Summe der Dateigroessen
    dateien: "list[tuple[str, int, Oeffner, array]]"   # (Pfad, Groesse, Oeffner, Datenbloecke) in Baumreihenfolge
    _regionen: "list[tuple[int, bytes | Callable[[], bytes]]]" = field(default_factory=list)   # (Offset, Bytes) der Verwaltungsdaten
    inodes_belegt: int = 0
    verzeichnisse: int = 0
    gruppen: int = 0

    def schreiben(self, ziel: str, *, reihenfolge: Iterable[str] = (), abbruch: Callable[[], bool] = lambda: False,
                  melden: "Callable[[str, int, int, int], None] | None" = None) -> int:
        """Schreibt das Abbild nach ``ziel`` (neu angelegt, auf die Endgroesse gestreckt). Gibt die Groesse zurueck.

        ``reihenfolge`` nennt Pfade, deren Oeffner zuerst gerufen werden; der Rest folgt in Baumreihenfolge. ``melden(phase, fertig, gesamt,
        bytes)`` bekommt ``"write"`` nach jeder Datei. Bricht ``abbruch()`` ab, kommt :class:`InterruptedError`. Fehler und Abbruch lassen
        das halbe Ziel liegen; der Aufrufer raeumt es weg (er schreibt nach ``<Ziel>.teil``).
        """
        bs = self.profil.block_size
        fs = self.profil.fragment_size
        fpb = bs // fs
        rang = {rel: i for i, rel in enumerate(reihenfolge)}
        offen = [d for d in self.dateien if d[1] > 0]
        offen.sort(key=lambda d: rang.get(d[0], len(rang)))
        gesamt = sum(d[1] for d in offen)
        with open(ziel, "w+b") as out:
            out.truncate(self.groesse)
            # Aufsteigend nach Offset: Auf NTFS fuellt ein Schreiben weit hinter dem bisherigen Ende die Luecke davor mit Nullen.
            for offset, daten in sorted(self._regionen, key=lambda r: r[0]):
                if abbruch():
                    raise InterruptedError("abgebrochen")
                if callable(daten):
                    daten = daten()
                out.seek(offset)
                out.write(daten)
            geschrieben = 0
            for pfad, groesse, oeffner, bloecke in offen:
                if abbruch():
                    raise InterruptedError("abgebrochen")
                _datei_schreiben(out, bs, fs, fpb, bloecke, oeffner, groesse, pfad, abbruch)
                geschrieben += groesse
                if melden is not None:
                    melden("write", 1, gesamt, geschrieben)
            out.flush()
        return self.groesse


def _datei_schreiben(out, bs: int, fs: int, fpb: int, bloecke: "array", oeffner: Oeffner, groesse: int, pfad: str,
                     abbruch: Callable[[], bool]) -> None:
    pos = 0
    strom = iter(oeffner())
    try:
        for stueck in strom:
            if abbruch():
                raise InterruptedError("abgebrochen")
            ansicht = memoryview(stueck)
            laenge = len(ansicht)
            if pos + laenge > groesse:
                raise Ufs2SchreibFehler("%s ist laenger als gemeldet (%d Bytes)" % (pfad, groesse))
            vorn = 0
            while vorn < laenge:
                blk, im_block = divmod(pos, bs)
                start = bloecke[blk]
                lauf = 1
                noetig = (im_block + laenge - vorn + bs - 1) // bs
                while lauf < noetig and blk + lauf < len(bloecke) and bloecke[blk + lauf] == start + lauf * fpb:
                    lauf += 1
                nehmen = min(laenge - vorn, lauf * bs - im_block)
                out.seek(start * fs + im_block)
                out.write(ansicht[vorn:vorn + nehmen])
                pos += nehmen
                vorn += nehmen
    finally:
        schliessen = getattr(strom, "close", None)
        if callable(schliessen):
            schliessen()
    if pos != groesse:
        raise Ufs2SchreibFehler("%s ist kuerzer als gemeldet (%d von %d Bytes)" % (pfad, pos, groesse))


def groesse_schaetzen(wurzel: _Knoten, bs: int) -> "tuple[int, int, int]":
    """``CalculateDirectorySizes(Ordner, Blockgroesse)``: ``(rohe Bytes, blockausgerichtete Bytes, Zahl der Eintraege)``."""
    roh = 0
    ausgerichtet = 0
    eintraege = 0
    zeiger_je_block = bs // 8

    def _verzeichnis(knoten: _Knoten) -> int:
        anzahl = 2 + len(knoten.kinder)
        noetig = max(1, (anzahl * SCHAETZ_BYTES_JE_EINTRAG + bs - 1) // bs)
        return noetig * bs

    ausgerichtet += _verzeichnis(wurzel)
    stapel = list(wurzel.kinder.values())
    while stapel:
        k = stapel.pop()
        eintraege += 1
        if k.ordner:
            ausgerichtet += _verzeichnis(k)
            stapel.extend(k.kinder.values())
            continue
        laenge = k.groesse
        roh += laenge
        if laenge <= 0:
            continue
        bloecke = (laenge + bs - 1) // bs
        ausgerichtet += bloecke * bs
        if bloecke > N_DIREKT:
            ausgerichtet += bs
            rest = bloecke - N_DIREKT
            if rest > zeiger_je_block:
                rest -= zeiger_je_block
                zweite = (rest + zeiger_je_block - 1) // zeiger_je_block
                ausgerichtet += (1 + zweite) * bs
                if rest > zeiger_je_block * zeiger_je_block:
                    rest -= zeiger_je_block * zeiger_je_block
                    dritte_2 = (rest + zeiger_je_block - 1) // zeiger_je_block
                    dritte_1 = (dritte_2 + zeiger_je_block - 1) // zeiger_je_block
                    ausgerichtet += (1 + dritte_1 + dritte_2) * bs
    return roh, ausgerichtet, eintraege


def profil_aus_newfs(profil) -> Ufs2Profil:
    """Ein ``ffpkg_support.FfpkgNewfsProfile`` (die ``newfs``-Parameter des Programms) als :class:`Ufs2Profil`.

    Fehlt der Minimalfreiraum, gilt wie bei ``newfs`` der Vorgabewert 8; fehlt die Inode-Dichte, der Standard (2048 Inodes je Gruppe).
    """
    frei = getattr(profil, "min_free_percent", None)
    dichte = getattr(profil, "inode_density", None)
    return Ufs2Profil(block_size=int(profil.block_size), fragment_size=int(profil.fragment_size),
                      sector_size=int(getattr(profil, "sector_size", 4096)), min_free_percent=8 if frei is None else int(frei),
                      bytes_per_inode=0 if dichte is None else int(dichte))


def namen_pruefen(eintraege: "Iterable[tuple[str, int, Oeffner | None]]", ordner: Iterable[str] = ()) -> None:
    """Wirft :class:`Ufs2SchreibFehler`, wenn aus dieser Liste kein UFS2-Abbild wird (Namen, doppelte Pfade) - ohne etwas zu planen."""
    _baum_bauen(eintraege, ordner)


def _inodes_je_gruppe(profil: Ufs2Profil, gesamt_bytes: int) -> int:
    """``ComputeInodesPerGroup``."""
    if profil.bytes_per_inode > 0:
        inodes = gesamt_bytes // profil.bytes_per_inode
        fpb = profil.block_size // profil.fragment_size
        fpg = STANDARD_INODES_JE_GRUPPE * fpb
        gesamt_frags = gesamt_bytes // profil.fragment_size
        gruppen = max(1, (gesamt_frags + fpg - 1) // fpg)
        ipg = inodes // gruppen
        je_block = profil.block_size // INODE_GROESSE
        if je_block > 0:
            ipg = ((ipg + je_block - 1) // je_block) * je_block
        return max(ipg, je_block)
    return STANDARD_INODES_JE_GRUPPE


def abbildgroesse(eintraege: "Iterable[tuple[str, int, Oeffner]]", ordner: Iterable[str] = (),
                  profil: "Ufs2Profil | None" = None) -> int:
    """Die Groesse, die ``UFS2Tool newfs -D`` fuer diese Dateien anlegt (ohne etwas zu planen)."""
    profil = profil or Ufs2Profil()
    profil.pruefen()
    return _abbildgroesse(_baum_bauen(eintraege, ordner), profil)


def _abbildgroesse(wurzel: _Knoten, profil: Ufs2Profil) -> int:
    bs, fs = profil.block_size, profil.fragment_size
    _roh, ausgerichtet, eintraege = groesse_schaetzen(wurzel, bs)
    gesamt = int(ausgerichtet * 1.10) + 10 * 1024 * 1024
    if gesamt < bs * 16:
        gesamt = bs * 16
    gesamt = _hochrunden(gesamt, fs)
    noetig = eintraege + 3
    ipg = _inodes_je_gruppe(profil, gesamt)
    fpb = bs // fs
    fpg = ipg * fpb
    gruppen = max(1, (gesamt // fs + fpg - 1) // fpg)
    if noetig > gruppen * ipg:
        gebraucht = (noetig + ipg - 1) // ipg
        gebraucht_bytes = gebraucht * fpg * fs
        if gebraucht_bytes > gesamt:
            gesamt = _hochrunden(gebraucht_bytes, fs)
    return gesamt


# ---------------------------------------------------------------------------------------------------------------------------
# Inode und Superblock
# ---------------------------------------------------------------------------------------------------------------------------
def _inode_bytes(*, ordner: bool, nlink: int, bs: int, groesse: int, blocks: int, zeit: int, zuteilung: "_Zuteilung | None",
                 tiefe: int = 0) -> bytes:
    inode = bytearray(INODE_GROESSE)
    struct.pack_into("<HhIII", inode, 0, (IF_DIR if ordner else IF_REG) | PERM, nlink, 0, 0, bs)
    struct.pack_into("<qq", inode, 0x10, groesse, blocks)
    struct.pack_into("<qqqq", inode, 0x20, zeit, zeit, zeit, zeit)
    struct.pack_into("<i", inode, 0x50, 1)                                     # di_gen
    if zuteilung is not None:
        for i, frag in enumerate(zuteilung.direkt[:N_DIREKT]):
            struct.pack_into("<q", inode, 0x70 + i * 8, frag)
        for i, frag in enumerate((zuteilung.indirekt, zuteilung.doppelt, zuteilung.dreifach)):
            if frag:
                struct.pack_into("<q", inode, 0xD0 + i * 8, frag)
    struct.pack_into("<I", inode, 0xF0, tiefe if ordner else 0)
    return bytes(inode)


def _inode_bloecke_512(groesse: int, bs: int, fs: int, meta: int) -> int:
    """``di_blocks`` in 512-Byte-Einheiten wie ``WriteInodeAtPosition``."""
    fpb = bs // fs
    sektoren_je_frag = fs // SEKTOR
    noetig = (groesse + bs - 1) // bs if groesse > 0 else 0
    if noetig > N_DIREKT:
        daten_frags = noetig * fpb
    else:
        voll = groesse // bs if groesse > 0 else 0
        daten_frags = voll * fpb
        rest = groesse % bs if groesse > 0 else 0
        if rest > 0:
            daten_frags += (rest + fs - 1) // fs
    return (daten_frags + meta * fpb) * sektoren_je_frag


class _Geometrie:
    """Die Zahlen aus ``WriteFilesystem``."""

    def __init__(self, profil: Ufs2Profil, gesamt_bytes: int) -> None:
        bs, fs = profil.block_size, profil.fragment_size
        self.bs, self.fs = bs, fs
        self.fpb = fpb = bs // fs
        self.gesamt_bytes = gesamt_bytes
        self.gesamt_frags = gesamt_bytes // fs
        self.ipg = ipg = _inodes_je_gruppe(profil, gesamt_bytes)
        self.fpg = fpg = ipg * fpb
        self.ncg = max(1, (self.gesamt_frags + fpg - 1) // fpg)
        self.sblkno = _hochrunden((SUPERBLOCK_OFFSET + SUPERBLOCK_GROESSE + fs - 1) // fs, fpb)
        self.cblkno = self.sblkno + _hochrunden((SUPERBLOCK_GROESSE + fs - 1) // fs, fpb)
        self.iblkno = self.cblkno + fpb
        inopb = bs // INODE_GROESSE
        self.inopb = inopb
        inodebloecke = ((ipg + inopb - 1) // inopb) * fpb
        self.dblkno = self.iblkno + inodebloecke
        self.max_contig = max(1, MAX_BSIZE // bs)
        self.contig_summe = min(self.max_contig, MAX_CONTIG)
        inode_bitmap = (ipg + 7) // 8
        frag_bitmap = (fpg + 7) // 8
        roh = CG_KOPF_GRUNDGROESSE + inode_bitmap + frag_bitmap + 4
        if self.contig_summe > 0:
            roh += self.contig_summe * 4 + (fpg // fpb + 7) // 8
        self.cg_groesse = _hochrunden(roh, fs)
        self.cs_groesse = _hochrunden(self.ncg * CSUM_GROESSE, fs)
        self.cs_frags = (self.cs_groesse + fs - 1) // fs
        self.cs_frags_blk = ((self.cs_groesse + bs - 1) // bs) * fpb
        self.cs_schwanz_frei = self.cs_frags_blk - self.cs_frags
        self.wurzel_frag = self.dblkno + self.cs_frags_blk


def planen(eintraege: "Iterable[tuple[str, int, Oeffner]]", ordner: Iterable[str] = (), *, profil: "Ufs2Profil | None" = None,
           zeit: "int | None" = None, zeit_inodes: "int | None" = None, fs_id: "tuple[int, int] | None" = None,
           abbruch: Callable[[], bool] = lambda: False) -> Ufs2Plan:
    """Legt Aufbau und Blockvergabe fest - so, wie ``UFS2Tool newfs -D`` sie fuer einen Ordner mit diesen Dateien faende.

    ``zeit`` ist der Zeitstempel des Dateisystems, ``zeit_inodes`` der der Inodes (UFS2Tool fragt die Uhr zweimal; ohne Angabe gilt
    ``zeit``), ``fs_id`` das Paar ``fs_id[0], fs_id[1]`` (UFS2Tool leitet es aus der Uhr und der Prozessnummer ab). Ohne Angabe gilt die
    Uhr und die eigene Prozessnummer.
    """
    profil = profil or Ufs2Profil()
    profil.pruefen()
    wurzel = _baum_bauen(eintraege, ordner)
    gesamt_bytes = _abbildgroesse(wurzel, profil)
    if gesamt_bytes < profil.block_size * 16:
        raise Ufs2SchreibFehler("Abbild zu klein")
    jetzt = int(time.time()) if zeit is None else int(zeit)
    jetzt_inodes = jetzt if zeit_inodes is None else int(zeit_inodes)
    if fs_id is None:
        fs_id = ((jetzt & 0xFFFFFFFF), (((jetzt >> 16) ^ os.getpid()) & 0xFFFFFFFF))
    return _Planer(profil, wurzel, gesamt_bytes, jetzt, jetzt_inodes, fs_id, abbruch).planen()


class _Planer:
    def __init__(self, profil: Ufs2Profil, wurzel: _Knoten, gesamt_bytes: int, zeit: int, zeit_inodes: int,
                 fs_id: "tuple[int, int]", abbruch: Callable[[], bool]) -> None:
        self.profil = profil
        self.wurzel = wurzel
        self.g = _Geometrie(profil, gesamt_bytes)
        self.zeit = zeit
        self.zeit_inodes = zeit_inodes
        self.fs_id = fs_id
        self.abbruch = abbruch
        g = self.g
        self.naechster_inode = 3
        self.aktuelle_gruppe = 0
        self.naechster_frag = g.wurzel_frag + g.fpb
        self.hoechststand = [0] * g.ncg
        self.hoechststand[0] = self.naechster_frag
        self.verz_je_gruppe = [0] * g.ncg
        self.verz_je_gruppe[WURZEL_INODE // g.ipg] = 1
        self.verzeichnisse = 0
        self.dateien_belegt = 0
        self.schwanz_frei: "set[int]" = set()
        self.inode_tabelle: "dict[int, bytes]" = {}
        self.regionen: "list[tuple[int, bytes | Callable[[], bytes]]]" = []
        self.dateiliste: "list[tuple[str, int, Oeffner, array]]" = []
        self.max_inodes = g.ncg * g.ipg

    # -- Blockvergabe (AllocateDataBlock) ---------------------------------------------------------------------------------
    def _block(self) -> int:
        g = self.g
        limit = g.fpg
        if self.aktuelle_gruppe == g.ncg - 1:
            letzte = g.gesamt_frags - self.aktuelle_gruppe * g.fpg
            if letzte < limit:
                limit = letzte
        if self.naechster_frag + g.fpb > limit:
            self.aktuelle_gruppe += 1
            if self.aktuelle_gruppe >= g.ncg:
                raise Ufs2SchreibFehler("Abbild zu klein: keine Zylindergruppe mehr fuer Daten")
            self.naechster_frag = g.dblkno
            limit = g.fpg
            if self.aktuelle_gruppe == g.ncg - 1:
                letzte = g.gesamt_frags - self.aktuelle_gruppe * g.fpg
                if letzte < limit:
                    limit = letzte
            if self.naechster_frag + g.fpb > limit:
                raise Ufs2SchreibFehler("Abbild zu klein: Gruppe %d hat nur %d freie Fragmente" % (
                    self.aktuelle_gruppe, limit - self.naechster_frag))
        frag = self.naechster_frag
        self.naechster_frag += g.fpb
        self.hoechststand[self.aktuelle_gruppe] = self.naechster_frag
        return self.aktuelle_gruppe * g.fpg + frag

    # -- Zuteilung einer Datei (AllocateAndWriteFile ohne das Schreiben) ------------------------------------------------------
    def _einfach_indirekt(self, z: _Zuteilung, block: int, anzahl: int) -> None:
        zeiger = array("q")
        for _i in range(anzahl):
            frag = self._block()
            z.letzter_datenblock = frag
            zeiger.append(frag)
            z.daten.append(frag)
        z.zeiger.append((block, zeiger))

    def _datei_zuteilen(self, groesse: int) -> _Zuteilung:
        g = self.g
        z = _Zuteilung()
        if groesse == 0:
            return z
        noetig = (groesse + g.bs - 1) // g.bs
        direkt = min(noetig, N_DIREKT)
        zeiger_je_block = g.bs // 8
        # UFS2Tool kennt nur direkte, einfach und zweifach indirekte Bloecke: Sein Erzeuger schriebe fuer eine groessere Datei mehr
        # Zeiger in einen Zeigerblock, als hineinpassen (und bricht dabei ab). Das sind bei 64 KiB Bloecken 4,4 TB, bei 32 KiB 549 GB.
        hoechstens = N_DIREKT + zeiger_je_block + zeiger_je_block * zeiger_je_block
        if noetig > hoechstens:
            raise Ufs2SchreibFehler("Datei mit %d Bytes ist zu gross: hoechstens %d Bytes bei %d-Byte-Bloecken (UFS2Tool kennt keine "
                                    "dreifach indirekten Bloecke)" % (groesse, hoechstens * g.bs, g.bs))
        for _i in range(direkt):
            frag = self._block()
            z.direkt.append(frag)
            z.daten.append(frag)
            z.letzter_datenblock = frag
        rest = noetig - direkt
        if rest > 0:
            einzeln = min(rest, zeiger_je_block)
            z.indirekt = self._block()
            z.meta_bloecke += 1
            self._einfach_indirekt(z, z.indirekt, einzeln)
            rest -= einzeln
        if rest > 0:
            z.doppelt = self._block()
            z.meta_bloecke += 1
            zweite = (rest + zeiger_je_block - 1) // zeiger_je_block
            dzeiger = array("q")
            for _i in range(zweite):
                dieses = min(rest, zeiger_je_block)
                sblock = self._block()
                z.meta_bloecke += 1
                dzeiger.append(sblock)
                self._einfach_indirekt(z, sblock, dieses)
                rest -= dieses
            z.zeiger.append((z.doppelt, dzeiger))
        return z

    def _verzeichnis_zuteilen(self, bloecke: "list[int]") -> _Zuteilung:
        """``BuildDirectoryAllocation``: bis zu 12 direkte, darueber ein einfach indirekter Block."""
        g = self.g
        z = _Zuteilung()
        z.direkt = list(bloecke[:N_DIREKT])
        if len(bloecke) > N_DIREKT:
            z.indirekt = self._block()
            z.meta_bloecke = 1
            zeiger = array("q", bloecke[N_DIREKT:])
            if len(zeiger) > g.bs // 8:
                raise Ufs2SchreibFehler("Verzeichnis mit mehr als %d Bloecken" % (N_DIREKT + g.bs // 8))
            z.zeiger.append((z.indirekt, zeiger))
        return z

    # -- Durchlauf (ProcessDirectoryContents) -----------------------------------------------------------------------------------
    def _verarbeiten(self, knoten: _Knoten, eintraege: "list[tuple[str, int, int]]", tiefe: int) -> None:
        g = self.g
        for kind in _sortiert(knoten):
            if self.abbruch():
                raise InterruptedError("abgebrochen")
            if self.naechster_inode >= self.max_inodes:
                raise Ufs2SchreibFehler("Abbild zu klein: keine Inodes mehr (benutzt %d, hoechstens %d)" % (
                    self.naechster_inode, self.max_inodes))
            if kind.ordner:
                ino = self.naechster_inode
                self.naechster_inode += 1
                kind.inode = ino
                unter: "list[tuple[str, int, int]]" = []
                self._verarbeiten(kind, unter, tiefe + 1)
                noetig = _verzeichnisbloecke_noetig(unter, g.bs)
                bloecke = [self._block() for _b in range(noetig)]
                _verzeichnisbloecke(ino, knoten.inode, unter, g.bs, noetig)          # prueft jetzt (Fehler sollen vor dem Schreiben kommen)
                for i, frag in enumerate(bloecke):
                    # Der Block (64 KiB, fast nur Leereintraege) entsteht erst beim Schreiben: Hunderte Verzeichnisse waeren sonst
                    # bis zum Ende des Schreibens als Bytes im Plan.
                    self.regionen.append((frag * g.fs, lambda i=i, ino=ino, par=knoten.inode, unter=unter, bs=g.bs, noetig=noetig:
                                          _verzeichnisbloecke(ino, par, unter, bs, noetig)[i]))
                zuteilung = self._verzeichnis_zuteilen(bloecke)
                for frag, zeiger in zuteilung.zeiger:
                    self.regionen.append((frag * g.fs, zeiger.tobytes()))
                groesse = noetig * g.bs
                unter_ordner = sum(1 for _n, _i, typ in unter if typ == DT_DIR)
                self._inode_ablegen(ino, _inode_bytes(
                    ordner=True, nlink=2 + unter_ordner, bs=g.bs, groesse=groesse,
                    blocks=_inode_bloecke_512(groesse, g.bs, g.fs, zuteilung.meta_bloecke), zeit=self.zeit_inodes,
                    zuteilung=zuteilung, tiefe=tiefe + 1))
                eintraege.append((kind.name, ino, DT_DIR))
                self.verzeichnisse += 1
                gruppe = ino // g.ipg
                if gruppe < len(self.verz_je_gruppe):
                    self.verz_je_gruppe[gruppe] += 1
            else:
                ino = self.naechster_inode
                self.naechster_inode += 1
                kind.inode = ino
                zuteilung = self._datei_zuteilen(kind.groesse)
                for frag, zeiger in zuteilung.zeiger:
                    self.regionen.append((frag * g.fs, zeiger.tobytes()))
                if kind.groesse > 0 and zuteilung.letzter_datenblock != 0:
                    noetig = (kind.groesse + g.bs - 1) // g.bs
                    if noetig <= N_DIREKT:
                        benutzt = (kind.groesse + g.fs - 1) // g.fs
                        belegt = noetig * g.fpb
                        if belegt - benutzt > 0:
                            im_letzten = benutzt % g.fpb
                            if im_letzten == 0:
                                im_letzten = g.fpb
                            for tf in range(im_letzten, g.fpb):
                                self.schwanz_frei.add(zuteilung.letzter_datenblock + tf)
                self._inode_ablegen(ino, _inode_bytes(
                    ordner=False, nlink=1, bs=g.bs, groesse=kind.groesse,
                    blocks=_inode_bloecke_512(kind.groesse, g.bs, g.fs, zuteilung.meta_bloecke), zeit=self.zeit_inodes,
                    zuteilung=zuteilung))
                eintraege.append((kind.name, ino, DT_REG))
                self.dateien_belegt += 1
                self.dateiliste.append((kind.rel, kind.groesse, kind.oeffner, zuteilung.daten))

    def _inode_ablegen(self, ino: int, daten: bytes) -> None:
        self.inode_tabelle[ino] = daten

    # -- Gesamtplan -----------------------------------------------------------------------------------------------------------
    def planen(self) -> Ufs2Plan:
        g = self.g
        wurzel_eintraege: "list[tuple[str, int, int]]" = []
        self.wurzel.inode = WURZEL_INODE
        self._verarbeiten(self.wurzel, wurzel_eintraege, 0)

        noetig = _verzeichnisbloecke_noetig(wurzel_eintraege, g.bs)
        bloecke = [g.wurzel_frag]
        for _b in range(1, noetig):
            bloecke.append(self._block())
        _verzeichnisbloecke(WURZEL_INODE, WURZEL_INODE, wurzel_eintraege, g.bs, noetig)
        for i, frag in enumerate(bloecke):
            self.regionen.append((frag * g.fs, lambda i=i, eintraege=wurzel_eintraege, bs=g.bs, noetig=noetig:
                                  _verzeichnisbloecke(WURZEL_INODE, WURZEL_INODE, eintraege, bs, noetig)[i]))
        zuteilung = self._verzeichnis_zuteilen(bloecke)
        for frag, zeiger in zuteilung.zeiger:
            self.regionen.append((frag * g.fs, zeiger.tobytes()))
        wurzel_groesse = noetig * g.bs
        unter_ordner = sum(1 for _n, _i, typ in wurzel_eintraege if typ == DT_DIR)
        self._inode_ablegen(WURZEL_INODE, _inode_bytes(
            ordner=True, nlink=2 + unter_ordner, bs=g.bs, groesse=wurzel_groesse,
            blocks=_inode_bloecke_512(wurzel_groesse, g.bs, g.fs, zuteilung.meta_bloecke), zeit=self.zeit_inodes,
            zuteilung=zuteilung, tiefe=0))

        zaehler = self._gruppen_schreiben()
        gesamt_bytes = g.gesamt_bytes
        dateien_bytes = sum(d[1] for d in self.dateiliste)
        return Ufs2Plan(profil=self.profil, groesse=gesamt_bytes, dateien_bytes=dateien_bytes, dateien=self.dateiliste,
                        _regionen=self.regionen, inodes_belegt=self.naechster_inode, verzeichnisse=self.verzeichnisse + 1,
                        gruppen=zaehler)

    # -- Superblock, Zylindergruppen, Inode-Tabellen (WriteFilesystem + PatchCgAndSuperblock) --------------------------
    def _superblock(self, *, frei_bloecke: int, frei_frags: int, frei_inodes: int, verzeichnisse: int) -> bytes:
        g, p = self.g, self.profil
        sb = bytearray(SUPERBLOCK_GROESSE)
        fsbtodb = _log2(g.fs // SEKTOR)
        gesamt_frags = g.gesamt_frags
        dsize = gesamt_frags - g.sblkno - g.ncg * (g.dblkno - g.sblkno) - g.cs_frags
        bmask = ~(g.bs - 1)
        fmask = ~(g.fs - 1)
        zeit = self.zeit
        optim = 1 if p.optimierung_platz else 0
        nindir = g.bs // 8
        maxfilesize = g.bs * N_DIREKT - 1
        sizepb = g.bs
        for _i in range(3):
            sizepb *= nindir
            maxfilesize += sizepb
        metaspace = ((g.fpg * p.min_free_percent // 200 // g.fpb) * g.fpb)

        def _i32(offset: int, wert: int) -> None:
            struct.pack_into("<i", sb, offset, _s32(wert))

        def _i64(offset: int, wert: int) -> None:
            struct.pack_into("<q", sb, offset, wert)

        _i32(0x008, g.sblkno)
        _i32(0x00C, g.cblkno)
        _i32(0x010, g.iblkno)
        _i32(0x014, g.dblkno)
        _i32(0x020, zeit)
        _i32(0x024, gesamt_frags)
        _i32(0x028, dsize)
        _i32(0x02C, g.ncg)
        _i32(0x030, g.bs)
        _i32(0x034, g.fs)
        _i32(0x038, g.fpb)
        _i32(0x03C, p.min_free_percent)
        _i32(0x048, bmask)
        _i32(0x04C, fmask)
        _i32(0x050, _log2(g.bs))
        _i32(0x054, _log2(g.fs))
        _i32(0x058, g.max_contig)
        _i32(0x05C, g.ipg)
        _i32(0x060, _log2(g.fpb))
        _i32(0x064, fsbtodb)
        _i32(0x068, SUPERBLOCK_GROESSE)
        _i32(0x074, nindir)
        _i32(0x078, g.bs // INODE_GROESSE)
        _i32(0x07C, g.fs // SEKTOR)
        _i32(0x080, optim)
        _i32(0x090, self.fs_id[0])
        _i32(0x094, self.fs_id[1])
        _i32(0x098, g.dblkno)
        _i32(0x09C, g.cs_groesse)
        _i32(0x0A0, g.cg_groesse)
        _i32(0x0B0, g.ncg)
        _i32(0x0B4, 1)
        _i32(0x0B8, g.ipg)
        _i32(0x0BC, g.fpg)
        _i32(0x0C0, verzeichnisse)
        _i32(0x0C4, frei_bloecke)
        _i32(0x0C8, frei_inodes)
        _i32(0x0CC, frei_frags)
        sb[0x0D1] = 1                                    # fs_clean
        sb[0x0D3] = FS_FLAGS_UPDATED
        sb[0x0D4:0x0D4 + 1] = b"/"
        name = p.volume_name.encode("ascii", "ignore")[:31]
        sb[0x2A8:0x2A8 + len(name)] = name
        _i32(0x35C, MAX_BSIZE)
        _i64(0x368, gesamt_frags)
        _i64(0x370, metaspace)
        _i64(0x3E0, SUPERBLOCK_OFFSET)
        _i64(0x3E8, SUPERBLOCK_OFFSET)
        _i64(0x3F0, verzeichnisse)
        _i64(0x3F8, frei_bloecke)
        _i64(0x400, frei_inodes)
        _i64(0x408, frei_frags)
        _i64(0x430, zeit)
        _i64(0x438, gesamt_frags)
        _i64(0x440, dsize)
        _i64(0x448, g.dblkno)
        _i32(0x4AC, p.avg_file_size)
        _i32(0x4B0, p.avg_files_per_dir)
        _i64(0x4B8, zeit)
        _i32(0x520, 0)
        _i32(0x524, g.contig_summe)
        _i32(0x528, (N_DIREKT + 3) * 8)
        _i32(0x52C, FS_44INODEFMT)
        struct.pack_into("<Q", sb, 0x530, maxfilesize)
        _i64(0x538, ~bmask)
        _i64(0x540, ~fmask)
        _i32(0x54C, -1)
        _i32(0x550, 1)
        _i32(0x55C, UFS2_MAGIC)
        return bytes(sb)

    def _gruppenkopf(self, cg: int, benutzte_inodes: int, schwanz_frei_gruppe: "list[int]") -> "tuple[bytes, int, int, int, int]":
        """Der Kopf einer Zylindergruppe im Endzustand (``SerializeCylinderGroupHeader`` und danach ``PatchCgAndSuperblock``).

        Returns:
            ``(Bytes, cs_ndir, cs_nbfree, cs_nifree, cs_nffree)``
        """
        g = self.g
        fpb, fpg, ipg = g.fpb, g.fpg, g.ipg
        gruppe_start = cg * fpg
        nutzbar = fpg
        if cg == g.ncg - 1:
            nutzbar = g.gesamt_frags - gruppe_start
        inode_bm_bytes = (ipg + 7) // 8
        frag_bm_bytes = (fpg + 7) // 8
        inode_bm_off = CG_KOPF_GRUNDGROESSE
        frag_bm_off = inode_bm_off + inode_bm_bytes
        naechster_frei_off = frag_bm_off + frag_bm_bytes
        cluster_summe_off = 0
        cluster_off = 0
        cluster_bloecke = 0
        contig = g.contig_summe
        if contig > 0:
            cluster_bloecke = _tdiv(nutzbar, fpb)
            roh_ende = frag_bm_off + (fpg + 7) // 8
            cluster_summe_off = _hochrunden(roh_ende, 4) - 4
            cluster_off = cluster_summe_off + (contig + 1) * 4
            naechster_frei_off = cluster_off + (fpg // fpb + 7) // 8
        gesamt = _hochrunden(naechster_frei_off, g.fs)
        gesamt = max(gesamt, _hochrunden(g.fs, SEKTOR))
        kopf = bytearray(_hochrunden(gesamt, SEKTOR))

        struct.pack_into("<iiii", kopf, 0x00, 0, CG_MAGIC, _s32(self.zeit), cg)
        struct.pack_into("<hh", kopf, 0x10, 0, 0)
        struct.pack_into("<i", kopf, 0x14, nutzbar)
        # Verzeichnisse und freie Zaehler folgen nach dem Bitmap-Aufbau (0x18 ..).
        struct.pack_into("<iii", kopf, 0x28, 0, 0, 0)                       # rotor, frotor, irotor
        struct.pack_into("<i", kopf, 0x54, 0)                              # cg_old_btotoff
        struct.pack_into("<i", kopf, 0x58, 0)                              # cg_old_boff
        struct.pack_into("<i", kopf, 0x5C, inode_bm_off)
        struct.pack_into("<i", kopf, 0x60, frag_bm_off)
        struct.pack_into("<i", kopf, 0x64, naechster_frei_off)
        struct.pack_into("<i", kopf, 0x68, cluster_summe_off)
        struct.pack_into("<i", kopf, 0x6C, cluster_off)
        struct.pack_into("<i", kopf, 0x70, cluster_bloecke)
        struct.pack_into("<i", kopf, 0x74, ipg)
        # cg_initediblk: anfangs min(ipg, 2 * INOPB); danach setzt der Fuellvorgang es auf die benutzten Inodes, aufgerundet auf INOPB.
        initediblk = min(ipg, 2 * g.inopb)
        if benutzte_inodes > 0:
            initediblk = min(((benutzte_inodes + g.inopb - 1) // g.inopb) * g.inopb, ipg)
        struct.pack_into("<i", kopf, 0x78, initediblk)
        struct.pack_into("<q", kopf, 0x88, self.zeit)

        # Inode-Bitmap
        inode_bm = bytearray(inode_bm_bytes)
        _bits_setzen(inode_bm, 0, benutzte_inodes)
        kopf[inode_bm_off:inode_bm_off + inode_bm_bytes] = inode_bm

        # Fragment-Bitmap (1 = frei)
        frag_bm = bytearray(frag_bm_bytes)
        if cg > 0:
            _bits_setzen(frag_bm, 0, min(g.sblkno, nutzbar))
        benutzt_daten = self.hoechststand[cg] - g.dblkno if self.hoechststand[cg] > 0 else 0
        erste_freie = g.dblkno + benutzt_daten
        _bits_setzen(frag_bm, erste_freie, nutzbar)
        if cg == 0 and g.cs_schwanz_frei > 0:
            _bits_setzen(frag_bm, g.dblkno + g.cs_frags, min(g.dblkno + g.cs_frags_blk, nutzbar))
        for absolut in schwanz_frei_gruppe:
            lokal = absolut - gruppe_start
            if 0 <= lokal < nutzbar and lokal < frag_bm_bytes * 8:
                frag_bm[lokal >> 3] |= 1 << (lokal & 7)
        kopf[frag_bm_off:frag_bm_off + frag_bm_bytes] = frag_bm

        # Zaehler aus der Bitmap
        maske = (1 << fpb) - 1
        bloecke_in_gruppe = nutzbar // fpb

        def _block_wert(blk: int) -> int:
            f = blk * fpb
            return (frag_bm[f >> 3] >> (f & 7)) & maske

        frei_bloecke = 0
        frei_rest = 0
        frsum = [0] * 8
        teilweise: "list[int]" = []
        for blk in range(bloecke_in_gruppe):
            wert = _block_wert(blk)
            if wert == maske:
                frei_bloecke += 1
            else:
                frei_rest += bin(wert).count("1")
                teilweise.append(blk)
        anfang_rest = bloecke_in_gruppe * fpb
        for f in range(anfang_rest, nutzbar):
            if _bit(frag_bm, f):
                frei_rest += 1
        for blk in teilweise:
            lauf = 0
            for ff in range(fpb):
                if _bit(frag_bm, blk * fpb + ff):
                    lauf += 1
                else:
                    if 0 < lauf < 8:
                        frsum[lauf] += 1
                    lauf = 0
            if 0 < lauf < 8:
                frsum[lauf] += 1
        lauf = 0
        for f in range(anfang_rest, nutzbar):
            if _bit(frag_bm, f):
                lauf += 1
            else:
                if 0 < lauf < 8:
                    frsum[lauf] += 1
                lauf = 0
        if 0 < lauf < 8:
            frsum[lauf] += 1

        # Cluster-Bitmap und -Summe
        if contig > 0 and cluster_bloecke > 0:
            cluster_bm = bytearray((cluster_bloecke + 7) // 8)
            for blk in range(cluster_bloecke):
                f0 = blk * fpb
                alle_frei = True
                for ff in range(fpb):
                    f = f0 + ff
                    if f >= nutzbar or f >= frag_bm_bytes * 8 or not _bit(frag_bm, f):
                        alle_frei = False
                        break
                if alle_frei:
                    cluster_bm[blk >> 3] |= 1 << (blk & 7)
            kopf[cluster_off:cluster_off + len(cluster_bm)] = cluster_bm
            summe = [0] * (contig + 1)
            lauf = 0
            for blk in range(cluster_bloecke):
                if cluster_bm[blk >> 3] & (1 << (blk & 7)):
                    lauf += 1
                elif lauf != 0:
                    summe[min(lauf, contig)] += 1
                    lauf = 0
            if lauf != 0:
                summe[min(lauf, contig)] += 1
            for i in range(1, contig + 1):
                struct.pack_into("<i", kopf, cluster_summe_off + 4 + (i - 1) * 4, summe[i])

        verz = self.verz_je_gruppe[cg] if cg < len(self.verz_je_gruppe) else 0
        frei_inodes = ipg - benutzte_inodes
        struct.pack_into("<iiii", kopf, 0x18, verz, frei_bloecke, frei_inodes, frei_rest)
        struct.pack_into("<8i", kopf, 0x34, *frsum)
        return bytes(kopf), verz, frei_bloecke, frei_inodes, frei_rest

    def _inodetabelle(self, cg: int) -> bytes:
        """Die Inode-Tabelle einer Gruppe: vorbereitete Inodes mit Zufalls-``di_gen``, darueber die belegten."""
        g = self.g
        tabelle = bytearray(g.ipg * INODE_GROESSE)
        vorbereitet = min(g.ipg, 2 * g.inopb)
        zufall = _DotNetRandom(cg + 1)
        for i in range(vorbereitet):
            if cg == 0 and i == WURZEL_INODE:
                continue                                    # die Wurzel bekommt keinen Zufallswert (und verbraucht keinen)
            gen = zufall.naechste(1, 2147483647)
            struct.pack_into("<i", tabelle, i * INODE_GROESSE + 0x50, gen)
        erster = cg * g.ipg
        for ino in self._inodes_je_gruppe.get(cg, ()):
            i = ino - erster
            tabelle[i * INODE_GROESSE:(i + 1) * INODE_GROESSE] = self.inode_tabelle[ino]
        return bytes(tabelle)

    def _gruppen_schreiben(self) -> int:
        g = self.g
        zeit = self.zeit
        schwanz_je_gruppe: "dict[int, list[int]]" = {}
        for frag in self.schwanz_frei:
            schwanz_je_gruppe.setdefault(frag // g.fpg, []).append(frag)
        belegt = self.naechster_inode
        self._inodes_je_gruppe: "dict[int, list[int]]" = {}
        for ino in self.inode_tabelle:
            self._inodes_je_gruppe.setdefault(ino // g.ipg, []).append(ino)
        cs = bytearray(g.cs_frags_blk * g.fs)
        summe_frei_bloecke = 0
        summe_frei_rest = 0
        summe_frei_inodes = 0
        for cg in range(g.ncg):
            if self.abbruch():
                raise InterruptedError("abgebrochen")
            if cg == 0:
                benutzt = min(belegt, g.ipg)
            else:
                erster = cg * g.ipg
                benutzt = min(belegt - erster, g.ipg) if belegt > erster else 0
            kopf, verz, frei_bloecke, frei_inodes, frei_rest = self._gruppenkopf(cg, benutzt, schwanz_je_gruppe.get(cg, []))
            gruppe_byte = cg * g.fpg * g.fs
            self.regionen.append((gruppe_byte + g.cblkno * g.fs, kopf.rstrip(b"\x00")))       # der Rest ist Null: die Datei ist es schon
            self.regionen.append((gruppe_byte + g.iblkno * g.fs, lambda cg=cg: self._inodetabelle(cg)))
            summe_frei_bloecke += frei_bloecke
            summe_frei_rest += frei_rest
            summe_frei_inodes += frei_inodes
            offset = cg * CSUM_GROESSE
            if offset + CSUM_GROESSE <= len(cs):
                struct.pack_into("<iiii", cs, offset, verz, frei_bloecke, frei_inodes, frei_rest)
        verzeichnisse = 1 + self.verzeichnisse
        sb = self._superblock(frei_bloecke=summe_frei_bloecke, frei_frags=summe_frei_rest, frei_inodes=summe_frei_inodes,
                              verzeichnisse=verzeichnisse)
        self.regionen.append((SUPERBLOCK_OFFSET, sb))
        wiederherstellung = bytearray(SEKTOR)
        struct.pack_into("<iiiii", wiederherstellung, SEKTOR - 20, UFS2_MAGIC, g.fpg, _log2(g.fs // SEKTOR), g.sblkno, g.ncg)
        self.regionen.append((SUPERBLOCK_OFFSET - SEKTOR, bytes(wiederherstellung)))
        self.regionen.append((g.dblkno * g.fs, bytes(cs)))
        for cg in range(1, g.ncg):
            gruppe_byte = cg * g.fpg * g.fs
            nutzbar = g.fpg if cg < g.ncg - 1 else g.gesamt_frags - cg * g.fpg
            sicherung = gruppe_byte + g.sblkno * g.fs
            if sicherung + SUPERBLOCK_GROESSE <= gruppe_byte + nutzbar * g.fs:
                self.regionen.append((sicherung, sb))
        return g.ncg
