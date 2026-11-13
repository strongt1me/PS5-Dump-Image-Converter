# -*- coding: utf-8 -*-
"""Stufenzeile mit Zeiten: die Abschnitte eines Laufs, jeder mit Zustand und Dauer (nach Dump Forge, Nutzerwahl 13.11.2026).

Ein langer Lauf besteht aus Abschnitten (Entpacken, Einbau, Abbild bauen, ...). Bisher stand ihre Dauer erst nach dem
Abschnitt als ``[ZEIT]``-Zeile im Protokoll; waehrend des Laufs sah man nur "Phase 2/3". Hier hat jeder Abschnitt einen
Zustand (wartet, laeuft, fertig, Fehler, uebersprungen) und eine Dauer, und daraus entsteht eine Zeile fuer die Oberflaeche::

    ✓ Entpacken 12:03 · ▶ Einbau 2:10 (zstd-Packen 1:30) · ○ Abbild · gesamt 14:13

**Datengetrieben.** Welche Abschnitte ein Weg hat, steht in ``FOLGEN`` (Name des Wegs -> Liste von Schluesseln) und nicht
im Code der Anzeige. Ein neuer Weg ruft ``registrieren`` auf; ein Abschnitt, der in der Liste fehlt, wird beim ersten
``beginne`` hinten angefuegt. Ein Abschnitt kann einen Eltern-Abschnitt haben: Seine Zeit ist Teil von dessen Zeit und
erscheint hinter dem Eltern-Abschnitt, solange er laeuft (der Einbau enthaelt das zstd-Packen).

**Texte.** Der Schluessel eines Abschnitts ist der des Protokolls (``phase.entpacken``); die kurze Beschriftung der Zeile
steht unter ``stufe.<rest>`` (``stufe.entpacken``) in ``i18n.STRINGS``. Das Modul kennt keine Texte: ``zeile`` bekommt die
Uebersetzung als Funktion.

Fadensicher: Die Arbeitsfaeden melden, der Hauptfaden liest; alles Gemeinsame liegt hinter einem Schloss.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

WARTET = "wartet"
LAEUFT = "laeuft"
FERTIG = "fertig"
FEHLER = "fehler"
UEBERSPRUNGEN = "uebersprungen"

#: Zeichen vor dem Abschnitt, je Zustand.
ZEICHEN = {WARTET: "○", LAEUFT: "▶", FERTIG: "✓", FEHLER: "✗", UEBERSPRUNGEN: "–"}

#: Die Abschnitte je Weg: ``(Schluessel, Eltern-Schluessel oder None)``. Neue Wege tragen sich mit ``registrieren`` ein.
FOLGEN: dict[str, tuple[tuple[str, str | None], ...]] = {
    # .exFAT mit Asset-Pack neu packen: entpacken, einbauen (darin das Packen), neu bauen.
    "exfat_umpacken": (
        ("phase.entpacken", None),
        ("phase.integration", None),
        ("phase.zstd_packen", "phase.integration"),
        ("phase.zstd_pruefen", "phase.integration"),
        ("phase.zstd_uebernehmen", "phase.integration"),
        ("phase.zstd_originale", "phase.integration"),
        ("phase.abbild_bauen", None),
    ),
    # .exFAT mit zstd-Asset-Pack ohne Zwischenordner (Stufe 3): Systemdateien bereitstellen, einbauen (darin das Messen der
    # Packs), das Abbild direkt aus Quelle und Strom schreiben, zurueckpruefen.
    "exfat_strom": (
        ("phase.ueberlagerung", None),
        ("phase.integration", None),
        ("phase.messen", "phase.integration"),
        ("phase.schreiben", None),
        ("phase.pruefen", None),
    ),
}


def registrieren(name: str, stufen: Iterable[str | tuple[str, str | None]]) -> None:
    """Legt die Abschnitte eines Wegs fest (ersetzt eine vorhandene Eintragung gleichen Namens)."""
    FOLGEN[name] = tuple((s, None) if isinstance(s, str) else (s[0], s[1]) for s in stufen)


def kurz_dauer(sekunden: float) -> str:
    """``m:ss``; ab einer Stunde ``h:mm:ss``."""
    gesamt = max(0, int(round(sekunden)))
    if gesamt >= 3600:
        return "%d:%02d:%02d" % (gesamt // 3600, gesamt % 3600 // 60, gesamt % 60)
    return "%d:%02d" % (gesamt // 60, gesamt % 60)


def text_schluessel(schluessel: str) -> str:
    """Der Schluessel der kurzen Beschriftung: ``phase.entpacken`` -> ``stufe.entpacken``."""
    rest = schluessel.split(".", 1)[1] if "." in schluessel else schluessel
    return "stufe." + rest


@dataclass
class Stufe:
    schluessel: str
    eltern: str | None = None
    zustand: str = WARTET
    beginn: float | None = None
    ende: float | None = None


class Stufenfolge:
    """Die Abschnitte eines Laufs mit Zustand und Zeit."""

    def __init__(self, stufen: Sequence[tuple[str, str | None]] = (), uhr: Callable[[], float] = time.monotonic):
        self._uhr = uhr
        self._schloss = threading.RLock()
        self._stufen: dict[str, Stufe] = {}
        self._reihenfolge: list[str] = []
        self.beginn = uhr()
        self.ende: float | None = None
        for schluessel, eltern in stufen:
            self.hinzufuegen(schluessel, eltern)

    @classmethod
    def fuer(cls, name: str, uhr: Callable[[], float] = time.monotonic) -> "Stufenfolge":
        """Die Folge eines eingetragenen Wegs (unbekannter Name: leere Folge, die sich beim Beginnen fuellt)."""
        return cls(FOLGEN.get(name, ()), uhr)

    def hinzufuegen(self, schluessel: str, eltern: str | None = None) -> Stufe:
        with self._schloss:
            vorhanden = self._stufen.get(schluessel)
            if vorhanden is not None:
                return vorhanden
            stufe = Stufe(schluessel, eltern)
            self._stufen[schluessel] = stufe
            self._reihenfolge.append(schluessel)
            return stufe

    def beginne(self, schluessel: str, eltern: str | None = None, ab: float | None = None) -> None:
        """Der Abschnitt laeuft. ``ab``: Zeitpunkt, wenn der Aufrufer ihn schon gemessen hat."""
        with self._schloss:
            stufe = self.hinzufuegen(schluessel, eltern)
            stufe.zustand = LAEUFT
            stufe.beginn = self._uhr() if ab is None else ab
            stufe.ende = None

    def fertig(self, schluessel: str, beginn: float | None = None) -> None:
        """Der Abschnitt ist fertig. ``beginn``: der vom Aufrufer gemessene Anfang (sonst der gemerkte)."""
        self._abschliessen(schluessel, FERTIG, beginn)

    def fehler(self, schluessel: str) -> None:
        self._abschliessen(schluessel, FEHLER, None)

    def uebersprungen(self, schluessel: str) -> None:
        with self._schloss:
            stufe = self.hinzufuegen(schluessel)
            stufe.zustand = UEBERSPRUNGEN
            stufe.beginn = stufe.ende = None

    def _abschliessen(self, schluessel: str, zustand: str, beginn: float | None) -> None:
        with self._schloss:
            stufe = self.hinzufuegen(schluessel)
            if beginn is not None:
                stufe.beginn = beginn
            elif stufe.beginn is None:
                stufe.beginn = self._uhr()
            stufe.ende = self._uhr()
            stufe.zustand = zustand

    def abschliessen_alle(self, erfolg: bool) -> None:
        """Ende des Laufs: Was noch laeuft, endet (``fertig`` bei Erfolg, sonst ``fehler``); der Lauf hat ein Ende."""
        with self._schloss:
            for stufe in self._stufen.values():
                if stufe.zustand == LAEUFT:
                    stufe.zustand = FERTIG if erfolg else FEHLER
                    stufe.ende = self._uhr()
            self.ende = self._uhr()

    def zustand(self, schluessel: str) -> str | None:
        with self._schloss:
            stufe = self._stufen.get(schluessel)
            return stufe.zustand if stufe else None

    def dauer(self, schluessel: str) -> float | None:
        """Sekunden: bei einem laufenden Abschnitt bis jetzt, bei einem beendeten bis zum Ende; sonst None."""
        with self._schloss:
            stufe = self._stufen.get(schluessel)
            if stufe is None or stufe.beginn is None:
                return None
            if stufe.zustand == LAEUFT:
                return max(0.0, self._uhr() - stufe.beginn)
            if stufe.ende is None:
                return None
            return max(0.0, stufe.ende - stufe.beginn)

    def gesamtdauer(self) -> float:
        with self._schloss:
            return max(0.0, (self.ende if self.ende is not None else self._uhr()) - self.beginn)

    def oberste(self) -> list[Stufe]:
        """Die Abschnitte ohne Eltern, in der Reihenfolge der Folge."""
        with self._schloss:
            return [self._stufen[k] for k in self._reihenfolge if self._stufen[k].eltern is None]

    def laufende_kinder(self, schluessel: str) -> list[Stufe]:
        with self._schloss:
            return [s for s in (self._stufen[k] for k in self._reihenfolge)
                    if s.eltern == schluessel and s.zustand == LAEUFT]

    def leer(self) -> bool:
        with self._schloss:
            return not self._stufen

    def zeile(self, uebersetzen: Callable[[str], str], mit_gesamt: str = "") -> str:
        """Die Zeile fuer die Oberflaeche.

        ``uebersetzen`` macht aus einem Schluessel der kurzen Beschriftung den Text. ``mit_gesamt``: Beschriftung vor
        der Gesamtzeit (leer = ohne). Ein wartender Abschnitt hat keine Zeit, ein laufender die bis jetzt.
        """
        teile: list[str] = []
        with self._schloss:
            for stufe in self.oberste():
                if stufe.zustand == UEBERSPRUNGEN:
                    continue
                teil = "%s %s" % (ZEICHEN[stufe.zustand], uebersetzen(text_schluessel(stufe.schluessel)))
                dauer = self.dauer(stufe.schluessel)
                if dauer is not None:
                    teil += " " + kurz_dauer(dauer)
                if stufe.zustand == LAEUFT:
                    kinder = []
                    for kind in self.laufende_kinder(stufe.schluessel):
                        kd = self.dauer(kind.schluessel)
                        kinder.append(uebersetzen(text_schluessel(kind.schluessel))
                                      + (" " + kurz_dauer(kd) if kd is not None else ""))
                    if kinder:
                        teil += " (%s)" % ", ".join(kinder)
                teile.append(teil)
            if mit_gesamt:
                teile.append("%s %s" % (mit_gesamt, kurz_dauer(self.gesamtdauer())))
        return " · ".join(teile)
