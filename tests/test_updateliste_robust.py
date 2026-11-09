# -*- coding: utf-8 -*-
"""Updatelisten und Ladefenster: langsame Seiten, ehrliche Anzeige, Lebenszeichen (gemeldet 08.11.2026).

Gemeldet: "Es werden nicht immer Updates angezeigt, obwohl ich weiss, dass es welche gibt." Gemessen an 50 Titeln der
eigenen Sammlung: Bei 9 kam von prosperopatches.com/orbispatches.com keine Liste, weil die Seiten beim ersten Abruf eines
Titels 4 bis 30 s brauchen (danach 0,2 s) und das Programm nach 5 s mit einem einzigen Versuch aufgab - die Anzeige
sagte dann "Keine Updates gefunden", als waere die Liste leer. Sony kannte in allen 9 Faellen das Update.

Ausserdem: Das Ladefenster zeigte vor dem ersten Byte nichts, was sich aenderte ("man sieht nicht, ob etwas gestartet ist").
"""
from __future__ import annotations

import json
import sys
import threading
import time
import tkinter as tk
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("updateliste_robust")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ps5_updates                 # noqa: E402

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                           # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

TID = "PPSA00001"
SEITE = ('<html><head><title>%s: Testspiel</title></head><body>'
         '<div id="dynpatch" data-titleid="%s" data-key="0123456789abcdef0123456789abcdef01234567"></div></body></html>' % (TID, TID))
STARTSEITE = "<html><head><title>PROSPEROPatches.com - PlayStation 5 Game Tracker</title></head><body>Recently Updated</body></html>"


def _api(titleid: str = TID, patches: int = 1) -> bytes:
    return json.dumps({"success": True, "titleid": titleid, "patches": [
        {"content_ver": "01.00%d.000" % (i + 1), "filesize": "1.0 GB", "required_firmware": "09.00.00.00",
         "import_date": "2026-11-08 10:00:00", "is_latest": i == patches - 1} for i in range(patches)]}).encode()


class _Antwort:
    def __init__(self, daten: bytes) -> None:
        self.daten = daten

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self, _n=-1):
        return self.daten


def _folge(*schritte):
    """Ein ``urlopen``-Ersatz: je Aufruf der naechste Schritt (Bytes = Antwort, Ausnahme = wird geworfen)."""
    aufrufe: list = []
    liste = list(schritte)

    def urlopen(anfrage, timeout=None):
        aufrufe.append(timeout)
        schritt = liste.pop(0)
        if isinstance(schritt, BaseException):
            raise schritt
        return _Antwort(schritt)

    urlopen.aufrufe = aufrufe
    return urlopen


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._hauptfaden_planen = lambda f, *a, **k: f(*a)
    return gui


class PatchseiteLesenTests(unittest.TestCase):
    ZEITEN = (0.05, 0.05)

    def _lesen(self, *schritte, zeiten=None):
        urlopen = _folge(*schritte)
        with mock.patch.object(APP.urllib.request, "urlopen", urlopen):
            ergebnis = _gui()._patchseite_lesen("https://prosperopatches.com", "PS5", TID, zeiten=zeiten or self.ZEITEN)
        return ergebnis, urlopen.aufrufe

    def test_erster_abruf_zu_langsam_zweiter_versuch_mit_mehr_geduld(self) -> None:
        (zeilen, gescheitert), aufrufe = self._lesen(
            TimeoutError("The read operation timed out"), SEITE.encode(), _api(), zeiten=(15.0, 40.0))
        self.assertFalse(gescheitert)
        self.assertEqual(1, len(zeilen))
        self.assertEqual([15.0, 40.0, 15.0], aufrufe, "Seite: zweimal (15 s, 40 s), danach die Liste mit 15 s")

    def test_beide_versuche_zu_langsam_ist_ein_fehlschlag_und_keine_leere_liste(self) -> None:
        (zeilen, gescheitert), _ = self._lesen(TimeoutError("x"), TimeoutError("y"))
        self.assertEqual([], zeilen)
        self.assertTrue(gescheitert, "unbekannt, nicht 'keine Updates'")

    def test_server_fehler_5xx_wird_einmal_wiederholt(self) -> None:
        fehler = urllib.error.HTTPError("https://x", 503, "Service Unavailable", {}, None)
        (zeilen, gescheitert), _ = self._lesen(fehler, SEITE.encode(), _api(patches=3))
        self.assertFalse(gescheitert)
        self.assertEqual(3, len(zeilen))

    def test_seite_kennt_den_titel_nicht_ist_keine_liste_aber_kein_fehlschlag(self) -> None:
        """Unbekannte IDs beantwortet die Seite mit ihrer Startseite (HTTP 200, ohne die ID im Titel)."""
        (zeilen, gescheitert), _ = self._lesen(STARTSEITE.encode())
        self.assertEqual(([], False), (zeilen, gescheitert))

    def test_http_404_heisst_kein_eintrag(self) -> None:
        (zeilen, gescheitert), _ = self._lesen(urllib.error.HTTPError("https://x", 404, "Not Found", {}, None))
        self.assertEqual(([], False), (zeilen, gescheitert))

    def test_titel_da_aber_kein_schluessel_ist_ein_fehlschlag(self) -> None:
        """Steht die ID im Titel, fehlt aber der Schluessel, hat die Seite ihren Aufbau geaendert."""
        (zeilen, gescheitert), _ = self._lesen(("<title>%s: X</title><body>kaputt</body>" % TID).encode())
        self.assertEqual(([], True), (zeilen, gescheitert))

    def test_text_404_oder_not_here_im_inhalt_verwirft_die_liste_nicht_mehr(self) -> None:
        """Der fruehere Textvergleich auf '404' und 'not here' hielt eine Seite mit solchem Text fuer 'nicht gefunden'."""
        seite = SEITE.replace("<body>", "<body>PPSA00404 not here 404 ")
        (zeilen, gescheitert), _ = self._lesen(seite.encode(), _api())
        self.assertFalse(gescheitert)
        self.assertEqual(1, len(zeilen))

    def test_liste_eines_anderen_titels_wird_nicht_angezeigt(self) -> None:
        """Zwillings-IDs (PPSA01315/PPSA01316, beide Gran Turismo 7) teilen Fassungen und Groessen."""
        (zeilen, gescheitert), _ = self._lesen(SEITE.encode(), _api(titleid="PPSA00002"))
        self.assertEqual(([], True), (zeilen, gescheitert))

    def test_normalfall_liest_alle_felder(self) -> None:
        (zeilen, gescheitert), _ = self._lesen(SEITE.encode(), _api(patches=2))
        self.assertFalse(gescheitert)
        self.assertEqual(("PS5", "01.002.000", "1.0 GB", "09.00.00.00", "2026-11-08 10:00:00", True,
                          "https://prosperopatches.com/" + TID), zeilen[1])


class AnzeigeTests(unittest.TestCase):
    def _anzeige(self, ergebnisse, gescheitert):
        gui = _gui()
        gui._patch_tree = mock.MagicMock()
        gui._patch_tree.winfo_exists.return_value = True
        gui._patch_tree.get_children.return_value = []
        gui._patch_status_var = mock.Mock()
        gui._display_patches(ergebnisse, TID, elapsed_sec=42.0, final=True, source="Online", gescheitert=gescheitert)
        werte = [c.kwargs.get("values") or c.args[2] for c in gui._patch_tree.insert.call_args_list]
        return werte, gui._patch_status_var.set.call_args[0][0]

    def test_fehlschlag_wird_nicht_als_keine_updates_ausgegeben(self) -> None:
        werte, status = self._anzeige([], True)
        gui = _gui()
        self.assertEqual(gui._t("info_popup.update_failed_row"), werte[0][1])
        self.assertNotIn(gui._t("info_popup.no_updates_found"), [w[1] for w in werte])
        self.assertIn("fehlgeschlagen", status)

    def test_wirklich_keine_updates_bleibt_keine_updates(self) -> None:
        werte, status = self._anzeige([], False)
        gui = _gui()
        self.assertEqual(gui._t("info_popup.no_updates_found"), werte[0][1])
        self.assertNotIn("fehlgeschlagen", status)


class BibliothekTests(unittest.TestCase):
    def _gui_bibliothek(self):
        gui = _gui()
        gui._patch_cache = {}
        gui._patch_cache_seiten = {}
        return gui

    def test_ps4_nimmt_sonys_liste_mit_wenn_die_seite_nichts_liefert(self) -> None:
        """Gemessen: CUSA08519 und CUSA19269 kamen von der Drittseite leer, Sony kannte 01.32 bzw. 01.02."""
        gui = self._gui_bibliothek()
        fassung = ps5_updates.Fassung(inhalt="01.32", firmware="05.05", manifest_url="http://gs2.ww.prod.dl.playstation.net/x.json")
        with mock.patch.object(gui, "_patchseite_lesen", return_value=([], True)), \
                mock.patch.object(ps5_updates, "verxml_holen", return_value=[fassung]):
            ergebnisse, vollstaendig = gui._patchliste_holen("CUSA08519", online=True)
        self.assertEqual("01.32", gui._neueste_aus_patchliste(ergebnisse)[1])
        self.assertFalse(vollstaendig, "die Seite ist gescheitert: nicht als vollstaendig zwischenspeichern")
        self.assertNotIn("CUSA08519", gui._patch_cache_seiten)

    def test_ps4_beide_quellen_gut_ist_vollstaendig_und_wird_gemerkt(self) -> None:
        gui = self._gui_bibliothek()
        seite = [("PS4", "01.20", "1 GB", "05.05", "2026", True, "https://orbispatches.com/CUSA08519")]
        fassung = ps5_updates.Fassung(inhalt="01.20", firmware="05.05", manifest_url="http://gs2.ww.prod.dl.playstation.net/x.json")
        with mock.patch.object(gui, "_patchseite_lesen", return_value=(seite, False)), \
                mock.patch.object(ps5_updates, "verxml_holen", return_value=[fassung]):
            ergebnisse, vollstaendig = gui._patchliste_holen("CUSA08519", online=True)
        self.assertTrue(vollstaendig)
        self.assertIn("CUSA08519", gui._patch_cache_seiten)
        self.assertEqual("01.20", gui._neueste_aus_patchliste(ergebnisse)[1])

    def test_sony_ohne_liste_4xx_ist_kein_fehlschlag(self) -> None:
        gui = self._gui_bibliothek()
        with mock.patch.object(gui, "_patchseite_lesen", return_value=([], False)), \
                mock.patch.object(ps5_updates, "verxml_holen", side_effect=ps5_updates.UpdateFehler("ps5upd.http|404")):
            ergebnisse, vollstaendig = gui._patchliste_holen("CUSA00001", online=True)
        self.assertEqual(([], True), (ergebnisse, vollstaendig))

    def test_ps5_fragt_sony_in_der_bibliothek_nicht(self) -> None:
        gui = self._gui_bibliothek()
        with mock.patch.object(gui, "_patchseite_lesen", return_value=([], False)), \
                mock.patch.object(ps5_updates, "verxml_holen", side_effect=AssertionError("PS5 braucht eine versionFileUri")) as sony:
            gui._patchliste_holen("PPSA00001", online=True)
        sony.assert_not_called()


def _alle(w):
    for k in w.winfo_children():
        yield k
        yield from _alle(k)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class LadefensterLebenszeichenTests(unittest.TestCase):
    """Vor dem ersten Byte zeigt das Fenster, was geschieht und seit wann (vorher: ein stehender Satz)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _status(self, win) -> str:
        texte = []
        for w in _alle(win):
            if isinstance(w, tk.Label):
                try:
                    var = w.cget("textvariable")
                    texte.append(str(w.tk.globalgetvar(var)) if var else str(w.cget("text")))
                except tk.TclError:
                    pass
        return "\n".join(texte)

    def _pumpen(self, sekunden: float) -> None:
        ende = time.time() + sekunden
        while time.time() < ende:
            _WURZEL.update()
            time.sleep(0.02)

    def test_ps5_fenster_zeigt_vor_dem_manifest_die_laufzeit(self) -> None:
        app = self.app
        frei = threading.Event()

        def haengt(url, abbruch=None):
            frei.wait(10)
            raise ps5_updates.UpdateFehler("ps5upd.abgebrochen")

        info = {"name": "X", "version": "01.000.000", "dateiname": "x.pkg", "manifest_url": "https://x/m.json", "gesamt": 0}
        with mock.patch.object(ps5_updates, "manifest_holen", side_effect=haengt):
            app._sony_ladefenster(info, "x.pkg")
            win = app._sony_lauf["win"]
            try:
                self._pumpen(0.8)
                text = self._status(win)
                self.assertIn(app._t("ps5upd.status_start"), text)
                self.assertRegex(text, r"seit \d+:\d\d:\d\d", "kein Lebenszeichen mit der Laufzeit")
            finally:
                frei.set()
                self._pumpen(0.6)
                try:
                    win.destroy()
                except tk.TclError:
                    pass

    def test_ps4_fenster_sagt_verbinde_statt_verzeichnis_und_zaehlt_die_zeit(self) -> None:
        app = self.app
        frei = threading.Event()

        def haengt(url, ziel, fortschritt=None, abbruch=None, **_k):
            frei.wait(10)
            raise ps5_updates.UpdateFehler("ps5upd.abgebrochen")

        info = {"name": "Y", "version": "01.02", "dateiname": "y.pkg", "pkg_url": "http://gs2.ww.prod.dl.playstation.net/y.pkg"}
        with mock.patch.object(ps5_updates, "datei_laden", side_effect=haengt):
            app._ps4_ladefenster(info, "y.pkg")
            win = app._ps4_lauf["win"]
            try:
                self._pumpen(0.8)
                text = self._status(win)
                self.assertIn(app._t("ps5upd.status_verbinde_kurz"), text)
                self.assertNotIn(app._t("ps5upd.status_start"), text, "PS4 hat kein Verzeichnis zu laden")
                self.assertRegex(text, r"seit \d+:\d\d:\d\d")
            finally:
                frei.set()
                self._pumpen(0.6)
                try:
                    win.destroy()
                except tk.TclError:
                    pass

    def test_nach_dem_ersten_byte_steht_die_prozentzahl_mit_zwei_stellen_und_ruhe_wird_gemeldet(self) -> None:
        app = self.app
        frei = threading.Event()

        def langsam(url, ziel, fortschritt=None, abbruch=None, **_k):
            fortschritt(2 * 1024 * 1024, 100 * 1024 ** 3)           # 2 MiB von 100 GiB = 0,00 %
            frei.wait(10)
            raise ps5_updates.UpdateFehler("ps5upd.abgebrochen")

        info = {"name": "Z", "version": "01.03", "dateiname": "z.pkg", "pkg_url": "http://gs2.ww.prod.dl.playstation.net/z.pkg"}
        with mock.patch.object(ps5_updates, "datei_laden", side_effect=langsam):
            app._ps4_ladefenster(info, "z.pkg")
            win = app._ps4_lauf["win"]
            try:
                self._pumpen(0.8)
                text = self._status(win)
                self.assertIn("2.0 MB", text.replace(",", "."))
                self.assertRegex(text, r"\(0\.00 %\)", "unter 1 % zwei Nachkommastellen")
            finally:
                frei.set()
                self._pumpen(0.6)
                try:
                    win.destroy()
                except tk.TclError:
                    pass


if __name__ == "__main__":
    unittest.main()
