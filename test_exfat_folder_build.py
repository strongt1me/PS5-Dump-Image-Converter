"""Regressionstests für den Ordner->.exFAT-Bau (_create_exfat_from_folder).

Deckt zwei Dinge ab:
  1. Vorab-Prüfung: fehlende oder ungültige sce_sys/param.json in der Quelle
     bricht VOR dem Bau ab, statt ein exFAT-Image zu erzeugen, das erst auf
     der PS5 mit "Missing/invalid param.json" scheitert.
  2. Byte-genauer Rundlauf (Writer -> Reader) für ein realistisches Image mit
     vielen Dateien, großen mehrfach-Cluster-Dateien, verschachtelten Ordnern
     und einer Nulldatei, um Writer-Bugs jenseits winziger Testfälle zu fangen.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils.param_manifest import create_default_param

ROOT = Path(__file__).resolve().parent
MKPFS_DIR = ROOT / "MkPFS-1.0.0"


class _StubLabel:
    def config(self, **_kwargs: object) -> None:
        pass


class _StubRoot:
    def after(self, _delay_ms: int, callback) -> None:
        callback()


def _make_gui(*, recreate_param_json: bool = False) -> PS5ConverterGUI:
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui.mkpfs_dir = str(MKPFS_DIR.resolve())
    gui.is_running = True
    gui.root = _StubRoot()
    gui.status_label = _StubLabel()
    logged: list[str] = []
    gui._append_to_log = logged.append
    gui._fmt_bytes = lambda n: str(n)
    gui.task_progress = 0.0
    gui.task_total_source_bytes = 0
    gui._copy_total_bytes = 0
    gui._copy_done_bytes = 0
    gui._copy_total_exact = True
    gui._copy_rate_bps = 0.0
    gui._copy_rate_trend = ""
    gui._log_lines = logged
    # Fängt den echten (Tkinter-)Popup-Aufruf ab, damit Tests nicht auf ein
    # echtes Dialogfenster warten, und macht ihn gleichzeitig prüfbar.
    param_json_notifications: list[bool] = []
    gui._notify_param_json_problem = lambda missing: param_json_notifications.append(missing)
    gui._param_json_notifications = param_json_notifications
    # Simuliert die Antwort auf die Ja/Nein-Rückfrage "param.json automatisch
    # erstellen?", ohne einen echten Tkinter-Dialog zu öffnen.
    yesno_calls: list[tuple[str, str]] = []

    def _fake_ask_yesno(title: str, message: str,
                        default_yes: bool = True) -> bool:
        yesno_calls.append((title, message))
        return recreate_param_json

    # Ohne diese Zeile schlaegt der Test die Title-ID bei prosperopatches.com
    # nach - ein echter Netzabruf mitten in der Testreihe. Bis v1.8.52
    # verhinderte das die zweite Rueckfrage, die hier verneint wurde; seit
    # beide Fragen zusammengelegt sind, muss der Nachschlag ausdruecklich
    # abgeschaltet werden.
    gui._online_nachschlag_erlaubt = lambda: False

    gui._ask_yesno_threadsafe = _fake_ask_yesno
    gui._yesno_calls = yesno_calls
    return gui


class ExfatFolderPreflightTests(unittest.TestCase):
    def test_missing_param_json_aborts_before_build(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / "sce_sys").mkdir(parents=True)
            (src / "eboot.bin").write_bytes(b"\x7fELF")
            out_file = Path(td) / "out.exfat"

            gui = _make_gui()
            ok = gui._create_exfat_from_folder(str(src), str(out_file))

            self.assertFalse(ok)
            self.assertFalse(out_file.exists(), "Es darf kein Image gebaut werden, wenn param.json fehlt.")
            self.assertTrue(
                any("param.json" in line for line in gui._log_lines),
                "Die Protokollmeldung muss param.json erwähnen.",
            )
            self.assertEqual(
                gui._param_json_notifications, [True],
                "Bei fehlender param.json muss die verständliche Hinweis-Meldung ausgelöst werden.",
            )

    def test_invalid_param_json_aborts_before_build(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / "sce_sys").mkdir(parents=True)
            (src / "eboot.bin").write_bytes(b"\x7fELF")
            (src / "sce_sys" / "param.json").write_text("{ das ist kein json", encoding="utf-8")
            out_file = Path(td) / "out.exfat"

            gui = _make_gui()
            ok = gui._create_exfat_from_folder(str(src), str(out_file))

            self.assertFalse(ok)
            self.assertFalse(out_file.exists(), "Es darf kein Image gebaut werden, wenn param.json ungültig ist.")
            self.assertEqual(
                gui._param_json_notifications, [False],
                "Bei ungültiger param.json muss die verständliche Hinweis-Meldung ausgelöst werden.",
            )

    def test_missing_param_json_recreated_on_yes_and_build_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "PPSA04263-app0"
            (src / "sce_sys").mkdir(parents=True)
            (src / "eboot.bin").write_bytes(os.urandom(64))
            out_file = Path(td) / "out.exfat"

            gui = _make_gui(recreate_param_json=True)
            ok = gui._create_exfat_from_folder(str(src), str(out_file))

            self.assertTrue(ok, f"Bau sollte nach Ja-Antwort gelingen; Log: {gui._log_lines}")
            self.assertTrue(out_file.is_file())
            self.assertEqual(gui._param_json_notifications, [], "Bei Ja darf keine Fehlermeldung mehr kommen.")
            # Seit v1.8.53 genuegt eine Frage. Die zweite - "Titel online
            # nachschlagen?" - ist in sie hineingezogen worden; hier ist der
            # Nachschlag abgeschaltet, deshalb bleibt es bei der einen.
            self.assertEqual(len(gui._yesno_calls), 1)
            self.assertIn("param.json", gui._yesno_calls[0][1].lower())

            created = (src / "sce_sys" / "param.json")
            self.assertTrue(created.is_file(), "param.json muss lokal in der Quelle angelegt worden sein.")
            created_data = json.loads(created.read_text(encoding="utf-8"))
            self.assertEqual(created_data.get("titleId"), "PPSA04263", "Titel-ID muss aus dem Ordnernamen erkannt werden.")

    def test_invalid_param_json_replaced_on_yes_and_build_succeeds(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / "sce_sys").mkdir(parents=True)
            (src / "eboot.bin").write_bytes(os.urandom(64))
            (src / "sce_sys" / "param.json").write_text("{ das ist kein json", encoding="utf-8")
            out_file = Path(td) / "out.exfat"

            gui = _make_gui(recreate_param_json=True)
            ok = gui._create_exfat_from_folder(str(src), str(out_file))

            self.assertTrue(ok, f"Bau sollte nach Ja-Antwort gelingen; Log: {gui._log_lines}")
            self.assertTrue(out_file.is_file())
            created = (src / "sce_sys" / "param.json")
            created_data = json.loads(created.read_text(encoding="utf-8"))
            self.assertNotIn("titleId", created_data, "Kein Ordnername-Titel-ID-Muster -> keine titleId erfunden.")

    def test_valid_param_json_builds_and_roundtrips(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "PPSA04263-app0"
            (src / "sce_sys").mkdir(parents=True)
            (src / "assets" / "sub").mkdir(parents=True)
            (src / "sce_module").mkdir(parents=True)
            (src / "eboot.bin").write_bytes(os.urandom(1024))

            # Vollstaendig, nicht knapp: Seit v1.8.51 prueft der Bau die
            # param.json inhaltlich und bricht bei Fehlern ab. Zwei Felder
            # genuegen dafuer nicht mehr.
            param = create_default_param(title_id="PPSA04263",
                                         title="Test Game")
            param_bytes = json.dumps(param).encode("utf-8")
            (src / "sce_sys" / "param.json").write_bytes(param_bytes)

            big_data = os.urandom(2 * 1024 * 1024 + 123)
            (src / "assets" / "big.pak").write_bytes(big_data)
            (src / "assets" / "empty.txt").write_bytes(b"")
            for i in range(50):
                (src / "sce_module" / f"file_{i:03d}.bin").write_bytes(os.urandom(50))

            out_file = Path(td) / "out.exfat"
            gui = _make_gui()
            ok = gui._create_exfat_from_folder(str(src), str(out_file))

            self.assertTrue(ok, f"Bau sollte gelingen; Log: {gui._log_lines}")
            self.assertTrue(out_file.is_file())

            import sys

            if str(MKPFS_DIR) not in sys.path:
                sys.path.insert(0, str(MKPFS_DIR))
            from mkpfs.exfat import ExfatReader

            with out_file.open("rb") as fh:
                reader = ExfatReader(fh)
                entries = list(reader.iter_files())
                by_path = {str(getattr(e, "rel_path", "")).replace("\\", "/"): e for e in entries}

                self.assertIn("sce_sys/param.json", by_path)
                pj_bytes = b"".join(reader.read_file(by_path["sce_sys/param.json"]))
                self.assertEqual(pj_bytes, param_bytes)

                self.assertIn("assets/big.pak", by_path)
                big_bytes = b"".join(reader.read_file(by_path["assets/big.pak"]))
                self.assertEqual(big_bytes, big_data)

                self.assertEqual(len(entries), 54)  # eboot + param.json + big.pak + empty.txt + 50 small files


if __name__ == "__main__":
    unittest.main()
