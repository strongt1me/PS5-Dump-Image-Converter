"""
PS5 Dump Validator – Basis-Klasse
Einheitliches Interface und Ergebnis-Schema für alle Validator-Module.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


#: Saetze, die mehrere Validatoren gleich melden - einmal hier, damit sie in
#: allen Modulen dieselbe Vorlage tragen. Der Dispatcher vereinigt alle
#: MELDUNGEN unter dem Praefix "validator." (Durchsicht, Runde 17); eine
#: Kennung darf dort also nur eine Bedeutung haben.
GEMEINSAME_MELDUNGEN: dict[str, str] = {
    "datei_fehlt": "Datei nicht gefunden: {pfad}",
    "keine_regulaere_datei": "Keine reguläre Datei: {pfad}",
    "groesse_unlesbar": "Dateigröße nicht lesbar: {fehler}",
    "datei_leer": "Datei ist leer (0 Bytes).",
    "datei_unlesbar": "Datei nicht lesbar: {fehler}",
    "abgebrochen_ungelesen": "Validierung abgebrochen – die Datei wurde nicht vollständig gelesen.",
    "lesefehler_byte": "Lesefehler bei Byte {byte}: {fehler}",
    "lesefehler_beschaedigt": "{anzahl} Lesefehler - Datei beschädigt.",
}


def vorlage_fuellen(meldungen: dict[str, str], texte: dict[str, str] | None,
                    kennung: str, /, **werte: Any) -> str:
    """Die Vorlage zu ``kennung`` - uebersetzt, wenn ``texte`` sie traegt.

    Die Module unter ``ps5_validator`` binden i18n nicht ein; die
    Oberflaeche reicht die uebersetzten Vorlagen herein (``texte=``). Ohne
    sie gilt die deutsche Vorgabe aus ``meldungen`` - darauf bauen die
    eigenstaendige Kommandozeile und die aelteren Tests.

    Die ersten drei Parameter sind nur-positionell, damit ein Platzhalter
    beliebig heissen darf (Runde 18: ``{kennung}`` stiess mit dem
    gleichnamigen Parameter zusammen).
    """
    vorlage = (texte or {}).get(kennung) or meldungen[kennung]
    return vorlage.format(**werte) if werte else vorlage


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

    #: Die Saetze des Moduls als Vorlagen; jede Unterklasse setzt ihr dict.
    MELDUNGEN: dict[str, str] = GEMEINSAME_MELDUNGEN

    def __init__(
        self,
        progress_cb: Callable[[int, int, str], None] | None = None,
        cancel_flag: Callable[[], bool] | None = None,
        verbose: bool = False,
        texte: dict[str, str] | None = None,
    ) -> None:
        """
        :param progress_cb: Callback(bytes_done, bytes_total, current_file)
        :param cancel_flag: Callable das True zurückgibt wenn Abbruch gewünscht
        :param verbose:     Ausführliche Ausgabe
        :param texte:       Übersetzte Vorlagen je Kennung (``MELDUNGEN``);
                            bis zur Durchsicht (Runde 17) kamen alle Befunde
                            deutsch in einer englischen Oberfläche an.
        """
        self._progress_cb  = progress_cb
        self._cancel_flag  = cancel_flag or (lambda: False)
        self._verbose      = verbose
        self._texte        = dict(texte or {})

    def _vorlage(self, kennung: str) -> str:
        """Die ungefüllte Vorlage - für Aufrufer, die selbst einsetzen."""
        return self._texte.get(kennung) or self.MELDUNGEN[kennung]

    def _text(self, kennung: str, /, **werte: Any) -> str:
        """Ein fertiger Satz aus der Vorlage zu ``kennung``."""
        return vorlage_fuellen(self.MELDUNGEN, self._texte, kennung, **werte)

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
