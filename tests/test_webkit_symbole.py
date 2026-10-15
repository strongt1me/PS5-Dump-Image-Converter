# -*- coding: utf-8 -*-
"""Die Symbole ueber den drei Knoepfen der Seite "WebKit Autoloader" (Wunsch des Nutzers vom 10.10.2026).

Entwurf des Nutzers: Die drei Wege stehen in einer Reihe - links der Installer, daneben die beiden Host-Wege -, und
ueber jedem Knopf sitzt sein Symbol ("Mit JB ELF", "Ohne JB EXE", "Ohne JB Python"). Dazu kamen die englischen
Fassungen der Symbole ("With JB", "Without JB"). Geprueft werden die Bilddateien selbst, die Wahl nach Sprache mit
Rueckfall und am echten Fenster: Lage der Symbole, Sprachwechsel, und dass sie bei kleinem Fenster verschwinden, statt
das Protokoll zu erdruecken.
"""
from __future__ import annotations

import hashlib
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("webkit_symbole")

# ERST das Hauptprogramm, DANN die Wurzel (DPI-Kenntnis des Prozesses, siehe test_rollflaeche).
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

from PIL import Image                                       # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

KLASSE = APP.PS5ConverterGUI
ORDNER = PROJEKT / KLASSE._WEBKIT_ORDNER
ARTEN = ("installer", "host_exe", "host_py")


def _datei(art: str, sprache: str) -> Path:
    return ORDNER / (KLASSE._WEBKIT_SYMBOLE[art] + ("_en" if sprache == "en" else "") + ".png")


class DateienTests(unittest.TestCase):
    def test_jedes_symbol_gibt_es_deutsch_und_englisch(self) -> None:
        for art in ARTEN:
            for sprache in ("de", "en"):
                with self.subTest(art=art, sprache=sprache):
                    self.assertTrue(_datei(art, sprache).is_file())

    def test_quadratisch_mit_durchsichtigen_ecken(self) -> None:
        """Die Ecken sind durchsichtig, nicht schwarz: Sonst stuende auf der dunkelgrauen Seite ein schwarzes Quadrat."""
        for art in ARTEN:
            for sprache in ("de", "en"):
                with self.subTest(art=art, sprache=sprache), Image.open(_datei(art, sprache)) as bild:
                    self.assertEqual("RGBA", bild.mode)
                    self.assertEqual(bild.width, bild.height)
                    self.assertGreaterEqual(bild.width, 256, "klein gezeichnet waere es auf hohen Aufloesungen unscharf")
                    for ecke in ((0, 0), (bild.width - 1, 0), (0, bild.height - 1), (bild.width - 1, bild.height - 1)):
                        self.assertEqual(0, bild.getpixel(ecke)[3])
                    self.assertEqual(255, bild.getpixel((bild.width // 2, bild.height // 2))[3])

    def test_die_sprachen_und_wege_sehen_verschieden_aus(self) -> None:
        """Ein Rueckfall auf eine Kopie des deutschen Bildes waere kein englisches Symbol."""
        pruefsummen = {(art, sprache): hashlib.sha256(_datei(art, sprache).read_bytes()).hexdigest()
                       for art in ARTEN for sprache in ("de", "en")}
        self.assertEqual(6, len(set(pruefsummen.values())))

    def test_nicht_zu_gross(self) -> None:
        """Die Symbole liegen im Bau und in jedem Archiv - 400 KB je Bild reichen."""
        for art in ARTEN:
            for sprache in ("de", "en"):
                with self.subTest(art=art, sprache=sprache):
                    self.assertLess(_datei(art, sprache).stat().st_size, 400 * 1024)


class PfadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.objekt = KLASSE.__new__(KLASSE)

    def test_die_sprache_waehlt_die_datei(self) -> None:
        for art in ARTEN:
            with self.subTest(art=art):
                self.assertEqual(str(_datei(art, "de")), str(Path(self.objekt._webkit_symbol_pfad(art, "de"))))
                self.assertEqual(str(_datei(art, "en")), str(Path(self.objekt._webkit_symbol_pfad(art, "en"))))

    def test_fehlt_das_englische_gilt_das_deutsche(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            Path(t, "symbol_installer.png").write_bytes(b"x")
            with mock.patch.object(APP, "_bundled_resource", lambda ordner, name="": str(Path(t, name))):
                self.assertEqual(str(Path(t, "symbol_installer.png")), self.objekt._webkit_symbol_pfad("installer", "en"))
                self.assertEqual("", self.objekt._webkit_symbol_pfad("host_exe", "en"), "gar kein Bild: leer")


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):
    """Die Seite am wirklichen Programm, in einem eigenen unsichtbaren Fenster."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.root = tk.Toplevel(_WURZEL)
        try:
            cls.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        cls.app = APP.PS5ConverterGUI(cls.root)
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

    def _einstellen(self, breite: int, hoehe: int, sprache: str = "de") -> None:
        if self.root.winfo_screenwidth() < breite or self.root.winfo_screenheight() < hoehe:
            self.skipTest("der Bildschirm gibt %dx%d nicht her" % (breite, hoehe))
        try:
            self.root.state("normal")        # der Aufbau maximiert das Fenster
        except Exception:  # noqa: BLE001
            pass
        self.root.geometry("%dx%d" % (breite, hoehe))
        self.app._current_language = sprache
        self.app._apply_language()
        self._ruhen(1.0)
        self.app._konsole_seite_setzen("webkit")
        self._ruhen(1.5)

    def _schilder(self) -> dict:
        return self.app._webkit_symbolschilder

    def test_gross_stehen_die_drei_symbole_je_ueber_ihrem_knopf(self) -> None:
        self._einstellen(1800, 1000)
        knoepfe = self.app._webkit_wegknoepfe
        zeilen = set()
        mitten = {}
        for art in ARTEN:
            schild, knopf = self._schilder()[art], knoepfe[art]
            with self.subTest(art=art):
                self.assertTrue(schild.winfo_ismapped(), "Symbol %s nicht sichtbar" % art)
                self.assertIsNotNone(getattr(schild, "_symbol", None), "Symbol %s ohne Bild" % art)
                self.assertLessEqual(schild.winfo_rooty() + schild.winfo_height(), knopf.winfo_rooty(),
                                     "das Symbol muss ueber dem Knopf sitzen")
                mitte_schild = schild.winfo_rootx() + schild.winfo_width() / 2
                mitte_knopf = knopf.winfo_rootx() + knopf.winfo_width() / 2
                self.assertAlmostEqual(mitte_knopf, mitte_schild, delta=3, msg="Symbol und Knopf nicht mittig")
                zeilen.add(knopf.winfo_rooty())
                mitten[art] = mitte_knopf
        self.assertEqual(1, len(zeilen), "alle drei Wege in einer Reihe")
        self.assertLess(mitten["installer"], mitten["host_exe"])
        self.assertLess(mitten["host_exe"], mitten["host_py"], "Reihenfolge: Installer, Host-Programm, Host-Skript")

    def test_die_reihe_sitzt_rechtsbuendig_und_der_installer_hat_mehr_luft(self) -> None:
        self._einstellen(1800, 1000)
        k = self.app._webkit_wegknoepfe
        rand = self.app._webkit_wege.winfo_rootx() + self.app._webkit_wege.winfo_width()
        self.assertAlmostEqual(rand, k["host_py"].winfo_rootx() + k["host_py"].winfo_width(), delta=8)
        luecke_hosts = k["host_py"].winfo_rootx() - (k["host_exe"].winfo_rootx() + k["host_exe"].winfo_width())
        luecke_installer = k["host_exe"].winfo_rootx() - (k["installer"].winfo_rootx() + k["installer"].winfo_width())
        self.assertGreater(luecke_installer, luecke_hosts + 20)

    def test_der_sprachwechsel_tauscht_die_bilder(self) -> None:
        self._einstellen(1800, 1000, "de")
        deutsch = {art: self._schilder()[art]._symbol for art in ARTEN}
        self._einstellen(1800, 1000, "en")
        englisch = {art: self._schilder()[art]._symbol for art in ARTEN}
        try:
            for art in ARTEN:
                with self.subTest(art=art):
                    self.assertIsNotNone(englisch[art])
                    self.assertIsNot(deutsch[art], englisch[art])
                    self.assertEqual(str(self._schilder()[art].cget("image")), str(englisch[art]))
        finally:
            self._einstellen(1800, 1000, "de")
        for art in ARTEN:
            self.assertIs(deutsch[art], self._schilder()[art]._symbol, "zurueck auf Deutsch: dasselbe gemerkte Bild")

    def test_klein_verschwinden_die_symbole_und_die_knoepfe_bleiben(self) -> None:
        self._einstellen(APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT)
        for art in ARTEN:
            with self.subTest(art=art):
                self.assertFalse(self._schilder()[art].winfo_ismapped(), "Symbol %s steht bei Mindestgroesse" % art)
                self.assertTrue(self.app._webkit_wegknoepfe[art].winfo_ismapped())
        self.assertGreater(self.app._webkit_protokoll.winfo_height(), 60, "das Protokoll darf nicht erdrueckt sein")

    def test_gross_und_wieder_klein_und_wieder_gross(self) -> None:
        """Die Entscheidung kippt nicht hin und her und holt die Symbole zurueck."""
        self._einstellen(1800, 1000)
        self.assertTrue(all(s.winfo_ismapped() for s in self._schilder().values()))
        self._einstellen(APP.WINDOW_MIN_WIDTH, APP.WINDOW_MIN_HEIGHT)
        self.assertFalse(any(s.winfo_ismapped() for s in self._schilder().values()))
        self._einstellen(1800, 1000)
        self.assertTrue(all(s.winfo_ismapped() for s in self._schilder().values()))

    def test_das_bild_von_itsplk_bleibt_das_einzige_mit_bild_attribut(self) -> None:
        """test_webkit_seite zaehlt Labels mit ``_bild`` - die Symbole duerfen dieses Attribut nicht tragen."""
        self._einstellen(1800, 1000)
        for schild in self._schilder().values():
            self.assertIsNone(getattr(schild, "_bild", None))


if __name__ == "__main__":
    unittest.main()
