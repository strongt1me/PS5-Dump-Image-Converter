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
    for idx, reloc in enumerate(relocs):
        if reloc is None or idx in stubs:
            continue
        pos = pos0 + PLT_LAENGE * idx
        if pos < 0 or pos + PLT_LAENGE > len(elf):
            continue
        eintrag = elf[pos:pos + PLT_LAENGE]
        if any(eintrag.startswith(b) for b in bekannt):
            stubs[idx] = (va0 + PLT_LAENGE * idx, pos)


# --------------------------------------------------------------------------
# Stub-Tabelle
# --------------------------------------------------------------------------

class StubArt(NamedTuple):
    kennung: str
    bytes_: bytes
    beschreibung: str


#: ``xor eax,eax; ret`` - die Funktion tut nichts und meldet Erfolg (0).
STUB_STANDARD = StubArt("standard", bytes.fromhex("31c0c3"), "xor eax,eax; ret")

#: ``mov dword [rdi],-1; mov dword [rsi],-1; xor eax,eax; ret`` - fuer Funktionen, deren Aufrufer zwei Ausgabeparameter
#: liest. 15 Byte, passt in den 16-Byte-PLT-Eintrag.
STUB_AUSGABEN_MINUS1 = StubArt(
    "ausgaben_minus1", bytes.fromhex("c707ffffffffc706ffffffff31c0c3"),
    "*rdi=*rsi=-1; xor eax,eax; ret")

#: Arten, die ein Profil beim Namen nennen darf.
STUB_ARTEN: dict[str, StubArt] = {a.kennung: a for a in (STUB_STANDARD, STUB_AUSGABEN_MINUS1)}

#: Ausnahmen von der Standard-Art je (Bibliothek, NID). Gemessen an Anno 117 (04.11.2026): ``NH6xARDOVv8`` (libkernel,
#: erst ab FW 11.00) hat drei Aufrufer, die danach ``cmp dword [rbp-0xe0],1`` auf einem AUSGABEPARAMETER ausfuehren;
#: das Original schreibt -1 hinein. Ohne die Schreibzugriffe liest der Aufrufer Stapelmuell.
#: **Regel fuer neue Eintraege:** Vor jedem Stub pruefen, ob der Aufrufer Rueckgabewert oder Ausgabeparameter auswertet.
#: Die allgemeine Neutralisierung kann das nicht - jede NID, die hier fehlt, bekommt den Standard-Stub.
STUB_TABELLE: dict[tuple[str, str], StubArt] = {
    ("libkernel", "NH6xARDOVv8"): STUB_AUSGABEN_MINUS1,
}

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
                 schwache_auslassen: bool = True) -> "tuple[bytes, list[StubErgebnis]]":
    """Ersetzt die PLT-Eintraege der genannten Importe durch Stubs.

    Args:
        elf: Das ELF (kein SELF).
        ziele: ``(Bibliothek, NID)`` -> Art-Kennung oder ``None`` (= :func:`stub_art`).
        schwache_auslassen: Schwach gebundene Importe nicht anfassen.

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
        stelle = elf[e.plt_offset:e.plt_offset + len(art.bytes_)]
        if stelle[:2] == _SPRUNG:
            if puffer is None:
                puffer = bytearray(elf)
            puffer[e.plt_offset:e.plt_offset + len(art.bytes_)] = art.bytes_
            status = STATUS_GESETZT
        elif stelle == art.bytes_:
            status = STATUS_BEREITS
        else:
            status = STATUS_ABWEICHEND
        ergebnisse.append(StubErgebnis(e.bibliothek, e.nid, art.kennung, e.plt_offset, status))
    return (bytes(puffer) if puffer is not None else elf), ergebnisse


def luecken_neutralisieren(elf: bytes, luecken: "dict[str, Iterable[str]]") -> "tuple[bytes, list[StubErgebnis]]":
    """Stubs fuer alle Luecken (Bibliothek -> NIDs), die diese Datei importiert.

    Die Luecken gelten fuer den ganzen Dump; was die Datei nicht importiert, wird uebergangen. Bibliotheken ohne
    ``lib``-Vorsatz bleiben unberuehrt: Die Exporttabelle der Firmware fuehrt sie nicht, eine "Luecke" dort waere nur
    eine Unkenntnis (Anno 117: ``ulobjmgr``).
    """
    ziele = {(lib, nid): None for lib, nids in luecken.items() if lib.startswith("lib") for nid in nids
             if (lib, nid) not in STUB_NIE}
    return stubs_setzen(elf, ziele)


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


def profil_datei_anwenden(elf: bytes, sha_original: str, pd: ProfilDatei) -> "tuple[bytes, ProfilErgebnis]":
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
    for s in pd.stubs:
        e = eintraege.get((s.bibliothek, s.nid))
        if e is None:
            return elf, ProfilErgebnis(pd.pfad, P_STUB, 0, 0, "%s %s" % (s.bibliothek, s.nid))
        art = STUB_ARTEN[s.art]
        stellen.append((e.plt_offset, None, art.bytes_, "%s %s" % (s.bibliothek, s.nid)))

    def ist_neu(offset: int, neu: bytes) -> bool:
        return elf[offset:offset + len(neu)] == neu

    def ist_alt(offset: int, alt: "bytes | None") -> bool:
        return elf[offset:offset + 2] == _SPRUNG if alt is None else elf[offset:offset + len(alt)] == alt

    alle_neu = all(ist_neu(o, n) for o, _a, n, _t in stellen)
    if sha_original != pd.sha256_elf:
        status = P_BEREITS if alle_neu else P_SHA
        return elf, ProfilErgebnis(pd.pfad, status, len(pd.patches) if alle_neu else 0,
                                   len(pd.stubs) if alle_neu else 0, "")
    for offset, alt, _neu, text in stellen:
        if not ist_alt(offset, alt):
            return elf, ProfilErgebnis(pd.pfad, P_BYTES, 0, 0, text)
    puffer = bytearray(elf)
    for offset, _alt, neu, _text in stellen:
        puffer[offset:offset + len(neu)] = neu
    return bytes(puffer), ProfilErgebnis(pd.pfad, P_ANGEWENDET, len(pd.patches), len(pd.stubs), "")


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
                         laeuft: "Callable[[], bool] | None" = None) -> Bericht:
    """Wendet Profile und Luecken-Stubs auf die Programmdateien eines Dumps an.

    Args:
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
        for a, pd in profile_hier:
            neu, ergebnis = profil_datei_anwenden(neu, a.sha.get(pfad_schluessel(pd.pfad), ""), pd)
            profil_ergebnisse.append((a.profil, ergebnis, pd))
        stub_ergebnisse = []
        if luecken:
            neu, stub_ergebnisse = luecken_neutralisieren(neu, luecken)
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
