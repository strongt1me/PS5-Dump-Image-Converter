# -*- coding: utf-8 -*-
"""Tests gegen ungefragte Verbindungen nach draussen.

Bis v1.8.73 fragte das Programm von selbst bei store.playstation.com,
prosperopatches.com und orbispatches.com nach, sobald in einem Backup Titel,
Publisher oder Kategorie fehlten. Es gab weder eine Rueckfrage noch einen
Schalter. Unter Windows faellt das nicht auf, weil dort nichts nachfragt; auf
dem Mac meldet die Firewall jede dieser Verbindungen.

Am 21.08.2026 nachgestellt und gemessen - ohne Schalter vier Verbindungen
allein fuer einen Titel:

    https://store.playstation.com/store/api/chihiro/.../DE/de/19/CUSA03877
    https://store.playstation.com/store/api/chihiro/.../US/en/19/CUSA03877
    https://store.playstation.com/store/api/chihiro/.../GB/en/19/CUSA03877
    https://orbispatches.com/CUSA03877

Dabei geht die Title-ID nach draussen, also die Information, welches Spiel
gerade verarbeitet wird.
"""
import io
import os
import socket
import sys
import unittest
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    tk = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class QuelltextTests(unittest.TestCase):
    """Was sich ohne Anzeige pruefen laesst."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            cls.quelltext = datei.read()

    def _methode(self, name: str) -> str:
        anfang = self.quelltext.index("    def %s(self" % name)
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        return self.quelltext[anfang:weiter]

    def test_jede_netzstelle_fragt_den_schalter(self):
        """Drei Methoden gehen ins Netz - alle drei muessen gesperrt sein."""
        for name in ("_resolve_title_id_from_store_search",
                     "_resolve_title_id_from_patch_search",
                     "_fetch_psstore_meta",
                     "_fetch_patch_page_meta",
                     "_fetch_patches_async",
                     "_download_cover_online"):
            with self.subTest(methode=name):
                self.assertIn("_metadaten_online_erlaubt()", self._methode(name),
                              "%s geht ohne Schalter ins Netz." % name)

    def test_der_schalter_steht_vor_dem_ersten_aufruf(self):
        """Die Sperre muss greifen, bevor irgendetwas geholt wird."""
        for name in ("_fetch_psstore_meta", "_fetch_patch_page_meta"):
            rumpf = self._methode(name)
            with self.subTest(methode=name):
                self.assertLess(
                    rumpf.index("_metadaten_online_erlaubt()"),
                    rumpf.index("urlopen") if "urlopen" in rumpf else len(rumpf),
                    "%s holt etwas, bevor der Schalter gefragt wird." % name)

    def test_auch_der_umweg_ueber_die_suchmaschine_ist_gesperrt(self):
        """_resolve_title_id_from_patch_search fragt bei duckduckgo.com an.

        Dorthin geht nicht die Title-ID, sondern der Klartext-Titel des
        Spiels - noch einmal aussagekraeftiger.
        """
        rumpf = self._methode("_resolve_title_id_from_patch_search")
        self.assertIn("duckduckgo.com", rumpf)
        self.assertLess(rumpf.index("_metadaten_online_erlaubt()"),
                        rumpf.index("duckduckgo.com"))

    def test_der_zwischenspeicher_bleibt_erlaubt(self):
        """Was lokal liegt, kostet keine Verbindung und darf gelesen werden."""
        self.assertNotIn("_metadaten_online_erlaubt()",
                         self._methode("_load_meta_cache"))

    def test_der_knopf_haengt_an_einem_festen_bezug(self):
        """Nachtraegliches ``pack()`` haengt ans Ende - dort ist kein Platz.

        Gemessen 21.08.2026: Der Knopf war verwaltet (``winfo_manager`` gab
        "pack"), aber ``winfo_ismapped`` blieb False, weil der Container schon
        voll war. Erst ``before=`` setzt ihn an seine Stelle.
        """
        rumpf = self._methode("_nachschlag_knopf_pruefen")
        self.assertIn("before=anker", rumpf,
                      "Ohne festen Bezug bleibt der Knopf unsichtbar.")

    def test_der_einmalige_klick_hebt_die_sperre_nur_kurz_auf(self):
        rumpf = self._methode("_metadaten_online_erlaubt")
        self.assertIn("_meta_nachschlag_einmalig", rumpf)
        fertig = self._methode("_nachschlag_fertig")
        self.assertIn("self._meta_nachschlag_einmalig = False", fertig,
                      "Die Sperre wird nach dem Nachschlag nicht wieder "
                      "geschlossen.")

    def test_der_arbeitsfaden_ueberlebt_ein_geschlossenes_fenster(self):
        """``root.after`` aus einem Faden wirft, wenn die Schleife weg ist.

        Wird die Infobox waehrend des Nachschlags geschlossen, meldet Tk
        "main thread is not in main loop". Ohne Absicherung endet der Faden
        mit einem Stapelauszug im Protokoll.
        """
        rumpf = self._methode("_nachschlag_ausloesen")
        davor = rumpf[:rumpf.index("self.root.after(")]
        self.assertTrue(davor.rstrip().endswith("try:"),
                        "Der after-Aufruf steht ungeschuetzt im Faden.")

    def test_die_einstellung_ist_im_fenster_erreichbar(self):
        rumpf = self._methode("_show_settings_dialog")
        for schluessel in ("settings_dialog.metadata_section",
                           "settings_dialog.metadata_checkbox",
                           "settings_dialog.metadata_services"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, rumpf)
        self.assertIn("_METADATEN_ONLINE_SETTING", rumpf)

    def test_die_texte_nennen_die_dienste_beim_namen(self):
        from ps5_validator.utils import i18n
        for sprache in i18n.SUPPORTED_LANGUAGES:
            text = i18n.STRINGS["settings_dialog.metadata_services"][sprache]
            with self.subTest(sprache=sprache):
                for dienst in ("store.playstation.com", "prosperopatches.com",
                               "orbispatches.com"):
                    self.assertIn(dienst, text)

    def test_die_texte_sagen_was_hinausgeht(self):
        from ps5_validator.utils import i18n
        for schluessel in ("settings_dialog.metadata_section",
                           "settings_dialog.metadata_hint",
                           "settings_dialog.metadata_checkbox",
                           "settings_dialog.metadata_services"):
            eintrag = i18n.STRINGS.get(schluessel)
            self.assertIsNotNone(eintrag, "%s fehlt" % schluessel)
            for sprache in i18n.SUPPORTED_LANGUAGES:
                self.assertTrue(eintrag[sprache].strip())
        self.assertIn("Title-ID",
                      i18n.STRINGS["settings_dialog.metadata_hint"]["de"])
        self.assertIn("title ID",
                      i18n.STRINGS["settings_dialog.metadata_hint"]["en"])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class VerbindungsTests(unittest.TestCase):
    """Misst am laufenden Programm, ob wirklich nichts hinausgeht."""

    @classmethod
    def setUpClass(cls):
        cls._eigene_wurzel = tk._default_root is None
        cls.wurzel = tk._default_root or tk.Tk()
        cls.wurzel.withdraw()
        haupt = _lade_hauptprogramm()
        cls.haupt = haupt
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(haupt.messagebox, name, lambda *a, **k: None)
        cls.app = haupt.PS5ConverterGUI(cls.wurzel)

    @classmethod
    def tearDownClass(cls):
        if not cls._eigene_wurzel:
            return
        try:
            cls.wurzel.destroy()
        except Exception:
            pass

    def setUp(self):
        self.versuche = []
        self._echt_urlopen = urllib.request.urlopen
        self._echt_connect = socket.create_connection

        def _urlopen(url, *a, **k):
            ziel = url.full_url if hasattr(url, "full_url") else str(url)
            self.versuche.append(ziel)
            raise OSError("vom Test geblockt")

        def _connect(adresse, *a, **k):
            self.versuche.append("socket %s:%s" % tuple(adresse[:2]))
            raise OSError("vom Test geblockt")

        urllib.request.urlopen = _urlopen
        socket.create_connection = _connect
        self.haupt.urllib.request.urlopen = _urlopen

    def tearDown(self):
        urllib.request.urlopen = self._echt_urlopen
        socket.create_connection = self._echt_connect
        self.haupt.urllib.request.urlopen = self._echt_urlopen

    def test_vorgabe_ist_aus(self):
        """Ohne Zutun darf nichts hinausgehen."""
        self.assertFalse(self.app._load_setting(
            self.haupt.PS5ConverterGUI._METADATEN_ONLINE_SETTING, False))

    def test_ohne_schalter_keine_verbindung(self):
        """Der Fall, der die Firewall auf den Plan rief.

        Ein Backup ohne Publisher und Kategorie - typisch fuer ein aus PKG
        gebautes PS4-Abbild.
        """
        alt = self.app._metadaten_online_erlaubt
        self.app._metadaten_online_erlaubt = lambda: False
        try:
            self.app._enrich_meta_online(
                {"title": "Styx", "publisher": "–", "category": "–"},
                "CUSA03877")
        finally:
            self.app._metadaten_online_erlaubt = alt
        self.assertEqual(self.versuche, [],
                         "Trotz abgeschaltetem Nachschlag: %s" % self.versuche)

    def test_mit_schalter_geht_es_wieder(self):
        """Wer es einschaltet, soll die Angaben auch bekommen."""
        alt = self.app._metadaten_online_erlaubt
        self.app._metadaten_online_erlaubt = lambda: True
        try:
            self.app._enrich_meta_online(
                {"title": "Styx", "publisher": "–", "category": "–"},
                "CUSA03877")
        finally:
            self.app._metadaten_online_erlaubt = alt
        self.assertTrue(self.versuche,
                        "Eingeschaltet wurde trotzdem nichts abgefragt.")

    def test_vollstaendige_metadaten_fragen_nie(self):
        """Auch eingeschaltet wird nur nachgeschlagen, was fehlt."""
        alt = self.app._metadaten_online_erlaubt
        self.app._metadaten_online_erlaubt = lambda: True
        try:
            self.app._enrich_meta_online(
                {"title": "Styx: Shards of Darkness", "publisher": "Focus",
                 "category": "Game"}, "CUSA03877")
        finally:
            self.app._metadaten_online_erlaubt = alt
        self.assertEqual(self.versuche, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
