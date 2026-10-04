# -*- coding: utf-8 -*-
"""Weboberflaechen der Konsole im Programm (Wunsch vom 26.09.2026).

"Wenn eine Weboberflaeche geoeffnet wird (im Programm), soll diese bitte auch
im Programm geoeffnet bzw. angezeigt werden." Unter Windows legt WebView2 die
Seite in einen Rahmen der Ansicht KONSOLE (ps5_validator/utils/webansicht.py);
sonst geht wie bisher der Browser auf.

Geprueft wird hier:

* wann eingebettet wird und wann nicht (Gruende als Textschluessel),
* wo die beiden Microsoft-DLLs gesucht werden (Quelltext und Bau),
* die Steuerung der Seite gegen nachgebaute .NET-Objekte - sie wartet nie,
* eine **echte** Einbettung gegen einen kleinen Webserver auf diesem Rechner
  (nur unter Windows mit pythonnet; die Konsole wird nicht gebraucht),
* die Seite im Programm: Zurueck, Browser als Ausweg, Sprachwechsel.
"""
from __future__ import annotations

import ast
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("webansicht")
from ps5_validator.utils import webansicht as wa            # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

PROJEKT = Path(__file__).resolve().parent

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


# -- Nachbauten der .NET-Seite ----------------------------------------------

class _Task:
    """Wie ein .NET-Task: fertig, gescheitert oder noch unterwegs."""

    def __init__(self, ergebnis=None):
        self.IsCompleted = False
        self.IsFaulted = False
        self.Result = ergebnis
        self.Exception = None

    def fertig(self):
        self.IsCompleted = True
        return self

    def scheitern(self, fehler):
        self.IsCompleted = True
        self.IsFaulted = True
        self.Exception = fehler
        return self


class _Ereignis:
    def __init__(self):
        self.abnehmer = []

    def __iadd__(self, abnehmer):
        self.abnehmer.append(abnehmer)
        return self

    def ausloesen(self, *args):
        for abnehmer in self.abnehmer:
            abnehmer(None, *args)


class _Kern:
    def __init__(self):
        self.NavigationCompleted = _Ereignis()
        self.navigiert = []
        self.neu_geladen = 0
        self.DocumentTitle = "Titel der Seite"

    def Navigate(self, adresse):
        self.navigiert.append(adresse)

    def Reload(self):
        self.neu_geladen += 1


class _Controller:
    def __init__(self):
        self.CoreWebView2 = _Kern()
        self.Bounds = None
        self.IsVisible = None
        self.geschlossen = False

    def Close(self):
        self.geschlossen = True


class _Umgebung:
    def __init__(self, controller_task):
        self.controller_task = controller_task
        self.eltern = []

    def CreateCoreWebView2ControllerAsync(self, hwnd):
        self.eltern.append(hwnd)
        return self.controller_task


def _nachbau():
    """Die .NET-Typen, wie :func:`webansicht._net_laden` sie liefert - nachgebaut."""
    controller = _Controller()
    controller_task = _Task(controller)
    umgebung = _Umgebung(controller_task)
    umgebung_task = _Task(umgebung)
    typen = {
        "Umgebung": mock.Mock(**{"CreateAsync.return_value": umgebung_task}),
        "IntPtr": lambda wert: ("IntPtr", wert),
        "Rechteck": lambda x, y, b, h: (x, y, b, h),
    }
    return typen, umgebung_task, controller_task, umgebung, controller


class VerfuegbarTests(unittest.TestCase):

    def test_nur_unter_windows(self):
        with mock.patch.object(wa.sys, "platform", "linux"):
            self.assertEqual((False, wa.GRUND_PLATTFORM), wa.verfuegbar())

    def test_ohne_pythonnet(self):
        echt = wa.importlib.util.find_spec
        with mock.patch.object(wa.sys, "platform", "win32"), \
                mock.patch.object(wa.importlib.util, "find_spec",
                                  lambda name, *a: None if name == "pythonnet" else echt(name, *a)):
            self.assertEqual((False, wa.GRUND_PYTHONNET), wa.verfuegbar())

    def test_ohne_dlls(self):
        with mock.patch.object(wa.sys, "platform", "win32"), \
                mock.patch.object(wa.importlib.util, "find_spec", return_value=object()), \
                mock.patch.object(wa, "dll_ordner", return_value=""):
            self.assertEqual((False, wa.GRUND_DLL), wa.verfuegbar())

    def test_ohne_laufzeit(self):
        with tempfile.TemporaryDirectory() as ordner:
            Path(ordner, wa.LOADER_DLL).write_bytes(b"x")
            with mock.patch.object(wa.sys, "platform", "win32"), \
                    mock.patch.object(wa.importlib.util, "find_spec", return_value=object()), \
                    mock.patch.object(wa, "dll_ordner", return_value=ordner), \
                    mock.patch.object(wa, "laufzeit_version", return_value=""):
                self.assertEqual((False, wa.GRUND_LAUFZEIT), wa.verfuegbar())

    def test_jeder_grund_ist_zweisprachig(self):
        for grund in (wa.GRUND_PLATTFORM, wa.GRUND_PYTHONNET, wa.GRUND_DLL,
                      wa.GRUND_LAUFZEIT, wa.GRUND_FADEN, wa.GRUND_START):
            for sprache in ("de", "en"):
                with self.subTest(grund=grund, sprache=sprache):
                    self.assertTrue(STRINGS[grund].get(sprache))


class DllOrdnerTests(unittest.TestCase):

    def test_im_bau_liegen_beide_flach_in_webview2(self):
        with tempfile.TemporaryDirectory() as basis:
            ordner = Path(basis, wa.BUENDEL_ORDNER)
            ordner.mkdir()
            (ordner / wa.CORE_DLL).write_bytes(b"x")
            (ordner / wa.LOADER_DLL).write_bytes(b"x")
            with mock.patch.object(wa.sys, "_MEIPASS", basis, create=True):
                self.assertEqual(str(ordner), wa.dll_ordner())
                self.assertEqual(str(ordner / wa.LOADER_DLL), wa.loader_pfad(wa.dll_ordner()))

    def test_im_bau_ohne_dateien_nichts(self):
        with tempfile.TemporaryDirectory() as basis, \
                mock.patch.object(wa.sys, "_MEIPASS", basis, create=True):
            self.assertEqual("", wa.dll_ordner())

    @unittest.skipUnless(wa.importlib.util.find_spec("webview"), "pywebview nicht installiert")
    def test_aus_dem_quelltext_liegt_der_lader_unter_runtimes(self):
        ordner = wa.dll_ordner()
        self.assertTrue(os.path.isfile(os.path.join(ordner, wa.CORE_DLL)))
        self.assertTrue(wa.loader_pfad(ordner).endswith(
            os.path.join("runtimes", "win-x64", "native", wa.LOADER_DLL)))

    def test_ohne_ordner_kein_lader(self):
        self.assertEqual("", wa.loader_pfad(""))


class SeiteTests(unittest.TestCase):
    """Die Steuerung gegen nachgebaute .NET-Objekte - sie wartet nie."""

    def _seite(self):
        typen, umgebung_task, controller_task, umgebung, controller = _nachbau()
        flicken = mock.patch.object(wa, "_net_laden", return_value=typen)
        flicken.start()
        self.addCleanup(flicken.stop)
        seite = wa.Seite(4711, r"C:\daten\WebView2")
        return seite, typen, umgebung_task, controller_task, umgebung, controller

    def test_was_vor_dem_start_bestellt_wird_gilt_danach(self):
        seite, typen, u_task, c_task, umgebung, controller = self._seite()
        seite.groesse_setzen(800, 600)
        seite.navigieren("http://10.0.0.5:8084/")
        seite.starten()
        self.assertEqual("startet", seite.zustand)
        typen["Umgebung"].CreateAsync.assert_called_once_with(None, r"C:\daten\WebView2", None)
        seite.schritt()                     # Umgebung noch unterwegs
        self.assertEqual([], umgebung.eltern)
        u_task.fertig()
        seite.schritt()
        self.assertEqual([("IntPtr", 4711)], umgebung.eltern)
        self.assertEqual([], controller.CoreWebView2.navigiert)
        c_task.fertig()
        seite.schritt()
        self.assertEqual("bereit", seite.zustand)
        self.assertEqual((0, 0, 800, 600), controller.Bounds)
        self.assertTrue(controller.IsVisible)
        self.assertEqual(["http://10.0.0.5:8084/"], controller.CoreWebView2.navigiert)

    def _bereit(self):
        seite, typen, u_task, c_task, umgebung, controller = self._seite()
        seite.starten()
        u_task.fertig()
        seite.schritt()
        c_task.fertig()
        seite.schritt()
        return seite, controller

    def test_navigation_und_titel(self):
        seite, controller = self._bereit()
        seite.navigieren("http://10.0.0.5:8080/")
        self.assertIsNone(seite.navigation)
        controller.CoreWebView2.NavigationCompleted.ausloesen(
            mock.Mock(IsSuccess=True, WebErrorStatus="Unknown"))
        self.assertEqual((True, "Unknown"), seite.navigation)
        self.assertEqual("Titel der Seite", seite.titel)

    def test_groesse_sichtbarkeit_neu_laden_schliessen(self):
        seite, controller = self._bereit()
        seite.groesse_setzen(1024, 700)
        self.assertEqual((0, 0, 1024, 700), controller.Bounds)
        seite.sichtbar_setzen(False)
        self.assertFalse(controller.IsVisible)
        seite.neu_laden()
        self.assertEqual(1, controller.CoreWebView2.neu_geladen)
        seite.schliessen()
        self.assertTrue(controller.geschlossen)
        self.assertEqual("zu", seite.zustand)
        seite.schritt()                     # nach dem Schliessen geschieht nichts mehr
        self.assertEqual("zu", seite.zustand)

    def test_gescheiterte_umgebung(self):
        seite, typen, u_task, c_task, umgebung, controller = self._seite()
        seite.starten()
        u_task.scheitern(RuntimeError("Zeile eins\nZeile zwei"))
        seite.schritt()
        self.assertEqual(("fehler", "Zeile eins"), (seite.zustand, seite.fehler))

    def test_mta_faden_nennt_den_grund(self):
        with mock.patch.object(wa, "_net_laden", side_effect=OSError(wa.GRUND_FADEN)):
            seite = wa.Seite(1, "x")
            seite.starten()
        self.assertEqual(("fehler", wa.GRUND_FADEN), (seite.zustand, seite.fehler))


class _Kleinserver:
    """Ein Webserver auf 127.0.0.1 mit einer Seite, die ihren Titel nennt."""

    SEITE = (b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n"
             b"<html><head><title>Einbettungsprobe</title></head><body>ok</body></html>")

    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._schleife, daemon=True).start()
        return self

    def _schleife(self):
        while True:
            try:
                verbindung, _ = self.sock.accept()
            except OSError:
                return
            with verbindung:
                try:
                    verbindung.settimeout(3.0)
                    verbindung.recv(4096)
                    verbindung.sendall(self.SEITE)
                except OSError:
                    pass

    def __exit__(self, *_a):
        self.sock.close()
        return False


@unittest.skipUnless(TK_DA and wa.verfuegbar()[0], "WebView2 hier nicht einbettbar")
class EchteEinbettungTests(unittest.TestCase):
    """Die echte Engine in einem Tk-Rahmen - gegen 127.0.0.1, nicht gegen die Konsole."""

    def test_eine_seite_laedt_im_tk_rahmen(self):
        fenster = tk.Toplevel(_WURZEL)
        fenster.geometry("420x300+-3000+-3000")     # sichtbar, aber ausser Blick
        self.addCleanup(fenster.destroy)
        rahmen = tk.Frame(fenster, bg="black")
        rahmen.pack(fill="both", expand=True)
        fenster.update()
        # Ein fester Ordner statt eines Wegwerfordners: WebView2 beendet seine
        # Hilfsprozesse nach Close() verzoegert und haelt ihn noch kurz fest.
        daten = os.path.join(os.environ["PS5CONV_KONFIGORDNER"], "WebView2_probe")
        with _Kleinserver() as server:
            seite = wa.Seite(rahmen.winfo_id(), daten)
            seite.groesse_setzen(rahmen.winfo_width(), rahmen.winfo_height())
            seite.navigieren("http://127.0.0.1:%d/" % server.port)
            seite.starten()
            ende = time.monotonic() + 30.0
            while seite.navigation is None and seite.zustand != "fehler" \
                    and time.monotonic() < ende:
                seite.schritt()
                fenster.update()
                time.sleep(0.02)
            titel = seite.titel
            seite.schliessen()
            fenster.update()
        self.assertNotEqual("fehler", seite.zustand, seite.fehler)
        self.assertEqual(True, (seite.navigation or (None,))[0], seite.navigation)
        self.assertEqual("Einbettungsprobe", titel)


class DoktorTests(unittest.TestCase):
    """Die Diagnose sagt, wo Weboberflaechen aufgehen - und warum nicht im Programm."""

    def _zeile(self, verfuegbar, laufzeit="153.0"):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        with mock.patch.object(wa, "verfuegbar", return_value=verfuegbar), \
                mock.patch.object(wa, "laufzeit_version", return_value=laufzeit):
            zeilen = APP.umgebung_doktor()
        return APP, next(z for z in zeilen if "Weboberflächen" in z)

    def test_eingebettet(self):
        APP, zeile = self._zeile((True, ""))
        self.assertEqual("%s Weboberflächen öffnen im Programm (WebView2 153.0)"
                         % APP.DOKTOR_GUT, zeile)

    def test_unter_windows_ohne_pythonnet_ein_hinweis(self):
        APP, zeile = self._zeile((False, wa.GRUND_PYTHONNET))
        self.assertEqual("%s Weboberflächen öffnen im Browser (pythonnet fehlt)"
                         % APP.DOKTOR_HINWEIS, zeile)

    def test_unter_linux_und_macos_neutral(self):
        APP, zeile = self._zeile((False, wa.GRUND_PLATTFORM))
        self.assertTrue(zeile.startswith(APP.DOKTOR_EGAL), zeile)


def _methode(name: str):
    baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
        encoding="utf-8"))
    return next(k for k in ast.walk(baum)
                if isinstance(k, ast.FunctionDef) and k.name == name)


class AufrufstellenTests(unittest.TestCase):
    """Jede Stelle, die eine Weboberflaeche der Konsole oeffnet, geht ueber die Seite."""

    def test_die_drei_stellen_oeffnen_im_programm(self):
        for name in ("_konsole_tafel_web", "_spielstaende_oeffnen", "_bibliothek_dateimanager"):
            quelltext = ast.unparse(_methode(name))
            with self.subTest(methode=name):
                self.assertIn("_webansicht_oeffnen", quelltext)
                self.assertNotIn("webbrowser.open", quelltext)

    def test_der_browser_bleibt_der_ausweg(self):
        quelltext = ast.unparse(_methode("_webansicht_oeffnen"))
        self.assertIn("webansicht.verfuegbar()", quelltext)
        self.assertIn("_webseite_im_browser_statt", quelltext)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfuegbar")
class ProgrammseiteTests(unittest.TestCase):
    """Die Seite im Programm - mit einer nachgebauten Engine statt WebView2."""

    @classmethod
    def setUpClass(cls):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        cls.APP = APP
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def setUp(self):
        self.engines = []
        testfall = self

        class _Engine:
            def __init__(self, hwnd, datenordner):
                self.hwnd, self.datenordner = hwnd, datenordner
                self.zustand, self.fehler, self.navigation = "neu", "", None
                self.titel = ""
                self.aufrufe = []
                testfall.engines.append(self)

            def starten(self):
                self.aufrufe.append("starten")
                self.zustand = "startet"

            def schritt(self):
                pass

            def navigieren(self, adresse):
                self.aufrufe.append(("navigieren", adresse))

            def sichtbar_setzen(self, sichtbar):
                self.aufrufe.append(("sichtbar", sichtbar))

            def groesse_setzen(self, breite, hoehe):
                pass

            def neu_laden(self):
                self.aufrufe.append("neu_laden")

            def schliessen(self):
                self.aufrufe.append("schliessen")
                self.zustand = "zu"

        for ziel, name, ersatz in (
                (self.APP.webansicht, "verfuegbar", lambda: (True, "")),
                (self.APP.webansicht, "Seite", _Engine)):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.browser = mock.Mock()
        flicken = mock.patch.object(self.APP.webbrowser, "open", self.browser)
        flicken.start()
        self.addCleanup(flicken.stop)
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self):
        self.app._webseite_engine = None
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln")
        _WURZEL.update()

    def test_oeffnen_zeigt_die_seite_im_programm(self):
        app = self.app
        app._ansicht_setzen("konsole")
        app._konsole_seite_setzen("spielstaende")
        app._webansicht_oeffnen("http://10.0.0.5:8082/", "dienst.garlic", "spielstaende")
        _WURZEL.update_idletasks()
        self.assertEqual("web", app._konsole_seite)
        self.assertEqual("grid", app._webseite.winfo_manager())
        self.assertEqual("", app._spielstaende_seite.winfo_manager())
        # Wunsch vom 27.09.2026: die ganze Flaeche unter der oberen Leiste -
        # ueber Seitenleiste und Inhalt, die Seitenleiste weicht.
        lage = app._webseite.grid_info()
        self.assertEqual((1, 0, 3), (int(lage["row"]), int(lage["column"]),
                                     int(lage["columnspan"])))
        self.assertEqual("", app.sidebar.winfo_manager())
        # Die obere Leiste liegt in der Stapelreihenfolge ueber der Seite
        # (winfo children nennt die unterste zuerst).
        kinder = [str(k) for k in app.root.tk.splitlist(
            app.root.tk.call("winfo", "children", str(app.root)))]
        self.assertGreater(kinder.index(str(app._main_titlebar)), kinder.index(str(app._webseite)))
        self.assertEqual(app._t("dienst.garlic"), app._webseite_titel.get())
        self.assertEqual("http://10.0.0.5:8082/", app._webseite_adresse.get())
        engine = self.engines[-1]
        self.assertEqual(app._webseite_rahmen.winfo_id(), engine.hwnd)
        self.assertEqual(os.path.join(os.environ["PS5CONV_KONFIGORDNER"], "WebView2"),
                         engine.datenordner)
        self.assertIn("starten", engine.aufrufe)
        self.assertIn(("navigieren", "http://10.0.0.5:8082/"), engine.aufrufe)
        self.browser.assert_not_called()

    def test_zurueck_fuehrt_dorthin_wo_man_herkam(self):
        app = self.app
        app._ansicht_setzen("konsole")
        app._webansicht_oeffnen("http://10.0.0.5:8082/", "dienst.garlic", "spielstaende")
        app._webseite_zurueck()
        self.assertEqual("spielstaende", app._konsole_seite)
        self.assertEqual("", app._webseite.winfo_manager())
        self.assertIn("schliessen", self.engines[-1].aufrufe)
        self.assertEqual("grid", app.sidebar.winfo_manager(), "Die Seitenleiste fehlt danach.")

    def test_verlassen_schliesst_die_engine(self):
        """Entscheidung des Nutzers vom 26.09.2026: beim Verlassen schliessen -
        Speicher frei, kein Hintergrundverkehr zur Konsole."""
        app = self.app
        app._ansicht_setzen("konsole")
        app._webansicht_oeffnen("http://10.0.0.5:8084/", "dienst.pldmgr", "uebersicht")
        erste = self.engines[-1]
        app._konsole_seite_setzen("bibliothek")                  # andere Seite
        self.assertIn("schliessen", erste.aufrufe)
        self.assertIsNone(app._webseite_engine)
        app._webansicht_oeffnen("http://10.0.0.5:8084/", "dienst.pldmgr", "uebersicht")
        zweite = self.engines[-1]
        self.assertIsNot(erste, zweite)
        self.assertIn("starten", zweite.aufrufe)
        app._ansicht_setzen("umwandeln")                         # andere Ansicht
        self.assertIn("schliessen", zweite.aufrufe)
        self.assertIsNone(app._webseite_engine)
        self.assertEqual("grid", app.sidebar.winfo_manager(),
                         "In UMWANDELN fehlt die Seitenleiste.")
        # Zurueck in KONSOLE steht die Seite, von der man kam - kein leerer Rahmen.
        self.assertEqual("uebersicht", app._konsole_seite)
        app._ansicht_setzen("konsole")
        _WURZEL.update_idletasks()
        self.assertEqual("grid", app._konsole_tafel.winfo_manager())
        self.assertEqual("", app._webseite.winfo_manager())

    def test_ohne_einbettung_der_browser_mit_grund(self):
        app = self.app
        protokoll = []
        with mock.patch.object(self.APP.webansicht, "verfuegbar",
                               lambda: (False, self.APP.webansicht.GRUND_PYTHONNET)), \
                mock.patch.object(app, "_append_to_log", protokoll.append):
            app._webansicht_oeffnen("http://10.0.0.5:8084/", "dienst.pldmgr", "uebersicht")
        self.browser.assert_called_once_with("http://10.0.0.5:8084/")
        self.assertEqual([app._t("webseite.log_browser", adresse="http://10.0.0.5:8084/",
                                 grund=app._t("webseite.grund_pythonnet")) + "\n"], protokoll)
        self.assertNotEqual("web", getattr(app, "_konsole_seite", ""))

    def test_startfehler_oeffnet_den_browser_und_fuehrt_zurueck(self):
        app = self.app
        app._ansicht_setzen("konsole")
        app._webansicht_oeffnen("http://10.0.0.5:8084/", "dienst.pldmgr", "uebersicht")
        engine = self.engines[-1]
        engine.zustand, engine.fehler = "fehler", "webseite.grund_faden"
        with mock.patch.object(app, "_append_to_log") as log:
            app._webseite_takt()
        self.browser.assert_called_once_with("http://10.0.0.5:8084/")
        self.assertIn(app._t("webseite.grund_faden"), log.call_args[0][0])
        self.assertEqual("uebersicht", app._konsole_seite)

    def test_verlassen_und_wiederkommen(self):
        app = self.app
        app._ansicht_setzen("konsole")
        app._webansicht_oeffnen("http://10.0.0.5:8084/", "dienst.pldmgr", "uebersicht")
        with mock.patch.object(app, "_webseite_verlassen") as verlassen:
            app._ansicht_setzen("umwandeln")
            verlassen.assert_called()
            verlassen.reset_mock()
            app._ansicht_setzen("konsole")
            app._konsole_seite_setzen("bibliothek")
            verlassen.assert_called()
        self.assertIn(("sichtbar", True), self.engines[-1].aufrufe)

    def test_der_knopf_der_herkunft_bleibt_hervorgehoben(self):
        app = self.app
        app._ansicht_setzen("konsole")
        app._webansicht_oeffnen("http://10.0.0.5:8082/", "dienst.garlic", "spielstaende")
        farben = {schluessel: knopf._bg for knopf, schluessel in app._konsole_knoepfe}
        self.assertEqual(app._COLORS["fg_accent"], farben["konsole.btn_spielstaende"])
        # Ungewaehlt die dunkle Pillenflaeche (seit v1.9.62; vorher bg_card).
        self.assertEqual(app._COLORS["console_bg"], farben["konsole.btn_dienste"])

    def test_sprachwechsel(self):
        app = self.app
        app._ansicht_setzen("konsole")
        app._webansicht_oeffnen("http://10.0.0.5:8084/", "dienst.pldmgr", "uebersicht")
        app._current_language = "en"
        try:
            app._webseite_beschriften()
            self.assertEqual(STRINGS["dienst.pldmgr"]["en"], app._webseite_titel.get())
            self.assertEqual(STRINGS["webseite.startet"]["en"], app._webseite_status.get())
        finally:
            app._current_language = "de"
            app._webseite_beschriften()

    def test_texte_zweisprachig(self):
        for schluessel in ("webseite.zurueck", "webseite.neu_laden", "webseite.im_browser",
                           "webseite.startet", "webseite.laedt", "webseite.geladen",
                           "webseite.fehler_laden", "webseite.fehler_start",
                           "webseite.log_browser"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache))


if __name__ == "__main__":
    unittest.main()
