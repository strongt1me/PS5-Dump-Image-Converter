# -*- coding: utf-8 -*-
"""Eigenschaftsbasierte Prüfungen mit Hypothesis.

Ein gewöhnlicher Test prüft die Fälle, an die jemand gedacht hat.
Hypothesis dreht das um: Man beschreibt eine **Eigenschaft**, die immer
gelten muss, und die Bibliothek sucht selbst nach einer Eingabe, die sie
verletzt - und schrumpft sie dann auf das kleinste Gegenbeispiel.

Angesetzt wird auf die drei Stellen, an denen eine falsche Eingabe wirklich
weh tut:

* **Die Fortschrittsrechnung.** Ein Balken, der zurückspringt oder über
  100 % läuft, ist immer falsch - egal welche Werte hineinlaufen.
* **Der ``param.sfo``-Leser.** Er bekommt Bytes aus fremden Dateien. Ein
  Absturz dort reisst die ganze Anzeige mit. Genau dieser Leser war bis
  v1.8.92 fehlerhaft (Kopffelder um eines versetzt).
* **Der Fortschritts-Wächter.** Er misst und darf den gemessenen Vorgang
  unter keinen Umständen stören.

Läuft Hypothesis nicht, werden die Prüfungen übersprungen statt zu scheitern:
Die Bibliothek gehört nicht zur Auslieferung.
"""
from __future__ import annotations

import os
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from hypothesis import HealthCheck, assume, given, settings
    from hypothesis import strategies as st
    HYPOTHESIS_DA = True
except ImportError:                                   # pragma: no cover
    HYPOTHESIS_DA = False

HAUPTDATEI = Path(__file__).resolve().parent / "PS5ImageConverter_Pro_FINAL_revised.py"


def _lade_hauptprogramm():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _Balken:
    """Trägt genau die Felder, die ``_balken_anzeigewert`` anfasst."""

    def __init__(self, angezeigt=0.0, von=0.0, bis=100.0, zuletzt=0.0):
        self.task_displayed = angezeigt
        self._batch_von = von
        self._batch_bis = bis
        self._zuletzt_angezeigt = zuletzt


@unittest.skipUnless(HYPOTHESIS_DA, "hypothesis nicht installiert")
class FortschrittsrechnungTests(unittest.TestCase):
    """Der Balken darf nie zurück, nie über 100, nie aus seinem Abschnitt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    def wert(self, attrappe) -> float:
        return self.haupt.PS5ConverterGUI._balken_anzeigewert(attrappe)

    @settings(max_examples=250, deadline=None)
    @given(werte=st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=1, max_size=40))
    def test_der_balken_geht_nie_zurueck(self, werte) -> None:
        a = _Balken()
        zuletzt = 0.0
        for w in werte:
            a.task_displayed = w
            jetzt = self.wert(a)
            self.assertGreaterEqual(jetzt + 1e-9, zuletzt)
            zuletzt = jetzt

    @settings(max_examples=250, deadline=None)
    @given(
        werte=st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=1, max_size=20),
        dateien=st.integers(min_value=1, max_value=8),
    )
    def test_der_balken_bleibt_zwischen_null_und_hundert(self, werte, dateien) -> None:
        """Auch über mehrere Dateien der Sammelkonvertierung hinweg."""
        a = _Balken()
        for nummer in range(1, dateien + 1):
            a._batch_von = (nummer - 1) * 100.0 / dateien
            a._batch_bis = nummer * 100.0 / dateien
            for w in werte:
                a.task_displayed = w
                jetzt = self.wert(a)
                self.assertGreaterEqual(jetzt, 0.0)
                self.assertLessEqual(jetzt, 100.0)

    @settings(max_examples=200, deadline=None)
    @given(
        anteil=st.floats(min_value=0.0, max_value=100.0),
        nummer=st.integers(min_value=1, max_value=12),
        gesamt=st.integers(min_value=1, max_value=12),
    )
    def test_jede_datei_bleibt_in_ihrem_abschnitt(self, anteil, nummer, gesamt) -> None:
        assume(nummer <= gesamt)
        von = (nummer - 1) * 100.0 / gesamt
        bis = nummer * 100.0 / gesamt
        a = _Balken(anteil, von=von, bis=bis, zuletzt=von)
        ergebnis = self.wert(a)
        self.assertGreaterEqual(ergebnis + 1e-9, von)
        self.assertLessEqual(ergebnis - 1e-9, bis)

    _UNSINN = st.one_of(
        st.none(),
        st.text(max_size=8),
        st.integers(min_value=-10 ** 9, max_value=10 ** 9),
        st.floats(allow_nan=True, allow_infinity=True),
        st.just(object()),
        st.lists(st.integers(), max_size=2),
    )

    @settings(max_examples=300, deadline=None)
    @given(wert=_UNSINN)
    def test_unsinnige_werte_werfen_nicht(self, wert) -> None:
        """Die Anzeige darf an keiner Stelle eine Ausnahme auslösen.

        Gefunden am 25.08.2026: ``task_displayed = ':'`` löste ein
        ``ValueError`` aus. Die Rechnung läuft im Tk-Takt - eine Ausnahme
        dort beendet die ganze Fortschrittsschleife, ohne dass etwas
        abstürzt oder eine Meldung erscheint. Der Balken stünde für immer.
        """
        a = _Balken()
        a.task_displayed = wert
        try:
            ergebnis = self.wert(a)
        except Exception as fehler:
            self.fail("unsinniger Wert %r loeste %s aus"
                      % (wert, type(fehler).__name__))
        self.assertIsInstance(ergebnis, float)
        self.assertEqual(ergebnis, ergebnis, "NaN auf dem Balken")
        self.assertGreaterEqual(ergebnis, 0.0)
        self.assertLessEqual(ergebnis, 100.0)

    @settings(max_examples=300, deadline=None)
    @given(von=_UNSINN, bis=_UNSINN, wert=_UNSINN)
    def test_auch_unsinnige_abschnittsgrenzen_werfen_nicht(self, von, bis, wert) -> None:
        """Die Abschnittsgrenzen kommen aus der Sammelkonvertierung."""
        a = _Balken()
        a._batch_von, a._batch_bis, a.task_displayed = von, bis, wert
        try:
            ergebnis = self.wert(a)
        except Exception as fehler:
            self.fail("Grenzen %r/%r loesten %s aus"
                      % (von, bis, type(fehler).__name__))
        self.assertGreaterEqual(ergebnis, 0.0)
        self.assertLessEqual(ergebnis, 100.0)


@unittest.skipUnless(HYPOTHESIS_DA, "hypothesis nicht installiert")
class ParamSfoTests(unittest.TestCase):
    """Der Leser bekommt Bytes aus fremden Dateien und darf nie abstürzen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    @settings(max_examples=400, deadline=None,
              suppress_health_check=[HealthCheck.too_slow])
    @given(roh=st.binary(max_size=600))
    def test_beliebige_bytes_ergeben_ein_dictionary(self, roh) -> None:
        ergebnis = self.haupt.parse_sfo(roh)
        self.assertIsInstance(ergebnis, dict)

    @settings(max_examples=300, deadline=None)
    @given(rest=st.binary(max_size=400))
    def test_richtige_magie_mit_muell_dahinter(self, rest) -> None:
        """Der gefährlichere Fall: Der Kopf sieht gültig aus, der Rest nicht.

        So kam der Fehler bis v1.8.92 zustande - die Kopffelder wurden um
        eines versetzt gelesen, als Anzahl der Einträge kam eine Adresse
        heraus, und der Leser lief über das Dateiende hinaus.
        """
        ergebnis = self.haupt.parse_sfo(b"\x00PSF" + rest)
        self.assertIsInstance(ergebnis, dict)

    @settings(max_examples=200, deadline=None)
    @given(
        version=st.integers(min_value=0, max_value=0xFFFFFFFF),
        key_off=st.integers(min_value=0, max_value=0xFFFFFFFF),
        data_off=st.integers(min_value=0, max_value=0xFFFFFFFF),
        anzahl=st.integers(min_value=0, max_value=0xFFFFFFFF),
        rest=st.binary(max_size=200),
    )
    def test_beliebige_kopffelder_werfen_nicht(self, version, key_off, data_off,
                                               anzahl, rest) -> None:
        """Absichtlich unsinnige Zeiger und Anzahlen - etwa 4 Milliarden Einträge."""
        kopf = b"\x00PSF" + struct.pack("<IIII", version, key_off, data_off, anzahl)
        ergebnis = self.haupt.parse_sfo(kopf + rest)
        self.assertIsInstance(ergebnis, dict)

    def test_eine_gueltige_sfo_wird_gelesen(self) -> None:
        """Die Gegenprobe - sonst bestünde ein Leser, der immer {} liefert."""
        eintraege = [("TITLE", "Ein Spiel"), ("TITLE_ID", "PPSA01234")]
        schluessel = b""
        daten = b""
        tabelle = b""
        for k, v in eintraege:
            ko, do = len(schluessel), len(daten)
            schluessel += k.encode() + b"\x00"
            roh = v.encode() + b"\x00"
            daten += roh
            tabelle += struct.pack("<HHIII", ko, 0x0204, len(roh), len(roh), do)
        kopf_laenge = 20 + len(tabelle)
        sfo = (b"\x00PSF"
               + struct.pack("<IIII", 0x0101, kopf_laenge,
                             kopf_laenge + len(schluessel), len(eintraege))
               + tabelle + schluessel + daten)
        ergebnis = self.haupt.parse_sfo(sfo)
        self.assertEqual(ergebnis.get("TITLE"), "Ein Spiel")
        self.assertEqual(ergebnis.get("TITLE_ID"), "PPSA01234")


@unittest.skipUnless(HYPOTHESIS_DA, "hypothesis nicht installiert")
class WaechterTests(unittest.TestCase):
    """Eine Messung, die den gemessenen Vorgang stört, wäre schlimmer als keine."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade_hauptprogramm()

    @settings(max_examples=200, deadline=None)
    @given(
        punkte=st.lists(
            st.tuples(
                st.floats(min_value=0.0, max_value=1e6, allow_nan=False),
                st.one_of(st.floats(allow_nan=True, allow_infinity=True),
                          st.none(), st.text(max_size=6)),
                st.text(max_size=40),
            ),
            max_size=30,
        )
    )
    def test_beliebige_messpunkte_werfen_nicht(self, punkte) -> None:
        w = self.haupt.FortschrittsWaechter()
        for zeit, balken, status in punkte:
            w.beobachte(balken, "?", status, jetzt=zeit)
        w.abschliessen()
        self.assertIsInstance(w.befunde(), list)
        self.assertIsInstance(w.bericht(), list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
