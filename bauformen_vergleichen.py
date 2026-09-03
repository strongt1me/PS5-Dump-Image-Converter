# -*- coding: utf-8 -*-
"""Baut aus einem Dump-Ordner beide Bauformen und vergleicht sie.

    python beide_formen.py <dump-ordner> [<zielordner>]

Erzeugt zwei Abbilder aus derselben Quelle:

* ``<name>_pfs.ffpfsc``   - PFS-in-PFS, so wie das Programm heute baut:
  ``pack folder --raw --no-compress`` fuer das innere PFS, danach
  ``pack file --compress`` fuer den aeusseren Container.
* ``<name>_exfat.ffpfsc`` - exFAT-in-PFS, so wie die Anleitung der Engine
  es nennt: ein einziger ``pack folder``-Aufruf.

Danach sagt es zu jedem Abbild, was der Validator des Programms darin
sieht, wie gross es ist und wie lange der Bau gedauert hat.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

PROJEKT = Path(r"C:\PS5-Dump-Image-Converter-WPF")
ENGINE = PROJEKT / "MkPFS-1.0.0"

#: Die Schalter, die beide Wege gemeinsam haben - abgelesen an den
#: Packaufrufen des Programms.
GEMEINSAM = ["--no-adjust-output-file-extension", "--version", "PS5",
             "--inode-bits", "32", "--block-size", "65536"]
STUFE = ["--compression-level", "9"]


def _mkpfs(argumente: list[str]) -> int:
    """Ruft die Engine im eigenen Prozess auf und schluckt ihre Ausgabe."""
    import contextlib
    import io

    sys.path.insert(0, str(ENGINE))
    from mkpfs.cli import cli_mkpfs_main

    puffer = io.StringIO()
    with contextlib.redirect_stdout(puffer), contextlib.redirect_stderr(puffer):
        try:
            return int(cli_mkpfs_main(argumente) or 0)
        except SystemExit as ende:
            return int(ende.code) if isinstance(ende.code, int) else 0


def _bauform(pfad: Path) -> str:
    sys.path.insert(0, str(PROJEKT))
    from ps5_validator.modules.ffpfs_validator import ermittle_bauform

    befund = ermittle_bauform(str(pfad))
    return str(befund.get("bauform", "?"))


def main() -> int:
    quelle = Path(sys.argv[1]).resolve()
    ziel = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else quelle.parent
    if not quelle.is_dir():
        raise SystemExit(f"Kein Ordner: {quelle}")
    ziel.mkdir(parents=True, exist_ok=True)

    weg_pfs = ziel / f"{quelle.name}_pfs.ffpfsc"
    weg_exfat = ziel / f"{quelle.name}_exfat.ffpfsc"
    inneres = ziel / f"{quelle.name}_inneres_pfs.dat"

    print(f"Quelle: {quelle}")
    print(f"Ziel:   {ziel}\n")

    # --- Weg 1: PFS-in-PFS, wie das Programm heute baut ------------------
    t = time.perf_counter()
    rc1 = _mkpfs(["pack", "folder", "--raw", "--no-compress", *GEMEINSAM,
                  str(quelle), str(inneres)])
    rc2 = _mkpfs(["pack", "file", "--compress", "--no-rename-inner-image",
                  *GEMEINSAM, *STUFE, str(inneres), str(weg_pfs)])
    dauer_pfs = time.perf_counter() - t
    inneres.unlink(missing_ok=True)

    # --- Weg 2: exFAT-in-PFS, wie die Anleitung es nennt -----------------
    t = time.perf_counter()
    rc3 = _mkpfs(["pack", "folder", *GEMEINSAM, *STUFE, str(quelle), str(weg_exfat)])
    dauer_exfat = time.perf_counter() - t

    if rc1 or rc2 or rc3:
        print(f"WARNUNG: Rueckgabewerte {rc1}/{rc2}/{rc3}")

    print(f"{'Abbild':34s} {'Bauform':9s} {'Groesse':>14s} {'Bau':>8s}")
    print("-" * 70)
    for pfad, dauer in ((weg_pfs, dauer_pfs), (weg_exfat, dauer_exfat)):
        if not pfad.is_file():
            print(f"{pfad.name:34s} NICHT ENTSTANDEN")
            continue
        groesse = pfad.stat().st_size
        print(f"{pfad.name:34s} {_bauform(pfad):9s} {groesse:>14,d} {dauer:7.1f}s")

    quellgroesse = sum(f.stat().st_size for f in quelle.rglob("*") if f.is_file())
    print(f"\nQuelle: {quellgroesse:,d} Bytes")
    for pfad in (weg_pfs, weg_exfat):
        if pfad.is_file() and quellgroesse:
            print(f"  {pfad.name:32s} {pfad.stat().st_size / quellgroesse * 100:5.1f} % der Quelle")
    return 0


if __name__ == "__main__":
    sys.exit(main())
