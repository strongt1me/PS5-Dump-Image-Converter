# -*- coding: utf-8 -*-
"""Die zweite Ansicht "KONSOLE" (Stufe 1, v1.9.42).

Ein Knopf oben in der Seitenleiste schaltet um: links andere Knoepfe, keine
Cover-Vorschau, kein "Spiel Info", kein "Was man sonst ev. noch braucht",
rechts eine leere Flaeche. Zurueck muss alles wieder so stehen wie vorher -
in derselben Reihenfolge, ohne dass Quelle oder Auftrag verloren gehen.

Geprueft am echten Programmfenster, nicht an einer Attrappe: Es geht um
pack/grid-Zustaende, und die gibt es nur dort.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import threading
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ZweiteAnsichtTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Der Ausgangszustand der Leiste, bevor irgendeine Pruefung umschaltet.
        # "vorher" in einer einzelnen Pruefung zu nehmen reicht nicht: Laeuft
        # eine andere zuerst und verbiegt die Leiste, gaelte das Verbogene als
        # Vorbild (so in der Gegenprobe vom 22.09.2026 geschehen).
        cls.grundzustand = cls._packangaben_von(cls.app)

    @staticmethod
    def _packangaben_von(app):
        angaben = []
        for w in app.sidebar.pack_slaves():
            info = {k: str(v) for k, v in w.pack_info().items() if k != "in"}
            angaben.append((str(w), info))
        return angaben

    def tearDown(self):
        # Jede Pruefung endet in der ersten Ansicht - andere Pruefstaende im
        # selben Prozess sollen sie so vorfinden.
        self.app._ansicht_setzen("umwandeln", speichern=False)
        self.app._vorschau_warteschlange = []

    def _packfolge(self):
        return [w for w in self.app.sidebar.pack_slaves()]

    def _packangaben(self):
        """Reihenfolge UND Packangaben - fill, pady, side ... gehoeren dazu."""
        return self._packangaben_von(self.app)

    def test_umschalten_tauscht_die_knoepfe(self):
        app = self.app
        vorher = self.grundzustand
        app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update_idletasks()
        gepackt = self._packfolge()
        for knopf, _modus in app.mode_buttons:
            self.assertNotIn(knopf, gepackt)
        for knopf, _schluessel in app._konsole_knoepfe:
            self.assertIn(knopf, gepackt)
        self.assertEqual(len(app._KONSOLE_KNOEPFE), len(app._konsole_knoepfe))
        # Kein Spiel-Info, kein "Was man sonst", keine Vorschau
        self.assertNotIn(app._sidebar_footer_frame, gepackt)
        self.assertNotIn(app._sidebar_preview_img_label, gepackt)
        # Der Umschalter selbst bleibt
        self.assertIn(app._ansicht_knopf, gepackt)
        # Rechts leer: die Inhaltsspalte ist ausgeblendet
        self.assertEqual("", app.content_scroll.winfo_manager())
        self.assertEqual("", app.content_scrollbar.winfo_manager())

        app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update_idletasks()
        self.assertEqual(vorher, self._packangaben(),
                         "Nach dem Zurueckschalten steht die Leiste anders als vorher.")
        self.assertEqual("grid", app.content_scroll.winfo_manager())

    def test_umschalter_nennt_sein_ziel(self):
        app = self.app
        self.assertEqual(app._t("ansicht.to_konsole"), app._ansicht_knopf.cget("text"))
        app._ansicht_setzen("konsole", speichern=False)
        self.assertEqual(app._t("ansicht.to_umwandeln"), app._ansicht_knopf.cget("text"))
        app._ansicht_umschalten()
        self.assertFalse(app._ansicht_ist_konsole())

    def test_quelle_ueberlebt_das_umschalten(self):
        app = self.app
        app.source_path.set(r"C:\irgendwo\PPSA01234")
        app._ansicht_setzen("konsole", speichern=False)
        app._ansicht_setzen("umwandeln", speichern=False)
        self.assertEqual(r"C:\irgendwo\PPSA01234", app.source_path.get())
        app.source_path.set("")

    def test_vorschau_bleibt_in_der_konsole_weg_und_wird_nachgeholt(self):
        app = self.app
        app._ansicht_setzen("konsole", speichern=False)
        with mock.patch.object(app, "_pack_sidebar_title") as titel:
            app._update_sidebar_preview(None, "Spieltitel")
            titel.assert_not_called()
        self.assertEqual([(None, "Spieltitel")], app._vorschau_warteschlange)
        self.assertEqual("", app._sidebar_preview_title_label.winfo_manager())
        aufrufe = []
        echt = app._update_sidebar_preview

        def _mitschreiben(cover, titel):
            aufrufe.append((cover, titel))
            return echt(cover, titel)

        with mock.patch.object(app, "_update_sidebar_preview", _mitschreiben):
            app._ansicht_setzen("umwandeln", speichern=False)
        self.assertEqual([(None, "Spieltitel")], aufrufe)
        self.assertEqual([], app._vorschau_warteschlange)
        app._update_sidebar_preview(None, "")

    def test_cover_packt_sich_in_der_konsole_nicht_selbst_ein(self):
        """Mit echtem Cover - ohne Bild steigen die Funktionen ohnehin frueh aus."""
        from PIL import Image
        app = self.app
        _WURZEL.update()
        app._update_sidebar_preview(Image.new("RGB", (512, 512), (30, 90, 160)),
                                    "Spieltitel")
        _WURZEL.update()
        self.assertEqual("pack", app._sidebar_preview_img_label.winfo_manager(),
                         "Anker: Das Cover muesste in der ersten Ansicht stehen.")
        app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        app._pack_sidebar_title()
        app._center_sidebar_cover()
        app._refresh_sidebar_cover_size()
        gepackt = self._packfolge()
        self.assertNotIn(app._sidebar_preview_title_label, gepackt)
        self.assertNotIn(app._sidebar_preview_img_label, gepackt)
        app._ansicht_setzen("umwandeln", speichern=False)
        self.assertEqual("pack", app._sidebar_preview_img_label.winfo_manager(),
                         "Nach dem Zurueckschalten fehlt das Cover.")
        app._update_sidebar_preview(None, "")

    def test_die_ansicht_wird_gemerkt(self):
        app = self.app
        gespeichert = []
        with mock.patch.object(app, "_save_setting",
                               lambda k, v: gespeichert.append((k, v))):
            app._ansicht_setzen("konsole")
            app._ansicht_setzen("umwandeln")
        self.assertEqual([("ansicht", "konsole"), ("ansicht", "umwandeln")], gespeichert)
        with mock.patch.object(app, "_load_setting", return_value="konsole"):
            app._ansicht_beim_start_herstellen()
        self.assertTrue(app._ansicht_ist_konsole())

    def test_jeder_konsolenknopf_oeffnet_sein_fenster(self):
        """Seit Stufe 4 ist jeder der sieben Knoepfe verdrahtet.

        Bis dahin hielt dieser Test fest, dass ein Knopf ohne Fenster das
        auch sagt; dieser Zweig wird jetzt in test_konsole_dienste direkt
        geprueft, weil er sich ueber die Seitenleiste nicht mehr ausloesen
        laesst. Hier zaehlt nun das Gegenstueck: Ein Druck oeffnet wirklich
        das Fenster, das in der Karte steht - und keine Kennung fehlt.
        """
        app = self.app
        app._ansicht_setzen("konsole", speichern=False)
        for nummer, (_schluessel, kennung) in enumerate(app._KONSOLE_KNOEPFE):
            methode = app._KONSOLE_FENSTER.get(kennung, "")
            with self.subTest(kennung=kennung):
                self.assertTrue(methode, "Kennung %s ohne Fenster" % kennung)
                knopf, _s = app._konsole_knoepfe[nummer]
                with mock.patch.object(app,
                                       "_werkzeugfenster_umschalten") as um:
                    knopf._on_click()
                um.assert_called_once_with(methode)

    def test_texte_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        schluessel = ["ansicht.to_konsole", "ansicht.to_umwandeln",
                      "konsole.coming_title", "konsole.coming_message"]
        schluessel += [k for k, _kennung in self.app._KONSOLE_KNOEPFE]
        for k in schluessel:
            with self.subTest(schluessel=k):
                self.assertTrue(STRINGS[k].get("de"))
                self.assertTrue(STRINGS[k].get("en"))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class KonsolenTafelTests(unittest.TestCase):
    """Die Uebersicht rechts in der Ansicht KONSOLE.

    Bis v1.9.43 blieb die rechte Seite dort leer. Jetzt steht da, was die
    Ansicht ausmacht: ist die Konsole erreichbar, und was laeuft auf ihr.
    Die Zusage, auf die es beim Umschalten ankommt: **Tafel und Rollflaeche
    sind nie gleichzeitig da** - sie teilen sich dieselbe Zelle (1, 1).
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self):
        if self.app._ansicht_ist_konsole():
            self.app._ansicht_setzen("umwandeln", speichern=False)
            _WURZEL.update()

    def tearDown(self):
        if self.app._ansicht_ist_konsole():
            self.app._ansicht_setzen("umwandeln", speichern=False)
            _WURZEL.update()

    @staticmethod
    def _sichtbar(widget) -> bool:
        if widget is None:
            return False
        try:
            return widget.winfo_manager() == "grid" and bool(widget.grid_info())
        except Exception:  # noqa: BLE001
            return False

    def test_tafel_erscheint_erst_in_der_konsole(self):
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        tafel = getattr(self.app, "_konsole_tafel", None)
        self.assertIsNotNone(tafel, "in der Konsole muss die Tafel stehen")
        self.assertTrue(self._sichtbar(tafel))

    def test_tafel_und_rollflaeche_schliessen_einander_aus(self):
        """Beide in derselben Zelle - gleichzeitig waere eine ueber der anderen."""
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        tafel = getattr(self.app, "_konsole_tafel", None)
        self.assertTrue(self._sichtbar(tafel))
        self.assertFalse(self._sichtbar(self.app.content_scroll))

        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()
        self.assertFalse(self._sichtbar(tafel))
        self.assertTrue(self._sichtbar(self.app.content_scroll))

    def test_tafel_liegt_in_der_zelle_der_rollflaeche(self):
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        lage = getattr(self.app, "_konsole_tafel").grid_info()
        self.assertEqual(1, int(lage["row"]))
        self.assertEqual(1, int(lage["column"]))

    def test_tabelle_nennt_alle_dienste(self):
        from ps5_validator.utils import konsole_dienste
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        tabelle = getattr(self.app, "_konsole_tafel_tabelle", None)
        self.assertIsNotNone(tabelle)
        self.assertEqual([d.schluessel for d in konsole_dienste.KATALOG],
                         list(tabelle.get_children()))

    def test_umschalten_startet_keinen_faden(self):
        """Gemessen wird erst auf Knopfdruck - nicht beim Hinsehen."""
        vorher = {t.name for t in threading.enumerate()}
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertEqual(set(), {n for n in neu if n.startswith("konsole-")})

    def test_zweites_umschalten_baut_nicht_neu(self):
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        erste = getattr(self.app, "_konsole_tafel")
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        self.assertIs(erste, getattr(self.app, "_konsole_tafel"),
                      "die Tafel wird gebaut, nicht jedes Mal neu")

    def test_texte_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("tafel.title", "tafel.subtitle", "tafel.check",
                           "tafel.unbekannt", "tafel.status_idle",
                           "tafel.status_running", "tafel.gefunden",
                           "tafel.nur_dienste", "tafel.nicht_gefunden"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
