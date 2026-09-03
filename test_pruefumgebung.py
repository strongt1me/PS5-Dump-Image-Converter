# -*- coding: utf-8 -*-
"""Prueft die Umlenkung, die den Bestand des Anwenders schuetzt.

``pruefumgebung.umlenken()`` setzt ``PS5CONV_KONFIGORDNER``, und
``plattform.konfigurationsordner()`` gibt dieser Variablen den Vorrang.
Ohne die Kette schreibt jeder Pruefstand in
``%APPDATA%\\PS5ImageConverterPro`` - am 03.09.2026 hier nachgemessen:
Ein Gesamtlauf legte dort einen Diagnosebericht ab und rollte dabei den
aeltesten der zehn weg.

Zwei Sachen werden bewacht, nicht eine:

* dass die Umlenkung **wirkt**, und
* dass ``leeren`` weiterhin auf ``False`` steht. Das ist kein
  Schoenheitsfehler: Mit ``True`` als Vorgabe hat drueben am 29.08.2026
  ein blosser Import die Ablage eines vorangegangenen Laufs geloescht -
  und damit das Beweisstueck, das eine Untersuchung gerade brauchte.

Jede Pruefung stellt die Umgebung hinterher wieder her. Eine
liegengebliebene Variable wuerde sonst alle spaeter geladenen Pruefungen
mit umlenken, und dann bewacht diese Datei nicht mehr, sondern stoert.
"""
from __future__ import annotations

import inspect
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung  # noqa: E402
from ps5_validator.utils import plattform  # noqa: E402


class _MitSauberterUmgebung(unittest.TestCase):
    """Merkt sich die Variable und legt sie hinterher zurueck."""

    def setUp(self) -> None:
        self._gemerkt = os.environ.get(pruefumgebung.UMGEBUNGSNAME)

    def tearDown(self) -> None:
        if self._gemerkt is None:
            os.environ.pop(pruefumgebung.UMGEBUNGSNAME, None)
        else:
            os.environ[pruefumgebung.UMGEBUNGSNAME] = self._gemerkt


class UmlenkungTests(_MitSauberterUmgebung):
    def test_die_umlenkung_kommt_beim_programm_an(self) -> None:
        ordner = pruefumgebung.umlenken("pruefung_der_pruefung")
        self.assertEqual(plattform.konfigurationsordner(), ordner)
        self.assertTrue(os.path.isdir(ordner), "Der Ordner wurde nicht angelegt.")

    def test_ohne_umlenkung_gilt_wieder_der_bestand(self) -> None:
        """Gegenprobe - sonst sagt die Pruefung oben nichts aus."""
        echt = pruefumgebung.bestandsordner()
        pruefumgebung.umlenken("pruefung_der_pruefung")
        os.environ.pop(pruefumgebung.UMGEBUNGSNAME, None)
        self.assertEqual(plattform.konfigurationsordner(), echt)

    def test_zwei_namen_zwei_ordner(self) -> None:
        eins = pruefumgebung.umlenken("eins")
        zwei = pruefumgebung.umlenken("zwei")
        self.assertNotEqual(eins, zwei)

    def test_der_ordner_liegt_im_temp(self) -> None:
        """Nirgends sonst - schon gar nicht neben dem Bestand."""
        ordner = pruefumgebung.umlenken("wo_denn")
        self.assertTrue(
            ordner.startswith(tempfile.gettempdir()),
            "Die Ablage liegt ausserhalb des Temp-Ordners: %s" % ordner)


class BestandsordnerTests(_MitSauberterUmgebung):
    """``bestandsordner()`` muss an der Umlenkung vorbeisehen."""

    def test_er_meldet_den_echten_ordner(self) -> None:
        os.environ[pruefumgebung.UMGEBUNGSNAME] = os.path.join("Z:", "erfunden")
        self.assertNotEqual(pruefumgebung.bestandsordner(),
                            os.path.join("Z:", "erfunden"))

    def test_er_laesst_die_variable_stehen(self) -> None:
        """Er nimmt sie zum Nachsehen heraus - und legt sie zurueck."""
        os.environ[pruefumgebung.UMGEBUNGSNAME] = os.path.join("Z:", "erfunden")
        pruefumgebung.bestandsordner()
        self.assertEqual(os.environ.get(pruefumgebung.UMGEBUNGSNAME),
                         os.path.join("Z:", "erfunden"))


class LeerenTests(_MitSauberterUmgebung):
    """Die Vorgabe ``leeren=False`` ist eine Lehre, keine Bequemlichkeit."""

    def test_die_vorgabe_raeumt_nicht_weg(self) -> None:
        ordner = pruefumgebung.umlenken("beweisstueck")
        spur = os.path.join(ordner, "beweis.txt")
        with open(spur, "w", encoding="utf-8") as datei:
            datei.write("Ergebnis eines frueheren Laufs")
        pruefumgebung.umlenken("beweisstueck")
        self.assertTrue(os.path.isfile(spur),
                        "Ein blosser Aufruf hat die Ablage geleert.")

    def test_die_unterschrift_sagt_es_auch(self) -> None:
        """Damit niemand die Vorgabe im Vorbeigehen umdreht."""
        vorgabe = inspect.signature(pruefumgebung.umlenken).parameters["leeren"].default
        self.assertIs(vorgabe, False)

    def test_ausdruecklich_geleert_wird_geleert(self) -> None:
        ordner = pruefumgebung.umlenken("wegraeumen")
        spur = os.path.join(ordner, "beweis.txt")
        with open(spur, "w", encoding="utf-8") as datei:
            datei.write("weg damit")
        pruefumgebung.umlenken("wegraeumen", leeren=True)
        self.assertFalse(os.path.isfile(spur))


class UnberuehrtTests(_MitSauberterUmgebung):
    """``unberuehrt()`` ist das Nachsehen, ob ein Lauf brav war."""

    def test_eine_unveraenderte_datei_gilt_als_unberuehrt(self) -> None:
        datei = os.path.join(pruefumgebung.bestandsordner(), "paths.json")
        if not os.path.isfile(datei):
            self.skipTest("Auf dieser Anlage gibt es keine Einstellungsdatei.")
        ok, satz = pruefumgebung.unberuehrt(time.time())
        self.assertTrue(ok, satz)

    def test_eine_juengere_datei_faellt_auf(self) -> None:
        """Gegenprobe ueber einen umgelenkten Bestand.

        Gemessen wird an einer echten Datei, nicht an einer Nachbildung:
        ``unberuehrt`` liest ``getmtime``, und das lasst sich nur an
        einer wirklich geschriebenen Datei pruefen.
        """
        ordner = pruefumgebung.umlenken("unberuehrt_gegenprobe", leeren=True)
        vorher = time.time() - 60
        with open(os.path.join(ordner, "paths.json"), "w", encoding="utf-8") as datei:
            datei.write("{}")
        # bestandsordner() sieht an der Umlenkung vorbei - fuer diese eine
        # Pruefung muss es sie aber sehen. Deshalb direkt gegen den Ordner.
        pfad = os.path.join(ordner, "paths.json")
        self.assertGreater(os.path.getmtime(pfad), vorher,
                           "Die Datei traegt keinen neueren Zeitstempel.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
