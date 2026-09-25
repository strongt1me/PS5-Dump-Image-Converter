"""
PS5 Dump Validator – .extfat Datei-Prüfung
Streaming-Read, SHA-256, exFAT-Struktur-Parsing (Boot-Sektor).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Callable

from ps5_validator.core.validator_base import (
    GEMEINSAME_MELDUNGEN, BaseValidator, ValidationResult,
)
from ps5_validator.utils.hashing import sha256_stream
from ps5_validator.utils.file_io import fmt_bytes
from ps5_validator.utils.logger import get_logger

# exFAT Boot-Sektor Signatur (Offset 0x1FE): 0x55AA
EXFAT_BOOT_SIG = b"\x55\xAA"
# exFAT OEM-Name (Offset 0x03): "EXFAT   " (8 Bytes)
EXFAT_OEM_NAME = b"EXFAT   "
# Sektor-Grösse für exFAT-Parsing
SECTOR_SIZE    = 512


def _genau(anzahl: int) -> str:
    """Groesse gerundet und byte-genau - ein fehlender Block ginge sonst in
    der Rundung unter ("nennt 6.1 MB, hat nur 6.1 MB")."""
    return f"{fmt_bytes(anzahl)} ({anzahl:,} Bytes)".replace(",", ".")


#: Die Befunde als Vorlagen (Durchsicht, Runde 17) - deutsch als Vorgabe,
#: uebersetzt ueber ``texte=`` (Praefix "validator." in i18n).
MELDUNGEN: dict[str, str] = {
    **GEMEINSAME_MELDUNGEN,
    "exfat_sektorgroesse": "Sektorgröße im Boot-Sektor ungültig (BytesPerSectorShift={wert}).",
    "exfat_boot_signatur": "Boot-Signatur ungültig (0x55AA erwartet).",
    "exfat_kein_oem": ("Kein exFAT-OEM-Name gefunden (gefunden: '{oem}'). "
                       "Möglicherweise kein exFAT-Container oder beschädigt."),
    "exfat_zu_klein": "Datei zu klein für Boot-Sektor (<512 Bytes).",
    "exfat_boot_lesefehler": "Boot-Sektor Lesefehler: {fehler}",
    "exfat_abgeschnitten": ("Abbild abgeschnitten: Der Boot-Sektor nennt {soll}, "
                            "die Datei hat nur {ist} (es fehlen {fehlend}). "
                            "Typisch für eine abgebrochene Kopie oder Übertragung – die Datei "
                            "neu kopieren oder neu erzeugen."),
    "exfat_lesefehler_beschaedigt": "{anzahl} Lesefehler – Container beschädigt.",
}


class ExtfatValidator(BaseValidator):
    """Validiert eine .extfat Container-Datei."""

    MELDUNGEN = MELDUNGEN

    def __init__(
        self,
        progress_cb: Callable | None = None,
        cancel_flag: Callable | None = None,
        verbose: bool = False,
        texte: dict | None = None,
    ) -> None:
        super().__init__(progress_cb, cancel_flag, verbose, texte=texte)
        self._log = get_logger()

    def _volumen_bytes(self, boot: bytes, result: ValidationResult) -> int:
        """Die Volumengroesse laut Boot-Sektor in Bytes, 0 wenn unbrauchbar.

        VolumeLength (Offset 0x48, 8 Bytes) zaehlt Sektoren,
        BytesPerSectorShift (0x6C) liegt laut exFAT-Spezifikation zwischen
        9 und 12 (512 bis 4096 Bytes je Sektor).
        """
        if len(boot) < 0x70:
            return 0
        sektoren = struct.unpack_from("<Q", boot, 0x48)[0]
        verschiebung = boot[0x6C]
        if not 9 <= verschiebung <= 12:
            result.add_error(self._text("exfat_sektorgroesse", wert=verschiebung))
            return 0
        return sektoren << verschiebung

    def validate(self, path: str) -> ValidationResult:
        result = ValidationResult(mode="extfat")
        fpath  = Path(path)

        # ── Existenz prüfen ──────────────────────────────────────────────────
        if not fpath.exists():
            result.set_missing(self._text("datei_fehlt", pfad=path))
            return result
        if not fpath.is_file():
            result.set_failed(self._text("keine_regulaere_datei", pfad=path))
            return result

        try:
            file_size = fpath.stat().st_size
        except OSError as exc:
            result.set_failed(self._text("groesse_unlesbar", fehler=exc))
            return result

        if file_size == 0:
            result.set_corrupted(self._text("datei_leer"))
            return result

        self._log.info(f"Starte exFAT-Validierung: {fpath.name} ({fmt_bytes(file_size)})")
        result.summary["file_size"]     = fmt_bytes(file_size)
        result.summary["files_scanned"] = 1

        # ── exFAT Boot-Sektor parsen ─────────────────────────────────────────
        parse_ok     = False
        cluster_count = 0
        volumen_bytes = 0
        try:
            with open(fpath, "rb") as fh:
                boot = fh.read(SECTOR_SIZE)

            if len(boot) >= SECTOR_SIZE:
                # OEM-Name prüfen (Offset 3, 8 Bytes)
                oem = boot[3:11]
                if oem == EXFAT_OEM_NAME:
                    parse_ok = True
                    # Boot-Signatur prüfen (Offset 510)
                    if boot[SECTOR_SIZE - 2:SECTOR_SIZE] != EXFAT_BOOT_SIG:
                        result.add_error(self._text("exfat_boot_signatur"))
                    # Cluster-Anzahl (Offset 0x5C, 4 Bytes LE)
                    if len(boot) >= 0x60:
                        cluster_count = struct.unpack_from("<I", boot, 0x5C)[0]
                    volumen_bytes = self._volumen_bytes(boot, result)
                    self._log.info(f"exFAT erkannt | Cluster: {cluster_count}")
                else:
                    oem_str = oem.decode("ascii", errors="replace").strip()
                    result.add_error(self._text("exfat_kein_oem", oem=oem_str))
            else:
                result.add_error(self._text("exfat_zu_klein"))

        except OSError as exc:
            result.add_error(self._text("exfat_boot_lesefehler", fehler=exc))

        result.summary["exfat_detected"]   = parse_ok
        result.summary["cluster_count"]    = cluster_count

        # ── Groesse gegen den Boot-Sektor ────────────────────────────────────
        # Bis v1.9.24 fehlte dieser Vergleich. Eine abgebrochene Kopie oder
        # Uebertragung las sich ohne Lesefehler bis zu ihrem (zu fruehen)
        # Ende, und Aufgabe 8 meldete "OK" - gemessen am 17.09.2026 an einem
        # auf 1 MB gekuerzten Abbild. Ein vom Programm gebautes .exfat ist
        # genau VolumeLength Sektoren gross (12 von 12 Abbildern gemessen).
        if volumen_bytes:
            result.summary["volume_size"] = fmt_bytes(volumen_bytes)
            if file_size < volumen_bytes:
                fehlend = volumen_bytes - file_size
                result.summary["missing_bytes"] = fehlend
                result.set_corrupted(self._text(
                    "exfat_abgeschnitten", soll=_genau(volumen_bytes),
                    ist=_genau(file_size), fehlend=_genau(fehlend)))
                return result

        # ── Vollständiger Streaming-Read + SHA-256 ───────────────────────────
        read_errors: list[str] = []
        file_hash = ""
        try:
            with open(fpath, "rb") as fh:
                file_hash, read_errors = sha256_stream(
                    fh,
                    total_size=file_size,
                    progress_cb=lambda d, t: self._report_progress(d, t, fpath.name),
                    cancel_cb=self._is_cancelled,
                    lesefehler=self._vorlage("lesefehler_byte"),
                )
        except OSError as exc:
            result.set_corrupted(self._text("datei_unlesbar", fehler=exc))
            return result

        if self._is_cancelled():
            result.set_skipped(self._text("abgebrochen_ungelesen"))
            return result

        result.hashes[fpath.name] = file_hash
        result.summary["read_errors"] = read_errors

        if read_errors:
            for e in read_errors:
                result.add_error(e)
            result.set_corrupted(self._text("exfat_lesefehler_beschaedigt",
                                            anzahl=len(read_errors)))
        elif not parse_ok:
            result.status = "WARNING"
        # Sonst bleibt der Stand stehen. Bis v1.9.24 stand hier
        # ``result.status = "OK"`` - eine ungueltige Boot-Signatur (add_error
        # oben) wurde damit wieder zu "OK".

        self._log.info(
            f"exFAT-Validierung abgeschlossen: {result.status} | SHA-256: {file_hash[:16]}..."
        )
        return result
