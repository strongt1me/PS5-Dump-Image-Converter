# -*- coding: utf-8 -*-
"""Haelt Pruefstaende vom Bestand des Anwenders fern.

Angelegt am 28.08.2026, nachdem genau das schiefgegangen ist.

Die Pruefstaende dieses Projekts druecken **echte** Knoepfe - das ist ihr
Sinn, denn nur so pruefen sie, was der Anwender bedient. Echte Knoepfe
speichern aber auch echt. Ein Lauf hat dadurch die Einstellungsdatei unter
``%APPDATA%\\PS5ImageConverterPro`` veraendert, darunter zwei mit Folgen:

* ``metadata_online`` stand danach auf ``True``. Damit verlaesst die
  Title-ID des verarbeiteten Spiels den Rechner. Die Vorgabe ist aus, und
  das Programm unterscheidet ausdruecklich zwischen "nichts eingestellt"
  und "ausdruecklich abgeschaltet".
* ``shutdown_after_success`` stand danach auf ``True``. Der Rechner waere
  nach der naechsten erfolgreichen Konvertierung heruntergefahren.

Aufgefallen ist beides nur, weil ein Test es gemeldet hat
(``test_metadaten_online``: "Ohne Zutun darf nichts hinausgehen").

Wer einen Pruefstand schreibt, ruft :func:`umlenken` **vor** dem Laden des
Hauptprogramms. Danach zeigt ``konfigurationsordner()`` auf einen eigenen
Ordner, und der Bestand bleibt unberuehrt.

Beispiel::

    import pruefumgebung
    pruefumgebung.umlenken("rueckkanal")
    # ... erst jetzt das Hauptprogramm laden
"""
from __future__ import annotations

import os
import tempfile

#: Die Umgebungsvariable, die ``plattform.konfigurationsordner`` auswertet.
UMGEBUNGSNAME = "PS5CONV_KONFIGORDNER"


def umlenken(name: str = "pruefstand", leeren: bool = False) -> str:
    """Lenkt den Einstellungsordner auf einen eigenen um.

    Muss laufen, **bevor** das Hauptprogramm geladen wird: Schon beim
    Aufbau der Klasse werden Einstellungen gelesen.

    Args:
        name: Unterscheidet mehrere Pruefstaende voneinander.
        leeren: Vorhandenes wegraeumen. **Vorgabe ist False**, und zwar
            aus Erfahrung: Die Umlenkung geschieht beim Laden des Moduls,
            also auch dann, wenn jemand einen Pruefstand nur importiert,
            um darin nachzulesen. Mit ``True`` als Vorgabe hat am
            29.08.2026 ein solcher Import die Ablage eines vorangegangenen
            Laufs geloescht - und damit das Beweisstueck, das eine
            Untersuchung gerade brauchte.

            Wer wirklich bei null anfangen will, sagt es ausdruecklich.

    Returns:
        Der Ordner, der ab jetzt gilt.
    """
    ordner = os.path.join(tempfile.gettempdir(), "ps5conv_pruefung", name)
    if leeren and os.path.isdir(ordner):
        import shutil

        shutil.rmtree(ordner, ignore_errors=True)
    os.makedirs(ordner, exist_ok=True)
    os.environ[UMGEBUNGSNAME] = ordner
    return ordner


def bestandsordner() -> str:
    """Der echte Ordner des Anwenders - ohne Umlenkung.

    Nur zum Nachsehen, ob ein Lauf ihn wirklich in Ruhe gelassen hat.
    """
    gemerkt = os.environ.pop(UMGEBUNGSNAME, None)
    try:
        from ps5_validator.utils.plattform import konfigurationsordner

        return konfigurationsordner()
    finally:
        if gemerkt is not None:
            os.environ[UMGEBUNGSNAME] = gemerkt


def unberuehrt(seit: float) -> tuple[bool, str]:
    """Ob die Einstellungsdatei des Anwenders seit ``seit`` unveraendert ist.

    Args:
        seit: Zeitstempel, wie ihn ``os.path.getmtime`` liefert.

    Returns:
        Ob unveraendert, und ein Satz dazu.
    """
    datei = os.path.join(bestandsordner(), "paths.json")
    if not os.path.isfile(datei):
        return (True, "Es gibt keine Einstellungsdatei.")
    jetzt = os.path.getmtime(datei)
    if jetzt <= seit:
        return (True, "unveraendert")
    return (False, "veraendert um %.1f s nach dem Merken" % (jetzt - seit))
