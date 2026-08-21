# -*- coding: utf-8 -*-
"""Tests gegen springende und vertauschte Sidebar-Vorschau.

Hintergrund (Bildschirmaufnahme vom 16.08.2026): Beim Programmstart erschien
das Cover zuerst allein, verschwand rund 0,8 s ganz und kam danach mit dem
Spielnamen zurueck - der Name stand dabei *ueber* dem Bild, obwohl er darunter
gehoert, und das Cover sass 23 px tiefer als vorher.

Ursache war die Reihenfolge im Packmanager. ``pack()`` haengt ein Widget ans
Ende der Packliste seines Elternteils. ``_update_sidebar_preview`` wird von vier
Stellen mit unterschiedlichen Kombinationen aufgerufen:

    (None,  "")      Quellwechsel      - beides ausblenden
    (Cover, "")      Schnellvorschau   - nur Bild
    (None,  Titel)   Metadaten ohne Bild
    (Cover, Titel)   vollstaendige Metadaten

Lag die Titelzeile schon in der Packliste, landete ein danach gepacktes Cover
dahinter. Deshalb pruefen die Tests hier *jede* Reihenfolge dieser Aufrufe, nicht
nur die eine, die zufaellig in der Aufnahme zu sehen war.

Ohne verfuegbare Anzeige werden die Tests uebersprungen.
"""
import io
import itertools
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    from PIL import Image
    # Vorhandene Wurzel mitbenutzen, falls ein anderes Testmodul schon eine
    # angelegt hat: Ein zweiter Tk-Interpreter im selben Prozess kann die
    # Bilder des ersten nicht verwenden ("image ... doesn't exist").
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "keine Anzeige verfuegbar")
class SidebarVorschauTests(unittest.TestCase):
    """Prueft Reihenfolge und Sichtbarkeit am laufenden Tk-Baum."""

    @classmethod
    def setUpClass(cls):
        haupt = _lade_hauptprogramm()
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.cover = Image.new("RGB", (512, 512), (40, 90, 160))

    def setUp(self):
        self.bild = self.app._sidebar_preview_img_label
        self.titel = self.app._sidebar_preview_title_label
        self.sidebar = self.bild.nametowidget(self.bild.winfo_parent())
        # Jeder Test startet aus dem leeren Zustand.
        self.app._update_sidebar_preview(None, "")

    def _reihenfolge(self):
        """Positionen von Bild und Titelzeile in der Packliste der Sidebar."""
        liste = self.sidebar.pack_slaves()
        return (liste.index(self.bild) if self.bild in liste else -1,
                liste.index(self.titel) if self.titel in liste else -1)

    def test_titel_steht_immer_unter_dem_cover(self):
        """Der Spielname gehoert unter das Bild - in jeder Aufrufreihenfolge."""
        aufrufe = [
            ("leer",        None,        ""),
            ("nur Bild",    self.cover,  ""),
            ("nur Titel",   None,        "Instant Sports Plus"),
            ("vollstaendig", self.cover, "Instant Sports Plus"),
        ]
        for folge in itertools.permutations(aufrufe):
            with self.subTest(folge=[n for n, _, _ in folge]):
                self.app._update_sidebar_preview(None, "")
                for _name, cover, titel in folge:
                    self.app._update_sidebar_preview(cover, titel)
                pos_bild, pos_titel = self._reihenfolge()
                if pos_bild >= 0 and pos_titel >= 0:
                    self.assertLess(
                        pos_bild, pos_titel,
                        "Der Spielname steht ueber dem Cover statt darunter",
                    )

    def test_titelzeile_bleibt_bei_cover_ohne_namen_stehen(self):
        """Die Zeile wird schon mit dem Bild reserviert, nicht erst mit Text.

        Sonst rueckt das Cover nach oben, sobald der Name eintrifft - in der
        Aufnahme der Sprung von y=571 auf y=548.
        """
        self.app._update_sidebar_preview(self.cover, "")
        self.assertTrue(
            self.titel.winfo_manager(),
            "Titelzeile fehlt, obwohl das Cover angezeigt wird",
        )
        self.assertEqual(self.titel.cget("text"), "")

    def test_leere_titelzeile_ist_so_hoch_wie_eine_gefuellte(self):
        """Darauf beruht, dass das Cover beim Eintreffen des Namens stehenbleibt.

        Die Zeile wird schon mit dem Cover eingeblendet und erst danach
        beschriftet. Zaehlte eine leere Zeile weniger als eine einzeilige,
        ruckte das Cover genau in diesem Moment nach oben.
        """
        hoehen = {}
        for name in ("", "Kurz", "Instant Sports Plus"):
            self.app._update_sidebar_preview(self.cover, name)
            _WURZEL.update_idletasks()
            hoehen[name] = self.app._sidebar_titel_hoehe()
        self.assertEqual(len(set(hoehen.values())), 1,
                         f"Hoehe schwankt mit dem Text: {hoehen}")

    def test_polsterung_haengt_nicht_am_spielnamen(self):
        """Dieselbe Quelle, einmal ohne und einmal mit Namen - gleiche Lage."""
        self.app._sidebar_cover_vorlauf = 3          # sonst am Fenster gemessen
        ohne = self.app._sidebar_block_polster(299, True, 3)
        self.app._sidebar_preview_title_label.config(text="Instant Sports Plus")
        mit = self.app._sidebar_block_polster(299, True, 3)
        self.assertEqual(ohne, mit)

    def test_metadaten_ohne_cover_nehmen_das_bild_nicht_weg(self):
        """Sonst blinkt das Cover bei jedem Metadatenschritt weg.

        Am Start ruft _update_info_box mehrfach mit cover=None auf, obwohl die
        Schnellvorschau schon ein Bild derselben Quelle zeigt.
        """
        self.app._update_sidebar_preview(self.cover, "")
        self.app._update_sidebar_preview(None, "Instant Sports Plus")
        self.assertTrue(self.bild.winfo_manager(),
                        "Das Cover wurde von den Metadaten verdraengt")
        self.assertEqual(self.titel.cget("text"), "Instant Sports Plus")
        pos_bild, pos_titel = self._reihenfolge()
        self.assertLess(pos_bild, pos_titel)

    def test_ohne_vorhandenes_cover_bleibt_der_titel_allein(self):
        """Gibt es kein Bild, zeigt die Sidebar nur den Namen."""
        self.app._update_sidebar_preview(None, "Ein Spiel ohne icon0")
        self.assertFalse(self.bild.winfo_manager())
        self.assertTrue(self.titel.winfo_manager())

    def test_runde_ecken_stoeren_das_fenster_nicht(self):
        """Der Eckenschnitt ist Beiwerk - er darf nie den Splash verhindern."""
        fenster = tk.Toplevel(_WURZEL)
        try:
            fenster.overrideredirect(True)
            fenster.geometry("400x200+50+50")
            fenster.update_idletasks()
            self.app._runde_fensterecken(fenster, self.app._SPLASH_ECKENRADIUS)
            self.assertTrue(fenster.winfo_exists())
            # Auch unsinnige Werte duerfen nichts umwerfen
            self.app._runde_fensterecken(fenster, 0)
            self.app._runde_fensterecken(fenster, 9999)
            self.assertTrue(fenster.winfo_exists())
        finally:
            fenster.destroy()

    def test_cover_ohne_quelle_wird_geleert(self):
        """Bei echtem Quellwechsel verschwindet die Vorschau vollstaendig."""
        self.app._update_sidebar_preview(self.cover, "Instant Sports Plus")
        self.app._update_sidebar_preview(None, "")
        self.assertFalse(self.bild.winfo_manager())
        self.assertFalse(self.titel.winfo_manager())


class QuelltextTests(unittest.TestCase):
    """Prueft die Stellen, die sich nur im Quelltext nachweisen lassen."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            cls.quelle = datei.read()

    def test_jedes_toplevel_bekommt_farbe_im_erzeuger(self):
        """Sonst blitzt ein neues Fenster weiss auf, bevor es dunkel wird.

        Tk zeichnet ein frisches Toplevel zuerst in seiner weissen
        Standardfarbe. Am Hauptfenster war das nachmessbar: zwei Einzelbilder
        lang vollflaechig weiss. Ein spaeteres ``configure(bg=...)`` kommt zu
        spaet - die Farbe gehoert in den Erzeuger.
        """
        ohne_farbe = []
        for nr, zeile in enumerate(self.quelle.split("\n"), start=1):
            if "tk.Toplevel(" in zeile and "bg=" not in zeile:
                ohne_farbe.append(f"{nr}: {zeile.strip()}")
        self.assertEqual(ohne_farbe, [],
                         "Toplevel ohne Hintergrundfarbe im Erzeuger:\n" +
                         "\n".join(ohne_farbe))

    def test_hauptfenster_wird_erst_fertig_gezeigt(self):
        """Unsichtbar aufbauen, dann in einem Zug zeigen.

        Ueber "-alpha" und ausdruecklich nicht ueber withdraw(): Das
        state("zoomed") in _setup_window bildet ein zurueckgezogenes Fenster
        wieder ab - gemessen springt winfo_viewable dabei von 0 auf 1, das
        weisse Fenster war danach trotz withdraw() zu sehen.
        """
        abschnitt = self.quelle[self.quelle.index('if __name__ == "__main__":'):]
        self.assertIn('root.attributes("-alpha", 0.0)', abschnitt)
        self.assertIn('root.attributes("-alpha", 1.0)', abschnitt)
        self.assertNotIn("root.withdraw()", abschnitt)
        self.assertLess(
            abschnitt.index('root.attributes("-alpha", 0.0)'),
            abschnitt.index("app = PS5ConverterGUI(root)"),
            "Das Fenster muss vor dem Aufbau unsichtbar werden",
        )
        self.assertLess(
            abschnitt.index('root.attributes("-alpha", 1.0)'),
            abschnitt.index("root.mainloop()"),
            "Ohne Ruecknahme vor mainloop() bliebe das Fenster unsichtbar",
        )

    def test_splash_bekommt_runde_ecken(self):
        """Der Eckenschnitt muss im Splash auch tatsaechlich aufgerufen werden."""
        anfang = self.quelle.index("def _show_splash")
        rumpf = self.quelle[anfang:anfang + 4000]
        self.assertIn("self._runde_fensterecken(splash, self._SPLASH_ECKENRADIUS)", rumpf)

    def test_bild_wird_vor_die_titelzeile_gepackt(self):
        """Ohne before= landet ein spaeter gepacktes Cover hinter dem Namen."""
        anfang = self.quelle.index(
            "_sidebar_preview_img_label.config(image=self._sidebar_preview_photo)")
        rumpf = self.quelle[anfang:anfang + 800]
        self.assertIn("before=self._sidebar_preview_title_label", rumpf)

    def test_moduswechsel_leert_die_vorschau_nicht(self):
        """Nur ein anderer Quellpfad rechtfertigt das Leeren."""
        stelle = self.quelle.index("_alt_ctx = getattr(self, \"_last_preview_ctx\"")
        rumpf = self.quelle[stelle:stelle + 1600]
        treffer = re.search(
            r"if _alt_ctx is None or _alt_ctx\[1\] != _ctx\[1\]:\s*\n\s*"
            r"self\._update_sidebar_preview\(None, \"\"\)", rumpf)
        self.assertIsNotNone(
            treffer, "Das Leeren haengt nicht mehr am Quellpfad")


if __name__ == "__main__":
    unittest.main(verbosity=2)
