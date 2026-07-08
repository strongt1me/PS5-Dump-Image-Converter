#!/usr/bin/env python3
"""E2E-Runner fuer Aufgaben 1-8 der PS5 Converter App.

Hinweis:
- Aufgaben 1-5 benoetigen Administratorrechte (OSFMount/exFAT-Pfad).
- Aufgabe 7 (fakelib Manager) kann automatisiert ueber einen deterministischen fakelib_add-Test laufen.
- Aufgabe 8 wird ueber den CLI-Validator geprueft (OK/FAIL Pfad).
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import tkinter as tk

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI, ProgressEngine


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


def _find_fakelib_source(repo: Path) -> Path:
    candidates = [
        (repo / "fakelib").resolve(),
        (repo / "Diverses" / "fakelib").resolve(),
    ]
    for candidate in candidates:
        if (candidate / "libSceAmpr.sprx").is_file():
            return candidate
    raise FileNotFoundError("Kein fakelib-Ordner mit libSceAmpr.sprx gefunden")


def _find_existing_exfat_artifact(repo: Path, dump_name: str) -> Path | None:
    preferred = [
        (repo / "_e2e_output_alltasks_recheck" / f"{dump_name}.exfat").resolve(),
        (repo / "_e2e_output_alltasks_recheck3" / f"{dump_name}.exfat").resolve(),
        (repo / "_e2e_output_tasks3_8_admin_recheck" / f"{dump_name}.exfat").resolve(),
        (repo / "_e2e_output_a2_recheck" / f"{dump_name}.exfat").resolve(),
    ]
    for candidate in preferred:
        if candidate.is_file():
            return candidate

    for candidate in repo.rglob("*.exfat"):
        if candidate.is_file() and candidate.stem.lower() == dump_name.lower():
            return candidate.resolve()
    return None


def _expected_a7_output_path(staged_input: Path, output_dir: Path) -> Path:
    if staged_input.suffix.lower() == ".ffpkg":
        return output_dir / f"{staged_input.stem}.ffpfsc"
    return output_dir / staged_input.name


def _extract_a7_output(app: PS5ConverterGUI, actual_out: Path, verify_dir: Path, *, log_prefix: str) -> tuple[bool, Path]:
    if not actual_out.is_absolute():
        actual_out = actual_out.resolve()
    if not actual_out.is_file():
        return False, verify_dir

    if verify_dir.exists():
        shutil.rmtree(verify_dir, ignore_errors=True)
    verify_dir.mkdir(parents=True, exist_ok=True)

    _reset_app_progress_state(app)
    app.is_running = True
    setattr(app, "cancel_requested", False)

    suffix = actual_out.suffix.lower()
    if suffix == ".exfat":
        ok = bool(
            app._extract_exfat_to_folder_mkpfs(
                str(actual_out),
                str(verify_dir),
                status_prefix="A7-Verifikation",
                log_prefix=log_prefix,
                progress_start=96.0,
                progress_end=99.0,
            )
        )
    elif suffix == ".ffpfsc":
        ok = bool(app._mode_unpack_to_game_folder(str(actual_out), str(verify_dir)))
    else:
        return False, verify_dir

    game_root = _resolve_game_folder(verify_dir)
    return bool(ok and game_root is not None), (game_root or verify_dir)


def _run_a7_automation(
    app: PS5ConverterGUI,
    source_image: Path,
    fakelib_src: Path,
    output_dir: Path,
    *,
    output_subdir: str = "A7_output",
    verify_subdir: str = "_a7_verify",
    verify_log_prefix: str = "A7 verifiziert",
) -> tuple[bool, Path, Path]:
    a7_input_dir = output_dir / "_a7_input"
    a7_output_dir = output_dir / output_subdir
    a7_verify_dir = output_dir / verify_subdir
    a7_input_dir.mkdir(parents=True, exist_ok=True)
    a7_output_dir.mkdir(parents=True, exist_ok=True)

    staged_input = a7_input_dir / source_image.name
    shutil.copy2(source_image, staged_input)

    ok = bool(
        app._mode_fakelib_manager(
            str(staged_input),
            str(a7_output_dir),
            automation={
                "action": "fakelib_add",
                "fakelib_src": str(fakelib_src),
            },
        )
    )

    actual_out_raw = getattr(app, "task_final_output_path", "")
    actual_out = Path(actual_out_raw) if actual_out_raw else _expected_a7_output_path(staged_input, a7_output_dir)
    extracted_ok, verify_root = _extract_a7_output(app, actual_out, a7_verify_dir, log_prefix=verify_log_prefix) if ok else (False, a7_verify_dir)

    return bool(ok and extracted_ok), actual_out, verify_root


def _run_a7_files_add_automation(app: PS5ConverterGUI, source_exfat: Path, output_dir: Path) -> tuple[bool, Path, Path, str]:
    a7_input_dir = output_dir / "_a7_input_files_add"
    a7_output_dir = output_dir / "A7_files_add_output"
    a7_verify_dir = output_dir / "_a7_verify_files_add"
    a7_input_dir.mkdir(parents=True, exist_ok=True)
    a7_output_dir.mkdir(parents=True, exist_ok=True)

    staged_input = a7_input_dir / source_exfat.name
    shutil.copy2(source_exfat, staged_input)

    marker_name = "A7_AUTOMATION_MARKER.txt"
    marker_file = output_dir / marker_name
    marker_file.write_text("A7 files_add automation marker\n", encoding="utf-8")

    ok = bool(
        app._mode_fakelib_manager(
            str(staged_input),
            str(a7_output_dir),
            automation={
                "action": "files_add",
                "files_to_add": [str(marker_file)],
            },
        )
    )

    actual_out_raw = getattr(app, "task_final_output_path", "")
    actual_out = Path(actual_out_raw) if actual_out_raw else _expected_a7_output_path(staged_input, a7_output_dir)
    extracted_ok, verify_root = _extract_a7_output(app, actual_out, a7_verify_dir, log_prefix="A7 files_add verifiziert") if ok else (False, a7_verify_dir)
    marker_ok = (verify_root / marker_name).is_file()
    return bool(ok and extracted_ok and marker_ok), actual_out, verify_root, marker_name


def _prepare_a7_files_remove_seed(app: PS5ConverterGUI, source_exfat: Path, output_dir: Path) -> tuple[bool, Path, Path, str]:
    add_ok, seeded_out, seeded_verify_dir, marker_name = _run_a7_files_add_automation(app, source_exfat, output_dir)
    return add_ok, seeded_out, seeded_verify_dir, marker_name


def _run_a7_files_remove_automation(app: PS5ConverterGUI, seeded_out: Path, output_dir: Path, marker_name: str) -> tuple[bool, Path, Path, str]:
    seeded_verify_dir = output_dir / "_a7_verify_files_add"
    if not seeded_out.exists():
        return False, seeded_out, seeded_verify_dir, marker_name

    a7_output_dir = output_dir / "A7_files_remove_output"
    a7_verify_dir = output_dir / "_a7_verify_files_remove"
    a7_output_dir.mkdir(parents=True, exist_ok=True)

    ok = bool(
        app._mode_fakelib_manager(
            str(seeded_out),
            str(a7_output_dir),
            automation={
                "action": "files_remove",
                "selected_root_items": [marker_name],
            },
        )
    )

    actual_out_raw = getattr(app, "task_final_output_path", "")
    actual_out = Path(actual_out_raw) if actual_out_raw else _expected_a7_output_path(seeded_out, a7_output_dir)
    extracted_ok, verify_root = _extract_a7_output(app, actual_out, a7_verify_dir, log_prefix="A7 files_remove verifiziert") if ok else (False, a7_verify_dir)
    marker_removed = not (verify_root / marker_name).exists()
    return bool(ok and extracted_ok and marker_removed), actual_out, verify_root, marker_name


def _read_validator_status(report_path: Path) -> str:
    """Liest den semantischen Status aus dem JSON-Bericht des Validators.

    Returns:
        Status wie ``OK``, ``WARNING`` oder ``FAILED``.
        Bei nicht lesbarem Bericht wird ein Leerstring zurückgegeben.
    """
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    status = payload.get("status", "") if isinstance(payload, dict) else ""
    return str(status).strip().upper()


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


def _reset_app_progress_state(app: PS5ConverterGUI) -> None:
    """Setzt die task-weiten Progress-Felder für einen direkten E2E-Methodenaufruf zurück."""
    app.is_running = True
    app.monitor_active = False
    setattr(app, "cancel_requested", False)

    while not app.engine_output_queue.empty():
        try:
            app.engine_output_queue.get_nowait()
        except Exception:
            break

    start_ts = time.monotonic()
    app.task_start_time = start_ts
    app.task_total_source_bytes = 0
    app.task_final_output_path = ""
    app.task_progress = 0.0
    app.task_displayed = 0.0
    app.task_num_steps = 1
    app.task_current_step = 0
    app.task_step_ends = []
    app.task_uncompressed_str = ""
    app.task_stored_str = ""
    app._copy_total_bytes = 0
    app._copy_done_bytes = 0
    app._copy_rate_bps = 0.0
    app._copy_rate_trend = ""
    app._last_engine_output_ts = start_ts
    app._eta_ui_seconds = None
    app._eta_ui_last_ts = start_ts
    app._eta_ui_step = 0
    app._mkpfs_eta_initial = 0.0
    app.progress_engine = ProgressEngine()
    try:
        if hasattr(app, "progress_var"):
            app.progress_var.set(0.0)
        if hasattr(app, "percent_label"):
            app.percent_label.config(text="0%")
        if hasattr(app, "size_label"):
            app.size_label.config(text="")
        if hasattr(app, "status_label"):
            app.status_label.config(text="Bereit.")
    except Exception:
        pass


def _install_threadsafe_tk_shims(root: tk.Tk, app: PS5ConverterGUI) -> Callable[[], None]:
    """Erlaubt Worker-Threads, UI-Callbacks über eine lokale Queue in den Hauptthread zu schedulen."""
    main_thread = threading.main_thread()
    pending: queue.SimpleQueue[tuple[float, Callable[..., Any], tuple[Any, ...]]] = queue.SimpleQueue()
    original_after = root.after
    cached_temp_dir = app._load_runtime_temp_dir()

    class _ThreadSafeVar:
        def __init__(self, value: str) -> None:
            self._value = value
            self._lock = threading.Lock()

        def get(self) -> str:
            with self._lock:
                return self._value

        def set(self, value: str) -> None:
            with self._lock:
                self._value = str(value)

    def _threadsafe_after(delay_ms: int, callback=None, *args):
        if threading.current_thread() is main_thread:
            return original_after(delay_ms, callback, *args)
        if callback is None:
            return None
        due = time.monotonic() + max(0, int(delay_ms)) / 1000.0
        pending.put((due, callback, args))
        return f"e2e_after_{time.monotonic_ns()}"

    def _pump_pending() -> None:
        ready: list[tuple[float, Callable[..., Any], tuple[Any, ...]]] = []
        deferred: list[tuple[float, Callable[..., Any], tuple[Any, ...]]] = []
        now = time.monotonic()

        while True:
            try:
                item = pending.get_nowait()
            except queue.Empty:
                break
            if item[0] <= now:
                ready.append(item)
            else:
                deferred.append(item)

        for item in deferred:
            pending.put(item)

        for _, callback, args in ready:
            try:
                callback(*args)
            except Exception:
                pass

    root.after = _threadsafe_after  # type: ignore[assignment]
    app._get_runtime_temp_dir = lambda: cached_temp_dir  # type: ignore[method-assign]
    if hasattr(app, "temp_path"):
        app.temp_path = _ThreadSafeVar(cached_temp_dir)
    return _pump_pending


def _capture_progress_sample(app: PS5ConverterGUI, started_at: float) -> dict[str, Any]:
    """Erfasst einen kompakten Schnappschuss der aktuellen Task-Fortschrittswerte."""
    try:
        percent_label = str(app.percent_label.cget("text")) if hasattr(app, "percent_label") else ""
    except Exception:
        percent_label = ""
    try:
        size_label = str(app.size_label.cget("text")) if hasattr(app, "size_label") else ""
    except Exception:
        size_label = ""
    try:
        status_label = str(app.status_label.cget("text")) if hasattr(app, "status_label") else ""
    except Exception:
        status_label = ""
    return {
        "elapsed_s": round(max(0.0, time.monotonic() - started_at), 3),
        "task_epoch": round(float(getattr(app, "task_start_time", 0.0) or 0.0), 6),
        "progress": round(float(getattr(app, "task_progress", 0.0) or 0.0), 3),
        "displayed": round(float(getattr(app, "task_displayed", 0.0) or 0.0), 3),
        "step": int(getattr(app, "task_current_step", 0) or 0),
        "steps": int(getattr(app, "task_num_steps", 0) or 0),
        "percent_label": percent_label,
        "size_label": size_label,
        "status_label": status_label,
    }


def _infer_progress_phase_kind(samples: list[dict[str, Any]], phase_index: int) -> str:
    labels = " ".join(str(s.get("status_label", "")).lower() for s in samples)
    if "verifikation" in labels or "verifiziert" in labels or "verify" in labels:
        return "verify"
    return "main" if phase_index == 1 else "verify"


def _split_progress_epochs(samples: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if not samples:
        return []

    groups: list[list[dict[str, Any]]] = [[samples[0]]]
    for sample in samples[1:]:
        prev = groups[-1][-1]
        if float(sample.get("task_epoch", 0.0) or 0.0) > float(prev.get("task_epoch", 0.0) or 0.0):
            groups.append([sample])
        else:
            groups[-1].append(sample)
    return groups


def _summarize_progress(
    samples: list[dict[str, Any]],
    ok: bool,
    *,
    include_phases: bool = True,
    require_final_progress: bool | None = None,
) -> dict[str, Any]:
    """Bewertet einen Progress-Verlauf auf Monotonie, Schrittgrenzen und Endzustand."""
    if not samples:
        checks = {
            "progress_monotonic": False,
            "displayed_monotonic": False,
            "step_monotonic": False,
            "step_in_range": False,
            "displayed_not_ahead": False,
            "saw_activity": False,
            "final_progress_ge_95": not ok,
            "all_pass": False,
        }
        return {
            "sample_count": 0,
            "checks": checks,
            "violations": ["Keine Progress-Samples aufgezeichnet"],
            "preview": [],
            "ui_preview": [],
            "last_non_empty_size": "",
            "last_non_empty_percent": "",
            "last_non_empty_status": "",
            "saw_eta_label": False,
            "saw_remaining_label": False,
            "phases": [],
        }

    violations: list[str] = []
    progress_monotonic = True
    displayed_monotonic = True
    step_monotonic = True
    step_in_range = True
    displayed_not_ahead = True

    for prev, cur in zip(samples, samples[1:]):
        epoch_changed = float(cur.get("task_epoch", 0.0) or 0.0) > float(prev.get("task_epoch", 0.0) or 0.0)
        if epoch_changed:
            continue
        if cur["progress"] + 1e-6 < prev["progress"]:
            progress_monotonic = False
        if cur["displayed"] + 1e-6 < prev["displayed"]:
            displayed_monotonic = False
        if cur["step"] < prev["step"]:
            step_monotonic = False

    for sample in samples:
        step = int(sample["step"])
        steps = max(0, int(sample["steps"]))
        if step < 0 or step > steps:
            step_in_range = False
        is_completed_ui = "abgeschlossen" in str(sample.get("status_label", "")).lower()
        ahead_gap = float(sample["displayed"]) - float(sample["progress"])
        if ahead_gap > 0.35 and not (is_completed_ui and float(sample["progress"]) >= 95.0 and float(sample["displayed"]) <= 100.0):
            displayed_not_ahead = False

    if not progress_monotonic:
        violations.append("task_progress fällt rückwärts")
    if not displayed_monotonic:
        violations.append("task_displayed fällt rückwärts")
    if not step_monotonic:
        violations.append("task_current_step fällt rückwärts")
    if not step_in_range:
        violations.append("task_current_step liegt außerhalb von 0..task_num_steps")
    if not displayed_not_ahead:
        violations.append("task_displayed läuft sichtbar vor task_progress")

    saw_activity = any(s["progress"] > 0.0 or s["step"] > 0 for s in samples)
    if not saw_activity:
        violations.append("kein sichtbarer Progress-Ausschlag")

    if require_final_progress is None:
        require_final_progress = ok

    final_progress = float(samples[-1]["progress"])
    final_progress_ge_95 = (final_progress >= 95.0) if require_final_progress else True
    if require_final_progress and not final_progress_ge_95:
        violations.append(f"Erfolgspfad endet nur bei {final_progress:.2f}% statt >= 95%")

    checks = {
        "progress_monotonic": progress_monotonic,
        "displayed_monotonic": displayed_monotonic,
        "step_monotonic": step_monotonic,
        "step_in_range": step_in_range,
        "displayed_not_ahead": displayed_not_ahead,
        "saw_activity": saw_activity,
        "final_progress_ge_95": final_progress_ge_95,
    }
    checks["all_pass"] = all(checks.values())

    preview = samples[:6]
    if len(samples) > 10:
        preview = samples[:5] + samples[-5:]

    ui_samples = [
        {
            "elapsed_s": s["elapsed_s"],
            "progress": s["progress"],
            "step": s["step"],
            "percent_label": s.get("percent_label", ""),
            "size_label": s.get("size_label", ""),
            "status_label": s.get("status_label", ""),
        }
        for s in samples
        if s.get("percent_label") or s.get("size_label") or s.get("status_label")
    ]
    ui_preview = ui_samples[:8]
    if len(ui_samples) > 14:
        ui_preview = ui_samples[:7] + ui_samples[-7:]

    last_non_empty_size = next((str(s.get("size_label", "")) for s in reversed(ui_samples) if str(s.get("size_label", "")).strip()), "")
    last_non_empty_percent = next((str(s.get("percent_label", "")) for s in reversed(ui_samples) if str(s.get("percent_label", "")).strip()), "")
    last_non_empty_status = next((str(s.get("status_label", "")) for s in reversed(ui_samples) if str(s.get("status_label", "")).strip()), "")
    saw_eta_label = any(
        "ETA" in str(s.get("size_label", ""))
        or "ETA" in str(s.get("status_label", ""))
        for s in ui_samples
    )
    saw_remaining_label = any("Rest:" in str(s.get("size_label", "")) for s in ui_samples)

    summary = {
        "sample_count": len(samples),
        "max_progress": max(float(s["progress"]) for s in samples),
        "max_displayed": max(float(s["displayed"]) for s in samples),
        "max_step": max(int(s["step"]) for s in samples),
        "final": samples[-1],
        "checks": checks,
        "violations": violations,
        "preview": preview,
        "ui_preview": ui_preview,
        "last_non_empty_size": last_non_empty_size,
        "last_non_empty_percent": last_non_empty_percent,
        "last_non_empty_status": last_non_empty_status,
        "saw_eta_label": saw_eta_label,
        "saw_remaining_label": saw_remaining_label,
        "phases": [],
    }

    if include_phases:
        phase_groups = _split_progress_epochs(samples)
        phase_kind_counts: dict[str, int] = {}
        phases: list[dict[str, Any]] = []
        for index, phase_samples in enumerate(phase_groups, start=1):
            phase_kind = _infer_progress_phase_kind(phase_samples, index)
            phase_kind_counts[phase_kind] = phase_kind_counts.get(phase_kind, 0) + 1
            phase_name = phase_kind if phase_kind_counts[phase_kind] == 1 else f"{phase_kind}_{phase_kind_counts[phase_kind]}"
            is_last_phase = index == len(phase_groups)
            phase_summary = _summarize_progress(
                phase_samples,
                ok,
                include_phases=False,
                require_final_progress=(ok and is_last_phase),
            )
            phase_summary["phase_index"] = index
            phase_summary["phase_kind"] = phase_kind
            phase_summary["phase_name"] = phase_name
            phase_summary["epoch"] = float(phase_samples[0].get("task_epoch", 0.0) or 0.0)
            phase_summary["elapsed_start_s"] = float(phase_samples[0].get("elapsed_s", 0.0) or 0.0)
            phase_summary["elapsed_end_s"] = float(phase_samples[-1].get("elapsed_s", 0.0) or 0.0)
            phases.append(phase_summary)
        summary["phases"] = phases

    return summary


def _run_task_with_progress_capture(
    name: str,
    fn: Callable[[], bool],
    result_store: dict[str, str],
    logs: dict[str, str],
    task_log: list[str],
    progress_store: dict[str, Any],
    root: tk.Tk,
    app: PS5ConverterGUI,
) -> bool:
    """Führt einen GUI-Aufgabenpfad im Worker-Thread aus und zeichnet Progress-Zustände auf."""
    _reset_app_progress_state(app)
    started_at = time.monotonic()
    samples: list[dict[str, Any]] = []
    worker_error: list[str] = []
    worker_result: dict[str, bool] = {"ok": False}

    def _worker() -> None:
        try:
            worker_result["ok"] = bool(fn())
        except Exception:
            worker_error.append(traceback.format_exc(limit=6))
            worker_result["ok"] = False
        finally:
            app.is_running = False

    thread = threading.Thread(target=_worker, name=f"e2e_{name}", daemon=True)
    thread.start()

    try:
        while thread.is_alive():
            _pump_pending = getattr(app, "_e2e_pump_pending_callbacks", None)
            if callable(_pump_pending):
                _pump_pending()
            try:
                root.update_idletasks()
                root.update()
            except Exception:
                pass
            try:
                app._update_progress_gui()
            except Exception:
                pass
            samples.append(_capture_progress_sample(app, started_at))
            time.sleep(0.05)

        thread.join()
        for _ in range(3):
            _pump_pending = getattr(app, "_e2e_pump_pending_callbacks", None)
            if callable(_pump_pending):
                _pump_pending()
            try:
                root.update_idletasks()
                root.update()
            except Exception:
                pass
            try:
                app._update_progress_gui()
            except Exception:
                pass
            samples.append(_capture_progress_sample(app, started_at))

        ok = bool(worker_result["ok"] and not worker_error)
        summary = _summarize_progress(samples, ok)
        progress_store[name] = summary
        final_ok = bool(ok and summary["checks"]["all_pass"])
        result_store[name] = "PASS" if final_ok else ("ERROR" if worker_error else "FAIL")

        if not final_ok:
            parts: list[str] = []
            if worker_error:
                parts.append(worker_error[0])
            if summary.get("violations"):
                parts.append("--- progress-violations ---\n" + "\n".join(summary["violations"]))
            if task_log:
                parts.append("--- task-log-tail ---\n" + "".join(task_log)[-4000:])
            logs[name] = "\n\n".join(parts)
        return final_ok
    finally:
        app.monitor_active = False
        app.is_running = False


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
    a7_out = out_dir / "A7_output" / f"{dump_dir.name}.exfat"
    a7_verify_dir = out_dir / "_a7_verify"
    a7_files_add_out = out_dir / "A7_files_add_output" / f"{dump_dir.name}.exfat"
    a7_files_add_verify_dir = out_dir / "_a7_verify_files_add"
    a7_files_add_marker_name = "A7_AUTOMATION_MARKER.txt"
    a7_files_remove_out = out_dir / "A7_files_remove_output" / f"{dump_dir.name}.exfat"
    a7_files_remove_verify_dir = out_dir / "_a7_verify_files_remove"
    a7_files_remove_marker_name = "A7_AUTOMATION_MARKER.txt"
    a7_ffpkg_out = out_dir / "A7_ffpkg_output" / "A7_from_ffpkg.ffpfsc"
    a7_ffpkg_verify_dir = out_dir / "_a7_verify_ffpkg"
    existing_a7_source = _find_existing_exfat_artifact(repo, dump_dir.name)
    if ffpkg_path and ffpkg_path.is_file():
        a6_out = out_dir / f"{ffpkg_path.stem}.ffpfsc"
        a7_ffpkg_out = out_dir / "A7_ffpkg_output" / f"{ffpkg_path.stem}.ffpfsc"

    results: dict[str, str] = {}
    logs: dict[str, str] = {}
    progress_checks: dict[str, Any] = {}

    root = tk.Tk()
    root.withdraw()
    app = PS5ConverterGUI(root)
    app._e2e_pump_pending_callbacks = _install_threadsafe_tk_shims(root, app)
    fakelib_src = _find_fakelib_source(repo)
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

    is_admin = _is_admin()

    try:
        if not dump_dir.is_dir():
            raise FileNotFoundError(f"Dump-Ordner nicht gefunden: {dump_dir}")

        if selected_task is not None:
            single_results: dict[str, str] = {}
            single_logs: dict[str, str] = {}
            single_progress_checks: dict[str, Any] = {}

            def _single_run(label: str, fn) -> None:
                _prep()
                _run_task_with_progress_capture(
                    label,
                    fn,
                    single_results,
                    single_logs,
                    _task_log,
                    single_progress_checks,
                    root,
                    app,
                )

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
                a7_source = a2_out if a2_out.exists() else existing_a7_source
                if a7_source is None and is_admin:
                    if not a1_out.exists():
                        _prep()
                        if not app._mode_pack_folder(str(dump_dir), str(out_dir)):
                            raise RuntimeError("A7-Vorbereitung fehlgeschlagen: A1 konnte nicht erstellt werden")
                    if not a2_out.exists():
                        _prep()
                        if not app._mode_unpack_to_exfat(str(a1_out), str(out_dir)):
                            raise RuntimeError("A7-Vorbereitung fehlgeschlagen: A2 konnte nicht erstellt werden")
                    a7_source = a2_out

                if a7_source is None:
                    single_results["A7_fakelib_manager"] = "SKIPPED_NEEDS_ADMIN_OR_EXFAT_ARTIFACT"
                else:

                    a7_state: dict[str, Path] = {}

                    def _run_single_a7() -> bool:
                        ok, actual_out, verify_dir = _run_a7_automation(app, a7_source, fakelib_src, out_dir)
                        a7_state["actual_out"] = actual_out
                        a7_state["verify_dir"] = verify_dir
                        return ok

                    _single_run("A7_fakelib_manager", _run_single_a7)
                    if "actual_out" in a7_state:
                        a7_out = a7_state["actual_out"]
                    if "verify_dir" in a7_state:
                        a7_verify_dir = a7_state["verify_dir"]

                    a7_files_state: dict[str, Path | str] = {}

                    def _run_single_a7_files_add() -> bool:
                        ok, actual_out, verify_dir, marker_name = _run_a7_files_add_automation(app, a7_source, out_dir)
                        a7_files_state["actual_out"] = actual_out
                        a7_files_state["verify_dir"] = verify_dir
                        a7_files_state["marker_name"] = marker_name
                        return ok

                    _single_run("A7_files_add", _run_single_a7_files_add)
                    if "actual_out" in a7_files_state:
                        a7_files_add_out = a7_files_state["actual_out"]  # type: ignore[assignment]
                    if "verify_dir" in a7_files_state:
                        a7_files_add_verify_dir = a7_files_state["verify_dir"]  # type: ignore[assignment]
                    if "marker_name" in a7_files_state:
                        a7_files_add_marker_name = str(a7_files_state["marker_name"])

                    a7_remove_state: dict[str, Path | str] = {}
                    _prep()
                    remove_seed_ok, remove_seed_out, remove_seed_verify_dir, remove_seed_marker = _prepare_a7_files_remove_seed(app, a7_source, out_dir)
                    if not remove_seed_ok:
                        single_results["A7_files_remove"] = "FAIL"
                        single_logs["A7_files_remove"] = "Seed-Erzeugung fuer files_remove fehlgeschlagen"
                    else:
                        a7_files_remove_out = remove_seed_out
                        a7_files_remove_verify_dir = remove_seed_verify_dir
                        a7_files_remove_marker_name = remove_seed_marker

                        def _run_single_a7_files_remove() -> bool:
                            ok, actual_out, verify_dir, marker_name = _run_a7_files_remove_automation(app, remove_seed_out, out_dir, remove_seed_marker)
                            a7_remove_state["actual_out"] = actual_out
                            a7_remove_state["verify_dir"] = verify_dir
                            a7_remove_state["marker_name"] = marker_name
                            return ok

                        _single_run("A7_files_remove", _run_single_a7_files_remove)
                    if "actual_out" in a7_remove_state:
                        a7_files_remove_out = a7_remove_state["actual_out"]  # type: ignore[assignment]
                    if "verify_dir" in a7_remove_state:
                        a7_files_remove_verify_dir = a7_remove_state["verify_dir"]  # type: ignore[assignment]
                    if "marker_name" in a7_remove_state:
                        a7_files_remove_marker_name = str(a7_remove_state["marker_name"])

                if ffpkg_path and ffpkg_path.is_file() and is_admin:
                    a7_ffpkg_state: dict[str, Path] = {}

                    def _run_single_a7_ffpkg() -> bool:
                        ok, actual_out, verify_dir = _run_a7_automation(
                            app,
                            ffpkg_path,
                            fakelib_src,
                            out_dir,
                            output_subdir="A7_ffpkg_output",
                            verify_subdir="_a7_verify_ffpkg",
                            verify_log_prefix="A7 .ffpkg verifiziert",
                        )
                        a7_ffpkg_state["actual_out"] = actual_out
                        a7_ffpkg_state["verify_dir"] = verify_dir
                        return ok

                    _single_run("A7_ffpkg_fakelib_manager", _run_single_a7_ffpkg)
                    if "actual_out" in a7_ffpkg_state:
                        a7_ffpkg_out = a7_ffpkg_state["actual_out"]
                    if "verify_dir" in a7_ffpkg_state:
                        a7_ffpkg_verify_dir = a7_ffpkg_state["verify_dir"]
                elif ffpkg_path and ffpkg_path.is_file():
                    single_results["A7_ffpkg_fakelib_manager"] = "SKIPPED_NEEDS_ADMIN"
            elif selected_task == "A8":
                _single_run("A8_GUI_dump_validator", lambda: app._mode_dump_validator(str(dump_dir)))
                a8_ok_json = out_dir / "a8_ok.json"
                a8_fail_json = out_dir / "a8_fail.json"
                ok_cli_ok, ok_tail = _run_cli_dump_validator(dump_dir, a8_ok_json)
                ok_status = _read_validator_status(a8_ok_json)
                ok_semantic = ok_status in {"OK", "WARNING"}
                single_results["A8_OK_dump_validator"] = "PASS" if (ok_cli_ok or ok_semantic) else "FAIL"
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
                "progress_checks": single_progress_checks,
                "selected_task": selected_task,
            }
            report_path = out_dir / f"e2e_report_{selected_task.lower()}.json"
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps({"output_dir": str(out_dir), "report": str(report_path), "results": single_results}, indent=2, ensure_ascii=False))
            return 0

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
            ok_a1 = _run_task_with_progress_capture(
                "A1_pack_folder_to_ffpfsc",
                lambda: app._mode_pack_folder(str(dump_dir), str(out_dir)),
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )

        if not is_admin:
            ok_a2 = False
            results["A2_ffpfsc_to_exfat"] = "SKIPPED_NEEDS_ADMIN"
            results["A3_exfat_to_ffpfsc"] = "SKIPPED_DEPENDS_ON_A2"
            results["A4_ffpfsc_to_game_folder"] = "SKIPPED_DEPENDS_ON_A3"
            results["A5_exfat_to_game_folder"] = "SKIPPED_DEPENDS_ON_A2"
        elif ok_a1 and a1_out.exists():
            _prep()
            ok_a2 = _run_task_with_progress_capture(
                "A2_ffpfsc_to_exfat",
                lambda: app._mode_unpack_to_exfat(str(a1_out), str(out_dir)),
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
        else:
            ok_a2 = False
            results["A2_ffpfsc_to_exfat"] = "SKIPPED_DEPENDS_ON_A1"

        if not is_admin:
            ok_a3 = False
        elif ok_a2 and a2_out.exists():
            _prep()
            ok_a3 = _run_task_with_progress_capture(
                "A3_exfat_to_ffpfsc",
                lambda: app._mode_pack_file(str(a2_out), str(a3_out)),
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
        else:
            ok_a3 = False
            results["A3_exfat_to_ffpfsc"] = "SKIPPED_DEPENDS_ON_A2"

        if not is_admin:
            pass
        elif ok_a3 and a3_out.exists():
            _prep()
            _run_task_with_progress_capture(
                "A4_ffpfsc_to_game_folder",
                lambda: app._mode_unpack_to_game_folder(str(a3_out), str(out_dir)),
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
        else:
            results["A4_ffpfsc_to_game_folder"] = "SKIPPED_DEPENDS_ON_A3"

        if not is_admin:
            pass
        elif ok_a2 and a2_out.exists():
            _prep()
            _run_task_with_progress_capture(
                "A5_exfat_to_game_folder",
                lambda: app._mode_exfat_to_folder(str(a2_out), str(a5_out)),
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
        else:
            results["A5_exfat_to_game_folder"] = "SKIPPED_DEPENDS_ON_A2"

        if ffpkg_path and ffpkg_path.is_file():
            _prep()
            _run_task_with_progress_capture(
                "A6_ffpkg_to_ffpfsc",
                lambda: app._mode_ffpkg_to_ffpfsc(str(ffpkg_path), str(out_dir)),
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
            _actual_a6 = getattr(app, "task_final_output_path", "")
            if _actual_a6:
                _actual_path = Path(_actual_a6)
                if not _actual_path.is_absolute():
                    _actual_path = (repo / _actual_path).resolve()
                a6_out = _actual_path
        else:
            results["A6_ffpkg_to_ffpfsc"] = "SKIPPED_NO_FFPKG"

        a7_source = a2_out if (ok_a2 and a2_out.exists()) else existing_a7_source
        if a7_source is not None:
            a7_state: dict[str, Path] = {}

            def _run_full_a7() -> bool:
                ok, actual_out, verify_dir = _run_a7_automation(app, a7_source, fakelib_src, out_dir)
                a7_state["actual_out"] = actual_out
                a7_state["verify_dir"] = verify_dir
                return ok

            _prep()
            _run_task_with_progress_capture(
                "A7_fakelib_manager",
                _run_full_a7,
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
            if "actual_out" in a7_state:
                a7_out = a7_state["actual_out"]
            if "verify_dir" in a7_state:
                a7_verify_dir = a7_state["verify_dir"]

            a7_files_state: dict[str, Path | str] = {}

            def _run_full_a7_files_add() -> bool:
                ok, actual_out, verify_dir, marker_name = _run_a7_files_add_automation(app, a7_source, out_dir)
                a7_files_state["actual_out"] = actual_out
                a7_files_state["verify_dir"] = verify_dir
                a7_files_state["marker_name"] = marker_name
                return ok

            _prep()
            _run_task_with_progress_capture(
                "A7_files_add",
                _run_full_a7_files_add,
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
            if "actual_out" in a7_files_state:
                a7_files_add_out = a7_files_state["actual_out"]  # type: ignore[assignment]
            if "verify_dir" in a7_files_state:
                a7_files_add_verify_dir = a7_files_state["verify_dir"]  # type: ignore[assignment]
            if "marker_name" in a7_files_state:
                a7_files_add_marker_name = str(a7_files_state["marker_name"])

            a7_remove_state: dict[str, Path | str] = {}
            _prep()
            remove_seed_ok, remove_seed_out, remove_seed_verify_dir, remove_seed_marker = _prepare_a7_files_remove_seed(app, a7_source, out_dir)
            if not remove_seed_ok:
                results["A7_files_remove"] = "FAIL"
                logs["A7_files_remove"] = "Seed-Erzeugung fuer files_remove fehlgeschlagen"
            else:
                a7_files_remove_out = remove_seed_out
                a7_files_remove_verify_dir = remove_seed_verify_dir
                a7_files_remove_marker_name = remove_seed_marker

                def _run_full_a7_files_remove() -> bool:
                    ok, actual_out, verify_dir, marker_name = _run_a7_files_remove_automation(app, remove_seed_out, out_dir, remove_seed_marker)
                    a7_remove_state["actual_out"] = actual_out
                    a7_remove_state["verify_dir"] = verify_dir
                    a7_remove_state["marker_name"] = marker_name
                    return ok

                _prep()
                _run_task_with_progress_capture(
                    "A7_files_remove",
                    _run_full_a7_files_remove,
                    results,
                    logs,
                    _task_log,
                    progress_checks,
                    root,
                    app,
                )
            if "actual_out" in a7_remove_state:
                a7_files_remove_out = a7_remove_state["actual_out"]  # type: ignore[assignment]
            if "verify_dir" in a7_remove_state:
                a7_files_remove_verify_dir = a7_remove_state["verify_dir"]  # type: ignore[assignment]
            if "marker_name" in a7_remove_state:
                a7_files_remove_marker_name = str(a7_remove_state["marker_name"])

        else:
            results["A7_fakelib_manager"] = "SKIPPED_DEPENDS_ON_A2_OR_EXISTING_EXFAT"
            results["A7_files_add"] = "SKIPPED_DEPENDS_ON_A2_OR_EXISTING_EXFAT"
            results["A7_files_remove"] = "SKIPPED_DEPENDS_ON_A2_OR_EXISTING_EXFAT"

        if ffpkg_path and ffpkg_path.is_file() and is_admin:
            a7_ffpkg_state: dict[str, Path] = {}

            def _run_full_a7_ffpkg() -> bool:
                ok, actual_out, verify_dir = _run_a7_automation(
                    app,
                    ffpkg_path,
                    fakelib_src,
                    out_dir,
                    output_subdir="A7_ffpkg_output",
                    verify_subdir="_a7_verify_ffpkg",
                    verify_log_prefix="A7 .ffpkg verifiziert",
                )
                a7_ffpkg_state["actual_out"] = actual_out
                a7_ffpkg_state["verify_dir"] = verify_dir
                return ok

            _prep()
            _run_task_with_progress_capture(
                "A7_ffpkg_fakelib_manager",
                _run_full_a7_ffpkg,
                results,
                logs,
                _task_log,
                progress_checks,
                root,
                app,
            )
            if "actual_out" in a7_ffpkg_state:
                a7_ffpkg_out = a7_ffpkg_state["actual_out"]
            if "verify_dir" in a7_ffpkg_state:
                a7_ffpkg_verify_dir = a7_ffpkg_state["verify_dir"]
        elif ffpkg_path and ffpkg_path.is_file():
            results["A7_ffpkg_fakelib_manager"] = "SKIPPED_NEEDS_ADMIN"

        _prep()
        _run_task_with_progress_capture(
            "A8_GUI_dump_validator",
            lambda: app._mode_dump_validator(str(dump_dir)),
            results,
            logs,
            _task_log,
            progress_checks,
            root,
            app,
        )

        a8_ok_json = out_dir / "a8_ok.json"
        a8_fail_json = out_dir / "a8_fail.json"

        ok_cli_ok, ok_tail = _run_cli_dump_validator(dump_dir, a8_ok_json)
        ok_status = _read_validator_status(a8_ok_json)
        ok_semantic = ok_status in {"OK", "WARNING"}
        results["A8_OK_dump_validator"] = "PASS" if (ok_cli_ok or ok_semantic) else "FAIL"
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
        "A7_exists": a7_out.exists(),
        "A7_size_gt_0": a7_out.exists() and a7_out.stat().st_size > 0,
        "A7_has_fakelib_ampr": (a7_verify_dir / "fakelib" / "libSceAmpr.sprx").exists(),
        "A7_has_ampr_index": (a7_verify_dir / "ampr_emu.index").exists(),
        "A7_files_add_exists": a7_files_add_out.exists(),
        "A7_files_add_size_gt_0": a7_files_add_out.exists() and a7_files_add_out.stat().st_size > 0,
        "A7_files_add_marker": (a7_files_add_verify_dir / a7_files_add_marker_name).exists(),
        "A7_files_remove_exists": a7_files_remove_out.exists(),
        "A7_files_remove_size_gt_0": a7_files_remove_out.exists() and a7_files_remove_out.stat().st_size > 0,
        "A7_files_remove_marker_absent": not (a7_files_remove_verify_dir / a7_files_remove_marker_name).exists(),
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
            "A7": str(a7_out),
            "A7_verify": str(a7_verify_dir),
            "A7_files_add": str(a7_files_add_out),
            "A7_files_add_verify": str(a7_files_add_verify_dir),
            "A7_files_remove": str(a7_files_remove_out),
            "A7_files_remove_verify": str(a7_files_remove_verify_dir),
            "A8_OK": str(out_dir / "a8_ok.json"),
            "A8_FAIL": str(out_dir / "a8_fail.json"),
        },
        "artifact_checks": artifact_checks,
        "progress_checks": progress_checks,
        "output_dir": str(out_dir),
        "logs": logs,
    }

    report_path = out_dir / "e2e_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(json.dumps({"output_dir": str(out_dir), "report": str(report_path), "results": results}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
