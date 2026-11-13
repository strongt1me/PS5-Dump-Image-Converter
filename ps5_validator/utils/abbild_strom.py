# -*- coding: utf-8 -*-
"""Ein exFAT-Abbild direkt aus Lesebaum und zstd-Strom - ohne Zwischenordner (Stufe 3, Etappe 3).

Bisher entpackte der Weg ``.exfat`` -> ``.exfat`` mit zstd das ganze Spiel in einen Ordner, packte dort und baute aus dem Ordner das
Abbild. Hier laufen die Quelle (ein Lesebaum, :mod:`spielbaum`) und die Packdateien (:func:`ampr_zstdpack.strom`) als Dateiliste
durch den Schreiber von MkPFS (``iter_exfat_image_liste``) und kommen als Bytes des fertigen Abbilds heraus.

Die Packdateien (Baender und Index) kennt der Schreiber vorab nur nach Name und Groesse (aus dem Messdurchgang); ihre Bytes liefert
der Schreibdurchgang erst, wenn der Schreiber sie braucht. Der Strom kann nur vorwaerts gelesen werden, deshalb muss die Reihenfolge,
in der der Schreiber die Dateien anfordert, die des Stroms sein; :func:`abbild_strom` prueft das, **bevor** das erste Byte kommt.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator

from ps5_validator.utils import ampr_zstdpack as z

Oeffner = Callable[[], Iterator[bytes]]


class StromDateien:
    """Macht aus dem Erzeuger ``strom()`` (``(Name, Bytes)``, Name wechselt von Datei zu Datei) einzelne Dateien.

    Jede Datei hat einen Oeffner; der Oeffner einer Datei darf erst gerufen werden, wenn die davor fertig gelesen sind.
    """

    def __init__(self, erzeuger: Iterator[tuple[str, bytes]], dateien: "list[tuple[str, int]]") -> None:
        self._erzeuger = iter(erzeuger)
        self._reihe = [name for name, _g in dateien]
        self._groessen = dict(dateien)
        self._pos = 0
        self._vorrat: "tuple[str, bytes] | None" = None
        self._zu = False

    def eintraege(self) -> "list[tuple[str, int, Oeffner]]":
        """``(Name, Groesse, Oeffner)`` in der Reihenfolge des Stroms; die Namen liegen im Wurzelordner des Spiels."""
        return [(name, self._groessen[name], self._oeffner(name)) for name in self._reihe]

    def _oeffner(self, name: str) -> Oeffner:
        def lesen() -> Iterator[bytes]:
            if self._pos >= len(self._reihe) or self._reihe[self._pos] != name:
                raise z.ZstdPackFehler("Packdatei %s wird nicht in der Reihenfolge des Stroms gelesen" % name)
            while True:
                if self._vorrat is None:
                    try:
                        self._vorrat = next(self._erzeuger)
                    except StopIteration:
                        break
                gelesen_name, daten = self._vorrat
                if gelesen_name != name:
                    break
                self._vorrat = None
                yield daten
            self._pos += 1
        return lesen

    def schliessen(self) -> None:
        """Beendet den Erzeuger (Faeden, Lesevorlauf); mehrfaches Rufen schadet nicht."""
        if self._zu:
            return
        self._zu = True
        schliessen = getattr(self._erzeuger, "close", None)
        if callable(schliessen):
            schliessen()


def reihenfolge_pruefen(anforderung: Iterable[str], strom_reihe: Iterable[str]) -> None:
    """Die Packdateien muessen in der Reihenfolge angefordert werden, in der der Strom sie liefert.

    ``anforderung`` ist die Reihenfolge, in der der Schreiber alle Dateien liest; nur die Namen aus ``strom_reihe`` zaehlen.
    Zwischen zwei Packdateien duerfen andere Dateien gelesen werden - sie kommen aus dem Lesebaum und nicht aus dem Strom.
    """
    reihe = list(strom_reihe)
    menge = set(reihe)
    gesehen = [rel for rel in anforderung if rel in menge]
    if gesehen != reihe:
        raise z.ZstdPackFehler("Reihenfolge der Packdateien im Abbild (%s) weicht vom Strom (%s) ab" % (
            ", ".join(gesehen[:3]), ", ".join(reihe[:3])))


def abbild_strom(baum: Any, auswahl: "z.Auswahl", messung: "z.Messung", *, iter_liste: Callable[..., Iterator[bytes]],
                 reihenfolge_liste: Callable[[Iterable], "list[str]"], originale_behalten: bool = False, arbeiter: int = 0,
                 abbruch: Callable[[], bool] = lambda: False, fortschritt: "Callable[[float], None] | None" = None,
                 on_layout: "Callable[[int], None] | None" = None) -> Iterator[bytes]:
    """Die Bytes eines exFAT-Abbilds mit den losen Dateien des Baums und den zstd-Packs aus dem Strom.

    ``iter_liste`` und ``reihenfolge_liste`` sind ``mkpfs.exfat_writer.iter_exfat_image_liste`` und ``dateireihenfolge_liste``
    (das Paket ``mkpfs`` liegt nicht im Importpfad, bis das Hauptmodul es einbettet). Ohne ``originale_behalten`` fallen die
    gepackten Dateien weg, wie bei "Originale weglassen"; mit bleiben sie neben den Packs im Abbild.

    ``fortschritt`` bekommt den Anteil des **Strom-Schreibdurchgangs** (0..1), nicht den des Abbilds - dafuer ist ``on_layout``
    mit der Gesamtgroesse und die Zahl der gelieferten Bytes da.
    """
    gepackt = {rel for rel, _g in auswahl.gepackt}
    vorhanden = baum.suchen()
    for rel in vorhanden:
        if z.ist_packname(rel):
            raise z.ZstdPackFehler("ampr_zstd.ausgabe_belegt")
    lose = [(d.rel, d.groesse, d.lesen) for d in baum.dateien() if originale_behalten or d.rel not in gepackt]
    fehlend = [rel for rel in gepackt if rel not in vorhanden]
    if fehlend:
        raise z.ZstdPackFehler("%s fehlt in der Quelle" % fehlend[0])

    dateien = StromDateien(z.strom(baum, auswahl, messung, arbeiter=arbeiter, abbruch=abbruch, fortschritt=fortschritt),
                           messung.dateien())
    try:
        gesamt = lose + dateien.eintraege()
        reihenfolge_pruefen(reihenfolge_liste(gesamt), [name for name, _g in messung.dateien()])
        yield from iter_liste(gesamt, on_layout=on_layout)
    finally:
        dateien.schliessen()
