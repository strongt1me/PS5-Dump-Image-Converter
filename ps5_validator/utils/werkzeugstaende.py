# -*- coding: utf-8 -*-
"""Stand der mitgelieferten Fremdwerkzeuge: Bestand, Doku und Rueckstand.

Zwei Teile, bewusst getrennt:

* **Ohne Netz** (laeuft in jedem Diagnosebericht mit): Liegt zu jeder Datei in
  ``helloworld/`` eine Zeile in ``THIRD_PARTY_LICENSES.md`` - und umgekehrt?
  Am 17.09.2026 fielen dabei drei Fehler auf, die niemandem aufgefallen waren:
  Die Tabelle nannte ``ps5upload_v5.2.1.elf``, im Ordner lag
  ``ps5upload-5.15.0.elf``; ``shadowmountplus_v1.7_Beta6.elf`` trug eine
  Fassungsbezeichnung, die es beim Autor nie gab; und fuenf Dateien fehlten in
  der Tabelle ganz. Solche Abweichungen findet nur ein Vergleich, kein Blick.

* **Mit Netz** (nur auf ausdruecklichen Wunsch, nie von selbst): Die Fassungen
  gegen eine oeffentliche Liste halten. Diese Datei rechnet nur - **geholt**
  wird die Liste an genau einer Stelle im Hauptmodul, hinter einem eigenen
  Schalter. So bleibt der Grundsatz gewahrt, dass ein Diagnoselauf nicht
  stillschweigend ins Netz geht.

Die Liste stammt von ``itsPLK/ps5-payloads-mirror`` (``payloads.json``): Sie
nennt je Payload Name, Dateiname, Fassung, Pruefsumme und die Originalquelle -
auch fuer Projekte, die GitHub verlassen haben.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.request

logger = logging.getLogger(__name__)

#: Woher die Liste kommt, wenn jemand ausdruecklich danach fragt.
SPIEGEL_ADRESSE = ("https://raw.githubusercontent.com/itsPLK/"
                   "ps5-payloads-mirror/main/payloads.json")

#: Fassung aus einem Dateinamen: "elfldr-ps5_v0.26.elf" -> "0.26",
#: "ps5upload-5.28.0.elf" -> "5.28.0", "shadowmountplus_v1.7alpha13fix1.elf"
#: -> "1.7alpha13fix1". Was keine Ziffernfolge traegt, hat eben keine.
_FASSUNG = re.compile(r"[-_]v?(\d+(?:\.\d+)+[0-9a-z.]*)", re.IGNORECASE)

#: Namen, die der Spiegel anders schreibt als unser Ordner (Spiegel -> unser).
#: Am 17.09.2026 an der wirklichen Liste abgelesen, nicht geraten.
_GLEICHSETZUNG = {
    "elfldr": "elfldrps5",
    "ftpsrv": "ftpsrvps5",
    "klogsrv": "klogsrvps5",
    "websrv": "websrvps5",
    "zftpd": "zftpdps5",
    "ps5webfilemanager": "webfilemgr",
}

#: Woerter hinter der Fassung, die nichts unterscheiden ("_Beta", "_Beta2").
#: Alles andere dahinter (``-dr``, ``-ng``, ``-zhttp``) gehoert zur Kennung:
#: Es sind eigene Reihen, und ihre Nummern sind nicht vergleichbar.
_RAUSCHEN = frozenset({"beta", "final", "release", "stable"})


def fassung_aus_name(dateiname: str) -> str:
    """Die Fassung aus einem Dateinamen, oder ein leerer Text."""
    treffer = _FASSUNG.search(os.path.splitext(str(dateiname or ""))[0])
    return treffer.group(1).rstrip(".") if treffer else ""


def kennung_aus_name(dateiname: str) -> str:
    """Der Name ohne Fassung und Trennzeichen - zum Vergleichen.

    Was **hinter** der Fassung steht, gehoert dazu: ``kstuff_lite_v1.2-dr``
    ist eine andere Reihe als ``kstuff_lite_v1.10``, und
    ``ftpsrv-ps5_v1.15-ng`` eine andere als ``ftpsrv-ps5_v0.21``. Ohne diese
    Unterscheidung meldete der erste Lauf am 17.09.2026 die dr-Fassung 1.2 als
    veraltet gegenueber 1.10 - zwei Projekte, deren Nummern nichts miteinander
    zu tun haben. Ein blosses ``_Beta`` unterscheidet dagegen nichts und faellt
    weg.

    Was danach zu keinem Eintrag der Liste passt, wird schlicht nicht
    verglichen - lieber nichts sagen als das Falsche.
    """
    stamm = os.path.splitext(str(dateiname or ""))[0]
    treffer = _FASSUNG.search(stamm)
    vorne = stamm[:treffer.start()] if treffer else stamm
    hinten = stamm[treffer.end():] if treffer else ""
    teile = [t for t in re.split(r"[^0-9A-Za-z]+", hinten) if t]
    rest = "".join(t for t in teile
                   if re.sub(r"\d+$", "", t.lower()) not in _RAUSCHEN)
    klein = re.sub(r"[^a-z0-9]", "", (vorne + rest).lower())
    return _GLEICHSETZUNG.get(klein, klein)


def payloads_lesen(ordner: str) -> dict[str, str]:
    """Alle ``.elf`` eines Ordners als ``{Dateiname: Fassung}``.

    Returns:
        Leeres Woerterbuch, wenn der Ordner fehlt oder nicht lesbar ist -
        der Bericht sagt das an anderer Stelle, hier wird nichts erfunden.
    """
    try:
        namen = [n for n in os.listdir(str(ordner or ""))
                 if n.lower().endswith(".elf")]
    except OSError as exc:
        logger.debug("Payload-Ordner nicht lesbar (%s): %s", ordner, exc)
        return {}
    return {name: fassung_aus_name(name) for name in sorted(namen)}


#: Ueberschrift des Abschnitts, in dem die Nutzlasten stehen.
PAYLOAD_ABSCHNITT = "## Payloads im Ordner"


def dokumentierte_dateien(lizenzdatei: str,
                          abschnitt: str = PAYLOAD_ABSCHNITT) -> set[str]:
    """Welche ``.elf`` nennt THIRD_PARTY_LICENSES.md im Payload-Abschnitt?

    Gelesen wird, was in Rueckstrichen steht (``` `name.elf` ```) - die
    Tabelle schreibt jeden Dateinamen so.

    **Nur dieser eine Abschnitt.** Ueber das ganze Dokument gelesen faellt
    sonst jede ELF-Datei mit hinein, die anderswo erwaehnt wird: Der erste
    Lauf am 17.09.2026 meldete ``ps5-backpork.elf`` als fehlend, und die
    steckt in der Danksagung und liegt in ``Backport_Fakelibs/7/fakelib/``.
    Ein Waechter, der Falsches meldet, wird nach dem zweiten Mal ignoriert.

    Fehlt die Ueberschrift, wird nichts geraten: Das Ergebnis ist leer, und
    der Aufrufer meldet den Abgleich als nicht moeglich.
    """
    try:
        with open(str(lizenzdatei), "r", encoding="utf-8") as datei:
            text = datei.read()
    except OSError as exc:
        logger.debug("Lizenzdatei nicht lesbar (%s): %s", lizenzdatei, exc)
        return set()
    anfang = text.find(abschnitt)
    if anfang < 0:
        logger.debug("Abschnitt %r fehlt in %s", abschnitt, lizenzdatei)
        return set()
    ende = text.find("\n## ", anfang + len(abschnitt))
    ausschnitt = text[anfang:ende if ende > 0 else len(text)]
    return set(re.findall(r"`([^`]+\.elf)`", ausschnitt))


def bestand_abgleichen(payload_ordner: str, lizenzdatei: str) -> dict[str, list[str]]:
    """Ordner gegen Lizenzdatei - beides muss dasselbe sagen.

    Returns:
        ``{"ohne_zeile": [...], "ohne_datei": [...]}`` - Dateien ohne Eintrag
        und Eintraege ohne Datei, beide sortiert.
    """
    vorhanden = set(payloads_lesen(payload_ordner))
    genannt = dokumentierte_dateien(lizenzdatei)
    return {
        "ohne_zeile": sorted(vorhanden - genannt),
        "ohne_datei": sorted(genannt - vorhanden),
    }


def _stueckeln(fassung: str) -> tuple:
    """Eine Fassung in vergleichbare Teile zerlegen (Zahlen als Zahlen)."""
    teile: list = []
    for stueck in re.split(r"[.\-_]", str(fassung or "")):
        for wort in re.findall(r"\d+|[a-zA-Z]+", stueck):
            teile.append(int(wort) if wort.isdigit() else wort.lower())
    return tuple(teile)


def vergleiche(unsere: str, ihre: str) -> str:
    """Wie stehen zwei Fassungen zueinander?

    Returns:
        ``"gleich"``, ``"aelter"``, ``"neuer"`` oder ``"unklar"``. Unklar
        heisst: nicht vergleichbar (etwa ``1.7alpha13fix1`` gegen ``1.6``
        mit unterschiedlichem Aufbau) - dann wird nichts behauptet.
    """
    a, b = _stueckeln(unsere), _stueckeln(ihre)
    if not a or not b:
        return "unklar"
    if a == b:
        return "gleich"
    for links, rechts in zip(a, b):
        if links == rechts:
            continue
        if isinstance(links, int) and isinstance(rechts, int):
            return "aelter" if links < rechts else "neuer"
        return "unklar"
    return "aelter" if len(a) < len(b) else "neuer"


def rueckstaende(payloads: dict[str, str],
                 liste: list) -> list[tuple[str, str, str, str]]:
    """Welche mitgelieferte Nutzlast ist aelter als die der Liste?

    Args:
        payloads: Ergebnis von :func:`payloads_lesen`.
        liste: Die bereits geholten Eintraege der Spiegelliste (JSON).

    Returns:
        Je Rueckstand ``(Dateiname, unsere Fassung, neueste Fassung, Quelle)``.
        Nur eindeutige Faelle - wo der Vergleich unklar bleibt, steht nichts.
    """
    nach_kennung: dict[str, dict] = {}
    for eintrag in liste or []:
        if not isinstance(eintrag, dict):
            continue
        for feld in ("filename", "name"):
            kennung = kennung_aus_name(str(eintrag.get(feld) or ""))
            if kennung and kennung not in nach_kennung:
                nach_kennung[kennung] = eintrag
    befunde: list[tuple[str, str, str, str]] = []
    for datei, unsere in sorted(payloads.items()):
        eintrag = nach_kennung.get(kennung_aus_name(datei))
        if not eintrag or not unsere:
            continue
        ihre = str(eintrag.get("version") or "").lstrip("vV")
        if vergleiche(unsere, ihre) == "aelter":
            befunde.append((datei, unsere, ihre,
                            str(eintrag.get("source") or "")))
    return befunde


def spiegel_holen(adresse: str = SPIEGEL_ADRESSE, zeitgrenze: float = 20.0) -> list:
    """Holt die Liste - **nur** aus einem ausdruecklichen Aufruf heraus.

    Kein Diagnoselauf und kein Programmstart ruft das von selbst. Die
    Entscheidung, ins Netz zu gehen, trifft der Anwender an der
    Kommandozeile; dieselbe Regel gilt fuer den Metadaten-Nachschlag.

    Raises:
        OSError: Wenn die Liste nicht erreichbar oder nicht lesbar ist.
    """
    with urllib.request.urlopen(adresse, timeout=zeitgrenze) as antwort:
        roh = antwort.read().decode("utf-8", "replace")
    try:
        daten = json.loads(roh)
    except ValueError as exc:
        raise OSError("Liste nicht lesbar: %s" % exc) from exc
    return daten if isinstance(daten, list) else []
