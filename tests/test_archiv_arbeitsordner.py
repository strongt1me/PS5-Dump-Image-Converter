# -*- coding: utf-8 -*-
"""Archiv als Quelle: TEMP-ORDNER wird sichtbar, vor dem Entpacken fragt das Programm, wohin, und in EINSTELLUNGEN laesst sich
der Arbeitsordner waehlen (Nutzerwunsch 17.11.2026).

Gemeldet wurde: Bei einem Archiv als Quelle (Aufgabe 1) wird ein Arbeitsordner gebraucht, er liess sich aber nicht waehlen - das Feld
TEMP-ORDNER war versteckt (es zeigt sich nur, wo ein Zwischenordner entsteht), und das Entpacken begann sofort im Standardordner.
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import archiv_quelle   # noqa: E402
from ps5_validator.utils.i18n import SUPPORTED_LANGUAGES, translate   # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover - ohne Anzeige
    TK_DA = False
    _WURZEL = None


def _datei(ordner: str, name: str) -> str:
    pfad = os.path.join(ordner, name)
    Path(pfad).write_bytes(b"x")
    return pfad


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ArbeitsordnerTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        app = self.app
        self._vorher = {"mode": app.current_mode.get(), "quelle": app.source_path.get(), "temp": app.temp_path.get(),
                        "batch": list(getattr(app, "_batch_sources", []) or []),
                        "herkunft": dict(getattr(app, "_archiv_herkunft", {}) or {}),
                        "gefragt": getattr(app, "_archiv_ordner_gefragt", ""),
                        "setting": app._load_setting("temp_dir", "")}
        app.current_mode.set("pack_folder")
        app.source_path.set("")
        app._batch_sources = []
        app._archiv_herkunft = {}
        app._archiv_ordner_gefragt = ""
        app._archiv_laeuft = False
        app.temp_path.set("")
        app._save_setting("temp_dir", "")          # sonst traegt _get_runtime_temp_dir die geerbte Einstellung ins Feld ein
        app._temp_pruefung = None
        _WURZEL.update()

    def tearDown(self) -> None:
        app, v = self.app, self._vorher
        app._archiv_laeuft = False
        app.current_mode.set(v["mode"])
        app.source_path.set(v["quelle"])
        app._batch_sources = v["batch"]
        app._archiv_herkunft = v["herkunft"]
        app._archiv_ordner_gefragt = v["gefragt"]
        app.temp_path.set(v["temp"])
        app._save_setting("temp_dir", v["setting"])
        app._temp_pruefung = None
        app._arbeitsordner_nachziehen()
        _WURZEL.update()

    # ------------------------------------------------------------------ wann ist die Quelle ein Archiv
    def test_ein_archiv_in_aufgabe_1_ist_eine_archivquelle(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            ordner = os.path.join(t, "PPSA01234")
            os.mkdir(ordner)
            for name, soll in (("spiel.zip", True), ("spiel.7z", True), ("spiel.rar", True), ("spiel.ffpkg", False)):
                with self.subTest(archiv=name):
                    self.app.source_path.set(_datei(t, name))
                    self.assertEqual(soll, self.app._quelle_ist_archiv())
            self.app.source_path.set(ordner)
            self.assertFalse(self.app._quelle_ist_archiv(), "ein Spielordner ist keine Archivquelle")
            self.app.source_path.set("")
            self.assertFalse(self.app._quelle_ist_archiv())

    def test_in_anderen_aufgaben_zaehlt_eine_archivdatei_nicht(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            self.app.source_path.set(_datei(t, "spiel.7z"))
            self.app.current_mode.set("unpack_to_exfat")
            self.assertFalse(self.app._quelle_ist_archiv())

    def test_der_entpackte_spielordner_und_der_lauf_zaehlen_weiter(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            ordner = os.path.join(t, "PPSA01234")
            os.mkdir(ordner)
            self.app.source_path.set(ordner)
            self.assertFalse(self.app._quelle_ist_archiv())
            self.app._archiv_herkunft[self.app._archiv_schluessel(ordner)] = os.path.join(t, "spiel.7z")
            self.assertTrue(self.app._quelle_ist_archiv(), "der Ordner stammt aus einem Archiv")
            self.app._archiv_herkunft = {}
            self.app._archiv_laeuft = True
            self.assertTrue(self.app._quelle_ist_archiv(), "das Entpacken laeuft")

    def test_die_sammelkonvertierung_kennt_archive_unter_den_quellen(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            archiv, abbild = _datei(t, "a.7z"), _datei(t, "b.exfat")
            self.app.current_mode.set("batch_convert")
            self.app._batch_sources = [abbild]
            self.assertFalse(self.app._quelle_ist_archiv())
            self.app._batch_sources = [abbild, archiv]
            self.assertTrue(self.app._quelle_ist_archiv())

    # ------------------------------------------------------------------ TEMP-ORDNER zeigt sich
    def _manager(self) -> list:
        a = self.app
        return [a.temp_title.winfo_manager(), a.temp_entry.winfo_manager(), a.temp_btn.winfo_manager()]

    def test_temp_ordner_zeigt_sich_bei_einem_archiv_und_verschwindet_mit_ihm(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t:
            ordner = os.path.join(t, "PPSA01234")
            os.mkdir(ordner)
            a.source_path.set(ordner)
            _WURZEL.update()
            self.assertEqual(["", "", ""], self._manager(), "ein Spielordner im Strom braucht keinen Arbeitsordner")
            a.source_path.set(_datei(t, "spiel.7z"))
            _WURZEL.update()
            self.assertEqual(["grid", "grid", "grid"], self._manager(), "ein Archiv wird in den Arbeitsordner entpackt")
            a.source_path.set(ordner)
            _WURZEL.update()
            self.assertEqual(["", "", ""], self._manager(), "ohne Archiv wieder weg")

    def test_unveraendert_wird_die_zeile_nicht_neu_gelegt(self) -> None:
        """Jede Eingabe im Feld QUELLE ruft ``_arbeitsordner_nachziehen``: Es legt die Karte nur neu, wenn sich der Bedarf aendert."""
        a = self.app
        with mock.patch.object(a, "_arbeitsordner_noetig", return_value=True), \
                mock.patch.object(a, "_arbeitsordner_sichtbarkeit_setzen", wraps=a._arbeitsordner_sichtbarkeit_setzen) as setzen:
            a._arbeitsordner_nachziehen()
            self.assertEqual(1, setzen.call_count, "der Bedarf hat sich geaendert")
            a._arbeitsordner_nachziehen()
            a._arbeitsordner_nachziehen()
            self.assertEqual(1, setzen.call_count, "gleicher Bedarf: nichts neu legen")
        a._arbeitsordner_sichtbarkeit_setzen()             # Ausgangslage fuer die naechsten Tests

    def test_beim_wechsel_der_aufgabe_geht_das_feld_wieder_weg(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t:
            a.source_path.set(_datei(t, "spiel.zip"))
            _WURZEL.update()
            self.assertEqual("grid", a.temp_entry.winfo_manager())
            a.current_mode.set("unpack_to_exfat")
            _WURZEL.update()
            self.assertEqual("", a.temp_entry.winfo_manager())

    def test_der_dump_haken_folgt_derselben_regel(self) -> None:
        """Der Haken "Dump-Ordner im Arbeitsordner" erscheint, wo TEMP-ORDNER erscheint (``_arbeitsordner_sichtbarkeit_setzen``)."""
        a = self.app
        with tempfile.TemporaryDirectory() as t:
            a.source_path.set(_datei(t, "spiel.7z"))
            _WURZEL.update()
            self.assertTrue(a._dump_haken_an)
            a.source_path.set("")
            _WURZEL.update()
            self.assertFalse(a._dump_haken_an)

    def test_nach_dem_entpacken_bleibt_das_feld_stehen(self) -> None:
        """``_archiv_fertig`` setzt die Quelle auf den Spielordner: Die Herkunft muss vorher eingetragen sein, sonst verschwindet
        TEMP-ORDNER beim Wechsel vom Archiv zum entpackten Ordner (der Trace auf die Quelle fragt sie ab)."""
        a = self.app
        with tempfile.TemporaryDirectory() as t:
            spiel = Path(t) / "entpackt" / "PPSA01234"
            (spiel / "sce_sys").mkdir(parents=True)
            (spiel / "sce_sys" / "param.json").write_text("{}", encoding="utf-8")
            (spiel / "eboot.bin").write_bytes(b"x")
            archiv = _datei(t, "spiel.7z")
            a.source_path.set(archiv)
            _WURZEL.update()
            with mock.patch.object(type(a), "_validate_source_path", return_value=""):
                a._archiv_fertig(archiv, str(spiel), "")
            _WURZEL.update()
            self.assertEqual(str(spiel), a.source_path.get())
            self.assertEqual("grid", a.temp_entry.winfo_manager())

    # ------------------------------------------------------------------ die Frage vor dem Entpacken
    def _siebenzip(self, t: str) -> str:
        return _datei(t, "spiel.7z")

    def test_ein_7z_fragt_einmal_und_traegt_den_ordner_ins_feld_ein(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, mock.patch.object(a, "_archiv_ordner_dialog", return_value="entpacken") as dialog:
            archiv = self._siebenzip(t)
            self.assertTrue(a._archiv_ordner_klaeren(archiv))
            dialog.assert_called_once()
            basis = dialog.call_args.args[1]
            self.assertEqual(os.path.basename(archiv), dialog.call_args.args[0])
            self.assertEqual(basis, a.temp_path.get(), "\"Hier entpacken\": Der Ordner steht danach im Feld")
            self.assertTrue(a._archiv_ordner_klaeren(archiv), "fuer diesen Ordner wurde schon gefragt")
            dialog.assert_called_once()

    def test_abbrechen_aendert_nichts(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, mock.patch.object(a, "_archiv_ordner_dialog", return_value="abbrechen"):
            self.assertFalse(a._archiv_ordner_klaeren(self._siebenzip(t)))
        self.assertEqual("", a.temp_path.get())
        self.assertEqual("", a._archiv_ordner_gefragt)

    def test_anderen_ordner_waehlen_setzt_feld_und_einstellung(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as neu, \
                mock.patch.object(a, "_archiv_ordner_dialog", return_value="waehlen") as dialog, \
                mock.patch.object(self.haupt.filedialog, "askdirectory", return_value=neu):
            self.assertTrue(a._archiv_ordner_klaeren(self._siebenzip(t)))
            dialog.assert_called_once()
            self.assertEqual(os.path.normpath(neu), os.path.normpath(a.temp_path.get()))
            self.assertEqual(os.path.normpath(neu), os.path.normpath(a._load_setting("temp_dir", "")))
            self.assertEqual(os.path.normcase(os.path.normpath(neu)), a._archiv_ordner_gefragt)
            self.assertTrue(a._archiv_ordner_klaeren(self._siebenzip(t)), "der gewaehlte Ordner gilt, es wird nicht noch einmal gefragt")
            dialog.assert_called_once()

    def test_ohne_gewaehlten_ordner_kommt_die_frage_zurueck(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(a, "_archiv_ordner_dialog", side_effect=["waehlen", "abbrechen"]) as dialog, \
                mock.patch.object(self.haupt.filedialog, "askdirectory", return_value=""):
            self.assertFalse(a._archiv_ordner_klaeren(self._siebenzip(t)))
            self.assertEqual(2, dialog.call_count)
        self.assertEqual("", a.temp_path.get())

    def test_ein_anderer_ordner_wird_neu_gefragt(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, tempfile.TemporaryDirectory() as zweiter, \
                mock.patch.object(a, "_archiv_ordner_dialog", return_value="entpacken") as dialog:
            archiv = self._siebenzip(t)
            a._archiv_ordner_klaeren(archiv)
            a.temp_path.set(zweiter)                          # der Anwender stellt das Feld um
            a._temp_pruefung = None
            a._archiv_ordner_klaeren(archiv)
            self.assertEqual(2, dialog.call_count)

    def test_ein_zip_im_strom_wird_nicht_gefragt_ohne_strom_schon(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, mock.patch.object(a, "_archiv_ordner_dialog", return_value="entpacken") as dialog:
            zip_ = _datei(t, "spiel.zip")
            with mock.patch.object(type(a), "_archiv_strom_gewaehlt", return_value=True):
                self.assertTrue(a._archiv_ordner_klaeren(zip_))
            dialog.assert_not_called()
            with mock.patch.object(type(a), "_archiv_strom_gewaehlt", return_value=False):
                self.assertTrue(a._archiv_ordner_klaeren(zip_))
            dialog.assert_called_once()

    def test_kommandozeile_und_laufender_auftrag_werden_nicht_gefragt(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, mock.patch.object(a, "_archiv_ordner_dialog") as dialog:
            archiv = self._siebenzip(t)
            a._cli_mode = True
            self.addCleanup(setattr, a, "_cli_mode", False)
            self.assertTrue(a._archiv_ordner_klaeren(archiv))
            a._cli_mode = False
            a.is_running = True
            self.addCleanup(setattr, a, "is_running", False)
            self.assertTrue(a._archiv_ordner_klaeren(archiv), "waehrend eines Laufs warnt _archiv_als_quelle selbst")
            dialog.assert_not_called()

    def test_knopf_und_ablegen_klaeren_zuerst_den_ordner(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t:
            archiv = self._siebenzip(t)
            abgelegt = types.SimpleNamespace(data=archiv.replace("\\", "/"))      # Tk liefert beim Ablegen Schraegstriche
            with mock.patch.object(self.haupt.filedialog, "askopenfilename", return_value=archiv), \
                    mock.patch.object(a, "_archiv_ordner_klaeren", return_value=False) as klaeren, \
                    mock.patch.object(a, "_archiv_als_quelle") as entpacken:
                a._browse_archiv()
                a._on_source_dropped(abgelegt)
            self.assertEqual(2, klaeren.call_count)
            entpacken.assert_not_called()
            with mock.patch.object(self.haupt.filedialog, "askopenfilename", return_value=archiv), \
                    mock.patch.object(a, "_archiv_ordner_klaeren", return_value=True), \
                    mock.patch.object(a, "_archiv_als_quelle") as entpacken:
                a._browse_archiv()
                a._on_source_dropped(abgelegt)
            self.assertEqual(2, entpacken.call_count)

    def test_der_passwortweg_fragt_nicht_noch_einmal(self) -> None:
        """Die zweite Runde mit dem Passwort ruft ``_archiv_als_quelle`` direkt - eine zweite Ordnerfrage waere falsch."""
        quelle = inspect.getsource(type(self.app)._archiv_passwort_fragen)
        self.assertIn("self._archiv_als_quelle(archiv, passwort=eingabe)", quelle)
        self.assertNotIn("_archiv_waehlen", quelle)

    def test_der_dialog_laesst_sich_bauen_und_schliessen(self) -> None:
        a = self.app
        gebaut = []

        def _statt_warten(fenster):
            gebaut.append(fenster.title())
            fenster.update_idletasks()
            fenster.destroy()

        with mock.patch.object(tk.Toplevel, "grab_set"), mock.patch.object(a.root, "wait_window", side_effect=_statt_warten):
            antwort = self.haupt.PS5ConverterGUI._archiv_ordner_dialog(a, "spiel.7z", "C:\\Temp", 3 * 1024 ** 3, 50 * 1024 ** 3)
            ohne_zahlen = self.haupt.PS5ConverterGUI._archiv_ordner_dialog(a, "spiel.7z", "C:\\Temp", None, None)
        import time
        time.sleep(0.45)                       # _build_modern_toplevel plant Nachmessungen
        _WURZEL.update()
        self.assertEqual(("abbrechen", "abbrechen"), (antwort, ohne_zahlen), "Schliessen ueber die Titelleiste heisst Abbrechen")
        self.assertEqual([a._t("archiv_ordner.titel")] * 2, gebaut)

    # ------------------------------------------------------------------ EINSTELLUNGEN
    def test_arbeitsordner_setzen_und_zuruecksetzen(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t:
            wirksam = a._arbeitsordner_setzen(t)
            self.assertEqual(os.path.normpath(t), os.path.normpath(a.temp_path.get()))
            self.assertEqual(os.path.normpath(t), os.path.normpath(a._load_setting("temp_dir", "")))
            self.assertEqual(os.path.normpath(t), os.path.normpath(wirksam))
            a._arbeitsordner_setzen("")
            self.assertEqual("", a.temp_path.get())
            self.assertEqual("", a._load_setting("temp_dir", ""), "ein leerer Ordner heisst Standard und wird so gespeichert")

    def test_der_abschnitt_in_den_einstellungen_waehlt_und_setzt_zurueck(self) -> None:
        a = self.app
        dlg = tk.Toplevel(_WURZEL)
        self.addCleanup(dlg.destroy)
        body = tk.Frame(dlg)
        body.pack()
        with tempfile.TemporaryDirectory() as t:
            bausteine = a._einstellungen_arbeitsordner_abschnitt(dlg, body)
            self.assertEqual("", bausteine["var"].get())
            self.assertEqual("readonly", str(bausteine["eingabe"].cget("state")), "geaendert wird per Knopf, nicht beim Tippen")
            with mock.patch.object(self.haupt.filedialog, "askdirectory", return_value=t):
                bausteine["waehlen"]()
            self.assertEqual(os.path.normpath(t), os.path.normpath(bausteine["var"].get()))
            self.assertEqual(os.path.normpath(t), os.path.normpath(a.temp_path.get()), "dieselbe Einstellung wie das Feld im Hauptfenster")
            self.assertEqual(os.path.normpath(t), os.path.normpath(a._load_setting("temp_dir", "")))
            with mock.patch.object(self.haupt.filedialog, "askdirectory", return_value=""):
                bausteine["waehlen"]()
            self.assertEqual(os.path.normpath(t), os.path.normpath(a.temp_path.get()), "abgebrochene Wahl aendert nichts")
            bausteine["standard"]()
            self.assertEqual("", bausteine["var"].get())
            self.assertEqual("", a.temp_path.get())
            self.assertEqual("", a._load_setting("temp_dir", ""))

    def test_der_einstellungsdialog_baut_den_abschnitt(self) -> None:
        quelle = inspect.getsource(type(self.app)._show_settings_dialog)
        self.assertIn("self._einstellungen_arbeitsordner_abschnitt(dlg, body)", quelle)
        self.assertLess(quelle.index("_archiv_passwoerter_speichern()"), quelle.index("_einstellungen_arbeitsordner_abschnitt"),
                        "der Abschnitt steht bei den Archiv-Einstellungen")

    def test_die_regel_nennt_das_archiv_vor_den_anderen_faellen(self) -> None:
        rumpf = inspect.getsource(type(self.app)._arbeitsordner_noetig)
        self.assertLess(rumpf.index("self._quelle_ist_archiv()"), rumpf.index("_EXFAT_STROM_SETTING"))


class UebersetzungTests(unittest.TestCase):
    SCHLUESSEL = {
        "archiv_ordner.titel": {}, "archiv_ordner.untertitel": {}, "archiv_ordner.erklaerung": {"name": "x.7z"},
        "archiv_ordner.zahlen": {"groesse": "1 GB", "frei": "2 GB"}, "archiv_ordner.knopf_entpacken": {},
        "archiv_ordner.knopf_waehlen": {}, "archiv_ordner.waehlen_titel": {}, "archiv_ordner.log_gewaehlt": {"ordner": "D:\\T"},
        "settings_dialog.arbeitsordner_section": {}, "settings_dialog.arbeitsordner_hint": {"standard": "C:\\T"},
        "settings_dialog.arbeitsordner_waehlen": {}, "settings_dialog.arbeitsordner_standard": {},
    }

    def test_jeder_text_gibt_es_in_allen_fuenf_sprachen(self) -> None:
        for schluessel, args in self.SCHLUESSEL.items():
            texte = {}
            for sprache in SUPPORTED_LANGUAGES:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = translate(sprache, schluessel, **args)
                    self.assertTrue(text and text != schluessel, "fehlt")
                    self.assertNotIn("{", text, "Platzhalter nicht ersetzt")
                    texte[sprache] = text
            with self.subTest(schluessel=schluessel):
                self.assertGreaterEqual(len(set(texte.values())), 3, "kaum uebersetzt: %s" % texte)


if __name__ == "__main__":
    unittest.main()
