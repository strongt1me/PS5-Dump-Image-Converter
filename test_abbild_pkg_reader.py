# -*- coding: utf-8 -*-
"""Waechter fuer "Abbild -> PKG" (jedes Abbildformat) und den PKG-Reader.

Hintergrund (13.09.2026): Das Fenster "exFAT -> PKG" nahm nur ``.exfat``
an. Es heisst jetzt "Abbild -> PKG" und akzeptiert ``.exfat``, ``.ffpfsc``,
``.ffpfs`` und ``.ffpkg`` ueber die Format-Weiche ``_abbild_zu_dumpordner``.
Dazu kam der PKG-Reader (``_show_pkg_reader``), der den aeusseren Container
einer ``.pkg`` ueber ``prosperopkg.paket_lesen`` anzeigt.

Die Wege sind an echten Abbildern/Paketen geprueft; hier stehen die
Regressionswaechter.
"""
from __future__ import annotations

import importlib.util
import os
import re
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
HAUPT = os.path.join(HIER, "PS5ImageConverter_Pro_FINAL_revised.py")


def _methode(quelle: str, name: str) -> str:
    m = re.search(r"\n    def %s\(.*?(?=\n    def )" % re.escape(name), quelle, re.S)
    assert m, "Methode %s nicht gefunden" % name
    return m.group(0)


def _modul():
    """Laedt das Hauptmodul (ohne die GUI zu starten - __main__-Schutz)."""
    spec = importlib.util.spec_from_file_location("hauptprogramm_test", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


class AbbildWeicheBaurichtung(unittest.TestCase):
    """Das Baufenster nimmt jedes der vier Abbildformate an."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = open(HAUPT, encoding="utf-8", errors="replace").read()
        cls.fenster = _methode(cls.quelle, "_show_pkg_bauen")
        cls.weiche = _methode(cls.quelle, "_abbild_zu_dumpordner")

    def test_endungen_decken_alle_vier_formate(self):
        for endung in (".exfat", ".ffpfsc", ".ffpfs", ".ffpkg"):
            self.assertIn(
                '"%s"' % endung, self.quelle.split("_ABBILD_PKG_ENDUNGEN", 1)[1][:120],
                "_ABBILD_PKG_ENDUNGEN deckt %s nicht ab" % endung)

    def test_validierung_nutzt_endungsliste(self):
        # Nicht mehr fest auf .exfat pruefen, sondern die Vierer-Liste.
        self.assertIn("endswith(self._ABBILD_PKG_ENDUNGEN)", self.fenster,
                      "Quellpruefung haengt nicht an _ABBILD_PKG_ENDUNGEN")
        self.assertNotIn('not quelle.lower().endswith(".exfat")', self.fenster,
                         "Alte exfat-only-Pruefung noch da")

    def test_dialogfilter_bietet_alle_formate(self):
        # Der Datei-Dialog muss die vier Muster anbieten.
        self.assertIn("*.exfat *.ffpfsc *.ffpfs *.ffpkg", self.fenster,
                      "Der kombinierte Dateifilter fehlt im Quellen-Dialog")

    def test_fenster_ruft_die_weiche(self):
        self.assertIn("self._abbild_zu_dumpordner(", self.fenster,
                      "Das Baufenster ruft die Format-Weiche nicht auf")

    def test_weiche_verzweigt_nach_format(self):
        # exfat -> nativer Bildextraktor; pfs/ufs2 -> erprobter A4-Weg.
        self.assertIn("extract_exfat_image", self.weiche)
        self.assertIn("_extract_inner_image", self.weiche)
        self.assertIn("_entpacke_container_ebenen", self.weiche)


class PkgReaderWaechter(unittest.TestCase):
    """Der PKG-Reader ist eingehaengt, die Helfer stimmen, i18n ist komplett."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = open(HAUPT, encoding="utf-8", errors="replace").read()
        cls.modul = _modul()
        cls.gui = cls.modul.PS5ConverterGUI

    def test_menueeintrag_vorhanden(self):
        self.assertIn(('titlebar.pkg_reader', '_show_pkg_reader'),
                      self.gui._MORE_TOOLS_ENTRIES,
                      "PKG-Reader haengt nicht im WEITERE-TOOLS-Menue")
        self.assertTrue(callable(getattr(self.gui, "_show_pkg_reader", None)),
                        "_show_pkg_reader fehlt")

    def test_magic_nach_ascii(self):
        self.assertEqual(self.gui._pkg_magic_ascii("7F-43-4E-54"), ".CNT")
        self.assertEqual(self.gui._pkg_magic_ascii("7F-46-49-48"), ".FIH")
        self.assertEqual(self.gui._pkg_magic_ascii("XX-YY"), "")

    def test_content_id_zerlegen(self):
        title, code, key = self.gui._pkg_content_id_teile(
            "EP4908-CUSA19269_00-00000000SKULLYEU")
        self.assertEqual(title, "CUSA19269")
        self.assertEqual(code, "EP")
        self.assertEqual(key, "pkgreader.region_europe")
        # US-Praefix
        _t, _c, k2 = self.gui._pkg_content_id_teile("UP0283-CUSA44880_00-X")
        self.assertEqual(k2, "pkgreader.region_america")
        # Leerwert faellt nicht um
        self.assertEqual(self.gui._pkg_content_id_teile(""),
                         ("", "", "pkgreader.region_unknown"))

    def _pkg_lesen_ausfuehren(self, inhalt: bytes):
        """Fuehrt ``_show_pkg_reader`` wirklich aus - Dialoge und Werkzeug attrappiert."""
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, "paket.pkg")
            with open(pfad, "wb") as fh:
                fh.write(inhalt)
            gui = self.gui.__new__(self.gui)
            gui._current_language = "de"
            gui.root = mock.MagicMock()
            gui._get_source_dialog_initial_dir = lambda: ""
            gui._remember_source_dialog_path = mock.MagicMock()
            gui._render_pkg_reader_window = mock.MagicMock()
            m = self.modul
            ergebnis = {"ist_pkg": True, "typ": "FullDebug", "kopf": {}, "eintraege": []}
            with mock.patch.object(m.prosperopkg, "werkzeug_finden", return_value="prosperopkg.exe"), \
                    mock.patch.object(m.prosperopkg, "paket_lesen", return_value=ergebnis) as lesen, \
                    mock.patch.object(m.filedialog, "askopenfilename", return_value=pfad), \
                    mock.patch.object(m.messagebox, "showinfo") as info, \
                    mock.patch.object(m.messagebox, "showwarning") as warnung:
                gui._show_pkg_reader()
        return lesen, info, warnung, gui

    def test_update_paket_wird_erklaert_statt_abgewiesen(self):
        """Ein Delta (LIH) ist keine "fremde Datei" - es braucht sein Grundpaket.

        LibProsperoPkg kennt die Art nicht und meldete "keine PS5-PKG". Seit
        23.09.2026 erklaert das Fenster, was ein Update-Paket ist, und nennt
        den Fehlercode, mit dem die Konsole ein unpassendes abweist.
        """
        lesen, info, warnung, _gui = self._pkg_lesen_ausfuehren(b"\x7fLIH" + b"\0" * 60)
        lesen.assert_not_called()
        warnung.assert_not_called()
        self.assertEqual(info.call_count, 1)
        text = info.call_args[0][1]
        self.assertIn("CE-107891-6", text)
        self.assertIn("paket.pkg", text)

    def test_volles_paket_geht_den_gewohnten_weg(self):
        lesen, info, _warnung, gui = self._pkg_lesen_ausfuehren(b"\x7fFIH\x00\x00" + b"\0" * 60)
        lesen.assert_called_once()
        info.assert_not_called()
        gui._render_pkg_reader_window.assert_called_once()

    def test_pkg_entpacken_erklaert_update_pakete(self):
        """Die Weiche in "PKG entpacken" faengt das Delta vor "keine PKG" ab."""
        fenster = _methode(self.quelle, "_show_pkg_entpacken")
        delta = fenster.find('art == "ps5_delta"')
        fremd = fenster.find('art != "ps4"')
        self.assertGreaterEqual(delta, 0, "Zweig fuer Update-Pakete fehlt")
        self.assertGreaterEqual(fremd, 0, "Anker 'art != \"ps4\"' nicht gefunden")
        self.assertLess(delta, fremd, "Delta wuerde vorher als 'keine PKG' abgewiesen")
        self.assertIn("pkgentpacken.ps5_delta", fenster)

    def test_alle_pkgreader_schluessel_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        verwendet = set(re.findall(r"pkgreader\.[a-z_]+", self.quelle))
        verwendet.add("titlebar.pkg_reader")
        self.assertIn("pkgreader.window_title", verwendet)  # Scan greift
        for schluessel in sorted(verwendet):
            eintrag = STRINGS.get(schluessel)
            self.assertIsNotNone(eintrag, "i18n-Schluessel %s fehlt" % schluessel)
            self.assertTrue(eintrag.get("de") and eintrag.get("en"),
                            "de/en fuer %s unvollstaendig" % schluessel)


class FadensicherheitWaechter(unittest.TestCase):
    """Der Abbild->PKG-Lauf laeuft im Arbeitsfaden - dort duerfen keine
    Tk-Variablen gelesen werden (sonst "main thread is not in main loop",
    Absturz mit leerem Protokoll). Alle Tk-Werte werden im Hauptfaden
    abgegriffen; Balken/Log/Knoepfe laufen ueber einen Haupt-Takt.
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = open(HAUPT, encoding="utf-8", errors="replace").read()
        cls.fenster = _methode(cls.quelle, "_show_pkg_bauen")
        cls.temp = _methode(cls.quelle, "_get_runtime_temp_dir")

    def test_temp_dir_liest_tk_nur_im_hauptfaden(self):
        # Der Tk-Zugriff auf self.temp_path ist an den Hauptfaden gebunden.
        self.assertIn("threading.current_thread() is threading.main_thread()",
                      self.temp,
                      "_get_runtime_temp_dir liest self.temp_path ungeschuetzt "
                      "(Absturz aus dem Arbeitsfaden)")

    def test_bauen_nutzt_hauptfaden_werte(self):
        # Die Kaestchen werden im Hauptfaden gelesen und als einfache Werte
        # uebergeben - NICHT per .get() im bauen()-Aufruf (der laeuft im
        # Arbeitsfaden und wuerfe dort "main thread is not in main loop").
        self.assertIn("lizenzfrei = bool(lizenzfrei_var.get())", self.fenster,
                      "lizenzfrei wird nicht im Hauptfaden gelesen")
        self.assertIn("schnell = bool(schnell_var.get())", self.fenster,
                      "schnell wird nicht im Hauptfaden gelesen")
        self.assertIn("lizenzfrei=lizenzfrei", self.fenster,
                      "bauen() nutzt nicht den vorab gelesenen Wert")
        self.assertIn("schnell=schnell", self.fenster,
                      "bauen() nutzt nicht den vorab gelesenen Wert")
        self.assertNotIn("lizenzfrei=bool(lizenzfrei_var.get())", self.fenster,
                         "bauen() liest lizenzfrei_var im Arbeitsfaden")
        self.assertNotIn("schnell=bool(schnell_var.get())", self.fenster,
                         "bauen() liest schnell_var im Arbeitsfaden")

    def test_fortschritt_und_abbrechen_vorhanden(self):
        # Fortschritts-Takt, Abbrechen-Knopf und Puffer-Protokoll muessen da sein.
        self.assertIn("def _takt(", self.fenster, "Fortschritts-Takt fehlt")
        self.assertIn("exfatpkg.abort_button", self.fenster,
                      "Abbrechen-Knopf fehlt")
        self.assertIn("protokoll_puffer", self.fenster,
                      "Protokoll-Puffer (Haupt-Takt) fehlt - Log ginge verloren")
        self.assertIn("mode=\"indeterminate\"", self.fenster,
                      "Marquee fuer den Bau fehlt")

    def test_abbruch_i18n_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("exfatpkg.abort_button", "exfatpkg.status_aborting",
                           "exfatpkg.status_aborted"):
            eintrag = STRINGS.get(schluessel)
            self.assertIsNotNone(eintrag, "i18n %s fehlt" % schluessel)
            self.assertTrue(eintrag.get("de") and eintrag.get("en"),
                            "de/en fuer %s unvollstaendig" % schluessel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
