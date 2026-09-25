"""
PS5 Dump Validator – Dispatcher
Zentrale validate(path, mode) Funktion die an das richtige Modul weiterleitet.
"""
from __future__ import annotations

from typing import Callable

from ps5_validator.core.validator_base import ValidationResult, vorlage_fuellen
from ps5_validator.modules.dump_validator   import DumpValidator
from ps5_validator.modules.ffpfs_validator  import FfpfsValidator
from ps5_validator.modules.extfat_validator import ExtfatValidator
from ps5_validator.modules.ffpkg_validator  import FfpkgValidator

VALID_MODES = ("dump", "ffpfs", "extfat", "ffpkg")

#: Alle Saetze der vier Validatoren unter einem Dach - die Oberflaeche
#: baut daraus ihre Vorlagen (Praefix "validator.", Durchsicht Runde 17).
#: Gleiche Kennungen tragen in allen Modulen dieselbe Vorlage
#: (validator_base.GEMEINSAME_MELDUNGEN; test_durchsicht_runde17 prueft es).
MELDUNGEN: dict[str, str] = {
    **DumpValidator.MELDUNGEN,
    **FfpfsValidator.MELDUNGEN,
    **ExtfatValidator.MELDUNGEN,
    **FfpkgValidator.MELDUNGEN,
    "unbekannter_modus": "Unbekannter Modus: '{modus}'. Erlaubt: {erlaubt}",
}


def _satz(texte: dict[str, str] | None, kennung: str, /, **werte: object) -> str:
    """Ein Satz aus MELDUNGEN - uebersetzt, wenn ``texte`` ihn traegt."""
    return vorlage_fuellen(MELDUNGEN, texte, kennung, **werte)


def validate(
    path: str,
    mode: str,
    threads: int = 4,
    resume: bool = False,
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_flag: Callable[[], bool] | None = None,
    verbose: bool = False,
    ufs2tool_path: str = "",
    texte: dict[str, str] | None = None,
    param_texte: dict[str, str] | None = None,
) -> ValidationResult:
    """
    Zentrale Dispatcher-Funktion.

    :param path:        Pfad zum Ordner oder zur Datei
    :param mode:        "dump" | "ffpfs" | "extfat" | "ffpkg"
    :param threads:     Anzahl Worker-Threads (nur für dump-Modus)
    :param resume:      Hash-Cache verwenden (nur für dump-Modus)
    :param progress_cb: Fortschritts-Callback(bytes_done, bytes_total, label)
    :param cancel_flag: Callable → True wenn Abbruch gewünscht
    :param verbose:     Ausführliche Ausgabe
    :param texte:       Übersetzte Vorlagen je Kennung aus ``MELDUNGEN``
    :param param_texte: Übersetzte Vorlagen der param.json-Prüfung
                        (``param_check.MELDUNGEN``, nur dump-Modus)
    :return:            ValidationResult
    """
    mode = mode.lower().strip()
    if mode not in VALID_MODES:
        r = ValidationResult(mode=mode)
        r.set_failed(_satz(texte, "unbekannter_modus", modus=mode, erlaubt=VALID_MODES))
        return r

    kwargs = dict(progress_cb=progress_cb, cancel_flag=cancel_flag, verbose=verbose,
                  texte=texte)

    if mode == "dump":
        v = DumpValidator(threads=threads, resume=resume, param_texte=param_texte, **kwargs)
    elif mode == "ffpfs":
        v = FfpfsValidator(**kwargs)
    elif mode == "extfat":
        v = ExtfatValidator(**kwargs)
    else:  # ffpkg
        v = FfpkgValidator(ufs2tool_path=ufs2tool_path, **kwargs)

    return v.validate(path)
