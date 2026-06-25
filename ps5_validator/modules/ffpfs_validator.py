"""
PS5 Dump Validator – .ffpfs / .ffpfsc Datei-Prüfung
Streaming-Read, SHA-256, Magic-Header-Check.

PFS-Image-Header-Struktur (erzeugt von mkpfs pack file):
  Offset 0x00  int64  version  = 2          (PFS-Version)
  Offset 0x08  int64  magic    = 0x1332A0B  (PFS_MAGIC)

PFSC-Block-Header (innerhalb des PFS-Images):
  Offset 0x00  int32  magic    = 0x43534650 (PFSC_MAGIC = "PFSC")
  Offset 0x04  int32  unk4     = 0
  Offset 0x08  int32  unk8     = 6
  Offset 0x0C  int32  block_sz = 65536
"""
from __future__ import annotations

import os
import struct
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import BaseValidator, ValidationResult
from ps5_validator.utils.hashing import sha256_stream
from ps5_validator.utils.file_io import fmt_bytes
from ps5_validator.utils.logger import get_logger

# ── PFS-Image-Header (äußerer Container, erzeugt von mkpfs pack file) ──────
# Header-Struktur: version (int64) @ 0x00, magic (int64) @ 0x08
PFS_MAGIC_VALUE  = 0x1332A0B   # mkpfs consts.PFS_MAGIC
PFS_VERSION_FFPFSC = 2          # Standard-Version für .ffpfsc

# ── PFSC-Block-Header (innerhalb des PFS-Images) ────────────────────────────
PFSC_MAGIC_VALUE = 0x43534650  # "PFSC" in little-endian

# Bekannte Magic-Header für PS5 PFS-Container
# Schlüssel = (version_int64, magic_int64) oder (magic_int32,)
KNOWN_PFS_VERSIONS = {
    2: "PFS-Image v2 (ffpfsc, mkpfs pack file)",
    1: "PFS-Image v1 (ffpfs, unkomprimiert)",
}


class FfpfsValidator(BaseValidator):
    """Validiert eine .ffpfs oder .ffpfsc Datei."""

    def __init__(
        self,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose)
        self._log = get_logger()

    def validate(self, path: str) -> ValidationResult:
        result = ValidationResult(mode="ffpfs")
        fpath  = Path(path)

        # ── Existenz prüfen ──────────────────────────────────────────────────
        if not fpath.exists():
            result.set_missing(f"Datei nicht gefunden: {path}")
            return result
        if not fpath.is_file():
            result.set_failed(f"Keine regulaere Datei: {path}")
            return result

        try:
            file_size = fpath.stat().st_size
        except OSError as exc:
            result.set_failed(f"Dateigroesse nicht lesbar: {exc}")
            return result

        if file_size == 0:
            result.set_corrupted("Datei ist leer (0 Bytes).")
            return result

        self._log.info(f"Starte FFPFS-Validierung: {fpath.name} ({fmt_bytes(file_size)})")
        result.summary["file_size"] = fmt_bytes(file_size)
        result.summary["files_scanned"] = 1

        # ── Magic-Header prüfen (erste 16 Bytes) ────────────────────────────
        # PFS-Image-Header: version (int64) @ 0x00, magic (int64) @ 0x08
        magic_info = "unbekannt"
        try:
            with open(fpath, "rb") as fh:
                header = fh.read(16)

            if len(header) >= 16:
                # PFS-Image-Header: version @ 0x00 (int64), magic @ 0x08 (int64)
                version = struct.unpack_from("<q", header, 0x00)[0]
                magic   = struct.unpack_from("<q", header, 0x08)[0]

                if magic == PFS_MAGIC_VALUE:
                    # Korrekter PFS-Image-Container (mkpfs pack file)
                    ver_name = KNOWN_PFS_VERSIONS.get(version, f"v{version}")
                    magic_info = f"PFS-Image ({ver_name})"
                    self._log.info(
                        f"PFS-Header erkannt: version={version}, "
                        f"magic=0x{magic:016X} ({magic_info})"
                    )
                else:
                    # Kein PFS-Image – prüfe ob es ein roher PFSC-Block ist
                    if len(header) >= 4:
                        pfsc_magic = struct.unpack_from("<I", header, 0x00)[0]
                        if pfsc_magic == PFSC_MAGIC_VALUE:
                            magic_info = "PFSC-Block (raw, ohne PFS-Container)"
                            self._log.info(f"PFSC-Magic erkannt (raw): 0x{pfsc_magic:08X}")
                        else:
                            magic_info = f"unbekannt (version=0x{version:016X}, magic=0x{magic:016X})"
                            result.add_error(
                                f"Unbekannter PFS-Header: version=0x{version:016X}, "
                                f"magic=0x{magic:016X}"
                            )
            elif len(header) >= 4:
                # Datei zu kurz für vollständigen Header – nur int32 lesen
                magic32 = struct.unpack_from("<I", header, 0x00)[0]
                if magic32 == PFSC_MAGIC_VALUE:
                    magic_info = "PFSC-Block (raw)"
                else:
                    magic_info = f"unbekannt (0x{magic32:08X})"
                    result.add_error(f"Unbekannter Magic-Header: 0x{magic32:08X}")

        except OSError as exc:
            result.add_error(f"Header-Lesefehler: {exc}")

        result.summary["magic"] = magic_info

        # ── Vollständiger Streaming-Read + SHA-256 ───────────────────────────
        read_errors: list[str] = []
        file_hash = ""
        try:
            with open(fpath, "rb") as fh:
                file_hash, read_errors = sha256_stream(
                    fh,
                    total_size=file_size,
                    progress_cb=lambda d, t: self._report_progress(d, t, fpath.name),
                )
        except OSError as exc:
            result.set_corrupted(f"Datei nicht lesbar: {exc}")
            return result

        result.hashes[fpath.name] = file_hash
        result.summary["read_errors"] = read_errors

        if read_errors:
            for e in read_errors:
                result.add_error(e)
            result.set_corrupted(f"{len(read_errors)} Lesefehler - Datei beschaedigt.")
        elif not result.errors:
            # Nur OK wenn kein Header-Fehler und keine Lesefehler
            result.status = "OK"

        self._log.info(
            f"FFPFS-Validierung abgeschlossen: {result.status} | "
            f"SHA-256: {file_hash[:16]}..."
        )
        return result
