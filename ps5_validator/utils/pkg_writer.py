"""Writer fuer strukturell gueltige, UNSIGNIERTE PS5-Debug-.pkg-Container.

WICHTIG - bewusste Umfangsgrenzen (siehe README/CHANGELOG fuer die Begruendung):

- Erzeugt ausschliesslich Pakete mit FIH ``signed_byte = 0x00`` ("Debug"-Kennzeichnung).
  Es wird KEINE echte RSA-3072-Signatur erzeugt oder vorgetaeuscht - dafuer waere
  privates Sony-/SDK-Schluesselmaterial noetig, auf das dieses Projekt keinen Zugriff
  hat und das bewusst nicht nachgebaut wird.
- Es wird KEIN Fake-SELF-Autoritaets-Spoofing von ELF-Modulen durchgefuehrt. ELF-Dateien
  werden unveraendert als gewoehnliche Entries/Dateien im inneren PFS-Image abgelegt.
- Die Digest-Eintraege (``digests``/``general_digests``) sind reine, selbst definierte
  SHA3-256-Struktur-Pruefsummen fuer die eigene Rundlauf-Pruefung (siehe pkg_reader.py).
  Sie entsprechen NICHT zwingend dem exakten, von echter PS5-Firmware verifizierten
  Digest-Format - dafuer fehlt eine echte Referenzimplementierung/-hardware zum Abgleich.
- Der optionale ``image_key``-Eintrag speichert den EKPFS-Schluessel im Klartext ab
  (kein DRM-Schluesseltausch). Das ist fuer "license-free"-Debug-Pakete auf bereits
  gejailbreakten Konsolen ausreichend, aber NICHT das, was ein echtes retail-.pkg tut.
- Nicht auf echter PS5-Hardware getestet (kein Testgeraet vorhanden) - experimentell.

Byte-Layout entspricht dem in ``pkg_reader.py`` implementierten (aus dem quelloffenen
LibProsperoPKG-Reader, GPL-3.0-or-later, zurueckgelesenen) Format. Eigenstaendige
Python-Neuentwicklung auf Basis der (nicht schutzfaehigen) Format-Fakten.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
from dataclasses import dataclass

from .pkg_reader import (
    CNT_MAGIC,
    CONTENT_ID_SIZE,
    ENTRY_META_SIZE,
    FIH_CONTENT_VERSION_OFFSET,
    FIH_DATA_REGION_BLOCK_COUNT_OFFSET,
    FIH_EMBEDDED_CNT_OFFSET_OFFSET,
    FIH_FLAT_PATH_TABLE_BLOCK_COUNT_OFFSET,
    FIH_FORMAT_VERSION_OFFSET,
    FIH_HEADER_REGION_SIZE,
    FIH_INNER_IMAGE_BLOCK_COUNT_OFFSET,
    FIH_INNER_IMAGE_LOGICAL_SIZE_OFFSET,
    FIH_INNER_IMAGE_SIZE_OFFSET,
    FIH_MAGIC,
    FIH_META_BLOCK_COUNT_MIRROR_OFFSET,
    FIH_META_BLOCK_COUNT_OFFSET,
    FIH_OUTER_FILE_COUNT_OFFSET,
    FIH_PFS_IMAGE_OFFSET_OFFSET,
    FIH_PFS_IMAGE_SIZE_OFFSET,
    FIH_REQUIRED_FORMAT_VERSION,
    FIH_SIGNED_BYTE_OFFSET,
    HEADER_SIZE,
    KNOWN_ENTRY_NAMES,
)

_ALIGN = 0x10
_PFS_BLOCK_ALIGN = 0x10000  # entspricht FIH_HEADER_REGION_SIZE
ZERO_EKPFS = b"\x00" * 32


class PkgWriteError(Exception):
    """Wird bei ungueltigen Eingaben (z. B. zu vielen Entries) ausgeloest."""


def _align_up(value: int, align: int) -> int:
    return (value + align - 1) // align * align


@dataclass
class _WriteEntry:
    raw_id: int
    name: str
    payload: bytes
    name_table_offset: int = 0
    data_offset: int = 0
    data_size: int = 0


def _entry_name(raw_id: int, override: str | None) -> str:
    if override:
        return override
    return KNOWN_ENTRY_NAMES.get(raw_id, f"0x{raw_id:04X}")


def build_cnt_container(
    content_id: str,
    param_json: dict,
    extra_entries: list[tuple[int, str, bytes]] | None = None,
    ekpfs: bytes | None = None,
    drm_type: int = 0,
    content_type: int = 0,
    content_flags: int = 0,
) -> bytes:
    """Baut einen vollstaendigen CNT-Metadatencontainer (Header + Entry-/Namenstabelle + Body).

    Args:
        content_id: PS5-Content-ID (wird auf 0x30 Bytes ASCII zugeschnitten/aufgefuellt).
        param_json: Inhalt fuer den ``param.json``-Entry (id 0x2000).
        extra_entries: Zusaetzliche (id, name, payload)-Tripel, z. B. Icons.
        ekpfs: Optionaler 32-Byte-EKPFS-Schluessel; erzeugt bei Angabe einen
            ``image_key``-Entry (id 0x0020) im Klartext (siehe Modul-Docstring).
        drm_type/content_type/content_flags: Rohe Header-Felder, Standard 0
            (kein bekanntes echtes Sony-Enum verifiziert - nur strukturell abgelegt).

    Returns:
        Vollstaendige CNT-Containerbytes, beginnend mit der ``\\x7fCNT``-Magic.
    """
    param_bytes = json.dumps(param_json, indent=2, ensure_ascii=False).encode("utf-8")

    entries: list[_WriteEntry] = [_WriteEntry(0x0200, "entry_names", b"")]
    entries.append(_WriteEntry(0x2000, _entry_name(0x2000, None), param_bytes))
    for raw_id, name, payload in extra_entries or []:
        entries.append(_WriteEntry(raw_id, _entry_name(raw_id, name), payload))
    if ekpfs is not None:
        if len(ekpfs) != 32:
            raise PkgWriteError("ekpfs muss genau 32 Bytes lang sein.")
        entries.append(_WriteEntry(0x0020, _entry_name(0x0020, None), ekpfs))

    if len(entries) > 0x10000:
        raise PkgWriteError("Zu viele Entries.")

    # Namenstabelle aus allen bisherigen Entries (Reihenfolge = Tabellenreihenfolge).
    names_blob = bytearray()
    for entry in entries:
        entry.name_table_offset = len(names_blob)
        names_blob += entry.name.encode("ascii", errors="replace") + b"\x00"
    entries[0].payload = bytes(names_blob)

    # Digest-Entries zuletzt anhaengen (decken alle vorherigen Payloads ab).
    digestable = entries[1:]  # ohne entry_names selbst
    digest_payload = b"".join(hashlib.sha3_256(e.payload).digest() for e in digestable)
    digests_entry = _WriteEntry(0x0001, _entry_name(0x0001, None), digest_payload)
    digests_entry.name_table_offset = len(names_blob)
    names_blob += digests_entry.name.encode("ascii", errors="replace") + b"\x00"
    entries.append(digests_entry)

    general_digest = hashlib.sha3_256(b"".join(e.payload for e in digestable) + digest_payload).digest()
    general_entry = _WriteEntry(0x0080, _entry_name(0x0080, None), general_digest)
    general_entry.name_table_offset = len(names_blob)
    names_blob += general_entry.name.encode("ascii", errors="replace") + b"\x00"
    entries.append(general_entry)
    entries[0].payload = bytes(names_blob)
    entries[0].data_size = len(names_blob)

    entry_count = len(entries)
    entry_table_offset = HEADER_SIZE
    entry_table_size = entry_count * ENTRY_META_SIZE
    name_table_offset = _align_up(entry_table_offset + entry_table_size, _ALIGN)
    entries[0].data_offset = name_table_offset

    cursor = _align_up(name_table_offset + len(names_blob), _ALIGN)
    for entry in entries[1:]:
        entry.data_offset = cursor
        entry.data_size = len(entry.payload)
        cursor = _align_up(cursor + entry.data_size, _ALIGN)

    body_offset = name_table_offset
    body_size = cursor - body_offset
    total_size = cursor

    buf = bytearray(total_size)
    buf[0:4] = CNT_MAGIC
    content_id_bytes = content_id.encode("ascii", errors="replace")[:CONTENT_ID_SIZE].ljust(CONTENT_ID_SIZE, b"\x00")

    struct.pack_into(">I", buf, 0x04, 0)  # flags
    struct.pack_into(">I", buf, 0x10, entry_count)
    struct.pack_into(">H", buf, 0x14, 0)  # sc_entry_count (kein Split-Set)
    struct.pack_into(">I", buf, 0x18, entry_table_offset)
    struct.pack_into(">Q", buf, 0x20, body_offset)
    struct.pack_into(">Q", buf, 0x28, body_size)
    buf[0x40:0x40 + CONTENT_ID_SIZE] = content_id_bytes
    struct.pack_into(">I", buf, 0x70, drm_type)
    struct.pack_into(">I", buf, 0x74, content_type)
    struct.pack_into(">I", buf, 0x78, content_flags)

    for i, entry in enumerate(entries):
        rec_off = entry_table_offset + i * ENTRY_META_SIZE
        struct.pack_into(
            ">IIIIII", buf, rec_off,
            entry.raw_id, entry.name_table_offset, 0, 0, entry.data_offset, entry.data_size,
        )
        buf[rec_off + 0x18:rec_off + ENTRY_META_SIZE] = b"\x00" * 8

    for entry in entries:
        buf[entry.data_offset:entry.data_offset + entry.data_size] = entry.payload

    return bytes(buf)


def wrap_in_fih(
    cnt_size: int,
    pfs_image_size: int,
    content_version: int = 1,
) -> tuple[bytes, int, int]:
    """Baut den FIH-Kopfbereich (0x10000 Bytes) fuer ein Debug-Vollabbild.

    Returns:
        Tupel aus (header_region_bytes, pfs_image_offset, embedded_cnt_offset).
    """
    pfs_image_offset = FIH_HEADER_REGION_SIZE
    aligned_pfs_size = _align_up(pfs_image_size, _PFS_BLOCK_ALIGN)
    embedded_cnt_offset = pfs_image_offset + aligned_pfs_size
    block_count = aligned_pfs_size // _PFS_BLOCK_ALIGN

    header = bytearray(FIH_HEADER_REGION_SIZE)
    header[0:4] = FIH_MAGIC
    header[FIH_SIGNED_BYTE_OFFSET] = 0x00  # Debug-Paket, siehe Modul-Docstring
    struct.pack_into("<H", header, FIH_FORMAT_VERSION_OFFSET, FIH_REQUIRED_FORMAT_VERSION)
    struct.pack_into("<Q", header, FIH_PFS_IMAGE_OFFSET_OFFSET, pfs_image_offset)
    struct.pack_into("<Q", header, FIH_PFS_IMAGE_SIZE_OFFSET, pfs_image_size)
    struct.pack_into("<Q", header, FIH_DATA_REGION_BLOCK_COUNT_OFFSET, block_count)
    struct.pack_into("<Q", header, FIH_EMBEDDED_CNT_OFFSET_OFFSET, embedded_cnt_offset)
    struct.pack_into("<I", header, FIH_INNER_IMAGE_BLOCK_COUNT_OFFSET, block_count)
    struct.pack_into("<I", header, FIH_META_BLOCK_COUNT_OFFSET, 0)
    struct.pack_into("<I", header, FIH_META_BLOCK_COUNT_MIRROR_OFFSET, 0)
    struct.pack_into("<I", header, FIH_CONTENT_VERSION_OFFSET, content_version)
    struct.pack_into("<Q", header, FIH_INNER_IMAGE_SIZE_OFFSET, pfs_image_size)
    struct.pack_into("<Q", header, FIH_INNER_IMAGE_LOGICAL_SIZE_OFFSET, pfs_image_size)
    struct.pack_into("<I", header, FIH_OUTER_FILE_COUNT_OFFSET, 1)
    struct.pack_into("<I", header, FIH_FLAT_PATH_TABLE_BLOCK_COUNT_OFFSET, 0)
    return bytes(header), pfs_image_offset, embedded_cnt_offset


def build_debug_pkg(
    output_path: str,
    content_id: str,
    param_json: dict,
    pfs_image_path: str | None = None,
    extra_entries: list[tuple[int, str, bytes]] | None = None,
    ekpfs: bytes | None = None,
    drm_type: int = 0,
) -> dict:
    """Baut ein strukturell gueltiges Debug-.pkg (CNT-only oder FIH-Vollabbild).

    Ist ``pfs_image_path`` angegeben, wird ein FIH-Vollabbild geschrieben (Header +
    gestreamtes PFS-Image + eingebetteter CNT-Container). Ohne PFS-Image wird nur
    der reine CNT-Metadatencontainer geschrieben (Typ "meta" fuer pkg_reader).

    Returns:
        Zusammenfassung als dict (path, type, size, entry_count, content_id, ...).
    """
    effective_ekpfs = ekpfs if (ekpfs is not None or pfs_image_path is None) else ZERO_EKPFS
    cnt_bytes = build_cnt_container(
        content_id=content_id,
        param_json=param_json,
        extra_entries=extra_entries,
        ekpfs=effective_ekpfs if pfs_image_path is not None else None,
        drm_type=drm_type,
    )

    if pfs_image_path is None:
        with open(output_path, "wb") as f:
            f.write(cnt_bytes)
        return {
            "path": output_path,
            "type": "meta",
            "size": len(cnt_bytes),
            "content_id": content_id,
        }

    pfs_image_size = os.path.getsize(pfs_image_path)
    fih_header, pfs_image_offset, embedded_cnt_offset = wrap_in_fih(len(cnt_bytes), pfs_image_size)
    aligned_pfs_size = embedded_cnt_offset - pfs_image_offset

    with open(output_path, "wb") as out:
        out.write(fih_header)
        with open(pfs_image_path, "rb") as pf:
            shutil.copyfileobj(pf, out, length=1024 * 1024)
        pad = aligned_pfs_size - pfs_image_size
        if pad:
            out.write(b"\x00" * pad)
        out.write(cnt_bytes)

    return {
        "path": output_path,
        "type": "full_debug",
        "size": embedded_cnt_offset + len(cnt_bytes),
        "pfs_image_size": pfs_image_size,
        "embedded_cnt_offset": embedded_cnt_offset,
        "content_id": content_id,
    }
