"""Neuere AMPR-EMU-Fassungen von GitHub holen und in den Bestand legen.

Der mitgelieferte Versionsspeicher altert: Er wird beim Bauen eingefroren,
waehrend das Projekt ``drakmor/ampr_emu`` weiter veroeffentlicht. Am
04.09.2026 lagen hier hoechstens 0.3.6.2, auf GitHub standen bereits 0.3.6.4
und 0.3.6.6.

**Zwei Teile, bewusst getrennt** - dieselbe Aufteilung wie in
``aktualisierungen``:

* **Das Urteil** - reine Funktionen auf Zeichenketten und Listen. Sie lesen
  die Antwort der Schnittstelle, ordnen Fassungen ein und rechnen Zielpfade
  aus, ohne irgendetwas zu holen. Damit laesst sich jede Regel ohne
  Netzverbindung pruefen.
* **Das Holen** - wird als Rueckruf hereingereicht (``lade``), nicht fest
  eingebaut. Tests geben eine Nachbildung mit, das Programm die echte
  Abfrage.

**Netzzugriff nur auf Knopfdruck.** Nichts in diesem Modul faengt von selbst
an zu laden; jede Funktion, die ins Netz geht, braucht einen Rueckruf, den
der Aufrufer mitbringt. Das Programm hat sich das seit v1.8.74 zur Regel
gemacht, nachdem es an sechs Stellen ungefragt Anfragen verschickt hatte.

Aufbau der Veroeffentlichungen (04.09.2026 nachgesehen)::

    tag 0.3.6.6  "AMPR Emu 0.3.6.6"
        libSceAmpr.sprx-0.3.6.6-test           255.126 B
        libSceAmpr.sprx-0.3.6.6-test-debug     414.614 B

Die Fassung steht im Dateinamen, nicht in der Marke: Die Marke ``0.3.6``
traegt Anhaenge bis ``0.3.6.4``. Gelesen wird deshalb der **Anhangsname**.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

#: Ordner neben dem Programm, in dem geholte Fassungen landen.
ORDNERNAME = "AMPR EMU updates"

#: Unterordner darin - damit derselbe Scanner greift wie beim mitgelieferten
#: Bestand, der ``PlayGo & AMPR_EMU/AMPR_EMU/<Fassung> <Variante>/`` benutzt.
UNTERORDNER = "AMPR_EMU"

#: So heisst die Datei im Bestand, unabhaengig vom Namen des Anhangs.
DATEINAME = "libSceAmpr.sprx"

#: Die Schnittstelle. Alle Veroeffentlichungen, nicht nur die neueste - die
#: Marke 0.3.6 traegt Anhaenge, die neuer sind als sie selbst.
ADRESSE = "https://api.github.com/repos/%s/releases"

#: Das Projekt, das AMPR EMU veroeffentlicht.
PROJEKT = "drakmor/ampr_emu"

#: Wie die Varianten im Bestand heissen. Der Anhang ``...-test-debug`` ist
#: die Debug-Fassung, ``...-test`` die stille.
DEBUG = "debug"
OHNE_DEBUG = "no debug"

_FASSUNG = re.compile(r"(\d+(?:\.\d+)+)")


@dataclass(frozen=True)
class Angebot:
    """Eine holbare Fassung aus einer Veroeffentlichung."""

    fassung: str
    variante: str
    anhang: str
    adresse: str
    groesse: int = 0

    @property
    def beschriftung(self) -> str:
        """So heisst sie in der Auswahlliste - wie beim mitgelieferten Bestand."""
        return ("%s %s" % (self.fassung, self.variante)).strip()


def fassung_teile(text: str) -> tuple[int, ...]:
    """``"0.3.6.10"`` -> ``(0, 3, 6, 10)``; unbrauchbares wird zu ``()``.

    Zahlenweise, nicht als Zeichenkette: ``0.3.6.10`` ist neuer als
    ``0.3.6.9``, obwohl es alphabetisch davor stuende.
    """
    treffer = _FASSUNG.search(str(text or ""))
    if not treffer:
        return ()
    return tuple(int(t) for t in treffer.group(1).split("."))


def variante_aus_anhang(name: str) -> str:
    """Debug-Fassung oder nicht - abgelesen am Namen des Anhangs."""
    return DEBUG if str(name or "").rstrip().endswith("-debug") else OHNE_DEBUG


def fassung_aus_anhang(name: str) -> str:
    """Die Fassungsnummer aus dem Namen des Anhangs.

    Der Name traegt sie, die Marke nicht zuverlaessig: Unter der Marke
    ``0.3.6`` haengen Anhaenge bis ``0.3.6.4``.
    """
    treffer = _FASSUNG.search(str(name or ""))
    return treffer.group(1) if treffer else ""


def angebote_lesen(rohtext: str) -> list[Angebot]:
    """Liest die Antwort der Releases-Schnittstelle.

    Beruecksichtigt werden nur Anhaenge, deren Name mit ``libSceAmpr.sprx``
    beginnt und eine Fassungsnummer traegt. Alles andere - Quelltextarchive,
    Lesetexte - wird uebergangen.

    Doppelte (dieselbe Fassung und Variante in mehreren Veroeffentlichungen)
    kommen nur einmal vor; es gewinnt der erste Fund, und die Schnittstelle
    liefert die neueste Veroeffentlichung zuerst.
    """
    try:
        daten = json.loads(rohtext)
    except (ValueError, TypeError):
        return []
    if isinstance(daten, dict):        # eine einzelne Veroeffentlichung
        daten = [daten]
    if not isinstance(daten, list):
        return []

    raus: list[Angebot] = []
    gesehen: set[tuple[str, str]] = set()
    for veroeffentlichung in daten:
        if not isinstance(veroeffentlichung, dict):
            continue
        for anhang in (veroeffentlichung.get("assets") or []):
            if not isinstance(anhang, dict):
                continue
            name = str(anhang.get("name") or "")
            if not name.startswith(DATEINAME):
                continue
            fassung = fassung_aus_anhang(name)
            if not fassung:
                continue
            variante = variante_aus_anhang(name)
            schluessel = (fassung, variante)
            if schluessel in gesehen:
                continue
            adresse = str(anhang.get("browser_download_url") or "")
            if not adresse:
                continue
            gesehen.add(schluessel)
            try:
                groesse = int(anhang.get("size") or 0)
            except (TypeError, ValueError):
                groesse = 0
            raus.append(Angebot(fassung, variante, name, adresse, groesse))

    # Zwei Durchgaenge statt eines negierten Schluessels. Das Negieren
    # jeder Komponente - tuple(-t for t in ...) - geht bei verschieden
    # langen Fassungen schief: "0.3.6" wird zu (0,-3,-6), "0.3.6.6" zu
    # (0,-3,-6,-6). Das kuerzere Tupel ist ein Praefix des laengeren und
    # gilt damit als kleiner, also stuende 0.3.6 VOR 0.3.6.6. Beim
    # Schreiben genau so passiert; die Pruefung hat es gemeldet.
    raus.sort(key=lambda a: a.variante)
    raus.sort(key=lambda a: fassung_teile(a.fassung), reverse=True)
    return raus


def neuere(angebote: list[Angebot], vorhanden: list[str]) -> list[Angebot]:
    """Was von den Angeboten neuer ist als alles, was schon dasteht.

    ``vorhanden`` sind die Fassungsnummern im Bestand - egal aus welchem
    Speicher, mitgeliefert oder geholt. Verglichen wird gegen die **hoechste**
    davon: Eine Fassung, die zwischen zwei vorhandenen liegt, ist nichts
    Neues mehr.

    Gibt es gar nichts im Bestand, gilt alles als neu.
    """
    hoechste = max((fassung_teile(v) for v in vorhanden if fassung_teile(v)),
                   default=())
    if not hoechste:
        return list(angebote)
    return [a for a in angebote if fassung_teile(a.fassung) > hoechste]


def zielordner(wurzel: str, fassung: str, variante: str) -> str:
    """Wohin eine geholte Fassung gehoert.

    Derselbe Aufbau wie im mitgelieferten Bestand
    (``<Fassung> <Variante>/libSceAmpr.sprx``), damit der vorhandene Scanner
    sie ohne Aenderung findet.
    """
    return os.path.join(str(wurzel), UNTERORDNER,
                        ("%s %s" % (fassung, variante)).strip())


def zielpfad(wurzel: str, fassung: str, variante: str) -> str:
    """Der volle Pfad der Zieldatei."""
    return os.path.join(zielordner(wurzel, fassung, variante), DATEINAME)


def schon_da(wurzel: str, angebot: Angebot) -> bool:
    """Liegt diese Fassung in dieser Variante bereits im Zielordner?"""
    return os.path.isfile(zielpfad(wurzel, angebot.fassung, angebot.variante))


def ablegen(wurzel: str, angebot: Angebot, inhalt: bytes) -> str:
    """Schreibt einen geholten Anhang an seinen Platz.

    Erst neben die Zieldatei, dann umbenennen: Ein Abbruch mitten im
    Schreiben liesse sonst eine halbe Datei zurueck, die der Scanner als
    gueltige Fassung anboete.

    Raises:
        ValueError: Der Inhalt ist leer oder deutlich kleiner als angekuendigt.
    """
    if not inhalt:
        raise ValueError("Leerer Inhalt fuer %s" % angebot.beschriftung)
    if angebot.groesse and len(inhalt) < angebot.groesse:
        raise ValueError(
            "Unvollstaendig: %d von %d Bytes fuer %s"
            % (len(inhalt), angebot.groesse, angebot.beschriftung))

    ordner = zielordner(wurzel, angebot.fassung, angebot.variante)
    os.makedirs(ordner, exist_ok=True)
    ziel = os.path.join(ordner, DATEINAME)
    vorlaeufig = ziel + ".teil"
    with open(vorlaeufig, "wb") as datei:
        datei.write(inhalt)
    os.replace(vorlaeufig, ziel)
    return ziel


def holen(wurzel: str, angebote: list[Angebot], lade) -> tuple[list[str], list[str]]:
    """Holt mehrere Angebote und legt sie ab.

    Args:
        wurzel: Der Ordner ``AMPR EMU updates``.
        angebote: Was geholt werden soll.
        lade: Rueckruf ``(adresse) -> bytes``. Das Netz steckt allein hier.

    Returns:
        ``(abgelegte Pfade, Fehlermeldungen)``. Ein Fehlschlag bei einem
        Angebot haelt die uebrigen nicht auf - wer drei Fassungen holt und
        bei der zweiten scheitert, behaelt die erste und die dritte.
    """
    abgelegt: list[str] = []
    fehler: list[str] = []
    for angebot in angebote:
        try:
            abgelegt.append(ablegen(wurzel, angebot, lade(angebot.adresse)))
        except Exception as exc:  # noqa: BLE001
            fehler.append("%s: %s" % (angebot.beschriftung, exc))
    return abgelegt, fehler
