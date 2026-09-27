# -*- coding: utf-8 -*-
"""Ein Spiel auf der PS5 starten - ueber websrv.

Wunsch des Nutzers vom 27.09.2026: "einen Knopf, damit man von der Bibliothek
aus die Spiele starten kann auf der PS5".

Keiner der Dienste, die das Programm sonst anspricht, kann das: ShadowMount+
1.7beta2 hat 23 API-Pfade, aber keinen zum Starten (es haengt sich nur in den
Start der Konsole ein), der Payload Manager startet nur Payloads und den
Browser. **websrv** (ps5-payload-dev, John Toernblom, GPLv3; liegt als
``helloworld/websrv-ps5_v*.elf`` bei, Port 8080) nimmt dagegen

    GET /launch?titleId=<TITLE_ID>

entgegen und ruft auf der Konsole ``sceSystemServiceLaunchApp`` auf. Am
Quelltext nachgelesen (``src/websrv.c`` ``launch_request``, ``src/ps5/sys.c``
``sys_launch_title``, in den Tags v0.20 bis v0.34 unveraendert):

* **Vorher beendet websrv ein laufendes Spiel** (``sceSystemServiceKillApp``)
  - wer startet, muss das wissen; die Bibliothek fragt deshalb vorher.
* Antwort 200: gestartet. 503: die Konsole hat abgelehnt (Titel nicht
  installiert bzw. nicht registriert). 400: keine Kennung.
* Einen Pfad, den er nicht kennt, beantwortet er aus seiner
  Dateiauslieferung - ein Webserver ohne ``/launch`` antwortet also 404.

Ueber ``http.client`` statt ``urllib``: ``urllib`` nimmt eingestellte
Proxys, und ein Proxy kann die Konsole im eigenen Netz nicht erreichen.
"""
from __future__ import annotations

import http.client
import re
import socket
import urllib.parse

from .logger import get_logger

log = get_logger(__name__)

#: Der Port von websrv (siehe ``konsole_dienste``).
PORT = 8080

#: Die Ergebnisse von :func:`titel_starten`.
GESTARTET = "gestartet"
ABGELEHNT = "abgelehnt"
UNBEKANNTER_PFAD = "unbekannter_pfad"
NICHT_ERREICHBAR = "nicht_erreichbar"
FEHLER = "fehler"

#: So sieht eine Title-ID aus - PS5 (PPSA) wie PS4 (CUSA) und Homebrew.
KENNUNG = re.compile(r"[A-Z]{4}\d{5}")


def startpfad(kennung: str) -> str:
    """Der Anfragepfad fuer websrv, mit sauber kodierter Kennung."""
    return "/launch?" + urllib.parse.urlencode({"titleId": kennung})


def titel_starten(adresse: str, kennung: str, *, port: int = PORT,
                  zeit: float = 15.0) -> tuple[str, str]:
    """Bittet websrv auf der Konsole, den Titel ``kennung`` zu starten.

    Laeuft im Arbeitsfaden - die Konsole antwortet erst, wenn ein laufendes
    Spiel beendet und das neue angestossen ist.

    Returns:
        ``(ergebnis, einzelheit)`` - ``ergebnis`` ist eine der Konstanten
        dieses Moduls, ``einzelheit`` ein Text fuer Protokoll und Meldung.
    """
    kennung = str(kennung or "").strip().upper()
    if not KENNUNG.fullmatch(kennung):
        return FEHLER, "keine gueltige Title-ID: %r" % kennung
    if not str(adresse or "").strip():
        return FEHLER, "keine Adresse"
    verbindung = http.client.HTTPConnection(adresse, port, timeout=zeit)
    try:
        verbindung.request("GET", startpfad(kennung),
                           headers={"Connection": "close"})
        antwort = verbindung.getresponse()
        status = antwort.status
        antwort.read()
    except (ConnectionError, socket.timeout, OSError) as exc:
        log.debug("Titelstart: websrv %s:%d nicht erreichbar (%s)", adresse, port, exc)
        return NICHT_ERREICHBAR, str(exc)
    except http.client.HTTPException as exc:
        log.debug("Titelstart: Antwort unlesbar (%s)", exc)
        return FEHLER, str(exc)
    finally:
        verbindung.close()
    log.info("Titelstart %s auf %s: HTTP %d", kennung, adresse, status)
    if status == 200:
        return GESTARTET, ""
    if status == 503:
        return ABGELEHNT, "HTTP 503"
    if status == 404:
        return UNBEKANNTER_PFAD, "HTTP 404"
    return FEHLER, "HTTP %d" % status
