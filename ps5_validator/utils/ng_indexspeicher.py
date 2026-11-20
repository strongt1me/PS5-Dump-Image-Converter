# -*- coding: utf-8 -*-
"""Wie viel Indexspeicher ampr-emu-ng (NG) fuer ein Spiel braucht - und ob er reicht.

NG haelt den ``ampr_emu.index`` (AMPRIDX3), das Pack-Manifest (LZ4: ``ampr_assets.index``, AMPRPAK4; zstd: ``ampr_zstd.index``,
AMPRZPK1) und die daraus gebauten Tabellen in einem festen Speicherblock. Reicht er nicht, laesst NG die Packs ungenutzt - die
gepackten Dateien fehlen dem Spiel (ENOENT), nach einer einzigen Meldung an der Konsole (``rt/index_memory.rs``). Ohne Pack bleibt
der Index aus, und NG bedient das Spiel nicht.

Nachgebaut aus dem Quelltext von ampr-emu-ng (gelesen am 14.11.2026; nur Rechnung, an der Konsole nicht gemessen):

* **0.3.5** (``rt/index_memory.rs`` dieser Marke): ein Block von 55 MiB (``INDEX_MEMORY_MAX``; die 52 + 3 MiB im Kommentar sind
  nur die Aufteilung, geprueft wird die Summe, ``Ledger::new(INDEX_MEMORY_MAX)``). Erst der ``ampr_emu.index``, dann das
  Manifest, dann die Tabellen: zstd 16 B je AMPRIDX3-Eintrag (Projektion) und 4 B je gepackter Datei (Ordnung), LZ4 4 B je
  gepackter Datei (Ordnerordnung). Kein seitenweises Lesen.
* **0.4.0 und die beta** (``rt/index_memory.rs``, ``rt/index_pages.rs``, ``rt/index.rs``, ``rt/pack/manifest.rs``,
  ``rt/pack/zstd.rs``): alles zusammen hoechstens 64 MiB (``INDEX_MEMORY_MAX``), davon Nachschlagetabellen hoechstens 48 MiB
  (``INDEX_LOOKUP_MAX``). Eine Indexdatei wird ganz gelesen, wenn sie samt den Tabellen, die sie noch braucht, in den freien Platz
  passt; sonst seitenweise - dann nimmt der Seitenspeicher beim ersten Mal 16 MiB (``INDEX_ARENA_MIN``), je 16-KiB-Seite 2 B
  Seitentabelle, und die Datei bekommt eine Schnelltabelle. Der ``ampr_emu.index`` wird zuerst geladen, ohne Ruecksicht auf das
  Manifest. Ein Pack-Index ueber 512 MiB wird abgelehnt (``AMPR_EMU_PACK_INDEX_MAX_BYTES``).
* **Vor 0.3.5** gab es diesen Block nicht (Speicher anderer Art) - dafuer keine Aussage.

Die Ladefolge wird Schritt fuer Schritt nachgerechnet (:func:`pruefen`); jede Belegung wird wie in NG auf 16-KiB-Seiten gerundet.
``Befund.benoetigt``/``grenze`` rechnen wie die Meldung an der Konsole ("index needs X MiB, over the Y MiB ..."): belegter Block
ohne Seitenspeicher plus die abgelehnte Anforderung, gegen den Block ohne Seitenspeicher (``index_refused``).

* **beta ab 54d6ac2** (14.11.2026 17:34 UTC, "Page an unsorted ampr_emu.index and size it against the pack index"): wie 0.4.0,
  aber der ``ampr_emu.index`` wird nur noch ganz gelesen, wenn daneben das, was das Manifest mindestens braucht, frei bleibt
  (``pack_index_reserve``: das Kleinere aus "ganz samt Tabellen" und "Schnelltabelle + Tabellen + 16 MiB Seitenspeicher", je auf
  Seiten gerundet); sonst seitenweise. Ein unsortierter, seitenweise gelesener Index bekaeme dort noch eine Rangtabelle (4 B je
  Eintrag) - der Index dieses Programms ist sortiert, das ist nicht nachgebaut.
* **0.4.1 und neuer** (Freigabe vom 15.11.2026, Marke auf 8b61a06; gelesen an ``rt/index_memory.rs``, ``rt/index_view.rs``,
  ``ampr-format/src/view.rs``, ``rt/index.rs``, ``rt/pack/zstd.rs``, ``rt/pack/manifest.rs``): Der Index wird nicht mehr seitenweise
  gelesen, und die 48-MiB-Grenze fuer Tabellen entfaellt. Alles zusammen liegt in einem Block von 80 MiB (``INDEX_MEMORY_MAX``).
  Der ``ampr_emu.index`` wird einmal sequenziell durch zwei 64-KiB-Fenster gelesen und in eine **kompilierte Ansicht** gebaut: ein
  Hauptblock mit je Datei 24 B Spalten (Hash, Groesse, Zeit), 4 B ``path_at``, bei Packs 4 B ``next`` (zstd dazu 4 B ``chunk``) und
  4 B je Hash-Platz (Platzzahl = naechste Zweierpotenz ueber 1,5 x Dateien), je Ordner 32 B (Ordnerzahl vorab ``Dateien / 8 + 1024``,
  bei Bedarf verdoppelt) samt Ordner-Hashplaetzen und 1 KiB ``collide``, dazu ein **Zwischenblock** ``dir_of`` (4 B je Datei, LZ4 +
  8 B ``lz4_hash``), der erst nach dem Zusammenfuegen mit dem Pack frei wird. Das Pack wird danach eingehaengt: zstd haelt Chunk-
  und Bandtabellen (8 B je Chunk und Band, ``table_bytes``) und prueft vorab Tabellen plus zwei Fenster gegen den freien Platz; LZ4
  haelt 128 B Kopf, 48 B je Datei, 12 B je Chunk und je Pack 32 B Satz + Name + 16 B Spanne (``read_resident``), danach eine
  Abgleich-Bitmap von (Dateien + 1) / 8 B. Jede Belegung wird auf 16-KiB-Seiten gerundet. Die Rechnung trifft die eigenen Zahlen
  der Entwickler (Kommentar in ``index_memory.rs``: 12,6 / 14,9 / 16,0 MiB Ansicht bei 300.000 Dateien ohne Pack / zstd / LZ4;
  21,74 MiB Ansicht plus Tabellen bei 242.409 zstd-Dateien; 27,5 MiB LZ4-Manifest bei 223.180 Dateien; ``tests/test_ng_indexspeicher.py``).
  Gemessen an der Konsole hat das niemand (die Entwickler: "no console run has measured it").
* **0.5.0 und neuer** (Freigabe vom 20.11.2026, Marke auf d20210e; gelesen im Vergleich v0.4.1...v0.5.0 an ``rt/index_memory.rs``,
  ``rt/index_view.rs``, ``ampr-format/src/view.rs``): Der Block bleibt 80 MiB (``INDEX_MEMORY_MAX``), die Ladefolge dieselbe. Neu ist die
  Ansicht: je Datei **eine 32-Byte-Zeile** (``view::Row``: Hash, Groesse, Zeit, ``path_at``, ``next``; auf 32 ausgerichtet, damit sie in
  einer Cache-Zeile liegt) statt vier Spalten. Das kostet **4 B je Datei ohne Pack** (vorher 28 B) und nichts mit Pack (``next`` war
  dort schon eine eigene Spalte: 24 + 4 + 4); die zstd-Spalte ``chunk`` (4 B) bleibt eine eigene. Die Ordnerzahl wird beim Aufbau nicht
  mehr verdoppelt, sondern nach dem fehlgeschlagenen Versuch genau uebernommen (``view::build_sized``). Die Zahlen der Entwickler
  (``index_view.rs view_bytes_at_300k_files``: 14.055 / 15.227 / 16.399 KiB Spitze ohne Pack / zstd / LZ4 bei 300.000 Dateien) trifft die
  Rechnung (``tests/test_ng_indexspeicher.py``). Der Cache waechst nach dem Laden in den freien Indexspeicher - er nimmt dem Index nichts
  weg, was er braucht (``INDEX_KEPT_ROOM`` 2 MiB), darum aendert das die Pruefung nicht. An der Konsole nicht gemessen.

Gegengeprueft an den gemeldeten Faellen (Issues #53, #61, #67 von ampr-emu-ng; Zahlen aus den Kommentaren): Demon's Souls (LZ4,
223.180 Dateien, 0.4.0: "need 62MiB, over the 48 MiB") und Final Fantasy XVI (zstd, 0.4.0: "49 MiB against 48"; 0.3.5:
"needs 62 MiB, over the 55 MiB cap") - die Rechnung kommt auf dieselben Zahlen (``tests/test_ng_indexspeicher.py``). Mit der
beta ab 54d6ac2 passen beide nach der Rechnung; an der Konsole ist das nicht gemessen ("Not yet run on a console").
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

MIB = 1 << 20
#: Seitengroesse der Konsole (``SCE_KERNEL_PAGE_SIZE``) und des Seitenspeichers (``index_pages::PAGE``).
SEITE = 16 << 10

# 0.3.5
GRENZE_035 = 55 * MIB
# 0.4.0 / beta
GRENZE_040_GESAMT = 64 * MIB
GRENZE_040_TABELLEN = 48 * MIB
SEITENSPEICHER_040 = 16 * MIB
PACKINDEX_MAX_040 = 512 * MIB
#: Je AMPRIDX3-Eintrag eines seitenweise gelesenen Index: 12 B Schnelltabelle und 20 B Pack-Tabellen (``LOOKUP_PER_FILE``).
AMPRIDX3_JE_DATEI_040 = 12 + 20
AMPRIDX3_SCHNELL_040 = 12

# Kopfzahlen der drei Formate (Stelle im Kopf, siehe ampr-format / ampr-lz4 / ampr-zstd)
_AMPRIDX3 = b"AMPRIDX3"
_AMPRPAK4 = b"AMPRPAK4"
_AMPRZPK1 = b"AMPRZPK1"

# 0.4.1 und neuer (kompilierte Ansicht, ein Block fuer alles)
GRENZE_041 = 80 * MIB
#: Ein Lesefenster (``index_file::WINDOW``); der Index wird immer durch zwei gelesen.
FENSTER_041 = 64 * 1024
#: Kopf, Satz-Abschnitte und Namen eines eingehaengten LZ4-Manifests: 128 B Kopf, je Pack 32 B Satz + ~32 B Name + 16 B Spanne.
LZ4_KOPF = 128
LZ4_JE_PACK = 32 + 32 + 16

MODELL_035 = "0.3.5"
MODELL_040 = "0.4.0"
#: 0.4.0 mit dem Vorbehalt fuer das Manifest (die beta ab 54d6ac2).
MODELL_BETA = "0.4.0-beta"
#: Freigabe 0.4.1: die kompilierte Ansicht im 80-MiB-Block.
MODELL_041 = "0.4.1"
#: Freigabe 0.5.0 und neuer: wie 0.4.1, die Ansicht aber mit einer 32-Byte-Zeile je Datei.
MODELL_050 = "0.5.0"
#: Die neueste NG-Fassung, fuer die eine Rechnung steht (Empfehlung "mit dieser Fassung reicht der Speicher").
NEUESTE_FASSUNG = "0.5.0"


def modell_fuer(fassung: str) -> str:
    """Welches Modell fuer eine NG-Fassung gilt: ``"0.5.0"`` ab 0.5.0, ``"0.4.1"`` fuer 0.4.1 bis 0.4.x, ``"0.4.0-beta"`` fuer die beta
    (der Stand im Bestand ist 54d6ac2), ``"0.4.0"`` fuer die Freigabe 0.4.0, ``"0.3.5"`` fuer 0.3.5, sonst ``""`` (vor 0.3.5: kein Modell)."""
    text = str(fassung or "")
    treffer = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not treffer:
        return ""
    teile = tuple(int(t) for t in treffer.groups())
    if teile >= (0, 5, 0):
        return MODELL_050
    if teile >= (0, 4, 1):
        return MODELL_041
    if teile >= (0, 4, 0) and "beta" in text.lower():
        return MODELL_BETA
    if teile >= (0, 4, 0):
        return MODELL_040
    if teile == (0, 3, 5):
        return MODELL_035
    return ""


@dataclass(frozen=True)
class Kopf:
    """Laenge einer Indexdatei und die Zahlen aus ihrem Kopf."""

    laenge: int
    dateien: int
    chunks: int = 0
    baender: int = 0


def ampridx3_kopf(daten: bytes, laenge: int | None = None) -> Kopf:
    """Kopf eines ``ampr_emu.index`` (``daten`` reicht ab 24 Bytes; ``laenge`` = Dateigroesse, sonst ``len(daten)``)."""
    if len(daten) < 24 or daten[:8] != _AMPRIDX3:
        raise ValueError("kein AMPRIDX3-Kopf")
    return Kopf(laenge if laenge is not None else len(daten), struct.unpack_from("<Q", daten, 16)[0])


def lz4_kopf(daten: bytes, laenge: int | None = None) -> Kopf:
    """Kopf eines ``ampr_assets.index`` (AMPRPAK4): Dateien @40, Chunks @48, Baender @56."""
    if len(daten) < 60 or daten[:8] != _AMPRPAK4:
        raise ValueError("kein AMPRPAK4-Kopf")
    dateien, chunks = struct.unpack_from("<QQ", daten, 40)
    return Kopf(laenge if laenge is not None else len(daten), dateien, chunks, struct.unpack_from("<I", daten, 56)[0])


def zstd_kopf(daten: bytes, laenge: int | None = None) -> Kopf:
    """Kopf eines ``ampr_zstd.index`` (AMPRZPK1): Dateien @40, Chunks @48, Baender @20."""
    if len(daten) < 56 or daten[:8] != _AMPRZPK1:
        raise ValueError("kein AMPRZPK1-Kopf")
    dateien, chunks = struct.unpack_from("<QQ", daten, 40)
    return Kopf(laenge if laenge is not None else len(daten), dateien, chunks, struct.unpack_from("<I", daten, 20)[0])


@dataclass
class Befund:
    """Ob der Indexspeicher reicht. ``engpass``: woran es scheitert (leer, wenn es passt); Zahlen in Bytes."""

    modell: str
    passt: bool
    engpass: str = ""
    benoetigt: int = 0
    grenze: int = 0
    #: Was am Ende belegt waere: ``gesamt`` (Indexblock) und ``tabellen`` (Nachschlagetabellen), dazu je Datei ganz/seitenweise.
    belegt: dict = field(default_factory=dict)


def _rund(n: int) -> int:
    return -(-max(0, n) // SEITE) * SEITE


class _Buch040:
    """Die Buchfuehrung von 0.4.0/beta: ein Block (64 MiB), darin hoechstens 48 MiB Nachschlagetabellen."""

    def __init__(self) -> None:
        self.frei = GRENZE_040_GESAMT
        self.tabellen = 0
        self.seitenspeicher = False
        self.weg: dict = {}

    def nehmen(self, n: int) -> bool:
        n = _rund(n)
        if n > self.frei:
            return False
        self.frei -= n
        return True

    def tabelle(self, n: int) -> bool:
        n = _rund(n)
        if self.tabellen + n > GRENZE_040_TABELLEN or n > self.frei:
            return False
        self.tabellen += n
        self.frei -= n
        return True

    def tabelle_passt(self, n: int) -> bool:
        """Die Vorabpruefung vor einer Schnelltabelle (``attach_fast``): ungerundet, gegen beide Grenzen."""
        return self.tabellen + n <= GRENZE_040_TABELLEN and n <= self.frei

    def seitenweise(self, laenge: int) -> bool:
        if not self.seitenspeicher:
            if not self.nehmen(SEITENSPEICHER_040):
                return False
            self.seitenspeicher = True
        return self.nehmen(-(-laenge // SEITE) * 2)


def _pack_kosten(art: str, pack: Kopf, ampr_ids: int) -> "tuple[int, int]":
    """``(Schnelltabelle, abgeleitete Tabellen)`` eines Manifests (``zstd.rs lookup_bytes`` / ``lz4_lookup_bytes``)."""
    if art == "zstd":
        return (2 * pack.dateien + pack.chunks + pack.baender) * 8, ampr_ids * 16 + min(pack.dateien, ampr_ids) * 4
    return pack.dateien * 48 + pack.chunks * 12 + pack.baender * 32, pack.dateien * 4


def _vorbehalt_beta(art: str, pack: Kopf, ampridx: Kopf) -> int:
    """``pack_index_reserve`` der beta ab 54d6ac2: das Wenigste, was das Manifest nach dem ``ampr_emu.index`` braucht."""
    if art == "zstd":
        # Einhaengen zaehlt einen Eintrag je zstd-Datei, die Projektion danach je AMPRIDX3-Eintrag - das Groessere zaehlt.
        einhaengen = _pack_kosten(art, pack, pack.dateien)
        gebaut = _pack_kosten(art, pack, ampridx.dateien)
        schnell, abgeleitet = max(einhaengen[0], gebaut[0]), max(einhaengen[1], gebaut[1])
    else:
        schnell, abgeleitet = _pack_kosten(art, pack, ampridx.dateien)
    ganz = _rund(pack.laenge) + _rund(abgeleitet)
    seitenweise = _rund(schnell) + _rund(abgeleitet) + SEITENSPEICHER_040
    return min(ganz, seitenweise)


def _pruefen_040(ampridx: Kopf, art: str, pack: Kopf | None, vorbehalt: bool = False) -> Befund:
    modell = MODELL_BETA if vorbehalt else MODELL_040
    buch = _Buch040()

    def belegt() -> dict:
        return {"gesamt": GRENZE_040_GESAMT - buch.frei, "tabellen": buch.tabellen, **buch.weg}

    def kaputt(engpass: str, anforderung: int) -> Befund:
        # Wie die Meldung an der Konsole (index_refused): belegter Block ohne Seitenspeicher plus Anforderung, gegen den Block
        # ohne Seitenspeicher ("over the 48 MiB beside the page cache").
        seiten = SEITENSPEICHER_040 if buch.seitenspeicher else 0
        return Befund(modell, False, engpass, GRENZE_040_GESAMT - buch.frei - seiten + anforderung,
                      GRENZE_040_GESAMT - seiten, belegt())

    # 1. ampr_emu.index (rt/index.rs: read_whole / ab 54d6ac2 whole_fits, sonst register_file + attach_fast)
    if vorbehalt and art and pack is not None:
        ganz = _rund(ampridx.laenge) + _vorbehalt_beta(art, pack, ampridx) <= buch.frei
    else:
        ganz = ampridx.laenge + ampridx.dateien * AMPRIDX3_JE_DATEI_040 <= buch.frei
    if ganz and buch.nehmen(ampridx.laenge):
        buch.weg["ampr_emu.index"] = "ganz"
    else:
        if not buch.seitenweise(ampridx.laenge):
            return kaputt("ampr_emu.index: Seitenspeicher", SEITENSPEICHER_040)
        bedarf = ampridx.dateien * AMPRIDX3_JE_DATEI_040
        if not buch.tabelle_passt(bedarf) or not buch.tabelle(ampridx.dateien * AMPRIDX3_SCHNELL_040):
            return kaputt("ampr_emu.index: Tabellen", bedarf)
        buch.weg["ampr_emu.index"] = "seitenweise"
    if art == "" or pack is None:
        return Befund(modell, True, "", 0, 0, belegt())
    if pack.laenge > PACKINDEX_MAX_040:
        return Befund(modell, False, "Pack-Index ueber 512 MiB", pack.laenge, PACKINDEX_MAX_040, belegt())

    # 2. Pack-Manifest (rt/pack/manifest.rs mount_index_source; zstd.rs / attach_lz4_fast). Beim Einhaengen ist der
    # ampr_emu.index noch nicht veroeffentlicht: zstd zaehlt dann einen Eintrag je zstd-Datei (published_ampr_ids = None).
    schnell, abgeleitet = _pack_kosten(art, pack, pack.dateien if art == "zstd" else ampridx.dateien)
    name = "ampr_zstd.index" if art == "zstd" else "ampr_assets.index"
    if pack.laenge + abgeleitet <= buch.frei and buch.nehmen(pack.laenge):
        buch.weg[name] = "ganz"
    else:
        if not buch.seitenweise(pack.laenge):
            return kaputt(name + ": Seitenspeicher", SEITENSPEICHER_040)
        if not buch.tabelle_passt(schnell + abgeleitet) or not buch.tabelle(schnell):
            return kaputt(name + ": Tabellen", schnell + abgeleitet)
        buch.weg[name] = "seitenweise"
    # 3. Die abgeleiteten Tabellen (zstd: Projektion + Ordnung; LZ4: Ordnerordnung)
    teile = [ampridx.dateien * 16, min(pack.dateien, ampridx.dateien) * 4] if art == "zstd" else [pack.dateien * 4]
    for teil in teile:
        if not buch.tabelle(teil):
            return kaputt(name + ": abgeleitete Tabellen", _rund(teil))
    # Was danach nicht mehr passt (Spielstand-Symbol, kurzlebige Puffer), laesst NG nur weg - kein Grund, die Packs zu verlieren.
    return Befund(modell, True, "", 0, 0, belegt())


def _slots_041(n: int) -> int:
    """``view::slot_count``: die Zweierpotenz ab 1,5 x ``n`` (``n * 3 / 2 + (n & 1)``), mindestens 2."""
    gewollt = max(n * 3 // 2 + (n & 1), 2)
    return 1 << (gewollt - 1).bit_length()


def ansicht_041(dateien: int, art: str = "", ordner: int | None = None) -> "tuple[int, int]":
    """Groesse der kompilierten Ansicht von NG ab 0.4.1 in Bytes, ungerundet: ``(Hauptblock, Zwischenblock)``.

    Nach ``index_view::layout``: Hauptblock = Hash, Groesse, Zeit je 8 B, ``path_at`` 4 B, bei Packs ``next`` 4 B (zstd dazu ``chunk``
    4 B), die Hash-Plaetze der Dateien (4 B je Platz), je Ordner 32 B samt Ordner-Hashplaetzen und 1 KiB ``collide``. Zwischenblock =
    ``dir_of`` (4 B je Datei) und bei LZ4 ``lz4_hash`` (8 B je Datei); er wird nach dem Zusammenfuegen mit dem Pack frei.

    Args:
        dateien: Eintraege des ``ampr_emu.index``.
        art: ``"zstd"``, ``"lz4"`` oder ``""`` (kein Pack).
        ordner: Ordnerzahl, falls bekannt; sonst die erste Schaetzung von NG (``Dateien / 8 + 1024``). NG verdoppelt sie bei Bedarf und
            liest den Index dann nochmal - das ist nicht nachgebaut.
    """
    n = max(int(dateien), 1)
    kappe = int(ordner) if ordner else n // 8 + 1024
    haupt = (24 * n + 32 * kappe + 4 * n + (4 * n if art else 0) + (4 * n if art == "zstd" else 0)
             + 4 * _slots_041(n) + 4 * _slots_041(kappe) + 4 * 256)
    zwischen = 4 * n + (8 * n if art == "lz4" else 0)
    return haupt, zwischen


def ansicht_050(dateien: int, art: str = "", ordner: int | None = None) -> "tuple[int, int]":
    """Groesse der kompilierten Ansicht von NG ab 0.5.0 in Bytes, ungerundet: ``(Hauptblock, Zwischenblock)``.

    Nach ``index_view::layout`` von 0.5.0: Hauptblock = eine 32-Byte-Zeile je Datei (``view::Row``: Hash, Groesse, Zeit, ``path_at``,
    ``next``), bei zstd dazu die Spalte ``chunk`` (4 B je Datei), die Hash-Plaetze der Dateien (4 B je Platz), je Ordner 32 B samt
    Ordner-Hashplaetzen und 1 KiB ``collide``. Der Zwischenblock ist wie bei 0.4.1 (``dir_of`` 4 B je Datei, LZ4 dazu ``lz4_hash`` 8 B).
    Gegenueber 0.4.1: ohne Pack 4 B je Datei mehr, mit Pack gleich viel.

    Args: wie :func:`ansicht_041`.
    """
    n = max(int(dateien), 1)
    kappe = int(ordner) if ordner else n // 8 + 1024
    haupt = (32 * n + 32 * kappe + (4 * n if art == "zstd" else 0)
             + 4 * _slots_041(n) + 4 * _slots_041(kappe) + 4 * 256)
    zwischen = 4 * n + (8 * n if art == "lz4" else 0)
    return haupt, zwischen


class _Buch041:
    """Die Buchfuehrung von 0.4.1: ein Block (80 MiB) fuer alles; jede Belegung wird auf Seiten gerundet, die Spitze gemerkt."""

    def __init__(self) -> None:
        self.benutzt = 0
        self.spitze = 0
        self.weg: dict = {}

    def nehmen(self, n: int) -> bool:
        n = _rund(max(n, 1))
        if n > GRENZE_041 - self.benutzt:
            return False
        self.benutzt += n
        self.spitze = max(self.spitze, self.benutzt)
        return True

    def geben(self, n: int) -> None:
        self.benutzt -= _rund(max(n, 1))

    def frei(self) -> int:
        return GRENZE_041 - self.benutzt


def _pruefen_041(ampridx: Kopf, art: str, pack: Kopf | None, ordner: int | None = None, modell: str = MODELL_041,
                 ansicht=ansicht_041) -> Befund:
    """Die Ladefolge von NG ab 0.4.1 (``rt/index.rs load_file``, ``rt/pack/zstd.rs zstd_mount_join``, ``rt/pack/manifest.rs``).

    Gilt unveraendert auch ab 0.5.0; ``modell`` und ``ansicht`` (:func:`ansicht_041` oder :func:`ansicht_050`) nennen die Fassung."""
    buch = _Buch041()
    mit_pack = bool(art) and pack is not None
    haupt, zwischen = ansicht(ampridx.dateien, art if mit_pack else "", ordner)
    fenster = 2 * FENSTER_041

    def belegt() -> dict:
        return {"gesamt": buch.spitze, "ansicht": haupt, "zwischen": zwischen, **buch.weg}

    def kaputt(engpass: str, anforderung: int) -> Befund:
        # Wie die Meldung an der Konsole ("index needs X MiB, over the 80 MiB cap"): belegter Block plus die abgelehnte Anforderung.
        return Befund(modell, False, engpass, buch.benutzt + anforderung, GRENZE_041, belegt())

    # 1. ampr_emu.index (rt/index.rs load_file): zwei Fenster, dann Hauptblock und Zwischenblock der Ansicht; danach die Fenster frei.
    for teil, bytes_ in (("Fenster", fenster), ("Ansicht", haupt), ("Aufbau", zwischen)):
        if not buch.nehmen(bytes_):
            return kaputt("ampr_emu.index: " + teil, bytes_)
    buch.geben(fenster)
    if not mit_pack:
        buch.geben(zwischen)   # ohne Pack wird die Ansicht gleich fertig (Compact::finish gibt den Zwischenblock zurueck)
        return Befund(modell, True, "", 0, 0, belegt())
    if pack.laenge > PACKINDEX_MAX_040:
        return Befund(modell, False, "Pack-Index ueber 512 MiB", pack.laenge, PACKINDEX_MAX_040, belegt())

    # 2. Pack-Manifest einhaengen und mit der Ansicht verbinden; der Zwischenblock ist dabei noch belegt.
    if art == "zstd":
        tabellen = (pack.chunks + pack.baender) * 8
        # zstd_mount_join: "needed" = Tabellen + zwei Fenster gegen den freien Platz, ungerundet, vor jeder Belegung
        if tabellen + fenster > buch.frei():
            return kaputt("ampr_zstd.index: Tabellen", tabellen + fenster)
        if not (buch.nehmen(fenster) and buch.nehmen(max(tabellen, 8))):
            return kaputt("ampr_zstd.index: Tabellen", tabellen)
        buch.geben(fenster)
        buch.weg["tabellen"] = tabellen
    else:
        ablage = LZ4_KOPF + pack.dateien * 48 + pack.chunks * 12 + pack.baender * LZ4_JE_PACK
        if not buch.nehmen(fenster):
            return kaputt("ampr_assets.index: Fenster", fenster)
        if not buch.nehmen(ablage):
            return kaputt("ampr_assets.index", ablage)
        buch.geben(fenster)
        bitmap = (ampridx.dateien + 1 + 7) // 8        # join_lz4: ein Bit je Ansicht-ID
        if not buch.nehmen(bitmap):
            return kaputt("ampr_assets.index: Abgleich", bitmap)
        buch.weg["tabellen"] = ablage + bitmap
    buch.geben(zwischen)                                # Compact::finish nach dem Verbinden
    buch.weg["dauerhaft"] = buch.benutzt
    return Befund(modell, True, "", 0, 0, belegt())


def _pruefen_035(ampridx: Kopf, art: str, pack: Kopf | None) -> Befund:
    belegt = 0
    schritte: list[tuple[str, int]] = [("ampr_emu.index", ampridx.laenge)]
    if art and pack is not None:
        name = "ampr_zstd.index" if art == "zstd" else "ampr_assets.index"
        schritte.append((name, pack.laenge))
        if art == "zstd":
            schritte += [(name + ": Tabellen", ampridx.dateien * 16), (name + ": Tabellen", min(pack.dateien, ampridx.dateien) * 4)]
        else:
            schritte.append((name + ": Tabellen", pack.dateien * 4))
    for engpass, anforderung in schritte:
        if belegt + _rund(anforderung) > GRENZE_035:
            # "index needs X MiB, over the 55 MiB cap": belegt plus die abgelehnte Anforderung.
            return Befund(MODELL_035, False, engpass, belegt + anforderung, GRENZE_035, {"gesamt": belegt})
        belegt += _rund(anforderung)
    return Befund(MODELL_035, True, "", 0, 0, {"gesamt": belegt})


def pruefen(fassung: str, ampridx: Kopf, art: str = "", pack: Kopf | None = None, ordner: int | None = None) -> "Befund | None":
    """Rechnet die Ladefolge von NG ``fassung`` nach.

    Args:
        fassung: Die gewaehlte NG-Fassung (``"0.5.0"``, ``"0.4.1"``, ``"0.4.0-beta"``, ``"0.3.5"`` ...).
        ampridx: Kopf des ``ampr_emu.index`` (:func:`ampridx3_kopf`).
        art: ``"zstd"``, ``"lz4"`` oder ``""`` (kein Asset-Pack).
        pack: Kopf des Pack-Manifests (:func:`zstd_kopf` / :func:`lz4_kopf`).
        ordner: Ordnerzahl des Spiels, falls bekannt; nur 0.4.1 und neuer braucht sie (:func:`ansicht_041`, :func:`ansicht_050`).

    Returns:
        Den Befund, oder ``None`` fuer eine Fassung ohne bekanntes Modell (vor 0.3.5).
    """
    modell = modell_fuer(fassung)
    if modell == MODELL_050:
        return _pruefen_041(ampridx, art, pack, ordner, MODELL_050, ansicht_050)
    if modell == MODELL_041:
        return _pruefen_041(ampridx, art, pack, ordner)
    if modell in (MODELL_040, MODELL_BETA):
        return _pruefen_040(ampridx, art, pack, vorbehalt=modell == MODELL_BETA)
    if modell == MODELL_035:
        return _pruefen_035(ampridx, art, pack)
    return None
