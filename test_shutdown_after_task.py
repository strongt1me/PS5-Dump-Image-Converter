"""Regressionstests für „Rechner nach erfolgreichem Abschluss herunterfahren".

Deckt ab:
  1. Die Entscheidungsregel _should_shutdown_after_task(): nur bei
     ausgeschalteter Laufzeit UND erfolgreichem Abschluss UND aktiver
     Einstellung. Fehler, Abbruch und „läuft noch" verhindern sie.
  2. Der Erfolg wird am Flag _last_task_ok festgemacht, nicht am Statustext –
     ein englischer Statustext darf das Ergebnis nicht verändern.
  3. Die Reihenfolge in _shutdown_cleanup_and_execute(): erst Laufwerke lösen,
     dann Temp-Ziele räumen, erst danach der Herunterfahr-Befehl.
  4. Ein fehlgeschlagener Befehl wird als Fehlschlag gemeldet.

Der eigentliche Befehl wird nie ausgeführt: _execute_shutdown ist am
Testobjekt ersetzt.
"""
from __future__ import annotations

import unittest

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI


def _make_gui(*, aktiviert: bool, ok: bool, laeuft: bool = False) -> PS5ConverterGUI:
    """Baut ein Testobjekt ohne Tk-Fenster (Muster wie test_background_image)."""
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._shutdown_after_success_cli = aktiviert
    gui._last_task_ok = ok
    gui.is_running = laeuft
    gui._shutdown_pending = False
    return gui


class EntscheidungsregelTests(unittest.TestCase):
    def test_erfolg_mit_aktivierter_einstellung_faehrt_herunter(self):
        gui = _make_gui(aktiviert=True, ok=True)
        self.assertTrue(gui._should_shutdown_after_task())

    def test_fehler_faehrt_nicht_herunter(self):
        gui = _make_gui(aktiviert=True, ok=False)
        self.assertFalse(gui._should_shutdown_after_task())

    def test_abbruch_faehrt_nicht_herunter(self):
        # Abbruch setzt in _write_task_report success=False/aborted=True,
        # beides landet als False in _last_task_ok.
        gui = _make_gui(aktiviert=True, ok=False)
        self.assertFalse(gui._should_shutdown_after_task())

    def test_laufende_aufgabe_faehrt_nicht_herunter(self):
        gui = _make_gui(aktiviert=True, ok=True, laeuft=True)
        self.assertFalse(gui._should_shutdown_after_task())

    def test_abgeschaltete_einstellung_faehrt_nicht_herunter(self):
        gui = _make_gui(aktiviert=False, ok=True)
        self.assertFalse(gui._should_shutdown_after_task())

    def test_laufender_countdown_startet_keinen_zweiten(self):
        gui = _make_gui(aktiviert=True, ok=True)
        gui._shutdown_pending = True
        self.assertFalse(gui._should_shutdown_after_task())

    def test_statustext_beeinflusst_die_entscheidung_nicht(self):
        """Der Statustext ist übersetzt und darf nicht ausgewertet werden."""
        gui = _make_gui(aktiviert=True, ok=False)

        class _Label:
            @staticmethod
            def cget(_name):
                return "Completed successfully"

        gui.status_label = _Label()
        self.assertFalse(gui._should_shutdown_after_task())

        gui2 = _make_gui(aktiviert=True, ok=True)
        gui2.status_label = _Label()
        self.assertTrue(gui2._should_shutdown_after_task())


class AblaufTests(unittest.TestCase):
    def _vorbereiten(self, befehl_erfolgreich: bool = True):
        gui = _make_gui(aktiviert=True, ok=True)
        ablauf: list[str] = []
        gui._engine_done_event = None
        gui._force_dismount_all = lambda: ablauf.append("dismount")
        gui._cleanup_exit_temp_targets = lambda *a, **k: ablauf.append("temp")
        gui._execute_shutdown = lambda: (ablauf.append("shutdown"), befehl_erfolgreich)[1]
        return gui, ablauf

    def test_reihenfolge_erst_aufraeumen_dann_herunterfahren(self):
        gui, ablauf = self._vorbereiten()
        self.assertTrue(gui._shutdown_cleanup_and_execute())
        self.assertEqual(ablauf, ["dismount", "temp", "shutdown"])

    def test_laufzeitflags_werden_zurueckgesetzt(self):
        gui, _ = self._vorbereiten()
        gui.is_running = True
        gui.monitor_active = True
        gui._shutdown_cleanup_and_execute()
        self.assertFalse(gui.is_running)
        self.assertFalse(gui.monitor_active)

    def test_fehlgeschlagener_befehl_wird_gemeldet(self):
        gui, ablauf = self._vorbereiten(befehl_erfolgreich=False)
        self.assertFalse(gui._shutdown_cleanup_and_execute())
        self.assertIn("shutdown", ablauf)

    def test_aufraeumfehler_verhindert_das_herunterfahren_nicht(self):
        """Ein Fehler beim Lösen darf den Rechner nicht anlassen –
        gelogged wird er, abgebrochen wird deswegen nicht."""
        gui, ablauf = self._vorbereiten()

        def _kracht():
            ablauf.append("dismount")
            raise OSError("Laufwerk belegt")

        gui._force_dismount_all = _kracht
        self.assertTrue(gui._shutdown_cleanup_and_execute())
        self.assertEqual(ablauf, ["dismount", "shutdown"])


class EinstellungsTests(unittest.TestCase):
    def test_cli_schalter_wirkt_ohne_oberflaeche(self):
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui._shutdown_after_success_cli = True
        self.assertTrue(gui._shutdown_after_success_enabled())

    def test_ohne_alles_ist_die_funktion_aus(self):
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        self.assertFalse(gui._shutdown_after_success_enabled())

    def test_ankreuzfeld_hat_vorrang_vor_dem_cli_wert(self):
        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui._shutdown_after_success_cli = False

        class _Var:
            @staticmethod
            def get():
                return True

        gui.shutdown_after_success = _Var()
        self.assertTrue(gui._shutdown_after_success_enabled())


if __name__ == "__main__":
    unittest.main(verbosity=2)
