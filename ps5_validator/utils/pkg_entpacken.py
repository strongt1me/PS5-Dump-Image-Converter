# -*- coding: utf-8 -*-
"""Entpackt eine PKG-Datei in einen Spielordner.

Entpackt werden **PS4-Pakete** (Magic ``\\x7FCNT``) - ueber denselben
Entpacker, den das Fenster "PS4 PKG -> ffpfsc" schon mitbringt
(``PS4FFPFSC-0.2.9/bin/ps4_pkg_extract``, aus shadPS4 gebaut). Am 21.09.2026
an Tetris Ultimate gemessen: 124 MB Paket, 12,9 s, 113 Dateien in 18 Ordnern,
``eboot.bin`` und ``sce_sys/param.sfo`` vorhanden.

**PS5-Pakete** (Magic ``\\x7FFIH``) entpackt dieses Modul nicht. Die
eingebettete LibProsperoPkg bringt zwar einen Entpacker mit, aber am
21.09.2026 scheiterte er mit beiden Fassungen (2.5.0 und 2.6.0) an allen
vier Paketen, die hier vorlagen - auch an einem, das dieselbe Bibliothek
selbst gebaut hatte ("Inner mount metadata does not start with a PS5 PFS
superblock"). Retail-Pakete sind ohnehin an die Konsole gebunden. Die
Oberflaeche erkennt ein PS5-Paket deshalb nur und sagt es.

Das Modul bindet ``i18n`` nicht ein. Es liefert Kennungen (``grund``,
``event``), die Oberflaeche uebersetzt sie.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from typing import Callable

MAGIC_PS4 = b"\x7fCNT"
MAGIC_PS5 = b"\x7fFIH"
#: PS5-Update-Paket (Delta) - Herkunft und Grenzen siehe ``pkg_reader.LIH_MAGIC``.
#: Es traegt nur Aenderungen gegenueber einem Grundpaket; allein laesst es sich
#: nicht entpacken.
MAGIC_PS5_DELTA = b"\x7fLIH"

#: Hoechstlaenge des Zielordners. Der Entpacker kennt kein "longPathAware"
#: und scheitert ab 260 Zeichen mit "Failed to write extracted PKG entry".
#: Dazu kommen ``.partial`` (8 Zeichen) waehrend des Laufs und der tiefste
#: spielinterne Pfad - an Tetris Ultimate 73 Zeichen gemessen, bei anderen
#: Titeln bis etwa 100 (siehe _PS4FFPSC_MAX_ARBEITSPFAD im Hauptmodul).
MAX_ZIELPFAD = 140

#: Alle Kennungen, die :func:`entpacken` unter ``grund`` liefern kann. Die
#: Oberflaeche braucht zu jeder ausser ``abgebrochen`` einen Text
#: ``pkgentpacken.grund_<kennung>`` (test_pkg_entpacken haelt das fest).
GRUENDE = ("ziel_existiert", "pfad_zu_lang", "abgebrochen", "kein_platz",
           "werkzeug_fehler", "unvollstaendig")

#: Windows-Rueckgabewert eines Stapelueberlaufs. Der Entpacker stuerzt so ab,
#: wenn er beim Pruefen die Pruefsumme rechnet - deshalb immer ``--fast``.
_STAPELUEBERLAUF = 0xC00000FD


def paket_art(pfad: str) -> str:
    """Liest die Konsole aus den ersten vier Bytes.

    Returns:
        ``"ps4"``, ``"ps5"``, ``"ps5_delta"`` (Update-Paket) oder ``""``
        (keine PKG oder nicht lesbar).
    """
    try:
        with open(pfad, "rb") as datei:
            magic = datei.read(4)
    except OSError:
        return ""
    if magic == MAGIC_PS4:
        return "ps4"
    if magic == MAGIC_PS5:
        return "ps5"
    if magic == MAGIC_PS5_DELTA:
        return "ps5_delta"
    return ""


def _anlauf() -> dict:
    """Gemeinsame Popen-Einstellungen: Zeilen als Text, kein Konsolenfenster."""
    anlauf: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if sys.platform == "win32":
        anlauf["creationflags"] = 0x08000000     # CREATE_NO_WINDOW
    return anlauf


def _json_zeile(zeile: str) -> dict | None:
    """Ein JSON-Objekt aus einer Ausgabezeile, sonst ``None``."""
    zeile = (zeile or "").strip()
    if not zeile.startswith("{"):
        return None
    try:
        wert = json.loads(zeile)
    except ValueError:
        return None
    return wert if isinstance(wert, dict) else None


def pruefen(entpacker: str, paket: str, zeitgrenze: float = 300.0) -> dict:
    """Fragt den Entpacker, was in dem Paket steckt - ohne zu entpacken.

    Returns:
        Das JSON des Entpackers (``supported``, ``title_id``, ``title``,
        ``kind``, ``content_id``, ``app_version``, ``entitlement_label``,
        ``size`` ...). Liefert er keines, ``{"supported": False,
        "reason": ...}``.
    """
    try:
        lauf = subprocess.run(
            [entpacker, "inspect", paket, "--json", "--fast"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=zeitgrenze, check=False,
            creationflags=0x08000000 if sys.platform == "win32" else 0)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"supported": False, "reason": str(exc)}
    for zeile in reversed((lauf.stdout or "").splitlines()):
        wert = _json_zeile(zeile)
        if wert is not None:
            return wert
    rc = lauf.returncode & 0xFFFFFFFF
    grund = (lauf.stderr or "").strip()
    if not grund:
        grund = ("stack overflow (0xC00000FD)" if rc == _STAPELUEBERLAUF
                 else "exit %d" % lauf.returncode)
    return {"supported": False, "reason": grund}


def _saeubern(text: str) -> str:
    """Ein Namensteil ohne Zeichen, die Windows im Dateinamen verbietet."""
    sauber = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", str(text or "")).strip(" .")
    return sauber[:60]


def zielordner_name(info: dict, paket: str) -> str:
    """Der Name des Ordners, in den das Paket entpackt wird.

    Basis-Spiel ``CUSA00775``, Patch ``CUSA16627_patch_01.02``, DLC
    ``CUSA16627_dlc_<Label>``. Ohne Title-ID der Dateiname des Pakets.
    """
    title_id = _saeubern(info.get("title_id", ""))
    if not title_id:
        return _saeubern(os.path.splitext(os.path.basename(paket))[0]) or "pkg"
    art = str(info.get("kind", "") or "").lower()
    if art == "patch":
        version = _saeubern(info.get("app_version", "") or info.get("version", ""))
        return "%s_patch_%s" % (title_id, version) if version else title_id + "_patch"
    if art == "dlc":
        label = _saeubern(info.get("entitlement_label", ""))
        return "%s_dlc_%s" % (title_id, label) if label else title_id + "_dlc"
    return title_id


def _teilstand_entfernen(pfad: str,
                         fortschritt: Callable[[dict], None] | None) -> None:
    """Raeumt einen halb entpackten Ordner weg und sagt es vorher an.

    Der Ordner kann bei einem grossen Paket viele Gigabyte tragen; ohne
    Ansage stuende die Anzeige waehrenddessen still.
    """
    if not os.path.isdir(pfad):
        return
    if fortschritt is not None:
        fortschritt({"event": "cleanup", "path": pfad})
    shutil.rmtree(pfad, ignore_errors=True)


def entpacken(entpacker: str, paket: str, ziel: str,
              melden: Callable[[str], None] | None = None,
              fortschritt: Callable[[dict], None] | None = None,
              prozess_ablage: dict | None = None,
              abbruch: Callable[[], bool] | None = None) -> dict:
    """Entpackt ein PS4-Paket nach ``ziel``.

    Der Entpacker schreibt zuerst nach ``<ziel>.partial``; erst ein
    vollstaendiger Lauf wird zu ``ziel`` umbenannt. Ein halber Stand bleibt
    so nie unter dem richtigen Namen liegen.

    Args:
        entpacker: Pfad zu ``ps4_pkg_extract``.
        paket: Die ``.pkg``.
        ziel: Der Ordner, der entstehen soll. Er darf noch nicht bestehen.
        melden: Bekommt jede Zeile des Entpackers, die kein Fortschritt ist.
        fortschritt: Bekommt jedes Fortschrittsereignis als dict
            (``extract_start``/``extract_progress``/``extract_complete`` mit
            ``bytes_current``, ``bytes_total``, ``files_current``,
            ``files_total``) und die eigenen Schritte ``cleanup`` und
            ``finish``.
        prozess_ablage: Nimmt den laufenden Prozess unter ``"prozess"`` auf,
            damit ein Abbruch ihn beenden kann.
        abbruch: Wird je Zeile gefragt; ``True`` beendet den Lauf.

    Returns:
        ``{"ok": bool, "grund": str, "rc": int, "dateien": int,
        "bytes": int, "ziel": str, "noetig": int, "frei": int}``.
        ``grund`` ist ``""`` bei Erfolg, sonst ``ziel_existiert``,
        ``pfad_zu_lang``, ``abgebrochen``, ``kein_platz``,
        ``werkzeug_fehler`` oder ``unvollstaendig``.
    """
    ergebnis = {"ok": False, "grund": "", "rc": 0, "dateien": 0,
                "bytes": 0, "ziel": ziel, "noetig": 0, "frei": 0}
    ziel = os.path.abspath(ziel)
    ergebnis["ziel"] = ziel
    if os.path.exists(ziel):
        ergebnis["grund"] = "ziel_existiert"
        return ergebnis
    if sys.platform == "win32" and len(ziel) > MAX_ZIELPFAD:
        ergebnis["grund"] = "pfad_zu_lang"
        return ergebnis

    teilstand = ziel + ".partial"
    _teilstand_entfernen(teilstand, fortschritt)
    os.makedirs(os.path.dirname(teilstand) or ".", exist_ok=True)

    abgeschlossen = False
    kein_platz = False
    befehl = [entpacker, "extract", paket, "--output", teilstand,
              "--json-progress"]
    with subprocess.Popen(befehl, **_anlauf()) as lauf:
        if prozess_ablage is not None:
            prozess_ablage["prozess"] = lauf
        for zeile in lauf.stdout or ():
            if abbruch is not None and abbruch():
                lauf.terminate()
                break
            ereignis = _json_zeile(zeile)
            if ereignis is None or "event" not in ereignis:
                sauber = zeile.rstrip("\r\n")
                if sauber and melden is not None:
                    melden(sauber)
                continue
            art = ereignis.get("event")
            if art == "extract_start":
                # Jetzt steht die entpackte Groesse fest. Reicht der Platz
                # nicht, gleich aufhoeren statt nach Gigabytes zu scheitern.
                noetig = int(ereignis.get("bytes_total", 0) or 0)
                try:
                    frei = shutil.disk_usage(os.path.dirname(teilstand)).free
                except OSError:
                    frei = -1
                if frei >= 0 and noetig > frei:
                    ergebnis["noetig"], ergebnis["frei"] = noetig, frei
                    kein_platz = True
                    lauf.terminate()
                    break
            elif art == "extract_complete":
                abgeschlossen = True
                ergebnis["dateien"] = int(ereignis.get(
                    "files", ereignis.get("files_current", 0)) or 0)
                ergebnis["bytes"] = int(ereignis.get("bytes_total", 0) or 0)
            if fortschritt is not None:
                fortschritt(ereignis)
        lauf.wait()
    ergebnis["rc"] = lauf.returncode

    if kein_platz:
        ergebnis["grund"] = "kein_platz"
    elif abbruch is not None and abbruch():
        ergebnis["grund"] = "abgebrochen"
    elif lauf.returncode != 0:
        ergebnis["grund"] = "werkzeug_fehler"
    elif not abgeschlossen:
        # Rueckgabe 0, aber nie "fertig" gemeldet - das ist kein Erfolg.
        ergebnis["grund"] = "unvollstaendig"
    if ergebnis["grund"]:
        _teilstand_entfernen(teilstand, fortschritt)
        return ergebnis

    os.replace(teilstand, ziel)
    if fortschritt is not None:
        fortschritt({"event": "finish", "path": ziel})
    ergebnis["ok"] = True
    return ergebnis
