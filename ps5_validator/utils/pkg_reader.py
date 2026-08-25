"""Read-only Parser fuer echte PS5-Pakete (.pkg: CNT-Metadatencontainer und/oder FIH-Finalabbild.

Wichtig: Dies ist NICHT dasselbe Format wie .ffpkg (unser UFS2-Rohabbild fuer ShadowMount).
Ein echtes PS5-.pkg ist ein CNT(+PFS)+FIH-Container mit AES-XTS-Verschluesselung und
RSA-3072-Signatur. Dieses Modul liest ausschliesslich die unverschluesselten Strukturfelder
(Header, Entry-Tabelle, Namen, Content-ID) und dekodiert optional unverschluesselte
Klartext-Entries wie param.json. Es entschluesselt keine geschuetzten Entries und benoetigt
keine privaten Schluessel.

Byte-Layout durch Gegenlesen des quelloffenen LibProsperoPKG-Readers (GPL-3.0-or-later,
https://github.com/SvenGDK/LibProsperoPKG) ermittelt; diese Implementierung ist eine
eigenstaendige Python-Neuentwicklung auf Basis der (nicht schutzfaehigen) Format-Fakten,
kein Uebersetzen/Kopieren des dortigen C#-Quellcodes.
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass, field

CNT_MAGIC = b"\x7fCNT"
FIH_MAGIC = b"\x7fFIH"

HEADER_SIZE = 0x5A0
ENTRY_META_SIZE = 0x20
CONTENT_ID_SIZE = 0x30
ENTRY_FLAG_ENCRYPTED = 0x80000000

FIH_SIGNED_BYTE_OFFSET = 0x05
FIH_FORMAT_VERSION_OFFSET = 0x06
FIH_PFS_IMAGE_OFFSET_OFFSET = 0x10
FIH_PFS_IMAGE_SIZE_OFFSET = 0x18
FIH_DATA_REGION_BLOCK_COUNT_OFFSET = 0x50
FIH_EMBEDDED_CNT_OFFSET_OFFSET = 0x58
FIH_INNER_IMAGE_BLOCK_COUNT_OFFSET = 0x90
FIH_META_BLOCK_COUNT_OFFSET = 0x94
FIH_META_BLOCK_COUNT_MIRROR_OFFSET = 0x98
FIH_CONTENT_VERSION_OFFSET = 0x9C
FIH_INNER_IMAGE_SIZE_OFFSET = 0xA0
FIH_INNER_IMAGE_LOGICAL_SIZE_OFFSET = 0xA8
FIH_OUTER_FILE_COUNT_OFFSET = 0xF0
FIH_FLAT_PATH_TABLE_BLOCK_COUNT_OFFSET = 0xF8
FIH_HEADER_REGION_SIZE = 0x10000
FIH_READ_SIZE = 0x100  # genuegt fuer alle oben gelisteten FIH-Felder
FIH_REQUIRED_FORMAT_VERSION = 3  # von der Konsolen-Mountpfad-Pruefung verlangte Formatversion

# Bekannte Entry-IDs (Untermenge, die fuer Inspektion relevant ist).
KNOWN_ENTRY_NAMES: dict[int, str] = {
    0x0001: "digests",
    0x0010: "entry_keys",
    0x0020: "image_key",
    0x0080: "general_digests",
    0x0100: "metas",
    0x0200: "entry_names",
    0x0400: "license.dat",
    0x0401: "license.info",
    0x040A: "imagedigs.dat",
    0x1000: "param.sfo",
    0x1001: "playgo-chunk.dat",
    0x1002: "playgo-chunk.sha",
    0x1003: "playgo-manifest.xml",
    0x1200: "icon0.png",
    0x1220: "pic0.png",
    0x1240: "snd0.at9",
    0x1280: "icon0.dds",
    0x12A0: "pic0.dds",
    0x12C0: "pic1.dds",
    0x2000: "param.json",
    0x2010: "playgo-hash-table.dat",
    0x2011: "playgo-ficm.dat",
}


class PkgParseError(Exception):
    """Wird ausgeloest, wenn eine Datei kein erkennbares PS5-PKG ist oder strukturell ungueltig ist."""


@dataclass
class PkgEntry:
    raw_id: int
    name: str
    name_table_offset: int
    flags1: int
    flags2: int
    data_offset: int
    data_size: int

    @property
    def encrypted(self) -> bool:
        return bool(self.flags1 & ENTRY_FLAG_ENCRYPTED)


@dataclass
class PkgHeader:
    flags: int
    entry_count: int
    sc_entry_count: int
    entry_table_offset: int
    body_offset: int
    body_size: int
    content_id: str
    drm_type: int
    content_type: int
    content_flags: int


@dataclass
class FihHeader:
    signed_byte: int
    format_version: int
    pfs_image_offset: int
    pfs_image_size: int
    data_region_block_count: int
    embedded_cnt_offset: int
    inner_image_block_count: int
    meta_block_count: int
    meta_block_count_mirror: int
    content_version: int
    inner_image_size: int
    inner_image_logical_size: int
    outer_file_count: int
    flat_path_table_block_count: int

    @property
    def is_debug(self) -> bool:
        return self.signed_byte == 0x00

    @property
    def is_retail(self) -> bool:
        return self.signed_byte == 0x80


@dataclass
class PkgInfo:
    path: str
    type: str  # "meta" | "full_debug" | "full_retail"
    fih: FihHeader | None = None
    header: PkgHeader | None = None
    entries: list[PkgEntry] = field(default_factory=list)

    def find_entry(self, entry_id: int) -> PkgEntry | None:
        for entry in self.entries:
            if entry.raw_id == entry_id:
                return entry
        return None


def detect_pkg_type(path: str) -> str | None:
    """Erkennt den Pakettyp anhand der 4-Byte-Magic (und bei FIH des signed byte).

    Returns:
        "meta", "full_debug", "full_retail" oder None, falls keine erkennbare PS5-PKG-Datei.
    """
    with open(path, "rb") as f:
        head = f.read(6)
    if len(head) < 6:
        return None
    if head[:4] == CNT_MAGIC:
        return "meta"
    if head[:4] == FIH_MAGIC:
        signed_byte = head[5]
        if signed_byte == 0x80:
            return "full_retail"
        if signed_byte == 0x00:
            return "full_debug"
        return None
    return None


def _read_cnt_header(data: bytes, base: int) -> PkgHeader:
    if len(data) < base + HEADER_SIZE:
        raise PkgParseError("CNT-Header ist abgeschnitten (Datei zu kurz).")

    def u32(off: int) -> int:
        return struct.unpack_from(">I", data, base + off)[0]

    def u16(off: int) -> int:
        return struct.unpack_from(">H", data, base + off)[0]

    def u64(off: int) -> int:
        return struct.unpack_from(">Q", data, base + off)[0]

    content_id_raw = data[base + 0x40: base + 0x40 + CONTENT_ID_SIZE]
    content_id = content_id_raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")

    return PkgHeader(
        flags=u32(0x04),
        entry_count=u32(0x10),
        sc_entry_count=u16(0x14),
        entry_table_offset=u32(0x18),
        body_offset=u64(0x20),
        body_size=u64(0x28),
        content_id=content_id,
        drm_type=u32(0x70),
        content_type=u32(0x74),
        content_flags=u32(0x78),
    )


def _read_entry_table(data: bytes, base: int, header: PkgHeader) -> list[PkgEntry]:
    max_entries = (len(data) - (base + header.entry_table_offset)) // ENTRY_META_SIZE
    if header.entry_count > max_entries or header.entry_count > 0x10000:
        raise PkgParseError("Entry-Tabelle ist unplausibel (Anzahl außerhalb des gültigen Bereichs).")

    entries: list[PkgEntry] = []
    table_start = base + header.entry_table_offset
    for i in range(header.entry_count):
        rec_off = table_start + i * ENTRY_META_SIZE
        rec = data[rec_off: rec_off + ENTRY_META_SIZE]
        if len(rec) < ENTRY_META_SIZE:
            raise PkgParseError("Entry-Tabelle ist abgeschnitten.")
        raw_id, name_table_offset, flags1, flags2, data_offset, data_size = struct.unpack(">IIIIII", rec[:24])
        entries.append(PkgEntry(
            raw_id=raw_id,
            name=KNOWN_ENTRY_NAMES.get(raw_id, f"0x{raw_id:04X}"),
            name_table_offset=name_table_offset,
            flags1=flags1,
            flags2=flags2,
            data_offset=data_offset,
            data_size=data_size,
        ))
    _resolve_names(data, base, entries)
    return entries


def _resolve_names(data: bytes, base: int, entries: list[PkgEntry]) -> None:
    """Löst lesbare Entry-Namen aus dem ENTRY_NAMES-Eintrag (id 0x0200) auf, falls vorhanden.

    Die Namenstabelle ist ein Block NUL-terminierter ASCII-Strings; jeder Entry indiziert
    hinein per `name_table_offset`. Wo vorhanden, hat der aufgelöste Name Vorrang vor dem
    statischen `KNOWN_ENTRY_NAMES`-Fallback.
    """
    name_entry = next((e for e in entries if e.raw_id == 0x0200), None)
    if name_entry is None or name_entry.data_size == 0:
        return
    start = base + name_entry.data_offset
    names = data[start: start + name_entry.data_size]
    if not names:
        return
    for entry in entries:
        if entry.name_table_offset == 0 or entry.name_table_offset >= len(names):
            continue
        end = names.find(b"\x00", entry.name_table_offset)
        if end < 0:
            end = len(names)
        resolved = names[entry.name_table_offset:end].decode("ascii", errors="replace")
        if resolved:
            entry.name = resolved


def _read_fih_header(data: bytes) -> FihHeader:
    if len(data) < FIH_READ_SIZE:
        raise PkgParseError("FIH-Header ist abgeschnitten (Datei zu kurz).")

    def u16(off: int) -> int:
        return struct.unpack_from("<H", data, off)[0]

    def u32(off: int) -> int:
        return struct.unpack_from("<I", data, off)[0]

    def u64(off: int) -> int:
        return struct.unpack_from("<Q", data, off)[0]

    return FihHeader(
        signed_byte=data[FIH_SIGNED_BYTE_OFFSET],
        format_version=u16(FIH_FORMAT_VERSION_OFFSET),
        pfs_image_offset=u64(FIH_PFS_IMAGE_OFFSET_OFFSET),
        pfs_image_size=u64(FIH_PFS_IMAGE_SIZE_OFFSET),
        data_region_block_count=u64(FIH_DATA_REGION_BLOCK_COUNT_OFFSET),
        embedded_cnt_offset=u64(FIH_EMBEDDED_CNT_OFFSET_OFFSET),
        inner_image_block_count=u32(FIH_INNER_IMAGE_BLOCK_COUNT_OFFSET),
        meta_block_count=u32(FIH_META_BLOCK_COUNT_OFFSET),
        meta_block_count_mirror=u32(FIH_META_BLOCK_COUNT_MIRROR_OFFSET),
        content_version=u32(FIH_CONTENT_VERSION_OFFSET),
        inner_image_size=u64(FIH_INNER_IMAGE_SIZE_OFFSET),
        inner_image_logical_size=u64(FIH_INNER_IMAGE_LOGICAL_SIZE_OFFSET),
        outer_file_count=u32(FIH_OUTER_FILE_COUNT_OFFSET),
        flat_path_table_block_count=u32(FIH_FLAT_PATH_TABLE_BLOCK_COUNT_OFFSET),
    )


def read_pkg(path: str) -> PkgInfo:
    """Liest die Struktur eines PS5-.pkg (CNT-Metadatencontainer oder FIH-Finalabbild).

    Entschluesselt keine geschuetzten Nutzdaten; liefert Header, Entry-Tabelle und
    (falls unverschluesselt) den Rohinhalt kleiner Klartext-Entries ueber `read_entry_payload`.

    Raises:
        PkgParseError: Datei ist kein erkennbares/gueltiges PS5-PKG.
    """
    pkg_type = detect_pkg_type(path)
    if pkg_type is None:
        raise PkgParseError(f"Keine erkennbare PS5-PKG-Datei (unbekannte Magic): {path}")

    with open(path, "rb") as f:
        data = f.read()

    if pkg_type == "meta":
        header = _read_cnt_header(data, 0)
        entries = _read_entry_table(data, 0, header)
        return PkgInfo(path=path, type=pkg_type, header=header, entries=entries)

    fih = _read_fih_header(data)
    cnt_base = fih.embedded_cnt_offset
    info = PkgInfo(path=path, type=pkg_type, fih=fih)
    if cnt_base <= 0 or cnt_base + HEADER_SIZE > len(data):
        return info

    header = _read_cnt_header(data, cnt_base)
    entries = _read_entry_table(data, cnt_base, header)
    info.header = header
    info.entries = entries
    return info


def read_entry_payload(path: str, info: PkgInfo, entry: PkgEntry) -> bytes | None:
    """Liest die Rohbytes eines Entries, sofern er nicht als verschluesselt markiert ist.

    Returns:
        Die Rohbytes, oder None wenn der Entry verschluesselt ist oder ausserhalb der Datei liegt.
    """
    if entry.encrypted or entry.data_size == 0:
        return None
    base = info.fih.embedded_cnt_offset if info.fih is not None else 0
    with open(path, "rb") as f:
        f.seek(base + entry.data_offset)
        return f.read(entry.data_size)


def try_read_param_json(path: str, info: PkgInfo) -> dict | None:
    """Liest und dekodiert den param.json-Entry (id 0x2000), falls vorhanden und unverschluesselt."""
    entry = info.find_entry(0x2000)
    if entry is None:
        return None
    payload = read_entry_payload(path, info, entry)
    if payload is None:
        return None
    try:
        return json.loads(payload.decode("utf-8", errors="strict").rstrip("\x00"))
    except (ValueError, UnicodeDecodeError):
        return None
