# -*- coding: utf-8 -*-
"""Dateien direkt in einem UFS2-Abbild (``.ffpkg``) umbenennen, loeschen, ersetzen und hinzufuegen - ohne Entpacken und Neubau.

Gegenstueck zu :mod:`exfat_bearbeiten` fuer UFS2 (seit dem 14.11.2026; Vorbild Dump Forge, "Undo-Journal"). Gleiche Regeln:

1. Jede Aenderung wird zuerst im Speicher geplant (Verzeichnisse, Inodes, Bitmaps der Zylindergruppen, Zaehler). Scheitert sie - Name
   vergeben, kein Platz -, steht alles wieder wie vorher (:meth:`Ufs2Abbild._transaktion`), und geschrieben ist nichts.
2. Beim Speichern kommt zuerst das Journal ``<Abbild>.undo`` (:mod:`abbild_journal`) mit den alten Bytes jeder Verwaltungsstelle und jedes
   Blocks, der auf der Platte belegt war und ueberschrieben wird; dann die Dateidaten, dann die Verwaltungsdaten. Ein Abbruch laesst sich so
   immer zuruecknehmen.
3. Das Abbild waechst nie. UFS2-Abbilder des Programms (UFS2Tool ``newfs -D`` und der eigene Schreiber) haben freien Platz - die
   Groessenschaetzung legt 10 % und 10 MiB drauf -, anders als die exFAT-Abbilder.

Was ein Werkzeug wie ``fsck_ufs`` prueft, haelt der Editor ein: Jeder belegte Block und jeder Inode steht in den Bitmaps der Gruppe, die
Zaehler (Gruppe, Summenfeld, Superblock), ``frsum`` und die Cluster-Bitmap samt Summe werden fuer jede beruehrte Gruppe aus der Bitmap neu
gerechnet - genau wie der Schreiber (:mod:`ufs2_schreiber`, ``_gruppenkopf``) sie anlegt. Verzeichnisse folgen ``struct direct``
(``DIRBLKSIZ`` 512, ``d_reclen`` auf 4 gerundet), neue Bloecke sind ganze Bloecke, Schwanzfragmente nur bei Dateien bis 12 Bloecke - wie
beim Schreiber. Die Ersatz-Superbloecke bleiben unberuehrt (der Kern schreibt sie auch nicht nach).

Nicht unterstuetzt (dann kommt :class:`Ufs2BearbeitenFehler`, und es bleibt der Weg entpacken -> aendern -> neu packen): Soft Updates,
Journal, Pruefsummen der Metadaten, dreifach indirekte Bloecke, Verweise/Geraete als Ziel einer Aenderung.
"""
from __future__ import annotations

import contextlib
import os
import struct
import time
from dataclasses import dataclass, field
from typing import BinaryIO, Iterator

from ps5_validator.utils import abbild_bearbeiten
from ps5_validator.utils.abbild_journal import (
    DirektFehler,
    DirektPlatzFehlt,
    journal_pfad,
    journal_schreiben,
    journal_zurueckspielen,
)
from ps5_validator.utils.ufs2_dateisystem import (
    INODE_GROESSE,
    MAGIC_OFFSET,
    N_DIREKT,
    S_IFDIR,
    S_IFMT,
    S_IFREG,
    SUPERBLOCK_OFFSET,
    UFS2_MAGIC,
    WURZEL_INODE,
)

SUPERBLOCK_GROESSE = 8192
CG_MAGIC = 0x090255
DIRBLKSIZ = 512
DT_DIR = 4
DT_REG = 8
PERM = 0o555
SEKTOR = 512
#: So viel alter Inhalt (auf der Platte belegte Bloecke, die ueberschrieben werden) darf ins Journal.
JOURNAL_DATEN_MAX = 2 * 1024 ** 3
#: fs_flags, die der Editor nicht kennt: unsauber, Soft Updates, fsck noetig, SU-Journal, gjournal, Metadaten-Pruefsummen.
_FLAGS_UNBEKANNT = 0x01 | 0x02 | 0x04 | 0x08 | 0x40 | 0x200


class Ufs2BearbeitenFehler(DirektFehler):
    """Das Abbild laesst sich so nicht aendern (kein UFS2, Name unzulaessig, Pfad fehlt, nicht unterstuetzt, beschaedigt)."""


class Ufs2PlatzFehlt(Ufs2BearbeitenFehler, DirektPlatzFehlt):
    """Nicht genug freie Bloecke oder Inodes im Abbild (es waechst nie)."""


def _dirsiz(namlen: int) -> int:
    """``DIRSIZ``: 8 Bytes Kopf, der Name samt Nullbyte, auf 4 gerundet."""
    return (8 + namlen + 1 + 3) & ~3


def _popcount(daten: "bytes | bytearray") -> int:
    return int.from_bytes(daten, "little").bit_count()


@dataclass
class _Eintrag:
    pos: int                 # Byte-Offset im Verzeichnisinhalt
    ino: int
    reclen: int
    typ: int
    name: str


@dataclass
class _Verzeichnis:
    ino: int
    rel: str
    roh: bytearray                                   # der ganze Inhalt (di_size Bytes)
    bloecke: "list[int]"                             # Fragmentadresse je logischem Block
    meta: "list[int]"                                # Zeigerbloecke (einfach indirekt)
    geaendert: "set[int]" = field(default_factory=set)   # logische Bloecke, die neu geschrieben werden


class _Plan:
    """Was beim Speichern geschrieben wird: Bloecke (Adresse -> Bytes), Dateidaten (Rueckrufe) und die Bloecke, in die sie gehen."""

    def __init__(self) -> None:
        self.bloecke: "dict[int, bytes]" = {}
        self.daten: "list[tuple[list[int], str, int]]" = []      # (Bloecke, Quelle, Groesse)


class Ufs2Abbild:
    """Ein UFS2-Abbild zum Aendern in place. ``with Ufs2Abbild(pfad) as a: a.umbenennen(...); a.speichern()``."""

    art = "ufs2"

    def __init__(self, pfad: str) -> None:
        self.pfad = pfad
        journal_zurueckspielen(pfad)                                  # ein Abbruch des letzten Laufs wird hier rueckgaengig gemacht
        self._fh: BinaryIO = open(pfad, "r+b")
        try:
            self._laden()
        except BaseException:
            self._fh.close()
            raise

    def __enter__(self) -> "Ufs2Abbild":
        return self

    def __exit__(self, *_a: object) -> None:
        self.schliessen()

    def schliessen(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass

    # -- Aufbau ---------------------------------------------------------------------------------------------------------
    def _lesen(self, offset: int, laenge: int) -> bytes:
        if offset < 0 or offset + laenge > self._ende:
            raise Ufs2BearbeitenFehler("Zugriff hinter dem Ende des Abbilds (Offset %d, %d Bytes)" % (offset, laenge))
        self._fh.seek(offset)
        daten = self._fh.read(laenge)
        if len(daten) != laenge:
            raise Ufs2BearbeitenFehler("Abbild abgeschnitten bei Offset %d" % offset)
        return daten

    def _laden(self) -> None:
        self._fh.seek(0, 2)
        self._ende = self._fh.tell()
        if self._ende < SUPERBLOCK_OFFSET + SUPERBLOCK_GROESSE:
            raise Ufs2BearbeitenFehler("kein UFS2-Abbild (zu klein)")
        sb = bytearray(self._lesen(SUPERBLOCK_OFFSET, SUPERBLOCK_GROESSE))
        if struct.unpack_from("<I", sb, MAGIC_OFFSET)[0] != UFS2_MAGIC:
            raise Ufs2BearbeitenFehler("kein UFS2-Abbild")

        def i32(o: int) -> int:
            return struct.unpack_from("<i", sb, o)[0]

        def i64(o: int) -> int:
            return struct.unpack_from("<q", sb, o)[0]

        self.sblkno, self.cblkno, self.iblkno, self.dblkno = i32(0x08), i32(0x0C), i32(0x10), i32(0x14)
        self.ncg = struct.unpack_from("<I", sb, 0x2C)[0]
        self.bs, self.fs, self.fpb = i32(0x30), i32(0x34), i32(0x38)
        self.ipg, self.fpg = struct.unpack_from("<I", sb, 0xB8)[0], i32(0xBC)
        self.cgsize, self.cssize = i32(0xA0), i32(0x9C)
        self.csaddr = i64(0x448)
        self.contig = i32(0x524)
        self.groesse_frags = i64(0x438)
        flags, metackhash = i32(0x520), i32(0x51C)
        if (self.bs < 4096 or self.bs > 65536 or self.bs & (self.bs - 1) or self.fs < 512 or self.fs & (self.fs - 1)
                or self.fpb != self.bs // self.fs or self.fpb not in (1, 2, 4, 8) or self.ncg <= 0 or self.ipg <= 0
                or self.fpg <= 0 or self.iblkno <= 0 or self.dblkno <= self.iblkno):
            raise Ufs2BearbeitenFehler("unplausible Werte im Superblock")
        if flags & _FLAGS_UNBEKANNT or metackhash:
            raise Ufs2BearbeitenFehler("nicht unterstuetzt: Soft Updates, Journal, Pruefsummen oder unsauberes Dateisystem (fs_flags 0x%X)"
                                       % flags)
        if sb[0xD1] != 1:
            raise Ufs2BearbeitenFehler("Das Dateisystem ist nicht als sauber markiert (fs_clean)")
        if self.contig < 0 or self.contig > 16:
            raise Ufs2BearbeitenFehler("unplausible Cluster-Summengroesse %d" % self.contig)
        self.nindir = self.bs // 8
        self.inopb = self.bs // INODE_GROESSE
        self.sb = sb
        self.cs = bytearray(self._lesen(self.csaddr * self.fs, self.cssize))
        self._cs_platte = bytes(self.cs)
        self._sb_platte = bytes(sb)
        self._cg: "dict[int, bytearray]" = {}                      # geladene Gruppenkoepfe (im Speicher geaendert)
        self._cg_platte: "dict[int, bytes]" = {}                   # wie sie auf der Platte stehen
        self._inodes: "dict[int, bytearray]" = {}                  # geladene Inodes
        self._inodes_platte: "dict[int, bytes]" = {}
        self._verz: "dict[int, _Verzeichnis]" = {}
        self._plan = _Plan()
        self._beruehrt: "set[int]" = set()                         # Gruppen, deren Zaehler neu gerechnet werden muessen
        self._frei_geworden: "set[int]" = set()                    # Bloecke, die in dieser Sitzung frei wurden (auf der Platte belegt)
        self._daten_bloecke: "set[int]" = set()                    # Bloecke, in die Dateidaten kommen
        wurzel = self._inode(WURZEL_INODE)
        if self._modus(wurzel) & S_IFMT != S_IFDIR:
            raise Ufs2BearbeitenFehler("Das Wurzelverzeichnis fehlt")

    # -- Gruppen --------------------------------------------------------------------------------------------------------
    def _cg_kopf(self, cg: int) -> bytearray:
        kopf = self._cg.get(cg)
        if kopf is None:
            if not 0 <= cg < self.ncg:
                raise Ufs2BearbeitenFehler("Zylindergruppe %d ausserhalb des Dateisystems" % cg)
            roh = self._lesen((cg * self.fpg + self.cblkno) * self.fs, self.cgsize)
            if struct.unpack_from("<i", roh, 4)[0] != CG_MAGIC or struct.unpack_from("<i", roh, 0x0C)[0] != cg:
                raise Ufs2BearbeitenFehler("Zylindergruppe %d beschaedigt (Magic oder Nummer)" % cg)
            kopf = bytearray(roh)
            self._cg[cg] = kopf
            self._cg_platte[cg] = roh
        return kopf

    def _cg_feld(self, kopf: "bytes | bytearray", offset: int) -> int:
        return struct.unpack_from("<i", kopf, offset)[0]

    def _frag_frei(self, frag: int, platte: bool = False) -> bool:
        cg, lokal = divmod(frag, self.fpg)
        if platte:
            self._cg_kopf(cg)
            kopf = self._cg_platte[cg]
        else:
            kopf = self._cg_kopf(cg)
        off = self._cg_feld(kopf, 0x60)
        return bool(kopf[off + (lokal >> 3)] & (1 << (lokal & 7)))

    def _frags_setzen(self, frag: int, anzahl: int, frei: bool) -> None:
        cg, lokal = divmod(frag, self.fpg)
        kopf = self._cg_kopf(cg)
        off = self._cg_feld(kopf, 0x60)
        for f in range(lokal, lokal + anzahl):
            if frei:
                kopf[off + (f >> 3)] |= 1 << (f & 7)
            else:
                kopf[off + (f >> 3)] &= ~(1 << (f & 7)) & 0xFF
        self._beruehrt.add(cg)

    def _block_belegt_auf_platte(self, frag: int) -> bool:
        return any(not self._frag_frei(frag + i, platte=True) for i in range(self.fpb))

    def _zaehler_auffrischen(self) -> None:
        """Rechnet fuer jede beruehrte Gruppe Zaehler, ``frsum`` und Cluster-Bitmap/-Summe aus der Bitmap neu (wie ``_gruppenkopf`` des
        Schreibers), dann das Summenfeld und die Summen im Superblock."""
        for cg in sorted(self._beruehrt):
            self._gruppe_neu_zaehlen(cg)
        self._beruehrt.clear()
        summe = [0, 0, 0, 0]
        for cg in range(self.ncg):
            werte = struct.unpack_from("<4i", self.cs, cg * 16)
            for i in range(4):
                summe[i] += werte[i]
        struct.pack_into("<4i", self.sb, 0x0C0, summe[0], summe[1], summe[2], summe[3])
        struct.pack_into("<4q", self.sb, 0x3F0, summe[0], summe[1], summe[2], summe[3])

    def _gruppe_neu_zaehlen(self, cg: int) -> None:
        kopf = self._cg_kopf(cg)
        fpb = self.fpb
        nutzbar = self._cg_feld(kopf, 0x14)
        frag_off = self._cg_feld(kopf, 0x60)
        frag_bm = kopf[frag_off:frag_off + (self.fpg + 7) // 8]
        maske = (1 << fpb) - 1

        def bit(f: int) -> bool:
            return bool(frag_bm[f >> 3] & (1 << (f & 7)))

        bloecke_in_gruppe = nutzbar // fpb
        frei_bloecke = 0
        frei_rest = 0
        frsum = [0] * 8
        teilweise: "list[int]" = []
        for blk in range(bloecke_in_gruppe):
            f = blk * fpb
            wert = (frag_bm[f >> 3] >> (f & 7)) & maske
            if wert == maske:
                frei_bloecke += 1
            else:
                frei_rest += bin(wert).count("1")
                if wert:
                    teilweise.append(blk)
        anfang_rest = bloecke_in_gruppe * fpb
        for f in range(anfang_rest, nutzbar):
            if bit(f):
                frei_rest += 1
        for blk in teilweise:
            lauf = 0
            for ff in range(fpb):
                if bit(blk * fpb + ff):
                    lauf += 1
                else:
                    if 0 < lauf < 8:
                        frsum[lauf] += 1
                    lauf = 0
            if 0 < lauf < 8:
                frsum[lauf] += 1
        lauf = 0
        for f in range(anfang_rest, nutzbar):
            if bit(f):
                lauf += 1
            else:
                if 0 < lauf < 8:
                    frsum[lauf] += 1
                lauf = 0
        if 0 < lauf < 8:
            frsum[lauf] += 1

        cluster_summe_off = self._cg_feld(kopf, 0x68)
        cluster_off = self._cg_feld(kopf, 0x6C)
        cluster_bloecke = self._cg_feld(kopf, 0x70)
        if self.contig > 0 and cluster_bloecke > 0:
            cluster_bm = bytearray((cluster_bloecke + 7) // 8)
            for blk in range(cluster_bloecke):
                f0 = blk * fpb
                if f0 + fpb <= nutzbar and ((frag_bm[f0 >> 3] >> (f0 & 7)) & maske) == maske:
                    cluster_bm[blk >> 3] |= 1 << (blk & 7)
            kopf[cluster_off:cluster_off + len(cluster_bm)] = cluster_bm
            summe = [0] * (self.contig + 1)
            lauf = 0
            for blk in range(cluster_bloecke):
                if cluster_bm[blk >> 3] & (1 << (blk & 7)):
                    lauf += 1
                elif lauf:
                    summe[min(lauf, self.contig)] += 1
                    lauf = 0
            if lauf:
                summe[min(lauf, self.contig)] += 1
            for i in range(1, self.contig + 1):
                struct.pack_into("<i", kopf, cluster_summe_off + 4 * i, summe[i])

        inode_off = self._cg_feld(kopf, 0x5C)
        benutzt = _popcount(kopf[inode_off:inode_off + (self.ipg + 7) // 8])
        verz = self._cg_feld(kopf, 0x18)
        frei_inodes = self.ipg - benutzt
        struct.pack_into("<iiii", kopf, 0x18, verz, frei_bloecke, frei_inodes, frei_rest)
        struct.pack_into("<8i", kopf, 0x34, *frsum)
        struct.pack_into("<iiii", self.cs, cg * 16, verz, frei_bloecke, frei_inodes, frei_rest)

    # -- Inodes ---------------------------------------------------------------------------------------------------------
    def _inode_offset(self, ino: int) -> int:
        cg, index = divmod(ino, self.ipg)
        return (cg * self.fpg + self.iblkno) * self.fs + index * INODE_GROESSE

    def _inode(self, ino: int) -> bytearray:
        if not 0 <= ino < self.ncg * self.ipg:
            raise Ufs2BearbeitenFehler("Inode %d ausserhalb des Dateisystems" % ino)
        roh = self._inodes.get(ino)
        if roh is None:
            platte = self._lesen(self._inode_offset(ino), INODE_GROESSE)
            roh = bytearray(platte)
            self._inodes[ino] = roh
            self._inodes_platte[ino] = platte
        return roh

    @staticmethod
    def _modus(roh: "bytes | bytearray") -> int:
        return struct.unpack_from("<H", roh, 0)[0]

    @staticmethod
    def _groesse(roh: "bytes | bytearray") -> int:
        return struct.unpack_from("<Q", roh, 0x10)[0]

    def _inode_belegt(self, ino: int) -> bool:
        cg, index = divmod(ino, self.ipg)
        kopf = self._cg_kopf(cg)
        off = self._cg_feld(kopf, 0x5C)
        return bool(kopf[off + (index >> 3)] & (1 << (index & 7)))

    def _inode_zuteilen(self, bevorzugt: int, ordner: bool) -> int:
        for k in range(self.ncg):
            cg = (bevorzugt + k) % self.ncg
            if struct.unpack_from("<i", self.cs, cg * 16 + 8)[0] <= 0:
                continue
            kopf = self._cg_kopf(cg)
            off = self._cg_feld(kopf, 0x5C)
            for index in range(self.ipg):
                if cg == 0 and index < 3:
                    continue                                      # 0, 1 und die Wurzel gehoeren dem System
                if not kopf[off + (index >> 3)] & (1 << (index & 7)):
                    kopf[off + (index >> 3)] |= 1 << (index & 7)
                    initediblk = self._cg_feld(kopf, 0x78)
                    if index >= initediblk:
                        # UFS2 legt Inodes erst beim Gebrauch an: Die Gruppe kennt nur die ersten ``cg_initediblk``. Wer dahinter
                        # zuteilt, muss die Grenze nachziehen (in Schritten von INOPB) und die neuen Plaetze leer schreiben.
                        neu = min(self.ipg, ((index // self.inopb) + 1) * self.inopb)
                        struct.pack_into("<i", kopf, 0x78, neu)
                        for frisch in range(initediblk, neu):
                            leer = bytearray(INODE_GROESSE)
                            struct.pack_into("<i", leer, 0x50, int.from_bytes(os.urandom(4), "little") & 0x7FFFFFFF or 1)
                            nummer = cg * self.ipg + frisch
                            self._inode(nummer)[:] = leer
                    if ordner:
                        verz = self._cg_feld(kopf, 0x18)
                        struct.pack_into("<i", kopf, 0x18, verz + 1)
                    self._beruehrt.add(cg)
                    return cg * self.ipg + index
        raise Ufs2PlatzFehlt("Keine freie Inode mehr im Abbild")

    def _inode_freigeben(self, ino: int) -> None:
        roh = self._inode(ino)
        cg, index = divmod(ino, self.ipg)
        kopf = self._cg_kopf(cg)
        if self._modus(roh) & S_IFMT == S_IFDIR:
            struct.pack_into("<i", kopf, 0x18, self._cg_feld(kopf, 0x18) - 1)
        off = self._cg_feld(kopf, 0x5C)
        kopf[off + (index >> 3)] &= ~(1 << (index & 7)) & 0xFF
        gen = struct.unpack_from("<i", roh, 0x50)[0]
        roh[:] = bytes(INODE_GROESSE)
        struct.pack_into("<i", roh, 0x50, (gen + 1) & 0x7FFFFFFF or 1)   # wie der Kern: di_gen bleibt (eins weiter)
        self._beruehrt.add(cg)

    def _neuer_inode(self, ino: int, *, ordner: bool, nlink: int, tiefe: int = 0) -> bytearray:
        roh = self._inode(ino)
        gen = struct.unpack_from("<i", roh, 0x50)[0] or (int.from_bytes(os.urandom(4), "little") & 0x7FFFFFFF or 1)
        roh[:] = bytes(INODE_GROESSE)
        jetzt = int(time.time())
        struct.pack_into("<HhIII", roh, 0, (S_IFDIR if ordner else S_IFREG) | PERM, nlink, 0, 0, self.bs)
        struct.pack_into("<qqqq", roh, 0x20, jetzt, jetzt, jetzt, jetzt)
        struct.pack_into("<i", roh, 0x50, gen)
        if ordner:
            struct.pack_into("<I", roh, 0xF0, tiefe)
        return roh

    def _nlink_aendern(self, ino: int, um: int) -> None:
        roh = self._inode(ino)
        struct.pack_into("<h", roh, 2, struct.unpack_from("<h", roh, 2)[0] + um)

    # -- Bloecke einer Datei --------------------------------------------------------------------------------------------
    def _zeiger_lesen(self, frag: int) -> "list[int]":
        roh = self._plan.bloecke.get(frag)
        if roh is None:
            roh = self._lesen(frag * self.fs, self.bs)
        return list(struct.unpack("<%dq" % self.nindir, roh))

    def _bloecke(self, roh: "bytes | bytearray") -> "tuple[list[int], list[int]]":
        """``(Datenbloecke je logischem Block, Zeigerbloecke)`` eines Inodes (0 = Loch)."""
        groesse = self._groesse(roh)
        anzahl = -(-groesse // self.bs)
        direkt = list(struct.unpack_from("<12q", roh, 0x70))
        indirekt = struct.unpack_from("<3q", roh, 0xD0)
        daten = direkt[:min(anzahl, N_DIREKT)]
        meta: "list[int]" = []
        rest = anzahl - len(daten)
        if rest > 0:
            if indirekt[0]:
                meta.append(indirekt[0])
                daten += self._zeiger_lesen(indirekt[0])[:min(rest, self.nindir)]
            else:
                daten += [0] * min(rest, self.nindir)
            rest -= min(rest, self.nindir)
        if rest > 0:
            if indirekt[1]:
                meta.append(indirekt[1])
                for zweig in self._zeiger_lesen(indirekt[1]):
                    if rest <= 0:
                        break
                    n = min(rest, self.nindir)
                    if zweig:
                        meta.append(zweig)
                        daten += self._zeiger_lesen(zweig)[:n]
                    else:
                        daten += [0] * n
                    rest -= n
            else:
                daten += [0] * min(rest, self.nindir * self.nindir)
                rest -= min(rest, self.nindir * self.nindir)
        if rest > 0:
            raise Ufs2BearbeitenFehler("nicht unterstuetzt: dreifach indirekte Bloecke")
        return daten, meta

    def _frags_im_block(self, groesse: int, lbn: int, anzahl: int) -> int:
        """Wie viele Fragmente der logische Block ``lbn`` belegt: der letzte einer Datei bis 12 Bloecke nur so viele wie noetig."""
        if anzahl <= N_DIREKT and lbn == anzahl - 1 and self.fpb > 1:
            rest = groesse - lbn * self.bs
            return -(-rest // self.fs)
        return self.fpb

    def _inhalt_freigeben(self, roh: "bytes | bytearray") -> None:
        groesse = self._groesse(roh)
        daten, meta = self._bloecke(roh)
        frei: "set[int]" = set()
        for lbn, frag in enumerate(daten):
            if frag:
                self._frags_setzen(frag, self._frags_im_block(groesse, lbn, len(daten)), True)
                frei.add(frag)
        for frag in meta:
            self._frags_setzen(frag, self.fpb, True)
            frei.add(frag)
        self._frei_geworden |= frei
        self._daten_bloecke -= frei
        for frag in frei:
            self._plan.bloecke.pop(frag, None)
        # Ein schon vorgemerkter Inhalt (dieselbe Datei zweimal ersetzt) wird nicht mehr geschrieben: Seine Bloecke sind wieder frei
        # und koennen einer anderen Datei gehoeren - der alte Rueckruf schriebe sonst an ihnen vorbei am Journal.
        self._plan.daten = [eintrag for eintrag in self._plan.daten if not frei.intersection(eintrag[0])]

    def _bloecke_zuteilen(self, anzahl: int, bevorzugt: int) -> "list[int]":
        """``anzahl`` ganze, freie Bloecke (aufsteigend gesucht ab Gruppe ``bevorzugt``). Zuerst Bloecke, die auch auf der Platte frei
        sind (nichts muss ins Journal); erst wenn die nicht reichen, Bloecke, die in dieser Sitzung frei wurden."""
        if anzahl <= 0:
            return []
        gefunden: "list[int]" = []
        schon: "set[int]" = set()
        maske = (1 << self.fpb) - 1
        for durchgang in (0, 1):
            for k in range(self.ncg):
                cg = (bevorzugt + k) % self.ncg
                if struct.unpack_from("<i", self.cs, cg * 16 + 4)[0] <= 0:
                    continue
                kopf = self._cg_kopf(cg)
                nutzbar = self._cg_feld(kopf, 0x14)
                off = self._cg_feld(kopf, 0x60)
                basis = cg * self.fpg
                for blk in range(nutzbar // self.fpb):
                    f = blk * self.fpb
                    if (kopf[off + (f >> 3)] >> (f & 7)) & maske != maske:
                        continue
                    adresse = basis + f
                    if durchgang == 0 and adresse in self._frei_geworden:
                        continue
                    if adresse in schon:
                        continue
                    schon.add(adresse)
                    gefunden.append(adresse)
                    if len(gefunden) == anzahl:
                        for a in gefunden:
                            self._frags_setzen(a, self.fpb, False)
                        return gefunden
        raise Ufs2PlatzFehlt("Nicht genug freie Bloecke im Abbild: %d gebraucht, %d frei" % (anzahl, len(gefunden)))

    def _zuteilen_fuer(self, groesse: int, bevorzugt: int) -> "tuple[list[int], list[tuple[int, list[int]]], int, int]":
        """Bloecke fuer einen Inhalt von ``groesse`` Bytes: ``(Datenbloecke, [(Zeigerblock, Zeiger)], ib[0], ib[1])``."""
        anzahl = -(-groesse // self.bs)
        hoechstens = N_DIREKT + self.nindir + self.nindir * self.nindir
        if anzahl > hoechstens:
            raise Ufs2BearbeitenFehler("Datei zu gross fuer zweifach indirekte Bloecke (%d Bytes)" % groesse)
        rest = anzahl - min(anzahl, N_DIREKT)
        meta_anzahl = 0
        if rest > 0:
            meta_anzahl += 1
            rest -= min(rest, self.nindir)
        if rest > 0:
            meta_anzahl += 1 + -(-rest // self.nindir)
        alle = self._bloecke_zuteilen(anzahl + meta_anzahl, bevorzugt)
        daten, meta = alle[:anzahl], alle[anzahl:]
        zeigerbloecke: "list[tuple[int, list[int]]]" = []
        ib0 = ib1 = 0
        rest_daten = daten[N_DIREKT:]
        if rest_daten:
            ib0 = meta.pop(0)
            zeigerbloecke.append((ib0, rest_daten[:self.nindir]))
            rest_daten = rest_daten[self.nindir:]
        if rest_daten:
            ib1 = meta.pop(0)
            zweite: "list[int]" = []
            while rest_daten:
                zweig = meta.pop(0)
                zweite.append(zweig)
                zeigerbloecke.append((zweig, rest_daten[:self.nindir]))
                rest_daten = rest_daten[self.nindir:]
            zeigerbloecke.append((ib1, zweite))
        if anzahl and anzahl <= N_DIREKT and self.fpb > 1:
            genutzt = self._frags_im_block(groesse, anzahl - 1, anzahl)
            if genutzt < self.fpb:
                self._frags_setzen(daten[-1] + genutzt, self.fpb - genutzt, True)   # Schwanzfragmente zurueck
        return daten, zeigerbloecke, ib0, ib1

    def _zeiger_eintragen(self, roh: bytearray, groesse: int, daten: "list[int]", zeigerbloecke: "list[tuple[int, list[int]]]",
                          ib0: int, ib1: int) -> None:
        struct.pack_into("<Q", roh, 0x10, groesse)
        direkt = (daten[:N_DIREKT] + [0] * N_DIREKT)[:N_DIREKT]
        struct.pack_into("<12q", roh, 0x70, *direkt)
        struct.pack_into("<3q", roh, 0xD0, ib0, ib1, 0)
        for frag, zeiger in zeigerbloecke:
            block = bytearray(self.bs)
            struct.pack_into("<%dq" % len(zeiger), block, 0, *zeiger)
            self._plan.bloecke[frag] = bytes(block)
        frags = sum(self._frags_im_block(groesse, lbn, len(daten)) for lbn in range(len(daten)))
        frags += len(zeigerbloecke) * self.fpb
        struct.pack_into("<q", roh, 0x18, frags * (self.fs // SEKTOR))

    # -- Verzeichnisse --------------------------------------------------------------------------------------------------
    def _verzeichnis_laden(self, ino: int, rel: str) -> _Verzeichnis:
        v = self._verz.get(ino)
        if v is not None:
            v.rel = rel
            return v
        roh = self._inode(ino)
        if self._modus(roh) & S_IFMT != S_IFDIR:
            raise Ufs2BearbeitenFehler("Kein Ordner: %s" % (rel or "/"))
        groesse = self._groesse(roh)
        if groesse % DIRBLKSIZ or groesse > 256 << 20:
            raise Ufs2BearbeitenFehler("Ordner %s hat eine unbrauchbare Groesse (%d)" % (rel or "/", groesse))
        daten, meta = self._bloecke(roh)
        if any(b == 0 for b in daten):
            raise Ufs2BearbeitenFehler("Ordner %s hat ein Loch" % (rel or "/"))
        inhalt = bytearray()
        for lbn, frag in enumerate(daten):
            stueck = self._plan.bloecke.get(frag)
            if stueck is None:
                stueck = self._lesen(frag * self.fs, min(self.bs, groesse - lbn * self.bs))
            inhalt += stueck[:min(self.bs, groesse - lbn * self.bs)]
        v = _Verzeichnis(ino, rel, inhalt, daten, meta)
        self._verz[ino] = v
        return v

    def _eintraege(self, v: _Verzeichnis) -> "list[_Eintrag]":
        liste: "list[_Eintrag]" = []
        pos = 0
        while pos + 8 <= len(v.roh):
            ino, reclen, typ, namlen = struct.unpack_from("<IHBB", v.roh, pos)
            if reclen < 8 or reclen % 4 or pos + reclen > len(v.roh) or (pos % DIRBLKSIZ) + reclen > DIRBLKSIZ:
                raise Ufs2BearbeitenFehler("Ordner %s beschaedigt (Eintragslaenge %d bei %d)" % (v.rel or "/", reclen, pos))
            if ino and namlen:
                name = bytes(v.roh[pos + 8:pos + 8 + namlen]).decode("ascii", "replace")
                liste.append(_Eintrag(pos, ino, reclen, typ, name))
            pos += reclen
        return liste

    def _verzeichnis(self, rel: str) -> _Verzeichnis:
        rel = rel.strip("/")
        v = self._verzeichnis_laden(WURZEL_INODE, "")
        if not rel:
            return v
        weg = ""
        for teil in rel.split("/"):
            e = self._finde(v, teil)
            if e is None or e.typ != DT_DIR:
                raise Ufs2BearbeitenFehler("Ordner nicht gefunden: %s" % rel)
            weg = (weg + "/" + e.name) if weg else e.name
            v = self._verzeichnis_laden(e.ino, weg)
        return v

    def _finde(self, v: _Verzeichnis, name: str) -> "_Eintrag | None":
        schluessel = name.upper()
        for e in self._eintraege(v):
            if e.name not in (".", "..") and e.name.upper() == schluessel:
                return e
        return None

    def _block_markieren(self, v: _Verzeichnis, pos: int, laenge: int) -> None:
        for lbn in range(pos // self.bs, (pos + max(1, laenge) - 1) // self.bs + 1):
            v.geaendert.add(lbn)

    def _eintrag_schreiben(self, v: _Verzeichnis, pos: int, ino: int, reclen: int, typ: int, name: str) -> None:
        kodiert = name.encode("ascii")
        v.roh[pos:pos + reclen] = bytes(reclen)
        struct.pack_into("<IHBB", v.roh, pos, ino, reclen, typ, len(kodiert))
        v.roh[pos + 8:pos + 8 + len(kodiert)] = kodiert
        self._block_markieren(v, pos, reclen)

    def _eintrag_entfernen(self, v: _Verzeichnis, e: _Eintrag) -> None:
        abschnitt = e.pos - e.pos % DIRBLKSIZ
        if e.pos == abschnitt:
            # Erster Eintrag eines Abschnitts: bleibt als leerer Eintrag stehen (d_ino 0, kein Name, kein Typ).
            reclen = e.reclen
            v.roh[e.pos:e.pos + reclen] = bytes(reclen)
            struct.pack_into("<IHBB", v.roh, e.pos, 0, reclen, 0, 0)
            self._block_markieren(v, e.pos, reclen)
            return
        pos = abschnitt
        vorher = -1
        while pos < e.pos:
            vorher = pos
            pos += struct.unpack_from("<H", v.roh, pos + 4)[0]
        if pos != e.pos or vorher < 0:
            raise Ufs2BearbeitenFehler("Ordner %s beschaedigt (Eintragskette)" % (v.rel or "/"))
        reclen_vorher = struct.unpack_from("<H", v.roh, vorher + 4)[0]
        struct.pack_into("<H", v.roh, vorher + 4, reclen_vorher + e.reclen)
        v.roh[e.pos:e.pos + e.reclen] = bytes(e.reclen)
        self._block_markieren(v, vorher, reclen_vorher + e.reclen)

    def _eintrag_einfuegen(self, v: _Verzeichnis, name: str, ino: int, typ: int) -> None:
        brauche = _dirsiz(len(name))
        pos = 0
        while pos + 8 <= len(v.roh):
            e_ino, reclen, _t, namlen = struct.unpack_from("<IHBB", v.roh, pos)
            if e_ino == 0 and reclen >= brauche:
                self._eintrag_schreiben(v, pos, ino, reclen, typ, name)
                return
            eigen = _dirsiz(namlen) if e_ino else 0
            if e_ino and reclen - eigen >= brauche:
                struct.pack_into("<H", v.roh, pos + 4, eigen)
                self._block_markieren(v, pos, eigen)
                self._eintrag_schreiben(v, pos + eigen, ino, reclen - eigen, typ, name)
                return
            pos += reclen
        # Kein Platz: ein ganzer Block mehr fuer den Ordner.
        roh = self._inode(v.ino)
        alt_groesse = self._groesse(roh)
        bloecke = list(v.bloecke)
        if len(bloecke) + 1 > N_DIREKT + self.nindir:
            raise Ufs2PlatzFehlt("Der Ordner %s ist zu gross" % (v.rel or "/"))
        neu = self._bloecke_zuteilen(1, v.ino // self.ipg)[0]
        bloecke.append(neu)
        zeigerbloecke: "list[tuple[int, list[int]]]" = []
        ib0 = struct.unpack_from("<q", roh, 0xD0)[0]
        if len(bloecke) > N_DIREKT:
            if not ib0:
                ib0 = self._bloecke_zuteilen(1, v.ino // self.ipg)[0]
                v.meta.append(ib0)
            zeigerbloecke.append((ib0, bloecke[N_DIREKT:]))
        v.bloecke = bloecke
        v.roh += bytes(self.bs)
        for abschnitt in range(alt_groesse, alt_groesse + self.bs, DIRBLKSIZ):
            struct.pack_into("<IHBB", v.roh, abschnitt, 0, DIRBLKSIZ, 0, 0)
        self._zeiger_eintragen(roh, alt_groesse + self.bs, bloecke, zeigerbloecke, ib0, 0)
        self._eintrag_schreiben(v, alt_groesse, ino, DIRBLKSIZ, typ, name)
        v.geaendert.add(len(bloecke) - 1)

    def _verzeichnis_planen(self, v: _Verzeichnis) -> None:
        for lbn in sorted(v.geaendert):
            if lbn < len(v.bloecke):
                self._plan.bloecke[v.bloecke[lbn]] = bytes(v.roh[lbn * self.bs:(lbn + 1) * self.bs])
        v.geaendert.clear()

    @staticmethod
    def _name_pruefen(name: str) -> None:
        try:
            abbild_bearbeiten.name_pruefen(name)
        except abbild_bearbeiten.BearbeitenFehler as exc:
            raise Ufs2BearbeitenFehler("Unzulaessiger Name: %r" % name) from exc
        if not name.isascii():
            raise Ufs2BearbeitenFehler("Nur ASCII-Namen sind moeglich: %r" % name)

    # -- Oeffentlich: Lesen ---------------------------------------------------------------------------------------------
    def auflisten(self, rel: str = "") -> "list[tuple[str, bool, int]]":
        """``(Name, ist_ordner, Groesse)`` der Eintraege eines Ordners (ohne ``.`` und ``..``)."""
        v = self._verzeichnis(rel)
        ergebnis = []
        for e in self._eintraege(v):
            if e.name in (".", ".."):
                continue
            roh = self._inode(e.ino)
            ist_ordner = self._modus(roh) & S_IFMT == S_IFDIR
            ergebnis.append((e.name, ist_ordner, 0 if ist_ordner else self._groesse(roh)))
        return ergebnis

    def freie_bytes(self) -> int:
        frei = 0
        for cg in range(self.ncg):
            _verz, bloecke, _inodes, frags = struct.unpack_from("<4i", self.cs, cg * 16)
            frei += bloecke * self.bs + frags * self.fs
        return frei

    # -- Oeffentlich: Aendern -------------------------------------------------------------------------------------------
    @contextlib.contextmanager
    def _transaktion(self) -> "Iterator[None]":
        """Eine Aenderung als Ganzes: Scheitert sie, steht alles im Speicher wieder wie vorher."""
        stand = (
            bytes(self.sb), bytes(self.cs),
            {cg: bytes(k) for cg, k in self._cg.items()}, dict(self._cg_platte),
            {i: bytes(r) for i, r in self._inodes.items()}, dict(self._inodes_platte),
            {i: (v.rel, bytes(v.roh), list(v.bloecke), list(v.meta), set(v.geaendert)) for i, v in self._verz.items()},
            dict(self._plan.bloecke), list(self._plan.daten), set(self._beruehrt), set(self._frei_geworden),
            set(self._daten_bloecke),
        )
        try:
            yield
            self._zaehler_auffrischen()
        except BaseException:
            self.sb[:] = stand[0]
            self.cs[:] = stand[1]
            self._cg = {cg: bytearray(k) for cg, k in stand[2].items()}
            self._cg_platte = stand[3]
            self._inodes = {i: bytearray(r) for i, r in stand[4].items()}
            self._inodes_platte = stand[5]
            self._verz = {i: _Verzeichnis(i, rel, bytearray(roh), bl, me, ge) for i, (rel, roh, bl, me, ge) in stand[6].items()}
            self._plan.bloecke = stand[7]
            self._plan.daten = stand[8]
            self._beruehrt, self._frei_geworden, self._daten_bloecke = stand[9], stand[10], stand[11]
            raise

    def _ziel(self, rel: str) -> "tuple[_Verzeichnis, str]":
        rel = rel.strip("/")
        if not rel:
            raise Ufs2BearbeitenFehler("Die Wurzel laesst sich nicht aendern")
        eltern, _, name = rel.rpartition("/")
        return self._verzeichnis(eltern), name

    def _holen(self, rel: str) -> "tuple[_Verzeichnis, _Eintrag]":
        v, name = self._ziel(rel)
        e = self._finde(v, name)
        if e is None:
            raise Ufs2BearbeitenFehler("Nicht gefunden: %s" % rel)
        return v, e

    def umbenennen(self, rel: str, neuer_name: str) -> None:
        """Benennt eine Datei oder einen Ordner im selben Ordner um. Inhalt und Zeitstempel bleiben."""
        with self._transaktion():
            self._name_pruefen(neuer_name)
            v, e = self._holen(rel)
            vorhanden = self._finde(v, neuer_name)
            if vorhanden is not None and vorhanden.pos != e.pos:
                raise Ufs2BearbeitenFehler("Der Name ist schon vergeben: %s" % neuer_name)
            if _dirsiz(len(neuer_name)) <= e.reclen:
                self._eintrag_schreiben(v, e.pos, e.ino, e.reclen, e.typ, neuer_name)
            else:
                self._eintrag_entfernen(v, e)
                self._eintrag_einfuegen(v, neuer_name, e.ino, e.typ)
            self._verzeichnis_planen(v)

    def loeschen(self, rel: str) -> int:
        """Loescht eine Datei oder einen Ordner samt Inhalt. Rueckgabe: die freigegebenen Bytes."""
        with self._transaktion():
            vorher = self._frei_jetzt()
            v, e = self._holen(rel)
            self._baum_loeschen(e.ino, rel.strip("/"))
            if e.typ == DT_DIR:
                self._nlink_aendern(v.ino, -1)
            self._eintrag_entfernen(v, e)
            self._verzeichnis_planen(v)
            self._zaehler_auffrischen()
            return self._frei_jetzt() - vorher

    def _frei_jetzt(self) -> int:
        self._zaehler_auffrischen()
        return self.freie_bytes()

    def _baum_loeschen(self, ino: int, rel: str) -> None:
        roh = self._inode(ino)
        if self._modus(roh) & S_IFMT == S_IFDIR:
            kind_v = self._verzeichnis_laden(ino, rel)
            for kind in self._eintraege(kind_v):
                if kind.name in (".", ".."):
                    continue
                self._baum_loeschen(kind.ino, rel + "/" + kind.name)
            self._verz.pop(ino, None)
        elif self._modus(roh) & S_IFMT != S_IFREG:
            raise Ufs2BearbeitenFehler("nicht unterstuetzt: %s ist weder Datei noch Ordner" % rel)
        nlink = struct.unpack_from("<h", roh, 2)[0]
        if self._modus(roh) & S_IFMT == S_IFREG and nlink > 1:
            self._nlink_aendern(ino, -1)                               # harter Verweis: Inhalt bleibt fuer den anderen Namen
            return
        self._inhalt_freigeben(roh)
        self._inode_freigeben(ino)

    def ordner_anlegen(self, rel: str) -> None:
        """Legt einen leeren Ordner an (er braucht einen Block und einen Inode)."""
        with self._transaktion():
            v, name = self._ziel(rel)
            self._name_pruefen(name)
            if self._finde(v, name) is not None:
                raise Ufs2BearbeitenFehler("Der Name ist schon vergeben: %s" % name)
            eltern = self._inode(v.ino)
            tiefe = struct.unpack_from("<I", eltern, 0xF0)[0] + 1
            ino = self._inode_zuteilen(v.ino // self.ipg, True)
            block = self._bloecke_zuteilen(1, ino // self.ipg)[0]
            roh = self._neuer_inode(ino, ordner=True, nlink=2, tiefe=tiefe)
            inhalt = bytearray(self.bs)
            struct.pack_into("<IHBB", inhalt, 0, ino, 12, DT_DIR, 1)
            inhalt[8:9] = b"."
            struct.pack_into("<IHBB", inhalt, 12, v.ino, DIRBLKSIZ - 12, DT_DIR, 2)
            inhalt[20:22] = b".."
            for abschnitt in range(DIRBLKSIZ, self.bs, DIRBLKSIZ):
                struct.pack_into("<IHBB", inhalt, abschnitt, 0, DIRBLKSIZ, 0, 0)
            self._plan.bloecke[block] = bytes(inhalt)
            self._zeiger_eintragen(roh, self.bs, [block], [], 0, 0)
            self._verz[ino] = _Verzeichnis(ino, rel.strip("/"), inhalt, [block], [])
            self._eintrag_einfuegen(v, name, ino, DT_DIR)
            self._nlink_aendern(v.ino, +1)
            self._verzeichnis_planen(v)

    def hinzufuegen(self, rel: str, quelle: str) -> None:
        """Legt eine Datei aus ``quelle`` (Pfad) neu an. Der Name darf noch nicht vergeben sein."""
        with self._transaktion():
            v, name = self._ziel(rel)
            self._name_pruefen(name)
            if self._finde(v, name) is not None:
                raise Ufs2BearbeitenFehler("Der Name ist schon vergeben: %s" % name)
            groesse = os.path.getsize(quelle)
            ino = self._inode_zuteilen(v.ino // self.ipg, False)
            roh = self._neuer_inode(ino, ordner=False, nlink=1)
            self._inhalt_einplanen(roh, quelle, groesse, ino // self.ipg)
            self._eintrag_einfuegen(v, name, ino, DT_REG)
            self._verzeichnis_planen(v)

    def ersetzen(self, rel: str, quelle: str) -> None:
        """Ersetzt den Inhalt einer Datei durch den von ``quelle``. Freie Bloecke gehen vor; reicht der Platz nur mit den Bloecken der
        alten Datei, landet deren Inhalt vorher im Journal."""
        with self._transaktion():
            _v, e = self._holen(rel)
            roh = self._inode(e.ino)
            if self._modus(roh) & S_IFMT != S_IFREG:
                raise Ufs2BearbeitenFehler("Nur eine Datei hat Inhalt zum Ersetzen: %s" % rel)
            groesse = os.path.getsize(quelle)
            self._inhalt_freigeben(roh)
            self._inhalt_einplanen(roh, quelle, groesse, e.ino // self.ipg)
            jetzt = int(time.time())
            struct.pack_into("<qq", roh, 0x28, jetzt, jetzt)           # mtime, ctime

    def _inhalt_einplanen(self, roh: bytearray, quelle: str, groesse: int, bevorzugt: int) -> None:
        daten, zeigerbloecke, ib0, ib1 = self._zuteilen_fuer(groesse, bevorzugt)
        self._zeiger_eintragen(roh, groesse, daten, zeigerbloecke, ib0, ib1)
        if daten:
            self._daten_bloecke.update(daten)
            self._plan.daten.append((daten, quelle, groesse))

    # -- Speichern ------------------------------------------------------------------------------------------------------
    def _stellen(self) -> "list[tuple[int, bytes]]":
        """Die geaenderten Verwaltungsstellen: Inodes, Gruppenkoepfe, Summenfeld, Superblock."""
        stellen: "list[tuple[int, bytes]]" = []
        for ino in sorted(self._inodes):
            if bytes(self._inodes[ino]) != self._inodes_platte[ino]:
                stellen.append((self._inode_offset(ino), bytes(self._inodes[ino])))
        for cg in sorted(self._cg):
            if bytes(self._cg[cg]) != self._cg_platte[cg]:
                stellen.append(((cg * self.fpg + self.cblkno) * self.fs, bytes(self._cg[cg])))
        if bytes(self.cs) != self._cs_platte:
            stellen.append((self.csaddr * self.fs, bytes(self.cs)))
        if bytes(self.sb) != self._sb_platte:
            stellen.append((SUPERBLOCK_OFFSET, bytes(self.sb)))
        return stellen

    def speichern(self) -> None:
        """Schreibt alle geplanten Aenderungen: Journal, Dateidaten, Bloecke, Verwaltungsdaten. Ohne Aenderungen geschieht nichts."""
        self._zaehler_auffrischen()
        stellen = self._stellen()
        if not stellen and not self._plan.bloecke and not self._plan.daten:
            return
        alte: "list[tuple[int, bytes]]" = []
        gesichert = 0
        zu_schreiben = set(self._plan.bloecke) | self._daten_bloecke
        for frag in sorted(zu_schreiben):
            if self._block_belegt_auf_platte(frag):                   # auf der Platte belegt: alter Inhalt ins Journal
                alte.append((frag * self.fs, self._lesen(frag * self.fs, self.bs)))
                gesichert += self.bs
        if gesichert > JOURNAL_DATEN_MAX:
            raise Ufs2PlatzFehlt("Der ueberschriebene Inhalt ist fuer das Journal zu gross (%d MiB); bitte neu bauen" % (gesichert >> 20))
        for offset, neu in stellen:
            alte.append((offset, self._lesen(offset, len(neu))))
        journal_schreiben(journal_pfad(self.pfad), alte)
        try:
            for daten, quelle, groesse in self._plan.daten:
                self._daten_schreiben(daten, quelle, groesse)
            for frag in sorted(self._plan.bloecke):
                self._fh.seek(frag * self.fs)
                self._fh.write(self._plan.bloecke[frag])
            for offset, neu in stellen:
                self._fh.seek(offset)
                self._fh.write(neu)
            self._fh.flush()
            os.fsync(self._fh.fileno())
        except BaseException:
            try:
                self._fh.flush()
            except OSError:
                pass
            journal_zurueckspielen(self.pfad)                            # ein Fehler mitten im Schreiben: sofort zurueck
            raise
        os.remove(journal_pfad(self.pfad))
        self._laden()

    def _daten_schreiben(self, daten: "list[int]", quelle: str, groesse: int) -> None:
        rest = groesse
        with open(quelle, "rb") as q:
            i = 0
            while i < len(daten):
                lauf = 1
                while i + lauf < len(daten) and daten[i + lauf] == daten[i] + lauf * self.fpb and lauf < 64:
                    lauf += 1
                stueck = q.read(min(rest, lauf * self.bs))
                if len(stueck) < min(rest, lauf * self.bs):
                    raise Ufs2BearbeitenFehler("Die Quelldatei ist kuerzer geworden: %s" % quelle)
                rest -= len(stueck)
                if len(stueck) % self.fs:
                    stueck += bytes(self.fs - len(stueck) % self.fs)   # das letzte Fragment bis zum Ende mit Nullen
                self._fh.seek(daten[i] * self.fs)
                self._fh.write(stueck)
                i += lauf

    # -- Pruefung -------------------------------------------------------------------------------------------------------
    def pruefen(self) -> "list[str]":
        """Prueft das Abbild so, wie ``fsck_ufs`` es taete: jeder Block und jeder Inode genau einmal, Bitmaps, Zaehler, Verweiszahlen,
        ``.``/``..``. Gelesen wird der Stand im Speicher (nach :meth:`speichern` also die Platte). Rueckgabe: Befunde (leer = in Ordnung)."""
        befunde: "list[str]" = []
        benutzt: "dict[int, str]" = {}
        inodes: "set[int]" = set()
        unterordner: "dict[int, int]" = {}

        def belegen(frag: int, anzahl: int, wer: str) -> None:
            for f in range(frag, frag + anzahl):
                if f in benutzt:
                    befunde.append("Fragment %d doppelt benutzt: %s und %s" % (f, benutzt[f], wer))
                benutzt[f] = wer

        def gehen(ino: int, rel: str, eltern: int) -> None:
            v = self._verzeichnis_laden(ino, rel)
            eintraege = self._eintraege(v)
            if len(eintraege) < 2 or eintraege[0].name != "." or eintraege[0].ino != ino or eintraege[1].name != ".." \
                    or eintraege[1].ino != eltern:
                befunde.append("Ordner %s: '.' oder '..' falsch" % (rel or "/"))
            unterordner[ino] = 0
            for e in eintraege[2:]:
                pfad = (rel + "/" + e.name) if rel else e.name
                if e.ino in inodes:
                    befunde.append("Inode %d mehrfach verwendet (%s)" % (e.ino, pfad))
                    continue
                inodes.add(e.ino)
                roh = self._inode(e.ino)
                modus = self._modus(roh) & S_IFMT
                if (modus == S_IFDIR) != (e.typ == DT_DIR):
                    befunde.append("Typ im Eintrag passt nicht zum Inode: %s" % pfad)
                if modus not in (S_IFDIR, S_IFREG):
                    befunde.append("Weder Datei noch Ordner (nicht geprueft): %s" % pfad)
                    continue
                daten, meta = self._bloecke(roh)
                groesse = self._groesse(roh)
                frags = 0
                for lbn, frag in enumerate(daten):
                    if frag:
                        n = self._frags_im_block(groesse, lbn, len(daten))
                        belegen(frag, n, pfad)
                        frags += n
                for frag in meta:
                    belegen(frag, self.fpb, pfad + " (Zeiger)")
                    frags += self.fpb
                if struct.unpack_from("<q", roh, 0x18)[0] != frags * (self.fs // SEKTOR):
                    befunde.append("di_blocks passt nicht: %s" % pfad)
                if modus == S_IFDIR:
                    unterordner[ino] += 1
                    gehen(e.ino, pfad, ino)

        wurzel = self._inode(WURZEL_INODE)
        inodes.add(WURZEL_INODE)
        daten, meta = self._bloecke(wurzel)
        for frag in daten:
            belegen(frag, self.fpb, "/")
        for frag in meta:
            belegen(frag, self.fpb, "/ (Zeiger)")
        gehen(WURZEL_INODE, "", WURZEL_INODE)
        for ino, n in unterordner.items():
            if struct.unpack_from("<h", self._inode(ino), 2)[0] != 2 + n:
                befunde.append("Verweiszahl des Ordners mit Inode %d passt nicht (%d Unterordner)" % (ino, n))
        verz_je_gruppe: "dict[int, int]" = {}
        for ino in list(inodes):
            if self._modus(self._inode(ino)) & S_IFMT == S_IFDIR:
                verz_je_gruppe[ino // self.ipg] = verz_je_gruppe.get(ino // self.ipg, 0) + 1
        for cg in range(self.ncg):
            kopf = self._cg_kopf(cg)
            vorher = bytes(kopf)
            cs_vorher = bytes(self.cs[cg * 16:cg * 16 + 16])
            self._gruppe_neu_zaehlen(cg)
            if bytes(kopf) != vorher or bytes(self.cs[cg * 16:cg * 16 + 16]) != cs_vorher:
                befunde.append("Zaehler der Gruppe %d passen nicht zur Bitmap" % cg)
                kopf[:] = vorher
                self.cs[cg * 16:cg * 16 + 16] = cs_vorher
            if self._cg_feld(kopf, 0x18) != verz_je_gruppe.get(cg, 0):
                befunde.append("Ordnerzahl der Gruppe %d passt nicht" % cg)
            nutzbar = self._cg_feld(kopf, 0x14)
            off = self._cg_feld(kopf, 0x60)
            for lokal in range(nutzbar):
                frag = cg * self.fpg + lokal
                frei = bool(kopf[off + (lokal >> 3)] & (1 << (lokal & 7)))
                metadaten = lokal < self.dblkno and (cg == 0 or lokal >= self.sblkno)
                cs_bereich = cg == 0 and self.csaddr <= frag < self.csaddr + -(-self.cssize // self.fs)
                if frei and frag in benutzt:
                    befunde.append("Fragment %d ist belegt (%s), steht aber als frei in der Bitmap" % (frag, benutzt[frag]))
                    break
                if not frei and frag not in benutzt and not metadaten and not cs_bereich:
                    befunde.append("Fragment %d steht als belegt in der Bitmap, gehoert aber niemandem" % frag)
                    break
            ioff = self._cg_feld(kopf, 0x5C)
            for index in range(self.ipg):
                ino = cg * self.ipg + index
                belegt = bool(kopf[ioff + (index >> 3)] & (1 << (index & 7)))
                soll = ino in inodes or (cg == 0 and index < WURZEL_INODE)
                if belegt != soll:
                    befunde.append("Inode %d: Bitmap sagt %s" % (ino, "belegt" if belegt else "frei"))
                    break
        summe = [0, 0, 0, 0]
        for cg in range(self.ncg):
            for i, w in enumerate(struct.unpack_from("<4i", self.cs, cg * 16)):
                summe[i] += w
        if list(struct.unpack_from("<4q", self.sb, 0x3F0)) != summe or list(struct.unpack_from("<4i", self.sb, 0xC0)) != summe:
            befunde.append("Summen im Superblock passen nicht zu den Gruppen")
        return befunde


def ist_ufs2(pfad: str) -> bool:
    """Ob ``pfad`` ein UFS2-Abbild ist (Magic im Superblock)."""
    try:
        with open(pfad, "rb") as fh:
            fh.seek(SUPERBLOCK_OFFSET + MAGIC_OFFSET)
            return struct.unpack("<I", fh.read(4))[0] == UFS2_MAGIC
    except (OSError, struct.error):
        return False


__all__ = ["Ufs2Abbild", "Ufs2BearbeitenFehler", "Ufs2PlatzFehlt", "ist_ufs2"]
