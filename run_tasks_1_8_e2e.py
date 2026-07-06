#!/usr/bin/env python3
"""E2E-Runner fuer Aufgaben 1-8 der PS5 Converter App.

Hinweis:
- Aufgaben 1-5 benoetigen Administratorrechte (OSFMount/exFAT-Pfad).
- Aufgabe 7 (fakelib Manager) ist interaktiv und wird als MANUAL_REQUIRED markiert.
- Aufgabe 8 wird ueber den CLI-Validator geprueft (OK/FAIL Pfad).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

import tkinter as tk

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI


def _is_admin() -> bool:
    if os.name != "nt":
        return True
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _looks_like_game_folder(path: Path) -> bool:
    return (path / "eboot.bin").exists() or (path / "sce_sys" / "param.json").exists()


def _resolve_game_folder(*candidates: Path) -> Path | None:
    """Findet den plausiblen Spielordner auch bei verschachtelten Tool-Ausgaben."""
    checked: set[Path] = set()

    for base in candidates:
        if not base:
            continue
        if base in checked:
            continue
        checked.add(base)

        if _looks_like_game_folder(base):
            return base

        if not base.exists() or not base.is_dir():
            continue

        # Begrenzte Suche: eboot.bin ist ein starker Indikator fuer den Root des Dumps.
        for eboot in base.rglob("eboot.bin"):
            parent = eboot.parent
            if _looks_like_game_folder(parent):
                return parent
    return None


def _resolve_dump_dir(repo: Path, dump_arg: str) -> Path:
    """Resolve the dump directory from the user argument or local fallbacks.

    Args:
        repo: Repository root.
        dump_arg: User-provided dump path, absolute or relative.

    Returns:
        Existing dump directory path.

    Raises:
        FileNotFoundError: When no suitable dump directory can be found.
    """
    candidates: list[Path] = []
    raw_path = Path(dump_arg).expanduser()
    if raw_path.is_absolute():
        candidates.append(raw_path)
    else:
        candidates.append((repo / raw_path).resolve())
        candidates.append(raw_path.resolve())

    candidates.extend(
        [
            (repo / "_dummy_inputs" / "DummyDump").resolve(),
            (repo / "Diverses" / "_dummy_inputs" / "DummyDump").resolve(),
        ]
    )

    resolved = _resolve_game_folder(*candidates)
    if resolved is not None:
        return resolved.resolve()

    raise FileNotFoundError(
        "Dump-Ordner nicht gefunden: "
        f"{raw_path} (auch keine lokalen Fallbacks wie _dummy_inputs/DummyDump gefunden)"
    )


def _run_cli_dump_validator(path: Path, output_json: Path) -> tuple[bool, str]:
    repo = Path(__file__).resolve().parent
    validator_script = repo / "ps5_validator" / "main.py"
    cmd = [
        sys.executable,
        str(validator_script),
        "--mode",
        "dump",
        "--path",
        str(path),
        "--output",
        str(output_json),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=repo)
    ok = proc.returncode == 0
    tail = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    return ok, tail[-4000:]


def _run_task(name: str, fn, result_store: dict, logs: dict, task_log: list[str]) -> bool:
    try:
        ok = bool(fn())
        result_store[name] = "PASS" if ok else "FAIL"
        if not ok and task_log:
            logs[name] = "".join(task_log)[-6000:]
        return ok
    except Exception:
        result_store[name] = "ERROR"
        tail = "".join(task_log)[-3000:]
        logs[name] = (traceback.format_exc(limit=6) + ("\n\n--- task-log-tail ---\n" + tail if tail else ""))
        return False


def _normalize_task_selector(task: str | None) -> str | None:
    """Normalize a user-supplied task selector to the canonical task key.

    Args:
        task: User-supplied task token such as ``A1`` or ``A8``.

    Returns:
        Canonical task key like ``A1`` when recognized, otherwise ``None``.
    """
    if task is None:
        return None
    normalized = task.strip().upper()
    if normalized in {f"A{i}" for i in range(1, 9)}:
        return normalized
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E-Runner fuer Aufgaben 1-8")
    parser.add_argument("--dump", default="DumpA", help="Pfad zum Dump-Ordner")
    parser.add_argument(
        "--ffpkg",
        default="",
        help="Pfad zur .ffpkg-Datei (optional, sonst auto-detect)",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        help="Ausgabeordner fuer Report und Artefakte",
    )
    parser.add_argument(
        "--skip-a1",
        action="store_true",
        help="Aufgabe 1 ueberspringen und mit vorhandenem A1-Artefakt fortsetzen",
    )
    parser.add_argument(
        "--a1-input",
        default="",
        help="Pfad zu bestehender .ffpfsc-Datei aus Aufgabe 1 (fuer --skip-a1)",
    )
    parser.add_argument(
        "--task",
        default="",
        help="Nur eine Aufgabe ausfuehren (A1 bis A8), um Haenger gezielt zu isolieren",
    )
    args = parser.parse_args()

    selected_task: str | None = _normalize_task_selector(args.task)
    if args.task and selected_task is None:
        raise ValueError("--task muss A1, A2, A3, A4, A5, A6, A7 oder A8 sein")

    repo = Path(__file__).resolve().parent
    dump_dir = _resolve_dump_dir(repo, args.dump)

    if args.ffpkg:
        ffpkg_path = Path(args.ffpkg).resolve() if not os.path.isabs(args.ffpkg) else Path(args.ffpkg)
    else:
        candidates = sorted(repo.glob("*.ffpkg"))
        ffpkg_path = candidates[0].resolve() if candidates else Path("")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output_dir:
        out_dir = Path(args.output_dir)
        if not out_dir.is_absolute():
            out_dir = repo / out_dir
        out_dir = out_dir.resolve()
    else:
        out_dir = (repo / f"_e2e_output_{stamp}").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    a1_out = out_dir / f"{dump_dir.name}.ffpfsc"
    if args.skip_a1 and args.a1_input:
        a1_out = Path(args.a1_input).resolve() if not os.path.isabs(args.a1_input) else Path(args.a1_input)
    a2_out = out_dir / f"{dump_dir.name}.exfat"
    a3_out = out_dir / f"{dump_dir.name}_fromA3.ffpfsc"
    a4_out = out_dir / dump_dir.name
    a5_out = out_dir / f"{dump_dir.name}_from_exfat"
    a6_out = out_dir / "A6_from_ffpkg.ffpfsc"
    if ffpkg_path and ffpkg_path.is_file():
        a6_out = out_dir / f"{ffpkg_path.stem}.ffpfsc"

    results: dict[str, str] = {}
    logs: dict[str, str] = {}

    root = tk.Tk()
    root.withdraw()
    app = PS5ConverterGUI(root)
    _task_log: list[str] = []
    _orig_append = app._append_to_log

    def _capture_append(text: str) -> None:
        _task_log.append(text)
        _orig_append(text)

    app._append_to_log = _capture_append

    def _prep() -> None:
        _task_log.clear()
        app.is_running = True
        setattr(app, "cancel_requested", False)
        root.update_idletasks()
        root.update()

    try:
        if not dump_dir.is_dir():
            raise FileNotFoundError(f"Dump-Ordner nicht gefunden: {dump_dir}")

        if selected_task is not None:
            single_results: dict[str, str] = {}
            single_logs: dict[str, str] = {}

            def _single_run(label: str, fn) -> None:
                _prep()
                _run_task(label, fn, single_results, single_logs, _task_log)

            if selected_task == "A1":
                _single_run("A1_pack_folder_to_ffpfsc", lambda: app._mode_pack_folder(str(dump_dir), str(out_dir)))
            elif selected_task == "A2":
                if not a1_out.exists():
                    raise FileNotFoundError(f"A1-Artefakt fehlt fuer A2: {a1_out}")
                _single_run("A2_ffpfsc_to_exfat", lambda: app._mode_unpack_to_exfat(str(a1_out), str(out_dir)))
            elif selected_task == "A3":
                if not a2_out.exists():
                    raise FileNotFoundError(f"A2-Artefakt fehlt fuer A3: {a2_out}")
                _single_run("A3_exfat_to_ffpfsc", lambda: app._mode_pack_file(str(a2_out), str(a3_out)))
            elif selected_task == "A4":
                if not a3_out.exists():
                    raise FileNotFoundError(f"A3-Artefakt fehlt fuer A4: {a3_out}")
                _single_run("A4_ffpfsc_to_game_folder", lambda: app._mode_unpack_to_game_folder(str(a3_out), str(out_dir)))
            elif selected_task == "A5":
                if not a2_out.exists():
                    raise FileNotFoundError(f"A2-Artefakt fehlt fuer A5: {a2_out}")
                _single_run("A5_exfat_to_game_folder", lambda: app._mode_exfat_to_folder(str(a2_out), str(a5_out)))
            elif selected_task == "A6":
                if not ffpkg_path or not ffpkg_path.is_file():
                    raise FileNotFoundError("FFPKG-Datei fehlt fuer A6")
                _single_run("A6_ffpkg_to_ffpfsc", lambda: app._mode_ffpkg_to_ffpfsc(str(ffpkg_path), str(out_dir)))
            elif selected_task == "A7":
                single_results["A7_fakelib_manager"] = "MANUAL_REQUIRED"
            elif selected_task == "A8":
                a8_ok_json = out_dir / "a8_ok.json"
                a8_fail_json = out_dir / "a8_fail.json"
                ok_cli_ok, ok_tail = _run_cli_dump_validator(dump_dir, a8_ok_json)
                single_results["A8_OK_dump_validator"] = "PASS" if ok_cli_ok else "FAIL"
                if ok_tail.strip():
                    single_logs["A8_OK_dump_validator"] = ok_tail

                broken = out_dir / "_tmp_dump_broken"
                if broken.exists():
                    shutil.rmtree(broken, ignore_errors=True)
                broken.mkdir(parents=True, exist_ok=True)
                (broken / "README.txt").write_text("intentionally broken dump\n", encoding="utf-8")

                ok_cli_fail, fail_tail = _run_cli_dump_validator(broken, a8_fail_json)
                single_results["A8_FAIL_dump_validator"] = "PASS" if not ok_cli_fail else "FAIL"
                if fail_tail.strip():
                    single_logs["A8_FAIL_dump_validator"] = fail_tail

            report = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "results": single_results,
                "output_dir": str(out_dir),
                "logs": single_logs,
                "selected_task": selected_task,
            }
            report_path = out_dir / f"e2e_report_{selected_task.lower()}.json"
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({"output_dir": str(out_dir), "report": str(report_path), "results": single_results}, indent=2, ensure_ascii=False))
            return 0

        is_admin = _is_admin()

        if args.skip_a1:
            if a1_out.exists() and a1_out.suffix.lower() == ".ffpfsc":
                ok_a1 = True
                results["A1_pack_folder_to_ffpfsc"] = "SKIPPED_USING_EXISTING_ARTIFACT"
            else:
                ok_a1 = False
                results["A1_pack_folder_to_ffpfsc"] = "SKIPPED_BUT_MISSING_A1_ARTIFACT"
        elif not is_admin:
            ok_a1 = False
            results["A1_pack_folder_to_ffpfsc"] = "SKIPPED_NEEDS_ADMIN"
        else:
            _prep()
            ok_a1 = _run_task("A1_pack_folder_to_ffpfsc", lambda: app._mode_pack_folder(str(dump_dir), str(out_dir)), results, logs, _task_log)

        if not is_admin:
            ok_a2 = False
            results["A2_ffpfsc_to_exfat"] = "SKIPPED_NEEDS_ADMIN"
            results["A3_exfat_to_ffpfsc"] = "SKIPPED_DEPENDS_ON_A2"
            results["A4_ffpfsc_to_game_folder"] = "SKIPPED_DEPENDS_ON_A3"
            results["A5_exfat_to_game_folder"] = "SKIPPED_DEPENDS_ON_A2"
        elif ok_a1 and a1_out.exists():
            _prep()
            ok_a2 = _run_task("A2_ffpfsc_to_exfat", lambda: app._mode_unpack_to_exfat(str(a1_out), str(out_dir)), results, logs, _task_log)
        else:
            ok_a2 = False
            results["A2_ffpfsc_to_exfat"] = "SKIPPED_DEPENDS_ON_A1"

        if not is_admin:
            ok_a3 = False
        elif ok_a2 and a2_out.exists():
            _prep()
            ok_a3 = _run_task("A3_exfat_to_ffpfsc", lambda: app._mode_pack_file(str(a2_out), str(a3_out)), results, logs, _task_log)
        else:
            ok_a3 = False
            results["A3_exfat_to_ffpfsc"] = "SKIPPED_DEPENDS_ON_A2"

        if not is_admin:
            pass
        elif ok_a3 and a3_out.exists():
            _prep()
            _run_task("A4_ffpfsc_to_game_folder", lambda: app._mode_unpack_to_game_folder(str(a3_out), str(out_dir)), results, logs, _task_log)
        else:
            results["A4_ffpfsc_to_game_folder"] = "SKIPPED_DEPENDS_ON_A3"

        if not is_admin:
            pass
        elif ok_a2 and a2_out.exists():
            _prep()
            _run_task("A5_exfat_to_game_folder", lambda: app._mode_exfat_to_folder(str(a2_out), str(a5_out)), results, logs, _task_log)
        else:
            results["A5_exfat_to_game_folder"] = "SKIPPED_DEPENDS_ON_A2"

        if ffpkg_path and ffpkg_path.is_file():
            _prep()
            _run_task("A6_ffpkg_to_ffpfsc", lambda: app._mode_ffpkg_to_ffpfsc(str(ffpkg_path), str(out_dir)), results, logs, _task_log)
            _actual_a6 = getattr(app, "task_final_output_path", "")
            if _actual_a6:
                _actual_path = Path(_actual_a6)
                if not _actual_path.is_absolute():
                    _actual_path = (repo / _actual_path).resolve()
                a6_out = _actual_path
        else:
            results["A6_ffpkg_to_ffpfsc"] = "SKIPPED_NO_FFPKG"

        results["A7_fakelib_manager"] = "MANUAL_REQUIRED"

        a8_ok_json = out_dir / "a8_ok.json"
        a8_fail_json = out_dir / "a8_fail.json"

        ok_cli_ok, ok_tail = _run_cli_dump_validator(dump_dir, a8_ok_json)
        results["A8_OK_dump_validator"] = "PASS" if ok_cli_ok else "FAIL"
        if ok_tail.strip():
            logs["A8_OK_dump_validator"] = ok_tail

        broken = out_dir / "_tmp_dump_broken"
        if broken.exists():
            shutil.rmtree(broken, ignore_errors=True)
        broken.mkdir(parents=True, exist_ok=True)
        (broken / "README.txt").write_text("intentionally broken dump\n", encoding="utf-8")

        ok_cli_fail, fail_tail = _run_cli_dump_validator(broken, a8_fail_json)
        # FAIL-Pfad gilt als erfolgreich getestet, wenn Validator NICHT mit 0 endet.
        results["A8_FAIL_dump_validator"] = "PASS" if not ok_cli_fail else "FAIL"
        if fail_tail.strip():
            logs["A8_FAIL_dump_validator"] = fail_tail

    finally:
        try:
            root.destroy()
        except Exception:
            pass

    # Reale Ausgabeorte nach den Tasks aufloesen (einige Modi erzeugen dynamische Unterordnernamen).
    _a4_resolved = _resolve_game_folder(
        out_dir / a3_out.stem,
        out_dir / dump_dir.name,
        out_dir,
    )
    if _a4_resolved is not None:
        a4_out = _a4_resolved

    _a5_resolved = _resolve_game_folder(
        a5_out / dump_dir.name,
        a5_out,
        out_dir,
    )
    if _a5_resolved is not None:
        a5_out = _a5_resolved

    artifact_checks = {
        "A1_exists": a1_out.exists(),
        "A1_size_gt_0": a1_out.exists() and a1_out.stat().st_size > 0,
        "A2_exists": a2_out.exists(),
        "A2_size_gt_0": a2_out.exists() and a2_out.stat().st_size > 0,
        "A3_exists": a3_out.exists(),
        "A3_size_gt_0": a3_out.exists() and a3_out.stat().st_size > 0,
        "A4_has_eboot": (a4_out / "eboot.bin").exists(),
        "A4_has_param_json": (a4_out / "sce_sys" / "param.json").exists(),
        "A5_has_eboot": (a5_out / "eboot.bin").exists(),
        "A5_has_param_json": (a5_out / "sce_sys" / "param.json").exists(),
        "A6_exists": a6_out.exists(),
        "A6_size_gt_0": a6_out.exists() and a6_out.stat().st_size > 0,
    }

    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "results": results,
        "artifacts": {
            "A1": str(a1_out),
            "A2": str(a2_out),
            "A3": str(a3_out),
            "A4": str(a4_out),
            "A5": str(a5_out),
            "A6": str(a6_out),
            "A8_OK": str(out_dir / "a8_ok.json"),
            "A8_FAIL": str(out_dir / "a8_fail.json"),
        },
        "artifact_checks": artifact_checks,
        "output_dir": str(out_dir),
        "logs": logs,
    }

    report_path = out_dir / "e2e_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"output_dir": str(out_dir), "report": str(report_path), "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
