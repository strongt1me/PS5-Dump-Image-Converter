# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 11 (24.09.2026).

Die letzten "mittel"-Befunde und drei "niedrig" mit echter Wirkung:

* **H10-1** - BACKPORT: eine vollstaendige Sicherung hiess im Fehlerfall
  "angefangen" - wer das glaubt, loescht die einzige intakte Kopie.
* **H2-2** - Selbst-Ziel: Start und Aufgabenfaden erkannten es an
  verschiedenen Merkmalen; der Faden brach ab oder uebersprang die Datei.
* **H2-3** - Platz: .ffpfsc -> .exFAT entpackt im Arbeitsordner, gerechnet
  wurde beim Ziel.
* **H2-4** - _expects_dump_folder las die Tk-Variable im Faden.
* **H3-11** - Spiel holen: Markierung und Pfadzeile liefen auseinander
  (seit 25.09.2026 am Herunterladen der Bibliothek geprueft).
* **H3-14** - Konsolenfenster: der Endstand ging verloren.
* **H3-20** - Rueckfragen aus dem Faden warteten ohne Ende.
"""
from __future__ import annotations

import ast
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde11")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

GB = 1024 ** 3
_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.root = _WURZEL
    return gui


def _ordner(test: unittest.TestCase, praefix: str) -> Path:
    pfad = Path(tempfile.mkdtemp(prefix=praefix))
    test.addCleanup(shutil.rmtree, pfad, True)
    return pfad


def _im_faden(aufruf, grenze: float = 10.0):
    """(fertig, ergebnis, fehler) - fertig ist False, wenn der Faden haengt."""
    ablage: dict = {}

    def _lauf() -> None:
        try:
            ablage["wert"] = aufruf()
        except BaseException as exc:  # noqa: BLE001
            ablage["fehler"] = exc

    faden = threading.Thread(target=_lauf, daemon=True)
    faden.start()
    faden.join(grenze)
    return not faden.is_alive(), ablage.get("wert"), ablage.get("fehler")


def _schleife_bis(bedingung, grenze: float = 15.0) -> bool:
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(20, _takt)
    _WURZEL.mainloop()
    return bool(bedingung())


# ---------------------------------------------------------------- H10-1

class BackportSicherungTests(unittest.TestCase):
    """H10-1: Eine vollstaendige Sicherung heisst im Fehlerfall vollstaendig."""

    def test_fertige_sicherung_heisst_nicht_angefangen(self) -> None:
        basis = _ordner(self, "r11_bp_")
        spiel = basis / "PPSA01234"
        (spiel / "sce_sys").mkdir(parents=True)
        (spiel / "eboot.bin").write_bytes(b"\x7fELF" + bytes(60))
        gui = _gui()
        geplant: list = []
        gui.root = types.SimpleNamespace(
            after=lambda _ms, rueckruf, *werte: geplant.append((rueckruf, werte)))
        meldungen: list = []
        with mock.patch.object(APP.ps5_backport, "sdk_paar", lambda _fw: (0, 0)), \
                mock.patch.object(APP.ps5_backport, "kandidaten",
                                  mock.Mock(side_effect=OSError(28, "Kein Platz"))), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda _titel, text, **_k: meldungen.append(text)):
            gui._backport_worker(
                ordner=str(spiel), firmware=10, sicherung=True, libs=False,
                libc=False, baum=None, zeilen={},
                stand_var=types.SimpleNamespace(set=lambda _t: None), laeuft={},
                start_btn=None, analyse_btn=None,
                win=types.SimpleNamespace(winfo_exists=lambda: True))
            for rueckruf, werte in geplant:
                rueckruf(*werte)
        protokoll = "".join(gui.protokoll)
        self.assertNotIn("Angefangene Sicherung", protokoll,
                         "Die vollstaendige Sicherung heisst im Protokoll 'angefangen'.")
        self.assertIn("vollständig", protokoll)
        self.assertEqual(1, len(meldungen))
        self.assertIn("vollständig", meldungen[0])
        self.assertNotIn("Angefangene", meldungen[0])


# ---------------------------------------------------------------- H2-2

class SelbstzielTests(unittest.TestCase):
    """H2-2: Der Start setzt den Merker, den der Faden liest."""

    def _gui(self):
        gui = _gui()
        gui._integration_gewaehlt = lambda: True
        gui._selbstziel_erlaubt = lambda: True
        gui._cli_mode = False
        gui._ask_yesno_threadsafe = mock.Mock(
            side_effect=AssertionError("Ein Selbst-Ziel fragt nicht"))
        # Von aussen geprueft: Ein except Exception im Programm schluckte den
        # AssertionError sonst still (test_qualitaetslauf).
        self.addCleanup(gui._ask_yesno_threadsafe.assert_not_called)
        return gui

    def test_ffpfs_nach_ffpfs(self) -> None:
        quelle = _ordner(self, "r11_sz_") / "Spiel.ffpfs"
        quelle.write_bytes(b"x")
        gui = self._gui()
        gui._umhuellt_neu_packen = False
        self.assertTrue(gui._umhuellenden_weg_klaeren("unpack_to_exfat", str(quelle), "ffpfs"))
        self.assertTrue(gui._umhuellt_neu_packen,
                        "Der Faden bricht sonst mit 'Quelle und Zielformat identisch' ab.")

    def test_sammelkonvertierung_mit_selbst_ziel(self) -> None:
        basis = _ordner(self, "r11_sz_")
        (basis / "a.exfat").write_bytes(b"x")
        (basis / "b.ffpkg").write_bytes(b"x")
        gui = self._gui()
        gui._batch_sources = [str(basis / "a.exfat"), str(basis / "b.ffpkg")]
        gui._umhuellt_neu_packen = False
        self.assertTrue(gui._umhuellenden_weg_klaeren("batch_convert", "", "exfat"))
        self.assertTrue(gui._umhuellt_neu_packen,
                        "a.exfat wird sonst still als 'liegt schon vor' uebersprungen.")


# ---------------------------------------------------------------- H2-3

_Platz = namedtuple("_Platz", "total used free")


class PlatzTests(unittest.TestCase):
    """H2-3: .ffpfsc -> .exFAT entpackt im Arbeitsordner."""

    def _gui(self):
        gui = _gui()
        gui._quellgroesse_ermitteln = lambda _q: 24 * GB
        gui._estimate_unpack_space_requirement = lambda _q: 102 * GB
        gui._integration_gewuenscht = lambda: False
        gui._umhuellt_neu_packen = False
        gui._dump_im_arbeitsordner = lambda: False
        return gui

    def test_schaetzung_bucht_das_entpacken_im_arbeitsordner(self) -> None:
        temp, ziel = self._gui()._platzbedarf_schaetzen("unpack_to_exfat", "x.ffpfsc", "exfat")
        self.assertGreaterEqual(temp, 102 * GB, "Der Arbeitsordner braucht Innenabbild und Dateien.")
        self.assertLess(ziel, 102 * GB, "Ans Ziel kommt nur die fertige .exfat.")
        self.assertGreaterEqual(ziel, 51 * GB)

    def test_nach_ordner_bleibt_es_beim_ziel(self) -> None:
        temp, ziel = self._gui()._platzbedarf_schaetzen("unpack_to_exfat", "x.ffpfsc", "folder")
        self.assertEqual(102 * GB, ziel)
        self.assertLess(temp, 102 * GB)

    def test_vorabpruefung_warnt_beim_arbeitsordner(self) -> None:
        basis = _ordner(self, "r11_platz_")
        quelle = basis / "Spiel.ffpfsc"
        quelle.write_bytes(b"x")
        arbeit, ziel = basis / "arbeit", basis / "ziel"
        arbeit.mkdir()
        ziel.mkdir()
        gui = self._gui()
        gui._get_runtime_temp_dir = lambda: str(arbeit)
        frei = {str(arbeit): 60 * GB, str(ziel): 200 * GB}

        def _platz(pfad):
            return _Platz(500 * GB, 0, frei.get(os.fspath(pfad), 200 * GB))

        with mock.patch.object(APP.shutil, "disk_usage", _platz):
            _fehler, warnungen = gui._run_preflight_checks(
                "unpack_to_exfat", str(quelle), str(ziel), target_type="exfat")
        text = "\n".join(warnungen)
        self.assertIn("Arbeitsordner", text, "Der Engpass im Arbeitsordner bleibt unerwaehnt.")
        self.assertNotIn("Zielordner hat wenig", text)


# ---------------------------------------------------------------- H2-4

class DumpOrdnerErwartetTests(unittest.TestCase):
    """H2-4: Im Faden gilt das Zielformat vom Start."""

    def test_im_faden_aus_dem_startstand(self) -> None:
        gui = _gui()

        class _NurHauptfaden:
            def get(self):
                raise AssertionError("Tk-Variable im Faden gelesen")

        gui.target_format = _NurHauptfaden()
        gui._lauf_zielformat = "folder"
        fertig, wert, fehler = _im_faden(lambda: gui._expects_dump_folder("unpack_to_exfat"))
        self.assertTrue(fertig)
        self.assertIsNone(fehler)
        self.assertTrue(wert, "Die Dump-Pruefung faellt sonst weg.")


# ---------------------------------------------------------------- H3-14

class TaktTests(unittest.TestCase):
    """H3-14: Erst den Stand des Fadens lesen, dann anzeigen."""

    def test_alle_taktfunktionen(self) -> None:
        takte = [f for f in ast.walk(_baum())
                 if isinstance(f, ast.FunctionDef) and f.name == "_takt"
                 and "win.after(120, _takt)" in ast.unparse(f)]
        # Bis zum 25.09.2026 acht: Die Fenster "Spiel holen" und
        # "Zurueckspielen" gingen mit ihren Takten in der Bibliothek auf -
        # dort heisst der Takt _anzeigen (Pruefung darunter).
        self.assertEqual(6, len(takte))
        for takt in takte:
            with self.subTest(zeile=takt.lineno):
                zuweisungen = [a for a in takt.body if isinstance(a, ast.Assign)
                               and ast.unparse(a) == "aktiv = laeuft['aktiv']"]
                self.assertEqual(1, len(zuweisungen), "Der Stand wird nicht vorher gelesen.")
                erste_anzeige = next(a for a in takt.body if isinstance(a, ast.Try))
                self.assertLess(zuweisungen[0].lineno, erste_anzeige.lineno)
                spaet = [a.lineno for a in takt.body if isinstance(a, ast.If)
                         and "laeuft['aktiv']" in ast.unparse(a.test)]
                self.assertEqual([], spaet, "Nach der Anzeige wird wieder frisch gelesen.")

    def test_der_takt_der_ordneruebertragung(self) -> None:
        """Dieselbe Regel fuer das Holen und Senden von Ordnern in der Bibliothek."""
        methode = next(f for f in ast.walk(_baum()) if isinstance(f, ast.FunctionDef)
                       and f.name == "_bibliothek_ordner_uebertragen")
        takt = next(f for f in ast.walk(methode) if isinstance(f, ast.FunctionDef)
                    and f.name == "_anzeigen")
        zuweisungen = [a for a in takt.body if isinstance(a, ast.Assign)
                       and ast.unparse(a) == "ende = lauf['ende']"]
        self.assertEqual(1, len(zuweisungen), "Der Stand wird nicht vorher gelesen.")
        erste_anzeige = next(a for a in takt.body if isinstance(a, ast.Try))
        self.assertLess(zuweisungen[0].lineno, erste_anzeige.lineno)
        spaet = [a.lineno for a in takt.body if isinstance(a, ast.If)
                 and "lauf['ende']" in ast.unparse(a.test)]
        self.assertEqual([], spaet, "Nach der Anzeige wird wieder frisch gelesen.")


# ---------------------------------------------------------------- H3-20

class RueckfrageAusDemFadenTests(unittest.TestCase):
    """H3-20: Ohne erreichbaren Hauptfaden endet die Rueckfrage mit Nein."""

    def test_after_wirft(self) -> None:
        gui = _gui()

        def _after(*_a):
            raise RuntimeError("main thread is not in main loop")

        gui.root = types.SimpleNamespace(after=_after, winfo_exists=lambda: True)
        for aufruf, erwartet in ((lambda: gui._ask_yesno_threadsafe("T", "F"), False),
                                 (lambda: gui._ask_directory_threadsafe("T"), ""),
                                 (lambda: gui._im_hauptfaden(lambda: "ja"), None)):
            with self.subTest(erwartet=erwartet):
                fertig, wert, fehler = _im_faden(aufruf)
                self.assertTrue(fertig)
                self.assertIsNone(fehler, "Die Ausnahme kam im Faden an - ein Absturz statt Nein.")
                self.assertEqual(erwartet, wert)

    def test_hauptfaden_antwortet_nie(self) -> None:
        gui = _gui()

        def _weg():
            raise RuntimeError("main thread is not in main loop")

        gui.root = types.SimpleNamespace(after=lambda *_a: None, winfo_exists=_weg)
        for aufruf in (lambda: gui._ask_yesno_threadsafe("T", "F"),
                       lambda: gui._ask_directory_threadsafe("T"),
                       lambda: gui._im_hauptfaden(lambda: "ja")):
            with self.subTest(aufruf=aufruf):
                fertig, _wert, fehler = _im_faden(aufruf, grenze=5.0)
                self.assertTrue(fertig, "Der Faden wartet fuer immer auf eine Antwort.")
                self.assertIsNone(fehler)


# ---------------------------------------------------------------- H3-11

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SpielHolenPfadTests(unittest.TestCase):
    """H3-11: Gemessen wird der Ordner, der gewaehlt ist.

    Im Fenster "Spiel holen" liefen Markierung und Pfadzeile auseinander.
    Seit dem 25.09.2026 holt die Bibliothek die Ordner; eine Pfadzeile gibt
    es dort nicht mehr, der Pfad kommt aus dem gewaehlten Eintrag. Geprueft
    wird deshalb der ganze Weg vom Herunterladen bis zur Vermessung.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def setUp(self) -> None:
        import gc
        gc.collect()

    def tearDown(self) -> None:
        import gc
        gc.collect()

    def _ersetzen(self, ziel, name: str, wert) -> None:
        flicken = mock.patch.object(ziel, name, wert)
        flicken.start()
        self.addCleanup(flicken.stop)

    def test_groesse_des_gewaehlten_ordners(self) -> None:
        ziel = _ordner(self, "r11_ziel_")
        self._ersetzen(self.app, "_ps5_ip", lambda default="": "127.0.0.1")
        self._ersetzen(self.app, "_ps5_ftp_port", lambda: 2121)
        self._ersetzen(self.app, "_konsole_ftp_bereit", lambda _ip, _melden: True)
        gemessen: list = []

        def _schaetzen(_ip, pfad, _port, **_k):
            gemessen.append(pfad)
            return 3, 3 * GB

        eintrag = {"kind": "folder", "path": "/mnt/usb0/PPSA01234-app", "size": 0}
        vorher = set(_WURZEL.winfo_children())

        def _zu() -> bool:
            return not [w for w in _WURZEL.winfo_children() if w not in vorher]

        # Nein auf die Frage nach dem Holen: Es wird nur vermessen.
        with mock.patch.object(APP.filedialog, "askdirectory", return_value=str(ziel)), \
                mock.patch.object(APP.konsole_ftp, "groesse_schaetzen", _schaetzen), \
                mock.patch.object(APP.messagebox, "askyesno", return_value=False) as frage:
            self.app._bibliothek_herunterladen(_WURZEL, eintrag)
            self.assertTrue(_schleife_bis(lambda: bool(gemessen) and frage.called and _zu()),
                            "Das Uebertragungsfenster schloss nicht.")
        self.assertEqual(["/mnt/usb0/PPSA01234-app"], gemessen)
        self.assertIn(os.path.join(str(ziel), "PPSA01234-app"), frage.call_args.args[1],
                      "Geholt wuerde in einen anderen Ordner als gefragt.")


# ---------------------------------------------------------------- Texte

class TexteTests(unittest.TestCase):
    def test_zweisprachig(self) -> None:
        for schluessel, platzhalter in (
                ("backport.log_backup_complete", ("{path}",)),
                ("backport.error_message", ("{error}", "{rest}")),
                ("preflight.temp_estimated_need", ("{size}", "{need}"))):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel].get(sprache, "")
                    self.assertTrue(text.strip())
                    for stelle in platzhalter:
                        self.assertIn(stelle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
