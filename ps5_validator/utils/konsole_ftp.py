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

Zweite gemessene Tatsache: Die Leitung zur Konsole traegt hier rund
1,1 MB/s (20.09.2026). Ein Spielordner von 50 GB ist damit kein Vorgang
von Minuten - deshalb meldet jede Uebertragung Fortschritt, und die
Gesamtmenge laesst sich vorher getrennt ermitteln
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
import posixpath
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

logger = logging.getLogger("PS5Converter.konsole.ftp")

#: Der Port, auf dem ftpsrv auf der PS5 horcht (nicht 21).
FTP_PORT = 2121

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


class FtpFehler(RuntimeError):
    """Der FTP-Zugriff ist fehlgeschlagen."""


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

    Zuerst ueber ``MLSD``, weil das eindeutig zwischen Datei und Ordner
    unterscheidet. Kann der Server das nicht, wird die Textausgabe von
    ``LIST`` gelesen - dort steht der Typ im ersten Zeichen der Zeile.
    """
    try:
        return sorted(
            (Eintrag(name=name,
                     ordner=merkmale.get("type") == "dir",
                     groesse=int(merkmale.get("size", 0) or 0))
             for name, merkmale in verbindung.mlsd(pfad)
             if name not in (".", "..")),
            key=lambda e: (not e.ordner, e.name.lower()))
    except (ftplib.error_perm, ftplib.error_proto):
        pass  # Kein MLSD - unten mit LIST weiter.
    except Exception as fehler:  # noqa: BLE001
        raise FtpFehler("%s nicht lesbar: %s" % (pfad, fehler)) from fehler

    zeilen: list[str] = []
    try:
        verbindung.retrlines("LIST %s" % pfad, zeilen.append)
    except Exception as fehler:  # noqa: BLE001
        raise FtpFehler("%s nicht lesbar: %s" % (pfad, fehler)) from fehler

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


def _durchlaufen(verbindung: ftplib.FTP, wurzel: str
                 ) -> Iterator[tuple[str, Eintrag]]:
    """Alle Dateien unterhalb von ``wurzel``, Ordner zuerst betreten."""
    offen = [wurzel]
    while offen:
        ordner = offen.pop(0)
        for eintrag in auflisten(verbindung, ordner):
            voll = posixpath.join(ordner, eintrag.name)
            if eintrag.ordner:
                offen.append(voll)
            else:
                yield voll, eintrag


def groesse_schaetzen(adresse: str, fern: str, port: int = FTP_PORT,
                      melden: Callable[[int, int], None] | None = None
                      ) -> tuple[int, int]:
    """Wie viele Dateien und Bytes liegen unter diesem Pfad?

    Wird vor einer Uebertragung gerufen, damit der Balken etwas anzeigen
    kann. Bei grossen Baeumen kostet schon das Zeit - deshalb getrennt
    aufrufbar, und ``melden`` bekommt den Zwischenstand, damit auch dieser
    Schritt nicht stumm bleibt.
    """
    verbindung = verbinden(adresse, port)
    try:
        dateien = bytes_ = 0
        for _, eintrag in _durchlaufen(verbindung, fern):
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

    stand = Fortschritt(dateien_gesamt=dateien_gesamt,
                        bytes_gesamt=bytes_gesamt)
    verbindung = verbinden(adresse, port)

    try:
        for pfad, _eintrag in _durchlaufen(verbindung, fern):
            if abbruch is not None and abbruch():
                stand.abgebrochen = True
                logger.info("Uebertragung auf Wunsch beendet (zwischen zwei "
                            "Dateien, nach %d)", stand.dateien)
                break

            relativ = posixpath.relpath(pfad, fern)
            datei = ziel / Path(relativ)
            datei.parent.mkdir(parents=True, exist_ok=True)

            stand.aktuell = relativ
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

            try:
                with open(datei, "wb") as ausgabe:
                    def schreiben(block: bytes) -> None:
                        ausgabe.write(block)
                        stand.bytes += len(block)
                        if auf_fortschritt is not None:
                            auf_fortschritt(stand)

                    verbindung.retrbinary("RETR %s" % pfad, schreiben)
            except Exception as fehler:  # noqa: BLE001
                raise FtpFehler("%s nicht ladbar: %s"
                                % (pfad, fehler)) from fehler

            stand.dateien += 1
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

        return stand
    finally:
        schliessen(verbindung)


def ordner_senden(adresse: str, lokal: "str | Path", fern: str,
                  port: int = FTP_PORT,
                  auf_fortschritt: "Callable[[Fortschritt], None] | None" = None,
                  abbruch: "Callable[[], bool] | None" = None) -> Fortschritt:
    """Schiebt einen Ordner vom PC auf die Konsole.

    Die Gesamtmenge steht hier vorher fest - der Ordner liegt ja auf diesem
    Rechner. Abgebrochen wird auch hier nur zwischen zwei Dateien.
    """
    quelle = Path(lokal)
    if not quelle.is_dir():
        raise FtpFehler("Kein Ordner: %s" % quelle)

    dateien = [p for p in sorted(quelle.rglob("*")) if p.is_file()]
    stand = Fortschritt(dateien_gesamt=len(dateien),
                        bytes_gesamt=sum(p.stat().st_size for p in dateien))

    verbindung = verbinden(adresse, port)
    try:
        for datei in dateien:
            if abbruch is not None and abbruch():
                stand.abgebrochen = True
                break

            relativ = datei.relative_to(quelle).as_posix()
            zielpfad = posixpath.join(fern, relativ)
            ordner_anlegen(verbindung, posixpath.dirname(zielpfad))

            stand.aktuell = relativ
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

            try:
                with open(datei, "rb") as eingabe:
                    def gelesen(block: bytes) -> None:
                        stand.bytes += len(block)
                        if auf_fortschritt is not None:
                            auf_fortschritt(stand)

                    verbindung.storbinary("STOR %s" % zielpfad, eingabe,
                                          callback=gelesen)
            except Exception as fehler:  # noqa: BLE001
                raise FtpFehler("%s nicht schreibbar: %s"
                                % (relativ, fehler)) from fehler

            stand.dateien += 1
            if auf_fortschritt is not None:
                auf_fortschritt(stand)

        return stand
    finally:
        schliessen(verbindung)


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
        except Exception:  # noqa: BLE001
            pass


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


def dauer_schaetzen(bytes_: int, tempo: float = 1.1 * 1024 * 1024) -> float:
    """Wie lange das etwa dauert, in Sekunden.

    ``tempo`` ist die am 20.09.2026 gemessene Leitungsgeschwindigkeit zur
    Konsole (1,1 MB/s). Eine Schaetzung, kein Versprechen - aber der
    Unterschied zwischen "gleich" und "ueber Nacht" ist die Auskunft, die
    vor einer Uebertragung wirklich fehlt.
    """
    if bytes_ <= 0 or tempo <= 0:
        return 0.0
    return float(bytes_) / float(tempo)


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
