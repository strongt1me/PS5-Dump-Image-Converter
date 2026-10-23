# -*- coding: utf-8 -*-
"""DLC EMU (drakmor/dlc_emu, GPL-3.0) beim Erstellen in einen Dump-Ordner einbauen.

Der Einbau besteht aus zwei Teilen:

* drei Ersatzbibliotheken (``libSceAppContent``, ``libSceNpEntitlementAccess``, ``libSceGameUpdate``) kommen
  in den ``fakelib``-Ordner des Dumps - dorthin, wo auch AMPR EMU und PlayGo liegen;
* ``/app0/dlc_emu.ini`` im Wurzelordner des Dumps sagt den Bibliotheken, welche Zusatzinhalte als vorhanden
  gelten. Eine vorhandene Datei bleibt unangetastet. Fehlt sie, wird sie aus den vollstaendigen Content-IDs der
  ``dlcmap.json`` des Dumps angelegt (der PS5-App-Dumper schreibt sie bei Spielen mit Zusatzinhalten, Schluessel =
  Content-ID) und, wenn dort nichts steht, aus den vollstaendigen Content-IDs der ``eboot.bin`` - dasselbe
  Verfahren wie das ``find_codes.py`` des Projekts, aber ohne die reinen Label-Kandidaten, die geraten sind.

Ohne ``dlc_emu.ini`` melden die Bibliotheken leere Listen. Der Einbau schadet also nie, nuetzt aber nur mit einer
passenden Datei - das Protokoll sagt, welcher Fall vorlag.

Mitgeliefert wird je Fassung ``log`` (schreibt ``/app0/dlc_emu.log``) und ``nolog``; eingebaut wird ``nolog``.
Dieses Modul kennt kein Tk und keine Hauptdatei, damit es sich ohne Fenster pruefen laesst.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Callable

logger = logging.getLogger("PS5Converter")

#: Ordner im Versionsspeicher (``PlayGo & AMPR_EMU``), der die Fassungen enthaelt.
ORDNER = "DLC_EMU"

#: Die drei Ersatzbibliotheken, die zusammen eingebaut werden.
BIBLIOTHEKEN = ("libSceAppContent.sprx", "libSceNpEntitlementAccess.sprx", "libSceGameUpdate.sprx")

#: Name der Konfiguration, die die Bibliotheken zur Laufzeit aus ``/app0`` lesen.
INI_NAME = "dlc_emu.ini"

#: Dateiendung, an der ein frueherer Einbau wiedererkannt wird (Sicherung des Spieloriginals).
SICHERUNG = ".orig"

#: Obergrenze des Programms (32 KiB) - die Bibliothek liest nicht mehr.
INI_MAX_BYTES = 32 * 1024

_CONTENT_ID = re.compile(
    rb"(?<![A-Z0-9])([A-Z]{2}[0-9]{4}-[A-Z0-9]{9}_[0-9]{2}-[A-Z0-9]{16})(?![A-Z0-9])")
_FASSUNG = re.compile(r"^\d+(?:\.\d+)*$")
_BLOCK = 4 * 1024 * 1024
_UEBERLAPP = 64


def _schluessel(fassung: str) -> tuple[int, ...]:
    return tuple(int(teil) for teil in fassung.split("."))


def fassungen(speicher: str) -> list[str]:
    """Die vorhandenen Fassungen im Versionsspeicher, neueste zuerst (leer, wenn keine mit ``nolog`` da ist)."""
    basis = Path(speicher) / ORDNER
    try:
        namen = [p.name for p in basis.iterdir()
                 if p.is_dir() and _FASSUNG.match(p.name) and (p / "nolog").is_dir()]
    except OSError:
        return []
    return sorted(namen, key=_schluessel, reverse=True)


def bibliotheksordner(speicher: str, fassung: str = "", protokoll: bool = False) -> str:
    """Ordner mit den drei Bibliotheken der Fassung (die neueste, wenn keine genannt ist); ``""`` wenn nichts da ist."""
    vorhanden = fassungen(speicher)
    if not vorhanden:
        return ""
    gewaehlt = fassung if fassung in vorhanden else vorhanden[0]
    ordner = Path(speicher) / ORDNER / gewaehlt / ("log" if protokoll else "nolog")
    if not all((ordner / name).is_file() for name in BIBLIOTHEKEN):
        return ""
    return str(ordner)


def fassung_aus_ordner(ordner: str) -> str:
    """``0.3`` aus ``.../DLC_EMU/0.3/nolog`` - fuer das Protokoll."""
    return Path(ordner).parent.name


def _sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as datei:
        for stueck in iter(lambda: datei.read(1 << 20), b""):
            h.update(stueck)
    return h.hexdigest()


def _ist_eigene_fassung(pfad: Path, bestand: str) -> bool:
    """Gleicht ``pfad`` byteweise mit einer der mitgelieferten Dateien (``log`` oder ``nolog``) ab.

    Nur dann ist es ein frueherer Einbau und kein Spieloriginal - ein Original darf nicht verloren gehen.
    """
    try:
        wurzel = Path(bestand).parent.parent
        digest = _sha256(pfad)
        for variante in ("log", "nolog"):
            for ordner in wurzel.glob("*/" + variante):
                kandidat = ordner / pfad.name
                if kandidat.is_file() and _sha256(kandidat) == digest:
                    return True
    except OSError:
        return False
    return False


def bibliotheken_einbauen(quelle: str, fakelib: Path, protokoll: Callable[[str], None]) -> list[str]:
    """Kopiert die drei Bibliotheken in ``fakelib``; ein Spieloriginal wird einmalig als ``.orig`` gesichert.

    Returns:
        Die Namen der eingebauten Dateien. Wirft ``OSError``, wenn das Kopieren scheitert.
    """
    fakelib.mkdir(parents=True, exist_ok=True)
    fertig: list[str] = []
    for name in BIBLIOTHEKEN:
        ziel = fakelib / name
        sicherung = fakelib / (name + SICHERUNG)
        if ziel.is_file() and not sicherung.is_file() and not _ist_eigene_fassung(ziel, quelle):
            shutil.copy2(ziel, sicherung)
            protokoll(sicherung.name)
        shutil.copy2(os.path.join(quelle, name), ziel)
        fertig.append(name)
    return fertig


def content_ids_in(pfad: str) -> list[str]:
    """Alle vollstaendigen Content-IDs einer Binaerdatei, in der Reihenfolge des ersten Fundes."""
    gefunden: list[str] = []
    gesehen: set[str] = set()
    rest = b""
    try:
        with open(pfad, "rb") as datei:
            while True:
                stueck = datei.read(_BLOCK)
                if not stueck:
                    break
                daten = rest + stueck
                for treffer in _CONTENT_ID.finditer(daten):
                    wert = treffer.group(1).decode("ascii")
                    if wert not in gesehen:
                        gesehen.add(wert)
                        gefunden.append(wert)
                rest = daten[-_UEBERLAPP:]
    except OSError as exc:
        logger.debug("Content-IDs nicht lesbar (%s): %s", pfad, exc)
    return gefunden


def eigene_content_id(ordner: str) -> str:
    """Die Content-ID des Spiels selbst (``sce_sys/param.json``) - sie ist kein Zusatzinhalt; ``""`` wenn unbekannt."""
    try:
        with open(os.path.join(ordner, "sce_sys", "param.json"), "r", encoding="utf-8-sig") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return ""
    wert = daten.get("contentId") if isinstance(daten, dict) else ""
    return wert if isinstance(wert, str) else ""


#: Name der Karte, die manche Spiele (gesehen bei Unreal-Engine-Titeln wie Double Dragon Revive) selbst neben die
#: ``eboot.bin`` legen. Sie stammt nicht vom Dump-Werkzeug: Dessen Quelltext (ps5-app-dumper 2.10) kennt den Namen nicht.
DLCMAP_NAME = "dlcmap.json"

#: So heisst der Ordner eines Zusatzinhalts mit eigenen Dateien, den der PS5-App-Dumper (``dump_dlc``) neben das
#: Spiel legt: ``<Region>-<TITEL-ID>_00-<LABEL>-ac``. Ohne das ``-ac`` ist es die Content-ID (36 Zeichen).
_DLC_ORDNER = re.compile(r"^([A-Z]{2}[0-9]{4}-(?:PPSA|CUSA)[0-9]{5}_00-[A-Za-z0-9]{16})-ac$")

#: ``/app0/addcont<N>`` darf hoechstens 15 Zeichen lang sein (README von dlc_emu) - also N von 0 bis 10.
MAX_EINHAENGEPUNKTE = 11


def nachbar_dlc(ordner: str, title_id: str = "") -> list[tuple[str, str]]:
    """Die DLC-Ordner des PS5-App-Dumpers, die neben dem Spielordner liegen: ``[(Content-ID, Pfad), ...]``.

    Zusatzinhalte mit eigenen Dateien legt der Dumper als eigenen Ordner neben das Spiel (README: "each as a folder of
    its own next to the game's"). Die meisten Zusatzinhalte schalten nur etwas frei, was im Spiel schon steckt - fuer
    sie gibt es keinen Ordner. Nur Ordner mit der Titel-ID des Spiels zaehlen.
    """
    eltern = os.path.dirname(os.path.abspath(ordner))
    titel = title_id or titel_id_aus_param(ordner)
    gefunden: list[tuple[str, str]] = []
    try:
        namen = sorted(os.listdir(eltern))
    except OSError:
        return gefunden
    for name in namen:
        treffer = _DLC_ORDNER.match(name)
        pfad = os.path.join(eltern, name)
        if not treffer or not os.path.isdir(pfad):
            continue
        if titel and ("-%s_00-" % titel) not in name:
            continue
        gefunden.append((treffer.group(1), pfad))
    return gefunden


def titel_id_aus_param(ordner: str) -> str:
    """Die Title-ID aus ``sce_sys/param.json`` des Dump-Ordners; ``""`` wenn sie fehlt."""
    try:
        with open(os.path.join(ordner, "sce_sys", "param.json"), "r", encoding="utf-8-sig") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return ""
    wert = daten.get("titleId") if isinstance(daten, dict) else ""
    return wert if isinstance(wert, str) else ""


def nachbarn_einbauen(ordner: str, nachbarn: list[tuple[str, str]],
                      protokoll: Callable[[str, str, int], None],
                      melden_beginn: "Callable[[str, str, int], None] | None" = None) -> list[tuple[str, int]]:
    """Kopiert die DLC-Ordner nach ``<ordner>/addcont<N>``.

    ``melden_beginn`` wird vor dem Kopieren eines Ordners gerufen (er kann Gigabyte gross sein), ``protokoll`` danach.

    Returns:
        ``[(Content-ID, N), ...]`` der kopierten Ordner. Wirft ``OSError``, wenn das Kopieren scheitert. Ein schon
        vorhandener ``addcont<N>``-Ordner wird nicht angefasst, die naechste freie Nummer genommen.
    """
    fertig: list[tuple[str, int]] = []
    nummer = 0
    for content_id, quelle in nachbarn[:MAX_EINHAENGEPUNKTE]:
        while os.path.exists(os.path.join(ordner, "addcont%d" % nummer)) and nummer < MAX_EINHAENGEPUNKTE:
            nummer += 1
        if nummer >= MAX_EINHAENGEPUNKTE:
            break
        ziel = os.path.join(ordner, "addcont%d" % nummer)
        if melden_beginn is not None:
            melden_beginn(os.path.basename(quelle), "addcont%d" % nummer, nummer)
        shutil.copytree(quelle, ziel)
        protokoll(os.path.basename(quelle), "addcont%d" % nummer, nummer)
        fertig.append((content_id, nummer))
        nummer += 1
    return fertig

_CONTENT_ID_GANZ = re.compile(r"^[A-Z]{2}[0-9]{4}-[A-Z0-9]{9}_[0-9]{2}-[A-Z0-9]{16}$")


def content_ids_aus_dlcmap(ordner: str) -> list[str]:
    """Die Content-IDs aus ``dlcmap.json`` (``{"dlcmap": {"<Content-ID>": "<Name>", ...}}``), ohne Ungueltiges.

    Eine fehlende oder kaputte Datei gibt eine leere Liste.
    """
    try:
        with open(os.path.join(ordner, DLCMAP_NAME), "r", encoding="utf-8-sig") as datei:
            daten = json.load(datei)
    except (OSError, ValueError):
        return []
    karte = daten.get("dlcmap") if isinstance(daten, dict) else None
    if not isinstance(karte, dict):
        return []
    return [k for k in karte if isinstance(k, str) and _CONTENT_ID_GANZ.match(k)]


def ini_aus_eboot(ordner: str) -> list[str]:
    """Die Content-IDs aus der ``eboot.bin`` des Dumps ohne die des Spiels selbst."""
    eboot = os.path.join(ordner, "eboot.bin")
    if not os.path.isfile(eboot):
        return []
    eigene = eigene_content_id(ordner)
    return [c for c in content_ids_in(eboot) if c != eigene]


#: Abschnitt der angelegten Eintraege: ``PSAL`` (Lizenz/Berechtigung, keine Datendateien zum Einhaengen).
#: Gemessen am 23.10.2026 an Double Dragon Revive (Vorbesteller-Inhalt): Mit ``PSAC`` stuerzte das Spiel nach 16 s mit
#: einem Lesezugriff auf null ab; mit ``fakelib_mode=...:disabled`` lief es. Vermutet: Die Bibliothek liefert beim
#: Einhaengen den Pfad ``/app0/addcont0``, den es nicht gibt. Wer Zusatzinhalte mit Dateien hat, schreibt ``[PSAC]``
#: mit ``mount_point`` von Hand.
ABSCHNITT = "PSAL"


def ini_text_mit_ordnern(einhaengen: list[tuple[str, int]], lizenzen: list[str]) -> str:
    """``[PSAC]`` mit ``mount_point`` je kopiertem DLC-Ordner, danach ``[PSAL]`` je Content-ID ohne Ordner."""
    teile: list[str] = []
    laenge = 0
    belegt = {content_id for content_id, _n in einhaengen}
    stuecke = ["[PSAC]\ncontent_id=%s\nmount_point=/app0/addcont%d\n" % (cid, n) for cid, n in einhaengen]
    stuecke += ["[%s]\ncontent_id=%s\n" % (ABSCHNITT, cid) for cid in lizenzen if cid not in belegt]
    for stueck in stuecke:
        if laenge + len(stueck) + 1 > INI_MAX_BYTES:
            break
        teile.append(stueck)
        laenge += len(stueck) + 1
    return "\n".join(teile)


def ini_text(content_ids: list[str]) -> str:
    """Der Inhalt einer ``dlc_emu.ini`` mit einem Abschnitt (:data:`ABSCHNITT`) je Content-ID (innerhalb der 32 KiB)."""
    teile: list[str] = []
    laenge = 0
    for content_id in content_ids:
        stueck = "[%s]\ncontent_id=%s\n" % (ABSCHNITT, content_id)
        if laenge + len(stueck) + 1 > INI_MAX_BYTES:
            break
        teile.append(stueck)
        laenge += len(stueck) + 1
    return "\n".join(teile)


def ini_anlegen(ordner: str, einhaengen: "list[tuple[str, int]] | None" = None) -> tuple[str, int]:
    """Legt ``dlc_emu.ini`` im Dump an, wenn es keine gibt.

    Args:
        einhaengen: ``[(Content-ID, N), ...]`` der nach ``addcont<N>`` kopierten DLC-Ordner
            (:func:`nachbarn_einbauen`); sie bekommen einen ``[PSAC]``-Eintrag mit ``mount_point``.

    Returns:
        ``("vorhanden", 0)`` bei einer schon vorhandenen Datei, ``("angelegt", n)`` mit ``n`` Eintraegen, sonst
        ``("keine", 0)`` - dann liegt nichts da, und der Anwender muss die Datei selbst schreiben.
    """
    ziel = os.path.join(ordner, INI_NAME)
    if os.path.isfile(ziel):
        return "vorhanden", 0
    # Die Karte des Spiels zuerst: Sie nennt die Zusatzinhalte ausdruecklich. Die eboot.bin ist nur der Rueckfall.
    ids = content_ids_aus_dlcmap(ordner) or ini_aus_eboot(ordner)
    if einhaengen:
        text = ini_text_mit_ordnern(einhaengen, ids)
    else:
        text = ini_text(ids)
    if not text:
        return "keine", 0
    with open(ziel, "w", encoding="utf-8", newline="\n") as datei:
        datei.write(text)
    return "angelegt", text.count("content_id=")
