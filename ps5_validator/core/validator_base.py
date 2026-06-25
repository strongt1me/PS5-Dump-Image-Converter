"""
PS5 Dump Validator – Basis-Klasse
Einheitliches Interface und Ergebnis-Schema für alle Validator-Module.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ValidationResult:
    """Einheitliches JSON-kompatibles Ergebnis-Schema."""
    mode: str = ""
    status: str = "OK"          # OK | WARNING | FAILED | CORRUPTED | MISSING
    summary: dict[str, Any] = field(default_factory=lambda: {
        "files_scanned": 0,
        "corrupted": [],
        "missing": [],
    })
    hashes: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode":    self.mode,
            "status":  self.status,
            "summary": self.summary,
            "hashes":  self.hashes,
            "errors":  self.errors,
        }

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        if self.status == "OK":
            self.status = "WARNING"

    def set_failed(self, msg: str | None = None) -> None:
        self.status = "FAILED"
        if msg:
            self.errors.append(msg)

    def set_corrupted(self, msg: str | None = None) -> None:
        self.status = "CORRUPTED"
        if msg:
            self.errors.append(msg)

    def set_missing(self, msg: str | None = None) -> None:
        self.status = "MISSING"
        if msg:
            self.errors.append(msg)


class BaseValidator(ABC):
    """Abstrakte Basisklasse für alle Validator-Module."""

    def __init__(
        self,
        progress_cb: Callable[[int, int, str], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
        verbose: bool = False,
    ) -> None:
        """
        :param progress_cb: Callback(bytes_done, bytes_total, current_file)
        :param cancel_flag: Callable das True zurückgibt wenn Abbruch gewünscht
        :param verbose:     Ausführliche Ausgabe
        """
        self._progress_cb  = progress_cb
        self._cancel_flag  = cancel_flag or (lambda: False)
        self._verbose      = verbose

    def _report_progress(self, done: int, total: int, label: str = "") -> None:
        if self._progress_cb:
            try:
                self._progress_cb(done, total, label)
            except Exception:
                pass

    def _is_cancelled(self) -> bool:
        return self._cancel_flag()

    @abstractmethod
    def validate(self, path: str) -> ValidationResult:
        """Validierung durchführen und ValidationResult zurückgeben."""
        ...
