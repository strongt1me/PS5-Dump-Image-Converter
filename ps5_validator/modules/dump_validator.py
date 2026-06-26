"""
PS5 Dump Validator – Game Dump Ordner Prüfung
Rekursiver Scan mit SHA-256, Multithreading und Resume-Cache.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import BaseValidator, ValidationResult
from ps5_validator.utils.hashing import sha256_file
from ps5_validator.utils.file_io import (
    get_all_files, fmt_bytes, load_cache, save_cache, get_cache_path
)
from ps5_validator.utils.logger import get_logger

# Bekannte PS5-Dump-Struktur (Pflichtordner)
REQUIRED_DIRS = ["sce_sys"]
# Optionale aber typische Ordner
OPTIONAL_DIRS = ["sce_module", "media", "data"]

# Kritische Dateien für einen PS5-Dump (müssen auf jeden Fall vorhanden sein)
CRITICAL_FILES = [
    "eboot.bin",                    # PS5 Game Executable
    "sce_sys/param.json",           # Game Metadaten (Title, Icon, etc.)
    "sce_sys/pfs-version.dat",      # PFS-Version-Marker
]

# Bekannte PS5-Marker-Dateien die legitim leer sind (0 Bytes)
# Format: Datei-Endung (case-insensitive)
_KNOWN_EMPTY_SUFFIXES = (
    ".complete",   # PPSA12345.complete – Installations-Abschluss-Flag
    ".lock",       # Installations-Sperrdatei
    ".done",       # Abschluss-Marker
    ".flag",       # Allgemeiner Status-Marker
    ".ready",      # Bereitschafts-Marker
)
# Exakte Dateinamen die leer sein dürfen (case-insensitive)
_KNOWN_EMPTY_NAMES = frozenset({
    "placeholder", "dummy", ".gitkeep", ".keep",
})


def _is_known_empty(rel_path: str) -> bool:
    """Gibt True zurück wenn die Datei bekanntermaßen leer sein darf."""
    name = rel_path.replace("\\", "/").split("/")[-1].lower()
    if name in _KNOWN_EMPTY_NAMES:
        return True
    for suffix in _KNOWN_EMPTY_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


class DumpValidator(BaseValidator):
    """Validiert einen PS5 Game Dump Ordner."""

    def __init__(
        self,
        threads: int = 4,
        resume: bool = False,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose)
        self._threads = max(1, threads)
        self._resume  = resume
        self._log     = get_logger()

    def validate(self, path: str) -> ValidationResult:
        result = ValidationResult(mode="dump")
        root   = Path(path)

        # ── Existenz prüfen ──────────────────────────────────────────────────
        if not root.exists():
            result.set_missing(f"Ordner nicht gefunden: {path}")
            return result
        if not root.is_dir():
            result.set_failed(f"Kein Verzeichnis: {path}")
            return result

        self._log.info(f"Starte Dump-Validierung: {root}")

        # ── Dateien sammeln ──────────────────────────────────────────────────
        try:
            all_files = get_all_files(root)
        except OSError as exc:
            result.set_failed(f"Verzeichnis nicht lesbar: {exc}")
            return result

        total_files = len(all_files)
        result.summary["files_scanned"] = total_files
        self._log.info(f"{total_files} Dateien gefunden")

        # ── Struktur-Check ───────────────────────────────────────────────────
        for req in REQUIRED_DIRS:
            if not (root / req).is_dir():
                result.add_error(f"Pflichtordner fehlt: {req}/")
                result.summary["missing"].append(str(root / req))

        # ── Kritische Dateien prüfen ────────────────────────────────────────
        # Diese müssen für einen gültigen PS5-Dump vorhanden sein
        missing_critical = []
        for crit_file in CRITICAL_FILES:
            crit_path = root / crit_file
            if not crit_path.exists():
                missing_critical.append(crit_file)
                result.add_error(f"Kritische Datei fehlt: {crit_file}")
                result.summary["missing"].append(str(crit_path))

        # Wenn kritische Dateien fehlen → Dump wahrscheinlich beschädigt oder unvollständig
        if missing_critical:
            self._log.warning(
                f"Kritische Dateien fehlen ({len(missing_critical)}): {', '.join(missing_critical)}"
            )
            result.summary["critical_missing"] = missing_critical

        # ── Leere Dateien prüfen ─────────────────────────────────────────────
        empty_files: list[str] = []
        known_empty: list[str] = []  # legitim leere Marker-Dateien (kein Fehler)
        for f in all_files:
            try:
                if f.stat().st_size == 0:
                    rel = str(f.relative_to(root))
                    if _is_known_empty(rel):
                        known_empty.append(rel)  # Marker-Datei – kein Fehler
                    else:
                        empty_files.append(rel)
                        result.add_error(f"Leere Datei: {rel}")
            except OSError as exc:
                result.add_error(f"Zugriffsfehler: {f.relative_to(root)}: {exc}")
                result.summary["corrupted"].append(str(f.relative_to(root)))

        result.summary["empty_files"] = empty_files
        if known_empty:
            result.summary["marker_files"] = known_empty  # Info, kein Fehler

        if self._is_cancelled():
            result.add_error("Abgebrochen durch Benutzer.")
            return result

        # ── Hash-Cache laden (Resume) ────────────────────────────────────────
        cache_path = get_cache_path(root)
        cache: dict = load_cache(cache_path) if self._resume else {}

        # ── Multithreaded SHA-256 ────────────────────────────────────────────
        total_bytes = sum(
            f.stat().st_size for f in all_files
            if f.stat().st_size > 0 and not self._is_cancelled()
        )
        done_bytes  = 0
        hashes: dict[str, str] = {}
        corrupted:  list[str]  = []

        def _hash_one(f: Path) -> tuple[str, str | None, str | None]:
            """(rel_path, hash_or_None, error_or_None)"""
            rel = str(f.relative_to(root))
            # Cache-Hit prüfen
            if self._resume and rel in cache:
                cached = cache[rel]
                mtime  = str(f.stat().st_mtime)
                if cached.get("mtime") == mtime:
                    return rel, cached["hash"], None
            try:
                h = sha256_file(f)
                return rel, h, None
            except OSError as exc:
                return rel, None, str(exc)

        with ThreadPoolExecutor(max_workers=self._threads) as pool:
            futures = {pool.submit(_hash_one, f): f for f in all_files if f.stat().st_size > 0}
            for fut in as_completed(futures):
                if self._is_cancelled():
                    pool.shutdown(wait=False, cancel_futures=True)
                    result.add_error("Abgebrochen durch Benutzer.")
                    break
                rel, h, err = fut.result()
                if err:
                    result.add_error(f"Hash-Fehler {rel}: {err}")
                    corrupted.append(rel)
                    result.summary["corrupted"].append(rel)
                else:
                    hashes[rel] = h
                    # Cache aktualisieren
                    f = futures[fut]
                    cache[rel] = {"hash": h, "mtime": str(f.stat().st_mtime)}

                done_bytes += futures[fut].stat().st_size
                self._report_progress(done_bytes, total_bytes, rel)

        # ── Cache speichern ──────────────────────────────────────────────────
        if self._resume and not self._is_cancelled():
            save_cache(cache_path, cache)

        result.hashes = hashes
        result.summary["corrupted"] = list(set(result.summary["corrupted"]))
        result.summary["total_size"] = fmt_bytes(total_bytes)

        # ── Gesamtstatus ─────────────────────────────────────────────────────
        if corrupted or result.summary["missing"]:
            result.status = "FAILED"
        elif empty_files or result.errors:
            result.status = "WARNING"
        else:
            result.status = "OK"

        self._log.info(f"Dump-Validierung abgeschlossen: {result.status}")
        return result
