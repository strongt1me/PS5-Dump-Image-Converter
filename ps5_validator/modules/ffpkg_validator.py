"""Native UFS2 validation for PS5 ``.ffpkg`` filesystem images."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import BaseValidator, ValidationResult
from ps5_validator.utils.file_io import fmt_bytes
from ps5_validator.utils.hashing import sha256_stream
from ps5_validator.utils.logger import get_logger


class FfpkgValidator(BaseValidator):
    """Validate a UFS2 ``.ffpkg`` with UFS2Tool's read-only checks."""

    def __init__(
        self,
        ufs2tool_path: str,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose)
        self._ufs2tool_path = ufs2tool_path
        self._log = get_logger()

    def _run_tool(self, *args: str) -> tuple[int, str]:
        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            creationflags = subprocess.CREATE_NO_WINDOW

        completed = subprocess.run(
            [self._ufs2tool_path, *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            startupinfo=startupinfo,
            creationflags=creationflags,
            check=False,
        )
        return completed.returncode, completed.stdout.strip()

    def validate(self, path: str) -> ValidationResult:
        result = ValidationResult(mode="ffpkg")
        image = Path(path)
        tool = Path(self._ufs2tool_path)

        if not image.is_file():
            result.set_missing(f"Datei nicht gefunden: {path}")
            return result
        if not tool.is_file():
            result.set_failed(f"UFS2Tool nicht gefunden: {tool}")
            return result

        try:
            image_size = image.stat().st_size
        except OSError as exc:
            result.set_failed(f"Dateigroesse nicht lesbar: {exc}")
            return result
        if image_size == 0:
            result.set_corrupted("Datei ist leer (0 Bytes).")
            return result

        result.summary["file_size"] = fmt_bytes(image_size)
        result.summary["files_scanned"] = 1
        self._log.info("Starte native UFS2-Validierung: %s", image.name)

        try:
            info_rc, info_output = self._run_tool("info", str(image))
        except OSError as exc:
            result.set_failed(f"UFS2Tool konnte nicht gestartet werden: {exc}")
            return result
        result.summary["ufs2_info"] = info_output or "keine Ausgabe"
        if info_rc != 0:
            result.set_corrupted(
                f"UFS2-Superblock konnte nicht gelesen werden (info rc={info_rc}): "
                f"{info_output or 'keine Ausgabe'}"
            )
            return result

        if self._is_cancelled():
            result.set_failed("Validierung abgebrochen.")
            return result

        fsck_rc, fsck_output = self._run_tool("fsck_ufs", "-fn", str(image))
        result.summary["ufs2_fsck"] = fsck_output or "keine Ausgabe"
        result.summary["fsck_return_code"] = fsck_rc
        if fsck_rc != 0:
            result.set_corrupted(
                f"UFS2-Konsistenzpruefung fehlgeschlagen (fsck_ufs rc={fsck_rc}): "
                f"{fsck_output or 'keine Ausgabe'}"
            )
            return result

        try:
            with image.open("rb") as file_handle:
                file_hash, read_errors = sha256_stream(
                    file_handle,
                    total_size=image_size,
                    progress_cb=lambda done, total: self._report_progress(
                        done, total, image.name
                    ),
                )
        except OSError as exc:
            result.set_corrupted(f"Datei nicht vollstaendig lesbar: {exc}")
            return result

        result.hashes[image.name] = file_hash
        result.summary["read_errors"] = read_errors
        if read_errors:
            for error in read_errors:
                result.add_error(error)
            result.set_corrupted(f"{len(read_errors)} Lesefehler - Datei beschaedigt.")
        else:
            result.status = "OK"
        return result