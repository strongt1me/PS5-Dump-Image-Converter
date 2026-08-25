"""Inhaltliche Pruefung und Reparatur von ``sce_sys/param.json``.

Bis v1.8.50 pruefte das Programm die Datei nur mit ``json.loads``: Sie musste
lesbar sein, mehr nicht. Damit rutschte alles durch, was syntaktisch stimmt und
trotzdem dazu fuehrt, dass die Konsole beim Einhaengen "Missing/invalid
param.json" meldet - eine Versionsnummer als Zahl statt als Zeichenkette, eine
``contentId``, die eine andere Title-ID nennt als das Feld ``titleId``, ein
fehlender Sprachblock, ein UTF-8-BOM am Dateianfang.

Dieses Modul schliesst die Luecke. Es ist bewusst als Bibliothek geschrieben
und nicht als eigenstaendiges Programm: Aufrufer sind der Bau (Aufgaben 1 und
4), der Validator (Aufgabe 8) und die Reparatur - alle drei brauchen dieselben
Befunde in derselben Form.

Drei Schweregrade, weil nicht jeder Verstoss gleich schwer wiegt:

``fehler``
    Bricht auf der Konsole. Beispiel: ``contentVersion`` als Zahl - dabei geht
    die fuehrende Null verloren, aus "01.000.000" wird 1.0.
``warnungen``
    Faellt auf, muss aber nicht scheitern. Beispiel: eine Sprache, die in
    keiner bekannten Liste steht.
``hinweise``
    Auffaellig, aber vermutlich in Ordnung. Beispiel: ein ``attribute``-Wert,
    der in keiner Dokumentation steht - es ist ein Bitfeld, da sind ungewohnte
    Kombinationen normal.

**Woher die Wertelisten stammen.** Nicht aus dem Bauch, sondern aus den
Referenzwerkzeugen unter ``PS5 SDK usw/``:

- ``LibProsperoPKG-2.5`` (``ProsperoParamEnums.cs``, ``ProsperoApplicationType.cs``)
  liefert die Schluesselnamen, die Sprach- und Laendercodes sowie die drei
  gueltigen ``applicationDrmType``-Tokens.
- ``src/HomebrewTest/sce_sys/param.json`` derselben Quelle ist eine
  vollstaendige, gueltige Datei und dient als Vorlage fuer die Reparatur.
- ``ps5-payload-sdk`` zeigt mit ``samples/install_app/FAKE02932`` das andere
  Extrem: eine Datei mit drei Feldern, die auf der Konsole laeuft. Deshalb sind
  hier nur wenige Felder harte Pflicht - der Rest ist Warnung.

Eine Falle, die diese Gegenueberstellung aufgedeckt hat: ``upgradable`` und
``demo`` sind **keine** ``applicationDrmType``-Werte, auch wenn sie oft so
notiert werden. Es sind Anwendungstypen; ``ProsperoApplicationTypes`` bildet
sie auf ``standard`` bzw. ``free`` ab. Wer sie in das Feld schreibt, bekommt
eine Datei, die kein Werkzeug der Kette akzeptiert.
"""
from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from typing import Any

from ps5_validator.utils.param_manifest import APPLICATION_DRM_TYPES

# ---------------------------------------------------------------------------
# Wertelisten (Quelle: LibProsperoPKG 2.5)
# ---------------------------------------------------------------------------
#: ``applicationDrmType``. Genau diese drei Tokens kennt die Referenz - und
#: dieselben drei fuehrt der Manifest-Editor des Programms schon laenger. Die
#: Liste wird deshalb von dort uebernommen statt hier ein zweites Mal
#: geschrieben: Zwei Wahrheiten im selben Programm waeren eine zu viel.
DRM_TYPEN = frozenset(APPLICATION_DRM_TYPES)

#: Haeufige Verwechslung: Anwendungstyp statt DRM-Token. Der Wert nennt das
#: Token, auf das die Referenz den Typ abbildet - damit kann die Reparatur den
#: Eintrag geradeziehen, statt ihn nur zu bemaengeln.
DRM_VERWECHSLUNGEN = {
    "upgradable": "standard",
    "demo": "free",
    "paid": "standard",
    "standalone": "standard",
}

#: ``applicationCategoryType``. 0 ist das native Spiel; die uebrigen Werte
#: gehoeren zu System- und Medienanwendungen.
APP_KATEGORIEN = {
    0: "Natives Spiel",
    65536: "Prospero Native Media App",
    65792: "RNPS Media App",
    66048: "Web Based Media App",
    131328: "System Built-in App",
    131584: "Big Daemon",
    16777216: "ShellUI",
    33554432: "Daemon",
    50331648: "CommonDialog",
    67108864: "ShellApp",
}

CONTENT_BADGE_TYPEN = {0: "keiner", 1: "Spiel", 2: "sonstiges"}

# Bitfelder. Dokumentiert sind nur einzelne Kombinationen; alles andere ist ein
# Hinweis, kein Fehler.
BEKANNTE_ATTRIBUTE = frozenset({0, 1, 536870912, 1073741824, 1107296256, 1644167168})
BEKANNTE_ATTRIBUTE2 = frozenset({0, 4})
BEKANNTE_ATTRIBUTE3 = frozenset({0, 4, 68, 80, 132, 4160, 262148})

#: ``gameIntent.permittedIntents[].intentType``. Die Referenz nennt zwei; die
#: uebrigen beiden tauchen in freier Wildbahn auf und gelten hier als bekannt.
INTENT_TYPEN = frozenset({
    "launchActivity",
    "joinSession",
    "launchMultiplayerActivity",
    "launchByCustomParameters",
})

#: Sprachcodes fuer ``localizedParameters``.
SPRACHEN = frozenset({
    "ja-JP", "en-US", "fr-FR", "es-ES", "de-DE", "it-IT", "nl-NL", "pt-PT",
    "ru-RU", "ko-KR", "zh-Hant", "zh-Hans", "fi-FI", "sv-SE", "da-DK", "no-NO",
    "pl-PL", "pt-BR", "es-419", "tr-TR", "en-GB", "ar-AE", "fr-CA", "cs-CZ",
    "hu-HU", "el-GR", "ro-RO", "th-TH", "vi-VN", "id-ID",
})

#: Laendercodes fuer ``ageLevel`` (ohne den Sonderschluessel ``default``).
LAENDER = (
    "AE", "AR", "AT", "AU", "BE", "BG", "BH", "BO", "BR", "CA", "CH", "CL",
    "CN", "CO", "CR", "CY", "CZ", "DE", "DK", "EC", "ES", "FI", "FR", "GB",
    "GR", "GT", "HK", "HN", "HR", "HU", "ID", "IE", "IL", "IN", "IS", "IT",
    "JP", "KR", "KW", "LB", "LU", "MT", "MX", "MY", "NI", "NL", "NO", "NZ",
    "OM", "PA", "PE", "PL", "PT", "PY", "QA", "RO", "RU", "SA", "SE", "SG",
    "SI", "SK", "SV", "TH", "TR", "TW", "UA", "US", "UY", "ZA",
)

DISC_INHALTSTYPEN = frozenset({"PS5GD", "PS5AC", "PS5GP", "PS4GD", "PS4AC", "PS4GP"})

# ---------------------------------------------------------------------------
# Pflichtfelder
# ---------------------------------------------------------------------------
# Zwei Stufen, und der Unterschied ist gemessen, nicht geraten: Die
# Beispieldatei des ps5-payload-sdk kommt mit drei Feldern aus und laeuft. Ein
# Retail-Backup traegt dagegen den vollen Satz. Wer die volle Liste als Pflicht
# erklaert, meldet jedes Homebrew faelschlich als kaputt.

#: Ohne diese Felder erkennt die Konsole gar keinen Titel.
HARTE_PFLICHTFELDER: dict[str, type] = {
    "titleId": str,
    "applicationCategoryType": int,
    "localizedParameters": dict,
}

#: Gehoert in jedes vollstaendige Paket, fehlt aber bei Homebrew regelmaessig.
WEICHE_PFLICHTFELDER: dict[str, type] = {
    "contentId": str,
    "contentVersion": str,
    "masterVersion": str,
    "conceptId": str,
    "applicationDrmType": str,
    "contentBadgeType": int,
    "attribute": int,
    "attribute2": int,
    "attribute3": int,
    "ageLevel": dict,
}

# ---------------------------------------------------------------------------
# Muster
# ---------------------------------------------------------------------------
#: Diese Felder prueft ``_versionen_pruefen`` mit eigener, genauerer Meldung.
_VERSIONSFELDER = frozenset({"contentVersion", "masterVersion",
                             "originContentVersion", "targetContentVersion"})

RE_TITLE_ID = re.compile(r"^[A-Z]{4}\d{5}$")
RE_CONTENT_ID = re.compile(r"^[A-Z]{2}\d{4}-[A-Z]{4}\d{5}_00-[A-Za-z0-9_\-]{16}$")
RE_VERSION_LANG = re.compile(r"^\d{2}\.\d{3}\.\d{3}$")
RE_VERSION_KURZ = re.compile(r"^\d{2}\.\d{2}$")
RE_HEX64 = re.compile(r"^0x[0-9A-Fa-f]{16}$")
RE_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?$")


# ---------------------------------------------------------------------------
# Befund
# ---------------------------------------------------------------------------
class Befund:
    """Ergebnis einer Pruefung: Fehler, Warnungen, Hinweise und Eckdaten."""

    def __init__(self, pfad: str = "") -> None:
        self.pfad = pfad
        self.fehler: list[str] = []
        self.warnungen: list[str] = []
        self.hinweise: list[str] = []
        self.info: "OrderedDict[str, str]" = OrderedDict()
        #: True, wenn die Datei gar nicht erst gelesen werden konnte (fehlt,
        #: kein UTF-8, kein gueltiges JSON). Dann ist Reparatur nicht moeglich,
        #: nur Neuanlage.
        self.unlesbar = False
        #: True, wenn die Datei ueberhaupt nicht existiert.
        self.fehlt = False
        #: Erkannter Typ: "base", "patch" oder "disc".
        self.art = ""

    # -- Erfassen ----------------------------------------------------------
    def fehler_melden(self, text: str) -> None:
        self.fehler.append(text)

    def warnen(self, text: str) -> None:
        self.warnungen.append(text)

    def hinweis(self, text: str) -> None:
        self.hinweise.append(text)

    # -- Auswerten ---------------------------------------------------------
    @property
    def ok(self) -> bool:
        """True, wenn kein Fehler vorliegt. Warnungen zaehlen nicht dagegen."""
        return not self.fehler

    @property
    def reparierbar(self) -> bool:
        """True, wenn sich die Datei lesen liess und Beanstandungen hat.

        Eine fehlende oder unlesbare Datei ist nicht reparierbar - sie muss neu
        angelegt werden.
        """
        return not self.fehlt and not self.unlesbar and bool(self.fehler or self.warnungen)

    def zusammenfassung(self) -> str:
        """Einzeiler fuer das Protokoll."""
        if self.fehlt:
            return "param.json fehlt"
        if self.unlesbar:
            return "param.json nicht lesbar: " + (self.fehler[0] if self.fehler else "unbekannt")
        if self.ok and not self.warnungen:
            return "param.json in Ordnung"
        teile = []
        if self.fehler:
            teile.append(f"{len(self.fehler)} Fehler")
        if self.warnungen:
            teile.append(f"{len(self.warnungen)} Warnung(en)")
        if self.hinweise:
            teile.append(f"{len(self.hinweise)} Hinweis(e)")
        return "param.json: " + ", ".join(teile)

    def als_text(self, mit_hinweisen: bool = True) -> list[str]:
        """Alle Befunde als Zeilenliste, jede mit vorangestelltem Schweregrad."""
        zeilen = [f"[FEHLER] {t}" for t in self.fehler]
        zeilen += [f"[WARNUNG] {t}" for t in self.warnungen]
        if mit_hinweisen:
            zeilen += [f"[HINWEIS] {t}" for t in self.hinweise]
        return zeilen


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def firmware_aus_text(wert: str) -> int | None:
    """``"5.50"`` -> ``0x0550000000000000``.

    Die Nibbles sind BCD, nicht binaer: Aus der 50 wird 0x50, nicht 0x32.
    """
    treffer = re.match(r"^(\d{1,2})\.(\d{2})$", (wert or "").strip())
    if not treffer:
        return None
    try:
        haupt = int(treffer.group(1).zfill(2), 16)
        neben = int(treffer.group(2), 16)
    except ValueError:
        return None
    return (haupt << 56) | (neben << 48)


def firmware_als_text(roh: int) -> str:
    """``0x0550000000000000`` -> ``"05.50"``."""
    return f"{(roh >> 56) & 0xFF:02X}.{(roh >> 48) & 0xFF:02X}"


def _versionstupel(wert: object) -> tuple[int, ...] | None:
    if not isinstance(wert, str):
        return None
    try:
        return tuple(int(teil) for teil in wert.split("."))
    except ValueError:
        return None


_TYPNAMEN = {str: "Zeichenkette", int: "Ganzzahl", dict: "Objekt",
             list: "Liste", bool: "Wahrheitswert", float: "Kommazahl"}


def _typname(typ: type) -> str:
    return _TYPNAMEN.get(typ, typ.__name__)


def _typ_pruefen(befund: Befund, daten: dict, name: str, erwartet: type,
                 umfeld: str = "") -> bool:
    """True, wenn ``name`` vorhanden ist und den erwarteten Typ hat."""
    if name not in daten:
        return False
    wert = daten[name]
    # bool ist in Python eine int-Unterklasse - hier nie gewollt.
    if erwartet is int and isinstance(wert, bool):
        befund.fehler_melden(f"{umfeld}{name}: Wahrheitswert statt Ganzzahl")
        return False
    if not isinstance(wert, erwartet):
        befund.fehler_melden(
            f"{umfeld}{name}: erwartet {_typname(erwartet)}, "
            f"gefunden {_typname(type(wert))} ({wert!r})"
        )
        return False
    return True


def art_erkennen(daten: dict) -> str:
    """Unterscheidet Basisspiel, Patch und Disc-Abzug."""
    if isinstance(daten.get("disc"), list) and daten["disc"]:
        return "disc"
    if "targetContentVersion" in daten:
        return "patch"
    herkunft = daten.get("originContentVersion")
    inhalt = daten.get("contentVersion")
    if isinstance(herkunft, str) and isinstance(inhalt, str) and herkunft != inhalt:
        return "patch"
    return "base"


# ---------------------------------------------------------------------------
# Einzelpruefungen
# ---------------------------------------------------------------------------
def _ids_pruefen(befund: Befund, daten: dict, pfad: str) -> None:
    title_id = daten.get("titleId")
    content_id = daten.get("contentId")

    if isinstance(title_id, str):
        if not RE_TITLE_ID.match(title_id):
            befund.fehler_melden(
                f"titleId '{title_id}' passt nicht auf das Muster AAAA99999 "
                f"(z. B. PPSA12345)"
            )
        elif not title_id.startswith(("PPSA", "PPSF")):
            befund.hinweis(
                f"titleId beginnt mit '{title_id[:4]}' - Retail-PS5-Titel "
                f"nutzen PPSA"
            )

    if isinstance(content_id, str):
        if len(content_id) != 36:
            befund.fehler_melden(
                f"contentId hat {len(content_id)} Zeichen, erwartet sind 36"
            )
        if not RE_CONTENT_ID.match(content_id):
            befund.fehler_melden(
                f"contentId '{content_id}' passt nicht auf das Muster "
                f"XX9999-AAAA99999_00-<16 Zeichen>"
            )
        elif isinstance(title_id, str):
            eingebettet = content_id[7:16]
            if eingebettet != title_id:
                befund.fehler_melden(
                    f"contentId nennt die Title-ID '{eingebettet}', das Feld "
                    f"titleId aber '{title_id}' - beide müssen gleich sein"
                )
            kennung = content_id[20:]
            if kennung != kennung.upper():
                befund.warnen(
                    f"contentId-Kennung '{kennung}' enthält Kleinbuchstaben - "
                    f"üblich sind Großbuchstaben und Ziffern"
                )

    # Ordnername gegen titleId halten: Loader suchen die Installation dort.
    if isinstance(title_id, str) and pfad:
        sce_sys = os.path.dirname(os.path.abspath(pfad))
        spielordner = os.path.basename(os.path.dirname(sce_sys))
        if spielordner:
            normalisiert = spielordner[:-4] if spielordner.endswith("-app") else spielordner
            if RE_TITLE_ID.match(normalisiert) and normalisiert != title_id:
                befund.fehler_melden(
                    f"Ordnername '{spielordner}' passt nicht zu titleId "
                    f"'{title_id}' - Loader finden die Installation sonst nicht"
                )
            elif not RE_TITLE_ID.match(normalisiert):
                befund.hinweis(
                    f"Der übergeordnete Ordner heißt '{spielordner}', "
                    f"erwartet wäre '{title_id}' oder '{title_id}-app'"
                )


def _versionen_pruefen(befund: Befund, daten: dict, art: str) -> None:
    for name, muster, form in (
        ("contentVersion", RE_VERSION_LANG, "01.000.000"),
        ("originContentVersion", RE_VERSION_LANG, "01.000.000"),
        ("targetContentVersion", RE_VERSION_LANG, "01.000.000"),
        ("masterVersion", RE_VERSION_KURZ, "01.00"),
    ):
        if name not in daten:
            continue
        wert = daten[name]
        if isinstance(wert, (int, float)) and not isinstance(wert, bool):
            befund.fehler_melden(
                f"{name} ist eine Zahl ({wert}) und muss eine Zeichenkette "
                f"sein (\"{form}\") - sonst geht die führende Null verloren"
            )
            continue
        if not isinstance(wert, str):
            befund.fehler_melden(
                f"{name}: erwartet Zeichenkette, gefunden {_typname(type(wert))}"
            )
            continue
        if not muster.match(wert):
            befund.fehler_melden(f"{name} '{wert}' passt nicht auf das Format {form}")

    inhalt = _versionstupel(daten.get("contentVersion"))
    herkunft = _versionstupel(daten.get("originContentVersion"))
    ziel = _versionstupel(daten.get("targetContentVersion"))

    if art == "patch":
        if herkunft and inhalt and herkunft > inhalt:
            befund.fehler_melden(
                f"originContentVersion ({daten['originContentVersion']}) ist "
                f"neuer als contentVersion ({daten['contentVersion']})"
            )
        if ziel and inhalt and ziel < inhalt:
            befund.warnen(
                f"targetContentVersion ({daten['targetContentVersion']}) liegt "
                f"unter contentVersion ({daten['contentVersion']}) - typische "
                f"Ursache für Update-Schleifen"
            )
    elif art == "base" and herkunft and inhalt and herkunft != inhalt:
        befund.warnen(
            "originContentVersion weicht bei einem Basisspiel von "
            "contentVersion ab - ist das in Wahrheit ein Patch?"
        )


def _wertelisten_pruefen(befund: Befund, daten: dict) -> None:
    kategorie = daten.get("applicationCategoryType")
    if isinstance(kategorie, int) and not isinstance(kategorie, bool):
        if kategorie not in APP_KATEGORIEN:
            befund.warnen(
                f"applicationCategoryType {kategorie} ist kein dokumentierter "
                f"Wert (0 = natives Spiel)"
            )

    drm = daten.get("applicationDrmType")
    if isinstance(drm, str) and drm not in DRM_TYPEN:
        ersatz = DRM_VERWECHSLUNGEN.get(drm.lower())
        if ersatz:
            befund.fehler_melden(
                f"applicationDrmType '{drm}' ist ein Anwendungstyp, kein "
                f"DRM-Wert - gemeint ist '{ersatz}'"
            )
        else:
            befund.fehler_melden(
                f"applicationDrmType '{drm}' ist unbekannt - erlaubt sind "
                f"{', '.join(sorted(DRM_TYPEN))}"
            )

    abzeichen = daten.get("contentBadgeType")
    if isinstance(abzeichen, int) and not isinstance(abzeichen, bool):
        if abzeichen not in CONTENT_BADGE_TYPEN:
            befund.warnen(f"contentBadgeType {abzeichen} ist unbekannt - erlaubt: 0, 1, 2")

    for name, bekannt in (
        ("attribute", BEKANNTE_ATTRIBUTE),
        ("attribute2", BEKANNTE_ATTRIBUTE2),
        ("attribute3", BEKANNTE_ATTRIBUTE3),
    ):
        wert = daten.get(name)
        if isinstance(wert, int) and not isinstance(wert, bool) and wert not in bekannt:
            befund.hinweis(
                f"{name} = {wert} steht in keiner Dokumentation - es ist ein "
                f"Bitfeld und kann trotzdem stimmen"
            )


def _sprachen_pruefen(befund: Befund, daten: dict) -> None:
    lokal = daten.get("localizedParameters")
    if not isinstance(lokal, dict):
        return

    standard = lokal.get("defaultLanguage")
    if standard is None:
        befund.fehler_melden("localizedParameters.defaultLanguage fehlt")
    elif not isinstance(standard, str):
        befund.fehler_melden(
            "localizedParameters.defaultLanguage muss ein Sprachcode als "
            "Zeichenkette sein (z. B. \"en-US\")"
        )
    else:
        if standard not in SPRACHEN:
            befund.warnen(f"defaultLanguage '{standard}' ist kein bekannter Sprachcode")
        if standard not in lokal:
            befund.fehler_melden(
                f"localizedParameters hat keinen Block für die Standardsprache "
                f"'{standard}'"
            )

    bloecke = 0
    for name, wert in lokal.items():
        if name == "defaultLanguage":
            continue
        bloecke += 1
        if name not in SPRACHEN:
            befund.warnen(f"localizedParameters['{name}'] ist kein bekannter Sprachcode")
        if not isinstance(wert, dict):
            befund.fehler_melden(f"localizedParameters['{name}'] muss ein Objekt sein")
            continue
        titel = wert.get("titleName")
        if not isinstance(titel, str) or not titel.strip():
            befund.fehler_melden(
                f"localizedParameters['{name}'].titleName fehlt oder ist leer"
            )

    if bloecke == 0:
        befund.fehler_melden("localizedParameters enthält keinen einzigen Sprachblock")


def _altersfreigaben_pruefen(befund: Befund, daten: dict) -> None:
    alter = daten.get("ageLevel")
    if not isinstance(alter, dict):
        return
    if "default" not in alter:
        befund.fehler_melden("ageLevel enthält keinen Eintrag 'default'")
    bekannte_laender = frozenset(LAENDER)
    for name, wert in alter.items():
        if name != "default" and name not in bekannte_laender:
            befund.warnen(f"ageLevel['{name}'] ist kein bekannter Ländercode")
        if not isinstance(wert, int) or isinstance(wert, bool):
            befund.fehler_melden(f"ageLevel['{name}'] muss eine Ganzzahl sein, ist {wert!r}")
        elif not 0 <= wert <= 21:
            befund.warnen(f"ageLevel['{name}'] = {wert} liegt außerhalb von 0 bis 21")


def _absichten_pruefen(befund: Befund, daten: dict, art: str) -> None:
    absicht = daten.get("gameIntent")
    if absicht is None:
        if art in ("base", "disc") and daten.get("applicationCategoryType") == 0:
            befund.warnen(
                "gameIntent fehlt - Spiele führen dort ihre permittedIntents"
            )
        return
    if not isinstance(absicht, dict):
        befund.fehler_melden("gameIntent muss ein Objekt sein")
        return
    eintraege = absicht.get("permittedIntents")
    if not isinstance(eintraege, list) or not eintraege:
        befund.fehler_melden("gameIntent.permittedIntents fehlt oder ist leer")
        return
    for nummer, eintrag in enumerate(eintraege):
        if not isinstance(eintrag, dict):
            befund.fehler_melden(f"permittedIntents[{nummer}] muss ein Objekt sein")
            continue
        typ = eintrag.get("intentType")
        if not isinstance(typ, str):
            befund.fehler_melden(f"permittedIntents[{nummer}].intentType fehlt")
        elif typ not in INTENT_TYPEN:
            befund.warnen(f"permittedIntents[{nummer}].intentType '{typ}' ist unbekannt")


def _hexfelder_pruefen(befund: Befund, daten: dict, hoechste_firmware: str | None) -> None:
    for name in ("requiredSystemSoftwareVersion", "sdkVersion"):
        if name not in daten:
            continue
        wert = daten[name]
        if not isinstance(wert, str):
            befund.fehler_melden(
                f"{name} muss eine Hex-Zeichenkette sein "
                f"(z. B. \"0x0114000000000000\"), ist {_typname(type(wert))}"
            )
            continue
        if not RE_HEX64.match(wert):
            befund.fehler_melden(
                f"{name} '{wert}' passt nicht auf 0x gefolgt von 16 Hex-Ziffern"
            )
            continue
        roh = int(wert, 16)
        beschriftung = "Firmware-Bedarf" if name.startswith("required") else "SDK"
        befund.info[beschriftung] = f"{wert} (FW {firmware_als_text(roh)})"

    if not hoechste_firmware:
        return
    grenze = firmware_aus_text(hoechste_firmware)
    if grenze is None:
        befund.warnen(
            f"Firmware-Grenze '{hoechste_firmware}' nicht lesbar, erwartet z. B. 5.50"
        )
        return
    verlangt = daten.get("requiredSystemSoftwareVersion")
    if isinstance(verlangt, str) and RE_HEX64.match(verlangt):
        roh = int(verlangt, 16)
        if roh > grenze:
            befund.fehler_melden(
                f"requiredSystemSoftwareVersion verlangt Firmware "
                f"{firmware_als_text(roh)}, die Zielkonsole hat höchstens "
                f"{hoechste_firmware} - das Spiel wird ein Systemupdate fordern"
            )


def _werkzeugblock_pruefen(befund: Befund, daten: dict) -> None:
    block = daten.get("pubtools")
    if block is None:
        return
    if not isinstance(block, dict):
        befund.fehler_melden("pubtools muss ein Objekt sein")
        return
    datum = block.get("creationDate")
    if isinstance(datum, str) and not RE_DATUM.match(datum):
        befund.warnen(
            f"pubtools.creationDate '{datum}' - erwartet 'jjjj-mm-tt hh:mm:ss'"
        )
    einreichung = block.get("submission")
    if einreichung is not None and not isinstance(einreichung, bool):
        befund.fehler_melden("pubtools.submission muss ein Wahrheitswert sein")


def _disc_pruefen(befund: Befund, daten: dict) -> None:
    scheiben = daten.get("disc")
    if not isinstance(scheiben, list):
        befund.fehler_melden("disc muss eine Liste sein")
        return

    for name in ("discNumber", "discTotal"):
        if name not in daten:
            befund.fehler_melden(f"{name} fehlt (bei Disc-Abzügen Pflicht)")
        elif not isinstance(daten[name], int) or isinstance(daten[name], bool):
            befund.fehler_melden(f"{name} muss eine Ganzzahl sein")

    nummer = daten.get("discNumber")
    gesamt = daten.get("discTotal")
    if isinstance(nummer, int) and isinstance(gesamt, int) and not isinstance(nummer, bool):
        if nummer < 1 or nummer > gesamt:
            befund.fehler_melden(f"discNumber {nummer} liegt außerhalb von 1 bis {gesamt}")
    if isinstance(gesamt, int) and not isinstance(gesamt, bool) and gesamt != len(scheiben):
        befund.warnen(
            f"discTotal = {gesamt}, die Liste disc hat aber {len(scheiben)} Einträge"
        )

    title_id = daten.get("titleId")

    for nummer, eintrag in enumerate(scheiben):
        umfeld = f"disc[{nummer}]."
        if not isinstance(eintrag, dict):
            befund.fehler_melden(f"disc[{nummer}] muss ein Objekt sein")
            continue

        for name, erwartet in (
            ("contents", list), ("files", list), ("localizedParameters", dict),
            ("masterDataId", str), ("role", str),
        ):
            if name not in eintrag:
                befund.fehler_melden(f"{umfeld}{name} fehlt (bei Disc-Abzügen Pflicht)")
            else:
                _typ_pruefen(befund, eintrag, name, erwartet, umfeld)

        kennung = eintrag.get("masterDataId")
        if isinstance(kennung, str) and isinstance(title_id, str) and kennung != title_id:
            befund.hinweis(
                f"{umfeld}masterDataId '{kennung}' weicht von titleId '{title_id}' ab"
            )

        rolle = eintrag.get("role")
        if isinstance(rolle, str) and rolle != "Play Disc":
            befund.hinweis(f"{umfeld}role = '{rolle}' (dokumentiert ist 'Play Disc')")

        for lfd, inhalt in enumerate(eintrag.get("contents") or []):
            umfeld2 = f"{umfeld}contents[{lfd}]."
            if not isinstance(inhalt, dict):
                befund.fehler_melden(f"{umfeld}contents[{lfd}] muss ein Objekt sein")
                continue
            kennung = inhalt.get("contentId")
            if not isinstance(kennung, str):
                befund.fehler_melden(f"{umfeld2}contentId fehlt")
            elif len(kennung) != 36:
                befund.fehler_melden(f"{umfeld2}contentId hat {len(kennung)} statt 36 Zeichen")
            typ = inhalt.get("contentType")
            if not isinstance(typ, str):
                befund.fehler_melden(f"{umfeld2}contentType fehlt")
            elif typ not in DISC_INHALTSTYPEN:
                befund.warnen(f"{umfeld2}contentType '{typ}' ist unbekannt (z. B. PS5GD)")

        dateien = eintrag.get("files")
        if isinstance(dateien, list) and not dateien:
            befund.warnen(f"{umfeld}files ist leer - Disc-Abzüge führen dort die Dateien")
        for lfd, datei in enumerate(dateien or []):
            umfeld2 = f"{umfeld}files[{lfd}]."
            if not isinstance(datei, dict):
                befund.fehler_melden(f"{umfeld}files[{lfd}] muss ein Objekt sein")
                continue
            if not isinstance(datei.get("fileName"), str):
                befund.fehler_melden(f"{umfeld2}fileName fehlt")
            pruefwerte = datei.get("digests")
            if pruefwerte is None:
                befund.fehler_melden(f"{umfeld2}digests fehlt")
            elif isinstance(pruefwerte, str):
                if not re.fullmatch(r"[0-9A-Fa-f]+", pruefwerte):
                    befund.warnen(f"{umfeld2}digests ist keine Hex-Zeichenkette")
            elif isinstance(pruefwerte, list):
                if any(not isinstance(einzel, str) for einzel in pruefwerte):
                    befund.fehler_melden(f"{umfeld2}digests enthält Nicht-Zeichenketten")
            else:
                befund.fehler_melden(f"{umfeld2}digests hat einen unerwarteten Typ")

        lokal = eintrag.get("localizedParameters")
        if isinstance(lokal, dict):
            standard = lokal.get("defaultLanguage")
            if not isinstance(standard, str):
                befund.fehler_melden(f"{umfeld}localizedParameters.defaultLanguage fehlt")
            elif standard not in lokal:
                befund.fehler_melden(
                    f"{umfeld}localizedParameters hat keinen Block für '{standard}'"
                )


def _nachbarn_pruefen(befund: Befund, pfad: str) -> None:
    """Dateien neben der param.json, die zum selben Bild gehoeren."""
    sce_sys = os.path.dirname(os.path.abspath(pfad))
    if not os.path.isfile(os.path.join(sce_sys, "icon0.png")):
        befund.warnen(
            "sce_sys/icon0.png fehlt - ohne Symbol taucht der Titel unter "
            "Umständen nicht auf dem Startbildschirm auf"
        )
    if not os.path.isfile(os.path.join(os.path.dirname(sce_sys), "eboot.bin")):
        befund.hinweis("eboot.bin liegt nicht neben dem Ordner sce_sys")


# ---------------------------------------------------------------------------
# Laden
# ---------------------------------------------------------------------------
def laden(pfad: str, befund: Befund) -> dict | None:
    """Liest die Datei streng und traegt jeden Lesefehler in ``befund`` ein.

    Streng heisst: Ein UTF-8-BOM ist ein Fehler, kein Schoenheitsfehler. Genau
    daran scheitert die Konsole mit "invalid param.json", waehrend jeder
    Texteditor die Datei anstandslos anzeigt.
    """
    try:
        with open(pfad, "rb") as datei:
            roh = datei.read()
    except FileNotFoundError:
        befund.fehlt = True
        befund.unlesbar = True
        befund.fehler_melden("Datei nicht vorhanden")
        return None
    except OSError as exc:
        befund.unlesbar = True
        befund.fehler_melden(f"nicht lesbar: {exc}")
        return None

    if roh.startswith(b"\xef\xbb\xbf"):
        befund.fehler_melden(
            "Die Datei beginnt mit einem UTF-8-BOM - das allein genügt für "
            "'invalid param.json'. Sie muss ohne BOM gespeichert werden."
        )
        roh = roh[3:]
    if roh.startswith((b"\xff\xfe", b"\xfe\xff")):
        befund.unlesbar = True
        befund.fehler_melden("Die Datei ist UTF-16 kodiert und muss UTF-8 sein")
        return None

    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError as exc:
        befund.unlesbar = True
        befund.fehler_melden(f"kein gültiges UTF-8: {exc}")
        return None

    try:
        daten = json.loads(text, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError as exc:
        befund.unlesbar = True
        befund.fehler_melden(
            f"JSON-Syntaxfehler in Zeile {exc.lineno}, Spalte {exc.colno}: {exc.msg}"
        )
        zeilen = text.splitlines()
        if 0 < exc.lineno <= len(zeilen):
            befund.fehler_melden(f"  -> {zeilen[exc.lineno - 1].strip()}")
        if re.search(r",\s*[}\]]", text):
            befund.fehler_melden("  -> es steht mindestens ein Komma vor einer schließenden Klammer")
        return None

    if not isinstance(daten, dict):
        befund.unlesbar = True
        befund.fehler_melden("Das Wurzelelement ist kein Objekt")
        return None
    return daten


# ---------------------------------------------------------------------------
# Oeffentliche Pruefung
# ---------------------------------------------------------------------------
def pruefe_datei(pfad: str, hoechste_firmware: str | None = None,
                 nachbarn_pruefen: bool = True) -> Befund:
    """Prueft eine ``param.json`` auf dem Datentraeger.

    Args:
        pfad: Vollstaendiger Pfad zur ``param.json``.
        hoechste_firmware: Firmware der Zielkonsole als ``"5.50"``. Ist sie
            angegeben, wird ``requiredSystemSoftwareVersion`` dagegen gehalten.
        nachbarn_pruefen: Auch ``icon0.png`` und ``eboot.bin`` ansehen.

    Returns:
        Befund mit Fehlern, Warnungen, Hinweisen und Eckdaten.
    """
    befund = Befund(pfad)
    daten = laden(pfad, befund)
    if daten is None:
        return befund
    _inhalt_pruefen(befund, daten, pfad, hoechste_firmware)
    if nachbarn_pruefen:
        _nachbarn_pruefen(befund, pfad)
    return befund


def pruefe_daten(daten: dict, pfad: str = "",
                 hoechste_firmware: str | None = None) -> Befund:
    """Prueft ein bereits geladenes Dokument.

    Fuer Quellen, die keine Datei sind - etwa eine ``param.json`` aus einem
    ``.ffpfsc``, die ueber die mkpfs-Schnittstelle gelesen wurde.
    """
    befund = Befund(pfad)
    _inhalt_pruefen(befund, daten, pfad, hoechste_firmware)
    return befund


def _inhalt_pruefen(befund: Befund, daten: dict, pfad: str,
                    hoechste_firmware: str | None) -> None:
    art = art_erkennen(daten)
    befund.art = art
    befund.info["Art"] = {
        "base": "Basisspiel", "patch": "Patch/Update", "disc": "Disc-Abzug",
    }[art]
    befund.info["titleId"] = str(daten.get("titleId", "-"))
    befund.info["contentId"] = str(daten.get("contentId", "-"))
    befund.info["Version"] = str(daten.get("contentVersion", "-"))
    befund.info["Titel"] = titel_aus_daten(daten) or "-"

    for name, typ in HARTE_PFLICHTFELDER.items():
        if name not in daten:
            befund.fehler_melden(f"Pflichtfeld '{name}' fehlt")
        else:
            _typ_pruefen(befund, daten, name, typ)

    for name, typ in WEICHE_PFLICHTFELDER.items():
        if name not in daten:
            befund.warnen(
                f"Feld '{name}' fehlt - vollständige Pakete führen es, "
                f"Homebrew kommt ohne aus"
            )
        elif name not in _VERSIONSFELDER:
            # Die Versionsfelder laesst _versionen_pruefen aus - dort steht
            # nicht nur der Typ, sondern auch, warum er zaehlt. Zweimal
            # dasselbe zu melden macht den Befund nur laenger.
            _typ_pruefen(befund, daten, name, typ)

    if "versionFileUri" not in daten:
        befund.hinweis(
            "versionFileUri fehlt - laut Dokumentation Pflicht, bei einfachen "
            "Anwendungen darf es aber leer bleiben"
        )

    if art == "patch" and "originContentVersion" not in daten:
        befund.warnen("originContentVersion fehlt bei einem Patch")

    _ids_pruefen(befund, daten, pfad)
    _versionen_pruefen(befund, daten, art)
    _wertelisten_pruefen(befund, daten)
    _sprachen_pruefen(befund, daten)
    _altersfreigaben_pruefen(befund, daten)
    _absichten_pruefen(befund, daten, art)
    _hexfelder_pruefen(befund, daten, hoechste_firmware)
    _werkzeugblock_pruefen(befund, daten)
    if art == "disc":
        _disc_pruefen(befund, daten)
    elif "disc" in daten:
        befund.hinweis("Der Schlüssel disc ist vorhanden, aber leer")


def titel_aus_daten(daten: dict) -> str:
    """Anzeigename aus ``localizedParameters``, sonst leer."""
    lokal = daten.get("localizedParameters")
    if not isinstance(lokal, dict):
        return ""
    standard = lokal.get("defaultLanguage")
    if isinstance(standard, str) and isinstance(lokal.get(standard), dict):
        name = lokal[standard].get("titleName")
        if isinstance(name, str):
            return name
    # Kein Standardblock: den ersten brauchbaren nehmen.
    for name, wert in lokal.items():
        if name == "defaultLanguage" or not isinstance(wert, dict):
            continue
        titel = wert.get("titleName")
        if isinstance(titel, str) and titel.strip():
            return titel
    return ""


# ---------------------------------------------------------------------------
# Reparatur
# ---------------------------------------------------------------------------
#: Werte, mit denen fehlende Felder aufgefuellt werden. Sie stammen aus der
#: vollstaendigen Beispieldatei von LibProsperoPKG (HomebrewTest) - also aus
#: einem Paket, das nachweislich gebaut und geladen wird.
_VORGABEN: "OrderedDict[str, Any]" = OrderedDict([
    ("applicationCategoryType", 0),
    ("applicationDrmType", "standard"),
    ("attribute", 0),
    ("attribute2", 0),
    ("attribute3", 0),
    ("contentBadgeType", 2),
    ("contentVersion", "01.000.000"),
    ("masterVersion", "01.00"),
])


def vollstaendiger_altersblock(stufe: int = 0) -> "OrderedDict[str, int]":
    """``ageLevel`` mit allen bekannten Laendern und dem Eintrag ``default``.

    Die Reihenfolge folgt der Beispieldatei: Laender alphabetisch, ``default``
    zum Schluss.
    """
    block: "OrderedDict[str, int]" = OrderedDict()
    for land in LAENDER:
        block[land] = stufe
    block["default"] = stufe
    return block


def repariere(daten: dict, *, title_id: str = "", content_id: str = "",
              titel: str = "",
              inhaltsversion: str = "") -> tuple["OrderedDict[str, Any]", list[str]]:
    """Zieht ein geladenes Dokument gerade, ohne vorhandene Angaben zu verwerfen.

    Der Unterschied zum Neuanlegen ist der Punkt der ganzen Uebung: Eine
    vorhandene ``param.json`` enthaelt fast immer brauchbare Angaben - Titel,
    Versionen, Altersfreigaben. Sie zu ueberschreiben wirft weg, was noch
    stimmt. Repariert wird deshalb nur, was nachweislich falsch ist.

    Args:
        daten: Geladenes Dokument.
        title_id: Falls bekannt, wird eine fehlende oder unpassende ``titleId``
            damit gesetzt.
        content_id: Ergaenzt eine fehlende ``contentId``.
        titel: Ergaenzt einen fehlenden Anzeigenamen.

    Returns:
        (repariertes Dokument, Liste der vorgenommenen Aenderungen in Klartext).
    """
    neu: "OrderedDict[str, Any]" = OrderedDict(daten)
    aenderungen: list[str] = []

    # -- Kennungen ---------------------------------------------------------
    vorhandene_id = neu.get("titleId")
    if title_id:
        if not isinstance(vorhandene_id, str) or not RE_TITLE_ID.match(vorhandene_id):
            neu["titleId"] = title_id
            aenderungen.append(f"titleId auf '{title_id}' gesetzt")
        elif vorhandene_id != title_id:
            # Der Dump weiss es besser als der Dateiname - nptitle.dat und
            # Ordnername sind die Quellen, aus denen title_id stammt.
            neu["titleId"] = title_id
            aenderungen.append(
                f"titleId von '{vorhandene_id}' auf '{title_id}' berichtigt"
            )

    kennung = neu.get("titleId")
    inhalt_id = neu.get("contentId")
    if content_id and not isinstance(inhalt_id, str):
        neu["contentId"] = content_id
        aenderungen.append(f"contentId auf '{content_id}' gesetzt")
    elif (isinstance(inhalt_id, str) and isinstance(kennung, str)
            and RE_CONTENT_ID.match(inhalt_id) and inhalt_id[7:16] != kennung):
        berichtigt = inhalt_id[:7] + kennung + inhalt_id[16:]
        neu["contentId"] = berichtigt
        aenderungen.append(
            f"contentId auf die Title-ID '{kennung}' abgeglichen"
        )

    # -- Versionen ---------------------------------------------------------
    # Zahlen statt Zeichenketten sind der haeufigste Fehler: Wer die Datei in
    # einem Editor "aufraeumt", macht aus "01.000.000" schnell 1.0.
    # Steht die Inhaltsversion im Dump (sce_sys/pfs-version.dat), gilt sie.
    # Sonst bliebe bei einem gepatchten Spiel die Vorgabe stehen, und die
    # Datei behauptete einen Stand, den sie nicht hat.
    inhalt_vorgabe = inhaltsversion or "01.000.000"
    for name, muster, vorgabe in (
        ("contentVersion", RE_VERSION_LANG, inhalt_vorgabe),
        ("originContentVersion", RE_VERSION_LANG, "01.000.000"),
        ("targetContentVersion", RE_VERSION_LANG, "01.000.000"),
        ("masterVersion", RE_VERSION_KURZ, "01.00"),
    ):
        if name not in neu:
            continue
        wert = neu[name]
        if isinstance(wert, str) and muster.match(wert):
            # Format stimmt - aber wenn der Dump eine andere Inhaltsversion
            # nennt, ist seine Angabe die richtige.
            if (name == "contentVersion" and inhaltsversion
                    and wert != inhaltsversion):
                neu[name] = inhaltsversion
                aenderungen.append(
                    f"contentVersion von {wert!r} auf {inhaltsversion!r} "
                    f"berichtigt (aus sce_sys/pfs-version.dat)")
            continue
        neu[name] = vorgabe
        aenderungen.append(f"{name} von {wert!r} auf '{vorgabe}' gesetzt")

    # -- DRM-Wert ----------------------------------------------------------
    drm = neu.get("applicationDrmType")
    if isinstance(drm, str) and drm not in DRM_TYPEN:
        ersatz = DRM_VERWECHSLUNGEN.get(drm.lower(), "standard")
        neu["applicationDrmType"] = ersatz
        aenderungen.append(f"applicationDrmType '{drm}' auf '{ersatz}' berichtigt")

    # -- Sprachblock -------------------------------------------------------
    lokal = neu.get("localizedParameters")
    if not isinstance(lokal, dict):
        lokal = OrderedDict()
        aenderungen.append("localizedParameters neu angelegt")
    else:
        lokal = OrderedDict(lokal)

    standard = lokal.get("defaultLanguage")
    if not isinstance(standard, str) or not standard:
        standard = "en-US"
        lokal["defaultLanguage"] = standard
        aenderungen.append("localizedParameters.defaultLanguage auf 'en-US' gesetzt")

    blockname = titel or titel_aus_daten(daten) or (kennung if isinstance(kennung, str) else "")
    if not isinstance(lokal.get(standard), dict):
        lokal[standard] = OrderedDict([("titleName", blockname or "Unbekannt")])
        aenderungen.append(f"Sprachblock '{standard}' angelegt")
    else:
        block = OrderedDict(lokal[standard])
        name = block.get("titleName")
        if not isinstance(name, str) or not name.strip():
            block["titleName"] = blockname or "Unbekannt"
            aenderungen.append(f"titleName in '{standard}' ergänzt")
        lokal[standard] = block

    # defaultLanguage gehoert nach oben - so steht es in jeder Vorlage.
    geordnet: "OrderedDict[str, Any]" = OrderedDict()
    geordnet["defaultLanguage"] = lokal.pop("defaultLanguage")
    for name, wert in lokal.items():
        geordnet[name] = wert
    neu["localizedParameters"] = geordnet

    # -- Altersfreigaben ---------------------------------------------------
    alter = neu.get("ageLevel")
    if not isinstance(alter, dict) or not alter:
        neu["ageLevel"] = vollstaendiger_altersblock()
        aenderungen.append("ageLevel mit allen Ländern angelegt (Stufe 0)")
    elif "default" not in alter:
        ergaenzt = OrderedDict(alter)
        ergaenzt["default"] = 0
        neu["ageLevel"] = ergaenzt
        aenderungen.append("ageLevel.default ergänzt (Stufe 0)")

    # -- Fehlende Standardfelder ------------------------------------------
    for name, vorgabe in _VORGABEN.items():
        if name not in neu:
            neu[name] = vorgabe
            aenderungen.append(f"{name} ergänzt ({vorgabe!r})")

    # -- Typfehler in Ganzzahlfeldern -------------------------------------
    for name in ("applicationCategoryType", "contentBadgeType",
                 "attribute", "attribute2", "attribute3"):
        if name not in neu:
            continue
        wert = neu[name]
        if isinstance(wert, bool) or not isinstance(wert, int):
            ersatz = _VORGABEN.get(name, 0)
            neu[name] = ersatz
            aenderungen.append(f"{name} von {wert!r} auf {ersatz!r} gesetzt")

    # -- Hexfelder ---------------------------------------------------------
    for name in ("requiredSystemSoftwareVersion", "sdkVersion"):
        if name not in neu:
            continue
        wert = neu[name]
        if isinstance(wert, str) and RE_HEX64.match(wert):
            continue
        neu[name] = "0x0000000000000000"
        aenderungen.append(f"{name} von {wert!r} auf '0x0000000000000000' gesetzt")

    return neu, aenderungen


def neu_anlegen(title_id: str = "", content_id: str = "", titel: str = "",
                inhaltsversion: str = "",
                vollstaendig: bool = True) -> "OrderedDict[str, Any]":
    """Erzeugt eine vollstaendige ``param.json`` von Grund auf.

    Für den Fall, dass gar keine Datei da ist oder sie sich nicht mehr lesen
    laesst. Der Aufbau folgt der Beispieldatei aus LibProsperoPKG.

    Args:
        vollstaendig: Mit allen Feldern und dem kompletten Altersblock. Auf
            ``False`` entsteht das knappe Grundgeruest, das dem Beispiel des
            ps5-payload-sdk entspricht.
    """
    doc: "OrderedDict[str, Any]" = OrderedDict()
    if vollstaendig:
        doc["ageLevel"] = vollstaendiger_altersblock()
    doc["applicationCategoryType"] = 0
    if vollstaendig:
        doc["applicationDrmType"] = "standard"
        doc["attribute"] = 0
        doc["attribute2"] = 0
        doc["attribute3"] = 0
        doc["contentBadgeType"] = 2
    if content_id:
        doc["contentId"] = content_id
    if vollstaendig:
        # Steht die Inhaltsversion im Dump (sce_sys/pfs-version.dat), gilt
        # sie: Bei einem gepatchten Spiel ist die Vorgabe 01.000.000 schlicht
        # falsch, und niemand merkt es der Datei an.
        doc["contentVersion"] = inhaltsversion or "01.000.000"
    lokal: "OrderedDict[str, Any]" = OrderedDict()
    lokal["defaultLanguage"] = "en-US"
    lokal["en-US"] = OrderedDict([("titleName", titel or title_id or "Unbekannt")])
    doc["localizedParameters"] = lokal
    if vollstaendig:
        doc["masterVersion"] = "01.00"
    if title_id:
        doc["titleId"] = title_id
    return doc
