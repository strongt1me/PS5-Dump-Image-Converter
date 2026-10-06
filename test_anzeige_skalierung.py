# -*- coding: utf-8 -*-
"""Skalierung und Auflösung von Hand einstellen (Einstellungen, Abschnitt Anzeige).

Gewünscht am 02.10.2026: Eine Option für Skalierung (Schieberegler) und
Auflösung (Klappliste) der Oberfläche. **Automatisch bleibt die Vorgabe**; nur
wer von Hand umstellt, behält es danach, und ein Knopf stellt alles zurück.

Was hier gesichert wird:

* Die Rechenregeln (``ps5_validator.utils.anzeige_skalierung``) ohne Fenster.
* Das Anwenden beim Start: Ohne Wahl bleibt ``tk scaling`` unberührt, mit Wahl
  wird es **vor dem ersten Bedienelement** gesetzt. An einem wirklich
  gestarteten Programm gemessen (Teilprozess), damit die gemeinsame Tk-Wurzel
  der übrigen Tests ihre Skalierung behält.
* Die Auflösung begrenzt nur die Größe von Fenstern, nie ihren Ort - und ohne
  Wahl verhalten sich alle Stellen wie vorher (Fenster über mehrere Monitore!).
* Das Einstellungsfenster: gespeichert wird erst beim Übernehmen, der Neustart
  hängt an denselben Bedingungen wie beim Design-Wechsel, Zurücksetzen löscht
  beide Werte.
* Die Diagnose misst gegen die Wahl statt gegen den DPI-Wert.
"""
import ast
import json
import math
import os
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as mod  # noqa: E402
from ps5_validator.utils import anzeige_diagnose as ad  # noqa: E402
from ps5_validator.utils import anzeige_skalierung as ask  # noqa: E402

GUI = mod.PS5ConverterGUI
QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Attrappen ohne Fenster
# ---------------------------------------------------------------------------
class _AttrappeTk:
    """Der Tcl-Teil einer Wurzel: kennt nur ``tk scaling``."""

    def __init__(self, skalierung: float) -> None:
        self.skalierung = skalierung
        self.aufrufe: list = []

    def call(self, *args):
        self.aufrufe.append(args)
        if args[:2] == ("tk", "scaling"):
            if len(args) == 3:
                self.skalierung = float(args[2])
                return ""
            return str(self.skalierung)
        raise RuntimeError("unbekannter Aufruf %r" % (args,))


class _AttrappeWurzel:
    def __init__(self, breite: int = 1920, hoehe: int = 1200, skalierung: float = 1.6683) -> None:
        self.tk = _AttrappeTk(skalierung)
        self._breite, self._hoehe = breite, hoehe
        self.geometrien: list = []
        self.attribute: list = []

    def winfo_screenwidth(self) -> int:
        return self._breite

    def winfo_screenheight(self) -> int:
        return self._hoehe

    def geometry(self, wert=None):
        self.geometrien.append(wert)

    def attributes(self, *args):
        self.attribute.append(args)

    def overrideredirect(self, *_args):
        pass


def _oberflaeche(einstellungen: dict | None = None, breite: int = 1920, hoehe: int = 1200,
                 skalierung: float = 1.6683):
    """Eine Oberfläche ohne ``__init__``: nur Wurzel-Attrappe und Einstellungen."""
    gui = GUI.__new__(GUI)
    gui.root = _AttrappeWurzel(breite, hoehe, skalierung)
    speicher = dict(einstellungen or {})
    gui._load_setting = lambda schluessel, vorgabe: speicher.get(schluessel, vorgabe)
    gui._speicher = speicher
    return gui


# ---------------------------------------------------------------------------
# 1. Rechenregeln
# ---------------------------------------------------------------------------
class SkalierungLesenTests(unittest.TestCase):
    def test_gueltige_werte(self):
        for wert, erwartet in ((100, 100), (125, 125), (300, 300), ("150", 150), (149.6, 150),
                               (" 175 ", 175), (200.0, 200)):
            with self.subTest(wert=wert):
                self.assertEqual(ask.skalierung_lesen(wert), erwartet)

    def test_unbrauchbares_bedeutet_automatisch(self):
        """Ein verstümmelter Wert darf die Oberfläche nie unbenutzbar machen."""
        for wert in (None, True, False, "", "abc", [], {}, 99, 99.4, 301, 0, -150, float("nan"),
                     float("inf"), "1e9", object()):
            with self.subTest(wert=repr(wert)):
                self.assertIsNone(ask.skalierung_lesen(wert))

    def test_grenzen_sind_die_des_reglers(self):
        self.assertEqual((ask.SKALIERUNG_MIN, ask.SKALIERUNG_MAX, ask.SKALIERUNG_SCHRITT), (100, 300, 5))


class AufloesungLesenTests(unittest.TestCase):
    def test_schreibweisen(self):
        for wert in ("1920x1080", " 1920 x 1080 ", "1920X1080", "1920×1080", "1920 × 1080"):
            with self.subTest(wert=wert):
                self.assertEqual(ask.aufloesung_lesen(wert), (1920, 1080))

    def test_unbrauchbares_bedeutet_automatisch(self):
        for wert in (None, 1920, "", "auto", "1920", "1920x", "x1080", "1920x1080x3", "abcxdef",
                     "10x10", "99999x99999", "1920*1080", ("1920", "1080"), 1920.5):
            with self.subTest(wert=repr(wert)):
                self.assertIsNone(ask.aufloesung_lesen(wert))

    def test_speichern_und_anzeigen_gehen_hin_und_zurueck(self):
        self.assertEqual(ask.aufloesung_text(2560, 1440), "2560x1440")
        self.assertEqual(ask.aufloesung_anzeige(2560, 1440), "2560 × 1440")
        self.assertEqual(ask.aufloesung_lesen(ask.aufloesung_text(2560, 1440)), (2560, 1440))
        self.assertEqual(ask.aufloesung_lesen(ask.aufloesung_anzeige(2560, 1440)), (2560, 1440))

    def test_liste_enthaelt_erkannte_und_gewaehlte(self):
        liste = ask.aufloesungen_anbieten((1920, 1111), (1234, 987))
        self.assertIn((1920, 1111), liste)
        self.assertIn((1234, 987), liste)
        self.assertIn((1920, 1080), liste)
        self.assertEqual(len(liste), len(set(liste)))

    def test_liste_ist_nach_flaeche_sortiert_und_ohne_doppelte(self):
        liste = ask.aufloesungen_anbieten((1920, 1080), (1920, 1080))
        flaechen = [b * h for b, h in liste]
        self.assertEqual(flaechen, sorted(flaechen))
        self.assertEqual(liste.count((1920, 1080)), 1)

    def test_liste_ohne_erkannte_gibt_die_gaengigen(self):
        self.assertEqual(ask.aufloesungen_anbieten(None), sorted(ask.AUFLOESUNGEN, key=lambda a: (a[0] * a[1], a[0])))

    def test_gaengige_liegen_nicht_unter_der_mindestgroesse(self):
        """Darunter passt die Mindestgroesse des Hauptfensters nicht mehr hinein."""
        for breite, hoehe in ask.AUFLOESUNGEN:
            with self.subTest(aufloesung=(breite, hoehe)):
                self.assertGreaterEqual(breite, 1280)
                self.assertGreaterEqual(hoehe, 720)


class UmrechnungTests(unittest.TestCase):
    #: Gemessen am 02.10.2026 an Minimalfenstern: Tk rundet die Bildschirm-
    #: millimeter auf ganze Zahlen, daher 2,0 -> 1,998 und 2,3333 -> 2,3356.
    GEMESSEN = ((1.3333, 100), (1.6683, 125), (1.998, 150), (2.3356, 175), (2.6667, 200),
                (3.3366, 250), (4.0079, 300))

    def test_prozent_zu_tk(self):
        self.assertAlmostEqual(ask.tk_skalierung(100), 96 / 72, places=6)
        self.assertAlmostEqual(ask.tk_skalierung(125), 120 / 72, places=6)
        self.assertAlmostEqual(ask.tk_skalierung(200), 192 / 72, places=6)

    def test_gemessene_tk_werte_ergeben_die_ganzen_prozent(self):
        for skalierung, prozent in self.GEMESSEN:
            with self.subTest(tk=skalierung):
                self.assertEqual(ask.prozent_aus_tk(skalierung), prozent)

    def test_hin_und_zurueck(self):
        for prozent in range(100, 301, 5):
            with self.subTest(prozent=prozent):
                self.assertEqual(ask.prozent_aus_tk(ask.tk_skalierung(prozent)), prozent)

    def test_krumme_windows_werte_bleiben_krumm(self):
        """Windows erlaubt auch 126 % oder 112 % - die Rundung auf Fuenferschritte darf sie nicht schlucken."""
        for prozent in (101, 107, 112, 118, 124, 126, 133, 141, 163):
            with self.subTest(prozent=prozent):
                self.assertEqual(ask.prozent_aus_tk(prozent / 75.0), prozent)

    def test_tk_rundung_um_ein_halbes_prozent_wird_geglaettet(self):
        """Tk rundet die Bildschirmmillimeter: 300 % wurde als 4,0079 gemessen (= 300,6 %)."""
        self.assertEqual(ask.prozent_aus_tk(4.0079), 300)
        self.assertEqual(ask.prozent_aus_tk(1.998), 150)
        self.assertEqual(ask.prozent_aus_tk(2.3356), 175)

    def test_system_prozent(self):
        self.assertEqual(ask.system_prozent(False, 1.6683), 125)
        self.assertEqual(ask.system_prozent(False, 1.3333), 100)
        self.assertEqual(ask.system_prozent(True, 1.0), 125)       # macOS: der Eichpunkt
        for unbrauchbar in (0.0, -1.0, None):
            with self.subTest(wert=unbrauchbar):
                self.assertEqual(ask.system_prozent(False, unbrauchbar), 100)

    def test_mac_faktor(self):
        self.assertEqual(ask.mac_faktor(1.65, None), 1.65)
        self.assertAlmostEqual(ask.mac_faktor(1.65, 125), 1.65)
        self.assertAlmostEqual(ask.mac_faktor(1.65, 150), 1.65 * 1.2)
        self.assertAlmostEqual(ask.mac_faktor(1.65, 100), 1.65 * 0.8)
        self.assertEqual(ask.mac_faktor(2.5, 300), 4.0)             # wie die Grenze der Anhebung sonst

    def test_auf_schritt(self):
        for wert, erwartet in ((137, 135), (138, 140), (100, 100), (50, 100), (999, 300), (302.4, 300),
                               (122.4, 120), (122.6, 125)):
            with self.subTest(wert=wert):
                self.assertEqual(ask.auf_schritt(wert), erwartet)
        self.assertEqual(ask.auf_schritt(float("nan")), 100)


class BildschirmRegelTests(unittest.TestCase):
    ECHT = (1920, 1200)

    def test_ohne_wahl_ist_alles_der_echte_schirm(self):
        self.assertEqual(ask.bildschirm_wirksam(self.ECHT, None), self.ECHT)
        self.assertEqual(ask.fenster_obergrenze(self.ECHT, None), self.ECHT)
        self.assertFalse(ask.ist_verkleinert(self.ECHT, None))

    def test_kleinere_wahl(self):
        wahl = (1366, 768)
        self.assertEqual(ask.bildschirm_wirksam(self.ECHT, wahl), wahl)
        self.assertEqual(ask.fenster_obergrenze(self.ECHT, wahl), wahl)
        self.assertTrue(ask.ist_verkleinert(self.ECHT, wahl))

    def test_groessere_wahl_macht_keine_fenster_groesser_als_der_schirm(self):
        wahl = (3840, 2160)
        self.assertEqual(ask.bildschirm_wirksam(self.ECHT, wahl), wahl)        # fuer Bilder zaehlt sie
        self.assertEqual(ask.fenster_obergrenze(self.ECHT, wahl), self.ECHT)   # fuer Fenster nie
        self.assertFalse(ask.ist_verkleinert(self.ECHT, wahl))

    def test_nur_eine_richtung_kleiner(self):
        """2560x1080 auf 1920x1200: breiter, aber niedriger - je Richtung der kleinere Wert."""
        wahl = (2560, 1080)
        self.assertEqual(ask.fenster_obergrenze(self.ECHT, wahl), (1920, 1080))
        self.assertTrue(ask.ist_verkleinert(self.ECHT, wahl))

    def test_gleiche_wahl_aendert_nichts(self):
        self.assertFalse(ask.ist_verkleinert(self.ECHT, self.ECHT))

    def test_maximiert_groesse_zieht_den_rand_ab(self):
        self.assertEqual(ask.maximiert_groesse((1920, 1080)),
                         (1920 - ask.FENSTER_RAND_BREITE, 1080 - ask.FENSTER_RAND_HOEHE))
        self.assertEqual(ask.maximiert_groesse((5, 5)), (1, 1))


class ObergrenzeTests(unittest.TestCase):
    """Wie weit der Regler reicht: bis die Oberfläche noch in die Bildschirmbreite passt."""

    #: (Fensterbreite, Mindestbreite) -> Grenze; die Mindestbreite 1245 ist auf 125 % geschrieben.
    def test_gemessene_schirmbreiten(self):
        for breite, erwartet in ((1280, 125), (1366, 135), (1600, 160), (1920, 190), (2560, 255),
                                 (3440, 300), (3840, 300)):
            with self.subTest(breite=breite):
                self.assertEqual(ask.skalierung_obergrenze(breite, 1245), erwartet)

    def test_nie_unter_dem_minimum(self):
        self.assertEqual(ask.skalierung_obergrenze(800, 1245), 100)
        self.assertEqual(ask.skalierung_obergrenze(1, 1245), 100)

    def test_der_systemwert_bleibt_erreichbar(self):
        """Windows auf 150 % und ein 1366er Schirm: Die Grenze waere 135, der Regler muss bis 150 gehen."""
        self.assertEqual(ask.skalierung_obergrenze(1366, 1245, 150), 150)
        self.assertEqual(ask.skalierung_obergrenze(1920, 1245, 150), 190)    # darunter bleibt es bei der Grenze
        self.assertEqual(ask.skalierung_obergrenze(1920, 1245, 400), 300)    # nie ueber das Maximum

    def test_unsinnige_mindestbreite_wirft_nicht(self):
        self.assertEqual(ask.skalierung_obergrenze(1920, 0), 300)

    def test_die_breite_waechst_im_gleichen_verhaeltnis(self):
        """Der Grund der Regel, als Zahlen: gewuenschte Breite je Skalierung (gemessen 02.10.2026)."""
        gemessen = ((100, 776), (125, 966), (150, 1152), (200, 1532), (250, 1912), (300, 2292))
        je_prozent = [breite / prozent for prozent, breite in gemessen]
        self.assertLess(max(je_prozent) - min(je_prozent), 0.5 * min(je_prozent))   # nahezu proportional
        for (p1, b1), (p2, b2) in zip(gemessen, gemessen[1:]):
            with self.subTest(von=p1, bis=p2):
                self.assertAlmostEqual(b2 / b1, p2 / p1, delta=0.05 * p2 / p1)


# ---------------------------------------------------------------------------
# 2. Anwenden beim Start
# ---------------------------------------------------------------------------
class AnwendenTests(unittest.TestCase):
    """``_anzeige_einstellungen_anwenden`` an einer Oberfläche mit Wurzel-Attrappe."""

    def _anwenden(self, einstellungen=None, **kwargs):
        gui = _oberflaeche(einstellungen, **kwargs)
        gui._anzeige_einstellungen_anwenden()
        return gui

    def _gesetzt(self, gui):
        return [a for a in gui.root.tk.aufrufe if len(a) == 3]

    def test_ohne_wahl_bleibt_tk_scaling_unberuehrt(self):
        gui = self._anwenden()
        self.assertEqual(self._gesetzt(gui), [])
        self.assertEqual(gui.root.tk.skalierung, 1.6683)
        self.assertIsNone(gui._skalierung_manuell)
        self.assertIsNone(gui._aufloesung_manuell)
        self.assertEqual(gui._skalierung_system, 125)

    def test_mit_wahl_wird_tk_scaling_gesetzt(self):
        gui = self._anwenden({"ui_skalierung": 150})
        self.assertEqual(self._gesetzt(gui), [("tk", "scaling", ask.tk_skalierung(150))])
        self.assertEqual(gui._skalierung_manuell, 150)
        self.assertEqual(gui._skalierung_system, 125)     # das System, vor dem Eingriff gemessen

    def test_system_wird_vor_dem_eingriff_gemessen(self):
        gui = self._anwenden({"ui_skalierung": 200}, skalierung=1.3333)
        self.assertEqual(gui._skalierung_system, 100)
        self.assertEqual(gui._skalierung_manuell, 200)

    def test_unbrauchbare_wahl_bedeutet_automatisch(self):
        for wert in (99, 301, "abc", True, None, [], 0):
            with self.subTest(wert=repr(wert)):
                gui = self._anwenden({"ui_skalierung": wert})
                self.assertEqual(self._gesetzt(gui), [])
                self.assertIsNone(gui._skalierung_manuell)

    def test_aufloesung_ohne_skalierung(self):
        gui = self._anwenden({"ui_aufloesung": "1366x768"})
        self.assertEqual(self._gesetzt(gui), [])
        self.assertEqual(gui._aufloesung_manuell, (1366, 768))
        self.assertIsNone(gui._skalierung_manuell)

    def test_unbrauchbare_aufloesung_bedeutet_automatisch(self):
        for wert in ("auto", "abc", 1920, "10x10", None):
            with self.subTest(wert=repr(wert)):
                self.assertIsNone(self._anwenden({"ui_aufloesung": wert})._aufloesung_manuell)

    def test_beides_zugleich(self):
        gui = self._anwenden({"ui_skalierung": 175, "ui_aufloesung": "2560x1440"})
        self.assertEqual((gui._skalierung_manuell, gui._aufloesung_manuell), (175, (2560, 1440)))

    def test_unter_macos_wirkt_es_ueber_die_schriftanhebung(self):
        with mock.patch.object(mod, "IST_MACOS", True):
            gui = self._anwenden({"ui_skalierung": 150})
        self.assertEqual(self._gesetzt(gui), [])          # tk scaling setzt hier _macos_schrift_skalieren
        self.assertEqual(gui._skalierung_manuell, 150)
        self.assertEqual(gui._skalierung_system, 125)

    def test_ein_fehler_beim_setzen_verhindert_den_start_nicht(self):
        gui = _oberflaeche({"ui_skalierung": 150})
        gui.root.tk.call = mock.Mock(side_effect=[str(1.6683), RuntimeError("kaputt")])
        gui._anzeige_einstellungen_anwenden()           # darf nicht werfen
        self.assertEqual(gui._skalierung_manuell, 150)

    def test_klassenvorgaben_fuer_eine_oberflaeche_ohne_init(self):
        gui = GUI.__new__(GUI)
        self.assertEqual((gui._skalierung_system, gui._skalierung_manuell, gui._aufloesung_manuell),
                         (100, None, None))


class MacosTests(unittest.TestCase):
    """Die Schriftanhebung unter macOS folgt der Wahl - in ``pt()`` und in ``tk scaling`` gleich."""

    def _schriftfaktor(self, einstellungen: dict) -> float:
        with mock.patch.object(mod, "IST_MACOS", True), \
                mock.patch.object(mod.einstellungen, "lesen",
                                  side_effect=lambda schluessel, vorgabe=None, **_k: einstellungen.get(schluessel, vorgabe)):
            return mod._macos_schriftfaktor()

    def test_ohne_wahl_wie_bisher(self):
        self.assertEqual(self._schriftfaktor({}), mod.MACOS_SCHRIFT_SKALIERUNG)
        self.assertEqual(self._schriftfaktor({"macos_font_scaling": 2.0}), 2.0)

    def test_mit_wahl_im_verhaeltnis_zu_125(self):
        basis = mod.MACOS_SCHRIFT_SKALIERUNG
        self.assertAlmostEqual(self._schriftfaktor({"ui_skalierung": 150}), basis * 1.2)
        self.assertAlmostEqual(self._schriftfaktor({"ui_skalierung": 125}), basis)
        self.assertAlmostEqual(self._schriftfaktor({"ui_skalierung": 100}), basis * 0.8)

    def test_wahl_und_eigener_faktor_vervielfachen_sich(self):
        self.assertAlmostEqual(self._schriftfaktor({"macos_font_scaling": 2.0, "ui_skalierung": 150}), 2.4)

    def test_unbrauchbare_wahl_wird_ignoriert(self):
        self.assertEqual(self._schriftfaktor({"ui_skalierung": "abc"}), mod.MACOS_SCHRIFT_SKALIERUNG)

    def test_ausserhalb_von_macos_immer_eins(self):
        with mock.patch.object(mod, "IST_MACOS", False):
            self.assertEqual(mod._macos_schriftfaktor(), 1.0)

    def test_tk_scaling_bekommt_denselben_faktor(self):
        gui = _oberflaeche({"ui_skalierung": 150}, skalierung=1.0)
        with mock.patch.object(mod, "IST_MACOS", True):
            gui._macos_schrift_skalieren()
        self.assertAlmostEqual(gui.root.tk.skalierung, 1.0 * mod.MACOS_SCHRIFT_SKALIERUNG * 1.2)


# ---------------------------------------------------------------------------
# 3. Bildschirmgroessen
# ---------------------------------------------------------------------------
class BildschirmTests(unittest.TestCase):
    def test_ohne_wahl_ist_alles_der_erkannte_schirm(self):
        gui = _oberflaeche()
        self.assertEqual(gui._bildschirm_erkannt(), (1920, 1200))
        self.assertEqual(gui._bildschirm_wirksam(), (1920, 1200))
        self.assertEqual(gui._bildschirm_fuer_fenster(), (1920, 1200))
        self.assertFalse(gui._aufloesung_verkleinert())

    def test_kleinere_wahl(self):
        gui = _oberflaeche()
        gui._aufloesung_manuell = (1366, 768)
        self.assertEqual(gui._bildschirm_wirksam(), (1366, 768))
        self.assertEqual(gui._bildschirm_fuer_fenster(), (1366, 768))
        self.assertTrue(gui._aufloesung_verkleinert())

    def test_groessere_wahl(self):
        gui = _oberflaeche()
        gui._aufloesung_manuell = (3840, 2160)
        self.assertEqual(gui._bildschirm_wirksam(), (3840, 2160))
        self.assertEqual(gui._bildschirm_fuer_fenster(), (1920, 1200))
        self.assertFalse(gui._aufloesung_verkleinert())

    def test_wurzel_ohne_antwort_gibt_die_rueckfallgroesse(self):
        gui = GUI.__new__(GUI)
        gui.root = mock.Mock()
        gui.root.winfo_screenwidth.side_effect = tk.TclError("weg")
        self.assertEqual(gui._bildschirm_erkannt(), (1920, 1080))

    def test_bildempfehlung_richtet_sich_nach_der_wirksamen_groesse(self):
        """Das Hauptbild liegt nur rechts neben der Seitenleiste: Bildschirmbreite minus Leiste, aufgerundet.

        Hinweis vom 05.10.2026 ("zwei Hintergrundbilder, getrennt ... jetzt ist es ja 1920x1200, das wuerde
        aber nicht stimmen"): Gemessen an einem 1920 x 1200-Schirm bei 125 % ist die Leiste 493 Pixel breit,
        die Flaeche des Hauptbilds 1427 - die Einstellungen nannten die ganze Bildschirmbreite.
        """
        gui = _oberflaeche()
        gui.sidebar = mock.Mock()
        gui.sidebar.winfo_width.return_value = 493
        # Ohne Wahl rechnet das System: maximiertes Fenster 1920 x 1111 (gemessen), genaue Zahlen.
        with mock.patch.object(mod, "_system_maximierte_flaeche", return_value=(1920, 1111)):
            self.assertEqual(gui._hintergrund_sollmasse(), (1427, 1111, 493))
        # Von Hand gewaehlte Aufloesung: Bildschirm minus feste Reserve fuer Rahmen und Taskleiste.
        gui._aufloesung_manuell = (2560, 1440)
        rand_b, rand_h = ask.FENSTER_RAND_BREITE, ask.FENSTER_RAND_HOEHE
        self.assertEqual(gui._hintergrund_sollmasse(), (2560 - rand_b - 493, 1440 - rand_h, 493))
        gui._aufloesung_manuell = (1366, 768)
        self.assertEqual(gui._hintergrund_sollmasse(), (1366 - rand_b - 493, 768 - rand_h, 493))

    def test_bildempfehlung_ohne_systemwert_nimmt_die_reserve(self):
        """Wo das System die maximierte Flaeche nicht nennt (Linux, macOS), gilt die feste Reserve."""
        gui = _oberflaeche()
        gui.sidebar = mock.Mock()
        gui.sidebar.winfo_width.return_value = 493
        with mock.patch.object(mod, "_system_maximierte_flaeche", return_value=None):
            self.assertEqual(gui._hintergrund_sollmasse(),
                             (1920 - ask.FENSTER_RAND_BREITE - 493, 1200 - ask.FENSTER_RAND_HOEHE, 493))

    def test_bildempfehlung_bleibt_positiv_bei_schmalem_schirm(self):
        """Eine Leiste, die breiter ist als der angenommene Schirm, ergibt nie eine Breite unter 1 Pixel."""
        gui = _oberflaeche()
        gui.sidebar = mock.Mock()
        gui.sidebar.winfo_width.return_value = 700
        gui._aufloesung_manuell = (640, 480)
        breite, hoehe, leiste = gui._hintergrund_sollmasse()
        self.assertEqual(1, breite)
        self.assertEqual((hoehe, leiste), (480 - ask.FENSTER_RAND_HOEHE, 700))

    def test_seitenleiste_pixel_bevorzugt_die_spaltenbreite(self):
        """Gemessen, nicht angenommen: erst die Spalte des Aufbaus, dann die gezeichnete Breite, dann die Vorgabe."""
        gui = _oberflaeche()
        gui.sidebar = mock.Mock()
        gui.sidebar.winfo_width.return_value = 480
        self.assertEqual(480, gui._seitenleiste_pixel())
        gui._seitenleiste_breite = 493
        self.assertEqual(493, gui._seitenleiste_pixel())
        del gui._seitenleiste_breite
        gui.sidebar.winfo_width.return_value = 1                # noch nicht gezeichnet
        self.assertGreaterEqual(gui._seitenleiste_pixel(), 320)

    def test_hintergrund_masse_rechnet_fenster_minus_leiste(self):
        """Die reine Rechnung: Hauptbild rechts neben der Leiste, beide so hoch wie das Fenster."""
        self.assertEqual((1427, 1111, 493), ask.hintergrund_masse((1920, 1111), 493))
        self.assertEqual((1, 1, 1), ask.hintergrund_masse((0, 0), 0))
        self.assertEqual((1, 600, 700), ask.hintergrund_masse((640, 600), 700))


class FensterRestaurierenTests(unittest.TestCase):
    """``_fenstergeometrie_wiederherstellen``: Die Wahl begrenzt die Größe, nie den Ort."""

    DESKTOP = (0, 0, 1920, 1200)

    def _gui(self, einstellungen=None, aufloesung=None, desktop=None, breite=1920, hoehe=1200):
        gui = _oberflaeche(einstellungen, breite, hoehe)
        gui._aufloesung_manuell = aufloesung
        gui._arbeitsflaeche = lambda: desktop or self.DESKTOP
        gui._maximiert = []
        gui._maximieren_versuchen = lambda: gui._maximiert.append(True)
        return gui

    def test_ohne_wahl_und_ohne_gemerktes_wie_vorher(self):
        gui = self._gui()
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui.root.geometrien, ["%dx%d" % (mod.WINDOW_WIDTH, mod.WINDOW_HEIGHT)])
        self.assertEqual(gui._maximiert, [True])

    def test_ohne_wahl_mit_gemerktem_wie_vorher(self):
        gui = self._gui({"window_geometry": "1500x900+50+40", "window_maximized": True})
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui.root.geometrien, ["1500x900+50+40"])
        self.assertEqual(gui._maximiert, [True])

    def test_fenster_ueber_zwei_monitore_wird_ohne_wahl_nicht_beschnitten(self):
        """Der Schutz vor der naheliegenden Verallgemeinerung: Der erste Schirm ist keine Grenze.

        Ohne Wahl begrenzt allein die Arbeitsflaeche aller Monitore - sonst bekaeme, wer sein
        Fenster ueber zwei Schirme zieht, bei jedem Start nur den ersten.
        """
        gui = self._gui({"window_geometry": "3000x1000+0+0"}, desktop=(0, 0, 3840, 1200))
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui.root.geometrien, ["3000x1000+0+0"])

    def test_kleinere_wahl_ohne_gemerktes_stellt_ein_fenster_in_der_groesse_hin(self):
        gui = self._gui(aufloesung=(1600, 900))
        gui._fenstergeometrie_wiederherstellen()
        breite, hoehe = ask.maximiert_groesse((1600, 900))
        self.assertEqual(len(gui.root.geometrien), 1)
        self.assertEqual(gui.root.geometrien[0],
                         "%dx%d+%d+%d" % (breite, hoehe, (1920 - breite) // 2, (1200 - hoehe) // 2))
        self.assertEqual(gui._maximiert, [], "maximiert wuerde den echten Schirm fuellen")

    def test_kleinere_wahl_geht_nie_unter_die_mindestgroesse(self):
        gui = self._gui(aufloesung=(1280, 720))
        gui._fenstergeometrie_wiederherstellen()
        treffer = gui.root.geometrien[0]
        breite, hoehe = (int(x) for x in treffer.split("+")[0].split("x"))
        self.assertGreaterEqual(breite, mod.WINDOW_MIN_WIDTH)
        self.assertGreaterEqual(hoehe, mod.WINDOW_MIN_HEIGHT)

    def test_kleinere_wahl_begrenzt_gemerkte_groesse(self):
        gui = self._gui({"window_geometry": "1800x1000+10+10"}, aufloesung=(1600, 900))
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui.root.geometrien, ["1600x900+10+10"])
        self.assertEqual(gui._maximiert, [])

    def test_kleinere_wahl_ersetzt_maximieren(self):
        gui = self._gui({"window_geometry": "1500x900+50+40", "window_maximized": True}, aufloesung=(1600, 900))
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui._maximiert, [])
        self.assertEqual(len(gui.root.geometrien), 2)           # gemerkte Groesse, dann die nachgestellte
        breite, hoehe = ask.maximiert_groesse((1600, 900))
        self.assertTrue(gui.root.geometrien[1].startswith("%dx%d+" % (breite, hoehe)))

    def test_groessere_wahl_aendert_nichts(self):
        gui = self._gui({"window_geometry": "1800x1000+10+10", "window_maximized": True}, aufloesung=(3840, 2160))
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui.root.geometrien, ["1800x1000+10+10"])
        self.assertEqual(gui._maximiert, [True])

    def test_gemerkter_ort_bleibt_der_ort(self):
        """Die Wahl begrenzt die Groesse - der gemerkte Ort bleibt, wo er ist."""
        gui = self._gui({"window_geometry": "1400x800+300+200"}, aufloesung=(1600, 900))
        gui._fenstergeometrie_wiederherstellen()
        self.assertEqual(gui.root.geometrien, ["1400x800+300+200"])


class FensterMerkenTests(unittest.TestCase):
    """Eine Nachstellung (kleinere Auflösung gewählt) überschreibt das gemerkte Fenster nicht.

    Sonst käme das Fenster nach „Zurücksetzen“ nicht mehr maximiert hoch, sondern in der
    verkleinerten Form der Nachstellung.
    """

    def _gui(self, aufloesung=None, zustand="normal", geometrie="1350x700+294+288"):
        gui = _oberflaeche()
        gui._aufloesung_manuell = aufloesung
        gui.root.state = lambda: zustand
        gui.root.winfo_geometry = lambda: geometrie
        gui._geschrieben = {}
        gui._save_setting = lambda schluessel, wert: gui._geschrieben.__setitem__(schluessel, wert)
        return gui

    def test_ohne_wahl_wird_wie_immer_gemerkt(self):
        gui = self._gui()
        gui._fenstergeometrie_merken()
        self.assertEqual(gui._geschrieben, {"window_maximized": False, "window_geometry": "1350x700+294+288"})

    def test_maximiert_merkt_nur_den_zustand(self):
        gui = self._gui(zustand="zoomed", geometrie="1920x1111+0+0")
        gui._fenstergeometrie_merken()
        self.assertEqual(gui._geschrieben, {"window_maximized": True})

    def test_kleinere_wahl_merkt_nichts(self):
        gui = self._gui(aufloesung=(1366, 768))
        gui._fenstergeometrie_merken()
        self.assertEqual(gui._geschrieben, {})

    def test_groessere_wahl_merkt_wie_immer(self):
        """Eine groessere Aufloesung stellt nichts nach - das Fenster ist ein ganz gewoehnliches."""
        gui = self._gui(aufloesung=(3840, 2160))
        gui._fenstergeometrie_merken()
        self.assertEqual(set(gui._geschrieben), {"window_maximized", "window_geometry"})


class FensterSizingTests(unittest.TestCase):
    def _gui(self, aufloesung=None):
        gui = _oberflaeche()
        gui._aufloesung_manuell = aufloesung
        gui._sync_docked_windows = lambda: None
        gui.is_fullscreen = True
        return gui

    def _geometrie(self, gui):
        text = gui.root.geometrien[-1]
        groesse, x, y = text.split("+")
        breite, hoehe = (int(v) for v in groesse.split("x"))
        return breite, hoehe, int(x), int(y)

    def test_zentrieren_ohne_wahl_wie_vorher(self):
        gui = self._gui()
        gui._center_window_safe()
        breite, hoehe, x, y = self._geometrie(gui)
        self.assertEqual(breite, max(mod.WINDOW_MIN_WIDTH, int(1920 * 0.70)))
        self.assertEqual(hoehe, max(mod.WINDOW_MIN_HEIGHT, min(int(1200 * 0.60), 1200 - 160)))
        self.assertEqual(x, (1920 - breite) // 2)

    def test_zentrieren_mit_kleinerer_wahl_misst_die_groesse_dort_und_die_lage_am_echten_schirm(self):
        gui = self._gui((1600, 900))
        gui._center_window_safe()
        breite, hoehe, x, y = self._geometrie(gui)
        self.assertEqual(breite, max(mod.WINDOW_MIN_WIDTH, int(1600 * 0.70)))
        self.assertEqual(x, (1920 - breite) // 2, "mittig auf dem echten Schirm")

    def test_unterer_rand_bleibt_sichtbar(self):
        gui = self._gui((1600, 900))
        gui._center_window_safe()
        _breite, hoehe, _x, y = self._geometrie(gui)
        self.assertLessEqual(y + hoehe, 1200 - 80 + 1)


# ---------------------------------------------------------------------------
# 4. Wächter über den Quelltext
# ---------------------------------------------------------------------------
class QuelltextTests(unittest.TestCase):
    #: Funktionen, die den rohen Bildschirm lesen dürfen: Sie *platzieren* (zentrieren, zurückholen,
    #: Vollbild) oder *messen* ihn. Eine Stelle, die eine **Größe** daran bemisst, nimmt
    #: ``_bildschirm_fuer_fenster`` (Fenster) oder ``_bildschirm_wirksam`` (Bilder) - sonst ignoriert
    #: sie die gewählte Auflösung. Eine neue Stelle muss hier stehen und begründet sein.
    ROHER_ZUGRIFF_ERLAUBT = {
        "_arbeitsflaeche": "Arbeitsflaeche aller Monitore (Messung)",
        "_bildschirm_erkannt": "die eine Quelle fuer den erkannten Schirm",
        "_build_info_popup": "zentriert ein festes Fenster",
        "_center_window_safe": "Lage am echten Schirm (die Groesse nimmt _bildschirm_fuer_fenster)",
        "_diagnose_anzeige": "Bericht nennt den echten Schirm",
        "_diagnose_pruefen": "Messwert fuer die Pruefung",
        "_fenstergeometrie_wiederherstellen": "holt ein verlorenes Fenster auf den ersten Schirm",
        "_go_fullscreen": "Vollbild fuellt den echten Schirm",
        "_mode_ampr_manager._show_ampr_dialog": "zentriert",
        "_show_ampr_ftp_picker": "zentriert",
        "_show_credits": "zentriert (die Groesse nimmt _bildschirm_fuer_fenster)",
        "_show_resources": "zentriert (die Groesse nimmt _bildschirm_fuer_fenster)",
        "_show_splash": "zentriert",
    }

    @classmethod
    def setUpClass(cls):
        cls.baum = ast.parse(QUELLE)

    def _roher_zugriff(self) -> set:
        gefunden: set = set()

        class Besucher(ast.NodeVisitor):
            def __init__(self):
                self.stapel: list = []

            def _funktion(self, knoten):
                self.stapel.append(knoten.name)
                self.generic_visit(knoten)
                self.stapel.pop()

            visit_FunctionDef = _funktion
            visit_AsyncFunctionDef = _funktion

            def visit_Call(self, knoten):
                f = knoten.func
                if isinstance(f, ast.Attribute) and f.attr in (
                        "winfo_screenwidth", "winfo_screenheight", "winfo_vrootwidth", "winfo_vrootheight"):
                    gefunden.add(".".join(self.stapel) or "<Modul>")
                self.generic_visit(knoten)

        Besucher().visit(self.baum)
        return gefunden

    def test_nur_erlaubte_stellen_lesen_den_rohen_bildschirm(self):
        gefunden = self._roher_zugriff()
        self.assertEqual(sorted(gefunden - set(self.ROHER_ZUGRIFF_ERLAUBT)), [],
                         "Neue Stelle liest den rohen Bildschirm: Groessen bitte ueber "
                         "_bildschirm_fuer_fenster / _bildschirm_wirksam, Lagen in ROHER_ZUGRIFF_ERLAUBT begruenden")

    def test_die_erlaubnisliste_ist_nicht_veraltet(self):
        self.assertEqual(sorted(set(self.ROHER_ZUGRIFF_ERLAUBT) - self._roher_zugriff()), [])

    def test_init_wendet_die_wahl_vor_dem_ersten_bedienelement_an(self):
        beginn = QUELLE.index("    def __init__(self, root: tk.Tk) -> None:")
        rumpf = QUELLE[beginn:beginn + 6000]
        mac = rumpf.index("self._macos_schrift_skalieren()")
        wahl = rumpf.index("self._anzeige_einstellungen_anwenden()")
        weiter = rumpf.index("self._macos_translokation_melden()")
        self.assertLess(mac, wahl)
        self.assertLess(wahl, weiter)
        # Und vor dem ersten Bedienelement: Tk rechnet Schriften beim Anlegen in Pixel um.
        for widget in ("tk.Frame(", "tk.Label(", "ttk.", "tk.Canvas(", "tk.Button(", "tk.StringVar("):
            self.assertNotIn(widget, rumpf[:wahl], widget)

    def test_schriftfaktor_und_tk_scaling_rechnen_gleich(self):
        beginn = QUELLE.index("def _macos_schriftfaktor()")
        self.assertIn("anzeige_skalierung.mac_faktor(", QUELLE[beginn:beginn + 2500])
        beginn = QUELLE.index("    def _macos_schrift_skalieren(self)")
        self.assertIn("anzeige_skalierung.mac_faktor(", QUELLE[beginn:beginn + 3500])

    def test_einstellungsfenster_baut_den_abschnitt_zuerst(self):
        beginn = QUELLE.index("    def _show_settings_dialog(self)")
        rumpf = QUELLE[beginn:beginn + 6000]
        self.assertLess(rumpf.index("self._einstellungen_anzeige_abschnitt(dlg, body)"),
                        rumpf.index("settings_dialog.background_section_label"))

    def test_bildempfehlung_liest_die_wirksame_groesse(self):
        """Die Empfehlung folgt der angenommenen Aufloesung: ueber ``_fenster_maximal`` - nie am echten Schirm."""
        beginn = QUELLE.index("    def _hintergrund_sollmasse(self)")
        rumpf = QUELLE[beginn:beginn + 2500]
        self.assertIn("self._fenster_maximal()", rumpf)
        self.assertIn("self._seitenleiste_pixel()", rumpf)
        self.assertNotIn("winfo_screenwidth", rumpf)
        beginn = QUELLE.index("    def _fenster_maximal(self)")
        rumpf = QUELLE[beginn:beginn + 2500]
        self.assertIn("self._bildschirm_wirksam()", rumpf)
        self.assertIn("_aufloesung_manuell", rumpf)
        self.assertNotIn("winfo_screenwidth", rumpf)

    def test_handbuch_beschreibt_den_abschnitt_mit_den_worten_der_oberflaeche(self):
        """Handbuch und Fenster sagen dasselbe: Titel, Beschriftungen, Knoepfe und die Grenzen des Reglers."""
        from ps5_validator.utils import i18n
        html = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        for schluessel in ("settings_dialog.anzeige_section", "settings_dialog.anzeige_skalierung",
                           "settings_dialog.anzeige_aufloesung", "settings_dialog.anzeige_uebernehmen",
                           "settings_dialog.anzeige_zuruecksetzen"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(i18n.STRINGS[schluessel]["de"], html)
        for breite in (1920, 1366):
            with self.subTest(breite=breite):
                grenze = ask.skalierung_obergrenze(breite, mod.WINDOW_MIN_WIDTH)
                self.assertIn("bei %d Pixeln Breite bis %d %%" % (breite, grenze)
                              if breite == 1920 else "bei %d Pixeln bis %d %%" % (breite, grenze), html)
        self.assertIn("Abschnitt 14.3", html)
        self.assertIn('<h3>14.3 Skalierung und Auflösung von Hand einstellen</h3>', html)

    def test_alle_texte_haben_deutsch_und_englisch(self):
        from ps5_validator.utils import i18n
        schluessel = sorted(k for k in i18n.STRINGS if k.startswith("settings_dialog.anzeige_"))
        self.assertGreaterEqual(len(schluessel), 15)
        for name in schluessel:
            with self.subTest(schluessel=name):
                self.assertTrue(i18n.STRINGS[name]["de"].strip())
                self.assertTrue(i18n.STRINGS[name]["en"].strip())
                # Die Platzhalter beider Sprachen stimmen ueberein.
                import string
                felder = lambda text: {f[1] for f in string.Formatter().parse(text) if f[1]}   # noqa: E731
                self.assertEqual(felder(i18n.STRINGS[name]["de"]), felder(i18n.STRINGS[name]["en"]))


# ---------------------------------------------------------------------------
# 5. Diagnose
# ---------------------------------------------------------------------------
class DiagnoseTests(unittest.TestCase):
    def _lage(self, **kw):
        vorgabe = dict(plattform="win32", dpi_bewusstsein=2, fenster_dpi=120, tk_skalierung=1.6683,
                       schrifthoehe_px=20, schriftgroesse_pt=9)
        vorgabe.update(kw)
        return ad.Skalierungslage(**vorgabe)

    def _kennungen(self, befunde):
        return sorted(b.kennung for b in befunde)

    def test_von_hand_gestellt_ist_ein_hinweis_und_kein_mangel(self):
        befunde = ad.pruefe_skalierung(self._lage(
            tk_skalierung=1.998, manuell_prozent=150, system_prozent=125, soll_skalierung=2.0))
        self.assertEqual(self._kennungen(befunde), ["skalierung_von_hand"])
        self.assertEqual(befunde[0].schwere, ad.HINWEIS)
        self.assertTrue(ad.Pruefergebnis(befunde).sauber)
        self.assertIn("150 %", befunde[0].text)
        self.assertIn("125 %", befunde[0].text)

    def test_gewollte_abweichung_vom_dpi_ist_keine_warnung(self):
        """Das Fenster meldet 120 dpi, tk scaling steht auf 2,0 - gewollt, also nichts zu melden."""
        befunde = ad.pruefe_skalierung(self._lage(
            tk_skalierung=2.0, manuell_prozent=150, system_prozent=125, soll_skalierung=2.0))
        self.assertNotIn("skalierung_weicht_ab", self._kennungen(befunde))

    def test_gewahlte_skalierung_kommt_nicht_an(self):
        """Der Fehler, den die Auswahl nicht sehen koennte: gewaehlt 150 %, tk scaling steht noch auf 125 %."""
        befunde = ad.pruefe_skalierung(self._lage(
            tk_skalierung=1.6683, manuell_prozent=150, system_prozent=125, soll_skalierung=2.0))
        self.assertIn("skalierung_weicht_ab", self._kennungen(befunde))
        warnung = [b for b in befunde if b.kennung == "skalierung_weicht_ab"][0]
        self.assertEqual(warnung.schwere, ad.WARNUNG)
        self.assertIn("nicht angekommen", warnung.text)

    def test_messung_hat_toleranz(self):
        """Tk rundet die Bildschirmmillimeter: 2,0 wird 1,998."""
        befunde = ad.pruefe_skalierung(self._lage(
            tk_skalierung=1.998, manuell_prozent=150, soll_skalierung=2.0))
        self.assertNotIn("skalierung_weicht_ab", self._kennungen(befunde))

    def test_ohne_wahl_gilt_weiter_der_dpi_wert(self):
        befunde = ad.pruefe_skalierung(self._lage(fenster_dpi=192, tk_skalierung=1.3333))
        self.assertIn("skalierung_weicht_ab", self._kennungen(befunde))
        self.assertNotIn("skalierung_von_hand", self._kennungen(befunde))

    def test_unter_macos_gibt_es_nur_den_hinweis(self):
        befunde = ad.pruefe_skalierung(ad.Skalierungslage(
            plattform="darwin", tk_skalierung=1.98, schrifthoehe_px=20, manuell_prozent=150, system_prozent=125))
        self.assertEqual(self._kennungen(befunde), ["skalierung_von_hand"])

    def test_standardwerte_aendern_nichts_an_alten_aufrufen(self):
        lage = ad.Skalierungslage()
        self.assertEqual((lage.manuell_prozent, lage.system_prozent, lage.soll_skalierung), (None, None, None))


# ---------------------------------------------------------------------------
# 6. Das echte Einstellungsfenster
# ---------------------------------------------------------------------------
def _wurzel():
    try:
        wurzel = tk._default_root or tk.Tk()
        wurzel.withdraw()
        return wurzel
    except Exception as exc:                          # pragma: no cover - ohne Anzeige
        raise unittest.SkipTest("keine Anzeige verfügbar: %s" % exc)


class EinstellungsfensterTests(unittest.TestCase):
    """Der Abschnitt Anzeige im echten Einstellungsfenster (Wurzel zurückgezogen)."""

    @classmethod
    def setUpClass(cls):
        cls.wurzel = _wurzel()
        cls.app = GUI(cls.wurzel)

    def setUp(self):
        self.arbeit = tempfile.TemporaryDirectory()
        self.addCleanup(self.arbeit.cleanup)
        self.konfig = os.path.join(self.arbeit.name, "paths.json")
        self.app._get_config_path = lambda: self.konfig
        # Was diese Sitzung beim Start hatte, steht auf "automatisch" - und wird nach dem Test zurueckgesetzt.
        for name, wert in (("_skalierung_manuell", None), ("_aufloesung_manuell", None),
                           ("_skalierung_system", 125)):
            alt = self.app.__dict__.get(name, mock.sentinel.fehlt)
            setattr(self.app, name, wert)
            self.addCleanup(self._zurueck, name, alt)
        self.neustarts = []
        mock.patch.object(self.app, "_restart_application", side_effect=lambda: self.neustarts.append(1)).start()
        mock.patch.object(self.app, "_vorgang_laeuft_noch", return_value=False).start()
        self.addCleanup(mock.patch.stopall)
        self.info = mock.patch.object(mod.messagebox, "showinfo").start()
        self.frage = mock.patch.object(mod.messagebox, "askyesno", return_value=False).start()
        self._schreibe({})

    def _zurueck(self, name, alt):
        if alt is mock.sentinel.fehlt:
            self.app.__dict__.pop(name, None)
        else:
            setattr(self.app, name, alt)

    def _schreibe(self, inhalt):
        with open(self.konfig, "w", encoding="utf-8") as datei:
            json.dump(inhalt, datei)

    def _lies(self):
        with open(self.konfig, encoding="utf-8") as datei:
            return json.load(datei)

    def _dialog(self):
        erfasst: dict = {}
        original = self.app._einstellungen_anzeige_abschnitt

        def abfangen(dlg, body):
            erfasst.update(original(dlg, body))
            erfasst["dlg"] = dlg
            return erfasst

        with mock.patch.object(self.app, "_einstellungen_anzeige_abschnitt", abfangen):
            self.app._show_settings_dialog()
        dlg = erfasst["dlg"]
        dlg.update_idletasks()
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        return erfasst

    def test_start_ohne_wahl_zeigt_das_system_und_hat_nichts_zu_uebernehmen(self):
        d = self._dialog()
        self.assertAlmostEqual(float(d["regler"].get()), 125.0, delta=0.5)
        self.assertEqual(d["regler"].master._zahl.get(), "125 %")
        self.assertIn("automatisch", d["status"]._var.get())
        self.assertTrue(d["box"].get().startswith("Automatisch"))
        self.assertEqual(str(d["uebernehmen"].cget("state")), "disabled")
        self.assertFalse(d["hinweis"].winfo_ismapped())
        self.assertEqual(d["wahl"], {"skala": None, "aufl": None})

    def test_gespeicherte_wahl_wird_angezeigt(self):
        self._schreibe({"ui_skalierung": 150, "ui_aufloesung": "1600x900"})
        d = self._dialog()
        self.assertAlmostEqual(float(d["regler"].get()), 150.0, delta=0.5)
        self.assertEqual(d["box"].get(), "1600 × 900")
        self.assertIn("von Hand 150 %", d["status"]._var.get())
        self.assertIn("1600", d["status"]._var.get())

    def test_gespeichert_aber_noch_nicht_neu_gestartet_laesst_den_neustart_zu(self):
        """Die Sitzung lief automatisch, in der Datei steht schon eine Wahl: Der Knopf bietet den Neustart an."""
        self._schreibe({"ui_skalierung": 150})
        d = self._dialog()
        self.assertEqual(str(d["uebernehmen"].cget("state")), "normal")
        self.assertTrue(d["hinweis"].winfo_ismapped() or d["hinweis"].winfo_manager())

    def test_regler_bewegen_aendert_nur_die_anzeige(self):
        d = self._dialog()
        d["regler"].set(140)
        self.wurzel.update()
        self.assertEqual(d["wahl"]["skala"], 140)
        self.assertEqual(d["regler"].master._zahl.get(), "140 %")
        self.assertEqual(str(d["uebernehmen"].cget("state")), "normal")
        self.assertTrue(d["hinweis"].winfo_manager())
        self.assertEqual(self._lies(), {}, "gespeichert wird erst beim Uebernehmen")
        self.assertIn("automatisch", d["status"]._var.get(), "der Satz zeigt, was gespeichert ist")

    def test_anzeige_rastet_auf_reglerschritte(self):
        d = self._dialog()
        d["regler"].set(137)
        self.wurzel.update()
        self.assertEqual(d["wahl"]["skala"], 135)
        self.assertEqual(d["regler"].master._zahl.get(), "135 %")

    def test_setzen_per_programm_ist_keine_handlung(self):
        """Ein Zuruecksetzen darf aus 'automatisch' keine Wahl machen."""
        d = self._dialog()
        d["zuruecksetzen_aktion"]()
        self.assertEqual(d["wahl"], {"skala": None, "aufl": None})

    def test_aufloesung_waehlen(self):
        d = self._dialog()
        d["box"].set("1366 × 768")
        d["box_gewaehlt"]()
        self.assertEqual(d["wahl"]["aufl"], (1366, 768))
        self.assertEqual(str(d["uebernehmen"].cget("state")), "normal")
        d["box"].current(0)
        d["box_gewaehlt"]()
        self.assertIsNone(d["wahl"]["aufl"])
        self.assertEqual(str(d["uebernehmen"].cget("state")), "disabled")

    def test_regler_reicht_nur_bis_zur_bildschirmbreite(self):
        d = self._dialog()
        breite = self.app._bildschirm_fuer_fenster()[0]
        erwartet = ask.skalierung_obergrenze(breite, mod.WINDOW_MIN_WIDTH, self.app._skalierung_system)
        self.assertAlmostEqual(float(d["regler"].cget("to")), erwartet, delta=0.5)

    def test_kleinere_aufloesung_senkt_die_grenze_und_nimmt_die_wahl_mit(self):
        d = self._dialog()
        d["regler"].set(195)
        self.wurzel.update()
        vorher = d["wahl"]["skala"]
        d["box"].set("1366 × 768")
        d["box_gewaehlt"]()
        grenze = ask.skalierung_obergrenze(1366, mod.WINDOW_MIN_WIDTH, self.app._skalierung_system)
        self.assertAlmostEqual(float(d["regler"].cget("to")), grenze, delta=0.5)
        if vorher > grenze:
            self.assertEqual(d["wahl"]["skala"], grenze)
        self.assertLessEqual(d["wahl"]["skala"], max(grenze, vorher))

    def test_uebernehmen_speichert_und_startet_neu(self):
        d = self._dialog()
        d["regler"].set(140)
        d["box"].set("1600 × 900")
        d["box_gewaehlt"]()
        self.wurzel.update()
        d["anwenden"]()
        self.assertEqual(self._lies(), {"ui_skalierung": 140, "ui_aufloesung": "1600x900"})
        self.assertEqual(self.neustarts, [1])

    def test_uebernehmen_nur_einer_der_beiden_werte(self):
        d = self._dialog()
        d["box"].set("1600 × 900")
        d["box_gewaehlt"]()
        d["anwenden"]()
        self.assertEqual(self._lies(), {"ui_skalierung": None, "ui_aufloesung": "1600x900"})

    def test_ohne_neustart_wenn_ein_vorgang_laeuft(self):
        """Der Neustart beendet den Prozess - auch einen laufenden PKG-Merge. Gespeichert wird trotzdem."""
        self.app._vorgang_laeuft_noch.return_value = True
        d = self._dialog()
        d["regler"].set(140)
        self.wurzel.update()
        d["anwenden"]()
        self.assertEqual(self._lies()["ui_skalierung"], 140)
        self.assertEqual(self.neustarts, [])
        self.info.assert_called()
        self.assertTrue(d["dlg"].winfo_exists())

    def test_ohne_neustart_bei_pkg_merge_oder_uebertragung(self):
        for zaehler in ("_pkg_merge_laeuft", "_bibliothek_uebertragungen"):
            with self.subTest(zaehler=zaehler):
                self.neustarts.clear()
                alt = getattr(self.app, zaehler, 0)
                setattr(self.app, zaehler, 1)
                self.addCleanup(setattr, self.app, zaehler, alt)
                d = self._dialog()
                d["regler"].set(145)
                self.wurzel.update()
                d["anwenden"]()
                self.assertEqual(self.neustarts, [])
                setattr(self.app, zaehler, alt)

    def test_zuruecksetzen_loescht_beide_werte_sofort(self):
        self._schreibe({"ui_skalierung": 150, "ui_aufloesung": "1600x900"})
        d = self._dialog()
        d["zuruecksetzen_aktion"]()
        self.assertEqual(self._lies(), {"ui_skalierung": None, "ui_aufloesung": None})
        self.assertAlmostEqual(float(d["regler"].get()), 125.0, delta=0.5)
        self.assertTrue(d["box"].get().startswith("Automatisch"))
        self.assertEqual(d["wahl"], {"skala": None, "aufl": None})

    def test_zuruecksetzen_fragt_nur_wenn_die_sitzung_von_hand_lief(self):
        d = self._dialog()
        d["zuruecksetzen_aktion"]()
        self.frage.assert_not_called()
        self.assertEqual(self.neustarts, [])
        self.app._skalierung_manuell = 150                 # diese Sitzung lief von Hand
        d = self._dialog()
        d["zuruecksetzen_aktion"]()
        self.frage.assert_called_once()
        self.assertEqual(self.neustarts, [], "Antwort war nein")
        self.info.assert_called()

    def test_zuruecksetzen_mit_ja_startet_neu(self):
        self.frage.return_value = True
        self.app._aufloesung_manuell = (1600, 900)
        d = self._dialog()
        d["zuruecksetzen_aktion"]()
        self.assertEqual(self.neustarts, [1])

    def test_offene_werkzeugfenster_halten_den_neustart_auf(self):
        fenster = tk.Toplevel(self.wurzel)
        self.addCleanup(fenster.destroy)
        with mock.patch.object(self.app, "_werkzeugfenster", {"x": fenster}, create=True), \
                mock.patch.object(self.app, "_werkzeugfenster_schliessen"), \
                mock.patch.object(self.app, "_fenster_lebt", return_value=True):
            d = self._dialog()
            d["regler"].set(140)
            self.wurzel.update()
            d["anwenden"]()
        self.assertEqual(self.neustarts, [])
        self.info.assert_called()

    def test_statussatz_nennt_wahl_und_system(self):
        text = self.app._anzeige_status_text(150, (1366, 768))
        for erwartet in ("150 %", "125 %", "1366", "768"):
            self.assertIn(erwartet, text)
        text = self.app._anzeige_status_text(None, None)
        self.assertIn("automatisch", text)
        self.assertNotIn("von Hand", text)

    def test_diagnose_kennt_die_wahl(self):
        self.app._skalierung_manuell = 150
        self.app._skalierung_system = 125
        lage = self.app._diagnose_skalierung_messen()
        self.assertEqual((lage.manuell_prozent, lage.system_prozent), (150, 125))
        self.assertAlmostEqual(lage.soll_skalierung, 2.0, places=3)
        self.app._skalierung_manuell = None
        lage = self.app._diagnose_skalierung_messen()
        self.assertIsNone(lage.soll_skalierung)

    def test_bericht_nennt_skalierung_und_aufloesung(self):
        self.app._skalierung_manuell = 175
        self.app._aufloesung_manuell = (2560, 1440)
        zeilen = "\n".join(self.app._diagnose_anzeige())
        self.assertIn("Skalierung (Einstellung)", zeilen)
        self.assertIn("von Hand 175 %", zeilen)
        self.assertIn("Auflösung (Einstellung)", zeilen)
        self.assertIn("von Hand 2560x1440", zeilen)
        self.app._skalierung_manuell, self.app._aufloesung_manuell = None, None
        zeilen = "\n".join(self.app._diagnose_anzeige())
        self.assertIn("automatisch", zeilen)


# ---------------------------------------------------------------------------
# 7. Am wirklich gestarteten Programm gemessen
# ---------------------------------------------------------------------------
class GestartetesProgrammTests(unittest.TestCase):
    """Greift die Wahl beim Start wirklich? Gemessen im Teilprozess.

    Im Teilprozess, damit die gemeinsame Tk-Wurzel der übrigen Tests ihre Skalierung
    behält. Mit dem Wert ``tk scaling`` allein wäre nichts bewiesen: Entscheidend ist, dass
    Schrift und ``knopfmass`` folgen - die Standardschrift wurde am 02.10.2026 bei 125 %
    mit 20 px, bei 150 % mit 25 px und bei 200 % mit 32 px Zeilenhöhe gemessen.
    """

    PROBE = r"""
import json, os, sys, tkinter as tk
try:
    import ctypes
    ctypes.windll.user32.SetProcessDPIAware()
except Exception:
    pass
sys.path.insert(0, os.getcwd())
import PS5ImageConverter_Pro_FINAL_revised as GUI
import tkinter.font as tkfont
root = tk.Tk()
root.withdraw()
app = GUI.PS5ConverterGUI(root)
root.update()
print("ERGEBNIS " + json.dumps({
    "scaling": float(root.tk.call("tk", "scaling")),
    "zeile": tkfont.nametofont("TkDefaultFont").metrics("linespace"),
    "knopf": GUI.knopfmass(44, root),
    "system": app._skalierung_system,
    "manuell": app._skalierung_manuell,
}))
root.destroy()
"""

    @classmethod
    def setUpClass(cls):
        cls.ordner = tempfile.TemporaryDirectory()
        cls.messungen: dict = {}

    @classmethod
    def tearDownClass(cls):
        cls.ordner.cleanup()

    @classmethod
    def _messen(cls, **einstellungen):
        schluessel = json.dumps(einstellungen, sort_keys=True)
        if schluessel in cls.messungen:
            return cls.messungen[schluessel]
        konfig = tempfile.mkdtemp(dir=cls.ordner.name)
        with open(os.path.join(konfig, "paths.json"), "w", encoding="utf-8") as datei:
            json.dump(dict(einstellungen, language="de"), datei)
        env = dict(os.environ, PS5CONV_KONFIGORDNER=konfig)
        lauf = subprocess.run([sys.executable, "-c", cls.PROBE], cwd=str(PROJEKT), env=env,
                              capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("ERGEBNIS ")]
        if not zeilen:
            if "TclError" in lauf.stderr and ("display" in lauf.stderr.lower() or "no display" in lauf.stderr.lower()):
                raise unittest.SkipTest("keine Anzeige verfügbar")
            raise AssertionError("Programm nicht gestartet:\n" + lauf.stderr[-800:])
        cls.messungen[schluessel] = json.loads(zeilen[-1][len("ERGEBNIS "):])
        return cls.messungen[schluessel]

    def test_gewaehlte_skalierung_erreicht_tk_schrift_und_knoepfe(self):
        klein = self._messen(ui_skalierung=100)
        gross = self._messen(ui_skalierung=200)
        self.assertAlmostEqual(klein["scaling"], 100 / 75, delta=0.02)
        self.assertAlmostEqual(gross["scaling"], 200 / 75, delta=0.02)
        self.assertGreater(gross["zeile"], klein["zeile"] * 1.5,
                           "die Standardschrift waechst mit: %s -> %s px" % (klein["zeile"], gross["zeile"]))
        self.assertEqual(klein["knopf"], 44, "unter 125 % schrumpfen die Knopfmasse nie")
        self.assertGreaterEqual(gross["knopf"], 68, "bei 200 % wird aus 44 px ein Knopf mit rund 70 px")
        self.assertEqual((klein["manuell"], gross["manuell"]), (100, 200))

    def test_ohne_wahl_bleibt_es_beim_system(self):
        auto = self._messen()
        self.assertIsNone(auto["manuell"])
        # Dieselbe Zahl, die der Teilprozess an einer unberuehrten Wurzel liest: das System.
        lauf = subprocess.run(
            [sys.executable, "-c",
             "import ctypes,tkinter as tk\n"
             "try: ctypes.windll.user32.SetProcessDPIAware()\nexcept Exception: pass\n"
             "r=tk.Tk(); r.withdraw(); print('SYSTEM', float(r.tk.call('tk','scaling')))"],
            capture_output=True, text=True, timeout=60)
        zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("SYSTEM ")]
        if not zeilen:
            self.skipTest("keine Anzeige verfügbar")
        self.assertAlmostEqual(auto["scaling"], float(zeilen[0].split()[1]), places=4)
        self.assertEqual(auto["system"], ask.prozent_aus_tk(float(zeilen[0].split()[1])))

    def test_wahl_gleich_dem_system_aendert_das_bild_nicht(self):
        auto = self._messen()
        gleich = self._messen(ui_skalierung=auto["system"])
        self.assertEqual(gleich["zeile"], auto["zeile"])
        self.assertAlmostEqual(gleich["scaling"], auto["scaling"], delta=0.02)

    def test_unbrauchbare_wahl_wird_ignoriert(self):
        auto = self._messen()
        kaputt = self._messen(ui_skalierung="abc", ui_aufloesung="quatsch")
        self.assertIsNone(kaputt["manuell"])
        self.assertEqual(kaputt["zeile"], auto["zeile"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
