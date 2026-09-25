"""
PS5 Dump Validator – Hashing
SHA-256 Berechnung mit Chunked-Reading und optionalem Progress-Callback.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

CHUNK_SIZE = 16 * 1024 * 1024  # 16 MB


def sha256_file(
    path: str | Path,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> str:
    """
    SHA-256 Hash einer Datei berechnen (chunkweise, kein RAM-Load).

    :param path: Dateipfad
    :param progress_cb: optionaler Callback(bytes_done, total_bytes)
    :param cancel_cb: wird vor jedem Block gefragt; liefert er True, endet
        das Lesen dort (der Hash ist dann unvollstaendig - der Aufrufer fragt
        den Abbruch selbst ab). Wie bei ``sha256_stream``: Bis zum 24.09.2026
        las die Dump-Pruefung nach "Abbrechen" jede angefangene Datei zu Ende
        - bei grossen Baendern Minuten (Durchsicht, U4-4).
    :return: Hex-String des SHA-256 Hashes
    :raises OSError: bei Lesefehler
    """
    path = Path(path)
    total = path.stat().st_size
    h = hashlib.sha256()
    done = 0

    with open(path, "rb") as fh:
        while True:
            if cancel_cb is not None and cancel_cb():
                break
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
    cancel_cb: Callable[[], bool] | None = None,
    lesefehler: str | None = None,
) -> tuple[str, list[str]]:
    """
    SHA-256 eines bereits geöffneten Datei-Handles berechnen.
    Gibt (hash_hex, errors[]) zurück.

    ``cancel_cb`` wird vor jedem Block gefragt; liefert er True, endet das
    Lesen dort (der Hash ist dann unvollstaendig - der Aufrufer fragt den
    Abbruch selbst ab). Bis v1.9.24 fehlte der Parameter: Aufgabe 8 las nach
    "Abbrechen" ein 100-GB-Abbild noch bis zum Ende.

    ``lesefehler`` ist die Vorlage fuer den Fehlereintrag (Platzhalter
    ``{byte}`` und ``{fehler}``); die Validatoren reichen die uebersetzte
    herein (Durchsicht, Runde 17). Ohne sie gilt die deutsche.
    """
    h = hashlib.sha256()
    done = 0
    errors: list[str] = []

    try:
        while True:
            if cancel_cb is not None and cancel_cb():
                break
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
        vorlage = lesefehler or "Lesefehler bei Byte {byte}: {fehler}"
        errors.append(vorlage.format(byte=done, fehler=exc))

    return h.hexdigest(), errors
