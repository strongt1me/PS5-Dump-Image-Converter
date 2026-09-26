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

Seit dem 26.09.2026 (Wunsch des Nutzers) kommt elfldr dafuer per FTP in
den Ordner, in dem der Payload Manager selbst seine Payloads ablegt
(``/data/pldmgr/payloads/elfldr/``, samt Begleitdatei ``.json``) - und
nur, wenn es dort noch fehlt. Danach genuegt ``/loadpayload:``. Laeuft
kein ftpsrv, geht elfldr wie zuvor ueber die Weboberflaeche hinauf.
"""
from __future__ import annotations

import ftplib
import io
import json
import logging
import os
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime

from ps5_validator.utils import konsole_ftp

logger = logging.getLogger(__name__)

#: Wo elfldr lauscht (prospero-deploy aus dem SDK nutzt denselben Port).
ELFLDR_PORT = 9021

#: Weboberflaeche des Payload Managers.
PLDMGR_PORT = 8084

#: Wohin der Payload Manager hochgeladene Payloads legt.
PLDMGR_ABLAGE = "/data/pldmgr/payloads"

#: Sein Unterordner fuer elfldr - so legt er ihn selbst an, abgelesen auf
#: der Konsole des Nutzers (26.09.2026): ``elfldr/elfldr-ps5_v0.26.elf``
#: und daneben ``elfldr-ps5_v0.26.elf.json``.
ELFLDR_ORDNER = "elfldr"

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

#: Wie elfldr in den Ordner des Payload Managers kam (:func:`elfldr_laden`).
ABLAGE_VORHANDEN = "vorhanden"  # lag schon da - nichts hochgeladen
ABLAGE_FTP = "ftp"              # per FTP hochgeladen
ABLAGE_WEB = "web"              # kein FTP - ueber die Weboberflaeche


class VersandFehler(Exception):
    """Fehler, der dem Anwender wortwoertlich gezeigt werden kann."""


class AblageBelegt(VersandFehler):
    """Unter dem Namen von elfldr liegt eine andere Datei - sie bleibt, wie sie ist."""


@dataclass(frozen=True)
class ElfldrAblage:
    """Wo elfldr auf der Konsole liegt und wie es dorthin kam."""

    pfad: str
    art: str
    #: Warum es nicht per FTP ging (nur bei ``ABLAGE_WEB``) - fuers Protokoll.
    grund: str = ""


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


def elfldr_begleitdatei(name: str, zeitpunkt: "datetime | None" = None) -> bytes:
    """Die Begleitdatei ``<name>.json``, wie der Payload Manager sie anlegt.

    Felder und Form abgelesen an der Datei, die er auf der Konsole des
    Nutzers selbst angelegt hat (26.09.2026). ``install_source`` bleibt
    ``web_upload``: der einzige Wert, der dort beobachtet ist - einen
    unbekannten koennte seine Liste anders behandeln.
    """
    zeit = (zeitpunkt or datetime.now().astimezone()).strftime("%Y-%m-%dT%H:%M:%S%z")
    angaben = {
        "name": name, "filename": name, "url": "", "source": "",
        "source_direct": "", "description": "", "last_update": "",
        "version": "", "checksum": "", "category": "", "downloaded_at": zeit,
        "install_source": "web_upload", "install_source_detail": "",
        "source_name": "",
    }
    return (json.dumps(angaben, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def elfldr_ablegen(host: str, elfldr_daten: bytes, name: str = ELFLDR_NAME,
                   ftp_port: int = konsole_ftp.FTP_PORT,
                   texte: "dict[str, str] | None" = None) -> ElfldrAblage:
    """Legt elfldr per FTP in den Ordner des Payload Managers - nur wenn es fehlt.

    Wunsch des Nutzers vom 26.09.2026: Ist Port 9021 zu, soll der Ordner
    ``elfldr`` - "falls noch nicht vorhanden auf der PS5" - per FTP nach
    ``/data/pldmgr/payloads`` und die .elf dann ueber den Payload Manager
    geladen werden. Bis dahin ging elfldr bei jedem Wecken erneut ueber
    dessen Weboberflaeche hinauf.

    * Liegt die Datei in derselben Groesse schon da, wird nichts
      hochgeladen; fehlt nur die Begleitdatei, kommt sie nach.
    * Hochgeladen wird mit :func:`konsole_ftp.datei_ablegen` - erst unter
      ``.tmp``, dann umbenannt. Ein Abriss hinterlaesst nie eine halbe
      elfldr, die der Payload Manager spaeter laden wuerde.
    * Eine *andere* Datei gleichen Namens bleibt unangetastet
      (:class:`AblageBelegt`): Sie zu ersetzen hiesse, auf der Konsole
      etwas zu loeschen - sie zu laden, etwas Unbekanntes zu starten.

    Raises:
        konsole_ftp.FtpFehler: kein ftpsrv oder ein FTP-Fehler.
        AblageBelegt: siehe oben.
    """
    ordner = "%s/%s" % (PLDMGR_ABLAGE, ELFLDR_ORDNER)
    ziel = "%s/%s" % (ordner, name)
    verbindung = konsole_ftp.verbinden(host, ftp_port)
    try:
        try:
            verbindung.cwd(ordner)
        except ftplib.error_perm:
            eintraege: "dict[str, konsole_ftp.Eintrag]" = {}
        except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
            raise konsole_ftp.FtpFehler(
                "%s nicht lesbar: %s" % (ordner, fehler)) from fehler
        else:
            eintraege = {e.name: e for e in konsole_ftp.auflisten(verbindung, ordner)}

        vorhanden = eintraege.get(name)
        if vorhanden is None:
            konsole_ftp.ordner_anlegen(verbindung, ordner)
            konsole_ftp.datei_ablegen(verbindung, io.BytesIO(elfldr_daten), ziel)
        else:
            groesse = vorhanden.groesse
            if not vorhanden.ordner and groesse != len(elfldr_daten):
                # Eine Auflistung ohne Groessenangabe liefert 0 - SIZE fragt nach.
                try:
                    groesse = int(verbindung.size(ziel) or 0)
                except Exception:  # noqa: BLE001 - dann bleibt die Angabe
                    pass
            if vorhanden.ordner or groesse != len(elfldr_daten):
                raise AblageBelegt(_satz(texte, "elfldr_belegt", pfad=ziel,
                                         ist=groesse, soll=len(elfldr_daten)))

        if name + ".json" not in eintraege:
            try:
                konsole_ftp.datei_ablegen(
                    verbindung, io.BytesIO(elfldr_begleitdatei(name)), ziel + ".json")
            except konsole_ftp.FtpFehler as fehler:
                # Sie dient nur der Liste des Payload Managers - geladen wird die .elf.
                logger.warning("%s.json nicht abgelegt: %s", ziel, fehler)
        return ElfldrAblage(ziel, ABLAGE_FTP if vorhanden is None else ABLAGE_VORHANDEN)
    finally:
        konsole_ftp.schliessen(verbindung)


def elfldr_laden(host: str, elfldr_daten: bytes, name: str = ELFLDR_NAME,
                 pldmgr_port: int = PLDMGR_PORT,
                 ftp_port: int = konsole_ftp.FTP_PORT,
                 texte: "dict[str, str] | None" = None) -> ElfldrAblage:
    """Startet elfldr ueber den Payload Manager - aus dessen eigenem Ordner.

    Erst :func:`elfldr_ablegen` (per FTP, nur wenn es fehlt), dann
    ``/loadpayload:``. Laeuft kein ftpsrv, geht elfldr wie bis zum
    26.09.2026 ueber die Weboberflaeche hinauf (:func:`ueber_pldmgr`).
    Auf Port 9021 wartet erst :func:`elfldr_aufwecken`.

    Raises:
        AblageBelegt: eine andere Datei unter dem Namen - nichts geladen.
    """
    try:
        ablage = elfldr_ablegen(host, elfldr_daten, name, ftp_port=ftp_port,
                                texte=texte)
    except konsole_ftp.FtpFehler as fehler:
        logger.info("elfldr nicht per FTP abgelegt (%s) - Weboberflaeche", fehler)
        return ElfldrAblage(ueber_pldmgr(host, elfldr_daten, name, port=pldmgr_port),
                            ABLAGE_WEB, str(fehler))
    _pldmgr_ruf(host, "/loadpayload:" + urllib.parse.quote(ablage.pfad),
                port=pldmgr_port)
    return ablage


def elfldr_aufwecken(host: str, elfldr_daten: bytes, name: str = ELFLDR_NAME,
                     elfldr_port: int = ELFLDR_PORT,
                     pldmgr_port: int = PLDMGR_PORT,
                     warten: float = ELFLDR_WARTEN,
                     ftp_port: int = konsole_ftp.FTP_PORT,
                     texte: "dict[str, str] | None" = None) -> bool:
    """Startet elfldr ueber den Payload Manager und wartet auf den Port.

    Das ist der bessere Ausweg, wenn 9021 zu ist: Statt jedes einzelne
    Payload ueber den Payload Manager zu schicken - der die Ausgabe
    verwirft - wird dort **einmal** elfldr gestartet. Danach steht der
    gewohnte Weg offen, mit Rueckmeldung.

    Am 29.08.2026 auf einer echten Konsole gemessen: Port 9021 ging nach
    dem Start binnen weniger Sekunden auf. Seit dem 26.09.2026 ueber
    :func:`elfldr_laden` (erst FTP, dann Weboberflaeche); der Port wird alle
    0,5 s gefragt statt alle 2 s.
    """
    elfldr_laden(host, elfldr_daten, name, pldmgr_port=pldmgr_port,
                 ftp_port=ftp_port, texte=texte)
    ende = time.monotonic() + warten
    while time.monotonic() < ende:
        if port_offen(host, elfldr_port):
            return True
        time.sleep(0.5)
    return False


#: Die Sätze, die der Anwender zu sehen bekommt - als Vorgabe. Die
#: Oberfläche reicht über ``texte`` die übersetzte Fassung herein; dieses
#: Modul darf ``i18n`` nicht einbinden und bleibt so ohne Fenster benutzbar.
#: Dasselbe Muster wie in ``pkg_merger.MELDUNGEN``.
MELDUNGEN: dict[str, str] = {
    'nichts_erreichbar':
        'Weder elfldr (Port {elfldr}) noch der Payload Manager (Port {pldmgr}) sind erreichbar.',
    'elfldr_belegt':
        'Unter {pfad} liegt schon eine andere Datei ({ist} statt {soll} Bytes). '
        'Sie bleibt unangetastet – elfldr wurde nicht geladen.',
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
       elfldr starten (:func:`elfldr_aufwecken`), damit 9021 aufgeht, dann
       wie Fall 1 - es sei denn, das Payload *ist* elfldr. Der Port
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
                            elfldr_port=elfldr_port, pldmgr_port=pldmgr_port,
                            texte=texte):
            if daten == elfldr_daten:
                # Das Payload war elfldr selbst - und das laeuft jetzt. Es
                # noch einmal an 9021 zu schicken, startete es ein zweites Mal.
                return WEG_GEWECKT, "", os.path.basename(elfldr_pfad)
            return (WEG_GEWECKT,
                    ueber_elfldr(host, daten, port=elfldr_port, timeout=timeout),
                    os.path.basename(elfldr_pfad))

    ziel = ueber_pldmgr(host, daten, name, port=pldmgr_port)
    return WEG_PLDMGR, "", ziel
