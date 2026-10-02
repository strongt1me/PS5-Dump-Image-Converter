# -*- coding: utf-8 -*-
"""Beenden, waehrend der AMPR-Mitschnitt-Assistent laeuft (01.10.2026).

Der Assistent stellt an der Konsole um (ShadowMount+-Schluessel,
Aufnahme-Bibliothek) und im ``finally`` seines Fadens wieder zurueck. Bis
zum 01.10.2026 lehnte sein Fenster das Schliessen ab, solange er
zurueckstellte - das Programm blieb dann einfach offen und musste ein
zweites Mal geschlossen werden. Ein Herunterfahren nach einer Aufgabe
wartete gar nicht.

Jetzt fragt das Beenden einmal, wartet im Hintergrund auf die Rueckstellung
und schliesst danach von selbst; ein zweiter Klick bietet "sofort beenden"
an. Gemessen am echten Fenster des Assistenten, dessen Automatik durch eine
Attrappe ersetzt ist: Sie wartet bis zum Abbruch und "stellt" dann
"zurueck".
"""
from __future__ import annotations

import ast
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("mitschnitt_beenden")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PS5ConverterGUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
ASSISTENT = "_show_ampr_mitschnitt_assistent"

try:
    import tkinter as tk
    # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    tk = None
    _WURZEL = None
    _TK_DA = False


def _text(kennung: str, /, **werte) -> str:
    return STRINGS[kennung]["de"].format(**werte)


def _attrappe() -> PS5ConverterGUI:
    """Ein Programm ohne Oberflaeche - fuer die Regeln selbst."""
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    g._current_language = "de"
    g._mitschnitt_laeufe = {}
    g._mitschnitt_nicht_abwarten = False
    g._protokoll = []
    g._append_to_log = g._protokoll.append
    return g


def _lauf_anmelden(g: PS5ConverterGUI, kennung: int = 1) -> None:
    g._mitschnitt_laeufe[kennung] = {"fenster": None, "abbrechen": lambda: None}


# ------------------------------------------------------------------ Regeln

class WartenTests(unittest.TestCase):
    """_auf_mitschnitt_warten - der Abbau wartet im eigenen Faden."""

    def test_wartet_bis_der_lauf_sich_abmeldet(self) -> None:
        g = _attrappe()
        _lauf_anmelden(g)
        threading.Timer(0.3, lambda: g._mitschnitt_laeufe.pop(1)).start()
        anfang = time.monotonic()
        self.assertTrue(g._auf_mitschnitt_warten())
        self.assertGreaterEqual(time.monotonic() - anfang, 0.25)

    def test_ohne_lauf_geht_es_sofort_weiter(self) -> None:
        g = _attrappe()
        anfang = time.monotonic()
        self.assertTrue(g._auf_mitschnitt_warten())
        self.assertLess(time.monotonic() - anfang, 0.2)

    def test_sofort_beenden_gibt_das_warten_auf(self) -> None:
        g = _attrappe()
        _lauf_anmelden(g)
        threading.Timer(0.2, setattr, (g, "_mitschnitt_nicht_abwarten", True)).start()
        anfang = time.monotonic()
        self.assertFalse(g._auf_mitschnitt_warten())
        self.assertLess(time.monotonic() - anfang, 2.0)
        self.assertTrue(g._mitschnitt_laeuft(), "Der Lauf selbst bleibt angemeldet.")

    def test_ohne_merkmal_laeuft_nichts(self) -> None:
        """Eine Attrappe ohne Aufbau (CLI, alte Tests) hat das Merkmal nicht."""
        self.assertFalse(PS5ConverterGUI.__new__(PS5ConverterGUI)._mitschnitt_laeuft())


class HerunterfahrenTests(unittest.TestCase):
    """Herunterfahren nach der Aufgabe beendet das Programm genauso."""

    def _bereit(self) -> PS5ConverterGUI:
        g = _attrappe()
        g._shutdown_after_success_enabled = lambda: True
        g.is_running = False
        g._pkg_merge_laeuft = 0
        g._bibliothek_uebertragungen = 0
        g._last_task_ok = True
        g._shutdown_pending = False
        return g

    def test_nicht_solange_der_assistent_laeuft(self) -> None:
        g = self._bereit()
        self.assertTrue(g._should_shutdown_after_task(), "Gegenprobe: ohne Assistent ja.")
        _lauf_anmelden(g)
        self.assertFalse(g._should_shutdown_after_task())

    def test_und_das_protokoll_sagt_warum(self) -> None:
        g = self._bereit()
        _lauf_anmelden(g)
        g._start_shutdown_countdown = mock.Mock(side_effect=AssertionError("darf nicht"))
        self.addCleanup(g._start_shutdown_countdown.assert_not_called)
        g._maybe_shutdown_after_task()
        self.assertIn(_text("shutdown.log_mitschnitt") + "\n", g._protokoll)

    def test_ohne_haken_kein_hinweis(self) -> None:
        g = self._bereit()
        g._shutdown_after_success_enabled = lambda: False
        _lauf_anmelden(g)
        g._maybe_shutdown_after_task()
        self.assertEqual([], g._protokoll)


class SegmentWartenTests(unittest.TestCase):
    """Ein Abbruch, bevor die Warteanzeige steht, ging bis zum 01.10. verloren."""

    def test_abbruch_vor_der_anzeige_weckt_den_faden(self) -> None:
        g = _attrappe()
        # Die Anzeige kommt nie dran - also traegt auch niemand das Ereignis
        # ein, das der Abbruch setzen koennte.
        g._spaeter_im_fenster = lambda _fenster, _rueckruf, *_a: True
        ergebnis: list = []
        faden = threading.Thread(target=lambda: ergebnis.append(
            g._ampr_mitschnitt_segment_warten(None, {}, "Lauf", 1, 5, lambda: True)),
            daemon=True)
        faden.start()
        faden.join(3.0)
        self.assertFalse(faden.is_alive(),
                         "Der Faden schlaeft trotz Abbruch bis zur Zeitgrenze (6 h).")
        self.assertEqual([False], ergebnis)


class VerdrahtungTests(unittest.TestCase):
    """Was am Syntaxbaum zu sehen ist."""

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        cls.methoden = {k.name: k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)}

    @staticmethod
    def _innere(methode: ast.FunctionDef, name: str) -> ast.FunctionDef:
        return next(k for k in ast.walk(methode)
                    if isinstance(k, ast.FunctionDef) and k.name == name)

    @staticmethod
    def _rufe(knoten: ast.AST) -> list:
        """Aufrufnamen in Quelltextreihenfolge - ast.walk allein geht in die
        Breite und stellte einen verschachtelten Aufruf hinter einen flachen."""
        aufrufe = [k for k in ast.walk(knoten) if isinstance(k, ast.Call)]
        aufrufe.sort(key=lambda k: (k.lineno, k.col_offset))
        return [getattr(k.func, "attr", getattr(k.func, "id", "")) for k in aufrufe]

    def test_der_abbau_wartet_zuerst_auf_den_assistenten(self) -> None:
        rufe = self._rufe(self._innere(self.methoden["on_closing"], "_shutdown"))
        self.assertIn("_auf_mitschnitt_warten", rufe)
        self.assertLess(rufe.index("_auf_mitschnitt_warten"), rufe.index("_force_dismount_all"))
        self.assertLess(rufe.index("_auf_mitschnitt_warten"), rufe.index("_hauptfaden_planen"))

    def test_countdown_bricht_ab_wenn_der_assistent_startet(self) -> None:
        tick = self._innere(self.methoden["_start_shutdown_countdown"], "_tick")
        self.assertIn("_mitschnitt_laeuft", self._rufe(tick))

    def test_abmeldung_steht_im_finally_nach_der_automatik(self) -> None:
        lauf = self._innere(self.methoden[ASSISTENT], "_lauf")
        versuch = next(k for k in lauf.body if isinstance(k, ast.Try))
        self.assertIn("_ampr_mitschnitt_automatik", self._rufe(ast.Module(versuch.body, [])))
        abmeldung = [k for teil in versuch.finalbody for k in ast.walk(teil)
                     if isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "pop"
                     and "_mitschnitt_laeufe" in ast.unparse(k.func)]
        self.assertTrue(abmeldung, "Ohne Abmeldung im finally wartete das Beenden ewig.")


# --------------------------------------------------------- echtes Fenster

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class BeendenTests(unittest.TestCase):
    """on_closing mit laufendem Assistenten - echtes Fenster, Attrappen-Automatik."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        # Der Aufbau zeigt und maximiert die Wurzel - Rueckfragen erschienen
        # sonst echt auf dem Bildschirm (siehe test_ordner_einbau.FensterTests).
        _WURZEL.withdraw()
        for kind in _WURZEL.winfo_children():
            if isinstance(kind, tk.Toplevel):
                kind.withdraw()

    # -- Aufbau ------------------------------------------------------------

    def setUp(self) -> None:
        app = self.app
        app._werkzeugfenster.clear()
        self.ablauf: list[str] = []
        self.fragen: list[str] = []
        self.warnungen: list[str] = []
        self.protokoll: list[str] = []
        self.gestartet = threading.Event()
        self.zurueck_frei = threading.Event()
        self.zurueck_frei.set()
        self.zerstoert = threading.Event()
        self.echte_rueckstellung = False

        echt_planen = app._hauptfaden_planen

        def _planen(rueckruf, *args, **kwargs):
            # Das Hauptfenster wirklich zu zerstoeren, nahme allen Tests die
            # Wurzel - hier wird nur festgehalten, dass es so weit kam.
            if rueckruf == app.root.destroy:
                self.ablauf.append("destroy")
                self.zerstoert.set()
                return True
            return echt_planen(rueckruf, *args, **kwargs)

        for name, wert in (("_force_dismount_all", lambda: None),
                           ("_cleanup_exit_temp_targets", lambda **_k: None),
                           ("_fenstergeometrie_merken", lambda: None),
                           ("_hauptfaden_planen", _planen),
                           ("_append_to_log", self.protokoll.append),
                           ("_ampr_mitschnitt_automatik", self._automatik)):
            flicken = mock.patch.object(app, name, wert)
            flicken.start()
            self.addCleanup(flicken.stop)
        flicken = mock.patch.object(APP.messagebox, "showwarning", self._warnung)
        flicken.start()
        self.addCleanup(flicken.stop)
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self) -> None:
        """Jeden Lauf beenden, alles zuruecksetzen - auch nach einem Fehlschlag."""
        app = self.app
        self.zurueck_frei.set()
        for lauf in list(app._mitschnitt_laeufe.values()):
            lauf["abbrechen"]()
        self._schleife_bis(lambda: not app._mitschnitt_laeufe, 5.0)
        for fenster in list(app._werkzeugfenster.values()):
            try:
                if fenster.winfo_exists():
                    fenster.destroy()
            except tk.TclError:
                pass
        app._werkzeugfenster.clear()
        app._beenden_wartet_auf_mitschnitt = False
        app._mitschnitt_nicht_abwarten = False
        app._mitschnitt_rueckstellung_offen = ""
        _WURZEL.update()

    # -- Attrappen ---------------------------------------------------------

    def _automatik(self, win, melde, _segment_ui, abgebrochen) -> None:
        """Wartet wie beim Spielen bis zum Abbruch, dann "Rueckstellung"."""
        self.gestartet.set()
        while not abgebrochen():
            time.sleep(0.02)
        if self.echte_rueckstellung:
            # Die echte Rueckstellung gegen einen Port, an dem niemand horcht.
            ordner = tempfile.mkdtemp(prefix="mitschnitt_beenden_")
            rueckweg = {"config": {"vorher": "x", "geschrieben": None,
                                   "werte": {"update_emulators": None}},
                        "dateien": [], "sicherung": ordner}
            self.app._ampr_mitschnitt_zurueckstellen("127.0.0.1", rueckweg, melde)
        else:
            melde("Attrappe: stelle zurueck")
            self.zurueck_frei.wait(10.0)
            time.sleep(0.2)
        self.ablauf.append("zurueckgestellt")

    def _ja(self, _titel, text, **_k) -> bool:
        self.fragen.append(text)
        return True

    def _nein(self, _titel, text, **_k) -> bool:
        self.fragen.append(text)
        return False

    def _warnung(self, _titel, text, **_k) -> None:
        self.ablauf.append("warnung")
        self.warnungen.append(text)

    # -- Hilfen ------------------------------------------------------------

    @staticmethod
    def _schleife_bis(bedingung, frist: float) -> bool:
        """Echte mainloop, bis ``bedingung`` gilt - Faeden melden sich nur dann."""
        ende = time.monotonic() + frist

        def _wache() -> None:
            if bedingung() or time.monotonic() >= ende:
                _WURZEL.quit()
                return
            _WURZEL.after(20, _wache)

        _WURZEL.after(20, _wache)
        _WURZEL.mainloop()
        return bool(bedingung())

    def _assistent_starten(self):
        self.app._werkzeugfenster_umschalten(ASSISTENT)
        fenster = self.app._werkzeugfenster[ASSISTENT]
        fenster.withdraw()
        self.assertTrue(self._schleife_bis(self.gestartet.is_set, 5.0),
                        "Der Lauf des Assistenten startete nicht.")
        self.assertTrue(self.app._mitschnitt_laeuft())
        return fenster

    # -- Pruefungen --------------------------------------------------------

    def test_beenden_wartet_auf_die_rueckstellung_und_schliesst_dann(self) -> None:
        fenster = self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0),
                        "Das Programm schloss nach der Rueckstellung nicht von selbst.")
        self.assertEqual(["zurueckgestellt", "destroy"], self.ablauf)
        self.assertEqual([_text("amprmitschnitt.quit_confirm")], self.fragen)
        self.assertIn(_text("amprmitschnitt.quit_waiting") + "\n", self.protokoll)
        self.assertFalse(self.app._mitschnitt_laeuft())
        self.assertTrue(self._schleife_bis(lambda: not fenster.winfo_exists(), 3.0),
                        "Das Fenster des Assistenten blieb stehen.")

    def test_nein_laesst_alles_laufen(self) -> None:
        fenster = self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._nein):
            self.app.on_closing()
        self._schleife_bis(lambda: False, 0.4)
        self.assertEqual([], self.ablauf, "Nach Nein wurde abgebrochen oder beendet.")
        self.assertTrue(self.app._mitschnitt_laeuft())
        self.assertTrue(fenster.winfo_exists())
        self.assertFalse(self.app._beenden_wartet_auf_mitschnitt)

    def test_zweiter_klick_beendet_sofort(self) -> None:
        self.zurueck_frei.clear()                      # die Rueckstellung haengt
        self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            self.app.on_closing()
            self._schleife_bis(lambda: False, 0.5)
            self.assertFalse(self.zerstoert.is_set(), "Das Beenden wartete nicht.")
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 5.0))
        self.assertEqual(["destroy"], self.ablauf, "Es wurde doch abgewartet.")
        self.assertEqual([_text("amprmitschnitt.quit_confirm"),
                          _text("amprmitschnitt.quit_now_confirm")], self.fragen)

    def test_zweiter_klick_nein_wartet_weiter(self) -> None:
        self.zurueck_frei.clear()
        self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            self.app.on_closing()
        with mock.patch.object(APP.messagebox, "askyesno", self._nein):
            self._schleife_bis(lambda: False, 0.3)
            self.app.on_closing()
            self._schleife_bis(lambda: False, 0.3)
        self.assertFalse(self.zerstoert.is_set())
        self.zurueck_frei.set()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0))
        self.assertEqual(["zurueckgestellt", "destroy"], self.ablauf)

    def test_offene_punkte_erscheinen_vor_dem_schliessen(self) -> None:
        """Mit dem Fenster verschwaende das Protokoll - also eine Meldung davor."""
        self.echte_rueckstellung = True
        flicken = mock.patch.object(self.app, "_ps5_ftp_port", lambda: 1)  # niemand horcht
        flicken.start()
        self.addCleanup(flicken.stop)
        self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 15.0))
        self.assertEqual(["zurueckgestellt", "warnung", "destroy"], self.ablauf)
        self.assertIn("update_emulators", self.warnungen[0])

    def test_alte_offene_punkte_erscheinen_nicht(self) -> None:
        """Was ein frueherer Lauf offen liess, stand damals schon im Protokoll."""
        self.app._mitschnitt_rueckstellung_offen = "ALT"
        self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 10.0))
        self.assertEqual([], self.warnungen)

    def test_ohne_assistent_keine_frage(self) -> None:
        """Gegenprobe: Das gewoehnliche Beenden bleibt, wie es war."""
        frage = mock.Mock(side_effect=AssertionError("unerwartete Frage"))
        with mock.patch.object(APP.messagebox, "askyesno", frage):
            self.app.on_closing()
        self.assertTrue(self._schleife_bis(self.zerstoert.is_set, 5.0))
        frage.assert_not_called()
        self.assertEqual(["destroy"], self.ablauf)

    def test_das_fenster_fragt_nicht_zweimal(self) -> None:
        """Schon abgebrochen, stellt zurueck: Das Kreuz des Assistenten fragt nicht erneut."""
        self.zurueck_frei.clear()
        fenster = self._assistent_starten()
        with mock.patch.object(APP.messagebox, "askyesno", self._ja):
            fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
            self._schleife_bis(lambda: False, 0.3)
            fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
        self.assertEqual([_text("amprmitschnitt.close_confirm")], self.fragen)
        self.assertTrue(fenster.winfo_exists(), "Das Fenster ging vor der Rueckstellung zu.")
        self.zurueck_frei.set()
        self.assertTrue(self._schleife_bis(lambda: not fenster.winfo_exists(), 5.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
