"""Regressionstests für das wählbare Hintergrundbild (Einstellungen-Dialog).

Deckt ab:
  1. Das Blenden mit der Design-Hintergrundfarbe nutzt genau BG_IMAGE_OPACITY.
  2. _apply_custom_background_image liest ein beliebiges Pillow-Format,
     wandelt es intern nach RGB um, speichert den Pfad dauerhaft und
     aktualisiert den Cache; ungültige Dateien liefern False statt zu crashen.
  3. _load_bg_image_cache bevorzugt einen gespeicherten eigenen Pfad vor dem
     eingebetteten Standardbild und ignoriert einen nicht mehr vorhandenen Pfad.
  4. Die dezente Kartentönung (bg_card/console_bg) für Bereiche, die das
     Hintergrundbild selbst nie zeigen (Quelle-Karte, Protokollfenster).
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

import PS5ImageConverter_Pro_FINAL_revised as mod
from PS5ImageConverter_Pro_FINAL_revised import BG_CARD_TINT_OPACITY, BG_IMAGE_OPACITY, PS5ConverterGUI


def _make_gui() -> PS5ConverterGUI:
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._COLORS = {"bg_main": "#101418"}
    settings: dict[str, object] = {}
    gui._load_setting = lambda key, default: settings.get(key, default)
    gui._save_setting = lambda key, value: settings.__setitem__(key, value)
    gui._settings_store = settings
    gui._refresh_bg_label = lambda: None  # Tkinter-Rendering ist nicht Gegenstand dieses Tests.
    gui._bg_image_cache = None
    return gui


class BlendBgImageTests(unittest.TestCase):
    def test_blend_uses_configured_opacity(self) -> None:
        gui = _make_gui()
        gui._COLORS = {"bg_main": "#000000"}
        source = Image.new("RGB", (4, 4), "#FFFFFF")

        blended = gui._blend_bg_image_with_theme(source)

        # Weiß (255) geblendet mit Schwarz (0) bei BG_IMAGE_OPACITY ergibt
        # ungefaehr 255 * BG_IMAGE_OPACITY pro Kanal (PIL.Image.blend-Formel).
        # PILs interne C-Rundung weicht von Pythons round() gelegentlich um
        # genau 1 ab (z. B. bei .75-Bruchteilen) -- Toleranz statt Exaktheit.
        expected = 255 * BG_IMAGE_OPACITY
        pixel = blended.getpixel((0, 0))
        for channel in pixel:
            self.assertLessEqual(abs(channel - expected), 1, f"Kanal {channel} weicht zu stark von {expected} ab")


class ApplyCustomBackgroundImageTests(unittest.TestCase):
    def test_accepts_png_converts_and_persists_path(self) -> None:
        with TemporaryDirectory() as td:
            img_path = Path(td) / "mein_hintergrund.png"
            Image.new("RGBA", (20, 12), (10, 20, 30, 128)).save(img_path)  # RGBA + Alpha bewusst als Stresstest

            gui = _make_gui()
            ok = gui._apply_custom_background_image(str(img_path))

            self.assertTrue(ok)
            self.assertIsNotNone(gui._bg_image_cache)
            self.assertEqual(gui._bg_image_cache.mode, "RGB")
            self.assertEqual(gui._settings_store.get("background_image_path"), os.path.abspath(str(img_path)))

    def test_accepts_bmp_format_too(self) -> None:
        with TemporaryDirectory() as td:
            img_path = Path(td) / "anderes_format.bmp"
            Image.new("RGB", (16, 16), (200, 50, 50)).save(img_path)

            gui = _make_gui()
            ok = gui._apply_custom_background_image(str(img_path))

            self.assertTrue(ok)
            self.assertEqual(gui._bg_image_cache.mode, "RGB")

    def test_rejects_non_image_file_without_crashing(self) -> None:
        with TemporaryDirectory() as td:
            fake_path = Path(td) / "kein_bild.txt"
            fake_path.write_text("das ist kein Bild", encoding="utf-8")

            gui = _make_gui()
            ok = gui._apply_custom_background_image(str(fake_path))

            self.assertFalse(ok)
            self.assertIsNone(gui._bg_image_cache)
            self.assertNotIn("background_image_path", gui._settings_store)


class LoadBgImageCacheTests(unittest.TestCase):
    def test_prefers_saved_custom_path_over_embedded_default(self) -> None:
        with TemporaryDirectory() as td:
            img_path = Path(td) / "custom.png"
            Image.new("RGB", (8, 8), (1, 2, 3)).save(img_path)

            gui = _make_gui()
            gui._settings_store["background_image_path"] = str(img_path)

            gui._load_bg_image_cache()

            self.assertIsNotNone(gui._bg_image_cache)
            # Bei (1, 2, 3) blended mit der Hintergrundfarbe bleibt der Kanalwert
            # winzig (weit unter 50) -- der eingebettete Standard ist deutlich heller/bunter.
            r, g, b = gui._bg_image_cache.getpixel((0, 0))
            self.assertLess(max(r, g, b), 50)

    def test_falls_back_to_default_when_saved_path_no_longer_exists(self) -> None:
        gui = _make_gui()
        gui._settings_store["background_image_path"] = r"C:\does\not\exist.png"

        gui._load_bg_image_cache()

        # Faellt auf mod._BG_IMAGE zurueck (das eingebettete Standardbild) --
        # solange dieses vorhanden ist, darf der Cache nicht None sein.
        if mod._BG_IMAGE:
            self.assertIsNotNone(gui._bg_image_cache)


class CardTintTests(unittest.TestCase):
    def test_average_image_rgb_on_solid_color(self) -> None:
        img = Image.new("RGB", (10, 10), (10, 20, 30))
        self.assertEqual(PS5ConverterGUI._average_image_rgb(img), (10, 20, 30))

    def test_blend_hex_color_matches_manual_math(self) -> None:
        result = PS5ConverterGUI._blend_hex_color("#101010", (200, 100, 50), 0.5)
        # 0x10 = 16; (16*0.5 + 200*0.5, 16*0.5 + 100*0.5, 16*0.5 + 50*0.5) = (108, 58, 33)
        self.assertEqual(result, "#6C3A21")

    def test_apply_card_tint_noop_without_bg_image(self) -> None:
        gui = _make_gui()
        gui._COLORS = {"bg_main": "#101418", "bg_card": "#1A1E24", "console_bg": "#0D1013"}
        gui._bg_image_cache = None

        gui._apply_card_tint_from_bg_image()

        self.assertEqual(gui._COLORS["bg_card"], "#1A1E24")
        self.assertEqual(gui._COLORS["console_bg"], "#0D1013")

    def test_apply_card_tint_shifts_colors_toward_image_average(self) -> None:
        gui = _make_gui()
        gui._COLORS = {"bg_main": "#101418", "bg_card": "#000000", "console_bg": "#000000"}
        gui._bg_image_cache = Image.new("RGB", (10, 10), (0, 255, 0))  # kraeftiges Gruen

        gui._apply_card_tint_from_bg_image()

        # Von reinem Schwarz aus muss die Toenung sichtbar Richtung Gruen wandern,
        # aber wegen BG_CARD_TINT_OPACITY (dezent) nicht bis zum vollen Gruenwert.
        # Karten und Protokollflaeche haben seit v1.8.60 getrennte
        # Deckkraft: Die Protokollflaeche ist gross und dauerhaft sichtbar,
        # was bei einer Karte dezent wirkt, ist dort zu wenig.
        #
        # Seit v1.9.0 haengt die Protokollflaeche am Schieberegler in den
        # Einstellungen; die Konstante ist nur noch seine Vorgabe. Gerechnet
        # wird deshalb mit dem Reglerwert - sonst weicht das Ergebnis um
        # 1/255 ab, weil ``1.0 - 0.7`` nicht exakt 0.3 ist.
        from PS5ImageConverter_Pro_FINAL_revised import REGLER_VORGABEN

        erwartet = {"bg_card": BG_CARD_TINT_OPACITY,
                    "console_bg": REGLER_VORGABEN["protokoll_deckkraft"] / 100}
        for key, anteil in erwartet.items():
            r, g, b = int(gui._COLORS[key][1:3], 16), int(gui._COLORS[key][3:5], 16), int(gui._COLORS[key][5:7], 16)
            self.assertEqual(r, 0)
            self.assertEqual(g, round(255 * anteil), key)
            self.assertEqual(b, 0)
            self.assertLess(g, 255 // 2,
                            "Toenung soll dezent bleiben, nicht das Bild ueberdecken")

    def test_apply_card_tint_live_handles_missing_console_view(self) -> None:
        gui = _make_gui()
        gui._COLORS = {"bg_main": "#101418", "bg_card": "#000000", "console_bg": "#000000"}
        gui._bg_image_cache = Image.new("RGB", (10, 10), (0, 255, 0))
        style_calls: list[bool] = []
        gui._setup_styles = lambda: style_calls.append(True)

        gui._apply_card_tint_live()  # darf ohne console_view/echtes Tk nicht crashen

        self.assertEqual(len(style_calls), 1)
        self.assertNotEqual(gui._COLORS["bg_card"], "#000000")


class GetrennteBilderlistenTests(unittest.TestCase):
    """Haupt- und Sidebar-Bilder stehen in getrennten Klapplisten.

    Unterschieden wird am Seitenverhältnis, nicht am Dateinamen: Die
    mitgelieferten Sidebar-Bilder heißen zwar alle ``s..``, ein selbst
    hinzugelegtes Bild aber nicht zwingend.
    """

    def setUp(self):
        self.ordner = TemporaryDirectory()
        self.addCleanup(self.ordner.cleanup)
        self._alt = PS5ConverterGUI._bundled_background_dir
        PS5ConverterGUI._bundled_background_dir = classmethod(
            lambda cls, _p=self.ordner.name: _p)
        self.addCleanup(setattr, PS5ConverterGUI, "_bundled_background_dir", self._alt)

    def _bild(self, name, groesse):
        pfad = os.path.join(self.ordner.name, name)
        Image.new("RGB", groesse, (10, 20, 30)).save(pfad)
        return pfad

    def test_querformat_gehoert_zum_hauptbereich(self):
        self._bild("weit.png", (1920, 1020))
        self._bild("hoch.png", (320, 1000))
        haupt = [os.path.basename(p) for p in PS5ConverterGUI._bundled_background_images("haupt")]
        self.assertEqual(haupt, ["weit.png"])

    def test_hochformat_gehoert_zur_sidebar(self):
        self._bild("weit.png", (1920, 1020))
        self._bild("hoch.png", (320, 1000))
        seite = [os.path.basename(p) for p in PS5ConverterGUI._bundled_background_images("sidebar")]
        self.assertEqual(seite, ["hoch.png"])

    def test_ohne_angabe_kommt_alles(self):
        self._bild("weit.png", (1920, 1020))
        self._bild("hoch.png", (320, 1000))
        self.assertEqual(len(PS5ConverterGUI._bundled_background_images()), 2)

    def test_dateiname_entscheidet_nicht(self):
        """Ein 's'-Name im Querformat gehört trotzdem in die Hauptliste."""
        self._bild("s99_irrefuehrend.png", (1920, 1020))
        haupt = [os.path.basename(p) for p in PS5ConverterGUI._bundled_background_images("haupt")]
        self.assertEqual(haupt, ["s99_irrefuehrend.png"])
        self.assertEqual(PS5ConverterGUI._bundled_background_images("sidebar"), [])

    def test_quadratisch_zaehlt_als_hauptbild(self):
        self._bild("quadrat.png", (800, 800))
        self.assertEqual(len(PS5ConverterGUI._bundled_background_images("haupt")), 1)
        self.assertEqual(PS5ConverterGUI._bundled_background_images("sidebar"), [])

    def test_unlesbare_datei_verschwindet_nicht(self):
        with open(os.path.join(self.ordner.name, "kaputt.png"), "wb") as datei:
            datei.write(b"kein Bild")
        self.assertEqual(
            [os.path.basename(p) for p in PS5ConverterGUI._bundled_background_images("haupt")],
            ["kaputt.png"])

    def test_mitgelieferte_bilder_teilen_sich_sauber_auf(self):
        """Gegenprobe am echten Ordner des Projekts.

        Bewusst ohne feste Anzahlen: Der Bilderbestand darf wachsen. Geprüft
        wird, dass jedes mitgelieferte Bild in genau einer Liste landet und die
        Zuordnung zum Format passt.
        """
        PS5ConverterGUI._bundled_background_dir = self._alt
        ordner = PS5ConverterGUI._bundled_background_dir()
        if not ordner or not os.path.isdir(ordner):
            self.skipTest("Ordner mit mitgelieferten Bildern nicht gefunden")
        haupt = PS5ConverterGUI._bundled_background_images("haupt")
        seite = PS5ConverterGUI._bundled_background_images("sidebar")
        alle = PS5ConverterGUI._bundled_background_images()
        self.assertTrue(haupt, "keine Bilder für den Hauptbereich")
        self.assertTrue(seite, "keine Bilder für die Seitenleiste")
        self.assertEqual(len(haupt) + len(seite), len(alle))
        self.assertEqual(set(haupt) & set(seite), set(), "Bild in beiden Listen")
        for pfad in haupt:
            with Image.open(pfad) as bild:
                breite, hoehe = bild.size
            self.assertGreaterEqual(breite, hoehe, f"{os.path.basename(pfad)} ist hoch")
        for pfad in seite:
            with Image.open(pfad) as bild:
                breite, hoehe = bild.size
            self.assertGreater(hoehe, breite, f"{os.path.basename(pfad)} ist quer")


class SidebarDeckkraftTests(unittest.TestCase):
    """Das Sidebar-Bild tritt weiter zurück als das Bild im Hauptbereich.

    Grund: Im Hauptbereich decken Karten (QUELLE, ZIELFORMAT, Protokoll) den
    größten Teil des Bildes ab. Die Seitenleiste hat keine solchen Flächen –
    dasselbe Mischverhältnis wirkt dort deutlich kräftiger.
    """

    def test_sidebar_ist_durchsichtiger(self):
        self.assertLess(mod.SIDEBAR_BG_IMAGE_OPACITY, BG_IMAGE_OPACITY)
        self.assertAlmostEqual(mod.SIDEBAR_BG_IMAGE_OPACITY, 0.50, places=2)

    # Image.blend schneidet den Nachkommateil ab, statt zu runden - deshalb
    # wird auf ein Pixel genau verglichen, nicht exakt.
    def test_blende_nimmt_eigene_deckkraft(self):
        gui = _make_gui()
        bild = Image.new("RGB", (4, 4), (255, 255, 255))
        gui._COLORS = dict(gui._COLORS, bg_main="#000000")
        voll = gui._blend_bg_image_with_theme(bild, 1.0).getpixel((0, 0))
        halb = gui._blend_bg_image_with_theme(bild, 0.5).getpixel((0, 0))
        self.assertEqual(voll, (255, 255, 255))
        self.assertAlmostEqual(halb[0], 255 * 0.5, delta=1)

    def test_ohne_angabe_gilt_der_hauptwert(self):
        gui = _make_gui()
        bild = Image.new("RGB", (4, 4), (255, 255, 255))
        gui._COLORS = dict(gui._COLORS, bg_main="#000000")
        gemessen = gui._blend_bg_image_with_theme(bild).getpixel((0, 0))[0]
        self.assertAlmostEqual(gemessen, 255 * BG_IMAGE_OPACITY, delta=1)

    def test_sidebar_cache_nutzt_den_eigenen_wert(self):
        # Geprueft wird die Absicht, nicht die Schreibweise: Die Sidebar muss
        # einen eigenen Wert uebergeben. Seit v1.8.52 waehlt sie zwischen dem
        # dunklen und dem hellen Wert, reicht ihn aber weiterhin als zweites
        # Argument herein - ohne das gaelte der Hauptwert, und die Sidebar
        # waere deutlich zu kraeftig.
        quelle = Path(mod.__file__).read_text(encoding="utf-8")
        stelle = quelle.index("def _load_sidebar_bg_image_cache")
        block = quelle[stelle:stelle + 1200]
        self.assertIn("SIDEBAR_BG_IMAGE_OPACITY", block)
        self.assertIn("SIDEBAR_BG_IMAGE_OPACITY_LIGHT", block)
        self.assertRegex(block, r"_blend_bg_image_with_theme\(img,\s*\w+\)")


class SpeichernKnopfTests(unittest.TestCase):
    """Speichern übernimmt auch eine noch nicht angewandte Listenauswahl.

    Wer in der Klappliste ein Bild wählt und direkt auf Speichern geht, ohne
    vorher „Ausgewähltes übernehmen" zu drücken, erwartet zu Recht, dass es
    übernommen wird. Ebenso wichtig ist der Gegenfall: Speichern ohne Änderung
    darf das aktive Bild nicht durch den ersten Listeneintrag ersetzen.
    """

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk
            cls.tk = tk
            cls.wurzel = tk._default_root or tk.Tk()
            cls.wurzel.withdraw()
        except Exception:                        # pragma: no cover
            raise unittest.SkipTest("keine Anzeige verfügbar")
        cls.app = mod.PS5ConverterGUI(cls.wurzel)

    def setUp(self):
        self.arbeit = TemporaryDirectory()
        self.addCleanup(self.arbeit.cleanup)
        self.konfig = os.path.join(self.arbeit.name, "paths.json")
        self.app._get_config_path = lambda: self.konfig

    def _schreibe(self, inhalt):
        import json
        with open(self.konfig, "w", encoding="utf-8") as datei:
            json.dump(inhalt, datei)

    def _lies(self):
        import json
        with open(self.konfig, encoding="utf-8") as datei:
            return json.load(datei)

    def _sammle(self, widget, art, treffer=None):
        treffer = [] if treffer is None else treffer
        for kind in widget.winfo_children():
            if kind.__class__.__name__ == art:
                treffer.append(kind)
            self._sammle(kind, art, treffer)
        return treffer

    def _dialog(self):
        self.app._show_settings_dialog()
        dlg = [k for k in self.wurzel.winfo_children()
               if isinstance(k, self.tk.Toplevel) and k.winfo_exists()][-1]
        dlg.update_idletasks()
        self.addCleanup(lambda: dlg.winfo_exists() and dlg.destroy())
        return dlg

    def _speichern(self, dlg):
        knopf = [b for b in self._sammle(dlg, "Button")
                 if "Speichern" in b.cget("text")]
        self.assertTrue(knopf, "kein Speichern-Knopf im Dialog")
        knopf[0].invoke()

    def test_listenauswahl_wird_beim_speichern_uebernommen(self):
        self._schreibe({})
        dlg = self._dialog()
        # Die beiden Bildlisten heraussuchen statt sie zu zaehlen: Der
        # Dialog hat seit v1.8.97 eine dritte Combobox (Farbsehschwaeche),
        # und die naechste kommt bestimmt. Erkennbar sind die richtigen an
        # ihrem Inhalt - dort stehen Bilddateien.
        endungen = mod.PS5ConverterGUI._BACKGROUND_EXTENSIONS
        boxen = [b for b in self._sammle(dlg, "Combobox")
                 if any(str(w).lower().endswith(endungen)
                        for w in (b.cget("values") or ()))]
        self.assertEqual(len(boxen), 2,
                         "erwartet: Haupt- und Sidebar-Bildliste")
        # Namen aus den Listen nehmen, nicht fest verdrahten - der
        # Bilderbestand darf sich aendern.
        haupt = boxen[0].cget("values")[-1]
        seite = boxen[1].cget("values")[-1]
        boxen[0].set(haupt)
        boxen[1].set(seite)
        self._speichern(dlg)
        gespeichert = self._lies()
        # Nicht auf die Schreibweise festlegen: Der gespeicherte Wert traegt
        # den Unterordner mit ("bundled:Main/..."), der Listeneintrag zeigt
        # nur den Dateinamen. Gemeint ist beides Mal dieselbe Datei - und
        # genau das wird geprueft.
        for schluessel, gewaehlt in (("background_image_path", haupt),
                                     ("sidebar_background_image_path", seite)):
            wert = gespeichert.get(schluessel, "")
            self.assertTrue(wert.startswith(
                mod.PS5ConverterGUI._BUNDLED_IMAGE_MARKER), wert)
            pfad = mod.PS5ConverterGUI._decode_background_setting(wert)
            self.assertTrue(pfad, "gespeicherter Wert nicht aufloesbar: %s" % wert)
            self.assertEqual(os.path.basename(pfad), os.path.basename(gewaehlt))

    def test_speichern_ohne_aenderung_laesst_alles_stehen(self):
        vorhandene = mod.PS5ConverterGUI._bundled_background_images
        # Bewusst ohne Unterordner: So sahen gespeicherte Werte frueher aus,
        # und sie muessen weiter greifen.
        vorher = {"background_image_path":
                  "bundled:" + os.path.basename(vorhandene("haupt")[-1]),
                  "sidebar_background_image_path":
                  "bundled:" + os.path.basename(vorhandene("sidebar")[-1])}
        self._schreibe(vorher)
        dlg = self._dialog()
        self._speichern(dlg)
        nachher = self._lies()
        for schluessel, wert in vorher.items():
            self.assertEqual(nachher.get(schluessel), wert)

    def test_klappliste_zeigt_das_aktive_bild(self):
        vorhandene = mod.PS5ConverterGUI._bundled_background_images
        haupt = os.path.basename(vorhandene("haupt")[-1])
        seite = os.path.basename(vorhandene("sidebar")[-1])
        self._schreibe({"background_image_path": f"bundled:{haupt}",
                        "sidebar_background_image_path": f"bundled:{seite}"})
        dlg = self._dialog()
        boxen = self._sammle(dlg, "Combobox")
        self.assertEqual(boxen[0].get(), haupt)
        self.assertEqual(boxen[1].get(), seite)


class DialogQuelltextTests(unittest.TestCase):
    """Der Einstellungsdialog bietet beide Listen an."""

    def test_speichern_knopf_vorhanden(self):
        self.assertIn("settings_dialog.save_button", self.quelle)
        anfang = self.quelle.index("def _speichern_und_schliessen")
        ende = self.quelle.index("close_row = tk.Frame(", anfang)
        block = self.quelle[anfang:ende]
        # Sichert alle drei im Dialog geführten Einstellungen und schließt.
        for schluessel in ("background_image_path", "sidebar_background_image_path",
                           "download_dir"):
            self.assertIn(schluessel, block)
        self.assertIn("dlg.destroy()", block)

    def test_speichern_uebernimmt_die_listenauswahl(self):
        """Sonst bliebe eine Auswahl ohne Klick auf „Übernehmen" wirkungslos."""
        anfang = self.quelle.index("def _speichern_und_schliessen")
        ende = self.quelle.index("close_row = tk.Frame(", anfang)
        block = self.quelle[anfang:ende]
        self.assertIn("_apply_custom_background_image", block)
        self.assertIn("_apply_custom_sidebar_background_image", block)
        # Vergleich gegen den Stand beim Öffnen, nicht gegen den ersten Eintrag.
        self.assertIn("haupt_beim_oeffnen", block)
        self.assertIn("sidebar_beim_oeffnen", block)

    @classmethod
    def setUpClass(cls):
        cls.quelle = Path(mod.__file__).read_text(encoding="utf-8")

    def test_hauptliste_zeigt_nur_querformate(self):
        self.assertIn('self._bundled_background_images("haupt")', self.quelle)

    def test_sidebar_hat_eine_eigene_liste(self):
        self.assertIn('self._bundled_background_images("sidebar")', self.quelle)
        self.assertIn("settings_dialog.sidebar_background_bundled_label", self.quelle)

    def test_sidebar_liste_uebernimmt_in_die_sidebar(self):
        stelle = self.quelle.index('self._bundled_background_images("sidebar")')
        block = self.quelle[stelle:stelle + 1800]
        self.assertIn("_apply_custom_sidebar_background_image", block)


class StandardHintergrundTests(unittest.TestCase):
    """Die beiden Vorgabebilder muessen es wirklich geben.

    Ein Tippfehler im Dateinamen faellt sonst nicht auf: Das Programm findet
    das Bild nicht, faengt die Ausnahme ab und zeigt einfach das eingebettete
    Bild - die Vorgabe waere still wirkungslos.
    """

    def test_vorgaben_zeigen_auf_vorhandene_bilder(self) -> None:
        for wert in (mod.STANDARD_HINTERGRUND, mod.STANDARD_SIDEBAR_HINTERGRUND):
            with self.subTest(wert=wert):
                pfad = mod.PS5ConverterGUI._decode_background_setting(wert)
                self.assertTrue(pfad, f"nicht aufloesbar: {wert}")
                self.assertTrue(os.path.isfile(pfad), f"Datei fehlt: {pfad}")

    def test_vorgaben_nutzen_die_bundled_schreibweise(self) -> None:
        """Ein absoluter Pfad zeigte aus der EXE in einen fluechtigen _MEI-Ordner."""
        marke = mod.PS5ConverterGUI._BUNDLED_IMAGE_MARKER
        for wert in (mod.STANDARD_HINTERGRUND, mod.STANDARD_SIDEBAR_HINTERGRUND):
            with self.subTest(wert=wert):
                self.assertTrue(wert.startswith(marke))

    def test_sidebar_vorgabe_stammt_aus_der_sidebar_liste(self) -> None:
        # Ueber den aufgeloesten Pfad vergleichen, nicht ueber den
        # Dateinamen: Die Vorgabe darf einen Unterordner tragen
        # ("bundled:Main/..."), die Liste liefert volle Pfade.
        pfad = mod.PS5ConverterGUI._decode_background_setting(mod.STANDARD_SIDEBAR_HINTERGRUND)
        self.assertTrue(pfad, "Vorgabe nicht aufloesbar: %s" % mod.STANDARD_SIDEBAR_HINTERGRUND)
        liste = mod.PS5ConverterGUI._bundled_background_images("sidebar")
        self.assertIn(os.path.normcase(pfad),
                      [os.path.normcase(x) for x in liste])

    def test_haupt_vorgabe_stammt_aus_der_hauptliste(self) -> None:
        # Ueber den aufgeloesten Pfad vergleichen, nicht ueber den
        # Dateinamen: Die Vorgabe darf einen Unterordner tragen
        # ("bundled:Main/..."), die Liste liefert volle Pfade.
        pfad = mod.PS5ConverterGUI._decode_background_setting(mod.STANDARD_HINTERGRUND)
        self.assertTrue(pfad, "Vorgabe nicht aufloesbar: %s" % mod.STANDARD_HINTERGRUND)
        liste = mod.PS5ConverterGUI._bundled_background_images("haupt")
        self.assertIn(os.path.normcase(pfad),
                      [os.path.normcase(x) for x in liste])

    def test_abwahl_wird_nicht_von_der_vorgabe_ueberstimmt(self) -> None:
        """Wer ausdruecklich kein Bild will, bekommt keins aufgedraengt.

        Die Einstellung wird ueber data.get(key, default) gelesen: Ein leerer
        Text steht in der Datei und gewinnt gegen die Vorgabe, die nur bei
        fehlendem Schluessel greift.
        """
        quelle = (Path(__file__).resolve().parent
                  / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn("return data.get(key, default)", quelle)
        # Und die Vorgabe darf nicht versehentlich beim Speichern landen
        self.assertIn('self._save_setting("background_image_path", "")', quelle)


class HellesDesignTests(unittest.TestCase):
    """Im hellen Design darf das dunkle Hintergrundbild nicht dominieren.

    Bis v1.8.51 galt BG_IMAGE_OPACITY fuer jedes Design. Im hellen blieb das
    (typischerweise dunkle) Bild damit zu 85 % stehen, waehrend Karten und
    Knoepfe hell sind - das Fenster zerfiel sichtbar in zwei Haelften, und
    Beschriftungen sassen je nach Stelle auf hellem oder dunklem Grund.
    """

    class _Attrappe:
        """Nur die Teile, die _blend_bg_image_with_theme wirklich anfasst."""

        _blend_bg_image_with_theme = mod.PS5ConverterGUI._blend_bg_image_with_theme

        def __init__(self, theme, bg_main):
            self._current_theme = theme
            self._COLORS = {"bg_main": bg_main}

    @staticmethod
    def _helligkeit(farbe):
        r, g, b = farbe
        return (r * 299 + g * 587 + b * 114) // 1000

    def _gemischt(self, theme, bg_main):
        from PIL import Image

        dunkles_bild = Image.new("RGB", (8, 8), (12, 14, 20))
        attrappe = self._Attrappe(theme, bg_main)
        return attrappe._blend_bg_image_with_theme(dunkles_bild).getpixel((0, 0))

    def test_heller_grund_bleibt_hell(self):
        # Der Kartengrund im hellen Design ist #FFFFFF. Liegt der Bildgrund
        # darunter bei Helligkeit 44, sieht das Fenster aus wie zwei Programme.
        farbe = self._gemischt("hell", "#E4EAF3")
        self.assertGreater(self._helligkeit(farbe), 150,
                           f"Hintergrund im hellen Design zu dunkel: {farbe}")

    def test_dunkles_design_unveraendert(self):
        farbe = self._gemischt("dunkel", "#05070A")
        self.assertLess(self._helligkeit(farbe), 40,
                        f"Hintergrund im dunklen Design zu hell: {farbe}")

    def test_eigene_deckkraft_hat_vorrang(self):
        # Die Sidebar reicht ihren eigenen Wert herein - der darf nicht vom
        # Design ueberschrieben werden.
        from PIL import Image

        bild = Image.new("RGB", (8, 8), (255, 255, 255))
        attrappe = self._Attrappe("hell", "#000000")
        farbe = attrappe._blend_bg_image_with_theme(bild, 1.0).getpixel((0, 0))
        self.assertEqual(farbe, (255, 255, 255))

    def test_konstanten_vorhanden(self):
        self.assertLess(mod.BG_IMAGE_OPACITY_LIGHT, mod.BG_IMAGE_OPACITY)
        self.assertLess(mod.SIDEBAR_BG_IMAGE_OPACITY_LIGHT,
                        mod.SIDEBAR_BG_IMAGE_OPACITY)


import io as _io_pruefung


class FormatfuellendTests(unittest.TestCase):
    """Hintergrundbilder werden beschnitten, nicht verzerrt.

    Gemeldet am 19.08.2026 an einem Mac mini: An einem grossen Monitor wird
    der Hintergrund im Vollbild verzerrt dargestellt und faengt sich erst
    danach wieder.
    """

    def _bild(self, breite, hoehe):
        # Ein Verlauf, an dem sich Stauchung nachweisen laesst.
        bild = Image.new("RGB", (breite, hoehe))
        for x in range(breite):
            for y in range(0, hoehe, max(1, hoehe // 8)):
                bild.putpixel((x, y), (x * 255 // max(1, breite - 1), 0, 0))
        return bild

    def test_masse_stimmen_immer_genau(self):
        # Der ganze Rest des Programms schneidet Ausschnitte aus dem
        # skalierten Bild. Weicht die Groesse auch nur um ein Pixel ab,
        # sitzen alle Beschriftungshintergruende falsch.

        master = self._bild(1920, 1080)
        for breite, hoehe in ((1366, 820), (3440, 1440), (800, 1200),
                              (1920, 1080), (17, 5), (1, 1)):
            ergebnis = PS5ConverterGUI._bild_fuellen(master, breite, hoehe)
            self.assertEqual(ergebnis.size, (breite, hoehe),
                             "Zielmasse verfehlt bei %dx%d" % (breite, hoehe))

    def test_gleiches_seitenverhaeltnis_bleibt_unveraendert(self):
        # Der Normalfall: Die mitgelieferten Bilder passen zum Fensterformat.
        # Dort darf sich gegenueber der bisherigen Fassung nichts aendern.
        from PS5ImageConverter_Pro_FINAL_revised import _LANCZOS

        master = self._bild(1920, 1080)
        neu = PS5ConverterGUI._bild_fuellen(master, 960, 540)
        alt = master.resize((960, 540), _LANCZOS)
        self.assertEqual(list(neu.getdata()), list(alt.getdata()),
                         "Bei passendem Format muss das Ergebnis identisch sein")

    def test_breites_ziel_wird_beschnitten_nicht_gestaucht(self):

        # Ein quadratisches Master auf ein sehr breites Ziel.
        master = self._bild(1000, 1000)
        ergebnis = PS5ConverterGUI._bild_fuellen(master, 1000, 250)
        self.assertEqual(ergebnis.size, (1000, 250))
        # Beschnitten heisst: die Breite wurde NICHT gestaucht. Die
        # Farbe waechst weiterhin von links nach rechts ueber den vollen
        # Bereich - bei einer Stauchung waere sie zusammengedraengt.
        links = ergebnis.getpixel((0, 0))[0]
        rechts = ergebnis.getpixel((999, 0))[0]
        self.assertLess(links, 20)
        self.assertGreater(rechts, 235)

    def test_hohes_ziel_wird_beschnitten(self):

        master = self._bild(1000, 1000)
        ergebnis = PS5ConverterGUI._bild_fuellen(master, 250, 1000)
        self.assertEqual(ergebnis.size, (250, 1000))
        # Mittig beschnitten: Der linke Rand zeigt nicht mehr den
        # Bildanfang, sondern etwa das erste Viertel.
        self.assertGreater(ergebnis.getpixel((0, 0))[0], 60)

    def test_kein_resize_mehr_ohne_den_helfer(self):
        # Faellt eine Stelle zurueck auf master.resize((w, h)), verzerrt
        # genau sie wieder - und niemand sieht es auf einem 16:9-Schirm.
        quelle = _io_pruefung.open(mod.__file__, encoding="utf-8").read()
        # _bg_image_raw gehoert dazu: Die Karte zeichnet ihren Untergrund
        # daraus. Die erste Fassung dieses Tests liess ihn aus, und genau
        # dort blieb resize() stehen - die Karte zeigte einen anderen
        # Ausschnitt als ihre Umgebung (gemeldet 19.08.2026, v1.8.60).
        for name in ("_bg_image_cache", "_sidebar_bg_image_cache", "_bg_image_raw"):
            self.assertNotIn("self.%s.resize(" % name, quelle,
                             "Diese Stelle umgeht _bild_fuellen und verzerrt.")

    def test_vollbild_ist_keine_ausnahme_mehr(self):
        # Im Vollbild wurde das Hintergrundbild gar nicht angepasst, waehrend
        # Inhaltsflaeche, Seitenleiste und Karten ihre Bilder nachzogen.
        quelle = _io_pruefung.open(mod.__file__, encoding="utf-8").read()
        self.assertNotIn("if not self._bg_image_cache or self.is_fullscreen:", quelle,
                         "Das Hintergrundbild wird im Vollbild wieder uebersprungen.")


class KnopfleisteDeckkraftTests(unittest.TestCase):
    """Die Knopfleiste zeigt das Hintergrundbild nur gedaempft.

    Gemeldet am 19.08.2026 mit einem Bildausschnitt der Leiste, in der
    "STARTEN", "ABBRECHEN" und die Groessenanzeige stehen: Das Motiv war
    dort unveraendert zu sehen und wirkte neben der Karte darueber wie
    gespiegelt. Wie bei der Protokollflaeche traegt jetzt die Flaechenfarbe.
    """

    def test_konstante_steht_auf_siebzig_prozent(self):
        self.assertAlmostEqual(mod.ACTION_BAR_DECKKRAFT, 0.70, places=4)

    def test_flaechenfarbe_traegt(self):
        gui = _make_gui()
        gui._COLORS = {"bg_main": "#000000"}
        quelle = Image.new("RGB", (4, 4), "#FFFFFF")

        ergebnis = gui._blend_bg_image_for_action_bar(quelle)

        # Schwarze Flaeche, weisses Bild: Uebrig bleiben die 30 %, die das
        # Bild noch beitragen darf.
        erwartet = 255 * (1.0 - mod.ACTION_BAR_DECKKRAFT)
        for kanal in ergebnis.getpixel((0, 0)):
            self.assertLessEqual(abs(kanal - erwartet), 1,
                                 "Kanal %d weicht zu stark von %.1f ab" % (kanal, erwartet))

    def test_jede_zeichenstelle_mischt(self):
        # Es gibt zwei Stellen, die das Bild der Leiste setzen. Die erste
        # Fassung dieses Fixes traf nur eine davon -- beim Vergroessern des
        # Fensters waere das Motiv zurueckgekommen.
        zeilen = _io_pruefung.open(mod.__file__, encoding="utf-8").read().splitlines()
        stellen = [i for i, z in enumerate(zeilen)
                   if "action_bar_bg_photo = ImageTk.PhotoImage(" in z]
        self.assertGreaterEqual(len(stellen), 2,
                                "Weniger Zeichenstellen als erwartet -- Test pruefen.")
        for i in stellen:
            umfeld = " ".join(zeilen[max(0, i - 3):i + 3])
            self.assertIn("_blend_bg_image_for_action_bar", umfeld,
                          "Zeile %d setzt das Bild ungemischt." % (i + 1))


class FlaechenbildMerkerTests(unittest.TestCase):
    """Der Merker vor ``_bild_fuellen`` darf am Ergebnis nichts aendern.

    Bis v1.8.65 skalierte ``_compute_content_bg_crop`` fuer **jede einzelne**
    Beschriftung das komplette Hintergrundbild neu, nur um daraus ein paar
    hundert Pixel auszuschneiden. Bei laufender Aufgabe wechseln Status- und
    Telemetriezeile mehrmals je Sekunde. Der Merker spart diese Durchlaeufe -
    und muss dabei Pixel fuer Pixel dasselbe liefern wie vorher.
    """

    def _bild(self, breite=640, hoehe=400):
        bild = Image.new("RGB", (breite, hoehe))
        for x in range(breite):
            for y in range(hoehe):
                bild.putpixel((x, y), (x % 256, y % 256, (x + y) % 256))
        return bild

    def test_ergebnis_ist_pixelgleich_zu_bild_fuellen(self):
        gui = _make_gui()
        master = self._bild()
        for breite, hoehe in ((1366, 820), (3440, 1440), (500, 900)):
            gemerkt = gui._flaechenbild(master, breite, hoehe)
            direkt = PS5ConverterGUI._bild_fuellen(master, breite, hoehe)
            self.assertEqual(gemerkt.size, (breite, hoehe))
            self.assertEqual(list(gemerkt.getdata()), list(direkt.getdata()),
                             "Merker liefert ein anderes Bild bei %dx%d" % (breite, hoehe))

    def test_zweiter_aufruf_rechnet_nicht_neu(self):
        gui = _make_gui()
        master = self._bild()
        erst = gui._flaechenbild(master, 800, 600)
        self.assertIs(gui._flaechenbild(master, 800, 600), erst)
        # Andere Masse sind ein anderer Eintrag.
        self.assertIsNot(gui._flaechenbild(master, 801, 600), erst)

    def test_neues_hintergrundbild_liefert_neues_ergebnis(self):
        """Ein PIL-Bild taugt nicht als Schluessel - die id() koennte wandern."""
        gui = _make_gui()
        eins = Image.new("RGB", (64, 64), (255, 0, 0))
        zwei = Image.new("RGB", (64, 64), (0, 255, 0))
        rot = gui._flaechenbild(eins, 32, 32)
        gruen = gui._flaechenbild(zwei, 32, 32)
        self.assertEqual(rot.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(gruen.getpixel((0, 0)), (0, 255, 0))

    def test_ohne_quelle_oder_masse_kein_absturz(self):
        gui = _make_gui()
        self.assertIsNone(gui._flaechenbild(None, 100, 100))
        self.assertIsNone(gui._flaechenbild(self._bild(), 0, 100))
        self.assertIsNone(gui._flaechen_ausschnitt(None, None, (0, 0), 10, 10))


if __name__ == "__main__":
    unittest.main()
