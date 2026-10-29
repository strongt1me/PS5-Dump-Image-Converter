# -*- coding: utf-8 -*-
"""Ein UFS2-Abbild (``.ffpkg``) lesen - ohne Mount, ohne Administratorrechte, ohne die Datei zu laden.

Ein ``.ffpkg`` ist ein UFS2-Dateisystem (FreeBSD ``ffs``), das UFS2Tool baut. Dieser Leser liest es **nur lesend** und
per Seek: Superblock, die Inodes entlang eines Pfads, deren Verzeichnisbloecke und am Ende die gesuchte Datei - zusammen
einige hundert Kilobyte, auch bei einem Abbild von 40 GB. Gedacht fuer ``sce_sys/param.json`` und ``sce_sys/icon0.png``
(Bibliothek: verlangte Firmware, Titel, Titelbild).

Aufbau (am 29.10.2026 an einem echten ``.ffpkg`` nachgemessen: Superblock bei 0x10000, Magic ``0x19540119`` bei
Superblock+0x55C, Block- und Fragmentgroesse 64 KiB, 512 Inodes je Gruppe):

* ``struct fs`` (Auszug, little-endian): ``fs_iblkno`` +16, ``fs_old_cgoffset`` +24, ``fs_old_cgmask`` +28, ``fs_bsize`` +48,
  ``fs_fsize`` +52, ``fs_frag`` +56, ``fs_nindir`` +116, ``fs_inopb`` +120, ``fs_ipg`` +184, ``fs_fpg`` +188.
* ``struct ufs2_dinode`` (256 Byte): ``di_mode`` +0, ``di_size`` +16, ``di_db[12]`` +112, ``di_ib[3]`` +208; Blockzeiger sind
  Fragmentnummern (mal ``fs_fsize`` = Byte-Lage).
* Verzeichniseintrag: ``d_ino`` u32, ``d_reclen`` u16, ``d_type`` u8, ``d_namlen`` u8, dann der Name.

Was hier **nicht** steht: Schreiben, Verschluesselung, UFS1, Erweiterte Attribute. Ein fremder Aufbau ergibt ``Ufs2Fehler``,
nie eine geratene Antwort.
"""
from __future__ import annotations

import os
import struct
from typing import BinaryIO

#: Lage des UFS2-Superblocks (``SBLOCK_UFS2``) und seine Kennung (``FS_UFS2_MAGIC``).
SUPERBLOCK_LAGE = 0x10000
UFS2_MAGIC = 0x19540119
MAGIC_LAGE = 0x55C
WURZEL_INODE = 2
INODE_GROESSE = 256
ANZAHL_DIREKT = 12

#: Mehr liest ein Aufruf nie: ``icon0.png`` hat gemessen 5 bis 450 KB, ``param.json`` unter 100 KB.
MAX_DATEI = 8 * 1024 * 1024
#: Schutz vor Schleifen in beschaedigten Abbildern.
MAX_TIEFE = 16
MAX_EINTRAEGE_JE_ORDNER = 200_000

_S_IFMT = 0xF000
_S_IFDIR = 0x4000
_S_IFREG = 0x8000


class Ufs2Fehler(Exception):
    """Das ist kein lesbares UFS2-Abbild, oder ein Teil davon ist beschaedigt."""


class Ufs2Leser:
    """Liest Dateien aus einem UFS2-Abbild. Mit ``with`` benutzen (schliesst die Datei)."""

    def __init__(self, pfad: str) -> None:
        self._pfad = str(pfad)
        self._f: BinaryIO = open(self._pfad, "rb")
        try:
            self._groesse = os.fstat(self._f.fileno()).st_size
            self._superblock_lesen()
        except Exception:
            self._f.close()
            raise

    def __enter__(self) -> "Ufs2Leser":
        return self

    def __exit__(self, *_a: object) -> None:
        self.schliessen()

    def schliessen(self) -> None:
        try:
            self._f.close()
        except OSError:
            pass

    # --- Aufbau ----------------------------------------------------------------------------------
    def _lesen(self, stelle: int, laenge: int) -> bytes:
        if stelle < 0 or laenge < 0 or stelle + laenge > self._groesse:
            raise Ufs2Fehler("Lesestelle ausserhalb des Abbilds: %d+%d" % (stelle, laenge))
        self._f.seek(stelle)
        daten = self._f.read(laenge)
        if len(daten) != laenge:
            raise Ufs2Fehler("Abbild zu kurz an Stelle %d" % stelle)
        return daten

    def _superblock_lesen(self) -> None:
        sb = self._lesen(SUPERBLOCK_LAGE, 0x600) if self._groesse >= SUPERBLOCK_LAGE + 0x600 else b""
        if len(sb) < 0x600 or struct.unpack_from("<I", sb, MAGIC_LAGE)[0] != UFS2_MAGIC:
            raise Ufs2Fehler("Kein UFS2-Superblock bei 0x%X" % SUPERBLOCK_LAGE)
        self._iblkno = struct.unpack_from("<i", sb, 16)[0]
        self._cgoffset = struct.unpack_from("<i", sb, 24)[0]
        self._cgmask = struct.unpack_from("<i", sb, 28)[0]
        self._bsize = struct.unpack_from("<i", sb, 48)[0]
        self._fsize = struct.unpack_from("<i", sb, 52)[0]
        self._frag = struct.unpack_from("<i", sb, 56)[0]
        self._nindir = struct.unpack_from("<i", sb, 116)[0]
        self._inopb = struct.unpack_from("<I", sb, 120)[0]
        self._ipg = struct.unpack_from("<I", sb, 184)[0]
        self._fpg = struct.unpack_from("<i", sb, 188)[0]
        if (self._bsize < 4096 or self._bsize > 262144 or self._bsize & (self._bsize - 1)
                or self._fsize <= 0 or self._fsize > self._bsize or self._frag != self._bsize // self._fsize
                or self._inopb != self._bsize // INODE_GROESSE or self._ipg <= 0 or self._fpg <= 0
                or self._nindir != self._bsize // 8):
            raise Ufs2Fehler("Unplausiger UFS2-Superblock")

    # --- Inodes ----------------------------------------------------------------------------------
    def _inode(self, nummer: int) -> tuple[int, int, list[int], list[int]]:
        """``(Modus, Groesse, direkte Zeiger, indirekte Zeiger)`` des Inodes ``nummer``."""
        if nummer < WURZEL_INODE:
            raise Ufs2Fehler("Ungueltige Inode-Nummer %d" % nummer)
        gruppe, in_gruppe = divmod(nummer, self._ipg)
        cgbase = self._fpg * gruppe
        cgstart = cgbase + self._cgoffset * (gruppe & ~self._cgmask)
        block = cgstart + self._iblkno + (in_gruppe // self._inopb) * self._frag
        stelle = block * self._fsize + (in_gruppe % self._inopb) * INODE_GROESSE
        roh = self._lesen(stelle, INODE_GROESSE)
        modus = struct.unpack_from("<H", roh, 0)[0]
        groesse = struct.unpack_from("<Q", roh, 16)[0]
        direkt = list(struct.unpack_from("<12Q", roh, 112))
        indirekt = list(struct.unpack_from("<3Q", roh, 208))
        return modus, groesse, direkt, indirekt

    def _zeiger_block(self, fragment: int) -> list[int]:
        return list(struct.unpack("<%dQ" % self._nindir, self._lesen(fragment * self._fsize, self._bsize)))

    def _datenbloecke(self, groesse: int, direkt: list[int], indirekt: list[int]):
        """Die Fragmentnummern der Datenbloecke in Dateireihenfolge (0 = Loch); hoechstens so viele wie ``groesse``."""
        noetig = -(-groesse // self._bsize)
        erzeugt = 0

        def _ebene(zeiger: int, tiefe: int):
            nonlocal erzeugt
            if erzeugt >= noetig:
                return
            if tiefe == 0:
                erzeugt += 1
                yield zeiger
                return
            if zeiger == 0:
                luecke = self._nindir ** tiefe
                for _ in range(min(luecke, noetig - erzeugt)):
                    erzeugt += 1
                    yield 0
                return
            for unter in self._zeiger_block(zeiger):
                if erzeugt >= noetig:
                    return
                yield from _ebene(unter, tiefe - 1)

        for zeiger in direkt:
            if erzeugt >= noetig:
                return
            yield from _ebene(zeiger, 0)
        for tiefe, zeiger in enumerate(indirekt, start=1):
            if erzeugt >= noetig:
                return
            yield from _ebene(zeiger, tiefe)

    def _inhalt(self, nummer: int, hoechstens: int) -> bytes:
        modus, groesse, direkt, indirekt = self._inode(nummer)
        wunsch = min(groesse, hoechstens)
        teile: list[bytes] = []
        gelesen = 0
        for fragment in self._datenbloecke(wunsch, direkt, indirekt):
            laenge = min(self._bsize, wunsch - gelesen)
            teile.append(b"\0" * laenge if fragment == 0 else self._lesen(fragment * self._fsize, laenge))
            gelesen += laenge
            if gelesen >= wunsch:
                break
        return b"".join(teile)

    # --- Verzeichnisse ---------------------------------------------------------------------------
    def _eintraege(self, nummer: int) -> list[tuple[str, int, int]]:
        """``(Name, Inode, Typ)`` eines Verzeichnisses (ohne ``.`` und ``..``)."""
        modus, groesse, _d, _i = self._inode(nummer)
        if modus & _S_IFMT != _S_IFDIR:
            raise Ufs2Fehler("Inode %d ist kein Verzeichnis" % nummer)
        daten = self._inhalt(nummer, 64 * 1024 * 1024)
        ergebnis: list[tuple[str, int, int]] = []
        stelle = 0
        while stelle + 8 <= len(daten) and len(ergebnis) < MAX_EINTRAEGE_JE_ORDNER:
            ino, reclen, typ, namlen = struct.unpack_from("<IHBB", daten, stelle)
            if reclen < 8 or reclen % 4 or stelle + reclen > len(daten):
                # Blockgrenze oder Luecke: zum naechsten 512-Byte-Abschnitt (DIRBLKSIZ) springen
                stelle = (stelle // 512 + 1) * 512
                continue
            if ino != 0 and namlen and 8 + namlen <= reclen:
                name = daten[stelle + 8:stelle + 8 + namlen].decode("utf-8", "replace")
                if name not in (".", ".."):
                    ergebnis.append((name, ino, typ))
            stelle += reclen
        return ergebnis

    def _suchen(self, pfad: str) -> int:
        teile = [t for t in str(pfad).replace("\\", "/").split("/") if t]
        if len(teile) > MAX_TIEFE:
            raise Ufs2Fehler("Pfad zu tief")
        nummer = WURZEL_INODE
        for teil in teile:
            for name, ino, _typ in self._eintraege(nummer):
                if name == teil:
                    nummer = ino
                    break
            else:
                raise FileNotFoundError(pfad)
        return nummer

    # --- Oeffentlich -----------------------------------------------------------------------------
    def auflisten(self, pfad: str = "") -> list[tuple[str, bool, int]]:
        """``(Name, ist_ordner, Groesse)`` der Eintraege eines Verzeichnisses.

        Raises:
            FileNotFoundError: Pfad gibt es nicht. Ufs2Fehler: kein Verzeichnis oder beschaedigt.
        """
        ergebnis = []
        for name, ino, _typ in self._eintraege(self._suchen(pfad)):
            modus, groesse, _d, _i = self._inode(ino)
            ergebnis.append((name, modus & _S_IFMT == _S_IFDIR, int(groesse)))
        return ergebnis

    def datei_lesen(self, pfad: str, hoechstens: int = MAX_DATEI) -> bytes:
        """Der Inhalt einer Datei, hoechstens ``hoechstens`` Byte (nie mehr als :data:`MAX_DATEI`).

        Raises:
            FileNotFoundError: Pfad gibt es nicht. Ufs2Fehler: keine Datei oder beschaedigt.
        """
        nummer = self._suchen(pfad)
        modus, _g, _d, _i = self._inode(nummer)
        if modus & _S_IFMT != _S_IFREG:
            raise Ufs2Fehler("%s ist keine Datei" % pfad)
        return self._inhalt(nummer, min(int(hoechstens), MAX_DATEI))


def ist_ufs2(pfad: str) -> bool:
    """Trägt die Datei einen UFS2-Superblock an der ueblichen Stelle? (Liest 4 Byte.)"""
    try:
        with open(pfad, "rb") as datei:
            datei.seek(SUPERBLOCK_LAGE + MAGIC_LAGE)
            kennung = datei.read(4)
    except OSError:
        return False
    return len(kennung) == 4 and struct.unpack("<I", kennung)[0] == UFS2_MAGIC
