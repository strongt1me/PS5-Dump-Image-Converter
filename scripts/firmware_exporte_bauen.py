"""Baut die Exporttabellen der Backport-Zielfirmwares (``Backport_Fakelibs/<n>/firmware_exporte.json.gz``).

Je Hauptversion werden alle entpackten Staende dieser Version gelesen (z. B. 4.00, 4.03, 4.50, 4.51) und je
Bibliothek nur die Funktionen behalten, die JEDER Stand fuehrt, der diese Bibliothek ueberhaupt enthaelt. Ein
Backport auf "4" muss auf der niedrigsten 4.xx-Konsole laufen; einzelne Entpackungen sind lueckenhaft (4.00 fuehrt
261 Bibliotheken, 4.03 dagegen 509), deshalb zaehlt eine fehlende Datei nicht als fehlende Bibliothek.

Gespeichert werden nur Bibliotheksnamen und NIDs (Kurzkennungen), kein Code aus der Firmware.

Aufruf: .venv\\Scripts\\python.exe scripts\\firmware_exporte_bauen.py <Wurzel der entpackten Firmwares> [4 5 6 7]
"""
from __future__ import annotations

import gzip
import json
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
PROJEKT = os.path.dirname(HIER)
sys.path.insert(0, PROJEKT)

from ps5_validator.utils import ps5_backport as bp  # noqa: E402


def staende(wurzel: str, haupt: int) -> list[str]:
    gefunden = []
    for name in sorted(os.listdir(wurzel)):
        kopf, _, rest = name.partition(".")
        if rest and kopf.isdigit() and int(kopf) == haupt:
            pfad = os.path.join(wurzel, name)
            if bp.ist_firmware_bestand(pfad):
                gefunden.append(pfad)
    return gefunden


#: Nur diese Ordner sieht ein Spiel in seinem Sandkasten (``/<zufall>/common/lib``); ``priv`` bleibt dem System.
SPIEL_PFADE = (("system", "common", "lib"), ("system_ex", "common_ex", "lib"))


def stand_lesen(pfad: str) -> dict[str, set]:
    """Exporte eines Standes, beschraenkt auf das, was ein Spiel laden kann.

    Die Systemoberflaeche bringt zehntausende Mono-/React-Exporte mit (mscorlib, SystemCore, ...), die kein Spiel
    importiert - sie machten drei Viertel der Tabelle aus. Behalten werden Bibliotheken aus ``common/lib``, deren
    Name mit ``lib`` beginnt.
    """
    tabelle: dict[str, set] = {}
    for teile in SPIEL_PFADE:
        ordner = os.path.join(pfad, *teile)
        if not os.path.isdir(ordner):
            continue
        for name in sorted(os.listdir(ordner)):
            if not name.lower().endswith((".sprx", ".prx")):
                continue
            for lib, nids in bp.symbole_aus_datei(os.path.join(ordner, name))["exporte"].items():
                if lib and lib != "?" and lib.startswith("lib"):
                    tabelle.setdefault(lib, set()).update(nids)
    return tabelle


def tabelle_bauen(wurzel: str, haupt: int) -> tuple[dict[str, list[str]], list[str]]:
    pfade = staende(wurzel, haupt)
    zusammen: dict[str, set] = {}
    for pfad in pfade:
        for lib, nids in stand_lesen(pfad).items():
            if lib in zusammen:
                zusammen[lib] &= nids
            else:
                zusammen[lib] = set(nids)
    return {lib: sorted(nids) for lib, nids in sorted(zusammen.items())}, [os.path.basename(p) for p in pfade]


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    wurzel = argv[0]
    hauptversionen = [int(a) for a in argv[1:]] or list(bp.FIRMWARE_MIT_FAKELIBS)
    for haupt in hauptversionen:
        tabelle, quellen = tabelle_bauen(wurzel, haupt)
        if not tabelle:
            print(f"FW {haupt}: kein Stand gefunden")
            continue
        ziel = os.path.join(PROJEKT, "Backport_Fakelibs", str(haupt), bp.FIRMWARE_EXPORTE_DATEI)
        daten = {"firmware": haupt, "staende": quellen, "exporte": tabelle}
        roh = json.dumps(daten, separators=(",", ":"), sort_keys=True).encode("utf-8")
        # mtime=0: dieselbe Eingabe ergibt byte-gleich dieselbe Datei.
        with open(ziel, "wb") as datei:
            with gzip.GzipFile(fileobj=datei, mode="wb", mtime=0, filename="") as gz:
                gz.write(roh)
        print(f"FW {haupt}: {len(tabelle)} Bibliotheken, {sum(len(v) for v in tabelle.values())} Funktionen "
              f"aus {', '.join(quellen)} -> {os.path.getsize(ziel)} Byte")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
