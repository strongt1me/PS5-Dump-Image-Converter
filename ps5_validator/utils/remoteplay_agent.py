# -*- coding: utf-8 -*-
"""ActRemoteLink: einen Offline-Benutzer fuer Remote Play koppeln.

Remote Play verlangt einen Benutzer, der bei PSN angemeldet ist. Wer die
Konsole offline betreibt, hat den nicht - der Agent legt die noetigen
Merkmale deshalb von Hand an: eine ``account_id``, den Typ ``np`` und die
Merker ``0x1002`` (SETID), dazu eine vorgetaeuschte Anmeldung
(FAKESIGNIN). Danach kann Chiaki sich koppeln (PIN).

**Das ist ein Schreibzugriff auf die Benutzerdaten der Konsole** - die
einzige Stelle im ganzen Programm, die so etwas tut. Darum:

* Jeder schreibende Weg geht durch :func:`schreibzugriff_pruefen`.
* Slot 1 ist gesperrt: Aenderungen am ersten Benutzer koennen dessen
  Spielstaende unbrauchbar machen. Der Weg ist, einen **neuen lokalen
  Benutzer** anzulegen (Slot 2 oder hoeher) und den zu koppeln.
* Gelesen wird immer zuerst (LIST), geschrieben nur, was noch fehlt.

**Protokoll:** Request/Response mit Half-Close - pro Kommando eine eigene
TCP-Verbindung auf Port 31337. Ein dauerhaft offener Socket ist deshalb
nicht moeglich; diese Klasse haelt Einstellungen, keine Verbindung.

**Die beiden Payloads (`actremotelink_agent*.elf`,
`actremotelink_pin_notify*.elf`) liegen diesem Programm nicht bei** und
waren am 22.09.2026 auch sonst nirgends auf dem Rechner. Ohne sie laesst
sich der Agent nicht starten; die Oberflaeche sagt das, statt es zu
versuchen. Geschickt werden sie - wenn sie da sind - ueber denselben
erprobten Weg wie jedes andere Payload (``_send_payload_to_ps5``), der
hier als ``sende_payload`` hereingereicht wird.

Nur Standardbibliothek.

Vorlage: ``remoteplay/agent.py`` aus den vorbereiteten Dateien des Nutzers.
"""
from __future__ import annotations

import logging
import re
import socket
import time
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger("PS5Converter.remoteplay.agent")

#: Der Port, auf dem der Agent horcht.
AGENT_PORT = 31337

#: Aktiviert heisst: Typ "np" und diese Merker gesetzt.
AKTIV_MERKER = 0x1002

#: Welche Schluesselarten der Agent kennt.
SCHLUESSELARTEN = ("int", "str", "bin")


class AgentFehler(RuntimeError):
    """Basis aller Fehler dieses Moduls."""


class AgentOffline(AgentFehler):
    """Der Agent laeuft nicht oder antwortet nicht."""


class AgentAbgelehnt(AgentFehler):
    """Der Agent hat das Kommando mit ERR beantwortet."""


class Slot1Gesperrt(AgentFehler):
    """Ein Schreibzugriff auf Slot 1 wuerde Spielstaende gefaehrden."""


class BenutzerFehlt(AgentFehler):
    """Der angefragte Slot ist nicht belegt."""


class BenutzerNichtVorn(AgentFehler):
    """Der Benutzer ist auf der Konsole gerade nicht der aktive.

    FAKESIGNIN wirkt nur auf den Benutzer, der auf dem Bildschirm der
    Konsole vorne ist - nicht auf einen beliebigen Slot. Das ist die
    eigentliche Bedingung des Verfahrens; die Slot-Nummer ist es nicht.
    """


@dataclass(frozen=True)
class Benutzer:
    """Ein Benutzerkonto auf der Konsole, wie LIST es meldet."""

    slot: int
    name: str = ""
    benutzer_id: str = ""
    art: str = ""
    merker: int = 0
    konto_id: str = ""
    b64: str = ""
    vordergrund: bool = False

    @property
    def aktiviert(self) -> bool:
        """Traegt dieser Benutzer schon alles, was Remote Play braucht?"""
        return self.art == "np" and bool(self.merker & AKTIV_MERKER)


@dataclass(frozen=True)
class Kopplungsstand:
    """Was der letzte Schritt getan hat - und was jetzt zu tun ist."""

    #: "setid", "signin", "pin" oder "gekoppelt". Die Oberflaeche macht
    #: daraus den Text ``remoteplay.schritt_<schritt>``.
    schritt: str
    neustart_noetig: bool = False
    benutzer: "Benutzer | None" = None

    @property
    def text_schluessel(self) -> str:
        return "remoteplay.schritt_%s" % self.schritt


def schreibzugriff_pruefen(benutzer: "Benutzer | None", slot: int) -> None:
    """Darf auf diesen Benutzer geschrieben werden?

    Dieses Gatter sitzt bewusst im Modul und nicht in der Oberflaeche: Jeder
    schreibende Weg (SETID, FAKESIGNIN) ruft es auf, auch wenn jemand die
    Methoden einzeln benutzt. Es ist die einzige Stelle, an der die
    Projektregel "nie in Systemdatenbanken schreiben" eine Ausnahme bekommt -
    und die Ausnahme ist so eng wie moeglich gehalten.

    **Slot 1 ist unbedingt gesperrt** (Entscheidung des Nutzers vom
    22.09.2026). Es gibt bewusst keinen Schalter, der das aufhebt: Ein
    Schalter, der nie umgelegt werden darf, waere nur eine Einladung. Wer
    Remote Play will, legt auf der Konsole einen neuen lokalen Benutzer an -
    der bekommt Slot 2 oder hoeher, und dessen Spielstaende sind leer,
    solange nichts damit gespielt wurde.

    Ein bereits aktivierter Benutzer wird **durchgelassen**: Der Ablauf in
    :meth:`ActRemoteLink.koppeln` laeuft nach jedem Neustart der Konsole
    erneut durch dieselben Schritte, und ein zweites SETID mit demselben
    Wert aendert nichts. Ein Verbot waere hier kein Schutz, sondern nur ein
    Abbruch mitten im Ablauf.

    Args:
        benutzer: Was LIST ueber den Slot gemeldet hat, oder ``None``, wenn
            der Slot gar nicht belegt ist.
        slot: Der angefragte Slot (1 = der erste Benutzer der Konsole).

    Raises:
        Slot1Gesperrt: Der Slot ist 1 (oder kleiner).
        BenutzerFehlt: Der Slot ist nicht belegt.
    """
    # Zuerst die harte Regel: Bei Slot 1 ist es gleichgueltig, ob er belegt
    # ist - dort wird nicht geschrieben.
    if int(slot) < 2:
        raise Slot1Gesperrt(
            "Slot %d ist gesperrt: Aenderungen am ersten Benutzer koennen "
            "dessen Spielstaende unbrauchbar machen. Lege auf der Konsole "
            "einen neuen lokalen Benutzer an (Slot 2 oder hoeher) und "
            "koppele den." % int(slot))
    if benutzer is None:
        raise BenutzerFehlt(
            "Slot %d ist nicht belegt. Erst auf der Konsole einen lokalen "
            "Benutzer anlegen, dann die Liste neu einlesen." % int(slot))


class ActRemoteLink:
    """Der Agent auf der Konsole - ein Kommando je Verbindung."""

    def __init__(self, host: str, *, agent_port: int = AGENT_PORT,
                 zeit: float = 5.0,
                 sende_payload: "Callable[[str], tuple[bool, str]] | None" = None,
                 agent_elf: str = "", pin_elf: str = "") -> None:
        self.host = str(host or "").strip()
        self.agent_port = int(agent_port)
        self.zeit = float(zeit)
        #: Bekommt den Pfad einer ELF-Datei und schickt sie zur Konsole.
        self.sende_payload = sende_payload
        self.agent_elf = agent_elf
        self.pin_elf = pin_elf

    def __repr__(self) -> str:
        return "<ActRemoteLink %s:%d>" % (self.host, self.agent_port)

    # -- Zustand ------------------------------------------------------

    def laeuft(self) -> bool:
        """Antwortet der Agent auf seinem Port?"""
        try:
            return "END" in self._befehl("HELP", zeit=2.0)
        except (OSError, AgentFehler):
            return False

    def starten(self, versuche: int = 10, pause: float = 0.5) -> bool:
        """Sorgt dafuer, dass der Agent laeuft.

        Returns:
            True, wenn er dafuer neu geschickt werden musste.

        Raises:
            AgentOffline: wenn kein Payload da ist oder er nicht hochkommt.
        """
        if self.laeuft():
            return False
        if not self.agent_elf or self.sende_payload is None:
            raise AgentOffline(
                "Der Agent laeuft nicht, und es liegt kein "
                "actremotelink_agent*.elf zum Starten bereit.")
        ok, meldung = self.sende_payload(self.agent_elf)
        if not ok:
            raise AgentOffline(meldung)
        for _ in range(int(versuche)):
            time.sleep(float(pause))
            if self.laeuft():
                return True
        raise AgentOffline(
            "Agent antwortet nicht auf %s:%d." % (self.host, self.agent_port))

    def beenden(self) -> str:
        """Beendet den Agent auf der Konsole."""
        return self._befehl("QUIT")

    # -- Lesen --------------------------------------------------------

    def benutzer_liste(self) -> "list[Benutzer]":
        """Alle Benutzer der Konsole (LIST). Reiner Lesezugriff."""
        return self._benutzer_lesen(self._befehl("LIST"))

    def benutzer(self, slot: int) -> "Benutzer | None":
        for eintrag in self.benutzer_liste():
            if eintrag.slot == int(slot):
                return eintrag
        return None

    # -- Schreiben ----------------------------------------------------

    def konto_id_setzen(self, slot: int, konto_id: "int | str") -> str:
        """Setzt account_id, type=np und flags=0x1002 (SETID).

        Schreibt in die Benutzerdaten der Konsole - geht deshalb durch
        :func:`schreibzugriff_pruefen`.
        """
        schreibzugriff_pruefen(self.benutzer(slot), int(slot))
        wert = self.konto_id_normalisieren(konto_id)
        logger.info("SETID slot=%d account_id=%s", int(slot), wert)
        return self._befehl("SETID %d %s" % (int(slot), wert))

    def fake_anmeldung(self, slot: int,
                       vordergrund_verlangen: bool = True) -> str:
        """Offline-PSN-Anmeldung (FAKESIGNIN). Danach ist ein Neustart faellig.

        Der Benutzer muss auf dem Bildschirm der Konsole **vorne** sein -
        sonst laeuft das Kommando ins Leere. Das ist die eigentliche
        Bedingung des Verfahrens (nicht die Slot-Nummer), deshalb wird sie
        hier geprueft und nicht nur in der Oberflaeche erklaert.
        """
        eintrag = self.benutzer(slot)
        schreibzugriff_pruefen(eintrag, int(slot))
        if vordergrund_verlangen and eintrag is not None \
                and not eintrag.vordergrund:
            raise BenutzerNichtVorn(
                "Slot %d (%s) ist auf der Konsole gerade nicht der aktive "
                "Benutzer. Auf der PS5 zu diesem Benutzer wechseln und "
                "erneut versuchen." % (int(slot), eintrag.name or "-"))
        logger.info("FAKESIGNIN slot=%d", int(slot))
        return self._befehl("FAKESIGNIN %d" % int(slot), zeit=15.0)

    def pin_vorbereiten(self) -> str:
        return self._befehl("PREPARE_PIN")

    def gekoppelt(self) -> bool:
        return "1" in self._befehl("IS_PAIRED").split()

    def pin_anzeigen(self) -> str:
        """Schickt das PIN-Payload; die PIN erscheint auf dem Fernseher.

        Nachgebaut wird hier nichts: Die PIN kommt als Benachrichtigung auf
        der Konsole, abgelesen wird sie vom Bildschirm und in Chiaki
        eingetippt.
        """
        if not self.pin_elf or self.sende_payload is None:
            raise AgentOffline(
                "Es liegt kein actremotelink_pin_notify*.elf bereit.")
        self.pin_vorbereiten()
        ok, meldung = self.sende_payload(self.pin_elf)
        if not ok:
            raise AgentOffline(meldung)
        return meldung

    # -- Der Ablauf ---------------------------------------------------

    def koppeln(self, slot: int,
                konto_id: "int | str | None" = None) -> "Kopplungsstand":
        """Bringt einen lokalen Benutzer Schritt fuer Schritt zur Kopplung.

        Macht **genau einen** Schritt je Aufruf, wenn danach ein Neustart
        der Konsole faellig ist, und sagt das im Ergebnis. Nach dem Neustart
        wird dieselbe Methode einfach erneut gerufen - sie sieht an der
        Benutzerliste selbst, was schon erledigt ist. Deshalb ist sie
        wiederholbar, ohne etwas doppelt zu schreiben.

        Reihenfolge: ``account_id`` setzen -> Neustart -> Fake-Anmeldung ->
        Neustart -> PIN anzeigen.
        """
        self.starten()
        eintrag = self.benutzer(slot)
        schreibzugriff_pruefen(eintrag, int(slot))

        if konto_id is not None:
            gewuenscht = self.konto_id_normalisieren(konto_id)
            if (eintrag.konto_id or "").lower() != gewuenscht.lower():
                self.konto_id_setzen(slot, konto_id)
                return Kopplungsstand("setid", True, eintrag)

        if not eintrag.aktiviert:
            self.fake_anmeldung(slot)
            return Kopplungsstand("signin", True, eintrag)

        if self.gekoppelt():
            return Kopplungsstand("gekoppelt", False, eintrag)

        self.pin_anzeigen()
        return Kopplungsstand("pin", False, eintrag)

    # -- Hilfen -------------------------------------------------------

    @staticmethod
    def konto_id_normalisieren(wert: "int | str") -> str:
        """Dezimal (wie auf playstation.com) oder Hex -> ``0x%016x``."""
        if isinstance(wert, int):
            zahl = wert
        else:
            text = str(wert).strip()
            if not text:
                raise ValueError("Keine account_id angegeben.")
            zahl = int(text, 16) if text.lower().startswith("0x") \
                else int(text, 10)
        if not 0 <= zahl < 2 ** 64:
            raise ValueError("account_id ausserhalb 64 Bit: %s" % wert)
        return "0x%016x" % zahl

    _ZEILE = re.compile(
        r'slot=(?P<slot>\d+)\s+current=(?P<current>\d+)\s+'
        r'user_id=(?P<user_id>\S+)\s+name="(?P<name>[^"]*)"\s+'
        r'type="(?P<type>[^"]*)"\s+flags=(?P<flags>0x[0-9a-fA-F]+)\s+'
        r'id=(?P<id>\S+)\s+b64=(?P<b64>\S+)')

    @classmethod
    def _benutzer_lesen(cls, text: str) -> "list[Benutzer]":
        gefunden: "list[Benutzer]" = []
        for zeile in str(text or "").splitlines():
            treffer = cls._ZEILE.search(zeile)
            if treffer is None:
                continue
            gefunden.append(Benutzer(
                slot=int(treffer.group("slot")),
                name=treffer.group("name"),
                benutzer_id=treffer.group("user_id"),
                art=treffer.group("type"),
                merker=int(treffer.group("flags"), 16),
                konto_id=treffer.group("id"),
                b64=treffer.group("b64"),
                vordergrund=treffer.group("current") == "1",
            ))
        return gefunden

    def _befehl(self, kommando: str, zeit: "float | None" = None) -> str:
        """Ein Kommando, eine Verbindung, eine Antwort."""
        if not self.host:
            raise AgentOffline("Keine PS5-Adresse angegeben.")
        grenze = float(self.zeit if zeit is None else zeit)
        try:
            with socket.create_connection((self.host, self.agent_port),
                                          timeout=grenze) as verbindung:
                verbindung.sendall((kommando.strip() + "\n").encode("utf-8"))
                # Half-Close: Der Agent antwortet erst, wenn die Senderichtung
                # zu ist.
                try:
                    verbindung.shutdown(socket.SHUT_WR)
                except OSError:
                    pass
                verbindung.settimeout(grenze)
                teile: "list[bytes]" = []
                while True:
                    try:
                        brocken = verbindung.recv(4096)
                    except socket.timeout:
                        break
                    if not brocken:
                        break
                    teile.append(brocken)
        except OSError as fehler:
            raise AgentOffline(
                "%s:%d nicht erreichbar (%s)"
                % (self.host, self.agent_port, fehler)) from fehler

        antwort = b"".join(teile).decode("utf-8", errors="replace")
        if antwort.strip().startswith("ERR"):
            raise AgentAbgelehnt(antwort.strip())
        return antwort
