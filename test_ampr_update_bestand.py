# -*- coding: utf-8 -*-
"""Der Bestand, gegen den die AMPR-Aktualisierung vergleicht.

**Was schiefging.** ``ampr_updates`` ist ausschliesslich fuer
``libSceAmpr.sprx`` gebaut - ``DATEINAME``, ``PROJEKT`` und der Filter in
``angebote_lesen`` sagen das alle drei. Der Aufrufer gab den Bestand aber
ungefiltert weiter, also samt der PlayGo-Fassungen aus demselben Speicher.
``neuere()`` vergleicht gegen die **hoechste** Nummer darin.

Die mitgelieferte PlayGo-Fassung heisst 0.5, die hoechste AMPR-Fassung
0.3.6.6. Also war die hoechste Nummer im Bestand immer 0.5, und kein
AMPR-Angebot kam je darueber. Gemessen am 05.09.2026: ein Angebot 0.4.0
wurde nicht als neu erkannt.

**Warum es niemandem auffiel.** Der Knopf meldete nicht etwa einen Fehler,
sondern "schon aktuell" - die freundlichste aller Antworten. Es traf jeden
Anwender, ohne eigenen Ordner und ohne Zutun; man haette es nur gemerkt,
wenn man die angebotene Fassung von Hand mit der eigenen verglichen haette.

Die beiden Projekte zaehlen unabhaengig voneinander (siehe den Docstring
von ``_ampr_playgo_zur_version``). Ihre Nummern gehoeren nie in denselben
Vergleich.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_update_bestand")

from ps5_validator.utils import ampr_updates                # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class _Angebot:
    """So viel von ampr_updates.Angebot, wie neuere() anfasst."""

    def __init__(self, fassung: str, variante: str = "no debug") -> None:
        self.fassung = fassung
        self.variante = variante
        self.anhang = "libSceAmpr.sprx_v%s" % fassung


def _gui(eintraege):
    """Eine Oberflaeche, die genau diesen Speicherinhalt sieht.

    Gestellt wird ``_ampr_alle_fassungen`` - die Methode, die der
    Aktualisierungsweg wirklich ruft. Stellte man hier stattdessen
    ``_ampr_scan_version_store``, liefe der Test an einer Stelle vorbei,
    die inzwischen woanders liest, und pruefte nur noch sich selbst.
    Genau das ist beim Umbau am 05.09.2026 passiert - und dieser Test
    hat es gemeldet.
    """
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._ampr_alle_fassungen = lambda *_a: list(eintraege)
    return gui


def _eintrag(lib: str, version: str) -> dict:
    return {"lib": lib, "version": version, "variant": "no debug",
            "path": "", "size": 0, "sha256": ""}


#: Nachgebaut nach dem mitgelieferten Ordner: acht AMPR-Fassungen bis
#: 0.3.6.6 und PlayGo 0.5 - genau die Konstellation, die ab Werk vorliegt.
BEILAGE = [_eintrag("libSceAmpr.sprx", v)
           for v in ("0.3.6.6", "0.3.6.4", "0.3.6.2", "0.3.6.1",
                     "0.3.6", "0.3.5.1", "0.3.5", "0.3.4")]
BEILAGE += [_eintrag("libScePlayGo.sprx", "0.5")]


#: Eine GitHub-Antwort mit genau einem Angebot dieser Fassung.
#:
#: Die Variante liest ``variante_aus_anhang`` am Namensende ab, deshalb
#: haengt hier "-debug" dran und nicht "(debug)".
def _antwort(fassung: str, variante: str = "no debug") -> bytes:
    name = "libSceAmpr.sprx_v%s%s" % (
        fassung, "-debug" if variante == "debug" else "")
    return ('[{"tag_name": "v%s", "assets": [{"name": "%s", '
            '"browser_download_url": "http://beispiel.invalid/x", '
            '"size": 4096}]}]' % (fassung, name)).encode("utf-8")


class WegTests(unittest.TestCase):
    """Der echte Ablauf, nicht sein Nachbau.

    Ein Test, der den Filter selbst nachbaut, bleibt gruen, wenn ihn
    jemand aus der Hauptdatei entfernt - er prueft dann nur noch sich
    selbst. Deshalb laeuft hier _ampr_updates_arbeiten wirklich, mit
    gestelltem Netzzugang und gestelltem Holen.
    """

    def _lauf(self, angebot: str, eintraege=None, variante: str = "no debug"):
        """Laesst den Aktualisierungsweg laufen; liefert (geholt, Protokoll)."""
        gui = _gui(BEILAGE if eintraege is None else eintraege)
        protokoll: list[str] = []
        gui._melde_im_hauptstrang = protokoll.append
        gui._t = lambda schluessel, **kw: schluessel
        gui._ampr_lade_adresse = lambda _adresse: _antwort(angebot, variante)
        # Ein Ordner, den es sicher nicht gibt: schon_da() muss "nein"
        # sagen, sonst faende der Lauf jedes Angebot bereits abgelegt.
        gui._ampr_updates_ordner = lambda: os.path.join(
            tempfile.gettempdir(), "ampr_gibt_es_nicht_" + str(os.getpid()))
        geholt: list = []
        echt = ampr_updates.holen
        ampr_updates.holen = lambda _w, a, _l: (geholt.extend(a) or ([], []))
        try:
            gui._ampr_updates_arbeiten()
        finally:
            ampr_updates.holen = echt
        return geholt, protokoll

    def test_ein_neueres_angebot_wird_wirklich_geholt(self):
        geholt, protokoll = self._lauf("0.4.0")
        self.assertEqual(["0.4.0"], [a.fassung for a in geholt],
                         "Protokoll: %s" % protokoll)
        self.assertIn("ampr.update_gefunden", protokoll)

    def test_eine_aeltere_wird_nicht_geholt(self):
        geholt, protokoll = self._lauf("0.3.5")
        self.assertEqual([], geholt)
        self.assertIn("ampr.update_aktuell", protokoll)

    def test_ohne_ampr_im_speicher_gilt_alles_als_neu(self):
        # Nur PlayGo im Speicher heisst: kein AMPR-Bestand, also ist jedes
        # Angebot neu. Vorher gewann PlayGos 0.5 auch diesen Fall.
        nur_playgo = [_eintrag("libScePlayGo.sprx", "0.5")]
        geholt, _p = self._lauf("0.1.0", nur_playgo)
        self.assertEqual(["0.1.0"], [a.fassung for a in geholt])

    def test_eigene_variantennamen_werden_uebersetzt(self):
        """Der gemessene Fall - ueber den echten Weg, nicht nachgebaut.

        Der Anwender nennt seine Ordner "nolog"/"log"; beides fuehrt
        _AMPR_VARIANT_ORDER als dieselben zwei Klassen wie "no debug" und
        "debug". Ohne die Uebersetzung im Aufrufer galt fuer ampr_updates
        keine der beiden als bekannt, beide fielen auf die hoechste Nummer
        ueberhaupt zurueck (0.3.6.6) - und 0.3.6.4 debug, das ihm wirklich
        fehlt, wurde nicht angeboten.
        """
        eigen = [dict(_eintrag("libSceAmpr.sprx", "0.3.6.6"), variant="nolog"),
                 dict(_eintrag("libSceAmpr.sprx", "0.3.6.2"), variant="log")]
        geholt, protokoll = self._lauf("0.3.6.4", eigen, variante="debug")
        self.assertEqual(["0.3.6.4"], [a.fassung for a in geholt],
                         "Protokoll: %s" % protokoll)

    def test_die_uebersetzung_verschenkt_nichts(self):
        """Die Gegenrichtung: Was er hat, wird nicht noch einmal geholt."""
        eigen = [dict(_eintrag("libSceAmpr.sprx", "0.3.6.6"), variant="log")]
        geholt, _p = self._lauf("0.3.6.6", eigen, variante="debug")
        self.assertEqual([], geholt,
                         "0.3.6.6 log ist dieselbe Klasse wie 0.3.6.6 debug")


class BestandTests(unittest.TestCase):
    """Warum es schiefging - die Mechanik, nicht der Weg.

    ``_vorhanden`` baut den Filter hier nach. Damit bleiben diese Tests
    gruen, wenn ihn jemand aus der Hauptdatei entfernt - das ist Absicht
    und ihre Grenze: Sie erklaeren die Ursache, sie bewachen sie nicht.
    Bewacht wird sie von ``WegTests`` weiter oben, und die fallen.
    """

    def _vorhanden(self, eintraege) -> list[tuple[str, str]]:
        """Baut den Bestand so, wie der Aktualisierungsweg ihn baut."""
        gui = _gui(eintraege)
        return [(e["version"], e["variant"]) for e in gui._ampr_alle_fassungen()
                if e.get("lib") == gui._AMPR_SPRX_NAME]

    def test_playgo_steht_nicht_im_bestand(self):
        self.assertNotIn("0.5", [f for f, _v in self._vorhanden(BEILAGE)])

    def test_die_ampr_fassungen_stehen_alle_drin(self):
        # Die Gegenrichtung: Es darf nicht zu viel weggefiltert werden.
        self.assertEqual(8, len(self._vorhanden(BEILAGE)))
        self.assertIn("0.3.6.6", [f for f, _v in self._vorhanden(BEILAGE)])

    def test_ein_neueres_angebot_kommt_durch(self):
        # Der eigentliche Schaden: 0.4.0 ist neuer als 0.3.6.6 und wurde
        # trotzdem abgewiesen, weil PlayGos 0.5 den Vergleich gewann.
        neu = ampr_updates.neuere([_Angebot("0.4.0")], self._vorhanden(BEILAGE))
        self.assertEqual(["0.4.0"], [a.fassung for a in neu])

    def test_auch_eine_knapp_neuere_fassung_kommt_durch(self):
        neu = ampr_updates.neuere([_Angebot("0.3.6.7")], self._vorhanden(BEILAGE))
        self.assertEqual(["0.3.6.7"], [a.fassung for a in neu])

    def test_eine_aeltere_bleibt_draussen(self):
        # Sonst waere der Filter nur eine Schleuse, die alles durchlaesst.
        neu = ampr_updates.neuere([_Angebot("0.3.5")], self._vorhanden(BEILAGE))
        self.assertEqual([], neu)

    def test_ohne_den_filter_verstummt_die_suche(self):
        """Der Beleg fuer die Ursache - nicht fuer das Verhalten.

        Ohne ihn stuende hier nur, dass es jetzt geht, nicht warum es
        vorher nicht ging.
        """
        ungefiltert = [(e["version"], e["variant"]) for e in BEILAGE]
        self.assertEqual([], ampr_updates.neuere([_Angebot("0.4.0")], ungefiltert),
                         "Wenn das durchkommt, ist PlayGo nicht mehr die Ursache "
                         "und dieser Test hat seinen Gegenstand verloren.")


class VariantenklasseTests(unittest.TestCase):
    """Die Uebersetzung zwischen Ordnernamen und ampr_updates.

    Der Scanner liest die Variante aus dem Ordnernamen ab und kennt sechs
    Schreibweisen, die _AMPR_VARIANT_ORDER als zwei Klassen fuehrt.
    ``ampr_updates`` kennt nur die beiden kanonischen Namen. Ohne die
    Uebersetzung rechnete der Vergleich an dem vorbei, was der Anwender
    hat: Gemessen am 05.09.2026 mit einem Bestand ``0.3.6.6 nolog`` und
    ``0.3.6.2 log`` wurden die fehlenden Fassungen 0.3.6.4 und 0.3.6.6
    debug nicht angeboten.
    """

    def setUp(self):
        self.gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)

    def test_alle_no_debug_schreibweisen_werden_eine_klasse(self):
        for name in ("no debug", "nodebug", "nolog", "release", "NoLog"):
            self.assertEqual(ampr_updates.OHNE_DEBUG,
                             self.gui._ampr_variantenklasse(name), name)

    def test_alle_debug_schreibweisen_werden_eine_klasse(self):
        for name in ("debug", "log", "DEBUG", " Log "):
            self.assertEqual(ampr_updates.DEBUG,
                             self.gui._ampr_variantenklasse(name), name)

    def test_jede_klasse_ist_ein_name_den_ampr_updates_kennt(self):
        # Sonst uebersetzte die Methode in eine dritte Sprache.
        for name in APP.PS5ConverterGUI._AMPR_VARIANT_ORDER:
            self.assertIn(self.gui._ampr_variantenklasse(name),
                          (ampr_updates.DEBUG, ampr_updates.OHNE_DEBUG), name)

    def test_eine_unbekannte_variante_bleibt_stehen(self):
        # "standard" kommt aus einem flachen Ordner ohne Variantenangabe.
        # Sie einer Klasse zuzuschlagen waere geraten.
        self.assertEqual("standard", self.gui._ampr_variantenklasse("standard"))

    def test_der_gemessene_fall_wird_jetzt_angeboten(self):
        gui = _gui([_eintrag("libSceAmpr.sprx", "0.3.6.6"),
                    _eintrag("libSceAmpr.sprx", "0.3.6.2")])
        # Die beiden Eintraege auf die eigene Benennung des Anwenders setzen.
        vorrat = gui._ampr_alle_fassungen()
        vorrat[0]["variant"] = "nolog"
        vorrat[1]["variant"] = "log"
        bestand = [(e["version"], gui._ampr_variantenklasse(e["variant"]))
                   for e in vorrat]
        self.assertEqual([("0.3.6.6", "no debug"), ("0.3.6.2", "debug")], bestand)
        neu = ampr_updates.neuere([_Angebot("0.3.6.4", "debug")], bestand)
        self.assertEqual(["0.3.6.4"], [a.fassung for a in neu],
                         "0.3.6.4 debug fehlt ihm und muss angeboten werden")


class ModulgrenzeTests(unittest.TestCase):
    """Dass ampr_updates wirklich nur AMPR meint - die Vorbedingung."""

    def test_das_modul_holt_nur_libsceampr(self):
        self.assertEqual("libSceAmpr.sprx", ampr_updates.DATEINAME)

    def test_das_projekt_ist_das_ampr_projekt(self):
        self.assertIn("ampr", ampr_updates.PROJEKT.lower())

    def test_fremde_anhaenge_werden_gar_nicht_erst_gelesen(self):
        rohtext = ('[{"tag_name": "v9.9", "assets": ['
                   '{"name": "libScePlayGo.sprx_v9.9", "browser_download_url": "http://x/1"},'
                   '{"name": "libSceAmpr.sprx_v9.9 (no debug)", "browser_download_url": "http://x/2"}'
                   ']}]')
        angebote = ampr_updates.angebote_lesen(rohtext)
        self.assertTrue(angebote)
        for a in angebote:
            self.assertTrue(a.anhang.startswith("libSceAmpr.sprx"), a.anhang)


if __name__ == "__main__":
    unittest.main(verbosity=2)
