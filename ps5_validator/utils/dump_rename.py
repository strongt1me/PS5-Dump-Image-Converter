"""Reine Namens-/Konfidenzlogik fuer die Dump-Rename-Funktion.

Trennt die (testbare) Namensbildung von der GUI- und Dateisystem-Interaktion:
Metadaten-Extraktion (param.json lesen, Cover laden) bleibt Sache der GUI-Klasse,
da sie bestehende, bereits genutzte Instanzmethoden wiederverwendet.
"""
from __future__ import annotations

_INVALID_CHARS = '<>:"/\\|?*'

GENERIC_FOLDER_NAMES: frozenset[str] = frozenset({
    "downloads", "download", "games", "game", "backup", "backups",
    "dump", "dumps", "new folder", "neuer ordner", "untitled",
})

CONFIDENCE_READY = "🟢 Ready"
CONFIDENCE_NEEDS_REVIEW = "🟡 Needs review"
CONFIDENCE_FAILED = "🔴 Failed"

PRESET_PPSA_ONLY = "PPSA only"
PRESET_PPSA_TITLE = "PPSA + Title"
PRESET_PPSA_TITLE_VERSION = "PPSA + Title + Version"


def sanitize_name(text: str) -> str:
    """Entfernt unter Windows ungültige Pfadzeichen und normalisiert Leerraum."""
    cleaned = "".join(ch for ch in text if ch not in _INVALID_CHARS).strip()
    return " ".join(cleaned.split())


def is_generic_folder_name(name: str) -> bool:
    """True, wenn ein Ordnername zu generisch ist, um als Titel übernommen zu werden."""
    return name.strip().lower() in GENERIC_FOLDER_NAMES


def compute_confidence(has_ppsa: bool, has_title: bool, has_version: bool) -> str:
    """Bestimmt den Konfidenz-Status analog zu ps5-exfat-builder (🟢/🟡/🔴)."""
    if not has_ppsa:
        return CONFIDENCE_FAILED
    if has_title and has_version:
        return CONFIDENCE_READY
    return CONFIDENCE_NEEDS_REVIEW


def build_presets(title_id: str, title: str, version: str, has_ppsa: bool, has_version: bool) -> dict[str, str]:
    """Baut die drei Namens-Presets. Ohne gültige PPSA-Title-ID bleiben alle Presets leer."""
    if not has_ppsa:
        return {PRESET_PPSA_ONLY: "", PRESET_PPSA_TITLE: "", PRESET_PPSA_TITLE_VERSION: ""}

    clean_title = sanitize_name(title) if title else ""
    ppsa_title = f"{title_id} {clean_title}".strip()
    if has_version:
        ppsa_title_version = f"{title_id} {clean_title} ({version})".strip()
    else:
        ppsa_title_version = ppsa_title

    return {
        PRESET_PPSA_ONLY: title_id,
        PRESET_PPSA_TITLE: ppsa_title,
        PRESET_PPSA_TITLE_VERSION: ppsa_title_version,
    }
