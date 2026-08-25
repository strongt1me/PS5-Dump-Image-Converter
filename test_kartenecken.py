# -*- coding: utf-8 -*-
"""Die Karten im Hauptbereich haben runde Ecken.

Tk kennt keine runden Ecken; ein Frame ist immer ein Rechteck. Gelöst ist
das über vier kleine Bilder auf den Ecken, jedes aus **zwei** Quellen
zusammengesetzt: außerhalb des Viertelkreises der Bildausschnitt, der
*hinter* der Karte liegt, innerhalb die Kartenfläche selbst. Weil beide aus
demselben Bild stammen, sitzt der Übergang nahtlos - die Ecke sieht
weggeschnitten aus, nicht überklebt.

**Was hier geprüft wird, ist nicht „sieht rund aus".** Geprüft werden die
Pixel: In der äußersten Ecke muss der Hintergrund stehen, schräg gegenüber
die Kartenfläche. Sind beide gleich, ist nichts rund geworden - genau das
wäre der stille Ausfall, wenn eine der beiden Quellen fehlschlägt.

**Die Transparenzfalle.** ``Image.composite`` verlangt gleiche Bildmodi.
Das Hintergrundbild wird beim Laden zwar mit ``convert("RGB")``
flachgelegt, aber ein einziger RGBA-Weg irgendwo wäre ein stiller Ausfall
der Ecken statt einer runden Karte. Deshalb bringt die Rundung beide
Quellen selbst auf RGB - und dieser Test hält das fest.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"
QUELLE = HAUPTDATEI.read_text(encoding="utf-8")

#: Ab diesem Abstand (Summe über R, G und B, Spanne 0-765) gelten zwei
#: Farben als unterscheidbar. Kleiner heißt: die Ecke zeigt dasselbe wie
#: die Fläche, es ist also nichts weggeschnitten worden.
MINDESTABSTAND = 8


def _lade_hauptprogramm():
    import importlib.util
    spec = importlib.util.spec_from_file_location("hp_ecken", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("hp_ecken", modul)
    spec.loader.exec_module(modul)
    return modul


class MaskenTests(unittest.TestCase):
    """Die Viertelkreis-Maske - ohne Fenster prüfbar."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI.__new__(cls.haupt.PS5ConverterGUI)

    def test_jede_ecke_zeigt_in_ihre_richtung(self) -> None:
        """Der gefüllte Viertelkreis muss zur Kartenmitte zeigen.

        Zeigte er nach außen, wäre die Ecke nicht weggeschnitten, sondern
        alles andere - die Karte hätte dann vier Nasen statt runder Ecken.
        """
        r = 16
        # Je Ecke: (Punkt ganz außen, Punkt schräg gegenüber = innen)
        erwartung = {
            "ol": ((0, 0), (r - 1, r - 1)),
            "or": ((r - 1, 0), (0, r - 1)),
            "ul": ((0, r - 1), (r - 1, 0)),
            "ur": ((r - 1, r - 1), (0, 0)),
        }
        for ecke, (aussen, innen) in erwartung.items():
            with self.subTest(ecke=ecke):
                maske = self.app._eckmaske(ecke, r)
                self.assertEqual(maske.size, (r, r))
                self.assertLess(maske.getpixel(aussen), 40,
                                "%s: außen muss Hintergrund sein" % ecke)
                self.assertGreater(maske.getpixel(innen), 215,
                                   "%s: innen muss Kartenfläche sein" % ecke)

    def test_die_kante_ist_weich(self) -> None:
        """Ohne Überabtastung stünde die Rundung als Treppe da."""
        maske = self.app._eckmaske("ol", 16)
        werte = {maske.getpixel((x, y)) for x in range(16) for y in range(16)}
        zwischen = [w for w in werte if 40 < w < 215]
        self.assertTrue(zwischen,
                        "keine Zwischenwerte - die Kante ist nicht geglättet")

    def test_radius_ist_gemeinsam_festgelegt(self) -> None:
        self.assertGreaterEqual(self.haupt.PS5ConverterGUI._KARTEN_ECKE, 8)
        self.assertGreater(self.haupt.PS5ConverterGUI._ECKE_FEIN, 1)


class QuelltextTests(unittest.TestCase):
    """Zusagen, die im Quelltext stehen müssen."""

    def test_beide_karten_werden_gerundet(self) -> None:
        anfang = QUELLE.index("def _karten_ecken_nachziehen")
        rumpf = QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]
        self.assertIn("path_card", rumpf)
        self.assertIn("console_frame", rumpf)

    def test_beide_quellen_werden_auf_rgb_gebracht(self) -> None:
        """Sonst wirft ``composite`` bei einem RGBA-Bild - stiller Ausfall."""
        anfang = QUELLE.index("def _kartenecken_runden")
        rumpf = QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]
        self.assertIn('hinten.convert("RGB")', rumpf)
        self.assertIn('vorn.convert("RGB")', rumpf)

    def test_der_designwechsel_zieht_nach(self) -> None:
        """Die Ecken tragen Bildausschnitte - nach dem Wechsel stimmen die
        alten nicht mehr."""
        anfang = QUELLE.index("def _apply_theme")
        rumpf = QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]
        self.assertIn("_karten_ecken_planen", rumpf)

    def test_die_anforderungen_werden_gebuendelt(self) -> None:
        """Beim Ziehen am Fensterrand kommen dutzende Configure-Ereignisse."""
        anfang = QUELLE.index("def _karten_ecken_planen")
        rumpf = QUELLE[anfang:QUELLE.index(chr(10) + "    def ", anfang + 10)]
        self.assertIn("after_cancel", rumpf)
        self.assertIn("self.root.after(", rumpf)


class WidgetbaumTests(unittest.TestCase):
    """Der eigentliche Beweis: am laufenden Fenster abgelesen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()
        import tkinter as tk
        try:
            cls.wurzel = tk._default_root or tk.Tk()
        except Exception as exc:                       # pragma: no cover
            raise unittest.SkipTest("keine Anzeige: %s" % exc) from exc
        cls.wurzel.geometry("1280x860")
        for n in ("showinfo", "showwarning", "showerror", "askyesno"):
            setattr(cls.haupt.messagebox, n, lambda *a, **k: False)
        cls.app = cls.haupt.PS5ConverterGUI(cls.wurzel)
        cls.wurzel.update_idletasks()
        cls.wurzel.update()
        cls.app._karten_ecken_nachziehen()
        cls.wurzel.update_idletasks()
        cls.wurzel.update()

    @classmethod
    def tearDownClass(cls) -> None:
        # Die Wurzel NICHT zerstören - eine Tk-Wurzel je Prozess.
        try:
            cls.wurzel.withdraw()
        except Exception:
            pass

    def _punkt(self, foto, x, y):
        roh = self.wurzel.tk.call(str(foto), "get", x, y)
        if isinstance(roh, str):
            return tuple(int(v) for v in roh.split())
        return tuple(int(v) for v in roh)

    def _karte(self, name):
        karte = getattr(self.app, name, None)
        if karte is None:
            self.skipTest("%s gibt es in diesem Aufbau nicht" % name)
        return karte

    def test_jede_karte_hat_vier_eckbilder(self) -> None:
        for name in ("path_card", "console_frame"):
            with self.subTest(karte=name):
                bilder = getattr(self._karte(name), "_eckbilder", None)
                self.assertIsNotNone(bilder, "%s ohne Eckbilder" % name)
                self.assertEqual(sorted(bilder), ["ol", "or", "ul", "ur"])

    def test_in_der_ecke_steht_der_hintergrund(self) -> None:
        """Die Kernaussage: außen Hintergrund, innen Kartenfläche.

        Gegenprobe zum stillen Ausfall - stünde in beiden Punkten dasselbe,
        wäre die Ecke nicht weggeschnitten worden.
        """
        punkte = {"ol": ((0, 0), (-1, -1)), "or": ((-1, 0), (0, -1)),
                  "ul": ((0, -1), (-1, 0)), "ur": ((-1, -1), (0, 0))}
        for name in ("path_card", "console_frame"):
            bilder = getattr(self._karte(name), "_eckbilder", {})
            for ecke, schild in sorted(bilder.items()):
                with self.subTest(karte=name, ecke=ecke):
                    foto = getattr(schild, "_bild", None)
                    self.assertIsNotNone(foto)
                    r = foto.width()
                    (ax, ay), (ix, iy) = punkte[ecke]
                    aussen = self._punkt(foto, ax % r, ay % r)
                    innen = self._punkt(foto, ix % r, iy % r)
                    abstand = sum(abs(a - b)
                                  for a, b in zip(aussen[:3], innen[:3]))
                    self.assertGreaterEqual(
                        abstand, MINDESTABSTAND,
                        "%s/%s: Ecke und Fläche sind fast gleich (%s gegen %s)"
                        % (name, ecke, aussen, innen))

    def test_die_eckbilder_sitzen_an_den_ecken(self) -> None:
        """Ohne Ausgleich für das ``padding`` säßen sie zu weit innen."""
        for name in ("path_card", "console_frame"):
            karte = self._karte(name)
            bilder = getattr(karte, "_eckbilder", {})
            breite, hoehe = karte.winfo_width(), karte.winfo_height()
            if breite <= 1:
                self.skipTest("Karte noch ohne Größe")
            for ecke, schild in sorted(bilder.items()):
                with self.subTest(karte=name, ecke=ecke):
                    x, y = schild.winfo_x(), schild.winfo_y()
                    r = schild.winfo_width()
                    links = x <= 2
                    rechts = abs((x + r) - breite) <= 2
                    oben = y <= 2
                    unten = abs((y + r) - hoehe) <= 2
                    self.assertTrue(links or rechts,
                                    "%s: weder links noch rechts (x=%d)" % (ecke, x))
                    self.assertTrue(oben or unten,
                                    "%s: weder oben noch unten (y=%d)" % (ecke, y))

    def test_wiederholtes_nachziehen_haeuft_keine_bilder_an(self) -> None:
        """Jeder Aufruf baut vier neue Bilder - die alten müssen weg.

        Sonst wäre jede Größenänderung ein kleines Leck, und beim Ziehen am
        Fensterrand kommen viele.
        """
        karte = self._karte("path_card")
        vorher = len(getattr(karte, "_eckbilder", {}))
        for _ in range(6):
            self.app._karten_ecken_nachziehen()
            self.wurzel.update_idletasks()
        self.assertEqual(len(getattr(karte, "_eckbilder", {})), vorher)
        kinder = [w for w in karte.winfo_children()
                  if w.winfo_class() == "Label"]
        self.assertLessEqual(
            len([w for w in kinder if getattr(w, "_bild", None) is not None]),
            4, "es sammeln sich Eckbilder an")


if __name__ == "__main__":
    unittest.main(verbosity=2)
