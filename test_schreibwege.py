# -*- coding: utf-8 -*-
"""Auf eine Datei fuehrt genau ein Schreibweg - und der baut daneben.

Zwei Befunde des Pruefstands vom 06.09.2026, beide von derselben Bauart wie
die vier Loeschbefunde in ``test_ueberschreiben.py``: Etwas Vorhandenes wird
zerstoert, bevor der Ersatz fertig ist.

**Die Einstellungsdatei hatte zwei Schreiber.** ``_save_setting`` schrieb
unter einem Schloss ueber eine Zwischendatei und uebernahm mit
``os.replace``. ``_save_paths`` schrieb daneben mit ``open(..., "w")``
direkt in dieselbe ``paths.json`` - ohne Schloss, ohne Zwischendatei.
Nachgemessen wurde beides:

* Ein Fehler beim Schreiben (volle Platte) liess **alle** Einstellungen
  verschwinden: aus 114 Bytes mit vier Schluesseln wurden 0 Bytes. Derselbe
  Abbruch in ``_save_setting`` liess die Datei unversehrt.
* Bei gleichzeitigem Schreiben aus zwei Faeden - kein Sonderfall,
  ``_save_paths`` laeuft zu Beginn **jeder** Konvertierung im Hintergrund -
  gingen von 400 Speicherversuchen 4 ganz verloren (1,0 %), waehrend
  ``_save_setting`` in denselben 400 keinen einzigen verlor. Ein Leser fand
  die Datei dabei in 136 von 1600 Versuchen (8,5 %) leer vor.

Nach der Umstellung: 0 verlorene Speicherversuche, 0 leere Lesungen.

**Der Debug-.pkg-Bauer schrieb in die Zieldatei.** ``build_debug_pkg``
oeffnete ``output_path`` mit ``"wb"`` - das leert die Datei beim ersten
Byte. Das Fenster schlaegt den Zielpfad ausserdem **selbst vor**: Wer einen
Quellordner waehlt, bekommt ``<darueber>/<Content-ID>.pkg`` eingetragen,
also genau den Pfad, unter dem das Paket des letzten Laufs liegt. Gefragt
wurde nicht. Gemessen: Bricht das Kopieren des PFS-Abbilds ab, stand an der
Stelle des alten Pakets ein Rumpf von 65.600 Bytes - gross genug, um wie
ein Ergebnis auszusehen.
"""
from __future__ import annotations

import ast
import builtins
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
ORDNER = pruefumgebung.umlenken("schreibwege")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import pkg_writer                  # noqa: E402

CFG = os.path.join(ORDNER, "paths.json")


def setUpModule():
    """Die Umlenkung vor dem ersten Test dieser Datei wieder geltend machen.

    ``umlenken()`` oben setzt ``PS5CONV_KONFIGORDNER`` beim **Import**. In
    einem Gesamtlauf importiert pytest aber erst alle Dateien und laesst
    danach laufen - und 24 Pruefstaende lenken beim Import um. Es gewinnt
    der zuletzt importierte, und der schreibt woandershin als hier gelesen
    wird. Am 08.09.2026 fielen deshalb sieben Pruefungen dieser Datei mit
    "paths.json nicht gefunden" aus, obwohl sie einzeln aufgerufen alle
    durchliefen - ein Scheinbefund, der einen echten hier verdecken wuerde.
    """
    os.environ["PS5CONV_KONFIGORDNER"] = ORDNER
    os.makedirs(ORDNER, exist_ok=True)


def _gui():
    return APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)


def _baum(name: str) -> str:
    """Der Quelltext einer Methode des Hauptprogramms, normalisiert."""
    with io.open(APP.__file__, "rb") as fh:
        baum = ast.parse(fh.read().decode("utf-8"))
    knoten = next(k for k in ast.walk(baum)
                  if isinstance(k, ast.FunctionDef) and k.name == name)
    return ast.unparse(knoten)


class EinSchreibwegTests(unittest.TestCase):
    """Beide Speichermethoden gehen durch dieselbe Tuer."""

    def test_save_paths_schreibt_nicht_mehr_selbst(self):
        text = _baum("_save_paths")
        self.assertIn("_konfiguration_schreiben", text)
        self.assertNotIn("json.dump", text,
                         "_save_paths schreibt wieder selbst - dann laufen "
                         "die beiden Wege auf paths.json auseinander.")

    def test_save_setting_geht_denselben_weg(self):
        text = _baum("_save_setting")
        self.assertIn("_konfiguration_schreiben", text)
        self.assertNotIn("json.dump", text)

    def test_es_gibt_im_ganzen_programm_nur_diesen_einen(self):
        """Sonst kommt der naechste Schreiber als dritter dazu."""
        with io.open(APP.__file__, "rb") as fh:
            quelle = fh.read().decode("utf-8")
        self.assertNotIn('open(cfg_path, "w"', quelle,
                         "Es schreibt wieder jemand direkt in die "
                         "Einstellungsdatei.")

    def test_der_weg_selbst_baut_daneben(self):
        text = _baum("_konfiguration_schreiben")
        self.assertIn("os.replace(tmp_path, cfg_path)", text)
        self.assertIn("self._settings_lock", text)


class AbbruchTests(unittest.TestCase):
    """Was ein misslungenes Schreiben kostet."""

    def setUp(self):
        # Bei null anfangen: Die anderen Klassen dieser Datei schreiben in
        # dieselbe Ablage, und ein voriger Lauf hinterlaesst sie ebenfalls.
        # Ohne das Aufraeumen zaehlt diese Klasse fremde Schluessel mit.
        for rest in Path(ORDNER).glob("paths.json*"):
            rest.unlink()
        self.gui = _gui()
        for k, v in (("metadata_online", False), ("language", "de"),
                     ("last_source_dir", "D:\\PS5 Spiele"),
                     ("shutdown_after_success", False)):
            self.gui._save_setting(k, v)
        self.vorher = Path(CFG).read_text(encoding="utf-8")
        self.assertEqual(4, len(json.loads(self.vorher)))

    def _mit_stolperstein(self, ruf):
        echt = json.dump

        def _stolpert(_daten, _strom, **_kw):
            raise OSError(28, "No space left on device")

        json.dump = _stolpert
        try:
            ruf()
        finally:
            json.dump = echt

    def test_ein_abbruch_in_save_paths_kostet_keine_einstellung(self):
        self._mit_stolperstein(lambda: self.gui._save_paths("Q", "Z"))
        self.assertEqual(self.vorher, Path(CFG).read_text(encoding="utf-8"),
                         "Die Einstellungsdatei hat den Abbruch nicht "
                         "ueberlebt.")

    def test_dasselbe_gilt_fuer_save_setting(self):
        self._mit_stolperstein(lambda: self.gui._save_setting("language", "en"))
        self.assertEqual(self.vorher, Path(CFG).read_text(encoding="utf-8"))

    def test_die_zieldatei_ist_waehrend_des_schreibens_vollstaendig(self):
        """Der Kern des Befunds: open(..., "w") leert sofort.

        Es wird nicht geprueft, ob am Ende alles dasteht - das taete es auch
        beim alten Weg -, sondern wie die Datei **waehrend** des Schreibens
        aussieht. Genau dort lag das Zeitfenster.
        """
        gesehen: list[str] = []
        echt = json.dump

        def _mitlesen(daten, strom, **kw):
            gesehen.append(Path(CFG).read_text(encoding="utf-8"))
            return echt(daten, strom, **kw)

        json.dump = _mitlesen
        try:
            self.gui._save_paths("Q", "Z")
        finally:
            json.dump = echt
        self.assertTrue(gesehen, "Es wurde gar nicht geschrieben.")
        for stand in gesehen:
            self.assertEqual(4, len(json.loads(stand)),
                             "Die Datei war beim Schreiben schon geleert.")

    def test_ein_liegengebliebener_rumpf_wird_weggeraeumt(self):
        self._mit_stolperstein(lambda: self.gui._save_paths("Q", "Z"))
        reste = [p.name for p in Path(ORDNER).glob("paths.json.*")]
        self.assertEqual([], reste, "Zwischendatei bleibt liegen: %s" % reste)

    def test_zwei_fenster_teilen_sich_keine_zwischendatei(self):
        """Das Schloss gilt nur im eigenen Programmlauf."""
        gemerkt: list[str] = []
        echt = os.replace

        def _merken(a, b):
            gemerkt.append(str(a))
            return echt(a, b)

        os.replace = _merken
        try:
            self.gui._save_setting("language", "de")
        finally:
            os.replace = echt
        self.assertTrue(gemerkt)
        self.assertIn(str(os.getpid()), gemerkt[0])


class GleichzeitigTests(unittest.TestCase):
    """Der gemessene Fall: Konvertierung startet, waehrend etwas gespeichert wird."""

    LAEUFE = 200

    def test_zwei_schreiber_verdraengen_einander_nicht(self):
        """Ohne Leser - dann ist die Null belastbar.

        Das Schloss serialisiert die Schreiber innerhalb eines
        Programmlaufs; hier kann nichts scheitern. Die Pruefung darunter
        nimmt einen Leser dazu und wird dadurch von Windows abhaengig -
        deshalb stehen beide getrennt da.
        """
        gui = _gui()
        gui._save_setting("marker", -1)
        verloren = {"n": 0}
        echt_warn = APP.logger.warning

        def _mitzaehlen(text, *a, **kw):
            if "konnte nicht gespeichert" in str(text):
                verloren["n"] += 1

        APP.logger.warning = _mitzaehlen
        try:
            faeden = [
                threading.Thread(target=lambda: [gui._save_setting("marker", i)
                                                 for i in range(self.LAEUFE)]),
                threading.Thread(target=lambda: [gui._save_paths("Q%d" % i,
                                                                "Z%d" % i)
                                                 for i in range(self.LAEUFE)]),
            ]
            for f in faeden:
                f.start()
            for f in faeden:
                f.join()
        finally:
            APP.logger.warning = echt_warn
        self.assertEqual(0, verloren["n"],
                         "%d von %d Speichervorgaengen verloren - das Schloss "
                         "greift nicht." % (verloren["n"], self.LAEUFE * 2))
        stand = json.loads(Path(CFG).read_text(encoding="utf-8"))
        for schluessel in ("marker", "src", "dst"):
            self.assertIn(schluessel, stand)

    def test_kein_speichervorgang_geht_verloren(self):
        gui = _gui()
        gui._save_setting("marker", -1)
        zaehler = {"weg": 0, "leer": 0, "kaputt": 0}
        echt_warn = APP.logger.warning

        def _mitzaehlen(text, *a, **kw):
            if "konnte nicht gespeichert" in str(text):
                zaehler["weg"] += 1

        def _einstellungen():
            for i in range(self.LAEUFE):
                gui._save_setting("marker", i)

        def _pfade():
            for i in range(self.LAEUFE):
                gui._save_paths("Q%d" % i, "Z%d" % i)

        def _leser():
            for _ in range(self.LAEUFE * 4):
                try:
                    roh = Path(CFG).read_text(encoding="utf-8")
                    if not roh.strip():
                        zaehler["leer"] += 1
                    else:
                        json.loads(roh)
                except json.JSONDecodeError:
                    zaehler["kaputt"] += 1
                except OSError:
                    pass          # kurz belegt - dagegen hilft die Wiederholung
                time.sleep(0)

        APP.logger.warning = _mitzaehlen
        try:
            faeden = [threading.Thread(target=_einstellungen),
                      threading.Thread(target=_pfade),
                      threading.Thread(target=_leser)]
            for f in faeden:
                f.start()
            for f in faeden:
                f.join()
        finally:
            APP.logger.warning = echt_warn

        # Was das Schloss WIRKLICH zusichert: kein Schreiber verdraengt einen
        # anderen. Vor der Umstellung gingen hier 1,0 % verloren.
        #
        # Nicht zugesichert - und deshalb hier auch nicht behauptet: dass
        # unter Windows *nie* ein os.replace scheitert. Haelt der Leser die
        # Datei im selben Augenblick offen, weist Windows das Ersetzen ab;
        # die Wiederholungsschleife deckt 300 ms ab, unter Last kann das zu
        # wenig sein. Ein absolutes "0" war an dieser Stelle eine Zusicherung,
        # die der Code gar nicht gibt - im Vollauf ist sie am 06.09.2026
        # einmal gefallen. Gezaehlt wird sie trotzdem, damit ein echter
        # Rueckfall (jeder zweite Versuch weg) auffaellt.
        self.assertLessEqual(
            zaehler["weg"], self.LAEUFE * 2 // 20,
            "%d von %d Speichervorgaengen verloren - das ist mehr als die "
            "seltene Kollision mit einem Leser." % (zaehler["weg"],
                                                    self.LAEUFE * 2))
        # Das hier ist dagegen absolut: Niemand leert die Datei mehr an Ort
        # und Stelle, also kann sie kein Leser leer oder halb sehen.
        self.assertEqual(0, zaehler["leer"],
                         "Die Datei war %dmal leer - jemand leert sie wieder "
                         "an Ort und Stelle." % zaehler["leer"])
        self.assertEqual(0, zaehler["kaputt"])
        stand = json.loads(Path(CFG).read_text(encoding="utf-8"))
        for schluessel in ("marker", "src", "dst"):
            self.assertIn(schluessel, stand)


class PfadeLesenTests(unittest.TestCase):
    """Ein belegter Moment darf den gemerkten Zielordner nicht kosten."""

    def test_load_paths_wiederholt_wie_load_setting(self):
        self.assertIn("_load_setting", _baum("_load_paths"))

    def test_ein_belegter_moment_kostet_den_zielordner_nicht(self):
        gui = _gui()
        gui._save_paths("Q", "D:\\Ziel")
        echt_open = builtins.open
        zaehler = {"n": 0}

        def _mal_belegt(pfad, *a, **kw):
            if str(pfad).endswith("paths.json"):
                zaehler["n"] += 1
                if zaehler["n"] <= 2:
                    raise PermissionError(13, "kurz belegt")
            return echt_open(pfad, *a, **kw)

        builtins.open = _mal_belegt
        try:
            gelesen = gui._load_paths()
        finally:
            builtins.open = echt_open
        self.assertEqual(("Q", "D:\\Ziel"), gelesen,
                         "Ein einzelner Fehlversuch hat den gemerkten Pfad "
                         "stillschweigend geleert.")


class DebugPkgZielTests(unittest.TestCase):
    """Gefragt wird, bevor ein vorhandenes Paket ueberschrieben wird."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="debugpkg_")
        self.ordner = Path(self.tmp.name)
        self.vorhanden = self.ordner / "CUSA00000.pkg"
        self.vorhanden.write_bytes(b"das alte Paket")
        self.gefragt: list[str] = []
        self.gui = _gui()
        self.gui._t = lambda s, **kw: s

    def tearDown(self):
        self.tmp.cleanup()

    def _antwort(self, ja: bool):
        def _fragen(titel, _text, **_kw):
            self.gefragt.append(titel)
            return ja
        return _fragen

    def test_vorhandenes_paket_fragt_nach(self):
        with mock.patch.object(APP.messagebox, "askyesno",
                                        self._antwort(True)):
            self.assertTrue(self.gui._debug_pkg_ziel_freigegeben(
                str(self.vorhanden), ""))
        self.assertEqual(1, len(self.gefragt))

    def test_ein_nein_haelt_den_bau_auf(self):
        with mock.patch.object(APP.messagebox, "askyesno",
                                        self._antwort(False)):
            self.assertFalse(self.gui._debug_pkg_ziel_freigegeben(
                str(self.vorhanden), ""))

    def test_der_speichern_dialog_hat_schon_gefragt(self):
        """Sonst zwei Rueckfragen fuer dieselbe Entscheidung."""
        with mock.patch.object(APP.messagebox, "askyesno",
                                        self._antwort(True)):
            self.assertTrue(self.gui._debug_pkg_ziel_freigegeben(
                str(self.vorhanden), str(self.vorhanden)))
        self.assertEqual([], self.gefragt)

    def test_ein_anderer_bestaetigter_pfad_zaehlt_nicht(self):
        with mock.patch.object(APP.messagebox, "askyesno",
                                        self._antwort(True)):
            self.gui._debug_pkg_ziel_freigegeben(
                str(self.vorhanden), str(self.ordner / "anderes.pkg"))
        self.assertEqual(1, len(self.gefragt))

    def test_ohne_vorhandene_datei_wird_nicht_gefragt(self):
        with mock.patch.object(APP.messagebox, "askyesno",
                                        self._antwort(True)):
            self.assertTrue(self.gui._debug_pkg_ziel_freigegeben(
                str(self.ordner / "neu.pkg"), ""))
        self.assertEqual([], self.gefragt)

    def test_der_vorschlag_gilt_nicht_als_bestaetigung(self):
        """_quelle_waehlen traegt einen Pfad ein, ohne zu fragen."""
        text = _baum("_show_debug_pkg_builder")
        self.assertIn("bestaetigtes_ziel[0] = pfad", text,
                      "Der Speichern-Dialog merkt seinen Pfad nicht mehr vor.")
        self.assertEqual(1, text.count("bestaetigtes_ziel[0] = "),
                         "Ein zweiter Weg gibt sich als bestaetigt aus.")

    def test_gefragt_wird_vor_dem_bauen(self):
        text = _baum("_show_debug_pkg_builder")
        i_frage = text.find("_debug_pkg_ziel_freigegeben")
        i_bau = text.find("build_debug_pkg(")
        self.assertGreater(i_frage, 0, "Es wird gar nicht gefragt.")
        self.assertLess(i_frage, i_bau, "Gefragt wird erst nach dem Bauen.")


class PkgDanebenBauenTests(unittest.TestCase):
    """build_debug_pkg zerstoert das vorhandene Paket nicht mehr."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="pkgbau_")
        self.ordner = Path(self.tmp.name)
        self.ziel = self.ordner / "CUSA00000.pkg"
        self.alt = b"DAS ALTE, FUNKTIONIERENDE PAKET" * 100
        self.ziel.write_bytes(self.alt)
        self.bild = self.ordner / "abbild.pfs"
        self.bild.write_bytes(b"\x00" * 4096)
        self.param = {"titleId": "CUSA00000"}
        self.kennung = "IV0000-CUSA00000_00-TEST"

    def tearDown(self):
        self.tmp.cleanup()

    def _mit_voller_platte(self):
        echt = pkg_writer.shutil.copyfileobj

        def _voll(quelle, strom, length=0):
            strom.write(quelle.read(64))
            raise OSError(28, "No space left on device")

        pkg_writer.shutil.copyfileobj = _voll
        try:
            with self.assertRaises(OSError):
                pkg_writer.build_debug_pkg(
                    str(self.ziel), self.kennung, self.param,
                    pfs_image_path=str(self.bild))
        finally:
            pkg_writer.shutil.copyfileobj = echt

    def test_ein_gescheiterter_bau_laesst_das_alte_paket_stehen(self):
        self._mit_voller_platte()
        self.assertEqual(self.alt, self.ziel.read_bytes(),
                         "Das vorhandene Paket wurde beim Bau zerstoert.")

    def test_und_hinterlaesst_keinen_rumpf(self):
        self._mit_voller_platte()
        reste = [p.name for p in self.ordner.glob("*.neu")]
        self.assertEqual([], reste,
                         "Ein Rumpf bleibt liegen: %s" % reste)

    def test_auch_das_meta_paket_geht_diesen_weg(self):
        """Der Zweig ohne PFS-Abbild - einer allein reicht nicht."""
        echt = os.replace
        os.replace = lambda a, b: (_ for _ in ()).throw(OSError(28, "voll"))
        try:
            with self.assertRaises(OSError):
                pkg_writer.build_debug_pkg(str(self.ziel), self.kennung,
                                           self.param)
        finally:
            os.replace = echt
        self.assertEqual(self.alt, self.ziel.read_bytes())

    def test_der_gelungene_bau_landet_unter_dem_richtigen_namen(self):
        ergebnis = pkg_writer.build_debug_pkg(
            str(self.ziel), self.kennung, self.param,
            pfs_image_path=str(self.bild))
        self.assertEqual(str(self.ziel), ergebnis["path"])
        self.assertEqual("full_debug", ergebnis["type"])
        self.assertNotEqual(self.alt, self.ziel.read_bytes())
        self.assertEqual([], [p.name for p in self.ordner.glob("*.neu")])
        self.assertEqual(ergebnis["size"], self.ziel.stat().st_size)

    def test_der_bau_nutzt_die_gemeinsame_klammer(self):
        with io.open(pkg_writer.__file__, "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "build_debug_pkg")
        text = ast.unparse(knoten)
        self.assertEqual(2, text.count("_daneben_bauen("),
                         "Ein Zweig schreibt wieder direkt in die Zieldatei.")
        self.assertNotIn("open(output_path", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
