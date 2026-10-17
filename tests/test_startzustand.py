# -*- coding: utf-8 -*-
"""Der Startzustand des Bereichs UMWANDELN im echten Programm (Nutzerwunsch vom 11.10.2026).

Beim Oeffnen soll nichts aktiviert sein (AMPR EMU, PlayGo, BACKPORT), AMPR EMU steht auf "Normal" (ohne Pack) mit der
neuesten Fassung ohne Pack, und die Pfadfelder QUELLE, ZIELORDNER und TEMP-ORDNER sind leer - sie werden von Hand gewaehlt.

Das gilt nur fuer ``PS5ConverterGUI(root, start_leer=True)``, den echten Programmstart. Kommandozeile, Diagnose und
Testreihe bauen das Programm ohne den Schalter und behalten die gespeicherten Einstellungen - die Kommandozeile liest
``integrate_ampr`` & Co. aus der Einstellungsdatei.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("startzustand")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ampr_assetpakete            # noqa: E402
from ps5_validator.utils.i18n import AMPR_METHODE_NORMAL    # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _ruhen(sekunden: float, fenster=None) -> None:
    ende = time.perf_counter() + sekunden
    while time.perf_counter() < ende:
        (fenster or _WURZEL).update()
        time.sleep(0.01)


def _fenster() -> "tk.Toplevel":
    top = tk.Toplevel(_WURZEL)
    try:
        top.attributes("-alpha", 0.0)
    except tk.TclError:
        pass
    return top


def _gespeichertes_vorbereiten(ordner: str, ziel: str) -> None:
    """Legt eine Sitzung "wie gestern" in die Einstellungen: alles angekreuzt, alte Fassung, Ordner gemerkt."""
    probe_fenster = _fenster()
    probe = APP.PS5ConverterGUI(probe_fenster)
    try:
        for schluessel, wert in (("integrate_ampr", True), ("integrate_playgo", True), ("integrate_backport", True),
                                 ("integrate_ampr_version", "0.0.0 gestern"), ("integrate_ampr_methode", "assetpack"),
                                 ("temp_dir", ordner), ("dst", ziel), ("src", ordner)):
            probe._save_setting(schluessel, wert)
    finally:
        probe_fenster.destroy()
        _ruhen(0.1)


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class StartLeerTests(unittest.TestCase):
    """Das Programm startet mit start_leer=True, obwohl die Einstellungen von gestern alles gesetzt haben."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ordner = tempfile.mkdtemp(prefix="startzustand_")
        cls.ziel = tempfile.mkdtemp(prefix="startzustand_ziel_")
        _gespeichertes_vorbereiten(cls.ordner, cls.ziel)
        cls.fenster = _fenster()
        cls.app = APP.PS5ConverterGUI(cls.fenster, start_leer=True)
        cls.app._current_language = "de"
        _ruhen(1.5, cls.fenster)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.fenster.destroy()
        except Exception:  # noqa: BLE001
            pass
        APP._rmtree_force(cls.ordner, ignore_errors=True)
        APP._rmtree_force(cls.ziel, ignore_errors=True)

    def test_nichts_ist_angekreuzt(self) -> None:
        a = self.app
        self.assertFalse(a.ampr_integrate_var.get(), "AMPR EMU")
        self.assertFalse(a.ampr_playgo_var.get(), "PlayGo")
        self.assertFalse(a.backport_integrate_var.get(), "BACKPORT")

    def test_die_wahllisten_sind_bis_zum_ankreuzen_gesperrt(self) -> None:
        a = self.app
        for widget in (a.ampr_version_combo, a.ampr_methode_combo, a.backport_fw_combo):
            self.assertEqual("disabled", str(widget.cget("state")))

    def test_playgo_kaestchen_haengt_am_versionsspeicher_nicht_am_ampr_haken(self) -> None:
        """Seit v1.9.83 (nur_playgo): PlayGo laesst sich auch ohne AMPR EMU ankreuzen.

        Das Kaestchen ist also nicht mehr an ``ampr_integrate_var`` gekoppelt - nur noch daran, ob ueberhaupt
        ein Versionsspeicher da ist (``_ampr_versionsauswahl``, hier real vom Bestand der Maschine)."""
        a = self.app
        erwartet = "normal" if a._ampr_versionsauswahl else "disabled"
        self.assertEqual(erwartet, str(a.ampr_playgo_check.cget("state")))

    def test_ampr_emu_steht_auf_normal_ohne_pack(self) -> None:
        a = self.app
        self.assertEqual(AMPR_METHODE_NORMAL, a._ampr_methode())

    def test_die_vorbelegte_fassung_ist_die_neueste_ohne_pack(self) -> None:
        a = self.app
        werte = list(a.ampr_version_combo.cget("values"))
        if not werte:
            self.skipTest("kein AMPR-Versionsspeicher im Bestand")
        gewaehlt = a.ampr_version_var.get()
        self.assertEqual(werte[0], gewaehlt, "die oberste (neueste) Fassung der Liste")
        self.assertNotEqual("0.0.0 gestern", gewaehlt, "die gemerkte Fassung von gestern gilt nicht")
        eintrag = a._ampr_versionsauswahl[gewaehlt]
        self.assertFalse(ampr_assetpakete.variante_kann_packen(str(eintrag.get("variant", ""))),
                         "ohne Pack: keine packfaehige Fassung")
        for beschriftung, e in a._ampr_versionsauswahl.items():
            self.assertFalse(ampr_assetpakete.variante_kann_packen(str(e.get("variant", ""))),
                             "unter Normal steht eine Packfassung: " + beschriftung)

    def test_die_pfadfelder_sind_leer(self) -> None:
        a = self.app
        self.assertEqual("", a.source_path.get(), "QUELLE")
        self.assertEqual("", a.dest_path.get(), "ZIELORDNER")
        self.assertEqual("", a.temp_path.get(), "TEMP-ORDNER")

    def test_die_gespeicherten_gegenstuecke_sind_geleert(self) -> None:
        """Arbeitsfaeden lesen die Einstellung, nicht die Tk-Variable - beide muessen dasselbe sagen."""
        a = self.app
        self.assertFalse(a._load_setting("integrate_ampr", None))
        self.assertFalse(a._load_setting("integrate_playgo", None))
        self.assertFalse(a._load_setting("integrate_backport", None))
        self.assertEqual("", a._load_setting("integrate_ampr_version", None))
        self.assertEqual(AMPR_METHODE_NORMAL, a._load_setting("integrate_ampr_methode", None))
        self.assertEqual("", a._load_setting("temp_dir", None))

    def test_der_zuletzt_benutzte_zielordner_bleibt_fuer_den_dialog_gemerkt(self) -> None:
        """Das Feld ist leer, der Durchsuchen-Dialog beginnt aber dort, wo es zuletzt hinging."""
        self.assertEqual(self.ziel, self.app._load_paths()[1])
        with mock.patch.object(APP.filedialog, "askdirectory", return_value="") as dialog:
            self.app._browse_dest()
        self.assertEqual(self.ziel, dialog.call_args.kwargs["initialdir"])

    def test_ein_leerer_temp_ordner_heisst_standardordner_und_bleibt_leer(self) -> None:
        """Der erste Aufruf (Telemetrie, Vorabpruefung) darf das Feld nicht fuellen, das der Nutzer leer sehen wollte.

        Ein leeres Feld heisst seit v1.9.79 den Standard-Arbeitsordner (Windows: "Temp - Dump-Image Converter" im
        Wurzelverzeichnis des Systemlaufwerks, siehe ``arbeitsordner``; die Testreihe lenkt ihn um), vorher den
        Temp-Ordner des Systems.
        """
        a = self.app
        a._temp_pruefung = None
        benutzt = a._get_runtime_temp_dir()
        self.assertEqual(os.path.normpath(os.environ["PS5CONV_STANDARD_TEMP"]), benutzt)
        self.assertEqual("", a.temp_path.get())
        self.assertEqual("", a._load_setting("temp_dir", None), "auch die Einstellung bleibt leer")

    def test_ein_gewaehlter_temp_ordner_gilt_und_wird_gemerkt(self) -> None:
        a = self.app
        gewaehlt = tempfile.mkdtemp(prefix="startzustand_temp_")
        self.addCleanup(APP._rmtree_force, gewaehlt, ignore_errors=True)
        a.temp_path.set(gewaehlt)
        a._temp_pruefung = None
        try:
            self.assertEqual(os.path.normpath(gewaehlt), a._get_runtime_temp_dir())
            self.assertEqual(os.path.normpath(gewaehlt), a.temp_path.get())
            self.assertEqual(os.path.normpath(gewaehlt), str(a._load_setting("temp_dir", "")))
        finally:
            a.temp_path.set("")
            a._save_setting("temp_dir", "")
            a._temp_pruefung = None

    def test_ohne_ziel_wird_nicht_gestartet(self) -> None:
        """Ein leeres Ziel darf nie zu einem Lauf fuehren - es gibt keinen Standardordner, auch keinen alten."""
        a = self.app
        dump = Path(tempfile.mkdtemp(prefix="startzustand_dump_"))
        self.addCleanup(APP._rmtree_force, str(dump), ignore_errors=True)
        (dump / "sce_sys").mkdir()
        (dump / "sce_sys" / "param.json").write_text('{"titleId": "PPSA00001", "contentId": "EP0000-PPSA00001_00-TESTTESTTESTTEST"}',
                                                     encoding="utf-8")
        (dump / "eboot.bin").write_bytes(b"x" * 128)
        a.source_path.set(str(dump))
        a.dest_path.set("")
        meldungen: list = []
        try:
            with mock.patch.object(APP.messagebox, "showerror", side_effect=lambda *x, **k: meldungen.append(x)), \
                    mock.patch.object(APP.messagebox, "showwarning", side_effect=lambda *x, **k: meldungen.append(x)), \
                    mock.patch.object(APP.messagebox, "askyesno", return_value=False), \
                    mock.patch.object(APP.messagebox, "showinfo", side_effect=lambda *x, **k: meldungen.append(x)):
                a._launch_task()
            self.assertFalse(getattr(a, "is_running", False), "ohne Zielordner darf nichts laufen")
            self.assertTrue(meldungen, "es muss eine Meldung geben")
        finally:
            a.source_path.set("")


@unittest.skipUnless(_TK_DA, "keine Anzeige verfuegbar")
class OhneSchalterTests(unittest.TestCase):
    """Kommandozeile, Diagnose und Testreihe: die gespeicherten Einstellungen gelten wie bisher."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ordner = tempfile.mkdtemp(prefix="startzustand_alt_")
        cls.ziel = tempfile.mkdtemp(prefix="startzustand_alt_ziel_")
        _gespeichertes_vorbereiten(cls.ordner, cls.ziel)
        cls.fenster = _fenster()
        cls.app = APP.PS5ConverterGUI(cls.fenster)
        _ruhen(1.0, cls.fenster)

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            cls.fenster.destroy()
        except Exception:  # noqa: BLE001
            pass
        APP._rmtree_force(cls.ordner, ignore_errors=True)
        APP._rmtree_force(cls.ziel, ignore_errors=True)

    def test_die_gespeicherte_wahl_gilt_weiter(self) -> None:
        a = self.app
        self.assertTrue(a.ampr_playgo_var.get() or a.backport_integrate_var.get() or a.ampr_integrate_var.get(),
                        "ohne den Schalter bleibt die gespeicherte Wahl (die Kommandozeile liest sie)")
        self.assertEqual(self.ziel, a.dest_path.get())
        self.assertEqual(os.path.normpath(self.ordner), a.temp_path.get())
        self.assertEqual("", a.source_path.get(), "die Quelle startete schon immer leer")


class QuelltextTests(unittest.TestCase):
    def test_nur_der_echte_start_setzt_den_schalter(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertEqual(1, quelle.count("PS5ConverterGUI(root, start_leer=True)"),
                         "genau ein Aufruf mit start_leer=True - der echte Programmstart")
        self.assertEqual(3, quelle.count("PS5ConverterGUI(root)"),
                         "die drei uebrigen Aufrufe (zwei Kommandozeilenwege, Diagnose) bleiben ohne den Schalter")


if __name__ == "__main__":
    unittest.main()
