# -*- coding: utf-8 -*-
"""Tests fuer das Auffinden der externen FileZilla-Installation.

Der eingebaute FTP-Client wurde entfernt; der Knopf FILEZILLA startet
ausschliesslich die externe Anwendung. Damit haengt alles daran, dass sie auch
gefunden wird - und Nutzer installieren sie unter ganz verschiedenen Namen:
"FileZilla", "FileZilla FTP Client", "FileZilla3", oder schlicht direkt auf
einem Laufwerk (``C:\\FileZilla``).

Feste Pfadlisten gehen an solchen Faellen vorbei. Geprueft wird deshalb die
Suche nach dem *Ordnernamen* und die Tiefensuche darin.

Mit abgedeckt ist OSFMount: Dort steckte derselbe Fehler - gelesen wurde aus
``self._settings``, einem Attribut, das nirgends gesetzt wird.
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class TiefensucheTests(unittest.TestCase):
    """_filezilla_exe_unterhalb: die ausfuehrbare Datei im Installationsordner."""

    @classmethod
    def setUpClass(cls):
        cls.G = _lade_hauptprogramm().PS5ConverterGUI

    def setUp(self):
        self.ordner = tempfile.mkdtemp(prefix="fz_test_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)

    def _lege_an(self, *teile):
        pfad = os.path.join(self.ordner, *teile)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with io.open(pfad, "w", encoding="utf-8") as datei:
            datei.write("")
        return pfad

    def test_direkt_im_ordner(self):
        erwartet = self._lege_an("filezilla.exe")
        self.assertEqual(self.G._filezilla_exe_unterhalb(self.ordner, 2), erwartet)

    def test_eine_ebene_tiefer(self):
        erwartet = self._lege_an("App", "filezilla.exe")
        self.assertEqual(self.G._filezilla_exe_unterhalb(self.ordner, 2), erwartet)

    def test_portable_ablage_zwei_ebenen_tiefer(self):
        """FileZillaPortable\\App\\FileZilla\\filezilla.exe."""
        erwartet = self._lege_an("App", "FileZilla", "filezilla.exe")
        self.assertEqual(self.G._filezilla_exe_unterhalb(self.ordner, 2), erwartet)

    def test_jenseits_der_tiefe_nicht_gefunden(self):
        self._lege_an("a", "b", "c", "filezilla.exe")
        self.assertIsNone(self.G._filezilla_exe_unterhalb(self.ordner, 2))

    def test_ohne_treffer(self):
        self._lege_an("liesmich.txt")
        self.assertIsNone(self.G._filezilla_exe_unterhalb(self.ordner, 2))

    def test_unlesbarer_ordner_wirft_nicht(self):
        self.assertIsNone(self.G._filezilla_exe_unterhalb(
            os.path.join(self.ordner, "gibtsnicht"), 2))


class WurzelsucheTests(unittest.TestCase):
    """_find_filezilla_in_roots: beliebig benannter Installationsordner."""

    @classmethod
    def setUpClass(cls):
        cls.G = _lade_hauptprogramm().PS5ConverterGUI

    def setUp(self):
        self.wurzel = tempfile.mkdtemp(prefix="fz_wurzel_")
        self.addCleanup(shutil.rmtree, self.wurzel, ignore_errors=True)
        self.gui = self.G.__new__(self.G)
        self.gui._settings = {}
        # Laufwerkswurzeln ausblenden: Der Test soll nur den gestellten Ordner
        # sehen, nicht eine echte Installation auf diesem Rechner.
        self.gui._feste_laufwerke = staticmethod(lambda: [])
        self._alte_umgebung = {k: os.environ.get(k) for k in
                               ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
                                "LOCALAPPDATA", "APPDATA")}
        for schluessel in self._alte_umgebung:
            os.environ.pop(schluessel, None)
        os.environ["ProgramFiles"] = self.wurzel
        self.addCleanup(self._umgebung_zuruecksetzen)

    def _umgebung_zuruecksetzen(self):
        for schluessel, wert in self._alte_umgebung.items():
            if wert is None:
                os.environ.pop(schluessel, None)
            else:
                os.environ[schluessel] = wert

    def _installiere(self, ordnername, *unterteile):
        pfad = os.path.join(self.wurzel, ordnername, *unterteile, "filezilla.exe")
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with io.open(pfad, "w", encoding="utf-8") as datei:
            datei.write("")
        return pfad

    def test_ordnername_mit_zusatz(self):
        erwartet = self._installiere("FileZilla FTP Client")
        self.assertEqual(self.G._find_filezilla_in_roots(self.gui), erwartet)

    def test_ordnername_ohne_zusatz(self):
        erwartet = self._installiere("FileZilla")
        self.assertEqual(self.G._find_filezilla_in_roots(self.gui), erwartet)

    def test_ordnername_mit_versionsnummer(self):
        erwartet = self._installiere("FileZilla3_x64")
        self.assertEqual(self.G._find_filezilla_in_roots(self.gui), erwartet)

    def test_kleinschreibung_egal(self):
        erwartet = self._installiere("filezilla-portable")
        self.assertEqual(self.G._find_filezilla_in_roots(self.gui), erwartet)

    def test_portable_ablage(self):
        erwartet = self._installiere("FileZillaPortable", "App", "FileZilla")
        self.assertEqual(self.G._find_filezilla_in_roots(self.gui), erwartet)

    def test_fremder_ordner_wird_uebergangen(self):
        os.makedirs(os.path.join(self.wurzel, "Notepad++"), exist_ok=True)
        self.assertIsNone(self.G._find_filezilla_in_roots(self.gui))

    def test_ordner_ohne_ausfuehrbare_datei(self):
        os.makedirs(os.path.join(self.wurzel, "FileZilla Reste"), exist_ok=True)
        self.assertIsNone(self.G._find_filezilla_in_roots(self.gui))


class LaufwerkeTests(unittest.TestCase):
    """_feste_laufwerke: nur eingebaute Datentraeger."""

    @classmethod
    def setUpClass(cls):
        cls.G = _lade_hauptprogramm().PS5ConverterGUI

    @unittest.skipUnless(sys.platform == "win32", "nur unter Windows")
    def test_liefert_mindestens_das_systemlaufwerk(self):
        laufwerke = self.G._feste_laufwerke()
        self.assertTrue(laufwerke, "keine festen Laufwerke gefunden")
        self.assertIn("C:\\", laufwerke)
        for eintrag in laufwerke:
            self.assertRegex(eintrag, r"^[A-Z]:\\$")


class MerkenTests(unittest.TestCase):
    """Ein einmal gestarteter Pfad muss den Programmstart ueberdauern.

    Vorher lag hier ein stiller Fehler: Geschrieben wurde der Pfad, gelesen
    aber aus ``self._settings`` - einem Attribut, das im ganzen Programm
    nirgends gesetzt wird. Der gemerkte Pfad war damit wirkungslos, und
    FileZilla wurde bei jedem Start neu gesucht.
    """

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.G = cls.haupt.PS5ConverterGUI

    def setUp(self):
        self.arbeit = tempfile.mkdtemp(prefix="fz_merken_")
        self.addCleanup(shutil.rmtree, self.arbeit, ignore_errors=True)
        self.konfig = os.path.join(self.arbeit, "paths.json")
        self.exe = os.path.join(self.arbeit, "FileZilla3_x64", "filezilla.exe")
        os.makedirs(os.path.dirname(self.exe), exist_ok=True)
        with io.open(self.exe, "w", encoding="utf-8") as datei:
            datei.write("")

        self.gui = self.G.__new__(self.G)
        self.gui._get_config_path = lambda: self.konfig
        self.gui._feste_laufwerke = staticmethod(lambda: [])
        self.gui._set_status = lambda *a, **k: None
        self.gui.root = None

    def _gespeichert(self):
        if not os.path.isfile(self.konfig):
            return None
        with io.open(self.konfig, encoding="utf-8") as datei:
            return json.load(datei).get("filezilla_path")

    def _schreibe(self, pfad):
        with io.open(self.konfig, "w", encoding="utf-8") as datei:
            json.dump({"filezilla_path": pfad}, datei)

    def test_gestarteter_pfad_wird_gemerkt(self):
        gestartet = []

        class _Popen:
            def __init__(self, befehl, *a, **k):
                gestartet.append(befehl[0])

        self.gui._find_filezilla = lambda: self.exe
        alt = self.haupt.subprocess.Popen
        self.haupt.subprocess.Popen = _Popen
        self.addCleanup(setattr, self.haupt.subprocess, "Popen", alt)

        self.assertTrue(self.G._launch_filezilla(self.gui))
        self.assertEqual(gestartet, [self.exe])
        self.assertEqual(self._gespeichert(), self.exe)

    def test_gemerkter_pfad_wird_zuerst_genutzt(self):
        """Schritt 1 der Suche - ohne ihn waere dieser Pfad unauffindbar."""
        self._schreibe(self.exe)
        self.assertEqual(self.G._find_filezilla(self.gui), self.exe)

    def test_toter_gemerkter_pfad_wird_uebergangen(self):
        tot = os.path.join(self.arbeit, "weg", "filezilla.exe")
        self._schreibe(tot)
        self.assertNotEqual(self.G._find_filezilla(self.gui), tot)

    def test_gleicher_pfad_wird_nicht_neu_geschrieben(self):
        self._schreibe(self.exe)
        vorher = os.stat(self.konfig).st_mtime_ns
        self.G._remember_filezilla_path(self.gui, self.exe)
        self.assertEqual(os.stat(self.konfig).st_mtime_ns, vorher,
                         "unveraenderter Pfad wurde erneut geschrieben")

    def test_leerer_pfad_wird_nicht_gemerkt(self):
        self._schreibe(self.exe)
        self.G._remember_filezilla_path(self.gui, "")
        self.assertEqual(self._gespeichert(), self.exe)


class OsfmountMerkenTests(unittest.TestCase):
    """Derselbe Mechanismus fuer OSFMount.

    Dort war es doppelt wirkungslos: gelesen aus dem nicht existierenden
    ``self._settings`` - und ``osfmount_path`` wurde ueberdies nirgends
    geschrieben. OSFMount wurde deshalb bei jedem Einhaengen neu gesucht,
    an neun Aufrufstellen im Programm.
    """

    @classmethod
    def setUpClass(cls):
        cls.G = _lade_hauptprogramm().PS5ConverterGUI

    def setUp(self):
        self.arbeit = tempfile.mkdtemp(prefix="osf_merken_")
        self.addCleanup(shutil.rmtree, self.arbeit, ignore_errors=True)
        self.konfig = os.path.join(self.arbeit, "paths.json")
        with io.open(self.konfig, "w", encoding="utf-8") as datei:
            datei.write("{}")
        self.exe = os.path.join(self.arbeit, "OSFMount", "OSFMount.com")
        os.makedirs(os.path.dirname(self.exe), exist_ok=True)
        with io.open(self.exe, "w", encoding="utf-8") as datei:
            datei.write("")
        self.gui = self.G.__new__(self.G)
        self.gui._get_config_path = lambda: self.konfig

    def _gespeichert(self):
        with io.open(self.konfig, encoding="utf-8") as datei:
            return json.load(datei).get("osfmount_path")

    def test_treffer_wird_gemerkt(self):
        self.gui._suche_osfmount = lambda: self.exe
        self.assertEqual(self.G._find_osfmount(self.gui), self.exe)
        self.assertEqual(self._gespeichert(), self.exe)

    def test_zweiter_aufruf_sucht_nicht_mehr(self):
        with io.open(self.konfig, "w", encoding="utf-8") as datei:
            json.dump({"osfmount_path": self.exe}, datei)

        def _darf_nicht_laufen():
            raise AssertionError("Die Suche haette nicht laufen duerfen")

        self.gui._suche_osfmount = _darf_nicht_laufen
        self.assertEqual(self.G._find_osfmount(self.gui), self.exe)

    def test_toter_pfad_loest_neue_suche_aus(self):
        with io.open(self.konfig, "w", encoding="utf-8") as datei:
            json.dump({"osfmount_path": os.path.join(self.arbeit, "weg.com")}, datei)
        self.gui._suche_osfmount = lambda: self.exe
        self.assertEqual(self.G._find_osfmount(self.gui), self.exe)
        self.assertEqual(self._gespeichert(), self.exe)

    def test_ohne_treffer_bleibt_es_bei_none(self):
        self.gui._suche_osfmount = lambda: None
        self.assertIsNone(self.G._find_osfmount(self.gui))
        self.assertIsNone(self._gespeichert())


class QuelltextTests(unittest.TestCase):
    """Der eingebaute Client ist vollstaendig entfernt."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            cls.quelle = datei.read()

    def test_eingebauter_client_ist_weg(self):
        for spur in ("_show_ftp_client", "_ftp_win"):
            self.assertNotIn(spur, self.quelle, f"Rest des alten Clients: {spur}")

    def test_knopf_startet_filezilla(self):
        self.assertIn("command=self._launch_filezilla,", self.quelle)

    def test_tastenkuerzel_startet_filezilla(self):
        stelle = self.quelle.index("def _on_shortcut_ftp(")
        block = self.quelle[stelle:stelle + 300]
        self.assertIn("self._launch_filezilla()", block)

    def test_wurzelsuche_haengt_in_der_suchkette(self):
        anfang = self.quelle.index("def _find_filezilla(")
        ende = self.quelle.index("def _feste_laufwerke(", anfang)
        block = self.quelle[anfang:ende]
        self.assertIn("self._find_filezilla_in_roots()", block)

    def test_kein_zugriff_mehr_auf_das_leere_settings_woerterbuch(self):
        """self._settings wird nirgends gesetzt - Zugriffe darauf liefen ins Leere.

        Die verbliebenen Treffer stehen in der Schnellverbindungs-Funktion, die
        selbst nicht aufgerufen wird; Werkzeugpfade duerfen nicht dabei sein.
        """
        for schluessel in ("'filezilla_path'", "'osfmount_path'"):
            stellen = [zeile for zeile in self.quelle.split("\n")
                       if "getattr(self, '_settings'" in zeile and schluessel in zeile]
            self.assertEqual(stellen, [], f"{schluessel} liest noch aus _settings")

    def test_keine_uebersetzungen_des_alten_fensters(self):
        with io.open(os.path.join("ps5_validator", "utils", "i18n.py"),
                     encoding="utf-8") as datei:
            self.assertNotIn("ftp_client.", datei.read())


class MacOsSucheTests(unittest.TestCase):
    """FileZilla auf macOS: gefunden, gestartet - und kein Absturz.

    Gemeldet am 19.08.2026 an echter Apple-Hardware: "nicht gefunden", obwohl
    installiert; danach nach einem Klick auf "Nein" ein vollstaendiger
    Absturz mit Apple-Fehlerbericht.
    """

    @classmethod
    def setUpClass(cls):
        cls.APP = _lade_hauptprogramm()
        cls.quelle = io.open(HAUPTDATEI, encoding="utf-8").read()

    def _gui(self):
        APP = self.APP
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._load_setting = lambda *a, **k: ""
        gui._save_setting = lambda *a, **k: None
        return gui

    def test_app_buendel_gilt_als_gueltiger_pfad(self):
        # Ein .app ist ein Ordner. os.path.isfile() allein liess den
        # gemerkten Pfad bei jeder Pruefung durchfallen.
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            buendel = os.path.join(td, "FileZilla.app")
            os.makedirs(buendel)
            self.assertTrue(self.APP.PS5ConverterGUI._filezilla_pfad_gueltig(buendel))
            self.assertFalse(self.APP.PS5ConverterGUI._filezilla_pfad_gueltig(
                os.path.join(td, "gibtsnicht.app")))
            self.assertFalse(self.APP.PS5ConverterGUI._filezilla_pfad_gueltig(""))

    def test_macos_findet_das_buendel(self):
        from unittest import mock

        gui = self._gui()
        with mock.patch.object(self.APP, "IST_MACOS", True), \
             mock.patch.object(self.APP, "IST_LINUX", False), \
             mock.patch.object(self.APP.os.path, "isdir",
                               lambda p: p == "/Applications/FileZilla.app"), \
             mock.patch.object(self.APP.os.path, "isfile", lambda p: False):
            self.assertEqual(gui._filezilla_posix_suchen(),
                             "/Applications/FileZilla.app")

    def test_nicht_windows_geht_nie_in_die_registrierung(self):
        # Der Windows-Zweig durchsucht Registrierung und alle festen
        # Laufwerke. Auf macOS dauerte das nicht nur umsonst - er fand dort
        # grundsaetzlich nichts, weil er filezilla.exe sucht.
        from unittest import mock

        gui = self._gui()
        gerufen = []
        gui._filezilla_posix_suchen = lambda: gerufen.append("posix") or "/x"
        gui._find_filezilla_via_uninstall_registry = lambda: gerufen.append("registry")
        gui._find_filezilla_by_scan = lambda **k: gerufen.append("scan")
        with mock.patch.object(self.APP, "IST_WINDOWS", False):
            self.assertEqual(gui._find_filezilla(), "/x")
        self.assertEqual(gerufen, ["posix"])

    def test_keine_exe_muster_ausserhalb_von_windows(self):
        # Das war die Absturzursache: Tk auf macOS erwartet Muster der Form
        # "*.ext"; "filezilla.exe" ist keins, und der Cocoa-Dialog riss die
        # Anwendung mit sich.
        quelle = self.quelle
        anfang = quelle.index("    def _launch_filezilla(self)")
        ende = quelle.index("    def _install_osfmount(", anfang)
        block = quelle[anfang:ende]
        # Nicht die Zeichenkette "filezilla.exe" allein suchen - sie steht
        # auch im erklaerenden Kommentar darueber. Gemeint ist der Aufruf,
        # erkennbar am Uebersetzungsschluessel.
        muster_stelle = block.index('self._t("filetype.filezilla_exe")')
        windows_stelle = block.index("elif IST_WINDOWS:")
        macos_stelle = block.index("if IST_MACOS:")
        self.assertLess(macos_stelle, windows_stelle)
        self.assertLess(windows_stelle, muster_stelle,
                        "Die exe-Musterliste steht nicht im Windows-Zweig.")
        self.assertIn("askdirectory(", block,
                      "macOS braucht den Ordnerdialog - ein .app ist ein Ordner.")

    def test_buendel_wird_mit_open_gestartet(self):
        quelle = self.quelle
        anfang = quelle.index("    def _launch_filezilla(self)")
        ende = quelle.index("    def _install_osfmount(", anfang)
        block = quelle[anfang:ende]
        self.assertIn('befehl = ["open", "-a", exe]', block)
        self.assertIn('IST_MACOS and exe.endswith(".app")', block)

    def test_startmeldung_bleibt_nicht_stehen(self):
        """Die Statuszeile nennt einen Zustand, kein Ereignis.

        "FileZilla gestartet: ..." blieb dort auch dann noch stehen, als
        FileZilla laengst wieder geschlossen war (gemeldet am 20.08.2026).
        Ueber ``open -a`` gibt es kein Handle auf FileZilla selbst - dieser
        Zweig muss die Meldung deshalb ohne Prozess abgeben, sonst waere sie
        sofort wieder weg.
        """
        quelle = self.quelle
        anfang = quelle.index("    def _launch_filezilla(self)")
        ende = quelle.index("    def _install_osfmount(", anfang)
        block = quelle[anfang:ende]
        self.assertIn("_set_status_fluechtig(", block,
                      "Die Startmeldung steht wieder fest in der Zeile.")
        self.assertIn("prozess=None if ueber_open else prozess", block)
        self.assertNotIn('self._set_status(f"FileZilla gestartet', block)


class FluechtigeMeldungTests(unittest.TestCase):
    """Die Statuszeile nennt einen Zustand, kein Ereignis.

    "FileZilla gestartet: ..." blieb unten rechts stehen, bis irgendetwas
    anderes die Zeile ueberschrieb - auch dann noch, als FileZilla laengst
    wieder geschlossen war (gemeldet am 20.08.2026).
    """

    @classmethod
    def setUpClass(cls):
        cls.APP = _lade_hauptprogramm()

    def _gui(self, _uhr):
        """Oberflaeche ohne Tk: eine Zeile, eine Warteschlange, eine Uhr."""
        APP = self.APP
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"

        class _Zeile:
            text = ""

            def config(self, text):
                _Zeile.text = text

            def cget(self, _name):
                return _Zeile.text

        class _Wurzel:
            wartend = []

            def after(self, ms, rueckruf):
                if ms == 0:
                    rueckruf()
                else:
                    _Wurzel.wartend.append(rueckruf)
                return "id"

        gui.status_label = _Zeile()
        gui.root = _Wurzel()
        return gui, _Wurzel, _Zeile

    def test_meldung_geht_mit_dem_programm(self):
        """Mit echtem Prozess-Handle: weg, sobald es beendet ist."""
        uhr = [1000.0]
        gui, wurzel, zeile = self._gui(uhr)

        class _Prozess:
            laeuft = True

            def poll(self):
                return None if _Prozess.laeuft else 0

        with mock.patch.object(self.APP.time, "monotonic", lambda: uhr[0]):
            gui._set_status_fluechtig("FileZilla gestartet: FileZilla.app",
                                      prozess=_Prozess())
            self.assertEqual(zeile.text, "FileZilla gestartet: FileZilla.app")
            # Solange es laeuft, bleibt die Meldung stehen.
            for _ in range(3):
                wurzel.wartend.pop(0)()
                self.assertEqual(zeile.text, "FileZilla gestartet: FileZilla.app")
            _Prozess.laeuft = False
            wurzel.wartend.pop(0)()
            self.assertEqual(zeile.text, "Bereit.")

    def test_ohne_prozess_verschwindet_sie_nach_der_hoechstdauer(self):
        """macOS startet ueber ``open`` - dort gibt es kein Handle."""
        uhr = [1000.0]
        gui, wurzel, zeile = self._gui(uhr)
        with mock.patch.object(self.APP.time, "monotonic", lambda: uhr[0]):
            gui._set_status_fluechtig("FileZilla gestartet: FileZilla.app",
                                      prozess=None, hoechstdauer_ms=10000)
            uhr[0] += 5
            wurzel.wartend.pop(0)()
            self.assertEqual(zeile.text, "FileZilla gestartet: FileZilla.app")
            uhr[0] += 10
            wurzel.wartend.pop(0)()
            self.assertEqual(zeile.text, "Bereit.")

    def test_fremde_meldung_behaelt_vorrang(self):
        """Faengt inzwischen eine Aufgabe an, wird ihre Zeile nicht geleert."""
        uhr = [1000.0]
        gui, wurzel, zeile = self._gui(uhr)
        with mock.patch.object(self.APP.time, "monotonic", lambda: uhr[0]):
            gui._set_status_fluechtig("FileZilla gestartet: FileZilla.app",
                                      prozess=None, hoechstdauer_ms=1)
            zeile.text = "Aufgabe 1/8: Packen..."
            uhr[0] += 60
            wurzel.wartend.pop(0)()
        self.assertEqual(zeile.text, "Aufgabe 1/8: Packen...")


class DateidialogTests(unittest.TestCase):
    """Kein Dateidialog darf macOS mit einem Dateinamen als Muster erwischen.

    Der Absturzbericht vom 18.08.2026 (Mac mini, macOS 26.6.2) zeigt die
    Kette::

        Exception Reason: *** -[__NSArrayM insertObject:atIndex:]:
                          object cannot be nil
        3  libtk8.6.dylib   setAllowedFileTypes + 268
        4  libtk8.6.dylib   Tk_GetOpenFileObjCmd + 1240

    Tk streift von jedem Muster fuehrende ``*`` und ``.`` ab und reicht den
    Rest als Dateiendung weiter. Aus ``*.exe`` wird ``exe`` - gueltig. Aus
    ``filezilla.exe`` wird ``filezilla.exe``, und das ist keine Endung:
    macOS liefert nichts, Tk legt das Nichts in ein Array, Objective-C
    bricht den Prozess ab.

    Gefunden wurden zwei solche Stellen. Diese Pruefung geht ueber *alle*
    Dateidialoge des Programms, damit die dritte gar nicht erst entsteht.
    """

    @classmethod
    def setUpClass(cls):
        cls.APP = _lade_hauptprogramm()

    @staticmethod
    def _ist_gefaehrlich(muster: str) -> bool:
        """True, wenn nach dem Abstreifen noch ein Punkt im Rest steht."""
        for teil in str(muster).split():
            if "." in teil.lstrip("*").lstrip("."):
                return True
        return False

    def test_dateidialoge_macos_sicher(self):
        import ast

        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            baum = ast.parse(datei.read())

        geprueft = 0
        beanstandet = []
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            for schluessel in knoten.keywords:
                if schluessel.arg != "filetypes":
                    continue
                geprueft += 1
                wert = schluessel.value
                # Durch _dateitypen gereicht? Dann ist die Zusage gegeben.
                if (isinstance(wert, ast.Call)
                        and isinstance(wert.func, ast.Attribute)
                        and wert.func.attr == "_dateitypen"):
                    continue
                # Nur das MUSTER pruefen, nicht die Beschriftung: Die ist
                # ein Uebersetzungsschluessel wie "filetype.all_files" und
                # enthaelt selbst einen Punkt. Ein Durchlauf ueber alle
                # Zeichenketten des Knotens meldete deshalb 21 Fehlalarme.
                for eintrag in getattr(wert, "elts", []):
                    paar = getattr(eintrag, "elts", [])
                    if len(paar) != 2:
                        continue
                    muster = paar[1]
                    if (isinstance(muster, ast.Constant)
                            and isinstance(muster.value, str)
                            and self._ist_gefaehrlich(muster.value)):
                        beanstandet.append(
                            "Zeile %d: %r" % (muster.lineno, muster.value))

        self.assertGreater(geprueft, 15, "Es wurden kaum Dialoge gefunden - "
                                         "sucht die Pruefung noch richtig?")
        self.assertEqual(
            beanstandet, [],
            "Diese Muster bringen macOS zum Absturz. Entweder ein Muster der "
            "Form '*.endung' benutzen oder die Liste durch self._dateitypen(...) "
            "reichen:\n  " + "\n  ".join(beanstandet))

    def test_entschaerfung_wirkt_nur_auf_macos(self):
        from unittest import mock

        APP = self.APP
        roh = [("FileZilla", "filezilla.exe"), ("Programme", "*.exe")]

        with mock.patch.object(APP, "IST_MACOS", False):
            self.assertEqual(APP.PS5ConverterGUI._dateitypen(roh), roh,
                             "Auf Windows und Linux darf nichts wegfallen")

        with mock.patch.object(APP, "IST_MACOS", True):
            self.assertEqual(APP.PS5ConverterGUI._dateitypen(roh),
                             [("Programme", "*.exe")])

    def test_sternchen_punkt_sternchen_bleibt(self):
        # "*.*" ist harmlos: Nach dem Abstreifen bleibt nichts uebrig, und
        # was leer ist, ueberspringt Tk. Faellt es trotzdem weg, verlieren
        # 21 Dialoge ihren "Alle Dateien"-Eintrag.
        from unittest import mock

        APP = self.APP
        with mock.patch.object(APP, "IST_MACOS", True):
            self.assertEqual(
                APP.PS5ConverterGUI._dateitypen([("Alle Dateien", "*.*")]),
                [("Alle Dateien", "*.*")])

    def test_gemischtes_muster_verliert_nur_den_dateinamen(self):
        from unittest import mock

        APP = self.APP
        with mock.patch.object(APP, "IST_MACOS", True):
            self.assertEqual(
                APP.PS5ConverterGUI._dateitypen(
                    [("SELF", "eboot.bin *.self *.elf")]),
                [("SELF", "*.self *.elf")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
