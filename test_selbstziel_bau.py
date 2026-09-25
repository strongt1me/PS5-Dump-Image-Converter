# -*- coding: utf-8 -*-
"""Waechter: Ein Selbst-Ziel baut neben der Quelle und ersetzt sie erst am Schluss.

Befund der Durchsicht vom 23.09.2026 (H6-1, H6-2): Steht im Feld ZIEL der
Ordner der Quelle und traegt das Ergebnis ihren Namen - ``.ffpfsc`` mit
Asset-Pack wieder als ``.ffpfsc``, ``.ffpfs`` als ``.ffpfs``, ``.exfat`` als
``.exfat`` -, dann zeigt der Ausgabepfad auf die Quelle.

* Die drei Packwege (einstufig ueber exFAT, flach, zweistufig) raeumten ihn
  vor dem Bau mit ``_cleanup_stale_mkpfs_output`` ab.
* Der exFAT-Neubau oeffnete ihn mit ``"wb"`` und schrieb direkt hinein.

Die Quelle lag dann nur noch entpackt im Temp-Ordner, den der Weg am Ende
selbst loescht. Scheiterte der Bau oder brach der Anwender ab, war beides
weg. ``_run_engine_thread`` und die Sammelkonvertierung liessen das Ziel mit
dem Hinweis "die Wege bauen daneben" stehen - das stimmte nur fuer den
.ffpkg-Bau und den AMPR-Manager.

Geprueft wird am Verhalten: Eine Attrappe schreibt, was die Engine schreiben
wuerde, und scheitert auf Wunsch mitten im Bau.
"""
from __future__ import annotations

import ast
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("selbstziel_bau")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

QUELLE_INHALT = b"QUELLE - das Abbild des Anwenders"


class _Attrappe:
    def __getattr__(self, _name):
        return lambda *a, **k: None


def _gui(arbeit: str) -> APP.PS5ConverterGUI:
    """Eine Programminstanz ohne Fenster; die Engine ist eine Attrappe."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.is_running = True
    gui.bauform = APP.BAUFORM_EXFAT
    gui.task_total_source_bytes = 1000
    gui.task_progress = 0.0
    gui.progress_engine = _Attrappe()
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._save_runtime_checkpoint = lambda **_k: None
    gui._ensure_param_json = lambda _s: True
    gui._mkpfs_pruef_argumente = lambda: []
    gui._decide_pack_output_staging = lambda p, **_k: p
    gui._seed_preview_cache_from_source = lambda *_a: None
    gui._resolve_pack_profile = lambda *_a: {
        "profile": "Test", "size_gb": 1, "level": 9,
        "cpu": 4, "cores": 8, "block_size": 65536}
    gui._mkdtemp = lambda prefix="t", dir_path=None, **_k: tempfile.mkdtemp(
        prefix=prefix, dir=dir_path or arbeit)
    gui.gelingt = True
    gui.aufrufe = []

    def ausfuehren(argumente, **_kwargs):
        gui.aufrufe.append(list(argumente))
        # Wie die Engine: Die Ausgabe entsteht - bei einem Abbruch halb.
        Path(argumente[-1]).write_bytes(b"NEU" if gui.gelingt else b"HALB")
        return gui.gelingt

    gui._execute_mkpfs = ausfuehren
    return gui


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory(prefix="selbstziel_")
        self.ordner = self.td.name
        self.arbeit = os.path.join(self.ordner, "arbeit")
        os.makedirs(self.arbeit)
        self.dump = os.path.join(self.arbeit, "Spiel")
        os.makedirs(os.path.join(self.dump, "sce_sys"))
        Path(self.dump, "eboot.bin").write_bytes(b"\x7fELF")

    def tearDown(self) -> None:
        for wurzel, _ordner, dateien in os.walk(self.ordner):
            for name in dateien:
                try:
                    os.chmod(os.path.join(wurzel, name), stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    pass
        self.td.cleanup()

    def _quelle(self, endung: str) -> str:
        pfad = os.path.join(self.ordner, "Spiel" + endung)
        Path(pfad).write_bytes(QUELLE_INHALT)
        return pfad


class PackwegeTests(_Grundlage):
    """Die drei Packwege von _mode_pack_folder_mkpfs."""

    WEGE = (
        ("einstufig exFAT", ".ffpfsc", APP.BAUFORM_EXFAT, False),
        ("zweistufig PFS", ".ffpfsc", APP.BAUFORM_PFS, False),
        ("flach", ".ffpfs", APP.BAUFORM_EXFAT, True),
    )

    def _packen(self, gui, ziel: str, unkomprimiert: bool) -> bool:
        return gui._mode_pack_folder_mkpfs(
            self.dump, self.ordner, ziel, 10.0, 50.0, 90.0,
            lambda _p: None, lambda _s: None, uncompressed=unkomprimiert)

    def test_scheitert_der_bau_bleibt_die_quelle(self) -> None:
        for name, endung, bauform, unkomprimiert in self.WEGE:
            with self.subTest(weg=name):
                quelle = self._quelle(endung)
                gui = _gui(self.arbeit)
                gui.bauform = bauform
                gui._lauf_quelle = quelle
                gui.gelingt = False
                self.assertFalse(self._packen(gui, quelle, unkomprimiert))
                self.assertTrue(os.path.isfile(quelle),
                                "Die Quelle wurde vor dem Bau geloescht.")
                self.assertEqual(Path(quelle).read_bytes(), QUELLE_INHALT)
                # Der halbe Bau liegt daneben und wird am Laufende entfernt.
                gui._selbstziel_reste_entfernen()
                self.assertFalse(os.path.exists(quelle + ".neu"))
                self.assertEqual(Path(quelle).read_bytes(), QUELLE_INHALT)

    def test_gelingt_der_bau_ersetzt_er_die_quelle(self) -> None:
        for name, endung, bauform, unkomprimiert in self.WEGE:
            with self.subTest(weg=name):
                quelle = self._quelle(endung)
                gui = _gui(self.arbeit)
                gui.bauform = bauform
                gui._lauf_quelle = quelle
                self.assertTrue(self._packen(gui, quelle, unkomprimiert))
                self.assertEqual(Path(quelle).read_bytes(), b"NEU")
                self.assertFalse(os.path.exists(quelle + ".neu"))
                self.assertEqual(gui.aufrufe[-1][-1], quelle + ".neu",
                                 "Gebaut wurde nicht neben der Quelle.")
                self.assertEqual(gui.task_final_output_path, quelle)

    def test_ohne_selbstziel_wird_direkt_gebaut(self) -> None:
        """Gegenprobe: Ein gewoehnliches Ziel bleibt, wie es war."""
        for name, endung, bauform, unkomprimiert in self.WEGE:
            with self.subTest(weg=name):
                ziel = os.path.join(self.ordner, "Ergebnis" + endung)
                gui = _gui(self.arbeit)
                gui.bauform = bauform
                gui._lauf_quelle = self._quelle(".exfat")
                self.assertTrue(self._packen(gui, ziel, unkomprimiert))
                self.assertEqual(gui.aufrufe[-1][-1], ziel)
                self.assertEqual(Path(ziel).read_bytes(), b"NEU")
                self.assertFalse(any(".neu" in z for z in os.listdir(self.ordner)))


class ExfatNeubauTests(_Grundlage):
    """_mode_exfat_umpacken: .exfat -> .exfat mit Einbau."""

    def _umpacken(self, gelingt: bool):
        quelle = self._quelle(".exfat")
        gui = _gui(self.arbeit)
        gui._lauf_quelle = quelle
        gui._dump_ordner_basis = lambda _d: self.arbeit
        gui._integration_anwenden = lambda ordner, **_k: ordner
        gui._quellgroesse_mit_meldung = lambda _o: 1
        gebaut: list[str] = []

        def entpacken(_src, ziel, **_k):
            os.makedirs(os.path.join(ziel, "sce_sys"))
            Path(ziel, "eboot.bin").write_bytes(b"\x7fELF")
            return True

        def bauen(_ordner, ziel, **_k):
            gebaut.append(ziel)
            Path(ziel).write_bytes(b"NEU" if gelingt else b"HALB")
            return gelingt

        gui._extract_exfat_to_folder_mkpfs = entpacken
        gui._create_exfat_from_folder = bauen
        ok = gui._mode_exfat_umpacken(quelle, self.ordner)
        return gui, quelle, ok, gebaut

    def test_scheitert_der_bau_bleibt_die_quelle(self) -> None:
        gui, quelle, ok, gebaut = self._umpacken(gelingt=False)
        self.assertFalse(ok)
        self.assertEqual(gebaut, [quelle + ".neu"], "Der Bau schrieb in die Quelle.")
        self.assertEqual(Path(quelle).read_bytes(), QUELLE_INHALT)
        gui._selbstziel_reste_entfernen()
        self.assertFalse(os.path.exists(quelle + ".neu"))

    def test_gelingt_der_bau_ersetzt_er_die_quelle(self) -> None:
        _gui_, quelle, ok, _gebaut = self._umpacken(gelingt=True)
        self.assertTrue(ok)
        self.assertEqual(Path(quelle).read_bytes(), b"NEU")
        self.assertFalse(os.path.exists(quelle + ".neu"))


class UebernahmeTests(_Grundlage):
    """_bauziel_neben_quelle / _bauziel_uebernehmen / _selbstziel_reste_entfernen."""

    def test_nur_die_quelle_selbst_zaehlt(self) -> None:
        quelle = self._quelle(".ffpfsc")
        gui = _gui(self.arbeit)
        gui._lauf_quelle = quelle
        self.assertEqual(gui._bauziel_neben_quelle(quelle), quelle + ".neu")
        # Andere Schreibweise desselben Pfads (Windows kennt keine Gross-/Kleinschreibung).
        if os.name == "nt":
            self.assertEqual(gui._bauziel_neben_quelle(quelle.upper()),
                             quelle.upper() + ".neu")
        anderes = os.path.join(self.ordner, "Anderes.ffpfsc")
        self.assertEqual(gui._bauziel_neben_quelle(anderes), anderes)
        gui._lauf_quelle = ""
        self.assertEqual(gui._bauziel_neben_quelle(quelle), quelle)

    def test_schreibgeschuetzte_quelle_wird_trotzdem_ersetzt(self) -> None:
        quelle = self._quelle(".exfat")
        os.chmod(quelle, stat.S_IREAD)
        gui = _gui(self.arbeit)
        gui._lauf_quelle = quelle
        neu = gui._bauziel_neben_quelle(quelle)
        Path(neu).write_bytes(b"NEU")
        self.assertEqual(gui._bauziel_uebernehmen(neu, quelle), quelle)
        self.assertEqual(Path(quelle).read_bytes(), b"NEU")

    def test_scheitert_die_uebernahme_bleibt_beides(self) -> None:
        quelle = self._quelle(".exfat")
        gui = _gui(self.arbeit)
        gui._lauf_quelle = quelle
        neu = gui._bauziel_neben_quelle(quelle)
        Path(neu).write_bytes(b"NEU")
        with mock.patch.object(APP.os, "replace",
                               side_effect=PermissionError("gesperrt")):
            self.assertEqual(gui._bauziel_uebernehmen(neu, quelle), neu)
        self.assertEqual(Path(quelle).read_bytes(), QUELLE_INHALT)
        # Das fertige Ergebnis ist kein Rest - es bleibt liegen.
        gui._selbstziel_reste_entfernen()
        self.assertEqual(Path(neu).read_bytes(), b"NEU")
        self.assertTrue(any("nicht ersetzen" in z for z in gui.protokoll), gui.protokoll)


class VerdrahtungTests(unittest.TestCase):
    """Wer die Quelle des Laufs setzt und wer am Ende aufraeumt."""

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        cls.methoden = {k.name: k for k in ast.walk(baum)
                        if isinstance(k, ast.FunctionDef)}

    def test_der_lauf_setzt_seine_quelle(self) -> None:
        text = ast.unparse(self.methoden["_run_engine_thread"])
        i_setzen = text.find("self._lauf_quelle = src")
        self.assertGreater(i_setzen, 0, "_run_engine_thread setzt die Quelle nicht.")
        self.assertLess(i_setzen, text.find("_run_flexible_conversion"),
                        "Die Quelle steht erst nach dem Bau fest.")

    def test_der_lauf_raeumt_halbe_bauten_ab(self) -> None:
        lauf = self.methoden["_run_engine_thread"]
        schluesse = ["\n".join(ast.unparse(z) for z in t.finalbody)
                     for t in ast.walk(lauf) if isinstance(t, ast.Try) and t.finalbody]
        self.assertTrue(any("self._selbstziel_reste_entfernen()" in s for s in schluesse),
                        "Das finally von _run_engine_thread raeumt halbe Bauten nicht ab.")

    def test_die_sammelkonvertierung_setzt_je_datei_die_quelle(self) -> None:
        text = ast.unparse(self.methoden["_run_flexible_conversion"])
        i_setzen = text.find("self._lauf_quelle = candidate")
        self.assertGreater(i_setzen, 0, "Die Sammelkonvertierung setzt die Quelle nicht.")
        self.assertLess(i_setzen, text.find("_execute_conversion_by_type"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
