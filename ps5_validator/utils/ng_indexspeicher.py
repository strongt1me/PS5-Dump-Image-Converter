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

* **beta ab 54d6ac2** (14.11.2026 17:34 UTC, "Page an unsorted ampr_emu.index and size it against the pack index") und - so
  angenommen - jede Freigabe ab 0.4.1: wie 0.4.0, aber der ``ampr_emu.index`` wird nur noch ganz gelesen, wenn daneben das, was das
  Manifest mindestens braucht, frei bleibt (``pack_index_reserve``: das Kleinere aus "ganz samt Tabellen" und "Schnelltabelle +
  Tabellen + 16 MiB Seitenspeicher", je auf Seiten gerundet); sonst seitenweise. Ein unsortierter, seitenweise gelesener Index
  bekaeme dort noch eine Rangtabelle (4 B je Eintrag) - der Index dieses Programms ist sortiert, das ist nicht nachgebaut.

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

MODELL_035 = "0.3.5"
MODELL_040 = "0.4.0"
#: 0.4.0 mit dem Vorbehalt fuer das Manifest (beta ab 54d6ac2; angenommen fuer jede Freigabe ab 0.4.1).
MODELL_BETA = "0.4.0-beta"


def modell_fuer(fassung: str) -> str:
    """Welches Modell fuer eine NG-Fassung gilt: ``"0.4.0-beta"`` fuer die beta (der mitgelieferte Stand ist 54d6ac2) und ab
    0.4.1, ``"0.4.0"`` fuer die Freigabe 0.4.0, ``"0.3.5"`` fuer 0.3.5, sonst ``""`` (vor 0.3.5: kein Modell)."""
    text = str(fassung or "")
    treffer = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not treffer:
        return ""
    teile = tuple(int(t) for t in treffer.groups())
    if teile >= (0, 4, 1) or (teile >= (0, 4, 0) and "beta" in text.lower()):
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


def pruefen(fassung: str, ampridx: Kopf, art: str = "", pack: Kopf | None = None) -> "Befund | None":
    """Rechnet die Ladefolge von NG ``fassung`` nach.

    Args:
        fassung: Die gewaehlte NG-Fassung (``"0.4.0-beta"``, ``"0.3.5"`` ...).
        ampridx: Kopf des ``ampr_emu.index`` (:func:`ampridx3_kopf`).
        art: ``"zstd"``, ``"lz4"`` oder ``""`` (kein Asset-Pack).
        pack: Kopf des Pack-Manifests (:func:`zstd_kopf` / :func:`lz4_kopf`).

    Returns:
        Den Befund, oder ``None`` fuer eine Fassung ohne bekanntes Modell (vor 0.3.5).
    """
    modell = modell_fuer(fassung)
    if modell in (MODELL_040, MODELL_BETA):
        return _pruefen_040(ampridx, art, pack, vorbehalt=modell == MODELL_BETA)
    if modell == MODELL_035:
        return _pruefen_035(ampridx, art, pack)
    return None
