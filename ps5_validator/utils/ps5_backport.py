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

import hashlib
import os
import struct

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

# --------------------------------------------------------------------------
# Firmware-Profile
# --------------------------------------------------------------------------

#: Firmware-Hauptversion -> (PS5-SDK, PS4-SDK). Werte aus PS5 BackPork Kitchen.
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

#: Ordner, in den die Ersatzbibliotheken im Spiel gelegt werden.
FAKELIB_ORDNER = "fakelib"

#: Alternativer Ordner, den ShadowMount+ **bevorzugt** einhaengt.
#:
#: Aus der config.ini von ShadowMount+ 1.7alpha6:
#:   "mount app0/fakelib2 when present, otherwise app0/fakelib, into common/lib"
#:
#: Es wird also immer nur EINER von beiden eingehaengt. Liegen Bibliotheken in
#: beiden Ordnern, gewinnt fakelib2 und der Inhalt von fakelib bleibt ungenutzt.
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


def kandidaten(ordner: str) -> list[str]:
    """Sammelt alle patchbaren Dateien eines Dump-Ordners.

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
            if ist_kandidat(name):
                gefunden.append(os.path.join(wurzel, name))
    return sorted(gefunden)


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

def self_zu_elf(daten: bytes) -> bytes:
    """Holt das eingebettete ELF aus einem SELF-Container.

    Nachbau von SelfUtil: Der Container legt die Segmente unveraendert ab, das
    Entpacken setzt sie nur wieder an ihre ELF-Offsets zurueck.

    Raises:
        BackportFehler: Kein SELF oder kein eingebettetes ELF auffindbar.
    """
    if len(daten) < 0x20:
        raise BackportFehler("Datei zu kurz fuer einen SELF-Container.")
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
            raise BackportFehler("Programmkopftabelle reicht ueber das Dateiende hinaus.")
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
        raise BackportFehler(f"Unglaubwuerdige ELF-Groesse: {gesamt}")

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
        raise BackportFehler("Datei zu kurz fuer ein ELF.")
    kopf = _ElfKopf(elf)
    if kopf.phentsize == 0 or kopf.phnum == 0:
        raise BackportFehler("ELF ohne Programmkopftabelle laesst sich nicht signieren.")
    # Abschnittskoepfe werden nicht uebernommen (wie im Original).
    kopf.shnum = 0

    digest = hashlib.sha256(elf).digest()

    programm_koepfe: list[dict] = []
    segmente: list[bytes] = []
    for i in range(kopf.phnum):
        basis = kopf.phoff + i * kopf.phentsize
        if basis + PHDR_SIZE > len(elf):
            raise BackportFehler("Programmkopftabelle reicht ueber das Dateiende hinaus.")
        typ, flags, offset, vaddr, paddr, filesz, memsz, align = struct.unpack_from(
            PHDR_FMT, elf, basis)
        programm_koepfe.append({
            "type": typ, "flags": flags, "offset": offset, "vaddr": vaddr,
            "paddr": paddr, "filesz": filesz, "memsz": memsz, "align": align,
        })
        if filesz > 0:
            if offset + filesz > len(elf):
                raise BackportFehler(f"Segment {i} reicht ueber das Dateiende hinaus.")
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
        raise BackportFehler("ELF enthaelt kein signierbares Segment.")

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


# --------------------------------------------------------------------------
# Gesamtablauf je Datei
# --------------------------------------------------------------------------

#: Ergebniskennungen von :func:`datei_verarbeiten`.
ERG_GEPATCHT = "gepatcht"
ERG_UEBERSPRUNGEN = "uebersprungen"
ERG_FEHLER = "fehler"


def datei_verarbeiten(daten: bytes, *, ziel_ps5: int, ziel_ps4: int,
                      libc_zusatz: bool = False,
                      ist_libc_datei: bool = False) -> tuple[str, bytes, str]:
    """Fuehrt den kompletten Ablauf auf einer Bytefolge aus.

    Schreibt nichts. Der Aufrufer ersetzt das Original nur bei ``ERG_GEPATCHT``.

    Returns:
        (Ergebniskennung, neue Bytes, Klartextbegruendung). Bei allem ausser
        ``ERG_GEPATCHT`` sind die Bytes unveraendert.
    """
    typ = dateityp(daten)
    if typ == TYP_UNBEKANNT:
        return ERG_UEBERSPRUNGEN, daten, "kein ELF und kein SELF"

    war_self = typ == TYP_SELF
    try:
        elf = self_zu_elf(daten) if war_self else daten
    except BackportFehler as exc:
        return ERG_FEHLER, daten, f"Entpacken fehlgeschlagen: {exc}"

    try:
        aktuell_ps5, _aktuell_ps4 = sdk_lesen(elf)
    except SdkNichtGefunden:
        return ERG_UEBERSPRUNGEN, daten, "keine SDK-Angabe enthalten"

    if not muss_gepatcht_werden(aktuell_ps5, ziel_ps5):
        return (ERG_UEBERSPRUNGEN, daten,
                f"bereits {firmware_text(aktuell_ps5)} oder aelter")

    try:
        elf, alt_ps5, _alt_ps4 = sdk_setzen(elf, ziel_ps5, ziel_ps4)
    except BackportFehler as exc:
        return ERG_FEHLER, daten, f"SDK nicht setzbar: {exc}"

    zusatz = ""
    if libc_zusatz and ist_libc_datei:
        elf, stelle = libc_patchen(elf)
        if stelle >= 0:
            zusatz = f", libc-Patch bei 0x{stelle:X}"
        elif stelle == -2:
            zusatz = ", libc bereits gepatcht"
        else:
            zusatz = ", libc-Muster nicht gefunden"

    # Signieren ist Pflicht - eine unsignierte Datei darf nie zurueckgegeben werden.
    try:
        ergebnis = elf_signieren(elf)
    except BackportFehler as exc:
        return ERG_FEHLER, daten, f"Signieren fehlgeschlagen: {exc}"

    return (ERG_GEPATCHT, ergebnis,
            f"{firmware_text(alt_ps5)} -> {firmware_text(ziel_ps5)}{zusatz}")


# --------------------------------------------------------------------------
# Ersatzbibliotheken
# --------------------------------------------------------------------------

def fakelib_quelle(basis: str, firmware: int) -> str:
    """Pfad zum mitgelieferten Bibliothekssatz einer Firmware."""
    return os.path.join(str(basis or ""), str(int(firmware)), FAKELIB_ORDNER)


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

    Gedacht fuer die Warnung, wenn beide existieren: Dann haengt die Konsole nur
    ``fakelib2`` ein, und was in ``fakelib`` liegt, wirkt nicht.
    """
    da = []
    for name in FAKELIB_ORDNERNAMEN:
        if os.path.isdir(os.path.join(str(spielordner or ""), name)):
            da.append(name)
    return da


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
