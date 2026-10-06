# -*- coding: utf-8 -*-
"""Fenster "Credits & Community" (Entwicklerkarten), Profilbilder, psxtools.de-Banner und die Entwicklerzeile bei Knopf 8.

Auftraege des Nutzers vom 06.10.2026. Geprueft wird ohne Netz: Jeder Eintrag hat sein Bild im mitgelieferten
Ordner, jedes Bild steht mit Pruefsumme in ``herkunft.json``, kein Bild liegt ohne Eintrag herum, jede Adresse
zeigt auf GitHub, die Bauplaene betten den Ordner ein. Dazu das echte Fenster: Karten, Umbruch nach Breite,
Dank nur bei Platz; das Banner: nie in der Testreihe, ein- und ausblenden, Klick oeffnet psxtools.de.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import credits_daten as cd         # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

ORDNER = PROJEKT / cd.BILDORDNER
HERKUNFT = json.loads((ORDNER / "herkunft.json").read_text(encoding="utf-8"))
BAUPLAENE = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec", "PS5ImageConverter_Pro_macos.spec")


class DatenTests(unittest.TestCase):
    def test_es_gibt_alle_drei_gruppen(self) -> None:
        for gruppe in cd.GRUPPEN:
            with self.subTest(gruppe=gruppe):
                self.assertTrue(cd.gruppe(gruppe))

    def test_kein_konto_doppelt(self) -> None:
        logins = [e.login.lower() for e in cd.ENTWICKLER if e.login]
        self.assertEqual(len(logins), len(set(logins)))

    def test_ausdruecklich_gewuenschte_stehen_drin(self) -> None:
        """Nutzer 06.10.2026: Gezine, owendswang und Drakmor - und das eigene Bild fuers Programm."""
        logins = {e.login for e in cd.ENTWICKLER}
        self.assertLessEqual({"Gezine", "owendswang", "drakmor", "strongt1me"}, logins)
        self.assertEqual("strongt1me", cd.gruppe(cd.PROJEKT)[0].login)

    def test_jede_adresse_zeigt_auf_github(self) -> None:
        for e in cd.ENTWICKLER:
            for titel, adresse in e.werke:
                with self.subTest(wer=e.name, werk=titel):
                    self.assertRegex(adresse, r"^https://github\.com/[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)?$")

    def test_jeder_dank_ist_zweisprachig(self) -> None:
        for e in cd.ENTWICKLER:
            with self.subTest(wer=e.name):
                self.assertTrue(e.dank_text("de"))
                self.assertTrue(e.dank_text("en"))
                self.assertNotEqual(e.dank_text("de"), e.dank_text("en"))

    def test_nichts_unbelegtes(self) -> None:
        """Gezine und owendswang stehen in keinem kstuff-Commitverlauf - so wird es auch nicht behauptet."""
        for e in cd.ENTWICKLER:
            if e.login in ("Gezine", "owendswang"):
                with self.subTest(wer=e.login):
                    self.assertNotIn("kstuff", " ".join([e.dank_text("de"), e.dank_text("en")] +
                                                        [t for t, _u in e.werke]).lower())

    def test_die_ueberschriften_sind_uebersetzt(self) -> None:
        for gruppe in cd.GRUPPEN:
            for schluessel in ("credits.gruppe_" + gruppe, "credits.gruppe_%s_text" % gruppe):
                with self.subTest(schluessel=schluessel):
                    self.assertTrue(STRINGS[schluessel]["de"])
                    self.assertTrue(STRINGS[schluessel]["en"])


class BilderTests(unittest.TestCase):
    def test_jeder_eintrag_mit_konto_hat_sein_bild(self) -> None:
        for e in cd.ENTWICKLER:
            if e.login:
                with self.subTest(wer=e.login):
                    self.assertTrue((ORDNER / e.bild).is_file())

    def test_jedes_bild_steht_mit_pruefsumme_in_der_herkunft(self) -> None:
        eintraege = dict(HERKUNFT["bilder"], **HERKUNFT["banner"])
        bilder = sorted(p.name for p in ORDNER.glob("*.png"))
        self.assertEqual(sorted(eintraege), bilder)
        for name, angabe in eintraege.items():
            with self.subTest(bild=name):
                self.assertEqual(angabe["sha256"], hashlib.sha256((ORDNER / name).read_bytes()).hexdigest())

    def test_kein_bild_ohne_eintrag(self) -> None:
        erwartet = {e.bild for e in cd.ENTWICKLER if e.login} | {APP.PS5ConverterGUI._BANNER_DATEI}
        self.assertEqual(erwartet, {p.name for p in ORDNER.glob("*.png")})

    def test_profilbilder_sind_klein(self) -> None:
        from PIL import Image
        for e in cd.ENTWICKLER:
            if e.login:
                with self.subTest(wer=e.login), Image.open(ORDNER / e.bild) as bild:
                    self.assertEqual((160, 160), bild.size)

    def test_jeder_bauplan_bettet_den_ordner_ein(self) -> None:
        for plan in BAUPLAENE:
            with self.subTest(plan=plan):
                text = (PROJEKT / plan).read_text(encoding="utf-8")
                self.assertIn("_dateien_ohne_pycache(_credits_bilder, 'credits')", text)

    def test_die_lizenzdatei_nennt_den_ordner(self) -> None:
        self.assertIn("`credits/`", (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8"))


class _MitFenster(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
        cls.root = tk._default_root or tk.Tk()
        cls.root.withdraw()
        cls.app = APP.PS5ConverterGUI(cls.root)
        cls.app._current_language = "de"
        cls.root.withdraw()
        for kind in cls.root.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    def ruhen(self, sekunden: float) -> None:
        ende = time.time() + sekunden
        while time.time() < ende:
            self.root.update()
            time.sleep(0.02)


class FensterTests(_MitFenster):
    def setUp(self) -> None:
        # Der Umbruch misst die echte Breite - dazu muss das Fenster stehen, aber ausserhalb des Bildschirms.
        self.root.geometry("800x600+-4000+100")
        self.root.deiconify()
        self.addCleanup(self.root.withdraw)
        self.app._show_credits()
        self.win = self.app._cred_win
        self.win.geometry("900x800+-4000+50")
        self.addCleanup(self._zu)

    def _zu(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.app._cred_win = None

    def _karten(self) -> list:
        leinwand = next(w for w in self.win.winfo_children() if isinstance(w, tk.Canvas))
        inner = leinwand.winfo_children()[0]
        return [k for r in inner.winfo_children() if isinstance(r, tk.Frame)
                for k in r.winfo_children() if isinstance(k, tk.Frame) and k.cget("highlightthickness") == 1]

    def _dank_sichtbar(self) -> int:
        return sum(1 for k in self._karten() for w in k.winfo_children()
                   if isinstance(w, tk.Label) and w.winfo_manager() == "grid" and str(w.cget("font")).endswith("italic"))

    def test_eine_karte_je_entwickler(self) -> None:
        self.ruhen(0.4)
        self.assertEqual(len(cd.ENTWICKLER), len(self._karten()))

    def test_breit_mehrere_spalten_mit_dank(self) -> None:
        self.win.geometry("1500x900+-4000+50")
        self.ruhen(0.6)
        spalten = {int(k.grid_info()["column"]) for k in self._karten()}
        self.assertEqual({0, 1, 2}, spalten)
        self.assertEqual(len(cd.ENTWICKLER), self._dank_sichtbar())

    def test_schmal_eine_spalte(self) -> None:
        self.win.geometry("560x800+-4000+50")
        self.ruhen(0.6)
        self.assertEqual({0}, {int(k.grid_info()["column"]) for k in self._karten()})

    def test_namen_und_werke_sind_links(self) -> None:
        self.ruhen(0.4)
        with mock.patch("webbrowser.open") as offen:
            karte = self._karten()[0]
            rechts = next(w for w in karte.winfo_children() if isinstance(w, tk.Frame))
            rechts.winfo_children()[0].event_generate("<Button-1>")
        offen.assert_called_once_with("https://github.com/strongt1me")


class BannerTests(_MitFenster):
    def test_in_der_testreihe_wird_nichts_geplant(self) -> None:
        with mock.patch.object(self.root, "after") as nach:
            self.app._banner_planen()
        nach.assert_not_called()

    def test_ausserhalb_der_testreihe_nach_fuenf_minuten(self) -> None:
        module = dict(sys.modules)
        module.pop("pytest", None)
        with mock.patch.dict(sys.modules, module, clear=True), mock.patch.object(self.root, "after") as nach:
            self.app._banner_planen()
        nach.assert_called_once()
        self.assertEqual(300_000, nach.call_args[0][0])

    def test_minimiert_kein_fenster_und_neuer_versuch(self) -> None:
        with mock.patch.object(self.root, "state", return_value="iconic"), \
                mock.patch.object(self.root, "after") as nach, \
                mock.patch.object(APP.tk, "Toplevel") as fenster:
            self.app._banner_zeigen(3)
        fenster.assert_not_called()
        self.assertEqual((60_000, self.app._banner_zeigen, 2), nach.call_args[0])

    def test_nach_dem_letzten_versuch_wieder_zur_naechsten_stunde(self) -> None:
        with mock.patch.object(self.root, "state", return_value="iconic"), \
                mock.patch.object(self.app, "_banner_naechstes") as naechstes:
            self.app._banner_zeigen(1)
        naechstes.assert_called_once_with()

    def test_die_naechste_einblendung_kommt_nach_60_minuten(self) -> None:
        module = dict(sys.modules)
        module.pop("pytest", None)
        with mock.patch.dict(sys.modules, module, clear=True), mock.patch.object(self.root, "after") as nach:
            self.app._banner_naechstes()
        self.assertEqual((3_600_000, self.app._banner_zeigen, self.app._BANNER_VERSUCHE), nach.call_args[0])

    def test_in_der_testreihe_keine_naechste_einblendung(self) -> None:
        with mock.patch.object(self.root, "after") as nach:
            self.app._banner_naechstes()
        nach.assert_not_called()

    def test_klick_oeffnet_psxtools(self) -> None:
        # Ausserhalb des Bildschirms - das Banner folgt dem Fenster dorthin
        self.root.geometry("800x600+-4000+100")
        self.root.deiconify()
        self.addCleanup(self.root.withdraw)
        self.ruhen(0.3)
        vorher = set(self.root.winfo_children())
        with mock.patch.object(self.app, "_BANNER_ZEIGEN_MS", 200), mock.patch("webbrowser.open") as offen, \
                mock.patch.object(self.app, "_banner_naechstes") as naechstes:
            self.app._banner_zeigen()
            neu = [w for w in self.root.winfo_children() if w not in vorher and isinstance(w, tk.Toplevel)]
            self.assertEqual(1, len(neu))
            self.ruhen(0.5)
            naechstes.assert_not_called()
            neu[0].winfo_children()[0].event_generate("<Button-1>")
            self.ruhen(2.5)
        offen.assert_called_once_with("https://psxtools.de/")
        self.assertFalse(neu[0].winfo_exists())
        naechstes.assert_called_once_with()


class UrheberZeileTests(unittest.TestCase):
    def test_knopf_8_nennt_chillquant(self) -> None:
        name, adresse, bild = APP.PS5ConverterGUI._WEBSEITE_URHEBER["directstream.titel"]
        self.assertEqual(("ChillQuant", "https://github.com/ChillQuant/direct-stream-ps5"), (name, adresse))
        self.assertTrue((PROJEKT / "DirectStream-2.8.5" / bild).is_file())
        self.assertIn("{name}", STRINGS["webseite.entwickler"]["de"])


if __name__ == "__main__":
    unittest.main()
