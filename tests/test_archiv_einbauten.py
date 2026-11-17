# -*- coding: utf-8 -*-
"""Archiv als Quelle: Rueckfrage, ob fruehere Einbauten aus der entpackten Kopie entfernt werden (Nutzerwunsch 17.11.2026).

Gemeldet wurde die Preflight-Warnung "Der Quellordner enthaelt schon Teile aus einem frueheren Einbau" bei einem 7z-Archiv - das Archiv
wird ohnehin entpackt, die Kopie gehoert dem Programm. Jetzt fragt es vorher: Ja entfernt AMPR-EMU-Bibliothek und PlayGo-Stub aus der
Kopie, Nein laesst alles, wie es war. Nie bei einem Ordner des Anwenders, nie still, das Archiv bleibt unveraendert.
"""
from __future__ import annotations

import inspect
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES   # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

HAKEN = ("ampr_integrate_var", "ampr_playgo_var", "dlc_integrate_var", "backport_integrate_var")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ArchivEinbautenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        a = self.app
        self._vorher = {"haken": {n: getattr(a, n).get() for n in HAKEN}, "herkunft": dict(getattr(a, "_archiv_herkunft", {}) or {}),
                        "antwort": dict(getattr(a, "_archiv_einbauten_antwort", {}) or {}),
                        "schatten": getattr(a, "_archiv_schatten", None), "mode": a.current_mode.get(),
                        "cli": getattr(a, "_cli_mode", False)}
        for n in HAKEN:
            getattr(a, n).set(False)
        a.current_mode.set("pack_folder")
        a._archiv_herkunft = {}
        a._archiv_einbauten_antwort = {}
        a._archiv_schatten = {}
        a._cli_mode = False
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = tmp.name
        self.kopie = os.path.join(self.t, "ps5conv_archiv_abc123", "PPSA00001-app")
        os.makedirs(os.path.join(self.kopie, "fakelib"))
        self.archiv = os.path.join(self.t, "spiel.7z")
        Path(self.archiv).write_bytes(b"7z")

    def tearDown(self) -> None:
        a, v = self.app, self._vorher
        for n, wert in v["haken"].items():
            getattr(a, n).set(wert)
        a._archiv_herkunft = v["herkunft"]
        a._archiv_einbauten_antwort = v["antwort"]
        a._archiv_schatten = v["schatten"]
        a._cli_mode = v["cli"]
        a.current_mode.set(v["mode"])

    # ------------------------------------------------------------------ Hilfen
    def _herkunft(self, ordner: "str | None" = None) -> None:
        ordner = ordner or self.kopie
        self.app._archiv_herkunft[self.app._archiv_schluessel(ordner)] = self.archiv

    def _lege(self, *namen: str, ordner: "str | None" = None) -> None:
        fakelib = Path(ordner or self.kopie, "fakelib")
        fakelib.mkdir(parents=True, exist_ok=True)
        for name in namen:
            (fakelib / name).write_bytes(b"x")

    def _fakelib(self, ordner: "str | None" = None) -> "set[str]":
        return set(os.listdir(os.path.join(ordner or self.kopie, "fakelib")))

    def _frage(self, antwort: bool = True):
        return mock.patch.object(self.haupt.messagebox, "askyesno", return_value=antwort)

    # ------------------------------------------------------------------ Ja und Nein
    def test_ja_entfernt_ampr_und_playgo_aus_der_kopie(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx", "libScePlayGo.sprx")
        with self._frage(True) as frage:
            entfernt = a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        frage.assert_called_once()
        self.assertEqual(["fakelib/libSceAmpr.sprx", "fakelib/libScePlayGo.sprx"], sorted(entfernt))
        self.assertEqual(set(), self._fakelib())
        self.assertEqual([], a._fruehere_einbauten(self.kopie), "die Preflight-Warnung hat danach nichts mehr zu nennen")
        self.assertTrue(os.path.isfile(self.archiv), "das Archiv wird nicht angefasst")

    def test_die_frage_nennt_das_archiv_und_die_dateien(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx", "libScePlayGo.sprx")
        with self._frage(False) as frage:
            a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        titel, text = frage.call_args.args[:2]
        self.assertEqual(a._t("archiv_einbau.titel"), titel)
        self.assertIn("spiel.7z", text)
        self.assertIn("AMPR EMU (fakelib/libSceAmpr.sprx)", text)
        self.assertIn("PlayGo (fakelib/libScePlayGo.sprx)", text)
        self.assertNotIn("{", text, "kein offener Platzhalter")

    def test_nein_laesst_alles_wie_es_war_und_fragt_nicht_noch_einmal(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx", "libScePlayGo.sprx")
        with self._frage(False) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie), "derselbe Stand: keine zweite Frage")
        frage.assert_called_once()
        self.assertEqual({"libSceAmpr.sprx", "libScePlayGo.sprx"}, self._fakelib())
        self.assertEqual(["fakelib/libSceAmpr.sprx", "fakelib/libScePlayGo.sprx"], sorted(a._fruehere_einbauten(self.kopie)),
                         "die Preflight-Warnung nennt sie weiter, wie bisher")

    def test_ein_neuer_stand_wird_neu_gefragt(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx")
        with self._frage(False) as frage:
            a._archiv_einbauten_klaeren("pack_folder", self.kopie)
            self._lege("libScePlayGo.sprx")                       # es kam etwas dazu: anderer Stand
            a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        self.assertEqual(2, frage.call_count)

    # ------------------------------------------------------------------ nie ein Ordner des Anwenders
    def test_ein_ordner_des_anwenders_wird_nie_gefragt_und_nie_angefasst(self) -> None:
        a = self.app
        eigener = os.path.join(self.t, "MeinSpiel")
        self._lege("libSceAmpr.sprx", "libScePlayGo.sprx", ordner=eigener)
        with self._frage(True) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", eigener), "kein Archiv: keine Herkunft")
            self._herkunft(eigener)
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", eigener),
                             "selbst mit eingetragener Herkunft: der Ordner liegt nicht in einem Entpackordner des Programms")
        frage.assert_not_called()
        self.assertEqual({"libSceAmpr.sprx", "libScePlayGo.sprx"}, self._fakelib(eigener))

    def test_ein_entpackordner_ohne_herkunft_wird_nicht_angefasst(self) -> None:
        a = self.app
        self._lege("libSceAmpr.sprx")
        with self._frage(True) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
        frage.assert_not_called()
        self.assertEqual({"libSceAmpr.sprx"}, self._fakelib())

    def test_ein_zip_schattenordner_wird_nicht_gefragt(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx")
        a._archiv_schatten[a._archiv_schluessel(self.kopie)] = {"archiv": self.archiv}
        with self._frage(True) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
        frage.assert_not_called()

    def test_auf_der_kommandozeile_wird_nicht_gefragt(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx")
        a._cli_mode = True
        with self._frage(True) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
        frage.assert_not_called()
        self.assertEqual({"libSceAmpr.sprx"}, self._fakelib())

    def test_andere_aufgaben_fragen_nicht(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx")
        with self._frage(True) as frage:
            for modus in ("inspect", "dump_validator", "gibt_es_nicht"):
                self.assertEqual([], a._archiv_einbauten_klaeren(modus, self.kopie), modus)
        frage.assert_not_called()

    # ------------------------------------------------------------------ was gefragt wird
    def test_ohne_fruehere_einbauten_gibt_es_keine_frage(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceFoo.sprx")                               # irgendeine Bibliothek, kein Einbau des Programms
        with self._frage(True) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
        frage.assert_not_called()
        self.assertEqual({"libSceFoo.sprx"}, self._fakelib())

    def test_ein_angehaktes_kaestchen_haelt_seine_datei_heraus(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx", "libScePlayGo.sprx")
        a.ampr_integrate_var.set(True)                             # AMPR EMU wird ohnehin eingebaut: kein "Rest"
        with self._frage(True) as frage:
            entfernt = a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        self.assertEqual(["fakelib/libScePlayGo.sprx"], entfernt)
        self.assertNotIn("libSceAmpr", frage.call_args.args[1])
        self.assertEqual({"libSceAmpr.sprx"}, self._fakelib())

    def test_eine_datei_mit_sicherung_wird_nicht_angeboten(self) -> None:
        """Mit ``.orig`` stammt die Datei vom Spiel selbst; das Wiederherstellen ist Sache des AMPR EMU Managers."""
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx", "libSceAmpr.sprx.orig")
        with self._frage(True) as frage:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
        frage.assert_not_called()
        self.assertEqual({"libSceAmpr.sprx", "libSceAmpr.sprx.orig"}, self._fakelib())
        self.assertEqual(["fakelib/libSceAmpr.sprx"], a._fruehere_einbauten(self.kopie), "die Preflight-Warnung nennt sie weiter")

    def test_backport_markierung_und_asset_pack_bleiben_die_warnung_nennt_sie_weiter(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx", "fw7")
        with self._frage(True) as frage:
            entfernt = a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        self.assertEqual(["fakelib/libSceAmpr.sprx"], entfernt)
        self.assertNotIn("fw7", frage.call_args.args[1])
        self.assertEqual({"fw7"}, self._fakelib())
        self.assertEqual(["fakelib/fw7"], a._fruehere_einbauten(self.kopie))

    def test_scheitert_das_entfernen_wird_es_gemeldet_und_nichts_bricht(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx")
        with self._frage(True), mock.patch.object(type(a), "_ampr_remove_library", return_value=False), \
                mock.patch.object(a, "_append_to_log") as protokoll:
            self.assertEqual([], a._archiv_einbauten_klaeren("pack_folder", self.kopie))
        gemeldet = " ".join(str(aufruf.args[0]) for aufruf in protokoll.call_args_list)
        self.assertIn(a._t("archiv_einbau.log_fehler", dateien="fakelib/libSceAmpr.sprx").strip(), gemeldet)
        self.assertEqual({"libSceAmpr.sprx"}, self._fakelib())

    def test_das_protokoll_sagt_was_entfernt_wurde_und_was_bleibt(self) -> None:
        a = self.app
        self._herkunft()
        self._lege("libSceAmpr.sprx")
        with self._frage(True), mock.patch.object(a, "_append_to_log") as protokoll:
            a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        gemeldet = " ".join(str(aufruf.args[0]) for aufruf in protokoll.call_args_list)
        self.assertIn(a._t("archiv_einbau.log_entfernt", dateien="fakelib/libSceAmpr.sprx").strip(), gemeldet)
        self._lege("libScePlayGo.sprx")
        with self._frage(False), mock.patch.object(a, "_append_to_log") as protokoll:
            a._archiv_einbauten_klaeren("pack_folder", self.kopie)
        gemeldet = " ".join(str(aufruf.args[0]) for aufruf in protokoll.call_args_list)
        self.assertIn(a._t("archiv_einbau.log_bleibt", dateien="fakelib/libScePlayGo.sprx").strip(), gemeldet)

    # ------------------------------------------------------------------ Einbindung und Texte
    def test_der_start_fragt_vor_der_preflight_warnung(self) -> None:
        quelle = inspect.getsource(type(self.app)._launch_task)
        frage = quelle.index("self._archiv_einbauten_klaeren(mode, src)")
        preflight = quelle.index("self._run_preflight_checks(")
        self.assertLess(frage, preflight, "erst fragen und entfernen, dann pruefen und warnen")

    def test_jeder_text_gibt_es_in_allen_fuenf_sprachen_mit_denselben_platzhaltern(self) -> None:
        for schluessel in ("archiv_einbau.titel", "archiv_einbau.frage", "archiv_einbau.log_entfernt", "archiv_einbau.log_bleibt",
                           "archiv_einbau.log_fehler"):
            with self.subTest(schluessel=schluessel):
                self.assertEqual(set(SUPPORTED_LANGUAGES), set(STRINGS[schluessel]))
                platzhalter = {sp: frozenset(re.findall(r"\{(\w+)\}", text)) for sp, text in STRINGS[schluessel].items()}
                self.assertEqual(1, len(set(platzhalter.values())), platzhalter)
        self.assertEqual({"name", "dateien"}, set(re.findall(r"\{(\w+)\}", STRINGS["archiv_einbau.frage"]["de"])))


if __name__ == "__main__":
    unittest.main()
