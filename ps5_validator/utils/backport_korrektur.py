# -*- coding: utf-8 -*-
"""BACKPORT: Korrekturen an Programmdateien nach dem Herabsetzen - Stubs und Korrekturprofile.

Zwei Werkzeuge, beide **nur auf Haken** und beide ohne Garantie:

1. **Stubs fuer unaufgeloeste Importe.** Ein herabgesetztes Spiel verlangt manchmal Funktionen, die die Zielfirmware
   nicht kennt und die keine Ersatzbibliothek liefern kann (``libkernel``, ``LibcInternal``: der Kernel liefert sie,
   ShadowMount+ loescht ``libkernel.sprx`` absichtlich aus dem fakelib-Cache). Auf der Konsole bricht das Spiel dann mit
   ``0xa0020101 PRX_NOT_RESOLVED_FUNCTION`` ab - beim ersten Aufruf. Hier wird der PLT-Eintrag der Funktion im Spiel
   selbst durch einen winzigen Stub ersetzt (``xor eax,eax; ret``). Gemessen wird gegen die Exporttabelle der
   Zielfirmware (:func:`ps5_backport.luecken_ohne_ersatz`).
2. **Korrekturprofile je Titel.** Manche Spiele brauchen mehr als fehlende Importe (falsche Parameter an der
   Zielfirmware). Ein Profil (JSON, je Title-ID) nennt Byte-Aenderungen mit Adresse, alten und neuen Bytes. Es wird nur
   angewendet, wenn die SHA-256 der Originaldatei stimmt **und** an jeder Stelle die alten Bytes stehen.

Hintergrund: Anno 117 (PPSA23559, SDK 11) laeuft auf FW 4.xx erst mit beidem (Test Z3, 04.11.2026, am echten Geraet
bestaetigt). Die Stub-Bytes und die Ausnahme fuer ``NH6xARDOVv8`` stammen aus dieser Messreihe.

Dieses Modul bindet weder Fenster noch ``i18n`` ein; die Oberflaeche formuliert die Meldungen aus den Ergebnissen.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import struct
from typing import Callable, Iterable, NamedTuple

from ps5_validator.utils import ps5_backport as bp

# --------------------------------------------------------------------------
# ELF: Programmkoepfe, Dynamik, PLT
# --------------------------------------------------------------------------

PT_LOAD = 1
PT_DYNAMIC = 2
PF_X = 1

DT_PLTRELSZ = 2
DT_STRTAB = 5
DT_SYMTAB = 6
DT_STRSZ = 10
DT_PLTREL = 20
DT_RELA = 7
DT_JMPREL = 23

#: ``R_X86_64_JUMP_SLOT`` - einziger Typ, der in den PLT-Relocations der PS5-Module vorkommt (gemessen).
R_JUMP_SLOT = 7
#: Bindung "schwach" (``st_info >> 4``): Ein unaufgeloester schwacher Import ist erlaubt und bleibt 0, ein Stub
#: wuerde ihn zu einer vorhandenen Funktion machen - deshalb fasst die allgemeine Neutralisierung ihn nicht an.
STB_WEAK = 2

#: Ein PLT-Eintrag der PS5-Module, 16 Byte: ``jmp [rip+rel32]`` (6), ``push idx32`` (5), ``jmp rel32`` (5).
PLT_LAENGE = 16
_PLT_MUSTER = re.compile(rb"\xff\x25(.{4})\x68(.{4})\xe9(.{4})", re.S)
_SPRUNG = b"\xff\x25"


class _Kopf(NamedTuple):
    typ: int
    flags: int
    offset: int
    vaddr: int
    filesz: int
    memsz: int


def _koepfe(elf: bytes) -> list[_Kopf]:
    if len(elf) < 0x40 or elf[:4] != b"\x7fELF":
        return []
    phoff, = struct.unpack_from("<Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", elf, 0x36)
    if phentsize < 0x38:
        return []
    koepfe = []
    for i in range(phnum):
        p = phoff + i * phentsize
        if p + 0x38 > len(elf):
            break
        typ, flags = struct.unpack_from("<II", elf, p)
        offset, vaddr, _paddr, filesz, memsz = struct.unpack_from("<5Q", elf, p + 8)
        koepfe.append(_Kopf(typ, flags, offset, vaddr, filesz, memsz))
    return koepfe


def va_zu_offset(elf: bytes, va: int, laenge: int = 1) -> "int | None":
    """Dateioffset einer virtuellen Adresse; ``None``, wenn ``va..va+laenge`` nicht ganz in einem Segment liegt."""
    for k in _koepfe(elf):
        if k.typ == PT_LOAD and k.vaddr <= va and va + laenge <= k.vaddr + k.filesz:
            ziel = k.offset + (va - k.vaddr)
            if ziel + laenge <= len(elf):
                return ziel
    return None


class PltEintrag(NamedTuple):
    """Ein Import mit seinem PLT-Eintrag."""
    bibliothek: str
    nid: str
    index: int
    got_va: int
    plt_va: int
    plt_offset: int
    schwach: bool


def plt_eintraege(elf: bytes) -> list[PltEintrag]:
    """Alle Importe eines ELF/PRX, zu denen ein PLT-Eintrag gefunden wurde, nach Relocation-Index sortiert.

    Der Eintrag wird auf zwei Wegen abgesichert: Die Relocation nennt die GOT-Adresse, der gefundene Stub muss genau
    dorthin springen **und** den Relocation-Index als ``push`` tragen. Gemessen an libc.prx (114 Eintraege) und der
    eboot.bin von Anno 117 (1354 Eintraege): jeder Eintrag gefunden, Offsets gleich denen der REA-Analyse.
    """
    koepfe = _koepfe(elf)
    lade = [k for k in koepfe if k.typ == PT_LOAD]
    dyn = next((k for k in koepfe if k.typ == PT_DYNAMIC), None)
    if not lade or dyn is None or dyn.offset + dyn.filesz > len(elf):
        return []
    tags: dict[int, int] = {}
    for i in range(dyn.filesz // 16):
        tag, wert = struct.unpack_from("<QQ", elf, dyn.offset + i * 16)
        if tag == 0:
            break
        tags.setdefault(tag, wert)
    if not all(t in tags for t in (DT_JMPREL, DT_PLTRELSZ, DT_SYMTAB, DT_STRTAB, DT_STRSZ)):
        return []
    if tags.get(DT_PLTREL, DT_RELA) != DT_RELA:
        return []
    rela = va_zu_offset(elf, tags[DT_JMPREL], max(24, tags[DT_PLTRELSZ]))
    symtab = va_zu_offset(elf, tags[DT_SYMTAB])
    strtab = va_zu_offset(elf, tags[DT_STRTAB])
    if rela is None or symtab is None or strtab is None:
        return []
    strsz = tags[DT_STRSZ]

    bibliotheken = bp.prx_symbole(elf)["import_bibliotheken"]
    relocs: list = []
    for i in range(tags[DT_PLTRELSZ] // 24):
        r_offset, r_info, _zusatz = struct.unpack_from("<QQq", elf, rela + i * 24)
        if (r_info & 0xFFFFFFFF) != R_JUMP_SLOT:
            relocs.append(None)
            continue
        sym = r_info >> 32
        p = symtab + sym * 24
        if p + 24 > len(elf):
            relocs.append(None)
            continue
        st_name, st_info = struct.unpack_from("<IB", elf, p)
        if st_name == 0 or st_name >= strsz:
            relocs.append(None)
            continue
        ende = elf.find(b"\0", strtab + st_name)
        if ende < 0:
            relocs.append(None)
            continue
        nid, bib, _modul = bp.symbol_zerlegen(elf[strtab + st_name:ende].decode("latin1"))
        if bib < 0:
            relocs.append(None)
            continue
        relocs.append((r_offset, nid, bibliotheken.get(bib, "?"), (st_info >> 4) == STB_WEAK))

    stubs: dict[int, tuple[int, int]] = {}
    for k in lade:
        if not k.flags & PF_X:
            continue
        bis = min(k.offset + k.filesz, len(elf))
        for treffer in _PLT_MUSTER.finditer(elf, k.offset, bis):
            pos = treffer.start()
            va = k.vaddr + (pos - k.offset)
            rel, = struct.unpack("<i", treffer.group(1))
            idx, = struct.unpack("<I", treffer.group(2))
            if idx < len(relocs) and relocs[idx] is not None and relocs[idx][0] == va + 6 + rel:
                stubs.setdefault(idx, (va, pos))

    _bereits_gesetzte_ergaenzen(elf, stubs, relocs)

    ergebnis = []
    for idx, reloc in enumerate(relocs):
        if reloc is None or idx not in stubs:
            continue
        got, nid, bib, schwach = reloc
        va, pos = stubs[idx]
        ergebnis.append(PltEintrag(bib, nid, idx, got, va, pos, schwach))
    return ergebnis


def _bereits_gesetzte_ergaenzen(elf: bytes, stubs: "dict[int, tuple[int, int]]", relocs: list) -> None:
    """Findet PLT-Eintraege wieder, die schon durch einen Stub ersetzt sind.

    Ein gesetzter Stub ueberschreibt den Anfang des Eintrags, das Muster ``ff 25 ... 68 idx e9`` trifft dann nicht
    mehr - ein zweiter Lauf wuerde den Eintrag nicht mehr kennen und nicht sagen koennen, dass er schon erledigt ist.
    Die Eintraege folgen aber lueckenlos im Abstand von 16 Byte in der Reihenfolge der Relocations (gemessen an
    libc.prx und eboot.bin von Anno 117: keine einzige Ausnahme). Aus den gefundenen Eintraegen ergibt sich die
    Anfangsadresse; ein fehlender Index wird nur ergaenzt, wenn dort die Bytes eines unserer Stubs stehen.
    """
    if not stubs:
        return
    versaetze: dict[tuple[int, int], int] = {}
    for idx, (va, pos) in stubs.items():
        schluessel = (va - PLT_LAENGE * idx, pos - PLT_LAENGE * idx)
        versaetze[schluessel] = versaetze.get(schluessel, 0) + 1
    (va0, pos0), haeufig = max(versaetze.items(), key=lambda kv: kv[1])
    if haeufig * 10 < len(stubs) * 9:           # weniger als 90 % auf einer Linie: nichts raten
        return
    bekannt = tuple(a.bytes_ for a in STUB_ARTEN.values())
    bekannt_landeplatz = tuple(a.landeplatz_bytes() for a in STUB_ARTEN.values())
    for idx, reloc in enumerate(relocs):
        if reloc is None or idx in stubs:
            continue
        pos = pos0 + PLT_LAENGE * idx
        if pos < 0 or pos + PLT_LAENGE > len(elf):
            continue
        eintrag = elf[pos:pos + PLT_LAENGE]
        im_eintrag = any(eintrag.startswith(b) for b in bekannt)
        # Landeplatz-Stub: der erste Sprung bleibt, dahinter steht unser Stub statt "push idx; jmp Aufloeser".
        am_landeplatz = (eintrag[:2] == _SPRUNG
                         and any(eintrag[LANDEPLATZ_OFFSET:].startswith(b) for b in bekannt_landeplatz))
        # Warte-Ersatz (:func:`warten_ersetzen`): ``mov edi,<µs>; jmp usleep`` im Eintrag oder auf dem Landeplatz.
        warte_ersatz = (eintrag.startswith(_WARTE_KOPF + b"\xe9")
                        or (eintrag[:2] == _SPRUNG and eintrag[LANDEPLATZ_OFFSET:].startswith(_WARTE_KOPF + b"\xe9")))
        if im_eintrag or am_landeplatz or warte_ersatz:
            stubs[idx] = (va0 + PLT_LAENGE * idx, pos)


# --------------------------------------------------------------------------
# Stub-Tabelle
# --------------------------------------------------------------------------

#: Der Landeplatz eines Stubs im "Landeplatz"-Modus: hinter dem ``jmp [GOT]`` (6 Byte) des PLT-Eintrags, dort wo sonst
#: ``push idx; jmp Aufloeser`` steht. Der lazy gebundene GOT-Eintrag zeigt anfangs genau dorthin - ein Stub dort laeuft
#: nur, wenn der Lader die Funktion **nicht** aufgeloest hat; hat er sie gebunden, springt der erste ``jmp`` in die
#: echte Funktion. Gemessen am 21.11.2026 an einer Konsole mit FW 12.00: Der Lader der PS5 bindet Funktionen der Firmware
#: schon beim Laden (der Stub wird nie erreicht), bei einem unaufgeloesten Import zeigt der GOT auf Byte 6 (der Stub
#: bekommt die Kontrolle). Mit einem echten Backport und auf 4.xx noch nicht erprobt (siehe :func:`stubs_setzen`).
LANDEPLATZ_OFFSET = 6
LANDEPLATZ_MAX = PLT_LAENGE - LANDEPLATZ_OFFSET


class StubArt(NamedTuple):
    kennung: str
    #: Die Bytes im PLT-Eintrag selbst (bis 16).
    bytes_: bytes
    beschreibung: str
    #: Gleichwertige Kurzform fuer den Landeplatz (bis 10 Byte); ``None`` = ``bytes_`` passt schon.
    kurz: "bytes | None" = None

    def landeplatz_bytes(self) -> bytes:
        return self.kurz if self.kurz is not None else self.bytes_


#: ``xor eax,eax; ret`` - die Funktion tut nichts und meldet Erfolg (0).
STUB_STANDARD = StubArt("standard", bytes.fromhex("31c0c3"), "xor eax,eax; ret")

#: ``mov dword [rdi],-1; mov dword [rsi],-1; xor eax,eax; ret`` - fuer Funktionen, deren Aufrufer zwei Ausgabeparameter
#: liest. 15 Byte, passt in den 16-Byte-PLT-Eintrag; die Kurzform (``or dword [rdi],-1; or dword [rsi],-1`` statt der
#: Schreibzugriffe, gleiches Ergebnis -1) hat 9 Byte und passt auf den Landeplatz.
STUB_AUSGABEN_MINUS1 = StubArt(
    "ausgaben_minus1", bytes.fromhex("c707ffffffffc706ffffffff31c0c3"),
    "*rdi=*rsi=-1; xor eax,eax; ret", bytes.fromhex("830fff830eff31c0c3"))

#: Vertraege nach der Beschreibung im fremden ps5-backport-toolkit (``stub_contracts.json``, MIT) - die Bytes sind hier
#: aus der Beschreibung neu geschrieben. **An keiner Konsole bewiesen** (dort ``hw_proved: false``); sie ersetzen nur
#: den Standard-Stub ``xor eax,eax; ret`` dort, wo dieser einen Ausgabewert ungeschrieben oder einen Fehlercode als
#: Erfolg liesse.
#: ``scePadIsRemoteController``: ``*(bool*)rsi = 0; return 0``.
STUB_AUSGABE_BOOL0 = StubArt("ausgabe_bool0", bytes.fromhex("31c08806c3"), "*(bool*)rsi=0; eax=0; ret")
#: ``sceNpEntitlementAccessGetGameTrialsFlag``: ``*(int*)rdi = 0`` (keine Testversion); ``return 0``.
STUB_AUSGABE_INT0 = StubArt("ausgabe_int0", bytes.fromhex("c7070000000031c0c3"), "*(int*)rdi=0; eax=0; ret")
#: ``sceSaveDataConvert``: ``return 0x809F0008`` (kein PS4-Spielstand zum Umwandeln).
STUB_FEHLER_809F0008 = StubArt("fehler_809f0008", bytes.fromhex("b808009f80c3"), "eax=0x809F0008; ret")
#: ``sceSystemServiceOpenTournamentOccurrence``: ``return 0x80A10001`` (ein vom Spiel behandelter Fehlerzweig).
STUB_FEHLER_80A10001 = StubArt("fehler_80a10001", bytes.fromhex("b80100a180c3"), "eax=0x80A10001; ret")

#: Arten, die ein Profil beim Namen nennen darf.
STUB_ARTEN: dict[str, StubArt] = {a.kennung: a for a in (
    STUB_STANDARD, STUB_AUSGABEN_MINUS1, STUB_AUSGABE_BOOL0, STUB_AUSGABE_INT0, STUB_FEHLER_809F0008,
    STUB_FEHLER_80A10001)}

#: Ausnahmen von der Standard-Art je (Bibliothek, NID). Gemessen an Anno 117 (04.11.2026): ``NH6xARDOVv8`` (libkernel,
#: erst ab FW 11.00) hat drei Aufrufer, die danach ``cmp dword [rbp-0xe0],1`` auf einem AUSGABEPARAMETER ausfuehren;
#: das Original schreibt -1 hinein. Ohne die Schreibzugriffe liest der Aufrufer Stapelmuell.
#: **Regel fuer neue Eintraege:** Vor jedem Stub pruefen, ob der Aufrufer Rueckgabewert oder Ausgabeparameter auswertet.
#: Die allgemeine Neutralisierung kann das nicht - jede NID, die hier fehlt, bekommt den Standard-Stub.
STUB_TABELLE: dict[tuple[str, str], StubArt] = {
    ("libkernel", "NH6xARDOVv8"): STUB_AUSGABEN_MINUS1,
    # Die folgenden vier stammen aus Fremdangaben (siehe oben), nicht aus einer eigenen Messreihe:
    ("libScePad", "fCWdlnmB1Ks"): STUB_AUSGABE_BOOL0,                    # erst ab FW 10.01
    ("libSceNpEntitlementAccess", "y7JD1gfwyfA"): STUB_AUSGABE_INT0,    # erst ab FW 6.00
    ("libSceSaveData", "2mfSRGdshtk"): STUB_FEHLER_809F0008,            # erst ab FW 8.00
    # Marsupilami 2 (PPSA34356) fuehrt dieselbe NID unter dem Bibliotheksnamen "libSceSaveData_native" (gemessen 20.11.2026)
    ("libSceSaveData_native", "2mfSRGdshtk"): STUB_FEHLER_809F0008,
    ("libSceSystemService", "gELp9ue2ccQ"): STUB_FEHLER_80A10001,       # erste Fassung unbekannt
}

#: Zwei weitere Vertraege des Toolkits fehlen hier mit Absicht: ``gWT7X8H0bYs`` (VideoOut, 0x40 Byte nullen, nur wenn
#: jeder Aufrufer einen eigenen, ueber 0x40 Byte beschriebenen Puffer uebergibt) und ``YFC3dBBipj8`` (libkernel,
#: ``return 0x80020003``, nur wenn jeder Aufrufer danach genau damit vergleicht). Beides sind Bedingungen am Aufrufer,
#: die die allgemeine Neutralisierung nicht pruefen kann.

#: Importe, die die allgemeine Neutralisierung nie anfasst (leer: bisher nichts bekannt, das gefaehrlicher waere als
#: ein Absturz). Eintraege hier haben Vorrang vor allem anderen.
STUB_NIE: frozenset = frozenset()


def stub_art(bibliothek: str, nid: str) -> StubArt:
    """Die Stub-Art fuer einen Import: Tabelle, sonst Standard."""
    return STUB_TABELLE.get((bibliothek, nid), STUB_STANDARD)


STATUS_GESETZT = "gesetzt"
STATUS_BEREITS = "bereits"
STATUS_FEHLT = "fehlt"
STATUS_ABWEICHEND = "abweichend"


class StubErgebnis(NamedTuple):
    bibliothek: str
    nid: str
    art: str
    offset: int
    status: str


def stubs_setzen(elf: bytes, ziele: "dict[tuple[str, str], str | None]", *,
                 schwache_auslassen: bool = True, landeplatz: bool = False) -> "tuple[bytes, list[StubErgebnis]]":
    """Ersetzt die PLT-Eintraege der genannten Importe durch Stubs.

    Args:
        elf: Das ELF (kein SELF).
        ziele: ``(Bibliothek, NID)`` -> Art-Kennung oder ``None`` (= :func:`stub_art`).
        schwache_auslassen: Schwach gebundene Importe nicht anfassen.
        landeplatz: **Versuch; der Mechanismus ist an FW 12.00 gemessen (21.11.2026), ein echter Backport-Lauf nicht.**
            Statt den ganzen PLT-Eintrag zu ueberschreiben, bleibt der erste ``jmp [GOT]`` stehen und der Stub
            (Kurzform, bis 10 Byte) ersetzt nur das ``push idx; jmp Aufloeser`` dahinter. Bindet der Lader eine
            Funktion, die die Zielfirmware doch hat, bleibt sie dann erreichbar; der feste Stub im Eintrag haette sie
            verdeckt. Gemessen (Sonden-Bau mit ``ud2``, KLOG-Mitschnitt): aufgeloeste Funktion bleibt nativ (Stub nie
            erreicht, 2 von 2), unaufgeloester Import trifft den Stub bei Eintrag + 6 (2 von 2). Nicht gemessen: 4.xx.

    Returns:
        (Bytes, Ergebnisse). Ein Ziel, das in der Datei nicht vorkommt, taucht **nicht** auf - der Aufrufer prueft
        das bei Bedarf selbst (:func:`profil_datei_anwenden` verlangt es). Die Bytes sind dasselbe Objekt, wenn nichts
        zu tun war.
    """
    eintraege = {(e.bibliothek, e.nid): e for e in plt_eintraege(elf)}
    ergebnisse: list[StubErgebnis] = []
    puffer = None
    for ziel, art_name in sorted(ziele.items()):
        e = eintraege.get(ziel)
        if e is None:
            continue
        if schwache_auslassen and e.schwach:
            continue
        art = STUB_ARTEN[art_name] if art_name else stub_art(*ziel)
        stelle_offset, neu = stub_stelle(e, art, landeplatz)
        stelle = elf[stelle_offset:stelle_offset + len(neu)]
        if _plt_eintrag_original(elf, e):
            if puffer is None:
                puffer = bytearray(elf)
            puffer[stelle_offset:stelle_offset + len(neu)] = neu
            status = STATUS_GESETZT
        elif stelle == neu or _eigener_stub_da(elf, e, art):
            status = STATUS_BEREITS
        else:
            status = STATUS_ABWEICHEND
        ergebnisse.append(StubErgebnis(e.bibliothek, e.nid, art.kennung, stelle_offset, status))
    return (bytes(puffer) if puffer is not None else elf), ergebnisse


_PUSH = 0x68


def stub_stelle(e: "PltEintrag", art: StubArt, landeplatz: bool) -> "tuple[int, bytes]":
    """Wohin ein Stub kommt und welche Bytes: im Eintrag selbst, oder auf den Landeplatz (dann die Kurzform)."""
    if not landeplatz:
        return e.plt_offset, art.bytes_
    kurz = art.landeplatz_bytes()
    if len(kurz) > LANDEPLATZ_MAX:
        raise ValueError("Stub %s ist mit %d Byte zu lang fuer den Landeplatz (%d)" % (art.kennung, len(kurz), LANDEPLATZ_MAX))
    return e.plt_offset + LANDEPLATZ_OFFSET, kurz


def _plt_eintrag_original(elf: bytes, e: "PltEintrag") -> bool:
    """Steht im PLT-Eintrag noch ``jmp [GOT]; push idx`` - also weder ein fester noch ein Landeplatz-Stub von uns?"""
    return (elf[e.plt_offset:e.plt_offset + 2] == _SPRUNG
            and elf[e.plt_offset + LANDEPLATZ_OFFSET:e.plt_offset + LANDEPLATZ_OFFSET + 1] == bytes((_PUSH,)))


def _eigener_stub_da(elf: bytes, e: "PltEintrag", art: StubArt) -> bool:
    """Traegt der Eintrag schon unseren Stub dieser Art - in einer der beiden Formen?

    Ein frueherer Lauf kann ihn in der anderen Form gesetzt haben: bis 21.11.2026 fest am Eintragsanfang, seitdem fuer Luecken auf
    dem Landeplatz hinter dem ersten ``jmp [GOT]``. Beide fangen die fehlende Funktion ab (der feste sogar immer) - das ist erledigt,
    keine "unerwarteten Bytes" (frueher ``STATUS_ABWEICHEND``, und die Restmeldung nannte die Funktion dann als offene Luecke).
    """
    fest = elf[e.plt_offset:e.plt_offset + len(art.bytes_)] == art.bytes_
    kurz = art.landeplatz_bytes()
    auf_landeplatz = (elf[e.plt_offset:e.plt_offset + 2] == _SPRUNG
                      and elf[e.plt_offset + LANDEPLATZ_OFFSET:e.plt_offset + LANDEPLATZ_OFFSET + len(kurz)] == kurz)
    return fest or auf_landeplatz


def luecken_neutralisieren(elf: bytes, luecken: "dict[str, Iterable[str]]", *,
                           landeplatz: bool = False) -> "tuple[bytes, list[StubErgebnis]]":
    """Stubs fuer alle Luecken (Bibliothek -> NIDs), die diese Datei importiert.

    Die Luecken gelten fuer den ganzen Dump; was die Datei nicht importiert, wird uebergangen. Bibliotheken ohne
    ``lib``-Vorsatz bleiben unberuehrt: Die Exporttabelle der Firmware fuehrt sie nicht, eine "Luecke" dort waere nur
    eine Unkenntnis (Anno 117: ``ulobjmgr``).
    """
    ziele = {(lib, nid): None for lib, nids in luecken.items() if lib.startswith("lib") for nid in nids
             if (lib, nid) not in STUB_NIE}
    ersetzt: list[StubErgebnis] = []
    if any(nid in WARTE_NIDS for _lib, nid in ziele):
        usleep_fehlt = USLEEP_IMPORT[1] in set(luecken.get(USLEEP_IMPORT[0], ()))
        elf, ersetzt = warten_ersetzen(elf, [z for z in ziele if z[1] in WARTE_NIDS], usleep_fehlt=usleep_fehlt,
                                       landeplatz=landeplatz)
        for s in ersetzt:
            ziele.pop((s.bibliothek, s.nid), None)
    neu, rest = stubs_setzen(elf, ziele, landeplatz=landeplatz)
    return neu, ersetzt + rest


# --------------------------------------------------------------------------
# Warten auf eine Adresse: Abfragen statt Stub
# --------------------------------------------------------------------------

#: "Warte, solange der Wert an der Adresse gleich bleibt" (``libkernel`` und ``libkernel_sync_on_address``, in der
#: Firmware ab 6.00; in libkernel 6.00 eine Huelle um ``_umtx_op`` mit einer Sony-Erweiterung, die 4.03 und 5.50 nicht
#: kennen). Der Unity-Player ab 2022.3 baut darauf seine Semaphoren (``PS5Util.prx``), jede libc ab SDK 9 importiert sie.
#: Mit dem Standard-Stub kehrt jedes Warten sofort zurueck, und jeder wartende Thread dreht eine Dauerschleife. Gemessen
#: an Valheim (PPSA28824, FW 4.03, 25.11.2026): schwarzer Bildschirm ohne Fehlermeldung; mit ``sceKernelUsleep(200)``
#: statt des Stubs laeuft das Spiel (Test D). Ein fremder Backport von Hollow Knight loest es ebenfalls durch Abfragen.
#: Das Wecken (``q2y-wDIVWZA``) bleibt beim Standard-Stub: Wer abfragt, muss nicht geweckt werden.
WARTE_NIDS: frozenset = frozenset({"Hc4CaR6JBL0"})

#: ``sceKernelUsleep`` - hat jede Firmware ab 4.00.
USLEEP_IMPORT = ("libkernel", "1jfXLRVzisc")

#: Abstand zwischen zwei Abfragen. 200 µs ist der an der Konsole gemessene Wert (Valheim, Test D).
WARTE_MIKROSEKUNDEN = 200

#: ``mov edi, <µs>`` - das Argument fuer ``sceKernelUsleep``.
_WARTE_KOPF = b"\xbf" + struct.pack("<I", WARTE_MIKROSEKUNDEN)

#: Die Datei importiert ``sceKernelUsleep`` schon: Der Ersatz springt in dessen PLT-Eintrag.
ART_WARTEN_SPRUNG = "warten_usleep"
#: Die Datei importiert es nicht: Der Import der Warte-Funktion wird auf ``sceKernelUsleep`` umgeschrieben.
ART_WARTEN_IMPORT = "warten_usleep_import"


def _strtab_bereich(elf: bytes) -> "tuple[int, int] | None":
    """(Dateioffset, Laenge) der Zeichenkettentabelle der Dynamik."""
    dyn = next((k for k in _koepfe(elf) if k.typ == PT_DYNAMIC), None)
    if dyn is None or dyn.offset + dyn.filesz > len(elf):
        return None
    tags: dict[int, int] = {}
    for i in range(dyn.filesz // 16):
        tag, wert = struct.unpack_from("<QQ", elf, dyn.offset + i * 16)
        if tag == 0:
            break
        tags.setdefault(tag, wert)
    if DT_STRTAB not in tags or not tags.get(DT_STRSZ):
        return None
    anfang = va_zu_offset(elf, tags[DT_STRTAB])
    return None if anfang is None else (anfang, min(tags[DT_STRSZ], len(elf) - anfang))


def _import_umbenennen(puffer: bytearray, alt: "tuple[str, str]", neu: "tuple[str, str]") -> bool:
    """Schreibt den Importnamen ``alt`` (Bibliothek, NID) auf ``neu`` um - gleich lang, an derselben Stelle.

    Ein Importname ist ``<NID>#<Bibliothek>#<Modul>`` mit je einem Zeichen als Kennzahl. Die Kennzahl der neuen Bibliothek
    steht in der Bibliotheksliste der Datei, die des Moduls wird von einem vorhandenen Import derselben Bibliothek
    abgelesen. Nichts wird geraten: Kommt der alte Name nicht genau einmal vor, gibt es den neuen schon oder importiert
    die Datei aus der neuen Bibliothek gar nichts, bleibt alles, wie es ist.
    """
    bereich = _strtab_bereich(bytes(puffer))
    if bereich is None:
        return False
    anfang, laenge = bereich
    bibliotheken = bp.prx_symbole(bytes(puffer))["import_bibliotheken"]
    alt_ids = [k for k, name in bibliotheken.items() if name == alt[0]]
    neu_ids = [k for k, name in bibliotheken.items() if name == neu[0]]
    if len(alt_ids) != 1 or len(neu_ids) != 1:
        return False
    try:
        alt_kennung = bp.NID_ALPHABET[alt_ids[0]].encode("ascii")
        neu_kennung = bp.NID_ALPHABET[neu_ids[0]].encode("ascii")
    except (IndexError, TypeError):
        return False
    tabelle = bytes(puffer[anfang:anfang + laenge])
    treffer = list(re.finditer(rb"(?<=\0)" + re.escape(alt[1].encode("ascii")) + b"#" + re.escape(alt_kennung)
                               + rb"#[A-Za-z0-9+\-]\0", tabelle))
    modul = re.search(rb"(?<=\0)[A-Za-z0-9+\-]{11}#" + re.escape(neu_kennung) + rb"#([A-Za-z0-9+\-])\0", tabelle)
    if len(treffer) != 1 or modul is None:
        return False
    name = neu[1].encode("ascii") + b"#" + neu_kennung + b"#" + modul.group(1)
    if b"\0" + name + b"\0" in tabelle or len(name) + 1 != len(treffer[0].group(0)):
        return False
    stelle = anfang + treffer[0].start()
    puffer[stelle:stelle + len(name)] = name
    return True


def warten_ersetzen(elf: bytes, ziele: "Iterable[tuple[str, str]]", *, usleep_fehlt: bool = False,
                    landeplatz: bool = False) -> "tuple[bytes, list[StubErgebnis]]":
    """Ersetzt fehlende Warte-Funktionen (:data:`WARTE_NIDS`) durch ``sceKernelUsleep(200)`` statt durch einen Stub.

    Ein Aufrufer wartet in einer Schleife, bis sich der Wert an der Adresse aendert. Eine Rueckkehr ohne Aenderung ist
    fuer ihn ein gewoehnliches verfruehtes Aufwachen, er prueft den Wert und wartet erneut - nur eben mit 200 µs Pause
    statt in einer Dauerschleife.

    Zwei Wege, je nach Datei:

    * Die Datei importiert ``sceKernelUsleep`` schon (libc.prx): ``mov edi,200; jmp <PLT-Eintrag von usleep>``, 10 Byte -
      im Landeplatz-Modus hinter dem ersten ``jmp [GOT]`` (bindet der Lader die echte Funktion, bleibt sie erreichbar).
    * Sie importiert es nicht (PS5Util.prx): Der Importname der Warte-Funktion wird auf ``sceKernelUsleep`` umgeschrieben
      (:func:`_import_umbenennen`), der Lader bindet den Eintrag dann an usleep; davor steht ``mov edi,200``. Das setzt
      voraus, dass der Lader Importe beim Laden bindet (gemessen an FW 12.00 am 21.11.2026 und an FW 4.03 mit eben
      dieser Form).

    Beide Wege sind an der Konsole gelaufen: Valheim auf FW 4.03 mit der so erzeugten PS5Util.prx und libc.prx
    (Test F, 26.11.2026) - das Spiel startet, laesst sich spielen und speichert.

    Nicht nachgebildet: das Zeitlimit des Originals (Restzeit zurueckschreiben, ``0x8002003c`` bei Ablauf). Ein Aufrufer,
    der sich allein auf den Ablauf verlaesst, wartet weiter, bis sich der Wert aendert. Bei Valheim wertet keiner der
    gelesenen Aufrufer die Rueckgabe aus.

    Args:
        ziele: ``(Bibliothek, NID)`` der Luecken dieser Art.
        usleep_fehlt: Die Zielfirmware hat ``sceKernelUsleep`` nicht - dann bleibt alles beim Stub.

    Returns:
        (Bytes, Ergebnisse) - nur fuer Eintraege, die ersetzt wurden oder schon ersetzt sind. Was hier nicht auftaucht,
        bekommt wie bisher seinen Stub (:func:`stubs_setzen`). Die Bytes sind dasselbe Objekt, wenn nichts zu tun war.
    """
    gesucht = sorted(z for z in ziele if z[1] in WARTE_NIDS)
    if usleep_fehlt or not gesucht:
        return elf, []
    eintraege = {(e.bibliothek, e.nid): e for e in plt_eintraege(elf)}
    usleep = eintraege.get(USLEEP_IMPORT)
    ergebnisse: list[StubErgebnis] = []
    puffer: "bytearray | None" = None
    for ziel in gesucht:
        e = eintraege.get(ziel)
        if e is None or e.schwach:
            continue
        frei = _plt_eintrag_original(elf, e) or _eigener_stub_da(elf, e, STUB_STANDARD)
        po = e.plt_offset
        if usleep is not None:
            if usleep.plt_offset == po or not _plt_eintrag_original(elf, usleep):
                continue

            def sprung(versatz: int) -> bytes:
                return _WARTE_KOPF + b"\xe9" + struct.pack("<i", usleep.plt_va - (e.plt_va + versatz + 10))

            erster_sprung = elf[po:po + 2] == _SPRUNG
            if ((erster_sprung and elf[po + LANDEPLATZ_OFFSET:po + PLT_LAENGE] == sprung(LANDEPLATZ_OFFSET))
                    or elf[po:po + 10] == sprung(0)):
                versatz = LANDEPLATZ_OFFSET if erster_sprung else 0
                ergebnisse.append(StubErgebnis(e.bibliothek, e.nid, ART_WARTEN_SPRUNG, po + versatz, STATUS_BEREITS))
                continue
            if not frei:
                continue
            versatz = LANDEPLATZ_OFFSET if landeplatz and erster_sprung else 0
            if puffer is None:
                puffer = bytearray(elf)
            puffer[po + versatz:po + versatz + 10] = sprung(versatz)
            ergebnisse.append(StubErgebnis(e.bibliothek, e.nid, ART_WARTEN_SPRUNG, po + versatz, STATUS_GESETZT))
            continue
        if not frei:
            continue
        versuch = bytearray(puffer if puffer is not None else elf)
        if not _import_umbenennen(versuch, ziel, USLEEP_IMPORT):
            continue
        eintrag = _WARTE_KOPF + _SPRUNG + struct.pack("<i", e.got_va - (e.plt_va + len(_WARTE_KOPF) + 6))
        versuch[po:po + PLT_LAENGE] = eintrag + b"\xcc" * (PLT_LAENGE - len(eintrag))
        puffer = versuch
        ergebnisse.append(StubErgebnis(e.bibliothek, e.nid, ART_WARTEN_IMPORT, po, STATUS_GESETZT))
    return (bytes(puffer) if puffer is not None else elf), ergebnisse


# --------------------------------------------------------------------------
# libc: Heap-Flags hinter dem Zeichenkettenpatch
# --------------------------------------------------------------------------

#: Der Import, auf den der libc-Patch (:data:`ps5_backport.LIBC_NEU`) die neue Map-Funktion umbiegt:
#: ``sceKernelMapFlexibleMemory`` (libkernel).
LIBC_MAP_IMPORT = ("libkernel", "IWIBBdTHit4")

#: ``mov ecx, 0x8000`` - das Flag, das eine libc ab SDK 7 der neuen Map-Funktion (``4h6F1LLbTiw``) mitgibt.
#: Die alte Funktion lehnt es auf jeder Firmware ab, auf die der Zeichenkettenpatch zielt: libkernel 4.00 bis 6.50
#: (entschluesselte Staende, 23.11.2026) prueft ``flags & 0xffbfff6f`` und meldet sonst 0x80020016 (EINVAL); 7.61 weist
#: ``0x88000`` vor dem Aufruf ausdruecklich ab. Gemessen an GTA V (PPSA04264, SDK-9-libc, FW 4.03, 23.11.2026): mit dem
#: Flag "Failed to create the heap" (r9 = 0x80020016), mit ``mov ecx, 0`` an den drei Aufrufstellen startet das Spiel.
#: Spiele, die malloc ersetzen (GT7), erreichen diesen Pfad nie - deshalb fiel es dort nicht auf.
LIBC_MAP_FLAG_ALT = bytes.fromhex("b900800000")
LIBC_MAP_FLAG_NEU = bytes.fromhex("b900000000")

#: So weit (Byte) vor dem Aufruf wird das Flag gesucht. Bei GTA V liegt es 11 bzw. 16 Byte davor.
LIBC_MAP_FENSTER = 32

_AUFRUF = re.compile(rb"[\xe8\xe9]")


class LibcFlagsErgebnis(NamedTuple):
    #: Aufrufe (``call``/``jmp rel32``) des Imports, die gefunden wurden.
    aufrufe: int
    #: Dateioffsets der korrigierten ``mov ecx``-Befehle.
    korrigiert: "tuple[int, ...]"
    #: Aufrufe, vor denen schon ``mov ecx, 0`` steht (frueherer Lauf).
    bereits: int
    #: Aufrufe ohne eindeutiges ``mov ecx, 0x8000`` im Fenster - bleiben unveraendert.
    unklar: int


def libc_map_flags_korrigieren(elf: bytes) -> "tuple[bytes, LibcFlagsErgebnis]":
    """Setzt vor jedem Aufruf von ``sceKernelMapFlexibleMemory`` das Flag ``0x8000`` auf 0 (siehe :data:`LIBC_MAP_FLAG_ALT`).

    Nur sinnvoll nach dem Zeichenkettenpatch der libc (:func:`ps5_backport.libc_patchen`): Erst dann ruft die libc die
    alte Funktion mit den Argumenten der neuen auf. Geaendert wird nur, wo im Fenster vor dem Aufruf **genau ein**
    ``mov ecx, 0x8000`` steht; alles andere bleibt und wird als ``unklar`` gezaehlt.

    Returns:
        (Bytes, Ergebnis). Die Bytes sind dasselbe Objekt, wenn nichts zu aendern war.
    """
    ziele = {e.plt_va for e in plt_eintraege(elf) if (e.bibliothek, e.nid) == LIBC_MAP_IMPORT}
    if not ziele:
        return elf, LibcFlagsErgebnis(0, (), 0, 0)
    aufrufe = bereits = unklar = 0
    korrigiert: list[int] = []
    for k in _koepfe(elf):
        if k.typ != PT_LOAD or not k.flags & PF_X:
            continue
        bis = min(k.offset + k.filesz, len(elf)) - 4
        for treffer in _AUFRUF.finditer(elf, k.offset, max(k.offset, bis)):
            pos = treffer.start()
            rel, = struct.unpack_from("<i", elf, pos + 1)
            if k.vaddr + (pos - k.offset) + 5 + rel not in ziele:
                continue
            aufrufe += 1
            anfang = max(k.offset, pos - LIBC_MAP_FENSTER)
            fenster = elf[anfang:pos]
            if fenster.count(LIBC_MAP_FLAG_ALT) == 1:
                korrigiert.append(anfang + fenster.index(LIBC_MAP_FLAG_ALT))
            elif LIBC_MAP_FLAG_ALT not in fenster and LIBC_MAP_FLAG_NEU in fenster:
                bereits += 1
            else:
                unklar += 1
    if not korrigiert:
        return elf, LibcFlagsErgebnis(aufrufe, (), bereits, unklar)
    puffer = bytearray(elf)
    for stelle in korrigiert:
        puffer[stelle:stelle + len(LIBC_MAP_FLAG_NEU)] = LIBC_MAP_FLAG_NEU
    return bytes(puffer), LibcFlagsErgebnis(aufrufe, tuple(korrigiert), bereits, unklar)


# --------------------------------------------------------------------------
# Spielvorgaben: Groesse der Ausgabestruktur
# --------------------------------------------------------------------------

#: ``sceUserServiceGetGamePresets``.
PRESETS_IMPORT = ("libSceUserService", "-sD02mFDBh4")

#: Die Groesse der Ausgabestruktur, die die Spiele ab SDK 7 eintragen, und die der Zielfirmware bis 6. Gemessen an
#: ``libSceUserService.sprx`` aller entpackten Staende (26.11.2026): Die IPMI-Huelle fordert bis 6.50 0x28 Byte an, ab
#: 7.01 0x30. Ein Spiel, das 0x30 eintraegt, bekommt auf FW 4.03 ``0x80960005`` vom Systemdienst. Der Unity-Player ab
#: 2022.3 verwirft daraufhin den angemeldeten Nutzer (Protokoll "sceUserServiceGetUserColor returned ... ignoring
#: event"), und das Spiel nimmt keinen Controller an. Gemessen an Valheim (PPSA28824, FW 4.03, 26.11.2026, Test I): mit
#: 0x28 geht der Controller, und die Vibration wirkt.
PRESETS_GROESSE_ALT = 0x30
PRESETS_GROESSE_NEU = 0x28

#: So weit (Byte) vor dem Aufruf wird die Groesse gesucht. Bei Valheim liegt sie 15 Byte davor.
PRESETS_FENSTER = 48

#: ``mov qword [rbp+d8], imm32`` und ``lea rsi, [rbp+d8]``.
_MOV_RBP_QWORD = re.compile(rb"\x48\xc7\x45(.)(.)\x00\x00\x00", re.S)
_LEA_RSI_RBP = b"\x48\x8d\x75"


class PresetsErgebnis(NamedTuple):
    #: Aufrufe des Imports in der Datei.
    aufrufe: int
    #: Dateioffsets der geaenderten Groessen-Bytes.
    korrigiert: tuple
    #: Aufrufe, vor denen schon die Groesse der Zielfirmware steht.
    bereits: int
    #: Aufrufe ohne eindeutige Groessenangabe - bleiben unveraendert.
    unklar: int


def _presets_groesse_im_fenster(fenster: bytes) -> "list[tuple[int, int]]":
    """(Stelle des Groessen-Bytes im Fenster, Wert) fuer jedes ``mov qword [rbp+d], imm`` mit passendem ``lea rsi``."""
    funde = []
    for treffer in _MOV_RBP_QWORD.finditer(fenster):
        versatz = treffer.group(1)
        if _LEA_RSI_RBP + versatz in fenster[treffer.end():]:
            funde.append((treffer.start(2), treffer.group(2)[0]))
    return funde


def presets_groesse_korrigieren(elf: bytes) -> "tuple[bytes, PresetsErgebnis]":
    """Setzt vor jedem Aufruf von ``sceUserServiceGetGamePresets`` die Strukturgroesse 0x30 auf 0x28 (Ziel bis FW 6).

    Gesucht wird im Fenster vor dem Aufruf genau ein ``mov qword [rbp+d], 0x30``, dessen Adresse danach als zweites
    Argument (``lea rsi, [rbp+d]``) uebergeben wird. Was davon abweicht, bleibt unveraendert und zaehlt als ``unklar``.

    Returns:
        (Bytes, Ergebnis). Die Bytes sind dasselbe Objekt, wenn nichts zu aendern war.
    """
    ziele = {e.plt_va for e in plt_eintraege(elf) if (e.bibliothek, e.nid) == PRESETS_IMPORT}
    if not ziele:
        return elf, PresetsErgebnis(0, (), 0, 0)
    aufrufe = bereits = unklar = 0
    korrigiert: list[int] = []
    for k in _koepfe(elf):
        if k.typ != PT_LOAD or not k.flags & PF_X:
            continue
        bis = min(k.offset + k.filesz, len(elf)) - 4
        for treffer in _AUFRUF.finditer(elf, k.offset, max(k.offset, bis)):
            pos = treffer.start()
            rel, = struct.unpack_from("<i", elf, pos + 1)
            if k.vaddr + (pos - k.offset) + 5 + rel not in ziele:
                continue
            aufrufe += 1
            anfang = max(k.offset, pos - PRESETS_FENSTER)
            funde = _presets_groesse_im_fenster(elf[anfang:pos])
            if len(funde) == 1 and funde[0][1] == PRESETS_GROESSE_ALT:
                korrigiert.append(anfang + funde[0][0])
            elif len(funde) == 1 and funde[0][1] == PRESETS_GROESSE_NEU:
                bereits += 1
            else:
                unklar += 1
    if not korrigiert:
        return elf, PresetsErgebnis(aufrufe, (), bereits, unklar)
    puffer = bytearray(elf)
    for stelle in korrigiert:
        puffer[stelle] = PRESETS_GROESSE_NEU
    return bytes(puffer), PresetsErgebnis(aufrufe, tuple(korrigiert), bereits, unklar)


# --------------------------------------------------------------------------
# Korrekturprofile
# --------------------------------------------------------------------------

PROFIL_FORMAT = 1
PROFIL_ORDNER = "Korrekturprofile"

_TITEL_ID = re.compile(r"[A-Z]{4}\d{5}")
_NID = re.compile(r"[A-Za-z0-9+\-]{11}")
_SHA = re.compile(r"[0-9a-f]{64}")


class ProfilFehler(ValueError):
    """Ein Profil ist unbrauchbar (Form, Werte)."""


class ProfilPatch(NamedTuple):
    zweck: str
    va: int
    alt: bytes
    neu: bytes


class ProfilStub(NamedTuple):
    bibliothek: str
    nid: str
    art: str


class ProfilDatei(NamedTuple):
    pfad: str
    sha256_elf: str
    patches: tuple
    stubs: tuple


class Profil(NamedTuple):
    titel_id: str
    name: str
    fassung: str
    firmware: tuple
    hinweis: str
    dateien: tuple
    quelle: str


def pfad_schluessel(pfad: str) -> str:
    """Vergleichsform eines relativen Pfads: Schraegstriche, Kleinschreibung."""
    return str(pfad).replace("\\", "/").strip("/").lower()


def _hex_bytes(wert, feld: str) -> bytes:
    try:
        roh = bytes.fromhex(str(wert).replace(" ", ""))
    except ValueError as exc:
        raise ProfilFehler("%s: keine Hex-Folge (%s)" % (feld, wert)) from exc
    if not roh:
        raise ProfilFehler("%s: leer" % feld)
    return roh


def profil_aus_dict(daten: object, quelle: str = "") -> Profil:
    """Prueft ein Profil streng und liefert es als :class:`Profil`.

    Raises:
        ProfilFehler: Form oder Werte stimmen nicht - ein halb verstandenes Profil darf nie schreiben.
    """
    if not isinstance(daten, dict):
        raise ProfilFehler("Profil ist kein Objekt")
    if daten.get("format") != PROFIL_FORMAT:
        raise ProfilFehler("format %r wird nicht unterstuetzt (erwartet %d)" % (daten.get("format"), PROFIL_FORMAT))
    titel = str(daten.get("titel_id", ""))
    if not _TITEL_ID.fullmatch(titel):
        raise ProfilFehler("titel_id %r ist keine Title-ID" % titel)
    firmware = daten.get("firmware")
    if (not isinstance(firmware, list) or not firmware
            or not all(isinstance(f, int) and not isinstance(f, bool) and 1 <= f <= 20 for f in firmware)):
        raise ProfilFehler("firmware muss eine Liste von Hauptversionen sein")
    roh_dateien = daten.get("dateien")
    if not isinstance(roh_dateien, list) or not roh_dateien:
        raise ProfilFehler("dateien fehlt oder ist leer")
    dateien = []
    gesehen = set()
    for i, d in enumerate(roh_dateien):
        wo = "dateien[%d]" % i
        if not isinstance(d, dict):
            raise ProfilFehler("%s: kein Objekt" % wo)
        pfad = str(d.get("pfad", "")).replace("\\", "/")
        teile = pfad.split("/")
        if not pfad or pfad.startswith("/") or ":" in pfad or any(t in ("", ".", "..") for t in teile):
            raise ProfilFehler("%s: pfad %r ist nicht relativ zum Spielordner" % (wo, pfad))
        if pfad_schluessel(pfad) in gesehen:
            raise ProfilFehler("%s: pfad %r kommt doppelt vor" % (wo, pfad))
        gesehen.add(pfad_schluessel(pfad))
        sha = str(d.get("sha256_elf", "")).lower()
        if not _SHA.fullmatch(sha):
            raise ProfilFehler("%s: sha256_elf ist keine SHA-256" % wo)
        patches = []
        for j, p in enumerate(d.get("patches", [])):
            pw = "%s.patches[%d]" % (wo, j)
            if not isinstance(p, dict):
                raise ProfilFehler("%s: kein Objekt" % pw)
            try:
                va = int(str(p.get("va", "")), 16)
            except ValueError as exc:
                raise ProfilFehler("%s: va ist keine Hex-Adresse" % pw) from exc
            alt, neu = _hex_bytes(p.get("alt"), pw + ".alt"), _hex_bytes(p.get("neu"), pw + ".neu")
            if len(alt) != len(neu):
                raise ProfilFehler("%s: alt und neu sind verschieden lang" % pw)
            if alt == neu:
                raise ProfilFehler("%s: alt und neu sind gleich" % pw)
            patches.append(ProfilPatch(str(p.get("zweck", "")), va, alt, neu))
        # Ueberlappende Aenderungen waeren nicht eindeutig.
        spannen = sorted((p.va, p.va + len(p.alt)) for p in patches)
        for (a0, a1), (b0, _b1) in zip(spannen, spannen[1:]):
            if b0 < a1:
                raise ProfilFehler("%s: Aenderungen ueberlappen bei 0x%X" % (wo, b0))
        stubs = []
        for j, s in enumerate(d.get("plt_stubs", [])):
            sw = "%s.plt_stubs[%d]" % (wo, j)
            if not isinstance(s, dict):
                raise ProfilFehler("%s: kein Objekt" % sw)
            bib, nid, art = str(s.get("bibliothek", "")), str(s.get("nid", "")), str(s.get("art", "standard"))
            if not bib or not _NID.fullmatch(nid):
                raise ProfilFehler("%s: bibliothek/nid unbrauchbar" % sw)
            if art not in STUB_ARTEN:
                raise ProfilFehler("%s: art %r unbekannt" % (sw, art))
            stubs.append(ProfilStub(bib, nid, art))
        if not patches and not stubs:
            raise ProfilFehler("%s: weder patches noch plt_stubs" % wo)
        dateien.append(ProfilDatei(pfad, sha, tuple(patches), tuple(stubs)))
    return Profil(titel, str(daten.get("name", titel)), str(daten.get("fassung", "")), tuple(firmware),
                  str(daten.get("hinweis", "")), tuple(dateien), quelle)


def profile_laden(ordner: "Iterable[str]") -> "tuple[list[Profil], list[str]]":
    """Liest alle ``*.json`` der Ordner.

    Returns:
        (Profile, Fehlertexte). Eine unbrauchbare Datei wird gemeldet und uebergangen, die anderen zaehlen weiter.
    """
    profile: list[Profil] = []
    fehler: list[str] = []
    for basis in ordner:
        if not basis or not os.path.isdir(basis):
            continue
        for name in sorted(os.listdir(basis)):
            if not name.lower().endswith(".json"):
                continue
            pfad = os.path.join(basis, name)
            try:
                with open(pfad, "r", encoding="utf-8-sig") as datei:
                    profile.append(profil_aus_dict(json.load(datei), pfad))
            except (OSError, ValueError) as exc:     # ProfilFehler und JSONDecodeError sind ValueError
                fehler.append("%s: %s" % (name, exc))
    return profile, fehler


def elf_aus_bytes(daten: bytes) -> "bytes | None":
    """Das ELF hinter einer Datei (SELF wird ausgepackt); ``None``, wenn es keines ist oder sich nicht auspacken laesst."""
    typ = bp.dateityp(daten)
    if typ == bp.TYP_ELF:
        return daten
    if typ == bp.TYP_SELF:
        try:
            return bp.self_zu_elf(daten)
        except bp.BackportFehler:
            return None
    return None


def elf_sha256(daten: bytes) -> str:
    """SHA-256 des ELF hinter einer Datei; leer, wenn es keines gibt.

    Das ELF und nicht die Datei: Dieselbe Programmdatei steckt je nach Dumper in verschiedenen SELF-Huellen.
    """
    elf = elf_aus_bytes(daten)
    return hashlib.sha256(elf).hexdigest() if elf is not None else ""


class AktivesProfil(NamedTuple):
    """Ein Profil, das auf diesen Dump und dieses Ziel passt, samt den SHA-256 der Originaldateien."""
    profil: Profil
    sha: dict


class Vorbereitung(NamedTuple):
    aktiv: tuple
    uebergangen: tuple          # (Profil, Grund) - Title-ID passt, aber nicht die Zielfirmware


def profile_vorbereiten(ordner: str, profile: "Iterable[Profil]", titel_id: str, firmware: int) -> Vorbereitung:
    """Waehlt die Profile des Titels und hasht die Originaldateien - **vor** dem Herabsetzen.

    Nach dem Herabsetzen traegt die Datei neue SDK-Werte und eine neue Huelle; die SHA-256 der Originale muss deshalb
    vorher gemessen werden.
    """
    aktiv, uebergangen = [], []
    for profil in profile:
        if profil.titel_id != titel_id:
            continue
        if int(firmware) not in profil.firmware:
            uebergangen.append((profil, "firmware"))
            continue
        sha = {}
        for datei in profil.dateien:
            pfad = os.path.join(ordner, *datei.pfad.split("/"))
            try:
                with open(pfad, "rb") as fh:
                    sha[pfad_schluessel(datei.pfad)] = elf_sha256(fh.read())
            except OSError:
                sha[pfad_schluessel(datei.pfad)] = ""
        aktiv.append(AktivesProfil(profil, sha))
    return Vorbereitung(tuple(aktiv), tuple(uebergangen))


P_ANGEWENDET = "angewendet"
P_BEREITS = "bereits"
P_SHA = "sha"
P_BYTES = "bytes"
P_STUB = "stub"
P_ADRESSE = "adresse"
P_DATEI = "datei"
P_SCHREIBEN = "schreiben"


class ProfilErgebnis(NamedTuple):
    pfad: str
    status: str
    patches: int
    stubs: int
    stelle: str          # bei Abweichungen: "0x175607" bzw. "<Bibliothek> <NID>"


def profil_datei_anwenden(elf: bytes, sha_original: str, pd: ProfilDatei, *,
                          landeplatz: bool = False) -> "tuple[bytes, ProfilErgebnis]":
    """Wendet die Aenderungen einer Profil-Datei an - ganz oder gar nicht.

    Reihenfolge der Pruefung: Adressen und Stubs auffindbar, dann Bytes. Stimmt die SHA-256 der Originaldatei
    (``sha_original``), muessen **alle** Stellen den alten Zustand tragen. Stimmt sie nicht, wird nichts geaendert;
    stehen dann an allen Stellen schon die neuen Bytes, heisst das "bereits angewendet" (zweiter Lauf).
    """
    stellen = []        # (offset, alt, neu, text)
    for p in pd.patches:
        offset = va_zu_offset(elf, p.va, len(p.alt))
        if offset is None:
            return elf, ProfilErgebnis(pd.pfad, P_ADRESSE, 0, 0, "0x%X" % p.va)
        stellen.append((offset, p.alt, p.neu, "0x%X" % p.va))
    eintraege = {(e.bibliothek, e.nid): e for e in plt_eintraege(elf)} if pd.stubs else {}
    stub_eintraege = []                 # (PLT-Eintrag, Art) je Stub des Profils
    for s in pd.stubs:
        e = eintraege.get((s.bibliothek, s.nid))
        if e is None:
            return elf, ProfilErgebnis(pd.pfad, P_STUB, 0, 0, "%s %s" % (s.bibliothek, s.nid))
        stub_offset, stub_bytes = stub_stelle(e, STUB_ARTEN[s.art], landeplatz)
        stellen.append((stub_offset, None, stub_bytes, "%s %s" % (s.bibliothek, s.nid)))
        stub_eintraege.append((e, STUB_ARTEN[s.art]))

    def ist_neu(offset: int, neu: bytes) -> bool:
        return elf[offset:offset + len(neu)] == neu

    def ist_alt(offset: int, alt: "bytes | None") -> bool:
        # ``None`` = ein Stub-Platz: noch der urspruengliche PLT-Eintrag, im Landeplatz-Modus mit ``push`` an Stelle 6.
        if alt is not None:
            return elf[offset:offset + len(alt)] == alt
        anfang = offset - (LANDEPLATZ_OFFSET if landeplatz else 0)
        return (elf[anfang:anfang + 2] == _SPRUNG
                and elf[anfang + LANDEPLATZ_OFFSET:anfang + LANDEPLATZ_OFFSET + 1] == bytes((_PUSH,)))

    alle_neu = all(ist_neu(o, n) for o, _a, n, _t in stellen)
    if sha_original != pd.sha256_elf:
        if alle_neu:
            return elf, ProfilErgebnis(pd.pfad, P_BEREITS, len(pd.patches), len(pd.stubs), "")
        if not landeplatz:
            umgesetzt = _profil_stubs_vom_landeplatz_holen(elf, stellen, stub_eintraege)
            if umgesetzt is not None:
                return umgesetzt[0], ProfilErgebnis(pd.pfad, P_ANGEWENDET, 0, umgesetzt[1], "")
        return elf, ProfilErgebnis(pd.pfad, P_SHA, 0, 0, "")
    for offset, alt, _neu, text in stellen:
        if not ist_alt(offset, alt):
            return elf, ProfilErgebnis(pd.pfad, P_BYTES, 0, 0, text)
    puffer = bytearray(elf)
    for offset, _alt, neu, _text in stellen:
        puffer[offset:offset + len(neu)] = neu
    return bytes(puffer), ProfilErgebnis(pd.pfad, P_ANGEWENDET, len(pd.patches), len(pd.stubs), "")


def _profil_stubs_vom_landeplatz_holen(elf: bytes, stellen: list, stub_eintraege: list) -> "tuple[bytes, int] | None":
    """Ein Profil, das am 21./22.11.2026 mit seinen Stubs auf dem Landeplatz angewendet wurde, auf die feste Form bringen.

    Seit 22.11.2026 stehen Profil-Stubs fest im Eintrag (:func:`korrekturen_anwenden`); auf dem Landeplatz erreicht sie der Lader bei
    einer Funktion, die die Zielfirmware doch hat, nie. Die SHA-256 stimmt bei so einer Datei nicht mehr (sie ist schon bearbeitet) -
    umgesetzt wird darum nur, wenn **alle** Byte-Aenderungen des Profils schon stehen und jeder Stub entweder fest oder in genau
    seiner Landeplatz-Form dasteht. ``None``: nicht diese Lage (dann bleibt es bei "andere Fassung").

    Nur bei einer Profil-Datei **mit** Byte-Aenderungen: Erst sie belegen die Fassung. Eine Datei nur mit Stubs (Anno 117:
    ``sce_module/libc.prx``) koennte sonst die Luecken-Stubs einer anderen Fassung fuer Profil-Stubs halten (gleiche Art, gleicher
    Landeplatz) - dort fehlen die Funktionen ohnehin, und der Landeplatz wirkt (Gegenlese 22.11.2026).
    """
    patches = [(o, n) for o, a, n, _t in stellen if a is not None]
    if not patches or not all(elf[o:o + len(n)] == n for o, n in patches):
        return None
    zu_setzen = []
    for e, art in stub_eintraege:
        if elf[e.plt_offset:e.plt_offset + len(art.bytes_)] == art.bytes_:
            continue
        kurz = art.landeplatz_bytes()
        if (elf[e.plt_offset:e.plt_offset + 2] == _SPRUNG
                and elf[e.plt_offset + LANDEPLATZ_OFFSET:e.plt_offset + LANDEPLATZ_OFFSET + len(kurz)] == kurz):
            zu_setzen.append((e, art))
            continue
        return None
    if not zu_setzen:
        return None
    puffer = bytearray(elf)
    for e, art in zu_setzen:
        puffer[e.plt_offset:e.plt_offset + len(art.bytes_)] = art.bytes_
    return bytes(puffer), len(zu_setzen)


# --------------------------------------------------------------------------
# Gesamtlauf ueber einen Dump
# --------------------------------------------------------------------------

class Bericht:
    """Was :func:`korrekturen_anwenden` getan hat (fuer das Protokoll der Oberflaeche)."""

    def __init__(self) -> None:
        self.profile: list[tuple[Profil, ProfilErgebnis]] = []
        self.stubs: list[tuple[str, StubErgebnis]] = []
        self.geaendert: list[str] = []
        self.fehler: list[tuple[str, str]] = []
        #: (Bibliothek, NID) der Luecken, die irgendwo gestubbt wurden - fuer die Restmeldung der Oberflaeche.
        self.neutralisiert: set = set()
        #: ``laeuft`` meldete einen Abbruch, bevor alle Dateien dran waren: Die Korrekturen stehen nur in einem Teil der Programme.
        self.abgebrochen = False


def _atomar_schreiben(pfad: str, daten: bytes) -> None:
    zwischen = pfad + ".neu"
    with open(zwischen, "wb") as fh:
        fh.write(daten)
    try:
        os.replace(zwischen, pfad)
    except PermissionError:
        import stat
        if not os.path.isfile(pfad):
            raise
        os.chmod(pfad, stat.S_IWRITE | stat.S_IREAD)
        os.replace(zwischen, pfad)


def korrekturen_anwenden(ordner: str, dateien: "Iterable[str]", *,
                         aktive: "Iterable[AktivesProfil]" = (),
                         luecken: "dict[str, Iterable[str]] | None" = None,
                         schreiben: "Callable[[str, bytes], None] | None" = None,
                         laeuft: "Callable[[], bool] | None" = None,
                         landeplatz: bool = False) -> Bericht:
    """Wendet Profile und Luecken-Stubs auf die Programmdateien eines Dumps an.

    Args:
        landeplatz: Die Stubs der **Luecken** im Landeplatz-Modus setzen (:func:`stubs_setzen`). Die Stubs eines **Profils** stehen
            immer fest im Eintrag: Ein Profil baut einen an der Konsole gemessenen Zustand nach (Anno 117, Test Z3, feste Stubs),
            und seine Stubs treffen gerade Funktionen, die die Zielfirmware oder eine Ersatzbibliothek doch liefert (Anno 117 auf
            FW 4: ``libSceAudioOut2 v8iOE+j8a5o`` hat die Firmware, ``TViD1EZXkNI`` die mitgelieferte ``libSceAudioOut.sprx``) -
            auf dem Landeplatz bindet der Lader sie, und der Stub wird nie erreicht. Eine Luecke, die ein Profil in derselben
            Datei schon stubbt, fasst der Luecken-Stub nicht noch einmal an.
        ordner: Wurzel des Dumps.
        dateien: Absolute Pfade der Kandidaten (:func:`ps5_backport.kandidaten`).
        aktive: Ergebnis von :func:`profile_vorbereiten`; leer = keine Profile.
        luecken: Bibliothek -> NIDs ohne Ersatz (:func:`ps5_backport.luecken_ohne_ersatz`); ``None`` = keine Stubs.
        schreiben: ``(Pfad, Bytes)`` ersetzt die Datei atomar; Vorgabe: Zwischendatei + ``os.replace``.
        laeuft: Gibt ``False`` zurueck, wenn abgebrochen werden soll (zwischen zwei Dateien).

    Jede Datei wird erst veraendert, wenn sich das Ergebnis neu signieren liess; scheitert etwas, bleibt sie wie sie
    war (:attr:`Bericht.fehler`).
    """
    bericht = Bericht()
    schreiben = schreiben or _atomar_schreiben
    nach_pfad: dict[str, list] = {}
    for a in aktive:
        for pd in a.profil.dateien:
            nach_pfad.setdefault(pfad_schluessel(pd.pfad), []).append((a, pd))
    if not nach_pfad and not luecken:
        return bericht

    for pfad in dateien:
        if laeuft is not None and not laeuft():
            bericht.abgebrochen = True
            break
        rel = os.path.relpath(pfad, ordner).replace("\\", "/")
        profile_hier = nach_pfad.get(pfad_schluessel(rel), [])
        if not profile_hier and not luecken:
            continue
        try:
            with open(pfad, "rb") as fh:
                roh = fh.read()
        except OSError as exc:
            bericht.fehler.append((rel, str(exc)))
            continue
        elf = elf_aus_bytes(roh)
        del roh
        if elf is None:
            for a, pd in profile_hier:
                bericht.profile.append((a.profil, ProfilErgebnis(pd.pfad, P_DATEI, 0, 0, "")))
            continue

        neu = elf
        profil_ergebnisse = []          # (Profil, Ergebnis, Profil-Datei)
        vom_profil: set = set()         # (Bibliothek, NID), die ein Profil in dieser Datei schon fest stubbt
        for a, pd in profile_hier:
            # Fest im Eintrag, nie auf dem Landeplatz (siehe ``landeplatz`` oben).
            neu, ergebnis = profil_datei_anwenden(neu, a.sha.get(pfad_schluessel(pd.pfad), ""), pd)
            profil_ergebnisse.append((a.profil, ergebnis, pd))
            if ergebnis.status in (P_ANGEWENDET, P_BEREITS):
                vom_profil.update((s.bibliothek, s.nid) for s in pd.stubs)
        stub_ergebnisse = []
        if luecken:
            luecken_hier = ({lib: [n for n in nids if (lib, n) not in vom_profil] for lib, nids in luecken.items()}
                            if vom_profil else luecken)
            neu, stub_ergebnisse = luecken_neutralisieren(neu, luecken_hier, landeplatz=landeplatz)
        if neu is not elf:
            try:
                schreiben(pfad, bp.elf_signieren(neu))
            except (bp.BackportFehler, OSError) as exc:
                # Nichts geschrieben: Was eben noch "angewendet" hiess, stimmt nicht.
                bericht.fehler.append((rel, str(exc)))
                profil_ergebnisse = [
                    (p, e._replace(status=P_SCHREIBEN, stelle=str(exc)) if e.status == P_ANGEWENDET else e, pd)
                    for p, e, pd in profil_ergebnisse]
                stub_ergebnisse = [s._replace(status=STATUS_FEHLT) if s.status == STATUS_GESETZT else s
                                   for s in stub_ergebnisse]
            else:
                bericht.geaendert.append(rel)
        for profil, ergebnis, pd in profil_ergebnisse:
            bericht.profile.append((profil, ergebnis))
            if ergebnis.status in (P_ANGEWENDET, P_BEREITS):
                # Auch die Stubs eines Profils schliessen Luecken - die Restmeldung der Oberflaeche zaehlt sie nicht mehr.
                bericht.neutralisiert.update((s.bibliothek, s.nid) for s in pd.stubs)
        for s in stub_ergebnisse:
            bericht.stubs.append((rel, s))
            if s.status in (STATUS_GESETZT, STATUS_BEREITS):
                bericht.neutralisiert.add((s.bibliothek, s.nid))
    return bericht
