# -*- coding: utf-8 -*-
"""Tests für die Aktualisierungsprüfung.

Ohne Netz: Das Urteil steckt in reinen Funktionen, das Holen wird als Rückruf
hereingereicht. Die Tests geben eine Nachbildung mit – auch, weil die
Verbindung zu GitHub auf dem Entwicklungsrechner etwa bei jedem zweiten
Aufruf abbricht und ein davon abhängiger Test nicht wiederholbar wäre.

Der zweite Teil prüft am Quelltext, dass die Prüfung im Programm auf
Knopfdruck läuft und nicht bei jedem Bericht – ein Fehlerbericht darf nicht an
einer Internetverbindung hängen.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import aktualisierungen as ak

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")


def _github(fassung: str) -> str:
    return json.dumps({"tag_name": fassung})


def _pypi(fassung: str) -> str:
    return json.dumps({"info": {"version": fassung}})


class FassungsvergleichTests(unittest.TestCase):
    """Der Vergleich zweier Fassungsangaben."""

    def test_gleich(self):
        self.assertEqual(0, ak.vergleiche("1.8.70", "1.8.70"))

    def test_praefix_v_stoert_nicht(self):
        self.assertEqual(0, ak.vergleiche("v1.8.70", "1.8.70"))

    def test_aelter_und_neuer(self):
        self.assertEqual(-1, ak.vergleiche("1.8.69", "1.8.70"))
        self.assertEqual(1, ak.vergleiche("1.8.71", "1.8.70"))

    def test_vierte_stelle_zaehlt(self):
        """0.3.5 ist aelter als 0.3.5.1 - genau das ging schon einmal schief.

        Bei gleichem Anfang gilt das kuerzere Tupel als kleiner; beim
        absteigenden Sortieren gewann dadurch die aeltere Nummer. Der Fehler
        trat 2026-08-20 in der AMPR-Versionsliste auf.
        """
        self.assertEqual(-1, ak.vergleiche("0.3.5", "0.3.5.1"))
        self.assertEqual(1, ak.vergleiche("0.3.5.1", "0.3.5"))

    def test_text_drumherum_faellt_weg(self):
        self.assertEqual(0, ak.vergleiche("Release 2.1.0 (stable)", "2.1.0"))

    def test_immer_vier_stellen(self):
        self.assertEqual((1, 8, 70, 0), ak.fassung_teile("v1.8.70"))
        self.assertEqual((0, 0, 0, 0), ak.fassung_teile(""))


class BeurteilungTests(unittest.TestCase):
    """Wie ein Bestandteil eingeordnet wird."""

    def test_aktuell(self):
        teil = ak.Bestandteil("MkPFS", "0.0.9", ak.GITHUB, "PSBrew/MkPFS")
        self.assertEqual(ak.AKTUELL, ak.beurteile(teil, "v0.0.9").zustand)

    def test_veraltet(self):
        teil = ak.Bestandteil("MkPFS", "0.0.9", ak.GITHUB, "PSBrew/MkPFS")
        befund = ak.beurteile(teil, "v0.1.0")
        self.assertEqual(ak.VERALTET, befund.zustand)
        self.assertIn("0.1.0", str(befund))

    def test_eigene_fassung_neuer(self):
        """Kommt vor: Im PS4-Werkzeug steckt MkPFS 1.0.0, veroeffentlicht ist 0.0.9."""
        teil = ak.Bestandteil("MkPFS", "1.0.0", ak.GITHUB, "PSBrew/MkPFS")
        self.assertEqual(ak.VORAUS, ak.beurteile(teil, "0.0.9").zustand)

    def test_ohne_quelle_wird_nicht_behauptet(self):
        teil = ak.Bestandteil("OSFMount", "3.1.1013", ak.OHNE_QUELLE, "https://…")
        befund = ak.beurteile(teil)
        self.assertEqual(ak.UNBEKANNT, befund.zustand)
        self.assertIn("https://…", str(befund))

    def test_unlesbare_eigene_fassung_gilt_nicht_als_veraltet(self):
        """"vorhanden" ist keine Null.

        Ohne diese Ausnahme wurde jede Angabe ohne Zahl als 0.0.0.0 gelesen
        und damit als veraltet gemeldet - am 21.08.2026 an tkinterdnd2
        aufgefallen, das kein ``__version__`` mitbringt.
        """
        teil = ak.Bestandteil("tkinterdnd2", "vorhanden", ak.PYPI, "tkinterdnd2")
        befund = ak.beurteile(teil, "0.6.2")
        self.assertEqual(ak.UNBEKANNT, befund.zustand)
        self.assertIn("0.6.2", str(befund))

    def test_fehler_wird_genannt(self):
        teil = ak.Bestandteil("MkPFS", "0.0.9", ak.GITHUB, "PSBrew/MkPFS")
        befund = ak.beurteile(teil, fehler="Verbindung abgebrochen")
        self.assertEqual(ak.FEHLER, befund.zustand)
        self.assertIn("Verbindung abgebrochen", str(befund))


class AbfrageTests(unittest.TestCase):
    """Das Holen - mit Nachbildung statt Netz."""

    def test_github_und_pypi_werden_richtig_gelesen(self):
        gh = ak.Bestandteil("MkPFS", "0.0.9", ak.GITHUB, "PSBrew/MkPFS")
        py = ak.Bestandteil("Pillow", "11.0.0", ak.PYPI, "pillow")
        self.assertEqual(("0.1.0", ""),
                         ak.hole_fassung(gh, lambda _u: _github("v0.1.0")))
        self.assertEqual(("12.0.0", ""),
                         ak.hole_fassung(py, lambda _u: _pypi("12.0.0")))

    def test_marke_und_titel_zaehlen_beide(self):
        """Manche Projekte kuerzen die Marke ab.

        Bei drakmor/ampr_emu heisst die Marke 0.3.6, das Release aber
        "AMPR Emu 0.3.6 / 0.3.6.1" - und 0.3.6.1 liegt wirklich darin. Nur die
        Marke zu lesen liess die hier vorhandene 0.3.6.1 als "neuer als die
        Quelle" erscheinen.
        """
        antwort = json.dumps({"tag_name": "0.3.6",
                              "name": "AMPR Emu 0.3.6 / 0.3.6.1"})
        teil = ak.Bestandteil("AMPR EMU", "0.3.6.1", ak.GITHUB, "drakmor/ampr_emu")
        self.assertEqual(("0.3.6.1", ""), ak.hole_fassung(teil, lambda _u: antwort))
        self.assertEqual(ak.AKTUELL, ak.beurteile(teil, "0.3.6.1").zustand)

    def test_jahreszahl_gilt_nicht_als_fassung(self):
        """Nur Nummern mit Punkt - sonst waere "Build 2026" die Fassung."""
        antwort = json.dumps({"tag_name": "v2.0.1", "name": "Build 2026 stable"})
        teil = ak.Bestandteil("x", "2.0.1", ak.GITHUB, "a/b")
        self.assertEqual(("2.0.1", ""), ak.hole_fassung(teil, lambda _u: antwort))

    def test_adressen(self):
        gh = ak.Bestandteil("x", "1", ak.GITHUB, "a/b")
        self.assertIn("api.github.com/repos/a/b", ak.adresse(gh))
        py = ak.Bestandteil("x", "1", ak.PYPI, "pillow")
        self.assertIn("pypi.org/pypi/pillow", ak.adresse(py))
        self.assertEqual("", ak.adresse(ak.Bestandteil("x", "1")))

    def test_wiederholung_faengt_aussetzer_ab(self):
        """Die Verbindung bricht hier etwa bei jedem zweiten Aufruf ab."""
        zaehler = {"n": 0}

        def _wackelig(_adresse):
            zaehler["n"] += 1
            if zaehler["n"] < 3:
                raise OSError("connectex")
            return _github("v2.0.0")

        teil = ak.Bestandteil("x", "1.0.0", ak.GITHUB, "a/b")
        self.assertEqual(("2.0.0", ""), ak.hole_fassung(teil, _wackelig, versuche=3))
        self.assertEqual(3, zaehler["n"])

    def test_endgueltiger_fehlschlag_meldet_den_grund(self):
        def _kaputt(_adresse):
            raise OSError("kein Netz")

        teil = ak.Bestandteil("x", "1.0.0", ak.GITHUB, "a/b")
        fassung, fehler = ak.hole_fassung(teil, _kaputt, versuche=2)
        self.assertEqual("", fassung)
        self.assertIn("kein Netz", fehler)

    def test_ohne_quelle_wird_nicht_abgefragt(self):
        def _darf_nicht(_adresse):
            raise AssertionError("es wurde doch abgefragt")

        teile = [ak.Bestandteil("OSFMount", "3.1", ak.OHNE_QUELLE, "https://…")]
        self.assertEqual(ak.UNBEKANNT, ak.pruefe(teile, _darf_nicht)[0].zustand)


class ZusammenfassungTests(unittest.TestCase):
    """Die eine Zeile oben."""

    def test_ohne_befunde(self):
        self.assertIn("nichts zu prüfen", ak.zusammenfassung([]))

    def test_zaehlt_die_veralteten(self):
        befunde = [
            ak.Befund("a", "1", "2", ak.VERALTET),
            ak.Befund("b", "1", "1", ak.AKTUELL),
            ak.Befund("c", "1", "", ak.FEHLER),
            ak.Befund("d", "1", "", ak.UNBEKANNT),
        ]
        text = ak.zusammenfassung(befunde)
        self.assertIn("1 Aktualisierung verfügbar", text)
        self.assertIn("1 nicht abfragbar", text)
        self.assertIn("1 ohne abfragbare Quelle", text)

    def test_alles_aktuell(self):
        befunde = [ak.Befund("a", "1", "1", ak.AKTUELL)]
        self.assertIn("auf dem Stand", ak.zusammenfassung(befunde))


class QuelltextTests(unittest.TestCase):
    """Wie die Prüfung im Programm eingebunden ist."""

    @classmethod
    def setUpClass(cls):
        with open(HAUPTDATEI, "r", encoding="utf-8") as datei:
            cls.quelltext = datei.read()

    def _methode(self, name: str) -> str:
        anfang = self.quelltext.index("    def %s(self" % name)
        weiter = self.quelltext.index("\n    def ", anfang + 10)
        return self.quelltext[anfang:weiter]

    def test_inventar_steht_im_bericht(self):
        """Es ist offline und schnell - deshalb immer dabei."""
        self.assertIn("diagnostics.report_section_inventory", self.quelltext)
        self.assertIn("self._diagnose_werkzeugbestand", self.quelltext)

    def test_netzabfrage_laeuft_nicht_im_bericht_mit(self):
        """Ein Fehlerbericht darf nicht an einer Verbindung haengen."""
        bericht = self._methode("_build_diagnostic_report_text")
        self.assertNotIn("_aktualisierungen_holen", bericht)
        self.assertNotIn("aktualisierungen", bericht.lower().replace(
            "diagnostics.", ""))

    def test_knopf_ist_vorhanden(self):
        self.assertIn("diagnostics.update_button", self.quelltext)
        self.assertIn("_aktualisierungen_pruefen", self.quelltext)

    def test_abfrage_laeuft_im_hintergrund(self):
        """Zwoelf Sekunden je Abfrage - das Fenster muss bedienbar bleiben."""
        fenster = self._methode("_render_diagnostic_report_window")
        self.assertIn("threading.Thread", fenster)
        self.assertIn("daemon=True", fenster)

    def test_eingebettete_werkzeuge_sind_erfasst(self):
        for teil in ("MkPFS-0.0.9", "PS4FFPFSC-0.2.8"):
            with self.subTest(teil=teil):
                self.assertIn(teil, self.quelltext)

    def test_fassung_wird_gelesen_nicht_importiert(self):
        """Ein Import zoege die Abhaengigkeiten des Werkzeugs nach sich."""
        rumpf = self._methode("_eingebettete_fassung")
        self.assertIn("__version__", rumpf)
        self.assertNotIn("import_module", rumpf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
