"""
PS5 Dump Validator – Dispatcher
Zentrale validate(path, mode) Funktion die an das richtige Modul weiterleitet.
"""
from __future__ import annotations

from typing import Callable

from ps5_validator.core.validator_base import ValidationResult
from ps5_validator.modules.dump_validator   import DumpValidator
from ps5_validator.modules.ffpfs_validator  import FfpfsValidator
from ps5_validator.modules.extfat_validator import ExtfatValidator

VALID_MODES = ("dump", "ffpfs", "extfat")


def validate(
    path: str,
    mode: str,
    threads: int = 4,
    resume: bool = False,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_flag: Callable[[], bool] | None = None,
    verbose: bool = False,
) -> ValidationResult:
    """
    Zentrale Dispatcher-Funktion.

    :param path:        Pfad zum Ordner oder zur Datei
    :param mode:        "dump" | "ffpfs" | "extfat"
    :param threads:     Anzahl Worker-Threads (nur für dump-Modus)
    :param resume:      Hash-Cache verwenden (nur für dump-Modus)
    :param progress_cb: Fortschritts-Callback(bytes_done, bytes_total, label)
    :param cancel_flag: Callable → True wenn Abbruch gewünscht
    :param verbose:     Ausführliche Ausgabe
    :return:            ValidationResult
    """
    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        r = ValidationResult(mode=mode)
        r.set_failed(f"Unbekannter Modus: '{mode}'. Erlaubt: {VALID_MODES}")
        return r

    kwargs = dict(progress_cb=progress_cb, cancel_flag=cancel_flag, verbose=verbose)

    if mode == "dump":
        v = DumpValidator(threads=threads, resume=resume, **kwargs)
    elif mode == "ffpfs":
        v = FfpfsValidator(**kwargs)
    else:  # extfat
        v = ExtfatValidator(**kwargs)

    return v.validate(path)
