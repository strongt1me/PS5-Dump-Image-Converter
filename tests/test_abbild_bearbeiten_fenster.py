# -*- coding: utf-8 -*-
"""Das Fenster "Abbild bearbeiten" (``ui/abbild_bearbeiten_fenster.py``): Ablauf Entpacken - Aendern - Speichern.

Die Umwandlung selbst (Aufgabe 6) ist hier ersetzt; geprueft wird, was das Fenster ihr uebergibt, wie es auf ihr Ende
reagiert und dass der Arbeitsordner nicht liegen bleibt. Die Dateiarbeit hat ihre eigene Testdatei.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.ui import abbild_bearbeiten_fenster as fz   # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()           # wie die anderen Testdateien: ein gemeinsames Wurzelfenster
    _WURZEL.withdraw()
    TK_DA = True
except Exception:   # noqa: BLE001
    TK_DA = False
    _WURZEL = None


class _Var:
    def __init__(self, wert="") -> None:
        self.wert = wert

    def get(self):
        return self.wert

    def set(self, wert) -> None:
        self.wert = wert


class _AttrenGui:
    """Gerade so viel Hauptoberflaeche, wie ``aufgabe_starten`` anfasst."""

    def __init__(self) -> None:
        self.current_mode = _Var("pack_folder")
        self.source_path = _Var("alt-quelle")
        self.dest_path = _Var("alt-ziel")
        self.target_format = _Var("alt-format")
        self._batch_sources = ["x", "y"]
        self._task_thread = None
        self._last_task_ok = False
        self.task_final_output_path = ""
        self.laeuft = False
        self.eingestellt: dict = {}
        self.geplant: list = []
        self.root = self
        self.start_tut = "faden"          # "faden" | "nichts"

    def after(self, ms, funktion) -> None:
        self.geplant.append(funktion)

    def _vorgang_laeuft_noch(self) -> bool:
        return self.laeuft

    def _set_mode_from_sidebar(self, modus) -> None:
        self.current_mode.set(modus)

    def _zielformat_label(self, schluessel, modus="", quelle="") -> str:
        return "Label:" + schluessel

    def _launch_task(self) -> None:
        self.eingestellt = {"modus": self.current_mode.get(), "quelle": self.source_path.get(),
                            "ziel": self.dest_path.get(), "format": self.target_format.get(),
                            "sammel": list(self._batch_sources)}
        if self.start_tut == "nichts":
            return
        self.freigabe = threading.Event()
        self._task_thread = threading.Thread(target=self.freigabe.wait, daemon=True)
        self._task_thread.start()
        self.laeuft = True

    def beenden(self, ok: bool, ausgabe: str) -> None:
        self._last_task_ok = ok
        self.task_final_output_path = ausgabe
        self.laeuft = False
        self.freigabe.set()
        self._task_thread.join(2)

    def abarbeiten(self) -> None:
        """Ein Durchgang ueber das, was gerade geplant ist (ein Takt) - die Nachplanung kommt erst beim naechsten."""
        for funktion in [self.geplant.pop(0) for _ in range(len(self.geplant))]:
            funktion()


class AufgabeStartenTests(unittest.TestCase):
    def test_stellt_ein_startet_meldet_und_stellt_zurueck(self) -> None:
        gui = _AttrenGui()
        ergebnis: list = []
        self.assertTrue(fz.aufgabe_starten(gui, "Q", "Z", "folder", lambda ok, pfad: ergebnis.append((ok, pfad))))
        self.assertEqual({"modus": "universal_convert", "quelle": "Q", "ziel": "Z", "format": "Label:folder",
                          "sammel": []}, gui.eingestellt)
        gui.abarbeiten()
        self.assertEqual([], ergebnis, "solange der Faden laeuft, kommt keine Meldung")
        self.assertEqual(1, len(gui.geplant), "es wird weiter nachgesehen")
        gui.beenden(True, "AUSGABE")
        gui.abarbeiten()
        self.assertEqual([(True, "AUSGABE")], ergebnis)
        self.assertEqual(("pack_folder", "alt-quelle", "alt-ziel", ["x", "y"]),
                         (gui.current_mode.get(), gui.source_path.get(), gui.dest_path.get(), gui._batch_sources),
                         "die Oberflaeche steht wieder, wie sie war")

    def test_misserfolg_wird_gemeldet(self) -> None:
        gui = _AttrenGui()
        ergebnis: list = []
        fz.aufgabe_starten(gui, "Q", "Z", "ffpfsc", lambda ok, pfad: ergebnis.append((ok, pfad)))
        gui.beenden(False, "")
        gui.abarbeiten()
        self.assertEqual([(False, "")], ergebnis)

    def test_ohne_start_wird_nicht_gemeldet_und_alles_zurueckgesetzt(self) -> None:
        gui = _AttrenGui()
        gui.start_tut = "nichts"
        ergebnis: list = []
        self.assertFalse(fz.aufgabe_starten(gui, "Q", "Z", "folder", lambda ok, pfad: ergebnis.append(1)))
        self.assertEqual([], ergebnis)
        self.assertEqual([], gui.geplant)
        self.assertEqual(("pack_folder", "alt-quelle", "alt-ziel"),
                         (gui.current_mode.get(), gui.source_path.get(), gui.dest_path.get()))

    def test_laeuft_schon_eine_aufgabe_wird_nichts_angefasst(self) -> None:
        gui = _AttrenGui()
        gui.laeuft = True
        self.assertFalse(fz.aufgabe_starten(gui, "Q", "Z", "folder", lambda *a: None))
        self.assertEqual({}, gui.eingestellt)
        self.assertEqual("alt-quelle", gui.source_path.get())

    def test_ein_fehler_beim_start_stellt_die_oberflaeche_wieder_her(self) -> None:
        gui = _AttrenGui()
        with mock.patch.object(gui, "_launch_task", side_effect=RuntimeError("kaputt")):
            self.assertFalse(fz.aufgabe_starten(gui, "Q", "Z", "folder", lambda *a: None))
        self.assertEqual("alt-quelle", gui.source_path.get())

    def test_formate(self) -> None:
        self.assertEqual("ffpfsc", fz.format_der_datei("a/B.FFPFSC"))
        self.assertEqual("ffpfs", fz.format_der_datei("b.ffpfs"))
        self.assertEqual("exfat", fz.format_der_datei("c.exfat"))
        self.assertEqual("ffpkg", fz.format_der_datei("d.ffpkg"))
        self.assertEqual("", fz.format_der_datei("e.zip"))
        self.assertEqual("", fz.format_der_datei(""))
        for schluessel, endung in fz.ENDUNG_VON.items():
            self.assertEqual(schluessel, fz.FORMATE[endung])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt
        cls.app = haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.t = Path(tmp.name)
        (self.t / "arbeit").mkdir()
        (self.t / "ziel").mkdir()
        self.bild = self.t / "Spiel.ffpfsc"
        self.bild.write_bytes(b"x")
        patcher = mock.patch.object(self.app, "_get_runtime_temp_dir", return_value=str(self.t / "arbeit"))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.aufrufe: list = []
        self.win = self.haupt.abbild_bearbeiten_fenster.oeffnen(
            self.app, self.haupt.UI_SCHRIFT, self.haupt.MONO_SCHRIFT, self.haupt.pt)
        self.addCleanup(self._schliessen)
        self.f = self.win._bearbeiten

    def _schliessen(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def _falsche_aufgabe(self, erfolg: bool = True):
        """Ersetzt ``aufgabe_starten``: legt beim Entpacken einen Spielordner an und meldet sofort."""
        def starten(gui, quelle, ziel, zielformat, fertig):
            self.aufrufe.append((quelle, ziel, zielformat))
            if zielformat == "folder":
                spiel = os.path.join(ziel, "Spiel")
                os.makedirs(os.path.join(spiel, "sce_sys"))
                Path(spiel, "sce_sys", "param.json").write_text("{}")
                Path(spiel, "eboot.bin").write_bytes(b"ELF")
                os.makedirs(os.path.join(spiel, "Media"))
                Path(spiel, "Media", "a.dat").write_bytes(b"aaa")
                fertig(erfolg, spiel if erfolg else "")
            else:
                fertig(erfolg, os.path.join(ziel, "Spiel_bearbeitet.ffpfsc") if erfolg else "")
            return True
        return mock.patch.object(self.haupt.abbild_bearbeiten_fenster, "aufgabe_starten", side_effect=starten)

    def _entpacken(self) -> None:
        self.f.bild_var.set(str(self.bild))
        with self._falsche_aufgabe():
            self.f._entpacken()

    # ---- Anfang ----------------------------------------------------------------------------------------------
    def test_am_anfang_ist_alles_gesperrt_ausser_wahl_und_entpacken(self) -> None:
        for knopf in self.f.aenderungs_knoepfe + [self.f.speichern_knopf]:
            self.assertEqual("disabled", str(knopf["state"]))
        self.assertNotEqual("disabled", str(self.f.entpacken_knopf["state"]))

    def test_ohne_abbild_wird_nichts_gestartet(self) -> None:
        with mock.patch.object(self.haupt.messagebox, "showwarning") as warnung, self._falsche_aufgabe():
            self.f.bild_var.set(str(self.t / "gibt_es_nicht.ffpfsc"))
            self.f._entpacken()
            self.f.bild_var.set(str(self.t / "arbeit"))
            self.f._entpacken()
        self.assertEqual(2, warnung.call_count)
        self.assertEqual([], self.aufrufe)

    # ---- Entpacken -------------------------------------------------------------------------------------------
    def test_entpacken_fuellt_den_baum_und_nennt_den_ordner_nach(self) -> None:
        self._entpacken()
        self.assertEqual([(str(self.bild), self.f.arbeit, "folder")], self.aufrufe)
        self.assertTrue(self.f.arbeit.startswith(str(self.t / "arbeit")))
        self.assertEqual("Spiel_bearbeitet", os.path.basename(self.f.ordner), "das Ergebnis traegt den Zusatz")
        self.assertTrue(os.path.isfile(os.path.join(self.f.ordner, "eboot.bin")))
        eintraege = set(self.f.baum.get_children("")) | set(self.f.baum.get_children("Media"))
        self.assertTrue({"eboot.bin", "Media", "sce_sys", "Media/a.dat"} <= eintraege, eintraege)
        for knopf in self.f.aenderungs_knoepfe + [self.f.speichern_knopf]:
            self.assertNotEqual("disabled", str(knopf["state"]))
        self.assertEqual(".ffpfsc", self.f.format_var.get(), "vorgewaehlt ist das Format des Originals")

    def test_misslungenes_entpacken_raeumt_auf_und_meldet(self) -> None:
        self.f.bild_var.set(str(self.bild))
        with self._falsche_aufgabe(erfolg=False), mock.patch.object(self.haupt.messagebox, "showerror") as fehler:
            self.f._entpacken()
        fehler.assert_called_once()
        self.assertEqual("", self.f.ordner)
        self.assertEqual([], os.listdir(self.t / "arbeit"), "kein Arbeitsordner bleibt liegen")
        self.assertEqual("disabled", str(self.f.speichern_knopf["state"]))

    def test_abgelehnte_aufgabe_raeumt_auf(self) -> None:
        self.f.bild_var.set(str(self.bild))
        with mock.patch.object(self.haupt.abbild_bearbeiten_fenster, "aufgabe_starten", return_value=False):
            self.f._entpacken()
        self.assertEqual([], os.listdir(self.t / "arbeit"))
        self.assertFalse(self.f.beschaeftigt)
        self.assertNotEqual("disabled", str(self.f.entpacken_knopf["state"]))

    # ---- Aendern ---------------------------------------------------------------------------------------------
    def test_loeschen_umbenennen_ersetzen_hinzufuegen(self) -> None:
        self._entpacken()
        o = Path(self.f.ordner)
        neu = self.t / "neu.bin"
        neu.write_bytes(b"NEU")

        self.f.baum.selection_set("Media/a.dat")
        with mock.patch.object(self.haupt.simpledialog if hasattr(self.haupt, "simpledialog") else
                               __import__("tkinter.simpledialog", fromlist=["x"]),
                               "askstring", return_value="b.dat"):
            self.f._umbenennen()
        self.assertTrue((o / "Media" / "b.dat").exists())
        self.assertFalse((o / "Media" / "a.dat").exists())
        self.assertTrue(self.f.baum.exists("Media/b.dat"), "der Baum zeigt den neuen Namen")

        self.f.baum.selection_set("Media/b.dat")
        with mock.patch.object(fz.filedialog, "askopenfilename", return_value=str(neu)):
            self.f._ersetzen()
        self.assertEqual(b"NEU", (o / "Media" / "b.dat").read_bytes())

        self.f.baum.selection_set("Media")
        with mock.patch.object(fz.filedialog, "askopenfilenames", return_value=(str(neu),)):
            self.f._hinzufuegen()
        self.assertEqual(b"NEU", (o / "Media" / "neu.bin").read_bytes())

        self.f.baum.selection_set("Media/neu.bin")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._loeschen()
        self.assertFalse((o / "Media" / "neu.bin").exists())
        self.assertEqual(4, self.f.protokoll.anzahl())
        self.assertIn("4", self.f.zaehler_var.get())

    def test_geschuetztes_wird_abgelehnt_und_nichts_geaendert(self) -> None:
        self._entpacken()
        self.f.baum.selection_set("eboot.bin")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True), \
                mock.patch.object(fz.messagebox, "showerror") as fehler:
            self.f._loeschen()
        fehler.assert_called_once()
        self.assertTrue(os.path.exists(os.path.join(self.f.ordner, "eboot.bin")))
        self.assertEqual(0, self.f.protokoll.anzahl())

    def test_ohne_auswahl_wird_nur_gefragt(self) -> None:
        self._entpacken()
        self.f.baum.selection_set(())
        with mock.patch.object(fz.messagebox, "showinfo") as info, mock.patch.object(fz.messagebox, "askyesno") as frage:
            self.f._loeschen()
            self.f._umbenennen()
            self.f._ersetzen()
            self.f._hinzufuegen()
            self.f._neuer_ordner()
        self.assertEqual(5, info.call_count)
        frage.assert_not_called()

    def test_neuer_ordner(self) -> None:
        self._entpacken()
        self.f.baum.selection_set("Media/a.dat")      # eine Datei gewaehlt: der Ordner entsteht in ihrem Ordner
        with mock.patch.object(__import__("tkinter.simpledialog", fromlist=["x"]), "askstring", return_value="Neu"):
            self.f._neuer_ordner()
        self.assertTrue(os.path.isdir(os.path.join(self.f.ordner, "Media", "Neu")))

    # ---- Speichern -------------------------------------------------------------------------------------------
    def test_speichern_uebergibt_ordner_ziel_und_format(self) -> None:
        self._entpacken()
        self.aufrufe.clear()
        self.f.format_var.set(".exfat")
        with self._falsche_aufgabe(), \
                mock.patch.object(fz.filedialog, "askdirectory", return_value=str(self.t / "ziel")), \
                mock.patch.object(fz.messagebox, "showinfo") as info:
            self.f._speichern()
        self.assertEqual([(self.f.ordner, str(self.t / "ziel"), "exfat")], self.aufrufe)
        info.assert_called_once()
        self.assertFalse(self.f.beschaeftigt)

    def test_gespeicherte_aenderungen_zaehlen_nicht_mehr_als_offen(self) -> None:
        self._entpacken()
        self.f.baum.selection_set("Media/a.dat")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._loeschen()
        self.assertTrue(self.f._hat_ungespeichertes())
        with self._falsche_aufgabe(), mock.patch.object(fz.filedialog, "askdirectory", return_value=str(self.t / "ziel")), \
                mock.patch.object(fz.messagebox, "showinfo"):
            self.f._speichern()
        self.assertFalse(self.f._hat_ungespeichertes())

    def test_misslungenes_speichern_laesst_die_aenderungen_offen(self) -> None:
        self._entpacken()
        self.f.baum.selection_set("Media/a.dat")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._loeschen()
        with self._falsche_aufgabe(erfolg=False), \
                mock.patch.object(fz.filedialog, "askdirectory", return_value=str(self.t / "ziel")), \
                mock.patch.object(fz.messagebox, "showerror") as fehler:
            self.f._speichern()
        fehler.assert_called_once()
        self.assertTrue(self.f._hat_ungespeichertes())
        self.assertTrue(os.path.isdir(self.f.ordner), "der bearbeitete Ordner bleibt zum erneuten Versuch")

    def test_unvollstaendiges_spiel_wird_vor_dem_speichern_gefragt(self) -> None:
        self._entpacken()
        os.unlink(os.path.join(self.f.ordner, "eboot.bin"))
        self.aufrufe.clear()
        with self._falsche_aufgabe(), mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage, \
                mock.patch.object(fz.filedialog, "askdirectory", return_value=str(self.t / "ziel")) as ordner:
            self.f._speichern()
        frage.assert_called_once()
        self.assertIn("eboot.bin", frage.call_args.args[1])
        ordner.assert_not_called()
        self.assertEqual([], self.aufrufe)

    def test_ohne_zielordner_wird_nichts_gestartet(self) -> None:
        self._entpacken()
        self.aufrufe.clear()
        with self._falsche_aufgabe(), mock.patch.object(fz.filedialog, "askdirectory", return_value=""):
            self.f._speichern()
        self.assertEqual([], self.aufrufe)

    # ---- Schliessen ------------------------------------------------------------------------------------------
    def test_schliessen_raeumt_den_arbeitsordner_weg(self) -> None:
        self._entpacken()
        self.assertTrue(os.listdir(self.t / "arbeit"))
        self.win.destroy()
        self.assertEqual([], os.listdir(self.t / "arbeit"))

    def test_schliessen_mit_ungespeichertem_fragt_und_kann_abbrechen(self) -> None:
        self._entpacken()
        self.f.baum.selection_set("Media/a.dat")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True):
            self.f._loeschen()
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.f._schliessen()
        frage.assert_called_once()
        self.assertTrue(self.win.winfo_exists())
        self.assertTrue(os.path.isdir(self.f.ordner))

    def test_schliessen_waehrend_gearbeitet_wird_ist_gesperrt(self) -> None:
        self.f.beschaeftigt = True
        with mock.patch.object(fz.messagebox, "showinfo") as info:
            self.f._schliessen()
        info.assert_called_once()
        self.assertTrue(self.win.winfo_exists())
        self.f.beschaeftigt = False

    def test_die_texte_gibt_es_in_allen_sprachen(self) -> None:
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        schluessel = [k for k in STRINGS if k.startswith("bearbeiten.")] + ["titlebar.abbild_bearbeiten"]
        self.assertGreater(len(schluessel), 40)
        import re
        for k in schluessel:
            for sprache in SUPPORTED_LANGUAGES:
                self.assertTrue(STRINGS[k].get(sprache, "").strip(), "%s fehlt auf %s" % (k, sprache))
            mengen = {frozenset(re.findall(r"\{(\w+)\}", STRINGS[k][s])) for s in SUPPORTED_LANGUAGES}
            self.assertEqual(1, len(mengen), "%s: Platzhalter unterscheiden sich" % k)

    def test_jede_fehlermeldung_der_logik_hat_einen_text(self) -> None:
        """Jeder Schluessel, den ``abbild_bearbeiten`` meldet, muss uebersetzt sein - sonst sieht man den Rohschluessel."""
        from ps5_validator.utils import abbild_bearbeiten
        from ps5_validator.utils.i18n import STRINGS
        quelle = Path(abbild_bearbeiten.__file__).read_text(encoding="utf-8")
        import re
        for schluessel in set(re.findall(r'"(bearbeiten\.[a-z_]+)"', quelle)):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)

    def test_der_menueeintrag_steht_da(self) -> None:
        self.assertIn(("titlebar.abbild_bearbeiten", "_show_abbild_bearbeiten"),
                      self.haupt.PS5ConverterGUI._MORE_TOOLS_ENTRIES)


if __name__ == "__main__":
    unittest.main()
