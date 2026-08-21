# -*- coding: utf-8 -*-
"""Tests fuer den Ablageort-Hinweis waehrend der PS4-Konvertierung.

Waehrend der Balken laeuft, wartet der Nutzer ohnehin - der beste Moment
fuer die eine Sache, die ueber Laufen und Nicht-Laufen entscheidet: Ein
PS4-Spiel darf nur vom externen USB-Datentraeger starten, nie von der
internen SSD (sonst Kernel Panic, an der Konsole dreimal gemessen).

Vorgabe: viermal je Lauf, je 15 Sekunden, ein- und ausgeblendet, ohne dass
man etwas druecken muss.
"""
import io
import os
import sys
import time
import unittest

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


class VorgabenTests(unittest.TestCase):
    """Die Zahlen, die der Nutzer vorgegeben hat."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.G = cls.haupt.PS5ConverterGUI
        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            cls.quelltext = datei.read()

    def test_viermal_je_lauf(self):
        self.assertEqual(len(self.G._PS4_HINWEIS_MARKEN), 4)

    def test_die_marken_liegen_verteilt_und_nicht_bei_null(self):
        """Bei 0 % schaut der Nutzer noch auf den Knopf, nicht auf den Balken."""
        marken = list(self.G._PS4_HINWEIS_MARKEN)
        self.assertEqual(marken, sorted(marken), "Marken nicht aufsteigend")
        self.assertGreater(marken[0], 0.0)
        self.assertLess(marken[-1], 100.0)
        abstaende = [b - a for a, b in zip(marken, marken[1:])]
        self.assertTrue(all(a >= 15.0 for a in abstaende),
                        "Zu dicht beieinander: %s" % abstaende)

    def test_fuenfundzwanzig_sekunden(self):
        """25 statt 15, seit die Einblendung auch den Kasten traegt.

        Seit v1.8.77 steht der ganze Ablageort-Hinweis hier statt dauerhaft
        im Fenster - vier Absaetze lesen sich nicht in fuenfzehn Sekunden.
        """
        self.assertEqual(self.G._PS4_HINWEIS_DAUER, 25000)

    def test_es_wird_geblendet(self):
        self.assertGreaterEqual(self.G._PS4_HINWEIS_BLENDE, 300,
                                "Zu schnell, um als Blende zu wirken")
        self.assertGreaterEqual(
            self.G._PS4_HINWEIS_BLENDE // self.G._PS4_HINWEIS_SCHRITT, 10,
            "Zu wenige Schritte fuer einen weichen Verlauf")

    def test_kein_knopf_zum_wegklicken(self):
        """Sie geht von selbst - nichts, was man druecken muesste."""
        anfang = self.quelltext.index("    def _ps4_hinweis_zeigen(self")
        ende = self.quelltext.index("\n    def ", anfang + 10)
        rumpf = self.quelltext[anfang:ende]
        for verboten in ("tk.Button", "ttk.Button", "command="):
            self.assertNotIn(verboten, rumpf,
                             "Die Einblendung hat ein Bedienelement: %r"
                             % verboten)
        self.assertIn("after(self._PS4_HINWEIS_DAUER", rumpf,
                      "Sie schliesst sich nicht von selbst")

    def test_sie_stiehlt_den_eingabeplatz_nicht(self):
        anfang = self.quelltext.index("    def _ps4_hinweis_zeigen(self")
        ende = self.quelltext.index("\n    def ", anfang + 10)
        rumpf = self.quelltext[anfang:ende]
        for verboten in ("focus_force", "grab_set", "wait_window"):
            self.assertNotIn(verboten, rumpf,
                             "Die Einblendung greift nach der Eingabe: %r"
                             % verboten)

    def test_sie_zeigt_die_wesentlichen_texte(self):
        anfang = self.quelltext.index("    def _ps4_hinweis_zeigen(self")
        ende = self.quelltext.index("\n    def ", anfang + 10)
        rumpf = self.quelltext[anfang:ende]
        for schluessel in ("ps4pkg.place_title", "ps4pkg.place_ok",
                           "ps4pkg.place_bad", "ps4pkg.place_after_crash",
                           "ps4pkg.place_hint", "ps4pkg.runtime_note"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, rumpf)

    def test_der_kern_steht_in_beiden_sprachen(self):
        """USB ja, interne SSD nein - das ist die Aussage."""
        from ps5_validator.utils import i18n
        for sprache in i18n.SUPPORTED_LANGUAGES:
            with self.subTest(sprache=sprache):
                self.assertIn("/mnt/usb0/",
                              i18n.STRINGS["ps4pkg.place_ok"][sprache])
                schlecht = i18n.STRINGS["ps4pkg.place_bad"][sprache]
                self.assertIn("/data/homebrew", schlecht)
                self.assertIn("/data/etaHEN/games", schlecht)

    def test_alle_drei_gemessenen_orte_stehen_da(self):
        """Drei Orte auf dem Stick, jeder einzeln an der Konsole gemessen.

        21.08.2026, Firmware 12.00, ShadowMount+ v1.7alpha6 - die Datei
        jeweils dorthin verschoben und danach zurueckgelegt:

            /mnt/usb0/              binnen 15 s indiziert
            /mnt/usb0/homebrew/     binnen 20 s eingehaengt
            /mnt/usb0/etaHEN/games  binnen 20 s eingehaengt

        Der dritte war zuerst nicht drin, weil ich ihn fuer unbelegt hielt -
        die gezielten Scans beim Einstecken nennen nur einen Teil der 34
        eingebauten Pfade. Der Nutzer lag richtig, die Messung hat es
        bestaetigt.
        """
        from ps5_validator.utils import i18n
        for sprache in i18n.SUPPORTED_LANGUAGES:
            text = i18n.STRINGS["ps4pkg.place_ok"][sprache]
            for ort in ("/mnt/usb0/", "/mnt/usb0/homebrew/",
                        "/mnt/usb0/etaHEN/games"):
                with self.subTest(sprache=sprache, ort=ort):
                    self.assertIn(ort, text)

    def test_am_ende_wird_aufgeraeumt(self):
        """Bricht der Nutzer ab, darf keine Einblendung stehen bleiben."""
        self.assertIn("_ps4_hinweis_aufraeumen", self.quelltext)
        anfang = self.quelltext.index("    def _ps4_hinweis_aufraeumen(self")
        ende = self.quelltext.index("\n    def ", anfang + 10)
        self.assertIn("destroy", self.quelltext[anfang:ende])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class AblaufTests(unittest.TestCase):
    """Faehrt einen Fortschritt von 0 auf 100 und zaehlt mit."""

    @classmethod
    def setUpClass(cls):
        cls._eigene_wurzel = tk._default_root is None
        cls.wurzel = tk._default_root or tk.Tk()
        cls.wurzel.withdraw()
        cls.haupt = _lade_hauptprogramm()
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(cls.haupt.messagebox, name, lambda *a, **k: None)
        cls.app = cls.haupt.PS5ConverterGUI(cls.wurzel)
        cls.app._online_nachschlag_erlaubt = lambda: False

    @classmethod
    def tearDownClass(cls):
        if not cls._eigene_wurzel:
            return
        try:
            cls.wurzel.destroy()
        except Exception:
            pass

    def setUp(self):
        self.app._ps4_hinweis_stand = {"gezeigt": set(), "laeuft": False,
                                       "fenster": None}

    def test_genau_vier_ueber_den_ganzen_lauf(self):
        treffer = [p for p in range(0, 101)
                   if self.app._ps4_hinweis_faellig(float(p))]
        self.assertEqual(len(treffer), 4,
                         "Ausgeloest bei: %s" % treffer)

    def test_waehrend_einer_laeuft_kommt_keine_zweite(self):
        self.assertTrue(self.app._ps4_hinweis_faellig(10.0))
        self.app._ps4_hinweis_stand["laeuft"] = True
        for p in (40.0, 60.0, 90.0):
            with self.subTest(prozent=p):
                self.assertFalse(self.app._ps4_hinweis_faellig(p))

    def test_ein_sprung_loest_nicht_vier_hintereinander_aus(self):
        """Kleine Spiele sind schnell durch - der Balken springt dann."""
        self.assertTrue(self.app._ps4_hinweis_faellig(95.0))
        self.assertEqual(len(self.app._ps4_hinweis_stand["gezeigt"]), 4)
        self.assertFalse(self.app._ps4_hinweis_faellig(100.0))

    def test_ein_zweiter_lauf_zeigt_sie_wieder(self):
        for p in range(0, 101):
            self.app._ps4_hinweis_faellig(float(p))
        self.app._ps4_hinweis_stand = {"gezeigt": set(), "laeuft": False,
                                       "fenster": None}
        treffer = [p for p in range(0, 101)
                   if self.app._ps4_hinweis_faellig(float(p))]
        self.assertEqual(len(treffer), 4)

    def test_sie_blendet_auf_und_verschwindet_von_selbst(self):
        """Ohne einen einzigen Tastendruck.

        Die Haltedauer wird fuer den Test verkuerzt - 15 Sekunden zu warten
        brächte keine zusaetzliche Erkenntnis.
        """
        alt = self.haupt.PS5ConverterGUI._PS4_HINWEIS_DAUER
        self.haupt.PS5ConverterGUI._PS4_HINWEIS_DAUER = 400
        self.wurzel.deiconify()
        try:
            self.wurzel.update_idletasks()
            self.app._ps4_hinweis_zeigen(self.wurzel)
            karte = self.app._ps4_hinweis_stand["fenster"]
            self.assertIsNotNone(karte, "Keine Einblendung entstanden")

            deckkraefte = []
            ende = time.perf_counter() + 8.0
            while (time.perf_counter() < ende
                   and self.app._ps4_hinweis_stand["laeuft"]):
                self.wurzel.update()
                try:
                    if karte.winfo_exists():
                        deckkraefte.append(float(karte.attributes("-alpha")))
                except Exception:
                    pass
                time.sleep(0.01)

            self.assertFalse(self.app._ps4_hinweis_stand["laeuft"],
                             "Sie ist nicht von selbst verschwunden")
            self.assertIsNone(self.app._ps4_hinweis_stand["fenster"])
            if deckkraefte:
                self.assertLess(min(deckkraefte), 0.5,
                                "Kein Aufblenden erkennbar")
                self.assertGreater(max(deckkraefte), 0.9,
                                   "Wird nie ganz sichtbar")
        finally:
            self.haupt.PS5ConverterGUI._PS4_HINWEIS_DAUER = alt
            self.app._ps4_hinweis_aufraeumen()
            self.wurzel.withdraw()

    def test_aufraeumen_schliesst_eine_offene(self):
        self.wurzel.deiconify()
        try:
            self.app._ps4_hinweis_zeigen(self.wurzel)
            self.assertTrue(self.app._ps4_hinweis_stand["laeuft"])
            self.app._ps4_hinweis_aufraeumen()
            self.assertFalse(self.app._ps4_hinweis_stand["laeuft"])
            self.assertIsNone(self.app._ps4_hinweis_stand["fenster"])
        finally:
            self.wurzel.withdraw()


if __name__ == "__main__":
    unittest.main(verbosity=2)
