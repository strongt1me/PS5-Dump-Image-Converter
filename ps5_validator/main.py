"""
PS5 Dump Validator Tool – CLI Entry Point
==========================================
Verwendung:
  python main.py --mode dump   --path  "D:\\PS5\\Game"
  python main.py --mode ffpfs  --file  "game.ffpfsc"
  python main.py --mode extfat --file  "image.extfat"
  python main.py --mode ffpkg --file  "image.ffpkg" --ufs2tool-path "UFS2Tool.exe"

Optionale Flags:
  --output report.json   JSON-Bericht speichern
  --verbose              Ausführliche Ausgabe
  --threads N            Worker-Threads (Standard: CPU-Kerne / 2)
  --resume               Hash-Cache verwenden (nur dump-Modus)
  --log logfile.log      Log-Datei schreiben
  --gui                  GUI starten (tkinter)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Sicherstellen, dass ps5_validator importierbar ist.
_HERE = Path(__file__).resolve().parent
if str(_HERE.parent) not in sys.path:
    sys.path.insert(0, str(_HERE.parent))

from ps5_validator.core.dispatcher import VALID_MODES, validate
from ps5_validator.utils.file_io import write_json_report
from ps5_validator.utils.logger import setup_logger


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ps5_validator",
        description=(
            "PS5 Dump Validator Tool – Integrität prüfen für Dumps, FFPFS, "
            "exFAT und UFS2-FFPKG"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        required=False,
        help="Validierungsmodus: dump | ffpfs | extfat | ffpkg",
    )
    parser.add_argument("--path", metavar="ORDNER", help="Quellordner (dump-Modus)")
    parser.add_argument(
        "--file", metavar="DATEI", help="Quelldatei (ffpfs / extfat / ffpkg Modus)"
    )
    parser.add_argument(
        "--ufs2tool-path",
        metavar="UFS2TOOL.EXE",
        help="Pfad zu UFS2Tool.exe (für ffpkg erforderlich)",
    )
    parser.add_argument("--output", metavar="REPORT.JSON", help="JSON-Bericht speichern")
    parser.add_argument("--verbose", action="store_true", help="Ausführliche Ausgabe")
    parser.add_argument(
        "--threads",
        type=int,
        default=max(1, (os.cpu_count() or 4) // 2),
        help="Worker-Threads für Hash-Berechnung (Standard: CPU/2)",
    )
    parser.add_argument("--resume", action="store_true", help="Hash-Cache verwenden (dump-Modus)")
    parser.add_argument("--log", metavar="LOGFILE", help="Log-Datei schreiben")
    parser.add_argument("--gui", action="store_true", help="GUI starten")
    return parser


def _progress_bar(done: int, total: int, label: str) -> None:
    """Einfache ASCII-Fortschrittsanzeige."""
    if total <= 0:
        return
    percent = min(100, int(done / total * 100))
    bar = "█" * (percent // 2) + "░" * (50 - percent // 2)
    short = label[-40:] if len(label) > 40 else label
    print(f"\r[{bar}] {percent:3d}%  {short:<40}", end="", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.gui:
        try:
            from ps5_validator.gui import run_gui

            run_gui()
        except ImportError as exc:
            print(f"[FEHLER] GUI nicht verfügbar: {exc}")
            return 1
        return 0

    if not args.mode:
        parser.print_help()
        return 1

    target = args.path if args.mode == "dump" else args.file
    if not target:
        flag = "--path" if args.mode == "dump" else "--file"
        print(f"[FEHLER] Für Modus '{args.mode}' ist {flag} erforderlich.")
        return 1
    if args.mode == "ffpkg" and not args.ufs2tool_path:
        print("[FEHLER] Für Modus 'ffpkg' ist --ufs2tool-path erforderlich.")
        return 1

    logger = setup_logger(verbose=args.verbose, log_file=args.log)
    logger.info("PS5 Dump Validator | Modus: %s | Ziel: %s", args.mode, target)

    try:
        result = validate(
            path=target,
            mode=args.mode,
            threads=args.threads,
            resume=args.resume,
            progress_cb=_progress_bar,
            verbose=args.verbose,
            ufs2tool_path=args.ufs2tool_path or "",
        )
    except KeyboardInterrupt:
        print("\n[ABBRUCH] Durch Benutzer abgebrochen.")
        return 130
    except Exception as exc:
        print(f"\n[FEHLER] Unerwarteter Fehler: {exc}")
        return 1

    print()
    data = result.to_dict()
    print(json.dumps(data, indent=2, ensure_ascii=False))

    if args.output:
        write_json_report(args.output, data)
        logger.info("Bericht gespeichert: %s", args.output)

    return 0 if result.status in ("OK", "WARNING") else 1


if __name__ == "__main__":
    sys.exit(main())
