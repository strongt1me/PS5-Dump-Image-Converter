# -*- coding: utf-8 -*-
"""Der Arbeitsordner, wenn der Anwender keinen gewaehlt hat.

Bis v1.9.78 galt dann der Temp-Ordner des Systems (``%TEMP%``). Dort raeumt Windows von sich aus auf
(Speicheroptimierung, "Temporaere Dateien entfernen") - mitten in einem Lauf verschwand so eine Arbeitskopie
(Dirt 5, 06.10.2026) - und der Pfad liegt tief im Benutzerordner, was bei langen Spielpfaden zaehlt.

Seit v1.9.79 legt das Programm unter Windows im **Wurzelverzeichnis des Systemlaufwerks** (dort, wo Windows
installiert ist, meist ``C:``) den Ordner ``Temp - Dump-Image Converter`` an und arbeitet darin. Unter Linux und
macOS gibt es kein beschreibbares Wurzelverzeichnis; dort bleibt es beim Temp-Ordner des Systems.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Mapping

#: Der Ordnername im Wurzelverzeichnis des Systemlaufwerks.
NAME = "Temp - Dump-Image Converter"

#: Umgebungsvariable, die den ganzen Pfad ersetzt - fuer die Testreihe, damit sie nie in das echte
#: Wurzelverzeichnis schreibt (``tests/conftest.py`` setzt sie), und fuer Anwender, die den Ordner verlegen wollen.
UEBERSTEUERUNG = "PS5CONV_STANDARD_TEMP"


def standard_ordner(plattform: str | None = None, umgebung: Mapping[str, str] | None = None) -> str:
    """Der Arbeitsordner ohne Wahl des Anwenders - oder ``""``, wenn der Temp-Ordner des Systems gilt.

    Der Ordner wird hier **nicht** angelegt; das geschieht erst, wenn das Programm ihn braucht
    (``_get_runtime_temp_dir`` legt ihn an und prueft die Schreibbarkeit).

    Args:
        plattform: Nur fuer Tests - ``sys.platform``.
        umgebung: Nur fuer Tests - ``os.environ``.

    Returns:
        Unter Windows ``<Systemlaufwerk>\\Temp - Dump-Image Converter``; mit gesetzter
        :data:`UEBERSTEUERUNG` deren Wert; sonst ``""``.
    """
    umgebung = os.environ if umgebung is None else umgebung
    eigener = str(umgebung.get(UEBERSTEUERUNG, "") or "").strip()
    if eigener:
        return os.path.normpath(eigener)
    if (plattform or sys.platform) != "win32":
        return ""
    laufwerk = str(umgebung.get("SystemDrive", "") or "").strip().rstrip("\\/")
    # "C:" - alles andere (leer, ein Pfad, eine UNC-Angabe) waere nicht das Laufwerk, auf dem Windows liegt.
    if len(laufwerk) != 2 or laufwerk[1] != ":" or not laufwerk[0].isalpha():
        laufwerk = "C:"
    return laufwerk + "\\" + NAME
