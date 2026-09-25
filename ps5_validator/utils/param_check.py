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


#: Der Einzeiler, der nach der param.json-Prüfung im sichtbaren
#: Protokollfeld steht - als Vorgabe. Die Oberfläche reicht über ``texte``
#: die übersetzte Fassung herein; dieses Modul darf ``i18n`` nicht
#: einbinden. Dasselbe Muster wie in ``pkg_merger.MELDUNGEN``.
MELDUNGEN: dict[str, str] = {
    "param_fehlt": "param.json fehlt",
    "param_unlesbar": "param.json nicht lesbar: {grund}",
    "param_in_ordnung": "param.json in Ordnung",
    "param_befunde": "param.json: {teile}",
    "grund_unbekannt": "unbekannt",
    "anzahl_fehler": "{anzahl} Fehler",
    "anzahl_warnungen": "{anzahl} Warnung(en)",
    "anzahl_hinweise": "{anzahl} Hinweis(e)",
    # Zeilen fuer das Protokoll (als_text) und die Typnamen in den Befunden.
    "zeile_fehler": "[FEHLER] {text}",
    "zeile_warnung": "[WARNUNG] {text}",
    "zeile_hinweis": "[HINWEIS] {text}",
    "typname_str": "Zeichenkette",
    "typname_int": "Ganzzahl",
    "typname_dict": "Objekt",
    "typname_list": "Liste",
    "typname_bool": "Wahrheitswert",
    "typname_float": "Kommazahl",
    # Die Einzelbefunde und die Reparaturschritte (Durchsicht, Runde 18,
    # 25.09.2026) - bis dahin fest deutsch in den Pruefungen. Die Kennung
    # nennt Pruefung, Schweregrad und laufende Nummer.
    "typ_fehler_1": "{umfeld}{name}: Wahrheitswert statt Ganzzahl",
    "typ_fehler_2": "{umfeld}{name}: erwartet {typ}, gefunden {typ2} ({wert!r})",
    "ids_fehler_1": "titleId '{title_id}' passt nicht auf das Muster AAAA99999 (z. B. PPSA12345)",
    "ids_hinweis_1": "titleId beginnt mit '{wert}' - Retail-PS5-Titel nutzen PPSA",
    "ids_fehler_2": "contentId hat {anzahl} Zeichen, erwartet sind 36",
    "ids_fehler_3": "contentId '{content_id}' passt nicht auf das Muster XX9999-AAAA99999_00-<16 Zeichen>",
    "ids_fehler_4": "contentId nennt die Title-ID '{eingebettet}', das Feld titleId aber '{title_id}' - beide müssen gleich sein",
    "ids_warnung_1": "contentId-Kennung '{kennung}' enthält Kleinbuchstaben - üblich sind Großbuchstaben und Ziffern",
    "ids_warnung_2": "Ordnername '{spielordner}' passt nicht zu titleId '{title_id}' - Loader finden die Installation sonst nicht",
    "ids_hinweis_2": "Der übergeordnete Ordner heißt '{spielordner}', erwartet wäre '{title_id}' oder '{title_id}-app'",
    "versionen_fehler_1": "{name} ist eine Zahl ({wert}) und muss eine Zeichenkette sein (\"{form}\") - sonst geht die führende Null verloren",
    "versionen_fehler_2": "{name}: erwartet Zeichenkette, gefunden {typ}",
    "versionen_fehler_3": "{name} '{wert}' passt nicht auf das Format {form}",
    "versionen_fehler_4": "originContentVersion ({originContentVersion}) ist neuer als contentVersion ({contentVersion})",
    "versionen_warnung_1": "targetContentVersion ({targetContentVersion}) liegt unter contentVersion ({contentVersion}) - typische Ursache für Update-Schleifen",
    "versionen_warnung_2": "originContentVersion weicht bei einem Basisspiel von contentVersion ab - ist das in Wahrheit ein Patch?",
    "wertelisten_warnung_1": "applicationCategoryType {kategorie} ist kein dokumentierter Wert (0 = natives Spiel)",
    "wertelisten_fehler_1": "applicationDrmType '{drm}' ist ein Anwendungstyp, kein DRM-Wert - gemeint ist '{ersatz}'",
    "wertelisten_fehler_2": "applicationDrmType '{drm}' ist unbekannt - erlaubt sind {wert}",
    "wertelisten_warnung_2": "contentBadgeType {abzeichen} ist unbekannt - erlaubt: 0, 1, 2",
    "wertelisten_hinweis_1": "{name} = {wert} steht in keiner Dokumentation - es ist ein Bitfeld und kann trotzdem stimmen",
    "sprachen_fehler_1": "localizedParameters.defaultLanguage fehlt",
    "sprachen_fehler_2": "localizedParameters.defaultLanguage muss ein Sprachcode als Zeichenkette sein (z. B. \"en-US\")",
    "sprachen_warnung_1": "defaultLanguage '{standard}' ist kein bekannter Sprachcode",
    "sprachen_fehler_3": "localizedParameters hat keinen Block für die Standardsprache '{standard}'",
    "sprachen_warnung_2": "localizedParameters['{name}'] ist kein bekannter Sprachcode",
    "sprachen_fehler_4": "localizedParameters['{name}'] muss ein Objekt sein",
    "sprachen_fehler_5": "localizedParameters['{name}'].titleName fehlt oder ist leer",
    "sprachen_fehler_6": "localizedParameters enthält keinen einzigen Sprachblock",
    "altersfreigaben_fehler_1": "ageLevel enthält keinen Eintrag 'default'",
    "altersfreigaben_warnung_1": "ageLevel['{name}'] ist kein bekannter Ländercode",
    "altersfreigaben_fehler_2": "ageLevel['{name}'] muss eine Ganzzahl sein, ist {wert!r}",
    "altersfreigaben_warnung_2": "ageLevel['{name}'] = {wert} liegt außerhalb von 0 bis 21",
    "absichten_warnung_1": "gameIntent fehlt - Spiele führen dort ihre permittedIntents",
    "absichten_fehler_1": "gameIntent muss ein Objekt sein",
    "absichten_fehler_2": "gameIntent.permittedIntents fehlt oder ist leer",
    "absichten_fehler_3": "permittedIntents[{nummer}] muss ein Objekt sein",
    "absichten_fehler_4": "permittedIntents[{nummer}].intentType fehlt",
    "absichten_warnung_2": "permittedIntents[{nummer}].intentType '{typ}' ist unbekannt",
    "hexfelder_fehler_1": "{name} muss eine Hex-Zeichenkette sein (z. B. \"0x0114000000000000\"), ist {typ}",
    "hexfelder_fehler_2": "{name} '{wert}' passt nicht auf 0x gefolgt von 16 Hex-Ziffern",
    "hexfelder_warnung_1": "Firmware-Grenze '{hoechste_firmware}' nicht lesbar, erwartet z. B. 5.50",
    "hexfelder_fehler_3": "requiredSystemSoftwareVersion verlangt Firmware {firmware}, die Zielkonsole hat höchstens {hoechste_firmware} - das Spiel wird ein Systemupdate fordern",
    "werkzeugblock_fehler_1": "pubtools muss ein Objekt sein",
    "werkzeugblock_warnung_1": "pubtools.creationDate '{datum}' - erwartet 'jjjj-mm-tt hh:mm:ss'",
    "werkzeugblock_fehler_2": "pubtools.submission muss ein Wahrheitswert sein",
    "disc_fehler_1": "disc muss eine Liste sein",
    "disc_fehler_2": "{name} fehlt (bei Disc-Abzügen Pflicht)",
    "disc_fehler_3": "{name} muss eine Ganzzahl sein",
    "disc_fehler_4": "discNumber {nummer} liegt außerhalb von 1 bis {gesamt}",
    "disc_warnung_1": "discTotal = {gesamt}, die Liste disc hat aber {anzahl} Einträge",
    "disc_fehler_5": "disc[{nummer}] muss ein Objekt sein",
    "disc_fehler_6": "{umfeld}{name} fehlt (bei Disc-Abzügen Pflicht)",
    "disc_hinweis_1": "{umfeld}masterDataId '{kennung}' weicht von titleId '{title_id}' ab",
    "disc_hinweis_2": "{umfeld}role = '{rolle}' (dokumentiert ist 'Play Disc')",
    "disc_fehler_7": "{umfeld}contents[{lfd}] muss ein Objekt sein",
    "disc_fehler_8": "{umfeld2}contentId fehlt",
    "disc_fehler_9": "{umfeld2}contentId hat {anzahl} statt 36 Zeichen",
    "disc_fehler_10": "{umfeld2}contentType fehlt",
    "disc_warnung_2": "{umfeld2}contentType '{typ}' ist unbekannt (z. B. PS5GD)",
    "disc_warnung_3": "{umfeld}files ist leer - Disc-Abzüge führen dort die Dateien",
    "disc_fehler_11": "{umfeld}files[{lfd}] muss ein Objekt sein",
    "disc_fehler_12": "{umfeld2}fileName fehlt",
    "disc_fehler_13": "{umfeld2}digests fehlt",
    "disc_warnung_4": "{umfeld2}digests ist keine Hex-Zeichenkette",
    "disc_fehler_14": "{umfeld2}digests enthält Nicht-Zeichenketten",
    "disc_fehler_15": "{umfeld2}digests hat einen unerwarteten Typ",
    "disc_fehler_16": "{umfeld}localizedParameters.defaultLanguage fehlt",
    "disc_fehler_17": "{umfeld}localizedParameters hat keinen Block für '{standard}'",
    "nachbarn_warnung_1": "sce_sys/icon0.png fehlt - ohne Symbol taucht der Titel unter Umständen nicht auf dem Startbildschirm auf",
    "nachbarn_hinweis_1": "eboot.bin liegt nicht neben dem Ordner sce_sys",
    "laden_fehler_1": "Datei nicht vorhanden",
    "laden_fehler_2": "nicht lesbar: {exc}",
    "laden_fehler_3": "Die Datei beginnt mit einem UTF-8-BOM - das allein genügt für 'invalid param.json'. Sie muss ohne BOM gespeichert werden.",
    "laden_fehler_4": "Die Datei ist UTF-16 kodiert und muss UTF-8 sein",
    "laden_fehler_5": "kein gültiges UTF-8: {exc}",
    "laden_fehler_6": "JSON-Syntaxfehler in Zeile {lineno}, Spalte {colno}: {msg}",
    "laden_fehler_7": "  -> {wert}",
    "laden_fehler_8": "  -> es steht mindestens ein Komma vor einer schließenden Klammer",
    "laden_fehler_9": "Das Wurzelelement ist kein Objekt",
    "inhalt_fehler_1": "Pflichtfeld '{name}' fehlt",
    "inhalt_warnung_1": "Feld '{name}' fehlt - vollständige Pakete führen es, Homebrew kommt ohne aus",
    "inhalt_hinweis_1": "versionFileUri fehlt - laut Dokumentation Pflicht, bei einfachen Anwendungen darf es aber leer bleiben",
    "inhalt_warnung_2": "originContentVersion fehlt bei einem Patch",
    "inhalt_hinweis_2": "Der Schlüssel disc ist vorhanden, aber leer",
    "rep_aenderung_1": "titleId auf '{title_id}' gesetzt",
    "rep_aenderung_2": "titleId von '{vorhandene_id}' auf '{title_id}' berichtigt",
    "rep_aenderung_3": "titleId von {kennung!r} auf '{aus_inhalt}' berichtigt (aus der contentId)",
    "rep_aenderung_4": "contentId auf '{content_id}' gesetzt",
    "rep_aenderung_5": "contentId auf die Title-ID '{kennung}' abgeglichen",
    "rep_aenderung_6": "contentVersion von {wert!r} auf {inhaltsversion!r} berichtigt (aus sce_sys/pfs-version.dat)",
    "rep_aenderung_7": "{name} von {wert!r} auf '{umgewandelt}' umgeschrieben",
    "rep_aenderung_8": "{name} von {wert!r} auf '{vorgabe}' gesetzt",
    "rep_aenderung_9": "applicationDrmType '{drm}' auf '{ersatz}' berichtigt",
    "rep_aenderung_10": "localizedParameters neu angelegt",
    "rep_aenderung_11": "localizedParameters.defaultLanguage auf 'en-US' gesetzt",
    "rep_aenderung_12": "Sprachblock '{standard}' angelegt",
    "rep_aenderung_13": "titleName in '{standard}' ergänzt",
    "rep_aenderung_14": "ageLevel mit allen Ländern angelegt (Stufe 0)",
    "rep_aenderung_15": "ageLevel.default ergänzt (Stufe 0)",
    "rep_aenderung_16": "{name} ergänzt ({vorgabe!r})",
    "rep_aenderung_17": "{name} von {wert!r} auf {zahl!r} umgeschrieben",
    "rep_aenderung_18": "{name} von {wert!r} auf {ersatz!r} gesetzt",
    "rep_aenderung_19": "{name} von {wert!r} auf '0x0000000000000000' gesetzt",
}


def _satz(texte: "dict[str, str] | None", kennung: str, /, **werte) -> str:
    """Eine Vorlage, übersetzt wenn möglich.

    ``texte`` und ``kennung`` sind nur-positionell (``/``): Die Befunde
    tragen Platzhalter wie ``{kennung}`` - als Schluesselwort uebergeben,
    stiess das bis zur Durchsicht (Runde 18) mit dem Parameternamen zusammen
    ("got multiple values for argument 'kennung'").
    """
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return MELDUNGEN[kennung].format(**werte)


# ---------------------------------------------------------------------------
# Befund
# ---------------------------------------------------------------------------
class Befund:
    """Ergebnis einer Pruefung: Fehler, Warnungen, Hinweise und Eckdaten.

    Args:
        texte: Uebersetzte Vorlagen je Kennung aus :data:`MELDUNGEN`. Die
            Pruefungen bauen ihre Saetze damit (:meth:`satz`), und
            :meth:`zusammenfassung` sowie :meth:`als_text` nehmen sie, wenn
            ihnen keine eigenen mitgegeben werden (Durchsicht, Runde 18).
    """

    def __init__(self, pfad: str = "", texte: "dict[str, str] | None" = None) -> None:
        self.pfad = pfad
        self.texte = texte
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
    def satz(self, kennung: str, /, **werte: Any) -> str:
        """Ein Befundsatz aus :data:`MELDUNGEN` - in der Sprache der Vorlagen."""
        return _satz(self.texte, kennung, **werte)

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

    def zusammenfassung(self, texte: "dict[str, str] | None" = None) -> str:
        """Einzeiler fuer das Protokoll.

        Args:
            texte: Vorlagen je Kennung; fehlt eine, gilt die aus
                :data:`MELDUNGEN`. Der Satz steht im sichtbaren
                Protokollfeld des Hauptfensters, nicht nur in der Datei.
                Ohne Angabe gelten die Vorlagen des Befunds.
        """
        if texte is None:
            texte = self.texte
        if self.fehlt:
            return _satz(texte, "param_fehlt")
        if self.unlesbar:
            return _satz(texte, "param_unlesbar",
                         grund=(self.fehler[0] if self.fehler
                                else _satz(texte, "grund_unbekannt")))
        if self.ok and not self.warnungen:
            return _satz(texte, "param_in_ordnung")
        teile = []
        if self.fehler:
            teile.append(_satz(texte, "anzahl_fehler", anzahl=len(self.fehler)))
        if self.warnungen:
            teile.append(_satz(texte, "anzahl_warnungen",
                               anzahl=len(self.warnungen)))
        if self.hinweise:
            teile.append(_satz(texte, "anzahl_hinweise",
                               anzahl=len(self.hinweise)))
        return _satz(texte, "param_befunde", teile=", ".join(teile))

    def als_text(self, mit_hinweisen: bool = True) -> list[str]:
        """Alle Befunde als Zeilenliste, jede mit vorangestelltem Schweregrad.

        Die Vorsaetze ("[FEHLER]" usw.) kommen aus den Vorlagen des Befunds -
        bis zur Durchsicht (Runde 18) standen sie fest deutsch hier.
        """
        zeilen = [self.satz("zeile_fehler", text=t) for t in self.fehler]
        zeilen += [self.satz("zeile_warnung", text=t) for t in self.warnungen]
        if mit_hinweisen:
            zeilen += [self.satz("zeile_hinweis", text=t) for t in self.hinweise]
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


#: Kennungen der Typnamen in :data:`MELDUNGEN` (bis Runde 18 der Text selbst).
_TYPNAMEN = {str: "typname_str", int: "typname_int", dict: "typname_dict",
             list: "typname_list", bool: "typname_bool", float: "typname_float"}


def _typname(typ: type, texte: "dict[str, str] | None" = None) -> str:
    kennung = _TYPNAMEN.get(typ)
    return _satz(texte, kennung) if kennung else typ.__name__


def _typ_pruefen(befund: Befund, daten: dict, name: str, erwartet: type,
                 umfeld: str = "") -> bool:
    """True, wenn ``name`` vorhanden ist und den erwarteten Typ hat."""
    if name not in daten:
        return False
    wert = daten[name]
    # bool ist in Python eine int-Unterklasse - hier nie gewollt.
    if erwartet is int and isinstance(wert, bool):
        befund.fehler_melden(befund.satz("typ_fehler_1", umfeld=umfeld, name=name))
        return False
    if not isinstance(wert, erwartet):
        befund.fehler_melden(befund.satz(
            "typ_fehler_2", umfeld=umfeld, name=name,
            typ=_typname(erwartet, befund.texte),
            typ2=_typname(type(wert), befund.texte), wert=wert))
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
                befund.satz("ids_fehler_1", title_id=title_id)
            )
        elif not title_id.startswith(("PPSA", "PPSF")):
            befund.hinweis(
                befund.satz("ids_hinweis_1", wert=title_id[:4])
            )

    if isinstance(content_id, str):
        if len(content_id) != 36:
            befund.fehler_melden(
                befund.satz("ids_fehler_2", anzahl=len(content_id))
            )
        if not RE_CONTENT_ID.match(content_id):
            befund.fehler_melden(
                befund.satz("ids_fehler_3", content_id=content_id)
            )
        elif isinstance(title_id, str):
            eingebettet = content_id[7:16]
            if eingebettet != title_id:
                befund.fehler_melden(
                    befund.satz("ids_fehler_4", eingebettet=eingebettet, title_id=title_id)
                )
            kennung = content_id[20:]
            if kennung != kennung.upper():
                befund.warnen(
                    befund.satz("ids_warnung_1", kennung=kennung)
                )

    # Ordnername gegen titleId halten: Loader suchen die Installation dort.
    if isinstance(title_id, str) and pfad:
        sce_sys = os.path.dirname(os.path.abspath(pfad))
        spielordner = os.path.basename(os.path.dirname(sce_sys))
        if spielordner:
            normalisiert = spielordner[:-4] if spielordner.endswith("-app") else spielordner
            if RE_TITLE_ID.match(normalisiert) and normalisiert != title_id:
                # Eine Warnung, kein Fehler: In der Datei selbst ist nichts
                # falsch, und keine Reparatur der param.json kann einen
                # Ordnernamen aendern. Als Fehler stiess der Befund bis
                # v1.9.24 die Reparaturkette an - die Nachpruefung scheiterte
                # am selben Namen, und am Ende wurde angeboten, die komplette
                # param.json (Sprachbloecke, Altersfreigabe, Attribute) durch
                # ein Geruest zu ersetzen. In einem Abbild spielt der Name des
                # Dump-Ordners ohnehin keine Rolle.
                befund.warnen(
                    befund.satz("ids_warnung_2", spielordner=spielordner, title_id=title_id)
                )
            elif not RE_TITLE_ID.match(normalisiert):
                befund.hinweis(
                    befund.satz("ids_hinweis_2", spielordner=spielordner, title_id=title_id)
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
                befund.satz("versionen_fehler_1", name=name, wert=wert, form=form)
            )
            continue
        if not isinstance(wert, str):
            befund.fehler_melden(
                befund.satz("versionen_fehler_2", name=name, typ=_typname(type(wert), befund.texte))
            )
            continue
        if not muster.match(wert):
            befund.fehler_melden(befund.satz("versionen_fehler_3", name=name, wert=wert, form=form))

    inhalt = _versionstupel(daten.get("contentVersion"))
    herkunft = _versionstupel(daten.get("originContentVersion"))
    ziel = _versionstupel(daten.get("targetContentVersion"))

    if art == "patch":
        if herkunft and inhalt and herkunft > inhalt:
            befund.fehler_melden(
                befund.satz("versionen_fehler_4", originContentVersion=daten['originContentVersion'], contentVersion=daten['contentVersion'])
            )
        if ziel and inhalt and ziel < inhalt:
            befund.warnen(
                befund.satz("versionen_warnung_1", targetContentVersion=daten['targetContentVersion'], contentVersion=daten['contentVersion'])
            )
    elif art == "base" and herkunft and inhalt and herkunft != inhalt:
        befund.warnen(
            befund.satz("versionen_warnung_2")
        )


def _wertelisten_pruefen(befund: Befund, daten: dict) -> None:
    kategorie = daten.get("applicationCategoryType")
    if isinstance(kategorie, int) and not isinstance(kategorie, bool):
        if kategorie not in APP_KATEGORIEN:
            befund.warnen(
                befund.satz("wertelisten_warnung_1", kategorie=kategorie)
            )

    drm = daten.get("applicationDrmType")
    if isinstance(drm, str) and drm not in DRM_TYPEN:
        ersatz = DRM_VERWECHSLUNGEN.get(drm.lower())
        if ersatz:
            befund.fehler_melden(
                befund.satz("wertelisten_fehler_1", drm=drm, ersatz=ersatz)
            )
        else:
            befund.fehler_melden(
                befund.satz("wertelisten_fehler_2", drm=drm, wert=', '.join(sorted(DRM_TYPEN)))
            )

    abzeichen = daten.get("contentBadgeType")
    if isinstance(abzeichen, int) and not isinstance(abzeichen, bool):
        if abzeichen not in CONTENT_BADGE_TYPEN:
            befund.warnen(befund.satz("wertelisten_warnung_2", abzeichen=abzeichen))

    for name, bekannt in (
        ("attribute", BEKANNTE_ATTRIBUTE),
        ("attribute2", BEKANNTE_ATTRIBUTE2),
        ("attribute3", BEKANNTE_ATTRIBUTE3),
    ):
        wert = daten.get(name)
        if isinstance(wert, int) and not isinstance(wert, bool) and wert not in bekannt:
            befund.hinweis(
                befund.satz("wertelisten_hinweis_1", name=name, wert=wert)
            )


def _sprachen_pruefen(befund: Befund, daten: dict) -> None:
    lokal = daten.get("localizedParameters")
    if not isinstance(lokal, dict):
        return

    standard = lokal.get("defaultLanguage")
    if standard is None:
        befund.fehler_melden(befund.satz("sprachen_fehler_1"))
    elif not isinstance(standard, str):
        befund.fehler_melden(
            befund.satz("sprachen_fehler_2")
        )
    else:
        if standard not in SPRACHEN:
            befund.warnen(befund.satz("sprachen_warnung_1", standard=standard))
        if standard not in lokal:
            befund.fehler_melden(
                befund.satz("sprachen_fehler_3", standard=standard)
            )

    bloecke = 0
    for name, wert in lokal.items():
        if name == "defaultLanguage":
            continue
        bloecke += 1
        if name not in SPRACHEN:
            befund.warnen(befund.satz("sprachen_warnung_2", name=name))
        if not isinstance(wert, dict):
            befund.fehler_melden(befund.satz("sprachen_fehler_4", name=name))
            continue
        titel = wert.get("titleName")
        if not isinstance(titel, str) or not titel.strip():
            befund.fehler_melden(
                befund.satz("sprachen_fehler_5", name=name)
            )

    if bloecke == 0:
        befund.fehler_melden(befund.satz("sprachen_fehler_6"))


def _altersfreigaben_pruefen(befund: Befund, daten: dict) -> None:
    alter = daten.get("ageLevel")
    if not isinstance(alter, dict):
        return
    if "default" not in alter:
        befund.fehler_melden(befund.satz("altersfreigaben_fehler_1"))
    bekannte_laender = frozenset(LAENDER)
    for name, wert in alter.items():
        if name != "default" and name not in bekannte_laender:
            befund.warnen(befund.satz("altersfreigaben_warnung_1", name=name))
        if not isinstance(wert, int) or isinstance(wert, bool):
            befund.fehler_melden(befund.satz("altersfreigaben_fehler_2", name=name, wert=wert))
        elif not 0 <= wert <= 21:
            befund.warnen(befund.satz("altersfreigaben_warnung_2", name=name, wert=wert))


def _absichten_pruefen(befund: Befund, daten: dict, art: str) -> None:
    absicht = daten.get("gameIntent")
    if absicht is None:
        if art in ("base", "disc") and daten.get("applicationCategoryType") == 0:
            befund.warnen(
                befund.satz("absichten_warnung_1")
            )
        return
    if not isinstance(absicht, dict):
        befund.fehler_melden(befund.satz("absichten_fehler_1"))
        return
    eintraege = absicht.get("permittedIntents")
    if not isinstance(eintraege, list) or not eintraege:
        befund.fehler_melden(befund.satz("absichten_fehler_2"))
        return
    for nummer, eintrag in enumerate(eintraege):
        if not isinstance(eintrag, dict):
            befund.fehler_melden(befund.satz("absichten_fehler_3", nummer=nummer))
            continue
        typ = eintrag.get("intentType")
        if not isinstance(typ, str):
            befund.fehler_melden(befund.satz("absichten_fehler_4", nummer=nummer))
        elif typ not in INTENT_TYPEN:
            befund.warnen(befund.satz("absichten_warnung_2", nummer=nummer, typ=typ))


def _hexfelder_pruefen(befund: Befund, daten: dict, hoechste_firmware: str | None) -> None:
    for name in ("requiredSystemSoftwareVersion", "sdkVersion"):
        if name not in daten:
            continue
        wert = daten[name]
        if not isinstance(wert, str):
            befund.fehler_melden(
                befund.satz("hexfelder_fehler_1", name=name, typ=_typname(type(wert), befund.texte))
            )
            continue
        if not RE_HEX64.match(wert):
            befund.fehler_melden(
                befund.satz("hexfelder_fehler_2", name=name, wert=wert)
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
            befund.satz("hexfelder_warnung_1", hoechste_firmware=hoechste_firmware)
        )
        return
    verlangt = daten.get("requiredSystemSoftwareVersion")
    if isinstance(verlangt, str) and RE_HEX64.match(verlangt):
        roh = int(verlangt, 16)
        if roh > grenze:
            befund.fehler_melden(
                befund.satz("hexfelder_fehler_3", firmware=firmware_als_text(roh), hoechste_firmware=hoechste_firmware)
            )


def _werkzeugblock_pruefen(befund: Befund, daten: dict) -> None:
    block = daten.get("pubtools")
    if block is None:
        return
    if not isinstance(block, dict):
        befund.fehler_melden(befund.satz("werkzeugblock_fehler_1"))
        return
    datum = block.get("creationDate")
    if isinstance(datum, str) and not RE_DATUM.match(datum):
        befund.warnen(
            befund.satz("werkzeugblock_warnung_1", datum=datum)
        )
    einreichung = block.get("submission")
    if einreichung is not None and not isinstance(einreichung, bool):
        befund.fehler_melden(befund.satz("werkzeugblock_fehler_2"))


def _disc_pruefen(befund: Befund, daten: dict) -> None:
    scheiben = daten.get("disc")
    if not isinstance(scheiben, list):
        befund.fehler_melden(befund.satz("disc_fehler_1"))
        return

    for name in ("discNumber", "discTotal"):
        if name not in daten:
            befund.fehler_melden(befund.satz("disc_fehler_2", name=name))
        elif not isinstance(daten[name], int) or isinstance(daten[name], bool):
            befund.fehler_melden(befund.satz("disc_fehler_3", name=name))

    nummer = daten.get("discNumber")
    gesamt = daten.get("discTotal")
    if isinstance(nummer, int) and isinstance(gesamt, int) and not isinstance(nummer, bool):
        if nummer < 1 or nummer > gesamt:
            befund.fehler_melden(befund.satz("disc_fehler_4", nummer=nummer, gesamt=gesamt))
    if isinstance(gesamt, int) and not isinstance(gesamt, bool) and gesamt != len(scheiben):
        befund.warnen(
            befund.satz("disc_warnung_1", gesamt=gesamt, anzahl=len(scheiben))
        )

    title_id = daten.get("titleId")

    for nummer, eintrag in enumerate(scheiben):
        umfeld = f"disc[{nummer}]."
        if not isinstance(eintrag, dict):
            befund.fehler_melden(befund.satz("disc_fehler_5", nummer=nummer))
            continue

        for name, erwartet in (
            ("contents", list), ("files", list), ("localizedParameters", dict),
            ("masterDataId", str), ("role", str),
        ):
            if name not in eintrag:
                befund.fehler_melden(befund.satz("disc_fehler_6", umfeld=umfeld, name=name))
            else:
                _typ_pruefen(befund, eintrag, name, erwartet, umfeld)

        kennung = eintrag.get("masterDataId")
        if isinstance(kennung, str) and isinstance(title_id, str) and kennung != title_id:
            befund.hinweis(
                befund.satz("disc_hinweis_1", umfeld=umfeld, kennung=kennung, title_id=title_id)
            )

        rolle = eintrag.get("role")
        if isinstance(rolle, str) and rolle != "Play Disc":
            befund.hinweis(befund.satz("disc_hinweis_2", umfeld=umfeld, rolle=rolle))

        for lfd, inhalt in enumerate(eintrag.get("contents") or []):
            umfeld2 = f"{umfeld}contents[{lfd}]."
            if not isinstance(inhalt, dict):
                befund.fehler_melden(befund.satz("disc_fehler_7", umfeld=umfeld, lfd=lfd))
                continue
            kennung = inhalt.get("contentId")
            if not isinstance(kennung, str):
                befund.fehler_melden(befund.satz("disc_fehler_8", umfeld2=umfeld2))
            elif len(kennung) != 36:
                befund.fehler_melden(befund.satz("disc_fehler_9", umfeld2=umfeld2, anzahl=len(kennung)))
            typ = inhalt.get("contentType")
            if not isinstance(typ, str):
                befund.fehler_melden(befund.satz("disc_fehler_10", umfeld2=umfeld2))
            elif typ not in DISC_INHALTSTYPEN:
                befund.warnen(befund.satz("disc_warnung_2", umfeld2=umfeld2, typ=typ))

        dateien = eintrag.get("files")
        if isinstance(dateien, list) and not dateien:
            befund.warnen(befund.satz("disc_warnung_3", umfeld=umfeld))
        for lfd, datei in enumerate(dateien or []):
            umfeld2 = f"{umfeld}files[{lfd}]."
            if not isinstance(datei, dict):
                befund.fehler_melden(befund.satz("disc_fehler_11", umfeld=umfeld, lfd=lfd))
                continue
            if not isinstance(datei.get("fileName"), str):
                befund.fehler_melden(befund.satz("disc_fehler_12", umfeld2=umfeld2))
            pruefwerte = datei.get("digests")
            if pruefwerte is None:
                befund.fehler_melden(befund.satz("disc_fehler_13", umfeld2=umfeld2))
            elif isinstance(pruefwerte, str):
                if not re.fullmatch(r"[0-9A-Fa-f]+", pruefwerte):
                    befund.warnen(befund.satz("disc_warnung_4", umfeld2=umfeld2))
            elif isinstance(pruefwerte, list):
                if any(not isinstance(einzel, str) for einzel in pruefwerte):
                    befund.fehler_melden(befund.satz("disc_fehler_14", umfeld2=umfeld2))
            else:
                befund.fehler_melden(befund.satz("disc_fehler_15", umfeld2=umfeld2))

        lokal = eintrag.get("localizedParameters")
        if isinstance(lokal, dict):
            standard = lokal.get("defaultLanguage")
            if not isinstance(standard, str):
                befund.fehler_melden(befund.satz("disc_fehler_16", umfeld=umfeld))
            elif standard not in lokal:
                befund.fehler_melden(
                    befund.satz("disc_fehler_17", umfeld=umfeld, standard=standard)
                )


def _nachbarn_pruefen(befund: Befund, pfad: str) -> None:
    """Dateien neben der param.json, die zum selben Bild gehoeren."""
    sce_sys = os.path.dirname(os.path.abspath(pfad))
    if not os.path.isfile(os.path.join(sce_sys, "icon0.png")):
        befund.warnen(
            befund.satz("nachbarn_warnung_1")
        )
    if not os.path.isfile(os.path.join(os.path.dirname(sce_sys), "eboot.bin")):
        befund.hinweis(befund.satz("nachbarn_hinweis_1"))


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
        befund.fehler_melden(befund.satz("laden_fehler_1"))
        return None
    except OSError as exc:
        befund.unlesbar = True
        befund.fehler_melden(befund.satz("laden_fehler_2", exc=exc))
        return None

    if roh.startswith(b"\xef\xbb\xbf"):
        befund.fehler_melden(
            befund.satz("laden_fehler_3")
        )
        roh = roh[3:]
    if roh.startswith((b"\xff\xfe", b"\xfe\xff")):
        befund.unlesbar = True
        befund.fehler_melden(befund.satz("laden_fehler_4"))
        return None

    try:
        text = roh.decode("utf-8")
    except UnicodeDecodeError as exc:
        befund.unlesbar = True
        befund.fehler_melden(befund.satz("laden_fehler_5", exc=exc))
        return None

    try:
        daten = json.loads(text, object_pairs_hook=OrderedDict)
    except json.JSONDecodeError as exc:
        befund.unlesbar = True
        befund.fehler_melden(
            befund.satz("laden_fehler_6", lineno=exc.lineno, colno=exc.colno, msg=exc.msg)
        )
        zeilen = text.splitlines()
        if 0 < exc.lineno <= len(zeilen):
            befund.fehler_melden(befund.satz("laden_fehler_7", wert=zeilen[exc.lineno - 1].strip()))
        if re.search(r",\s*[}\]]", text):
            befund.fehler_melden(befund.satz("laden_fehler_8"))
        return None

    if not isinstance(daten, dict):
        befund.unlesbar = True
        befund.fehler_melden(befund.satz("laden_fehler_9"))
        return None
    return daten


# ---------------------------------------------------------------------------
# Oeffentliche Pruefung
# ---------------------------------------------------------------------------
def pruefe_datei(pfad: str, hoechste_firmware: str | None = None,
                 nachbarn_pruefen: bool = True,
                 texte: "dict[str, str] | None" = None) -> Befund:
    """Prueft eine ``param.json`` auf dem Datentraeger.

    Args:
        pfad: Vollstaendiger Pfad zur ``param.json``.
        hoechste_firmware: Firmware der Zielkonsole als ``"5.50"``. Ist sie
            angegeben, wird ``requiredSystemSoftwareVersion`` dagegen gehalten.
        nachbarn_pruefen: Auch ``icon0.png`` und ``eboot.bin`` ansehen.
        texte: Uebersetzte Vorlagen (:data:`MELDUNGEN`) fuer die Befunde.

    Returns:
        Befund mit Fehlern, Warnungen, Hinweisen und Eckdaten.
    """
    befund = Befund(pfad, texte=texte)
    daten = laden(pfad, befund)
    if daten is None:
        return befund
    _inhalt_pruefen(befund, daten, pfad, hoechste_firmware)
    if nachbarn_pruefen:
        _nachbarn_pruefen(befund, pfad)
    return befund


def pruefe_daten(daten: dict, pfad: str = "",
                 hoechste_firmware: str | None = None,
                 texte: "dict[str, str] | None" = None) -> Befund:
    """Prueft ein bereits geladenes Dokument.

    Fuer Quellen, die keine Datei sind - etwa eine ``param.json`` aus einem
    ``.ffpfsc``, die ueber die mkpfs-Schnittstelle gelesen wurde.
    """
    befund = Befund(pfad, texte=texte)
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
            befund.fehler_melden(befund.satz("inhalt_fehler_1", name=name))
        else:
            _typ_pruefen(befund, daten, name, typ)

    for name, typ in WEICHE_PFLICHTFELDER.items():
        if name not in daten:
            befund.warnen(
                befund.satz("inhalt_warnung_1", name=name)
            )
        elif name not in _VERSIONSFELDER:
            # Die Versionsfelder laesst _versionen_pruefen aus - dort steht
            # nicht nur der Typ, sondern auch, warum er zaehlt. Zweimal
            # dasselbe zu melden macht den Befund nur laenger.
            _typ_pruefen(befund, daten, name, typ)

    if "versionFileUri" not in daten:
        befund.hinweis(
            befund.satz("inhalt_hinweis_1")
        )

    if art == "patch" and "originContentVersion" not in daten:
        befund.warnen(befund.satz("inhalt_warnung_2"))

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
        befund.hinweis(befund.satz("inhalt_hinweis_2"))


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


#: Vorsatz einer Ersatz-Content-ID. Die echte Kennung steht in keiner Datei
#: eines Backups - gemessen am 16.08.2026, auch nicht in der eboot.bin
#: (Vollscan) und nicht in npbind.dat -, sondern nur online. "UP0000" ist
#: derselbe neutrale Vorsatz wie im Beispiel des Param-Editors: Region und
#: Herausgeber sind damit ausdruecklich unbekannt.
CONTENT_ID_ERSATZ_VORSATZ = "UP0000"


def content_id_ersatz(title_id: str, titel: str = "") -> str:
    """Eine formal gueltige Content-ID fuer den Fall, dass die echte fehlt.

    PKG-Werkzeuge brechen ohne ``contentId`` ab ("param.json has no Content
    ID" - Rueckmeldung eines Anwenders am 23.09.2026, der aus Abbildern dieses
    Programms Pakete bauen wollte). Die Konsole selbst startet Titel auch ohne
    sie. Fuer Updates und DLC zaehlt dagegen die echte Kennung - deshalb ist
    das hier ausdruecklich ein Platzhalter, und die Aufrufer sagen das so.

    Aufbau ``UP0000-<Title-ID>_00-<16 Zeichen>``; die 16 Zeichen kommen aus dem
    Titel (Grossbuchstaben und Ziffern) und werden mit ``0`` aufgefuellt.

    Returns:
        Die Kennung, oder ``""`` ohne gueltige Title-ID - eine erfundene
        Title-ID waere schlimmer als gar keine Content-ID.
    """
    tid = str(title_id or "").strip().upper()
    if not RE_TITLE_ID.match(tid):
        return ""
    kennung = re.sub(r"[^A-Z0-9]", "", str(titel or "").upper())[:16].ljust(16, "0")
    return f"{CONTENT_ID_ERSATZ_VORSATZ}-{tid}_00-{kennung}"


def content_id_fehlt(daten: object) -> bool:
    """Fehlt in einem geladenen Dokument die ``contentId`` (oder ist sie leer)?"""
    if not isinstance(daten, dict):
        return False
    wert = daten.get("contentId")
    return not (isinstance(wert, str) and wert.strip())


def content_id_einsetzen(daten: dict, content_id: str) -> "OrderedDict[str, Any]":
    """Setzt ``contentId`` an ihre Stelle und laesst alles andere, wie es ist.

    Die Felder einer echten param.json stehen alphabetisch; die Kennung kommt
    deshalb vor das erste Feld, das danach einsortiert gehoert (in der Regel
    ``contentVersion``), statt ans Ende.
    """
    neu: "OrderedDict[str, Any]" = OrderedDict()
    gesetzt = False
    for name, wert in daten.items():
        if name == "contentId":
            continue
        if not gesetzt and name > "contentId":
            neu["contentId"] = content_id
            gesetzt = True
        neu[name] = wert
    if not gesetzt:
        neu["contentId"] = content_id
    return neu


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


def _als_ganzzahl(wert: object) -> "int | None":
    """Die Ganzzahl in einem nur formal falschen Wert - oder None.

    ``"1073741824"``, ``"0x10"`` oder ``65536.0`` lassen sich verlustfrei
    umwandeln. Bis zum 24.09.2026 setzte die Reparatur an ihre Stelle die
    Vorgabe - aus einer Kategorie 65536 wurde 0, ein natives Spiel
    (Durchsicht, U1-2). Wahrheitswerte bleiben aussen vor: ``true`` hat
    niemand als Zahl gemeint.
    """
    if isinstance(wert, bool):
        return None
    if isinstance(wert, float):
        return int(wert) if wert.is_integer() and wert >= 0 else None
    if isinstance(wert, str):
        text = wert.strip()
        if re.fullmatch(r"[0-9]+", text):
            return int(text)
        if re.fullmatch(r"0[xX][0-9A-Fa-f]+", text):
            return int(text, 16)
    return None


def _als_version(wert: object, muster: "re.Pattern[str]") -> str:
    """Eine Version im verlangten Format - oder "", wenn sie nicht eindeutig ist.

    Umgewandelt wird nur, was sich auf genau eine Weise lesen laesst
    (Durchsicht, U1-2):

    * Die erste Stelle hat nicht zwei Ziffern: ``"1.005.000"`` wird
      ``"01.005.000"``, ``"1.00"`` wird ``"01.00"``. Die hinteren Stellen
      muessen schon stimmen - ob ``"1.5.0"`` 005 oder 500 meint, weiss niemand.
    * Eine ganze Zahl: ``2`` oder ``2.0`` wird ``"02.000.000"`` bzw. ``"02.00"``.
    * Bei der kurzen Form auch eine Kommazahl mit hoechstens zwei
      Nachkommastellen: ``1.05`` wird ``"01.05"``.
    """
    lang = muster is RE_VERSION_LANG
    if isinstance(wert, bool):
        return ""
    if isinstance(wert, (int, float)):
        if isinstance(wert, float) and not wert.is_integer():
            if lang:
                return ""
            hundertstel = round(wert * 100)
            if abs(wert * 100 - hundertstel) > 1e-6 or not 0 <= hundertstel < 10000:
                return ""
            text = f"{hundertstel // 100:02d}.{hundertstel % 100:02d}"
            return text if muster.match(text) else ""
        ganz = int(wert)
        if not 0 <= ganz <= 99:
            return ""
        return f"{ganz:02d}.000.000" if lang else f"{ganz:02d}.00"
    if isinstance(wert, str):
        teile = wert.strip().split(".")
        if not re.fullmatch(r"[0-9]+", teile[0]) or int(teile[0]) > 99:
            return ""
        text = ".".join([f"{int(teile[0]):02d}"] + teile[1:])
        return text if muster.match(text) else ""
    return ""


def _als_hex64(wert: object) -> str:
    """Ein Hexwert mit 16 Stellen - oder "", wenn keiner darin steckt.

    ``"0x114000000000000"`` (eine Stelle zu wenig) wird
    ``"0x0114000000000000"``: Fuehrende Nullen aendern den Wert nicht. Bis
    zum 24.09.2026 wurde daraus ``0x0000000000000000`` - und der
    Firmware-Bedarf war weg (Durchsicht, U1-2). Eine ganze Zahl wird
    hexadezimal geschrieben.
    """
    if isinstance(wert, bool):
        return ""
    if isinstance(wert, int):
        return f"0x{wert:016X}" if 0 <= wert < 1 << 64 else ""
    if isinstance(wert, str):
        treffer = re.fullmatch(r"0[xX]([0-9A-Fa-f]{1,16})", wert.strip())
        if treffer:
            return "0x" + treffer.group(1).rjust(16, "0")
    return ""


def repariere(daten: dict, *, title_id: str = "", content_id: str = "",
              titel: str = "",
              inhaltsversion: str = "",
              texte: "dict[str, str] | None" = None) -> tuple["OrderedDict[str, Any]", list[str]]:
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
        texte: Uebersetzte Vorlagen fuer die Aenderungsliste - sie steht im
            Protokoll (Durchsicht, Runde 18). Ein fehlender Titel wird
            weiterhin als "Unbekannt" in die Datei geschrieben: Das ist
            Inhalt der param.json, keine Oberflaeche.

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
            aenderungen.append(_satz(texte, "rep_aenderung_1", title_id=title_id))
        elif vorhandene_id != title_id:
            # Der Dump weiss es besser als der Dateiname - nptitle.dat und
            # Ordnername sind die Quellen, aus denen title_id stammt.
            neu["titleId"] = title_id
            aenderungen.append(
                _satz(texte, "rep_aenderung_2", vorhandene_id=vorhandene_id, title_id=title_id)
            )

    kennung = neu.get("titleId")
    inhalt_id = neu.get("contentId")
    if (not (isinstance(kennung, str) and RE_TITLE_ID.match(kennung))
            and isinstance(inhalt_id, str) and RE_CONTENT_ID.match(inhalt_id)):
        # Die titleId ist ungueltig ("ppsa01234", "PPSA1234") und keine
        # bessere wurde uebergeben - die gueltige contentId traegt sie an
        # Stelle 7-15. Bis zum 24.09.2026 lief es umgekehrt: Die ungueltige
        # titleId wurde in die contentId geschrieben und verdarb sie
        # (Durchsicht, U1-3).
        aus_inhalt = inhalt_id[7:16]
        neu["titleId"] = aus_inhalt
        aenderungen.append(
            _satz(texte, "rep_aenderung_3", kennung=kennung, aus_inhalt=aus_inhalt)
        )
        kennung = aus_inhalt
    if content_id and content_id_fehlt(neu):
        # Auch ein leerer Text zaehlt als fehlend - "contentId": "" laesst
        # jedes PKG-Werkzeug genauso abbrechen wie ein fehlendes Feld.
        neu = content_id_einsetzen(neu, content_id)
        aenderungen.append(_satz(texte, "rep_aenderung_4", content_id=content_id))
    elif (isinstance(inhalt_id, str) and isinstance(kennung, str)
            and RE_TITLE_ID.match(kennung)
            and RE_CONTENT_ID.match(inhalt_id) and inhalt_id[7:16] != kennung):
        berichtigt = inhalt_id[:7] + kennung + inhalt_id[16:]
        neu["contentId"] = berichtigt
        aenderungen.append(
            _satz(texte, "rep_aenderung_5", kennung=kennung)
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
                    _satz(texte, "rep_aenderung_6", wert=wert, inhaltsversion=inhaltsversion))
            continue
        # Die Angabe aus pfs-version.dat geht vor; sonst wird umgewandelt,
        # was eindeutig ist, und erst dann die Vorgabe gesetzt (U1-2).
        umgewandelt = "" if (name == "contentVersion" and inhaltsversion) \
            else _als_version(wert, muster)
        if umgewandelt:
            neu[name] = umgewandelt
            aenderungen.append(_satz(texte, "rep_aenderung_7", name=name, wert=wert, umgewandelt=umgewandelt))
            continue
        neu[name] = vorgabe
        aenderungen.append(_satz(texte, "rep_aenderung_8", name=name, wert=wert, vorgabe=vorgabe))

    # -- DRM-Wert ----------------------------------------------------------
    drm = neu.get("applicationDrmType")
    if isinstance(drm, str) and drm not in DRM_TYPEN:
        ersatz = DRM_VERWECHSLUNGEN.get(drm.lower(), "standard")
        neu["applicationDrmType"] = ersatz
        aenderungen.append(_satz(texte, "rep_aenderung_9", drm=drm, ersatz=ersatz))

    # -- Sprachblock -------------------------------------------------------
    lokal = neu.get("localizedParameters")
    if not isinstance(lokal, dict):
        lokal = OrderedDict()
        aenderungen.append(_satz(texte, "rep_aenderung_10"))
    else:
        lokal = OrderedDict(lokal)

    standard = lokal.get("defaultLanguage")
    if not isinstance(standard, str) or not standard:
        standard = "en-US"
        lokal["defaultLanguage"] = standard
        aenderungen.append(_satz(texte, "rep_aenderung_11"))

    blockname = titel or titel_aus_daten(daten) or (kennung if isinstance(kennung, str) else "")
    if not isinstance(lokal.get(standard), dict):
        lokal[standard] = OrderedDict([("titleName", blockname or "Unbekannt")])
        aenderungen.append(_satz(texte, "rep_aenderung_12", standard=standard))
    else:
        block = OrderedDict(lokal[standard])
        name = block.get("titleName")
        if not isinstance(name, str) or not name.strip():
            block["titleName"] = blockname or "Unbekannt"
            aenderungen.append(_satz(texte, "rep_aenderung_13", standard=standard))
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
        aenderungen.append(_satz(texte, "rep_aenderung_14"))
    elif "default" not in alter:
        ergaenzt = OrderedDict(alter)
        ergaenzt["default"] = 0
        neu["ageLevel"] = ergaenzt
        aenderungen.append(_satz(texte, "rep_aenderung_15"))

    # -- Fehlende Standardfelder ------------------------------------------
    for name, vorgabe in _VORGABEN.items():
        if name not in neu:
            # Die Inhaltsversion aus pfs-version.dat geht vor - sonst stand
            # ein gepatchter Dump ohne contentVersion danach als Basisversion
            # 01.000.000 da, obwohl der Aufrufer die richtige mitgab.
            if name == "contentVersion":
                vorgabe = inhalt_vorgabe
            neu[name] = vorgabe
            aenderungen.append(_satz(texte, "rep_aenderung_16", name=name, vorgabe=vorgabe))

    # -- Typfehler in Ganzzahlfeldern -------------------------------------
    for name in ("applicationCategoryType", "contentBadgeType",
                 "attribute", "attribute2", "attribute3"):
        if name not in neu:
            continue
        wert = neu[name]
        if isinstance(wert, bool) or not isinstance(wert, int):
            zahl = _als_ganzzahl(wert)
            if zahl is not None:
                neu[name] = zahl
                aenderungen.append(_satz(texte, "rep_aenderung_17", name=name, wert=wert, zahl=zahl))
                continue
            ersatz = _VORGABEN.get(name, 0)
            neu[name] = ersatz
            aenderungen.append(_satz(texte, "rep_aenderung_18", name=name, wert=wert, ersatz=ersatz))

    # -- Hexfelder ---------------------------------------------------------
    for name in ("requiredSystemSoftwareVersion", "sdkVersion"):
        if name not in neu:
            continue
        wert = neu[name]
        if isinstance(wert, str) and RE_HEX64.match(wert):
            continue
        umgewandelt = _als_hex64(wert)
        if umgewandelt:
            neu[name] = umgewandelt
            aenderungen.append(_satz(texte, "rep_aenderung_7", name=name, wert=wert, umgewandelt=umgewandelt))
            continue
        neu[name] = "0x0000000000000000"
        aenderungen.append(_satz(texte, "rep_aenderung_19", name=name, wert=wert))

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
