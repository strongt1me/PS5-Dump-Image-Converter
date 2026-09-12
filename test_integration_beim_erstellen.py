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

import io
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


class _Kaestchen:
    """Ersatz für ein Tk-Widget, das nur ``configure`` können muss."""

    def __init__(self) -> None:
        self.zustand = ""

    def configure(self, **kw) -> None:
        self.zustand = kw.get("state", self.zustand)


def _paar(*, ampr: bool, backport: bool) -> PS5ConverterGUI:
    """Prüfling nur für ``_on_integration_changed`` – ohne Tk."""
    g = PS5ConverterGUI.__new__(PS5ConverterGUI)
    g._log_lines = []
    g._append_to_log = g._log_lines.append
    g._save_setting = lambda *_a, **_k: None
    g.ampr_integrate_var = _Var(ampr)
    g.ampr_playgo_var = _Var(True)
    g.backport_integrate_var = _Var(backport)
    g._ampr_versionsauswahl = {"0.3.5 no debug": {}}
    for name in ("ampr_version_combo", "ampr_playgo_check",
                 "backport_fw_combo", "ampr_integrate_check"):
        setattr(g, name, _Kaestchen())
    return g


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

        Die Kombination ist ausdrücklich erlaubt: ShadowMount+ hängt genau
        ein fakelib-Verzeichnis in die Sandbox und ersetzt darin vorhandene
        Dateien durch die aus ``emulators_path``. Es ersetzt aber nur, was
        schon da ist – eine reine Backport-fakelib ohne ``libSceAmpr.sprx``
        bekommt sie nicht nachträglich. Genau deshalb gehört beides zusammen
        in den Dump.
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

    def test_kein_kaestchen_schaltet_das_andere_ab(self) -> None:
        """Beide dürfen gleichzeitig gesetzt sein.

        Eine Zeit lang schlossen sie einander aus - das beruhte auf einer
        Annahme, die die ShadowMount+-Beschreibung nicht trägt: Dort ersetzen
        die Emulator-Dateien Dateien *in* der gewählten fakelib, sie
        konkurrieren nicht mit ihr. Der Test hält fest, dass keines der
        Kästchen das andere anfasst.
        """
        for gesetzt in (True, False):
            for ampr, backport in ((True, True), (True, False),
                                   (False, True), (False, False)):
                with self.subTest(speichern=gesetzt, ampr=ampr,
                                  backport=backport):
                    g = _paar(ampr=ampr, backport=backport)
                    g._on_integration_changed(speichern=gesetzt)
                    self.assertEqual(g.ampr_integrate_var.get(), ampr)
                    self.assertEqual(g.backport_integrate_var.get(), backport)

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



class ArbeitskopieFortschrittTests(unittest.TestCase):
    """Beim Anlegen der Arbeitskopie muss der Balken laufen.

    Bis zum 08.09.2026 stand hier ein blankes ``shutil.copytree`` - ein
    einziger blockierender Aufruf, der nichts meldet. Die Statuszeile sagte
    "Arbeitskopie anlegen...", und dann geschah minutenlang sichtbar nichts;
    bei einem Spielordner von zig Gigabyte war nicht zu unterscheiden, ob das
    Programm arbeitet oder haengt. Abbrechen liess sich der Lauf ebenfalls
    nicht.
    """

    @classmethod
    def setUpClass(cls):
        import tkinter as tk
        try:
            cls.wurzel = tk._default_root or tk.Tk()
            cls.wurzel.withdraw()
        except Exception:                       # pragma: no cover
            raise unittest.SkipTest("keine Anzeige verfuegbar")
        cls.app = PS5ConverterGUI(cls.wurzel)

    def setUp(self):
        self.meldungen = []
        self.statuszeilen = []
        self.verlauf = []
        self.merker = self.app._set_progress
        self.app._set_progress = lambda wert, **kw: self.meldungen.append(
            (wert, kw.get("size_text")))
        self.addCleanup(setattr, self.app, "_set_progress", self.merker)

        # Die Statuszeile mitschreiben: Sie traegt seit dem 10.09.2026 die
        # laufenden Zahlen, damit _stillstand_uhr eine lange Kopie nicht
        # fuer einen Aufhaenger haelt.
        self.merker_status = self.app._set_status
        self.app._set_status = lambda t: self.statuszeilen.append(str(t))
        self.addCleanup(setattr, self.app, "_set_status", self.merker_status)

        # Und den Gesamtfortschritt, auf den der Melder jetzt schreibt.
        self.merker_teil = self.app._teilschritt_melden

        def _mit_verlauf(schluessel, anteil, spanne):
            self.merker_teil(schluessel, anteil, spanne)
            self.verlauf.append(self.app.task_progress)

        self.app._teilschritt_melden = _mit_verlauf
        self.addCleanup(setattr, self.app, "_teilschritt_melden", self.merker_teil)

        self.app.task_progress = 0.0
        self.app._teilschritt_merker = None
        # Was ``_integration_arbeitskopie`` vor der Kopie setzt.
        self.app._copy_total_bytes = 0
        self.app._copy_done_bytes = 0
        self.app._copy_total_exact = True
        self.app._copy_rate_bps = 0.0
        self.app.is_running = True

    @staticmethod
    def _baum(wurzel: Path) -> Path:
        quelle = wurzel / "quelle"
        (quelle / "a" / "tief").mkdir(parents=True)
        (quelle / "leer").mkdir()
        for i in range(12):
            (quelle / "a" / ("d%02d.bin" % i)).write_bytes(b"X" * 4096)
        (quelle / "a" / "tief" / "t.bin").write_bytes(b"Y" * 8192)
        return quelle

    def test_kopiert_vollstaendig_und_meldet_dabei(self):
        # Ohne Takt, sonst fasst er die Meldungen eines schnellen Laufs
        # zusammen und der Test saehe die Zwischenstaende nicht.
        merker = self.app._KOPIE_TAKT_SEKUNDEN
        self.app._KOPIE_TAKT_SEKUNDEN = 0.0
        self.addCleanup(setattr, self.app, "_KOPIE_TAKT_SEKUNDEN", merker)

        with TemporaryDirectory() as basis:
            quelle = self._baum(Path(basis))
            ziel = os.path.join(basis, "ziel")
            gesamt = self.app._get_path_size(str(quelle))
            self.app._kopieren_mit_fortschritt(str(quelle), ziel, gesamt)

            def dateien(w):
                return {os.path.relpath(os.path.join(r, n), w)
                        for r, _u, ns in os.walk(w) for n in ns}
            self.assertEqual(dateien(str(quelle)), dateien(ziel))
            self.assertTrue(os.path.isdir(os.path.join(ziel, "leer")),
                            "Ein leerer Unterordner ist verlorengegangen")

        # Gemessen werden die **Byte-Zaehler**, nicht die Aufrufe an
        # ``_set_progress``.
        #
        # Bis zum 10.09.2026 stand hier "werte[0] == 0.0" und
        # "werte[-1] == 100.0" - also die Zusicherung, dass die Kopie ihren
        # eigenen 0-bis-100-Wert direkt auf den Balken schreibt. Genau das war
        # der Fehler: Der Takt aus ``_update_progress_gui`` setzt 80 ms
        # spaeter wieder den Gesamtwert, und der Balken sprang zwischen beiden
        # hin und her - beim Anwender bis zu 567 Mal in einem Lauf.
        #
        # Der erste Anlauf der Behebung meldete ueber einen eigenen Weg. Auch
        # das war zu kurz gesprungen: Das Groessenfeld rechts blieb leer, weil
        # der Takt es bei jedem Durchlauf neu setzt und fuer diese Phase kein
        # Zweig greift. Seit dem 11.09.2026 fuellt die Kopie die Zaehler, die
        # der Takt ohnehin auswertet - damit laeuft der Balken **und** rechts
        # steht "Copy: x/y GB | Rest: ... | ... MB/s".
        self.assertEqual(
            [], self.meldungen,
            "Der Melder hat den Balken angefasst: %r" % (self.meldungen,))
        self.assertEqual(
            gesamt, self.app._copy_done_bytes,
            "Am Ende muss der Zaehler auf der vollen Groesse stehen.")
        self.assertTrue(self.app._copy_total_exact,
                        "Ohne das zeigt das Groessenfeld keine GB-Angabe.")
        self.assertGreater(self.app._copy_rate_bps, 0.0,
                           "Ohne Rate fehlen MB/s und Restzeit.")
        self.assertTrue(
            any("/" in z for z in self.statuszeilen),
            "Die Statuszeile trug keine laufenden Zahlen - ohne sie haelt "
            "_stillstand_uhr eine lange Kopie fuer einen Aufhaenger: %r"
            % (self.statuszeilen,))

    def test_abbruch_wirkt_sofort(self):
        with TemporaryDirectory() as basis:
            quelle = self._baum(Path(basis))
            ziel = os.path.join(basis, "ziel")
            self.app.is_running = False
            with self.assertRaises(Exception) as fehler:
                self.app._kopieren_mit_fortschritt(
                    str(quelle), ziel, self.app._get_path_size(str(quelle)))
            self.assertEqual(type(fehler.exception).__name__,
                             "_KopieAbgebrochen")

    def test_abbruch_ist_kein_schreibfehler(self):
        """Der Aufrufer muss beides unterscheiden koennen.

        Eine Entscheidung des Anwenders und eine volle Platte verlangen
        verschiedene Meldungen - deshalb ist der Abbruch kein ``OSError``.
        """
        import PS5ImageConverter_Pro_FINAL_revised as modul
        self.assertFalse(issubclass(modul._KopieAbgebrochen, OSError))

    def test_kein_blankes_copytree_mehr(self):
        """Gegenprobe zur Bauart.

        Ohne sie koennte jemand den Aufruf "vereinfachen" und dieselbe
        stumme Wartezeit wieder einbauen.
        """
        import ast
        quelle = (Path(__file__).resolve().parent
                  / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(
                      encoding="utf-8")
        for knoten in ast.walk(ast.parse(quelle)):
            if (isinstance(knoten, ast.FunctionDef)
                    and knoten.name == "_integration_arbeitskopie"):
                text = ast.unparse(knoten)
                self.assertNotIn("copytree", text)
                self.assertIn("_kopieren_mit_fortschritt", text)
                return
        self.fail("_integration_arbeitskopie heisst nicht mehr so - dieser "
                  "Test misst dann nichts.")

class IntegrationsLueckenTests(unittest.TestCase):
    """Kein Konvertierungsweg darf die Kaestchen stillschweigend uebergehen.

    Am 08.09.2026 an echten Sicherungen gemessen - je zweimal derselbe Lauf,
    einmal ohne und einmal mit gesetzten Haken, verglichen wurden die
    Protokollmarker und die Dateizahl:

    | Weg                    | ohne | mit                     | greift |
    | ---------------------- | ---- | ----------------------- | ------ |
    | .exFAT  -> .ffpfsc     | -    | -                       | nein   |
    | .ffpkg  -> .ffpfsc     | -    | -                       | nein   |
    | .ffpkg  -> Dump-Ordner | 191  | 191                     | nein   |
    | .exFAT  -> Dump-Ordner | 191  | 200, ampr+backport+index | ja    |
    | .ffpfsc -> .ffpfs      | -    | ampr+backport+index      | ja    |

    Die letzten beiden Zeilen sind die Gegenprobe: Ohne sie wuesste man
    nicht, ob die Messung ueberhaupt etwas sieht.

    Zwei verschiedene Ursachen, deshalb zwei verschiedene Behebungen:

    * ``.ffpkg`` -> Dump-Ordner **kann** einbauen und tat es nur nicht. Das
      Gegenstueck fuer die .exFAT macht es seit jeher. Nachgeholt.
    * Die beiden ``.ffpfsc``-Wege huellen das Abbild als Ganzes ein und
      oeffnen seinen Inhalt nie. Dort *kann* nichts eingebaut werden - der
      Anwender muss es aber erfahren, statt ein Backup ohne AMPR EMU zu
      bekommen und es fuer eines mit zu halten.
    """

    @classmethod
    def setUpClass(cls):
        cls.quelle = (Path(__file__).resolve().parent
                      / "PS5ImageConverter_Pro_FINAL_revised.py"
                      ).read_text(encoding="utf-8")

    def _rumpf(self, name: str) -> str:
        import ast
        baum = ast.parse(self.quelle)
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
                return ast.unparse(knoten)
        self.fail("%s gibt es nicht mehr" % name)

    def test_ffpkg_nach_ordner_baut_ein(self):
        self.assertIn("_integration_anwenden", self._rumpf("_mode_ffpkg_to_folder"),
                      "Aufgabe 4 nach Dump-Ordner laesst AMPR EMU und "
                      "BACKPORT wieder weg.")

    def test_exfat_nach_ordner_baut_weiterhin_ein(self):
        """Anker: das Gegenstueck, an dem der Fehlende gemessen wurde."""
        self.assertIn("_integration_anwenden", self._rumpf("_mode_exfat_to_folder"))

    def test_die_einhuellenden_wege_stehen_in_der_liste(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP
        wege = APP.PS5ConverterGUI._EINHUELLENDE_WEGE
        self.assertIn(("exfat", "ffpfsc"), wege)
        self.assertIn(("ffpkg", "ffpfsc"), wege)

    def test_die_liste_enthaelt_nur_wirklich_einhuellende_wege(self):
        """Wer hier etwas einträgt, unterdrueckt den Einbau nicht - er warnt
        nur. Steht ein Weg faelschlich drin, warnt das Programm, obwohl der
        Einbau laeuft. Geprueft wird deshalb, dass die genannten Modi das
        Abbild wirklich als eine Datei einbetten.
        """
        for name in ("_mode_pack_file", "_mode_ffpkg_to_ffpfsc"):
            with self.subTest(modus=name):
                rumpf = self._rumpf(name)
                self.assertIn("'pack', 'file'", rumpf.replace('"', "'"),
                              "%s bettet nicht mehr als einzelne Datei ein" % name)
                self.assertNotIn("_integration_anwenden", rumpf)

    def test_die_vorpruefung_fragt(self):
        """Seit dem 12.09.2026 ist aus der Warnung eine Rueckfrage geworden.

        Vorher warnte das Programm nur und machte weiter - heraus kam ein
        Abbild ohne die angehakten Bestandteile. Jetzt entscheidet der
        Anwender: Dump-Ordner statt Container, oder Schluss.
        """
        rumpf = self._rumpf("_umhuellenden_weg_klaeren")
        self.assertIn("_EINHUELLENDE_WEGE", rumpf)
        self.assertIn("_integration_gewaehlt", rumpf,
                      "Ohne diese Bedingung fragt das Programm auch den, "
                      "der gar nichts einbauen wollte.")
        self.assertIn("dialog.msg.umhuellt_ordner_frage", rumpf)

    def test_die_rueckfrage_haengt_wirklich_im_ablauf(self):
        """Die Verdrahtung, nicht nur die Methode.

        Eine Pruefung, die ``_umhuellenden_weg_klaeren`` direkt aufruft, bleibt
        auch dann gruen, wenn niemand die Methode mehr benutzt. Genau so ist
        am 12.09.2026 eine Gegenprobe durchgerutscht: Der Aufruf war aus
        ``_launch_task`` entfernt, und neun Pruefungen meldeten weiter alles
        in Ordnung.
        """
        rumpf = self._rumpf("_launch_task")
        self.assertIn("_umhuellenden_weg_klaeren", rumpf,
                      "Die Rueckfrage wird nirgends mehr gestellt.")
        self.assertIn("return", rumpf)

    def test_die_texte_gibt_es_in_beiden_sprachen(self):
        from ps5_validator.utils import i18n
        for schluessel in ("dialog.title.umhuellt_ordner",
                           "dialog.msg.umhuellt_ordner_frage",
                           "log.umhuellt_ordner_gewaehlt",
                           "log.umhuellt_abgebrochen",
                           "log.umhuellt_cli"):
            eintrag = i18n.STRINGS.get(schluessel)
            self.assertIsNotNone(eintrag, schluessel)
            for sprache in i18n.SUPPORTED_LANGUAGES:
                self.assertTrue(eintrag.get(sprache), "%s/%s" % (schluessel, sprache))


class UmhuellenderWegTests(unittest.TestCase):
    """Wenn die Integration auf einem Weg nicht greifen kann, wird gefragt.

    Auf den Wegen ``.exFAT -> .ffpfsc`` und ``.ffpkg -> .ffpfsc`` wandert das
    Abbild als **eine Datei** in den Container; sein Inhalt wird nie geöffnet.
    Was in der Pfad-Karte angehakt ist, kann dort nicht eingebaut werden.

    Bis zum 12.09.2026 stand darüber nur eine Warnung, und der Lauf ging
    weiter. Heraus kam ein Abbild **ohne** AMPR EMU und BACKPORT, und nichts
    unterschied es von einem mit. Jetzt entscheidet der Anwender: Dump-Ordner
    statt Container – oder Schluss.
    """

    def _gui(self, *, ampr=True, backport=False, antwort=True, cli=False,
             cli_schalter=False, zielformat="ffpfsc"):
        g = PS5ConverterGUI.__new__(PS5ConverterGUI)
        g._log_lines = []
        g._append_to_log = g._log_lines.append
        g._t = lambda s, **w: (s + " " + " ".join(
            "%s=%s" % (k, v) for k, v in sorted(w.items()))).strip()
        g.ampr_integrate_var = _Var(ampr)
        g.backport_integrate_var = _Var(backport)
        g.target_format = _Var("format.%s" % zielformat)
        g._gefragt = []

        def _frage(titel, text, **kw):
            g._gefragt.append((titel, text))
            return antwort

        g._ask_yesno_threadsafe = _frage
        g._cli_mode = cli
        g._cli_umhuellt_ordner = cli_schalter
        return g

    def test_ja_stellt_auf_dump_ordner_um(self):
        g = self._gui(antwort=True)
        self.assertTrue(g._umhuellenden_weg_klaeren("pack_file", "x.exfat", "ffpfsc"))
        self.assertTrue(g._gefragt, "Es wurde gar nicht gefragt.")
        self.assertEqual("format.folder", g.target_format.get(),
                         "Das Zielformat wurde nicht auf den Dump-Ordner gestellt.")

    def test_nein_beendet_die_aufgabe(self):
        g = self._gui(antwort=False)
        self.assertFalse(g._umhuellenden_weg_klaeren("pack_file", "x.exfat", "ffpfsc"))
        self.assertEqual("format.ffpfsc", g.target_format.get(),
                         "Bei Nein darf nichts umgestellt werden.")
        self.assertTrue(any("umhuellt_abgebrochen" in z for z in g._log_lines),
                        "Der Abbruch steht nicht im Protokoll.")

    def test_ohne_haekchen_wird_nicht_gefragt(self):
        """Wer nichts einbauen will, soll auch nichts entscheiden muessen."""
        g = self._gui(ampr=False, backport=False)
        self.assertTrue(g._umhuellenden_weg_klaeren("pack_file", "x.exfat", "ffpfsc"))
        self.assertEqual([], g._gefragt)
        self.assertEqual("format.ffpfsc", g.target_format.get())

    def test_unbetroffener_weg_wird_nicht_gefragt(self):
        """Aus einem Dump-Ordner heraus greift die Integration ja."""
        g = self._gui(zielformat="ffpfsc")
        self.assertTrue(g._umhuellenden_weg_klaeren("pack_folder", "ordner", "ffpfsc"))
        self.assertEqual([], g._gefragt)

    def test_backport_allein_reicht_fuer_die_frage(self):
        g = self._gui(ampr=False, backport=True, antwort=False)
        self.assertFalse(g._umhuellenden_weg_klaeren("pack_file", "x.exfat", "ffpfsc"))
        self.assertTrue(g._gefragt)

    def test_cli_ohne_schalter_endet(self):
        """Ohne Fenster entscheidet ein eigener Schalter - nicht --yes."""
        g = self._gui(cli=True, cli_schalter=False)
        self.assertFalse(g._umhuellenden_weg_klaeren("pack_file", "x.exfat", "ffpfsc"))
        self.assertEqual([], g._gefragt, "Im CLI darf kein Fenster aufgehen.")
        self.assertTrue(any("umhuellt_cli" in z for z in g._log_lines),
                        "Der Grund steht nicht im Protokoll.")

    def test_cli_mit_schalter_baut_den_ordner(self):
        g = self._gui(cli=True, cli_schalter=True)
        self.assertTrue(g._umhuellenden_weg_klaeren("pack_file", "x.exfat", "ffpfsc"))
        self.assertEqual("format.folder", g.target_format.get())

    def test_beide_bekannten_wege_sind_erfasst(self):
        """Die Liste selbst - sonst faellt ein Weg still heraus."""
        self.assertIn(("exfat", "ffpfsc"), PS5ConverterGUI._EINHUELLENDE_WEGE)
        self.assertIn(("ffpkg", "ffpfsc"), PS5ConverterGUI._EINHUELLENDE_WEGE)

    def test_preflight_warnt_nicht_mehr_doppelt(self):
        """Aus der Warnung ist eine Entscheidung geworden - nicht beides."""
        import ast
        with io.open(PS5ConverterGUI.__module__ and
                     str(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"),
                     encoding="utf-8", errors="replace") as fh:
            baum = ast.parse(fh.read())
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef)
                      and k.name == "_run_preflight_checks")
        text = ast.unparse(knoten)
        self.assertNotIn("preflight.integration_umhuellt", text,
                         "Der Fall steht noch in der Vorabpruefung - der "
                         "Anwender saehe Warnung UND Rueckfrage.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
