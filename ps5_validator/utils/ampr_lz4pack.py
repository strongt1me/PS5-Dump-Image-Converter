# -*- coding: utf-8 -*-
"""LZ4-Asset-Packs im Strom, ohne Zwischenordner (Stufe 3, Etappe 14) - wie ``ampr_zstdpack`` und wie Dump Forge.

Das Packwerkzeug des Herstellers (``AMPR_PackTools-4.0/ampr_pack.py``) liest einen Spielordner und schreibt die Baender in einen
Ausgabeordner: Fuer ein Spiel in einem Abbild hiess das erst entpacken, dann packen, dann das Abbild bauen. Hier laeuft dasselbe
als zwei Durchgaenge ueber einen Lesebaum (:mod:`spielbaum`):

1. **Messen** (:func:`messen`): Alles wird gelesen und verdichtet, aber nichts gespeichert. Gemerkt wird, was der Schreibdurchgang
   vorab braucht: Lage und Groesse jedes Chunks (12 Bytes) und seine Pruefsumme, die Groesse jedes Bandes, die Build-ID und damit
   Manifest, Pruefsummenbeilage und Laufzeitprofil. Die Build-ID steht im Kopf jedes Bandes - deshalb ist der erste Durchgang noetig.
2. **Strom** (:func:`strom`): Jeder Chunk wird noch einmal verdichtet und gegen die Messung gehalten (Lage, Groesse, Pruefsumme der
   Quelle); die Baender kommen in der Reihenfolge ihrer Namen heraus, danach Manifest, Pruefsummenbeilage und Laufzeitprofil. So
   geht das Pack ohne Platz auf der Platte direkt in das Abbild. Die Quelle wird zweimal gelesen.

**Layout wie bei Forge** (``crates/ps5-dump-forge-lz4``): eine Spur je Gruppe, dichte Platzierung nach den Regeln des Werkzeugs
(``PackVolumeWriter.placement_for``), neue Baender bei ``max_pack_size`` der Gruppe. ``pack_count``/Spuren des Profils entfallen -
mehrere Spuren waeren nur ueber den Zugriff auf verstreute Dateien in einem Strom zu schreiben. **Was das Werkzeug zu lesen
versteht, entscheidet sich am Format, nicht an der Spurzahl:** Das Ergebnis liest ``ampr_pack.py verify`` und die Laufzeit.

Was dieser Weg nicht kann, meldet :class:`Lz4NichtImStrom` - der Aufrufer nimmt dann den Weg ueber den Ordner: mehr als eine Gruppe
mit gepackten Dateien (die Baender kaemen nicht in der Reihenfolge ihrer Namen), Striping grosser Dateien. **Kein Auto-Loose:**
grosse, kaum verdichtbare Dateien werden gepackt (Chunks, die LZ4 nicht verkleinert, bleiben roh), statt vorher stichprobenweise
lose zu bleiben - wie Forge bei ampr-emu-ng, und weil die Stichprobe wahlfreien Zugriff in die Quelle braeuchte.

Format und Regeln (``load_config``, ``select_rule``, Chunk- und Manifestformat, Build-ID) kommen unveraendert aus dem Werkzeug.
"""
from __future__ import annotations

import concurrent.futures
import fnmatch
import os
import random
import struct
import sys
import threading
import zlib
from array import array
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from ps5_validator.utils import ampr_assetpakete as ap
from ps5_validator.utils import ampr_zstdpack as z
from ps5_validator.utils.spielbaum import BaumFehler

MANIFEST = ap.MANIFEST_NAME
CRC_NAME = ap.PRUEFSUMMEN_NAME
PROFIL_NAME = ap.LAUFZEIT_NAME
#: Ein Chunk-Eintrag im Manifest (``<QI``).
CHUNK_EINTRAG = 12
LESE_STUECK = 4 << 20
STICHPROBE_ANTEIL = 0.01
STICHPROBE_MAX_CHUNKS = 16384


class Lz4PackFehler(z.ZstdPackFehler):
    """Der Packlauf ist gescheitert. Eine ``ZstdPackFehler``, damit der Strom-Weg beide Packer gleich behandelt."""


class Lz4NichtImStrom(Lz4PackFehler):
    """Dieses Profil oder Layout kann der Strom nicht schreiben; der Weg ueber den Ordner kann es."""


class Lz4SpeicherZuKlein(Lz4PackFehler):
    """Manifest und Index sprengen den Speicherblock des AMPR EMU: Kein Cache hilft (``ampr_pack.speicher_zu_klein``)."""

    def __init__(self, manifest_bytes: int, index_bytes: int, bisher: "dict[str, int]") -> None:
        super().__init__("ampr_pack.speicher_zu_klein")
        self.manifest_bytes = manifest_bytes
        self.index_bytes = index_bytes
        self.bisher = bisher


_geladen: "tuple[Any, Any] | None" = None


def _werkzeug() -> "tuple[Any, Any]":
    """``(ampr_pack, ampr_pack_format)`` des Packwerkzeugs - im eigenen Prozess importiert (beide liegen nebeneinander)."""
    global _geladen
    if _geladen is None:
        ordner = ap.werkzeugordner_finden()
        if not ordner:
            raise Lz4PackFehler("ampr_pack.werkzeug_fehlt")
        if ordner not in sys.path:
            sys.path.insert(0, ordner)
        try:
            import ampr_pack  # type: ignore[import-not-found]  # noqa: PLC0415
            import ampr_pack_format  # type: ignore[import-not-found]  # noqa: PLC0415
        except ImportError as exc:
            raise Lz4PackFehler("ampr_pack.lz4_fehlt") from exc
        _geladen = (ampr_pack, ampr_pack_format)
    return _geladen


def verfuegbar() -> bool:
    """Sind Packwerkzeug und LZ4-Modul da?"""
    return bool(ap.einsatzbereit()[0])


def ist_packname(rel: str) -> bool:
    """Ein Name, den dieser Packer schreibt (Baender und Beilagen); gilt bei jeder ``pack_pattern`` des Werkzeugs gleich."""
    klein = rel.lower()
    if klein in (MANIFEST, CRC_NAME, PROFIL_NAME):
        return True
    return fnmatch.fnmatchcase(klein, "ampr_assets*.pak")


# ---------------------------------------------------------------------------------------------------------------------------
# Auswahl
# ---------------------------------------------------------------------------------------------------------------------------
@dataclass
class _Punkt:
    nummer: int                    # file id (1-basiert, Reihenfolge von ampr_emu.index)
    eintrag: Any                   # AmprIndexEntry
    rel: str
    regel: Any                     # ampr_pack.Rule
    groesse: int
    mtime: int
    gepackt: bool


@dataclass
class Lz4Auswahl(z.Auswahl):
    """Was ein Lauf packt (``gepackt``) und was lose bleibt (``lose``) - dazu die Punkte des Index samt Regel."""

    punkte: "list[_Punkt]" = field(default_factory=list)
    config: Any = None
    gruppe: str = ""
    index_bytes: int = 0
    #: Dateien, die das Profil per Auto-Loose lose gelassen haette, der Strom aber packt.
    auto_loose_uebergangen: int = 0


def auswaehlen(baum: Any, index_pfad: str, profil_pfad: str, abbruch: Callable[[], bool] = lambda: False) -> Lz4Auswahl:
    """Wendet das Profil auf den ``ampr_emu.index`` an: je Datei Regel, gepackt oder lose - wie ``plan_files`` des Werkzeugs.

    Die Dateien kommen aus dem Lesebaum (Groesse und Vorhandensein), nicht aus einem Ordner. ``mtime`` ist die des Index
    (``preserve_mtime`` des Werkzeugs nimmt sonst die der Datei auf der Platte - einen Lesebaum hat keine).
    """
    ampr_pack, fmt = _werkzeug()
    try:
        config = ampr_pack.load_config(Path(profil_pfad))
        eintraege = fmt.read_ampridx3(Path(index_pfad))
    except (ampr_pack.PackError, ValueError, OSError) as exc:
        raise Lz4PackFehler("Profil oder Index nicht lesbar: %s" % exc) from exc
    dateien = baum.suchen()
    index_name = config.index_name.replace("\\", "/").lstrip("/")
    ausgabe_glob = ampr_pack._pack_output_glob(config.pack_pattern)
    ergebnis = Lz4Auswahl(config=config, index_bytes=os.path.getsize(index_pfad))
    gruppen: "set[str]" = set()
    for nummer, eintrag in enumerate(eintraege, 1):
        if abbruch():
            raise Lz4PackFehler("ampr_pack.abgebrochen")
        rel = fmt.asset_relative_path(eintrag.path)
        regel = ampr_pack.select_rule(config, rel)
        norm = rel.replace("\\", "/").lstrip("/")
        if norm in (index_name, index_name + ".crc", index_name + ".runtime") or fmt.glob_matches(norm, (ausgabe_glob,)):
            regel = ampr_pack.Rule(action="loose", block_shift=regel.block_shift)       # nie die Beilagen eines frueheren Laufs
        if regel.action == "loose":
            ergebnis.punkte.append(_Punkt(nummer, eintrag, rel, regel, eintrag.size, eintrag.mtime, False))
            ergebnis.lose.append((rel, eintrag.size))
            continue
        datei = dateien.get(rel)
        if datei is None:
            raise Lz4PackFehler("%s fehlt in der Quelle" % rel)
        if config.validate_index_metadata and datei.groesse != eintrag.size:
            raise Lz4PackFehler("Groesse von %s weicht vom Index ab (Index %d, Quelle %d)" % (rel, eintrag.size, datei.groesse))
        gruppe = config.groups[regel.group]
        if gruppe.stripe_large_files and gruppe.pack_count > 1 and datei.groesse >= gruppe.stripe_threshold:
            raise Lz4NichtImStrom("Striping grosser Dateien (Gruppe %s)" % regel.group)
        gruppen.add(regel.group)
        if (config.auto_loose_large_files and regel.action == "compress" and not regel.force_pack
                and datei.groesse >= config.auto_loose_min_file_size):
            ergebnis.auto_loose_uebergangen += 1
        ergebnis.punkte.append(_Punkt(nummer, eintrag, rel, regel, datei.groesse, eintrag.mtime, True))
        ergebnis.gepackt.append((rel, datei.groesse))
    if len(gruppen) > 1:
        raise Lz4NichtImStrom("%d Gruppen mit gepackten Dateien: %s" % (len(gruppen), ", ".join(sorted(gruppen))))
    ergebnis.gruppe = next(iter(gruppen), "")
    return ergebnis


def grund_gegen_strom(profil_pfad: str) -> str:
    """Warum der Strom dieses Profil nicht schreiben kann - oder ``""``, wenn er es kann.

    Das ist die Vorabfrage **ohne** Index und ohne Quelle (:func:`auswaehlen` prueft genauer, an den Dateien): mehr als eine Gruppe
    oder Striping einer Gruppe verlangen mehrere Baender gleichzeitig. Ein Profil, das das Werkzeug nicht lesen kann, ist kein Grund
    gegen den Strom - der Weg ueber den Ordner nennt den Fehler mit seinem eigenen Text.
    """
    ampr_pack, _fmt = _werkzeug()
    try:
        config = ampr_pack.load_config(Path(profil_pfad))
    except (ampr_pack.PackError, ValueError, OSError):
        return ""
    # Die Gruppe "default" legt das Werkzeug immer an; es zaehlt, was die Regeln wirklich packen.
    benutzt = sorted({regel.group for regel in config.rules if regel.action != "loose"})
    if len(benutzt) > 1:
        return "%d Gruppen: %s" % (len(benutzt), ", ".join(benutzt))
    for name in benutzt:
        gruppe = config.groups[name]
        if gruppe.stripe_large_files and gruppe.pack_count > 1:
            return "Striping grosser Dateien (Gruppe %s)" % name
    return ""


# ---------------------------------------------------------------------------------------------------------------------------
# Baender: nur Rechnen
# ---------------------------------------------------------------------------------------------------------------------------
class _Band:
    """Ein Band im Planen: Lage der Chunks wie ``PackVolumeWriter`` des Werkzeugs, ohne eine Datei zu oeffnen."""

    def __init__(self, fmt: Any, pack_id: int, name: str, config: Any, gruppe: Any) -> None:
        self.fmt = fmt
        self.pack_id = pack_id
        self.name = name
        self.io_page_size = gruppe.io_page_size or config.io_page_size
        self.payload_alignment = max(config.payload_alignment, self.io_page_size)
        self.chunk_alignment = config.chunk_alignment
        self.max_pack_size = gruppe.max_pack_size
        self.flags = fmt.PACK_FLAG_IO_PAGE_LAYOUT
        self.payload_offset = fmt.align_up(fmt.DATA_HEADER_SIZE, self.payload_alignment)
        self.position = self.payload_offset

    def platz(self, gespeichert: int, layout: str, extent_start: bool) -> "tuple[int, int]":
        fmt = self.fmt
        position = self.position
        if extent_start:
            position = fmt.align_up(position, self.io_page_size)
        if layout == "streaming":
            offset = fmt.align_up(position, self.chunk_alignment)
        elif gespeichert >= self.io_page_size:
            offset = fmt.align_up(position, self.io_page_size)
        else:
            offset = fmt.align_up(position, self.chunk_alignment)
            seitenende = fmt.align_up(offset + 1, self.io_page_size)
            if offset + gespeichert > seitenende:
                offset = fmt.align_up(offset, self.io_page_size)
        flags = 0
        if gespeichert <= self.io_page_size:
            if offset // self.io_page_size == (offset + gespeichert - 1) // self.io_page_size:
                flags |= fmt.CHUNK_FLAG_PAGE_CONTAINED
        if offset % self.io_page_size == 0:
            flags |= fmt.CHUNK_FLAG_PAGE_ALIGNED
        return offset, flags

    def passt(self, gespeichert: int, layout: str, extent_start: bool) -> bool:
        offset, _f = self.platz(gespeichert, layout, extent_start)
        ende = self.fmt.align_up(offset + gespeichert, self.io_page_size)
        return self.max_pack_size <= 0 or ende <= self.max_pack_size

    def schreiben(self, gespeichert: int, layout: str, extent_start: bool) -> "tuple[int, int, int]":
        """``(Offset, Auffuellung davor, Platzierungsflags)``; die Bytes selbst liefert der Strom."""
        offset, flags = self.platz(gespeichert, layout, extent_start)
        auffuellung = offset - self.position
        self.position = offset + gespeichert
        return offset, auffuellung, flags

    def endgroesse(self) -> int:
        return self.fmt.align_up(self.position, self.io_page_size)


@dataclass
class Ergebnis:
    """Zahlen eines Packlaufs (wie ``BuildStats`` des Werkzeugs, soweit sie hier etwas bedeuten)."""

    dateien: int = 0
    lose: int = 0
    chunks: int = 0
    lz4_chunks: int = 0
    rohe_chunks: int = 0
    geteilte_chunks: int = 0
    roh_bytes: int = 0
    gespeichert_bytes: int = 0
    baender: int = 0


class _Plan:
    """Fuehrt Manifest, Chunk-Liste und Baender nach - der Rechenteil von ``build_packs``."""

    def __init__(self, auswahl: Lz4Auswahl) -> None:
        _pack, fmt = _werkzeug()
        self.fmt = fmt
        self.config = auswahl.config
        self.gruppe = self.config.groups[auswahl.gruppe]
        self.punkte = auswahl.punkte
        self.strings = fmt.StringTable()
        self.dateien = bytearray()
        self.chunks = bytearray()
        self.crcs = array("I")
        self.stored_crcs = array("I")
        self.dedupe: "dict[tuple, tuple]" = {}
        self.baender: "list[_Band]" = []
        self.band: "_Band | None" = None
        self.ergebnis = Ergebnis()
        self.naechster = 0                      # Index in ``punkte``: der naechste noch nicht eingetragene Punkt
        self.aktuell: "_Punkt | None" = None
        self.erster_chunk = 0
        self.datei_chunks = 0
        self.chunk_index = 0
        self.namen: "set[str]" = set()
        self.laufzeit_bisher: "dict[str, int] | None" = None
        self.laufzeit_werte: "dict[str, int] | None" = None

    # -- Dateien ----------------------------------------------------------------------------------------------------------
    def _lose_bis(self, nummer: int) -> None:
        fmt = self.fmt
        while self.naechster < len(self.punkte) and self.punkte[self.naechster].nummer < nummer:
            punkt = self.punkte[self.naechster]
            if punkt.gepackt:
                raise Lz4PackFehler("Reihenfolge der gepackten Dateien weicht vom Index ab")
            self.naechster += 1
            pfad = fmt.canonical_asset_path(punkt.eintrag.path)
            offset, laenge = self.strings.add(pfad)
            self.dateien += fmt.FileRecord(
                path_hash=fmt.asset_path_hash(pfad), logical_size=punkt.eintrag.size, mtime=punkt.eintrag.mtime, first_chunk=0,
                chunk_count=0, path_offset=offset, path_length=laenge, flags=0, block_shift=0).pack()
            self.ergebnis.lose += 1

    def datei_beginnt(self, punkt: _Punkt) -> None:
        fmt = self.fmt
        self._lose_bis(punkt.nummer)
        if self.naechster >= len(self.punkte) or self.punkte[self.naechster].nummer != punkt.nummer:
            raise Lz4PackFehler("Reihenfolge der gepackten Dateien weicht vom Index ab")
        self.naechster += 1
        self.aktuell = punkt
        pfad = fmt.canonical_asset_path(punkt.eintrag.path)
        self.pfad_offset, self.pfad_laenge = self.strings.add(pfad)
        self.pfad_hash = fmt.asset_path_hash(pfad)
        self.erster_chunk = len(self.chunks) // CHUNK_EINTRAG
        if self.erster_chunk > 0xFFFFFFFF:
            raise Lz4PackFehler("Chunkzahl ueberschreitet die Grenze des Formats")
        self.datei_chunks = 0
        self.chunk_index = 0

    def datei_endet(self) -> None:
        fmt = self.fmt
        punkt = self.aktuell
        assert punkt is not None
        regel = punkt.regel
        flags = fmt.FILE_FLAG_PACKED
        if regel.action == "store":
            flags |= fmt.FILE_FLAG_STORE_ONLY
        layout = regel.resolved_layout()
        if layout == "streaming":
            flags |= fmt.FILE_FLAG_STREAMING
        elif layout == "random":
            flags |= fmt.FILE_FLAG_RANDOM_ACCESS
        if regel.hot:
            flags |= fmt.FILE_FLAG_HOT
        self.dateien += fmt.FileRecord(
            path_hash=self.pfad_hash, logical_size=punkt.groesse,
            mtime=punkt.mtime if self.config.preserve_mtime else punkt.eintrag.mtime, first_chunk=self.erster_chunk,
            chunk_count=self.datei_chunks, path_offset=self.pfad_offset, path_length=self.pfad_laenge, flags=flags,
            block_shift=regel.block_shift, packing_class=sorted(self.config.groups).index(regel.group)).pack()
        self.ergebnis.dateien += 1
        self.aktuell = None

    # -- Chunks -----------------------------------------------------------------------------------------------------------
    def _neues_band(self) -> _Band:
        fmt = self.fmt
        pack_id = len(self.baender)
        if pack_id > 0xFFFF:
            raise Lz4PackFehler("Zahl der Baender ueberschreitet das Format")
        nummer = pack_id                                    # eine Spur: Bandnummer in der Gruppe = pack_id
        try:
            name = self.config.pack_pattern.format(group=self.gruppe.name, lane=0, volume=nummer, id=pack_id)
        except (KeyError, ValueError) as exc:
            raise Lz4PackFehler("pack_pattern unbrauchbar: %r" % self.config.pack_pattern) from exc
        name = name.replace("\\", "/")
        if len(name.encode("utf-8")) > 1017:
            raise Lz4PackFehler("pack_pattern ergibt einen zu langen Namen")
        if name in self.namen:
            raise Lz4PackFehler("pack_pattern ergibt einen Namen doppelt: %s" % name)
        self.namen.add(name)
        band = _Band(fmt, pack_id, name, config=self.config, gruppe=self.gruppe)
        self.baender.append(band)
        self.band = band
        return band

    def chunk(self, block: Any) -> "tuple[bool, _Band | None, int, bool]":
        """Traegt einen Chunk der laufenden Datei ein.

        Returns:
            ``(geschrieben, Band, Auffuellung, neues_Band)`` - ``Band`` nur, wenn Bytes ins Band gehen (nicht bei einem geteilten Chunk).
        """
        fmt = self.fmt
        punkt = self.aktuell
        assert punkt is not None
        regel = punkt.regel
        layout = regel.resolved_layout()
        domain = self.gruppe.name if self.config.deduplicate_scope == "group" else "%s:0" % self.gruppe.name
        physisch = "dense" if layout == "streaming" else "isolated"
        schluessel = (domain, physisch, block.codec, block.raw_fingerprint)
        teilen = self.config.deduplicate and (layout != "streaming" or self.config.deduplicate_streaming)
        vorher = self.dedupe.get(schluessel) if teilen else None
        if vorher is not None:
            offset, gespeichert, pack_id, codec, vflags = vorher
            flags = (fmt.CHUNK_FLAG_SHARED | (vflags & (fmt.CHUNK_FLAG_PAGE_CONTAINED | fmt.CHUNK_FLAG_PAGE_ALIGNED))
                     | (fmt.CHUNK_FLAG_STREAMING if layout == "streaming" else 0))
            satz = fmt.ChunkRecord(offset=offset, stored_size=gespeichert, raw_size=len(block.raw), pack_id=pack_id,
                                   codec=codec, flags=flags)
            band, auffuellung, neu, geschrieben = None, 0, False, False
            self.ergebnis.geteilte_chunks += 1
        else:
            gespeichert = len(block.stored)
            extent_start = layout == "streaming" and self.chunk_index == 0
            band = self.band
            neu = False
            if band is None:
                band, neu = self._neues_band(), True
            if not band.passt(gespeichert, layout, extent_start):
                band, neu = self._neues_band(), True
                if not band.passt(gespeichert, layout, True):
                    raise Lz4PackFehler("ein Block (%d Bytes) ist groesser als max_pack_size der Gruppe %s"
                                        % (gespeichert, self.gruppe.name))
            offset, auffuellung, platzflags = band.schreiben(gespeichert, layout, extent_start)
            flags = (fmt.CHUNK_FLAG_STREAMING if layout == "streaming" else 0) | platzflags
            sicher = (bool(platzflags & fmt.CHUNK_FLAG_PAGE_CONTAINED) if gespeichert <= band.io_page_size
                      else bool(platzflags & fmt.CHUNK_FLAG_PAGE_ALIGNED))
            if layout != "streaming" and not sicher:
                raise Lz4PackFehler("ein Chunk wurde nicht seitensicher platziert")
            satz = fmt.ChunkRecord(offset=offset, stored_size=gespeichert, raw_size=len(block.raw), pack_id=band.pack_id,
                                   codec=block.codec, flags=flags)
            if teilen:
                self.dedupe[schluessel] = (offset, gespeichert, band.pack_id, block.codec, flags)
            self.ergebnis.gespeichert_bytes += gespeichert
            self.stored_crcs.append(block.stored_crc)
            geschrieben = True
        self.chunks += satz.pack()
        self.crcs.append(block.raw_crc)
        self.chunk_index += 1
        self.datei_chunks += 1
        self.ergebnis.chunks += 1
        self.ergebnis.roh_bytes += len(block.raw)
        if satz.codec == fmt.CHUNK_CODEC_LZ4:
            self.ergebnis.lz4_chunks += 1
        else:
            self.ergebnis.rohe_chunks += 1
        return geschrieben, band, auffuellung, neu

    # -- Ende -------------------------------------------------------------------------------------------------------------
    def ende(self, einpassen: "Callable[[int, dict[str, int]], dict[str, int]] | None" = None
             ) -> "tuple[bytes, bytes, bytes | None, bytes]":
        """Schliesst die Eintraege ab: ``(Manifest, Pruefsummenbeilage, Laufzeitprofil oder None, Build-ID)``.

        ``einpassen(manifest_bytes, werte)`` liefert die Laufzeitwerte, die in den Speicherblock passen (oder wirft)."""
        fmt = self.fmt
        pack_modul, _f = _werkzeug()
        self._lose_bis(1 << 60)
        provisorisch = bytearray()
        for band in self.baender:
            name_offset, name_laenge = self.strings.add(band.name)
            provisorisch += fmt.PackRecord(
                payload_bytes=band.endgroesse() - band.payload_offset, file_size=band.endgroesse(), name_offset=name_offset,
                name_length=name_laenge, flags=band.flags, io_page_size=band.io_page_size).pack()
        if len(self.chunks) // CHUNK_EINTRAG > 0xFFFFFFFF:
            raise Lz4PackFehler("Chunkzahl ueberschreitet die Grenze des Formats")
        crc_nutzlast = fmt.encode_chunk_crcs(self.crcs)
        build_id = fmt.deterministic_build_id((
            pack_modul._canonical_config_bytes(self.config), bytes(self.dateien), bytes(self.chunks), crc_nutzlast,
            bytes(provisorisch), self.strings.bytes()))
        manifest = self._manifest(build_id, bytes(provisorisch))
        crc_datei = fmt.build_chunk_crc_header(build_id, len(self.crcs), fmt.crc32(crc_nutzlast)) + crc_nutzlast
        laufzeit = None
        if self.config.runtime is not None:
            vorgabe = {"decoded_cache_bytes": self.config.runtime.decoded_cache_bytes,
                       "physical_cache_bytes": self.config.runtime.physical_cache_bytes,
                       "workers": self.config.runtime.workers,
                       "latency_reserve_workers": self.config.runtime.latency_reserve_workers}
        else:
            vorgabe = dict(ap.LAUFZEIT_VORGABE)             # kein [runtime]: so rechnet auch der Weg ueber den Ordner
        werte = dict(vorgabe)
        self.laufzeit_bisher = dict(vorgabe)
        if einpassen is not None:
            werte = einpassen(len(manifest), werte)
        self.laufzeit_werte = dict(werte)
        # Ohne [runtime] gibt es nur dann ein Laufzeitprofil, wenn die Caches in den Speicherblock gekuerzt werden mussten.
        if self.config.runtime is not None or werte != vorgabe:
            laufzeit = fmt.RuntimeSettings(**{k: int(v) for k, v in werte.items()}).encode(build_id)
        self.ergebnis.baender = len(self.baender)
        return manifest, crc_datei, laufzeit, build_id

    def _manifest(self, build_id: bytes, packs: bytes) -> bytes:
        fmt = self.fmt
        strings = self.strings.bytes()
        anzahl_dateien = len(self.dateien) // fmt.FILE_RECORD.size
        anzahl_chunks = len(self.chunks) // CHUNK_EINTRAG
        anzahl_baender = len(packs) // fmt.PACK_RECORD.size
        if anzahl_dateien > 0xFFFFFFFE or anzahl_baender > 0xFFFF or len(strings) > 0xFFFFFFFF:
            raise Lz4PackFehler("Manifest ueberschreitet die Grenzen des Formats")
        dateien_off = fmt.INDEX_HEADER_SIZE
        chunks_off = dateien_off + len(self.dateien)
        packs_off = chunks_off + len(self.chunks)
        strings_off = packs_off + len(packs)
        nutzlast = bytes(self.dateien) + bytes(self.chunks) + packs + strings
        kopf = fmt.build_manifest_header(
            flags=0, build_id=build_id, file_count=anzahl_dateien, chunk_count=anzahl_chunks, pack_count=anzahl_baender,
            files_offset=dateien_off, chunks_offset=chunks_off, packs_offset=packs_off, strings_offset=strings_off,
            strings_size=len(strings), payload_crc=fmt.crc32(nutzlast))
        return kopf + nutzlast

    def bandkopf(self, band: _Band, build_id: bytes, endgroesse: int) -> bytes:
        """Kopf und Auffuellung bis zum Beginn der Nutzdaten (``payload_offset``)."""
        fmt = self.fmt
        kopf = fmt.build_data_header(band.pack_id, build_id, band.payload_offset, endgroesse - band.payload_offset, band.flags)
        return kopf + b"\0" * (band.payload_offset - len(kopf))


# ---------------------------------------------------------------------------------------------------------------------------
# Lesen und Verdichten
# ---------------------------------------------------------------------------------------------------------------------------
def _folge(auswahl: Lz4Auswahl, dateien: "dict[str, Any]", arbeiter: int, abbruch: Callable[[], bool]) -> "Iterator[tuple]":
    """Liest die gepackten Dateien in Indexordnung, verdichtet auf mehreren Faeden und liefert in derselben Ordnung:

    * ``("datei", punkt)`` - die Datei beginnt,
    * ``("block", CompressedBlock)`` - ein Chunk,
    * ``("ende", punkt)`` - die Datei ist zu Ende.

    Die Platte liest voraus (``_Vorlauf``), waehrend die Faeden verdichten; das Ergebnis haengt nicht von den Faeden ab.
    """
    pack_modul, fmt = _werkzeug()
    codec = fmt.Lz4Codec()
    gruppe = auswahl.config.groups[auswahl.gruppe]
    io_seite = gruppe.io_page_size or auswahl.config.io_page_size
    arbeiter = z._arbeiterzahl(arbeiter)

    def lesen() -> Iterator[tuple]:
        for punkt in auswahl.punkte:
            if not punkt.gepackt:
                continue
            datei = dateien.get(punkt.rel)
            if datei is None or datei.groesse != punkt.groesse:
                raise Lz4PackFehler("%s hat sich waehrend des Packens veraendert" % punkt.rel)
            block = 1 << punkt.regel.block_shift
            yield ("datei", punkt, None)
            puffer = bytearray()
            try:
                for stueck in datei.lesen(LESE_STUECK):
                    puffer += stueck
                    while len(puffer) >= block:
                        yield ("roh", punkt, bytes(puffer[:block]))
                        del puffer[:block]
                if puffer:
                    yield ("roh", punkt, bytes(puffer))
            except BaumFehler as exc:
                raise Lz4PackFehler(str(exc)) from exc
            yield ("ende", punkt, None)

    def verdichten(roh: bytes, regel: Any) -> Any:
        return pack_modul._compress_block(codec, roh, regel, io_seite)

    fenster = arbeiter * 4
    ausstehend: "deque" = deque()

    def liefern(bis: int) -> Iterator[tuple]:
        while len(ausstehend) > bis:
            art, punkt, zukunft = ausstehend.popleft()
            if art == "block":
                yield ("block", zukunft.result())
            else:
                yield (art, punkt)

    with concurrent.futures.ThreadPoolExecutor(max_workers=arbeiter) as pool:
        vorlauf = z._Vorlauf(lesen())
        try:
            for art, punkt, roh in vorlauf:
                if abbruch():
                    raise Lz4PackFehler("ampr_pack.abgebrochen")
                if art == "roh":
                    ausstehend.append(("block", punkt, pool.submit(verdichten, roh, punkt.regel)))
                else:
                    ausstehend.append((art, punkt, None))
                yield from liefern(fenster)
            yield from liefern(0)
        finally:
            vorlauf.schliessen()


# ---------------------------------------------------------------------------------------------------------------------------
# Messen und Strom
# ---------------------------------------------------------------------------------------------------------------------------
@dataclass
class Messung:
    """Alles, was der Schreibdurchgang vorab braucht - ohne dass ein Byte eines Bandes gespeichert wurde."""

    build_id: bytes
    #: ``(Pfad, Groesse)`` der gepackten Dateien in Indexordnung.
    eintraege: "list[tuple[str, int]]"
    chunk_saetze: bytes
    roh_summen: "array[int]"
    gespeicherte_summen: "array[int]"
    #: ``(Name, Groesse)`` jedes Bandes.
    baender: "list[tuple[str, int]]"
    manifest: bytes
    pruefsummen: bytes
    laufzeit: "bytes | None"
    ergebnis: Ergebnis
    #: Der Packer, zu dem die Messung gehoert (``abbild_strom`` ruft ``messung.modul.strom``).
    modul: Any = None
    #: Die Laufzeitwerte des Profils und die, die nach dem Einpassen in den Speicherblock gelten (``None`` ohne ``[runtime]``).
    laufzeit_bisher: "dict[str, int] | None" = None
    laufzeit_werte: "dict[str, int] | None" = None
    #: Dateien, die Auto-Loose lose gelassen haette (der Strom packt sie).
    auto_loose_uebergangen: int = 0

    def dateien(self) -> "list[tuple[str, int]]":
        """``(Name, Groesse)`` der Dateien des Schreibdurchgangs in der Reihenfolge, in der ein Abbild sie anfordert (Namensordnung)."""
        beilagen = [(MANIFEST, len(self.manifest)), (CRC_NAME, len(self.pruefsummen))]
        if self.laufzeit is not None:
            beilagen.append((PROFIL_NAME, len(self.laufzeit)))
        return list(self.baender) + beilagen

    @property
    def gesamtgroesse(self) -> int:
        return sum(g for _n, g in self.dateien())


def _pruefen_vorab(auswahl: Lz4Auswahl) -> None:
    if not auswahl.gepackt:
        raise Lz4PackFehler("ampr_zstd.nichts_zu_packen")
    if auswahl.config is None:
        raise Lz4PackFehler("kein Profil")


def messen(baum: Any, auswahl: Lz4Auswahl, *, arbeiter: int = 0, abbruch: Callable[[], bool] = lambda: False,
           fortschritt: "Callable[[float], None] | None" = None,
           einpassen: "Callable[[int, int, dict[str, int]], dict[str, int] | None] | None" = None) -> Messung:
    """Messdurchgang: verdichtet alles und behaelt nur, was der Schreibdurchgang braucht. Nichts wird gespeichert.

    ``einpassen(manifest_bytes, index_bytes, werte)`` darf die Laufzeitwerte verkleinern (``ampr_assetpakete.laufzeit_einpassen``);
    ``None`` als Antwort ist :class:`Lz4SpeicherZuKlein`. ``index_bytes`` ist die Groesse des ``ampr_emu.index``.
    """
    _pruefen_vorab(auswahl)
    plan = _Plan(auswahl)
    folge = _folge(auswahl, baum.suchen(), arbeiter, abbruch)
    gesamt = max(1, sum(g for _p, g in auswahl.gepackt))
    erledigt = 0
    try:
        for art, wert in folge:
            if art == "datei":
                plan.datei_beginnt(wert)
            elif art == "block":
                plan.chunk(wert)
                erledigt += len(wert.raw)
                if fortschritt is not None:
                    fortschritt(min(1.0, erledigt / gesamt))
            else:
                plan.datei_endet()
    finally:
        folge.close()

    def anpassen(manifest_bytes: int, werte: "dict[str, int]") -> "dict[str, int]":
        passend = einpassen(manifest_bytes, auswahl.index_bytes, werte)           # type: ignore[misc]
        if passend is None:
            raise Lz4SpeicherZuKlein(manifest_bytes, auswahl.index_bytes, werte)
        return passend

    manifest, pruefsummen, laufzeit, build_id = plan.ende(anpassen if einpassen is not None else None)
    baender = [(b.name, b.endgroesse()) for b in plan.baender]
    messung = Messung(build_id=build_id, eintraege=list(auswahl.gepackt), chunk_saetze=bytes(plan.chunks), roh_summen=plan.crcs,
                      gespeicherte_summen=plan.stored_crcs, baender=baender, manifest=manifest, pruefsummen=pruefsummen,
                      laufzeit=laufzeit, ergebnis=plan.ergebnis, modul=sys.modules[__name__],
                      laufzeit_bisher=plan.laufzeit_bisher, laufzeit_werte=plan.laufzeit_werte,
                      auto_loose_uebergangen=auswahl.auto_loose_uebergangen)
    # Die Baender muessen in Namensordnung entstehen: Ein Abbild fordert sie so an, und der Strom kann nur vorwaerts.
    namen = [n for n, _g in baender]
    if namen != sorted(namen, key=str.lower):
        raise Lz4NichtImStrom("die Baender entstehen nicht in der Reihenfolge ihrer Namen (pack_pattern)")
    return messung


def stichprobe_chunks(messung: Messung, startwert: int) -> "tuple[frozenset[int], int]":
    """Welche Chunks die schnelle Pruefung im Strom entpackt: ``(Chunknummern, Bytes)`` - das erste, das letzte und etwa 1 % zufaellige."""
    anzahl = len(messung.chunk_saetze) // CHUNK_EINTRAG
    if anzahl <= 0:
        return frozenset(), 0
    gewaehlt = {0, anzahl - 1}
    wunsch = min(anzahl, max(1, int(anzahl * STICHPROBE_ANTEIL)), STICHPROBE_MAX_CHUNKS)
    zufall = random.Random(startwert)
    while len(gewaehlt) < min(anzahl, wunsch + 2):
        gewaehlt.add(zufall.randrange(anzahl))
    je_chunk = max(1, messung.ergebnis.roh_bytes // anzahl)
    return frozenset(gewaehlt), len(gewaehlt) * je_chunk


def strom(baum: Any, auswahl: Lz4Auswahl, messung: Messung, *, arbeiter: int = 0, abbruch: Callable[[], bool] = lambda: False,
          fortschritt: "Callable[[float], None] | None" = None,
          pruefen: "bool | frozenset[int] | set[int] | None" = None) -> "Iterator[tuple[str, bytes]]":
    """Schreibdurchgang: verdichtet noch einmal und liefert ``(Dateiname, Bytes)`` in der Reihenfolge von ``messung.dateien()``.

    Aufeinanderfolgende Stuecke mit demselben Namen gehoeren zu einer Datei. Jeder Chunk wird gegen die Messung gehalten (Lage,
    Groesse, Pruefsumme der Quelle und des gespeicherten Chunks): Hat sich die Quelle zwischen den Durchgaengen geaendert oder
    verdichtet die Bibliothek nicht reproduzierbar, bricht der Durchgang ab, ehe ein falsches Pack abgeliefert ist.
    ``pruefen``: ``True`` entpackt jeden Chunk und vergleicht mit der Pruefsumme der Quelle, eine Menge von Chunknummern nur
    diese (:func:`stichprobe_chunks`).
    """
    _pruefen_vorab(auswahl)
    _pack, fmt = _werkzeug()
    plan = _Plan(auswahl)
    if list(auswahl.gepackt) != messung.eintraege:
        raise Lz4PackFehler("Dateiliste weicht von der Messung ab")
    endgroessen = dict(messung.baender)
    codec = fmt.Lz4Codec()
    folge = _folge(auswahl, baum.suchen(), arbeiter, abbruch)
    gesamt = max(1, sum(g for _p, g in auswahl.gepackt))
    erledigt = 0
    nr = 0                                   # laufende Chunknummer
    geschrieben_nr = 0                       # laufende Nummer unter den ins Band geschriebenen Chunks
    aktuelles: "_Band | None" = None
    aktuelles_position = 0
    try:
        for art, wert in folge:
            if art == "datei":
                plan.datei_beginnt(wert)
                continue
            if art == "ende":
                plan.datei_endet()
                continue
            block = wert
            geschrieben, band, auffuellung, neu = plan.chunk(block)
            stelle = nr * CHUNK_EINTRAG
            if (stelle + CHUNK_EINTRAG > len(messung.chunk_saetze)
                    or plan.chunks[stelle:stelle + CHUNK_EINTRAG] != messung.chunk_saetze[stelle:stelle + CHUNK_EINTRAG]
                    or block.raw_crc != messung.roh_summen[nr]):
                raise Lz4PackFehler("Schreibdurchgang weicht vom Messdurchgang ab (Chunk %d): die Quelle hat sich geaendert, "
                                    "oder die Verdichtung ist nicht reproduzierbar" % nr)
            if geschrieben and block.stored_crc != messung.gespeicherte_summen[geschrieben_nr]:
                raise Lz4PackFehler("Schreibdurchgang weicht vom Messdurchgang ab (Chunk %d): der verdichtete Chunk ist ein "
                                    "anderer" % nr)
            if pruefen is True or (pruefen and nr in pruefen):
                if block.codec == fmt.CHUNK_CODEC_LZ4:
                    entpackt = codec.decompress(block.stored, len(block.raw))
                else:
                    entpackt = block.stored
                if fmt.crc32(entpackt) != block.raw_crc:
                    raise Lz4PackFehler("ampr_zstd.inhalt_anders: Chunk %d" % nr)
            nr += 1
            if geschrieben:
                geschrieben_nr += 1
                if neu:
                    if aktuelles is not None:
                        yield aktuelles.name, b"\0" * (endgroessen[aktuelles.name] - aktuelles_position)
                    aktuelles = band
                    yield band.name, plan.bandkopf(band, messung.build_id, endgroessen[band.name])
                    aktuelles_position = band.payload_offset
                if auffuellung:
                    yield band.name, b"\0" * auffuellung
                yield band.name, block.stored
                aktuelles_position = aktuelles_position + auffuellung + len(block.stored)
            erledigt += len(block.raw)
            if fortschritt is not None:
                fortschritt(min(1.0, erledigt / gesamt))
    finally:
        folge.close()
    if aktuelles is not None:
        yield aktuelles.name, b"\0" * (endgroessen[aktuelles.name] - aktuelles_position)
    manifest, pruefsummen, _laufzeit, build_id = plan.ende(lambda _m, w: dict(w))
    if (nr * CHUNK_EINTRAG != len(messung.chunk_saetze) or [(b.name, b.endgroesse()) for b in plan.baender] != messung.baender
            or build_id != messung.build_id or manifest != messung.manifest or pruefsummen != messung.pruefsummen):
        raise Lz4PackFehler("Schreibdurchgang weicht vom Messdurchgang ab (Baender oder Manifest)")
    yield MANIFEST, messung.manifest
    yield CRC_NAME, messung.pruefsummen
    if messung.laufzeit is not None:
        yield PROFIL_NAME, messung.laufzeit
