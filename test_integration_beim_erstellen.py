"""Tests für AMPR EMU und BACKPORT als Häkchen beim Erstellen.

In der Pfad-Karte stehen zwei Kästchen, die beim Bauen eines Backups mit
einfließen: der AMPR EMU (Bibliothek in ``fakelib/`` plus neuer
``ampr_emu.index``) und der BACKPORT (SDK-Angaben herabsetzen plus passende
Ersatzbibliotheken). Beide arbeiten immer auf einem **Dump-Ordner** – das ist
der einzige verlässliche Weg, denn jedes Zielformat entsteht aus einem Ordner.

Zwei Fehler, die dabei ans Licht kamen und mitgeprüft werden:

* Die Versionsliste sortierte ``0.3.5`` vor ``0.3.5.1``. Beim absteigenden
  Sortieren gewinnt sonst die *kürzere* Nummer, weil Python bei gleichem
  Anfang das kürzere Tupel als kleiner ansieht – als „neueste Version" wurde
  also die ältere vorausgewählt. Das galt auch für Aufgabe 7.
* ``libScePlayGo.sprx`` stammt aus einem eigenen Projekt und zählt seine
  Versionen getrennt (mitgeliefert ist 0.5). Eine Suche nach derselben
  Versionsnummer wie beim AMPR-Modul hätte nie etwas gefunden.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.utils import ps5_backport
from ps5_validator.utils.i18n import STRINGS


class _Var:
    """Ersatz für eine Tk-Variable."""

    def __init__(self, wert) -> None:
        self._wert = wert

    def get(self):
        return self._wert

    def set(self, wert) -> None:
        self._wert = wert


def _dump_anlegen(ziel: Path) -> None:
    """Legt einen kleinen Dump an, wie ihn die Integration erwartet."""
    (ziel / "sce_sys").mkdir(parents=True, exist_ok=True)
    (ziel / "sce_sys" / "param.json").write_text('{"titleId":"CUSA00001"}', encoding="utf-8")
    (ziel / "eboot.bin").write_bytes(b"\x7fELF" + os.urandom(2048))
    (ziel / "sce_module").mkdir(exist_ok=True)
    (ziel / "sce_module" / "libc.prx").write_bytes(os.urandom(1024))


def _gui(*, ampr: bool, backport: bool, arbeitskopie: bool = False) -> PS5ConverterGUI:
    """Baut eine Prüflings-Instanz mit gesetzten Kästchen, ohne Tk."""
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    protokoll: list[str] = []
    g._append_to_log = protokoll.append
    g._log_lines = protokoll
    g._set_status = lambda *_a, **_k: None
    g._load_setting = lambda _k, vorgabe: vorgabe
    g._save_setting = lambda *_a, **_k: None
    g._fmt_bytes = lambda n: f"{n} B"
    g._get_path_size = lambda p: 0
    g.is_running = True
    g._ask_yesno_threadsafe = lambda *_a, **_k: arbeitskopie
    g.engine_output_queue = queue.Queue()
    g._embedded_mkpfs_lock = threading.RLock()
    g.ampr_integrate_var = _Var(ampr)
    g.ampr_playgo_var = _Var(True)
    g.backport_integrate_var = _Var(backport)
    g.backport_fw_var = _Var(str(ps5_backport.FIRMWARE_STANDARD))
    g.ampr_version_var = _Var("")
    g._integration_erledigt = False

    eintraege = g._ampr_scan_version_store(PS5ConverterGUI._ampr_bundled_store())
    g._ampr_versionsauswahl = {}
    for eintrag in eintraege:
        if eintrag["lib"] != "libSceAmpr.sprx":
            continue
        beschriftung = f"{eintrag['version']} {eintrag['variant']}".strip()
        g._ampr_versionsauswahl.setdefault(beschriftung, eintrag)
    if g._ampr_versionsauswahl:
        g.ampr_version_var.set(next(iter(g._ampr_versionsauswahl)))
    return g


class VersionssortierungTests(unittest.TestCase):
    """Die neueste Version muss oben stehen – auch bei vier Stellen."""

    def test_vierstellig_schlaegt_dreistellig(self) -> None:
        schluessel = PS5ConverterGUI._ampr_version_sort_key
        self.assertGreater(schluessel("0.3.5.1"), schluessel("0.3.5"))
        self.assertGreater(schluessel("0.2.7.6"), schluessel("0.2.7"))
        self.assertGreater(schluessel("0.3.0"), schluessel("0.2.7.6"))

    def test_gleich_lange_nummern_unveraendert(self) -> None:
        schluessel = PS5ConverterGUI._ampr_version_sort_key
        self.assertGreater(schluessel("0.3.4"), schluessel("0.3.3"))
        self.assertEqual(schluessel("0.3.4"), schluessel("0.3.4.0"))

    def test_neueste_steht_im_speicher_oben(self) -> None:
        g = _gui(ampr=True, backport=False)
        if not g._ampr_versionsauswahl:
            self.skipTest("kein AMPR-Versionsspeicher vorhanden")
        erste = next(iter(g._ampr_versionsauswahl))
        alle = list(g._ampr_versionsauswahl)
        schluessel = PS5ConverterGUI._ampr_version_sort_key
        hoechste = max(alle, key=lambda b: schluessel(b.split()[0]))
        self.assertEqual(schluessel(erste.split()[0]), schluessel(hoechste.split()[0]))


class PlayGoZuordnungTests(unittest.TestCase):
    """PlayGo zählt eigene Versionen – gesucht wird nach der Variante."""

    def test_variante_entscheidet(self) -> None:
        g = _gui(ampr=True, backport=False)
        treffer = g._ampr_playgo_zur_version({"version": "0.3.5.1", "variant": "no debug"})
        if not treffer:
            self.skipTest("keine PlayGo-Datei mitgeliefert")
        self.assertIn("nolog", treffer.lower())

    def test_debug_bekommt_log_variante(self) -> None:
        g = _gui(ampr=True, backport=False)
        treffer = g._ampr_playgo_zur_version({"version": "0.3.2", "variant": "debug"})
        if not treffer:
            self.skipTest("keine PlayGo-Datei mitgeliefert")
        self.assertTrue(treffer.lower().endswith("libsceplaygo.sprx"))


class IntegrationsablaufTests(unittest.TestCase):
    """Was bei gesetzten Kästchen tatsächlich im Ordner landet."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory(prefix="integration_")
        self.dump = Path(self._tmp.name) / "spiel"
        _dump_anlegen(self.dump)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_ohne_haekchen_bleibt_alles_wie_es_war(self) -> None:
        g = _gui(ampr=False, backport=False)
        vorher = sorted(p.name for p in self.dump.rglob("*"))
        self.assertEqual(g._integration_anwenden(str(self.dump)), str(self.dump))
        self.assertEqual(sorted(p.name for p in self.dump.rglob("*")), vorher)

    def test_ampr_legt_bibliothek_und_index_an(self) -> None:
        g = _gui(ampr=True, backport=False)
        if not g._ampr_versionsauswahl:
            self.skipTest("kein AMPR-Versionsspeicher vorhanden")
        ergebnis = g._integration_anwenden(str(self.dump))
        self.assertTrue(ergebnis, "".join(g._log_lines[-4:]))
        ordner = Path(ergebnis)
        fakelib = ordner / g._fakelib_ordnername()
        self.assertTrue((fakelib / "libSceAmpr.sprx").is_file(), "AMPR-Bibliothek fehlt")
        self.assertTrue((ordner / PS5ConverterGUI._AMPR_INDEX_NAME).is_file(),
                        "ampr_emu.index fehlt")

    def test_backport_legt_ersatzbibliotheken_dazu(self) -> None:
        g = _gui(ampr=False, backport=True)
        if not g._backport_fakelib_basis():
            self.skipTest("keine Ersatzbibliotheken mitgeliefert")
        ergebnis = g._integration_anwenden(str(self.dump))
        self.assertTrue(ergebnis, "".join(g._log_lines[-4:]))
        fakelib = Path(ergebnis) / g._fakelib_ordnername()
        self.assertTrue(fakelib.is_dir(), "fakelib-Ordner fehlt")
        self.assertTrue(any(fakelib.glob("*.sprx")), "keine Ersatzbibliothek kopiert")

    def test_beide_zusammen_und_ampr_gewinnt_die_reihenfolge(self) -> None:
        """Der AMPR-Einbau muss NACH dem Backport laufen.

        Beide schreiben in denselben fakelib-Ordner. Liefe der Backport
        zuletzt, könnte er die eben eingebaute AMPR-Bibliothek überschreiben.
        """
        g = _gui(ampr=True, backport=True)
        if not g._ampr_versionsauswahl:
            self.skipTest("kein AMPR-Versionsspeicher vorhanden")
        ergebnis = g._integration_anwenden(str(self.dump))
        self.assertTrue(ergebnis, "".join(g._log_lines[-6:]))

        gewaehlt = g._ampr_versionsauswahl[g.ampr_version_var.get()]
        eingebaut = Path(ergebnis) / g._fakelib_ordnername() / "libSceAmpr.sprx"
        self.assertTrue(eingebaut.is_file())
        self.assertEqual(eingebaut.stat().st_size, int(gewaehlt["size"]),
                         "Die eingebaute Datei ist nicht die gewählte Version")

    def test_arbeitskopie_laesst_die_quelle_unberuehrt(self) -> None:
        g = _gui(ampr=True, backport=False, arbeitskopie=True)
        if not g._ampr_versionsauswahl:
            self.skipTest("kein AMPR-Versionsspeicher vorhanden")
        g._mkdtemp = lambda prefix, dir_path=None: str(
            Path(self._tmp.name, "kopie_" + prefix).resolve())

        def _mkdtemp(prefix, dir_path=None):
            ziel = Path(self._tmp.name) / ("kopie_" + prefix)
            ziel.mkdir(parents=True, exist_ok=True)
            return str(ziel)

        g._mkdtemp = _mkdtemp
        ergebnis = g._integration_anwenden(str(self.dump), ist_quellordner=True)
        self.assertTrue(ergebnis)
        self.assertNotEqual(os.path.normcase(ergebnis), os.path.normcase(str(self.dump)))
        self.assertFalse((self.dump / g._fakelib_ordnername()).exists(),
                         "Der Quellordner wurde trotz Arbeitskopie verändert")
        self.assertTrue((Path(ergebnis) / g._fakelib_ordnername()).is_dir())

    def test_zweiter_aufruf_bleibt_wirkungslos(self) -> None:
        """Mehrstufige Wege rufen einander auf – der Einbau darf nur einmal laufen."""
        g = _gui(ampr=True, backport=False)
        if not g._ampr_versionsauswahl:
            self.skipTest("kein AMPR-Versionsspeicher vorhanden")
        self.assertTrue(g._integration_anwenden(str(self.dump)))
        zeilen_nach_erstem = len(g._log_lines)
        zweiter = g._integration_anwenden(str(self.dump))
        self.assertEqual(zweiter, str(self.dump))
        self.assertEqual(len(g._log_lines), zeilen_nach_erstem,
                         "Der zweite Aufruf hat erneut gearbeitet")


class OberflaecheTests(unittest.TestCase):
    """Die Kästchen müssen verdrahtet und beschriftet sein."""

    def test_texte_sind_zweisprachig(self) -> None:
        schluessel = [k for k in STRINGS if k.startswith("main.integrate_")]
        self.assertGreaterEqual(len(schluessel), 15)
        for name in schluessel:
            with self.subTest(schluessel=name):
                self.assertTrue(STRINGS[name].get("de"))
                self.assertTrue(STRINGS[name].get("en"))

    def test_alte_beschriftung_ist_weg(self) -> None:
        """An ihrer Stelle stehen jetzt die beiden Kästchen."""
        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertNotIn("verify_inline_title", quelle)

    def test_alle_wege_haengen_am_selben_einbau(self) -> None:
        """Jedes Zielformat muss durch _integration_anwenden gehen.

        Sonst greifen die Kästchen nur für einen Teil der Formate – genau der
        Fehler, der beim Auspacken schon dreimal auftrat.
        """
        quelle = Path("PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        for name in ("_mode_pack_folder", "_mode_folder_to_exfat", "_mode_folder_to_ffpkg",
                     "_mode_ffpfsc_to_ffpkg", "_mode_exfat_to_ffpkg", "_mode_ffpkg_to_ffpkg",
                     "_mode_ffpkg_to_exfat", "_mode_unpack_to_exfat",
                     "_mode_unpack_to_game_folder", "_mode_exfat_to_folder"):
            with self.subTest(weg=name):
                start = quelle.index(f"    def {name}(")
                naechste = quelle.index("\n    def ", start + 1)
                self.assertIn("_integration_anwenden", quelle[start:naechste],
                              f"{name} baut nichts ein")


if __name__ == "__main__":
    unittest.main(verbosity=2)
