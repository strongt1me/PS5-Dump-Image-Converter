"""
PS5 Dump Validator Tool – CLI Entry Point
==========================================
Verwendung:
  python main.py --mode dump   --path  "D:\\PS5\\Game"
  python main.py --mode ffpfs  --file  "game.ffpfsc"
  python main.py --mode extfat --file  "image.extfat"

Optionale Flags:
  --output report.json   JSON-Bericht speichern
  --verbose              Ausführliche Ausgabe
  --threads N            Worker-Threads (Standard: CPU-Kerne / 2)
  --resume               Hash-Cache verwenden (nur dump-Modus)
  --log   logfile.log    Log-Datei schreiben
  --gui                  GUI starten (tkinter)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Sicherstellen dass ps5_validator importierbar ist
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from ps5_validator.core.dispatcher import validate, VALID_MODES
from ps5_validator.utils.logger    import setup_logger
from ps5_validator.utils.file_io   import write_json_report


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ps5_validator",
        description="PS5 Dump Validator Tool – Integrität prüfen für Dumps, FFPFS und exFAT",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--mode",    choices=VALID_MODES, required=False,
                   help="Validierungsmodus: dump | ffpfs | extfat")
    p.add_argument("--path",    metavar="ORDNER",
                   help="Quellordner (dump-Modus)")
    p.add_argument("--file",    metavar="DATEI",
                   help="Quelldatei (ffpfs / extfat Modus)")
    p.add_argument("--output",  metavar="REPORT.JSON",
                   help="JSON-Bericht speichern")
    p.add_argument("--verbose", action="store_true",
                   help="Ausführliche Ausgabe")
    p.add_argument("--threads", type=int, default=max(1, (os.cpu_count() or 4) // 2),
                   help="Worker-Threads für Hash-Berechnung (Standard: CPU/2)")
    p.add_argument("--resume",  action="store_true",
                   help="Hash-Cache verwenden (dump-Modus)")
    p.add_argument("--log",     metavar="LOGFILE",
                   help="Log-Datei schreiben")
    p.add_argument("--gui",     action="store_true",
                   help="GUI starten")
    return p


def _progress_bar(done: int, total: int, label: str) -> None:
    """Einfache ASCII-Fortschrittsanzeige."""
    if total <= 0:
        return
    pct   = min(100, int(done / total * 100))
    bar   = "█" * (pct // 2) + "░" * (50 - pct // 2)
    short = label[-40:] if len(label) > 40 else label
    print(f"\r[{bar}] {pct:3d}%  {short:<40}", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args   = parser.parse_args(argv)

    # GUI-Modus
    if args.gui:
        try:
            from ps5_validator.gui import run_gui
            run_gui()
        except ImportError as exc:
            print(f"[FEHLER] GUI nicht verfügbar: {exc}")
            return 1
        return 0

    # Modus und Pfad bestimmen
    if not args.mode:
        parser.print_help()
        return 1

    target = args.path if args.mode == "dump" else args.file
    if not target:
        flag = "--path" if args.mode == "dump" else "--file"
        print(f"[FEHLER] Für Modus '{args.mode}' ist {flag} erforderlich.")
        return 1

    # Logger einrichten
    log = setup_logger(verbose=args.verbose, log_file=args.log)
    log.info(f"PS5 Dump Validator | Modus: {args.mode} | Ziel: {target}")

    # Validierung starten
    try:
        result = validate(
            path=target,
            mode=args.mode,
            threads=args.threads,
            resume=args.resume,
            progress_cb=_progress_bar,
            verbose=args.verbose,
        )
    except KeyboardInterrupt:
        print("\n[ABBRUCH] Durch Benutzer abgebrochen.")
        return 130
    except Exception as exc:
        print(f"\n[FEHLER] Unerwarteter Fehler: {exc}")
        return 1

    print()  # Zeilenumbruch nach Fortschrittsbalken

    # Ergebnis ausgeben
    data = result.to_dict()
    print(json.dumps(data, indent=2, ensure_ascii=False))

    # JSON-Bericht speichern
    if args.output:
        write_json_report(args.output, data)
        log.info(f"Bericht gespeichert: {args.output}")

    # Exit-Code
    return 0 if result.status == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
