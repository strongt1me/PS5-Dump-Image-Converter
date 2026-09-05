# -*- coding: utf-8 -*-
"""Der AMPR-Vorrat aus allen Wurzeln, nicht nur aus einer.

**Was schiefging.** Fassungen koennen an vier Orten liegen: in einem
ausdruecklich genannten Ordner, im gespeicherten eigenen Ordner, im Ordner
"AMPR EMU updates" und in der Beilage. Bis v1.9.5 sah jede Stelle im
Programm nur einen Ausschnitt davon, und zwar einen anderen:

* Die Klappliste beim Erstellen las fest ``_ampr_bundled_store()``, sah
  also den eigenen Ordner des Anwenders nie.
* Der AMPR-Manager, der Automatiklauf und die Aktualisierung lasen ueber
  ``_ampr_resolve_store()``, und das liefert **genau eine** Wurzel - war
  ``ampr_store_dir`` gesetzt, war die Beilage weg.

Gemessen am 05.09.2026 mit einem eigenen Ordner, der zwei Fassungen
enthielt: die eine Liste zeigte 13 Fassungen, die andere 2, vorhanden
waren 15. Zwei Fenster desselben Programms, zwei Bestaende.

Ausgeloest wurde das leicht - ``ampr_store_dir`` wird gespeichert, sobald
der gewaehlte Ordner vom mitgelieferten abweicht. Einmal im Manager auf
"Ordner waehlen" genuegte.

**Warum ueber (lib, version, variant) entdoppelt wird und nicht ueber den
Inhalt.** Die im Manager getroffene Auswahl wird beim Anwenden ueber genau
dieses Tripel wieder aufgeloest und dann mit ``matches[0]`` gegriffen.
Blieben zwei Eintraege mit gleicher Fassung und Variante stehen - was eine
Entdopplung ueber SHA-256 zulaesst -, bekaeme der Anwender eine andere
Datei als die angeklickte, und auf der Konsole faellt das erst beim
Spielstart auf.
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

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ampr_speicher")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


def _lege_an(wurzel: str, ordnername: str, *libs: str, inhalt: bytes = b"x" * 32):
    """Legt eine Fassung im Aufbau des Versionsspeichers ab."""
    ordner = os.path.join(wurzel, ordnername)
    os.makedirs(ordner, exist_ok=True)
    for lib in libs:
        with open(os.path.join(ordner, lib), "wb") as fh:
            fh.write(inhalt)
    return ordner


class _Umgebung:
    """Vier echte Ordner auf der Platte, einer je Herkunft."""

    def __init__(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="ampr_wurzeln_")
        self.gewaehlt = os.path.join(self.basis, "gewaehlt")
        self.eigen = os.path.join(self.basis, "eigen")
        self.geholt = os.path.join(self.basis, "geholt")
        self.beilage = os.path.join(self.basis, "beilage")
        for pfad in (self.gewaehlt, self.eigen, self.geholt, self.beilage):
            os.makedirs(pfad)

    def gui(self, eigen: str | None = None):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        wert = self.eigen if eigen is None else eigen
        gui._load_setting = lambda k, v="": wert if k == "ampr_store_dir" else v
        gui._ampr_updates_ordner = lambda: self.geholt
        gui._ampr_bundled_store = lambda: self.beilage
        return gui

    def weg(self) -> None:
        shutil.rmtree(self.basis, ignore_errors=True)


class WurzelTests(unittest.TestCase):
    """Welche Ordner ueberhaupt gelesen werden."""

    def setUp(self):
        self.u = _Umgebung()

    def tearDown(self):
        self.u.weg()

    def _quellen(self, gui, explicit=""):
        return [q for _o, q in gui._ampr_speicherwurzeln(explicit)]

    def test_alle_vier_werden_gelesen(self):
        gui = self.u.gui()
        self.assertEqual(["gewaehlt", "eigen", "geholt", "beilage"],
                         self._quellen(gui, self.u.gewaehlt))

    def test_ohne_ausdrueckliche_angabe_bleiben_drei(self):
        gui = self.u.gui()
        self.assertEqual(["eigen", "geholt", "beilage"], self._quellen(gui))

    def test_ohne_eigenen_ordner_bleiben_zwei(self):
        # Der Normalfall ab Werk - und er muss unveraendert bleiben.
        gui = self.u.gui(eigen="")
        self.assertEqual(["geholt", "beilage"], self._quellen(gui))

    def test_ein_nicht_vorhandener_ordner_faellt_heraus(self):
        gui = self.u.gui(eigen=os.path.join(self.u.basis, "gibtsnicht"))
        self.assertEqual(["geholt", "beilage"], self._quellen(gui))

    def test_derselbe_ordner_wird_nur_einmal_gelesen(self):
        # Wer den mitgelieferten Ordner ausdruecklich setzt, soll seine
        # Fassungen nicht doppelt in der Liste sehen.
        gui = self.u.gui(eigen=self.u.beilage)
        self.assertEqual(["eigen", "geholt"], self._quellen(gui))

    def test_die_schreibweise_spielt_dabei_keine_rolle(self):
        # Die gespeicherte Einstellung traegt Rueckstriche, der
        # mitgelieferte Pfad kommt aus _bundled_resource - derselbe Ordner
        # in zwei Schreibweisen darf nicht als zwei zaehlen.
        krumm = os.path.join(self.u.beilage, "..",
                             os.path.basename(self.u.beilage))
        gui = self.u.gui(eigen=krumm)
        self.assertEqual(["eigen", "geholt"], self._quellen(gui))


class VorratTests(unittest.TestCase):
    """Was am Ende in der Liste steht."""

    def setUp(self):
        self.u = _Umgebung()

    def tearDown(self):
        self.u.weg()

    def test_fassungen_aus_allen_wurzeln_stehen_drin(self):
        _lege_an(self.u.eigen, "0.9.9.9 debug", "libSceAmpr.sprx")
        _lege_an(self.u.geholt, "0.4.0 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual({"0.9.9.9", "0.4.0", "0.3.6.6"},
                         {e["version"] for e in alle})

    def test_die_neueste_steht_oben(self):
        """Mehrere Stellen nehmen den ersten Eintrag als "die neueste"."""
        _lege_an(self.u.eigen, "0.2.7.6 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual("0.3.6.6", alle[0]["version"])

    def test_dieselbe_fassung_zweimal_gibt_einen_eintrag(self):
        _lege_an(self.u.eigen, "0.3.6.6 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual(1, len(alle))

    def test_bei_gleichstand_gewinnt_der_eigene_ordner(self):
        # Wer eine Fassung selbst hinlegt, meint sie auch - und der Pfad
        # entscheidet, welche Datei spaeter uebertragen wird.
        _lege_an(self.u.eigen, "0.3.6.6 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual("eigen", alle[0]["quelle"])
        # Ueber realpath vergleichen: Der Scanner loest die Pfade auf, und
        # unter Windows steht im TEMP-Pfad sonst der 8.3-Kurzname
        # ("JBUSER~1") gegen den ausgeschriebenen.
        self.assertTrue(os.path.realpath(alle[0]["path"]).startswith(
            os.path.realpath(self.u.eigen)), alle[0]["path"])

    def test_der_rang_haengt_nicht_an_der_lesereihenfolge(self):
        # Die Beilage wird zuletzt gelesen und muss trotzdem verlieren -
        # und umgekehrt darf ein spaeter gelesener hoeherer Rang gewinnen.
        _lege_an(self.u.geholt, "0.3.6.6 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.eigen, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual("eigen", alle[0]["quelle"])

    def test_verschiedene_varianten_bleiben_zwei_eintraege(self):
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.beilage, "0.3.6.6 debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual(2, len(alle))

    def test_playgo_und_ampr_bleiben_getrennt(self):
        # Bewusst unter DERSELBEN Nummer und Variante: Nur so prueft der
        # Test den lib-Anteil des Entdopplungsschluessels. Lagen sie unter
        # verschiedenen Nummern, blieben sie schon deshalb zwei Eintraege.
        _lege_an(self.u.beilage, "0.3.6.6 no debug",
                 "libSceAmpr.sprx", "libScePlayGo.sprx")
        alle = self.u.gui()._ampr_alle_fassungen()
        self.assertEqual(2, len(alle))
        self.assertEqual({"libSceAmpr.sprx", "libScePlayGo.sprx"},
                         {e["lib"] for e in alle})

    def test_jede_fassung_ist_eindeutig_auffindbar(self):
        """Die Bedingung, unter der die getroffene Auswahl haelt.

        Beim Anwenden wird ueber (lib, version, variant) gesucht und dann
        ``matches[0]`` genommen. Gibt es dazu je zwei Eintraege, bekommt
        der Anwender eine andere Datei als die angeklickte.
        """
        _lege_an(self.u.eigen, "0.3.6.6 no debug", "libSceAmpr.sprx",
                 inhalt=b"eine")
        _lege_an(self.u.geholt, "0.3.6.6 no debug", "libSceAmpr.sprx",
                 inhalt=b"eine voellig andere Datei")
        alle = self.u.gui()._ampr_alle_fassungen()
        tripel = [(e["lib"], e["version"], e["variant"]) for e in alle]
        self.assertEqual(len(tripel), len(set(tripel)))

    def test_ein_ausdruecklicher_ordner_sticht_alles(self):
        _lege_an(self.u.gewaehlt, "0.3.6.6 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.eigen, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen(self.u.gewaehlt)
        self.assertEqual("gewaehlt", alle[0]["quelle"])

    def test_ohne_jede_fassung_bleibt_die_liste_leer(self):
        self.assertEqual([], self.u.gui()._ampr_alle_fassungen())


class FensteraufbauTests(unittest.TestCase):
    """Der Aufbau darf nicht auf einen fremden Ordner warten.

    Der selbst gesetzte Versionsspeicher kann alles sein - ein
    Netzlaufwerk, ein halbes Dateisystem. Gemessen am 05.09.2026: 200
    Fassungen kosteten 492 ms, 3000 fremde Dateien im Baum 105 ms. Beides
    hinge sonst am ersten Zeichnen des Hauptfensters.
    """

    def setUp(self):
        self.u = _Umgebung()

    def tearDown(self):
        self.u.weg()

    def test_beim_aufbau_bleibt_der_eigene_ordner_aussen_vor(self):
        gui = self.u.gui()
        quellen = [q for _o, q in gui._ampr_speicherwurzeln(nur_programmnah=True)]
        self.assertEqual(["geholt", "beilage"], quellen)

    def test_auch_eine_ausdrueckliche_angabe_wartet(self):
        gui = self.u.gui()
        quellen = [q for _o, q in
                   gui._ampr_speicherwurzeln(self.u.gewaehlt, nur_programmnah=True)]
        self.assertNotIn("gewaehlt", quellen)

    def test_die_liste_ist_dabei_nicht_leer(self):
        # Sonst sperrte das Integrationskaestchen kurz zu und ginge gleich
        # wieder auf - ein Flackern, das wie ein Fehler aussieht.
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        alle = self.u.gui()._ampr_alle_fassungen(nur_programmnah=True)
        self.assertEqual(1, len(alle))

    def test_der_eigene_ordner_kommt_nach(self):
        _lege_an(self.u.eigen, "0.9.9.9 no debug", "libSceAmpr.sprx")
        _lege_an(self.u.beilage, "0.3.6.6 no debug", "libSceAmpr.sprx")
        gui = self.u.gui()
        self.assertEqual(1, len(gui._ampr_alle_fassungen(nur_programmnah=True)))
        self.assertEqual(2, len(gui._ampr_alle_fassungen()))

    def test_der_aufbau_laedt_wirklich_nach(self):
        """Der Nachschlag muss angestossen werden, nicht nur moeglich sein.

        Ohne ihn saehe die Klappliste den eigenen Ordner nie wieder - der
        Mangel, der diese ganze Aenderung ausgeloest hat, waere fuer die
        Karte "Integration beim Erstellen" wieder da.
        """
        with io.open(APP.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        aufbau = [k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)
                  and any(isinstance(x, ast.Call)
                          and isinstance(x.func, ast.Attribute)
                          and x.func.attr == "_ampr_versionsliste_fuellen"
                          for x in ast.walk(k))]
        namen = {k.name for k in aufbau}
        self.assertIn("_ampr_versionsliste_nachladen", namen,
                      "Niemand laedt die volle Liste nach")
        # Und die Stelle, die schnell fuellt, muss den Nachschlag anstossen.
        anstoss = [k for k in aufbau if k.name != "_ampr_versionsliste_nachladen"
                   and any(isinstance(x, ast.Call)
                           and isinstance(x.func, ast.Attribute)
                           and x.func.attr == "_ampr_versionsliste_nachladen"
                           for x in ast.walk(k))]
        self.assertTrue(anstoss, "Der Nachschlag wird nirgends angestossen")


class AufrufTests(unittest.TestCase):
    """Dass die Stellen, um die es ging, den neuen Leser wirklich nehmen.

    Geprueft wird ueber den Syntaxbaum der einzelnen Methode, nicht ueber
    eine Zeichenkettensuche in der ganzen Datei: Ein ``assertIn`` faende
    den Aufruf auch dann noch, wenn er in einer voellig anderen Methode
    stuende.
    """

    @classmethod
    def setUpClass(cls):
        with io.open(APP.__file__, "rb") as fh:
            cls.baum = ast.parse(fh.read().decode("utf-8"))
        cls.methoden = {k.name: k for k in ast.walk(cls.baum)
                        if isinstance(k, ast.FunctionDef)}

    def _rufe(self, methode: str) -> set[str]:
        knoten = self.methoden.get(methode)
        self.assertIsNotNone(knoten, "%s gibt es nicht mehr" % methode)
        return {k.func.attr for k in ast.walk(knoten)
                if isinstance(k, ast.Call)
                and isinstance(k.func, ast.Attribute)}

    def test_die_klappliste_beim_erstellen_sieht_alles(self):
        rufe = self._rufe("_ampr_versionsliste_fuellen")
        self.assertIn("_ampr_alle_fassungen", rufe)
        self.assertNotIn("_ampr_scan_version_store", rufe)

    def test_die_playgo_zuordnung_sieht_alles(self):
        rufe = self._rufe("_ampr_playgo_zur_version")
        self.assertIn("_ampr_alle_fassungen", rufe)
        self.assertNotIn("_ampr_scan_version_store", rufe)

    def test_die_aktualisierung_sieht_alles(self):
        rufe = self._rufe("_ampr_updates_arbeiten")
        self.assertIn("_ampr_alle_fassungen", rufe)
        self.assertNotIn("_ampr_scan_version_store", rufe)

    def test_die_auswahllisten_des_managers_sehen_alles(self):
        rufe = self._rufe("_refresh_versions")
        self.assertIn("_ampr_alle_fassungen", rufe)
        self.assertNotIn("_ampr_scan_version_store", rufe)

    def test_der_automatiklauf_sieht_alles(self):
        rufe = self._rufe("_ampr_gen_automatik")
        self.assertIn("_ampr_alle_fassungen", rufe)
        self.assertNotIn("_ampr_scan_version_store", rufe)

    def test_die_einloesung_sieht_alles(self):
        """Anzeige und Einloesung muessen denselben Vorrat sehen.

        Die im Manager getroffene Wahl wird beim Anwenden ueber
        (lib, version, variant) wiedergefunden. Saehe die Einloesung
        weniger als die Anzeige, meldete sie "nicht im Speicher" und
        uebersprunge die Bibliothek wortlos.
        """
        rufe = self._rufe("_mode_ampr_manager")
        self.assertIn("_ampr_alle_fassungen", rufe)
        # _ampr_scan_einen_speicher steht dort zu Recht: Der Waechter
        # "im Versionsordner liegt nichts" meint den GEWAEHLTEN Ordner
        # und muss weiter fallen koennen, auch wenn eine andere Wurzel
        # etwas beisteuert.
        self.assertIn("_ampr_scan_einen_speicher", rufe)
        self.assertNotIn("_ampr_scan_version_store", rufe)

    def test_der_waechter_im_uebertragungsweg_meldet_noch(self):
        """Der Waechter selbst, nicht nur sein Leser.

        Ohne ihn schriebe ein Hotswap ungefragt Fassungen in den
        fakelib-Ordner der laufenden PS5, wo er heute abbricht und den
        Grund nennt.
        """
        knoten = self.methoden.get("_ampr_ftp_apply_set")
        self.assertIsNotNone(knoten)
        texte = {k.value for k in ast.walk(knoten)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        self.assertIn("ampr.store_empty", texte)

    def test_der_uebertragungsweg_meint_weiter_genau_einen_ordner(self):
        """Die Gegenrichtung - nicht alles gehoert zusammengefuehrt.

        ``_ampr_ftp_apply_set`` schreibt ein Set in den fakelib-Ordner der
        laufenden Konsole. Dort ist wirklich ein einzelner Ordner gemeint,
        und der Waechter davor ("im Versionsordner liegt nichts") muss
        fallen koennen.
        """
        rufe = self._rufe("_ampr_ftp_apply_set")
        self.assertIn("_ampr_scan_version_store", rufe)
        self.assertNotIn("_ampr_alle_fassungen", rufe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
