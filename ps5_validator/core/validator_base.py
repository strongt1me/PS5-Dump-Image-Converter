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
    #: OK | WARNING | SKIPPED | FAILED | CORRUPTED | MISSING
    #:
    #: ``SKIPPED`` steht seit v1.9.1 fuer "konnte nicht geprueft werden" und
    #: ist ausdruecklich **kein** Urteil ueber die Datei. Vorher meldete der
    #: Validator in diesem Fall ``FAILED`` - also "beanstandet" -, obwohl
    #: nichts angesehen worden war. Aufgefallen ist das zweimal in vollen
    #: Testrunden: Ohne Administratorrechte kommt UFS2Tool nicht an ein
    #: ``.ffpkg`` heran (WinError 740), und das Ergebnis las sich wie ein
    #: Schaden am Abbild.
    status: str = "OK"
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

    def set_skipped(self, msg: str | None = None) -> None:
        """Die Pruefung konnte nicht stattfinden - kein Urteil ueber die Datei.

        Bewusst getrennt von ``set_failed``: Dort ist etwas beanstandet
        worden, hier ist nichts angesehen worden. Der Unterschied ist fuer
        den Benutzer entscheidend, denn ``FEHLGESCHLAGEN`` an einem
        einwandfreien Abbild fuehrt in die Irre.

        Ein bereits gefaelltes Urteil wird nicht ueberschrieben: Wer schon
        etwas gefunden hat, hat auch etwas gesehen.
        """
        if self.status in ("OK", "WARNING"):
            self.status = "SKIPPED"
        if msg:
            self.errors.append(msg)

    @property
    def wurde_geprueft(self) -> bool:
        """False, wenn die Pruefung gar nicht erst zustande kam."""
        return self.status != "SKIPPED"


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
