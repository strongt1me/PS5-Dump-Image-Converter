# -*- coding: utf-8 -*-
"""Kein Weg loescht etwas, bevor der Ersatz fertig ist.

Vier Befunde des Pruefstands vom 06.09.2026, alle derselben Bauart: Erst
wird geloescht, dann gebaut. Scheitert der Bau - voller Datentraeger,
Abbruch durch den Anwender, Fehler im Werkzeug -, hat der Anwender beides
verloren.

**Aufgabe 4 mit Zielformat .ffpkg loeschte die QUELLE.** Steht im Feld ZIEL
derselbe Ordner, in dem die Quelle liegt - der Normalfall, wenn alles in
einem Spieleordner liegt -, dann zeigt der "erwartete Ausgabepfad" auf die
Quelldatei selbst. Gemessen:

    _get_expected_output_path("ffpkg_to_ffpfsc",
                              r"D:\\PS5 Spiele\\Spiel.ffpkg",
                              r"D:\\PS5 Spiele")
    -> "D:\\PS5 Spiele\\Spiel.ffpkg"

Auf "ja, ueberschreiben" folgte ``os.remove`` auf genau diese Datei, bevor
ein einziger Arbeitsschritt begonnen hatte.

**Aufgabe 5 fragte gar nicht.** ``_get_expected_output_path`` liefert fuer
``batch_convert`` ``None``, womit der ganze Ueberschreib-Block in
``_launch_task`` uebersprungen wurde. Der erste Packschritt entfernte eine
vorhandene Zieldatei dann kommentarlos. Ausgerechnet in der Aufgabe, in der
zehn Dateien in einen Ordner gehen und Namensgleichheit beim
Wiederholungslauf der Normalfall ist.

**Der AMPR-Manager loeschte den Container**, bevor der neue gebaut war -
in beiden Zweigen (.ffpfsc/.ffpfs und .exfat).

Das Muster dagegen steht im Programm schon: ``_build_ffpkg_from_folder``
baut ueber eine Zwischendatei und uebernimmt erst am Schluss mit
``os.replace``. Auf demselben Datentraeger ist das unteilbar - entweder
steht die neue Datei da oder die alte, nie ein Rumpf.
"""
from __future__ import annotations

import ast
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ueberschreiben")

from ps5_validator.utils import i18n                        # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class _Var:
    """So viel von tk.StringVar, wie _get_selected_target_type anfasst."""

    def __init__(self, wert: str) -> None:
        self._wert = wert

    def get(self) -> str:
        return self._wert


def _gui():
    return APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)


class ZielIstQuelleTests(unittest.TestCase):
    """Der Fall, in dem der Ausgabepfad auf die Quelle zeigt."""

    def test_der_ausgabepfad_kann_die_quelle_sein(self):
        """Die Vorbedingung des Befunds - gemessen, nicht angenommen."""
        gui = _gui()
        gui.target_format = _Var(".ffpkg")
        quelle = os.path.join("D:", os.sep, "PS5 Spiele", "Spiel.ffpkg")
        ziel = os.path.dirname(quelle)
        pfad = gui._get_expected_output_path("ffpkg_to_ffpfsc", quelle, ziel)
        self.assertEqual(os.path.normcase(os.path.abspath(quelle)),
                         os.path.normcase(os.path.abspath(pfad)))

    def test_dann_wird_nicht_geloescht(self):
        """Ueber den Syntaxbaum: Vor dem os.remove steht der Vergleich."""
        with io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef) and k.name == "_run_engine_thread")
        quelltext = ast.unparse(knoten)
        self.assertIn("os.path.normcase(os.path.abspath(output_exists_path))",
                      quelltext,
                      "Der Vergleich Ziel==Quelle fehlt - dann loescht der "
                      "Ueberschreib-Zweig wieder die Quelldatei.")

    def test_der_hinweis_gibt_es_in_beiden_sprachen(self):
        eintrag = i18n.STRINGS["log.ziel_ist_quelle"]
        self.assertTrue(eintrag.get("de"))
        self.assertTrue(eintrag.get("en"))

    def test_der_ueberschreib_dialog_ist_nicht_mehr_fest_deutsch(self):
        with io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef) and k.name == "_run_engine_thread")
        quelltext = ast.unparse(knoten)
        self.assertNotIn("Datei überschreiben?", quelltext)
        self.assertNotIn("Die Ausgabedatei existiert bereits", quelltext)
        self.assertIn("dialog.msg.target_file_exists_overwrite_confirm", quelltext)


class SammelUeberschreibenTests(unittest.TestCase):
    """Aufgabe 5 fragt jetzt - einmal, nicht zehnmal."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ueberschreiben_")
        self.ordner = Path(self.tmp.name)
        self.quelle = self.ordner / "Spiel.exfat"
        self.quelle.write_bytes(b"Q" * 64)
        self.vorhanden = self.ordner / "Spiel.ffpfsc"
        self.vorhanden.write_bytes(b"altes Ergebnis")

    def tearDown(self):
        self.tmp.cleanup()

    def _gui(self, antwort: bool):
        gui = _gui()
        gui.root = object()      # nur die Anwesenheit zaehlt
        gui._t = lambda s, **kw: s
        self.protokoll: list[str] = []
        gui._append_to_log = self.protokoll.append
        self.gefragt: list[str] = []

        def _fragen(titel, text):
            self.gefragt.append(titel)
            return antwort
        gui._ask_yesno_threadsafe = _fragen
        gui._batch_ueberschreiben = None
        return gui

    def test_bei_vorhandener_datei_wird_gefragt(self):
        gui = self._gui(antwort=True)
        self.assertTrue(gui._batch_ueberschreiben_klaeren(
            str(self.quelle), str(self.ordner), "ffpfsc"))
        self.assertEqual(1, len(self.gefragt))

    def test_ein_nein_ueberspringt_die_datei(self):
        gui = self._gui(antwort=False)
        self.assertFalse(gui._batch_ueberschreiben_klaeren(
            str(self.quelle), str(self.ordner), "ffpfsc"))
        self.assertIn("batch.uebersprungen_vorhanden", self.protokoll[0])

    def test_die_datei_bleibt_dabei_unangetastet(self):
        gui = self._gui(antwort=False)
        gui._batch_ueberschreiben_klaeren(str(self.quelle), str(self.ordner),
                                          "ffpfsc")
        self.assertEqual(b"altes Ergebnis", self.vorhanden.read_bytes())

    def test_gefragt_wird_nur_einmal_je_lauf(self):
        """Zehn Adressen, ein Fenster - sonst klickt der Anwender zehnmal."""
        gui = self._gui(antwort=True)
        for _ in range(10):
            gui._batch_ueberschreiben_klaeren(str(self.quelle),
                                              str(self.ordner), "ffpfsc")
        self.assertEqual(1, len(self.gefragt))

    def test_ohne_vorhandene_datei_wird_nicht_gefragt(self):
        gui = self._gui(antwort=True)
        self.assertTrue(gui._batch_ueberschreiben_klaeren(
            str(self.quelle), str(self.ordner), "ffpkg"))
        self.assertEqual([], self.gefragt)

    def test_ziel_gleich_quelle_fragt_nicht(self):
        # Dieselbe Datei - die Wege bauen daneben und ersetzen am Schluss.
        gui = self._gui(antwort=False)
        self.assertTrue(gui._batch_ueberschreiben_klaeren(
            str(self.quelle), str(self.ordner), "exfat"))
        self.assertEqual([], self.gefragt)

    def test_ohne_oberflaeche_wird_nicht_gefragt(self):
        """Automatisierung und --cli haben schon entschieden."""
        gui = _gui()
        gui._t = lambda s, **kw: s
        gui._append_to_log = lambda _t: None
        gui._batch_ueberschreiben = None
        self.assertTrue(gui._batch_ueberschreiben_klaeren(
            str(self.quelle), str(self.ordner), "ffpfsc"))

    def test_die_antwort_gilt_nicht_fuer_den_naechsten_lauf(self):
        with io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_run_flexible_conversion")
        self.assertIn("self._batch_ueberschreiben = None", ast.unparse(knoten),
                      "Ohne Ruecksetzer entscheidet der vorige Lauf ueber die "
                      "Dateien des naechsten.")

    def test_die_schleife_fragt_vor_dem_bauen(self):
        with io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_run_flexible_conversion")
        text = ast.unparse(knoten)
        i_frage = text.find("_batch_ueberschreiben_klaeren")
        i_bau = text.find("_execute_conversion_by_type")
        self.assertGreater(i_frage, 0, "Es wird gar nicht gefragt")
        self.assertLess(i_frage, i_bau, "Gefragt wird erst nach dem Bauen")

    def test_die_texte_gibt_es_in_beiden_sprachen(self):
        for schluessel in ("batch.ueberschreiben_frage",
                           "batch.uebersprungen_vorhanden"):
            eintrag = i18n.STRINGS[schluessel]
            self.assertTrue(eintrag.get("de"), schluessel)
            self.assertTrue(eintrag.get("en"), schluessel)


class AmprManagerTests(unittest.TestCase):
    """Der Container wird nicht mehr vor dem Bau entfernt."""

    @classmethod
    def setUpClass(cls):
        with io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_mode_ampr_manager")
        cls.text = ast.unparse(knoten)

    def test_es_wird_daneben_gebaut(self):
        self.assertIn("final_out + '.neu'", self.text)

    def test_und_erst_danach_uebernommen(self):
        self.assertIn("os.replace(bau_ziel, final_out)", self.text)

    def test_beide_zweige_sind_umgestellt(self):
        """.ffpfsc/.ffpfs UND .exfat - einer allein reicht nicht."""
        self.assertEqual(2, self.text.count("os.replace(bau_ziel, final_out)"))

    def test_kein_vorab_loeschen_mehr(self):
        self.assertNotIn("os.remove(final_out)", self.text,
                         "Der Container wird wieder vor dem Bau entfernt.")

    def test_ein_halber_bau_bleibt_nicht_liegen(self):
        # Sonst saehe er beim naechsten Lauf wie ein Ergebnis aus.
        self.assertIn("os.remove(bau_ziel)", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
