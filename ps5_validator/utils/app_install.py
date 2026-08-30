# -*- coding: utf-8 -*-
"""Installiert eine Anwendung direkt auf der PS5 - ohne Paketdatei.

Warum es diesen Weg gibt: Ein selbst gebautes Paket laesst sich zwar
installieren, aber die Kachel startet nicht. Am 29.08.2026 auf einer
echten Konsole nachgemessen - einmal mit einem Spiel-Backup, einmal mit
einem reinen Homebrew-Paket. Beide Male derselbe CE-100096-6, und im
Kernel-Protokoll derselbe Grund:

    verify_ppr_sblock_100()  error(-1) ekey[0xffffffff] skey[0xffffffff]
    verify_ppr_sblock_100()  verify error=0xffffffff -> EICV!

Die Konsole kann fuer solche Abbilder keine Schluessel ableiten und weist
deshalb den Integritaetswert des Superblocks zurueck. Das liegt nicht am
Paket, sondern am Schluesselplan - der ist ausserhalb der Konsole nicht
nachzubilden.

Der Weg hier umgeht das Paketformat vollstaendig. Die Dateien werden im
Klartext ins Dateisystem gelegt und ueber die Systemschnittstelle
sceAppInstUtilAppInstallAll registriert - warum nicht die
genauere Funktion, steht weiter unten. Ein verschluesseltes
Abbild entsteht dabei nie, also gibt es auch nichts aufzuschliessen -
dasselbe Prinzip, aus dem auch ShadowMount+ funktioniert.

Vorbild ist samples/install_app aus dem PS5-Payload-SDK von John
Toernblom (GPL-3). Das dortige Payload traegt die Title-ID fest
einkompiliert; das mitgelieferte appinst.elf liest sie stattdessen aus
/data/appinst.txt, damit ein Payload fuer alle Faelle genuegt.

Voraussetzung auf der Konsole: ftpsrv (Port 2121), dazu ein Weg, ein
Payload zu starten. Das ist ueblicherweise elfldr auf Port 9021; ist der
zu, weckt payload_versand ihn ueber den Payload Manager. Nur dort kommt
die Ausgabe des Payloads zurueck - sonst bleibt /data/appinst.log.

Ein Hinweis zur Firmware: Das SDK-Beispiel ruft
sceAppInstUtilAppInstallTitleDir. Diese Funktion ist nicht ueberall
vorhanden - am 29.08.2026 auf einer echten Konsole war sie es nicht, und
zwar auch unter elfldr nicht ("Unable to resolve"). Das mitgelieferte
Payload nimmt deshalb sceAppInstUtilAppInstallAll. Der Unterschied ist
nicht kosmetisch: Diese Funktion registriert alles Anstehende, nicht
gezielt eine Kennung.

Dieses Modul kennt keine Oberflaeche und keine Zustandsvariablen - es
laesst sich damit ohne laufendes Programm pruefen.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field

from . import payload_versand, self_reader

#: Port, auf dem elfldr Payloads entgegennimmt (prospero-deploy nutzt denselben).
ELFLDR_PORT = 9021

#: applicationCategoryType beim Registrieren. Die Anwendung liegt zu diesem
#: Zeitpunkt unter /user/app und gilt als gewoehnliche Anwendung.
KATEGORIE_INSTALL = 0

#: applicationCategoryType, das hinterher nachgereicht wird (0x02000000).
#: Erst damit startet die Kachel aus /system_ex.
KATEGORIE_SYSTEM = 33554432

#: Dort erwartet das Payload die Title-ID.
KENNUNGSDATEI = "/data/appinst.txt"

#: Dorthin schreibt das Payload seinen Verlauf - die einzige
#: Rueckmeldung, wenn es nicht ueber elfldr lief.
PROTOKOLLDATEI = "/data/appinst.log"

#: Dateiname und Ablage des mitgelieferten Payloads.
PAYLOAD_NAME = "appinst.elf"
PAYLOAD_ORDNER = "PS5-AppInstall"

#: applicationCategoryType einer Deeplink-Kachel (0x10000). Abgelesen an
#: den Kacheln, die auf der Konsole tatsaechlich laufen.
KATEGORIE_DEEPLINK = 65536

#: Die beiden Betriebsarten.
ART_PROGRAMM = "programm"    # eigenes eboot.bin, Vorbild samples/install_app
ART_DEEPLINK = "deeplink"    # nur Metadaten, oeffnet eine Weboberflaeche

SYSTEM_EX = "/system_ex/app"
USER_APP = "/user/app"

#: Ohne dieses Kommando ist /system_ex nur lesbar, und das Anlegen der
#: Ordner scheitert mit einem wenig sprechenden Fehler.
BESCHREIBBAR = "MTRW"


class AppInstallFehler(Exception):
    """Fehler, der dem Anwender wortwoertlich gezeigt werden kann."""


@dataclass
class AppAngaben:
    """Was ueber die zu installierende Anwendung bekannt ist."""

    ordner: str
    kennung: str
    name: str
    eboot: str
    param: str
    icon: str = ""
    param_system: str = ""
    huelle: str = ""
    autoritaet: str = ""
    art: str = ART_PROGRAMM
    uri: str = ""
    param_daten: dict = field(default_factory=dict)


def payload_finden(basis: str | None = None) -> str:
    """Sucht appinst.elf neben dem Programm.

    Im gebauten EXE liegt der Ordner im entpackten Verzeichnis, in der
    Quellfassung im Projektverzeichnis. Beide Faelle werden abgeklappert,
    statt sich auf einen zu verlassen.
    """
    kandidaten = []
    if basis:
        kandidaten.append(basis)
    for wurzel in (getattr(sys, "_MEIPASS", None),
                   os.path.dirname(os.path.abspath(sys.argv[0])),
                   os.path.dirname(os.path.dirname(os.path.dirname(
                       os.path.abspath(__file__))))):
        if wurzel:
            kandidaten.append(os.path.join(wurzel, PAYLOAD_ORDNER))
    for ordner in kandidaten:
        pfad = os.path.join(ordner, PAYLOAD_NAME)
        if os.path.isfile(pfad):
            return pfad
    raise AppInstallFehler(PAYLOAD_NAME + " nicht gefunden")


def kennung_gueltig(kennung: str) -> bool:
    """Prueft die Form einer Title-ID: vier Grossbuchstaben, fuenf Ziffern."""
    if len(kennung) != 9:
        return False
    return kennung[:4].isalpha() and kennung[:4].isupper() and kennung[4:].isdigit()


def param_lesen(pfad: str) -> dict:
    """Liest param.json; wirft mit klarem Text, wenn das misslingt."""
    try:
        with open(pfad, "rb") as fh:
            roh = fh.read()
    except OSError as exc:
        raise AppInstallFehler("param.json nicht lesbar: %s" % exc) from exc
    try:
        daten = json.loads(roh.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AppInstallFehler("param.json ist kein gueltiges JSON: %s" % exc) from exc
    if not isinstance(daten, dict):
        raise AppInstallFehler("param.json enthaelt kein Objekt")
    return daten


def titelname(param: dict, ersatz: str = "") -> str:
    """Holt den angezeigten Namen aus den localizedParameters."""
    lokal = param.get("localizedParameters")
    if isinstance(lokal, dict):
        sprache = lokal.get("defaultLanguage")
        reihe = []
        if isinstance(sprache, str):
            reihe.append(sprache)
        reihe.extend(k for k in lokal if k != "defaultLanguage")
        for schluessel in reihe:
            eintrag = lokal.get(schluessel)
            if isinstance(eintrag, dict):
                name = eintrag.get("titleName")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return ersatz


def _mit_kategorie(param: dict, kategorie: int) -> dict:
    kopie = dict(param)
    kopie["applicationCategoryType"] = kategorie
    return kopie


def installfassung(param: dict) -> dict:
    """param.json fuer den Registrierungsschritt.

    Die Kategorie wird bewusst gesetzt statt uebernommen: Steht in der
    Vorlage schon die Systemkategorie, laeuft die Registrierung ins Leere
    und niemand sieht, woran es lag.
    """
    return _mit_kategorie(param, KATEGORIE_INSTALL)


def systemfassung(param: dict) -> dict:
    """param.json, das hinterher nach /system_ex nachgereicht wird."""
    return _mit_kategorie(param, KATEGORIE_SYSTEM)


def als_json(param: dict) -> bytes:
    """Formt die Vorlage so, wie die Konsole sie erwartet (UTF-8, ohne BOM)."""
    text = json.dumps(param, indent=4, ensure_ascii=False, sort_keys=True)
    return (text + "\n").encode("utf-8")


def _eboot_beurteilen(pfad: str) -> tuple[str, str, list[str]]:
    """Bestimmt Huelle und Autoritaet von eboot.bin."""
    fehler: list[str] = []
    if self_reader.detect_elf(pfad):
        fehler.append("eboot.bin ist ein rohes ELF. Die Konsole startet nur ein "
                      "SELF mit Fake-Autoritaet - erst mit make_fself.py "
                      "signieren (--ptype fake).")
        return "ELF", "", fehler
    if not self_reader.detect_self(pfad):
        fehler.append("eboot.bin ist weder ELF noch SELF.")
        return "", "", fehler
    try:
        auskunft = self_reader.read_self(pfad)
    except Exception as exc:  # eine defekte Datei soll nicht das Fenster reissen
        return "SELF", "", ["eboot.bin nicht lesbar: %s" % exc]

    autoritaet = ""
    if auskunft.ext_info is not None:
        kategorie = auskunft.ext_info.authority_category
        autoritaet = "0x%016X (%s)" % (auskunft.ext_info.authority_id,
                                       auskunft.ext_info.authority_category_name)
        if kategorie == self_reader.AUTHORITY_CATEGORY_GENUINE:
            fehler.append("eboot.bin traegt eine echte Sony-Autoritaet. Ein solches "
                          "Modul laesst sich auf diesem Weg nicht starten.")
        elif kategorie == self_reader.AUTHORITY_CATEGORY_SDK_FAKE:
            # Am 29.08.2026 auf einer echten Konsole gemessen: Mit 0x38 kommt
            # der Start bis zum Prozess und scheitert dann am Entschluesseln
            # der SELF-Bloecke (CE-108262-9). Mit 0x31 - derselben Kategorie,
            # die auch libSceAmpr traegt - laeuft dieselbe Anwendung durch.
            fehler.append(
                "eboot.bin traegt die Autoritaet des Payload-SDK (Kategorie "
                "0x38). Damit entschluesselt die Konsole die SELF-Bloecke "
                "nicht und die Anwendung stuerzt beim Start ab "
                "(CE-108262-9). Neu signieren mit "
                "--paid 0x3100000000000002 --app-version 0x0 "
                "--fw-version 0x0.")
    verschluesselt = [s for s in auskunft.segments if s.encrypted]
    if verschluesselt:
        fehler.append("eboot.bin hat %d verschluesselte Segmente. Die Konsole "
                      "braeuchte dafuer Schluessel, die sich hier nicht "
                      "ableiten lassen." % len(verschluesselt))
    return auskunft.magic_name, autoritaet, fehler


def pruefen(ordner: str) -> tuple[AppAngaben | None, list[str], list[str]]:
    """Sieht nach, ob aus dem Ordner eine startfaehige Kachel werden kann.

    Rueckgabe: (Angaben oder None, Fehler, Hinweise). Fehler verhindern die
    Installation, Hinweise nicht.
    """
    fehler: list[str] = []
    hinweise: list[str] = []

    if not os.path.isdir(ordner):
        return None, ["Kein Ordner: %s" % ordner], hinweise

    eboot = os.path.join(ordner, "eboot.bin")
    if not os.path.isfile(eboot):
        try:
            lose = [n for n in sorted(os.listdir(ordner))
                    if n.lower().endswith((".elf", ".bin"))]
        except OSError:
            lose = []
        zusatz = (" Gefunden: %s - diese Datei muesste eboot.bin heissen."
                  % ", ".join(lose)) if lose else ""
        return None, ["eboot.bin fehlt im Ordner." + zusatz], hinweise

    param_pfad = os.path.join(ordner, "sce_sys", "param.json")
    if not os.path.isfile(param_pfad):
        if os.path.isfile(os.path.join(ordner, "sce_sys", "param.sfo")):
            return None, ["Der Ordner traegt eine PS4-param.sfo statt einer "
                          "param.json. Dieser Weg braucht die PS5-Fassung."], hinweise
        return None, ["sce_sys/param.json fehlt."], hinweise

    param = param_lesen(param_pfad)
    kennung = param.get("titleId")
    if not isinstance(kennung, str) or not kennung.strip():
        return None, ["param.json nennt keine titleId."], hinweise
    kennung = kennung.strip()
    if not kennung_gueltig(kennung):
        fehler.append("titleId %r hat nicht die Form ABCD12345." % kennung)

    huelle, autoritaet, eboot_fehler = _eboot_beurteilen(eboot)
    fehler.extend(eboot_fehler)

    icon = ""
    for kandidat in (os.path.join(ordner, "sce_sys", "icon0.png"),
                     os.path.join(ordner, "icon0.png")):
        if os.path.isfile(kandidat):
            icon = kandidat
            break
    if not icon:
        hinweise.append("icon0.png fehlt - die Kachel bleibt dann ohne Bild.")

    param_system = os.path.join(ordner, "sce_sys", "param.json.system")
    if not os.path.isfile(param_system):
        param_system = ""
        hinweise.append("param.json.system fehlt und wird aus param.json "
                        "erzeugt (applicationCategoryType %d)." % KATEGORIE_SYSTEM)

    angaben = AppAngaben(
        ordner=ordner, kennung=kennung, name=titelname(param, kennung),
        eboot=eboot, param=param_pfad, icon=icon, param_system=param_system,
        huelle=huelle, autoritaet=autoritaet, param_daten=param)
    return angaben, fehler, hinweise


def deeplink_param(kennung: str, name: str, uri: str) -> dict:
    """Baut die param.json einer Deeplink-Kachel.

    Der Aufbau ist keiner Vorlage entnommen, sondern den Kacheln
    abgelesen, die auf einer echten Konsole laufen (Payload Manager,
    Homebrew Launcher, WebKit Autoload).
    """
    return {
        "applicationCategoryType": KATEGORIE_DEEPLINK,
        "deeplinkUri": uri,
        "localizedParameters": {
            "defaultLanguage": "en-US",
            "en-US": {"titleName": name or kennung},
        },
        "titleId": kennung,
    }


def uri_gueltig(uri: str) -> bool:
    """Prueft die Adresse grob: http/https und ein Rumpf dahinter."""
    text = (uri or "").strip()
    for schema in ("http://", "https://"):
        if text.lower().startswith(schema) and len(text) > len(schema):
            return True
    return False


def deeplink_pruefen(kennung: str, name: str, uri: str,
                     icon: str = "") -> tuple[AppAngaben | None, list[str], list[str]]:
    """Sieht nach, ob aus den Angaben eine Deeplink-Kachel werden kann."""
    fehler: list[str] = []
    hinweise: list[str] = []

    kennung = (kennung or "").strip()
    if not kennung:
        return None, ["Es ist keine Title-ID angegeben."], hinweise
    if not kennung_gueltig(kennung):
        fehler.append("titleId %r hat nicht die Form ABCD12345." % kennung)

    if not uri_gueltig(uri):
        fehler.append("Die Adresse muss mit http:// oder https:// beginnen.")

    if icon and not os.path.isfile(icon):
        fehler.append("Das Symbolbild gibt es nicht: %s" % icon)
        icon = ""
    if not icon:
        hinweise.append("icon0.png fehlt - die Kachel bleibt dann ohne Bild.")

    uri = (uri or "").strip()
    if "127.0.0.1" not in uri and "localhost" not in uri:
        hinweise.append("Die Adresse zeigt nicht auf die Konsole selbst. "
                        "Das geht, ist aber ungewoehnlich - die ueblichen "
                        "Kacheln oeffnen eine Oberflaeche, die ein Payload "
                        "auf der Konsole bereitstellt.")

    angaben = AppAngaben(
        ordner="", kennung=kennung, name=(name or "").strip() or kennung,
        eboot="", param="", icon=icon, art=ART_DEEPLINK, uri=uri,
        param_daten=deeplink_param(kennung, name, uri))
    return angaben, fehler, hinweise


def deeplink_zielordner(kennung: str) -> tuple[str, ...]:
    """Die zwei Ordner einer Deeplink-Kachel - /system_ex bleibt unberuehrt."""
    return (USER_APP + "/" + kennung,
            USER_APP + "/" + kennung + "/sce_sys")


def zielordner(kennung: str) -> tuple[str, ...]:
    """Die vier Ordner, die auf der Konsole angelegt werden muessen."""
    return (SYSTEM_EX + "/" + kennung,
            SYSTEM_EX + "/" + kennung + "/sce_sys",
            USER_APP + "/" + kennung,
            USER_APP + "/" + kennung + "/sce_sys")


def payload_senden(host: str, daten: bytes, port: int = ELFLDR_PORT,
                   timeout: float = 30.0, elfldr_pfad: str = "") -> str:
    """Schickt das Payload und liefert zurueck, was es ausgegeben hat.

    Der Weg wird nicht hier entschieden, sondern in payload_versand:
    elfldr, wenn er lauscht; sonst wird er ueber den Payload Manager
    gestartet. Nur der letzte Ausweg - direkt ueber den Payload
    Manager - liefert nichts zurueck; dann bleibt die Protokolldatei
    auf der Konsole.
    """
    _weg, ausgabe, _bemerkung = payload_versand.senden(
        host, daten, PAYLOAD_NAME, elfldr_port=port,
        elfldr_pfad=elfldr_pfad)
    return ausgabe


def protokoll_lesen(ftp) -> str:
    """Holt /data/appinst.log von der Konsole.

    Gebraucht, wenn das Payload ueber den Payload Manager lief: Der
    reicht die Ausgabe nicht zurueck, und ohne diese Datei waere ein
    Fehlschlag von einem Erfolg nicht zu unterscheiden.
    """
    import io as _io

    puffer = _io.BytesIO()
    try:
        ftp.retrbinary("RETR " + PROTOKOLLDATEI, puffer.write)
    except Exception:
        return ""
    return puffer.getvalue().decode("utf-8", "replace").strip()


def antwort_beurteilen(antwort: str) -> tuple[bool, str]:
    """Liest aus der Payload-Ausgabe, ob das Registrieren geklappt hat."""
    if not antwort:
        return False, ("Das Payload hat nichts zurueckgemeldet. Laeuft elfldr "
                       "auf Port %d?" % ELFLDR_PORT)
    for zeile in antwort.splitlines():
        text = zeile.strip()
        if text.endswith("registriert"):
            return True, text
    return False, antwort.strip().splitlines()[-1]
