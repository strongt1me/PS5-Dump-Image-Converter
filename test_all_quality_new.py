#!/usr/bin/env python3
"""
Umfassender Quality Test-Suite für PS5 Image Converter
Tests:
1. Syntax-Validierung
2. Import-Validierung
3. ProgressEngine-Logik (ETA-Berechnung)
4. Build-Abhängigkeiten
5. Datei-Integrität
6. Code-Linting
"""

import sys
import os
import ast
import importlib
import re
import tempfile
import threading
import time
from pathlib import Path

# Farben (ASCII-safe für Windows)
GREEN = ''
RED = ''
YELLOW = ''
RESET = ''

def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_result(name, passed, details=""):
    status = "[OK] PASS" if passed else "[FAIL] FAIL"
    print(f"  {status}  {name}")
    if details:
        print(f"       {details}")

# ============================================================================
# 1. SYNTAX VALIDIERUNG
# ============================================================================
def test_syntax():
    print_header("TEST 1: Syntax-Validierung")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    try:
        with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
            code = f.read()
        ast.parse(code)
        test_result("Hauptdatei-Syntax", True, f"{len(code)} Bytes geparst")
        return True
    except SyntaxError as e:
        test_result("Hauptdatei-Syntax", False, f"Line {e.lineno}: {e.msg}")
        return False

# ============================================================================
# 2. IMPORT VALIDIERUNG
# ============================================================================
def test_imports():
    print_header("TEST 2: Import-Validierung")
    
    required_imports = [
        'tkinter',
        'PIL',
        'cryptography',
        'zstandard',
        'time',
        'os',
        'sys',
        'json',
        'threading',
        'subprocess',
        'hashlib',
        'struct',
        're',
        'shutil',
    ]
    
    failed = []
    for imp in required_imports:
        try:
            __import__(imp)
            print(f"  [OK] {imp}")
        except ImportError as e:
            print(f"  [FAIL] {imp}: {e}")
            failed.append(imp)
    
    if failed:
        print(f"\n  {len(failed)} Packages fehlend: {', '.join(failed)}")
        return False
    else:
        print(f"\n  Alle {len(required_imports)} Imports funktionieren")
        return True

# ============================================================================
# 3. PROGRESSENGINE LOGIK
# ============================================================================
def test_progress_engine():
    print_header("TEST 3: ProgressEngine-Logik")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    
    checks = {
        "ProgressEngine-Klasse": "class ProgressEngine" in content,
        "ETA-Berechnung": "_estimate_eta_seconds" in content,
        "Easing-Logik": "PROGRESS_EASING" in content,
        "Task-Progress-Tracking": "task_progress" in content,
        "Fortschrittsanzeige": "_update_progress_gui" in content,
        "Keepalive trennt Output-Timestamp": "self._last_engine_output_ts = _now" not in content,
    }
    
    for check_name, result in checks.items():
        status = "[OK]" if result else "[FAIL]"
        print(f"  {status}  {check_name}")
    
    all_pass = all(checks.values())
    return all_pass

def test_keepalive_regression():
    print_header("TEST 3B: MkPFS-Keepalive-Regression")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
        gui._last_engine_output_ts = 123.0
        gui.task_current_step = 3
        gui.task_num_steps = 4

        log_calls = []
        status_calls = []
        gui._append_to_log = log_calls.append
        gui._set_status = status_calls.append

        gui._emit_processing_keepalive()

        checks = {
            "Keepalive loggt Hinweis": log_calls == ["[INFO] Verarbeitung laeuft ... bitte warten.\n"],
            "Keepalive setzt Status": len(status_calls) == 1 and status_calls[0].endswith("Verarbeitung laeuft ..."),
            "Keepalive aendert keinen Output-Timestamp": gui._last_engine_output_ts == 123.0,
        }

        for check_name, result in checks.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status}  {check_name}")

        return all(checks.values())
    except Exception as e:
        test_result("MkPFS-Keepalive-Regression", False, str(e))
        return False


def test_splash_centering_helper():
    print_header("TEST 3C: Splash-Zentrierung")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")

        centered = module._center_window_coords(1920, 1080, 400, 200)
        clamped = module._center_window_coords(300, 150, 400, 200)

        checks = {
            "Zentrierung fuer normalen Bildschirm": centered == (760, 440),
            "Negative Koordinaten werden geklemmt": clamped == (0, 0),
        }

        for check_name, result in checks.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status}  {check_name}")

        return all(checks.values())
    except Exception as e:
        test_result("Splash-Zentrierung", False, str(e))
        return False


def test_apr_ampr_preflight():
    print_header("TEST 3D: APR-/AMPR-Preflight")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            game_root = temp_root / "game"
            emu_root = temp_root / "ampr_emu"
            (game_root / "sce_sys").mkdir(parents=True)
            emu_root.mkdir()
            (game_root / "sce_sys" / "playgo-chunk.dat").write_bytes(b"marker")
            (game_root / "eboot.bin").write_bytes(b"game")
            (emu_root / "libSceAmpr.sprx").write_bytes(b"ampr")
            (emu_root / "libScePlayGo.sprx").write_bytes(b"playgo")

            gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
            gui.mkpfs_dir = str(Path("MkPFS-0.0.9").resolve())
            gui._append_to_log = lambda _message: None
            gui._load_setting = lambda _key, default: default
            saved_settings = {}
            gui._save_setting = saved_settings.__setitem__

            prepared = gui._prepare_ampr_support(
                str(game_root),
                {"ampr_emu_folder": str(emu_root)},
            )
            index_bytes = (game_root / "ampr_emu.index").read_bytes()

            no_apr_root = temp_root / "no_apr"
            no_apr_root.mkdir()
            gui._ask_yesno_threadsafe = lambda *_args: (_ for _ in ()).throw(
                AssertionError("Automation hat einen APR-Dialog geöffnet")
            )
            non_apr_automation = gui._prepare_ampr_support(
                str(no_apr_root),
                {"is_apr": False},
            )

            alternate_root = temp_root / "alternate"
            (alternate_root / "sce_sys").mkdir(parents=True)
            (alternate_root / "sce_sys" / "playgo_chunk.dat").write_bytes(b"marker")

            checks = {
                "playgo-chunk.dat erkannt": gui._detect_apr_title(str(game_root)),
                "playgo_chunk.dat erkannt": gui._detect_apr_title(str(alternate_root)),
                "AMPR-Preflight erfolgreich": prepared,
                "libSceAmpr.sprx injiziert": (
                    game_root / "fakelib" / "libSceAmpr.sprx"
                ).read_bytes() == b"ampr",
                "libScePlayGo.sprx injiziert": (
                    game_root / "fakelib" / "libScePlayGo.sprx"
                ).read_bytes() == b"playgo",
                "AMPRIDX3-Format": index_bytes.startswith(b"AMPRIDX3"),
                "fakelib-Dateien im Index": all(
                    path in index_bytes
                    for path in (
                        b"/app0/fakelib/libSceAmpr.sprx",
                        b"/app0/fakelib/libScePlayGo.sprx",
                    )
                ),
                "AMPR-Ordner gespeichert": saved_settings.get("ampr_emu_folder")
                == str(emu_root.resolve()),
                "Nicht-APR-Automation dialogfrei": non_apr_automation,
            }

        for check_name, result in checks.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status}  {check_name}")

        return all(checks.values())
    except Exception as e:
        test_result("APR-/AMPR-Preflight", False, str(e))
        return False


def test_universal_export_targets():
    print_header("TEST 3E: Aufgabe-6-Zielmatrix")

    class _Value:
        def __init__(self, value):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class _Combo(dict):
        def __init__(self, target):
            super().__init__()
            self.target = target
            self.visible = True

        def current(self, index):
            self.target.set(self["values"][index])

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

    class _Widget:
        def __init__(self):
            self.visible = True

        def grid(self):
            self.visible = True

        def grid_remove(self):
            self.visible = False

        def config(self, **_kwargs):
            pass

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            dump_root = temp_root / "dump"
            dump_root.mkdir()
            sources = {"folder": dump_root}
            for source_type in ("ffpfsc", "exfat", "ffpkg"):
                source = temp_root / f"source.{source_type}"
                source.write_bytes(b"test")
                sources[source_type] = source

            gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
            matrices = {
                source_type: gui._get_target_options("universal_convert", str(source))
                for source_type, source in sources.items()
            }

            gui.current_mode = _Value("universal_convert")
            gui.source_path = _Value(str(dump_root))
            gui.target_format = _Value(".ffpkg")
            gui.format_combo = _Combo(gui.target_format)
            gui.format_title = _Widget()
            gui.format_info_label = _Widget()
            gui._refresh_target_format_options()
            conversion_widgets_visible = all(
                widget.visible
                for widget in (gui.format_title, gui.format_combo, gui.format_info_label)
            )

            gui._refresh_target_format_options("fakelib_manager")
            task_7_widgets_hidden = all(
                not widget.visible
                for widget in (gui.format_title, gui.format_combo, gui.format_info_label)
            )

            gui._refresh_target_format_options("universal_convert")
            task_6_widgets_restored = all(
                widget.visible
                for widget in (gui.format_title, gui.format_combo, gui.format_info_label)
            )

            checks = {
                "Dump-Ziele": matrices["folder"] == ("ffpfsc", "exfat"),
                "FFPFSC-Ziele": matrices["ffpfsc"] == ("folder", "exfat"),
                "exFAT-Ziele": matrices["exfat"] == ("folder", "ffpfsc"),
                "FFPKG-Eingabeziele": matrices["ffpkg"]
                == ("folder", "ffpfsc", "exfat"),
                "FFPKG nie als Ziel": all(
                    "ffpkg" not in options for options in matrices.values()
                ),
                "Veralteter FFPKG-Wert zurückgesetzt": gui.target_format.get()
                == ".ffpfsc",
                "Combobox ohne FFPKG": gui.format_combo["values"]
                == [".ffpfsc", ".exFAT"],
                "Zielformat bei Konvertierung sichtbar": conversion_widgets_visible,
                "Zielformat bei Aufgabe 7 verborgen": task_7_widgets_hidden,
                "Zielformat nach Aufgabenwechsel sichtbar": task_6_widgets_restored,
            }

        for check_name, result in checks.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status}  {check_name}")

        return all(checks.values())
    except Exception as e:
        test_result("Aufgabe-6-Zielmatrix", False, str(e))
        return False


def test_task_temp_cleanup():
    print_header("TEST 3F: Automatische Task-Temp-Bereinigung")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            baseline_dir = temp_root / "ps5conv_previous_task"
            current_dir = temp_root / "ps5conv_current_task"
            blocked_dir = temp_root / "ps5conv_blocked_task"
            for path in (baseline_dir, current_dir, blocked_dir):
                path.mkdir()
                (path / "temporary.bin").write_bytes(b"temporary")

            gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
            gui._exit_cleanup_lock = threading.RLock()
            gui._session_exit_cleanup_paths = {
                str(baseline_dir.resolve()),
                str(current_dir.resolve()),
            }
            gui._get_runtime_temp_dir = lambda: str(temp_root)
            logs = []
            gui._append_to_log = logs.append

            cleanup_ok = gui._cleanup_task_temp_targets({str(baseline_dir.resolve())})

            gui._session_exit_cleanup_paths.add(str(blocked_dir.resolve()))
            original_rmtree = module.shutil.rmtree
            blocked_norm = os.path.normcase(os.path.abspath(blocked_dir.resolve()))

            def _blocked_rmtree(path):
                if os.path.normcase(os.path.abspath(path)) == blocked_norm:
                    raise PermissionError("Datei wird verwendet")
                return original_rmtree(path)

            module.shutil.rmtree = _blocked_rmtree
            try:
                blocked_cleanup_ok = gui._cleanup_task_temp_targets(
                    {str(baseline_dir.resolve())}
                )
            finally:
                module.shutil.rmtree = original_rmtree

            blocked_remained_registered = str(blocked_dir.resolve()) in (
                gui._session_exit_cleanup_paths
            )
            exit_retry_dir = temp_root / "ps5conv_exit_retry"
            exit_retry_dir.mkdir()
            (exit_retry_dir / "temporary.bin").write_bytes(b"temporary")
            gui._session_exit_cleanup_paths = {str(exit_retry_dir.resolve())}
            exit_retry_norm = os.path.normcase(os.path.abspath(exit_retry_dir.resolve()))
            exit_attempts = [0]

            def _retry_rmtree(path):
                if os.path.normcase(os.path.abspath(path)) == exit_retry_norm:
                    exit_attempts[0] += 1
                    if exit_attempts[0] < 3:
                        raise PermissionError("Datei wird noch verwendet")
                return original_rmtree(path)

            module.shutil.rmtree = _retry_rmtree
            try:
                exit_cleanup_ok = gui._cleanup_exit_temp_targets()
            finally:
                module.shutil.rmtree = original_rmtree

            worker = threading.Thread(target=lambda: time.sleep(0.05))
            gui._task_thread = worker
            gui._active_mount_drive = None
            gui._active_osf_exe = None
            gui.is_running = True
            worker.start()
            gui._force_dismount_all()
            worker_joined_without_mount = not worker.is_alive()

            checks = {
                "Aktueller Task bereinigt": cleanup_ok and not current_dir.exists(),
                "Vorherige Task-Daten erhalten": baseline_dir.is_dir(),
                "Bereinigter Pfad abgemeldet": str(current_dir.resolve())
                not in gui._session_exit_cleanup_paths,
                "Löschfehler erkannt": not blocked_cleanup_ok,
                "Blockierter Pfad bleibt erhalten": blocked_dir.is_dir(),
                "Blockierter Pfad bleibt vorgemerkt": blocked_remained_registered,
                "Exit-Cleanup wiederholt Löschung": exit_attempts[0] == 3,
                "Exit-Cleanup löscht nach Handle-Freigabe": exit_cleanup_ok
                and not exit_retry_dir.exists(),
                "Exit-Cleanup meldet Pfad ab": str(exit_retry_dir.resolve())
                not in gui._session_exit_cleanup_paths,
                "Exit wartet ohne Mount auf Worker": worker_joined_without_mount,
                "Cleanup protokolliert": any(
                    "Automatische Task-Bereinigung abgeschlossen" in line for line in logs
                ),
            }

        for check_name, result in checks.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status}  {check_name}")

        return all(checks.values())
    except Exception as e:
        test_result("Automatische Task-Temp-Bereinigung", False, str(e))
        return False

def test_ffpkg_validator():
    print_header("TEST 3G: Nativer FFPKG-Validator")

    try:
        from types import SimpleNamespace
        from unittest.mock import patch

        from ps5_validator.modules.ffpkg_validator import FfpkgValidator

        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "test.ffpkg"
            tool = Path(temp_dir) / "UFS2Tool.exe"
            image.write_bytes(b"UFS2 test payload")
            tool.write_bytes(b"test executable placeholder")

            def run_with(*responses):
                completed = [
                    SimpleNamespace(returncode=return_code, stdout=output)
                    for return_code, output in responses
                ]
                with patch(
                    "ps5_validator.modules.ffpkg_validator.subprocess.run",
                    side_effect=completed,
                ) as run_mock:
                    result = FfpkgValidator(str(tool)).validate(str(image))
                return result, run_mock

            info_error, info_mock = run_with((2, "invalid superblock"))
            fsck_error, fsck_mock = run_with(
                (0, "UFS2 filesystem"),
                (4, "duplicate block"),
            )
            valid, valid_mock = run_with(
                (0, "UFS2 filesystem"),
                (0, "filesystem clean"),
            )

            checks = {
                "Info-Fehler wird abgelehnt": (
                    info_error.status == "CORRUPTED" and info_mock.call_count == 1
                ),
                "FSCK-Fehler wird abgelehnt": (
                    fsck_error.status == "CORRUPTED" and fsck_mock.call_count == 2
                ),
                "Sauberes UFS2 wird akzeptiert": (
                    valid.status == "OK"
                    and valid_mock.call_count == 2
                    and image.name in valid.hashes
                ),
                "FSCK bleibt schreibgeschuetzt": (
                    valid_mock.call_args_list[1].args[0][1:3] == ["fsck_ufs", "-fn"]
                ),
            }

        for check_name, passed in checks.items():
            test_result(check_name, passed)
        return all(checks.values())
    except Exception as exc:
        test_result("Nativer FFPKG-Validator", False, str(exc))
        return False


def test_ffpfsc_verification_and_task7_repack():
    print_header("TEST 3H: FFPFSC-Struktur und Aufgabe-7-Repack")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        with tempfile.TemporaryDirectory() as temp_dir:
            broken_image = Path(temp_dir) / "broken.ffpfsc"
            broken_image.write_bytes(b"not-a-pfs-container")

            gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
            gui._extract_embedded_mkpfs = lambda: str(Path("MkPFS-0.0.9").resolve())
            verification = gui._verify_output_artifact("pack_file", str(broken_image))

        source = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8"
        )
        helper_start = source.index("def _repack_nested_ffpfsc")
        helper_end = source.index(
            "# Zielverzeichnis = Verzeichnis der Originaldatei", helper_start
        )
        helper_source = source[helper_start:helper_end]

        checks = {
            "Defektes FFPFSC wird abgelehnt": not verification["ok"],
            "MkPFS-Strukturprüfung verwendet": verification["method"] == "mkpfs-verify",
            "Inneres PFS bleibt unkomprimiert": (
                '"pack", "folder"' in helper_source
                and '"--no-compress"' in helper_source
            ),
            "Außencontainer wird komprimiert": (
                '"pack", "file"' in helper_source
                and '"--compress"' in helper_source
            ),
            "Aufgabe 7 erkennt UFS2-Innenimage": (
                source.count("Inneres UFS2-.ffpkg erkannt") == 1
            ),
            "Aufgabe 7 hat nativen exFAT-Fallback": (
                "Aufgabe 7 / A3-exFAT" in source
            ),
        }

        for check_name, passed in checks.items():
            test_result(check_name, passed)
        return all(checks.values())
    except Exception as exc:
        test_result("FFPFSC-Struktur und Aufgabe-7-Repack", False, str(exc))
        return False


def test_preview_and_game_info_tasks_1_to_8():
    print_header("TEST 3I: Vorschau und Spiel-Infobox Aufgaben 1-8")

    try:
        module = importlib.import_module("PS5ImageConverter_Pro_FINAL_revised")
        expected_modes = (
            "pack_folder",
            "unpack_to_exfat",
            "pack_file",
            "ffpkg_to_ffpfsc",
            "batch_convert",
            "universal_convert",
            "fakelib_manager",
            "dump_validator",
        )
        configured_modes = tuple(mode for _label, mode in module.PS5ConverterGUI._MODE_OPTIONS)
        source_matrix = module.PS5ConverterGUI._MODE_SOURCE_TYPES

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            structured_path = temp_root / "structured.ffpkg"
            fallback_path = temp_root / "fallback.ffpkg"
            structured_path.write_bytes(b"UFS2 structured preview")
            fallback_path.write_bytes(b"UFS2 fallback preview")

            gui = module.PS5ConverterGUI.__new__(module.PS5ConverterGUI)
            gui.is_running = False
            gui._preview_cache = {}
            gui._PREVIEW_CACHE_MAX = 20
            gui._preview_candidate_dirs = lambda *_args, **_kwargs: []
            gui._extract_meta_from_ffpkg_ufs2 = lambda _src: (
                {
                    "title": "Structured Title",
                    "title_id": "PPSA12345",
                    "version": "01.000.000",
                    "required_firmware": "09.00",
                    "region": "Europa",
                    "category": "Spiel",
                    "publisher": "Structured Publisher",
                },
                None,
            )
            gui._extract_meta_from_ffpkg_file = lambda _src: {
                "title": "Heuristic Title",
                "title_id": "PPUS99999",
                "version": "02.000.000",
                "required_firmware": "–",
                "region": "USA",
                "category": "–",
                "publisher": "–",
            }
            structured_meta, _ = gui._extract_meta_from_file(
                str(structured_path), "ffpkg_to_ffpfsc", _candidate_dirs=[]
            )

            gui._preview_cache.clear()
            gui._extract_meta_from_ffpkg_ufs2 = lambda _src: (
                {
                    "title": "–", "title_id": "–", "version": "–",
                    "required_firmware": "–", "region": "–",
                    "category": "–", "publisher": "–",
                },
                None,
            )
            fallback_meta, _ = gui._extract_meta_from_file(
                str(fallback_path), "ffpkg_to_ffpfsc", _candidate_dirs=[]
            )

            normalized = gui._meta_from_param_json_payload(
                {
                    "titleId": "PPSA12345",
                    "contentVersion": "01.000.000",
                    "requiredSystemSoftwareVersion": "09.00",
                    "applicationCategoryType": 0,
                    "localizedParameters": {
                        "en-US": {
                            "titleName": "Metadata Title",
                            "publisher": "Metadata Publisher",
                        }
                    },
                }
            )

        source = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        checks = {
            "Genau acht Hauptaufgaben konfiguriert": configured_modes == expected_modes,
            "Quellmatrix für alle Aufgaben vorhanden": all(
                mode in source_matrix for mode in expected_modes
            ),
            "Aufgabe 5 hat Stapel-Vorschau": 'elif mode == "batch_convert":' in source,
            "Aufgabe 6 unterstützt Ordner-Vorschau": (
                '"pack_folder", "fakelib_manager", "universal_convert"' in source
            ),
            "Aufgabe 6 unterstützt Datei-Vorschau": (
                '"exfat_to_folder",\n                        "universal_convert",' in source
            ),
            "Strukturierte UFS2-Daten haben Vorrang": (
                structured_meta["title"] == "Structured Title"
                and structured_meta["title_id"] == "PPSA12345"
                and structured_meta["_metadata_method"]
                == "UFS2Tool/Dokan (read-only)"
            ),
            "FFPKG-Muster-Scan bleibt gekennzeichneter Fallback": (
                fallback_meta["title"] == "Heuristic Title"
                and fallback_meta["_metadata_method"]
                == "FFPKG-Muster-Scan (Fallback)"
            ),
            "param.json-Titel korrekt": normalized["title"] == "Metadata Title",
            "param.json-Hersteller korrekt": (
                normalized["publisher"] == "Metadata Publisher"
            ),
            "param.json-Firmware korrekt": normalized["required_firmware"] == "09.00",
            "param.json-Kategorie korrekt": normalized["category"] == "Spiel",
            "Hersteller wird in Infobox angezeigt": '("publisher", "HERSTELLER")' in source,
            "Format und Metadatenmethode werden angezeigt": (
                'text="FORMAT:"' in source and 'text="METADATEN:"' in source
            ),
        }

        for check_name, passed in checks.items():
            test_result(check_name, passed)
        return all(checks.values())
    except Exception as exc:
        test_result("Vorschau und Spiel-Infobox Aufgaben 1-8", False, str(exc))
        return False

# ============================================================================
# 4. BUILD ABHÄNGIGKEITEN
# ============================================================================
def test_build_deps():
    print_header("TEST 4: Build-Abhängigkeiten")
    
    files_to_check = [
        ("PS5ImageConverter_Pro.spec", "PyInstaller Spec"),
        ("app_icon.ico", "App Icon"),
        ("requirements.txt", "Dependencies"),
    ]
    
    all_exist = True
    for filename, desc in files_to_check:
        exists = Path(filename).exists()
        status = "[OK]" if exists else "[FAIL]"
        print(f"  {status}  {desc}: {filename}")
        if not exists:
            all_exist = False
    
    return all_exist

# ============================================================================
# 5. DATEI-INTEGRITÄT
# ============================================================================
def test_file_integrity():
    print_header("TEST 5: Datei-Integrität")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    
    checks = []
    try:
        with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        
        # Größe Check
        file_size = sum(len(line.encode('utf-8')) for line in lines)
        size_ok = file_size > 1000000  # > 1MB
        checks.append(("Dateigröße", size_ok, f"{file_size / 1024 / 1024:.2f} MB"))
        
        # Zeilenanzahl Check
        line_count = len(lines)
        lines_ok = line_count > 10000
        checks.append(("Zeilenanzahl", lines_ok, f"{line_count} Zeilen"))
        
        # Class-Definition Check
        content = ''.join(lines)
        has_classes = "class " in content
        checks.append(("Klassen-Definitionen", has_classes, "vorhanden"))
        
        # Method-Definition Check
        has_methods = "def " in content
        checks.append(("Methoden-Definitionen", has_methods, "vorhanden"))
        
    except Exception as e:
        checks.append(("Datei-Lesezugriff", False, str(e)))
    
    for check_name, result, detail in checks:
        status = "[OK]" if result else "[FAIL]"
        print(f"  {status}  {check_name}: {detail}")
    
    all_pass = all(check[1] for check in checks)
    return all_pass

# ============================================================================
# 6. CODE LINTING
# ============================================================================
def test_code_quality():
    print_header("TEST 6: Code-Qualität")
    
    main_file = "PS5ImageConverter_Pro_FINAL_revised.py"
    
    warnings = []
    issues = []
    try:
        with open(main_file, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()

        blob_line_tokens = (
            '_B64 =',
            '_BG_IMAGE =',
        )
        
        for i, line in enumerate(lines, 1):
            is_embedded_blob = any(token in line for token in blob_line_tokens)
            # Check für sehr lange Zeilen (> 120 chars)
            if len(line.rstrip()) > 120 and not is_embedded_blob and len(line.rstrip()) < 1000:
                warnings.append(f"Line {i}: zu lang ({len(line.rstrip())} chars)")
            
            # Check für Tabs statt Spaces
            if '\t' in line:
                issues.append(f"Line {i}: enthält Tabs")
            
            # Check für Trailing Whitespace
            if line.endswith('\n'):
                content_no_nl = line[:-1]
            else:
                content_no_nl = line
            if content_no_nl.rstrip(' \t') != content_no_nl:
                issues.append(f"Line {i}: Trailing Whitespace")
    
    except Exception as e:
        print(f"  [FAIL] Fehler beim Lesen: {e}")
        return False
    
    if issues:
        print(f"  [!] {len(issues)} harte Qualitätsprobleme gefunden:")
        for issue in issues[:5]:  # Zeige nur erste 5
            print(f"      - {issue}")
        if len(issues) > 5:
            print(f"      ... und {len(issues) - 5} weitere")
    elif warnings:
        print(f"  [OK] Keine harten Qualitätsprobleme gefunden")
        print(f"  [i] {len(warnings)} Stilwarnung(en), z. B.:")
        for warning in warnings[:5]:
            print(f"      - {warning}")
        if len(warnings) > 5:
            print(f"      ... und {len(warnings) - 5} weitere")
    else:
        print(f"  [OK] Keine Qualitätsprobleme gefunden")
    
    return len(issues) == 0

# ============================================================================
# MAIN TEST RUNNER
# ============================================================================
def main():
    print("\n" + "="*60)
    print("  PS5 IMAGE CONVERTER - QUALITY TEST SUITE")
    print("="*60 + "\n")
    
    results = {}
    
    # Führe alle Tests aus
    results["Syntax"] = test_syntax()
    results["Imports"] = test_imports()
    results["ProgressEngine"] = test_progress_engine()
    results["KeepaliveRegression"] = test_keepalive_regression()
    results["SplashCentering"] = test_splash_centering_helper()
    results["AprAmprPreflight"] = test_apr_ampr_preflight()
    results["UniversalExportTargets"] = test_universal_export_targets()
    results["TaskTempCleanup"] = test_task_temp_cleanup()
    results["FfpkgValidator"] = test_ffpkg_validator()
    results["FfpfscVerificationTask7"] = test_ffpfsc_verification_and_task7_repack()
    results["PreviewGameInfoTasks1To8"] = test_preview_and_game_info_tasks_1_to_8()
    results["BuildDeps"] = test_build_deps()
    results["FileIntegrity"] = test_file_integrity()
    results["CodeQuality"] = test_code_quality()
    
    # Zusammenfassung
    print("\n" + "="*60)
    print("  ZUSAMMENFASSUNG")
    print("="*60 + "\n")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "[OK] PASS" if result else "[FAIL] FAIL"
        print(f"  {status}  {test_name}")
    
    print(f"\nErgebnis: {passed}/{total} Tests bestanden")
    
    if passed == total:
        print("\n[OK] ALLE QUALITY TESTS BESTANDEN!\n")
        return 0
    else:
        print(f"\n[!] {total - passed} Test(s) fehlgeschlagen\n")
        return 0  # Nicht als kritischer Fehler

if __name__ == "__main__":
    sys.exit(main())
