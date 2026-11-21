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
import time
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

#: Eine Gibibyte (``archiv_quelle.PLATZ_RESERVE`` ist eine davon).
GIB = 1 << 30


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

    def test_lz4_zeigt_das_feld_nur_bei_feststehendem_rueckfall(self) -> None:
        """Nutzerwunsch 21.11.2026: Bei AMPR EMU mit LZ4-Asset-Pack erschien TEMP-ORDNER immer; jetzt nur, wo der Zwischenordner entsteht."""
        a = self.app
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(a, "_ampr_wird_eingebaut", return_value=True), \
                mock.patch.object(a, "_ampr_methode", return_value=self.haupt.AMPR_METHODE_ASSETPACK), \
                mock.patch.object(a, "_ampr_pack_verfahren", return_value="lz4"):
            ordner = os.path.join(t, "PPSA01234")
            os.mkdir(ordner)
            a._arbeitsordner_sichtbarkeit_setzen()
            a.source_path.set(ordner)
            _WURZEL.update()
            self.assertEqual(["", "", ""], self._manager(), "der Strom packt dieses Spiel ohne Zwischenordner")
            Path(ordner + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
            a.source_path.set(ordner)                       # neu gewaehlt: die Eingabe im Feld QUELLE zieht die Anzeige nach
            _WURZEL.update()
            self.assertEqual(["grid", "grid", "grid"], self._manager(), "ein Packprofil des Anwenders: der Strom schreibt es nicht")
            a.source_path.set(_datei(t, "spiel.exfat"))
            _WURZEL.update()
            self.assertEqual(["", "", ""], self._manager(), "ein Abbild als Quelle: der Lauf entscheidet erst selbst")
        a._arbeitsordner_sichtbarkeit_setzen()

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

    def test_fehlt_7zip_kommt_keine_ordnerfrage_vor_der_meldung(self) -> None:
        """Fehlt 7-Zip fuer ein .7z, sagt das ``_archiv_als_quelle`` gleich. Eine vorangestellte Ordnerfrage (samt gemerktem Ordner) fuehrte zu nichts.

        Ein .zip braucht kein 7-Zip: dort bleibt die Frage wie bisher (Pruefung 18.11.2026).
        """
        a = self.app
        with tempfile.TemporaryDirectory() as t, mock.patch.object(a, "_archiv_ordner_dialog", return_value="entpacken") as dialog, \
                mock.patch.object(self.haupt.archiv_quelle, "siebenzip_suchen", return_value=""):
            self.assertTrue(a._archiv_ordner_klaeren(self._siebenzip(t)), "weiter: ``_archiv_als_quelle`` meldet, dass 7-Zip fehlt")
            dialog.assert_not_called()
            self.assertEqual("", a._archiv_ordner_gefragt, "nichts als beantwortet gemerkt")
            with mock.patch.object(type(a), "_archiv_strom_gewaehlt", return_value=False):
                self.assertTrue(a._archiv_ordner_klaeren(_datei(t, "spiel.zip")))
            dialog.assert_called_once()
        a._archiv_ordner_gefragt = ""

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

    # ------------------------------------------------------------------ die entpackte Groesse (17.11.2026)
    def _dialog_texte(self, frei: int, entpackt: "int | None") -> "list[str]":
        """Die Beschriftungen des Dialogs, wie sie beim Anzeigen stehen."""
        a = self.app
        texte: "list[str]" = []

        def _sammeln(widget) -> None:
            if isinstance(widget, tk.Label):
                texte.append(str(widget.cget("text")))
            for kind in widget.winfo_children():
                _sammeln(kind)

        def _statt_warten(fenster) -> None:
            fenster.update_idletasks()
            _sammeln(fenster)
            fenster.destroy()

        with mock.patch.object(tk.Toplevel, "grab_set"), mock.patch.object(a.root, "wait_window", side_effect=_statt_warten):
            self.haupt.PS5ConverterGUI._archiv_ordner_dialog(a, "spiel.7z", "C:\\Temp", 38 * GIB, frei, entpackt)
        time.sleep(0.45)                       # _build_modern_toplevel plant Nachmessungen
        _WURZEL.update()
        return texte

    def test_der_dialog_nennt_die_entpackte_groesse(self) -> None:
        a = self.app
        texte = self._dialog_texte(300 * GIB, 160 * GIB)
        self.assertIn(a._t("archiv_ordner.zahlen_entpackt", groesse=a._fmt_bytes(38 * GIB), entpackt=a._fmt_bytes(160 * GIB),
                           frei=a._fmt_bytes(300 * GIB)), texte)
        self.assertFalse([t for t in texte if t.startswith(a._t("archiv_ordner.zu_wenig", entpackt="", frei="", reserve="")[:18])],
                         "es passt: keine Warnung")

    def test_der_dialog_warnt_wenn_es_entpackt_nicht_passt(self) -> None:
        a = self.app
        texte = self._dialog_texte(100 * GIB, 160 * GIB)
        self.assertIn(a._t("archiv_ordner.zu_wenig", entpackt=a._fmt_bytes(160 * GIB), frei=a._fmt_bytes(100 * GIB),
                           reserve=a._fmt_bytes(archiv_quelle.PLATZ_RESERVE)), texte)

    def test_knapp_ist_auch_zu_wenig_weil_die_reserve_frei_bleiben_soll(self) -> None:
        a = self.app
        texte = self._dialog_texte(160 * GIB + archiv_quelle.PLATZ_RESERVE - 1, 160 * GIB)
        self.assertTrue([t for t in texte if "160" in t and a._t("archiv_ordner.zu_wenig", entpackt="", frei="", reserve="")[:12] in t])
        texte = self._dialog_texte(160 * GIB + archiv_quelle.PLATZ_RESERVE, 160 * GIB)
        self.assertFalse([t for t in texte if a._t("archiv_ordner.zu_wenig", entpackt="", frei="", reserve="")[:12] in t])

    def test_ohne_bekannte_groesse_bleibt_es_bei_der_archivgroesse(self) -> None:
        a = self.app
        texte = self._dialog_texte(100 * GIB, None)
        self.assertIn(a._t("archiv_ordner.zahlen", groesse=a._fmt_bytes(38 * GIB), frei=a._fmt_bytes(100 * GIB)), texte)

    def _auf_den_knopf_druecken(self, frei: int, entpackt: "int | None") -> "tuple[str, list]":
        """Zeigt den Dialog, drueckt "Hier entpacken" und liefert (Antwort, Aufrufe von showerror)."""
        a = self.app

        def _knoepfe(widget, gefunden: list) -> None:
            if hasattr(widget, "invoke") and hasattr(widget, "cget"):
                gefunden.append(widget)
            for kind in widget.winfo_children():
                _knoepfe(kind, gefunden)

        def _statt_warten(fenster) -> None:
            fenster.update_idletasks()
            gefunden: list = []
            _knoepfe(fenster, gefunden)
            knopf = next(k for k in gefunden if str(k.cget("text")) == a._t("archiv_ordner.knopf_entpacken"))
            knopf.invoke()
            if fenster.winfo_exists():                       # der Dialog blieb offen: jetzt wie ueber die Titelleiste schliessen
                fenster.destroy()

        with mock.patch.object(tk.Toplevel, "grab_set"), mock.patch.object(a.root, "wait_window", side_effect=_statt_warten), \
                mock.patch.object(self.haupt.messagebox, "showerror") as fehler:
            antwort = self.haupt.PS5ConverterGUI._archiv_ordner_dialog(a, "spiel.7z", "C:\\Temp", 38 * GIB, frei, entpackt)
        time.sleep(0.45)
        _WURZEL.update()
        return antwort, fehler.call_args_list

    def test_hier_entpacken_tut_nichts_wenn_es_nicht_passt(self) -> None:
        a = self.app
        antwort, fehler = self._auf_den_knopf_druecken(100 * GIB, 160 * GIB)
        self.assertEqual("abbrechen", antwort, "der Dialog blieb offen und wurde danach geschlossen - es wurde nichts entpackt")
        self.assertEqual(1, len(fehler))
        self.assertEqual(a._t("quelle.archiv_platz_entpackt", frei=a._fmt_bytes(100 * GIB), groesse=a._fmt_bytes(160 * GIB),
                              reserve=a._fmt_bytes(archiv_quelle.PLATZ_RESERVE)), fehler[0].args[1])

    def test_hier_entpacken_geht_wenn_es_passt_oder_die_groesse_unbekannt_ist(self) -> None:
        for frei, entpackt in ((400 * GIB, 160 * GIB), (100 * GIB, None)):
            with self.subTest(frei=frei, entpackt=entpackt):
                antwort, fehler = self._auf_den_knopf_druecken(frei, entpackt)
                self.assertEqual(("entpacken", []), (antwort, fehler))

    def test_der_start_rechnet_die_reserve_mit(self) -> None:
        a = self.app
        for frei_bytes, meldung in ((160 * GIB + archiv_quelle.PLATZ_RESERVE - 1, True), (160 * GIB + archiv_quelle.PLATZ_RESERVE, False)):
            with self.subTest(frei=frei_bytes):
                frei = types.SimpleNamespace(total=500 * GIB, used=0, free=frei_bytes)
                with tempfile.TemporaryDirectory() as t, \
                        mock.patch.object(type(a), "_archiv_entpackt_groesse", return_value=160 * GIB), \
                        mock.patch.object(self.haupt.shutil, "disk_usage", return_value=frei), \
                        mock.patch.object(self.haupt.messagebox, "showerror") as fehler, \
                        mock.patch.object(archiv_quelle, "siebenzip_suchen", return_value="7z"), \
                        mock.patch.object(self.haupt.tempfile, "mkdtemp", side_effect=OSError("angehalten")):
                    a._archiv_als_quelle(self._siebenzip(t))
                platz = a._t("quelle.archiv_platz_entpackt", frei=a._fmt_bytes(frei_bytes), groesse=a._fmt_bytes(160 * GIB),
                             reserve=a._fmt_bytes(archiv_quelle.PLATZ_RESERVE))
                self.assertEqual(meldung, fehler.call_args.args[1] == platz)

    def test_ein_zip_im_strom_braucht_keinen_platz_fuer_den_entpackten_inhalt(self) -> None:
        """Es kommen nur sce_sys und eboot.bin in einen Schattenordner: die entpackte Groesse zaehlt dort nicht."""
        a = self.app
        frei = types.SimpleNamespace(total=500 * GIB, used=0, free=100 * GIB)
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(type(a), "_archiv_entpackt_groesse", return_value=160 * GIB) as groesse, \
                mock.patch.object(type(a), "_archiv_strom_gewaehlt", return_value=True), \
                mock.patch.object(self.haupt.shutil, "disk_usage", return_value=frei), \
                mock.patch.object(self.haupt.messagebox, "showerror") as fehler, \
                mock.patch.object(self.haupt.tempfile, "mkdtemp", side_effect=OSError("angehalten")):
            a._archiv_als_quelle(_datei(t, "spiel.zip"))
        groesse.assert_not_called()
        self.assertEqual(a._t("quelle.archiv_fehler", grund="angehalten"), fehler.call_args.args[1])

    def test_die_frage_reicht_die_entpackte_groesse_an_den_dialog(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(type(a), "_archiv_entpackt_groesse", return_value=160 * GIB), \
                mock.patch.object(a, "_archiv_ordner_dialog", return_value="entpacken") as dialog:
            a._archiv_ordner_klaeren(self._siebenzip(t))
        self.assertEqual(160 * GIB, dialog.call_args.args[4])

    def test_der_start_bricht_ab_wenn_es_entpackt_nicht_passt_und_entpackt_nichts(self) -> None:
        a = self.app
        frei = types.SimpleNamespace(total=500 * GIB, used=400 * GIB, free=100 * GIB)
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(type(a), "_archiv_entpackt_groesse", return_value=160 * GIB), \
                mock.patch.object(self.haupt.shutil, "disk_usage", return_value=frei), \
                mock.patch.object(self.haupt.messagebox, "showerror") as fehler, \
                mock.patch.object(archiv_quelle, "siebenzip_suchen", return_value="7z"), \
                mock.patch.object(archiv_quelle, "entpacken") as entpacken:
            a._archiv_als_quelle(self._siebenzip(t))
        fehler.assert_called_once()
        self.assertEqual(a._t("quelle.archiv_platz_entpackt", frei=a._fmt_bytes(100 * GIB), groesse=a._fmt_bytes(160 * GIB),
                              reserve=a._fmt_bytes(archiv_quelle.PLATZ_RESERVE)), fehler.call_args.args[1])
        entpacken.assert_not_called()
        self.assertFalse(a._archiv_laeuft, "nichts laeuft")

    def test_passt_es_geht_der_start_an_der_platzpruefung_vorbei(self) -> None:
        """Gegenprobe: mit genug Platz kommt die Meldung des Platzes nicht (der Start scheitert hier erst am Arbeitsordner)."""
        a = self.app
        frei = types.SimpleNamespace(total=500 * GIB, used=100 * GIB, free=400 * GIB)
        with tempfile.TemporaryDirectory() as t, \
                mock.patch.object(type(a), "_archiv_entpackt_groesse", return_value=160 * GIB), \
                mock.patch.object(self.haupt.shutil, "disk_usage", return_value=frei), \
                mock.patch.object(self.haupt.messagebox, "showerror") as fehler, \
                mock.patch.object(archiv_quelle, "siebenzip_suchen", return_value="7z"), \
                mock.patch.object(self.haupt.tempfile, "mkdtemp", side_effect=OSError("angehalten")):
            a._archiv_als_quelle(self._siebenzip(t))
        fehler.assert_called_once()
        self.assertEqual(a._t("quelle.archiv_fehler", grund="angehalten"), fehler.call_args.args[1],
                         "die Meldung ist die des Arbeitsordners, nicht die des Platzes")

    def test_die_groesse_wird_je_archiv_gemerkt_und_bei_einer_aenderung_neu_gelesen(self) -> None:
        a = self.app
        with tempfile.TemporaryDirectory() as t, mock.patch.object(archiv_quelle, "entpackte_groesse", return_value=5 * GIB) as lesen:
            archiv = self._siebenzip(t)
            self.assertEqual(5 * GIB, a._archiv_entpackt_groesse(archiv))
            self.assertEqual(5 * GIB, a._archiv_entpackt_groesse(archiv))
            self.assertEqual(1, lesen.call_count, "gemerkt")
            Path(archiv).write_bytes(b"xx")                                    # eine andere Datei gleichen Namens
            a._archiv_entpackt_groesse(archiv)
            self.assertEqual(2, lesen.call_count)
        self.assertIsNone(a._archiv_entpackt_groesse(os.path.join(t, "gibt-es-nicht.7z")))

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
