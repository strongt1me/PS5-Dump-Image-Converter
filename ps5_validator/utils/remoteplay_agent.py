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

**Die beiden Payloads** (``actremotelink_agent*.elf``,
``actremotelink_pin_notify*.elf``, Fassung 2.0, GPL-3.0-or-later) liegen
seit dem 23.09.2026 in ``helloworld``. Fehlen sie dort, nennt die
Oberflaeche :data:`DOWNLOAD_ADRESSE` - heruntergeladen wird nichts von
selbst. Geschickt werden sie ueber denselben erprobten Weg wie jedes andere
Payload (``_send_payload_to_ps5``), der hier als ``sende_payload``
hereingereicht wird.

**Die Reihenfolge ist nicht frei** (actremotelink_agent.c 2.0): FAKESIGNIN
verweigert einen Benutzer ohne account_id, und das PIN-Payload nimmt den
Benutzer, der auf der Konsole vorne ist. Den ganzen Ablauf fuehrt
:class:`Kopplungsassistent` aus - so weit es geht, allein.

Nur Standardbibliothek.

Vorlage: ``remoteplay/agent.py`` aus den vorbereiteten Dateien des Nutzers.
"""
from __future__ import annotations

import logging
import re
import secrets
import socket
import time
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger("PS5Converter.remoteplay.agent")

#: Der Port, auf dem der Agent horcht.
AGENT_PORT = 31337

#: Das Projekt und sein Release 2.0 - daher stammen die beiden Payloads in
#: ``helloworld``. Fehlen sie, nennt die Oberflaeche diese Adresse und
#: oeffnet sie auf Klick im Browser (Wunsch des Nutzers, 24.09.2026).
PROJEKT_ADRESSE = "https://github.com/francoataffarel/ActRemoteLink"
DOWNLOAD_ADRESSE = PROJEKT_ADRESSE + "/releases/download/v2.0/ActRemoteLink.zip"

#: Woran die beiden Payloads in ``helloworld`` zu erkennen sind.
PAYLOAD_MUSTER: "dict[str, str]" = {
    "agent": "actremotelink_agent*.elf",
    "pin": "actremotelink_pin_notify*.elf",
}

#: Aktiviert heisst: Typ "np" und diese Merker gesetzt.
AKTIV_MERKER = 0x1002

#: Welche Schluesselarten der Agent kennt.
SCHLUESSELARTEN = ("int", "str", "bin")


class AgentFehler(RuntimeError):
    """Basis aller Fehler dieses Moduls."""


class AgentOffline(AgentFehler):
    """Der Agent laeuft nicht oder antwortet nicht."""


class PayloadFehlt(AgentOffline):
    """Eines der beiden Payloads liegt nicht in ``helloworld``.

    ``art`` ist "agent" oder "pin" (Schluessel von :data:`PAYLOAD_MUSTER`).
    """

    def __init__(self, art: str) -> None:
        self.art = art
        self.muster = PAYLOAD_MUSTER.get(art, art)
        super().__init__("Es liegt kein %s bereit (Download: %s)."
                         % (self.muster, DOWNLOAD_ADRESSE))


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
    #: Die ``signin``-Angabe aus LIST - FAKESIGNIN schreibt sie. ``None``
    #: heisst: Der Agent meldet das Feld gar nicht (dann bleibt nur
    #: :attr:`aktiviert` als Anhaltspunkt), ``""``: noch nicht angemeldet.
    anmeldung: "str | None" = None

    @property
    def aktiviert(self) -> bool:
        """Traegt dieser Benutzer schon alles, was Remote Play braucht?"""
        return self.art == "np" and bool(self.merker & AKTIV_MERKER)


def _ist_null(konto_id: str) -> bool:
    """Steht dort keine account_id? (LIST schreibt ``0x0000000000000000``.)"""
    try:
        return int(str(konto_id or "").strip() or "0", 16) == 0
    except ValueError:
        return True


def setid_noetig(eintrag: "Benutzer", gewuenscht: "str | None" = None
                 ) -> "tuple[bool, str | None]":
    """Braucht dieser Benutzer SETID - und mit welchem Wert?

    Args:
        eintrag: Was LIST ueber ihn meldet.
        gewuenscht: Die account_id, die der Anwender angegeben hat
            (``0x%016x``), oder ``None``.

    Returns:
        ``(noetig, wert)``. ``wert`` ist ``None``, wenn SETID noetig ist,
        aber niemand eine account_id angegeben hat - dann erzeugt der
        Aufrufer eine (:func:`neue_konto_id`).

    Ohne account_id bricht FAKESIGNIN ab (``user_not_activated_aborting``,
    actremotelink_agent.c 2.0). Bis zum 24.09.2026 ging ``koppeln`` ohne
    angegebene ID trotzdem gleich zur Anmeldung - an einem frischen Benutzer
    scheiterte das an der Konsole. Steht schon eine ID da, der Typ oder die
    Merker aber fehlen, setzt SETID dieselbe ID noch einmal: Es schreibt Typ
    ``np`` und die Merker ``0x1002`` mit.
    """
    ist = str(eintrag.konto_id or "").strip().lower()
    if gewuenscht is not None and ist != gewuenscht.lower():
        return True, gewuenscht
    if _ist_null(ist):
        return True, gewuenscht
    if not eintrag.aktiviert:
        return True, ist
    return False, None


def anmeldung_noetig(eintrag: "Benutzer") -> bool:
    """Fehlt diesem Benutzer noch die Offline-Anmeldung (FAKESIGNIN)?

    SETID setzt Typ "np" und die Merker 0x1002 schon selbst - nach dem
    ersten Neustart galt der Benutzer damit als "aktiviert", und die
    Fake-Anmeldung fiel bis zum 24.09.2026 still aus: Es ging gleich zur
    PIN, die Kopplung scheiterte (Durchsicht, U3-4). Ob FAKESIGNIN gelaufen
    ist, zeigt erst dessen ``signin``-Angabe in LIST. Aeltere Agenten melden
    sie nicht (``None``) - die kennen FAKESIGNIN aber auch nicht; dann zaehlt
    allein :attr:`Benutzer.aktiviert`.
    """
    return not eintrag.aktiviert or eintrag.anmeldung == ""


def neue_konto_id() -> str:
    """Eine zufaellige account_id fuer einen Offline-Benutzer (``0x%016x``).

    Remote Play prueft nur, ob Chiaki dieselbe ID nennt, die auf der Konsole
    steht (sonst Fehler 0x80FC1040, actremotelink_pin_notify.c). Fuer einen
    Benutzer, der nie online geht, ist gleich, welche es ist. Wer seine
    echte PSN-ID nehmen will, traegt sie ins Feld ein - dann gilt die.
    """
    while True:
        zahl = secrets.randbits(64)
        if zahl:
            return "0x%016x" % zahl


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

    Ein bereits aktivierter Benutzer wird **durchgelassen**: Der
    :class:`Kopplungsassistent` laeuft nach jedem Neustart der Konsole
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
            PayloadFehlt: ``actremotelink_agent*.elf`` liegt nicht bereit.
            AgentOffline: er kommt nicht hoch.
        """
        if self.laeuft():
            return False
        if not self.agent_elf:
            raise PayloadFehlt("agent")
        if self.sende_payload is None:
            raise AgentOffline("Kein Weg angegeben, das Payload zu schicken.")
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
        """PREPARE_PIN: schaltet Remote Play ein, nennt die Konto-ID (Base64).

        Wirkt auf den Benutzer, der auf der Konsole vorne ist - wie das
        PIN-Payload danach auch.
        """
        return self._befehl("PREPARE_PIN")

    #: Eine Geraetezeile der Antwort auf ``PAIRED``. Der Agent listet drei
    #: Tabellen der Konsole (``DEVICE``, ``DEVICE2``, ``DEVICE3``), je Zeile
    #: ein gekoppeltes Remote-Play-Geraet samt Benutzer-ID als
    #: ``user_id=<dezimal>/<hex>`` (actremotelink_agent.c, ``cmd_paired``).
    _GERAET = re.compile(r"^DEVICE\d*\s.*?\buser_id=(?P<dez>-?\d+)/",
                         re.MULTILINE)

    def gekoppelte_benutzer(self) -> "set[int]":
        """Die Benutzer-IDs, fuer die ein Remote-Play-Geraet gekoppelt ist.

        Bis zum 24.09.2026 fragte das Programm hier ``IS_PAIRED``. Das kennt
        der mitgelieferte Agent 2.0 nicht - er antwortet ``ERR
        unknown_command``, und ``koppeln`` brach nach der Fake-Anmeldung mit
        ``AgentAbgelehnt`` ab, statt die PIN anzuzeigen (Durchsicht, U3-3).
        Sein Befehl dafuer heisst ``PAIRED``.
        """
        antwort = self._befehl("PAIRED")
        return {int(treffer.group("dez")) & 0xFFFFFFFF
                for treffer in self._GERAET.finditer(antwort)}

    def gekoppelt(self, slot: "int | None" = None) -> bool:
        """Ist ein Remote-Play-Geraet gekoppelt - fuer diesen Slot oder ueberhaupt?

        Verglichen wird die Benutzer-ID aus ``LIST`` (dort dezimal) mit denen
        der Geraetezeilen, auf 32 Bit - beide schreibt der Agent als ``%d``.
        """
        gekoppelt = self.gekoppelte_benutzer()
        if slot is None:
            return bool(gekoppelt)
        eintrag = self.benutzer(slot)
        if eintrag is None:
            return False
        try:
            kennung = int(str(eintrag.benutzer_id).strip(), 0) & 0xFFFFFFFF
        except ValueError:
            return False
        return kennung in gekoppelt

    def pin_senden(self) -> str:
        """Schickt das PIN-Payload, ohne seine Ausgabe mitzulesen.

        Der Weg, wenn elfldr nicht erreichbar ist (Payload Manager): Die PIN
        steht dann nur in der Benachrichtigung auf der Konsole. Mit elfldr
        liest der Assistent die Ausgabe selbst (``pin_mitlesen``).
        """
        if not self.pin_elf:
            raise PayloadFehlt("pin")
        if self.sende_payload is None:
            raise AgentOffline("Kein Weg angegeben, das Payload zu schicken.")
        ok, meldung = self.sende_payload(self.pin_elf)
        if not ok:
            raise AgentOffline(meldung)
        return meldung

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

    #: Agent 2.0 haengt ``signin="..."`` an (actremotelink_agent.c,
    #: ``cmd_list``); aeltere Fassungen nicht - deshalb getrennt und
    #: freiwillig gelesen.
    _ANMELDUNG = re.compile(r'\bsignin="(?P<signin>[^"]*)"')

    @classmethod
    def _benutzer_lesen(cls, text: str) -> "list[Benutzer]":
        gefunden: "list[Benutzer]" = []
        for zeile in str(text or "").splitlines():
            treffer = cls._ZEILE.search(zeile)
            if treffer is None:
                continue
            anmeldung = cls._ANMELDUNG.search(zeile, treffer.end())
            gefunden.append(Benutzer(
                slot=int(treffer.group("slot")),
                name=treffer.group("name"),
                benutzer_id=treffer.group("user_id"),
                art=treffer.group("type"),
                merker=int(treffer.group("flags"), 16),
                konto_id=treffer.group("id"),
                b64=treffer.group("b64"),
                vordergrund=treffer.group("current") == "1",
                anmeldung=(anmeldung.group("signin")
                           if anmeldung is not None else None),
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


# -- Die Ausgabe des PIN-Payloads -------------------------------------------

@dataclass(frozen=True)
class PinAusgabe:
    """Was das PIN-Payload (oder PREPARE_PIN) zurueckmeldet.

    ``ergebnis``: "" (noch offen), "erfolg", "falsche_pin",
    "falsche_konto_id" oder "fehler" - dann steht in ``fehler``, was die
    Konsole gemeldet hat.
    """

    pin: str = ""
    b64: str = ""
    slot: int = 0
    ergebnis: str = ""
    fehler: str = ""


_PIN_ZEILE = re.compile(r"^pin=(\d{4} \d{4})\s*$", re.MULTILINE)
_B64_ZEILE = re.compile(r"^account_id_base64=(\S+)\s*$", re.MULTILINE)
_SLOT_ZEILE = re.compile(r"^slot=(\d+)\s*$", re.MULTILINE)
_FEHLSCHLAG = re.compile(r"^PAIRING FAILED[ \t]*(\S*)", re.MULTILINE)
_STARTFEHLER = re.compile(r"^ActRemoteLink ERROR[ \t]*\n(.+)$", re.MULTILINE)


def pin_ausgabe_lesen(text: str) -> PinAusgabe:
    """Zerlegt die Ausgabe des PIN-Payloads (actremotelink_pin_notify.c 2.0).

    Das Payload schreibt ``OK PIN``, ``slot=``, ``pin=1234 5678``,
    ``account_id_base64=`` und ``END``, danach - wenn Chiaki sich meldet -
    ``PAIRING SUCCESS`` oder ``PAIRING FAILED <grund>``. Laeuft die PIN ab,
    schreibt es **nichts** mehr; dann endet nur die Verbindung. PREPARE_PIN
    antwortet im selben Format (ohne ``pin=``) und geht hier ebenso durch.
    """
    text = str(text or "").replace("\r\n", "\n")
    pin = _PIN_ZEILE.search(text)
    b64 = _B64_ZEILE.search(text)
    slot = _SLOT_ZEILE.search(text)
    ergebnis, fehler = "", ""
    fehlschlag = _FEHLSCHLAG.search(text)
    startfehler = _STARTFEHLER.search(text)
    if "PAIRING SUCCESS" in text:
        ergebnis = "erfolg"
    elif fehlschlag is not None:
        grund = fehlschlag.group(1)
        ergebnis = {"invalid_pin": "falsche_pin",
                    "invalid_account_id": "falsche_konto_id"}.get(grund, "fehler")
        if ergebnis == "fehler":
            fehler = grund or "?"
    elif startfehler is not None:
        ergebnis, fehler = "fehler", startfehler.group(1).strip()
    return PinAusgabe(pin=pin.group(1) if pin else "",
                      b64=b64.group(1) if b64 else "",
                      slot=int(slot.group(1)) if slot else 0,
                      ergebnis=ergebnis, fehler=fehler)


# -- Der Assistent ------------------------------------------------------------

#: Die Schritte, in ihrer Reihenfolge - die Reihenfolge ist Teil des
#: Verfahrens (siehe Modulkopf). Die Oberflaeche zeigt sie als nummerierte
#: Liste mit ``rpassist.schritt_<name>`` und ``rpassist.wer_<name>``.
ASSISTENT_SCHRITTE = ("verbinden", "benutzer", "konto", "anmeldung",
                      "neustart", "pin", "chiaki")

#: Die Zustaende eines Schritts.
OFFEN = "offen"
LAEUFT = "laeuft"
#: Wartet auf den Anwender - an der PS5 oder in Chiaki.
WARTET = "wartet"
ERLEDIGT = "erledigt"
UEBERSPRUNGEN = "uebersprungen"
FEHLER = "fehler"

#: So lange gilt eine PIN (actremotelink_pin_notify.c: ``time(0) + 300``).
PIN_GUELTIG = 300.0

#: Wie oft eine abgelaufene oder falsch eingegebene PIN von selbst durch eine
#: neue ersetzt wird, bevor der Assistent aufgibt.
PIN_VERSUCHE = 3


@dataclass(frozen=True)
class Ereignis:
    """Eine Meldung des Assistenten an die Oberflaeche.

    ``art``:

    * ``"schritt"`` - ``schritt`` steht jetzt auf ``zustand``; ``text`` ist
      der i18n-Schluessel der Anweisung "Jetzt" (leer: bleibt, wie sie ist),
      ``werte`` fuellt ihn.
    * ``"protokoll"`` - eine Zeile fuers Protokoll (``text`` = Schluessel).
    * ``"ausgabe"`` - eine Zeile, die das PIN-Payload geschrieben hat
      (``text`` = die Zeile selbst; sie ist sprachfrei).
    * ``"pin"`` - PIN und Konto-ID (``werte``: ``pin`` - leer, solange die
      Konsole sie nicht gemeldet hat -, ``b64`` und ``bis``, der Ablauf auf
      der Uhr :func:`time.monotonic`).
    * ``"merken"`` - soll das Programmende ueberstehen (``werte``:
      ``neustart_offen``).
    """

    art: str
    schritt: str = ""
    zustand: str = ""
    text: str = ""
    werte: "dict" = field(default_factory=dict)


class AssistentAbbruch(Exception):
    """Der Anwender hat abgebrochen (oder die Rueckfrage verneint)."""


class _Fehlschlag(Exception):
    """Der Ablauf endet hier - ``schluessel`` ist die Anweisung dazu."""

    def __init__(self, schluessel: str, **werte) -> None:
        super().__init__(schluessel)
        self.schluessel = schluessel
        self.werte = werte


class Kopplungsassistent:
    """Fuehrt die ganze Kopplung aus - der Reihe nach, so weit es geht allein.

    Vom PC aus erledigt er alles, was geht: Agent schicken, Benutzer lesen,
    account_id setzen (ohne Angabe eine erzeugte), Offline-Anmeldung, PIN
    erzeugen und die Kopplung erkennen. Wo nur der Anwender weiterkommt,
    sagt er, was zu tun ist, und **wartet, bis er es sieht**:

    * einen neuen lokalen Benutzer anlegen bzw. zu ihm wechseln (LIST zeigt
      ihn mit ``current=1``),
    * die PS5 neu starten und den Jailbreak wieder starten (der Agent ist
      weg, danach antwortet der Payload-Lader wieder),
    * PIN und Konto-ID in Chiaki eingeben (``PAIRING SUCCESS`` in der
      Ausgabe des PIN-Payloads oder ein Geraet in ``PAIRED``).

    Jeder Schritt entscheidet am Zustand der Konsole - ein zweiter Lauf
    schreibt nichts doppelt und macht dort weiter, wo der erste stand. Nur
    den ausstehenden Neustart sieht man der Benutzerliste nicht an: Den
    meldet der Assistent als ``merken`` (``neustart_offen``), und die
    Oberflaeche reicht ihn beim naechsten Lauf wieder herein.

    **Zwischen SETID und FAKESIGNIN braucht es keinen Neustart:** Der Autor
    fuehrt beide hintereinander aus und startet danach einmal neu ("Full
    Workflow" im README von ActRemoteLink 2.0). Bis zum 24.09.2026
    verlangte ``koppeln`` nach jedem der beiden einen eigenen.

    Kein Tk hier: Alles, was die Oberflaeche wissen muss, geht als
    :class:`Ereignis` an ``melden``. Der Assistent laeuft in einem Faden;
    ``melden`` darf deshalb nur ablegen, nicht zeichnen.
    """

    def __init__(self, agent: ActRemoteLink, *,
                 slot: "int | None" = None,
                 konto_id: "int | str | None" = None,
                 neustart_offen: bool = False,
                 melden: "Callable[[Ereignis], None] | None" = None,
                 bestaetigen: "Callable[[Benutzer], bool] | None" = None,
                 abgebrochen: "Callable[[], bool] | None" = None,
                 lader_erreichbar: "Callable[[], bool] | None" = None,
                 pin_mitlesen: "Callable[[str], object] | None" = None,
                 takt: float = 3.0,
                 pin_gueltig: float = PIN_GUELTIG) -> None:
        """
        Args:
            agent: Der Agent auf der Konsole (mit ``agent_elf``/``pin_elf``).
            slot: Welcher Benutzer; ``None`` = der, der auf der PS5 vorne
                ist (ab Slot 2).
            konto_id: Die account_id, dezimal oder hex; ``None``: die
                vorhandene behalten bzw. eine erzeugen.
            neustart_offen: Ob seit dem letzten Schreiben noch ein Neustart
                aussteht (aus einem frueheren Lauf).
            bestaetigen: Wird vor dem ersten Schreiben gefragt; ``False``
                bricht ab.
            abgebrochen: Liefert ``True``, sobald der Anwender abbricht.
            lader_erreichbar: Antwortet der Payload-Lader der Konsole?
            pin_mitlesen: Schickt das PIN-Payload und liefert einen Leser
                seiner Ausgabe (``lesen()``, ``zu``, ``schliessen()`` wie
                ``payload_versand.Mitleser``) - oder ``None``, wenn der Weg
                keine Ausgabe zurueckreicht.
            takt: Sekunden zwischen zwei Nachfragen, solange gewartet wird.
            pin_gueltig: Wie lange eine PIN gilt.

        Raises:
            ValueError: ``konto_id`` ist keine Zahl oder 0 (mit 0 gilt der
                Benutzer als nicht aktiviert - FAKESIGNIN bricht dann ab).
        """
        self.agent = agent
        self.slot = None if slot in (None, "") else int(slot)
        self.konto_id = (None if konto_id in (None, "")
                         else agent.konto_id_normalisieren(konto_id))
        if self.konto_id is not None and _ist_null(self.konto_id):
            raise ValueError("account_id 0 aktiviert keinen Benutzer.")
        self.neustart_offen = bool(neustart_offen)
        self._melden = melden or (lambda _ereignis: None)
        self._bestaetigen = bestaetigen
        self._abgebrochen = abgebrochen or (lambda: False)
        self._lader_erreichbar = lader_erreichbar or (lambda: True)
        self._pin_mitlesen = pin_mitlesen
        self.takt = float(takt)
        self.pin_gueltig = float(pin_gueltig)
        self._bestaetigt = False
        self._aktuell = ASSISTENT_SCHRITTE[0]

    # -- Ablauf -------------------------------------------------------

    def lauf(self) -> str:
        """Fuehrt den Ablauf aus: "gekoppelt", "abgebrochen" oder "fehler".

        Wirft nichts - jeder Ausgang kommt auch als :class:`Ereignis` an.
        """
        try:
            self._ablauf()
        except AssistentAbbruch:
            self._schritt(self._aktuell, OFFEN, "rpassist.jetzt_abgebrochen")
            return "abgebrochen"
        except PayloadFehlt as fehler:
            self._schritt(self._aktuell, FEHLER, "rpassist.jetzt_kein_payload",
                          datei=fehler.muster, adresse=DOWNLOAD_ADRESSE)
            return "fehler"
        except Slot1Gesperrt:
            self._schritt(self._aktuell, FEHLER, "rpassist.jetzt_slot1")
            return "fehler"
        except _Fehlschlag as fehler:
            self._schritt(self._aktuell, FEHLER, fehler.schluessel,
                          **fehler.werte)
            return "fehler"
        except AgentAbgelehnt as fehler:
            self._schritt(self._aktuell, FEHLER, "rpassist.jetzt_abgelehnt",
                          text=str(fehler))
            return "fehler"
        except AgentOffline as fehler:
            self._schritt(self._aktuell, FEHLER, "rpassist.jetzt_offline",
                          text=str(fehler))
            return "fehler"
        except Exception as fehler:  # noqa: BLE001 - der Faden darf nicht still sterben
            logger.exception("Koppel-Assistent gescheitert")
            self._schritt(self._aktuell, FEHLER, "rpassist.jetzt_fehler",
                          text=str(fehler))
            return "fehler"
        return "gekoppelt"

    def _ablauf(self) -> None:
        self._verbinden()
        slot = self._benutzer_waehlen().slot
        for _runde in range(2):
            self._konto(slot)
            self._anmeldung(slot)
            self._neustart()
            if not anmeldung_noetig(self._eintrag(slot)):
                break
            # Die Anmeldung hat den Neustart nicht ueberstanden - noch einmal.
            self._protokoll("rpassist.log_anmeldung_fehlt_noch", slot=slot)
        else:
            raise _Fehlschlag("rpassist.jetzt_anmeldung_haelt_nicht", slot=slot)
        self._pin_und_chiaki(slot)

    # -- Die Schritte -------------------------------------------------

    def _verbinden(self) -> None:
        agent = self.agent
        self._schritt("verbinden", LAEUFT, "rpassist.jetzt_verbinden",
                      adresse=agent.host)
        if not agent.laeuft():
            if not agent.agent_elf:
                raise PayloadFehlt("agent")
            self._warten_bis(
                lambda: (agent.laeuft() or self._lader_erreichbar(),
                         "rpassist.jetzt_lader", {"adresse": agent.host}),
                "verbinden")
            self._schritt("verbinden", LAEUFT, "rpassist.jetzt_agent_senden")
        if agent.starten():
            # Er musste geschickt werden - ein Agent von vor einem Neustart
            # lebt also nicht mehr: Die PS5 wurde seitdem neu gestartet.
            self._neustart_erledigt()
        self._protokoll("rpassist.log_agent", adresse=agent.host,
                        port=agent.agent_port)
        self._schritt("verbinden", ERLEDIGT, "")

    def _benutzer_waehlen(self) -> Benutzer:
        agent = self.agent
        self._schritt("benutzer", LAEUFT, "rpassist.jetzt_benutzer")
        if self.slot is not None:
            if self.slot < 2:
                # Wirft Slot1Gesperrt - gleich, was dort steht.
                schreibzugriff_pruefen(None, self.slot)
            slot = self.slot

            def _pruefung():
                return (agent.benutzer(slot), "rpassist.jetzt_slot_fehlt",
                        {"slot": slot})
        else:
            def _pruefung():
                leute = [b for b in agent.benutzer_liste() if b.slot >= 2]
                if not leute:
                    return None, "rpassist.jetzt_neuer_benutzer", {}
                vorn = [b for b in leute if b.vordergrund]
                if vorn:
                    return vorn[0], "", {}
                if len(leute) == 1:
                    return leute[0], "", {}
                namen = ", ".join("%s (%d)" % (b.name or "-", b.slot)
                                  for b in leute)
                return None, "rpassist.jetzt_waehlen", {"namen": namen}
        eintrag = self._warten_bis(_pruefung, "benutzer")
        self._protokoll("rpassist.log_benutzer", name=eintrag.name or "-",
                        slot=eintrag.slot)
        self._schritt("benutzer", ERLEDIGT, "")
        return eintrag

    def _konto(self, slot: int) -> None:
        eintrag = self._eintrag(slot)
        self._schritt("konto", LAEUFT, "rpassist.jetzt_konto",
                      name=eintrag.name or "-", slot=slot)
        noetig, wert = setid_noetig(eintrag, self.konto_id)
        if not noetig:
            self._protokoll("rpassist.log_konto_da", slot=slot,
                            konto=eintrag.konto_id)
            self._schritt("konto", ERLEDIGT, "")
            return
        if wert is not None and wert.lower() != str(eintrag.konto_id or "").lower():
            # Zwei Benutzer mit derselben account_id - das liesse die Konsole
            # zwei Konten fuer eines halten. Eine erzeugte ID ist neu.
            doppelt = [b.slot for b in self.agent.benutzer_liste()
                       if b.slot != slot
                       and str(b.konto_id or "").lower() == wert.lower()]
            if doppelt:
                raise _Fehlschlag("rpassist.jetzt_id_doppelt", konto=wert,
                                  slot=doppelt[0])
        self._schreiben_bestaetigen(eintrag)
        if wert is None:
            wert = neue_konto_id()
            self._protokoll("rpassist.log_konto_neu", konto=wert)
        self.agent.konto_id_setzen(slot, wert)
        self._neustart_vormerken()
        self._protokoll("rpassist.log_konto_gesetzt", slot=slot, konto=wert)
        self._schritt("konto", ERLEDIGT, "")

    def _anmeldung(self, slot: int) -> None:
        eintrag = self._eintrag(slot)
        self._schritt("anmeldung", LAEUFT, "rpassist.jetzt_anmeldung",
                      name=eintrag.name or "-", slot=slot)
        if not anmeldung_noetig(eintrag):
            self._protokoll("rpassist.log_anmeldung_da", slot=slot)
            self._schritt("anmeldung", ERLEDIGT, "")
            return
        for _versuch in range(5):
            eintrag = self._vorne_warten(slot, "anmeldung")
            self._schreiben_bestaetigen(eintrag)
            self._schritt("anmeldung", LAEUFT, "rpassist.jetzt_anmeldung",
                          name=eintrag.name or "-", slot=slot)
            try:
                self.agent.fake_anmeldung(slot)
            except BenutzerNichtVorn:
                continue            # zwischen Nachsehen und Schreiben gewechselt
            except AgentAbgelehnt as fehler:
                if "target_slot_mismatch" not in str(fehler):
                    raise
                continue            # dasselbe, vom Agent selbst bemerkt
            break
        else:
            raise _Fehlschlag("rpassist.jetzt_nicht_vorn", slot=slot)
        self._neustart_vormerken()
        self._protokoll("rpassist.log_anmeldung", slot=slot)
        self._schritt("anmeldung", ERLEDIGT, "")

    def _neustart(self) -> None:
        agent = self.agent
        if not self.neustart_offen:
            self._schritt("neustart", UEBERSPRUNGEN, "")
            return
        while True:
            # Der Agent lebt bis zum Neustart - ist er weg, war einer.
            self._warten_bis(lambda: (not agent.laeuft(),
                                      "rpassist.jetzt_neustart", {}),
                             "neustart")
            self._protokoll("rpassist.log_neustart_erkannt")
            self._warten_bis(
                lambda: (agent.laeuft() or self._lader_erreichbar(),
                         "rpassist.jetzt_nach_neustart", {}),
                "neustart")
            self._schritt("neustart", LAEUFT, "rpassist.jetzt_agent_senden")
            if agent.starten():
                break
            # Der alte Agent antwortet wieder: Die PS5 war nur kurz nicht zu
            # erreichen, neu gestartet wurde sie nicht.
            self._protokoll("rpassist.log_doch_kein_neustart")
        self._neustart_erledigt()
        self._schritt("neustart", ERLEDIGT, "")

    def _pin_und_chiaki(self, slot: int) -> None:
        agent = self.agent
        for versuch in range(1, PIN_VERSUCHE + 1):
            self._schritt("pin", LAEUFT, "rpassist.jetzt_pin")
            # Das PIN-Payload nimmt den Benutzer, der vorne ist.
            eintrag = self._vorne_warten(slot, "pin")
            if agent.gekoppelt(slot):
                self._schritt("pin", UEBERSPRUNGEN, "")
                self._protokoll("rpassist.log_schon_gekoppelt", slot=slot)
                self._fertig(eintrag)
                return
            if not agent.pin_elf:
                raise PayloadFehlt("pin")
            b64 = pin_ausgabe_lesen(agent.pin_vorbereiten()).b64 or eintrag.b64
            bis = time.monotonic() + self.pin_gueltig
            self._melde(Ereignis("pin", werte={"pin": "", "b64": b64, "bis": bis}))
            leser = (self._pin_mitlesen(agent.pin_elf)
                     if self._pin_mitlesen is not None else None)
            if leser is None:
                agent.pin_senden()
                self._protokoll("rpassist.log_pin_ohne_ausgabe")
            self._schritt("pin", ERLEDIGT, "")
            self._schritt("chiaki", WARTET, "rpassist.jetzt_chiaki",
                          adresse=agent.host)
            ergebnis = self._kopplung_abwarten(slot, leser, b64, bis)
            if ergebnis == "erfolg":
                self._fertig(eintrag)
                return
            if versuch < PIN_VERSUCHE:
                self._protokoll("rpassist.log_neue_pin_" + ergebnis)
        raise _Fehlschlag("rpassist.jetzt_pin_aufgegeben", anzahl=PIN_VERSUCHE)

    def _kopplung_abwarten(self, slot: int, leser, b64: str,
                           bis: float) -> str:
        """Wartet auf Chiaki: "erfolg", "abgelaufen", "falsche_pin" oder
        "falsche_konto_id"."""
        agent = self.agent
        text = ""
        gezeigt = ""
        fertige_zeilen = 0
        naechste_frage = time.monotonic() + self.takt
        try:
            while True:
                self._abbruch_pruefen()
                if leser is not None and not leser.zu:
                    text += leser.lesen()
                    zeilen = text.replace("\r\n", "\n").split("\n")
                    for zeile in zeilen[fertige_zeilen:-1]:
                        if zeile.strip():
                            self._melde(Ereignis("ausgabe", text=zeile.strip()))
                    fertige_zeilen = max(fertige_zeilen, len(zeilen) - 1)
                    ausgabe = pin_ausgabe_lesen(text)
                    if ausgabe.pin and ausgabe.pin != gezeigt:
                        gezeigt = ausgabe.pin
                        b64 = ausgabe.b64 or b64
                        self._melde(Ereignis("pin", werte={
                            "pin": ausgabe.pin, "b64": b64, "bis": bis}))
                        self._protokoll("rpassist.log_pin", pin=ausgabe.pin,
                                        b64=b64)
                    if ausgabe.ergebnis == "erfolg":
                        return "erfolg"
                    if ausgabe.ergebnis in ("falsche_pin", "falsche_konto_id"):
                        return ausgabe.ergebnis
                    if ausgabe.ergebnis == "fehler":
                        raise _Fehlschlag("rpassist.jetzt_pin_fehler",
                                          text=ausgabe.fehler)
                    if leser.zu:
                        # Beendet ohne Ergebnis: abgelaufen (dann schreibt
                        # das Payload nichts mehr) - oder vor der PIN
                        # gescheitert; den Grund nennt die Benachrichtigung.
                        if agent.gekoppelt(slot):
                            return "erfolg"
                        if ausgabe.pin:
                            return "abgelaufen"
                        raise _Fehlschlag("rpassist.jetzt_pin_beendet")
                else:
                    self._pause(min(1.0, self.takt))
                jetzt = time.monotonic()
                if jetzt >= naechste_frage:
                    naechste_frage = jetzt + self.takt
                    if agent.gekoppelt(slot):
                        return "erfolg"
                # Etwas Nachlauf: Das Payload zaehlt ab seinem Start, die
                # Frist hier ab dem Senden.
                if jetzt >= bis + min(5.0, self.pin_gueltig):
                    return "abgelaufen"
        finally:
            if leser is not None:
                leser.schliessen()

    def _fertig(self, eintrag: Benutzer) -> None:
        self._protokoll("rpassist.log_gekoppelt", slot=eintrag.slot)
        try:
            # Der Agent wird nicht mehr gebraucht (README: "Stop the Agent").
            self.agent.beenden()
        except AgentFehler:
            pass
        self._schritt("chiaki", ERLEDIGT, "rpassist.jetzt_fertig",
                      name=eintrag.name or "-", slot=eintrag.slot)

    # -- Hilfen -------------------------------------------------------

    def _eintrag(self, slot: int) -> Benutzer:
        eintrag = self.agent.benutzer(slot)
        if eintrag is None:
            raise _Fehlschlag("rpassist.jetzt_slot_fehlt", slot=slot)
        return eintrag

    def _vorne_warten(self, slot: int, schritt: str) -> Benutzer:
        """Wartet, bis dieser Benutzer auf der PS5 vorne ist."""
        def _pruefung():
            eintrag = self.agent.benutzer(slot)
            if eintrag is None:
                return None, "rpassist.jetzt_slot_fehlt", {"slot": slot}
            return (eintrag if eintrag.vordergrund else None,
                    "rpassist.jetzt_wechseln",
                    {"name": eintrag.name or "-", "slot": slot})
        return self._warten_bis(_pruefung, schritt)

    def _warten_bis(self, pruefung, schritt: str):
        """Fragt ``pruefung`` im Takt, bis sie etwas liefert.

        ``pruefung`` gibt ``(ergebnis, text, werte)`` zurueck. Solange
        ``ergebnis`` leer ist, steht der Schritt auf :data:`WARTET` mit
        dieser Anweisung - gemeldet wird nur, wenn sie sich aendert.
        """
        zuletzt = None
        while True:
            self._abbruch_pruefen()
            ergebnis, text, werte = pruefung()
            if ergebnis:
                return ergebnis
            if (text, werte) != zuletzt:
                zuletzt = (text, werte)
                self._schritt(schritt, WARTET, text, **werte)
            self._pause(self.takt)

    def _schreiben_bestaetigen(self, eintrag: Benutzer) -> None:
        """Vor dem ersten Schreiben einmal fragen - verneint heisst Abbruch."""
        if self._bestaetigt:
            return
        if self._bestaetigen is not None and not self._bestaetigen(eintrag):
            raise AssistentAbbruch()
        self._bestaetigt = True

    def _neustart_vormerken(self) -> None:
        if not self.neustart_offen:
            self.neustart_offen = True
            self._melde(Ereignis("merken", werte={"neustart_offen": True}))

    def _neustart_erledigt(self) -> None:
        if self.neustart_offen:
            self.neustart_offen = False
            self._melde(Ereignis("merken", werte={"neustart_offen": False}))

    def _abbruch_pruefen(self) -> None:
        if self._abgebrochen():
            raise AssistentAbbruch()

    def _pause(self, dauer: float) -> None:
        """Schlaeft - und merkt einen Abbruch binnen einer Zehntelsekunde."""
        ende = time.monotonic() + max(0.0, float(dauer))
        while True:
            self._abbruch_pruefen()
            rest = ende - time.monotonic()
            if rest <= 0:
                return
            time.sleep(min(0.1, rest))

    # ``schluessel`` statt ``text``: Mehrere Anweisungen haben den Platzhalter
    # ``{text}`` - als Parametername stiesse er mit ``**werte`` zusammen.

    def _schritt(self, schritt: str, zustand: str, schluessel: str,
                 **werte) -> None:
        self._aktuell = schritt
        self._melde(Ereignis("schritt", schritt, zustand, schluessel,
                             dict(werte)))

    def _protokoll(self, schluessel: str, **werte) -> None:
        self._melde(Ereignis("protokoll", text=schluessel, werte=dict(werte)))

    def _melde(self, ereignis: Ereignis) -> None:
        try:
            self._melden(ereignis)
        except Exception:  # noqa: BLE001 - die Anzeige haelt den Ablauf nicht auf
            logger.exception("Ereignis nicht zustellbar: %r", ereignis)
