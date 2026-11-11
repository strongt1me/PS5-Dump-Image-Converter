# -*- coding: utf-8 -*-
"""Sicherungskopien (``<Datei>.orig``) ganz oder gar nicht anlegen.

Die Einbauten (AMPR EMU, DLC EMU, Fake-Signieren) legen vor dem Ersetzen einer Spieldatei einmalig eine Sicherung des
Originals an und schauen beim naechsten Lauf nur nach, ob es die ``.orig`` schon gibt. Eine Kopie, die mitten im
Schreiben abbricht (Platte voll, Stromausfall, Prozess beendet), stuende dann als vermeintlich gueltige Sicherung da,
und der naechste Lauf ersetzte das Original, ohne es noch einmal zu sichern. Darum entsteht die Kopie unter einem
Zwischennamen, wird auf den Datentraeger geschrieben und auf Groesse geprueft und erhaelt ihren Endnamen erst dann.
"""
from __future__ import annotations

import os
import shutil

#: Endung der Zwischendatei neben der Sicherung.
TEIL = ".teil"


def sicherung_anlegen(quelle: "str | os.PathLike[str]", ziel: "str | os.PathLike[str]") -> None:
    """Legt ``ziel`` als vollstaendige Kopie von ``quelle`` an - ganz oder gar nicht.

    Raises:
        OSError: Die Kopie liess sich nicht vollstaendig schreiben. ``ziel`` existiert dann nicht, und es bleibt
            keine halbe Zwischendatei liegen.
    """
    quelle = os.fspath(quelle)
    ziel = os.fspath(ziel)
    teil = ziel + TEIL
    try:
        if os.path.lexists(teil):
            _entfernen(teil)                       # Rest eines frueheren, abgebrochenen Laufs
        shutil.copyfile(quelle, teil)
        with open(teil, "rb+") as fh:
            fh.flush()
            os.fsync(fh.fileno())
        if os.path.getsize(teil) != os.path.getsize(quelle):
            raise OSError("Sicherungskopie unvollstaendig: %s" % os.path.basename(ziel))
        shutil.copystat(quelle, teil)              # Zeitstempel und Attribute wie beim Original
        os.replace(teil, ziel)
    except BaseException:
        if os.path.lexists(teil):
            _entfernen(teil)
        raise


def _entfernen(pfad: str) -> None:
    try:
        os.remove(pfad)
    except OSError:
        try:
            os.chmod(pfad, 0o600)                  # ein mitkopierter Schreibschutz haelt das Aufraeumen nicht auf
            os.remove(pfad)
        except OSError:
            pass
