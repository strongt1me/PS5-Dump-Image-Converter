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
import logging
import os
import re
from collections import OrderedDict

#: Beide Lesefunktionen fangen OSError ab und schreiben dorthin.
#: Ohne diese Zeile stuerzte der Fehlerbehandler selbst mit einem
#: NameError ab - aus einem abgefangenen Lesefehler wurde so ein
#: Programmabbruch.
logger = logging.getLogger("PS5Converter.param_manifest")

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


def read_title_name_from_trophy(source_dir: str) -> str:
    """Liest den Anzeigenamen aus ``sce_sys/trophy2/trophy00.ucp``.

    Der Titel ist das eine Feld, das bisher nur der Online-Nachschlag liefern
    konnte - dabei liegt er im Backup selbst. Die Trophaeendatei ist ein
    Container mit eigenem Kopf (Magic ``b2 28 c6 0a``), traegt darin aber einen
    unverschluesselten JSON-Block:

        "npCommId":"NPWR27856_00","metadata":{"titleMetadata":{"name":"Arkanoid - Eternal Battle"}, ...

    An "Arkanoid Eternal Battle" nachgemessen: Der Block steht rund 7,78 MB
    tief in einer 7,81-MB-Datei, also fast am Ende. Gesucht wird deshalb von
    hinten - ein Durchlauf von vorn liest fast die ganze Datei umsonst.

    Die Trophaeentexte sind mehrsprachig und enthalten Zeichen aus vielen
    Schriften; deshalb wird streng als UTF-8 mit Ersatzzeichen dekodiert und
    nicht als latin-1 geraten.

    Returns:
        Anzeigename, sonst leerer String.
    """
    pfad = os.path.join(source_dir, "sce_sys", "trophy2", "trophy00.ucp")
    if not os.path.isfile(pfad):
        return ""

    muster = re.compile(rb'"titleMetadata"\s*:\s*\{\s*"name"\s*:\s*"([^"]{1,120})"')
    blockgroesse = 4 * 1024 * 1024
    ueberlappung = 512
    try:
        groesse = os.path.getsize(pfad)
        with open(pfad, "rb") as datei:
            # Von hinten nach vorn, weil der Metadatenblock dort liegt.
            gelesen = 0
            rest = b""
            while gelesen < groesse:
                schritt = min(blockgroesse, groesse - gelesen)
                datei.seek(groesse - gelesen - schritt)
                block = datei.read(schritt)
                gelesen += schritt
                treffer = muster.search(block + rest)
                if treffer:
                    return treffer.group(1).decode("utf-8", "replace").strip()
                rest = block[:ueberlappung]
    except OSError as exc:
        logger.debug("Trophaeendatei nicht lesbar (%s): %s", pfad, exc)
    return ""


def read_content_version_from_pfs(source_dir: str) -> str:
    """Liest die Inhaltsversion aus ``sce_sys/pfs-version.dat``.

    Die Datei ist zehn Byte reiner Text im langen Versionsformat, etwa
    ``01.002.000`` - genau die Form, die ``contentVersion`` in der param.json
    braucht. Ohne sie muesste beim Neuanlegen pauschal ``01.000.000``
    eingetragen werden, was bei einem gepatchten Spiel schlicht falsch ist.

    Sie fehlt in etwa jedem sechzehnten Backup (30 von 32 nachgesehen) - je
    nach verwendetem Dumper wird der Marker nicht mitgeschrieben. Deshalb nur
    eine Quelle unter mehreren, kein Pflichtfeld.

    Returns:
        Version im Format ``01.002.000``, sonst leerer String.
    """
    pfad = os.path.join(source_dir, "sce_sys", "pfs-version.dat")
    try:
        with open(pfad, "rb") as datei:
            roh = datei.read(32)
    except OSError:
        return ""
    text = roh.decode("ascii", "ignore").strip()
    return text if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}", text) else ""


def read_metadata_from_dump(source_dir: str) -> "OrderedDict[str, str]":
    """Sammelt alle param.json-Felder, die im Backup selbst stehen.

    Damit laesst sich eine fehlende param.json weitgehend ohne Netzzugriff
    wiederherstellen. Was hier fehlt, ist die Content-ID - die steht in keiner
    Datei des Dumps und bleibt dem Online-Nachschlag vorbehalten.

    Returns:
        Dict mit den gefundenen Schluesseln ``titleId``, ``titleName`` und
        ``contentVersion``; nicht gefundene Felder fehlen darin.
    """
    gefunden: "OrderedDict[str, str]" = OrderedDict()
    title_id = read_title_id_from_dump(source_dir)
    if title_id:
        gefunden["titleId"] = title_id
    name = read_title_name_from_trophy(source_dir)
    if name:
        gefunden["titleName"] = name
    version = read_content_version_from_pfs(source_dir)
    if version:
        gefunden["contentVersion"] = version
    return gefunden


def read_title_id_from_eboot(source_dir: str, hoechstens: int = 64 * 1024 * 1024) -> str:
    """Liest die Title-ID aus der ``eboot.bin`` eines Dump-Ordners.

    Zweite Quelle neben ``nptitle.dat`` - und die einzige, die auch dann noch
    traegt, wenn der Ordner umbenannt wurde und ``sce_sys`` unvollstaendig ist.

    An "Arkanoid Eternal Battle" (26 MB eboot.bin) nachgemessen: Die Kennung
    steht dort genau **einmal**, als ``PPSA06328_00`` mit demselben
    ``_00``-Suffix wie in der ``nptitle.dat``, und stimmt mit ihr ueberein.

    Was sich dort **nicht** holen laesst: der Anzeigename. Die Treffer auf den
    Spielnamen sind Klassenbezeichner aus dem Programmcode
    (``ArkanoidBallMoveSystem``), kein Titel. Eine Content-ID kommt gar nicht
    vor - beides muss weiterhin online nachgeschlagen werden.

    Gelesen wird blockweise mit Ueberlappung statt am Stueck: Eine eboot.bin
    kann mehrere hundert Megabyte gross sein, und die Kennung darf nicht
    zwischen zwei Bloecken zerrissen werden.

    Args:
        source_dir: Dump-Ordner (die eboot.bin wird darin erwartet).
        hoechstens: Obergrenze der gelesenen Bytes.

    Returns:
        Title-ID ohne Suffix, sonst leerer String.
    """
    pfad = os.path.join(source_dir, "eboot.bin")
    if not os.path.isfile(pfad):
        return ""

    blockgroesse = 4 * 1024 * 1024
    # Ein Treffer ist neun Zeichen lang; sechzehn Byte Ueberlappung genuegen,
    # damit keiner an einer Blockgrenze verlorengeht.
    ueberlappung = 16
    gelesen = 0
    rest = b""
    try:
        with open(pfad, "rb") as datei:
            while gelesen < hoechstens:
                block = datei.read(blockgroesse)
                if not block:
                    break
                gelesen += len(block)
                treffer = _TITLE_ID_PATTERN.search((rest + block).decode("latin-1"))
                if treffer:
                    return treffer.group(0)
                rest = block[-ueberlappung:]
    except OSError as exc:
        logger.debug("eboot.bin nicht lesbar (%s): %s", pfad, exc)
    return ""


def read_title_id_from_dump(source_dir: str) -> str:
    """Sucht die Title-ID eines Dump-Ordners in zwei Quellen.

    Zuerst ``sce_sys/nptitle.dat``: An 32 echten Backups nachgemessen stand die
    Kennung dort ausnahmslos und stimmte ausnahmslos mit der param.json
    ueberein. Fehlt die Datei - etwa in einem unvollstaendigen Dump -, wird die
    ``eboot.bin`` durchsucht; sie traegt dieselbe Kennung und laesst sich, im
    Gegensatz zum Ordnernamen, nicht versehentlich umbenennen.
    """
    aus_nptitle = read_title_id_from_nptitle(
        os.path.join(source_dir, "sce_sys", NPTITLE_FILE_NAME)
    )
    if aus_nptitle:
        return aus_nptitle
    return read_title_id_from_eboot(source_dir)

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
                         title: str = "",
                         content_version: str = "") -> "OrderedDict[str, object]":
    """Erstellt ein vollstaendiges, gueltiges param.json-Grundgeruest.

    **Warum das mehr ist als ein Minimalgeruest:** Bis v1.8.52 schrieb diese
    Funktion vier Felder - titleId, applicationDrmType, masterVersion und
    contentVersion. Solange niemand den Inhalt prueft, faellt das nicht auf.
    Seit v1.8.51 prueft das Programm die Datei inhaltlich, und seither meldete
    ausgerechnet die selbst erzeugte Datei drei Fehler:

    * ``applicationCategoryType`` fehlte - ohne dieses Feld erkennt die Konsole
      gar keinen Titel.
    * ``localizedParameters`` fehlte, sobald kein Anzeigename bekannt war.
    * ``contentVersion`` stand als ``"01.00"`` da. Das ist das Format von
      ``masterVersion``; die Inhaltsversion braucht die lange Form
      ``"01.000.000"``.

    Erzeugt wird deshalb ein Dokument, das die Pruefung besteht. Die Feldwerte
    stammen aus ``param_check.neu_anlegen``, damit es fuer "wie sieht eine
    gueltige param.json aus" nur eine Stelle im Programm gibt.

    Args:
        title_id: Title-ID, z. B. ``PPSA19015``.
        content_id: Vollstaendige Content-ID, falls bekannt.
        title: Anzeigename. Wird als ``localizedParameters`` hinterlegt - genau
            dort, wo die Konsole und dieses Programm ihn suchen.
    """
    # Bewusst hier importiert und nicht am Modulkopf: param_check holt sich von
    # hier die DRM-Liste, ein Import oben ergaebe einen Ringschluss.
    from ps5_validator.utils.param_check import neu_anlegen

    return neu_anlegen(title_id=title_id, content_id=content_id, titel=title,
                       inhaltsversion=content_version)


def create_default_manifest(application_name: str = "", title_id: str = "") -> "OrderedDict[str, object]":
    """Erstellt ein minimales manifest.json-Grundgerüst in kanonischer Feldreihenfolge."""
    doc: "OrderedDict[str, object]" = OrderedDict()
    if application_name:
        doc["applicationName"] = application_name
    doc["applicationVersion"] = "1.0.0"
    if title_id:
        doc["titleId"] = title_id
    return doc
