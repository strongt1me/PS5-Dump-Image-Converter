# -*- coding: utf-8 -*-
"""Die sieben Pruefungen aus dem alten Qualitaetslauf - jetzt im Pruefbestand.

Angelegt am 03.09.2026.

**Warum es diese Datei gibt.** Die sieben Pruefungen standen in
``test_all_quality_new.py`` und liefen **nie mit**. Der Grund ist der
Aufbau jener Datei: Sie enthaelt keine einzige ``TestCase``-Klasse,
sondern Funktionen auf Modulebene im pytest-Stil. ``unittest`` sammelt
daraus nichts ein - ``python -m unittest test_all_quality_new`` meldet
``Ran 0 tests``. ``lauf_geteilt.py`` nimmt die Datei zwar als eines der
Module mit, bekommt aber nichts von ihr. Aufgerufen hat sie ausserdem
niemand: kein Test, kein Skript, kein Bauplan. Und selbst von Hand
gestartet konnte sie nicht rot werden, weil ihr ``main()`` mit
``return 0  # Nicht als kritischer Fehler`` endet.

Was dadurch unbewacht war: die Fensterzentrierung des Startbildes, die
APR-Erkennung samt AMPR-Preflight aus Aufgabe 7, die Zielmatrix von
Aufgabe 6, die Temp-Bereinigung **nach einem Auftrag** (die beim
Beenden ist anderswo abgedeckt), der Schreibschutz des FFPKG-Validators,
die Abschlusspruefung des Ergebnisses und der Vorrang strukturierter
UFS2-Metadaten vor dem Muster-Scan.

**Was bei der Ueberfuehrung geaendert wurde.**

* Aus je einem ``checks``-Woerterbuch sind einzelne Pruefmethoden
  geworden. Faellt eine, sagt der Bericht welche - vorher stand am Ende
  nur ein ``[FAIL]`` fuer den ganzen Block.
* Das umschliessende ``try/except Exception: return False`` ist weg. Es
  verwandelte jede Ausnahme in ein stilles Nein; ``unittest`` zeigt sie.
* Vierzehn Suchen nach Wortlaut im Quelltext sind ersetzt: sechs durch
  eine Wirkung, sechs durch eine Strukturpruefung ueber den
  Syntaxbaum (sie liest die **uebergebenen Werte** statt einer
  Zeichenkette und ueberlebt damit jedes Umformatieren), zwei durch die
  Frage an die Textquelle, ob es den Schluessel gibt. Wo eine Pruefung
  weiterhin den Aufbau des Quelltextes misst, sagt ihr Name das.
* ``Path("MkPFS-1.0.0")`` war relativ zum Arbeitsverzeichnis - der alte
  Lauf ging nur aus dem Projektordner heraus auf. Jetzt absolut, und die
  Fassung kommt aus ``MKPFS_ERFORDERLICHE_FASSUNG`` statt aus dem
  Quelltext dieser Datei.

**Nachtrag vom selben Tag.** Die uebrigen sieben Funktionen jener Datei
sind inzwischen ebenfalls geklaert, und die Datei ist samt ihrer aelteren
Zwillingsfassung ``test_all_quality.py`` geloescht:

* **Uebernommen**, weil sie etwas pruefen, das sonst niemand prueft: der
  Keepalive-Hinweis (unten) und die Stilpruefung (Tabs, Leerraum am
  Zeilenende) - letztere gilt jetzt fuer den ganzen eigenen Bestand statt
  nur fuer den Monolithen.
* **Verworfen**, weil die Sache anderswo steht oder nichts aussagt: die
  Syntaxpruefung (jede der 3400 Pruefungen importiert den Monolithen, ein
  Syntaxfehler faellt sofort auf), die Importpruefung und die
  Bauabhaengigkeiten (beides deckt ``test_build_ready.py`` ab), die
  ProgressEngine-Pruefung (sechs Suchen nach Wortlaut; die Wirkung prueft
  ``test_fortschrittsbalken.py``) und die Dateiintegritaet (sie fragte, ob
  der Monolith groesser als 1 MB ist und mehr als 10000 Zeilen hat).

Damit das nicht wiederkommt, steht unten ``KeineTotenPruefungenTests``.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import werkzeuge_bereitstellen as wb
from ps5_validator.utils.i18n import STRINGS

#: Der Engine-Ordner, wie ihn das Programm erwartet - absolut, und die
#: Fassung aus der Vorgabe statt aus dem Quelltext dieser Datei.
MKPFS_ORDNER = str((PROJEKT / f"MkPFS-{wb.MKPFS_ERFORDERLICHE_FASSUNG}").resolve())


# ---------------------------------------------------------------------------
# Werkzeug
# ---------------------------------------------------------------------------

_QUELLE = Path(APP.__file__).read_text(encoding="utf-8")
_BAUM = ast.parse(_QUELLE)


def _funktion(name: str, innerhalb: ast.AST | None = None) -> ast.FunctionDef:
    """Sucht eine Funktion im Syntaxbaum - auch eine verschachtelte.

    Args:
        name:      Der gesuchte Funktionsname.
        innerhalb: Knoten, unter dem gesucht wird. Ohne Angabe die ganze Datei.

    Returns:
        Der Knoten der Funktion.

    Raises:
        AssertionError: Wenn es sie nicht mehr gibt - das ist der Befund.
    """
    for knoten in ast.walk(innerhalb if innerhalb is not None else _BAUM):
        if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
            return knoten
    raise AssertionError(f"Die Funktion {name} gibt es im Programm nicht mehr.")


def _aufrufe(knoten: ast.AST, name: str) -> list[ast.Call]:
    """Alle Aufrufe von ``name`` unter ``knoten``, in Reihenfolge des Quelltextes."""
    treffer: list[ast.Call] = []
    for k in ast.walk(knoten):
        if isinstance(k, ast.Call):
            ziel = k.func
            gerufen = ziel.attr if isinstance(ziel, ast.Attribute) else getattr(ziel, "id", None)
            if gerufen == name:
                treffer.append(k)
    return sorted(treffer, key=lambda k: (k.lineno, k.col_offset))


def _zeichenketten(knoten: ast.AST) -> list[str]:
    """Alle Zeichenketten-Konstanten unter ``knoten``, in Reihenfolge."""
    return [k.value for k in ast.walk(knoten)
            if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def _gui() -> APP.PS5ConverterGUI:
    """Eine Programminstanz ohne Fenster - wie im uebrigen Pruefbestand."""
    return APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)


# ---------------------------------------------------------------------------
# 1 - Zentrierung des Startbildschirms
# ---------------------------------------------------------------------------


class SplashZentrierungTests(unittest.TestCase):
    """``_center_window_coords`` - sonst nirgends im Pruefbestand."""

    def test_auf_einem_normalen_bildschirm_sitzt_es_mittig(self) -> None:
        self.assertEqual((760, 440), APP._center_window_coords(1920, 1080, 400, 200))

    def test_auf_einem_zu_kleinen_bildschirm_bleibt_es_am_rand(self) -> None:
        """Ohne Klemmung staende das Fenster bei negativen Koordinaten."""
        self.assertEqual((0, 0), APP._center_window_coords(300, 150, 400, 200))


# ---------------------------------------------------------------------------
# 2 - APR-Erkennung und AMPR-Preflight (Aufgabe 7)
# ---------------------------------------------------------------------------


class AprAmprPreflightTests(unittest.TestCase):
    """Der Weg, der ``fakelib`` in einen Dump legt und den Index anstoesst.

    Die einzige andere Fundstelle im Pruefbestand
    (``test_ffpkg_production_integration.py``) **ersetzt**
    ``_prepare_ampr_support`` durch eine Attrappe - dort wird der Weg also
    gerade nicht geprueft.

    ``mkpfs.ampr`` steht hier als Attrappe: Geprueft wird der Preflight des
    Programms, nicht die Indexerzeugung der Engine. Die Attrappe traegt
    bewusst genau die Signatur, mit der das Programm aufruft - weicht der
    Aufruf spaeter ab, faellt es hier auf.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._ordner = tempfile.TemporaryDirectory()
        wurzel = Path(cls._ordner.name)
        cls.spiel = wurzel / "game"
        emu = wurzel / "ampr_emu"
        (cls.spiel / "sce_sys").mkdir(parents=True)
        emu.mkdir()
        (cls.spiel / "sce_sys" / "playgo-chunk.dat").write_bytes(b"marker")
        (cls.spiel / "eboot.bin").write_bytes(b"game")
        (emu / "libSceAmpr.sprx").write_bytes(b"ampr")
        (emu / "libScePlayGo.sprx").write_bytes(b"playgo")

        gui = _gui()
        gui.mkpfs_dir = MKPFS_ORDNER
        gui._append_to_log = lambda _nachricht: None
        gui._load_setting = lambda _schluessel, vorgabe: vorgabe
        cls.gespeichert: dict[str, str] = {}
        gui._save_setting = cls.gespeichert.__setitem__

        def ensure_ampr_index(root_path, *, enabled=True):
            index = Path(root_path) / "ampr_emu.index"
            index.write_bytes(
                b"AMPRIDX3\n"
                b"/app0/fakelib/libSceAmpr.sprx\n"
                b"/app0/fakelib/libScePlayGo.sprx\n"
            )
            return index if enabled else None

        falsches_mkpfs = types.ModuleType("mkpfs")
        falsches_mkpfs.__path__ = []
        falsches_ampr = types.ModuleType("mkpfs.ampr")
        falsches_ampr.ensure_ampr_index = ensure_ampr_index
        falsches_mkpfs.ampr = falsches_ampr

        with patch.dict(sys.modules,
                        {"mkpfs": falsches_mkpfs, "mkpfs.ampr": falsches_ampr}):
            cls.vorbereitet = gui._prepare_ampr_support(
                str(cls.spiel), {"ampr_emu_folder": str(emu)})

        # Fehlende Ergebnisse werden hier nicht zur Ausnahme: Sonst reisst ein
        # missglueckter Aufbau alle Pruefungen der Klasse mit, und der Bericht
        # sagt nicht mehr, welche Sache fehlt.
        def _inhalt(pfad: Path) -> bytes:
            return pfad.read_bytes() if pfad.is_file() else b""

        cls.index_bytes = _inhalt(cls.spiel / "ampr_emu.index")
        cls.ampr_sprx = _inhalt(cls.spiel / "fakelib" / "libSceAmpr.sprx")
        cls.playgo_sprx = _inhalt(cls.spiel / "fakelib" / "libScePlayGo.sprx")
        cls.emu_ordner = str(emu.resolve())

        # Ein Titel ohne APR-Merkmal darf in der Automatik keinen Dialog oeffnen.
        ohne_apr = wurzel / "no_apr"
        ohne_apr.mkdir()
        gui._ask_yesno_threadsafe = lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("Die Automatik hat einen APR-Dialog geoeffnet"))
        cls.ohne_apr_ergebnis = gui._prepare_ampr_support(str(ohne_apr), {"is_apr": False})

        # Zweite Schreibweise des Merkmals.
        cls.zweitschreibweise = wurzel / "alternate"
        (cls.zweitschreibweise / "sce_sys").mkdir(parents=True)
        (cls.zweitschreibweise / "sce_sys" / "playgo_chunk.dat").write_bytes(b"marker")
        cls.gui = gui

    @classmethod
    def tearDownClass(cls) -> None:
        cls._ordner.cleanup()

    def test_playgo_chunk_mit_bindestrich_gilt_als_apr(self) -> None:
        self.assertTrue(self.gui._detect_apr_title(str(self.spiel)))

    def test_playgo_chunk_mit_unterstrich_gilt_auch(self) -> None:
        """Beide Schreibweisen kommen auf echten Dumps vor."""
        self.assertTrue(self.gui._detect_apr_title(str(self.zweitschreibweise)))

    def test_der_preflight_meldet_erfolg(self) -> None:
        self.assertTrue(self.vorbereitet)

    def test_die_ampr_bibliothek_liegt_im_dump(self) -> None:
        self.assertEqual(b"ampr", self.ampr_sprx,
                         "libSceAmpr.sprx ist nicht im fakelib des Dumps gelandet.")

    def test_die_playgo_bibliothek_liegt_im_dump(self) -> None:
        self.assertEqual(b"playgo", self.playgo_sprx,
                         "libScePlayGo.sprx ist nicht im fakelib des Dumps gelandet.")

    def test_der_index_traegt_die_kennung(self) -> None:
        self.assertTrue(self.index_bytes.startswith(b"AMPRIDX3"))

    def test_beide_bibliotheken_stehen_im_index(self) -> None:
        for pfad in (b"/app0/fakelib/libSceAmpr.sprx", b"/app0/fakelib/libScePlayGo.sprx"):
            with self.subTest(pfad=pfad):
                self.assertIn(pfad, self.index_bytes)

    def test_der_gewaehlte_ordner_wird_gemerkt(self) -> None:
        self.assertEqual(self.emu_ordner, self.gespeichert.get("ampr_emu_folder"))

    def test_ohne_apr_laeuft_die_automatik_dialogfrei_durch(self) -> None:
        """Der Dialog wuerde in der Automatik haengenbleiben - die Attrappe wirft."""
        self.assertTrue(self.ohne_apr_ergebnis)


# ---------------------------------------------------------------------------
# 3 - Zielmatrix von Aufgabe 6
# ---------------------------------------------------------------------------


class _Wert:
    """Ersatz fuer eine Tk-Variable."""

    def __init__(self, wert):
        self.wert = wert

    def get(self):
        return self.wert

    def set(self, wert):
        self.wert = wert


class _Auswahlfeld(dict):
    """Ersatz fuer die Combobox - merkt sich, ob sie sichtbar waere."""

    def __init__(self, ziel):
        super().__init__()
        self.ziel = ziel
        self.sichtbar = True

    def current(self, nummer):
        self.ziel.set(self["values"][nummer])

    def grid(self):
        self.sichtbar = True

    def grid_remove(self):
        self.sichtbar = False


class _Feld:
    """Ersatz fuer Beschriftung und Hinweiszeile."""

    def __init__(self):
        self.sichtbar = True

    def grid(self):
        self.sichtbar = True

    def grid_remove(self):
        self.sichtbar = False

    def config(self, **_kwargs):
        pass


class ZielmatrixTests(unittest.TestCase):
    """``_get_target_options`` - welche Ziele je Quelle gelten.

    ``test_aufgabenwechsel.py`` prueft nur, ob die Felder sichtbar sind;
    welche Ziele angeboten werden, prueft sonst niemand.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._ordner = tempfile.TemporaryDirectory()
        wurzel = Path(cls._ordner.name)
        dump = wurzel / "dump"
        dump.mkdir()
        quellen = {"folder": dump}
        for art in ("ffpfsc", "exfat", "ffpkg"):
            quelle = wurzel / f"source.{art}"
            quelle.write_bytes(b"test")
            quellen[art] = quelle

        gui = _gui()
        cls.matrix = {
            art: gui._get_target_options("universal_convert", str(quelle))
            for art, quelle in quellen.items()
        }

        gui.current_mode = _Wert("universal_convert")
        gui.source_path = _Wert(str(dump))
        gui.target_format = _Wert(".ffpkg")
        gui.format_combo = _Auswahlfeld(gui.target_format)
        gui.format_title = _Feld()
        gui.format_info_label = _Feld()

        felder = (gui.format_title, gui.format_combo, gui.format_info_label)
        gui._refresh_target_format_options()
        cls.sichtbar_beim_umwandeln = all(f.sichtbar for f in felder)
        gui._refresh_target_format_options("ampr_manager")
        cls.verborgen_bei_aufgabe_7 = all(not f.sichtbar for f in felder)
        gui._refresh_target_format_options("universal_convert")
        cls.wieder_sichtbar = all(f.sichtbar for f in felder)
        cls.gewaehlt = gui.target_format.get()
        cls.eintraege = gui.format_combo["values"]

    @classmethod
    def tearDownClass(cls) -> None:
        cls._ordner.cleanup()

    def test_ein_dump_ordner_kann_in_vier_formate(self) -> None:
        self.assertEqual(("ffpfsc", "ffpfs", "exfat", "ffpkg"), self.matrix["folder"])

    def test_eine_ffpfsc_kann_in_vier_formate(self) -> None:
        self.assertEqual(("folder", "ffpfs", "exfat", "ffpkg"), self.matrix["ffpfsc"])

    def test_eine_exfat_kann_in_vier_formate(self) -> None:
        self.assertEqual(("folder", "ffpfsc", "ffpfs", "ffpkg"), self.matrix["exfat"])

    def test_eine_ffpkg_kann_in_vier_formate(self) -> None:
        self.assertEqual(("folder", "ffpfsc", "ffpfs", "exfat"), self.matrix["ffpkg"])

    def test_ffpkg_steht_jeder_packbaren_quelle_offen(self) -> None:
        for art in ("folder", "ffpfsc", "exfat"):
            with self.subTest(quelle=art):
                self.assertIn("ffpkg", self.matrix[art])

    def test_ffpkg_ist_kein_ziel_fuer_sich_selbst(self) -> None:
        self.assertNotIn("ffpkg", self.matrix["ffpkg"])

    def test_die_getroffene_wahl_ueberlebt_das_neuaufbauen(self) -> None:
        self.assertEqual(".ffpkg", self.gewaehlt)

    def test_das_auswahlfeld_bietet_alle_vier_an(self) -> None:
        self.assertEqual([".ffpfsc", ".ffpfs (unkomprimiert)", ".exFAT", ".ffpkg"],
                         self.eintraege)

    def test_beim_umwandeln_steht_die_zielwahl_da(self) -> None:
        self.assertTrue(self.sichtbar_beim_umwandeln)

    def test_bei_aufgabe_7_ist_die_zielwahl_weg(self) -> None:
        """Aufgabe 7 schreibt in die Quelle zurueck - ein Ziel gibt es nicht."""
        self.assertTrue(self.verborgen_bei_aufgabe_7)

    def test_nach_dem_zurueckwechseln_ist_sie_wieder_da(self) -> None:
        self.assertTrue(self.wieder_sichtbar)


# ---------------------------------------------------------------------------
# 4 - Temp-Bereinigung nach einem Auftrag
# ---------------------------------------------------------------------------


class TaskTempBereinigungTests(unittest.TestCase):
    """``_cleanup_task_temp_targets`` - die Bereinigung **nach** einem Auftrag.

    Die Bereinigung beim Beenden (``_cleanup_exit_temp_targets``) ist in
    vier weiteren Dateien abgedeckt; diese hier war es nirgends.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._ordner = tempfile.TemporaryDirectory()
        wurzel = Path(cls._ordner.name)
        vorher = wurzel / "ps5conv_previous_task"
        aktuell = wurzel / "ps5conv_current_task"
        gesperrt = wurzel / "ps5conv_blocked_task"
        for pfad in (vorher, aktuell, gesperrt):
            pfad.mkdir()
            (pfad / "temporary.bin").write_bytes(b"temporary")

        gui = _gui()
        gui._exit_cleanup_lock = threading.RLock()
        gui._session_exit_cleanup_paths = {str(vorher.resolve()), str(aktuell.resolve())}
        gui._get_runtime_temp_dir = lambda: str(wurzel)
        cls.protokoll: list[str] = []
        gui._append_to_log = cls.protokoll.append

        cls.bereinigt = gui._cleanup_task_temp_targets({str(vorher.resolve())})
        cls.vorher_pfad, cls.aktuell_pfad, cls.gesperrt_pfad = vorher, aktuell, gesperrt

        # Ein Ordner, den Windows festhaelt: der Lauf muss das melden und ihn
        # vorgemerkt lassen, damit das Beenden ihn spaeter noch erwischt.
        gui._session_exit_cleanup_paths.add(str(gesperrt.resolve()))
        echtes_rmtree = APP.shutil.rmtree
        gesperrt_norm = os.path.normcase(os.path.abspath(gesperrt.resolve()))

        def rmtree_mit_sperre(pfad):
            if os.path.normcase(os.path.abspath(pfad)) == gesperrt_norm:
                raise PermissionError("Datei wird verwendet")
            return echtes_rmtree(pfad)

        APP.shutil.rmtree = rmtree_mit_sperre
        try:
            cls.gesperrt_bereinigt = gui._cleanup_task_temp_targets({str(vorher.resolve())})
        finally:
            APP.shutil.rmtree = echtes_rmtree
        cls.gesperrt_bleibt_vorgemerkt = (
            str(gesperrt.resolve()) in gui._session_exit_cleanup_paths)

        # Beim Beenden wird wiederholt: erst der dritte Versuch geht auf.
        wiederholung = wurzel / "ps5conv_exit_retry"
        wiederholung.mkdir()
        (wiederholung / "temporary.bin").write_bytes(b"temporary")
        gui._session_exit_cleanup_paths = {str(wiederholung.resolve())}
        wiederholung_norm = os.path.normcase(os.path.abspath(wiederholung.resolve()))
        cls.versuche = [0]

        def rmtree_mit_wiederholung(pfad):
            if os.path.normcase(os.path.abspath(pfad)) == wiederholung_norm:
                cls.versuche[0] += 1
                if cls.versuche[0] < 3:
                    raise PermissionError("Datei wird noch verwendet")
            return echtes_rmtree(pfad)

        APP.shutil.rmtree = rmtree_mit_wiederholung
        try:
            cls.beim_beenden = gui._cleanup_exit_temp_targets()
        finally:
            APP.shutil.rmtree = echtes_rmtree
        cls.wiederholung_pfad = wiederholung
        cls.wiederholung_abgemeldet = (
            str(wiederholung.resolve()) not in gui._session_exit_cleanup_paths)
        cls.aktuell_abgemeldet = (
            str(aktuell.resolve()) not in gui._session_exit_cleanup_paths)

        # Ohne eingehaengtes Laufwerk darf das Beenden nur auf den Arbeiter warten.
        arbeiter = threading.Thread(target=lambda: time.sleep(0.05))
        gui._task_thread = arbeiter
        gui._active_mount_drive = None
        gui._active_osf_exe = None
        gui.is_running = True
        arbeiter.start()
        gui._force_dismount_all()
        cls.arbeiter_beendet = not arbeiter.is_alive()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._ordner.cleanup()

    def test_der_ordner_des_auftrags_ist_weg(self) -> None:
        self.assertTrue(self.bereinigt)
        self.assertFalse(self.aktuell_pfad.exists())

    def test_der_ordner_des_vorherigen_auftrags_bleibt(self) -> None:
        """Uebergeben wird, was verschont werden soll - sonst raeumt es zu viel."""
        self.assertTrue(self.vorher_pfad.is_dir())

    def test_der_bereinigte_pfad_ist_abgemeldet(self) -> None:
        self.assertTrue(self.aktuell_abgemeldet)

    def test_ein_loeschfehler_wird_gemeldet(self) -> None:
        self.assertFalse(self.gesperrt_bereinigt)

    def test_der_gesperrte_ordner_bleibt_liegen(self) -> None:
        self.assertTrue(self.gesperrt_pfad.is_dir())

    def test_der_gesperrte_ordner_bleibt_vorgemerkt(self) -> None:
        """Sonst bliebe er nach dem Beenden fuer immer liegen."""
        self.assertTrue(self.gesperrt_bleibt_vorgemerkt)

    def test_beim_beenden_wird_wiederholt(self) -> None:
        self.assertEqual(3, self.versuche[0])

    def test_nach_der_freigabe_ist_er_weg(self) -> None:
        self.assertTrue(self.beim_beenden)
        self.assertFalse(self.wiederholung_pfad.exists())

    def test_das_beenden_meldet_den_pfad_ab(self) -> None:
        self.assertTrue(self.wiederholung_abgemeldet)

    def test_ohne_laufwerk_wird_auf_den_arbeiter_gewartet(self) -> None:
        self.assertTrue(self.arbeiter_beendet)

    def test_die_bereinigung_steht_im_protokoll(self) -> None:
        self.assertTrue(any("Automatische Task-Bereinigung abgeschlossen" in zeile
                            for zeile in self.protokoll),
                        "Ohne Protokollzeile sieht der Anwender nicht, dass geraeumt wurde.")


# ---------------------------------------------------------------------------
# 5 - Der native FFPKG-Validator
# ---------------------------------------------------------------------------


class FfpkgValidatorTests(unittest.TestCase):
    """``FfpkgValidator.validate`` - Ablauf und Schreibschutz.

    ``test_validator_ungeprueft.py`` deckt die Randfaelle ab (fehlende
    Rechte, fehlendes Werkzeug, leere Datei). Der Ablauf selbst und der
    Schreibschutz von ``fsck_ufs`` standen nur in der Datei, die nie lief.
    """

    def setUp(self) -> None:
        self._ordner = tempfile.TemporaryDirectory()
        wurzel = Path(self._ordner.name)
        self.abbild = wurzel / "test.ffpkg"
        self.werkzeug = wurzel / "UFS2Tool.exe"
        self.abbild.write_bytes(b"UFS2 test payload")
        self.werkzeug.write_bytes(b"test executable placeholder")
        self.addCleanup(self._ordner.cleanup)

    def _lauf(self, *antworten):
        """Laesst den Validator laufen und gibt jedem Aufruf eine Antwort vor."""
        from ps5_validator.modules.ffpkg_validator import FfpkgValidator

        fertige = [SimpleNamespace(returncode=code, stdout=text)
                   for code, text in antworten]
        with patch("ps5_validator.modules.ffpkg_validator.subprocess.run",
                   side_effect=fertige) as aufrufe:
            ergebnis = FfpkgValidator(str(self.werkzeug)).validate(str(self.abbild))
        return ergebnis, aufrufe

    def test_ein_fehler_beim_lesen_gilt_als_beschaedigt(self) -> None:
        ergebnis, aufrufe = self._lauf((2, "invalid superblock"))
        self.assertEqual("CORRUPTED", ergebnis.status)
        self.assertEqual(1, aufrufe.call_count,
                         "Nach einem Lesefehler darf fsck nicht mehr starten.")

    def test_ein_fehler_bei_der_dateisystempruefung_gilt_als_beschaedigt(self) -> None:
        ergebnis, aufrufe = self._lauf((0, "UFS2 filesystem"), (4, "duplicate block"))
        self.assertEqual("CORRUPTED", ergebnis.status)
        self.assertEqual(2, aufrufe.call_count)

    def test_ein_sauberes_abbild_wird_angenommen(self) -> None:
        ergebnis, aufrufe = self._lauf((0, "UFS2 filesystem"), (0, "filesystem clean"))
        self.assertEqual("OK", ergebnis.status)
        self.assertEqual(2, aufrufe.call_count)
        self.assertIn(self.abbild.name, ergebnis.hashes)

    def test_die_dateisystempruefung_darf_nicht_schreiben(self) -> None:
        """``-n`` beantwortet jede Rueckfrage mit Nein - sonst repariert fsck.

        Ein Reparaturlauf wuerde das Abbild des Anwenders veraendern.
        """
        _ergebnis, aufrufe = self._lauf((0, "UFS2 filesystem"), (0, "filesystem clean"))
        self.assertEqual(["fsck_ufs", "-fn"], aufrufe.call_args_list[1].args[0][1:3])


# ---------------------------------------------------------------------------
# 6 - Die Abschlusspruefung des Ergebnisses
# ---------------------------------------------------------------------------


class AbschlusspruefungTests(unittest.TestCase):
    """``_verify_output_artifact`` - erkennt sie ein untaugliches Ergebnis?

    Ohne sie gilt ein Lauf als gelungen, und der Fehler faellt erst auf der
    Konsole auf.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._ordner = tempfile.TemporaryDirectory()
        wurzel = Path(cls._ordner.name)

        defekt = wurzel / "broken.ffpfsc"
        defekt.write_bytes(b"not-a-pfs-container")

        gui = _gui()
        gui._extract_embedded_mkpfs = lambda: MKPFS_ORDNER
        cls.defekt_befund = gui._verify_output_artifact("pack_file", str(defekt))

        gui._current_language = "de"
        gui.target_format = SimpleNamespace(get=lambda: "Dump-Ordner")

        kein_dump = wurzel / "kein_dump"
        kein_dump.mkdir()
        (kein_dump / "inner_image.exfat").write_bytes(b"x" * 4096)
        cls.kein_dump_befund = gui._verify_output_artifact("universal_convert", str(kein_dump))

        echter_dump = wurzel / "echter_dump"
        (echter_dump / "sce_sys").mkdir(parents=True)
        (echter_dump / "eboot.bin").write_bytes(b"y" * 4096)
        cls.echter_befund = gui._verify_output_artifact("universal_convert", str(echter_dump))

        sammelziel = wurzel / "sammelziel"
        (sammelziel / "spiel_a").mkdir(parents=True)
        (sammelziel / "spiel_a" / "eboot.bin").write_bytes(b"z" * 4096)
        cls.sammel_befund = gui._verify_output_artifact("batch_convert", str(sammelziel))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._ordner.cleanup()

    def test_ein_defektes_ffpfsc_faellt_durch(self) -> None:
        self.assertFalse(self.defekt_befund["ok"])

    def test_geprueft_wird_mit_der_engine(self) -> None:
        self.assertEqual("mkpfs-verify", self.defekt_befund["method"])

    def test_ein_ordner_ohne_spieldateien_faellt_durch(self) -> None:
        """Falsch verschachtelt liefert einen Ordner mit einem Container darin."""
        self.assertFalse(self.kein_dump_befund["ok"])

    def test_ein_echter_dump_wird_angenommen(self) -> None:
        self.assertTrue(self.echter_befund["ok"])

    def test_ein_sammelziel_mit_dumps_darin_wird_angenommen(self) -> None:
        self.assertTrue(self.sammel_befund["ok"])


# ---------------------------------------------------------------------------
# 7 - Das Neupacken in Aufgabe 7 (Aufbau des Quelltextes)
# ---------------------------------------------------------------------------


class AufgabeSiebenNeupackenTests(unittest.TestCase):
    """``_repack_nested_ffpfsc`` - gemessen am Syntaxbaum, nicht am Wortlaut.

    Die Funktion liegt **innerhalb** von ``_mode_ampr_manager`` und ist von
    aussen nicht aufrufbar; ein Wirkungstest ginge nur ueber einen Umbau des
    Programms. Statt im Quelltext nach Zeichenketten zu suchen, liest diese
    Pruefung die **uebergebenen Werte** der ``_execute_mkpfs``-Aufrufe aus
    dem Syntaxbaum. Umformatieren, Umbrechen und Umbenennen von
    Hilfsvariablen aendern daran nichts.

    Seit dem 03.09.2026 gibt es dort drei Aufrufe statt zwei: Die Funktion
    packt in der Bauform zurueck, aus der die Quelle kam, und der einstufige
    Weg braucht einen eigenen. Zugeordnet wird deshalb nach Art des Aufrufs
    und nicht nach seiner Stelle - sonst haengt die Pruefung an der
    Reihenfolge im Quelltext.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.aufgabe7 = _funktion("_mode_ampr_manager")
        cls.neupacken = _funktion("_repack_nested_ffpfsc", cls.aufgabe7)
        aufrufe = [_zeichenketten(k.args[0])
                   for k in _aufrufe(cls.neupacken, "_execute_mkpfs") if k.args]
        cls.innen = next(
            (a for a in aufrufe if a[:2] == ["pack", "folder"] and "--raw" in a), [])
        cls.einstufig = next(
            (a for a in aufrufe if a[:2] == ["pack", "folder"] and "--raw" not in a), [])
        cls.aussen = next((a for a in aufrufe if a[:2] == ["pack", "file"]), [])
        assert cls.innen and cls.aussen and cls.einstufig, (
            "Erwartet werden drei Aufrufe: einstufig, inneres PFS, aeusserer "
            "Container. Gefunden: %r" % (aufrufe,))

    def test_das_innere_pfs_wird_gepackt(self) -> None:
        self.assertEqual(["pack", "folder"], self.innen[:2])

    def test_das_innere_pfs_bleibt_unkomprimiert(self) -> None:
        """Sonst entstuende doppelt komprimierter Inhalt."""
        self.assertIn("--no-compress", self.innen)

    def test_das_innere_pfs_wird_roh_gepackt(self) -> None:
        """Ohne --raw legt mkpfs noch ein Image dazwischen - dreifach
        verschachtelt und auf der Konsole unbrauchbar."""
        self.assertIn("--raw", self.innen)

    def test_der_aeussere_container_wird_als_datei_gepackt(self) -> None:
        self.assertEqual(["pack", "file"], self.aussen[:2])

    def test_der_aeussere_container_folgt_der_zielendung(self) -> None:
        """``.ffpfs`` bleibt unkomprimiert, ``.ffpfsc`` wird komprimiert -
        im Quelltext ein Bedingungsausdruck, hier an beiden Zweigen erkannt."""
        self.assertIn("--no-compress", self.aussen)
        self.assertIn("--compress", self.aussen)
        self.assertIn(".ffpfs", _zeichenketten(self.neupacken))

    def test_der_innenname_bleibt_unveraendert(self) -> None:
        """mkpfs leitete den Namen sonst ueber die Endungen ab und verstuemmelte
        Titel mit Punkten in Klammern."""
        self.assertIn("--no-rename-inner-image", self.aussen)

    def test_der_einstufige_weg_packt_nicht_roh(self) -> None:
        """Ohne ``--raw`` wickelt die Engine das exFAT selbst - genau dafuer
        gibt es diesen Weg. Mit ``--raw`` waere es der zweistufige."""
        self.assertEqual(["pack", "folder"], self.einstufig[:2])
        self.assertNotIn("--raw", self.einstufig)

    def test_der_einstufige_weg_sagt_ob_komprimiert_wird(self) -> None:
        """Sich auf die Vorgabe der Engine zu verlassen, hat hier schon
        einmal zu einem stillen Wechsel gefuehrt."""
        self.assertTrue({"--compress", "--no-compress"} & set(self.einstufig),
                        "Der einstufige Weg nennt die Kompression nicht.")


class GemeinsameAuspackschleifeTests(unittest.TestCase):
    """Aufgabe 2, 4 und 7 packen ueber dieselbe Schleife aus.

    Frueher hatte jede ihre eigene Fassung - und Korrekturen erreichten nur
    eine davon. Auch das ist am Syntaxbaum gemessen: gefragt wird, ob der
    Aufruf im Baum steht, nicht ob eine Zeichenkette im Text vorkommt.
    """

    def test_aufgabe_7_ruft_die_gemeinsame_schleife(self) -> None:
        self.assertTrue(_aufrufe(_funktion("_mode_ampr_manager"), "_entpacke_container_ebenen"))

    def test_aufgabe_2_ruft_die_gemeinsame_schleife(self) -> None:
        self.assertTrue(_aufrufe(_funktion("_mode_unpack_to_exfat"), "_entpacke_container_ebenen"))

    def test_die_schleife_erkennt_ein_ufs2_innenabbild(self) -> None:
        innen = _funktion("_extract_inner_image")
        self.assertIn("ufs2", _zeichenketten(innen))
        self.assertTrue(_aufrufe(innen, "_extract_ffpkg_to_folder_via_ufs2tool"))

    def test_der_eigene_exfat_leser_kommt_vor_osfmount(self) -> None:
        """Reihenfolge zaehlt: OSFMount nur, wenn der eigene Leser scheitert."""
        innen = _funktion("_extract_inner_image")
        eigener = _aufrufe(innen, "_extract_exfat_to_folder_mkpfs")
        osfmount = _aufrufe(innen, "_extract_exfat_via_osfmount")
        self.assertTrue(eigener and osfmount, "Einer der beiden Wege fehlt.")
        self.assertLess(eigener[0].lineno, osfmount[0].lineno)


# ---------------------------------------------------------------------------
# 8 - Vorschau und Spiel-Infobox ueber alle acht Aufgaben
# ---------------------------------------------------------------------------


class AufgabenbestandTests(unittest.TestCase):
    """Acht Aufgaben, und fuer jede eine Quellregel."""

    ERWARTET = (
        "pack_folder", "unpack_to_exfat", "pack_file", "ffpkg_to_ffpfsc",
        "batch_convert", "universal_convert", "ampr_manager", "dump_validator",
    )

    def test_es_sind_genau_diese_acht(self) -> None:
        self.assertEqual(
            self.ERWARTET,
            tuple(modus for _beschriftung, modus in APP.PS5ConverterGUI._MODE_OPTIONS))

    def test_jede_aufgabe_hat_eine_quellregel(self) -> None:
        for modus in self.ERWARTET:
            with self.subTest(aufgabe=modus):
                self.assertIn(modus, APP.PS5ConverterGUI._MODE_SOURCE_TYPES)


class MetadatenVorrangTests(unittest.TestCase):
    """Strukturierte UFS2-Daten haben Vorrang vor dem Muster-Scan.

    Der Muster-Scan raet aus den Rohbytes. Wenn er gewinnt, steht ein
    geratener Titel in der Infobox, ohne dass es jemand merkt - deshalb muss
    er auch gekennzeichnet sein.
    """

    STRUKTURIERT = {
        "title": "Structured Title", "title_id": "PPSA12345",
        "version": "01.000.000", "required_firmware": "09.00",
        "region": "Europa", "category": "Spiel", "publisher": "Structured Publisher",
    }
    GERATEN = {
        "title": "Heuristic Title", "title_id": "PPUS99999",
        "version": "02.000.000", "required_firmware": "–",
        "region": "USA", "category": "–", "publisher": "–",
    }
    LEER = {schluessel: "–" for schluessel in STRUKTURIERT}

    def _meta(self, ufs2_antwort):
        """Liest die Metadaten einer .ffpkg mit vorgegebenen Teilantworten."""
        ordner = tempfile.TemporaryDirectory()
        self.addCleanup(ordner.cleanup)
        abbild = Path(ordner.name) / "probe.ffpkg"
        abbild.write_bytes(b"UFS2 preview")

        gui = _gui()
        gui.is_running = False
        gui._preview_cache = {}
        gui._PREVIEW_CACHE_MAX = 20
        gui._preview_candidate_dirs = lambda *_a, **_k: []
        gui._extract_meta_from_ffpkg_ufs2 = lambda _quelle: (ufs2_antwort, None)
        gui._extract_meta_from_ffpkg_file = lambda _quelle: dict(self.GERATEN)
        meta, _rest = gui._extract_meta_from_file(
            str(abbild), "ffpkg_to_ffpfsc", _candidate_dirs=[])
        return meta

    def test_strukturierte_daten_gewinnen(self) -> None:
        meta = self._meta(dict(self.STRUKTURIERT))
        self.assertEqual("Structured Title", meta["title"])
        self.assertEqual("PPSA12345", meta["title_id"])
        self.assertEqual("UFS2Tool/Dokan (read-only)", meta["_metadata_method"])

    def test_ohne_strukturierte_daten_greift_der_muster_scan(self) -> None:
        meta = self._meta(dict(self.LEER))
        self.assertEqual("Heuristic Title", meta["title"])

    def test_der_muster_scan_ist_als_solcher_gekennzeichnet(self) -> None:
        meta = self._meta(dict(self.LEER))
        self.assertEqual("FFPKG-Muster-Scan (Fallback)", meta["_metadata_method"])


class ParamJsonTests(unittest.TestCase):
    """Was aus ``param.json`` in die Infobox kommt."""

    NUTZLAST = {
        "titleId": "PPSA12345",
        "contentVersion": "01.000.000",
        "requiredSystemSoftwareVersion": "09.00",
        "applicationCategoryType": 0,
        "localizedParameters": {
            "en-US": {"titleName": "Metadata Title", "publisher": "Metadata Publisher"}
        },
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.meta = _gui()._meta_from_param_json_payload(cls.NUTZLAST)

    def test_der_titel_kommt_aus_den_uebersetzten_angaben(self) -> None:
        self.assertEqual("Metadata Title", self.meta["title"])

    def test_der_hersteller_kommt_mit(self) -> None:
        self.assertEqual("Metadata Publisher", self.meta["publisher"])

    def test_die_firmware_kommt_mit(self) -> None:
        self.assertEqual("09.00", self.meta["required_firmware"])

    def test_die_kategorie_wird_uebersetzt(self) -> None:
        """``applicationCategoryType`` 0 ist ein Spiel."""
        self.assertEqual("Spiel", self.meta["category"])


class InfoboxAnzeigeTests(unittest.TestCase):
    """Was die Infobox anzeigt - an der Textquelle und am Syntaxbaum gemessen."""

    def test_die_beschriftungen_gibt_es_in_beiden_sprachen(self) -> None:
        for schluessel in ("info_popup.meta.publisher", "info_popup.format_label",
                           "info_popup.metadata_label"):
            with self.subTest(schluessel=schluessel):
                eintrag = STRINGS.get(schluessel)
                self.assertIsNotNone(eintrag, f"{schluessel} fehlt in der Textquelle.")
                self.assertTrue(eintrag.get("de") and eintrag.get("en"))

    def test_die_infobox_holt_diese_beschriftungen(self) -> None:
        infobox = _funktion("_build_info_popup")
        geholt = {k.args[0].value for k in _aufrufe(infobox, "_t")
                  if k.args and isinstance(k.args[0], ast.Constant)}
        for schluessel in ("info_popup.meta.publisher", "info_popup.format_label",
                           "info_popup.metadata_label"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, geholt)

    def test_die_vorschau_kennt_die_stapelaufgabe(self) -> None:
        """Aufgabe 5 braucht einen eigenen Zweig - sie zeigt einen Ordner
        voller Dumps, nicht einen einzelnen."""
        self.assertIn("batch_convert", _zeichenketten(_funktion("_calc")))

    def test_die_vorschau_kennt_die_ordneraufgaben(self) -> None:
        vorschau = _zeichenketten(_funktion("_calc"))
        for modus in ("pack_folder", "ampr_manager", "universal_convert"):
            with self.subTest(aufgabe=modus):
                self.assertIn(modus, vorschau)


class KeepaliveTests(unittest.TestCase):
    """``_emit_processing_keepalive`` - der Lebenszeichen-Hinweis.

    Nachgezogen am 03.09.2026 aus derselben toten Datei. Diese Pruefung war
    die einzige der uebrigen sieben mit einer echten Wirkung, und sie stand
    sonst nirgends: ``_emit_processing_keepalive`` kommt im ganzen
    Pruefbestand kein zweites Mal vor.

    Worum es geht: Der Hinweis "Verarbeitung laeuft" darf den Zeitstempel
    der letzten Engine-Ausgabe **nicht** anfassen. Taete er es, saehe die
    Ueberwachung eine Engine, die staendig etwas von sich gibt, und ein
    haengender Lauf fiele nie auf.
    """

    @classmethod
    def setUpClass(cls) -> None:
        gui = _gui()
        gui._last_engine_output_ts = 123.0
        gui.task_current_step = 3
        gui.task_num_steps = 4
        cls.protokoll: list[str] = []
        cls.status: list[str] = []
        gui._append_to_log = cls.protokoll.append
        gui._set_status = cls.status.append
        gui._emit_processing_keepalive()
        cls.zeitstempel = gui._last_engine_output_ts

    def test_der_hinweis_steht_im_protokoll(self) -> None:
        self.assertEqual(["[INFO] Verarbeitung läuft ... bitte warten.\n"], self.protokoll)

    def test_die_statuszeile_sagt_dasselbe(self) -> None:
        self.assertEqual(1, len(self.status))
        self.assertTrue(self.status[0].endswith("Verarbeitung läuft ..."))

    def test_der_zeitstempel_der_engine_bleibt_unberuehrt(self) -> None:
        """Sonst sieht die Ueberwachung eine Engine, die gar nichts sagt."""
        self.assertEqual(123.0, self.zeitstempel)


class StilTests(unittest.TestCase):
    """Tabs und Leerraum am Zeilenende - im ganzen eigenen Bestand.

    Auch das kommt aus der toten Datei; dort galt es nur fuer den
    Monolithen und konnte ohnehin nichts melden. Der Bauplan laesst kein
    ruff oder flake8 laufen, es gibt also sonst keinen Stilwaechter.

    Zwei harte Sachen werden geprueft, keine Geschmacksfragen: ein Tab in
    einer Datei, die sonst Leerzeichen einrueckt, und Leerraum am
    Zeilenende. Zeilenlaengen bleiben aussen vor - davon gibt es im
    Monolithen ueber neunzig, und sie sind eine Stilfrage, keine Sache.
    """

    #: Die Fremdbestandteile bringen ihren eigenen Stil mit; sie werden
    #: unveraendert uebernommen und nicht von uns gepflegt.
    FREMD = ("MkPFS-", "PS4FFPFSC-", "UFS2Tool-", "ProsperoPkg-", "Backport_Fakelibs/",
             "PS5-AppInstall/", "PS5 WebKit Autoloader/", "PlayGo & AMPR_EMU/",
             "helloworld/", "tools/")

    @classmethod
    def eigene_dateien(cls) -> list[str]:
        """Alle verfolgten .py-Dateien, die dieses Projekt selbst pflegt."""
        roh = subprocess.run(["git", "ls-files", "*.py"], cwd=str(PROJEKT),
                             capture_output=True, text=True, timeout=120).stdout
        return [d for d in roh.split()
                if not d.startswith(cls.FREMD)]

    def test_es_gibt_ueberhaupt_dateien_zu_pruefen(self) -> None:
        """Gegenprobe: Ohne sie saehe man den beiden Pruefungen unten nicht an,
        ob sie etwas angesehen haben."""
        self.assertGreater(len(self.eigene_dateien()), 100)

    def test_keine_tabs(self) -> None:
        funde = []
        for datei in self.eigene_dateien():
            pfad = PROJEKT / datei
            if not pfad.is_file():
                continue
            for nummer, zeile in enumerate(
                    pfad.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if "\t" in zeile:
                    funde.append(f"{datei}:{nummer}")
        self.assertEqual([], funde[:20], f"{len(funde)} Zeile(n) mit Tab")

    def test_kein_leerraum_am_zeilenende(self) -> None:
        funde = []
        for datei in self.eigene_dateien():
            pfad = PROJEKT / datei
            if not pfad.is_file():
                continue
            for nummer, zeile in enumerate(
                    pfad.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if zeile != zeile.rstrip(" \t"):
                    funde.append(f"{datei}:{nummer}")
        self.assertEqual([], funde[:20], f"{len(funde)} Zeile(n) mit Leerraum am Ende")


class KeineTotenPruefungenTests(unittest.TestCase):
    """Niemand darf mehr eine Pruefung schreiben, die nie laeuft.

    Das ist der eigentliche Fund dieser ganzen Runde: ``unittest`` sammelt
    nur Methoden in ``TestCase``-Klassen ein. Eine Funktion ``test_*`` auf
    Modulebene sieht aus wie eine Pruefung, laeuft aber nie mit - und faellt
    niemandem auf, weil der Bericht sie schlicht nicht erwaehnt.

    Am 03.09.2026 waren es 24 solche Funktionen in drei Dateien: zweimal
    dieselbe tote Qualitaetsdatei und acht Bau-Voraussetzungen in
    ``test_build_ready.py``, das daneben elf laufende Pruefungen trug.
    """

    def test_keine_pruefung_steht_auf_modulebene(self) -> None:
        funde: list[str] = []
        for datei in sorted(PROJEKT.glob("test_*.py")):
            baum = ast.parse(datei.read_text(encoding="utf-8", errors="replace"))
            for knoten in baum.body:
                if (isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and knoten.name.startswith("test")):
                    funde.append(f"{datei.name}:{knoten.lineno} {knoten.name}")
        self.assertEqual(
            [], funde,
            "Diese Funktionen sehen aus wie Pruefungen, laufen aber nie mit. "
            "In eine TestCase-Klasse nehmen - oder umbenennen, wenn es "
            "Hilfsfunktionen sind:\n  " + "\n  ".join(funde))

    @staticmethod
    def _pruefmethoden(baum: ast.Module) -> int:
        """Zaehlt die Methoden, die unittest aus dieser Datei einsammelt.

        Vererbung zaehlt mit: ``test_sammel_ordner.py`` fuehrt eine
        Basisklasse ``_MitOrdner(unittest.TestCase)`` ohne eigene
        Pruefungen, und die zwanzig Pruefungen stehen in Klassen, die
        davon erben. Eine Zaehlung, die nur auf das Wort "TestCase" in der
        Basis sieht, haelt so eine Datei faelschlich fuer einen
        Blindgaenger - am 03.09.2026 genau so passiert.
        """
        klassen = {k.name: k for k in ast.walk(baum) if isinstance(k, ast.ClassDef)}
        pruefklassen: set[str] = set()
        # Erst die offensichtlichen, dann so lange erben lassen, bis sich
        # nichts mehr aendert.
        gewachsen = True
        while gewachsen:
            gewachsen = False
            for name, knoten in klassen.items():
                if name in pruefklassen:
                    continue
                basen = [ast.unparse(b) for b in knoten.bases]
                if any("TestCase" in b for b in basen) or any(b in pruefklassen for b in basen):
                    pruefklassen.add(name)
                    gewachsen = True
        return sum(1 for name in pruefklassen for m in klassen[name].body
                   if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and m.name.startswith("test"))

    def test_jede_pruefdatei_traegt_auch_etwas_bei(self) -> None:
        """Eine test_*.py ohne eine einzige Pruefmethode ist ein Blindgaenger."""
        leer: list[str] = []
        for datei in sorted(PROJEKT.glob("test_*.py")):
            baum = ast.parse(datei.read_text(encoding="utf-8", errors="replace"))
            if self._pruefmethoden(baum) == 0:
                leer.append(datei.name)
        self.assertEqual([], leer,
                         "Aus diesen Dateien sammelt unittest nichts ein: "
                         + ", ".join(leer))

    def test_die_zaehlung_sieht_auch_geerbte_pruefklassen(self) -> None:
        """Gegenprobe zur Zaehlung darueber - sonst meldet sie Blindgaenger,
        die keine sind."""
        baum = ast.parse("""
import unittest


class _Basis(unittest.TestCase):
    def setUp(self):
        pass


class Abgeleitet(_Basis):
    def test_eins(self):
        pass

    def test_zwei(self):
        pass
""")
        self.assertEqual(2, self._pruefmethoden(baum))


if __name__ == "__main__":
    unittest.main(verbosity=2)
