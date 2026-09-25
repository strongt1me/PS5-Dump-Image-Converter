# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 9 (24.09.2026): Datenverlust.

* **H5-9** - Meta-Zwischenspeicher: Dateiname aus der ungeprueften Title-ID;
  eine alte .json ausserhalb des Caches wurde geloescht.
* **H3-10** - Zurueckspielen: ein gleichnamiger Ordner auf der Konsole wurde
  ohne Rueckfrage Datei fuer Datei ueberschrieben.
* **H12-7** - AMPR-Hochladen: das Ziel wurde vor dem Umbenennen geloescht.
* **H10-6** - Autoloader: STOR direkt auf den endgueltigen Namen.
* **H10-7** - Autoloader: die Antwort der Konsole ersetzte, was waehrenddessen
  getippt wurde.
* **U1-6** - PKG zusammenfuehren: ein vorhandenes -merged.pkg wurde ohne
  Rueckfrage ersetzt.
* **H2-6** - Aufraeumen meldete "geloescht", obwohl der Ordner stehen blieb.
* **H2-7** - runtime_checkpoint.json ohne Schloss und nicht atomar.
* **U1-2/U1-3** - param.json-Reparatur: umwandelbare Werte wurden Vorgaben,
  eine ungueltige titleId verdarb die gueltige contentId.
"""
from __future__ import annotations

import ast
import ftplib
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde9")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_ftp as kf           # noqa: E402
from ps5_validator.utils import param_check as pc           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

from test_konsole_stufe3 import _FtpStube                   # noqa: E402
from test_param_check import _gueltiges_dokument            # noqa: E402


_BAUM: list = []


def _methode(name: str) -> ast.FunctionDef:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return next(k for k in ast.walk(_BAUM[0])
                if isinstance(k, ast.FunctionDef) and k.name == name)


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


def _schleife_bis(bedingung, grenze: float = 15.0) -> bool:
    """Laesst eine echte Ereignisschleife laufen, bis ``bedingung`` gilt.

    ``update()`` genuegt nicht: Tk nimmt Aufrufe aus einem Faden nur an,
    wenn der Hauptfaden in ``mainloop`` steht (siehe test_durchsicht_runde8).
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


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _knopf(fenster, text: str):
    for widget in _alle(fenster):
        try:
            if str(widget.cget("text")) == text:
                return widget
        except tk.TclError:
            continue
    raise AssertionError("Knopf %r fehlt" % text)


def _neues_fenster(aufruf):
    vorher = set(_WURZEL.winfo_children())
    aufruf()
    _WURZEL.update()
    neu = [w for w in _WURZEL.winfo_children()
           if w not in vorher and isinstance(w, tk.Toplevel)]
    if not neu:
        raise AssertionError("Es wurde kein Fenster geoeffnet")
    return neu[-1]


# ---------------------------------------------------------------- H5-9

class MetaCacheTests(unittest.TestCase):
    """H5-9: Die Title-ID bestimmt den Dateinamen - nie den Ordner."""

    INHALT = '{"wichtig": true}'

    def setUp(self) -> None:
        self.basis = _ordner(self, "r9_meta_")
        self.cache = self.basis / "cache"
        self.cache.mkdir()
        # Gross geschrieben wie der alte Dateiname (title_id.upper()), damit
        # der Fall auch auf Dateisystemen greift, die Schreibung unterscheiden.
        self.opfer = self.basis / "OPFER.json"
        self.opfer.write_text(self.INHALT, encoding="utf-8")
        alt = time.time() - 40 * 86400
        os.utime(self.opfer, (alt, alt))
        self.gui = _gui()
        self.gui._get_meta_cache_dir = lambda: str(self.cache)

    def test_laden_loescht_nichts_ausserhalb(self) -> None:
        for kennung in ("../OPFER", str(self.basis / "OPFER")):
            with self.subTest(kennung=kennung):
                self.assertIsNone(self.gui._load_meta_cache(kennung))
                self.assertTrue(self.opfer.exists(),
                                "Eine .json ausserhalb des Caches wurde geloescht.")

    def test_speichern_schreibt_nichts_ausserhalb(self) -> None:
        self.gui._save_meta_cache("../OPFER", {"title": "X"})
        self.assertEqual(self.INHALT, self.opfer.read_text(encoding="utf-8"))
        self.assertEqual([], list(self.cache.iterdir()))

    def test_gueltige_kennung_wird_bereinigt_abgelegt(self) -> None:
        self.gui._save_meta_cache("ppsa-01234", {"title": "Spiel"})
        self.assertTrue((self.cache / "PPSA01234.json").is_file())
        self.assertEqual({"title": "Spiel"}, self.gui._load_meta_cache("PPSA01234"))


# ---------------------------------------------------------------- H12-7 / H10-6

ZIEL = "/data/ps5_autoloader/etaHEN.bin"


class _FtpSpeicher:
    """Ein FTP-Dienst im Speicher - mit den Eigenheiten, um die es geht.

    ``ersetzt``: Umbenennen ueberschreibt ein vorhandenes Ziel (ftpsrv,
    rename(2) unter FreeBSD). ``umbenennen_scheitert``: jedes Umbenennen der
    Zwischendatei wird abgewiesen. ``zuruecklegen_scheitert``: auch das
    Zuruecklegen der beiseitegelegten Datei. ``stor_bricht_ab``: die
    Verbindung reisst mitten im STOR ab.
    """

    def __init__(self, dateien=None, *, ersetzt: bool = True,
                 umbenennen_scheitert: bool = False,
                 zuruecklegen_scheitert: bool = False,
                 stor_bricht_ab: bool = False) -> None:
        self.dateien = dict(dateien or {})
        self.ersetzt = ersetzt
        self.umbenennen_scheitert = umbenennen_scheitert
        self.zuruecklegen_scheitert = zuruecklegen_scheitert
        self.stor_bricht_ab = stor_bricht_ab
        self.befehle: list = []

    def storbinary(self, befehl, strom, blocksize=8192, callback=None):
        pfad = befehl.split(" ", 1)[1]
        self.befehle.append(("STOR", pfad))
        daten = strom.read()
        if self.stor_bricht_ab:
            self.dateien[pfad] = daten[: len(daten) // 2]
            raise OSError("Verbindung abgerissen")
        self.dateien[pfad] = daten
        return "226 fertig"

    def rename(self, alt, neu):
        self.befehle.append(("RENAME", alt, neu))
        if alt not in self.dateien:
            raise ftplib.error_perm("550 %s: No such file" % alt)
        if self.umbenennen_scheitert and alt.endswith(kf.ZWISCHEN_ENDUNG):
            raise ftplib.error_perm("550 Umbenennen abgewiesen")
        if self.zuruecklegen_scheitert and alt.endswith(kf.BEISEITE_ENDUNG):
            raise ftplib.error_perm("550 Zuruecklegen abgewiesen")
        if neu in self.dateien and not self.ersetzt:
            raise ftplib.error_perm("550 %s: File exists" % neu)
        self.dateien[neu] = self.dateien.pop(alt)
        return "250 umbenannt"

    def delete(self, pfad):
        self.befehle.append(("DELE", pfad))
        if pfad not in self.dateien:
            raise ftplib.error_perm("550 %s: No such file" % pfad)
        del self.dateien[pfad]
        return "250 geloescht"


class AblegenTests(unittest.TestCase):
    """konsole_ftp.datei_ablegen: nie halb, und nie gar nicht."""

    def test_ftpsrv_ersetzt_beim_umbenennen(self) -> None:
        ftp = _FtpSpeicher({ZIEL: b"ALT"})
        kf.datei_ablegen(ftp, io.BytesIO(b"NEU"), ZIEL)
        self.assertEqual({ZIEL: b"NEU"}, ftp.dateien)
        self.assertNotIn(("DELE", ZIEL), ftp.befehle,
                         "Das Ziel wurde vor dem Umbenennen geloescht.")

    def test_server_ohne_ersetzen_bekommt_die_neue_datei(self) -> None:
        ftp = _FtpSpeicher({ZIEL: b"ALT"}, ersetzt=False)
        kf.datei_ablegen(ftp, io.BytesIO(b"NEU"), ZIEL)
        self.assertEqual({ZIEL: b"NEU"}, ftp.dateien)

    def test_abgewiesenes_umbenennen_laesst_die_alte_datei(self) -> None:
        for ersetzt in (True, False):
            with self.subTest(ersetzt=ersetzt):
                ftp = _FtpSpeicher({ZIEL: b"ALT"}, ersetzt=ersetzt,
                                   umbenennen_scheitert=True)
                with self.assertRaises(kf.FtpFehler):
                    kf.datei_ablegen(ftp, io.BytesIO(b"NEU"), ZIEL)
                self.assertEqual({ZIEL: b"ALT"}, ftp.dateien)

    def test_abriss_im_stor_laesst_die_alte_datei(self) -> None:
        ftp = _FtpSpeicher({ZIEL: b"ALTE-FASSUNG"}, stor_bricht_ab=True)
        with self.assertRaises(kf.FtpFehler):
            kf.datei_ablegen(ftp, io.BytesIO(b"NEUE-FASSUNG"), ZIEL)
        self.assertEqual({ZIEL: b"ALTE-FASSUNG"}, ftp.dateien)

    def test_scheitert_auch_das_zuruecklegen_bleibt_beides(self) -> None:
        ftp = _FtpSpeicher({ZIEL: b"ALT"}, ersetzt=False, umbenennen_scheitert=True,
                           zuruecklegen_scheitert=True)
        with self.assertRaises(kf.ErsetzenUnvollstaendig) as fehler:
            kf.datei_ablegen(ftp, io.BytesIO(b"NEU"), ZIEL)
        self.assertEqual(b"ALT", ftp.dateien[ZIEL + kf.BEISEITE_ENDUNG])
        self.assertEqual(b"NEU", ftp.dateien[ZIEL + kf.ZWISCHEN_ENDUNG])
        self.assertIn(ZIEL + kf.BEISEITE_ENDUNG, str(fehler.exception))


class AmprHochladenTests(unittest.TestCase):
    """H12-7: Die Bibliothek bleibt, wenn das Umbenennen scheitert."""

    ORDNER = "/mnt/sandbox/PPSA01234_000/app0/fakelib"

    def _hochladen(self, ftp, inhalt: bytes) -> bool:
        gui = _gui()
        gui._ampr_ftp_ensure_dir = lambda _ftp, _ordner: None
        gui._warnen_wenn_nicht_ausfuehrbar = lambda _ftp, _pfad: True
        datei = _ordner(self, "r9_lib_") / "libSceAmpr.sprx"
        datei.write_bytes(inhalt)
        return gui._ampr_ftp_upload_file(ftp, self.ORDNER, str(datei))

    def test_abgewiesenes_umbenennen_laesst_die_bibliothek(self) -> None:
        ziel = self.ORDNER + "/libSceAmpr.sprx"
        ftp = _FtpSpeicher({ziel: b"ALT"}, umbenennen_scheitert=True)
        self.assertFalse(self._hochladen(ftp, b"NEU"))
        self.assertEqual({ziel: b"ALT"}, ftp.dateien,
                         "Im fakelib-Ordner fehlt danach die Bibliothek.")

    def test_kein_loeschen_vor_dem_umbenennen(self) -> None:
        ziel = self.ORDNER + "/libSceAmpr.sprx"
        ftp = _FtpSpeicher({ziel: b"ALT"})
        self.assertTrue(self._hochladen(ftp, b"NEU"))
        self.assertEqual({ziel: b"NEU"}, ftp.dateien)
        self.assertNotIn(("DELE", ziel), ftp.befehle)


class AutoloaderAblageTests(unittest.TestCase):
    """H10-6: Im Autoloader-Fenster geht kein STOR direkt auf den Namen."""

    def test_alles_ueber_den_zwischennamen(self) -> None:
        fenster = _methode("_show_autoloader")
        direkt = [k.lineno for k in ast.walk(fenster)
                  if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "storbinary"]
        self.assertEqual([], direkt,
                         "Zeile(n) %s schreiben direkt auf den endgueltigen Namen." % direkt)
        ueber = [k for k in ast.walk(fenster)
                 if isinstance(k, ast.Call)
                 and getattr(k.func, "attr", "") == "datei_ablegen"]
        # autoload.txt schreiben, Payload hochladen, Schnappschuss zurueckspielen
        self.assertEqual(3, len(ueber))


# ---------------------------------------------------------------- H3-10

class VorhandenTests(unittest.TestCase):
    """konsole_ftp.vorhanden gegen einen echten kleinen FTP-Server."""

    def setUp(self) -> None:
        self.fern = _ordner(self, "r9_fern_")
        (self.fern / "mnt" / "usb0" / "PPSA01234-app").mkdir(parents=True)
        (self.fern / "mnt" / "usb0" / "notiz.txt").write_bytes(b"x")
        self.stube = _FtpStube(self.fern)
        self.addCleanup(self.stube.schliessen)

    def test_ordner_datei_und_fehlendes(self) -> None:
        port = self.stube.port
        self.assertTrue(kf.vorhanden("127.0.0.1", "/mnt/usb0/PPSA01234-app", port))
        self.assertTrue(kf.vorhanden("127.0.0.1", "/mnt/usb0/notiz.txt/", port))
        self.assertFalse(kf.vorhanden("127.0.0.1", "/mnt/usb0/PPSA99999-app", port))
        self.assertFalse(kf.vorhanden("127.0.0.1", "/mnt/usb9/PPSA01234-app", port))


class _FadenTest(unittest.TestCase):
    """Speicherbereinigung im Hauptfaden vor und nach jedem Test.

    Siehe test_durchsicht_runde8: Raeumt ein Faden Tk-Variablen aus dem
    Kreis-Muell ab, warnt Tk "main thread is not in main loop".
    """

    def setUp(self) -> None:
        import gc
        gc.collect()

    def tearDown(self) -> None:
        import gc
        gc.collect()


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class FensterTests(_FadenTest):
    """H3-10, H10-7, U1-6 - am wirklichen Programm."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def _ersetzen(self, ziel, name: str, wert) -> None:
        flicken = mock.patch.object(ziel, name, wert)
        flicken.start()
        self.addCleanup(flicken.stop)

    def _schliessen_nachher(self, fenster) -> None:
        def _zu() -> None:
            try:
                fenster.destroy()
            except tk.TclError:
                pass
            _WURZEL.update()
        self.addCleanup(_zu)

    # -- H3-10: Zurueckspielen ------------------------------------------

    def _zurueckspielen(self, antwort: bool, *, ziel_da: bool = True):
        """Ordner senden - seit dem 25.09.2026 ueber die Bibliothek.

        Das Fenster "Zurueckspielen" ist in ihr aufgegangen. Gefragt wird
        dort zweimal: erst "Jetzt senden?" mit Groesse und Dauer (hier immer
        Ja), dann - nur wenn der Ordner auf der Konsole schon liegt - ob er
        ueberschrieben werden darf. Gezaehlt wird nur diese zweite Frage.
        """
        fern = _ordner(self, "r9_fern_")
        lokal = _ordner(self, "r9_lokal_")
        if ziel_da:
            (fern / "mnt" / "usb0" / "PPSA01234-app").mkdir(parents=True)
            (fern / "mnt" / "usb0" / "PPSA01234-app" / "eboot.bin").write_bytes(b"ORIGINAL")
        else:
            (fern / "mnt" / "usb0").mkdir(parents=True)
        (lokal / "PPSA01234-app").mkdir()
        (lokal / "PPSA01234-app" / "eboot.bin").write_bytes(b"NEU")
        stube = _FtpStube(fern)
        self.addCleanup(stube.schliessen)
        self._ersetzen(self.app, "_ps5_ip", lambda default="": "127.0.0.1")
        self._ersetzen(self.app, "_ps5_ftp_port", lambda: stube.port)
        self._ersetzen(self.app, "_konsole_ftp_bereit", lambda _ip, _melden: True)

        ziel = "/mnt/usb0/PPSA01234-app"
        ueberschreiben = self.app._t("zurueck.ask_overwrite", ziel=ziel)
        gefragt: list = []

        def _frage(_titel, text, **_kwargs):
            if text == ueberschreiben:
                gefragt.append(text)
                return antwort
            return True

        vorher = set(_WURZEL.winfo_children())
        with mock.patch.object(APP.messagebox, "askyesno", _frage), \
                mock.patch.object(APP.messagebox, "showinfo"), \
                mock.patch.object(APP.messagebox, "showwarning"):
            self.app._bibliothek_ordner_uebertragen(
                _WURZEL, richtung="hoch", oertlich=str(lokal / "PPSA01234-app"),
                entfernt=ziel)
            for fenster in set(_WURZEL.winfo_children()) - vorher:
                self._schliessen_nachher(fenster)
            self.assertTrue(_schleife_bis(lambda: not any(
                t.name == "bibliothek-ordner" for t in threading.enumerate())),
                "Die Uebertragung wurde nicht fertig.")
            _WURZEL.update()
        ergebnis = (fern / "mnt" / "usb0" / "PPSA01234-app" / "eboot.bin")
        return gefragt, (ergebnis.read_bytes() if ergebnis.exists() else None)

    def test_zurueckspielen_fragt_vor_vorhandenem_ordner(self) -> None:
        gefragt, inhalt = self._zurueckspielen(False)
        self.assertEqual(1, len(gefragt), "Es wurde nicht gefragt.")
        self.assertEqual(b"ORIGINAL", inhalt,
                         "Der Ordner auf der Konsole wurde trotz Nein ueberschrieben.")

    def test_zurueckspielen_nach_ja(self) -> None:
        gefragt, inhalt = self._zurueckspielen(True)
        self.assertEqual(1, len(gefragt))
        self.assertEqual(b"NEU", inhalt)

    def test_zurueckspielen_ohne_vorhandenes_ziel_fragt_nicht(self) -> None:
        gefragt, inhalt = self._zurueckspielen(False, ziel_da=False)
        self.assertEqual([], gefragt)
        self.assertEqual(b"NEU", inhalt)

    # -- H10-7: Autoloader ----------------------------------------------

    ANTWORT = {"dateien": ["kstuff.elf"], "inhalt": "kstuff.elf\n",
               "alle": ["kstuff.elf"]}

    def _autoloader(self):
        auftraege: list = []
        self._ersetzen(self.app, "_ps5_ip", lambda default="": "")
        self._ersetzen(self.app, "_autoloader_auftrag",
                       lambda _win, _stand, _arbeit, fertig=None: auftraege.append(fertig))
        fenster = _neues_fenster(self.app._show_autoloader)
        self._schliessen_nachher(fenster)
        feld = next(w for w in _alle(fenster) if isinstance(w, tk.Text))
        holen = _knopf(fenster, self.app._t("autoloader.action_load"))
        return auftraege, feld, holen

    def test_getipptes_bleibt_beim_holen_stehen(self) -> None:
        auftraege, feld, holen = self._autoloader()
        holen.invoke()
        self.assertEqual(1, len(auftraege))
        # Waehrend die Konsole antwortet, wird getippt.
        feld.insert("1.0", "etaHEN.bin\n")
        auftraege[0](dict(self.ANTWORT))
        self.assertEqual("etaHEN.bin\n", feld.get("1.0", "end-1c"),
                         "Die Antwort der Konsole hat die Eingabe ersetzt.")

    def test_ohne_eingabe_kommt_die_fassung_der_konsole(self) -> None:
        auftraege, feld, holen = self._autoloader()
        holen.invoke()
        auftraege[0](dict(self.ANTWORT))
        self.assertEqual("kstuff.elf\n", feld.get("1.0", "end-1c"))

    # -- U1-6: PKG zusammenfuehren --------------------------------------

    def _zusammenfuehren(self, antwort: bool, *, vorhanden: bool):
        basis = _ordner(self, "r9_merge_")
        ziel = basis / "aus"
        ziel.mkdir()
        ergebnis = ziel / ("Spiel" + APP.MERGED_SUFFIX)
        if vorhanden:
            ergebnis.write_bytes(b"ALT")
        gerufen: list = []

        def _zusammen(_teile, _meta, ausgabe, **_k):
            gerufen.append(ausgabe)
            return types.SimpleNamespace(output_path=ausgabe, total_size=0,
                                         sha256="0" * 64)

        self._ersetzen(APP, "merge_split_set", _zusammen)
        self._ersetzen(APP.filedialog, "askdirectory", lambda **_k: str(ziel))
        satz = types.SimpleNamespace(base_name="Spiel", has_root=True,
                                     numbered=["a", "b"], meta=None,
                                     ordered_numbered=["a", "b"])
        fenster = _neues_fenster(
            lambda: self.app._render_pkg_merger_window(str(basis), [satz], []))
        self._schliessen_nachher(fenster)
        baum = next(w for w in _alle(fenster) if isinstance(w, ttk.Treeview))
        baum.selection_set("0")
        gefragt: list = []

        def _frage(*args, **_kwargs):
            gefragt.append(args)
            return antwort

        knopf = _knopf(fenster, self.app._t("pkg_merger.merge_selected_button"))
        with mock.patch.object(APP.messagebox, "askyesno", _frage):
            knopf.invoke()
            _schleife_bis(lambda: not any(f.name == "pkg-merger"
                                          for f in threading.enumerate()))
        return gefragt, gerufen, ergebnis

    def test_vorhandenes_ergebnis_wird_erst_erfragt(self) -> None:
        gefragt, gerufen, ergebnis = self._zusammenfuehren(False, vorhanden=True)
        self.assertEqual(1, len(gefragt), "Es wurde nicht gefragt.")
        self.assertEqual([], gerufen, "Trotz Nein wurde zusammengefuehrt.")
        self.assertEqual(b"ALT", ergebnis.read_bytes())

    def test_nach_ja_wird_zusammengefuehrt(self) -> None:
        gefragt, gerufen, ergebnis = self._zusammenfuehren(True, vorhanden=True)
        self.assertEqual(1, len(gefragt))
        self.assertEqual([str(ergebnis)], gerufen)

    def test_ohne_vorhandenes_ergebnis_keine_frage(self) -> None:
        gefragt, gerufen, ergebnis = self._zusammenfuehren(False, vorhanden=False)
        self.assertEqual([], gefragt)
        self.assertEqual([str(ergebnis)], gerufen)


# ---------------------------------------------------------------- H2-6

class AufraeumenTests(unittest.TestCase):
    """H2-6: "geloescht" nur, wenn der Ordner wirklich weg ist."""

    def setUp(self) -> None:
        basis = _ordner(self, "r9_aufr_")
        self.ordner = basis / "ps5conv_lauf"
        (self.ordner / "unter").mkdir(parents=True)
        (self.ordner / "unter" / "gross.bin").write_bytes(b"x" * 16)
        self.norm = os.path.abspath(str(self.ordner))
        gui = _gui()
        gui._t = lambda schluessel, **_werte: schluessel
        gui._exit_cleanup_lock = threading.RLock()
        gui._session_exit_cleanup_paths = {self.norm}
        gui._is_managed_temp_path = lambda _pfad: True
        self.gui = gui

    def test_gesperrter_ordner_bleibt_vorgemerkt(self) -> None:
        def _gesperrt(pfad, ignore_errors=True):
            if not ignore_errors:
                raise PermissionError(13, "Zugriff verweigert", pfad)
            return False

        with mock.patch.object(APP, "_rmtree_force", _gesperrt):
            self.gui._cleanup_checkpoint_artifacts({"tmp_dir": str(self.ordner)})
        self.assertIn(self.norm, self.gui._session_exit_cleanup_paths,
                      "Der Ordner fiel aus der Liste fuers Aufraeumen beim Beenden.")
        self.assertNotIn("log.auto.0000", self.gui.protokoll,
                         "Das Protokoll meldet einen Ordner als geloescht, der noch da ist.")
        self.assertIn("log.auto.0004", self.gui.protokoll)

    def test_geloeschter_ordner_wird_gemeldet_und_vergessen(self) -> None:
        self.gui._cleanup_checkpoint_artifacts({"tmp_dir": str(self.ordner)})
        self.assertFalse(self.ordner.exists())
        self.assertNotIn(self.norm, self.gui._session_exit_cleanup_paths)
        self.assertIn("log.auto.0000", self.gui.protokoll)


# ---------------------------------------------------------------- H2-7

class CheckpointTests(unittest.TestCase):
    """H2-7: runtime_checkpoint.json - Schloss und Zwischendatei."""

    def setUp(self) -> None:
        self.basis = _ordner(self, "r9_cp_")
        self.datei = self.basis / "runtime_checkpoint.json"
        self.gui = _gui()
        self.gui._checkpoint_file_path = lambda: str(self.datei)

    def _speichern(self, nummer: int) -> None:
        self.gui._save_runtime_checkpoint(
            "modus", "C:/quelle%d" % nummer, "C:/ziel", "stufe")

    def _da(self, nummer: int) -> bool:
        return self.gui._load_runtime_checkpoint(
            "modus", "C:/quelle%d" % nummer, "C:/ziel") is not None

    def _eigene(self, datei) -> bool:
        return str(getattr(datei, "name", "")).startswith(str(self.basis))

    def test_abgebrochenes_schreiben_laesst_die_datei_stehen(self) -> None:
        self._speichern(1)
        echt = json.dump

        def _halb(daten, datei, *args, **kwargs):
            if not self._eigene(datei):
                return echt(daten, datei, *args, **kwargs)
            datei.write('{"jobs": {')
            raise OSError(28, "Kein Platz auf dem Datentraeger")

        with mock.patch.object(APP.json, "dump", _halb):
            self._speichern(2)
        self.assertTrue(self._da(1),
                        "Ein abgebrochenes Schreiben hat den Checkpoint geleert.")
        self.assertEqual([], [p.name for p in self.basis.iterdir()
                              if p.name.endswith(".tmp")])

    def test_gleichzeitiges_schreiben_verliert_nichts(self) -> None:
        echt = json.load

        def _langsam(datei, *args, **kwargs):
            daten = echt(datei, *args, **kwargs)
            if self._eigene(datei):
                time.sleep(0.01)
            return daten

        fehler: list = []

        def _reihe(start: int) -> None:
            try:
                for nummer in range(start, start + 8):
                    self._speichern(nummer)
            except Exception as exc:  # noqa: BLE001
                fehler.append(exc)

        with mock.patch.object(APP.json, "load", _langsam):
            faeden = [threading.Thread(target=_reihe, args=(s,)) for s in (0, 100)]
            for faden in faeden:
                faden.start()
            for faden in faeden:
                faden.join(60)
        self.assertEqual([], fehler)
        fehlend = [n for n in list(range(8)) + list(range(100, 108)) if not self._da(n)]
        self.assertEqual([], fehlend, "Gleichzeitiges Schreiben hat Eintraege verloren.")

    def test_aufraeumen_haelt_das_schloss_nicht(self) -> None:
        """Ein rmtree ueber viele GB darf den Fortschrittstakt nicht aufhalten."""
        self._speichern(1)
        laeuft, weiter = threading.Event(), threading.Event()

        def _aufraeumen(_stand) -> None:
            laeuft.set()
            weiter.wait(20)

        self.gui._cleanup_checkpoint_artifacts = _aufraeumen
        faden = threading.Thread(target=self.gui._clear_runtime_checkpoint,
                                 args=("modus", "C:/quelle1", "C:/ziel"))
        faden.start()
        try:
            self.assertTrue(laeuft.wait(10))
            fertig = threading.Event()

            def _takt() -> None:
                self._speichern(2)
                fertig.set()

            threading.Thread(target=_takt, daemon=True).start()
            self.assertTrue(fertig.wait(5),
                            "Der Fortschrittstakt wartete auf das Aufraeumen.")
        finally:
            weiter.set()
            faden.join(20)
        self.assertFalse(self._da(1))
        self.assertTrue(self._da(2))


# ---------------------------------------------------------------- U1-2 / U1-3

class ParamReparaturTests(unittest.TestCase):
    """U1-2/U1-3: berichtigen, nicht verwerfen."""

    def test_ganzzahlen_werden_umgeschrieben(self) -> None:
        neu, _ = pc.repariere(_gueltiges_dokument(
            attribute="1073741824", applicationCategoryType="65536",
            contentBadgeType=2.0, attribute3="0x10"))
        self.assertEqual(1073741824, neu["attribute"])
        self.assertEqual(65536, neu["applicationCategoryType"])
        self.assertEqual(2, neu["contentBadgeType"])
        self.assertIs(int, type(neu["contentBadgeType"]))
        self.assertEqual(16, neu["attribute3"])

    def test_wahrheitswert_bleibt_die_vorgabe(self) -> None:
        neu, _ = pc.repariere(_gueltiges_dokument(attribute2=True))
        self.assertEqual(0, neu["attribute2"])

    def test_versionen_werden_umgeschrieben(self) -> None:
        neu, _ = pc.repariere(_gueltiges_dokument(
            contentVersion="1.005.000", masterVersion=1.05,
            originContentVersion=2, targetContentVersion="1.5.0"))
        self.assertEqual("01.005.000", neu["contentVersion"])
        self.assertEqual("01.05", neu["masterVersion"])
        self.assertEqual("02.000.000", neu["originContentVersion"])
        # Nicht eindeutig (005 oder 500?) - dann weiter die Vorgabe.
        self.assertEqual("01.000.000", neu["targetContentVersion"])

    def test_pfs_version_geht_weiter_vor(self) -> None:
        neu, _ = pc.repariere(_gueltiges_dokument(contentVersion="1.005.000"),
                              inhaltsversion="01.020.000")
        self.assertEqual("01.020.000", neu["contentVersion"])

    def test_hexwerte_werden_aufgefuellt(self) -> None:
        neu, _ = pc.repariere(_gueltiges_dokument(
            requiredSystemSoftwareVersion="0x114000000000000",
            sdkVersion=0x04508001))
        self.assertEqual("0x0114000000000000", neu["requiredSystemSoftwareVersion"])
        self.assertEqual("0x0000000004508001", neu["sdkVersion"])
        neu, _ = pc.repariere(_gueltiges_dokument(sdkVersion="keine Zahl"))
        self.assertEqual("0x0000000000000000", neu["sdkVersion"])

    def test_das_ergebnis_besteht_die_pruefung(self) -> None:
        neu, _ = pc.repariere(_gueltiges_dokument(
            attribute="1073741824", contentVersion="1.005.000", masterVersion="1.00",
            requiredSystemSoftwareVersion="0x114000000000000"))
        befund = pc.pruefe_daten(neu)
        self.assertTrue(befund.ok, befund.fehler)

    def test_ungueltige_title_id_verdirbt_keine_content_id(self) -> None:
        gueltig = "UP0001-PPSA12345_00-ABCDEFGH12345678"
        for kennung in ("ppsa12345", "PPSA1234", None):
            with self.subTest(titleId=kennung):
                doc = _gueltiges_dokument(contentId=gueltig)
                if kennung is None:
                    del doc["titleId"]
                else:
                    doc["titleId"] = kennung
                neu, _ = pc.repariere(doc)
                self.assertEqual(gueltig, neu["contentId"],
                                 "Die gueltige contentId wurde verdorben.")
                self.assertEqual("PPSA12345", neu["titleId"])
                befund = pc.pruefe_daten(neu)
                self.assertTrue(befund.ok, befund.fehler)


# ---------------------------------------------------------------- Texte

class TexteTests(unittest.TestCase):
    """Die neuen Rueckfragen gibt es zweisprachig, mit denselben Platzhaltern."""

    def test_zweisprachig_mit_platzhaltern(self) -> None:
        for schluessel, platzhalter in (
                ("zurueck.ask_overwrite", ("{ziel}",)),
                ("zurueck.log_kept", ("{ziel}",)),
                ("pkg_merger.ask_overwrite_many", ("{count}", "{namen}"))):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel].get(sprache, "")
                    self.assertTrue(text.strip())
                    for stelle in platzhalter:
                        self.assertIn(stelle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
