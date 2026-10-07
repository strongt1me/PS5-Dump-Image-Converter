# -*- coding: utf-8 -*-
"""Gesamtfortschritt und Restzeit fuer „PS4 PKG -> ffpfsc/exFAT“.

Bis v1.9.64 zeigte das Fenster nur den Fortschritt des **gerade laufenden Teilschritts**
(Entpacken, Zusammenfuehren, Packen ...): Der Balken lief mehrfach von 0 bis 100, und eine
Restzeit gab es nicht. PS4 FFPFSC 0.2.9 (GPL-3.0-or-later, ``gui.py``/``gui_model.py``)
legt dagegen alle fuenf Stufen eines Baus auf **eine** Skala - Entpacken 2-30 %,
Zusammenfuehren 30-55 %, Packen 55-88 %, Pruefen 88-96 %, Abschluss 96-100 % - und schaetzt
die Restzeit aus der verstrichenen Zeit. Dieses Modul uebernimmt die Aufteilung (aus der
GPL-Quelle, daher die Herkunftsangabe) und die Rechnung, ohne Oberflaeche.

Ein Bau mit mehreren Spielen (Warteschlange) geht ueber ``spiel_nr``/``spiel_gesamt`` in die
Gesamtprozent ein: jedes fertige Spiel zaehlt 100 %.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

#: Anfang jeder Stufe auf der Gesamtskala (Stufe -> Prozent). Quelle: PS4 FFPFSC 0.2.9, gui.py.
STUFEN_START = {1: 2.0, 2: 30.0, 3: 55.0, 4: 88.0, 5: 96.0}
#: Breite der Stufen, in denen das Werkzeug Zwischenstaende meldet.
BREITE_ENTPACKEN = 28.0       # 2 -> 30
BREITE_ZUSAMMEN = 25.0        # 30 -> 55
BREITE_PACKEN = 33.0          # 55 -> 88
BREITE_PRUEFEN = 8.0          # 88 -> 96
ABSCHLUSS = 99.0

#: Das Werkzeug schreibt „stage 3/5: ...“ ins Protokoll (pipeline.py, build_game).
_STUFE = re.compile(r"\bstage (\d+)/(\d+):")

#: Frueheste Schaetzung: darunter ist die Hochrechnung reines Raten.
MIN_PROZENT_FUER_SCHAETZUNG = 3.0
MIN_SEKUNDEN_FUER_SCHAETZUNG = 5.0


def stufe_aus_zeile(text: str) -> "tuple[int, int] | None":
    """(Stufe, Gesamtstufen) aus einer Protokollzeile, sonst ``None``."""
    treffer = _STUFE.search(text or "")
    return (int(treffer.group(1)), int(treffer.group(2))) if treffer else None


def dauer_text(sekunden: float) -> str:
    """``mm:ss`` bzw. ``h:mm:ss``; negative Werte zaehlen als 0."""
    gesamt = max(0, int(sekunden))
    stunden, rest = divmod(gesamt, 3600)
    minuten, sek = divmod(rest, 60)
    return "%d:%02d:%02d" % (stunden, minuten, sek) if stunden else "%02d:%02d" % (minuten, sek)


def rest_sekunden(verstrichen: float, prozent: float) -> "float | None":
    """Geschaetzte Restzeit aus dem bisherigen Tempo; ``None``, solange die Schaetzung nichts taugt."""
    if prozent >= 100.0:
        return 0.0
    if prozent < MIN_PROZENT_FUER_SCHAETZUNG or verstrichen < MIN_SEKUNDEN_FUER_SCHAETZUNG:
        return None
    return verstrichen * (100.0 - prozent) / prozent


def _verhaeltnis(daten: dict) -> float:
    try:
        aktuell = float(daten.get("current", 0) or 0)
        gesamt = float(daten.get("total", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, aktuell / gesamt)) if gesamt > 0 else 0.0


@dataclass
class Stand:
    """Was die Anzeige zeigen soll."""
    prozent: float            #: Gesamt ueber alle Spiele, 0-100
    stufe: int                #: 0 = noch keine gemeldet
    stufen_gesamt: int
    teil: str                 #: Name des Teilschritts (scope/phase des Werkzeugs), "" wenn keiner
    teil_prozent: int         #: Fortschritt des Teilschritts, 0-100 (nur wenn bekannt)
    verstrichen: float
    rest: "float | None"


class Gesamtfortschritt:
    """Haelt den Stand eines Baus (ein oder mehrere Spiele) und rechnet Gesamtprozent und Restzeit.

    Die Uhr laeuft ab :meth:`__init__`; ``jetzt`` ist austauschbar (Tests).
    """

    def __init__(self, spiel_gesamt: int = 1, jetzt=time.monotonic) -> None:
        self._jetzt = jetzt
        self.beginn = jetzt()
        self.spiel_gesamt = max(1, int(spiel_gesamt))
        self.spiel_nr = 0          # 0-basiert: das laufende Spiel
        self.stufe = 0
        self.stufen_gesamt = 5
        self.teil = ""
        self.teil_prozent = 0
        self._lokal = 0.0          # Fortschritt innerhalb des laufenden Spiels, 0-100

    # -- Eingaben ----------------------------------------------------------------
    def naechstes_spiel(self) -> None:
        """Das laufende Spiel ist fertig; das naechste beginnt bei 0."""
        self.spiel_nr = min(self.spiel_nr + 1, self.spiel_gesamt - 1)
        self.stufe = 0
        self.teil = ""
        self.teil_prozent = 0
        self._lokal = 0.0

    def zeile(self, text: str) -> bool:
        """Liest eine Protokollzeile; ``True``, wenn sie eine neue Stufe meldete."""
        gefunden = stufe_aus_zeile(text)
        if gefunden is None:
            return False
        self.stufe, self.stufen_gesamt = gefunden
        self.teil, self.teil_prozent = "", 0
        # Die Stufe setzt nur nach oben: ein verspaeteter Zwischenstand der Vorstufe darf nicht zurueckspringen.
        self._lokal = max(self._lokal, STUFEN_START.get(self.stufe, self._lokal))
        return True

    def ereignis(self, daten: dict) -> None:
        """Ein Zwischenstand des Werkzeugs (``PS4FFPSC_PROGRESS``-Zeile als Woerterbuch)."""
        bereich = str(daten.get("scope") or "")
        if daten.get("action") == "status":
            return
        anteil = _verhaeltnis(daten)
        if bereich == "extract":
            lokal, teil = STUFEN_START[1] + BREITE_ENTPACKEN * anteil, anteil
        elif bereich == "merge_package":
            lokal, teil = STUFEN_START[2] + BREITE_ZUSAMMEN * anteil, anteil
        elif bereich == "mkpfs" and self.stufe in (3, 4):
            if self.stufe == 3:
                lokal = STUFEN_START[3] + BREITE_PACKEN * anteil
            else:
                lokal = STUFEN_START[4] + BREITE_PRUEFEN * anteil
            teil = anteil
            bereich = str(daten.get("phase") or bereich)
        elif bereich == "cleanup":
            lokal, teil = ABSCHLUSS, 1.0
        else:
            return
        self.teil = bereich
        self.teil_prozent = int(round(teil * 100))
        self._lokal = max(self._lokal, min(100.0, lokal))

    # -- Ausgabe -----------------------------------------------------------------
    @property
    def prozent(self) -> float:
        fertig = self.spiel_nr * 100.0
        return max(0.0, min(100.0, (fertig + self._lokal) / self.spiel_gesamt))

    def stand(self) -> Stand:
        verstrichen = self._jetzt() - self.beginn
        prozent = self.prozent
        return Stand(prozent, self.stufe, self.stufen_gesamt, self.teil, self.teil_prozent,
                     verstrichen, rest_sekunden(verstrichen, prozent))

    def abschluss(self) -> Stand:
        """Alles fertig: 100 %, Rest 0."""
        self.spiel_nr = self.spiel_gesamt - 1
        self._lokal = 100.0
        return self.stand()
