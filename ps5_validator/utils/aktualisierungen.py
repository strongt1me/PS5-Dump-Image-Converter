"""Prueft, ob es fuer die mitgelieferten Werkzeuge etwas Neueres gibt.

Zwei Teile, bewusst getrennt:

* **Das Urteil** - reine Funktionen auf Zeichenketten. Sie vergleichen
  Fassungen und ordnen ein, ohne irgendetwas zu holen. Damit laesst sich jede
  Regel ohne Netzverbindung pruefen.
* **Das Holen** - eine einzige Stelle, die eine Adresse abruft. Sie wird als
  Rueckruf hereingereicht (``holen``), nicht fest eingebaut. Tests geben eine
  Nachbildung mit, das Programm die echte Abfrage.

Warum der Aufwand: Die Verbindung zu GitHub ist auf dem Entwicklungsrechner
unzuverlaessig - etwa jeder zweite Aufruf bricht ab. Eine Pruefung, die daran
haengt, waere nicht wiederholbar testbar.

**Nicht alles hat eine maschinenlesbare Quelle.** FileZilla, OSFMount und die
Szene-Bestaende (AMPR EMU, Fakelibs, Nutzlasten) veroeffentlichen keine
abfragbare Fassungsliste. Fuer die gibt dieses Modul ``unbekannt`` zurueck und
nennt die Bezugsquelle - eine erfundene Aussage waere schlechter als keine.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

#: Woher sich die neueste Fassung abfragen laesst.
GITHUB = "github"
PYPI = "pypi"
OHNE_QUELLE = "ohne_quelle"

GITHUB_ADRESSE = "https://api.github.com/repos/%s/releases/latest"
PYPI_ADRESSE = "https://pypi.org/pypi/%s/json"

AKTUELL = "aktuell"
VERALTET = "veraltet"
VORAUS = "voraus"
UNBEKANNT = "unbekannt"
FEHLER = "fehler"

#: Wie oft eine Abfrage wiederholt wird, bevor sie als gescheitert gilt.
VERSUCHE = 3

_ZAHLEN = re.compile(r"\d+")


@dataclass(frozen=True)
class Bestandteil:
    """Etwas, das das Programm mitbringt oder benutzt."""

    name: str
    fassung: str
    art: str = OHNE_QUELLE
    quelle: str = ""
    hinweis: str = ""


@dataclass(frozen=True)
class Befund:
    """Das Ergebnis fuer einen Bestandteil."""

    name: str
    fassung: str
    neueste: str
    zustand: str
    quelle: str = ""
    hinweis: str = ""

    def __str__(self) -> str:
        if self.zustand == VERALTET:
            kern = "%s -> %s verfuegbar" % (self.fassung, self.neueste)
        elif self.zustand == AKTUELL:
            kern = "%s (aktuell)" % self.fassung
        elif self.zustand == VORAUS:
            kern = "%s (neuer als die Quelle: %s)" % (self.fassung, self.neueste)
        elif self.zustand == FEHLER:
            kern = "%s (nicht abfragbar: %s)" % (self.fassung, self.hinweis)
        elif self.hinweis:
            kern = "%s (%s)" % (self.fassung, self.hinweis)
        else:
            kern = "%s (keine abfragbare Quelle)" % self.fassung
        wo = ("  %s" % self.quelle) if self.quelle else ""
        return "%s: %s%s" % (self.name, kern, wo)


def fassung_teile(text: str) -> tuple[int, ...]:
    """Zerlegt eine Fassungsangabe in vergleichbare Zahlen.

    Alles Nicht-Zifferige faellt weg: ``v1.8.70``, ``1.8.70``, ``Release
    1.8.70`` ergeben dasselbe. Auf vier Stellen aufgefuellt, weil sonst
    ``0.3.5`` groesser waere als ``0.3.5.1`` - bei gleichem Anfang gilt das
    kuerzere Tupel als kleiner, und beim absteigenden Sortieren gewinnt dann
    die aeltere Nummer. Genau dieser Fehler trat 2026-08-20 in der
    AMPR-Versionsliste auf.

    Args:
        text: Die Fassungsangabe.

    Returns:
        Vier Zahlen; fehlende Stellen sind 0.
    """
    zahlen = [int(t) for t in _ZAHLEN.findall(str(text or ""))][:4]
    return tuple(zahlen + [0] * (4 - len(zahlen)))


def vergleiche(hier: str, dort: str) -> int:
    """Vergleicht zwei Fassungsangaben.

    Returns:
        -1 wenn ``hier`` aelter ist, 0 bei Gleichstand, 1 wenn ``hier`` neuer
        ist.
    """
    a, b = fassung_teile(hier), fassung_teile(dort)
    return (a > b) - (a < b)


def beurteile(teil: Bestandteil, neueste: str = "", fehler: str = "") -> Befund:
    """Ordnet einen Bestandteil gegen die gefundene neueste Fassung ein.

    Args:
        teil: Der Bestandteil samt hier vorliegender Fassung.
        neueste: Was die Quelle meldet; leer, wenn nichts zu holen war.
        fehler: Grund, falls die Abfrage scheiterte.

    Returns:
        Den Befund.
    """
    if teil.art == OHNE_QUELLE:
        return Befund(teil.name, teil.fassung, "", UNBEKANNT,
                      teil.quelle, teil.hinweis)
    if fehler:
        return Befund(teil.name, teil.fassung, "", FEHLER, teil.quelle, fehler)
    if not neueste:
        return Befund(teil.name, teil.fassung, "", UNBEKANNT,
                      teil.quelle, teil.hinweis)
    if not _ZAHLEN.search(str(teil.fassung or "")):
        # Steht hier keine Zahl ("vorhanden", "gefunden"), laesst sich
        # nichts vergleichen. Ohne diese Ausnahme galt jede solche
        # Angabe als 0.0.0.0 - und damit als veraltet, was schlicht
        # falsch ist. Am 21.08.2026 an tkinterdnd2 aufgefallen, das
        # kein __version__ mitbringt.
        return Befund(teil.name, teil.fassung, str(neueste), UNBEKANNT,
                      teil.quelle,
                      "eigene Fassung nicht auslesbar, verfuegbar: %s" % neueste)
    richtung = vergleiche(teil.fassung, neueste)
    zustand = AKTUELL if richtung == 0 else (VERALTET if richtung < 0 else VORAUS)
    return Befund(teil.name, teil.fassung, str(neueste), zustand,
                  teil.quelle, teil.hinweis)


def _lies_github(rohtext: str) -> str:
    """Zieht die Fassung aus der Antwort der GitHub-Releases-Schnittstelle."""
    daten = json.loads(rohtext)
    return str(daten.get("tag_name") or daten.get("name") or "").strip()


def _lies_pypi(rohtext: str) -> str:
    """Zieht die Fassung aus der Antwort der PyPI-Schnittstelle."""
    daten = json.loads(rohtext)
    return str((daten.get("info") or {}).get("version") or "").strip()


def adresse(teil: Bestandteil) -> str:
    """Die abzufragende Adresse fuer einen Bestandteil, oder leer."""
    if teil.art == GITHUB and teil.quelle:
        return GITHUB_ADRESSE % teil.quelle
    if teil.art == PYPI and teil.quelle:
        return PYPI_ADRESSE % teil.quelle
    return ""


def hole_fassung(teil: Bestandteil, holen, versuche: int = VERSUCHE) -> tuple[str, str]:
    """Fragt die neueste Fassung eines Bestandteils ab.

    Args:
        teil: Der Bestandteil.
        holen: Rueckruf ``holen(adresse) -> str``, der den Rohtext liefert.
        versuche: Wie oft es wiederholt wird. Die Verbindung bricht auf dem
            Entwicklungsrechner etwa bei jedem zweiten Aufruf ab; ein einzelner
            Fehlschlag ist deshalb kein Befund.

    Returns:
        ``(fassung, fehler)`` - genau eines von beiden ist gefuellt.
    """
    ziel = adresse(teil)
    if not ziel:
        return "", ""
    letzter = ""
    for _ in range(max(1, versuche)):
        try:
            rohtext = holen(ziel)
            fassung = _lies_github(rohtext) if teil.art == GITHUB else _lies_pypi(rohtext)
            if fassung:
                return fassung, ""
            letzter = "Antwort ohne Fassungsangabe"
        except Exception as exc:                     # noqa: BLE001 - Grund melden
            letzter = str(exc)[:120]
    return "", letzter or "keine Antwort"


def pruefe(teile: list[Bestandteil], holen, versuche: int = VERSUCHE) -> list[Befund]:
    """Prueft alle Bestandteile der Reihe nach.

    Args:
        teile: Was geprueft werden soll.
        holen: Rueckruf zum Abrufen einer Adresse.
        versuche: Wiederholungen je Abfrage.

    Returns:
        Je Bestandteil einen Befund, in derselben Reihenfolge.
    """
    befunde: list[Befund] = []
    for teil in teile:
        if teil.art == OHNE_QUELLE:
            befunde.append(beurteile(teil))
            continue
        fassung, fehler = hole_fassung(teil, holen, versuche)
        befunde.append(beurteile(teil, fassung, fehler))
    return befunde


def zusammenfassung(befunde: list[Befund]) -> str:
    """Eine Zeile fuer den Kopf des Abschnitts."""
    if not befunde:
        return "Aktualisierungen: nichts zu pruefen"
    veraltet = sum(1 for b in befunde if b.zustand == VERALTET)
    fehler = sum(1 for b in befunde if b.zustand == FEHLER)
    offen = sum(1 for b in befunde if b.zustand == UNBEKANNT)
    if veraltet:
        kern = "%d Aktualisierung%s verfuegbar" % (veraltet, "" if veraltet == 1 else "en")
    else:
        kern = "alles auf dem Stand der abgefragten Quellen"
    teile = [kern]
    if fehler:
        teile.append("%d nicht abfragbar" % fehler)
    if offen:
        teile.append("%d ohne abfragbare Quelle" % offen)
    return "Aktualisierungen: " + ", ".join(teile)
