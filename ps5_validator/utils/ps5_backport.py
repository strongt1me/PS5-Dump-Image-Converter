"""Backport: ausfuehrbare Dateien eines PS5-Dumps auf ein aelteres SDK setzen.

Ein Spiel prueft beim Start, mit welchem SDK es gebaut wurde, und laeuft nur auf
Firmware, die mindestens so neu ist. Diese Angabe steht unverschluesselt im
Modulkopf jeder ausfuehrbaren Datei. Wird sie herabgesetzt und die Datei danach
neu signiert, startet das Spiel auch auf aelterer Firmware.

Der Ablauf je Datei - die Reihenfolge ist zwingend::

    1. Typ bestimmen (ELF, SELF oder unbrauchbar)
    2. SELF -> ELF entpacken (nur bei SELF)
    3. SDK-Angabe im Modulkopf herabsetzen
    4. optionaler libc-Zeichenkettenpatch (nur 6.xx, nur libc.prx)
    5. ELF -> SELF neu signieren  *** nicht optional ***
    6. Original erst danach ersetzen

Nie signieren, bevor gepatcht wurde; nie den libc-Patch nach dem Signieren; nie
das Original anfassen, solange nicht beide Schritte gelungen sind. Dieses Modul
arbeitet daher ausschliesslich auf Bytefolgen im Speicher - wer schreibt,
entscheidet der Aufrufer.

Grundlagen: ``make_fself.py`` von john-tornblom (im Repo unter
``PlayGo & AMPR_EMU/PlayGo_v0.5/.../tools/make_fself.py``) fuer den Signierteil
und SelfUtil von CyB1K fuer das Entpacken. Beides ist hier nachgebaut, damit
kein Fremdwerkzeug und keine .NET-Laufzeit noetig ist.

Nichts davon entschluesselt irgendetwas: Die Segmentdaten eines fake-signierten
SELF liegen im Klartext im Container, das Entpacken ist reines Umkopieren.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
import shutil
import struct
from typing import Any

# --------------------------------------------------------------------------
# Dateikennungen
# --------------------------------------------------------------------------

#: ``\x7fELF`` - unverpacktes ELF.
MAGIC_ELF = 0x464C457F
#: Beide SELF-Kennungen kommen auf der PS5 vor und sind gleichwertig.
MAGIC_SELF_A = 0x1D3D154F
MAGIC_SELF_B = 0xEEF51454

TYP_ELF = "elf"
TYP_SELF = "self"
TYP_ELF_GESTRIPPT = "elf_gestrippt"
TYP_UNBEKANNT = "unbekannt"

# --------------------------------------------------------------------------
# ELF-Aufbau
# --------------------------------------------------------------------------

ELF_HEADER_FMT = "<4s5B6xB"          # magic, class, data, version, osabi, abiversion, identsize
ELF_HEADER_EX_FMT = "<2HI3QI6H"      # type, machine, version, entry, phoff, shoff, flags, ...
PHDR_FMT = "<2I6Q"                   # type, flags, offset, vaddr, paddr, filesz, memsz, align
PHDR_SIZE = struct.calcsize(PHDR_FMT)          # 0x38

E_PHOFF_OFFSET = 0x20
E_PHNUM_OFFSET = 0x38

PT_LOAD = 0x1
PT_SCE_RELRO = 0x61000010
PT_SCE_DYNLIBDATA = 0x61000000
PT_SCE_COMMENT = 0x6FFFFF00
PT_SCE_VERSION = 0x6FFFFF01
PT_SCE_PROCPARAM = 0x61000001
PT_SCE_MODULE_PARAM = 0x61000002

#: Segmente, die in den signierten Container uebernommen werden.
SIGNIERTE_SEGMENTE = (PT_LOAD, PT_SCE_RELRO, PT_SCE_DYNLIBDATA, PT_SCE_COMMENT)

# --------------------------------------------------------------------------
# Modulkopf (sceProcessParam / sceModuleParam)
# --------------------------------------------------------------------------

SCE_PROCESS_PARAM_MAGIC = 0x4942524F
SCE_MODULE_PARAM_MAGIC = 0x3C13F4BF

PARAM_MAGIC_OFFSET = 0x08
PARAM_PS4_SDK_OFFSET = 0x10
PARAM_PS5_SDK_OFFSET = 0x14
PARAM_MINDESTGROESSE = PARAM_PS5_SDK_OFFSET + 4

# --------------------------------------------------------------------------
# SELF-Aufbau (Signieren)
# --------------------------------------------------------------------------

SELF_COMMON_HEADER_FMT = "<4s4B"
SELF_EXT_HEADER_FMT = "<I2HQ2H4x"
SELF_ENTRY_FMT = "<4Q"
SELF_EXINFO_FMT = "<4Q32s"
SELF_NPDRM_FMT = "<H14x19s13s"
SELF_METABLOCK_FMT = "<80x"
SELF_METAFOOTER_FMT = "<48xI28x"

SELF_MAGIC = b"\x4F\x15\x3D\x1D"
SELF_VERSION = 0x00
SELF_MODE = 0x01
SELF_ENDIAN = 0x01
SELF_ATTRIBS = 0x12
SELF_KEY_TYPE = 0x101

FLAGS_SEGMENT_SIGNED_SHIFT = 4
FLAGS_SEGMENT_SIGNED_MASK = 0x7

DIGEST_SIZE = 0x20
SIGNATURE_SIZE = 0x100
BLOCK_SIZE = 0x4000

NPDRM_TYPE = 0x3
NPDRM_CONTENT_ID_SIZE = 0x13
NPDRM_RANDOM_PAD_SIZE = 0xD

#: Standardwerte aus make_fself - ein Fake-Paket ohne echte Signatur.
PAID_STANDARD = 0x3100000000000002
PTYPE_FAKE = 0x1

# Bitfelder im ``props``-Feld eines SELF-Eintrags.
PROPS_SIGNED_SHIFT = 2
PROPS_HAS_BLOCKS_SHIFT = 11
PROPS_BLOCK_SIZE_SHIFT = 12
PROPS_HAS_DIGESTS_SHIFT = 16
PROPS_SEGMENT_INDEX_SHIFT = 20
PROPS_SEGMENT_INDEX_MASK = 0xFFFF
#: Segmentdaten liegen verschluesselt bzw. komprimiert im Container - dieselben
#: Bits wie ``self_reader.SEGMENT_FLAG_ENCRYPTED``/``_COMPRESSED``.
PROPS_VERSCHLUESSELT = 0x2
PROPS_KOMPRIMIERT = 0x8

# --------------------------------------------------------------------------
# Firmware-Profile
# --------------------------------------------------------------------------

#: Firmware-Hauptversion -> (PS5-SDK, PS4-SDK). Werte aus PS5 BackPork Kitchen.
#:
#: **Warum die Tabelle bei 10 aufhoert** (nachgesehen am 07.09.2026, damit es
#: nicht ein zweites Mal untersucht wird):
#:
#: Die Vorlage - ``core/VersionProfiles.vb`` aus PS5 BACKPORK KITCHEN 2.3.1,
#: der neuesten Fassung - endet Eintrag fuer Eintrag wertgleich ebenfalls bei
#: 10. Ihr ``Ps4SdkResolver.vb`` ist eine feste Nachschlagliste mit
#: Rueckfallwert, keine Rechenregel. Diese Tabelle hinkt also nicht hinterher.
#:
#: Ableitbar ist nur ein Teil: Das PS5-Hauptbyte ist die BCD-Firmware
#: (10 -> ``0x10``), und die PS4-Seite steigt ab Firmware 5 regelmaessig um
#: 0.50 (FW 11 -> ``0x12590001``, 12 -> ``0x13090001``). Die **PS5-Baunummer**,
#: also die unteren 16 Bit, folgt keiner Regel - 0x50, 0x09, 0x27, 0x31, 0x33,
#: 0x38, 0x38, 0x41, 0x40, 0x40. Sie ist gemessen, nicht gerechnet, und laesst
#: sich nur aus einem echten Modul dieser Firmware lesen.
#:
#: Kernel-Offset-Tabellen (``sdk-0.42/crt/kernel.c``, ``sdkVersionHex.ts`` aus
#: PS5Upload) kennen zwar 13.00 bis 13.60, taugen hier aber **nicht**: Das sind
#: Exploit-Offsets und blanke BCD-Firmwarewoerter ohne Baunummer und ohne
#: PS4-Partnerwert.
#:
#: **Nachtrag 07.09.2026 - 11 und 12 sind jetzt gemessen.** Aus einem Bestand
#: entpackter Firmware (1.00 bis 12.70) wurde der Modulkopf von
#: ``system/common/lib/libSceAgc.sprx`` gelesen, je Stand gegen fuenf weitere
#: Module gegengeprueft (alle sechs stimmten ueberein). Ergebnis fuer die
#: ``x.00``-Staende: 11.00 -> ``0x11000043`` / ``0x12590001``, 12.00 ->
#: ``0x12000043`` / ``0x13090001``. Die oben vermutete PS4-Ableitung war damit
#: richtig; nur die Baunummer liess sich wie beschrieben nicht rechnen.
#:
#: **Warum die Werte 1 bis 10 trotzdem stehenbleiben.** Dieselbe Messung
#: liefert fuer sie *andere* Baunummern als die Vorlage - 4.00 misst
#: ``0x04000042`` statt ``0x04000031``, 6.00 misst ``0x06000042`` statt
#: ``0x06000038``, 9.00 misst ``0x09000045`` statt ``0x09000040``. Das ist
#: kein Widerspruch: Der Modulkopf einer Systembibliothek traegt die SDK-
#: Fassung, mit der **sie** gebaut wurde, nicht den Wert, den ein
#: herabgesetztes Spiel tragen muss. Geprueft wird beim Start ohnehin gegen
#: Haupt- und Nebenversion; die unteren Bits sind Beiwerk. Die Werte 1 bis 10
#: sind in der Szene erprobt, die gemessenen sind es nicht - deshalb bleiben
#: sie unangetastet, und 11/12 folgen ihrer Form (Nebenversion 00).
#:
#: Ersatzbibliotheken bleiben die eigentliche Huerde: mitgeliefert werden nur
#: 4 bis 7 (rechtlich, nicht technisch - siehe ``firmwares_mit_bestand``).
#: Ein Eintrag hier macht einen Stand also noch nicht waehlbar.
SDK_PAARE: dict[int, tuple[int, int]] = {
    1: (0x01000050, 0x07590001),
    2: (0x02000009, 0x08050001),
    3: (0x03000027, 0x08540001),
    4: (0x04000031, 0x09040001),
    5: (0x05000033, 0x09590001),
    6: (0x06000038, 0x10090001),
    7: (0x07000038, 0x10590001),
    8: (0x08000041, 0x11090001),
    9: (0x09000040, 0x11590001),
    10: (0x10000040, 0x12090001),
    11: (0x11000043, 0x12590001),
    12: (0x12000043, 0x13090001),
}

#: Firmware-Staende, fuer die Ersatzbibliotheken mitgeliefert werden.
FIRMWARE_MIT_FAKELIBS: tuple[int, ...] = (4, 5, 6, 7)

#: Voreinstellung - deckt die verbreitetsten gejailbreakten Konsolen ab.
FIRMWARE_STANDARD = 7

#: Dateien, die ueberhaupt in Frage kommen.
EBOOT_NAME = "eboot.bin"
MODUL_ENDUNGEN = (".prx", ".sprx")

#: Zeichenkettenpatch fuer libc.prx unter 6.xx. Beide Folgen sind gleich lang;
#: das ist Bedingung, sonst verschoebe sich alles dahinter.
LIBC_ALT = b"4h6F1LLbTiw#A#B"
LIBC_NEU = b"IWIBBdTHit4#A#B"

#: Bis zu dieser Ziel-Firmware (einschliesslich) wird der libc-Patch angewendet. Darueber nimmt Auto-Backpork
#: (Nazky, ``Backport.py``: ``if sdk_pair <= 6: apply_libc_patch ... elif auto_revert_for_high_sdk: revert``) ihn
#: zurueck, und ein Ziel von 7 oder hoeher bekommt die Datei unveraendert. Bis zum 22.10.2026 wurde er hier auf
#: jedes Ziel angewendet, obwohl er nur fuer 6.xx und darunter gedacht ist.
LIBC_PATCH_BIS = 6

#: Ordner, in den die Ersatzbibliotheken im Spiel gelegt werden.
FAKELIB_ORDNER = "fakelib"

#: Der zweite Ordnername. **Welcher von beiden wirkt, haengt von der Fassung
#: UND vom Ort ab** - die Regeln stehen in ``shadowmount_generation``, nicht
#: hier.
#:
#: Bis zum 05.09.2026 stand an dieser Stelle "den ShadowMount+ **bevorzugt**
#: einhaengt", belegt mit der config.ini von 1.7alpha6:
#:   "mount app0/fakelib2 when present, otherwise app0/fakelib, into common/lib"
#:
#: Das ist zweifach unzuverlaessig. Erstens gilt es nur bis alpha6: Ab alpha8
#: sucht ShadowMount+ ``fakelib2`` ausschliesslich im **Backport-Ordner**; aus
#: dem Spielordner kommt nur noch ``fakelib`` (README alpha8 Z. 190 bis
#: alpha12 unveraendert). Zweitens ist ausgerechnet die zitierte Zeile der
#: schlechteste Beleg: Sie steht in **allen** vorliegenden Fassungen bis
#: alpha12 bytegleich da, waehrend die README daneben laengst etwas anderes
#: sagt - ShadowMount+ widerspricht sich in der eigenen Dokumentation, und der
#: config-Kommentar ist der stehengebliebene Text.
#:
#: Nachtrag 28.09.2026: Ab 1.7beta1 (auch 1.7beta2) liest ShadowMount+ im
#: Spielordner wieder erst ``fakelib2``, dann ``fakelib`` (am Quelltext
#: gemessen, README Z. 188 "in the same order") - die Ausnahme ist die Stufe
#: alpha8 bis alpha13fix1. Es wird weiterhin immer nur EINER von beiden
#: eingehaengt.
FAKELIB2_ORDNER = "fakelib2"

#: Beide Namen, fuer Suchen und Pruefungen.
FAKELIB_ORDNERNAMEN = (FAKELIB_ORDNER, FAKELIB2_ORDNER)


class BackportFehler(Exception):
    """Eine Datei liess sich nicht verarbeiten."""


class SdkNichtGefunden(BackportFehler):
    """Die Datei traegt keinen Modulkopf mit SDK-Angabe."""


# --------------------------------------------------------------------------
# Kleine Helfer
# --------------------------------------------------------------------------

def _aufrunden(wert: int, schritt: int) -> int:
    """Naechstes Vielfaches von ``schritt`` ab ``wert``."""
    return (wert + schritt - 1) & ~(schritt - 1)


def dateityp(daten: bytes) -> str:
    """Bestimmt, womit man es zu tun hat.

    Args:
        daten: Anfang der Datei (mindestens 64 Bytes fuer die Stripped-Erkennung).

    Returns:
        Eine der Konstanten ``TYP_*``.
    """
    if not daten or len(daten) < 4:
        return TYP_UNBEKANNT
    kennung = struct.unpack_from("<I", daten, 0)[0]
    if kennung == MAGIC_ELF:
        return TYP_ELF
    if kennung in (MAGIC_SELF_A, MAGIC_SELF_B):
        return TYP_SELF
    if _sieht_aus_wie_gestripptes_elf(daten):
        return TYP_ELF_GESTRIPPT
    return TYP_UNBEKANNT


def _sieht_aus_wie_gestripptes_elf(daten: bytes) -> bool:
    """Erkennt ein ELF, dem die Kennung abgeschnitten wurde.

    Rein heuristisch: Kopfgroesse, Eintragsgroesse und eine plausible Zahl von
    Programmkopfeintraegen innerhalb der Datei.
    """
    if len(daten) < 64:
        return False
    try:
        ehsize, phentsize, phnum = struct.unpack_from("<3H", daten, 0x34)
        phoff = struct.unpack_from("<Q", daten, E_PHOFF_OFFSET)[0]
    except struct.error:
        return False
    return (ehsize == 64 and phentsize == PHDR_SIZE
            and 0 < phnum < 100 and phoff < len(daten))


def ist_kandidat(name: str) -> bool:
    """True fuer Dateien, die ueberhaupt gepatcht werden koennen."""
    klein = os.path.basename(str(name or "")).lower()
    return klein == EBOOT_NAME or klein.endswith(MODUL_ENDUNGEN)


#: Die ersten vier Bytes einer ELF-Datei und der beiden SELF-Behaelter (PS4 und PS5).
_KENNUNGEN = (b"\x7fELF", b"\x4f\x15\x3d\x1d", b"\x54\x14\xf5\xee")


def _hat_programmkennung(pfad: str) -> bool:
    """Beginnt die Datei mit der Kennung eines ELF oder SELF? (Auto-Backpork prueft jede Datei so.)"""
    try:
        with open(pfad, "rb") as datei:
            return datei.read(4) in _KENNUNGEN
    except OSError:
        return False


# Gesucht wird nach dem Namen (``eboot.bin``, ``*.prx``, ``*.sprx``) **und** nach der Kennung am Dateianfang:
# Auto-Backpork behandelt jede Datei, die ein ELF oder SELF ist, gleich welchen Namens. Eine Programmdatei mit
# anderem Namen (``.elf``, ``.self``, andere ``.bin``) blieb hier bis zum 22.10.2026 auf der hohen Firmware.
# Datensicherungen (``.bak``) zaehlen nicht.
def kandidaten(ordner: str) -> list[str]:
    """Sammelt alle patchbaren Dateien eines Dump-Ordners (Namen und ELF/SELF-Kennung).

    Der Ordner ``fakelib`` bleibt aussen vor: Er enthaelt die mitgelieferten
    Ersatzbibliotheken, die bereits auf die Zielfirmware passen.
    """
    gefunden: list[str] = []
    for wurzel, ordnernamen, dateinamen in os.walk(str(ordner or "")):
        # Beide Bibliotheksordner ueberspringen: Ihr Inhalt passt bereits auf die
        # Zielfirmware und darf nicht noch einmal gepatcht werden.
        ordnernamen[:] = [d for d in ordnernamen
                          if d.lower() not in FAKELIB_ORDNERNAMEN]
        for name in sorted(dateinamen):
            pfad = os.path.join(wurzel, name)
            if ist_kandidat(name) or (not name.lower().endswith(".bak") and _hat_programmkennung(pfad)):
                gefunden.append(pfad)
    return sorted(gefunden)


#: Die zwei Felder der ``sce_sys/param.json``, die der PS5-App-Dumper (EchoStretch, ``ps5_backport_param_json``) beim
#: Backport herabsetzt: die Firmware, die das Spiel verlangt, und die SDK-Hauptversion. Beide stehen als 18-stelliger
#: Hex-Text, die ersten zwei Ziffern nach ``0x`` sind die Hauptversion (``0x1160...`` = 11.60, ``0x1000...`` = SDK 10).
PARAM_FELDER = ("requiredSystemSoftwareVersion", "sdkVersion")

_PARAM_MUSTER = {
    feld: re.compile(rb'("' + feld.encode("ascii") + rb'"\s*:\s*")(0[xX][0-9A-Fa-f]{16})(")')
    for feld in PARAM_FELDER
}


def param_json_herabsetzen(daten: bytes, firmware: int) -> tuple[bytes, list[tuple[str, str, str]]]:
    """Setzt ``requiredSystemSoftwareVersion`` und ``sdkVersion`` auf ``0xMM00000000000000``, wenn ihre Hauptversion
    ueber dem Ziel liegt (Auto: wie der PS5-App-Dumper).

    Es wird nur der Wert ersetzt, der Rest der Datei bleibt Byte fuer Byte; je Feld zaehlt das erste Vorkommen. Ein
    Wert auf oder unter der Zielversion bleibt, auch mit hoeherer Nebenversion - wie beim Dumper.

    Returns:
        ``(neue Bytes, [(Feld, alt, neu), ...])``; die Liste ist leer, wenn nichts zu aendern war.

    Raises:
        BackportFehler: unbekannte Firmware.
    """
    ziel = (sdk_paar(firmware)[0] >> 24) & 0xFF
    neu_wert = "0x%02X00000000000000" % ziel
    aenderungen: list[tuple[str, str, str]] = []
    for feld in PARAM_FELDER:
        treffer = _PARAM_MUSTER[feld].search(daten)
        if not treffer:
            continue
        alt = treffer.group(2).decode("ascii")
        if int(alt[2:4], 16) <= ziel:
            continue
        daten = daten[:treffer.start(2)] + neu_wert.encode("ascii") + daten[treffer.end(2):]
        aenderungen.append((feld, alt, neu_wert))
    return daten, aenderungen


def param_json_anpassen(ordner: str, firmware: int) -> list[tuple[str, str, str]]:
    """Wendet :func:`param_json_herabsetzen` auf ``<ordner>/sce_sys/param.json`` an - atomar, ueber eine Zwischendatei.

    Returns:
        Die Aenderungen (leer, wenn es die Datei nicht gibt oder nichts zu aendern war).

    Raises:
        OSError: Lesen oder Schreiben scheitert - die Datei ist dann unveraendert.
    """
    pfad = os.path.join(str(ordner or ""), "sce_sys", "param.json")
    if not os.path.isfile(pfad):
        return []
    with open(pfad, "rb") as datei:
        roh = datei.read()
    neu, aenderungen = param_json_herabsetzen(roh, firmware)
    if not aenderungen:
        return []
    zwischen = pfad + ".bp_neu"
    try:
        with open(zwischen, "wb") as datei:
            datei.write(neu)
        os.replace(zwischen, pfad)
    except OSError:
        try:
            if os.path.isfile(zwischen):
                os.remove(zwischen)
        except OSError:
            pass
        raise
    return aenderungen


def firmware_text(ps5_sdk: int) -> str:
    """Formt eine SDK-Zahl in die uebliche Schreibweise um (``0x07000038`` -> ``7.00``)."""
    haupt = (int(ps5_sdk) >> 24) & 0xFF
    neben = (int(ps5_sdk) >> 16) & 0xFF
    return f"{haupt:X}.{neben:02X}"


def sdk_paar(firmware: int) -> tuple[int, int]:
    """SDK-Paar zu einer Firmware-Hauptversion.

    Raises:
        BackportFehler: Unbekannte Firmware.
    """
    try:
        return SDK_PAARE[int(firmware)]
    except (KeyError, TypeError, ValueError):
        raise BackportFehler(f"Unbekannte Firmware: {firmware}") from None


def muss_gepatcht_werden(aktuell: int, ziel: int) -> bool:
    """Nur herabsetzen, nie anheben - alles andere bleibt unangetastet."""
    return int(aktuell) > int(ziel)


# --------------------------------------------------------------------------
# SDK-Angabe lesen und setzen
# --------------------------------------------------------------------------

def _param_segment_finden(elf: bytes) -> int:
    """Offset des Modulkopfs im ELF, oder -1.

    Sucht im Programmkopf nach ``PT_SCE_PROCPARAM`` bzw. ``PT_SCE_MODULE_PARAM``
    und prueft die Kennung im Segment selbst - ein Typtreffer allein genuegt
    nicht, sonst wuerde bei einer beschaedigten Datei ins Leere geschrieben.
    """
    if len(elf) < 64:
        return -1
    phoff = struct.unpack_from("<Q", elf, E_PHOFF_OFFSET)[0]
    phnum = struct.unpack_from("<H", elf, E_PHNUM_OFFSET)[0]
    for i in range(phnum):
        basis = phoff + i * PHDR_SIZE
        if basis + PHDR_SIZE > len(elf):
            return -1
        typ = struct.unpack_from("<I", elf, basis)[0]
        if typ not in (PT_SCE_PROCPARAM, PT_SCE_MODULE_PARAM):
            continue
        seg_offset = struct.unpack_from("<Q", elf, basis + 0x08)[0]
        if seg_offset + PARAM_MINDESTGROESSE > len(elf):
            return -1
        groesse = struct.unpack_from("<I", elf, seg_offset)[0]
        if groesse < PARAM_MINDESTGROESSE:
            return -1
        kennung = struct.unpack_from("<I", elf, seg_offset + PARAM_MAGIC_OFFSET)[0]
        erwartet = (SCE_PROCESS_PARAM_MAGIC if typ == PT_SCE_PROCPARAM
                    else SCE_MODULE_PARAM_MAGIC)
        if kennung != erwartet:
            return -1
        return seg_offset
    return -1


def sdk_lesen(elf: bytes) -> tuple[int, int]:
    """Liest PS5- und PS4-SDK aus einem entpackten ELF.

    Raises:
        SdkNichtGefunden: Kein auswertbarer Modulkopf vorhanden.
    """
    offset = _param_segment_finden(elf)
    if offset < 0:
        raise SdkNichtGefunden("Kein Modulkopf mit SDK-Angabe gefunden.")
    ps4 = struct.unpack_from("<I", elf, offset + PARAM_PS4_SDK_OFFSET)[0]
    ps5 = struct.unpack_from("<I", elf, offset + PARAM_PS5_SDK_OFFSET)[0]
    return ps5, ps4


def sdk_setzen(elf: bytes, ziel_ps5: int, ziel_ps4: int) -> tuple[bytes, int, int]:
    """Setzt die SDK-Angabe im Modulkopf.

    Returns:
        (neue Bytes, altes PS5-SDK, altes PS4-SDK)

    Raises:
        SdkNichtGefunden: Kein auswertbarer Modulkopf vorhanden.
    """
    offset = _param_segment_finden(elf)
    if offset < 0:
        raise SdkNichtGefunden("Kein Modulkopf mit SDK-Angabe gefunden.")
    puffer = bytearray(elf)
    alt_ps4 = struct.unpack_from("<I", puffer, offset + PARAM_PS4_SDK_OFFSET)[0]
    alt_ps5 = struct.unpack_from("<I", puffer, offset + PARAM_PS5_SDK_OFFSET)[0]
    struct.pack_into("<I", puffer, offset + PARAM_PS4_SDK_OFFSET, int(ziel_ps4))
    struct.pack_into("<I", puffer, offset + PARAM_PS5_SDK_OFFSET, int(ziel_ps5))
    return bytes(puffer), alt_ps5, alt_ps4


# --------------------------------------------------------------------------
# SELF -> ELF
# --------------------------------------------------------------------------

def self_segmente_verschluesselt(daten: bytes) -> bool:
    """Ob ein SELF seine Segmente verschluesselt oder komprimiert ablegt.

    :func:`self_zu_elf` setzt die Segmente nur Byte fuer Byte zurueck. Aus
    einem nicht entschluesselten Container kommt dabei Datensalat, in dem
    kein Modulkopf zu finden ist - bis zum 24.09.2026 hiess das dann nur
    "keine SDK-Angabe enthalten", die Datei galt als uebersprungen und der
    Lauf als gelungen (Durchsicht, U2-4). Geprueft werden nur die
    Daten-Eintraege (Bit 11); die Meta-Eintraege tragen die Pruefsummen.
    """
    if len(daten) < 0x20:
        return False
    try:
        kennung = struct.unpack_from("<I", daten, 0)[0]
        anzahl = struct.unpack_from("<H", daten, 0x18)[0]
    except struct.error:
        return False
    if kennung not in (MAGIC_SELF_A, MAGIC_SELF_B):
        return False
    for index in range(anzahl):
        eintrag = 0x20 * (1 + index)
        if eintrag + 0x20 > len(daten):
            break
        props = struct.unpack_from("<Q", daten, eintrag)[0]
        if not (props >> PROPS_HAS_BLOCKS_SHIFT) & 0x1:
            continue
        if props & (PROPS_VERSCHLUESSELT | PROPS_KOMPRIMIERT):
            return True
    return False


def self_zu_elf(daten: bytes) -> bytes:
    """Holt das eingebettete ELF aus einem SELF-Container.

    Nachbau von SelfUtil: Der Container legt die Segmente unveraendert ab, das
    Entpacken setzt sie nur wieder an ihre ELF-Offsets zurueck.

    Raises:
        BackportFehler: Kein SELF oder kein eingebettetes ELF auffindbar.
    """
    if len(daten) < 0x20:
        raise BackportFehler("Datei zu kurz für einen SELF-Container.")
    kennung = struct.unpack_from("<I", daten, 0)[0]
    if kennung not in (MAGIC_SELF_A, MAGIC_SELF_B):
        raise BackportFehler("Keine SELF-Kennung am Dateianfang.")

    anzahl_eintraege = struct.unpack_from("<H", daten, 0x18)[0]

    # 1) Eingebetteten ELF-Kopf suchen - er liegt hinter der Eintragstabelle.
    such_ab = (1 + anzahl_eintraege) * 0x20
    elf_offset = -1
    for i in range(such_ab, len(daten) - 4):
        if struct.unpack_from("<I", daten, i)[0] == MAGIC_ELF:
            elf_offset = i
            break
    if elf_offset < 0:
        raise BackportFehler("Kein eingebettetes ELF im SELF-Container gefunden.")

    # 2) Programmkopftabelle des eingebetteten ELF auswerten.
    e_phoff = struct.unpack_from("<Q", daten, elf_offset + E_PHOFF_OFFSET)[0]
    e_phentsize = struct.unpack_from("<H", daten, elf_offset + 0x36)[0]
    e_phnum = struct.unpack_from("<H", daten, elf_offset + E_PHNUM_OFFSET)[0]
    pht = elf_offset + e_phoff
    if e_phentsize == 0 or e_phnum == 0:
        raise BackportFehler("Eingebettetes ELF hat keine Programmkopftabelle.")

    def kopf(i: int) -> tuple[int, int, int]:
        """(Typ, Offset, Dateigroesse) des i-ten Programmkopfeintrags."""
        basis = pht + i * e_phentsize
        if basis + PHDR_SIZE > len(daten):
            raise BackportFehler("Programmkopftabelle reicht über das Dateiende hinaus.")
        typ = struct.unpack_from("<I", daten, basis)[0]
        offset = struct.unpack_from("<Q", daten, basis + 0x08)[0]
        filesz = struct.unpack_from("<Q", daten, basis + 0x20)[0]
        return typ, offset, filesz

    # 3) Erstes und letztes Segment bestimmen - daraus ergibt sich die Groesse.
    erstes_offset = 0
    erstes_gefunden = False
    letztes_offset = 0
    letzte_groesse = 0
    for i in range(e_phnum):
        _typ, offset, filesz = kopf(i)
        if offset > 0 and (not erstes_gefunden or offset < erstes_offset):
            erstes_offset = offset
            erstes_gefunden = True
        if offset >= letztes_offset:
            letztes_offset = offset
            letzte_groesse = filesz
    gesamt = letztes_offset + letzte_groesse
    if gesamt <= 0 or gesamt > (1 << 34):
        raise BackportFehler(f"Unglaubwürdige ELF-Größe: {gesamt}")

    ausgabe = bytearray(gesamt)

    # 4) Kopfbereich uebernehmen (bis zum ersten Segment).
    kopf_laenge = min(int(erstes_offset), gesamt, len(daten) - elf_offset)
    ausgabe[:kopf_laenge] = daten[elf_offset:elf_offset + kopf_laenge]

    # 5) Segmentdaten anhand der SELF-Eintraege an ihren Platz kopieren.
    #
    # Jedes Segment hat zwei Eintraege: einen Meta-Eintrag mit den Pruefsummen
    # und einen Daten-Eintrag mit dem Segment selbst. Nur der Daten-Eintrag
    # traegt Bit 11 (hat Bloecke); sein segment_index zeigt auf den zugehoerigen
    # Programmkopf. Beim Meta-Eintrag zeigt dasselbe Feld dagegen auf den
    # Partner-Eintrag - wird er mitkopiert, landen 32 Byte Pruefsumme an einer
    # voellig fremden Stelle. In einem Backup fiel genau das auf: Der Meta-
    # Eintrag zu Segment 5 schrieb auf Offset 0 und loeschte den ELF-Kopf.
    for index in range(anzahl_eintraege):
        eintrag = 0x20 * (1 + index)
        if eintrag + 0x20 > len(daten):
            break
        props, quelle, filesz, _memsz = struct.unpack_from(SELF_ENTRY_FMT, daten, eintrag)
        if filesz == 0:
            continue
        if not (props >> PROPS_HAS_BLOCKS_SHIFT) & 0x1:
            continue
        ph_index = (props >> PROPS_SEGMENT_INDEX_SHIFT) & PROPS_SEGMENT_INDEX_MASK
        if ph_index >= e_phnum:
            continue
        _typ, ziel, _fs = kopf(ph_index)
        if quelle + filesz > len(daten) or ziel + filesz > len(ausgabe):
            continue
        ausgabe[ziel:ziel + filesz] = daten[quelle:quelle + filesz]

    # 6) Versionssegment nachtragen - es haengt am Ende des Containers.
    for i in range(e_phnum):
        typ, ziel, filesz = kopf(i)
        if typ != PT_SCE_VERSION or filesz == 0:
            continue
        quelle = len(daten) - filesz
        if quelle >= 0 and ziel + filesz <= len(ausgabe):
            ausgabe[ziel:ziel + filesz] = daten[quelle:quelle + filesz]
        break

    # 7) Doppelt abgelegten Kopf des ersten Segments ausnullen.
    _erste_kopie_entfernen(ausgabe, int(erstes_offset))

    return bytes(ausgabe)


def _erste_kopie_entfernen(ausgabe: bytearray, erstes_offset: int) -> int:
    """Nullt eine Zweitablage des ersten Segments vor dessen eigentlichem Offset.

    Manche Container legen den Anfang des ersten Segments zusaetzlich weiter vorn
    ab. Bleibt das stehen, stimmt das Ergebnis nicht mit dem urspruenglichen ELF
    ueberein. Gesucht wird ein Abschnitt, der mit dem Segmentanfang uebereinstimmt.

    Returns:
        Fundstelle oder -1.
    """
    vergleichslaenge = 0xC0
    sicherheit_prozent = 2
    if erstes_offset < vergleichslaenge or erstes_offset > len(ausgabe):
        return -1
    if erstes_offset + vergleichslaenge > len(ausgabe):
        return -1
    muster = bytes(ausgabe[erstes_offset:erstes_offset + vergleichslaenge])
    grenze = int(erstes_offset * (100 - sicherheit_prozent) / 100)
    fundstelle = -1
    for i in range(grenze + 1):
        if erstes_offset - i < vergleichslaenge:
            break
        if bytes(ausgabe[i:i + vergleichslaenge]) == muster:
            fundstelle = i
            break
    if fundstelle >= 0:
        for i in range(fundstelle, erstes_offset):
            ausgabe[i] = 0
    return fundstelle


# --------------------------------------------------------------------------
# ELF -> SELF (signieren)
# --------------------------------------------------------------------------

class _ElfKopf:
    """Der ELF-Kopf, so weit er zum Wiederschreiben gebraucht wird."""

    def __init__(self, daten: bytes) -> None:
        groesse = struct.calcsize(ELF_HEADER_FMT)
        (self.magic, self.ei_class, self.ei_data, self.ei_version,
         self.ei_osabi, self.ei_abiversion, self.ei_pad) = struct.unpack_from(
            ELF_HEADER_FMT, daten, 0)
        if self.magic != b"\x7fELF":
            raise BackportFehler("Keine ELF-Kennung.")
        (self.type, self.machine, self.version, self.entry, self.phoff,
         self.shoff, self.flags, self.ehsize, self.phentsize, self.phnum,
         self.shentsize, self.shnum, self.shstridx) = struct.unpack_from(
            ELF_HEADER_EX_FMT, daten, groesse)

    def packen(self) -> bytes:
        return (struct.pack(ELF_HEADER_FMT, self.magic, self.ei_class,
                            self.ei_data, self.ei_version, self.ei_osabi,
                            self.ei_abiversion, self.ei_pad)
                + struct.pack(ELF_HEADER_EX_FMT, self.type, self.machine,
                              self.version, self.entry, self.phoff, self.shoff,
                              self.flags, self.ehsize, self.phentsize,
                              self.phnum, self.shentsize, self.shnum,
                              self.shstridx))


def elf_signieren(elf: bytes, *, paid: int = PAID_STANDARD,
                  ptype: int = PTYPE_FAKE, app_version: int = 0,
                  fw_version: int = 0) -> bytes:
    """Verpackt ein ELF wieder in einen SELF-Container.

    Nachbau von ``make_fself.py``. Das Ergebnis traegt keine echte Signatur -
    die Signaturflaeche bleibt leer, wie bei jedem Fake-Paket.

    Raises:
        BackportFehler: Kein brauchbares ELF.
    """
    if len(elf) < 64:
        raise BackportFehler("Datei zu kurz für ein ELF.")
    kopf = _ElfKopf(elf)
    if kopf.phentsize == 0 or kopf.phnum == 0:
        raise BackportFehler("ELF ohne Programmkopftabelle lässt sich nicht signieren.")
    # Abschnittskoepfe werden nicht uebernommen (wie im Original).
    kopf.shnum = 0

    digest = hashlib.sha256(elf).digest()

    programm_koepfe: list[dict] = []
    segmente: list[bytes] = []
    for i in range(kopf.phnum):
        basis = kopf.phoff + i * kopf.phentsize
        if basis + PHDR_SIZE > len(elf):
            raise BackportFehler("Programmkopftabelle reicht über das Dateiende hinaus.")
        typ, flags, offset, vaddr, paddr, filesz, memsz, align = struct.unpack_from(
            PHDR_FMT, elf, basis)
        programm_koepfe.append({
            "type": typ, "flags": flags, "offset": offset, "vaddr": vaddr,
            "paddr": paddr, "filesz": filesz, "memsz": memsz, "align": align,
        })
        if filesz > 0:
            if offset + filesz > len(elf):
                raise BackportFehler(f"Segment {i} reicht über das Dateiende hinaus.")
            segmente.append(elf[offset:offset + filesz])
        else:
            segmente.append(b"")

    # ---- Eintraege aufbauen: je Segment ein Meta- und ein Datenpaar ----
    versionsdaten: bytes | None = None
    eintraege: list[dict] = []
    lauf = 0
    for i, ph in enumerate(programm_koepfe):
        if ph["type"] == PT_SCE_VERSION:
            versionsdaten = segmente[i]
        if ph["type"] not in SIGNIERTE_SEGMENTE:
            continue
        meta_props = (1 << PROPS_SIGNED_SHIFT) | (1 << PROPS_HAS_DIGESTS_SHIFT)
        meta_props |= ((lauf + 1) & PROPS_SEGMENT_INDEX_MASK) << PROPS_SEGMENT_INDEX_SHIFT
        eintraege.append({"props": meta_props, "meta": True, "ph": i})

        daten_props = (1 << PROPS_SIGNED_SHIFT) | (1 << PROPS_HAS_BLOCKS_SHIFT)
        daten_props |= ((BLOCK_SIZE.bit_length() - 1 - 12) & 0xF) << PROPS_BLOCK_SIZE_SHIFT
        daten_props |= (i & PROPS_SEGMENT_INDEX_MASK) << PROPS_SEGMENT_INDEX_SHIFT
        eintraege.append({"props": daten_props, "meta": False, "ph": i})
        lauf += 2

    if not eintraege:
        raise BackportFehler("ELF enthält kein signierbares Segment.")

    anzahl = len(eintraege)
    flags = 0x2 | ((2 & FLAGS_SEGMENT_SIGNED_MASK) << FLAGS_SEGMENT_SIGNED_SHIFT)

    elf_kopfbereich = max(kopf.ehsize, kopf.phoff + kopf.phentsize * kopf.phnum)
    header_size = (struct.calcsize(SELF_COMMON_HEADER_FMT)
                   + struct.calcsize(SELF_EXT_HEADER_FMT)
                   + anzahl * struct.calcsize(SELF_ENTRY_FMT)
                   + elf_kopfbereich)
    header_size = _aufrunden(header_size, 16)
    header_size += struct.calcsize(SELF_EXINFO_FMT)
    header_size += struct.calcsize(SELF_NPDRM_FMT)

    meta_size = (anzahl * struct.calcsize(SELF_METABLOCK_FMT)
                 + struct.calcsize(SELF_METAFOOTER_FMT) + SIGNATURE_SIZE)

    # ---- Offsets und Nutzdaten festlegen ----
    offset = header_size + meta_size
    for eintrag in eintraege:
        ph = programm_koepfe[eintrag["ph"]]
        if eintrag["meta"]:
            bloecke = _aufrunden(ph["filesz"], BLOCK_SIZE) // BLOCK_SIZE
            eintrag["data"] = b"\0" * (DIGEST_SIZE * bloecke)
        else:
            eintrag["data"] = segmente[eintrag["ph"]]
        eintrag["offset"] = offset
        eintrag["filesz"] = len(eintrag["data"])
        offset = _aufrunden(offset + eintrag["filesz"], 16)
    file_size = offset

    # ---- Schreiben ----
    ausgabe = bytearray(file_size)

    def schreibe(pos: int, roh: bytes) -> None:
        ende = pos + len(roh)
        if ende > len(ausgabe):
            ausgabe.extend(b"\0" * (ende - len(ausgabe)))
        ausgabe[pos:ende] = roh

    schreibe(0, struct.pack(SELF_COMMON_HEADER_FMT, SELF_MAGIC, SELF_VERSION,
                            SELF_MODE, SELF_ENDIAN, SELF_ATTRIBS))
    pos = struct.calcsize(SELF_COMMON_HEADER_FMT)
    schreibe(pos, struct.pack(SELF_EXT_HEADER_FMT, SELF_KEY_TYPE,
                              header_size & 0xFFFF, meta_size & 0xFFFF,
                              file_size, anzahl & 0xFFFF, flags & 0xFFFF))
    pos += struct.calcsize(SELF_EXT_HEADER_FMT)

    for eintrag in eintraege:
        schreibe(pos, struct.pack(SELF_ENTRY_FMT, eintrag["props"],
                                  eintrag["offset"], eintrag["filesz"],
                                  eintrag["filesz"]))
        pos += struct.calcsize(SELF_ENTRY_FMT)

    elf_start = pos
    schreibe(elf_start, kopf.packen())
    for i, ph in enumerate(programm_koepfe):
        schreibe(elf_start + kopf.phoff + i * kopf.phentsize,
                 struct.pack(PHDR_FMT, ph["type"], ph["flags"], ph["offset"],
                             ph["vaddr"], ph["paddr"], ph["filesz"],
                             ph["memsz"], ph["align"]))
    pos = elf_start + _aufrunden(elf_kopfbereich, 16)

    schreibe(pos, struct.pack(SELF_EXINFO_FMT, paid, ptype, app_version,
                              fw_version, digest))
    pos += struct.calcsize(SELF_EXINFO_FMT)

    schreibe(pos, struct.pack(SELF_NPDRM_FMT, NPDRM_TYPE,
                              b"\0" * NPDRM_CONTENT_ID_SIZE,
                              b"\0" * NPDRM_RANDOM_PAD_SIZE))
    pos += struct.calcsize(SELF_NPDRM_FMT)

    for _ in range(anzahl):
        schreibe(pos, struct.pack(SELF_METABLOCK_FMT))
        pos += struct.calcsize(SELF_METABLOCK_FMT)
    schreibe(pos, struct.pack(SELF_METAFOOTER_FMT, 0x10000))
    pos += struct.calcsize(SELF_METAFOOTER_FMT)
    schreibe(pos, b"\0" * SIGNATURE_SIZE)

    for eintrag in eintraege:
        schreibe(eintrag["offset"], eintrag["data"])

    if versionsdaten:
        ausgabe.extend(versionsdaten)

    return bytes(ausgabe)


# --------------------------------------------------------------------------
# libc-Zeichenkettenpatch (6.xx)
# --------------------------------------------------------------------------

def ist_libc(pfad: str) -> bool:
    """True fuer die Datei, auf die der 6.xx-Patch ueberhaupt zutrifft.

    Der Dateiname wird an beiden Trennzeichen abgeschnitten, nicht ueber
    ``os.path.basename``: Die geprueften Pfade stammen teils aus dem lokalen
    Dateisystem, teils aus PS5-Metadaten und FTP-Listen. Unter Linux kennt
    ``basename`` den Rueckstrich nicht, sodass ein Eintrag wie
    ``sce_module\\libc.prx`` dort komplett als Dateiname galt und der Patch
    stillschweigend uebersprungen wurde.
    """
    name = str(pfad or "").replace("\\", "/").rsplit("/", 1)[-1]
    return name.lower() == "libc.prx"


def libc_patchen(daten: bytes) -> tuple[bytes, int]:
    """Ersetzt die 6.xx-Zeichenkette in libc.prx.

    Returns:
        (Bytes, Fundstelle). Fundstelle ist ``-1``, wenn das Muster fehlt, und
        ``-2``, wenn bereits gepatzt wurde - beides ist kein Fehler.
    """
    schon = daten.find(LIBC_NEU)
    if schon >= 0:
        return daten, -2
    stelle = daten.find(LIBC_ALT)
    if stelle < 0:
        return daten, -1
    puffer = bytearray(daten)
    puffer[stelle:stelle + len(LIBC_NEU)] = LIBC_NEU
    return bytes(puffer), stelle


def libc_zuruecksetzen(daten: bytes) -> tuple[bytes, int]:
    """Macht :func:`libc_patchen` rueckgaengig (Auto-Backpork: ``revert_libc_patch``).

    Returns:
        (Bytes, Fundstelle). Fundstelle ist ``-1``, wenn die gepatchte Folge nicht vorkommt - dann ist nichts zu tun.
    """
    stelle = daten.find(LIBC_NEU)
    if stelle < 0:
        return daten, -1
    puffer = bytearray(daten)
    puffer[stelle:stelle + len(LIBC_ALT)] = LIBC_ALT
    return bytes(puffer), stelle


#: Ergebnisse von :func:`libc_regel` (Kennungen, keine Anzeigetexte).
LIBC_PATCHEN = "patchen"
LIBC_ZURUECK = "zuruecksetzen"


def libc_regel(ziel_ps5: int) -> str:
    """Was mit der ``libc.prx`` zu tun ist: ``"patchen"`` bis Ziel 6, darueber ``"zuruecksetzen"``."""
    try:
        haupt = int(firmware_text(ziel_ps5).split(".")[0])
    except ValueError:
        return LIBC_PATCHEN
    return LIBC_PATCHEN if haupt <= LIBC_PATCH_BIS else LIBC_ZURUECK


# --------------------------------------------------------------------------
# Gesamtablauf je Datei
# --------------------------------------------------------------------------

#: Ergebniskennungen von :func:`datei_verarbeiten`.
ERG_GEPATCHT = "gepatcht"
ERG_UEBERSPRUNGEN = "uebersprungen"
ERG_FEHLER = "fehler"


#: Die Sätze, die der Anwender zu sehen bekommt - als Vorgabe. Die
#: Oberfläche reicht über ``texte`` die übersetzte Fassung herein; dieses
#: Modul darf ``i18n`` nicht einbinden und bleibt so ohne Fenster benutzbar.
#: Dasselbe Muster wie in ``pkg_merger.MELDUNGEN``.
MELDUNGEN: dict[str, str] = {
    'kein_elf_kein_self':
        'kein ELF und kein SELF',
    # Bis zum 17.09.2026 standen die folgenden Gruende fest im Quelltext -
    # die Statusspalte des BACKPORT-Fensters zeigte sie auch auf Englisch.
    'elf_ohne_kennung':
        'ELF ohne Kennung – so nicht signierbar, bleibt unverändert',
    'entpacken_fehlgeschlagen':
        'Entpacken fehlgeschlagen: {fehler}',
    'keine_sdk_angabe':
        'keine SDK-Angabe enthalten',
    'self_verschluesselt':
        'SELF verschlüsselt oder komprimiert – nur entschlüsselte Dumps lassen sich backportieren',
    'bereits_niedrig':
        'bereits {firmware} oder älter',
    'sdk_nicht_setzbar':
        'SDK nicht setzbar: {fehler}',
    'signieren_fehlgeschlagen':
        'Signieren fehlgeschlagen: {fehler}',
    'libc_patch_bei':
        ', libc-Patch bei 0x{stelle}',
    'libc_bereits_gepatcht':
        ', libc bereits gepatcht',
    'libc_muster_fehlt':
        ', libc-Muster nicht gefunden',
    'libc_zurueckgesetzt':
        ', libc-Patch bei 0x{stelle} zurückgenommen',
}


def _satz(texte: "dict[str, str] | None", kennung: str, **werte) -> str:
    """Eine Vorlage, übersetzt wenn möglich."""
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return MELDUNGEN[kennung].format(**werte)

def datei_verarbeiten(daten: bytes, *, ziel_ps5: int, ziel_ps4: int,
                      libc_zusatz: bool = False,
                      ist_libc_datei: bool = False,
                      texte: "dict[str, str] | None" = None) -> tuple[str, bytes, str]:
    """Fuehrt den kompletten Ablauf auf einer Bytefolge aus.

    Schreibt nichts. Der Aufrufer ersetzt das Original nur bei ``ERG_GEPATCHT``.

    Returns:
        (Ergebniskennung, neue Bytes, Klartextbegruendung). Bei allem ausser
        ``ERG_GEPATCHT`` sind die Bytes unveraendert.
    """
    typ = dateityp(daten)
    if typ == TYP_UNBEKANNT:
        return ERG_UEBERSPRUNGEN, daten, _satz(texte, "kein_elf_kein_self")
    if typ == TYP_ELF_GESTRIPPT:
        # Gemessen am 17.09.2026: Herabsetzen gelang, Signieren scheiterte
        # danach immer ("Keine ELF-Kennung") - und die Analyse im Fenster
        # zaehlte die Datei trotzdem als offen. Die Kennung einfach zu
        # ergaenzen waere geraten: Ob die Konsole so eine Datei annimmt, ist
        # nicht gemessen.
        return ERG_FEHLER, daten, _satz(texte, "elf_ohne_kennung")

    war_self = typ == TYP_SELF
    try:
        elf = self_zu_elf(daten) if war_self else daten
    except BackportFehler as exc:
        return ERG_FEHLER, daten, _satz(texte, "entpacken_fehlgeschlagen", fehler=exc)

    try:
        aktuell_ps5, _aktuell_ps4 = sdk_lesen(elf)
    except SdkNichtGefunden:
        # Ein verschluesselter Container ist kein "nichts zu tun": Die Datei
        # bleibt auf der hohen Firmware, und das Spiel startet danach nicht.
        if war_self and self_segmente_verschluesselt(daten):
            return ERG_FEHLER, daten, _satz(texte, "self_verschluesselt")
        return ERG_UEBERSPRUNGEN, daten, _satz(texte, "keine_sdk_angabe")

    if not muss_gepatcht_werden(aktuell_ps5, ziel_ps5):
        return (ERG_UEBERSPRUNGEN, daten,
                _satz(texte, "bereits_niedrig", firmware=firmware_text(aktuell_ps5)))

    try:
        elf, alt_ps5, _alt_ps4 = sdk_setzen(elf, ziel_ps5, ziel_ps4)
    except BackportFehler as exc:
        return ERG_FEHLER, daten, _satz(texte, "sdk_nicht_setzbar", fehler=exc)

    zusatz = ""
    if libc_zusatz and ist_libc_datei:
        if libc_regel(ziel_ps5) == LIBC_PATCHEN:
            elf, stelle = libc_patchen(elf)
            if stelle >= 0:
                zusatz = _satz(texte, "libc_patch_bei", stelle="%X" % stelle)
            elif stelle == -2:
                zusatz = _satz(texte, "libc_bereits_gepatcht")
            else:
                zusatz = _satz(texte, "libc_muster_fehlt")
        else:
            # Ziel 7 und hoeher: wie Auto-Backpork - ein frueher gesetzter Patch geht zurueck, sonst bleibt es.
            elf, stelle = libc_zuruecksetzen(elf)
            if stelle >= 0:
                zusatz = _satz(texte, "libc_zurueckgesetzt", stelle="%X" % stelle)

    # Signieren ist Pflicht - eine unsignierte Datei darf nie zurueckgegeben werden.
    try:
        ergebnis = elf_signieren(elf)
    except BackportFehler as exc:
        return ERG_FEHLER, daten, _satz(texte, "signieren_fehlgeschlagen", fehler=exc)

    return (ERG_GEPATCHT, ergebnis,
            f"{firmware_text(alt_ps5)} -> {firmware_text(ziel_ps5)}{zusatz}")


# --------------------------------------------------------------------------
# Ersatzbibliotheken
# --------------------------------------------------------------------------

def fakelib_quelle(basis: str, firmware: int) -> str:
    """Pfad zum mitgelieferten Bibliothekssatz einer Firmware."""
    return os.path.join(str(basis or ""), str(int(firmware)), FAKELIB_ORDNER)


def firmwares_mit_bestand(basis: str) -> tuple[int, ...]:
    """Welche Firmware-Staende hier wirklich einen Bibliothekssatz haben.

    :data:`FIRMWARE_MIT_FAKELIBS` nennt die **mitgelieferten** Saetze - 4 bis
    7, mehr darf nicht weitergegeben werden. Die Saetze fuer 8, 9 und 10 sind
    damit aber nicht unmoeglich: PS5 BACKPORK KITCHEN 2.3.1 fuehrt in
    ``FAKELIBS_SETUP.md`` die Firmware 1.x bis 10.x als unterstuetzt und
    begruendet die Luecke ausdruecklich rechtlich ("Fakelibs cannot be
    distributed directly due to legal restrictions"), nicht technisch. Wer
    die Bibliotheken aus einer offiziellen Firmware zieht und als
    ``<basis>/8/fakelib/`` ablegt, hat einen vollwertigen Satz.

    Diese Funktion sieht deshalb nach, statt zu behaupten. Ohne sie stuende
    ein selbst ergaenzter Satz im Ordner und liesse sich trotzdem nicht
    waehlen - die Liste im Auswahlfeld war bis dahin fest verdrahtet.

    Grenze nach oben ist :data:`SDK_PAARE`: Fuer einen Stand ohne SDK-Paar
    liesse sich der Modulkopf nicht schreiben. Die PS5-Baunummer laesst sich
    nicht ausrechnen (siehe dort), ein Satz allein genuegt also nicht.

    Returns:
        Aufsteigend sortiert. Leer, wenn ``basis`` nichts enthaelt - dann
        faellt der Aufrufer auf :data:`FIRMWARE_MIT_FAKELIBS` zurueck.
    """
    if not basis or not os.path.isdir(str(basis)):
        return ()
    gefunden: list[int] = []
    for stand in sorted(SDK_PAARE):
        if fakelib_dateien(basis, stand):
            gefunden.append(stand)
    return tuple(gefunden)


def fakelib_ziel(spielordner: str, ordnername: str = FAKELIB_ORDNER) -> str:
    """Pfad, in den die Ersatzbibliotheken im Spiel gelegt werden.

    Args:
        spielordner: Wurzel des Dumps.
        ordnername:  ``FAKELIB_ORDNER`` oder ``FAKELIB2_ORDNER``. Ein anderer
            Wert faellt auf ``FAKELIB_ORDNER`` zurueck - ShadowMount+ kennt nur
            diese zwei Namen, ein Tippfehler wuerde sonst einen Ordner anlegen,
            den die Konsole nie einhaengt.
    """
    name = str(ordnername or "").strip().lower()
    if name not in FAKELIB_ORDNERNAMEN:
        name = FAKELIB_ORDNER
    return os.path.join(str(spielordner or ""), name)


def fakelib_vorhandene_ordner(spielordner: str) -> list[str]:
    """Nennt die vorhandenen Bibliotheksordner eines Dumps.

    Gedacht fuer die Warnung, wenn beide existieren. **Welcher der beiden dann
    wirkt, sagt diese Funktion bewusst nicht** - es haengt von der
    ShadowMount+-Fassung ab, und die Regeln stehen in
    ``shadowmount_generation``. Bis zum 05.09.2026 behauptete der Docstring
    hier "dann haengt die Konsole nur fakelib2 ein"; im Spielordner galt in
    1.7 alpha8 bis alpha13fix1 das Gegenteil (ab 1.7beta1 stimmt es wieder).
    """
    da = []
    for name in FAKELIB_ORDNERNAMEN:
        if os.path.isdir(os.path.join(str(spielordner or ""), name)):
            da.append(name)
    return da


#: Die beiden Bibliotheken, die AMPR EMU und der PlayGo-Stub ersetzen (Kleinschreibung).
AMPR_PLAYGO_BIBLIOTHEKEN = ("libsceampr.sprx", "libsceplaygo.sprx")

#: Woran ein AMPR EMU oder PlayGo-Stub zu erkennen ist (gemessen am 18.09.2026, siehe ``_ist_ersatzbibliothek`` im
#: Hauptmodul): in allen EMU-Fassungen und beiden Stubs, in keiner Sony-Bibliothek.
EMU_KENNZEICHEN = (b"[AMPR_EMU]", b"playgo_stub.dat")


def fremde_ampr_playgo(spielordner: str) -> list[str]:
    """Nennt die AMPR- und PlayGo-Bibliotheken im Dump, die weder AMPR EMU noch der PlayGo-Stub sind.

    Gedacht fuer den Hinweis beim Backport: Hat der Dump ``libSceAmpr.sprx`` oder ``libScePlayGo.sprx`` schon im
    ``fakelib``-Ordner (von einem anderen Werkzeug, oder die Originale eines frueheren Backports), bleiben sie bei
    ``Ersatzbibliotheken kopieren`` unberuehrt - der mitgelieferte Satz hat keine von beiden. Gemessen an Hollow Knight
    (PPSA34971, Firmware 4.03, 25.10.2026): Mit und ohne die Ersatzbibliotheken derselbe Absturz ``0xa0020104`` direkt nach
    ``libSceSysmodule``; behoben hat ihn erst das Ersetzen dieser zwei Dateien durch die aus AMPR EMU.

    Returns:
        Relative Pfade wie ``fakelib/libSceAmpr.sprx``, Reihenfolge der Ordner, leer ohne Befund.
    """
    gefunden: list[str] = []
    for ordnername in FAKELIB_ORDNERNAMEN:
        ordner = os.path.join(str(spielordner or ""), ordnername)
        try:
            namen = sorted(os.listdir(ordner))
        except OSError:
            continue
        for name in namen:
            if name.lower() not in AMPR_PLAYGO_BIBLIOTHEKEN:
                continue
            try:
                with open(os.path.join(ordner, name), "rb") as fh:
                    daten = fh.read()
            except OSError:
                continue
            if not any(k in daten for k in EMU_KENNZEICHEN):
                gefunden.append(ordnername + "/" + name)
    return gefunden


#: Endungen, die als Ersatzbibliothek in das Spiel gehoeren.
#:
#: Der mitgelieferte Satz ist wortgleich von PS5 BACKPORK KITCHEN 2.3.1
#: uebernommen, und dessen Form1.vb kopiert den Ordner ungefiltert
#: (``CopyRelative(fakelibfolder, fakelibingame)``). Im FW7-Satz liegt dadurch
#: eine ``ps5-backpork.elf`` (116 KB, der Payload des Werkzeugs selbst) - in den
#: Saetzen FW4 bis FW6 fehlt sie, es sieht also nach einem Versehen aus.
#:
#: ShadowMount+ haengt den Ordner nach ``common/lib``; der Lader holt
#: Bibliotheken nach Namen, wenn ein Spiel sie anfordert. Nach der .elf fragt
#: kein Spiel - sie ist Ballast im Sandkasten. Der ps5-exfat-builder beschreibt
#: seinen Auswahldialog passend dazu mit "containing .sprx/.prx files".
FAKELIB_ENDUNGEN = (".sprx", ".prx")


def fakelib_dateien(basis: str, firmware: int) -> list[str]:
    """Listet den Bibliothekssatz einer Firmware; leer, wenn keiner vorliegt.

    Uebernommen werden nur Bibliotheken (siehe ``FAKELIB_ENDUNGEN``) und die
    leere Markierungsdatei ``FW<n>``. Letztere kostet nichts und verraet
    spaeter, welcher Satz in dem Ordner liegt - bei der Fehlersuche nuetzlich.
    """
    ordner = fakelib_quelle(basis, firmware)
    try:
        namen = sorted(os.listdir(ordner))
    except OSError:
        return []
    markierung = f"FW{int(firmware)}".lower()
    gewaehlt: list[str] = []
    for name in namen:
        voll = os.path.join(ordner, name)
        if not os.path.isfile(voll):
            continue
        if name.lower().endswith(FAKELIB_ENDUNGEN) or name.lower() == markierung:
            gewaehlt.append(voll)
    return gewaehlt


def fakelib_uebersprungene(basis: str, firmware: int) -> list[str]:
    """Nennt die Dateien des Satzes, die NICHT mitkopiert werden.

    Damit die Aussage im Protokoll belegbar bleibt, statt nur zu behaupten, es
    sei alles Nötige dabei.
    """
    ordner = fakelib_quelle(basis, firmware)
    try:
        namen = sorted(os.listdir(ordner))
    except OSError:
        return []
    genommen = {os.path.basename(p) for p in fakelib_dateien(basis, firmware)}
    return [n for n in namen
            if os.path.isfile(os.path.join(ordner, n)) and n not in genommen]


def fakelib_dateien_benoetigt(basis: str, firmware: int,
                               spieldateien: list[str]) -> list[str]:
    """Wie :func:`fakelib_dateien`, aber nur die Bibliotheken, die eine der
    ``spieldateien`` (eboot.bin und Spielmodule) tatsaechlich importiert.

    Grund: Mehrere unabhaengige Befunde in der Szene (drakmor/ShadowMountPlus
    Issues #169 und #173) zeigen Spiele, die mit dem vollen Ersatzsatz beim
    Start abstuerzen oder haengen und erst nach Beschraenkung auf die wirklich
    gebrauchten Bibliotheken ("Emulators only" statt "Full") starten. Eine
    Bibliothek, die keine Spieldatei importiert, kann auf der Konsole ohnehin
    nie geladen werden - sie liegt dann nur als unnoetiger, womoeglich
    schaedlicher Ballast im Zielordner.

    Die Markierungsdatei ``FW<n>`` bleibt immer erhalten, da sie keine
    Bibliothek ist. Laesst sich aus keiner ``spieldatei`` eine Importtabelle
    lesen (z.B. weil die Liste leer ist oder alle Dateien verschluesselt
    sind), bleibt der volle Satz stehen - eine Einschraenkung ohne Grundlage
    waere schlimmer als gar keine.
    """
    voll = fakelib_dateien(basis, firmware)
    verlangt: set = set()
    gelesen = False
    for pfad in spieldateien:
        symbole = symbole_aus_datei(pfad)
        if symbole["importe"]:
            gelesen = True
        verlangt.update(name for name in symbole["importe"] if name and name != "?")
    if not gelesen:
        return voll

    markierung = f"FW{int(firmware)}".lower()
    ergebnis: list[str] = []
    for pfad in voll:
        if os.path.basename(pfad).lower() == markierung:
            ergebnis.append(pfad)
            continue
        symbole = symbole_aus_datei(pfad)
        exportiert = {name for name in symbole["exporte"] if name and name != "?"}
        if not exportiert:
            exportiert = {bibliotheksname(pfad)}
        if exportiert & verlangt:
            ergebnis.append(pfad)
    return ergebnis


def fakelib_unnoetige(basis: str, firmware: int,
                       spieldateien: list[str]) -> list[str]:
    """Nennt die Bibliotheken aus dem Satz, die keine ``spieldatei``
    importiert - Grundlage fuer die Protokollzeile zu
    :func:`fakelib_dateien_benoetigt`."""
    voll = {os.path.basename(p) for p in fakelib_dateien(basis, firmware)}
    noetig = {os.path.basename(p)
              for p in fakelib_dateien_benoetigt(basis, firmware, spieldateien)}
    return sorted(voll - noetig)


# --------------------------------------------------------------------------
# Deckungspruefung: Was importiert das Spiel, was liefert die Ersatzbibliothek
# --------------------------------------------------------------------------
#
# Bis v1.8.61 hiess "backportiert" nur: Die Dateien liegen im Ordner. Ob eine
# mitgelieferte Ersatzbibliothek ueberhaupt das exportiert, was das Spiel von
# ihr verlangt, hat nie jemand nachgesehen - auf der Konsole faellt es erst
# beim Start auf, und dann ohne brauchbare Meldung.
#
# Moeglich wird die Pruefung durch den NID-Algorithmus aus dem backport-helper
# (tools/prx_rename_nids_auto.py, im Repo unter "PS5 SDK usw/"). Er ist hier
# nachgerechnet, nicht uebernommen: sceKernelLoadStartModule -> wzvqT4UqKX8,
# sceKernelDlsym -> LwG8g3niqwA, sceKernelAllocateDirectMemory -> rTXw65xmLIA,
# alle drei gegen oeffentlich bekannte Werte geprueft (19.08.2026).

#: Alphabet der SCE-Kurzkennungen. Die Reihenfolge ist nicht Base64-Standard -
#: '+' und '-' stehen am Ende statt '+' und '/'.
NID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+-"

#: Fester Anhang vor dem SHA-1. Ohne ihn kommt eine voellig andere Kennung
#: heraus - der Wert stammt aus dem backport-helper und ist oben belegt.
NID_SALZ = bytes.fromhex("518D64A635DED8C1E6B039B1C3E55230")

#: Dynamische Eintraege eines PRX. Die 0x61...-Werte sind Sonys Erweiterungen.
DT_HASH = 4
DT_STRTAB = 5
DT_SYMTAB = 6
DT_STRSZ = 10
DT_SCE_IMPORT_LIB = 0x61000049
DT_SCE_EXPORT_LIB = 0x61000047


def nid_von_name(name: str) -> str:
    """Rechnet den 11-Zeichen-NID zu einem Funktionsnamen aus."""
    verdaut = hashlib.sha1(str(name).encode("utf-8") + NID_SALZ).digest()
    wert = struct.unpack("<Q", verdaut[:8])[0]
    roh = base64.b64encode(wert.to_bytes(8, "big"), altchars=b"+-")
    return roh.decode("ascii").rstrip("=")


def _kennzahl(zeichen: str) -> int:
    """Kurzkennung eines Symbols (ein Zeichen) zurueck in ihre Zahl."""
    try:
        return NID_ALPHABET.index(zeichen)
    except ValueError:
        return -1


def symbol_zerlegen(symbol: str) -> tuple[str, int, int]:
    """Zerlegt ``<NID>#<Bibliothek>#<Modul>`` in seine drei Teile.

    Returns:
        (NID, Bibliothekskennzahl, Modulkennzahl). Bei einem Symbol, das nicht
        dieser Form entspricht, sind beide Zahlen -1.
    """
    teile = str(symbol).split("#")
    if len(teile) != 3 or len(teile[1]) != 1 or len(teile[2]) != 1:
        return str(symbol), -1, -1
    return teile[0], _kennzahl(teile[1]), _kennzahl(teile[2])


def _programmkoepfe(elf: bytes) -> list[tuple[int, int, int, int]]:
    """Alle Programmkoepfe als (Typ, Offset, virtuelle Adresse, Groesse)."""
    if len(elf) < 0x40:
        return []
    phoff, = struct.unpack_from("<Q", elf, 0x20)
    phentsize, phnum = struct.unpack_from("<HH", elf, 0x36)
    koepfe = []
    for i in range(phnum):
        p = phoff + i * phentsize
        if p + 0x38 > len(elf):
            break
        typ, = struct.unpack_from("<I", elf, p)
        offset, vaddr = struct.unpack_from("<QQ", elf, p + 0x08)
        groesse, = struct.unpack_from("<Q", elf, p + 0x20)
        koepfe.append((typ, offset, vaddr, groesse))
    return koepfe


def prx_symbole(elf: bytes) -> dict[str, Any]:
    """Liest Importe und Exporte eines PRX/ELF aus seiner Dynamiktabelle.

    Ein PRX traegt keine Abschnittstabelle; alles Noetige steht in PT_DYNAMIC
    und den geladenen Segmenten. Die Symbolnamen sind keine Klartextnamen,
    sondern ``<NID>#<Bibliothek>#<Modul>`` - welche Bibliothek gemeint ist,
    verraten erst die Eintraege DT_SCE_IMPORT_LIB und DT_SCE_EXPORT_LIB.

    Returns:
        Dict mit ``importe`` und ``exporte`` (je Dict Bibliotheksname ->
        Menge von NIDs) sowie ``import_bibliotheken`` /
        ``export_bibliotheken`` (Kennzahl -> Name). Leere Dicts, wenn die
        Datei keine Dynamiktabelle hat - statisch gebundene Homebrew etwa.
    """
    leer = {"importe": {}, "exporte": {},
            "import_bibliotheken": {}, "export_bibliotheken": {}}
    if elf[:4] != b"\x7fELF":
        return leer

    lade, dynamik = [], None
    for typ, offset, vaddr, groesse in _programmkoepfe(elf):
        if typ == 1:                       # PT_LOAD
            lade.append((vaddr, offset, groesse))
        elif typ == 2:                     # PT_DYNAMIC
            dynamik = (offset, groesse)
    if dynamik is None or not lade:
        return leer

    def zu_offset(adresse: int):
        for vaddr, offset, groesse in lade:
            if vaddr <= adresse < vaddr + groesse:
                return offset + (adresse - vaddr)
        return None

    werte: dict[int, int] = {}
    bibliotheken: list[tuple[int, int, bool]] = []   # (Kennzahl, Namensoffset, Import?)
    offset, groesse = dynamik
    for i in range(groesse // 16):
        p = offset + i * 16
        if p + 16 > len(elf):
            break
        marke, wert = struct.unpack_from("<QQ", elf, p)
        if marke == 0:
            break
        if marke in (DT_SCE_IMPORT_LIB, DT_SCE_EXPORT_LIB):
            # Unten der Namensoffset in der Zeichenkettentabelle, ab Bit 48
            # die Kennzahl, die im Symbol als einzelnes Zeichen auftaucht.
            bibliotheken.append((wert >> 48, wert & 0xFFFFFFFF,
                                 marke == DT_SCE_IMPORT_LIB))
        else:
            werte.setdefault(marke, wert)

    if DT_STRTAB not in werte or DT_SYMTAB not in werte:
        return leer
    strtab = zu_offset(werte[DT_STRTAB])
    symtab = zu_offset(werte[DT_SYMTAB])
    strsz = werte.get(DT_STRSZ, 0)
    if strtab is None or symtab is None or not strsz:
        return leer

    def zeichenkette(relativ: int) -> str:
        p = strtab + relativ
        if p >= len(elf) or relativ >= strsz:
            return ""
        ende = elf.find(b"\0", p)
        if ende < 0:
            return ""
        return elf[p:ende].decode("latin1")

    import_namen = {k: zeichenkette(o) for k, o, ist_import in bibliotheken if ist_import}
    export_namen = {k: zeichenkette(o) for k, o, ist_import in bibliotheken if not ist_import}

    # Wie viele Symbole es sind, steht nicht in der Dynamiktabelle - aber in
    # der SysV-Hashtabelle: deren zweites Wort (nchain) ist die Anzahl der
    # Eintraege in .dynsym. Ohne diese Grenze liest man einfach bis zum
    # Dateiende weiter.
    #
    # Genau das tat diese Funktion bis v1.8.65. Bei "Dirt 5" waren das 37468
    # statt 744 Eintraege - der Rest sind fremde Bytes, deren st_name zufaellig
    # in die Zeichenkettentabelle zeigt und dort mitten in einen Namen. Heraus
    # kamen Bruchstuecke wie "+mr7GjTvr8" (ein Stueck von "N+mr7GjTvr8"), die
    # als eigenstaendige Kennungen gezaehlt wurden - und damit als fehlende
    # Funktionen, die es nie gab.
    anzahl = None
    if DT_HASH in werte:
        hashoff = zu_offset(werte[DT_HASH])
        if hashoff is not None and hashoff + 8 <= len(elf):
            _nbucket, nchain = struct.unpack_from("<II", elf, hashoff)
            if 0 < nchain < 1_000_000:
                anzahl = nchain
    if anzahl is None:
        # Ohne Hashtabelle bleibt nur eine vorsichtige Schranke: bis zum
        # Beginn der Zeichenkettentabelle, wenn die dahinter liegt.
        ende = strtab if strtab > symtab else len(elf)
        anzahl = max(0, (ende - symtab) // 24)

    importe: dict[str, set] = {}
    exporte: dict[str, set] = {}
    i = 0
    # 24 Bytes je Eintrag (Elf64_Sym).
    while i < anzahl and symtab + (i + 1) * 24 <= len(elf):
        st_name, _info, _other, st_shndx, _wert, _groesse = struct.unpack_from(
            "<IBBHQQ", elf, symtab + i * 24)
        i += 1
        if st_name == 0 or st_name >= strsz:
            continue
        name = zeichenkette(st_name)
        if not name:
            continue
        nid, bibliothek, _modul = symbol_zerlegen(name)
        if bibliothek < 0:
            continue
        # st_shndx == 0 heisst "hier nicht definiert" - also ein Import.
        if st_shndx:
            exporte.setdefault(export_namen.get(bibliothek, "?"), set()).add(nid)
        else:
            importe.setdefault(import_namen.get(bibliothek, "?"), set()).add(nid)

    return {"importe": importe, "exporte": exporte,
            "import_bibliotheken": import_namen, "export_bibliotheken": export_namen}


def symbole_aus_datei(pfad: str) -> dict[str, Any]:
    """Wie :func:`prx_symbole`, packt ein SELF vorher aus."""
    with open(pfad, "rb") as fh:
        roh = fh.read()
    if dateityp(roh) == "self":
        try:
            roh = self_zu_elf(roh)
        except Exception:  # noqa: BLE001 - verschluesseltes/beschaedigtes SELF bleibt ohne Symbole
            return {"importe": {}, "exporte": {},
                    "import_bibliotheken": {}, "export_bibliotheken": {}}
    return prx_symbole(roh)


def bibliotheksname(dateiname: str) -> str:
    """Bibliotheksname aus einem Dateinamen - ``libSceAgc.sprx`` -> ``libSceAgc``.

    ``libSceSaveData.native.sprx`` ergibt ``libSceSaveData.native``; der Name
    im Modul heisst dort tatsaechlich so.
    """
    name = os.path.basename(str(dateiname))
    for endung in (".sprx", ".prx", ".elf", ".bin"):
        if name.lower().endswith(endung):
            return name[:-len(endung)]
    return name


def deckung_pruefen(spieldateien: list[str], fakelibs: list[str]) -> dict[str, Any]:
    """Haelt die Importe eines Spiels gegen die Exporte der Ersatzbibliotheken.

    Args:
        spieldateien: Pfade der ausfuehrbaren Dateien des Spiels (eboot.bin
            und Module).
        fakelibs: Pfade der Ersatzbibliotheken, die installiert werden.

    Returns:
        Dict mit:
            ``geprueft``   Anzahl gelesener Spieldateien mit Dynamiktabelle
            ``ohne_tabelle`` Dateien ohne Importtabelle (statisch gebunden)
            ``bibliotheken`` je ersetzter Bibliothek ein Dict mit ``verlangt``,
                ``geliefert`` und ``fehlend`` (Mengen von NIDs)
            ``unbeteiligt`` Bibliotheken, die das Spiel importiert, fuer die
                aber keine Ersatzbibliothek mitkommt - die kommen von der
                Konsole und sind kein Befund
    """
    # Was die mitgelieferten Bibliotheken exportieren, nach Namen.
    #
    # Je Bibliotheksname genau deren eigene Exporte: Eine Datei kann mehrere
    # Bibliotheken fuehren - libSceNpAuth.sprx etwa libSceNpAuth (14 Symbole),
    # libSceNpAuthAuthorizedApp (1) und libSceNpAuthCompat (2). Wuerde man alle
    # zusammenwerfen, gaelte ein Symbol als geliefert, das in Wahrheit unter
    # einem anderen Namen steht - und die Pruefung schwiege genau dort, wo sie
    # etwas sagen sollte.
    geliefert: dict[str, set] = {}
    for pfad in fakelibs:
        symbole = symbole_aus_datei(pfad)
        erkannt = False
        for name, menge in symbole["exporte"].items():
            if not name or name == "?":
                continue
            geliefert.setdefault(name, set()).update(menge)
            erkannt = True
        if not erkannt:
            # Keine lesbare Exporttabelle - dann bleibt nur der Dateiname.
            alle: set = set()
            for menge in symbole["exporte"].values():
                alle |= menge
            geliefert.setdefault(bibliotheksname(pfad), set()).update(alle)

    verlangt: dict[str, set] = {}
    geprueft = 0
    ohne_tabelle = 0
    for pfad in spieldateien:
        symbole = symbole_aus_datei(pfad)
        if not symbole["importe"]:
            ohne_tabelle += 1
            continue
        geprueft += 1
        for bibliothek, nids in symbole["importe"].items():
            verlangt.setdefault(bibliothek, set()).update(nids)

    bibliotheken = {}
    unbeteiligt = []
    for bibliothek, nids in sorted(verlangt.items()):
        # "?" sind Symbole, deren Bibliothekskennzahl in keiner Tabelle steht -
        # Modulkopf-Eintraege und dergleichen. Sie als fehlende Bibliothek zu
        # melden waere Rauschen.
        if not bibliothek or bibliothek == "?":
            continue
        if bibliothek not in geliefert:
            unbeteiligt.append(bibliothek)
            continue
        bibliotheken[bibliothek] = {
            "verlangt": nids,
            "geliefert": geliefert[bibliothek],
            "fehlend": nids - geliefert[bibliothek],
        }
    return {"geprueft": geprueft, "ohne_tabelle": ohne_tabelle,
            "bibliotheken": bibliotheken, "unbeteiligt": sorted(unbeteiligt)}


# --------------------------------------------------------------------------
# Deckung gegen einen entpackten Firmware-Bestand
# --------------------------------------------------------------------------
#
# ``deckung_pruefen`` beantwortet: Liefert der mitgelieferte Ersatzsatz, was
# das Spiel von ihm verlangt? Offen bleibt die Frage davor: Braucht es
# ueberhaupt einen Ersatz - und wofuer genau?
#
# Am 07.09.2026 an zehn Dumps gemessen, gegen die entpackten Staende 7.01,
# 8.60, 9.40 und 11.00:
#
#   Zielfirmware   fehlende Funktionen (ueber alle zehn)
#   7.01           24
#   8.60           13
#   9.40            9
#   11.00           0
#
# Fast alles davon steckt in ``libSceAgc`` - genau der Bibliothek, die in
# jedem mitgelieferten Ersatzsatz liegt. Und es sind ueber die Spiele hinweg
# **dieselben** Funktionen: ``libSceAgc/dbOlWdppb4o`` fehlte bei sechs von
# acht, ``vieBRwlh1Lw`` bei vier.
#
# Ein Vergleich auf Ebene ganzer Bibliotheken taugt dafuer **nicht**: Er
# meldet fuer 12.00 dieselbe Liste wie fuer 7.01, obwohl ein SDK-10-Spiel auf
# 12.00 laeuft. Namen wie ``libScePosix`` haben gar keine eigene Datei; sie
# stecken in ``libkernel``. ``libSceAudioOut2`` dagegen ist ein Neben-Export
# von ``libSceAudioOut.sprx`` und damit abgedeckt. Gezaehlt wird deshalb hier
# auf NID-Ebene.

#: Bibliotheksnamen fuer Tonausgabe, die in keinem mitgelieferten Fakelib-Satz
#: enthalten sind. ``libSceAudioOut``, ``libSceAudioOut2``, ``libSceAjm``,
#: ``libSceAudiodec``, ``libSceAudio3d``, ``libSceNgs2``,
#: ``libSceAudioDeviceControl`` (Stub mit 2 NIDs aus FW 4.x) und
#: ``libSceAudioLatencyEstimation`` (Stub mit 2 berechneten NIDs, kein
#: FW-Dump verfuegbar) sind abgedeckt. Leer = alle bekannten Audio-
#: Bibliotheken haben einen Stub; fehlende NIDs erscheinen als 'fehlend'.
AUDIO_BIBLIOTHEKEN: frozenset[str] = frozenset()

#: Unterordner eines entpackten Firmware-Baums, in denen Module liegen.
FIRMWARE_LIB_PFADE: tuple[tuple[str, ...], ...] = (
    ("system", "common", "lib"),
    ("system", "priv", "lib"),
    ("system_ex", "common_ex", "lib"),
    ("system_ex", "priv_ex", "lib"),
)


def ist_firmware_bestand(ordner: str) -> bool:
    """Sieht dieser Ordner aus wie ein entpackter Firmware-Stand?"""
    for teile in FIRMWARE_LIB_PFADE:
        pfad = os.path.join(str(ordner or ""), *teile)
        if os.path.isdir(pfad):
            try:
                if any(n.lower().endswith((".sprx", ".prx"))
                       for n in os.listdir(pfad)):
                    return True
            except OSError:
                continue
    return False


def firmware_exporttabelle(ordner: str) -> dict[str, set]:
    """Alle Funktionen, die dieser Firmware-Stand anbietet.

    Returns:
        Bibliotheksname (wie im Import genannt) -> Menge von NIDs. Gelesen
        wird der Name aus der Exporttabelle des Moduls, nicht der Dateiname:
        Eine Datei fuehrt oft mehrere Bibliotheken.
    """
    tabelle: dict[str, set] = {}
    for teile in FIRMWARE_LIB_PFADE:
        pfad = os.path.join(str(ordner or ""), *teile)
        if not os.path.isdir(pfad):
            continue
        try:
            namen = sorted(os.listdir(pfad))
        except OSError:
            continue
        for name in namen:
            if not name.lower().endswith((".sprx", ".prx")):
                continue
            symbole = symbole_aus_datei(os.path.join(pfad, name))
            for lib, nids in symbole["exporte"].items():
                if lib and lib != "?":
                    tabelle.setdefault(lib, set()).update(nids)
    return tabelle


def firmware_ordner_fuer(basis: str, hauptversion: int) -> str:
    """Sucht unter ``basis`` den passenden entpackten Firmware-Stand.

    Erwartet einen Ordner mit Unterordnern je Fassung (``7.61``, ``9.40``,
    ...), wie ihn die uebliche Entpackung anlegt. Genommen wird der
    **vollstaendigste** Stand der gesuchten Hauptversion: Einzelne
    Entpackungen sind lueckenhaft - 9.60 fuehrt 273 Bibliotheken, 9.40
    dagegen 543 -, und der duennere Stand meldete reihenweise Funktionen als
    fehlend, die es in Wirklichkeit gibt.

    Returns:
        Voller Pfad oder leere Zeichenkette, wenn nichts passt.
    """
    wurzel = str(basis or "")
    if not os.path.isdir(wurzel):
        return ""
    bester, beste_zahl = "", -1
    try:
        eintraege = sorted(os.listdir(wurzel))
    except OSError:
        return ""
    for name in eintraege:
        kopf = name.split(".", 1)[0]
        if not kopf.isdigit() or int(kopf) != int(hauptversion):
            continue
        pfad = os.path.join(wurzel, name)
        if not ist_firmware_bestand(pfad):
            continue
        anzahl = 0
        for teile in FIRMWARE_LIB_PFADE:
            unter = os.path.join(pfad, *teile)
            if os.path.isdir(unter):
                try:
                    anzahl += sum(1 for n in os.listdir(unter)
                                  if n.lower().endswith((".sprx", ".prx")))
                except OSError:
                    pass
        if anzahl > beste_zahl:
            bester, beste_zahl = pfad, anzahl
    return bester


def firmware_deckung(spieldateien: list[str], firmware_ordner: str) -> dict[str, Any]:
    """Welche Funktionen findet das Spiel auf dieser Firmware nicht?

    Args:
        spieldateien: eboot.bin und die Module des Dumps.
        firmware_ordner: Wurzel eines entpackten Firmware-Standes.

    Returns:
        Dict mit ``bestand`` (Anzahl Bibliotheken der Firmware),
        ``verlangt`` (Anzahl angeforderter Funktionen), ``fehlend``
        (Bibliotheksname -> sortierte Liste fehlender NIDs) und
        ``ohne_datei`` (Bibliotheken, die der Bestand gar nicht kennt - meist
        keine Luecke, sondern in einem anderen Modul eingebettet).
    """
    tabelle = firmware_exporttabelle(firmware_ordner)
    if not tabelle:
        return {"bestand": 0, "verlangt": 0, "fehlend": {}, "ohne_datei": []}

    # Was der Dump selbst mitbringt, muss die Firmware nicht liefern.
    eigene: dict[str, set] = {}
    verlangt: dict[str, set] = {}
    for pfad in spieldateien:
        symbole = symbole_aus_datei(pfad)
        for lib, nids in symbole["exporte"].items():
            if lib and lib != "?":
                eigene.setdefault(lib, set()).update(nids)
        for lib, nids in symbole["importe"].items():
            if lib and lib != "?":
                verlangt.setdefault(lib, set()).update(nids)

    fehlend: dict[str, list] = {}
    ohne_datei: list[str] = []
    for lib, nids in sorted(verlangt.items()):
        vorhanden = tabelle.get(lib, set()) | eigene.get(lib, set())
        if not vorhanden:
            ohne_datei.append(lib)
            continue
        offen = nids - vorhanden
        if offen:
            fehlend[lib] = sorted(offen)

    return {
        "bestand": len(tabelle),
        "verlangt": sum(len(n) for n in verlangt.values()),
        "fehlend": fehlend,
        "ohne_datei": ohne_datei,
    }


# --------------------------------------------------------------------------
# Firmware-Analyse: fehlende Fakelibs ermitteln und kopieren
# --------------------------------------------------------------------------
#
# deckung_pruefen fragt: Liefert der mitgelieferte Ersatzsatz, was das Spiel
# braucht? Hier geht es einen Schritt weiter: Welche Datei im Firmware-Stand
# deckt eine noch offene Bibliothek, und wie kopiert man sie in den Zielordner?
#
# Die Funktion fw_dateipfad_tabelle ist wie firmware_exporttabelle, traegt
# aber auch den Quelldateipfad mit - noetig, weil zum Kopieren der Pfad,
# nicht nur der Bibliotheksname, benoetigt wird.

def fw_dateipfad_tabelle(fw_ordner: str) -> dict[str, Any]:
    """Wie :func:`firmware_exporttabelle`, aber mit Quelldateipfad je Bibliothek.

    Returns:
        ``{bibliotheksname: (menge_nids, dateipfad)}``. Fuehrt eine Datei
        mehrere Bibliotheken, erhaelt jede denselben Pfad.
    """
    tabelle: dict[str, tuple] = {}
    for teile in FIRMWARE_LIB_PFADE:
        pfad = os.path.join(str(fw_ordner or ""), *teile)
        if not os.path.isdir(pfad):
            continue
        try:
            namen = sorted(os.listdir(pfad))
        except OSError:
            continue
        for name in namen:
            if not name.lower().endswith((".sprx", ".prx")):
                continue
            voll = os.path.join(pfad, name)
            symbole = symbole_aus_datei(voll)
            for lib, nids in symbole["exporte"].items():
                if not lib or lib == "?":
                    continue
                if lib not in tabelle:
                    tabelle[lib] = (set(), voll)
                bestehend, _ = tabelle[lib]
                bestehend.update(nids)
                tabelle[lib] = (bestehend, voll)
    return tabelle


def fehlende_libs_ermitteln(
    spieldateien: list[str],
    vorhandene_fakelibs: list[str],
    fw_ordner: str,
) -> list[tuple[str, str]]:
    """Findet Firmware-Bibliotheken, die NIDs liefern, die das Spiel braucht
    aber die vorhandenen Fakelibs noch nicht abdecken.

    Gedacht als Vorstufe von :func:`fakelibs_aus_firmware_kopieren`.

    Args:
        spieldateien:        Pfade von eboot.bin und den Spielmodulen.
        vorhandene_fakelibs: Bereits installierte Fakelib-Dateien.
        fw_ordner:           Wurzel eines entpackten Firmware-Standes
                             (enthaelt z.B. ``system/common/lib/``).

    Returns:
        Liste von ``(bibliotheksname, quelldatei)`` -- je Quelldatei hoechstens
        ein Eintrag, auch wenn sie mehrere fehlende Bibliotheken abdeckt.
        Bibliotheken, die das Spiel importiert aber der Firmware-Stand nicht
        kennt, fehlen in der Liste (sie liefert die Konsole selbst).
    """
    # Schritt 1: Was liefern die vorhandenen Fakelibs?
    geliefert: dict[str, set] = {}
    for pfad in vorhandene_fakelibs:
        symbole = symbole_aus_datei(pfad)
        for lib, nids in symbole["exporte"].items():
            if lib and lib != "?":
                geliefert.setdefault(lib, set()).update(nids)
        if not any(lib and lib != "?" for lib in symbole["exporte"]):
            geliefert.setdefault(bibliotheksname(pfad), set()).update(
                {n for m in symbole["exporte"].values() for n in m})

    # Schritt 2: Was importiert das Spiel?
    verlangt: dict[str, set] = {}
    for pfad in spieldateien:
        symbole = symbole_aus_datei(pfad)
        for lib, nids in symbole["importe"].items():
            if lib and lib != "?":
                verlangt.setdefault(lib, set()).update(nids)

    # Schritt 3: Welche Bibliotheken sind noch nicht vollstaendig abgedeckt?
    fehlende_bibs: set[str] = set()
    for lib, nids in verlangt.items():
        vorh = geliefert.get(lib, set())
        if nids - vorh:
            fehlende_bibs.add(lib)

    if not fehlende_bibs:
        return []

    # Schritt 4: Welche Quelldateien liefern diese Bibliotheken?
    fw_tabelle = fw_dateipfad_tabelle(fw_ordner)
    ergebnis: list[tuple] = []
    gesehene_dateien: set[str] = set()
    for lib in sorted(fehlende_bibs):
        if lib not in fw_tabelle:
            continue
        _, dateipfad = fw_tabelle[lib]
        if dateipfad not in gesehene_dateien:
            gesehene_dateien.add(dateipfad)
            ergebnis.append((lib, dateipfad))
    return ergebnis


def fakelibs_aus_firmware_kopieren(
    spieldateien: list[str],
    vorhandene_fakelibs: list[str],
    fw_ordner: str,
    ziel_ordner: str,
) -> dict[str, Any]:
    """Kopiert fehlende Fakelibs aus einem Firmware-Stand in ``ziel_ordner``.

    Es werden nur Bibliotheken kopiert, die das Spiel importiert und die
    durch ``vorhandene_fakelibs`` noch nicht abgedeckt sind. Dateien, die im
    Zielordner bereits vorhanden sind, werden nicht ueberschrieben.

    Args:
        spieldateien:        Pfade von eboot.bin und den Spielmodulen.
        vorhandene_fakelibs: Bereits installierte Fakelib-Dateien.
        fw_ordner:           Wurzel eines entpackten Firmware-Standes.
        ziel_ordner:         Wohin die Dateien kopiert werden (fakelib/).

    Returns:
        ``kopiert`` (int), ``uebersprungen`` (int), ``dateien`` (list[str]).
    """
    kandis = fehlende_libs_ermitteln(spieldateien, vorhandene_fakelibs, fw_ordner)
    if not kandis:
        return {"kopiert": 0, "uebersprungen": 0, "dateien": []}

    os.makedirs(str(ziel_ordner), exist_ok=True)
    kopiert = uebersprungen = 0
    dateien: list[str] = []
    bereits_kopiert: set[str] = set()

    for _, quelldatei in kandis:
        zieldatei = os.path.join(str(ziel_ordner), os.path.basename(quelldatei))
        # Nicht zweimal kopieren, wenn eine Datei mehrere Bibliotheken abdeckt
        if quelldatei in bereits_kopiert or os.path.exists(zieldatei):
            uebersprungen += 1
            continue
        bereits_kopiert.add(quelldatei)
        try:
            shutil.copy2(quelldatei, zieldatei)
            kopiert += 1
            dateien.append(os.path.basename(zieldatei))
        except OSError:
            uebersprungen += 1

    return {"kopiert": kopiert, "uebersprungen": uebersprungen,
            "dateien": sorted(dateien)}


# --------------------------------------------------------------------------
# Backport als eigener Ordner (ShadowMount+ ``backports/<TITLE_ID>``)
# --------------------------------------------------------------------------

def firmware_vorschlag(konsole: str, verfuegbar: "tuple[int, ...] | list[int]") -> "int | None":
    """Die Zielfirmware, die zur Konsole passt: die hoechste Stufe, die nicht ueber der Konsole liegt.

    Ein Spiel auf eine hoehere Stufe herabzusetzen, als die Konsole hat, startet nicht (der Kernel verweist die
    SDK-Angabe: ``Prospero SDK version ... is newer than system version``, Mordhau-Test 3). Je hoeher die Stufe
    unter dieser Grenze, desto weniger Ersatzbibliotheken braucht das Spiel.

    Args:
        konsole: Firmware der Konsole, ``"4.03"``, ``"12.00"`` oder ``"04030000"``; leer = unbekannt.
        verfuegbar: Die waehlbaren Hauptversionen.

    Returns:
        Die Hauptversion, oder ``None``, wenn die Konsole unbekannt ist oder unter allen Stufen liegt.
    """
    text = str(konsole or "").strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    treffer = re.match(r"(\d{1,2})\.\d", text) or re.fullmatch(r"(\d{2})\d{6}(?:\d{8})?", text)
    if not treffer:
        return None
    haupt = int(treffer.group(1))
    passend = [int(f) for f in verfuegbar if int(f) <= haupt]
    return max(passend) if passend else None


#: Der Ordner neben den Spielen, den ShadowMount+ (ab 1.7beta2) ueber das Spiel legt:
#: ``<Suchpfad>/backports/<TITLE_ID>/``. Quelle: README von ShadowMountPlus 1.7beta2 ("Backport overlay behavior"),
#: ``src/sm_scan.c`` (``resolve_backport_path_for_title``, ``mount_backport_overlay_for_title``).
BACKPORTS_ORDNER = "backports"

_TITEL_ID_FORM = re.compile(r"[A-Z]{4}\d{5}")


def titel_id_aus_param(spielordner: str) -> str:
    """Die Title-ID aus ``sce_sys/param.json`` (``titleId``, sonst aus ``contentId``); leer, wenn nicht lesbar."""
    import json
    pfad = os.path.join(str(spielordner or ""), "sce_sys", "param.json")
    try:
        with open(pfad, "r", encoding="utf-8-sig", errors="replace") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return ""
    if not isinstance(daten, dict):
        return ""
    kandidaten_ = [daten.get("titleId"), daten.get("contentId")]
    for wert in kandidaten_:
        treffer = re.search(r"[A-Z]{4}\d{5}", str(wert or "").upper())
        if treffer:
            return treffer.group(0)
    return ""


def backport_ordner_pfad(ausgabe: str, titel_id: str) -> str:
    """``<ausgabe>/backports/<TITLE_ID>`` - der Name ist genau die Title-ID, ohne Zusatz.

    ShadowMount+ nimmt innerhalb eines Suchpfads zuerst den Ordner, der genau so heisst; ein Zusatz hinter der
    Title-ID gilt erst ab 1.7beta6. Der blanke Name wirkt in jeder Fassung ab 1.7beta2.

    Raises:
        BackportFehler: ``titel_id`` hat nicht die Form ``PPSA01234``.
    """
    kennung = str(titel_id or "").strip()
    if not _TITEL_ID_FORM.fullmatch(kennung):
        raise BackportFehler(f"Ungueltige Title-ID: {titel_id!r}")
    return os.path.join(str(ausgabe or ""), BACKPORTS_ORDNER, kennung)


def _ist_emu_datei(pfad: str) -> bool:
    try:
        with open(pfad, "rb") as datei:
            daten = datei.read()
    except OSError:
        return False
    return any(k in daten for k in EMU_KENNZEICHEN)


def einfuegen_ordner_pfad(ausgabe: str, titel_id: str, firmware: int) -> str:
    """``<ausgabe>/<TITLE_ID> Backport FW<n>`` - ein Ordner, dessen Inhalt in den Spielordner kopiert wird.

    Anders als :func:`backport_ordner_pfad` (Overlay ``backports/<TITLE_ID>`` fuer ShadowMount+) steht hier
    kein ``backports`` davor: Der Inhalt hat denselben Aufbau wie das Spiel und ersetzt beim Kopieren
    genau die Dateien, die der Backport im Spielordner selbst ersetzen wuerde.

    Raises:
        BackportFehler: ``titel_id`` hat nicht die Form ``PPSA01234``.
    """
    kennung = str(titel_id or "").strip()
    if not _TITEL_ID_FORM.fullmatch(kennung):
        raise BackportFehler(f"Ungueltige Title-ID: {titel_id!r}")
    return os.path.join(str(ausgabe or ""), f"{kennung} Backport FW{int(firmware)}")


def backport_ordner_bauen(spielordner: str, ausgabe: str, titel_id: str, firmware: int,
                          fakelib_basis: str, *, minimal: bool = False,
                          texte: "dict[str, str] | None" = None,
                          melde: Any = None, abbruch: Any = None,
                          ziel_ordner: "str | None" = None,
                          fakelib_name: str = FAKELIB_ORDNER) -> dict[str, Any]:
    """Baut nur den Backport - als Ordner ``<ausgabe>/backports/<TITLE_ID>/`` - und fasst das Spiel nicht an.

    Gelegt wird, was ShadowMount+ ueber das Spiel einblendet (``mount_backport_overlay``): derselbe Pfadaufbau wie
    im Spiel, aber nur die Dateien, die sich aendern - die herabgesetzte ``eboot.bin`` und ``.prx``/``.sprx``,
    die herabgesetzte ``sce_sys/param.json`` und der Ordner ``fakelib`` mit den Ersatzbibliotheken. Der Ordner
    ``fakelib`` des Spiels (etwa AMPR EMU) wird mitgenommen, weil ShadowMount+ nur EINEN Ordner waehlt - den des
    Backports - und der des Spiels sonst unbeachtet bliebe.

    Args:
        spielordner: Dump-Ordner (bleibt unveraendert).
        ausgabe: Ordner, in dem ``backports/<TITLE_ID>`` entsteht.
        titel_id: ``PPSA01234``.
        firmware: Zielfirmware (Hauptversion).
        fakelib_basis: Wurzel der Bibliothekssaetze (``<basis>/<fw>/fakelib``).
        minimal: nur die Bibliotheken, die das Spiel importiert.
        melde: ``(text) -> None`` fuer Zwischenstaende (ohne Tk).
        abbruch: ``() -> bool`` - True haelt am naechsten Schritt an.
        ziel_ordner: Ordner fuer das Ergebnis; ohne Angabe ``<ausgabe>/backports/<TITLE_ID>``. Mit
            :func:`einfuegen_ordner_pfad` entsteht ein Ordner, dessen Inhalt man in den Spielordner kopiert.
        fakelib_name: Name des Bibliotheksordners im Ergebnis - derselbe wie beim Backport im Spielordner
            (``fakelib`` oder ``fakelib2``, siehe ``shadowmount_generation``).

    Returns:
        ``{"ziel", "gepatcht", "fehler", "bibliotheken", "fehlermeldungen", "abgebrochen"}``.

    Raises:
        BackportFehler: Title-ID oder Firmware unbrauchbar, oder ``ausgabe`` liegt im Spielordner.
    """
    ziel = ziel_ordner or backport_ordner_pfad(ausgabe, titel_id)
    ziel_ps5, ziel_ps4 = sdk_paar(firmware)
    spiel = os.path.normcase(os.path.abspath(str(spielordner)))
    wurzel = os.path.normcase(os.path.abspath(ziel))
    if wurzel == spiel or wurzel.startswith(spiel + os.sep):
        raise BackportFehler("Der Ausgabeordner liegt im Spielordner.")

    def _meld(text: str) -> None:
        if melde is not None:
            melde(text)

    def _halt() -> bool:
        return bool(abbruch is not None and abbruch())

    ergebnis: dict[str, Any] = {"ziel": ziel, "gepatcht": 0, "fehler": 0, "bibliotheken": 0,
                                "fehlermeldungen": [], "abgebrochen": False}
    os.makedirs(ziel, exist_ok=True)

    def _schreiben(rel: str, daten: bytes) -> None:
        voll = os.path.join(ziel, rel)
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        zwischen = voll + ".neu"
        try:
            with open(zwischen, "wb") as datei:
                datei.write(daten)
            os.replace(zwischen, voll)
        except OSError:
            try:
                if os.path.isfile(zwischen):
                    os.remove(zwischen)
            except OSError:
                pass
            raise

    for pfad in kandidaten(spielordner):
        if _halt():
            ergebnis["abgebrochen"] = True
            return ergebnis
        rel = os.path.relpath(pfad, spielordner)
        try:
            with open(pfad, "rb") as datei:
                roh = datei.read()
        except OSError as exc:
            ergebnis["fehler"] += 1
            ergebnis["fehlermeldungen"].append((rel, str(exc)))
            continue
        kennung, neu, grund = datei_verarbeiten(
            roh, ziel_ps5=ziel_ps5, ziel_ps4=ziel_ps4, libc_zusatz=True,
            ist_libc_datei=ist_libc(pfad), texte=texte)
        if kennung == ERG_FEHLER:
            ergebnis["fehler"] += 1
            ergebnis["fehlermeldungen"].append((rel, grund))
            continue
        if kennung != ERG_GEPATCHT:
            continue
        try:
            _schreiben(rel, neu)
        except OSError as exc:
            ergebnis["fehler"] += 1
            ergebnis["fehlermeldungen"].append((rel, str(exc)))
            continue
        ergebnis["gepatcht"] += 1
        _meld(rel)

    param_quelle = os.path.join(str(spielordner), "sce_sys", "param.json")
    if os.path.isfile(param_quelle):
        try:
            os.makedirs(os.path.join(ziel, "sce_sys"), exist_ok=True)
            shutil.copy2(param_quelle, os.path.join(ziel, "sce_sys", "param.json"))
            param_json_anpassen(ziel, firmware)
        except (OSError, BackportFehler) as exc:
            ergebnis["fehlermeldungen"].append(("sce_sys/param.json", str(exc)))

    # Eigene fakelib des Spiels zuerst (fakelib2 vor fakelib: das spaetere gewinnt), dann der Satz der Firmware.
    bib = os.path.join(ziel, fakelib_name)
    try:
        for name in reversed(FAKELIB_ORDNERNAMEN):
            quelle_ordner = os.path.join(str(spielordner), name)
            if not os.path.isdir(quelle_ordner):
                continue
            os.makedirs(bib, exist_ok=True)
            for eintrag in sorted(os.listdir(quelle_ordner)):
                voll = os.path.join(quelle_ordner, eintrag)
                if os.path.isfile(voll) and not eintrag.lower().endswith(".orig"):
                    shutil.copy2(voll, os.path.join(bib, eintrag))
        if minimal:
            satz = fakelib_dateien_benoetigt(fakelib_basis, firmware, kandidaten(spielordner))
        else:
            satz = fakelib_dateien(fakelib_basis, firmware)
        for quelle in satz:
            if _halt():
                ergebnis["abgebrochen"] = True
                return ergebnis
            name = os.path.basename(quelle)
            ablage = os.path.join(bib, name)
            # Ein bereits mitgebrachtes AMPR EMU / PlayGo-Stub des Spiels bleibt; alles andere wird ersetzt.
            if (name.lower() in AMPR_PLAYGO_BIBLIOTHEKEN and os.path.isfile(ablage)
                    and _ist_emu_datei(ablage)):
                continue
            os.makedirs(bib, exist_ok=True)
            shutil.copy2(quelle, ablage)
            ergebnis["bibliotheken"] += 1
    except OSError as exc:
        ergebnis["fehler"] += 1
        ergebnis["fehlermeldungen"].append((fakelib_name, str(exc)))
    return ergebnis
