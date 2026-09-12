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
        """
        self._laden()
        eintrag = self._index.get(self.schluessel(pfad))
        return bool(eintrag) and not eintrag.get("datei")

    def schreiben(self, pfad: str, bilddaten: bytes | None,
                  endung: str = "png") -> str:
        """Legt ein Titelbild ab. ``None`` merkt sich "hat keines"."""
        self._laden()
        kennung = self.schluessel(pfad)
        if bilddaten is None:
            self._index[kennung] = {"datei": "", "zeit": time.time()}
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
        self._index[kennung] = {"datei": name, "zeit": time.time()}
        self._schreiben()
        return ziel

    def aufraeumen(self) -> int:
        """Wirft weg, was lange niemand gebraucht hat. Liefert die Anzahl."""
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
