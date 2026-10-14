# -*- coding: utf-8 -*-
"""Die Huelle um ``ffpfsc-pkg-tool`` (``utils/ps5_pkg_werkzeug.py``) und die Hilfen des Fensters (seit v1.9.71).

Am echten Werkzeug gemessen (09.10.2026, ein 939-MB-PS5-Paket): ``list-inner`` 4 s, voller Entpack 53 s und
``extract-inner --members`` mit allen Dateien 52 s - 118 von 118 Dateien, alle SHA-256 gleich, nur der zweite Weg
meldet den Fortschritt je Datei. Ein echter Lauf gehoert nicht in die Testreihe (kein Paket im Projekt); die
Huelle wird mit einem Ersatz fuer ``laufen`` geprueft, und ``laufen`` selbst mit dem Python-Interpreter als
Stellvertreter des Werkzeugs.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.ui import ps5_pkg_fenster as fz   # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz   # noqa: E402


def _info(**kw) -> "wz.PaketInfo":
    vorgabe = dict(pfad=r"E:\Spiele\Spiel.pkg", groesse=int(1.5 * 1024 ** 3), typ="FullDebug",
                   content_id="EP6665-PPSA16709_00-AOH0000000000000", title_id="PPSA16709", titel="Asterix & Obelix: Heroes",
                   param={"contentVersion": "01.000.000", "conceptId": "10008371"})
    vorgabe.update(kw)
    return wz.PaketInfo(**vorgabe)


class OrtTests(unittest.TestCase):

    def test_die_plattformordner(self) -> None:
        for plattform, maschine, soll in (("win32", "AMD64", "win-x64"), ("linux", "x86_64", "linux-x64"),
                                          ("darwin", "arm64", "osx-arm64"), ("darwin", "x86_64", "osx-x64")):
            with self.subTest(plattform=plattform, maschine=maschine):
                with mock.patch.object(wz.sys, "platform", plattform), \
                        mock.patch.object(wz.platform, "machine", return_value=maschine):
                    self.assertEqual(soll, wz.unterordner())

    def test_werkzeug_suchen_findet_den_bau_der_plattform(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            name = "ffpfsc-pkg-tool.exe" if sys.platform == "win32" else "ffpfsc-pkg-tool"
            ordner = Path(t) / wz.ORDNER / wz.unterordner()
            ordner.mkdir(parents=True)
            (ordner / name).write_bytes(b"x")
            self.assertEqual(str(ordner / name), wz.werkzeug_suchen(["/gibt/es/nicht", t]))
            self.assertEqual("", wz.werkzeug_suchen(["/gibt/es/nicht"]))
            self.assertEqual("", wz.werkzeug_suchen([]))

    @unittest.skipUnless(sys.platform in ("win32", "linux", "darwin"), "keine bekannte Plattform")
    def test_der_bau_dieser_plattform_liegt_im_projekt(self) -> None:
        pfad = wz.werkzeug_suchen([str(PROJEKT)])
        self.assertTrue(pfad, "PS5-PKG-Tool/%s fehlt" % wz.unterordner())
        ordner = Path(pfad).parent
        for datei in ("ffpfsc-pkg-tool.dll", "LibProsperoPkg.dll", "LibOrbisPkg.dll", "BCnEncoder.dll",
                      "CommunityToolkit.HighPerformance.dll", "Magick.NET-Q8-AnyCPU.dll", "Magick.NET.Core.dll"):
            self.assertTrue((ordner / datei).is_file(), datei)
        natives = [d for d in ordner.iterdir() if d.name.lower().startswith("magick.native")]
        self.assertTrue(natives, "Magick.Native fehlt - ohne sie bekommt ein Paket kein icon0.dds")

    def test_alle_vier_plattformen_sind_gebaut(self) -> None:
        for rid in ("win-x64", "linux-x64", "osx-arm64", "osx-x64"):
            with self.subTest(rid=rid):
                ordner = PROJEKT / wz.ORDNER / rid
                self.assertTrue((ordner / "ffpfsc-pkg-tool.dll").is_file())
                self.assertTrue(any(d.name.lower().startswith("magick.native") for d in ordner.iterdir()))

    def test_lizenz_und_quelle_liegen_bei(self) -> None:
        wurzel = PROJEKT / wz.ORDNER
        self.assertIn("GNU GENERAL PUBLIC LICENSE", (wurzel / "LICENSE").read_text(encoding="utf-8")[:200])
        self.assertTrue((wurzel / "src" / "ffpfsc-pkg-tool" / "Program.cs").is_file())
        self.assertTrue((wurzel / "src" / "ffpfsc-pkg-tool" / "PkgTool.csproj").is_file())
        projekt = (wurzel / "src" / "ffpfsc-pkg-tool" / "PkgTool.csproj").read_text(encoding="utf-8")
        self.assertIn("<TargetFramework>net10.0</TargetFramework>", projekt)
        self.assertIn("<SelfContained>false</SelfContained>", projekt)


class LaufenTests(unittest.TestCase):
    """``laufen`` mit dem Python-Interpreter als Werkzeug."""

    def test_zeilen_rueckgabewert_und_fortschritt_mit_wagenruecklauf(self) -> None:
        code = "import sys; sys.stdout.write('a\\r[####] 50% extract (x)\\rfertig\\n'); sys.exit(3)"
        zeilen: list[str] = []
        rc, aus = wz.laufen(sys.executable, ["-c", code], zeile=zeilen.append)
        self.assertEqual(3, rc)
        self.assertEqual(["a", "[####] 50% extract (x)", "fertig"], zeilen)
        self.assertIn("fertig", aus)

    def test_der_abbruch_beendet_den_prozess(self) -> None:
        code = "import sys, time; print('los', flush=True); time.sleep(60)"
        gesehen = []
        start = time.time()
        rc, _aus = wz.laufen(sys.executable, ["-c", code], zeile=gesehen.append, abbruch=lambda: bool(gesehen))
        self.assertEqual(-1, rc)
        self.assertLess(time.time() - start, 30)

    def test_ein_fehlendes_werkzeug_gibt_eine_meldung(self) -> None:
        with self.assertRaises(wz.Fehler):
            wz.laufen(os.path.join(tempfile.gettempdir(), "gibt-es-bestimmt-nicht.exe"), [])


class AuswertungTests(unittest.TestCase):

    def test_json_wird_aus_gemischter_ausgabe_gelesen(self) -> None:
        aus = '[info] los\n{"a": 1, "b": [1, 2]}\nfertig\n'
        self.assertEqual({"a": 1, "b": [1, 2]}, wz._json_aus(aus))

    def test_kein_json_gibt_eine_meldung(self) -> None:
        with self.assertRaises(wz.Fehler):
            wz._json_aus("nur Text")
        with self.assertRaises(wz.Fehler):
            wz._json_aus("{kaputt")

    def test_der_fehlertext_nimmt_die_letzte_fehlerzeile(self) -> None:
        self.assertEqual("[error] FileNotFoundException: package not found",
                         wz._fehlertext("[info] x\n[error] FileNotFoundException: package not found\n"))
        self.assertEqual("nur das", wz._fehlertext("nur das\n"))
        self.assertEqual("kein Text", wz._fehlertext(""))

    def test_titel_aus_param(self) -> None:
        lokal = {"defaultLanguage": "de-DE", "de-DE": {"titleName": "Deutsch"}, "en-US": {"titleName": "English"}}
        self.assertEqual("Deutsch", wz.titel_aus_param({"localizedParameters": dict(lokal)}))
        lokal["defaultLanguage"] = "fr-FR"
        self.assertEqual("English", wz.titel_aus_param({"localizedParameters": dict(lokal)}))
        self.assertEqual("Nur der", wz.titel_aus_param({"localizedParameters": {"ja-JP": {"titleName": " Nur der "}}}))
        self.assertEqual("", wz.titel_aus_param({"localizedParameters": {"en-US": {"titleName": "  "}}}))
        self.assertEqual("", wz.titel_aus_param({}))

    def test_debug_paket_und_version(self) -> None:
        self.assertTrue(_info(typ="FullDebug").debug)
        self.assertFalse(_info(typ="Retail").debug)
        self.assertEqual("01.000.000", _info().version)
        self.assertEqual("", _info(param={}).version)


class HuelleTests(unittest.TestCase):

    def test_lesen_holt_param_und_cover_aus_dem_paket(self) -> None:
        kopf = {"size_bytes": 1000, "package_type": "FullDebug", "content_id": "EP6665-PPSA16709_00-AOH0000000000000",
                "title_id": "PPSA16709", "drm_type": 0}

        def laufen(werkzeug, argumente, **_kw):
            ziel = Path(argumente[2]) / "sce_sys"
            ziel.mkdir(parents=True)
            (ziel / "param.json").write_text(json.dumps({"contentVersion": "01.000.000", "localizedParameters": {
                "defaultLanguage": "en-US", "en-US": {"titleName": "Spiel"}}}), encoding="utf-8")
            (ziel / "icon0.png").write_bytes(b"png")
            self.assertIn("--members", argumente)
            return 0, "OK"

        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "inspect", return_value=kopf), \
                mock.patch.object(wz, "laufen", side_effect=laufen):
            info = wz.lesen("werkzeug", "x.pkg", t)
            self.assertEqual(("PPSA16709", "Spiel", "01.000.000", 1000), (info.title_id, info.titel, info.version, info.groesse))
            self.assertTrue(os.path.isfile(info.icon))

    def test_lesen_ohne_param_gibt_wenigstens_die_kopfdaten(self) -> None:
        kopf = {"size_bytes": 5, "package_type": "FullDebug", "content_id": "C", "title_id": "PPSA00001"}
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "inspect", return_value=kopf), \
                mock.patch.object(wz, "laufen", return_value=(1, "[error] kaputt")):
            info = wz.lesen("werkzeug", "x.pkg", t)
            self.assertEqual("PPSA00001", info.title_id)
            self.assertEqual("", info.titel)
            self.assertEqual("", info.icon)

    def test_extrahieren_geht_ueber_members_und_meldet_je_datei(self) -> None:
        eintraege = [{"path": "Media", "type": "dir"}, {"path": "Media/a.dat", "type": "file", "size": 5},
                     {"path": "eboot.bin", "type": "file", "size": 9}]
        aufrufe: list[list[str]] = []
        inhalt: dict = {}

        def laufen(werkzeug, argumente, zeile=None, **_kw):
            aufrufe.append(list(argumente))
            liste = argumente[argumente.index("--members") + 1]
            inhalt["liste"] = Path(liste).read_text(encoding="utf-8").split()
            for p, name in ((50, "Media/a.dat"), (100, "")):
                zeile("[####] %d%% extract%s" % (p, " (%s)" % name if name else ""))
            zeile("[info] sonst")
            return 0, "[####] 100% extract\nOK - extracted 2 file(s) and 1 folder(s) to X\n"

        fortschritt, zeilen = [], []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", return_value=eintraege), \
                mock.patch.object(wz, "laufen", side_effect=laufen):
            schluss = wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), zeile=zeilen.append,
                                     fortschritt=lambda p, d: fortschritt.append((p, d)), arbeitsordner=t)
            self.assertEqual(1, len(aufrufe))
            self.assertEqual(["Media", "Media/a.dat", "eboot.bin"], inhalt["liste"])
            self.assertEqual([(50, "Media/a.dat"), (100, "")], fortschritt)
            self.assertEqual(["[info] sonst"], [z for z in zeilen if "Paketinhalt" not in z])
            self.assertEqual(2, len([z for z in zeilen if "Paketinhalt" in z]), "Hinweis vor und nach dem Lesen des Inhalts")
            self.assertTrue(schluss.startswith("OK"))
            self.assertEqual([], [n for n in os.listdir(t) if n.startswith("ps5conv_teile_")], "die Liste wird entfernt")

    # ---- Lebenszeichen waehrend das Werkzeug schweigt (12.10.2026: list-inner 80 s ohne Meldung, Fenster auf 0 %) ----
    @staticmethod
    def _herzschlaege() -> list:
        return [t for t in threading.enumerate() if t.name == "ps5pkg-herzschlag"]

    def _extrahieren_mit(self, laufen, fortschritt, baum_wert=None, **kw):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "_HERZSCHLAG", 0.05), \
                mock.patch.object(wz, "baum", **({"return_value": baum_wert} if baum_wert is not None else {"side_effect": kw.pop("baum")})), \
                mock.patch.object(wz, "laufen", side_effect=laufen):
            return wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), fortschritt=fortschritt, arbeitsordner=t, **kw)

    def test_schweigt_das_werkzeug_kommt_ein_lebenszeichen_mit_dem_letzten_stand(self) -> None:
        def laufen(werkzeug, argumente, zeile=None, **_kw):
            zeile("[####] 30% extract (Media/gross.dat)")
            time.sleep(0.5)
            return 0, "OK - extracted 1 file(s) to X\n"

        meldungen: list = []
        self._extrahieren_mit(laufen, lambda p, d: meldungen.append((p, d)), [{"path": "a", "type": "file", "size": 1}])
        herz = [(p, d) for p, d in meldungen if "·" in d]
        self.assertGreaterEqual(len(herz), 2, meldungen)
        for p, d in herz:
            self.assertEqual(30, p, "der Prozentwert bleibt der des Werkzeugs - nichts wird erfunden")
            self.assertTrue(d.startswith("Media/gross.dat · 0:0"), d)

    def test_das_lebenszeichen_laeuft_schon_beim_lesen_des_inhalts(self) -> None:
        def baum(*_a, **_k):
            time.sleep(0.4)
            return [{"path": "a", "type": "file", "size": 1}]

        meldungen: list = []
        self._extrahieren_mit(lambda *a, **k: (0, "OK - extracted 1 file(s)\n"), lambda p, d: meldungen.append((p, d)),
                              baum=baum)
        herz = [(p, d) for p, d in meldungen if "·" in d]
        self.assertGreaterEqual(len(herz), 2, "waehrend list-inner kommt schon etwas")
        self.assertTrue(all(p == 0 and d.startswith("… · ") for p, d in herz), herz)

    def test_meldet_das_werkzeug_regelmaessig_gibt_es_kein_lebenszeichen(self) -> None:
        def laufen(werkzeug, argumente, zeile=None, **_kw):
            for i in range(8):
                zeile("[####] %d%% extract (a)" % (i * 10))
                time.sleep(0.02)
            return 0, "OK - extracted 1 file(s)\n"

        meldungen: list = []
        self._extrahieren_mit(laufen, lambda p, d: meldungen.append((p, d)), [{"path": "a", "type": "file", "size": 1}])
        self.assertEqual([], [m for m in meldungen if "·" in m[1]])

    def test_der_herzschlag_endet_mit_dem_aufruf_auch_bei_fehlern(self) -> None:
        def laufen(*_a, **_k):
            return 1, "[error] kaputt"

        with self.assertRaises(wz.Fehler):
            self._extrahieren_mit(laufen, lambda p, d: None, [{"path": "a", "type": "file", "size": 1}])
        ende = time.time() + 2
        while self._herzschlaege() and time.time() < ende:
            time.sleep(0.02)
        self.assertEqual([], self._herzschlaege())

    def test_der_herzschlag_endet_auch_wenn_das_lesen_des_inhalts_unerwartet_scheitert(self) -> None:
        def baum(*_a, **_k):
            raise RuntimeError("unerwartet")

        with self.assertRaises(RuntimeError):
            self._extrahieren_mit(lambda *a, **k: (0, "OK"), lambda p, d: None, baum=baum)
        ende = time.time() + 2
        while self._herzschlaege() and time.time() < ende:
            time.sleep(0.02)
        self.assertEqual([], self._herzschlaege())

    def test_ohne_rueckruf_startet_kein_herzschlag(self) -> None:
        gesehen: list = []

        def laufen(*_a, **_k):
            gesehen.append(len(self._herzschlaege()))
            return 0, "OK - extracted 1 file(s)\n"

        ende = time.time() + 2                           # Nachzuegler der Tests davor (schlafen noch) abwarten
        while self._herzschlaege() and time.time() < ende:
            time.sleep(0.02)
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", return_value=[
                {"path": "a", "type": "file", "size": 1}]), mock.patch.object(wz, "laufen", side_effect=laufen):
            wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), arbeitsordner=t)
        self.assertEqual([0], gesehen)

    def test_scheitert_members_folgt_der_volle_entpack(self) -> None:
        aufrufe: list[list[str]] = []

        def laufen(werkzeug, argumente, **_kw):
            aufrufe.append(list(argumente))
            if "--members" in argumente:
                return 1, "[error] InvalidDataException: kaputt"
            return 0, "OK - extracted 3 file(s) to X\n"

        meldungen: list[str] = []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", return_value=[
                {"path": "a", "type": "file", "size": 1}]), mock.patch.object(wz, "laufen", side_effect=laufen):
            schluss = wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), zeile=meldungen.append, arbeitsordner=t)
        self.assertEqual(2, len(aufrufe))
        self.assertNotIn("--members", aufrufe[1])
        self.assertTrue(schluss.startswith("OK"))
        self.assertTrue(any("voller Entpack" in m for m in meldungen))

    def test_ohne_inhaltsliste_folgt_der_volle_entpack(self) -> None:
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", side_effect=wz.Fehler("kein JSON")), \
                mock.patch.object(wz, "laufen", return_value=(0, "OK - extracted 1 file(s) to X\n")) as lauf:
            wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), arbeitsordner=t)
        self.assertEqual(["extract-inner", "x.pkg", os.path.join(t, "ziel")], lauf.call_args.args[1])

    def test_ein_fehler_ohne_ok_wird_gemeldet(self) -> None:
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", return_value=[]), \
                mock.patch.object(wz, "laufen", return_value=(2, "[usage] falsch")):
            with self.assertRaises(wz.Fehler):
                wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), arbeitsordner=t)

    def test_abbruch_gibt_abgebrochen(self) -> None:
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", return_value=[
                {"path": "a", "type": "file", "size": 1}]), mock.patch.object(wz, "laufen", return_value=(-1, "")):
            with self.assertRaises(wz.Fehler) as ctx:
                wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), arbeitsordner=t)
            self.assertEqual("abgebrochen", str(ctx.exception))
            self.assertEqual([], [n for n in os.listdir(t) if n.startswith("ps5conv_teile_")])

    def test_pruefen_liest_die_liste(self) -> None:
        antwort = json.dumps({"pass": 30, "warn": 1, "fail": 2, "results": [{"Check": "x", "Level": "fail", "Message": "m"}]})
        with mock.patch.object(wz, "laufen", return_value=(1, antwort + "\n")):
            erg = wz.pruefen("werkzeug", "x.pkg")
        self.assertEqual((30, 1, 2), (erg["pass"], erg["warn"], erg["fail"]))


CID = "UP8016-PPSA19015_00-0489895718491618"


class OrdnerTests(unittest.TestCase):

    def _spiel(self, wurzel: str, param: dict | None = None, icon: bool = True) -> str:
        ordner = os.path.join(wurzel, "Spiel")
        os.makedirs(os.path.join(ordner, "sce_sys"))
        Path(ordner, "eboot.bin").write_bytes(b"x" * 1000)
        Path(ordner, "Media").mkdir()
        Path(ordner, "Media", "a.dat").write_bytes(b"y" * 3000)
        Path(ordner, "sce_sys", "param.json").write_text(json.dumps(param if param is not None else {
            "titleId": "PPSA19015", "contentId": CID, "contentVersion": "01.003.000",
            "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Arcade"}}}), encoding="utf-8-sig")
        if icon:
            Path(ordner, "sce_sys", "icon0.png").write_bytes(b"png")
        return ordner

    def test_ein_spielordner_wird_erkannt(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            self.assertFalse(wz.ordner_ist_spiel(t))
            ordner = self._spiel(t)
            self.assertTrue(wz.ordner_ist_spiel(ordner))

    def test_ordner_lesen_gibt_titel_kennungen_groesse_und_cover_als_kopie(self) -> None:
        meldungen: list[str] = []
        with tempfile.TemporaryDirectory() as t:
            ordner = self._spiel(t)
            info = wz.ordner_lesen(ordner, t, melden=meldungen.append)
            self.assertTrue(info.ist_ordner)
            self.assertEqual(("Arcade", "PPSA19015", CID), (info.titel, info.title_id, info.content_id))
            self.assertEqual(1000 + 3000 + len(Path(ordner, "sce_sys", "param.json").read_bytes()) + 3, info.groesse)
            self.assertEqual("01.003.000", info.version)
            self.assertTrue(os.path.isfile(info.icon))
            self.assertNotEqual(os.path.dirname(info.icon), os.path.join(ordner, "sce_sys"), "das Cover ist eine Kopie")
            self.assertTrue(info.arbeit and info.arbeit != ordner and os.path.isdir(info.arbeit))
            self.assertEqual(info.arbeit, os.path.dirname(info.icon))
            self.assertTrue(any("Dateien" in m for m in meldungen), "die Groessenbestimmung meldet sich")

    def test_ohne_cover_gibt_es_keinen_arbeitsordner(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            info = wz.ordner_lesen(self._spiel(t, icon=False), t)
            self.assertEqual(("", ""), (info.icon, info.arbeit))

    def test_ohne_lesbare_param_json_gibt_es_eine_meldung(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            ordner = self._spiel(t)
            Path(ordner, "sce_sys", "param.json").write_text("{kaputt", encoding="utf-8")
            with self.assertRaises(wz.Fehler):
                wz.ordner_lesen(ordner, t)
            Path(ordner, "sce_sys", "param.json").write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(wz.Fehler):
                wz.ordner_lesen(ordner, t)


class BauenTests(unittest.TestCase):

    def test_der_fortschritt_der_phasen(self) -> None:
        faelle = (
            ("[stage] copy 50% (0.6 of 1.2 GB)", 5),
            ("[inner]   read 3/178 ( 10%): /a/b (4 bytes)", 11),
            ("[inner]   data  37% (48/178): /Media/x.bundle -> 21,170,156 bytes (Kraken, ratio 92.5 %)", 45),
            ("[inner]   data 100% (178/178): /sce_module/libc.prx.esbak -> 1 bytes (stored, ratio 100.0 %)", 80),
            ("[stage 3/6] Writing and hashing outer-PFS data (20 worker(s)): 40% (1 MiB / 2 MiB; 3 MiB/s).", 85),
            ("[finalize] NAPS plaintext integrity tables (SHA3/ihsh/rhsh): 50% (1 / 2 blocks).", 96),
        )
        for zeile, soll in faelle:
            with self.subTest(zeile=zeile[:40]):
                self.assertEqual(soll, wz.bau_fortschritt(zeile)[0])
        self.assertEqual("/Media/x.bundle", wz.bau_fortschritt(faelle[2][0])[1])
        for ohne in ("Done (FIH).", "Building the PS5 package...", "[inner] Inode and AFID planning: 55% (192/192)"):
            self.assertIsNone(wz.bau_fortschritt(ohne))

    def test_der_fortschritt_steigt_ueber_die_phasen(self) -> None:
        reihe = [wz.bau_fortschritt(z)[0] for z in (
            "[stage] copy 100% (1 of 1 GB)", "[inner]   read 9/9 (100%): /x (1 bytes)",
            "[inner]   data  50% (1/2): /x -> 1 bytes (Kraken, ratio 50 %)", "[inner]   data 100% (2/2): /y -> 1 bytes (Kraken, ratio 50 %)",
            "[stage 4/6] Writing and hashing outer-PFS data (4 worker(s)): 100% (1 MiB / 1 MiB; 1 MiB/s).",
            "[finalize] x: 100% (1 / 1 blocks).")]
        self.assertEqual(sorted(reihe), reihe)
        self.assertLess(reihe[-1], 100)

    def test_content_und_title_id(self) -> None:
        for gut in (CID, "EP6665-PPSA16709_00-AOH0000000000000"):
            self.assertTrue(wz.CONTENT_ID.match(gut))
        for schlecht in ("", "kaputt", CID + "0", CID.lower(), "UP8016-PPSA19015-0489895718491618"):
            self.assertFalse(wz.CONTENT_ID.match(schlecht), schlecht)
        self.assertTrue(wz.TITLE_ID.match("PPSA19015"))
        self.assertFalse(wz.TITLE_ID.match("ppsa19015"))
        self.assertFalse(wz.TITLE_ID.match("CUSA1234"))

    def test_bauen_ruft_das_werkzeug_mit_den_belegten_voreinstellungen_auf(self) -> None:
        gesehen = {}

        def laufen(werkzeug, argumente, zeile=None, **_kw):
            gesehen["argumente"] = list(argumente)
            for z in ("[stage] copy 10% (1 of 9 GB)", "[inner]   data  50% (1/2): /Media/a -> 1 bytes (Kraken, ratio 50 %)",
                      "Build finished in 00:00:25; output 5 bytes"):
                zeile(z)
            return 0, "OK \u2014 wrote E:\\Ziel mit Leerzeichen\\UP8016-PPSA19015_00-0489895718491618-A0103-V0103.pkg (567,330,298 B)\n"

        fort, zeilen = [], []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "laufen", side_effect=laufen):
            pfad = wz.bauen("werkzeug", "Quelle", os.path.join(t, "ziel"), content_id=CID, title_id="PPSA19015", titel="Arcade",
                            version="01.003.000", temp=os.path.join(t, "tmp"), zeile=zeilen.append,
                            fortschritt=lambda p, d: fort.append((p, d)))
            self.assertTrue(os.path.isdir(os.path.join(t, "ziel")))
        a = gesehen["argumente"]
        self.assertEqual(["build", "Quelle"], a[:2])
        wert = lambda name: a[a.index(name) + 1]   # noqa: E731
        self.assertEqual((CID, "PPSA19015", "01.003.000", "Arcade"),
                         (wert("--content-id"), wert("--title-id"), wert("--version"), wert("--title")))
        self.assertEqual(("kraken", "builtin", "0"), (wert("--mode"), wert("--kraken-backend"), wert("--level")))
        self.assertEqual(os.path.join(t, "tmp"), wert("--temp"))
        for aus in ("--no-fake-sign", "--no-ampr-index", "--parallelism"):
            self.assertNotIn(aus, a)
        self.assertEqual("E:\\Ziel mit Leerzeichen\\UP8016-PPSA19015_00-0489895718491618-A0103-V0103.pkg", pfad)
        self.assertEqual([(1, "copy 10% (1 of 9 GB)"), (52, "/Media/a")], fort)
        self.assertEqual(["Build finished in 00:00:25; output 5 bytes"], zeilen)

    def test_die_wahlmoeglichkeiten_kommen_als_schalter_an(self) -> None:
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "laufen", return_value=(0, "OK - wrote x.pkg (1 B)")) as lauf:
            wz.bauen("w", "q", os.path.join(t, "z"), content_id=CID, title_id="PPSA19015", stufe=-3, kerne=4,
                     fake_signieren=False, ampr_index=False)
        a = lauf.call_args.args[1]
        self.assertEqual("-3", a[a.index("--level") + 1])
        self.assertEqual("4", a[a.index("--parallelism") + 1])
        self.assertIn("--no-fake-sign", a)
        self.assertIn("--no-ampr-index", a)
        self.assertNotIn("--title", a)
        self.assertNotIn("--temp", a)

    def test_ungueltige_kennungen_werden_vorher_abgelehnt(self) -> None:
        with mock.patch.object(wz, "laufen") as lauf:
            with self.assertRaises(wz.Fehler):
                wz.bauen("w", "q", "z", content_id="kaputt", title_id="PPSA19015")
            with self.assertRaises(wz.Fehler):
                wz.bauen("w", "q", "z", content_id=CID, title_id="kaputt")
        lauf.assert_not_called()

    def test_fehler_und_abbruch_beim_bauen(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            for rueckgabe, text in (((1, "[error] IOException: voll\n"), "[error] IOException: voll"),
                                    ((0, "kein ok am ende\n"), "kein ok am ende")):
                with self.subTest(text=text), mock.patch.object(wz, "laufen", return_value=rueckgabe):
                    with self.assertRaises(wz.Fehler) as ctx:
                        wz.bauen("w", "q", os.path.join(t, "z"), content_id=CID, title_id="PPSA19015")
                    self.assertEqual(text, str(ctx.exception))
            with mock.patch.object(wz, "laufen", return_value=(-1, "")):
                with self.assertRaises(wz.Fehler) as ctx:
                    wz.bauen("w", "q", os.path.join(t, "z"), content_id=CID, title_id="PPSA19015")
                self.assertEqual("abgebrochen", str(ctx.exception))

    def test_ohne_pfad_in_der_schlusszeile_bleibt_die_zeile(self) -> None:
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "laufen", return_value=(0, "OK - fertig\n")):
            self.assertEqual("OK - fertig", wz.bauen("w", "q", os.path.join(t, "z"), content_id=CID, title_id="PPSA19015"))


class FensterHilfenTests(unittest.TestCase):

    def test_firmware_text(self) -> None:
        self.assertEqual("9.00", fz.firmware_text("0x0900000000000000"))
        self.assertEqual("7.02", fz.firmware_text("0x0702000000000000"))
        self.assertEqual("10.20", fz.firmware_text("0x1020000000000000"))
        self.assertEqual("", fz.firmware_text(""))
        self.assertEqual("", fz.firmware_text(0))
        self.assertEqual("abc", fz.firmware_text("abc"))

    def test_sauberer_name_und_anzeigename(self) -> None:
        self.assertEqual("A b c d", fz.sauberer_name('A:b/c?d'))
        self.assertEqual("Asterix & Obelix Heroes", fz.sauberer_name("Asterix & Obelix Heroes."))
        self.assertEqual("Asterix & Obelix Heroes [PPSA16709]", fz.anzeigename(_info(titel="Asterix & Obelix: Heroes")))
        self.assertEqual("Spiel [PPSA16709]", fz.anzeigename(_info(titel="")))
        self.assertEqual("Spiel PPSA16709", fz.anzeigename(_info(titel="Spiel PPSA16709")))

    def test_die_suche(self) -> None:
        info = _info()
        for suche, soll in (("", True), ("asterix", True), ("ASTERIX heroes", True), ("asterix zelda", False),
                            ("-zelda", True), ("-asterix", False), ("titel:obelix", True), ("titel:ppsa", False),
                            ("id:ppsa16709", True), ("id:ep6665", True), ("id:ppsa1", True), ("id:ppsa2", False),
                            ("größe:>1GB", True), ("groesse:>2GB", False), ("größe:<2GB", True),
                            ("größe:>=1,5GB", True), ("size:<500MB", False), ("asterix -zelda größe:>1GB", True),
                            ("-", True)):
            with self.subTest(suche=suche):
                self.assertEqual(soll, fz.suche_passt(info, suche))

    def test_die_uebersicht_hat_alle_zeilen(self) -> None:
        t = lambda k, **kw: k   # noqa: E731 - die Schluessel genuegen
        param = {"contentVersion": "01.000.000", "masterVersion": "01.00", "conceptId": "10008371",
                 "requiredSystemSoftwareVersion": "0x0900000000000000", "sdkVersion": "0x0700000000000000",
                 "applicationCategoryType": 0, "applicationDrmType": "upgradable", "contentBadgeType": 1,
                 "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "X"}}}
        zeilen = dict(fz.uebersicht(_info(param=param), t, lambda n: "%d B" % n))
        self.assertEqual(14, len(zeilen))
        self.assertEqual("9.00", zeilen["ps5pkg.prop_firmware"])
        self.assertEqual("7.00", zeilen["ps5pkg.prop_sdk"])
        self.assertEqual("Spiel", zeilen["ps5pkg.prop_category"])
        self.assertEqual("en-US", zeilen["ps5pkg.prop_language"])
        self.assertEqual("10008371", zeilen["ps5pkg.prop_concept"])
        leer = dict(fz.uebersicht(_info(param={}, titel=""), t, lambda n: "x"))
        self.assertEqual("-", leer["ps5pkg.prop_concept"])



class AnzeigeTests(unittest.TestCase):
    """14.10.2026 (LEGO Batman, 31,8 GB): Die Anzeige stand minutenlang auf 0 %, das Protokoll war "Bahnhof"
    ("[info] extract-inner (members) E:\\...pkg -> ...LEGO\ufffd BatmanT ...")."""

    def test_der_fortschritt_laeuft_nur_vorwaerts_und_nennt_menge_und_dateien(self) -> None:
        """Zweiter Befund 14.10.2026: Die Anzeige sprang vor und zurueck - die Groesse der gerade geschriebenen Datei
        meldet Windows schon vor dem Schreiben voll. Der Wert ist jetzt der des Werkzeugs, nur vorwaerts."""
        gross = 100 * 1024 * 1024
        eintraege = [{"path": "fertig.dat", "type": "file", "size": gross},
                     {"path": "laeuft.dat", "type": "file", "size": gross}]

        def laufen(werkzeug, argumente, zeile=None, **_kw):
            ziel = argumente[2]
            with open(os.path.join(ziel, "fertig.dat"), "wb") as d:
                d.truncate(gross)
            with open(os.path.join(ziel, "laeuft.dat"), "wb") as d:
                d.truncate(gross)                          # vorab volle Groesse wie unter Windows
            for z in ("[####] 50% extract (laeuft.dat)", "[####] 49% extract (laeuft.dat)",
                      "[####] 60% extract (laeuft.dat)"):
                zeile(z)
            time.sleep(0.3)
            return 0, "OK - extracted 2 file(s) to X\n"

        meldungen: list = []
        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "_HERZSCHLAG", 0.1), \
                mock.patch.object(wz, "baum", return_value=eintraege), mock.patch.object(wz, "laufen", side_effect=laufen):
            os.makedirs(os.path.join(t, "ziel"))
            wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), arbeitsordner=t,
                           fortschritt=lambda pz, d: meldungen.append((pz, d)))
        werte = [pz for pz, _d in meldungen]
        self.assertEqual(werte, sorted(werte), "nie zurueck: %s" % werte)
        self.assertEqual(60, werte[-1], "kein erfundener Wert ueber dem des Werkzeugs")
        letzte = meldungen[-1][1]
        self.assertIn("120 MB / 200 MB", letzte, "die Menge folgt dem Prozentwert")
        self.assertIn("1/2", letzte, "die laufende Datei zaehlt nicht als fertig, obwohl sie schon voll gross ist")

    def test_die_ausgabe_wird_auch_in_der_oem_codeseite_gelesen(self) -> None:
        self.assertEqual("LEGO\u00ae", wz._dekodieren("LEGO\u00ae".encode("utf-8")))
        if sys.platform == "win32":
            import ctypes
            codeseite = "cp%d" % ctypes.windll.kernel32.GetOEMCP()
            self.assertEqual("LEGO\u00ae", wz._dekodieren("LEGO\u00ae".encode(codeseite)))

    def test_menge_kurz(self) -> None:
        self.assertEqual("31.8 GB", wz.menge_kurz(int(31.8 * 1024 ** 3)))
        self.assertEqual("420 MB", wz.menge_kurz(420 * 1024 ** 2))

    def test_die_werkzeugzeilen_stehen_in_worten_im_protokoll(self) -> None:
        texte = {"ps5pkg.log_extracting_files": "Entpacke {anzahl} Dateien", "ps5pkg.log_contents_read": "{anzahl} in {sekunden}",
                 "ps5pkg.log_extracted": "fertig {anzahl}", "ps5pkg.log_reading_contents": "lese",
                 "ps5pkg.log_extracting_all": "alles", "ps5pkg.log_whole_extract": "am Stueck"}

        class Attrappe:
            _LESBAR = fz.PS5PkgFenster._LESBAR if hasattr(fz, "PS5PkgFenster") else None

            def t(self, schluessel, **werte):
                return texte[schluessel].format(**werte)

        klasse = next(k for k in vars(fz).values() if isinstance(k, type) and hasattr(k, "_LESBAR"))
        a = Attrappe()
        a._LESBAR = klasse._LESBAR
        lesbar = lambda z: klasse._lesbar(a, z)   # noqa: E731
        self.assertEqual("Entpacke 215 Dateien", lesbar(
            "[info] extract-inner (members)  E:\\x.pkg -> C:\\t\\LEGO\ufffd BatmanT  (215 member(s))"))
        self.assertEqual("215 in 3", lesbar("[info] Paketinhalt gelesen: 215 Eintraege in 3 s"))
        self.assertEqual("fertig 215", lesbar("OK \u2014 extracted 215 file(s) and 3 folder(s) to C:\\t"))
        self.assertEqual("lese", lesbar("[info] Paketinhalt wird gelesen - bei einem grossen Paket ..."))
        self.assertEqual("etwas anderes", lesbar("[info] etwas anderes"), "nur die Kennung faellt weg")
        self.assertEqual("[warn] bleibt", lesbar("[warn] bleibt"))


if __name__ == "__main__":
    unittest.main()
