# -*- coding: utf-8 -*-
"""Ein Knopf, bei dem nichts geschieht, muss das sagen.

**Was schiefging.** ``plattform.datei_oeffnen`` lieferte einen blossen
``bool``, und der hiess nicht "geoeffnet", sondern nur "Versuch abgesetzt":

* Unter Windows kam nach ``os.startfile`` immer ``True``. Wirft es - weil
  die Datei fehlt -, faengt der Browser-Ausweg den Fall ab und meldet
  ebenfalls Erfolg.
* Unter POSIX wurde der Rueckgabewert von ``xdg-open``/``open`` nie
  gelesen, seine Fehlerausgabe ging nach ``DEVNULL``.

``False`` entstand damit praktisch nur bei leerem Pfad. Am 06.09.2026
gemessen: Fuer ``C:\\gibt-es-nicht\\x.pdf`` meldeten beide Funktionen
``True``.

Sechs Stellen im Hauptprogramm haben ein ``if not ...``, das deshalb nie
zutraf. Vier davon hatten eine Fehlermeldung, die nie erschien; zwei
schrieben nur mit ``logger.debug``, was beim eingestellten Grad nicht
einmal in der Protokolldatei landet. Der Anwender drueckte einen Knopf,
und nichts geschah - ohne Meldung, ohne Zeile im Protokoll.

**Die Gruende sind uebersetzbar.** ``ps5_validator/utils`` darf ``i18n``
nicht importieren; die Saetze gehen aber in Dialoge. Deshalb nimmt
``oeffnen_versuchen`` Vorlagen entgegen - dasselbe Muster wie
``pkg_merger.MELDUNGEN`` und ``shadowmount_generation.MELDUNGEN``.
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
pruefumgebung.umlenken("systemoeffner")

from ps5_validator.utils import plattform                   # noqa: E402
from ps5_validator.utils import i18n                        # noqa: E402
import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class ModulTests(unittest.TestCase):
    """Was die Plattformschicht meldet."""

    def test_ein_fehlender_pfad_gilt_nicht_als_geoeffnet(self):
        # Der Kern des Befunds.
        ok, grund = plattform.oeffnen_versuchen(
            os.path.join(tempfile.gettempdir(), "gibt-es-nicht-xyz.pdf"))
        self.assertFalse(ok)
        self.assertTrue(grund)

    def test_ein_leerer_pfad_nennt_seinen_eigenen_grund(self):
        ok, grund = plattform.oeffnen_versuchen("")
        self.assertFalse(ok)
        self.assertNotEqual(grund, plattform.OEFFNEN_MELDUNGEN["nicht_da"])

    def test_eine_adresse_wird_nicht_auf_der_platte_gesucht(self):
        # http://... liegt nicht im Dateisystem; die Existenzpruefung darf
        # sie nicht abweisen.
        with mock.patch.object(plattform, "IST_WINDOWS", False), \
             mock.patch.object(plattform.shutil, "which", return_value=""), \
             mock.patch("webbrowser.open", return_value=True) as browser:
            ok, _grund = plattform.oeffnen_versuchen("https://example.invalid/")
        self.assertTrue(ok)
        browser.assert_called_once()

    def test_die_gruende_lassen_sich_uebersetzen(self):
        ok, grund = plattform.oeffnen_versuchen(
            "", {"kein_pfad": "No path was given."})
        self.assertFalse(ok)
        self.assertEqual("No path was given.", grund)

    def test_eine_unbrauchbare_vorlage_verschluckt_den_grund_nicht(self):
        # Eine Vorlage mit falschem Platzhalter darf nicht dazu fuehren,
        # dass gar nichts mehr dasteht.
        ok, grund = plattform.oeffnen_versuchen("", {"kein_pfad": "{gibtsnicht}"})
        self.assertFalse(ok)
        self.assertTrue(grund)

    def test_datei_oeffnen_bleibt_als_huelle(self):
        # Aufrufer, denen der Grund gleichgueltig ist, sollen nicht
        # umgebaut werden muessen.
        self.assertFalse(plattform.datei_oeffnen(
            os.path.join(tempfile.gettempdir(), "gibt-es-nicht-xyz.pdf")))
        self.assertTrue(plattform.datei_oeffnen.__doc__)

    def test_der_dateimanager_prueft_ebenfalls(self):
        self.assertFalse(plattform.im_dateimanager_zeigen(
            os.path.join(tempfile.gettempdir(), "gibt-es-nicht-xyz.pdf")))

    def test_ein_echter_ordner_geht_durch(self):
        with mock.patch("os.startfile", create=True) as startfile, \
             mock.patch.object(plattform, "IST_WINDOWS", True):
            ok, grund = plattform.oeffnen_versuchen(str(PROJEKT))
        self.assertTrue(ok, grund)
        startfile.assert_called_once()


class HelferTests(unittest.TestCase):
    """Der Helfer im Hauptprogramm meldet wirklich."""

    def _gui(self):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._t = lambda s, **kw: s
        return gui

    def test_bei_misserfolg_kommt_eine_meldung(self):
        gui = self._gui()
        with mock.patch.object(APP.messagebox, "showwarning") as warnung:
            ergebnis = gui._oeffnen_oder_melden(
                os.path.join(tempfile.gettempdir(), "gibt-es-nicht-xyz.pdf"))
        self.assertFalse(ergebnis)
        warnung.assert_called_once()

    def test_bei_erfolg_kommt_keine(self):
        gui = self._gui()
        with mock.patch.object(APP, "_system_oeffnen_versuchen",
                               return_value=(True, "")), \
             mock.patch.object(APP.messagebox, "showwarning") as warnung:
            self.assertTrue(gui._oeffnen_oder_melden("egal"))
        warnung.assert_not_called()

    def test_ohne_fenster_bleibt_es_beim_protokoll(self):
        """Ohne laufende Oberflaeche darf der Versuch nicht scheitern.

        Die Instanz hat hier kein ``root`` - wie in Tests und unter --cli.
        Bis zum ersten Entwurf griff der Helfer darauf zu, bevor er
        ueberhaupt oeffnete, und riss den Aufruf mit.
        """
        gui = self._gui()
        with mock.patch.object(APP.messagebox, "showwarning",
                               side_effect=RuntimeError("kein Fenster")):
            self.assertFalse(gui._oeffnen_oder_melden("/gibt/es/nicht"))

    def test_die_vorlagen_gibt_es_in_beiden_sprachen(self):
        for kennung in plattform.OEFFNEN_MELDUNGEN:
            eintrag = i18n.STRINGS["oeffnen." + kennung]
            self.assertTrue(eintrag.get("de"), kennung)
            self.assertTrue(eintrag.get("en"), kennung)

    def test_die_vorlagen_kommen_wirklich_an(self):
        gui = self._gui()
        gui._t = lambda s, **kw: "UEBERSETZT" if s.startswith("oeffnen.") else s
        texte = gui._oeffnen_texte()
        self.assertEqual(set(plattform.OEFFNEN_MELDUNGEN), set(texte))
        self.assertTrue(all(v == "UEBERSETZT" for v in texte.values()))


class EinbauTests(unittest.TestCase):
    """Keine Stelle prueft mehr auf den alten, wertlosen Rueckgabewert."""

    @classmethod
    def setUpClass(cls):
        with io.open(APP.__file__, "rb") as fh:
            cls.baum = ast.parse(fh.read().decode("utf-8"))

    def test_kein_waechter_haengt_mehr_an_datei_oeffnen(self):
        """``if not _system_datei_oeffnen(...)`` traf nie zu.

        Ueber den Syntaxbaum, nicht ueber eine Zeichenkettensuche: Der
        Name steht auch im Import und in Docstrings, und danach zu suchen
        faende ihn dort ebenfalls.
        """
        treffer = []
        for knoten in ast.walk(self.baum):
            if not isinstance(knoten, ast.UnaryOp) or not isinstance(knoten.op, ast.Not):
                continue
            ruf = knoten.operand
            if (isinstance(ruf, ast.Call)
                    and isinstance(ruf.func, ast.Name)
                    and ruf.func.id == "_system_datei_oeffnen"):
                treffer.append(ruf.lineno)
        self.assertEqual([], treffer)

    def test_der_dateimanager_faellt_auf_den_helfer_zurueck(self):
        """Die zwei Stellen, die frueher ganz schwiegen."""
        stellen = []
        for knoten in ast.walk(self.baum):
            if not isinstance(knoten, ast.If):
                continue
            pruef = knoten.test
            if (isinstance(pruef, ast.UnaryOp) and isinstance(pruef.op, ast.Not)
                    and isinstance(pruef.operand, ast.Call)
                    and isinstance(pruef.operand.func, ast.Name)
                    and pruef.operand.func.id == "_system_im_dateimanager_zeigen"):
                rufe = {getattr(k.func, "attr", "") for k in ast.walk(knoten)
                        if isinstance(k, ast.Call)}
                stellen.append((knoten.lineno, "_oeffnen_oder_melden" in rufe))
        self.assertTrue(stellen, "Die Stellen gibt es nicht mehr")
        self.assertTrue(all(gemeldet for _z, gemeldet in stellen),
                        "stumm geblieben: %s" % stellen)


if __name__ == "__main__":
    unittest.main(verbosity=2)
