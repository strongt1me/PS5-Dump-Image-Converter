"""Regressionstests fuer drei kleinere Funde aus dem Praxistest.

1. Hintergrundbild: Die Auswahl wurde als absoluter Pfad gespeichert. In der
   EXE liegt der mitgelieferte Bildordner unter ``sys._MEIPASS`` und wird beim
   Beenden geloescht - die gespeicherte Wahl zeigte danach ins Leere und das
   Bild fiel still auf den Standard zurueck.
2. Pillow: ``Image.getdata()`` ist seit Pillow 12 veraltet (Entfernung mit
   Pillow 14) und warf bei jedem Programmstart eine DeprecationWarning.
3. Temp-Reste: ``ps5conv_*``-Ordner wurden nur beim Schliessen der Oberflaeche
   entfernt - ein CLI-Lauf endet ueber sys.exit() und liess sie liegen.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import tkinter as tk
import unittest
import warnings
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


class HintergrundbildPfadTests(unittest.TestCase):
    """Mitgelieferte Bilder werden als Markierung gespeichert, nicht als Pfad."""

    def setUp(self) -> None:
        self.GUI = APP.PS5ConverterGUI
        self.bundle = self.GUI._bundled_background_dir()
        if not self.bundle or not os.path.isdir(self.bundle):
            self.skipTest("mitgelieferter Bildordner nicht vorhanden")
        bilder = self.GUI._bundled_background_images()
        if not bilder:
            self.skipTest("keine mitgelieferten Bilder vorhanden")
        self.bild = bilder[0]

    def test_mitgeliefertes_bild_wird_als_markierung_abgelegt(self) -> None:
        wert = self.GUI._encode_background_setting(self.bild)
        self.assertTrue(wert.startswith(self.GUI._BUNDLED_IMAGE_MARKER))
        self.assertEqual(wert.split(":", 1)[1], os.path.basename(self.bild))

    def test_markierung_wird_wieder_aufgeloest(self) -> None:
        wert = self.GUI._encode_background_setting(self.bild)
        self.assertEqual(
            os.path.normcase(self.GUI._decode_background_setting(wert)),
            os.path.normcase(self.bild),
        )

    def test_eigenes_bild_bleibt_absoluter_pfad(self) -> None:
        with tempfile.TemporaryDirectory() as ordner:
            eigen = os.path.join(ordner, "eigenes.png")
            Path(eigen).write_bytes(b"\x89PNG\r\n\x1a\n")
            wert = self.GUI._encode_background_setting(eigen)
            self.assertFalse(wert.startswith(self.GUI._BUNDLED_IMAGE_MARKER))
            self.assertEqual(os.path.normcase(wert), os.path.normcase(eigen))
            self.assertEqual(os.path.normcase(self.GUI._decode_background_setting(wert)),
                             os.path.normcase(eigen))

    def test_toter_meipass_pfad_wird_repariert(self) -> None:
        """Genau der Altbestand aus der Konfiguration des Nutzers."""
        tot = os.path.join(
            r"C:\Users\XYZ\AppData\Local\Temp\_MEI213362\Hintergrundbilder",
            os.path.basename(self.bild),
        )
        self.assertFalse(os.path.isfile(tot))
        self.assertEqual(
            os.path.normcase(self.GUI._decode_background_setting(tot)),
            os.path.normcase(self.bild),
        )

    def test_unbekannter_pfad_bleibt_leer(self) -> None:
        self.assertEqual(self.GUI._decode_background_setting(r"X:\gibtsnicht\bild.png"), "")
        self.assertEqual(self.GUI._decode_background_setting(""), "")
        self.assertEqual(self.GUI._decode_background_setting("   "), "")

    def test_markierung_ohne_passende_datei_bleibt_leer(self) -> None:
        wert = self.GUI._BUNDLED_IMAGE_MARKER + "gibtsnicht.png"
        self.assertEqual(self.GUI._decode_background_setting(wert), "")


class DurchschnittsfarbeTests(unittest.TestCase):
    """Die Farbberechnung ohne die veraltete Pillow-Schnittstelle."""

    def test_ergebnis_stimmt(self) -> None:
        from PIL import Image
        bild = Image.new("RGB", (40, 40), (10, 20, 30))
        self.assertEqual(APP.PS5ConverterGUI._average_image_rgb(bild), (10, 20, 30))

    def test_gemischtes_bild_liegt_zwischen_den_farben(self) -> None:
        """Die Funktion verkleinert vorher auf 16x16 - das Ergebnis ist bewusst
        eine Naeherung, muss aber zwischen den beiden Ausgangsfarben liegen."""
        from PIL import Image
        bild = Image.new("RGB", (64, 64), (0, 0, 0))
        for x in range(32, 64):
            for y in range(64):
                bild.putpixel((x, y), (100, 200, 40))
        r, g, b = APP.PS5ConverterGUI._average_image_rgb(bild)
        self.assertTrue(0 < r < 100, r)
        self.assertTrue(0 < g < 200, g)
        self.assertTrue(0 < b < 40, b)

    def test_keine_deprecation_warnung_mehr(self) -> None:
        from PIL import Image
        bild = Image.new("RGB", (32, 32), (7, 7, 7))
        with warnings.catch_warnings(record=True) as gesammelt:
            warnings.simplefilter("always")
            APP.PS5ConverterGUI._average_image_rgb(bild)
        veraltet = [w for w in gesammelt if issubclass(w.category, DeprecationWarning)]
        self.assertEqual(veraltet, [], f"unerwartet: {[str(w.message) for w in veraltet]}")

    def test_getdata_wird_nicht_mehr_aufgerufen(self) -> None:
        """Nur der Aufruf ist verboten - im Kommentar darf der Name stehen."""
        quelltext = QUELLDATEI.read_text(encoding="utf-8")
        aufrufe = [
            zeile.strip() for zeile in quelltext.splitlines()
            if ".getdata()" in zeile
            and not zeile.lstrip().startswith("#")
            and "``" not in zeile
        ]
        self.assertEqual(aufrufe, [], f"noch vorhanden: {aufrufe}")
        self.assertIn("ImageStat.Stat(", quelltext)


class TempRestTests(unittest.TestCase):
    """Alte Arbeitsordner werden abgeraeumt, junge nicht angefasst."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="sweep_")
        self.basis = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _ordner(self, name: str, alter_stunden: float) -> str:
        pfad = os.path.join(self.basis, name)
        os.makedirs(pfad, exist_ok=True)
        Path(os.path.join(pfad, "inhalt.bin")).write_bytes(b"x" * 16)
        zeitpunkt = time.time() - alter_stunden * 3600
        os.utime(pfad, (zeitpunkt, zeitpunkt))
        return pfad

    def _sweep(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._get_runtime_temp_dir = lambda: self.basis
        gui._append_to_log = lambda *a, **k: None
        gui._t = lambda schluessel, **kw: schluessel
        APP.PS5ConverterGUI._sweep_stale_temp_dirs(gui)

    def test_alter_rest_wird_entfernt(self) -> None:
        alt = self._ordner("ps5conv_ufs2_alt", 30)
        self._sweep()
        self.assertFalse(os.path.exists(alt))

    def test_junger_ordner_bleibt_unberuehrt(self) -> None:
        """Schutz fuer einen parallel laufenden zweiten Vorgang."""
        jung = self._ordner("ps5conv_ufs2_jung", 1)
        self._sweep()
        self.assertTrue(os.path.exists(jung))

    def test_fremde_ordner_bleiben_unberuehrt(self) -> None:
        fremd = self._ordner("wichtige_daten", 99)
        self._sweep()
        self.assertTrue(os.path.exists(fremd))

    def test_nur_einmal_je_prozess(self) -> None:
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._get_runtime_temp_dir = lambda: self.basis
        gui._append_to_log = lambda *a, **k: None
        gui._t = lambda schluessel, **kw: schluessel
        APP.PS5ConverterGUI._sweep_stale_temp_dirs(gui)
        spaeter = self._ordner("ps5conv_nested_pfs_alt", 40)
        APP.PS5ConverterGUI._sweep_stale_temp_dirs(gui)
        self.assertTrue(os.path.exists(spaeter), "zweiter Durchlauf haette nicht laufen duerfen")


class CliAufraeumenTests(unittest.TestCase):
    """Der CLI-Modus muss die Temp-Ziele selbst abraeumen."""

    def test_cli_ruft_die_bereinigung_auf(self) -> None:
        quelltext = QUELLDATEI.read_text(encoding="utf-8")
        start = quelltext.index("def _run_cli(")
        block = quelltext[start:start + 40000]
        ende = block.index("if __name__ ==") if "if __name__ ==" in block else len(block)
        block = block[:ende]
        self.assertIn("_cleanup_exit_temp_targets()", block)

    def test_sweep_haengt_an_der_temp_erzeugung(self) -> None:
        quelltext = QUELLDATEI.read_text(encoding="utf-8")
        start = quelltext.index("def _mkdtemp(")
        self.assertIn("_sweep_stale_temp_dirs()", quelltext[start:start + 600])


class SidebarCoverTests(unittest.TestCase):
    """Das Cover in der Sidebar-Vorschau.

    Es sass mit ungleichen Raendern in seiner Flaeche: waagerecht 96 px links
    gegen 97 px rechts, senkrecht klebte es direkt unter den Modusknoepfen und
    liess den gesamten Rest bis zum Fussbereich als Leerraum stehen.

    Die Groesse bleibt dabei ausdruecklich unveraendert - hoechstens ein Pixel
    kleiner, damit der Restplatz gerade aufgeht und Tk ihn gleichmaessig
    verteilen kann.
    """

    class _Fake:
        def __init__(self, **werte):
            self._w = werte

        def winfo_width(self):
            return self._w.get("width", 0)

        def winfo_height(self):
            return self._w.get("height", 0)

        def winfo_y(self):
            return self._w.get("y", 0)

        def winfo_reqheight(self):
            return self._w.get("reqheight", 0)

        def winfo_ismapped(self):
            return self._w.get("mapped", True)

        def winfo_manager(self):
            # _center_sidebar_cover fragt den Packmanager statt der Abbildung
            # ab: Ein Widget ist gepackt, bevor Tk es abbildet.
            return "pack" if self._w.get("mapped", True) else ""

    def _gui(self, knopfbreite=473):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mode_buttons = [(self._Fake(width=knopfbreite), "pack_folder")]
        gui.sidebar = self._Fake(width=knopfbreite + 20)
        return gui

    def test_cover_wird_nicht_groesser(self):
        """Kernanforderung: die Groesse bleibt, nur die Lage aendert sich."""
        gui = self._gui(knopfbreite=473)
        self.assertLessEqual(APP.PS5ConverterGUI._sidebar_cover_width(gui),
                             APP.PS5ConverterGUI._SIDEBAR_COVER_SIZE)

    def test_ungerader_restplatz_wird_ausgeglichen(self):
        """473 - 300 = 173 waere ungerade und ergaebe 96/97 px."""
        gui = self._gui(knopfbreite=473)
        groesse = APP.PS5ConverterGUI._sidebar_cover_width(gui)
        self.assertEqual((473 - groesse) % 2, 0)
        self.assertEqual(groesse, 299)

    def test_gerader_restplatz_bleibt_unangetastet(self):
        gui = self._gui(knopfbreite=474)
        self.assertEqual(APP.PS5ConverterGUI._sidebar_cover_width(gui), 300)

    def test_schmale_sidebar_schneidet_nicht_ab(self):
        gui = self._gui(knopfbreite=200)
        self.assertLessEqual(APP.PS5ConverterGUI._sidebar_cover_width(gui), 200)

    def test_untergrenze_wird_eingehalten(self):
        gui = self._gui(knopfbreite=40)
        self.assertGreaterEqual(APP.PS5ConverterGUI._sidebar_cover_width(gui), 120)

    def test_ohne_gemessene_geometrie_bleibt_der_alte_wert(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mode_buttons = []
        gui.sidebar = None
        self.assertEqual(APP.PS5ConverterGUI._sidebar_cover_width(gui), 300)

    def test_innenbreite_kommt_vom_modusknopf(self):
        gui = self._gui(knopfbreite=473)
        self.assertEqual(APP.PS5ConverterGUI._sidebar_interior_width(gui), 473)

    def test_senkrechte_zentrierung_teilt_den_freiraum(self):
        """Der Block aus Bild und Name bekommt oben und unten gleich viel Luft."""
        gesetzt = {}

        class _Label(self._Fake):
            def winfo_exists(self):
                return True

            def pack_configure(self, **kw):
                gesetzt.update(kw)

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mode_buttons = [(self._Fake(width=473, y=476, height=40), "pack_folder")]
        gui._sidebar_preview_img_label = _Label(y=519, reqheight=300, mapped=True)
        gui._sidebar_footer_frame = self._Fake(y=887)
        gui._sidebar_preview_title_label = self._Fake(reqheight=20, mapped=True)
        gui._sidebar_cover_pady = 0
        APP.PS5ConverterGUI._center_sidebar_cover(gui)
        # Bereich 516..887, Bild 300, Titel 20+6, Vorlauf 519-516 = 3
        # frei = 887-516-300-26 = 45, Rest = 39  ->  Mitte = 19
        # dazu der gewuenschte Zusatzabstand von 8 px  ->  27
        abstand = APP.PS5ConverterGUI._SIDEBAR_COVER_ABSTAND
        self.assertEqual(gesetzt.get("pady"), (19 + abstand, 0))
        # Der Block sitzt bewusst um diesen Abstand tiefer als die exakte Mitte
        # (Wunsch vom 16.08.2026). Ein Pixel Rest bleibt bei ungeradem Platz.
        oben = 3 + 19 + abstand
        unten = 887 - (516 + 3 + 19 + abstand + 300 + 26)
        self.assertLessEqual(
            abs((oben - unten) - 2 * abstand), 1,
            f"oben={oben} unten={unten}: der Block soll {abstand} px tiefer sitzen")

    def test_gesetzte_polsterung_wird_selbst_gemerkt(self):
        """pack_info() liefert ein Tupel; ein int() darauf warf und legte die
        Zentrierung ab dem zweiten Aufruf still lahm."""
        gesetzt = {}

        class _Label(self._Fake):
            def winfo_exists(self):
                return True

            def pack_configure(self, **kw):
                gesetzt.update(kw)

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mode_buttons = [(self._Fake(width=473, y=476, height=40), "pack_folder")]
        # y = bereich_oben + Vorlauf 3 + gesetzte Polsterung 27
        gui._sidebar_preview_img_label = _Label(y=546, reqheight=300, mapped=True)
        gui._sidebar_footer_frame = self._Fake(y=887)
        gui._sidebar_preview_title_label = self._Fake(reqheight=20, mapped=True)
        gui._sidebar_cover_pady = 19 + APP.PS5ConverterGUI._SIDEBAR_COVER_ABSTAND
        APP.PS5ConverterGUI._center_sidebar_cover(gui)
        self.assertEqual(gui._sidebar_cover_pady,
                         19 + APP.PS5ConverterGUI._SIDEBAR_COVER_ABSTAND)
        self.assertEqual(gesetzt, {}, "unveraenderte Lage darf nicht neu gesetzt werden")

    def test_ohne_geometrie_passiert_nichts(self):
        """Vor dem ersten Zeichnen liefert Tk 0/1 - dann darf nichts gesetzt werden."""
        gesetzt = {}

        class _Label(self._Fake):
            def winfo_exists(self):
                return True

            def pack_configure(self, **kw):
                gesetzt.update(kw)

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mode_buttons = [(self._Fake(width=473, y=0, height=0), "pack_folder")]
        gui._sidebar_preview_img_label = _Label(y=0, reqheight=1, mapped=True)
        gui._sidebar_footer_frame = self._Fake(y=0)
        gui._sidebar_preview_title_label = self._Fake(reqheight=0, mapped=False)
        APP.PS5ConverterGUI._center_sidebar_cover(gui)
        self.assertEqual(gesetzt, {})

    def test_kein_negativer_abstand_bei_engem_platz(self):
        gesetzt = {}

        class _Label(self._Fake):
            def winfo_exists(self):
                return True

            def winfo_manager(self):
                return "pack"

            def pack_info(self):
                return {"pady": 40}

            def pack_configure(self, **kw):
                gesetzt.update(kw)

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui.mode_buttons = [(self._Fake(width=473, y=476, height=40), "pack_folder")]
        gui._sidebar_preview_img_label = _Label(y=560, reqheight=300, mapped=True)
        gui._sidebar_footer_frame = self._Fake(y=700)
        gui._sidebar_preview_title_label = self._Fake(reqheight=20, mapped=True)
        APP.PS5ConverterGUI._center_sidebar_cover(gui)
        self.assertEqual(gesetzt.get("pady"), (0, 0))

    def test_label_wird_nicht_gefuellt_sonst_entsteht_ein_rahmen(self):
        """Ein Label zeichnet immer seinen Hintergrund. Mit fill="x" stand der
        unbedeckte Teil als heller Rahmen neben dem Cover - genau der Effekt,
        der in v1.8.28 schon bei den Karten-Beschriftungen behoben wurde."""
        quelltext = QUELLDATEI.read_text(encoding="utf-8")
        start = quelltext.index("_sidebar_preview_img_label.config(image=self._sidebar_preview_photo)")
        block = quelltext[start:start + 400]
        self.assertIn('pack(anchor="center"', block)
        self.assertNotIn('pack(fill="x"', block)


class FruehesFenstersymbolTests(unittest.TestCase):
    """Beim Start darf nie die Tk-Standardfeder in der Taskleiste stehen.

    Bis v1.8.51 bekam das Fenster sein Symbol erst in
    ``PS5ConverterGUI.__init__`` - also nach dem Aufbau von Hintergrundbildern,
    Cover und Bedienelementen. Der Taskleisteneintrag entsteht aber schon mit
    ``tk.Tk()``, und bis dahin zeigt Windows das Standardsymbol von Tk. Rund
    eine Sekunde bei jedem Start.

    ``root.attributes("-alpha", 0.0)`` half nicht: Es macht das Fenster
    durchsichtig, nicht den Taskleisteneintrag weg.
    """

    QUELLE = Path(APP.__file__).read_text(encoding="utf-8")

    def test_funktion_vorhanden(self):
        self.assertTrue(callable(getattr(APP, "_fenstersymbol_sofort_setzen", None)))

    def _gui_start(self) -> str:
        """Nur der Abschnitt des GUI-Starts.

        'app = PS5ConverterGUI(root)' steht auch im Kommandozeilenzweig, und der
        kommt im Quelltext frueher - eine Suche ueber die ganze Datei misst
        deshalb die falsche Stelle.
        """
        beginn = self.QUELLE.index("# Normaler GUI-Modus")
        return self.QUELLE[beginn:]

    def test_aufruf_steht_vor_dem_aufbau(self):
        # Die Reihenfolge ist der ganze Punkt: erst Symbol, dann Oberflaeche.
        abschnitt = self._gui_start()
        symbol = abschnitt.index("_fenstersymbol_sofort_setzen(root)")
        aufbau = abschnitt.index("app = PS5ConverterGUI(root)")
        self.assertLess(symbol, aufbau,
                        "Das Symbol wird erst nach dem Aufbau der Oberflaeche gesetzt")

    def test_aufruf_direkt_nach_dem_fenster(self):
        abschnitt = self._gui_start()
        fenster = abschnitt.index("root = TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk()")
        symbol = abschnitt.index("_fenstersymbol_sofort_setzen(root)")
        dazwischen = abschnitt[fenster:symbol]
        # Nur Titel und Kommentare duerfen dazwischenstehen. Alles Weitere
        # verlaengert die Zeitspanne, in der die Feder sichtbar ist.
        code = [z.strip() for z in dazwischen.splitlines()[1:]
                if z.strip() and not z.strip().startswith("#")]
        self.assertEqual(code, ["root.title(APP_TITLE)"], f"Dazwischen steht: {code}")

    def test_drei_quellen_in_der_richtigen_reihenfolge(self):
        block = self.QUELLE[self.QUELLE.index("def _fenstersymbol_sofort_setzen"):]
        block = block[:block.index("def _set_windows_app_user_model_id")]
        datei = block.index("app_icon.ico")
        eingebettet_ico = block.index("_APP_ICON_ICO_B64")
        eingebettet_png = block.index("_APP_ICON_PNG32_B64")
        self.assertLess(datei, eingebettet_ico)
        self.assertLess(eingebettet_ico, eingebettet_png)

    def test_setzt_wirklich_ein_symbol(self):
        try:
            fenster = tk.Tk()
        except Exception:
            self.skipTest("Kein Tk verfuegbar")
        fenster.withdraw()
        try:
            self.assertTrue(APP._fenstersymbol_sofort_setzen(fenster))
        finally:
            fenster.destroy()

    def test_kein_temp_rest_wenn_das_setzen_scheitert(self):
        """Der Fehlerzweig muss die eben geschriebene .ico wieder abraeumen.

        Weg 2 schreibt das eingebettete Symbol in eine temporaere Datei und
        loescht sie ueber after(). Scheitert danach iconbitmap, wird das after()
        nie erreicht - ohne eigenes Aufraeumen bliebe bei jedem Start eine
        Datei im Temp-Ordner liegen.
        """
        import glob
        import tempfile as _tf
        from unittest import mock

        try:
            fenster = tk.Tk()
        except Exception:
            self.skipTest("Kein Tk verfuegbar")
        fenster.withdraw()
        muster = os.path.join(_tf.gettempdir(), "*.ico")
        vorher = set(glob.glob(muster))
        try:
            # Weg 1 ausschalten, Weg 2 scheitern lassen.
            with mock.patch.object(APP, "_bundled_resource", return_value=""),                  mock.patch.object(fenster, "iconbitmap", side_effect=RuntimeError("geht nicht")):
                APP._fenstersymbol_sofort_setzen(fenster)
            self.assertEqual(set(glob.glob(muster)) - vorher, set(),
                             "Der Fehlerzweig hat eine .ico im Temp-Ordner liegen lassen")
        finally:
            fenster.destroy()

    def test_parameter_ist_typisiert(self):
        # Die Datei nutzt durchgaengig Typangaben; der Helfer soll das auch.
        zeile = [z for z in self.QUELLE.splitlines()
                 if z.startswith("def _fenstersymbol_sofort_setzen")]
        self.assertTrue(zeile)
        self.assertIn("tk.Tk | tk.Toplevel", zeile[0])

    def test_eingebettetes_ico_gleicht_der_datei(self):
        # Zwei Quellen, ein Motiv: Weichen sie voneinander ab, zeigt das
        # Programm je nach Weg ein anderes Symbol.
        import base64
        import re

        treffer = re.search(r'_APP_ICON_ICO_B64 = "([^"]+)"', self.QUELLE)
        self.assertIsNotNone(treffer)
        eingebettet = base64.b64decode(treffer.group(1))
        with open(Path(APP.__file__).parent / "app_icon.ico", "rb") as datei:
            self.assertEqual(eingebettet, datei.read())


class DpiWechselTests(unittest.TestCase):
    """Der Monitorwechsel wird festgehalten, nicht ausgeglichen.

    Ein gemischter Aufbau laesst sich hier nicht herstellen - der Rechner hat
    einen Monitor. Geprueft wird deshalb die Logik mit untergeschobener
    Fenster-DPI: Wechselt sie, muss genau eine Warnung fallen; bleibt sie
    gleich, keine.
    """

    def _gui(self, dpi_folge):
        """Baut ein Objekt, dem eine Folge von DPI-Werten vorgesetzt wird."""
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._letzte_fenster_dpi = None
        gui._dpi_abfrage_moeglich = True
        gui.root = type("Wurzel", (), {"winfo_id": lambda self: 1})()
        self._folge = list(dpi_folge)
        return gui

    def _laufen_lassen(self, gui, dpi_folge):
        """Ruft die Feststellung je einmal pro DPI-Wert auf."""
        import logging
        from unittest import mock

        meldungen = []

        class _Faenger(logging.Handler):
            def emit(self, satz):
                meldungen.append((satz.levelno, satz.getMessage()))

        faenger = _Faenger()
        APP.logger.addHandler(faenger)
        try:
            for wert in dpi_folge:
                with mock.patch.object(APP.ctypes, "windll") as windll:
                    windll.user32.GetDpiForWindow.return_value = wert
                    gui._dpi_wechsel_festhalten()
        finally:
            APP.logger.removeHandler(faenger)
        return meldungen

    def test_gleiche_dpi_meldet_nur_den_start(self):
        gui = self._gui([120, 120, 120])
        meldungen = self._laufen_lassen(gui, [120, 120, 120])
        warnungen = [m for stufe, m in meldungen if stufe >= 30]
        self.assertEqual(warnungen, [], "Ohne Wechsel darf keine Warnung fallen")
        self.assertEqual(gui._letzte_fenster_dpi, 120)

    def test_wechsel_wird_einmal_gemeldet(self):
        gui = self._gui([120, 120, 96, 96])
        meldungen = self._laufen_lassen(gui, [120, 120, 96, 96])
        warnungen = [m for stufe, m in meldungen if stufe >= 30]
        self.assertEqual(len(warnungen), 1, meldungen)
        self.assertIn("125 % -> 100 %", warnungen[0])
        self.assertIn("DPI 120 -> 96", warnungen[0])
        self.assertEqual(gui._letzte_fenster_dpi, 96)

    def test_fehlende_windows_funktion_wird_nicht_nachgefragt(self):
        from unittest import mock

        gui = self._gui([])
        with mock.patch.object(APP.ctypes, "windll") as windll:
            windll.user32.GetDpiForWindow.side_effect = AttributeError("zu alt")
            gui._dpi_wechsel_festhalten()
            gui._dpi_wechsel_festhalten()
            # Nach dem ersten Fehlschlag wird gar nicht mehr gefragt.
            self.assertEqual(windll.user32.GetDpiForWindow.call_count, 1)
        self.assertFalse(gui._dpi_abfrage_moeglich)

    def test_feststellung_haengt_nicht_an_den_abbruchbedingungen(self):
        # Ein Monitorwechsel kann in jeden Zweig von _on_root_configure
        # laufen - Vollbild, kein Hintergrundbild, gleiche Groesse. Die
        # Feststellung muss davor stehen, sonst faellt sie genau dann aus,
        # wenn sie gebraucht wird.
        quelle = QUELLDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("    def _on_root_configure(self, event: tk.Event)")
        block = quelle[anfang:anfang + 1600]
        self.assertIn("self._dpi_wechsel_festhalten()", block)
        self.assertLess(
            block.index("self._dpi_wechsel_festhalten()"),
            # Die Vollbild-Ausnahme ist mit v1.8.55 gefallen; die
            # Abbruchbedingung heisst seither nur noch so.
            block.index("if not self._bg_image_cache:"),
            "Die Feststellung steht hinter einer Abbruchbedingung.",
        )

    def test_nichts_wird_umgerechnet(self):
        # Absichtserklaerung: Die Feststellung darf keine Schrift und keine
        # Geometrie anfassen. Faellt das je um, muss es hier auffallen.
        quelle = QUELLDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("    def _dpi_wechsel_festhalten(self)")
        ende = quelle.index("    def _on_root_configure(", anfang)
        rumpf = quelle[anfang:ende]
        for verboten in ("tk scaling", ".configure(font", "geometry(", "nametofont"):
            self.assertNotIn(verboten, rumpf,
                             "Die Feststellung greift ein, statt nur zu melden")


class FehlerfaengerTests(unittest.TestCase):
    """Unbehandelte Ausnahmen werden aufgezeichnet statt verschluckt.

    Die EXE wird mit console=False gebaut, damit ist sys.stderr leer.
    Tkinter schreibt Fehler aus Knopf-Handlern genau dorthin - sie
    verschwanden spurlos, und der Knopf tat einfach nichts.
    """

    def setUp(self):
        APP._LETZTE_FEHLER.clear()

    def _ausnahme(self, art, text):
        try:
            raise art(text)
        except art:
            import sys as _s
            return _s.exc_info()

    def test_alle_drei_wege_werden_aufgezeichnet(self):
        import sys, threading

        APP._haken_setzen()
        sys.excepthook(*self._ausnahme(ValueError, "Probe Haupt"))

        def kaputt():
            raise RuntimeError("Probe Faden")
        faden = threading.Thread(target=kaputt, name="Prober")
        faden.start()
        faden.join()

        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._append_to_log = lambda _s: None
        gui._t = lambda k, **kw: ""
        gui._tk_fehler_melden(*self._ausnahme(KeyError, "Probe Tk"))

        quellen = [e.split(" | ")[1] for e in APP._LETZTE_FEHLER]
        self.assertEqual(quellen, ["Hauptfaden", "Faden Prober", "Tk-Ereignis"])

    def test_rueckverfolgung_steht_drin(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._append_to_log = lambda _s: None
        gui._t = lambda k, **kw: ""
        gui._tk_fehler_melden(*self._ausnahme(ZeroDivisionError, "Probe"))
        eintrag = APP._LETZTE_FEHLER[-1]
        self.assertIn("ZeroDivisionError", eintrag)
        self.assertIn("Traceback", eintrag)

    def test_melden_scheitert_nie(self):
        # Ein Fehler beim Melden eines Fehlers darf das Programm nicht
        # mitreissen - im Fensterbetrieb gaebe es keinen Ort dafuer.
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

        def sprengt(_s):
            raise OSError("Protokoll kaputt")
        gui._append_to_log = sprengt
        gui._t = lambda k, **kw: ""
        gui._tk_fehler_melden(*self._ausnahme(ValueError, "Probe"))
        self.assertEqual(len(APP._LETZTE_FEHLER), 1)

    def test_ringspeicher_laeuft_nicht_ueber(self):
        for i in range(40):
            APP._fehler_festhalten("Probe", ValueError, ValueError(str(i)), None)
        self.assertEqual(len(APP._LETZTE_FEHLER), 20)

    def test_haken_werden_beim_start_gesetzt(self):
        quelle = QUELLDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("    multiprocessing.freeze_support()")
        block = quelle[anfang:anfang + 600]
        self.assertIn("_haken_setzen()", block,
                      "Die Haken muessen gleich beim Start stehen.")
        self.assertIn("self.root.report_callback_exception = self._tk_fehler_melden",
                      quelle)


class DiagnoseberichtTests(unittest.TestCase):
    """Der Bericht traegt jetzt auch Anzeige, Umgebung und Werkzeuge."""

    def _gui(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_theme = "dunkel"
        gui._current_language = "de"
        gui.is_fullscreen = False
        gui._bg_image_cache = None
        gui._sidebar_bg_image_cache = None
        gui.mkpfs_dir = ""
        gui._load_setting = lambda k, v=None: v
        return gui

    def test_umgebung_nennt_das_wesentliche(self):
        zeilen = "\n".join(self._gui()._diagnose_umgebung())
        for begriff in ("Gebaut als EXE", "Pillow", "tkinterdnd2",
                        "Drag & Drop aktiv", "Administratorrechte"):
            self.assertIn(begriff, zeilen)

    def test_werkzeuge_loesen_keine_suche_aus(self):
        # Ein frischer Suchlauf durchkaemmt alle Laufwerke - der Bericht
        # darf nicht minutenlang haengen.
        gui = self._gui()
        gerufen = []
        gui._find_filezilla = lambda: gerufen.append("suche")
        gui._find_filezilla_by_scan = lambda **k: gerufen.append("scan")
        gui._diagnose_werkzeuge()
        self.assertEqual(gerufen, [])

    def test_abschnitt_kann_scheitern_ohne_den_bericht_zu_kippen(self):
        quelle = QUELLDATEI.read_text(encoding="utf-8")
        anfang = quelle.index("report_section_display\", self._diagnose_anzeige)")
        block = quelle[anfang:anfang + 900]
        self.assertIn("except Exception as exc:", block)
        self.assertIn("Abschnitt fehlgeschlagen", block)

    def test_protokolldatei_wird_gelesen(self):
        zeilen = APP.PS5ConverterGUI._diagnose_protokolldatei(5)
        self.assertTrue(zeilen)
        self.assertLessEqual(len(zeilen), 5)

    def test_abschnitte_sind_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS

        for schluessel in ("diagnostics.report_section_display",
                           "diagnostics.report_section_runtime",
                           "diagnostics.report_section_tools",
                           "diagnostics.report_section_space",
                           "diagnostics.report_section_errors",
                           "diagnostics.report_section_logfile",
                           "log.unhandled_gui_error"):
            self.assertIn(schluessel, STRINGS)
            for sprache in ("de", "en"):
                self.assertTrue(STRINGS[schluessel].get(sprache), schluessel)


if __name__ == "__main__":
    unittest.main(verbosity=2)
