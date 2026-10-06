# -*- coding: utf-8 -*-
"""Offizielle Updates eines PS4-Titels: nachsehen, was es gibt, und laden.

Sony veroeffentlicht zu jedem Titel eine kleine XML-Datei (``<TitleID>-ver.xml``),
die die neueste Update-Fassung nennt und - wenn es eine gibt - auf ein
JSON-Verzeichnis (``manifest_url``) mit den einzelnen Teilen des Pakets
verweist. Die Adresse der XML ist durch einen HMAC-SHA256 ueber ``np_<TitleID>``
gesichert; der Schluessel ist der oeffentlich bekannte der ShellCore-Firmware.

Das Verfahren steht in OrbisPkgTool (``Psn/UpdateCheck.cs``, MIT-Lizenz) und
im PS4 PKG Tool; hier steht eine eigene Fassung davon.

**Zwei Teile, bewusst getrennt** (wie ``aktualisierungen``):

* **Das Urteil** - reine Funktionen auf Texten. Sie bauen die Adresse und
  lesen XML und JSON, ohne etwas zu holen.
* **Das Holen** - kommt als Rueckruf herein (``holen``). Tests reichen eine
  Nachbildung mit, das Programm :func:`standard_holen`.

Das Modul bleibt sprachfrei; Fehler tragen einen festen Schluessel in
``UpdateFehler.schluessel``.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("PS5Converter.ps4pkg_updates")

#: Der ShellCore-Schluessel fuer die Update-Adressen (oeffentlich bekannt).
HMAC_SCHLUESSEL = bytes([
    173, 98, 227, 127, 144, 94, 6, 188, 25, 89, 49, 66, 40, 28, 17, 44,
    236, 14, 126, 195, 233, 126, 253, 202, 239, 205, 186, 175, 166, 55, 141, 132,
])

SERVER = "http://gs-sec.ww.np.dl.playstation.net/plo/np"

#: Wie sich das Programm beim Server meldet.
BENUTZERAGENT = "PS5-Image-Converter-PS4-Updates"

_TITLE_ID = re.compile(r"^[A-Z]{4}\d{5}$")


class UpdateFehler(Exception):
    """Die Abfrage oder der Download ist gescheitert; ``schluessel`` nennt den Grund."""

    def __init__(self, schluessel: str, text: str = "") -> None:
        super().__init__(text or schluessel)
        self.schluessel = schluessel
        self.text = text


@dataclass
class UpdateTeil:
    """Ein Stueck des Update-Pakets (``pieces`` im JSON-Verzeichnis)."""
    url: str
    versatz: int
    groesse: int
    hash: str


@dataclass
class UpdateVerzeichnis:
    """Das JSON hinter ``manifest_url``: Gesamtgroesse und die Teile."""
    gesamtgroesse: int = 0
    digest: str = ""
    anzahl: int = 0
    teile: list[UpdateTeil] = field(default_factory=list)


@dataclass
class UpdateInfo:
    """Was die Update-XML eines Titels sagt."""
    title_id: str = ""
    tag: str = ""
    pflicht: bool = False
    version: str = ""
    groesse: int = 0
    digest: str = ""
    verzeichnis_url: str = ""
    content_id: str = ""
    system_ver: str = ""
    typ: str = ""
    remaster: bool = False
    patchgo: bool = False
    verzeichnis: "UpdateVerzeichnis | None" = None


def title_id_gueltig(title_id: str) -> bool:
    """Vier Grossbuchstaben und fuenf Ziffern (``CUSA00001``)."""
    return bool(_TITLE_ID.match(title_id or ""))


def update_url(title_id: str) -> str:
    """Die Adresse der Update-XML eines Titels.

    ``http://gs-sec.ww.np.dl.playstation.net/plo/np/<id>/<hmac>/<id>-ver.xml``,
    ``hmac`` = kleingeschriebenes Hex von HMAC-SHA256(Schluessel, ``np_<id>``).

    Raises:
        ValueError: ``title_id`` hat nicht die Form ``CUSA00001``.
    """
    if not title_id_gueltig(title_id):
        raise ValueError("keine PS4-Title-ID: %r" % (title_id,))
    mac = hmac.new(HMAC_SCHLUESSEL, ("np_" + title_id).encode("ascii"), hashlib.sha256).hexdigest()
    return "%s/%s/%s/%s-ver.xml" % (SERVER, title_id, mac, title_id)


def _bool(text: str) -> bool:
    return (text or "").strip().lower() in ("true", "1", "yes")


def _zahl(text: str) -> int:
    try:
        return int((text or "0").strip())
    except ValueError:
        return 0


def xml_auswerten(text: "str | bytes") -> "UpdateInfo | None":
    """Liest ``<titlepatch><tag><package .../></tag></titlepatch>``.

    Returns:
        Die Angaben - oder ``None``, wenn das Dokument keine Update-Angabe
        enthaelt (der Server antwortet fuer Titel ohne Update mit leerem oder
        andersartigem Inhalt).
    """
    try:
        wurzel = ET.fromstring(text if isinstance(text, bytes) else text.encode("utf-8"))
    except (ET.ParseError, ValueError):
        return None
    patch = wurzel if wurzel.tag == "titlepatch" else wurzel.find(".//titlepatch")
    if patch is None:
        return None
    tag = patch.find(".//tag")
    paket = tag.find(".//package") if tag is not None else None
    if tag is None or paket is None:
        return None
    return UpdateInfo(
        title_id=patch.get("titleid", ""),
        tag=tag.get("name", ""),
        pflicht=_bool(tag.get("mandatory", "")),
        version=paket.get("version", ""),
        groesse=_zahl(paket.get("size", "")),
        digest=paket.get("digest", ""),
        verzeichnis_url=paket.get("manifest_url", ""),
        content_id=paket.get("content_id", ""),
        system_ver=paket.get("system_ver", ""),
        typ=paket.get("type", ""),
        remaster=_bool(paket.get("remaster", "")),
        patchgo=_bool(paket.get("patchgo", "")),
    )


def verzeichnis_auswerten(text: "str | bytes") -> "UpdateVerzeichnis | None":
    """Liest das JSON hinter ``manifest_url``; ``None`` bei unlesbarem Inhalt."""
    try:
        roh = json.loads(text if isinstance(text, str) else text.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not isinstance(roh, dict):
        return None
    teile = []
    for stueck in roh.get("pieces") or []:
        if not isinstance(stueck, dict) or not stueck.get("url"):
            continue
        teile.append(UpdateTeil(url=str(stueck["url"]), versatz=_zahl(str(stueck.get("fileOffset", 0))),
                                groesse=_zahl(str(stueck.get("fileSize", 0))),
                                hash=str(stueck.get("hashValue", "")).lower()))
    teile.sort(key=lambda t: t.versatz)
    return UpdateVerzeichnis(gesamtgroesse=_zahl(str(roh.get("originalFileSize", 0))),
                             digest=str(roh.get("packageDigest", "")),
                             anzahl=_zahl(str(roh.get("numberOfSplitFiles", len(teile)))), teile=teile)


def standard_holen(adresse: str, zeit: float = 20.0) -> bytes:
    """Holt eine kleine Adresse (die XML oder das JSON).

    Raises:
        UpdateFehler: ``netz`` (keine Verbindung), ``nicht_gefunden`` (404 - bei
            Sony: kein Update bekannt), ``http``.
    """
    anfrage = urllib.request.Request(adresse, headers={"User-Agent": BENUTZERAGENT})
    try:
        with urllib.request.urlopen(anfrage, timeout=zeit) as antwort:
            return antwort.read(8 * 1024 * 1024)
    except urllib.error.HTTPError as fehler:
        if fehler.code == 404:
            raise UpdateFehler("nicht_gefunden", adresse) from fehler
        raise UpdateFehler("http", "HTTP %d: %s" % (fehler.code, adresse)) from fehler
    except (urllib.error.URLError, OSError, TimeoutError) as fehler:
        raise UpdateFehler("netz", str(fehler)) from fehler


def nachsehen(title_id: str, holen: "Callable[[str], bytes | str]" = standard_holen) -> "UpdateInfo | None":
    """Fragt Sony nach der neuesten Update-Fassung eines Titels.

    Returns:
        Die Angaben samt Teileverzeichnis (wenn es sich holen liess) - oder
        ``None``, wenn es zu dem Titel kein Update gibt.

    Raises:
        UpdateFehler: ``netz`` und ``http``; ein 404 gilt als „kein Update“.
        ValueError: Ungueltige Title-ID.
    """
    try:
        text = holen(update_url(title_id))
    except UpdateFehler as fehler:
        if fehler.schluessel == "nicht_gefunden":
            return None
        raise
    info = xml_auswerten(text)
    if info is None:
        return None
    if not info.title_id:
        info.title_id = title_id
    if info.verzeichnis_url:
        try:
            info.verzeichnis = verzeichnis_auswerten(holen(info.verzeichnis_url))
        except UpdateFehler:
            # Das Verzeichnis ist Beiwerk: Die Fassung ist auch ohne bekannt.
            info.verzeichnis = None
    return info


def ist_neuer(online: str, lokal: str) -> bool:
    """Ist die Online-Fassung hoeher als die lokale? Verglichen Stelle fuer Stelle als Zahl."""
    def zahlen(text: str) -> tuple:
        teile = re.findall(r"\d+", text or "")
        return tuple(int(t) for t in teile) if teile else (0,)
    return zahlen(online) > zahlen(lokal)


def dateiname_vorschlag(info: UpdateInfo) -> str:
    """Ein Dateiname fuer das geladene Update: ``CUSA00001-patch-v01.05.pkg``."""
    sauber = re.sub(r"[^A-Za-z0-9._-]+", "_", info.version or "0")
    return "%s-patch-v%s.pkg" % (info.title_id or "TITLE", sauber)


def herunterladen(info: UpdateInfo, ziel_ordner: str, *,
                  fortschritt: "Callable[[int, int], None] | None" = None,
                  abbruch: "Callable[[], bool] | None" = None,
                  oeffnen: "Callable[[str], object] | None" = None,
                  zeit: float = 30.0) -> str:
    """Laedt die Teile des Updates und setzt sie zu einer ``.pkg`` zusammen.

    Jedes Teil wird mit seinem SHA-256 geprueft (``hashValue`` im
    Verzeichnis). Geschrieben wird in eine ``.teil``-Datei; erst eine
    vollstaendige und geprueft Datei bekommt ihren Namen. Ein Abbruch oder
    Fehler loescht die Teildatei **nicht** - sie bleibt zum Fortsetzen liegen
    (bereits fertige Teile werden dann uebersprungen).

    Args:
        fortschritt: ``(geladen, gesamt)`` in Bytes.
        oeffnen: Nur fuer Tests - ersetzt ``urllib.request.urlopen``.

    Returns:
        Der Pfad der fertigen Datei.

    Raises:
        UpdateFehler: ``ohne_teile`` (kein Verzeichnis), ``hash`` (ein Teil ist
            beschaedigt), ``netz``, ``http``, ``abgebrochen``, ``schreiben``.
    """
    verz = info.verzeichnis
    if verz is None or not verz.teile:
        raise UpdateFehler("ohne_teile", info.title_id)
    opener = oeffnen or (lambda adresse: urllib.request.urlopen(
        urllib.request.Request(adresse, headers={"User-Agent": BENUTZERAGENT}), timeout=zeit))
    os.makedirs(ziel_ordner, exist_ok=True)
    ziel = os.path.join(ziel_ordner, dateiname_vorschlag(info))
    teildatei = ziel + ".teil"
    markierung = teildatei + ".fertig"   # Zahl der fertig geschriebenen Teile
    gesamt = verz.gesamtgroesse or sum(t.groesse for t in verz.teile)
    fertig_teile = 0
    try:
        with open(markierung, "r", encoding="utf-8") as m:
            fertig_teile = max(0, int(m.read().strip() or 0))
    except (OSError, ValueError):
        fertig_teile = 0
    if fertig_teile and not os.path.isfile(teildatei):
        fertig_teile = 0
    geladen = sum(t.groesse for t in verz.teile[:fertig_teile])
    try:
        modus = "r+b" if fertig_teile and os.path.isfile(teildatei) else "wb"
        with open(teildatei, modus) as ausgabe:
            for nummer, teil in enumerate(verz.teile):
                if nummer < fertig_teile:
                    continue
                ausgabe.seek(teil.versatz)
                pruefsumme = hashlib.sha256()
                geschrieben = 0
                try:
                    with opener(teil.url) as antwort:
                        while True:
                            if abbruch is not None and abbruch():
                                raise UpdateFehler("abgebrochen")
                            block = antwort.read(1024 * 1024)
                            if not block:
                                break
                            ausgabe.write(block)
                            pruefsumme.update(block)
                            geschrieben += len(block)
                            if fortschritt is not None:
                                fortschritt(geladen + geschrieben, gesamt)
                except urllib.error.HTTPError as fehler:
                    raise UpdateFehler("http", "HTTP %d: %s" % (fehler.code, teil.url)) from fehler
                except (urllib.error.URLError, OSError, TimeoutError) as fehler:
                    raise UpdateFehler("netz", str(fehler)) from fehler
                if teil.hash and pruefsumme.hexdigest() != teil.hash:
                    raise UpdateFehler("hash", "Teil %d: %s" % (nummer + 1, teil.url))
                if teil.groesse and geschrieben != teil.groesse:
                    raise UpdateFehler("hash", "Teil %d hat %d statt %d Bytes" % (nummer + 1, geschrieben, teil.groesse))
                geladen += geschrieben
                ausgabe.flush()
                with open(markierung, "w", encoding="utf-8") as m:
                    m.write(str(nummer + 1))
    except UpdateFehler:
        raise
    except OSError as fehler:
        raise UpdateFehler("schreiben", str(fehler)) from fehler
    os.replace(teildatei, ziel)
    try:
        os.remove(markierung)
    except OSError:
        pass
    return ziel
