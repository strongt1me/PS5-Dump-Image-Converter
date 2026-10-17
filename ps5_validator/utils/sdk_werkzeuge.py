# -*- coding: utf-8 -*-
"""SDK-Hilfswerkzeuge aus dem PlayStation-SDK (derzeit Windows-only).

Das SDK liegt unter ``libs/sdk/`` naeben der EXE.  Jede Funktion prueft,
ob das Werkzeug vorhanden ist, und wirft ``Fehler``, wenn es fehlt oder
der Lauf scheitert.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable

_Zeile = Callable[[str], None]

#: Ordner mit den SDK-Werkzeugen (relativ zur Projektwurzel oder neben der EXE).
SDK_ORDNER = os.path.join("libs", "sdk")

DDS2PNG_NAME = "prospero-dds2png.exe" if sys.platform == "win32" else "prospero-dds2png"


class Fehler(Exception):
    """Ein SDK-Werkzeug ist gescheitert; die Meldung ist fuer das Protokoll."""


def dds2png_suchen(wurzeln: list[str] | None = None) -> str:
    """Pfad zu ``prospero-dds2png`` (``.exe`` unter Windows), sonst ``""``."""
    for wurzel in (wurzeln or []):
        kandidat = os.path.join(wurzel, SDK_ORDNER, DDS2PNG_NAME)
        if os.path.isfile(kandidat):
            return kandidat
    return ""


def dds_zu_png(werkzeug: str, quelle: str, ziel: str, *,
               preserve_alpha: bool = False, zeile: _Zeile | None = None) -> None:
    """Konvertiert eine DDS-Datei nach PNG mit ``prospero-dds2png``.

    Args:
        werkzeug: Pfad zur EXE.
        quelle: Eingabedatei (.dds).
        ziel: Ausgabedatei (.png).
        preserve_alpha: ``--preserve-alpha`` weiterreichen.
        zeile: Fortschritts-/Protokollrueckruf.

    Raises:
        Fehler: Werkzeug fehlt, Quelldatei fehlt oder Lauf gescheitert.
    """
    if not werkzeug or not os.path.isfile(werkzeug):
        raise Fehler("prospero-dds2png nicht gefunden")
    if not os.path.isfile(quelle):
        raise Fehler("Quelldatei nicht gefunden: %s" % quelle)

    argumente = [werkzeug, "decode-dds", quelle, ziel]
    if preserve_alpha:
        argumente.append("--preserve-alpha")

    if zeile:
        zeile("DDS → PNG: %s" % os.path.basename(quelle))

    try:
        proc = subprocess.run(argumente, capture_output=True, timeout=60)
    except FileNotFoundError as exc:
        raise Fehler("prospero-dds2png nicht ausfuehrbar") from exc
    except subprocess.TimeoutExpired as exc:
        raise Fehler("Zeitueberschreitung bei der Konvertierung") from exc

    ausgabe = (proc.stdout + proc.stderr).decode("utf-8", errors="replace").strip()
    if ausgabe and zeile:
        zeile(ausgabe)
    if proc.returncode != 0:
        raise Fehler("Rueckgabe %d%s" % (proc.returncode, (": " + ausgabe) if ausgabe else ""))
