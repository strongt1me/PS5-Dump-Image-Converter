# -*- coding: utf-8 -*-
"""Backport-Schritt fuer den PS5-PKG-Bau (seit v1.9.83).

Stellt :func:`backport_einbauen` bereit, das den Backport-Schritt des Hauptprogramms
nachbaut, aber ohne Tk-Zugriff. Wird von :mod:`ps5_validator.ui.ps5_pkg_fenster` im
Arbeitsfaden vor ``ffpfsc-pkg-tool build`` ausgefuehrt.

Wichtig: Diese Funktion aendert den Spielordner **in-place**. Wenn der Aufrufer nicht
sicher ist, dass er eine Staging-Kopie uebergibt, soll er vorher eine anlegen.
"""
from __future__ import annotations

import logging
import os
import shutil
from typing import Callable

from ps5_validator.utils import ps5_backport

logger = logging.getLogger("PS5Converter.utils.ps5_pkg_backport")

#: Was die Funktion zurueckliefert.
ERGEBNIS_OK = "ok"
ERGEBNIS_FEHLER = "fehler"
ERGEBNIS_ABGEBROCHEN = "abgebrochen"


def backport_einbauen(ordner: str, firmware: int, fakelib_basis: str, *,
                      zeile: Callable[[str], None] | None = None,
                      abbruch: Callable[[], bool] | None = None,
                      fakelib_ordnername: str = ps5_backport.FAKELIB_ORDNER
                      ) -> tuple[str, str]:
    """Fuehrt den Backport-Schritt auf ``ordner`` aus.

    Args:
        ordner:            Spielordner (wird in-place veraendert).
        firmware:          PS5-Hauptversion (4, 5, 6, 7 …).
        fakelib_basis:     Ordner mit den mitgelieferten Ersatzbibliotheken.
                           Leer = nur patchen, keine Bibliotheken kopieren.
        zeile:             Callback fuer Protokollzeilen.
        abbruch:           Callback; liefert True wenn abgebrochen werden soll.
        fakelib_ordnername: ``"fakelib"`` oder ``"fakelib2"``.

    Returns:
        ``(ERGEBNIS_OK|ERGEBNIS_FEHLER|ERGEBNIS_ABGEBROCHEN, meldung)``
    """
    def melden(text: str) -> None:
        if zeile:
            zeile(text)

    def pruefe_abbruch() -> bool:
        return bool(abbruch and abbruch())

    try:
        ziel_ps5, ziel_ps4 = ps5_backport.sdk_paar(firmware)
    except ps5_backport.BackportFehler as exc:
        return ERGEBNIS_FEHLER, str(exc)

    melden("[BACKPORT] Firmware %d.xx — SDK 0x%X / 0x%X" % (firmware, ziel_ps5, ziel_ps4))

    gepatcht = fehler = 0
    for pfad in ps5_backport.kandidaten(ordner):
        if pruefe_abbruch():
            return ERGEBNIS_ABGEBROCHEN, "abgebrochen"
        try:
            with open(pfad, "rb") as fh:
                roh = fh.read()
        except OSError as exc:
            fehler += 1
            logger.debug("Backport: %s nicht lesbar: %s", pfad, exc)
            continue

        kennung, neu, grund = ps5_backport.datei_verarbeiten(
            roh, ziel_ps5=ziel_ps5, ziel_ps4=ziel_ps4,
            libc_zusatz=True, ist_libc_datei=ps5_backport.ist_libc(pfad))
        if kennung == ps5_backport.ERG_FEHLER:
            fehler += 1
            melden("[BACKPORT] Fehler: %s — %s" % (os.path.relpath(pfad, ordner), grund))
            continue
        if kennung != ps5_backport.ERG_GEPATCHT:
            continue

        zwischen = pfad + ".bp_neu"
        try:
            with open(zwischen, "wb") as fh:
                fh.write(neu)
            os.replace(zwischen, pfad)
            gepatcht += 1
        except OSError as exc:
            fehler += 1
            try:
                if os.path.isfile(zwischen):
                    os.remove(zwischen)
            except OSError:
                pass
            melden("[BACKPORT] Schreibfehler: %s — %s" % (os.path.relpath(pfad, ordner), exc))

    # param.json: verlangte Firmware und SDK-Hauptversion herabsetzen
    try:
        for feld, alt, neu_wert in ps5_backport.param_json_anpassen(ordner, firmware):
            melden("[BACKPORT] param.json %s: %s -> %s" % (feld, alt, neu_wert))
    except (OSError, ps5_backport.BackportFehler) as exc:
        melden("[BACKPORT] param.json nicht herabgesetzt: %s" % exc)

    # Ersatzbibliotheken
    kopiert = 0
    if fakelib_basis and os.path.isdir(fakelib_basis):
        quellen = ps5_backport.fakelib_dateien(fakelib_basis, firmware)
        ziel_lib = ps5_backport.fakelib_ziel(ordner, fakelib_ordnername)
        if not quellen:
            melden("[BACKPORT] Warnung: keine Ersatzbibliotheken fuer FW %d.xx." % firmware)
        else:
            try:
                os.makedirs(ziel_lib, exist_ok=True)
                for quelle in quellen:
                    shutil.copy2(quelle, os.path.join(ziel_lib, os.path.basename(quelle)))
                    kopiert += 1
            except OSError as exc:
                return ERGEBNIS_FEHLER, "Ersatzbibliotheken: %s" % exc

    ergebnis = "gepatcht=%d, libs=%d, fehler=%d" % (gepatcht, kopiert, fehler)
    melden("[BACKPORT] Fertig. " + ergebnis)
    return (ERGEBNIS_FEHLER if fehler > 0 else ERGEBNIS_OK), ergebnis


def firmwares_fuer_auswahl(fakelib_basis: str) -> tuple[int, ...]:
    """Verfuegbare Firmware-Versionen fuer die Auswahl im Dialog."""
    gefunden = ps5_backport.firmwares_mit_bestand(fakelib_basis)
    return gefunden or ps5_backport.FIRMWARE_MIT_FAKELIBS
