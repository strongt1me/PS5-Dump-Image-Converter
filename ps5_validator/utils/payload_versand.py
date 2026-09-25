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

import codecs
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
#: Am 17.09.2026 von 0.23 auf 0.26 gehoben. Aendert sich der Dateiname, muss er
#: hier mit - test_payload_versand prueft, dass die Datei wirklich daliegt.
ELFLDR_NAME = "elfldr-ps5_v0.26.elf"

#: Wie lange nach dem Start von elfldr auf Port 9021 gewartet wird.
ELFLDR_WARTEN = 45.0

#: In welchen Stuecken :func:`ueber_elfldr` sendet - die Zeitgrenze gilt je
#: Stueck (siehe :func:`stueckweise_senden`).
SENDESTUECK = 64 * 1024

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


def stueckweise_senden(verbindung: socket.socket, daten: bytes) -> None:
    """Sendet alles - mit der Zeitgrenze der Buchse je Stueck.

    Seit Python 3.5 gilt die Zeitgrenze bei ``sendall`` fuer den ganzen
    Aufruf. Bei den gemessenen 1,1 MB/s der Leitung zur Konsole brauchen
    62 MB knapp eine Minute - mit 30 s brach der Versand grosser Payloads
    bis zum 24.09.2026 jedes Mal ab (Durchsicht, U3-5). ``send`` wartet je
    Aufruf hoechstens die Zeitgrenze; eine wirklich stehende Leitung faellt
    so trotzdem auf.
    """
    ansicht = memoryview(daten)
    gesendet = 0
    while gesendet < len(ansicht):
        anzahl = verbindung.send(ansicht[gesendet:gesendet + SENDESTUECK])
        if anzahl <= 0:
            raise ConnectionError("Die Konsole nimmt keine Daten mehr an.")
        gesendet += anzahl


def ueber_elfldr(host: str, daten: bytes, port: int = ELFLDR_PORT,
                 timeout: float = 30.0) -> str:
    """Schiebt das Payload zu elfldr und liest zurueck, was es ausgibt.

    elfldr beginnt erst, wenn die Gegenseite die Senderichtung schliesst -
    deshalb das ``shutdown``. Was danach zurueckkommt, ist die Ausgabe des
    Payloads; ohne sie liesse sich Erfolg nicht von Fehlschlag
    unterscheiden.

    ``timeout`` gilt je Sende- und Leseschritt, nicht fuer den ganzen
    Versand.
    """
    teile: list[bytes] = []
    with socket.create_connection((host, int(port)), timeout=timeout) as verbindung:
        stueckweise_senden(verbindung, daten)
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


class Mitleser:
    """Schickt ein Payload an elfldr und liest seine Ausgabe stueckweise mit.

    :func:`ueber_elfldr` liest, bis die Leitung ``timeout`` Sekunden
    schweigt, und gibt dann alles auf einmal zurueck. Fuer ein Payload, das
    minutenlang laeuft und zwischendurch etwas meldet, taugt das nicht: Das
    PIN-Payload von ActRemoteLink wartet bis zu 300 s auf Chiaki und
    schreibt erst dann "PAIRING SUCCESS" - der Aufrufer muss zwischendurch
    nachsehen und abbrechen koennen.

    Gesendet wird sofort im Erzeuger - ein Fehler kommt also dort an, nicht
    erst beim ersten Lesen. :meth:`lesen` wartet hoechstens ``takt``
    Sekunden und liefert, was bis dahin kam (bei Stille ""). Schliesst die
    Konsole die Verbindung - das Payload hat sich beendet -, steht ``zu``.
    """

    def __init__(self, host: str, daten: bytes, port: int = ELFLDR_PORT,
                 timeout: float = 30.0, takt: float = 1.0) -> None:
        self.zu = False
        self._dekoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._buchse = socket.create_connection((host, int(port)),
                                                timeout=timeout)
        try:
            stueckweise_senden(self._buchse, daten)
            self._buchse.shutdown(socket.SHUT_WR)
            self._buchse.settimeout(takt)
        except BaseException:
            self._buchse.close()
            raise

    def lesen(self) -> str:
        """Was seit dem letzten Aufruf kam - "" bei Stille oder am Ende."""
        if self.zu:
            return ""
        try:
            stueck = self._buchse.recv(4096)
        except (socket.timeout, TimeoutError):
            return ""
        except OSError:
            stueck = b""
        if not stueck:
            self.zu = True
            return self._dekoder.decode(b"", final=True)
        return self._dekoder.decode(stueck)

    def schliessen(self) -> None:
        self.zu = True
        try:
            self._buchse.close()
        except OSError:
            pass


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


#: Die Sätze, die der Anwender zu sehen bekommt - als Vorgabe. Die
#: Oberfläche reicht über ``texte`` die übersetzte Fassung herein; dieses
#: Modul darf ``i18n`` nicht einbinden und bleibt so ohne Fenster benutzbar.
#: Dasselbe Muster wie in ``pkg_merger.MELDUNGEN``.
MELDUNGEN: dict[str, str] = {
    'nichts_erreichbar':
        'Weder elfldr (Port {elfldr}) noch der Payload Manager (Port {pldmgr}) sind erreichbar.',
}


def _satz(texte: "dict[str, str] | None", kennung: str, **werte) -> str:
    """Eine Vorlage, übersetzt wenn möglich."""
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return MELDUNGEN[kennung].format(**werte)

def senden(host: str, daten: bytes, name: str, elfldr_port: int = ELFLDR_PORT,
           pldmgr_port: int = PLDMGR_PORT,
           elfldr_pfad: str = "",
           texte: "dict[str, str] | None" = None,
           timeout: float = 30.0) -> tuple[str, str, str]:
    """Nimmt den Weg, der offensteht - elfldr zuerst.

    Drei Faelle, in dieser Reihenfolge:

    1. 9021 offen: der gewohnte Weg, mit Ausgabe des Payloads.
    2. 9021 zu, Payload Manager da und ``elfldr_pfad`` gesetzt: erst
       elfldr starten, damit 9021 aufgeht, dann wie Fall 1. Der Port
       bleibt danach offen und steht auch allen weiteren Aufrufen zur
       Verfuegung.
    3. 9021 zu, kein elfldr zur Hand: das Payload geht direkt ueber den
       Payload Manager - es laeuft, aber ohne Rueckmeldung.

    ``timeout`` geht an :func:`ueber_elfldr` - je Schritt, nicht gesamt.

    Rueckgabe: (Weg, Ausgabe, Bemerkung).
    """
    if port_offen(host, elfldr_port):
        return (WEG_ELFLDR,
                ueber_elfldr(host, daten, port=elfldr_port, timeout=timeout), "")

    if not port_offen(host, pldmgr_port):
        raise VersandFehler(_satz(texte, "nichts_erreichbar",
                                  elfldr=elfldr_port, pldmgr=pldmgr_port))

    if elfldr_pfad and os.path.isfile(elfldr_pfad):
        with open(elfldr_pfad, "rb") as fh:
            elfldr_daten = fh.read()
        if elfldr_aufwecken(host, elfldr_daten, os.path.basename(elfldr_pfad),
                            elfldr_port=elfldr_port, pldmgr_port=pldmgr_port):
            return (WEG_GEWECKT,
                    ueber_elfldr(host, daten, port=elfldr_port, timeout=timeout),
                    os.path.basename(elfldr_pfad))

    ziel = ueber_pldmgr(host, daten, name, port=pldmgr_port)
    return WEG_PLDMGR, "", ziel
