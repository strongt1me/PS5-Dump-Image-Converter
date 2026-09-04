# -*- coding: utf-8 -*-
"""Der eingebettete PS4-Weg: PS4-Pakete nach ffpfsc wandeln.

Neunter Schnitt der Trennung. Sechs Methoden, die den mitgelieferten
PS4-FFPFSC-Auszug ansteuern: Quellen sichten, die Konsole am Titel
erkennen, das Ergebnis finden, das entstandene Abbild pruefen, den Aufruf
bauen und ihn ausfuehren.

Ein besonders sauberer Block - er brauchte von aussen nur fuenf Konstanten
und eine einzige fremde Methode, und alle seine Aufrufer sitzen in einem
einzigen Fenster (``_show_ps4_pkg_converter``).

**Eine Falle steckte doch darin.** ``befehl()`` baute den Selbstaufruf mit
``os.path.abspath(__file__)`` - gemeint war die Hauptdatei des Programms.
Aus ``ps5_validator/utils/`` heraus zeigt ``__file__`` auf dieses Modul,
und der Aufruf ginge ins Leere. Der Pfad kommt deshalb als Parameter
herein; die Weiterleitung im Monolithen reicht ihr eigenes ``__file__``.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import struct
import subprocess
import sys
from typing import Callable

from ps5_validator.utils.plattform import prozess_flags

logger = logging.getLogger("PS5Converter.utils.ps4_werkzeug")

#: Womit die Title-IDs der jeweiligen Konsole anfangen.
PS4_KENNUNGEN: tuple[str, ...] = ("CUSA", "PUSA")
PS5_KENNUNGEN: tuple[str, ...] = ("PPSA", "PPSS", "PPUS", "PPJP")

#: Dateien, an denen ein PS4-Abbild zu erkennen ist.
PS4_MERKMALE: tuple[str, ...] = ("manifest_nonufsfiles_ps4.txt",
                                 "sce_discmap.plt")

#: Was in einem vollstaendigen PS4-Abbild liegen sollte.
PS4_EMPFOHLENE_DATEIEN: tuple[str, ...] = ("sce_sys/pfs-version.dat",)

#: Endungen, die als Ergebnis in Frage kommen.
PS4_ABBILD_ENDUNGEN: tuple[str, ...] = (".ffpfsc", ".ffpfs", ".exfat",
                                        ".ffpkg")

#: Praefix, mit dem das PS4-Werkzeug seine Fortschrittsmeldungen
#: kennzeichnet (JSON je Zeile auf stderr, siehe dort
#: pipeline.PROGRESS_PREFIX).
PROGRESS_PREFIX = "PS4FFPSC_PROGRESS "


def quellen_sichten(eingabe: str, art: str,
                    konsole_erkennen: Callable[[str], str]) -> dict:
    """Zaehlt in der gewaehlten Quelle die Pakete je Konsole.

    Args:
        eingabe: Der eingetippte Pfad; bei einzelnen Dateien mehrere,
            getrennt durch ``os.pathsep``.
        art: ``"pkg_file"``, ``"pkg_dir"`` oder ``"dump_dir"``.

    Returns:
        ``{"ps4": [...], "ps5": [...], "fremd": [...]}`` mit den
        Dateinamen - Namen, nicht Pfade, denn sie gehen ins Protokoll.
    """
    befund = {"ps4": [], "ps5": [], "fremd": []}
    pfade: list[str] = []
    if art == "pkg_file":
        pfade = [teil.strip() for teil in eingabe.split(os.pathsep)
                 if teil.strip()]
    elif os.path.isdir(eingabe):
        try:
            # Nur die Ebene selbst: Genau das nimmt das Werkzeug auch.
            for name in sorted(os.listdir(eingabe)):
                voll = os.path.join(eingabe, name)
                if name.lower().endswith(".pkg") and os.path.isfile(voll):
                    pfade.append(voll)
        except OSError as exc:
            logger.debug("Quellordner nicht lesbar: %s", exc)
    for pfad in pfade:
        konsole = konsole_erkennen(pfad)
        befund[konsole or "fremd"].append(os.path.basename(pfad))
    return befund

def plattform(title_id: str, spiel=None) -> str:
    """Sagt, zu welcher Konsole ein Titel gehoert.

    Returns:
        ``"ps4"``, ``"ps5"`` oder ``""`` wenn die Kennung nichts hergibt.
    """
    kennung = str(title_id or "").strip().upper()
    if kennung.startswith(PS5_KENNUNGEN):
        return "ps5"
    if kennung.startswith(PS4_KENNUNGEN):
        return "ps4"
    # Das Werkzeug meldet die Plattform manchmal selbst mit.
    if isinstance(spiel, dict):
        roh = str(spiel.get("platform") or spiel.get("console") or "").lower()
        if "ps5" in roh or "prospero" in roh:
            return "ps5"
        if "ps4" in roh or "orbis" in roh:
            return "ps4"
    return ""

def ergebnis_finden(ordner: str, title_id: str = "",
                              format_wunsch: str = "") -> str:
    """Sucht das eben gebaute Abbild im Ausgabeordner.

    Bis v1.8.77 bekam die Nachpruefung den **Ordner** uebergeben statt
    der Datei. Sie scheiterte dadurch jedes Mal mit
    ``[Errno 13] Permission denied`` auf dem Ordnerpfad - sie hat also
    nie stattgefunden, obwohl im Protokoll stand, dass sie laeuft.
    Gesehen am 21.08.2026 an einer echten Konvertierung.

    Args:
        ordner: Der Ausgabeordner.
        title_id: Wenn bekannt, wird ein Treffer mit dieser Kennung
            bevorzugt - im selben Ordner koennen aeltere Abbilder liegen.
        format_wunsch: Das gewaehlte Zielformat, ebenfalls als Vorzug.

    Returns:
        Der Pfad, oder "" wenn nichts Passendes dasteht.
    """
    endungen = list(PS4_ABBILD_ENDUNGEN)
    wunsch = "." + str(format_wunsch or "").lstrip(".").lower()
    if wunsch in endungen:
        endungen.remove(wunsch)
        endungen.insert(0, wunsch)
    kennung = str(title_id or "").upper()
    kandidaten = []
    try:
        for name in os.listdir(ordner):
            pfad = os.path.join(ordner, name)
            if not os.path.isfile(pfad):
                continue
            klein = name.lower()
            passende = [e for e in endungen if klein.endswith(e)]
            if not passende:
                continue
            kandidaten.append((
                0 if kennung and kennung in name.upper() else 1,
                endungen.index(passende[0]),
                -os.path.getmtime(pfad),
                pfad,
            ))
    except OSError as exc:
        logger.debug("Ausgabeordner nicht lesbar: %s", exc)
        return ""
    if not kandidaten:
        return ""
    kandidaten.sort()
    return kandidaten[0][3]

def abbild_pruefen(pfad: str) -> dict:
    """Sieht in ein fertiges Abbild hinein, ohne es zu entpacken.

    Gelesen werden nur die Verzeichnisbloecke des inneren exFAT, nicht
    die Nutzdaten - bei einem 8,7-GB-Abbild sind das wenige Sekunden.

    Args:
        pfad: Das erzeugte ``.ffpfsc`` oder ``.exfat``.

    Returns:
        ``{"dateien": int, "fehlend": [...], "ps4": bool, "fehler": str}``.
    """
    ergebnis = {"dateien": 0, "fehlend": [], "ps4": False, "fehler": ""}
    griff = None
    try:
        from mkpfs.exfat import ExfatReader

        with open(pfad, "rb") as datei:
            kopf = datei.read(16)
        if len(kopf) >= 12 and struct.unpack_from("<I", kopf, 0x08)[0] == 0x1332A0B:
            from mkpfs import pfs as mkpfs_pfs

            geoeffnet = mkpfs_pfs.open_inner_file_view(pathlib.Path(pfad))
            if not geoeffnet:
                ergebnis["fehler"] = "Innenebene nicht lesbar"
                return ergebnis
            sicht, griff, _name = geoeffnet
        else:
            sicht = griff = open(pfad, "rb")

        sicht.seek(0)
        leser = ExfatReader(sicht)
        namen = [e.rel_path.replace("\\", "/").lower()
                 for e in leser.iter_files()]
        ergebnis["dateien"] = len(namen)
        vorhanden = set(namen)
        ergebnis["fehlend"] = [d for d in PS4_EMPFOHLENE_DATEIEN
                               if d.lower() not in vorhanden]
        ergebnis["ps4"] = any(m in vorhanden for m in PS4_MERKMALE)
    except Exception as exc:                      # noqa: BLE001 - melden
        ergebnis["fehler"] = str(exc)[:160]
    finally:
        try:
            if griff is not None:
                griff.close()
        except Exception:
            pass
    return ergebnis

def befehl(hauptdatei: str = "") -> list[str]:
    """Baut den Aufruf für die eingebettete PS4-Kommandozeile.

    Als eingefrorene Anwendung ruft sich das Programm selbst mit dem
    internen Schalter auf; aus der Quelle heraus wird die Hauptdatei an
    denselben Schalter gehängt.

    Returns:
        Die Befehlsliste ohne die eigentlichen Unterbefehle.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ps4ffpsc"]
    return [sys.executable, os.path.abspath(hauptdatei), "--ps4ffpsc"]

def lauf(
    argumente: list[str],
    *,
    arbeitsordner: str,
    zeile_callback,
    fortschritt_callback=None,
    prozess_ablage: dict | None = None,
    json_modus: bool = False,
    hauptdatei: str = "",
    umgebung_bauen: Callable[[str], dict] | None = None,
) -> tuple[int, str]:
    """Führt einen PS4-FFPFSC-Unterbefehl aus und meldet Zeilen zurück.

    stderr wird in stdout geführt: Das Werkzeug schreibt seine
    Fortschrittsmeldungen (``PS4FFPSC_PROGRESS {…}``) dorthin, sein
    Protokoll ebenso. Getrennt zu lesen bräuchte zwei Lesefäden, ohne
    etwas zu gewinnen - die Reihenfolge bliebe trotzdem ungewiss.

    Args:
        argumente:            Unterbefehl samt Schaltern.
        arbeitsordner:        Ordner für Zwischenstände des Werkzeugs.
        zeile_callback:       Bekommt jede Protokollzeile.
        fortschritt_callback: Bekommt die entschlüsselten Fortschrittsdaten.
        prozess_ablage:       Nimmt den laufenden Prozess auf, damit ein
                              Abbruch ihn beenden kann.
        json_modus:           Haelt stderr getrennt, damit auf stdout reines
                              JSON steht. Fuer --json-Abfragen noetig.

    Returns:
        ``(Rückgabewert, gesammelte Ausgabe)``.
    """
    # Eigener Name fuer das Ergebnis: hiesse die Liste wieder "befehl",
    # waere der Name in dieser Funktion lokal, und der Aufruf rechts
    # daneben traefe nicht mehr die Modulfunktion darueber, sondern die
    # eigene, noch unbelegte Variable - UnboundLocalError, 04.09.2026.
    befehlsliste = [*befehl(hauptdatei), *argumente]
    gesammelt: list[str] = []
    prozess = subprocess.Popen(
        befehlsliste,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if json_modus else subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=umgebung_bauen(arbeitsordner),
        **prozess_flags(),
    )
    if prozess_ablage is not None:
        prozess_ablage["prozess"] = prozess
    if json_modus:
        # stdout bleibt unangetastet, damit die Antwort als Ganzes lesbar
        # ist; das Protokoll kommt getrennt ueber stderr.
        stdout_text, stderr_text = prozess.communicate()
        for zeile in (stderr_text or "").splitlines():
            text = zeile.rstrip()
            if text.startswith(PROGRESS_PREFIX):
                continue
            if text.strip():
                zeile_callback(text)
        return int(prozess.returncode or 0), stdout_text or ""
    try:
        for zeile in prozess.stdout or []:
            text = zeile.rstrip("\r\n")
            if text.startswith(PROGRESS_PREFIX):
                if fortschritt_callback is not None:
                    try:
                        fortschritt_callback(
                            json.loads(text[len(PROGRESS_PREFIX):])
                        )
                    except (ValueError, TypeError) as exc:
                        logger.debug("PS4-Fortschritt nicht lesbar: %s", exc)
                continue
            gesammelt.append(text)
            if text.strip():
                zeile_callback(text)
    finally:
        prozess.wait()
    return int(prozess.returncode or 0), "\n".join(gesammelt)
