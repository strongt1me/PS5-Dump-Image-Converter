"""
PS5 Dump Validator – Hashing
SHA-256 Berechnung mit Chunked-Reading und optionalem Progress-Callback.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Callable

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB


def sha256_file(
    path: str | Path,
    progress_cb: Callable[[int, int], None] | None = None,
) -> str:
    """
    SHA-256 Hash einer Datei berechnen (chunkweise, kein RAM-Load).

    :param path: Dateipfad
    :param progress_cb: optionaler Callback(bytes_done, total_bytes)
    :return: Hex-String des SHA-256 Hashes
    :raises OSError: bei Lesefehler
    """
    path = Path(path)
    total = path.stat().st_size
    h = hashlib.sha256()
    done = 0

    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress_cb:
                try:
                    progress_cb(done, total)
                except Exception:
                    pass

    return h.hexdigest()


def sha256_stream(
    fh,
    total_size: int = 0,
    progress_cb: Callable[[int, int], None] | None = None,
) -> tuple[str, list[str]]:
    """
    SHA-256 eines bereits geöffneten Datei-Handles berechnen.
    Gibt (hash_hex, errors[]) zurück.
    """
    h = hashlib.sha256()
    done = 0
    errors: list[str] = []

    try:
        while True:
            chunk = fh.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
            done += len(chunk)
            if progress_cb and total_size:
                try:
                    progress_cb(done, total_size)
                except Exception:
                    pass
    except OSError as exc:
        errors.append(f"Lesefehler bei Byte {done}: {exc}")

    return h.hexdigest(), errors
