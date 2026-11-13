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

import os
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


# ---------------------------------------------------------------------------
# Einbau ohne Entpacken: Ueberlagerungsordner und Ansicht
# ---------------------------------------------------------------------------
#: Zeitstempel, den der Schreiber jeder Datei im Abbild gibt (2024-01-01 00:00:00); der ``ampr_emu.index`` traegt ihn ebenso.
FESTER_MTIME = 1704067200


def _kopf(datei: Any, laenge: int = 4) -> bytes:
    erzeuger = datei.lesen(laenge)
    try:
        return next(erzeuger, b"")[:laenge]
    finally:
        erzeuger.close()


def _ziel_pfad(ziel: str, rel: str) -> str:
    wurzel = os.path.normpath(os.path.abspath(ziel))
    voll = os.path.normpath(os.path.join(wurzel, *rel.split("/")))
    if os.path.commonpath([voll, wurzel]) != wurzel:
        raise z.ZstdPackFehler("Pfad liegt ausserhalb des Ordners: %s" % rel)
    return voll


def schatten_fuellen(baum: Any, ziel: str, *, programmdateien: bool = False, abbruch: Callable[[], bool] = lambda: False,
                     fortschritt: "Callable[[int, int], None] | None" = None) -> "tuple[list[str], int]":
    """Legt die Dateien in einen kleinen Ordner, die der Einbau braucht: die Systemschicht (``ampr_zstdpack.bleibt_lose``:
    ``eboot.bin``, Module, ``sce_sys``, ``fakelib*``, ``.ini``) und mit ``programmdateien`` jede Datei mit der Kennung eines
    ELF oder SELF (der Backport patcht auch solche mit anderem Namen).

    Backport, Fake-Signatur, DLC EMU und AMPR EMU arbeiten auf einem Ordner; hier ist es dieser kleine statt eines entpackten
    Spiels. Alles andere bleibt in der Quelle und wird nur gelesen. Rueckgabe: die Pfade der abgelegten Dateien und ihre Bytes.
    """
    from ps5_validator.utils import ps5_backport

    os.makedirs(ziel, exist_ok=True)
    dateien = baum.dateien()
    abgelegt: list[str] = []
    gesamt_bytes = 0
    for nummer, datei in enumerate(dateien, 1):
        if abbruch():
            raise z.ZstdPackFehler("ampr_pack.abgebrochen")
        if fortschritt is not None and not nummer % 512:
            fortschritt(nummer, len(dateien))
        rel = datei.rel
        wanted = z.bleibt_lose(rel)
        if not wanted and programmdateien and datei.groesse >= 4 and not rel.lower().endswith(ps5_backport.SICHERUNGS_ENDUNGEN):
            erster = rel.split("/", 1)[0].lower()
            if erster not in ps5_backport.FAKELIB_ORDNERNAMEN:
                wanted = _kopf(datei) in ps5_backport._KENNUNGEN
        if not wanted:
            continue
        voll = _ziel_pfad(ziel, rel)
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        try:
            with open(voll, "wb") as fh:
                for stueck in datei.lesen():
                    fh.write(stueck)
        except OSError as exc:
            raise z.ZstdPackFehler("%s nicht schreibbar: %s" % (rel, exc)) from exc
        abgelegt.append(rel)
        gesamt_bytes += datei.groesse
    if fortschritt is not None:
        fortschritt(len(dateien), len(dateien))
    return abgelegt, gesamt_bytes


class Ansicht:
    """Das Spiel, wie es nach dem Einbau aussieht: die Quelle, darueber die Dateien des Ueberlagerungsordners.

    Der Einbau aendert Dateien im Ordner (patcht, signiert, ergaenzt Bibliotheken und Index). Die Ansicht liest bei jedem
    :meth:`baum` den Ordner neu und nennt, was seit dem Fuellen dort fehlt, als entfernt.
    """

    def __init__(self, quelle: Any, ordner: str, abgelegt: Iterable[str], ignoriert: "Callable[[str], bool] | None" = None):
        self.quelle = quelle
        self.ordner = os.path.abspath(ordner)
        self.ordner_norm = os.path.normcase(os.path.realpath(self.ordner))
        self.abgelegt = set(abgelegt)
        self._ignoriert = ignoriert

    def baum(self) -> Any:
        from ps5_validator.utils import spielbaum as sb

        ueber = sb.OrdnerBaum(self.ordner, ignoriert=self._ignoriert)
        jetzt = {d.rel for d in ueber.dateien()}
        return sb.UeberlagerBaum(self.quelle, ueber, entfernt=self.abgelegt - jetzt)


def abbild_eintraege(baum: Any, auswahl: "z.Auswahl", messung: "z.Messung",
                     originale_behalten: bool = False) -> "list[tuple[str, int]]":
    """``(Pfad, Groesse)`` jeder Datei des fertigen Abbilds: die losen aus dem Baum, dazu Baender und Index."""
    gepackt = {rel for rel, _g in auswahl.gepackt}
    lose = [(d.rel, d.groesse) for d in baum.dateien() if originale_behalten or d.rel not in gepackt]
    return lose + list(messung.dateien())


def liste_pruefen(exfat_pfad: str, erwartet: "Iterable[tuple[str, int]]", mkpfs_ordner: str = "",
                  ignoriert: "Callable[[str], bool] | None" = None) -> "dict[str, Any]":
    """Liest die Dateiliste des fertigen Abbilds zurueck und vergleicht Pfade und Groessen mit ``erwartet``.

    Rueckgabe wie ``abbild_pruefen.exfat_ruecklesen``: ``fehlen``, ``zuviel``, ``groesse`` (Listen von Pfaden) und ``dateien``.
    Der Inhalt wird hier nicht verglichen - die Packdateien hat der Schreibdurchgang Chunk fuer Chunk gegen die Messung gehalten.
    """
    from ps5_validator.utils import spielbaum as sb

    soll = {rel: groesse for rel, groesse in erwartet if not (ignoriert and any(ignoriert(t) for t in rel.split("/")))}
    with sb.ExfatBaum(exfat_pfad, mkpfs_ordner=mkpfs_ordner) as neu:
        ist = {d.rel: d.groesse for d in neu.dateien()}
    return {
        "dateien": len(ist),
        "fehlen": sorted(set(soll) - set(ist)),
        "zuviel": sorted(set(ist) - set(soll)),
        "groesse": sorted(rel for rel in set(soll) & set(ist) if soll[rel] != ist[rel]),
    }
