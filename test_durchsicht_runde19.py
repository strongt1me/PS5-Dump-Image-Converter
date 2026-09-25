# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 19 (25.09.2026): Abbruch und Laufzeit.

Zwei Arten von Fehlern, beide ohne falsches Ergebnis und trotzdem aergerlich:

* **"Abbrechen" wirkte nicht.** Das Zusammenfuehren geteilter Pakete (U1-5),
  die Abschlusspruefung (U1-9), die Uebernahme der AMPR-Baender (U2-5), das
  Warten auf einen alten MkPFS-Lauf (H6-4), das Nachkopieren beim
  UFS2Tool-Entpacken (H8-7), die Bibliothekssuche (H8-14) und das "Pruefen"
  im Fenster "PKG bauen" (H11-8) liefen nach dem Druck auf den Knopf weiter -
  Minuten, bei grossen Titeln laenger.
* **Der Fensterfaden wartete auf die Platte.** Das Nachlesen der
  AMPR-Fassungen (H7-9), die Schnellpfade der Vorschau (H4-10) und das
  Aufraeumen eines nicht fortsetzbaren Laufs beim Klick auf STARTEN (H2-5).

U1-10 ist in seiner Wirkung widerlegt: Der fruehere Ausstieg haette nichts
gespart, weil beide Leser den ganzen Baum vorab lesen. Gemessen wird das
hier - und dass die Bedingung deshalb bleiben darf, wie sie ist.
"""
from __future__ import annotations

import ast
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
MKPFS_ORDNER = PROJEKT / "MkPFS-1.0.0"
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde19")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import abbild_metadaten            # noqa: E402
from ps5_validator.utils import abbild_pruefen              # noqa: E402
from ps5_validator.utils import ampr_assetpakete as ap      # noqa: E402
from ps5_validator.utils import pkg_merger                  # noqa: E402
from ps5_validator.utils import prosperopkg                 # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402
from ps5_validator.utils.pkg_reader import FIH_MAGIC        # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


_BAUM: list = []


def _baum() -> ast.Module:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return _BAUM[0]


def _methode(name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(_baum())
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _innere(aeussere: ast.AST, name: str) -> ast.FunctionDef:
    return next(k for k in ast.walk(aeussere)
                if isinstance(k, ast.FunctionDef) and k.name == name)


def _aufrufe(knoten: ast.AST, name: str) -> list[ast.Call]:
    return [k for k in ast.walk(knoten) if isinstance(k, ast.Call)
            and (getattr(k.func, "attr", None) == name
                 or getattr(k.func, "id", None) == name)]


def _schluesselwoerter(aufruf: ast.Call) -> set[str]:
    return {w.arg for w in aufruf.keywords if w.arg}


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._t = lambda schluessel, **_werte: schluessel
    gui.root = _WURZEL
    return gui


def _ordner(test: unittest.TestCase, praefix: str) -> Path:
    pfad = Path(tempfile.mkdtemp(prefix=praefix))
    test.addCleanup(shutil.rmtree, pfad, True)
    return pfad


def _schleife_bis(bedingung, grenze: float = 15.0) -> bool:
    """Laesst eine echte Ereignisschleife laufen, bis ``bedingung`` gilt.

    ``update()`` genuegt nicht: Tk nimmt Aufrufe aus einem Faden nur an,
    wenn der Hauptfaden in ``mainloop`` steht (siehe test_durchsicht_runde8).
    """
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if bedingung() or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(20, _takt)

    _WURZEL.after(20, _takt)
    _WURZEL.mainloop()
    return bool(bedingung())


class _Zaehler:
    """Ein Abbruch, der erst nach ``ab`` Fragen zutrifft."""

    def __init__(self, ab: int) -> None:
        self.ab = ab
        self.fragen = 0

    def __call__(self) -> bool:
        self.fragen += 1
        return self.fragen > self.ab


def _teilsatz(ordner: Path, groesse: int = 3 * 1024 * 1024) -> Path:
    """Ein gueltiger geteilter Satz aus EINEM Wurzelteil - ``groesse`` Bytes."""
    teil = bytearray(groesse)
    teil[0:4] = FIH_MAGIC
    teil[0x05] = 0x00
    import struct
    struct.pack_into("<H", teil, 0x06, 3)
    struct.pack_into("<Q", teil, 0x10, 0x10)
    struct.pack_into("<Q", teil, 0x18, groesse - 0x10)
    struct.pack_into("<Q", teil, 0x58, groesse)
    pfad = ordner / "SPIEL_0.pkg"
    pfad.write_bytes(bytes(teil))
    return pfad


# ---------------------------------------------------------------- U1-5

class MergeAbbruchTests(unittest.TestCase):
    """U1-5: Ein Satz von 50-100 GB liess sich nicht anhalten."""

    def test_abbruch_mitten_im_satz_entfernt_die_tmp(self) -> None:
        ordner = _ordner(self, "r19_merge_")
        teil = _teilsatz(ordner)
        ziel = ordner / "aus" / "SPIEL-merged.pkg"
        abbruch = _Zaehler(ab=2)                  # der dritte Block haelt an
        with self.assertRaises(pkg_merger.MergeAbgebrochen):
            pkg_merger.merge_split_set([str(teil)], None, str(ziel), abbruch=abbruch)
        self.assertGreater(abbruch.fragen, 2, "Der Abbruch wurde nie gefragt.")
        self.assertFalse(ziel.exists(), "Ein Ergebnis steht trotz Abbruch da.")
        self.assertEqual([], sorted(p.name for p in ziel.parent.iterdir()),
                         "Die angefangene .tmp blieb im Zielordner liegen.")

    def test_ohne_abbruch_wird_ganz_zusammengefuehrt(self) -> None:
        ordner = _ordner(self, "r19_merge_")
        teil = _teilsatz(ordner)
        ziel = ordner / "SPIEL-merged.pkg"
        erg = pkg_merger.merge_split_set([str(teil)], None, str(ziel),
                                         abbruch=lambda: False)
        self.assertEqual(teil.stat().st_size, erg.total_size)

    def test_merge_directory_reicht_ihn_weiter(self) -> None:
        ordner = _ordner(self, "r19_merge_")
        _teilsatz(ordner, 64 * 1024)
        with self.assertRaises(pkg_merger.MergeAbgebrochen):
            pkg_merger.merge_directory(str(ordner), str(ordner / "aus"),
                                       abbruch=lambda: True)

    def test_die_meldung_ist_uebersetzbar(self) -> None:
        ordner = _ordner(self, "r19_merge_")
        teil = _teilsatz(ordner, 64 * 1024)
        texte = {"abgebrochen": STRINGS["pkg_merger.log_abgebrochen"]["en"]}
        with self.assertRaises(pkg_merger.MergeAbgebrochen) as fang:
            pkg_merger.merge_split_set([str(teil)], None, str(ordner / "x.pkg"),
                                       texte=texte, abbruch=lambda: True)
        self.assertIn("Merge cancelled", str(fang.exception))
        self.assertIn("SPIEL", str(fang.exception))


class ProgrammendeWartetTests(unittest.TestCase):
    """U1-5: Beendet wird erst, wenn der abgebrochene Satz seine .tmp los ist."""

    def test_warten_bis_der_zaehler_faellt(self) -> None:
        gui = _gui()
        gui._pkg_merge_laeuft = 1

        def _spaeter() -> None:
            time.sleep(0.3)
            gui._pkg_merge_laeuft = 0

        threading.Thread(target=_spaeter, daemon=True).start()
        anfang = time.monotonic()
        self.assertTrue(gui._auf_pkg_merge_warten(frist_s=5.0))
        self.assertGreaterEqual(time.monotonic() - anfang, 0.25)

    def test_die_frist_gilt(self) -> None:
        gui = _gui()
        gui._pkg_merge_laeuft = 1
        anfang = time.monotonic()
        self.assertFalse(gui._auf_pkg_merge_warten(frist_s=0.2))
        self.assertLess(time.monotonic() - anfang, 2.0)

    def test_on_closing_wartet_vor_dem_abbau(self) -> None:
        abbau = _innere(_methode("on_closing"), "_shutdown")
        rufe = [getattr(k.func, "attr", "") for k in ast.walk(abbau)
                if isinstance(k, ast.Call)]
        self.assertIn("_auf_pkg_merge_warten", rufe,
                      "Das Programmende wartet nicht auf den abgebrochenen Merge.")
        self.assertLess(rufe.index("_auf_pkg_merge_warten"),
                        rufe.index("_force_dismount_all"))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class MergerFensterTests(unittest.TestCase):
    """U1-5 am Fenster: Knopf "Abbrechen" und Schliessen mitten im Satz."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def _ersetzen(self, ziel, name: str, wert) -> None:
        flicken = mock.patch.object(ziel, name, wert)
        flicken.start()
        self.addCleanup(flicken.stop)

    def _fenster_mit_laufendem_satz(self):
        ordner = _ordner(self, "r19_mfenster_")
        ziel = ordner / "aus"
        ziel.mkdir()
        zustand = {"gestartet": False, "angehalten": False}

        def _zusammen(_teile, _meta, ausgabe, *, abbruch=None, **_k):
            zustand["gestartet"] = True
            while not (abbruch is not None and abbruch()):
                time.sleep(0.02)
            zustand["angehalten"] = True
            raise pkg_merger.MergeAbgebrochen("[stop] abgebrochen")

        self._ersetzen(APP, "merge_split_set", _zusammen)
        self._ersetzen(APP.filedialog, "askdirectory", lambda **_k: str(ziel))
        satz = types.SimpleNamespace(base_name="Spiel", has_root=True,
                                     numbered=["a"], meta=None, ordered_numbered=["a"])
        vorher = set(_WURZEL.winfo_children())
        self.app._render_pkg_merger_window(str(ordner), [satz], [])
        _WURZEL.update()
        fenster = [w for w in _WURZEL.winfo_children()
                   if w not in vorher and isinstance(w, tk.Toplevel)][-1]
        self.addCleanup(lambda: fenster.winfo_exists() and fenster.destroy())
        baum = next(w for w in self._alle(fenster) if isinstance(w, ttk.Treeview))
        baum.selection_set("0")
        self._knopf(fenster, self.app._t("pkg_merger.merge_selected_button")).invoke()
        self.assertTrue(_schleife_bis(lambda: zustand["gestartet"], 5.0))
        return fenster, zustand

    @staticmethod
    def _alle(widget):
        for kind in widget.winfo_children():
            yield kind
            yield from MergerFensterTests._alle(kind)

    def _knopf(self, fenster, text: str):
        for widget in self._alle(fenster):
            try:
                if str(widget.cget("text")) == text:
                    return widget
            except tk.TclError:
                continue
        raise AssertionError("Knopf %r fehlt" % text)

    @staticmethod
    def _faden_fertig() -> bool:
        return not any(f.name == "pkg-merger" for f in threading.enumerate())

    def test_der_knopf_haelt_den_satz_an(self) -> None:
        fenster, zustand = self._fenster_mit_laufendem_satz()
        halt = self._knopf(fenster, self.app._t("action.cancel"))
        self.assertEqual("normal", str(halt.cget("state")))
        halt.invoke()
        self.assertTrue(_schleife_bis(self._faden_fertig, 5.0))
        self.assertTrue(zustand["angehalten"])
        self.assertEqual(0, self.app._pkg_merge_laeuft)
        _WURZEL.update()
        self.assertTrue(fenster.winfo_exists())
        self.assertEqual("disabled", str(halt.cget("state")))

    def test_schliessen_fragt_und_bricht_ab(self) -> None:
        fenster, zustand = self._fenster_mit_laufendem_satz()
        gefragt: list = []

        def _frage(*args, **_k):
            gefragt.append(args)
            return True

        # Das X der Titelleiste - derselbe Weg wie der Umschalter.
        with mock.patch.object(APP.messagebox, "askyesno", _frage), \
                mock.patch.object(APP.messagebox, "showinfo",
                                  side_effect=AssertionError("verweigert")) as nein:
            fenster.tk.call(fenster.protocol("WM_DELETE_WINDOW"))
            _schleife_bis(self._faden_fertig, 5.0)
        nein.assert_not_called()
        self.assertEqual(1, len(gefragt), "Beim Schliessen wurde nicht gefragt.")
        self.assertFalse(fenster.winfo_exists(),
                         "Das Fenster weigerte sich wie vor Runde 19.")
        self.assertTrue(zustand["angehalten"], "Der Satz lief nach dem Schliessen weiter.")
        self.assertEqual(0, self.app._pkg_merge_laeuft)


# ---------------------------------------------------------------- U1-9

class AbschlusspruefungAbbruchTests(unittest.TestCase):
    """U1-9: Nach "Abbrechen" lief die Abschlusspruefung ganz."""

    def _stand(self) -> abbild_pruefen.Pruefstand:
        return abbild_pruefen.Pruefstand(text=lambda s, **_w: s)

    def test_nach_abbruch_wird_nichts_gelesen(self) -> None:
        ordner = _ordner(self, "r19_pruef_")
        (ordner / "a.bin").write_bytes(b"x" * 1000)
        befund = self._stand()._verify_output_artifact(
            "universal_convert", str(ordner), abbruch=lambda: True)
        self.assertTrue(befund.get("abgebrochen"))
        self.assertFalse(befund["ok"])
        self.assertEqual("verify.abgebrochen", befund["detail"])

    def test_die_pruefsumme_haelt_an(self) -> None:
        ordner = _ordner(self, "r19_pruef_")
        datei = ordner / "ergebnis.exfat"
        datei.write_bytes(os.urandom(9 * 1024 * 1024))
        abbruch = _Zaehler(ab=1)                  # die Vorab-Frage verneinen
        befund = self._stand()._verify_output_artifact("pack_file", str(datei),
                                                       abbruch=abbruch)
        self.assertTrue(befund.get("abgebrochen"),
                        "Die Pruefsumme lief nach dem Abbruch zu Ende.")
        self.assertEqual("", befund["sha256"])

    def test_ohne_abbruch_wie_bisher(self) -> None:
        ordner = _ordner(self, "r19_pruef_")
        datei = ordner / "ergebnis.exfat"
        datei.write_bytes(b"y" * 4096)
        befund = self._stand()._verify_output_artifact("pack_file", str(datei))
        self.assertTrue(befund["ok"])
        self.assertNotIn("abgebrochen", befund)

    def test_ffpkg_bekommt_den_abbruch(self) -> None:
        """Der Validator bricht selbst ab - er muss ihn nur bekommen."""
        ordner = _ordner(self, "r19_pruef_")
        datei = ordner / "spiel.ffpkg"
        datei.write_bytes(b"z" * 4096)
        stand = self._stand()
        erhalten: list = []

        def _validieren(pfad, *, base_result=None, abbruch=None):
            erhalten.append(abbruch)
            base_result.update({"ok": False, "detail": "CANCELLED"})
            return base_result

        stand._validate_ffpkg_artifact = _validieren
        abbruch = _Zaehler(ab=1)
        befund = stand._verify_output_artifact("pack_folder", str(datei), abbruch=abbruch)
        self.assertEqual([abbruch], erhalten, "Der Validator bekam keinen Abbruch.")
        self.assertTrue(befund.get("abgebrochen"))
        self.assertEqual("verify.abgebrochen", befund["detail"])

    def test_der_hoerer_wirft(self) -> None:
        """Der Hoerer allein - MkPFS selbst prueft MkpfsPruefungAbbruchTests."""
        stand = self._stand()

        def _pruefung(image, progress=None):     # Signatur wie verify_pfs_image
            return image

        class _Progress:                          # wie mkpfs.pbar.Progress
            def __init__(self, enabled=True, listener=None):
                self.listener = listener

            def step(self, phase, done, total, bytes_processed=0):
                if self.listener:
                    self.listener("step", phase, done, total, bytes_processed)

        pbar = types.ModuleType("mkpfs.pbar")
        pbar.Progress = _Progress
        with mock.patch.dict(sys.modules, {"mkpfs.pbar": pbar}):
            argument = stand._fortschritt_argument(_pruefung, abbruch=lambda: True)
        self.assertIn("progress", argument)
        with self.assertRaises(abbild_pruefen._PruefungAbgebrochen):
            argument["progress"].step("verify", 0, 10)
        with mock.patch.dict(sys.modules, {"mkpfs.pbar": pbar}):
            ohne = stand._fortschritt_argument(_pruefung)         # ohne Abbruch: still
        ohne["progress"].step("verify", 0, 10)

    def test_die_abschlusspruefung_reicht_ihn_weiter(self) -> None:
        gui = _gui()
        gerufen: list = []
        gui._verify_output_artifact = lambda *a, **k: gerufen.append(k) or {"ok": True}
        gui._abschlusspruefung("pack_file", "x.ffpfsc", abbruch=len)
        self.assertEqual([{"abbruch": len}], gerufen)

    def test_alle_vier_stellen_der_aufgabe_geben_ihn_mit(self) -> None:
        rufe = _aufrufe(_methode("_run_engine_thread"), "_abschlusspruefung")
        self.assertGreaterEqual(len(rufe), 4)
        for ruf in rufe:
            with self.subTest(zeile=ruf.lineno):
                self.assertIn("abbruch", _schluesselwoerter(ruf))

    def test_abbruch_waehrend_der_pruefung_ist_kein_fehlschlag(self) -> None:
        """Kein Fehlerdialog, Bericht als abgebrochen (Erfolgszweig)."""
        lauf = _methode("_run_engine_thread")
        berichte = [k for k in _aufrufe(lauf, "_write_task_report")
                    if any(w.arg == "aborted" and isinstance(w.value, ast.Name)
                           and w.value.id == "pruefung_abgebrochen" for w in k.keywords)]
        self.assertEqual(1, len(berichte),
                         "Der Erfolgszweig meldet einen Abbruch in der Pruefung "
                         "nicht als Abbruch.")
        fertig = _innere(lauf, "_finish_success")
        self.assertIn("_abgebrochen", [a.arg for a in fertig.args.args])
        erste = fertig.body[1] if isinstance(fertig.body[0], ast.Expr) else fertig.body[0]
        self.assertIsInstance(erste, ast.If)
        self.assertIn("_abgebrochen", ast.unparse(erste.test))


#: Packt eine kleine .ffpfsc und prueft sie mit Abbruch - im eigenen Prozess,
#: denn hier kann laengst ein anderes mkpfs geladen sein (test_mkpfs_fassung).
PRUEFUNG_MIT_ABBRUCH = r'''
import json, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[3])
basis = Path(sys.argv[2])
from mkpfs import cli
from ps5_validator.utils import abbild_pruefen
quelle = basis / "spiel.exfat"
quelle.write_bytes(os.urandom(12 * 1024 * 1024))
ziel = basis / "spiel.ffpfsc"
rc = cli.main(["pack", "file", "--compress", "--no-adjust-output-file-extension",
               "--no-rename-inner-image", "--version", "PS5", "--inode-bits", "32",
               "--cpu-count", "1", "--compression-level", "1", "--block-size", "65536",
               "--no-verify-structure", str(quelle), str(ziel)])
gefragt = []
def abbruch():
    gefragt.append(1)
    return len(gefragt) > 1
stand = abbild_pruefen.Pruefstand(text=lambda s, **w: s,
                                  mkpfs_ordner_holen=lambda: sys.argv[1])
befund = stand._verify_output_artifact("pack_file", str(ziel), abbruch=abbruch)
ohne = stand._verify_output_artifact("pack_file", str(ziel))
print("ERGEBNIS:" + json.dumps({"rc": rc, "befund": befund, "gefragt": len(gefragt),
                                "ohne_ok": ohne["ok"]}))
'''


class MkpfsPruefungAbbruchTests(unittest.TestCase):
    """U1-9: Die Dekodierpruefung einer .ffpfsc haelt wirklich an.

    Belegt zugleich, dass MkPFS die Ausnahme aus dem Hoerer durchlaesst -
    davon haengt der ganze Weg ab.
    """

    def test_die_pruefung_haelt_an(self) -> None:
        with tempfile.TemporaryDirectory(prefix="r19_mkpfs_") as basis:
            lauf = subprocess.run(
                [sys.executable, "-c", PRUEFUNG_MIT_ABBRUCH, str(MKPFS_ORDNER),
                 basis, str(PROJEKT)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        zeilen = [z for z in lauf.stdout.splitlines() if z.startswith("ERGEBNIS:")]
        self.assertTrue(zeilen, "Kein Ergebnis:\n%s\n%s"
                        % (lauf.stdout[-1500:], lauf.stderr[-1500:]))
        r = json.loads(zeilen[-1][len("ERGEBNIS:"):])
        self.assertEqual(0, r["rc"])
        self.assertTrue(r["ohne_ok"], "Ohne Abbruch muss die Pruefung bestehen.")
        self.assertGreaterEqual(r["gefragt"], 2, "Der Hoerer fragte nie.")
        self.assertTrue(r["befund"].get("abgebrochen"),
                        "Die Pruefung lief trotz Abbruch zu Ende: %r" % r["befund"])
        self.assertEqual("mkpfs-verify", r["befund"]["method"])


# ---------------------------------------------------------------- U2-5

class UebernahmeAbbruchTests(unittest.TestCase):
    """U2-5: Die Baender liessen sich nicht anhalten - und nichts Halbes bleibt."""

    def _bestand(self) -> tuple[Path, Path]:
        basis = _ordner(self, "r19_uebern_")
        aus = basis / "aus"
        app0 = basis / "app0"
        aus.mkdir()
        app0.mkdir()
        (aus / ap.MANIFEST_NAME).write_bytes(b"NEU")
        (aus / ap.LAUFZEIT_NAME).write_bytes(b"R")
        (aus / ap.PRUEFSUMMEN_NAME).write_bytes(b"C")
        for name in ("band_0.pak", "band_1.pak"):
            (aus / name).write_bytes(os.urandom(9 * 1024 * 1024))
        (app0 / ap.MANIFEST_NAME).write_bytes(b"ALT")
        return aus, app0

    def test_abbruch_laesst_den_alten_satz_stehen(self) -> None:
        aus, app0 = self._bestand()
        # Je kleine Datei zwei Fragen, je Band drei: die achte faellt in den
        # zweiten Block des ersten Bands - mitten in einer 8-MiB-Kopie.
        abbruch = _Zaehler(ab=7)
        with self.assertRaises(ap.PackFehler) as fang:
            ap.bestand_uebernehmen(str(aus), str(app0),
                                   baender=["band_0.pak", "band_1.pak"],
                                   abbruch=abbruch)
        self.assertEqual("ampr_pack.abgebrochen", str(fang.exception))
        self.assertEqual(8, abbruch.fragen, "Der Abbruch traf nicht mitten ins Band.")
        self.assertEqual(b"ALT", (app0 / ap.MANIFEST_NAME).read_bytes(),
                         "Der fruehere Satz wurde angetastet.")
        self.assertEqual([ap.MANIFEST_NAME], sorted(p.name for p in app0.iterdir()),
                         "Zwischenstaende oder Teile des neuen Satzes blieben liegen.")

    def test_ohne_abbruch_kommt_alles_an(self) -> None:
        aus, app0 = self._bestand()
        anzahl = ap.bestand_uebernehmen(str(aus), str(app0),
                                        baender=["band_0.pak", "band_1.pak"],
                                        abbruch=lambda: False)
        self.assertEqual(5, anzahl)
        self.assertEqual((aus / "band_1.pak").read_bytes(),
                         (app0 / "band_1.pak").read_bytes())
        self.assertEqual(os.stat(aus / "band_1.pak").st_mtime_ns // 10 ** 6,
                         os.stat(app0 / "band_1.pak").st_mtime_ns // 10 ** 6,
                         "Die Zeitstempel kamen nicht mit (copystat).")

    def test_der_aufrufer_gibt_ihn_mit(self) -> None:
        rufe = _aufrufe(_methode("_ampr_assetpakete_bauen"), "bestand_uebernehmen")
        self.assertEqual(1, len(rufe))
        self.assertIn("abbruch", _schluesselwoerter(rufe[0]))


# ---------------------------------------------------------------- H6-4

class WartenAbbruchTests(unittest.TestCase):
    """H6-4: Bis zu 15 Minuten "Warte auf Abschluss" nach dem Abbrechen."""

    def _gui(self):
        gui = _gui()
        gui._pending_mkpfs_engine_done = threading.Event()     # nie gesetzt
        gui._pending_mkpfs_target_path = ""
        return gui

    def test_abbruch_beendet_das_warten(self) -> None:
        gui = self._gui()
        anfang = time.monotonic()
        frei = gui._wait_for_pending_mkpfs_background("", timeout_s=3.0,
                                                      abbruch=lambda: True)
        self.assertFalse(frei, "Das Warten ging ueber den Abbruch hinweg.")
        self.assertLess(time.monotonic() - anfang, 2.0)
        self.assertIn("log.warten_abgebrochen", gui.protokoll)
        self.assertIsNotNone(gui._pending_mkpfs_engine_done,
                             "Der alte Lauf muss vorgemerkt bleiben.")

    def test_ohne_abbruch_wie_bisher(self) -> None:
        gui = self._gui()
        self.assertTrue(gui._wait_for_pending_mkpfs_background("", timeout_s=0.3))
        gui._pending_mkpfs_engine_done.set()
        self.assertTrue(gui._wait_for_pending_mkpfs_background(""))
        self.assertIsNone(gui._pending_mkpfs_engine_done)

    def test_die_aufgabenwege_geben_ihn_mit_und_halten_an(self) -> None:
        rufe = [k for k in _aufrufe(_baum(), "_wait_for_pending_mkpfs_background")
                if k.args]
        self.assertEqual(6, len(rufe), "Die Zahl der Aufgabenwege hat sich geaendert.")
        eltern = {kind: knoten for knoten in ast.walk(_baum())
                  for kind in ast.iter_child_nodes(knoten)}
        for ruf in rufe:
            with self.subTest(zeile=ruf.lineno):
                self.assertIn("abbruch", _schluesselwoerter(ruf))
                ober = eltern.get(eltern.get(ruf))
                self.assertIsInstance(ober, ast.If,
                                      "Der Rueckgabewert wird nicht ausgewertet.")

    def test_pkg_bauen_wartet_ohne_abbruch(self) -> None:
        """Dort wird NACH einem Abbruch gewartet - sonst loescht es, waehrend MkPFS schreibt."""
        rufe = _aufrufe(_methode("_show_pkg_bauen"), "_wait_for_pending_mkpfs_background")
        self.assertEqual(1, len(rufe))
        self.assertNotIn("abbruch", _schluesselwoerter(rufe[0]))


# ---------------------------------------------------------------- H8-7

class NachkopierenTests(unittest.TestCase):
    """H8-7: Das Nachkopieren lief stumm und bis zur letzten Datei."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.aussen = next(k for k in ast.walk(_baum()) if isinstance(k, ast.FunctionDef)
                          and any(isinstance(i, ast.FunctionDef)
                                  and i.name == "_einzeln_nachkopieren"
                                  for i in ast.walk(k) if i is not k))
        cls.innen = _innere(cls.aussen, "_einzeln_nachkopieren")

    def test_jeder_block_fragt_nach_dem_abbruch(self) -> None:
        schleifen = [k for k in ast.walk(self.innen) if isinstance(k, ast.While)]
        self.assertTrue(schleifen)
        self.assertIn("is_running", ast.unparse(schleifen[0]),
                      "Die Blockschleife fragt nicht nach dem Abbruch.")

    def test_es_meldet_sich(self) -> None:
        self.assertTrue(_aufrufe(self.innen, "_fortschritt_melden"),
                        "Balken und Groessenfeld stehen beim Nachkopieren still.")

    def test_der_poller_meldet_ueber_denselben_weg(self) -> None:
        self.assertTrue(_aufrufe(_innere(self.aussen, "_poll"), "_fortschritt_melden"))

    def test_jede_datei_fragt_nach_dem_abbruch(self) -> None:
        schleifen = [k for k in ast.walk(self.aussen) if isinstance(k, ast.For)
                     and _aufrufe(k, "_einzeln_nachkopieren")]
        self.assertEqual(1, len(schleifen))
        self.assertIn("is_running", ast.unparse(schleifen[0]))


# ---------------------------------------------------------------- H8-14

class BibliothekSucheTests(unittest.TestCase):
    """H8-14: Alte Suchlaeufe lasen alle Abbilder zu Ende."""

    def _gui(self):
        gui = _gui()
        gui.gelesen = []
        gui._read_game_meta = lambda pfad, deep_scan=False: gui.gelesen.append(pfad) or {}
        return gui

    def test_der_abbruch_geht_in_die_suche(self) -> None:
        """Die Suche selbst haelt an - nicht erst das Einlesen danach.

        Die erste Fassung dieses Tests blieb in der Gegenprobe gruen: Ohne
        Weitergabe fing die Schleife ueber die Funde den Abbruch ab, der
        Durchlauf ueber die Platte lief aber ganz.
        """
        ordner = _ordner(self, "r19_bib_")
        (ordner / "Spiel" / "sce_sys").mkdir(parents=True)
        (ordner / "Spiel" / "sce_sys" / "param.json").write_text("{}")
        gui = self._gui()
        self.assertEqual(1, len(gui._library_scan_folder(str(ordner))))
        echt = APP.bibliothek_bestand.ordner_durchsuchen
        erhalten: list = []

        def _suchen(wurzel, **kwargs):
            erhalten.append(kwargs.get("abbruch"))
            return echt(wurzel, **kwargs)

        def abbruch() -> bool:
            return True

        with mock.patch.object(APP.bibliothek_bestand, "ordner_durchsuchen", _suchen):
            self.assertEqual([], gui._library_scan_folder(str(ordner), abbruch=abbruch))
        self.assertEqual([abbruch], erhalten, "Die Suche selbst bekam keinen Abbruch.")

    def test_der_abbruch_gilt_auch_beim_einlesen(self) -> None:
        gui = self._gui()
        funde = [{"pfad": "D:\\S%d" % i, "art": "folder", "groesse": None, "name": "S"}
                 for i in range(3)]
        with mock.patch.object(APP.bibliothek_bestand, "ordner_durchsuchen",
                               lambda *_a, **_k: funde):
            self.assertEqual([], gui._library_scan_folder("D:\\", abbruch=lambda: True))
        self.assertEqual([], gui.gelesen, "Trotz Abbruch wurde eingelesen.")

    def test_die_seite_gibt_ihn_mit(self) -> None:
        seite = _methode("_render_library_window")
        rufe = _aufrufe(seite, "_library_scan_folder")
        self.assertEqual(1, len(rufe))
        self.assertIn("abbruch", _schluesselwoerter(rufe[0]))

    def test_mit_der_seite_verfallen_ihre_suchen(self) -> None:
        seite = _methode("_render_library_window")
        bindungen = [k for k in _aufrufe(seite, "bind")
                     if k.args and isinstance(k.args[0], ast.Constant)
                     and k.args[0].value == "<Destroy>"]
        self.assertEqual(1, len(bindungen))
        rueckruf = _innere(seite, bindungen[0].args[1].id)
        self.assertIn('ansicht["suchlauf"] += 1', ast.unparse(rueckruf).replace("'", '"'))


# ---------------------------------------------------------------- H11-8

class PkgPruefenTests(unittest.TestCase):
    """H11-8: "Abbrechen" beim Pruefen beendete den falschen Prozess."""

    def test_pruefen_legt_den_prozess_ab(self) -> None:
        ablage: dict = {}
        gesehen: dict = {}

        def _laufen(argumente, melden=None, zeitgrenze=0.0, prozess_ablage=None,
                    texte=None):
            gesehen["ablage"] = prozess_ablage
            return 0, ["RESULT: READY"]

        with mock.patch.object(prosperopkg, "_laufen_lassen", _laufen):
            prosperopkg.pruefen("D:\\Dump", prozess_ablage=ablage)
        self.assertIs(ablage, gesehen.get("ablage"))

    def test_das_fenster_gibt_seine_ablage(self) -> None:
        fenster = _methode("_show_pkg_bauen")
        pruefen = _innere(fenster, "_pruefen")
        rufe = _aufrufe(pruefen, "pruefen")
        self.assertEqual(1, len(rufe))
        self.assertIn("prozess_ablage", _schluesselwoerter(rufe[0]))
        self.assertIn('laeuft["prozess"] = None',
                      ast.unparse(pruefen).replace("'", '"'),
                      "Ein alter Bauprozess bleibt in der Ablage stehen.")

    def test_schliessen_waehrend_der_pruefung_fragt_nicht_nach_dem_bau(self) -> None:
        schliessen = _innere(_methode("_show_pkg_bauen"), "_beim_schliessen")
        text = ast.unparse(schliessen)
        self.assertIn("pruefung", text)
        self.assertLess(text.index("pruefung"), text.index("askyesno"),
                        "Die Frage nach dem Bau kommt vor der Unterscheidung.")


# ---------------------------------------------------------------- H7-9

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Tk")
class AmprNachlesenTests(unittest.TestCase):
    """H7-9: Der Vorrat des Anwenders wurde im Fensterfaden gelesen."""

    def _gui(self):
        gui = _gui()
        gui.lesefaeden = []
        gui.gefuellt = []

        def _alle(explicit: str = "", nur_programmnah: bool = False):
            gui.lesefaeden.append(threading.current_thread() is threading.main_thread())
            return [{"lib": "libSceAmpr.sprx", "version": "9.9", "variant": "release"}]

        gui._ampr_alle_fassungen = _alle
        gui._ampr_versionsliste_fuellen = (
            lambda nur_programmnah=False, eintraege=None: gui.gefuellt.append(eintraege))
        gui._on_integration_changed = lambda speichern=True: None
        return gui

    def test_gelesen_wird_im_faden_eingetragen_im_hauptfaden(self) -> None:
        gui = self._gui()
        gui._ampr_versionsliste_nachladen()
        self.assertTrue(_schleife_bis(lambda: gui.gefuellt, 10.0),
                        "Das Ergebnis kam nie an.")
        self.assertEqual([False], gui.lesefaeden,
                         "Der Vorrat wurde im Fensterfaden gelesen.")
        self.assertEqual("9.9", gui.gefuellt[0][0]["version"])
        self.assertEqual(gui.gefuellt[0], gui._ampr_fassungen_gelesen)

    def test_ein_zweiter_anstoss_stapelt_keine_faeden(self) -> None:
        gui = self._gui()
        sperre = threading.Event()
        alt = gui._ampr_alle_fassungen
        eintritte: list = []

        def _langsam(*a, **k):
            eintritte.append(1)
            sperre.wait(5)
            return alt(*a, **k)

        gui._ampr_alle_fassungen = _langsam
        gui._ampr_versionsliste_nachladen()
        gui._ampr_versionsliste_nachladen()
        gui._ampr_versionsliste_nachladen()
        time.sleep(0.3)
        self.assertEqual(1, len(eintritte), "Jeder Anstoss startete einen eigenen Faden.")
        sperre.set()
        self.assertTrue(_schleife_bis(lambda: len(gui.gefuellt) >= 2, 10.0),
                        "Das vorgemerkte zweite Nachlesen kam nicht.")
        self.assertEqual(2, len(eintritte))

    def test_die_liste_selbst_liest_nie_den_ganzen_vorrat(self) -> None:
        gui = _gui()
        gefragt: list = []
        gui._ampr_alle_fassungen = (
            lambda explicit="", nur_programmnah=False: gefragt.append(nur_programmnah) or [])
        gui.ampr_version_combo = ttk.Combobox(_WURZEL)
        self.addCleanup(gui.ampr_version_combo.destroy)
        gui.ampr_version_var = tk.StringVar(master=_WURZEL)
        gui._ampr_methode = lambda: APP.AMPR_METHODE_NORMAL
        gui._load_setting = lambda _k, vorgabe=None: vorgabe
        gui._ampr_fassungen_gelesen = None
        gui._ampr_versionsliste_fuellen()
        self.assertEqual([True], gefragt,
                         "Ohne gelesenen Stand las die Liste den ganzen Vorrat.")
        gui._ampr_fassungen_gelesen = []
        gui._ampr_versionsliste_fuellen()
        self.assertEqual([True], gefragt, "Trotz gelesenem Stand neu gelesen.")

    def test_der_methodenwechsel_liest_im_faden_nach(self) -> None:
        self.assertTrue(_aufrufe(_methode("_on_ampr_methode_changed"),
                                 "_ampr_versionsliste_nachladen"))

    def test_die_kommandozeile_traegt_vor_dem_start_ein(self) -> None:
        cli = next(k for k in _baum().body if isinstance(k, ast.FunctionDef)
                   and k.name == "_run_cli")
        fuellen = _aufrufe(cli, "_ampr_versionsliste_fuellen")
        starten = _aufrufe(cli, "_launch_task")
        self.assertTrue(fuellen, "Die Kommandozeile startet ohne den ganzen Vorrat.")
        self.assertIn("eintraege", _schluesselwoerter(fuellen[0]))
        self.assertLess(fuellen[0].lineno, starten[0].lineno)


# ---------------------------------------------------------------- H4-10

@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class VorschauPfadeTests(unittest.TestCase):
    """H4-10: listdir und Berichtsdateien im Fensterfaden."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        _WURZEL.update_idletasks()

    def test_die_schnellpfade_kommen_aus_einem_faden(self) -> None:
        ordner = _ordner(self, "r19_vorschau_")
        datei = ordner / "Spiel.ffpfsc"
        datei.write_bytes(b"\0" * 4096)
        faeden: list = []

        def _kandidaten(src, mode, include_report_source=True):
            faeden.append(threading.current_thread() is threading.main_thread())
            return []

        flicken = mock.patch.object(self.app, "_preview_candidate_dirs", _kandidaten)
        flicken.start()
        self.addCleanup(flicken.stop)
        self.app.is_running = False
        self.app.current_mode.set("unpack_to_exfat")
        self.app.source_path.set(str(datei))
        self.app._on_source_path_changed()
        self.assertTrue(_schleife_bis(lambda: faeden, 10.0),
                        "Die Schnellpfade wurden nie ermittelt.")
        self.assertNotIn(True, faeden, "Die Schnellpfade kamen aus dem Fensterfaden.")


# ---------------------------------------------------------------- H2-5

class ResteRaeumenTests(unittest.TestCase):
    """H2-5: rmtree der Reste im Klick auf STARTEN."""

    def test_der_klick_loescht_nichts(self) -> None:
        start = _methode("_launch_task")
        for name in ("_clear_runtime_checkpoint", "_cleanup_checkpoint_artifacts",
                     "_rmtree_force"):
            with self.subTest(aufruf=name):
                self.assertEqual([], [k.lineno for k in _aufrufe(start, name)])
        self.assertIn("self._checkpoint_reste = resume_cp", ast.unparse(start))

    def test_der_aufgabenfaden_raeumt_zuerst(self) -> None:
        lauf = _methode("_run_engine_thread")
        rufe = [getattr(k.func, "attr", "") for k in ast.walk(lauf)
                if isinstance(k, ast.Call)]
        self.assertIn("_checkpoint_reste_raeumen", rufe)
        self.assertLess(rufe.index("_checkpoint_reste_raeumen"),
                        rufe.index("_snapshot_exit_cleanup_paths"))

    def test_die_reste_verschwinden_mit_statuszeile(self) -> None:
        basis = _ordner(self, "r19_reste_")
        reste = basis / "ps5conv_lauf"
        (reste / "unter").mkdir(parents=True)
        (reste / "unter" / "gross.bin").write_bytes(b"x" * 16)
        gui = _gui()
        gui.status = []
        gui._set_status = gui.status.append
        gui._exit_cleanup_lock = threading.RLock()
        gui._session_exit_cleanup_paths = set()
        gui._is_managed_temp_path = lambda _pfad: True
        gui._checkpoint_reste = {"tmp_dir": str(reste)}
        gui._checkpoint_reste_raeumen()
        self.assertFalse(reste.exists())
        self.assertEqual(["status.reste_raeumen"], gui.status)
        self.assertIsNone(gui._checkpoint_reste)
        gui._checkpoint_reste_raeumen()               # nichts vorgemerkt: still
        self.assertEqual(["status.reste_raeumen"], gui.status)


# ---------------------------------------------------------------- U1-10

class BaumVorabGelesenTests(unittest.TestCase):
    """U1-10 widerlegt: Beide Leser lesen den ganzen Baum vor der ersten Datei."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(MKPFS_ORDNER))
        from mkpfs import exfat_writer                      # noqa: PLC0415
        from mkpfs.exfat import ExfatReader                 # noqa: PLC0415
        cls.ExfatReader = ExfatReader
        cls._tmp = tempfile.TemporaryDirectory(prefix="r19_baum_")
        quelle = Path(cls._tmp.name) / "PPSA00001"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "sce_sys" / "param.json").write_bytes(
            b'{"titleId":"PPSA00001","contentId":"UP0000-PPSA00001_00-TEST"}')
        (quelle / "sce_sys" / "icon0.png").write_bytes(b"\x89PNG" + b"\0" * 60)
        for nummer in range(6):
            tief = quelle / ("daten%d" % nummer) / "unter"
            tief.mkdir(parents=True)
            (tief / "x.bin").write_bytes(b"x" * 100)
        cls.ordner_gesamt = 1 + 6 * 2               # sce_sys + je zwei Ebenen
        cls.abbild = b"".join(exfat_writer.iter_exfat_image(quelle))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()
        sys.path.remove(str(MKPFS_ORDNER))

    def test_der_ganze_baum_ist_vor_der_ersten_datei_gelesen(self) -> None:
        leser = self.ExfatReader(io.BytesIO(self.abbild))
        gelesen: list = []
        echt = leser._walk_directory

        def _zaehlen(*args, **kwargs):
            gelesen.append(args[-1] if args else "")
            return echt(*args, **kwargs)

        leser._walk_directory = _zaehlen
        dateien = iter(leser.iter_files())
        next(dateien)
        nach_der_ersten = len(gelesen)
        list(dateien)
        self.assertEqual(nach_der_ersten, len(gelesen),
                         "Der Baum wird doch nach und nach gelesen - dann lohnte "
                         "sich ein frueherer Ausstieg (U1-10 neu bewerten).")
        # Die Wurzel plus jeder Unterordner - schon nach der ersten Datei.
        self.assertEqual(self.ordner_gesamt + 1, nach_der_ersten)

    def test_ein_ps5_titel_bekommt_ein_verlaessliches_nein(self) -> None:
        """Ohne param.sfo laeuft der Durchgang ganz - also darf "Nein" dastehen."""
        leser = abbild_metadaten.Metadatenleser(text=lambda s, **_w: s)
        meta, _bild = leser._extract_meta_from_exfat_reader(
            self.ExfatReader(io.BytesIO(self.abbild)))
        self.assertEqual("PPSA00001", meta.get("title_id"))
        self.assertEqual("info_popup.meta.ampr_emu_nein", meta.get("ampr_emu"),
                         "Ein PS5-Titel ohne AMPR bekam kein 'Nein' mehr - der "
                         "Ausstieg greift jetzt ohne param.sfo (U1-10).")


# ---------------------------------------------------------------- Texte

class TexteTests(unittest.TestCase):
    """Jeder neue Schluessel in beiden Sprachen, mit gleichen Platzhaltern."""

    NEU = ("pkg_merger.log_abgebrochen", "pkg_merger.abort_confirm",
           "pkg_merger.status_stopping", "pkg_merger.status_aborted",
           "verify.abgebrochen", "log.abschlusspruefung_abgebrochen",
           "log.warten_abgebrochen", "pkgbau.status_check_aborted",
           "status.reste_raeumen")

    def test_beide_sprachen(self) -> None:
        import string
        for schluessel in self.NEU:
            with self.subTest(schluessel=schluessel):
                eintrag = STRINGS[schluessel]
                self.assertTrue(eintrag.get("de") and eintrag.get("en"))
                self.assertNotEqual(eintrag["de"], eintrag["en"])
                felder = [{f for _t, f, _s, _k in string.Formatter().parse(eintrag[s]) if f}
                          for s in ("de", "en")]
                self.assertEqual(felder[0], felder[1])

    def test_der_verweigerungstext_ist_weg(self) -> None:
        """Das Fenster weigert sich nicht mehr - der Text dazu waere eine Luege."""
        self.assertNotIn("pkg_merger.busy_close", STRINGS)
        self.assertNotIn("pkg_merger.busy_close",
                         Path(APP.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
