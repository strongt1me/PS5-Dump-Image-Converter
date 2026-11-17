# -*- coding: utf-8 -*-
"""Die Huelle um die Befehlszeile von Dump Forge (``utils/forge_cli.py``, seit 16.11.2026).

Zwei Arten von Pruefung:

* **Mit einer Attrappe** (ein Python-Skript, das Forges Ausgabe nachmacht: je Ereignis eine JSON-Zeile auf stdout, die
  Kurzfassung auf stderr): Fortschritt, gekuerzte Protokollzeilen, Fehlerwege, Abbruch.
* **Mit der echten, mitgelieferten Befehlszeile** (``Dump-Forge-CLI/<Plattform>/``), wo es sie fuer diese Plattform gibt:
  ein kleines, selbst gebautes Spiel (eigene ``param.json``, Zufallsbytes als ``eboot.bin``) wird zum Paket gebaut, und
  aus ihm entstehen alle vier Abbildformate, die dann ebenfalls zum Paket gebaut werden.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("forgecli")

from ps5_validator.utils import forge_cli as fc              # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz       # noqa: E402

#: Ein PNG mit einem Pixel (fuer das Cover in Forges ``inspect``).
_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

_ATTRAPPE = textwrap.dedent('''
    import json, os, sys, time
    modus = os.environ.get("FAKE_MODUS", "ok")
    args = sys.argv[1:]
    def ev(**k):
        print(json.dumps(k), flush=True)
    if args[0] == "inspect":
        if modus == "inspect_fehler":
            print("ps5-dump-forge: kaputte Quelle", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(json.loads(os.environ["FAKE_INSPECT"])))
        sys.exit(0)
    ziel = args[args.index("-o") + 1]
    ev(kind="stages", job=1, stages=["scan", "preflight", "write", "verify", "finalize"])
    ev(kind="progress", job=1, stage="scan", done=0, total=0)
    for i in range(8):
        ev(kind="log", job=1, line="fpkg: leaving out Media/x%d.esbak (build-project file)" % i)
    ev(kind="log", job=1, line="package: content id UP0000-PPSA00001_00-AAAA, about 1 MiB")
    ev(kind="progress", job=1, stage="write", done=50, total=100)
    if modus == "lang":
        time.sleep(60)
    if modus == "ok":
        open(ziel, "wb").write(b"\\x7fFIH" + b"x" * 60)
        ev(kind="progress", job=1, stage="finalize", done=100, total=100)
        ev(kind="done", job=1, result={"Ok": {"output": ziel, "bytes": 64, "files": 3,
            "checks": ["fpkg verify: a", "fpkg verify: b", "check: c"],
            "verify": {"mode": os.environ.get("FAKE_VERIFY", "fast"), "checked_bytes": 4, "total_bytes": 8,
                       "samples": 2, "seed": 7}}})
        print("ps5-dump-forge: wrote " + ziel, file=sys.stderr)
        sys.exit(0)
    if modus == "err":
        ev(kind="done", job=1, result={"Err": "the output already exists"})
        print("ps5-dump-forge: failed: the output already exists", file=sys.stderr)
        sys.exit(1)
    if modus == "absturz":
        print("ps5-dump-forge: failed: boom", file=sys.stderr)
        sys.exit(1)
    if modus == "ohne_ergebnis":
        sys.exit(0)
    if modus == "ohne_datei":
        ev(kind="done", job=1, result={"Ok": {"output": ziel + ".gibtsnicht", "bytes": 1, "files": 1,
                                              "checks": [], "verify": {"mode": "fast"}}})
        sys.exit(0)
''')


class _MitAttrappe(unittest.TestCase):
    """Legt die Attrappe an und ruft ``forge_cli`` mit ``werkzeug=python``, ``vorspann=(skript,)`` auf."""

    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.ordner = Path(self._temp.name)
        self.skript = self.ordner / "forge_attrappe.py"
        self.skript.write_text(_ATTRAPPE, encoding="utf-8")
        self.ziel = str(self.ordner / "aus" / "Spiel [PPSA00001].pkg")

    def _bauen(self, modus: str = "ok", **kw):
        zeilen: list[str] = []
        fortschritt: list[tuple[int, str]] = []
        with mock.patch.dict(os.environ, {"FAKE_MODUS": modus}):
            erg = fc.bauen(sys.executable, str(self.ordner / "quelle"), self.ziel, zeile=zeilen.append,
                           fortschritt=lambda p, s: fortschritt.append((p, s)), vorspann=(str(self.skript),), **kw)
        return erg, zeilen, fortschritt


class BauenMitAttrappeTests(_MitAttrappe):
    def test_ein_erfolgreicher_bau_liefert_ergebnis_fortschritt_und_zeilen(self) -> None:
        erg, zeilen, fortschritt = self._bauen()
        self.assertTrue(os.path.isfile(erg.pfad))
        self.assertEqual((64, 3), (erg.bytes, erg.dateien))
        self.assertEqual(3, len(erg.pruefungen))
        self.assertEqual(("fast", 4, 8, 2), (erg.modus, erg.geprueft_bytes, erg.gesamt_bytes, erg.proben))
        self.assertIn((0, "scan"), fortschritt)
        self.assertIn((50, "write"), fortschritt)
        # 100 % meldet das Fenster selbst nach dem Ablegen; aus dem Strom kommt hoechstens 99
        self.assertTrue(all(0 <= p <= 99 for p, _s in fortschritt))
        self.assertEqual([p for p, _s in fortschritt], sorted(p for p, _s in fortschritt))
        self.assertTrue(os.path.isdir(os.path.dirname(self.ziel)), "der Zielordner wird angelegt")

    def test_gleichartige_protokollzeilen_werden_gekuerzt_die_uebrigen_kommen_durch(self) -> None:
        _erg, zeilen, _f = self._bauen()
        weg = [z for z in zeilen if z.startswith("fpkg: leaving out ")]
        self.assertEqual(5, len(weg), "nur die ersten fuenf je Gruppe")
        self.assertIn("... und 3 weitere Zeilen dieser Art", zeilen)
        self.assertIn("package: content id UP0000-PPSA00001_00-AAAA, about 1 MiB", zeilen)
        self.assertFalse([z for z in zeilen if z.startswith("{")], "kein JSON im Protokoll")

    def test_der_modus_full_kommt_aus_dem_ergebnis(self) -> None:
        with mock.patch.dict(os.environ, {"FAKE_VERIFY": "full"}):
            erg, _z, _f = self._bauen()
        self.assertEqual("full", erg.modus)

    def test_ein_fehler_forges_kommt_mit_seinem_text(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            self._bauen("err")
        self.assertEqual("the output already exists", str(ctx.exception))

    def test_ein_absturz_ohne_ereignis_nimmt_den_text_aus_stderr(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            self._bauen("absturz")
        self.assertEqual("boom", str(ctx.exception))

    def test_ein_ende_ohne_ergebnis_ist_ein_fehler(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            self._bauen("ohne_ergebnis")
        self.assertIn("kein Ergebnis", str(ctx.exception))

    def test_meldet_forge_erfolg_aber_die_datei_fehlt_ist_das_ein_fehler(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            self._bauen("ohne_datei")
        self.assertIn("fehlt", str(ctx.exception))

    def test_der_abbruch_beendet_den_lauf_schnell_und_meldet_abgebrochen(self) -> None:
        start = time.monotonic()
        with self.assertRaises(wz.Fehler) as ctx:
            self._bauen("lang", abbruch=lambda: time.monotonic() - start > 1.0)
        self.assertEqual("abgebrochen", str(ctx.exception))
        self.assertLess(time.monotonic() - start, 30, "der Prozess ist beendet worden, nicht abgewartet")

    def test_ohne_abbruch_wird_ein_schon_verlangter_abbruch_vor_dem_start_erkannt(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            self._bauen("ok", abbruch=lambda: True)
        self.assertEqual("abgebrochen", str(ctx.exception))
        self.assertFalse(os.path.exists(self.ziel))


class ArgumenteTests(unittest.TestCase):
    def test_die_vorgabe_ist_forges_schnelle_stufe_ohne_weitere_schalter(self) -> None:
        self.assertEqual(["convert", "Q", "--to", "pkg", "-o", "Z.pkg", "--kraken", "fast"],
                         fc.convert_argumente("Q", "Z.pkg"))

    def test_alle_schalter_kommen_an(self) -> None:
        a = fc.convert_argumente("Q", "Z.pkg", kraken="smallest", voll_pruefen=True, backport_entfernen=True, kerne=6)
        self.assertEqual(["--kraken", "smallest"], a[a.index("--kraken"):a.index("--kraken") + 2])
        self.assertEqual(["--threads", "6"], a[a.index("--threads"):a.index("--threads") + 2])
        self.assertIn("--full-verify", a)
        self.assertIn("--remove-backport", a)

    def test_null_kerne_heisst_alle_und_laesst_den_schalter_weg(self) -> None:
        self.assertNotIn("--threads", fc.convert_argumente("Q", "Z.pkg", kerne=0))

    def test_eine_unbekannte_stufe_wird_abgelehnt_statt_durchgereicht(self) -> None:
        with self.assertRaises(wz.Fehler):
            fc.convert_argumente("Q", "Z.pkg", kraken="langsam")
        self.assertEqual(("fast", "balanced", "smallest", "stored"), fc.KRAKEN_STUFEN)

    def test_der_pfad_steht_als_ein_argument_auch_mit_leerzeichen_und_sonderzeichen(self) -> None:
        a = fc.convert_argumente("C:/Spiele/Ein Spiel [PPSA1]/x.exfat", "D:/Aus Ordner/Ä ö.pkg")
        self.assertIn("C:/Spiele/Ein Spiel [PPSA1]/x.exfat", a)
        self.assertIn("D:/Aus Ordner/Ä ö.pkg", a)


class DateinameTests(unittest.TestCase):
    def test_titel_und_kennung(self) -> None:
        self.assertEqual("Crazy Chicken Shooter [PPSA03117].pkg", fc.dateiname_fuer("Crazy Chicken Shooter", "PPSA03117"))

    def test_der_name_ohne_endung_bleibt_in_63_bytes_und_die_kennung_bleibt_ganz(self) -> None:
        lang = "Ein sehr langer Spieltitel " * 8
        name = fc.dateiname_fuer(lang, "PPSA03117")
        stamm = name[:-4]
        self.assertTrue(name.endswith(" [PPSA03117].pkg"))
        self.assertLessEqual(len(stamm.encode("utf-8")), fc.STAMM_GRENZE)
        self.assertGreaterEqual(len(stamm.encode("utf-8")), fc.STAMM_GRENZE - 3, "es wird nicht mehr als noetig gekuerzt")

    def test_mehrbytezeichen_werden_nicht_mitten_im_zeichen_zerschnitten(self) -> None:
        name = fc.dateiname_fuer("日本語のとても長いタイトル" * 6, "PPSA00001")
        stamm = name[:-4]
        self.assertLessEqual(len(stamm.encode("utf-8")), fc.STAMM_GRENZE)
        stamm.encode("utf-8").decode("utf-8")        # wirft bei einem zerschnittenen Zeichen

    def test_ohne_titel_oder_ohne_kennung_oder_ohne_beides(self) -> None:
        self.assertEqual("[PPSA00001].pkg", fc.dateiname_fuer("", "PPSA00001"))
        self.assertEqual("Nur Titel.pkg", fc.dateiname_fuer("Nur Titel", ""))
        self.assertEqual("Paket.pkg", fc.dateiname_fuer("", ""))

    def test_leerzeichen_und_punkte_am_ende_des_gekuerzten_titels_fallen_weg(self) -> None:
        name = fc.dateiname_fuer("a" * 50 + " .", "PPSA00001")
        self.assertNotIn(" . [", name)
        self.assertNotIn("  [", name)


class ErkennungTests(unittest.TestCase):
    def test_abbildarten_nach_der_endung_gleich_gross_oder_klein(self) -> None:
        for name, art in (("a.ffpkg", "ffpkg"), ("a.FFPFSC", "ffpfsc"), ("a.ffpfs", "ffpfs"), ("a.ExFAT", "exfat")):
            with self.subTest(name=name):
                self.assertEqual(art, fc.abbild_art(name))
        for name in ("a.pkg", "a.zip", "a", "a.exfat.txt"):
            with self.subTest(name=name):
                self.assertEqual("", fc.abbild_art(name))

    def test_ist_abbild_braucht_eine_vorhandene_datei(self) -> None:
        with tempfile.TemporaryDirectory() as t:
            vorhanden = os.path.join(t, "a.exfat")
            Path(vorhanden).write_bytes(b"x")
            self.assertTrue(fc.ist_abbild(vorhanden))
            self.assertFalse(fc.ist_abbild(os.path.join(t, "fehlt.exfat")))

    def test_werkzeug_suchen_findet_den_mitgelieferten_ordner_und_sonst_nichts(self) -> None:
        self.assertEqual("", fc.werkzeug_suchen([]))
        self.assertEqual("", fc.werkzeug_suchen(None))
        unter = fc.unterordner()
        if not unter:
            self.skipTest("fuer diese Plattform liefert das Programm keine Befehlszeile mit")
        with tempfile.TemporaryDirectory() as wurzel:
            ordner = Path(wurzel, fc.ORDNER, unter)
            ordner.mkdir(parents=True)
            (ordner / fc.dateiname()).write_bytes(b"x")
            self.assertEqual(str(ordner / fc.dateiname()), fc.werkzeug_suchen([wurzel]))

    def test_die_plattformordner_heissen_wie_im_projekt(self) -> None:
        for maschine, soll in (("AMD64", "win-x64"), ("ARM64", "win-arm64"), ("arm64", "win-arm64")):
            with self.subTest(windows=maschine), mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.object(fc.platform, "machine", return_value=maschine):
                self.assertEqual((soll, "ps5-dump-forge.exe"), (fc.unterordner(), fc.dateiname()))
        for maschine in ("arm64", "x86_64"):
            with self.subTest(mac=maschine), mock.patch.object(sys, "platform", "darwin"), \
                    mock.patch.object(fc.platform, "machine", return_value=maschine):
                self.assertEqual("macos-universal", fc.unterordner(), "Apple Silicon und Intel gleichermassen")
        for maschine, soll in (("x86_64", "linux-x64"), ("AMD64", "linux-x64"), ("aarch64", "linux-arm64"), ("arm64", "linux-arm64"),
                               ("riscv64", ""), ("armv7l", "")):
            with self.subTest(linux=maschine), mock.patch.object(sys, "platform", "linux"), \
                    mock.patch.object(fc.platform, "machine", return_value=maschine):
                self.assertEqual(soll, fc.unterordner())

    def test_windows_arm64_faellt_auf_die_x64_fassung_zurueck_wenn_die_native_fehlt(self) -> None:
        with tempfile.TemporaryDirectory() as wurzel, mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(fc.platform, "machine", return_value="ARM64"):
            x64 = Path(wurzel, fc.ORDNER, "win-x64")
            x64.mkdir(parents=True)
            (x64 / "ps5-dump-forge.exe").write_bytes(b"x")
            self.assertEqual(str(x64 / "ps5-dump-forge.exe"), fc.werkzeug_suchen([wurzel]), "nur x64 da: die Emulation fuehrt sie aus")
            arm = Path(wurzel, fc.ORDNER, "win-arm64")
            arm.mkdir()
            (arm / "ps5-dump-forge.exe").write_bytes(b"x")
            self.assertEqual(str(arm / "ps5-dump-forge.exe"), fc.werkzeug_suchen([wurzel]), "die native geht vor")
        with tempfile.TemporaryDirectory() as wurzel, mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(fc.platform, "machine", return_value="AMD64"):
            arm = Path(wurzel, fc.ORDNER, "win-arm64")
            arm.mkdir(parents=True)
            (arm / "ps5-dump-forge.exe").write_bytes(b"x")
            self.assertEqual("", fc.werkzeug_suchen([wurzel]), "auf x64 gibt es keinen Ausweg auf die arm64-Datei")


class MitgelieferteBefehlszeilenTests(unittest.TestCase):
    """``Dump-Forge-CLI/`` haelt je Plattform eine unveraenderte Datei der Freigabe: Herkunft laut README, Pruefsumme, Dateikopf."""

    ORDNER = Path(__file__).resolve().parent.parent / "Dump-Forge-CLI"
    #: Ordner -> (Dateiname, Kennzeichen am Dateianfang: ELF e_machine, PE Machine, Mach-O universal)
    ERWARTET = {"win-x64": ("ps5-dump-forge.exe", ("pe", 0x8664)), "win-arm64": ("ps5-dump-forge.exe", ("pe", 0xAA64)),
                "linux-x64": ("ps5-dump-forge", ("elf", 0x3E)), "linux-arm64": ("ps5-dump-forge", ("elf", 0xB7)),
                "macos-universal": ("ps5-dump-forge", ("fat", 0))}

    def _tabelle(self) -> dict:
        text = (self.ORDNER / "README.md").read_text(encoding="utf-8")
        return {m.group(1): (m.group(2), m.group(3)) for m in re.finditer(
            r"\|\s*`([\w-]+)/`\s*\|\s*`(ps5-dump-forge(?:\.exe)?)`[^|]*\|\s*`([0-9a-f]{64})`", text)}

    def test_die_readme_nennt_jede_mitgelieferte_datei_mit_ihrer_pruefsumme(self) -> None:
        tabelle = self._tabelle()
        self.assertEqual(set(self.ERWARTET), set(tabelle), "ein Ordner fehlt in der Tabelle oder die Tabelle kennt einen zu viel")
        for ordner, (name, summe) in tabelle.items():
            with self.subTest(ordner=ordner):
                self.assertEqual(self.ERWARTET[ordner][0], name)
                datei = self.ORDNER / ordner / name
                self.assertTrue(datei.is_file(), str(datei))
                self.assertEqual(summe, hashlib.sha256(datei.read_bytes()).hexdigest(), "die Datei ist nicht mehr die der Freigabe")

    def test_jede_datei_ist_fuer_ihre_plattform_gebaut(self) -> None:
        import struct
        for ordner, (name, (art, kennzahl)) in self.ERWARTET.items():
            with self.subTest(ordner=ordner):
                d = (self.ORDNER / ordner / name).read_bytes()
                if art == "elf":
                    self.assertEqual(b"\x7fELF", d[:4])
                    self.assertEqual(kennzahl, struct.unpack_from("<H", d, 18)[0], "ELF e_machine")
                elif art == "pe":
                    self.assertEqual(b"MZ", d[:2])
                    pe = struct.unpack_from("<I", d, 0x3C)[0]
                    self.assertEqual(b"PE\0\0", d[pe:pe + 4])
                    self.assertEqual(kennzahl, struct.unpack_from("<H", d, pe + 4)[0], "PE Machine")
                else:
                    self.assertEqual(b"\xca\xfe\xba\xbe", d[:4], "Mach-O universal")
                self.assertIn(b"0.5.6", d, "die Fassung der Freigabe steht in der Datei")

    def test_die_plattformordner_stimmen_mit_der_auswahl_des_programms_ueberein(self) -> None:
        gewaehlt = set()
        for sp, maschine in (("win32", "AMD64"), ("win32", "ARM64"), ("darwin", "arm64"), ("linux", "x86_64"), ("linux", "aarch64")):
            with mock.patch.object(sys, "platform", sp), mock.patch.object(fc.platform, "machine", return_value=maschine):
                gewaehlt.add(fc.unterordner())
        self.assertEqual(set(self.ERWARTET), gewaehlt, "jeder gelieferte Ordner wird auch gewaehlt und umgekehrt")


class LesenMitAttrappeTests(_MitAttrappe):
    def _lesen(self, inspect: dict, pfad: str = "", modus: str = "ok"):
        pfad = pfad or str(self.ordner / "Spiel.exfat")
        if pfad.endswith(".exfat"):
            Path(pfad).write_bytes(b"x" * 2048)
        with mock.patch.dict(os.environ, {"FAKE_MODUS": modus, "FAKE_INSPECT": json.dumps(inspect)}):
            return fc.lesen(sys.executable, pfad, str(self.ordner), vorspann=(str(self.skript),))

    def test_ein_abbild_wird_mit_titel_kennungen_cover_und_befunden_gelesen(self) -> None:
        info = self._lesen({"kind": "exfat", "title_id": "PPSA00001", "content_id": "UP0000-PPSA00001_00-AAAA",
                            "title_name": "Mein Spiel", "total_bytes": 999, "cover": "data:image/png;base64," + _PNG,
                            "param_json": {"contentVersion": "01.002.000"}, "findings": ["eine Warnung"],
                            "additional_content": False, "patch": False})
        self.assertTrue(info.ist_abbild)
        self.assertTrue(info.ist_quelle)
        self.assertFalse(info.ist_ordner)
        self.assertEqual(wz.TYP_ABBILD, info.typ)
        self.assertEqual("exfat", info.abbild)
        self.assertEqual(("PPSA00001", "UP0000-PPSA00001_00-AAAA", "Mein Spiel"), (info.title_id, info.content_id, info.titel))
        self.assertEqual(2048, info.groesse, "die Groesse der Datei, nicht der Inhalt")
        self.assertEqual(["eine Warnung"], info.befunde)
        self.assertEqual("01.002.000", info.version)
        self.assertTrue(os.path.isfile(info.icon))
        self.assertTrue(Path(info.icon).read_bytes().startswith(b"\x89PNG"))
        self.assertEqual(os.path.dirname(info.icon), info.arbeit)

    def test_der_titel_faellt_auf_die_param_json_zurueck(self) -> None:
        info = self._lesen({"kind": "ffpkg", "title_id": "PPSA00001", "param_json": {
            "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Aus der Param"}}}})
        self.assertEqual("Aus der Param", info.titel)

    def test_ein_ordner_bleibt_ein_ordner_und_nimmt_den_inhalt_als_groesse(self) -> None:
        ordner = self.ordner / "Spielordner"
        ordner.mkdir()
        info = self._lesen({"kind": "folder", "title_id": "PPSA00001", "total_bytes": 4242}, pfad=str(ordner))
        self.assertTrue(info.ist_ordner)
        self.assertFalse(info.ist_abbild)
        self.assertEqual(4242, info.groesse)

    def test_ein_ungueltiges_cover_wird_ignoriert(self) -> None:
        for cover in (None, "", "kein-data-url", "data:image/png;base64,@@@@", "data:image/png;base64,aGFsbG8="):
            with self.subTest(cover=cover):
                info = self._lesen({"kind": "exfat", "title_id": "PPSA00001", "cover": cover})
                self.assertEqual("", info.icon)

    def test_ein_fehler_beim_lesen_kommt_als_fehler_mit_text(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            self._lesen({}, modus="inspect_fehler")
        self.assertIn("kaputte Quelle", str(ctx.exception))

    def test_die_paketinfo_kennt_abbild_und_quelle_nur_fuer_ihre_typen(self) -> None:
        paket = wz.PaketInfo(pfad="a.pkg", typ="FullDebug")
        ordner = wz.PaketInfo(pfad="d", typ=wz.TYP_ORDNER)
        abbild = wz.PaketInfo(pfad="a.exfat", typ=wz.TYP_ABBILD)
        self.assertEqual((False, False, False), (paket.ist_ordner, paket.ist_abbild, paket.ist_quelle))
        self.assertEqual((True, False, True), (ordner.ist_ordner, ordner.ist_abbild, ordner.ist_quelle))
        self.assertEqual((False, True, True), (abbild.ist_ordner, abbild.ist_abbild, abbild.ist_quelle))


# ------------------------------------------------------------------------------------------ die echte Befehlszeile
_EXE = fc.werkzeug_suchen([str(PROJEKT)])
_PARAM = {"contentId": "EP9999-PPSA99999_00-TESTSPIEL0000001", "titleId": "PPSA99999", "contentVersion": "01.000.000",
          "masterVersion": "01.00", "applicationCategoryType": 0, "applicationDrmType": "standard",
          "conceptId": "100000", "requiredSystemSoftwareVersion": "0x0200000000000000",
          "sdkVersion": "0x0200000000000000",
          "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Testspiel"}}}


@unittest.skipUnless(_EXE, "fuer diese Plattform liegt keine Dump-Forge-Befehlszeile bei")
class EchteBefehlszeileTests(unittest.TestCase):
    """Das mitgelieferte ``ps5-dump-forge`` selbst - Ende zu Ende, mit einem kleinen eigenen Testspiel."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._temp.cleanup)
        cls.ordner = Path(cls._temp.name)
        spiel = cls.ordner / "Spiel"
        (spiel / "sce_sys").mkdir(parents=True)
        (spiel / "sce_sys" / "param.json").write_text(json.dumps(_PARAM), encoding="utf-8")
        (spiel / "eboot.bin").write_bytes(os.urandom(4096))
        (spiel / "daten.bin").write_bytes(b"abc" * 4000)
        cls.spiel = str(spiel)
        cls.aus = cls.ordner / "aus"
        cls.aus.mkdir()

    def _paket_pruefen(self, erg: "fc.ForgeBau") -> None:
        self.assertTrue(os.path.isfile(erg.pfad))
        self.assertTrue(erg.pfad.lower().endswith(".pkg"))
        with open(erg.pfad, "rb") as f:
            self.assertEqual(b"\x7fFIH", f.read(4), "ein fertiges PS5-Paket beginnt mit \\x7fFIH")
        self.assertGreater(len(erg.pruefungen), 10, "Forge prueft Struktur und Digests des Pakets")
        self.assertTrue(any("fpkg verify" in z for z in erg.pruefungen))
        self.assertEqual("fast", erg.modus)
        self.assertEqual(4, erg.dateien, "param.json, eboot.bin, Daten und die erzeugten Metadaten")

    def test_ein_spielordner_wird_zum_paket(self) -> None:
        stufen: list[str] = []
        erg = fc.bauen(_EXE, self.spiel, str(self.aus / "aus_ordner.pkg"), fortschritt=lambda p, s: stufen.append(s))
        self._paket_pruefen(erg)
        for stufe in ("scan", "preflight", "compress", "write", "verify", "finalize"):
            self.assertIn(stufe, stufen)

    def test_jedes_abbildformat_wird_gelesen_und_zum_paket(self) -> None:
        for art in ("ffpkg", "ffpfsc", "ffpfs", "exfat"):
            with self.subTest(abbild=art):
                bild = str(self.ordner / ("Testspiel." + art))
                rc = subprocess.run([_EXE, "convert", self.spiel, "--to", art, "-o", bild], capture_output=True).returncode
                self.assertEqual(0, rc, "Forge baut das Abbild %s selbst" % art)
                info = fc.lesen(_EXE, bild, str(self.ordner))
                self.addCleanup(lambda i=info: i.arbeit and shutil.rmtree(i.arbeit, ignore_errors=True))
                self.assertTrue(info.ist_abbild)
                self.assertEqual(art, info.abbild)
                self.assertEqual(("PPSA99999", "EP9999-PPSA99999_00-TESTSPIEL0000001", "Testspiel"),
                                 (info.title_id, info.content_id, info.titel))
                erg = fc.bauen(_EXE, bild, str(self.aus / ("aus_%s.pkg" % art)))
                self._paket_pruefen(erg)

    def test_die_schnelle_und_die_vollstaendige_pruefung_unterscheiden_sich_im_modus(self) -> None:
        erg = fc.bauen(_EXE, self.spiel, str(self.aus / "voll.pkg"), voll_pruefen=True, kraken="stored")
        self.assertEqual("full", erg.modus)
        self.assertEqual(erg.gesamt_bytes, erg.geprueft_bytes, "jedes Byte")

    def test_ein_vorhandenes_ziel_wird_nicht_ersetzt_und_forges_text_kommt_an(self) -> None:
        ziel = str(self.aus / "doppelt.pkg")
        fc.bauen(_EXE, self.spiel, ziel)
        with self.assertRaises(wz.Fehler):
            fc.bauen(_EXE, self.spiel, ziel)
        self.assertEqual(0, len([n for n in os.listdir(self.aus) if n.endswith(".part") or ".part" in n]),
                         "Forge raeumt seine .part weg")

    def test_eine_fehlende_quelle_gibt_forges_meldung(self) -> None:
        with self.assertRaises(wz.Fehler) as ctx:
            fc.bauen(_EXE, str(self.ordner / "gibt_es_nicht.exfat"), str(self.aus / "x.pkg"))
        self.assertTrue(str(ctx.exception).strip())
        self.assertFalse(os.path.exists(self.aus / "x.pkg"))

    def test_lesen_einer_fehlenden_quelle_ist_ein_fehler(self) -> None:
        with self.assertRaises(wz.Fehler):
            fc.lesen(_EXE, str(self.ordner / "gibt_es_nicht.exfat"), str(self.ordner))


if __name__ == "__main__":
    unittest.main()
