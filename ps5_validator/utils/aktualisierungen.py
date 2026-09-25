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
#: Ein Zusatz in Klammern, etwa die Fassung einer eingebetteten Bibliothek.
_KLAMMERN = re.compile(r"\([^)]*\)")

#: Die Saetze dieses Moduls - als Vorgabe deutsch. Das Diagnosefenster reicht
#: ueber ``texte=`` die uebersetzten herein (i18n ``aktualisierung.*``); bis
#: zum 24.09.2026 stand dort auch auf Englisch "1 Aktualisierung verfügbar"
#: (Durchsicht U2-8). Dasselbe Muster wie ``payload_versand.MELDUNGEN``.
MELDUNGEN: dict[str, str] = {
    "veraltet": "{fassung} -> {neueste} verfügbar",
    "aktuell": "{fassung} (aktuell)",
    "voraus": "{fassung} (neuer als die Quelle: {neueste})",
    "fehler": "{fassung} (nicht abfragbar: {grund})",
    "hinweis": "{fassung} ({hinweis})",
    "unlesbar": "{fassung} (eigene Fassung nicht auslesbar, verfügbar: {neueste})",
    "ohne_quelle": "{fassung} (keine abfragbare Quelle)",
    "wert_unbekannt": "unbekannt",
    "wert_vorhanden": "vorhanden",
    "kopf": "Aktualisierungen: {teile}",
    "nichts_zu_pruefen": "Aktualisierungen: nichts zu prüfen",
    "anzahl_eins": "1 Aktualisierung verfügbar",
    "anzahl_mehr": "{anzahl} Aktualisierungen verfügbar",
    "alles_aktuell": "alles auf dem Stand der abgefragten Quellen",
    "keine_antwort": "keine Quelle hat geantwortet",
    "nichts_abfragbar": "nichts abfragbar",
    "nicht_abfragbar": "{anzahl} nicht abfragbar",
    "ohne_quelle_anzahl": "{anzahl} ohne abfragbare Quelle",
}


def _satz(texte: "dict[str, str] | None", kennung: str, **werte) -> str:
    """Eine Vorlage, uebersetzt wenn moeglich - sonst die Vorgabe."""
    vorlage = (texte or {}).get(kennung) or MELDUNGEN[kennung]
    try:
        return vorlage.format(**werte)
    except (KeyError, IndexError, ValueError):
        return MELDUNGEN[kennung].format(**werte)


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

    def text(self, texte: "dict[str, str] | None" = None) -> str:
        """Die Zeile fuer den Bericht - uebersetzt, wenn ``texte`` da sind.

        "unbekannt" und "vorhanden" sind als Fassung Merker (sie tragen keine
        Zahl, siehe :func:`beurteile`) und werden erst hier uebersetzt.
        """
        fassung = self.fassung
        if fassung in ("unbekannt", "vorhanden"):
            fassung = _satz(texte, "wert_" + fassung)
        if self.zustand == VERALTET:
            kern = _satz(texte, "veraltet", fassung=fassung, neueste=self.neueste)
        elif self.zustand == AKTUELL:
            kern = _satz(texte, "aktuell", fassung=fassung)
        elif self.zustand == VORAUS:
            kern = _satz(texte, "voraus", fassung=fassung, neueste=self.neueste)
        elif self.zustand == FEHLER:
            kern = _satz(texte, "fehler", fassung=fassung, grund=self.hinweis)
        elif self.hinweis:
            kern = _satz(texte, "hinweis", fassung=fassung, hinweis=self.hinweis)
        elif self.neueste:
            kern = _satz(texte, "unlesbar", fassung=fassung, neueste=self.neueste)
        else:
            kern = _satz(texte, "ohne_quelle", fassung=fassung)
        wo = ("  %s" % self.quelle) if self.quelle else ""
        return "%s: %s%s" % (self.name, kern, wo)

    def __str__(self) -> str:
        return self.text()


def fassung_teile(text: str) -> tuple[int, ...]:
    """Zerlegt eine Fassungsangabe in vergleichbare Zahlen.

    Alles Nicht-Zifferige faellt weg: ``v1.8.70``, ``1.8.70``, ``Release
    1.8.70`` ergeben dasselbe. Auf vier Stellen aufgefuellt, weil sonst
    ``0.3.5`` groesser waere als ``0.3.5.1`` - bei gleichem Anfang gilt das
    kuerzere Tupel als kleiner, und beim absteigenden Sortieren gewinnt dann
    die aeltere Nummer. Genau dieser Fehler trat 2026-08-20 in der
    AMPR-Versionsliste auf.

    Was in Klammern steht, zaehlt nicht: ``lz4`` meldet sich als
    ``4.4.5 (liblz4 1.9.4)``, und bis zum 24.09.2026 wurde die 4 aus
    "liblz4" zur vierten Stelle - ein aktuelles lz4 galt dann als "neuer als
    die Quelle" (Durchsicht, U2-6).

    Args:
        text: Die Fassungsangabe.

    Returns:
        Vier Zahlen; fehlende Stellen sind 0.
    """
    ohne_zusatz = _KLAMMERN.sub(" ", str(text or ""))
    zahlen = [int(t) for t in _ZAHLEN.findall(ohne_zusatz)][:4]
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
        # Ohne Hinweis, mit "neueste": Den Satz dazu ("eigene Fassung nicht
        # auslesbar, verfuegbar: ...") baut Befund.text - uebersetzbar.
        return Befund(teil.name, teil.fassung, str(neueste), UNBEKANNT,
                      teil.quelle, "")
    richtung = vergleiche(teil.fassung, neueste)
    zustand = AKTUELL if richtung == 0 else (VERALTET if richtung < 0 else VORAUS)
    return Befund(teil.name, teil.fassung, str(neueste), zustand,
                  teil.quelle, teil.hinweis)


def _lies_github(rohtext: str) -> str:
    """Zieht die Fassung aus der Antwort der GitHub-Releases-Schnittstelle.

    Marke **und** Titel werden gelesen, und die hoehere Nummer gewinnt.
    Grund: Manche Projekte kuerzen die Marke ab. Bei ``drakmor/ampr_emu``
    heisst die Marke ``0.3.6``, das Release selbst aber "AMPR Emu 0.3.6 /
    0.3.6.1" - und 0.3.6.1 liegt wirklich darin. Nur die Marke zu lesen
    liess die hier vorhandene 0.3.6.1 als "neuer als die Quelle"
    erscheinen, was sie nicht ist.

    Nur Nummern mit mindestens einem Punkt zaehlen - eine blosse
    Jahreszahl im Titel soll nicht als Fassung durchgehen.
    """
    daten = json.loads(rohtext)
    text = "%s %s" % (daten.get("tag_name") or "", daten.get("name") or "")
    kandidaten = re.findall(r"\d+(?:\.\d+)+", text)
    if not kandidaten:
        return str(daten.get("tag_name") or daten.get("name") or "").strip()
    return max(kandidaten, key=fassung_teile)


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


def zusammenfassung(befunde: list[Befund],
                    texte: "dict[str, str] | None" = None) -> str:
    """Eine Zeile fuer den Kopf des Abschnitts.

    ``texte``: uebersetzte Vorlagen zu :data:`MELDUNGEN` (sonst deutsch).
    """
    if not befunde:
        return _satz(texte, "nichts_zu_pruefen")
    veraltet = sum(1 for b in befunde if b.zustand == VERALTET)
    fehler = sum(1 for b in befunde if b.zustand == FEHLER)
    offen = sum(1 for b in befunde if b.zustand == UNBEKANNT)
    beantwortet = sum(1 for b in befunde if b.zustand in (AKTUELL, VERALTET, VORAUS))
    if veraltet:
        kern = (_satz(texte, "anzahl_eins") if veraltet == 1
                else _satz(texte, "anzahl_mehr", anzahl=veraltet))
    elif beantwortet:
        kern = _satz(texte, "alles_aktuell")
    else:
        # Keine einzige Quelle hat geantwortet - offline, oder GitHub/PyPI
        # brachen ab. Bis zum 24.09.2026 stand dann trotzdem "alles auf dem
        # Stand" in der ersten Zeile (Durchsicht, U2-7).
        kern = _satz(texte, "keine_antwort" if fehler else "nichts_abfragbar")
    teile = [kern]
    if fehler:
        teile.append(_satz(texte, "nicht_abfragbar", anzahl=fehler))
    if offen:
        teile.append(_satz(texte, "ohne_quelle_anzahl", anzahl=offen))
    return _satz(texte, "kopf", teile=", ".join(teile))
