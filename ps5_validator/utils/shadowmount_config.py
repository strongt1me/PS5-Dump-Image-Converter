# -*- coding: utf-8 -*-
"""ShadowMount+ ab 1.7beta12: die ``config.ini`` in Abschnitten (Format 2) samt ``profiles.ini``.

**Was sich mit 1.7beta12 aendert** (Quelltext ``src/sm_config_file.c``, ``config.ini.example`` und
``profiles.ini.example`` der Vorabfassung vom 08.11.2026 gelesen, Diff gegen beta11):

* Die ``config.ini`` hat Abschnitte (``[general]``, ``[api]``, ``[scan]``, ``[mount]``, ``[library]``,
  ``[fakelib]``, ``[emulators]``, ``[fan]``, ``[sectors]``, ``[smb:NAME]``) und beginnt mit ``[config]``
  ``version = 2``. Die Schluessel heissen anders (``update_emulators`` wird ``[emulators] update_enabled``,
  ``scanpath`` wird ``[scan] path``, ``mount_read_only=1`` wird ``[mount] mode = ro``).
* Einstellungen je Spiel und je Abbild stehen nicht mehr in der ``config.ini``, sondern in ``profiles.ini``
  (``[game:PPSA…] fakelib = …``, ``ignore_global_fakelib``; ``[image:Name.exfat] mount_mode``, ``sector_size``).
* Beim ersten Start der neuen Fassung wandelt ShadowMount+ eine alte Datei selbst um (Sicherung in
  ``config-v1-backup/``). ``autotune.ini`` und ``smb.json`` entfallen.

**Wie das Programm damit umgeht.** Es denkt in den Schluesselnamen der alten Fassung (``update_emulators``,
``backport_fakelib`` …). Dieses Modul legt die Uebersetzung an die Dateigrenze:

* :func:`ansicht` macht aus ``config.ini`` + ``profiles.ini`` (Format 2) einen **flachen Text in den alten
  Schluesseln** - die Ansicht. Alles, was bisher ``parse_flat_ini`` auf dem Text der Konsole tat, geht
  unveraendert weiter.
* :func:`zurueckschreiben` nimmt die geaenderte Ansicht und baut aus ihr die beiden Dateien im Format 2 -
  **nur die Unterschiede** zur Ansicht des Ausgangsstands werden eingetragen; Kommentare, Reihenfolge und
  alles, was die Ansicht nicht kennt (z. B. ``[smb:…]``), bleiben stehen.

Reine Logik, kein Netz, keine Oberflaeche.
"""
from __future__ import annotations

import re

from ps5_validator.utils.ini_config import parse_flat_ini_multi

FORMAT_V1 = "v1"
FORMAT_V2 = "v2"

CONFIG_PFAD = "/data/shadowmount/config.ini"
PROFILES_PFAD = "/data/shadowmount/profiles.ini"

#: Erste Zeile der Ansicht - ``shadowmount_generation.generation_erkennen`` wertet sie als Beleg fuer die neue Fassung.
ANSICHT_MARKE = "# shadowmount-config-format: v2 (Ansicht in den Schluesseln der Fassungen vor 1.7beta12)"

#: (Schluessel bis 1.7beta11, Abschnitt, Schluessel ab 1.7beta12) - abgeschrieben aus ``sm_config_keys[]``.
SCHLUESSEL: tuple[tuple[str, str, str], ...] = (
    ("debug", "general", "debug"),
    ("quiet_mode", "general", "quiet_mode"),
    ("library_sync_notification", "general", "library_sync_notification"),
    ("language", "general", "language"),
    ("api_enabled", "api", "enabled"),
    ("api_bind_address", "api", "bind_address"),
    ("api_port", "api", "port"),
    ("scan_depth", "scan", "depth"),
    ("scanpath", "scan", "path"),
    ("scan_interval_seconds", "scan", "interval_seconds"),
    ("stability_wait_seconds", "scan", "stability_wait_seconds"),
    ("mount_read_only", "mount", "mode"),
    ("force_mount", "mount", "force"),
    ("persistent_image_mounts", "mount", "persistent_images"),
    ("exfat_backend", "mount", "exfat_backend"),
    ("ufs_backend", "mount", "ufs_backend"),
    ("nested_pfs_index_cache", "mount", "nested_pfs_index_cache"),
    ("app_install_all", "library", "install_all"),
    ("auto_remove_missing_games", "library", "remove_missing"),
    ("auto_remove_games_with_dlc", "library", "remove_with_dlc"),
    ("auto_remove_missing_delay_seconds", "library", "remove_delay_seconds"),
    ("backport_fakelib", "fakelib", "enabled"),
    ("fakelib_default_mode", "fakelib", "default_mode"),
    ("global_fakelib", "fakelib", "global_enabled"),
    ("global_fakelib_path", "fakelib", "global_path"),
    ("global_fakelib_priority", "fakelib", "global_priority"),
    ("update_emulators", "emulators", "update_enabled"),
    ("emulators_path", "emulators", "path"),
    ("auto_update_ampr", "emulators", "auto_update_ampr"),
    ("ampr_update_url", "emulators", "ampr_update_url"),
    ("fan_target_temperature", "fan", "target_temperature"),
    ("lvd_exfat_sector_size", "sectors", "lvd_exfat"),
    ("lvd_ufs_sector_size", "sectors", "lvd_ufs"),
    ("lvd_pfs_sector_size", "sectors", "lvd_pfs"),
    ("md_exfat_sector_size", "sectors", "md_exfat"),
    ("md_ufs_sector_size", "sectors", "md_ufs"),
)

_NACH_V2 = {alt: (abschnitt, neu) for alt, abschnitt, neu in SCHLUESSEL}
_NACH_V1 = {(abschnitt, neu): alt for alt, abschnitt, neu in SCHLUESSEL}

#: Schluessel mit Ja/Nein-Wert. Geschrieben wird ``on``/``off`` (das Format 2 nimmt auch 1/0, true/false, yes/no).
_WAHRHEITSWERTE = frozenset({
    "debug", "quiet_mode", "library_sync_notification", "api_enabled", "force_mount", "persistent_image_mounts",
    "nested_pfs_index_cache", "app_install_all", "auto_remove_missing_games", "auto_remove_games_with_dlc",
    "backport_fakelib", "global_fakelib", "update_emulators", "auto_update_ampr",
})
_AN = ("1", "true", "yes", "on")
_AUS = ("0", "false", "no", "off")

#: Schluessel, die in ``profiles.ini`` stehen (Format 2) und in der Ansicht so heissen wie bisher.
PROFIL_SCHLUESSEL = ("fakelib_mode", "fakelib_exclude", "global_fakelib_exclude", "image_ro", "image_rw", "image_sector")

#: Alle Schluessel, die das Format 2 kennt - die Ansicht enthaelt nur diese.
BEKANNT = frozenset(_NACH_V2) | frozenset(PROFIL_SCHLUESSEL)

_FAKELIB_MODI = ("default", "full", "emulators", "disabled")
#: Kopfzeile ``[Name]``. Gierig bis zur letzten ``]``: Abbildnamen duerfen Klammern tragen (``[image:Spiel [v1].exfat]``).
_KOPF = re.compile(r"^\s*\[(.+)\]\s*(?:[#;].*)?$")
_SCHLUESSELZEILE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=(.*)$")


# --------------------------------------------------------------------------------------------------- erkennen
def format_erkennen(text: str) -> str:
    """``FORMAT_V2``, wenn die Datei Abschnitte hat, ``FORMAT_V1`` bei flachen Schluesseln, sonst ``""``.

    ``""`` heisst: nichts Aktives drin (leer oder nur Kommentare, so liefert ShadowMount+ seine Vorlage aus).
    Dann beweist die Datei nichts, und die Wahl des Anwenders gilt.
    """
    flach = False
    for zeile in (text or "").splitlines():
        s = zeile.strip()
        if not s or s[0] in "#;":
            continue
        if _KOPF.match(zeile):
            return FORMAT_V2
        if "=" in s:
            flach = True
    return FORMAT_V1 if flach else ""


# --------------------------------------------------------------------------------------------------- lesen
def _wert_lesen(roh: str) -> str:
    roh = roh.strip()
    if roh.startswith('"'):
        aus: list[str] = []
        i = 1
        while i < len(roh):
            zeichen = roh[i]
            if zeichen == "\\" and i + 1 < len(roh):
                aus.append(roh[i + 1])
                i += 2
                continue
            if zeichen == '"':
                break
            aus.append(zeichen)
            i += 1
        return "".join(aus)
    treffer = re.search(r"[#;]", roh)
    return (roh[:treffer.start()] if treffer else roh).strip()


def _wert_schreiben(wert: str) -> str:
    """Wert fuer die Datei: in Anfuehrungszeichen, wenn ``#``, ``;``, ``"`` oder Randleerzeichen vorkommen."""
    if wert != wert.strip() or any(z in wert for z in '#;"') or wert == "":
        return '"' + wert.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return wert


def eintraege(text: str) -> list[tuple[str, str, str]]:
    """Alle aktiven ``(Abschnitt, Schluessel, Wert)`` einer Datei im Format 2, in Dateireihenfolge."""
    abschnitt = ""
    ergebnis: list[tuple[str, str, str]] = []
    for zeile in (text or "").splitlines():
        s = zeile.strip()
        if not s or s[0] in "#;":
            continue
        kopf = _KOPF.match(zeile)
        if kopf:
            abschnitt = kopf.group(1).strip()
            continue
        treffer = _SCHLUESSELZEILE.match(zeile)
        if treffer:
            ergebnis.append((abschnitt, treffer.group(1), _wert_lesen(treffer.group(2))))
    return ergebnis


def _wahrheit(wert: str) -> "bool | None":
    klein = wert.strip().lower()
    if klein in _AN:
        return True
    if klein in _AUS:
        return False
    return None


def ansicht(config_text: str, profiles_text: str = "") -> str:
    """Der Zustand der Konsole als flacher Text in den **alten** Schluesseln.

    Nur Aktives kommt hinein. ``[mount] mode`` wird zu ``mount_read_only`` (1/0), ``[scan] path`` zu einer
    ``scanpath``-Zeile je Pfad, die Profile zu ``fakelib_mode=<ID>:<Modus>``, ``global_fakelib_exclude=<ID>``,
    ``image_ro``/``image_rw=<Name>`` und ``image_sector=<Name>:<Groesse>``. ``[smb:…]`` und ``[config]`` fehlen.
    """
    zeilen = [ANSICHT_MARKE]
    werte: dict[tuple[str, str], list[str]] = {}
    for abschnitt, schluessel, wert in eintraege(config_text):
        werte.setdefault((abschnitt.lower(), schluessel.lower()), []).append(wert)
    for alt, abschnitt, neu in SCHLUESSEL:
        for wert in werte.get((abschnitt, neu), []):
            if alt == "mount_read_only":
                wert = "1" if wert.strip().lower() == "ro" else "0" if wert.strip().lower() == "rw" else wert
            zeilen.append("%s=%s" % (alt, wert))
    spiele: list[str] = []
    abbilder: list[str] = []
    for abschnitt, schluessel, wert in eintraege(profiles_text):
        art, _, name = abschnitt.partition(":")
        art = art.strip().lower()
        name = name.strip()
        schluessel = schluessel.lower()
        if art == "game" and name:
            if schluessel == "fakelib" and wert.strip().lower() in _FAKELIB_MODI:
                spiele.append("fakelib_mode=%s:%s" % (name, wert.strip().lower()))
            elif schluessel == "ignore_global_fakelib" and _wahrheit(wert) is True:
                spiele.append("global_fakelib_exclude=%s" % name)
        elif art == "image" and name:
            if schluessel == "mount_mode" and wert.strip().lower() in ("ro", "rw"):
                abbilder.append("image_%s=%s" % (wert.strip().lower(), name))
            elif schluessel == "sector_size" and wert.strip() and wert.strip().lower() != "default":
                abbilder.append("image_sector=%s:%s" % (name, wert.strip()))
    return "\n".join(zeilen + spiele + abbilder) + "\n"


# --------------------------------------------------------------------------------------------------- schreiben
class _Datei:
    """Eine Datei im Format 2 als Zeilenliste - bearbeitet wird gezielt, der Rest bleibt wortgleich."""

    def __init__(self, text: str) -> None:
        self.eol = "\r\n" if "\r\n" in (text or "") else "\n"
        self.geaendert = False
        self.zeilen = (text or "").splitlines()
        if not any(_KOPF.match(z) and _KOPF.match(z).group(1).strip().lower() == "config" for z in self.zeilen):
            # Neue oder fremde Datei: Versionsmarke voranstellen, wie ShadowMount+ sie schreibt.
            self.zeilen = ["[config]", "version = 2", ""] + self.zeilen

    def text(self) -> str:
        return self.eol.join(self.zeilen) + self.eol

    def _abschnitt(self, name: str) -> "tuple[int, int] | None":
        """``(Kopfzeile, Ende)`` des ersten aktiven Abschnitts ``name`` (ohne Beachtung der Gross-/Kleinschreibung)."""
        start = None
        for i, zeile in enumerate(self.zeilen):
            kopf = _KOPF.match(zeile)
            if not kopf or zeile.lstrip()[:1] in "#;":
                continue
            if start is not None:
                return start, i
            if kopf.group(1).strip().lower() == name.lower():
                start = i
        return (start, len(self.zeilen)) if start is not None else None

    def _zeilen_des(self, name: str, schluessel: str) -> "tuple[list[int], int | None, tuple[int, int] | None]":
        """Aktive Zeilen des Schluessels, eine auskommentierte Mustervorlage und der Abschnittsbereich."""
        bereich = self._abschnitt(name)
        if bereich is None:
            return [], None, None
        aktiv: list[int] = []
        muster: "int | None" = None
        for i in range(bereich[0] + 1, bereich[1]):
            zeile = self.zeilen[i]
            s = zeile.strip()
            if s[:1] in "#;":
                m = re.match(r"^\s*[#;]\s*([A-Za-z0-9_.-]+)\s*=", zeile)
                if m and m.group(1).lower() == schluessel.lower():
                    muster = i
                continue
            m = _SCHLUESSELZEILE.match(zeile)
            if m and m.group(1).lower() == schluessel.lower():
                aktiv.append(i)
        return aktiv, muster, bereich

    def setzen(self, abschnitt: str, schluessel: str, werte: list[str]) -> None:
        """Setzt die aktiven Zeilen des Schluessels auf ``werte``; leer heisst auskommentieren."""
        aktiv, muster, bereich = self._zeilen_des(abschnitt, schluessel)
        self.geaendert = True
        if not werte:
            for i in aktiv:
                self.zeilen[i] = "# " + self.zeilen[i].lstrip()
            return
        neu = ["%s = %s" % (schluessel, _wert_schreiben(w)) for w in werte]
        for i, zeile in zip(aktiv, neu):
            self.zeilen[i] = zeile
        for i in aktiv[len(neu):]:
            self.zeilen[i] = "# " + self.zeilen[i].lstrip()
        rest = neu[len(aktiv):]
        if not rest:
            return
        if aktiv:
            stelle = aktiv[min(len(aktiv), len(neu)) - 1] + 1
        elif muster is not None:
            stelle = muster + 1
        elif bereich is not None:
            stelle = bereich[1]
            while stelle > bereich[0] + 1 and not self.zeilen[stelle - 1].strip():
                stelle -= 1
        else:
            if self.zeilen and self.zeilen[-1].strip():
                self.zeilen.append("")
            self.zeilen.append("[%s]" % abschnitt)
            self.zeilen.extend(rest)
            return
        self.zeilen[stelle:stelle] = rest


def _mehrfach(text: str) -> dict[str, list[str]]:
    return parse_flat_ini_multi(text or "")


def _bool_wert(neu: str) -> str:
    wahr = _wahrheit(neu)
    return neu if wahr is None else ("on" if wahr else "off")


def _profil_schluessel(wert: str) -> "tuple[str, str]":
    name, _, rest = wert.partition(":")
    return name.strip(), rest.strip()


def zurueckschreiben(neue_ansicht: str, alte_config: str, alte_profile: str = "") -> "tuple[str, str, list[str]]":
    """Baut aus einer geaenderten Ansicht die beiden Dateien im Format 2.

    Verglichen wird mit ``ansicht(alte_config, alte_profile)``; nur Unterschiede werden eingetragen. Was die
    Ansicht nicht kennt, bleibt wortgleich.

    Returns:
        ``(config_text, profiles_text, nicht_uebernommen)`` - ``nicht_uebernommen`` nennt die Schluessel der Ansicht,
        die es im Format 2 nicht gibt (z. B. ``kstuff_delay``): Sie wurden nicht geschrieben.
    """
    alt = _mehrfach(ansicht(alte_config, alte_profile))
    neu = _mehrfach(neue_ansicht)
    config = _Datei(alte_config)
    profile = _Datei(alte_profile)
    uebergangen: list[str] = []
    for schluessel in sorted(set(alt) | set(neu)):
        vorher, nachher = alt.get(schluessel, []), neu.get(schluessel, [])
        if vorher == nachher:
            continue
        if schluessel in _NACH_V2:
            abschnitt, v2 = _NACH_V2[schluessel]
            if schluessel == "mount_read_only":
                werte = [("ro" if _wahrheit(w) else "rw") if _wahrheit(w) is not None else w for w in nachher]
            elif schluessel in _WAHRHEITSWERTE:
                werte = [_bool_wert(w) for w in nachher]
            else:
                werte = list(nachher)
            config.setzen(abschnitt, v2, werte)
        elif schluessel in PROFIL_SCHLUESSEL:
            _profil_anwenden(profile, schluessel, vorher, nachher)
        else:
            uebergangen.append(schluessel)
    return (config.text() if config.geaendert else alte_config,
            profile.text() if profile.geaendert else alte_profile, uebergangen)


def _profil_anwenden(profile: _Datei, schluessel: str, vorher: list[str], nachher: list[str]) -> None:
    """Uebertraegt einen Profil-Schluessel der Ansicht auf ``profiles.ini``."""
    if schluessel in ("fakelib_mode", "fakelib_exclude", "global_fakelib_exclude"):
        feld = "ignore_global_fakelib" if schluessel == "global_fakelib_exclude" else "fakelib"
        def wert_zu(eintrag: str) -> "tuple[str, str]":
            if schluessel == "fakelib_mode":
                titel, modus = _profil_schluessel(eintrag)
                return titel, modus.lower()
            return eintrag.strip(), "on" if feld == "ignore_global_fakelib" else "disabled"
        alt_map = dict(wert_zu(e) for e in vorher)
        neu_map = dict(wert_zu(e) for e in nachher)
        for titel in alt_map:
            if titel not in neu_map:
                profile.setzen("game:%s" % titel, feld, [])
        for titel, wert in neu_map.items():
            if alt_map.get(titel) != wert and titel:
                profile.setzen("game:%s" % titel, feld, [wert])
        return
    # Abbilder: image_ro / image_rw = <Name>, image_sector = <Name>:<Groesse>
    if schluessel in ("image_ro", "image_rw"):
        modus = schluessel.split("_", 1)[1]
        for name in vorher:
            if name not in nachher:
                profile.setzen("image:%s" % name.strip(), "mount_mode", [])
        for name in nachher:
            if name not in vorher and name.strip():
                profile.setzen("image:%s" % name.strip(), "mount_mode", [modus])
        return
    alt_map = dict(_profil_schluessel(e) for e in vorher)
    neu_map = dict(_profil_schluessel(e) for e in nachher)
    for name in alt_map:
        if name not in neu_map:
            profile.setzen("image:%s" % name, "sector_size", [])
    for name, groesse in neu_map.items():
        if alt_map.get(name) != groesse and name:
            profile.setzen("image:%s" % name, "sector_size", [groesse])


# --------------------------------------------------------------------------------------------------- Anzeige
#: Wie ein Schluessel der alten Fassung im Format 2 geschrieben wird (Meldungen, Editor).
_ANZEIGE: dict[str, str] = {alt: "[%s] %s" % (abschnitt, neu) for alt, abschnitt, neu in SCHLUESSEL}
_ANZEIGE.update({
    "fakelib_mode": "profiles.ini [game:ID] fakelib",
    "fakelib_exclude": "profiles.ini [game:ID] fakelib = disabled",
    "global_fakelib_exclude": "profiles.ini [game:ID] ignore_global_fakelib",
    "image_ro": "profiles.ini [image:Name] mount_mode = ro",
    "image_rw": "profiles.ini [image:Name] mount_mode = rw",
    "image_sector": "profiles.ini [image:Name] sector_size",
})
#: In Meldungstexten nur die unverwechselbaren Namen ersetzen: ``debug`` und ``language`` kommen als gewoehnliche
#: Woerter vor (debug.log, Debug-Bau), die duerfen nicht zu ``[general] debug`` werden.
_UEBERSETZBAR = tuple(sorted((k for k in _ANZEIGE if "_" in k or k == "scanpath"), key=len, reverse=True))
_MUSTER_ANZEIGE = re.compile(
    r"(?<![A-Za-z0-9_.-])(" + "|".join(re.escape(k) for k in _UEBERSETZBAR) + r")(?![A-Za-z0-9_])")


def anzeigename(schluessel: str) -> str:
    """Name eines Schluessels im Format 2 (``update_emulators`` -> ``[emulators] update_enabled``); unbekannte bleiben."""
    return _ANZEIGE.get(schluessel, schluessel)


def uebersetzen(text: str) -> str:
    """Ersetzt in einem Meldungstext die alten Schluesselnamen durch ihre Schreibweise im Format 2."""
    return _MUSTER_ANZEIGE.sub(lambda m: _ANZEIGE[m.group(1)], text or "")


def schluessel_bekannt(schluessel: str) -> bool:
    """Gibt es den Schluessel im Format 2 (config.ini oder profiles.ini)?"""
    return schluessel in BEKANNT
