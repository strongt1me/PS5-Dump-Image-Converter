# -*- coding: utf-8 -*-
"""Schickt ein Payload an die PS5 - auf drei Wegen.

Der uebliche Weg ist elfldr auf Port 9021: roher TCP-Strom, danach die
Senderichtung schliessen, und was das Payload ausgibt, kommt ueber
dieselbe Verbindung zurueck.

Nur laeuft elfldr nicht ueberall. Am 29.08.2026 auf einer echten Konsole
gemessen: Ueber den WebKit-Einstieg von itsplk bleibt 9021 zu, und in der
Autostartliste stand kein elfldr. Trotzdem liefen dort ftpsrv, klogsrv,
gdbsrv und ShadowMountPlus - geladen vom **Payload Manager**, der eine
Weboberflaeche auf Port 8084 mitbringt.

Der nimmt Payloads ueber zwei Aufrufe entgegen::

    POST /manage:upload?filename=<Name>     (Koerper: das nackte ELF)
    GET  /loadpayload:<Pfad auf der Konsole>

Ein Unterschied bleibt und laesst sich nicht wegprogrammieren: Der
Payload Manager reicht die Ausgabe des Payloads **nicht** zurueck.

Genau deshalb ist der bevorzugte Ausweg nicht, jedes Payload dort
hindurchzuschicken, sondern dort **einmal elfldr zu starten**. Danach
steht Port 9021 offen - fuer diesen Aufruf und fuer alle weiteren -, und
die Rueckmeldung ist wieder da. Der direkte Weg ueber den Payload Manager
bleibt als letzte Stufe, wenn kein elfldr zur Hand ist.

OnionHEN und etaHEN sind uebrigens keine Loesung fuer ein fehlendes
elfldr: OnionHEN sagt selbst "The elfldr on port 9021 is REQUIRED".
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.parse
import urllib.request

#: Wo elfldr lauscht (prospero-deploy aus dem SDK nutzt denselben Port).
ELFLDR_PORT = 9021

#: Weboberflaeche des Payload Managers.
PLDMGR_PORT = 8084

#: Wohin der Payload Manager hochgeladene Payloads legt.
PLDMGR_ABLAGE = "/data/pldmgr/payloads"

#: Name des mitgelieferten elfldr-Payloads (in helloworld/).
ELFLDR_NAME = "elfldr-ps5_v0.23.elf"

#: Wie lange nach dem Start von elfldr auf Port 9021 gewartet wird.
ELFLDR_WARTEN = 45.0

#: Wege, die dieses Modul kennt.
WEG_ELFLDR = "elfldr"          # 9021 stand schon offen
WEG_GEWECKT = "geweckt"        # elfldr erst gestartet, dann 9021 benutzt
WEG_PLDMGR = "pldmgr"          # ganz ohne elfldr, ohne Rueckmeldung


class VersandFehler(Exception):
    """Fehler, der dem Anwender wortwoertlich gezeigt werden kann."""


def port_offen(host: str, port: int, timeout: float = 1.5) -> bool:
    """Sieht nach, ob auf der Konsole jemand auf diesem Port zuhoert."""
    buchse = socket.socket()
    buchse.settimeout(timeout)
    try:
        buchse.connect((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        buchse.close()


def ueber_elfldr(host: str, daten: bytes, port: int = ELFLDR_PORT,
                 timeout: float = 30.0) -> str:
    """Schiebt das Payload zu elfldr und liest zurueck, was es ausgibt.

    elfldr beginnt erst, wenn die Gegenseite die Senderichtung schliesst -
    deshalb das ``shutdown``. Was danach zurueckkommt, ist die Ausgabe des
    Payloads; ohne sie liesse sich Erfolg nicht von Fehlschlag
    unterscheiden.
    """
    teile: list[bytes] = []
    with socket.create_connection((host, int(port)), timeout=timeout) as verbindung:
        verbindung.sendall(daten)
        verbindung.shutdown(socket.SHUT_WR)
        while True:
            try:
                stueck = verbindung.recv(4096)
            except (socket.timeout, TimeoutError):
                break
            if not stueck:
                break
            teile.append(stueck)
    return b"".join(teile).decode("utf-8", "replace").strip()


def _pldmgr_ruf(host: str, pfad: str, koerper: bytes | None = None,
                port: int = PLDMGR_PORT, timeout: float = 180.0) -> str:
    adresse = "http://%s:%d%s" % (host, int(port), pfad)
    ruf = urllib.request.Request(
        adresse, data=koerper, method="POST" if koerper is not None else "GET")
    if koerper is not None:
        ruf.add_header("Content-Type", "application/octet-stream")
    with urllib.request.urlopen(ruf, timeout=timeout) as antwort:
        return antwort.read().decode("utf-8", "replace")


def pldmgr_ablageort(host: str, name: str, port: int = PLDMGR_PORT) -> str:
    """Fragt den Payload Manager, wohin er eine Datei dieses Namens legt.

    Den Ordnernamen selbst zu raten ginge meistens gut - aber eben nur
    meistens. Der Dienst weiss es, also wird er gefragt.
    """
    roh = _pldmgr_ruf(host, "/manage:check?filename="
                      + urllib.parse.quote(name), port=port, timeout=30.0)
    try:
        auskunft = json.loads(roh)
    except ValueError:
        auskunft = {}
    ordner = auskunft.get("folder_name")
    if not isinstance(ordner, str) or not ordner:
        ordner = name.rsplit(".", 1)[0]
    return "%s/%s/%s" % (PLDMGR_ABLAGE, ordner, name)


def ueber_pldmgr(host: str, daten: bytes, name: str,
                 port: int = PLDMGR_PORT) -> str:
    """Laedt das Payload in den Payload Manager und startet es dort.

    Rueckgabe ist der Ablageort auf der Konsole, nicht die Ausgabe des
    Payloads - die reicht der Payload Manager nicht zurueck.
    """
    if not name.lower().endswith((".elf", ".bin")):
        raise VersandFehler(
            "Der Payload Manager nimmt nur .elf und .bin an, nicht %r." % name)
    ziel = pldmgr_ablageort(host, name, port=port)
    _pldmgr_ruf(host, "/manage:upload?filename=" + urllib.parse.quote(name),
                koerper=daten, port=port)
    _pldmgr_ruf(host, "/loadpayload:" + urllib.parse.quote(ziel), port=port)
    return ziel



def elfldr_aufwecken(host: str, elfldr_daten: bytes, name: str = ELFLDR_NAME,
                     elfldr_port: int = ELFLDR_PORT,
                     pldmgr_port: int = PLDMGR_PORT,
                     warten: float = ELFLDR_WARTEN) -> bool:
    """Startet elfldr ueber den Payload Manager und wartet auf den Port.

    Das ist der bessere Ausweg, wenn 9021 zu ist: Statt jedes einzelne
    Payload ueber den Payload Manager zu schicken - der die Ausgabe
    verwirft - wird dort **einmal** elfldr gestartet. Danach steht der
    gewohnte Weg offen, mit Rueckmeldung.

    Am 29.08.2026 auf einer echten Konsole gemessen: Port 9021 ging nach
    dem Start binnen weniger Sekunden auf.
    """
    ueber_pldmgr(host, elfldr_daten, name, port=pldmgr_port)
    ende = time.monotonic() + warten
    while time.monotonic() < ende:
        if port_offen(host, elfldr_port):
            return True
        time.sleep(2.0)
    return False


def senden(host: str, daten: bytes, name: str, elfldr_port: int = ELFLDR_PORT,
           pldmgr_port: int = PLDMGR_PORT,
           elfldr_pfad: str = "") -> tuple[str, str, str]:
    """Nimmt den Weg, der offensteht - elfldr zuerst.

    Drei Faelle, in dieser Reihenfolge:

    1. 9021 offen: der gewohnte Weg, mit Ausgabe des Payloads.
    2. 9021 zu, Payload Manager da und ``elfldr_pfad`` gesetzt: erst
       elfldr starten, damit 9021 aufgeht, dann wie Fall 1. Der Port
       bleibt danach offen und steht auch allen weiteren Aufrufen zur
       Verfuegung.
    3. 9021 zu, kein elfldr zur Hand: das Payload geht direkt ueber den
       Payload Manager - es laeuft, aber ohne Rueckmeldung.

    Rueckgabe: (Weg, Ausgabe, Bemerkung).
    """
    if port_offen(host, elfldr_port):
        return WEG_ELFLDR, ueber_elfldr(host, daten, port=elfldr_port), ""

    if not port_offen(host, pldmgr_port):
        raise VersandFehler(
            "Weder elfldr (Port %d) noch der Payload Manager (Port %d) sind "
            "erreichbar." % (elfldr_port, pldmgr_port))

    if elfldr_pfad and os.path.isfile(elfldr_pfad):
        with open(elfldr_pfad, "rb") as fh:
            elfldr_daten = fh.read()
        if elfldr_aufwecken(host, elfldr_daten, os.path.basename(elfldr_pfad),
                            elfldr_port=elfldr_port, pldmgr_port=pldmgr_port):
            return (WEG_GEWECKT, ueber_elfldr(host, daten, port=elfldr_port),
                    os.path.basename(elfldr_pfad))

    ziel = ueber_pldmgr(host, daten, name, port=pldmgr_port)
    return WEG_PLDMGR, "", ziel
