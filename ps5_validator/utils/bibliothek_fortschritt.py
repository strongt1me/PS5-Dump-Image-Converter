# -*- coding: utf-8 -*-
"""Der Fortschritt des Suchlaufs der Bibliothek - ohne Oberfläche.

Ein Suchlauf besteht aus Stufen sehr verschiedener Dauer: Ordner durchsuchen,
Angaben lesen, Titelbilder holen, Einbauten prüfen (auf der Konsole zusätzlich
die Konsole finden und ihre Ablageorte absuchen). Dieses Modul rechnet die
laufende Stufe auf **eine** Prozentzahl um und hält die Rückmeldungen aus den
Arbeitsfäden in einem Takt, den die Oberfläche verkraftet. Gezeichnet wird
anderswo (``bibliothek_raster.SuchlaufAnzeige``).

Zwei Entscheidungen, die man hier nachlesen kann statt sie zu erraten:

* **Die Stufen tragen Gewichte**, keine Zeiten. Was eine Stufe wirklich kostet,
  hängt an den Daten: Ein Dump-Ordner liest sich in Millisekunden, ein Abbild auf
  einer kalten Platte in Sekunden. Die Gewichte sind ein Anhalt, der den Balken
  gleichmäßig wandern lässt - kein Versprechen, wann er das Ende erreicht.
* **Der Balken geht nie zurück.** Eine Stufe, deren Umfang erst später feststeht
  (Ordner durchsuchen: wie viele Spiele es gibt, weiß niemand vorher), meldet
  sich als "unbestimmt"; der Balken läuft dann als Laufbalken weiter, und die
  Prozentzahl bleibt, wo sie war. Beim Übergang zur nächsten Stufe springt er
  nicht zurück, auch wenn deren erste Meldung ein kleineres Verhältnis ergäbe.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Sequence

#: Die Stufen des Suchlaufs auf dem Rechner mit ihrem Gewicht (Prozent der Gesamtstrecke).
PC_STUFEN: tuple[tuple[str, float], ...] = (
    ("ordner", 5.0),
    ("angaben", 35.0),
    ("bilder", 40.0),
    ("einbauten", 20.0),
)

#: Dasselbe für die Konsole. Eine Verbindung, viele kleine Antworten: Das Finden der Konsole
#: und das Absuchen der Ablageorte tragen den Anfang, die installierten Titel, Bilder und
#: Einbauten das Ende.
PS5_STUFEN: tuple[tuple[str, float], ...] = (
    ("konsole", 10.0),
    ("ablagen", 15.0),
    ("angaben", 12.0),
    ("kennungen", 8.0),
    ("installiert", 15.0),
    ("bilder", 30.0),
    ("einbauten", 10.0),
)


@dataclass(frozen=True)
class Stand:
    """Was die Anzeige zeigt: Stufe, Prozent und - wenn bekannt - "getan von gesamt"."""

    stufe: str
    prozent: int
    unbestimmt: bool
    getan: int | None = None
    gesamt: int | None = None


class Phasen:
    """Rechnet den Stand der laufenden Stufe auf eine Prozentzahl über alle Stufen um.

    Args:
        stufen: ``[(Name, Gewicht), ...]`` in der Reihenfolge, in der sie laufen. Die Gewichte
            müssen nicht zu 100 summieren - sie werden ins Verhältnis gesetzt.

    Die Klasse ist **nicht** thread-sicher gebaut, aber auch nicht darauf angewiesen: Die
    Seite ruft sie nur im Fensterfaden auf (die Arbeitsfäden melden über ``after``).
    """

    def __init__(self, stufen: Sequence[tuple[str, float]]) -> None:
        if not stufen:
            raise ValueError("ohne Stufen gibt es nichts zu rechnen")
        namen = [str(name) for name, _gewicht in stufen]
        if len(set(namen)) != len(namen):
            raise ValueError("Stufennamen muessen eindeutig sein: %s" % namen)
        gewichte = [float(gewicht) for _name, gewicht in stufen]
        if any(g <= 0 for g in gewichte):
            raise ValueError("Gewichte muessen positiv sein: %s" % gewichte)
        summe = sum(gewichte)
        self._namen = namen
        self._anteile = [g * 100.0 / summe for g in gewichte]
        self._anfang = [sum(self._anteile[:i]) for i in range(len(namen))]
        self._hoechste = 0
        self._aktuell = namen[0]

    @property
    def namen(self) -> tuple[str, ...]:
        return tuple(self._namen)

    def setzen(self, stufe: str, getan: int | None = None, gesamt: int | None = None) -> Stand:
        """Meldet den Stand einer Stufe.

        Alle Stufen davor gelten als erledigt (auch wenn sie nie gemeldet wurden), alle danach
        als nicht begonnen. Ist ``gesamt`` unbekannt oder 0, gilt die Stufe als unbestimmt: Der
        Balken steht am Anfang der Stufe und läuft, die Prozentzahl zeigt der Aufrufer nicht.

        Raises:
            ValueError: Die Stufe gibt es nicht - ein Tippfehler im Namen soll auffallen und
                nicht stumm bei null bleiben.
        """
        try:
            nummer = self._namen.index(stufe)
        except ValueError:
            raise ValueError("unbekannte Stufe %r (gibt es: %s)" % (stufe, self._namen)) from None
        self._aktuell = stufe
        anfang = self._anfang[nummer]
        if gesamt is None or gesamt <= 0:
            roh, unbestimmt = anfang, True
            getan = None
            gesamt = None
        else:
            getan = max(0, min(int(getan or 0), int(gesamt)))
            roh = anfang + self._anteile[nummer] * getan / float(gesamt)
            unbestimmt = False
        # Nie zurück: Eine Stufe, die ihr Verhältnis neu rechnet (gesamt wächst), soll den Balken
        # nicht zucken lassen.
        prozent = max(self._hoechste, min(99, int(roh)))
        self._hoechste = prozent
        return Stand(stufe=stufe, prozent=prozent, unbestimmt=unbestimmt, getan=getan, gesamt=gesamt)

    def fertig(self) -> Stand:
        """Alles erledigt: 100 Prozent."""
        self._hoechste = 100
        return Stand(stufe=self._aktuell, prozent=100, unbestimmt=False)


class Drossel:
    """Lässt Rückmeldungen höchstens alle ``intervall`` Sekunden durch - bis auf die letzte.

    Ein Arbeitsfaden, der je Datei meldet, schickt bei tausend Dateien tausend Aufträge an die
    Hauptschleife; die zeichnet dann nur noch Fortschritt. Die Drossel sitzt im Faden vor dem
    ``after``-Aufruf. Thread-sicher, weil mehrere Arbeitsfäden dieselbe Anzeige füttern können.

    Args:
        intervall: Mindestabstand zweier Meldungen in Sekunden.
        uhr: Zeitquelle - für Tests austauschbar.
    """

    def __init__(self, intervall: float = 0.08, uhr: Callable[[], float] = time.monotonic) -> None:
        self._intervall = float(intervall)
        self._uhr = uhr
        self._letzte: float | None = None
        self._sperre = threading.Lock()

    def darf(self, letzte: bool = False) -> bool:
        """Ist es Zeit für eine Meldung? ``letzte=True`` kommt immer durch (Stufenende)."""
        jetzt = self._uhr()
        with self._sperre:
            if letzte or self._letzte is None or jetzt - self._letzte >= self._intervall:
                self._letzte = jetzt
                return True
            return False
