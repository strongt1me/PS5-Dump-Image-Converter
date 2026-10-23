# -*- coding: utf-8 -*-
"""Erkennt Spiele mit sehr vielen Daten oder Texture-Streaming.

Nutzerauftrag vom 21.10.2026: Bei solchen Spielen sind in einem ``.ffpfsc``/``.ffpfs`` Ruckler moeglich. Vor dem
Erstellen soll deshalb geprueft werden, ob das Backup - gleich in welchem Format - diese Eigenschaften hat, und
gefragt werden, ob trotzdem umgewandelt werden soll.

Was geprueft wird (nur Hinweise, die sich belegen lassen):

* **Menge der Daten:** ab :data:`GROESSE_VIELE_DATEN` (50 GiB).
* **Streaming-Merkmale:** Dateien, die typische Streaming-Engines anlegen (:data:`ENDUNGEN`: ``.ubulk``, ``.ucas``,
  ``.utoc``, ``.streamdb``, ``.resS``, ``.cas``), grosse Dateien mit ``stream`` oder ``texture`` im Namen
  (:data:`NAMENSTEILE`) und Ordner wie ``StreamingAssets`` (:data:`ORDNER`). Sie zaehlen ab
  :data:`GROESSE_MIT_STREAMING` (20 GiB) - ein kleines Spiel mit einer ``.resS`` ist kein Fall.

Wie geprueft wird, haengt am Format: Ein Ordner und eine ``.exfat`` lassen sich ohne Entpacken durchsehen
(:func:`ordner_pruefen`, :func:`durchsehen`), bei ``.ffpfsc``, ``.ffpfs``, ``.ffpkg`` und Paketen bleibt nur die
Dateigroesse (:func:`datei_pruefen`) - bei einer komprimierten Datei ist sie eine **Untergrenze**.

Alle Suchen haben eine Zeitgrenze und stoppen, sobald das Urteil feststeht. Was nicht gemessen wurde, wird nicht
behauptet: ``vollstaendig`` sagt, ob alles gesehen wurde.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

GIB = 1024 ** 3
MIB = 1024 ** 2

#: Ab dieser Menge gilt ein Spiel als datenreich - ohne weiteres Merkmal.
GROESSE_VIELE_DATEN = 50 * GIB
#: Ab dieser Menge zaehlen die Streaming-Merkmale.
GROESSE_MIT_STREAMING = 20 * GIB

#: Dateiendung (klein) -> Engine, die sie fuer gestreamte Daten anlegt.
ENDUNGEN: dict[str, str] = {
    ".ubulk": "Unreal Engine (.ubulk)",
    ".ucas": "Unreal Engine (.ucas)",
    ".utoc": "Unreal Engine (.utoc)",
    ".streamdb": "id Tech (.streamdb)",
    ".ress": "Unity (.resS)",
    ".cas": "Frostbite (.cas)",
}

#: (Namensteil, kleinste Dateigroesse): Grosse Dateien, die schon im Namen sagen, was sie sind.
NAMENSTEILE: tuple[tuple[str, int], ...] = (("stream", 128 * MIB), ("texture", 512 * MIB))

#: Ordnernamen (klein), die auf gestreamte Inhalte deuten.
ORDNER: tuple[str, ...] = ("streamingassets", "texturestreaming", "streaming")

#: Wie viele Fundstellen je Merkmal als Beleg gemerkt werden.
BELEGE_JE_MERKMAL = 2


@dataclass
class Befund:
    """Ergebnis der Pruefung eines Spiels."""

    groesse: int = 0
    #: Alles gesehen? ``False``: Zeitgrenze, Abbruch oder nur die Dateigroesse - die Zahlen sind Untergrenzen.
    vollstaendig: bool = True
    #: Nur die Groesse der Datei, kein Blick hinein (``.ffpfsc``, ``.ffpkg`` ...).
    nur_dateigroesse: bool = False
    #: Merkmal -> Fundstellen (Beispiele).
    merkmale: dict[str, list[str]] = field(default_factory=dict)

    @property
    def viele_daten(self) -> bool:
        return self.groesse >= GROESSE_VIELE_DATEN

    @property
    def streaming(self) -> bool:
        return bool(self.merkmale) and self.groesse >= GROESSE_MIT_STREAMING

    @property
    def auffaellig(self) -> bool:
        """Sind Ruckler zu erwarten? Menge der Daten **oder** Streaming-Merkmal bei nennenswerter Menge."""
        return self.viele_daten or self.streaming

    def gruende(self) -> list[tuple[str, dict[str, object]]]:
        """Die Gruende als ``(Schluessel, Werte)`` fuer die Oberflaeche (Text dort, nicht hier)."""
        gruende: list[tuple[str, dict[str, object]]] = []
        if self.viele_daten:
            gruende.append(("viele_daten", {"groesse": self.groesse, "grenze": GROESSE_VIELE_DATEN}))
        if self.streaming:
            gruende.append(("streaming", {"merkmale": "; ".join(sorted(self.merkmale))}))
        return gruende


class _Sammler:
    """Zaehlt Groesse und Merkmale beim Durchgehen und sagt, wann das Urteil feststeht."""

    def __init__(self) -> None:
        self.befund = Befund()

    def datei(self, name: str, groesse: int, pfad: str) -> None:
        b = self.befund
        b.groesse += max(0, int(groesse))
        klein = name.lower()
        endung = os.path.splitext(klein)[1]
        if endung in ENDUNGEN:
            self._merken(ENDUNGEN[endung], pfad)
        for teil, grenze in NAMENSTEILE:
            if teil in klein and groesse >= grenze:
                self._merken("%s*" % teil, pfad)

    def ordner(self, name: str, pfad: str) -> None:
        if name.lower() in ORDNER:
            self._merken("%s/" % name, pfad)

    def _merken(self, merkmal: str, pfad: str) -> None:
        belege = self.befund.merkmale.setdefault(merkmal, [])
        if len(belege) < BELEGE_JE_MERKMAL:
            belege.append(pfad)

    @property
    def fertig(self) -> bool:
        """Mehr Suchen aendert nichts am Urteil: Die Menge reicht allein, oder Merkmal und Menge liegen vor."""
        return self.befund.auffaellig


def durchsehen(
    wurzel: object,
    auflisten: Callable[[object], Iterable[tuple[str, bool, int, object]]],
    *,
    zeit: float = 8.0,
    abbruch: Callable[[], bool] | None = None,
    uhr: Callable[[], float] = time.monotonic,
) -> Befund:
    """Geht einen Verzeichnisbaum durch.

    Args:
        wurzel: Die Wurzel in der Form, die ``auflisten`` versteht (Pfad, Eintrag ...).
        auflisten: ``f(ordner) -> [(name, ist_ordner, groesse, kind)]``; ``kind`` ist, was fuer den
            Unterordner wieder an ``auflisten`` geht. Ein Fehler beim Lesen eines Ordners ueberspringt ihn
            (``vollstaendig`` wird dann ``False``).
        zeit: Zeitgrenze in Sekunden.
        abbruch: Gibt ``True`` zurueck, wenn die Suche enden soll.
    """
    sammler = _Sammler()
    beginn = uhr()
    stapel: list[tuple[object, str]] = [(wurzel, "")]
    while stapel:
        if sammler.fertig:
            break
        if (abbruch is not None and abbruch()) or uhr() - beginn > zeit:
            sammler.befund.vollstaendig = False
            break
        ordner, vorsatz = stapel.pop()
        try:
            eintraege = list(auflisten(ordner))
        except Exception:  # noqa: BLE001 - ein nicht lesbarer Ordner stoppt die Pruefung nicht
            sammler.befund.vollstaendig = False
            continue
        for name, ist_ordner, groesse, kind in eintraege:
            pfad = "%s%s" % (vorsatz, name)
            if ist_ordner:
                sammler.ordner(name, pfad + "/")
                stapel.append((kind, pfad + "/"))
            else:
                sammler.datei(name, groesse, pfad)
    return sammler.befund


def _ordner_auflisten(pfad: object) -> list[tuple[str, bool, int, object]]:
    ergebnis: list[tuple[str, bool, int, object]] = []
    with os.scandir(str(pfad)) as eintraege:
        for e in eintraege:
            try:
                if e.is_dir(follow_symlinks=False):
                    ergebnis.append((e.name, True, 0, e.path))
                elif e.is_file(follow_symlinks=False):
                    ergebnis.append((e.name, False, e.stat(follow_symlinks=False).st_size, e.path))
            except OSError:
                continue
    return ergebnis


def ordner_pruefen(pfad: str, *, zeit: float = 8.0, abbruch: Callable[[], bool] | None = None,
                   uhr: Callable[[], float] = time.monotonic) -> Befund:
    """Prueft einen Dump-Ordner."""
    return durchsehen(pfad, _ordner_auflisten, zeit=zeit, abbruch=abbruch, uhr=uhr)


def datei_pruefen(pfad: str) -> Befund:
    """Nur die Dateigroesse - fuer ``.ffpfsc``, ``.ffpfs``, ``.ffpkg`` und Pakete.

    Bei einer komprimierten Datei liegt die echte Datenmenge darueber; ``vollstaendig`` ist deshalb ``False``.
    """
    try:
        groesse = os.path.getsize(pfad)
    except OSError:
        groesse = 0
    return Befund(groesse=groesse, vollstaendig=False, nur_dateigroesse=True)


def exfat_pruefen(pfad: str, mkpfs_ordner: str = "", *, zeit: float = 8.0,
                  abbruch: Callable[[], bool] | None = None,
                  uhr: Callable[[], float] = time.monotonic) -> Befund:
    """Prueft eine ``.exfat``-Datei ohne Entpacken (nur die Verzeichnisse werden gelesen).

    Gelingt das Lesen nicht, bleibt die Dateigroesse (:func:`datei_pruefen`).
    """
    import sys

    try:
        if mkpfs_ordner and mkpfs_ordner not in sys.path:
            sys.path.insert(0, mkpfs_ordner)
        from mkpfs.exfat import ExfatReader  # type: ignore[import-not-found]

        from ps5_validator.utils.exfat_gezielt import GezielterZugriff

        with open(pfad, "rb") as fh:
            zugriff = GezielterZugriff(ExfatReader(fh))

            def _auflisten(ordner: object):
                return [(e.name, e.ist_ordner, e.laenge, e) for e in zugriff.auflisten(ordner)]  # type: ignore[arg-type]

            return durchsehen(None, _auflisten, zeit=zeit, abbruch=abbruch, uhr=uhr)
    except Exception:  # noqa: BLE001 - dann zaehlt die Dateigroesse
        return datei_pruefen(pfad)
