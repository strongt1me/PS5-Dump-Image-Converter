# -*- coding: utf-8 -*-
"""Aufgabe 7 "PKG / FPKG" als Seite im rechten Bereich der Ansicht UMWANDELN (``ui/pkg_fpkg_seite.py``,
seit 12.10.2026, bis zum selben Abend noch ein reiner Platzhalter ohne Funktion).

Wunsch des Nutzers: Aufgabe 7 (AMPR EMU Manager) wandert zum Knopf "9." der Ansicht KONSOLE, an ihrer Stelle in der
Seitenleiste UMWANDELN steht "7. PKG / FPKG". Der Bereich "PS4 PKG" zeigt die Oberflaeche von ``ui/ps4_dump_image.py``
(bis dahin das Popup "PS4 PKG Dump & Image Converter"), "PS5 PKG" die von ``ui/ps5_pkg_fenster.py`` (bis dahin "PS5 PKG
Dump & Image Converter") - beide eingebettet statt als eigenes Fenster. Seit dem 30.10.2026 gibt es keinen Umschalter
mehr: Das Quellfeld der Seite erkennt am Format der gewaehlten Quelle, welcher Bereich gezeigt wird.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import tkinter as tk
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None

from ps5_validator.ui import ampr_seite                     # noqa: E402
from ps5_validator.ui import pkg_fpkg_seite                 # noqa: E402
from ps5_validator.ui import ps4_dump_image                 # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster                 # noqa: E402
from test_pkg_plattform import cnt_paket, fih_paket          # noqa: E402


def _quellfeld_oben_in_der_karte(test, s) -> None:
    """Das Quellfeld steht seit 31.10.2026 oben in der Karte des Bereichs (wie QUELLE bei Aufgabe 1)."""
    knoten, karte = s.quelle_feld, None
    while knoten is not None and knoten is not s.bereich:
        if getattr(knoten, "_sb_karte", False):
            karte = knoten
        knoten = knoten.master
    test.assertIs(knoten, s.bereich, "Das Quellfeld liegt im Bereich.")
    test.assertIsNotNone(karte, "Das Quellfeld steht in der Karte des Bereichs.")
    test.assertLessEqual(karte.winfo_rooty(), s.quelle_feld.winfo_rooty())
    test.assertLess(s.quelle_feld.winfo_rooty() - karte.winfo_rooty(), 120, "Das Quellfeld steht oben in der Karte.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class SeitenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._ansicht_setzen("umwandeln")
        self.app._pkg_fpkg_seite_verbergen()

    def _toplevels(self) -> set:
        return {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}

    def test_der_knopf_zeigt_die_seite_ohne_fenster(self) -> None:
        vorher = self._toplevels()
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertTrue(self.app._pkg_fpkg_seite_sichtbar)
        self.assertEqual("grid", s.rahmen.winfo_manager())
        self.assertEqual((1, 1), (int(s.rahmen.grid_info()["row"]), int(s.rahmen.grid_info()["column"])))
        self.assertEqual("", self.app.content_scroll.winfo_manager(), "Die Rollflaeche ist ausgeblendet.")
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein Fenster.")
        self.assertEqual("pkg_fpkg", self.app.current_mode.get())

    def test_ein_zweiter_druck_aendert_nichts(self) -> None:
        self.app._show_pkg_fpkg_seite()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        self.assertTrue(self.app._pkg_fpkg_seite_sichtbar)
        self.assertEqual("grid", s.rahmen.winfo_manager())

    def test_eine_andere_aufgabe_blendet_die_seite_aus(self) -> None:
        self.app._show_pkg_fpkg_seite()
        self.app._set_mode_from_sidebar("pack_folder")
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertFalse(self.app._pkg_fpkg_seite_sichtbar)
        self.assertEqual("", s.rahmen.winfo_manager())
        self.assertEqual("grid", self.app.content_scroll.winfo_manager(), "Die Rollflaeche ist wieder da.")

    def test_die_ampr_seite_und_diese_seite_schliessen_sich_aus(self) -> None:
        """Diese Seite liegt in der Zelle (1, 1) der Ansicht UMWANDELN, die AMPR-Seite in
        derselben Zelle der Ansicht KONSOLE - der Wechsel der Ansicht blendet die eine weg,
        bevor die andere erscheint (seit 12.10.2026: AMPR ist Knopf "9." der Ansicht KONSOLE)."""
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        pkg = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertTrue(self.app._pkg_fpkg_seite_sichtbar)
        self.app._ansicht_setzen("konsole")
        self.app._konsole_amprmgr_zeigen()
        _WURZEL.update()
        try:
            self.assertFalse(self.app._pkg_fpkg_seite_sichtbar)
            self.assertEqual("", pkg.rahmen.winfo_manager())
            ampr = getattr(self.app, ampr_seite.SEITE_ATTRIBUT)
            self.assertEqual("grid", ampr.rahmen.winfo_manager())
        finally:
            self.app._ansicht_setzen("umwandeln")

    def test_die_ansicht_konsole_nimmt_die_seite_weg(self) -> None:
        self.app._show_pkg_fpkg_seite()
        self.app._ansicht_setzen("konsole")
        try:
            self.assertFalse(self.app._pkg_fpkg_seite_sichtbar)
            s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
            self.assertEqual("", s.rahmen.winfo_manager())
        finally:
            self.app._ansicht_setzen("umwandeln")

    def test_der_knopf_der_seitenleiste_traegt_die_sieben(self) -> None:
        modi = [m for _n, m in self.app._MODE_OPTIONS]
        namen = [n for n, _m in self.app._MODE_OPTIONS]
        self.assertNotIn("ampr_manager", modi, "Aufgabe 7 ist aus der Seitenleiste UMWANDELN verlegt")
        self.assertIn("7. PKG / FPKG", namen)
        self.assertIn("8. Validator", namen)
        self.assertNotIn("7. AMPR EMU Manager", namen)

    def test_der_konsole_knopf_neun_zeigt_dieselbe_ampr_seite(self) -> None:
        kennungen = [k for _s, k in self.app._KONSOLE_KNOEPFE]
        # Knopf 9; seit 14.10.2026 folgt Knopf 10 "AMPR-Mitschnitt".
        self.assertEqual("amprmgr", kennungen[8])
        self.assertEqual("amprmitschnitt", kennungen[9])
        self.assertEqual("_konsole_amprmgr_zeigen", self.app._KONSOLE_SEITEN["amprmgr"])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class PkgFpkgUnterseitenTests(unittest.TestCase):
    """Die beiden eingebetteten Bereiche "PS4 PKG" (``ps4_dump_image``) und "PS5 PKG" (``ps5_pkg_fenster``), die das
    Quellfeld der Seite nach dem Format der gewaehlten Quelle waehlt (seit 30.10.2026, kein Umschalter mehr)."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._ansicht_setzen("umwandeln")
        self.app._pkg_fpkg_seite_verbergen()
        # Jeder Test faengt frisch an: die Seite (und mit ihr "PS4 PKG"/"PS5 PKG", als ihre Kinder) ganz zerstoeren,
        # statt sie nur auszublenden - sonst stuende der eine Bereich noch gewaehlt, wenn ein spaeterer Test den
        # anderen erwartet (``_bei_zerstoerung`` setzt die beiden ``FENSTER_ATTRIBUT`` beim Zerstoeren selbst zurueck).
        seite = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT, None)
        if seite is not None:
            try:
                seite.rahmen.destroy()
            except tk.TclError:
                pass
            delattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self._bereich_vorgeben("")                       # ohne gemerkten Bereich: Vorgabe PS5
        # Das Vorbauen im Leerlauf (900 ms) soll in den Tests nicht dazwischenfunken: Das Unterlegen des Hauptbilds macht
        # jedes Zeigen etwas langsamer, und ein Test, der "noch nicht gebaut" erwartet, sah sonst den Leerlauf kommen.
        vorbau = mock.patch.object(pkg_fpkg_seite.PkgFpkgSeite, "_VORBAU_NACH_MS", 600000)
        vorbau.start()
        self.addCleanup(vorbau.stop)
        self.ordner = tempfile.mkdtemp(prefix="pkgseite_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)

    def _bereich_vorgeben(self, wert: str) -> None:
        self.app._save_setting(pkg_fpkg_seite.EINST_BEREICH, wert)

    def _toplevels(self) -> set:
        return {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}

    def _seite(self):
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        return getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)

    def _ps4(self):
        return getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT)

    def _ps5(self):
        return getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)

    def test_die_seite_zeigt_zuerst_ps5_ohne_fenster(self) -> None:
        vorher = self._toplevels()
        s = self._seite()
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite, "Vorgabe ohne gemerkten Bereich: PS5.")
        ps5 = self._ps5()
        self.assertIsNotNone(ps5)
        self.assertFalse(isinstance(ps5.win, tk.Toplevel), "Die Oberflaeche liegt in einem Rahmen, nicht in einem Fenster.")
        self.assertIs(s.bereich, ps5.win.master, "Der Rahmen gehoert dem Bereich unter dem Quellfeld.")
        self.assertEqual("pack", ps5.win.winfo_manager())
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein Fenster.")

    def _seite_bauen_und_zerstoeren(self) -> None:
        self._seite()
        seite = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        seite.rahmen.destroy()
        delattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        del seite
        _WURZEL.update()

    def _hinterlassenschaft(self) -> tuple:
        """Was eine zerstoerte Seite im Prozess zurueckliesse: Tk-Bilder, Seitenbilder, Bindungen am Hauptfenster."""
        import gc
        from ps5_validator.ui.seitenbild import Seitenbild
        gc.collect()
        bilder = len(_WURZEL.tk.splitlist(_WURZEL.tk.call("image", "names")))
        seitenbilder = sum(1 for o in gc.get_objects() if isinstance(o, Seitenbild))
        oben = _WURZEL.winfo_toplevel()
        bindungen = sum(len([z for z in str(oben.tk.call("bind", oben._w, folge)).split("\n") if z.strip()])
                        for folge in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Map>", "<Configure>"))
        return bilder, seitenbilder, bindungen

    def test_eine_zerstoerte_seite_hinterlaesst_nichts(self) -> None:
        """Waechter (31.10.2026): Jede gebaute Seite liess ihre Rollflaeche samt Kindern und Tk-Bildern am Hauptfenster
        haengen (die Mausrad-Bindungen der Rollflaeche), im Testlauf rund 100 MB je Aufbau bis zum Absturz bei 65 %."""
        self._seite_bauen_und_zerstoeren()                 # warmlaufen: erste Bilder, Schriften, Zwischenspeicher
        vorher = self._hinterlassenschaft()
        for _ in range(3):
            self._seite_bauen_und_zerstoeren()
        nachher = self._hinterlassenschaft()
        self.assertEqual(vorher, nachher, "Eine zerstoerte Seite darf weder Bilder noch Bindungen zurueckhalten.")

    def test_gegenprobe_eine_hinterlassene_bindung_wird_gemessen(self) -> None:
        """Die Messung sieht den Fehler: Eine Bindung am Hauptfenster, die nicht abgenommen wird, zaehlt."""
        self._seite_bauen_und_zerstoeren()
        vorher = self._hinterlassenschaft()
        kennung = _WURZEL.winfo_toplevel().bind("<MouseWheel>", lambda e: None, add="+")
        self.addCleanup(_WURZEL.winfo_toplevel().unbind, "<MouseWheel>", kennung)
        self._seite_bauen_und_zerstoeren()
        self.assertNotEqual(vorher, self._hinterlassenschaft())

    # ---- Vor der ersten gueltigen Wahl steht nur QUELLE da (31.10.2026) ---------------------------------------------
    def _rest_steht(self, f) -> bool:
        """Steht alles unter dem Quellfeld im Layout (Knopfleiste, Protokoll, Zielformat bzw. Spiele)?"""
        if hasattr(f, "_rest_unten"):                       # PS4 PKG
            return f._rest_unten.winfo_manager() == "pack" and f._rest_karte.winfo_manager() == "pack"
        return f.leiste.winfo_manager() == "grid" and f.spalte_rechts.winfo_manager() == "grid"

    def test_vorher_steht_nur_quelle_da_im_ps5_bereich(self) -> None:
        s = self._seite()
        f = self._ps5()
        self.assertFalse(self._rest_steht(f), "Ohne Wahl steht nichts unter QUELLE.")
        self.assertFalse(f.start_knopf.winfo_ismapped())
        self.assertTrue(s.quelle_feld.winfo_ismapped(), "QUELLE selbst steht da.")
        self.assertTrue(s._quellsaetze[pkg_fpkg_seite.UNTERSEITE_FPKG]["datei"].winfo_ismapped())
        self.assertTrue(s._quellsaetze[pkg_fpkg_seite.UNTERSEITE_FPKG]["ordner"].winfo_ismapped())

    def test_vorher_steht_nur_quelle_da_im_ps4_bereich(self) -> None:
        self._bereich_vorgeben(pkg_fpkg_seite.UNTERSEITE_PKG)
        s = self._seite()
        f = self._ps4()
        self.assertFalse(self._rest_steht(f), "Ohne Wahl steht nichts unter QUELLE.")
        self.assertFalse(f.start_knopf.winfo_ismapped())
        self.assertTrue(s.quelle_feld.winfo_ismapped())

    def test_eine_ps5_wahl_blendet_den_rest_ein(self) -> None:
        s = self._seite()
        pfad = fih_paket(os.path.join(self.ordner, "Spiel_PPSA00001.pkg"))
        s.quelle_waehlen([pfad])
        _WURZEL.update()
        f = self._ps5()
        self.assertTrue(self._rest_steht(f))
        self.assertTrue(f.start_knopf.winfo_ismapped())
        self.assertTrue(s.quelle_feld.winfo_ismapped(), "QUELLE bleibt dabei stehen.")

    def test_eine_ps4_wahl_blendet_den_rest_ein(self) -> None:
        s = self._seite()
        pfad = cnt_paket(os.path.join(self.ordner, "Spiel_CUSA00001.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.quelle_waehlen([pfad])
        _WURZEL.update()
        f = self._ps4()
        self.assertTrue(self._rest_steht(f))
        self.assertTrue(f.start_knopf.winfo_ismapped())

    def test_eine_ungueltige_quelle_laesst_den_rest_verborgen(self) -> None:
        s = self._seite()
        kaputt = os.path.join(self.ordner, "kein_paket.pkg")
        with open(kaputt, "wb") as f:
            f.write(b"kein Paket")
        erg = s.quelle_waehlen([kaputt])
        _WURZEL.update()
        self.assertIsNone(erg.plattform)
        self.assertFalse(self._rest_steht(self._ps5()), "Ungueltig: der Rest bleibt verborgen.")
        self.assertFalse(s._gewaehlt)

    def test_nach_der_ersten_gueltigen_wahl_bleibt_der_rest_auch_bei_ungueltiger_eingabe(self) -> None:
        s = self._seite()
        s.quelle_waehlen([fih_paket(os.path.join(self.ordner, "Spiel_PPSA00001.pkg"))])
        kaputt = os.path.join(self.ordner, "kein_paket.pkg")
        with open(kaputt, "wb") as f:
            f.write(b"kein Paket")
        s.quelle_waehlen([kaputt])
        _WURZEL.update()
        self.assertTrue(self._rest_steht(self._ps5()))

    def test_der_wechsel_zwischen_den_bereichen_zeigt_in_beiden_den_rest(self) -> None:
        s = self._seite()
        ps5 = fih_paket(os.path.join(self.ordner, "Spiel_PPSA00001.pkg"))
        ps4 = cnt_paket(os.path.join(self.ordner, "Spiel_CUSA00001.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.quelle_waehlen([ps4])
            _WURZEL.update()
            self.assertTrue(self._rest_steht(self._ps4()))
            s.quelle_waehlen([ps5])
            _WURZEL.update()
            self.assertTrue(self._rest_steht(self._ps5()))
            s.quelle_waehlen([ps4])
            _WURZEL.update()
            self.assertTrue(self._rest_steht(self._ps4()))

    def test_ein_paket_aus_der_bibliothek_blendet_den_rest_gleich_ein(self) -> None:
        s = self._seite()
        pfad = cnt_paket(os.path.join(self.ordner, "Spiel_CUSA00001.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.pkg_zeigen(pfad)
        _WURZEL.update()
        self.assertTrue(self._rest_steht(self._ps4()))

    def test_der_vorgebaute_bereich_bleibt_ohne_wahl_verborgen_und_zeigt_sich_nach_der_wahl(self) -> None:
        s = self._seite()                                   # PS5 steht
        s._pkg_vorbauen()                                   # PS4 im Leerlauf, hinter PS5
        _WURZEL.update()
        self.assertFalse(self._rest_steht(self._ps4()), "Vorgebaut, aber ohne Wahl nur QUELLE.")
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.quelle_waehlen([cnt_paket(os.path.join(self.ordner, "Spiel_CUSA00001.pkg"))])
        _WURZEL.update()
        self.assertTrue(self._rest_steht(self._ps4()), "Nach der Wahl steht der vorgebaute Bereich fertig da.")

    def test_gegenprobe_die_pruefung_sieht_einen_sichtbaren_rest(self) -> None:
        s = self._seite()
        s.quelle_waehlen([fih_paket(os.path.join(self.ordner, "Spiel_PPSA00001.pkg"))])
        _WURZEL.update()
        self.assertTrue(self._rest_steht(self._ps5()))
        self._ps5().rest_zeigen(False)
        self.assertFalse(self._rest_steht(self._ps5()))

    def test_der_zuletzt_benutzte_bereich_steht_beim_naechsten_mal_da(self) -> None:
        self._bereich_vorgeben(pkg_fpkg_seite.UNTERSEITE_PKG)
        s = self._seite()
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        self.assertEqual("pack", self._ps4().win.winfo_manager())

    def test_es_gibt_keinen_umschalter_mehr(self) -> None:
        s = self._seite()
        self.assertFalse(hasattr(s, "knoepfe"), "Der Umschalter PS4 PKG / PS5 PKG ist entfallen.")
        self.assertTrue(s.quelle_feld.winfo_ismapped(), "Stattdessen: das Quellfeld.")
        _quellfeld_oben_in_der_karte(self, s)

    def test_eine_ps4_quelle_oeffnet_den_ps4_bereich(self) -> None:
        s = self._seite()                                              # zuerst steht PS5
        pfad = cnt_paket(os.path.join(self.ordner, "Spiel_CUSA00001.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen") as einlesen:
            erg = s.quelle_waehlen([pfad])
        _WURZEL.update()
        self.assertEqual("ps4", erg.plattform)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        ps4 = self._ps4()
        self.assertEqual("pack", ps4.win.winfo_manager())
        self.assertEqual("", self._ps5().win.winfo_manager(), "PS5 ist jetzt ausgeblendet.")
        self.assertEqual(ps4_dump_image.QUELLE_DATEIEN, ps4.art_var.get())
        self.assertEqual(os.path.normpath(pfad), ps4.quelle_var.get())
        einlesen.assert_called_once()
        self.assertEqual(self.app._t("main.config_for", task=self.app._t("pkg_fpkg_seite.tab_pkg")),
                         s._untertitel.cget("text"), "Der Untertitel folgt dem erkannten Bereich.")
        self.assertIn("PS4 PKG", s._hinweis.cget("text"))
        self.assertEqual(pfad, s.quelle_var.get())

    def test_eine_ps5_quelle_oeffnet_den_ps5_bereich(self) -> None:
        self._bereich_vorgeben(pkg_fpkg_seite.UNTERSEITE_PKG)
        s = self._seite()                                              # zuerst steht PS4
        pfad = fih_paket(os.path.join(self.ordner, "Spiel_PPSA01234.pkg"))
        with mock.patch.object(ps5_pkg_fenster.Ps5PkgFenster, "_pakete_hinzufuegen") as hinzu:
            erg = s.quelle_waehlen([pfad])
        _WURZEL.update()
        self.assertEqual("ps5", erg.plattform)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite)
        self.assertEqual("pack", self._ps5().win.winfo_manager())
        self.assertEqual("", self._ps4().win.winfo_manager(), "PS4 ist jetzt ausgeblendet.")
        hinzu.assert_called_once_with([pfad], waehlen=True)
        self.assertEqual(self.app._t("main.config_for", task=self.app._t("pkg_fpkg_seite.tab_fpkg")),
                         s._untertitel.cget("text"))

    def test_die_quelle_wechselt_den_bereich_hin_und_her(self) -> None:
        s = self._seite()
        ps4_datei = cnt_paket(os.path.join(self.ordner, "a.pkg"))
        ps5_datei = fih_paket(os.path.join(self.ordner, "b.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"), \
                mock.patch.object(ps5_pkg_fenster.Ps5PkgFenster, "_pakete_hinzufuegen"):
            for datei, soll in ((ps4_datei, "pkg"), (ps5_datei, "fpkg"), (ps4_datei, "pkg"), (ps5_datei, "fpkg")):
                s.quelle_waehlen([datei])
                _WURZEL.update()
                self.assertEqual(soll, s.unterseite)
                sichtbar = self._ps4().win if soll == "pkg" else self._ps5().win
                andere = self._ps5().win if soll == "pkg" else self._ps4().win
                self.assertEqual("pack", sichtbar.winfo_manager())
                self.assertEqual("", andere.winfo_manager())

    def test_der_untertitel_erscheint_erst_nach_wahl_und_erkennung(self) -> None:
        """Nutzerwunsch 31.10.2026: Vor der Wahl kein "Konfiguration fuer: PS5 PKG"; die Zeile behaelt aber ihre Hoehe."""
        s = self._seite()
        leer = "\u00a0"
        self.assertEqual(leer, s._untertitel.cget("text"))
        hoehe = s._untertitel.winfo_reqheight()
        self.assertGreater(hoehe, 10, "Die Zeile behaelt ihre Hoehe, damit nichts springt.")
        # Ungueltig: nichts erkannt, der Untertitel bleibt leer.
        schlecht = os.path.join(self.ordner, "text.pkg")
        with open(schlecht, "wb") as f:
            f.write(b"keine Paketdatei" * 50)
        s.quelle_waehlen([schlecht])
        self.assertEqual(leer, s._untertitel.cget("text"))
        # Erkannt (Gegenprobe): jetzt steht der Text da, und die Hoehe ist dieselbe.
        pfad = cnt_paket(os.path.join(self.ordner, "Spiel_CUSA00001.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.quelle_waehlen([pfad])
        _WURZEL.update()
        self.assertEqual(self.app._t("main.config_for", task=self.app._t("pkg_fpkg_seite.tab_pkg")),
                         s._untertitel.cget("text"))
        self.assertEqual(hoehe, s._untertitel.winfo_reqheight(), "Gleiche Hoehe vor und nach der Wahl.")

    def test_der_untertitel_bleibt_leer_nach_ruecksprung_und_aktualisierung_solange_nichts_gewaehlt_ist(self) -> None:
        s = self._seite()
        self.app._show_pkg_fpkg_seite()                  # zurueck auf die Seite
        s._untertitel_aktualisieren()                    # wie nach einem Sprach- oder Designwechsel
        _WURZEL.update()
        self.assertEqual("\u00a0", s._untertitel.cget("text"))
        # Ein Paket aus der Bibliothek (Vorgabe) gilt als gewaehlt.
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.pkg_zeigen(os.path.join(self.ordner, "x.pkg"))
        self.assertEqual(self.app._t("main.config_for", task=self.app._t("pkg_fpkg_seite.tab_pkg")),
                         s._untertitel.cget("text"))
        s._untertitel_aktualisieren()
        self.assertEqual(self.app._t("main.config_for", task=self.app._t("pkg_fpkg_seite.tab_pkg")),
                         s._untertitel.cget("text"), "Nach der Wahl bleibt er auch nach einer Aktualisierung.")

    def test_eine_ungueltige_quelle_laesst_bereich_und_feld_stehen(self) -> None:
        s = self._seite()
        gueltig = fih_paket(os.path.join(self.ordner, "gut.pkg"))
        with mock.patch.object(ps5_pkg_fenster.Ps5PkgFenster, "_pakete_hinzufuegen"):
            s.quelle_waehlen([gueltig])
        schlecht = os.path.join(self.ordner, "text.pkg")
        with open(schlecht, "wb") as f:
            f.write(b"keine Paketdatei" * 50)
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen") as einlesen, \
                mock.patch.object(ps5_pkg_fenster.Ps5PkgFenster, "_pakete_hinzufuegen") as hinzu:
            erg = s.quelle_waehlen([schlecht])
        _WURZEL.update()
        self.assertIsNone(erg.plattform)
        einlesen.assert_not_called()
        hinzu.assert_not_called()
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite, "Der Bereich bleibt, wie er war.")
        self.assertEqual(gueltig, s.quelle_var.get(), "Das Feld behaelt die letzte gueltige Wahl.")
        text = s._hinweis.cget("text")
        self.assertIn("Keine gültige PKG", text)
        self.assertIn("nicht übernommen", text)
        zeilen = self._ps5().protokoll.get("1.0", "end")
        self.assertIn("Keine gültige PKG", zeilen, "Die Meldung steht auch im Protokoll - nichts geschieht stumm.")

    def test_ein_ordner_ohne_spiel_und_ohne_pkg_wird_klar_abgelehnt(self) -> None:
        s = self._seite()
        leer = os.path.join(self.ordner, "leer")
        os.makedirs(leer)
        erg = s.quelle_waehlen([leer])
        self.assertIsNone(erg.plattform)
        self.assertIn("Keine gültige PKG", s._hinweis.cget("text"))

    def test_ein_gemischter_ordner_geht_in_den_ps4_bereich_und_sagt_es(self) -> None:
        s = self._seite()
        mix = os.path.join(self.ordner, "mix")
        os.makedirs(mix)
        cnt_paket(os.path.join(mix, "a.pkg"))
        fih_paket(os.path.join(mix, "b.pkg"))
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            erg = s.quelle_waehlen([mix])
        _WURZEL.update()
        self.assertTrue(erg.gemischt)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        self.assertEqual(ps4_dump_image.QUELLE_ORDNER, self._ps4().art_var.get())
        self.assertIn("Gemischte Auswahl", s._hinweis.cget("text"))
        self.assertIn("Gemischte Auswahl", self._ps4().protokoll.get("1.0", "end"))

    def test_ein_entpacktes_ps4_spiel_wird_als_solches_uebergeben(self) -> None:
        s = self._seite()
        spiel = os.path.join(self.ordner, "dump")
        os.makedirs(os.path.join(spiel, "sce_sys"))
        open(os.path.join(spiel, "sce_sys", "param.sfo"), "w").close()
        with mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s.quelle_waehlen([spiel])
        self.assertEqual(ps4_dump_image.QUELLE_DUMP, self._ps4().art_var.get())

    def test_ablegen_und_getippter_pfad_gehen_denselben_weg(self) -> None:
        s = self._seite()
        pfad = fih_paket(os.path.join(self.ordner, "mit leerzeichen.pkg"))
        with mock.patch.object(ps5_pkg_fenster.Ps5PkgFenster, "_pakete_hinzufuegen") as hinzu:
            s._abgelegt(types.SimpleNamespace(data="{%s}" % pfad.replace("\\", "/")))
            s.quelle_var.set(pfad)
            s._quelle_eingegeben()
        self.assertEqual(2, hinzu.call_count)
        for aufruf in hinzu.call_args_list:
            self.assertEqual([os.path.normpath(pfad)], aufruf.args[0])

    def test_die_dateiwahl_nimmt_mehrere_pakete(self) -> None:
        s = self._seite()
        a = cnt_paket(os.path.join(self.ordner, "a.pkg"))
        b = cnt_paket(os.path.join(self.ordner, "b.pkg"))
        with mock.patch.object(pkg_fpkg_seite.filedialog, "askopenfilenames", return_value=(a, b)), \
                mock.patch.object(ps4_dump_image.Ps4DumpImageFenster, "_einlesen"):
            s._datei_waehlen()
        self.assertEqual(os.pathsep.join((os.path.normpath(a), os.path.normpath(b))), self._ps4().quelle_var.get())
        self.assertEqual(ps4_dump_image.QUELLE_DATEIEN, self._ps4().art_var.get())

    def test_die_ordnerwahl_geht_in_die_erkennung(self) -> None:
        s = self._seite()
        pkgs = os.path.join(self.ordner, "pkgs")
        os.makedirs(pkgs)
        fih_paket(os.path.join(pkgs, "a.pkg"))
        with mock.patch.object(pkg_fpkg_seite.filedialog, "askdirectory", return_value=pkgs), \
                mock.patch.object(ps5_pkg_fenster.Ps5PkgFenster, "_pakete_hinzufuegen") as hinzu:
            s._ordner_waehlen()
        hinzu.assert_called_once_with([os.path.normpath(pkgs)], waehlen=True)

    def test_die_unterseite_ist_beim_ersten_zeigen_schon_ausgelegt(self) -> None:
        """Nichts baut sich sichtbar auf (30.10.2026): Beim Packen steht der neue Bereich schon in Zielgroesse.

        Vorher wurde er gepackt, bevor sein Layout fertig war - der Anwender sah beim ersten Wechsel erst ein Geruest
        mit schmaler Karte, dann die endgueltige Breite. Beim zweiten Mal war er bereits geordnet.
        """
        self._bereich_vorgeben(pkg_fpkg_seite.UNTERSEITE_PKG)
        s = self._seite()
        gesehen = {}
        echt = tk.Frame.pack

        def _pack(widget, *args, **kw):
            ps5 = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT, None)
            if ps5 is not None and widget is ps5.win:
                gesehen["breite"] = widget.winfo_width()
                gesehen["bereich"] = s.bereich.winfo_width()
            return echt(widget, *args, **kw)

        with mock.patch.object(tk.Frame, "pack", _pack):
            s.fpkg_zeigen()
        self.assertGreater(gesehen.get("breite", 0), 200, "Beim Packen war der Bereich noch nicht ausgelegt.")
        self.assertEqual(gesehen["bereich"], gesehen["breite"], "Er stand schon in der Groesse des Bereichsrahmens.")
        _WURZEL.update()
        # (Das Unterlegbild des Bereichs, ``Seitenbild``, liegt auch per ``place`` darin - das gehoert dazu.)
        stehen_geblieben = [w for w in s.bereich.winfo_children()
                            if w.winfo_manager() == "place" and not getattr(w, "_sb_eigen", False)]
        self.assertEqual([], stehen_geblieben, "Abdeckung oder Platzhalter sind wieder weg.")

    def test_der_andere_bereich_wird_im_leerlauf_vorgebaut_und_das_zeigen_packt_ihn_nur(self) -> None:
        """Der erste Wechsel dauerte 0,66 s, der zweite 0,08 s (30.10.2026): Der andere Bereich entsteht vorab."""
        self._bereich_vorgeben(pkg_fpkg_seite.UNTERSEITE_PKG)
        s = self._seite()
        self.assertIsNone(getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT, None), "Vor dem Leerlauf gibt es ihn noch nicht.")
        s._fpkg_vorbauen()
        ps5 = self._ps5()
        self.assertIsNotNone(ps5, "Die PS5-Ansicht ist vorgebaut.")
        self.assertEqual("", ps5.win.winfo_manager(), "Sie ist noch nicht gepackt - zu sehen ist weiter PS4.")
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        self.assertTrue(getattr(ps5.win, "_vorgelegt", False))
        s.fpkg_zeigen()
        _WURZEL.update()
        self.assertEqual("pack", ps5.win.winfo_manager())
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite)
        s._fpkg_vorbauen()                       # ein zweiter Aufruf baut nichts neu
        self.assertIs(ps5, self._ps5())

    def test_auch_der_ps4_bereich_wird_vorgebaut(self) -> None:
        s = self._seite()                         # PS5 steht
        self.assertIsNone(getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT, None))
        s._anderen_vorbauen()
        ps4 = self._ps4()
        self.assertEqual("", ps4.win.winfo_manager())
        self.assertTrue(getattr(ps4.win, "_vorgelegt", False))
        self.assertEqual("pack", self._ps5().win.winfo_manager(), "Sichtbar bleibt PS5.")

    def test_ein_erneuter_druck_auf_sieben_merkt_sich_den_bereich(self) -> None:
        s = self._seite()
        s.pkg_zeigen()
        self.app._set_mode_from_sidebar("pack_folder")                 # eine andere Aufgabe blendet die Seite aus
        _WURZEL.update()
        self.app._show_pkg_fpkg_seite()                                # erneut "7." - PS4 soll stehen bleiben
        _WURZEL.update()
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        self.assertEqual("pack", self._ps4().win.winfo_manager())

    def test_der_ps4_konverter_zeigt_sich_eingebettet_statt_in_einem_fenster(self) -> None:
        """``_show_ps4_pkg_converter`` ist der Weg der Bibliothek (Paket zum Umwandeln) - bis zum 12.10.2026
        abends oeffnete er ein Popup-Fenster, jetzt waehlt er den PS4-Bereich dieser Seite."""
        vorher = self._toplevels()
        self.app._ps4pkg_vorgabe = ""
        self.app._show_ps4_pkg_converter()
        _WURZEL.update()
        self.assertEqual("umwandeln", self.app._ansicht)
        self.assertEqual("pkg_fpkg", self.app.current_mode.get())
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_PKG, s.unterseite)
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein eigenes Fenster mehr.")

    def test_der_ps5_konverter_zeigt_sich_eingebettet_statt_in_einem_fenster(self) -> None:
        vorher = self._toplevels()
        self.app._show_ps5_pkg_converter()
        _WURZEL.update()
        self.assertEqual("umwandeln", self.app._ansicht)
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertEqual(pkg_fpkg_seite.UNTERSEITE_FPKG, s.unterseite)
        self.assertEqual(set(), self._toplevels() - vorher, "Es entsteht kein eigenes Fenster mehr.")

    def test_die_weitere_tools_knoepfe_sind_entfernt(self) -> None:
        ziele = [z for _s, z in self.app._MORE_TOOLS_ENTRIES]
        self.assertNotIn("_show_ps4_pkg_converter", ziele)
        self.assertNotIn("_show_ps5_pkg_converter", ziele)
        from ps5_validator.utils.i18n import STRINGS
        self.assertNotIn("titlebar.ps4pkg", STRINGS)
        self.assertNotIn("titlebar.ps5pkg", STRINGS)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class AussehenTests(unittest.TestCase):
    """Optik vom 30.10.2026: Die Seite hat den Kopf der Aufgaben 1 bis 6 (Ueberschrift, Untertitel), ein Quellfeld mit
    Waehl-Knoepfen, flache Abschnitte und die Knopfleiste STARTEN / ABBRECHEN - und haelt bei der Mindestgroesse alles
    im Bild."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app._ansicht_setzen("umwandeln")
        self.app._pkg_fpkg_seite_verbergen()
        self.app._save_setting(pkg_fpkg_seite.EINST_BEREICH, "")

    def _mindestgroesse(self) -> None:
        """Stellt das Fenster auf die Mindestgroesse (1260 x 700 inklusive Rahmen) und danach wieder zurueck."""
        zustand, geometrie = _WURZEL.state(), _WURZEL.geometry()

        def zurueck() -> None:
            _WURZEL.state("normal")
            _WURZEL.geometry(geometrie)
            _WURZEL.update()
            if zustand == "zoomed":
                _WURZEL.state("zoomed")
            _WURZEL.update()

        self.addCleanup(zurueck)
        _WURZEL.state("normal")
        _WURZEL.update()
        _WURZEL.geometry("1245x700+0+0")
        for _ in range(3):
            _WURZEL.update()
            _WURZEL.update_idletasks()

    @staticmethod
    def _abgeschnitten(wurzeln, panel) -> list:
        """Alle sichtbaren Nachfahren der ``wurzeln``, die rechts ueber die Flaeche ``panel`` hinausragen."""
        rechts = panel.winfo_rootx() + panel.winfo_width()
        schlecht = []
        stapel = list(wurzeln)
        while stapel:
            w = stapel.pop()
            for k in w.winfo_children():
                if isinstance(k, tk.Toplevel):
                    continue
                stapel.append(k)
                if k.winfo_viewable() and k.winfo_width() > 1 and k.winfo_rootx() + k.winfo_width() > rechts + 2:
                    schlecht.append("%s (%d px zu weit)" % (k, k.winfo_rootx() + k.winfo_width() - rechts))
        return schlecht

    def _leiste_im_bild(self, knoepfe, panel) -> list:
        """Knoepfe der Knopfleiste: nicht ueber den rechten Rand, und breit genug fuer ihre Beschriftung. Die Leiste steht
        wie bei Aufgabe 1 in der Rollflaeche - ob sie gerade im Sichtfeld liegt, haengt vom Rollstand ab."""
        fehler = []
        for knopf in knoepfe:
            links = knopf.winfo_rootx()
            if links < panel.winfo_rootx() or links + knopf.winfo_width() > panel.winfo_rootx() + panel.winfo_width() + 2:
                fehler.append("%s steht ausserhalb der Flaeche" % knopf)
            if knopf.winfo_width() < knopf.winfo_reqwidth() - 2:
                fehler.append("%s ist schmaler als seine Beschriftung" % knopf)
        return fehler

    def _seite_zeigen(self, bereich: str, gewaehlt: bool = True):
        """Zeigt die Seite mit dem Bereich. ``gewaehlt``: als haette der Anwender schon ein Paket gewaehlt - erst dann steht
        mehr als QUELLE da (31.10.2026)."""
        self.app._show_pkg_fpkg_seite()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        s._gewaehlt = gewaehlt
        (s.pkg_zeigen if bereich == "pkg" else s.fpkg_zeigen)()
        for _ in range(3):
            _WURZEL.update()
        return s

    def test_der_kopf_hat_ueberschrift_untertitel_und_quellfeld_wie_die_aufgaben(self) -> None:
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        self.assertEqual(self.app._t("mode.pkg_fpkg"), s._titel.cget("text"))
        self.assertEqual("\u00a0", s._untertitel.cget("text"), "Vor der Wahl bleibt der Untertitel leer.")
        s.pkg_zeigen()
        self.assertEqual("\u00a0", s._untertitel.cget("text"), "Auch der Bereichswechsel ohne Wahl nennt ihn nicht.")
        # Ueberschrift, Untertitel und Flaeche stehen untereinander; in der Flaeche das Quellfeld ueber dem Bereich.
        zeilen = [int(w.grid_info()["row"]) for w in (s._titel, s._untertitel, s.inhalt)]
        self.assertEqual(sorted(zeilen), zeilen)
        self.assertEqual(3, len(set(zeilen)))
        _quellfeld_oben_in_der_karte(self, s)

    def test_die_karte_steht_wie_bei_aufgabe_1_unter_dem_untertitel(self) -> None:
        """Karte, Titel und Untertitel an den Stellen von ``path_card``/``header_label``/``subtitle_label`` (gemessen)."""
        self.app._show_pkg_fpkg_seite()
        _WURZEL.update()
        s = getattr(self.app, pkg_fpkg_seite.SEITE_ATTRIBUT)
        s._gewaehlt = True
        for kennung, zeigen in (("pkg", s.pkg_zeigen), ("fpkg", s.fpkg_zeigen)):
            zeigen()
            for _ in range(6):
                _WURZEL.update()
            karte = s._quellsaetze[kennung]["zeile"].master.master
            self.assertTrue(getattr(karte, "_sb_karte", False), kennung)
            self.assertEqual(s._titel.winfo_rootx(), karte.winfo_rootx(), "Titel und Karte beginnen bei x gleich.")
            self.assertGreater(karte.winfo_rooty(), s._untertitel.winfo_rooty() + s._untertitel.winfo_height())
            # 30 px Polster wie ``path_card`` (padding=30).
            self.assertAlmostEqual(30, s._quellsaetze[kennung]["zeile"].winfo_rootx() - karte.winfo_rootx(), delta=2)

    def test_start_und_abbrechen_sind_die_grossen_knoepfe_der_aufgabe_1(self) -> None:
        self._seite_zeigen("fpkg")
        f = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)
        _WURZEL.update()
        for knopf, breite in ((f.start_knopf, 190), (f.abbrechen_knopf, 170)):
            self.assertEqual(self.app.run_btn.winfo_reqheight(), knopf.winfo_reqheight(), "Hoehe wie STARTEN.")
            self.assertGreaterEqual(knopf.winfo_reqwidth(), self.app.abort_btn.winfo_reqwidth() - 1 if breite == 170 else 0)
        self.assertEqual("disabled", str(f.abbrechen_knopf.cget("state")))
        f.abbrechen_knopf.state(["!disabled"])
        self.assertEqual("normal", str(f.abbrechen_knopf.cget("state")))

    def test_die_knopfleiste_steht_unter_den_abschnitten_mit_start_und_abbrechen_zuerst(self) -> None:
        self._seite_zeigen("fpkg")
        f = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)
        self.assertLess(f.start_knopf.winfo_rooty(), f.protokoll.winfo_rooty(), "Das Protokoll steht unter der Leiste.")
        self.assertGreater(f.start_knopf.winfo_rooty(), f.ziel_feld.winfo_rooty(), "Die Leiste steht unter den Abschnitten.")
        self.assertLess(f.start_knopf.winfo_rootx(), f.abbrechen_knopf.winfo_rootx())
        self.assertLess(f.abbrechen_knopf.winfo_rootx(), f.update_knopf.winfo_rootx())
        self._seite_zeigen("pkg")
        ps4 = getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT)
        self.assertLess(ps4.start_knopf.winfo_rootx(), ps4.abbrechen_knopf.winfo_rootx())
        self.assertLess(ps4.start_knopf.winfo_rooty(), ps4.protokoll.winfo_rooty(), "Das Protokoll steht unter der Leiste.")

    def test_die_abschnitte_sind_flach_ohne_kartenflaechen(self) -> None:
        """Wie bei Aufgabe 1: Abschnitte mit Beschriftung in Grossbuchstaben direkt auf der Seite, keine eigene Karte
        (``pw.Karte``) je Abschnitt."""
        self._seite_zeigen("fpkg")
        f = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)

        def karten_in(wurzel) -> list:
            stapel, gefunden = [wurzel], []
            while stapel:
                for k in stapel.pop().winfo_children():
                    stapel.append(k)
                    if type(k).__name__ == "Karte":
                        gefunden.append(k)
            return gefunden

        self.assertTrue(karten_in(f.seiten["extras"]), "Anker: die Suche findet Karten, wo es welche gibt.")
        self.assertEqual([], karten_in(f.seiten["umwandeln"]), "Die Seite Umwandeln hat keine Kartenflaechen mehr.")

    def test_die_pkg_seite_ragt_bei_mindestgroesse_nirgends_ueber_den_rand(self) -> None:
        self._mindestgroesse()
        s = self._seite_zeigen("pkg")
        ps4 = getattr(self.app, ps4_dump_image.FENSTER_ATTRIBUT)
        self.assertGreater(s.inhalt.winfo_width(), 400, "Anker: die Seite hat eine echte Breite.")
        self.assertEqual([], self._abgeschnitten([s._quelle_zeile, ps4.win], s.inhalt))
        # Seit 01.11.2026 rollt die Seite nicht mehr: Bei der Mindesthoehe (700 px) reicht der Platz nicht fuer alles,
        # der untere Teil (Leiste, Fortschritt, Protokoll) wird abgeschnitten statt zu rollen - dann ist er nicht zu
        # sehen und zaehlt hier nicht; was zu sehen ist, steht innerhalb der Flaeche.
        sichtbar = tuple(k for k in (ps4.start_knopf, ps4.abbrechen_knopf, ps4.einlesen_knopf, ps4.update_knopf,
                                     ps4.senden_knopf, ps4.mehr_knopf) if k.winfo_viewable())
        self.assertEqual([], self._leiste_im_bild(sichtbar, s.inhalt))

    def test_die_ps5_seite_ragt_bei_mindestgroesse_nirgends_ueber_den_rand(self) -> None:
        self._mindestgroesse()
        s = self._seite_zeigen("fpkg")
        f = getattr(self.app, ps5_pkg_fenster.FENSTER_ATTRIBUT)
        f._seite_zeigen("umwandeln")
        _WURZEL.update()
        self.assertGreater(s.inhalt.winfo_width(), 400, "Anker: die Seite hat eine echte Breite.")
        self.assertEqual([], self._abgeschnitten([s._quelle_zeile, f.seiten["umwandeln"], f.leiste], s.inhalt))
        self.assertEqual([], self._leiste_im_bild(
            (f.start_knopf, f.abbrechen_knopf, f.update_knopf, f.browser_knopf, f.detail_knopf, f.optionen_knopf),
            s.inhalt))

    def test_die_pruefung_erkennt_ein_bedienelement_das_ueber_den_rand_ragt(self) -> None:
        """Gegenprobe: Ein Knopf, der rechts ueber die Flaeche hinausreicht, wird gemeldet."""
        self._mindestgroesse()
        s = self._seite_zeigen("pkg")
        breite = s.inhalt.winfo_width()
        zu_breit = tk.Frame(s.inhalt, width=breite + 300, height=20)
        zu_breit.place(x=0, y=0)
        self.addCleanup(zu_breit.destroy)
        _WURZEL.update()
        self.assertTrue(self._abgeschnitten([s.inhalt], s.inhalt))


if __name__ == "__main__":
    unittest.main()
