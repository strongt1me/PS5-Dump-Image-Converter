# -*- coding: utf-8 -*-
"""Die Plattformschicht - was das Programm je nach System anders macht.

Entstanden am 31.08.2026 aus ``test_macos_fassung.py``. Diese Datei
enthaelt die Haelfte davon, die **geteilten Code** prueft und nicht die
macOS-Baudateien: die Plattformweiche, die Schriftwahl, die
Systembefehle, die Schriftskalierung, die Erkennung des
Translokationsordners und die Knopfweiche.

**Warum sie getrennt steht.** Die macOS-Baudateien - ``Build_macOS.sh``,
``Install_macOS.sh``, ``PS5ImageConverter_Pro_macos.spec``,
``extract_icon_icns.py`` und ``app_icon.icns`` - sind am 31.08.2026 aus
diesem Repository entfernt worden. Es traegt die WPF-Fassung, und die
gibt es nur unter Windows; gebaut wird fuer macOS im Tk-Repository, wo
alle fuenf Dateien unveraendert liegen.

Die Pruefungen hier waeren dabei fast mitgegangen, obwohl sie mit den
Baudateien nichts zu tun haben: Sie messen Code, der weiter hier liegt
und auf jedem System laeuft. Ihn ungeprueft zu lassen, weil in
derselben Datei auch etwas anderes stand, waere ein Verlust ohne
Gegenwert gewesen.

**Warum sie macOS trotzdem erwaehnen.** Der Monolith enthaelt weiter
seine macOS-Zweige - er ist dieselbe Datei wie im Tk-Repository, und
sie dort auseinanderlaufen zu lassen waere der schlimmere Schnitt.
Geprueft wird also, was das Programm auf einem Mac taete; gebaut wird
es hier nicht mehr.
"""
from __future__ import annotations

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

PLATTFORM_DATEI = PROJEKT / "ps5_validator" / "utils" / "plattform.py"



def _plattform_als(system: str):
    """Laedt die Plattformschicht frisch, als liefe sie auf ``system``.

    Bewusst ueber ``spec_from_file_location`` statt ``importlib.reload``: Ein
    reload traegt das umgebogene Modul in ``sys.modules`` ein, und jeder
    spaetere Test - auch in einer anderen Datei desselben Laufs - saehe dann
    ein Modul, das sich fuer macOS haelt.
    """
    ladeplan = importlib.util.spec_from_file_location(f"plattform_test_{system}", PLATTFORM_DATEI)
    assert ladeplan is not None and ladeplan.loader is not None
    modul = importlib.util.module_from_spec(ladeplan)
    with mock.patch.object(sys, "platform", system):
        ladeplan.loader.exec_module(modul)
    return modul


class PlattformschichtTests(unittest.TestCase):
    """Die macOS-Zweige der Betriebssystem-Abstraktion."""

    @classmethod
    def setUpClass(cls):
        cls.mac = _plattform_als("darwin")

    def test_erkennung(self):
        self.assertTrue(self.mac.IST_MACOS)
        self.assertFalse(self.mac.IST_WINDOWS)
        self.assertFalse(self.mac.IST_LINUX)
        self.assertTrue(self.mac.IST_POSIX)
        self.assertEqual(self.mac.systemname(), "macOS")

    def test_prozessflags_leer(self):
        # creationflags/startupinfo kennt nur die Windows-Implementierung von
        # subprocess; ein von null verschiedener Wert loest dort einen
        # ValueError aus.
        self.assertEqual(self.mac.prozess_flags(), {})

    def test_konfigurationsordner_folgt_apple(self):
        # Ohne die Umlenkung messen. Seit dem 28.08.2026 gilt
        # PS5CONV_KONFIGORDNER vor der plattformueblichen Ableitung, damit
        # Pruefstaende nicht in den Bestand des Anwenders schreiben - und
        # der geteilte Testlauf setzt sie. Hier geht es um die Ableitung
        # selbst, also muss sie aus der Umgebung heraus.
        gemerkt = os.environ.pop("PS5CONV_KONFIGORDNER", None)
        try:
            ordner = self.mac.konfigurationsordner()
        finally:
            if gemerkt is not None:
                os.environ["PS5CONV_KONFIGORDNER"] = gemerkt
        self.assertIn(os.path.join("Library", "Application Support"), ordner)
        self.assertTrue(ordner.endswith("PS5ImageConverterPro"))

    def test_die_umlenkung_gilt_vor_der_plattform(self):
        """Sonst schriebe ein Pruefstand doch wieder in den Bestand."""
        gemerkt = os.environ.get("PS5CONV_KONFIGORDNER")
        os.environ["PS5CONV_KONFIGORDNER"] = os.path.join("Z:", "pruefung")
        try:
            self.assertEqual(self.mac.konfigurationsordner(),
                             os.path.join("Z:", "pruefung"))
        finally:
            if gemerkt is None:
                os.environ.pop("PS5CONV_KONFIGORDNER", None)
            else:
                os.environ["PS5CONV_KONFIGORDNER"] = gemerkt

    def test_windows_hinweis_nennt_das_system(self):
        """Geprueft am Dokan-Treiber - er ist wirklich Windows-gebunden.

        UFS2Tool stand hier bis v1.8.71 mit, war aber nie eine Grenze des
        Werkzeugs: Es laeuft auf allen drei Systemen, nur lag bei uns bloss
        der Windows-Bau bei. Einzig das Einhaengen als Laufwerk braucht Dokan.
        """
        text = self.mac.nur_windows_hinweis("Dokan")
        self.assertIn("Dokan", text)
        self.assertIn("macOS", text)
        # Der Hinweis soll den Zweck nennen, nicht nur den Namen des Werkzeugs.
        self.assertIn("Laufwerk", text)

    def test_ufs2tool_ist_keine_windows_grenze_mehr(self):
        self.assertNotIn("UFS2Tool", self.mac.NUR_WINDOWS_WERKZEUGE)


class SchriftwahlTests(unittest.TestCase):
    """Die Schriftwahl sieht in den Schriftordnern des Systems nach."""

    @classmethod
    def setUpClass(cls):
        cls.mac = _plattform_als("darwin")

    def test_erster_vorhandener_gewinnt(self):
        with tempfile.TemporaryDirectory() as ordner:
            # Nur Helvetica Neue liegt vor - Segoe UI steht davor, fehlt aber.
            Path(ordner, "HelveticaNeue.ttc").write_bytes(b"")
            with mock.patch.object(self.mac, "_MACOS_SCHRIFTORDNER", (ordner,)):
                gewaehlt = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
        self.assertEqual(gewaehlt, "Helvetica Neue")

    def test_segoe_ui_hat_vorrang(self):
        # Wer Microsoft Office installiert hat, soll exakt das Schriftbild
        # bekommen, fuer das die Abstaende im Fensteraufbau ausgelegt sind.
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, "HelveticaNeue.ttc").write_bytes(b"")
            Path(ordner, "segoeui.ttf").write_bytes(b"")
            with mock.patch.object(self.mac, "_MACOS_SCHRIFTORDNER", (ordner,)):
                gewaehlt = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
        self.assertEqual(gewaehlt, "Segoe UI")

    def test_ersatzname_wenn_nichts_gefunden(self):
        with tempfile.TemporaryDirectory() as ordner:
            with mock.patch.object(self.mac, "_MACOS_SCHRIFTORDNER", (ordner,)):
                flaeche = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
                mono = self.mac._macos_familie(self.mac._MACOS_MONO_KANDIDATEN, "Courier")
        self.assertEqual(flaeche, "Helvetica")
        self.assertEqual(mono, "Courier")

    def test_unlesbarer_ordner_bricht_nicht_ab(self):
        # Ein Schriftordner auf einem abgemeldeten Netzlaufwerk darf den Start
        # nicht verhindern - die Schriftwahl laeuft schon beim Import.
        with mock.patch.object(self.mac.os.path, "isfile", side_effect=OSError("weg")):
            gewaehlt = self.mac._macos_familie(self.mac._MACOS_UI_KANDIDATEN, "Helvetica")
        self.assertEqual(gewaehlt, "Helvetica")

    def test_kein_tkinter_beim_import(self):
        # Die Schriftnamen stehen in Vorgabewerten von Funktionssignaturen und
        # werden deshalb schon beim Import gebraucht - da gibt es noch kein
        # Tk-Fenster, ueber das sich Familien abfragen liessen.
        quelle = PLATTFORM_DATEI.read_text(encoding="utf-8")
        self.assertNotIn("import tkinter", quelle)


class SystembefehleTests(unittest.TestCase):
    """Oeffnen, Anzeigen und Herunterfahren nehmen die Apple-Befehle."""

    @classmethod
    def setUpClass(cls):
        cls.mac = _plattform_als("darwin")

    def test_datei_oeffnen_nutzt_open(self):
        with mock.patch.object(self.mac.shutil, "which", return_value="/usr/bin/open"), \
             mock.patch.object(self.mac.subprocess, "Popen") as popen:
            self.assertTrue(self.mac.datei_oeffnen("/tmp/handbuch.html"))
        self.assertEqual(popen.call_args[0][0], ["open", "/tmp/handbuch.html"])

    def test_im_dateimanager_zeigen_markiert_die_datei(self):
        with mock.patch.object(self.mac.subprocess, "Popen") as popen:
            self.assertTrue(self.mac.im_dateimanager_zeigen(str(PROJEKT / "README.md")))
        befehl = popen.call_args[0][0]
        self.assertEqual(befehl[:2], ["open", "-R"])

    def test_herunterfahren_probiert_beide_wege(self):
        # Der erste Weg braucht die Erlaubnis, andere Programme zu steuern.
        # Wird sie verweigert, muss der zweite drankommen.
        aufrufe = []

        class Ergebnis:
            def __init__(self, code):
                self.returncode = code
                self.stdout = ""
                self.stderr = "nicht erlaubt"

        def laeuft(befehl, **_kwargs):
            aufrufe.append(befehl[0])
            return Ergebnis(1 if befehl[0] == "osascript" else 0)

        with mock.patch.object(self.mac.shutil, "which", side_effect=lambda name: f"/usr/bin/{name}"), \
             mock.patch.object(self.mac.subprocess, "run", side_effect=laeuft):
            erfolg, meldung = self.mac.herunterfahren()

        self.assertTrue(erfolg)
        self.assertEqual(aufrufe, ["osascript", "shutdown"])
        self.assertIn("shutdown", meldung)


class SchriftskalierungTests(unittest.TestCase):
    """Punktgroessen bedeuten auf Aqua etwas anderes als auf Windows.

    Gemeldet am 19.08.2026 an einem Mac mini: "Die Schrift ist teilweise
    verdammt klein und extrem schwer zu lesen."
    """

    def _gui(self, *, macos: bool, einstellung=None, scaling=1.0):
        import PS5ImageConverter_Pro_FINAL_revised as APP

        gerufen = []

        class _Tk:
            def call(self, *args):
                if args[:2] == ("tk", "scaling") and len(args) == 2:
                    return scaling
                gerufen.append(args)
                return ""

        class _Wurzel:
            tk = _Tk()

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.root = _Wurzel()
        gui._load_setting = lambda name, vorgabe=None: (
            vorgabe if einstellung is None else einstellung)
        return APP, gui, gerufen

    def test_auf_windows_passiert_nichts(self):
        from unittest import mock

        APP, gui, gerufen = self._gui(macos=False)
        with mock.patch.object(APP, "IST_MACOS", False):
            gui._macos_schrift_skalieren()
        self.assertEqual(gerufen, [], "Windows und Linux bleiben unberuehrt")

    def test_auf_macos_wird_hochgesetzt(self):
        from unittest import mock

        APP, gui, gerufen = self._gui(macos=True, scaling=1.0)
        with mock.patch.object(APP, "IST_MACOS", True):
            gui._macos_schrift_skalieren()
        self.assertEqual(len(gerufen), 1, gerufen)
        self.assertEqual(gerufen[0][:2], ("tk", "scaling"))
        self.assertAlmostEqual(gerufen[0][2], APP.MACOS_SCHRIFT_SKALIERUNG, places=6)

    def test_eigener_wert_aus_den_einstellungen(self):
        from unittest import mock

        APP, gui, gerufen = self._gui(macos=True, einstellung="1.6", scaling=1.0)
        with mock.patch.object(APP, "IST_MACOS", True):
            gui._macos_schrift_skalieren()
        self.assertAlmostEqual(gerufen[0][2], 1.6, places=6)

    def test_unsinniger_wert_wird_abgelehnt(self):
        from unittest import mock

        for wert in ("0", "12", "-3", "kaese"):
            APP, gui, gerufen = self._gui(macos=True, einstellung=wert)
            with mock.patch.object(APP, "IST_MACOS", True):
                gui._macos_schrift_skalieren()
            if wert == "kaese":
                # Unlesbar -> Vorgabe, nicht abgeschaltet.
                self.assertEqual(len(gerufen), 1, wert)
            else:
                self.assertEqual(gerufen, [], "Wert %r haette abgelehnt werden muessen" % wert)

    def test_steht_vor_dem_aufbau_der_oberflaeche(self):
        # Tk rechnet Punktgroessen beim Anlegen einer Schrift in Pixel um.
        # Wird die Skalierung erst hinterher gesetzt, bleiben alle bereits
        # erzeugten Schriften klein - der Aufruf muss vor _create_widgets
        # stehen.
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        anfang = quelle.index("    def __init__(self, root: tk.Tk) -> None:")
        block = quelle[anfang:anfang + 40000]
        self.assertLess(block.index("self._macos_schrift_skalieren()"),
                        block.index("self._create_widgets()"),
                        "Die Skalierung wirkt nicht mehr auf die Schriften.")


class TranslokationTests(unittest.TestCase):
    """macOS startet quarantaenebehaftete Programme aus einem Schattenordner.

    Im Protokoll vom 19.08.2026 stand der mkpfs-Pfad unter
    ".../T/AppTranslocation/7997DEE9-.../d/..." - niemand konnte die
    Ursache benennen. Einstellungen und Protokolle gehen dort beim
    Beenden verloren.
    """

    SCHATTEN = ("/private/var/folders/2k/T/AppTranslocation/7997DEE9/d/"
                "PS5 Dump & Image Converter.app/Contents/Frameworks")
    ORDENTLICH = ("/Applications/PS5 Dump & Image Converter.app/"
                  "Contents/Frameworks")

    def setUp(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        self.APP = APP

    def _pruefen(self, macos, pfad):
        from unittest import mock

        with mock.patch.object(self.APP, "IST_MACOS", macos):
            with mock.patch.object(self.APP.sys, "_MEIPASS", pfad,
                                   create=True):
                return self.APP.PS5ConverterGUI._macos_translokation()

    def test_ausserhalb_von_macos_immer_falsch(self):
        self.assertFalse(self._pruefen(False, self.SCHATTEN))

    def test_schattenordner_wird_erkannt(self):
        self.assertTrue(self._pruefen(True, self.SCHATTEN))

    def test_normaler_ort_wird_nicht_gemeldet(self):
        self.assertFalse(self._pruefen(True, self.ORDENTLICH))

    # Hier stand bis zum 31.08.2026 test_installer_liegt_im_abbild. Es
    # las Build_macOS.sh und ist mit der Datei ins Tk-Repository
    # gegangen - dort gilt es weiter. Sein Grund, damit er nicht
    # verlorengeht: Bis v1.8.58 wanderte allein das Buendel ins .dmg,
    # und der Installer, der die Quarantaene abraeumt, kam nie beim
    # Anwender an.

    def test_hinweis_ist_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS

        for schluessel in ("macos.translocation_title",
                           "macos.translocation_hint"):
            self.assertIn(schluessel, STRINGS)
            for sprache in ("de", "en"):
                self.assertTrue(STRINGS[schluessel].get(sprache), schluessel)


class AquaKnopfTests(unittest.TestCase):
    """Auf Aqua ignoriert ein ``tk.Button`` seine Hintergrundfarbe.

    Uebrig blieb die helle Systemflaeche, auf der die hellen Schriftfarben
    dieses Programms stehen. Im Mitschnitt vom 20.08.2026 war der Fussknopf
    "Was man sonst ev. noch braucht" (fg_primary auf Weiss) nicht mehr zu
    entziffern, und die Titelleiste zeigte eine Reihe heller Pillen.
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")

    def test_titelleistenknoepfe_gehen_ueber_die_weiche(self):
        """Jeder Knopf der Titelleiste muss ueber flach_knopf entstehen.

        Hier stand bis zum 22.08.2026 die feste Zahl 13. Die bricht bei
        jedem neuen Knopf, ohne dass etwas kaputt waere - gemeint war nie
        die Anzahl, sondern dass **keiner** an der Weiche vorbeigeht.
        Genau das wird jetzt geprueft, unabhaengig davon, wie viele es
        sind.
        """
        import re

        anfang = self.quelle.index("self._titlebar_right = tk.Frame(")
        ende = self.quelle.index("        # 8. Bindings", anfang)
        block = self.quelle[anfang:ende]

        zuweisungen = re.findall(r"self\.(_btn_\w+)\s*=\s*(\w+)\(", block)
        self.assertTrue(zuweisungen, "In der Titelleiste entsteht kein Knopf.")
        falsch = [name for name, weiche in zuweisungen if weiche != "flach_knopf"]
        self.assertEqual(falsch, [],
                         "Diese Knoepfe gehen an flach_knopf vorbei: %s" % falsch)
        self.assertNotIn(" = tk.Button(", block,
                         "In der Titelleiste steht wieder ein Systemknopf.")

    def test_fussknoepfe_gehen_ueber_die_weiche(self):
        for name in ("self.info_toggle_btn = ", "self.resources_btn = "):
            stelle = self.quelle.index(name)
            self.assertTrue(
                self.quelle[stelle:stelle + len(name) + 12].endswith("flach_knopf("),
                f"{name.strip()} entsteht nicht ueber flach_knopf.")

    def test_weiche_liefert_je_system_das_richtige(self):
        import tkinter as tk

        import PS5ImageConverter_Pro_FINAL_revised as APP

        try:
            wurzel = tk._default_root or tk.Tk()
        except tk.TclError:
            self.skipTest("keine Anzeige verfuegbar")
        with mock.patch.object(APP, "IST_MACOS", True):
            self.assertIsInstance(APP.flach_knopf(wurzel, text="x"), APP.FlachButton)
        with mock.patch.object(APP, "IST_MACOS", False):
            self.assertIsInstance(APP.flach_knopf(wurzel, text="x"), tk.Button)

    def test_flachbutton_traegt_seine_farbe_und_ruft_auf(self):
        import tkinter as tk

        import PS5ImageConverter_Pro_FINAL_revised as APP

        try:
            wurzel = tk._default_root or tk.Tk()
        except tk.TclError:
            self.skipTest("keine Anzeige verfuegbar")
        gerufen = []
        knopf = APP.FlachButton(wurzel, text="Probe", bg="#123456", fg="#abcdef",
                                command=lambda: gerufen.append(1))
        # Der Punkt der ganzen Uebung: die Farbe bleibt, wie sie gesetzt wurde.
        self.assertEqual(str(knopf.cget("bg")), "#123456")
        self.assertEqual(str(knopf.cget("fg")), "#abcdef")
        knopf.invoke()
        self.assertEqual(gerufen, [1])
        # Abgeschaltet loest er nicht aus - wie ein tk.Button auch nicht.
        knopf.config(state=tk.DISABLED)
        knopf.invoke()
        self.assertEqual(gerufen, [1])
        knopf.config(state=tk.NORMAL)
        knopf.invoke()
        self.assertEqual(gerufen, [1, 1])
        # config(command=...) muss den Aufruf austauschen, nicht abstuerzen.
        anders = []
        knopf.config(command=lambda: anders.append(1), text="Neu")
        knopf.invoke()
        self.assertEqual((anders, str(knopf.cget("text"))), ([1], "Neu"))
        knopf.destroy()

    def test_pt_laesst_windows_und_linux_unberuehrt(self):
        """Ausserhalb von macOS muss die Zahl unveraendert durchgehen."""
        import PS5ImageConverter_Pro_FINAL_revised as APP

        if APP.IST_MACOS:
            self.skipTest("laeuft auf macOS")
        self.assertEqual(APP._MACOS_SCHRIFTFAKTOR, 1.0)
        for punkte in (7, 8, 9, 10, 12, 16, 24):
            self.assertEqual(APP.pt(punkte), punkte)

    def test_alle_schriftangaben_gehen_ueber_pt(self):
        """Sonst faellt die naechste neue Beschriftung wieder aus dem Raster.

        Die Umstellung war mechanisch (288 Stellen). Genau deshalb braucht sie
        eine Sperre: Eine einzelne nackte Punktzahl faellt beim Lesen nicht auf,
        auf dem Mac aber sofort - sie stuende dann bei 60 % der Groesse ihrer
        Nachbarn.
        """
        nackt = re.findall(r"\((?:UI_SCHRIFT|MONO_SCHRIFT), \d", self.quelle)
        self.assertEqual(nackt, [],
                         f"{len(nackt)} Schriftangabe(n) ohne pt() im Quelltext.")
        # Gegenprobe, dass das Muster ueberhaupt greift.
        self.assertGreater(
            len(re.findall(r"\((?:UI_SCHRIFT|MONO_SCHRIFT), pt\(", self.quelle)), 250)

    def test_faktor_trifft_die_windows_pixelhoehen(self):
        """Ziel der Umstellung: dasselbe Schriftbild wie unter Windows.

        Vergleichsmass ist die Anzeigeskalierung, mit der die Fassung dort
        laeuft (125 %, ``tk scaling`` 1,6683). Rundung darf einen Bildpunkt
        abweichen - mehr nicht.
        """
        import PS5ImageConverter_Pro_FINAL_revised as APP

        faktor = APP.MACOS_SCHRIFT_SKALIERUNG
        for punkte in (7, 8, 9, 10, 12, 14, 16, 18, 24):
            auf_mac = max(1, round(punkte * faktor))
            auf_windows = round(punkte * 1.6683)
            self.assertLessEqual(
                abs(auf_mac - auf_windows), 1,
                f"{punkte} pt: Mac {auf_mac} px gegen Windows {auf_windows} px")

    def test_faktor_kommt_aus_der_einstellungsdatei(self):
        """``macos_font_scaling`` muss ohne neuen Bau wirken - und zwar auf pt().

        Seit dem 17. Schnitt liest der Faktor ueber
        ``einstellungen.lesen`` statt ueber einen selbstgebauten Pfad -
        deshalb wird hier der Konfigurationsordner des Moduls ersetzt.
        Geprueft wird unveraendert das Verhalten: eine echte Datei wird
        angelegt und ihr Wert muss ankommen.
        """
        import PS5ImageConverter_Pro_FINAL_revised as APP
        from ps5_validator.utils import einstellungen

        with tempfile.TemporaryDirectory() as ordner:
            with open(os.path.join(ordner, "paths.json"), "w", encoding="utf-8") as f:
                f.write('{"macos_font_scaling": 2.0}')
            with mock.patch.object(APP, "IST_MACOS", True),                     mock.patch.object(einstellungen, "konfigurationsordner",
                                      lambda *a, **k: ordner):
                self.assertEqual(APP._macos_schriftfaktor(), 2.0)
            # Unsinnige Werte fallen auf die Vorgabe zurueck.
            with open(os.path.join(ordner, "paths.json"), "w", encoding="utf-8") as f:
                f.write('{"macos_font_scaling": 99}')
            with mock.patch.object(APP, "IST_MACOS", True),                     mock.patch.object(einstellungen, "konfigurationsordner",
                                      lambda *a, **k: ordner):
                self.assertEqual(APP._macos_schriftfaktor(),
                                 APP.MACOS_SCHRIFT_SKALIERUNG)

    def test_tk_scaling_bleibt_wegen_der_seitenleiste(self):
        """Der Aufruf wirkt nicht auf Schriften - aber auf Tks cm-Vorgaben.

        An denen haengt die Standardbreite eines Canvas (10c) und damit ueber
        die Aufgabenknoepfe die Breite der Seitenleiste. Faellt der Aufruf weg,
        schrumpft sie auf dem Mac von 487 auf 283 Pixel.
        """
        anfang = self.quelle.index("    def _macos_schrift_skalieren(self)")
        ende = self.quelle.index("\n    @staticmethod", anfang)
        block = self.quelle[anfang:ende]
        self.assertIn('self.root.tk.call("tk", "scaling", vorher * faktor)', block)
