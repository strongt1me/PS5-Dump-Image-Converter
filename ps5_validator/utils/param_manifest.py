"""Hilfsfunktionen zum Bearbeiten von `sce_sys/param.json` und `manifest.json`.

Beide Dateien sind reine JSON-Dokumente mit einer Menge bekannter, aber nicht
verpflichtender Top-Level-Schlüssel. Dieses Modul stellt die bekannten Schlüssel/
Wertebereiche als Referenz für eine komfortable GUI-Bearbeitung bereit und kapselt
das Lesen/Schreiben mit dem für PS5-Werkzeuge üblichen Formatierungsstil
(param.json: 2 Leerzeichen Einrückung; manifest.json: 4 Leerzeichen Einrückung;
jeweils UTF-8 ohne BOM). Es wird keine Kryptografie oder Signierung durchgeführt.

Schlüssel-/Wertelisten durch Gegenlesen des quelloffenen LibProsperoPKG-Metadatenmodells
(GPL-3.0-or-later, https://github.com/SvenGDK/LibProsperoPKG) ermittelt; eigenstaendige
Python-Neuentwicklung auf Basis der (nicht schutzfaehigen) Format-Fakten.
"""
from __future__ import annotations

import json
import os
import re
from collections import OrderedDict

APPLICATION_DRM_TYPES: tuple[str, ...] = ("standard", "free", "freemium")

# --- sce_sys/nptitle.dat ----------------------------------------------------
# Kleine, signierte Metadatendatei neben der param.json. Aufbau an 32 echten
# Backups nachgemessen (Stand 15.08.2026, alle 32 identisch):
#
#   0x00  4 Byte   Magic "NPTD"
#   0x04  12 Byte  Versions-/Flagfeld
#   0x10  16 Byte  Title-ID mit Suffix, NUL-aufgefuellt: "PPSA18089_00"
#   0x20  128 Byte Signatur
#
# Sie ist damit die verlaesslichste Quelle fuer die Title-ID, wenn die
# param.json fehlt oder beschaedigt ist - in allen 32 Faellen stimmte sie mit
# der param.json ueberein. Die vollstaendige Content-ID steht hier NICHT: nur
# der Mittelteil "PPSA18089_00", nicht Regionalpraefix und Label.
NPTITLE_FILE_NAME = "nptitle.dat"
NPTITLE_MAGIC = b"NPTD"
NPTITLE_TITLE_ID_OFFSET = 0x10
NPTITLE_TITLE_ID_SIZE = 16
_TITLE_ID_PATTERN = re.compile(r"(?:PPSA|CUSA|PLAS)\d{5}")


def read_title_id_from_nptitle(path: str) -> str:
    """Liest die Title-ID aus einer ``sce_sys/nptitle.dat``.

    Args:
        path: Pfad zur nptitle.dat.

    Returns:
        Die Title-ID (z. B. ``"PPSA18089"``) oder ein leerer String, wenn die
        Datei fehlt, die Magic nicht stimmt oder kein gueltiges Muster darin steht.
    """
    try:
        with open(path, "rb") as handle:
            kopf = handle.read(NPTITLE_TITLE_ID_OFFSET + NPTITLE_TITLE_ID_SIZE)
    except OSError:
        return ""
    if len(kopf) < NPTITLE_TITLE_ID_OFFSET + 4 or kopf[:4] != NPTITLE_MAGIC:
        return ""
    roh = kopf[NPTITLE_TITLE_ID_OFFSET:].split(b"\x00", 1)[0]
    try:
        text = roh.decode("ascii")
    except UnicodeDecodeError:
        return ""
    # "PPSA18089_00" -> "PPSA18089"
    kern = text.split("_", 1)[0].strip().upper()
    return kern if _TITLE_ID_PATTERN.fullmatch(kern) else ""


def read_title_id_from_dump(source_dir: str) -> str:
    """Sucht die Title-ID im ``sce_sys`` eines Dump-Ordners.

    Bequemlichkeitsschale um :func:`read_title_id_from_nptitle`.
    """
    return read_title_id_from_nptitle(
        os.path.join(source_dir, "sce_sys", NPTITLE_FILE_NAME)
    )

INTENT_TYPES: tuple[str, ...] = ("launchActivity", "joinSession")

LANGUAGE_CODES: tuple[str, ...] = (
    "ja-JP", "en-US", "fr-FR", "es-ES", "de-DE", "it-IT", "nl-NL", "pt-PT", "ru-RU", "ko-KR",
    "zh-Hant", "zh-Hans", "fi-FI", "sv-SE", "da-DK", "no-NO", "pl-PL", "pt-BR", "es-419", "tr-TR",
    "en-GB", "ar-AE", "fr-CA", "cs-CZ", "hu-HU", "el-GR", "ro-RO", "th-TH", "vi-VN", "id-ID",
)

COUNTRY_CODES: tuple[str, ...] = (
    "AE", "AR", "AT", "AU", "BE", "BG", "BH", "BO", "BR", "CA", "CH", "CL", "CN", "CO", "CR",
    "CY", "CZ", "DE", "DK", "EC", "ES", "FI", "FR", "GB", "GR", "GT", "HK", "HN", "HR", "HU",
    "ID", "IE", "IL", "IN", "IS", "IT", "JP", "KR", "KW", "LB", "LU", "MT", "MX", "MY", "NI",
    "NL", "NO", "NZ", "OM", "PA", "PE", "PL", "PT", "PY", "QA", "RO", "RU", "SA", "SE", "SG",
    "SI", "SK", "SV", "TH", "TR", "TW", "UA", "US", "UY", "ZA",
)

# Bekannte param.json-Schlüssel -> kurze Beschreibung (Untermenge der 34 dokumentierten Felder).
PARAM_KNOWN_KEYS: "OrderedDict[str, str]" = OrderedDict([
    ("titleId", "Title-ID, z.B. PPSA00000"),
    ("contentId", "Content-ID, 36 Zeichen, z.B. UP0000-PPSA00000_00-0000000000000000"),
    ("conceptId", "Concept-ID (Produktfamilie über mehrere Content-IDs hinweg)"),
    ("masterVersion", "Master-Version, z.B. 01.00"),
    ("contentVersion", "Content-Version, z.B. 01.00"),
    ("targetContentVersion", "Ziel-Content-Version für Updates"),
    ("originContentVersion", "Ursprüngliche Content-Version"),
    ("versionFileUri", "URI der Versionsdatei für Update-Prüfung"),
    ("applicationDrmType", "DRM-Typ: standard/free/freemium"),
    ("applicationCategoryType", "Kategorie-Typ (Ganzzahl)"),
    ("contentBadgeType", "Badge-Typ (Ganzzahl)"),
    ("attribute", "Attribut-Flags (Ganzzahl)"),
    ("attribute2", "Attribut-Flags 2 (Ganzzahl)"),
    ("attribute3", "Attribut-Flags 3 (Ganzzahl)"),
    ("downloadDataSize", "Erwartete Download-Größe in Bytes"),
    ("deeplinkUri", "Deeplink-URI"),
    ("requiredSystemSoftwareVersion", "Mindest-Systemsoftware-Version (hex-kodiert)"),
    ("sdkVersion", "Verwendete SDK-Version (hex-kodiert)"),
    ("userDefinedParam1", "Benutzerdefinierter Parameter 1"),
    ("userDefinedParam2", "Benutzerdefinierter Parameter 2"),
    ("userDefinedParam3", "Benutzerdefinierter Parameter 3"),
    ("userDefinedParam4", "Benutzerdefinierter Parameter 4"),
    ("localizedParameters", "Objekt: defaultLanguage + je Sprache ein titleName"),
    ("ageLevel", "Objekt: je Land ein Alterslevel plus 'default'"),
    ("gameIntent", "Objekt: permittedIntents-Liste (launchActivity/joinSession)"),
    ("addcont", "Objekt: serviceIdForSharing-Liste für Zusatzinhalte"),
    ("pubtools", "Objekt: creationDate/submission/toolVersion"),
])

# Bekannte manifest.json-Schlüssel -> kurze Beschreibung.
MANIFEST_KNOWN_KEYS: "OrderedDict[str, str]" = OrderedDict([
    ("applicationName", "Anzeigename der Anwendung"),
    ("applicationVersion", "Versionsstring der Anwendung"),
    ("commitHash", "Commit-Hash des Builds"),
    ("bootAnimation", "Pfad/ID der Boot-Animation"),
    ("titleId", "Title-ID, z.B. PPSA00000"),
    ("repositoryUrl", "Quell-Repository-URL"),
    ("reactNativePlaystationVersion", "Version des React-Native-PlayStation-Frameworks"),
    ("twinTurbo", "Flag: TwinTurbo-Unterstützung (bool)"),
    ("enableHttpCache", "Flag: HTTP-Cache aktivieren (bool)"),
    ("enableAccessibility", "Liste aktivierter Accessibility-Funktionen"),
    ("applicationData", "Objekt: u.a. branchType"),
])

MANIFEST_CANONICAL_ORDER: tuple[str, ...] = (
    "applicationName", "applicationVersion", "commitHash", "bootAnimation", "titleId",
    "repositoryUrl", "reactNativePlaystationVersion", "enableAccessibility",
    "enableHttpCache", "applicationData", "twinTurbo",
)


def load_json(path: str) -> "OrderedDict[str, object]":
    """Lädt ein JSON-Dokument und erhält dabei die Schlüsselreihenfolge."""
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f, object_pairs_hook=OrderedDict)


def save_param_json(data: dict, path: str) -> None:
    """Schreibt ein param.json-Dokument: UTF-8 ohne BOM, 2-Leerzeichen-Einrückung."""
    _save_json(data, path, indent=2)


def save_manifest_json(data: dict, path: str) -> None:
    """Schreibt ein manifest.json-Dokument: UTF-8 ohne BOM, 4-Leerzeichen-Einrückung."""
    _save_json(data, path, indent=4)


def _save_json(data: dict, path: str, indent: int) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")


def create_default_param(title_id: str = "", content_id: str = "",
                         title: str = "") -> "OrderedDict[str, object]":
    """Erstellt ein minimales, leeres param.json-Grundgerüst.

    Args:
        title_id: Title-ID, z. B. ``PPSA19015``.
        content_id: Vollständige Content-ID, falls bekannt.
        title: Anzeigename. Wird als ``localizedParameters`` hinterlegt – genau
            dort, wo die Konsole und dieses Programm ihn suchen; ein Feld
            ``titleName`` auf oberster Ebene würde nirgends gelesen.
    """
    doc: "OrderedDict[str, object]" = OrderedDict()
    if title_id:
        doc["titleId"] = title_id
    if content_id:
        doc["contentId"] = content_id
    doc["applicationDrmType"] = "standard"
    doc["masterVersion"] = "01.00"
    doc["contentVersion"] = "01.00"
    if title:
        lokal: "OrderedDict[str, object]" = OrderedDict()
        lokal["defaultLanguage"] = "en-US"
        lokal["en-US"] = OrderedDict([("titleName", title)])
        doc["localizedParameters"] = lokal
    return doc


def create_default_manifest(application_name: str = "", title_id: str = "") -> "OrderedDict[str, object]":
    """Erstellt ein minimales manifest.json-Grundgerüst in kanonischer Feldreihenfolge."""
    doc: "OrderedDict[str, object]" = OrderedDict()
    if application_name:
        doc["applicationName"] = application_name
    doc["applicationVersion"] = "1.0.0"
    if title_id:
        doc["titleId"] = title_id
    return doc
