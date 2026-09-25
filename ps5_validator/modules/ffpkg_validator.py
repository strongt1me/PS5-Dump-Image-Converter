"""Native UFS2 validation for PS5 ``.ffpkg`` filesystem images."""
from __future__ import annotations

import errno
import os
import subprocess
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import (
    GEMEINSAME_MELDUNGEN, BaseValidator, ValidationResult,
)
from ps5_validator.utils.file_io import fmt_bytes
from ps5_validator.utils.ffpkg_support import build_readonly_validation_commands
from ps5_validator.utils.hashing import sha256_stream
from ps5_validator.utils.logger import get_logger


#: Windows meldet "Der angeforderte Vorgang erfordert erhoehte Rechte" als
#: WinError 740. Unter Linux und macOS kommt stattdessen EACCES/EPERM,
#: wenn das Werkzeug nicht ausfuehrbar ist oder das Abbild nicht
#: eingehaengt werden darf.
_RECHTE_WINERROR = 740
_RECHTE_ERRNO = (errno.EACCES, errno.EPERM)

#: Die Befunde als Vorlagen (Durchsicht, Runde 17) - deutsch als Vorgabe,
#: uebersetzt ueber ``texte=`` (Praefix "validator." in i18n). Der Satz zu
#: den Administratorrechten stand bis dahin in Umschrift ("geprueft").
MELDUNGEN: dict[str, str] = {
    **GEMEINSAME_MELDUNGEN,
    "ffpkg_ufs2tool_fehlt": "UFS2Tool nicht gefunden: {pfad}",
    "ffpkg_rechte": ("UFS2Tool braucht Administratorrechte - die Struktur "
                     "wurde nicht geprüft ({fehler})."),
    "ffpkg_start_fehler": "UFS2Tool konnte nicht gestartet werden: {fehler}",
    "ffpkg_keine_ausgabe": "keine Ausgabe",
    "ffpkg_superblock": "UFS2-Superblock konnte nicht gelesen werden (info rc={rc}): {ausgabe}",
    "ffpkg_abgebrochen": "Validierung abgebrochen.",
    "ffpkg_fsck": "UFS2-Konsistenzprüfung fehlgeschlagen (fsck_ufs rc={rc}): {ausgabe}",
    "ffpkg_unvollstaendig_lesbar": "Datei nicht vollständig lesbar: {fehler}",
}


def _braucht_rechte(exc: BaseException) -> bool:
    """Ob dieser Fehler nur fehlende Rechte meldet - und keinen Schaden.

    Der Unterschied entscheidet ueber das Urteil: Fehlende Rechte heissen
    "nicht geprueft", alles andere heisst "beanstandet". Bis v1.9.0 war
    beides dasselbe, und ein einwandfreies ``.ffpkg`` galt ohne
    Administratorrechte als fehlerhaft.
    """
    if getattr(exc, "winerror", None) == _RECHTE_WINERROR:
        return True
    if isinstance(exc, PermissionError):
        return True
    return getattr(exc, "errno", None) in _RECHTE_ERRNO


class FfpkgValidator(BaseValidator):
    """Validate a UFS2 ``.ffpkg`` with UFS2Tool's read-only checks."""

    MELDUNGEN = MELDUNGEN

    def __init__(
        self,
        ufs2tool_path: str,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
        texte: dict | None = None,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose, texte=texte)
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
            result.set_missing(self._text("datei_fehlt", pfad=path))
            return result
        if not tool.is_file():
            result.set_failed(self._text("ffpkg_ufs2tool_fehlt", pfad=tool))
            return result

        try:
            image_size = image.stat().st_size
        except OSError as exc:
            result.set_failed(self._text("groesse_unlesbar", fehler=exc))
            return result
        if image_size == 0:
            result.set_corrupted(self._text("datei_leer"))
            return result

        result.summary["file_size"] = fmt_bytes(image_size)
        result.summary["files_scanned"] = 1
        self._log.info("Starte native UFS2-Validierung: %s", image.name)

        try:
            info_cmd, fsck_cmd = build_readonly_validation_commands(tool, image)
            info_rc, info_output = self._run_tool(*info_cmd[1:])
        except (OSError, ValueError) as exc:
            if _braucht_rechte(exc):
                # Kein Urteil ueber das Abbild: Es wurde nicht angesehen.
                # Bis v1.9.0 stand hier FAILED, und ein einwandfreies .ffpkg
                # galt dadurch als beanstandet.
                result.set_skipped(self._text("ffpkg_rechte", fehler=exc))
                return result
            result.set_failed(self._text("ffpkg_start_fehler", fehler=exc))
            return result
        keine_ausgabe = self._text("ffpkg_keine_ausgabe")
        result.summary["ufs2_info"] = info_output or keine_ausgabe
        if info_rc != 0:
            result.set_corrupted(self._text("ffpkg_superblock", rc=info_rc,
                                            ausgabe=info_output or keine_ausgabe))
            return result

        if self._is_cancelled():
            result.set_failed(self._text("ffpkg_abgebrochen"))
            return result

        fsck_rc, fsck_output = self._run_tool(*fsck_cmd[1:])
        result.summary["ufs2_fsck"] = fsck_output or keine_ausgabe
        result.summary["fsck_return_code"] = fsck_rc
        if fsck_rc != 0:
            result.set_corrupted(self._text("ffpkg_fsck", rc=fsck_rc,
                                            ausgabe=fsck_output or keine_ausgabe))
            return result

        try:
            with image.open("rb") as file_handle:
                file_hash, read_errors = sha256_stream(
                    file_handle,
                    total_size=image_size,
                    progress_cb=lambda done, total: self._report_progress(
                        done, total, image.name
                    ),
                    cancel_cb=self._is_cancelled,
                    lesefehler=self._vorlage("lesefehler_byte"),
                )
        except OSError as exc:
            result.set_corrupted(self._text("ffpkg_unvollstaendig_lesbar", fehler=exc))
            return result

        if self._is_cancelled():
            # Kein Urteil ueber die Datei - siehe ValidationResult.set_skipped.
            result.set_skipped(self._text("abgebrochen_ungelesen"))
            return result

        result.hashes[image.name] = file_hash
        result.summary["read_errors"] = read_errors
        if read_errors:
            for error in read_errors:
                result.add_error(error)
            result.set_corrupted(self._text("lesefehler_beschaedigt", anzahl=len(read_errors)))
        else:
            result.status = "OK"
        return result