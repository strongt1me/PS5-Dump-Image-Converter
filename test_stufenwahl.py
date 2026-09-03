# -*- coding: utf-8 -*-
"""Prueft Packstufe und Pruefstufe gegen einen stillen Rueckfall.

Beide Werte werden als **Anzeigetext** gehalten, nicht als Zahl:
``compression_level_var`` traegt ``"9 - Maximal"``, ``verify_var``
traegt ``"Vollstaendig"``. Erst beim Uebernehmen wird der Text in einer
Tabelle nachgeschlagen, die in der jeweiligen Programmsprache gebaut
ist.

**Der Fehler, den diese Datei festhaelt:** Beide Handler benutzten
``.get(text, Vorgabe)``. Stand der Text nicht in der Tabelle - weil
Tabelle und Anzeige nach einem Sprachwechsel auseinanderstanden -,
setzten sie stumm die Vorgabe **und speicherten sie**.

Bei der Pruefstufe ist das der schlimmere Fall: Die Vorgabe ist
``"schnell"``. Wer eine vollstaendige Pruefung gewaehlt hatte, bekam
eine schnelle, und die Oberflaeche zeigte weiter "Vollstaendig".

Dazu kam eine Asymmetrie: ``_zstd_level_options`` wurde beim
Sprachwechsel neu gebaut, ``_verify_optionen`` **nie**. Sie ist
behoben.
"""
from __future__ import annotations

import unittest


class _Traeger:
    """Das Wenigste, was die zwei Handler brauchen."""

    def __init__(self, tabelle, text, gemerkt) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as APP

        self._APP = APP
        self.gespeichert: dict = {}
        self._text = text
        if isinstance(gemerkt, int):
            self._zstd_level_options = tabelle
            self.zstd_level = gemerkt
        else:
            self._verify_optionen = tabelle
            self.mkpfs_verify = gemerkt

    # ── Nahtstellen ────────────────────────────────────────────────
    class _Feld:
        def __init__(self, t): self._t = t
        def get(self): return self._t

    @property
    def compression_level_var(self): return self._Feld(self._text)

    @property
    def verify_var(self): return self._Feld(self._text)

    def _save_setting(self, name, wert): self.gespeichert[name] = wert

    def _schaetzung_neu_berechnen(self): pass

    def packstufe(self):
        self._APP.PS5ConverterGUI._on_compression_level_changed(self)

    def pruefstufe(self):
        self._APP.PS5ConverterGUI._on_verify_stufe_changed(self)


class PackstufeTests(unittest.TestCase):
    TABELLE = {"1 - Am schnellsten": 1, "9 - Maximal": 9}

    def test_ein_bekannter_text_wird_uebernommen(self) -> None:
        t = _Traeger(self.TABELLE, "1 - Am schnellsten", 9)
        t.packstufe()
        self.assertEqual(t.zstd_level, 1)
        self.assertEqual(t.gespeichert.get("zstd_level"), 1)

    def test_ein_unbekannter_text_laesst_die_wahl_stehen(self) -> None:
        """Der Kern.

        Frueher setzte das die Vorgabe und speicherte sie. Ein Text,
        den die Tabelle nicht kennt, heisst aber nicht "nimm die
        Vorgabe" - er heisst, dass Tabelle und Anzeige
        auseinanderstehen.
        """
        t = _Traeger(self.TABELLE, "9 - Maximum", 9)   # englischer Text
        t.packstufe()
        self.assertEqual(t.zstd_level, 9, "Die Stufe wurde umgesetzt.")
        self.assertEqual(t.gespeichert, {},
                         "Es wurde etwas gespeichert, obwohl der Text "
                         "unbekannt war.")

    def test_auch_ein_leerer_text_aendert_nichts(self) -> None:
        t = _Traeger(self.TABELLE, "", 3)
        t.packstufe()
        self.assertEqual(t.zstd_level, 3)
        self.assertEqual(t.gespeichert, {})


class PruefstufeTests(unittest.TestCase):
    """Hier wiegt der Rueckfall schwerer - die Vorgabe ist 'schnell'."""

    TABELLE = {"Schnell": "schnell", "Vollstaendig": "voll"}

    def test_ein_bekannter_text_wird_uebernommen(self) -> None:
        t = _Traeger(self.TABELLE, "Vollstaendig", "schnell")
        t.pruefstufe()
        self.assertEqual(t.mkpfs_verify, "voll")
        self.assertEqual(t.gespeichert.get("mkpfs_verify"), "voll")

    def test_ein_unbekannter_text_macht_aus_voll_nicht_schnell(self) -> None:
        """Der schlimmste Fall des ganzen Befundes.

        Wer eine vollstaendige Pruefung gewaehlt hat und die Sprache
        wechselt, bekam eine schnelle - und die Oberflaeche zeigte
        weiter "Vollstaendig". Ein Abbild galt dann als geprueft, das
        es nicht war.
        """
        t = _Traeger(self.TABELLE, "Full", "voll")     # englischer Text
        t.pruefstufe()
        self.assertEqual(t.mkpfs_verify, "voll",
                         "Aus einer vollstaendigen Pruefung wurde stumm "
                         "eine schnelle.")
        self.assertEqual(t.gespeichert, {})


class SprachwechselTests(unittest.TestCase):
    """Beide Tabellen muessen beim Sprachwechsel mitgezogen werden."""

    def test_beide_tabellen_werden_nachgezogen(self) -> None:
        """Die Asymmetrie, die den Fall ueberhaupt ermoeglichte.

        _zstd_level_options wurde beim Sprachwechsel neu gebaut,
        _verify_optionen nie.
        """
        import ast
        from pathlib import Path

        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        klasse = next(k for k in ast.walk(ast.parse(quelle))
                      if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        methode = next(m for m in klasse.body
                       if isinstance(m, ast.FunctionDef)
                       and m.name == "_apply_language")
        text = ast.unparse(methode)
        for tabelle in ("_zstd_level_options", "_verify_optionen"):
            with self.subTest(tabelle=tabelle):
                self.assertIn(
                    tabelle, text,
                    "%s wird beim Sprachwechsel nicht nachgezogen - dann "
                    "stehen Tabelle und Anzeige auseinander." % tabelle)

    def test_die_gewaehlte_stufe_ueberlebt_den_wechsel(self) -> None:
        """Nachgezogen wird die Beschriftung, nicht die Wahl."""
        import ast
        from pathlib import Path

        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8", errors="replace")
        klasse = next(k for k in ast.walk(ast.parse(quelle))
                      if isinstance(k, ast.ClassDef)
                      and k.name == "PS5ConverterGUI")
        methode = next(m for m in klasse.body
                       if isinstance(m, ast.FunctionDef)
                       and m.name == "_apply_language")
        text = ast.unparse(methode)
        # Beide merken sich die Wahl VOR dem Neubau der Tabelle.
        self.assertIn("self.zstd_level", text)
        self.assertIn("mkpfs_verify", text)


class VorgabenTests(unittest.TestCase):
    def test_die_packvorgabe_ist_die_hoechste_stufe(self) -> None:
        """Damit ein Rueckfall wenigstens nicht schlechter packt.

        Der Bericht vom 30.08.2026 behauptete einen Rueckfall auf
        Stufe 1. Nachgemessen ist die Vorgabe 9 - die Richtung stimmte
        dort nicht. Der Rueckfall selbst gab es trotzdem.
        """
        import PS5ImageConverter_Pro_FINAL_revised as APP

        self.assertEqual(APP.ZSTD_VORGABE, 9)

    def test_der_pruefrueckfall_ist_schwaecher_als_voll(self) -> None:
        """Deshalb wiegt der Rueckfall dort schwerer.

        Die drei Stufen sind aus, schnell, voll. Zurueckgefallen wurde
        auf "schnell" - nicht auf die schwaechste, aber eben auch nicht
        auf die gewaehlte. Ein Abbild galt dann als geprueft, das nur
        ueberflogen worden war.
        """
        import PS5ImageConverter_Pro_FINAL_revised as APP

        kennungen = [k for _s, k in APP.VERIFY_STUFEN]
        self.assertEqual(kennungen, ["aus", "schnell", "voll"],
                         "Die Stufen haben sich geaendert - dann ist neu "
                         "zu bewerten, was ein Rueckfall bedeutet.")
        self.assertLess(kennungen.index("schnell"), kennungen.index("voll"),
                        "schnell ist nicht mehr schwaecher als voll.")


if __name__ == "__main__":
    unittest.main()
