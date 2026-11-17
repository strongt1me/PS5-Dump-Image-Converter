# -*- coding: utf-8 -*-
"""Die Aufklappliste einer ttk.Combobox ist so breit wie ihr laengster Eintrag (Nutzerwunsch 17.11.2026).

Gemeldet wurde: "Dump-Ordner (mit Ei..." in der Liste des Zielformats und "NG 0.4.0-beta de..." in der Liste der AMPR-EMU-Fassung -
Tk macht die Liste so breit wie das Feld und schneidet laengere Eintraege ab.
"""
from __future__ import annotations

import inspect
import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import combobox_liste   # noqa: E402

try:
    import tkinter as tk
    from tkinter import font as tkfont
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

LANG = "Dump-Ordner (mit Einbau, ohne Abbild)"
VERSIONEN = ["NG 0.4.1", "NG 0.4.1 debug", "NG 0.4.0-beta", "NG 0.4.0-beta debug", "NG 0.3.5", "NG 0.3.5 debug"]


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ComboboxListeTests(unittest.TestCase):

    def setUp(self) -> None:
        self.assertTrue(combobox_liste.installieren(_WURZEL), "diese Tk-Fassung kennt ttk::combobox::PlacePopdown")
        self.fenster = tk.Toplevel(_WURZEL)
        self.fenster.geometry("+120+120")
        self.addCleanup(self.fenster.destroy)
        self.offen: "list[ttk.Combobox]" = []
        self.addCleanup(self._schliessen)

    def _schliessen(self) -> None:
        for box in self.offen:
            try:
                _WURZEL.tk.call("ttk::combobox::Unpost", str(box))
            except tk.TclError:
                pass

    def _box(self, werte: "list[str]", breite: int = 10, **kw) -> ttk.Combobox:
        box = ttk.Combobox(self.fenster, values=werte, width=breite, state="readonly", **kw)
        box.pack(padx=20, pady=20)
        self.fenster.update()                    # das Fenster wird angezeigt: das Feld hat seine wirkliche Breite
        return box

    def _liste_zeigen(self, box: ttk.Combobox) -> "tuple[int, int, int, int]":
        """Oeffnet die Liste wie ein Klick und liefert (Breite, Hoehe, x, y) der Aufklappliste."""
        _WURZEL.tk.call("ttk::combobox::Post", str(box))
        self.offen.append(box)
        _WURZEL.update()                         # die Groesse eines angezeigten Fensters gilt erst, wenn Tk die Ereignisse verarbeitet hat
        geo = _WURZEL.tk.call("wm", "geometry", "%s.popdown" % box)
        m = re.match(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$", str(geo))
        self.assertIsNotNone(m, geo)
        return int(m.group(1)), int(m.group(2)), int(m.group(3)[1:]), int(m.group(4)[1:])

    def _schrift(self, box: ttk.Combobox) -> tkfont.Font:
        return tkfont.Font(root=_WURZEL, font=str(_WURZEL.tk.call("%s.popdown.f.l" % box, "cget", "-font")))

    # ------------------------------------------------------------------ die Breite
    def test_ein_langer_eintrag_ist_nicht_mehr_abgeschnitten(self) -> None:
        box = self._box([".ffpfsc", ".exFAT", LANG])
        feld = box.winfo_width()
        breite, *_ = self._liste_zeigen(box)
        text = self._schrift(box).measure(LANG)
        self.assertGreater(text, feld, "Voraussetzung: der Eintrag ist breiter als das Feld")
        self.assertGreaterEqual(breite, text, "die Liste ist mindestens so breit wie der Text")
        self.assertGreater(breite, feld)

    def test_die_fassungsliste_der_ampr_emu_ist_breit_genug(self) -> None:
        box = self._box(VERSIONEN, breite=9)
        breite, *_ = self._liste_zeigen(box)
        self.assertGreaterEqual(breite, self._schrift(box).measure("NG 0.4.0-beta debug"))

    def test_kurze_eintraege_lassen_die_liste_so_breit_wie_das_feld(self) -> None:
        box = self._box(["a", "bb", "ccc"], breite=24)
        feld = box.winfo_width()
        breite, *_ = self._liste_zeigen(box)
        self.assertEqual(feld, breite, "nicht schmaler und nicht breiter als das Feld")

    def test_rollt_die_liste_kommt_die_rollleiste_dazu(self) -> None:
        werte = ["Eintrag %02d mit einem recht langen Text" % i for i in range(30)]
        box = self._box(werte, breite=12, height=5)
        breite, *_ = self._liste_zeigen(box)
        sb = int(_WURZEL.tk.call("winfo", "reqwidth", "%s.popdown.f.sb" % box))
        text = self._schrift(box).measure(werte[0])
        self.assertGreater(sb, 0)
        self.assertGreaterEqual(breite, text + sb, "Text und Rollleiste passen nebeneinander")

    def test_ohne_eintraege_aendert_sich_nichts(self) -> None:
        box = self._box([], breite=14)
        feld = box.winfo_width()
        breite, *_ = self._liste_zeigen(box)
        self.assertEqual(feld, breite)

    def test_die_liste_geht_nicht_ueber_den_rechten_bildschirmrand(self) -> None:
        rechts = _WURZEL.winfo_vrootx() + _WURZEL.winfo_vrootwidth()
        self.fenster.geometry("+%d+120" % (rechts - 140))               # das Feld sitzt fast am rechten Rand
        self.fenster.update_idletasks()
        box = self._box([LANG], breite=8)
        breite, _h, x, _y = self._liste_zeigen(box)
        self.assertGreater(breite, box.winfo_width())
        self.assertLessEqual(x + breite, rechts, "die Liste endet am Bildschirmrand, nicht dahinter")
        self.assertGreaterEqual(x, _WURZEL.winfo_vrootx())

    def test_die_liste_ist_nie_breiter_als_der_bildschirm(self) -> None:
        box = self._box(["x" * 1200], breite=8)
        breite, *_ = self._liste_zeigen(box)
        self.assertLessEqual(breite, _WURZEL.winfo_vrootwidth())

    def test_mehrfaches_installieren_aendert_nichts_und_laeuft_nicht_in_sich_selbst(self) -> None:
        combobox_liste.installieren(_WURZEL)
        combobox_liste.installieren(_WURZEL)
        box = self._box([LANG], breite=8)
        breite, *_ = self._liste_zeigen(box)                              # endlose Rekursion wuerde hier als TclError enden
        self.assertGreaterEqual(breite, self._schrift(box).measure(LANG))

    def test_die_stiloption_steht_nach_dem_aufklappen_wieder_wie_vorher(self) -> None:
        def zahlen(wert) -> "tuple[int, ...]":
            return tuple(int(z) for z in str(wert).replace("(", " ").replace(")", " ").replace(",", " ").split())

        stil = ttk.Style(_WURZEL)
        stil.configure("Eigen.TCombobox", postoffset=(4, 0, 12, 0))      # ein Stil, der die Liste schon selbst verschiebt
        box = self._box([LANG], breite=8, style="Eigen.TCombobox")
        vorher = zahlen(stil.lookup("Eigen.TCombobox", "postoffset"))
        self.assertEqual((4, 0, 12, 0), vorher)
        breite, *_ = self._liste_zeigen(box)
        self.assertEqual(vorher, zahlen(stil.lookup("Eigen.TCombobox", "postoffset")), "die Huelle gibt die Option zurueck")
        self.assertGreaterEqual(breite, self._schrift(box).measure(LANG), "auch mit eigener Verschiebung ist nichts abgeschnitten")
        standard = zahlen(stil.lookup("TCombobox", "postoffset", None, "0 0 0 0"))
        self._liste_zeigen(self._box([LANG], breite=8))
        self.assertEqual(standard, zahlen(stil.lookup("TCombobox", "postoffset", None, "0 0 0 0")))

    def test_ein_zweites_aufklappen_bleibt_breit_genug(self) -> None:
        box = self._box([LANG, ".ffpkg"], breite=8)
        erste, *_ = self._liste_zeigen(box)
        _WURZEL.tk.call("ttk::combobox::Unpost", str(box))
        _WURZEL.update()
        zweite, *_ = self._liste_zeigen(box)
        self.assertEqual(erste, zweite)
        self.assertGreaterEqual(zweite, self._schrift(box).measure(LANG))

    def test_der_wert_des_feldes_bleibt_wie_er_war(self) -> None:
        box = self._box([".ffpkg", LANG], breite=8)
        box.set(".ffpkg")
        self._liste_zeigen(box)
        self.assertEqual(".ffpkg", box.get(), "Aufklappen aendert die Auswahl nicht")
        self.assertEqual(8, int(box.cget("width")), "das Feld selbst bleibt so schmal, wie es war")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class HauptfensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"                 # im Volllauf sonst die Sprache des zuletzt importierten Pruefmoduls

    def test_das_programm_baut_die_huelle_beim_anlegen_der_stile_ein(self) -> None:
        self.assertTrue(_WURZEL.tk.call("info", "commands", combobox_liste.URSPRUNG))
        quelle = inspect.getsource(type(self.app)._setup_styles)
        self.assertIn("combobox_liste.installieren(self.root)", quelle)

    def test_die_echten_felder_zeigen_ihre_eintraege_ganz(self) -> None:
        a = self.app
        for name, werte in (("format_combo", [".ffpfsc", ".ffpfs (unkomprimiert)", ".exFAT", ".ffpkg", "Dump-Ordner (mit Einbau, ohne Abbild)"]),
                            ("ampr_version_combo", VERSIONEN)):
            box = getattr(a, name)
            vorher = tuple(box.cget("values"))
            zustand = str(box.cget("state"))
            with self.subTest(feld=name):
                try:
                    box.configure(values=werte, state="readonly")          # ein gesperrtes Feld klappt nicht auf
                    a.root.update_idletasks()
                    _WURZEL.tk.call("ttk::combobox::Post", str(box))
                    _WURZEL.update()
                    geo = str(_WURZEL.tk.call("wm", "geometry", "%s.popdown" % box))
                    breite = int(geo.split("x", 1)[0])
                    schrift = tkfont.Font(root=_WURZEL, font=str(_WURZEL.tk.call("%s.popdown.f.l" % box, "cget", "-font")))
                    self.assertGreaterEqual(breite, max(schrift.measure(w) for w in werte), "kein Eintrag wird abgeschnitten")
                finally:
                    try:
                        _WURZEL.tk.call("ttk::combobox::Unpost", str(box))
                    except tk.TclError:
                        pass
                    box.configure(values=vorher, state=zustand)


if __name__ == "__main__":
    unittest.main()
