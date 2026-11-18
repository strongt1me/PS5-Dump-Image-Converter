# -*- coding: utf-8 -*-
"""PlayGo und DLC EMU werden nach dem gewaehlten Spiel selbst angehakt (Nutzerwunsch 18.11.2026).

"Wenn ein Spiel PlayGo-Inhalt enthaelt, soll PlayGo bitte automatisch angehakt werden. Das selbe bitte auch bei DLC-Inhalt."
Bis dahin stand nur der Hinweis "PlayGo empfohlen ... Beim Erstellen den Haken setzen" im Protokoll.

Die Regeln, die hier gehalten werden:

* Hat das Spiel die Inhalte, geht der Haken an - ohne Rueckfrage, ohne dass es gespeichert wird.
* Ein Haken, den das Programm gesetzt hat, wird wieder zurueckgenommen, wenn das naechste Spiel ihn nicht braucht oder es kein
  einzelnes Spiel mehr gibt (sonst bekaeme es stumm einen Stub, den es nicht braucht).
* Ein Haken, den der Anwender selbst gesetzt hat, wird nie angefasst.
* Nicht einsehbare Quelle (``None``) und laufender Auftrag: nichts aendert sich.
* Klickt der Anwender irgendeinen Haken an, speichert ``_on_integration_changed`` alle - ein automatisch gesetzter darf dabei
  nicht festgeschrieben werden.
"""
from __future__ import annotations

import ast
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("haken_nach_quelle")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
PLAYGO = "sce_sys/playgo-scenario.json"


class _Wert:
    """Steht fuer eine Tk-Variable: get und set, sonst nichts."""

    def __init__(self, wert) -> None:
        self.wert = wert

    def get(self):
        return self.wert

    def set(self, wert) -> None:
        self.wert = wert


def _gui(playgo: bool = False, dlc: bool = False) -> GUI:
    gui = GUI.__new__(GUI)
    gui._current_language = "de"
    gui._calc_generation = 7
    gui.is_running = False
    gui.zeilen = []
    gui._append_to_log = gui.zeilen.append
    gui._hauptfaden_planen = lambda *a, **k: None
    gui.ampr_playgo_var = _Wert(playgo)
    gui.dlc_integrate_var = _Wert(dlc)
    gui.nachgezogen = []
    gui._on_integration_changed = lambda speichern=True: gui.nachgezogen.append(speichern)
    gui.gespeichert = []
    gui._save_setting = lambda schluessel, wert: gui.gespeichert.append((schluessel, wert))
    return gui


class _Spiele(unittest.TestCase):
    def setUp(self) -> None:
        self.wurzel = Path(tempfile.mkdtemp(prefix="haken_nach_quelle_"))
        self.addCleanup(shutil.rmtree, self.wurzel, True)

    def spiel(self, name: str, *, playgo: bool = False, dlc: bool = False) -> str:
        ordner = self.wurzel / name
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "eboot.bin").write_bytes(b"x")
        if playgo:
            (ordner / "sce_sys" / "playgo-scenario.json").write_text("{}", encoding="utf-8")
        if dlc:
            (ordner / "addcont0").mkdir()
            (ordner / "addcont0" / "inhalt.pkg").write_bytes(b"x")
        return str(ordner)

    @staticmethod
    def waehlen(gui: GUI, quelle: str) -> str:
        """Was beim Waehlen einer Quelle im Hintergrund geschieht (Aufgaben 1 bis 6) - hier im Hauptfaden."""
        gui._quelle_einbauten_pruefen(quelle, 7)
        return "".join(gui.zeilen)


class AnhakenTests(_Spiele):
    def test_playgo_inhalt_hakt_playgo_an_ohne_zu_speichern(self) -> None:
        gui = _gui()
        text = self.waehlen(gui, self.spiel("a", playgo=True))
        self.assertTrue(gui.ampr_playgo_var.get())
        self.assertFalse(gui.dlc_integrate_var.get())
        self.assertIn("Haken „PlayGo“ automatisch gesetzt", text)
        self.assertIn(PLAYGO, text)
        self.assertEqual([], gui.gespeichert, "ein automatischer Haken ist keine Einstellung")
        self.assertEqual([False], gui.nachgezogen, "Listen und Sperren ziehen nach, ohne zu speichern")

    def test_dlc_inhalt_hakt_dlc_an(self) -> None:
        gui = _gui()
        text = self.waehlen(gui, self.spiel("b", dlc=True))
        self.assertTrue(gui.dlc_integrate_var.get())
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertIn("Haken „DLC EMU“ automatisch gesetzt", text)
        self.assertEqual([], gui.gespeichert)

    def test_die_hinweise_zu_playgo_und_dlc_stehen_im_protokoll(self) -> None:
        """Nutzerwunsch 18.11.2026: Die Meldung "⚠ PlayGo-Dateien gefunden (...) - PlayGo beim Backup einbinden!" von Seite 7 steht
        so im Status-Log, und derselbe Hinweis gilt fuer Zusatzinhalte (DLC)."""
        text = self.waehlen(_gui(), self.spiel("h", playgo=True, dlc=True))
        self.assertIn("⚠ PlayGo-Dateien gefunden (sce_sys/playgo-scenario.json) – PlayGo beim Backup einbinden!", text)
        self.assertIn("⚠ DLC-Inhalte gefunden (addcont0/) – DLC EMU beim Backup einbinden!", text)

    def test_ohne_dlc_kein_dlc_hinweis(self) -> None:
        text = self.waehlen(_gui(), self.spiel("i", playgo=True))
        self.assertIn("PlayGo-Dateien gefunden", text)
        self.assertNotIn("DLC-Inhalte gefunden", text)

    def test_beides_zusammen(self) -> None:
        gui = _gui()
        self.waehlen(gui, self.spiel("c", playgo=True, dlc=True))
        self.assertTrue(gui.ampr_playgo_var.get())
        self.assertTrue(gui.dlc_integrate_var.get())

    def test_ohne_inhalte_bleibt_alles_aus(self) -> None:
        gui = _gui()
        text = self.waehlen(gui, self.spiel("d"))
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertFalse(gui.dlc_integrate_var.get())
        self.assertNotIn("automatisch gesetzt", text)
        self.assertEqual([], gui.nachgezogen)

    def test_der_hinweis_verlangt_den_haken_nicht_mehr_vom_anwender(self) -> None:
        text = self.waehlen(_gui(), self.spiel("e", playgo=True))
        self.assertIn("PlayGo-Dateien gefunden", text)
        self.assertNotIn("Beim Erstellen den Haken", text)

    def test_ein_schon_gesetzter_haken_wird_nicht_zum_automatischen(self) -> None:
        """Der Anwender hat PlayGo selbst angehakt: kein Protokolleintrag, und beim naechsten Spiel bleibt er stehen."""
        gui = _gui(playgo=True)
        text = self.waehlen(gui, self.spiel("f", playgo=True))
        self.assertNotIn("automatisch gesetzt", text)
        self.assertFalse(gui._haken_auto.get("ampr_playgo_var"))
        self.waehlen(gui, self.spiel("g"))
        self.assertTrue(gui.ampr_playgo_var.get(), "der eigene Haken des Anwenders bleibt")


class ZuruecknehmenTests(_Spiele):
    def test_naechstes_spiel_ohne_inhalt_nimmt_den_automatischen_haken_zurueck(self) -> None:
        gui = _gui()
        self.waehlen(gui, self.spiel("a", playgo=True, dlc=True))
        gui.zeilen.clear()
        text = self.waehlen(gui, self.spiel("b"))
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertFalse(gui.dlc_integrate_var.get())
        self.assertIn("Haken „PlayGo“ wieder entfernt", text)
        self.assertIn("Haken „DLC EMU“ wieder entfernt", text)
        self.assertEqual([], gui.gespeichert)

    def test_der_eigene_haken_des_anwenders_wird_nie_zurueckgenommen(self) -> None:
        gui = _gui(dlc=True)                 # vom Anwender angehakt
        self.waehlen(gui, self.spiel("a", playgo=True))   # PlayGo kommt automatisch dazu
        self.waehlen(gui, self.spiel("b"))
        self.assertFalse(gui.ampr_playgo_var.get(), "der automatische geht wieder")
        self.assertTrue(gui.dlc_integrate_var.get(), "der eigene bleibt")

    def test_zwei_spiele_mit_inhalt_hintereinander_lassen_den_haken_stehen(self) -> None:
        gui = _gui()
        self.waehlen(gui, self.spiel("a", playgo=True))
        gui.zeilen.clear()
        text = self.waehlen(gui, self.spiel("b", playgo=True))
        self.assertTrue(gui.ampr_playgo_var.get())
        self.assertNotIn("wieder entfernt", text)

    def test_ohne_einzelspiel_gehen_die_automatischen_haken_zurueck(self) -> None:
        gui = _gui()
        self.waehlen(gui, self.spiel("a", playgo=True, dlc=True))
        gui._einbauten_geprueft_fuer = ("etwas", 1)
        gui._haken_auto_zuruecknehmen()
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertFalse(gui.dlc_integrate_var.get())
        self.assertIsNone(gui._einbauten_geprueft_fuer,
                          "dasselbe Spiel muss danach wieder geprueft werden, sonst bliebe es ohne Haken")

    def test_zuruecknehmen_ohne_automatische_haken_tut_nichts(self) -> None:
        gui = _gui(playgo=True, dlc=True)
        gui._einbauten_geprueft_fuer = ("etwas", 1)
        gui._haken_auto_zuruecknehmen()
        self.assertTrue(gui.ampr_playgo_var.get())
        self.assertTrue(gui.dlc_integrate_var.get())
        self.assertEqual(("etwas", 1), gui._einbauten_geprueft_fuer)


class GrenzenTests(_Spiele):
    def test_nicht_einsehbar_laesst_die_haken_wie_sie_sind(self) -> None:
        gui = _gui()
        self.waehlen(gui, self.spiel("a", playgo=True))
        gui._haken_nach_quelle(None, None)                   # etwa ein .ffpkg ohne Dump Forge
        self.assertTrue(gui.ampr_playgo_var.get(), "unbekannt heisst nicht 'nicht noetig'")
        gui2 = _gui()
        gui2._haken_nach_quelle(PLAYGO, None)
        self.assertTrue(gui2.ampr_playgo_var.get())
        self.assertFalse(gui2.dlc_integrate_var.get())

    def test_waehrend_eines_laufs_aendert_sich_nichts(self) -> None:
        gui = _gui()
        gui.is_running = True
        gui._haken_nach_quelle(PLAYGO, "addcont0/")
        self.assertFalse(gui.ampr_playgo_var.get())
        self.assertFalse(gui.dlc_integrate_var.get())
        gui.is_running = False
        gui._haken_nach_quelle(PLAYGO, "")
        gui.is_running = True
        gui._haken_nach_quelle("", "")
        self.assertTrue(gui.ampr_playgo_var.get(), "auch das Zuruecknehmen wartet bis nach dem Lauf")

    def test_aus_einem_faden_wird_im_hauptfaden_gesetzt(self) -> None:
        gui = _gui()
        geplant: list = []
        gui._hauptfaden_planen = lambda rueckruf, *a, **k: geplant.append((rueckruf, a))
        faden = threading.Thread(target=lambda: gui._haken_nach_quelle(PLAYGO, ""))
        faden.start()
        faden.join()
        self.assertFalse(gui.ampr_playgo_var.get(), "im Faden wird kein Tk-Wert angefasst")
        self.assertEqual(1, len(geplant))
        rueckruf, args = geplant[0]
        rueckruf(*args)
        self.assertTrue(gui.ampr_playgo_var.get())


class SpeichernTests(unittest.TestCase):
    def test_ein_automatischer_haken_wird_nicht_festgeschrieben(self) -> None:
        gui = _gui(playgo=True)
        gui._haken_auto = {"ampr_playgo_var": True}
        self.assertFalse(gui._haken_wert_zum_speichern("ampr_playgo_var"))

    def test_ein_eigener_haken_wird_gespeichert(self) -> None:
        gui = _gui(playgo=True, dlc=True)
        self.assertTrue(gui._haken_wert_zum_speichern("ampr_playgo_var"))
        gui._haken_auto = {"ampr_playgo_var": True}
        self.assertTrue(gui._haken_wert_zum_speichern("dlc_integrate_var"), "ein anderer Haken ist davon unberuehrt")

    def test_hakt_der_anwender_ihn_ab_ist_er_nicht_mehr_automatisch(self) -> None:
        gui = _gui(playgo=True)
        gui._haken_auto = {"ampr_playgo_var": True}
        gui.ampr_playgo_var.set(False)
        self.assertFalse(gui._haken_wert_zum_speichern("ampr_playgo_var"))
        self.assertFalse(gui._haken_auto["ampr_playgo_var"])
        gui.ampr_playgo_var.set(True)                       # der Anwender hakt ihn selbst wieder an
        self.assertTrue(gui._haken_wert_zum_speichern("ampr_playgo_var"))

    def test_der_hakenhandler_speichert_ueber_diese_stelle(self) -> None:
        """Wer in ``_on_integration_changed`` wieder ``.get()`` speichert, schreibt den automatischen Haken fest."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        baum = ast.parse(quelle)
        funktion = next(n for n in ast.walk(baum)
                        if isinstance(n, ast.FunctionDef) and n.name == "_on_integration_changed")
        text = ast.get_source_segment(quelle, funktion) or ""
        for schluessel, name in (("integrate_playgo", "ampr_playgo_var"), ("integrate_dlc", "dlc_integrate_var")):
            with self.subTest(haken=name):
                self.assertIn('self._save_setting("%s", self._haken_wert_zum_speichern("%s"))' % (schluessel, name), text)
                self.assertNotIn('self._save_setting("%s", bool(self.%s.get()))' % (schluessel, name), text)


try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


@unittest.skipUnless(TK_DA, "keine Anzeige")
class EchtesFensterTests(_Spiele):
    """Das fertige Hauptfenster: Waehlen -> Hintergrundpruefung -> Haken im Fenster; Klick speichert nur die eigene Wahl."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = GUI(_WURZEL)
        cls.app._online_nachschlag_erlaubt = lambda: False
        cls.app._current_language = "de"

    def setUp(self) -> None:
        super().setUp()
        app = self.app
        self.protokoll: list = []
        self.gespeichert: list = []
        app._append_to_log = lambda text, *a, **k: self.protokoll.append(text)
        app._save_setting = lambda schluessel, wert: self.gespeichert.append((schluessel, wert))
        self.addCleanup(self._zuruecksetzen)
        self._zuruecksetzen(erst=True)

    def _zuruecksetzen(self, erst: bool = False) -> None:
        app = self.app
        app.is_running = False
        app.ampr_playgo_var.set(False)
        app.dlc_integrate_var.set(False)
        app._haken_auto = {}
        app._einbauten_geprueft_fuer = None
        if not erst:
            for name in ("_append_to_log", "_save_setting"):
                app.__dict__.pop(name, None)

    def _laufen(self, anlass, bedingung, sekunden: float = 20.0) -> bool:
        """Fuehrt ``anlass`` in der Hauptschleife aus und wartet dort auf ``bedingung``.

        Die Hauptschleife muss laufen: Ein Faden darf ``root.after`` nur dann aufrufen (sonst "main thread is not in main loop",
        und ``_hauptfaden_planen`` schluckt den Fehler) - mit blossem ``update()`` ginge der Rueckruf des Pruefthreads verloren.
        """
        import time
        ende = time.monotonic() + sekunden

        def pruefen() -> None:
            if bedingung() or time.monotonic() > ende:
                _WURZEL.quit()
            else:
                _WURZEL.after(20, pruefen)

        _WURZEL.after(0, anlass)
        _WURZEL.after(20, pruefen)
        _WURZEL.mainloop()
        return bool(bedingung())

    def _waehlen(self, quelle: str, bedingung) -> bool:
        """Waehlt eine Quelle wie der Anwender (Aufgabe 1, Dump-Ordner: Modus und Quellfeld) und wartet auf ``bedingung``.

        Der Weg ist der echte: die Spur auf dem Quellfeld ruft ``_on_source_path_changed``, das die Pruefung anstoesst.
        """
        modus, alte_quelle = self.app.current_mode.get(), self.app.source_path.get()
        self.addCleanup(self.app.source_path.set, alte_quelle)
        self.addCleanup(self.app.current_mode.set, modus)

        def waehlen() -> None:
            self.app.current_mode.set("pack_folder")
            self.app.source_path.set(quelle)

        return self._laufen(waehlen, bedingung)

    def test_waehlen_hakt_die_kaestchen_an_und_ein_klick_schreibt_sie_nicht_fest(self) -> None:
        app = self.app
        self.assertTrue(self._waehlen(self.spiel("a", playgo=True, dlc=True),
                                      lambda: app.ampr_playgo_var.get() and app.dlc_integrate_var.get()),
                        "".join(self.protokoll))
        self.assertEqual([], self.gespeichert, "das Anhaken allein speichert nichts")
        # Der Anwender klickt irgendeinen Haken: ``_on_integration_changed`` speichert alle - hier nur seine eigene Wahl.
        app._on_integration_changed()
        gespeichert = dict(self.gespeichert)
        self.assertIs(False, gespeichert["integrate_playgo"])
        self.assertIs(False, gespeichert["integrate_dlc"])
        self.assertTrue(app.ampr_playgo_var.get(), "im Fenster bleibt der Haken gesetzt")

    def test_ein_anderes_spiel_ohne_inhalt_nimmt_sie_zurueck(self) -> None:
        app = self.app
        self.assertTrue(self._waehlen(self.spiel("a", playgo=True), lambda: app.ampr_playgo_var.get()))
        self.assertTrue(self._waehlen(self.spiel("b"), lambda: not app.ampr_playgo_var.get()), "".join(self.protokoll))
        self.assertIn("wieder entfernt", "".join(self.protokoll))

    def test_ein_hinweis_steht_im_status_log_in_der_warnfarbe(self) -> None:
        """Eine Zeile mit "⚠" steht im Status-Log in der Warnfarbe des Designs, jede andere in der gewohnten."""
        app = self.app
        for name in ("_append_to_log",):
            app.__dict__.pop(name, None)                         # hier zaehlt das echte Protokoll, nicht der Mitschreiber
        ansicht = app.console_view
        ansicht.delete("1.0", "end")
        app._append_to_log("[Prüfung] eine gewöhnliche Zeile\n")
        app._append_to_log("⚠ PlayGo-Dateien gefunden (sce_sys/playgo-scenario.json) – PlayGo beim Backup einbinden!\n")
        app._append_to_log("⚠ DLC-Inhalte gefunden (addcont0/) – DLC EMU beim Backup einbinden!\n")
        for _ in range(20):
            _WURZEL.update()
        markiert = ansicht.tag_ranges(app._LOG_HINWEIS_TAG)
        # Aneinanderliegende markierte Zeilen fasst Tk zu einem Bereich zusammen - darum nach Zeilen aufteilen.
        zeilen = [z.strip() for a, e in zip(markiert[0::2], markiert[1::2])
                  for z in ansicht.get(str(a), str(e)).splitlines() if z.strip()]
        self.assertEqual(["⚠ PlayGo-Dateien gefunden (sce_sys/playgo-scenario.json) – PlayGo beim Backup einbinden!",
                          "⚠ DLC-Inhalte gefunden (addcont0/) – DLC EMU beim Backup einbinden!"], zeilen)
        self.assertEqual(app._COLORS.get("fg_warning"), str(ansicht.tag_cget(app._LOG_HINWEIS_TAG, "foreground")))
        self.assertIn("gewöhnliche Zeile", ansicht.get("1.0", "end"))

    def test_die_sammelkonvertierung_bekommt_keinen_haken_vom_vorigen_spiel(self) -> None:
        app = self.app
        self.assertTrue(self._waehlen(self.spiel("a", playgo=True), lambda: app.ampr_playgo_var.get()),
                        "".join(self.protokoll))
        # Kein Einzelspiel mehr: Die Sammelkonvertierung wuerde sonst jedes ihrer Spiele mit PlayGo einbauen.
        self.assertTrue(self._laufen(lambda: app.current_mode.set("batch_convert"),
                                     lambda: not app.ampr_playgo_var.get()), "".join(self.protokoll))


class QuellwechselTests(unittest.TestCase):
    def test_bei_leerer_quelle_und_anderen_aufgaben_werden_die_haken_zurueckgenommen(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        funktion = next(n for n in ast.walk(ast.parse(quelle))
                        if isinstance(n, ast.FunctionDef) and n.name == "_on_source_path_changed")
        text = ast.get_source_segment(quelle, funktion) or ""
        self.assertIn("self._haken_auto_zuruecknehmen()", text)
        # Seite 7 fuehrt ihre Haken nach ihrer eigenen Wahl nach - ein Quellwechsel im Hauptfenster darf sie nicht abraeumen.
        self.assertIn('mode != "pkg_fpkg"', text)
        self.assertIn("mode not in self._EINBAU_PRUEFEN_MODI", text)

    def test_seite_7_und_aufgaben_nutzen_dieselbe_stelle(self) -> None:
        """Beide Wege (Aufgaben 1-6 und Seite 7) lesen ihre Zeilen aus ``_quelle_einbauten_zeilen`` - dort wird angehakt."""
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        funktion = next(n for n in ast.walk(ast.parse(quelle))
                        if isinstance(n, ast.FunctionDef) and n.name == "_quelle_einbauten_zeilen")
        self.assertIn("self._haken_nach_quelle(", ast.get_source_segment(quelle, funktion) or "")
        seite7 = (PROJEKT / "ps5_validator" / "ui" / "ps5_pkg_fenster.py").read_text(encoding="utf-8")
        self.assertIn("self.g._quelle_einbauten_zeilen(", seite7)


class TexteTests(unittest.TestCase):
    SPRACHEN = ("de", "en", "es", "it", "fr")

    def test_die_neuen_texte_gibt_es_in_allen_sprachen(self) -> None:
        for schluessel, felder in (("einbau_pruefung.haken_gesetzt", ("{name}", "{merkmal}")),
                                   ("einbau_pruefung.haken_entfernt", ("{name}",))):
            for sprache in self.SPRACHEN:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertTrue(text.startswith("["), text)
                    self.assertTrue(text.endswith("\n"), text)
                    for feld in felder:
                        self.assertIn(feld, text)

    #: Die Aufforderung, den Haken selbst zu setzen, je Sprache - sie ist mit dem automatischen Haken ueberfluessig.
    AUFFORDERUNG = {"de": "Haken", "en": "Tick", "es": "Marque", "it": "spuntare", "fr": "Cochez"}

    def test_der_playgo_hinweis_ohne_aufforderung_in_allen_sprachen(self) -> None:
        for sprache in self.SPRACHEN:
            with self.subTest(sprache=sprache):
                text = STRINGS["einbau_pruefung.playgo_noetig"][sprache]
                self.assertIn("{datei}", text)
                self.assertNotIn(self.AUFFORDERUNG[sprache], text)

    def test_die_hinweise_tragen_die_marke_der_warnfarbe_in_allen_sprachen(self) -> None:
        """Das Status-Log faerbt jede Zeile, die mit der Warnmarke beginnt - die beiden Hinweise muessen sie tragen."""
        for schluessel, feld in (("einbau_pruefung.playgo_noetig", "{datei}"), ("einbau_pruefung.dlc_gefunden", "{merkmal}")):
            for sprache in self.SPRACHEN:
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertTrue(text.startswith(GUI._LOG_HINWEIS_MARKE + " "), text)
                    self.assertIn(feld, text)
                    self.assertTrue(text.endswith("\n"), text)

    def test_der_playgo_hinweis_ist_wortgleich_der_meldung_auf_seite_7(self) -> None:
        """Nutzerwunsch 18.11.2026: "so wie sie aussieht" - derselbe Text wie das fruehere Etikett unter der Quelle (``pkg.playgo_hinweis``)."""
        for sprache in self.SPRACHEN:
            with self.subTest(sprache=sprache):
                self.assertEqual(STRINGS["pkg.playgo_hinweis"][sprache] + "\n", STRINGS["einbau_pruefung.playgo_noetig"][sprache])


if __name__ == "__main__":
    unittest.main()
