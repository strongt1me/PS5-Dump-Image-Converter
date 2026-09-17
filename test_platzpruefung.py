# -*- coding: utf-8 -*-
"""Die Platzprüfung vor dem Start – und die BAUFORM-Zeile.

Zwei Meldungen des Anwenders vom 12.09.2026, beide über dieselbe Sorte
Mangel: Das Fenster zeigt etwas, das nichts bewirkt.

**Zu wenig Platz.** Bis v1.9.14 rechnete ``_launch_task`` mit
Quellgröße × 1,1, zeigte ein ``showwarning`` – und ließ die Aufgabe
trotzdem los. Wer zu wenig Platz hatte, sah also, dass es eng wird, konnte
aber nichts tun und stand Stunden später vor einem abgebrochenen Lauf.
Verlangt war: eine Meldung **und** die Möglichkeit, Temp- oder Zielordner
daraufhin zu wechseln.

**Die BAUFORM.** Sie stand über allen acht Aufgaben und jedem Zielformat,
wirkt aber ausschließlich bei ``.ffpfsc``. „Ansonsten ist es eher
irreführend."

**Aufgabe 7 und ein alter Zielordner.** Dazugekommen beim Nachfahren der
Prüfmatrix: Ein ausgeblendetes Zielfeld wurde beim Start trotzdem geprüft.

Gemessen wird am laufenden Fenster, nicht am Quelltext: Ob ein Widget
sichtbar ist, sagt nur ``winfo_ismapped()``.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

GB = 1024 ** 3


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class PlatzbedarfTests(unittest.TestCase):
    """Die Schätzung muss über dem liegen, was wirklich gebraucht wird."""

    #: Was die Prüfmatrix am 10.–12.09.2026 wirklich erzeugt hat, aus
    #: einem 51,08-GB-Dump von Prince of Persia: The Lost Crown.
    #: Die Schätzung darf nie darunter liegen – sonst läuft jemand in
    #: einen Abbruch, den die Prüfung hätte verhindern sollen.
    GEMESSEN_GB = {
        "ffpfsc": 24.22,
        "ffpfs": 51.63,
        "exfat": 51.64,
        "ffpkg": 61.11,
        "folder": 51.08,
    }
    QUELLE_GB = 51.08

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def setUp(self):
        # Eine echte Quelle, sonst liefert die Größenermittlung 0 und die
        # Prüfung enthält sich – der Test würde nichts messen.
        self.quelle = os.path.dirname(HAUPTDATEI)
        # Ueber _quellgroesse_merken, nicht _last_source_size_bytes: Seit
        # 16.09.2026 gilt eine gemerkte Groesse nur fuer die Quelle, fuer die
        # sie gemessen wurde. Die nackte Zahl traf zuvor auch jede andere
        # Quelle - genau der behobene Fehler.
        self.app._quellgroesse_merken(self.quelle, int(self.QUELLE_GB * GB))
        for name in ("ampr_integrate_var", "backport_integrate_var"):
            var = getattr(self.app, name, None)
            if var is not None:
                var.set(False)

    def test_die_schaetzung_deckt_jedes_gemessene_ergebnis(self):
        zu_knapp = []
        for fmt, gemessen in sorted(self.GEMESSEN_GB.items()):
            _temp, ziel = self.app._platzbedarf_schaetzen(
                "pack_folder", self.quelle, fmt)
            if ziel < gemessen * GB:
                zu_knapp.append("%s: geschätzt %.2f GB, gebraucht %.2f GB"
                                % (fmt, ziel / GB, gemessen))
        self.assertEqual([], zu_knapp,
                         "Diese Schätzungen liegen unter dem gemessenen "
                         "Bedarf:\n  " + "\n  ".join(zu_knapp))

    def test_ein_komprimiertes_ziel_braucht_weniger_als_ein_rohes(self):
        """Sonst wäre der Faktor nur Zierde."""
        _t, ffpfsc = self.app._platzbedarf_schaetzen(
            "pack_folder", self.quelle, "ffpfsc")
        _t, ffpkg = self.app._platzbedarf_schaetzen(
            "pack_folder", self.quelle, "ffpkg")
        self.assertLess(ffpfsc, ffpkg)

    def test_integration_hebt_den_temp_bedarf(self):
        """AMPR und BACKPORT legen eine vollständige Arbeitskopie an."""
        ohne, _z = self.app._platzbedarf_schaetzen(
            "pack_folder", self.quelle, "ffpfsc")
        self.app.ampr_integrate_var.set(True)
        try:
            mit, _z2 = self.app._platzbedarf_schaetzen(
                "pack_folder", self.quelle, "ffpfsc")
        finally:
            self.app.ampr_integrate_var.set(False)
        self.assertGreater(mit, ohne * 2,
                           "Eine Arbeitskopie ist so groß wie der Dump - das "
                           "muss sich im Temp-Bedarf zeigen.")

    def test_neu_packen_rechnet_den_dump_ordner_im_ziel_mit(self):
        """Entpacken, einbauen, neu packen (13.09.2026): Dump-Ordner und
        .ffpfsc liegen zugleich im Zielordner, bis gepackt ist."""
        _t, einhuellen = self.app._platzbedarf_schaetzen(
            "pack_file", self.quelle, "ffpfsc")
        self.app._umhuellt_neu_packen = True
        try:
            _t2, neu_packen = self.app._platzbedarf_schaetzen(
                "pack_file", self.quelle, "ffpfsc")
        finally:
            self.app._umhuellt_neu_packen = False
        gemessen = (self.GEMESSEN_GB["folder"] + self.GEMESSEN_GB["ffpfsc"]) * GB
        self.assertGreater(neu_packen, einhuellen)
        self.assertGreaterEqual(neu_packen, gemessen,
                                "Dump-Ordner und .ffpfsc zusammen passen nicht "
                                "in die Schaetzung.")

    def test_ohne_bekannte_quellgroesse_wird_nicht_geraten(self):
        """Lieber keine Aussage als eine erfundene."""
        self.app._quellgroesse_merken(os.path.dirname(HAUPTDATEI), 0)
        temp, ziel = self.app._platzbedarf_schaetzen(
            "pack_folder", os.path.dirname(HAUPTDATEI), "ffpfsc")
        self.assertEqual((0, 0), (temp, ziel))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class PlatzKlaerenTests(unittest.TestCase):
    """Was passiert, wenn der Platz nicht reicht."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def setUp(self):
        self.app._cli_mode = False
        self.quelle = os.path.dirname(HAUPTDATEI)
        # Unerfuellbar gross - und an die Quelle gebunden, siehe PlatzbedarfTests.
        self.app._quellgroesse_merken(self.quelle, int(900 * GB))
        self.gezeigt = []

    def _dialog_abfangen(self, antwort):
        def _statt(knapp):
            self.gezeigt.append(list(knapp))
            return antwort
        self.app._platz_dialog = _statt

    def test_bei_zu_wenig_platz_wird_gefragt(self):
        self._dialog_abfangen("abbrechen")
        self.app.dest_path.set(os.path.dirname(HAUPTDATEI))
        darf = self.app._platz_klaeren("pack_folder", self.quelle, "ffpfsc")
        self.assertFalse(darf, "Nach 'abbrechen' darf nicht gestartet werden")
        self.assertTrue(self.gezeigt, "Es wurde gar nicht gefragt")

    def test_trotzdem_startet_und_steht_im_protokoll(self):
        """Wer es sehenden Auges tut, darf – aber es wird vermerkt.

        Sonst steht im Fehlerbild später eine Ursache, die niemand mehr
        zuordnen kann.
        """
        self._dialog_abfangen("trotzdem")
        self.app.dest_path.set(os.path.dirname(HAUPTDATEI))
        self.app.console_view.delete("1.0", "end")
        darf = self.app._platz_klaeren("pack_folder", self.quelle, "ffpfsc")
        self.assertTrue(darf)
        # ``_append_to_log`` schreibt über ``root.after`` - ohne einen
        # Durchlauf der Ereignisschleife steht im Feld noch nichts.
        _WURZEL.update()
        self.assertIn("Platz", self.app.console_view.get("1.0", "end"))

    def test_aufgaben_ohne_ergebnis_fragen_nie(self):
        """Aufgabe 7 und 8 schreiben nichts Großes."""
        self._dialog_abfangen("abbrechen")
        for modus in ("ampr_manager", "dump_validator", "inspect"):
            with self.subTest(modus=modus):
                self.assertTrue(
                    self.app._platz_klaeren(modus, self.quelle, ""))
        self.assertEqual([], self.gezeigt)

    def test_im_cli_geht_nie_ein_fenster_auf(self):
        """Ein eigenes Fenster mit ``wait_window`` ließe den Lauf hängen.

        ``_run_cli`` ersetzt nur ``messagebox.*``, nicht selbst gebaute
        Dialoge. Die Prüfmatrix wäre daran stillschweigend stehen
        geblieben.
        """
        def _darf_nicht(_knapp):
            raise AssertionError("Dialog im CLI-Modus geöffnet")
        self.app._platz_dialog = _darf_nicht
        self.app._cli_mode = True
        self.app.dest_path.set(os.path.dirname(HAUPTDATEI))
        try:
            for yes in (True, False):
                with self.subTest(yes=yes):
                    self.app._cli_platz_trotzdem = yes
                    self.assertEqual(
                        yes,
                        self.app._platz_klaeren("pack_folder", self.quelle,
                                                "ffpfsc"))
        finally:
            self.app._cli_mode = False

    def test_genug_platz_fragt_nicht(self):
        self._dialog_abfangen("abbrechen")
        self.app._quellgroesse_merken(self.quelle, 1024)   # ein Kilobyte
        self.app.dest_path.set(os.path.dirname(HAUPTDATEI))
        self.assertTrue(
            self.app._platz_klaeren("pack_folder", self.quelle, "ffpfsc"))
        self.assertEqual([], self.gezeigt)

    def test_die_pruefung_haengt_wirklich_im_ablauf(self):
        """Eine Prüfung, die nur der Test aufruft, schützt niemanden.

        Am 12.09.2026 blieben neun Tests grün, nachdem der Aufruf aus
        ``_launch_task`` verschwunden war – sie riefen alle direkt auf.
        """
        with open(HAUPTDATEI, encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertIn("if not self._platz_klaeren(mode, src, target_type):",
                      quelle)
        # Und die alte, wirkungslose Warnung ist weg.
        self.assertNotIn('self._t("dialog.msg.low_disk_space"', quelle)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class EchterDialogTests(unittest.TestCase):
    """Der Platzdialog wird wirklich gebaut – nicht nur ersetzt.

    Anwendermeldung vom 14.09.2026 zu v1.9.19: Jeder Start, bei dem der Platz
    knapp schien, brach ab mit

        TypeError: PS5ConverterGUI._build_modern_toplevel() got an unexpected
        keyword argument 'parent'

    Getroffen hat es vor allem .ffpkg -> .ffpfsc mit AMPR EMU: Das Neu-Packen
    rechnet den vorübergehenden Dump-Ordner im Ziel mit, erst dadurch wurde
    es knapp genug für den Dialog. Die Tests darüber ersetzen
    ``_platz_dialog`` durch eine Attrappe und haben das Fenster nie gebaut.
    Dasselbe ``parent=`` stand in zwei Fenstern der Bibliothek.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    @staticmethod
    def _nachmessungen_ablaufen_lassen():
        # _build_modern_toplevel plant zwei Nachmessungen (80 und 400 ms).
        # Erst ablaufen lassen, dann schliessen - sonst treffen sie in einem
        # spaeteren Test auf ein zerstoertes Fenster.
        time.sleep(0.45)
        _WURZEL.update()

    def test_der_dialog_laesst_sich_bauen_und_schliessen(self):
        knapp = [("ziel", os.path.dirname(HAUPTDATEI), 300 * GB, 190 * GB)]
        gebaut = []

        def _statt_warten(fenster):
            gebaut.append(fenster.title())
            self._nachmessungen_ablaufen_lassen()
            fenster.destroy()      # wie das Schliessen ueber die Titelleiste

        # Ueber die Klasse aufgerufen, nicht ueber die Instanz: Andere Tests
        # setzen auf ihrer Instanz eine Attrappe an diese Stelle.
        with mock.patch.object(tk.Toplevel, "grab_set"), \
                mock.patch.object(self.app.root, "wait_window",
                                  side_effect=_statt_warten):
            antwort = self.haupt.PS5ConverterGUI._platz_dialog(self.app, knapp)
        self.assertEqual("abbrechen", antwort)
        self.assertEqual([self.app._t("platz.titel")], gebaut)

    def test_parent_bestimmt_den_besitzer(self):
        """Ohne Angabe das Hauptfenster, sonst das genannte Fenster."""
        eltern = self.app._build_modern_toplevel("Eltern", 320, 200)
        kind = self.app._build_modern_toplevel("Kind", 240, 160, parent=eltern)
        try:
            self._nachmessungen_ablaufen_lassen()
            self.assertEqual(str(self.app.root), str(eltern.transient()))
            self.assertEqual(str(eltern), str(kind.transient()))
        finally:
            kind.destroy()
            eltern.destroy()


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class BauformSichtbarkeitTests(unittest.TestCase):
    """Die BAUFORM steht nur da, wo sie etwas bewirkt."""

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def _sichtbar_bei(self, modus, zielformat):
        self.app.current_mode.set(modus)
        self.app.target_format.set(
            self.app._t("format." + zielformat) if zielformat else "")
        self.app._format_hinweis_setzen(modus)
        _WURZEL.update_idletasks()
        return bool(self.app.bauform_combo.winfo_ismapped())

    def test_nur_bei_ffpfsc_sichtbar(self):
        falsch = []
        for _label, modus in self.haupt.PS5ConverterGUI._MODE_OPTIONS:
            ziele = self.haupt.PS5ConverterGUI._MODE_TARGET_OPTIONS.get(
                modus, ()) or ("",)
            for ziel in ziele:
                sichtbar = self._sichtbar_bei(modus, ziel)
                soll = ziel == "ffpfsc"
                if sichtbar != soll:
                    falsch.append("%s/%s: %s statt %s"
                                  % (modus, ziel or "-",
                                     "sichtbar" if sichtbar else "verborgen",
                                     "sichtbar" if soll else "verborgen"))
        self.assertEqual([], falsch,
                         "Die BAUFORM steht an der falschen Stelle:\n  "
                         + "\n  ".join(falsch))

    def test_aufgabe_7_und_8_zeigen_sie_nie(self):
        """Beide haben gar kein Zielformat."""
        for modus in ("ampr_manager", "dump_validator"):
            with self.subTest(modus=modus):
                self.assertFalse(self._sichtbar_bei(modus, ""))

    def test_zurueckschalten_bringt_sie_wieder(self):
        """``grid_remove`` statt ``destroy`` – die Zeile muss wiederkommen."""
        self.assertTrue(self._sichtbar_bei("pack_folder", "ffpfsc"))
        self.assertFalse(self._sichtbar_bei("pack_folder", "exfat"))
        self.assertTrue(self._sichtbar_bei("pack_folder", "ffpfsc"))

    def test_die_umschaltung_haengt_am_formatwechsel(self):
        """Ohne diesen Aufruf ändert sich nichts, bis das Fenster neu baut."""
        with open(HAUPTDATEI, encoding="utf-8") as datei:
            quelle = datei.read()
        self.assertIn("self._bauform_sichtbarkeit_setzen()", quelle)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class Aufgabe7ZielfeldTests(unittest.TestCase):
    """Aufgabe 7 prüft kein Zielfeld, das sie ausblendet und nie liest.

    Aufgefallen am 12.09.2026 in der Prüfmatrix: Alle sechs Läufe der
    Aufgabe 7 brachen mit „Zielverzeichnis existiert nicht" ab, obwohl kein
    ``--dest`` angegeben war – der Pfad stand noch aus einem früheren Lauf
    in den Einstellungen. Im Fenster ist es derselbe Fall, nur schlimmer:
    Bei einem Dump-Ordner ist das Zielfeld dort ausgeblendet, man kann es
    weder sehen noch leeren.

    Gemessen wird am echten ``_launch_task``. Die Platzprüfung ist ersetzt
    und hält den Start an: Wird sie erreicht, hat die Zielprüfung die
    Aufgabe durchgelassen.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dump = os.path.join(tmp.name, "PPSA99999-app")
        os.makedirs(os.path.join(self.dump, "sce_sys"))
        self.datei = os.path.join(tmp.name, "spiel.ffpfsc")
        with open(self.datei, "wb"):
            pass
        # Ein Ziel, das es nicht (mehr) gibt – wie ein abgestecktes Laufwerk.
        self.altes_ziel = os.path.join(tmp.name, "abgestecktes_laufwerk")
        app = self.app
        vorher = (app.current_mode.get(), app.source_path.get(),
                  app.dest_path.get())

        def _zurueck():
            app.current_mode.set(vorher[0])
            app.source_path.set(vorher[1])
            app.dest_path.set(vorher[2])
        # addCleanup läuft rückwärts: erst zurückstellen, dann aufräumen.
        self.addCleanup(_zurueck)

    def _starten(self, quelle):
        """``_launch_task`` bis zur Platzprüfung.

        Gibt zurück, ob die Platzprüfung erreicht wurde, und alle Texte, die
        in einem Meldungsfenster gelandet wären.
        """
        app = self.app
        app.current_mode.set("ampr_manager")
        app.source_path.set(quelle)
        app.dest_path.set(self.altes_ziel)
        erreicht = []

        def _platz(*args, **kwargs):
            erreicht.append(args)
            return False

        with mock.patch.object(self.haupt, "messagebox") as box, \
                mock.patch.object(app, "_platz_klaeren", side_effect=_platz):
            app._launch_task()
        texte = [wert for _name, args, _kw in box.method_calls
                 for wert in args if isinstance(wert, str)]
        return bool(erreicht), texte

    def _zielmeldung(self):
        return self.app._t("dialog.msg.target_dir_not_found",
                           path=self.altes_ziel)

    def test_ausgeblendetes_altes_ziel_haelt_aufgabe_7_nicht_auf(self):
        erreicht, texte = self._starten(self.dump)
        self.assertFalse(
            any(self._zielmeldung() in t for t in texte),
            "Aufgabe 7 mit einem Dump-Ordner wird wieder an einem Zielfeld "
            "abgewiesen, das ausgeblendet ist und nie gelesen wird.")
        self.assertTrue(
            erreicht,
            "Aufgabe 7 mit einem Dump-Ordner kam nicht bis zur "
            "Platzprüfung:\n  " + "\n  ".join(texte))

    def test_bei_einer_datei_wird_ein_angegebenes_ziel_weiter_geprueft(self):
        """.ffpfsc, .exfat und .ffpkg schreiben ins Ziel – dort bleibt die
        Prüfung, sonst landet ein Tippfehler still neben der Quelle."""
        erreicht, texte = self._starten(self.datei)
        self.assertTrue(
            any(self._zielmeldung() in t for t in texte),
            "Bei einer Datei-Quelle fällt ein nicht vorhandenes Ziel nicht "
            "mehr auf. Gemeldet wurde:\n  " + "\n  ".join(texte))
        self.assertFalse(erreicht)

    def test_das_gespeicherte_ziel_bleibt_stehen(self):
        """Nicht prüfen heißt nicht löschen: Der nächste Lauf mit einer
        Datei-Quelle braucht das Feld wieder."""
        self._starten(self.dump)
        self.assertEqual(self.altes_ziel, self.app.dest_path.get())

    def test_fenster_und_start_folgen_derselben_regel(self):
        """Ausgeblendet im Fenster heißt ungeprüft beim Start – und
        umgekehrt. Beide Stellen, die das Feld ein- und ausblenden, werden
        gemessen: der Aufgabenwechsel und der Quellwechsel."""
        app = self.app
        auswahl = (mock.patch.object(app, "_show_ampr_auswahl")
                   if hasattr(app, "_show_ampr_auswahl") else mock.MagicMock())
        with auswahl:
            for quelle in (self.dump, self.datei, self.dump):
                name = os.path.basename(quelle)
                soll = app._aufgabe7_liest_kein_ziel("ampr_manager", quelle)
                with self.subTest(weg="Aufgabenwechsel", quelle=name):
                    app.source_path.set(quelle)
                    app._set_mode_from_sidebar("ampr_manager")
                    _WURZEL.update_idletasks()
                    self.assertEqual(soll, app.dest_entry.winfo_manager() == "")
                with self.subTest(weg="Quellwechsel", quelle=name):
                    app.source_path.set(quelle)
                    app._on_source_path_changed()
                    _WURZEL.update_idletasks()
                    self.assertEqual(soll, app.dest_entry.winfo_manager() == "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
