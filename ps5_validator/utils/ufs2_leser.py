# -*- coding: utf-8 -*-
"""Ein UFS2-Abbild (``.ffpkg``) nach Pfad lesen - ohne Mount, ohne Administratorrechte, ohne die Datei zu laden.

Ein ``.ffpkg`` ist ein UFS2-Dateisystem (FreeBSD ``ffs``), das UFS2Tool oder der eigene Schreiber (:mod:`ufs2_schreiber`) baut. Dieses Modul
ist der Leser fuer **einzelne** Dateien: Es sucht einen Pfad (``sce_sys/param.json``, ``sce_sys/icon0.png``) und liest ihn - fuer die
Bibliothek (verlangte Firmware, Titel, Titelbild, Einbauten). Es liest nur lesend und per Seek: Superblock, die Inodes entlang des Pfads,
deren Verzeichnisbloecke und die gesuchte Datei - zusammen einige hundert Kilobyte, auch bei einem Abbild von 40 GB.

**Die Formatkenntnis steht nicht hier**, sondern in :mod:`ufs2_dateisystem` (Superblock, Inodes, Blockzeiger, Verzeichnisse): Dasselbe
Modul liest den ganzen Baum fuer :class:`spielbaum.Ufs2Baum`. Bis zum 14.11.2026 hatte dieses Modul eine eigene Fassung davon (zwei
Parser desselben Formats mit eigenen Konstanten und leicht verschiedener Strenge); jetzt ist es eine Huelle um den einen Leser. Die
Konstanten ``SUPERBLOCK_LAGE``, ``MAGIC_LAGE``, ``UFS2_MAGIC`` und ``WURZEL_INODE`` bleiben unter ihren alten Namen erreichbar. Die
Verzeichnisse liest die Huelle nachsichtig wie bisher (``verzeichnis(..., nachsichtig=True)``: Luecken werden uebersprungen); der Baum fuer die
Umwandlung bleibt streng.

Was hier **nicht** steht: Schreiben, Verschluesselung, UFS1, Erweiterte Attribute. Ein fremder Aufbau ergibt ``Ufs2Fehler``, nie eine
geratene Antwort.
"""
from __future__ import annotations

import struct
from typing import BinaryIO

from ps5_validator.utils import ufs2_dateisystem as _dateisystem
from ps5_validator.utils.ufs2_dateisystem import (
    INODE_GROESSE,
    MAGIC_OFFSET as MAGIC_LAGE,
    SUPERBLOCK_OFFSET as SUPERBLOCK_LAGE,
    UFS2_MAGIC,
    WURZEL_INODE,
    Ufs2Fehler,
    Ufs2Inode,
)

__all__ = ["INODE_GROESSE", "MAGIC_LAGE", "MAX_DATEI", "MAX_TIEFE", "SUPERBLOCK_LAGE", "UFS2_MAGIC", "WURZEL_INODE",
           "Ufs2Fehler", "Ufs2Leser", "ist_ufs2"]

#: Mehr liest ein Aufruf nie: ``icon0.png`` hat gemessen 5 bis 450 KB, ``param.json`` unter 100 KB.
MAX_DATEI = 8 * 1024 * 1024
#: Schutz vor absurd langen Pfaden.
MAX_TIEFE = 16


class Ufs2Leser:
    """Liest Dateien nach Pfad aus einem UFS2-Abbild. Mit ``with`` benutzen (schliesst die Datei)."""

    def __init__(self, pfad: str) -> None:
        self._pfad = str(pfad)
        self._f: BinaryIO = open(self._pfad, "rb")
        try:
            self._fs = _dateisystem.Ufs2Leser(self._f)
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

    # --- Pfade -------------------------------------------------------------------------------------
    def _suchen(self, pfad: str) -> Ufs2Inode:
        teile = [t for t in str(pfad).replace("\\", "/").split("/") if t]
        if len(teile) > MAX_TIEFE:
            raise Ufs2Fehler("Pfad zu tief")
        inode = self._fs.inode(WURZEL_INODE)
        for teil in teile:
            for name, nummer, _typ in self._fs.verzeichnis(inode, nachsichtig=True):
                if name == teil:
                    inode = self._fs.inode(nummer)
                    break
            else:
                raise FileNotFoundError(pfad)
        return inode

    # --- Oeffentlich -------------------------------------------------------------------------------
    def auflisten(self, pfad: str = "") -> list[tuple[str, bool, int]]:
        """``(Name, ist_ordner, Groesse)`` der Eintraege eines Verzeichnisses.

        Raises:
            FileNotFoundError: Pfad gibt es nicht. Ufs2Fehler: kein Verzeichnis oder beschaedigt.
        """
        ergebnis = []
        for name, nummer, _typ in self._fs.verzeichnis(self._suchen(pfad), nachsichtig=True):
            kind = self._fs.inode(nummer)
            ergebnis.append((name, kind.ist_verzeichnis, int(kind.groesse)))
        return ergebnis

    def datei_lesen(self, pfad: str, hoechstens: int = MAX_DATEI) -> bytes:
        """Der Inhalt einer Datei, hoechstens ``hoechstens`` Byte (nie mehr als :data:`MAX_DATEI`).

        Raises:
            FileNotFoundError: Pfad gibt es nicht. Ufs2Fehler: keine Datei oder beschaedigt.
        """
        inode = self._suchen(pfad)
        if not inode.ist_datei:
            raise Ufs2Fehler("%s ist keine Datei" % pfad)
        wunsch = min(int(inode.groesse), max(0, int(hoechstens)), MAX_DATEI)
        if wunsch <= 0:
            return b""
        teile: list[bytes] = []
        gelesen = 0
        erzeuger = self._fs.lesen(inode, wunsch)          # Stuecke zu hoechstens ``wunsch``: gelesen wird nicht mehr als noetig
        try:
            for stueck in erzeuger:
                teile.append(stueck)
                gelesen += len(stueck)
                if gelesen >= wunsch:
                    break
        finally:
            erzeuger.close()
        return b"".join(teile)[:wunsch]


def ist_ufs2(pfad: str) -> bool:
    """Trägt die Datei einen UFS2-Superblock an der ueblichen Stelle? (Liest 4 Byte.)"""
    try:
        with open(pfad, "rb") as datei:
            datei.seek(SUPERBLOCK_LAGE + MAGIC_LAGE)
            kennung = datei.read(4)
    except OSError:
        return False
    return len(kennung) == 4 and struct.unpack("<I", kennung)[0] == UFS2_MAGIC
