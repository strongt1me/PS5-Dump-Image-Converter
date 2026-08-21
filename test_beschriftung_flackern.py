# -*- coding: utf-8 -*-
"""Tests gegen flackernde Beschriftungen auf dem Hintergrundbild.

Hintergrund (Bildschirmaufnahme vom 16.08.2026): Während einer laufenden
Aufgabe zuckte die Statuszeile unten rechts (*„Aufgabe 8/8: Validierung
[1.9 GB/2.5 GB]"*) sichtbar.

Ursache war das Vermessen selbst. Die drei ``_redraw_*_captions`` legen jeder
Beschriftung einen passenden Ausschnitt des Hintergrundbilds unter. Dafür
mussten sie deren natürliche Größe kennen – und holten sie sich, indem sie am
**sichtbaren** Label den Ausschnitt entfernten und mit ``update_idletasks()``
ein Neuzeichnen erzwangen:

    label.config(image="")
    label.update_idletasks()          # zeichnet einmal OHNE Hintergrund
    natural_size = (label.winfo_reqwidth(), label.winfo_reqheight())

Bei laufender Aufgabe ändert sich der Statustext mehrmals je Sekunde, jedes Mal
wurde neu vermessen – das war das Flackern.

Gemessen wird jetzt an einem unsichtbaren Zwillingslabel. Zwei Dinge müssen
dabei stimmen, und genau die prüfen diese Tests:

1. Der Ausschnitt darf am sichtbaren Label nie mehr verschwinden.
2. Die Maße müssen exakt dieselben bleiben – sonst säße der Ausschnitt versetzt.

Ohne verfügbare Anzeige werden die Tests übersprungen.
"""
import io
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

try:
    import tkinter as tk
    TK_DA = True
except Exception:                             # pragma: no cover
    TK_DA = False


def _wurzel_holen():
    """Tk-Wurzel erst beim Testlauf anlegen, nicht beim Import.

    Beim Import angelegt, kaeme sie anderen Testdateien zuvor, die ihrerseits
    ``tk.Tk()`` aufrufen - ein zweiter Interpreter im selben Prozess kann die
    Bilder des ersten nicht verwenden ("image ... doesn't exist").
    """
    wurzel = tk._default_root or tk.Tk()
    try:
        wurzel.attributes("-alpha", 0.0)      # sichtbar für Tk, unsichtbar für den Nutzer
    except tk.TclError:
        pass
    return wurzel


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


@unittest.skipUnless(TK_DA, "keine Anzeige verfügbar")
class BeschriftungMessungTests(unittest.TestCase):
    """Am laufenden Tk-Baum - nur dort zeigt sich das Verhalten."""

    @classmethod
    def setUpClass(cls):
        haupt = _lade_hauptprogramm()
        cls.wurzel = _wurzel_holen()
        # Das Fenster muss abgebildet sein, sonst meldet winfo_ismapped()
        # fuer jede Beschriftung False und die Tests uebersprangen sich
        # selbst. Andere Testdateien ziehen die gemeinsame Wurzel zurueck
        # (withdraw); im Gesamtlauf vom 21.08.2026 kamen dadurch 6 statt 3
        # Uebersprungene heraus - je nach Reihenfolge. Dank -alpha 0.0 aus
        # _wurzel_holen bleibt es dabei fuer den Nutzer unsichtbar.
        cls._war_zurueckgezogen = cls.wurzel.state() == "withdrawn"
        cls.wurzel.deiconify()
        cls.app = haupt.PS5ConverterGUI(cls.wurzel)
        cls.wurzel.update()

    @classmethod
    def tearDownClass(cls):
        """Den Zustand hinterlassen, wie er vorgefunden wurde."""
        if getattr(cls, "_war_zurueckgezogen", False):
            try:
                cls.wurzel.withdraw()
            except Exception:
                pass

    def _beschriftungen(self, gruppe):
        return [l for l in getattr(self.app, gruppe, [])
                if l.winfo_exists() and l.winfo_ismapped()]

    def _hintergrundbild_sicherstellen(self):
        """Sorgt fuer ein Bild im Cache, statt sich zu ueberspringen.

        ``_bg_image_cache`` haengt daran, welches Hintergrundbild der Nutzer
        gewaehlt hat. Der Flackertest prueft aber das Zeichnen, nicht die
        Bildauswahl - er soll also mit irgendeinem mitgelieferten Bild
        laufen. Uebersprungen wird nur noch, wenn wirklich keines beiliegt;
        das waere ein echter Mangel an der Auslieferung.
        """
        if self.app._bg_image_cache is not None:
            return
        from PIL import Image
        ordner = os.path.join(os.path.dirname(HAUPTDATEI), "Hintergrundbilder")
        if not os.path.isdir(ordner):
            self.skipTest("Ordner Hintergrundbilder fehlt")
        # Kein fester Dateiname: Der Bestand aendert sich mit den Ausgaben.
        bilder = sorted(n for n in os.listdir(ordner)
                        if n.lower().endswith((".png", ".jpg", ".jpeg")))
        if not bilder:
            self.skipTest("keine mitgelieferten Hintergrundbilder")
        self.app._bg_image_cache = Image.open(
            os.path.join(ordner, bilder[0])).convert("RGB")

    def _alle(self):
        treffer = []
        for gruppe in ("_content_caption_labels", "_card_caption_labels",
                       "_sidebar_caption_labels"):
            treffer += self._beschriftungen(gruppe)
        return treffer

    def test_messung_stimmt_mit_der_alten_ueberein(self):
        """Sonst säße der Bildausschnitt versetzt hinter der Schrift."""
        beschriftungen = self._alle()
        if not beschriftungen:
            self.skipTest("keine abgebildeten Beschriftungen")
        abweichungen = []
        for ziel in beschriftungen:
            self.app._make_caption_borderless(ziel)
            for text in ("Aufgabe 8/8: Validierung [1.9 GB/2.5 GB]",
                         "Bereit", "QUELLE", "Phase 3/4"):
                ziel.config(text=text)
                neu = self.app._caption_natuerliche_groesse(ziel)
                gemerkt = ziel.cget("image")
                ziel.config(image="")
                ziel.update_idletasks()
                alt = (max(1, ziel.winfo_reqwidth()), max(1, ziel.winfo_reqheight()))
                if gemerkt:
                    ziel.config(image=gemerkt)
                if neu != alt:
                    abweichungen.append((text, neu, alt))
        self.assertEqual(abweichungen, [], f"Maße weichen ab: {abweichungen[:3]}")

    def test_ausschnitt_verschwindet_bei_textwechsel_nicht(self):
        """Der eigentliche Flackertest: 40 Textwechsel, immer hinterlegt."""
        self._hintergrundbild_sicherstellen()
        ziele = self._beschriftungen("_content_caption_labels")
        if not ziele:
            self.skipTest("keine abgebildeten Beschriftungen")
        self.app._redraw_content_captions()
        ohne = 0
        for i in range(40):
            for ziel in ziele:
                ziel.config(text=f"Aufgabe 8/8: Validierung [{1.0 + i * 0.03:.2f} GB/2.5 GB]")
            self.app._redraw_content_captions()
            ohne += sum(1 for ziel in ziele if not str(ziel.cget("image")))
        self.assertEqual(ohne, 0, f"{ohne} Mal ohne Hintergrundausschnitt gezeichnet")

    def test_zwilling_wird_nie_angezeigt(self):
        beschriftungen = self._alle()
        if not beschriftungen:
            self.skipTest("keine abgebildeten Beschriftungen")
        self.app._caption_natuerliche_groesse(beschriftungen[0])
        zwillinge = getattr(self.app, "_caption_mess_labels", {})
        self.assertTrue(zwillinge, "kein Zwillingslabel angelegt")
        for mess in zwillinge.values():
            self.assertFalse(mess.winfo_ismapped(), "Messlabel ist sichtbar")
            self.assertEqual(mess.winfo_manager(), "", "Messlabel wurde eingehängt")

    def test_zwilling_je_widgetklasse(self):
        """ttk- und tk-Labels brauchen verschiedene Zwillinge."""
        klassen = {type(l) for l in self._alle()}
        for ziel in self._alle():
            self.app._caption_natuerliche_groesse(ziel)
        zwillinge = getattr(self.app, "_caption_mess_labels", {})
        self.assertEqual(set(zwillinge), klassen)


class QuelltextTests(unittest.TestCase):
    """Das alte Messverfahren darf nicht zurückkehren."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as datei:
            cls.quelle = datei.read()

    def test_kein_erzwungenes_neuzeichnen_beim_vermessen(self):
        self.assertNotIn("label.update_idletasks()", self.quelle)

    def test_alle_drei_gruppen_messen_am_zwilling(self):
        # Bis zur nächsten Methode schneiden: Die Dokumentation von
        # _redraw_card_captions ist länger als ein fester Ausschnitt.
        for name in ("_redraw_content_captions", "_redraw_card_captions",
                     "_redraw_sidebar_captions"):
            anfang = self.quelle.index(f"def {name}")
            ende = self.quelle.index("\n    def ", anfang + 10)
            block = self.quelle[anfang:ende]
            self.assertIn("_caption_natuerliche_groesse(label)", block,
                          f"{name} misst noch am sichtbaren Label")


if __name__ == "__main__":
    unittest.main(verbosity=2)
