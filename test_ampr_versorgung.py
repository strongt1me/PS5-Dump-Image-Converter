# -*- coding: utf-8 -*-
"""Ein APR-Titel wird aus dem Versionsspeicher versorgt, nicht per Rueckfrage.

**Was schiefging.** ``_prepare_ampr_support`` laeuft am Ende jedes
Aufgabe-7-Laufs. Fehlten die Bibliotheken im fakelib-Ordner, fragte es
ausschliesslich nach ``ampr_emu_folder`` - einer fuenften Einstellung neben
``ampr_store_dir``, und einer, die einen **flachen** Ordner verlangt: beide
``.sprx`` direkt nebeneinander. Genau diesen Aufbau hat der Versionsspeicher
nicht; dort liegt jede Fassung in ``<Fassung> <Variante>/``.

Gemessen am 05.09.2026 mit den 13 mitgelieferten Fassungen: Der Lauf brach
im Automationsbetrieb mit ``log.auto.0148`` ab, obwohl die Bibliotheken
danebenlagen. In der Oberflaeche kam ein Ordner-Auswahldialog - direkt
nachdem der Anwender in Aufgabe 7 aus dreizehn Fassungen gewaehlt hatte.

**Der alte Weg bleibt.** Wer einen flachen Ordner eingestellt hat, soll ihn
behalten; der Versionsspeicher ist nur der erste Griff.
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
pruefumgebung.umlenken("ampr_versorgung")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


def _fassung(wurzel: str, ordnername: str, *libs: str) -> None:
    ziel = os.path.join(wurzel, ordnername)
    os.makedirs(ziel, exist_ok=True)
    for lib in libs:
        with open(os.path.join(ziel, lib), "wb") as fh:
            fh.write(b"x" * 64)


class _Lage:
    """Ein Dump ohne fakelib und ein Versionsspeicher daneben."""

    def __init__(self, mit_playgo: bool = True, leer: bool = False) -> None:
        self.basis = tempfile.mkdtemp(prefix="ampr_versorgung_")
        self.dump = os.path.join(self.basis, "dump")
        self.speicher = os.path.join(self.basis, "speicher")
        os.makedirs(os.path.join(self.dump, "sce_sys"))
        os.makedirs(self.speicher)
        if not leer:
            _fassung(self.speicher, "0.3.6.6 no debug", "libSceAmpr.sprx")
            _fassung(self.speicher, "0.2.0 no debug", "libSceAmpr.sprx")
            if mit_playgo:
                _fassung(self.speicher, "PlayGo_v0.5 nolog", "libScePlayGo.sprx")

    def gui(self, emu_ordner: str = ""):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        self.protokoll: list[str] = []
        gui._append_to_log = self.protokoll.append
        gui._t = lambda s, **kw: s
        gui._detect_apr_title = lambda _p: True
        gui._auto_generate_ampr_index = lambda _p: True
        self.gespeichert: dict[str, str] = {}
        gui._save_setting = lambda k, v: self.gespeichert.__setitem__(k, v)
        gui._load_setting = lambda k, v="": {
            "ampr_store_dir": self.speicher,
            "ampr_emu_folder": emu_ordner,
        }.get(k, v)
        gui._ampr_updates_ordner = lambda: os.path.join(self.basis, "nichts")
        gui._ampr_bundled_store = lambda: ""
        self.gefragt: list[str] = []

        def _fragen(titel, vorgabe=""):
            self.gefragt.append(titel)
            return ""
        gui._ask_directory_threadsafe = _fragen
        return gui

    def abgelegt(self, gui) -> list[str]:
        pfad = gui._fakelib_pfad(self.dump)
        return sorted(p.name for p in pfad.iterdir()) if pfad.is_dir() else []

    def weg(self) -> None:
        shutil.rmtree(self.basis, ignore_errors=True)


class VersorgungTests(unittest.TestCase):

    def tearDown(self):
        if getattr(self, "lage", None):
            self.lage.weg()

    def test_der_automationslauf_gelingt_aus_dem_speicher(self):
        # Der gemessene Fall: Vorher brach er mit log.auto.0148 ab.
        self.lage = _Lage()
        gui = self.lage.gui()
        self.assertTrue(gui._prepare_ampr_support(self.lage.dump, {"is_apr": True}),
                        self.lage.protokoll)
        self.assertEqual(["libSceAmpr.sprx", "libScePlayGo.sprx"],
                         self.lage.abgelegt(gui))

    def test_ohne_speicher_bleibt_es_beim_abbruch(self):
        # Die Gegenrichtung: Der neue Weg darf nicht behaupten, versorgt zu
        # haben, wenn nichts da ist.
        self.lage = _Lage(leer=True)
        gui = self.lage.gui()
        self.assertFalse(gui._prepare_ampr_support(self.lage.dump, {"is_apr": True}))
        self.assertIn("log.auto.0148", self.lage.protokoll)

    def test_die_neueste_fassung_wird_genommen(self):
        self.lage = _Lage()
        gui = self.lage.gui()
        gui._prepare_ampr_support(self.lage.dump, {"is_apr": True})
        quelle = os.path.join(self.lage.speicher, "0.3.6.6 no debug",
                              "libSceAmpr.sprx")
        ziel = gui._fakelib_pfad(self.lage.dump) / "libSceAmpr.sprx"
        self.assertEqual(os.path.getsize(quelle), ziel.stat().st_size)

    def test_ohne_playgo_wird_gar_nichts_abgelegt(self):
        """Halb versorgt waere schlechter als gar nicht.

        Der Aufrufer prueft beide Dateien; eine halbe Ablage saehe beim
        naechsten Lauf nach "schon versorgt" aus und der fehlende Teil
        fiele nie wieder auf.
        """
        self.lage = _Lage(mit_playgo=False)
        gui = self.lage.gui()
        self.assertFalse(gui._ampr_aus_speicher_versorgen(self.lage.dump))
        self.assertEqual([], self.lage.abgelegt(gui))

    def test_ein_gefuellter_fakelib_ordner_bleibt_unberuehrt(self):
        self.lage = _Lage()
        gui = self.lage.gui()
        pfad = gui._fakelib_pfad(self.lage.dump)
        pfad.mkdir(parents=True, exist_ok=True)
        for name in ("libSceAmpr.sprx", "libScePlayGo.sprx"):
            (pfad / name).write_bytes(b"schon da")
        gui._prepare_ampr_support(self.lage.dump, {"is_apr": True})
        self.assertEqual(b"schon da", (pfad / "libSceAmpr.sprx").read_bytes())

    def test_der_alte_weg_ueber_einen_flachen_ordner_bleibt(self):
        """Wer ampr_emu_folder eingestellt hat, behaelt ihn.

        Geprueft mit leerem Versionsspeicher - sonst saehe man nicht, ob
        der alte Weg noch traegt oder nur der neue eingesprungen ist.
        """
        self.lage = _Lage(leer=True)
        flach = os.path.join(self.lage.basis, "flach")
        os.makedirs(flach)
        for name in ("libSceAmpr.sprx", "libScePlayGo.sprx"):
            with open(os.path.join(flach, name), "wb") as fh:
                fh.write(b"flach")
        gui = self.lage.gui(emu_ordner=flach)
        self.assertTrue(gui._prepare_ampr_support(self.lage.dump, {"is_apr": True}),
                        self.lage.protokoll)
        self.assertEqual(["libSceAmpr.sprx", "libScePlayGo.sprx"],
                         self.lage.abgelegt(gui))

    def test_ein_eingestellter_ordner_geht_dem_speicher_vor(self):
        """Die ausdrueckliche Angabe schlaegt die Vorgabe.

        Der erste Entwurf griff vor dem eingestellten Ordner zu und legte
        die Fassung aus dem Versionsspeicher ab - ein bestehender Test
        (test_qualitaetslauf.AprAmprPreflightTests) hat das gemeldet.
        Beide Quellen sind hier gefuellt; entscheidend ist, welche gewinnt.
        """
        self.lage = _Lage()
        flach = os.path.join(self.lage.basis, "flach")
        os.makedirs(flach)
        for name in ("libSceAmpr.sprx", "libScePlayGo.sprx"):
            with open(os.path.join(flach, name), "wb") as fh:
                fh.write(b"aus dem flachen Ordner")
        gui = self.lage.gui()
        self.assertTrue(gui._prepare_ampr_support(
            self.lage.dump, {"is_apr": True, "ampr_emu_folder": flach}))
        ziel = gui._fakelib_pfad(self.lage.dump) / "libSceAmpr.sprx"
        self.assertEqual(b"aus dem flachen Ordner", ziel.read_bytes())

    def test_in_der_oberflaeche_kommt_keine_rueckfrage_mehr(self):
        # automation=None heisst Oberflaechenbetrieb; dort stand vorher der
        # Ordner-Auswahldialog.
        self.lage = _Lage()
        gui = self.lage.gui()
        gui._ask_yesno_threadsafe = lambda *a: True
        self.assertTrue(gui._prepare_ampr_support(self.lage.dump))
        self.assertEqual([], self.lage.gefragt,
                         "Es wurde trotz vollem Versionsspeicher gefragt")


class TextTests(unittest.TestCase):
    """Kein fester deutscher Satz mehr an dieser Stelle."""

    @classmethod
    def setUpClass(cls):
        from ps5_validator.utils import i18n
        cls.i18n = i18n
        with io.open(APP.__file__, "rb") as fh:
            cls.baum = ast.parse(fh.read().decode("utf-8"))

    def test_die_texte_gibt_es_in_beiden_sprachen(self):
        for schluessel in ("ampr.aus_speicher", "ampr.choose_emu_folder",
                           "ampr.emu_folder_incomplete"):
            eintrag = self.i18n.STRINGS[schluessel]
            self.assertTrue(eintrag.get("de"), schluessel)
            self.assertTrue(eintrag.get("en"), schluessel)

    def test_kein_deutscher_satz_mehr_im_rumpf(self):
        """Ueber den Syntaxbaum der Methode, nicht ueber die ganze Datei.

        Gesucht werden Zeichenketten, die wie ein Satz an den Anwender
        aussehen - mehrere Woerter mit Leerzeichen. Ein Schluessel wie
        "ampr.aus_speicher" hat keine.
        """
        knoten = next(k for k in ast.walk(self.baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_prepare_ampr_support")
        saetze = [k.value for k in ast.walk(knoten)
                  if isinstance(k, ast.Constant) and isinstance(k.value, str)
                  and k.value.count(" ") >= 2 and not k.value.startswith("[")]
        # Der Docstring darf bleiben - er steht nicht in der Oberflaeche.
        saetze = [s for s in saetze if s != ast.get_docstring(knoten)]
        self.assertEqual([], saetze, "fester Satz im Rumpf")


if __name__ == "__main__":
    unittest.main(verbosity=2)
