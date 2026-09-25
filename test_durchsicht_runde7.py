# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 7 (24.09.2026).

* **H9-10** - Ein erneut eingefuegter, zuvor gescheiterter Download bekam
  einen zweiten Eintrag - beide schrieben in dieselbe ``.teil``-Datei.
* **H9-14** - Ueber den Kacheln der Bibliothek rollte das Mausrad nicht.
* **H11-4** - "Trennen" im KLOG-Fenster weckte unter Linux den wartenden
  Empfang nicht.
* **U4-4** - "Abbrechen" in der Dump-Pruefung wartete, bis jede angefangene
  Datei zu Ende gehasht war.
* **H1-1** - Der Ausweichpfad der Einstellungsdatei galt nur beim Schreiben;
  beim Start wurden Design, Sprache und Farbschwaeche am Normalort gelesen.
* **H1-5** - Bei Achromatopsie war die Schrift auf Fehlerknoepfen weiss auf
  fast weiss, und FILEZILLA in der Titelleiste verschwand.
"""
from __future__ import annotations

import ast
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde7")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.is_running = False
    gui.root = mock.Mock()
    return gui


_BAUM: list = []


def _methode(name: str) -> ast.FunctionDef:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return next(k for k in ast.walk(_BAUM[0])
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _innere(aussen: str, innen: str) -> str:
    knoten = next(k for k in ast.walk(_methode(aussen))
                  if isinstance(k, ast.FunctionDef) and k.name == innen)
    return ast.unparse(knoten)


class DownloadDoppeltTests(unittest.TestCase):
    """H9-10: Ein gescheiterter Download wird wieder angestossen, nicht verdoppelt."""

    def test_der_alte_eintrag_laeuft_mit_der_neuen_adresse(self) -> None:
        gui = _gui()
        gestartet: list = []

        class _Faden:
            def __init__(self, target=None, args=(), **_k):
                gestartet.append(args)

            def start(self):
                pass

        with tempfile.TemporaryDirectory(prefix="runde7_") as basis:
            gui._downloads = {"alt": {
                "dateiname": "EP0001-PPSA01234_00-SPIEL.pkg", "status": "failed",
                "url": "https://alt.example/abgelaufen", "fehler": "403",
                "title_id": "PPSA01234", "art": "update",
                "pfad": os.path.join(basis, "alt.pkg")}}
            baum = mock.MagicMock()
            baum.winfo_exists.return_value = True
            gui._downloads_tree = baum
            gui._download_basis = lambda: basis
            gui._letzte_patch_ist_neueste = None
            zerlegt = {"url": "https://neu.example/frisch",
                       "dateiname": "EP0001-PPSA01234_00-SPIEL.pkg",
                       "title_id": "PPSA01234", "content_id": "EP0001-PPSA01234_00-SPIEL",
                       "host": "neu.example", "region_code": "EP", "label": "SPIEL"}
            with mock.patch.object(APP.ps5_downloads, "parse_pkg_url",
                                   return_value=dict(zerlegt)), \
                    mock.patch.object(APP.threading, "Thread", _Faden):
                ergebnis = gui._download_aufnehmen("https://neu.example/frisch")
        self.assertEqual("neu", ergebnis)
        baum.insert.assert_not_called()
        eintrag = gui._downloads["alt"]
        self.assertEqual("queued", eintrag["status"])
        self.assertEqual("https://neu.example/frisch", eintrag["url"])
        self.assertNotIn("fehler", eintrag)
        self.assertEqual([("alt",)], gestartet)
        self.assertEqual(1, len(gui._downloads))

    def test_erneut_startet_keinen_zweiten_faden(self) -> None:
        text = _innere("_show_downloads_manager", "_erneut")
        self.assertIn("anderer.get('pfad') == eintrag.get('pfad')", text)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class KachelRadTests(unittest.TestCase):
    """H9-14: Jede Kachel reicht das Mausrad an die Flaeche weiter."""

    def test_jede_kachel_rollt_die_flaeche(self) -> None:
        gui = _gui()
        gui._COLORS = dict(APP.PS5ConverterGUI._THEMES["dunkel"])
        fenster = tk.Toplevel(_WURZEL)
        try:
            _rahmen, _flaeche, innen = gui._bibliothek_kachelflaeche(fenster)
            eintraege = [{"path": os.path.join("x", "a.ffpfsc"), "name": "A",
                          "kind": "ffpfsc", "meta": {"title": "Spiel A"}}]
            gui._bibliothek_kacheln_setzen(innen, eintraege, gewaehlt="",
                                           bei_auswahl=lambda _e: None,
                                           bei_start=lambda _e: None)
            eintrag = eintraege[0]
            teile = [eintrag["_kachel"], eintrag["_bildfeld"], *eintrag["_kachel_texte"]]
            for teil in teile:
                with self.subTest(teil=str(teil)):
                    self.assertTrue(teil.bind("<MouseWheel>"),
                                    "Ueber dieser Kachel rollt nichts.")
                    self.assertTrue(teil.bind("<Button-4>"))
        finally:
            fenster.destroy()
            _WURZEL.update()


class KlogTrennenTests(unittest.TestCase):
    """H11-4: shutdown vor close - sonst wacht recv() unter Linux nicht auf."""

    def test_trennen_weckt_den_empfang(self) -> None:
        text = _innere("_show_klog_window", "_disconnect")
        i_shutdown = text.find("sock.shutdown(socket.SHUT_RDWR)")
        self.assertGreater(i_shutdown, 0, "Kein shutdown vor dem Schliessen.")
        self.assertLess(i_shutdown, text.find("sock.close()"))


class HashAbbruchTests(unittest.TestCase):
    """U4-4: Der Abbruch greift je Block, nicht erst am Dateiende."""

    def test_der_abbruch_beendet_das_lesen(self) -> None:
        from ps5_validator.utils import hashing
        with tempfile.TemporaryDirectory(prefix="runde7_") as ordner:
            datei = Path(ordner, "band.pak")
            datei.write_bytes(b"ABCDEFGHIJKLMNOPQRST")
            gefragt = {"n": 0}

            def _abbruch() -> bool:
                gefragt["n"] += 1
                return gefragt["n"] > 1          # nach dem ersten Block

            with mock.patch.object(hashing, "CHUNK_SIZE", 4):
                teil = hashing.sha256_file(datei, cancel_cb=_abbruch)
                ganz = hashing.sha256_file(datei)
        self.assertEqual(hashlib.sha256(b"ABCD").hexdigest(), teil)
        self.assertEqual(hashlib.sha256(b"ABCDEFGHIJKLMNOPQRST").hexdigest(), ganz)

    def test_die_dump_pruefung_reicht_den_abbruch_durch(self) -> None:
        text = (PROJEKT / "ps5_validator" / "modules" / "dump_validator.py").read_text(
            encoding="utf-8")
        self.assertIn("sha256_file(f, cancel_cb=self._is_cancelled)", text)


class EinstellungsdateiTests(unittest.TestCase):
    """H1-1: Lesen beim Start und Schreiben nutzen dieselbe Datei."""

    def test_der_ausweichpfad_gilt_auch_beim_start(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde7_") as basis:
            sperre = Path(basis, "keinordner")
            sperre.write_text("x", encoding="utf-8")        # eine Datei, kein Ordner
            ausweich = Path(basis, "temp")
            ausweich.mkdir()
            with mock.patch.object(APP, "_system_konfigurationsordner",
                                   lambda: str(sperre / "unterordner")), \
                    mock.patch.object(APP.tempfile, "gettempdir", lambda: str(ausweich)):
                pfad = APP._konfigurationsdatei()
                self.assertEqual(str(ausweich / "ps5converter_paths.json"), pfad)
                Path(pfad).write_text('{"theme": "hell"}', encoding="utf-8")
                self.assertEqual("hell", APP.PS5ConverterGUI._load_setting_static(
                    "theme", "dunkel"))
                self.assertEqual(pfad, _gui()._get_config_path())


class SchriftkontrastTests(unittest.TestCase):
    """H1-5: Beschriftungen bleiben lesbar - ohne den gewohnten Look zu aendern."""

    def test_fehlerknoepfe(self) -> None:
        self.assertEqual("#000000", APP.lesbare_schrift("#F0FFFF"),
                         "Weiss auf fast weiss (Achromatopsie).")
        self.assertEqual("#000000", APP.lesbare_schrift("#C8D6D6"))
        for rot in ("#FF5C74", "#D65B57", "#C0392B", "#D66A62", "#E8524F", "#090A0B"):
            with self.subTest(farbe=rot):
                self.assertEqual("#FFFFFF", APP.lesbare_schrift(rot),
                                 "Ein Design-Rot bekaeme ungefragt schwarze Schrift.")

    def test_keine_feste_weisse_schrift_auf_fehlerknoepfen(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        self.assertNotIn('error_btn"], fg="white"', quelle)
        self.assertGreaterEqual(quelle.count('lesbare_schrift(c["error_btn"])'), 3)

    def test_die_titelleiste_bleibt_lesbar(self) -> None:
        G = APP.PS5ConverterGUI
        gui = _gui()
        for design in ("hell", "metallisch"):
            with self.subTest(design=design):
                palette = dict(G._THEMES[design])
                palette.update(G._farbschwaeche_satz("achromatopsie", design))
                gui._COLORS = palette
                self.assertEqual(palette["fg_primary"],
                                 gui._titelleisten_schrift("fg_success"))
        gui._COLORS = dict(G._THEMES["dunkel"])
        self.assertEqual(gui._COLORS["fg_success"],
                         gui._titelleisten_schrift("fg_success"),
                         "Ohne Not wird keine Farbe ersetzt.")

    def test_die_diagnose_prueft_den_kontrast(self) -> None:
        gui = _gui()
        G = APP.PS5ConverterGUI
        for design in G._THEMES:
            with self.subTest(design=design):
                gui._current_theme = design
                zeilen = gui._diagnose_schriftkontrast()
                self.assertTrue(
                    any("Schrift auf Fehlerknöpfen und Titelleiste lesbar" in z
                        for z in zeilen), "\n".join(zeilen))
        self.assertIn("self._diagnose_schriftkontrast()",
                      ast.unparse(_methode("_diagnose_randlos")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
