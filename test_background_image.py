"""Regressionstests für das wählbare Hintergrundbild (Einstellungen-Dialog).

Deckt ab:
  1. _apply_custom_background_image liest ein beliebiges Pillow-Format,
     wandelt es intern nach RGB um, speichert den Pfad dauerhaft und
     aktualisiert den Cache; ungültige Dateien liefern False statt zu crashen.
  2. _load_bg_image_cache bevorzugt einen gespeicherten eigenen Pfad vor dem
     eingebetteten Standardbild und ignoriert einen nicht mehr vorhandenen Pfad.
  3. Die Aufteilung in Haupt- und Seitenleistenbilder, der Speichern-Knopf
     und das formatfüllende Skalieren.

Was hier **nicht** mehr steht: Die fünf Effektschichten auf dem Bild
(Helligkeit, Kontrast, Einmischung der Designfarbe, Deckkraft unter Karten
und Knopfleiste, Kartentönung) sind auf Wunsch des Nutzers ausgebaut. Das
Bild wird gezeigt, nicht nachgebildet. Dass sie nicht zurückkommen, sichert
``KeineBildeffekteTests`` weiter unten.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

import PS5ImageConverter_Pro_FINAL_revised as mod
from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI


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
        boxen = [b for b in self._sammle(dlg, "Combobox")
                 if any(str(w).lower().endswith(".png")
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
        self.assertEqual(gespeichert.get("background_image_path"), f"bundled:{haupt}")
        self.assertEqual(gespeichert.get("sidebar_background_image_path"),
                         f"bundled:{seite}")

    def test_speichern_ohne_aenderung_laesst_alles_stehen(self):
        vorhandene = mod.PS5ConverterGUI._bundled_background_images
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
        marke = mod.PS5ConverterGUI._BUNDLED_IMAGE_MARKER
        name = mod.STANDARD_SIDEBAR_HINTERGRUND[len(marke):]
        namen = [os.path.basename(x) for x
                 in mod.PS5ConverterGUI._bundled_background_images("sidebar")]
        self.assertIn(name, namen)

    def test_haupt_vorgabe_stammt_aus_der_hauptliste(self) -> None:
        marke = mod.PS5ConverterGUI._BUNDLED_IMAGE_MARKER
        name = mod.STANDARD_HINTERGRUND[len(marke):]
        namen = [os.path.basename(x) for x
                 in mod.PS5ConverterGUI._bundled_background_images("haupt")]
        self.assertIn(name, namen)

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

class FarbrechnungTests(unittest.TestCase):
    """``_blend_hex_color`` bleibt - es ist reine Farbrechnung ohne Bild.

    Zwei Stellen brauchen es weiterhin: die Fuellung der Eingabefelder
    (Karte in Richtung Fensterhintergrund verschoben) und die
    Fokus-Hervorhebung. Beide haben mit dem Hintergrundbild nichts zu tun -
    beim Ausbau der Bildeffekte waere der Helfer sonst mitgegangen.
    """

    def test_blend_hex_color_matches_manual_math(self) -> None:
        result = PS5ConverterGUI._blend_hex_color("#101010", (200, 100, 50), 0.5)
        # 0x10 = 16; (16*0.5 + 200*0.5, 16*0.5 + 100*0.5, 16*0.5 + 50*0.5) = (108, 58, 33)
        self.assertEqual(result, "#6C3A21")


class KeineBildeffekteTests(unittest.TestCase):
    """Die ausgebauten Effekte duerfen nicht zurueckkehren.

    Fuenf Schichten lagen auf dem Hintergrundbild: Helligkeit und Kontrast
    ueber PIL, eine Einmischung der Designfarbe, je eine eigene Deckkraft
    unter Karten und Knopfleiste, und eine Toenung der Kartenfarben zur
    Durchschnittsfarbe des Bildes. Zusammen sorgten sie dafuer, dass nie das
    gewaehlte Bild zu sehen war, sondern dessen Nachbildung - und drei
    Regler wirkten auf dieselbe Stelle.

    Geprueft wird die **Abwesenheit**, und zwar an drei Merkmalen: den
    Methoden, den Konstanten und dem Aufruf, der die Einmischung machte.
    """

    ENTFERNTE_METHODEN = (
        "_blend_bg_image_with_theme",
        "_blend_bg_image_for_card",
        "_blend_bg_image_for_action_bar",
        "_bild_regler_anwenden",
        "_apply_card_tint_from_bg_image",
        "_average_image_rgb",
        "_regler",
        "_regler_anteil",
        "_regler_uebernehmen",
    )

    ENTFERNTE_KONSTANTEN = (
        "BG_IMAGE_OPACITY", "BG_IMAGE_OPACITY_LIGHT",
        "SIDEBAR_BG_IMAGE_OPACITY", "SIDEBAR_BG_IMAGE_OPACITY_LIGHT",
        "BG_CARD_TINT_OPACITY", "BG_CARD_IMAGE_OPACITY",
        "BG_CARD_IMAGE_OPACITY_LIGHT", "ACTION_BAR_DECKKRAFT",
        "CONSOLE_BG_DECKKRAFT", "CONTENT_CAPTION_BACKDROP_OPACITY",
        "REGLER_VORGABEN", "REGLER_GRENZEN",
    )

    def test_keine_der_methoden_ist_zurueck(self) -> None:
        zurueck = [m for m in self.ENTFERNTE_METHODEN
                   if hasattr(PS5ConverterGUI, m)]
        self.assertEqual([], zurueck, "Wieder da: %s" % zurueck)

    def test_keine_der_konstanten_ist_zurueck(self) -> None:
        zurueck = [k for k in self.ENTFERNTE_KONSTANTEN if hasattr(mod, k)]
        self.assertEqual([], zurueck, "Wieder da: %s" % zurueck)

    def test_das_bild_wird_nicht_mehr_eingemischt(self) -> None:
        """``Image.blend`` war das Werkzeug aller fuenf Schichten."""
        quelle = Path(mod.__file__).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("Image.blend(", quelle,
                         "Es wird wieder ein Bild eingemischt.")

    def test_pil_effektmodule_sind_nicht_mehr_eingebunden(self) -> None:
        """Ohne Helligkeit und Kontrast braucht es ImageEnhance nicht mehr."""
        quelle = Path(mod.__file__).read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("ImageEnhance", quelle)
        self.assertNotIn("ImageStat", quelle)

    def test_die_pruefung_wuerde_eine_rueckkehr_melden(self) -> None:
        """Gegenprobe - sonst pruefte sie nur, dass Erfundenes fehlt."""
        self.assertTrue(hasattr(PS5ConverterGUI, "_blend_hex_color"),
                        "Der Farbhelfer fehlt - dann misst der Test oben nichts.")
