# -*- coding: utf-8 -*-
"""Geraete im Netz finden: NAS und Rechner mit Freigaben - ohne Zusatzpaket (14.11.2026; Vorbild: "Nearby" bei Dump Forge).

Zwei Verfahren, beide nur mit der Standardbibliothek:

* **mDNS** (Multicast-DNS, UDP 5353, Gruppe 224.0.0.251): Die Geraete melden Dienste wie ``_smb._tcp.local`` (Windows-Freigabe), ``_ftp._tcp.local``
  oder ``_nfs._tcp.local`` mit Namen, Adresse und Port. Gefragt wird mit dem "Unicast-Antwort"-Bit (0x8000): Die Antworten kommen dann an unseren
  eigenen Anschluss, ohne dass wir Port 5353 besetzen muessten (den auch das System benutzt).
* **WS-Discovery** (UDP 3702, Gruppe 239.255.255.250): So melden sich Windows-Rechner und viele NAS im Netzwerk-Fenster des Explorers. Die Antwort
  (``ProbeMatches``) nennt die Adresse; ein Name steht dort nicht, er wird aus der Adresse aufgeloest.

Es gibt keinen Subnetz-Scan (wie bei Forge): Gefunden wird nur, was sich selbst meldet. Eine Freigabe laesst sich danach unter Windows direkt als
``\\\\Adresse\\Freigabe`` als Quelle oder Ziel eintragen (UNC; das Programm liest und schreibt dort ohne Zwischenkopie).

Nur die Aufbereitung der Pakete (``mdns_anfrage``, ``mdns_antwort_lesen``, ``wsd_probe``, ``wsd_antwort_lesen``) ist rein und getestet; ``suchen`` ist
die duenne Huelle mit den Anschluessen.
"""
from __future__ import annotations

import re
import socket
import struct
import time
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Iterable

MDNS_GRUPPE = ("224.0.0.251", 5353)
WSD_GRUPPE = ("239.255.255.250", 3702)

#: Dienstname (mDNS) -> Art. ``smb`` heisst: Als UNC-Pfad benutzbar (Windows-Freigabe, Samba).
DIENSTE: "dict[str, str]" = {
    "_smb._tcp.local": "smb",
    "_ftp._tcp.local": "ftp",
    "_nfs._tcp.local": "nfs",
    "_afpovertcp._tcp.local": "afp",
    "_workstation._tcp.local": "pc",
}
_TYP_A, _TYP_PTR, _TYP_TXT, _TYP_AAAA, _TYP_SRV = 1, 12, 16, 28, 33


@dataclass(frozen=True)
class Geraet:
    """Ein gefundenes Geraet: Name (oder Adresse), Adresse, Art (``smb``, ``ftp``, ``nfs``, ``afp``, ``pc``, ``wsd``), Anschluss (0 = unbekannt)."""

    name: str
    adresse: str
    art: str
    port: int = 0

    @property
    def unc(self) -> str:
        """Der Anfang eines UNC-Pfades (``\\\\Adresse\\``) - nur sinnvoll fuer ``smb``, ``pc`` und ``wsd``."""
        return "\\\\" + self.adresse + "\\"


# ---------------------------------------------------------------------------------------------------------------------------
# mDNS
# ---------------------------------------------------------------------------------------------------------------------------
def _name_kodieren(name: str) -> bytes:
    teile = [t for t in name.strip(".").split(".") if t]
    return b"".join(bytes([len(t)]) + t.encode("utf-8") for t in teile) + b"\x00"


def mdns_anfrage(dienste: "Iterable[str]" = tuple(DIENSTE)) -> bytes:
    """Eine mDNS-Anfrage nach den Diensten (PTR), mit dem Bit "bitte direkt an mich antworten"."""
    dienste = list(dienste)
    fragen = b"".join(_name_kodieren(d) + struct.pack(">HH", _TYP_PTR, 0x8001) for d in dienste)
    return struct.pack(">HHHHHH", 0, 0, len(dienste), 0, 0, 0) + fragen


def _name_lesen(daten: bytes, pos: int, tiefe: int = 0) -> "tuple[str, int]":
    """Liest einen DNS-Namen ab ``pos`` (mit Verweisen); Rueckgabe: Name und Position hinter dem Namen im urspruenglichen Datenstrom."""
    teile: "list[str]" = []
    weiter = -1
    while True:
        if pos >= len(daten) or tiefe > 32:
            raise ValueError("Name ausserhalb des Pakets")
        laenge = daten[pos]
        if laenge == 0:
            pos += 1
            break
        if laenge & 0xC0 == 0xC0:
            if pos + 1 >= len(daten):
                raise ValueError("Verweis abgeschnitten")
            ziel = ((laenge & 0x3F) << 8) | daten[pos + 1]
            if weiter < 0:
                weiter = pos + 2
            pos = ziel
            tiefe += 1
            continue
        pos += 1
        if pos + laenge > len(daten):
            raise ValueError("Namensteil abgeschnitten")
        teile.append(daten[pos:pos + laenge].decode("utf-8", errors="replace"))
        pos += laenge
    return ".".join(teile), (weiter if weiter >= 0 else pos)


def mdns_antwort_lesen(daten: bytes, absender: str = "") -> "list[Geraet]":
    """Die Geraete aus einer mDNS-Antwort. Ein kaputtes Paket ergibt eine leere Liste (nie eine Ausnahme)."""
    try:
        return _mdns_antwort(daten, absender)
    except (ValueError, struct.error, IndexError):
        return []


def _mdns_antwort(daten: bytes, absender: str) -> "list[Geraet]":
    if len(daten) < 12:
        return []
    _id, flags, qd, an, ns, ar = struct.unpack_from(">HHHHHH", daten, 0)
    if not flags & 0x8000:                                   # eine Frage, keine Antwort
        return []
    pos = 12
    for _ in range(qd):
        _n, pos = _name_lesen(daten, pos)
        pos += 4
    dienst_von: "dict[str, str]" = {}                        # Instanzname -> Dienstname
    srv: "dict[str, tuple[int, str]]" = {}                   # Instanzname -> (Port, Zielname)
    adressen: "dict[str, list[str]]" = {}                    # Zielname -> Adressen
    for _ in range(an + ns + ar):
        name, pos = _name_lesen(daten, pos)
        typ, _klasse, _ttl, laenge = struct.unpack_from(">HHIH", daten, pos)
        pos += 10
        ende = pos + laenge
        if ende > len(daten):
            raise ValueError("Antwort abgeschnitten")
        if typ == _TYP_PTR:
            instanz, _p = _name_lesen(daten, pos)
            dienst_von[instanz] = name
        elif typ == _TYP_SRV:
            port = struct.unpack_from(">H", daten, pos + 4)[0]
            ziel, _p = _name_lesen(daten, pos + 6)
            srv[name] = (port, ziel)
        elif typ == _TYP_A and laenge == 4:
            adressen.setdefault(name.lower(), []).append(socket.inet_ntoa(daten[pos:pos + 4]))
        pos = ende
    ergebnis: "list[Geraet]" = []
    for instanz, dienst in dienst_von.items():
        art = DIENSTE.get(dienst.lower())
        if art is None:
            continue
        port, ziel = srv.get(instanz, (0, ""))
        anzeige = instanz[: -len("." + dienst)] if instanz.lower().endswith("." + dienst.lower()) else instanz
        liste = adressen.get(ziel.lower()) or ([absender] if absender else [])
        for adresse in liste:
            ergebnis.append(Geraet(anzeige or ziel or adresse, adresse, art, port))
    return ergebnis


# ---------------------------------------------------------------------------------------------------------------------------
# WS-Discovery
# ---------------------------------------------------------------------------------------------------------------------------
_PROBE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope" '
    'xmlns:wsa="http://schemas.xmlsoap.org/ws/2004/08/addressing" '
    'xmlns:wsd="http://schemas.xmlsoap.org/ws/2005/04/discovery">'
    '<soap:Header><wsa:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</wsa:To>'
    '<wsa:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</wsa:Action>'
    '<wsa:MessageID>urn:uuid:%s</wsa:MessageID></soap:Header>'
    '<soap:Body><wsd:Probe/></soap:Body></soap:Envelope>')


def wsd_probe(nachrichten_id: "str | None" = None) -> bytes:
    """Das WS-Discovery-Paket "wer ist da?" (ein ``Probe`` ohne Typfilter)."""
    return (_PROBE % (nachrichten_id or str(uuid.uuid4()))).encode("utf-8")


def wsd_antwort_lesen(daten: bytes, absender: str = "") -> "list[Geraet]":
    """Die Geraete aus einer ``ProbeMatches``-Antwort (Adresse aus ``XAddrs``, sonst der Absender). Kaputtes ergibt eine leere Liste."""
    try:
        wurzel = ET.fromstring(daten)
    except ET.ParseError:
        return []
    ergebnis: "list[Geraet]" = []
    for element in wurzel.iter():
        if element.tag.endswith("}ProbeMatch") or element.tag == "ProbeMatch":
            xaddrs = ""
            for kind in element.iter():
                if kind.tag.endswith("}XAddrs") and kind.text:
                    xaddrs = kind.text
            adresse = ""
            port = 0
            for url in xaddrs.split():
                treffer = re.match(r"^[a-z]+://\[?([^\]/:]+)\]?(?::(\d+))?", url, re.I)
                if treffer:
                    adresse, port = treffer.group(1), int(treffer.group(2) or 0)
                    break
            adresse = adresse or absender
            if adresse:
                ergebnis.append(Geraet(adresse, adresse, "wsd", port))
    return ergebnis


# ---------------------------------------------------------------------------------------------------------------------------
# Anschluesse
# ---------------------------------------------------------------------------------------------------------------------------
def lokale_adressen() -> "list[str]":
    """Die IPv4-Adressen dieses Rechners (ohne 127.x), ueber die Anfragen hinausgehen sollen."""
    gefunden: "list[str]" = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            adresse = info[4][0]
            if not adresse.startswith("127.") and adresse not in gefunden:
                gefunden.append(adresse)
    except OSError:
        pass
    return gefunden


def suchen(zeit: float = 3.0, *, schnittstellen: "list[str] | None" = None,
           mdns_ziele: "list[tuple[str, int]] | None" = None, wsd_ziele: "list[tuple[str, int]] | None" = None,
           melden: "Callable[[Geraet], None] | None" = None, abbruch: "Callable[[], bool] | None" = None) -> "list[Geraet]":
    """Sucht ``zeit`` Sekunden lang und liefert die gefundenen Geraete (ohne Doppelte, nach Adresse und Art).

    ``schnittstellen``: von welchen lokalen Adressen aus gefragt wird (Vorgabe: alle ausser 127.x; ohne eine: die Standardschnittstelle).
    ``mdns_ziele``/``wsd_ziele`` ersetzen die Multicast-Gruppen (die Tests fragen damit ein Geraet auf 127.0.0.1).
    """
    quellen = list(schnittstellen) if schnittstellen is not None else (lokale_adressen() or [""])
    ziele = [(ziel, "mdns", mdns_anfrage()) for ziel in (mdns_ziele or [MDNS_GRUPPE])]
    ziele += [(ziel, "wsd", wsd_probe()) for ziel in (wsd_ziele or [WSD_GRUPPE])]
    sockets: "list[socket.socket]" = []
    for quelle in quellen:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            s.bind((quelle, 0))
            s.settimeout(0.2)
            sockets.append(s)
        except OSError:
            continue
        if quelle:
            try:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(quelle))
            except OSError:
                pass                                         # ohne diese Wahl nimmt das System die Standardschnittstelle
    gefunden: "dict[tuple[str, str], Geraet]" = {}
    try:
        for s in sockets:
            for ziel, _art, paket in ziele:
                try:
                    s.sendto(paket, ziel)
                except OSError:
                    continue
        ende = time.monotonic() + max(0.1, zeit)
        while time.monotonic() < ende and not (abbruch and abbruch()):
            for s in sockets:
                try:
                    daten, (absender, port) = s.recvfrom(65535)
                except (socket.timeout, OSError):
                    continue
                neue = mdns_antwort_lesen(daten, absender) or wsd_antwort_lesen(daten, absender)
                for geraet in neue:
                    schluessel = (geraet.adresse, geraet.art)
                    if schluessel not in gefunden:
                        gefunden[schluessel] = geraet
                        if melden is not None:
                            melden(geraet)
    finally:
        for s in sockets:
            try:
                s.close()
            except OSError:
                pass
    return sorted(gefunden.values(), key=lambda g: (g.name.lower(), g.adresse))
