# -*- coding: utf-8 -*-
"""Die Huelle um ``ProsperoPkgTool`` - den zweiten, waehlbaren Paketersteller (seit 12.10.2026).

Nutzerwunsch: Die eigene Vorlagen-App des Nutzers bietet in ihren Optionen zwei Paketersteller zur Wahl
("Standard-Builder": LibProsperoPkg 1.2.0 / ProsperoPkgTool). Dieses Modul bringt den zweiten dazu - nur fuer
**Aufgabe "Paket bauen"**: Lesen, Pruefen und Entpacken bleiben beim bestehenden :mod:`ps5_pkg_werkzeug`
(``ffpfsc-pkg-tool``), das ``--json`` kennt, die CNT-Metadaten (param.json, Cover, Trophaeen) automatisch dazuholt
und einen Passcode durchreicht. ProsperoPkgTool kennt nur Klartext-Zeilen auf stdout/stderr, keine JSON-Ausgabe -
dieses Modul liest sie deshalb mit Mustern, kein Umweg ueber eine Datenstruktur, die es nicht gibt.

ProsperoPkgTool stammt aus dem Quelltext von **pearlxcore/ProsperoPkgTool 0.3.0** (MIT-Lizenz, Commit ``f2c91cd7``)
und liegt, fuer jede Plattform einzeln gebaut, unter ``PS5-PKG-Tool/<Plattform>/`` - neben ``ffpfsc-pkg-tool``.
Laut eigenem README eine clean-room-Neuimplementierung, kein gemeinsamer Code mit LibProsperoPkg. Herkunft und
Messung in ``PS5-PKG-Tool/NOTICE_ProsperoPkgTool.md``.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Callable

from . import ps5_pkg_werkzeug as wz

#: Ordner im Projekt (und im Bau), darin je Plattform ein Unterordner - derselbe wie bei ffpfsc-pkg-tool.
ORDNER = wz.ORDNER

_Zeile = Callable[[str], None]
_Abbruch = Callable[[], bool]

#: ``    NN%  <Stufe> (<Pfad oder Zaehler>)`` - eine Fortschrittszeile von ``convert``/``img_create``.
_FORTSCHRITT = re.compile(r"^\s*(\d{1,3})%\s+(.*)$")
#: ``[stage N/5] <Name> complete in <Dauer>.`` - eine abgeschlossene Stufe.
_STUFE_FERTIG = re.compile(r"\[stage\s+(\d)/5\]\s+(.+?)\s+complete\b")
#: Die fuenf Stufen von ``convert`` (Innenabbild, NAPS, aeussere PFS, CNT, Abschluss), mit ihrem ungefaehren
#: Anteil am Ganzen (von, bis in Prozent) - gemessen an den Laufzeiten eines echten Baus (12.10.2026).
_STUFEN_ANTEIL = ((5, 25), (25, 30), (30, 75), (75, 90), (90, 99))


def werkzeug_suchen(wurzeln: "list[str] | None" = None) -> str:
    """Pfad zu ``ProsperoPkgTool`` (``.exe`` unter Windows), sonst ``""`` - derselbe Suchweg wie bei ffpfsc-pkg-tool."""
    name = "ProsperoPkgTool.exe" if sys.platform == "win32" else "ProsperoPkgTool"
    for wurzel in wurzeln or []:
        kandidat = os.path.join(wurzel, ORDNER, wz.unterordner(), name)
        if os.path.isfile(kandidat):
            return kandidat
    return ""


class ProsperoBau:
    """Verfolgt den Baufortschritt ueber mehrere Zeilen - die Stufe wechselt nur bei einer ``[stage N/5]``-Zeile."""

    def __init__(self) -> None:
        self.stufe = 0  # 0 = vor der ersten Stufe

    def zeile(self, text: str) -> "tuple[int, str] | None":
        rest = text
        for _ in range(2):
            treffer = re.match(r"^\s*\[[^\]]*\]\s*(.*)$", rest)
            if not treffer:
                break
            rest = treffer.group(1)
        begonnen = re.search(r"\[stage\s+(\d)/5\]", rest)
        if begonnen:
            self.stufe = max(self.stufe, int(begonnen.group(1)) - 1)
        fertig = _STUFE_FERTIG.search(rest)
        if fertig:
            nummer = int(fertig.group(1))
            self.stufe = nummer
            _von, bis = _STUFEN_ANTEIL[nummer - 1]
            return bis, fertig.group(2)
        treffer = _FORTSCHRITT.match(rest)
        if treffer:
            von, bis = _STUFEN_ANTEIL[min(max(self.stufe, 0), len(_STUFEN_ANTEIL) - 1)]
            anteil = min(100, int(treffer.group(1)))
            return von + (bis - von) * anteil // 100, treffer.group(2).strip()
        return None


def bauen(werkzeug: str, quelle: str, ziel: str, *, content_id: str = "", title_id: str = "",
          passcode: str = "", zeile: "_Zeile | None" = None,
          fortschritt: "Callable[[int, str], None] | None" = None, abbruch: "_Abbruch | None" = None,
          popen_extra: "dict | None" = None) -> str:
    """Baut aus einem Spielordner ein Debug-Paket (``convert``) und gibt den Pfad der ``.pkg`` zurueck.

    ``convert`` ist der Weg fuer einen entpackten Dump/Spielordner (im Gegensatz zu ``img_create``, das einen
    frischen Quellordner oder ein GP5-Projekt baut): Es erkennt bereits fake-signierte Module und laesst sie stehen,
    ersetzt nur rohe ELF-Dateien. Ohne ``content_id``/``title_id`` liest ``convert`` sie aus ``sce_sys/param.json``.

    Raises:
        Fehler: ungueltige Werkzeugausgabe, Fehler des Werkzeugs, kein Ausgabepfad am Ende; ``abgebrochen`` beim
            Abbruch (Baufortschritt wird nicht unterbrochen - ``abbruch`` wird nur zwischen den Zeilen gefragt).
    """
    os.makedirs(os.path.dirname(os.path.abspath(ziel)) or ".", exist_ok=True)
    # --verbose: ohne das meldet convert nur die fuenf Stufenenden, mit ihm auch die feineren Prozentzeilen
    # innerhalb jeder Stufe (z. B. "Outer PFS encrypt") - ein ruhigerer Balken statt fuenf grossen Spruengen.
    argumente = ["convert", quelle, "--out", ziel, "--verbose"]
    if passcode:
        argumente += ["--passcode", passcode]
    else:
        argumente.append("--no_passcode")
    if content_id:
        argumente += ["--content-id", content_id]
    if title_id:
        argumente += ["--title-id", title_id]

    bau = ProsperoBau()
    gesammelt: list[str] = []

    def jede(text: str) -> None:
        gesammelt.append(text)
        gemeldet = bau.zeile(text)
        if gemeldet and fortschritt:
            fortschritt(gemeldet[0], gemeldet[1])
        elif zeile:
            zeile(text)

    rc, aus = wz.laufen(werkzeug, argumente, zeile=jede, abbruch=abbruch, popen_extra=popen_extra)
    if rc == -1:
        raise wz.Fehler("abgebrochen")
    if rc != 0:
        fehler = next((z for z in reversed(gesammelt) if z.startswith("Error:")), "")
        raise wz.Fehler(fehler or wz._fehlertext(aus))  # noqa: SLF001 - dieselbe Aufbereitung wie ffpfsc-pkg-tool
    treffer = re.search(r"^\s*Output:\s*(.+?)\s*$", aus, re.MULTILINE)
    pfad = treffer.group(1) if treffer else ziel
    if not os.path.isfile(pfad):
        raise wz.Fehler("ProsperoPkgTool meldet Erfolg, aber die Ausgabedatei fehlt: %s" % pfad)
    return pfad
