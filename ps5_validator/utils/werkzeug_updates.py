# -*- coding: utf-8 -*-
"""Updates fuer alle mitgelieferten Werkzeuge: pruefen, anbieten, holen (seit v1.9.72).

Der Knopf **Updates** auf der Seite „Konsole & Payloads“ oeffnet ein Fenster, das jedes mitgelieferte Werkzeug beim
Projekt seines Autors nachschlaegt - die ELF-Payloads in ``helloworld/``, den WebKit Autoloader, AMPR EMU und die
Engines (MkPFS, UFS2Tool, LibProsperoPkg, OrbisPkgTool, PS5-PKG-Tool, PS5 Wee Tools, 7-Zip ...). Was neuer ist, wird
zur Auswahl angeboten und auf Wunsch geholt.

**Zwei Teile, bewusst getrennt** - wie in ``ampr_updates``:

* **Das Urteil** - reine Funktionen: Fassungen lesen und vergleichen, Freigaben deuten, Angebote und Zielnamen
  berechnen. Sie holen nichts. Damit laesst sich jede Regel ohne Netz pruefen (``test_werkzeug_updates.py`` gegen eine
  gespeicherte Antwort der Schnittstellen, die auch belegt, dass die Zielnamen mit den heutigen Dateinamen
  uebereinstimmen).
* **Das Holen** - die Abfrage und das Laden stecken in :class:`Netz`, das der Aufrufer mitbringt. Tests geben eine
  Nachbildung mit. Nichts in diesem Modul faengt von selbst an: **Netzzugriff nur auf Knopfdruck** (Regel seit
  v1.8.74). :class:`Netz` ist die einzige Stelle, die hier ins Netz geht.

**Was geholt wird, landet nie im mitgelieferten Bestand.** Neue Dateien kommen in den Ordner
``<Einstellungsordner>/Werkzeug-Updates/<Ort>/`` (immer beschreibbar, ueberlebt neue Programmfassungen); das Programm
nimmt dort bei jedem Muster die **hoechste Fassung** aus Bestand und Update-Ordner (:func:`beste_datei`). Es wird
nichts geloescht oder ueberschrieben, was mitgeliefert ist; eine geholte Datei ersetzt hoechstens eine fruehere geholte
gleichen Namens.

**Jede Datei wird geprueft, bevor sie an ihren Platz kommt:** Groesse gegen die Angabe der Freigabe und SHA-256 gegen
die Pruefsumme, die GitHub zu jedem Anhang fuehrt (bei Codeberg: die danebenliegende ``.sha256``-Datei). Mehrteilige
Werkzeuge (WebKit Autoloader: drei Dateien) kommen ganz oder gar nicht.

**Wo sich ein Austausch nicht von selbst verbietet, wird er nur gemeldet.** Engines mit eigenen Anpassungen
(UFS2Tool, LibProsperoPkg, PS5-PKG-Tool), Werkzeuge, deren Freigabe nur ein Archiv ist (OffAct, Dump Installer,
ActRemoteLink), und Dateien ohne Fassung im Namen (unjail) zeigen das Urteil und den Link zur Freigabe-Seite -
herunterladen laesst sich dort nichts, weil das Einbauen Handarbeit mit Gegenprobe ist
(``references/werkzeug-updates.md`` des Projekt-Skills).

**Anfragegrenze:** GitHub erlaubt ohne Anmeldung 60 Anfragen je Stunde und Adresse; die Pruefung braucht rund 50. Jede
Antwort wird mit ihrem ETag zwischengespeichert; eine zweite Pruefung fragt mit ``If-None-Match`` nach, und eine
Antwort 304 zaehlt nicht mit. Scheitert eine Quelle (Netz weg, Grenze erreicht), gilt ihr letzter gespeicherter Stand
- mit dem Datum dazu.
"""
from __future__ import annotations

import datetime
import fnmatch
import hashlib
import json
import logging
import os
import re
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable, NamedTuple, Sequence

from ps5_validator.utils import ampr_updates

logger = logging.getLogger("PS5Converter.utils.werkzeug_updates")

#: Unterordner des Einstellungsordners fuer geholte Dateien; darin ein Ordner je Bestandsordner.
UNTERORDNER = "Werkzeug-Updates"
#: Zwischenspeicher der Freigaben (im Ordner :data:`UNTERORDNER`, nicht in einem Ort).
SPEICHER_DATEI = "freigaben.json"
#: Die Bestandsordner, in denen Dateien ersetzt werden koennen.
ORT_PAYLOADS = "helloworld"
ORT_WEBKIT = "PS5 WebKit Autoloader"
ORTE = (ORT_PAYLOADS, ORT_WEBKIT)

#: Gruppen, in der Reihenfolge der Anzeige.
GRUPPE_PAYLOAD = "payload"
GRUPPE_WEBKIT = "webkit"
GRUPPE_EMU = "emu"
GRUPPE_WERKZEUG = "werkzeug"
GRUPPE_EIGEN = "eigen"
GRUPPEN = (GRUPPE_PAYLOAD, GRUPPE_WEBKIT, GRUPPE_EMU, GRUPPE_WERKZEUG, GRUPPE_EIGEN)

#: Wie ein Werkzeug behandelt wird.
ART_DATEI = "datei"        # eine oder mehrere Dateien, die sich 1:1 ablegen lassen
ART_HINWEIS = "hinweis"    # nur melden (Anpassungen, Archiv, keine Fassung im Namen)
ART_EMU = "emu"            # AMPR EMU - eigener Weg ueber ``ampr_updates``
ART_KEINE = "keine"        # Eigenbestand, nicht vergleichbar oder keine oeffentliche Quelle

#: Urteile ueber ein Werkzeug.
STATUS_NICHT_GEPRUEFT = "nicht_geprueft"
STATUS_NEU = "neu"                  # neuer und ladbar
STATUS_NEU_HINWEIS = "neu_hinweis"  # neuer, aber nur von Hand einzubauen
STATUS_AKTUELL = "aktuell"
STATUS_NEUER = "neuer"              # die mitgelieferte Fassung ist neuer als jede Freigabe
STATUS_UNKLAR = "unklar"            # Fassungen nicht eindeutig vergleichbar
STATUS_FEHLER = "fehler"            # Quelle nicht erreichbar
STATUS_OHNE_QUELLE = "ohne_quelle"

#: Meldungen eines Befunds (die Oberflaeche uebersetzt sie).
MELDUNG_NETZ = "netz"
MELDUNG_LIMIT = "limit"
MELDUNG_NICHT_GEFUNDEN = "nicht_gefunden"
MELDUNG_ANTWORT = "antwort"
MELDUNG_ABGEBROCHEN = "abgebrochen"
MELDUNG_KEINE_FREIGABE = "keine_freigabe"
MELDUNG_KEINE_DATEI = "keine_datei"
MELDUNG_LOKAL_UNLESBAR = "lokal_unlesbar"
MELDUNG_FASSUNG_UNKLAR = "fassung_unklar"

#: Hoechstens so viele Freigaben werden je Quelle gelesen (eine Anfrage, egal wie viele - gross genug, dass bei
#: AMPR EMU auch die Fassungen einer aelteren Variante noch darin stehen).
FREIGABEN_JE_QUELLE = 12
#: Mehr als das wird nie geladen (die groesste mitgelieferte Datei hat 19 MB).
GRENZE_BYTES = 200 * 1024 * 1024
#: Frist je Anfrage und je Block beim Laden, in Sekunden.
FRIST = 20

_ADRESSEN = {
    "github": "https://api.github.com/repos/%s/releases?per_page=" + str(FREIGABEN_JE_QUELLE),
    "codeberg": "https://codeberg.org/api/v1/repos/%s/releases?limit=" + str(FREIGABEN_JE_QUELLE),
}
_SEITEN = {
    "github": "https://github.com/%s/releases",
    "codeberg": "https://codeberg.org/%s/releases",
}
#: Dahin darf eine Datei-Adresse aus einer Antwort zeigen (Umleitungen der beiden Anbieter folgt urllib selbst).
_ERLAUBTE_ADRESSEN = ("https://github.com/", "https://codeberg.org/")
#: Nur diese Dateiarten werden abgelegt.
_ERLAUBTE_ENDUNGEN = (".elf", ".exe", ".py")
#: Eine Fassung, die in einen Dateinamen eingesetzt wird, darf nur das enthalten.
_SICHER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,40}")


# ---------------------------------------------------------------------------
# Fassungen
# ---------------------------------------------------------------------------
_STUFEN = {"alpha": 0, "beta": 1, "rc": 2}
#: Nach der Zahl: Stufe (``beta4``, ``-beta2``, ``alpha13fix1``) oder Bauzahl (``-3``).
_NACHSILBE = r"(?:[-_.]?(?:alpha|beta|rc)\d*(?:fix\d+)?|-\d+(?![\w]))"
_DATEI_FASSUNG = re.compile(r"[-_]v?(\d+(?:\.\d+)+%s?)" % _NACHSILBE, re.IGNORECASE)
_TAG_FASSUNG = re.compile(r"^[vV]?(\d+(?:\.\d+)*%s?)" % _NACHSILBE, re.IGNORECASE)
_ZAHLEN = re.compile(r"(\d+(?:\.\d+)*)")
_STUFE = re.compile(r"[-_.]?(alpha|beta|rc)(\d*)(?:fix(\d+))?", re.IGNORECASE)
_BAU = re.compile(r"-(\d+)$")
_RC = re.compile(r"rc(\d+)", re.IGNORECASE)
_ACHT_ZIFFERN = re.compile(r"(?<!\d)(\d{8})(?!\d)")
_DATUM = re.compile(r"(\d{4}-\d{2}-\d{2})")
_ORDNER_FASSUNG = re.compile(r"-(\d+(?:\.\d+)+)$")
_STELLEN = 6


def _zerlegen(fassung: str) -> tuple[tuple, str]:
    """``(Schluessel, Rest)``: der Schluessel zum Vergleichen, der Rest ist, was keine Zahl und keine Stufe ist."""
    text = str(fassung or "").strip().lstrip("vV")
    treffer = _ZAHLEN.match(text)
    if not treffer:
        return (), ""
    zahlen = [int(z) for z in treffer.group(1).split(".")]
    zahlen += [0] * (_STELLEN - len(zahlen))
    rest = text[treffer.end():]
    stufe, nummer, fix, bau = 3, 0, 0, 0
    stufentreffer = _STUFE.match(rest)
    if stufentreffer:
        stufe = _STUFEN[stufentreffer.group(1).lower()]
        nummer = int(stufentreffer.group(2) or 0)
        fix = int(stufentreffer.group(3) or 0)
        rest = rest[stufentreffer.end():]
    else:
        bautreffer = _BAU.match(rest)
        if bautreffer:
            bau = int(bautreffer.group(1))
            rest = rest[bautreffer.end():]
    return (tuple(zahlen), stufe, nummer, fix, bau), rest.strip().lstrip("-_.+").lower()


def fassungsschluessel(fassung: str) -> tuple:
    """Vergleichsschluessel einer Fassung: ``(Zahlen, Stufe, Stufennummer, fix, Bauzahl)``.

    Zahlenweise und aufgefuellt (``0.4`` gegen ``0.4.1``), eine Vorabstufe liegt unter der fertigen Fassung
    (``1.7beta4`` < ``1.7``), eine Bauzahl zaehlt hoch (``1.37.0-3`` > ``1.37.0-2``). Ein Anhang, der weder Stufe
    noch Zahl ist (``-915a65e`` hinter ``0.1.5``), zaehlt nicht mit - :func:`vergleichen` meldet dann "unklar",
    wenn die Zahlen gleich und die Reste verschieden sind.

    Returns:
        ``()``, wenn gar keine Zahl zu lesen ist.
    """
    return _zerlegen(fassung)[0]


def fassung_aus_ordnername(name: str) -> str:
    """``MkPFS-1.1.0`` -> ``1.1.0``; ohne Fassung am Ende leer."""
    treffer = _ORDNER_FASSUNG.search(os.path.basename(str(name or "").rstrip("/\\")))
    return treffer.group(1) if treffer else ""


def fassung_aus_datei(name: str, modus: str = "zahl", vorlage: str = "") -> str:
    """Die Fassung aus einem Dateinamen.

    ``zahl`` (und ``nur_zahl``): die erste Fassungszahl hinter ``_``/``-`` (mit Stufe oder Bauzahl). ``tag``: der
    Teil, den ``vorlage`` (``prefix{f}suffix``) offen laesst. ``rc``, ``datum8`` und ``datum``: die Marke ``rc51``,
    ``20260930`` bzw. ``2026-04-09`` im Namen.
    """
    stamm = os.path.splitext(os.path.basename(name))[0]
    if modus == "tag" and vorlage:
        vorn, _, hinten = os.path.splitext(vorlage)[0].partition("{f}")
        if stamm.startswith(vorn) and stamm.endswith(hinten):
            rest = stamm[len(vorn):len(stamm) - len(hinten)]
            return rest
        return ""
    if modus == "rc":
        treffer = _RC.search(stamm)
        return "rc" + treffer.group(1) if treffer else ""
    if modus == "datum8":
        treffer = _ACHT_ZIFFERN.search(stamm)
        return treffer.group(1) if treffer else ""
    if modus == "datum":
        treffer = _DATUM.search(stamm)
        return treffer.group(1) if treffer else ""
    treffer = _DATEI_FASSUNG.search(stamm)
    return treffer.group(1) if treffer else ""


def fassung_aus_tag(tag: str, modus: str = "zahl", datum: str = "") -> str:
    """Die Fassung aus der Marke einer Freigabe (``datum``: ``2026-04-09`` ... fuer Modus ``datum``)."""
    tag = str(tag or "").strip()
    if modus == "tag":
        return tag[1:] if tag[:1] in "vV" and tag[1:2].isdigit() else tag
    if modus == "rc":
        treffer = _RC.search(tag)
        return "rc" + treffer.group(1) if treffer else ""
    if modus == "datum8":
        treffer = _ACHT_ZIFFERN.search(tag)
        return treffer.group(1) if treffer else ""
    if modus == "datum":
        return str(datum or "")[:10]
    treffer = _TAG_FASSUNG.match(tag)
    return treffer.group(1) if treffer else ""


def _schluessel(fassung: str, modus: str) -> tuple:
    if modus in ("rc", "datum8"):
        zahl = re.sub(r"\D", "", fassung or "")
        return (int(zahl),) if zahl else ()
    if modus == "datum":
        return (fassung,) if _DATUM.fullmatch(fassung or "") else ()
    schluessel = fassungsschluessel(fassung)
    if modus == "nur_zahl":
        return schluessel[:1]
    return schluessel


def vergleichen(lokal: str, neu: str, modus: str = "zahl") -> str:
    """``"neu"``, ``"aktuell"``, ``"neuer"`` (lokal ist neuer als die Freigabe) oder ``"unklar"``."""
    a, b = _schluessel(lokal, modus), _schluessel(neu, modus)
    if not a or not b:
        return "unklar"
    if b > a:
        return "neu"
    if b < a:
        return "neuer"
    if modus != "zahl":
        return "aktuell"
    return "aktuell" if _zerlegen(lokal)[1] == _zerlegen(neu)[1] else "unklar"


def datei_schluessel(dateiname: str) -> tuple:
    """Sortierschluessel fuer Dateien desselben Musters - die neueste liegt am Ende.

    Ersetzt die Sortierung nach ``_v<Zahl>``: Auch ``ps5upload-6.7.3.elf`` (kein ``_v``), ``1.7beta4`` und
    ``0.9.0-beta2`` ordnen sich richtig (``6.10.0`` hinter ``6.9.0``, Vorabfassung unter der fertigen). Ohne lesbare
    Fassung entscheidet der Name.
    """
    stamm = os.path.basename(dateiname)
    schluessel = fassungsschluessel(fassung_aus_datei(stamm))
    if schluessel:
        return (1, schluessel, stamm.lower())
    return (0, ((0,) * _STELLEN, 0, 0, 0, 0), stamm.lower())


# ---------------------------------------------------------------------------
# Freigaben deuten
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Anhang:
    name: str
    groesse: int = 0
    digest: str = ""
    adresse: str = ""


@dataclass(frozen=True)
class Freigabe:
    tag: str
    name: str = ""
    vorab: bool = False
    entwurf: bool = False
    datum: str = ""
    seite: str = ""
    anhaenge: tuple[Anhang, ...] = ()


def _ist_liste(roh: "str | bytes | list") -> bool:
    if isinstance(roh, list):
        return True
    try:
        return isinstance(json.loads(roh), list)
    except (ValueError, TypeError):
        return False


def freigaben_lesen(roh: "str | bytes | list") -> list[Freigabe]:
    """Liest die Antwort von GitHub oder Forgejo (Codeberg) - oder den gekuerzten Zwischenspeicher.

    Beide Schnittstellen nennen die Felder gleich. Unbrauchbares wird uebersprungen, nie geworfen.
    """
    if isinstance(roh, (str, bytes, bytearray)):
        try:
            daten = json.loads(roh)
        except (ValueError, TypeError):
            return []
    else:
        daten = roh
    if not isinstance(daten, list):
        return []
    erg: list[Freigabe] = []
    for eintrag in daten:
        if not isinstance(eintrag, dict):
            continue
        tag = eintrag.get("tag_name") or eintrag.get("tag")
        if not tag:
            continue
        anhaenge = []
        for a in eintrag.get("assets") or eintrag.get("anhaenge") or []:
            if isinstance(a, dict) and a.get("name"):
                try:
                    groesse = int(a.get("size") or a.get("groesse") or 0)
                except (TypeError, ValueError):
                    groesse = 0
                anhaenge.append(Anhang(
                    name=str(a["name"]), groesse=groesse, digest=str(a.get("digest") or ""),
                    adresse=str(a.get("browser_download_url") or a.get("adresse") or "")))
        erg.append(Freigabe(
            tag=str(tag), name=str(eintrag.get("name") or ""),
            vorab=bool(eintrag.get("prerelease") or eintrag.get("vorab")),
            entwurf=bool(eintrag.get("draft") or eintrag.get("entwurf")),
            datum=str(eintrag.get("published_at") or eintrag.get("datum") or "")[:10],
            seite=str(eintrag.get("html_url") or eintrag.get("seite") or ""),
            anhaenge=tuple(anhaenge)))
    return erg


def freigaben_als_daten(freigaben: list[Freigabe]) -> list[dict]:
    """Die gekuerzte Form fuer den Zwischenspeicher (nur, was gebraucht wird)."""
    return [{"tag": f.tag, "name": f.name, "vorab": f.vorab, "entwurf": f.entwurf, "datum": f.datum, "seite": f.seite,
             "anhaenge": [{"name": a.name, "groesse": a.groesse, "digest": a.digest, "adresse": a.adresse}
                          for a in f.anhaenge]} for f in freigaben]


def freigaben_als_roh(freigaben: list[Freigabe]) -> list[dict]:
    """Die Form der Releases-Schnittstelle - fuer ``ampr_updates.angebote_lesen``."""
    return [{"tag_name": f.tag, "name": f.name, "prerelease": f.vorab, "draft": f.entwurf, "published_at": f.datum,
             "html_url": f.seite,
             "assets": [{"name": a.name, "size": a.groesse, "digest": a.digest, "browser_download_url": a.adresse}
                        for a in f.anhaenge]} for f in freigaben]


def quelle_zerlegen(quelle: str) -> tuple[str, str]:
    """``("github", "owner/repo")`` bzw. ``("codeberg", "owner/repo")``; ``("", "")`` ohne Quelle."""
    quelle = str(quelle or "").strip()
    if not quelle:
        return "", ""
    if quelle.startswith("codeberg:"):
        return "codeberg", quelle[len("codeberg:"):]
    return "github", quelle


def seite_der_quelle(quelle: str) -> str:
    """Die Freigaben-Seite im Browser (``""`` ohne Quelle)."""
    art, repo = quelle_zerlegen(quelle)
    return _SEITEN[art] % repo if art else ""


def adresse_der_quelle(quelle: str) -> str:
    """Die Adresse der Schnittstelle (``""`` ohne Quelle)."""
    art, repo = quelle_zerlegen(quelle)
    return _ADRESSEN[art] % repo if art else ""


# ---------------------------------------------------------------------------
# Die Tabelle
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Datei:
    """Ein Anhang der Freigabe und der Name, unter dem er abgelegt wird (``{f}`` = die Fassung)."""
    anhang: str
    ziel: str
    orte: tuple[str, ...] = (ORT_PAYLOADS,)


@dataclass(frozen=True)
class Werkzeug:
    schluessel: str
    name: str
    gruppe: str
    quelle: str = ""
    #: Wo die mitgelieferte Fassung liegt: ``ordner`` (bei Dateien der Bestandsordner, bei Werkzeugordnern ein Glob
    #: unter der Programmwurzel) und ``muster`` (Glob der Dateien darin).
    ordner: str = ORT_PAYLOADS
    muster: str = ""
    ausschluss: str = ""
    dateien: tuple[Datei, ...] = ()
    #: Auch als Vorabfassung gekennzeichnete Freigaben gelten.
    vorab: bool = False
    #: Wie Fassungen gelesen und verglichen werden: ``zahl``, ``nur_zahl`` (Stufe im Dateinamen ist Namensbestandteil),
    #: ``tag`` (die ganze Marke), ``rc``, ``datum8``, ``datum``.
    modus: str = "zahl"
    art: str = ART_DATEI
    #: Schluessel eines Hinweistextes (``updates.hinweis_*``).
    hinweis: str = ""
    #: Wie die mitgelieferte Fassung gelesen wird, wenn nicht aus Dateinamen: ``fest:<Fassung>``, ``ordnername`` oder
    #: ``ordnername:<Glob>``, ``json:<Datei>:<Feld>``, ``text:<Datei>:<Regex>``.
    lokal: str = ""
    #: Vorlage ``praefix{f}suffix`` zum Lesen der Fassung im Modus ``tag`` (sonst die erste Datei der Tabelle).
    vorlage: str = ""
    #: Link, wenn die Quelle nicht die Freigaben-Seite ist.
    seite: str = ""
    #: Das Programm bleibt bei der mitgelieferten, geprueften Datei - in seinen festen Abläufen (Namen in
    #: ``payload_versand``/``_FTPSRV_PAYLOAD_NAME``/``_KLOG_PAYLOAD``), in der Dienstetabelle und bei "Ausgewaehltes
    #: starten". Eine geholte neuere Fassung liegt nur in der Schnellauswahl zum Senden bereit (:func:`ist_fest`).
    fest: bool = False


def _d(anhang: str, ziel: str = "", *orte: str) -> Datei:
    return Datei(anhang, ziel or anhang, tuple(orte) if orte else (ORT_PAYLOADS,))


def _p(schluessel: str, name: str, quelle: str, muster: str, *dateien: Datei, **opt: Any) -> Werkzeug:
    return Werkzeug(schluessel, name, opt.pop("gruppe", GRUPPE_PAYLOAD), quelle, muster=muster,
                    dateien=tuple(dateien), **opt)


def _hinweis(schluessel: str, name: str, quelle: str, muster: str, hinweis: str, **opt: Any) -> Werkzeug:
    return Werkzeug(schluessel, name, opt.pop("gruppe", GRUPPE_PAYLOAD), quelle, muster=muster, art=ART_HINWEIS,
                    hinweis=hinweis, **opt)


def _ohne(schluessel: str, name: str, muster: str, hinweis: str, **opt: Any) -> Werkzeug:
    return Werkzeug(schluessel, name, opt.pop("gruppe", GRUPPE_PAYLOAD), "", muster=muster, art=ART_KEINE,
                    hinweis=hinweis, **opt)


WERKZEUGE: tuple[Werkzeug, ...] = (
    # --- Payloads: je Eintrag eine Quelle, der Anhang ersetzt sich 1:1 -----------------------------------------
    _p("elfldr", "elfldr", "ps5-payload-dev/elfldr", "elfldr-ps5_v*.elf",
       _d("elfldr-ps5.elf", "elfldr-ps5_v{f}.elf"), hinweis="updates.hinweis_fest", fest=True),
    _p("ftpsrv", "ftpsrv", "ps5-payload-dev/ftpsrv", "ftpsrv-ps5_v*.elf",
       _d("ftpsrv-ps5.elf", "ftpsrv-ps5_v{f}.elf"), ausschluss="-ng", hinweis="updates.hinweis_fest", fest=True),
    _p("klogsrv", "klogsrv", "ps5-payload-dev/klogsrv", "klogsrv-ps5_v*.elf",
       _d("klogsrv-ps5.elf", "klogsrv-ps5_v{f}.elf"), hinweis="updates.hinweis_fest", fest=True),
    _p("websrv", "websrv", "ps5-payload-dev/websrv", "websrv-ps5_v*.elf", _d("websrv-ps5.elf", "websrv-ps5_v{f}.elf")),
    _p("shsrv", "shsrv", "ps5-payload-dev/shsrv", "shsrv-ps5_v*.elf", _d("shsrv-ps5.elf", "shsrv-ps5_v{f}.elf")),
    _p("gdbsrv", "gdbsrv", "ps5-payload-dev/gdbsrv", "gdbsrv-ps5_v*.elf", _d("gdbsrv-ps5.elf", "gdbsrv-ps5_v{f}.elf")),
    _hinweis("offact", "OffAct", "ps5-payload-dev/offact", "OffAct_v*.elf", "updates.hinweis_archiv"),
    _p("pkgmgr", "PKG Manager", "itsPLK/ps5-pkg-manager", "pkgmgr_v*.elf",
       _d("pkg-manager_v{f}.elf", "pkgmgr_v{f}.elf")),
    _p("pldmgr", "Payload Manager", "itsPLK/ps5-payload-manager", "pldmgr_v*.elf", _d("pldmgr_v{f}.elf")),
    _p("lapy", "Lapy JB Daemon", "itsPLK/PS5-Lapy-JB-Daemon", "lapy_jb_daemon-v*.elf",
       _d("lapy_jb_daemon-v{f}.elf")),
    _p("unified-autoloader", "Unified Autoloader", "itsPLK/ps5-unified-autoloader", "ps5-unified-autoloader-v*.elf",
       _d("ps5-unified-autoloader-v{f}.elf"), modus="tag"),
    _p("ps5upload", "PS5Upload", "phantomptr/ps5upload", "ps5upload-*.elf", _d("ps5upload-{f}.elf")),
    _p("app-dumper", "PS5 App Dumper", "EchoStretch/ps5-app-dumper", "ps5-app-dumper_v*.elf",
       _d("ps5-app-dumper_v{f}.elf")),
    _hinweis("dump-installer", "Dump Installer", "EchoStretch/dump_installer", "dump_installer_v*.elf",
             "updates.hinweis_archiv"),
    _p("kstuff-lite", "kstuff-lite (EchoStretch)", "EchoStretch/kstuff-lite", "kstuff_lite_v*_EchoStretch.elf",
       _d("kstuff.elf", "kstuff_lite_v{f}_Beta_EchoStretch.elf"), modus="nur_zahl"),
    _p("shadowmountplus", "ShadowMount+", "drakmor/ShadowMountPlus", "shadowmountplus_v*.elf",
       _d("shadowmountplus.elf", "shadowmountplus_v{f}.elf"), vorab=True, hinweis="updates.hinweis_vorab"),
    _p("nanodns", "nanoDNS", "drakmor/nanoDNS", "nanodns_v*.elf", _d("nanodns.elf", "nanodns_v{f}.elf")),
    _p("hwinfo", "ps5-hwinfo", "drakmor/ps5-hwinfo", "ps5-hwinfo-*_v*.elf",
       _d("hwinfo_sysinfo.elf", "ps5-hwinfo-sysinfo_v{f}.elf"), _d("hwinfo_bench.elf", "ps5-hwinfo-bench_v{f}.elf")),
    _p("zftpd", "zftpd", "seregonwar/zftpd", "zftpd-ps5-v*.elf",
       _d("zftpd-ps5-v{f}.elf"), _d("zftpd-ps5-zhttp-v{f}.elf")),
    _p("ps5debug", "ps5debug-NG", "Pharaoh2k/ps5debug-NG", "ps5debug-NG_v*.elf", _d("ps5debug-NG_v{f}.elf")),
    _p("prosperomgr", "Prospero Manager", "notmaj0r/ProsperoMgr", "ProsperoMgr_v*.elf",
       _d("ProsperoMgr.elf", "ProsperoMgr_v{f}.elf")),
    _p("cheatrunner", "CheatRunner", "notmaj0r/CheatRunner", "CheatRunner_v*.elf",
       _d("CheatRunner.elf", "CheatRunner_v{f}.elf")),
    _p("smplusgui", "SMPlusGui", "KarnerF/SMPlusGui", "SMPlusGui_v*.elf", _d("SMPlusGui_v{f}.elf")),
    _p("backpork", "BackPork", "BestPig/BackPork", "ps5-backpork_v*.elf",
       _d("ps5-backpork.elf", "ps5-backpork_v{f}.elf")),
    _p("aria2", "aria2 (PS5)", "owendswang/ps5-aria2", "aria2-v*.elf", _d("aria2-v{f}.elf")),
    _p("web-file-mgr", "Web File Manager", "owendswang/ps5-web-file-manager", "web-file-mgr-v*.elf",
       _d("web-file-mgr-v{f}.elf")),
    _p("syslang", "ps5-syslang (Deutsch)", "owendswang/ps5-syslang", "ps5-syslang-de-v*.elf",
       _d("ps5-syslang-de-v{f}.elf")),
    _p("self-pager", "ps5-self-pager", "idlesauce/ps5-self-pager", "ps5-self-pager-*_v*.elf",
       *[_d("ps5-self-pager-%s.elf" % teil, "ps5-self-pager-%s_v{f}.elf" % teil)
         for teil in ("full-system", "game", "shellcore", "system-common-lib")]),
    _p("game-compressor", "Game Compressor", "juma-sayeh/PS5-Game-Compressor", "game-compressor_v*.elf",
       _d("game-compressor.elf", "game-compressor_v{f}.elf")),
    _p("wk-autoloader", "WK AutoLoader", "X-F1REBALL-X/wk-autoloader", "WK-AutoLoader_v*.elf",
       _d("wk-dual-payload.elf", "WK-AutoLoader_v{f}.elf")),
    _p("anypad", "AnyPad PS5", "codeberg:elmonomalva0/Any-Pad-ps5", "AnyPad-PS5-*.elf", _d("AnyPad-PS5-{f}.elf"),
       vorab=True, hinweis="updates.hinweis_vorab"),
    _p("onionhen", "OnionHEN", "aydencharles/onionHEN", "OnionHEN_v*.elf", _d("OnionHEN.elf", "OnionHEN_v{f}.elf"),
       vorab=True, hinweis="updates.hinweis_vorab"),
    _p("np-fake-signin", "NP Fake Signin", "earthonion/np-fake-signin", "np-fake-signin-v*.elf",
       _d("np-fake-signin-ps5.elf", "np-fake-signin-v{f}.elf")),
    _p("garlic-savemgr", "garlic-savemgr", "earthonion/garlic-savemgr", "garlic-savemgr_v*.elf",
       _d("garlic-savemgr.elf", "garlic-savemgr_v{f}.elf")),
    _p("garlic-worker", "garlic-worker", "earthonion/garlic-worker", "garlic-worker-ps5_*.elf",
       _d("garlic-worker-ps5.elf", "garlic-worker-ps5_{f}.elf"), modus="datum", hinweis="updates.hinweis_datum"),
    _p("poords4", "PoorDS4", "ItsBlurf/PoorDS4", "PoorDS4_rc*.elf",
       _d("PoorDS4{f}.elf", "PoorDS4_{f}.elf"), _d("PoorDS4-status.elf", "PoorDS4-status_{f}.elf"),
       _d("PoorDS4-stop.elf", "PoorDS4-stop_{f}.elf"), modus="rc"),
    _p("memdbg", "MemDBG", "seregonwar/MemDBG", "MemDBG-ps5_nightly-*.elf",
       _d("MemDBG-ps5.elf", "MemDBG-ps5_nightly-{f}.elf"), modus="datum8", hinweis="updates.hinweis_datum"),
    # Agent und PIN-Anzeige kommen aus demselben Archiv ("actremotelink_agent_v2.0.elf", "..._pin_notify_v2.0.elf").
    _hinweis("actremotelink", "ActRemoteLink", "francoataffarel/ActRemoteLink", "actremotelink_*_v*.elf",
             "updates.hinweis_archiv"),
    _hinweis("unjail", "unjail-ps5app-payload", "SvenGDK/unjail-ps5app-payload", "unjail-ps5app-payload.elf",
             "updates.hinweis_ordner_fassung", lokal="ordnername:helloworld/unjail-ps5app-payload-*"),
    # Die Zahlen im Dateinamen (13.60-1.00) sind Firmware und Plugin-Fassung, keine Fassung der Freigabe.
    _hinweis("dpiv2", "DPI v2 (OnionHEN-Plugin)", "OnionBuddies/onionHEN-dpiv2-plugin", "dpiv2-*.elf",
             "updates.hinweis_ohne_freigabe", lokal="fest:"),
    _ohne("kstuff-drakmor", "kstuff-lite (drakmor, Testfassung)", "kstuff_v*-fpkg-dr-test*.elf",
          "updates.hinweis_testfassung", seite=_SEITEN["github"] % "drakmor/kstuff-lite"),
    _ohne("bdj-unpatch", "Y2JB-P2JB bdj_unpatch", "bdj_unpatch_*.elf", "updates.hinweis_paket",
          seite=_SEITEN["github"] % "owendswang/Y2JB-P2JB-bdj_unpatch"),
    _ohne("ftpsrv-ng", "ftpsrv (-ng-Fork)", "ftpsrv-ps5_v*-ng*.elf", "updates.hinweis_ohne_quelle"),
    _ohne("pizza-hen", "PIZZA-HEN", "PIZZA-HEN-v*.elf", "updates.hinweis_ohne_quelle"),
    _ohne("bfpilot", "BFpilot", "bfpilot_v*.elf", "updates.hinweis_ohne_quelle"),
    _ohne("yt-blocker", "YT-Blocker", "YT-Blocker_v*.elf", "updates.hinweis_paket",
          seite=_SEITEN["github"] % "MasterPS0/PS5HostPayloads"),
    _p("cooling", "PS5 Cooling & System Center - Pro", "strongt1me/ps5-cooling-system-center-pro",
       "PS5_Cooling_System_Center_v*.elf", _d("PS5_Cooling_System_Center_v{f}.elf"), hinweis="updates.hinweis_eigen"),
    # --- WebKit Autoloader: drei Dateien, der Installer zusaetzlich in helloworld/ ------------------------------
    Werkzeug("webkit", "WebKit Autoloader", GRUPPE_WEBKIT, "itsPLK/ps5-webkit-autoloader",
             ordner=ORT_WEBKIT, muster="webkit-autoloader-installer_v*.elf",
             dateien=(Datei("webkit-autoloader-host_v{f}.exe", "webkit-autoloader-host_v{f}.exe", (ORT_WEBKIT,)),
                      Datei("webkit-autoloader-host_v{f}.py", "webkit-autoloader-host_v{f}.py", (ORT_WEBKIT,)),
                      Datei("webkit-autoloader-installer_v{f}.elf", "webkit-autoloader-installer_v{f}.elf",
                            (ORT_WEBKIT, ORT_PAYLOADS))),
             hinweis="updates.hinweis_webkit"),
    # --- AMPR EMU: eigener Weg ueber ampr_updates ----------------------------------------------------------------
    Werkzeug("ampr-emu", "AMPR EMU", GRUPPE_EMU, "drakmor/ampr_emu", art=ART_EMU, hinweis="updates.hinweis_ampr"),
    # --- Engines und Werkzeuge: nur melden -----------------------------------------------------------------------
    Werkzeug("mkpfs", "MkPFS", GRUPPE_WERKZEUG, "PSBrew/MkPFS", ordner="MkPFS-*", art=ART_HINWEIS,
             hinweis="updates.hinweis_festgelegt", lokal="ordnername"),
    Werkzeug("ufs2tool", "UFS2Tool", GRUPPE_WERKZEUG, "SvenGDK/UFS2Tool", ordner="UFS2Tool-*", art=ART_HINWEIS,
             hinweis="updates.hinweis_angepasst", lokal="ordnername"),
    Werkzeug("prosperopkg", "LibProsperoPkg", GRUPPE_WERKZEUG, "SvenGDK/LibProsperoPkg", ordner="ProsperoPkg-*",
             art=ART_HINWEIS, hinweis="updates.hinweis_angepasst", lokal="json:fassung.json:fassung"),
    Werkzeug("orbispkgtool", "OrbisPkgTool", GRUPPE_WERKZEUG, "pearlxcore/OrbisPkgTool", ordner="OrbisPkgTool-*",
             art=ART_HINWEIS, hinweis="updates.hinweis_festgelegt", lokal="ordnername"),
    Werkzeug("ps5-pkg-tool", "PS5-PKG-Tool (ps5-fpkg-converter)", GRUPPE_WERKZEUG, "sub0x00001/ps5-fpkg-converter",
             ordner="PS5-PKG-Tool", art=ART_HINWEIS, hinweis="updates.hinweis_angepasst", lokal="fest:0.0.2"),
    Werkzeug("ps5-ultrapack", "ps5-ultrapack (Engine im PS5-PKG-Tool)", GRUPPE_WERKZEUG, "knutwurst/ps5-ultrapack",
             ordner="PS5-PKG-Tool", art=ART_HINWEIS, hinweis="updates.hinweis_angepasst", lokal="fest:2.2.1"),
    Werkzeug("wee-tools", "PS5 Wee Tools", GRUPPE_WERKZEUG, "andy-man/ps5-wee-tools", ordner="PS5-Wee-Tools-*",
             art=ART_HINWEIS, hinweis="updates.hinweis_festgelegt", lokal="ordnername"),
    Werkzeug("7zip", "7-Zip", GRUPPE_WERKZEUG, "ip7z/7zip", ordner="7-Zip-*", art=ART_HINWEIS,
             hinweis="updates.hinweis_buendel", lokal="ordnername"),
    Werkzeug("ampr-packtools", "AMPR PackTools", GRUPPE_WERKZEUG, "", ordner="AMPR_PackTools-*", art=ART_KEINE,
             hinweis="updates.hinweis_mit_ampr", lokal="ordnername"),
    Werkzeug("ps4ffpfsc", "PS4 FFPFSC", GRUPPE_WERKZEUG, "", ordner="PS4FFPFSC-*", art=ART_KEINE,
             hinweis="updates.hinweis_ohne_quelle", lokal="ordnername"),
    # PlayGo-Stub (drakmor/pgo_stub): Ordner heissen PlayGo_v0.6, nicht <Name>-<Fassung> - deshalb fest;
    # AbdeckungTests.test_playgo_stimmt_mit_dem_ordner haelt die Zahl gegen den hoechsten PlayGo_v*-Ordner.
    Werkzeug("playgo", "PlayGo-Stub (pgo_stub)", GRUPPE_WERKZEUG, "drakmor/pgo_stub", ordner="PlayGo & AMPR_EMU",
             art=ART_HINWEIS, hinweis="updates.hinweis_festgelegt", lokal="fest:0.6"),
    # --- Eigenbestand ---------------------------------------------------------------------------------------------
    Werkzeug("appinst", "PS5-AppInstall (appinst.elf)", GRUPPE_EIGEN, "", ordner="PS5-AppInstall", art=ART_KEINE,
             hinweis="updates.hinweis_selbst_gebaut"),
    Werkzeug("fakelibs", "Backport-Fakelibs", GRUPPE_EIGEN, "", ordner="Backport_Fakelibs", art=ART_KEINE,
             hinweis="updates.hinweis_eigenbestand"),
)

_NACH_SCHLUESSEL = {w.schluessel: w for w in WERKZEUGE}


def werkzeug(schluessel: str) -> "Werkzeug | None":
    return _NACH_SCHLUESSEL.get(schluessel)


def _passt(w: Werkzeug, name: str) -> bool:
    if not w.muster:
        return False
    return fnmatch.fnmatchcase(name.lower(), w.muster.lower()) and not (w.ausschluss and w.ausschluss in name)


def _gehoert_zu(w: Werkzeug, name: str, ort: str) -> bool:
    """Gehoert die Datei im Bestandsordner ``ort`` zu diesem Eintrag - als Hauptdatei oder als eine seiner Dateien?"""
    if w.ausschluss and w.ausschluss in name:
        return False
    if w.ordner == ort and _passt(w, name):
        return True
    return any(ort in d.orte and fnmatch.fnmatchcase(name.lower(), d.ziel.replace("{f}", "*").lower())
               for d in w.dateien)


def abgedeckte_dateien(dateinamen: Sequence[str], ort: str = ORT_PAYLOADS) -> dict[str, list[str]]:
    """Ordnet Dateinamen eines Bestandsordners den Eintraegen der Tabelle zu.

    Zu einem Eintrag gehoeren seine Hauptdatei (``muster``) und alle Dateien, die ``dateien`` ablegt - das
    Schluesselwort ``{f}`` steht dabei fuer beliebiges (``PoorDS4-status_rc51.elf``, die zweite zftpd-Datei, die
    WebKit-Host-Dateien); ``ausschluss`` nimmt Namen heraus.

    Returns:
        ``{schluessel: [Namen]}``; Namen ohne Eintrag stehen unter ``""``. Ein Name gehoert dem ersten Eintrag,
        der passt.
    """
    erg: dict[str, list[str]] = {}
    for name in dateinamen:
        gefunden = ""
        for w in WERKZEUGE:
            if _gehoert_zu(w, name, ort):
                gefunden = w.schluessel
                break
        erg.setdefault(gefunden, []).append(name)
    return erg


def _vorlage(w: Werkzeug) -> str:
    return w.vorlage or (w.dateien[0].ziel if w.dateien else "")


def ist_fest(muster: str) -> bool:
    """Gehoert dieses Dateimuster (z. B. aus dem Katalog der Konsolenseite) zu einem Werkzeug, bei dem das Programm
    bei der mitgelieferten Datei bleibt (:attr:`Werkzeug.fest`)?

    Geprueft wird, ob das Muster einen Dateinamen aus der Vorlage eines solchen Eintrags trifft (``{f}`` = ``0``)
    und keinen eines anderen Eintrags: ``elfldr*.elf`` trifft ``elfldr-ps5_v0.elf``, ``klogsrv*.elf`` trifft
    ``klogsrv-ps5_v0.elf``; ein Fangnetz wie ``*.elf`` trifft auch Anderes und gilt deshalb nicht als fest.
    """
    if not muster:
        return False
    muster = muster.lower()
    fest = andere = False
    for w in WERKZEUGE:
        for d in w.dateien:
            if fnmatch.fnmatchcase(d.ziel.replace("{f}", "0").lower(), muster):
                if w.fest:
                    fest = True
                else:
                    andere = True
    return fest and not andere


# ---------------------------------------------------------------------------
# Was lokal vorliegt
# ---------------------------------------------------------------------------
@dataclass
class Bestand:
    """Was an Dateien vorliegt - mitgeliefert und geholt."""
    #: Ort -> Dateinamen im mitgelieferten Ordner.
    mitgeliefert: dict[str, list[str]] = field(default_factory=dict)
    #: Ort -> Dateinamen im Update-Ordner.
    geholt: dict[str, list[str]] = field(default_factory=dict)
    #: Die Programmwurzel(n): Dort liegen die Werkzeugordner.
    wurzeln: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Lokal:
    fassung: str = ""
    geholt: bool = False
    dateien: tuple[str, ...] = ()


def update_ordner(basis: str) -> str:
    """``<basis>/Werkzeug-Updates`` (``basis`` ist der Einstellungsordner). Legt nichts an."""
    return os.path.join(str(basis), UNTERORDNER)


def _dateien_in(pfad: str) -> list[str]:
    try:
        return sorted(n for n in os.listdir(pfad)
                      if os.path.isfile(os.path.join(pfad, n)) and not n.lower().endswith(".teil"))
    except OSError:
        return []


def geholte_dateien(basis: str, ort: str) -> list[str]:
    """Die Dateinamen, die im Update-Ordner zu einem Ort liegen (leer, wenn es ihn nicht gibt)."""
    if not basis:
        return []
    return _dateien_in(os.path.join(update_ordner(basis), ort))


def bestand_lesen(ort_finden: Callable[[str], str], basis: str) -> Bestand:
    """Liest, was mitgeliefert und was geholt ist.

    Args:
        ort_finden: ``(name) -> Pfad`` des mitgelieferten Ordners (leer, wenn es ihn nicht gibt) - im Programm
            ``_mitgeliefert_finden``, das auch die macOS-Regel kennt.
        basis: Der Einstellungsordner.
    """
    bestand = Bestand()
    for ort in ORTE:
        pfad = ""
        try:
            pfad = ort_finden(ort) or ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("Ordner %s nicht gefunden: %s", ort, exc)
        if pfad and os.path.isdir(pfad):
            bestand.mitgeliefert[ort] = _dateien_in(pfad)
            wurzel = os.path.dirname(os.path.abspath(pfad))
            if wurzel not in bestand.wurzeln:
                bestand.wurzeln.append(wurzel)
        bestand.geholt[ort] = geholte_dateien(basis, ort)
    return bestand


def _unter(wurzel: str, muster: str) -> list[str]:
    """Alle Pfade unter ``wurzel``, die ``muster`` (Teile mit ``/`` getrennt, jeder ein Glob) trifft.

    Ohne ``glob``: Ein Programmordner mit ``[`` im Namen waere dort ein Zeichenvorrat.
    """
    pfade = [wurzel]
    for teil in str(muster).split("/"):
        weiter: list[str] = []
        for pfad in pfade:
            try:
                namen = sorted(os.listdir(pfad))
            except OSError:
                continue
            weiter.extend(os.path.join(pfad, n) for n in namen if fnmatch.fnmatchcase(n.lower(), teil.lower()))
        pfade = weiter
    return pfade


def _fassung_aus_ordner(w: Werkzeug, wurzeln: Sequence[str]) -> str:
    art, _, rest = w.lokal.partition(":")
    if art == "fest":
        return rest
    if art == "ordnername":
        beste = ""
        for wurzel in wurzeln:
            for pfad in _unter(wurzel, rest or w.ordner):
                fassung = fassung_aus_ordnername(pfad)
                if fassung and (not beste or fassungsschluessel(fassung) > fassungsschluessel(beste)):
                    beste = fassung
        return beste
    if art in ("json", "text"):
        datei, _, ausdruck = rest.partition(":")
        for wurzel in wurzeln:
            for ordner in _unter(wurzel, w.ordner):
                pfad = os.path.join(ordner, *datei.split("/"))
                try:
                    with open(pfad, "r", encoding="utf-8-sig", errors="replace") as handle:
                        text = handle.read()
                except OSError:
                    continue
                if art == "json":
                    try:
                        wert = json.loads(text).get(ausdruck, "")
                    except (ValueError, AttributeError):
                        continue
                    if wert:
                        return str(wert)
                else:
                    treffer = re.search(ausdruck, text)
                    if treffer:
                        return treffer.group(1)
    return ""


def lokale_fassung(w: Werkzeug, bestand: Bestand) -> Lokal:
    """Die hoechste Fassung, die von diesem Werkzeug vorliegt (mitgeliefert oder geholt)."""
    if w.lokal:
        return Lokal(fassung=_fassung_aus_ordner(w, bestand.wurzeln))
    if not w.muster:
        return Lokal()
    kandidaten: list[tuple[tuple, int, str, str]] = []
    passend: list[str] = []
    for rang, quelle in ((1, bestand.mitgeliefert), (0, bestand.geholt)):
        for name in quelle.get(w.ordner, ()):
            if not _passt(w, name):
                continue
            passend.append(name)
            fassung = fassung_aus_datei(name, w.modus, _vorlage(w))
            if fassung:
                kandidaten.append((_schluessel(fassung, w.modus), rang, fassung, name))
    if not kandidaten:
        return Lokal(dateien=tuple(passend))
    # Bei gleicher Fassung gewinnt die mitgelieferte (Rang 1): Dann gilt sie nicht als "geholt".
    beste = max(kandidaten, key=lambda k: (k[0], k[1]))
    return Lokal(fassung=beste[2], geholt=beste[1] == 0, dateien=tuple(passend))


# ---------------------------------------------------------------------------
# Das Urteil
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Teil:
    """Eine Datei, die geholt wird - einmal geladen, in jeden ihrer Orte gelegt."""
    anhang: str
    ziel: str
    orte: tuple[str, ...]
    adresse: str
    groesse: int = 0
    #: ``sha256:<hex>`` aus der Freigabe, oder leer.
    digest: str = ""
    #: Adresse einer danebenliegenden ``.sha256``-Datei (wenn die Freigabe keinen Digest fuehrt).
    pruefsumme_adresse: str = ""


@dataclass(frozen=True)
class Befund:
    werkzeug: Werkzeug
    status: str
    lokal: str = ""
    neu: str = ""
    datum: str = ""
    seite: str = ""
    teile: tuple[Teil, ...] = ()
    #: AMPR EMU: die holbaren ``ampr_updates.Angebot``e.
    ampr: tuple = ()
    #: Was bei der Abfrage schieflief (:data:`MELDUNG_NETZ` ...), oder leer.
    meldung: str = ""
    #: Zusatz zur Meldung (z. B. der Fehlertext).
    detail: str = ""
    #: Die neue Fassung ist als Vorabfassung gekennzeichnet.
    vorab: bool = False
    #: Der Stand ist aus dem Zwischenspeicher (Datum), weil die Abfrage nicht gelang.
    stand: str = ""
    #: Die lokale Fassung liegt im Update-Ordner.
    geholt: bool = False

    @property
    def ladbar(self) -> bool:
        return self.status == STATUS_NEU and bool(self.teile or self.ampr)

    @property
    def groesse(self) -> int:
        return sum(t.groesse for t in self.teile) + sum(int(getattr(a, "groesse", 0) or 0) for a in self.ampr)


def _kandidat(w: Werkzeug, freigaben: Sequence[Freigabe]):
    """Die Freigabe, gegen die verglichen wird: ``(Freigabe, Fassung, Teile)`` oder ``None``.

    Die oberste ohne Entwurf; ohne ``vorab`` zuerst eine fertige - gibt es nur Vorabfassungen (``latest`` bei
    garlic-worker), gilt die oberste. Eine Freigabe, deren Marke keine lesbare Fassung traegt oder der ein
    benoetigter Anhang fehlt, wird uebergangen.
    """
    sichtbar = [f for f in freigaben if not f.entwurf]
    fertig = [f for f in sichtbar if not f.vorab]
    reihenfolge = sichtbar if w.vorab else (fertig or sichtbar)
    for freigabe in reihenfolge:
        fassung = fassung_aus_tag(freigabe.tag, w.modus, freigabe.datum)
        if not fassung or not _SICHER.fullmatch(fassung):
            continue
        teile: tuple[Teil, ...] = ()
        if w.art == ART_DATEI:
            gebaut = _teile(w, freigabe, fassung)
            if gebaut is None:
                continue
            teile = gebaut
        return freigabe, fassung, teile
    return None


def _teile(w: Werkzeug, freigabe: Freigabe, fassung: str) -> "tuple[Teil, ...] | None":
    nach_name = {a.name: a for a in freigabe.anhaenge}
    teile: list[Teil] = []
    for datei in w.dateien:
        name = datei.anhang.replace("{f}", fassung)
        anhang = nach_name.get(name)
        if anhang is None or not anhang.adresse:
            return None
        pruefsumme = ""
        if not anhang.digest.lower().startswith("sha256:"):
            for endung in (".sha256", ".sha256sum"):
                danebenliegend = nach_name.get(name + endung)
                if danebenliegend is not None and danebenliegend.adresse:
                    pruefsumme = danebenliegend.adresse
                    break
        teile.append(Teil(anhang=name, ziel=datei.ziel.replace("{f}", fassung), orte=datei.orte,
                          adresse=anhang.adresse, groesse=anhang.groesse,
                          digest=anhang.digest if anhang.digest.lower().startswith("sha256:") else "",
                          pruefsumme_adresse=pruefsumme))
    return tuple(teile)


def beurteilen(w: Werkzeug, lokal: Lokal, freigaben: "Sequence[Freigabe] | None", fehler: str = "",
               stand: str = "") -> Befund:
    """Das Urteil ueber ein Werkzeug - rein, ohne Netz und ohne Dateizugriff.

    Args:
        lokal: Was vorliegt (:func:`lokale_fassung`).
        freigaben: Die Freigaben der Quelle, ``None`` wenn sie nicht zu bekommen waren.
        fehler: Der Grund dafuer (:data:`MELDUNG_NETZ` ...), ggf. mit Zusatz nach ``:``.
        stand: Das Datum des Zwischenspeichers, wenn die Freigaben nicht frisch sind.
    """
    meldung, _, detail = str(fehler or "").partition(":")
    basis: dict[str, Any] = dict(werkzeug=w, lokal=lokal.fassung, geholt=lokal.geholt,
                                 seite=w.seite or seite_der_quelle(w.quelle), stand=stand, meldung=meldung,
                                 detail=detail.strip())
    if w.art == ART_KEINE or not w.quelle:
        return Befund(status=STATUS_OHNE_QUELLE, **basis)
    if freigaben is None:
        return Befund(status=STATUS_FEHLER, **{**basis, "meldung": meldung or MELDUNG_NETZ})
    treffer = _kandidat(w, freigaben)
    if treffer is None:
        grund = MELDUNG_KEINE_FREIGABE if not [f for f in freigaben if not f.entwurf] else MELDUNG_KEINE_DATEI
        return Befund(status=STATUS_UNKLAR, **{**basis, "meldung": meldung or grund})
    freigabe, fassung, teile = treffer
    basis.update(neu=fassung, datum=freigabe.datum, seite=freigabe.seite or basis["seite"], vorab=freigabe.vorab)
    if not lokal.fassung:
        return Befund(status=STATUS_UNKLAR, **{**basis, "meldung": meldung or MELDUNG_LOKAL_UNLESBAR})
    urteil = vergleichen(lokal.fassung, fassung, w.modus)
    if urteil == "neu":
        status = STATUS_NEU if w.art == ART_DATEI else STATUS_NEU_HINWEIS
        return Befund(status=status, teile=teile, **basis)
    if urteil == "aktuell":
        return Befund(status=STATUS_AKTUELL, **basis)
    if urteil == "neuer":
        return Befund(status=STATUS_NEUER, **basis)
    return Befund(status=STATUS_UNKLAR, **{**basis, "meldung": meldung or MELDUNG_FASSUNG_UNKLAR})


def beurteilen_emu(w: Werkzeug, freigaben: "Sequence[Freigabe] | None", fehler: str = "", stand: str = "",
                   vorhanden: Sequence[tuple[str, str]] = (), ordner: str = "") -> Befund:
    """Das Urteil ueber AMPR EMU - mit den Regeln von ``ampr_updates`` (je Variante gerechnet).

    Args:
        vorhanden: Paare ``(Fassung, Variante)`` im Bestand, mitgeliefert oder geholt.
        ordner: Der Ordner "AMPR EMU updates" (``ampr_updates.schon_da`` schaut dort nach).
    """
    meldung, _, detail = str(fehler or "").partition(":")
    hoechste = ""
    for fassung, _variante in vorhanden:
        if ampr_updates.fassung_teile(fassung) > ampr_updates.fassung_teile(hoechste):
            hoechste = fassung
    basis: dict[str, Any] = dict(werkzeug=w, lokal=hoechste, seite=seite_der_quelle(w.quelle), stand=stand,
                                 meldung=meldung, detail=detail.strip())
    if freigaben is None:
        return Befund(status=STATUS_FEHLER, **{**basis, "meldung": meldung or MELDUNG_NETZ})
    angebote = ampr_updates.angebote_lesen(json.dumps(freigaben_als_roh(list(freigaben))))
    if not angebote:
        return Befund(status=STATUS_UNKLAR, **{**basis, "meldung": meldung or MELDUNG_KEINE_DATEI})
    neu = tuple(a for a in ampr_updates.neuere(angebote, list(vorhanden))
                if not (ordner and ampr_updates.schon_da(ordner, a)))
    # Angezeigt wird immer die neueste Fassung der Freigaben; die ladbaren Dateien (je Variante gerechnet, auch
    # aeltere Fassungen, die dem Bestand in einer Variante fehlen) stehen in ``ampr``.
    if neu:
        return Befund(status=STATUS_NEU, neu=angebote[0].fassung, ampr=neu, **basis)
    return Befund(status=STATUS_AKTUELL, neu=angebote[0].fassung, **basis)


def zusammenfassung(befunde: Sequence[Befund]) -> dict[str, int]:
    """Wie viele Befunde je Status."""
    zaehler: dict[str, int] = {}
    for befund in befunde:
        zaehler[befund.status] = zaehler.get(befund.status, 0) + 1
    return zaehler


# ---------------------------------------------------------------------------
# Zwischenspeicher
# ---------------------------------------------------------------------------
def speicher_lesen(basis: str) -> dict:
    """Der Zwischenspeicher ``{quelle: {etag, stand, freigaben}}``; leer, wenn es ihn nicht gibt oder er kaputt ist."""
    pfad = os.path.join(update_ordner(basis), SPEICHER_DATEI)
    try:
        with open(pfad, "r", encoding="utf-8") as handle:
            daten = json.load(handle)
    except (OSError, ValueError):
        return {}
    quellen = daten.get("quellen") if isinstance(daten, dict) else None
    return {k: v for k, v in quellen.items() if isinstance(v, dict)} if isinstance(quellen, dict) else {}


def speicher_schreiben(basis: str, speicher: dict) -> bool:
    """Schreibt den Zwischenspeicher (erst daneben, dann umbenennen). ``False``, wenn es nicht ging."""
    ordner = update_ordner(basis)
    pfad = os.path.join(ordner, SPEICHER_DATEI)
    vorlaeufig = pfad + ".teil"
    try:
        os.makedirs(ordner, exist_ok=True)
        with open(vorlaeufig, "w", encoding="utf-8") as handle:
            json.dump({"fassung": 1, "quellen": speicher}, handle, ensure_ascii=False, indent=1)
        os.replace(vorlaeufig, pfad)
        return True
    except OSError as exc:
        logger.debug("Zwischenspeicher nicht geschrieben: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Das Netz - die einzige Stelle, die hier ins Netz geht
# ---------------------------------------------------------------------------
class Antwort(NamedTuple):
    status: int
    text: str = ""
    etag: str = ""
    #: Unix-Zeit, zu der die Anfragegrenze zurueckgesetzt wird (0 = unbekannt).
    zuruecksetzen: int = 0


class Abgebrochen(Exception):
    """Der Nutzer hat abgebrochen."""


class Netz:
    """Fragt Freigaben ab und laedt Dateien. Tests geben eine Nachbildung mit denselben drei Methoden."""

    AGENT = "PS5DumpImageConverter"

    def abfragen(self, quelle: str, etag: str = "") -> Antwort:
        """Die Freigaben einer Quelle. Mit ``etag`` fragt es bedingt nach (Antwort 304 = unveraendert)."""
        adresse = adresse_der_quelle(quelle)
        if not adresse:
            raise ValueError("Quelle ohne Adresse: %r" % quelle)
        kopf = {"User-Agent": self.AGENT,
                "Accept": "application/vnd.github+json" if quelle_zerlegen(quelle)[0] == "github"
                else "application/json"}
        if etag:
            kopf["If-None-Match"] = etag
        anfrage = urllib.request.Request(adresse, headers=kopf)
        try:
            with urllib.request.urlopen(anfrage, timeout=FRIST) as antwort:
                return Antwort(int(getattr(antwort, "status", 200) or 200), antwort.read().decode("utf-8", "replace"),
                               antwort.headers.get("ETag", "") or "")
        except urllib.error.HTTPError as fehler:
            try:
                if fehler.code == 304:
                    return Antwort(304, "", etag)
                # Die Anfragegrenze meldet GitHub als 403 mit leerem Kontingent (``X-RateLimit-Remaining: 0``, Ende
                # in ``X-RateLimit-Reset``) oder als 429/403 mit ``Retry-After`` (zweite Grenze) - beides ist hier
                # 429. Ein anderes 403 (gesperrtes Projekt, ...) bleibt 403.
                kopf = fehler.headers
                try:
                    zurueck = int(kopf.get("X-RateLimit-Reset", "0") or 0)
                except (TypeError, ValueError):
                    zurueck = 0
                try:
                    warten = int(kopf.get("Retry-After", "") or 0)
                except (TypeError, ValueError):
                    warten = 0
                if warten > 0 and not zurueck:
                    zurueck = int(time.time()) + warten
                grenze = (kopf.get("X-RateLimit-Remaining", "") or "") == "0" or warten > 0
                return Antwort(429 if (fehler.code in (403, 429) and grenze) else fehler.code, "", "", zurueck)
            finally:
                fehler.close()

    def laden(self, adresse: str, pfad: str, fortschritt: "Callable[[int, int], None] | None" = None,
              abbruch: "threading.Event | None" = None) -> tuple[int, str]:
        """Laedt eine Datei nach ``pfad`` und liefert ``(Groesse, SHA-256)``. Bricht ab, wenn ``abbruch`` gesetzt ist.

        Raises:
            Abgebrochen: ``abbruch`` wurde gesetzt.
            ValueError: Die Datei ist groesser als :data:`GRENZE_BYTES`.
        """
        anfrage = urllib.request.Request(adresse, headers={"User-Agent": self.AGENT,
                                                            "Accept": "application/octet-stream"})
        summe = hashlib.sha256()
        gelesen = 0
        with urllib.request.urlopen(anfrage, timeout=FRIST) as antwort, open(pfad, "wb") as ziel:
            try:
                gesamt = int(antwort.headers.get("Content-Length") or 0)
            except (TypeError, ValueError):
                gesamt = 0
            if gesamt > GRENZE_BYTES:
                raise ValueError("Datei zu gross: %d Bytes" % gesamt)
            while True:
                if abbruch is not None and abbruch.is_set():
                    raise Abgebrochen()
                block = antwort.read(1 << 17)
                if not block:
                    break
                gelesen += len(block)
                if gelesen > GRENZE_BYTES:
                    raise ValueError("Datei zu gross: ueber %d Bytes" % GRENZE_BYTES)
                ziel.write(block)
                summe.update(block)
                if fortschritt is not None:
                    fortschritt(gelesen, gesamt)
        return gelesen, summe.hexdigest()

    def bytes(self, adresse: str, grenze: int = 64 * 1024 * 1024) -> bytes:
        """Eine kleine Datei im Speicher (Pruefsummen, AMPR-Bibliotheken)."""
        anfrage = urllib.request.Request(adresse, headers={"User-Agent": self.AGENT,
                                                            "Accept": "application/octet-stream"})
        with urllib.request.urlopen(anfrage, timeout=FRIST) as antwort:
            daten = antwort.read(grenze + 1)
        if len(daten) > grenze:
            raise ValueError("Datei zu gross")
        return daten


def _kurz(fehler: BaseException) -> str:
    text = str(fehler).strip().replace("\n", " ")
    return "%s: %s" % (MELDUNG_NETZ, text[:160] or type(fehler).__name__)


def adresse_erlaubt(adresse: str) -> bool:
    """Nur Adressen bei GitHub und Codeberg (die Antwort einer Schnittstelle bestimmt nie den Zielort allein)."""
    return str(adresse or "").startswith(_ERLAUBTE_ADRESSEN)


def ziel_erlaubt(name: str) -> bool:
    """Ein Dateiname, der nur ein Name ist - kein Pfad, keine versteckte Datei, eine erlaubte Endung."""
    return bool(name) and name == os.path.basename(name) and "\\" not in name and not name.startswith(".") \
        and name.lower().endswith(_ERLAUBTE_ENDUNGEN)


# ---------------------------------------------------------------------------
# Pruefen
# ---------------------------------------------------------------------------
Melder = Callable[..., None]


def quellen(werkzeuge: Sequence[Werkzeug]) -> list[str]:
    """Die Quellen, die zu fragen sind - jede einmal, in Tabellenreihenfolge."""
    erg: list[str] = []
    for w in werkzeuge:
        if w.art != ART_KEINE and w.quelle and w.quelle not in erg:
            erg.append(w.quelle)
    return erg


def _aus_speicher(speicher: dict, quelle: str) -> tuple["list[Freigabe] | None", str]:
    eintrag = speicher.get(quelle)
    if isinstance(eintrag, dict) and isinstance(eintrag.get("freigaben"), list):
        return freigaben_lesen(eintrag["freigaben"]), str(eintrag.get("stand") or "")
    return None, ""


def pruefen(werkzeuge: Sequence[Werkzeug], bestand: Bestand, netz: Any, speicher: "dict | None" = None,
            melden: "Melder | None" = None, abbruch: "threading.Event | None" = None,
            ampr_vorhanden: "Callable[[], list[tuple[str, str]]] | None" = None, ampr_ordner: str = "",
            parallel: int = 6, heute: str = "") -> tuple[list[Befund], dict]:
    """Fragt jede Quelle einmal ab und urteilt ueber jedes Werkzeug.

    Args:
        netz: Ein :class:`Netz` (oder eine Nachbildung mit ``abfragen(quelle, etag)``).
        speicher: Der Zwischenspeicher (:func:`speicher_lesen`); er wird nicht veraendert.
        melden: Rueckruf ``melden("pruefe", name=quelle, fertig=n, gesamt=m)`` nach jeder Quelle - aus einem
            Arbeitsfaden, die Oberflaeche darf dort kein Widget anfassen.
        abbruch: Wird sie gesetzt, werden keine weiteren Quellen gefragt; fuer sie gilt der Zwischenspeicher.
        ampr_vorhanden: Rueckruf fuer die Paare ``(Fassung, Variante)`` im AMPR-Bestand.
        ampr_ordner: Der Ordner "AMPR EMU updates".
        heute: Nur fuer Tests - das Datum, das als Stand gespeichert wird.

    Returns:
        ``(Befunde in Tabellenreihenfolge, neuer Zwischenspeicher)``.
    """
    heute = heute or datetime.date.today().isoformat()
    zu_fragen = quellen(werkzeuge)
    # Nur, was heute gefragt wird: Eine Quelle, die aus der Tabelle verschwunden ist, bleibt nicht im Speicher liegen.
    neuer = {q: v for q, v in (speicher or {}).items() if q in zu_fragen}
    antworten: dict[str, tuple["list[Freigabe] | None", str, str]] = {}

    # Vorher gelesen: Die Faeden fassen den Zwischenspeicher nicht an, nur der Sammler unten schreibt hinein.
    etags = {q: str((neuer.get(q) or {}).get("etag") or "") for q in zu_fragen}

    def _fragen(quelle: str) -> tuple[str, "Antwort | None", str]:
        if abbruch is not None and abbruch.is_set():
            return quelle, None, MELDUNG_ABGEBROCHEN
        try:
            return quelle, netz.abfragen(quelle, etags[quelle]), ""
        except Exception as exc:  # noqa: BLE001
            return quelle, None, _kurz(exc)

    fertig = 0
    if zu_fragen:
        with ThreadPoolExecutor(max_workers=max(1, min(parallel, len(zu_fragen)))) as pool:
            laufend = [pool.submit(_fragen, q) for q in zu_fragen]
            for zukunft in as_completed(laufend):
                quelle, antwort, fehler = zukunft.result()
                freigaben: "list[Freigabe] | None" = None
                meldung = fehler
                if antwort is not None:
                    if antwort.status == 200:
                        if _ist_liste(antwort.text):
                            freigaben = freigaben_lesen(antwort.text)
                            neuer[quelle] = {"etag": antwort.etag, "stand": heute,
                                             "freigaben": freigaben_als_daten(freigaben)}
                        else:
                            meldung = MELDUNG_ANTWORT
                    elif antwort.status == 304:
                        freigaben, _stand = _aus_speicher(neuer, quelle)
                        if freigaben is None:
                            meldung = MELDUNG_ANTWORT
                        else:
                            neuer[quelle] = {**neuer[quelle], "stand": heute}
                    elif antwort.status == 429:
                        meldung = MELDUNG_LIMIT + (":%d" % antwort.zuruecksetzen if antwort.zuruecksetzen else "")
                    elif antwort.status == 404:
                        meldung = MELDUNG_NICHT_GEFUNDEN
                    else:
                        meldung = "%s:%d" % (MELDUNG_NETZ, antwort.status)
                stand = ""
                if freigaben is None:
                    freigaben, stand = _aus_speicher(neuer, quelle)
                antworten[quelle] = (freigaben, meldung, stand if meldung else "")
                fertig += 1
                if melden is not None:
                    melden("pruefe", name=quelle, fertig=fertig, gesamt=len(zu_fragen))

    amprs = list(ampr_vorhanden() if ampr_vorhanden is not None else [])
    befunde: list[Befund] = []
    for w in werkzeuge:
        freigaben, meldung, stand = antworten.get(w.quelle, (None, "", ""))
        befunde.append(_urteil(w, bestand, freigaben, meldung, stand, amprs, ampr_ordner))
    return befunde, neuer


def _urteil(w: Werkzeug, bestand: Bestand, freigaben: "Sequence[Freigabe] | None", fehler: str, stand: str,
            ampr_vorhanden: Sequence[tuple[str, str]], ampr_ordner: str) -> Befund:
    if w.art == ART_EMU:
        return beurteilen_emu(w, freigaben, fehler, stand, list(ampr_vorhanden), ampr_ordner)
    return beurteilen(w, lokale_fassung(w, bestand), freigaben, fehler, stand)


def neu_beurteilen(befund: Befund, bestand: Bestand, speicher: dict,
                   ampr_vorhanden: Sequence[tuple[str, str]] = (), ampr_ordner: str = "") -> Befund:
    """Urteilt noch einmal ueber ein Werkzeug - ohne Netz, aus dem Zwischenspeicher.

    Nach dem Holen: Der Bestand hat sich geaendert, die Freigaben nicht. Meldung und Stand des alten Befunds
    bleiben erhalten (eine Quelle, die vorhin nicht antwortete, ist es jetzt auch nicht).
    """
    freigaben, _stand = _aus_speicher(speicher, befund.werkzeug.quelle)
    fehler = befund.meldung + (":" + befund.detail if befund.detail else "")
    return _urteil(befund.werkzeug, bestand, freigaben, fehler, befund.stand, ampr_vorhanden, ampr_ordner)


# ---------------------------------------------------------------------------
# Holen
# ---------------------------------------------------------------------------
@dataclass
class Ergebnis:
    #: Pfade der abgelegten Dateien.
    abgelegt: list[str] = field(default_factory=list)
    #: ``Name: Grund`` je Werkzeug, das nicht geholt werden konnte.
    fehler: list[str] = field(default_factory=list)
    #: Dateien, deren Freigabe keine Pruefsumme fuehrt (nur die Groesse wurde geprueft).
    ohne_summe: list[str] = field(default_factory=list)
    #: Werkzeuge, die vollstaendig geholt wurden.
    fertig: list[str] = field(default_factory=list)
    abgebrochen: bool = False


def _soll_summe(teil: Teil, netz: Any) -> str:
    """Die erwartete SHA-256 (klein geschrieben) - aus der Freigabe oder der danebenliegenden Datei; sonst leer."""
    if teil.digest.lower().startswith("sha256:"):
        return teil.digest.split(":", 1)[1].strip().lower()
    if teil.pruefsumme_adresse:
        text = netz.bytes(teil.pruefsumme_adresse, 4096).decode("utf-8", "replace")
        treffer = re.search(r"\b([0-9a-fA-F]{64})\b", text)
        if treffer:
            return treffer.group(1).lower()
    return ""


def _ablegen(teil: Teil, vorlaeufig: str, basis: str) -> list[str]:
    pfade = []
    for ort in teil.orte:
        ordner = os.path.join(update_ordner(basis), ort)
        os.makedirs(ordner, exist_ok=True)
        ziel = os.path.join(ordner, teil.ziel)
        zwischen = ziel + ".teil"
        shutil.copyfile(vorlaeufig, zwischen)
        os.replace(zwischen, ziel)
        pfade.append(ziel)
    return pfade


def holen(befunde: Sequence[Befund], basis: str, netz: Any, melden: "Melder | None" = None,
          abbruch: "threading.Event | None" = None) -> Ergebnis:
    """Holt die Dateien der gewaehlten Befunde nach ``<basis>/Werkzeug-Updates/<Ort>/``.

    Je Werkzeug alles oder nichts: Erst werden alle Teile geladen und geprueft (Groesse, SHA-256), dann erst
    kommen sie an ihren Platz. Ein Fehler bei einem Werkzeug haelt die uebrigen nicht auf.

    Args:
        melden: ``melden("hole", name=Werkzeug, text=Datei, fertig=Bytes, gesamt=Bytes)``,
            ``melden("abgelegt", name=..., text=Pfad)``, ``melden("fehler", name=..., text=Grund)`` und
            ``melden("ohne_summe", name=..., text=Datei)``.
    """
    ergebnis = Ergebnis()
    ordner = update_ordner(basis)
    for befund in befunde:
        if not befund.ladbar or not befund.teile:
            continue
        if abbruch is not None and abbruch.is_set():
            ergebnis.abgebrochen = True
            break
        name = befund.werkzeug.name
        geladen: list[tuple[Teil, str]] = []
        ohne_summe: list[str] = []
        try:
            os.makedirs(ordner, exist_ok=True)
            for teil in befund.teile:
                if abbruch is not None and abbruch.is_set():
                    raise Abgebrochen()               # keine neue Verbindung mehr aufmachen
                if not adresse_erlaubt(teil.adresse):
                    raise ValueError("Adresse nicht erlaubt: %s" % teil.adresse[:80])
                if not ziel_erlaubt(teil.ziel) or any(o not in ORTE for o in teil.orte):
                    raise ValueError("Zielname nicht erlaubt: %s" % teil.ziel)
                vorlaeufig = os.path.join(ordner, ".%s.teil" % uuid.uuid4().hex)
                geladen.append((teil, vorlaeufig))
                groesse, summe = netz.laden(
                    teil.adresse, vorlaeufig,
                    (lambda f, g, t=teil: melden("hole", name=name, text=t.ziel, fertig=f, gesamt=g)) if melden else None,
                    abbruch)
                if teil.groesse and groesse != teil.groesse:
                    raise ValueError("%s: %d statt %d Bytes" % (teil.ziel, groesse, teil.groesse))
                soll = _soll_summe(teil, netz)
                if soll and soll != summe:
                    raise ValueError("%s: SHA-256 stimmt nicht" % teil.ziel)
                if not soll:
                    ohne_summe.append(teil.ziel)
            pfade: list[str] = []
            for teil, vorlaeufig in geladen:
                pfade.extend(_ablegen(teil, vorlaeufig, basis))
            ergebnis.abgelegt.extend(pfade)
            ergebnis.ohne_summe.extend(ohne_summe)
            ergebnis.fertig.append(name)
            if melden is not None:
                for pfad in pfade:
                    melden("abgelegt", name=name, text=pfad)
                for datei in ohne_summe:
                    melden("ohne_summe", name=name, text=datei)
        except Abgebrochen:
            ergebnis.abgebrochen = True
            break
        except Exception as exc:  # noqa: BLE001
            grund = str(exc).strip() or type(exc).__name__
            ergebnis.fehler.append("%s: %s" % (name, grund))
            if melden is not None:
                melden("fehler", name=name, text=grund)
        finally:
            for _teil, vorlaeufig in geladen:
                try:
                    os.remove(vorlaeufig)
                except OSError:
                    pass
    return ergebnis


def holen_emu(befund: Befund, ordner: str, netz: Any) -> tuple[list[str], list[str]]:
    """Legt die AMPR-Angebote eines Befunds ab (``ampr_updates.holen``): ``(abgelegt, Fehler)``."""
    for angebot in befund.ampr:
        if not adresse_erlaubt(angebot.adresse):
            return [], ["Adresse nicht erlaubt: %s" % angebot.adresse[:80]]
    return ampr_updates.holen(ordner, list(befund.ampr), lambda adresse: netz.bytes(adresse))


# ---------------------------------------------------------------------------
# Der Update-Ordner im Programm
# ---------------------------------------------------------------------------
def beste_datei(muster: str, ordner_liste: Sequence[str]) -> str:
    """Die Datei mit der hoechsten Fassung, die ``muster`` ueber mehrere Ordner trifft ("" ohne Treffer).

    Bei gleichem Namen gewinnt der Ordner weiter vorn (der mitgelieferte), bei gleicher Fassung und verschiedenem
    Namen der Name. Die Ordner muessen nicht existieren.
    """
    if not muster:
        return ""
    gesehen: dict[str, str] = {}
    for ordner in ordner_liste:
        if not ordner:
            continue
        for name in _dateien_in(ordner):
            if fnmatch.fnmatchcase(name.lower(), muster.lower()) and name.lower() not in gesehen:
                gesehen[name.lower()] = os.path.join(ordner, name)
    if not gesehen:
        return ""
    return gesehen[max(gesehen, key=lambda n: datei_schluessel(n))]
