"""Opt-in-End-to-End-Test des produktiven GUI-FFPKG-Buildpfads.

Ausführung:
    RUN_FFPKG_INTEGRATION=1 python -m unittest -v test_ffpkg_production_integration.py
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import stat
import tempfile
import unittest
from pathlib import Path

import PS5ImageConverter_Pro_FINAL_revised as ps5converter
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils.ffpkg_support import validate_source_folder
from ps5_validator.utils.param_manifest import create_default_param


class _ProgressEngineStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def start_task(self, task_index: int, task_label: str) -> None:
        self.calls.append(("start_task", (task_index, task_label)))

    def begin_prepare(self, description: str) -> None:
        self.calls.append(("prepare", description))

    def begin_payload(self, total: int, *, description: str, unit_label: str) -> None:
        self.calls.append(("payload", (total, description, unit_label)))

    def begin_validate(self, description: str) -> None:
        self.calls.append(("validate", description))

    def commit_task(self) -> None:
        self.calls.append(("commit", True))


def _runtime_test_tool(root: Path, embedded_exe: Path) -> str:
    """Liefert ein ausführbares UFS2Tool für opt-in-Integrationstests."""
    tool_dll = embedded_exe.with_name("UFS2Tool.dll")
    if not tool_dll.is_file():
        raise FileNotFoundError(tool_dll)

    if os.name == "nt":
        wrapper = root / "ufs2tool.cmd"
        wrapper.write_text(
            '@echo off\r\n"C:\\Program Files\\dotnet\\dotnet.exe" '
            + f'"{tool_dll}" %*\r\n'
            + "exit /b %ERRORLEVEL%\r\n",
            encoding="utf-8",
        )
        return str(wrapper)

    wrapper = root / "ufs2tool"
    wrapper.write_text(
        "#!/bin/sh\nexec /usr/bin/dotnet " + repr(str(tool_dll)) + ' "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return str(wrapper)


def _write_pattern(path: Path, byte_count: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    block = hashlib.sha256(path.as_posix().encode("utf-8")).digest() * 32768
    remaining = byte_count
    with path.open("wb") as handle:
        while remaining:
            chunk = block[: min(len(block), remaining)]
            handle.write(chunk)
            remaining -= len(chunk)


class FfpkgFallbackSelectionTests(unittest.TestCase):
    """Prüft die atomare Auswahl unabhängig vom echten UFS2Tool-Binary."""

    def setUp(self) -> None:
        # _build_ffpkg_from_folder verlangt seit dem Admin-Preflight erhöhte
        # Rechte. Diese Tests mocken die UFS2Tool-Ausführung ohnehin komplett,
        # also wird auch die Rechteprüfung übersprungen.
        self._original_is_admin = ps5converter._is_admin
        ps5converter._is_admin = lambda: True
        # Geprueft wird die Kandidatenlogik des Bauwerks, nicht die Frage, ob
        # UFS2Tool auf diesem System existiert. Die Betriebssystem-Weiche davor
        # muss dafuer genauso gestellt werden wie die Rechtepruefung - sonst
        # steigt der Lauf unter Linux schon vor der zu pruefenden Stelle aus.
        self._original_ist_windows = ps5converter.IST_WINDOWS
        ps5converter.IST_WINDOWS = True

    def tearDown(self) -> None:
        ps5converter._is_admin = self._original_is_admin
        ps5converter.IST_WINDOWS = self._original_ist_windows

    def test_builder_discards_invalid_primary_and_commits_valid_compatibility_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffpkg-fallback-selection-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            (source / "sce_sys").mkdir(parents=True)
            (source / "sce_sys" / "param.json").write_text(
                # Vollstaendig, sonst haelt die inhaltliche Pruefung des
                # Baus (seit v1.8.51) den Lauf mit einer Rueckfrage an.
                json.dumps(create_default_param(title_id="PPSA00001")) + "\n",
                encoding="utf-8")
            _write_pattern(source / "payload" / "game.bin", 8192)
            output = root / "result.ffpkg"

            gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
            gui.is_running = True
            gui.task_progress = 0.0
            gui.progress_engine = _ProgressEngineStub()
            gui.ffpkg_progress_queue = queue.Queue()
            gui._ffpkg_progress_run_id = 0
            gui._extract_ufs2tool = lambda: "UFS2Tool.exe"
            staging_root = root / "configured-temp"
            staging_root.mkdir()
            gui._mkdtemp = lambda prefix: tempfile.mkdtemp(prefix=prefix, dir=staging_root)
            log_lines: list[str] = []
            gui._append_to_log = log_lines.append

            commands: list[list[str]] = []
            validation_paths: list[Path] = []

            def fake_run(command: list[str], **_kwargs: object) -> int:
                commands.append(command)
                candidate_path = Path(command[-1] if command[1] == "newfs" else command[-2])
                candidate_path.write_bytes(b"candidate")
                return 0

            def fake_validate(candidate_path: str) -> dict[str, object]:
                validation_paths.append(Path(candidate_path))
                if len(validation_paths) == 1:
                    return {"ok": False, "detail": "fsck_ufs rc=8: Cylinder Group ungültig."}
                return {
                    "ok": True,
                    "detail": "UFS2-Struktur validiert.",
                    "sha256": hashlib.sha256(Path(candidate_path).read_bytes()).hexdigest(),
                }

            gui._run_subprocess_logged = fake_run
            gui._validate_ffpkg_artifact = fake_validate

            ok = gui._build_ffpkg_from_folder(
                str(source),
                str(output),
                task_index=0,
                task_label="Fallback-Auswahlprüfung",
            )

            self.assertTrue(ok, "".join(log_lines))
            self.assertEqual([command[1] for command in commands], ["newfs", "newfs"])
            self.assertIn("65536", commands[0])
            self.assertIn("32768", commands[1])
            # Zwei Validierungen für die Kandidaten im Temp-Staging und eine
            # zusätzliche Validierung der übertragenen Zielvolume-Datei.
            self.assertEqual(len(validation_paths), 3)
            self.assertEqual(output.read_bytes(), b"candidate")
            self.assertTrue(all(path.name == "candidate.ffpkg" for path in validation_paths[:2]))
            self.assertTrue(all(staging_root in path.parents for path in validation_paths[:2]))
            self.assertIn(".transfer-", validation_paths[2].name)
            self.assertEqual(validation_paths[2].parent, root)
            self.assertFalse(list(root.glob("*.part-*.ffpkg")))
            self.assertFalse(list(root.glob("*.transfer-*.ffpkg")))
            self.assertFalse(list(staging_root.glob("ps5conv_ffpkg_stage_*")))
            self.assertIn(("commit", True), gui.progress_engine.calls)
            joined_log = "".join(log_lines)
            self.assertIn("newfs-64k-reference", joined_log)
            self.assertIn("newfs-32k-4k-compatibility", joined_log)
            self.assertIn("verworfen", joined_log)
            self.assertIn("Temp-Staging", joined_log)
            self.assertIn("Zielvolume übertragen", joined_log)

    def test_builder_discards_candidate_when_target_volume_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffpkg-target-validation-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            (source / "sce_sys").mkdir(parents=True)
            (source / "sce_sys" / "param.json").write_text(
                # Vollstaendig, sonst haelt die inhaltliche Pruefung des
                # Baus (seit v1.8.51) den Lauf mit einer Rueckfrage an.
                json.dumps(create_default_param(title_id="PPSA00001")) + "\n",
                encoding="utf-8")
            output = root / "result.ffpkg"
            staging_root = root / "configured-temp"
            staging_root.mkdir()

            gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
            gui.is_running = True
            gui.task_progress = 0.0
            gui.progress_engine = _ProgressEngineStub()
            gui.ffpkg_progress_queue = queue.Queue()
            gui._ffpkg_progress_run_id = 0
            gui._extract_ufs2tool = lambda: "UFS2Tool.exe"
            gui._mkdtemp = lambda prefix: tempfile.mkdtemp(prefix=prefix, dir=staging_root)
            gui._append_to_log = lambda _line: None

            def fake_run(command: list[str], **_kwargs: object) -> int:
                candidate_path = Path(command[-1] if command[1] == "newfs" else command[-2])
                candidate_path.write_bytes(b"candidate")
                return 0

            validation_calls: list[Path] = []

            def target_rejecting_validate(candidate_path: str) -> dict[str, object]:
                candidate = Path(candidate_path)
                validation_calls.append(candidate)
                if ".transfer-" in candidate.name:
                    return {"ok": False, "detail": "fsck_ufs rc=8: Zielvolume-UFS2 ungültig."}
                return {"ok": True, "detail": "Staging gültig.", "sha256": hashlib.sha256(b"candidate").hexdigest()}

            gui._run_subprocess_logged = fake_run
            gui._validate_ffpkg_artifact = target_rejecting_validate

            ok = gui._build_ffpkg_from_folder(
                str(source), str(output), task_index=0, task_label="Zielvolume-Ablehnung"
            )

            self.assertFalse(ok)
            self.assertFalse(output.exists())
            self.assertEqual(len([path for path in validation_calls if ".transfer-" in path.name]), 3)
            self.assertFalse(list(root.glob("*.transfer-*.ffpkg")))


class FfpkgFakelibRegressionTests(unittest.TestCase):
    """Prüft den Aufgabe-7-Repackpfad für bearbeitete ``.ffpkg``-Quellen."""

    def test_ampr_manager_repacks_ffpkg_source_back_to_ffpkg(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffpkg-fakelib-regression-") as temp_dir:
            root = Path(temp_dir)
            source_image = root / "input.ffpkg"
            source_image.write_bytes(b"ffpkg source")
            destination_dir = root / "output"
            destination_dir.mkdir()
            # Eigene AMPR-Bibliothek, die der Manager in den Dump uebernimmt.
            added_file = root / "libSceAmpr.sprx"
            added_file.write_bytes(b"AMPR" * 64)

            gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
            gui.is_running = True
            gui.task_progress = 0.0
            gui.task_num_steps = 1
            gui.task_step_ends = [100.0]
            gui.task_current_step = 1
            gui.task_total_source_bytes = 0
            gui.task_final_output_path = ""
            gui.progress_engine = _ProgressEngineStub()
            log_lines: list[str] = []
            gui._append_to_log = log_lines.append
            gui._set_status = lambda _message: None
            gui._prepare_ampr_support = lambda search_root, _automation: True

            def fake_mkdtemp(prefix: str, dir_path: str | None = None) -> str:
                return tempfile.mkdtemp(prefix=prefix, dir=dir_path or root)

            gui._mkdtemp = fake_mkdtemp

            def fake_extract(_src: str, output_dir: str, **_kwargs: object) -> bool:
                output_root = Path(output_dir)
                (output_root / "sce_sys").mkdir(parents=True, exist_ok=True)
                (output_root / "sce_sys" / "param.json").write_text(
                    '{"titleId":"PPSA00001"}\n', encoding="utf-8"
                )
                return True

            gui._extract_ffpkg_to_folder_via_ufs2tool = fake_extract

            build_calls: list[dict[str, object]] = []

            def fake_build(
                source_dir: str,
                final_output: str,
                *,
                task_index: int,
                task_label: str,
                progress_start: float = 5.0,
                progress_end: float = 98.0,
            ) -> bool:
                build_calls.append(
                    {
                        "source_dir": source_dir,
                        "final_output": final_output,
                        "task_index": task_index,
                        "task_label": task_label,
                        "progress_start": progress_start,
                        "progress_end": progress_end,
                    }
                )
                return True

            gui._build_ffpkg_from_folder = fake_build

            ok = gui._mode_ampr_manager(
                str(source_image),
                str(destination_dir),
                automation={
                    "action": "ampr_apply",
                    "ampr_source": str(added_file),
                    "ampr_lib": "libSceAmpr.sprx",
                    "ampr_rebuild_index": False,
                },
            )

            self.assertTrue(ok, "".join(log_lines))
            self.assertEqual(len(build_calls), 1)
            build_call = build_calls[0]
            self.assertEqual(build_call["final_output"], str(destination_dir / source_image.name))
            self.assertEqual(build_call["task_index"], 6)
            self.assertEqual(build_call["task_label"], "Aufgabe 7 – FFPKG neu packen")
            self.assertEqual(build_call["progress_start"], 55.0)
            self.assertEqual(build_call["progress_end"], 98.0)
            self.assertNotIn("keine Schreiblogik vorhanden", "".join(log_lines))


@unittest.skipUnless(
    os.environ.get("RUN_FFPKG_INTEGRATION") == "1",
    "Setze RUN_FFPKG_INTEGRATION=1 für den realen UFS2Tool-Test.",
)
class FfpkgProductionIntegrationTests(unittest.TestCase):
    def test_productive_builder_creates_validated_atomic_ffpkg_and_live_events(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ffpkg-production-") as temp_dir:
            root = Path(temp_dir)
            gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
            gui._mkdtemp = lambda prefix: tempfile.mkdtemp(prefix=prefix)
            embedded_exe = Path(gui._extract_ufs2tool())
            tool_dll = embedded_exe.with_name("UFS2Tool.dll")
            self.assertTrue(embedded_exe.is_file(), embedded_exe)
            self.assertTrue(tool_dll.is_file(), tool_dll)
            runtime_tool = _runtime_test_tool(root, embedded_exe)

            source = root / "source"
            (source / "sce_sys").mkdir(parents=True)
            (source / "sce_sys" / "param.json").write_text(
                '{"titleId":"PPSA66666"}\n', encoding="utf-8"
            )
            _write_pattern(source / "payload" / "game.bin", 9 * 1024 * 1024 + 123)
            for index in range(80):
                file_path = source / "assets" / f"group_{index % 8}" / f"asset_{index:04d}.bin"
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(hashlib.sha256(f"asset-{index}".encode()).digest() * 5)

            output = root / "result.ffpkg"
            gui.is_running = True
            gui.task_progress = 0.0
            gui.progress_engine = _ProgressEngineStub()
            gui.ffpkg_progress_queue = queue.Queue()
            gui._ffpkg_progress_run_id = 0
            gui._extract_ufs2tool = lambda: runtime_tool
            log_lines: list[str] = []
            gui._append_to_log = log_lines.append

            ok = gui._build_ffpkg_from_folder(
                str(source),
                str(output),
                task_index=0,
                task_label="Integrationsprüfung FFPKG",
            )

            self.assertTrue(ok, "".join(log_lines))
            self.assertTrue(output.is_file())
            self.assertEqual(gui.task_progress, 100.0)
            self.assertFalse(list(root.glob("*.part-*.ffpkg")))

            _file_count, source_bytes = validate_source_folder(source)
            self.assertGreater(output.stat().st_size, source_bytes)
            self.assertIn(("commit", True), gui.progress_engine.calls)

            events: list[dict[str, object]] = []
            while not gui.ffpkg_progress_queue.empty():
                events.append(gui.ffpkg_progress_queue.get_nowait())
            self.assertEqual(events[0]["kind"], "start")
            self.assertEqual(events[-1]["kind"], "end")
            percentages = [
                float(event["percent"])
                for event in events
                if event.get("kind") == "line" and "percent" in event
            ]
            self.assertGreaterEqual(len(percentages), 100)
            self.assertEqual(percentages[0], 0.0)
            self.assertEqual(percentages[-1], 100.0)
            self.assertTrue(all(a <= b for a, b in zip(percentages, percentages[1:])))
            self.assertIn("Echtes UFS2-FFPKG erstellt, übertragen und validiert (newfs-64k-reference)", "".join(log_lines))


@unittest.skipUnless(
    os.environ.get("RUN_FFPKG_648MB_INTEGRATION") == "1",
    "Setze RUN_FFPKG_648MB_INTEGRATION=1 fuer den realen 648-MB-UFS2-Regressionsfall.",
)
class Ffpkg648MbRegressionTests(unittest.TestCase):
    """Reproduziert die Größen- und Dateianzahl des gemeldeten Korruptionsfalls."""

    def test_191_files_648mb_builds_to_a_clean_validated_ffpkg(self) -> None:
        source_bytes = 648_398_581
        file_count = 191
        directory_count = 15
        small_file_size = 65_537

        with tempfile.TemporaryDirectory(prefix="ffpkg-648mb-") as temp_dir:
            root = Path(temp_dir)
            gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
            gui._mkdtemp = lambda prefix: tempfile.mkdtemp(prefix=prefix)
            embedded_exe = Path(gui._extract_ufs2tool())
            tool_dll = embedded_exe.with_name("UFS2Tool.dll")
            self.assertTrue(tool_dll.is_file(), tool_dll)
            runtime_tool = _runtime_test_tool(root, embedded_exe)

            source = root / "source"
            for index in range(directory_count):
                (source / f"dir_{index:02d}").mkdir(parents=True)
            _write_pattern(
                source / "dir_00" / "game_data.bin",
                source_bytes - ((file_count - 1) * small_file_size),
            )
            # Eine der kleinen Dateien wird als gültige sce_sys/param.json
            # angelegt (auf exakt small_file_size aufgefüllt), damit die
            # Vorab-Prüfung in _build_ffpkg_from_folder nicht abbricht, ohne
            # die exakte Datei-/Byteanzahl des Regressionsfalls zu verändern.
            (source / "sce_sys").mkdir(parents=True)
            param_json_text = '{"titleId":"PPSA00001"}'
            (source / "sce_sys" / "param.json").write_text(
                param_json_text + " " * (small_file_size - len(param_json_text)),
                encoding="utf-8",
            )
            for index in range(1, file_count - 1):
                _write_pattern(
                    source / f"dir_{index % directory_count:02d}" / f"file_{index:03d}.bin",
                    small_file_size,
                )

            output = root / "result_648mb.ffpkg"
            gui.is_running = True
            gui.task_progress = 0.0
            gui.progress_engine = _ProgressEngineStub()
            gui.ffpkg_progress_queue = queue.Queue()
            gui._ffpkg_progress_run_id = 0
            gui._extract_ufs2tool = lambda: runtime_tool
            log_lines: list[str] = []
            gui._append_to_log = log_lines.append

            ok = gui._build_ffpkg_from_folder(
                str(source),
                str(output),
                task_index=0,
                task_label="648-MB-UFS2-Regressionspruefung",
            )

            self.assertTrue(ok, "".join(log_lines))
            self.assertTrue(output.is_file())
            actual_files, actual_source_bytes = validate_source_folder(source)
            self.assertEqual((actual_files, actual_source_bytes), (file_count, source_bytes))
            self.assertGreater(output.stat().st_size, actual_source_bytes)
            self.assertEqual(gui.task_progress, 100.0)
            self.assertIn(("commit", True), gui.progress_engine.calls)
            self.assertIn("Echtes UFS2-FFPKG erstellt, übertragen und validiert (newfs-64k-reference)", "".join(log_lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
