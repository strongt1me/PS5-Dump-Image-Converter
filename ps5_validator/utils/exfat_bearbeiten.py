# -*- coding: utf-8 -*-
"""Dateien direkt in einem exFAT-Abbild umbenennen, loeschen, ersetzen und hinzufuegen - ohne es zu entpacken und neu zu bauen.

Bis hierher ging das nur ueber "entpacken, aendern, neu packen" (``abbild_bearbeiten``). Ein Abbild von 100 GB neu zu bauen, um eine Datei
umzubenennen, ist die Zeit nicht wert. Dieses Modul schreibt in die Datei selbst - und zwar so, dass ein Abbruch nie ein halbes Abbild
hinterlaesst (Vorbild: Dump Forge, ``exfat/src/edit.rs``, "Undo-Journal"):

1. Alles wird zuerst im Speicher geplant (Verzeichniseintraege, FAT, Belegungs-Bitmap). Scheitert die Planung - Name vergeben, kein
   Platz -, ist nichts geschrieben.
2. Neue Dateidaten kommen in freie Cluster. Was dabei an alten Daten ueberschrieben wuerde (der Platz einer ersetzten Datei, den die
   neue mitbenutzt), wird vorher ins Journal gesichert.
3. Das **Journal** ``<Abbild>.undo`` enthaelt die alten Bytes jeder Stelle, die ein Schritt aendert, mit Pruefsumme; es wird zuerst
   geschrieben und auf die Platte gezwungen. Erst dann werden die Stellen geaendert, wieder auf die Platte gezwungen, und das Journal
   faellt weg. Findet das Programm beim naechsten Oeffnen ein vollstaendiges Journal, spielt es die alten Bytes zurueck - und das Abbild
   ist wieder, wie es war. Ein unvollstaendiges Journal heisst: Es wurde noch nichts geaendert.

Das Abbild waechst nie. Fehlt der Platz, gibt es :class:`PlatzFehlt` - dann bleibt der bisherige Weg (entpacken, aendern, neu packen). Die
Abbilder, die dieses Programm baut, haben keinen freien Cluster; Platz entsteht dort durch Loeschen oder Ersetzen durch eine kleinere Datei.

Nicht angefasst werden der Startbereich (Pruefsumme und Sicherungskopie), das Feld "Belegung in Prozent" und alles ausserhalb der
Verzeichnisse, der FAT, der Bitmap und der Dateidaten. Ein umbenannter Eintrag behaelt seine Zeitstempel, ein ersetzter bekommt die
Aenderungszeit neu.
"""
from __future__ import annotations

import contextlib
import os
import struct
import time
from dataclasses import dataclass, field
from typing import BinaryIO, Callable, Iterator

from ps5_validator.utils.abbild_journal import (  # noqa: F401  (die alten Namen dieses Moduls bleiben gueltig)
    _ENDE,
    _MAGIC,
    JOURNAL_ENDUNG,
    DirektFehler,
    DirektPlatzFehlt,
    journal_lesen,
    journal_pfad,
    journal_schreiben,
    journal_zurueckspielen,
)

_FAT_MAX = 256 * 1024 * 1024            # eine groessere FAT wird nicht ganz in den Speicher geladen
_JOURNAL_DATEN_MAX = 2 * 1024 ** 3      # so viel alter Dateiinhalt darf ins Journal (sonst: neu bauen)
_FAT_FREI, _FAT_ENDE = 0, 0xFFFFFFFF
_ENTRY_BITMAP, _ENTRY_UPCASE, _ENTRY_FILE, _ENTRY_STREAM, _ENTRY_NAME = 0x81, 0x82, 0x85, 0xC0, 0xC1
_ATTR_DIRECTORY, _ATTR_ARCHIVE = 0x10, 0x20
_FLAG_ALLOC, _FLAG_NO_FAT_CHAIN = 0x01, 0x02
_NAME_PRO_EINTRAG = 15
_VERBOTEN = '\\/:*?"<>|'
_BLOCK = 4096


class ExfatBearbeitenFehler(DirektFehler):
    """Das Abbild laesst sich so nicht aendern (kein exFAT, Name unzulaessig, Pfad fehlt, beschaedigt)."""


class PlatzFehlt(ExfatBearbeitenFehler, DirektPlatzFehlt):
    """Im Abbild ist nicht genug Platz: Es waechst nie - dann bleibt nur, es neu zu bauen."""


# ---------------------------------------------------------------------------------------------------------------------------
# Journal: seit dem 14.11.2026 in ``abbild_journal`` (gemeinsam mit UFS2 und PFS); die alten Namen bleiben.
# ---------------------------------------------------------------------------------------------------------------------------
_journal_schreiben = journal_schreiben
_journal_lesen = journal_lesen


class _Fenster:
    """Ein Fenster in eine groessere Datei: das innere exFAT-Abbild einer unkomprimierten PFS-Huelle, ``laenge`` Bytes ab ``basis``.

    Der Editor liest und schreibt darin wie in einer eigenen Datei; nichts ausserhalb des Fensters wird beruehrt.
    """

    def __init__(self, fh: BinaryIO, basis: int, laenge: int) -> None:
        self._fh = fh
        self._basis = basis
        self._laenge = laenge
        self._pos = 0

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 1:
            offset += self._pos
        elif whence == 2:
            offset += self._laenge
        self._pos = max(0, offset)
        return self._pos

    def tell(self) -> int:
        return self._pos

    def read(self, anzahl: int = -1) -> bytes:
        ende = self._laenge if anzahl is None or anzahl < 0 else min(self._laenge, self._pos + anzahl)
        if ende <= self._pos:
            return b""
        self._fh.seek(self._basis + self._pos)
        daten = self._fh.read(ende - self._pos)
        self._pos += len(daten)
        return daten

    def write(self, daten: "bytes | bytearray | memoryview") -> int:
        if self._pos + len(daten) > self._laenge:
            raise ExfatBearbeitenFehler("Schreiben hinter dem Ende des inneren Abbilds (%d + %d > %d)" % (
                self._pos, len(daten), self._laenge))
        self._fh.seek(self._basis + self._pos)
        n = self._fh.write(daten)
        self._pos += len(daten)
        return n

    def flush(self) -> None:
        self._fh.flush()

    def fileno(self) -> int:
        return self._fh.fileno()

    def close(self) -> None:
        self._fh.close()


# ---------------------------------------------------------------------------------------------------------------------------
# exFAT
# ---------------------------------------------------------------------------------------------------------------------------
def _satz_pruefsumme(eintraege: bytes) -> int:
    cs = 0
    for i, byte in enumerate(eintraege):
        if i in (2, 3):
            continue
        cs = (((cs << 15) | (cs >> 1)) & 0xFFFF) + byte
        cs &= 0xFFFF
    return cs


def _dos_zeit(sekunden: "float | None" = None) -> int:
    t = time.localtime(sekunden if sekunden is not None else time.time())
    return max(0, t.tm_year - 1980) << 25 | t.tm_mon << 21 | t.tm_mday << 16 | t.tm_hour << 11 | t.tm_min << 5 | (t.tm_sec // 2)


@dataclass
class _Satz:
    """Ein Verzeichniseintrag (File + Stream + Namen) im Rohinhalt eines Verzeichnisses."""

    anfang: int                 # Byte-Offset im Rohinhalt des Verzeichnisses
    anzahl: int                 # Eintraege insgesamt (1 + Folgeeintraege)
    name: str
    attribute: int
    erster: int
    laenge: int
    flags: int

    @property
    def ist_ordner(self) -> bool:
        return bool(self.attribute & _ATTR_DIRECTORY)


@dataclass
class _Verzeichnis:
    cluster: "list[int]"
    roh: bytearray
    saetze: "list[_Satz]" = field(default_factory=list)
    eltern_satz: "tuple[_Verzeichnis, _Satz] | None" = None     # der Eintrag dieses Ordners im Elternordner (Wurzel: keiner)
    pfad: str = ""
    ohne_kette: bool = False                                     # Ordner ohne FAT-Kette (zusammenhaengend): wird nicht erweitert


class _Plan:
    """Aenderungen im Speicher: ``(Offset, neue Bytes)`` und die Dateidaten, die in freie Cluster kommen."""

    def __init__(self) -> None:
        self.stellen: "list[tuple[int, bytes]]" = []
        self.daten: "list[Callable[[BinaryIO], None]]" = []

    def schreiben(self, offset: int, daten: bytes) -> None:
        self.stellen.append((offset, bytes(daten)))


class ExfatAbbild:
    """Ein exFAT-Abbild zum Aendern in place. ``with ExfatAbbild(pfad) as a: a.umbenennen(...); a.speichern()``."""

    #: Fuer die Oberflaeche: welches Format dieser Editor aendert.
    art = "exfat"

    def __init__(self, pfad: str, *, basis: int = 0, laenge: "int | None" = None) -> None:
        """``basis``/``laenge``: Das exFAT liegt als innere Datei in einer unkomprimierten PFS-Huelle (``pfs_bearbeiten.oeffnen``); der
        Editor aendert nur diese ``laenge`` Bytes ab ``basis``, das Journal nennt die Stellen in der aeusseren Datei."""
        self.pfad = pfad
        self._basis = int(basis)
        journal_zurueckspielen(pfad)                                  # ein Abbruch des letzten Laufs wird hier rueckgaengig gemacht
        datei = open(pfad, "r+b")
        self._fh: BinaryIO = datei if not self._basis and laenge is None else _Fenster(  # type: ignore[assignment]
            datei, self._basis, int(laenge if laenge is not None else os.fstat(datei.fileno()).st_size - self._basis))
        self._plan = _Plan()
        self._cache: "dict[str, _Verzeichnis]" = {}
        self._daten_cluster: "set[int]" = set()                          # Cluster, in die Dateidaten geschrieben werden
        self._bitmap_platte = b""                                        # die Bitmap, wie sie auf der Platte steht (beim Speichern gelesen)
        try:
            self._boot()
            self._fat_laden()
            self._wurzel_lesen()
        except BaseException:
            self._fh.close()
            raise

    def __enter__(self) -> "ExfatAbbild":
        return self

    def __exit__(self, *_a: object) -> None:
        self.schliessen()

    def schliessen(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass

    # -- Aufbau ---------------------------------------------------------------------------------------------------------
    def _boot(self) -> None:
        self._fh.seek(0)
        vbr = self._fh.read(512)
        if len(vbr) < 512 or vbr[3:11] != b"EXFAT   " or struct.unpack_from("<H", vbr, 510)[0] != 0xAA55:
            raise ExfatBearbeitenFehler("kein exFAT-Abbild")
        self.fat_sektor, self.fat_sektoren, self.heap_sektor, self.cluster_anzahl, self.wurzel_cluster = struct.unpack_from(
            "<IIIII", vbr, 80)
        sektor_shift, cluster_shift = vbr[108], vbr[109]
        if not (9 <= sektor_shift <= 12) or vbr[110] != 1:
            raise ExfatBearbeitenFehler("nicht unterstuetzt: Sektorgroesse oder mehrere FATs")
        self.sektor = 1 << sektor_shift
        self.cluster_groesse = self.sektor << cluster_shift

    def _cluster_offset(self, cluster: int) -> int:
        return (self.heap_sektor + (cluster - 2) * (self.cluster_groesse // self.sektor)) * self.sektor

    def _fat_laden(self) -> None:
        laenge = (self.cluster_anzahl + 2) * 4
        if laenge > _FAT_MAX:
            raise ExfatBearbeitenFehler("Die FAT ist zu gross zum Aendern in place")
        self._fh.seek(self.fat_sektor * self.sektor)
        roh = self._fh.read(laenge)
        if len(roh) < laenge:
            raise ExfatBearbeitenFehler("Die FAT ist abgeschnitten")
        self.fat = bytearray(roh)

    def _kette(self, erster: int, ohne_kette: bool = False, laenge: int = 0) -> "list[int]":
        """Die Cluster einer Zuordnung: zusammenhaengend (``ohne_kette``, mit ``laenge``) oder ueber die FAT."""
        if erster < 2:
            return []
        if ohne_kette and laenge > 0:
            return list(range(erster, erster + (laenge + self.cluster_groesse - 1) // self.cluster_groesse))
        kette, c = [], erster
        while 2 <= c < self.cluster_anzahl + 2:
            kette.append(c)
            if len(kette) > self.cluster_anzahl:
                raise ExfatBearbeitenFehler("Cluster-Kette ohne Ende (Schleife)")
            c = struct.unpack_from("<I", self.fat, c * 4)[0]
        return kette

    def _roh_lesen(self, kette: "list[int]") -> bytearray:
        roh = bytearray()
        for c in kette:
            self._fh.seek(self._cluster_offset(c))
            roh += self._fh.read(self.cluster_groesse)
        return roh

    def _wurzel_lesen(self) -> None:
        self._wurzel = self._verzeichnis_laden(self.wurzel_cluster, "", None)
        bitmap = upcase = None
        for i in range(0, len(self._wurzel.roh), 32):
            typ = self._wurzel.roh[i]
            if typ == 0:
                break
            if typ == _ENTRY_BITMAP:
                bitmap = struct.unpack_from("<IQ", self._wurzel.roh, i + 0x14)
            elif typ == _ENTRY_UPCASE:
                upcase = struct.unpack_from("<IQ", self._wurzel.roh, i + 0x14)
        if bitmap is None:
            raise ExfatBearbeitenFehler("Die Belegungs-Bitmap fehlt im Wurzelverzeichnis")
        self.bitmap_cluster, bitmap_laenge = bitmap
        self.bitmap_kette = self._kette(self.bitmap_cluster, False, bitmap_laenge)
        self.bitmap = bytearray(self._roh_lesen(self.bitmap_kette)[: (self.cluster_anzahl + 7) // 8])
        self._bitmap_roh_laenge = len(self.bitmap_kette) * self.cluster_groesse
        self._upcase = self._upcase_laden(upcase)

    def _upcase_laden(self, eintrag: "tuple[int, int] | None") -> "list[int]":
        tabelle = list(range(0x10000))
        if eintrag is None:
            return tabelle
        erster, laenge = eintrag
        roh = bytes(self._roh_lesen(self._kette(erster, False, laenge))[:laenge])
        werte = struct.unpack("<%dH" % (len(roh) // 2), roh[: len(roh) // 2 * 2])
        i = j = 0
        while i < len(werte) and j < 0x10000:
            if werte[i] == 0xFFFF and i + 1 < len(werte):        # komprimiert: ``0xFFFF, n`` = die naechsten n Zeichen bleiben gleich
                j += werte[i + 1]
                i += 2
                continue
            tabelle[j] = werte[i]
            i += 1
            j += 1
        return tabelle

    # -- Namen ----------------------------------------------------------------------------------------------------------
    def _gross(self, name: str) -> str:
        return "".join(chr(self._upcase[ord(z)]) if ord(z) < 0x10000 else z for z in name)

    def _name_hash(self, name: str) -> int:
        h = 0
        for byte in self._gross(name).encode("utf-16-le"):
            h = (((h << 15) | (h >> 1)) & 0xFFFF) + byte
            h &= 0xFFFF
        return h

    @staticmethod
    def _name_pruefen(name: str) -> None:
        if not name or name in (".", "..") or len(name) > 255 or name != name.strip(" ") or name.endswith("."):
            raise ExfatBearbeitenFehler("Unzulaessiger Name: %r" % name)
        if any(z in _VERBOTEN or ord(z) < 32 for z in name):
            raise ExfatBearbeitenFehler("Der Name enthaelt ein verbotenes Zeichen: %r" % name)

    # -- Verzeichnisse --------------------------------------------------------------------------------------------------
    def _saetze_lesen(self, roh: bytearray) -> "list[_Satz]":
        saetze: "list[_Satz]" = []
        i = 0
        while i + 32 <= len(roh):
            typ = roh[i]
            if typ == 0:
                break
            if typ != _ENTRY_FILE:
                i += 32
                continue
            folge = roh[i + 1]
            if i + 32 * (1 + folge) > len(roh) or folge < 2 or roh[i + 32] != _ENTRY_STREAM:
                raise ExfatBearbeitenFehler("Beschaedigter Verzeichniseintrag bei Offset %d" % i)
            strom = roh[i + 32: i + 64]
            namen = bytearray()
            for k in range(2, 1 + folge):
                eintrag = roh[i + 32 * k: i + 32 * (k + 1)]
                if eintrag[0] != _ENTRY_NAME:
                    raise ExfatBearbeitenFehler("Beschaedigter Namenseintrag bei Offset %d" % (i + 32 * k))
                namen += eintrag[2:32]
            name = bytes(namen).decode("utf-16-le", errors="replace")[: strom[3]]
            saetze.append(_Satz(i, 1 + folge, name, struct.unpack_from("<H", roh, i + 4)[0],
                                struct.unpack_from("<I", strom, 0x14)[0], struct.unpack_from("<Q", strom, 0x18)[0], strom[1]))
            i += 32 * (1 + folge)
        return saetze

    def _verzeichnis_laden(self, erster: int, pfad: str, eltern: "tuple[_Verzeichnis, _Satz] | None",
                           ohne_kette: bool = False, laenge: int = 0) -> _Verzeichnis:
        kette = self._kette(erster, ohne_kette, laenge)
        roh = self._roh_lesen(kette)
        v = _Verzeichnis(kette, roh, [], eltern, pfad, ohne_kette)
        v.saetze = self._saetze_lesen(roh)
        return v

    def _verzeichnis(self, rel: str) -> _Verzeichnis:
        """Das Verzeichnis zu ``rel`` (``""`` = Wurzel). Aenderungen im Speicher bleiben bis zum Speichern sichtbar."""
        rel = rel.strip("/")
        if not rel:
            return self._wurzel
        if rel in self._cache:
            return self._cache[rel]
        eltern_rel, _, name = rel.rpartition("/")
        eltern = self._verzeichnis(eltern_rel)
        satz = self._finde(eltern, name)
        if satz is None or not satz.ist_ordner:
            raise ExfatBearbeitenFehler("Ordner nicht gefunden: %s" % rel)
        v = self._verzeichnis_laden(satz.erster, rel, (eltern, satz), bool(satz.flags & _FLAG_NO_FAT_CHAIN), satz.laenge)
        self._cache[rel] = v
        return v

    def _finde(self, verzeichnis: _Verzeichnis, name: str) -> "_Satz | None":
        schluessel = self._gross(name)
        for satz in verzeichnis.saetze:
            if self._gross(satz.name) == schluessel:
                return satz
        return None

    def auflisten(self, rel: str = "") -> "list[tuple[str, bool, int]]":
        """``(Name, ist_ordner, Groesse)`` der Eintraege eines Ordners."""
        return [(s.name, s.ist_ordner, 0 if s.ist_ordner else s.laenge) for s in self._verzeichnis(rel).saetze]

    # -- Bitmap und FAT -------------------------------------------------------------------------------------------------
    def _belegt(self, cluster: int) -> bool:
        i = cluster - 2
        return bool(self.bitmap[i >> 3] & (1 << (i & 7)))

    def _belegung(self, cluster: int, belegt: bool) -> None:
        i = cluster - 2
        if belegt:
            self.bitmap[i >> 3] |= 1 << (i & 7)
        else:
            self.bitmap[i >> 3] &= ~(1 << (i & 7)) & 0xFF

    def _freie(self) -> "Iterator[int]":
        """Die freien Cluster in aufsteigender Reihenfolge (volle Bitmap-Bytes werden uebersprungen)."""
        grenze = self.cluster_anzahl + 2
        for b, wert in enumerate(self.bitmap):
            if wert == 0xFF:
                continue
            for bit in range(8):
                c = b * 8 + bit + 2
                if c >= grenze:
                    return
                if not wert & (1 << bit):
                    yield c

    def freie_bytes(self) -> int:
        """Freier Platz fuer neue Dateidaten (gemeinsame Schnittstelle der Editoren fuer die Oberflaeche)."""
        return self.freie_cluster() * self.cluster_groesse

    def freie_cluster(self) -> int:
        """Wie viele Cluster frei sind."""
        return sum(1 for _ in self._freie())

    def _zuteilen(self, anzahl: int) -> "list[int]":
        """``anzahl`` freie Cluster: bevorzugt ein zusammenhaengender Lauf (erste Passung), sonst die ersten freien."""
        if anzahl <= 0:
            return []
        lauf: "list[int]" = []
        frei: "list[int]" = []
        for c in self._freie():
            if lauf and c != lauf[-1] + 1:
                lauf = []
            lauf.append(c)
            if len(lauf) == anzahl:
                return lauf
            if len(frei) < anzahl:
                frei.append(c)
        if len(frei) < anzahl:
            fehlen = anzahl - len(frei)
            raise PlatzFehlt("Im Abbild fehlen %d Cluster (%d KiB); es waechst nie - bitte neu bauen"
                             % (fehlen, fehlen * self.cluster_groesse // 1024))
        return frei

    def _kette_eintragen(self, kette: "list[int]") -> None:
        for a, b in zip(kette, kette[1:]):
            struct.pack_into("<I", self.fat, a * 4, b)
        struct.pack_into("<I", self.fat, kette[-1] * 4, _FAT_ENDE)
        for c in kette:
            self._belegung(c, True)

    def _kette_freigeben(self, kette: "list[int]") -> None:
        for c in kette:
            struct.pack_into("<I", self.fat, c * 4, _FAT_FREI)
            self._belegung(c, False)

    # -- Eintraege bauen ------------------------------------------------------------------------------------------------
    def _satz_bytes(self, name: str, attribute: int, erster: int, laenge: int, zeiten: bytes, flags: "int | None" = None) -> bytes:
        """Die Eintraege eines Satzes. ``zeiten``: die 24 Bytes ab Offset 8 des File-Eintrags (Zeiten samt Feinheiten und Zeitzone)."""
        anzahl_namen = (len(name) + _NAME_PRO_EINTRAG - 1) // _NAME_PRO_EINTRAG
        datei = bytearray(32)
        datei[0] = _ENTRY_FILE
        datei[1] = 1 + anzahl_namen
        struct.pack_into("<H", datei, 4, attribute)
        datei[8:32] = zeiten
        strom = bytearray(32)
        strom[0] = _ENTRY_STREAM
        strom[1] = (_FLAG_ALLOC if erster >= 2 else 0) if flags is None else flags
        strom[3] = len(name)
        struct.pack_into("<H", strom, 4, self._name_hash(name))
        struct.pack_into("<Q", strom, 8, laenge)
        struct.pack_into("<I", strom, 0x14, erster if erster >= 2 else 0)
        struct.pack_into("<Q", strom, 0x18, laenge)
        namen = bytearray()
        raw = name.encode("utf-16-le")
        for k in range(anzahl_namen):
            e = bytearray(32)
            e[0] = _ENTRY_NAME
            stueck = raw[k * 30:(k + 1) * 30]
            e[2:2 + len(stueck)] = stueck
            namen += e
        struct.pack_into("<H", datei, 2, _satz_pruefsumme(bytes(datei) + bytes(strom) + bytes(namen)))
        return bytes(datei) + bytes(strom) + bytes(namen)

    def _verzeichnis_schreiben(self, v: _Verzeichnis, von: int, bis: int) -> None:
        """Plant das Schreiben von ``v.roh[von:bis]`` an die Cluster des Verzeichnisses."""
        gs = self.cluster_groesse
        pos = von
        while pos < bis:
            k = pos // gs
            ende = min(bis, (k + 1) * gs)
            self._plan.schreiben(self._cluster_offset(v.cluster[k]) + pos % gs, bytes(v.roh[pos:ende]))
            pos = ende

    @staticmethod
    def _freier_lauf(roh: bytearray, eintraege: int) -> int:
        """Byte-Offset von ``eintraege`` zusammenhaengenden unbenutzten Eintraegen (Ende-Marke oder geloescht), sonst ``-1``."""
        frei = 0
        for i in range(0, len(roh), 32):
            if roh[i] & 0x80 == 0:
                frei += 1
                if frei == eintraege:
                    return i - 32 * (eintraege - 1)
            else:
                frei = 0
        return -1

    def _platz_im_verzeichnis(self, v: _Verzeichnis, eintraege: int) -> int:
        """Byte-Offset fuer ``eintraege`` Eintraege; haengt dem Ordner einen Cluster an, wenn er voll ist."""
        ort = self._freier_lauf(v.roh, eintraege)
        if ort >= 0:
            return ort
        if v.ohne_kette:
            raise PlatzFehlt("Der Ordner ist voll und liegt ohne FAT-Kette im Abbild; bitte neu bauen")
        zusatz = self._zuteilen(1)
        self._kette_eintragen(zusatz)
        struct.pack_into("<I", self.fat, v.cluster[-1] * 4, zusatz[0])
        v.cluster.append(zusatz[0])
        v.roh += bytearray(self.cluster_groesse)
        self._plan.schreiben(self._cluster_offset(zusatz[0]), bytes(self.cluster_groesse))
        if v.eltern_satz is not None:                                       # die Laenge des Ordners im Elternordner
            eltern, satz = v.eltern_satz
            self._satz_neu_schreiben(eltern, satz, laenge=len(v.cluster) * self.cluster_groesse)
        ort = self._freier_lauf(v.roh, eintraege)
        if ort < 0:
            raise ExfatBearbeitenFehler("Kein Platz im Verzeichnis")
        return ort

    def _satz_neu_schreiben(self, v: _Verzeichnis, satz: _Satz, *, laenge: "int | None" = None, erster: "int | None" = None,
                            aenderungszeit: "int | None" = None) -> None:
        """Aendert Laenge, ersten Cluster oder Aenderungszeit eines vorhandenen Eintrags und rechnet die Satzpruefsumme neu."""
        roh = v.roh
        a = satz.anfang
        if laenge is not None:
            struct.pack_into("<Q", roh, a + 32 + 0x08, laenge)
            struct.pack_into("<Q", roh, a + 32 + 0x18, laenge)
            satz.laenge = laenge
        if erster is not None:
            struct.pack_into("<I", roh, a + 32 + 0x14, erster if erster >= 2 else 0)
            roh[a + 32 + 1] = _FLAG_ALLOC if erster >= 2 else 0                  # ersetzte Inhalte laufen ueber die FAT-Kette
            satz.erster, satz.flags = erster, roh[a + 32 + 1]
        if aenderungszeit is not None:
            struct.pack_into("<I", roh, a + 12, aenderungszeit)
        folge = roh[a + 1]
        struct.pack_into("<H", roh, a + 2, 0)
        struct.pack_into("<H", roh, a + 2, _satz_pruefsumme(bytes(roh[a: a + 32 * (1 + folge)])))
        self._verzeichnis_schreiben(v, a, a + 32 * (1 + folge))

    def _satz_loeschen(self, v: _Verzeichnis, satz: _Satz) -> None:
        for k in range(satz.anzahl):
            v.roh[satz.anfang + 32 * k] &= 0x7F
        self._verzeichnis_schreiben(v, satz.anfang, satz.anfang + 32 * satz.anzahl)
        v.saetze.remove(satz)

    def _satz_einfuegen(self, v: _Verzeichnis, name: str, attribute: int, erster: int, laenge: int, zeiten: bytes,
                        flags: "int | None" = None) -> _Satz:
        blob = self._satz_bytes(name, attribute, erster, laenge, zeiten, flags)
        ort = self._platz_im_verzeichnis(v, len(blob) // 32)
        v.roh[ort: ort + len(blob)] = blob
        self._verzeichnis_schreiben(v, ort, ort + len(blob))
        satz = _Satz(ort, len(blob) // 32, name, attribute, erster, laenge, blob[33])
        v.saetze.append(satz)
        return satz

    def _zeiten_neu(self) -> bytes:
        jetzt = _dos_zeit()
        return struct.pack("<III", jetzt, jetzt, jetzt) + bytes(12)

    # -- Zugriff auf Eintraege ------------------------------------------------------------------------------------------
    def _ziel(self, rel: str) -> "tuple[_Verzeichnis, str]":
        eltern, _, name = rel.strip("/").rpartition("/")
        return self._verzeichnis(eltern), name

    def _satz_holen(self, rel: str) -> "tuple[_Verzeichnis, _Satz]":
        v, name = self._ziel(rel)
        satz = self._finde(v, name)
        if satz is None:
            raise ExfatBearbeitenFehler("Nicht gefunden: %s" % rel)
        return v, satz

    def _inhalt_kette(self, satz: _Satz) -> "list[int]":
        return self._kette(satz.erster, bool(satz.flags & _FLAG_NO_FAT_CHAIN), satz.laenge)

    # -- Aenderungen ----------------------------------------------------------------------------------------------------
    @contextlib.contextmanager
    def _transaktion(self) -> "Iterator[None]":
        """Macht eine Aenderung im Speicher zu einem Ganzen: Scheitert sie (Platz, Name), steht alles wieder wie vorher.

        Eine Aenderung besteht aus mehreren Schritten (Cluster zuteilen, Daten vormerken, Eintrag schreiben, Ordner erweitern); ein Fehler
        im letzten liesse sonst die ersten stehen - belegte Cluster ohne Eintrag.
        """
        verzeichnisse = [("", self._wurzel)] + list(self._cache.items())
        stand = (bytearray(self.fat), bytearray(self.bitmap), len(self._plan.stellen), len(self._plan.daten),
                 set(self._daten_cluster), dict(self._cache),
                 [(v, bytearray(v.roh), list(v.cluster), list(v.saetze), [(s, dict(s.__dict__)) for s in v.saetze])
                  for _k, v in verzeichnisse])
        try:
            yield
        except BaseException:
            self.fat, self.bitmap = stand[0], stand[1]
            del self._plan.stellen[stand[2]:]
            del self._plan.daten[stand[3]:]
            self._daten_cluster = stand[4]
            self._cache = stand[5]
            for v, roh, cluster, saetze, felder in stand[6]:
                v.roh, v.cluster = roh, cluster
                v.saetze[:] = saetze
                for satz, werte in felder:
                    satz.__dict__.update(werte)
            raise

    def umbenennen(self, rel: str, neuer_name: str) -> None:
        """Benennt eine Datei oder einen Ordner um (im selben Ordner). Der Inhalt bleibt, wo er ist; die Zeitstempel auch."""
        with self._transaktion():
            self._umbenennen(rel, neuer_name)

    def _umbenennen(self, rel: str, neuer_name: str) -> None:
        self._name_pruefen(neuer_name)
        rel = rel.strip("/")
        v, satz = self._satz_holen(rel)
        vorhanden = self._finde(v, neuer_name)
        if vorhanden is not None and vorhanden is not satz:
            raise ExfatBearbeitenFehler("Der Name ist schon vergeben: %s" % neuer_name)
        zeiten = bytes(v.roh[satz.anfang + 8: satz.anfang + 32])
        flags = v.roh[satz.anfang + 33]
        self._satz_loeschen(v, satz)
        self._satz_einfuegen(v, neuer_name, satz.attribute, satz.erster, satz.laenge, zeiten, flags)
        if satz.ist_ordner:
            eltern, _, _ = rel.rpartition("/")
            neu = (eltern + "/" if eltern else "") + neuer_name
            neuer_cache: "dict[str, _Verzeichnis]" = {}
            for k, x in self._cache.items():
                if k == rel or k.startswith(rel + "/"):
                    k = neu + k[len(rel):]
                    x.pfad = k
                neuer_cache[k] = x
            self._cache = neuer_cache
            if neu in self._cache:                                          # sein Eintrag im Elternordner ist der neue
                self._cache[neu].eltern_satz = (v, self._finde(v, neuer_name))  # type: ignore[assignment]

    def loeschen(self, rel: str) -> int:
        """Loescht eine Datei oder einen Ordner samt Inhalt. Rueckgabe: die Zahl freigegebener Cluster."""
        with self._transaktion():
            return self._loeschen(rel)

    def _loeschen(self, rel: str) -> int:
        rel = rel.strip("/")
        v, satz = self._satz_holen(rel)
        freigegeben = self._baum_freigeben(rel, satz)
        self._satz_loeschen(v, satz)
        self._cache = {k: x for k, x in self._cache.items() if k != rel and not k.startswith(rel + "/")}
        return freigegeben

    def _baum_freigeben(self, rel: str, satz: _Satz) -> int:
        n = 0
        if satz.ist_ordner:
            for kind in list(self._verzeichnis(rel).saetze):
                n += self._baum_freigeben(rel + "/" + kind.name, kind)
        kette = self._inhalt_kette(satz)
        self._kette_freigeben(kette)
        return n + len(kette)

    def ordner_anlegen(self, rel: str) -> None:
        """Legt einen leeren Ordner an (er braucht einen Cluster)."""
        with self._transaktion():
            self._ordner_anlegen(rel)

    def _ordner_anlegen(self, rel: str) -> None:
        v, name = self._ziel(rel)
        self._name_pruefen(name)
        if self._finde(v, name) is not None:
            raise ExfatBearbeitenFehler("Der Name ist schon vergeben: %s" % name)
        kette = self._zuteilen(1)
        self._kette_eintragen(kette)
        self._plan.schreiben(self._cluster_offset(kette[0]), bytes(self.cluster_groesse))
        self._satz_einfuegen(v, name, _ATTR_DIRECTORY, kette[0], self.cluster_groesse, self._zeiten_neu())

    def hinzufuegen(self, rel: str, quelle: str) -> None:
        """Legt eine Datei aus ``quelle`` (Pfad) neu an. Der Name darf noch nicht vergeben sein."""
        with self._transaktion():
            self._hinzufuegen(rel, quelle)

    def _hinzufuegen(self, rel: str, quelle: str) -> None:
        v, name = self._ziel(rel)
        self._name_pruefen(name)
        if self._finde(v, name) is not None:
            raise ExfatBearbeitenFehler("Der Name ist schon vergeben: %s" % name)
        groesse = os.path.getsize(quelle)
        kette = self._zuteilen((groesse + self.cluster_groesse - 1) // self.cluster_groesse)
        if kette:
            self._kette_eintragen(kette)
        self._daten_vormerken(kette, quelle, groesse)
        self._satz_einfuegen(v, name, _ATTR_ARCHIVE, kette[0] if kette else 0, groesse, self._zeiten_neu())

    def ersetzen(self, rel: str, quelle: str) -> None:
        """Ersetzt den Inhalt einer Datei durch den von ``quelle``. Der Platz der alten Datei zaehlt mit; was davon ueberschrieben wird,
        landet vorher im Journal."""
        with self._transaktion():
            self._ersetzen(rel, quelle)

    def _ersetzen(self, rel: str, quelle: str) -> None:
        v, satz = self._satz_holen(rel)
        if satz.ist_ordner:
            raise ExfatBearbeitenFehler("Ein Ordner hat keinen Inhalt zum Ersetzen: %s" % rel)
        alt = self._inhalt_kette(satz)
        groesse = os.path.getsize(quelle)
        brauche = (groesse + self.cluster_groesse - 1) // self.cluster_groesse
        self._kette_freigeben(alt)                                    # im Speicher: der Platz der alten Datei steht zur Verfuegung
        neu = self._zuteilen(brauche)
        if neu:
            self._kette_eintragen(neu)
        self._daten_vormerken(neu, quelle, groesse)
        self._satz_neu_schreiben(v, satz, laenge=groesse, erster=neu[0] if neu else 0, aenderungszeit=_dos_zeit())

    def _daten_vormerken(self, kette: "list[int]", quelle: str, groesse: int) -> None:
        self._daten_cluster |= set(kette)

        def schreiben(fh: BinaryIO) -> None:
            rest = groesse
            with open(quelle, "rb") as q:
                for c in kette:
                    block = q.read(min(self.cluster_groesse, rest))
                    rest -= len(block)
                    fh.seek(self._cluster_offset(c))
                    fh.write(block)
                    if len(block) < self.cluster_groesse:
                        fh.write(bytes(self.cluster_groesse - len(block)))
        self._plan.daten.append(schreiben)

    # -- Schreiben ------------------------------------------------------------------------------------------------------
    def _metadaten_planen(self) -> None:
        """Haengt die geaenderten Teile von FAT und Bitmap als Schreibstellen an (Vergleich mit dem, was auf der Platte steht)."""
        self._fh.seek(self.fat_sektor * self.sektor)
        fat_alt = self._fh.read(len(self.fat))
        for i in range(0, len(self.fat), _BLOCK):
            if self.fat[i:i + _BLOCK] != fat_alt[i:i + _BLOCK]:
                self._plan.schreiben(self.fat_sektor * self.sektor + i, bytes(self.fat[i:i + _BLOCK]))
        bitmap_alt = bytes(self._roh_lesen(self.bitmap_kette))
        self._bitmap_platte = bitmap_alt
        for k in range(0, len(self.bitmap), _BLOCK):
            stueck = bytes(self.bitmap[k:k + _BLOCK])
            if stueck != bitmap_alt[k:k + len(stueck)]:
                self._plan.schreiben(self._cluster_offset(self.bitmap_kette[k // self.cluster_groesse]) + k % self.cluster_groesse,
                                     stueck)

    def speichern(self) -> None:
        """Schreibt alle geplanten Aenderungen: Journal, Dateidaten, Eintraege/FAT/Bitmap - so, dass ein Abbruch nie ein halbes Abbild
        hinterlaesst. Ohne Aenderungen geschieht nichts."""
        if not self._plan.stellen and not self._plan.daten:
            return
        self._metadaten_planen()
        alte: "list[tuple[int, bytes]]" = []
        gesichert = 0
        for c in sorted(self._daten_cluster):
            i = c - 2
            if not self._bitmap_platte[i >> 3] & (1 << (i & 7)):
                continue                                                # auf der Platte frei: nichts zu sichern
            self._fh.seek(self._cluster_offset(c))                      # auf der Platte belegt (geloeschte oder ersetzte Datei): sichern
            alte.append((self._cluster_offset(c), self._fh.read(self.cluster_groesse)))
            gesichert += self.cluster_groesse
        if gesichert > _JOURNAL_DATEN_MAX:
            raise PlatzFehlt("Der ersetzte Inhalt ist fuer das Journal zu gross (%d MiB); bitte neu bauen" % (gesichert >> 20))
        for offset, neu in self._plan.stellen:
            self._fh.seek(offset)
            alte.append((offset, self._fh.read(len(neu))))
        # Das Journal nennt Stellen in der Datei selbst: In einer PFS-Huelle liegt das exFAT ab ``basis``.
        _journal_schreiben(journal_pfad(self.pfad), [(self._basis + o, alt) for o, alt in alte])
        try:
            for schreiben in self._plan.daten:
                schreiben(self._fh)
            for offset, neu in self._plan.stellen:
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
        self._plan = _Plan()
        self._daten_cluster = set()
        self._cache = {}
        self._wurzel = self._verzeichnis_laden(self.wurzel_cluster, "", None)

    # -- Pruefung -------------------------------------------------------------------------------------------------------
    def pruefen(self) -> "list[str]":
        """Prueft die Ordnung des Abbilds: jeder Cluster hoechstens einmal benutzt, Bitmap und Eintraege stimmen ueberein.

        Rueckgabe: die Befunde (leer = in Ordnung).
        """
        befunde: "list[str]" = []
        benutzt: "dict[int, str]" = {}

        def belegen(kette: "list[int]", wer: str) -> None:
            for c in kette:
                if c in benutzt:
                    befunde.append("Cluster %d doppelt benutzt: %s und %s" % (c, benutzt[c], wer))
                benutzt[c] = wer

        belegen(self.bitmap_kette, "Bitmap")
        belegen(self._wurzel.cluster, "Wurzel")
        hat_upcase = False
        for i in range(0, len(self._wurzel.roh), 32):
            if self._wurzel.roh[i] == _ENTRY_UPCASE:
                erster, laenge = struct.unpack_from("<IQ", self._wurzel.roh, i + 0x14)
                belegen(self._kette(erster, False, laenge), "Upcase")
                hat_upcase = True
        if not hat_upcase:
            befunde.append("Keine Upcase-Tabelle")

        def gehen(rel: str, v: _Verzeichnis) -> None:
            for s in v.saetze:
                pfad = (rel + "/" + s.name) if rel else s.name
                if s.laenge and s.erster < 2:
                    befunde.append("Eintrag mit Laenge ohne Cluster: %s" % pfad)
                    continue
                kette = self._inhalt_kette(s)
                if not s.ist_ordner and len(kette) != (s.laenge + self.cluster_groesse - 1) // self.cluster_groesse:
                    befunde.append("Kettenlaenge passt nicht zur Groesse: %s" % pfad)
                belegen(kette, pfad)
                if s.ist_ordner:
                    gehen(pfad, self._verzeichnis(pfad))

        gehen("", self._wurzel)
        for c in range(2, self.cluster_anzahl + 2):
            if self._belegt(c) != (c in benutzt):
                befunde.append("Bitmap und Eintraege widersprechen sich bei Cluster %d" % c)
                break
        return befunde
