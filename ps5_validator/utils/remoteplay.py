# -*- coding: utf-8 -*-
"""Die Konsole im Netz finden - ueber das Discovery-Protokoll von Remote Play.

**Die Suche kann, was unsere Dienste-Ampel nicht kann.** Sie spricht das
Discovery-Protokoll auf UDP 9302 - dasselbe, das Remote-Play-Clients wie
Chiaki verwenden - und bekommt dadurch auch von einer Konsole im
**Ruhemodus** eine Antwort (Status 620). Ein TCP-Portscan sieht dort gar
nichts, weil im Standby kein einziges Payload laeuft. Die Uebersicht der
Ansicht KONSOLE ("Konsole pruefen") fragt deshalb beides.

Bis zum 25.09.2026 stand hier auch, was die Funktionen "Remote Play"
(Chiaki starten, Kopplung abfragen) und "ProsperoLight" (Sunshine pruefen)
brauchten. Beide sind auf Wunsch des Nutzers aus dem Programm genommen;
geblieben ist die Suche - der Name des Moduls kommt vom Protokoll.

Nur Standardbibliothek.
"""
from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field

logger = logging.getLogger("PS5Converter.remoteplay")

#: Discovery der PS5 (Remote-Play-Clients nutzen denselben Port und dieselbe Fassung).
PS5_SUCHPORT = 9302
PS5_PROTOKOLL = "00030010"

#: Dasselbe fuer die PS4 - kostet nichts und beantwortet die Frage
#: "ist das ueberhaupt eine PS5?", bevor jemand lange sucht.
PS4_SUCHPORT = 987
PS4_PROTOKOLL = "00020020"


@dataclass(frozen=True)
class Konsole:
    """Was die Konsole auf die Suchanfrage geantwortet hat."""

    adresse: str
    name: str = ""
    kennung: str = ""
    art: str = ""
    firmware: str = ""
    status: int = 0
    felder: dict = field(default_factory=dict)

    @property
    def bereit(self) -> bool:
        """200 = eingeschaltet und ansprechbar."""
        return self.status == 200

    @property
    def standby(self) -> bool:
        """620 = Ruhemodus. Antwortet, laesst sich aber nicht bespielen."""
        return self.status == 620

    @property
    def status_schluessel(self) -> str:
        """Textschluessel fuer die Oberflaeche - uebersetzt wird dort."""
        if self.bereit:
            return "remoteplay.status_an"
        if self.standby:
            return "remoteplay.status_standby"
        return "remoteplay.status_unklar"


def suchen(adresse: str = "", zeit: float = 2.0, port: int = PS5_SUCHPORT,
           protokoll: str = PS5_PROTOKOLL) -> "list[Konsole]":
    """Sucht Konsolen im Netz.

    Ohne ``adresse`` geht die Anfrage als Rundruf ins ganze Teilnetz, mit
    ``adresse`` gezielt an eine Konsole. Antwortet nichts, ist das kein
    Beweis: Manche Router lassen Rundrufe nicht durch, und dann hilft die
    gezielte Frage oder die Adresse von Hand.
    """
    anfrage = ("SRCH * HTTP/1.1\ndevice-discovery-protocol-version:%s\n\n"
               % protokoll)
    ziel = (adresse or "").strip() or "255.255.255.255"

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if not (adresse or "").strip():
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(0.4)
        try:
            sock.sendto(anfrage.encode("ascii"), (ziel, int(port)))
        except OSError as fehler:
            logger.debug("Suchanfrage nicht absendbar: %s", fehler)
            return []

        gefunden: "dict[str, Konsole]" = {}
        ende = time.monotonic() + float(zeit)
        while time.monotonic() < ende:
            try:
                daten, absender = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            konsole = _antwort_lesen(daten, absender[0])
            if konsole is not None:
                gefunden[konsole.adresse] = konsole
        return list(gefunden.values())
    finally:
        sock.close()


def suchen_in(adressen: "list[str]", zeit: float = 2.5, port: int = PS5_SUCHPORT,
              protokoll: str = PS5_PROTOKOLL) -> "list[Konsole]":
    """Fragt jede dieser Adressen einzeln - fuer Netze, in denen kein Rundruf durchkommt.

    Seit dem 26.09.2026 fuer "Konsole & Payloads": Findet der Rundruf nichts,
    werden alle Adressen des eigenen Netzes gezielt gefragt (254 kleine
    UDP-Pakete aus **einem** Socket, dann ``zeit`` Sekunden Antworten
    einsammeln). Antworten gibt nur eine Konsole - anders als ein offener
    TCP-Port, auf dem auch ein Drucker horchen koennte.
    """
    anfrage = ("SRCH * HTTP/1.1\ndevice-discovery-protocol-version:%s\n\n"
               % protokoll).encode("ascii")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.4)
        for adresse in adressen:
            try:
                sock.sendto(anfrage, (str(adresse).strip(), int(port)))
            except OSError as fehler:
                logger.debug("Suchanfrage an %s nicht absendbar: %s", adresse, fehler)
        gefunden: "dict[str, Konsole]" = {}
        ende = time.monotonic() + float(zeit)
        while time.monotonic() < ende:
            try:
                daten, absender = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                # Windows meldet ein ICMP "Port unerreichbar" einer fruehen
                # Anfrage als Fehler beim naechsten Empfang - weiter horchen.
                continue
            konsole = _antwort_lesen(daten, absender[0])
            if konsole is not None:
                gefunden[konsole.adresse] = konsole
        return list(gefunden.values())
    finally:
        sock.close()


def _antwort_lesen(daten: bytes, adresse: str) -> "Konsole | None":
    text = daten.decode("utf-8", errors="replace")
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    if not zeilen:
        return None

    status = 0
    for teil in zeilen[0].split():
        if teil.isdigit():
            status = int(teil)
            break

    felder: dict = {}
    for zeile in zeilen[1:]:
        if ":" in zeile:
            name, _, wert = zeile.partition(":")
            felder[name.strip().lower()] = wert.strip()

    return Konsole(
        adresse=adresse,
        name=felder.get("host-name", ""),
        kennung=felder.get("host-id", ""),
        art=felder.get("host-type", ""),
        firmware=felder.get("system-version", ""),
        status=status,
        felder=felder,
    )


if __name__ == "__main__":  # pragma: no cover - Selbsttest von Hand
    import sys

    wo = sys.argv[1] if len(sys.argv) > 1 else ""
    for k in suchen(wo, zeit=3.0):
        print("%-15s %-20s Status %d  FW %s"
              % (k.adresse, k.name, k.status, k.firmware))
