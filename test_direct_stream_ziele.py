# -*- coding: utf-8 -*-
"""Direct Stream: Pakete nach /data/pkg, Abbildformate in der Auswahl (Nutzer 06.10.2026).

Die Dateien des Werkzeugs bleiben unveraendert: Das Programm legt sich um ``transfer`` (Zielordner je Datei)
und beantwortet ``/api/pick`` selbst. Kein Test oeffnet einen echten Dialog - die Auswahl ist nachgebildet.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402,F401
from ps5_validator.utils import direct_stream as ds         # noqa: E402

ORDNER = PROJEKT / ds.ORDNER


class ZielordnerTests(unittest.TestCase):
    def test_pakete_bei_der_vorgabe_nach_data_pkg(self) -> None:
        self.assertEqual("/data/pkg", ds.zielordner_fuer("Spiel.PKG", "/data/homebrew"))
        self.assertEqual("/data/pkg", ds.zielordner_fuer("spiel.pkg", "/data/homebrew/"))

    def test_abbilder_bleiben_bei_der_vorgabe(self) -> None:
        for name in ("Spiel.ffpkg", "Spiel.ffpfsc", "Spiel.exfat", "Spiel.ffpfs", "datei.bin"):
            with self.subTest(name=name):
                self.assertEqual("/data/homebrew", ds.zielordner_fuer(name, "/data/homebrew"))

    def test_selbst_gewaehlter_ordner_gilt_fuer_alles(self) -> None:
        self.assertEqual("/mnt/usb0", ds.zielordner_fuer("spiel.pkg", "/mnt/usb0"))


class UmleitungTests(unittest.TestCase):
    def _modul(self):
        aufrufe = []
        modul = types.ModuleType("ps5_streamer_attrappe")
        modul.transfer = lambda job, cfg, *a, **k: aufrufe.append((job["name"], cfg["folder"]))
        ds._transfer_umleiten(modul)
        return modul, aufrufe

    def test_paket_geht_nach_data_pkg_rest_bleibt(self) -> None:
        modul, aufrufe = self._modul()
        cfg = {"folder": "/data/homebrew", "host": "192.0.2.10"}
        modul.transfer({"name": "a.pkg"}, cfg, None)
        modul.transfer({"name": "b.ffpkg"}, cfg, None)
        self.assertEqual([("a.pkg", "/data/pkg"), ("b.ffpkg", "/data/homebrew")], aufrufe)
        self.assertEqual("/data/homebrew", cfg["folder"], "die Einstellungen selbst bleiben unberuehrt")

    def test_nur_einmal_umgelegt(self) -> None:
        modul, _aufrufe = self._modul()
        erste = modul.transfer
        ds._transfer_umleiten(modul)
        self.assertIs(erste, modul.transfer)

    def test_das_echte_werkzeug_ist_umgelegt(self) -> None:
        modul = ds.module_laden(str(ORDNER))
        self.assertTrue(getattr(modul.transfer, "_ps5conv_umgeleitet", False))
        self.assertIs(sys.modules["transfer_core"].transfer, modul.transfer.__wrapped__)


class AuswahlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ds_ziele_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_ordner_findet_abbilder_und_pakete(self) -> None:
        for name in ("a.pkg", "b.ffpkg", "c.ffpfsc", "d.exfat", "e.ffpfs", "liesmich.txt"):
            Path(self.tmp, name).write_bytes(b"x")
        gefunden = sorted(os.path.basename(p) for p in ds.ordner_durchsuchen(self.tmp))
        self.assertEqual(["a.pkg", "b.ffpkg", "c.ffpfsc", "d.exfat", "e.ffpfs"], gefunden)

    def test_hoechstens_hundert(self) -> None:
        for nummer in range(130):
            Path(self.tmp, "%03d.pkg" % nummer).write_bytes(b"x")
        self.assertEqual(100, len(ds.ordner_durchsuchen(self.tmp)))

    def _anfrage(self, sitzung, koerper):
        verbindung = http.client.HTTPConnection("127.0.0.1", sitzung.port, timeout=10)
        try:
            verbindung.request("POST", "/api/pick", body=json.dumps(koerper).encode(),
                               headers={"Host": "127.0.0.1:%d" % sitzung.port, "Content-Type": "application/json",
                                        "X-Session-Token": sitzung.marke})
            antwort = verbindung.getresponse()
            return antwort.status, json.loads(antwort.read())
        finally:
            verbindung.close()

    def test_server_beantwortet_die_auswahl_selbst(self) -> None:
        Path(self.tmp, "spiel.ffpkg").write_bytes(b"x")
        sitzung = ds.starten(str(ORDNER), os.path.join(self.tmp, "daten"), sprache="de")
        self.addCleanup(sitzung.beenden)
        with mock.patch.object(ds, "_auswahl_dialog", return_value=([], self.tmp, False)) as dialog:
            status, antwort = self._anfrage(sitzung, {"type": "folder"})
        self.assertEqual(200, status)
        dialog.assert_called_once_with("folder", "de")
        self.assertEqual([os.path.join(self.tmp, "spiel.ffpkg")], antwort["paths"])
        with mock.patch.object(ds, "_auswahl_dialog", return_value=(["C:/x/a.exfat"], "", False)):
            status, antwort = self._anfrage(sitzung, {"type": "file"})
        self.assertEqual(["C:/x/a.exfat"], antwort["paths"])

    def test_ohne_marke_keine_auswahl(self) -> None:
        sitzung = ds.starten(str(ORDNER), os.path.join(self.tmp, "daten"))
        self.addCleanup(sitzung.beenden)
        verbindung = http.client.HTTPConnection("127.0.0.1", sitzung.port, timeout=10)
        self.addCleanup(verbindung.close)
        with mock.patch.object(ds, "_auswahl_dialog") as dialog:
            verbindung.request("POST", "/api/pick", body=b"{}",
                               headers={"Host": "127.0.0.1:%d" % sitzung.port,
                                        "Content-Type": "application/json"})
            self.assertEqual(401, verbindung.getresponse().status)
        dialog.assert_not_called()


class ZielwahlTests(unittest.TestCase):
    """Knopf "Ziel: …" im Kopf der Seite (Nutzer 06.10.2026): interner Speicher oder USB."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ds_zielwahl_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_sitzung_stellt_den_ordner_ueber_das_werkzeug_um(self) -> None:
        sitzung = ds.starten(str(ORDNER), os.path.join(self.tmp, "daten"), host="192.0.2.10", ftp_port=2121)
        self.addCleanup(sitzung.beenden)
        self.assertEqual("/data/homebrew", sitzung.zielordner)
        sitzung.zielordner_setzen("/mnt/usb0")
        self.assertEqual("/mnt/usb0", sitzung.zielordner)
        einstellungen = sitzung.stand()["settings"]
        self.assertEqual(("192.0.2.10", 2121), (einstellungen["host"], einstellungen["port"]),
                         "Adresse und Port bleiben")

    def test_unzulaessiger_ordner_wird_abgelehnt(self) -> None:
        sitzung = ds.starten(str(ORDNER), os.path.join(self.tmp, "daten"))
        self.addCleanup(sitzung.beenden)
        with self.assertRaises(Exception):
            sitzung.zielordner_setzen("relativ/ohne/schraegstrich")
        self.assertEqual("/data/homebrew", sitzung.zielordner)

    def _gui(self):
        import PS5ImageConverter_Pro_FINAL_revised as APP  # noqa: PLC0415
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        gui.root = None
        gui.zeilen = []
        gui._append_to_log = gui.zeilen.append
        return APP, gui

    def test_lesbare_ziele(self) -> None:
        _APP, gui = self._gui()
        self.assertEqual("Interner Speicher", gui._direct_stream_ziel_text("/data/homebrew/"))
        self.assertEqual("USB usb0", gui._direct_stream_ziel_text("/mnt/usb0"))
        self.assertEqual("USB usb1/spiele", gui._direct_stream_ziel_text("/mnt/usb1/spiele"))
        self.assertEqual("/data/anderes", gui._direct_stream_ziel_text("/data/anderes"))

    def test_umstellen_meldet_und_fehler_kommt_als_meldung(self) -> None:
        APP, gui = self._gui()
        sitzung = mock.Mock(laeuft=True)
        gui._direct_stream_sitzung = sitzung
        gui._direct_stream_ziel_zeigen = lambda: None
        gui._direct_stream_ziel_setzen("/mnt/usb0")
        sitzung.zielordner_setzen.assert_called_once_with("/mnt/usb0")
        self.assertIn("auch Pakete", "".join(gui.zeilen))
        sitzung.zielordner_setzen.side_effect = RuntimeError("Pause transfers first")
        with mock.patch.object(APP.messagebox, "showerror") as fehler:
            gui._direct_stream_ziel_setzen("/data/homebrew")
        fehler.assert_called_once()


if __name__ == "__main__":
    unittest.main()
