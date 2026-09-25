# -*- coding: utf-8 -*-
"""Der Bestand: Was liegt wo, und wie sieht es aus.

Dieses Modul beschafft die Daten für die Bibliothek - **ohne Oberfläche**,
damit sich jeder Teil einzeln nachmessen lässt. Drei Dinge stehen hier:

* **Der Suchlauf über den Rechner** (:func:`ordner_durchsuchen`) - rekursiv,
  über alle fünf Bauformen. Der bisherige Scan der Bibliothek ging nur eine
  Ebene tief; wer seine Sicherungen in ``Downloads/PS5/Spiele/...`` abgelegt
  hatte, sah eine leere Liste.

* **Der Suchlauf über die Konsole** (:func:`konsole_durchsuchen`) - über die
  bekannten Ablageorte. Die FTP-Verbindung kommt von außen herein: Sie
  gehört dem Fenster, das sie aufgebaut hat, und dieses Modul soll keine
  eigene aufmachen.

* **Der Bildspeicher** (:class:`Bildspeicher`) - einmal geöffnete Titelbilder
  bleiben auf der Platte liegen. Ohne das öffnet jeder Blick in die
  Bibliothek jeden Container neu; bei fünfzig Titeln sind das Minuten, und
  beim nächsten Öffnen wieder.

Was hier **nicht** steht: Tk, Bilder zeichnen, Fortschrittsbalken. Das Modul
kennt Pfade, Bytes und Wörterbücher.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import threading
import time
from typing import Any, Callable, Iterable

from .logger import get_logger

log = get_logger(__name__)

#: Die Endungen, die als fertige Sicherung gelten.
CONTAINER_ENDUNGEN: tuple[str, ...] = ("ffpfsc", "ffpfs", "exfat", "ffpkg")

#: Woran ein Dump-Ordner zu erkennen ist. Eines von beiden genügt: Manche
#: Dumps tragen kein ``eboot.bin`` im Wurzelverzeichnis, aber immer ein
#: ``sce_sys``.
DUMP_MERKMALE: tuple[str, ...] = ("eboot.bin", "sce_sys")

#: Ordner, die ein Suchlauf nie betritt - nach vollem Namen.
UEBERSPRINGEN: frozenset = frozenset({
    "__pycache__", ".git", "$RECYCLE.BIN", "System Volume Information",
    "sce_sys", "sce_module", "Media", "backports",
})

#: Dasselbe nach Namensende. ``<Spiel>_ampr_pack`` ist die Ablage der
#: gepackten Asset-Bänder: Sie liegt **neben** dem Spiel, trägt dessen Namen
#: mit einem Anhängsel und würde sonst als zweiter Titel in der Liste stehen.
#: Ein fester Name reicht dafür nicht - der Präfix ist bei jedem Spiel anders.
UEBERSPRINGEN_ENDET_AUF: tuple[str, ...] = ("_ampr_pack",)

#: So tief geht der Suchlauf höchstens. Ein Dump-Ordner liegt selten mehr
#: als eine Handvoll Ebenen unter dem gewählten Ort, und ein versehentlich
#: gewähltes Laufwerkswurzelverzeichnis soll das Fenster nicht minutenlang
#: blockieren.
MAX_TIEFE: int = 8


def _ist_dump_ordner(pfad: str) -> bool:
    """Trägt dieser Ordner ein Spiel?"""
    try:
        return any(os.path.exists(os.path.join(pfad, m)) for m in DUMP_MERKMALE)
    except OSError:
        return False


def _endung(name: str) -> str:
    return os.path.splitext(name)[1].lower().lstrip(".")


def ordner_durchsuchen(
    wurzel: str,
    *,
    max_tiefe: int = MAX_TIEFE,
    abbruch: Callable[[], bool] | None = None,
    melden: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Sucht ab ``wurzel`` nach Sicherungen - rekursiv, alle Bauformen.

    Ein gefundener Dump-Ordner wird **nicht weiter durchsucht**: Was darin
    liegt, gehört zu ihm und ist kein eigener Titel.

    Args:
        wurzel: Der gewählte Ort.
        max_tiefe: Wie viele Ebenen tief, von ``wurzel`` aus gezählt.
        abbruch: Wird zwischen den Ebenen gefragt; ``True`` beendet die Suche.
        melden: Bekommt jede Stelle, die sich nicht lesen ließ. Eine leere
            Liste sieht sonst aus wie "da ist nichts" und nicht wie "durfte
            nicht nachsehen" - derselbe Fehler steckte bis v1.9.11 im alten
            Scan.

    Returns:
        Je Fund ``{"pfad", "art", "groesse", "name"}``. ``art`` ist
        ``"folder"`` oder eine der :data:`CONTAINER_ENDUNGEN`.
    """
    funde: list[dict[str, Any]] = []
    wurzel = os.path.abspath(wurzel)
    if not os.path.isdir(wurzel):
        if melden:
            melden(wurzel)
        return funde

    def _gehe(ordner: str, tiefe: int) -> None:
        if abbruch is not None and abbruch():
            return
        if tiefe > max_tiefe:
            return
        try:
            eintraege = sorted(os.scandir(ordner), key=lambda e: e.name.lower())
        except OSError as exc:
            log.debug("Bibliothek: %s nicht lesbar (%s)", ordner, exc)
            if melden:
                melden(ordner)
            return

        for eintrag in eintraege:
            if abbruch is not None and abbruch():
                return
            try:
                ist_ordner = eintrag.is_dir(follow_symlinks=False)
            except OSError:
                continue

            if ist_ordner:
                if eintrag.name in UEBERSPRINGEN:
                    continue
                if eintrag.name.endswith(UEBERSPRINGEN_ENDET_AUF):
                    continue
                if _ist_dump_ordner(eintrag.path):
                    funde.append({
                        "pfad": eintrag.path,
                        "art": "folder",
                        "groesse": None,
                        "name": eintrag.name,
                    })
                    continue          # nicht hineinsteigen - das ist EIN Titel
                _gehe(eintrag.path, tiefe + 1)
                continue

            art = _endung(eintrag.name)
            if art not in CONTAINER_ENDUNGEN:
                continue
            try:
                groesse = eintrag.stat().st_size
            except OSError:
                groesse = None
            funde.append({
                "pfad": eintrag.path,
                "art": art,
                "groesse": groesse,
                "name": os.path.splitext(eintrag.name)[0],
            })

    _gehe(wurzel, 0)
    return funde


# ---------------------------------------------------------------------------
# Die Konsole
# ---------------------------------------------------------------------------

def _ist_dump_ordner_auf_konsole(
        ftp: Any, pfad: str,
        auflisten: Callable[[Any, str], dict[str, list[str]]]) -> bool:
    """Traegt der Ordner auf der Konsole die Merkmale eines Spiels?

    Das Gegenstueck zu :func:`_ist_dump_ordner`, nur ueber FTP statt ueber
    das Dateisystem. Die beiden duerfen **nicht** denselben Namen tragen:
    Python nimmt in einem Modul die letzte Definition, und die zweite
    verdeckte am 12.09.2026 die erste - der ganze Suchlauf ueber den
    Rechner fiel mit einem TypeError aus.

    Gesucht wird nach :data:`DUMP_MERKMALE` - ``sce_sys`` als Unterordner
    oder ``eboot.bin`` als Datei. Beides steht in jedem Dump; ein
    Papierkorb oder ein leerer Sammelordner hat weder das eine noch das
    andere.

    Ein Fehler beim Auflisten gilt als Nein: Was sich nicht lesen laesst,
    gehoert nicht als Spiel in die Liste.
    """
    try:
        inhalt = auflisten(ftp, pfad)
    except Exception as exc:  # noqa: BLE001
        log.debug("Bibliothek: %s nicht lesbar (%s)", pfad, exc)
        return False
    namen = {str(n).lower() for n in inhalt.get("dirs", [])}
    for eintrag in inhalt.get("files", []):
        name = eintrag[0] if isinstance(eintrag, (tuple, list)) else eintrag
        namen.add(str(name).lower())
    return any(merkmal in namen for merkmal in DUMP_MERKMALE)


def konsole_durchsuchen(
    ftp: Any,
    scanpfade: Iterable[str],
    *,
    ist_ordner: Callable[[Any, str], bool],
    auflisten: Callable[[Any, str], dict[str, list[str]]],
    abbruch: Callable[[], bool] | None = None,
) -> list[dict[str, Any]]:
    """Sucht auf der Konsole nach Sicherungen.

    Die FTP-Verbindung und die beiden Helfer kommen von außen: Das Fenster
    hat sie aufgebaut, kennt Zeitüberschreitungen und Anmeldung, und dieses
    Modul soll daneben keine zweite Verbindung aufmachen.

    Gesucht wird **eine Ebene** je Ablageort - so liegen die Spiele dort:
    ``/data/homebrew/<Spiel>`` oder ``/data/homebrew/<Spiel>.ffpkg``. Tiefer
    zu gehen kostet bei FTP jedesmal einen Umlauf und bringt nichts.

    Args:
        ftp: Die offene Verbindung.
        scanpfade: Die Ablageorte, die geprüft werden sollen.
        ist_ordner: ``(ftp, pfad) -> bool``.
        auflisten: ``(ftp, pfad) -> {"dirs": [...], "files": [...]}``.
        abbruch: Wird zwischen den Orten gefragt.

    Returns:
        Je Fund ``{"pfad", "art", "groesse", "name", "ablage"}``.
    """
    funde: list[dict[str, Any]] = []
    gesehen: set[str] = set()
    orte = [str(p).rstrip("/") for p in scanpfade]
    # ``/mnt/usb0`` steht selbst in der Liste - dort liegen Abbilder, die
    # ShadowMount+ sonst nie indiziert. Dadurch taucht ``/mnt/usb0/homebrew``
    # zweimal auf: einmal als Ablageort, einmal als vermeintliches Spiel
    # darin. Ein Ablageort ist kein Fund.
    ist_ablageort = set(orte)

    for ort in orte:
        if abbruch is not None and abbruch():
            break
        try:
            if not ist_ordner(ftp, ort):
                continue
            inhalt = auflisten(ftp, ort)
        except Exception as exc:  # noqa: BLE001
            log.debug("Bibliothek: %s auf der Konsole nicht lesbar (%s)", ort, exc)
            continue

        for name in inhalt.get("dirs", []):
            pfad = "%s/%s" % (ort.rstrip("/"), name)
            if pfad in gesehen or pfad in ist_ablageort:
                continue
            if name in UEBERSPRINGEN or name.endswith(UEBERSPRINGEN_ENDET_AUF):
                continue
            # Nicht jeder Ordner ist ein Spiel. Auf einem USB-Datentraeger
            # der Konsole liegen ``GAMES``, ``GAMEI`` und der Papierkorb
            # gleich neben den Dumps; ohne diese Pruefung standen sie als
            # Titel in der Bibliothek. Ein Umlauf je Ordner kostet bei einer
            # Handvoll Ordnern nichts - der ganze Suchlauf braucht unter
            # einer Sekunde.
            if not _ist_dump_ordner_auf_konsole(ftp, pfad, auflisten):
                continue
            gesehen.add(pfad)
            funde.append({"pfad": pfad, "art": "folder", "groesse": None,
                          "name": name, "ablage": ort})

        for eintrag in inhalt.get("files", []):
            # ``auflisten`` darf Namen liefern oder ``(name, groesse)``.
            # Der Browser des Programms gibt Tupel zurueck - so steht die
            # Groesse gleich in der Liste, ohne dass jemand die Datei dafuer
            # noch einmal ueber FTP nachschlagen muss.
            if isinstance(eintrag, (tuple, list)):
                name = str(eintrag[0])
                try:
                    groesse = int(eintrag[1]) if len(eintrag) > 1 else None
                except (TypeError, ValueError):
                    groesse = None
            else:
                name, groesse = str(eintrag), None
            art = _endung(name)
            if art not in CONTAINER_ENDUNGEN:
                continue
            pfad = "%s/%s" % (ort.rstrip("/"), name)
            if pfad in gesehen:
                continue
            gesehen.add(pfad)
            funde.append({"pfad": pfad, "art": art, "groesse": groesse,
                          "name": os.path.splitext(name)[0], "ablage": ort})

    return funde


#: Kuerzer als das gilt ein Name als zu allgemein fuer einen Abgleich.
#: "Demo" oder "Game" wuerden sonst auf irgendetwas passen.
MINDESTLAENGE_ABGLEICH = 8


def namen_vergleichbar(links: str) -> str:
    """Bringt einen Titel auf eine Form, die sich vergleichen laesst.

    Derselbe Titel heisst an drei Stellen drei Mal anders: Die Konsole
    fuehrt "Crazy Chicken Shooter Bundle", die Datei heisst
    "Crazy Chicken Shooter.ffpfsc", und auf dem USB-Datentraeger steht
    "Arcade_Game_Zone". Interpunktion, Unterstriche, Gross- und
    Kleinschreibung und Versionsanhaengsel fallen deshalb weg.
    """
    return "".join(z for z in links.lower() if z.isalnum())


def name_zuordnen(name: str, verzeichnis: dict[str, str]) -> str:
    """Sucht zu einem Titel die Kennung aus einem Namensverzeichnis.

    Verglichen wird ueber den Anfang: Der kuerzere der beiden Namen muss
    den laengeren beginnen. Anders geht es nicht - der Dateiname traegt
    oft einen Versionszusatz ("... (01.000.000)"), die Konsole dafuer ein
    "Bundle" am Ende.

    Mehrdeutigkeit gilt als Fehlschlag: Passen zwei Titel, ist keiner
    gemeint. Ein falsches Titelbild ist schlimmer als gar keines - es
    sieht richtig aus.

    Args:
        name: Der Titel, wie er am Fund steht.
        verzeichnis: ``{vergleichbarer Name: Kennung}``.

    Returns:
        Die Kennung, oder ``""``.
    """
    gesucht = namen_vergleichbar(name)
    if len(gesucht) < MINDESTLAENGE_ABGLEICH:
        return ""
    treffer = {kennung for bekannt, kennung in verzeichnis.items()
               if len(bekannt) >= MINDESTLAENGE_ABGLEICH
               and (gesucht.startswith(bekannt) or bekannt.startswith(gesucht))}
    return treffer.pop() if len(treffer) == 1 else ""


# ---------------------------------------------------------------------------
# Namen, Fassungen, Firmware
#
# Seit dem 25.09.2026 zeigt die Bibliothek mehr als Titel und Fassung: die
# Mindest-Firmware gegen die der Konsole, die neueste Fassung laut
# PROSPEROPatches und einheitliche Namen zum Umbenennen. Die Anregung kam aus
# dem "PKG Viewer" von Loopayeh (MIT-Lizenz); uebernommen sind Ideen, kein
# Code. Hier steht nur Rechnerei ueber Zeichenketten - ohne Dateisystem,
# Netz oder Tk.
# ---------------------------------------------------------------------------

#: Leere Angaben, wie sie die Metadatenleser liefern ("–" ist ein Gedankenstrich).
_LEER: frozenset = frozenset({"", "-", "–", "?", "unbekannt", "unknown"})

#: Eine Title-ID steht allein - "PPSA01234", "CUSA12345".
_KENNUNG_RE = re.compile(r"[A-Z]{4}\d{5}")

#: Die Region als Kuerzel nach den ersten beiden Zeichen der Content-ID.
REGION_KURZ: dict[str, str] = {"EP": "EU", "UP": "US", "JP": "JP",
                               "HP": "AS", "AP": "AS", "KP": "KR"}

#: Dasselbe aus den Regionsnamen, die die Metadatenleser schreiben - der
#: aus MkPFS ("EUR", "JPN") und der eigene ("Europa", "Japan").
_REGION_AUS_NAMEN: dict[str, str] = {
    "eur": "EU", "europa": "EU", "europe": "EU",
    "usa": "US", "americas": "US",
    "jpn": "JP", "japan": "JP",
    "asia": "AS", "asien": "AS",
    "kor": "KR", "korea": "KR",
}


def _wert(angaben: dict, schluessel: str) -> str:
    """Ein Feld der Angaben - Platzhalter wie "–" gelten als leer."""
    wert = str((angaben or {}).get(schluessel) or "").strip()
    return "" if wert.lower() in _LEER else wert


def region_kurz(angaben: dict) -> str:
    """Die Region als Kuerzel ("EU", "US", ...), oder "" wenn unbekannt.

    Zuerst aus der Content-ID ("EP0001-PPSA01234_00-..." -> "EU"): Sie traegt
    die Region verlaesslich. Das Feld ``region`` ist je nach Leser anders
    beschriftet und kommt deshalb erst danach.
    """
    kennung = _wert(angaben, "content_id").upper()
    if kennung[:2] in REGION_KURZ:
        return REGION_KURZ[kennung[:2]]
    return _REGION_AUS_NAMEN.get(_wert(angaben, "region").lower(), "")


def fassung_kurz(fassung: str) -> str:
    """"01.008.000" -> "1.8.0" - fuehrende Nullen je Stelle fallen weg.

    Was nicht nur aus Ziffern und Punkten besteht, bleibt, wie es ist.
    """
    text = str(fassung or "").strip()
    teile = text.split(".")
    if not text or not all(teil.isdigit() for teil in teile):
        return text
    return ".".join(str(int(teil)) for teil in teile)


def fassung_teile(fassung: str) -> tuple[int, ...] | None:
    """Die Zahlen einer Fassung zum Vergleichen, oder None."""
    zahlen = re.findall(r"\d+", str(fassung or ""))
    return tuple(int(z) for z in zahlen) if zahlen else None


def fassung_vergleichen(eigene: str, andere: str) -> int | None:
    """-1, 0 oder 1 wie ``eigene`` gegen ``andere`` - None, wenn eine fehlt.

    Stelle fuer Stelle als Zahl: "01.010.000" ist neuer als "01.008.000",
    auch wenn die Zeichenkette kleiner aussieht. Fehlende Stellen zaehlen als
    0 ("1.8" == "01.008.000").
    """
    links, rechts = fassung_teile(eigene), fassung_teile(andere)
    if links is None or rechts is None:
        return None
    laenge = max(len(links), len(rechts))
    links += (0,) * (laenge - len(links))
    rechts += (0,) * (laenge - len(rechts))
    return (links > rechts) - (links < rechts)


def firmware_teile(firmware: str) -> tuple[int, int] | None:
    """Haupt- und Nebenstand einer Firmware-Angabe, oder None.

    Zwei Schreibweisen kommen vor: die der param.json nach der
    Aufbereitung ("09.00.00.00", "9.00") und die der Konsolensuche
    ("system-version: 12000020" - Hauptstand, Nebenstand, Rest).
    """
    text = str(firmware or "").strip().lower()
    if text.startswith("0x"):
        text = text[2:]
    if not text or text in _LEER:
        return None
    treffer = re.match(r"(\d{1,2})\.(\d{1,2})", text)
    if treffer:
        return int(treffer.group(1)), int(treffer.group(2))
    treffer = re.fullmatch(r"(\d{2})(\d{2})\d{4}(?:\d{8})?", text)
    if treffer:
        return int(treffer.group(1)), int(treffer.group(2))
    return None


def firmware_kurz(firmware: str) -> str:
    """"09.00.00.00" -> "9.00", "12000020" -> "12.00"; unbekannt -> ""."""
    teile = firmware_teile(firmware)
    return "%d.%02d" % teile if teile else ""


def firmware_vergleichen(verlangt: str, konsole: str) -> int | None:
    """-1, 0 oder 1 wie die verlangte Firmware gegen die der Konsole.

    ``1`` heisst: Das Spiel verlangt mehr, als die Konsole hat - ohne
    BACKPORT startet es dort nicht. ``None``, wenn eine Seite unbekannt ist.
    """
    links, rechts = firmware_teile(verlangt), firmware_teile(konsole)
    if links is None or rechts is None:
        return None
    return (links > rechts) - (links < rechts)


# ---------------------------------------------------------------------------
# Umbenennen
# ---------------------------------------------------------------------------

#: Die Namensformen - Kennung und Beispiel. Die ersten drei sind dieselben
#: wie im Fenster "Dump umbenennen" (``dump_rename.build_presets``), damit
#: beide Stellen gleich benennen; die vierte ist die Form des PKG Viewers.
NAMENSFORMEN: tuple[str, ...] = (
    "titel_kennung_fassung_region",     # Elden Ring - PPSA04610 - v1.17.0 - EU
    "kennung_titel_fassung",            # PPSA04610 Elden Ring (01.017.000)
    "kennung_titel",                    # PPSA04610 Elden Ring
    "kennung",                          # PPSA04610
)

#: So lang darf der Titel im neuen Namen hoechstens werden. Windows kennt
#: 260 Zeichen fuer den ganzen Pfad; ein Titel mit Untertitel und Edition
#: kommt leicht auf 120.
TITEL_HOECHSTENS: int = 120

#: Die Zustaende eines Plans. Nur "bereit" wird umbenannt.
BEREIT = "bereit"
GLEICH = "gleich"
OHNE_KENNUNG = "ohne_kennung"
ZIEL_VORHANDEN = "ziel_vorhanden"
DOPPELT = "doppelt"
AUF_KONSOLE = "konsole"
FEHLT = "fehlt"


def neuer_name(angaben: dict, form: str) -> str:
    """Der neue Name **ohne Endung** - oder "", wenn die Angaben nicht reichen.

    Ohne Title-ID gibt es keinen Namen: Sie ist das Einzige, was jede Form
    traegt, und ohne sie saehe das Ergebnis richtig aus und waere es nicht.
    """
    from .dump_rename import (PRESET_PPSA_ONLY, PRESET_PPSA_TITLE,
                              PRESET_PPSA_TITLE_VERSION, build_presets,
                              sanitize_name)

    kennung = _wert(angaben, "title_id").upper()
    if not _KENNUNG_RE.fullmatch(kennung):
        return ""
    titel = sanitize_name(_wert(angaben, "title"))[:TITEL_HOECHSTENS].strip()
    fassung = _wert(angaben, "version")
    if form == "titel_kennung_fassung_region":
        teile = [titel] if titel else []
        teile.append(kennung)
        if fassung:
            teile.append("v" + fassung_kurz(fassung))
        region = region_kurz(angaben)
        if region:
            teile.append(region)
        return sanitize_name(" - ".join(teile))
    vorlagen = build_presets(kennung, titel, fassung, True, bool(fassung))
    name = {"kennung_titel_fassung": vorlagen[PRESET_PPSA_TITLE_VERSION],
            "kennung_titel": vorlagen[PRESET_PPSA_TITLE],
            "kennung": vorlagen[PRESET_PPSA_ONLY]}.get(form, "")
    return sanitize_name(name)


def _vergleichsform(pfad: str) -> str:
    return os.path.normcase(os.path.abspath(pfad))


def umbenennen_planen(eintraege: Iterable[dict], form: str) -> list[dict[str, Any]]:
    """Plant das Umbenennen - **ohne etwas anzufassen**.

    Args:
        eintraege: Eintraege der Bibliothek (``path``, ``kind``, ``meta``,
            ``ps5``).
        form: Eine der :data:`NAMENSFORMEN`.

    Returns:
        Je Eintrag ``{"eintrag", "alt", "neu", "zustand"}``. ``neu`` ist der
        volle neue Pfad; Endungen bleiben, wie sie waren. Auf der Konsole
        wird nichts umbenannt: Dort liest ShadowMount+ die Namen, und ein
        Fehlgriff liesse ein Spiel verschwinden.
    """
    plan: list[dict[str, Any]] = []
    vergeben: set[str] = set()
    for eintrag in eintraege:
        alt = str(eintrag.get("path") or "")
        zeile: dict[str, Any] = {"eintrag": eintrag, "alt": alt, "neu": "",
                                 "zustand": BEREIT}
        plan.append(zeile)
        if eintrag.get("ps5"):
            zeile["zustand"] = AUF_KONSOLE
            continue
        if not alt or not os.path.exists(alt):
            zeile["zustand"] = FEHLT
            continue
        name = neuer_name(eintrag.get("meta") or {}, form)
        if not name:
            zeile["zustand"] = OHNE_KENNUNG
            continue
        endung = "" if os.path.isdir(alt) else os.path.splitext(alt)[1]
        neu = os.path.join(os.path.dirname(alt), name + endung)
        zeile["neu"] = neu
        if neu == alt:
            zeile["zustand"] = GLEICH
            continue
        ziel = _vergleichsform(neu)
        # Nur die Schreibweise anders ("elden ring" -> "Elden Ring"): Auf
        # Windows und macOS "gibt" es das Ziel schon - es ist die Datei
        # selbst. Das ist kein Hindernis, os.rename kann das.
        if ziel != _vergleichsform(alt) and os.path.exists(neu):
            zeile["zustand"] = ZIEL_VORHANDEN
        elif ziel in vergeben:
            zeile["zustand"] = DOPPELT
        else:
            vergeben.add(ziel)
    return plan


#: Wo die Protokolle zum Rueckgaengigmachen liegen - im Einstellungsordner.
PROTOKOLL_MUSTER = "umbenannt_%s.json"


def _protokoll_schreiben(ordner: str, paare: list[tuple[str, str]]) -> str:
    """Legt das Protokoll eines Laufs ab - ohne es kann niemand zurueck."""
    os.makedirs(ordner, exist_ok=True)
    marke = time.strftime("%Y%m%d-%H%M%S")
    pfad = os.path.join(ordner, PROTOKOLL_MUSTER % marke)
    nummer = 1
    while os.path.exists(pfad):
        nummer += 1
        pfad = os.path.join(ordner, PROTOKOLL_MUSTER % ("%s-%d" % (marke, nummer)))
    zwischen = pfad + ".tmp"
    with io.open(zwischen, "w", encoding="utf-8") as datei:
        json.dump({"zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "paare": [[alt, neu] for alt, neu in paare]},
                  datei, ensure_ascii=False, indent=1)
    os.replace(zwischen, pfad)
    return pfad


def umbenennen_ausfuehren(plan: Iterable[dict], protokoll_ordner: str,
                          umbenennen: Callable[[str, str], None] | None = None
                          ) -> dict[str, Any]:
    """Benennt um, was im Plan bereit und gewaehlt ist.

    Direkt davor wird noch einmal nachgesehen: Zwischen Plan und Ausfuehren
    kann jemand eine Datei gleichen Namens angelegt haben, und
    ``os.rename`` ueberschreibt unter Linux ohne Frage.

    Args:
        plan: Aus :func:`umbenennen_planen`; ``gewaehlt`` (Vorgabe True)
            nimmt einzelne Zeilen heraus.
        protokoll_ordner: Ablage fuer das Protokoll zum Rueckgaengigmachen.
        umbenennen: Fuer Tests; Vorgabe ``os.rename``.

    Returns:
        ``{"erledigt": [(alt, neu)], "fehler": [(alt, text)], "protokoll": pfad}``.
    """
    tun = umbenennen or os.rename
    erledigt: list[tuple[str, str]] = []
    fehler: list[tuple[str, str]] = []
    for zeile in plan:
        if zeile.get("zustand") != BEREIT or not zeile.get("gewaehlt", True):
            continue
        alt, neu = str(zeile["alt"]), str(zeile["neu"])
        if (_vergleichsform(alt) != _vergleichsform(neu)
                and os.path.exists(neu)):
            fehler.append((alt, ZIEL_VORHANDEN))
            continue
        try:
            tun(alt, neu)
        except OSError as exc:
            fehler.append((alt, str(exc)))
            continue
        erledigt.append((alt, neu))
    protokoll = ""
    if erledigt:
        try:
            protokoll = _protokoll_schreiben(protokoll_ordner, erledigt)
        except OSError as exc:
            log.warning("Umbenennen: Protokoll nicht schreibbar (%s)", exc)
    return {"erledigt": erledigt, "fehler": fehler, "protokoll": protokoll}


def protokolle(ordner: str) -> list[str]:
    """Die Protokolle, die sich noch rueckgaengig machen lassen - neueste zuerst."""
    try:
        namen = [n for n in os.listdir(ordner)
                 if n.startswith("umbenannt_") and n.endswith(".json")]
    except OSError:
        return []
    return [os.path.join(ordner, n) for n in sorted(namen, reverse=True)]


def rueckgaengig(protokoll: str,
                 umbenennen: Callable[[str, str], None] | None = None
                 ) -> dict[str, Any]:
    """Macht einen Lauf rueckgaengig - in umgekehrter Reihenfolge.

    Zurueck geht nur, was noch unter dem neuen Namen liegt und dessen alter
    Name frei ist; alles andere steht danach in ``fehler``. Das Protokoll
    bekommt die Endung ``.erledigt``, damit es nicht ein zweites Mal
    angeboten wird.
    """
    tun = umbenennen or os.rename
    with io.open(protokoll, encoding="utf-8") as datei:
        daten = json.load(datei)
    paare = [(str(a), str(n)) for a, n in (daten.get("paare") or [])]
    erledigt: list[tuple[str, str]] = []
    fehler: list[tuple[str, str]] = []
    for alt, neu in reversed(paare):
        if not os.path.exists(neu):
            fehler.append((neu, FEHLT))
            continue
        if (_vergleichsform(alt) != _vergleichsform(neu)
                and os.path.exists(alt)):
            fehler.append((alt, ZIEL_VORHANDEN))
            continue
        try:
            tun(neu, alt)
        except OSError as exc:
            fehler.append((neu, str(exc)))
            continue
        erledigt.append((neu, alt))
    try:
        os.replace(protokoll, protokoll + ".erledigt")
    except OSError as exc:
        log.debug("Umbenennen: Protokoll %s nicht abgelegt (%s)", protokoll, exc)
    return {"erledigt": erledigt, "fehler": fehler}


# ---------------------------------------------------------------------------
# Der Bildspeicher
# ---------------------------------------------------------------------------

class Bildspeicher:
    """Hält einmal geöffnete Titelbilder auf der Platte fest.

    **Warum das sein muss:** Ein Titelbild aus einer ``.ffpfsc`` zu holen
    heißt, den Container zu öffnen. Bei fünfzig Titeln dauert das Minuten -
    und ohne Speicher beim nächsten Öffnen der Bibliothek wieder. Der
    vorhandene ``_preview_cache`` des Hauptfensters liegt nur im
    Arbeitsspeicher und ist mit dem Programm weg.

    Der Schlüssel ist Pfad **plus** Änderungszeit und Größe: Wird eine Datei
    ersetzt, gilt das alte Bild nicht mehr. Ein Schlüssel allein aus dem Pfad
    hätte nach jedem Neubau das Bild des Vorgängers gezeigt.
    """

    #: Ältere Einträge werden beim Aufräumen weggeworfen.
    MAX_ALTER_TAGE: int = 90

    def __init__(self, ordner: str) -> None:
        self._ordner = ordner
        self._verzeichnis = os.path.join(ordner, "index.json")
        self._index: dict[str, dict[str, Any]] = {}
        self._geladen = False
        # Die Bildlader der Bibliothek laufen in Faeden. Bis v1.9.24 schrieben
        # zeitweise zwei zugleich (Rechner und Konsole) ohne Sperre in dasselbe
        # Verzeichnis und ueber dieselbe .tmp-Datei.
        self._sperre = threading.RLock()

    # -- innen ---------------------------------------------------------
    def _laden(self) -> None:
        if self._geladen:
            return
        self._geladen = True
        try:
            with io.open(self._verzeichnis, encoding="utf-8") as f:
                daten = json.load(f)
            if isinstance(daten, dict):
                self._index = {k: v for k, v in daten.items() if isinstance(v, dict)}
        except (OSError, ValueError) as exc:
            log.debug("Bildspeicher: Verzeichnis nicht lesbar (%s)", exc)
            self._index = {}

    def _schreiben(self) -> None:
        try:
            os.makedirs(self._ordner, exist_ok=True)
            zwischen = self._verzeichnis + ".tmp"
            with io.open(zwischen, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False)
            os.replace(zwischen, self._verzeichnis)
        except OSError as exc:
            log.debug("Bildspeicher: Verzeichnis nicht schreibbar (%s)", exc)

    @staticmethod
    def schluessel(pfad: str) -> str:
        """Pfad **und** Stand der Datei - sonst zeigt der Speicher Altes.

        Ein Container, der neu gebaut wurde, liegt unter demselben Pfad. Ohne
        Änderungszeit und Größe im Schlüssel bekäme er das Titelbild seines
        Vorgängers.
        """
        try:
            zustand = os.stat(pfad)
            marke = "%d:%d" % (int(zustand.st_mtime), int(zustand.st_size))
        except OSError:
            marke = "?"
        roh = "%s|%s" % (os.path.abspath(pfad), marke)
        return hashlib.sha1(roh.encode("utf-8", "replace")).hexdigest()

    # -- außen ---------------------------------------------------------
    def lesen(self, pfad: str) -> str:
        """Liefert den Dateipfad des gespeicherten Bildes, oder ""."""
        with self._sperre:
            self._laden()
            eintrag = self._index.get(self.schluessel(pfad))
            if not eintrag:
                return ""
            bild = os.path.join(self._ordner, str(eintrag.get("datei", "")))
            if not os.path.isfile(bild):
                return ""
            return bild

    def kennt_ohne_bild(self, pfad: str) -> bool:
        """True, wenn schon nachgesehen wurde und es kein Bild gab.

        Ohne diese Auskunft öffnet die Bibliothek bei jedem Aufschlagen
        wieder jeden Container, der gar kein Titelbild trägt - und das sind
        die teuersten Fälle, weil dabei alles durchsucht wird.

        Gefragt wird nach dem **Feld** ``datei``: Seit dem 25.09.2026 kann
        ein Eintrag auch nur Angaben tragen (:meth:`angaben_schreiben`), und
        der hat gar nicht nach einem Bild gesucht.
        """
        with self._sperre:
            self._laden()
            eintrag = self._index.get(self.schluessel(pfad))
            return bool(eintrag) and "datei" in eintrag and not eintrag["datei"]

    def schreiben(self, pfad: str, bilddaten: bytes | None,
                  endung: str = "png") -> str:
        """Legt ein Titelbild ab. ``None`` merkt sich "hat keines"."""
        with self._sperre:
            self._laden()
            kennung = self.schluessel(pfad)
            # Was schon zum Eintrag gehoert (die Angaben), bleibt stehen.
            vorher = dict(self._index.get(kennung) or {})
            if bilddaten is None:
                vorher.update(datei="", zeit=time.time())
                self._index[kennung] = vorher
                self._schreiben()
                return ""
            name = "%s.%s" % (kennung, endung.lstrip("."))
            ziel = os.path.join(self._ordner, name)
            try:
                os.makedirs(self._ordner, exist_ok=True)
                with io.open(ziel, "wb") as f:
                    f.write(bilddaten)
            except OSError as exc:
                log.debug("Bildspeicher: %s nicht schreibbar (%s)", ziel, exc)
                return ""
            vorher.update(datei=name, zeit=time.time())
            self._index[kennung] = vorher
            self._schreiben()
            return ziel

    def angaben_lesen(self, pfad: str) -> dict[str, Any]:
        """Die gemerkten erweiterten Angaben zu einer Datei, oder ``{}``.

        Mindest-Firmware, SDK, Kategorie und Content-ID liegen im Abbild;
        bei einer ``.ffpfsc`` heisst sie lesen, den Container zu oeffnen.
        Gemerkt werden sie unter demselben Schluessel wie das Titelbild -
        wird die Datei ersetzt, gelten sie nicht mehr.
        """
        with self._sperre:
            self._laden()
            eintrag = self._index.get(self.schluessel(pfad)) or {}
            angaben = eintrag.get("angaben")
            return dict(angaben) if isinstance(angaben, dict) else {}

    def angaben_schreiben(self, pfad: str, angaben: dict[str, Any]) -> None:
        """Merkt die erweiterten Angaben zu einer Datei."""
        with self._sperre:
            self._laden()
            kennung = self.schluessel(pfad)
            eintrag = dict(self._index.get(kennung) or {})
            eintrag["angaben"] = {str(k): str(v) for k, v in dict(angaben).items()}
            eintrag.setdefault("zeit", time.time())
            self._index[kennung] = eintrag
            self._schreiben()

    def umziehen(self, alter_schluessel: str, neuer_pfad: str) -> bool:
        """Nach dem Umbenennen: Bild und Angaben gehoeren zum neuen Namen.

        Der Schluessel haengt am Pfad. Ohne Umzug oeffnete die Bibliothek
        nach dem Umbenennen jeden Container noch einmal, nur um dasselbe
        Titelbild wieder zu holen. Den alten Schluessel muss der Aufrufer
        **vor** dem Umbenennen bilden - danach gibt es die Datei unter dem
        alten Namen nicht mehr, und :meth:`schluessel` kaeme auf etwas
        anderes.
        """
        with self._sperre:
            self._laden()
            eintrag = self._index.pop(alter_schluessel, None)
            if eintrag is None:
                return False
            self._index[self.schluessel(neuer_pfad)] = eintrag
            self._schreiben()
            return True

    def aufraeumen(self) -> int:
        """Wirft weg, was lange niemand gebraucht hat. Liefert die Anzahl."""
        with self._sperre:
            self._laden()
            grenze = time.time() - self.MAX_ALTER_TAGE * 86400
            weg = [k for k, v in self._index.items()
                   if float(v.get("zeit", 0) or 0) < grenze]
            for k in weg:
                datei = str(self._index[k].get("datei", ""))
                if datei:
                    try:
                        os.remove(os.path.join(self._ordner, datei))
                    except OSError:
                        pass
                del self._index[k]
            if weg:
                self._schreiben()
            return len(weg)
