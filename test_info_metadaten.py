"""Regressionstests: Metadaten im Info-Fenster waehrend und nach einer Aufgabe.

Beobachtet beim Praxistest: Waehrend einer laufenden Konvertierung blieben im
Fenster "Spiel-Info - Updates & Patches" Metadaten, Updates und Downloads aus.

Ursache war keine Stoerung, sondern eine bewusste Sperre: `_on_source_path_changed`
steigt bei `is_running` sofort aus, weil eine Metadaten-Aufloesung einen mehrere
GB grossen Container lesen und der laufenden Arbeit Platte und CPU wegnehmen
wuerde. Der Abbruch geschah aber stillschweigend - das Fenster blieb leer oder
zeigte weiterhin die Werte der zuvor gewaehlten Quelle, was stimmig aussah und
es nicht war.

Behoben durch: sichtbarer Hinweis waehrend des Laufs, und automatisches
Nachholen, sobald die Aufgabe beendet ist.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class _Var:
    """Ersatz fuer tk.StringVar ohne Tk-Abhaengigkeit."""

    def __init__(self, wert: str = "") -> None:
        self._wert = wert

    def get(self) -> str:
        return self._wert

    def set(self, wert: str) -> None:
        self._wert = str(wert)


def _gui(**felder):
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._patch_status_var = _Var("Bereit")
    for name in ("_info_title_var", "_info_id_var", "_info_version_var",
                 "_info_firmware_var", "_info_region_var", "_info_category_var",
                 "_info_publisher_var", "_info_method_var"):
        setattr(gui, name, _Var("alter Wert"))
    gui._patch_tree = None
    gui._t = lambda schluessel, **kw: APP.i18n_translate("de", schluessel, **kw)
    gui._append_to_log = lambda *a, **k: None
    for k, v in felder.items():
        setattr(gui, k, v)
    return gui


class HinweisTests(unittest.TestCase):
    """Waehrend des Laufs muss dastehen, warum nichts kommt."""

    def test_statuszeile_nennt_den_grund(self) -> None:
        gui = _gui()
        APP.PS5ConverterGUI._show_meta_deferred_hint(gui)
        self.assertIn("Abschluss", gui._patch_status_var.get())

    def test_alte_werte_werden_nicht_stehen_gelassen(self) -> None:
        """Das eigentliche Uebel: stimmig aussehende Werte der Vorgaengerquelle."""
        gui = _gui()
        APP.PS5ConverterGUI._show_meta_deferred_hint(gui)
        for name in ("_info_title_var", "_info_id_var", "_info_version_var",
                     "_info_region_var"):
            with self.subTest(feld=name):
                self.assertNotEqual(getattr(gui, name).get(), "alter Wert")

    def test_methode_sagt_dass_gewartet_wird(self) -> None:
        gui = _gui()
        APP.PS5ConverterGUI._show_meta_deferred_hint(gui)
        self.assertIn("wartet", gui._info_method_var.get().lower())

    def test_ohne_variablen_kein_absturz(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._patch_status_var = _Var()
        gui._patch_tree = None
        gui._t = lambda s, **kw: s
        APP.PS5ConverterGUI._show_meta_deferred_hint(gui)   # darf nicht werfen


class NachholenTests(unittest.TestCase):
    """Nach dem Ende der Aufgabe wird die vorgemerkte Quelle nachgeladen."""

    def _mit_quelle(self, vorgemerkt: str, aktuell: str, laeuft: bool = False):
        gerufen = []
        gui = _gui(
            _deferred_meta_src=vorgemerkt,
            source_path=_Var(aktuell),
            is_running=laeuft,
        )
        gui._on_source_path_changed = lambda *a: gerufen.append(True)
        APP.PS5ConverterGUI._nachholen_zurueckgestellte_metadaten(gui)
        return gui, gerufen

    def test_gleiche_quelle_wird_nachgeladen(self) -> None:
        gui, gerufen = self._mit_quelle(r"D:\Spiele\Teardown", r"D:\Spiele\Teardown")
        self.assertEqual(len(gerufen), 1)
        self.assertEqual(gui._deferred_meta_src, "", "Vormerkung muss verbraucht sein")

    @unittest.skipUnless(sys.platform == "win32",
                         "Nur Windows vergleicht Pfade ohne Ruecksicht auf Gross-/Kleinschreibung")
    def test_gross_kleinschreibung_egal_unter_windows(self) -> None:
        """Windows: os.path.normcase() macht beide Schreibweisen gleich."""
        _gui_, gerufen = self._mit_quelle(r"D:\Spiele\Teardown", r"d:\spiele\teardown")
        self.assertEqual(len(gerufen), 1)

    @unittest.skipIf(sys.platform == "win32",
                     "Gilt nur fuer Dateisysteme, die Gross-/Kleinschreibung unterscheiden")
    def test_gross_kleinschreibung_zaehlt_auf_posix(self) -> None:
        """Linux/macOS: Zwei Schreibweisen sind zwei verschiedene Ordner.

        os.path.normcase() ist dort absichtlich wirkungslos. Die Vormerkung
        darf deshalb nicht greifen - sonst wuerden die Metadaten eines gar
        nicht gewaehlten Ordners nachgeladen.
        """
        _gui_, gerufen = self._mit_quelle("/spiele/Teardown", "/spiele/teardown")
        self.assertEqual(gerufen, [])

    def test_inzwischen_andere_quelle_gewaehlt(self) -> None:
        """Dann gilt die neue Wahl - nicht die alte Vormerkung."""
        _gui_, gerufen = self._mit_quelle(r"D:\Spiele\Teardown", r"D:\Spiele\Dirt 5")
        self.assertEqual(gerufen, [])

    def test_ohne_vormerkung_passiert_nichts(self) -> None:
        _gui_, gerufen = self._mit_quelle("", r"D:\Spiele\Teardown")
        self.assertEqual(gerufen, [])

    def test_naechste_aufgabe_laeuft_schon_wieder(self) -> None:
        _gui_, gerufen = self._mit_quelle(r"D:\Spiele\Teardown", r"D:\Spiele\Teardown",
                                          laeuft=True)
        self.assertEqual(gerufen, [])

    def test_hinweis_wird_beim_nachladen_zurueckgenommen(self) -> None:
        gui, _ = self._mit_quelle(r"D:\Spiele\Teardown", r"D:\Spiele\Teardown")
        self.assertNotIn("Abschluss", gui._patch_status_var.get())


class VerdrahtungTests(unittest.TestCase):
    """Die beiden Haken im Quelltext."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelltext = QUELLDATEI.read_text(encoding="utf-8")

    def test_sperre_merkt_die_quelle_statt_still_auszusteigen(self) -> None:
        start = self.quelltext.index("def _on_source_path_changed")
        block = self.quelltext[start:start + 4000]
        stelle = block.index("if self.is_running:")
        self.assertIn("_deferred_meta_src", block[stelle:stelle + 300])
        self.assertIn("_show_meta_deferred_hint", block[stelle:stelle + 300])

    def test_gemeinsamer_ausgang_holt_nach(self) -> None:
        self.assertIn("_nachholen_zurueckgestellte_metadaten", self.quelltext)
        stelle = self.quelltext.index("_maybe_shutdown_after_task,")
        self.assertIn("_nachholen_zurueckgestellte_metadaten",
                      self.quelltext[stelle:stelle + 800])

    def test_meldungen_sind_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("info_popup.status_deferred", "info_popup.method_deferred",
                           "info_popup.log_deferred_reload"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
