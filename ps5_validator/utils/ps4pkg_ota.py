# -*- coding: utf-8 -*-
"""OTA: ein Paket ueber das Netzwerk auf die Konsole bringen.

Zwei Wege, beide ohne Kabel und ohne USB-Stick:

**1. Die Konsole holt das Paket** (``RpiClient`` + ``PaketServer``). Der PC
stellt die Datei auf einem kleinen HTTP-Server bereit und sagt der Konsole,
wo sie liegt. Das ist der Weg des *Remote Package Installer* von flatz
(PS4-Anwendung, Port 12800): ``POST /api/install`` mit der Adresse; danach
fragt man den Fortschritt ab. Das PS4 PKG Tool von pearlxcore benutzt
denselben Weg (mit Node.js ``http-server`` als Dateiserver); hier uebernimmt
Python den Server.

**2. Der PC schickt das Paket** (``DpiClient``). Der Paketmanager von OnionHEN
(DPI v2, das Plugin ``DPIV00001.elf``) nimmt ``.pkg`` bis 50 GB in Bloecken
entgegen und installiert sie. Das Protokoll ist das seiner eigenen
Weboberflaeche - ihr Quelltext steckt in der ELF-Datei und wurde dort
gelesen (kein Mitschnitt, kein Test an der Konsole).

**Ungeprueft an der Konsole.** Beide Clients sind gegen Nachbildungen der
Gegenstelle getestet, die nach denselben Quellen gebaut sind. Ob eine echte
Konsole ein Paket annimmt, haengt von Firmware, Betriebsart und Paket ab -
und ein erfolgreicher Versand heisst nicht, dass das Spiel danach startet.

Das Modul bleibt sprachfrei (keine ``i18n``); Fehler tragen einen festen
Schluessel in ``OtaFehler.schluessel``, den die Oberflaeche uebersetzt.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import os
import re
import secrets
import socket
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable

logger = logging.getLogger("PS5Converter.ps4pkg_ota")

#: Der Standardport des Remote Package Installer und des DPI-Plugins.
STANDARD_PORT = 12800

#: Der DPI-Paketmanager nimmt hoechstens so viel an (laut seiner Weboberflaeche).
DPI_HOECHSTGROESSE = 50 * 1024 ** 3

#: Der erste Block des DPI-Versands ist 1 MiB, die weiteren 128 MiB.
DPI_ERSTER_BLOCK = 1024 * 1024
DPI_BLOCK = 128 * 1024 * 1024

BLOCK_LESEN = 1024 * 1024


class OtaFehler(Exception):
    """Ein Versand ist gescheitert. ``schluessel`` benennt den Grund."""

    def __init__(self, schluessel: str, text: str = "") -> None:
        super().__init__(text or schluessel)
        self.schluessel = schluessel
        self.text = text


class OtaAbgebrochen(OtaFehler):
    """Der Anwender hat abgebrochen."""

    def __init__(self) -> None:
        super().__init__("abgebrochen")


# ---------------------------------------------------------------------------
# Adressen
# ---------------------------------------------------------------------------

def adresse_gueltig(text: str) -> bool:
    """Ist ``text`` eine IPv4-Adresse in Punktschreibweise?"""
    teile = (text or "").strip().split(".")
    if len(teile) != 4:
        return False
    try:
        return all(0 <= int(t) <= 255 and t.isdigit() for t in teile)
    except ValueError:
        return False


def eigene_adresse_fuer(ziel_ip: str) -> str:
    """Die Adresse dieses Rechners, ueber die ``ziel_ip`` erreichbar ist.

    Ein UDP-Socket wird ``connect``-iert (es wird nichts gesendet) - das
    Betriebssystem waehlt dabei die Schnittstelle, die es auch fuer echten
    Verkehr nehmen wuerde. Liefert einen leeren String, wenn es keine gibt.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1.0)
            s.connect((ziel_ip, 9))
            adresse = s.getsockname()[0]
            return "" if adresse.startswith("0.") else adresse
    except OSError:
        return ""


def lokale_adressen() -> list[str]:
    """Die IPv4-Adressen dieses Rechners ohne Loopback, ohne Duplikate."""
    adressen: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            adresse = info[4][0]
            if not adresse.startswith("127.") and adresse not in adressen:
                adressen.append(adresse)
    except OSError:
        pass
    return adressen


# ---------------------------------------------------------------------------
# Der Dateiserver
# ---------------------------------------------------------------------------

_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


def bereich_auswerten(kopf: str, laenge: int) -> "tuple[int, int] | None | str":
    """Liest einen ``Range``-Kopf.

    Returns:
        ``None`` ohne Kopf (ganze Datei), ``(von, bis)`` einschliesslich, oder
        ``"ungueltig"``, wenn der Bereich ausserhalb der Datei liegt (-> 416).
        Mehrere Bereiche sind nicht vorgesehen und gelten als ungueltig.
    """
    if not kopf:
        return None
    treffer = _RANGE.match(kopf.strip())
    if not treffer or (not treffer.group(1) and not treffer.group(2)):
        return "ungueltig"
    anfang, ende = treffer.group(1), treffer.group(2)
    if anfang == "":
        # letzte N Bytes
        n = int(ende)
        if n <= 0:
            return "ungueltig"
        return (max(0, laenge - n), laenge - 1) if laenge > 0 else "ungueltig"
    von = int(anfang)
    bis = int(ende) if ende else laenge - 1
    if von >= laenge or bis < von:
        return "ungueltig"
    return (von, min(bis, laenge - 1))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "PS4PkgOTA"

    def log_message(self, *argumente) -> None:   # kein Lärm auf stderr
        return

    def _freigabe(self) -> "tuple[str, str] | None":
        """``(name, pfad)`` der angefragten Datei - oder ``None`` (Antwort ist dann schon gesendet)."""
        srv: PaketServer = self.server.paketserver   # type: ignore[attr-defined]
        if srv.nur_ip and self.client_address[0] != srv.nur_ip:
            self.send_error(403, "Forbidden")
            return None
        teile = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path).split("/")
        if len(teile) != 3 or teile[0] != "" or teile[1] != srv.token:
            self.send_error(404, "Not Found")
            return None
        pfad = srv.dateien.get(teile[2])
        if not pfad or not os.path.isfile(pfad):
            self.send_error(404, "Not Found")
            return None
        return teile[2], pfad

    def _senden(self, mit_koerper: bool) -> None:
        gefunden = self._freigabe()
        if gefunden is None:
            return
        name, pfad = gefunden
        srv: PaketServer = self.server.paketserver   # type: ignore[attr-defined]
        laenge = os.path.getsize(pfad)
        bereich = bereich_auswerten(self.headers.get("Range", ""), laenge)
        if bereich == "ungueltig":
            self.send_response(416)
            self.send_header("Content-Range", "bytes */%d" % laenge)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        von, bis = (0, laenge - 1) if bereich is None else bereich   # type: ignore[misc]
        teil = bis - von + 1 if laenge else 0
        self.send_response(200 if bereich is None else 206)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(teil))
        if bereich is not None:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (von, bis, laenge))
        self.end_headers()
        srv._anfrage_notieren(self.command, name, von, bis)
        if not mit_koerper or teil <= 0:
            return
        rest = teil
        try:
            with open(pfad, "rb") as datei:
                datei.seek(von)
                while rest > 0 and not srv._anhalten.is_set():
                    block = datei.read(min(BLOCK_LESEN, rest))
                    if not block:
                        break
                    self.wfile.write(block)
                    rest -= len(block)
                    srv._gesendet_zaehlen(name, len(block))
        except (ConnectionError, OSError):
            # Die Konsole bricht Verbindungen ab und baut sie neu auf - normal.
            self.close_connection = True

    def do_GET(self) -> None:   # noqa: N802
        self._senden(True)

    def do_HEAD(self) -> None:   # noqa: N802
        self._senden(False)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    #: Unter Windows erlaubt ``SO_REUSEADDR`` das Binden an einen Port, an dem
    #: schon jemand lauscht - ein zweiter Server uebernaehme still den Port.
    #: Dort gilt stattdessen ``SO_EXCLUSIVEADDRUSE``.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        # ``HTTPServer.server_bind`` ruft ``getfqdn`` - das braucht ohne
        # Namensaufloesung Sekunden. Der Name wird nicht gebraucht.
        import socketserver
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        socketserver.TCPServer.server_bind(self)
        self.server_name = self.server_address[0]
        self.server_port = self.server_address[1]


class PaketServer:
    """Stellt einzelne Dateien per HTTP bereit - und sonst nichts.

    * Nur Dateien, die mit :meth:`datei_anbieten` angemeldet sind; kein
      Verzeichnis, keine Auflistung.
    * Der Pfad traegt ein Zufallszeichen (``/<token>/<name>``), damit andere
      Geraete im Netz ihn nicht erraten.
    * Mit ``nur_ip`` antwortet der Server nur diesem Client (der Konsole).
    * ``Range``-Anfragen werden bedient (die Konsole laedt in Stuecken und
      setzt nach Abbruechen fort).
    """

    def __init__(self, adresse: str = "0.0.0.0", port: int = 0, nur_ip: str = "") -> None:
        self.adresse = adresse
        self.port = port
        self.nur_ip = nur_ip
        self.token = secrets.token_hex(6)
        self.dateien: dict[str, str] = {}
        self._server: "_Server | None" = None
        self._faden: "threading.Thread | None" = None
        self._anhalten = threading.Event()
        self._schloss = threading.Lock()
        self._gesendet: dict[str, int] = {}
        self.anfragen: list[tuple[str, str, int, int]] = []

    # -- Anmeldung -----------------------------------------------------
    def datei_anbieten(self, pfad: str) -> str:
        """Meldet eine Datei an. Gibt den Namen im Pfad zurueck (Dateiname, bei Doppeln mit Zaehler)."""
        name = os.path.basename(pfad)
        wurzel, endung = os.path.splitext(name)
        zaehler = 1
        while name in self.dateien and self.dateien[name] != pfad:
            zaehler += 1
            name = "%s_%d%s" % (wurzel, zaehler, endung)
        self.dateien[name] = pfad
        return name

    def url(self, name: str, host: str) -> str:
        return "http://%s:%d/%s/%s" % (host, self.port, self.token, urllib.parse.quote(name))

    # -- Betrieb -------------------------------------------------------
    def starten(self) -> int:
        """Startet den Server und gibt den (tatsaechlichen) Port zurueck."""
        if self._server is not None:
            return self.port
        try:
            self._server = _Server((self.adresse, self.port), _Handler)
        except OSError as fehler:
            raise OtaFehler("server_start", str(fehler)) from fehler
        self._server.paketserver = self      # type: ignore[attr-defined]
        self.port = self._server.server_address[1]
        self._anhalten.clear()
        self._faden = threading.Thread(target=self._server.serve_forever,
                                       kwargs={"poll_interval": 0.2}, daemon=True)
        self._faden.start()
        return self.port

    def anhalten(self) -> None:
        self._anhalten.set()
        server, self._server = self._server, None
        if server is not None:
            try:
                server.shutdown()
            finally:
                server.server_close()
        if self._faden is not None:
            self._faden.join(timeout=5)
            self._faden = None

    @property
    def laeuft(self) -> bool:
        return self._server is not None

    # -- Zaehler -------------------------------------------------------
    def _gesendet_zaehlen(self, name: str, n: int) -> None:
        with self._schloss:
            self._gesendet[name] = self._gesendet.get(name, 0) + n

    def _anfrage_notieren(self, methode: str, name: str, von: int, bis: int) -> None:
        with self._schloss:
            self.anfragen.append((methode, name, von, bis))
            del self.anfragen[:-200]

    def gesendet(self, name: str = "") -> int:
        """Bytes, die an Clients gegangen sind - je Datei oder insgesamt."""
        with self._schloss:
            if name:
                return self._gesendet.get(name, 0)
            return sum(self._gesendet.values())


# ---------------------------------------------------------------------------
# HTTP-Hilfen der Clients
# ---------------------------------------------------------------------------

def _anfrage(ip: str, port: int, methode: str, pfad: str, *, daten: "bytes | None" = None,
             kopf: "dict[str, str] | None" = None, zeit: float = 8.0) -> "tuple[int, bytes]":
    """Eine kurze Anfrage; wirft ``OtaFehler('netz')``, wenn die Gegenstelle nicht antwortet."""
    verbindung = http.client.HTTPConnection(ip, port, timeout=zeit)
    try:
        verbindung.request(methode, pfad, body=daten, headers=kopf or {})
        antwort = verbindung.getresponse()
        return antwort.status, antwort.read()
    except (OSError, http.client.HTTPException) as fehler:
        raise OtaFehler("netz", "%s:%d - %s" % (ip, port, fehler)) from fehler
    finally:
        verbindung.close()


def _json(roh: bytes) -> dict:
    try:
        wert = json.loads(roh.decode("utf-8", "replace"))
    except ValueError as fehler:
        raise OtaFehler("antwort", "keine JSON-Antwort: %r" % roh[:120]) from fehler
    if not isinstance(wert, dict):
        raise OtaFehler("antwort", "unerwartete Antwort: %r" % roh[:120])
    return wert


# ---------------------------------------------------------------------------
# Remote Package Installer (PS4)
# ---------------------------------------------------------------------------

@dataclass
class RpiFortschritt:
    """Was ``get_task_progress`` meldet (nur, was wir anzeigen)."""
    laenge: int = 0
    uebertragen: int = 0
    gesamt_laenge: int = 0
    gesamt_uebertragen: int = 0
    rest_sekunden: int = 0
    vorbereitung_prozent: int = 0
    fehler: int = 0
    roh: dict = field(default_factory=dict)

    @property
    def prozent(self) -> float:
        gesamt = self.gesamt_laenge or self.laenge
        fertig = self.gesamt_uebertragen or self.uebertragen
        return 100.0 * fertig / gesamt if gesamt > 0 else 0.0


class RpiClient:
    """Spricht mit dem Remote Package Installer der PS4 (Port 12800)."""

    def __init__(self, ip: str, port: int = STANDARD_PORT, zeit: float = 8.0) -> None:
        self.ip = ip
        self.port = port
        self.zeit = zeit

    def _aufruf(self, endpunkt: str, daten: dict) -> dict:
        status, roh = _anfrage(self.ip, self.port, "POST", "/api/" + endpunkt,
                               daten=json.dumps(daten).encode("utf-8"),
                               kopf={"Content-Type": "application/json"}, zeit=self.zeit)
        if status != 200:
            raise OtaFehler("http", "HTTP %d von /api/%s" % (status, endpunkt))
        antwort = _json(roh)
        if antwort.get("status") not in ("success", None):
            raise OtaFehler("abgelehnt", "%s: %s" % (endpunkt, json.dumps(antwort)[:200]))
        return antwort

    def erreichbar(self) -> bool:
        """Antwortet dort ein Remote Package Installer? (eine harmlose Abfrage)"""
        try:
            antwort = self._aufruf("is_exists", {"title_id": "CUSA00000"})
        except OtaFehler:
            return False
        return "status" in antwort or "exists" in antwort

    def installieren(self, adressen: Iterable[str]) -> int:
        """Gibt der Konsole die Adressen der Pakete (``direct``) und liefert die Aufgabennummer."""
        antwort = self._aufruf("install", {"type": "direct", "packages": list(adressen)})
        if "task_id" not in antwort:
            raise OtaFehler("antwort", "ohne task_id: %s" % json.dumps(antwort)[:200])
        return int(antwort["task_id"])

    def fortschritt(self, aufgabe: int) -> RpiFortschritt:
        a = self._aufruf("get_task_progress", {"task_id": aufgabe})

        def zahl(name: str) -> int:
            try:
                return int(a.get(name, 0) or 0)
            except (TypeError, ValueError):
                return 0

        return RpiFortschritt(
            laenge=zahl("length"), uebertragen=zahl("transferred"),
            gesamt_laenge=zahl("length_total"), gesamt_uebertragen=zahl("transferred_total"),
            rest_sekunden=zahl("rest_sec_total") or zahl("rest_sec"),
            vorbereitung_prozent=zahl("preparing_percent"), fehler=zahl("error"), roh=a)

    def stoppen(self, aufgabe: int) -> None:
        self._aufruf("stop_task", {"task_id": aufgabe})

    def ist_installiert(self, title_id: str) -> bool:
        antwort = self._aufruf("is_exists", {"title_id": title_id})
        return str(antwort.get("exists", "")).lower() == "true"

    def deinstallieren(self, art: str, kennung: str) -> dict:
        """``art``: ``game``/``patch`` (Title-ID) oder ``ac``/``theme`` (Content-ID)."""
        if art in ("game", "patch"):
            return self._aufruf("uninstall_" + art, {"title_id": kennung})
        if art in ("ac", "theme"):
            return self._aufruf("uninstall_" + art, {"content_id": kennung})
        raise ValueError("unbekannte Art: %s" % art)


def rpi_senden(ip: str, dateien: "list[str]", *, port: int = STANDARD_PORT,
               eigene_ip: str = "", server_port: int = 0,
               fortschritt: "Callable[[RpiFortschritt | None, int], None] | None" = None,
               abbruch: "Callable[[], bool] | None" = None,
               abfrage_sekunden: float = 1.0, zeitgrenze: float = 24 * 3600.0,
               server: "PaketServer | None" = None) -> int:
    """Stellt die Pakete bereit, laesst die Konsole sie holen und wartet auf das Ende.

    Args:
        fortschritt: ``(RpiFortschritt | None, gesendete_bytes)`` etwa je Sekunde.
        server: Nur fuer Tests - ein vorbereiteter Server.

    Returns:
        Die Aufgabennummer der Konsole.

    Raises:
        OtaFehler: ``netz`` (keine Verbindung), ``server_start``, ``abgelehnt``,
            ``konsole_fehler`` (die Konsole meldet einen Fehlercode),
            ``zeit``; :class:`OtaAbgebrochen`.
    """
    host = eigene_ip or eigene_adresse_fuer(ip)
    if not host:
        raise OtaFehler("keine_adresse", "keine Adresse dieses Rechners fuer %s" % ip)
    eigener = server is None
    srv = server or PaketServer(adresse=host, port=server_port, nur_ip=ip)
    try:
        if eigener:
            srv.starten()
        namen = [srv.datei_anbieten(p) for p in dateien]
        client = RpiClient(ip, port)
        aufgabe = client.installieren(srv.url(n, host) for n in namen)
        start = time.monotonic()
        letzter = RpiFortschritt()
        fehler_zaehler = 0
        while True:
            if abbruch is not None and abbruch():
                try:
                    client.stoppen(aufgabe)
                except OtaFehler:
                    pass
                raise OtaAbgebrochen()
            if time.monotonic() - start > zeitgrenze:
                raise OtaFehler("zeit")
            try:
                letzter = client.fortschritt(aufgabe)
                fehler_zaehler = 0
            except OtaFehler as fehler:
                fehler_zaehler += 1
                if fehler_zaehler >= 15:
                    raise fehler
            if fortschritt is not None:
                fortschritt(letzter, srv.gesendet())
            if letzter.fehler:
                raise OtaFehler("konsole_fehler", "Fehlercode 0x%X" % (letzter.fehler & 0xFFFFFFFF))
            gesamt = letzter.gesamt_laenge or letzter.laenge
            if gesamt > 0 and (letzter.gesamt_uebertragen or letzter.uebertragen) >= gesamt:
                return aufgabe
            time.sleep(abfrage_sekunden)
    finally:
        if eigener:
            srv.anhalten()


# ---------------------------------------------------------------------------
# OnionHEN-Paketmanager (DPI v2)
# ---------------------------------------------------------------------------

def kopfhash(pfad: str) -> str:
    """SHA-256 der ersten (hoechstens) 1 MiB - das ``head256`` des Paketmanagers."""
    with open(pfad, "rb") as datei:
        return hashlib.sha256(datei.read(DPI_ERSTER_BLOCK)).hexdigest()


def dpi_bloecke(groesse: int) -> list[tuple[int, int]]:
    """Die Aufteilung des Versands: ein erster Block von 1 MiB, dann 128-MiB-Bloecke.

    Returns:
        ``[(versatz, laenge), ...]``; leer bei Groesse 0.
    """
    if groesse <= 0:
        return []
    erster = min(DPI_ERSTER_BLOCK, groesse)
    bloecke = [(0, erster)]
    stelle = erster
    while stelle < groesse:
        laenge = min(DPI_BLOCK, groesse - stelle)
        bloecke.append((stelle, laenge))
        stelle += laenge
    return bloecke


class DpiClient:
    """Spricht mit dem OnionHEN-Paketmanager (Plugin ``DPIV00001``).

    Der Manager lauscht auf **zwei** Ports: dem *API-Port* (``/ping``,
    ``/install``, ``/staged-size``) und dem *Web-Port* (die Oberflaeche,
    ``/api/config``, ``/api/stream``). Welcher der beiden auf 12800 liegt,
    haengt von der Einstellung des Plugins ab - :func:`erkennen` findet es
    heraus.
    """

    def __init__(self, ip: str, api_port: int = STANDARD_PORT, web_port: int = 0,
                 zeit: float = 15.0) -> None:
        self.ip = ip
        self.api_port = api_port
        self.web_port = web_port
        self.zeit = zeit

    # -- kurze Abfragen --------------------------------------------------
    def ping(self) -> dict:
        """``GET /ping`` am API-Port: ``{"ok":true,"name":"pkg-server","version":..,"fw":..,"busy":..}``."""
        status, roh = _anfrage(self.ip, self.api_port, "GET", "/ping", zeit=self.zeit)
        if status != 200:
            raise OtaFehler("http", "HTTP %d von /ping" % status)
        antwort = _json(roh)
        if antwort.get("name") != "pkg-server":
            raise OtaFehler("fremd", "Dort antwortet kein OnionHEN-Paketmanager: %s" % json.dumps(antwort)[:120])
        return antwort

    def konfiguration(self) -> dict:
        """``GET /api/config`` am Web-Port: unter anderem ``api_port``."""
        if not self.web_port:
            raise OtaFehler("ohne_web_port")
        status, roh = _anfrage(self.ip, self.web_port, "GET", "/api/config", zeit=self.zeit)
        if status != 200:
            raise OtaFehler("http", "HTTP %d von /api/config" % status)
        return _json(roh)

    def abgelegte_groesse(self, name: str) -> int:
        """Wie viele Bytes liegen schon unter diesem Namen auf der Konsole (``/staged-size``)?"""
        status, roh = _anfrage(self.ip, self.api_port, "GET",
                               "/staged-size?name=" + urllib.parse.quote(name, safe=""), zeit=self.zeit)
        if status != 200:
            return 0
        antwort = _json(roh)
        try:
            return int(antwort.get("size", 0)) if antwort.get("ok") else 0
        except (TypeError, ValueError):
            return 0

    # -- Versand ---------------------------------------------------------
    def _block_senden(self, pfad: str, name: str, versatz: int, laenge: int, gesamt: int,
                      kopf_hash: str, bei_bytes: "Callable[[int], None]",
                      abbruch: "Callable[[], bool] | None") -> None:
        anfrage = "/install?name=%s&offset=%d&total=%d" % (urllib.parse.quote(name, safe=""), versatz, gesamt)
        if kopf_hash:
            anfrage += "&head256=" + kopf_hash
        verbindung = http.client.HTTPConnection(self.ip, self.api_port, timeout=max(self.zeit, 60.0))
        try:
            verbindung.putrequest("POST", anfrage)
            verbindung.putheader("Content-Type", "text/plain")
            verbindung.putheader("Content-Length", str(laenge))
            verbindung.endheaders()
            with open(pfad, "rb") as datei:
                datei.seek(versatz)
                rest = laenge
                while rest > 0:
                    if abbruch is not None and abbruch():
                        raise OtaAbgebrochen()
                    block = datei.read(min(BLOCK_LESEN, rest))
                    if not block:
                        raise OtaFehler("lesen", "Die Datei endet vor ihrer Groesse: %s" % pfad)
                    verbindung.send(block)
                    rest -= len(block)
                    bei_bytes(len(block))
            antwort = verbindung.getresponse()
            roh = antwort.read()
        except (OSError, http.client.HTTPException) as fehler:
            raise OtaFehler("netz", "Block %d: %s" % (versatz, fehler)) from fehler
        finally:
            verbindung.close()
        daten = _json(roh)
        if antwort.status != 200 or not daten.get("ok"):
            raise OtaFehler("abgelehnt", "Block %d: %s" % (versatz, daten.get("error") or antwort.status))

    def hochladen(self, pfad: str, *, name: str = "",
                  fortschritt: "Callable[[int, int], None] | None" = None,
                  abbruch: "Callable[[], bool] | None" = None, versuche: int = 3) -> dict:
        """Schickt eine ``.pkg`` in Bloecken und schliesst den Versand ab.

        Liegt unter diesem Namen schon eine Datei der richtigen Groesse auf der
        Konsole (``/staged-size``), wird nicht noch einmal gesendet - das
        macht auch die Weboberflaeche des Managers so.

        Args:
            fortschritt: ``(gesendet, gesamt)``.

        Returns:
            Die Antwort des Abschlusses (``{"ok":true,"phase":"accepted",...}``).

        Raises:
            OtaFehler: ``zu_gross`` (ueber 50 GB), ``keine_pkg``, ``leer``, ``netz``,
                ``abgelehnt``, ``fremd``; :class:`OtaAbgebrochen`.
        """
        name = name or os.path.basename(pfad)
        if not name.lower().endswith(".pkg"):
            raise OtaFehler("keine_pkg", name)
        gesamt = os.path.getsize(pfad)
        if gesamt <= 0:
            raise OtaFehler("leer", pfad)
        if gesamt > DPI_HOECHSTGROESSE:
            raise OtaFehler("zu_gross", "%d Bytes" % gesamt)
        self.ping()
        gesendet = [0]

        def _bytes(n: int) -> None:
            gesendet[0] += n
            if fortschritt is not None:
                fortschritt(gesendet[0], gesamt)

        if self.abgelegte_groesse(name) == gesamt:
            gesendet[0] = gesamt
            if fortschritt is not None:
                fortschritt(gesamt, gesamt)
        else:
            kopf = kopfhash(pfad)
            for versatz, laenge in dpi_bloecke(gesamt):
                for versuch in range(1, max(1, versuche) + 1):
                    vorher = gesendet[0]
                    try:
                        self._block_senden(pfad, name, versatz, laenge, gesamt,
                                           kopf if versatz == 0 else "", _bytes, abbruch)
                        break
                    except OtaAbgebrochen:
                        raise
                    except OtaFehler:
                        # Den Zaehler zuruecksetzen: Der Block wird ganz neu gesendet.
                        gesendet[0] = vorher
                        if versuch >= versuche:
                            raise
                        time.sleep(0.5 * versuch)
        anfrage = "/install?name=%s&offset=%d&total=%d&finalize=1" % (
            urllib.parse.quote(name, safe=""), gesamt, gesamt)
        status, roh = _anfrage(self.ip, self.api_port, "POST", anfrage, zeit=max(self.zeit, 60.0))
        antwort = _json(roh)
        if status != 200 or not antwort.get("ok"):
            raise OtaFehler("abgelehnt", "Abschluss: %s" % (antwort.get("error") or status))
        return antwort

    def warten(self, *, abbruch: "Callable[[], bool] | None" = None, zeitgrenze: float = 1800.0,
               abfrage_sekunden: float = 2.0,
               bei_ping: "Callable[[dict], None] | None" = None) -> dict:
        """Wartet, bis der Manager nicht mehr beschaeftigt ist (``busy`` im ``/ping``).

        Die Weboberflaeche des Managers verfolgt den Fortschritt mit einem
        Ereignisstrom am Web-Port; ``/ping`` ist die einfachere Naeherung.
        """
        start = time.monotonic()
        letzter: dict = {}
        sah_beschaeftigt = False
        while time.monotonic() - start < zeitgrenze:
            if abbruch is not None and abbruch():
                raise OtaAbgebrochen()
            letzter = self.ping()
            if bei_ping is not None:
                bei_ping(letzter)
            if letzter.get("busy"):
                sah_beschaeftigt = True
            elif sah_beschaeftigt or time.monotonic() - start > 10:
                return letzter
            time.sleep(abfrage_sekunden)
        raise OtaFehler("zeit")


# ---------------------------------------------------------------------------
# Was lauscht dort?
# ---------------------------------------------------------------------------

#: Ergebnisse von :func:`erkennen`.
ART_DPI_API = "dpi_api"
ART_DPI_WEB = "dpi_web"
ART_RPI = "rpi"


def erkennen(ip: str, port: int = STANDARD_PORT, zeit: float = 3.0) -> str:
    """Welche Art Installationsdienst lauscht auf ``ip:port``? Leer, wenn keiner.

    Nur harmlose Lesezugriffe: ``GET /ping`` (Paketmanager, API-Port),
    ``GET /api/config`` (Paketmanager, Web-Port), ``POST /api/is_exists`` mit
    einer Title-ID, die es nicht gibt (Remote Package Installer).
    """
    try:
        status, roh = _anfrage(ip, port, "GET", "/ping", zeit=zeit)
        if status == 200 and _json(roh).get("name") == "pkg-server":
            return ART_DPI_API
    except OtaFehler:
        pass
    try:
        status, roh = _anfrage(ip, port, "GET", "/api/config", zeit=zeit)
        if status == 200 and "api_port" in _json(roh):
            return ART_DPI_WEB
    except OtaFehler:
        pass
    if RpiClient(ip, port, zeit).erreichbar():
        return ART_RPI
    return ""
