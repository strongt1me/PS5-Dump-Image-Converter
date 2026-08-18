"""Reassembliert geteilte PS5-.pkg-Dateisaetze (Split-Packages) zu einer vollstaendigen Datei.

Manche Distributionswege liefern ein finalisiertes PS5-Paket nicht als einzelne .pkg-Datei,
sondern aufgeteilt in nummerierte Teile (<base>_0.pkg .. <base>_N.pkg) plus einen optionalen
Metadaten-Teil (<base>_sc.pkg). Dieses Modul erkennt solche Saetze in einem Ordner, prueft ihre
strukturelle Konsistenz gegen den FIH-Header des ersten Teils und fuegt sie durch reine
Byte-Konkatenation (aufsteigende Reihenfolge, Metadaten-Teil zuletzt) zu einer vollstaendigen
Datei zusammen. Es werden keine Paketinhalte entschluesselt, geprueft (signiert) oder veraendert.

WICHTIG: Das ist NICHT dasselbe wie das Zusammenfuehren von Basisspiel + Update + DLC in ein
gemeinsames Paket - auf der PS5 sind das grundsaetzlich separate, eigenstaendig installierbare
Pakete. "Merge" bezieht sich hier ausschliesslich auf das Wiederzusammensetzen EINES aus
Distributionsgruenden gesplitteten Pakets.

Byte-Layout und Validierungsregeln durch Gegenlesen des quelloffenen LibProsperoPKG-Mergers
(GPL-3.0-or-later, https://github.com/SvenGDK/LibProsperoPKG) ermittelt; eigenstaendige
Python-Neuentwicklung auf Basis der (nicht schutzfaehigen) Format-Fakten, kein Uebersetzen/
Kopieren des dortigen C#-Quellcodes.
"""
from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass, field
from typing import Callable

from ps5_validator.utils.pkg_reader import (
    CNT_MAGIC,
    FIH_EMBEDDED_CNT_OFFSET_OFFSET,
    FIH_FORMAT_VERSION_OFFSET,
    FIH_MAGIC,
    FIH_PFS_IMAGE_OFFSET_OFFSET,
    FIH_PFS_IMAGE_SIZE_OFFSET,
    FIH_REQUIRED_FORMAT_VERSION,
    FIH_SIGNED_BYTE_OFFSET,
)

META_TOKEN = "sc"
MERGED_SUFFIX = "-merged.pkg"
_HEAD_READ_SIZE = 0x60
_COPY_CHUNK_SIZE = 1024 * 1024

LogFn = Callable[[str], None]


class PkgMergeError(Exception):
    """Wird ausgeloest, wenn ein Split-Set die strukturelle Validierung nicht besteht."""


@dataclass
class SplitSet:
    base_name: str
    numbered: dict[int, str] = field(default_factory=dict)
    meta: str | None = None

    @property
    def ordered_numbered(self) -> list[str]:
        return [self.numbered[key] for key in sorted(self.numbered)]

    @property
    def has_root(self) -> bool:
        return 0 in self.numbered


@dataclass
class MergeValidation:
    is_valid: bool
    package_type: str  # "full_retail" | "full_debug"
    format_version: int
    pfs_image_offset: int
    pfs_image_size: int
    embedded_cnt_offset: int
    numbered_size: int
    meta_size: int
    errors: list[str]


@dataclass
class MergeResult:
    output_path: str
    base_name: str
    numbered_pieces: list[str]
    meta_piece: str | None
    total_size: int
    package_type: str
    sha256: str | None = None


def _try_parse_name(file_name: str) -> tuple[str, str] | None:
    """Zerlegt einen Dateinamen in Basisname (vor dem letzten '_') und Teil-Token.

    Das Token endet an der Dateiendung, nicht am ersten Punkt des Namens: Sonst
    fallen alle Basisnamen durch, die selbst einen Punkt enthalten - etwa die
    Versionsklammer ``Spiel (01.003.000)_0.pkg`` oder ``Game.v1.00_0.pkg``.
    Solche Saetze galten als "entspricht nicht dem Split-Namensschema" und
    wurden stillschweigend uebersprungen.
    """
    stem = os.path.splitext(file_name)[0]
    last_underscore = stem.rfind("_")
    if last_underscore < 0:
        return None
    token = stem[last_underscore + 1:]
    if not token:
        return None
    return stem[:last_underscore], token


def _try_parse_leading_int(token: str) -> int | None:
    i = 0
    while i < len(token) and token[i].isdigit():
        i += 1
    if i == 0:
        return None
    return int(token[:i])


def discover_split_sets(input_dir: str, log: LogFn | None = None) -> list[SplitSet]:
    """Gruppiert alle `.pkg`-Dateien in `input_dir` nach dem Split-Namensschema."""
    if not os.path.isdir(input_dir):
        raise NotADirectoryError(f"'{input_dir}' ist kein Ordner.")

    sets: dict[str, SplitSet] = {}
    for entry in sorted(os.listdir(input_dir)):
        full = os.path.join(input_dir, entry)
        if not os.path.isfile(full):
            continue
        if os.path.splitext(entry)[1].lower() != ".pkg":
            continue
        if MERGED_SUFFIX in entry:
            continue

        parsed = _try_parse_name(entry)
        if parsed is None:
            if log:
                log(f"[warn] '{entry}' entspricht nicht dem Split-Namensschema; übersprungen.")
            continue
        base_name, token = parsed

        split_set = sets.setdefault(base_name, SplitSet(base_name=base_name))
        if token.lower() == META_TOKEN:
            split_set.meta = full
            continue
        number = _try_parse_leading_int(token)
        if number is None:
            if log:
                log(f"[warn] '{entry}' hat ein unbekanntes Teil-Token; übersprungen.")
            continue
        split_set.numbered[number] = full

    return list(sets.values())


def _read_head(path: str, length: int) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read(length)
    except OSError:
        return b""


def validate_split_set(numbered_pieces: list[str], meta_piece: str | None) -> MergeValidation:
    """Prüft einen Split-Satz gegen das finalisierte FIH-Layout, ohne etwas zu schreiben."""
    if not numbered_pieces:
        raise ValueError("Mindestens das Wurzelteil (_0) wird benötigt.")

    errors: list[str] = []
    head = _read_head(numbered_pieces[0], _HEAD_READ_SIZE)

    package_type = "full_retail"
    format_version = 0
    pfs_offset = pfs_size = cnt_offset = 0

    if len(head) < _HEAD_READ_SIZE or head[:4] != FIH_MAGIC:
        errors.append("Wurzelteil beginnt nicht mit dem finalisierten FIH-Header.")
    else:
        signed_byte = head[FIH_SIGNED_BYTE_OFFSET]
        if signed_byte == 0x80:
            package_type = "full_retail"
        elif signed_byte == 0x00:
            package_type = "full_debug"
        else:
            errors.append(f"Unerwartetes signed byte 0x{signed_byte:02X} im FIH-Header.")

        format_version = struct.unpack_from("<H", head, FIH_FORMAT_VERSION_OFFSET)[0]
        if format_version != FIH_REQUIRED_FORMAT_VERSION:
            errors.append(f"Unerwartete Formatversion {format_version}.")

        pfs_offset = struct.unpack_from("<Q", head, FIH_PFS_IMAGE_OFFSET_OFFSET)[0]
        pfs_size = struct.unpack_from("<Q", head, FIH_PFS_IMAGE_SIZE_OFFSET)[0]
        cnt_offset = struct.unpack_from("<Q", head, FIH_EMBEDDED_CNT_OFFSET_OFFSET)[0]

        if cnt_offset != pfs_offset + pfs_size:
            errors.append(
                f"Eingebetteter Subcontainer-Offset {cnt_offset} entspricht nicht "
                f"Image-Offset+Größe {pfs_offset + pfs_size}."
            )

    numbered_size = 0
    for piece in numbered_pieces:
        if not os.path.isfile(piece):
            errors.append(f"Teil fehlt: '{piece}'.")
        else:
            numbered_size += os.path.getsize(piece)

    if not errors and cnt_offset != numbered_size:
        errors.append(
            f"Summe der nummerierten Teile ({numbered_size}) entspricht nicht dem "
            f"eingebetteten Subcontainer-Offset ({cnt_offset})."
        )

    meta_size = 0
    if meta_piece is not None:
        if not os.path.isfile(meta_piece):
            errors.append(f"Metadaten-Teil fehlt: '{meta_piece}'.")
        else:
            meta_size = os.path.getsize(meta_piece)
            meta_head = _read_head(meta_piece, 4)
            if len(meta_head) < 4 or meta_head[:4] != CNT_MAGIC:
                errors.append("Metadaten-Teil beginnt nicht mit dem Subcontainer-Header.")

    return MergeValidation(
        is_valid=not errors,
        package_type=package_type,
        format_version=format_version,
        pfs_image_offset=pfs_offset,
        pfs_image_size=pfs_size,
        embedded_cnt_offset=cnt_offset,
        numbered_size=numbered_size,
        meta_size=meta_size,
        errors=errors,
    )


def _base_name_of(path: str) -> str:
    file_name = os.path.basename(path)
    parsed = _try_parse_name(file_name)
    return parsed[0] if parsed is not None else os.path.splitext(file_name)[0]


def merge_split_set(
    numbered_pieces: list[str],
    meta_piece: str | None,
    output_path: str,
    compute_digest: bool = False,
    log: LogFn | None = None,
) -> MergeResult:
    """Fügt einen validierten Split-Satz per Byte-Konkatenation zu `output_path` zusammen.

    Raises:
        PkgMergeError: Der Satz besteht die strukturelle Validierung nicht.
    """
    if not numbered_pieces:
        raise ValueError("Mindestens das Wurzelteil (_0) wird benötigt.")

    validation = validate_split_set(numbered_pieces, meta_piece)
    if not validation.is_valid:
        raise PkgMergeError("Split-Set-Validierung fehlgeschlagen: " + "; ".join(validation.errors))

    ordered = list(numbered_pieces)
    if meta_piece is not None:
        ordered.append(meta_piece)

    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    sha = hashlib.sha256() if compute_digest else None
    total = 0
    tmp_path = output_path + ".tmp"
    try:
        with open(tmp_path, "wb") as out_f:
            for piece in ordered:
                if log:
                    log(f"[work] füge '{os.path.basename(piece)}' an...")
                with open(piece, "rb") as in_f:
                    while True:
                        chunk = in_f.read(_COPY_CHUNK_SIZE)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        if sha is not None:
                            sha.update(chunk)
                        total += len(chunk)
        os.replace(tmp_path, output_path)
    except Exception:
        if os.path.isfile(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        raise

    if log:
        log("[done] Zusammenfügen abgeschlossen.")

    return MergeResult(
        output_path=output_path,
        base_name=_base_name_of(numbered_pieces[0]),
        numbered_pieces=list(numbered_pieces),
        meta_piece=meta_piece,
        total_size=total,
        package_type=validation.package_type,
        sha256=sha.hexdigest() if sha is not None else None,
    )


def merge_directory(
    input_dir: str,
    output_dir: str | None = None,
    compute_digest: bool = False,
    log: LogFn | None = None,
) -> list[MergeResult]:
    """Findet und führt alle vollständigen Split-Sets in `input_dir` zusammen.

    Sets ohne Wurzelteil (`_0`) werden übersprungen und protokolliert.
    """
    output_dir = output_dir or input_dir
    os.makedirs(output_dir, exist_ok=True)

    results: list[MergeResult] = []
    for split_set in discover_split_sets(input_dir, log):
        if not split_set.has_root:
            if log:
                log(f"[warn] kein Wurzelteil (_0) für '{split_set.base_name}'; übersprungen.")
            continue
        output_path = os.path.join(output_dir, split_set.base_name + MERGED_SUFFIX)
        if log:
            piece_info = f"{len(split_set.numbered)} nummerierte(s) Teil(e)"
            piece_info += ", ohne Metadaten-Teil" if split_set.meta is None else " + Metadaten-Teil"
            log(f"[work] führe '{split_set.base_name}' zusammen ({piece_info})...")
        results.append(
            merge_split_set(split_set.ordered_numbered, split_set.meta, output_path, compute_digest, log)
        )

    if log:
        log("[done] Alle Split-Sets verarbeitet.")
    return results
