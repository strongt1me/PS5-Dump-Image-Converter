# -*- coding: utf-8 -*-
"""Ausgabename per Vorlage im Programm: Einstellung, Namensbildung an den Ausgabestellen, Einstellungsfenster."""
from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ausgabename_einbindung")

from ps5_validator.utils import ausgabename as an            # noqa: E402


def _lade():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", ROOT / "PS5ImageConverter_Pro_FINAL_revised.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


HAUPT = _lade()
GUI = HAUPT.PS5ConverterGUI
QUELLE = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

SPIEL = {"title": "Astro Bot", "title_id": "PPSA01234", "version": "01.000.000",
         "required_firmware": "09.00.00.00", "content_id": "UP9000-PPSA01234_00-ASTROBOT00000000", "region": "–"}


def _app(einstellungen=None, angaben=SPIEL):
    app = GUI.__new__(GUI)
    app._einstellungen = dict(einstellungen or {})
    app._load_setting = lambda k, d=None: app._einstellungen.get(k, d)
    app._save_setting = lambda k, v: app._einstellungen.__setitem__(k, v)
    app.protokoll = []
    app._append_to_log = app.protokoll.append
    app._t = lambda k, **w: k + " " + " ".join("%s=%s" % kv for kv in sorted(w.items()))
    app._lesezaehler = 0

    def lesen(src, deep_scan=True):
        app._lesezaehler += 1
        if isinstance(angaben, Exception):
            raise angaben
        return dict(angaben)
    app._read_game_meta = lesen
    app._assetpack_gewaehlt = lambda: False
    app._ampr_pack_verfahren = lambda: "zstd"
    app._cli_ausgabe_vorlage = None
    return app


class VorlageTests(unittest.TestCase):
    def test_ohne_einstellung_gilt_die_vorgabe(self):
        self.assertEqual(an.STANDARD, _app()._ausgabe_vorlage())

    def test_eine_gespeicherte_taugliche_vorlage_gilt(self):
        self.assertEqual("{title} [{title_id}]", _app({"ausgabe_vorlage": " {title} [{title_id}] "})._ausgabe_vorlage())

    def test_eine_unbrauchbare_gespeicherte_vorlage_wird_zur_vorgabe(self):
        for schlecht in ("{unsinn}", "{title", "", "nur Text", 5):
            self.assertEqual(an.STANDARD, _app({"ausgabe_vorlage": schlecht})._ausgabe_vorlage(), repr(schlecht))

    def test_die_kommandozeile_hat_vorrang(self):
        app = _app({"ausgabe_vorlage": "{title_id}"})
        app._cli_ausgabe_vorlage = "{title}"
        self.assertEqual("{title}", app._ausgabe_vorlage())
        app._cli_ausgabe_vorlage = "{kaputt}"
        self.assertEqual(an.STANDARD, app._ausgabe_vorlage(), "eine unbrauchbare Vorlage von der Kommandozeile gilt nicht")

    def test_eine_unbrauchbare_vorlage_wird_einmal_je_lauf_gemeldet(self):
        app = _app({"ausgabe_vorlage": "{unsinn}"})
        for _ in range(3):
            self.assertEqual(an.STANDARD, app._ausgabe_vorlage())
        meldungen = [z for z in app.protokoll if "log.ausgabename_vorlage_unbrauchbar" in z]
        self.assertEqual(1, len(meldungen), app.protokoll)
        self.assertIn("{unsinn}", meldungen[0])
        app._ausgabe_vorlage_gemeldet = ""                       # der naechste Lauf (``_launch_task``) setzt es zurueck
        app._ausgabe_vorlage()
        self.assertEqual(2, len([z for z in app.protokoll if "log.ausgabename_vorlage_unbrauchbar" in z]))

    def test_die_vorgabe_und_eine_leere_einstellung_sind_keine_meldung_wert(self):
        for wert in (an.STANDARD, "", "   "):
            app = _app({"ausgabe_vorlage": wert})
            self.assertEqual(an.STANDARD, app._ausgabe_vorlage())
            self.assertEqual([], app.protokoll, repr(wert))

    def test_eine_kaputte_einstellung_stoert_nicht(self):
        app = _app()

        def kaputt(*_a):
            raise OSError("weg")
        app._load_setting = kaputt
        self.assertEqual(an.STANDARD, app._ausgabe_vorlage())


class StammTests(unittest.TestCase):
    def test_die_vorgabe_aendert_nichts_und_liest_nichts(self):
        app = _app()
        self.assertEqual("Mein_Dump", app._ausgabe_stamm("C:/x/Mein_Dump", "Mein_Dump", "exfat"))
        self.assertEqual(0, app._lesezaehler)
        self.assertEqual([], app.protokoll)

    def test_eine_vorlage_erzeugt_den_namen(self):
        app = _app({"ausgabe_vorlage": "[{title}]-[{title_id}]"})
        self.assertEqual("[Astro Bot]-[PPSA01234]", app._ausgabe_stamm("C:/x/Mein_Dump", "Mein_Dump", "exfat"))
        self.assertTrue(any("log.ausgabename_nach_vorlage" in z and "[Astro Bot]-[PPSA01234]" in z for z in app.protokoll))

    def test_das_ergebnis_wird_gemerkt_und_nur_einmal_protokolliert(self):
        app = _app({"ausgabe_vorlage": "{title_id}"})
        for _ in range(3):
            self.assertEqual("PPSA01234", app._ausgabe_stamm("C:/x/D", "D", "exfat"))
        self.assertEqual(1, app._lesezaehler)
        self.assertEqual(1, len(app.protokoll))

    def test_jedes_format_und_jede_quelle_hat_ihren_eigenen_merkzettel(self):
        app = _app({"ausgabe_vorlage": "{title_id}-{name}"})
        self.assertEqual("PPSA01234-A", app._ausgabe_stamm("C:/x/A", "A", "exfat"))
        self.assertEqual("PPSA01234-B", app._ausgabe_stamm("C:/x/B", "B", "exfat"))
        self.assertEqual(2, app._lesezaehler)

    def test_eine_andere_vorlage_gilt_sofort(self):
        app = _app({"ausgabe_vorlage": "{title_id}"})
        self.assertEqual("PPSA01234", app._ausgabe_stamm("C:/x/D", "D", "exfat"))
        app._einstellungen["ausgabe_vorlage"] = "{title}"
        self.assertEqual("Astro Bot", app._ausgabe_stamm("C:/x/D", "D", "exfat"))

    def test_ohne_lesbare_angaben_bleibt_der_name_der_quelle(self):
        app = _app({"ausgabe_vorlage": "{title} [{title_id}]"}, angaben={"title": "–", "title_id": "–"})
        self.assertEqual("Dump", app._ausgabe_stamm("C:/x/Dump", "Dump", "exfat"))
        self.assertTrue(any("log.ausgabename_ohne_angaben" in z for z in app.protokoll), app.protokoll)

    def test_ein_fehler_beim_lesen_verhindert_nichts(self):
        app = _app({"ausgabe_vorlage": "{title}"}, angaben=OSError("nicht lesbar"))
        self.assertEqual("Dump", app._ausgabe_stamm("C:/x/Dump", "Dump", "exfat"))

    def test_zu_lange_namen_werden_je_format_gekuerzt(self):
        lang = dict(SPIEL, title="T" * 80)
        app = _app({"ausgabe_vorlage": "{title} [{title_id}]"}, angaben=lang)
        ordner = app._ausgabe_stamm("C:/x/D", "D", "folder")
        self.assertEqual(80 + len(" [PPSA01234]"), len(ordner), "ein Ordner hat keine Grenze")
        self.assertEqual(63, len(app._ausgabe_stamm("C:/x/D", "D", "exfat").encode("utf-8")))
        self.assertEqual(58, len(app._ausgabe_stamm("C:/x/D", "D", "ffpfsc").encode("utf-8")))
        self.assertTrue(any("log.ausgabename_gekuerzt" in z for z in app.protokoll), app.protokoll)

    def test_das_pack_kommt_aus_der_wahl(self):
        app = _app({"ausgabe_vorlage": "{title_id} {pack}"})
        self.assertEqual("PPSA01234", app._ausgabe_stamm("C:/x/D", "D", "exfat"))
        app = _app({"ausgabe_vorlage": "{title_id} {pack}"})
        app._assetpack_gewaehlt = lambda: True
        self.assertEqual("PPSA01234 zstd", app._ausgabe_stamm("C:/x/D", "D", "exfat"))

    def test_der_merkzettel_wird_beim_start_eines_laufs_geleert(self):
        i = QUELLE.index("def _launch_task")
        self.assertIn("self._ausgabe_cache     = {}", QUELLE[i:i + 80000])
        self.assertIn('self._ausgabe_vorlage_gemeldet = ""', QUELLE[i:i + 80000], "eine unbrauchbare Vorlage wird je Lauf neu gemeldet")


class ErwarteterPfadTests(unittest.TestCase):
    def test_der_erwartete_ausgabepfad_folgt_der_vorlage(self):
        app = _app({"ausgabe_vorlage": "[{title}]-[{title_id}]"})
        app._resolve_mode_source_type = lambda mode, src: "folder"
        app._get_selected_target_type = lambda: "exfat"
        pfad = app._get_expected_output_path("pack_folder", "C:/x/Mein_Dump", "D:/Ziel")
        self.assertEqual(os.path.join("D:/Ziel", "[Astro Bot]-[PPSA01234].exfat"), pfad)

    def test_die_vorgabe_laesst_den_pfad_wie_er_war(self):
        app = _app()
        app._resolve_mode_source_type = lambda mode, src: "folder"
        app._get_selected_target_type = lambda: "ffpfsc"
        self.assertEqual(os.path.join("D:/Ziel", "Mein_Dump.ffpfsc"),
                         app._get_expected_output_path("pack_folder", "C:/x/Mein_Dump", "D:/Ziel"))

    def test_ordner_nach_ordner_bleibt_ohne_pfad(self):
        app = _app({"ausgabe_vorlage": "{title_id}"})
        app._resolve_mode_source_type = lambda mode, src: "folder"
        app._get_selected_target_type = lambda: "folder"
        self.assertIsNone(app._get_expected_output_path("pack_folder", "C:/x/D", "D:/Ziel"))

    def test_die_ffpkg_folgt_der_vorlage_wie_jedes_andere_format(self):
        """Ausgabepfad, Rueckfrage zum Ueberschreiben und Vorabpruefung nennen denselben Namen (Pruefbericht 14.11.2026)."""
        app = _app({"ausgabe_vorlage": "[{title}]-[{title_id}]"})
        app._ffpkg_support_texte = lambda: {}
        app._resolve_mode_source_type = lambda mode, src: "folder"
        app._get_selected_target_type = lambda: "ffpkg"
        erwartet = os.path.join("D:/Ziel", "[Astro Bot]-[PPSA01234].ffpkg")
        self.assertEqual(erwartet, app._get_expected_output_path("pack_folder", "C:/x/Mein_Dump", "D:/Ziel"))
        self.assertEqual(os.path.normpath(erwartet), os.path.normpath(app._ffpkg_output_path("C:/x/Mein_Dump", "D:/Ziel")))

    def test_die_vorgabe_laesst_den_ffpkg_namen_wie_er_war(self):
        app = _app()
        app._ffpkg_support_texte = lambda: {}
        self.assertEqual(os.path.normpath(os.path.join("D:/Ziel", "Mein_Dump.ffpkg")),
                         os.path.normpath(app._ffpkg_output_path("C:/x/Mein_Dump", "D:/Ziel")))

    def test_entpacken_in_einen_ordner(self):
        app = _app({"ausgabe_vorlage": "{title_id}"})
        self.assertEqual(os.path.join("D:/Ziel", "PPSA01234"),
                         app._get_expected_output_path("exfat_to_folder", "C:/x/Spiel.exfat", "D:/Ziel"))


class AusgabestellenTests(unittest.TestCase):
    """Wächter: Jede Stelle, die einen Namen fuer ein Ergebnis bildet, fragt die Vorlage."""

    def test_alle_wege_fragen_die_vorlage(self):
        erwartet = {
            "_mode_exfat_umpacken": '"exfat"', "_mode_exfat_umpacken_strom": '"exfat"', "_mode_folder_to_exfat": '"exfat"',
            "_mode_ffpkg_to_folder": '"folder"', "_mode_ffpkg_to_exfat": '"exfat"', "_mode_pack_folder": "out_ext",
            "_mode_exfat_to_folder": '"folder"', "_mode_ffpkg_to_ffpfsc": '"ffpfsc"',
            "_mode_unpack_to_game_folder": '"folder"', "_mode_pack_file": "out_ext", "_mode_unpack_to_exfat": '"exfat"',
        }
        for name, format_ in erwartet.items():
            m = re.search(r"    def %s\(.*?(?=\n    def )" % name, QUELLE, re.S)
            self.assertIsNotNone(m, name)
            self.assertRegex(m.group(0), r"self\._ausgabe_stamm\(src, .*?, %s\)" % re.escape(format_), name)

    def test_die_sammelkonvertierung_und_die_vorabpruefung_fragen_sie_auch(self):
        m = re.search(r"    def _ffpkg_output_path\(.*?(?=\n    def )", QUELLE, re.S)
        self.assertIn('self._ausgabe_stamm(src, source_name, "ffpkg")', m.group(0))
        m = re.search(r"    def _batch_ueberschreiben_klaeren\(.*?(?=\n    def )", QUELLE, re.S)
        self.assertIn("self._ausgabe_stamm(quelle, name, zielformat)", m.group(0))
        m = re.search(r"    def _vorab_befunde_rechnen\(.*?(?=\n    def )", QUELLE, re.S)
        self.assertIn("self._ausgabe_stamm(quelle, stamm, target_type)", m.group(0))

    def test_der_schalter_der_kommandozeile(self):
        self.assertIn('"--ausgabename", default=None, metavar="VORLAGE"', QUELLE)
        self.assertIn('app._cli_ausgabe_vorlage = getattr(args, "ausgabename", None)', QUELLE)


class VorabpruefungTests(unittest.TestCase):
    def test_die_vorabpruefung_prueft_den_namen_nach_der_vorlage(self):
        lang = dict(SPIEL, title="T" * 90)
        app = _app({"ausgabe_vorlage": "{title}"}, angaben=lang)
        app._MODE_TARGET_OPTIONS = GUI._MODE_TARGET_OPTIONS
        with tempfile.TemporaryDirectory() as tmp:
            quelle = Path(tmp) / "kurz"
            (quelle / "sce_sys").mkdir(parents=True)
            ziel = Path(tmp) / "Ziel"
            ziel.mkdir()
            fehler, warnungen = app._vorab_befunde("pack_folder", str(quelle), str(ziel), "exfat")
        # Der Name nach der Vorlage wird auf 63 Bytes gekuerzt: keine Warnung wegen eines zu langen Namens.
        self.assertEqual([], [w for w in warnungen if "vorab_name_lang" in w], warnungen)


class DialogTests(unittest.TestCase):
    """Das Einstellungsfenster zeigt den Abschnitt und speichert eine taugliche Vorlage."""

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
            cls.tk = tk
            cls.wurzel = tk._default_root or tk.Tk()
            cls.wurzel.withdraw()
        except Exception:                        # pragma: no cover
            raise unittest.SkipTest("keine Anzeige verfuegbar")
        cls.app = HAUPT.PS5ConverterGUI(cls.wurzel)
        cls.app._current_language = "de"

    def setUp(self):
        self.arbeit = tempfile.TemporaryDirectory()
        self.addCleanup(self.arbeit.cleanup)
        self.konfig = os.path.join(self.arbeit.name, "paths.json")
        with open(self.konfig, "w", encoding="utf-8") as datei:
            json.dump({}, datei)
        self.app._get_config_path = lambda: self.konfig
        self.app.__dict__["_settings_cache"] = None

    def _sammle(self, widget, art, treffer=None):
        treffer = [] if treffer is None else treffer
        for kind in widget.winfo_children():
            if kind.__class__.__name__ == art:
                treffer.append(kind)
            self._sammle(kind, art, treffer)
        return treffer

    def _dialog(self):
        self.app._show_settings_dialog()
        dlg = [k for k in self.wurzel.winfo_children() if isinstance(k, self.tk.Toplevel) and k.winfo_exists()][-1]
        dlg.update_idletasks()
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        return dlg

    def _texte(self, dlg):
        return [str(w.cget("text")) for w in self._sammle(dlg, "Label")]

    def _tippen(self, dlg, eingabe, text):
        """Setzt den Text und ruft den Behandler von <KeyRelease> - ``event_generate`` erreicht ein verborgenes Fenster nicht."""
        eingabe.delete(0, "end")
        eingabe.insert(0, text)
        skript = eingabe.bind("<KeyRelease>")
        behandler = re.search(r"\[(\S+) ", skript).group(1)
        dlg.tk.call(behandler, "x")
        dlg.update()

    def test_der_abschnitt_ist_da_mit_vorgabe_und_vorschau(self):
        dlg = self._dialog()
        texte = self._texte(dlg)
        self.assertIn(self.app._t("settings_dialog.ausgabe_section"), texte)
        eingaben = [e for e in self._sammle(dlg, "Entry") if e.get() == an.STANDARD]
        self.assertEqual(1, len(eingaben), "ein Feld mit der Vorgabe")

    def test_die_vorschau_zeigt_die_namen_je_format(self):
        dlg = self._dialog()
        eingabe = [e for e in self._sammle(dlg, "Entry") if e.get() == an.STANDARD][0]
        vorschau = [t for t in self._texte(dlg) if "Astro_Bot_Dump" in t]
        self.assertTrue(vorschau, "keine Vorschau gefunden")
        self.assertIn("Astro_Bot_Dump.exfat", vorschau[0])
        self.assertIn("Astro_Bot_Dump.ffpfsc", vorschau[0])
        self.assertIsNotNone(eingabe)

    def test_eine_getippte_taugliche_vorlage_wird_gespeichert_und_vorschau_folgt(self):
        dlg = self._dialog()
        eingabe = [e for e in self._sammle(dlg, "Entry") if e.get() == an.STANDARD][0]
        self._tippen(dlg, eingabe, "[{title}]-[{title_id}]")
        with open(self.konfig, encoding="utf-8") as datei:
            gespeichert = json.load(datei)
        self.assertEqual("[{title}]-[{title_id}]", gespeichert.get("ausgabe_vorlage"))
        self.assertTrue(any("[Astro Bot]-[PPSA01234].exfat" in t for t in self._texte(dlg)), self._texte(dlg))

    def test_eine_untaugliche_vorlage_wird_nicht_gespeichert_und_der_grund_steht_da(self):
        dlg = self._dialog()
        eingabe = [e for e in self._sammle(dlg, "Entry") if e.get() == an.STANDARD][0]
        self._tippen(dlg, eingabe, "{unsinn}")
        with open(self.konfig, encoding="utf-8") as datei:
            self.assertNotIn("ausgabe_vorlage", json.load(datei))
        self.assertTrue(any("unsinn" in t for t in self._texte(dlg)), self._texte(dlg))


class TexteTests(unittest.TestCase):
    def test_alle_texte_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        schluessel = ["settings_dialog.ausgabe_" + s for s in (
            "section", "hint", "beispiele", "vorgabe", "vorschau", "zeile", "gekuerzt", "problem_leer", "problem_lang",
            "problem_offen", "problem_zu", "problem_unbekannt", "problem_doppelt", "problem_zeichen",
            "problem_steuerzeichen", "problem_braucht_namen")]
        schluessel += ["log.ausgabename_nach_vorlage", "log.ausgabename_gekuerzt", "log.ausgabename_ohne_angaben",
                       "log.ausgabename_vorlage_unbrauchbar"]
        for key in schluessel:
            for sprache in SUPPORTED_LANGUAGES:
                self.assertTrue(STRINGS[key][sprache], "%s/%s" % (key, sprache))
        for art in ("leer", "lang", "offen", "zu", "unbekannt", "doppelt", "zeichen", "steuerzeichen", "braucht_namen"):
            self.assertIn("settings_dialog.ausgabe_problem_" + art, STRINGS, art)

    def test_die_platzhalter_stimmen_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        for key, felder in (("settings_dialog.ausgabe_vorschau", ("titel", "kennung")),
                            ("settings_dialog.ausgabe_zeile", ("format", "name", "bytes")),
                            ("settings_dialog.ausgabe_hint", ("teile", "vorgabe")),
                            ("settings_dialog.ausgabe_gekuerzt", ("format",)),
                            ("settings_dialog.ausgabe_problem_unbekannt", ("wert",)),
                            ("settings_dialog.ausgabe_problem_doppelt", ("wert",)),
                            ("settings_dialog.ausgabe_problem_zeichen", ("wert",)),
                            ("log.ausgabename_nach_vorlage", ("vorlage", "name", "gekuerzt")),
                            ("log.ausgabename_ohne_angaben", ("name",)),
                            ("log.ausgabename_vorlage_unbrauchbar", ("vorlage",))):
            for sprache in SUPPORTED_LANGUAGES:
                for feld in felder:
                    self.assertIn("{%s}" % feld, STRINGS[key][sprache], "%s/%s" % (key, sprache))


if __name__ == "__main__":
    unittest.main()
