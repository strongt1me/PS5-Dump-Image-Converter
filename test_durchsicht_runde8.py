# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 8 (24.09.2026): Fensterfaden.

Arbeit ueber das Netz oder an grossen Dateien lief im Klick - das Fenster
stand still, bis sie fertig war:

* **H11-3** - WebKit: Portsuche, Verbindung, USB-Liste und Hochladen.
* **H12-1** - KLOG: Senden an den Payload-Loader.
* **H12-2** - KLOG: Ablage auf dem USB-Datentraeger der Konsole.
* **H12-4** - AMPR-Picker: Auflisten, Pruefen, Hochladen.
* **H9-1** - Bibliothek: Titelbild der Detailspalte (Container oeffnen).

Die Rueckfragen dieser Wege laufen jetzt ueber ``_im_hauptfaden``: Die
Arbeit bleibt im Faden, die Fenster im Hauptfaden.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde8")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


_BAUM: list = []


def _methode(name: str) -> ast.FunctionDef:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return next(k for k in ast.walk(_BAUM[0])
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _innere(aussen: str, innen: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_methode(aussen))
                if isinstance(k, ast.FunctionDef) and k.name == innen)


def _direkte_aufrufe(funktion: ast.FunctionDef) -> set[str]:
    """Aufrufe im Rumpf selbst - ohne verschachtelte Funktionen und Lambdas.

    Genau das laeuft im Klick; was in einer inneren Funktion oder einem
    Lambda steht, geht an einen Faden.
    """
    namen: set[str] = set()

    def _besuchen(knoten) -> None:
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(knoten, ast.Call):
            ziel = knoten.func
            namen.add(ziel.attr if isinstance(ziel, ast.Attribute)
                      else getattr(ziel, "id", ""))
        for kind in ast.iter_child_nodes(knoten):
            _besuchen(kind)

    for anweisung in funktion.body:
        _besuchen(anweisung)
    return namen


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.root = _WURZEL
    gui._set_status_fluechtig = lambda *_a, **_k: None
    return gui


def _schleife_bis(bedingung, grenze: float = 10.0) -> bool:
    """Laesst eine echte Ereignisschleife laufen, bis ``bedingung`` gilt.

    ``update()`` genuegt nicht: Tk nimmt Aufrufe aus einem Faden nur an,
    wenn der Hauptfaden in ``mainloop`` steht ("main thread is not in main
    loop") - dasselbe Muster wie ``_in_schleife`` in test_debuglauf_befunde.
    """
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(20, _takt)
    _WURZEL.mainloop()
    return bool(bedingung())


class _FadenTest(unittest.TestCase):
    """Speicherbereinigung im Hauptfaden vor und nach jedem Test.

    Liegen von frueheren Fenstern noch Tk-Variablen im Kreis-Muell, raeumt
    sonst womoeglich einer der Faeden hier sie ab - und Tk warnt "main thread
    is not in main loop" (siehe test_konsole_stufe4, _aufraeumen).
    """

    def setUp(self) -> None:
        import gc
        gc.collect()

    def tearDown(self) -> None:
        import gc
        gc.collect()


@unittest.skipUnless(_TK_DA, "ohne Anzeige keine Ereignisschleife")
class HauptfadenTests(_FadenTest):
    """``_im_hauptfaden``: Dialoge im Hauptfaden, auch aus einem Faden."""

    def test_aus_dem_faden_im_hauptfaden(self) -> None:
        gui = _gui()
        ergebnis: dict = {}

        def _arbeit() -> None:
            ergebnis["wo"] = gui._im_hauptfaden(
                lambda: threading.current_thread() is threading.main_thread())

        faden = threading.Thread(target=_arbeit, daemon=True)
        faden.start()
        self.assertTrue(_schleife_bis(lambda: not faden.is_alive()))
        self.assertIs(True, ergebnis.get("wo"))

    def test_fehler_kommen_beim_aufrufer_an(self) -> None:
        gui = _gui()
        ergebnis: dict = {}

        def _kaputt():
            raise ValueError("Dialog kaputt")

        def _arbeit() -> None:
            try:
                gui._im_hauptfaden(_kaputt)
            except ValueError as exc:
                ergebnis["fehler"] = str(exc)

        faden = threading.Thread(target=_arbeit, daemon=True)
        faden.start()
        self.assertTrue(_schleife_bis(lambda: not faden.is_alive()))
        self.assertEqual("Dialog kaputt", ergebnis.get("fehler"))

    def test_ein_geschlossenes_elternfenster_wird_ersetzt(self) -> None:
        gui = _gui()
        weg = tk.Toplevel(_WURZEL)
        weg.destroy()
        gesehen: dict = {}
        gui._im_hauptfaden(lambda parent=None: gesehen.update(parent=parent),
                           parent=weg)
        self.assertIs(_WURZEL, gesehen.get("parent"))


@unittest.skipUnless(_TK_DA, "ohne Anzeige keine Ereignisschleife")
class KlogImFadenTests(_FadenTest):
    """H12-1/H12-2: Senden und USB-Ablage laufen im Faden."""

    def _lage(self, basis: str, loader: bool) -> dict:
        elf = Path(basis, "klogsrv.elf")
        elf.write_bytes(b"\x7fELF")
        return {"ip": "10.0.0.5", "klog_port": 9081, "elf": str(elf), "loader": loader}

    def test_senden_im_faden_meldung_im_hauptfaden(self) -> None:
        gui = _gui()
        gesendet: list = []
        gemeldet: list = []

        def _senden(_ip, _pfad):
            gesendet.append(threading.current_thread() is threading.main_thread())
            return True, "12 KB"

        with tempfile.TemporaryDirectory(prefix="runde8_") as basis, \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: True), \
                mock.patch.object(APP.messagebox, "showinfo",
                                  lambda *a, **k: gemeldet.append(
                                      threading.current_thread() is threading.main_thread())):
            gui._send_payload_to_ps5 = _senden
            gui._klog_anbieten(self._lage(basis, loader=True))
            self.assertTrue(_schleife_bis(lambda: bool(gemeldet)))
        self.assertEqual([False], gesendet, "Gesendet wurde im Fensterfaden.")
        self.assertEqual([True], gemeldet)

    def test_usb_ablage_im_faden_fehler_im_hauptfaden(self) -> None:
        gui = _gui()
        verbunden: list = []
        gemeldet: list = []

        def _verbinden(*_a, **_k):
            verbunden.append(threading.current_thread() is threading.main_thread())
            raise OSError("Konsole aus")

        with tempfile.TemporaryDirectory(prefix="runde8_") as basis, \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: True), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda *a, **k: gemeldet.append(
                                      threading.current_thread() is threading.main_thread())):
            gui._ampr_ftp_connect = _verbinden
            gui._klog_anbieten(self._lage(basis, loader=False))
            self.assertTrue(_schleife_bis(lambda: bool(gemeldet)))
        self.assertEqual([False], verbunden, "Die Verbindung entstand im Klick.")
        self.assertEqual([True], gemeldet)


@unittest.skipUnless(_TK_DA, "ohne Anzeige keine Ereignisschleife")
class WebkitImFadenTests(_FadenTest):
    """H11-3: Der USB-Weg des WebKit-Installers laeuft im Faden."""

    def test_usb_weg_im_faden(self) -> None:
        gui = _gui()
        verbunden: list = []
        gemeldet: list = []

        def _verbinden(*_a, **_k):
            verbunden.append(threading.current_thread() is threading.main_thread())
            raise OSError("Konsole aus")

        with tempfile.TemporaryDirectory(prefix="runde8_") as basis, \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: True), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda *a, **k: gemeldet.append(
                                      threading.current_thread() is threading.main_thread())):
            elf = Path(basis, "installer.elf")
            elf.write_bytes(b"\x7fELF")
            gui._webkit_installer_pfad = lambda: str(elf)
            gui._ps5_ip = lambda *_a: "10.0.0.5"
            gui._ps5_port_open = lambda *_a, **_k: False
            gui._ampr_ftp_connect = _verbinden
            gui._webkit_installer_senden()
            self.assertTrue(_schleife_bis(lambda: bool(gemeldet)))
        self.assertEqual([False], verbunden, "Die Verbindung entstand im Klick.")
        self.assertEqual([True], gemeldet)
        self.assertTrue(any("installer" in zeile.lower() or "usb" in zeile.lower()
                            or "Konsole aus" in zeile for zeile in gui.protokoll))

    def test_weiter_ruft_den_usb_weg_nicht_direkt(self) -> None:
        direkt = _direkte_aufrufe(_innere("_webkit_installer_senden", "_weiter"))
        self.assertNotIn("_webkit_auf_usb_ablegen", direkt)
        faden = ast.unparse(_innere("_webkit_installer_senden", "_usb_im_faden"))
        self.assertIn("threading.Thread(target=self._webkit_auf_usb_ablegen", faden)


class PickerImFadenTests(unittest.TestCase):
    """H12-4: Im Klick keine FTP-Arbeit mehr."""

    FTP_ARBEIT = {"_ampr_ftp_browse", "_ampr_ftp_validate_app0",
                  "_ampr_ftp_apply_set", "_ampr_ftp_upload_file"}

    def test_keine_ftp_arbeit_im_klick(self) -> None:
        for name in ("_render", "_validate", "_swap_set", "_swap_single"):
            with self.subTest(aktion=name):
                direkt = _direkte_aufrufe(_innere("_show_ampr_ftp_picker", name))
                self.assertFalse(direkt & self.FTP_ARBEIT,
                                 "%s arbeitet im Klick: %s" % (name, direkt & self.FTP_ARBEIT))
                self.assertIn("_im_faden", direkt)

    def test_immer_nur_eine_aktion(self) -> None:
        text = ast.unparse(_innere("_show_ampr_ftp_picker", "_im_faden"))
        self.assertIn("if state.get('beschaeftigt'):", text)
        verbinden = ast.unparse(_innere("_show_ampr_ftp_picker", "_connect"))
        self.assertIn("state.get('beschaeftigt')", verbinden)


class BibliothekCoverTests(unittest.TestCase):
    """H9-1: Das Titelbild der Detailspalte kommt aus dem Faden."""

    def test_der_klick_oeffnet_keinen_container(self) -> None:
        direkt = _direkte_aufrufe(_innere("_render_library_window", "_details_zeigen"))
        self.assertNotIn("_bibliothek_cover_datei", direkt)
        self.assertIn("Thread", direkt)

    def test_ein_spaetes_bild_gehoert_nur_zum_gewaehlten_eintrag(self) -> None:
        text = ast.unparse(_innere("_render_library_window", "_cover_setzen"))
        self.assertIn("if ansicht.get('cover_fuer') != pfad:", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
