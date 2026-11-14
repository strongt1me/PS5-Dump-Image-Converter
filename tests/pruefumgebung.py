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

import json
import os
import tempfile

#: Die Umgebungsvariable, die ``plattform.konfigurationsordner`` auswertet.
UMGEBUNGSNAME = "PS5CONV_KONFIGORDNER"

#: Die Umgebungsvariable, die ``arbeitsordner.standard_ordner`` auswertet (``arbeitsordner.UEBERSTEUERUNG``).
ARBEITSORDNER_NAME = "PS5CONV_STANDARD_TEMP"


def arbeitsordner_umlenken() -> str:
    """Lenkt den Standard-Arbeitsordner um - ausser der Aufrufer hat schon einen gesetzt.

    Ohne das legte jeder Test, der den Arbeitsordner braucht, ``C:\\Temp - Dump-Image Converter`` im echten
    Wurzelverzeichnis des Systemlaufwerks an (seit v1.9.79 der Standard, wenn niemand einen Ordner waehlt).
    """
    if not os.environ.get(ARBEITSORDNER_NAME):
        os.environ[ARBEITSORDNER_NAME] = os.path.join(tempfile.gettempdir(), "ps5conv_pruefung", "arbeitsordner")
    return os.environ[ARBEITSORDNER_NAME]


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
    arbeitsordner_umlenken()
    # Seit dem 12.11.2026 folgt das Programm beim Start der Systemsprache (``i18n.startsprache``); die Pruefstaende
    # brauchen auf jedem Rechner dieselbe Sprache - die Vorgabe der Tests war immer Deutsch.
    os.environ.setdefault("PS5CONV_SYSTEMSPRACHE", "de")
    return ordner


def gespeicherte_sprache_vergessen(ordner: "str | None" = None) -> bool:
    """Entfernt die gespeicherte Anzeigesprache (``language``) aus der Einstellungsdatei des Pruefordners.

    Im Gesamtlauf teilen sich die Pruefstaende einen Einstellungsordner (den zuletzt umgelenkten), der von Lauf zu Lauf stehen bleibt
    (``umlenken(leeren=False)``). Speichert ein Test die Sprache - der Sprachknopf, ``_save_setting("language", ...)``, eine Datei mit
    ``"language": "en"`` -, baut jede spaetere Klasse ihr Fenster in dieser Sprache, solange nichts sie zuruecksetzt. Am 14.11.2026 mass
    ``test_kartenzeilen`` so die Karte auf Englisch statt Deutsch: Dort ist der Drehknopf 8 px breiter, einzeln lief der Test durch.
    Die Pruefung ruft das vor jeder Testklasse (``conftest._gespeicherte_sprache_vergessen``): Jede Klasse beginnt mit der Sprache,
    die ``PS5CONV_SYSTEMSPRACHE`` vorgibt.

    Args:
        ordner: Der Einstellungsordner; ohne Angabe der Ordner aus ``PS5CONV_KONFIGORDNER``.

    Returns:
        ``True``, wenn eine Sprache entfernt wurde. Eine fehlende oder unlesbare Datei bleibt unberuehrt (``False``).
    """
    ordner = ordner or os.environ.get(UMGEBUNGSNAME, "")
    if not ordner:
        return False
    pfad = os.path.join(ordner, "paths.json")
    try:
        with open(pfad, "rb") as datei:
            roh = datei.read()
    except OSError:
        return False
    mit_bom = roh.startswith(b"\xef\xbb\xbf")
    try:
        daten = json.loads(roh.decode("utf-8-sig"))
    except ValueError:
        return False
    if not isinstance(daten, dict) or "language" not in daten:
        return False
    del daten["language"]
    neu = json.dumps(daten, ensure_ascii=False, indent=2).encode("utf-8")
    try:
        with open(pfad, "wb") as datei:
            datei.write((b"\xef\xbb\xbf" if mit_bom else b"") + neu)
    except OSError:
        return False
    return True


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
