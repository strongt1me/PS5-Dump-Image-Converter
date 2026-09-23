# -*- coding: utf-8 -*-
"""Welche Dienste laufen gerade auf der Konsole?

Die haeufigste Ursache, wenn etwas mit der PS5 nicht klappt, ist banal: Das
Payload laeuft nicht. Statt das an jeder Stelle einzeln zu merken, fragt
dieses Modul alle bekannten Ports auf einmal ab und liefert eine Ampel.

Geprueft wird mit einem TCP-Verbindungsversuch. Das ist absichtlich stumpf -
wer die Verbindung annimmt, laeuft; was er danach spricht, interessiert hier
nicht. Ein Dienst kann also "laeuft" melden und trotzdem streiken; die
Gegenprobe ist immer der eigentliche Aufruf.

**Zum Port des ELF-Loaders:** Die Quellen sind sich nicht einig - das README
von elfldr 0.26 nennt 9020, ps5upload und ActRemoteLink senden an 9021, und
an der Konsole des Nutzers ist 9021 der arbeitende Port (payload_versand).
Beide stehen im Katalog; welcher antwortet, sagt die Abfrage.

Das Modul bindet ``i18n`` nicht ein: Es traegt nur Schluessel, die
Oberflaeche uebersetzt sie (wie ``prosperopkg.MELDUNGEN``).

Vorlage: ``konsole/dienste.py`` aus den vorbereiteten Dateien des Nutzers
(nur Standardbibliothek). Hier angepasst: Textschluessel statt fester
Beschriftungen, der Payload-Manager (8084) dazu - ueber ihn laeuft der
zweite Sendeweg -, und die Muster der mitgelieferten ELF-Dateien.
"""
from __future__ import annotations

import socket
import threading
from dataclasses import dataclass, field

#: Wie lange auf eine Verbindung gewartet wird. Im LAN antwortet ein
#: laufender Dienst weit darunter; ist nichts da, kommt die Ablehnung
#: sofort. Der Wert greift nur bei stillen Paketverlusten.
ZEITSCHRANKE = 0.6


@dataclass(frozen=True)
class Dienst:
    """Ein Dienst auf der Konsole - Port, Textschluessel, Startdatei."""

    schluessel: str
    port: int
    #: Muster der mitgelieferten ELF-Datei (helloworld/), "" = keine.
    payload_muster: str = ""
    #: Pfad der Weboberflaeche, oder "" fuer keine.
    web: str = ""
    #: Nur einer aus dieser Gruppe muss laufen (die beiden Loader-Ports).
    gruppe: str = ""
    #: Sekunden, die dieser Dienst nach dem Start zum Hochkommen braucht.
    anlaufzeit: float = 1.5
    #: Dieser Dienst begruesst von sich aus (FTP: "220 ..."). Dann wird der
    #: Gruss mitgelesen - ein offener Port allein taeuscht hier.
    begruessung: bool = False

    @property
    def name_schluessel(self) -> str:
        return "dienst.%s" % self.schluessel

    @property
    def zweck_schluessel(self) -> str:
        return "dienst.%s_zweck" % self.schluessel


#: Reihenfolge = Anzeigereihenfolge. Oben steht, was ohne alles andere nicht
#: geht: ohne ELF-Loader laesst sich nichts nachladen.
KATALOG: tuple[Dienst, ...] = (
    Dienst("elfldr9021", 9021, "elfldr*.elf", gruppe="elfldr", anlaufzeit=2.5),
    Dienst("elfldr9020", 9020, "", gruppe="elfldr"),
    Dienst("pldmgr", 8084, "pldmgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("ftpsrv", 2121, "ftpsrv-ps5*.elf", begruessung=True),
    Dienst("klogsrv", 3232, "klogsrv*.elf", anlaufzeit=1.0),
    # Der PKG Manager haelt zwei weitere Ports offen: 18841 (Paketstrom) und
    # 18842 (Direct Install). Beide gehoeren zum selben Payload und kommen mit
    # ihm hoch - geprueft wird deshalb nur die Weboberflaeche auf 8844.
    Dienst("pkgmgr", 8844, "pkgmgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("webfm", 8888, "web-file-mgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("garlic", 8082, "garlic-savemgr*.elf", web="/", anlaufzeit=2.0),
    Dienst("bfpilot", 5905, "bfpilot*.elf", web="/"),
    Dienst("websrv", 8080, "websrv-ps5*.elf", web="/"),
    Dienst("upload", 9113, "ps5upload*.elf"),
)

#: Die Grundausstattung, in dieser Reihenfolge: Ohne Loader geht nichts,
#: danach die beiden Dienste, die fast jeder Weg braucht.
GRUNDAUSSTATTUNG: tuple[str, ...] = ("elfldr9021", "ftpsrv", "klogsrv")

_NACH_SCHLUESSEL = {d.schluessel: d for d in KATALOG}


@dataclass
class Stand:
    dienst: Dienst
    laeuft: bool = False
    #: Port offen, aber kein Gruss - der Dienst haengt. Am 17.08.2026 an der
    #: Konsole erlebt: ftpsrv nahm Verbindungen weiter an und antwortete
    #: nicht mehr; ein neu geladenes Payload half nicht, nur ein Neustart der
    #: Konsole. Ein reiner Portscan meldet hier faelschlich "laeuft".
    stumm: bool = False


@dataclass
class Uebersicht:
    adresse: str
    staende: list[Stand] = field(default_factory=list)

    def __iter__(self):
        return iter(self.staende)

    def __len__(self) -> int:
        return len(self.staende)

    def laeuft(self, schluessel: str) -> bool:
        return any(s.laeuft for s in self.staende
                   if s.dienst.schluessel == schluessel)

    def gruppe_laeuft(self, gruppe: str) -> bool:
        """Laeuft mindestens einer aus dieser Gruppe?"""
        return any(s.laeuft for s in self.staende if s.dienst.gruppe == gruppe)

    @property
    def loader_port(self) -> "int | None":
        """Der Port, auf dem der ELF-Loader tatsaechlich antwortet."""
        for stand in self.staende:
            if stand.dienst.gruppe == "elfldr" and stand.laeuft:
                return stand.dienst.port
        return None

    @property
    def anzahl_laufend(self) -> int:
        return sum(1 for s in self.staende if s.laeuft)

    @property
    def bereit(self) -> bool:
        """Ist die Konsole ansprechbar?

        Das entscheidet der ELF-Loader oder der Payload-Manager: Ueber einen
        von beiden laesst sich alles Weitere nachladen (siehe
        ``payload_versand``).
        """
        return self.gruppe_laeuft("elfldr") or self.laeuft("pldmgr")


def dienst(schluessel: str) -> "Dienst | None":
    return _NACH_SCHLUESSEL.get(schluessel)


def port_offen(adresse: str, port: int, zeit: float = ZEITSCHRANKE) -> bool:
    """Nimmt an diesem Port jemand Verbindungen an?"""
    try:
        with socket.create_connection((adresse, int(port)), timeout=zeit):
            return True
    except OSError:
        return False


def dienst_pruefen(adresse: str, eintrag: Dienst,
                   zeit: float = ZEITSCHRANKE) -> "tuple[bool, bool]":
    """Prueft einen Dienst.

    Returns:
        ``(laeuft, stumm)``. ``stumm`` ist True, wenn der Port zwar offen
        ist, ein erwarteter Gruss aber ausbleibt - dann haengt der Dienst
        (siehe :class:`Stand`), und ``laeuft`` ist False.
    """
    try:
        with socket.create_connection((adresse, int(eintrag.port)),
                                      timeout=zeit) as verbindung:
            if not eintrag.begruessung:
                return (True, False)
            verbindung.settimeout(zeit)
            try:
                gruss = verbindung.recv(64)
            except OSError:
                gruss = b""
            if gruss:
                return (True, False)
            return (False, True)
    except OSError:
        return (False, False)


def pruefen(adresse: str, zeit: float = ZEITSCHRANKE,
            dienste: "tuple[Dienst, ...]" = KATALOG) -> Uebersicht:
    """Fragt alle Dienste gleichzeitig ab.

    Nacheinander gefragt kostete das bei zehn Diensten und einer stillen
    Konsole das Zehnfache der Zeitschranke - nebenlaeufig kostet es einmal
    die Zeitschranke.
    """
    ziel = (adresse or "").strip()
    if not ziel:
        return Uebersicht(adresse="", staende=[Stand(d) for d in dienste])

    ergebnisse: "dict[str, tuple[bool, bool]]" = {}
    sperre = threading.Lock()

    def fragen(eintrag: Dienst) -> None:
        stand = dienst_pruefen(ziel, eintrag, zeit)
        with sperre:
            ergebnisse[eintrag.schluessel] = stand

    faeden = [threading.Thread(target=fragen, args=(d,), daemon=True)
              for d in dienste]
    for faden in faeden:
        faden.start()
    # Etwas Luft ueber der Zeitschranke, damit ein knapp verspaeteter Faden
    # noch zaehlt statt als "aus" zu gelten.
    for faden in faeden:
        faden.join(timeout=zeit + 1.0)

    return Uebersicht(
        adresse=ziel,
        staende=[Stand(d, *ergebnisse.get(d.schluessel, (False, False)))
                 for d in dienste],
    )


def web_adresse(eintrag: Dienst, adresse: str) -> str:
    """Die Adresse der Weboberflaeche - leer, wenn der Dienst keine hat."""
    if not eintrag.web or not str(adresse or "").strip():
        return ""
    return "http://%s:%d%s" % (str(adresse).strip(), eintrag.port, eintrag.web)
