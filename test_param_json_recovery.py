"""Regressionstests für die param.json-Wiederherstellung (Ja/Nein-Angebot).

Wenn sce_sys/param.json in der Quelle fehlt oder ungültig ist, bietet die App
jetzt vor dem Bau von .exfat/.ffpkg/.ffpfsc an, automatisch eine minimale,
gültige param.json zu erstellen (Titel-ID wird nach Möglichkeit aus dem
Quellnamen erkannt). Bei "Nein" bricht der Bau wie zuvor ab.

test_exfat_folder_build.py deckt den .exfat-Weg bereits ausführlich ab
(inkl. byte-genauem Rundlauf); diese Datei ergänzt den .ffpfsc/.ffpfs-Weg
(_mode_pack_folder_mkpfs) sowie einen direkten Logik-Test des gemeinsamen
Helfers _offer_create_param_json/_detect_title_id_from_name.
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

ROOT = Path(__file__).resolve().parent
MKPFS_DIR = ROOT / "MkPFS-1.0.0"


class _StubRoot:
    def after(self, _delay_ms: int, callback) -> None:
        callback()


def _make_gui(*, recreate_param_json: bool) -> PS5ConverterGUI:
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui.mkpfs_dir = str(MKPFS_DIR.resolve())
    gui.is_running = True
    gui.root = _StubRoot()
    logged: list[str] = []
    gui._append_to_log = logged.append
    gui._log_lines = logged
    notifications: list[bool] = []
    gui._notify_param_json_problem = lambda missing: notifications.append(missing)
    gui._param_json_notifications = notifications
    # Frueher hing die Antwort an default_yes: False kennzeichnete die
    # zweite Frage, die nach dem Online-Nachschlag. Seit v1.8.53 gibt es nur
    # noch eine Frage, und seit v1.8.54 steht sie auf Nein, sobald ein Ja
    # einen Netzabruf ausloest - an default_yes laesst sich die Absicht also
    # nicht mehr ablesen.
    gui._ask_yesno_threadsafe = (
        lambda _title, _message, default_yes=True: recreate_param_json)
    # Kein Netzabruf aus der Testreihe.
    gui._online_nachschlag_erlaubt = lambda: False
    return gui


class TitleIdDetectionTests(unittest.TestCase):
    def test_detects_known_prefix_in_name(self) -> None:
        gui = _make_gui(recreate_param_json=True)
        self.assertEqual(gui._detect_title_id_from_name("PPSA04263-app0"), "PPSA04263")
        self.assertEqual(gui._detect_title_id_from_name("Arcade Game Zone (CUSA19015)"), "CUSA19015")

    def test_returns_empty_when_no_pattern_matches(self) -> None:
        gui = _make_gui(recreate_param_json=True)
        self.assertEqual(gui._detect_title_id_from_name("Mein Lieblingsspiel"), "")


class PackFolderMkpfsParamJsonPreflightTests(unittest.TestCase):
    def _make_pack_gui(self, *, recreate_param_json: bool, engine_calls: list[list[str]]) -> PS5ConverterGUI:
        gui = _make_gui(recreate_param_json=recreate_param_json)
        gui.task_total_source_bytes = 0

        def _fake_execute_mkpfs(args, **_kwargs):
            engine_calls.append(args)
            return False  # Bricht direkt nach dem ersten Engine-Aufruf ab (Rest ist bereits getestet).

        gui._execute_mkpfs = _fake_execute_mkpfs
        gui._save_runtime_checkpoint = lambda **_kw: None
        return gui

    def test_missing_param_json_declined_never_reaches_engine(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "src"
            src.mkdir()
            (src / "eboot.bin").write_bytes(b"\x7fELF")
            engine_calls: list[list[str]] = []
            gui = self._make_pack_gui(recreate_param_json=False, engine_calls=engine_calls)

            ok = gui._mode_pack_folder_mkpfs(
                str(src), td, str(Path(td) / "out.ffpfsc"),
                5.0, 60.0, 98.0, lambda _v: None, lambda _v: None,
            )

            self.assertFalse(ok)
            self.assertEqual(engine_calls, [], "Bei 'Nein' darf die MkPFS-Engine nie aufgerufen werden.")
            self.assertEqual(gui._param_json_notifications, [True])
            self.assertFalse((src / "sce_sys" / "param.json").exists())

    def test_missing_param_json_accepted_creates_file_and_proceeds(self) -> None:
        with TemporaryDirectory() as td:
            src = Path(td) / "PPSA19015-app0"
            src.mkdir()
            (src / "eboot.bin").write_bytes(b"\x7fELF")
            engine_calls: list[list[str]] = []
            gui = self._make_pack_gui(recreate_param_json=True, engine_calls=engine_calls)

            ok = gui._mode_pack_folder_mkpfs(
                str(src), td, str(Path(td) / "out.ffpfsc"),
                5.0, 60.0, 98.0, lambda _v: None, lambda _v: None,
            )

            self.assertFalse(ok)  # Der gestubbte Engine-Aufruf selbst liefert False.
            self.assertEqual(len(engine_calls), 1, "Bei 'Ja' muss der Bau bis zur MkPFS-Engine fortgesetzt werden.")
            self.assertEqual(gui._param_json_notifications, [])

            created = src / "sce_sys" / "param.json"
            self.assertTrue(created.is_file())
            data = json.loads(created.read_text(encoding="utf-8"))
            self.assertEqual(data.get("titleId"), "PPSA19015")


if __name__ == "__main__":
    unittest.main()


class NptitleTitleIdTests(unittest.TestCase):
    """Title-ID aus `sce_sys/nptitle.dat` statt aus dem Ordnernamen.

    Die Ersatz-param.json bezog ihre Title-ID bisher ausschliesslich aus einer
    Mustersuche im Ordnernamen. In der Sammlung des Nutzers traegt das Muster
    aber nur ein Teil der Ordner - `nptitle.dat` dagegen lag in 32 von 32
    Backups vor und stimmte in 32 von 32 Faellen mit der param.json ueberein.
    """

    def setUp(self) -> None:
        from ps5_validator.utils import param_manifest
        self.pm = param_manifest
        self._tmp = TemporaryDirectory()
        self.ordner = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _nptitle(self, inhalt: bytes) -> str:
        sce = Path(self.ordner) / "sce_sys"
        sce.mkdir(parents=True, exist_ok=True)
        pfad = sce / "nptitle.dat"
        pfad.write_bytes(inhalt)
        return str(pfad)

    def _echte_datei(self, title_id: str = "PPSA18089", suffix: str = "_00") -> bytes:
        roh = bytearray(160)
        roh[0:4] = b"NPTD"
        roh[4:8] = bytes((0x00, 0x00, 0x00, 0x80))
        kennung = (title_id + suffix).encode("ascii")
        roh[0x10:0x10 + len(kennung)] = kennung
        return bytes(roh)

    def test_liest_die_id_am_gemessenen_offset(self) -> None:
        pfad = self._nptitle(self._echte_datei())
        self.assertEqual(self.pm.read_title_id_from_nptitle(pfad), "PPSA18089")

    def test_suffix_wird_abgeschnitten(self) -> None:
        pfad = self._nptitle(self._echte_datei("PPSA04933", "_00"))
        self.assertEqual(self.pm.read_title_id_from_nptitle(pfad), "PPSA04933")

    def test_ps4_kennung_wird_auch_erkannt(self) -> None:
        pfad = self._nptitle(self._echte_datei("CUSA12345"))
        self.assertEqual(self.pm.read_title_id_from_nptitle(pfad), "CUSA12345")

    def test_falsche_magic_liefert_nichts(self) -> None:
        roh = bytearray(self._echte_datei())
        roh[0:4] = b"XXXX"
        pfad = self._nptitle(bytes(roh))
        self.assertEqual(self.pm.read_title_id_from_nptitle(pfad), "")

    def test_unsinn_an_der_stelle_liefert_nichts(self) -> None:
        roh = bytearray(self._echte_datei())
        roh[0x10:0x20] = b"nicht_lesbar\x00\x00\x00\x00"
        pfad = self._nptitle(bytes(roh))
        self.assertEqual(self.pm.read_title_id_from_nptitle(pfad), "")

    def test_zu_kurze_datei_liefert_nichts(self) -> None:
        pfad = self._nptitle(b"NPTD")
        self.assertEqual(self.pm.read_title_id_from_nptitle(pfad), "")

    def test_fehlende_datei_liefert_nichts(self) -> None:
        self.assertEqual(
            self.pm.read_title_id_from_nptitle(os.path.join(self.ordner, "gibtsnicht.dat")), "")

    def test_ordnerschale_findet_die_datei(self) -> None:
        self._nptitle(self._echte_datei("PPSA23000"))
        self.assertEqual(self.pm.read_title_id_from_dump(self.ordner), "PPSA23000")

    def test_ordner_ohne_sce_sys_liefert_nichts(self) -> None:
        with TemporaryDirectory() as leer:
            self.assertEqual(self.pm.read_title_id_from_dump(leer), "")


class TitleIdHerkunftTests(unittest.TestCase):
    """Die Datei hat Vorrang vor dem Ordnernamen."""

    def setUp(self) -> None:
        self.gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        self._tmp = TemporaryDirectory()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _dump(self, ordnername: str, nptitle_id: str | None) -> str:
        pfad = Path(self._tmp.name) / ordnername
        (pfad / "sce_sys").mkdir(parents=True, exist_ok=True)
        if nptitle_id is not None:
            roh = bytearray(160)
            roh[0:4] = b"NPTD"
            kennung = (nptitle_id + "_00").encode("ascii")
            roh[0x10:0x10 + len(kennung)] = kennung
            (pfad / "sce_sys" / "nptitle.dat").write_bytes(bytes(roh))
        return str(pfad)

    def test_datei_schlaegt_ordnernamen(self) -> None:
        """Auch wenn beide etwas liefern, gilt die Datei."""
        ordner = self._dump("PPSA99999 Falscher Name", "PPSA18089")
        self.assertEqual(
            PS5ConverterGUI._detect_title_id_for_source(self.gui, ordner),
            ("PPSA18089", "nptitle"),
        )

    def test_ohne_datei_greift_der_ordnername(self) -> None:
        ordner = self._dump("PPSA17732 The Precinct", None)
        self.assertEqual(
            PS5ConverterGUI._detect_title_id_for_source(self.gui, ordner),
            ("PPSA17732", "name"),
        )

    def test_ordnername_ohne_muster_bleibt_leer(self) -> None:
        """Genau der Fall, den nptitle.dat jetzt auffaengt."""
        ordner = self._dump("Teardown", None)
        self.assertEqual(
            PS5ConverterGUI._detect_title_id_for_source(self.gui, ordner), ("", ""))

    def test_teardown_mit_datei_wird_erkannt(self) -> None:
        ordner = self._dump("Teardown", "PPSA15246")
        self.assertEqual(
            PS5ConverterGUI._detect_title_id_for_source(self.gui, ordner),
            ("PPSA15246", "nptitle"),
        )

    def test_meldungstext_ist_zweisprachig_vorhanden(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        schluessel = "dialog.msg.param_json_offer_id_from_nptitle"
        self.assertIn(schluessel, STRINGS)
        self.assertTrue(STRINGS[schluessel].get("de"))
        self.assertTrue(STRINGS[schluessel].get("en"))
