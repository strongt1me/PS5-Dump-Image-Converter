# -*- coding: utf-8 -*-
"""Wo der JS Loader Adresse, Ports und Mitschrift ablegt.

Bis v1.9.5 hielt das Fenster Adresse und JS-Port in einer eigenen ``ip.ini``
neben dem Programm (Befunde M077, M078, M079, M082 vom 04.09.2026). Das hatte
drei Folgen, und die dritte stand nicht im Bericht:

* Im Einzeldatei-Bau zeigt ``__file__`` nach ``sys._MEIPASS`` - dem Ordner,
  den PyInstaller beim Beenden loescht. Was der Anwender eintrug, war beim
  naechsten Start weg, und die Mitschrift ``ps5_payload_log.txt`` gleich mit.
* Die Datei ueberschrieb die zentrale Einstellung ``ps5_ip`` bedingungslos,
  schrieb aber nie dorthin zurueck.
* **Die drei Bauskripte betteten eine vorgefundene ip.ini ein.** Wer aus dem
  Quelltext heraus einmal gesendet hatte, legte damit eine Datei mit der
  Adresse *seiner* Konsole an, die der naechste Bau an jeden Anwender
  ausgeliefert haette.

Geprueft wird die Wirkung an einer echten Instanz mit umgelenktem
Einstellungsordner - keine Zeichenkettensuche im Quelltext.
"""
from __future__ import annotations

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
pruefumgebung.umlenken("jsloader_ablage")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


def _gui():
    """Programmobjekt ohne Tk - nur die Ablagewege werden gebraucht."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._t = lambda key, **kw: key
    return gui


class _MitEigenenEinstellungen(unittest.TestCase):
    """Jeder Fall bekommt eine leere Einstellungsablage."""

    def setUp(self):
        self.gui = _gui()
        self.werte: dict[str, object] = {}
        self.gui._load_setting = lambda k, d=None: self.werte.get(k, d)
        self.gui._save_setting = lambda k, v: self.werte.__setitem__(k, v)


class UebernahmeTests(_MitEigenenEinstellungen):
    """Eine alte ip.ini wird genau einmal eingesammelt."""

    def setUp(self):
        super().setUp()
        self.ordner = tempfile.mkdtemp(prefix="jsloader_ini_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.ordner,
                                                            ignore_errors=True))
        self.pfad = os.path.join(self.ordner, "ip.ini")
        self.gui._jsloader_ini_pfad = lambda: self.pfad

    def _datei(self, inhalt: str) -> None:
        with io.open(self.pfad, "w", encoding="utf-8") as fh:
            fh.write(inhalt)

    def test_adresse_und_port_wandern_in_die_einstellungen(self):
        self._datei("10.0.0.5\n50010\n")
        self.assertEqual(self.pfad, self.gui._jsloader_ini_uebernehmen())
        self.assertEqual("10.0.0.5", self.werte.get("ps5_ip"))
        self.assertEqual("50010", self.werte.get("jsloader_js_port"))
        self.assertTrue(self.werte.get("jsloader_ini_uebernommen"))

    def test_nur_einmal(self):
        """Danach ist die Datei stumm - sonst waere sie weiter die zweite Quelle."""
        self._datei("10.0.0.5\n50010\n")
        self.gui._jsloader_ini_uebernehmen()
        self._datei("10.0.0.99\n50099\n")
        self.assertEqual("", self.gui._jsloader_ini_uebernehmen())
        self.assertEqual("10.0.0.5", self.werte.get("ps5_ip"))
        self.assertEqual("50010", self.werte.get("jsloader_js_port"))

    def test_eine_gesetzte_adresse_wird_nicht_gekippt(self):
        """Der Einstellungsdialog ist die neuere Angabe."""
        self.werte["ps5_ip"] = "192.168.1.7"
        self._datei("10.0.0.5\n50010\n")
        self.gui._jsloader_ini_uebernehmen()
        self.assertEqual("192.168.1.7", self.werte.get("ps5_ip"))
        # Der Port hat keine solche Konkurrenz und wird trotzdem uebernommen.
        self.assertEqual("50010", self.werte.get("jsloader_js_port"))

    def test_muell_in_der_datei_wird_uebergangen(self):
        # "192.168.1." ist ein Tippzwischenstand, "999999" kein Port.
        # Ein Rechnername waere dagegen gueltig - _ist_plausible_ps5_adresse
        # laesst ihn mit Absicht durch, im Heimnetz ist er ein zulaessiges
        # Ziel.
        self._datei("192.168.1.\n999999\n")
        self.gui._jsloader_ini_uebernehmen()
        self.assertIsNone(self.werte.get("ps5_ip"))
        self.assertIsNone(self.werte.get("jsloader_js_port"))
        self.assertTrue(self.werte.get("jsloader_ini_uebernommen"),
                        "Auch dann darf es nicht bei jedem Oeffnen neu "
                        "versucht werden.")

    def test_ein_rechnername_wird_uebernommen(self):
        """Die Gegenrichtung - sonst waere die Pruefung nur streng."""
        self._datei("ps5-wohnzimmer\n50010\n")
        self.gui._jsloader_ini_uebernehmen()
        self.assertEqual("ps5-wohnzimmer", self.werte.get("ps5_ip"))

    def test_ohne_datei_kostet_es_nur_einen_blick(self):
        self.assertEqual("", self.gui._jsloader_ini_uebernehmen())
        self.assertTrue(self.werte.get("jsloader_ini_uebernommen"))

    def test_die_datei_bleibt_liegen(self):
        """Wer sie von Hand pflegt, behaelt seinen Bestand."""
        self._datei("10.0.0.5\n50010\n")
        self.gui._jsloader_ini_uebernehmen()
        self.assertTrue(os.path.isfile(self.pfad))


class RueckwegTests(_MitEigenenEinstellungen):
    """Was im Fenster steht, wird zentral gemerkt."""

    def test_adresse_und_beide_ports(self):
        self.gui._jsloader_verbindung_merken("192.168.1.94", "50000", "9021")
        self.assertEqual("192.168.1.94", self.werte.get("ps5_ip"))
        self.assertEqual("50000", self.werte.get("jsloader_js_port"))
        self.assertEqual("9021", self.werte.get("jsloader_elf_port"))

    def test_unfertige_adresse_wird_nicht_gemerkt(self):
        """Der Torso aus einer halb getippten Eingabe hat dort nichts zu suchen."""
        self.gui._jsloader_verbindung_merken("192.168.1.", "50000", "9021")
        self.assertIsNone(self.werte.get("ps5_ip"))
        # Die Ports sind davon unabhaengig und werden trotzdem gemerkt.
        self.assertEqual("50000", self.werte.get("jsloader_js_port"))

    def test_leere_eingaben_loeschen_nichts(self):
        self.werte["ps5_ip"] = "192.168.1.94"
        self.gui._jsloader_verbindung_merken("", "", "")
        self.assertEqual("192.168.1.94", self.werte.get("ps5_ip"))

    def test_unsinnige_ports_werden_uebergangen(self):
        self.gui._jsloader_verbindung_merken("192.168.1.94", "0", "70000")
        self.assertIsNone(self.werte.get("jsloader_js_port"))
        self.assertIsNone(self.werte.get("jsloader_elf_port"))


class ProtokollpfadTests(unittest.TestCase):
    """Die Mitschrift ueberlebt das Beenden."""

    def test_liegt_nicht_im_entpackordner_des_buendels(self):
        """Genau der Fehler: __file__ zeigt in der EXE nach _MEIPASS.

        Gepatcht wird ``__file__`` des Moduls selbst, nicht nur ``frozen``
        und ``_MEIPASS``: Sonst prueft der Fall gar nichts. Im Skriptbetrieb
        liegt ``__file__`` ohnehin nie unter _MEIPASS - der alte Code haette
        die Behauptung also genauso bestanden. Beim ersten Anlauf war der
        Test aus genau diesem Grund gruen geblieben.
        """
        meipass = tempfile.mkdtemp(prefix="jsloader_meipass_")
        self.addCleanup(lambda: __import__("shutil").rmtree(meipass,
                                                            ignore_errors=True))
        with mock.patch.object(APP.sys, "frozen", True, create=True), \
                mock.patch.object(APP.sys, "_MEIPASS", meipass, create=True), \
                mock.patch.object(APP, "__file__",
                                  os.path.join(meipass, "programm.py")):
            pfad = APP.PS5ConverterGUI._jsloader_protokollpfad()
        self.assertFalse(
            os.path.normcase(pfad).startswith(os.path.normcase(meipass)),
            "Die Mitschrift liegt im Ordner, den das Beenden loescht: %s" % pfad)

    def test_liegt_bei_den_anderen_protokollen(self):
        pfad = APP.PS5ConverterGUI._jsloader_protokollpfad()
        self.assertEqual(os.path.normcase(tempfile.gettempdir()),
                         os.path.normcase(os.path.dirname(pfad)))

    def test_der_testlauf_schreibt_nicht_in_die_datei_des_anwenders(self):
        """Dasselbe Muster wie bei ps5converter.log."""
        pfad = APP.PS5ConverterGUI._jsloader_protokollpfad()
        self.assertIn("_test", os.path.basename(pfad))

    def test_zu_grosse_mitschrift_wird_umgerollt(self):
        ordner = tempfile.mkdtemp(prefix="jsloader_roll_")
        self.addCleanup(lambda: __import__("shutil").rmtree(ordner,
                                                            ignore_errors=True))
        pfad = os.path.join(ordner, "mitschrift.txt")
        with io.open(pfad, "wb") as fh:
            fh.write(b"x" * (APP.PS5ConverterGUI._JS_PROTOKOLL_GRENZE + 1))
        APP.PS5ConverterGUI._jsloader_protokoll_umrollen(pfad)
        self.assertFalse(os.path.exists(pfad), "Die volle Datei liegt noch da.")
        self.assertTrue(os.path.exists(pfad + ".1"),
                        "Der Vorgaenger ist verschwunden statt umbenannt.")

    def test_kleine_mitschrift_bleibt_liegen(self):
        ordner = tempfile.mkdtemp(prefix="jsloader_roll2_")
        self.addCleanup(lambda: __import__("shutil").rmtree(ordner,
                                                            ignore_errors=True))
        pfad = os.path.join(ordner, "mitschrift.txt")
        with io.open(pfad, "wb") as fh:
            fh.write(b"kurz")
        APP.PS5ConverterGUI._jsloader_protokoll_umrollen(pfad)
        self.assertTrue(os.path.exists(pfad))
        self.assertFalse(os.path.exists(pfad + ".1"))


class BauskriptTests(unittest.TestCase):
    """Keine ip.ini darf mehr in einen Bau geraten."""

    SPECS = ("PS5ImageConverter_Pro.spec",
             "PS5ImageConverter_Pro_linux.spec",
             "PS5ImageConverter_Pro_macos.spec")

    def test_kein_bauskript_bettet_sie_ein(self):
        """Sonst gaebe ein Bau die Adresse des Baurechners an jeden weiter."""
        for name in self.SPECS:
            with self.subTest(spec=name):
                text = (PROJEKT / name).read_text(encoding="utf-8")
                # Die Zeilen nennen, nicht die ganze Datei ausgeben - sonst
                # steht im Fehlschlag ein Bildschirm voll Bauskript.
                treffer = [i for i, z in enumerate(text.splitlines(), 1)
                           if "ip.ini" in z]
                self.assertEqual(
                    [], treffer,
                    "%s nennt ip.ini in Zeile %s - eine vorgefundene Datei "
                    "wuerde damit wieder eingebettet." % (name, treffer))

    def test_sie_steht_in_gitignore(self):
        """Eine aus einer alten Fassung uebrige Datei darf nicht eingecheckt werden."""
        text = (PROJEKT / ".gitignore").read_text(encoding="utf-8")
        eintraege = [z.strip() for z in text.splitlines()
                     if z.strip() and not z.strip().startswith("#")]
        self.assertIn("ip.ini", eintraege)

    def test_der_macos_ausloeser_nennt_sie_nicht_mehr(self):
        text = (PROJEKT / ".github/workflows/macos-buendel.yml").read_text(
            encoding="utf-8")
        self.assertNotIn("ip.ini", text)


if __name__ == "__main__":
    unittest.main()
