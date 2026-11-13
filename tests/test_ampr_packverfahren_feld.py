# -*- coding: utf-8 -*-
"""Packverfahren (LZ4 / zstd) unter der Methode in der AMPR-Einbauzeile (Nutzerwunsch 11.11.2026).

Das Feld sitzt in der zweiten Zeile unter "Normal"/"Asset-Pack" und schreibt dieselbe Einstellung wie das Feld in den
Einstellungen. Regeln:

* Waehlbar nur bei angehaktem AMPR EMU **und** Methode Asset-Pack; bei Normal bleibt es ausgegraut (der gespeicherte Wert
  steht weiter darin), und es wird nichts mit LZ4 oder zstd gepackt.
* zstd: Die Versionsliste zeigt nur ampr-emu-ng, und ist die gewaehlte Fassung nicht NG, wird die neueste normale
  NG-Fassung gewaehlt (nicht die Debug-Fassung). Eine schon von Hand gewaehlte NG-Fassung bleibt.
* LZ4: Alles bleibt frei.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("packverfahren_feld")

from ps5_validator.utils.i18n import STRINGS                # noqa: E402

HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


def _lade():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class QuelltextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import ast
        text = HAUPT.read_text(encoding="utf-8")
        zeilen = text.splitlines()
        cls.f = {}
        for k in ast.walk(ast.parse(text)):
            if isinstance(k, ast.FunctionDef):
                cls.f[k.name] = "\n".join(zeilen[k.lineno - 1:k.end_lineno])

    def test_das_feld_haengt_an_methode_und_haken(self):
        quelle = self.f["_ampr_pack_combo_schalten"]
        self.assertIn("AMPR_METHODE_ASSETPACK", quelle)
        self.assertIn("ampr_integrate_var", quelle)

    def test_die_integrationsschaltung_ruft_es(self):
        self.assertIn("_ampr_pack_combo_schalten()", self.f["_on_integration_changed"])

    def test_der_einstellungsdialog_zieht_das_feld_nach(self):
        text = HAUPT.read_text(encoding="utf-8")
        self.assertIn("self._ampr_pack_combo_schalten()", text.split("def _verfahren_gewaehlt")[1][:900])

    def test_texte(self):
        for sprache in ("de", "en", "es", "it", "fr"):
            self.assertTrue(STRINGS["ampr_pack.verfahren_hint"][sprache])
            self.assertTrue(STRINGS["ampr_pack.stufe_hint"][sprache])
            self.assertTrue(STRINGS["ampr_pack.stufe_gesperrt"][sprache])

    def test_die_packstufe_folgt_dem_verfahren_und_der_sperre(self):
        self.assertIn("_ampr_stufe_combo_schalten()", self.f["_ampr_pack_combo_schalten"])
        self.assertIn("_ampr_stufe_combo_schalten()", self.f["_ampr_pack_gewaehlt"])
        quelle = self.f["_ampr_stufe_combo_schalten"]
        self.assertIn("AMPR_METHODE_ASSETPACK", quelle)
        self.assertIn("ampr_integrate_var", quelle)

    def test_das_packverfahren_steht_unter_dem_ersten_schalter_der_kette(self):
        """Nutzerwunsch 12.11.2026: Verfahren, Pfeil und Stufe beginnen unter dem ersten Schalter (vorher NG, jetzt die
        Methode, weil sie vor der Fassung steht). Unter der Fassung ragte die Stufe aus der Karte."""
        quelle = self.f["_dlc_zeile_setzen"]
        self.assertIn("ampr_methode_combo", quelle)
        self.assertNotIn("ampr_version_combo", quelle)

    def test_der_einstellungsdialog_zieht_die_packstufe_nach(self):
        text = HAUPT.read_text(encoding="utf-8")
        self.assertIn("self._ampr_stufe_combo_schalten()", text.split("def _lz4_gewaehlt")[1][:900])
        self.assertIn("self._ampr_stufe_combo_schalten()", text.split("def _zstd_gewaehlt")[1][:900])


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        app = self.app
        app._save_setting("ampr_pack_verfahren", "lz4")
        app._save_setting("integrate_ampr_version", "")
        app.ampr_integrate_var.set(False)
        app.ampr_methode_var.set(next(t for t, k in app._ampr_methode_options.items()
                                      if k == self.haupt.AMPR_METHODE_NORMAL))
        app._ampr_versionsliste_fuellen()
        app._on_integration_changed(speichern=False)
        self.addCleanup(self._zurueck)

    def _zurueck(self) -> None:
        self.app._save_setting("ampr_pack_verfahren", "lz4")

    def _methode(self, neu: str) -> None:
        """Waehlt die Methode ueber die Tabelle der Oberflaeche (Anzeigetext -> Kennung), unabhaengig von der Sprache."""
        app = self.app
        ziel = self.haupt.AMPR_METHODE_ASSETPACK if neu == "pack" else self.haupt.AMPR_METHODE_NORMAL
        text = next(t for t, kennung in app._ampr_methode_options.items() if kennung == ziel)
        app.ampr_methode_var.set(text)
        app._on_ampr_methode_changed()
        app._ampr_pack_combo_schalten()

    def _zustand(self) -> str:
        return str(self.app.ampr_pack_combo.cget("state"))

    def test_ohne_haken_gesperrt(self):
        self.assertEqual("disabled", self._zustand())

    def test_bei_normal_gesperrt_auch_mit_haken(self):
        self.app.ampr_integrate_var.set(True)
        self.app._on_integration_changed(speichern=False)
        self.assertEqual("disabled", self._zustand())

    def test_bei_asset_pack_und_haken_waehlbar(self):
        self.app.ampr_integrate_var.set(True)
        self.app._on_integration_changed(speichern=False)
        self._methode("pack")
        self.assertEqual("readonly", self._zustand())

    def test_zurueck_auf_normal_sperrt_wieder_und_zeigt_den_gespeicherten_wert(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self._methode("normal")
        self.assertEqual("disabled", self._zustand())
        self.assertEqual("zstd", app._ampr_pack_var.get())

    def test_zstd_waehlt_die_neueste_normale_ng_fassung(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app.ampr_version_var.set(next(iter(app._ampr_versionsauswahl)))          # irgendeine packfaehige, nicht NG
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        wahl = app._ampr_versionsauswahl[app.ampr_version_var.get()]
        self.assertEqual("ng", str(wahl["variant"]).lower(), "neueste normale NG-Fassung, nicht die Debug-Fassung")
        alle = [e for e in app._ampr_versionsauswahl.values() if str(e["variant"]).lower() == "ng"]
        self.assertEqual(alle[0]["version"], wahl["version"], "die neueste steht in der Liste oben")
        self.assertEqual("zstd", app._ampr_pack_verfahren())
        self.assertTrue(all(str(e["variant"]).lower() in ("ng", "ng-debug")
                            for e in app._ampr_versionsauswahl.values()), "bei zstd bietet die Liste nur NG an")

    def test_eine_von_hand_gewaehlte_ng_fassung_bleibt(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        ng = [b for b, e in app._ampr_versionsauswahl.items() if str(e["variant"]).lower() == "ng"]
        waehlen = ng[1] if len(ng) > 1 else ng[0]
        app.ampr_version_var.set(waehlen)
        app._save_setting("integrate_ampr_version", waehlen)
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self.assertEqual(waehlen, app.ampr_version_var.get())

    def test_lz4_laesst_die_wahl_frei(self):
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        app._ampr_pack_var.set("LZ4")
        app._ampr_pack_gewaehlt()
        self.assertEqual("lz4", app._ampr_pack_verfahren())
        varianten = {str(e["variant"]).lower() for e in app._ampr_versionsauswahl.values()}
        self.assertTrue(varianten - {"ng", "ng-debug"}, "bei LZ4 stehen wieder alle packfaehigen Fassungen da")

    def test_der_tooltip_sagt_beim_gesperrten_feld_wann_es_frei_wird(self):
        app = self.app
        tipp = app._ampr_pack_tooltip
        self.assertEqual(app._t("ampr_pack.verfahren_gesperrt"), tipp.text)       # ohne Haken, Normal
        self.assertIn("Asset-Pack", tipp.text)
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self.assertEqual(app._t("ampr_pack.verfahren_gesperrt"), tipp.text)       # Haken, aber Normal
        self._methode("pack")
        self.assertEqual(app._t("ampr_pack.verfahren_hint"), tipp.text)           # frei: die Erklaerung
        self._methode("normal")
        self.assertEqual(app._t("ampr_pack.verfahren_gesperrt"), tipp.text)

    def test_der_tooltip_zeigt_sich_auch_am_gesperrten_feld(self):
        """Ein ttk-Feld im Zustand disabled bekommt weiter <Enter>; ``_show`` baut das Hinweisfenster mit dem Text."""
        tipp = self.app._ampr_pack_tooltip
        tipp._show()
        try:
            self.assertIsNotNone(tipp._tip_window, "der Hinweis erscheint, auch wenn das Feld gesperrt ist")
        finally:
            tipp._hide()

    def test_unbekannte_auswahl_aendert_nichts(self):
        app = self.app
        app._ampr_pack_var.set("irgendwas")
        with mock.patch.object(app, "_save_setting") as speichern:
            app._ampr_pack_gewaehlt()
        speichern.assert_not_called()

    # ----- Packstufe rechts neben dem Packverfahren (Nutzerwunsch 12.11.2026) -----------------------------------
    def _stufe_zustand(self) -> str:
        return str(self.app.ampr_stufe_combo.cget("state"))

    def _stufe_werte(self) -> list[str]:
        return list(self.app.ampr_stufe_combo.cget("values"))

    def _pack_frei(self, verfahren: str = "lz4") -> None:
        app = self.app
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self._methode("pack")
        app._ampr_pack_var.set("zstd" if verfahren == "zstd" else "LZ4")
        app._ampr_pack_gewaehlt()

    def test_packstufe_sitzt_rechts_neben_dem_packverfahren(self):
        info = self.app.ampr_stufe_combo.place_info()
        self.assertEqual(str(self.app.ampr_pack_combo), str(info["in"]), "bezogen auf das Packverfahren")
        self.assertEqual("w", info["anchor"], "ihre linke Kante am rechten Rand des Verfahrens")
        self.assertEqual(1.0, float(info["relx"]))
        self.assertGreater(int(info["x"]), 0, "mit etwas Luft nach rechts")

    def test_ein_pfeil_steht_zwischen_verfahren_und_stufe(self):
        """Nutzerwunsch 12.11.2026: Der Pfeil zeigt, dass die Stufe zum Verfahren links davon gehoert."""
        app = self.app
        pfeil = app.ampr_stufe_pfeil
        info = pfeil.place_info()
        self.assertEqual(str(app.ampr_pack_combo), str(info["in"]))
        self.assertEqual(1.0, float(info["relx"]))
        x_pfeil = int(info["x"])
        x_stufe = int(app.ampr_stufe_combo.place_info()["x"])
        self.assertGreaterEqual(x_pfeil, 0)
        self.assertEqual(x_pfeil + app._PFEIL_BREITE + app._STUFE_ABSTAND, x_stufe,
                         "der Pfeil liegt zwischen Verfahren und Stufe, mit Luft auf beiden Seiten")

    def test_in_der_einbauzeile_steht_die_methode_vor_der_fassung_mit_einem_pfeil_dazwischen(self):
        """Nutzerwunsch 12.11.2026: NG und Normal getauscht - erst die Methode, dann die Fassung."""
        app = self.app
        kette = [(w, a) for w, a in app._kartenzeilen()[1] if w is not None]
        namen = [next(n for n in dir(app) if getattr(app, n, None) is w and n.endswith(("_check", "_combo")))
                 for w, _a in kette]
        self.assertEqual(["ampr_integrate_check", "ampr_methode_combo", "ampr_version_combo", "ampr_playgo_check",
                          "backport_integrate_check", "backport_fw_combo"], namen)
        abstand = {n: a for n, (_w, a) in zip(namen, kette)}
        self.assertEqual(app._ZEILE_ABSTAND_PFEIL, abstand["ampr_version_combo"], "die Luecke fuer den Pfeil")
        self.assertEqual(app._ZEILE_ABSTAND_ENG, abstand["ampr_methode_combo"], "Haken und Methode gehoeren eng zusammen")

    def test_zwischen_zielformat_kompression_worker_und_pruefung_stehen_pfeile(self):
        app = self.app
        obere = [(w, a) for w, a in app._kartenzeilen()[0] if w is not None]
        self.assertEqual([app.compression_combo, app.worker_knob, app.verify_combo], [w for w, _a in obere])
        self.assertEqual([0, app._ZEILE_ABSTAND_PFEIL, app._ZEILE_ABSTAND_PFEIL], [a for _w, a in obere])
        self.assertEqual(app._ZEILE_ABSTAND_PFEIL, int(str(app.format_combo.grid_info()["padx"][-1])),
                         "auch zwischen Zielformat und Kompression ist die Luecke so breit wie der Pfeil")
        gebraucht = {"pfeil_format", "pfeil_kompression", "pfeil_worker", "pfeil_methode"}
        self.assertEqual(gebraucht, {n for n, _l, _r in app._PFEILE_PAARE})
        for name, links, _rechts in app._PFEILE_PAARE:
            info = getattr(app, name).place_info()
            self.assertEqual(str(getattr(app, links)), str(info["in"]), name)
            self.assertEqual(1.0, float(info["relx"]), name)
        self.assertLessEqual(app._PFEIL_BREITE + 2, app._ZEILE_ABSTAND_PFEIL, "der Pfeil passt in die Luecke")

    def test_der_pfeil_zur_fassung_folgt_dem_haken_ampr_emu(self):
        app = self.app
        self.assertFalse(app.pfeil_methode._aktiv, "ohne Haken blass")
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self.assertTrue(app.pfeil_methode._aktiv)

    def test_der_pfeil_wird_mit_dem_verfahren_gesperrt_und_freigegeben(self):
        app = self.app
        self.assertFalse(app.ampr_stufe_pfeil._aktiv, "ohne Haken gesperrt")
        self._pack_frei("lz4")
        self.assertTrue(app.ampr_stufe_pfeil._aktiv)
        self._methode("normal")
        self.assertFalse(app.ampr_stufe_pfeil._aktiv)

    def test_der_pfeil_zeichnet_sich_ohne_fehler_und_haelt_ein_bild(self):
        app = self.app
        pfeil = app.ampr_stufe_pfeil
        pfeil._redraw()
        pfeil.nachziehen()
        self.assertIsNotNone(pfeil._foto)

    def test_packstufe_ist_gesperrt_wie_das_verfahren(self):
        app = self.app
        self.assertEqual("disabled", self._stufe_zustand(), "ohne Haken")
        app.ampr_integrate_var.set(True)
        app._on_integration_changed(speichern=False)
        self.assertEqual("disabled", self._stufe_zustand(), "Haken, aber Normal")
        self._methode("pack")
        self.assertEqual("readonly", self._stufe_zustand(), "Haken und Asset-Pack")
        self._methode("normal")
        self.assertEqual("disabled", self._stufe_zustand(), "zurueck auf Normal")

    def test_packstufe_zeigt_bei_lz4_die_lz4_stufen(self):
        self._pack_frei("lz4")
        werte = self._stufe_werte()
        self.assertEqual(9, len(werte), werte)
        self.assertEqual(self.app._t("settings_dialog.lz4_stufe_vorgabe", stufe=9), self.app._ampr_stufe_var.get())
        self.assertTrue(any(w.startswith("12 ") for w in werte))
        self.assertFalse(any(w.startswith("22 ") for w in werte), "keine zstd-Stufen bei LZ4")

    def test_packstufe_zeigt_bei_zstd_die_zstd_stufen(self):
        self._pack_frei("zstd")
        werte = self._stufe_werte()
        self.assertEqual([str(s) for s in (1, 3, 5, 7, 9, 12, 15, 19, 22)],
                         [w.split(" ")[0] for w in werte], werte)
        self.assertEqual(dict(self.app._ampr_stufen_tabelle("zstd", kurz=True))[5], self.app._ampr_stufe_var.get())
        self.assertNotIn("(", self.app._ampr_stufe_var.get(), "Klammerzusaetze passen nicht in die Einbauzeile")

    def test_umschalten_des_verfahrens_tauscht_die_stufen(self):
        app = self.app
        self._pack_frei("lz4")
        lz4 = self._stufe_werte()
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        zstd = self._stufe_werte()
        self.assertNotEqual(lz4, zstd)
        app._ampr_pack_var.set("LZ4")
        app._ampr_pack_gewaehlt()
        self.assertEqual(lz4, self._stufe_werte())

    def test_die_gewaehlte_stufe_geht_in_die_einstellung_des_verfahrens(self):
        app = self.app
        self._pack_frei("lz4")
        self.addCleanup(app._save_setting, "ampr_lz4_stufe", 9)
        self.addCleanup(app._save_setting, "ampr_zstd_stufe", 5)
        app._save_setting("ampr_zstd_stufe", 5)
        app._ampr_stufe_var.set(dict(app._ampr_stufen_tabelle("lz4", kurz=True))[12])
        app._ampr_stufe_gewaehlt()
        self.assertEqual(12, app._ampr_lz4_stufe())
        self.assertEqual(5, app._ampr_zstd_stufe(), "Gegenprobe: die zstd-Stufe bleibt, wie sie war")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        app._ampr_stufe_var.set(dict(app._ampr_stufen_tabelle("zstd", kurz=True))[19])
        app._ampr_stufe_gewaehlt()
        self.assertEqual(19, app._ampr_zstd_stufe())
        self.assertEqual(12, app._ampr_lz4_stufe(), "Gegenprobe: die LZ4-Stufe bleibt, wie sie war")

    def test_gesperrt_steht_die_gespeicherte_stufe_weiter_drin(self):
        app = self.app
        self.addCleanup(app._save_setting, "ampr_zstd_stufe", 5)
        app._save_setting("ampr_zstd_stufe", 15)
        app._save_setting("ampr_pack_verfahren", "zstd")
        app._ampr_pack_combo_schalten()
        self.assertEqual("disabled", self._stufe_zustand())
        self.assertEqual("15", app._ampr_stufe_var.get())

    def test_die_einstellungsdialog_aenderung_zieht_das_feld_nach(self):
        app = self.app
        self._pack_frei("zstd")
        self.addCleanup(app._save_setting, "ampr_zstd_stufe", 5)
        app._save_setting("ampr_zstd_stufe", 9)
        app._ampr_stufe_combo_schalten()
        self.assertEqual(dict(app._ampr_stufen_tabelle("zstd", kurz=True))[9], app._ampr_stufe_var.get())

    def test_eine_lz4_stufe_von_1_bis_4_zeigt_die_1_unbrauchbares_die_vorgabe(self):
        app = self.app
        self.addCleanup(app._save_setting, "ampr_lz4_stufe", 9)
        app._save_setting("ampr_lz4_stufe", 3)
        self.assertEqual(1, app._ampr_stufe_angezeigt("lz4"))
        app._save_setting("ampr_lz4_stufe", "kaputt")
        self.assertEqual(9, app._ampr_stufe_angezeigt("lz4"))

    def test_eine_stufe_ausserhalb_der_auswahl_wird_mit_angezeigt(self):
        """Code-Review 12.11.2026: ``--ampr-zstd-stufe 4`` oder eine handgeschriebene Einstellung zeigte die Vorgabe 5,
        waehrend mit 4 gepackt wurde."""
        app = self.app
        self.addCleanup(app._save_setting, "ampr_zstd_stufe", 5)
        self._pack_frei("zstd")
        app._save_setting("ampr_zstd_stufe", 4)
        app._ampr_stufe_combo_schalten()
        werte = self._stufe_werte()
        self.assertIn("4", werte, werte)
        self.assertEqual("4", app._ampr_stufe_var.get(), "das Feld zeigt, womit gepackt wird")
        self.assertEqual(["1", "3", "4", "5", "7", "9", "12", "15", "19", "22"], [w.split(" ")[0] for w in werte])
        app._save_setting("ampr_zstd_stufe", 5)
        app._ampr_stufe_combo_schalten()
        self.assertEqual(9, len(self._stufe_werte()), "mit einer Stufe aus der Auswahl bleibt es bei den neun")

    def test_unbekannte_stufenauswahl_aendert_nichts(self):
        app = self.app
        app._ampr_stufe_var.set("irgendwas")
        with mock.patch.object(app, "_save_setting") as speichern:
            app._ampr_stufe_gewaehlt()
        speichern.assert_not_called()

    def test_kurztexte_haben_kein_komma_und_dieselbe_stufenzahl_wie_die_einstellungen(self):
        app = self.app
        for verfahren in ("lz4", "zstd"):
            lang = app._ampr_stufen_tabelle(verfahren)
            kurz = app._ampr_stufen_tabelle(verfahren, kurz=True)
            self.assertEqual([s for s, _t in lang], [s for s, _t in kurz])
            self.assertFalse(any("," in t for _s, t in kurz), kurz)
            self.assertTrue(all(t.startswith(str(s)) for s, t in kurz), kurz)

    def test_die_schmalen_schalter_der_einbauzeile_zentrieren_ihren_text(self):
        """Nutzerwunsch 12.11.2026: Der Text steht in der Mitte des Schalters, nicht links."""
        app = self.app
        namen = ("ampr_version_combo", "ampr_methode_combo", "ampr_pack_combo", "ampr_stufe_combo",
                 "backport_fw_combo", "format_combo", "compression_combo", "verify_combo")
        self.assertEqual(set(namen), set(app._PILLEN_ZENTRIERT))
        for name in namen:
            self.assertEqual("center", str(getattr(app, name).cget("justify")), name)
        self.assertEqual("left", str(app.bauform_combo.cget("justify")),
                         "Gegenprobe: die uebrigen Klapplisten bleiben, wie sie waren")

    # ----- "Vollstaendige Pruefung" rechts neben der Packstufe (Nutzerwunsch 12.11.2026) ----------------------------
    def _voll_zustand(self) -> str:
        return str(self.app.ampr_voll_check.cget("state"))

    def test_der_schalter_sitzt_rechts_neben_der_packstufe(self):
        info = self.app.ampr_voll_check.place_info()
        self.assertEqual(str(self.app.ampr_stufe_combo), str(info["in"]))
        self.assertEqual("w", info["anchor"])
        self.assertEqual(1.0, float(info["relx"]))
        self.assertGreater(int(info["x"]), 0)

    def test_der_schalter_ist_nur_bei_zstd_mit_asset_pack_waehlbar(self):
        app = self.app
        self.assertEqual("disabled", self._voll_zustand(), "ohne Haken gesperrt")
        self._pack_frei("lz4")
        self.assertEqual("disabled", self._voll_zustand(), "bei LZ4 gesperrt")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self.assertEqual("normal", self._voll_zustand(), "zstd mit Asset-Pack: waehlbar")
        self._methode("normal")
        self.assertEqual("disabled", self._voll_zustand(), "bei Normal wieder gesperrt")

    def test_bei_lz4_steht_der_schalter_angehakt_weil_dort_immer_voll_geprueft_wird(self):
        app = self.app
        self.addCleanup(app._save_setting, "ampr_voll_pruefen", False)
        app._save_setting("ampr_voll_pruefen", False)
        self._pack_frei("lz4")
        self.assertTrue(app._ampr_voll_var.get())
        self.assertFalse(app._ampr_voll_pruefen(), "gespeichert wird dabei nichts")
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self.assertFalse(app._ampr_voll_var.get(), "bei zstd zeigt der Schalter die gespeicherte Wahl")

    def test_die_wahl_wird_gespeichert_und_beim_umschalten_wieder_gezeigt(self):
        app = self.app
        self.addCleanup(app._save_setting, "ampr_voll_pruefen", False)
        self._pack_frei("zstd")
        app._ampr_voll_var.set(True)
        app._ampr_voll_gewaehlt()
        self.assertTrue(app._ampr_voll_pruefen())
        app._ampr_pack_var.set("LZ4")
        app._ampr_pack_gewaehlt()
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self.assertTrue(app._ampr_voll_var.get())
        app._ampr_voll_var.set(False)
        app._ampr_voll_gewaehlt()
        self.assertFalse(app._ampr_voll_pruefen())

    def test_vorgabe_ist_die_stichprobe(self):
        app = self.app
        self.addCleanup(app._save_setting, "ampr_voll_pruefen", False)
        app._save_setting("ampr_voll_pruefen", False)
        self.assertFalse(app._ampr_voll_pruefen())

    def test_tooltip_des_schalters_erklaert_je_zustand(self):
        app = self.app
        tipp = app._ampr_voll_tooltip
        self.assertEqual(app._t("ampr_pack.voll_pruefen_gesperrt"), tipp.text)
        self._pack_frei("lz4")
        self.assertEqual(app._t("ampr_pack.voll_pruefen_lz4"), tipp.text)
        app._ampr_pack_var.set("zstd")
        app._ampr_pack_gewaehlt()
        self.assertEqual(app._t("ampr_pack.voll_pruefen_hint"), tipp.text)

    def test_tooltip_der_packstufe_wechselt_mit_der_sperre(self):
        app = self.app
        tipp = app._ampr_stufe_tooltip
        self.assertEqual(app._t("ampr_pack.stufe_gesperrt"), tipp.text)
        self._pack_frei("lz4")
        self.assertEqual(app._t("ampr_pack.stufe_hint"), tipp.text)
        self._methode("normal")
        self.assertEqual(app._t("ampr_pack.stufe_gesperrt"), tipp.text)


if __name__ == "__main__":
    unittest.main()
