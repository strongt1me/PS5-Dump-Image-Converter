# -*- coding: utf-8 -*-
"""AMPR EMU: Rueckfrage vor dem Lauf, wenn das Spiel ``libSceAmpr`` laedt und keinen Ersatz mitbringt (16.11.2026).

Dasselbe Muster wie bei DLC EMU und PlayGo (``test_dlc_erkennung.py``): Wer die Kaestchen beim Erstellen nicht kennt,
soll genau dann gefragt werden, wenn AMPR EMU gebraucht wird. Der Bedarf kommt aus Dump Forges ``inspect`` und gilt fuer
einen Spielordner und jedes der vier Abbilder (auch ein ``.ffpkg``, das die eigene Dateiliste nicht lesen kann).

Die JSON-Beispiele unten sind an echten Abbildern gemessen (16.11.2026, ``ps5-dump-forge inspect --json``):

* Arcade Game Zone ohne Einbau: ``imports_ampr`` wahr, ``runtime`` "none", ``emulators`` leer;
* dasselbe Spiel mit AMPR EMU: ``runtime`` "other", ``emulators`` mit ``fakelib/libSceAmpr.sprx`` (Name "AMPR");
* Prince of Persia (zstd-Packs): ``runtime`` "zstd", ``emulators`` mit AMPR;
* Jobee's Lair (kein Import): ``lz4`` gleich ``null``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI as GUI   # noqa: E402
from ps5_validator.utils import ampr_assetpakete             # noqa: E402
from ps5_validator.utils import forge_cli as fc              # noqa: E402

_AMPR_EMU = {"path": "fakelib/libSceAmpr.sprx", "name": "AMPR"}


def _lz4(runtime: str = "none", imports: bool = True) -> dict:
    return {"imports_ampr": imports, "packed": None, "manifest_error": None, "runtime": runtime,
            "shipped_runtime_version": "0.4.2.1", "runtime_version": None, "runtime_action": "install",
            "pack_runtime_action": "install", "index": "missing"}


class BrauchtAmprTests(unittest.TestCase):
    """``forge_cli.braucht_ampr``: rein, am Aufbau von Forges Antwort."""

    def test_importiert_und_ohne_ersatz_braucht_es(self) -> None:
        self.assertIs(True, fc.braucht_ampr({"lz4": _lz4(), "emulators": []}))

    def test_ein_mitgebrachter_emulator_genuegt(self) -> None:
        self.assertIs(False, fc.braucht_ampr({"lz4": _lz4("other"), "emulators": [_AMPR_EMU]}))

    def test_ein_emulator_allein_genuegt_auch_ohne_laufzeitangabe(self) -> None:
        """Gegenprobe zur Laufzeit: die Liste der Emulatoren zaehlt fuer sich."""
        self.assertIs(False, fc.braucht_ampr({"lz4": _lz4("none"), "emulators": [_AMPR_EMU]}))
        self.assertIs(False, fc.braucht_ampr({"lz4": _lz4("none"), "emulators": [{"path": "FakeLib/LIBSCEAMPR.SPRX"}]}))

    def test_eine_laufzeit_allein_genuegt_auch_ohne_emulatorliste(self) -> None:
        self.assertIs(False, fc.braucht_ampr({"lz4": _lz4("zstd"), "emulators": []}))
        self.assertIs(False, fc.braucht_ampr({"lz4": _lz4("ng")}))

    def test_andere_emulatoren_ersetzen_ampr_nicht(self) -> None:
        andere = [{"path": "fakelib/libScePlayGo.sprx", "name": "PlayGo"}, {"path": "fakelib/x.sprx", "name": "Other"}]
        self.assertIs(True, fc.braucht_ampr({"lz4": _lz4(), "emulators": andere}))

    def test_ohne_import_braucht_es_keins(self) -> None:
        self.assertIs(False, fc.braucht_ampr({"lz4": None, "emulators": []}))
        self.assertIs(False, fc.braucht_ampr({"lz4": _lz4(imports=False), "emulators": []}))

    def test_ohne_den_schluessel_wird_nicht_geraten(self) -> None:
        self.assertIsNone(fc.braucht_ampr({"title_id": "PPSA00001"}))
        self.assertIsNone(fc.braucht_ampr({}))
        self.assertIsNone(fc.braucht_ampr(None))  # type: ignore[arg-type]

    def test_unbrauchbare_eintraege_stoeren_nicht(self) -> None:
        self.assertIs(True, fc.braucht_ampr({"lz4": _lz4(), "emulators": ["x", None, 3]}))
        self.assertIs(True, fc.braucht_ampr({"lz4": _lz4(), "emulators": None}))


_ATTRAPPE = (
    "import os, sys\n"
    "if os.environ.get('FAKE_MODUS') == 'fehler':\n"
    "    sys.stderr.write('ps5-dump-forge: kaputt\\n'); sys.exit(1)\n"
    "if sys.argv[1:2] != ['inspect'] or '--json' not in sys.argv:\n"
    "    sys.stderr.write('falscher Aufruf\\n'); sys.exit(2)\n"
    "print(os.environ['FAKE_INSPECT'])\n"
)


class AmprBedarfMitAttrappeTests(unittest.TestCase):
    """``forge_cli.ampr_bedarf``: ruft ``inspect <Quelle> --json`` auf und wertet die Antwort aus."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.skript = Path(tmp.name) / "attrappe.py"
        self.skript.write_text(_ATTRAPPE, encoding="utf-8")

    def _bedarf(self, inspect: dict, modus: str = "ok"):
        with mock.patch.dict(os.environ, {"FAKE_MODUS": modus, "FAKE_INSPECT": json.dumps(inspect)}):
            return fc.ampr_bedarf(sys.executable, "irgendwo.ffpkg", vorspann=(str(self.skript),))

    def test_fehlt_ampr_ist_die_antwort_ja(self) -> None:
        self.assertIs(True, self._bedarf({"lz4": _lz4(), "emulators": []}))

    def test_liegt_ampr_im_spiel_ist_die_antwort_nein(self) -> None:
        self.assertIs(False, self._bedarf({"lz4": _lz4("other"), "emulators": [_AMPR_EMU]}))

    def test_liest_forge_die_quelle_nicht_ist_die_antwort_unbekannt_und_kein_fehler(self) -> None:
        self.assertIsNone(self._bedarf({}, modus="fehler"))

    def test_ein_abbruch_ist_unbekannt(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_INSPECT": "{}"}):
            self.assertIsNone(fc.ampr_bedarf(sys.executable, "x", vorspann=(str(self.skript),), abbruch=lambda: True))

    def test_eine_fehlende_befehlszeile_ist_unbekannt(self) -> None:
        self.assertIsNone(fc.ampr_bedarf(os.path.join(tempfile.gettempdir(), "gibt-es-bestimmt-nicht.exe"), "x"))


_EXE = fc.werkzeug_suchen([str(PROJEKT)])


@unittest.skipUnless(_EXE, "fuer diese Plattform liegt keine Dump-Forge-Befehlszeile bei")
class EchteBefehlszeileTests(unittest.TestCase):
    """Das mitgelieferte ``ps5-dump-forge`` selbst, an einem kleinen Testspiel mit Zufallsbytes als ``eboot.bin``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._temp.cleanup)
        spiel = Path(cls._temp.name) / "Spiel"
        (spiel / "sce_sys").mkdir(parents=True)
        param = {"contentId": "EP9999-PPSA99999_00-TESTSPIEL0000001", "titleId": "PPSA99999",
                 "contentVersion": "01.000.000", "masterVersion": "01.00", "applicationCategoryType": 0,
                 "applicationDrmType": "standard", "conceptId": "100000",
                 "requiredSystemSoftwareVersion": "0x0200000000000000", "sdkVersion": "0x0200000000000000",
                 "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Testspiel"}}}
        (spiel / "sce_sys" / "param.json").write_text(json.dumps(param), encoding="utf-8")
        (spiel / "eboot.bin").write_bytes(os.urandom(4096))
        (spiel / "daten.bin").write_bytes(b"abc" * 4000)
        cls.spiel = str(spiel)

    def test_ein_spiel_ohne_import_braucht_kein_ampr_und_ist_lesbar(self) -> None:
        self.assertIs(False, fc.ampr_bedarf(_EXE, self.spiel), "False (nachgesehen), nicht None (nicht lesbar)")

    def test_ein_abbild_davon_ebenso(self) -> None:
        bild = os.path.join(self._temp.name, "Testspiel.ffpkg")
        rc = subprocess.run([_EXE, "convert", self.spiel, "--to", "ffpkg", "-o", bild], capture_output=True).returncode
        self.assertEqual(0, rc)
        self.assertIs(False, fc.ampr_bedarf(_EXE, bild))

    def test_eine_fehlende_quelle_ist_unbekannt(self) -> None:
        self.assertIsNone(fc.ampr_bedarf(_EXE, os.path.join(self._temp.name, "gibt_es_nicht.exfat")))


class QuellFaktenTests(unittest.TestCase):
    """``forge_cli.quellfakten``: AMPR, Packs, Emulatoren, DLC und PlayGo aus einer ``inspect``-Antwort."""

    def test_ein_ungepacktes_spiel_ohne_ampr_ersatz(self) -> None:
        f = fc.quellfakten({"lz4": _lz4(), "emulators": []})
        self.assertEqual((True, True, "", "none", ()), (f.ampr_importiert, f.ampr_fehlt, f.gepackt, f.laufzeit, f.emulatoren))

    def test_zstd_packs_stehen_im_obersten_schluessel(self) -> None:
        """Gemessen an Prince of Persia: ``zstd_packed`` wahr, ``lz4.packed`` leer, Laufzeit ``zstd``."""
        f = fc.quellfakten({"lz4": dict(_lz4("zstd"), packed=None), "zstd_packed": True, "emulators": [_AMPR_EMU]})
        self.assertEqual(("zstd", "zstd", False), (f.gepackt, f.laufzeit, f.ampr_fehlt))

    def test_lz4_packs_stehen_in_lz4_packed(self) -> None:
        f = fc.quellfakten({"lz4": dict(_lz4("forge_release"), packed={"files": 10}), "zstd_packed": False})
        self.assertEqual(("lz4", False), (f.gepackt, f.ampr_fehlt))

    def test_ohne_packs_ist_gepackt_leer(self) -> None:
        for daten in ({"lz4": None}, {"lz4": _lz4(), "zstd_packed": False}, {}):
            with self.subTest(daten=daten):
                self.assertEqual("", fc.quellfakten(daten).gepackt)

    def test_emulatoren_werden_klein_und_ohne_doppelte_gefuehrt(self) -> None:
        emu = [{"name": "AMPR", "path": "a"}, {"name": "PlayGo", "path": "b"}, {"name": "playgo", "path": "c"}, {"name": "Other"}]
        self.assertEqual(("ampr", "other", "playgo"), fc.quellfakten({"emulators": emu}).emulatoren)

    def test_dlc_fehlt_nur_ohne_meldung_an_der_konsole(self) -> None:
        dlc = {"content_id": "EP1003-PPSA09017_00-FALLOUT4DLC00003", "folder": "addcont0"}
        ohne = fc.quellfakten({"dlcs": [dlc], "emulators": []})
        self.assertEqual((True, False, True, "addcont0"), (ohne.dlc_vorhanden, ohne.dlc_emuliert, ohne.dlc_fehlt, ohne.dlc_merkmal))
        self.assertFalse(fc.quellfakten({"dlcs": [dlc], "emulators": [{"name": "DLC", "path": "x"}]}).dlc_fehlt, "der Emulator")
        self.assertFalse(fc.quellfakten({"dlcs": [dict(dlc, emulated="NO_EXTRA_DATA")]}).dlc_fehlt, "der Eintrag der dlc_emu.ini")
        self.assertFalse(fc.quellfakten({"dlcs": []}).dlc_fehlt, "kein DLC im Spiel")
        self.assertEqual("EP1003-PPSA09017_00-FALLOUT4DLC00003", fc.quellfakten({"dlcs": [{"content_id": dlc["content_id"]}]}).dlc_merkmal)

    def test_playgo_fehlt_nur_mit_merkmal_und_ohne_stub(self) -> None:
        dateien = [{"path": "eboot.bin"}, {"path": "sce_sys/playgo-scenario.json"}]
        ohne = fc.quellfakten({"files": dateien, "emulators": []})
        self.assertEqual(("sce_sys/playgo-scenario.json", True), (ohne.playgo_merkmal, ohne.playgo_fehlt))
        mit = fc.quellfakten({"files": dateien, "emulators": [{"name": "PlayGo", "path": "fakelib/libScePlayGo.sprx"}]})
        self.assertEqual(("sce_sys/playgo-scenario.json", False), (mit.playgo_merkmal, mit.playgo_fehlt))
        kein = fc.quellfakten({"files": [{"path": "eboot.bin"}], "emulators": []})
        self.assertEqual(("", False), (kein.playgo_merkmal, kein.playgo_fehlt))

    def test_das_playgo_merkmal_gilt_auch_eine_ebene_tiefer_und_in_jeder_schreibweise(self) -> None:
        self.assertEqual("sce_sys/playgo-chunk.dat", fc.quellfakten({"files": [{"path": "PPSA26344/SCE_SYS/PlayGo-Chunk.dat"}]}).playgo_merkmal)

    def test_die_merkmale_sind_dieselben_wie_im_hauptprogramm(self) -> None:
        """Zwei Listen, eine Wahrheit: Aendert sich die eine, muss die andere folgen."""
        self.assertEqual(tuple(GUI._PLAYGO_MERKMALE), tuple(fc.PLAYGO_MERKMALE))

    def test_unbrauchbare_antworten_ergeben_leere_fakten(self) -> None:
        for daten in (None, [], "x", {"files": "x", "emulators": "x", "dlcs": "x", "lz4": "x"}):
            with self.subTest(daten=daten):
                f = fc.quellfakten(daten)  # type: ignore[arg-type]
                self.assertEqual(("", (), False, ""), (f.gepackt, f.emulatoren, f.dlc_vorhanden, f.playgo_merkmal))

    def test_quellfakten_lesen_gibt_bei_einem_fehler_none(self) -> None:
        self.assertIsNone(fc.quellfakten_lesen(os.path.join(tempfile.gettempdir(), "gibt-es-bestimmt-nicht.exe"), "x"))

    def test_die_paketinfo_traegt_die_fakten_aus_lesen(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skript = Path(tmp) / "attrappe.py"
            skript.write_text(_ATTRAPPE, encoding="utf-8")
            bild = Path(tmp) / "Spiel.exfat"
            bild.write_bytes(b"x" * 64)
            daten = {"kind": "exfat", "title_id": "PPSA00001", "lz4": _lz4(), "emulators": [], "files": []}
            with mock.patch.dict(os.environ, {"FAKE_INSPECT": json.dumps(daten)}):
                info = fc.lesen(sys.executable, str(bild), tmp, vorspann=(str(skript),))
            self.addCleanup(lambda: info.arbeit and shutil.rmtree(info.arbeit, ignore_errors=True))
            self.assertTrue(info.fakten.ampr_fehlt)


class _Stand:
    """Ein Hauptfenster ohne Oberflaeche, mit nur dem, was die Rueckfrage anfasst."""

    @staticmethod
    def fakten(*, fehlt=True, gepackt="") -> "fc.QuellFakten":
        return fc.QuellFakten(ampr_importiert=True, ampr_fehlt=fehlt, gepackt=gepackt)

    @staticmethod
    def gui(*, bedarf=True, ampr_an=False, cli=False, versionen=True, gepackt="", ng="", wahl="normal", fassung="0.3.5"):
        g = GUI.__new__(GUI)
        stand = {"ampr_integrate_var": ampr_an, "ampr_version_var": fassung}
        g._tk_wert = lambda name, vorgabe=None: stand.get(name, vorgabe)
        g._set_status = lambda *_a, **_k: None
        g._log = []
        g._append_to_log = g._log.append
        g._t = lambda schluessel, **w: schluessel
        g._cli_mode = cli
        g.is_running = True
        g._ampr_auswahl_beim_start = lambda: {"0.4.2.1 NG": {"path": "x", "variant": "ng"}} if versionen else {}
        fakten = None if bedarf is None else _Stand.fakten(fehlt=bedarf, gepackt=gepackt)
        g._quellfakten_der_quelle = mock.Mock(return_value=fakten)
        g._ampr_ng_angebot = lambda: ng
        g._ampr_wahl_fragen = mock.Mock(return_value=wahl)
        g._ampr_einschalten = mock.Mock()
        g._ask_yesno_threadsafe = mock.Mock(return_value=True)
        return g


class FrageTests(unittest.TestCase):
    def test_ja_schaltet_ein(self) -> None:
        g = _Stand.gui()
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_called_once()
        self.assertTrue(g._ask_yesno_threadsafe.call_args.kwargs.get("default_yes"), "vorbelegt ist Ja")
        g._ampr_einschalten.assert_called_once_with()
        self.assertEqual(["main.ampr_eingeschaltet"], g._log)

    def test_nein_bleibt_aus(self) -> None:
        g = _Stand.gui()
        g._ask_yesno_threadsafe.return_value = False
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_not_called()
        self.assertEqual(["main.ampr_bleibt_aus"], g._log)

    def test_ja_bei_einem_zstd_gepackten_spiel_prueft_gleich_auf_ng(self) -> None:
        """Wie im Zweig "schon angehakt": zstd-Packs liest nur NG - lieber jetzt fragen als erst im Einbau (nach Minuten) abbrechen."""
        g = _Stand.gui(gepackt="zstd")
        g._ampr_gepackt_pruefen = mock.Mock()
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_called_once_with()
        g._ampr_gepackt_pruefen.assert_called_once_with(g._quellfakten_der_quelle.return_value)

    def test_nein_bei_einem_zstd_gepackten_spiel_prueft_nichts(self) -> None:
        g = _Stand.gui(gepackt="zstd")
        g._ask_yesno_threadsafe.return_value = False
        g._ampr_gepackt_pruefen = mock.Mock()
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_not_called()
        g._ampr_gepackt_pruefen.assert_not_called()

    def test_braucht_es_kein_ampr_keine_frage_und_keine_zeile(self) -> None:
        g = _Stand.gui(bedarf=False)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._ampr_wahl_fragen.assert_not_called()
        self.assertEqual([], g._log)

    def test_die_sammelkonvertierung_fragt_nie(self) -> None:
        g = _Stand.gui()
        g._ampr_vor_dem_lauf_klaeren("batch_convert", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._quellfakten_der_quelle.assert_not_called()

    def test_ein_modus_ohne_einbau_fragt_nie(self) -> None:
        g = _Stand.gui()
        g._ampr_vor_dem_lauf_klaeren("inspect", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._quellfakten_der_quelle.assert_not_called()

    def test_nicht_nachzusehen_gibt_einen_hinweis_ohne_frage(self) -> None:
        g = _Stand.gui(bedarf=None)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x.zip")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(["main.ampr_nicht_pruefbar"], g._log)

    def test_eine_antwort_ohne_bedarfsangabe_gilt_als_nicht_nachzusehen(self) -> None:
        g = _Stand.gui()
        g._quellfakten_der_quelle = mock.Mock(return_value=fc.QuellFakten(ampr_fehlt=None))
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(["main.ampr_nicht_pruefbar"], g._log)

    def test_die_kommandozeile_fragt_nie_und_schreibt_den_hinweis(self) -> None:
        g = _Stand.gui(cli=True, ng="0.4.2.1 NG")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._ampr_wahl_fragen.assert_not_called()
        g._ampr_einschalten.assert_not_called()
        self.assertEqual(["main.integrate_ampr_empfohlen"], g._log)

    def test_die_kommandozeile_braucht_keinen_versionsspeicher_fuer_den_hinweis(self) -> None:
        g = _Stand.gui(cli=True, versionen=False)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        self.assertEqual(["main.integrate_ampr_empfohlen"], g._log)

    def test_ohne_versionsspeicher_gibt_es_nichts_einzubauen_also_keine_frage(self) -> None:
        g = _Stand.gui(versionen=False)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._quellfakten_der_quelle.assert_not_called()
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)

    def test_wird_der_lauf_waehrend_der_pruefung_beendet_kommt_keine_frage(self) -> None:
        g = _Stand.gui()

        def beenden(_src):
            g.is_running = False
            return _Stand.fakten()

        g._quellfakten_der_quelle = mock.Mock(side_effect=beenden)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._ampr_wahl_fragen.assert_not_called()

    def test_jede_reihe_von_rueckfragen_beginnt_mit_leeren_zwischenspeicher(self) -> None:
        g = _Stand.gui(bedarf=False)
        g._quellfakten_zwischen = {"alt": object()}
        g._ampr_vor_dem_lauf_klaeren("batch_convert", "C:/x")
        self.assertEqual({}, g._quellfakten_zwischen)


class NgWahlTests(unittest.TestCase):
    """Gibt es eine NG-Fassung samt Packwerkzeug, waehlt die Rueckfrage zwischen normal, zstd- und LZ4-Packs."""

    def test_die_wahl_normal_schaltet_wie_bisher_ein(self) -> None:
        g = _Stand.gui(ng="0.4.2.1 NG", wahl="normal")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        g._ampr_einschalten.assert_called_once_with()
        self.assertEqual(["main.ampr_eingeschaltet"], g._log)

    def test_die_wahl_zstd_schaltet_ng_mit_zstd_packs_ein(self) -> None:
        g = _Stand.gui(ng="0.4.2.1 NG", wahl="zstd")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_called_once_with(ng_label="0.4.2.1 NG", verfahren="zstd")
        self.assertEqual(["main.ampr_eingeschaltet_pack"], g._log)

    def test_die_wahl_lz4_schaltet_ng_mit_lz4_packs_ein(self) -> None:
        g = _Stand.gui(ng="0.4.2.1 NG", wahl="lz4")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_called_once_with(ng_label="0.4.2.1 NG", verfahren="lz4")

    def test_die_wahl_ohne_laesst_es_aus(self) -> None:
        g = _Stand.gui(ng="0.4.2.1 NG", wahl="")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_not_called()
        self.assertEqual(["main.ampr_bleibt_aus"], g._log)

    def test_ohne_ng_oder_packwerkzeug_bleibt_es_bei_ja_und_nein(self) -> None:
        g = _Stand.gui(ng="")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_wahl_fragen.assert_not_called()
        g._ask_yesno_threadsafe.assert_called_once()

    def test_ein_gepacktes_spiel_behaelt_seine_packs_und_bekommt_nur_die_einfache_frage(self) -> None:
        """Keine Wahl der Methode (``_ampr_wahl_fragen``): Die Packs bleiben, wie sie sind - nur die Frage nach AMPR EMU selbst."""
        for gepackt in ("lz4", "zstd"):
            with self.subTest(gepackt=gepackt):
                g = _Stand.gui(ng="0.4.2.1 NG", gepackt=gepackt)
                g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
                g._ampr_wahl_fragen.assert_not_called()
                self.assertEqual("dialog.title.ampr_empfohlen", g._ask_yesno_threadsafe.call_args_list[0].args[0])
                self.assertEqual(((), {}), (g._ampr_einschalten.call_args_list[0].args, g._ampr_einschalten.call_args_list[0].kwargs))

    def test_bei_lz4_packs_bleibt_es_bei_der_einen_frage(self) -> None:
        g = _Stand.gui(ng="0.4.2.1 NG", gepackt="lz4")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_called_once()
        g._ampr_einschalten.assert_called_once_with()

    def test_bei_zstd_packs_kommt_nach_dem_ja_die_pruefung_auf_ng(self) -> None:
        """zstd-Packs liest nur NG: Steht eine andere Fassung gewaehlt, fragt das Programm sofort, ob es auf NG umstellen soll
        (``_ampr_gepackt_pruefen``) - statt erst im Einbau abzubrechen (Pruefung 18.11.2026)."""
        g = _Stand.gui(ng="0.4.2.1 NG", gepackt="zstd")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        self.assertEqual(["dialog.title.ampr_empfohlen", "dialog.title.ampr_ng_noetig"],
                         [c.args[0] for c in g._ask_yesno_threadsafe.call_args_list])
        self.assertEqual([(), ("0.4.2.1 NG",)], [(tuple(c.args) or tuple(c.kwargs.values())) for c in g._ampr_einschalten.call_args_list])
        self.assertEqual(["main.ampr_eingeschaltet", "main.ampr_ng_umgestellt"], g._log)

    def test_die_ng_fassung_ist_die_neueste_der_variante_ng_und_nie_die_debugfassung(self) -> None:
        g = GUI.__new__(GUI)
        g._ampr_auswahl_beim_start = lambda: {
            "0.4.2.1 debug": {"variant": "ng-debug"}, "0.4.2.1 NG": {"variant": "ng"},
            "0.4.2": {"variant": "ng"}, "0.3.5": {"variant": "test-nopack"}}
        self.assertEqual("0.4.2.1 NG", g._ampr_ng_label())
        g._ampr_auswahl_beim_start = lambda: {"0.3.5": {"variant": "test-nopack"}, "x": None}
        self.assertEqual("", g._ampr_ng_label())

    def test_das_angebot_braucht_das_packwerkzeug(self) -> None:
        g = GUI.__new__(GUI)
        g._ampr_ng_label = lambda: "0.4.2.1 NG"
        with mock.patch.object(ampr_assetpakete, "einsatzbereit", return_value=(True, "")):
            self.assertEqual("0.4.2.1 NG", g._ampr_ng_angebot())
        with mock.patch.object(ampr_assetpakete, "einsatzbereit", return_value=(False, "ampr_pack.werkzeug_fehlt")):
            self.assertEqual("", g._ampr_ng_angebot())
        g._ampr_ng_label = lambda: ""
        with mock.patch.object(ampr_assetpakete, "einsatzbereit", side_effect=AssertionError("unnoetig")) as pruefung:
            self.assertEqual("", g._ampr_ng_angebot())
            pruefung.assert_not_called()

    def test_die_wahl_kommt_aus_dem_auswahldialog_und_ein_schliessen_heisst_ohne(self) -> None:
        g = GUI.__new__(GUI)
        g._t = lambda schluessel, **w: schluessel
        gesehen = {}

        def dialog(funktion, titel, frage, eintraege):
            gesehen["eintraege"] = list(eintraege)
            return gesehen["antwort"]

        g._im_hauptfaden = dialog
        for antwort, erwartet in (("ampr_wahl.normal", "normal"), ("ampr_wahl.zstd", "zstd"), ("ampr_wahl.lz4", "lz4"),
                                  ("ampr_wahl.nein", ""), ("", ""), (None, "")):
            with self.subTest(antwort=antwort):
                gesehen["antwort"] = antwort
                self.assertEqual(erwartet, g._ampr_wahl_fragen())
        self.assertEqual(["ampr_wahl.normal", "ampr_wahl.zstd", "ampr_wahl.lz4", "ampr_wahl.nein"], gesehen["eintraege"],
                         "die erste Wahl - normal - ist vorbelegt, ohne AMPR EMU steht zuletzt")


class GepacktPruefenTests(unittest.TestCase):
    """AMPR EMU angehakt und das Spiel mit zstd-Packs gepackt: Die Fassung muss NG sein (Frage vor dem Entpacken)."""

    @staticmethod
    def _gui(*, gepackt="zstd", ist_ng=False, ng="0.4.2.1 NG", fassung="0.3.5", ja=True, auswahl_da=True):
        g = _Stand.gui(ampr_an=True, gepackt=gepackt, fassung=fassung)
        g._ampr_auswahl_beim_start = lambda: {fassung: {"path": "x"}} if auswahl_da else {"andere": {"path": "y"}}
        g._ampr_bibliothek_ist_ng = lambda auswahl: ist_ng
        g._ampr_ng_label = lambda: ng
        g._ask_yesno_threadsafe = mock.Mock(return_value=ja)
        return g

    def test_zstd_und_keine_ng_fassung_fragt_und_stellt_auf_ng_um(self) -> None:
        g = self._gui()
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_called_once()
        g._ampr_einschalten.assert_called_once_with(ng_label="0.4.2.1 NG")
        self.assertEqual(["main.ampr_ng_umgestellt"], g._log)

    def test_nein_bleibt_bei_der_gewaehlten_fassung(self) -> None:
        g = self._gui(ja=False)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ampr_einschalten.assert_not_called()
        self.assertEqual(["main.ampr_ng_bleibt"], g._log)

    def test_ist_die_fassung_schon_ng_bleibt_es_still(self) -> None:
        g = self._gui(ist_ng=True)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)

    def test_lz4_packs_lesen_alle_laufzeiten_keine_frage(self) -> None:
        g = self._gui(gepackt="lz4")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)

    def test_ein_ungepacktes_spiel_braucht_keine_ng_fassung(self) -> None:
        g = self._gui(gepackt="")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)

    def test_gibt_es_keine_ng_fassung_steht_nur_der_hinweis(self) -> None:
        g = self._gui(ng="")
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(["main.ampr_ng_fehlt"], g._log)

    def test_eine_fassung_ausserhalb_der_liste_gilt_als_keine_ng_fassung(self) -> None:
        g = self._gui(auswahl_da=False)
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_called_once()

    def test_die_kommandozeile_fragt_nie(self) -> None:
        g = self._gui()
        g._cli_mode = True
        g._ampr_vor_dem_lauf_klaeren("pack_folder", "C:/x")
        g._ask_yesno_threadsafe.assert_not_called()


class QuelleTests(unittest.TestCase):
    """``_quellfakten_der_quelle``: was nachgesehen wird, und dass es nur einmal je Lauf geschieht."""

    @staticmethod
    def _gui(exe: str = "forge-exe"):
        g = GUI.__new__(GUI)
        g.is_running = True
        g._forge_befehlszeile = lambda: exe
        return g

    def test_ein_spielordner_und_jedes_abbild_gehen_an_forge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            quellen = [tmp]
            for endung in (".ffpkg", ".ffpfsc", ".ffpfs", ".exfat", ".EXFAT"):
                pfad = os.path.join(tmp, "Spiel" + endung)
                Path(pfad).write_bytes(b"x")
                quellen.append(pfad)
            for quelle in quellen:
                with self.subTest(quelle=os.path.basename(quelle)), \
                        mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten(ampr_fehlt=True)) as lesen:
                    self.assertTrue(self._gui()._quellfakten_der_quelle(quelle).ampr_fehlt)
                    self.assertEqual(("forge-exe", quelle), lesen.call_args.args)

    def test_ein_archiv_oder_eine_fehlende_quelle_wird_nicht_an_forge_gegeben(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            archiv = os.path.join(tmp, "Spiel.zip")
            Path(archiv).write_bytes(b"x")
            for quelle in (archiv, os.path.join(tmp, "fehlt.ffpkg"), os.path.join(tmp, "Ordner_fehlt")):
                with self.subTest(quelle=os.path.basename(quelle)), \
                        mock.patch.object(fc, "quellfakten_lesen", side_effect=AssertionError("nicht aufrufen")) as lesen:
                    self.assertIsNone(self._gui()._quellfakten_der_quelle(quelle))
                    lesen.assert_not_called()

    def test_ohne_befehlszeile_ist_es_unbekannt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fc, "quellfakten_lesen", side_effect=AssertionError("nicht aufrufen")) as lesen:
            self.assertIsNone(self._gui(exe="")._quellfakten_der_quelle(tmp))
            lesen.assert_not_called()

    def test_je_lauf_und_quelle_liest_forge_nur_einmal(self) -> None:
        g = self._gui()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten()) as lesen:
            erste = g._quellfakten_der_quelle(tmp)
            self.assertIs(erste, g._quellfakten_der_quelle(tmp))
            self.assertEqual(1, lesen.call_count, "AMPR, PlayGo und DLC teilen sich die Antwort")
            g._quellfakten_zwischen = {}                          # die naechste Reihe von Rueckfragen
            g._quellfakten_der_quelle(tmp)
            self.assertEqual(2, lesen.call_count)

    def test_ein_abbruch_waehrend_des_lesens_wird_nicht_gemerkt(self) -> None:
        """ABBRECHEN mitten im ``inspect``: Das ``None`` des Abbruchs darf der naechste Lauf nicht als Antwort vorfinden."""
        g = self._gui()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fc, "quellfakten_lesen") as lesen:
            def abgebrochen(*_a, **_k):
                g.is_running = False
                return None

            lesen.side_effect = abgebrochen
            self.assertIsNone(g._quellfakten_der_quelle(tmp))
            g.is_running = True
            lesen.side_effect = None
            lesen.return_value = fc.QuellFakten(gepackt="lz4")
            self.assertEqual("lz4", g._quellfakten_der_quelle(tmp).gepackt, "ein gemerktes None haette hier gestanden")
            self.assertEqual(2, lesen.call_count)

    def _mit_arbeitsfaden(self, g, arbeit) -> None:
        """Fuehrt ``arbeit`` in einem Faden aus, der als ``_task_thread`` des Auftrags gilt (lebt, solange er rechnet)."""
        faden = threading.Thread(target=arbeit)
        g._task_thread = faden
        faden.start()
        faden.join(15)
        self.assertFalse(faden.is_alive())

    def test_der_arbeitsfaden_bleibt_nach_abbrechen_im_laufpfad(self) -> None:
        """Zwischen zwei Rueckfragen kann ABBRECHEN kommen: Der Arbeitsfaden liest dann nicht ungebremst weiter, sondern bricht ab."""
        g = self._gui()
        g.is_running = False                                       # ABBRECHEN ist schon gedrueckt
        ergebnis: dict = {}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fc, "quellfakten_lesen", return_value=None) as lesen:
            self._mit_arbeitsfaden(g, lambda: ergebnis.update(r=g._quellfakten_der_quelle(tmp)))
            abbruch = lesen.call_args.kwargs["abbruch"]
        self.assertIsNotNone(abbruch, "der Arbeitsfaden bekommt den Abbruch-Rueckruf auch nach ABBRECHEN")
        self.assertTrue(abbruch())

    def test_ein_fremder_faden_liest_im_ruhezustand_auch_waehrend_ein_auftrag_laeuft(self) -> None:
        """Seitenleiste und Seite 7 fragen auch mitten in einem Auftrag: Dessen Ende darf ihr Lesen nicht abbrechen, ihre Antwort
        gehoert nicht in den Zwischenspeicher der Rueckfragen."""
        g = self._gui()
        g.is_running = True
        gehalten = threading.Event()
        arbeitsfaden = threading.Thread(target=gehalten.wait, args=(30,))
        arbeitsfaden.start()
        try:
            g._task_thread = arbeitsfaden                                  # ein Auftrag laeuft, die Frage kommt von woanders
            with tempfile.TemporaryDirectory() as tmp, \
                    mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten(gepackt="lz4")) as lesen:
                self.assertEqual("lz4", g._quellfakten_der_quelle(tmp).gepackt)
            self.assertIsNone(lesen.call_args.kwargs["abbruch"], "das Ende des fremden Auftrags darf dieses Lesen nicht abbrechen")
            self.assertEqual({}, getattr(g, "_quellfakten_zwischen", {}), "nichts aus einem fremden Faden in den Zwischenspeicher")
        finally:
            gehalten.set()
            arbeitsfaden.join(15)

    def test_viele_dateien_gleichzeitig_verdraengen_ohne_fehler(self) -> None:
        """Verschiedene Dateien haben verschiedene Schloesser, teilen aber das Merk-Woerterbuch (Pruefung 18.11.2026: ``pop`` zweier
        Faeden warf KeyError, der Aufrufer zeigte \"unbekannt\")."""
        g = self._gui()
        g.is_running = False
        fehler: list = []

        def arbeit(teil):
            try:
                for _runde in range(6):
                    for datei in teil:
                        g._quellfakten_der_quelle(datei)
            except BaseException as exc:  # noqa: BLE001 - jeder Fehler im Faden ist der Befund
                fehler.append(exc)

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fc, "quellfakten_lesen", side_effect=lambda *_a, **_k: fc.QuellFakten()):
            dateien = []
            for i in range(64):
                datei = os.path.join(tmp, "s%02d.pkg" % i)
                Path(datei).write_bytes(b"x")
                dateien.append(datei)
            faeden = [threading.Thread(target=arbeit, args=(dateien[k::8],)) for k in range(8)]
            alt = sys.getswitchinterval()
            sys.setswitchinterval(1e-6)                                    # viele Wechsel zwischen den Faeden erzwingen
            try:
                for faden in faeden:
                    faden.start()
                for faden in faeden:
                    faden.join(60)
            finally:
                sys.setswitchinterval(alt)
        self.assertEqual([], fehler)
        self.assertLessEqual(len(g._quellfakten_ruhe), 16)

    def test_der_abbruch_des_laufs_wird_an_forge_weitergereicht(self) -> None:
        g = self._gui()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fc, "quellfakten_lesen", return_value=None) as lesen:
            g._quellfakten_der_quelle(tmp)
            abbruch = lesen.call_args.kwargs["abbruch"]
            self.assertFalse(abbruch())
            g.is_running = False
            self.assertTrue(abbruch())

    def test_im_ruhezustand_wird_forge_gefragt_und_nicht_abgebrochen(self) -> None:
        """Ohne laufenden Auftrag (Seitenleiste, [Pruefung]-Zeilen, Seite 7) ist ``is_running`` falsch - das ist kein Abbruch.

        Gemessen 18.11.2026 am echten Programm: Der Rueckruf "nicht laufend = abgebrochen" liess ``wz.laufen`` vor dem Start zurueckkehren,
        ein Spielordner und ein .pkg ergaben im Ruhezustand immer "unbekannt" (die Kacheln fehlten, das Protokoll sagte "nicht pruefbar").
        Die Attrappe haelt den Vertrag von ``ps5_pkg_werkzeug.laufen`` ein: Ein Abbruch vor dem Start ergibt ``(-1, "")``.
        """
        g = self._gui()
        g.is_running = False

        def laufen(werkzeug, argumente, *, zeile=None, abbruch=None, **kw):
            if abbruch and abbruch():
                return -1, ""
            return 0, '{"title_id": "PPSA01234", "emulators": [{"name": "AMPR"}], "backport": [], "backport_firmware": "2.00"}'

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fc.wz, "laufen", side_effect=laufen) as lauf:
            fakten = g._quellfakten_der_quelle(tmp)
        self.assertIsNotNone(fakten, "im Ruhezustand muss Dump Forge gefragt werden")
        self.assertEqual(("ampr",), fakten.emulatoren)
        self.assertFalse(fakten.backport_vorhanden, "nur AMPR EMU in fakelib/ ist kein Backport")
        lauf.assert_called_once()
        self.assertIsNone(lauf.call_args.kwargs["abbruch"], "ohne Lauf gibt es nichts abzubrechen")

    def test_im_ruhezustand_gilt_nichts_aus_einem_frueheren_lauf_und_nichts_wird_gemerkt(self) -> None:
        """Was ein Lauf zwischengespeichert hat, kann sich im Spiel inzwischen geaendert haben (etwa durch den Einbau selbst)."""
        g = self._gui()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten(gepackt="lz4")) as lesen:
            self.assertEqual("lz4", g._quellfakten_der_quelle(tmp).gepackt)          # im Lauf: gemerkt
            g.is_running = False
            lesen.return_value = fc.QuellFakten(gepackt="")
            self.assertEqual("", g._quellfakten_der_quelle(tmp).gepackt, "kein Rest aus dem Lauf")
            g._quellfakten_der_quelle(tmp)
            self.assertEqual(3, lesen.call_count, "im Ruhezustand wird nichts gemerkt")

    def _paketdatei(self, tmp: str) -> str:
        datei = os.path.join(tmp, "Spiel.pkg")
        Path(datei).write_bytes(b"pkg")
        return datei

    def test_im_ruhezustand_wird_eine_datei_nur_einmal_gelesen_ein_ordner_immer_frisch(self) -> None:
        """Bericht der Seite, Seitenleiste und PlayGo-Merkmal fragen dieselbe Quelle: eine Datei aendert sich nicht still."""
        g = self._gui()
        g.is_running = False
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten(gepackt="lz4")) as lesen:
            datei = self._paketdatei(tmp)
            self.assertEqual("lz4", g._quellfakten_der_quelle(datei).gepackt)
            self.assertEqual("lz4", g._quellfakten_der_quelle(datei).gepackt)
            self.assertEqual(1, lesen.call_count, "die Datei wird einmal gelesen")
            g._quellfakten_der_quelle(tmp)
            g._quellfakten_der_quelle(tmp)
            self.assertEqual(3, lesen.call_count, "ein Ordner wird jedes Mal frisch gelesen")

    def test_eine_geaenderte_datei_und_eine_unlesbare_antwort_werden_neu_gelesen(self) -> None:
        g = self._gui()
        g.is_running = False
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(fc, "quellfakten_lesen", return_value=fc.QuellFakten(gepackt="lz4")) as lesen:
            datei = self._paketdatei(tmp)
            g._quellfakten_der_quelle(datei)
            os.utime(datei, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))      # Aenderungszeit ein anderes Mal
            g._quellfakten_der_quelle(datei)
            self.assertEqual(2, lesen.call_count, "eine geaenderte Datei hat einen neuen Schluessel")
            lesen.return_value = None
            os.utime(datei, ns=(2_000_000_000_000_000_000, 2_000_000_000_000_000_000))
            self.assertIsNone(g._quellfakten_der_quelle(datei))
            self.assertIsNone(g._quellfakten_der_quelle(datei))
            self.assertEqual(4, lesen.call_count, "\"Forge konnte nicht lesen\" wird nie gemerkt")

    def test_gleichzeitige_fragen_im_ruhezustand_lesen_die_datei_nur_einmal(self) -> None:
        """Bis zu drei ``inspect`` derselben Datei liefen gleichzeitig (Pruefung 18.11.2026): Ein Schloss je Quelle."""
        g = self._gui()
        g.is_running = False
        tor = threading.Event()

        def langsam(*_a, **_k):
            tor.wait(10)
            return fc.QuellFakten(gepackt="zstd")

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam) as lesen:
            datei = self._paketdatei(tmp)
            ergebnisse: list = []
            faeden = [threading.Thread(target=lambda: ergebnisse.append(g._quellfakten_der_quelle(datei))) for _ in range(3)]
            for faden in faeden:
                faden.start()
            threading.Event().wait(0.4)                 # alle drei sind unterwegs, der erste liest noch
            tor.set()
            for faden in faeden:
                faden.join(15)
            self.assertEqual(1, lesen.call_count)
            self.assertEqual(["zstd", "zstd", "zstd"], [e.gepackt for e in ergebnisse])

    def test_die_befehlszeile_wird_im_projekt_gefunden(self) -> None:
        if not fc.unterordner():
            self.skipTest("fuer diese Plattform liegt keine Dump-Forge-Befehlszeile bei")
        exe = GUI._forge_befehlszeile()
        self.assertTrue(os.path.isfile(exe), exe)
        self.assertEqual(fc.dateiname(), os.path.basename(exe))


class FfpkgMitForgeTests(unittest.TestCase):
    """Ein ``.ffpkg`` liest die eigene Sicht nicht (UFS2); PlayGo und DLC EMU fragen trotzdem vor dem Lauf - mit Forges Antwort."""

    @staticmethod
    def _gui(fakten):
        g = GUI.__new__(GUI)
        g._abbild_eintraege = lambda pfad: None
        g._quellfakten_der_quelle = mock.Mock(return_value=fakten)
        return g

    def _ffpkg(self) -> str:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        pfad = os.path.join(tmp.name, "Spiel.ffpkg")
        Path(pfad).write_bytes(b"x")
        return pfad

    def test_playgo_kommt_aus_forges_dateiliste(self) -> None:
        g = self._gui(fc.QuellFakten(playgo_merkmal="sce_sys/playgo-scenario.json"))
        self.assertEqual("sce_sys/playgo-scenario.json", g._playgo_merkmal_der_quelle(self._ffpkg()))

    def test_ohne_playgo_merkmal_ist_nachgesehen_und_leer_nicht_unbekannt(self) -> None:
        self.assertEqual("", self._gui(fc.QuellFakten())._playgo_merkmal_der_quelle(self._ffpkg()))

    def test_liest_forge_nicht_bleibt_es_unbekannt_wie_bisher(self) -> None:
        self.assertIsNone(self._gui(None)._playgo_merkmal_der_quelle(self._ffpkg()))
        self.assertIsNone(self._gui(None)._dlc_merkmal_der_quelle(self._ffpkg()))

    def test_dlc_kommt_aus_forges_liste_der_zusatzinhalte(self) -> None:
        g = self._gui(fc.QuellFakten(dlc_vorhanden=True, dlc_emuliert=False, dlc_merkmal="addcont0"))
        self.assertEqual("addcont0", g._dlc_merkmal_der_quelle(self._ffpkg()))

    def test_meldet_dlc_emu_die_zusatzinhalte_schon_fragt_es_nicht(self) -> None:
        g = self._gui(fc.QuellFakten(dlc_vorhanden=True, dlc_emuliert=True, dlc_merkmal="addcont0"))
        self.assertEqual("", g._dlc_merkmal_der_quelle(self._ffpkg()))

    def test_ohne_dlc_ist_es_leer(self) -> None:
        self.assertEqual("", self._gui(fc.QuellFakten())._dlc_merkmal_der_quelle(self._ffpkg()))

    def test_was_die_eigene_sicht_lesen_kann_fragt_forge_gar_nicht(self) -> None:
        g = self._gui(fc.QuellFakten(playgo_merkmal="x", dlc_vorhanden=True, dlc_merkmal="y"))
        g._abbild_eintraege = lambda pfad: ["eboot.bin"]
        pfad = self._ffpkg()
        self.assertEqual("", g._playgo_merkmal_der_quelle(pfad))
        self.assertEqual("", g._dlc_merkmal_der_quelle(pfad))
        g._quellfakten_der_quelle.assert_not_called()


class EinschaltenTests(unittest.TestCase):
    """``_ampr_einschalten``: Haken, Auftragsstand, Methode und Packverfahren."""

    @staticmethod
    def _gui():
        g = GUI.__new__(GUI)
        g.ampr_integrate_var = mock.Mock()
        g.ampr_methode_var = mock.Mock()
        g.ampr_version_var = mock.Mock()
        g._ampr_versionsauswahl = {"0.4.2.1 NG": {"variant": "ng"}}
        g._ampr_versionsliste_fuellen = mock.Mock()
        g._on_integration_changed = mock.Mock()
        g._save_setting = mock.Mock()
        g._t = lambda schluessel, **w: schluessel
        g.root = mock.Mock()
        return g

    def test_im_hauptfaden_wird_sofort_angehakt_und_die_listen_nachgezogen(self) -> None:
        g = self._gui()
        g._ampr_einschalten()
        self.assertEqual({"ampr_integrate_var": True}, g._lauf_variablen)
        g.ampr_integrate_var.set.assert_called_once_with(True)
        g._on_integration_changed.assert_called_once_with()
        g._ampr_versionsliste_fuellen.assert_not_called()
        g.ampr_methode_var.set.assert_not_called()

    def test_mit_packs_gilt_die_methode_asset_pack_und_das_verfahren_fuer_diesen_lauf(self) -> None:
        g = self._gui()
        g._ampr_einschalten(ng_label="0.4.2.1 NG", verfahren="zstd")
        self.assertEqual({"ampr_integrate_var": True, "ampr_version_var": "0.4.2.1 NG", "_ampr_methode": "assetpack",
                          "ampr_methode_var": "ampr_pack.methode_neu", "_ampr_pack_verfahren": "zstd"}, g._lauf_variablen)

    def test_mit_packs_wird_auch_das_fenster_und_die_einstellung_nachgezogen(self) -> None:
        g = self._gui()
        g._ampr_einschalten(ng_label="0.4.2.1 NG", verfahren="lz4")
        g._save_setting.assert_any_call("ampr_pack_verfahren", "lz4")
        g._save_setting.assert_any_call("integrate_ampr_methode", "assetpack")
        g._save_setting.assert_any_call("integrate_ampr_version", "0.4.2.1 NG")
        g.ampr_methode_var.set.assert_called_once_with("ampr_pack.methode_neu")
        g._ampr_versionsliste_fuellen.assert_called_once_with()
        g.ampr_version_var.set.assert_called_once_with("0.4.2.1 NG")
        g._on_integration_changed.assert_called_once_with()

    def test_nur_die_ng_fassung_aendert_weder_methode_noch_verfahren(self) -> None:
        g = self._gui()
        g._lauf_variablen = {"_ampr_methode": "normal"}
        g._ampr_einschalten(ng_label="0.4.2.1 NG")
        self.assertEqual({"_ampr_methode": "normal", "ampr_integrate_var": True, "ampr_version_var": "0.4.2.1 NG"},
                         g._lauf_variablen)
        g._ampr_versionsliste_fuellen.assert_not_called()
        g.ampr_methode_var.set.assert_not_called()
        g._save_setting.assert_called_once_with("integrate_ampr_version", "0.4.2.1 NG")

    def test_eine_fassung_ausserhalb_der_liste_wird_im_fenster_nicht_gesetzt(self) -> None:
        g = self._gui()
        g._ampr_versionsauswahl = {}
        g._ampr_einschalten(ng_label="0.4.2.1 NG")
        g.ampr_version_var.set.assert_not_called()

    def test_ein_unbekanntes_verfahren_aendert_die_methode_nicht(self) -> None:
        g = self._gui()
        g._ampr_einschalten(verfahren="brotli")
        self.assertEqual({"ampr_integrate_var": True}, g._lauf_variablen)
        g.ampr_methode_var.set.assert_not_called()

    def test_im_arbeitsfaden_wird_der_haken_dem_hauptfaden_uebergeben(self) -> None:
        g = self._gui()
        g._lauf_variablen = {"dlc_integrate_var": True}
        faden = threading.Thread(target=g._ampr_einschalten)
        faden.start()
        faden.join(10)
        self.assertIs(True, g._lauf_variablen["ampr_integrate_var"], "der Auftrag sieht es sofort")
        self.assertIs(True, g._lauf_variablen["dlc_integrate_var"], "der uebrige Stand bleibt")
        g.ampr_integrate_var.set.assert_not_called()                  # Tk nur im Hauptfaden
        verzoegert, = g.root.after.call_args.args[1:]
        verzoegert()
        g.ampr_integrate_var.set.assert_called_once_with(True)
        g._on_integration_changed.assert_called_once_with()


class PackVerfahrenTests(unittest.TestCase):
    """``_ampr_pack_verfahren``: das Verfahren der Rueckfrage gilt nur im Arbeitsfaden dieses Laufs."""

    @staticmethod
    def _gui(gespeichert: str = "lz4"):
        g = GUI.__new__(GUI)
        g._load_setting = lambda schluessel, vorgabe: gespeichert
        return g

    def _im_faden(self, g):
        ergebnis = []
        faden = threading.Thread(target=lambda: ergebnis.append(g._ampr_pack_verfahren()))
        faden.start()
        faden.join(10)
        return ergebnis[0]

    def test_ohne_wahl_gilt_die_gespeicherte_einstellung(self) -> None:
        for gespeichert in ("lz4", "zstd"):
            with self.subTest(gespeichert=gespeichert):
                g = self._gui(gespeichert)
                g._lauf_variablen = {}
                self.assertEqual(gespeichert, self._im_faden(g))
                self.assertEqual(gespeichert, g._ampr_pack_verfahren())

    def test_die_wahl_der_rueckfrage_gilt_im_arbeitsfaden(self) -> None:
        for gewaehlt in ("lz4", "zstd"):
            with self.subTest(gewaehlt=gewaehlt):
                g = self._gui("lz4" if gewaehlt == "zstd" else "zstd")
                g._lauf_variablen = {"_ampr_pack_verfahren": gewaehlt}
                self.assertEqual(gewaehlt, self._im_faden(g))

    def test_im_hauptfaden_zaehlt_nur_die_einstellung(self) -> None:
        g = self._gui("lz4")
        g._lauf_variablen = {"_ampr_pack_verfahren": "zstd"}
        self.assertEqual("lz4", g._ampr_pack_verfahren())

    def test_die_kommandozeile_hat_vorrang(self) -> None:
        g = self._gui("lz4")
        g._cli_ampr_pack_verfahren = "zstd"
        g._lauf_variablen = {"_ampr_pack_verfahren": "lz4"}
        self.assertEqual("zstd", self._im_faden(g))

    def test_ein_unbrauchbarer_wert_ergibt_lz4_nie_still_zstd(self) -> None:
        g = self._gui("lz4")
        g._lauf_variablen = {"_ampr_pack_verfahren": "brotli"}
        self.assertEqual("lz4", self._im_faden(g))


class BatchEmulatorenTests(unittest.TestCase):
    """Sammelkonvertierung: einmal gesammelt fragen, je Spiel anwenden (``_batch_emulatoren_klaeren``)."""

    @staticmethod
    def _gui(fakten: dict, *, basis=None, cli=False, root=True, versionen=True, ja=True):
        g = GUI.__new__(GUI)
        stand = dict(basis or {})
        g._konsole_fw_bekannt = lambda: ""              # "nicht angegeben": die Frage nach BACKPORT bleibt hier aussen vor
        g._konsole_firmware_erfragen = mock.Mock(return_value="")
        g._backport_firmwares = lambda: (4, 5, 6, 7)
        g._tk_wert = lambda name, vorgabe=None: stand.get(name, vorgabe)
        g._set_status = lambda *_a, **_k: None
        g._log = []
        g._append_to_log = g._log.append
        g._t = lambda schluessel, **w: schluessel + ("|" + ",".join("%s=%s" % kv for kv in sorted(w.items())) if w else "")
        g._cli_mode = cli
        g.root = object() if root else None
        g.is_running = True
        g._ampr_auswahl_beim_start = lambda: {"0.4.2.1 NG": {"variant": "ng"}} if versionen else {}
        g._quellfakten_der_quelle = mock.Mock(side_effect=lambda q: fakten.get(q))
        g._ask_yesno_threadsafe = mock.Mock(return_value=ja)
        return g

    @staticmethod
    def _f(ampr=False, dlc=False, playgo=False) -> "fc.QuellFakten":
        return fc.QuellFakten(ampr_importiert=ampr, ampr_fehlt=ampr, dlc_vorhanden=dlc, dlc_emuliert=False,
                              playgo_merkmal="sce_sys/playgo-scenario.json" if playgo else "")

    def test_ein_spiel_das_ampr_braucht_wird_einmal_gefragt_und_mit_ja_eingeschaltet(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True)})
        g._batch_emulatoren_klaeren(["C:/A"])
        g._ask_yesno_threadsafe.assert_called_once()
        self.assertEqual({"C:/A": {"ampr_integrate_var": True}}, g._batch_je_spiel)
        self.assertIn("batch.emu_eingeschaltet|anzahl=1,emulator=AMPR EMU", g._log)

    def test_mehrere_spiele_eine_gesammelte_frage_und_jedes_bekommt_nur_seine_emulatoren(self) -> None:
        fakten = {"C:/A": self._f(ampr=True, dlc=True), "C:/B": self._f(), "C:/C": self._f(playgo=True)}
        g = self._gui(fakten)
        g._batch_emulatoren_klaeren(["C:/A", "C:/B", "C:/C"])
        g._ask_yesno_threadsafe.assert_called_once()
        liste = g._ask_yesno_threadsafe.call_args.args[1]
        for zeile in ("batch.emu_zeile_ampr|anzahl=1,namen=A", "batch.emu_zeile_dlc|anzahl=1,namen=A",
                      "batch.emu_zeile_playgo|anzahl=1,namen=C"):
            self.assertIn(zeile, liste)
        self.assertEqual({"C:/A": {"ampr_integrate_var": True, "dlc_integrate_var": True},
                          "C:/C": {"ampr_playgo_var": True}}, g._batch_je_spiel)
        self.assertNotIn("C:/B", g._batch_je_spiel, "ein Spiel ohne Bedarf bekommt nichts")

    def test_mit_nein_bleibt_alles_aus_und_das_protokoll_sagt_es(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True)}, ja=False)
        g._batch_emulatoren_klaeren(["C:/A"])
        self.assertEqual({}, g._batch_je_spiel)
        self.assertEqual(["batch.emu_bleibt_aus"], g._log)

    def test_ohne_bedarf_keine_frage_und_keine_zeile(self) -> None:
        g = self._gui({"C:/A": self._f(), "C:/B": None})
        g._batch_emulatoren_klaeren(["C:/A", "C:/B"])
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log)
        self.assertEqual({}, g._batch_je_spiel)

    def test_was_schon_angehakt_ist_wird_nicht_gefragt(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True, dlc=True)}, basis={"ampr_integrate_var": True})
        g._batch_emulatoren_klaeren(["C:/A"])
        liste = g._ask_yesno_threadsafe.call_args.args[1]
        self.assertNotIn("batch.emu_zeile_ampr", liste)
        self.assertIn("batch.emu_zeile_dlc", liste)
        self.assertEqual({"C:/A": {"dlc_integrate_var": True}}, g._batch_je_spiel)

    def test_ohne_versionsspeicher_wird_nach_ampr_nicht_gefragt(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True, dlc=True)}, versionen=False)
        g._batch_emulatoren_klaeren(["C:/A"])
        self.assertNotIn("batch.emu_zeile_ampr", g._ask_yesno_threadsafe.call_args.args[1])
        self.assertEqual({"C:/A": {"dlc_integrate_var": True}}, g._batch_je_spiel)

    def test_auf_der_kommandozeile_wird_nie_gefragt_und_je_spiel_geschrieben(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True), "C:/B": self._f(dlc=True)}, cli=True, versionen=False)
        g._batch_emulatoren_klaeren(["C:/A", "C:/B"])
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual({}, g._batch_je_spiel, "nichts schaltet sich ohne Antwort ein")
        text = "\n".join(g._log)
        self.assertIn("[A] AMPR EMU", text)
        self.assertIn("[B] DLC EMU", text)

    def test_ohne_fenster_und_ohne_kommandozeile_kann_niemand_antworten(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True)}, root=False)
        g._batch_emulatoren_klaeren(["C:/A"])
        g._quellfakten_der_quelle.assert_not_called()
        g._ask_yesno_threadsafe.assert_not_called()

    def test_ein_abbruch_waehrend_der_pruefung_beendet_sie_ohne_frage(self) -> None:
        g = self._gui({})

        def lesen(quelle):
            g.is_running = False
            return self._f(ampr=True)

        g._quellfakten_der_quelle = mock.Mock(side_effect=lesen)
        g._batch_emulatoren_klaeren(["C:/A", "C:/B"])
        self.assertEqual(1, g._quellfakten_der_quelle.call_count)
        g._ask_yesno_threadsafe.assert_not_called()

    def test_ein_fehler_beim_lesen_einer_quelle_stoert_die_uebrigen_nicht(self) -> None:
        g = self._gui({})
        g._quellfakten_der_quelle = mock.Mock(side_effect=[RuntimeError("kaputt"), self._f(dlc=True)])
        g._batch_emulatoren_klaeren(["C:/A", "C:/B"])
        self.assertEqual({"C:/B": {"dlc_integrate_var": True}}, g._batch_je_spiel)

    def test_die_namenliste_der_frage_ist_gekuerzt(self) -> None:
        fakten = {"C:/S%d" % i: self._f(playgo=True) for i in range(8)}
        g = self._gui(fakten)
        g._batch_emulatoren_klaeren(sorted(fakten))
        liste = g._ask_yesno_threadsafe.call_args.args[1]
        self.assertIn("anzahl=8", liste)
        self.assertIn("S0, S1, S2, S3, S4 …", liste)
        self.assertNotIn("S5", liste)

    def test_jede_sammelkonvertierung_beginnt_ohne_den_stand_der_vorigen(self) -> None:
        g = self._gui({"C:/A": self._f(ampr=True)})
        g._batch_je_spiel = {"C:/ALT": {"ampr_integrate_var": True}}
        g._batch_emulatoren_klaeren([])
        self.assertEqual({}, g._batch_je_spiel)


class BatchAnwendenTests(unittest.TestCase):
    """``_batch_emu_anwenden``: der Stand je Spiel, ohne dass ein Spiel das naechste beeinflusst."""

    @staticmethod
    def _gui(basis: dict, je_spiel: dict):
        g = GUI.__new__(GUI)
        g._lauf_variablen = {"worker_count_var": 4}
        g._batch_emu_basis = basis
        g._batch_je_spiel = je_spiel
        return g

    def test_jedes_spiel_bekommt_die_gesetzten_und_seine_eigenen(self) -> None:
        basis = {"ampr_integrate_var": False, "dlc_integrate_var": False, "ampr_playgo_var": True}
        g = self._gui(basis, {"C:/B": {"ampr_integrate_var": True}})
        g._batch_emu_anwenden("C:/A")
        self.assertEqual((False, False, True), tuple(g._lauf_variablen[n] for n in basis))
        g._batch_emu_anwenden("C:/B")
        self.assertEqual((True, False, True), tuple(g._lauf_variablen[n] for n in basis))
        g._batch_emu_anwenden("C:/C")
        self.assertEqual((False, False, True), tuple(g._lauf_variablen[n] for n in basis), "Spiel B wirkt nicht auf C")
        self.assertEqual(4, g._lauf_variablen["worker_count_var"], "der uebrige Stand bleibt")

    def test_ein_gesetztes_kaestchen_bleibt_fuer_alle_gesetzt(self) -> None:
        g = self._gui({"ampr_integrate_var": True}, {})
        g._batch_emu_anwenden("C:/A")
        self.assertIs(True, g._lauf_variablen["ampr_integrate_var"])

    def test_ohne_stand_oder_ohne_basis_geschieht_nichts(self) -> None:
        g = GUI.__new__(GUI)
        g._batch_emu_anwenden("C:/A")
        g = self._gui({}, {"C:/A": {"ampr_integrate_var": True}})
        g._batch_emu_anwenden("C:/A")
        self.assertEqual({"worker_count_var": 4}, g._lauf_variablen)

    def test_die_vorpruefung_fragt_nach_der_arbeitskopie_auch_wegen_der_je_spiel_emulatoren(self) -> None:
        """Ohne diese Frage vorab fragte jeder Ordner einzeln: Die Vorpruefung zaehlte nur die gesetzten Kaestchen."""
        with tempfile.TemporaryDirectory() as tmp:
            ordner = os.path.join(tmp, "Spiel")
            os.makedirs(ordner)
            for je_spiel, erwartet in (({ordner: {"dlc_integrate_var": True}}, 1), ({}, 0)):
                with self.subTest(je_spiel=bool(je_spiel)):
                    g = GUI.__new__(GUI)
                    g.root = object()
                    g._t = lambda schluessel, **w: schluessel
                    g._batch_ueberschreiben = False
                    g._batch_arbeitskopie_vorab = None
                    g._arbeitskopie_vorher_aktiv = lambda: False
                    g._tk_wert = lambda name, vorgabe=None: False
                    g._batch_je_spiel = je_spiel
                    g._ask_yesno_threadsafe = mock.Mock(return_value=True)
                    self.assertTrue(g._batch_vorpruefung([ordner], tmp, "ffpkg"))
                    self.assertEqual(erwartet, g._ask_yesno_threadsafe.call_count)


class QuelltextTests(unittest.TestCase):
    def test_die_gesammelte_frage_steht_vor_der_vorpruefung_und_die_anwendung_vor_jeder_pruefung_des_wegs(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        start = text.index("def _run_flexible_conversion")
        frage = text.index("self._batch_emulatoren_klaeren(sources)", start)
        vorpruefung = text.index("self._batch_vorpruefung(sources, dst, target_type)", start)
        schleife = text.index("for idx, candidate in enumerate(sources, start=1):", start)
        anwenden = text.index("self._batch_emu_anwenden(anzeige)", start)
        sperre = text.index("reason = self._conversion_block_reason(source_type, target_type, mode, candidate)", start)
        self.assertLess(frage, vorpruefung)
        self.assertLess(vorpruefung, schleife)
        self.assertLess(schleife, anwenden)
        self.assertLess(anwenden, sperre, "_conversion_block_reason liest die Kaestchen dieses Spiels")
        self.assertEqual(1, text.count("self._batch_emulatoren_klaeren(sources)"))

    def test_die_frage_nach_dem_zwischenspeicher_je_lauf_ist_in_der_sammelkonvertierung_leer(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        start = text.index("def _batch_emulatoren_klaeren")
        ende = text.index("def _batch_emu_anwenden", start)
        self.assertIn("self._quellfakten_zwischen = {}", text[start:ende])

    def test_die_frage_steht_vor_dem_ng_hinweis_und_vor_den_anderen_rueckfragen(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        a = text.index("self._ampr_vor_dem_lauf_klaeren(mode, src)")
        ng = text.index("self._ampr_ng_vor_dem_lauf_hinweisen()", a)
        playgo = text.index("self._playgo_vor_dem_lauf_klaeren(mode, src)", a)
        arbeit = text.index("success = self._run_flexible_conversion(mode, src, dst)", a)
        self.assertLess(a, ng, "der NG-Hinweis gilt nur bei angehaktem AMPR EMU - auch nach einem Ja")
        self.assertLess(ng, playgo)
        self.assertLess(playgo, arbeit)
        self.assertEqual(1, text.count("self._ampr_vor_dem_lauf_klaeren(mode, src)"))

    def test_alle_texte_gibt_es_in_fuenf_sprachen_mit_gleichen_platzhaltern(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        erwartet = {
            "status.ampr_pruefen": [], "dialog.title.ampr_empfohlen": [], "dialog.msg.ampr_empfohlen": [],
            "main.integrate_ampr_empfohlen": [], "main.ampr_bleibt_aus": [], "main.ampr_eingeschaltet": [],
            "main.ampr_nicht_pruefbar": [], "dialog.title.ampr_wahl": [], "dialog.msg.ampr_wahl": [],
            "ampr_wahl.normal": [], "ampr_wahl.zstd": [], "ampr_wahl.lz4": [], "ampr_wahl.nein": [],
            "main.ampr_eingeschaltet_pack": ["verfahren"], "dialog.title.ampr_ng_noetig": [],
            "dialog.msg.ampr_ng_noetig": ["fassung", "fassung", "ng"], "main.ampr_ng_umgestellt": ["ng"],
            "main.ampr_ng_bleibt": ["fassung"], "main.ampr_ng_fehlt": [],
            "status.batch_emu_pruefen": ["gesamt", "nummer"], "dialog.title.batch_emu": [], "dialog.msg.batch_emu": ["liste"],
            "batch.emu_zeile_ampr": ["anzahl", "namen"], "batch.emu_zeile_dlc": ["anzahl", "namen"],
            "batch.emu_zeile_playgo": ["anzahl", "namen"], "batch.emu_eingeschaltet": ["anzahl", "emulator"],
            "batch.emu_bleibt_aus": [],
        }
        for schluessel, platzhalter in erwartet.items():
            with self.subTest(schluessel=schluessel):
                self.assertEqual({"de", "en", "es", "it", "fr"}, set(STRINGS[schluessel]))
                for sprache, text in STRINGS[schluessel].items():
                    self.assertTrue(text.strip(), sprache)
                    self.assertEqual(sorted(platzhalter), sorted(re.findall(r"\{(\w+)\}", text)), sprache)


if __name__ == "__main__":
    unittest.main()
