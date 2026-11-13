# -*- coding: utf-8 -*-
"""Lesebaum: die Dateien eines Spiels als Liste mit Lesefunktion - ohne sie vorher irgendwohin zu entpacken.

Erste Etappe von "Strom ohne Zwischenordner" (Stufe 3 nach dem Vorbild von Dump Forge, 13.11.2026). Bis dahin entpackt jeder
Weg, der eine ``.exfat`` umbaut, das ganze Spiel in einen Ordner auf dem Ziellaufwerk (151 GB geschrieben, 4-faches Lesen) und
baut daraus das Ergebnis. Ein Lesebaum kennt nur, **was** im Spiel liegt (Pfad, Groesse) und **wie** man es liest; wer ihn
benutzt, braucht keinen Ordner mehr.

Drei Arten:

* :class:`OrdnerBaum` - ein Ordner auf der Platte (wie bisher).
* :class:`ExfatBaum` - eine ``.exfat``-Datei, gelesen mit dem eingebetteten Leser von MkPFS. Jeder Faden bekommt seinen eigenen
  Dateigriff und Leser (der Leser merkt sich nur eine Stelle in der Datei und darf nicht von zwei Faeden zugleich benutzt werden).
* :class:`UeberlagerBaum` - ein Baum, dessen Dateien durch die eines zweiten ersetzt, ergaenzt oder entfernt sind. So bleiben die
  wenigen Dateien, die der Einbau veraendert (Backport, Fake-Signatur, DLC EMU, AMPR-Bibliothek), in einem kleinen Ordner, und
  der Rest kommt weiter aus der Quelle.

Alle drei liefern ``dateien()`` als Liste von :class:`BaumDatei` in fester Reihenfolge (nach Pfad) und ``stempel()``, womit sich
vor dem Ersetzen der Quelle pruefen laesst, ob sie waehrenddessen geaendert wurde (SourceStamp bei Forge).
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator

#: Wie gross ein Stueck ist, das ``lesen`` in einem Zug liefert (hoechstens).
LESE_STUECK = 4 * 1024 * 1024


class BaumFehler(RuntimeError):
    """Ein Lesebaum laesst sich nicht aufbauen oder eine Datei darin nicht lesen."""


@dataclass(frozen=True)
class BaumDatei:
    """Eine Datei im Spiel: Pfad (mit ``/``, ohne fuehrenden Schraegstrich), Groesse und wie man sie liest."""

    rel: str
    groesse: int
    _leser: Callable[[int], Iterator[bytes]]

    def lesen(self, stueck: int = LESE_STUECK) -> Iterator[bytes]:
        """Die Bytes der Datei in Stuecken zu hoechstens ``stueck`` Bytes. Ihre Summe ist genau ``groesse``."""
        gelesen = 0
        for daten in self._leser(max(1, int(stueck))):
            gelesen += len(daten)
            if gelesen > self.groesse:
                raise BaumFehler("%s ist waehrend des Lesens gewachsen" % self.rel)
            yield daten
        if gelesen < self.groesse:
            raise BaumFehler("%s ist kuerzer als gemeldet (%d von %d Bytes)" % (self.rel, gelesen, self.groesse))


class _Baum:
    """Gemeinsames: ``dateien``, ``suchen``, Schliessen."""

    def dateien(self) -> list[BaumDatei]:
        raise NotImplementedError

    def stempel(self) -> tuple:
        raise NotImplementedError

    def suchen(self) -> dict[str, BaumDatei]:
        """Alle Dateien nach Pfad."""
        return {d.rel: d for d in self.dateien()}

    def schliessen(self) -> None:
        """Gibt Dateigriffe frei. Mehrfaches Rufen schadet nicht."""

    def __enter__(self) -> "_Baum":
        return self

    def __exit__(self, *_a: Any) -> None:
        self.schliessen()


class OrdnerBaum(_Baum):
    """Die regulaeren Dateien eines Ordners. Verweise (Symlinks) und Sonderdateien zaehlen nicht, werden aber gemerkt."""

    def __init__(self, wurzel: str, ignoriert: "Callable[[str], bool] | None" = None) -> None:
        self.wurzel = os.path.abspath(wurzel)
        if not os.path.isdir(self.wurzel):
            raise BaumFehler("kein Ordner: %s" % self.wurzel)
        self._ignoriert = ignoriert
        self.uebersprungen: list[str] = []
        self._dateien: "list[BaumDatei] | None" = None
        self._stempel_oeffnen: "tuple | None" = None

    def _leser_fuer(self, voll: str) -> Callable[[int], Iterator[bytes]]:
        def lesen(stueck: int) -> Iterator[bytes]:
            with open(voll, "rb") as fh:
                while True:
                    daten = fh.read(stueck)
                    if not daten:
                        return
                    yield daten
        return lesen

    def dateien(self) -> list[BaumDatei]:
        if self._dateien is not None:
            return self._dateien
        gefunden: list[BaumDatei] = []
        self.uebersprungen = []
        for ordner, unter, namen in os.walk(self.wurzel):
            unter.sort()
            for name in sorted(namen):
                voll = os.path.join(ordner, name)
                rel = os.path.relpath(voll, self.wurzel).replace(os.sep, "/")
                if self._ignoriert is not None and any(self._ignoriert(t) for t in rel.split("/")):
                    continue
                if os.path.islink(voll) or not os.path.isfile(voll):
                    self.uebersprungen.append(rel)
                    continue
                gefunden.append(BaumDatei(rel, os.path.getsize(voll), self._leser_fuer(voll)))
        gefunden.sort(key=lambda d: d.rel)
        self._dateien = gefunden
        # Der Stand beim Oeffnen (= beim ersten Auflisten), gegen den :meth:`unveraendert` spaeter vergleicht.
        self._stempel_oeffnen = self.stempel()
        return gefunden

    def stempel(self) -> tuple:
        """Pfad, Groesse und Aenderungszeit jeder Datei - ein Spiel mit 84.000 Dateien braucht dafuer Sekunden, keine Minuten."""
        zeilen = []
        for d in self.dateien():
            try:
                st = os.stat(os.path.join(self.wurzel, *d.rel.split("/")))
            except OSError:
                zeilen.append((d.rel, -1, -1))
                continue
            zeilen.append((d.rel, st.st_size, st.st_mtime_ns))
        return ("ordner", self.wurzel, tuple(zeilen))

    def unveraendert(self) -> bool:
        """Ob die Dateien noch so sind wie beim ersten Auflisten (Pfad, Groesse, Aenderungszeit); neue oder fehlende Dateien zaehlen mit."""
        if self._stempel_oeffnen is None:
            return True
        # Neu auflisten: eine Datei, die dazugekommen ist, steht nicht in der gemerkten Liste.
        try:
            jetzt = OrdnerBaum(self.wurzel, ignoriert=self._ignoriert)
            jetzt.dateien()                       # merkt den Stand dieses Augenblicks in ``_stempel_oeffnen``
            return jetzt._stempel_oeffnen == self._stempel_oeffnen
        except (OSError, BaumFehler):
            return False


class ExfatBaum(_Baum):
    """Die Dateien in einer ``.exfat``-Datei, gelesen ohne Einhaengen und ohne Entpacken.

    ``mkpfs_ordner`` ist der Ordner, der das Paket ``mkpfs`` enthaelt (Hauptmodul: ``_extract_embedded_mkpfs()``); ohne Angabe
    muss ``mkpfs`` schon importierbar sein.
    """

    def __init__(self, pfad: str, mkpfs_ordner: str = "", ignoriert: "Callable[[str], bool] | None" = None) -> None:
        self.pfad = os.path.abspath(pfad)
        if not os.path.isfile(self.pfad):
            raise BaumFehler("keine Datei: %s" % self.pfad)
        if mkpfs_ordner:
            import sys
            if mkpfs_ordner not in sys.path:
                sys.path.insert(0, mkpfs_ordner)
        try:
            from mkpfs.exfat import ExfatError, ExfatReader     # noqa: PLC0415  # pyright: ignore[reportMissingImports]
        except ImportError as exc:                                 # pragma: no cover - ohne MkPFS gibt es das Programm nicht
            raise BaumFehler("MkPFS nicht gefunden: %s" % exc) from exc
        self._ExfatReader = ExfatReader
        self._ExfatError = ExfatError
        self._ignoriert = ignoriert
        self._lokal = threading.local()
        self._griffe: list[Any] = []
        self._sperre = threading.Lock()
        self._stempel = self._datei_stempel()
        self._dateien: "list[BaumDatei] | None" = None
        self._geschlossen = False

    def _datei_stempel(self) -> tuple:
        st = os.stat(self.pfad)
        return ("exfat", self.pfad, st.st_size, st.st_mtime_ns)

    def _leser(self) -> Any:
        """Der Leser dieses Fadens; der erste Aufruf je Faden oeffnet Datei und liest die FAT."""
        leser = getattr(self._lokal, "leser", None)
        if leser is None:
            if self._geschlossen:
                raise BaumFehler("Lesebaum ist geschlossen")
            fh = open(self.pfad, "rb")
            try:
                leser = self._ExfatReader(fh)
            except Exception:
                fh.close()
                raise
            with self._sperre:
                self._griffe.append(fh)
            self._lokal.leser = leser
        return leser

    def dateien(self) -> list[BaumDatei]:
        if self._dateien is not None:
            return self._dateien
        try:
            eintraege = list(self._leser().iter_files())
        except self._ExfatError as exc:
            raise BaumFehler("exFAT-Abbild nicht lesbar: %s" % exc) from exc
        gefunden: list[BaumDatei] = []
        for eintrag in eintraege:
            rel = eintrag.rel_path
            if self._ignoriert is not None and any(self._ignoriert(t) for t in rel.split("/")):
                continue
            gefunden.append(BaumDatei(rel, int(eintrag.length), self._leser_fuer(eintrag)))
        gefunden.sort(key=lambda d: d.rel)
        self._dateien = gefunden
        return gefunden

    def _leser_fuer(self, eintrag: Any) -> Callable[[int], Iterator[bytes]]:
        def lesen(stueck: int) -> Iterator[bytes]:
            try:
                yield from self._leser().read_file(eintrag, chunk_size=stueck)
            except self._ExfatError as exc:
                raise BaumFehler("%s: %s" % (eintrag.rel_path, exc)) from exc
        return lesen

    def stempel(self) -> tuple:
        """Stand der Abbilddatei **jetzt** (Groesse und Zeit); mit dem beim Oeffnen gemerkten zu vergleichen: :meth:`unveraendert`."""
        return self._datei_stempel()

    def unveraendert(self) -> bool:
        """Ob die Abbilddatei noch so ist wie beim Oeffnen des Baums."""
        try:
            return self._datei_stempel() == self._stempel
        except OSError:
            return False

    def schliessen(self) -> None:
        with self._sperre:
            self._geschlossen = True
            griffe, self._griffe = self._griffe, []
        for fh in griffe:
            try:
                fh.close()
            except OSError:
                pass
        self._lokal = threading.local()


class UeberlagerBaum(_Baum):
    """``basis`` mit Aenderungen: Dateien aus ``ueberlager`` ersetzen oder ergaenzen, ``entfernt`` faellt weg."""

    def __init__(self, basis: _Baum, ueberlager: "_Baum | None" = None, entfernt: Iterable[str] = ()) -> None:
        self.basis = basis
        self.ueberlager = ueberlager
        self.entfernt = frozenset(str(e).replace("\\", "/").strip("/") for e in entfernt)

    def dateien(self) -> list[BaumDatei]:
        ersetzt = self.ueberlager.suchen() if self.ueberlager is not None else {}
        ergebnis = [d for d in self.basis.dateien() if d.rel not in ersetzt and d.rel not in self.entfernt]
        ergebnis.extend(d for rel, d in ersetzt.items() if rel not in self.entfernt)
        ergebnis.sort(key=lambda d: d.rel)
        return ergebnis

    def stempel(self) -> tuple:
        return ("ueberlagert", self.basis.stempel(),
                self.ueberlager.stempel() if self.ueberlager is not None else (), tuple(sorted(self.entfernt)))

    def schliessen(self) -> None:
        self.basis.schliessen()
        if self.ueberlager is not None:
            self.ueberlager.schliessen()


def einordnen(baum: _Baum) -> list[tuple[str, int]]:
    """``(Pfad, Groesse)`` aller Dateien des Baums - die Eingabe fuer ``ampr_zstdpack.auswahl_aus_liste``."""
    return [(d.rel, d.groesse) for d in baum.dateien()]
