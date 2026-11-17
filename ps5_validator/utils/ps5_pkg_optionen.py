# -*- coding: utf-8 -*-
"""Die Optionen des Fensters "PS5 PKG Dump & Image Converter" - Vorgaben, Pruefung und Suche ohne Oberflaeche.

Nutzerwunsch 11.10.2026: Dem Fenster fehlte der Bereich "Einstellungen"; Vorlage ist der Dialog "Optionen" der eigenen
PKG-App des Nutzers (Register Bibliothek, Darstellung, Ausgabe & Vorgaben, Wartung). Uebernommen ist, was es in diesem
Fenster gibt - Umbenennen, Hex-Ansicht, Verschieben und Papierkorb gibt es hier nicht, also auch keine Optionen dazu.

Gespeichert wird wie bisher in den Einstellungen des Programms (``_load_setting``/``_save_setting``); die Schluessel
tragen alle den Vorsatz ``ps5pkg_``. Dieses Modul kennt kein Tk - die Oberflaeche steht in
:mod:`ps5_validator.ui.ps5_pkg_optionen`.
"""
from __future__ import annotations

import os
from typing import Any, Callable

from ps5_validator.utils import ps5_pkg_werkzeug as wz
from ps5_validator.utils.pkg_plattform import ENDUNGEN_ABBILD

#: Bibliotheksordner (Liste von Pfaden) - ihre Pakete kommen beim Speichern und, mit ``START_SCAN``, bei jedem Start dazu.
ORDNER = "ps5pkg_ordner"
#: Unterordner beliebig tief durchsuchen (sonst nur eine Ebene tief wie beim Ablegen eines Ordners).
REKURSIV = "ps5pkg_rekursiv"
START_SCAN = "ps5pkg_start_scan"
#: Das Cover rechts neben der Umwandlung und in der Bibliothek zeigen.
COVER = "ps5pkg_cover"
SORTIERUNG = "ps5pkg_sortierung"
#: Nach einem erfolgreichen Auftrag den Ausgabeordner oeffnen.
OEFFNEN = "ps5pkg_oeffnen"
#: Passcode fuer ``list-inner``/``extract-inner``/``validate`` (LibProsperoPkg) - leer heisst der Standard des Werkzeugs
#: (32 Nullen). Dump Forge baut Pakete immer mit dem Standard-Passcode. Ein Paket, das mit einem anderen Passcode gebaut wurde, liesse sich sonst nicht lesen (nicht sein Kopf -
#: der ist immer offen -, aber param.json, Cover und der Inhalt).
PASSCODE = "ps5pkg_passcode"
ZIEL = "ps5pkg_ziel"
#: Eigener Arbeitsordner fuer Entpacken/Bauen/Extrahieren dieses Fensters (seit v1.9.83). Leer (Vorgabe) = wie
#: bisher der Temp-Ordner aus den Haupteinstellungen bzw. System-Temp (``Ps5PkgFenster._arbeitsordner``) - nur
#: bei Bedarf gesetzt, z. B. wenn das Systemlaufwerk fuer grosse Pakete zu wenig Platz hat.
TEMP_ORDNER = "ps5pkg_temp_ordner"
FORMAT = "ps5pkg_format"
AKTION = "ps5pkg_aktion"
BIBLIOTHEK = "ps5pkg_bibliothek"

# --- Dump Forge (seit 16.11.2026) -----------------------------------------
#: Kompressionsstufe des Pakets (``--kraken``): "fast" (Vorgabe von Dump Forge), "balanced", "smallest" oder "stored".
FORGE_KRAKEN = "ps5pkg_forge_kraken"
#: Das fertige Paket Byte fuer Byte gegen die Quelle pruefen (``--full-verify``); aus = Stichprobe (Vorgabe von Forge).
FORGE_VOLL_PRUEFEN = "ps5pkg_forge_voll_pruefen"
#: Die Backport-Bibliotheken aus ``fakelib/`` weglassen, die Emulatoren behalten (``--remove-backport``).
FORGE_BACKPORT_ENTFERNEN = "ps5pkg_forge_backport_entfernen"

# --- Bau (Dump Forge) ----------------------------------------------------
#: Anzahl der Threads beim Bau (0 = ein Kern je CPU-Kern, Vorgabe) - ``--threads`` von Dump Forge. Bis 17.11.2026 gab es hier
#: noch die Einstellungen des Baus mit LibProsperoPkg (Kompressionsmodus und -stufe, PlayGo-Chunks, deterministisch, PlayGo neu
#: erzeugen, Backport einbauen, Mindest-Firmware, Update-Paket); LibProsperoPkg baut nicht mehr, gespeicherte Werte bleiben ungenutzt.
KRAKEN_KERNE = "ps5pkg_kraken_kerne"

#: Weitergereicht, damit die Oberflaeche (``ui/ps5_pkg_optionen.py``) fuer die Passcode-Pruefung nicht extra
#: ``ps5_pkg_werkzeug`` importieren muss - alle Regeln zu den Optionen stehen hier.
passcode_gueltig = wz.passcode_gueltig

SORTIERUNGEN = ("titel", "titel_id", "groesse")
AKTIONEN = ("umwandeln", "extrahieren", "pruefen")
FORMATE = ("ffpkg", "ffpfsc", "ffpfs", "exfat")
FORGE_KRAKEN_STUFEN = ("fast", "balanced", "smallest", "stored")

#: Das Format, das vor einer eigenen Wahl gilt. Seit 16.11.2026 ``ffpkg``: Das Programm empfiehlt es selbst fuer den
#: Normalfall (``main.smp_rang_ffpkg``) und warnt bei ``ffpfsc``/``ffpfs`` vor Rucklern (150-250 MB/s beim Entpacken,
#: ``main.pfs_speed_hint``); die Vorgabe war bis dahin ``ffpfsc`` (kleiner, gemessen 417 MB gegen 703 MB). Eine gespeicherte
#: Wahl bleibt, wie sie ist.
STANDARD_FORMAT = "ffpkg"

#: Vorgaben der Optionen. Die Bibliothek selbst (``BIBLIOTHEK``) und die Bibliotheksordner gehoeren nicht zum Zuruecksetzen.
STANDARD: dict = {
    REKURSIV: False,
    START_SCAN: False,
    COVER: True,
    SORTIERUNG: "titel",
    OEFFNEN: False,
    PASSCODE: "",
    ZIEL: "",
    TEMP_ORDNER: "",
    FORMAT: STANDARD_FORMAT,
    AKTION: "umwandeln",
    KRAKEN_KERNE: 0,
    FORGE_KRAKEN: "fast",
    FORGE_VOLL_PRUEFEN: False,
    FORGE_BACKPORT_ENTFERNEN: False,
}

#: Alles, was Export und Import kennen.
BEKANNT = (ORDNER, BIBLIOTHEK) + tuple(STANDARD)

#: Ordner, in die das Durchsuchen nie hineingeht.
_UEBERSPRINGEN = ("system volume information", "$recycle.bin", "$recycle", "node_modules")


def normalisieren(schluessel: str, wert):
    """Bringt einen Wert in die erlaubte Form; ``None``, wenn er fuer diesen Schluessel nicht taugt."""
    if schluessel in (REKURSIV, START_SCAN, COVER, OEFFNEN):
        return wert if isinstance(wert, bool) else None
    if schluessel == SORTIERUNG:
        return wert if wert in SORTIERUNGEN else None
    if schluessel == AKTION:
        return wert if wert in AKTIONEN else None
    if schluessel == FORMAT:
        return wert if wert in FORMATE else None
    if schluessel == PASSCODE:
        return wert if isinstance(wert, str) and wz.passcode_gueltig(wert) else None
    if schluessel == FORGE_KRAKEN:
        return wert if wert in FORGE_KRAKEN_STUFEN else None
    if schluessel in (FORGE_VOLL_PRUEFEN, FORGE_BACKPORT_ENTFERNEN):
        return wert if isinstance(wert, bool) else None
    if schluessel == KRAKEN_KERNE:
        try:
            v = int(wert)
            return v if 0 <= v <= 256 else None
        except (TypeError, ValueError):
            return None
    if schluessel in (ZIEL, TEMP_ORDNER):
        return wert.strip() if isinstance(wert, str) else None
    if schluessel in (ORDNER, BIBLIOTHEK):
        if not isinstance(wert, list) or not all(isinstance(p, str) and p.strip() for p in wert):
            return None
        gesehen: list[str] = []
        for p in wert:
            if p not in gesehen:
                gesehen.append(p)
        return gesehen
    return None


def lesen(einstellung: Callable[[str, object], object]) -> dict[str, Any]:
    """Die gespeicherten Optionen samt Bibliothek; Unbrauchbares wird durch die Vorgabe ersetzt."""
    ergebnis: dict = {}
    for schluessel in BEKANNT:
        vorgabe = [] if schluessel in (ORDNER, BIBLIOTHEK) else STANDARD[schluessel]
        wert = normalisieren(schluessel, einstellung(schluessel, vorgabe))
        ergebnis[schluessel] = vorgabe if wert is None else wert
    return ergebnis


def importieren_pruefen(daten) -> tuple[dict, list[str]]:
    """Prueft eine eingelesene Einstellungsdatei.

    Returns:
        ``(gueltige Werte, Probleme)``. Unbekannte Schluessel und Werte der falschen Art werden gemeldet und nicht
        uebernommen; ist die Datei gar kein JSON-Objekt, steht das einzige Problem im Ergebnis.
    """
    if not isinstance(daten, dict):
        return {}, ["Die Datei enthält kein Objekt mit Einstellungen."]
    gueltig: dict = {}
    probleme: list[str] = []
    for schluessel, wert in daten.items():
        if schluessel not in BEKANNT:
            probleme.append("Unbekannt: %s" % schluessel)
            continue
        normal = normalisieren(schluessel, wert)
        if normal is None:
            probleme.append("Ungültiger Wert für %s" % schluessel)
        else:
            gueltig[schluessel] = normal
    if not gueltig and not probleme:
        probleme.append("Die Datei enthält keine Einstellungen.")
    return gueltig, probleme


def unterschiede(aktuell: dict, neu: dict) -> list[str]:
    """Was sich durch ``neu`` aendern wuerde, als kurze Zeilen ``schluessel: alt -> neu``."""
    zeilen = []
    for schluessel, wert in neu.items():
        if aktuell.get(schluessel) != wert:
            zeilen.append("%s: %s → %s" % (schluessel, _kurz(schluessel, aktuell.get(schluessel)), _kurz(schluessel, wert)))
    return zeilen


def _kurz(schluessel: str, wert) -> str:
    if schluessel == PASSCODE:
        return "(leer)" if not wert else "gesetzt"               # der Wert selbst steht nicht in einer Rueckfrage
    if isinstance(wert, list):
        return "%d Einträge" % len(wert)
    text = str(wert)
    return text if len(text) <= 40 else text[:37] + "…"


def zuruecksetzen_werte() -> dict[str, Any]:
    """Die Vorgaben fuer \"Einstellungen zuruecksetzen\" - Bibliothek und Bibliotheksordner bleiben unberuehrt."""
    return dict(STANDARD)


def ordner_durchsuchen(ordner: str, ist_spiel: Callable[[str], bool], grenze: int = 5000) -> list[str]:
    """Alle ``.pkg``, Abbilder und Spielordner unter ``ordner``, beliebig tief (ein Spielordner wird nicht weiter durchsucht).

    ``grenze`` schuetzt vor einem versehentlich gewaehlten Laufwerk: Danach hoert die Suche auf.
    """
    if ist_spiel(ordner):
        return [ordner]
    gefunden: list[str] = []
    offen = [ordner]
    while offen and len(gefunden) < grenze:
        aktuell = offen.pop()
        try:
            eintraege = sorted(os.scandir(aktuell), key=lambda e: e.name.lower())
        except OSError:
            continue
        unter: list[str] = []
        for eintrag in eintraege:
            try:
                if eintrag.is_file():
                    if eintrag.name.lower().endswith(".pkg") or os.path.splitext(eintrag.name)[1].lower() in ENDUNGEN_ABBILD:
                        gefunden.append(eintrag.path)
                elif eintrag.is_dir():
                    if eintrag.name.lower() in _UEBERSPRINGEN:
                        continue
                    if ist_spiel(eintrag.path):
                        gefunden.append(eintrag.path)
                    else:
                        unter.append(eintrag.path)
            except OSError:
                continue
        offen.extend(reversed(unter))            # in der Reihenfolge des Alphabets abarbeiten
    return gefunden[:grenze]
