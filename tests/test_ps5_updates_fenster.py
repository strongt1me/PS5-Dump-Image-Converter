# -*- coding: utf-8 -*-
"""Offizielle PS5-Updates im Fenster Spiel-Info (Liste und Download).

Die Abfrage und das Laden selbst pruefen ``test_ps5_updates``; hier geht es um
die Anbindung: Wann fragt das Fenster Sonys Liste (nur mit ``versionFileUri``
aus der ``param.json`` des gerade gezeigten Spiels), wie sehen die Zeilen aus,
und laedt der Klick auf DOWNLOAD wirklich - fortsetzbar, in den Ordner
„PS5 Spiele Updates“ bzw. „Patches“.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ps5_validator.utils import ps5_updates as pu  # noqa: E402
from ps5_validator.utils.i18n import STRINGS  # noqa: E402
from test_ps5_updates import _Server  # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

URI = "https://sgst.prod.dl.playstation.net/sgst/prod/00/np/PPSA01650_00/c91127c5-version.xml"
MANIFEST_URL = "https://sgst.prod.dl.playstation.net/sgst/prod/00/PPSA01650_00/app/info/33/x/UP4381-PPSA01650_00-YOUTUBESIEA00000.json"


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class _SofortFaden:
    def __init__(self, target=None, args=(), kwargs=None, **_k):
        self._ziel, self._args, self._kw = target, args, kwargs or {}

    def start(self):
        self._ziel(*self._args, **self._kw)

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False


def _gui(haupt):
    gui = haupt.PS5ConverterGUI.__new__(haupt.PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.is_running = False
    gui.root = mock.Mock()
    gui._hauptfaden_planen = lambda f, *a, **k: f(*a)
    gui._sony_pakete = {}
    gui._sony_lauf = None
    gui._patch_cache = {}
    gui._patch_tree = mock.MagicMock()
    gui._patch_tree.winfo_exists.return_value = True
    gui._patch_tree.get_children.return_value = []
    gui._patch_status_var = mock.Mock()
    gui._metadaten_online_erlaubt = lambda: True
    return gui


class ListeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()

    def _fassungen(self):
        return [pu.Fassung("01.010.002", 0x13600007, "13.60", MANIFEST_URL.replace("33", "34")),
                pu.Fassung("01.009.371", 0x13600007, "13.60", MANIFEST_URL)]

    def test_zeilen_mit_groesse_firmware_und_ladeadresse(self):
        gui = _gui(self.haupt)
        with mock.patch.object(pu, "verxml_holen", return_value=self._fassungen()), \
                mock.patch.object(pu, "manifest_holen",
                                  return_value=pu.Manifest(107675648, [])):
            zeilen, gescheitert = gui._sony_updates_lesen(URI, "PPSA01650")
        self.assertFalse(gescheitert)
        self.assertEqual(2, len(zeilen))
        plattform, fassung, groesse, firmware, datum, neueste, adresse = zeilen[0]
        self.assertEqual("PS5", plattform)
        self.assertEqual("01.010.002", fassung)
        self.assertEqual("13.60", firmware)
        self.assertTrue(neueste)
        self.assertFalse(zeilen[1][5], "Nur die erste ist die neueste")
        self.assertTrue(adresse.startswith("sony-update:https://sgst.prod.dl"))
        self.assertIn("MB", groesse)
        info = gui._sony_pakete[adresse[len("sony-update:"):]]
        self.assertEqual("PPSA01650", info["title_id"])
        self.assertEqual("UP4381-PPSA01650_00-YOUTUBESIEA00000_v01.010.002.pkg", info["dateiname"])

    def test_fehlendes_manifest_gibt_nur_einen_strich_statt_der_groesse(self):
        gui = _gui(self.haupt)
        with mock.patch.object(pu, "verxml_holen", return_value=self._fassungen()), \
                mock.patch.object(pu, "manifest_holen",
                                  side_effect=pu.UpdateFehler("ps5upd.http|503")):
            zeilen, gescheitert = gui._sony_updates_lesen(URI, "PPSA01650")
        self.assertFalse(gescheitert)
        self.assertEqual("-", zeilen[0][2])

    def test_404_von_sony_heisst_keine_liste_nicht_gescheitert(self):
        gui = _gui(self.haupt)
        for code in ("404", "403"):
            with self.subTest(code=code), mock.patch.object(
                    pu, "verxml_holen", side_effect=pu.UpdateFehler("ps5upd.http|" + code)):
                self.assertEqual(([], False), gui._sony_updates_lesen(URI, "PPSA01650"))

    def test_netzfehler_ist_gescheitert_und_steht_im_protokoll(self):
        gui = _gui(self.haupt)
        with mock.patch.object(pu, "verxml_holen",
                               side_effect=pu.UpdateFehler("ps5upd.netz|Zeit abgelaufen")):
            zeilen, gescheitert = gui._sony_updates_lesen(URI, "PPSA01650")
        self.assertEqual([], zeilen)
        self.assertTrue(gescheitert, "Eine unbekannte Liste darf nicht als 'keine Updates' gelten")
        self.assertTrue(any("Zeit abgelaufen" in z for z in gui.protokoll))

    def test_eintrag_ohne_manifestadresse_wird_uebergangen(self):
        gui = _gui(self.haupt)
        with mock.patch.object(pu, "verxml_holen", return_value=[pu.Fassung("01.001.000")]):
            self.assertEqual(([], False), gui._sony_updates_lesen(URI, "PPSA01650"))

    def _suche(self, meta, titel="PPSA01650"):
        gui = _gui(self.haupt)
        gui._letzte_meta = meta
        gui._patchseite_lesen = mock.Mock(return_value=([], False))
        gui._sony_updates_lesen = mock.Mock(return_value=([], False))
        gui._display_patches = mock.Mock()
        with mock.patch.object(self.haupt.threading, "Thread", _SofortFaden):
            gui._fetch_patches_async(titel)
        return gui

    def test_sony_wird_gefragt_wenn_das_spiel_die_adresse_nennt(self):
        gui = self._suche({"title_id": "PPSA01650", "version_file_uri": URI})
        gui._sony_updates_lesen.assert_called_once_with(URI, "PPSA01650")
        gui._patchseite_lesen.assert_called_once()

    def test_sony_wird_nicht_gefragt_ohne_passende_adresse(self):
        faelle = {
            "ohne Adresse": {"title_id": "PPSA01650"},
            "anderes Spiel": {"title_id": "PPSA99999", "version_file_uri": URI},
            "fremder Host": {"title_id": "PPSA01650", "version_file_uri": "https://evil.example/x-version.xml"},
            "keine xml": {"title_id": "PPSA01650", "version_file_uri": "https://sgst.prod.dl.playstation.net/x.json"},
            "ohne Meta": {},
        }
        for name, meta in faelle.items():
            with self.subTest(fall=name):
                gui = self._suche(meta)
                gui._sony_updates_lesen.assert_not_called()

    def test_ps4_titel_fragen_sony_mit_abgeleiteter_adresse(self):
        gui = self._suche({"title_id": "CUSA00001", "version_file_uri": URI}, titel="CUSA00001")
        gui._sony_updates_lesen.assert_called_once()
        adresse, kennung, name = gui._sony_updates_lesen.call_args.args
        self.assertTrue(adresse.startswith("https://gs-sec.ww.np.dl.playstation.net/plo/np/CUSA00001/"))
        self.assertTrue(adresse.endswith("/CUSA00001-ver.xml"))
        self.assertNotEqual(URI, adresse)
        self.assertEqual("PS4", name)

    def test_ohne_freigabe_geht_nichts_ins_netz(self):
        gui = _gui(self.haupt)
        gui._metadaten_online_erlaubt = lambda: False
        gui._patch_abruf_gesperrt_zeigen = mock.Mock()
        gui._letzte_meta = {"title_id": "PPSA01650", "version_file_uri": URI}
        gui._sony_updates_lesen = mock.Mock()
        with mock.patch.object(self.haupt.threading, "Thread", _SofortFaden):
            gui._fetch_patches_async("PPSA01650")
        gui._sony_updates_lesen.assert_not_called()

    def test_zusammenfuehren_sony_zuerst_gleiche_version_der_seite_entfaellt(self):
        gui = _gui(self.haupt)
        seite_neu = ("PS5", "06.005.000", "50 GB", "12.00", "2026", True, "https://prosperopatches.com/X")
        seite_alt = ("PS5", "06.004.000", "50 GB", "12.00", "2026", False, "https://prosperopatches.com/X")
        sony = ("PS5", "06.005", "49 GB", "12.00", "-", True, "sony-update:" + MANIFEST_URL)
        ergebnis = gui._patchzeilen_zusammenfuehren([seite_neu, seite_alt, sony])
        self.assertEqual([sony, seite_alt], ergebnis)

    def test_zusammenfuehren_ohne_sony_bleibt_unveraendert(self):
        gui = _gui(self.haupt)
        zeilen = [("PS5", "1.0", "-", "-", "-", True, "https://prosperopatches.com/X")]
        self.assertEqual(zeilen, gui._patchzeilen_zusammenfuehren(zeilen))

    def test_download_klick_geht_an_den_neuen_weg(self):
        gui = _gui(self.haupt)
        gui._sony_update_laden = mock.Mock()
        gui._download_starten("sony-update:" + MANIFEST_URL, True)
        gui._sony_update_laden.assert_called_once_with(MANIFEST_URL, True)

    def test_fehlertexte_gibt_es_in_beiden_sprachen(self):
        gui = _gui(self.haupt)
        self.assertIn("Prüfsumme", gui._ps5upd_text("ps5upd.pruefsumme|3"))
        self.assertIn("3", gui._ps5upd_text("ps5upd.pruefsumme|3"))
        self.assertIn("404", gui._ps5upd_text("ps5upd.http|404"))
        self.assertEqual("irgendein Systemtext", gui._ps5upd_text("irgendein Systemtext"))
        for schluessel in ("ps5upd.host_fremd", "ps5upd.umleitung_fremd", "ps5upd.zu_gross",
                           "ps5upd.xml_unzulaessig", "ps5upd.xml_kaputt", "ps5upd.manifest_kaputt",
                           "ps5upd.abgebrochen", "ps5upd.platz", "ps5upd.pruefsumme",
                           "ps5upd.netz", "ps5upd.http"):
            self.assertIn(schluessel, STRINGS, schluessel)

    def test_alle_neuen_texte_zweisprachig_mit_gleichen_platzhaltern(self):
        import re
        muster = re.compile(r"\{(\w+)\}")
        neu = [k for k in STRINGS if k.startswith("ps5upd.")]
        self.assertGreater(len(neu), 25)
        for schluessel in neu:
            with self.subTest(schluessel=schluessel):
                self.assertTrue(STRINGS[schluessel]["de"] and STRINGS[schluessel]["en"])
                self.assertEqual(set(muster.findall(STRINGS[schluessel]["de"])),
                                 set(muster.findall(STRINGS[schluessel]["en"])))


class MetadatenTests(unittest.TestCase):

    def test_param_json_liefert_die_adresse(self):
        from ps5_validator.utils import abbild_metadaten
        leser = abbild_metadaten.Metadatenleser.__new__(abbild_metadaten.Metadatenleser)
        meta = leser._meta_from_param_json_payload({
            "titleId": "PPSA01552", "contentVersion": "06.004.000",
            "versionFileUri": "https://sgst.prod.dl.playstation.net/x/y-version.xml"})
        self.assertEqual("https://sgst.prod.dl.playstation.net/x/y-version.xml",
                         meta["version_file_uri"])
        self.assertEqual("PPSA01552", meta["title_id"])

    def test_ohne_adresse_kein_schluessel(self):
        """Ein Platzhalter hiesse 'unbekannt', wo es nichts zu wissen gibt."""
        from ps5_validator.utils import abbild_metadaten
        leser = abbild_metadaten.Metadatenleser.__new__(abbild_metadaten.Metadatenleser)
        for payload in ({"titleId": "PPSA00001"}, {"titleId": "PPSA00001", "versionFileUri": ""},
                        {"titleId": "PPSA00001", "versionFileUri": None},
                        {"titleId": "PPSA00001", "versionFileUri": {"a": 1}}):
            with self.subTest(payload=payload):
                self.assertNotIn("version_file_uri", leser._meta_from_param_json_payload(payload))


@unittest.skipUnless(TK_DA, "keine Anzeige")
class LadenFensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self):
        self.teile = [os.urandom(2_500_000), os.urandom(90_000)]
        self.server = _Server({"/t0.bin": self.teile[0], "/t1.bin": self.teile[1]})
        versatz = 0
        stuecke = []
        for n, daten in enumerate(self.teile):
            stuecke.append({"url": self.server.url("/t%d.bin" % n), "fileOffset": versatz,
                            "fileSize": len(daten), "hashValue": hashlib.sha256(daten).hexdigest()})
            versatz += len(daten)
        manifest = json.dumps({"originalFileSize": versatz, "pieces": stuecke}).encode()
        self.server.teile["/m.json"] = manifest
        self.addCleanup(self.server.ende)
        hosts = mock.patch.object(pu, "ERLAUBTE_HOSTS", ("127.0.0.1",))
        hosts.start()
        self.addCleanup(hosts.stop)
        self.tmp = tempfile.TemporaryDirectory(prefix="ps5upd_fenster_")
        self.addCleanup(self.tmp.cleanup)
        self.key = self.server.url("/m.json")
        self.app._sony_pakete[self.key] = {
            "title_id": "PPSA01650", "version": "01.009.371", "manifest_url": self.key,
            "dateiname": "UP4381-PPSA01650_00-YOUTUBESIEA00000_v01.009.371.pkg",
            "name": "UP4381-PPSA01650_00-YOUTUBESIEA00000", "gesamt": versatz}
        basis = mock.patch.object(self.app, "_download_basis", return_value=self.tmp.name)
        basis.start()
        self.addCleanup(basis.stop)
        self.addCleanup(setattr, self.app, "_sony_lauf", None)

    def _warten(self, grenze=60.0):
        ende = time.monotonic() + grenze

        def takt():
            lauf = self.app._sony_lauf
            if (lauf is not None and not lauf["aktiv"]) or time.monotonic() > ende:
                # Dem Takt des Fensters noch einen Durchlauf gonnen.
                _WURZEL.after(600, _WURZEL.quit)
            else:
                _WURZEL.after(20, takt)

        _WURZEL.after(0, takt)
        _WURZEL.mainloop()

    def _fenster(self):
        return [w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)
                and w.title() == self.app._t("ps5upd.fenster_titel")]

    def _alle(self, w):
        for k in w.winfo_children():
            yield k
            yield from self._alle(k)

    @staticmethod
    def _text_von(w) -> str:
        try:
            return str(w.cget("text"))
        except tk.TclError:
            return ""

    def _texte(self, fenster):
        return [self._text_von(w) for w in self._alle(fenster)]

    def test_klick_laedt_in_den_update_ordner_und_meldet_fertig(self):
        self.app._sony_update_laden(self.key, True)
        fenster = self._fenster()
        self.assertEqual(1, len(fenster))
        self.addCleanup(fenster[0].destroy)
        self._warten()
        ziel = Path(self.tmp.name) / "PS5 Spiele Updates" / "UP4381-PPSA01650_00-YOUTUBESIEA00000_v01.009.371.pkg"
        self.assertTrue(ziel.is_file(), "Die Datei fehlt: " + str(ziel))
        self.assertEqual(b"".join(self.teile), ziel.read_bytes())
        self.assertFalse(Path(str(ziel) + ".teil").exists())
        texte = " ".join(self._texte(fenster[0]))
        self.assertIn(self.app._t("ps5upd.knopf_ordner"), texte)
        ordner_btn = next(w for w in self._alle(fenster[0])
                          if self._text_von(w) == self.app._t("ps5upd.knopf_ordner"))
        self.assertEqual("normal", str(ordner_btn.cget("state")), "Nach Fertig muss der Ordner erreichbar sein")

    def test_aeltere_fassung_geht_in_den_patch_ordner(self):
        self.app._sony_update_laden(self.key, False)
        fenster = self._fenster()
        self.addCleanup(fenster[0].destroy)
        self._warten()
        ziel = Path(self.tmp.name) / "Patches" / "UP4381-PPSA01650_00-YOUTUBESIEA00000_v01.009.371.pkg"
        self.assertTrue(ziel.is_file())

    def test_vorhandene_datei_wird_nicht_noch_einmal_geladen(self):
        ordner = Path(self.tmp.name) / "PS5 Spiele Updates"
        ordner.mkdir()
        (ordner / "UP4381-PPSA01650_00-YOUTUBESIEA00000_v01.009.371.pkg").write_bytes(b"da")
        with mock.patch.object(self.haupt.messagebox, "showinfo") as meldung:
            self.app._sony_update_laden(self.key, True)
        self.assertEqual(1, meldung.call_count)
        self.assertEqual([], self._fenster())
        self.assertEqual([], [r for r in self.server.anfragen if r[0].startswith("/t")])

    def test_zweiter_klick_waehrend_eines_laufs_wird_abgewiesen(self):
        self.app._sony_lauf = {"aktiv": True}
        with mock.patch.object(self.haupt.messagebox, "showinfo") as meldung:
            self.app._sony_update_laden(self.key, True)
        self.assertEqual(1, meldung.call_count)
        self.assertEqual([], self._fenster())

    def test_unbekannte_adresse_tut_nichts(self):
        self.app._sony_update_laden("http://127.0.0.1:1/gibtsnicht.json", True)
        self.assertEqual([], self._fenster())

    def test_ohne_speicherort_wird_gefragt_und_bei_nein_nichts_gestartet(self):
        with mock.patch.object(self.app, "_download_basis", return_value=""), \
                mock.patch.object(self.app, "_download_basis_waehlen", return_value="") as frage, \
                mock.patch.object(self.haupt.messagebox, "showwarning") as warnung:
            self.app._sony_update_laden(self.key, True)
        self.assertEqual(1, frage.call_count)
        self.assertEqual(1, warnung.call_count)
        self.assertEqual([], self._fenster())

    def test_fehler_wird_im_fenster_gezeigt(self):
        self.server.kaputt.update({"/t0.bin"})
        self.app._sony_update_laden(self.key, True)
        fenster = self._fenster()
        self.addCleanup(fenster[0].destroy)
        self._warten()
        ziel = Path(self.tmp.name) / "PS5 Spiele Updates" / "UP4381-PPSA01650_00-YOUTUBESIEA00000_v01.009.371.pkg"
        self.assertFalse(ziel.exists(), "Eine Datei mit falscher Pruefsumme darf nie fertig heissen")
        # Das Statusfeld ist eine StringVar; gelesen wird sie ueber das Label.
        status = ""
        for w in self._alle(fenster[0]):
            try:
                name = str(w.cget("textvariable"))
            except tk.TclError:
                continue
            if name:
                status += " " + str(_WURZEL.globalgetvar(name))
        self.assertIn(self.app._t("ps5upd.status_fehler", fehler="")[:11], status)
        self.assertIn("Prüfsumme", status)


if __name__ == "__main__":
    unittest.main()
