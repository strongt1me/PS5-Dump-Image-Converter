# -*- coding: utf-8 -*-
"""Die Einstellungsdatei lesen und schreiben - paths.json.

Siebzehnter Schnitt der Trennung.

Hier liegen die gemerkten Pfade, die Designwahl, der Hintergrund und
alles Weitere, was ueber das Programmende hinaus gelten soll. Der
Monolith greift an 116 Stellen darauf zu, die WPF-Oberflaeche ebenfalls
- deshalb muss es stehen, bevor eine der beiden Oberflaechen ohne die
andere laufen kann.

Zwei Dinge sind hier wichtiger als die Zeilenzahl:

**Geschrieben wird ueber eine Nebendatei.** ``open(..., "w")`` leert die
Zieldatei sofort. Wer in diesem Moment liest, bekommt eine leere oder
halb geschriebene Datei; ein Absturz zwischen Leeren und Schreiben
kostet **alle** Einstellungen. Deshalb: erst daneben schreiben, dann
umbenennen.

**Gelesen wird mit Wiederholung.** Waehrend eines Schreibvorgangs kann
die Datei kurz belegt sein. Ein einzelner Fehlversuch wuerde den
Vorgabewert liefern und damit eine gespeicherte Einstellung
stillschweigend verwerfen - der Anwender fände seine Wahl beim
naechsten Start nicht wieder und wuesste nicht, warum.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from typing import Any, Callable

from ps5_validator.utils.plattform import konfigurationsordner

logger = logging.getLogger("PS5Converter.utils.einstellungen")

#: Dateiname der Einstellungen im Konfigurationsordner.
DATEINAME = "paths.json"

#: Name des Rueckfalls, wenn der Konfigurationsordner nicht anlegbar ist.
NOTNAME = "ps5converter_paths.json"

#: So oft wird das Lesen wiederholt, wenn die Datei gerade belegt ist ...
LESEVERSUCHE = 4

#: ... und so oft das Ersetzen beim Schreiben.
ERSETZVERSUCHE = 6

#: Wartezeit zwischen zwei Versuchen.
WARTEZEIT_S = 0.05

#: Eine Sperre fuer alle. Sie verhindert, dass zwei Straenge zugleich
#: lesen-aendern-schreiben und einander die Werte ueberschreiben.
_sperre = threading.RLock()


def pfad() -> str:
    """Gibt den Pfad zur Einstellungsdatei zurueck.

    Der Ordner kommt aus der Plattformschicht: unter Windows weiterhin
    ``%APPDATA%\PS5ImageConverterPro`` - vorhandene Installationen
    finden ihre gemerkten Pfade und Designeinstellungen also unveraendert
    wieder -, unter Linux ``$XDG_CONFIG_HOME`` bzw. ``~/.config``, unter
    macOS ``~/Library/Application Support``.

    Laesst sich der Ordner nicht anlegen, wird auf den Temp-Ordner
    ausgewichen. Das ist kein guter Ort - die Einstellungen koennen dort
    aufgeraeumt werden -, aber besser als gar keine Einstellungen.
    """
    ordner = konfigurationsordner()
    try:
        os.makedirs(ordner, exist_ok=True)
    except OSError as exc:
        logger.debug("Konfigurationsordner nicht anlegbar: %s", exc)
        return os.path.join(tempfile.gettempdir(), NOTNAME)
    return os.path.join(ordner, DATEINAME)


def lesen(schluessel: str, vorgabe: Any = None, *,
          datei: str = "",
          warten: Callable[[float], Any] = time.sleep) -> Any:
    """Liest eine einzelne Einstellung.

    Args:
        schluessel: Name der Einstellung.
        vorgabe: Was gilt, wenn nichts gespeichert ist.
        datei: Abweichender Pfad. Leer heisst: der uebliche.
        warten: Haelt zwischen zwei Versuchen an. In Pruefungen ein
            Rueckruf, der sofort zurueckkommt.

    Returns:
        Der gespeicherte Wert oder die Vorgabe.
    """
    ziel = datei or pfad()
    letzter_fehler: Exception | None = None
    for _versuch in range(LESEVERSUCHE):
        try:
            if not os.path.isfile(ziel):
                return vorgabe
            with open(ziel, "r", encoding="utf-8") as f:
                daten = json.load(f)
            return daten.get(schluessel, vorgabe)
        except (PermissionError, json.JSONDecodeError) as exc:
            letzter_fehler = exc
            warten(WARTEZEIT_S)
        except Exception as exc:
            letzter_fehler = exc
            break
    if letzter_fehler is not None:
        logger.warning("Einstellung konnte nicht geladen werden: %s",
                       letzter_fehler)
    return vorgabe


def schreiben(schluessel: str, wert: Any, *,
              datei: str = "",
              warten: Callable[[float], Any] = time.sleep) -> None:
    """Speichert eine einzelne Einstellung.

    Geschrieben wird ueber eine Nebendatei und ein Umbenennen, damit ein
    Absturz mittendrin nicht die ganze Datei kostet.

    Args:
        schluessel: Name der Einstellung.
        wert: Was gespeichert werden soll.
        datei: Abweichender Pfad. Leer heisst: der uebliche.
        warten: Haelt zwischen zwei Versuchen an.
    """
    with _sperre:
        try:
            ziel = datei or pfad()
            vorhanden: dict = {}
            if os.path.isfile(ziel):
                try:
                    with open(ziel, "r", encoding="utf-8") as f:
                        vorhanden = json.load(f)
                except Exception as exc:
                    logger.debug("Vorhandene Konfiguration nicht lesbar: %s",
                                 exc)
            vorhanden[schluessel] = wert

            neben = "%s.tmp" % ziel
            with open(neben, "w", encoding="utf-8") as f:
                json.dump(vorhanden, f, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            # Unter Windows scheitert das Ersetzen, solange ein anderer
            # Zugriff die Zieldatei offen hat. Kurz warten und erneut
            # versuchen statt die Einstellung zu verlieren.
            for versuch in range(ERSETZVERSUCHE):
                try:
                    os.replace(neben, ziel)
                    break
                except PermissionError:
                    if versuch == ERSETZVERSUCHE - 1:
                        raise
                    warten(WARTEZEIT_S)
        except Exception as exc:
            logger.warning("Einstellung konnte nicht gespeichert werden: %s",
                           exc)
