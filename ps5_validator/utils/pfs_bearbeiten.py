# -*- coding: utf-8 -*-
"""Dateien direkt in einem PFS-Abbild (``.ffpfs``) umbenennen, loeschen, ersetzen und hinzufuegen - ohne Entpacken und Neubau.

Gegenstueck zu :mod:`exfat_bearbeiten` und :mod:`ufs2_bearbeiten` fuer PFS (seit dem 14.11.2026). Zwei Bauformen:

* **flach** (``mkpfs pack folder --raw --no-compress``, so baut das Programm ``.ffpfs``): Die Spieldateien liegen im PFS selbst. Das
  aendert :class:`PfsAbbild`.
* **Huelle** um ein exFAT (z. B. aus ``.ffpfsc`` -> ``.ffpfs`` umgepackt): Das PFS enthaelt genau eine Datei, ein exFAT-Abbild. Dessen
  Groesse aendert sich beim Bearbeiten nie, also bleibt das PFS unberuehrt - :func:`oeffnen` gibt dafuer einen ``ExfatAbbild`` auf das
  innere Abbild zurueck (``basis``/``laenge``). Nur unkomprimiert: Ein ``.ffpfsc`` laesst sich nicht an Ort und Stelle aendern.

**Wie das flache PFS geaendert wird.** Ein unsigniertes PFS legt jede Datei am Stueck ab (``db[0]``, Rest ``-1``); die Verwaltung
besteht aus Kopf, Inode-Tabelle, Superroot (fest hinter der Inode-Tabelle), Pfadtabelle (``flat_path_table``, nach Hash sortiert, mit
``collision_resolver`` bei gleichen Hashes) und den Verzeichnissen. Die Aenderungen geschehen an einem Baum im Speicher; beim Speichern
werden **alle** Verwaltungsdaten neu erzeugt - in der Reihenfolge, die MkPFS (``build_pfs``) fuer denselben Baum naehme: Inodes neu
nummeriert (Superroot, FPT, [Kollision], uroot, Ordner und Dateien nach ``rel.lower()``), Verzeichniseintraege und Pfadtabelle Byte fuer
Byte wie ein frischer Bau. Neue Dateiinhalte kommen nur in Bloecke, die auf der Platte frei sind (Luecken oder hinten an - das Abbild
darf wachsen, ``ndblock`` waechst mit); belegte Bloecke werden nie ueberschrieben. Das Journal (:mod:`abbild_journal`) braucht deshalb
nur die Verwaltungsdaten und die alte Laenge.

Grenzen (dann :class:`PfsBearbeitenFehler`, und es bleibt entpacken -> aendern -> neu packen): signierte, verschluesselte oder 64-Bit-
Abbilder; eine volle Inode-Tabelle (sie kann nicht wachsen, ohne den Superroot zu verschieben); leere Ordner (ein flaches PFS kennt
keine - MkPFS baut sie nie); Namen ausser ASCII.
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

PFS_MAGIC = 20130315
MODE_SIGNIERT, MODE_64BIT, MODE_VERSCHLUESSELT, MODE_GROSS_KLEIN_EGAL = 0x1, 0x2, 0x4, 0x8
INODE_GROESSE = 0xA8
INODE_ORDNER, INODE_DATEI = 0x4000, 0x8000
RX_NUR = 0x001 | 0x004 | 0x008 | 0x020 | 0x040 | 0x100
FLAG_KOMPRIMIERT, FLAG_NUR_LESEN, FLAG_INTERN = 0x1, 0x10, 0x20000
DIRENT_DATEI, DIRENT_ORDNER, DIRENT_PUNKT, DIRENT_PUNKTPUNKT = 2, 3, 4, 5
EXFAT_KENNUNG = b"EXFAT   "


class PfsBearbeitenFehler(DirektFehler):
    """Das Abbild laesst sich so nicht aendern (kein PFS, signiert/verschluesselt, Name unzulaessig, Pfad fehlt, beschaedigt)."""


class PfsPlatzFehlt(PfsBearbeitenFehler, DirektPlatzFehlt):
    """Die Verwaltung des PFS ist voll (Inode-Tabelle) - das Abbild selbst waechst bei Bedarf."""


def _ceil(a: int, b: int) -> int:
    return -(-a // b)


def fpt_hash(pfad: str, gross_klein_egal: bool) -> int:
    """Der Hash der ``flat_path_table`` (wie MkPFS ``fpt_hash``): ``h = c + 31*h`` ueber den Pfad, bei Bedarf in Grossschreibung."""
    h = 0
    for c in pfad:
        h = (ord(c.upper() if gross_klein_egal else c) + 31 * h) & 0xFFFFFFFF
    return h


def dirent(ino: int, typ: int, name: str) -> bytes:
    """Ein Verzeichniseintrag: ``inode, typ, namlen, entsize``, der ASCII-Name, auf 8 gerundet (``entsize = namlen + 17``)."""
    kodiert = name.encode("ascii")
    groesse = len(kodiert) + 17
    groesse += (-groesse) % 8
    aus = struct.pack("<Iiii", ino, typ, len(kodiert), groesse) + kodiert
    return aus + bytes(groesse - len(aus))


def dirents_lesen(blob: bytes) -> "list[tuple[int, int, str]]":
    """``(inode, typ, name)`` bis zum ersten leeren Eintrag; jede Unstimmigkeit ist ein Fehler."""
    aus: "list[tuple[int, int, str]]" = []
    pos = 0
    while pos + 16 <= len(blob):
        ino, typ, namlen, groesse = struct.unpack_from("<Iiii", blob, pos)
        if ino == 0 and typ == 0 and namlen == 0 and groesse == 0:
            break
        if groesse < 17 or groesse % 8 or namlen < 0 or namlen > groesse - 16 or pos + groesse > len(blob):
            raise PfsBearbeitenFehler("Verzeichniseintrag beschaedigt bei %d" % pos)
        try:
            name = bytes(blob[pos + 16:pos + 16 + namlen]).decode("ascii")
        except UnicodeDecodeError as exc:
            raise PfsBearbeitenFehler("Verzeichniseintrag mit Nicht-ASCII-Namen bei %d" % pos) from exc
        aus.append((ino, typ, name))
        pos += groesse
    return aus


@dataclass
class _Inode:
    roh: bytearray

    @property
    def modus(self) -> int:
        return struct.unpack_from("<H", self.roh, 0)[0]

    @property
    def flags(self) -> int:
        return struct.unpack_from("<I", self.roh, 4)[0]

    @property
    def groesse(self) -> int:
        return struct.unpack_from("<q", self.roh, 0x08)[0]

    @property
    def groesse_logisch(self) -> int:
        """Die Groesse der Datei, wie sie gelesen wird (bei PFSC-Kompression steht sie im zweiten Feld)."""
        return struct.unpack_from("<q", self.roh, 0x10 if self.flags & FLAG_KOMPRIMIERT else 0x08)[0]

    @property
    def bloecke(self) -> int:
        return struct.unpack_from("<I", self.roh, 0x60)[0]

    @property
    def erster(self) -> int:
        return struct.unpack_from("<i", self.roh, 0x64)[0]

    def lage(self, erster: int, bloecke: int) -> None:
        struct.pack_into("<I", self.roh, 0x60, bloecke)
        struct.pack_into("<12i", self.roh, 0x64, erster, *([-1] * 11))

    def groessen(self, gespeichert: int, logisch: int) -> None:
        struct.pack_into("<qq", self.roh, 0x08, gespeichert, logisch)

    def zeit_jetzt(self) -> None:
        jetzt = int(time.time())
        struct.pack_into("<qqqq", self.roh, 0x18, jetzt, jetzt, jetzt, jetzt)


def _neuer_inode(modus: int, flags: int) -> _Inode:
    roh = bytearray(INODE_GROESSE)
    struct.pack_into("<HHI", roh, 0, modus, 1, flags)
    struct.pack_into("<5i", roh, 0x94, 0, 0, 0, 0, 0)
    ino = _Inode(roh)
    ino.zeit_jetzt()
    return ino


@dataclass
class _Knoten:
    name: str
    ordner: bool
    inode: _Inode
    kinder: "dict[str, _Knoten]" = field(default_factory=dict)      # Schluessel: Name in Grossschreibung
    quelle: str = ""                                                # neuer Inhalt aus dieser Datei (Pfad)
    neu_lage: "tuple[int, int] | None" = None                       # (erster Block, Bloecke) fuer den neuen Inhalt


@dataclass
class _Kopf:
    roh: bytearray
    version: int
    modus: int
    bs: int
    inode_anzahl: int
    ndblock: int
    inode_bloecke: int


def _kopf_lesen(fh: BinaryIO, basis: int = 0) -> _Kopf:
    fh.seek(basis)
    roh = bytearray(fh.read(0x400))
    if len(roh) < 0x400:
        raise PfsBearbeitenFehler("kein PFS-Abbild (zu klein)")
    version, magic = struct.unpack_from("<qq", roh, 0)
    if magic != PFS_MAGIC:
        raise PfsBearbeitenFehler("kein PFS-Abbild")
    modus = struct.unpack_from("<H", roh, 0x1C)[0]
    bs = struct.unpack_from("<I", roh, 0x20)[0]
    inode_anzahl, ndblock, inode_bloecke = struct.unpack_from("<qqq", roh, 0x30)
    if bs < 4096 or bs & (bs - 1) or inode_anzahl <= 0 or inode_bloecke <= 0 or ndblock <= 0:
        raise PfsBearbeitenFehler("unplausible Werte im PFS-Kopf")
    return _Kopf(roh, version, modus, bs, inode_anzahl, ndblock, inode_bloecke)


def _inodes_lesen(fh: BinaryIO, kopf: _Kopf, basis: int = 0) -> "list[_Inode]":
    je_block = kopf.bs // INODE_GROESSE
    if kopf.inode_anzahl > kopf.inode_bloecke * je_block:
        raise PfsBearbeitenFehler("Inode-Zahl passt nicht in die Inode-Tabelle")
    fh.seek(basis + kopf.bs)
    tabelle = fh.read(kopf.inode_bloecke * kopf.bs)
    inodes = []
    for i in range(kopf.inode_anzahl):
        off = (i // je_block) * kopf.bs + (i % je_block) * INODE_GROESSE
        inodes.append(_Inode(bytearray(tabelle[off:off + INODE_GROESSE])))
    return inodes


def _inhalt(fh: BinaryIO, kopf: _Kopf, inode: _Inode, basis: int = 0) -> bytes:
    if inode.bloecke <= 0 or inode.groesse <= 0:
        return b""
    fh.seek(basis + inode.erster * kopf.bs)
    daten = fh.read(inode.groesse)
    if len(daten) != inode.groesse:
        raise PfsBearbeitenFehler("Inhalt abgeschnitten")
    return daten


def _superroot(fh: BinaryIO, kopf: _Kopf, basis: int = 0) -> "dict[str, int]":
    fh.seek(basis + (1 + kopf.inode_bloecke) * kopf.bs)
    return {name: ino for ino, _typ, name in dirents_lesen(fh.read(kopf.bs))}


class PfsAbbild:
    """Ein flaches, unsigniertes PFS-Abbild zum Aendern in place. ``with PfsAbbild(pfad) as a: a.umbenennen(...); a.speichern()``."""

    art = "pfs"
    #: Das Abbild waechst bei Bedarf (neue Inhalte kommen hinten an); Platz fehlt nur in der Verwaltung.
    waechst = True

    def __init__(self, pfad: str) -> None:
        self.pfad = pfad
        journal_zurueckspielen(pfad)
        self._fh: BinaryIO = open(pfad, "r+b")
        try:
            self._laden()
        except BaseException:
            self._fh.close()
            raise

    def __enter__(self) -> "PfsAbbild":
        return self

    def __exit__(self, *_a: object) -> None:
        self.schliessen()

    def schliessen(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass

    # -- Aufbau ---------------------------------------------------------------------------------------------------------
    def _laden(self) -> None:
        fh = self._fh
        kopf = _kopf_lesen(fh)
        if kopf.modus & (MODE_SIGNIERT | MODE_VERSCHLUESSELT | MODE_64BIT):
            raise PfsBearbeitenFehler("nicht unterstuetzt: signiertes, verschluesseltes oder 64-Bit-PFS (Modus 0x%X)" % kopf.modus)
        self.kopf = kopf
        self.bs = kopf.bs
        self.gross_klein_egal = bool(kopf.modus & MODE_GROSS_KLEIN_EGAL)
        inodes = _inodes_lesen(fh, kopf)
        sr = _superroot(fh, kopf)
        if "flat_path_table" not in sr or "uroot" not in sr:
            raise PfsBearbeitenFehler("Superroot ohne flat_path_table oder uroot")
        self._fpt = inodes[sr["flat_path_table"]]
        self._kollision = inodes[sr["collision_resolver"]] if "collision_resolver" in sr else None
        self._superroot_inode = inodes[0]
        besucht: "set[int]" = {0, sr["flat_path_table"], sr["uroot"]}
        if "collision_resolver" in sr:
            besucht.add(sr["collision_resolver"])

        def baum(nummer: int, name: str, tiefe: int) -> _Knoten:
            inode = inodes[nummer]
            if not inode.modus & INODE_ORDNER:
                raise PfsBearbeitenFehler("Ordner-Inode %d ist kein Ordner" % nummer)
            if tiefe > 256:
                raise PfsBearbeitenFehler("Ordner zu tief verschachtelt")
            knoten = _Knoten(name, True, _Inode(bytearray(inode.roh)))
            for ino, typ, kind in dirents_lesen(_inhalt(fh, kopf, inode)):
                if kind in (".", ".."):
                    continue
                if not 0 <= ino < len(inodes) or ino in besucht:
                    raise PfsBearbeitenFehler("Inode %d mehrfach oder ausserhalb der Tabelle (%s)" % (ino, kind))
                besucht.add(ino)
                if typ == DIRENT_ORDNER:
                    k = baum(ino, kind, tiefe + 1)
                elif typ == DIRENT_DATEI:
                    if not inodes[ino].modus & INODE_DATEI:
                        raise PfsBearbeitenFehler("Datei-Inode %d ist keine Datei" % ino)
                    k = _Knoten(kind, False, _Inode(bytearray(inodes[ino].roh)))
                else:
                    raise PfsBearbeitenFehler("unbekannter Eintragstyp %d bei %s" % (typ, kind))
                if kind.upper() in knoten.kinder:
                    raise PfsBearbeitenFehler("doppelter Name %s" % kind)
                knoten.kinder[kind.upper()] = k
            return knoten

        self.wurzel = baum(sr["uroot"], "", 0)
        if len(besucht) != len(inodes):
            raise PfsBearbeitenFehler("Das Abbild hat Inodes, die nicht im Baum haengen")
        # Die Verwaltungszone: alles vor dem ersten Dateiinhalt. Dort legt MkPFS Kopf, Inode-Tabelle, Superroot, Pfadtabelle,
        # Kollisionsliste (oder einen freigehaltenen Block) und die Ordner ab - und dort legt :meth:`speichern` sie neu an, in derselben
        # Reihenfolge. Belegt auf der Platte sind die Zone und die Bereiche aller Inodes.
        zone = kopf.ndblock
        belegt: "list[tuple[int, int]]" = []
        for inode in inodes:
            if inode.bloecke > 0 and inode.erster >= 0:
                belegt.append((inode.erster, inode.erster + inode.bloecke))
                if inode.modus & INODE_DATEI and not inode.flags & FLAG_INTERN:
                    zone = min(zone, inode.erster)
        self._zone_ende = max(zone, 2 + kopf.inode_bloecke)
        belegt.append((0, self._zone_ende))
        belegt.sort()
        self._luecken: "list[tuple[int, int]]" = []                 # (erster, Anzahl) freier Bloecke auf der Platte
        pos = 0
        for anfang, ende in belegt:
            if anfang > pos:
                self._luecken.append((pos, anfang - pos))
            pos = max(pos, ende)
        if pos < kopf.ndblock:
            self._luecken.append((pos, kopf.ndblock - pos))
        self._ende = max(pos, kopf.ndblock)                          # erster Block hinter allem (dort wird angehaengt)
        self._geaendert = False
        self._fh.seek(0, 2)
        self._laenge_platte = self._fh.tell()

    # -- Bloecke --------------------------------------------------------------------------------------------------------
    def _bereich(self, anzahl: int) -> int:
        """``anzahl`` zusammenhaengende Bloecke, die auf der Platte frei sind: aus einer Luecke, sonst hinten angehaengt."""
        for i, (anfang, n) in enumerate(self._luecken):
            if n >= anzahl:
                if n == anzahl:
                    del self._luecken[i]
                else:
                    self._luecken[i] = (anfang + anzahl, n - anzahl)
                return anfang
        anfang = self._ende
        self._ende += anzahl
        return anfang

    # -- Baum -----------------------------------------------------------------------------------------------------------
    def _knoten(self, rel: str) -> _Knoten:
        k = self.wurzel
        for teil in [t for t in rel.strip("/").split("/") if t]:
            if not k.ordner or teil.upper() not in k.kinder:
                raise PfsBearbeitenFehler("Nicht gefunden: %s" % rel)
            k = k.kinder[teil.upper()]
        return k

    def _ziel(self, rel: str) -> "tuple[_Knoten, str]":
        rel = rel.strip("/")
        if not rel:
            raise PfsBearbeitenFehler("Die Wurzel laesst sich nicht aendern")
        eltern, _, name = rel.rpartition("/")
        v = self._knoten(eltern)
        if not v.ordner:
            raise PfsBearbeitenFehler("Kein Ordner: %s" % eltern)
        return v, name

    @staticmethod
    def _name_pruefen(name: str) -> None:
        try:
            abbild_bearbeiten.name_pruefen(name)
        except abbild_bearbeiten.BearbeitenFehler as exc:
            raise PfsBearbeitenFehler("Unzulaessiger Name: %r" % name) from exc
        if not name.isascii():
            raise PfsBearbeitenFehler("Ein PFS kennt nur ASCII-Namen: %r" % name)

    # -- Oeffentlich: Lesen ---------------------------------------------------------------------------------------------
    def auflisten(self, rel: str = "") -> "list[tuple[str, bool, int]]":
        k = self._knoten(rel)
        if not k.ordner:
            raise PfsBearbeitenFehler("Kein Ordner: %s" % rel)
        return [(kind.name, kind.ordner, 0 if kind.ordner else kind.inode.groesse_logisch)
                for kind in sorted(k.kinder.values(), key=lambda x: x.name.lower())]

    def freie_bytes(self) -> int:
        """Freie Luecken im Abbild. Mehr Platz entsteht von selbst: Das Abbild waechst bei Bedarf (:attr:`waechst`)."""
        return sum(n for _a, n in self._luecken) * self.bs

    # -- Oeffentlich: Aendern -------------------------------------------------------------------------------------------
    @contextlib.contextmanager
    def _transaktion(self, baum: bool = False) -> "Iterator[None]":
        """Eine Aenderung als Ganzes. Die Aenderungen pruefen erst alles und aendern den Baum zuletzt; zurueckgenommen werden muessen
        nur die vergebenen Bloecke. ``baum=True`` (beim Speichern, das Lagen und Verweiszahlen in die Inodes schreibt) sichert auch
        den Baum."""
        import copy
        stand = (copy.deepcopy(self.wurzel) if baum else None, list(self._luecken), self._ende, self._geaendert)
        try:
            yield
        except BaseException:
            if stand[0] is not None:
                self.wurzel = stand[0]
            self._luecken, self._ende, self._geaendert = stand[1], stand[2], stand[3]
            raise

    def umbenennen(self, rel: str, neuer_name: str) -> None:
        with self._transaktion():
            self._name_pruefen(neuer_name)
            v, name = self._ziel(rel)
            k = v.kinder.get(name.upper())
            if k is None:
                raise PfsBearbeitenFehler("Nicht gefunden: %s" % rel)
            vorhanden = v.kinder.get(neuer_name.upper())
            if vorhanden is not None and vorhanden is not k:
                raise PfsBearbeitenFehler("Der Name ist schon vergeben: %s" % neuer_name)
            del v.kinder[name.upper()]
            k.name = neuer_name
            v.kinder[neuer_name.upper()] = k
            self._geaendert = True

    def loeschen(self, rel: str) -> int:
        with self._transaktion():
            v, name = self._ziel(rel)
            k = v.kinder.pop(name.upper(), None)
            if k is None:
                raise PfsBearbeitenFehler("Nicht gefunden: %s" % rel)
            self._geaendert = True
            return self._groesse_im_abbild(k)

    def _groesse_im_abbild(self, k: _Knoten) -> int:
        eigen = (k.neu_lage[1] if k.neu_lage else k.inode.bloecke) * self.bs
        return eigen + sum(self._groesse_im_abbild(x) for x in k.kinder.values())

    def ordner_anlegen(self, rel: str) -> None:
        """Legt einen Ordner an. Ein flaches PFS kennt keine leeren Ordner: Beim Speichern muss etwas darin liegen."""
        with self._transaktion():
            v, name = self._ziel(rel)
            self._name_pruefen(name)
            if name.upper() in v.kinder:
                raise PfsBearbeitenFehler("Der Name ist schon vergeben: %s" % name)
            v.kinder[name.upper()] = _Knoten(name, True, _neuer_inode(INODE_ORDNER | RX_NUR, FLAG_NUR_LESEN))
            self._geaendert = True

    def hinzufuegen(self, rel: str, quelle: str) -> None:
        with self._transaktion():
            v, name = self._ziel(rel)
            self._name_pruefen(name)
            if name.upper() in v.kinder:
                raise PfsBearbeitenFehler("Der Name ist schon vergeben: %s" % name)
            k = _Knoten(name, False, _neuer_inode(INODE_DATEI | RX_NUR, FLAG_NUR_LESEN))
            self._inhalt_vormerken(k, quelle)
            v.kinder[name.upper()] = k
            self._geaendert = True

    def ersetzen(self, rel: str, quelle: str) -> None:
        """Neuer Inhalt fuer eine Datei. Er kommt in freie Bloecke (oder hinten an); der alte Platz wird erst nach dem Speichern frei."""
        with self._transaktion():
            v, name = self._ziel(rel)
            k = v.kinder.get(name.upper())
            if k is None:
                raise PfsBearbeitenFehler("Nicht gefunden: %s" % rel)
            if k.ordner:
                raise PfsBearbeitenFehler("Nur eine Datei hat Inhalt zum Ersetzen: %s" % rel)
            self._inhalt_vormerken(k, quelle)
            k.inode.zeit_jetzt()
            self._geaendert = True

    def _inhalt_vormerken(self, k: _Knoten, quelle: str) -> None:
        groesse = os.path.getsize(quelle)                              # zuerst: scheitert es, ist noch nichts geaendert
        bloecke = max(1, _ceil(groesse, self.bs))
        if k.neu_lage is not None:
            self._luecken.append(k.neu_lage)                         # in dieser Sitzung vergeben und nie geschrieben: wieder frei
            self._luecken.sort()
        k.neu_lage = (self._bereich(bloecke), bloecke)
        k.quelle = quelle
        struct.pack_into("<I", k.inode.roh, 4, k.inode.flags & ~FLAG_KOMPRIMIERT)   # der neue Inhalt ist unkomprimiert
        k.inode.groessen(groesse, groesse)

    # -- Speichern ------------------------------------------------------------------------------------------------------
    def _alle(self) -> "tuple[list[tuple[str, _Knoten]], list[tuple[str, _Knoten]]]":
        """``(Ordner, Dateien)`` als ``(rel, Knoten)`` in der Reihenfolge von MkPFS (``rel.lower()``); die Wurzel ist der erste Ordner."""
        ordner: "list[tuple[str, _Knoten]]" = []
        dateien: "list[tuple[str, _Knoten]]" = []

        def gehen(rel: str, k: _Knoten) -> None:
            ordner.append((rel, k))
            for kind in k.kinder.values():
                pfad = (rel + "/" + kind.name) if rel else kind.name
                if kind.ordner:
                    gehen(pfad, kind)
                else:
                    dateien.append((pfad, kind))
        gehen("", self.wurzel)
        ordner.sort(key=lambda e: e[0].lower())
        dateien.sort(key=lambda e: e[0].lower())
        return ordner, dateien

    def speichern(self) -> None:
        """Erzeugt alle Verwaltungsdaten neu und schreibt: Journal, neue Inhalte, Verwaltung. Ohne Aenderungen geschieht nichts."""
        if not self._geaendert:
            return
        with self._transaktion(baum=True):
            self._speichern()
        self._laden()

    def _speichern(self) -> None:
        ordner, dateien = self._alle()
        leer = [rel for rel, k in ordner if rel and not k.kinder]
        if leer:
            raise PfsBearbeitenFehler("Ein PFS kennt keine leeren Ordner: %s - bitte eine Datei hineinlegen oder den Ordner loeschen"
                                      % ", ".join(leer[:5]))
        pfade: "list[tuple[str, bool]]" = [("/" + rel, True) for rel, _k in ordner if rel] + [("/" + rel, False) for rel, _k in dateien]
        je_hash: "dict[int, list[int]]" = {}
        for i, (pfad, _o) in enumerate(pfade):
            je_hash.setdefault(fpt_hash(pfad, self.gross_klein_egal), []).append(i)
        mit_kollision = any(len(v) > 1 for v in je_hash.values())

        # Nummern wie MkPFS: Superroot 0, FPT 1, [Kollision 2], uroot, Ordner, Dateien
        nummer: "dict[int, int]" = {}
        n = 3 if mit_kollision else 2
        for _rel, k in ordner:
            nummer[id(k)] = n
            n += 1
        for _rel, k in dateien:
            nummer[id(k)] = n
            n += 1
        anzahl = n
        je_block = self.bs // INODE_GROESSE
        inode_bloecke = _ceil(anzahl, je_block)
        superroot_block = 1 + inode_bloecke
        if superroot_block + 1 > self._zone_ende:
            raise PfsPlatzFehlt("Die Inode-Tabelle kann nicht wachsen: Vor dem ersten Dateiinhalt ist Platz fuer %d Inodes, gebraucht "
                                "werden %d; bitte neu bauen" % ((self._zone_ende - 2) * je_block, anzahl))

        # Verzeichnisinhalte
        blobs: "dict[int, bytes]" = {}
        eltern: "dict[int, int]" = {id(self.wurzel): nummer[id(self.wurzel)]}
        for _rel, k in ordner:
            kinder = sorted(k.kinder.values(), key=lambda x: x.name.lower())
            for kind in kinder:
                if kind.ordner:
                    eltern[id(kind)] = nummer[id(k)]
            blob = dirent(nummer[id(k)], DIRENT_PUNKT, ".") + dirent(eltern[id(k)], DIRENT_PUNKTPUNKT, "..")
            blob += b"".join(dirent(nummer[id(x)], DIRENT_ORDNER, x.name) for x in kinder if x.ordner)
            blob += b"".join(dirent(nummer[id(x)], DIRENT_DATEI, x.name) for x in kinder if not x.ordner)
            blobs[id(k)] = blob

        # Pfadtabelle und Kollisionsliste (wie MkPFS make_fpt_and_collision_blob)
        knoten_je_pfad = [k for _r, k in ordner if _r] + [k for _r, k in dateien]
        kollision = bytearray()
        versatz: "dict[int, int]" = {}
        if mit_kollision:
            for h in sorted(je_hash):
                if len(je_hash[h]) > 1:
                    versatz[h] = len(kollision)
                    for i in je_hash[h]:
                        pfad, ist_ordner = pfade[i]
                        kollision += dirent(nummer[id(knoten_je_pfad[i])], DIRENT_ORDNER if ist_ordner else DIRENT_DATEI, pfad)
                    kollision += bytes(0x18)
        fpt = bytearray()
        for h in sorted(je_hash):
            if len(je_hash[h]) == 1:
                i = je_hash[h][0]
                wert = nummer[id(knoten_je_pfad[i])] | (0x20000000 if pfade[i][1] else 0)
            else:
                wert = 0x80000000 | versatz[h]
            fpt += struct.pack("<II", h, wert & 0xFFFFFFFF)

        # Lage der Verwaltung: in der Zone vor dem ersten Dateiinhalt der Reihe nach wie bei MkPFS (Inode-Tabelle, Superroot,
        # Pfadtabelle, Kollisionsliste oder ein freigehaltener Block, Ordner); was dort nicht mehr hineinpasst, in freie Bloecke.
        zeiger = superroot_block + 1

        def lage(inhalt: int) -> "tuple[int, int]":
            nonlocal zeiger
            brauche = max(1, _ceil(inhalt, self.bs))
            if zeiger + brauche <= self._zone_ende:
                zeiger += brauche
                return zeiger - brauche, brauche
            return self._bereich(brauche), brauche

        fpt_lage = lage(len(fpt))
        if mit_kollision:
            koll_lage = lage(len(kollision))
        else:
            zeiger += 1                                                 # MkPFS haelt hinter der Pfadtabelle einen Block frei
        ordner_lage = {id(k): lage(len(blobs[id(k)])) for _r, k in ordner}

        # Inodes neu
        tabelle = bytearray(inode_bloecke * self.bs)

        def ablegen(nr: int, inode: _Inode) -> None:
            off = (nr // je_block) * self.bs + (nr % je_block) * INODE_GROESSE
            tabelle[off:off + INODE_GROESSE] = inode.roh

        superroot_inode = _Inode(bytearray(self._superroot_inode.roh))
        superroot_inode.lage(superroot_block, 1)
        ablegen(0, superroot_inode)
        fpt_inode = _Inode(bytearray(self._fpt.roh))
        fpt_inode.groessen(len(fpt), len(fpt))
        fpt_inode.lage(*fpt_lage)
        ablegen(1, fpt_inode)
        if mit_kollision:
            koll = _Inode(bytearray(self._kollision.roh)) if self._kollision is not None else _neuer_inode(
                INODE_DATEI | RX_NUR, FLAG_INTERN | FLAG_NUR_LESEN)
            koll.groessen(len(kollision), len(kollision))
            koll.lage(*koll_lage)
            ablegen(2, koll)
        for rel, k in ordner:
            unter = sum(1 for x in k.kinder.values() if x.ordner)
            struct.pack_into("<H", k.inode.roh, 2, (3 if not rel else 2) + unter)
            erster, bloecke = ordner_lage[id(k)]
            k.inode.lage(erster, bloecke)
            k.inode.groessen(bloecke * self.bs, bloecke * self.bs)
            ablegen(nummer[id(k)], k.inode)
        for _rel, k in dateien:
            if k.neu_lage is not None:
                k.inode.lage(*k.neu_lage)
            ablegen(nummer[id(k)], k.inode)

        superroot = dirent(1, DIRENT_DATEI, "flat_path_table")
        if mit_kollision:
            superroot += dirent(2, DIRENT_DATEI, "collision_resolver")
        superroot += dirent(nummer[id(self.wurzel)], DIRENT_ORDNER, "uroot")

        kopf = bytearray(self.kopf.roh)
        ndblock = max(self.kopf.ndblock, self._ende)
        struct.pack_into("<qqq", kopf, 0x30, anzahl, ndblock, inode_bloecke)
        # Die Beschreibung der Inode-Tabelle im Kopf (``build_inode_block_sig_s64``): Groesse in Bytes (zweimal) und in Bloecken.
        struct.pack_into("<qq", kopf, 0x50 + 0x08, inode_bloecke * self.bs, inode_bloecke * self.bs)
        struct.pack_into("<I", kopf, 0x50 + 0x60, inode_bloecke)

        stellen: "list[tuple[int, bytes]]" = [(0, bytes(kopf)), (self.bs, bytes(tabelle)),
                                              (superroot_block * self.bs, superroot + bytes(self.bs - len(superroot)))]

        def bereich_bytes(erster: int, bloecke: int, inhalt: bytes) -> "tuple[int, bytes]":
            return erster * self.bs, bytes(inhalt) + bytes(bloecke * self.bs - len(inhalt))

        stellen.append(bereich_bytes(*fpt_lage, fpt))
        if mit_kollision:
            stellen.append(bereich_bytes(*koll_lage, kollision))
        for _rel, k in ordner:
            stellen.append(bereich_bytes(*ordner_lage[id(k)], blobs[id(k)]))

        neu_laenge = ndblock * self.bs
        alte: "list[tuple[int, bytes]]" = []
        for offset, neu in stellen:
            if offset < self._laenge_platte:
                self._fh.seek(offset)
                alte.append((offset, self._fh.read(min(len(neu), self._laenge_platte - offset))))
        journal_schreiben(journal_pfad(self.pfad), alte,
                          laenge_vorher=self._laenge_platte if neu_laenge > self._laenge_platte else None)
        try:
            if neu_laenge > self._laenge_platte:
                self._fh.truncate(neu_laenge)
            for _rel, k in dateien:
                if k.neu_lage is not None:
                    self._daten_schreiben(k)
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
            journal_zurueckspielen(self.pfad)
            raise
        os.remove(journal_pfad(self.pfad))

    def _daten_schreiben(self, k: _Knoten) -> None:
        erster, bloecke = k.neu_lage                                  # type: ignore[misc]
        groesse = k.inode.groesse
        rest = groesse
        self._fh.seek(erster * self.bs)
        with open(k.quelle, "rb") as q:
            while rest > 0:
                stueck = q.read(min(rest, 4 * 1024 * 1024))
                if not stueck:
                    raise PfsBearbeitenFehler("Die Quelldatei ist kuerzer geworden: %s" % k.quelle)
                self._fh.write(stueck)
                rest -= len(stueck)
        luecke = bloecke * self.bs - groesse
        if luecke:
            self._fh.write(bytes(luecke))

    # -- Pruefung -------------------------------------------------------------------------------------------------------
    def pruefen(self) -> "list[str]":
        """Die Pruefung von MkPFS (``inspect_pfs_image`` ohne Inhalte): Kopf, Ueberlappungen, Inode-Zahl, Baum, Pfadtabelle, verwaiste
        Inodes. Rueckgabe: Befunde (leer = in Ordnung). Gelesen wird die Datei (nach :meth:`speichern` also der neue Stand)."""
        from pathlib import Path

        from mkpfs import pfs  # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        self._fh.flush()
        bericht = pfs.inspect_pfs_image(Path(self.pfad), verify_payloads=False)
        return list(bericht.errors)


def ist_pfs(pfad: str) -> bool:
    try:
        with open(pfad, "rb") as fh:
            _kopf_lesen(fh)
        return True
    except (OSError, PfsBearbeitenFehler, struct.error):
        return False


def huelle_um_exfat(pfad: str) -> "tuple[int, int] | None":
    """Liegt in ``pfad`` (auch mehrfach) ein unkomprimiertes PFS um genau ein exFAT-Abbild? Dann ``(basis, laenge)`` des inneren exFAT
    in der Datei, sonst ``None``. Komprimierte, signierte oder verschluesselte Huellen geben ``None``."""
    try:
        with open(pfad, "rb") as fh:
            basis = 0
            for _ in range(4):
                kopf = _kopf_lesen(fh, basis)
                if kopf.modus & (MODE_SIGNIERT | MODE_VERSCHLUESSELT | MODE_64BIT):
                    return None
                inodes = _inodes_lesen(fh, kopf, basis)
                sr = _superroot(fh, kopf, basis)
                if "uroot" not in sr:
                    return None
                uroot = inodes[sr["uroot"]]
                fh.seek(basis + uroot.erster * kopf.bs)
                eintraege = [e for e in dirents_lesen(fh.read(uroot.groesse)) if e[2] not in (".", "..")]
                if len(eintraege) != 1 or eintraege[0][1] != DIRENT_DATEI:
                    return None
                inner = inodes[eintraege[0][0]]
                if inner.flags & FLAG_KOMPRIMIERT or inner.bloecke <= 0 or inner.groesse < 16:
                    return None
                innen_basis = basis + inner.erster * kopf.bs
                fh.seek(innen_basis)
                kennung = fh.read(16)
                if kennung[3:11] == EXFAT_KENNUNG:
                    return innen_basis, inner.groesse
                if struct.unpack_from("<q", kennung, 8)[0] != PFS_MAGIC:
                    return None
                basis = innen_basis                                    # noch eine Huelle
            return None
    except (OSError, PfsBearbeitenFehler, struct.error, IndexError):
        return None


def oeffnen(pfad: str):  # noqa: ANN201 - PfsAbbild oder ExfatAbbild
    """Der passende Editor fuer ein PFS-Abbild: um ein exFAT ein ``ExfatAbbild`` auf das innere Abbild, sonst ein :class:`PfsAbbild`."""
    from ps5_validator.utils import exfat_bearbeiten  # noqa: PLC0415
    journal_zurueckspielen(pfad)                       # vor dem Erkennen: ein halber Lauf darf die Erkennung nicht taeuschen
    innen = huelle_um_exfat(pfad)
    if innen is not None:
        editor = exfat_bearbeiten.ExfatAbbild(pfad, basis=innen[0], laenge=innen[1])
        editor.art = "pfs-exfat"
        return editor
    editor = PfsAbbild(pfad)
    kinder = list(editor.wurzel.kinder.values())
    if len(kinder) == 1 and not kinder[0].ordner and kinder[0].inode.flags & FLAG_KOMPRIMIERT:
        # Eine komprimierte Huelle (.ffpfsc): Das innere Abbild liegt in PFSC-Bloecken, die sich nicht an Ort und Stelle aendern lassen.
        editor.schliessen()
        raise PfsBearbeitenFehler("Das Abbild ist komprimiert (eine Huelle um ein inneres Abbild); direkt aendern geht nur unkomprimiert")
    return editor


__all__ = ["PfsAbbild", "PfsBearbeitenFehler", "PfsPlatzFehlt", "fpt_hash", "dirent", "dirents_lesen", "huelle_um_exfat", "ist_pfs",
           "oeffnen"]
