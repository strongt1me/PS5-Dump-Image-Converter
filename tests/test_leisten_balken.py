# -*- coding: utf-8 -*-
"""Der Fortschrittsbalken der Knopfleiste mit runden Ecken (Nutzerwunsch 17.11.2026: "hier bitte die Ecken abrunden").

Bis dahin ein ``ttk.Progressbar`` mit rechteckiger Rinne. Jetzt ``leisten_balken.LeistenBalken``: ein Balken mit runden Enden,
dessen Rundungen ueber dem Bildausschnitt der Leiste stehen (``PS5ConverterGUI._rund_hintergrund``) - ohne ihn stuende hinter
den Ecken die Flaechenfarbe als dunkler Kasten auf dem Hintergrundbild.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("leisten_balken")

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    from PIL import Image
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


def _lade():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "keine Anzeige")
class LeistenBalkenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        from ps5_validator.ui import fenster_pillen, leisten_balken
        cls.haupt = _lade()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls.modul = leisten_balken
        cls.basis = fenster_pillen.Progressbar

    def setUp(self) -> None:
        self.rahmen = tk.Frame(_WURZEL)
        self.addCleanup(self.rahmen.destroy)
        self.aufrufe: list = []

    def _balken(self, hintergrund="muster", **opt):
        if hintergrund == "muster":
            def hintergrund(widget, b, h):                       # ein roter Ausschnitt: dort stehen die Rundungen
                self.aufrufe.append((b, h))
                return Image.new("RGB", (b, h), (255, 0, 0))
        balken = self.modul.LeistenBalken(self.rahmen, self.app._pw.look, hintergrund=hintergrund, maximum=100, **opt)
        self.addCleanup(balken.destroy)
        return balken

    # ---------------- im Hauptfenster ----------------
    def test_die_knopfleiste_hat_den_runden_balken(self) -> None:
        balken = self.app.progress
        self.assertIsInstance(balken, self.modul.LeistenBalken)
        self.assertNotIsInstance(balken, self.haupt.ttk.Progressbar, "kein eckiger ttk-Balken mehr")
        balken.grid()                       # im Leerlauf ausgeblendet: grid() stellt die gemerkten Optionen wieder her
        try:
            info = balken.grid_info()
            self.assertEqual(2, int(info["column"]))
            self.assertIn("e", str(info["sticky"]))
            self.assertIn("w", str(info["sticky"]))
            self.assertEqual("0", str(info.get("ipady", 0)), "kein ipady mehr: die Hoehe hat der Balken selbst")
        finally:
            balken.grid_remove()
        self.assertEqual(self.app.action_bar, balken.master)

    def test_er_folgt_der_fortschrittsvariable_wie_vorher(self) -> None:
        balken = self.app.progress
        for wert in (0.0, 0.2, 45.0, 100.0):
            with self.subTest(wert=wert):
                self.app.progress_var.set(wert)
                self.assertAlmostEqual(wert, balken.wert)
        self.app.progress_var.set(0)

    def test_im_leerlauf_bleibt_er_ausgeblendet(self) -> None:
        self.assertEqual("", self.app.progress.winfo_manager(), "grid_remove im Leerlauf, wie vorher")

    def test_die_runden_flaechen_ziehen_ihn_mit_nach(self) -> None:
        """Bild- oder Designwechsel und Verschieben laufen ueber ``_runde_flaechen_jetzt``: sonst bliebe der alte Ausschnitt stehen."""
        with mock.patch.object(self.app.progress, "nachziehen") as nachziehen:
            self.app._runde_flaechen_jetzt()
        nachziehen.assert_called()

    def test_er_gibt_dem_balken_den_ausschnitt_des_hauptfensters(self) -> None:
        quelle = HAUPT.read_text(encoding="utf-8")
        self.assertIn("hintergrund=self._rund_hintergrund, variable=self.progress_var", quelle)

    # ---------------- das Bild ----------------
    def test_die_ecken_stehen_auf_dem_bildausschnitt_nicht_auf_einer_flaechenfarbe(self) -> None:
        balken = self._balken()
        bild = balken._bild(120, 20)
        self.assertEqual((120, 20), bild.size)
        self.assertEqual((255, 0, 0, 255), bild.getpixel((0, 0)), "links oben: das Bild, nicht schwarz")
        self.assertEqual((255, 0, 0, 255), bild.getpixel((119, 19)), "rechts unten ebenso")
        mitte = bild.getpixel((60, 10))
        self.assertNotEqual((255, 0, 0), mitte[:3], "in der Mitte steht die Rinne")
        self.assertEqual(255, mitte[3])

    def test_ohne_bildausschnitt_sind_die_ecken_durchsichtig(self) -> None:
        balken = self._balken(hintergrund=None)
        bild = balken._bild(120, 20)
        self.assertEqual(0, bild.getpixel((0, 0))[3])
        self.assertEqual(0, bild.getpixel((119, 19))[3])
        self.assertEqual(255, bild.getpixel((60, 10))[3])

    def test_die_ecken_sind_gerundet_die_basis_zeichnet_sie_ebenso(self) -> None:
        """Gegen einen eckigen Balken: Die Rundung ist die Pille der Basisklasse (Radius = halbe Hoehe)."""
        balken = self._balken()
        roh = self.basis._bild(balken, 120, 20)
        for ecke in ((0, 0), (119, 0), (0, 19), (119, 19)):
            with self.subTest(ecke=ecke):
                self.assertEqual(0, roh.getpixel(ecke)[3])
        self.assertEqual(255, roh.getpixel((60, 0))[3], "oben in der Mitte ist die Kante gezeichnet")

    def test_die_fuellung_waechst_mit_dem_wert(self) -> None:
        balken = self._balken()
        leer = balken._bild(160, 22)
        balken.setzen(60)
        voll = balken._bild(160, 22)
        self.assertNotEqual(leer.tobytes(), voll.tobytes())
        links = voll.getpixel((24, 11))
        rechts = voll.getpixel((150, 11))
        self.assertNotEqual(links, rechts, "links die Fuellung, rechts die leere Rinne")

    def test_ein_ausschnitt_falscher_groesse_wird_angepasst(self) -> None:
        balken = self._balken(hintergrund=lambda w, b, h: Image.new("RGB", (b + 7, h + 3), (0, 255, 0)))
        bild = balken._bild(100, 20)
        self.assertEqual((100, 20), bild.size)
        self.assertEqual((0, 255, 0, 255), bild.getpixel((0, 0)))

    def test_ein_fehler_beim_holen_des_ausschnitts_laesst_den_balken_nicht_ausfallen(self) -> None:
        def kaputt(widget, b, h):
            raise RuntimeError("kein Bild")
        balken = self._balken(hintergrund=kaputt)
        bild = balken._bild(100, 20)
        self.assertEqual((100, 20), bild.size)
        self.assertEqual(0, bild.getpixel((0, 0))[3])

    # ---------------- der Ausschnitt wird nicht bei jedem Wert neu geholt ----------------
    def test_der_ausschnitt_wird_nur_bei_neuer_groesse_oder_lage_geholt(self) -> None:
        balken = self._balken()
        for _ in range(5):
            balken._bild(120, 20)
        self.assertEqual(1, len(self.aufrufe), "fuenf Zeichnungen derselben Groesse an derselben Stelle: ein Ausschnitt")
        balken._bild(130, 20)
        self.assertEqual(2, len(self.aufrufe), "neue Groesse: neuer Ausschnitt")

    def test_nachziehen_holt_den_ausschnitt_neu(self) -> None:
        balken = self._balken()
        balken._bild(120, 20)
        balken.nachziehen()
        self.assertIsNone(balken._ausschnitt_merker, "geleert; gezeichnet wird erst, wenn der Balken eine Groesse hat")
        balken._bild(120, 20)
        self.assertEqual(2, len(self.aufrufe))

    def test_die_hoehe_folgt_der_anzeigeskalierung(self) -> None:
        balken = self._balken(hoehe=22)
        self.assertEqual(int(self.app._pw.look.z.px(22)), int(balken.cget("height")))
        gross = self._balken(hoehe=40)
        self.assertGreater(int(gross.cget("height")), int(balken.cget("height")))


class BasisKlasseTests(unittest.TestCase):
    """Die Aufteilung von ``FortschrittsPille._zeichnen`` in ``_bild`` und Anzeige darf die PS4-Fenster nicht aendern."""

    def test_zeichnen_zeigt_was_bild_liefert(self) -> None:
        import inspect
        from ps5_validator.ui import ps4_ota_bausteine as b
        quelle = inspect.getsource(b.FortschrittsPille._zeichnen)
        self.assertIn("self._bild(b, h)", quelle)
        self.assertTrue(hasattr(b.FortschrittsPille, "_bild"))


if __name__ == "__main__":
    unittest.main()
