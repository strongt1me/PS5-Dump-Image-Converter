# -*- coding: utf-8 -*-
"""Streaming in beide Richtungen: Konsole suchen, Chiaki, Sunshine.

Zwei Wege, die einander nicht ersetzen, sondern ergaenzen:

============== ================= ===================== ==================
Werkzeug       Bild laeuft       Rolle der PS5         Gegenstelle
============== ================= ===================== ==================
Remote Play    PS5 -> PC         Quelle                Chiaki auf dem PC
ProsperoLight  PC -> PS5         Empfaenger            Sunshine auf dem PC
============== ================= ===================== ==================

Deshalb sucht dieses Modul beides: die **Konsole** im Netz (fuer Remote
Play) und den **Sunshine-Host** auf diesem Rechner (fuer ProsperoLight).

**Die Suche kann, was unsere Dienste-Ampel nicht kann.** Sie spricht das
Discovery-Protokoll auf UDP 9302 - dasselbe, das Chiaki verwendet - und
bekommt dadurch auch von einer Konsole im **Ruhemodus** eine Antwort
(Status 620). Ein TCP-Portscan sieht dort gar nichts, weil im Standby kein
einziges Payload laeuft.

Das Remote-Play-Protokoll selbst wird hier **nicht** nachgebaut: eigener
Transport, eigene Krypto, H.264/H.265. Dafuer gibt es Chiaki; dieses Modul
findet es und ruft es mit den richtigen Parametern auf.

Nur Standardbibliothek.

Vorlage: ``remoteplay/suche.py``, ``chiaki.py`` und ``sunshine.py`` aus den
vorbereiteten Dateien des Nutzers, hier zu einem Modul zusammengelegt und
an die Plattformschicht des Projekts angeschlossen.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

logger = logging.getLogger("PS5Converter.remoteplay")

#: Discovery der PS5 (Chiaki nutzt denselben Port und dieselbe Fassung).
PS5_SUCHPORT = 9302
PS5_PROTOKOLL = "00030010"

#: Dasselbe fuer die PS4 - kostet nichts und beantwortet die Frage
#: "ist das ueberhaupt eine PS5?", bevor jemand lange sucht.
PS4_SUCHPORT = 987
PS4_PROTOKOLL = "00020020"

#: Sunshine belegt vier Ports; gebraucht werden zwei.
SUNSHINE_HTTP = 47989   # /serverinfo, ohne Anmeldung lesbar
SUNSHINE_WEB = 47990    # Weboberflaeche, dort wird die PIN eingetragen

#: Reihenfolge = Suchreihenfolge. chiaki-ng ist der gepflegte Zweig.
_CHIAKI_NAMEN = ("chiaki-ng.exe", "chiaki-ng", "chiaki.exe", "chiaki")

_CHIAKI_ORTE_WINDOWS = (
    r"C:\Program Files\chiaki-ng",
    r"C:\Program Files\Chiaki",
    r"C:\Program Files (x86)\chiaki-ng",
    r"C:\Program Files (x86)\Chiaki",
)

_CHIAKI_ORTE_UNIX = (
    "/usr/bin", "/usr/local/bin", "/opt/chiaki-ng", "/opt/chiaki",
    "/Applications/chiaki-ng.app/Contents/MacOS",
    "/Applications/Chiaki.app/Contents/MacOS",
)

#: Platzhalter werden vor dem Start ersetzt. Die Kommandozeile
#: unterscheidet sich zwischen Chiaki, chiaki-ng und Distributionspaketen -
#: deshalb einstellbar statt fest verdrahtet.
STANDARD_ARGUMENTE = ("stream", "{nickname}", "{host}")


class ChiakiFehlt(RuntimeError):
    """Es wurde keine ausfuehrbare Chiaki-Datei gefunden."""


class NameFehlt(ValueError):
    """Chiaki braucht den Namen, unter dem die Konsole registriert ist.

    ``chiaki stream <nickname> <host>`` - beide sind Pflicht. Bis zum
    24.09.2026 fiel ein leerer Name still weg, die Adresse rutschte an seine
    Stelle, und Chiaki zeigte nur seine Hilfe (Durchsicht, U3-6).
    """


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


@dataclass(frozen=True)
class SunshineStand:
    """Antwortet auf diesem Rechner ein Sunshine-Host?"""

    laeuft: bool = False
    name: str = ""
    fassung: str = ""
    adresse: str = ""

    @property
    def weboberflaeche(self) -> str:
        """Die Adresse der Oberflaeche - leer, wenn kein Host antwortet.

        Absichtlich an ``laeuft`` gebunden: Ein Ergebnis, das gerade
        gemessen hat "da ist nichts", darf keinen Link auf eine
        Weboberflaeche anbieten. Wer die Adresse unabhaengig von einer
        Messung braucht, nimmt :func:`sunshine_web_adresse`.
        """
        if not self.laeuft:
            return ""
        return sunshine_web_adresse(self.adresse)


def sunshine_web_adresse(adresse: str = "127.0.0.1") -> str:
    """Die Weboberflaeche von Sunshine - dort wird die PIN eingetragen."""
    ziel = str(adresse or "").strip()
    if not ziel:
        return ""
    return "https://%s:%d" % (ziel, SUNSHINE_WEB)


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


def chiaki_finden(eigener_pfad: str = "") -> str:
    """Wo liegt Chiaki? Leer, wenn nichts gefunden wurde.

    Gesucht wird in dieser Reihenfolge: der eingetragene Pfad, der Suchpfad
    des Systems (``PATH``), dann die ueblichen Installationsorte.
    """
    wunsch = (eigener_pfad or "").strip().strip('"')
    if wunsch and os.path.isfile(wunsch):
        return wunsch

    for name in _CHIAKI_NAMEN:
        treffer = shutil.which(name)
        if treffer:
            return treffer

    orte = _CHIAKI_ORTE_WINDOWS if os.name == "nt" else _CHIAKI_ORTE_UNIX
    for ordner in orte:
        for name in _CHIAKI_NAMEN:
            pfad = os.path.join(ordner, name)
            if os.path.isfile(pfad):
                return pfad
    return ""


def chiaki_befehl(pfad: str, host: str, nickname: str = "",
                  argumente: "tuple[str, ...]" = STANDARD_ARGUMENTE
                  ) -> "list[str]":
    """Baut die Kommandozeile - ohne sie auszufuehren.

    Getrennt vom Starten, damit die Oberflaeche zeigen kann, was sie
    aufrufen wuerde, und damit ein Test sie pruefen kann, ohne Chiaki zu
    besitzen.

    Raises:
        NameFehlt: Die Vorlage verlangt ``{nickname}``, aber es gibt keinen.
            Weglassen verschiebt die Stellung der folgenden Angaben.
    """
    fertig = [str(pfad)]
    for teil in argumente:
        if "{nickname}" in str(teil) and not str(nickname or "").strip():
            raise NameFehlt("Chiaki braucht den Namen der Konsole.")
        text = str(teil).replace("{host}", str(host or ""))
        text = text.replace("{nickname}", str(nickname or ""))
        if not text:
            continue
        fertig.append(text)
    return fertig


def chiaki_starten(pfad: str, host: str, nickname: str = "",
                   argumente: "tuple[str, ...]" = STANDARD_ARGUMENTE):
    """Startet Chiaki und kehrt sofort zurueck.

    Raises:
        ChiakiFehlt: wenn ``pfad`` auf nichts Ausfuehrbares zeigt.
    """
    if not pfad or not os.path.isfile(pfad):
        raise ChiakiFehlt("Keine ausfuehrbare Chiaki-Datei: %r" % pfad)
    befehl = chiaki_befehl(pfad, host, nickname, argumente)
    logger.info("Starte Chiaki: %s", " ".join(befehl))
    merkmale = {}
    if os.name == "nt":
        merkmale["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0)
    return subprocess.Popen(befehl, cwd=str(Path(pfad).parent), **merkmale)


def sunshine_pruefen(adresse: str = "127.0.0.1", zeit: float = 2.0
                     ) -> SunshineStand:
    """Antwortet auf diesem Rechner ein Sunshine-Host?

    Gelesen wird ``/serverinfo`` auf Port 47989 - das geht ohne Anmeldung.
    Die Kopplung selbst wird **nicht** nachgebaut: Sie laeuft ueber die
    Weboberflaeche und verlangt deren Zugangsdaten, und die gehoeren nicht
    in ein fremdes Fenster.
    """
    ziel = (adresse or "127.0.0.1").strip()
    url = "http://%s:%d/serverinfo" % (ziel, SUNSHINE_HTTP)
    try:
        with urllib.request.urlopen(url, timeout=zeit) as antwort:
            roh = antwort.read(8192)
    except (urllib.error.URLError, OSError, ValueError) as fehler:
        logger.debug("Kein Sunshine unter %s: %s", url, fehler)
        return SunshineStand(adresse=ziel)

    name = fassung = ""
    try:
        baum = ElementTree.fromstring(roh)
        name = (baum.findtext("hostname") or "").strip()
        fassung = (baum.findtext("appversion") or "").strip()
    except ElementTree.ParseError:
        pass  # Antwort kam - das allein zaehlt schon als "laeuft".
    return SunshineStand(laeuft=True, name=name, fassung=fassung, adresse=ziel)


if __name__ == "__main__":  # pragma: no cover - Selbsttest von Hand
    import sys

    wo = sys.argv[1] if len(sys.argv) > 1 else ""
    for k in suchen(wo, zeit=3.0):
        print("%-15s %-20s Status %d  FW %s"
              % (k.adresse, k.name, k.status, k.firmware))
    print("Chiaki:", chiaki_finden() or "nicht gefunden")
    stand = sunshine_pruefen()
    print("Sunshine:", "laeuft (%s %s)" % (stand.name, stand.fassung)
          if stand.laeuft else "nicht gefunden")
