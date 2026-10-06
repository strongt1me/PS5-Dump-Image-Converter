# -*- coding: utf-8 -*-
"""Aufgabe 1: Dump-Ordner -> Dump-Ordner mit Einbau (Wunsch vom 01.10.2026).

Der Nutzer: "bei der Aufgabe 1 gar keinen Dump Ordner erstellen kann, der
einen AMPR EMU (oder auch Asset Pack), PlayGo oder Backport enthaelt ... Es
soll gefragt werden ob direkt im Original Dump Ordner oder im Backup erstellt
werden soll. Bei Wahl des Original Dump Ordners, soll darauf hingewiesen
werden, dass die Dateien danach geaendert werden und sie danach nicht mehr
original sind."

Vorher gemessen: Aufgabe 1 bot "Dump-Ordner" nie an. Aufgabe 6 bot es mit
BACKPORT an, und der Lauf endete mit "Nicht unterstuetzte Konvertierung:
folder -> folder". Bewacht wird hier:

* die Regel (Auswahlliste, Startsperre, Beschriftung) - nur mit Einbau,
* der Ablauf mit echtem BACKPORT-Einbau in einen kleinen Dump: Sicherung
  laesst das Original unberuehrt, Original wird veraendert,
* die gefaehrlichen Faelle: Ziel = Quelle, Ziel in der Quelle, vorhandene
  Sicherung, Abbruch, gescheiterter Einbau - nichts darf am Original verloren
  gehen,
* die Rueckfrage selbst (echtes Fenster, Knoepfe per Programm gedrueckt) und
  die Warnung vor dem Einbau im Original,
* die Kommandozeile: immer Sicherung, und ``--format`` ueberlebt das
  Auffrischen der Liste.
"""
from __future__ import annotations

import ast
import hashlib
import os
import queue
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ordner_einbau")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ps5_backport                # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PS5ConverterGUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


class _Var:
    """Ersatz fuer eine Tk-Variable."""

    def __init__(self, wert) -> None:
        self._wert = wert

    def get(self):
        return self._wert

    def set(self, wert) -> None:
        self._wert = wert


def _dump_anlegen(ziel: Path) -> None:
    """Ein kleiner Dump, wie ihn der Einbau erwartet."""
    (ziel / "sce_sys").mkdir(parents=True, exist_ok=True)
    (ziel / "sce_sys" / "param.json").write_text('{"titleId":"PPSA00001"}',
                                                  encoding="utf-8")
    (ziel / "eboot.bin").write_bytes(b"\x7fELF" + os.urandom(2048))
    (ziel / "sce_module").mkdir(exist_ok=True)
    (ziel / "sce_module" / "libc.prx").write_bytes(os.urandom(1024))


def _stand(ordner: Path) -> dict:
    """Jede Datei mit ihrem Inhalt - um "unberuehrt" wirklich zu messen."""
    return {str(p.relative_to(ordner)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(ordner.rglob("*")) if p.is_file()}


def _pruefling(testfall: unittest.TestCase, *, ampr: bool = False,
               backport: bool = False) -> PS5ConverterGUI:
    """Pruefling ohne Tk - der Einbau laeuft echt (wie in
    test_integration_beim_erstellen).

    Rueckfrage und Fenster sind Stubs, die bei einem unerwarteten Aufruf
    werfen. Ein ``except Exception`` im Programm koennte das still schlucken -
    deshalb prueft der Testfall am Ende von aussen, dass sie nie liefen
    (test_qualitaetslauf.VerschluckterStubfehlerTests). Ersetzt ein Test einen
    davon bewusst, gilt die Nachkontrolle dem urspruenglichen Stub.
    """
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    protokoll: list[str] = []
    g._append_to_log = protokoll.append
    g._log_lines = protokoll
    g._current_language = "de"
    g._set_status = lambda *_a, **_k: None
    g._load_setting = lambda _k, vorgabe=None: vorgabe
    g._save_setting = lambda *_a, **_k: None
    g._fmt_bytes = lambda n: f"{n} B"
    g._get_path_size = lambda p, **_k: 0
    g.is_running = True
    g.engine_output_queue = queue.Queue()
    g._embedded_mkpfs_lock = threading.RLock()
    g.ampr_integrate_var = _Var(ampr)
    g.ampr_playgo_var = _Var(False)
    g.backport_integrate_var = _Var(backport)
    g.backport_fw_var = _Var(str(ps5_backport.FIRMWARE_STANDARD))
    g.ampr_version_var = _Var("")
    g._integration_erledigt = False
    g.task_total_source_bytes = 0
    g.task_final_output_path = ""
    # Fehlerfenster nicht wirklich zeigen - mitschreiben.
    g._geplant = []
    g._hauptfaden_planen = lambda f, *a, **k: g._geplant.append((f, a)) or True
    # Jede Rueckfrage, die ein Test nicht ausdruecklich beantwortet, ist ein
    # Fehler im Test - nie still "Ja".
    g._ask_yesno_threadsafe = mock.Mock(side_effect=AssertionError("unerwartete Rueckfrage"))
    g._im_hauptfaden = mock.Mock(side_effect=AssertionError("unerwartetes Fenster"))
    testfall.addCleanup(g._ask_yesno_threadsafe.assert_not_called)
    testfall.addCleanup(g._im_hauptfaden.assert_not_called)
    return g


def _text(schluessel: str, **werte) -> str:
    return STRINGS[schluessel]["de"].format(**werte)


class RegelTests(unittest.TestCase):
    """Auswahlliste, Startsperre und Beschriftung folgen derselben Regel."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="ordner_einbau_regel_")
        self.dump = Path(self._tmp.name) / "spiel"
        _dump_anlegen(self.dump)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_aufgabe_1_zeigt_den_dump_ordner_nur_mit_einbau(self) -> None:
        for ampr, backport in ((False, False), (True, False), (False, True), (True, True)):
            with self.subTest(ampr=ampr, backport=backport):
                g = _pruefling(self, ampr=ampr, backport=backport)
                optionen = g._get_target_options("pack_folder", "")
                self.assertEqual(ampr or backport, "folder" in optionen)
                # Mit gewaehlter Quelle dasselbe.
                optionen = g._get_target_options("pack_folder", str(self.dump))
                self.assertEqual(ampr or backport, "folder" in optionen)

    def test_der_dump_ordner_steht_hinten_und_die_vorgabe_bleibt(self) -> None:
        optionen = _pruefling(self, backport=True)._get_target_options("pack_folder", "")
        self.assertEqual("ffpfsc", optionen[0])
        self.assertEqual("folder", optionen[-1])

    def test_startsperre_folgt_der_auswahl(self) -> None:
        for mode in ("pack_folder", "universal_convert"):
            with self.subTest(aufgabe=mode):
                self.assertIn("identisch", _pruefling(self)._conversion_block_reason(
                    "folder", "folder", mode, str(self.dump)))
                self.assertEqual("", _pruefling(self, ampr=True)._conversion_block_reason(
                    "folder", "folder", mode, str(self.dump)))
                self.assertEqual("", _pruefling(self, backport=True)._conversion_block_reason(
                    "folder", "folder", mode, str(self.dump)))
        # Die Sammelkonvertierung hat keine Ordner-Quellen.
        self.assertIn("identisch", _pruefling(self, backport=True)._conversion_block_reason(
            "folder", "folder", "batch_convert", str(self.dump)))
        # Ohne Aufgabe gilt die strenge Regel weiter.
        self.assertIn("identisch", _pruefling(self, backport=True)._conversion_block_reason(
            "folder", "folder"))

    def test_aufgabe_6_auch_mit_reinem_ampr(self) -> None:
        """Bisher nur mit BACKPORT, Asset-Pack oder PlayGo - und dann
        scheiterte der Lauf. Jetzt: jeder Einbau, und er laeuft."""
        optionen = _pruefling(self, ampr=True)._get_target_options("universal_convert", str(self.dump))
        self.assertIn("folder", optionen)

    def test_die_weiche_kennt_den_weg(self) -> None:
        g = _pruefling(self, backport=True)
        with mock.patch.object(g, "_mode_ordner_einbau", return_value=True) as weg:
            self.assertTrue(g._execute_conversion_by_type(
                "folder", "folder", str(self.dump), self._tmp.name))
        weg.assert_called_once_with(str(self.dump), self._tmp.name)

    def test_die_beschriftung_traegt_den_zusatz(self) -> None:
        g = _pruefling(self, backport=True)
        beschriftung = g._zielformat_label("folder", "pack_folder")
        self.assertEqual("Dump-Ordner (mit Einbau)", beschriftung)
        self.assertEqual("folder", g._format_label_to_key(beschriftung))
        self.assertEqual("Dump-Ordner (mit Einbau)",
                         g._zielformat_label("folder", "universal_convert", str(self.dump)))
        # Fuer ein Abbild als Quelle ist der Dump-Ordner ein gewoehnliches Ziel.
        abbild = Path(self._tmp.name) / "Spiel.ffpkg"
        abbild.write_bytes(b"\x00" * 16)
        self.assertEqual("Dump-Ordner",
                         g._zielformat_label("folder", "universal_convert", str(abbild)))
        self.assertEqual("Dump-Ordner",
                         g._zielformat_label("folder", "ffpkg_to_ffpfsc", str(abbild)))

    def test_kein_neu_packen_und_keine_frage_beim_start(self) -> None:
        """Sonst meldete der Start "wird neu gepackt" und setzte den Merker."""
        g = _pruefling(self, backport=True)
        self.assertTrue(g._umhuellenden_weg_klaeren("pack_folder", str(self.dump), "folder"))
        self.assertFalse(getattr(g, "_umhuellt_neu_packen", False))
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual([], g._log_lines)

    def test_vor_dem_lauf_wird_nichts_im_ziel_geloescht(self) -> None:
        """Die allgemeine Ueberschreibpruefung loescht ein vorhandenes Ziel
        VOR dem Lauf. Fuer diesen Weg entscheidet erst die Rueckfrage, ob im
        Ziel ueberhaupt etwas entsteht."""
        g = _pruefling(self, backport=True)
        with mock.patch.object(g, "_get_selected_target_type", return_value="folder"):
            self.assertIsNone(g._get_expected_output_path(
                "pack_folder", str(self.dump), self._tmp.name))
        with mock.patch.object(g, "_get_selected_target_type", return_value="ffpfsc"):
            self.assertTrue(g._get_expected_output_path(
                "pack_folder", str(self.dump), self._tmp.name))

    def test_platzbedarf_ohne_arbeitskopie(self) -> None:
        g = _pruefling(self, backport=True)
        g._quellgroesse_ermitteln = lambda _s: 1000
        g._estimate_unpack_space_requirement = lambda _s: None
        temp, ziel, _dump = g._platzbedarf_je_quelle(str(self.dump), "folder")
        self.assertEqual(int(1000 * PS5ConverterGUI._PLATZFAKTOR_TEMP_OHNE), temp)
        self.assertEqual(int(1000 * PS5ConverterGUI._PLATZFAKTOR_ZIEL["folder"]), ziel)
        # Gegenprobe: Ein Abbild als Ziel braucht die Arbeitskopie weiterhin.
        temp, _ziel, _dump = g._platzbedarf_je_quelle(str(self.dump), "ffpfsc")
        self.assertEqual(int(1000 * PS5ConverterGUI._PLATZFAKTOR_TEMP_MIT_KOPIE), temp)

    def test_texte_sind_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS if k.startswith("ordner_einbau.")]
        schluessel.append("format.folder_einbau_suffix")
        self.assertGreaterEqual(len(schluessel), 18)
        for name in schluessel:
            with self.subTest(schluessel=name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))


class AblaufTests(unittest.TestCase):
    """Echter Einbau (BACKPORT) in einen kleinen Dump."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="ordner_einbau_lauf_")
        basis = Path(self._tmp.name)
        self.dump = basis / "quelle" / "spiel"
        _dump_anlegen(self.dump)
        self.ziel = basis / "ziel"
        self.ziel.mkdir()
        self.sicherung = self.ziel / "spiel"
        self.vorher = _stand(self.dump)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _gui(self, wahl: str) -> PS5ConverterGUI:
        g = _pruefling(self, backport=True)
        if not g._backport_fakelib_basis():
            self.skipTest("keine Ersatzbibliotheken mitgeliefert")
        g._ordner_einbau_wahl = lambda _q, _s: wahl
        return g

    def _fakelib(self, g, ordner: Path) -> Path:
        return ordner / g._fakelib_ordnername()

    def test_sicherung_laesst_das_original_unberuehrt(self) -> None:
        g = self._gui("sicherung")
        self.assertTrue(g._mode_ordner_einbau(str(self.dump), str(self.ziel)),
                        "".join(g._log_lines[-6:]))
        self.assertEqual(os.path.normcase(str(self.sicherung)),
                         os.path.normcase(g.task_final_output_path))
        self.assertTrue(any(self._fakelib(g, self.sicherung).glob("*.sprx")),
                        "In der Sicherung fehlt der Einbau")
        self.assertEqual(self.vorher, _stand(self.dump), "Das Original wurde veraendert")
        self.assertFalse(self._fakelib(g, self.dump).exists())
        # Die Sicherung ist eine Kopie - gepackte Originale duerften dort weg.
        self.assertTrue(g._ampr_ordner_ist_kopie)
        self.assertEqual(str(self.dump), g._ampr_quelle_original)

    def test_original_wird_veraendert_und_im_ziel_entsteht_nichts(self) -> None:
        g = self._gui("original")
        self.assertTrue(g._mode_ordner_einbau(str(self.dump), str(self.ziel)),
                        "".join(g._log_lines[-6:]))
        self.assertEqual(os.path.normcase(str(self.dump)),
                         os.path.normcase(g.task_final_output_path))
        self.assertTrue(any(self._fakelib(g, self.dump).glob("*.sprx")))
        self.assertEqual([], list(self.ziel.iterdir()))
        # Im Original duerfen gepackte Originale nie weg.
        self.assertFalse(g._ampr_ordner_ist_kopie)
        self.assertIn(_text("ordner_einbau.log_original", path=str(self.dump)), g._log_lines)

    def test_abbruch_in_der_rueckfrage_aendert_nichts(self) -> None:
        g = self._gui("")
        self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(self.ziel)))
        self.assertEqual(self.vorher, _stand(self.dump))
        self.assertEqual([], list(self.ziel.iterdir()))
        self.assertIn(_text("ordner_einbau.log_abgebrochen"), g._log_lines)

    def test_ziel_ist_der_elternordner_der_quelle(self) -> None:
        """Die Sicherung waere die Quelle selbst. Vor allem: nichts loeschen."""
        g = self._gui("sicherung")
        self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(self.dump.parent)))
        self.assertEqual(self.vorher, _stand(self.dump), "Die Quelle wurde angefasst")
        self.assertFalse(self._fakelib(g, self.dump).exists())
        g._ask_yesno_threadsafe.assert_not_called()
        self.assertEqual(1, len(g._geplant), "Kein Fehlerfenster eingeplant")

    def test_ziel_liegt_in_der_quelle(self) -> None:
        """Sonst kopierte sich der Ordner endlos in sich hinein."""
        g = self._gui("sicherung")
        innen = self.dump / "ausgabe"
        innen.mkdir()
        self.vorher = _stand(self.dump)
        self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(innen)))
        self.assertEqual([], list(innen.iterdir()))
        self.assertEqual(self.vorher, _stand(self.dump))

    def test_vorhandene_sicherung_ohne_ja_bleibt_stehen(self) -> None:
        g = self._gui("sicherung")
        self.sicherung.mkdir()
        (self.sicherung / "alt.txt").write_text("alt", encoding="utf-8")
        g._ask_yesno_threadsafe = mock.Mock(return_value=False)
        self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(self.ziel)))
        self.assertTrue((self.sicherung / "alt.txt").is_file())
        self.assertEqual(self.vorher, _stand(self.dump))
        # Vorbelegt ist "Nein" - ein Enter loescht nichts.
        self.assertEqual(False, g._ask_yesno_threadsafe.call_args.kwargs.get("default_yes"))

    def test_vorhandene_sicherung_mit_ja_wird_ersetzt(self) -> None:
        g = self._gui("sicherung")
        self.sicherung.mkdir()
        (self.sicherung / "alt.txt").write_text("alt", encoding="utf-8")
        g._ask_yesno_threadsafe = mock.Mock(return_value=True)
        self.assertTrue(g._mode_ordner_einbau(str(self.dump), str(self.ziel)),
                        "".join(g._log_lines[-6:]))
        self.assertFalse((self.sicherung / "alt.txt").exists())
        self.assertTrue((self.sicherung / "eboot.bin").is_file())
        self.assertEqual(self.vorher, _stand(self.dump))

    def test_gescheiterter_einbau_raeumt_die_sicherung_weg(self) -> None:
        g = self._gui("sicherung")
        with mock.patch.object(g, "_integration_anwenden", return_value=""):
            self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(self.ziel)))
        self.assertFalse(self.sicherung.exists(), "Eine halbe Sicherung blieb liegen")
        self.assertEqual(self.vorher, _stand(self.dump))
        self.assertIn(_text("ordner_einbau.log_sicherung_entfernt", path=str(self.sicherung)),
                      g._log_lines)

    def test_gescheiterter_einbau_im_original_wird_gemeldet(self) -> None:
        g = self._gui("original")
        with mock.patch.object(g, "_integration_anwenden", return_value=""):
            self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(self.ziel)))
        self.assertTrue(self.dump.is_dir(), "Das Original wurde entfernt")
        self.assertIn(_text("ordner_einbau.log_original_teilweise", path=str(self.dump)),
                      g._log_lines)

    def test_abbruch_waehrend_der_sicherung(self) -> None:
        g = self._gui("sicherung")
        g._quellgroesse_ermitteln = lambda _s: 4096
        g.is_running = False
        self.assertFalse(g._mode_ordner_einbau(str(self.dump), str(self.ziel)))
        self.assertFalse(self.sicherung.exists(), "Die halbfertige Sicherung blieb liegen")
        self.assertEqual(self.vorher, _stand(self.dump))
        self.assertIn(_text("ordner_einbau.log_sicherung_abgebrochen"), g._log_lines)

    def test_der_einbau_bekommt_die_herkunft(self) -> None:
        g = self._gui("sicherung")
        with mock.patch.object(g, "_integration_anwenden",
                               side_effect=lambda ordner, **k: ordner) as einbau:
            self.assertTrue(g._mode_ordner_einbau(str(self.dump), str(self.ziel)))
        self.assertEqual(os.path.normcase(str(self.sicherung)),
                         os.path.normcase(einbau.call_args.args[0]))
        self.assertEqual(str(self.dump), einbau.call_args.kwargs.get("herkunft"))
        self.assertNotIn("ist_quellordner", einbau.call_args.kwargs,
                         "Sonst kaeme zusaetzlich die Frage nach der Arbeitskopie")


class WahlTests(unittest.TestCase):
    """Die Rueckfrage und die Warnung vor dem Einbau im Original."""

    def _gui(self, *antworten) -> PS5ConverterGUI:
        g = _pruefling(self, backport=True)
        g.root = object()
        g._im_hauptfaden = mock.Mock(side_effect=list(antworten))
        return g

    def test_sicherung_fragt_nicht_weiter(self) -> None:
        g = self._gui("sicherung")
        self.assertEqual("sicherung", g._ordner_einbau_wahl("Q", "S"))
        self.assertEqual(1, g._im_hauptfaden.call_count)
        self.assertEqual(g._ordner_einbau_dialog, g._im_hauptfaden.call_args.args[0])

    def test_original_warnt_und_nein_bricht_ab(self) -> None:
        g = self._gui("original", False)
        self.assertEqual("", g._ordner_einbau_wahl("D:/Spiele/Spiel", "S"))
        self.assertEqual(2, g._im_hauptfaden.call_count)
        warnung = g._im_hauptfaden.call_args
        self.assertIs(APP.messagebox.askyesno, warnung.args[0])
        self.assertEqual(_text("ordner_einbau.warnung_titel"), warnung.args[1])
        self.assertIn("D:/Spiele/Spiel", warnung.args[2])
        self.assertIn("nicht mehr original", warnung.args[2])
        self.assertEqual("warning", warnung.kwargs.get("icon"))
        self.assertEqual("no", warnung.kwargs.get("default"))

    def test_original_mit_ja(self) -> None:
        g = self._gui("original", True)
        self.assertEqual("original", g._ordner_einbau_wahl("Q", "S"))

    def test_abbrechen_im_fenster(self) -> None:
        for antwort in ("", None):
            with self.subTest(antwort=antwort):
                g = self._gui(antwort)
                self.assertEqual("", g._ordner_einbau_wahl("Q", "S"))
                self.assertEqual(1, g._im_hauptfaden.call_count)

    def test_kommandozeile_nimmt_immer_die_sicherung(self) -> None:
        """Ohne Fenster ware "Original" die zerstoerende Antwort."""
        g = _pruefling(self, backport=True)
        g._cli_mode = True
        self.assertEqual("sicherung", g._ordner_einbau_wahl("Q", "S"))
        g._im_hauptfaden.assert_not_called()
        self.assertIn(_text("ordner_einbau.log_cli_sicherung", path="S"), g._log_lines)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(unittest.TestCase):
    """Die Rueckfrage als echtes Fenster - die Knoepfe per Programm gedrueckt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Der Aufbau maximiert das Programmfenster. Bliebe es sichtbar,
        # erschiene jede Rueckfrage echt auf dem Bildschirm - mit Fokus und
        # Grab, im Takt von Millisekunden. Gemessen am 01.10.2026: Dann wurde
        # in rund jedem zweiten Lauf "ABBRECHEN" im naechsten Fenster ohne
        # Zutun des Tests ausgeloest (aus der Ereignisschleife, 15-25 ms nach
        # dem Oeffnen; welches Fensterereignis, liess sich nicht eingrenzen -
        # jede Aufzeichnung veraenderte das Zeitverhalten). Verborgen: 90 von
        # 90 schnellen Durchgaengen richtig, die Datei 10 von 10 Laeufen gruen.
        _WURZEL.withdraw()
        for kind in _WURZEL.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    #: So oft wird die Rueckfrage neu geoeffnet, wenn sie sich schloss, noch bevor
    #: der Test sie bedienen konnte. Gemessen am 04.10.2026 (Volllauf: zwei
    #: Untertests rot; einzeln 2 von 8 Laeufen, am letzten Commit 1 von 10
    #: ebenso): Das Fenster schliesst sich im selben Augenblick, in dem es
    #: erscheint - ueber seinen Schliessen-Handler oder die Bedienung eines
    #: Knopfes, ohne dass der Test etwas gedrueckt hat. Eingegrenzt: Das
    #: Schliessen laeuft aus der Ereignisschleife (Unmap/Map nach 5 ms, im
    #: selben Takt das Schliessen); was es ausloest, blieb offen - jede
    #: Aufzeichnung veraendert das Zeitverhalten (wie schon am 01.10.2026).
    #: Wiederholt wird nur, wenn das Fenster da war und der Test nicht zum
    #: Zug kam; erscheint es gar nicht oder bleibt es offen, scheitert der Test
    #: beim ersten Mal.
    _VERSUCHE = 3

    def _dialog_mit(self, aktion) -> str:
        """Oeffnet die Rueckfrage und fuehrt ``aktion(fenster)`` darin aus.

        Bedient wird genau das Fenster, das dieser Aufruf oeffnet - nicht das
        erste mit passendem Titel. Mit Notbremse: Schliesst die Aktion das
        Fenster nicht, macht es die Bremse nach 5 s zu, und der Test
        scheitert, statt an ``wait_window`` haengen zu bleiben. Was danach
        noch eingeplant ist, wird abgesagt - es darf in kein spaeteres Fenster
        greifen.

        Schloss sich das Fenster vor der ersten Bedienung von selbst
        (:data:`_VERSUCHE`), wird die Rueckfrage noch einmal geoeffnet.
        """
        for versuch in range(1, self._VERSUCHE + 1):
            wahl, gesehen = self._dialog_einmal(aktion)
            if "texte" in gesehen or "fenster" not in gesehen or versuch == self._VERSUCHE:
                break
        self.assertIn("texte", gesehen, "Die Rueckfrage ist nie erschienen")
        self.assertNotIn("gebremst", gesehen, "Die Aktion hat das Fenster nicht geschlossen")
        self.assertFalse(gesehen["fenster"].winfo_exists(), "Das Fenster blieb offen")
        self._texte_gesehen = gesehen["texte"]
        return wahl

    def _dialog_einmal(self, aktion) -> "tuple[str, dict]":
        """Ein Durchgang von :meth:`_dialog_mit` - liefert die Wahl und was gesehen wurde."""
        gesehen: dict = {}
        jobs: list = []
        echt = self.app._build_modern_toplevel

        def _bauen(*a, **k):
            fenster = echt(*a, **k)
            gesehen.setdefault("fenster", fenster)
            return fenster

        def _bremse(fenster) -> None:
            if fenster.winfo_exists():
                gesehen["gebremst"] = True
                fenster.destroy()

        def _druecken() -> None:
            fenster = gesehen.get("fenster")
            if fenster is None:
                jobs.append(_WURZEL.after(10, _druecken))
                return
            gesehen["texte"] = self._texte(fenster)
            jobs.append(_WURZEL.after(5000, _bremse, fenster))
            aktion(fenster)

        self.app._build_modern_toplevel = _bauen
        try:
            jobs.append(_WURZEL.after(0, _druecken))
            wahl = self.app._ordner_einbau_dialog("D:/Quelle/Spiel", "E:/Ziel/Spiel")
        finally:
            del self.app._build_modern_toplevel
            for job in jobs:
                try:
                    _WURZEL.after_cancel(job)
                except tk.TclError:
                    pass
        return wahl, gesehen

    @staticmethod
    def _texte(fenster) -> list[str]:
        texte, offen = [], [fenster]
        while offen:
            w = offen.pop()
            offen.extend(w.winfo_children())
            try:
                texte.append(str(w.cget("text")))
            except tk.TclError:
                pass
        return texte

    @staticmethod
    def _knopf(fenster, text: str):
        offen = [fenster]
        while offen:
            w = offen.pop()
            offen.extend(w.winfo_children())
            # Die Knoepfe der Fenster sind seit dem 05.10.2026 runde Ersatzteile (``fenster_pillen.Button``).
            if w.__class__.__name__ == "Button" and str(w.cget("text")) == text:
                return w
        raise AssertionError("Knopf %r fehlt" % text)

    def test_jeder_knopf_liefert_seine_wahl(self) -> None:
        for schluessel, erwartet in (("ordner_einbau.knopf_sicherung", "sicherung"),
                                     ("ordner_einbau.knopf_original", "original"),
                                     ("action.cancel", "")):
            with self.subTest(knopf=schluessel):
                text = self.app._t(schluessel)
                wahl = self._dialog_mit(lambda f, t=text: self._knopf(f, t).invoke())
                self.assertEqual(erwartet, wahl)

    def test_das_kreuz_des_fensters_bricht_ab(self) -> None:
        """Ueber den Schliessen-Handler des Fensters (wie das X oben rechts).

        Escape laesst sich hier nicht echt druecken: Das Hauptfenster ist im
        Test verborgen, ein Tastendruck geht an das Fenster mit dem Fokus.
        Dass Escape gebunden ist, prueft der Test daneben."""
        def _kreuz(fenster) -> None:
            fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
        self.assertEqual("", self._dialog_mit(_kreuz))

    def test_escape_ist_gebunden(self) -> None:
        def _pruefen_und_schliessen(fenster) -> None:
            self._escape_bindung = fenster.bind("<Escape>")
            fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
        self._dialog_mit(_pruefen_und_schliessen)
        self.assertTrue(self._escape_bindung, "Escape schliesst die Rueckfrage nicht")

    def test_das_fenster_nennt_beide_orte(self) -> None:
        self._dialog_mit(lambda f: self._knopf(f, self.app._t("action.cancel")).invoke())
        alles = "\n".join(self._texte_gesehen)
        self.assertIn("D:/Quelle/Spiel", alles)
        self.assertIn("E:/Ziel/Spiel", alles)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class AuswahllisteTests(unittest.TestCase):
    """Am echten Programm: Das Kaestchen schaltet den Eintrag sofort."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        app = self.app
        vorher = (app.current_mode.get(), app.target_format.get(),
                  app.backport_integrate_var.get(), app.ampr_integrate_var.get())

        def _zurueck() -> None:
            app.backport_integrate_var.set(vorher[2])
            app.ampr_integrate_var.set(vorher[3])
            app._on_integration_changed(speichern=False)
            app._set_mode_from_sidebar(vorher[0])
            app.target_format.set(vorher[1])

        self.addCleanup(_zurueck)

    def test_backport_bringt_den_eintrag_und_nimmt_ihn_wieder(self) -> None:
        app = self.app
        eintrag = "Dump-Ordner (mit Einbau)"
        app.ampr_integrate_var.set(False)
        app.backport_integrate_var.set(False)
        app._set_mode_from_sidebar("pack_folder")
        app._on_integration_changed(speichern=False)
        self.assertNotIn(eintrag, app.format_combo["values"])

        app.backport_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self.assertIn(eintrag, app.format_combo["values"])
        app.target_format.set(eintrag)
        self.assertEqual("folder", app._get_selected_target_type())

        app.backport_integrate_var.set(False)
        app._on_integration_changed(speichern=False)
        self.assertNotIn(eintrag, app.format_combo["values"])
        self.assertEqual("ffpfsc", app._get_selected_target_type(),
                         "Nach dem Abwaehlen muss die Vorgabe greifen")

    def test_kommandozeilen_format_ueberlebt_das_auffrischen(self) -> None:
        """Die Reihenfolge aus _run_cli: Format setzen, danach frischt
        _on_integration_changed die Liste auf. Bis zum 01.10.2026 wurde dabei
        aus "--format ffpkg" in Aufgabe 4 still ein Dump-Ordner."""
        app = self.app
        with TemporaryDirectory(prefix="ordner_einbau_cli_") as tmp:
            dump = Path(tmp) / "spiel"
            _dump_anlegen(dump)
            pkg = Path(tmp) / "Spiel.ffpkg"
            pkg.write_bytes(b"\x00" * 16)
            for mode, quelle, schluessel, backport in (
                    ("ffpkg_to_ffpfsc", pkg, "ffpkg", False),
                    ("pack_folder", dump, "folder", True)):
                with self.subTest(aufgabe=mode, format=schluessel):
                    app.backport_integrate_var.set(backport)
                    app.source_path.set(str(quelle))
                    app._set_mode_from_sidebar(mode)
                    app.target_format.set(app._zielformat_label(schluessel, mode))
                    app._on_integration_changed(speichern=False)
                    self.assertEqual(schluessel, app._get_selected_target_type())
            app.source_path.set("")

    def test_run_cli_setzt_die_beschriftung_der_liste(self) -> None:
        """Dass _run_cli das Format ueber _zielformat_label setzt - als
        Syntaxbaum, nicht als Textsuche (die stirbt still beim Umbauen)."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        funktion = next((k for k in ast.walk(baum)
                         if isinstance(k, ast.FunctionDef) and k.name == "_run_cli"), None)
        self.assertIsNotNone(funktion, "_run_cli heisst nicht mehr so")
        aufrufe = [k for k in ast.walk(funktion)
                   if isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "_zielformat_label"
                   and k.args and ast.unparse(k.args[0]) == "args.format"]
        self.assertTrue(aufrufe, "_run_cli setzt --format nicht ueber _zielformat_label")


if __name__ == "__main__":
    unittest.main(verbosity=2)
