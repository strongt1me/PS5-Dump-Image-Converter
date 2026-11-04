# -*- coding: utf-8 -*-
"""Aufgabe 4 nach Dump-Ordner: Nach ABBRECHEN bleibt kein halber Dump liegen.

Fenstermessung vom 04.11.2026 (Aufgabe 4, ``Arkanoid Eternal Battle.ffpkg``, Abbruch nach 5 s): Im Ziel
lag ein Ordner "Arkanoid Eternal Battle" mit 66 MB von 1,2 GB. Bei dieser Aufgabe IST der Zielordner das
Ergebnis - ein halber sieht aus wie ein fertiger Dump. Die anderen Wege entpacken in einen Arbeitsordner
(``ps5conv_unpack_*``), der beim Abbruch verschwindet.

Entfernt wird nur, was dieser Lauf selbst angelegt hat.
"""
from __future__ import annotations

import ast
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("abbruch_teilordner")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _gui():
    gui = GUI.__new__(GUI)
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._t = lambda schluessel, **w: schluessel + str(sorted(w.items()))
    return gui


class TeilordnerTests(unittest.TestCase):

    def setUp(self):
        self.basis = tempfile.mkdtemp(prefix="ps5conv_teilordner_")
        self.addCleanup(shutil.rmtree, self.basis, True)
        self.ordner = os.path.join(self.basis, "Spiel")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        with io.open(os.path.join(self.ordner, "eboot.bin"), "wb") as fh:
            fh.write(b"x" * 1000)

    def test_ein_neuer_halber_ordner_wird_entfernt(self):
        gui = _gui()
        gui._teilordner_nach_abbruch_entfernen(self.ordner, True)
        self.assertFalse(os.path.exists(self.ordner))
        self.assertTrue(any("log.teilordner_entfernt" in z for z in gui.protokoll), gui.protokoll)

    def test_ein_vorhandener_ordner_bleibt_unberuehrt(self):
        gui = _gui()
        gui._teilordner_nach_abbruch_entfernen(self.ordner, False)
        self.assertTrue(os.path.isfile(os.path.join(self.ordner, "eboot.bin")))
        self.assertEqual([], gui.protokoll)

    def test_der_ordner_wird_mit_mehreren_versuchen_entfernt(self):
        """Das Kopierwerkzeug schreibt nach "Abbrechen" noch einen Augenblick: Bei einem Abbruch nach 2 s blieben
        26 MB liegen, weil nur einmal versucht wurde (gemessen 04.11.2026)."""
        gui = _gui()
        echt = APP._rmtree_force
        versuche = {"n": 0}

        def widerspenstig(pfad, **kw):
            versuche["n"] += 1
            if versuche["n"] >= 3:
                echt(pfad, **kw)

        with mock.patch.object(APP, "_rmtree_force", widerspenstig), mock.patch.object(APP.time, "sleep", lambda _s: None):
            gui._teilordner_nach_abbruch_entfernen(self.ordner, True)
        self.assertEqual(3, versuche["n"])
        self.assertFalse(os.path.exists(self.ordner))
        self.assertTrue(any("log.teilordner_entfernt" in z for z in gui.protokoll), gui.protokoll)

    def test_bleibt_er_stehen_wird_es_gesagt_und_nach_fuenf_versuchen_aufgegeben(self):
        gui = _gui()
        versuche = {"n": 0}

        def nie(pfad, **kw):
            versuche["n"] += 1

        with mock.patch.object(APP, "_rmtree_force", nie), mock.patch.object(APP.time, "sleep", lambda _s: None):
            gui._teilordner_nach_abbruch_entfernen(self.ordner, True)
        self.assertEqual(5, versuche["n"])
        self.assertTrue(os.path.isdir(self.ordner))
        self.assertTrue(any("log.teilordner_bleibt" in z for z in gui.protokoll), gui.protokoll)

    def test_ein_fehlender_ordner_ist_kein_fehler(self):
        gui = _gui()
        gui._teilordner_nach_abbruch_entfernen(os.path.join(self.basis, "gibt_es_nicht"), True)
        self.assertEqual([], gui.protokoll)


class VerdrahtungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            baum = ast.parse(fh.read())
        klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        cls.methode = next(m for m in klasse.body if isinstance(m, ast.FunctionDef)
                           and m.name == "_extract_ffpkg_to_folder_via_ufs2tool")
        cls.text = ast.unparse(cls.methode)

    def test_der_abbruchzweig_raeumt_auf(self):
        i_zweig = self.text.find("except _KopieAbgebrochen")
        self.assertGreater(i_zweig, 0)
        i_aufruf = self.text.find("self._teilordner_nach_abbruch_entfernen(dest_folder, ordner_ist_neu)", i_zweig)
        self.assertGreater(i_aufruf, i_zweig, "Der Abbruchzweig laesst den halben Ordner liegen.")

    def test_ob_der_ordner_neu_ist_wird_vor_dem_anlegen_festgehalten(self):
        i_neu = self.text.find("ordner_ist_neu = not os.path.exists(dest_folder)")
        i_anlegen = self.text.find("os.makedirs(dest_folder, exist_ok=True)")
        self.assertGreater(i_neu, 0)
        self.assertLess(i_neu, i_anlegen, "Nach dem Anlegen waere jeder Ordner 'vorhanden'.")

    def test_auch_der_exfat_weg_raeumt_nach_dem_abbruch_auf(self):
        """Aufgabe 3 und 6 (.exFAT -> Dump-Ordner): derselbe Befund, 58 MB bzw. 159 MB blieben liegen."""
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            baum = ast.parse(fh.read())
        klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        text = ast.unparse(next(m for m in klasse.body if isinstance(m, ast.FunctionDef)
                                and m.name == "_extract_exfat_to_folder_mkpfs"))
        i_zweig = text.find("except _KopieAbgebrochen")
        self.assertGreater(i_zweig, 0)
        self.assertIn("self._teilordner_nach_abbruch_entfernen(str(dest_path), True)", text[i_zweig:i_zweig + 600])

    def test_nach_dem_abbruch_laeuft_der_osfmount_weg_nicht_an(self):
        """Fenstermessung 04.11.2026: Der Ausweichweg legte den eben entfernten Zielordner leer wieder an."""
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            baum = ast.parse(fh.read())
        klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        for name, fallback in (("_mode_exfat_to_folder", "log.auto.0223"),
                               ("_extract_exfat_ebenen", "log.auto.0255")):
            methoden = [m for m in klasse.body if isinstance(m, ast.FunctionDef) and m.name == name]
            if not methoden:
                # Der Weg heisst anders - ueber den Fallback-Text finden.
                methoden = [m for m in klasse.body if isinstance(m, ast.FunctionDef)
                            and "'%s'" % fallback in ast.unparse(m)]
            self.assertTrue(methoden, "Methode zu %s nicht gefunden" % fallback)
            text = ast.unparse(methoden[0])
            i_fallback = text.find("'%s'" % fallback)
            vorher = text[max(0, i_fallback - 400):i_fallback]
            with self.subTest(fallback=fallback):
                self.assertIn("if not self.is_running:", vorher,
                              "Vor dem Ausweichweg %s wird der Abbruch nicht gefragt." % fallback)

    def test_die_dokan_abweisung_eines_buchstabens_wird_nachgefasst(self):
        """Fenstermessung 04.11.2026: "Can't assign a drive letter or mount point" - Aufgabe 4 scheiterte so
        sofort, derselbe Buchstabe ging sechs Sekunden spaeter. Zweimal mit dem naechsten freien nachfassen."""
        text = self.text
        i_schleife = text.find("versuche = 0")
        i_popen = text.find("mount_udf", i_schleife)
        i_abweisung = text.find("'drive letter' in tail.lower()")
        i_neu = text.find("entpacken.laufwerk_neuer_versuch")
        self.assertGreater(i_schleife, 0, "Die Wiederholung beim Einhaengen fehlt.")
        self.assertLess(i_schleife, i_popen)
        self.assertGreater(i_abweisung, i_popen)
        self.assertGreater(i_neu, i_abweisung)
        # Höchstens drei Versuche, und nach dem Abbruch wird nicht mehr nachgefasst.
        self.assertRegex(text, r"versuche < 3 and self\.is_running and \(?'drive letter' in tail\.lower\(\)\)?")

    def test_der_text_zum_neuen_versuch_gibt_es_in_allen_sprachen(self):
        for sprache in ("de", "en", "es", "it", "fr"):
            text = STRINGS["entpacken.laufwerk_neuer_versuch"][sprache]
            self.assertIn("{alt}", text, sprache)
            self.assertIn("{neu}", text, sprache)
            text.format(alt="X:", neu="W:")

    def test_die_texte_gibt_es_in_allen_sprachen(self):
        for schluessel in ("log.teilordner_entfernt", "log.teilordner_bleibt"):
            for sprache in ("de", "en", "es", "it", "fr"):
                text = STRINGS[schluessel][sprache]
                self.assertIn("{pfad}", text, (schluessel, sprache))
                text.format(pfad="x")


if __name__ == "__main__":
    unittest.main()
