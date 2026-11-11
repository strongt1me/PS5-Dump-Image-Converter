# -*- coding: utf-8 -*-
"""Offizielle PS5-Updates von Sonys Auslieferungsnetz - finden, pruefen, laden.

**Warum das jetzt geht.** Bis v1.9.80 stand fuer PS5-Titel nur die Drittseite
prosperopatches.com zur Verfuegung; Sonys eigene Liste war nicht erreichbar,
weil ihre Adresse eine Kennung je Titel enthaelt (``.../<TitleID>_00/<UUID>-
version.xml``), die sich nicht errechnen laesst (Sony-Server: 404 fuer geratene
Adressen). Die Adresse steht aber in der ``sce_sys/param.json`` des Spiels
selbst (``versionFileUri``) - und in der ``app.db`` der Konsole
(``VERSION_FILE_URI``). Das Verfahren stammt aus PatchDL (knutwurst/ps5-patchdl,
GPL-3.0-or-later), das auf der Konsole denselben Weg geht.

Ablauf:

1. ``version.xml`` holen (:func:`verxml_holen`), ``<package>``-Eintraege lesen
   (:func:`fassungen_lesen`): Inhaltsfassung, noetige Firmware, ``manifest_url``.
2. Das Manifest (JSON) holen (:func:`manifest_holen`): die Teile des Pakets mit
   Adresse, Versatz, Groesse und SHA-256.
3. Die Teile laden und zusammensetzen (:func:`paket_laden`): fortsetzbar, jedes
   Teil gegen seine Pruefsumme geprueft.

Sonys Netz spricht TLS mit einer privaten Wurzel (``SCEI DNAS Root 05``), die in
keinem oeffentlichen Zertifikatsbuendel steht; sie ist unten eingebettet und
**nur** fuer die erlaubten Hosts gueltig. Die Pruefung wird nie abgeschaltet.

Reine Logik ohne Oberflaeche - die Fenster rufen sie im Faden.
"""
from __future__ import annotations

import errno
import hashlib
import hmac
import http.client
import json
import logging
import os
import re
import shutil
import ssl
import threading
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

from ps5_validator.utils import netz_abbruch

logger = logging.getLogger("PS5Converter.utils.ps5_updates")

#: Die einzigen Hosts (und deren Unterhosts), mit denen gesprochen wird.
ERLAUBTE_HOSTS: tuple[str, ...] = (
    "sgst.prod.dl.playstation.net",
    "gst.prod.dl.playstation.net",
    "gs2.ww.prod.dl.playstation.net",
    "gs-sec.ww.np.dl.playstation.net",
)

# HMAC-Schluessel fuer PS4-Update-URL-Ableitung.
# Oeffentlich bekannter PS4-Systemschluessel; Verfahren aus PatchDL
# (knutwurst/ps5-patchdl, GPL-3.0-or-later, src/patchdl_resolve.c).
_PS4_UPDATE_KEY = bytes([
    0xAD, 0x62, 0xE3, 0x7F, 0x90, 0x5E, 0x06, 0xBC, 0x19, 0x59, 0x31, 0x42,
    0x28, 0x1C, 0x11, 0x2C, 0xEC, 0x0E, 0x7E, 0xC3, 0xE9, 0x7E, 0xFD, 0xCA,
    0xEF, 0xCD, 0xBA, 0xAF, 0xA6, 0x37, 0x8D, 0x84,
])

#: SCEI DNAS Root 05 - die private Wurzel, die Sonys PS5-Auslieferungsnetz
#: signiert. Oeffentliches Zertifikat (gueltig 2004-2037), aus PatchDL
#: (``src/patchdl_ca.h``) uebernommen.
SONY_WURZEL_PEM = """-----BEGIN CERTIFICATE-----
MIID0jCCArqgAwIBAgIBADANBgkqhkiG9w0BAQUFADBUMQswCQYDVQQGEwJKUDEp
MCcGA1UEChMgU29ueSBDb21wdXRlciBFbnRlcnRhaW5tZW50IEluYy4xGjAYBgNV
BAMTEVNDRUkgRE5BUyBSb290IDA1MB4XDTA0MDcxMjA5MDExOVoXDTM3MTIwNjA5
MDExOVowVDELMAkGA1UEBhMCSlAxKTAnBgNVBAoTIFNvbnkgQ29tcHV0ZXIgRW50
ZXJ0YWlubWVudCBJbmMuMRowGAYDVQQDExFTQ0VJIEROQVMgUm9vdCAwNTCCASIw
DQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANmPeza8PwCqlI7esOGIkoSESnIN
g72ZD3Ut63jy7SdothPIvGBqVZWYkIpqJYJd1I4Nh//IpXQCQL0PnJLrh9BBeowq
Muf5NNq3Us80Ihiu9CvNEAEO18g3OFV1TYdSwQ5zUsk33OUeI7h4aBPDVcZXYeHt
dbPLqe4K8igian5prrAD5S6h28t8aAm+qMWRo+bW25B/841XwDGBP7/IxZv8Yoio
rCo80CVYe6lGoU08eeqQiaHI5zAF281DWZSoVfLjJUEWmEnxqr8aOhszRGePi+Ei
7UQjHDuZX9rLhDI1zAND+BA259tn/iwOqVXe20OccJllHJcG4Ecmd98f5qMCAwEA
AaOBrjCBqzAdBgNVHQ4EFgQUxlahM1tPzoN3YgVEhm0gV7Wv2twwfAYDVR0jBHUw
c4AUxlahM1tPzoN3YgVEhm0gV7Wv2tyhWKRWMFQxCzAJBgNVBAYTAkpQMSkwJwYD
VQQKEyBTb255IENvbXB1dGVyIEVudGVydGFpbm1lbnQgSW5jLjEaMBgGA1UEAxMR
U0NFSSBETkFTIFJvb3QgMDWCAQAwDAYDVR0TBAUwAwEB/zANBgkqhkiG9w0BAQUF
AAOCAQEACZPihjwXA27wJ03tEKcHAeFLi8aBw2ysH4GwuH1dWb3UpuznWOB0iQT1
wQocnEFYCJx5XFEnj4aLWpSHLEq/sSO+my+aPoTEsy20ajF+YLYZm0bZxH50CJYh
rkET4C2aC0XvhGp9k1JQ1o0W6+cFT5LTlXapsq8Btt31t+XDPX7RqGV4WGekt3hM
T7xRc7JWXdAQijIrbYi8mtbM07KEGnPU6IT8C47+0mSurpwLOoWL1tPgo6ePpLNi
c4quUMgh9RXVjeTyXOMmyYdeUm2gt7qErvQONli+6Epmhm0A2khpIMHSpQjTE8gV
rZp42a6+zg1iYy2vFBOmiQ17GRUl0A==
-----END CERTIFICATE-----
"""

#: Obergrenzen wie bei PatchDL: Was darueber liegt, ist kein PS5-Update.
MAX_VERXML = 4 * 1024 * 1024
MAX_MANIFEST = 16 * 1024 * 1024
MAX_TEILE = 4096
MAX_TEIL_BYTES = 8 * 1024 ** 3
MAX_GESAMT_BYTES = 200 * 1024 ** 3

#: Wie viele Megabyte zwischen zwei Merkpunkten der Teildatei liegen.
_MERKPUNKT = 32 * 1024 * 1024
_BLOCK = 1024 * 1024
USER_AGENT = "PS5ImageConverterPro (PS5 update lookup)"


class UpdateFehler(RuntimeError):
    """Eine Update-Abfrage oder ein Ladevorgang ist gescheitert.

    Die Meldung ist ein Uebersetzungsschluessel (``ps5upd.…``) oder ein
    fertiger Satz aus dem Netz/System.
    """


@dataclass
class Fassung:
    """Ein ``<package>`` aus der ``version.xml``."""

    inhalt: str                 # content_ver, z. B. "01.009.371"
    system_ver: int = 0         # noetige Firmware, gepackt (0x13600007)
    firmware: str = ""          # "13.60"
    manifest_url: str = ""      # PS5: JSON-Manifest-Adresse
    delta_url: str = ""
    digest: str = ""
    pflicht: bool = False
    pkg_url: str = ""           # PS4: direkte .pkg-Adresse


@dataclass
class Teil:
    url: str
    versatz: int
    groesse: int
    sha256: str


@dataclass
class Manifest:
    gesamt: int
    teile: list[Teil] = field(default_factory=list)
    paket_digest: str = ""


# ---------------------------------------------------------------------------
# Netz
# ---------------------------------------------------------------------------
def ssl_kontext() -> ssl.SSLContext:
    """TLS-Kontext, der **nur** Sonys private Wurzel kennt.

    Python 3.13 prueft standardmaessig strenger (``VERIFY_X509_STRICT``); die
    Wurzel von 2004 markiert ihre Basiseinschraenkung nicht als kritisch und
    fiele dadurch durch. Nur dieses Flag wird gelockert - Kette und Hostname
    bleiben streng.
    """
    kontext = ssl.create_default_context(cadata=SONY_WURZEL_PEM)
    kontext.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
    # Sonys Kettenglieder sind teils mit SHA-1 signiert; OpenSSL 3 meldet das
    # bei Sicherheitsstufe 2 als "CA signature digest algorithm too weak"
    # (am 15.10.2026 an einzelnen Servern der Auslieferung gemessen, andere
    # Aufrufe derselben Adresse gingen durch). PatchDL laeuft auf der Konsole
    # mit der Stufe des SDK. Die Wurzel bleibt auf Sonys eine beschraenkt,
    # Kette und Hostname werden weiter geprueft; die Pakete selbst prueft
    # zusaetzlich die SHA-256 aus dem Manifest.
    try:
        kontext.set_ciphers("DEFAULT:@SECLEVEL=0")
    except ssl.SSLError as exc:
        logger.debug("Sicherheitsstufe nicht senkbar: %s", exc)
    return kontext


def url_erlaubt(url: str) -> bool:
    """Nur http(s) und nur Sonys Auslieferungshosts (samt Unterhosts)."""
    try:
        zerlegt = urlparse(str(url or "").strip())
    except ValueError:
        return False
    if zerlegt.scheme.lower() not in ("http", "https") or not zerlegt.hostname:
        return False
    host = zerlegt.hostname.lower()
    for erlaubt in ERLAUBTE_HOSTS:
        if host == erlaubt or host.endswith("." + erlaubt):
            return True
    return False


class _UmleitungPruefen(urllib.request.HTTPRedirectHandler):
    """Folgt Umleitungen nur zu erlaubten Hosts (Sonys Kante leitet auf http um)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        if not url_erlaubt(newurl):
            raise UpdateFehler("ps5upd.umleitung_fremd")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _oeffner() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl_kontext()), _UmleitungPruefen())


def _anfrage(url: str, bereich_ab: int = 0) -> urllib.request.Request:
    kopf = {"User-Agent": USER_AGENT}
    if bereich_ab > 0:
        kopf["Range"] = "bytes=%d-" % bereich_ab
    return urllib.request.Request(url, headers=kopf)


def _abbruch_fehler() -> UpdateFehler:
    return UpdateFehler("ps5upd.abgebrochen")


def holen(url: str, max_bytes: int, timeout: float = 20.0,
          abbruch: Callable[[], bool] | None = None) -> bytes:
    """Holt eine kleine Datei (version.xml, Manifest) - mit Obergrenze."""
    if not url_erlaubt(url):
        raise UpdateFehler("ps5upd.host_fremd")
    try:
        antwort = netz_abbruch.oeffnen(lambda: _oeffner().open(_anfrage(url), timeout=timeout), abbruch, _abbruch_fehler)
        with antwort, netz_abbruch.wache(antwort, abbruch):
            daten = bytearray()
            while True:
                block = netz_abbruch.stueck_lesen(antwort, abbruch, _abbruch_fehler)
                if not block:
                    break
                daten += block
                if len(daten) > max_bytes:
                    raise UpdateFehler("ps5upd.zu_gross")
            return bytes(daten)
    except UpdateFehler:
        raise
    except urllib.error.HTTPError as exc:
        raise UpdateFehler("ps5upd.http|%d" % exc.code) from exc
    except (urllib.error.URLError, OSError, ssl.SSLError, http.client.HTTPException) as exc:
        # HTTPException (BadStatusLine, IncompleteRead ...) ist kein OSError: urllib reicht es roh durch.
        raise UpdateFehler("ps5upd.netz|%s" % exc) from exc


# ---------------------------------------------------------------------------
# version.xml
# ---------------------------------------------------------------------------
def firmware_text(system_ver: int) -> str:
    """``0x13600007`` -> ``"13.60"`` (die Stellen sind Hexziffern, als Dezimal gelesen)."""
    return "%x.%02x" % ((system_ver >> 24) & 0xFF, (system_ver >> 16) & 0xFF)


def _zahl(text: str) -> int:
    text = str(text or "").strip()
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text)
    except ValueError:
        return 0


def _fassung_schluessel(text: str) -> tuple[int, ...]:
    """``"01.009.371"`` -> ``(1, 9, 371)`` - Zahlen, nicht Text, vergleichen."""
    teile = []
    for stueck in str(text or "").split("."):
        try:
            teile.append(int(stueck))
        except ValueError:
            teile.append(0)
    return tuple(teile)


def verxml_url_gueltig(url: str) -> bool:
    """Ist das eine Adresse, mit der dieses Modul sprechen wuerde?"""
    return url_erlaubt(url) and str(url).strip().lower().endswith(".xml")


def ps4_verxml_url(title_id: str) -> str:
    """Leitet die ver.xml-Adresse eines PS4-Titels ab (HMAC-SHA256).

    ``title_id``: 9-Zeichen-Kuerzel wie ``CUSA12345``.
    Verfahren aus PatchDL (knutwurst/ps5-patchdl, GPL-3.0-or-later,
    ``src/patchdl_resolve.c``).
    """
    if len(title_id) != 9:
        raise UpdateFehler("ps5upd.title_id_ungueltig")
    msg = ("np_" + title_id).encode("ascii")
    digest = hmac.new(_PS4_UPDATE_KEY, msg, hashlib.sha256).hexdigest()
    return (
        "https://gs-sec.ww.np.dl.playstation.net/plo/np/"
        f"{title_id}/{digest}/{title_id}-ver.xml"
    )


def fassungen_lesen(xml_text: str | bytes) -> list[Fassung]:
    """Liest die ``<package>``-Eintraege einer ``version.xml``.

    Eine ``DOCTYPE``/``ENTITY``-Angabe wird abgelehnt (Entity-Bomben): eine
    ``version.xml`` hat so etwas nie.
    """
    roh = xml_text if isinstance(xml_text, bytes) else str(xml_text).encode("utf-8")
    kopf = roh[:4096].lower()
    if b"<!doctype" in kopf or b"<!entity" in roh[:65536].lower():
        raise UpdateFehler("ps5upd.xml_unzulaessig")
    try:
        wurzel = ET.fromstring(roh)
    except ET.ParseError as exc:
        raise UpdateFehler("ps5upd.xml_kaputt") from exc
    fassungen: list[Fassung] = []
    for paket in wurzel.iter("package"):
        inhalt = paket.get("content_ver") or paket.get("version") or ""
        if not inhalt:
            continue
        system = _zahl(paket.get("system_ver", ""))
        pkg_url = (paket.get("url") or "").strip()
        fassungen.append(Fassung(
            inhalt=inhalt.strip(), system_ver=system,
            firmware=firmware_text(system) if system else "",
            manifest_url=(paket.get("manifest_url") or "").strip(),
            delta_url=(paket.get("delta_url") or "").strip(),
            digest=(paket.get("digest") or "").strip(),
            pflicht=str(paket.get("mandatory", "")).lower() == "true",
            pkg_url=pkg_url if url_erlaubt(pkg_url) else ""))
    fassungen.sort(key=lambda f: _fassung_schluessel(f.inhalt), reverse=True)
    return fassungen


def neueste(fassungen: list[Fassung], firmware: int | None = None) -> Fassung | None:
    """Die neueste Fassung - mit ``firmware`` (gepackt) nur eine, die darauf laeuft."""
    for fassung in fassungen:        # absteigend sortiert
        if firmware is None or fassung.system_ver <= firmware:
            return fassung
    return None


def verxml_holen(url: str, abbruch: Callable[[], bool] | None = None) -> list[Fassung]:
    """``version.xml`` holen und lesen."""
    return fassungen_lesen(holen(url, MAX_VERXML, abbruch=abbruch))


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------
def _hex64(wert: Any) -> str:
    text = str(wert or "").strip().lower()
    # PS5-Manifeste tragen SHA-256 (64 Hex), PS4-Manifeste SHA-1 (40 Hex).
    if len(text) not in (40, 64) or any(z not in "0123456789abcdef" for z in text):
        return ""
    return text


def manifest_lesen(roh: bytes | str) -> Manifest:
    """Liest und **prueft** ein Paket-Manifest.

    Verlangt wird: erlaubte Hosts, lueckenlose Teile ab Versatz 0, Summe gleich
    ``originalFileSize``, je Teil eine SHA-256 und die Obergrenzen von PatchDL.
    """
    try:
        daten = json.loads(roh)
    except (ValueError, TypeError) as exc:
        raise UpdateFehler("ps5upd.manifest_kaputt") from exc
    if not isinstance(daten, dict) or not isinstance(daten.get("pieces"), list):
        raise UpdateFehler("ps5upd.manifest_kaputt")
    stuecke = daten["pieces"]
    if not 0 < len(stuecke) <= MAX_TEILE:
        raise UpdateFehler("ps5upd.manifest_kaputt")
    try:
        gesamt = int(daten.get("originalFileSize"))
    except (TypeError, ValueError) as exc:
        raise UpdateFehler("ps5upd.manifest_kaputt") from exc
    if not 0 < gesamt <= MAX_GESAMT_BYTES:
        raise UpdateFehler("ps5upd.manifest_kaputt")
    teile: list[Teil] = []
    naechster = 0
    for stueck in stuecke:
        if not isinstance(stueck, dict):
            raise UpdateFehler("ps5upd.manifest_kaputt")
        try:
            versatz = int(stueck.get("fileOffset"))
            groesse = int(stueck.get("fileSize"))
        except (TypeError, ValueError) as exc:
            raise UpdateFehler("ps5upd.manifest_kaputt") from exc
        pruefsumme = _hex64(stueck.get("hashValue"))
        url = str(stueck.get("url") or "").strip()
        if (not url_erlaubt(url) or not pruefsumme or versatz != naechster
                or not 0 < groesse <= MAX_TEIL_BYTES):
            raise UpdateFehler("ps5upd.manifest_kaputt")
        teile.append(Teil(url, versatz, groesse, pruefsumme))
        naechster += groesse
    if naechster != gesamt:
        raise UpdateFehler("ps5upd.manifest_kaputt")
    return Manifest(gesamt, teile, _hex64(daten.get("packageDigest")))


def manifest_holen(url: str, abbruch: Callable[[], bool] | None = None) -> Manifest:
    """Manifest holen und pruefen."""
    return manifest_lesen(holen(url, MAX_MANIFEST, abbruch=abbruch))


# ---------------------------------------------------------------------------
# Laden
# ---------------------------------------------------------------------------
def teildatei(ziel: str) -> str:
    return ziel + ".teil"


def merkdatei(ziel: str) -> str:
    return ziel + ".teil.json"


def datei_laden(url: str, ziel: str,
                fortschritt: Callable[[int, int], None] | None = None,
                abbruch: Callable[[], bool] | None = None,
                versuche: int = 4) -> str:
    """Laedt eine einzelne Datei von Sonys CDN (PS4-Update-Paket).

    Setzt bei unterbrochenen Downloads fort (Range-Request).
    Schreibt erst in ``<ziel>.teil``, benennt nach Fertigstellung um.

    Args:
        fortschritt: ``f(geladen_bytes, gesamt_bytes)`` - thread-sicher.
        abbruch: ``True`` -> ``UpdateFehler("ps5upd.abgebrochen")``.

    Returns:
        ``ziel``.

    Raises:
        UpdateFehler: ``ps5upd.host_fremd``, ``ps5upd.http|<code>``,
            ``ps5upd.netz|<exc>``, ``ps5upd.abgebrochen``.
    """
    if not url_erlaubt(url):
        raise UpdateFehler("ps5upd.host_fremd")
    teil = teildatei(ziel)
    os.makedirs(os.path.dirname(os.path.abspath(ziel)), exist_ok=True)
    geladen = os.path.getsize(teil) if os.path.isfile(teil) else 0
    gesamt = 0
    for versuch in range(versuche + 1):
        if abbruch is not None and abbruch():
            raise UpdateFehler("ps5upd.abgebrochen")
        try:
            antwort = netz_abbruch.oeffnen(
                lambda ab=geladen: _oeffner().open(_anfrage(url, ab), timeout=30), abbruch, _abbruch_fehler)
            with antwort, netz_abbruch.wache(antwort, abbruch):
                status = getattr(antwort, "status", 200)
                if geladen > 0 and status != 206:
                    geladen = 0
                try:
                    cl = int(antwort.headers.get("Content-Length") or 0)
                    if cl > 0:
                        gesamt = geladen + cl
                except (TypeError, ValueError):
                    pass
                if fortschritt is not None:
                    fortschritt(geladen, gesamt)
                mode = "r+b" if (geladen > 0 and os.path.isfile(teil)) else "wb"
                with open(teil, mode) as datei:
                    if geladen > 0:
                        datei.seek(0, 2)
                    while True:
                        block = netz_abbruch.stueck_lesen(antwort, abbruch, _abbruch_fehler)
                        if not block:
                            break
                        datei.write(block)
                        geladen += len(block)
                        if fortschritt is not None:
                            fortschritt(geladen, gesamt)
            if gesamt > 0 and geladen < gesamt:
                # Sauber, aber zu frueh beendet: Ohne diese Pruefung wuerde die halbe Datei als fertig umbenannt.
                # Als Netzfehler behandelt, setzt der naechste Versuch per Range fort.
                raise ConnectionError("Antwort zu kurz (%d von %d)" % (geladen, gesamt))
            break
        except UpdateFehler:
            raise
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and geladen > 0:
                # "Requested Range Not Satisfiable": Ab ``geladen`` gibt es nichts mehr. Entweder ist die Teildatei
                # schon vollstaendig (das Umbenennen war beim letzten Mal gescheitert) - dann ist sie fertig -, oder
                # sie ist unbrauchbar und wird neu geladen. Vorher hiess das fuer jeden weiteren Start "HTTP 416".
                if _gesamt_aus_inhaltsbereich(exc) == geladen:
                    break
                try:
                    os.remove(teil)
                except OSError as fehler:
                    raise UpdateFehler("ps5upd.netz|%s" % fehler) from fehler
                geladen = gesamt = 0
                if versuch >= versuche:
                    raise UpdateFehler("ps5upd.http|%d" % exc.code) from exc
                continue
            raise UpdateFehler("ps5upd.http|%d" % exc.code) from exc
        except (urllib.error.URLError, OSError, ssl.SSLError,
                http.client.HTTPException) as exc:
            if versuch >= versuche:
                raise UpdateFehler("ps5upd.netz|%s" % exc) from exc
            if netz_abbruch.schlafen(min(2.0 * (versuch + 1), 8.0), abbruch):
                raise UpdateFehler("ps5upd.abgebrochen") from exc
    _fertig_umbenennen(teil, ziel, abbruch)
    return ziel


def _gesamt_aus_inhaltsbereich(fehler: "urllib.error.HTTPError") -> int:
    """Die Gesamtgroesse aus ``Content-Range: bytes */<gesamt>`` einer 416-Antwort, sonst 0."""
    try:
        wert = str(fehler.headers.get("Content-Range") or "")
    except AttributeError:
        return 0
    treffer = re.search(r"/\s*(\d+)\s*$", wert)
    return int(treffer.group(1)) if treffer else 0


def _fertig_umbenennen(teil: str, ziel: str, abbruch: Callable[[], bool] | None) -> None:
    """``os.replace(teil, ziel)`` - mit Geduld: Unter Windows haelt ein Virenscanner die frisch geschriebene Datei
    gern ein paar Sekunden fest ([WinError 32]). Scheitert es am Ende doch, bleibt die vollstaendige Teildatei liegen
    und der naechste Start schliesst den Download ab (siehe 416 oben)."""
    versuche = 10
    for nummer in range(versuche):
        try:
            os.replace(teil, ziel)
            return
        except OSError as exc:
            if nummer >= versuche - 1:
                raise UpdateFehler("ps5upd.speichern|%s" % exc) from exc
            if netz_abbruch.schlafen(0.5, abbruch):
                raise UpdateFehler("ps5upd.abgebrochen") from exc


def _kennung(manifest: Manifest) -> str:
    """Woran ein Merkstand zu diesem Manifest gehoert."""
    text = "|".join("%d:%d:%s" % (t.versatz, t.groesse, t.sha256) for t in manifest.teile)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _bereich_pruefsumme(dateipfad: str, versatz: int, groesse: int,
                        abbruch: Callable[[], bool] | None,
                        erwartet: str = "") -> str:
    h = hashlib.sha1() if len(erwartet) == 40 else hashlib.sha256()
    with open(dateipfad, "rb") as datei:
        datei.seek(versatz)
        rest = groesse
        while rest > 0:
            if abbruch is not None and abbruch():
                raise UpdateFehler("ps5upd.abgebrochen")
            block = datei.read(min(_BLOCK, rest))
            if not block:
                break
            h.update(block)
            rest -= len(block)
    return h.hexdigest()


def _merk_lesen(pfad: str, kennung: str, anzahl: int) -> list[int]:
    try:
        with open(pfad, "r", encoding="utf-8") as datei:
            daten = json.load(datei)
        if daten.get("kennung") == kennung and len(daten.get("geladen", [])) == anzahl:
            return [max(0, int(x)) for x in daten["geladen"]]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return [0] * anzahl


def _merk_schreiben(pfad: str, kennung: str, geladen: list[int]) -> None:
    try:
        zwischen = pfad + ".neu"
        with open(zwischen, "w", encoding="utf-8") as datei:
            json.dump({"kennung": kennung, "geladen": geladen}, datei)
        os.replace(zwischen, pfad)
    except OSError as exc:
        logger.debug("Merkstand nicht schreibbar (%s): %s", pfad, exc)


def _dateisystem(pfad: str) -> str:
    """Name des Dateisystems unter ``pfad`` (Windows, z. B. ``NTFS``/``exFAT``); sonst oder bei Fehler ``""``."""
    if os.name != "nt":
        return ""
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        wurzel = ctypes.create_unicode_buffer(300)
        if not k32.GetVolumePathNameW(os.path.abspath(pfad), wurzel, 300):
            return ""
        name = ctypes.create_unicode_buffer(64)
        if not k32.GetVolumeInformationW(wurzel.value, None, 0, None, None, None, name, 64):
            return ""
        return name.value
    except Exception:  # noqa: BLE001
        return ""


def _datei_strecken(pfad: str, groesse: int) -> bool:
    """Streckt ``pfad`` auf ``groesse``, ohne die Luecke zu beschreiben. ``False``: geht hier nicht schnell.

    Gemessen 02.11.2026 auf exFAT (USB-Platte, 1 GiB): Pythons ``truncate`` fuellt unter Windows in 4-KiB-Schritten
    mit Nullen (0,22 MB/s - 52 GB haetten ueber zwei Tage gedauert, ohne ein Byte zu laden), ``SetEndOfFile`` braucht
    69 s je GiB. Nur NTFS (als duenn besetzte Datei) und POSIX strecken sofort.
    """
    if os.name != "nt":
        with open(pfad, "ab") as datei:
            datei.truncate(groesse)
        return True
    if _dateisystem(pfad).upper() != "NTFS":
        return False
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
                                        ctypes.c_void_p]
        k32.SetFilePointerEx.argtypes = [wintypes.HANDLE, ctypes.c_longlong, ctypes.c_void_p, wintypes.DWORD]
        k32.SetEndOfFile.argtypes = [wintypes.HANDLE]
        with open(pfad, "ab") as datei:
            handle = msvcrt.get_osfhandle(datei.fileno())
            zurueck = wintypes.DWORD()
            if not k32.DeviceIoControl(handle, 0x000900C4, None, 0, None, 0, ctypes.byref(zurueck), None):
                return False            # FSCTL_SET_SPARSE abgelehnt
            return bool(k32.SetFilePointerEx(handle, groesse, None, 0) and k32.SetEndOfFile(handle))
    except Exception as exc:  # noqa: BLE001
        logger.debug("Teildatei nicht duenn streckbar (%s): %s", pfad, exc)
        return False


def reihenstand(manifest: Manifest, geladen: list[int]) -> tuple[list[int], int]:
    """Der Merkstand, beschnitten auf das, was der Reihe nach ab Dateianfang lueckenlos geladen ist.

    Returns:
        ``(geladen, stelle)``: hinter dem ersten unvollstaendigen Teil zaehlt nichts mehr; ``stelle`` ist das
        Dateiende, an dem es weitergeht.
    """
    neu = [0] * len(manifest.teile)
    for i, stueck in enumerate(manifest.teile):
        menge = min(max(0, geladen[i]), stueck.groesse)
        neu[i] = menge
        if menge < stueck.groesse:
            return neu, stueck.versatz + menge
    return neu, manifest.gesamt


def paket_laden(manifest: Manifest, ziel: str,
                fortschritt: Callable[[int, int], None] | None = None,
                abbruch: Callable[[], bool] | None = None,
                faeden: int = 3, versuche: int = 4) -> str:
    """Laedt alle Teile in **eine** Datei und prueft jedes gegen seine SHA-256.

    Geschrieben wird in ``<ziel>.teil`` (auf NTFS/POSIX vorab duenn auf die
    Endgroesse gestreckt und parallel, sonst der Reihe nach angehaengt),
    daneben ``<ziel>.teil.json`` mit dem Stand je Teil. Bricht etwas ab, setzt
    der naechste Aufruf bei dem fort, was schon da ist (Bereichsanfrage). Erst
    wenn jedes Teil stimmt, wird zu ``ziel`` umbenannt.

    Args:
        fortschritt: ``f(geladen_bytes, gesamt_bytes)`` - aus mehreren Faeden,
            muss selbst thread-sicher sein.
        abbruch: ``True`` -> Abbruch mit ``UpdateFehler("ps5upd.abgebrochen")``;
            der Merkstand bleibt fuer die Fortsetzung stehen.
        faeden: Teile, die gleichzeitig geladen werden.

    Returns:
        ``ziel``.

    Raises:
        UpdateFehler: ``ps5upd.platz`` (zu wenig freier Platz),
            ``ps5upd.pruefsumme|<n>`` (Teil n stimmt auch nach neuem Laden nicht),
            ``ps5upd.abgebrochen`` oder ein Netz-/Systemfehler.
    """
    teil = teildatei(ziel)
    merk = merkdatei(ziel)
    os.makedirs(os.path.dirname(os.path.abspath(ziel)), exist_ok=True)
    kennung = _kennung(manifest)
    geladen = _merk_lesen(merk, kennung, len(manifest.teile))
    bereits = os.path.getsize(teil) if os.path.isfile(teil) else 0
    # Der Reihe nach (ein Faden, die Datei waechst nur am Ende), wo sie sich nicht sofort strecken laesst (exFAT/FAT).
    der_reihe_nach = False
    if bereits != manifest.gesamt:
        frei = shutil.disk_usage(os.path.dirname(os.path.abspath(ziel))).free
        if frei < manifest.gesamt - bereits + 64 * 1024 * 1024:
            raise UpdateFehler("ps5upd.platz")
        try:
            if _datei_strecken(teil, manifest.gesamt):
                geladen = [0] * len(manifest.teile)
            else:
                der_reihe_nach = True
                geladen, stelle = reihenstand(manifest, geladen)
                if bereits < stelle:
                    geladen, stelle = [0] * len(manifest.teile), 0
                with open(teil, "ab") as datei:
                    datei.truncate(stelle)          # nur kuerzen oder anlegen - das geht sofort
        except OSError as exc:
            raise UpdateFehler("ps5upd.platz|%s" % exc) from exc
    logger.info("PS5-Update: %s, %d Teile, ab %d Bytes", "der Reihe nach" if der_reihe_nach else "parallel",
                len(manifest.teile), sum(geladen))

    sperre = threading.Lock()
    naechstes = [0]
    fehler: list[BaseException] = []
    stand = {"summe": sum(geladen)}

    def _melden() -> None:
        if fortschritt is not None:
            fortschritt(stand["summe"], manifest.gesamt)

    def _teil_laden(i: int) -> None:
        stueck = manifest.teile[i]
        for versuch in range(versuche + 1):
            if (abbruch is not None and abbruch()) or fehler:
                raise UpdateFehler("ps5upd.abgebrochen")
            try:
                _teil_einmal(i, stueck)
                # Pruefen - bei Abweichung einmal komplett neu laden.
                if _bereich_pruefsumme(teil, stueck.versatz, stueck.groesse,
                                       abbruch, stueck.sha256) == stueck.sha256:
                    return
                with sperre:
                    stand["summe"] -= geladen[i]
                    geladen[i] = 0
                    _merk_schreiben(merk, kennung, geladen)
                if versuch >= 1:
                    raise UpdateFehler("ps5upd.pruefsumme|%d" % (i + 1))
            except UpdateFehler:
                raise
            except (urllib.error.URLError, OSError, ssl.SSLError, ConnectionError,
                    http.client.HTTPException) as exc:
                if getattr(exc, "errno", None) in (errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC)):
                    # Das Ziellaufwerk ist voll - das behebt kein neuer Versuch, und ein Netzfehler ist es nicht.
                    raise UpdateFehler("ps5upd.platz|%s" % exc) from exc
                if versuch >= versuche:
                    raise UpdateFehler("ps5upd.netz|%s" % exc) from exc
                if netz_abbruch.schlafen(min(2.0 * (versuch + 1), 8.0), lambda: (abbruch is not None and abbruch()) or bool(fehler)):
                    raise UpdateFehler("ps5upd.abgebrochen") from exc
        raise UpdateFehler("ps5upd.netz|?")

    def _teil_einmal(i: int, stueck: Teil) -> None:
        ab = geladen[i]
        if ab >= stueck.groesse:
            return
        if not url_erlaubt(stueck.url):
            raise UpdateFehler("ps5upd.host_fremd")
        def _stopp() -> bool:
            # Auch wenn ein anderer Faden gescheitert ist: nicht erst das ganze Teil zu Ende laden.
            return (abbruch is not None and abbruch()) or bool(fehler)

        antwort = netz_abbruch.oeffnen(lambda: _oeffner().open(_anfrage(stueck.url, ab), timeout=30),
                                       _stopp, _abbruch_fehler)
        with antwort, netz_abbruch.wache(antwort, _stopp):
            if ab > 0 and getattr(antwort, "status", 200) != 206:
                # Der Server ignoriert die Bereichsanfrage: von vorn.
                with sperre:
                    stand["summe"] -= geladen[i]
                    geladen[i] = ab = 0
            letzter_merk = geladen[i]
            with open(teil, "r+b") as datei:
                datei.seek(stueck.versatz + ab)
                try:
                    while geladen[i] < stueck.groesse:
                        block = netz_abbruch.stueck_lesen(
                            antwort, _stopp, _abbruch_fehler, min(netz_abbruch.STUECK, stueck.groesse - geladen[i]))
                        if not block:
                            break
                        datei.write(block)
                        with sperre:
                            geladen[i] += len(block)
                            stand["summe"] += len(block)
                        _melden()
                        if geladen[i] - letzter_merk >= _MERKPUNKT:
                            datei.flush()
                            with sperre:
                                _merk_schreiben(merk, kennung, geladen)
                            letzter_merk = geladen[i]
                except UpdateFehler:
                    # Abbruch: Stand sichern, damit ein neuer Start genau hier fortsetzt.
                    datei.flush()
                    with sperre:
                        _merk_schreiben(merk, kennung, geladen)
                    raise
                datei.flush()
        if geladen[i] < stueck.groesse:
            raise ConnectionError("Antwort zu kurz (%d von %d)" % (geladen[i], stueck.groesse))
        with sperre:
            _merk_schreiben(merk, kennung, geladen)

    def _arbeiter() -> None:
        while True:
            with sperre:
                if fehler or naechstes[0] >= len(manifest.teile):
                    return
                i = naechstes[0]
                naechstes[0] += 1
            try:
                _teil_laden(i)
            except BaseException as exc:  # noqa: BLE001
                with sperre:
                    fehler.append(exc)
                return

    _melden()
    arbeiter = [threading.Thread(target=_arbeiter, daemon=True, name="ps5-update-%d" % n)
                for n in range(1 if der_reihe_nach else max(1, min(int(faeden), len(manifest.teile))))]
    for faden in arbeiter:
        faden.start()
    for faden in arbeiter:
        faden.join()
    if fehler:
        erster = fehler[0]
        if isinstance(erster, UpdateFehler):
            raise erster
        raise UpdateFehler("ps5upd.netz|%s" % erster)
    os.replace(teil, ziel)
    try:
        os.remove(merk)
    except OSError:
        pass
    return ziel
