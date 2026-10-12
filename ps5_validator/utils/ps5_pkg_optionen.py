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
from typing import Callable

from ps5_validator.utils import ps5_pkg_werkzeug as wz

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
#: Passcode fuer ``list-inner``/``extract-inner``/``validate``/``build`` - leer heisst der Standard des Werkzeugs
#: (32 Nullen). Ein Paket, das mit einem anderen Passcode gebaut wurde, liesse sich sonst nicht lesen (nicht sein Kopf -
#: der ist immer offen -, aber param.json, Cover und der Inhalt).
PASSCODE = "ps5pkg_passcode"
#: Welches Werkzeug "Paket bauen" verwendet - "lpp" (LibProsperoPkg 1.2.0, ffpfsc-pkg-tool, Vorgabe) oder "ppt"
#: (ProsperoPkgTool, zweiter Paketersteller seit 12.10.2026). Gilt nur fuer den Bau; Lesen, Pruefen und Entpacken
#: bleiben immer bei LibProsperoPkg (ffpfsc-pkg-tool kennt --json, Passcode und die CNT-Metadaten-Zusammenfuehrung,
#: ProsperoPkgTool nicht).
BUILDER = "ps5pkg_builder"
ZIEL = "ps5pkg_ziel"
FORMAT = "ps5pkg_format"
AKTION = "ps5pkg_aktion"
BIBLIOTHEK = "ps5pkg_bibliothek"

#: Weitergereicht, damit die Oberflaeche (``ui/ps5_pkg_optionen.py``) fuer die Passcode-Pruefung nicht extra
#: ``ps5_pkg_werkzeug`` importieren muss - alle Regeln zu den Optionen stehen hier.
passcode_gueltig = wz.passcode_gueltig

SORTIERUNGEN = ("titel", "titel_id", "groesse")
AKTIONEN = ("umwandeln", "extrahieren", "pruefen")
FORMATE = ("ffpkg", "ffpfsc", "ffpfs", "exfat")
BUILDER_WERTE = ("lpp", "ppt")

#: Vorgaben der Optionen. Die Bibliothek selbst (``BIBLIOTHEK``) und die Bibliotheksordner gehoeren nicht zum Zuruecksetzen.
STANDARD: dict = {
    REKURSIV: False,
    START_SCAN: False,
    COVER: True,
    SORTIERUNG: "titel",
    OEFFNEN: False,
    PASSCODE: "",
    BUILDER: "lpp",
    ZIEL: "",
    FORMAT: "ffpfsc",
    AKTION: "umwandeln",
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
    if schluessel == BUILDER:
        return wert if wert in BUILDER_WERTE else None
    if schluessel == ZIEL:
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


def lesen(einstellung: Callable[[str, object], object]) -> dict:
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


def zuruecksetzen_werte() -> dict:
    """Die Vorgaben fuer \"Einstellungen zuruecksetzen\" - Bibliothek und Bibliotheksordner bleiben unberuehrt."""
    return dict(STANDARD)


def ordner_durchsuchen(ordner: str, ist_spiel: Callable[[str], bool], grenze: int = 5000) -> list[str]:
    """Alle ``.pkg`` und Spielordner unter ``ordner``, beliebig tief (ein Spielordner wird nicht weiter durchsucht).

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
                    if eintrag.name.lower().endswith(".pkg"):
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
