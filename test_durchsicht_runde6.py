# -*- coding: utf-8 -*-
"""Waechter fuer Befunde der Durchsicht, Runde 6 (24.09.2026).

Info-Box und Info-Fenster nach einem Quellwechsel:

* **H4-11** - Eine geleerte oder ungueltige Quelle entwertete die noch
  laufende Messung der vorigen nicht; deren Werte fuellten danach die eben
  geleerte Anzeige.
* **H4-13** - Nach der Store-Suche (bis zu 2 x 6 s) wurde die Info-Box ohne
  erneute Pruefung beschrieben - die Angaben von Spiel A standen unter B.
* **H5-4** - Die Patch-Liste von Spiel A landete unter Spiel B.
* **H5-5** - Eine abgelaufene oder gescheiterte Patch-Abfrage kam fuer eine
  Stunde als "keine Updates" in den Zwischenspeicher.
* **H5-7** - Die Freigabe eines einzelnen Klicks galt fuer alle Faeden; eine
  inzwischen gewaehlte andere Quelle ging ungefragt ins Netz.
* **H5-8** - Das Ergebnis des Nachschlags wurde ohne Quellabgleich
  eingetragen.

Dazu **H4-6** - das Packziel wurde auch dann aufs Temp-Laufwerk umgeleitet,
wenn Quelle und Ziel ohnehin auf verschiedenen Laufwerken lagen.

Zweiter Teil:

* **H4-15** - Die AMPR-Zeile der Info-Box las bei Abbildern den Container im
  Fensterfaden, bei jedem Aufruf neu.
* **H6-3** - Nach einem Abbruch merkte sich das Programm den Zwischenpfad,
  der naechste Lauf fragte mit dem Endziel - das Warten griff nie.
* **H8-3** - Die Sammelkonvertierung fuellte einen vorhandenen Dump-Ordner
  nur auf.
* **H7-3** - Ein Methodenwechsel waehrend des Laufs liess den Einbau seine
  AMPR-Fassung nicht mehr finden.
* **H7-5** - BACKPORT scheiterte an schreibgeschuetzten Dateien, beim Einbau
  ohne Grund im Protokoll.
* **H7-7** - Aufgabe 7 ersetzte eine fremde Datei am Ziel ohne Rueckfrage.
* **H11-2** - "PKG bauen" pruefte den Platz nicht zusammen, wenn Arbeits- und
  Zielordner auf demselben Datentraeger liegen.
* **U4-1** - Die Lizenzdatei wurde nie gefunden (Suche nur nach Ordnern).
* **U4-2** - Unlesbare Ordner uebersprang die Dump-Pruefung still.
"""
from __future__ import annotations

import ast
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("durchsicht_runde6")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402


def _gui():
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.is_running = False
    gui.root = mock.Mock()
    return gui


_BAUM: list = []


def _methode(name: str) -> ast.FunctionDef:
    if not _BAUM:
        _BAUM.append(ast.parse(Path(APP.__file__).read_text(encoding="utf-8")))
    return next(k for k in ast.walk(_BAUM[0])
                if isinstance(k, ast.FunctionDef) and k.name == name)


class _SofortFaden:
    """Fuehrt das Ziel beim Start sofort aus - macht die Abfrage berechenbar."""

    def __init__(self, target=None, args=(), kwargs=None, **_k):
        self._ziel, self._args, self._kw = target, args, kwargs or {}

    def start(self):
        self._ziel(*self._args, **self._kw)

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False


class InfoBoxGenerationTests(unittest.TestCase):
    """H4-11 und H4-13."""

    def test_eine_ungueltige_quelle_entwertet_die_laufende_messung(self) -> None:
        methode = _methode("_on_source_path_changed")
        weiche = next(k for k in ast.walk(methode) if isinstance(k, ast.If)
                      and isinstance(k.test, ast.Name) and k.test.id == "src_valid")
        erhoeht = [k for k in weiche.orelse if isinstance(k, ast.AugAssign)
                   and ast.unparse(k.target) == "self._calc_generation"]
        self.assertTrue(erhoeht, "Der Zweig ohne gueltige Quelle zaehlt nicht weiter.")

    def test_die_box_nimmt_nur_die_aktuelle_messung(self) -> None:
        gui = _gui()
        gui._calc_generation = 5
        gui._update_info_box = mock.Mock()
        gui._infobox_wenn_aktuell(4, {"title": "A"}, None, "1 GB", "")
        gui._update_info_box.assert_not_called()
        gui._infobox_wenn_aktuell(5, {"title": "B"}, None, "2 GB", "")
        gui._update_info_box.assert_called_once_with({"title": "B"}, None, "2 GB", "")

    def test_die_messung_schreibt_nur_ueber_die_pruefung(self) -> None:
        text = ast.unparse(_methode("_on_source_path_changed"))
        self.assertNotIn("self._update_info_box(", text)
        self.assertGreaterEqual(text.count("self._infobox_wenn_aktuell(my_gen,"), 7)

    def test_nach_der_store_suche_wird_neu_geprueft(self) -> None:
        text = ast.unparse(_methode("_on_source_path_changed"))
        i_suche = text.find("self._resolve_title_id_from_store_search(title_guess)")
        i_pruefung = text.find("if my_gen != self._calc_generation:\n", i_suche)
        # Seit Runde 12 plant der Faden ueber _hauptfaden_planen.
        i_anzeige = text.find("self._hauptfaden_planen(", i_suche)
        self.assertGreater(i_suche, 0)
        self.assertGreater(i_pruefung, i_suche)
        self.assertLess(i_pruefung, i_anzeige, "Angezeigt wird vor der Pruefung.")


class PatchListeTests(unittest.TestCase):
    """H5-4 und H5-5."""

    def _fenster(self):
        gui = _gui()
        gui._patch_tree = mock.MagicMock()
        gui._patch_tree.winfo_exists.return_value = True
        gui._patch_tree.get_children.return_value = []
        gui._patch_status_var = mock.Mock()
        return gui

    def test_eine_spaete_liste_fuer_ein_anderes_spiel_wird_verworfen(self) -> None:
        gui = self._fenster()
        gui._patch_titel = "PPSA00002"
        gui._display_patches([], "PPSA00001", final=True)
        gui._patch_tree.insert.assert_not_called()
        gui._patch_status_var.set.assert_not_called()
        # Gegenrichtung: die Liste des angezeigten Titels kommt an.
        gui._display_patches([], "ppsa00002", final=True)
        gui._patch_tree.insert.assert_called_once()

    def _abfragen(self, urlopen) -> dict:
        gui = self._fenster()
        gui._patch_cache = {}
        gui._metadaten_online_erlaubt = lambda: True
        with mock.patch.object(APP.threading, "Thread", _SofortFaden), \
                mock.patch.object(APP.urllib.request, "urlopen", urlopen):
            gui._fetch_patches_async("PPSA01234")
        return gui._patch_cache

    def test_eine_gescheiterte_abfrage_kommt_nicht_in_den_zwischenspeicher(self) -> None:
        zwischenspeicher = self._abfragen(mock.Mock(side_effect=OSError("Netz weg")))
        self.assertNotIn("PPSA01234", zwischenspeicher)

    def test_keine_updates_wird_weiter_gemerkt(self) -> None:
        """Gegenrichtung: Eine vollstaendige Antwort ohne Updates zaehlt."""
        antwort = mock.MagicMock()
        antwort.__enter__.return_value.read.return_value = b"<html>404 - not here</html>"
        zwischenspeicher = self._abfragen(mock.Mock(return_value=antwort))
        self.assertIn("PPSA01234", zwischenspeicher)
        self.assertEqual([], zwischenspeicher["PPSA01234"][1])

    def test_der_zwischenspeicher_richtet_sich_nach_der_vollstaendigkeit(self) -> None:
        text = ast.unparse(_methode("_fetch_patches_async"))
        self.assertIn("if vollstaendig:", text)


class EinmaligeFreigabeTests(unittest.TestCase):
    """H5-7 und H5-8."""

    def test_die_freigabe_gilt_nur_im_eigenen_faden(self) -> None:
        gui = _gui()
        gui._metadaten_online_vorgabe = lambda: False       # Abruf abgeschaltet
        gui._meta_nachschlag_einmalig = True
        try:
            self.assertTrue(gui._metadaten_online_erlaubt())
            gesehen: dict = {}

            def _anderer() -> None:
                gesehen["erlaubt"] = gui._metadaten_online_erlaubt()

            faden = threading.Thread(target=_anderer)
            faden.start()
            faden.join(10)
            self.assertIs(False, gesehen.get("erlaubt"),
                          "Ein anderer Faden bekam die Freigabe des Klicks.")
        finally:
            gui._meta_nachschlag_einmalig = False
        self.assertFalse(gui._metadaten_online_erlaubt())

    def _nachschlag(self, *, generation: int, titel: str):
        gui = _gui()
        gui._calc_generation = 4
        gui._cached_title_id = titel
        gui._update_info_box = mock.Mock()
        gui._info_roh_groessen = ("1 GB", "")
        gui._info_src_size_var = mock.Mock()
        gui._info_popup = None
        gui._meta_nachschlag_knopf = None
        gui._nachschlag_knopf_pruefen = lambda: None
        gui._nachschlag_fertig({"title": "Spiel A"}, None, "PPSA00001", generation)
        return gui

    def test_das_ergebnis_gilt_nur_fuer_die_quelle_des_klicks(self) -> None:
        for generation, titel in ((3, "PPSA00001"), (4, "PPSA00002")):
            with self.subTest(generation=generation, titel=titel):
                gui = self._nachschlag(generation=generation, titel=titel)
                gui._update_info_box.assert_not_called()
                self.assertFalse(gui._meta_nachschlag_einmalig)
        gui = self._nachschlag(generation=4, titel="PPSA00001")
        gui._update_info_box.assert_called_once()


@unittest.skipUnless(os.name == "nt", "Staging greift nur bei verschiedenen Laufwerksbuchstaben")
class StagingTests(unittest.TestCase):
    """H4-6: Umleiten nur, wenn Quelle und Ziel dasselbe Laufwerk teilen."""

    def _entscheiden(self, arbeit: str, quelle: str) -> str:
        gui = _gui()
        gui.task_total_source_bytes = 0
        gui._load_setting = lambda k, d=None: arbeit if k == "temp_dir" else d
        gui._mkdtemp = lambda prefix="", dir_path=None: tempfile.mkdtemp(
            prefix=prefix, dir=dir_path)
        laufwerk = os.path.splitdrive(arbeit)[0].upper()
        ziel_lw = "Q:" if laufwerk != "Q:" else "R:"
        return gui._decide_pack_output_staging(ziel_lw + "\\Ziel\\Spiel.ffpfsc",
                                               quelle=quelle.replace("?:", ziel_lw))

    def test_quelle_auf_anderem_laufwerk_wird_nicht_umgeleitet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as arbeit:
            laufwerk = os.path.splitdrive(arbeit)[0].upper()
            fremd = "S:" if laufwerk != "S:" else "T:"
            ergebnis = self._entscheiden(arbeit, fremd + "\\Dump")
            self.assertTrue(ergebnis.endswith("\\Ziel\\Spiel.ffpfsc"))
            self.assertFalse(ergebnis.startswith(arbeit))

    def test_quelle_auf_dem_ziellaufwerk_wird_umgeleitet(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as arbeit:
            ergebnis = self._entscheiden(arbeit, "?:\\Dump")
            self.assertTrue(ergebnis.startswith(arbeit), ergebnis)
            self.assertTrue(os.path.basename(os.path.dirname(ergebnis))
                            .lower().startswith("ps5conv_stage_"))

    def test_alle_packwege_nennen_ihre_quelle(self) -> None:
        aufrufe = []
        for name in ("_mode_pack_folder_exfat", "_mode_pack_folder_flach",
                     "_mode_pack_folder_mkpfs", "_mode_pack_file"):
            for k in ast.walk(_methode(name)):
                if isinstance(k, ast.Call) and \
                        getattr(k.func, "attr", "") == "_decide_pack_output_staging":
                    aufrufe.append((name, {kw.arg for kw in k.keywords}))
        self.assertEqual(4, len(aufrufe))
        for name, schluessel in aufrufe:
            with self.subTest(weg=name):
                self.assertIn("quelle", schluessel)


class AmprZeileTests(unittest.TestCase):
    """H4-15: Bei Abbildern im Faden, gemerkt je Datei."""

    def _gui(self):
        gui = _gui()
        self.zeile = mock.Mock()
        gui._meta_labels = {"ampr_emu": self.zeile}
        return gui

    def test_ein_abbild_wird_im_faden_gelesen_und_gemerkt(self) -> None:
        gui = self._gui()
        gelesen: list = []
        freigabe = threading.Event()

        def _stand(_quelle):
            gelesen.append(threading.current_thread() is threading.main_thread())
            freigabe.wait(5.0)
            return "eingebaut"

        gui._ampr_emu_stand = _stand
        with tempfile.TemporaryDirectory(prefix="runde6_") as basis:
            bild = Path(basis, "spiel.ffpfsc")
            bild.write_bytes(b"x" * 16)
            beginn = time.monotonic()
            gui._ampr_stand_anzeigen(str(bild))
            self.assertLess(time.monotonic() - beginn, 2.0,
                            "Die Info-Box wartet auf den Container.")
            self.zeile.set.assert_called_with(chr(0x2026))
            freigabe.set()
            ende = time.monotonic() + 5.0
            while not gui.root.after.called and time.monotonic() < ende:
                time.sleep(0.02)
            _null, rueckruf, *argumente = gui.root.after.call_args[0]
            rueckruf(*argumente)
            self.zeile.set.assert_called_with("eingebaut")
            self.assertEqual([False], gelesen, "Gelesen wurde im Fensterfaden.")
            # Zweiter Aufruf: aus dem Merker, ohne neues Lesen.
            gui._ampr_stand_anzeigen(str(bild))
            self.zeile.set.assert_called_with("eingebaut")
            self.assertEqual(1, len(gelesen))

    def test_die_info_box_geht_ueber_den_faden(self) -> None:
        text = ast.unparse(_methode("_update_info_box"))
        self.assertIn("self._ampr_stand_anzeigen(_quelle)", text)
        self.assertNotIn("self._ampr_emu_stand(", text)

    def test_ein_ordner_wird_direkt_und_ungemerkt_gelesen(self) -> None:
        """Nach einem Einbau aendert sich am Ordner selbst nichts."""
        gui = self._gui()
        antworten = iter(["nicht eingebaut", "eingebaut"])
        gui._ampr_emu_stand = lambda _q: next(antworten)
        with tempfile.TemporaryDirectory(prefix="runde6_") as ordner:
            gui._ampr_stand_anzeigen(ordner)
            self.zeile.set.assert_called_with("nicht eingebaut")
            gui._ampr_stand_anzeigen(ordner)
            self.zeile.set.assert_called_with("eingebaut")


class MkpfsWartenTests(unittest.TestCase):
    """H6-3: Der Abbruch merkt sich das Endziel, nicht den Zwischenpfad."""

    def test_der_abbruch_merkt_sich_das_endziel(self) -> None:
        text = ast.unparse(_methode("_execute_mkpfs"))
        self.assertIn("self._pending_mkpfs_target_path = str(endziel or "
                      "monitor_target_path or '')", text)

    def test_jeder_packschritt_nennt_sein_endziel(self) -> None:
        aufrufe = []
        for name in ("_mode_pack_folder_exfat", "_mode_pack_folder_flach",
                     "_mode_pack_folder_mkpfs", "_mode_pack_file"):
            for k in ast.walk(_methode(name)):
                if isinstance(k, ast.Call) and \
                        getattr(k.func, "attr", "") == "_execute_mkpfs":
                    aufrufe.append((name, {kw.arg for kw in k.keywords}))
        self.assertEqual(5, len(aufrufe))
        for name, schluessel in aufrufe:
            with self.subTest(weg=name):
                self.assertIn("endziel", schluessel)


class SammelOrdnerTests(unittest.TestCase):
    """H8-3: Ein Dump-Ordner als Ziel wird ersetzt, nicht aufgefuellt."""

    def _lage(self, basis: str, antwort: bool):
        quelle = Path(basis, "Spiel.exfat")
        quelle.write_bytes(b"abbild")
        alt = Path(basis, "ziel", "Spiel")
        (alt / "sce_sys").mkdir(parents=True)
        (alt / "alt_nur_in_v1.bin").write_bytes(b"alt")
        gui = _gui()
        gui._batch_ueberschreiben = None
        gui._ask_yesno_threadsafe = lambda *_a, **_k: antwort
        return gui, quelle, alt

    def test_nach_dem_ja_ist_der_alte_ordner_weg(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as basis:
            gui, quelle, alt = self._lage(basis, True)
            self.assertTrue(gui._batch_ueberschreiben_klaeren(
                str(quelle), str(alt.parent), "folder"))
            self.assertFalse(alt.exists(), "Der alte Dump bleibt und wird nur aufgefuellt.")

    def test_nach_dem_nein_bleibt_er(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as basis:
            gui, quelle, alt = self._lage(basis, False)
            self.assertFalse(gui._batch_ueberschreiben_klaeren(
                str(quelle), str(alt.parent), "folder"))
            self.assertTrue((alt / "alt_nur_in_v1.bin").is_file())

    def test_ein_ordner_mit_der_quelle_darin_bleibt(self) -> None:
        """Den weist der Weg selbst ab (H8-1) - hier wird nichts geloescht."""
        with tempfile.TemporaryDirectory(prefix="runde6_") as basis:
            gui, _quelle, alt = self._lage(basis, True)
            innen = alt / "Spiel.exfat"
            innen.write_bytes(b"abbild")
            self.assertTrue(gui._batch_ueberschreiben_klaeren(
                str(innen), str(alt.parent), "folder"))
            self.assertTrue(innen.is_file())


class AmprAuswahlTests(unittest.TestCase):
    """H7-3: Die Fassungsliste gilt im Lauf so, wie sie beim Start war."""

    def test_der_lauf_haelt_die_liste_seines_starts(self) -> None:
        gui = _gui()
        gui._ampr_versionsauswahl = {"1.0 release": {"path": "a"}}
        gui._lauf_variablen_festhalten()
        # Waehrend des Laufs auf die andere Methode umgeschaltet:
        gui._ampr_versionsauswahl = {"2.0 test-pack": {"path": "b"}}
        gesehen: dict = {}
        faden = threading.Thread(
            target=lambda: gesehen.update(gui._ampr_auswahl_beim_start()))
        faden.start()
        faden.join(10)
        self.assertIn("1.0 release", gesehen)
        self.assertIn("2.0 test-pack", gui._ampr_auswahl_beim_start(),
                      "Im Fenster gilt die aktuelle Liste.")

    def test_der_einbau_findet_seine_fassung_nach_dem_wechsel(self) -> None:
        gui = _gui()
        gui._lauf_variablen = {"ampr_version_var": "1.0 release",
                               "_ampr_versionsauswahl": {"1.0 release": {"path": "a"}}}
        gui._ampr_versionsauswahl = {}
        gui._set_status = lambda *_a, **_k: None
        angewandt: list = []
        gui._ampr_apply_library = lambda _o, pfad, _n: angewandt.append(pfad) or False
        faden = threading.Thread(target=lambda: gui._integration_ampr("ordner"))
        faden.start()
        faden.join(10)
        self.assertEqual(["a"], angewandt)
        self.assertNotIn(gui._t("main.integrate_ampr_no_version"), gui.protokoll)


class SchreibschutzTests(unittest.TestCase):
    """H7-5: BACKPORT ersetzt auch schreibgeschuetzte Dateien - und nennt Gruende."""

    @unittest.skipUnless(os.name == "nt", "Das Attribut blockiert os.replace nur unter Windows")
    def test_eine_schreibgeschuetzte_datei_wird_ersetzt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as basis:
            ziel = Path(basis, "eboot.bin")
            zwischen = Path(basis, "eboot.bin.neu")
            ziel.write_bytes(b"alt")
            os.chmod(ziel, stat.S_IREAD)
            zwischen.write_bytes(b"neu")
            try:
                APP._datei_ersetzen(str(zwischen), str(ziel))
                self.assertEqual(b"neu", ziel.read_bytes())
                self.assertFalse(zwischen.exists())
            finally:
                if ziel.exists():
                    os.chmod(ziel, stat.S_IWRITE | stat.S_IREAD)

    def test_der_einbau_nennt_den_grund(self) -> None:
        gui = _gui()
        gui.is_running = True
        gui.backport_fw_var = SimpleNamespace(get=lambda: 7)
        gui._set_status = lambda *_a, **_k: None
        gui._backport_ziel_deckung_melden = lambda *_a: None
        gui._backport_fakelib_basis = lambda: ""
        with tempfile.TemporaryDirectory(prefix="runde6_") as ordner:
            datei = Path(ordner, "eboot.bin")
            datei.write_bytes(b"x")
            with mock.patch.object(APP.ps5_backport, "kandidaten", lambda _o: [str(datei)]), \
                    mock.patch.object(APP.ps5_backport, "datei_verarbeiten",
                                      lambda *_a, **_k: (APP.ps5_backport.ERG_GEPATCHT, b"n", "")), \
                    mock.patch.object(APP, "_datei_ersetzen",
                                      mock.Mock(side_effect=PermissionError(13, "Zugriff verweigert"))):
                self.assertFalse(gui._integration_backport(ordner))
        self.assertTrue(any("Zugriff verweigert" in zeile for zeile in gui.protokoll),
                        "Der Grund steht nicht im Protokoll.")


class Aufgabe7ErsetzenTests(unittest.TestCase):
    """H7-7: Eine fremde Datei am Ziel nur nach Rueckfrage (--yes)."""

    def test_an_ort_und_stelle_wird_nicht_gefragt(self) -> None:
        gui = _gui()
        gui._ask_yesno_threadsafe = mock.Mock(return_value=False)
        self.assertTrue(gui._ampr7_ersetzen_erlaubt(
            "D:\\Spiele\\Spiel.ffpfsc", "D:\\Spiele\\Spiel.ffpfsc", {"action": "apply"}))
        gui._ask_yesno_threadsafe.assert_not_called()

    def test_eine_fremde_datei_wird_erfragt(self) -> None:
        gui = _gui()
        gui._ask_yesno_threadsafe = mock.Mock(return_value=False)
        self.assertFalse(gui._ampr7_ersetzen_erlaubt(
            "D:\\Spiele\\Spiel.ffpfsc", "E:\\Ziel\\Spiel.ffpfsc", {"action": "apply"}))
        gui._ask_yesno_threadsafe.assert_called_once()


class PlatzTests(unittest.TestCase):
    """H11-2: Auf demselben Datentraeger zaehlt die Summe."""

    def test_auf_einem_datentraeger_addiert_sich_der_bedarf(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as basis:
            arbeit = os.path.join(basis, "arbeit")
            ziel = os.path.join(basis, "ziel")
            os.makedirs(arbeit)
            os.makedirs(ziel)
            with mock.patch.object(APP.shutil, "disk_usage",
                                   lambda _p: SimpleNamespace(free=100)):
                pruefe = APP.PS5ConverterGUI._platz_reicht_fuer
                self.assertFalse(pruefe(arbeit, ziel, 60, 60))
                self.assertTrue(pruefe(arbeit, ziel, 60, 40))

    def test_das_fenster_benutzt_die_pruefung(self) -> None:
        text = ast.unparse(_methode("_show_pkg_bauen"))
        self.assertIn("self._platz_reicht_fuer(arbeit, ziel, noetig_arbeit, noetig_ziel)", text)


class MitgeliefertTests(unittest.TestCase):
    """U4-1: Die Lizenzdatei wird auch in der fertigen Programmdatei gefunden."""

    def test_eine_datei_wird_im_buendel_gefunden(self) -> None:
        with tempfile.TemporaryDirectory(prefix="runde6_") as buendel, \
                tempfile.TemporaryDirectory(prefix="runde6_") as anderswo:
            Path(buendel, "THIRD_PARTY_LICENSES.md").write_text("x", encoding="utf-8")
            with mock.patch.object(APP.sys, "_MEIPASS", buendel, create=True), \
                    mock.patch.object(APP.os, "getcwd", lambda: anderswo):
                gefunden = APP.PS5ConverterGUI._mitgeliefert_finden(
                    "THIRD_PARTY_LICENSES.md", datei=True)
            self.assertEqual(os.path.join(buendel, "THIRD_PARTY_LICENSES.md"), gefunden)

    def test_die_diagnose_sucht_die_lizenz_als_datei(self) -> None:
        text = (PROJEKT / "ps5_validator" / "utils" / "diagnose_befund.py").read_text(
            encoding="utf-8")
        self.assertIn('_mitgeliefert_finden("THIRD_PARTY_LICENSES.md", datei=True)', text)


class DateilisteTests(unittest.TestCase):
    """U4-2: Ein unlesbarer Ordner bricht die Dateiliste ab."""

    def test_ein_unlesbarer_ordner_faellt_auf(self) -> None:
        from ps5_validator.utils import file_io
        with tempfile.TemporaryDirectory(prefix="runde6_") as wurzel:
            os.makedirs(os.path.join(wurzel, "gesperrt"))
            Path(wurzel, "eboot.bin").write_bytes(b"x")
            echt = os.scandir

            def _scandir(pfad="."):
                if str(pfad).endswith("gesperrt"):
                    raise PermissionError(13, "Zugriff verweigert", str(pfad))
                return echt(pfad)

            with mock.patch.object(os, "scandir", _scandir):
                with self.assertRaises(OSError):
                    file_io.get_all_files(wurzel)
            # Gegenrichtung: ohne Sperre kommt die Liste.
            self.assertEqual(1, len(file_io.get_all_files(wurzel)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
