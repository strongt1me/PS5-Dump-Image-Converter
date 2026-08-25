"""Regressionstests für Aufgabe 4: .ffpfsc vollständig in einen Dump-Ordner entpacken.

Ein .ffpfsc kann auf mehrere Arten gebaut worden sein, und man sieht es der
Datei von außen nicht an:

  * ``mkpfs pack folder ... --raw``  → Container → rohes PFS → Spieldateien
    (so baut dieses Programm selbst)
  * ``mkpfs pack folder ...``        → Container → exFAT-Abbild → Spieldateien
    (ohne ``--raw`` legt mkpfs von sich aus ein exFAT dazwischen; ``--no-compress``
    wirkt auf diesem Weg nicht)
  * ``mkpfs pack file ...``          → Container → eingebettetes Abbild
  * beides hintereinander            → Container → PFS → exFAT → Spieldateien

Früher entschied die Aufgabe anhand der Frage „liegt im Container ein Ordner
oder eine Datei?" und packte höchstens eine Ebene tiefer aus. Ein dreifach
verschachtelter Container landete deshalb als **einzelne .exfat-Datei** im
Dump-Ordner – gemeldet wurde trotzdem Erfolg. Geprüft wird hier deshalb:

  1. jede der vier Bauformen liefert denselben, vollständigen Dump-Ordner,
  2. die Abbildart wird an der Kennung erkannt, nicht an der Dateiendung,
  3. ein unvollständiges Ergebnis wird als Fehler gemeldet statt als Erfolg,
  4. gleichnamige Ordner werden beim Verschieben zusammengeführt statt
     ineinander geschachtelt.
"""
from __future__ import annotations

import io
import json
import os
import queue
import struct
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

ROOT = Path(__file__).resolve().parent
MKPFS_DIR = next(
    (p for p in sorted(ROOT.glob("MkPFS-*"), reverse=True) if (p / "mkpfs" / "__init__.py").is_file()),
    None,
)


class _StubRoot:
    """Ersetzt das Tk-Fenster: Rückrufe laufen sofort im aufrufenden Thread."""

    def after(self, _delay_ms: int, callback=None, *args) -> None:
        if callable(callback):
            callback(*args)


class _StubLabel:
    """Nimmt Statustexte entgegen, ohne sie anzuzeigen."""

    def config(self, **_kwargs) -> None:
        pass

    def cget(self, _key: str) -> str:
        return ""


class _StubProgress:
    """Fortschrittsanzeige ohne Oberfläche."""

    _phase = ""

    def start_task(self, *_a, **_k) -> None:
        pass

    def begin_prepare(self, *_a, **_k) -> None:
        pass

    def begin_payload(self, *_a, **_k) -> None:
        pass

    def begin_validate(self, *_a, **_k) -> None:
        pass

    def update_payload(self, *_a, **_k) -> None:
        pass

    def commit_task(self, *_a, **_k) -> None:
        pass


class _StubKindLabel:
    """Platzhalter fuer den Bauform-Hinweis neben QUELLE."""

    def __init__(self) -> None:
        self.text = ""
        self.farbe = ""
        self.sichtbar = False
        self._caption_fg_role = ""

    def config(self, **kwargs) -> None:
        self.text = str(kwargs.get("text", self.text))
        self.farbe = str(kwargs.get("foreground", self.farbe))

    def grid(self) -> None:
        self.sichtbar = True

    def grid_remove(self) -> None:
        self.sichtbar = False


def _make_gui() -> PS5ConverterGUI:
    """Baut eine GUI-Instanz ohne Tk, die die echte mkpfs-Engine aufrufen kann."""
    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui.root = _StubRoot()
    gui.status_label = _StubLabel()
    gui.progress_engine = _StubProgress()
    gui.is_running = True
    gui.task_progress = 0.0
    gui.task_displayed = 0.0
    gui.task_current_step = 0
    gui.task_num_steps = 1
    gui.task_step_ends = [100.0]
    gui.task_total_source_bytes = 0
    gui.task_final_output_path = ""
    gui.mkpfs_dir = str(MKPFS_DIR.resolve()) if MKPFS_DIR else ""
    gui.engine_output_queue = queue.Queue()
    gui._embedded_mkpfs_lock = threading.RLock()
    gui._monitor_target_path = ""
    gui._preview_cache = {}
    protokoll: list[str] = []
    gui._append_to_log = protokoll.append
    gui._log_lines = protokoll
    gui._backfill_preview_from_dir_for_source = lambda *_a, **_k: None
    gui._ensure_mkpfs_runtime_dependencies = lambda: True
    gui._wait_for_pending_mkpfs_background = lambda *_a, **_k: None
    gui._cleanup_stale_mkpfs_output = lambda *_a, **_k: None
    gui._save_runtime_checkpoint = lambda **_kw: None
    gui._seed_preview_cache_from_dir = lambda *_a, **_k: None
    # Die inhaltliche param.json-Pruefung fragt bei Maengeln per Dialog nach
    # und wuerde hier ohne Tk-Fenster ewig warten. Sie hat mit dem Auspacken
    # nichts zu tun und ist in test_param_json_recovery.py eigens abgedeckt.
    gui._ensure_param_json = lambda *_a, **_k: True
    gui._COLORS = PS5ConverterGUI._THEMES["dunkel"]
    gui._seed_preview_cache_from_source = lambda *_a, **_k: None
    gui._set_status = lambda *_a, **_k: None
    gui._load_setting = lambda _schluessel, vorgabe: vorgabe
    gui._save_setting = lambda *_a, **_k: None
    return gui


def _dump_anlegen(ziel: Path) -> tuple[int, int]:
    """Legt einen kleinen, aber verschachtelten Testdump an.

    Returns:
        ``(Dateien, Bytes)`` des angelegten Baums.
    """
    (ziel / "sce_sys" / "about").mkdir(parents=True, exist_ok=True)
    (ziel / "sce_module").mkdir(parents=True, exist_ok=True)
    (ziel / "Media" / "Movies").mkdir(parents=True, exist_ok=True)
    (ziel / "sce_sys" / "param.json").write_text(
        json.dumps({"titleId": "CUSA12345", "contentVersion": "01.00"}), encoding="utf-8"
    )
    (ziel / "sce_sys" / "pfs-version.dat").write_bytes(os.urandom(16))
    (ziel / "sce_sys" / "icon0.png").write_bytes(b"\x89PNG\r\n\x1a\n" + os.urandom(4000))
    (ziel / "sce_sys" / "about" / "right.sprx").write_bytes(os.urandom(3000))
    (ziel / "eboot.bin").write_bytes(b"\x7fELF" + os.urandom(60_000))
    (ziel / "sce_module" / "libc.prx").write_bytes(os.urandom(20_000))
    (ziel / "Media" / "Movies" / "intro.pam").write_bytes(b"A" * 200_000)
    (ziel / "Media" / "data.bin").write_bytes(os.urandom(50_000))

    dateien = 0
    bytes_gesamt = 0
    for ordner, _unter, namen in os.walk(ziel):
        for name in namen:
            dateien += 1
            bytes_gesamt += os.path.getsize(os.path.join(ordner, name))
    return dateien, bytes_gesamt


def _mkpfs(*args: str) -> int:
    """Ruft die mitgelieferte mkpfs-Engine direkt auf.

    stdout/stderr werden dabei umgeleitet - zum einen, weil die Ausgabe hier
    nur stoert, zum anderen weil mkpfs Emojis ausgibt, an denen die
    Windows-Konsole (cp1252) scheitert. Im Programm passiert dasselbe: dort
    haengt an stdout der Queue-Writer der Oberflaeche.
    """
    if MKPFS_DIR and str(MKPFS_DIR) not in sys.path:
        sys.path.insert(0, str(MKPFS_DIR))
    from mkpfs.cli import cli_mkpfs_main  # noqa: PLC0415

    puffer = io.StringIO()
    with redirect_stdout(puffer), redirect_stderr(puffer):
        return cli_mkpfs_main(list(args)) or 0


def _ordner_inhalt(pfad: Path) -> tuple[int, int]:
    """Zählt Dateien und Bytes eines Ordners."""
    dateien = 0
    bytes_gesamt = 0
    for ordner, _unter, namen in os.walk(pfad):
        for name in namen:
            dateien += 1
            bytes_gesamt += os.path.getsize(os.path.join(ordner, name))
    return dateien, bytes_gesamt


@unittest.skipIf(MKPFS_DIR is None, "MkPFS-Quellordner nicht gefunden")
class EntpackenAllerBauformenTests(unittest.TestCase):
    """Jede Bauform muss denselben vollständigen Dump-Ordner liefern."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory(prefix="ffpfsc_entpacken_")
        basis = Path(cls._tmp.name)
        cls.quelle = basis / "dump"
        cls.quelle.mkdir()
        cls.soll_dateien, cls.soll_bytes = _dump_anlegen(cls.quelle)

        # a) mkpfs pack folder ohne --raw: Container -> exFAT -> Dateien.
        #    Genau die Form, die "--no-compress --no-adjust-output-file-extension"
        #    erzeugt; --no-compress greift auf diesem Weg gar nicht.
        cls.wrapper = basis / "wrapper.ffpfsc"
        _mkpfs("pack", "folder", str(cls.quelle), str(cls.wrapper),
               "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5")

        # b) mkpfs pack folder --raw: Dateien liegen direkt im Container.
        cls.flach = basis / "flach.ffpfsc"
        _mkpfs("pack", "folder", "--raw", str(cls.quelle), str(cls.flach),
               "--no-adjust-output-file-extension", "--version", "PS5")

        # c) mkpfs pack file auf ein exFAT: Container -> exFAT -> Dateien.
        cls.exfat = basis / "CUSA12345.exfat"
        _mkpfs("pack", "exfat", str(cls.quelle), str(cls.exfat))
        cls.packfile = basis / "packfile.ffpfsc"
        _mkpfs("pack", "file", str(cls.exfat), str(cls.packfile), "--version", "PS5")

        # d) beides hintereinander: Container -> PFS -> exFAT -> Dateien.
        cls.dreifach = basis / "dreifach.ffpfsc"
        _mkpfs("pack", "file", str(cls.wrapper), str(cls.dreifach), "--version", "PS5")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _entpacken_und_pruefen(self, container: Path) -> None:
        with TemporaryDirectory(prefix="ffpfsc_ziel_") as ziel:
            gui = _make_gui()
            self.assertTrue(
                gui._mode_unpack_to_game_folder(str(container), ziel),
                msg=f"{container.name} wurde nicht entpackt:\n" + "".join(gui._log_lines[-8:]),
            )
            ergebnis = Path(ziel) / container.stem
            self.assertTrue(ergebnis.is_dir(), f"{ergebnis} fehlt")
            dateien, bytes_gesamt = _ordner_inhalt(ergebnis)
            self.assertEqual(dateien, self.soll_dateien, f"Dateizahl weicht ab ({container.name})")
            self.assertEqual(bytes_gesamt, self.soll_bytes, f"Bytezahl weicht ab ({container.name})")
            # Der eigentliche Fehlerfall von früher: eine einzelne Abbilddatei
            # statt der Spieldateien.
            self.assertTrue((ergebnis / "eboot.bin").is_file())
            self.assertTrue((ergebnis / "sce_sys" / "param.json").is_file())

    def test_pack_folder_ohne_raw_wird_vollstaendig_entpackt(self) -> None:
        self._entpacken_und_pruefen(self.wrapper)

    def test_pack_folder_mit_raw_wird_vollstaendig_entpackt(self) -> None:
        self._entpacken_und_pruefen(self.flach)

    def test_pack_file_wird_vollstaendig_entpackt(self) -> None:
        self._entpacken_und_pruefen(self.packfile)

    def test_dreifach_verschachtelt_wird_vollstaendig_entpackt(self) -> None:
        self._entpacken_und_pruefen(self.dreifach)

    def test_sollwerte_stammen_aus_dem_innersten_abbild(self) -> None:
        art = PS5ConverterGUI._sniff_image_kind(str(self.exfat))
        self.assertEqual(art, "exfat")
        gui = _make_gui()
        erwartet = gui._container_expectations(str(self.exfat), art)
        self.assertIsNotNone(erwartet)
        assert erwartet is not None
        self.assertEqual(erwartet[0], self.soll_dateien)
        self.assertEqual(erwartet[1], self.soll_bytes)


@unittest.skipIf(MKPFS_DIR is None, "MkPFS-Quellordner nicht gefunden")
class Aufgabe2AlleBauformenTests(unittest.TestCase):
    """Aufgabe 2 (.ffpfsc -> .exfat) muss dieselben Bauformen verkraften.

    Sie ging früher denselben einstufigen Weg wie Aufgabe 4: Bei einem
    Container mit einer Ebene mehr lag danach eine einzelne .exfat im
    Arbeitsordner, und der Bau des neuen Images brach mit "eboot.bin fehlt"
    ab. Seit dem Umbau teilen sich beide Aufgaben dieselbe Auspack-Schleife.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory(prefix="ffpfsc_task2_")
        basis = Path(cls._tmp.name)
        cls.quelle = basis / "dump"
        cls.quelle.mkdir()
        cls.soll_dateien, cls.soll_bytes = _dump_anlegen(cls.quelle)

        cls.wrapper = basis / "wrapper.ffpfsc"
        _mkpfs("pack", "folder", str(cls.quelle), str(cls.wrapper),
               "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5")
        cls.flach = basis / "flach.ffpfsc"
        _mkpfs("pack", "folder", "--raw", str(cls.quelle), str(cls.flach),
               "--no-adjust-output-file-extension", "--version", "PS5")
        cls.dreifach = basis / "dreifach.ffpfsc"
        _mkpfs("pack", "file", str(cls.wrapper), str(cls.dreifach), "--version", "PS5")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _nach_exfat(self, container: Path) -> None:
        with TemporaryDirectory(prefix="ffpfsc_task2_ziel_") as ziel:
            gui = _make_gui()
            self.assertTrue(
                gui._mode_unpack_to_exfat(str(container), ziel),
                msg=f"{container.name} wurde nicht umgewandelt: " + "".join(gui._log_lines[-8:]),
            )
            ergebnis = Path(ziel) / f"{container.stem}.exfat"
            self.assertTrue(ergebnis.is_file(), f"{ergebnis} fehlt")

            # Das erzeugte Image muss denselben Baum enthalten wie die Quelle.
            if MKPFS_DIR and str(MKPFS_DIR) not in sys.path:
                sys.path.insert(0, str(MKPFS_DIR))
            from mkpfs.exfat import ExfatReader  # noqa: PLC0415

            with open(ergebnis, "rb") as fh:
                eintraege = list(ExfatReader(fh).iter_files())
            self.assertEqual(len(eintraege), self.soll_dateien, container.name)
            self.assertEqual(sum(e.length for e in eintraege), self.soll_bytes, container.name)
            self.assertTrue(any(e.rel_path == "eboot.bin" for e in eintraege))

    def test_pack_folder_ohne_raw(self) -> None:
        self._nach_exfat(self.wrapper)

    def test_pack_folder_mit_raw(self) -> None:
        self._nach_exfat(self.flach)

    def test_dreifach_verschachtelt(self) -> None:
        self._nach_exfat(self.dreifach)


class AbbildartErkennungTests(unittest.TestCase):
    """Die Kennung entscheidet, nicht die Dateiendung."""

    def test_exfat_wird_an_der_kennung_erkannt(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "ohne_endung"
            p.write_bytes(b"\xeb\x76\x90" + b"EXFAT   " + bytes(501))
            self.assertEqual(PS5ConverterGUI._sniff_image_kind(str(p)), "exfat")

    def test_pfs_wird_an_der_kennung_erkannt(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "beliebig.dat"
            p.write_bytes(struct.pack("<qq", 2, 0x1332A0B) + bytes(496))
            self.assertEqual(PS5ConverterGUI._sniff_image_kind(str(p)), "pfs")

    def test_ufs2_wird_am_superblock_erkannt(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "irgendwas.bin"
            roh = bytearray(65536 + 1372 + 4)
            struct.pack_into("<I", roh, 65536 + 1372, 0x19540119)
            p.write_bytes(bytes(roh))
            self.assertEqual(PS5ConverterGUI._sniff_image_kind(str(p)), "ufs2")

    def test_spieldatei_gilt_nicht_als_abbild(self) -> None:
        with TemporaryDirectory() as td:
            p = Path(td) / "eboot.bin"
            p.write_bytes(b"\x7fELF" + os.urandom(2000))
            self.assertEqual(PS5ConverterGUI._sniff_image_kind(str(p)), "")


@unittest.skipIf(MKPFS_DIR is None, "MkPFS-Quellordner nicht gefunden")
class UmpackenZwischenKompressionTests(unittest.TestCase):
    """.ffpfsc <-> .ffpfs: umpacken statt neu einbetten.

    Beide Richtungen waren frueher gesperrt ("laesst sich nicht nachtraeglich
    entpacken"). Der Hinweis stammte aus der Zeit, als das Programm einen
    Container nicht zuverlaessig auspacken konnte. Der Weg ist derselbe wie
    nach .ffpkg: erst in den Dump-Ordner, dann neu bauen - und genau das muss
    geprueft werden, denn die Quelldatei einfach neu einzubetten ergaebe eine
    Verschachtelungsebene mehr statt eines neuen Containers.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory(prefix="ffpfsc_umpacken_")
        basis = Path(cls._tmp.name)
        cls.quelle = basis / "dump"
        cls.quelle.mkdir()
        cls.soll_dateien, cls.soll_bytes = _dump_anlegen(cls.quelle)
        cls.komprimiert = basis / "spiel.ffpfsc"
        _mkpfs("pack", "folder", str(cls.quelle), str(cls.komprimiert),
               "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _umpacken(self, quelle: Path, ziel: str, *, uncompressed: bool) -> Path:
        gui = _make_gui()
        self.assertTrue(
            gui._mode_ffpfsc_umpacken(str(quelle), ziel, uncompressed=uncompressed),
            msg="Umpacken fehlgeschlagen: " + "".join(gui._log_lines[-8:]),
        )
        endung = ".ffpfs" if uncompressed else ".ffpfsc"
        ergebnis = Path(ziel) / (quelle.stem + endung)
        self.assertTrue(ergebnis.is_file(), f"{ergebnis} fehlt")
        return ergebnis

    def _inhalt_pruefen(self, container: Path) -> None:
        """Packt den Container wieder aus und vergleicht mit der Quelle."""
        with TemporaryDirectory(prefix="ffpfsc_umpacken_pruef_") as ziel:
            gui = _make_gui()
            self.assertTrue(gui._mode_unpack_to_game_folder(str(container), ziel))
            dateien, bytes_gesamt = _ordner_inhalt(Path(ziel) / container.stem)
            self.assertEqual(dateien, self.soll_dateien)
            self.assertEqual(bytes_gesamt, self.soll_bytes)

    def test_ffpfsc_wird_zu_unkomprimierter_ffpfs(self) -> None:
        with TemporaryDirectory(prefix="ffpfsc_zu_ffpfs_") as ziel:
            ergebnis = self._umpacken(self.komprimiert, ziel, uncompressed=True)
            self.assertGreater(ergebnis.stat().st_size, self.komprimiert.stat().st_size,
                               "Unkomprimiert muss groesser sein als komprimiert")
            self.assertEqual(
                PS5ConverterGUI._sniff_image_kind(str(ergebnis)), "pfs",
                "Das Ergebnis muss ein PFS-Container sein")
            self._inhalt_pruefen(ergebnis)

    def test_ffpfs_wird_zu_komprimierter_ffpfsc(self) -> None:
        with TemporaryDirectory(prefix="ffpfs_zu_ffpfsc_") as ziel:
            roh = self._umpacken(self.komprimiert, ziel, uncompressed=True)
            with TemporaryDirectory(prefix="zurueck_") as ziel2:
                zurueck = self._umpacken(roh, ziel2, uncompressed=False)
                self.assertLess(zurueck.stat().st_size, roh.stat().st_size)
                self._inhalt_pruefen(zurueck)

    def test_ergebnis_ist_zweistufig_und_nicht_neu_eingebettet(self) -> None:
        """Der haeufigste Fehlbau waere hier eine Ebene mehr."""
        from ps5_validator.modules.ffpfs_validator import ermittle_bauform  # noqa: PLC0415

        with TemporaryDirectory(prefix="ffpfsc_bauform_pruef_") as ziel:
            ergebnis = self._umpacken(self.komprimiert, ziel, uncompressed=True)
            befund = ermittle_bauform(ergebnis)
            self.assertIsNotNone(befund)
            assert befund is not None
            self.assertEqual(befund["bauform"], "pfs")


@unittest.skipIf(MKPFS_DIR is None, "MkPFS-Quellordner nicht gefunden")
class Aufgabe7QuelleTests(unittest.TestCase):
    """Der AMPR-EMU-Manager muss den Dump sehen, nicht das innere Abbild.

    Aufgabe 7 packt eine .ffpfsc aus, zeigt den Stammverzeichnis-Inhalt im
    Dialog und schreibt ihn danach zurueck. Mit der alten, einstufigen Fassung
    stand bei einem Container mit einer Ebene mehr genau eine .exfat in der
    Liste - und ein Zurueckpacken haette sie als "Dump" wieder eingebettet.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory(prefix="ffpfsc_task7_")
        basis = Path(cls._tmp.name)
        cls.quelle = basis / "dump"
        cls.quelle.mkdir()
        _dump_anlegen(cls.quelle)
        cls.wrapper = basis / "wrapper.ffpfsc"
        _mkpfs("pack", "folder", str(cls.quelle), str(cls.wrapper),
               "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5")
        cls.dreifach = basis / "dreifach.ffpfsc"
        _mkpfs("pack", "file", str(cls.wrapper), str(cls.dreifach), "--version", "PS5")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _stammverzeichnis(self, container: Path) -> list[str]:
        """Faehrt Aufgabe 7 bis zum Dialog und liest die aufgelistete Wurzel.

        Der Suchpfad selbst ist eine lokale Variable; sichtbar wird er ueber
        die Auflistung, die Aufgabe 7 vor dem Dialog ins Protokoll schreibt -
        genau das, was der Benutzer im Fenster zu sehen bekommt.
        """
        gui = _make_gui()
        gui._set_status = lambda *_a, **_k: None
        gui._load_setting = lambda _schluessel, vorgabe: vorgabe
        gui._save_setting = lambda *_a, **_k: None
        gui._mode_ampr_manager(str(container), str(container.parent),
                               automation={"action": "cancel"})

        eintraege: list[str] = []
        sammeln = False
        for zeile in gui._log_lines:
            text = str(zeile).strip()
            if text.startswith(">>> Inhalt des Stammverzeichnisses"):
                sammeln = True
                continue
            if not sammeln:
                continue
            if text.startswith("[Ordner]") or text.startswith("[Datei]"):
                name = text.split("]", 1)[1].strip()
                eintraege.append(name.split("  (")[0].strip())
            elif text.startswith(">>>") or text.startswith("[AUTO]"):
                break
        return eintraege

    def test_exfat_container_zeigt_den_dump(self) -> None:
        eintraege = self._stammverzeichnis(self.wrapper)
        self.assertIn("eboot.bin", eintraege)
        self.assertIn("sce_sys", eintraege)

    def test_eine_ebene_mehr_zeigt_ebenfalls_den_dump(self) -> None:
        eintraege = self._stammverzeichnis(self.dreifach)
        self.assertIn("eboot.bin", eintraege)
        self.assertIn("sce_sys", eintraege)
        self.assertFalse(
            [n for n in eintraege if n.lower().endswith(".exfat")],
            msg=f"Statt des Dumps steht ein Abbild in der Liste: {eintraege}",
        )


@unittest.skipIf(MKPFS_DIR is None, "MkPFS-Quellordner nicht gefunden")
class BauformAnzeigeTests(unittest.TestCase):
    """Der Hinweis neben QUELLE muss die Bauform richtig benennen.

    Geprueft wird die Erkennung selbst und die Anzeigelogik; das Widget wird
    dabei durch einen Platzhalter ersetzt, damit dafuer kein Tk-Fenster noetig
    ist. Ob das Label im Raster sitzt, deckt test_fensterlayout.py ab.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = TemporaryDirectory(prefix="ffpfsc_bauform_")
        basis = Path(cls._tmp.name)
        cls.quelle = basis / "dump"
        cls.quelle.mkdir()
        _dump_anlegen(cls.quelle)

        cls.wrapper = basis / "wrapper.ffpfsc"
        _mkpfs("pack", "folder", str(cls.quelle), str(cls.wrapper),
               "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5")
        cls.flach = basis / "flach.ffpfsc"
        _mkpfs("pack", "folder", "--raw", str(cls.quelle), str(cls.flach),
               "--no-adjust-output-file-extension", "--version", "PS5")
        cls.dreifach = basis / "dreifach.ffpfsc"
        _mkpfs("pack", "file", str(cls.wrapper), str(cls.dreifach), "--version", "PS5")

        # Der eigene Aufbau: aussen Container, innen rohes PFS mit den Dateien.
        inner = basis / "pfs_image.dat"
        _mkpfs("pack", "folder", "--raw", str(cls.quelle), str(inner),
               "--no-compress", "--no-adjust-output-file-extension", "--version", "PS5")
        cls.eigen = basis / "eigen.ffpfsc"
        _mkpfs("pack", "file", str(inner), str(cls.eigen),
               "--no-rename-inner-image", "--no-adjust-output-file-extension", "--version", "PS5")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_bauformen_werden_unterschieden(self) -> None:
        from ps5_validator.modules.ffpfs_validator import ermittle_bauform  # noqa: PLC0415

        for datei, erwartet in (
            (self.wrapper, "exfat"),
            (self.flach, "flach"),
            (self.dreifach, "dreifach"),
            (self.eigen, "pfs"),
        ):
            with self.subTest(datei=datei.name):
                befund = ermittle_bauform(datei)
                self.assertIsNotNone(befund)
                assert befund is not None
                self.assertEqual(befund["bauform"], erwartet)

    def test_keine_containerdatei_blendet_den_hinweis_aus(self) -> None:
        from ps5_validator.modules.ffpfs_validator import ermittle_bauform  # noqa: PLC0415

        self.assertIsNone(ermittle_bauform(self.quelle / "eboot.bin"))

    def test_anzeige_nennt_die_bauform(self) -> None:
        gui = _make_gui()
        gui.src_kind_label = _StubKindLabel()
        gui._schedule_caption_redraw = lambda _fn: None
        gui._bauform_quelle = str(self.wrapper)
        gui._zeige_quell_bauform(str(self.wrapper), {"bauform": "exfat"})
        self.assertIn("exFAT", gui.src_kind_label.text)
        self.assertTrue(gui.src_kind_label.sichtbar)

    def test_eine_ebene_zu_viel_wird_als_warnung_gezeigt(self) -> None:
        gui = _make_gui()
        gui.src_kind_label = _StubKindLabel()
        gui._schedule_caption_redraw = lambda _fn: None
        gui._bauform_quelle = str(self.dreifach)
        gui._zeige_quell_bauform(str(self.dreifach), {"bauform": "dreifach"})
        self.assertIn("Ebene zu viel", gui.src_kind_label.text)
        self.assertEqual(gui.src_kind_label.farbe, gui._COLORS["fg_warning"])

    def test_spaetes_ergebnis_einer_alten_quelle_wird_verworfen(self) -> None:
        """Sonst überschreibt ein langsamer Container den Hinweis der neuen Quelle."""
        gui = _make_gui()
        gui.src_kind_label = _StubKindLabel()
        gui._schedule_caption_redraw = lambda _fn: None
        gui._bauform_quelle = str(self.wrapper)
        gui._zeige_quell_bauform(str(self.wrapper), {"bauform": "exfat"})
        vorher = gui.src_kind_label.text
        # Ergebnis einer inzwischen abgewählten Datei trifft verspätet ein.
        gui._zeige_quell_bauform(str(self.flach), {"bauform": "flach"})
        self.assertEqual(gui.src_kind_label.text, vorher)


class VollstaendigkeitTests(unittest.TestCase):
    """Ein unvollständiges Ergebnis muss als Fehler herauskommen."""

    def _dump(self, ziel: Path) -> None:
        (ziel / "sce_sys").mkdir(parents=True, exist_ok=True)
        (ziel / "sce_sys" / "param.json").write_text('{"titleId":"CUSA00001"}', encoding="utf-8")
        (ziel / "eboot.bin").write_bytes(b"\x7fELF" + bytes(1000))

    def test_vollstaendiger_ordner_wird_angenommen(self) -> None:
        with TemporaryDirectory() as td:
            ziel = Path(td) / "dump"
            self._dump(ziel)
            dateien, bytes_gesamt = _ordner_inhalt(ziel)
            gui = _make_gui()
            self.assertTrue(gui._pruefe_dump_vollstaendig(str(ziel), (dateien, bytes_gesamt)))

    def test_fehlende_bytes_werden_gemeldet(self) -> None:
        with TemporaryDirectory() as td:
            ziel = Path(td) / "dump"
            self._dump(ziel)
            dateien, bytes_gesamt = _ordner_inhalt(ziel)
            gui = _make_gui()
            self.assertFalse(
                gui._pruefe_dump_vollstaendig(str(ziel), (dateien, bytes_gesamt + 5_000_000_000))
            )
            self.assertTrue(
                any("Unvollständig" in zeile for zeile in gui._log_lines),
                msg="Der Fehlbetrag muss im Protokoll stehen",
            )

    def test_fehlende_dateien_werden_gemeldet(self) -> None:
        with TemporaryDirectory() as td:
            ziel = Path(td) / "dump"
            self._dump(ziel)
            dateien, bytes_gesamt = _ordner_inhalt(ziel)
            gui = _make_gui()
            self.assertFalse(
                gui._pruefe_dump_vollstaendig(str(ziel), (dateien + 40, bytes_gesamt))
            )

    def test_ohne_sollwerte_bleibt_es_beim_hinweis(self) -> None:
        with TemporaryDirectory() as td:
            ziel = Path(td) / "dump"
            self._dump(ziel)
            gui = _make_gui()
            self.assertTrue(gui._pruefe_dump_vollstaendig(str(ziel), None))


class VerschiebenTests(unittest.TestCase):
    """Gleichnamige Ordner werden zusammengeführt, nicht ineinandergelegt."""

    def test_gleichnamige_ordner_werden_zusammengefuehrt(self) -> None:
        with TemporaryDirectory() as td:
            quelle = Path(td) / "quelle"
            ziel = Path(td) / "ziel"
            (quelle / "sce_sys").mkdir(parents=True)
            (quelle / "sce_sys" / "param.json").write_text("{}", encoding="utf-8")
            (quelle / "eboot.bin").write_bytes(b"\x7fELF")
            (ziel / "sce_sys").mkdir(parents=True)
            (ziel / "sce_sys" / "icon0.png").write_bytes(b"\x89PNG")

            gui = _make_gui()
            fehler = gui._move_tree_into(str(quelle), str(ziel))

            self.assertEqual(fehler, [])
            self.assertTrue((ziel / "sce_sys" / "param.json").is_file())
            self.assertTrue((ziel / "sce_sys" / "icon0.png").is_file())
            self.assertTrue((ziel / "eboot.bin").is_file())
            self.assertFalse(
                (ziel / "sce_sys" / "sce_sys").exists(),
                msg="shutil.move haette den Ordner ineinandergelegt",
            )

    def test_fehlgeschlagenes_verschieben_wird_gemeldet(self) -> None:
        with TemporaryDirectory() as td:
            quelle = Path(td) / "quelle"
            ziel = Path(td) / "ziel"
            quelle.mkdir()
            ziel.mkdir()
            (quelle / "Media").mkdir()
            (quelle / "Media" / "gross.pak").write_bytes(bytes(64))
            # Im Ziel steht eine Datei dort, wo der Ordner hin soll.
            (ziel / "Media").write_bytes(b"belegt")

            gui = _make_gui()
            fehler = gui._move_tree_into(str(quelle), str(ziel))

            self.assertTrue(fehler, msg="Der Fehlschlag darf nicht verschwiegen werden")
            self.assertIn("Media", fehler[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
