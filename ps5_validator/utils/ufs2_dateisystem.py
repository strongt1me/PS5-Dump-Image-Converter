# -*- coding: utf-8 -*-
"""Schreibgeschuetzter UFS2-Leser fuer ``.ffpkg`` - ohne UFS2Tool, ohne Dokan, ohne Administratorrechte (Stufe 3).

Eine ``.ffpkg`` ist ein UFS2-Dateisystem in einer Datei (``UFS2Tool newfs -O 2``). Bisher las das Programm sie nur ueber
UFS2Tool: unter Windows mit einem Dokan-Laufwerk und Administratorrechten, anderswo ueber ``extract`` - und immer als **Entpacken
in einen Ordner**. Dieses Modul liest Superblock, Inodes, Verzeichnisse und Dateiinhalt selbst und liefert die Dateien als Strom;
:class:`spielbaum.Ufs2Baum` macht daraus einen Lesebaum.

Daneben gibt es ``ufs2_leser``: ein Leser fuer **einzelne** Dateien (``sce_sys/param.json``, ``icon0.png`` fuer die Bibliothek), ueber
einen Pfad hinunter, ohne den Baum zu kennen. Dieses Modul geht durch das **ganze** Dateisystem und liest beliebig grosse Dateien als
Strom (indirekte Bloecke, Loecher); es teilt sich nur das Wissen ueber das Format.

Gelesen wird nur, was UFS2Tool ``newfs`` anlegt: UFS2 (Magic ``0x19540119``), Inodes zu 256 Bytes, 12 direkte und 3 indirekte Zeiger,
Verzeichniseintraege im ``struct direct``-Format. Aufbau nach dem Leser in ``UFS2Tool-4.1/patch/Ufs2Image.cs`` (BSD-2-Clause, SvenGDK)
und der FreeBSD-Beschreibung (``sys/ufs/ffs/fs.h``, ``dinode.h``, ``dir.h``); gemessen an echten Abbildern von UFS2Tool 4.1.

Was kein Spiel-Datei ist (Verweise, Geraete, Pipes), wird gemeldet (``baum().uebersprungen``), nicht verschwiegen. Jede Abweichung des
Abbilds (Zeiger hinter dem Ende, Zyklus im Verzeichnisbaum, abgeschnittene Datei) ist ein :class:`Ufs2Fehler`.
"""
from __future__ import annotations

import struct
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, Iterator

#: Der Superblock liegt bei 64 KiB, sein Magic bei Byte 1372 darin.
SUPERBLOCK_OFFSET = 65536
SUPERBLOCK_GROESSE = 1376
MAGIC_OFFSET = 1372
UFS2_MAGIC = 0x19540119
INODE_GROESSE = 256
WURZEL_INODE = 2
N_DIREKT = 12
N_INDIREKT = 3

S_IFMT = 0o170000
S_IFDIR = 0o040000
S_IFREG = 0o100000

#: Wie viele Inode-Bloecke der Leser zwischenspeichert (ein Block = ``bsize`` Bytes).
INODE_CACHE_BLOECKE = 64
LESE_STUECK = 4 * 1024 * 1024
MAX_TIEFE = 256


class Ufs2Fehler(ValueError):
    """Das Abbild ist kein lesbares UFS2 oder in sich widerspruechlich."""


@dataclass(frozen=True)
class Ufs2Inode:
    nummer: int
    modus: int
    groesse: int
    direkt: tuple
    indirekt: tuple

    @property
    def ist_verzeichnis(self) -> bool:
        return self.modus & S_IFMT == S_IFDIR

    @property
    def ist_datei(self) -> bool:
        return self.modus & S_IFMT == S_IFREG


@dataclass(frozen=True)
class Ufs2Eintrag:
    """Eine Datei im Abbild: Pfad (mit ``/``, ohne Wurzel), Inode-Nummer und Groesse."""

    rel: str
    inode: int
    groesse: int


@dataclass
class Ufs2Baum:
    """Das Ergebnis von :meth:`Ufs2Leser.baum`: Dateien, Verzeichnisse (auch leere) und was uebergangen wurde."""

    dateien: list[Ufs2Eintrag] = field(default_factory=list)
    ordner: list[str] = field(default_factory=list)
    uebersprungen: list[str] = field(default_factory=list)


class Ufs2Leser:
    """Liest ein UFS2-Abbild aus einer geoeffneten Datei. Nicht fadensicher: Jeder Faden braucht seine Datei und seinen Leser."""

    def __init__(self, fh: BinaryIO) -> None:
        self._fh = fh
        fh.seek(0, 2)
        self._ende = fh.tell()
        if self._ende < SUPERBLOCK_OFFSET + SUPERBLOCK_GROESSE:
            raise Ufs2Fehler("Datei zu klein fuer ein UFS2-Abbild (%d Bytes)" % self._ende)
        fh.seek(SUPERBLOCK_OFFSET)
        sb = fh.read(SUPERBLOCK_GROESSE)
        if len(sb) < SUPERBLOCK_GROESSE:
            raise Ufs2Fehler("Superblock abgeschnitten")
        magic = struct.unpack_from("<I", sb, MAGIC_OFFSET)[0]
        if magic != UFS2_MAGIC:
            raise Ufs2Fehler("kein UFS2-Superblock (Magic 0x%08X)" % magic)
        self.iblkno = struct.unpack_from("<i", sb, 16)[0]
        self.ncg = struct.unpack_from("<I", sb, 44)[0]
        self.bsize = struct.unpack_from("<i", sb, 48)[0]
        self.fsize = struct.unpack_from("<i", sb, 52)[0]
        self.frag = struct.unpack_from("<i", sb, 56)[0]
        self.ipg = struct.unpack_from("<I", sb, 184)[0]
        self.fpg = struct.unpack_from("<i", sb, 188)[0]
        if (self.bsize < 4096 or self.bsize > (1 << 20) or self.bsize & (self.bsize - 1)
                or self.fsize < 512 or self.fsize > self.bsize or self.fsize & (self.fsize - 1)
                or self.frag != self.bsize // self.fsize or self.ncg <= 0 or self.ipg <= 0 or self.fpg <= 0
                or self.iblkno <= 0):
            raise Ufs2Fehler("unplausible Werte im Superblock (bsize=%d fsize=%d frag=%d ncg=%d ipg=%d fpg=%d)" % (
                self.bsize, self.fsize, self.frag, self.ncg, self.ipg, self.fpg))
        self.nindir = self.bsize // 8
        self._inode_bloecke: "OrderedDict[int, bytes]" = OrderedDict()

    # -- Inodes ---------------------------------------------------------------------------------------------------------------

    def _lesen(self, offset: int, laenge: int) -> bytes:
        if offset < 0 or laenge < 0 or offset + laenge > self._ende:
            raise Ufs2Fehler("Zugriff hinter dem Ende des Abbilds (Offset %d, %d Bytes, Abbild %d)" % (offset, laenge, self._ende))
        self._fh.seek(offset)
        daten = self._fh.read(laenge)
        if len(daten) != laenge:
            raise Ufs2Fehler("Abbild abgeschnitten bei Offset %d" % offset)
        return daten

    def inode(self, nummer: int) -> Ufs2Inode:
        if nummer < 0 or nummer >= self.ncg * self.ipg:
            raise Ufs2Fehler("Inode %d ausserhalb des Dateisystems" % nummer)
        gruppe, index = divmod(nummer, self.ipg)
        offset = gruppe * self.fpg * self.fsize + self.iblkno * self.fsize + index * INODE_GROESSE
        block = offset // self.bsize
        daten = self._inode_bloecke.get(block)
        if daten is None:
            # Einen Block zugleich: Die Inodes eines Verzeichnisses liegen meist dicht beieinander.
            beginn = block * self.bsize
            daten = self._lesen(beginn, min(self.bsize, self._ende - beginn))
            self._inode_bloecke[block] = daten
            if len(self._inode_bloecke) > INODE_CACHE_BLOECKE:
                self._inode_bloecke.popitem(last=False)
        else:
            self._inode_bloecke.move_to_end(block)
        rel = offset - block * self.bsize
        blob = daten[rel:rel + INODE_GROESSE]
        if len(blob) != INODE_GROESSE:
            raise Ufs2Fehler("Inode %d liegt nicht vollstaendig im Abbild" % nummer)
        modus = struct.unpack_from("<H", blob, 0)[0]
        groesse = struct.unpack_from("<Q", blob, 16)[0]
        direkt = struct.unpack_from("<12q", blob, 112)
        indirekt = struct.unpack_from("<3q", blob, 208)
        return Ufs2Inode(nummer, modus, groesse, direkt, indirekt)

    # -- Dateiinhalt ----------------------------------------------------------------------------------------------------------

    def _zeiger(self, adresse: int, stufe: int, bedarf: int) -> Iterator[int]:
        """Die Blockzeiger unter einem Indirektblock der ``stufe`` (1 = einfach); genau ``min(bedarf, nindir**stufe)``, 0 = Loch."""
        gesamt = min(bedarf, self.nindir ** stufe)
        if adresse == 0:
            yield from (0 for _ in range(gesamt))
            return
        zeiger = struct.unpack("<%dq" % self.nindir, self._lesen(adresse * self.fsize, self.bsize))
        if stufe == 1:
            yield from zeiger[:gesamt]
            return
        je_zweig = self.nindir ** (stufe - 1)
        rest = gesamt
        for z in zeiger:
            if rest <= 0:
                return
            n = min(rest, je_zweig)
            yield from self._zeiger(z, stufe - 1, n)
            rest -= n

    def _bloecke(self, inode: Ufs2Inode) -> Iterator[int]:
        """Die Blockzeiger der Datei in Reihenfolge, einer je logischem Block (``bsize`` Bytes; der letzte kann kuerzer sein)."""
        anzahl = -(-inode.groesse // self.bsize)
        gewesen = 0
        for z in inode.direkt:
            if gewesen >= anzahl:
                return
            yield z
            gewesen += 1
        for stufe, adresse in enumerate(inode.indirekt, start=1):
            if gewesen >= anzahl:
                return
            n = min(anzahl - gewesen, self.nindir ** stufe)
            yield from self._zeiger(adresse, stufe, n)
            gewesen += n
        if gewesen < anzahl:
            raise Ufs2Fehler("Inode %d: Datei (%d Bytes) laenger als ihre Zeiger tragen" % (inode.nummer, inode.groesse))

    def lesen(self, inode: Ufs2Inode, stueck: int = LESE_STUECK) -> Iterator[bytes]:
        """Der Inhalt einer Datei in Stuecken zu hoechstens ``stueck`` Bytes; Loecher (Zeiger 0) kommen als Nullen. Die Summe ist ``groesse``."""
        if not inode.ist_datei and not inode.ist_verzeichnis:
            raise Ufs2Fehler("Inode %d ist keine Datei" % inode.nummer)
        stueck = max(self.bsize, int(stueck))
        groesse = inode.groesse
        geliefert = 0
        lauf_start = -1                       # Byte-Offset im Abbild des laufenden zusammenhaengenden Stuecks (-1 = keins)
        lauf_laenge = 0

        def leeren() -> Iterator[bytes]:
            nonlocal lauf_start, lauf_laenge, geliefert
            if lauf_start >= 0 and lauf_laenge:
                daten = self._lesen(lauf_start, lauf_laenge)
                geliefert += len(daten)
                yield daten
            lauf_start, lauf_laenge = -1, 0

        for nummer, zeiger in enumerate(self._bloecke(inode)):
            laenge = min(self.bsize, groesse - nummer * self.bsize)
            if zeiger == 0:                                    # Loch: Nullen
                yield from leeren()
                rest = laenge
                while rest > 0:
                    n = min(rest, stueck)
                    yield bytes(n)
                    geliefert += n
                    rest -= n
                continue
            offset = zeiger * self.fsize
            if lauf_start >= 0 and offset == lauf_start + lauf_laenge and lauf_laenge + laenge <= stueck:
                lauf_laenge += laenge
            else:
                yield from leeren()
                lauf_start, lauf_laenge = offset, laenge
        yield from leeren()
        if geliefert != groesse:
            raise Ufs2Fehler("Inode %d: %d von %d Bytes gelesen" % (inode.nummer, geliefert, groesse))

    # -- Verzeichnisse --------------------------------------------------------------------------------------------------------

    def verzeichnis(self, inode: Ufs2Inode) -> list[tuple[str, int, int]]:
        """Die Eintraege eines Verzeichnisses als ``(Name, Inode-Nummer, Typ)`` ohne ``.`` und ``..`` und ohne freie Plaetze."""
        if not inode.ist_verzeichnis:
            raise Ufs2Fehler("Inode %d ist kein Verzeichnis" % inode.nummer)
        daten = b"".join(self.lesen(inode))
        eintraege: list[tuple[str, int, int]] = []
        pos = 0
        while pos + 8 <= len(daten):
            ino, reclen, typ, namlen = struct.unpack_from("<IHBB", daten, pos)
            if reclen < 8 or reclen % 4 or pos + reclen > len(daten):
                raise Ufs2Fehler("Verzeichnis (Inode %d): unbrauchbare Eintragslaenge %d bei %d" % (inode.nummer, reclen, pos))
            if ino != 0:
                if namlen == 0 or 8 + namlen > reclen:
                    raise Ufs2Fehler("Verzeichnis (Inode %d): unbrauchbare Namenslaenge %d bei %d" % (inode.nummer, namlen, pos))
                name = daten[pos + 8:pos + 8 + namlen].decode("utf-8", errors="replace")
                if name not in (".", ".."):
                    eintraege.append((name, ino, typ))
            pos += reclen
        return eintraege

    def baum(self, abbruch: Callable[[], bool] = lambda: False) -> Ufs2Baum:
        """Geht vom Wurzelverzeichnis durch alle Verzeichnisse: Dateien, Verzeichnisse (auch leere), Uebergangenes."""
        ergebnis = Ufs2Baum()
        besucht = {WURZEL_INODE}
        stapel: list[tuple[int, str, int]] = [(WURZEL_INODE, "", 0)]
        while stapel:
            if abbruch():
                raise Ufs2Fehler("abgebrochen")
            nummer, rel, tiefe = stapel.pop()
            if tiefe > MAX_TIEFE:
                raise Ufs2Fehler("Verzeichnisse zu tief verschachtelt bei %s" % rel)
            for name, ino, _typ in self.verzeichnis(self.inode(nummer)):
                pfad = "%s/%s" % (rel, name) if rel else name
                kind = self.inode(ino)
                if kind.ist_verzeichnis:
                    if ino in besucht:
                        raise Ufs2Fehler("Zyklus im Verzeichnisbaum bei %s" % pfad)
                    besucht.add(ino)
                    ergebnis.ordner.append(pfad)
                    stapel.append((ino, pfad, tiefe + 1))
                elif kind.ist_datei:
                    ergebnis.dateien.append(Ufs2Eintrag(pfad, ino, kind.groesse))
                else:
                    ergebnis.uebersprungen.append(pfad)        # Verweis, Geraet, Pipe, Socket
        ergebnis.dateien.sort(key=lambda e: e.rel)
        ergebnis.ordner.sort()
        ergebnis.uebersprungen.sort()
        return ergebnis
