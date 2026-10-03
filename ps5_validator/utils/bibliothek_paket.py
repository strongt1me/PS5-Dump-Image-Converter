# -*- coding: utf-8 -*-
"""Kopf eines Pakets lesen: Angaben und Titelbild aus einer ``.pkg`` oder ``.fpkg`` - ohne die Datei zu laden.

Die Bibliothek zeigt auf dem Rechner auch Pakete (PS4 und PS5, echt oder als FPKG für Konsolen mit Jailbreak).
Ein Paket ist oft zehn bis hundert Gigabyte groß; gelesen werden darf davon nur ein Bruchteil. Dieses Modul
liest deshalb **nur** den Kopf, die Eintragstabelle und die wenigen unverschlüsselten Einträge, die die
Bibliothek braucht:

* ``0x1000`` - ``param.sfo`` (PS4 und PS5-Pakete mit SFO): Titel, Kennung, Fassung, Firmware, Region.
* ``0x2000`` - ``param.json`` (PS5): dasselbe in JSON.
* ``0x1200`` - ``icon0.png``: das Titelbild.

**Der Aufbau** (am 03.10.2026 an echten PS4-Paketen der Festplatte des Nutzers nachgemessen - Magic, Anzahl und
Lage der Tabelle, ``param.sfo`` und ``icon0.png`` unverschlüsselt): Ein Paket beginnt mit ``\\x7fCNT`` und einem
Kopf von 0x5A0 Byte (alles big-endian): ab 0x10 die Zahl der Einträge, ab 0x18 die Lage der Tabelle, ab 0x40 die
Content-ID. Jeder Eintrag der Tabelle ist 32 Byte: Kennung, Namensverweis, zwei Flags, Lage, Größe. Ein
verschlüsselter Eintrag trägt ``0x80000000`` in den ersten Flags und wird nicht angefasst - dieses Modul
entschlüsselt nichts. Ein PS5-Paket kann in ein ``\\x7fFIH``-Abbild gehüllt sein; dann steht die Lage des
eingebetteten Kopfs bei FIH+0x58 (little-endian). Dieselben Felder liest ``pkg_reader``, dort aber über die ganze
Datei - hier bleibt es bei einigen hundert Kilobyte.

Was hier **nicht** steht: Tk, Titelwahl, Zuordnung zu den Feldern der Bibliothek. Das Modul liefert Rohdaten; die
Seite macht daraus mit denselben Lesern wie für Ordner und Abbilder ihre Angaben.
"""
from __future__ import annotations

import json
import os
import struct
from typing import Any

from .logger import get_logger

log = get_logger(__name__)

CNT_MAGIC = b"\x7fCNT"
FIH_MAGIC = b"\x7fFIH"

#: Größe des CNT-Kopfs (``pkg_reader.HEADER_SIZE``).
KOPF_GROESSE = 0x5A0
EINTRAG_GROESSE = 0x20
EINTRAG_VERSCHLUESSELT = 0x80000000
#: Mehr Einträge hat kein Paket; eine größere Zahl heißt: kein Paketkopf.
MAX_EINTRAEGE = 0x10000

ID_PARAM_SFO = 0x1000
ID_ICON0 = 0x1200
ID_PARAM_JSON = 0x2000

#: So viel darf ein gelesener Eintrag höchstens groß sein. ``icon0.png`` hat gemessen 5 bis 450 KB,
#: ``param.sfo`` unter 10 KB; alles Größere ist kein solcher Eintrag, sondern ein falsch gelesener Kopf.
MAX_EINTRAG_BYTES = 4 * 1024 * 1024


def _u32(daten: bytes, stelle: int) -> int:
    return struct.unpack_from(">I", daten, stelle)[0]


def paket_lesen(pfad: str) -> dict[str, Any] | None:
    """Liest Content-ID, ``param.sfo``, ``param.json`` und ``icon0.png`` aus einem Paket.

    Returns:
        ``{"art": "cnt"|"fih", "content_id": str, "sfo": bytes|None, "json": dict|None,
        "icon": bytes|None}`` - oder ``None``, wenn die Datei kein lesbares Paket ist (keine bekannte
        Magic, ein Kopf, der in sich nicht stimmt, ein abgeschnittenes Paket). Nie eine Ausnahme: Eine
        Bibliothek, die an einer kaputten Datei scheitert, zeigt gar nichts.
    """
    try:
        groesse = os.path.getsize(pfad)
        with open(pfad, "rb") as f:
            kopf = f.read(0x100)
            if len(kopf) < 0x100:
                return None
            art = "cnt"
            basis = 0
            if kopf[:4] == FIH_MAGIC:
                art = "fih"
                basis = struct.unpack_from("<Q", kopf, 0x58)[0]
                if basis <= 0 or basis + KOPF_GROESSE > groesse:
                    return None
            elif kopf[:4] != CNT_MAGIC:
                return None
            f.seek(basis)
            cnt = f.read(KOPF_GROESSE)
            if len(cnt) < KOPF_GROESSE or cnt[:4] != CNT_MAGIC:
                return None
            anzahl = _u32(cnt, 0x10)
            tabelle = _u32(cnt, 0x18)
            if not 0 < anzahl <= MAX_EINTRAEGE:
                return None
            if basis + tabelle + anzahl * EINTRAG_GROESSE > groesse:
                return None
            inhalt_id = cnt[0x40:0x70].split(b"\x00", 1)[0].decode("ascii", errors="replace")
            f.seek(basis + tabelle)
            rohe = f.read(anzahl * EINTRAG_GROESSE)
            if len(rohe) < anzahl * EINTRAG_GROESSE:
                return None

            gewollt = {ID_PARAM_SFO, ID_ICON0, ID_PARAM_JSON}
            gelesen: dict[int, bytes] = {}
            for nummer in range(anzahl):
                eintrag = rohe[nummer * EINTRAG_GROESSE:(nummer + 1) * EINTRAG_GROESSE]
                kennung, _namen, flags1, _flags2, lage, laenge = struct.unpack(">IIIIII", eintrag[:24])
                if kennung not in gewollt or kennung in gelesen:
                    continue
                if flags1 & EINTRAG_VERSCHLUESSELT or not 0 < laenge <= MAX_EINTRAG_BYTES:
                    continue
                if basis + lage + laenge > groesse:
                    continue
                f.seek(basis + lage)
                daten = f.read(laenge)
                if len(daten) == laenge:
                    gelesen[kennung] = daten
    except (OSError, struct.error, ValueError) as exc:
        log.debug("Paket %s nicht lesbar (%s)", pfad, exc)
        return None

    angaben_json: dict | None = None
    if ID_PARAM_JSON in gelesen:
        try:
            geladen = json.loads(gelesen[ID_PARAM_JSON].decode("utf-8", errors="strict").rstrip("\x00"))
            angaben_json = geladen if isinstance(geladen, dict) else None
        except (ValueError, UnicodeDecodeError):
            angaben_json = None
    return {"art": art, "content_id": inhalt_id, "sfo": gelesen.get(ID_PARAM_SFO),
            "json": angaben_json, "icon": gelesen.get(ID_ICON0)}
