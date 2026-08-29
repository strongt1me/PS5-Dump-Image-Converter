"""Read-only Struktur-Inspektor fuer PS4/PS5-SELF-Dateien (Signed ELF).

WICHTIG - bewusste Umfangsgrenze: Dieses Modul liest AUSSCHLIESSLICH die
unverschluesselten Strukturfelder (Container-Header, Segment-Tabelle, eingebettete
ELF-Kopfdaten, Extended-Info mit Authority-ID/Programmtyp/Digest). Es entschluesselt
und verifiziert KEINE geschuetzten Segmente, prueft KEINE Signaturen und enthaelt/
benoetigt KEIN privates Schluesselmaterial - reine, informative Struktur-Anzeige,
analog zu ``pkg_reader.py``. Eine echte Entschluesselung wuerde Konsolen-Schluessel
aus einem Exploit-Dump voraussetzen, die dieses Projekt bewusst nicht beschafft.

Byte-Layout durch Gegenlesen des quelloffenen LibProsperoPKG-Fself-Parsers
(GPL-3.0-or-later, https://github.com/SvenGDK/LibProsperoPKG,
Content/ProsperoFself.cs) ermittelt; eigenstaendige Python-Neuentwicklung auf Basis
der (nicht schutzfaehigen) Format-Fakten, kein Uebersetzen/Kopieren des C#-Quellcodes.
"""
from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field

SELF_MAGIC = 0x1D3D154F  # u32 little-endian bei Dateioffset 0x00
# Zweite, gleichwertige PS5-Magic. An echten Dumps nachgemessen: identisches
# Kopflayout (version/mode/endian, header_size, Segmenttabelle, eingebetteter
# ELF-Kopf an derselben Stelle) - es unterscheidet sich ausschliesslich diese
# Konstante. Ohne sie wurde rund die Haelfte realer eboot.bin abgewiesen.
SELF_MAGIC_ALT = 0xEEF51454
SELF_MAGICS = (SELF_MAGIC, SELF_MAGIC_ALT)
HEADER_SIZE = 0x20
SEGMENT_ENTRY_SIZE = 0x20
EXT_INFO_SIZE = 0x40
ELF_MAGIC = b"\x7fELF"

# Containerarten, die read_self() unterscheidet.
CONTAINER_SELF = "self"   # signierte Huelle (SELF/fSELF) mit eingebettetem ELF
CONTAINER_ELF = "elf"     # reines, unsigniertes ELF ohne Huelle

# Fuer die Strukturanzeige werden nur Kopfbereiche gebraucht. Ein eboot.bin kann
# mehrere hundert MB gross sein - fruehere Fassungen lasen die Datei komplett in
# den Speicher, obwohl nie mehr als wenige KB ausgewertet werden.
MAX_HEADER_READ = 1 << 20

# Segment-Flags-Bitfeld (u64), siehe ProsperoFself.cs SelfSegment-Record
SEGMENT_FLAG_ORDERED = 0x1
SEGMENT_FLAG_ENCRYPTED = 0x2
SEGMENT_FLAG_SIGNED = 0x4
SEGMENT_FLAG_COMPRESSED = 0x8
SEGMENT_FLAG_BLOCKED = 0x800

# Authority-ID-Kategorie = oberstes Byte der 64-Bit Authority-ID
AUTHORITY_CATEGORY_FAKE = 0x31
AUTHORITY_CATEGORY_GENUINE = 0x45
AUTHORITY_CATEGORY_PRIVILEGED = 0x48
#: Kategorie der Fake-Autoritaet, die make_fself.py aus dem PS5-Payload-SDK
#: vergibt (AuthID 0x3800000000000022). Bis v1.9.1 lief sie als Unbekannt
#: durch, obwohl gerade selbst gebaute Anwendungen sie tragen.
AUTHORITY_CATEGORY_SDK_FAKE = 0x38

_AUTHORITY_CATEGORY_NAMES: dict[int, str] = {
    AUTHORITY_CATEGORY_FAKE: "Fake/Debug",
    AUTHORITY_CATEGORY_GENUINE: "Genuine",
    AUTHORITY_CATEGORY_PRIVILEGED: "Privilegiertes System",
    AUTHORITY_CATEGORY_SDK_FAKE: "Fake (Payload-SDK)",
}


class SelfParseError(Exception):
    """Wird ausgeloest, wenn eine Datei keine erkennbare/gueltige SELF-Datei ist."""


@dataclass
class SelfSegment:
    raw_flags: int
    file_offset: int
    file_size: int
    memory_size: int

    @property
    def ordered(self) -> bool:
        return bool(self.raw_flags & SEGMENT_FLAG_ORDERED)

    @property
    def encrypted(self) -> bool:
        return bool(self.raw_flags & SEGMENT_FLAG_ENCRYPTED)

    @property
    def signed(self) -> bool:
        return bool(self.raw_flags & SEGMENT_FLAG_SIGNED)

    @property
    def compressed(self) -> bool:
        return bool(self.raw_flags & SEGMENT_FLAG_COMPRESSED)

    @property
    def blocked(self) -> bool:
        return bool(self.raw_flags & SEGMENT_FLAG_BLOCKED)

    @property
    def segment_id(self) -> int:
        return (self.raw_flags >> 20) & 0xFFFF


@dataclass
class SelfHeader:
    version: int
    mode: int
    endian: int
    attributes: int
    key_type: int
    header_size: int
    meta_size: int
    file_size: int
    segment_count: int
    flags: int


@dataclass
class ElfHeaderInfo:
    ei_class: int
    ei_data: int
    ei_version: int
    ei_osabi: int
    e_type: int
    e_machine: int
    e_version: int
    e_entry: int
    e_phoff: int
    e_phnum: int

    @property
    def is_64bit(self) -> bool:
        return self.ei_class == 2

    @property
    def type_name(self) -> str:
        return {
            0x0002: "ET_EXEC (ausführbar)",
            0x0003: "ET_DYN (dynamisch/PIE)",
            0xFE00: "ET_SCE_EXEC",
            0xFE10: "ET_SCE_DYNEXEC",
        }.get(self.e_type, f"0x{self.e_type:04X}")


@dataclass
class SelfExtInfo:
    authority_id: int
    program_type: int
    app_version: int
    firmware_version: int
    digest: bytes

    @property
    def authority_category(self) -> int:
        return (self.authority_id >> 56) & 0xFF

    @property
    def authority_category_name(self) -> str:
        return _AUTHORITY_CATEGORY_NAMES.get(self.authority_category, "Unbekannt")


@dataclass
class SelfInfo:
    path: str
    header: SelfHeader | None = None
    segments: list[SelfSegment] = field(default_factory=list)
    elf_header: ElfHeaderInfo | None = None
    ext_info: SelfExtInfo | None = None
    container: str = CONTAINER_SELF
    magic: int = 0

    @property
    def is_self(self) -> bool:
        return self.container == CONTAINER_SELF

    @property
    def magic_name(self) -> str:
        """Benennt die erkannte Magic, damit die Anzeige beide Varianten auseinanderhaelt."""
        if self.container == CONTAINER_ELF:
            return "ELF"
        if self.magic == SELF_MAGIC:
            return f"SELF (0x{SELF_MAGIC:08X})"
        if self.magic == SELF_MAGIC_ALT:
            return f"SELF (0x{SELF_MAGIC_ALT:08X})"
        return f"0x{self.magic:08X}"


def _align_up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


def detect_self(path: str) -> bool:
    """Erkennt anhand der 4-Byte-Magic, ob eine Datei ein SELF-Container ist."""
    with open(path, "rb") as f:
        head = f.read(4)
    return len(head) == 4 and struct.unpack("<I", head)[0] in SELF_MAGICS


def detect_elf(path: str) -> bool:
    """Erkennt ein reines, unsigniertes ELF (kommt bei manchen Dumps als eboot.bin vor)."""
    with open(path, "rb") as f:
        return f.read(4) == ELF_MAGIC


def _parse_elf_header(data: bytes, off: int) -> ElfHeaderInfo | None:
    """Liest den 64-Bit-ELF-Kopf ab ``off``; None, wenn dort keiner liegt."""
    if off + 0x40 > len(data) or data[off:off + 4] != ELF_MAGIC:
        return None
    e_phnum = struct.unpack_from("<H", data, off + 0x38)[0] if off + 0x3A <= len(data) else 0
    return ElfHeaderInfo(
        ei_class=data[off + 4], ei_data=data[off + 5],
        ei_version=data[off + 6], ei_osabi=data[off + 7],
        e_type=struct.unpack_from("<H", data, off + 0x10)[0],
        e_machine=struct.unpack_from("<H", data, off + 0x12)[0],
        e_version=struct.unpack_from("<I", data, off + 0x14)[0],
        e_entry=struct.unpack_from("<Q", data, off + 0x18)[0],
        e_phoff=struct.unpack_from("<Q", data, off + 0x20)[0],
        e_phnum=e_phnum,
    )


def read_self(path: str) -> SelfInfo:
    """Liest die Struktur einer SELF- oder ELF-Datei (Header, Segmente, ELF-Kopf, Extended-Info).

    Entschluesselt keine geschuetzten Segmentdaten; liefert ausschliesslich Klartext-
    Strukturfelder. Erkennt beide PS5-SELF-Magics sowie reine ELF-Dateien, die in
    manchen Dumps unverpackt als ``eboot.bin`` liegen.

    Gelesen wird nur der Kopfbereich (hoechstens ``MAX_HEADER_READ`` Bytes plus ein
    gezielter Nachschlag fuer die Extended-Info), nicht die gesamte Datei.

    Raises:
        SelfParseError: Datei ist weder ein SELF-Container noch ein ELF.
    """
    try:
        file_size_on_disk = os.path.getsize(path)
    except OSError:
        file_size_on_disk = 0

    with open(path, "rb") as f:
        data = f.read(MAX_HEADER_READ)

        if len(data) >= 4 and data[:4] == ELF_MAGIC:
            # Reines ELF ohne SELF-Huelle: es gibt keinen Container-Header und
            # keine Extended-Info, der ELF-Kopf steht direkt am Dateianfang.
            return SelfInfo(
                path=path, header=None, segments=[],
                elf_header=_parse_elf_header(data, 0), ext_info=None,
                container=CONTAINER_ELF,
                magic=struct.unpack_from("<I", data, 0)[0],
            )

        if len(data) < HEADER_SIZE:
            raise SelfParseError(f"Datei ist zu kurz für einen SELF-Kopf: {path}")
        magic = struct.unpack_from("<I", data, 0)[0]
        if magic not in SELF_MAGICS:
            raise SelfParseError(f"Keine erkennbare SELF-Datei (unbekannte Magic): {path}")

        info = _read_self_body(f, data, path, magic, file_size_on_disk)
    return info


def _read_self_body(f, data: bytes, path: str, magic: int, file_size_on_disk: int) -> SelfInfo:
    """Wertet den bereits eingelesenen Kopfbereich eines SELF-Containers aus."""
    version, mode, endian, attributes = data[4], data[5], data[6], data[7]
    key_type = struct.unpack_from("<I", data, 0x08)[0]
    header_size = struct.unpack_from("<H", data, 0x0C)[0]
    meta_size = struct.unpack_from("<H", data, 0x0E)[0]
    file_size = struct.unpack_from("<Q", data, 0x10)[0]
    segment_count = struct.unpack_from("<H", data, 0x18)[0]
    flags = struct.unpack_from("<H", data, 0x1A)[0]
    header = SelfHeader(
        version=version, mode=mode, endian=endian, attributes=attributes,
        key_type=key_type, header_size=header_size, meta_size=meta_size,
        file_size=file_size, segment_count=segment_count, flags=flags,
    )

    segments: list[SelfSegment] = []
    seg_table_start = HEADER_SIZE
    for i in range(segment_count):
        off = seg_table_start + i * SEGMENT_ENTRY_SIZE
        if off + SEGMENT_ENTRY_SIZE > len(data):
            break
        raw_flags, seg_offset, seg_file_size, seg_mem_size = struct.unpack_from("<QQQQ", data, off)
        segments.append(SelfSegment(raw_flags, seg_offset, seg_file_size, seg_mem_size))

    elf_start = seg_table_start + segment_count * SEGMENT_ENTRY_SIZE
    elf_header = _parse_elf_header(data, elf_start)
    ext_info: SelfExtInfo | None = None

    if elf_header is not None:
        elf_region_len = max(elf_header.e_phoff + elf_header.e_phnum * 0x38, 0x40)
        ext_start = _align_up(elf_start + elf_region_len, 0x10)
        ext_block = data[ext_start: ext_start + EXT_INFO_SIZE]
        if len(ext_block) < EXT_INFO_SIZE and ext_start + EXT_INFO_SIZE <= file_size_on_disk:
            # Extended-Info liegt hinter dem eingelesenen Kopfbereich: gezielt
            # nachladen statt die ganze Datei in den Speicher zu holen.
            try:
                f.seek(ext_start)
                ext_block = f.read(EXT_INFO_SIZE)
            except OSError:
                ext_block = b""
        if len(ext_block) == EXT_INFO_SIZE:
            ext_info = SelfExtInfo(
                authority_id=struct.unpack_from("<Q", ext_block, 0)[0],
                program_type=struct.unpack_from("<Q", ext_block, 0x08)[0],
                app_version=struct.unpack_from("<Q", ext_block, 0x10)[0],
                firmware_version=struct.unpack_from("<Q", ext_block, 0x18)[0],
                digest=ext_block[0x20:0x40],
            )

    return SelfInfo(
        path=path, header=header, segments=segments,
        elf_header=elf_header, ext_info=ext_info,
        container=CONTAINER_SELF, magic=magic,
    )
