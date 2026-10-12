# -*- coding: utf-8 -*-
"""Schneidet eine Seite der Ansicht KONSOLE bei kleinem Fenster Text oder Knoepfe ab? (seit v1.9.63)

Anlass (04.10.2026): ``--anzeige-diagnose`` misst nur die Ansicht UMWANDELN. Die
drei Seiten der Ansicht KONSOLE blieben ungeprueft - und bei der Mindestbreite
fanden sich zwei Befunde: die Danksagung der neuen WebKit-Seite war 18 px zu
schmal, und "Neu scannen" in der Kopfkarte der Bibliothek war unter 1366 px
Fensterbreite 44 px zu schmal (schon seit v1.9.62 so).

Dieselbe Pruefung (``anzeige_diagnose.pruefe_flaechen``) laeuft hier ueber jede
Seite - bei der Mindestgroesse des Fensters und bei einem verbreiteten
Laptopschirm. Ein eigenes Fenster (Toplevel, unsichtbar) wie in
test_rollflaeche: Es misst nur die eigene Oberflaeche, nicht die einer anderen
Testdatei an derselben Wurzel.
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("konsole_mindestgroesse")

# ERST das Hauptprogramm, DANN die Wurzel: Sein Import setzt unter Windows die
# DPI-Kenntnis des Prozesses (siehe test_rollflaeche).
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import anzeige_diagnose as ad      # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

#: Die Mindestgroesse des Fensters und ein verbreiteter Laptopschirm.
GROESSEN = ((APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT), (1366, 768))
#: Die drei Seiten der Ansicht KONSOLE (Kennungen aus ``_KONSOLE_SEITENBAU``).
SEITEN = ("uebersicht", "webkit", "bibliothek")
#: Was hier zaehlt: Text, der nicht hineinpasst, und zusammengedrueckte Elemente.
#: Randueberstaende ("abgeschnitten") haengen an Lage und Groesse des Bildschirms.
MAENGEL = ("text_beschnitten", "eingeklappt")


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class KonsoleSeitenBeiKleinemFensterTests(unittest.TestCase):
    """Jede Seite, jede Groesse: nichts darf zu schmal oder zusammengedrueckt sein."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk.Toplevel(_WURZEL)
        try:
            cls.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.app = APP.PS5ConverterGUI(cls.root)
        # Deutsch festnageln - die Texte sind dort am laengsten, und im Volllauf
        # stuende sonst die Sprache des zuletzt importierten Pruefmoduls darin.
        cls.app._current_language = "de"
        cls.app._apply_language()
        cls.app._online_nachschlag_erlaubt = lambda: False
        cls._ruhen(1.5)
        cls.app._ansicht_setzen("konsole")
        cls._ruhen(1.0)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.root.destroy()
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def _ruhen(cls, sekunden: float) -> None:
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            cls.root.update()
            time.sleep(0.01)

    def _einstellen(self, breite: int, hoehe: int, seite: str) -> None:
        """Fenstergroesse und Seite einstellen und zur Ruhe kommen lassen."""
        try:
            self.root.state("normal")        # der Aufbau maximiert das Fenster
        except Exception:  # noqa: BLE001
            pass
        self.root.geometry("%dx%d" % (breite, hoehe))
        self._ruhen(1.0)
        self.app._konsole_seite_setzen(seite)
        self._ruhen(1.5)

    def _maengel(self, breite: int, hoehe: int, seite: str) -> list[str]:
        self._einstellen(breite, hoehe, seite)
        fenster = ad.Fensterlage(
            breite=self.root.winfo_width(), hoehe=self.root.winfo_height(),
            x=self.root.winfo_rootx(), y=self.root.winfo_rooty(),
            schirm_breite=self.root.winfo_screenwidth(),
            schirm_hoehe=self.root.winfo_screenheight())
        befunde = ad.pruefe_flaechen(fenster, self.app._diagnose_flaechen_sammeln())
        return [str(b) for b in befunde if b.kennung in MAENGEL]

    def test_es_gibt_ueberhaupt_etwas_zu_messen(self) -> None:
        """Sonst bestaende die Pruefung unten mit leeren Listen."""
        self.app._konsole_seite_setzen("webkit")
        self._ruhen(1.0)
        flaechen = self.app._diagnose_flaechen_sammeln()
        self.assertGreater(len([f for f in flaechen if f.sichtbar]), 20)

    def test_keine_seite_schneidet_text_ab(self) -> None:
        for breite, hoehe in GROESSEN:
            if self.root.winfo_screenwidth() < breite or self.root.winfo_screenheight() < hoehe:
                continue            # der Bildschirm gibt die Groesse nicht her
            for seite in SEITEN:
                with self.subTest(breite=breite, hoehe=hoehe, seite=seite):
                    self.assertEqual([], self._maengel(breite, hoehe, seite))

    def test_die_knoepfe_unter_der_tabelle_liegen_ganz_in_ihrer_reihe(self) -> None:
        """Jeder der vier Knoepfe ist sichtbar und liegt ganz in der Reihe - bei jeder Groesse.

        Ein Knopf, der aus dem Fenster geschoben ist, schneidet keinen Text ab und bleibt der Pruefung oben
        verborgen: ``QR-Code`` lag bei 1245 px Fensterbreite schon vor dem 10.10.2026 ausserhalb der Reihe
        (Reihe 704 px, die vier Knoepfe brauchen 785). Seitdem bricht die Reihe um.
        """
        gemessen = 0
        for breite, hoehe in GROESSEN:
            if self.root.winfo_screenwidth() < breite or self.root.winfo_screenheight() < hoehe:
                continue
            self._einstellen(breite, hoehe, "uebersicht")
            reihe = self.app._konsole_tafel_knopfreihe
            kinder = reihe.winfo_children()
            with self.subTest(breite=breite, hoehe=hoehe):
                self.assertEqual(4, len(kinder))
                for knopf in kinder:
                    name = knopf.cget("text")
                    self.assertTrue(knopf.winfo_ismapped(), name)
                    self.assertGreaterEqual(knopf.winfo_x(), 0, name)
                    self.assertLessEqual(knopf.winfo_x() + knopf.winfo_width(), reihe.winfo_width(), name)
                    self.assertGreaterEqual(knopf.winfo_width(), knopf.winfo_reqwidth(), name)
                unten = max(k.winfo_y() + k.winfo_height() for k in kinder)
                self.assertLessEqual(unten, reihe.winfo_height(), "Die Reihe waechst mit ihren Zeilen mit")
            gemessen += 1
        self.assertGreater(gemessen, 0, "Der Bildschirm gab keine der Groessen her")

    def test_die_tabelle_bleibt_bei_jeder_groesse_lesbar(self) -> None:
        """Mindestens vier Zeilenhoehen (Kopf und etwa drei Zeilen) - und die Seite wird bei niedrigem Fenster kompakt.

        Gemessen am 10.10.2026: Mit Favoritenzeile und zweiter Knopfzeile blieben der Tabelle bei 1245x700 nur 38 px.
        Seitdem gibt die Seite bei niedrigem Fenster zuerst die Unterzeile, zwei Protokollzeilen und Rand her.
        """
        from tkinter import ttk
        zeile = int(ttk.Style(self.root).lookup("Treeview", "rowheight") or 20)
        unterzeile = self.app._t("tafel.subtitle")
        gemessen = 0
        for breite, hoehe in GROESSEN:
            if self.root.winfo_screenwidth() < breite or self.root.winfo_screenheight() < hoehe:
                continue
            self._einstellen(breite, hoehe, "uebersicht")
            tabelle = self.app._konsole_tafel_tabelle
            sichtbar = tabelle.master.winfo_height()
            with self.subTest(breite=breite, hoehe=hoehe):
                self.assertGreaterEqual(sichtbar, 4 * zeile, "Tabelle %d px, eine Zeile %d px" % (sichtbar, zeile))
                titel = [w for w in self.app._konsole_tafel.winfo_children()
                         if w.winfo_class() == "Label" and str(w.cget("text")) == unterzeile]
                self.assertEqual(1, len(titel))
                # Kompakt heisst: Unterzeile weg und drei Protokollzeilen - und nur dann.
                kompakt = bool(self.app._konsole_tafel_kompakt)
                self.assertEqual(not kompakt, bool(titel[0].winfo_ismapped()))
                self.assertEqual(3 if kompakt else 5, int(self.app._konsole_tafel_protokoll.cget("height")))
            gemessen += 1
        self.assertGreater(gemessen, 0, "Der Bildschirm gab keine der Groessen her")

    def test_updates_sitzt_rechts_oben_neben_konsole_pruefen(self) -> None:
        """Der Knopf "Updates" liegt im Kopf der Seite rechts von "Konsole pruefen" und ganz im Kopf."""
        gemessen = 0
        for breite, hoehe in GROESSEN:
            if self.root.winfo_screenwidth() < breite or self.root.winfo_screenheight() < hoehe:
                continue
            self._einstellen(breite, hoehe, "uebersicht")
            updates = self.app._konsole_tafel_updates_knopf
            kopf = self.app._konsole_tafel_kopf
            pruefen = self.app._konsole_tafel_knoepfe[0]
            with self.subTest(breite=breite, hoehe=hoehe):
                self.assertTrue(updates.winfo_ismapped())
                self.assertGreaterEqual(updates.winfo_x(), pruefen.winfo_x() + pruefen.winfo_width())
                self.assertLessEqual(updates.winfo_x() + updates.winfo_width(), kopf.winfo_width())
                self.assertGreaterEqual(updates.winfo_width(), updates.winfo_reqwidth())
            gemessen += 1
        self.assertGreater(gemessen, 0, "Der Bildschirm gab keine der Groessen her")


if __name__ == "__main__":
    unittest.main(verbosity=2)
