"""
PS5 Dump Validator – .extfat Datei-Prüfung
Streaming-Read, SHA-256, exFAT-Struktur-Parsing (Boot-Sektor).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import BaseValidator, ValidationResult
from ps5_validator.utils.hashing import sha256_stream
from ps5_validator.utils.file_io import fmt_bytes
from ps5_validator.utils.logger import get_logger

# exFAT Boot-Sektor Signatur (Offset 0x1FE): 0x55AA
EXFAT_BOOT_SIG = b"\x55\xAA"
# exFAT OEM-Name (Offset 0x03): "EXFAT   " (8 Bytes)
EXFAT_OEM_NAME = b"EXFAT   "
# Sektor-Grösse für exFAT-Parsing
SECTOR_SIZE    = 512


class ExtfatValidator(BaseValidator):
    """Validiert eine .extfat Container-Datei."""

    def __init__(
        self,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose)
        self._log = get_logger()

    def validate(self, path: str) -> ValidationResult:
        result = ValidationResult(mode="extfat")
        fpath  = Path(path)

        # ── Existenz prüfen ──────────────────────────────────────────────────
        if not fpath.exists():
            result.set_missing(f"Datei nicht gefunden: {path}")
            return result
        if not fpath.is_file():
            result.set_failed(f"Keine reguläre Datei: {path}")
            return result

        try:
            file_size = fpath.stat().st_size
        except OSError as exc:
            result.set_failed(f"Dateigrösse nicht lesbar: {exc}")
            return result

        if file_size == 0:
            result.set_corrupted("Datei ist leer (0 Bytes).")
            return result

        self._log.info(f"Starte exFAT-Validierung: {fpath.name} ({fmt_bytes(file_size)})")
        result.summary["file_size"]     = fmt_bytes(file_size)
        result.summary["files_scanned"] = 1

        # ── exFAT Boot-Sektor parsen ─────────────────────────────────────────
        parse_ok     = False
        cluster_count = 0
        volume_label  = ""
        try:
            with open(fpath, "rb") as fh:
                boot = fh.read(512)

            if len(boot) >= 512:
                # OEM-Name prüfen (Offset 3, 8 Bytes)
                oem = boot[3:11]
                if oem == EXFAT_OEM_NAME:
                    parse_ok = True
                    # Boot-Signatur prüfen (Offset 510)
                    if boot[510:512] != EXFAT_BOOT_SIG:
                        result.add_error("Boot-Signatur ungültig (0x55AA erwartet).")
                    # Cluster-Anzahl (Offset 0x4C, 4 Bytes LE)
                    if len(boot) >= 0x50:
                        cluster_count = struct.unpack_from("<I", boot, 0x4C)[0]
                    self._log.info(f"exFAT erkannt | Cluster: {cluster_count}")
                else:
                    oem_str = oem.decode("ascii", errors="replace").strip()
                    result.add_error(
                        f"Kein exFAT-OEM-Name gefunden (gefunden: '{oem_str}'). "
                        "Möglicherweise kein exFAT-Container oder beschädigt."
                    )
            else:
                result.add_error("Datei zu klein für Boot-Sektor (<512 Bytes).")

        except OSError as exc:
            result.add_error(f"Boot-Sektor Lesefehler: {exc}")

        result.summary["exfat_detected"]   = parse_ok
        result.summary["cluster_count"]    = cluster_count

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
            result.set_corrupted(f"{len(read_errors)} Lesefehler – Container beschädigt.")
        elif not parse_ok:
            result.status = "WARNING"
        else:
            result.status = "OK"

        self._log.info(
            f"exFAT-Validierung abgeschlossen: {result.status} | SHA-256: {file_hash[:16]}..."
        )
        return result
