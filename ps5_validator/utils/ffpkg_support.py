"""Gemeinsame Hilfen für echte UFS2-basierte ``.ffpkg``-Images.

Die Funktionen in diesem Modul führen keine externen Programme aus. Sie
normalisieren ausschließlich nachprüfbare UFS2Tool-Argumente, prüfen
Eingabepfade und liefern reproduzierbare Read-only-Validierungskommandos.

Der FFPKG-Builder verwendet zuerst zwei ``newfs -D``-Profile, die aus den
untersuchten FFPKG-Referenzwerkzeugen abgeleitet sind. Jede erzeugte Datei wird
außerhalb dieses Moduls durch ``info`` und ``fsck_ufs -fn`` geprüft. Der
explizit dimensionierte ``makefs``-Pfad bleibt als letzter Fallback erhalten,
da er für andere Quellstrukturen ebenfalls gültige Images erzeugen kann.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from typing import Iterable


MiB = 1024 * 1024
GiB = 1024 * MiB

# Der makefs-Fallback erhält eine feste Zielgröße. Der Wert reserviert Platz für
# Superblöcke, Cylinder Groups, Verzeichnisse und eine Wachstumsreserve.
_MIN_IMAGE_HEADROOM_BYTES = 128 * MiB
_IMAGE_HEADROOM_RATIO = 0.20
_PER_FILE_METADATA_RESERVE_BYTES = 16 * 1024


@dataclass(frozen=True)
class FfpkgBuildProfile:
    """Konservative, UFS2Tool-kompatible Parameter für ``makefs``."""

    block_size: int = 65536
    fragment_size: int = 65536
    min_free_percent: int = 0
    sector_size: int = 512
    inode_density: int = 65536

    def normalized(self) -> "FfpkgBuildProfile":
        """Gibt ein gültiges Profil zurück oder löst bei falschen Werten aus."""
        block_size = int(self.block_size)
        fragment_size = int(self.fragment_size)
        min_free_percent = int(self.min_free_percent)
        sector_size = int(self.sector_size)
        inode_density = int(self.inode_density)

        if block_size < 4096 or block_size > 65536 or block_size & (block_size - 1):
            raise ValueError("UFS2-Blockgröße muss eine Zweierpotenz von 4 KiB bis 64 KiB sein.")
        if fragment_size < 512 or fragment_size > block_size or fragment_size & (fragment_size - 1):
            raise ValueError("UFS2-Fragmentgröße muss eine Zweierpotenz zwischen 512 B und Blockgröße sein.")
        if block_size // fragment_size not in (1, 2, 4, 8):
            raise ValueError("UFS2-Block-/Fragmentverhältnis muss 1, 2, 4 oder 8 sein.")
        if not 0 <= min_free_percent <= 99:
            raise ValueError("UFS2-Minimalfreiraum muss zwischen 0 und 99 Prozent liegen.")
        if sector_size not in (512, 1024, 2048, 4096):
            raise ValueError("UFS2-Sektorgröße muss 512, 1024, 2048 oder 4096 Byte sein.")
        if inode_density < 4096 or inode_density > 16 * MiB:
            raise ValueError("UFS2-Inode-Dichte liegt außerhalb des sicheren Bereichs.")

        return FfpkgBuildProfile(
            block_size=block_size,
            fragment_size=fragment_size,
            min_free_percent=min_free_percent,
            sector_size=sector_size,
            inode_density=inode_density,
        )


@dataclass(frozen=True)
class FfpkgNewfsProfile:
    """Nachvollziehbares UFS2Tool-``newfs -D``-Profil für FFPKG-Kandidaten."""

    identifier: str
    block_size: int
    fragment_size: int
    sector_size: int = 512
    min_free_percent: int | None = None
    inode_density: int | None = None

    def normalized(self) -> "FfpkgNewfsProfile":
        """Validiert nur Optionen, die tatsächlich an ``newfs`` übergeben werden."""
        identifier = str(self.identifier).strip()
        block_size = int(self.block_size)
        fragment_size = int(self.fragment_size)
        sector_size = int(self.sector_size)
        min_free_percent = (
            None if self.min_free_percent is None else int(self.min_free_percent)
        )
        inode_density = None if self.inode_density is None else int(self.inode_density)

        if not identifier:
            raise ValueError("FFPKG-newfs-Profil benötigt eine Kennung.")
        if block_size < 4096 or block_size > 65536 or block_size & (block_size - 1):
            raise ValueError("UFS2-newfs-Blockgröße muss eine Zweierpotenz von 4 KiB bis 64 KiB sein.")
        if fragment_size < 512 or fragment_size > block_size or fragment_size & (fragment_size - 1):
            raise ValueError("UFS2-newfs-Fragmentgröße muss eine Zweierpotenz zwischen 512 B und Blockgröße sein.")
        if block_size // fragment_size not in (1, 2, 4, 8):
            raise ValueError("UFS2-newfs-Block-/Fragmentverhältnis muss 1, 2, 4 oder 8 sein.")
        if sector_size not in (512, 1024, 2048, 4096):
            raise ValueError("UFS2-newfs-Sektorgröße muss 512, 1024, 2048 oder 4096 Byte sein.")
        if min_free_percent is not None and not 0 <= min_free_percent <= 99:
            raise ValueError("UFS2-newfs-Minimalfreiraum muss zwischen 0 und 99 Prozent liegen.")
        if inode_density is not None and not 4096 <= inode_density <= 16 * MiB:
            raise ValueError("UFS2-newfs-Inode-Dichte liegt außerhalb des sicheren Bereichs.")

        return FfpkgNewfsProfile(
            identifier=identifier,
            block_size=block_size,
            fragment_size=fragment_size,
            sector_size=sector_size,
            min_free_percent=min_free_percent,
            inode_density=inode_density,
        )


def default_build_profile() -> FfpkgBuildProfile:
    """Liefert das konservative UFS2-FFPKG-Profil für den ``makefs``-Fallback."""
    return FfpkgBuildProfile().normalized()


def primary_newfs_profile() -> FfpkgNewfsProfile:
    """Liefert das 64-KiB-``newfs -D``-Profil des primären Referenzablaufs."""
    return FfpkgNewfsProfile(
        identifier="newfs-64k-reference",
        block_size=65536,
        fragment_size=65536,
        sector_size=512,
        min_free_percent=0,
        inode_density=262144,
    ).normalized()


def compatibility_newfs_profile() -> FfpkgNewfsProfile:
    """Liefert das 32-KiB/4-KiB-``newfs -D``-Kompatibilitätsprofil.

    Freiraum- und Inode-Dichteoptionen bleiben absichtlich ``None``. Damit
    übernimmt UFS2Tool die Standardwerte, genau wie der dokumentierte schlanke
    Referenzwrapper, statt ungetestete eigene Annahmen zu erzwingen.
    """
    return FfpkgNewfsProfile(
        identifier="newfs-32k-4k-compatibility",
        block_size=32768,
        fragment_size=4096,
        sector_size=512,
        min_free_percent=None,
        inode_density=None,
    ).normalized()


def validate_source_folder(source_dir: str | os.PathLike[str]) -> tuple[int, int]:
    """Prüft einen Ordner auf eine sichere FFPKG-Quelle.

    Rückgabe ist ``(Dateianzahl, Gesamtbytes)``. Symbolische Links werden
    abgelehnt, damit UFS2Tool nur klar nachvollziehbare lokale Daten packt.
    """
    root = Path(source_dir)
    if not root.is_dir():
        raise ValueError(f"FFPKG-Quellordner nicht gefunden: {root}")

    file_count = 0
    total_bytes = 0
    for current, dirnames, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        for dirname in list(dirnames):
            path = current_path / dirname
            if path.is_symlink():
                raise ValueError(f"Symbolischer Ordner-Link ist nicht zulässig: {path}")
        for filename in filenames:
            path = current_path / filename
            if path.is_symlink():
                raise ValueError(f"Symbolischer Datei-Link ist nicht zulässig: {path}")
            try:
                stat = path.stat()
            except OSError as exc:
                raise ValueError(f"Quelldatei nicht lesbar: {path}: {exc}") from exc
            if not path.is_file():
                raise ValueError(f"Keine reguläre Quelldatei: {path}")
            file_count += 1
            total_bytes += int(stat.st_size)

    if file_count == 0:
        raise ValueError("Der FFPKG-Quellordner enthält keine Dateien.")
    return file_count, total_bytes


def normalize_output_path(output_path: str | os.PathLike[str]) -> Path:
    """Normalisiert einen FFPKG-Zielpfad und erzwingt die Endung ``.ffpkg``."""
    output = Path(output_path)
    raw_name = output.name
    if not raw_name or raw_name.lower() == ".ffpkg":
        raise ValueError("Ein gültiger FFPKG-Dateiname ist erforderlich.")
    if output.suffix.lower() != ".ffpkg":
        output = output.with_suffix(".ffpkg")
    return output


def _ffpkg_output_text(output_path: str | os.PathLike[str]) -> str:
    """Erzwingt die ``.ffpkg``-Endung, ohne die Pfadtrennzeichen des Aufrufers zu verändern.

    ``normalize_output_path`` arbeitet intern mit ``pathlib.Path``. Dessen String-Form
    ersetzt unter Windows jedes Forward-Slash durch ein Backslash, selbst wenn der
    Aufrufer bewusst Forward-Slashes übergeben hat, wie es Quell- und Executable-Pfad
    in diesem Modul unverändert tun. Diese Hilfsfunktion validiert über
    ``normalize_output_path``, ersetzt aber nur die Endung im ursprünglichen Text, damit
    alle Pfadargumente eines Kommandos denselben Trennzeichenstil behalten.
    """
    raw_text = os.fspath(output_path)
    validated_suffix = normalize_output_path(output_path).suffix
    original_suffix = Path(raw_text).suffix
    base_text = raw_text[: len(raw_text) - len(original_suffix)] if original_suffix else raw_text
    return f"{base_text}{validated_suffix}"


def build_newfs_directory_command(
    executable: str | os.PathLike[str],
    source_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    profile: FfpkgNewfsProfile | None = None,
) -> list[str]:
    """Erzeugt einen UFS2Tool-``newfs -D``-Aufruf für einen FFPKG-Kandidaten.

    ``newfs`` bestimmt die endgültige Imagegröße anhand des realen
    Verzeichnisbaums. Es wird kein Größenwert geschätzt oder nachträglich an
    das Image angehängt. Dadurch sind die angelegten Cylinder Groups und das
    Quellverzeichnis ein einzelner atomarer UFS2Tool-Erstellungsvorgang.
    """
    normalized = (profile or primary_newfs_profile()).normalized()
    executable_text = os.fspath(executable)
    source_text = os.fspath(source_dir)
    output_text = _ffpkg_output_text(output_path)
    if not executable_text:
        raise ValueError("UFS2Tool-Pfad fehlt.")
    if not source_text:
        raise ValueError("FFPKG-Quellordner fehlt.")

    command = [
        executable_text,
        "newfs",
        "-O",
        "2",
        "-b",
        str(normalized.block_size),
        "-f",
        str(normalized.fragment_size),
        "-S",
        str(normalized.sector_size),
    ]
    if normalized.min_free_percent is not None:
        command.extend(("-m", str(normalized.min_free_percent)))
    if normalized.inode_density is not None:
        command.extend(("-i", str(normalized.inode_density)))
    command.extend(("-D", source_text, output_text))
    return command


def calculate_makefs_image_size(
    source_size_bytes: int,
    file_count: int = 1,
    profile: FfpkgBuildProfile | None = None,
) -> int:
    """Berechnet eine blockausgerichtete, explizite UFS2-Imagegröße.

    Neben dem Quellinhalt werden mindestens 128 MiB beziehungsweise 20 Prozent
    Reserve für UFS2-Metadaten, Cylinder Groups und Verzeichnisse eingeplant.
    Zusätzlich wird die maximal mögliche Aufrundung jeder Datei auf ein volles
    UFS-Fragment sowie eine Metadatenreserve von 16 KiB je Datei berücksichtigt.
    """
    normalized = (profile or default_build_profile()).normalized()
    source_size = int(source_size_bytes)
    files = int(file_count)
    if source_size <= 0:
        raise ValueError("Die FFPKG-Quellgröße muss größer als 0 Byte sein.")
    if files <= 0:
        raise ValueError("Für FFPKG makefs ist mindestens eine Quelldatei erforderlich.")

    fragment_rounding_reserve = files * (normalized.fragment_size - 1)
    allocated_upper_bound = source_size + fragment_rounding_reserve
    headroom = max(
        _MIN_IMAGE_HEADROOM_BYTES,
        math.ceil(allocated_upper_bound * _IMAGE_HEADROOM_RATIO),
    )
    metadata_reserve = files * _PER_FILE_METADATA_RESERVE_BYTES
    raw_size = allocated_upper_bound + headroom + metadata_reserve
    block_size = normalized.block_size
    return ((raw_size + block_size - 1) // block_size) * block_size


def calculate_makefs_inode_density(
    image_size_bytes: int,
    file_count: int,
    profile: FfpkgBuildProfile | None = None,
) -> int:
    """Leitet eine sichere Byte-pro-Inode-Dichte für die tatsächliche Baumgröße ab."""
    normalized = (profile or default_build_profile()).normalized()
    image_size = int(image_size_bytes)
    files = int(file_count)
    if image_size <= 0:
        raise ValueError("Die FFPKG-Imagegröße muss größer als 0 Byte sein.")
    if files <= 0:
        raise ValueError("Für FFPKG makefs ist mindestens eine Quelldatei erforderlich.")

    required_inodes = max(4096, files * 2 + 2048)
    max_density_for_required_inodes = image_size // required_inodes
    if max_density_for_required_inodes < 4096:
        raise ValueError(
            "Die FFPKG-Quelle enthält zu viele Dateieinträge für die berechnete Imagegröße. "
            "Bitte die Quelle aufteilen oder weniger Dateien pro FFPKG verwenden."
        )
    return max(4096, min(normalized.inode_density, int(max_density_for_required_inodes)))


def build_makefs_command(
    executable: str | os.PathLike[str],
    source_dir: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    *,
    source_size_bytes: int,
    file_count: int,
    profile: FfpkgBuildProfile | None = None,
) -> list[str]:
    """Erzeugt den explizit dimensionierten UFS2Tool-``makefs``-Fallback-Aufruf."""
    normalized = (profile or default_build_profile()).normalized()
    executable_text = os.fspath(executable)
    source_text = os.fspath(source_dir)
    output_text = _ffpkg_output_text(output_path)
    if not executable_text:
        raise ValueError("UFS2Tool-Pfad fehlt.")
    if not source_text:
        raise ValueError("FFPKG-Quellordner fehlt.")

    image_size = calculate_makefs_image_size(source_size_bytes, file_count, normalized)
    inode_density = calculate_makefs_inode_density(image_size, file_count, normalized)
    fs_options = ",".join(
        (
            "version=2",
            f"bsize={normalized.block_size}",
            f"fsize={normalized.fragment_size}",
            f"density={inode_density}",
            f"minfree={normalized.min_free_percent}",
            "optimization=time",
        )
    )

    return [
        executable_text,
        "makefs",
        "-t",
        "ffs",
        "-S",
        str(normalized.sector_size),
        "-s",
        str(image_size),
        "-o",
        fs_options,
        output_text,
        source_text,
    ]


def build_readonly_validation_commands(
    executable: str | os.PathLike[str], image_path: str | os.PathLike[str]
) -> tuple[list[str], list[str]]:
    """Liefert die nicht schreibenden UFS2Tool-Prüfkommandos in Reihenfolge."""
    executable_text = os.fspath(executable)
    image_text = os.fspath(image_path)
    if not executable_text:
        raise ValueError("UFS2Tool-Pfad fehlt.")
    if not image_text:
        raise ValueError("FFPKG-Dateipfad fehlt.")
    return (
        [executable_text, "info", image_text],
        [executable_text, "fsck_ufs", "-fn", image_text],
    )


def format_bytes(byte_count: int) -> str:
    """Formatiert Größen für Logs ohne Abhängigkeit vom GUI-Modul."""
    value = max(0, int(byte_count))
    units: Iterable[str] = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    unit = "B"
    for unit in units:
        if amount < 1024.0 or unit == "TiB":
            break
        amount /= 1024.0
    return f"{amount:.2f} {unit}" if unit != "B" else f"{value} B"
