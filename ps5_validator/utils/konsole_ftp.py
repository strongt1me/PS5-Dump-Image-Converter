# -*- coding: utf-8 -*-
"""Dateien mit der Konsole austauschen - ueber ftpsrv auf Port 2121.

Warum FTP und nicht das schnellere ps5upload: Dessen Uebertragungs-
Endpunkte sind nicht dokumentiert, sein eigener Client geht ueber
Tauri-IPC. Geraten wird hier nichts - ps5upload wird nur gestartet und
seine eigene Oberflaeche geoeffnet. FTP ist langsamer, dafuer vollstaendig
und ohne Fremdprogramm nutzbar.

**Die wichtigste Regel dieses Moduls: Ein Abbruch ist nur ZWISCHEN zwei
Dateien erlaubt.** Ein mittendrin abgebrochener ``RETR`` legt ftpsrv lahm -
der Port nimmt danach weiter Verbindungen an und antwortet nicht mehr, und
kein neu geladenes Payload holt ihn zurueck; nur ein Neustart der Konsole.
Am 17.08.2026 an der Konsole des Nutzers erlebt, seitdem Projektregel.
Darum fragt :func:`ordner_holen` den Abbruch **vor** jeder Datei und nie
waehrend einer Uebertragung.

Zweite gemessene Tatsache: Die Leitung zur Konsole ist langsam - auf dem
jetzigen Rechner rund 3,4 MB/s beim Holen und 2,5 MB/s beim Senden
(:data:`TEMPO_RUNTER`, :data:`TEMPO_HOCH`, 26.09.2026). Ein Spielordner von
50 GB ist damit kein Vorgang von Minuten - deshalb meldet jede Uebertragung
Fortschritt, und die Gesamtmenge laesst sich vorher getrennt ermitteln
(:func:`groesse_schaetzen`).

``ftpsrv`` meldet sich ohne Anmeldung; Benutzer und Kennwort sind beliebig.
Nur Standardbibliothek.

Vorlage: ``konsole/ftp.py`` aus den vorbereiteten Dateien des Nutzers.
Hier ergaenzt: die Abbruchregel als Zusicherung im Ergebnis
(``Fortschritt.abgebrochen``), die Gesamtzahlen im Ergebnis des Sendens und
die Trennung von Verbindungsfehler und Lesefehler.
"""
from __future__ import annotations

import ftplib
import logging
import os
import posixpath
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable, Iterator

logger = logging.getLogger("PS5Converter.konsole.ftp")

#: Der Port, auf dem ftpsrv auf der PS5 horcht (nicht 21).
FTP_PORT = 2121

#: Wie oft eine Datei nach einem abgerissenen Zugriff noch einmal versucht wird (Wartezeit je Versuch wachsend:
#: ``PAUSE``, 2 x ``PAUSE`` ...). Idee von fpkg2ftp (kvaps, GPL-3.0-or-later): Ein Spielordner von 50 GB ist Stunden
#: unterwegs, und die Leitung zur Konsole reisst gelegentlich ab.
VERSUCHE = 5
PAUSE = 3.0

#: Blockgroesse beim Senden. ``ftplib`` nimmt 8 KB - bei Spielordnern von vielen GB unnoetig klein.
SENDE_BLOCK = 256 * 1024

#: Uebliche Ablageorte auf der Konsole - fuer die Schnellauswahl im Fenster.
#: Der USB-Datentraeger steht oben: Dorthin schreibt der App-Dumper, und nur
#: von dort holt man einen Spielordner ab.
BEKANNTE_ORTE: tuple[tuple[str, str], ...] = (
    ("/mnt/usb0", "USB-Datentraeger 0"),
    ("/mnt/usb1", "USB-Datentraeger 1"),
    ("/mnt/ext0", "erweiterter Speicher (ext0)"),
    ("/data", "Datenbereich"),
    ("/user/home", "Benutzerdaten"),
    ("/", "Wurzel"),
)


#: So tief steigt ein Durchlauf hoechstens hinab. Kein Spielordner kommt
#: annaehernd dorthin; ein Verweis im Kreis - oder ein Server, der wieder die
#: falsche Ebene liefert - endet damit mit einer Meldung statt nie.
MAX_TIEFE = 32

#: Zeitgrenze der Datenverbindung waehrend einer Uebertragung. Die 10 s des
#: Verbindungsaufbaus waren dafuer zu knapp: Ein kurzer Stillstand der
#: Konsole (etwa ein anlaufendes USB-Laufwerk) riss den RETR mitten in der
#: Datei ab - und genau das legt ftpsrv lahm (Durchsicht vom 23.09.2026).
DATEN_ZEIT = 60.0


#: Zeichen, die Windows in Dateinamen nicht speichert. Ein ":" legt dort
#: still einen alternativen Datenstrom an - die Datei sieht danach leer aus
#: (Durchsicht vom 23.09.2026, H9-9).
_WINDOWS_VERBOTEN = frozenset('<>:"|?*')


def unter_windows_speicherbar(relativ: str) -> bool:
    """Laesst sich dieser Pfad (mit "/" getrennt) unter Windows anlegen, wie er ist?"""
    if os.name != "nt":
        return True
    for teil in str(relativ).split("/"):
        if any(z in _WINDOWS_VERBOTEN or ord(z) < 32 for z in teil):
            return False
        if teil and teil.rstrip(" .") != teil:
            return False       # Windows liesse Punkt oder Leerzeichen still fallen
    return True


class FtpFehler(RuntimeError):
    """Der FTP-Zugriff ist fehlgeschlagen."""


class FtpAbgebrochen(FtpFehler):
    """Der Anwender hat abgebrochen - zwischen zwei Schritten, nie mittendrin."""


class LeseFehler(FtpFehler):
    """Die Quelle (Platte, Rohr) liess sich nicht lesen - kein Netzfehler, also nie wiederholen."""


class ErsetzenUnvollstaendig(FtpFehler):
    """Die bisherige Datei liegt noch beiseite, die neue unter dem Zwischennamen.

    Nur :func:`umbenennen` wirft das, und nur dann, wenn nach einem
    gescheiterten Umbenennen auch das Zuruecklegen scheiterte. Dann darf der
    Aufrufer **nichts** wegraeumen: Beide Fassungen liegen noch auf der
    Konsole, nur nicht unter dem richtigen Namen.
    """


#: Endung der Zwischendatei beim Ablegen. Erst wenn sie vollstaendig
#: angekommen ist, bekommt sie den endgueltigen Namen.
ZWISCHEN_ENDUNG = ".tmp"

#: Endung, unter der :func:`umbenennen` eine vorhandene Datei beiseitelegt,
#: wenn der Server ein vorhandenes Ziel nicht selbst ersetzt.
BEISEITE_ENDUNG = ".alt"


@dataclass(frozen=True)
class Eintrag:
    """Ein Eintrag in einem Ordner auf der Konsole."""

    name: str
    ordner: bool
    groesse: int = 0

    @property
    def zeichen(self) -> str:
        return "/" if self.ordner else ""


@dataclass
class Fortschritt:
    """Was bisher uebertragen wurde. Wird an die Rueckmeldung gereicht."""

    dateien: int = 0
    dateien_gesamt: int = 0
    bytes: int = 0
    bytes_gesamt: int = 0
    aktuell: str = ""
    #: True, wenn der Anwender abgebrochen hat. Dann ist das Ziel
    #: unvollstaendig - das muss die Oberflaeche sagen duerfen.
    abgebrochen: bool = False
    #: Beim Fortsetzen: Dateien, die schon vollstaendig auf der Konsole lagen (nicht noch einmal gesendet), und
    #: Dateien, die dort angefangen lagen und von der Stelle an weitergeschrieben wurden.
    uebersprungen: int = 0
    fortgesetzt: int = 0
    #: Wie oft nach einem abgerissenen Zugriff neu verbunden wurde.
    wiederholt: int = 0

    @property
    def anteil(self) -> float:
        """0.0 bis 1.0, oder 0.0 solange die Gesamtmenge unbekannt ist."""
        if self.bytes_gesamt <= 0:
            return 0.0
        return min(1.0, self.bytes / self.bytes_gesamt)


def verbinden(adresse: str, port: int = FTP_PORT,
              zeit: float = 10.0) -> ftplib.FTP:
    """Baut eine Verbindung auf. ``ftpsrv`` verlangt keine Anmeldung."""
    ziel = (adresse or "").strip()
    if not ziel:
        raise FtpFehler("Keine PS5-Adresse angegeben.")

    verbindung = ftplib.FTP()
    try:
        verbindung.connect(ziel, int(port), timeout=zeit)
        verbindung.login()
        # Ohne passiven Modus muesste die Konsole zum PC zurueckverbinden -
        # das scheitert an jeder Firewall auf dem PC.
        verbindung.set_pasv(True)
    except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
        raise FtpFehler(
            "%s:%d nicht erreichbar - laeuft ftpsrv? (%s)"
            % (ziel, int(port), fehler)) from fehler
    return verbindung


def auflisten(verbindung: ftplib.FTP, pfad: str) -> list[Eintrag]:
    """Inhalt eines Ordners.

    Erst ``CWD`` in den Ordner, dann ``MLSD`` **ohne** Pfad. Der
    mitgelieferte ftpsrv 0.21.1 uebergeht das Argument von ``MLSD`` und
    listet immer sein Arbeitsverzeichnis (``cmd.c``: ``opendir(env->cwd)``).
    Mit ``MLSD <pfad>`` sah deshalb jeder Ordner aus wie ``/``, und
    :func:`groesse_schaetzen` lief endlos im Kreis - die Pfade wurden nur
    laenger (Durchsicht vom 23.09.2026). Nach dem ``CWD`` braucht keiner der
    beiden Befehle ein Argument, und das Ergebnis stimmt auf jedem Server.

    ``MLSD`` zuerst, weil es eindeutig zwischen Datei und Ordner
    unterscheidet. Kann der Server das nicht, wird die Textausgabe von
    ``LIST`` gelesen - dort steht der Typ im ersten Zeichen der Zeile.
    """
    ziel = str(pfad or "").strip() or "/"
    try:
        verbindung.cwd(ziel)
    except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
        raise FtpFehler("%s nicht lesbar: %s" % (ziel, fehler)) from fehler
    try:
        return sorted(
            (Eintrag(name=name,
                     ordner=merkmale.get("type") == "dir",
                     groesse=int(merkmale.get("size", 0) or 0))
             for name, merkmale in verbindung.mlsd()
             if name not in (".", "..")),
            key=lambda e: (not e.ordner, e.name.lower()))
    except (ftplib.error_perm, ftplib.error_proto):
        pass  # Kein MLSD - unten mit LIST weiter.
    except Exception as fehler:  # noqa: BLE001
        raise FtpFehler("%s nicht lesbar: %s" % (ziel, fehler)) from fehler

    zeilen: list[str] = []
    try:
        verbindung.retrlines("LIST", zeilen.append)
    except Exception as fehler:  # noqa: BLE001
        raise FtpFehler("%s nicht lesbar: %s" % (ziel, fehler)) from fehler

    eintraege: list[Eintrag] = []
    for zeile in zeilen:
        teile = zeile.split(maxsplit=8)
        if len(teile) < 9:
            continue
        name = teile[8]
        if name in (".", ".."):
            continue
        eintraege.append(Eintrag(
            name=name,
            ordner=zeile.startswith("d"),
            groesse=int(teile[4]) if teile[4].isdigit() else 0,
        ))
    return sorted(eintraege, key=lambda e: (not e.ordner, e.name.lower()))


def hoehere_ebene(pfad: str) -> str:
    """Eine Ebene ueber diesem Pfad - die Wurzel bleibt die Wurzel."""
    sauber = "/" + str(pfad or "/").strip().strip("/")
    if sauber == "/":
        return "/"
    oben = posixpath.dirname(sauber)
    return oben or "/"


def _durchlaufen(verbindung: ftplib.FTP, wurzel: str,
                 abbruch: "Callable[[], bool] | None" = None
                 ) -> Iterator[tuple[str, Eintrag]]:
    """Alle Dateien unterhalb von ``wurzel``, Ordner zuerst betreten.

    ``abbruch`` wird vor jedem Ordner gefragt: Auflisten ist kein ``RETR``
    und darf jederzeit enden. Dann wirft der Durchlauf ``FtpAbgebrochen`` -
    ein stilles Ende saehe aus wie ein vollstaendiger Baum.
    """
    offen = [(wurzel, 0)]
    while offen:
        if abbruch is not None and abbruch():
            raise FtpAbgebrochen("Auf Wunsch abgebrochen.")
        ordner, tiefe = offen.pop(0)
        for eintrag in auflisten(verbindung, ordner):
            voll = posixpath.join(ordner, eintrag.name)
            if eintrag.ordner:
                if tiefe >= MAX_TIEFE:
                    raise FtpFehler(
                        "%s liegt mehr als %d Ebenen tief - Verweis im Kreis?"
                        % (voll, MAX_TIEFE))
                offen.append((voll, tiefe + 1))
            else:
                yield voll, eintrag


def groesse_schaetzen(adresse: str, fern: str, port: int = FTP_PORT,
                      melden: Callable[[int, int], None] | None = None,
                      abbruch: "Callable[[], bool] | None" = None
                      ) -> tuple[int, int]:
    """Wie viele Dateien und Bytes liegen unter diesem Pfad?

    Wird vor einer Uebertragung gerufen, damit der Balken etwas anzeigen
    kann. Bei grossen Baeumen kostet schon das Zeit - deshalb getrennt
    aufrufbar, und ``melden`` bekommt den Zwischenstand, damit auch dieser
    Schritt nicht stumm bleibt. ``abbruch`` beendet ihn zwischen zwei
    Ordnern (``FtpAbgebrochen``).
    """
    verbindung = verbinden(adresse, port)
    try:
        dateien = bytes_ = 0
        for _, eintrag in _durchlaufen(verbindung, fern, abbruch):
            dateien += 1
            bytes_ += eintrag.groesse
            if melden is not None and dateien % 50 == 0:
                melden(dateien, bytes_)
        if melden is not None:
            melden(dateien, bytes_)
        return dateien, bytes_
    finally:
        schliessen(verbindung)


def ordner_holen(adresse: str, fern: str, lokal: "str | Path",
                 port: int = FTP_PORT,
                 auf_fortschritt: "Callable[[Fortschritt], None] | None" = None,
                 abbruch: "Callable[[], bool] | None" = None,
                 dateien_gesamt: int = 0,
                 bytes_gesamt: int = 0) -> Fortschritt:
    """Holt einen ganzen Ordner von der Konsole auf den PC.

    Args:
        fern: Pfad auf der Konsole, z. B. ``/mnt/usb0/PPSA01234``.
        lokal: Zielordner auf dem PC.
        abbruch: Wird **vor jeder Datei** gefragt - nie mittendrin. Liefert
            es ``True``, endet die Uebertragung geordnet (siehe Modulkopf:
            ein abgebrochener RETR legt ftpsrv lahm).
        dateien_gesamt, bytes_gesamt: aus :func:`groesse_schaetzen`, damit
            der Balken von Anfang an stimmt.

    Returns:
        Den Endstand. ``abgebrochen`` sagt, ob das Ziel vollstaendig ist.
    """
    ziel = Path(lokal)
    ziel.mkdir(parents=True, exist_ok=True)

    # Erst pruefen, ob es passt: Ein voller Datentraeger mitten in einer
    # Datei brach bis zum 23.09.2026 den RETR ab - und legte damit ftpsrv
    # lahm, obwohl das Problem auf dem PC lag.
    if bytes_gesamt > 0:
        try:
            frei = shutil.disk_usage(ziel).free
        except OSError:
            frei = -1
        if 0 <= frei < bytes_gesamt:
            raise FtpFehler(
                "Zu wenig Platz in %s: %s frei, %s noetig."
                % (ziel, menge_lesbar(frei), menge_lesbar(bytes_gesamt)))

    stand = Fortschritt(dateien_gesamt=dateien_gesamt,
                        bytes_gesamt=bytes_gesamt)
    verbindung = verbinden(adresse, port)
    # Gilt fuer jede Datenverbindung, die ftplib ab hier aufbaut.
    verbindung.timeout = DATEN_ZEIT

    try:
        for pfad, _eintrag in _durchlaufen(verbindung, fern):
            if abbruch is not None and abbruch():
                stand.abgebrochen = True
                logger.info("Uebertragung auf Wunsch beendet (zwischen zwei "
                            "Dateien, nach %d)", stand.dateien)
                break

            relativ = posixpath.relpath(pfad, fern)
            if not unter_windows_speicherbar(relativ):
                # Umbenennen wuerde den Dump still veraendern; also ehrlich
                # enden - vor dem RETR, wo das der Konsole nicht schadet.
                raise FtpFehler(
                    "%s laesst sich unter Windows nicht speichern (Zeichen "
                    "wie : oder ? im Namen) - vor dieser Datei beendet."
                    % relativ)
            datei = ziel / Path(relativ)
            datei.parent.mkdir(parents=True, exist_ok=True)

            stand.aktuell = relativ
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

            try:
                ausgabe = open(datei, "wb")
            except OSError as fehler:
                # Noch kein RETR unterwegs - hier darf es einfach enden.
                raise FtpFehler("%s nicht speicherbar: %s"
                                % (relativ, fehler)) from fehler
            # Scheitert das Schreiben auf dem PC, wird der RETR trotzdem zu
            # Ende gelesen: Eine Ausnahme im Rueckruf wuerde ihn mittendrin
            # abreissen (siehe Modulkopf). Gemeldet wird danach.
            schreibfehler: list[OSError] = []
            try:
                def schreiben(block: bytes) -> None:
                    if schreibfehler:
                        return
                    try:
                        ausgabe.write(block)
                    except OSError as fehler:
                        schreibfehler.append(fehler)
                        return
                    stand.bytes += len(block)
                    if auf_fortschritt is not None:
                        auf_fortschritt(stand)

                verbindung.retrbinary("RETR %s" % pfad, schreiben)
            except Exception as fehler:  # noqa: BLE001
                raise FtpFehler("%s nicht ladbar: %s"
                                % (pfad, fehler)) from fehler
            finally:
                try:
                    ausgabe.close()
                except OSError as fehler:
                    schreibfehler.append(fehler)
            if schreibfehler:
                try:
                    datei.unlink()
                except OSError:
                    pass
                raise FtpFehler(
                    "%s nicht speicherbar: %s (der Download wurde zu Ende "
                    "gelesen, ftpsrv bleibt bedienbar)"
                    % (relativ, schreibfehler[0])) from schreibfehler[0]

            stand.dateien += 1
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

        return stand
    finally:
        schliessen(verbindung)


# ---------------------------------------------------------------------------
# Senden mit Fortsetzen und Wiederverbinden (seit 10.10.2026)
#
# Vorbild: fpkg2ftp (kvaps, GPL-3.0-or-later) - eine angefangene Datei wird von der Stelle an weitergeschrieben,
# an der die Konsole sie hat (SIZE, APPE), eine vollstaendige uebersprungen, ein abgerissener Zugriff mit frischer
# Verbindung wiederholt. Hier neu geschrieben, nicht uebernommen. Die Regel des Moduls bleibt: abgebrochen wird nur
# ZWISCHEN zwei Dateien, auch beim Senden.
# ---------------------------------------------------------------------------
class GroesseFalsch(FtpFehler):
    """Nach dem Senden hat die Datei auf der Konsole eine andere Groesse - ein neuer Versuch klaert, was dort liegt."""


def ist_netzfehler(fehler: BaseException) -> bool:
    """Lohnt nach diesem Fehler ein neuer Versuch mit frischer Verbindung?

    Ja bei allem, was nach Leitung aussieht: Zeitgrenze, abgerissene oder verweigerte Verbindung, vorzeitiges Ende der
    Steuerverbindung, ein "4xx" des Servers (vorlaeufig) und eine falsche Groesse nach dem Senden. Nein bei einem
    "5xx" (der Server lehnt ab - ein zweiter Versuch bringt dasselbe) und bei einer Quelle, die sich nicht lesen
    laesst (:class:`LeseFehler`).
    """
    if isinstance(fehler, (LeseFehler, ftplib.error_perm)):
        return False
    return isinstance(fehler, (OSError, EOFError, GroesseFalsch, ftplib.error_temp, ftplib.error_proto))


def groesse_fern(verbindung: ftplib.FTP, pfad: str) -> "int | None":
    """Die Groesse einer Datei auf der Konsole (``SIZE``); ``None``, wenn es sie nicht gibt oder der Server es nicht kann.

    Netzfehler kommen als Ausnahme an: "gibt es nicht" und "Leitung weg" sind zweierlei.
    """
    try:
        wert = verbindung.size(pfad)
    except ftplib.error_perm:
        return None
    return None if wert is None else int(wert)


def fern_baum(verbindung: ftplib.FTP, wurzel: str,
              abbruch: "Callable[[], bool] | None" = None) -> dict[str, int]:
    """Alle Dateien unter ``wurzel`` auf der Konsole: Pfad (relativ, mit ``/``) -> Groesse. Fehlt ``wurzel``: leer.

    Ein Durchlauf mit ``MLSD`` je Ordner kostet weit weniger Anfragen als ``SIZE`` je Datei (ein Spiel hat Zehntausende
    Dateien, aber nur Hunderte Ordner).
    """
    ziel = "/" + str(wurzel or "").strip().strip("/")
    try:
        verbindung.cwd(ziel)
    except ftplib.error_perm:
        return {}
    ergebnis: dict[str, int] = {}
    for voll, eintrag in _durchlaufen(verbindung, ziel, abbruch):
        ergebnis[posixpath.relpath(voll, ziel)] = eintrag.groesse
    return ergebnis


def fortsetzen_ab(lokal: int, fern: "int | None") -> tuple[str, int]:
    """Was mit einer Datei geschieht, wenn auf der Konsole schon etwas von ihr liegt.

    Returns:
        ``("ueberspringen", Groesse)`` - gleich gross, nichts zu senden; ``("fortsetzen", fern)`` - angefangen,
        von dieser Stelle an anhaengen; sonst ``("neu", 0)`` (fehlt, ist groesser, oder die Quelle ist leer: Eine leere
        Datei kostet nichts und wird immer neu angelegt).
    """
    if fern is None or lokal <= 0:
        return "neu", 0
    if fern == lokal:
        return "ueberspringen", lokal
    if 0 < fern < lokal:
        return "fortsetzen", fern
    return "neu", 0


class _Begrenzt:
    """Liest hoechstens ``anzahl`` Byte aus ``quelle`` - ``storbinary`` liest sonst bis zum Ende der Quelle.

    Endet die Quelle vorher, ist das kein Dateiende, sondern ein Fehler (:class:`LeseFehler`): Ein abgeschnittenes
    Rohr darf nicht als fertige Datei gelten.
    """

    def __init__(self, quelle, anzahl: int) -> None:
        self._quelle = quelle
        self.noch = int(anzahl)

    def read(self, n: int = -1) -> bytes:
        if self.noch <= 0:
            return b""
        wunsch = self.noch if n is None or n < 0 else min(int(n), self.noch)
        try:
            daten = self._quelle.read(wunsch)
        except OSError as fehler:
            raise LeseFehler("die Quelle liess sich nicht lesen: %s" % fehler) from fehler
        if not daten:
            raise LeseFehler("die Quelle endete %d Byte zu frueh" % self.noch)
        self.noch -= len(daten)
        return daten


def ordner_sichern(verbindung: ftplib.FTP, pfad: str, angelegt: "set[str]") -> None:
    """Legt den Pfad an, Ebene fuer Ebene - nur die Ebenen, die ``angelegt`` noch nicht kennt.

    Ein Spielordner hat Hunderte Ordner und Zehntausende Dateien; ``MKD`` je Datei und je Ebene waere eine
    Anfrage pro Datei. Netzfehler kommen als Ausnahme an (der Aufrufer wiederholt), ein "gibt es schon" nicht.
    """
    teil = ""
    for stueck in str(pfad or "").strip("/").split("/"):
        if not stueck:
            continue
        teil = "%s/%s" % (teil, stueck)
        if teil in angelegt:
            continue
        try:
            verbindung.mkd(teil)
        except ftplib.error_perm:
            pass                            # gibt es schon (oder darf nicht - dann scheitert das Schreiben sagend)
        angelegt.add(teil)


def datei_senden(verbindung: ftplib.FTP, eingabe: IO[bytes], groesse: int, ziel: str, start: int = 0,
                 callback: "Callable[[bytes], None] | None" = None, pruefen: bool = True) -> None:
    """Schickt ``groesse - start`` Byte aus ``eingabe`` an ``ziel``: ab ``start`` angehaengt (``APPE``), sonst neu (``STOR``).

    ``eingabe`` liefert die Daten ab ``start`` (eine geoeffnete, dorthin gesetzte Datei oder ein Rohr); gelesen wird
    nicht ueber ``groesse`` hinaus. Danach fragt die Funktion die Groesse auf der Konsole (``SIZE``) und wirft
    :class:`GroesseFalsch`, wenn sie nicht stimmt - ein Server, der still abgeschnitten hat, soll nicht als Erfolg
    gelten. Netzfehler und ``error_perm`` kommen unveraendert an (:func:`ist_netzfehler`), eine nicht lesbare Quelle
    als :class:`LeseFehler`.
    """
    befehl = "APPE" if start > 0 else "STOR"
    quelle = _Begrenzt(eingabe, max(0, int(groesse) - max(0, int(start))))
    verbindung.storbinary("%s %s" % (befehl, ziel), quelle, blocksize=SENDE_BLOCK, callback=callback)
    if pruefen:
        tatsaechlich = groesse_fern(verbindung, ziel)
        if tatsaechlich is not None and tatsaechlich != groesse:
            raise GroesseFalsch("%s hat auf der Konsole %d statt %d Byte" % (ziel, tatsaechlich, groesse))


def warten(sekunden: float, abbruch: "Callable[[], bool] | None" = None) -> bool:
    """Wartet in kurzen Schritten und fragt dabei den Abbruch; ``True``, wenn abgebrochen wurde."""
    ende = time.monotonic() + max(0.0, sekunden)
    while True:
        if abbruch is not None and abbruch():
            return True
        rest = ende - time.monotonic()
        if rest <= 0:
            return False
        time.sleep(min(0.25, rest))


def wiederverbinden(adresse: str, port: int, versuch: int, versuche: int, pause: float,
                    abbruch: "Callable[[], bool] | None" = None) -> "tuple[ftplib.FTP | None, int]":
    """Baut die Verbindung nach einem Abriss neu auf - nach ``pause * versuch`` Sekunden, so oft es noetig und erlaubt ist.

    Returns:
        ``(Verbindung, Versuch)``; ``(None, Versuch)``, wenn waehrend des Wartens abgebrochen wurde.

    Raises:
        FtpFehler: auch der letzte Versuch kam nicht durch.
    """
    while True:
        versuch += 1
        if warten(pause * versuch, abbruch):
            return None, versuch
        try:
            verbindung = verbinden(adresse, port)
        except FtpFehler:
            if versuch >= versuche:
                raise
            continue
        verbindung.timeout = DATEN_ZEIT
        return verbindung, versuch


def ordner_senden(adresse: str, lokal: "str | Path", fern: str,
                  port: int = FTP_PORT,
                  auf_fortschritt: "Callable[[Fortschritt], None] | None" = None,
                  abbruch: "Callable[[], bool] | None" = None, *,
                  fortsetzen: bool = False, versuche: int = VERSUCHE,
                  pause: float = PAUSE) -> Fortschritt:
    """Schiebt einen Ordner vom PC auf die Konsole.

    Die Gesamtmenge steht hier vorher fest - der Ordner liegt ja auf diesem
    Rechner. Abgebrochen wird auch hier nur zwischen zwei Dateien.

    Args:
        fortsetzen: Eine Datei, die auf der Konsole schon in voller Groesse liegt, wird uebersprungen, eine
            angefangene von der Stelle an weitergeschrieben (``APPE``), alles andere neu gesendet - wie bei
            FileZilla "Fortsetzen". Nur richtig, wenn dort dieselbe Fassung liegt: Gleich grosse Dateien mit anderem
            Inhalt blieben stehen. Ohne ``fortsetzen`` wird jede Datei neu geschrieben.
        versuche, pause: Reisst der Zugriff mitten in einer Datei ab, wird bis zu ``versuche``-mal neu verbunden
            (nach ``pause``, ``2 x pause`` ... Sekunden) und die Datei dort fortgesetzt, wo die Konsole sie hat. Das
            gilt auch ohne ``fortsetzen``: Was dort liegt, hat dieser Lauf selbst geschrieben. Lehnt der Server
            ``APPE`` ab, wird die Datei neu gesendet.
    """
    quelle = Path(lokal)
    if not quelle.is_dir():
        raise FtpFehler("Kein Ordner: %s" % quelle)

    dateien = [p for p in sorted(quelle.rglob("*")) if p.is_file()]
    stand = Fortschritt(dateien_gesamt=len(dateien),
                        bytes_gesamt=sum(p.stat().st_size for p in dateien))

    verbindung = verbinden(adresse, port)
    verbindung.timeout = DATEN_ZEIT
    angelegt: set[str] = set()
    appe_geht = True
    try:
        vorhanden = fern_baum(verbindung, fern, abbruch) if fortsetzen else {}
        for datei in dateien:
            if abbruch is not None and abbruch():
                stand.abgebrochen = True
                break

            relativ = datei.relative_to(quelle).as_posix()
            zielpfad = posixpath.join(fern, relativ)
            stand.aktuell = relativ
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

            groesse = datei.stat().st_size
            vor = stand.bytes                  # der Stand vor dieser Datei: Jeder Versuch rechnet von hier aus
            bekannt = vorhanden.get(relativ) if fortsetzen else None
            erlaubt = fortsetzen               # darf anhand der Groesse auf der Konsole entschieden werden?
            begonnen = False                   # hat DIESER Lauf schon etwas an diese Datei geschickt?
            nachfragen = False                 # nach einem Abriss: erst fragen, was jetzt von der Datei dort liegt
            versuch = 0

            def gelesen(block: bytes) -> None:
                stand.bytes += len(block)
                if auf_fortschritt is not None:
                    auf_fortschritt(stand)

            while True:
                start = 0
                try:
                    ordner_sichern(verbindung, posixpath.dirname(zielpfad), angelegt)
                    if nachfragen:
                        # Was dort liegt, hat dieser Lauf selbst geschrieben (STOR schneidet ab, APPE haengt an): ein
                        # Anfang der Datei, von dem aus es weitergehen darf - auch ohne ``fortsetzen``.
                        bekannt, erlaubt = groesse_fern(verbindung, zielpfad), True
                        nachfragen = False
                    aktion, start = fortsetzen_ab(groesse, bekannt) if erlaubt else ("neu", 0)
                    if aktion == "fortsetzen" and not appe_geht:
                        aktion, start = "neu", 0
                    if aktion == "ueberspringen":
                        stand.bytes = vor + groesse
                        stand.uebersprungen += 1
                        break
                    try:
                        eingabe = open(datei, "rb")
                        eingabe.seek(start)
                    except OSError as fehler:
                        raise LeseFehler(str(fehler)) from fehler
                    stand.bytes = vor + start
                    begonnen = True            # ab hier gehoert die Datei diesem Lauf
                    with eingabe:
                        datei_senden(verbindung, eingabe, groesse, zielpfad, start, callback=gelesen)
                    if aktion == "fortsetzen":
                        stand.fortgesetzt += 1
                    break
                except LeseFehler as fehler:
                    raise FtpFehler("%s nicht lesbar: %s" % (relativ, fehler)) from fehler
                except ftplib.error_perm as fehler:
                    if start > 0 and appe_geht:
                        # Der Server nimmt kein APPE (oder lehnt es hier ab): Die Datei geht neu, ab jetzt alle so.
                        logger.info("APPE abgelehnt (%s) - %s wird neu gesendet", fehler, relativ)
                        appe_geht = False
                        continue
                    raise FtpFehler("%s nicht schreibbar: %s" % (relativ, fehler)) from fehler
                except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
                    if not ist_netzfehler(fehler):
                        raise FtpFehler("%s nicht schreibbar: %s" % (relativ, fehler)) from fehler
                    verbindung, versuch, ende = _nach_abriss(
                        fehler, relativ, adresse, port, versuch, versuche, pause, abbruch, verbindung, stand)
                    if ende:
                        break
                    nachfragen = begonnen
            if stand.abgebrochen:
                break

            stand.dateien += 1
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

        return stand
    finally:
        schliessen(verbindung)


def _nach_abriss(fehler: BaseException, relativ: str, adresse: str, port: int, versuch: int, versuche: int,
                 pause: float, abbruch: "Callable[[], bool] | None", verbindung: ftplib.FTP,
                 stand: Fortschritt) -> "tuple[ftplib.FTP, int, bool]":
    """Ein Zugriff ist abgerissen: alte Verbindung weg, neu verbinden. ``(Verbindung, Versuch, abgebrochen)``.

    Raises:
        FtpFehler: die Versuche sind aufgebraucht oder die Konsole ist nicht mehr zu erreichen.
    """
    schliessen(verbindung)
    if versuch >= versuche:
        raise FtpFehler("%s nicht schreibbar: %s (nach %d Versuchen)" % (relativ, fehler, versuch + 1)) from fehler
    logger.warning("%s: %s - verbinde neu (%d/%d)", relativ, fehler, versuch + 1, versuche)
    stand.wiederholt += 1
    neu, versuch = wiederverbinden(adresse, port, versuch, versuche, pause, abbruch)
    if neu is None:
        stand.abgebrochen = True
        return verbindung, versuch, True
    return neu, versuch, False


def vorhanden(adresse: str, pfad: str, port: int = FTP_PORT) -> bool:
    """Gibt es diesen Pfad auf der Konsole schon - als Datei oder Ordner?

    Gefragt wird der Ordner darueber, nicht der Pfad selbst: ``CWD`` auf
    eine Datei scheitert genauso wie auf einen fehlenden Pfad. Fehlt schon
    der Ordner darueber, gibt es den Pfad auch nicht.

    Raises:
        FtpFehler: keine Verbindung, oder der Ordner darueber ist da, laesst
            sich aber nicht auflisten - dann ist die Frage nicht zu
            beantworten, und "nein" waere geraten.
    """
    sauber = "/" + str(pfad or "").strip().strip("/")
    if sauber == "/":
        return True
    oben, name = posixpath.split(sauber)
    verbindung = verbinden(adresse, port)
    try:
        try:
            verbindung.cwd(oben or "/")
        except ftplib.error_perm:
            return False
        except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
            raise FtpFehler("%s nicht lesbar: %s" % (oben, fehler)) from fehler
        return any(e.name == name for e in auflisten(verbindung, oben or "/"))
    finally:
        schliessen(verbindung)


def _still_loeschen(verbindung: ftplib.FTP, pfad: str) -> None:
    """Raeumt eine Zwischendatei weg, soweit die Verbindung das noch zulaesst."""
    try:
        verbindung.delete(pfad)
    except Exception as fehler:  # noqa: BLE001 - nur Aufraeumen
        logger.debug("%s bleibt liegen: %s", pfad, fehler)


def umbenennen(verbindung: ftplib.FTP, alt: str, neu: str) -> None:
    """Benennt ``alt`` in ``neu`` um - und ersetzt dabei ein vorhandenes ``neu``.

    ftpsrv ersetzt beim Umbenennen selbst (``rename(2)`` unter FreeBSD); dort
    genuegt der erste Versuch. Ein Server, der ein vorhandenes Ziel abweist,
    bekommt es vorher beiseitegelegt (``<neu>.alt``), nicht geloescht:
    Scheitert das Umbenennen auch dann, kommt die bisherige Datei an ihren
    Platz zurueck. Geloescht wird sie erst, wenn die neue steht.

    Bis zum 24.09.2026 loeschte das Hochladen der AMPR-Bibliotheken das Ziel
    vorab. Wies der Server danach das Umbenennen ab, raeumte der
    Fehlerzweig auch noch die Zwischendatei weg - und auf der Konsole lag
    weder die alte noch die neue Bibliothek (Durchsicht, H12-7).

    Raises:
        FtpFehler: ``neu`` ist unveraendert; ``alt`` liegt noch da.
        ErsetzenUnvollstaendig: auch das Zuruecklegen scheiterte - die
            bisherige Datei liegt unter ``<neu>.alt``, die neue unter ``alt``.
    """
    try:
        verbindung.rename(alt, neu)
        return
    except ftplib.all_errors as fehler:
        erster = fehler

    beiseite = neu + BEISEITE_ENDUNG
    try:
        verbindung.rename(neu, beiseite)
    except ftplib.all_errors:
        # Das Ziel gibt es nicht oder es laesst sich nicht bewegen - dann
        # lag es nicht am Ziel, und der erste Fehler ist der Grund.
        raise FtpFehler("%s nicht umbenennbar: %s" % (alt, erster)) from erster

    try:
        verbindung.rename(alt, neu)
    except ftplib.all_errors as fehler:
        try:
            verbindung.rename(beiseite, neu)
        except ftplib.all_errors as zurueck:
            raise ErsetzenUnvollstaendig(
                "%s nicht umbenennbar (%s); die bisherige Datei liegt unter "
                "%s, die neue unter %s (%s)"
                % (alt, fehler, beiseite, alt, zurueck)) from fehler
        raise FtpFehler("%s nicht umbenennbar: %s" % (alt, fehler)) from fehler
    _still_loeschen(verbindung, beiseite)


def datei_ablegen(verbindung: ftplib.FTP, eingabe: IO[bytes], ziel: str,
                  callback: "Callable[[bytes], None] | None" = None) -> None:
    """Legt eine Datei auf der Konsole ab - nie halb, und nie gar nicht.

    Erst unter ``<ziel>.tmp`` hochladen, dann umbenennen (:func:`umbenennen`).
    Reisst die Verbindung mitten im ``STOR`` ab, liegt die bisherige Datei
    unversehrt da; nur die Zwischendatei ist unvollstaendig.

    Bis zum 24.09.2026 gingen Payloads und ``autoload.txt`` im Autoloader-
    Fenster direkt unter ihren endgueltigen Namen. Ein Abriss mitten im
    ``STOR`` hinterliess eine halbe ``etaHEN.bin``, die der Autoloader beim
    naechsten Start lud - die alte, laufende Fassung war schon abgeschnitten
    (Durchsicht, H10-6).

    Args:
        eingabe: zum Lesen geoeffnete Datei (oder ``io.BytesIO``).
        callback: wie bei ``storbinary`` - bekommt jeden gesendeten Block.

    Raises:
        FtpFehler: nichts abgelegt; ``ziel`` ist unveraendert.
        ErsetzenUnvollstaendig: siehe :func:`umbenennen`.
    """
    zwischen = ziel + ZWISCHEN_ENDUNG
    try:
        if callback is None:
            verbindung.storbinary("STOR %s" % zwischen, eingabe)
        else:
            verbindung.storbinary("STOR %s" % zwischen, eingabe,
                                  callback=callback)
    except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
        _still_loeschen(verbindung, zwischen)
        raise FtpFehler("%s nicht schreibbar: %s" % (ziel, fehler)) from fehler
    try:
        umbenennen(verbindung, zwischen, ziel)
    except ErsetzenUnvollstaendig:
        raise
    except FtpFehler:
        _still_loeschen(verbindung, zwischen)
        raise


def _lokale_zwischendatei_loeschen(pfad: Path) -> None:
    """Raeumt eine lokale ``.tmp``-Datei weg, soweit noch moeglich."""
    try:
        pfad.unlink()
    except OSError as fehler:
        logger.debug("%s bleibt liegen: %s", pfad, fehler)


def datei_holen(verbindung: ftplib.FTP, fern: str, lokal: "str | Path") -> bool:
    """Holt eine einzelne Datei von der Konsole - nie halb, und nie gar nicht.

    Umgekehrte Zwei-Schritt-Regel wie :func:`datei_ablegen`: Es wird erst
    nach ``<lokal>.tmp`` geschrieben, danach per ``os.replace`` auf den
    Endnamen gebracht. Reisst die Verbindung mitten im ``RETR`` ab, bleibt
    nur die Zwischendatei zurueck; ``lokal`` selbst ist unveraendert.

    Anders als bei :func:`datei_ablegen` ist ein fehlendes Fernziel hier
    kein Fehler, sondern die Rueckgabe ``False`` - der Normalfall, solange
    ein Vorgang auf der Konsole noch nicht abgeschlossen ist (z. B. ein
    Mitschnitt, waehrend das Spiel noch laeuft). Meldet der Server vorher
    eine Groesse (``SIZE``) und stimmt sie nach der Uebertragung nicht,
    gilt das als Uebertragungsfehler, nicht als Erfolg mit falscher Groesse
    - manche Server melden ``SIZE`` nicht, dann entfaellt die Pruefung.

    Args:
        fern: Pfad auf der Konsole.
        lokal: Zielpfad auf der Platte.

    Returns:
        ``True`` bei vollstaendigem Erfolg, ``False`` wenn ``fern`` (noch)
        nicht existiert.

    Raises:
        FtpFehler: Verbindungs-, Lese- oder Schreibfehler, oder die Groesse
            passt nach der Uebertragung nicht. ``lokal`` bleibt dann
            unveraendert.
    """
    lokal_pfad = Path(lokal)
    zwischen = lokal_pfad.with_name(lokal_pfad.name + ZWISCHEN_ENDUNG)
    try:
        erwartet = verbindung.size(fern)
    except Exception:  # noqa: BLE001 - SIZE ist optional, nicht jeder Server kann es
        erwartet = None
    try:
        with open(zwischen, "wb") as ziel:
            verbindung.retrbinary("RETR %s" % fern, ziel.write)
    except ftplib.error_perm as fehler:
        _lokale_zwischendatei_loeschen(zwischen)
        logger.debug("%s (noch) nicht auf der Konsole: %s", fern, fehler)
        return False
    except Exception as fehler:  # noqa: BLE001 - ftplib wirft breit
        _lokale_zwischendatei_loeschen(zwischen)
        raise FtpFehler("%s nicht lesbar: %s" % (fern, fehler)) from fehler

    tatsaechlich = zwischen.stat().st_size
    if erwartet is not None and tatsaechlich != erwartet:
        _lokale_zwischendatei_loeschen(zwischen)
        raise FtpFehler(
            "%s unvollstaendig uebertragen (%d von %d Byte)"
            % (fern, tatsaechlich, erwartet))

    os.replace(zwischen, lokal_pfad)
    return True


def ordner_anlegen(verbindung: ftplib.FTP, pfad: str) -> None:
    """Legt den Pfad an, Ebene fuer Ebene. Vorhandenes stoert nicht."""
    teil = ""
    for stueck in str(pfad or "").strip("/").split("/"):
        if not stueck:
            continue
        teil = "%s/%s" % (teil, stueck)
        try:
            verbindung.mkd(teil)
        except ftplib.error_perm:
            pass  # Gibt es schon.
        except Exception as _err:  # noqa: BLE001
            logger.debug("ordner_anlegen: %s - %s", teil, _err)


def schliessen(verbindung: ftplib.FTP) -> None:
    """Beendet die Verbindung, ohne beim Aufraeumen noch zu stoeren."""
    try:
        verbindung.quit()
    except Exception:  # noqa: BLE001
        try:
            verbindung.close()
        except Exception:  # noqa: BLE001
            pass


def menge_lesbar(bytes_: int) -> str:
    """Bytes als kurze, lesbare Menge - fuer Status- und Groessenfeld."""
    menge = float(max(0, int(bytes_)))
    for einheit in ("B", "KB", "MB", "GB", "TB"):
        if menge < 1024.0 or einheit == "TB":
            if einheit == "B":
                return "%d B" % int(menge)
            return "%.1f %s" % (menge, einheit)
        menge /= 1024.0
    return "%.1f TB" % menge


#: Gemessene Leitung zur Konsole in Byte/s, je Richtung - am 26.09.2026 auf
#: dem Rechner des Nutzers (seit dem Umzug vom 23.09.2026), jeweils mit dem
#: Ordner der eben installierten App ProsperoEden (58 Dateien, 99,2 MB):
#: Holen mit :func:`ordner_holen` zweimal 3,48 und 3,89 MB/s (alle Dateien per
#: SHA-256 gegen das ZIP geprueft), Senden mit ``app_paket.senden`` 2,57 MB/s.
#: Abgerundet auf die langsamere Messung - lieber etwas zu lang geschaetzt.
#: Auf dem alten Rechner (2,4-GHz-WLAN, 20.09.2026) waren es 0,80 beim Holen
#: und 1,11 MB/s beim Senden; bis zum 26.09.2026 rechnete die Schaetzung in
#: beide Richtungen mit 1,1 MB/s und nannte hier gut die doppelte Dauer.
TEMPO_RUNTER = 3.4 * 1024 * 1024
TEMPO_HOCH = 2.5 * 1024 * 1024


def dauer_schaetzen(bytes_: int, tempo: float = TEMPO_HOCH) -> float:
    """Wie lange das etwa dauert, in Sekunden.

    ``tempo``: :data:`TEMPO_RUNTER` beim Holen, :data:`TEMPO_HOCH` beim
    Senden. Ohne Angabe gilt die langsamere Richtung. Eine Schaetzung, kein
    Versprechen - aber der Unterschied zwischen "gleich" und "ueber Nacht"
    ist die Auskunft, die vor einer Uebertragung wirklich fehlt.
    """
    if bytes_ <= 0 or tempo <= 0:
        return 0.0
    return float(bytes_) / float(tempo)


def tempo_lesbar(tempo: float) -> str:
    """Eine Geschwindigkeit fuer die Rueckfrage - "3.4 MB/s", wie :func:`menge_lesbar`."""
    return menge_lesbar(int(tempo)) + "/s"


if __name__ == "__main__":  # pragma: no cover - Selbsttest von Hand
    import sys

    if len(sys.argv) < 2:
        print("Aufruf: python konsole_ftp.py <ps5-ip> [pfad]")
        raise SystemExit(1)

    ziel_ip = sys.argv[1]
    wo = sys.argv[2] if len(sys.argv) > 2 else "/"
    try:
        v = verbinden(ziel_ip)
        print("Verbunden mit %s:%d" % (ziel_ip, FTP_PORT))
        for e in auflisten(v, wo):
            print("  %s%s  %s" % (e.name, e.zeichen,
                                  "" if e.ordner else menge_lesbar(e.groesse)))
        schliessen(v)
    except FtpFehler as f:
        print("Fehler:", f)
        raise SystemExit(1)
