# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht vom 23.09.2026.

* **H8-1** - Die Sammelkonvertierung nach Dump-Ordner leerte den Zielordner,
  auch wenn die Quelle darin lag: "D:\\PS5\\Spiel\\Spiel.exfat" mit ZIEL
  "D:\\PS5" ergibt "D:\\PS5\\Spiel". Der Einzellauf prueft das in
  ``_run_engine_thread``, die Sammelkonvertierung kam ungeprueft bis zur
  exFAT-Extraktion, und die raeumte den Ordner samt Quelle ab.
* **H7-1** - Eine abgebrochene Pruefung (Aufgabe 8) meldete "BESTANDEN":
  Der Validator fuehrt den Abbruch als Fehler und vergibt dafuer WARNING.
* **P1** - "[FEHLER] n Hinweise/Fehler" stand auch ueber blossen Hinweisen
  einer bestandenen Pruefung.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_befunde")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


class _Attrappe:
    def __getattr__(self, _name):
        return lambda *a, **k: None


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.is_running = True
    gui.root = mock.Mock()
    gui.status_label = mock.Mock()
    gui.progress_engine = _Attrappe()
    return gui


class ZielEnthaeltQuelleTests(unittest.TestCase):
    """H8-1: Kein Weg leert den Ordner, in dem die Quelle liegt."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory(prefix="h81_")
        self.basis = self.td.name
        self.spielordner = os.path.join(self.basis, "Spiel")
        os.makedirs(self.spielordner)
        self.quelle = os.path.join(self.spielordner, "Spiel.exfat")
        Path(self.quelle).write_bytes(b"QUELLE")

    def tearDown(self) -> None:
        self.td.cleanup()

    def test_die_sammelkonvertierung_ueberspringt_die_datei(self) -> None:
        gui = _gui()
        gui._batch_sources = [self.quelle]
        gui._get_selected_target_type = lambda: "folder"
        gebaut: list = []
        gui._execute_conversion_by_type = lambda *a: gebaut.append(a) or True
        ok = gui._run_flexible_conversion("batch_convert", "", self.basis)
        self.assertFalse(ok)
        self.assertEqual([], gebaut, "Der Weg wurde trotzdem gestartet.")
        self.assertEqual(Path(self.quelle).read_bytes(), b"QUELLE")
        ergebnis = gui.task_batch_results[0]
        self.assertFalse(ergebnis["ok"])
        self.assertIn(self.spielordner, ergebnis["detail"])

    def test_ein_anderer_zielordner_geht_durch(self) -> None:
        """Gegenprobe: Liegt die Quelle woanders, wird gebaut."""
        gui = _gui()
        gui._batch_sources = [self.quelle]
        gui._get_selected_target_type = lambda: "folder"
        ziel = os.path.join(self.basis, "Ausgabe")
        os.makedirs(ziel)
        gebaut: list = []
        gui._execute_conversion_by_type = lambda *a: gebaut.append(a) or False
        gui._run_flexible_conversion("batch_convert", "", ziel)
        self.assertEqual(1, len(gebaut))

    def test_der_exfat_weg_leert_den_ordner_nicht(self) -> None:
        gui = _gui()
        extrahiert: list = []
        gui._extract_exfat_to_folder_mkpfs = lambda *a, **k: extrahiert.append(a) or True
        self.assertFalse(gui._mode_exfat_to_folder(self.quelle, self.basis))
        self.assertEqual([], extrahiert)
        self.assertEqual(Path(self.quelle).read_bytes(), b"QUELLE")

    def test_der_extraktor_selbst_verweigert_es(self) -> None:
        gui = _gui()
        gui._extract_embedded_mkpfs = lambda: str(PROJEKT / "MkPFS-1.0.0")
        ok = gui._extract_exfat_to_folder_mkpfs(
            self.quelle, self.spielordner, status_prefix="T", log_prefix="T",
            progress_start=0.0, progress_end=100.0)
        self.assertFalse(ok)
        self.assertTrue(os.path.isfile(self.quelle), "Die Quelle wurde geloescht.")


class ValidatorAbbruchTests(unittest.TestCase):
    """H7-1 und P1: was nach der Pruefung im Protokoll steht."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory(prefix="h71_")
        self.ordner = os.path.join(self.td.name, "PPSA01234")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        Path(self.ordner, "eboot.bin").write_bytes(b"E")

    def tearDown(self) -> None:
        self.td.cleanup()

    def _pruefen(self, status: str, fehler: list, *, abbrechen: bool = False):
        gui = _gui()
        gui.task_progress = 0.0
        gui.mkpfs_dir = ""
        gui._extract_embedded_mkpfs = lambda: ""
        gui._validator_param_json_anbieten = lambda _s: None
        gui._quellgroesse_mit_meldung = lambda _p: 1
        gui._get_worker_count = lambda _n: 2
        gui._set_status = lambda *_a: None

        def _validate(**_k):
            if abbrechen:
                gui.is_running = False          # "Abbrechen" waehrend des Laufs
            return SimpleNamespace(status=status, errors=list(fehler),
                                   summary={}, hashes={})

        with mock.patch("ps5_validator.core.dispatcher.validate", _validate):
            ergebnis = gui._mode_dump_validator(self.ordner)
        return gui, ergebnis

    def test_ein_abbruch_ist_kein_bestanden(self) -> None:
        gui, ergebnis = self._pruefen("WARNING", ["Abgebrochen durch Benutzer."],
                                      abbrechen=True)
        self.assertFalse(ergebnis)
        text = "".join(gui.protokoll)
        self.assertNotIn("BESTANDEN", text)
        self.assertIn("ABGEBROCHEN", text)
        self.assertEqual("ABORTED", gui._last_validation_status)

    def test_ein_hinweis_steht_nicht_unter_fehler(self) -> None:
        gui, ergebnis = self._pruefen("WARNING", ["Leere Datei: sce_sys/leer.dat"])
        self.assertTrue(ergebnis)
        text = "".join(gui.protokoll)
        self.assertNotIn("[FEHLER]", text)
        self.assertIn("[HINWEIS] 1", text)
        self.assertIn("BESTANDEN", text)

    def test_ein_fehlschlag_bleibt_ein_fehler(self) -> None:
        gui, ergebnis = self._pruefen("FAILED", ["Hash-Fehler a.bin: kaputt"])
        self.assertFalse(ergebnis)
        self.assertIn("[FEHLER] 1", "".join(gui.protokoll))


class TitelIdAusDemOrdnernamenTests(unittest.TestCase):
    """U1-1: Der Ordnername ist nur der Notnagel - er ueberschreibt keine
    gueltige titleId (und damit keine contentId)."""

    DOC = {"applicationCategoryType": 0, "contentVersion": 1.0,
           "contentId": "EP0001-PPSA24680_00-ECHTEKENNUNG0000",
           "localizedParameters": {"defaultLanguage": "en-US",
                                   "en-US": {"titleName": "Test Spiel"}},
           "titleId": "PPSA24680"}

    def setUp(self) -> None:
        from ps5_validator.utils.param_manifest import save_param_json
        self.td = tempfile.TemporaryDirectory(prefix="u11_")
        self.ordner = os.path.join(self.td.name, "PPSA99999 Kopie")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        self.pfad = os.path.join(self.ordner, "sce_sys", "param.json")
        save_param_json(dict(self.DOC), self.pfad)

    def tearDown(self) -> None:
        self.td.cleanup()

    def _reparieren(self, herkunft: str) -> dict:
        import json

        from ps5_validator.utils import param_check
        gui = _gui()
        gui._param_frage = lambda *a, **k: True
        gui._detect_title_id_for_source = lambda _o: (
            "PPSA99999" if herkunft == "name" else "PPSA11111", herkunft)
        befund = param_check.pruefe_datei(self.pfad)
        self.assertFalse(befund.ok, "Die Vorlage muss eine Reparatur ausloesen.")
        self.assertTrue(gui._offer_repair_param_json(self.ordner, befund))
        with open(self.pfad, encoding="utf-8") as fh:
            return json.load(fh)

    def test_der_ordnername_ueberschreibt_keine_gueltige_kennung(self) -> None:
        doc = self._reparieren("name")
        self.assertEqual("PPSA24680", doc["titleId"])
        self.assertEqual("EP0001-PPSA24680_00-ECHTEKENNUNG0000", doc["contentId"])
        self.assertEqual("01.000.000", doc["contentVersion"], "Repariert wurde nicht.")

    def test_nptitle_berichtigt_weiterhin(self) -> None:
        """Gegenprobe: Die Angabe aus dem Dump selbst gilt wie bisher."""
        doc = self._reparieren("nptitle")
        self.assertEqual("PPSA11111", doc["titleId"])


class InstallerDownloadTests(unittest.TestCase):
    """H6-6: urlretrieve kennt keine Zeitgrenze - ein stockender Server hielt
    die Installation von FileZilla, OSFMount und Dokan ewig an."""

    def test_der_download_hat_eine_zeitgrenze_und_eine_zwischendatei(self) -> None:
        import io

        gefragt: dict = {}

        def _oeffnen(url, timeout=None, **_k):
            gefragt["zeit"] = timeout
            return io.BytesIO(b"MZ" + b"\0" * 100)

        gui = _gui()
        with tempfile.TemporaryDirectory() as ordner, \
                mock.patch.object(APP.urllib.request, "urlopen", _oeffnen):
            ziel = os.path.join(ordner, "setup.exe")
            gui._installer_laden("https://example.invalid/setup.exe", ziel)
            self.assertEqual(102, os.path.getsize(ziel))
            self.assertFalse(os.path.exists(ziel + ".part"))
        self.assertTrue(gefragt.get("zeit"), "Ohne Zeitgrenze geladen.")

    def test_ein_abgerissener_download_hinterlaesst_nichts(self) -> None:
        class _Bricht:
            def read(self, *_a):
                raise TimeoutError("Server stockt")

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

        gui = _gui()
        with tempfile.TemporaryDirectory() as ordner, \
                mock.patch.object(APP.urllib.request, "urlopen",
                                  lambda *a, **k: _Bricht()):
            ziel = os.path.join(ordner, "setup.exe")
            with self.assertRaises(TimeoutError):
                gui._installer_laden("https://example.invalid/setup.exe", ziel)
            self.assertEqual([], os.listdir(ordner))

    def test_kein_installer_laedt_mehr_ueber_urlretrieve(self) -> None:
        import ast
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        aufrufe = [k.lineno for k in ast.walk(baum) if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "urlretrieve"]
        self.assertEqual([], aufrufe)


class AufgabenfadenWartetBegrenztTests(unittest.TestCase):
    """H6-7: Die Ueberschreib-Rueckfrage wartete mit einem eigenen Ereignis
    ohne finally - warf der Dialog, stand der Aufgabenfaden fuer immer."""

    def test_der_aufgabenfaden_fragt_ueber_den_sicheren_weg(self) -> None:
        import ast
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        lauf = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)
                    and k.name == "_run_engine_thread")
        warten = [k.lineno for k in ast.walk(lauf) if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "wait"
                  and not k.args and not k.keywords]
        self.assertEqual([], warten, "wait() ohne Zeitgrenze im Aufgabenfaden")
        self.assertIn("_ask_yesno_threadsafe", ast.unparse(lauf))


@unittest.skipUnless(os.name == "nt", "Das Zurueckholen gibt es nur unter Windows")
class CliFensterTests(unittest.TestCase):
    """H12-10: --cli zeigte ein maximiertes, leeres Programmfenster."""

    def test_das_verbergen_haelt_auch_nach_dem_maximieren(self) -> None:
        import tkinter as tk
        wurzel = tk._default_root or tk.Tk()
        fenster = tk.Toplevel(wurzel)
        try:
            fenster.withdraw()
            fenster.state("zoomed")       # was _setup_window tut
            fenster.update()
            self.assertTrue(fenster.winfo_viewable(),
                            "Die Vorbedingung stimmt nicht mehr: zoomed bildet nicht ab.")
            APP._cli_fenster_verbergen(fenster)
            fenster.update()
            self.assertFalse(fenster.winfo_viewable())
        finally:
            fenster.destroy()

    def test_beide_cli_wege_verbergen_nach_dem_aufbau(self) -> None:
        import ast
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        for name in ("_run_cli", "_run_cli_ampr_ftp_index"):
            with self.subTest(weg=name):
                weg = next(k for k in baum.body if isinstance(k, ast.FunctionDef)
                           and k.name == name)
                text = ast.unparse(weg)
                i_bau = text.find("PS5ConverterGUI(root)")
                i_weg = text.find("_cli_fenster_verbergen(root)")
                self.assertGreater(i_bau, 0)
                self.assertGreater(i_weg, i_bau, "Verborgen wird nicht nach dem Aufbau.")


class KonsolenwegeTests(unittest.TestCase):
    """H3-2, H3-3, H8-2 - Konsole und exFAT-Rueckfall."""

    def test_die_ftp_bereitschaft_prueft_den_eingestellten_port(self) -> None:
        """H3-2: Fest 2121 geprueft - mit eigenem Port hiess es "laeuft nicht"."""
        gui = _gui()
        gui._ps5_ftp_port = lambda: 1337
        gefragt: list = []

        def _pruefen(_ip, eintrag, *_a, **_k):
            gefragt.append(eintrag.port)
            return (True, False)

        with mock.patch.object(APP.konsole_dienste, "dienst_pruefen", _pruefen):
            self.assertTrue(gui._konsole_ftp_bereit("192.168.178.50", lambda _t: None))
        self.assertEqual([1337], gefragt)

    @staticmethod
    def _innere(methode: str, name: str) -> str:
        import ast
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        aussen = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)
                      and k.name == methode)
        innen = next(k for k in ast.walk(aussen) if isinstance(k, ast.FunctionDef)
                     and k.name == name)
        return ast.unparse(innen)

    def test_benutzer_lesen_schickt_den_agenten(self) -> None:
        """H3-3: Ohne laufenden Agenten scheiterte "Benutzer lesen" - das
        Koppeln schickte ihn, das Lesen nicht."""
        text = self._innere("_show_konsole_remoteplay", "_benutzer_lesen")
        i_start = text.find("agent.starten()")
        self.assertGreater(i_start, 0, "Der Agent wird nicht geschickt.")
        self.assertLess(i_start, text.find("agent.benutzer_liste()"))

    def test_der_osfmount_rueckfall_baut_ebenfalls_ein(self) -> None:
        """H8-2: Ueber OSFMount entpackt kam der Ordner ohne AMPR/BACKPORT an."""
        import ast
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        weg = next(k for k in ast.walk(baum) if isinstance(k, ast.FunctionDef)
                   and k.name == "_mode_exfat_to_folder")
        text = ast.unparse(weg)
        self.assertEqual(2, text.count("self._integration_anwenden(dest_folder)"))
        self.assertGreater(text.rfind("self._integration_anwenden(dest_folder)"),
                           text.find("_worker()"))


class UnterprozessAbbruchTests(unittest.TestCase):
    """H6-5: Schwieg ein Werkzeug, griffen weder Abbrechen noch Zeitgrenze."""

    SCHWEIGT = [sys.executable, "-c", "import time; time.sleep(20)"]

    def test_abbrechen_greift_ohne_ausgabe(self) -> None:
        import time
        gui = _gui()
        start = time.monotonic()
        rc = gui._run_subprocess_logged(
            self.SCHWEIGT, timeout=60, line_callback=lambda _z: True,
            abbruch=lambda: time.monotonic() - start > 0.5)
        self.assertEqual(130, rc)
        self.assertLess(time.monotonic() - start, 8.0, "Der Abbruch wartete aufs Ende.")

    def test_die_zeitgrenze_greift_ohne_ausgabe(self) -> None:
        import time
        gui = _gui()
        start = time.monotonic()
        rc = gui._run_subprocess_logged(self.SCHWEIGT, timeout=1,
                                        line_callback=lambda _z: True)
        self.assertEqual(1, rc)
        self.assertLess(time.monotonic() - start, 8.0,
                        "Die Zeitgrenze griff erst nach dem Ende.")

    def test_die_abbrueche_der_aufgaben_sind_verdrahtet(self) -> None:
        """UFS2Tool und die drei robocopy-Wege geben ihren Abbruch mit."""
        import ast
        baum = ast.parse(Path(APP.__file__).read_text(encoding="utf-8"))
        aufrufe = [k for k in ast.walk(baum) if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_run_subprocess_logged"
                   and any(w.arg == "line_callback" for w in k.keywords)]
        self.assertEqual(4, len(aufrufe))
        for aufruf in aufrufe:
            with self.subTest(zeile=aufruf.lineno):
                self.assertIn("abbruch", [w.arg for w in aufruf.keywords])


class DndRueckfallTests(unittest.TestCase):
    """H12-12: Liess sich tkdnd nicht laden, startete das Programm gar nicht."""

    def test_ohne_tkdnd_startet_es_ohne_ziehen_und_ablegen(self) -> None:
        import subprocess
        skript = (
            "import sys, tkinter as tk\n"
            "sys.path.insert(0, %r)\n"
            "import PS5ImageConverter_Pro_FINAL_revised as APP\n"
            "class _Kaputt(tk.Tk):\n"
            "    def __init__(self, *a, **k):\n"
            "        tk.Tk.__init__(self, *a, **k)\n"
            "        raise RuntimeError('Unable to load tkdnd library.')\n"
            "APP._DND_AVAILABLE = True\n"
            "APP.TkinterDnD = type('Attrappe', (), {'Tk': _Kaputt})\n"
            "wurzel = APP._hauptfenster_anlegen()\n"
            "print('ERGEBNIS', type(wurzel).__name__, APP._DND_AVAILABLE,\n"
            "      tk._default_root is wurzel)\n"
            "wurzel.destroy()\n" % str(PROJEKT))
        lauf = subprocess.run([sys.executable, "-c", skript], cwd=str(PROJEKT),
                              capture_output=True, text=True, timeout=180,
                              env=dict(os.environ))
        zeile = [z for z in lauf.stdout.splitlines() if z.startswith("ERGEBNIS")]
        self.assertEqual(0, lauf.returncode, lauf.stderr[-1200:])
        self.assertEqual(["ERGEBNIS Tk False True"], zeile)


class TestumgebungTests(unittest.TestCase):
    """B-1..B-5: Pruefwerkzeuge laufen auf dem neuen Rechner und fassen die
    Einstellungen des Anwenders nicht an."""

    def test_die_conftest_lenkt_ohne_vorgabe_selbst_um(self) -> None:
        import subprocess
        umgebung = {k: v for k, v in os.environ.items()
                    if k != "PS5CONV_KONFIGORDNER"}
        lauf = subprocess.run(
            [sys.executable, "-c",
             "import conftest, os; print(os.environ.get('PS5CONV_KONFIGORDNER', ''))"],
            cwd=str(PROJEKT), env=umgebung, capture_output=True, text=True,
            timeout=120)
        self.assertEqual(0, lauf.returncode, lauf.stderr[-800:])
        ordner = lauf.stdout.strip().splitlines()[-1]
        self.assertTrue(ordner, "Ohne Vorgabe bleibt der Einstellungsordner des Anwenders.")
        self.assertIn("ps5conv_pruefung", ordner)

    def _skript(self, name: str) -> str:
        return (PROJEKT / name).read_text(encoding="utf-8-sig")

    def test_die_adminskripte_kennen_keinen_festen_rechner(self) -> None:
        for name in ("Pruefung_mit_Adminrechten.ps1", "Pruefung_ffpkg_Matrix.ps1"):
            with self.subTest(skript=name):
                text = self._skript(name)
                self.assertNotIn("C:\\Users\\", text)
                self.assertIn("$Projekt = $PSScriptRoot", text)
                self.assertIn("param(", text)

    def test_die_adminpruefung_lenkt_die_einstellungen_um(self) -> None:
        text = self._skript("Pruefung_mit_Adminrechten.ps1")
        i_setzen = text.find("$env:PS5CONV_KONFIGORDNER = $Konfig")
        i_erster_fall = text.find("Invoke-Fall \"AD1")
        self.assertGreater(i_setzen, 0)
        self.assertLess(i_setzen, i_erster_fall, "Umgelenkt wird erst nach dem ersten Fall.")

    def test_das_matrixprotokoll_zaehlt_nicht_als_ergebnis(self) -> None:
        text = self._skript("Pruefung_ffpkg_Matrix.ps1")
        self.assertEqual(2, text.count("$_.Name -ne $LaufLogName"),
                         "Das Protokoll zaehlt beim Vermessen oder bei 'SCHON DA' mit.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
