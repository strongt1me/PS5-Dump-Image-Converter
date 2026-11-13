# -*- coding: utf-8 -*-
"""Stufenzeile mit Zeiten: Abschnitte eines Laufs mit Zustand und Dauer (nach Dump Forge, Nutzerwahl 13.11.2026)."""
from __future__ import annotations

import importlib.util
import re
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("stufenzeile")

from ps5_validator.utils import stufenzeile as sz            # noqa: E402


class Uhr:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t

    def weiter(self, s: float) -> None:
        self.t += s


def _text(schluessel: str) -> str:
    return schluessel.split(".", 1)[1].upper()


class FolgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.uhr = Uhr()
        self.f = sz.Stufenfolge.fuer("exfat_umpacken", self.uhr)

    def test_eine_neue_folge_hat_alle_abschnitte_wartend(self):
        for stufe in self.f.oberste():
            self.assertEqual(sz.WARTET, stufe.zustand)
        self.assertEqual(["phase.entpacken", "phase.integration", "phase.abbild_bauen"],
                         [s.schluessel for s in self.f.oberste()])

    def test_die_zeile_zeigt_zustand_und_zeit(self):
        self.f.beginne("phase.entpacken")
        self.uhr.weiter(723)
        self.f.fertig("phase.entpacken")
        self.f.beginne("phase.integration")
        self.uhr.weiter(130)
        self.assertEqual("✓ ENTPACKEN 12:03 · ▶ INTEGRATION 2:10 · ○ ABBILD_BAUEN · gesamt 14:13",
                         self.f.zeile(_text, mit_gesamt="gesamt"))

    def test_ein_laufender_abschnitt_zaehlt_mit(self):
        self.f.beginne("phase.entpacken")
        self.uhr.weiter(5)
        self.assertEqual(5, self.f.dauer("phase.entpacken"))
        self.uhr.weiter(5)
        self.assertEqual(10, self.f.dauer("phase.entpacken"))

    def test_ein_beendeter_abschnitt_zaehlt_nicht_weiter(self):
        self.f.beginne("phase.entpacken")
        self.uhr.weiter(5)
        self.f.fertig("phase.entpacken")
        self.uhr.weiter(100)
        self.assertEqual(5, self.f.dauer("phase.entpacken"))

    def test_ein_wartender_abschnitt_hat_keine_zeit(self):
        self.assertIsNone(self.f.dauer("phase.abbild_bauen"))
        self.assertNotRegex(self.f.zeile(_text), r"ABBILD_BAUEN \d")

    def test_der_aufrufer_kann_den_gemessenen_anfang_mitgeben(self):
        self.f.beginne("phase.entpacken", ab=self.uhr() - 60)
        self.assertEqual(60, self.f.dauer("phase.entpacken"))
        self.f.fertig("phase.entpacken", beginn=self.uhr() - 90)
        self.assertEqual(90, self.f.dauer("phase.entpacken"))

    def test_ein_kind_erscheint_beim_eltern_abschnitt_solange_es_laeuft(self):
        self.f.beginne("phase.integration")
        self.f.beginne("phase.zstd_packen")
        self.uhr.weiter(90)
        zeile = self.f.zeile(_text)
        self.assertIn("▶ INTEGRATION 1:30 (ZSTD_PACKEN 1:30)", zeile)
        self.assertNotIn("· ▶ ZSTD_PACKEN", zeile, "ein Kind steht nicht als eigener Abschnitt da")
        self.f.fertig("phase.zstd_packen")
        self.assertNotIn("(", self.f.zeile(_text))

    def test_uebersprungene_abschnitte_fehlen_in_der_zeile(self):
        self.f.uebersprungen("phase.integration")
        self.assertNotIn("INTEGRATION", self.f.zeile(_text))

    def test_fehler_und_abbruch(self):
        self.f.beginne("phase.entpacken")
        self.uhr.weiter(3)
        self.f.abschliessen_alle(erfolg=False)
        self.assertEqual(sz.FEHLER, self.f.zustand("phase.entpacken"))
        self.assertTrue(self.f.zeile(_text).startswith("✗ ENTPACKEN 0:03"))
        self.uhr.weiter(50)
        self.assertEqual(3, self.f.gesamtdauer(), "nach dem Ende zaehlt die Gesamtzeit nicht weiter")

    def test_erfolgreiches_ende_laesst_nichts_laufen(self):
        self.f.beginne("phase.entpacken")
        self.f.abschliessen_alle(erfolg=True)
        self.assertEqual(sz.FERTIG, self.f.zustand("phase.entpacken"))

    def test_ein_unbekannter_abschnitt_wird_hinten_angefuegt(self):
        self.f.beginne("phase.messen")
        self.assertEqual("phase.messen", self.f.oberste()[-1].schluessel)

    def test_eine_leere_folge_fuellt_sich_beim_beginnen(self):
        f = sz.Stufenfolge(uhr=self.uhr)
        self.assertTrue(f.leer())
        self.assertEqual("", f.zeile(_text))
        f.beginne("phase.zstd_packen")
        self.assertFalse(f.leer())
        self.assertIn("▶ ZSTD_PACKEN", f.zeile(_text))

    def test_ein_unbekannter_weg_ergibt_eine_leere_folge(self):
        self.assertTrue(sz.Stufenfolge.fuer("gibt_es_nicht", self.uhr).leer())

    def test_neue_wege_tragen_sich_ein(self):
        sz.registrieren("stufe3_test", ["phase.messen", ("phase.schreiben", None), ("phase.pruefen", None)])
        try:
            f = sz.Stufenfolge.fuer("stufe3_test", self.uhr)
            self.assertEqual(["phase.messen", "phase.schreiben", "phase.pruefen"],
                             [s.schluessel for s in f.oberste()])
        finally:
            sz.FOLGEN.pop("stufe3_test", None)

    def test_ein_wiederholter_beginn_setzt_die_zeit_neu(self):
        self.f.beginne("phase.entpacken")
        self.uhr.weiter(50)
        self.f.beginne("phase.entpacken")
        self.uhr.weiter(2)
        self.assertEqual(2, self.f.dauer("phase.entpacken"))

    def test_fadensicher_unter_gleichzeitigem_melden_und_lesen(self):
        f = sz.Stufenfolge()
        fehler: list[Exception] = []

        def melden(n: int) -> None:
            try:
                for i in range(300):
                    f.beginne("phase.s%d_%d" % (n, i))
                    f.fertig("phase.s%d_%d" % (n, i))
            except Exception as exc:                          # noqa: BLE001
                fehler.append(exc)

        def lesen() -> None:
            try:
                for _ in range(300):
                    f.zeile(_text, mit_gesamt="g")
            except Exception as exc:                          # noqa: BLE001
                fehler.append(exc)

        faeden = [threading.Thread(target=melden, args=(n,)) for n in range(4)] + [threading.Thread(target=lesen)]
        for t in faeden:
            t.start()
        for t in faeden:
            t.join(30)
        self.assertEqual([], fehler)


class FormatTests(unittest.TestCase):
    def test_kurze_dauern(self):
        self.assertEqual("0:00", sz.kurz_dauer(0))
        self.assertEqual("0:59", sz.kurz_dauer(59))
        self.assertEqual("12:03", sz.kurz_dauer(723))
        self.assertEqual("59:59", sz.kurz_dauer(3599))
        self.assertEqual("1:00:00", sz.kurz_dauer(3600))
        self.assertEqual("2:03:04", sz.kurz_dauer(7384))
        self.assertEqual("0:00", sz.kurz_dauer(-5))

    def test_der_text_schluessel(self):
        self.assertEqual("stufe.entpacken", sz.text_schluessel("phase.entpacken"))
        self.assertEqual("stufe.messen", sz.text_schluessel("messen"))


def _lade():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", ROOT / "PS5ImageConverter_Pro_FINAL_revised.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Etikett:
    """Ein Etikett wie ttk.Label, soweit die Stufenzeile es braucht."""

    def __init__(self) -> None:
        self.text = ""
        self.sichtbar = False

    def cget(self, _name):
        return self.text

    def config(self, **kw):
        self.text = kw.get("text", self.text)

    def winfo_ismapped(self):
        return self.sichtbar

    def grid(self):
        self.sichtbar = True

    def grid_remove(self):
        self.sichtbar = False


class VerdrahtungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.GUI = _lade().PS5ConverterGUI
        self.app = self.GUI.__new__(self.GUI)
        self.app._t = lambda k, **w: k
        self.app._append_to_log = lambda _z: None
        self.app.stufen_label = _Etikett()
        self.app.is_running = True
        self.app._stufen = None
        self.neu_gezeichnet = 0
        self.app._schedule_caption_redraw = lambda _f: setattr(self, "neu_gezeichnet", self.neu_gezeichnet + 1)
        self.app._redraw_content_captions = lambda: None

    def test_die_phasenmeldung_des_protokolls_schliesst_den_abschnitt(self):
        self.app._stufen_neu("exfat_umpacken")
        begonnen = self.app._stufe_start("phase.entpacken")
        self.assertEqual(sz.LAEUFT, self.app._stufen.zustand("phase.entpacken"))
        self.app._phase_dauer_melden("phase.entpacken", begonnen)
        self.assertEqual(sz.FERTIG, self.app._stufen.zustand("phase.entpacken"))

    def test_ohne_gestartete_folge_legt_der_erste_abschnitt_eine_an(self):
        self.app._stufe_start("phase.zstd_packen")
        self.assertIsNotNone(self.app._stufen)
        self.assertEqual(sz.LAEUFT, self.app._stufen.zustand("phase.zstd_packen"))

    def test_die_zeile_erscheint_und_verschwindet_mit_dem_lauf(self):
        self.app._stufen_neu("exfat_umpacken")
        self.app._stufe_start("phase.entpacken")
        self.app._stufenzeile_zeigen()
        self.assertTrue(self.app.stufen_label.sichtbar)
        self.assertIn("stufe.entpacken", self.app.stufen_label.text)
        self.assertEqual(1, self.neu_gezeichnet)
        self.app._stufenzeile_zeigen()
        self.assertEqual(1, self.neu_gezeichnet, "ein unveraenderter Text zeichnet nichts neu")
        self.app._stufen = None
        self.app._stufenzeile_zeigen()
        self.assertFalse(self.app.stufen_label.sichtbar)
        self.assertEqual("", self.app.stufen_label.text)

    def test_nach_dem_lauf_bleibt_die_zeile_stehen_und_ein_unfertiger_abschnitt_gilt_als_fehler(self):
        self.app._stufen_neu("exfat_umpacken")
        self.app._stufe_start("phase.entpacken")
        self.app.is_running = False
        self.app._stufenzeile_zeigen()
        self.assertEqual(sz.FEHLER, self.app._stufen.zustand("phase.entpacken"))
        self.assertTrue(self.app.stufen_label.sichtbar)
        self.assertIn("✗", self.app.stufen_label.text)

    def test_eine_fehlerhafte_anzeige_stoert_nichts(self):
        self.app.stufen_label = None
        self.app._stufenzeile_zeigen()                       # kein Etikett: still
        self.app.stufen_label = object()                      # kaputtes Etikett: Fehler wird geschluckt
        self.app._stufen_neu("exfat_umpacken")
        self.app._stufe_start("phase.entpacken")
        self.app._stufenzeile_zeigen()

    def test_alle_abschnitte_im_hauptprogramm_haben_kurzen_und_langen_text_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        benutzt = set(re.findall(r'_stufe_start\("(phase\.[a-z_]+)"\)', quelle))
        benutzt |= {k for k, _ in (s for folge in sz.FOLGEN.values() for s in folge)}
        self.assertGreaterEqual(len(benutzt), 7)
        for schluessel in sorted(benutzt):
            for key in (schluessel, sz.text_schluessel(schluessel)):
                self.assertIn(key, STRINGS, key)
                for sprache in SUPPORTED_LANGUAGES:
                    self.assertTrue(STRINGS[key][sprache], "%s/%s" % (key, sprache))
        for sprache in SUPPORTED_LANGUAGES:
            self.assertTrue(STRINGS["stufe.gesamt"][sprache])

    def test_jeder_abschnitt_beginnt_ueber_die_stufenzeile(self):
        """Wächter: Wer ``_phase_dauer_melden`` ruft, hat vorher ``_stufe_start`` gerufen (sonst fehlt der Anfang)."""
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        gemeldet = set(re.findall(r'_phase_dauer_melden\("(phase\.[a-z_]+)"', quelle))
        begonnen = set(re.findall(r'_stufe_start\("(phase\.[a-z_]+)"\)', quelle))
        self.assertEqual(set(), gemeldet - begonnen)

    def test_das_etikett_sitzt_im_raster_unter_der_telemetrie(self):
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertRegex(quelle, r"self\.stufen_label\.grid\(row=7, column=0")
        self.assertIn("self._content_caption_labels.append(self.stufen_label)", quelle)


if __name__ == "__main__":
    unittest.main()
