# -*- coding: utf-8 -*-
"""Die PS4-Paketsammlung: einlesen, filtern, benennen, ordnen, ausfuehren.

Das ist der Teil von „PS4 PKG -> OTA“, der ohne Fenster und ohne das
Fremdwerkzeug auskommt: Er liest nur den Kopf eines Pakets (0x5A0 Byte), die
Eintragstabelle und die ``param.sfo`` - bei einem Paket von 100 GB sind das
wenige Kilobyte. ``pkg_reader.read_pkg`` taugt dafuer nicht, es liest die
ganze Datei in den Speicher.

Die Ideen der Verwaltung (zwoelf Namensmuster, Verschieben nach Titel, Typ
oder Region, Pruefen auf doppelte Pakete und Patches ohne Basis, die
Installationsreihenfolge) kennt auch das **PS4 PKG Tool** von pearlxcore
(GPL-3.0). Hier steht eigener Code nach demselben Muster - kein uebersetzter
Quelltext.

Das Modul bleibt sprachfrei: Typen, Echtheit und Verschiebearten heissen
hier ``base``, ``fake``, ``titel`` ...; die Oberflaeche uebersetzt sie.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
import struct
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Iterable

logger = logging.getLogger("PS5Converter.ps4pkg_bibliothek")

CNT_MAGIC = b"\x7fCNT"
KOPF_GROESSE = 0x5A0
EINTRAG_GROESSE = 0x20
FLAG_VERSCHLUESSELT = 0x80000000

EINTRAG_NAMEN = 0x0200
EINTRAG_PARAM_SFO = 0x1000
EINTRAG_ICON0 = 0x1200
EINTRAG_PIC0 = 0x1220
EINTRAG_PIC1 = 0x1240
EINTRAG_CHANGEINFO = 0x1260   # nur, wenn der Namenseintrag ihn so nennt

#: Die Arten eines Pakets (``typ``).
TYP_BASIS = "base"
TYP_UPDATE = "patch"
TYP_ZUSATZ = "addon"
TYP_APP = "app"
TYP_UNBEKANNT = "unbekannt"
TYPEN = (TYP_BASIS, TYP_UPDATE, TYP_ZUSATZ, TYP_APP, TYP_UNBEKANNT)

#: Wie echt ein Paket ist (``echtheit``).
ECHT_FAKE = "fake"
ECHT_OFFIZIELL = "official"
ECHT_OFFIZIELL_DP = "official_dp"

#: SFO-Kategorie -> Typ. ``gde``/``gdk`` heissen beim PS4 PKG Tool „App“.
KATEGORIE_TYP = {
    "gd": TYP_BASIS,
    "gp": TYP_UPDATE,
    "ac": TYP_ZUSATZ,
    "gde": TYP_APP,
    "gdk": TYP_APP,
}

REGIONEN = {
    "E": "EU", "U": "US", "I": "US", "J": "JP", "H": "HK", "A": "AS", "K": "KR",
}

_TITLE_ID = re.compile(r"^[A-Z]{4}\d{5}$")


@dataclass
class PkgEintrag:
    """Ein Paket der Sammlung - so wie es der Kopf und die param.sfo sagen."""
    pfad: str
    groesse: int = 0
    geaendert: float = 0.0
    lesbar: bool = False
    fehler: str = ""
    content_id: str = ""
    title_id: str = ""
    titel: str = ""
    kategorie: str = ""
    typ: str = TYP_UNBEKANNT
    app_ver: str = ""
    version: str = ""
    system_ver: str = ""
    region: str = ""
    echtheit: str = ECHT_FAKE
    paketgroesse: int = 0
    sfo: dict = field(default_factory=dict)

    @property
    def datei(self) -> str:
        return os.path.basename(self.pfad)

    @property
    def ordner(self) -> str:
        return os.path.dirname(self.pfad)


# ---------------------------------------------------------------------------
# param.sfo
# ---------------------------------------------------------------------------

def sfo_lesen(daten: bytes) -> dict:
    """Liest eine ``param.sfo`` in ein ``{Schluessel: Wert}``-Verzeichnis.

    Zeichenketten kommen als ``str`` (UTF-8, ohne NUL), Zahlen als ``int``.
    Eine beschaedigte Datei liefert, was sich lesen laesst - oder ein leeres
    Verzeichnis. Es wird nie geworfen.
    """
    erg: dict = {}
    if len(daten) < 0x14 or daten[:4] != b"\x00PSF":
        return erg
    try:
        schluessel_start, daten_start, anzahl = struct.unpack_from("<III", daten, 0x08)
        for i in range(min(anzahl, 512)):
            (schl_off, fmt, laenge, _max, daten_off) = struct.unpack_from(
                "<HHIII", daten, 0x14 + i * 16)
            ende = daten.find(b"\x00", schluessel_start + schl_off)
            if ende < 0:
                continue
            name = daten[schluessel_start + schl_off:ende].decode("ascii", "replace")
            roh = daten[daten_start + daten_off:daten_start + daten_off + laenge]
            if fmt == 0x0404:
                erg[name] = struct.unpack("<I", roh[:4].ljust(4, b"\x00"))[0]
            else:
                erg[name] = roh.split(b"\x00", 1)[0].decode("utf-8", "replace")
    except (struct.error, IndexError):
        logger.debug("param.sfo nicht vollstaendig lesbar", exc_info=True)
    return erg


def system_version_text(wert: int) -> str:
    """Die Mindest-Firmware aus ``SYSTEM_VER``: ``0x05050000`` -> ``5.05``.

    Die Fassung steht als BCD in den oberen zwei Byte; die unteren tragen
    Kennzeichen (``0x04008000`` heisst 4.00, nicht 4.00.80).
    """
    if not isinstance(wert, int) or wert <= 0:
        return ""
    haupt = (wert >> 24) & 0xFF
    neben = (wert >> 16) & 0xFF
    try:
        return "%d.%02d" % (int("%02X" % haupt), int("%02X" % neben))
    except ValueError:
        return "%X.%02X" % (haupt, neben)


def region_aus_content_id(content_id: str) -> str:
    """``UP9000-...`` -> ``US``; unbekannter Anfangsbuchstabe -> leer."""
    return REGIONEN.get(content_id[:1].upper(), "") if content_id else ""


def typ_aus_kategorie(kategorie: str) -> str:
    return KATEGORIE_TYP.get((kategorie or "").lower(), TYP_UNBEKANNT)


def echtheit_aus_kopf(flags: int, content_type: int, content_flags: int) -> str:
    """Fake, offiziell oder offiziell mit Download-Kennzeichen.

    Dieselbe Regel wie im PS4 PKG Tool (``DetectBuildState``): Das Paar aus
    Inhaltstyp und Inhaltsflags ``0x1E43`` kennzeichnet ein offizielles
    Download-Paket; ein offizielles Paket traegt in den Kopfflags ``0x8300``
    oder ``0x8100`` oben. Es ist eine **Faustregel** am Kopf, keine
    Signaturpruefung.
    """
    if (((content_type & 0xFF) << 8) | (content_flags >> 24)) == 0x1E43:
        return ECHT_OFFIZIELL_DP
    return ECHT_OFFIZIELL if (flags >> 16) in (0x8300, 0x8100) else ECHT_FAKE


# ---------------------------------------------------------------------------
# Ein Paket lesen
# ---------------------------------------------------------------------------

@dataclass
class _Eintragsrecord:
    kennung: int
    flags1: int
    flags2: int
    offset: int
    groesse: int
    name_offset: int = 0


#: Namen der Eintraege, die jedes PS4-Paket hat (Kennung -> Dateiname). Hat das
#: Paket die Namenstabelle (Eintrag 0x200), gelten deren Namen; diese Liste
#: deckt Pakete ab, deren Tabelle fehlt oder die einen Eintrag nicht nennt.
BEKANNTE_NAMEN = {
    0x0001: "digests", 0x0010: "entry_keys", 0x0020: "image_key", 0x0080: "general_digests",
    0x0100: "metas", 0x0200: "entry_names", 0x0400: "license.dat", 0x0401: "license.info",
    0x0409: "psreserved.dat", 0x1000: "param.sfo", 0x1001: "playgo-chunk.dat",
    0x1002: "playgo-chunk.sha", 0x1003: "playgo-manifest.xml", 0x1006: "pic1.png",
    0x1007: "pubtoolinfo.dat", 0x100B: "shareparam.json", 0x1200: "icon0.png", 0x1220: "pic0.png",
    0x1280: "icon0.dds", 0x12A0: "pic0.dds", 0x12C0: "pic1.dds",
}


def _eintraege_lesen(datei, anzahl: int, tabelle: int) -> list[_Eintragsrecord]:
    datei.seek(tabelle)
    roh = datei.read(anzahl * EINTRAG_GROESSE)
    if len(roh) < anzahl * EINTRAG_GROESSE:
        raise ValueError("Eintragstabelle abgeschnitten")
    erg = []
    for i in range(anzahl):
        kennung, name_off, flags1, flags2, off, groesse = struct.unpack_from(
            ">IIIIII", roh, i * EINTRAG_GROESSE)
        erg.append(_Eintragsrecord(kennung, flags1, flags2, off, groesse, name_off))
    return erg


def _namen_aufloesen(datei, eintraege: "list[_Eintragsrecord]") -> "dict[int, str]":
    """``{Kennung: Name}`` aus der Namenstabelle (Eintrag 0x200), soweit lesbar."""
    rec = next((e for e in eintraege if e.kennung == EINTRAG_NAMEN), None)
    if rec is None:
        return {}
    roh = _eintrag_bytes(datei, rec, grenze=1024 * 1024)
    if not roh:
        return {}
    namen: dict[int, str] = {}
    for e in eintraege:
        if e.name_offset <= 0 or e.name_offset >= len(roh):
            continue
        ende = roh.find(b"\x00", e.name_offset)
        text = roh[e.name_offset:ende if ende >= 0 else len(roh)].decode("ascii", "replace")
        if text:
            namen[e.kennung] = text
    return namen


def _kopf(datei) -> dict:
    kopf = datei.read(KOPF_GROESSE)
    if len(kopf) < KOPF_GROESSE or kopf[:4] != CNT_MAGIC:
        raise ValueError("kein PS4-Paket (Kennung fehlt)")

    def u32(off: int) -> int:
        return struct.unpack_from(">I", kopf, off)[0]

    def u64(off: int) -> int:
        return struct.unpack_from(">Q", kopf, off)[0]

    return {
        "flags": u32(0x04),
        "eintraege": u32(0x10),
        "tabelle": u32(0x18),
        "content_id": kopf[0x40:0x70].split(b"\x00", 1)[0].decode("ascii", "replace"),
        "content_type": u32(0x74),
        "content_flags": u32(0x78),
        "paketgroesse": u64(0x430),
    }


def _eintrag_bytes(datei, rec: _Eintragsrecord, grenze: int = 8 * 1024 * 1024) -> "bytes | None":
    """Die Bytes eines Eintrags - ``None`` bei verschluesselten oder zu grossen."""
    if rec.flags1 & FLAG_VERSCHLUESSELT or rec.groesse <= 0 or rec.groesse > grenze:
        return None
    datei.seek(rec.offset)
    daten = datei.read(rec.groesse)
    return daten if len(daten) == rec.groesse else None


def lese_paket(pfad: str) -> PkgEintrag:
    """Liest Kopf und ``param.sfo`` eines Pakets. Wirft nie.

    Bei einem Fehler bleibt ``lesbar`` falsch, und ``fehler`` nennt den Grund.
    """
    eintrag = PkgEintrag(pfad=os.path.normpath(pfad))
    try:
        status = os.stat(pfad)
        eintrag.groesse = status.st_size
        eintrag.geaendert = status.st_mtime
        with open(pfad, "rb") as datei:
            kopf = _kopf(datei)
            if not 0 < kopf["eintraege"] <= 4096:
                raise ValueError("unplausible Eintragszahl")
            eintraege = _eintraege_lesen(datei, kopf["eintraege"], kopf["tabelle"])
            sfo_rec = next((e for e in eintraege if e.kennung == EINTRAG_PARAM_SFO), None)
            sfo: dict = {}
            if sfo_rec is not None:
                roh = _eintrag_bytes(datei, sfo_rec)
                if roh:
                    sfo = sfo_lesen(roh)
        eintrag.content_id = kopf["content_id"]
        eintrag.paketgroesse = kopf["paketgroesse"]
        eintrag.echtheit = echtheit_aus_kopf(kopf["flags"], kopf["content_type"], kopf["content_flags"])
        eintrag.sfo = sfo
        eintrag.title_id = str(sfo.get("TITLE_ID", "")).strip()
        eintrag.titel = str(sfo.get("TITLE", "")).strip()
        eintrag.kategorie = str(sfo.get("CATEGORY", "")).strip()
        eintrag.typ = typ_aus_kategorie(eintrag.kategorie)
        eintrag.app_ver = str(sfo.get("APP_VER", "")).strip()
        eintrag.version = str(sfo.get("VERSION", "")).strip()
        eintrag.system_ver = system_version_text(sfo.get("SYSTEM_VER", 0))
        sfo_cid = str(sfo.get("CONTENT_ID", "")).strip()
        if sfo_cid:
            eintrag.content_id = sfo_cid
        eintrag.region = region_aus_content_id(eintrag.content_id)
        if not sfo:
            raise ValueError("param.sfo fehlt oder ist verschluesselt")
        if not _TITLE_ID.match(eintrag.title_id):
            raise ValueError("keine PS4-Title-ID (%s)" % (eintrag.title_id or "leer"))
        eintrag.lesbar = True
    except (OSError, ValueError, struct.error) as fehler:
        eintrag.fehler = str(fehler)
    return eintrag


def lese_bild(pfad: str, kennung: int = EINTRAG_ICON0) -> "bytes | None":
    """Die Bytes eines Bildeintrags (``icon0.png``, ``pic0.png``, ``pic1.png``) - oder ``None``."""
    try:
        with open(pfad, "rb") as datei:
            kopf = _kopf(datei)
            if not 0 < kopf["eintraege"] <= 4096:
                return None
            for rec in _eintraege_lesen(datei, kopf["eintraege"], kopf["tabelle"]):
                if rec.kennung == kennung:
                    return _eintrag_bytes(datei, rec, grenze=32 * 1024 * 1024)
    except (OSError, ValueError, struct.error):
        return None
    return None


def lese_eintragsliste(pfad: str) -> list[dict]:
    """Die rohe Eintragstabelle eines Pakets (fuer „Interna“): Kennung, Name, Flags, Lage, Groesse."""
    try:
        with open(pfad, "rb") as datei:
            kopf = _kopf(datei)
            if not 0 < kopf["eintraege"] <= 4096:
                return []
            eintraege = _eintraege_lesen(datei, kopf["eintraege"], kopf["tabelle"])
            namen = _namen_aufloesen(datei, eintraege)
            return [{"kennung": r.kennung,
                     "name": namen.get(r.kennung) or BEKANNTE_NAMEN.get(r.kennung, "0x%04X" % r.kennung),
                     "verschluesselt": bool(r.flags1 & FLAG_VERSCHLUESSELT),
                     "flags1": r.flags1, "flags2": r.flags2, "offset": r.offset, "groesse": r.groesse}
                    for r in eintraege]
    except (OSError, ValueError, struct.error):
        return []


# ---------------------------------------------------------------------------
# Die Sammlung einlesen
# ---------------------------------------------------------------------------

#: So oft (in Sekunden) meldet die Suche nach Paketen hoechstens ihren Stand.
SUCHE_TAKT = 0.15


def paket_dateien(quellen: Iterable[str], *, rekursiv: bool = True,
                  fortschritt: "Callable[[int, str], None] | None" = None,
                  abbruch: "Callable[[], bool] | None" = None) -> list[str]:
    """Alle ``.pkg``-Dateien in Ordnern und Dateien, ohne Doppelte, geordnet.

    Die Suche kann ueber einen ganzen Datentraeger laufen und dauert dann
    Minuten; deshalb meldet sie sich und laesst sich abbrechen.

    Args:
        fortschritt: ``(gefunden, ordner)`` - hoechstens alle :data:`SUCHE_TAKT` Sekunden.
        abbruch: ``True`` beendet die Suche; was bis dahin gefunden ist, bleibt.
    """
    gefunden: dict[str, str] = {}
    letzte_meldung = 0.0
    for quelle in quellen:
        if os.path.isfile(quelle):
            if quelle.lower().endswith(".pkg"):
                gefunden[os.path.normcase(os.path.abspath(quelle))] = os.path.abspath(quelle)
        elif os.path.isdir(quelle):
            for wurzel, ordner, dateien in os.walk(quelle):
                if abbruch is not None and abbruch():
                    return sorted(gefunden.values(), key=lambda p: p.lower())
                ordner.sort(key=str.lower)
                for name in dateien:
                    if name.lower().endswith(".pkg"):
                        voll = os.path.abspath(os.path.join(wurzel, name))
                        gefunden[os.path.normcase(voll)] = voll
                if fortschritt is not None:
                    jetzt = time.monotonic()
                    if jetzt - letzte_meldung >= SUCHE_TAKT:
                        letzte_meldung = jetzt
                        fortschritt(len(gefunden), wurzel)
                if not rekursiv:
                    break
    return sorted(gefunden.values(), key=lambda p: p.lower())


class Zwischenspeicher:
    """Merkt sich gelesene Pakete nach ``(Pfad, Groesse, Aenderungszeit)``.

    Eine Sammlung von hunderten Paketen soll beim zweiten Oeffnen sofort da
    sein. Ein geaendertes Paket (andere Groesse oder Zeit) wird neu gelesen.
    """

    FASSUNG = 1

    def __init__(self, pfad: str = "") -> None:
        self.pfad = pfad
        self._daten: dict[str, dict] = {}
        self._geaendert = False
        if pfad:
            try:
                with open(pfad, "r", encoding="utf-8") as datei:
                    inhalt = json.load(datei)
                if isinstance(inhalt, dict) and inhalt.get("fassung") == self.FASSUNG:
                    self._daten = dict(inhalt.get("pakete", {}))
            except (OSError, ValueError):
                self._daten = {}

    @staticmethod
    def _schluessel(pfad: str) -> str:
        return os.path.normcase(os.path.abspath(pfad))

    def holen(self, pfad: str, groesse: int, geaendert: float) -> "PkgEintrag | None":
        roh = self._daten.get(self._schluessel(pfad))
        if not roh or roh.get("groesse") != groesse or abs(roh.get("geaendert", 0) - geaendert) > 1e-3:
            return None
        try:
            return PkgEintrag(**roh["eintrag"])
        except TypeError:
            return None

    def merken(self, eintrag: PkgEintrag) -> None:
        self._daten[self._schluessel(eintrag.pfad)] = {
            "groesse": eintrag.groesse, "geaendert": eintrag.geaendert,
            "eintrag": asdict(eintrag)}
        self._geaendert = True

    def speichern(self) -> None:
        if not (self.pfad and self._geaendert):
            return
        try:
            os.makedirs(os.path.dirname(self.pfad), exist_ok=True)
            with open(self.pfad, "w", encoding="utf-8") as datei:
                json.dump({"fassung": self.FASSUNG, "pakete": self._daten}, datei)
            self._geaendert = False
        except OSError:
            logger.warning("Zwischenspeicher nicht schreibbar: %s", self.pfad)


def einlesen(quellen: Iterable[str], *, rekursiv: bool = True,
             fortschritt: "Callable[[int, int, str], None] | None" = None,
             abbruch: "Callable[[], bool] | None" = None,
             zwischenspeicher: "Zwischenspeicher | None" = None,
             suche_fortschritt: "Callable[[int, str], None] | None" = None) -> list[PkgEintrag]:
    """Liest alle Pakete aus Ordnern und Dateien ein.

    Args:
        fortschritt: ``(aktuell, gesamt, datei)`` je Paket.
        abbruch: ``True`` beendet die Suche und das Einlesen; bis dahin Gelesenes bleibt.
        suche_fortschritt: ``(gefunden, ordner)`` waehrend der Suche nach den Paketen
            (siehe :func:`paket_dateien`).
    """
    dateien = paket_dateien(quellen, rekursiv=rekursiv, fortschritt=suche_fortschritt, abbruch=abbruch)
    erg: list[PkgEintrag] = []
    for nummer, pfad in enumerate(dateien, 1):
        if abbruch is not None and abbruch():
            break
        eintrag = None
        if zwischenspeicher is not None:
            try:
                status = os.stat(pfad)
                eintrag = zwischenspeicher.holen(pfad, status.st_size, status.st_mtime)
            except OSError:
                eintrag = None
        if eintrag is None:
            eintrag = lese_paket(pfad)
            if zwischenspeicher is not None:
                zwischenspeicher.merken(eintrag)
        erg.append(eintrag)
        if fortschritt is not None:
            fortschritt(nummer, len(dateien), os.path.basename(pfad))
    if zwischenspeicher is not None:
        zwischenspeicher.speichern()
    return erg


# ---------------------------------------------------------------------------
# Filtern und Gruppieren
# ---------------------------------------------------------------------------

def fassung_zahlen(text: str) -> tuple:
    """``"01.09"`` -> ``(1, 9)`` - zum Ordnen; Unlesbares ordnet nach vorn."""
    teile = re.findall(r"\d+", text or "")
    return tuple(int(t) for t in teile) if teile else (-1,)


def filtern(eintraege: Iterable[PkgEintrag], *, suche: str = "", typ: str = "",
            region: str = "", echtheit: str = "", min_firmware: str = "") -> list[PkgEintrag]:
    """Die Pakete, auf die alle gesetzten Bedingungen passen.

    ``suche`` sucht ohne Beachtung der Gross-/Kleinschreibung in Dateiname,
    Titel, Title-ID und Content-ID. ``min_firmware`` ist eine **Obergrenze**
    fuer die verlangte Firmware: „zeige, was auf Firmware 5.05 laeuft“.
    """
    nadel = (suche or "").strip().lower()
    grenze = fassung_zahlen(min_firmware) if min_firmware else None
    erg = []
    for e in eintraege:
        if typ and e.typ != typ:
            continue
        if region and e.region != region:
            continue
        if echtheit and e.echtheit != echtheit:
            continue
        if grenze is not None and e.system_ver and fassung_zahlen(e.system_ver) > grenze:
            continue
        if nadel and not any(nadel in (feld or "").lower()
                             for feld in (e.datei, e.titel, e.title_id, e.content_id)):
            continue
        erg.append(e)
    return erg


GRUPPENARTEN = ("titel", "title_id", "kategorie", "system_ver", "typ")


def gruppieren(eintraege: Iterable[PkgEintrag], nach: str) -> list[tuple[str, list[PkgEintrag]]]:
    """Teilt die Pakete in Gruppen: nach Titel, Title-ID, Kategorie, Firmware oder Typ."""
    if nach not in GRUPPENARTEN:
        raise ValueError("unbekannte Gruppierung: %s" % nach)
    gruppen: dict[str, list[PkgEintrag]] = {}
    for e in eintraege:
        schluessel = getattr(e, nach) or "-"
        gruppen.setdefault(schluessel, []).append(e)
    return sorted(gruppen.items(), key=lambda kv: kv[0].lower())


# ---------------------------------------------------------------------------
# Namen
# ---------------------------------------------------------------------------

#: Die Platzhalter der Namensmuster.
PLATZHALTER = ("TITLE", "TITLE_ID", "APP_VERSION", "VERSION", "CATEGORY",
               "CONTENT_ID", "CONTENT_ID2", "REGION", "SYSTEM_VERSION")

#: Die zehn festen Muster (1-basiert); ein elftes ist das eigene.
VORLAGEN: tuple[tuple[int, str], ...] = (
    (1, "{TITLE}"),
    (2, "{TITLE} [{TITLE_ID}]"),
    (3, "{TITLE} [{TITLE_ID}] [{APP_VERSION}]"),
    (4, "{TITLE} [{CATEGORY}]"),
    (5, "{TITLE_ID}"),
    (6, "{TITLE_ID} [{TITLE}]"),
    (7, "[{TITLE_ID}] [{CATEGORY}] [{APP_VERSION}] {TITLE}"),
    (8, "{TITLE} [{CATEGORY}] [{VERSION}]"),
    (9, "{CONTENT_ID}"),
    (10, "{CONTENT_ID2}"),
)

_UNGUELTIG = '<>:"/\\|?*'
_ERSATZ = {c: e for c, e in zip(_UNGUELTIG, "＜＞：＂／＼｜？＊")}
_RESERVIERT = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


def dateiname_bereinigen(name: str, *, laenge: int = 180) -> str:
    """Macht aus einem Titel einen Dateinamen, der auf jedem System geht.

    Verbotene Zeichen werden durch ihre Vollbreiten-Schwestern ersetzt (so
    bleibt ``Spiel: Teil 2`` lesbar), Steuerzeichen durch ``_``; am Ende
    stehen weder Punkt noch Leerzeichen, und reservierte Windows-Namen
    bekommen einen Unterstrich vorweg.
    """
    erg = []
    for zeichen in name or "":
        if zeichen in _ERSATZ:
            erg.append(_ERSATZ[zeichen])
        elif ord(zeichen) < 32 or ord(zeichen) == 127:
            erg.append("_")
        else:
            erg.append(zeichen)
    text = "".join(erg).strip().rstrip(". ")
    if text.upper() in _RESERVIERT:
        text = "_" + text
    return text[:laenge].rstrip(". ") or "_"


def ohne_fuehrende_nullen(text: str) -> str:
    return re.sub(r"^0+(?=\d+\.)", "", text or "")


def content_id2(e: PkgEintrag) -> str:
    """Der Szenenname: ``<Content-ID>-A<App>-V<Fassung>`` (Zusatzinhalt: ``-A0000-V...``)."""
    version = (e.version or "").replace(".", "")
    if e.typ == TYP_ZUSATZ:
        return "%s-A0000-V%s" % (e.content_id, version)
    return "%s-A%s-V%s" % (e.content_id, (e.app_ver or "").replace(".", ""), version)


def namen_ersetzen(vorlage: str, e: PkgEintrag) -> str:
    """Setzt die Platzhalter eines Namensmusters fuer ein Paket ein."""
    werte = {
        "TITLE": dateiname_bereinigen(e.titel),
        "TITLE_ID": e.title_id,
        "APP_VERSION": ohne_fuehrende_nullen(e.app_ver),
        "VERSION": ohne_fuehrende_nullen(e.version),
        "CATEGORY": {TYP_BASIS: "Game", TYP_UPDATE: "Patch", TYP_ZUSATZ: "Addon",
                     TYP_APP: "App"}.get(e.typ, e.kategorie or "Unknown"),
        "CONTENT_ID": e.content_id,
        "CONTENT_ID2": content_id2(e),
        "REGION": e.region,
        "SYSTEM_VERSION": e.system_ver,
    }
    text = vorlage
    for name, wert in werte.items():
        text = text.replace("{%s}" % name, wert)
    return text


def vorlage_gueltig(vorlage: str) -> "tuple[bool, str]":
    """Ein eigenes Muster: nicht leer, nur bekannte Platzhalter, ein Name ergibt sich."""
    if not (vorlage or "").strip():
        return False, "leer"
    for treffer in re.findall(r"\{([^{}]*)\}", vorlage):
        if treffer not in PLATZHALTER:
            return False, treffer
    return True, ""


@dataclass
class Umbenennung:
    """Ein geplanter Schritt: Datei ``quelle`` bekommt den Namen/Ort ``ziel``."""
    quelle: str
    ziel: str
    hinweis: str = ""

    @property
    def aendert(self) -> bool:
        return os.path.normcase(self.quelle) != os.path.normcase(self.ziel)


def umbenennen_plan(eintraege: Iterable[PkgEintrag], vorlage: str) -> list[Umbenennung]:
    """Der Plan fuer ein Namensmuster. Nicht lesbare Pakete bleiben unberuehrt.

    Zwei Pakete, die denselben neuen Namen bekaemen, werden nummeriert
    (``... (2).pkg``) - nie ueberschrieben.
    """
    plan: list[Umbenennung] = []
    belegt: set[str] = set()
    for e in eintraege:
        if not e.lesbar:
            continue
        name = dateiname_bereinigen(namen_ersetzen(vorlage, e))
        ziel = os.path.join(e.ordner, name + ".pkg")
        ziel = _frei_machen(ziel, belegt, e.pfad)
        belegt.add(os.path.normcase(ziel))
        plan.append(Umbenennung(e.pfad, ziel))
    return plan


def _frei_machen(ziel: str, belegt: "set[str]", quelle: str) -> str:
    """Haengt ``(2)``, ``(3)`` ... an, bis der Name weder vergeben noch geplant ist."""
    wurzel, endung = os.path.splitext(ziel)
    kandidat, n = ziel, 1
    while True:
        schluessel = os.path.normcase(kandidat)
        gleiche_datei = schluessel == os.path.normcase(quelle)
        if gleiche_datei or (schluessel not in belegt and not os.path.exists(kandidat)):
            return kandidat
        n += 1
        kandidat = "%s (%d)%s" % (wurzel, n, endung)


def install_prioritaet_plan(eintraege: Iterable[PkgEintrag]) -> list[Umbenennung]:
    """Benennt je Title-ID so um, dass die Reihenfolge im Ordner die Installationsreihenfolge ist.

    Zuerst die Basis, dann die Updates nach ihrer Fassung. Muster:
    ``Titel [CUSA00001] 00 - Base.pkg`` und ``... 01 - Update v1.05.pkg``.
    Zusatzinhalte und Apps bleiben unberuehrt - sie haben keine feste
    Reihenfolge.
    """
    gruppen: dict[str, list[PkgEintrag]] = {}
    for e in eintraege:
        if e.lesbar and e.typ in (TYP_BASIS, TYP_UPDATE):
            gruppen.setdefault(e.title_id, []).append(e)
    plan: list[Umbenennung] = []
    belegt: set[str] = set()
    for title_id in sorted(gruppen):
        pakete = sorted(gruppen[title_id],
                        key=lambda p: (0 if p.typ == TYP_BASIS else 1, fassung_zahlen(p.app_ver)))
        for nummer, e in enumerate(pakete):
            marke = "Base" if e.typ == TYP_BASIS else "Update"
            name = "%s [%s] %02d - %s" % (dateiname_bereinigen(e.titel), title_id, nummer, marke)
            if e.typ == TYP_UPDATE and e.app_ver and fassung_zahlen(e.app_ver) != (0,):
                name += " v" + ohne_fuehrende_nullen(e.app_ver)
            ziel = _frei_machen(os.path.join(e.ordner, dateiname_bereinigen(name) + ".pkg"), belegt, e.pfad)
            belegt.add(os.path.normcase(ziel))
            plan.append(Umbenennung(e.pfad, ziel))
    return plan


VERSCHIEBE_ARTEN = ("titel", "title_id", "kategorie", "echtheit", "region", "einzelordner")


def verschieben_plan(eintraege: Iterable[PkgEintrag], art: str, basis: str,
                     einzelordner: str = "") -> list[Umbenennung]:
    """Der Plan, die Pakete in Unterordner von ``basis`` zu sortieren.

    Arten: nach Titel, Title-ID, Kategorie (Basis/Update/Zusatz), Echtheit
    (Fake/Offiziell), Region - oder alle in einen einzigen Ordner.
    """
    if art not in VERSCHIEBE_ARTEN:
        raise ValueError("unbekannte Verschiebeart: %s" % art)
    plan: list[Umbenennung] = []
    belegt: set[str] = set()
    for e in eintraege:
        if not e.lesbar:
            continue
        if art == "einzelordner":
            unter = dateiname_bereinigen(einzelordner or "PKG")
        elif art == "titel":
            unter = dateiname_bereinigen(e.titel)
        elif art == "title_id":
            unter = e.title_id
        elif art == "kategorie":
            unter = {TYP_BASIS: "Base", TYP_UPDATE: "Update", TYP_ZUSATZ: "Addon",
                     TYP_APP: "App"}.get(e.typ, "Other")
        elif art == "echtheit":
            unter = "Official" if e.echtheit != ECHT_FAKE else "Fake"
        else:
            unter = e.region or "Unknown"
        ziel = _frei_machen(os.path.join(basis, unter, e.datei), belegt, e.pfad)
        belegt.add(os.path.normcase(ziel))
        plan.append(Umbenennung(e.pfad, ziel))
    return plan


def plan_ausfuehren(plan: Iterable[Umbenennung], *,
                    fortschritt: "Callable[[int, int, str], None] | None" = None
                    ) -> list[tuple[Umbenennung, str]]:
    """Fuehrt einen Plan aus. Ueberschreibt **nie**; Ordner werden angelegt.

    Returns:
        Die Schritte, die nicht gelungen sind, mit dem Grund.
    """
    schritte = [s for s in plan if s.aendert]
    gescheitert: list[tuple[Umbenennung, str]] = []
    for nummer, schritt in enumerate(schritte, 1):
        try:
            if os.path.exists(schritt.ziel):
                raise FileExistsError("Ziel ist schon vergeben")
            os.makedirs(os.path.dirname(schritt.ziel), exist_ok=True)
            os.rename(schritt.quelle, schritt.ziel)
        except OSError as fehler:
            gescheitert.append((schritt, str(fehler)))
        if fortschritt is not None:
            fortschritt(nummer, len(schritte), os.path.basename(schritt.ziel))
    return gescheitert


# ---------------------------------------------------------------------------
# Pruefungen ueber die Sammlung
# ---------------------------------------------------------------------------

def duplikate(eintraege: Iterable[PkgEintrag]) -> list[list[PkgEintrag]]:
    """Pakete, die dasselbe sind: gleiche Content-ID, Art und Fassung.

    Zwei Dateien mit gleichem Titel aber verschiedener Fassung sind keine
    Duplikate - das sind Updates.
    """
    gruppen: dict[tuple, list[PkgEintrag]] = {}
    for e in eintraege:
        if e.lesbar:
            gruppen.setdefault((e.content_id, e.typ, e.app_ver, e.version), []).append(e)
    return [g for g in gruppen.values() if len(g) > 1]


def patches_ohne_basis(eintraege: Iterable[PkgEintrag]) -> list[PkgEintrag]:
    """Updates, zu deren Title-ID kein Basisspiel in der Sammlung liegt."""
    liste = [e for e in eintraege if e.lesbar]
    mit_basis = {e.title_id for e in liste if e.typ == TYP_BASIS}
    return [e for e in liste if e.typ == TYP_UPDATE and e.title_id not in mit_basis]


def neuestes_update(eintraege: Iterable[PkgEintrag], title_id: str) -> "PkgEintrag | None":
    """Das Update mit der hoechsten Fassung zu einer Title-ID."""
    kandidaten = [e for e in eintraege if e.lesbar and e.typ == TYP_UPDATE and e.title_id == title_id]
    return max(kandidaten, key=lambda e: fassung_zahlen(e.app_ver), default=None)


def passendes_basisspiel(eintraege: Iterable[PkgEintrag], update: PkgEintrag) -> "PkgEintrag | None":
    """Das Basisspiel zu einem Update (gleiche Title-ID)."""
    for e in eintraege:
        if e.lesbar and e.typ == TYP_BASIS and e.title_id == update.title_id:
            return e
    return None


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

SPALTEN_CSV = ("datei", "titel", "title_id", "typ", "app_ver", "version", "region",
               "system_ver", "echtheit", "content_id", "groesse", "ordner")


def als_csv(eintraege: Iterable[PkgEintrag], pfad: str) -> int:
    """Schreibt die Liste als CSV (UTF-8 mit BOM, Semikolon - Excel oeffnet sie direkt).

    Returns:
        Die Zahl der geschriebenen Zeilen.
    """
    zeilen = 0
    with open(pfad, "w", encoding="utf-8-sig", newline="") as datei:
        schreiber = csv.writer(datei, delimiter=";")
        schreiber.writerow(SPALTEN_CSV)
        for e in eintraege:
            schreiber.writerow([getattr(e, s) for s in SPALTEN_CSV])
            zeilen += 1
    return zeilen
