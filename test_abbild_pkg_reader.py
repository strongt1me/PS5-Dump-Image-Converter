# -*- coding: utf-8 -*-
"""Waechter fuer "PS4 & PS5 PKG lesen" (``_show_pkg_reader``).

Der Reader zeigt den aeusseren Container einer ``.pkg`` ueber
``prosperopkg.paket_lesen`` an. Bis zum 02.10.2026 stand hier auch der
Waechter fuer "Abbild -> PKG" bzw. "PKG bauen" - das Bauen ist seitdem
ausgebaut (Nutzerentscheid: die Pakete starteten auf der Konsole nicht,
CE-100096-6). Was davon bleibt, bewacht ``test_werkzeugmenue.py``.

Die Wege sind an echten Paketen geprueft; hier stehen die
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

    def test_fehlendes_werkzeug_wird_mit_eigenem_text_gemeldet(self):
        """Der Text gehoerte bis 02.10.2026 zu "PKG bauen" (``pkgbau.``)."""
        fenster = _methode(self.quelle, "_show_pkg_reader")
        self.assertIn('self._t("pkgreader.missing_tool"', fenster)
        from ps5_validator.utils.i18n import STRINGS
        self.assertIn("{ordner}", STRINGS["pkgreader.missing_tool"]["de"])
        self.assertIn("{ordner}", STRINGS["pkgreader.missing_tool"]["en"])

    def test_pkg_entpacken_erklaert_update_pakete(self):
        """Die Weiche in "PS4 PKG -> Dump Ordner" faengt das Delta vor "keine PKG" ab."""
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
    """Arbeitsfaeden duerfen keine Tk-Variablen lesen (sonst "main thread is
    not in main loop", Absturz mit leerem Protokoll).
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = open(HAUPT, encoding="utf-8", errors="replace").read()
        cls.temp = _methode(cls.quelle, "_get_runtime_temp_dir")

    def test_temp_dir_liest_tk_nur_im_hauptfaden(self):
        # Der Tk-Zugriff auf self.temp_path ist an den Hauptfaden gebunden.
        self.assertIn("threading.current_thread() is threading.main_thread()",
                      self.temp,
                      "_get_runtime_temp_dir liest self.temp_path ungeschuetzt "
                      "(Absturz aus dem Arbeitsfaden)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
