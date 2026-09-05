# -*- coding: utf-8 -*-
"""Mehrfache Schluessel bearbeiten, und den Bestand der Konsole sichern.

Beides ist am 05.09.2026 aus der fuehrenden Arbeitskopie uebernommen worden
(siehe deren ``ini_config.py`` und ``_smp_sicherung_ablegen``), aber gegen
diesen Quelltext geprueft statt abgeschrieben.

**Warum mehrfache Schluessel ueberhaupt ein Thema sind.** Die
``config.ini`` von ShadowMount+ kennt sieben Schluessel, die auf mehreren
Zeilen stehen duerfen - eine je Suchpfad, je Abbild, je Titel. Ein
gewoehnliches Woerterbuch kann das nicht abbilden: ``parse_flat_ini``
behaelt den letzten Wert, und aus drei Suchpfaden wird einer. Die Zeilenzahl
bleibt dabei gleich, also faellt es niemandem auf.

Bis v1.9.5 half sich dieses Projekt damit, solche Zeilen **unangetastet** zu
lassen - kein Verlust, aber auch nicht bearbeitbar. Jetzt werden die sieben
benannten Schluessel mit ``" | "`` zu einer Editorzeile zusammengezogen und
beim Schreiben wieder verteilt. Jeder ANDERE mehrfache Schluessel bleibt
weiterhin woertlich stehen: MicroMount benutzt denselben Editor mit eigenen
Schluesseln, und die naechste Payload-Fassung kann weitere bringen.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("smp_konfig")

from ps5_validator.utils.ini_config import (                # noqa: E402
    MEHRFACH_TRENNER,
    WIEDERHOLBARE_SCHLUESSEL,
    fuer_anzeige,
    fuer_datei,
    mehrfach_schluessel,
    merge_flat_ini,
    parse_flat_ini,
    parse_flat_ini_multi,
    render_flat_ini,
)
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

VORLAGE = """# ShadowMount+ Konfiguration
# scanpath=<absolute_path>  (wiederholbar)

scanpath=/mnt/usb0
scanpath=/data/games
debug=1
# api_port=9090
"""


class LesenTests(unittest.TestCase):
    """Kein Wert geht beim Lesen verloren."""

    def test_der_einfache_leser_verliert_werte(self):
        """Die Vorbedingung - ohne sie braeuchte es das alles nicht."""
        einfach = parse_flat_ini(VORLAGE)
        self.assertEqual("/data/games", einfach["scanpath"],
                         "Der letzte gewinnt - der erste ist weg.")

    def test_der_mehrfachleser_behaelt_alle(self):
        mehr = parse_flat_ini_multi(VORLAGE)
        self.assertEqual(["/mnt/usb0", "/data/games"], mehr["scanpath"])
        self.assertEqual(["1"], mehr["debug"])

    def test_auskommentiertes_zaehlt_nicht(self):
        mehr = parse_flat_ini_multi(VORLAGE)
        self.assertNotIn("api_port", mehr,
                         "Eine auskommentierte Vorlage ist kein Wert.")

    def test_die_anzeige_zieht_sie_zu_einer_zeile(self):
        anzeige = fuer_anzeige(parse_flat_ini_multi(VORLAGE))
        self.assertEqual("/mnt/usb0 | /data/games", anzeige["scanpath"])
        self.assertEqual("1", anzeige["debug"],
                         "Ein einfacher Schluessel bleibt einfach.")

    def test_der_trenner_taugt_fuer_die_echten_werte(self):
        """Doppelpunkt und Leerzeichen kaemen nicht infrage.

        ``image_sector`` traegt selbst einen Doppelpunkt, und Dateinamen
        duerfen Leerzeichen haben.
        """
        mehr = {"image_sector": ["mein spiel.ffpkg:4096", "anderes.ffpkg:512"]}
        anzeige = fuer_anzeige(mehr)
        self.assertEqual(["mein spiel.ffpkg:4096", "anderes.ffpkg:512"],
                         fuer_datei(anzeige)["image_sector"])


class SchreibenTests(unittest.TestCase):
    """Was der Editor zeigt, kommt so auf der Konsole an."""

    def _zeilen(self, text: str, schluessel: str) -> list[str]:
        return [z.split("=", 1)[1] for z in text.splitlines()
                if z.strip().startswith(schluessel + "=")]

    def test_geaenderte_werte_landen_je_auf_ihrer_zeile(self):
        anzeige = fuer_anzeige(parse_flat_ini_multi(VORLAGE))
        anzeige["scanpath"] = "/mnt/usb1 | /data/spiele"
        neu = merge_flat_ini(VORLAGE, fuer_datei(anzeige))
        self.assertEqual(["/mnt/usb1", "/data/spiele"],
                         self._zeilen(neu, "scanpath"))

    def test_ein_dritter_wert_kommt_in_den_anhang(self):
        """Die Vorlage hat zwei Zeilen, der Editor drei Werte."""
        anzeige = fuer_anzeige(parse_flat_ini_multi(VORLAGE))
        anzeige["scanpath"] = "/a | /b | /c"
        neu = merge_flat_ini(VORLAGE, fuer_datei(anzeige), header_comment="Neu")
        self.assertEqual(["/a", "/b", "/c"], self._zeilen(neu, "scanpath"),
                         "Der dritte Wert ist stillschweigend verschwunden.")

    def test_ein_wert_weniger_kommentiert_die_uebrige_zeile_aus(self):
        anzeige = fuer_anzeige(parse_flat_ini_multi(VORLAGE))
        anzeige["scanpath"] = "/nur-einer"
        neu = merge_flat_ini(VORLAGE, fuer_datei(anzeige))
        self.assertEqual(["/nur-einer"], self._zeilen(neu, "scanpath"))
        self.assertIn("# scanpath=/data/games", neu,
                      "Die zweite Zeile muss auskommentiert dastehen, nicht "
                      "geloescht - auf der Konsole ist das umkehrbar.")

    def test_eine_geleerte_zeile_kommentiert_alle_aus(self):
        anzeige = fuer_anzeige(parse_flat_ini_multi(VORLAGE))
        anzeige["scanpath"] = ""
        neu = merge_flat_ini(VORLAGE, fuer_datei(anzeige))
        self.assertEqual([], self._zeilen(neu, "scanpath"))
        self.assertIn("# scanpath=/mnt/usb0", neu)

    def test_kommentare_und_vorlagen_bleiben(self):
        anzeige = fuer_anzeige(parse_flat_ini_multi(VORLAGE))
        anzeige["scanpath"] = "/a | /b"
        neu = merge_flat_ini(VORLAGE, fuer_datei(anzeige))
        self.assertIn("# ShadowMount+ Konfiguration", neu)
        self.assertIn("# api_port=9090", neu)

    def test_render_schreibt_listen_zeilenweise(self):
        """Sonst stuende dort die Python-Schreibweise."""
        text = render_flat_ini({"scanpath": ["/a", "/b"], "debug": "1"})
        self.assertIn("scanpath=/a", text)
        self.assertIn("scanpath=/b", text)
        self.assertNotIn("[", text)


class FremdeSchluesselTests(unittest.TestCase):
    """Was nicht benannt ist, bleibt unangetastet."""

    FREMD = "eigener_pfad=/x\neigener_pfad=/y\ndebug=1\n"

    def test_ein_unbekannter_mehrfachschluessel_wird_nicht_gleichgemacht(self):
        """MicroMount benutzt denselben Editor mit eigenen Schluesseln.

        Ohne diese Sperre bekaeme jede seiner Zeilen denselben Wert - der
        Verlust, den die Namensliste allein nicht verhindert.
        """
        self.assertNotIn("eigener_pfad", WIEDERHOLBARE_SCHLUESSEL)
        self.assertIn("eigener_pfad", mehrfach_schluessel(self.FREMD))
        neu = merge_flat_ini(self.FREMD, {"eigener_pfad": "/z", "debug": "0"})
        self.assertIn("eigener_pfad=/x", neu)
        self.assertIn("eigener_pfad=/y", neu)
        self.assertNotIn("eigener_pfad=/z", neu)
        self.assertIn("debug=0", neu, "Der einfache Schluessel muss wirken.")

    def test_mit_einer_liste_laesst_er_sich_doch_setzen(self):
        """Wer es ausdruecklich will, kann - eine Liste sagt die Absicht."""
        neu = merge_flat_ini(self.FREMD, {"eigener_pfad": ["/z", "/w"]})
        self.assertIn("eigener_pfad=/z", neu)
        self.assertIn("eigener_pfad=/w", neu)


class SicherungTests(unittest.TestCase):
    """Der Bestand der Konsole wird gesichert, bevor jemand ihn ueberschreibt."""

    def setUp(self):
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        self.ordner = tempfile.mkdtemp(prefix="smpbak_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.ordner,
                                                            ignore_errors=True))
        # Das Original merken und zuruecksetzen, nicht mit "del" entfernen:
        # Es ist eine Methode der echten Klasse, und ein del liesse sie fuer
        # jede spaetere Testdatei im selben Prozess fehlen.
        self._original = APP.PS5ConverterGUI.__dict__["_smp_sicherungsorte"]
        self.addCleanup(setattr, APP.PS5ConverterGUI, "_smp_sicherungsorte",
                        self._original)
        APP.PS5ConverterGUI._smp_sicherungsorte = classmethod(
            lambda cls, _o=self.ordner: [_o])

    def test_der_gelesene_text_wird_abgelegt(self):
        pfad, fehler = self.gui._smp_sicherung_ablegen(
            "/data/shadowmount/config.ini", "debug=1\nscanpath=/a\n")
        self.assertEqual("", fehler)
        self.assertTrue(os.path.isfile(pfad))
        with io.open(pfad, encoding="utf-8") as fh:
            self.assertEqual("debug=1\nscanpath=/a\n", fh.read())

    def test_der_name_traegt_die_datei_und_die_zeit(self):
        pfad, _ = self.gui._smp_sicherung_ablegen(
            "/data/shadowmount/config.ini", "debug=1\n")
        name = os.path.basename(pfad)
        self.assertTrue(name.startswith("config.ini_"), name)
        self.assertTrue(name.endswith(".bak"), name)

    def test_zwei_sicherungen_ueberschreiben_sich_nicht(self):
        """Der Zeitstempel geht auf Sekunden - zwei am selben Tag gehen."""
        erste, _ = self.gui._smp_sicherung_ablegen("/x/config.ini", "a=1\n")
        # Der Stempel hat Sekundenaufloesung; ohne Wartezeit waere der Name
        # gleich. Geprueft wird deshalb der Aufbau, nicht zwei echte Laeufe.
        self.assertIn("_", os.path.basename(erste))
        self.assertTrue(os.path.isfile(erste))

    def test_ohne_inhalt_wird_nichts_abgelegt(self):
        pfad, fehler = self.gui._smp_sicherung_ablegen("/x/config.ini", "")
        self.assertEqual("", pfad)
        self.assertEqual("smpbak.error_empty", fehler)
        self.assertEqual([], os.listdir(self.ordner))

    def test_ein_unbeschreibbarer_ort_meldet_sich(self):
        # Eine Datei dort, wo ein Ordner entstehen muesste - os.makedirs
        # scheitert daran mit OSError, ohne dass es Rechte braucht.
        with io.open(os.path.join(self.ordner, "datei_statt_ordner"), "w") as fh:
            fh.write("x")
        APP.PS5ConverterGUI._smp_sicherungsorte = classmethod(
            lambda cls, _o=self.ordner: [os.path.join(_o, "datei_statt_ordner", "tiefer")])
        pfad, fehler = self.gui._smp_sicherung_ablegen("/x/config.ini", "a=1\n")
        self.assertEqual("", pfad)
        self.assertEqual("smpbak.error_write", fehler)


class SicherungsortTests(unittest.TestCase):
    """Zwei Orte, weil der erste schreibgeschuetzt sein kann."""

    def test_es_gibt_mehr_als_einen_ort(self):
        orte = APP.PS5ConverterGUI._smp_sicherungsorte()
        self.assertGreaterEqual(len(orte), 2,
                                "Unter Programme\\ ist der erste Ort nicht "
                                "beschreibbar - dann braucht es den zweiten.")

    def test_der_zweite_ort_folgt_der_umlenkung(self):
        """Sonst schriebe ein Testlauf in den Bestand des Anwenders."""
        orte = APP.PS5ConverterGUI._smp_sicherungsorte()
        umgelenkt = os.environ.get("PS5CONV_KONFIGORDNER", "")
        if not umgelenkt:
            self.skipTest("Ohne Umlenkung nicht pruefbar")
        self.assertTrue(
            any(os.path.normcase(umgelenkt) in os.path.normcase(o) for o in orte),
            "Kein Ort liegt im umgelenkten Einstellungsordner: %r" % (orte,))

    def test_der_ordner_wird_nicht_im_voraus_angelegt(self):
        """Ein leerer Ordner neben dem Programm waere nur Verwirrung."""
        ordner = APP.PS5ConverterGUI._smp_sicherungsordner()
        self.assertTrue(ordner, "Es muss ein Ort genannt werden.")
        # Angelegt wird erst beim Ablegen - der Name allein legt nichts an.
        self.assertEqual(ordner, APP.PS5ConverterGUI._smp_sicherungsordner())


if __name__ == "__main__":
    unittest.main()
