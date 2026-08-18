"""Adressen, Einordnung und Zielpfade fuer heruntergeladene PS5-Update-Pakete.

Reine Logik ohne GUI- und Netzbezug, damit sie fuer sich pruefbar bleibt; das
Herunterladen selbst liegt in der Oberflaeche.

Hintergrund: Die Update-Pakete liegen auf Sonys Auslieferungsnetz unter einer
Adresse dieser Form (am 16.08.2026 an einer echten Datei nachgemessen)::

    http://gst.prod.dl.playstation.net/gst/prod/00/PPSA19015_00/app/pkg/5/
        f_2f6a8429bc090a765d66f5d3d46b0db710967ef4b40c57005ba8e5ce4b6abff4/
        UP8016-PPSA19015_00-0489895718491618.pkg

Der Abruf laeuft ueber einfaches HTTP, ohne Anmeldung, und der Server
beantwortet Bereichsanfragen (``Accept-Ranges: bytes``) - Downloads lassen sich
also fortsetzen. Der Abschnitt ``f_<64 Hex>`` ist undurchsichtig und entsteht
erst beim Aufloesen der Adresse; dieser Schritt bleibt bewusst beim Nutzer.
"""
from __future__ import annotations

import os
import re
from urllib.parse import urlparse

#: Hosts, von denen Pakete angenommen werden.
ERLAUBTE_HOSTS: tuple[str, ...] = (
    "gst.prod.dl.playstation.net",
    "gst.prod.dl.playstation.com",
)

#: Zielordner unterhalb des gewaehlten Speicherorts.
ORDNER_UPDATE = "PS5 Spiele Updates"
ORDNER_PATCH = "Patches"

ART_UPDATE = "update"
ART_PATCH = "patch"

# UP8016-PPSA19015_00-0489895718491618
_CONTENT_ID_RE = re.compile(r"([A-Z]{2}\d{4})-((?:PPSA|CUSA|PLAS)\d{5})_(\d{2})-([A-Z0-9]{16})")


class DownloadAdresseUngueltig(ValueError):
    """Die Adresse gehoert nicht zu einem PS5-Update-Paket."""


def parse_pkg_url(url: str) -> dict[str, str]:
    """Zerlegt eine Paketadresse in ihre verwertbaren Bestandteile.

    Args:
        url: Vollstaendige Adresse aus dem Browser.

    Returns:
        Dict mit ``url``, ``host``, ``dateiname``, ``content_id``, ``title_id``,
        ``region_code`` und ``label``.

    Raises:
        DownloadAdresseUngueltig: Kein bekannter Host oder kein .pkg mit
            auswertbarer Content-ID im Namen.
    """
    text = str(url or "").strip().strip('"').strip("'")
    zerlegt = urlparse(text)
    if zerlegt.scheme.lower() not in ("http", "https") or not zerlegt.netloc:
        raise DownloadAdresseUngueltig("Das ist keine http(s)-Adresse.")
    # Jede Pruefung mit eigener Meldung, damit beim Einfuegen klar wird, woran
    # es lag - "endet nicht auf .pkg" bei einer fremden Domain waere irrefuehrend.
    host = zerlegt.netloc.split("@")[-1].split(":")[0].lower()
    if host not in ERLAUBTE_HOSTS:
        raise DownloadAdresseUngueltig(
            f"Unerwarteter Host: {host}. Erwartet wird {ERLAUBTE_HOSTS[0]}."
        )
    dateiname = zerlegt.path.rsplit("/", 1)[-1]
    if not dateiname.lower().endswith(".pkg"):
        raise DownloadAdresseUngueltig("Die Adresse endet nicht auf eine .pkg-Datei.")
    inhalt = _CONTENT_ID_RE.search(dateiname)
    if not inhalt:
        raise DownloadAdresseUngueltig(
            "Im Dateinamen steckt keine auswertbare Content-ID."
        )
    return {
        "url": text,
        "host": host,
        "dateiname": dateiname,
        "content_id": inhalt.group(0),
        "region_code": inhalt.group(1),
        "title_id": inhalt.group(2),
        "label": inhalt.group(4),
    }


def ist_pkg_url(url: str) -> bool:
    """True, wenn :func:`parse_pkg_url` die Adresse annehmen wuerde."""
    try:
        parse_pkg_url(url)
    except DownloadAdresseUngueltig:
        return False
    return True


def art_bestimmen(ist_neueste: bool | None) -> str:
    """Ordnet ein Paket als Update oder Patch ein.

    Die neueste Version eines Titels gilt als Update, jede aeltere als Patch.
    Ist die Lage unbekannt (kein Abgleich moeglich), wird als Update behandelt -
    lieber im Hauptordner als in einer falschen Ablage.
    """
    return ART_PATCH if ist_neueste is False else ART_UPDATE


def zielordner(basis: str, art: str) -> str:
    """Vollstaendiger Zielordner fuer eine Art unterhalb des Speicherorts."""
    unter = ORDNER_PATCH if art == ART_PATCH else ORDNER_UPDATE
    return os.path.join(str(basis or ""), unter)


def zielpfad(basis: str, art: str, dateiname: str) -> str:
    """Vollstaendiger Zielpfad einer Datei."""
    return os.path.join(zielordner(basis, art), dateiname)


def teildatei(zielpfad_: str) -> str:
    """Pfad der Teildatei, in die waehrend des Ladens geschrieben wird."""
    return zielpfad_ + ".teil"


def bereits_vorhanden(basis: str, dateiname: str) -> str:
    """Sucht eine fertige Datei in beiden Zielordnern.

    Returns:
        Der gefundene Pfad oder ein leerer String.
    """
    for art in (ART_UPDATE, ART_PATCH):
        pfad = zielpfad(basis, art, dateiname)
        if os.path.isfile(pfad):
            return pfad
    return ""


def vorhandene_dateien(basis: str) -> list[dict[str, str]]:
    """Listet die bereits abgelegten Pakete beider Ordner.

    Ueberspringt Teildateien und alles, was keine auswertbare Content-ID traegt.
    """
    gefunden: list[dict[str, str]] = []
    for art in (ART_UPDATE, ART_PATCH):
        ordner = zielordner(basis, art)
        try:
            eintraege = sorted(os.listdir(ordner))
        except OSError:
            continue
        for name in eintraege:
            if not name.lower().endswith(".pkg"):
                continue
            pfad = os.path.join(ordner, name)
            if not os.path.isfile(pfad):
                continue
            inhalt = _CONTENT_ID_RE.search(name)
            if not inhalt:
                continue
            try:
                groesse = os.path.getsize(pfad)
            except OSError:
                groesse = 0
            gefunden.append({
                "dateiname": name,
                "pfad": pfad,
                "art": art,
                "content_id": inhalt.group(0),
                "title_id": inhalt.group(2),
                "bytes": str(groesse),
            })
    return gefunden


def eingehende_urls(text: str) -> list[str]:
    """Zieht alle brauchbaren Paketadressen aus einem Textblock.

    Erlaubt das Einfuegen mehrerer Zeilen auf einmal; Reihenfolge bleibt
    erhalten, Doppelte fallen weg.
    """
    gesehen: set[str] = set()
    ergebnis: list[str] = []
    for stueck in re.split(r"[\s,;]+", str(text or "")):
        stueck = stueck.strip().strip('"').strip("'")
        if not stueck or stueck in gesehen:
            continue
        if ist_pkg_url(stueck):
            gesehen.add(stueck)
            ergebnis.append(stueck)
    return ergebnis
