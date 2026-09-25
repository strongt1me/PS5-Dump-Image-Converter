# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 14 (24.09.2026): Sprache.

Zwei Arten von Befunden, beide an der englischen Oberflaeche sichtbar:

* **Sprachwechsel** - Texte, die beim Aufbau einmal gesetzt und danach nie
  wieder angefasst wurden: die Titelknoepfe EINSTELLUNGEN und WEITERE TOOLS
  (H1-2), die Tooltips (H1-3/H2-14) und die Tafel der Ansicht KONSOLE
  (H2-13).
* **Feste deutsche Texte** - "Unbekannt"/"Spiel" in der Infobox (H5-10), die
  Temp-Ordner-Meldungen (H4-5) und die Startmeldung zur MIT-Lizenz (H12-13).

Die Pruefungen laufen am echten Programm: Sprache umschalten (wie der Knopf
in der Titelleiste) und nachsehen, was dasteht.
"""
from __future__ import annotations

import ast
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde14")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_dienste             # noqa: E402
from ps5_validator.utils import remoteplay                  # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _en(schluessel: str, **werte) -> str:
    return STRINGS[schluessel]["en"].format(**werte) if werte else STRINGS[schluessel]["en"]


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except (tk.TclError, AttributeError):
        return ""


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class _MitProgramm(unittest.TestCase):
    """Das echte Programm, in beiden Sprachen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Siehe test_koppel_assistent: Eine gemerkte Ansicht "konsole" schaltet
        # spaeter gebaute Programme mitten in fremden Tests um.
        cls.app._konfiguration_schreiben({"ansicht": "umwandeln"})
        _WURZEL.update_idletasks()

    def setUp(self) -> None:
        if self.app._current_language != "de":
            self._umschalten()

    def tearDown(self) -> None:
        if self.app._current_language != "de":
            self._umschalten()
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()

    def _umschalten(self) -> None:
        """Wie der Sprachknopf der Titelleiste - ohne die Wahl zu speichern."""
        with mock.patch.object(self.app, "_save_setting", lambda *_a: None):
            self.app._toggle_language()


class SprachwechselTests(_MitProgramm):

    def test_titelknoepfe_folgen_dem_wechsel(self) -> None:
        """H1-2: EINSTELLUNGEN und WEITERE TOOLS blieben deutsch."""
        self._umschalten()
        self.assertEqual("en", self.app._current_language)
        self.assertEqual(_en("titlebar.settings"),
                         self.app._btn_settings_title.cget("text"))
        self.assertEqual(_en("titlebar.more_tools"),
                         self.app._btn_more_tools_title.cget("text"))

    def test_nichts_in_der_titelleiste_bleibt_deutsch(self) -> None:
        """Allgemein: kein Knopf der Titelleiste traegt nach dem Wechsel noch
        einen deutschen Text, den es auf Englisch anders gibt."""
        deutsch = {v["de"] for v in STRINGS.values()
                   if isinstance(v, dict) and v.get("de") and v.get("en")
                   and v["de"] != v["en"]}
        self._umschalten()
        reste = [_text(w) for w in _alle(self.app._titlebar_right)
                 if _text(w) in deutsch]
        self.assertEqual([], reste)

    def test_tooltips_folgen_dem_wechsel(self) -> None:
        """H1-3/H2-14: Aufgaben-Tooltips und die Hinweise an den Feldern."""
        self._umschalten()
        self.assertTrue(self.app._tooltip_schluessel)
        for tipp, schluessel in self.app._tooltip_schluessel:
            with self.subTest(schluessel=schluessel):
                self.assertEqual(_en(schluessel), tipp.text)
        modi = [m for _b, m in self.app.mode_buttons if m in self.app._MODE_TOOLTIPS]
        self.assertEqual(len(modi), len(self.app._mode_tooltip_handles))
        for modus, tipp in zip(modi, self.app._mode_tooltip_handles):
            with self.subTest(modus=modus):
                self.assertEqual(_en("mode_tooltip." + modus), tipp.text)
        self.assertEqual(_en("verify.hint"), self.app._verify_tooltip.text)
        self.assertEqual(self.app._worker_wirkung_text(), self.app._worker_tooltip.text)
        self.assertEqual(self.app._bauform_erklaerung(), self.app.bauform_tooltip.text)

    def test_kein_tooltip_mit_festem_text_im_hauptfenster(self) -> None:
        """Wer im Hauptfenster einen Tooltip mit self._t(...) anlegt, soll
        _tooltip nehmen - sonst folgt er dem Sprachwechsel nicht."""
        for name in ("_create_widgets", "_build_info_popup"):
            funde = [k.lineno for k in ast.walk(_methode(name))
                     if isinstance(k, ast.Call)
                     and getattr(k.func, "id", "") == "DelayedTooltip"
                     and any(isinstance(a, ast.Call)
                             and getattr(a.func, "attr", "") == "_t"
                             for a in k.args)]
            with self.subTest(methode=name):
                self.assertEqual([], funde)


class KonsolentafelTests(_MitProgramm):
    """H2-13: Die Tafel wird einmal gebaut und bleibt stehen."""

    def _tafel(self):
        self.app._ansicht_setzen("konsole", speichern=False)
        _WURZEL.update()
        return self.app._konsole_tafel

    def test_die_tafel_folgt_dem_wechsel(self) -> None:
        tafel = self._tafel()
        konsole = remoteplay.Konsole(adresse="10.0.0.5", name="Wohnzimmer",
                                     status=200, firmware="12.00")
        uebersicht = konsole_dienste.pruefen("")
        self.app._konsole_tafel_stand = {"konsole": konsole, "uebersicht": uebersicht,
                                         "geprueft": True, "fehler": "", "hinweis": ""}
        self.addCleanup(setattr, self.app, "_konsole_tafel_stand", None)
        self.app._konsole_tafel_beschriften()
        self._umschalten()
        texte = [_text(w) for w in _alle(tafel)]
        self.assertIn(_en("tafel.title"), texte)
        self.assertIn(_en("tafel.subtitle"), texte)
        self.assertIn(_en("tafel.check"), texte)
        tabelle = self.app._konsole_tafel_tabelle
        self.assertEqual(_en("dienste.col_dienst"), tabelle.heading("dienst", "text"))
        erste = tabelle.get_children()[0]
        dienst = konsole_dienste.KATALOG[0]
        self.assertEqual(_en(dienst.name_schluessel), tabelle.item(erste, "values")[0])
        self.assertEqual(_en("tafel.gefunden", name="Wohnzimmer",
                             zustand=_en(konsole.status_schluessel), firmware="12.00"),
                         self.app._konsole_tafel_zustand.get())
        self.assertEqual(_en("dienste.status_result", laufend=0, gesamt=len(uebersicht),
                             urteil=_en("dienste.bereit_nein")),
                         self.app._konsole_tafel_status.get())

    def test_der_faden_uebersetzt_nicht(self) -> None:
        """Uebersetzt wird im Hauptfaden - sonst friert die Sprache der
        Messung im Text ein."""
        pruefen = _methode("_konsole_tafel_pruefen")
        arbeit = next(k for k in ast.walk(pruefen)
                      if isinstance(k, ast.FunctionDef) and k.name == "_arbeit")
        aufrufe = [k.lineno for k in ast.walk(arbeit) if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_t"]
        self.assertEqual([], aufrufe)

    def test_ohne_messung_steht_noch_nicht_geprueft(self) -> None:
        self._tafel()
        self.app._konsole_tafel_stand = None
        self.app._konsole_tafel_beschriften()
        self.assertEqual(self.app._t("tafel.unbekannt"),
                         self.app._konsole_tafel_zustand.get())
        self.assertEqual(self.app._t("tafel.status_idle"),
                         self.app._konsole_tafel_status.get())


class MetadatenTests(_MitProgramm):
    """H5-10: "Unbekannt" und "Spiel" standen in der englischen Infobox."""

    def test_anzeigewerte_werden_uebersetzt(self) -> None:
        self._umschalten()
        wert = self.app._meta_anzeigewert
        self.assertEqual("Unknown", wert("publisher", "Unbekannt"))
        self.assertEqual("Game", wert("category", "Spiel"))
        self.assertEqual("Spiel", wert("title", "Spiel"), "Ein Titel bleibt ein Titel.")
        self.assertEqual("–", wert("publisher", ""))
        self.assertEqual("DLC", wert("category", "DLC"))

    def test_die_infobox_zeigt_sie_uebersetzt(self) -> None:
        self._umschalten()
        self.app._update_info_box({"title": "Spiel", "publisher": "Unbekannt",
                                   "category": "Spiel"}, None, "1 B", "")
        self.assertEqual("Unknown", self.app._meta_labels["publisher"].get())
        self.assertEqual("Game", self.app._meta_labels["category"].get())
        self.assertEqual("Spiel", self.app._meta_labels["title"].get())


class TempOrdnerTests(_MitProgramm):
    """H4-5: Die Meldungen landen in Protokoll und Fehlerdialog."""

    def test_zu_wenig_platz(self) -> None:
        self._umschalten()
        ordner = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(ordner, ignore_errors=True))
        platz = types.SimpleNamespace(total=1, used=0, free=10 * 1024 * 1024)
        with mock.patch.object(APP.shutil, "disk_usage", return_value=platz):
            ok, grund = self.app._is_temp_dir_usable(ordner)
        self.assertFalse(ok)
        self.assertTrue(grund.startswith("not enough free space"), grund)

    def test_kein_ordner(self) -> None:
        self._umschalten()
        with mock.patch.object(self.app, "_sweep_stale_temp_dirs", lambda: None), \
                mock.patch.object(self.app, "_temp_fallback_candidates", lambda _p: []):
            with self.assertRaises(OSError) as fehler:
                self.app._mkdtemp("probe_", dir_path="Z:/gibt-es-nicht")
        self.assertEqual(_en("temp.kein_ordner", detail=_en("temp.unbekannter_fehler")),
                         str(fehler.exception))

    def test_groessenabweichung_geht_ueber_schluessel(self) -> None:
        text = ast.unparse(_methode("_finalize_staged_pack_output"))
        self.assertIn("self._t('temp.groesse_abweichend'", text)
        self.assertNotIn("Größenabweichung", text)


class LizenzTests(unittest.TestCase):
    """H12-13: Die Startmeldung zur MIT-Lizenz stand fest deutsch im Protokoll."""

    def test_ohne_windows_nennt_sie_nur_das_system(self) -> None:
        with mock.patch.object(APP, "IST_WINDOWS", False):
            ok, angabe = APP._register_mit_license_runtime()
        self.assertFalse(ok)
        self.assertEqual(APP._systemname(), angabe)

    def test_unter_windows_nennt_sie_den_pfad(self) -> None:
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), REG_SZ=1,
            CreateKey=lambda _w, _p: "schluessel",
            SetValueEx=lambda *_a: None, CloseKey=lambda _k: None)
        with mock.patch.dict(sys.modules, {"winreg": winreg}), \
                mock.patch.object(APP, "IST_WINDOWS", True):
            ok, angabe = APP._register_mit_license_runtime()
        self.assertTrue(ok)
        self.assertEqual("HKCU\\Software\\PS5DumpImageConverter\\License", angabe)

    def test_der_startblock_uebersetzt(self) -> None:
        quelle = Path(APP.__file__).read_text(encoding="utf-8")
        block = quelle[quelle.index('if __name__ == "__main__":'):]
        for schluessel in ("lizenz.registriert", "lizenz.ohne_registry",
                           "lizenz.fehlgeschlagen"):
            with self.subTest(schluessel=schluessel):
                self.assertIn('app._t("%s"' % schluessel, block)
        self.assertNotIn('f"[INFO] {_mit_msg}', block)
        self.assertNotIn('f"[WARN] {_mit_msg}', block)


class TexteTests(unittest.TestCase):
    def test_zweisprachig_mit_platzhaltern(self) -> None:
        for schluessel, platzhalter in (
                ("temp.zu_wenig_platz", ("{frei}",)),
                ("temp.unbekannter_fehler", ()),
                ("temp.kein_ordner", ("{detail}",)),
                ("temp.groesse_abweichend", ("{erwartet}", "{erhalten}")),
                ("meta.wert.unbekannt", ()), ("meta.wert.spiel", ()),
                ("lizenz.registriert", ("{pfad}",)),
                ("lizenz.ohne_registry", ("{system}",)),
                ("lizenz.fehlgeschlagen", ("{fehler}",))):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel].get(sprache, "")
                    self.assertTrue(text.strip())
                    for stelle in platzhalter:
                        self.assertIn(stelle, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
