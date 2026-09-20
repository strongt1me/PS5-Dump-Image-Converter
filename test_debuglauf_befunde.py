# -*- coding: utf-8 -*-
"""Waechter fuer die Befunde des Debuglaufs vom 16./17.09.2026.

Jede Klasse haelt eine Fehlerklasse fest, die bis v1.9.24 im Programm
steckte und von keinem Test gesehen wurde - obwohl die Testreihe gruen war.
Gemessen wird am Verhalten (echte Dateien, echte Tk-Variablen, echte Faeden),
wo das geht; sonst am Syntaxbaum, nie am Wortlaut.

Jeder Waechter wurde gegen den alten Fehler gehalten (Gegenprobe) und schlug
dort an.
"""
from __future__ import annotations

import ast
import calendar
import ftplib
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))
# mkpfs.utils.is_ignored_name - ohne den Pfad zaehlte der Rueckfall alles mit,
# und der exFAT-Waechter maesse nichts.
sys.path.insert(0, str(PROJEKT / "MkPFS-1.0.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("debuglauf_befunde")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402

GUI = APP.PS5ConverterGUI
HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    # Eine Wurzel je Prozess, nie zerstoeren - siehe test_fensterlayout.py.
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    tk = None
    _WURZEL = None
    TK_DA = False

_INSTANZ: list = []


def _app():
    """Eine gemeinsame Programminstanz fuer diese Datei."""
    if not _INSTANZ:
        _INSTANZ.append(GUI(_WURZEL))
    return _INSTANZ[0]


def _schreiben(pfad: str, inhalt: bytes = b"x") -> str:
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "wb") as fh:
        fh.write(inhalt)
    return pfad


def _klasse(baum: ast.Module, name: str = "PS5ConverterGUI") -> ast.ClassDef:
    return next(k for k in ast.walk(baum)
                if isinstance(k, ast.ClassDef) and k.name == name)


def _methode(klasse: ast.ClassDef, name: str) -> ast.FunctionDef:
    return next(m for m in klasse.body
                if isinstance(m, ast.FunctionDef) and m.name == name)


class _TempTest(unittest.TestCase):
    """Ein eigener Ordner je Test, danach entfernt."""

    def setUp(self) -> None:
        self.basis = tempfile.mkdtemp(prefix="dbg_befund_")
        self.addCleanup(shutil.rmtree, self.basis, True)


# ---------------------------------------------------------------------------
# Datenverlust
# ---------------------------------------------------------------------------

@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ExitAufraeumenTests(_TempTest):
    """Das Aufraeumen beim Beenden loeschte fertige Ergebnisse.

    Bis v1.9.24 galt alles unter dem Arbeitsordner als "verwaltet". Lag das
    Ziel dort (Temp = Ziel, oder der Arbeitsordner ist ein ganzes Laufwerk),
    loeschten Beenden, Herunterfahren und das Ende jedes ``--cli``-Laufs das
    Ergebnis; in der Sammelkonvertierung den ganzen Zielordner.
    """

    def setUp(self) -> None:
        super().setUp()
        self.app = _app()
        vorher_temp = self.app.temp_path.get()
        vorher_ziel = getattr(self.app, "task_final_output_path", "")

        def _zurueck() -> None:
            self.app.temp_path.set(vorher_temp)
            self.app._temp_pruefung = None
            self.app.task_final_output_path = vorher_ziel

        self.addCleanup(_zurueck)

    def _arbeitsordner(self, name: str) -> str:
        arbeit = os.path.join(self.basis, name)
        os.makedirs(arbeit)
        self.app.temp_path.set(arbeit)
        self.app._temp_pruefung = None
        self.assertEqual(os.path.normcase(os.path.abspath(self.app._get_runtime_temp_dir())),
                         os.path.normcase(os.path.abspath(arbeit)),
                         "Der Arbeitsordner wurde nicht uebernommen - der Test "
                         "maesse sonst etwas anderes.")
        return arbeit

    def test_ergebnis_im_arbeitsordner_ueberlebt(self) -> None:
        arbeit = self._arbeitsordner("arbeit")
        ergebnis = _schreiben(os.path.join(arbeit, "Spiel.ffpfsc"), b"x" * 1024)
        self.app.task_final_output_path = ergebnis
        self.app._cleanup_exit_temp_targets()
        self.assertTrue(os.path.isfile(ergebnis),
                        "Das fertige Ergebnis im Arbeitsordner wurde beim "
                        "Beenden geloescht.")

    def test_sammelziel_gleich_arbeitsordner_ueberlebt(self) -> None:
        arbeit = self._arbeitsordner("arbeit")
        fremd = _schreiben(os.path.join(arbeit, "anderes_spiel.ffpkg"))
        self.app.task_final_output_path = arbeit
        self.app._cleanup_exit_temp_targets()
        self.assertTrue(os.path.isdir(arbeit), "Der Arbeitsordner selbst ist weg.")
        self.assertTrue(os.path.isfile(fremd), "Fremde Dateien im Ziel sind weg.")

    def test_arbeitsordner_mit_programmnamen_zaehlt_nicht(self) -> None:
        """Heisst der gewaehlte Ordner selbst ps5conv_..., gilt sein Inhalt
        trotzdem nicht als verwaltet."""
        arbeit = self._arbeitsordner("ps5conv_eigene_wahl")
        ergebnis = _schreiben(os.path.join(arbeit, "Spiel.exfat"))
        self.app.task_final_output_path = ergebnis
        self.app._cleanup_exit_temp_targets()
        self.assertTrue(os.path.isfile(ergebnis))

    def test_echte_reste_werden_weiter_entfernt(self) -> None:
        """Gegenprobe: Das Aufraeumen darf nicht einfach abgeschaltet sein."""
        arbeit = self._arbeitsordner("arbeit")
        rest = os.path.join(arbeit, "ps5conv_rest_abc")
        _schreiben(os.path.join(rest, "halb.bin"))
        self.app.task_final_output_path = rest
        self.app._cleanup_exit_temp_targets()
        self.assertFalse(os.path.exists(rest),
                         "Ein echter ps5conv_-Rest blieb liegen.")


class PfadLiegtInTests(unittest.TestCase):
    """Grundlage der Sperre "Ziel enthaelt Quelle" (Ja loeschte die Quelle)."""

    def test_verschachtelt_und_gleich(self) -> None:
        basis = os.path.join(tempfile.gettempdir(), "dbg_liegt_in")
        self.assertTrue(GUI._pfad_liegt_in(os.path.join(basis, "Spiel", "Spiel.exfat"), basis))
        self.assertTrue(GUI._pfad_liegt_in(basis, basis))

    def test_gleicher_anfang_ist_kein_enthaltensein(self) -> None:
        basis = os.path.join(tempfile.gettempdir(), "dbg_liegt_in")
        self.assertFalse(GUI._pfad_liegt_in(basis + "2", basis))
        self.assertFalse(GUI._pfad_liegt_in(os.path.join(basis + "2", "x"), basis))

    def test_leer_ist_nie_enthalten(self) -> None:
        self.assertFalse(GUI._pfad_liegt_in("", "C:\\"))
        self.assertFalse(GUI._pfad_liegt_in("C:\\x", ""))

    @unittest.skipUnless(os.name == "nt", "Laufwerksbuchstaben gibt es nur unter Windows")
    def test_andere_laufwerke(self) -> None:
        self.assertFalse(GUI._pfad_liegt_in(r"D:\PS5\Spiel", r"E:\PS5"))
        self.assertTrue(GUI._pfad_liegt_in(r"d:\ps5\spiel", r"D:\PS5"))

    def test_die_sperre_steht_vor_der_rueckfrage(self) -> None:
        """Im Aufgabenfaden: erst die Sperre, dann "ueberschreiben?"."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        methode = _methode(_klasse(baum), "_run_engine_thread")
        sperre = [k.lineno for k in ast.walk(methode)
                  if isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "_pfad_liegt_in"]
        frage = [k.lineno for k in ast.walk(methode)
                 if isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "askyesno"]
        loeschen = [k.lineno for k in ast.walk(methode)
                    if isinstance(k, ast.Call)
                    and getattr(k.func, "id", "") == "_rmtree_force"]
        self.assertTrue(sperre, "Die Sperre 'Ziel enthaelt Quelle' fehlt.")
        self.assertTrue(frage and loeschen, "Rueckfrage/Loeschen nicht gefunden - "
                                            "der Test misst sonst nichts.")
        self.assertLess(min(sperre), min(frage))
        self.assertLess(min(sperre), min(loeschen))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class StagingTests(_TempTest):
    """Zwischenablage auf dem Temp-Laufwerk (Cross-Drive-Staging).

    Bis v1.9.24: Eine gleichnamige Datei im Arbeitsordner wurde vorher
    kommentarlos geloescht; scheiterte das Verschieben ins Ziel, meldeten die
    Packwege trotzdem Erfolg, und das Beenden loeschte das einzige Ergebnis.
    """

    def setUp(self) -> None:
        super().setUp()
        self.app = _app()
        laeuft = self.app.is_running
        self.addCleanup(setattr, self.app, "is_running", laeuft)

    def _gestagt(self, inhalt: bytes) -> str:
        stufe = os.path.join(self.basis, "ps5conv_stage_test")
        return _schreiben(os.path.join(stufe, "Spiel.ffpfsc"), inhalt)

    def test_erfolg_bringt_die_datei_ans_ziel_und_raeumt_die_stufe(self) -> None:
        gestagt = self._gestagt(b"abc" * 1000)
        ziel = os.path.join(self.basis, "ziel", "Spiel.ffpfsc")
        self.app.is_running = True
        ergebnis = self.app._finalize_staged_pack_output(gestagt, ziel)
        self.assertTrue(GUI._ergebnis_im_ziel(ergebnis, ziel))
        with open(ziel, "rb") as fh:
            self.assertEqual(fh.read(), b"abc" * 1000)
        self.assertFalse(os.path.exists(os.path.dirname(gestagt)),
                         "Der leere Staging-Ordner blieb liegen.")

    def test_scheitern_rettet_das_ergebnis_aus_der_stufe(self) -> None:
        gestagt = self._gestagt(b"ergebnis")
        # Ein Dateiname, wo der Zielordner hin muesste: makedirs scheitert.
        sperre = _schreiben(os.path.join(self.basis, "datei_statt_ordner"))
        ziel = os.path.join(sperre, "Spiel.ffpfsc")
        self.app.is_running = True
        ergebnis = self.app._finalize_staged_pack_output(gestagt, ziel)
        self.assertFalse(GUI._ergebnis_im_ziel(ergebnis, ziel),
                         "Ein gescheitertes Verschieben gilt als Erfolg.")
        self.assertTrue(os.path.isfile(ergebnis), "Das Ergebnis ist verloren.")
        self.assertFalse(os.path.basename(os.path.dirname(ergebnis)).lower()
                         .startswith("ps5conv_"),
                         "Das Ergebnis liegt noch in einem Ordner, den das "
                         "Beenden als Temp-Rest loescht.")
        with open(ergebnis, "rb") as fh:
            self.assertEqual(fh.read(), b"ergebnis")

    def test_alle_packwege_pruefen_den_ablageort(self) -> None:
        """Wer _finalize_staged_pack_output ruft, muss das Ergebnis pruefen."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        ohne = []
        mit = 0
        for m in _klasse(baum).body:
            if not isinstance(m, ast.FunctionDef) or m.name == "_finalize_staged_pack_output":
                continue
            rufe = [k for k in ast.walk(m) if isinstance(k, ast.Call)
                    and getattr(k.func, "attr", "") == "_finalize_staged_pack_output"]
            if not rufe:
                continue
            mit += len(rufe)
            pruefungen = [k for k in ast.walk(m) if isinstance(k, ast.Call)
                          and getattr(k.func, "attr", "") == "_ergebnis_im_ziel"]
            if len(pruefungen) < len(rufe):
                ohne.append(m.name)
        self.assertGreaterEqual(mit, 4, "Weniger Packwege als erwartet - "
                                        "der Test misst sonst nichts.")
        self.assertEqual(ohne, [], "Diese Wege melden Erfolg, ohne zu pruefen, "
                                   "ob das Ergebnis am Ziel liegt.")

    @unittest.skipUnless(os.name == "nt", "Staging greift nur bei verschiedenen Laufwerksbuchstaben")
    def test_gleichnamige_datei_im_arbeitsordner_bleibt(self) -> None:
        arbeit = os.path.join(self.basis, "arbeit")
        fremd = _schreiben(os.path.join(arbeit, "Spiel.ffpfsc"), b"meins")
        laufwerk = os.path.splitdrive(arbeit)[0].upper()
        anderes = "Q:" if laufwerk != "Q:" else "R:"
        einstellungen = {"temp_dir": arbeit}
        with mock.patch.object(self.app, "_load_setting",
                               lambda k, d=None: einstellungen.get(k, d)), \
                mock.patch.object(self.app, "task_total_source_bytes", 0, create=True):
            gestagt = self.app._decide_pack_output_staging(anderes + "\\Ziel\\Spiel.ffpfsc")
        stufe = os.path.dirname(gestagt)
        self.addCleanup(self.app._forget_exit_cleanup_path, stufe)
        self.assertTrue(os.path.basename(stufe).lower().startswith("ps5conv_stage_"),
                        "Die Zwischendatei liegt nicht in einem eigenen Staging-Ordner.")
        with open(fremd, "rb") as fh:
            self.assertEqual(fh.read(), b"meins",
                             "Eine Datei des Anwenders im Arbeitsordner wurde geloescht.")


class BlockkopieTests(_TempTest):
    """Grosse Einzeldateien: Meldung und Abbruch mitten in der Datei.

    ``shutil.copy2`` kopierte am Stueck - 120 s Stillstand, ein Stapelabzug als
    ERROR im Protokoll, und abbrechen ging bis zum Dateiende nicht.
    """

    def setUp(self) -> None:
        super().setUp()
        self.quelle = _schreiben(os.path.join(self.basis, "gross.bin"),
                                 os.urandom(10_000))
        self.ziel = os.path.join(self.basis, "kopie.bin")
        patcher = mock.patch.object(APP, "_KOPIE_BLOCK", 1024)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_kopie_ist_bytegleich_und_meldet_jeden_block(self) -> None:
        gemeldet: list = []
        APP._datei_blockweise_kopieren(self.quelle, self.ziel, gemeldet.append, lambda: True)
        with open(self.quelle, "rb") as a, open(self.ziel, "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual(sum(gemeldet), 10_000)
        self.assertGreaterEqual(len(gemeldet), 10, "Nicht blockweise gemeldet.")

    def test_abbruch_mitten_in_der_datei_hinterlaesst_nichts(self) -> None:
        stand = {"bloecke": 0}

        def _melden(_n: int) -> None:
            stand["bloecke"] += 1

        with self.assertRaises(APP._KopieAbgebrochen):
            APP._datei_blockweise_kopieren(self.quelle, self.ziel, _melden,
                                           lambda: stand["bloecke"] < 3)
        self.assertEqual(stand["bloecke"], 3, "Der Abbruch griff nicht zwischen den Bloecken.")
        self.assertFalse(os.path.exists(self.ziel),
                         "Eine halbe Kopie blieb liegen - sie saehe aus wie eine ganze.")

    def test_schreibfehler_hinterlaesst_nichts(self) -> None:
        def _platzt(_n: int) -> None:
            raise OSError(28, "Kein Platz")

        with self.assertRaises(OSError):
            APP._datei_blockweise_kopieren(self.quelle, self.ziel, _platzt, lambda: True)
        self.assertFalse(os.path.exists(self.ziel))


class ExfatDateizahlTests(_TempTest):
    """Die Vollstaendigkeitspruefung zaehlte, was der Writer bewusst weglaesst.

    Eine einzige ``desktop.ini`` im Dump ergab "nur N von N+1 Dateien", und das
    fertige, korrekte .exfat wurde geloescht.
    """

    def test_systemdateien_zaehlen_nicht(self) -> None:
        from mkpfs.utils import is_ignored_name  # noqa: F401  (muss importierbar sein)

        dump = os.path.join(self.basis, "PPSA00000")
        _schreiben(os.path.join(dump, "eboot.bin"))
        _schreiben(os.path.join(dump, "sce_sys", "param.json"))
        _schreiben(os.path.join(dump, "desktop.ini"))
        _schreiben(os.path.join(dump, "sce_sys", "Thumbs.db"))
        _schreiben(os.path.join(dump, "._eboot.bin"))
        _schreiben(os.path.join(dump, "__MACOSX", "versteckt.bin"))
        self.assertEqual(GUI._exfat_erwartete_dateizahl(dump), 2)


class AbgeschnitteneAbbilderTests(unittest.TestCase):
    """Aufgabe 8 hielt abgeschnittene Abbilder fuer bestanden.

    Kopf und Verzeichnisse liegen am Anfang, es fehlen nur Bloecke am Ende -
    der Volllesedurchgang endet ohne Lesefehler. Gemessen am 17.09.2026: auf
    1 MB gekuerzte .ffpfs/.ffpfsc "WARNING" (nur wegen einer Empfehlungsdatei),
    .exfat "OK".
    """

    @classmethod
    def setUpClass(cls) -> None:
        import subprocess

        from mkpfs.exfat_writer import write_exfat_image

        cls.arbeit = tempfile.mkdtemp(prefix="dbg_befund_abbild_")
        dump = os.path.join(cls.arbeit, "PPSA99999")
        _schreiben(os.path.join(dump, "eboot.bin"), os.urandom(300_000))
        _schreiben(os.path.join(dump, "sce_sys", "param.json"),
                   b'{"titleId":"PPSA99999"}')
        _schreiben(os.path.join(dump, "daten", "gross.bin"), os.urandom(400_000))
        cls.exfat = os.path.join(cls.arbeit, "Spiel.exfat")
        write_exfat_image(Path(dump), Path(cls.exfat))
        cls.ffpfs = os.path.join(cls.arbeit, "Spiel.ffpfs")
        lauf = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "folder", "--raw",
             "--no-compress", "--no-adjust-output-file-extension",
             "--version", "PS5", "--inode-bits", "32",
             "--block-size", "65536", dump, cls.ffpfs],
            capture_output=True, cwd=str(PROJEKT / "MkPFS-1.0.0"), timeout=180)
        cls.baufehler = lauf.stderr.decode("utf-8", "replace") if lauf.returncode else ""

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.arbeit, ignore_errors=True)

    def _kopie(self, quelle: str, laenge: int | None = None, name: str = "") -> str:
        ziel = os.path.join(self.arbeit, name or ("kurz_" + os.path.basename(quelle)))
        with open(quelle, "rb") as a, open(ziel, "wb") as b:
            b.write(a.read() if laenge is None else a.read(laenge))
        self.addCleanup(lambda: os.path.exists(ziel) and os.remove(ziel))
        return ziel

    def _pruefen(self, pfad: str, **kw):
        from ps5_validator.modules.extfat_validator import ExtfatValidator
        from ps5_validator.modules.ffpfs_validator import FfpfsValidator

        art = ExtfatValidator if pfad.endswith(".exfat") else FfpfsValidator
        return art(**kw).validate(pfad)

    def test_unversehrt_ist_nicht_beschaedigt(self) -> None:
        if self.baufehler:
            self.skipTest("mkpfs konnte nichts bauen: %s" % self.baufehler[:200])
        for pfad in (self.exfat, self.ffpfs):
            with self.subTest(abbild=os.path.basename(pfad)):
                ergebnis = self._pruefen(pfad)
                self.assertNotIn(ergebnis.status, ("CORRUPTED", "FAILED"), ergebnis.errors)

    def test_gekuerzt_ist_beschaedigt(self) -> None:
        if self.baufehler:
            self.skipTest("mkpfs konnte nichts bauen: %s" % self.baufehler[:200])
        for pfad in (self.exfat, self.ffpfs):
            groesse = os.path.getsize(pfad)
            for laenge in (groesse - 65536, groesse // 2, 200_000):
                with self.subTest(abbild=os.path.basename(pfad), laenge=laenge):
                    ergebnis = self._pruefen(self._kopie(pfad, laenge))
                    self.assertEqual(ergebnis.status, "CORRUPTED", ergebnis.errors)
                    self.assertIn("abgeschnitten", " ".join(ergebnis.errors))

    def test_ungueltige_boot_signatur_bleibt_eine_warnung(self) -> None:
        """Bis v1.9.24 setzte das Ende der Pruefung den Stand wieder auf OK."""
        kopie = self._kopie(self.exfat, name="signatur.exfat")
        with open(kopie, "r+b") as fh:
            fh.seek(510)
            fh.write(b"\x00\x00")
        ergebnis = self._pruefen(kopie)
        self.assertEqual(ergebnis.status, "WARNING", ergebnis.errors)

    def test_abbruch_liest_nicht_zu_ende(self) -> None:
        if self.baufehler:
            self.skipTest("mkpfs konnte nichts bauen: %s" % self.baufehler[:200])
        for pfad in (self.exfat, self.ffpfs):
            with self.subTest(abbild=os.path.basename(pfad)):
                gelesen: list = []
                ergebnis = self._pruefen(
                    pfad, cancel_flag=lambda: True,
                    progress_cb=lambda d, t, _n, _g=gelesen: _g.append(d))
                self.assertEqual(ergebnis.status, "SKIPPED", ergebnis.errors)
                self.assertEqual(gelesen, [], "Trotz Abbruch wurde weitergelesen.")

    def test_hashstrom_fragt_den_abbruch_je_block(self) -> None:
        import io as _io

        from ps5_validator.utils import hashing

        daten = _io.BytesIO(b"x" * (hashing.CHUNK_SIZE * 2 + 5))
        fragen = {"n": 0}

        def _nach_einem_block() -> bool:
            fragen["n"] += 1
            return fragen["n"] > 1

        hashing.sha256_stream(daten, total_size=0, cancel_cb=_nach_einem_block)
        self.assertEqual(daten.tell(), hashing.CHUNK_SIZE)


# ---------------------------------------------------------------------------
# Kaputte Funktionen
# ---------------------------------------------------------------------------

class SammelquellenTests(_TempTest):
    """Aufgabe 5 mit einem Ordner voller Abbilder.

    ``_SAMMEL_ENDUNGEN`` war nirgends definiert (AttributeError bei jedem Ordner
    mit Dateien), und ein einzeln gewaehlter Ordner ergab eine leere Liste.
    """

    def test_ordner_wird_zu_seinen_abbildern(self) -> None:
        _schreiben(os.path.join(self.basis, "a.ffpfsc"))
        _schreiben(os.path.join(self.basis, "b.exfat"))
        _schreiben(os.path.join(self.basis, "notiz.txt"))
        _schreiben(os.path.join(self.basis, "dump1", "eboot.bin"))
        os.makedirs(os.path.join(self.basis, "leer"))
        liste = GUI._sammelquellen_aufloesen(
            [self.basis, os.path.join(self.basis, "a.ffpfsc")])
        namen = [os.path.basename(p) for p in liste]
        self.assertEqual(namen, ["a.ffpfsc", "b.exfat", "dump1"])

    def test_dump_ordner_steht_fuer_sich(self) -> None:
        dump = os.path.join(self.basis, "PPSA00000")
        _schreiben(os.path.join(dump, "sce_sys", "param.json"))
        _schreiben(os.path.join(dump, "innen.ffpfsc"))
        self.assertEqual(GUI._sammelquellen_aufloesen([dump]), [os.path.normpath(dump)])

    def test_endungen_decken_die_sammelformate(self) -> None:
        self.assertEqual(set(GUI._SAMMEL_ENDUNGEN),
                         {".ffpfsc", ".ffpfs", ".exfat", ".ffpkg"})

    def test_jede_datei_bekommt_ihren_einbau(self) -> None:
        """Der Merker _integration_erledigt wird je Datei zurueckgesetzt."""
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        methode = _methode(_klasse(baum), "_run_flexible_conversion")
        treffer = [
            z for schleife in ast.walk(methode) if isinstance(schleife, ast.For)
            for z in ast.walk(schleife)
            if isinstance(z, ast.Assign)
            and any(isinstance(t, ast.Attribute) and t.attr == "_integration_erledigt"
                    for t in z.targets)
            and isinstance(z.value, ast.Constant) and z.value.value is False]
        self.assertTrue(treffer,
                        "In der Sammelschleife wird _integration_erledigt nicht "
                        "zurueckgesetzt - ab Datei 2 kaeme kein AMPR/BACKPORT mehr.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class FormatwegeTests(unittest.TestCase):
    """Wege, die die Oberflaeche anbot, die sich aber nie starten liessen."""

    def setUp(self) -> None:
        self.app = _app()

    def test_ffpfsc_zu_ffpfsc_mit_assetpack_ist_frei(self) -> None:
        with mock.patch.object(self.app, "_selbstziel_erlaubt", lambda: True):
            self.assertEqual(self.app._conversion_block_reason(
                "ffpfsc", "ffpfsc", mode="unpack_to_exfat"), "")
        with mock.patch.object(self.app, "_selbstziel_erlaubt", lambda: False):
            self.assertNotEqual(self.app._conversion_block_reason(
                "ffpfsc", "ffpfsc", mode="unpack_to_exfat"), "",
                "Gegenprobe: ohne Asset-Pack muss der Weg gesperrt bleiben.")

    def test_im_faden_entscheidet_der_startstand(self) -> None:
        def _verboten() -> bool:
            raise AssertionError("Tk-Auswahl im Aufgabenfaden gelesen")

        ergebnis: list = []
        with mock.patch.object(self.app, "_assetpack_gewaehlt", _verboten), \
                mock.patch.object(self.app, "_umhuellt_neu_packen", True, create=True):
            faden = threading.Thread(
                target=lambda: ergebnis.append(self.app._selbstziel_erlaubt()))
            faden.start()
            faden.join(10)
        self.assertEqual(ergebnis, [True])

    def test_aufgaben_ohne_zielformat_fragen_nie_nach_dem_umhuellen(self) -> None:
        """Aufgabe 8 fragte bei gesetztem AMPR-Haken "neu packen?".

        Die Quelle muss es wirklich geben: Fuer eine fehlende Datei erkennt das
        Programm keinen Quelltyp und fragt ohnehin nie - die erste Fassung
        dieses Tests blieb deshalb auch gegen den alten Fehler gruen.
        """
        gefragt: list = []
        ordner = tempfile.mkdtemp(prefix="dbg_befund_")
        self.addCleanup(shutil.rmtree, ordner, True)
        quelle = _schreiben(os.path.join(ordner, "Spiel.ffpkg"), bytes(70_000))
        self.assertEqual(self.app._detect_source_type(quelle), "ffpkg",
                         "Die Quelle wird nicht als .ffpkg erkannt - der Test "
                         "maesse sonst nichts.")
        with mock.patch.object(self.app, "_integration_gewaehlt", lambda: True), \
                mock.patch.object(self.app, "_ask_yesno_threadsafe",
                                  lambda *a, **k: gefragt.append(a) or False), \
                mock.patch.object(APP.messagebox, "askyesno",
                                  lambda *a, **k: gefragt.append(a) or False):
            for aufgabe in ("dump_validator", "ampr_manager"):
                with self.subTest(aufgabe=aufgabe):
                    self.assertTrue(self.app._umhuellenden_weg_klaeren(
                        aufgabe, quelle, "ffpfsc"))
        self.assertEqual(gefragt, [])

    def test_sprachwechsel_behaelt_das_zielformat(self) -> None:
        """Aus ".ffpfs (unkomprimiert)" wurde beim Umschalten still ".ffpfsc"."""
        app = self.app
        vorher_modus = app.current_mode.get()
        vorher_format = app.target_format.get()
        sprache = app._current_language

        def _zurueck() -> None:
            if app._current_language != sprache:
                app._toggle_language()
            app._set_mode_from_sidebar(vorher_modus)
            app.target_format.set(vorher_format)

        self.addCleanup(_zurueck)
        app._set_mode_from_sidebar("pack_folder")
        optionen = GUI._MODE_TARGET_OPTIONS["pack_folder"]
        schluessel = optionen[1]                     # bewusst nicht der erste
        app.target_format.set(app._zielformat_label(schluessel, "pack_folder"))
        self.assertEqual(app._get_selected_target_type(), schluessel)
        for _ in range(2):
            app._toggle_language()
            _WURZEL.update_idletasks()
            self.assertEqual(app._get_selected_target_type(), schluessel,
                             "Nach dem Sprachwechsel steht ein anderes Zielformat da.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class AmprVersorgungTests(_TempTest):
    """Eine gewaehlte AMPR-Fassung wurde beim Bauen still ersetzt.

    Fehlte nur PlayGo, legte der Versionsspeicher die NEUESTE AMPR-Fassung ueber
    die gewaehlte und PlayGo dazu - PlayGo kommt nie von selbst.
    """

    def test_vorhandene_bibliothek_bleibt_und_playgo_kommt_nicht(self) -> None:
        app = _app()
        dump = os.path.join(self.basis, "PPSA00000")
        _schreiben(os.path.join(dump, "eboot.bin"))
        fakelib = Path(app._fakelib_pfad(dump))
        ampr = _schreiben(str(fakelib / GUI._AMPR_SPRX_NAME), b"gewaehlte Fassung")
        protokoll: list = []
        with mock.patch.object(app, "_append_to_log", protokoll.append), \
                mock.patch.object(app, "_ampr_aus_speicher_versorgen",
                                  side_effect=AssertionError("Speicher angefasst")):
            ok = app._prepare_ampr_support(dump, {"is_apr": True,
                                                  "ampr_rebuild_index": False})
        self.assertTrue(ok)
        with open(ampr, "rb") as fh:
            self.assertEqual(fh.read(), b"gewaehlte Fassung")
        self.assertFalse((fakelib / GUI._PLAYGO_SPRX_NAME).exists(),
                         "PlayGo wurde ungefragt dazugelegt.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ZweiterStartTests(unittest.TestCase):
    """STARTEN waehrend ein abgebrochener Faden noch arbeitet.

    Der alte Faden ueberschrieb den Fortschritt des neuen, raeumte dessen
    Arbeitsordner ab und setzte im finally ``is_running = False``.
    """

    def test_laufender_faden_verhindert_den_start(self) -> None:
        app = _app()
        halt = threading.Event()
        alt = threading.Thread(target=halt.wait, daemon=True)
        alt.start()
        vorher = app._task_thread
        gemeldet: list = []
        try:
            app._task_thread = alt
            with mock.patch.object(APP.messagebox, "showinfo",
                                   lambda *a, **k: gemeldet.append(a)), \
                    mock.patch.object(APP.messagebox, "showerror",
                                      side_effect=AssertionError("Validierung erreicht")):
                app._launch_task()
            self.assertIs(app._task_thread, alt, "Ein zweiter Faden wurde gestartet.")
            self.assertEqual(len(gemeldet), 1, "Keine Meldung, warum nichts passiert.")
        finally:
            halt.set()
            alt.join(5)
            app._task_thread = vorher


# ---------------------------------------------------------------------------
# Faden und Oberflaeche
# ---------------------------------------------------------------------------

class _NurHauptfaden:
    """Eine Tk-Variable, die aus einem Faden gelesen einen Fehler meldet."""

    def __init__(self, wert) -> None:
        self.wert = wert

    def get(self):
        if threading.current_thread() is not threading.main_thread():
            raise AssertionError("Tk-Variable im Aufgabenfaden gelesen")
        return self.wert


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class StartstandImFadenTests(unittest.TestCase):
    """Der Faden liest den Startstand, nicht die Felder.

    Wer waehrend Aufgabe 2 den AMPR-Haken fuer den naechsten Lauf umlegte,
    veraenderte den laufenden: Der Container entstand ohne AMPR und galt als
    Erfolg. Ausserdem wirft Tk ohne laufende Ereignisschleife im Faden.
    """

    def _im_faden(self, aufruf):
        ergebnis: list = []
        fehler: list = []

        def _lauf() -> None:
            try:
                ergebnis.append(aufruf())
            except BaseException as exc:          # noqa: BLE001
                fehler.append(exc)

        faden = threading.Thread(target=_lauf)
        faden.start()
        faden.join(10)
        if fehler:
            raise fehler[0]
        return ergebnis[0]

    def test_einbau_und_worker_aus_dem_startstand(self) -> None:
        app = _app()
        with mock.patch.object(app, "ampr_integrate_var", _NurHauptfaden(True)), \
                mock.patch.object(app, "backport_integrate_var", _NurHauptfaden(False)), \
                mock.patch.object(app, "worker_count_var", _NurHauptfaden(3)):
            app._lauf_variablen_festhalten()
            self.addCleanup(setattr, app, "_lauf_variablen", None)
            # Nach dem Start umgestellt - der Lauf behaelt seinen Stand.
            app.ampr_integrate_var.wert = False
            self.assertTrue(self._im_faden(app._integration_gewaehlt))
            self.assertEqual(self._im_faden(lambda: app._tk_wert("worker_count_var", 0)), 3)

    def test_worker_zahl_im_faden_aus_der_einstellung(self) -> None:
        app = _app()
        with mock.patch.object(app, "worker_count_var", _NurHauptfaden(2)), \
                mock.patch.object(app, "_load_setting",
                                  lambda k, d=None: 5 if k == "worker_count" else d):
            erwartet = max(1, min(app._worker_obergrenze(), 5))
            self.assertEqual(self._im_faden(lambda: app._get_worker_count(1)), erwartet)

    def test_zielformat_im_faden_aus_dem_startstand(self) -> None:
        app = _app()
        with mock.patch.object(app, "target_format", _NurHauptfaden(".exfat")), \
                mock.patch.object(app, "_lauf_zielformat", "ffpfs", create=True):
            self.assertEqual(self._im_faden(app._get_selected_target_type), "ffpfs")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class EscapeTests(unittest.TestCase):
    """Esc aus einem anderen Fenster brach die laufende Aufgabe ab."""

    def setUp(self) -> None:
        self.app = _app()
        self.abgebrochen: list = []
        for ziel, wert in (("_kill_task", lambda: self.abgebrochen.append(True)),
                           ("abort_btn", {"state": tk.NORMAL})):
            patcher = mock.patch.object(self.app, ziel, wert)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _esc(self, widget) -> None:
        self.app._on_shortcut_escape(mock.Mock(widget=widget))

    def test_anderes_fenster_bricht_nicht_ab(self) -> None:
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.addCleanup(fenster.destroy)
        self._esc(tk.Frame(fenster))
        self.assertEqual(self.abgebrochen, [])

    def test_menue_bricht_nicht_ab(self) -> None:
        menue = tk.Menu(_WURZEL, tearoff=0)
        self.addCleanup(menue.destroy)
        self._esc(menue)
        self.assertEqual(self.abgebrochen, [])

    def test_hauptfenster_bricht_ab(self) -> None:
        """Gegenprobe: Esc im Hauptfenster wirkt weiter."""
        rahmen = tk.Frame(_WURZEL)
        self.addCleanup(rahmen.destroy)
        self._esc(rahmen)
        self.assertEqual(self.abgebrochen, [True])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ProtokollschwanzEinmalTests(unittest.TestCase):
    """Mehrzeilige Meldungen standen im Diagnosebericht doppelt."""

    def test_mehrzeilige_meldung_landet_einmal_im_puffer(self) -> None:
        app = _app()
        app._build_log_tail = []
        app._append_to_log("Befundzeile A 4711\nBefundzeile B 4711\n")
        _WURZEL.update()
        schwanz = list(app._build_log_tail)
        self.assertEqual(schwanz.count("Befundzeile A 4711"), 1, schwanz)
        self.assertEqual(schwanz.count("Befundzeile B 4711"), 1, schwanz)

    def test_einzeilige_meldung_landet_weiter_im_puffer(self) -> None:
        app = _app()
        app._build_log_tail = []
        app._append_to_log("Einzelzeile 4712\n")
        _WURZEL.update()
        self.assertEqual(list(app._build_log_tail).count("Einzelzeile 4712"), 1)


# ---------------------------------------------------------------------------
# Kommandozeile ohne Dialoge
# ---------------------------------------------------------------------------

@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class KommandozeileOhneDialogTests(_TempTest):
    """Im CLI gibt es niemanden, der eine Rueckfrage beantwortet."""

    def setUp(self) -> None:
        super().setUp()
        self.app = _app()
        vorher = getattr(self.app, "_cli_mode", False)
        self.addCleanup(setattr, self.app, "_cli_mode", vorher)
        self.app._cli_mode = True
        self.dialoge: list = []
        for name in ("askyesno", "showinfo", "showwarning", "showerror"):
            patcher = mock.patch.object(APP.messagebox, name,
                                        lambda *a, _n=name, **k: self.dialoge.append(_n))
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(self.app, "_ask_yesno_threadsafe",
                                    lambda *a, **k: self.dialoge.append("threadsafe") or False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ftpsrv_wird_ohne_frage_nicht_gesendet(self) -> None:
        vorher = getattr(self.app, "_ftpsrv_declined", False)
        self.addCleanup(setattr, self.app, "_ftpsrv_declined", vorher)
        self.app._ftpsrv_declined = False
        with mock.patch.object(self.app, "_ps5_port_open", lambda *a, **k: False), \
                mock.patch.object(self.app, "_append_to_log", lambda *a: None):
            self.assertEqual(self.app._ensure_ftpsrv("192.0.2.1"), 0)
        self.assertEqual(self.dialoge, [])

    def test_einbau_arbeitet_nie_im_original(self) -> None:
        """Ohne --yes baute ein vorsichtiger Lauf direkt in den Original-Dump."""
        rufe = [k for k in ast.walk(_methode(_klasse(ast.parse(
                    HAUPTDATEI.read_text(encoding="utf-8"))), "_integration_arbeitskopie"))
                if isinstance(k, ast.If)
                and "_cli_mode" in ast.dump(k.test)]
        self.assertTrue(rufe, "_integration_arbeitskopie unterscheidet das CLI nicht mehr.")
        zweig = rufe[0].body
        antwort_ja = any(isinstance(z, ast.Assign) and isinstance(z.value, ast.Constant)
                         and z.value.value is True for z in zweig)
        self.assertTrue(antwort_ja, "Im CLI-Zweig wird die Arbeitskopie nicht fest gewaehlt.")


# ---------------------------------------------------------------------------
# FTP
# ---------------------------------------------------------------------------

class _FtpAttrappe:
    def __init__(self, groesse, liste) -> None:
        self.groesse = groesse
        self.liste = liste
        self.befehle: list = []

    def voidcmd(self, befehl: str) -> str:
        self.befehle.append(befehl)
        return "200 OK"

    def size(self, pfad: str):
        self.befehle.append("SIZE " + pfad)
        if isinstance(self.groesse, BaseException):
            raise self.groesse
        return self.groesse

    def nlst(self, ordner: str):
        self.befehle.append("NLST " + ordner)
        if isinstance(self.liste, BaseException):
            raise self.liste
        return list(self.liste)


class FtpDateiVorhandenTests(unittest.TestCase):
    """Zwei Fassungen desselben Namens - die spaetere ueberdeckte die fruehere.

    Die Bibliothek fragte vor dem Ueberschreiben ueber eine eigene Fassung,
    die gar nicht lief. Jetzt eine: Binaermodus, SIZE, Ordnerliste als
    Rueckfall; Verbindungsfehler gehen an den Aufrufer.
    """

    PFAD = "/mnt/usb0/ps5_autoloader/autoload.txt"

    def _frage(self, groesse, liste):
        ftp = _FtpAttrappe(groesse, liste)
        return GUI._ftp_datei_vorhanden(None, ftp, self.PFAD), ftp

    def test_size_antwortet(self) -> None:
        ergebnis, ftp = self._frage(123, ftplib.error_perm("550"))
        self.assertTrue(ergebnis)
        self.assertEqual(ftp.befehle[0], "TYPE I", "SIZE ohne Binaermodus gefragt.")

    def test_size_abgelehnt_aber_in_der_liste(self) -> None:
        for eintrag in ("autoload.txt", self.PFAD):
            with self.subTest(eintrag=eintrag):
                ergebnis, _ = self._frage(ftplib.error_perm("550 SIZE not allowed"),
                                          ["andere.elf", eintrag])
                self.assertTrue(ergebnis)

    def test_gibt_es_nicht(self) -> None:
        self.assertFalse(self._frage(ftplib.error_perm("550"), ["andere.elf"])[0])
        self.assertFalse(self._frage(ftplib.error_perm("550"), ftplib.error_perm("550"))[0])

    def test_verbindungsfehler_ist_kein_nein(self) -> None:
        with self.assertRaises(EOFError):
            self._frage(EOFError(), ["autoload.txt"])


class DoppelteMethodenTests(unittest.TestCase):
    """Keine Klasse definiert eine Methode zweimal.

    Die spaetere Definition gewinnt still. ruff/pyflakes (F811) uebergehen
    den Fall, sobald eine der beiden einen Dekorator traegt - so geschehen am
    16.09.2026 mit ``@staticmethod _ftp_datei_vorhanden``.
    """

    @staticmethod
    def _zugriffsmethode(fn) -> bool:
        for d in fn.decorator_list:
            if isinstance(d, ast.Attribute) and d.attr in ("setter", "getter", "deleter",
                                                           "overload"):
                return True
            if isinstance(d, ast.Name) and d.id == "overload":
                return True
        return False

    def test_keine_doppelten_methoden(self) -> None:
        dateien = [HAUPTDATEI]
        for wurzel, ordner, namen in os.walk(PROJEKT / "ps5_validator"):
            ordner[:] = [o for o in ordner if o not in ("vendor", "__pycache__")]
            dateien += [Path(wurzel) / n for n in namen if n.endswith(".py")]
        self.assertGreater(len(dateien), 20, "Kaum Dateien gefunden - der Test misst nichts.")
        doppelt = []
        klassen = 0
        for datei in dateien:
            baum = ast.parse(datei.read_bytes().decode("utf-8"))
            for klasse in ast.walk(baum):
                if not isinstance(klasse, ast.ClassDef):
                    continue
                klassen += 1
                gesehen: dict = {}
                for m in klasse.body:
                    if not isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if self._zugriffsmethode(m):
                        continue
                    if m.name in gesehen:
                        doppelt.append("%s: %s.%s (Zeilen %d und %d)" % (
                            datei.name, klasse.name, m.name, gesehen[m.name], m.lineno))
                    gesehen.setdefault(m.name, m.lineno)
        self.assertGreater(klassen, 50)
        self.assertEqual(doppelt, [], "\n".join(doppelt))


# ---------------------------------------------------------------------------
# Kleinere Befunde
# ---------------------------------------------------------------------------

class KleinereBefundeTests(_TempTest):

    def test_ftp_zeitstempel_ist_utc_sekunden(self) -> None:
        """Bis v1.9.24 kam die Ziffernfolge selbst heraus (ein Jahr um 640 000)."""
        erwartet = calendar.timegm((2026, 9, 16, 12, 34, 56, 0, 0, 0))
        self.assertEqual(GUI._ampr_ftp_modify_to_int("20260916123456"), erwartet)
        self.assertEqual(GUI._ampr_ftp_modify_to_int("20260916123456.789"), erwartet)
        self.assertEqual(GUI._ampr_ftp_modify_to_int("kaputt"), 0)

    def test_derselbe_datentraeger_auch_fuer_noch_fehlende_ordner(self) -> None:
        """Unter Linux/macOS galten zwei Pfade immer als derselbe Datentraeger."""
        neu = os.path.join(self.basis, "gibt", "es", "noch", "nicht")
        self.assertEqual(os.path.normcase(GUI._naechster_vorhandener_ordner(neu)),
                         os.path.normcase(os.path.abspath(self.basis)))
        self.assertTrue(GUI._selber_datentraeger(self.basis, neu))

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_gemerkte_groesse_gilt_nur_fuer_ihre_quelle(self) -> None:
        app = _app()
        vorher = (getattr(app, "_quellgroesse_gemerkt", None),
                  getattr(app, "_last_source_size_bytes", 0))

        def _zurueck() -> None:
            app._quellgroesse_gemerkt, app._last_source_size_bytes = vorher

        self.addCleanup(_zurueck)
        a = os.path.join(self.basis, "SpielA")
        b = os.path.join(self.basis, "SpielB")
        app._quellgroesse_merken(a, 5_000)
        self.assertEqual(app._bekannte_quellgroesse(a), 5_000)
        self.assertEqual(app._bekannte_quellgroesse(b), 0,
                         "Die Platzpruefung rechnete mit der Groesse der vorigen Quelle.")

    def test_param_json_ordnername_ist_eine_warnung(self) -> None:
        """Als Fehler stiess der Befund eine Reparatur an, die ihn nie beheben
        konnte - am Ende wurde angeboten, die ganze param.json zu ersetzen."""
        from ps5_validator.utils import param_check

        daten = {"titleId": "PPSA01234",
                 "contentId": "UP0000-PPSA01234_00-0000000000000000"}
        pfad = os.path.join(self.basis, "PPSA09999", "sce_sys", "param.json")
        befund = param_check.pruefe_daten(daten, pfad)
        self.assertFalse(any("Ordnername" in f for f in befund.fehler), befund.fehler)
        self.assertTrue(any("Ordnername" in w for w in befund.warnungen), befund.warnungen)

    def test_param_json_reparatur_nimmt_die_inhaltsversion(self) -> None:
        from ps5_validator.utils import param_check

        neu, _aenderungen = param_check.repariere({"titleId": "PPSA01234"},
                                                  inhaltsversion="01.003.000")
        self.assertEqual(neu.get("contentVersion"), "01.003.000")

    def test_diagnose_nennt_nur_vorhandene_dateien(self) -> None:
        """Abgeschriebene Befehle muessen stimmen ("bisect_prüfung.ps1")."""
        quelle = (PROJEKT / "ps5_validator" / "utils" / "diagnose_befund.py").read_text(
            encoding="utf-8")
        texte = [k.value for k in ast.walk(ast.parse(quelle))
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        muster = re.compile(r"((?:tools[\\/])?[\w.-]+\.(?:ps1|py|sh))\b")
        genannt = {m.group(1).replace("\\", "/") for t in texte
                   for m in muster.finditer(t)
                   if m.group(1).startswith(("tools", "test_"))}
        self.assertGreaterEqual(len(genannt), 3, "Keine Dateinamen gefunden - "
                                                 "der Test misst nichts.")
        fehlend = sorted(n for n in genannt if not (PROJEKT / n).exists())
        self.assertEqual(fehlend, [], "Die Diagnose nennt Dateien, die es nicht gibt.")


# ---------------------------------------------------------------------------
# Zweiter Block (17.09.2026): Faeden, Werkzeugfenster, Vorschau
# ---------------------------------------------------------------------------

def _faden_befunde(quelle: str) -> list:
    """Tk-Zugriffe und after()-Rueckmeldungen aus Arbeitsfaeden - ueber den Baum.

    Fadenziele sind innere Funktionen, die ``threading.Thread(target=<name>)``
    bekommen, samt der inneren Funktionen, die sie per Namen rufen (jeweils
    nach Geltungsbereich aufgeloest - gleichnamige ``worker`` in einer Methode
    sind verschiedene Funktionen). Gemeldet wird:

    * ``tk``: Methodenaufruf auf einem lokalen Tk-Objekt der Methode
      (Zuweisung aus tk.*/ttk.* oder _build_modern_toplevel),
    * ``after``: ``<fenster>.after(...)``/``self.root.after(...)`` - ein
      Rueckruf in ein Fenster, das inzwischen zu sein kann.

    Was in lambda-Ausdruecken oder als Argument von _spaeter_im_fenster/after
    steht, laeuft im Hauptfaden und zaehlt nicht.
    """
    baum = ast.parse(quelle)
    eltern = {}
    for knoten in ast.walk(baum):
        for kind in ast.iter_child_nodes(knoten):
            eltern[kind] = knoten

    def umschliessend(knoten):
        k = eltern.get(knoten)
        while k is not None and not isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
            k = eltern.get(k)
        return k

    def lokale_defs(funktion):
        gefunden, stapel = {}, list(funktion.body)
        while stapel:
            k = stapel.pop()
            if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)):
                gefunden[k.name] = k
                continue
            if isinstance(k, (ast.ClassDef, ast.Lambda)):
                continue
            stapel.extend(ast.iter_child_nodes(k))
        return gefunden

    def aufloesen(name, ab):
        f = ab
        while f is not None:
            defs = lokale_defs(f)
            if name in defs:
                return defs[name]
            f = umschliessend(f)
        return None

    class _Sammler(ast.NodeVisitor):
        def __init__(self, tk_namen):
            self.tk_namen, self.funde, self.aufrufe = tk_namen, [], []

        def visit_Lambda(self, node):
            return

        def visit_FunctionDef(self, node):
            return

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            f = node.func
            if isinstance(f, ast.Name):
                self.aufrufe.append(f.id)
            if isinstance(f, ast.Attribute):
                basis = f.value
                if f.attr == "after":
                    if isinstance(basis, ast.Name) and basis.id in self.tk_namen:
                        self.funde.append((node.lineno, "after"))
                    elif (isinstance(basis, ast.Attribute) and basis.attr == "root"
                          and isinstance(basis.value, ast.Name) and basis.value.id == "self"):
                        self.funde.append((node.lineno, "after"))
                    return
                if f.attr in ("_spaeter_im_fenster", "_spaeter_nach_ms", "after_idle"):
                    return
                if isinstance(basis, ast.Name) and basis.id in self.tk_namen:
                    self.funde.append((node.lineno, "tk"))
            self.generic_visit(node)

    klasse = _klasse(baum)
    funde = []
    for methode in klasse.body:
        if not isinstance(methode, ast.FunctionDef):
            continue
        tk_namen = set()
        for k in ast.walk(methode):
            if not isinstance(k, ast.Assign):
                continue
            paare = []
            for z in k.targets:
                if isinstance(z, ast.Tuple) and isinstance(k.value, ast.Tuple):
                    paare.extend(zip(z.elts, k.value.elts))
                else:
                    paare.append((z, k.value))
            for ziel, wert in paare:
                if isinstance(ziel, ast.Name) and isinstance(wert, ast.Call):
                    f = wert.func
                    if ((isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name)
                         and f.value.id in ("tk", "ttk"))
                            or (isinstance(f, ast.Attribute)
                                and f.attr == "_build_modern_toplevel")):
                        tk_namen.add(ziel.id)
        if not tk_namen:
            continue
        offen = []
        for k in ast.walk(methode):
            if (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                    and k.func.attr == "Thread"):
                for kw in k.keywords:
                    if kw.arg == "target" and isinstance(kw.value, ast.Name):
                        ziel = aufloesen(kw.value.id, umschliessend(k))
                        if ziel is not None and ziel is not methode:
                            offen.append(ziel)
        gesehen = set()
        while offen:
            fn = offen.pop()
            if id(fn) in gesehen:
                continue
            gesehen.add(id(fn))
            sammler = _Sammler(tk_namen)
            for anweisung in fn.body:
                sammler.visit(anweisung)
            funde.extend((methode.name, fn.name, zeile, art) for zeile, art in sammler.funde)
            for name in sammler.aufrufe:
                ziel = aufloesen(name, fn)
                if ziel is not None and ziel is not methode and id(ziel) not in gesehen:
                    offen.append(ziel)
    return sorted(set(funde), key=lambda f: f[2])


class FadenzugriffTests(unittest.TestCase):
    """Kein Arbeitsfaden fasst Tk an oder meldet per after() in ein Fenster.

    Am 17.09.2026 fand die Pruefung 44 Stellen in zehn Fenstern: PKG bauen,
    PS4-Wandler und Debug-PKG lasen ihre Felder im Faden (ohne laufende
    Ereignisschleife wirft Tk dort, und eine waehrend des Laufs geaenderte
    Auswahl galt fuer den laufenden Lauf); KLOG, INI-Editor, App-Installation,
    Index-Bauer, AMPR-Auswahl und zwei weitere meldeten per after() in
    Fenster, die inzwischen zu sein konnten ("invalid command name" als
    [FEHLER] im Protokoll).
    """

    def test_im_hauptmodul_nichts(self) -> None:
        funde = _faden_befunde(HAUPTDATEI.read_text(encoding="utf-8"))
        self.assertEqual(funde, [], "\n".join(
            "%s / %s Z.%d: %s" % f for f in funde))

    def test_die_pruefung_sieht_beide_arten(self) -> None:
        """Gegenprobe am Kleinen - sonst misst der Test oben vielleicht nichts."""
        probe = (
            "import threading, tkinter as tk\n"
            "class PS5ConverterGUI:\n"
            "    def fenster(self):\n"
            "        win = self._build_modern_toplevel('x', 1, 1)\n"
            "        wert = tk.StringVar()\n"
            "        def worker():\n"
            "            wert.get()\n"
            "            win.after(0, print)\n"
            "            self._spaeter_im_fenster(win, wert.set, 'ok')\n"
            "        def worker2():\n"
            "            self.root.after(0, lambda: wert.get())\n"
            "        threading.Thread(target=worker).start()\n"
            "        threading.Thread(target=worker2).start()\n")
        arten = sorted(f[3] for f in _faden_befunde(probe))
        self.assertEqual(arten, ["after", "after", "tk"])

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_rueckruf_entfaellt_wenn_das_fenster_inzwischen_zu_ist(self) -> None:
        """Eingeplant am Fenster, nicht an der Wurzel.

        Tkinter verwirft am Fenster eingeplante Rueckrufe mit dem Fenster.
        Ueber self.root.after eingeplante liefen weiter und fassten zerstoerte
        Widgets an - genau die Stellen, die der Test oben sucht.
        """
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        gerufen: list = []
        self.assertTrue(GUI._spaeter_im_fenster(fenster, lambda: gerufen.append(1)))
        fenster.destroy()
        _WURZEL.update()
        self.assertEqual(gerufen, [], "Der Rueckruf lief nach dem Schliessen.")

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_offenes_fenster_bekommt_den_rueckruf(self) -> None:
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.addCleanup(fenster.destroy)
        gerufen: list = []
        GUI._spaeter_im_fenster(fenster, gerufen.append, 7)
        _WURZEL.update()
        self.assertEqual(gerufen, [7])


class AutoloaderAenderungenTests(unittest.TestCase):
    """Hochladen, Loeschen, Zurueckspielen verwarfen ungespeicherte Aenderungen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.fenster = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))),
                               "_show_autoloader")

    def _innere(self, name: str) -> ast.FunctionDef:
        return next(k for k in ast.walk(self.fenster)
                    if isinstance(k, ast.FunctionDef) and k.name == name)

    @staticmethod
    def _gerufen(knoten) -> set:
        return {k.func.id for k in ast.walk(knoten)
                if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)}

    def test_eigene_arbeit_laedt_nur_die_liste_nach(self) -> None:
        for name in ("_hochladen", "_loeschen", "_zurueckspielen", "_schreiben"):
            with self.subTest(knopf=name):
                gerufen = self._gerufen(self._innere(name))
                self.assertNotIn("_holen", gerufen,
                                 "%s ersetzt das Feld wieder ungefragt." % name)
                self.assertIn("_nachladen", gerufen)

    def test_holen_fragt_bei_ungespeicherten_aenderungen(self) -> None:
        holen = self._innere("_holen")
        texte = {k.value for k in ast.walk(holen)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        self.assertIn("autoloader.discard_message", texte)
        self.assertIn("_ungespeichert", self._gerufen(holen))

    def test_die_texte_gibt_es_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("autoloader.discard_title", "autoloader.discard_message",
                           "autoloader.state_list_refreshed_kept", "ps4pkg.bad_number"):
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class BibliothekKachelTests(_TempTest):
    """Kacheln: riesig ohne Bild, Klick baute alles neu, PS5-Bilder verschwanden."""

    def setUp(self) -> None:
        super().setUp()
        self.app = _app()
        self.innen = tk.Frame(_WURZEL)
        self.addCleanup(self.innen.destroy)

    def _eintraege(self, anzahl: int = 3) -> list:
        return [{"path": os.path.join(self.basis, "Spiel%d.ffpfsc" % i), "kind": "ffpfsc",
                 "name": "Spiel%d" % i, "meta": {"title": "Spiel %d" % i,
                                                 "title_id": "PPSA0000%d" % i}}
                for i in range(anzahl)]

    def test_kachel_ohne_bild_misst_in_pixeln(self) -> None:
        eintraege = self._eintraege(1)
        self.app._bibliothek_kacheln_setzen(self.innen, eintraege, gewaehlt="",
                                            bei_auswahl=lambda _e: None,
                                            bei_start=lambda _e: None)
        _WURZEL.update_idletasks()
        kante = APP.pt(GUI._KACHEL_BILD_PT)
        feld = eintraege[0]["_bildfeld"]
        self.assertLess(feld.winfo_reqwidth(), kante * 2,
                        "Das Bildfeld misst in Zeichen statt in Pixeln.")
        self.app._bibliothek_bild_setzen(feld, "", kante, getattr(
            self.app, "_bibliothek_generation", 0))
        _WURZEL.update_idletasks()
        self.assertLess(feld.winfo_reqwidth(), kante * 2,
                        "Nach 'kein Titelbild' misst das Feld wieder in Zeichen.")

    def test_markieren_baut_nichts_neu(self) -> None:
        eintraege = self._eintraege(3)
        self.app._bibliothek_kacheln_setzen(self.innen, eintraege, gewaehlt="",
                                            bei_auswahl=lambda _e: None,
                                            bei_start=lambda _e: None)
        vorher = [e["_kachel"] for e in eintraege]
        self.app._bibliothek_kacheln_markieren(eintraege, eintraege[1]["path"])
        self.assertEqual([e["_kachel"] for e in eintraege], vorher)
        self.assertTrue(all(k.winfo_exists() for k in vorher))
        c = self.app._COLORS
        self.assertEqual(str(eintraege[1]["_kachel"].cget("bg")), c["bg_card"])
        self.assertEqual(str(eintraege[0]["_kachel"].cget("bg")), c["console_bg"])

    def test_kachelklick_und_filter_im_fenster(self) -> None:
        fenster = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))),
                           "_render_library_window")
        klick = next(k for k in ast.walk(fenster)
                     if isinstance(k, ast.FunctionDef) and k.name == "_kachel_gewaehlt")
        gerufen = {getattr(k.func, "attr", "") for k in ast.walk(klick)
                   if isinstance(k, ast.Call)}
        self.assertNotIn("_bibliothek_kacheln_setzen", gerufen,
                         "Ein Klick baut wieder alle Kacheln neu.")
        self.assertIn("_bibliothek_kacheln_markieren", gerufen)
        filter_fn = next(k for k in ast.walk(fenster)
                         if isinstance(k, ast.FunctionDef) and k.name == "_apply_filter")
        gerufen = {getattr(k.func, "attr", "") for k in ast.walk(filter_fn)
                   if isinstance(k, ast.Call)}
        self.assertIn("_bibliothek_ps5_bilder_nachladen", gerufen,
                      "Filtern bei Quelle PS5 laedt die Bilder vom PC.")

    def test_ps5_bilder_aus_dem_speicher_ohne_verbindung(self) -> None:
        from ps5_validator.utils import bibliothek

        speicher = bibliothek.Bildspeicher(os.path.join(self.basis, "cover"))
        from PIL import Image
        puffer = __import__("io").BytesIO()
        Image.new("RGB", (8, 8), (200, 0, 0)).save(puffer, "PNG")
        speicher.schreiben("ps5://PPSA00001", puffer.getvalue())
        eintraege = [{"path": "/mnt/usb0/Spiel.ffpfsc", "kind": "ffpfsc",
                      "title_id": "PPSA00001", "meta": {"title": "Spiel"}}]
        self.app._bibliothek_kacheln_setzen(self.innen, eintraege, gewaehlt="",
                                            bei_auswahl=lambda _e: None,
                                            bei_start=lambda _e: None)
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.addCleanup(fenster.destroy)
        vorher_generation = getattr(self.app, "_bibliothek_generation", 0)
        self.addCleanup(setattr, self.app, "_bibliothek_generation", vorher_generation)
        self.app._bibliothek_generation = 4711
        verbunden: list = []
        faeden_vorher = set(threading.enumerate())
        with mock.patch.object(self.app, "_bibliothek_bildspeicher", lambda: speicher), \
                mock.patch.object(self.app, "_ampr_ftp_connect",
                                  lambda *a, **k: verbunden.append(a) or (_ for _ in ()).throw(
                                      OSError("keine Konsole"))):
            self.app._bibliothek_ps5_bilder_nachladen(fenster, eintraege, generation=4711)
            for faden in set(threading.enumerate()) - faeden_vorher:
                faden.join(10)
        self.assertEqual(verbunden, [], "Trotz vollstaendigem Bildspeicher wurde verbunden.")

    def test_bildspeicher_arbeitet_unter_seiner_sperre(self) -> None:
        """Jede oeffentliche Methode haelt die Sperre - ueber den Baum.

        Ein Verhaltenstest mit zwei schreibenden Faeden blieb am 17.09.2026
        auch OHNE Sperre gruen: Das Wettrennen ist echt (zwei Bildlader,
        dieselbe index.json und .tmp-Datei), laesst sich im Test aber nicht
        erzwingen. Ein Test, der nie rot wird, misst nichts.
        """
        quelle = (PROJEKT / "ps5_validator" / "utils" / "bibliothek.py").read_text(
            encoding="utf-8")
        klasse = _klasse(ast.parse(quelle), "Bildspeicher")
        for name in ("lesen", "kennt_ohne_bild", "schreiben", "aufraeumen"):
            with self.subTest(methode=name):
                methode = _methode(klasse, name)
                anweisungen = [a for a in methode.body
                               if not (isinstance(a, ast.Expr)
                                       and isinstance(a.value, ast.Constant))]
                self.assertTrue(
                    len(anweisungen) == 1 and isinstance(anweisungen[0], ast.With)
                    and "_sperre" in ast.dump(anweisungen[0].items[0].context_expr),
                    "%s arbeitet nicht (ganz) unter self._sperre." % name)


class _FortschrittAttrappe:
    def __getattr__(self, _name):
        return lambda *a, **k: None


class FfpkgBauAbbruchTests(_TempTest):
    """Nach "Abbrechen" legte der .ffpkg-Bau die Datei trotzdem ans Ziel."""

    def _bauen(self, abbruch_bei: str):
        """Baut mit Attrappen (wie test_ffpkg_production_integration) und
        setzt ``is_running`` an der genannten Stelle auf False.

        Rechte- und Betriebssystemweiche werden fuer den Lauf gestellt - es
        geht um den Ablauf des Baus, nicht um UFS2Tool.
        """
        import hashlib
        import json
        import queue

        from ps5_validator.utils.param_manifest import create_default_param

        quelle = os.path.join(self.basis, "source")
        _schreiben(os.path.join(quelle, "sce_sys", "param.json"),
                   (json.dumps(create_default_param(title_id="PPSA00001")) + "\n").encode("utf-8"))
        _schreiben(os.path.join(quelle, "payload", "game.bin"), os.urandom(8192))
        ziel = os.path.join(self.basis, "result.ffpkg")
        buehne = os.path.join(self.basis, "temp")
        os.makedirs(buehne)

        gui = GUI.__new__(GUI)
        gui.is_running = True
        gui.task_progress = 0.0
        gui.progress_engine = _FortschrittAttrappe()
        gui.ffpkg_progress_queue = queue.Queue()
        gui._ffpkg_progress_run_id = 0
        gui._extract_ufs2tool = lambda: "UFS2Tool.exe"
        gui._mkdtemp = lambda prefix: tempfile.mkdtemp(prefix=prefix, dir=buehne)
        gui._append_to_log = lambda *_a: None
        gui._verify_ffpkg_file_count_via_mount = lambda *_a, **_k: {"checked": False}

        def _lauf(befehl, **_k):
            with open(befehl[-1] if befehl[1] == "newfs" else befehl[-2], "wb") as fh:
                fh.write(b"candidate" * 1000)
            return 0

        def _abnahme(pfad, **_k):
            if abbruch_bei == "abnahme" or (abbruch_bei == "ziel" and ".transfer-" in pfad):
                gui.is_running = False
            with open(pfad, "rb") as fh:
                return {"ok": True, "sha256": hashlib.sha256(fh.read()).hexdigest()}

        gui._run_subprocess_logged = _lauf
        gui._validate_ffpkg_artifact = _abnahme
        with mock.patch.object(APP, "_is_admin", lambda: True), \
                mock.patch.object(APP, "IST_WINDOWS", True):
            ok = gui._build_ffpkg_from_folder(quelle, ziel, task_index=0, task_label="Abbruch")
        return ok, ziel

    def test_abbruch_in_der_abnahme(self) -> None:
        ok, ziel = self._bauen("abnahme")
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(ziel), "Nach dem Abbruch liegt die Datei am Ziel.")

    def test_abbruch_in_der_zielpruefung(self) -> None:
        ok, ziel = self._bauen("ziel")
        self.assertFalse(ok)
        self.assertFalse(os.path.exists(ziel), "Nach dem Abbruch liegt die Datei am Ziel.")
        reste = [n for n in os.listdir(self.basis) if ".transfer-" in n]
        self.assertEqual(reste, [], "Die Uebertragungsdatei blieb liegen.")

    def test_ohne_abbruch_wird_gebaut(self) -> None:
        """Gegenprobe: Der Weg selbst funktioniert mit denselben Attrappen."""
        ok, ziel = self._bauen("")
        self.assertTrue(ok)
        self.assertTrue(os.path.isfile(ziel))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class FensterWachstumTests(unittest.TestCase):
    """Der zweite Anlauf zentrierte ein verschobenes Fenster neu und protokollierte doppelt."""

    def test_zweiter_anlauf_laesst_ein_passendes_fenster_in_ruhe(self) -> None:
        app = _app()
        win = tk.Toplevel(_WURZEL)
        self.addCleanup(win.destroy)
        win.geometry("300x200+%d+%d" % ((win.winfo_screenwidth() - 300) // 2,
                                        (win.winfo_screenheight() - 200) // 2))
        tk.Frame(win, width=520, height=380).pack()
        with mock.patch.object(APP.logger, "info") as protokoll:
            app._fenster_auf_inhalt_wachsen(win, 300, 200, True)
            win.update_idletasks()
            win.geometry("+37+41")          # der Anwender verschiebt es
            win.update_idletasks()
            app._fenster_auf_inhalt_wachsen(win, 300, 200, True)
            win.update_idletasks()
        breite, hoehe, x, y = GUI._fenster_geometrie(win)
        self.assertGreaterEqual(breite, 520)
        self.assertEqual((x, y), (37, 41), "Der zweite Anlauf hat das Fenster verschoben.")
        vergroessert = [c for c in protokoll.call_args_list
                        if "vergr" in str(c.args[0] if c.args else "")]
        self.assertEqual(len(vergroessert), 1, "Das Wachsen steht mehrfach im Protokoll.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class BeendenReihenfolgeTests(unittest.TestCase):
    """Nein bei "Aufgabe laeuft noch - beenden?" schloss trotzdem die Werkzeugfenster."""

    def test_nein_laesst_werkzeugfenster_und_aufgabe_in_ruhe(self) -> None:
        app = _app()
        geschlossen: list = []
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.addCleanup(fenster.destroy)
        vorher = app.is_running
        self.addCleanup(setattr, app, "is_running", vorher)
        app.is_running = True
        with mock.patch.object(app, "_werkzeugfenster", {"probe": fenster}, create=True), \
                mock.patch.object(app, "_werkzeugfenster_schliessen",
                                  lambda befehl: geschlossen.append(befehl)), \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: False):
            app.on_closing()
        self.assertEqual(geschlossen, [], "Werkzeugfenster wurden trotz Nein geschlossen.")
        self.assertTrue(app.is_running, "Die Aufgabe wurde trotz Nein beendet.")

    def test_verweigert_ein_werkzeugfenster_laeuft_die_aufgabe_weiter(self) -> None:
        app = _app()
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.addCleanup(fenster.destroy)
        vorher = app.is_running
        self.addCleanup(setattr, app, "is_running", vorher)
        app.is_running = True
        with mock.patch.object(app, "_werkzeugfenster", {"probe": fenster}, create=True), \
                mock.patch.object(app, "_werkzeugfenster_schliessen", lambda _b: None), \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: True):
            app.on_closing()
        self.assertTrue(app.is_running,
                        "Die Aufgabe wurde beendet, obwohl das Programm offen bleibt.")


class VorschauOhneAuspackenTests(unittest.TestCase):
    """Die Quellvorschau packte flache .ffpfs komplett in den Temp-Ordner aus."""

    @classmethod
    def setUpClass(cls) -> None:
        import json
        import subprocess

        cls.arbeit = tempfile.mkdtemp(prefix="dbg_befund_vorschau_")
        dump = os.path.join(cls.arbeit, "PPSA01234")
        _schreiben(os.path.join(dump, "eboot.bin"), os.urandom(200_000))
        _schreiben(os.path.join(dump, "sce_sys", "param.json"), json.dumps({
            "titleId": "PPSA01234",
            "contentId": "UP0000-PPSA01234_00-0000000000000000",
            "contentVersion": "01.002.000",
            "localizedParameters": {"defaultLanguage": "en-US",
                                    "en-US": {"titleName": "Vorschau Probe"}},
        }).encode("utf-8"))
        cls.flach = os.path.join(cls.arbeit, "Spiel.ffpfs")
        lauf = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "folder", "--raw", "--no-compress",
             "--no-adjust-output-file-extension", "--version", "PS5", "--inode-bits", "32",
             "--block-size", "65536", dump, cls.flach],
            capture_output=True, cwd=str(PROJEKT / "MkPFS-1.0.0"), timeout=180)
        cls.baufehler = lauf.stderr.decode("utf-8", "replace") if lauf.returncode else ""

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.arbeit, ignore_errors=True)

    def setUp(self) -> None:
        if self.baufehler:
            self.skipTest("mkpfs konnte nichts bauen: %s" % self.baufehler[:200])

    def _leser(self):
        from ps5_validator.utils import abbild_metadaten

        return abbild_metadaten.Metadatenleser(
            pfs_leser_oeffnen=lambda fh: GUI._open_virtual_pfs_reader(None, fh))

    def test_flache_ffpfs_wird_virtuell_gelesen(self) -> None:
        meta, _bild = self._leser()._extract_meta_from_ffpfsc_virtual(self.flach)
        self.assertEqual(meta.get("title_id"), "PPSA01234", meta)
        self.assertIn("flach", meta.get("_metadata_method", ""))

    def test_flache_ffpfs_wird_nie_ausgepackt(self) -> None:
        gui = GUI.__new__(GUI)
        gui.mkpfs_dir = str(PROJEKT / "MkPFS-1.0.0")
        gui._fmt_bytes = lambda n: "%d B" % n
        self.assertFalse(gui._vorschau_entpacken_vertretbar(self.flach),
                         "Die Vorschau wuerde das ganze Spiel auspacken.")


# ---------------------------------------------------------------------------
# Dritter Block (17.09.2026): Mausrad, Installer, Metadaten, Automatik, Liste
# ---------------------------------------------------------------------------

class MausradTests(unittest.TestCase):
    """int(-delta/120) ergab unter macOS und auf Touchpads 0 (oder "immer hoch")."""

    def test_schritte_je_plattform(self) -> None:
        faelle = {
            120: -1, -120: 1, 240: -2, -360: 3,      # Windows-Mausrad
            1: -1, -1: 1, 7: -1, -10: 1,             # macOS
            30: -1, -45: 1,                          # Praezisions-Touchpad
            0: 0,
        }
        for delta, erwartet in faelle.items():
            with self.subTest(delta=delta):
                self.assertEqual(GUI._rad_einheiten(mock.Mock(delta=delta)), erwartet)

    def test_keine_alte_rechnung_mehr(self) -> None:
        quelle = HAUPTDATEI.read_text(encoding="utf-8")
        alt = [z.strip() for z in quelle.splitlines()
               if "delta / 120" in z and "_rad_einheiten" not in z
               and "int(-delta / 120)" not in z and not z.strip().startswith("#")
               and "``" not in z]
        self.assertEqual(alt, [])


class InstallerTests(unittest.TestCase):
    """Windows-Installer unter macOS/Linux und Dialoge aus dem Faden."""

    def test_ressourcen_19_bis_21_nur_unter_windows(self) -> None:
        baum = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        for name in ("_install_osfmount_background", "_install_dokan2_background",
                     "_install_filezilla_background"):
            with self.subTest(methode=name):
                aufruf = next(k for k in ast.walk(_methode(baum, name))
                              if isinstance(k, ast.Call)
                              and getattr(k.func, "attr", "") == "_run_background_installer")
                werte = {kw.arg: kw.value for kw in aufruf.keywords}
                self.assertIn("nur_windows", werte)
                self.assertIs(getattr(werte["nur_windows"], "value", None), True)

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_filezilla_installation_oeffnet_im_faden_keinen_dialog(self) -> None:
        app = _app()
        dialoge: list = []
        ergebnis: list = []
        with mock.patch.object(APP.sys, "platform", "linux"), \
                mock.patch.object(APP.messagebox, "showwarning",
                                  lambda *a, **k: dialoge.append("warn")), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda *a, **k: dialoge.append("error")), \
                mock.patch.object(app, "_append_to_log", lambda *a: None):
            faden = threading.Thread(target=lambda: ergebnis.append(app._install_filezilla()))
            faden.start()
            faden.join(10)
        self.assertEqual(ergebnis, [False])
        self.assertEqual(dialoge, [], "Dialog aus dem Arbeitsfaden geoeffnet.")

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_osfmount_laedt_ausserhalb_von_windows_nichts(self) -> None:
        """Aufrufe mitschreiben, nicht werfen: _install_osfmount faengt jede
        Ausnahme selbst - eine werfende Attrappe bliebe unbemerkt."""
        app = _app()
        geladen: list = []
        with mock.patch.object(APP, "IST_WINDOWS", False), \
                mock.patch.object(APP.urllib.request, "urlretrieve",
                                  lambda *a, **k: geladen.append(a)), \
                mock.patch.object(app, "_run_subprocess_logged", lambda *a, **k: 1), \
                mock.patch.object(app, "_append_to_log", lambda *a: None):
            self.assertFalse(app._install_osfmount())
        self.assertEqual(geladen, [], "Unter macOS/Linux wurde ein Windows-Installer geladen.")


class MetadatenFeinheitenTests(unittest.TestCase):

    def test_bauangaben_sind_kein_hersteller(self) -> None:
        from ps5_validator.utils import abbild_metadaten

        sfo = {"TITLE": "Spiel", "TITLE_ID": "CUSA00001",
               "PUBTOOLINFO": "c_date=20141024,c_time=080903,sdk_ver=01750000",
               "PUBLISHER": "Beispiel GmbH"}
        leser = abbild_metadaten.Metadatenleser(sfo_lesen=lambda _roh: sfo)
        meta = leser._meta_from_param_sfo_bytes(b"egal")
        self.assertEqual(meta["publisher"], "Beispiel GmbH")

    def test_sce_sys_aus_pfs_ohne_nutzdatenpruefung(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "utils" / "abbild_metadaten.py").read_text(
            encoding="utf-8")
        methode = _methode(_klasse(ast.parse(quelle), "Metadatenleser"),
                           "_extract_meta_files_from_pfs")
        aufrufe = [k for k in ast.walk(methode) if isinstance(k, ast.Call)
                   and getattr(k.func, "id", "") == "inspect_pfs_image"]
        self.assertTrue(aufrufe)
        for aufruf in aufrufe:
            werte = {kw.arg: getattr(kw.value, "value", None) for kw in aufruf.keywords}
            self.assertIs(werte.get("verify_payloads"), False,
                          "Fuer drei Dateien aus sce_sys wird jede Datei dekodiert.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class AmprAutomatikAbschlussTests(_TempTest):
    """"Fertig - jetzt das Spiel starten" kam auch nach gescheitertem Ablegen."""

    def test_gescheitertes_ablegen_meldet_keinen_erfolg(self) -> None:
        from ps5_validator.utils import shadowmount_generation as sg

        app = _app()
        # Der Zielordner laesst sich anlegen, die Datei aber nicht kopieren -
        # ein scheiterndes Anlegen endete schon vorher und maesse nichts.
        ziel = os.path.join(self.basis, "spiel", "fakelib")
        fehlt = os.path.join(self.basis, "gibt_es_nicht", "libSceAmpr.sprx")
        zeilen, abgelegt = app._ampr_gen_ablegen_mit_ergebnis(
            sg.NEU, sg.ORT_SPIEL, lokal=True, ziel=ziel, dateien=[fehlt])
        self.assertTrue(os.path.isdir(ziel), "Der Test misst sonst das Anlegen.")
        self.assertFalse(abgelegt)
        self.assertNotIn(app._t("amprgen.done", path=ziel), zeilen)

    def test_automatik_bricht_nach_fehlschlag_vor_dem_fertig_ab(self) -> None:
        methode = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))),
                           "_ampr_gen_automatik")
        texte = [(k.lineno, k.value) for k in ast.walk(methode)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        unvollstaendig = [z for z, t in texte if t == "amprgen.place_incomplete"]
        fertig = [z for z, t in texte if t == "amprgen.finished"]
        self.assertTrue(unvollstaendig, "Der Fehlschlag beim Hochladen wird nicht ausgewertet.")
        rueckkehr = [k.lineno for k in ast.walk(methode) if isinstance(k, ast.Return)]
        for zeile in unvollstaendig:
            self.assertTrue(any(zeile < r < min(fertig) for r in rueckkehr),
                            "Nach 'place_incomplete' laeuft die Automatik bis 'Fertig'.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ZielformatListeTests(_TempTest):
    """Bei einer .ffpfs-Quelle stand das gesperrte .ffpfs in der Liste."""

    def test_ffpfs_quelle(self) -> None:
        app = _app()
        quelle = _schreiben(os.path.join(self.basis, "Spiel.ffpfs"), b"x" * 64)
        umwandeln = app._get_target_options("universal_convert", quelle)
        self.assertNotIn("ffpfs", umwandeln)
        self.assertIn("ffpfsc", umwandeln, ".ffpfs -> .ffpfsc ist eine erlaubte Umwandlung.")
        self.assertNotIn("ffpfs", app._get_target_options("unpack_to_exfat", quelle))

    def test_ffpfsc_quelle_unveraendert(self) -> None:
        app = _app()
        quelle = _schreiben(os.path.join(self.basis, "Spiel.ffpfsc"), b"x" * 64)
        self.assertEqual(app._get_target_options("universal_convert", quelle),
                         ("folder", "ffpfs", "exfat", "ffpkg"))


class BibliothekSuchlaufTests(unittest.TestCase):
    """Ein alter Suchlauf ueberschrieb nach dem Quellwechsel die neue Liste."""

    def test_beide_suchlaeufe_pruefen_ihre_nummer(self) -> None:
        fenster = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))),
                           "_render_library_window")
        for name in ("_finish", "_fertig"):
            with self.subTest(rueckmeldung=name):
                fn = next(k for k in ast.walk(fenster)
                          if isinstance(k, ast.FunctionDef) and k.name == name)
                erste = fn.body[0]
                self.assertIsInstance(erste, ast.If)
                self.assertIn("suchlauf", ast.dump(erste.test))


# ---------------------------------------------------------------------------
# Vierter Block (17.09.2026): Abbrechen, Abbild->PKG, Balken, Doku
# ---------------------------------------------------------------------------

@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class AbbrechenOhneEinfrierenTests(unittest.TestCase):
    """_kill_task wartete im Fensterfaden bis zu 8 s auf den Aufgabenfaden."""

    def test_abbrechen_kehrt_sofort_zurueck(self) -> None:
        import time

        app = _app()
        gestartet = threading.Event()
        weiter = threading.Event()
        faeden: list = []

        def _langsam() -> None:
            faeden.append(threading.current_thread() is threading.main_thread())
            gestartet.set()
            weiter.wait(10)

        vorher = (app.is_running, app.monitor_active)
        self.addCleanup(lambda: (setattr(app, "is_running", vorher[0]),
                                 setattr(app, "monitor_active", vorher[1])))
        with mock.patch.object(app, "_force_dismount_all", _langsam), \
                mock.patch.object(app, "_append_to_log", lambda *a: None):
            beginn = time.monotonic()
            app._kill_task()
            dauer = time.monotonic() - beginn
            self.assertTrue(gestartet.wait(5), "Das Abhaengen wurde gar nicht angestossen.")
            weiter.set()
        _WURZEL.update()
        self.assertLess(dauer, 1.0, "Abbrechen blockierte den Fensterfaden.")
        self.assertEqual(faeden, [False], "Das Abhaengen lief im Fensterfaden.")


class AbbildPkgAufraeumenTests(unittest.TestCase):
    """Knoepfe kamen vor dem Loeschen zurueck; MkPFS schrieb nach dem Loeschen weiter."""

    def test_erst_warten_dann_loeschen_dann_freigeben(self) -> None:
        fenster = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))),
                           "_show_exfat_pkg_builder")
        umwandeln = next(k for k in ast.walk(fenster)
                         if isinstance(k, ast.FunctionDef) and k.name == "_umwandeln")
        arbeit = next(k for k in ast.walk(umwandeln)
                      if isinstance(k, ast.FunctionDef) and k.name == "_arbeit")
        versuch = next(k for k in arbeit.body if isinstance(k, ast.Try) and k.finalbody)

        def _zeile(pruefung) -> int:
            return min((k.lineno for anweisung in versuch.finalbody
                        for k in ast.walk(anweisung) if pruefung(k)), default=10 ** 9)

        warten = _zeile(lambda k: isinstance(k, ast.Call)
                        and getattr(k.func, "attr", "") == "_wait_for_pending_mkpfs_background")
        loeschen = _zeile(lambda k: isinstance(k, ast.Call)
                          and getattr(k.func, "id", "") == "_rmtree_force")
        frei = _zeile(lambda k: isinstance(k, ast.Assign)
                      and "aktiv" in ast.dump(k.targets[0]))
        self.assertLess(loeschen, frei, "Die Knoepfe kommen vor dem Loeschen zurueck.")
        self.assertLess(warten, loeschen, "Geloescht wird, waehrend MkPFS noch schreibt.")


class ZweistufigerBalkenTests(_TempTest):
    """Die zweite Stufe stand ihre ganze Dauer bei 98-99 %."""

    def _gui(self, stufen: list):
        gui = GUI.__new__(GUI)
        gui._batch_von, gui._batch_bis = 0.0, 100.0
        gui.task_progress = 0.0
        gui._mkdtemp = lambda prefix, dir_path=None: tempfile.mkdtemp(
            prefix=prefix, dir=self.basis)
        gui._dump_ordner_basis = lambda dst: self.basis
        gui._append_to_log = lambda *a: None
        gui._integration_anwenden = lambda ordner, **_k: ordner

        def _auspacken(src, ziel, **_k):
            stufen.append(("auspacken", gui._batch_von, gui._batch_bis))
            gui.task_progress = 99.0
            os.makedirs(os.path.join(ziel, "Spiel"), exist_ok=True)
            return True

        def _packen(ordner, dst, **_k):
            stufen.append(("packen", gui._batch_von, gui._batch_bis, gui.task_progress))
            return True

        gui._mode_unpack_to_game_folder = _auspacken
        gui._mode_pack_folder = _packen
        return gui

    def test_jede_stufe_bekommt_ihren_teil(self) -> None:
        stufen: list = []
        gui = self._gui(stufen)
        self.assertTrue(gui._mode_ffpfsc_umpacken(
            os.path.join(self.basis, "Spiel.ffpfsc"), self.basis, uncompressed=True))
        self.assertEqual(stufen[0], ("auspacken", 0.0, 50.0))
        self.assertEqual(stufen[1], ("packen", 50.0, 100.0, 0.0),
                         "Die zweite Stufe beginnt nicht bei null in ihrem Abschnitt.")
        self.assertEqual((gui._batch_von, gui._batch_bis), (0.0, 100.0),
                         "Der Abschnitt wird am Ende nicht zurueckgesetzt.")

    def test_in_der_sammelkonvertierung_teilt_sich_der_dateiabschnitt(self) -> None:
        stufen: list = []
        gui = self._gui(stufen)
        gui._batch_von, gui._batch_bis = 50.0, 100.0
        gui._mode_ffpfsc_umpacken(os.path.join(self.basis, "Spiel.ffpfsc"), self.basis,
                                  uncompressed=False)
        self.assertEqual(stufen[0][1:], (50.0, 75.0))
        self.assertEqual(stufen[1][1:3], (75.0, 100.0))
        self.assertEqual((gui._batch_von, gui._batch_bis), (50.0, 100.0))

    def test_alle_zweistufigen_wege_nutzen_die_abschnitte(self) -> None:
        klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        for name in ("_mode_ffpfsc_to_ffpkg", "_mode_ffpfsc_umpacken",
                     "_mode_abbild_zu_ffpfs", "_mode_exfat_to_ffpkg"):
            with self.subTest(weg=name):
                aufrufe = [k for k in ast.walk(_methode(klasse, name))
                           if isinstance(k, ast.Call)
                           and getattr(k.func, "attr", "") == "_balkenabschnitt_beginnen"]
                self.assertEqual(len(aufrufe), 2)


class DokuStandTests(unittest.TestCase):
    """Was README und Pruefskript behaupten, muss stimmen."""

    def test_readme_ffpkg_ist_ueberall_verfuegbar(self) -> None:
        text = (PROJEKT / "README.md").read_text(encoding="utf-8")
        zeile = next(z for z in text.splitlines() if z.startswith("| `.ffpkg` lesen und bauen"))
        self.assertNotIn("Nicht verfügbar", zeile,
                         "Seit v1.8.72 liegt UFS2Tool fuer alle Plattformen bei.")

    def test_readme_testbefehl_lenkt_die_einstellungen_um(self) -> None:
        text = (PROJEKT / "README.md").read_text(encoding="utf-8")
        abschnitt = text[text.index("Die Testreihe"):text.index("## Plattformunterschiede")]
        self.assertIn("PS5CONV_KONFIGORDNER", abschnitt)

    def test_matrixskript_schreibt_paths_json_ohne_bom(self) -> None:
        text = (PROJEKT / "Pruefung_ffpkg_Matrix.ps1").read_text(encoding="utf-8-sig")
        for zeile in text.splitlines():
            if "paths.json" in zeile and not zeile.strip().startswith("#"):
                self.assertNotIn("Out-File", zeile,
                                 "Out-File -Encoding utf8 schreibt unter PS 5.1 ein BOM.")


class AssetPackTests(_TempTest):
    """Abbruch in "verify" wirkte nicht; Ausgabeordner blieb nach Fehlschlag."""

    def test_abbruch_wirkt_auch_ohne_ausgabe_des_werkzeugs(self) -> None:
        import io as _io
        import time

        from ps5_validator.utils import ampr_assetpakete as ap

        class _StillerProzess:
            """Schreibt nichts, bis er beendet wird - wie "verify"."""

            def __init__(self) -> None:
                self.beendet = threading.Event()
                self.returncode = None
                self.stdout = _io.StringIO("")
                self.stderr = self

            def __iter__(self):
                return self

            def __next__(self):
                self.beendet.wait(8)
                raise StopIteration

            def poll(self):
                return self.returncode

            def terminate(self) -> None:
                self.returncode = -15
                self.beendet.set()

            def wait(self, timeout=None):
                self.beendet.wait(8)
                return self.returncode

            def close(self) -> None:
                pass

        prozess = _StillerProzess()
        beginn = time.monotonic()
        with mock.patch.object(ap, "werkzeug_finden", return_value=__file__), \
                mock.patch.object(ap, "_python_ruf", return_value=["python"]), \
                mock.patch.object(ap.subprocess, "Popen", return_value=prozess):
            with self.assertRaises(ap.PackFehler) as fall:
                ap._lauf(["verify"], melden=lambda *_a: None,
                         abbruch=lambda: time.monotonic() - beginn > 0.3)
        self.assertEqual(str(fall.exception), "ampr_pack.abgebrochen")
        self.assertLess(time.monotonic() - beginn, 5.0,
                        "Der Abbruch wartete auf das Ende des Werkzeugs.")

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_ausgabeordner_verschwindet_nach_fehlschlag(self) -> None:
        from ps5_validator.utils import ampr_assetpakete as ap

        app = _app()
        spiel = os.path.join(self.basis, "PPSA01234")
        os.makedirs(spiel)
        ausgabe = spiel + "_ampr_pack"

        def _profil(pfad, **_k):
            _schreiben(pfad, b"[pack]")
            _schreiben(os.path.join(os.path.dirname(pfad), "band_0000.pak"), b"x" * 1024)
            return pfad

        with mock.patch.object(ap, "einsatzbereit", return_value=(True, "")), \
                mock.patch.object(ap, "profil_schreiben", side_effect=_profil), \
                mock.patch.object(ap, "packen",
                                  side_effect=ap.PackFehler("ampr_pack.abgebrochen")), \
                mock.patch.object(app, "_append_to_log", lambda *a: None), \
                mock.patch.object(app, "_set_status", lambda *a: None):
            self.assertFalse(app._ampr_assetpakete_bauen(spiel, "idx", {}))
        self.assertFalse(os.path.exists(ausgabe),
                         "Der Ausgabeordner blieb nach dem Fehlschlag liegen.")

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_ein_fremder_vorhandener_ausgabeordner_bleibt(self) -> None:
        from ps5_validator.utils import ampr_assetpakete as ap

        app = _app()
        spiel = os.path.join(self.basis, "PPSA01234")
        os.makedirs(spiel)
        vorhanden = _schreiben(os.path.join(spiel + "_ampr_pack", "alt.txt"), b"alt")
        with mock.patch.object(ap, "einsatzbereit", return_value=(True, "")), \
                mock.patch.object(ap, "profil_schreiben",
                                  side_effect=ap.PackFehler("kaputt")), \
                mock.patch.object(app, "_append_to_log", lambda *a: None), \
                mock.patch.object(app, "_set_status", lambda *a: None):
            self.assertFalse(app._ampr_assetpakete_bauen(spiel, "idx", {}))
        self.assertTrue(os.path.isfile(vorhanden))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ExtraktionAbbruchTests(_TempTest):
    """exFAT-Extraktion und robocopy liefen nach "Abbrechen" bis zum Ende."""

    def test_native_exfat_extraktion_bricht_ab(self) -> None:
        from mkpfs.exfat_writer import write_exfat_image

        app = _app()
        dump = os.path.join(self.basis, "PPSA00001")
        for i in range(3):
            _schreiben(os.path.join(dump, "daten", "datei%d.bin" % i), os.urandom(200_000))
        _schreiben(os.path.join(dump, "sce_sys", "param.json"), b'{"titleId":"PPSA00001"}')
        abbild = os.path.join(self.basis, "Spiel.exfat")
        write_exfat_image(Path(dump), Path(abbild))
        ziel = os.path.join(self.basis, "ausgepackt")
        protokoll: list = []
        vorher = app.is_running
        self.addCleanup(setattr, app, "is_running", vorher)
        app.is_running = False            # "Abbrechen" ist schon gedrueckt
        with mock.patch.object(app, "_append_to_log", protokoll.append):
            ok = app._extract_exfat_to_folder_mkpfs(
                abbild, ziel, status_prefix="Test", log_prefix="Test",
                progress_start=0.0, progress_end=100.0)
        _WURZEL.update()
        self.assertFalse(ok, "Die Extraktion lief trotz Abbruch durch.")
        self.assertIn(app._t("log.extraktion_abgebrochen"), protokoll)

    def test_robocopy_wird_beim_abbruch_beendet(self) -> None:
        """Alle drei robocopy-Wege - der erste Entwurf dieses Tests sah nur
        einen und fand dabei den zweiten mit demselben Fehler."""
        klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        rueckrufe = [k for k in ast.walk(klasse)
                     if isinstance(k, ast.FunctionDef) and k.name == "_log_robo_line"]
        self.assertGreaterEqual(len(rueckrufe), 3)
        for fn in rueckrufe:
            with self.subTest(zeile=fn.lineno):
                rueckgaben = [k for k in ast.walk(fn) if isinstance(k, ast.Return)]
                self.assertTrue(
                    rueckgaben and all("is_running" in ast.dump(r) for r in rueckgaben),
                    "_log_robo_line (Zeile %d) meldet den Abbruch nicht an robocopy "
                    "weiter." % fn.lineno)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class BackportPlatzImFadenTests(_TempTest):
    """Das Vermessen des Dumps fror das BACKPORT-Fenster ein.

    ``_starten`` rief die Platzpruefung fuer die Sicherung im Fensterfaden
    auf: ``_get_path_size`` ueber einen Dump von 40 bis 100 GB. Das Fenster
    war minutenlang nicht bedienbar, und die Zwischenstaende erschienen erst,
    als alles vorbei war.
    """

    @staticmethod
    def _in_schleife(fertig, sekunden: float = 10.0) -> None:
        """Laesst eine echte Ereignisschleife laufen, bis ``fertig()`` gilt.

        ``update()`` genuegt nicht: Der Messfaden meldet ueber
        ``_spaeter_im_fenster``, und Tk wirft im Faden ohne laufende
        ``mainloop`` (siehe test_shadowmount_editor.py).
        """
        ende = time.monotonic() + sekunden

        def _takt() -> None:
            if fertig() or time.monotonic() > ende:
                _WURZEL.quit()
            else:
                _WURZEL.after(20, _takt)

        _WURZEL.after(20, _takt)
        _WURZEL.mainloop()

    @staticmethod
    def _widgets(wurzel) -> list:
        gefunden, offen = [], [wurzel]
        while offen:
            w = offen.pop()
            gefunden.append(w)
            offen.extend(w.winfo_children())
        return gefunden

    def test_gemessen_wird_im_faden_und_das_fenster_bleibt_bedienbar(self) -> None:
        app = _app()
        freigabe = threading.Event()
        self.addCleanup(freigabe.set)
        messung: dict = {}
        fragen: list = []

        def _messen_attrappe(_ordner, melden=None):
            messung["hauptfaden"] = threading.current_thread() is threading.main_thread()
            if melden is not None:
                melden("Zwischenstand 4711")
            freigabe.wait(5.0)
            return (1, 1 << 50)                 # reichlich Platz

        def _frage(titel, *_a, **_k):
            fragen.append(titel)
            return False                        # "Nein" - kein Backport-Lauf

        vorher = {str(w) for w in _WURZEL.winfo_children()}
        with mock.patch.object(app, "_backport_platz_messen", _messen_attrappe), \
                mock.patch.object(APP.ps5_backport, "fakelib_dateien",
                                  lambda *_a, **_k: ["libc.prx"]), \
                mock.patch.object(APP.messagebox, "askyesno", _frage):
            app._render_backport_window(self.basis)
            neu = [w for w in _WURZEL.winfo_children()
                   if str(w) not in vorher and isinstance(w, tk.Toplevel)]
            self.assertTrue(neu, "Es wurde kein Fenster geöffnet.")
            fenster = neu[-1]
            self.addCleanup(fenster.destroy)
            start = [w for w in self._widgets(fenster)
                     if w.winfo_class() == "TButton"
                     and str(w.cget("text")) == app._t("backport.action_start")]
            self.assertEqual(len(start), 1)
            start = start[0]

            def _texte() -> str:
                texte = []
                for w in self._widgets(fenster):
                    try:
                        texte.append(str(w.cget("text")))
                    except tk.TclError:
                        pass
                return "\n".join(texte)

            # Die Analyse beim Oeffnen sperrt den Knopf, bis sie zurueck ist.
            self._in_schleife(lambda: str(start.cget("state")) == "normal")
            self.assertEqual(str(start.cget("state")), "normal",
                             "Die Analyse beim Öffnen kam nicht zurück.")

            start.invoke()
            self._in_schleife(lambda: "hauptfaden" in messung)
            self.assertIs(messung.get("hauptfaden"), False,
                          "Der Dump wird im Fensterfaden vermessen - das Fenster "
                          "steht dabei still.")
            # Waehrend die Messung noch laeuft: Zwischenstand sichtbar, noch
            # nichts gefragt, Start gesperrt.
            self._in_schleife(lambda: "Zwischenstand 4711" in _texte())
            self.assertIn("Zwischenstand 4711", _texte())
            self.assertEqual(fragen, [], "Gefragt wurde vor dem Ende der Messung.")
            self.assertEqual(str(start.cget("state")), "disabled")

            freigabe.set()
            self._in_schleife(lambda: bool(fragen))
            self.assertEqual(fragen, [app._t("backport.confirm_title")])
            self.assertEqual(str(start.cget("state")), "normal",
                             "Nach der Messung bleibt der Start gesperrt.")
            self.assertNotIn("Zwischenstand 4711", _texte(),
                             "Der Messstand bleibt nach der Messung stehen.")

    def test_ein_selbst_ergaenzter_firmware_satz_ist_waehlbar(self) -> None:
        """Das Fenster bot fest 4 bis 7 an - beim Erstellen galt der Bestand."""
        app = _app()
        gefragt_fuer: list = []
        fragen: list = []

        def _satz(_basis, firmware):
            gefragt_fuer.append(firmware)
            return ["libc.prx"]

        vorher = {str(w) for w in _WURZEL.winfo_children()}
        with mock.patch.object(app, "_backport_firmwares", lambda: (4, 5, 6, 7, 8)), \
                mock.patch.object(app, "_backport_platz_messen",
                                  lambda *_a, **_k: (1, 1 << 50)), \
                mock.patch.object(APP.ps5_backport, "fakelib_dateien", _satz), \
                mock.patch.object(APP.messagebox, "askyesno",
                                  lambda titel, *a, **k: fragen.append(titel) or False):
            app._render_backport_window(self.basis)
            fenster = [w for w in _WURZEL.winfo_children()
                       if str(w) not in vorher and isinstance(w, tk.Toplevel)][-1]
            self.addCleanup(fenster.destroy)
            boxen = [w for w in self._widgets(fenster) if w.winfo_class() == "TCombobox"]
            self.assertEqual(len(boxen), 1)
            werte = list(boxen[0].cget("values"))
            self.assertIn(app._t("backport.firmware_entry", fw="8.00"), werte)
            start = [w for w in self._widgets(fenster)
                     if w.winfo_class() == "TButton"
                     and str(w.cget("text")) == app._t("backport.action_start")][0]
            self._in_schleife(lambda: str(start.cget("state")) == "normal")
            boxen[0].current(werte.index(app._t("backport.firmware_entry", fw="8.00")))
            gefragt_fuer.clear()
            start.invoke()
            self._in_schleife(lambda: bool(fragen))
        self.assertEqual(gefragt_fuer, [8], "Gestartet wurde nicht fuer Firmware 8.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class BackportAbbruchTests(_TempTest):
    """Der BACKPORT liess sich nicht anhalten.

    Das Fenster hatte keinen Schliessen-Handler: SCHLIESSEN und das X
    zerstoerten es, der Faden lief unsichtbar weiter - die Sicherung (40 bis
    100 GB) und das Herabsetzen. Das Beenden des Programms fragte nicht nach,
    und grosse Dateien kopierte die Sicherung mit ``lambda: True`` als
    Abbruchpruefung.
    """

    class _Aus:
        """Ein Fenster oder Knopf, den es nicht mehr gibt."""

        def winfo_exists(self) -> bool:
            return False

        def configure(self, **_k) -> None:
            pass

    def _dump(self) -> str:
        dump = os.path.join(self.basis, "spiel")
        for nummer in range(6):
            _schreiben(os.path.join(dump, "daten", "teil%02d.bin" % nummer), b"x" * 64)
        _schreiben(os.path.join(dump, "eboot.bin"), b"\x7fELF" + b"\0" * 60)
        return dump

    def _sicherung(self) -> str:
        ordner = [n for n in os.listdir(self.basis) if n.startswith("spiel_backup_")]
        self.assertEqual(len(ordner), 1, ordner)
        return os.path.join(self.basis, ordner[0])

    def _lauf(self, laeuft: dict) -> tuple:
        app = _app()
        protokoll: list = []
        dialoge: list = []
        aus = self._Aus()
        stand = tk.StringVar(master=_WURZEL)
        with mock.patch.object(app, "_append_to_log",
                               lambda text, *a, **k: protokoll.append(str(text))), \
                mock.patch.object(APP.messagebox, "showinfo",
                                  lambda titel, text, **k: dialoge.append((titel, text))), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda titel, text, **k: dialoge.append((titel, text))):
            app._backport_worker(os.path.join(self.basis, "spiel"),
                                 APP.ps5_backport.FIRMWARE_STANDARD, True, False, False,
                                 aus, {}, stand, laeuft, aus, aus, aus)
            for _ in range(5):
                _WURZEL.update()
        return app, protokoll, dialoge

    def test_abbruch_waehrend_der_sicherung(self) -> None:
        self._dump()
        laeuft = {"aktiv": True, "backport": True, "abbruch": False}
        echt = shutil.copy2
        kopiert: list = []

        def _kopieren(von, nach, *a, **k):
            kopiert.append(von)
            ergebnis = echt(von, nach, *a, **k)
            if len(kopiert) == 2:
                laeuft["abbruch"] = True
            return ergebnis

        bearbeitet: list = []
        with mock.patch.object(APP.shutil, "copy2", _kopieren), \
                mock.patch.object(APP.ps5_backport, "kandidaten",
                                  lambda ordner: bearbeitet.append(ordner) or []):
            app, protokoll, dialoge = self._lauf(laeuft)
        self.assertEqual(len(kopiert), 2, "Nach dem Abbruch wurde weiter gesichert.")
        self.assertEqual(bearbeitet, [], "Nach dem Abbruch wurde der Dump bearbeitet.")
        self.assertFalse(laeuft["backport"] or laeuft["aktiv"])
        sicherung = self._sicherung()
        self.assertEqual(dialoge, [(app._t("backport.cancelled_title"), app._t(
            "backport.cancelled_message", patched=0, skipped=0, failed=0,
            sicherung=app._t("backport.backup_partial", path=sicherung)))])
        self.assertIn(app._t("backport.log_backup_rest", path=sicherung) + chr(10), protokoll)

    def test_abbruch_beim_herabsetzen_nennt_die_vollstaendige_sicherung(self) -> None:
        self._dump()
        laeuft = {"aktiv": True, "backport": True, "abbruch": False}

        def _kandidaten(ordner):
            laeuft["abbruch"] = True
            return [os.path.join(ordner, "eboot.bin")]

        verarbeitet: list = []
        with mock.patch.object(APP.ps5_backport, "kandidaten", _kandidaten), \
                mock.patch.object(APP.ps5_backport, "datei_verarbeiten",
                                  lambda *a, **k: verarbeitet.append(a) or ("", b"", "")):
            app, protokoll, dialoge = self._lauf(laeuft)
        self.assertEqual(verarbeitet, [], "Nach dem Abbruch wurde noch eine Datei bearbeitet.")
        sicherung = self._sicherung()
        self.assertEqual(dialoge, [(app._t("backport.cancelled_title"), app._t(
            "backport.cancelled_message", patched=0, skipped=0, failed=0,
            sicherung=app._t("backport.backup_complete", path=sicherung)))])
        self.assertNotIn(app._t("backport.log_backup_rest", path=sicherung) + chr(10), protokoll,
                         "Eine vollstaendige Sicherung heisst nicht angefangen.")

    def test_grosse_datei_bricht_mitten_im_kopieren_ab(self) -> None:
        self._dump()
        laeuft = {"aktiv": True, "backport": True, "abbruch": False}
        echt = APP._datei_blockweise_kopieren

        def _spion(von, nach, fortschritt, weiter):
            def _nach_dem_block(anzahl: int) -> None:
                fortschritt(anzahl)
                laeuft["abbruch"] = True
            return echt(von, nach, _nach_dem_block, weiter)

        with mock.patch.object(APP, "_KOPIE_BLOCKWEISE_AB", 1), \
                mock.patch.object(APP, "_KOPIE_BLOCK", 8), \
                mock.patch.object(APP, "_datei_blockweise_kopieren", _spion):
            app, _protokoll, dialoge = self._lauf(laeuft)
        dateien = [n for _w, _o, namen in os.walk(self._sicherung()) for n in namen]
        self.assertEqual(dateien, [], "Die erste grosse Datei wurde trotz Abbruch fertig kopiert.")
        self.assertEqual([titel for titel, _text in dialoge], [app._t("backport.cancelled_title")])

    def test_schliessen_bei_laufendem_backport_fragt_und_haelt_an(self) -> None:
        app = _app()
        gestartet = threading.Event()
        freigabe = threading.Event()
        self.addCleanup(freigabe.set)
        erhalten: dict = {}

        def _arbeiter(*args) -> None:
            erhalten["laeuft"] = args[8]
            gestartet.set()
            freigabe.wait(5.0)

        fragen: list = []
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        schleife = BackportPlatzImFadenTests._in_schleife
        with mock.patch.object(app, "_backport_platz_messen", lambda *_a, **_k: (1, 1 << 50)), \
                mock.patch.object(app, "_backport_worker", _arbeiter), \
                mock.patch.object(APP.ps5_backport, "fakelib_dateien",
                                  lambda *_a, **_k: ["libc.prx"]), \
                mock.patch.object(APP.messagebox, "askyesno",
                                  lambda titel, *a, **k: fragen.append(titel) or True):
            app._render_backport_window(self.basis)
            fenster = [w for w in _WURZEL.winfo_children()
                       if str(w) not in vorher and isinstance(w, tk.Toplevel)][-1]
            self.addCleanup(lambda: fenster.winfo_exists() and fenster.destroy())
            start = [w for w in BackportPlatzImFadenTests._widgets(fenster)
                     if w.winfo_class() == "TButton"
                     and str(w.cget("text")) == app._t("backport.action_start")][0]
            schleife(lambda: str(start.cget("state")) == "normal")
            start.invoke()
            schleife(gestartet.is_set)
            self.assertTrue(gestartet.is_set(), "Der Backport startete nicht.")
            laeuft = erhalten["laeuft"]
            self.assertTrue(laeuft.get("backport"))
            fragen.clear()
            fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
        self.assertEqual(fragen, [app._t("backport.abort_title")])
        self.assertTrue(laeuft.get("abbruch"), "Schliessen haelt den Lauf nicht an.")
        self.assertFalse(fenster.winfo_exists())


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class InspektionOhneMetadatenTests(_TempTest):
    """Die Inspektion endete immer mit Erfolg - auch ohne jede Metadaten.

    Liess sich weder param.json noch param.sfo lesen (etwa ohne inneres
    Abbild), zeigte die Tabelle nur Striche, und Aufgabe und
    Kommandozeile meldeten Erfolg (Rueckgabe 0).
    """

    def _pruefen(self, meta: dict) -> tuple:
        app = _app()
        protokoll: list = []
        quelle = _schreiben(os.path.join(self.basis, "spiel.ffpfsc"), b"\0" * 64)
        with mock.patch.object(app, "_execute_mkpfs", lambda *a, **k: None), \
                mock.patch.object(app, "_mkdtemp",
                                  lambda prefix="", **_k: tempfile.mkdtemp(prefix=prefix, dir=self.basis)), \
                mock.patch.object(app, "_read_game_meta", lambda *_a, **_k: dict(meta)), \
                mock.patch.object(app, "_load_cover_image", lambda *_a, **_k: None), \
                mock.patch.object(app, "_enrich_meta_online", lambda m, _t: (m, None)), \
                mock.patch.object(app, "_update_info_box", lambda *_a, **_k: None), \
                mock.patch.object(app, "_append_to_log",
                                  lambda text, *a, **k: protokoll.append(str(text))):
            ergebnis = app._mode_inspect(quelle)
            _WURZEL.update()
        return app, ergebnis, protokoll, quelle

    def test_ohne_metadaten_kein_erfolg(self) -> None:
        strich = chr(0x2013)
        app, ergebnis, protokoll, quelle = self._pruefen({"title": strich, "title_id": strich})
        self.assertIs(ergebnis, False, "Ohne Metadaten meldet die Inspektion Erfolg.")
        self.assertIn(app._t("inspect.keine_metadaten", pfad=quelle), protokoll)

    def test_mit_metadaten_bleibt_es_ein_erfolg(self) -> None:
        app, ergebnis, protokoll, quelle = self._pruefen(
            {"title": "Spiel", "title_id": "PPSA01234"})
        self.assertIs(ergebnis, True)
        self.assertNotIn(app._t("inspect.keine_metadaten", pfad=quelle), protokoll)


class DiagnoseKritischeDateienTests(_TempTest):
    """Der Unvollstaendig-Bericht fuehrte eine eigene Liste kritischer Dateien.

    Darin stand weiter ``sce_sys/pfs-version.dat``, die der Validator seit
    v1.8.31 nur empfiehlt. Scheiterte die Pruefung an einer fehlenden
    eboot.bin, nannte der Bericht den Marker als zweite fehlende kritische
    Datei - bei 2 von 32 echten Dumps fehlt er ganz regulaer.
    """

    def test_dieselbe_liste_wie_der_validator(self) -> None:
        from ps5_validator import diagnose_incomplete
        from ps5_validator.modules.dump_validator import CRITICAL_FILES

        self.assertEqual(diagnose_incomplete.KRITISCHE_DATEIEN, tuple(CRITICAL_FILES))

    def test_ein_dump_ohne_marker_nennt_ihn_nicht(self) -> None:
        from ps5_validator import diagnose_incomplete

        dump = os.path.join(self.basis, "spiel")
        _schreiben(os.path.join(dump, "sce_sys", "param.json"), b"{}")
        bericht = diagnose_incomplete.diagnose_incomplete_extraction(dump)
        self.assertIn("eboot.bin", bericht)
        self.assertNotIn("pfs-version.dat", bericht)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class InfoboxSdkImFadenTests(_TempTest):
    """Die Infobox las die ganze eboot.bin im Fensterfaden - bei jedem Aufruf.

    Gemessen am 17.09.2026 an echten Dumps: Street Fighter 6 (329 MB) 6,1 s
    beim ersten Lesen, danach 0,6 s; Forza Horizon 5 (159 MB) 1,9 s bzw.
    0,23 s. ``_update_info_box`` kommt je Quellwahl mehrmals.
    """

    def _app_mit_quelle(self, quelle: str):
        app = _app()
        vorher = app.source_path.get()
        self.addCleanup(app.source_path.set, vorher)
        app.source_path.set(quelle)
        return app

    def _infobox(self, app) -> None:
        with mock.patch.object(app, "_ampr_emu_stand", lambda _q: "-"), \
                mock.patch.object(app, "_update_sidebar_preview", lambda *_a, **_k: None):
            app._update_info_box({"title": "Spiel"}, None, "1 B", "")

    def test_die_infobox_wartet_nicht_und_merkt_sich_den_stand(self) -> None:
        dump = os.path.join(self.basis, "spiel")
        _schreiben(os.path.join(dump, "eboot.bin"), b"x" * 16)
        app = self._app_mit_quelle(dump)
        freigabe = threading.Event()
        self.addCleanup(freigabe.set)
        aufrufe: list = []

        def _lesen(_ordner):
            aufrufe.append(threading.current_thread() is threading.main_thread())
            freigabe.wait(5.0)
            return "7.00", ""

        variable = app._meta_labels["sdk_stand"]
        with mock.patch.object(app, "_sdk_stand_lesen", _lesen):
            beginn = time.monotonic()
            self._infobox(app)
            self.assertLess(time.monotonic() - beginn, 2.0,
                            "Die Infobox wartet auf die eboot.bin.")
            self.assertEqual(variable.get(), chr(0x2026))
            freigabe.set()
            BackportPlatzImFadenTests._in_schleife(lambda: variable.get() == "7.00")
            self.assertEqual(variable.get(), "7.00")
            self.assertEqual(aufrufe, [False], "Gelesen wurde im Fensterfaden.")
            self._infobox(app)
            self.assertEqual(variable.get(), "7.00")
            self.assertEqual(len(aufrufe), 1, "Der Stand wurde fuer dieselbe Datei erneut gelesen.")

    def test_ein_spaetes_ergebnis_ueberschreibt_die_neue_quelle_nicht(self) -> None:
        """Direkt an _sdk_stand_anzeigen: Ein Wechsel ueber source_path loest
        weitere Infobox-Aufrufe aus, und die ueberschrieben die Zeile in der
        ersten Fassung dieses Tests hinterher wieder - die Gegenprobe blieb
        gruen. Deshalb wird jeder gesetzte Wert aufgezeichnet."""
        alt = os.path.join(self.basis, "alt")
        _schreiben(os.path.join(alt, "eboot.bin"), b"x" * 16)
        neu = os.path.join(self.basis, "neu")
        os.makedirs(neu)
        app = _app()
        freigabe = threading.Event()
        fertig = threading.Event()
        self.addCleanup(freigabe.set)
        gesetzt: list = []

        class _Aufzeichner:
            def set(self, wert) -> None:
                gesetzt.append(wert)

            def get(self):
                return gesetzt[-1] if gesetzt else ""

        def _lesen(_ordner):
            freigabe.wait(5.0)
            fertig.set()
            return "7.00", ""

        with mock.patch.dict(app._meta_labels, {"sdk_stand": _Aufzeichner()}), \
                mock.patch.object(app, "_sdk_stand_lesen", _lesen):
            app._sdk_stand_anzeigen(alt)
            app._sdk_stand_anzeigen(neu)
            self.assertEqual(gesetzt, [chr(0x2026), chr(0x2013)])
            freigabe.set()
            BackportPlatzImFadenTests._in_schleife(
                lambda: fertig.is_set() and not app._sdk_stand_laufend)
        self.assertFalse(app._sdk_stand_laufend, "Das Ergebnis kam nie zurueck.")
        self.assertIn("7.00", app._sdk_stand_merker.values(),
                      "Der Rueckruf lief nie - die Pruefung darunter saehe nichts.")
        # Nicht die ganze Liste vergleichen: Eingeplante Infobox-Aufrufe
        # frueherer Tests (source_path-Beobachter) setzen in der Schleife
        # weitere Werte. Entscheidend ist nur, dass "7.00" nie ankam.
        self.assertNotIn("7.00", gesetzt,
                         "Das Ergebnis der alten Quelle landete bei der neuen.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class ElfOhneKennungTests(_TempTest):
    """Ein "ELF (roh)" galt als herabsetzbar und scheiterte dann immer.

    Gemessen am 17.09.2026: Das Herabsetzen gelang, das Signieren meldete
    danach "Keine ELF-Kennung". Die Analyse im Fenster zaehlte die Datei
    trotzdem als offen. Nebenbefund: Alle Gruende von ``datei_verarbeiten``
    standen fest auf Deutsch im Modul und kamen so in die Statusspalte.
    """

    @staticmethod
    def _roh() -> bytes:
        import test_backport

        daten = bytearray(test_backport.baue_elf())
        daten[0:4] = b"\0\0\0\0"
        return bytes(daten)

    def test_der_lauf_lehnt_es_gleich_mit_grund_ab(self) -> None:
        bp = APP.ps5_backport
        ziel_ps5, ziel_ps4 = bp.sdk_paar(bp.FIRMWARE_STANDARD)
        roh = self._roh()
        kennung, neu, grund = bp.datei_verarbeiten(roh, ziel_ps5=ziel_ps5, ziel_ps4=ziel_ps4)
        self.assertEqual((kennung, neu, grund),
                         (bp.ERG_FEHLER, roh, bp.MELDUNGEN["elf_ohne_kennung"]))

    def test_die_gruende_kommen_uebersetzt_an(self) -> None:
        import test_backport

        app = _app()
        bp = APP.ps5_backport
        ziel_ps5, ziel_ps4 = bp.sdk_paar(bp.FIRMWARE_STANDARD)
        with mock.patch.object(app, "_current_language", "en"):
            texte = app._modul_texte(bp.MELDUNGEN, "backportmod.")
        faelle = {
            "roh": (self._roh(), "ELF without its magic – cannot be signed as it is, left unchanged"),
            "niedrig": (test_backport.baue_elf(ps5_sdk=0x06000040), "already 6.00 or older"),
        }
        for fall, (daten, erwartet) in faelle.items():
            with self.subTest(fall=fall):
                _k, _n, grund = bp.datei_verarbeiten(daten, ziel_ps5=ziel_ps5,
                                                     ziel_ps4=ziel_ps4, texte=texte)
                self.assertEqual(grund, erwartet)

    def test_kein_fester_grund_im_modul(self) -> None:
        bp = APP.ps5_backport
        baum = ast.parse(Path(bp.__file__).read_text(encoding="utf-8"))
        funktion = next(k for k in baum.body
                        if isinstance(k, ast.FunctionDef) and k.name == "datei_verarbeiten")
        ausgenommen = {id(c.args[1]) for c in ast.walk(funktion)
                       if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "_satz"
                       and len(c.args) > 1}
        # Nur der Rumpf ohne Docstring - die Signatur traegt Typangaben als Text.
        rumpf = ast.Module(body=funktion.body[1:], type_ignores=[])
        feste = [k.value for k in ast.walk(rumpf)
                 if isinstance(k, ast.Constant) and isinstance(k.value, str)
                 and id(k) not in ausgenommen
                 and re.search(r"[A-Za-zÄÖÜäöüß]{3,}", k.value)]
        self.assertTrue(any(isinstance(k, ast.Return) for k in ast.walk(rumpf)),
                        "Der Rumpf wurde nicht gefunden - die Pruefung misst nichts.")
        self.assertEqual(feste, [], "Fester Text in datei_verarbeiten - er geht an der Uebersetzung vorbei.")

    def test_die_analyse_zaehlt_es_nicht_als_offen(self) -> None:
        app = _app()
        _schreiben(os.path.join(self.basis, "eboot.bin"), self._roh())
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        with mock.patch.object(APP.ps5_backport, "fakelib_dateien",
                               lambda *_a, **_k: ["libc.prx"]):
            app._render_backport_window(self.basis)
            fenster = [w for w in _WURZEL.winfo_children()
                       if str(w) not in vorher and isinstance(w, tk.Toplevel)][-1]
            self.addCleanup(fenster.destroy)
            baum = [w for w in BackportPlatzImFadenTests._widgets(fenster)
                    if w.winfo_class() == "Treeview"][0]
            BackportPlatzImFadenTests._in_schleife(lambda: bool(baum.get_children()))
            zeilen = [baum.item(iid, "values") for iid in baum.get_children()]
        self.assertEqual([str(z[3]) for z in zeilen], [app._t("backport.row_elf_ohne_kennung")])


def _direkte_aufrufe(funktion: ast.AST) -> set:
    """Aufrufnamen im Rumpf - ohne verschachtelte Funktionen und Lambdas.

    Was in einer inneren Funktion steht, laeuft dort, wo diese hingereicht
    wird (Faden, after) - nicht im Klick selbst.
    """
    gefunden, offen = set(), list(ast.iter_child_nodes(funktion))
    while offen:
        k = offen.pop()
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(k, ast.Call):
            gefunden.add(getattr(k.func, "attr", "") or getattr(k.func, "id", ""))
        offen.extend(ast.iter_child_nodes(k))
    return gefunden


class NetzImKlickTests(unittest.TestCase):
    """Verbindungsaufbau im Klick fror das Programm bei ausgeschalteter Konsole ein.

    Drei Stellen, gefunden am 17.09.2026 ueber den Syntaxbaum (alle Aufrufe von
    _ampr_ftp_connect/_ps5_port_finden, deren Kette in einem Tk-Rueckruf endet):
    Bibliothek "Senden" (30 s Zeitgrenze, danach 144 FTP-Befehle), AMPR-FTP-
    Auswahl "Verbinden" (30 s je Port) und KLOG "Verbinden" (1,5 s je
    Portkandidat). Die USB-Ablagen von WebKit und KLOG blockieren weiter - dort
    ist das dokumentiert und kommt erst nach einer ausdruecklichen Zustimmung.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))

    def _innere(self, methode: str, innen: str) -> ast.FunctionDef:
        treffer = [k for k in ast.walk(_methode(self.klasse, methode))
                   if isinstance(k, ast.FunctionDef) and k.name == innen]
        self.assertEqual(len(treffer), 1, "%s.%s nicht eindeutig" % (methode, innen))
        return treffer[0]

    def test_bibliothek_senden_verbindet_nicht_im_klick(self) -> None:
        direkt = _direkte_aufrufe(_methode(self.klasse, "_bibliothek_hochladen"))
        for name in ("_ampr_ftp_connect", "_bibliothek_ziele_auf_ps5"):
            self.assertNotIn(name, direkt)
        self.assertIn("Thread", direkt)

    def test_ampr_auswahl_verbindet_nicht_im_klick(self) -> None:
        direkt = _direkte_aufrufe(self._innere("_show_ampr_ftp_picker", "_connect"))
        self.assertNotIn("_ampr_ftp_connect", direkt)
        self.assertIn("Thread", direkt)

    def test_klog_sucht_den_port_nicht_im_klick(self) -> None:
        direkt = _direkte_aufrufe(self._innere("_show_klog_window", "_connect"))
        self.assertNotIn("_ps5_port_finden", direkt)
        arbeiter = _direkte_aufrufe(self._innere("_show_klog_window", "worker"))
        self.assertIn("_ps5_port_finden", arbeiter)


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class BibliothekSendenOhneKonsoleTests(_TempTest):
    """Konsole aus: Das Programm bleibt bedienbar, die Meldung kommt trotzdem."""

    def test_verbindungsfehler_kommt_aus_dem_faden(self) -> None:
        app = _app()
        datei = _schreiben(os.path.join(self.basis, "Spiel.ffpfsc"), b"x" * 64)
        fenster = tk.Toplevel(_WURZEL)
        fenster.withdraw()
        self.addCleanup(fenster.destroy)
        verbunden: list = []
        fehler: list = []
        stand: list = []

        def _verbinden(host, port=0, *_a, **_k):
            verbunden.append(threading.current_thread() is threading.main_thread())
            raise OSError("Zeitueberschreitung (Attrappe)")

        einstellungen = {"ps5_ip": "192.0.2.1"}
        with mock.patch.object(app, "_ampr_ftp_connect", _verbinden), \
                mock.patch.object(app, "_load_setting",
                                  lambda k, d=None: einstellungen.get(k, d)), \
                mock.patch.object(APP.messagebox, "showerror",
                                  lambda *a, **k: fehler.append(a)):
            app._bibliothek_hochladen(fenster, {"path": datei}, melden=stand.append)
            # Der Faden kann schon verbunden haben - aber nie im Hauptfaden.
            self.assertNotIn(True, verbunden, "Verbunden wird im Klick, nicht im Faden.")
            self.assertEqual(stand, [app._t("status.connecting")])
            # Ein zweiter Klick waehrend der Suche startet keine zweite.
            app._bibliothek_hochladen(fenster, {"path": datei}, melden=stand.append)
            BackportPlatzImFadenTests._in_schleife(lambda: bool(fehler))
        self.assertEqual(verbunden, [False])
        self.assertEqual(len(fehler), 1, fehler)
        self.assertIn("192.0.2.1", fehler[0][1])
        self.assertEqual(stand[-1], "", "Die Statuszeile bleibt auf 'Verbinde...' stehen.")
        self.assertFalse(getattr(fenster, "_ps5conv_ziele_suche", False))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class SammelPlatzTests(_TempTest):
    """Die Platzpruefung der Sammelkonvertierung rechnete nur mit der ersten Quelle."""

    def setUp(self) -> None:
        super().setUp()
        self.app = _app()
        self.quellen = []
        for nummer, mib in enumerate((1, 3, 2)):
            pfad = os.path.join(self.basis, "spiel%d.exfat" % nummer)
            with open(pfad, "wb") as fh:
                fh.truncate(mib * 1024 * 1024)
            self.quellen.append(pfad)
        vorher = list(getattr(self.app, "_batch_sources", []) or [])
        self.addCleanup(setattr, self.app, "_batch_sources", vorher)
        self.app._batch_sources = list(self.quellen)
        for name, wert in (("_integration_gewuenscht", lambda: False),
                           ("_dump_im_arbeitsordner", lambda: False)):
            patcher = mock.patch.object(self.app, name, wert)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _einzeln(self):
        return [self.app._platzbedarf_schaetzen("pack_file", q, "ffpkg")
                for q in self.quellen]

    def test_ziel_ist_die_summe_temp_das_groesste(self) -> None:
        einzeln = self._einzeln()
        temp, ziel = self.app._platzbedarf_schaetzen(
            "batch_convert", self.quellen[0], "ffpkg")
        self.assertEqual(ziel, sum(z for _t, z in einzeln),
                         "Das Ziel nimmt alle Ergebnisse nacheinander auf.")
        self.assertEqual(temp, max(t for t, _z in einzeln))

    def test_der_dump_ordner_zaehlt_nur_einmal(self) -> None:
        """Beim Neu-Packen wird er je Datei wieder geloescht."""
        self.app._umhuellt_neu_packen = True
        self.addCleanup(setattr, self.app, "_umhuellt_neu_packen", False)
        _temp, ziel = self.app._platzbedarf_schaetzen(
            "batch_convert", self.quellen[0], "ffpkg")
        teile = [self.app._platzbedarf_je_quelle(q, "ffpkg") for q in self.quellen]
        self.assertEqual(ziel, sum(z for _t, z, _d in teile) + max(d for _t, _z, d in teile))

    def test_im_feld_steht_der_ordner(self) -> None:
        """Aus einem Ordner aufgeloest: Gerechnet wird mit den Dateien darin."""
        _temp, ziel = self.app._platzbedarf_schaetzen(
            "batch_convert", self.basis, "ffpkg")
        self.assertEqual(ziel, sum(z for _t, z in self._einzeln()))


class AbschlussMessungTests(unittest.TestCase):
    """Am Aufgabenende wurde ein Ordner-Ergebnis zweimal vermessen.

    Zuerst meldend und abbrechbar, direkt danach ein zweites Mal ueber
    denselben Pfad - stumm, ohne Abbruch, und dessen Ergebnis galt. In der
    Sammelkonvertierung war der Pfad der ganze Zielordner: Alles, was dort
    sonst lag, wurde mitgemessen, als Ergebnisgroesse angezeigt und noch
    einmal durchlaufen.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.methode = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))),
                               "_run_engine_thread")
        cls.eltern = {}
        for knoten in ast.walk(cls.methode):
            for kind in ast.iter_child_nodes(knoten):
                cls.eltern[kind] = knoten

    def _aufrufe(self, name: str) -> list:
        return [k for k in ast.walk(self.methode)
                if isinstance(k, ast.Call) and getattr(k.func, "attr", "") == name]

    def _nur_ohne_sammel(self, knoten) -> bool:
        """Liegt der Knoten im else-Zweig eines ``if sammel:``?"""
        kind, oben = knoten, self.eltern.get(knoten)
        while oben is not None:
            if (isinstance(oben, ast.If) and isinstance(oben.test, ast.Name)
                    and oben.test.id == "sammel" and kind in oben.orelse):
                return True
            kind, oben = oben, self.eltern.get(oben)
        return False

    def test_nur_die_meldende_messung(self) -> None:
        self.assertEqual([k.lineno for k in self._aufrufe("_get_path_size")], [],
                         "Stumme Messung ohne Abbruch am Aufgabenende.")
        self.assertTrue(self._aufrufe("_quellgroesse_mit_meldung"))

    def test_die_sammelkonvertierung_misst_nicht_den_zielordner(self) -> None:
        ueber_ziel = [k for k in self._aufrufe("_quellgroesse_mit_meldung")
                      if "task_final_output_path" in ast.unparse(k)]
        self.assertTrue(ueber_ziel)
        for k in ueber_ziel:
            with self.subTest(zeile=k.lineno):
                self.assertTrue(self._nur_ohne_sammel(k),
                                "Zeile %d laeuft auch in der Sammelkonvertierung - "
                                "dort ist das der ganze Zielordner." % k.lineno)

    def test_geprueft_wird_nur_ueber_die_abschlusspruefung(self) -> None:
        """Nach Erfolg, Abbruch, Fehlschlag und Ausnahme - vier Stellen."""
        self.assertEqual([k.lineno for k in self._aufrufe("_verify_output_artifact")], [])
        self.assertGreaterEqual(len(self._aufrufe("_abschlusspruefung")), 4)

    def test_die_abschlusspruefung_der_sammlung_laeuft_nicht_ueber_den_ordner(self) -> None:
        gui = GUI.__new__(GUI)
        gui._t = lambda schluessel, **werte: "%s %s" % (schluessel, werte)
        gerufen: list = []
        gui._verify_output_artifact = lambda *a: gerufen.append(a) or {"ok": True}
        gui.task_batch_results = [
            {"source": "a", "output": "a.ffpfsc", "ok": True, "detail": "ok"},
            {"source": "b", "output": "", "ok": False, "skipped": True, "detail": "da"},
        ]
        ergebnis = gui._abschlusspruefung("batch_convert", r"D:\Spiele")
        self.assertEqual(gerufen, [], "Der Zielordner wurde doch durchlaufen.")
        self.assertTrue(ergebnis["ok"])
        self.assertIn("'count': 1", ergebnis["detail"])
        # Ein echter Fehlschlag nennt seinen Grund, nicht die Ordnerzaehlung.
        gui.task_batch_results.append(
            {"source": "c", "output": "", "ok": False, "detail": "MkPFS-Strukturfehler"})
        ergebnis = gui._abschlusspruefung("batch_convert", r"D:\Spiele")
        self.assertFalse(ergebnis["ok"])
        self.assertEqual(ergebnis["detail"], "MkPFS-Strukturfehler")
        # Ausserhalb der Sammlung bleibt alles beim Alten.
        gui._abschlusspruefung("pack_folder", r"D:\Spiele\x.ffpfsc")
        self.assertEqual(gerufen, [("pack_folder", r"D:\Spiele\x.ffpfsc")])


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class Aufgabe2WiederaufnahmeTests(_TempTest):
    """Die angebotene Wiederaufnahme von Aufgabe 2 konnte nicht gelingen."""

    def setUp(self) -> None:
        super().setUp()
        self.app = _app()
        self.tmp = self.app._mkdtemp(prefix="ps5conv_exfat_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _abbild(self, pfad: str) -> str:
        kopf = bytearray(4096)
        kopf[3:11] = GUI._INNER_EXFAT_SIGNATURE
        return _schreiben(pfad, bytes(kopf))

    def _angebot(self, stufe: str, **weiter) -> bool:
        return self.app._checkpoint_supports_resume(
            "unpack_to_exfat", dict(stage=stufe, tmp_dir=self.tmp, **weiter))

    def test_ohne_wiederverwendbares_wird_nichts_angeboten(self) -> None:
        self._abbild(os.path.join(self.tmp, "inner.img"))
        self.assertFalse(self._angebot("task2_start"))
        self.assertFalse(self._angebot("task2_step1_running"))
        self.assertTrue(self._angebot("task2_step1_done"))
        # Angefangenes _ebene_ neben dem Abbild: verwerfbar.
        _schreiben(os.path.join(self.tmp, "_ebene_1", "halb.bin"))
        self.assertTrue(self._angebot("task2_step1_done"))
        # Abbild schon weg: Stand unklar.
        os.remove(os.path.join(self.tmp, "inner.img"))
        self.assertFalse(self._angebot("task2_step1_done"))
        self.assertFalse(self._angebot("task2_step2_done",
                                       game_dump_dir=os.path.join(self.tmp, "fehlt")))
        self.assertTrue(self._angebot("task2_step2_done",
                                      game_dump_dir=os.path.join(self.tmp, "_ebene_1")))

    def _lauf(self, stufe: str) -> dict:
        quelle = _schreiben(os.path.join(self.basis, "Spiel.ffpfsc"), b"\0" * 4096)
        ziel = os.path.join(self.basis, "ziel")
        gesehen: dict = {}

        def _mkpfs(argumente, **_k):
            gesehen["mkpfs"] = sorted(os.listdir(self.tmp))
            return False                              # Lauf hier beenden

        def _ebenen(ordner, **_k):
            gesehen["ebenen"] = sorted(os.listdir(ordner))
            return None                               # Lauf hier beenden

        vorher = getattr(self.app, "_active_resume_checkpoint", None)
        self.addCleanup(setattr, self.app, "_active_resume_checkpoint", vorher)
        self.app._active_resume_checkpoint = {"stage": stufe, "tmp_dir": self.tmp}
        laeuft = self.app.is_running
        self.addCleanup(setattr, self.app, "is_running", laeuft)
        self.app.is_running = True
        with mock.patch.object(self.app, "_execute_mkpfs", _mkpfs), \
                mock.patch.object(self.app, "_entpacke_container_ebenen", _ebenen), \
                mock.patch.object(self.app, "_append_to_log", lambda *_a: None), \
                mock.patch.object(self.app, "_save_runtime_checkpoint", lambda **_k: None):
            self.assertFalse(self.app._mode_unpack_to_exfat(quelle, ziel))
        _WURZEL.update()
        return gesehen

    def test_schritt2_beginnt_ohne_das_angefangene_ebene(self) -> None:
        self._abbild(os.path.join(self.tmp, "inner.img"))
        _schreiben(os.path.join(self.tmp, "_ebene_1", "halb.bin"))
        gesehen = self._lauf("task2_step1_done")
        self.assertNotIn("mkpfs", gesehen, "Schritt 1 lief erneut.")
        self.assertEqual(gesehen.get("ebenen"), ["inner.img"])

    def test_ein_neuer_schritt1_beginnt_im_leeren_ordner(self) -> None:
        _schreiben(os.path.join(self.tmp, "halb_geschrieben.img"), b"x" * 100)
        gesehen = self._lauf("task2_step1_running")
        self.assertEqual(gesehen.get("mkpfs"), [],
                         "mkpfs unpack laeuft in den halb gefuellten Ordner.")


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class DiagnoseAbschnitteTests(unittest.TestCase):
    """Die Abschnitte des Diagnoseberichts laufen - nicht nur ihre Ueberschriften.

    Die bisherigen Pruefungen (test_anzeige_diagnose, test_fortschrittsbalken,
    test_doktor) bauten ein nacktes ``Diagnosebericht()`` und suchten nur den
    Ueberschriftsschluessel: Der steht immer da, auch wenn der Bauer fehlt
    oder wirft - ``bericht_text()`` faengt jede Ausnahme ab und vermerkt nur
    "Abschnitt fehlgeschlagen" (Befund T6, 17.09.2026). Gemessen am echten
    Programm: alle 12 Abschnitte laufen.

    Die feste Zahl ist Absicht: Ein neuer Abschnitt braucht **zwei**
    Eintragungen (``ABSCHNITTE`` und die Weiterleitung im Hauptmodul), und wer
    die zweite vergisst, merkt es sonst nie - der Bericht ueberspringt einen
    unbekannten Bauer stillschweigend. Wer hier die Zahl hochsetzt, hat also
    gerade nachzusehen, ob beide Stellen stimmen. Am 17.09.2026 kam
    "Werkzeugpflege" dazu (11 -> 12).
    """

    def test_jeder_bauer_laeuft_und_liefert_inhalt(self) -> None:
        bericht = _app()._diagnosebericht()
        self.assertEqual(len(bericht.ABSCHNITTE), 12)
        fehlend, gescheitert, leer = [], [], []
        for _schluessel, name in bericht.ABSCHNITTE:
            bauer = bericht._bauer_holen(name)
            if bauer is None:
                fehlend.append(name)
                continue
            try:
                zeilen = bauer()
            except Exception as exc:  # noqa: BLE001
                gescheitert.append("%s: %s" % (name, exc))
                continue
            if not [z for z in zeilen if str(z).strip()]:
                leer.append(name)
        self.assertEqual({"fehlend": fehlend, "gescheitert": gescheitert, "leer": leer},
                         {"fehlend": [], "gescheitert": [], "leer": []})


class VermessenMitAbbruchTests(unittest.TestCase):
    """Jede Groessenmessung braucht einen Abbruch (T32, 17.09.2026).

    Der alte Waechter (test_teilschritt_fortschritt) suchte zwei woertliche
    Altzeilen. Dabei blieben zwei blanke Messungen unentdeckt:
    ``_execute_mkpfs`` vermass jeden Quellordner vor dem Packen noch einmal
    (51 GB auf USB: 37 min, ohne Meldung und ohne Abbruch), und die Vorschau
    zaehlte nach einem Quellwechsel weiter.
    """

    #: Begruendete Ausnahmen: die Messung selbst, die meldende Huelle, die
    #: BACKPORT-Platzmessung (dort haengt kein is_running, siehe Docstring)
    #: und die Beobachter, die alle 2 s den wachsenden Zielordner zaehlen.
    ERLAUBT = {"_get_path_size", "_backport_platz_messen", "_poll"}

    def test_kein_aufruf_ohne_abbruch(self) -> None:
        klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        eltern = {}
        for knoten in ast.walk(klasse):
            for kind in ast.iter_child_nodes(knoten):
                eltern[kind] = knoten
        funde, gesehen = [], 0
        for k in ast.walk(klasse):
            if not (isinstance(k, ast.Call) and getattr(k.func, "attr", "") == "_get_path_size"):
                continue
            gesehen += 1
            if any(s.arg == "cancel_check" for s in k.keywords):
                continue
            oben, kette = eltern.get(k), []
            while oben is not None and oben is not klasse:
                if isinstance(oben, ast.FunctionDef):
                    kette.append(oben.name)
                oben = eltern.get(oben)
            if not (set(kette) & self.ERLAUBT):
                funde.append("%s Z.%d" % (" < ".join(kette), k.lineno))
        self.assertGreaterEqual(gesehen, 6, "Die Pruefung findet die Aufrufe nicht mehr.")
        self.assertEqual(funde, [])

    @unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
    def test_die_meldende_messung_merkt_sich_ihr_ergebnis_fuer_die_aufgabe(self) -> None:
        app = _app()
        ordner = tempfile.mkdtemp(prefix="dbg_messen_")
        self.addCleanup(shutil.rmtree, ordner, True)
        _schreiben(os.path.join(ordner, "a.bin"), b"x" * 5000)
        laeuft = app.is_running
        self.addCleanup(setattr, app, "is_running", laeuft)
        app._gemessene_groessen = {}
        schluessel = os.path.normcase(os.path.abspath(ordner))
        app.is_running = False                       # abgebrochen: Teilwert
        app._quellgroesse_mit_meldung(ordner)
        self.assertNotIn(schluessel, app._gemessene_groessen)
        app.is_running = True
        self.assertEqual(app._quellgroesse_mit_meldung(ordner), 5000)
        self.assertEqual(app._gemessene_groessen.get(schluessel), 5000)


class ParameterTexteTests(unittest.TestCase):
    """Deutsche Texte gelangten ueber Parameter am Sprachleck-Waechter vorbei.

    test_sprachlecks sieht feste Texte in den sichtbaren Aufrufen selbst.
    "Aufgabe 7", "FFPKG-Extraktion", "exFAT extrahiert" oder "Schritt 1 nicht
    abgeschlossen" kamen aber als Argument herein und standen bei englischer
    Oberflaeche trotzdem in Statuszeile und Protokoll.
    """

    def test_praefixe_und_abbruchgruende_sind_uebersetzt(self) -> None:
        klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        funde, gesehen = [], 0

        def _fester_text(knoten) -> bool:
            if isinstance(knoten, ast.JoinedStr):
                return True
            return isinstance(knoten, ast.Constant) and isinstance(knoten.value, str) \
                and bool(knoten.value.strip())

        for k in ast.walk(klasse):
            if not isinstance(k, ast.Call):
                continue
            for schluessel in k.keywords:
                if schluessel.arg in ("status_prefix", "log_prefix"):
                    gesehen += 1
                    if _fester_text(schluessel.value):
                        funde.append("%s= Z.%d" % (schluessel.arg, k.lineno))
            if getattr(k.func, "id", "") == "_fail_keep_tmp" and k.args \
                    and _fester_text(k.args[0]):
                funde.append("_fail_keep_tmp Z.%d" % k.lineno)
        self.assertGreater(gesehen, 10, "Die Pruefung findet die Aufrufe nicht mehr.")
        self.assertEqual(funde, [])

    def test_praefix_und_text_bekommen_einen_trenner(self) -> None:
        """Bis v1.9.24 klebten sie zusammen: "FFPKG-RepackEntpacke ..."."""
        self.assertEqual(GUI._mit_praefix("FFPKG-Repack", "Entpacke"),
                         "FFPKG-Repack – Entpacke")
        self.assertEqual(GUI._mit_praefix("Aufgabe 4 - ", "x"), "Aufgabe 4 - x")
        self.assertEqual(GUI._mit_praefix("", "x"), "x")

    def test_die_neuen_schluessel_gibt_es_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("status.prefix_ffpkg_repack", "status.prefix_ffpkg_extraktion",
                           "status.prefix_abbild_pkg", "status.laufzeit",
                           "log.robocopy_fehlgeschlagen", "ffpkg.mount_fehlgeschlagen",
                           "task2.grund_schritt1", "resources.dotnet_download"):
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel].get("de"))
                self.assertTrue(STRINGS[schluessel].get("en"))
                self.assertNotEqual(STRINGS[schluessel]["de"], STRINGS[schluessel]["en"])


class DoktorFremdbauTests(_TempTest):
    """--doktor meldete auf Mac und Linux Programme als defekt, die in Ordnung sind."""

    def test_nur_der_ufs2tool_bau_dieser_maschine_wird_gestartet(self) -> None:
        kennung = b"MZ\x90\x00" if sys.platform == "win32" else b"\x7fELF"
        for bau in ("win-x64", "linux-x64", "osx-arm64"):
            pfad = _schreiben(os.path.join(self.basis, "UFS2Tool-4.1", bau, "UFS2Tool"),
                              kennung + b"\0" * 64)
            os.chmod(pfad, 0o755)
        gestartet: list = []

        def _lauf(befehl, **_k):
            gestartet.append(os.path.basename(os.path.dirname(befehl[0])))
            return mock.Mock(returncode=0)

        eigener = "win-x64" if sys.platform == "win32" else "linux-x64"
        with mock.patch.object(GUI, "_mitgeliefert_finden",
                               staticmethod(lambda rel: os.path.join(self.basis, rel))), \
                mock.patch.object(GUI, "_ufs2tool_plattform", staticmethod(lambda: eigener)), \
                mock.patch.object(APP, "_doktor_passt_architektur", lambda _p: True), \
                mock.patch.object(APP.subprocess, "run", _lauf):
            APP._doktor_werkzeuge_starten()
        self.assertEqual(gestartet, [eigener])

    def test_eine_fremde_architektur_ist_kein_programm_fuer_diesen_rechner(self) -> None:
        macho_arm = _schreiben(os.path.join(self.basis, "arm"),
                               b"\xcf\xfa\xed\xfe" + (0x0100000C).to_bytes(4, "little") + b"\0" * 12)
        elf_x64 = _schreiben(os.path.join(self.basis, "x64"),
                             b"\x7fELF" + b"\0" * 14 + (0x3E).to_bytes(2, "little"))
        windows = _schreiben(os.path.join(self.basis, "win.exe"), b"MZ" + b"\0" * 30)
        with mock.patch.object(APP.platform, "machine", lambda: "x86_64"):
            self.assertFalse(APP._doktor_passt_architektur(macho_arm))
            self.assertTrue(APP._doktor_passt_architektur(elf_x64))
            self.assertTrue(APP._doktor_passt_architektur(windows))
        with mock.patch.object(APP.platform, "machine", lambda: "arm64"):
            self.assertTrue(APP._doktor_passt_architektur(macho_arm))
            self.assertFalse(APP._doktor_passt_architektur(elf_x64))

    def test_ohne_ausfuehrungsrecht_wird_nicht_gestartet(self) -> None:
        """Das Recht setzt das Programm vor dem Einsatz selbst - kein Defekt."""
        pfad = _schreiben(os.path.join(self.basis, "PS4FFPFSC-0.2.9", "bin", "helfer"),
                          b"MZ" + b"\0" * 30)
        gestartet: list = []
        with mock.patch.object(GUI, "_mitgeliefert_finden",
                               staticmethod(lambda rel: os.path.join(self.basis, rel))), \
                mock.patch.object(GUI, "_ufs2tool_plattform", staticmethod(lambda: "")), \
                mock.patch.object(APP.sys, "platform", "linux"), \
                mock.patch.object(APP, "_doktor_ist_programm", lambda p: p == pfad), \
                mock.patch.object(APP.os, "access", lambda *_a: False), \
                mock.patch.object(APP.subprocess, "run",
                                  lambda befehl, **_k: gestartet.append(befehl) or mock.Mock(returncode=0)):
            befunde, _rechte = APP._doktor_werkzeuge_starten()
        self.assertEqual(gestartet, [])
        self.assertEqual(befunde, [])


class RegionTests(unittest.TestCase):
    """Die Region kam aus dem Title-ID-Praefix - PPSA hiess immer "Europa"."""

    def _leser(self):
        from ps5_validator.utils.abbild_metadaten import Metadatenleser
        return Metadatenleser.__new__(Metadatenleser)

    def test_param_json_nimmt_die_content_id(self) -> None:
        leser = self._leser()
        for content_id, erwartet in (("UP9000-PPSA01234_00-TESTSPIEL0000000", "USA"),
                                     ("JP0700-PPSA01234_00-TESTSPIEL0000000", "Japan"),
                                     ("EP0001-PPSA01234_00-TESTSPIEL0000000", "Europa")):
            with self.subTest(content_id=content_id):
                meta = leser._meta_from_param_json_payload(
                    {"titleId": "PPSA01234", "contentId": content_id,
                     "localizedParameters": {"en-US": {"titleName": "Test"}}})
                self.assertEqual(meta["region"], erwartet)

    def test_ohne_content_id_bleibt_der_rueckfall(self) -> None:
        meta = self._leser()._meta_from_param_json_payload({"titleId": "PCJS12345"})
        self.assertEqual(meta["region"], "Japan")

    def test_param_sfo_nimmt_die_content_id(self) -> None:
        leser = self._leser()
        leser._sfo_leser = lambda _roh: {"TITLE_ID": "CUSA01234",
                                         "CONTENT_ID": "EP1234-CUSA01234_00-TESTSPIEL0000000"}
        self.assertEqual(leser._meta_from_param_sfo_bytes(b"x")["region"], "Europa")


class RueckschrittalarmTests(unittest.TestCase):
    """Der Rueckschrittalarm verglich Leseaufgaben mit Packlaeufen.

    Aufgabe 8 liest nur (NVMe: rund 1000 MB/s). Ihr Durchsatz wurde als
    Bestwert der Kompressionsstufe gespeichert, und jede spaetere
    Konvertierung meldete danach "ACHTUNG ... langsamer". Der Schluessel hing
    ausserdem am uebersetzten Namen der Stufe.
    """

    def _bericht(self, art, etikett="Schnell", bestwert=0.0):
        from ps5_validator.utils.diagnose_befund import Diagnosebericht

        abgelegt: dict = {}

        class _Stufe:
            get = staticmethod(lambda: etikett)

        bericht = Diagnosebericht(
            kompression=_Stufe(),
            einstellung_lesen=lambda k, d=None: bestwert or d,
            einstellung_schreiben=lambda k, v: abgelegt.__setitem__(k, v),
            letzte_dauer_s=10.0, quellbytes=100 * 1048576,
            letzte_aufgabe_art=art,
            kompressionsstufen={"Schnell": 3, "Fast": 3})
        return bericht, abgelegt

    def test_eine_leseaufgabe_setzt_keinen_bestwert(self) -> None:
        bericht, abgelegt = self._bericht(("dump_validator", ""))
        zeilen = bericht._diagnose_optimierung()
        self.assertEqual(abgelegt, {})
        self.assertTrue(any("Leseaufgabe" in z for z in zeilen), zeilen[:2])
        # Und schlaegt nicht an, auch wenn der Bestwert hoeher liegt.
        bericht, _ = self._bericht(("dump_validator", ""), bestwert=1000.0)
        self.assertFalse(any("ACHTUNG" in z for z in bericht._diagnose_optimierung()))

    def test_der_schluessel_haengt_an_aufgabe_ziel_und_stufe_nicht_an_der_sprache(self) -> None:
        deutsch, de = self._bericht(("pack_folder", "ffpfsc"), etikett="Schnell")
        deutsch._diagnose_optimierung()
        englisch, en = self._bericht(("pack_folder", "ffpfsc"), etikett="Fast")
        englisch._diagnose_optimierung()
        self.assertEqual(list(de), ["opt_durchsatz_pack_folder_ffpfsc_3"])
        self.assertEqual(list(de), list(en))

    def test_das_programm_reicht_die_art_des_laufs_durch(self) -> None:
        """Ohne diese Verdrahtung saehe der Bericht nie eine Aufgabe."""
        klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        lauf = _methode(klasse, "_run_engine_thread")
        gesetzt = [k for k in ast.walk(lauf) if isinstance(k, ast.Assign)
                   and any(getattr(z, "attr", "") == "_letzte_aufgabe_art" for z in k.targets)]
        self.assertTrue(gesetzt, "Das Aufgabenende merkt sich die Art des Laufs nicht.")
        bericht = _methode(klasse, "_diagnosebericht")
        uebergeben = {s.arg for k in ast.walk(bericht) if isinstance(k, ast.Call)
                      for s in k.keywords}
        self.assertIn("letzte_aufgabe_art", uebergeben)
        self.assertIn("kompressionsstufen", uebergeben)


class KommandozeileZielordnerTests(_TempTest):
    """Ein fehlendes oder falsches --dest endete mit 1 statt 2."""

    def _lauf(self, **argumente) -> int:
        import argparse

        dump = os.path.join(self.basis, "PPSA00001")
        _schreiben(os.path.join(dump, "eboot.bin"))
        werte = dict(mode="pack_folder", task=None, source=[dump], dest=None,
                     ampr_action=None, quiet=True)
        werte.update(argumente)
        with mock.patch.object(APP, "_prepare_cli_streams", lambda: None), \
                mock.patch.object(APP.tk, "Tk",
                                  side_effect=AssertionError("Fenster gebaut")):
            return APP._run_cli(argparse.Namespace(**werte))

    def test_ohne_dest_ist_es_ein_argumentfehler(self) -> None:
        self.assertEqual(self._lauf(), 2)

    def test_ein_fehlender_zielordner_ist_ein_argumentfehler(self) -> None:
        self.assertEqual(self._lauf(dest=os.path.join(self.basis, "gibts_nicht")), 2)

    def test_der_rueckgabewert_4_ist_dokumentiert(self) -> None:
        readme = (PROJEKT / "README.md").read_text(encoding="utf-8")
        zeile = readme[readme.index("Rückgabewerte: `0` Erfolg"):][:300]
        self.assertIn("`4`", zeile)


class BauskriptPaketeTests(unittest.TestCase):
    """Die Bauskripte fuer Linux und macOS installierten kein lz4.

    Die .spec-Dateien nennen es als hiddenimport, PyInstaller uebergeht ein
    fehlendes Modul aber still. Im frischen .venv-macos des CI fehlte es, und
    die AMPR-EMU-Methode Asset-Pack war im Mac-Buendel nie verfuegbar.
    Gemessen wird gegen Build_EXE.ps1: Was Windows installiert, brauchen die
    anderen Bauten auch.
    """

    def test_linux_und_macos_installieren_dieselben_pakete_wie_windows(self) -> None:
        windows = set(re.findall(r"-m pip install ([A-Za-z0-9_.-]+) --upgrade",
                                 (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")))
        windows.discard("pip")
        self.assertIn("lz4", windows, "Die Auswertung von Build_EXE.ps1 misst nichts mehr.")
        for skript in ("Build_Linux.sh", "Build_macOS.sh"):
            with self.subTest(skript=skript):
                text = (PROJEKT / skript).read_text(encoding="utf-8")
                dort = set(re.findall(r"^(?:pflicht|optional)_installieren ([A-Za-z0-9_.-]+)",
                                      text, re.M))
                self.assertEqual(sorted(windows - dort), [],
                                 "%s installiert nicht, was die .spec braucht." % skript)


class BauskriptHinweisTests(unittest.TestCase):
    """Der Schlusshinweis der Bauskripte nannte UFS2Tool "nur unter Windows".

    Seit v1.8.72 liegt UFS2Tool fuer alle drei Systeme bei (README,
    Plattformunterschiede). Build_Linux.sh und Build_macOS.sh meldeten nach
    jedem Bau trotzdem, Aufgaben mit UFS2Tool liefen nur unter Windows.
    """

    EINSCHRAENKUNG = re.compile(r"(?:nur|ausschlie(?:ss|ß)lich) unter Windows", re.I)

    @staticmethod
    def _saetze(text: str) -> list:
        """Die Saetze aus aufeinanderfolgenden ``meldung``-Zeilen."""
        absaetze, laufend = [], []
        for zeile in text.splitlines():
            treffer = re.match(r'\s*meldung "([^"]*)"', zeile)
            if treffer:
                laufend.append(treffer.group(1).strip())
            elif laufend:
                absaetze.append(" ".join(laufend))
                laufend = []
        if laufend:
            absaetze.append(" ".join(laufend))
        saetze = []
        for absatz in absaetze:
            saetze.extend(re.split(r"(?<=[.;])\s+", re.sub(r"\s+", " ", absatz)))
        return saetze

    def test_windows_einschraenkung_nennt_kein_ffpkg_werkzeug(self) -> None:
        for skript in ("Build_Linux.sh", "Build_macOS.sh"):
            with self.subTest(skript=skript):
                text = (PROJEKT / skript).read_text(encoding="utf-8")
                einschraenkungen = [s for s in self._saetze(text) if self.EINSCHRAENKUNG.search(s)]
                self.assertTrue(einschraenkungen,
                                "%s: kein Windows-Hinweis mehr gefunden - die Pruefung misst nichts." % skript)
                for satz in einschraenkungen:
                    self.assertNotIn("UFS2Tool", satz, "%s: %s" % (skript, satz))
                    self.assertNotIn(".ffpkg", satz, "%s: %s" % (skript, satz))


@unittest.skipUnless(TK_DA, "Keine Anzeige verfügbar")
class WebkitFensterMessungTests(unittest.TestCase):
    """SCHLIESSEN darf nicht auf dem letzten Wege-Knopf liegen - gemessen.

    Befund T14: test_fensterknoepfe rechnete die Fensterhoehe im Test nach
    und verglich die Rechnung mit sich selbst; das Fenster wurde nie gebaut.
    Hier wird es gebaut und die Lage der Knoepfe auf der Leinwand gelesen.
    """

    def _kaesten(self, mit_bild: bool) -> tuple:
        app = _app()
        bild = tk.PhotoImage(master=_WURZEL, width=8, height=8) if mit_bild else None
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        with mock.patch.object(app, "_webkit_bild_laden", lambda: bild):
            app._show_webkit_autoloader()
        fenster = [w for w in _WURZEL.winfo_children()
                   if str(w) not in vorher and isinstance(w, tk.Toplevel)][-1]
        self.addCleanup(fenster.destroy)
        leinwand = [w for w in fenster.winfo_children() if w.winfo_class() == "Canvas"][0]
        kaesten = sorted((leinwand.bbox(eintrag) for eintrag in leinwand.find_all()
                          if leinwand.type(eintrag) == "window"), key=lambda k: k[1])
        return kaesten, int(leinwand.cget("height"))

    def test_schliessen_liegt_unter_den_wegen_und_im_fenster(self) -> None:
        for mit_bild in (True, False):
            with self.subTest(bild=mit_bild):
                kaesten, hoehe = self._kaesten(mit_bild)
                self.assertEqual(len(kaesten), 4, "Drei Wege und SCHLIESSEN erwartet.")
                *wege, schliessen = kaesten
                self.assertLess(wege[-1][3], schliessen[1],
                                "SCHLIESSEN liegt auf dem letzten Wege-Knopf.")
                self.assertLessEqual(schliessen[3], hoehe, "SCHLIESSEN ragt aus dem Fenster.")


class MenueGrabTests(unittest.TestCase):
    """WEITERE TOOLS und das Kontextmenue klappten mit ``Menu.post`` auf.

    Gemessen am 17.09.2026 unter X11 (WSLg): ``post`` setzt keinen Grab,
    ``tk_popup`` legt ihn auf das Menue. Ohne Grab schloss ein Klick daneben
    das Menue nicht, und die Tastatur erreichte es nicht.
    """

    def test_kein_menue_klappt_mehr_mit_post_auf(self) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        posts = [k.lineno for k in ast.walk(baum)
                 if isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)
                 and k.func.attr == "post"]
        self.assertEqual(posts, [], "Menu.post setzt unter X11 keinen Grab.")
        rufer = {f.name for f in ast.walk(baum) if isinstance(f, ast.FunctionDef)
                 and any(isinstance(c, ast.Call) and getattr(c.func, "attr", "") == "_menue_aufklappen"
                         for c in ast.walk(f))}
        self.assertLessEqual({"_show_context_menu", "_show_more_tools_menu"}, rufer)

    def test_der_grab_wird_auch_nach_einem_fehler_freigegeben(self) -> None:
        aufrufe: list = []

        class _Menue:
            def tk_popup(self, x, y) -> None:
                aufrufe.append(("aufklappen", x, y))
                raise RuntimeError("Fenster weg")

            def grab_release(self) -> None:
                aufrufe.append(("freigeben",))

        with self.assertRaises(RuntimeError):
            GUI._menue_aufklappen(_Menue(), 3, 4)
        self.assertEqual(aufrufe, [("aufklappen", 3, 4), ("freigeben",)])


class FensterklasseTests(unittest.TestCase):
    """``StartupWMClass`` im Linux-Starter traf nie.

    Gemessen am 17.09.2026 unter X11 (WSLg): Ohne ``className`` traegt jedes
    Tk-Fenster WM_CLASS ("tk", "Tk") - der Starter nannte
    "PS5ImageConverter_Pro_FINAL_revised". Mit ``className`` schreibt Tk die
    Klasse mit grossem ersten und kleinem Rest.
    """

    def test_linux_starter_nennt_die_klasse_des_hauptfensters(self) -> None:
        klasse = APP.TK_KLASSENNAME
        erwartet = klasse[:1].upper() + klasse[1:].lower()
        starter = (PROJEKT / "Install_Linux.sh").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r"^StartupWMClass=(.*)$", starter, re.M), [erwartet])

    def test_das_hauptfenster_bekommt_den_klassennamen(self) -> None:
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        start = next(k for k in baum.body if isinstance(k, ast.If)
                     and "__main__" in ast.unparse(k.test))
        erzeugt = [k for k in ast.walk(start) if isinstance(k, ast.Call)
                   and ast.unparse(k.func) in ("tk.Tk", "TkinterDnD.Tk")]
        self.assertTrue(erzeugt, "Die Messung findet das Hauptfenster nicht mehr.")
        for aufruf in erzeugt:
            with self.subTest(aufruf=ast.unparse(aufruf)):
                self.assertIn("className=TK_KLASSENNAME", ast.unparse(aufruf))


class MacUfs2toolBauTests(unittest.TestCase):
    """Build_macOS.sh misst UFS2Tool vor und nach dem Signieren.

    PyInstaller 6 stuft Mach-O-Dateien aus ``datas`` als Programmdateien ein
    und signiert sie neu (``codesign --force``, gelesen in PyInstaller 6.22.3).
    Aendert das die Pruefsumme, lehnt die Mac-App UFS2Tool ab und jede
    .ffpkg-Aufgabe scheitert - der CI-Lauf prueft das im Buendel nirgends.
    Das Verhalten der Helfer steht in test_werkzeuge_bereitstellen.MacBuendelTests.
    """

    def setUp(self) -> None:
        self.text = (PROJEKT / "Build_macOS.sh").read_text(encoding="utf-8")

    def _stelle(self, muster: str) -> int:
        treffer = re.search(muster, self.text, re.M)
        self.assertIsNotNone(treffer, "nicht gefunden: %s" % muster)
        return treffer.start()

    def test_reihenfolge_quelle_bau_signatur_nachtrag_pruefung(self) -> None:
        quelle = self._stelle(r"w\.ufs2tool_quelle_pruefen\(")
        bau = self._stelle(r"-m PyInstaller PS5ImageConverter_Pro_macos\.spec")
        signatur = self._stelle(r"codesign --force --deep --sign -")
        nachtrag = self._stelle(r"w\.ufs2tool_buendel_nachtragen\(")
        neu_versiegelt = self.text.find("codesign --force --deep --sign -", nachtrag)
        pruefung = self._stelle(r"w\.ufs2tool_buendel_pruefen\(")
        abbild = self._stelle(r"^GROESSE=")
        self.assertLess(quelle, bau, "Die Quelle muss vor PyInstaller geprueft werden.")
        self.assertLess(bau, signatur)
        self.assertLess(signatur, nachtrag, "Nachgemessen wird erst nach dem Signieren.")
        self.assertTrue(nachtrag < neu_versiegelt < pruefung,
                        "Nach dem Nachtrag muss neu versiegelt und danach geprueft werden.")
        self.assertLess(pruefung, abbild, "Die Pruefung gehoert vor Groesse und Abbild.")

    def test_die_gerufenen_helfer_gibt_es(self) -> None:
        from ps5_validator.utils import werkzeuge_bereitstellen as wb

        namen = set(re.findall(r"\bw\.(\w+)\(", self.text))
        self.assertGreaterEqual(namen, {"ufs2tool_quelle_pruefen", "ufs2tool_buendel_nachtragen",
                                        "ufs2tool_buendel_pruefen"})
        for name in sorted(namen):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(wb, name, None)), name)

    def test_geprueft_werden_die_bauten_der_spec(self) -> None:
        spec = (PROJEKT / "PS5ImageConverter_Pro_macos.spec").read_text(encoding="utf-8")
        eingebettet = set(re.findall(r"'(osx-[a-z0-9]+)'",
                                     re.search(r"for _ziel in \[([^\]]*)\]", spec).group(1)))
        self.assertEqual(eingebettet, {"osx-arm64", "osx-x64"})
        aufrufe = re.findall(r'\(("osx-[a-z0-9]+"(?:\s*,\s*"osx-[a-z0-9]+")*)\)', self.text)
        self.assertEqual(len(aufrufe), 2, "Quelle und Buendel nennen die Bauten je einmal.")
        for aufruf in aufrufe:
            with self.subTest(aufruf=aufruf):
                self.assertEqual(set(re.findall(r'"([^"]+)"', aufruf)), eingebettet)


class BalkenRohwertTests(unittest.TestCase):
    """Rohwerte direkt auf dem Balken liessen ihn springen.

    Nur zwei Stellen duerfen ``_set_progress`` mit einer Zahl rufen: der
    Anzeigetakt selbst und das Ruecksetzen beim Start. Alle anderen melden
    ueber ``task_progress``/``_teilschritt_melden`` oder mit ``None``.
    """

    ERLAUBT = {"_update_progress_gui", "_launch_task"}

    def test_niemand_sonst_setzt_eine_zahl(self) -> None:
        klasse = _klasse(ast.parse(HAUPTDATEI.read_text(encoding="utf-8")))
        verstoesse, gesehen = [], 0
        for methode in klasse.body:
            if not isinstance(methode, ast.FunctionDef):
                continue
            for k in ast.walk(methode):
                if not (isinstance(k, ast.Call)
                        and getattr(k.func, "attr", "") == "_set_progress"):
                    continue
                gesehen += 1
                erstes = k.args[0] if k.args else None
                if isinstance(erstes, ast.Constant) and erstes.value is None:
                    continue
                if methode.name not in self.ERLAUBT:
                    verstoesse.append("%s Z.%d" % (methode.name, k.lineno))
        self.assertGreaterEqual(gesehen, 3, "Die Pruefung findet keine Aufrufe mehr.")
        self.assertEqual(verstoesse, [])


class AbbildPkgPlatzTests(_TempTest):
    """"Abbild -> PKG" rechnete mit der Dateigroesse statt mit dem Dump.

    Gemessen am 17.09.2026: 8,39 MB Dump -> 1,00 MB .ffpfsc; verlangt wurden
    1,15 MB im Arbeits- und 1,47 MB im Zielordner.
    """

    def test_eine_komprimierte_ffpfsc_braucht_den_platz_des_dumps(self) -> None:
        import subprocess

        dump = os.path.join(self.basis, "PPSA12345")
        _schreiben(os.path.join(dump, "sce_sys", "param.json"), b'{"titleId":"PPSA12345"}')
        for i in range(4):
            _schreiben(os.path.join(dump, "daten%d.bin" % i), b"\0" * (1024 * 1024))
        dump_bytes = sum(os.path.getsize(os.path.join(w, f))
                         for w, _d, namen in os.walk(dump) for f in namen)
        abbild = os.path.join(self.basis, "Spiel.ffpfsc")
        lauf = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "folder", "--raw",
             "--no-adjust-output-file-extension", "--version", "PS5",
             "--inode-bits", "32", "--block-size", "65536", dump, abbild],
            capture_output=True, cwd=str(PROJEKT / "MkPFS-1.0.0"), timeout=300)
        self.assertEqual(lauf.returncode, 0, lauf.stderr.decode("utf-8", "replace")[-500:])
        # Ohne Kompression misst der Test nichts.
        self.assertLess(os.path.getsize(abbild), dump_bytes // 2)

        gui = GUI.__new__(GUI)
        gui._extract_embedded_mkpfs = lambda: str(PROJEKT / "MkPFS-1.0.0")
        arbeit, ziel = gui._abbild_pkg_platzbedarf(abbild)
        self.assertGreaterEqual(arbeit, dump_bytes, "Der entpackte Dump passt nicht hinein.")
        self.assertGreaterEqual(ziel, dump_bytes, "Das Paket aus dem Dump passt nicht hinein.")

    def test_ein_exfat_abbild_bleibt_bei_der_dateigroesse(self) -> None:
        """Gegenrichtung: Unkomprimiert ist der Dump so gross wie die Datei."""
        pfad = os.path.join(self.basis, "Spiel.exfat")
        with open(pfad, "wb") as fh:
            fh.truncate(10 * 1024 * 1024)
        gui = GUI.__new__(GUI)
        arbeit, ziel = gui._abbild_pkg_platzbedarf(pfad)
        self.assertEqual((arbeit, ziel), (int(10 * 1024 * 1024 * 1.1),
                                          int(10 * 1024 * 1024 * 1.4)))


# ---------------------------------------------------------------------------
# AMPR EMU Asset-Pack gegen die Anleitung des Entwicklers (17.09.2026)
# ---------------------------------------------------------------------------

def _index_saetze(pfad: str) -> list:
    """Die Pfade eines AMPRIDX3 in Satzreihenfolge (Satznummer = fileId - 1)."""
    import struct
    with open(pfad, "rb") as fh:
        daten = fh.read()
    kopf, satz = struct.Struct("<8sIIQQQII"), struct.Struct("<IIQq")
    anzahl = kopf.unpack_from(daten, 0)[3]
    blob = kopf.size + anzahl * satz.size
    pfade = []
    for i in range(anzahl):
        versatz, laenge, _g, _t = satz.unpack_from(daten, kopf.size + i * satz.size)
        pfade.append(daten[blob + versatz: blob + versatz + laenge].decode("utf-8"))
    return pfade


def _ampr_spiel(basis: str, mit_pack: bool = False) -> str:
    """Ein kleiner Dump mit AMPR EMU im fakelib-Ordner."""
    spiel = os.path.join(basis, "PPSA99999")
    _schreiben(os.path.join(spiel, "eboot.bin"), b"\x7fELF" + b"\0" * 4096)
    _schreiben(os.path.join(spiel, "sce_sys", "param.json"),
               b'{"titleId": "PPSA99999", "contentId": "UP9999-PPSA99999_00-TEST000000000000"}')
    _schreiben(os.path.join(spiel, "fakelib", "libSceAmpr.sprx"), b"AMPR" * 256)
    _schreiben(os.path.join(spiel, "daten", "level1.dat"), b"LEVEL " * 20000)
    if mit_pack:
        # Die Dateien einer Asset-Schicht, wie sie nach dem Packen daneben liegen.
        _schreiben(os.path.join(spiel, "ampr_assets.index"), b"AMPRPAK4" + b"\0" * 64)
        _schreiben(os.path.join(spiel, "ampr_assets.index.runtime"), b"AMPRCFG1" + b"\0" * 56)
        _schreiben(os.path.join(spiel, "ampr_assets-assets-lane00-vol00-000.pak"), b"\0" * 4096)
    return spiel


class MkpfsIndexNeubauTests(_TempTest):
    """MkPFS baute den ampr_emu.index beim Packen still neu - neben dem Asset-Pack.

    ``mkpfs pack folder`` ruft ``ensure_ampr_index``, sobald
    ``fakelib/libSceAmpr.sprx`` im Ordner liegt. Bis zum 17.09.2026 geschah das
    bei jeder ``.ffpfsc`` und ``.ffpfs`` - nachdem das Programm den Index
    gebaut und das Asset-Pack dagegen gepackt hatte. Nachgestellt: Der Index
    wuchs von 7 auf 13 Saetze (Baender, Manifest, Laufzeitdatei kamen dazu),
    alle 7 fileIds des Manifests zeigten auf einen anderen Pfad, und genau
    dieser Index lag im Abbild. Die Laufzeit vergleicht Pfad und Groesse je
    fileId ("fileId and path disagree").
    """

    def _packen(self, spiel: str, argumente: list) -> None:
        import subprocess
        umgebung = dict(os.environ)
        umgebung["PYTHONPATH"] = str(PROJEKT / "MkPFS-1.0.0")
        lauf = subprocess.run([sys.executable, "-m", "mkpfs", *argumente],
                              capture_output=True, env=umgebung, timeout=300)
        self.assertEqual(lauf.returncode, 0,
                         lauf.stderr.decode("utf-8", "replace")[-600:])

    def _argumente(self, spiel: str) -> list:
        return ["pack", "folder", "--compress", "--no-adjust-output-file-extension",
                "--version", "PS5", "--inode-bits", "32", "--cpu-count", "1",
                "--compression-level", "1", "--block-size", "65536",
                spiel, os.path.join(self.basis, "Spiel.ffpfsc")]

    def test_der_schalter_steht_nur_bei_pack_folder(self) -> None:
        neu = APP.mkpfs_argumente_ohne_ampr_index(["pack", "folder", "a", "b"])
        self.assertEqual(neu[:3], ["pack", "folder", "--no-ampr-index"])
        self.assertEqual(APP.mkpfs_argumente_ohne_ampr_index(neu), neu, "doppelt gesetzt")
        for andere in (["pack", "file", "a", "b"], ["unpack", "a", "b"]):
            self.assertEqual(APP.mkpfs_argumente_ohne_ampr_index(andere), andere)

    def test_mit_dem_schalter_bleibt_der_index_im_abbild(self) -> None:
        """Am echten MkPFS: Der Index vom Packzeitpunkt ueberlebt das Packen."""
        spiel = _ampr_spiel(self.basis, mit_pack=True)
        index = os.path.join(spiel, "ampr_emu.index")
        # Der Index vor dem Asset-Pack - ohne die drei Dateien der Schicht.
        for name in ("ampr_assets.index", "ampr_assets.index.runtime",
                     "ampr_assets-assets-lane00-vol00-000.pak"):
            os.rename(os.path.join(spiel, name), os.path.join(self.basis, name))
        GUI.__new__(GUI)._build_ampr_index_local(Path(spiel), Path(index))
        for name in ("ampr_assets.index", "ampr_assets.index.runtime",
                     "ampr_assets-assets-lane00-vol00-000.pak"):
            os.rename(os.path.join(self.basis, name), os.path.join(spiel, name))
        vorher = _index_saetze(index)

        argumente = APP.mkpfs_argumente_ohne_ampr_index(self._argumente(spiel))
        self._packen(spiel, argumente)
        self.assertEqual(_index_saetze(index), vorher,
                         "MkPFS hat den Index trotz --no-ampr-index neu gebaut.")

    def test_ohne_den_schalter_baut_mkpfs_ihn_neu(self) -> None:
        """Die Voraussetzung, gegen die der Schalter steht - am echten MkPFS.

        Wird diese Pruefung rot, baut MkPFS nicht mehr selbst: Dann ist der
        Schalter ueberfluessig, aber nicht schaedlich.
        """
        spiel = _ampr_spiel(self.basis, mit_pack=True)
        index = os.path.join(spiel, "ampr_emu.index")
        _schreiben(index, b"")
        self._packen(spiel, self._argumente(spiel))
        saetze = _index_saetze(index)
        self.assertIn("/app0/ampr_assets.index", saetze)

    def test_kein_indexschreiber_aus_mkpfs_mehr(self) -> None:
        """Ein Index, ein Verfahren: nichts aus ``mkpfs.ampr`` im Hauptprogramm.

        ``_auto_generate_ampr_index`` rief bis zum 17.09.2026
        ``ensure_ampr_index`` aus MkPFS - einen dritten Schreiber mit
        ``str.lower()`` und Codepunkt-Hash.
        """
        baum = ast.parse(HAUPTDATEI.read_text(encoding="utf-8"))
        treffer = [k.lineno for k in ast.walk(baum)
                   if isinstance(k, ast.ImportFrom) and (k.module or "") == "mkpfs.ampr"]
        self.assertEqual(treffer, [], "Import aus mkpfs.ampr in Zeile(n) %s" % treffer)

    def test_execute_mkpfs_setzt_schalter_und_entscheidet_vorher(self) -> None:
        """Im Syntaxbaum: Index-Entscheidung und Schalter vor dem Protokoll des Aufrufs."""
        text = ast.unparse(_methode(_klasse(ast.parse(HAUPTDATEI.read_text(
            encoding="utf-8"))), "_execute_mkpfs"))
        entscheidung = text.index("_ampr_index_vor_dem_packen(")
        schalter = text.index("mkpfs_argumente_ohne_ampr_index(")
        aufruf = text.index("'log.auto.0071'")
        self.assertLess(entscheidung, schalter)
        self.assertLess(schalter, aufruf)


class IndexVorDemPackenTests(_TempTest):
    """Was MkPFS still tat, entscheidet jetzt das Programm - mit Riegel."""

    def _gui(self) -> GUI:
        gui = GUI.__new__(GUI)
        self.protokoll: list = []
        gui._append_to_log = self.protokoll.append
        gui._t = lambda schluessel, **_w: schluessel
        gui._set_status = lambda *_a, **_k: None

        def _nie_fragen(*_a, **_k):
            raise AssertionError("Beim Packen darf nicht gefragt werden")
        gui._ask_yesno_threadsafe = _nie_fragen
        return gui

    def test_ohne_ampr_emu_entsteht_kein_index(self) -> None:
        spiel = _ampr_spiel(self.basis)
        os.remove(os.path.join(spiel, "fakelib", "libSceAmpr.sprx"))
        self.assertTrue(self._gui()._ampr_index_vor_dem_packen(spiel))
        self.assertFalse(os.path.exists(os.path.join(spiel, "ampr_emu.index")))

    def test_ohne_asset_schicht_wird_wie_beim_entwickler_gebaut(self) -> None:
        spiel = _ampr_spiel(self.basis)
        gui = self._gui()
        self.assertTrue(gui._ampr_index_vor_dem_packen(spiel))
        self.assertTrue(gui._ampr_index_entschieden)
        werkzeug = PROJEKT / "AMPR_PackTools-4.0"
        sys.path.insert(0, str(werkzeug))
        try:
            import build_ampr_index
        finally:
            sys.path.remove(str(werkzeug))
        # Die Vorlage schreibt an dieselbe Stelle: Nur so laesst sie den Index
        # selbst aus, wie es unser Bau tut.
        index = os.path.join(spiel, "ampr_emu.index")
        with open(index, "rb") as fh:
            unser = fh.read()
        self.assertEqual(0, build_ampr_index.build_index_local(Path(spiel), Path(index), False))
        with open(index, "rb") as fh:
            self.assertEqual(unser, fh.read())
        self.assertIn(b"/app0/fakelib/libSceAmpr.sprx", unser)

    def test_neben_einer_asset_schicht_bleibt_der_index_ohne_rueckfrage(self) -> None:
        spiel = _ampr_spiel(self.basis, mit_pack=True)
        index = _schreiben(os.path.join(spiel, "ampr_emu.index"), b"ALTER INDEX")
        self.assertTrue(self._gui()._ampr_index_vor_dem_packen(spiel))
        with open(index, "rb") as fh:
            self.assertEqual(fh.read(), b"ALTER INDEX")
        self.assertIn("ampr.assets_index_kept", self.protokoll)

    def test_eine_getroffene_entscheidung_gilt(self) -> None:
        """--ampr-no-index oder der Einbau haben schon entschieden."""
        spiel = _ampr_spiel(self.basis)
        index = _schreiben(os.path.join(spiel, "ampr_emu.index"), b"BLEIBT")
        gui = self._gui()
        gui._ampr_index_entschieden = True
        self.assertTrue(gui._ampr_index_vor_dem_packen(spiel))
        with open(index, "rb") as fh:
            self.assertEqual(fh.read(), b"BLEIBT")


class AufgabeSiebenTrennungTests(unittest.TestCase):
    """Aufgabe 7 baute Baender nach einer abgeschalteten Einstellung.

    Die Methodenliste ist gesperrt, solange "AMPR EMU" nicht angehakt ist.
    Aufgabe 7 fragte trotzdem nur die Methode ab - wer irgendwann einmal
    "Asset-Pack" gewaehlt und das Kaestchen dann abgeschaltet hatte, bekam
    nach jedem Tausch (auch nach Wiederherstellen und Entfernen) Baender.

    Am 17.09.2026 behoben - und am selben Tag weiter gefasst: Aufgabe 7 baute
    gar keine Baender mehr (siehe AufgabeSiebenFasstPackNichtAnTests).
    ``_assetpack_gewaehlt`` bleibt die Frage, die das Erstellen stellt.

    Seit v1.9.36 baut Aufgabe 7 wieder, aber nur ueber den Knopf
    "Asset-Pack bauen" - nie nebenbei nach einer anderen Aktion. Die
    Trennung, um die es dieser Klasse geht, bleibt damit bestehen.
    """

    class _Wert:
        def __init__(self, wert) -> None:
            self.wert = wert

        def get(self):
            return self.wert

    def _gui(self, ampr_an: bool) -> GUI:
        gui = GUI.__new__(GUI)
        gui.ampr_integrate_var = self._Wert(ampr_an)
        gui.ampr_methode_var = self._Wert("Asset-Pack")
        gui._ampr_methode_options = {"Asset-Pack": APP.AMPR_METHODE_ASSETPACK}
        return gui

    def test_methode_allein_ist_nicht_gewaehlt(self) -> None:
        self.assertEqual(self._gui(False)._ampr_methode(), APP.AMPR_METHODE_ASSETPACK,
                         "Aufbau: Die Methode steht auf Asset-Pack")
        self.assertFalse(self._gui(False)._assetpack_gewaehlt())
        self.assertTrue(self._gui(True)._assetpack_gewaehlt())

    def test_aufgabe_sieben_versorgt_vor_dem_index(self) -> None:
        """Und packt erst danach - sonst passen die fileIds nicht.

        Bis v1.9.35 stand hier ``assertNotIn("_ampr_assetpakete_bauen")``:
        Aufgabe 7 baute gar nichts. Seit v1.9.36 gibt es den Knopf, und die
        Reihenfolge ist das, was zu schuetzen bleibt - ``ampr_pack.py`` liest
        den Index, um die fileIds zu vergeben.
        """
        methode = _methode(_klasse(ast.parse(HAUPTDATEI.read_text(
            encoding="utf-8"))), "_mode_ampr_manager")
        text = ast.unparse(methode)
        # Bibliotheken erst hinein, dann der Index.
        self.assertLess(text.index("_prepare_ampr_support("),
                        text.index("_build_ampr_index_local("))
        stellen: dict = {"index": [], "pack": []}
        for k in ast.walk(methode):
            if not (isinstance(k, ast.Call) and isinstance(k.func, ast.Attribute)):
                continue
            if k.func.attr == "_build_ampr_index_local":
                stellen["index"].append(k.lineno)
            elif k.func.attr == "_ampr_assetpakete_bauen":
                stellen["pack"].append(k.lineno)
        self.assertTrue(stellen["index"], "Kein Index-Aufbau in Aufgabe 7")
        self.assertTrue(stellen["pack"], "Aufgabe 7 baut gar kein Pack mehr")
        self.assertLess(
            min(stellen["index"]), min(stellen["pack"]),
            "Das Pack entsteht vor dem Index - die fileIds passen dann nicht.")


class AufgabeSiebenFasstPackNichtAnTests(_TempTest):
    """Aufgabe 7 laesst ein vorhandenes Asset-Pack, wie es ist (17.09.2026).

    Entscheidung des Anwenders: Aufgabe 7 ist nur der AMPR EMU Manager. Bis
    dahin baute sie nach jedem Eingriff neue Baender, sobald beim Erstellen
    AMPR EMU und die Methode Asset-Pack gewaehlt waren - und "Asset-Pack
    entfernen" loeschte Manifest und Baender, auch wenn die Originale beim
    Erstellen weggelassen worden waren. Gemessen am echten Ablauf der
    Aufgabe, nicht am Quelltext.
    """

    PACKDATEIEN = ("ampr_assets.index", "ampr_assets.index.runtime",
                   "ampr_assets-assets-lane00-vol00-000.pak")

    def _lauf(self, spiel: str, aktion: dict) -> tuple:
        app = _app()
        protokoll: list = []
        gebaut: list = []
        with mock.patch.object(app, "_append_to_log", protokoll.append), \
                mock.patch.object(app, "_set_status", lambda *_a, **_k: None), \
                mock.patch.object(app, "_assetpack_gewaehlt", lambda: True), \
                mock.patch.object(app, "_ampr_assetpakete_bauen",
                                  lambda *a, **_k: gebaut.append(a) or True), \
                mock.patch.object(app, "_cli_mode", True, create=True), \
                mock.patch.object(app, "_cli_ampr_assets", False, create=True), \
                mock.patch.object(app, "_ampr_index_entschieden", False, create=True):
            ok = app._mode_ampr_manager(spiel, "", automation=aktion)
        return ok, protokoll, gebaut, app._t("ampr.aufgabe7_ohne_assetpack")

    def test_bibliothekstausch_neben_einem_pack(self) -> None:
        spiel = _ampr_spiel(self.basis, mit_pack=True)
        vorher = {}
        for name in self.PACKDATEIEN:
            with open(os.path.join(spiel, name), "rb") as fh:
                vorher[name] = fh.read()
        eigene = _schreiben(os.path.join(self.basis, "libSceAmpr.sprx"), b"NEU!" * 300)

        ok, protokoll, gebaut, hinweis = self._lauf(spiel, {
            "action": "ampr_apply", "ampr_source": eigene,
            "ampr_lib": "libSceAmpr.sprx"})

        self.assertTrue(ok, "".join(map(str, protokoll)))
        with open(os.path.join(spiel, "fakelib", "libSceAmpr.sprx"), "rb") as fh:
            self.assertEqual(fh.read(), b"NEU!" * 300,
                             "Aufbau: Der Tausch fand nicht statt")
        self.assertEqual(gebaut, [], "Aufgabe 7 hat Asset-Pack-Baender gebaut")
        for name, inhalt in vorher.items():
            with open(os.path.join(spiel, name), "rb") as fh:
                self.assertEqual(fh.read(), inhalt, "%s wurde veraendert" % name)
        self.assertIn(hinweis, protokoll,
                      "Wer die Methode beim Erstellen gewaehlt hat, erfaehrt nicht, "
                      "dass sie hier nicht greift")

    def test_die_alte_aktion_wird_abgewiesen(self) -> None:
        """Ein gespeicherter Ablauf mit der alten Aktion loescht nichts."""
        spiel = _ampr_spiel(self.basis, mit_pack=True)
        ok, _protokoll, gebaut, _hinweis = self._lauf(
            spiel, {"action": "ampr_pack_remove"})
        self.assertFalse(ok)
        self.assertEqual(gebaut, [])
        for name in self.PACKDATEIEN:
            self.assertTrue(os.path.isfile(os.path.join(spiel, name)),
                            "%s wurde entfernt" % name)


def _packbereit() -> bool:
    from ps5_validator.utils import ampr_assetpakete as ap
    return bool(ap.einsatzbereit()[0])


@unittest.skipUnless(_packbereit(), "Packwerkzeug oder lz4 fehlt")
class AssetPackBauwegTests(_TempTest):
    """Der ganze Bauweg mit dem echten ampr_pack.py - wie in der Anleitung.

    Bis zum 17.09.2026 fehlten darin ``list --json`` samt Pruefung der losen
    Dateien, die Speicherrechnung, die ``.crc`` im Spielordner, die
    Beschraenkung auf die vom Manifest genannten Baender und das Entfernen
    der gepackten Originale. Ausserdem blieb nach Erfolg eine zweite Kopie
    aller Baender neben dem Spielordner liegen.
    """

    def _gui(self) -> GUI:
        gui = GUI.__new__(GUI)
        self.protokoll: list = []
        gui._append_to_log = self.protokoll.append
        gui._t = lambda schluessel, **_w: schluessel
        gui._set_status = lambda *_a, **_k: None
        gui._ampr_pack_fortschritt = lambda *_a, **_k: None
        gui._ampr_pack_uhr_starten = lambda *_a, **_k: None
        gui._ampr_pack_uhr_stoppen = lambda *_a, **_k: None
        gui._ampr_pack_arbeiter = lambda: 2
        gui.is_running = True
        return gui

    def _spiel_mit_index(self) -> tuple:
        spiel = _ampr_spiel(self.basis)
        for i in range(3):
            _schreiben(os.path.join(spiel, "daten", "karte%d.dat" % i),
                       (b"KARTE %d " % i) * 30000)
        index = os.path.join(spiel, "ampr_emu.index")
        GUI.__new__(GUI)._build_ampr_index_local(Path(spiel), Path(index))
        return spiel, index

    def test_bauweg_liefert_den_vollstaendigen_pruefbaren_satz(self) -> None:
        from ps5_validator.utils import ampr_assetpakete as ap

        spiel, index = self._spiel_mit_index()
        gui = self._gui()
        self.assertTrue(gui._ampr_assetpakete_bauen(spiel, index, {"variant": "test-pack"}),
                        self.protokoll)
        namen = set(os.listdir(spiel))
        for name in (ap.MANIFEST_NAME, ap.LAUFZEIT_NAME, ap.PRUEFSUMMEN_NAME):
            self.assertIn(name, namen)
        baender = ap.bandnamen(ap.uebersicht(os.path.join(spiel, ap.MANIFEST_NAME)))
        self.assertTrue(baender)
        self.assertTrue(set(baender) <= namen, "Nicht jedes genannte Band liegt im Spiel")
        self.assertFalse(os.path.exists(spiel + "_ampr_pack"),
                         "Die zweite Kopie der Baender blieb neben dem Spiel liegen")
        self.assertIn("ampr_pack.speicher_ok", self.protokoll)
        self.assertIn("ampr_pack.quellen_bleiben", self.protokoll)
        # Ohne Wunsch bleiben die Originale; der Satz ist gegen sie pruefbar.
        self.assertTrue(os.path.isfile(os.path.join(spiel, "daten", "karte0.dat")))
        ap.pruefen(os.path.join(spiel, ap.MANIFEST_NAME), app0=spiel)

    def test_ein_altes_band_im_ausgabeordner_bleibt_draussen(self) -> None:
        """Nur die Baender, die das Manifest nennt, kommen ins Spiel."""
        spiel, index = self._spiel_mit_index()
        _schreiben(os.path.join(spiel + "_ampr_pack",
                                "ampr_assets-assets-lane07-vol00-099.pak"), b"ALT" * 100)
        self.assertTrue(self._gui()._ampr_assetpakete_bauen(
            spiel, index, {"variant": "test-pack"}), self.protokoll)
        self.assertNotIn("ampr_assets-assets-lane07-vol00-099.pak", os.listdir(spiel))

    def test_originale_weg_nur_in_einer_kopie(self) -> None:
        spiel, index = self._spiel_mit_index()
        gui = self._gui()
        gui._ampr_originale_weglassen = True
        gui._ampr_ordner_ist_kopie = False
        self.assertTrue(gui._ampr_assetpakete_bauen(spiel, index, {"variant": "test-pack"}))
        self.assertIn("ampr_pack.originale_nicht_im_quellordner", self.protokoll)
        self.assertTrue(os.path.isfile(os.path.join(spiel, "daten", "karte0.dat")),
                        "Im Ordner des Anwenders wurde ein Original entfernt")

    def test_originale_weg_in_der_arbeitskopie(self) -> None:
        from ps5_validator.utils import ampr_assetpakete as ap

        spiel, index = self._spiel_mit_index()
        gui = self._gui()
        gui._ampr_originale_weglassen = True
        gui._ampr_ordner_ist_kopie = True
        vorher = sum(os.path.getsize(os.path.join(w, f))
                     for w, _d, namen in os.walk(os.path.join(spiel, "daten")) for f in namen)
        self.assertTrue(gui._ampr_assetpakete_bauen(spiel, index, {"variant": "test-pack"}),
                        self.protokoll)
        self.assertIn("ampr_pack.originale_entfernt", self.protokoll)
        gepackt = {str(z["path"]) for z in ap.liste(os.path.join(spiel, ap.MANIFEST_NAME))
                   if z.get("packed")}
        self.assertIn("/app0/daten/karte0.dat", gepackt)
        for pfad in gepackt:
            self.assertFalse(os.path.exists(os.path.join(spiel, *pfad[len("/app0/"):].split("/"))),
                             "%s liegt noch als Original da" % pfad)
        # Was nie gepackt wird, bleibt: Programm, Systemordner, Bibliotheken, Index.
        for bleibt in ("eboot.bin", "sce_sys/param.json", "fakelib/libSceAmpr.sprx",
                       "ampr_emu.index"):
            self.assertTrue(os.path.isfile(os.path.join(spiel, *bleibt.split("/"))), bleibt)
        # Die Baender tragen die Daten jetzt allein - und sind in sich stimmig.
        ap.pruefen(os.path.join(spiel, ap.MANIFEST_NAME))
        self.assertGreater(vorher, 0)


class OriginaleRueckfrageTests(_TempTest):
    """Wann nach dem Weglassen gefragt wird - und wann gerade nicht."""

    class _Wert:
        def __init__(self, wert) -> None:
            self.wert = wert

        def get(self):
            return self.wert

    def _gui(self, ampr_an: bool, cli: bool = False, schalter: bool = False) -> GUI:
        gui = GUI.__new__(GUI)
        self.protokoll: list = []
        gui._append_to_log = self.protokoll.append
        gui._t = lambda schluessel, **_w: schluessel
        gui.ampr_integrate_var = self._Wert(ampr_an)
        gui.ampr_methode_var = self._Wert("Asset-Pack")
        gui._ampr_methode_options = {"Asset-Pack": APP.AMPR_METHODE_ASSETPACK}
        gui._cli_mode = cli
        gui._cli_ampr_originale_weglassen = schalter
        return gui

    def test_gefragt_wird_nur_mit_asset_pack(self) -> None:
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True) as frage:
            gui = self._gui(ampr_an=False)
            gui._ampr_originale_klaeren("pack_folder")
            self.assertFalse(gui._ampr_originale_weglassen)
            frage.assert_not_called()
            gui = self._gui(ampr_an=True)
            gui._ampr_originale_klaeren("pack_folder")
            self.assertTrue(gui._ampr_originale_weglassen)
            self.assertEqual(frage.call_args.kwargs.get("default"), "no",
                             "Vorgabe muss Nein sein - erst nach dem Konsolentest")

    def test_aufgabe_sieben_fragt_nie(self) -> None:
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True) as frage:
            gui = self._gui(ampr_an=True)
            gui._ampr_originale_klaeren("ampr_manager")
            self.assertFalse(gui._ampr_originale_weglassen)
            frage.assert_not_called()

    def test_kommandozeile_nur_mit_eigenem_schalter(self) -> None:
        with mock.patch.object(APP.messagebox, "askyesno",
                               side_effect=AssertionError("CLI darf nicht fragen")):
            gui = self._gui(ampr_an=True, cli=True, schalter=False)
            gui._ampr_originale_klaeren("pack_folder")
            self.assertFalse(gui._ampr_originale_weglassen)
            gui = self._gui(ampr_an=True, cli=True, schalter=True)
            gui._ampr_originale_klaeren("pack_folder")
            self.assertTrue(gui._ampr_originale_weglassen)

    def test_schalter_ist_verdrahtet(self) -> None:
        parser = APP._build_cli_parser()
        self.assertTrue(parser.parse_args(["--ampr-originale-weglassen"]).ampr_originale_weglassen)
        gui = GUI.__new__(GUI)
        APP._cli_schalter_uebernehmen(gui, parser.parse_args(["--ampr-originale-weglassen"]))
        self.assertTrue(gui._cli_ampr_originale_weglassen)

    def test_nur_eine_kopie_gilt_als_kopie(self) -> None:
        """Im Quellordner (Nein zur Arbeitskopie) bleibt der Merker aus."""
        ordner = os.path.join(self.basis, "PPSA00001")
        os.makedirs(ordner)
        kopie = os.path.join(self.basis, "kopie", "PPSA00001")
        os.makedirs(kopie)
        for rueckgabe, ist_quelle, erwartet in ((ordner, True, False),
                                                (kopie, True, True),
                                                (ordner, False, True)):
            with self.subTest(rueckgabe=rueckgabe, ist_quelle=ist_quelle):
                gui = GUI.__new__(GUI)
                gui._integration_gewaehlt = lambda: True
                gui._integration_erledigt = False
                gui._integration_arbeitskopie = lambda _q, r=rueckgabe: r
                gui._tk_wert = lambda _n, vorgabe=None: False
                gui._append_to_log = lambda *_a: None
                gui._t = lambda schluessel, **_w: schluessel
                self.assertTrue(gui._integration_anwenden(ordner, ist_quellordner=ist_quelle))
                self.assertIs(gui._ampr_ordner_ist_kopie, erwartet)


class FruehereEinbautenTests(_TempTest):
    """Einbauten aus frueheren Laeufen gehen ohne Haken mit - die Vorabpruefung sagt es.

    Gemessen am 17.09.2026: Crazy Chicken Shooter trug im Quellordner schon
    AMPR EMU, PlayGo und Backport-Bibliotheken (FW7). "Nur BACKPORT" daraus
    lieferte AMPR EMU und PlayGo mit - die Kaestchen legen dazu, nehmen aber
    nichts heraus.
    """

    class _Wert:
        def __init__(self, wert) -> None:
            self.wert = wert

        def get(self):
            return self.wert

    def _gui(self, ampr: bool = False, playgo: bool = False, backport: bool = False,
             pack: bool = False) -> GUI:
        gui = GUI.__new__(GUI)
        gui._t = lambda schluessel, **_w: schluessel
        gui.ampr_integrate_var = self._Wert(ampr)
        gui.ampr_playgo_var = self._Wert(playgo)
        gui.backport_integrate_var = self._Wert(backport)
        gui.ampr_methode_var = self._Wert("Asset-Pack" if pack else "Normal")
        gui._ampr_methode_options = {"Asset-Pack": APP.AMPR_METHODE_ASSETPACK,
                                     "Normal": APP.AMPR_METHODE_NORMAL}
        return gui

    def _spiel(self) -> str:
        spiel = os.path.join(self.basis, "Crazy Chicken Shooter")
        for name in ("libSceAmpr.sprx", "libScePlayGo.sprx", "FW7", "libSceAgc.sprx"):
            _schreiben(os.path.join(spiel, "fakelib", name))
        _schreiben(os.path.join(spiel, "ampr_assets.index"))
        return spiel

    def test_ohne_haken_wird_alles_genannt(self) -> None:
        self.assertEqual(self._gui()._fruehere_einbauten(self._spiel()),
                         ["fakelib/libSceAmpr.sprx", "fakelib/libScePlayGo.sprx",
                          "fakelib/FW7", "ampr_assets.index"])

    def test_angehakt_zaehlt_nicht_als_rest(self) -> None:
        gui = self._gui(ampr=True, playgo=True, backport=True, pack=True)
        self.assertEqual(gui._fruehere_einbauten(self._spiel()), [])

    def test_playgo_ohne_haken_bleibt_ein_rest(self) -> None:
        """AMPR angehakt, PlayGo nicht: der alte PlayGo-Stub ginge trotzdem mit."""
        self.assertEqual(self._gui(ampr=True, backport=True)._fruehere_einbauten(self._spiel()),
                         ["fakelib/libScePlayGo.sprx", "ampr_assets.index"])

    def test_vorabpruefung_meldet_es(self) -> None:
        gui = self._gui(backport=True)
        gui._get_runtime_temp_dir = lambda: self.basis
        gui._missing_critical_dump_files = lambda *_a: []
        _fehler, warnungen = gui._run_preflight_checks("pack_folder", self._spiel(), "")
        self.assertIn("preflight.einbau_schon_im_dump", warnungen)
        sauber = os.path.join(self.basis, "sauber")
        os.makedirs(sauber)
        _fehler, warnungen = gui._run_preflight_checks("pack_folder", sauber, "")
        self.assertNotIn("preflight.einbau_schon_im_dump", warnungen)


class OhneOsfmountTests(_TempTest):
    """Die Vorabpruefung darf OSFMount nicht mehr verlangen (18.09.2026).

    Sie warnte vor jedem Start von Aufgabe 2 und Aufgabe 3, OSFMount fehle -
    und schickte Anwender damit zu einem Fremdwerkzeug samt Kernel-Treiber,
    das dieses Programm nicht braucht: Aufgabe 2 haengt gar nichts ein, und
    Aufgabe 3 packt mit dem eingebetteten exFAT-Leser aus MkPFS aus. OSFMount
    ist nur noch der Rueckfall fuer ein ungewoehnliches Abbild, und das sagt
    der Lauf selbst.
    """

    def _gui(self) -> GUI:
        gui = GUI.__new__(GUI)
        gui._t = lambda schluessel, **_w: schluessel
        gui._get_runtime_temp_dir = lambda: self.basis
        gui._missing_critical_dump_files = lambda *_a: []
        # Kein OSFMount weit und breit - genau der Fall, der frueher warnte.
        gui._find_osfmount = lambda: None
        return gui

    def test_keine_warnung_mehr_bei_den_beiden_aufgaben(self) -> None:
        quelle = os.path.join(self.basis, "quelle")
        os.makedirs(quelle, exist_ok=True)
        for modus in ("unpack_to_exfat", "exfat_to_folder"):
            with self.subTest(modus=modus):
                _fehler, warnungen = self._gui()._run_preflight_checks(
                    modus, quelle, self.basis)
                treffer = [w for w in warnungen if "osfmount" in str(w).lower()]
                self.assertEqual(treffer, [],
                                 "Die Vorabpruefung verlangt wieder OSFMount")

    def test_der_text_dazu_ist_weg(self) -> None:
        """Gegenstueck: Der Schluessel darf auch nicht mehr herumliegen."""
        from ps5_validator.utils import i18n
        self.assertNotIn("preflight.osfmount_missing", i18n.STRINGS)

    def test_aufgabe_drei_nimmt_zuerst_den_eingebetteten_leser(self) -> None:
        """Am Syntaxbaum: der native Weg steht vor dem OSFMount-Rueckfall."""
        text = ast.unparse(_methode(_klasse(ast.parse(HAUPTDATEI.read_text(
            encoding="utf-8"))), "_mode_exfat_to_folder"))
        self.assertLess(text.index("_extract_exfat_to_folder_mkpfs"),
                        text.index("_find_osfmount"),
                        "Aufgabe 3 haengt ein, bevor sie den Leser probiert")


class PlayGoTrennungTests(_TempTest):
    """PlayGo: Hinweis bei PlayGo-Titeln, Variante passend zur Bauart."""

    class _Wert:
        def __init__(self, wert) -> None:
            self.wert = wert

        def get(self):
            return self.wert

    def _gui(self, playgo: bool) -> GUI:
        gui = GUI.__new__(GUI)
        self.protokoll: list = []
        gui._append_to_log = self.protokoll.append
        gui._t = lambda schluessel, **_w: schluessel
        gui._set_status = lambda *_a, **_k: None
        gui.ampr_version_var = self._Wert("0.4.2.1 test-pack")
        gui.ampr_playgo_var = self._Wert(playgo)
        gui._ampr_versionsauswahl = {"0.4.2.1 test-pack": {
            "path": "x", "variant": "test-pack", "version": "0.4.2.1"}}
        gui._ampr_apply_library = lambda *_a, **_k: True
        gui._ampr_playgo_zur_version = lambda _e: "playgo.sprx"
        gui._ampr_index_neubau_erlaubt = lambda *_a, **_k: True
        gui._build_ampr_index_local = lambda *_a, **_k: (1, 0)
        gui._ampr_methode = lambda: APP.AMPR_METHODE_NORMAL
        return gui

    def _spiel(self) -> str:
        spiel = os.path.join(self.basis, "PPSA26344")
        _schreiben(os.path.join(spiel, "sce_sys", "playgo-scenario.json"), b"{}")
        return spiel

    def test_playgo_titel_ohne_playgo_bekommt_einen_hinweis(self) -> None:
        spiel = self._spiel()
        self.assertTrue(self._gui(False)._integration_ampr(spiel))
        self.assertIn("main.integrate_playgo_empfohlen", self.protokoll)

    def test_mit_playgo_kein_hinweis(self) -> None:
        spiel = self._spiel()
        self.assertTrue(self._gui(True)._integration_ampr(spiel))
        self.assertNotIn("main.integrate_playgo_empfohlen", self.protokoll)

    def test_vorab_wird_gefragt_nicht_nur_gewarnt(self) -> None:
        """Vor der Arbeit, und so, dass sich PlayGo noch einschalten laesst.

        Bis zum 18.09.2026 stand hier eine Meldung in der Vorabpruefung -
        nur mit "OK", danach lief die Aufgabe los. Jetzt fragt der Anfang
        des Laufs (mehr in test_playgo_vor_dem_lauf.py).
        """
        spiel = self._spiel()
        for playgo, erwartet in ((False, 1), (True, 0)):
            with self.subTest(playgo=playgo):
                gui = self._gui(playgo)
                gui.ampr_integrate_var = self._Wert(True)
                gui._lauf_variablen = None
                gui._save_setting = lambda *_a: None
                fragen: list = []
                gui._ask_yesno_threadsafe = (
                    lambda *a, **_k: fragen.append(a) or False)
                gui._playgo_vor_dem_lauf_klaeren("pack_folder", spiel)
                self.assertEqual(erwartet, len(fragen))

    def test_titel_ohne_playgo_merkmal_kein_hinweis(self) -> None:
        spiel = self._spiel()
        os.remove(os.path.join(spiel, "sce_sys", "playgo-scenario.json"))
        self.assertTrue(self._gui(False)._integration_ampr(spiel))
        self.assertNotIn("main.integrate_playgo_empfohlen", self.protokoll)

    def test_playgo_variante_folgt_der_bauart(self) -> None:
        gui = GUI.__new__(GUI)
        # Absichtlich die "falsche" zuerst - bis zum 17.09.2026 gewann die erste.
        for erste, zweite, bauart, erwartet in (
                ("log", "nolog", "test-pack", "nolog"),
                ("nolog", "log", "test-debug-pack", "log"),
                ("log", "nolog", "test-nopack", "nolog")):
            with self.subTest(bauart=bauart):
                gui._ampr_alle_fassungen = lambda e=erste, z=zweite: [
                    {"lib": GUI._PLAYGO_SPRX_NAME, "variant": e, "path": e},
                    {"lib": GUI._PLAYGO_SPRX_NAME, "variant": z, "path": z}]
                self.assertEqual(gui._ampr_playgo_zur_version({"variant": bauart}),
                                 erwartet)


if __name__ == "__main__":
    unittest.main(verbosity=2)
