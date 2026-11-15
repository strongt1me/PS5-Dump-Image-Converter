# -*- coding: utf-8 -*-
"""Pfade vergleichen - auch auf Dateisystemen ohne Gross/Klein-Unterscheidung ausserhalb von Windows.

``os.path.normcase`` faltet nur unter Windows. Auf macOS (APFS/HFS+ in der Vorgabe) und auf exFAT/NTFS unter Linux sind
``Spiel.FFPKG`` und ``Spiel.ffpkg`` dieselbe Datei, der Textvergleich sagt aber "verschieden". Gesamtpruefung 14.11.2026 (S-A):
``_run_engine_thread`` hielt das Ziel deshalb nicht fuer die Quelle und loeschte sie als "altes Ergebnis", bevor der Lauf begann.

Reicht der Text nicht, wird das Dateisystem gefragt - und beide Funktionen sind **Schutzfragen**: Im Zweifel lieber "derselbe Ort"
(dann baut ein Lauf daneben oder eine Quelle bleibt liegen) als "verschieden" (dann koennte die Quelle als altes Ergebnis geloescht
werden).

* Geraet und Dateinummer (``os.path.samestat``), auf jedem System. Eine Dateinummer 0 zaehlt nicht (manche Netzlaufwerke melden sie
  fuer jede Datei). Unter Windows erkennt sie auch ``\\\\localhost\\C$``, ``\\\\127.0.0.1``, Hardlinks und ``\\\\?\\``-Pfade.
* Unter Windows zusaetzlich der aufgeloeste Pfad (``os.path.realpath``: Schreibung auf der Platte, Junctions, ``subst``-Laufwerke,
  verbundene Netzlaufwerke). Ein Fehlalarm bei zwei geklonten Datentraegern (gleiche Seriennummer und Datei-IDs) fuehrt nur dazu, dass
  daneben gebaut wird (R2-A5); die Dateinummer allein wegzulassen, liess dagegen Aliase durch, und ein Selbst-Ziel loeschte die Quelle
  vor dem Bau (R3-A1).

Fuer Pfade auf einem Netzlaufwerk kann jede Frage ans Dateisystem lange dauern (ein nicht erreichbarer Server: ~21 s). Wo nur Pfade
des Programms selbst verglichen werden oder die Oberflaeche wartet, gibt es :func:`liegt_in_text`.
"""
from __future__ import annotations

import os


def _norm(pfad: str) -> str:
    return os.path.normcase(os.path.abspath(pfad))


def _kennung_gleich(a: "os.stat_result", b: "os.stat_result") -> bool:
    return bool(a.st_ino) and os.path.samestat(a, b)


def _aufgeloest(pfad: str) -> str:
    return os.path.normcase(os.path.realpath(pfad))


def gleicher_ort(a: str, b: str) -> bool:
    """Bezeichnen ``a`` und ``b`` dieselbe Datei bzw. denselben Ordner? Fehlt einer von beiden, entscheidet nur der Text."""
    if not a or not b:
        return False
    try:
        if _norm(a) == _norm(b):
            return True
        if os.name == "nt" and os.path.lexists(a) and os.path.lexists(b) and _aufgeloest(a) == _aufgeloest(b):
            return True
        return _kennung_gleich(os.stat(a), os.stat(b))
    except (OSError, TypeError, ValueError):
        return False


def liegt_in_text(pfad: str, ordner: str) -> bool:
    """Nur der Textvergleich von :func:`liegt_in` - ohne Frage ans Dateisystem (sofort, auch fuer ein getrenntes Netzlaufwerk)."""
    if not pfad or not ordner:
        return False
    try:
        p, o = _norm(pfad), _norm(ordner)
        return os.path.commonpath([p, o]) == o
    except (TypeError, ValueError):
        return False


def liegt_in(pfad: str, ordner: str) -> bool:
    """Liegt ``pfad`` in ``ordner`` oder ist er es selbst?

    Bestandteil fuer Bestandteil - ``D:\\Spiele2`` liegt nicht in ``D:\\Spiele``. Reicht der Textvergleich nicht und gibt es ``ordner``,
    wird das Dateisystem gefragt (siehe oben): unter Windows ueber die aufgeloesten Pfade, sonst ueber die Dateinummer jedes vorhandenen
    Elternordners von ``pfad`` (und ``pfad`` selbst).
    """
    if not pfad or not ordner:
        return False
    try:
        p, o = _norm(pfad), _norm(ordner)
        if os.path.commonpath([p, o]) == o:
            return True
    except (TypeError, ValueError):                      # verschiedene Laufwerke unter Windows: weiter mit dem Dateisystem
        pass
    try:
        if not os.path.isdir(ordner):
            return False
        if os.name == "nt":
            p, o = _aufgeloest(pfad), _aufgeloest(ordner)
            try:
                if os.path.commonpath([p, o]) == o:
                    return True
            except ValueError:
                pass
        ziel = os.stat(ordner)
        stelle = os.path.abspath(pfad)
    except (OSError, TypeError, ValueError):
        return False
    while True:
        try:
            if _kennung_gleich(os.stat(stelle), ziel):
                return True
        except OSError:
            pass
        eltern = os.path.dirname(stelle)
        if eltern == stelle:
            return False
        stelle = eltern
