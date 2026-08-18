"""
PS5 Dump Validator – File I/O Utilities
Hilfsfunktionen für Dateizugriff, Grössen-Formatierung und Cache.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


CACHE_FILENAME = ".ps5val_cache.json"


def get_all_files(root: str | Path) -> list[Path]:
    """Alle Dateien in einem Verzeichnis rekursiv auflisten."""
    root = Path(root)
    files: list[Path] = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            files.append(Path(dirpath) / fn)
    return sorted(files)


def fmt_bytes(n: int) -> str:
    """Bytes in lesbare Grösse umwandeln."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def load_cache(cache_path: str | Path) -> dict[str, Any]:
    """Hash-Cache aus JSON-Datei laden."""
    try:
        with open(cache_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cache(cache_path: str | Path, data: dict[str, Any]) -> None:
    """Hash-Cache in JSON-Datei speichern."""
    try:
        with open(cache_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def get_cache_path(root: str | Path) -> Path:
    """Cache-Pfad für ein Verzeichnis oder eine Datei bestimmen."""
    root = Path(root)
    if root.is_dir():
        return root / CACHE_FILENAME
    return root.parent / CACHE_FILENAME


def write_json_report(output_path: str | Path, data: dict[str, Any]) -> None:
    """JSON-Bericht in Datei schreiben."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
