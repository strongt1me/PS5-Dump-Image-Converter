# -*- coding: utf-8 -*-
"""Attrappen fuer die Tests des Host-Downloads (kein Test selbst): eine Nachbildung des Netzes und Freigaben.

Genutzt von test_webkit_host_holen (reine Funktion) und test_webkit_seite (Klick auf der Seite).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ps5_validator.utils import werkzeug_updates as wu

QUELLE = "itsPLK/ps5-webkit-autoloader"
BASIS_ADRESSE = "https://github.com/itsPLK/ps5-webkit-autoloader/releases/download/"


def inhalt(name: str) -> bytes:
    return ("Inhalt von %s" % name).encode("utf-8") * 40


def summe(name: str) -> str:
    return hashlib.sha256(inhalt(name)).hexdigest()


def freigabe(tag: str, *, ohne_summe: bool = False, ohne: tuple[str, ...] = (), adresse: str = "") -> dict:
    nummer = tag[1:]
    assets = []
    for art in ("host_v%s.exe", "host_v%s.py", "installer_v%s.elf"):
        name = "webkit-autoloader-" + (art % nummer)
        if name in ohne:
            continue
        assets.append({
            "name": name, "size": len(inhalt(name)),
            "digest": "" if ohne_summe else "sha256:" + summe(name),
            "browser_download_url": (adresse or BASIS_ADRESSE) + "%s/%s" % (tag, name)})
    return {"tag_name": tag, "name": tag, "draft": False, "prerelease": tag.count("-") > 0,
            "published_at": "2026-10-28T00:07:18Z", "html_url": "https://github.com/%s/releases/%s" % (QUELLE, tag),
            "assets": assets}


class FakeNetz:
    """Antwortet aus ``freigaben``; ``verfaelscht`` liefert andere Bytes als die Freigabe verspricht."""

    def __init__(self, freigaben, ausfall=None, status=200) -> None:
        self.freigaben = freigaben
        self.ausfall = ausfall
        self.status = status
        self.geladen: list[str] = []
        self.abgefragt = 0
        self.verfaelscht = False
        #: Wird nach dem Laden gerufen (Pfad der Datei) - etwa um den Virenschutz nachzuahmen.
        self.nach_dem_laden = None

    def abfragen(self, quelle: str, etag: str = "") -> "wu.Antwort":
        self.abgefragt += 1
        if self.ausfall is not None:
            raise self.ausfall
        if self.status != 200:
            return wu.Antwort(self.status)
        return wu.Antwort(200, json.dumps(self.freigaben), "W/\"x\"")

    def laden(self, adresse, pfad, fortschritt=None, abbruch=None, grenze=None):
        self.geladen.append(adresse)
        daten = inhalt(adresse.rsplit("/", 1)[-1])
        if self.verfaelscht:
            daten = daten[:-1] + b"X"
        Path(pfad).write_bytes(daten)
        if fortschritt is not None:
            fortschritt(len(daten) // 2, len(daten))
            fortschritt(len(daten), len(daten))
        return len(daten), hashlib.sha256(daten).hexdigest()

    def bytes(self, adresse, grenze=64 * 1024 * 1024):
        raise AssertionError("Eine Pruefsummen-Datei wurde nicht erwartet: %s" % adresse)


FREIGABEN = [freigabe("v0.6.2"), freigabe("v0.6.1"), freigabe("v0.6.0-pre-4488577"), freigabe("v0.6.0")]
