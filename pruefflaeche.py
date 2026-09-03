# -*- coding: utf-8 -*-
"""Reicht der Bildschirm ueberhaupt fuer eine Layoutmessung?

Am 01.09.2026 fielen im Bauplan-Lauf zwoelf Pruefungen aus fuenf
Dateien durch - mit zwoelf verschiedenen Meldungen: "Backport ist 146
px zu schmal", "console_frame ohne Eckbilder", "bei 1080 px passt
alles ohne Rollen", "80 Mal ohne Hintergrundausschnitt gezeichnet".
Eine einzige Ursache: Der Rechner von GitHub hat einen Bildschirm von
1024x768.

Das Programm verlangt mindestens 1245x700 (WINDOW_MIN_WIDTH und
WINDOW_MIN_HEIGHT) und laesst um jedes Fenster einen Rand von 40 bzw.
80 Pixeln frei (``_fenster_auf_inhalt_wachsen``). 1024 - 40 = 984, und
genau 984 stand in der Meldung; 768 - 80 = 688, und genau 688 stand in
den beiden anderen. Auf so einem Schirm laesst sich das kleinste vom
Programm unterstuetzte Fenster nicht einmal darstellen.

Was eine Layoutmessung dort findet, sagt weder ueber das Programm noch
ueber einen Fehler etwas aus - sie misst einen Zustand, den es im
Betrieb nicht gibt. Deshalb wird sie uebersprungen statt als Fehler
gemeldet.

**Uebersprungen, nicht entfernt.** Auf einem gewoehnlichen
Arbeitsplatz laufen alle zwoelf weiter und finden weiter, wofuer sie
geschrieben wurden. Und gezielt statt klassenweise: Die fuenf Klassen
tragen zusammen 35 Pruefungen: 23 davon laufen auf dem kleinen Schirm
einwandfrei durch und sollen das auch weiterhin tun.

**Was hier bewusst NICHT gemessen wird.** Naheliegend waere: Masse
setzen und nachsehen, ob sie angekommen sind. Das taugt nicht, am
01.09.2026 nachgemessen:

* Ein zurueckgezogenes Fenster (``withdraw``) meldet ueberhaupt keine
  neuen Masse - ``winfo_width`` bleibt auf dem letzten sichtbaren
  Wert stehen. Genau so laeuft test_kartenzeilen.py.
* Ein sichtbares bekommt auch auf einem grossen Schirm weniger als
  verlangt: 1900 angefordert, 1540 bekommen - ohne dass das den
  Pruefungen etwas ausmacht. Ein Vergleich "verlangt gegen bekommen"
  wuerde also gerade dort ueberspringen, wo alles in Ordnung ist.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

#: Der Rand, den das Programm um jedes Fenster laesst. Steht in
#: ``_fenster_auf_inhalt_wachsen`` als ``winfo_screenwidth() - 40``
#: bzw. ``winfo_screenheight() - 80``. test_pruefflaeche.py sieht
#: nach, dass die beiden Zahlen dort noch so stehen - abgeschriebene
#: Zahlen laufen sonst irgendwann auseinander.
RAND_BREIT = 40
RAND_HOCH = 80

MONOLITH = Path(__file__).with_name("PS5ImageConverter_Pro_FINAL_revised.py")

_mindestmasse: tuple[int, int] | None = None


def mindestmasse() -> tuple[int, int]:
    """WINDOW_MIN_WIDTH und WINDOW_MIN_HEIGHT - aus dem Programm gelesen.

    Nicht abgeschrieben: Die beiden Werte wurden schon einmal
    heraufgesetzt (1230 -> 1245), und eine Pruefung, die die alte Zahl
    traegt, faellt das nicht auf.
    """
    global _mindestmasse
    if _mindestmasse is None:
        quelle = MONOLITH.read_text(encoding="utf-8", errors="replace")
        werte = []
        for name in ("WINDOW_MIN_WIDTH", "WINDOW_MIN_HEIGHT"):
            treffer = re.search(r"^%s\s*=\s*(\d+)" % name, quelle, re.M)
            if treffer is None:                        # pragma: no cover
                raise AssertionError("%s steht nicht mehr im Programm."
                                     % name)
            werte.append(int(treffer.group(1)))
        _mindestmasse = (werte[0], werte[1])
    return _mindestmasse


def deckel(fenster) -> tuple[int, int]:
    """Die Grenze, die das Programm seinen Fenstern selbst zieht."""
    return (fenster.winfo_screenwidth() - RAND_BREIT,
            fenster.winfo_screenheight() - RAND_HOCH)


def reicht(fenster) -> tuple[bool, str]:
    """Passt das kleinste unterstuetzte Fenster auf diesen Schirm?"""
    frei_b, frei_h = deckel(fenster)
    soll_b, soll_h = mindestmasse()
    if frei_b >= soll_b and frei_h >= soll_h:
        return True, ""
    return False, (
        "Bildschirm %dx%d - abzueglich des Randes, den das Programm "
        "laesst, bleiben %dx%d. Das kleinste Fenster, das es kennt, "
        "misst %dx%d. Eine Layoutmessung waere hier ohne Aussage."
        % (fenster.winfo_screenwidth(), fenster.winfo_screenheight(),
           frei_b, frei_h, soll_b, soll_h))


def sonst_ueberspringen(fenster) -> None:
    """In setUp oder am Anfang einer Pruefung aufrufen."""
    ok, grund = reicht(fenster)
    if not ok:
        raise unittest.SkipTest(grund)


def passt_sonst_ueberspringen(fenster, breite: int, hoehe: int,
                              name: str = "") -> None:
    """Fuer Fenster, die sich ihre Masse selbst suchen.

    Nicht der Bildschirm entscheidet, sondern die Grenze aus
    ``_fenster_auf_inhalt_wachsen``: Was darueber hinausgeht, kann das
    Programm gar nicht darstellen - dann misst die Pruefung die
    Grenze und nicht das Fenster.
    """
    frei_b, frei_h = deckel(fenster)
    if breite <= frei_b and hoehe <= frei_h:
        return
    raise unittest.SkipTest(
        "%s braucht %dx%d, auf diesem Bildschirm sind hoechstens %dx%d "
        "moeglich - das Programm deckelt selbst darauf."
        % (name or "Das Fenster", breite, hoehe, frei_b, frei_h))
