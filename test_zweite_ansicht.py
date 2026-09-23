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


if __name__ == "__main__":
    unittest.main(verbosity=2)
