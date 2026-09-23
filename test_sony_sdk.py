# -*- coding: utf-8 -*-
"""Der zweite Bauweg: PKG bauen mit Sonys Publishing Tools aus ``libs/sdk``.

Der Baukasten selbst liegt hier nicht und darf hier nie liegen - er gehoert
Sony. Geprueft wird deshalb alles, was **ohne** ihn messbar ist, und das ist
mehr, als es klingt:

* Erkennung: Was fehlt, und was heisst "vollstaendig"?
* Die **Dateinamen-Regel**, an der ein Bau sonst erst nach Stunden
  scheitert (``img_create`` weist ``%``, ``;``, Nicht-ASCII und Namen mit
  Schlusspunkt ab).
* Die **Befehlszeile** - sie wird gebaut, ohne sie auszufuehren.
* Das GP5-Projekt, das der SDK bekommt.

Was hier **nicht** geprueft werden kann: ob ein echter Lauf gelingt und ob
das Paket auf der Konsole startet. Das haengt am Baukasten des Anwenders -
ein unveraendertes SDK schreibt ein signiertes Paket, das eine gejailbreakte
Konsole nicht annimmt.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import gp5_project                  # noqa: E402
from ps5_validator.utils import sony_sdk as sdk              # noqa: E402
from ps5_validator.utils.i18n import STRINGS                 # noqa: E402

PROJEKT = Path(__file__).resolve().parent


def _baukasten_bauen(libs: Path, vollstaendig: bool = True,
                     ohne: str = "") -> Path:
    """Legt einen Schein-Baukasten an - Dateien mit Inhalt, kein Programm."""
    wurzel = libs / sdk.ORDNER
    for teil in sdk.PFLICHT + (sdk.KUER if vollstaendig else ()):
        if teil == ohne:
            continue
        pfad = wurzel / teil
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(b"MZ")
    wurzel.mkdir(parents=True, exist_ok=True)
    return wurzel


class ErkennungTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.libs = Path(self._tmp.name) / "libs"
        self.libs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_ohne_ordner_nichts(self):
        stand = sdk.pruefen(str(self.libs))
        self.assertFalse(stand.vorhanden)
        self.assertEqual("", stand.programm)

    def test_vollstaendiger_baukasten(self):
        _baukasten_bauen(self.libs)
        stand = sdk.pruefen(str(self.libs))
        self.assertTrue(stand.vorhanden)
        self.assertTrue(stand.vollstaendig)
        self.assertTrue(stand.programm.endswith("prospero-pub-cmd.exe"))

    def test_ohne_wandler_baut_trotzdem(self):
        """Die ext-Wandler sind Kuer: ohne sie baut der SDK, wandelt nur nicht."""
        _baukasten_bauen(self.libs, vollstaendig=False)
        stand = sdk.pruefen(str(self.libs))
        self.assertTrue(stand.vorhanden)
        self.assertFalse(stand.vollstaendig)
        self.assertEqual(len(sdk.KUER), len(stand.fehlende_kuer))

    def test_fehlende_pflichtdatei_nennt_sie(self):
        _baukasten_bauen(self.libs, ohne=sdk.PFLICHT[1])
        stand = sdk.pruefen(str(self.libs))
        self.assertFalse(stand.vorhanden)
        self.assertEqual([sdk.PFLICHT[1]], stand.fehlende)


class NamenTests(unittest.TestCase):
    """Die gemessene Regel: ASCII ausser % und ;, kein Schlusspunkt."""

    def test_zulaessige_namen(self):
        for name in ("eboot.bin", "param.json", "a b c.dat", "Datei-1_2.txt",
                     "klammer(1).bin", "raute#1.bin", "komma,1.bin"):
            with self.subTest(name=name):
                self.assertTrue(sdk.name_ist_zulaessig(name))

    def test_abgewiesene_namen(self):
        for name in ("50% rabatt.bin", "datei;.bin", "umlaut_ä.bin",
                     "punkt.", "", "tab\tname.bin"):
            with self.subTest(name=name):
                self.assertFalse(sdk.name_ist_zulaessig(name))

    def test_namen_pruefen_findet_dateien_und_ordner(self):
        with tempfile.TemporaryDirectory() as ordner:
            wurzel = Path(ordner)
            (wurzel / "sce_sys").mkdir()
            (wurzel / "sce_sys" / "param.json").write_bytes(b"{}")
            (wurzel / "eboot.bin").write_bytes(b"x")
            (wurzel / "100%.bin").write_bytes(b"x")
            (wurzel / "ordner;1").mkdir()
            treffer = sdk.namen_pruefen(str(wurzel))
        self.assertEqual({"100%.bin", "ordner;1"},
                         {os.path.basename(t) for t in treffer})

    def test_sauberer_ordner_meldet_nichts(self):
        with tempfile.TemporaryDirectory() as ordner:
            (Path(ordner) / "eboot.bin").write_bytes(b"x")
            self.assertEqual([], sdk.namen_pruefen(ordner))

    def test_grenze_bricht_ab(self):
        with tempfile.TemporaryDirectory() as ordner:
            for nummer in range(10):
                (Path(ordner) / ("datei;%d.bin" % nummer)).write_bytes(b"x")
            self.assertEqual(3, len(sdk.namen_pruefen(ordner, grenze=3)))

    def test_pruefung_meldet_sich(self):
        """Ein Durchlauf ueber einen ganzen Spielordner darf nicht stumm sein."""
        stand = []
        with tempfile.TemporaryDirectory() as ordner:
            (Path(ordner) / "eboot.bin").write_bytes(b"x")
            sdk.namen_pruefen(ordner, melden=stand.append)
        self.assertTrue(stand)


class BefehlTests(unittest.TestCase):
    """Die Befehlszeile - pruefbar, ohne den Baukasten zu besitzen."""

    def test_grundform(self):
        befehl = sdk.befehl_bauen("pub.exe", "p.gp5", "raus")
        self.assertEqual(["pub.exe", "img_create", "--oformat", "nwonly",
                          "p.gp5", "raus"], befehl)

    def test_projekt_steht_vor_dem_ziel(self):
        """Vertauscht wuerde der SDK das Projekt ueberschreiben wollen."""
        befehl = sdk.befehl_bauen("pub.exe", "p.gp5", "raus")
        self.assertLess(befehl.index("p.gp5"), befehl.index("raus"))

    def test_stufe_wird_begrenzt(self):
        for eingabe, erwartet in ((7, "7"), (-99, str(sdk.STUFE_MIN)),
                                  (99, str(sdk.STUFE_MAX))):
            with self.subTest(stufe=eingabe):
                befehl = sdk.befehl_bauen("p.exe", "p.gp5", "raus",
                                          stufe=eingabe)
                self.assertEqual(erwartet,
                                 befehl[befehl.index("--compression_level") + 1])

    def test_ohne_stufe_bleibt_die_vorgabe_des_baukastens(self):
        self.assertNotIn("--compression_level",
                         sdk.befehl_bauen("p.exe", "p.gp5", "raus"))

    def test_grundpaket_macht_ein_delta(self):
        befehl = sdk.befehl_bauen("p.exe", "p.gp5", "raus",
                                  grundpaket="basis.pkg")
        self.assertEqual("basis.pkg",
                         befehl[befehl.index("--ref_pkg_path") + 1])

    def test_ohne_baukasten_kein_lauf(self):
        with self.assertRaises(sdk.SdkFehler):
            sdk.bauen(sdk.SdkStand(), "p.gp5", "raus")


class ProjektTests(unittest.TestCase):

    def test_gp5_wird_lesbar_geschrieben(self):
        with tempfile.TemporaryDirectory() as ordner:
            quelle = Path(ordner) / "spiel"
            quelle.mkdir()
            ziel = str(Path(ordner) / "arbeit" / "projekt.gp5")
            sdk.projekt_schreiben(str(quelle), ziel,
                                  content_id="UP9000-PPSA01234_00-TEST")
            self.assertTrue(os.path.isfile(ziel))
            gelesen = gp5_project.read_from(ziel)
        self.assertEqual("UP9000-PPSA01234_00-TEST",
                         gelesen.volume.package.content_id)
        self.assertEqual(gp5_project.Gp5VolumeType.APP,
                         gelesen.volume.volume_type)
        self.assertTrue(gelesen.rootdir.src_path.endswith("spiel"))

    def test_art_waehlt_den_volumentyp(self):
        with tempfile.TemporaryDirectory() as ordner:
            quelle = str(Path(ordner) / "q")
            os.makedirs(quelle)
            for art, erwartet in (("app", gp5_project.Gp5VolumeType.APP),
                                  ("ac", gp5_project.Gp5VolumeType.AC),
                                  ("unsinn", gp5_project.Gp5VolumeType.APP)):
                ziel = str(Path(ordner) / ("%s.gp5" % art))
                sdk.projekt_schreiben(quelle, ziel, art=art)
                with self.subTest(art=art):
                    self.assertEqual(erwartet,
                                     gp5_project.read_from(ziel).volume.volume_type)


class TexteTests(unittest.TestCase):

    SCHLUESSEL = ("sdk.use", "sdk.hint_ready", "sdk.hint_partial",
                  "sdk.hint_missing", "sdk.log_missing", "sdk.log_names",
                  "sdk.log_bad_names", "sdk.log_no_contentid",
                  "sdk.log_project", "sdk.log_failed", "sdk.log_no_output",
                  "sdk.log_done")

    def test_zweisprachig(self):
        for schluessel in self.SCHLUESSEL:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))

    def test_hinweis_warnt_vor_dem_signierten_paket(self):
        """Ein unveraendertes SDK baut nichts, was die Konsole annimmt."""
        text = STRINGS["sdk.hint_ready"]["de"]
        self.assertIn("signiert", text)

    def test_hinweis_nennt_die_herkunft(self):
        self.assertIn("Sony", STRINGS["sdk.hint_missing"]["de"])


class VerdrahtungTests(unittest.TestCase):

    def test_fenster_kennt_den_bauweg(self):
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        self.assertIn("def _sdk_bauweg(", quelle)
        self.assertIn('self._sdk_bauweg(', quelle)
        self.assertIn('("sdk", self._t("sdk.use"), sdk_var)', quelle,
                      "das Kaestchen muss in der Schalterreihe stehen")

    def test_ohne_baukasten_bleibt_das_kaestchen_grau(self):
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
            encoding="utf-8")
        self.assertIn("if not sdk_stand.vorhanden:", quelle)

    def test_diagnose_nennt_den_ordner(self):
        from ps5_validator.utils import eigene_bibliotheken
        self.assertIn("sdk", eigene_bibliotheken.NICHT_BENUTZTE_ORDNER)


if __name__ == "__main__":
    unittest.main()
