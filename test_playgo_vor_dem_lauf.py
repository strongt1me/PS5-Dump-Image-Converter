# -*- coding: utf-8 -*-
"""PlayGo wird vor der Arbeit geklaert, nicht danach.

Anlass (Anwender, 18.09.2026): Der Hinweis "Der Titel erklaert
PlayGo-Inhalte" kam zu spaet, um noch etwas zu aendern. Bei einem
Dump-Ordner stand er vor dem Start in einer Meldung mit nur "OK" - danach
lief die Aufgabe los. Bei einem Abbild kam er erst im Protokoll, nachdem es
ausgepackt war. Wer PlayGo daraufhin wollte, musste neu bauen; bei Ghost of
Yotei, dem einzigen von 31 gemessenen Dumps mit playgo-scenario.json,
dauert ein Lauf gut elf Stunden.

Seitdem fragt ``_playgo_vor_dem_lauf_klaeren`` am Anfang des Laufs, bevor
kopiert, entpackt oder gepackt wird - bei einem Ordner sofort, bei einem
Abbild ueber dessen Verzeichnis. Die Abbild-Pruefungen laufen gegen echte,
mit MkPFS gebaute Abbilder aller vier Bauformen.
"""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
MKPFS_DIR = PROJEKT / "MkPFS-1.0.0"
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(MKPFS_DIR))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("playgo_vor_dem_lauf")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
MERKMAL = "sce_sys/playgo-scenario.json"


class _Wert:
    """Steht fuer eine Tk-Variable: get und set, sonst nichts."""

    def __init__(self, wert) -> None:
        self.wert = wert

    def get(self):
        return self.wert

    def set(self, wert) -> None:
        self.wert = wert


def _spielordner(basis: Path, *, mit_playgo: bool) -> Path:
    spiel = basis / "spiel"
    (spiel / "sce_sys").mkdir(parents=True)
    (spiel / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 60)
    (spiel / "sce_sys" / "param.json").write_text(json.dumps({
        "titleId": "PPSA26344",
        "contentId": "UP9000-PPSA26344_00-GHOSTOFYOTEI0000",
        "titleName": "Test",
        "masterVersion": "01.00",
        "applicationCategoryType": 0,
    }), encoding="utf-8")
    if mit_playgo:
        (spiel / "sce_sys" / "playgo-scenario.json").write_text(
            "{}", encoding="utf-8")
    return spiel


def _mkpfs(*argv: str) -> None:
    import mkpfs.cli as mkpfs_cli  # noqa: PLC0415
    # stderr mit abfangen: Dort schreibt die Fortschrittsanzeige der Engine.
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        rc = mkpfs_cli.main(list(argv))
    if rc != 0:
        raise RuntimeError("MkPFS-Aufbau fehlgeschlagen: %r -> %s" % (argv, rc))


_PFS_ARGE = ("--no-compress", "--no-verify-structure",
             "--no-adjust-output-file-extension", "--version", "PS5",
             "--inode-bits", "32", "--block-size", "65536")


def _abbild(basis: Path, bauform: str, *, mit_playgo: bool) -> Path:
    """Baut ein echtes Abbild in einer der vier Bauformen."""
    spiel = _spielordner(basis, mit_playgo=mit_playgo)
    if bauform == "exfat":
        ziel = basis / "spiel.exfat"
        _mkpfs("pack", "exfat", "--no-progress", str(spiel), str(ziel))
    elif bauform == "ffpfsc_um_exfat":
        # Die Bauform, die das Programm fuer .ffpfsc standardmaessig baut.
        ziel = basis / "spiel.ffpfsc"
        _mkpfs("pack", "folder", *_PFS_ARGE, "--no-ampr-index",
               str(spiel), str(ziel))
    elif bauform == "ffpfs_flach":
        ziel = basis / "spiel.ffpfs"
        _mkpfs("pack", "folder", "--raw", *_PFS_ARGE, "--no-ampr-index",
               str(spiel), str(ziel))
    elif bauform == "pfs_in_pfs":
        innen = basis / "innen.dat"
        _mkpfs("pack", "folder", "--raw", *_PFS_ARGE, "--no-ampr-index",
               str(spiel), str(innen))
        ziel = basis / "spiel.ffpfsc"
        _mkpfs("pack", "file", *_PFS_ARGE, "--cpu-count", "1",
               "--compression-level", "1", str(innen), str(ziel))
    else:
        raise ValueError(bauform)
    shutil.rmtree(spiel)
    return ziel


class _TempTest(unittest.TestCase):
    def setUp(self) -> None:
        self.basis = Path(tempfile.mkdtemp(prefix="playgo_vorab_"))
        self.addCleanup(shutil.rmtree, self.basis, True)


# ---------------------------------------------------------------------------
# Hineinsehen, ohne auszupacken
# ---------------------------------------------------------------------------
class MerkmalImAbbildTests(_TempTest):
    """Alle vier Bauformen - mit und ohne Merkmal, dazu ein Unlesbares."""

    BAUFORMEN = ("exfat", "ffpfsc_um_exfat", "ffpfs_flach", "pfs_in_pfs")

    def _gui(self) -> GUI:
        gui = GUI.__new__(GUI)
        gui.mkpfs_dir = str(MKPFS_DIR)
        return gui

    def test_merkmal_wird_in_jeder_bauform_gefunden(self) -> None:
        for bauform in self.BAUFORMEN:
            with self.subTest(bauform=bauform):
                basis = self.basis / bauform
                basis.mkdir()
                abbild = _abbild(basis, bauform, mit_playgo=True)
                self.assertEqual(
                    MERKMAL, self._gui()._playgo_merkmal_der_quelle(str(abbild)))

    def test_ohne_merkmal_heisst_nachgesehen_und_nichts_gefunden(self) -> None:
        """"" und nicht None - sonst fragte der Einbau spaeter trotzdem."""
        for bauform in self.BAUFORMEN:
            with self.subTest(bauform=bauform):
                basis = self.basis / bauform
                basis.mkdir()
                abbild = _abbild(basis, bauform, mit_playgo=False)
                self.assertEqual(
                    "", self._gui()._playgo_merkmal_der_quelle(str(abbild)))

    def test_der_verzeichnisbaum_ist_vollstaendig(self) -> None:
        """Die Liste enthaelt die Spieldateien, nicht nur das innere Abbild.

        Die umhuellende .ffpfsc liest sich auch als flaches PFS - als eine
        einzige Datei. Bliebe es dabei, hiesse jedes Abbild "kein PlayGo".
        """
        for bauform in self.BAUFORMEN:
            with self.subTest(bauform=bauform):
                basis = self.basis / bauform
                basis.mkdir()
                abbild = _abbild(basis, bauform, mit_playgo=True)
                pfade = {p.replace("\\", "/").lower()
                         for p in self._gui()._abbild_eintraege(str(abbild))}
                self.assertIn("eboot.bin", pfade)
                self.assertIn("sce_sys/param.json", pfade)

    def test_exfat_wird_nur_oben_gelesen(self) -> None:
        """Der ganze Baum dauerte kalt bis 137 s (DIRT5, 67.226 Dateien).

        Gelesen wird nur, wo sce_sys liegen kann. Tiefe Dateien fehlen in der
        Liste - fehlten sie nicht, liefe wieder der ganze Baum, etwa weil
        MkPFS die Methode umbenannt hat, in die der Leser eingreift.
        """
        spiel = _spielordner(self.basis, mit_playgo=True)
        (spiel / "daten" / "a" / "b").mkdir(parents=True)
        (spiel / "daten" / "a" / "b" / "tief.bin").write_bytes(b"x")
        (spiel / "daten" / "oben.bin").write_bytes(b"y")
        ziel = self.basis / "spiel.exfat"
        _mkpfs("pack", "exfat", "--no-progress", str(spiel), str(ziel))
        pfade = {p.replace("\\", "/").lower()
                 for p in self._gui()._abbild_eintraege(str(ziel))}
        self.assertIn(MERKMAL, pfade)
        self.assertIn("daten/oben.bin", pfade)
        self.assertNotIn("daten/a/b/tief.bin", pfade)

    def test_spiel_eine_ebene_tiefer_im_exfat(self) -> None:
        huelle = self.basis / "huelle"
        _spielordner(huelle, mit_playgo=True)
        ziel = self.basis / "tief.exfat"
        _mkpfs("pack", "exfat", "--no-progress", str(huelle), str(ziel))
        self.assertEqual(MERKMAL, self._gui()._playgo_merkmal_der_quelle(str(ziel)))

    def test_unlesbares_heisst_unbekannt(self) -> None:
        kaputt = self.basis / "kaputt.ffpkg"
        kaputt.write_bytes(os.urandom(256 * 1024))
        self.assertIsNone(self._gui()._playgo_merkmal_der_quelle(str(kaputt)))
        self.assertIsNone(self._gui()._playgo_merkmal_der_quelle(
            str(self.basis / "gibt_es_nicht.ffpfsc")))

    def test_merkmal_eine_ebene_tiefer(self) -> None:
        self.assertEqual(MERKMAL, GUI._playgo_merkmal_in(
            ["PPSA26344/eboot.bin", "PPSA26344\\sce_sys\\playgo-scenario.json"]))
        self.assertEqual("", GUI._playgo_merkmal_in(
            ["eboot.bin", "sce_sys/param.json", "playgo-scenario.json.bak"]))


# ---------------------------------------------------------------------------
# Die Rueckfrage am Anfang des Laufs
# ---------------------------------------------------------------------------
class _FrageTest(_TempTest):
    def _gui(self, *, ampr: bool = True, playgo: bool = False,
             antwort: bool = True, cli: bool = False) -> GUI:
        gui = GUI.__new__(GUI)
        gui.mkpfs_dir = str(MKPFS_DIR)
        self.protokoll: list = []
        self.fragen: list = []
        self.gespeichert: list = []
        self.texte: list = []
        gui._append_to_log = self.protokoll.append

        def _t(schluessel, **werte):
            self.texte.append((schluessel, werte))
            return schluessel

        gui._t = _t
        gui._set_status = lambda *_a, **_k: None
        gui.ampr_integrate_var = _Wert(ampr)
        gui.ampr_playgo_var = _Wert(playgo)
        gui._lauf_variablen = None
        gui._cli_mode = cli
        gui.is_running = True

        def _frage(titel, text, default_yes=True):
            self.fragen.append((titel, text, default_yes))
            return antwort

        gui._ask_yesno_threadsafe = _frage
        gui._save_setting = lambda k, v: self.gespeichert.append((k, v))
        return gui


class RueckfrageVorDemLaufTests(_FrageTest):

    def test_ja_schaltet_playgo_fuer_lauf_fenster_und_einstellung_ein(self) -> None:
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._gui(antwort=True)
        gui._playgo_vor_dem_lauf_klaeren("pack_folder", str(spiel))
        self.assertEqual(1, len(self.fragen))
        self.assertTrue(self.fragen[0][2], "Vorbelegt sein soll Ja")
        self.assertTrue(gui._lauf_variablen["ampr_playgo_var"])
        self.assertTrue(gui.ampr_playgo_var.get())
        self.assertIn(("integrate_playgo", True), self.gespeichert)
        self.assertIn("main.playgo_eingeschaltet", self.protokoll)

    def test_nein_laesst_playgo_aus_und_sagt_es(self) -> None:
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._gui(antwort=False)
        gui._playgo_vor_dem_lauf_klaeren("pack_folder", str(spiel))
        self.assertEqual(1, len(self.fragen))
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertFalse((gui._lauf_variablen or {}).get("ampr_playgo_var", False))
        self.assertEqual([], self.gespeichert)
        self.assertIn("main.playgo_bleibt_aus", self.protokoll)

    def test_abbild_wird_vor_dem_auspacken_gefragt(self) -> None:
        """Der eigentliche Anlass: bei einem Abbild kam bisher nichts vorab."""
        abbild = _abbild(self.basis, "ffpfsc_um_exfat", mit_playgo=True)
        gui = self._gui(antwort=True)
        gui._playgo_vor_dem_lauf_klaeren("unpack_to_exfat", str(abbild))
        self.assertEqual(1, len(self.fragen))
        self.assertIn(("dialog.msg.playgo_empfohlen", {"datei": MERKMAL}),
                      self.texte, "Die Frage nennt nicht, woran es erkannt wurde")
        self.assertTrue(gui._lauf_variablen["ampr_playgo_var"])

    def test_keine_frage_wo_es_nichts_zu_fragen_gibt(self) -> None:
        mit = _spielordner(self.basis / "mit", mit_playgo=True)
        ohne = _spielordner(self.basis / "ohne", mit_playgo=False)
        faelle = (
            ("PlayGo schon an", dict(playgo=True), "pack_folder", mit),
            ("AMPR aus", dict(ampr=False), "pack_folder", mit),
            ("kein Merkmal", {}, "pack_folder", ohne),
            ("Sammelkonvertierung", {}, "batch_convert", mit),
            ("keine Zielaufgabe", {}, "inspect", mit),
        )
        for name, einstellungen, mode, quelle in faelle:
            with self.subTest(fall=name):
                gui = self._gui(**einstellungen)
                gui._playgo_vor_dem_lauf_klaeren(mode, str(quelle))
                self.assertEqual([], self.fragen)
                self.assertNotIn("main.playgo_eingeschaltet", self.protokoll)

    def test_kommandozeile_fragt_nicht_und_schaltet_nicht_ein(self) -> None:
        """PlayGo kommt nie von selbst dazu - dort gilt die Einstellung."""
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._gui(cli=True)
        gui._playgo_vor_dem_lauf_klaeren("pack_folder", str(spiel))
        self.assertEqual([], self.fragen)
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertIn("main.integrate_playgo_empfohlen", self.protokoll)

    def test_vorabpruefung_meldet_playgo_nicht_mehr_nur_mit_ok(self) -> None:
        """Die alte Meldung vor dem Start liess nichts mehr aendern - weg damit,
        sonst kaeme dieselbe Sache zweimal: erst als Meldung, dann als Frage."""
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._gui()
        gui._get_runtime_temp_dir = lambda: str(self.basis)
        gui._missing_critical_dump_files = lambda *_a: []
        _fehler, warnungen = gui._run_preflight_checks("pack_folder", str(spiel), "")
        self.assertFalse([w for w in warnungen if "playgo" in w.lower()])

    def test_unlesbares_abbild_verschiebt_die_frage_auf_den_einbau(self) -> None:
        kaputt = self.basis / "spiel.ffpkg"
        kaputt.write_bytes(os.urandom(256 * 1024))
        gui = self._gui()
        gui._playgo_vor_dem_lauf_klaeren("ffpkg_to_ffpfsc", str(kaputt))
        self.assertEqual([], self.fragen)
        self.assertTrue(gui._playgo_beim_einbau_fragen)
        self.assertFalse(gui._playgo_geklaert)
        self.assertIn("main.playgo_nicht_pruefbar", self.protokoll)

    def test_aus_dem_aufgabenfaden_nur_ueber_den_hauptfaden_ins_fenster(self) -> None:
        """Der Faden setzt den Startstand; Kaestchen und Einstellung zieht
        der Hauptfaden nach - Tk-Variablen aus dem Faden sind verboten."""
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._gui(antwort=True)
        gui._lauf_variablen = {"ampr_integrate_var": True, "ampr_playgo_var": False}
        nachher: list = []
        gui.root = types.SimpleNamespace(after=lambda _ms, fn: nachher.append(fn))
        im_faden: dict = {}

        def _lauf() -> None:
            gui._playgo_vor_dem_lauf_klaeren("pack_folder", str(spiel))
            im_faden["playgo"] = gui._tk_wert("ampr_playgo_var", False)

        faden = threading.Thread(target=_lauf)
        faden.start()
        faden.join(30)
        self.assertTrue(im_faden.get("playgo"),
                        "Der laufende Auftrag sieht das Ja nicht")
        self.assertFalse(gui.ampr_playgo_var.get(),
                         "Der Faden hat die Tk-Variable selbst gesetzt")
        self.assertEqual(1, len(nachher))
        nachher[0]()
        self.assertTrue(gui.ampr_playgo_var.get())
        self.assertIn(("integrate_playgo", True), self.gespeichert)


# ---------------------------------------------------------------------------
# Beim Einbau: nur noch, wenn vorab nicht hineinzusehen war
# ---------------------------------------------------------------------------
class BeimEinbauTests(_FrageTest):

    def _einbau_gui(self, **kwargs) -> GUI:
        gui = self._gui(**kwargs)
        self.bibliotheken: list = []
        gui.ampr_version_var = _Wert("0.4.2.1 test-pack")
        gui._ampr_versionsauswahl = {"0.4.2.1 test-pack": {
            "path": "x", "variant": "test-pack", "version": "0.4.2.1"}}
        gui._ampr_apply_library = (
            lambda _o, _p, name: self.bibliotheken.append(name) or True)
        gui._ampr_playgo_zur_version = lambda _e: "playgo.sprx"
        gui._ampr_index_neubau_erlaubt = lambda *_a, **_k: True
        gui._build_ampr_index_local = lambda *_a, **_k: (1, 0)
        gui._ampr_methode = lambda: APP.AMPR_METHODE_NORMAL
        return gui

    def test_nach_dem_auspacken_gefragt_ja_bringt_den_stub(self) -> None:
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._einbau_gui(antwort=True)
        gui._playgo_beim_einbau_fragen = True
        self.assertTrue(gui._integration_ampr(str(spiel)))
        self.assertEqual(1, len(self.fragen))
        self.assertIn("libScePlayGo.sprx", self.bibliotheken)

    def test_vorab_verneint_keine_zweite_frage_kein_stub(self) -> None:
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._einbau_gui(antwort=True)
        gui._playgo_geklaert = True
        gui._playgo_beim_einbau_fragen = False
        self.assertTrue(gui._integration_ampr(str(spiel)))
        self.assertEqual([], self.fragen)
        self.assertNotIn("libScePlayGo.sprx", self.bibliotheken)
        self.assertNotIn("main.integrate_playgo_empfohlen", self.protokoll)

    def test_vorab_verneint_ganzer_weg(self) -> None:
        """Nein am Anfang gilt: beim Einbau weder Frage noch zweiter Hinweis."""
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._einbau_gui(antwort=False)
        gui._playgo_vor_dem_lauf_klaeren("pack_folder", str(spiel))
        self.assertTrue(gui._integration_ampr(str(spiel)))
        self.assertEqual(1, len(self.fragen))
        self.assertNotIn("libScePlayGo.sprx", self.bibliotheken)
        self.assertNotIn("main.integrate_playgo_empfohlen", self.protokoll)

    def test_vorab_bejaht_der_stub_kommt_mit(self) -> None:
        """Ganzer Weg: Ja am Anfang, danach der Einbau im selben Lauf."""
        spiel = _spielordner(self.basis, mit_playgo=True)
        gui = self._einbau_gui(antwort=True)
        gui._playgo_vor_dem_lauf_klaeren("pack_folder", str(spiel))
        self.assertTrue(gui._integration_ampr(str(spiel)))
        self.assertEqual(1, len(self.fragen), "Beim Einbau noch einmal gefragt")
        self.assertIn("libScePlayGo.sprx", self.bibliotheken)


# ---------------------------------------------------------------------------
# Reihenfolge im Lauf
# ---------------------------------------------------------------------------
class ReihenfolgeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        klasse = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        cls.methoden = {m.name: m for m in klasse.body
                        if isinstance(m, ast.FunctionDef)}

    @staticmethod
    def _aufrufe(knoten: ast.AST) -> list[tuple[int, str]]:
        return sorted((k.lineno, k.func.attr) for k in ast.walk(knoten)
                      if isinstance(k, ast.Call)
                      and isinstance(k.func, ast.Attribute))

    def test_gefragt_wird_vor_der_konvertierung(self) -> None:
        aufrufe = [name for _z, name in
                   self._aufrufe(self.methoden["_run_engine_thread"])]
        self.assertIn("_playgo_vor_dem_lauf_klaeren", aufrufe)
        self.assertLess(aufrufe.index("_playgo_vor_dem_lauf_klaeren"),
                        aufrufe.index("_run_flexible_conversion"))



if __name__ == "__main__":
    unittest.main(verbosity=2)
