"""Waechter: das KLOG-Fenster erkennt "Call to unpatched function" und weist darauf hin.

ps5upload 12.6.16 nutzt diese Kernel-Zeile als belegtes Zeichen fuer fehlende Bibliotheken (Red Dead Redemption ohne jede
Ersatzbibliothek: genau eine solche Zeile; mit einem falschen Satz: keine). Das Programm hatte dafuer bis 21.11.2026 keine
Auswertung. Erkennung: ``ps5_validator/utils/klog_hinweise.py``; Anzeige im KLOG-Fenster (Zeile farbig, Hinweis unter der
Werkzeugleiste, auch wenn der Filter die Zeile ausblendet).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import klog_hinweise  # noqa: E402
from ps5_validator.utils.i18n import STRINGS  # noqa: E402

QUELLE = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

SPRACHEN = ("de", "en", "es", "it", "fr")


def _rumpf(name: str) -> str:
    anfang = QUELLE.index("    def %s(" % name)
    ende = QUELLE.find("\n    def ", anfang + 10)
    return QUELLE[anfang:ende]


class ErkennungTests(unittest.TestCase):
    def test_die_gemessene_zeile(self) -> None:
        self.assertEqual("fehlende_funktion",
                         klog_hinweise.hinweis_kennung("Call to unpatched function is detected!!!"))

    def test_mit_vorspann_und_beliebiger_schreibung(self) -> None:
        for zeile in ("[KERNEL] WARN: Call to unpatched function is detected!!!",
                      "call to UNPATCHED function  (libSceFoo)",
                      "12:00:01  CALL TO UNPATCHED FUNCTION"):
            with self.subTest(zeile=zeile):
                self.assertEqual("fehlende_funktion", klog_hinweise.hinweis_kennung(zeile))

    def test_gewoehnliche_zeilen_loesen_nichts_aus(self) -> None:
        for zeile in ("[KERNEL] INFO: SDK vesion: PS4:09040001 PPR:04000031",
                      "createApp PPSA01234",
                      "EXEC /app0/eboot.bin",
                      "function patched",
                      "unpatched",
                      "Call to function",
                      ""):
            with self.subTest(zeile=zeile):
                self.assertIsNone(klog_hinweise.hinweis_kennung(zeile))

    def test_keine_zeile_und_kein_text_wirft(self) -> None:
        self.assertIsNone(klog_hinweise.hinweis_kennung(None))  # type: ignore[arg-type]
        self.assertIsNone(klog_hinweise.hinweis_kennung(b"x"))  # type: ignore[arg-type]

    def test_jede_kennung_hat_einen_text(self) -> None:
        # Neue Muster ohne Text in der Oberflaeche zeigten "klog.hinweis.<kennung>" als Schluesselnamen an.
        for kennung in klog_hinweise.MELDUNGEN:
            eintrag = STRINGS.get("klog.hinweis." + kennung)
            self.assertIsNotNone(eintrag, kennung)
            for sprache in SPRACHEN:
                with self.subTest(kennung=kennung, sprache=sprache):
                    self.assertTrue(str(eintrag.get(sprache, "")).strip())


class TexteTests(unittest.TestCase):
    def test_hinweis_nennt_die_meldung_in_jeder_sprache(self) -> None:
        for sprache in SPRACHEN:
            with self.subTest(sprache=sprache):
                self.assertIn("Call to unpatched function", STRINGS["klog.hinweis.fehlende_funktion"][sprache])

    def test_englisch_ist_nicht_gleich_deutsch(self) -> None:
        eintrag = STRINGS["klog.hinweis.fehlende_funktion"]
        self.assertNotEqual(eintrag["de"], eintrag["en"])

    def test_hinweis_behauptet_nur_fehlende_bibliothek_als_meist(self) -> None:
        # Gemessen ist: Zeile da = Bibliotheken fehlen. Ob es immer so ist, ist es nicht - "meist"/"usually".
        self.assertIn("meist", STRINGS["klog.hinweis.fehlende_funktion"]["de"])
        self.assertIn("usually", STRINGS["klog.hinweis.fehlende_funktion"]["en"])


class VerdrahtungTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fenster = _rumpf("_show_klog_window")

    def test_modul_ist_eingebunden(self) -> None:
        self.assertIn("from ps5_validator.utils import klog_hinweise", QUELLE)

    def test_zeile_wird_beim_empfang_geprueft_vor_dem_filter(self) -> None:
        anfang = self.fenster.index("def _render_line(")
        rumpf = self.fenster[anfang:self.fenster.index("def _reapply_filter(")]
        self.assertIn("klog_hinweise.hinweis_kennung(line)", rumpf)
        self.assertLess(rumpf.index("klog_hinweise.hinweis_kennung(line)"), rumpf.index("_matches_filter(line)"),
                        "der Hinweis muss auch erscheinen, wenn der Filter die Zeile ausblendet")

    def test_zeile_wird_farbig_gesetzt(self) -> None:
        anfang = self.fenster.index("def _classify(")
        rumpf = self.fenster[anfang:self.fenster.index("def _matches_filter(")]
        self.assertIn('return "hinweis"', rumpf)
        self.assertIn('console.tag_configure("hinweis"', self.fenster)

    def test_hinweis_steht_ueber_dem_protokollfeld_und_geht_mit_leeren_weg(self) -> None:
        self.assertIn("before=text_frame", self.fenster)
        anfang = self.fenster.index("def _clear(")
        self.assertIn("_hinweis_verbergen()", self.fenster[anfang:self.fenster.index("def _export(")])

    def test_text_kommt_aus_der_uebersetzung(self) -> None:
        self.assertIn('self._t("klog.hinweis." + kennung)', self.fenster)

    def test_hinweis_wird_nicht_ins_protokoll_geschrieben(self) -> None:
        # Der Export gibt state["lines"] aus: der Hinweis darf dort nicht landen (nur Zeilen des Kernels).
        anfang = self.fenster.index("def _hinweis_zeigen(")
        rumpf = self.fenster[anfang:self.fenster.index("def _hinweis_verbergen(")]
        self.assertNotIn('state["lines"]', rumpf)
        self.assertNotIn("console.insert", rumpf)


if __name__ == "__main__":
    unittest.main()
