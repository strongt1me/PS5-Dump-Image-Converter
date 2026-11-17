# -*- coding: utf-8 -*-
"""Der Bau eines Pakets mit Dump Forge im Fenster „PS5 PKG Dump & Image Converter“ (seit 16.11.2026).

Auftrag: ``.ffpkg``, ``.ffpfsc``, ``.ffpfs``, ``.exfat`` und Dump-Ordner werden im Bereich „PKG / FPKG“ zu einem Paket
(FPKG) gebaut - mit der Befehlszeile von Dump Forge, die das Programm mitliefert. Hier wird das **Fenster** geprueft, am
wirklichen Programm; die Befehlszeile selbst ist durch eine Attrappe ersetzt (``forge_cli.lesen``/``forge_cli.bauen``).
Die Huelle um die echte Befehlszeile prueft ``test_forge_cli.py``.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

# Die Hilfen und die Anzeige (ein Tk-Wurzelfenster je Prozess) kommen aus dem Test des Fensters; der Import lenkt auch
# den Einstellungsordner um.
import test_ps5_pkg_fenster as basis                        # noqa: E402

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.ui import ps5_pkg_fenster as fz          # noqa: E402
from ps5_validator.utils import forge_cli as fc             # noqa: E402
from ps5_validator.utils import ps5_pkg_optionen as opt     # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz      # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402


def _de(schluessel: str, **kw) -> str:
    return STRINGS[schluessel]["de"].format(**kw)


class _ForgeBasis(unittest.TestCase):
    """Das Fenster mit einer Attrappe fuer Dump Forge - die Grundlage von ``ForgeFensterTests`` und ``EinbauSeiteTests``."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(basis._WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        if basis._WURZEL.state() == "iconic":
            basis._WURZEL.deiconify()
            basis._pumpen(0.2)
        self.app._current_language = "de"
        self.ordner = tempfile.mkdtemp(prefix="ps5forge_test_")
        self.addCleanup(lambda: APP._rmtree_force(self.ordner, ignore_errors=True))
        self.infos: dict[str, wz.PaketInfo] = {}
        self.aufrufe: list[dict] = []
        # Weder ffpfsc-pkg-tool noch .NET: Der Forge-Weg braucht beides nicht (das ist ein Teil dessen, was geprueft wird).
        self._patcher = {
            "werkzeug": mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value=""),
            "forge": mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value="forge-exe"),
            "dotnet": mock.patch.object(wz, "dotnet_ordner", return_value=""),
            # Die Firmware der Konsole ist hier "nicht angegeben": Sonst fragte schon der erste Bau eines Spiels, das
            # eine Firmware verlangt (die echte Befehlszeile liest 2.00), mit einem echten Auswahlfenster danach - der
            # Vorschlag zu BACKPORT hat seine eigenen Tests (test_backport_empfehlung.py).
            "konsole": mock.patch.object(APP.PS5ConverterGUI, "_konsole_fw_bekannt", return_value=""),
            "lesen": mock.patch.object(fc, "lesen", side_effect=lambda exe, pfad, arbeit=None, **k: self.infos[pfad]),
            "ordner_lesen": mock.patch.object(wz, "ordner_lesen",
                                              side_effect=lambda ordner, arbeit=None, **k: self.infos[ordner]),
        }
        for p in self._patcher.values():
            p.start()
            self.addCleanup(p.stop)
        self.dialoge: dict[str, list] = {"info": [], "fehler": [], "frage": [], "auswahl": []}
        for name, ziel, antwort in (("showinfo", "info", None), ("showerror", "fehler", None), ("askyesno", "frage", True)):
            m = mock.patch.object(fz.messagebox, name, side_effect=lambda *a, _z=ziel, _r=antwort, **k: (
                self.dialoge[_z].append(a), _r)[1])
            m.start()
            self.addCleanup(m.stop)
        # Bei einem Spielordner bietet die Frage "In der Quelle fehlt etwas" seit 17.11.2026 einen Auswahldialog an (als Abbild
        # mit Einbau oder trotzdem als Paket); hier antwortet der Test mit dem Paket, wie zuvor mit "Ja".
        m = mock.patch.object(APP.PS5ConverterGUI, "_auswahl_dialog", side_effect=lambda _s, *a, **k: (
            self.dialoge["auswahl"].append(a), _de("ps5pkg.emu_wahl_paket"))[1])
        m.start()
        self.addCleanup(m.stop)
        for schluessel, wert in ((fz.EINST_AKTION, fz.AKTION_UMWANDELN), (fz.EINST_FORMAT, "ffpfsc"),
                                 (fz.EINST_BIBLIOTHEK, []), (fz.EINST_ZIEL, ""), (opt.BUILDER, "forge"),
                                 (opt.FORGE_KRAKEN, "fast"), (opt.FORGE_VOLL_PRUEFEN, False),
                                 (opt.FORGE_BACKPORT_ENTFERNEN, False), (opt.KRAKEN_KERNE, 0),
                                 (opt.MIN_FW_VERSION, ""), (opt.PATCH_MODUS, False), (fz.EINST_BAUER_GEFRAGT, True)):
            self.app._save_setting(schluessel, wert)
        self.f = fz.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
        self.addCleanup(self._schliessen)
        self.ziel = os.path.join(self.ordner, "ziel")
        os.makedirs(self.ziel)
        self.f.ziel_var.set(self.ziel)

    def _schliessen(self) -> None:
        try:
            if self.f.win.winfo_exists():
                self.f._job = None
                self.f._uebergabe = None
                self.f.win.destroy()
        except Exception:  # noqa: BLE001
            pass
        basis._pumpen(0.05)

    # ---------------- Quellen ----------------
    def _abbild(self, name: str = "Testspiel.exfat", tid: str = "PPSA00009", titel: str = "Neun Spiel") -> str:
        pfad = os.path.join(self.ordner, name)
        Path(pfad).write_bytes(b"x" * 4096)
        art = fc.abbild_art(pfad)
        self.infos[pfad] = wz.PaketInfo(
            pfad=pfad, groesse=4096, typ=wz.TYP_ABBILD, content_id="EP0000-%s_00-TESTTESTTESTTEST" % tid, title_id=tid,
            titel=titel, param={"contentVersion": "01.000.000"}, abbild=art, befunde=["Beispielbefund"])
        return pfad

    def _spielordner(self, name: str = "Spielordner", tid: str = "PPSA00003", titel: str = "Gamma Spiel") -> str:
        ordner = os.path.join(self.ordner, name)
        os.makedirs(os.path.join(ordner, "sce_sys"))
        Path(ordner, "sce_sys", "param.json").write_text("{}", encoding="utf-8")
        self.infos[ordner] = wz.PaketInfo(
            pfad=ordner, groesse=8192, typ=wz.TYP_ORDNER, content_id="EP0000-%s_00-TESTTESTTESTTEST" % tid, title_id=tid,
            titel=titel, param={"contentVersion": "01.000.000"})
        return ordner

    def _laden(self, pfad: str) -> None:
        # Einen Spielordner liest weiterhin ffpfsc-pkg-tool-seitig ``wz.ordner_lesen`` (hier ersetzt); das Fenster verlangt
        # dafuer wie bisher das Werkzeug. Ein Abbild braucht nur Forge.
        werkzeug = "werkzeug" if os.path.isdir(pfad) else ""
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value=werkzeug):
            self.f._pakete_hinzufuegen([pfad], waehlen=True)
        self.assertTrue(basis._warten(lambda: self.f.aktuell is not None and self.f.aktuell.pfad == pfad))

    def _attrappe(self, schreibt: bytes = b"pkg", warten=None, fehler: "Exception | None" = None):
        """Ersetzt ``forge_cli.bauen``: schreibt die Datei (wie Forge nach bestandener Pruefung) und meldet Fortschritt."""
        def bauen(exe, quelle, ziel, **kw):
            self.aufrufe.append(dict(kw, exe=exe, quelle=quelle, ziel=ziel, temp_da=os.path.isdir(os.path.dirname(ziel))))
            kw["fortschritt"](40, "compress")
            kw["zeile"]("package: content id X, about 1 MiB")
            if warten is not None:
                warten(kw["abbruch"])
            if fehler is not None:
                raise fehler
            Path(ziel).write_bytes(schreibt)
            return fc.ForgeBau(pfad=ziel, bytes=len(schreibt), dateien=2, pruefungen=["fpkg verify: a", "check: b"],
                               modus=kw.get("voll_pruefen") and "full" or "fast", geprueft_bytes=1, gesamt_bytes=2, proben=1)
        return mock.patch.object(fc, "bauen", side_effect=bauen)

    def _starten_und_warten(self, grenze: float = 20.0) -> None:
        self.f._starten()
        self.assertTrue(basis._warten(lambda: self.f._job is None, grenze), "der Auftrag ist nicht zu Ende gegangen")


@unittest.skipUnless(basis._TK_DA, "ohne Anzeige kein Fenster")
class ForgeFensterTests(_ForgeBasis):

    # ---------------- Lesen und Anzeige ----------------
    def test_ein_abbild_wird_ohne_net_werkzeug_gelesen_und_angezeigt(self) -> None:
        pfad = self._abbild()
        self._laden(pfad)
        f, info = self.f, self.f.aktuell
        self.assertTrue(info.ist_abbild)
        self.assertEqual("Abbild EXFAT", f.paket_typ.cget("text"))
        self.assertEqual(_de("ps5pkg.src_image", art="exfat"), dict(f.tech.item(i, "values") for i in f.tech.get_children())["Quelle"])
        self.assertIn("[Dump Forge] Beispielbefund", f.protokoll.get("1.0", "end"))
        self.assertEqual([], self.dialoge["fehler"])

    def test_aus_einem_abbild_geht_nur_das_paket_der_rest_hat_eine_klare_absage(self) -> None:
        self._laden(self._abbild())
        f = self.f
        self.assertEqual("pkg", f.format_schluessel, "das Auswahlfeld springt auf Paket")
        self.assertTrue(f._format_moeglich("pkg"))
        for anderes in ("ffpkg", "ffpfsc", "ffpfs", "exfat"):
            with self.subTest(format=anderes):
                self.assertFalse(f._format_moeglich(anderes))
        for aktion in ("extrahieren", "pruefen"):
            with self.subTest(aktion=aktion):
                self.assertFalse(f._aktion_moeglich(aktion))
        self.assertTrue(f._aktion_moeglich("umwandeln"))
        f._format_waehlen("ffpfsc")
        self.assertEqual(_de("ps5pkg.format_only_package"), f.status_var.get())
        self.assertEqual("pkg", f.format_schluessel)

    def test_das_datei_durchsuchen_im_ordner_nimmt_abbilder_mit_und_laesst_anderes_liegen(self) -> None:
        a = self._abbild("a.ffpkg", tid="PPSA00001")
        b = self._abbild("b.FFPFSC", tid="PPSA00002")
        Path(self.ordner, "text.txt").write_text("nichts")
        Path(self.ordner, "c.zip").write_bytes(b"zip")
        gefunden = self.f._quellen_in(self.ordner)
        self.assertEqual([a, b], gefunden)

    def test_ohne_die_forge_befehlszeile_fehlt_dem_abbild_das_werkzeug_mit_klarer_meldung(self) -> None:
        pfad = self._abbild()
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self.f._pakete_hinzufuegen([pfad], waehlen=True)
        self.assertEqual(1, len(self.dialoge["fehler"]))
        self.assertIn("Dump-Forge-CLI", self.dialoge["fehler"][0][1])
        self.assertEqual([], self.f.pakete)

    # ---------------- Bauen ----------------
    def test_ein_abbild_wird_mit_forge_zu_einem_paket_im_zielordner(self) -> None:
        pfad = self._abbild()
        self._laden(pfad)
        f = self.f
        with self._attrappe(), mock.patch.object(wz, "bauen") as lpp, mock.patch.object(wz, "pruefen") as pruefen:
            self._starten_und_warten()
        lpp.assert_not_called()
        pruefen.assert_not_called()
        self.assertEqual(1, len(self.aufrufe))
        aufruf = self.aufrufe[0]
        self.assertEqual(("forge-exe", pfad), (aufruf["exe"], aufruf["quelle"]))
        name = "Neun Spiel [PPSA00009].pkg"
        self.assertEqual(name, os.path.basename(aufruf["ziel"]))
        self.assertEqual(self.ziel, os.path.dirname(os.path.dirname(aufruf["ziel"])), "Arbeitsordner im Zielordner")
        self.assertTrue(aufruf["temp_da"])
        self.assertEqual([name], os.listdir(self.ziel), "das Paket liegt im Zielordner, der Arbeitsordner ist weg")
        self.assertEqual(b"pkg", Path(self.ziel, name).read_bytes())
        self.assertEqual(_de("ps5pkg.job_done_build", datei=name), f.auftrag_var.get())
        log = f.protokoll.get("1.0", "end")
        self.assertIn("package: content id X, about 1 MiB", log, "Forges Protokollzeilen kommen im Fenster an")
        self.assertIn("[OK] Dump Forge: 2 Prüfungen bestanden", log)
        self.assertIn("Stichproben", log)
        self.assertIn(_de("ps5pkg.forge_note"), log, "der Konsolenhinweis nennt Dump Forge")
        self.assertNotIn(_de("ps5pkg.build_note"), log, "nicht den des anderen Werkzeugs (ps5-fpkg-converter)")
        self.assertEqual(self.ziel, f._z.get("ausgabe"))
        self.assertEqual(100.0, float(f.balken_gesamt["value"]))

    def test_die_optionen_kommen_bei_forge_an(self) -> None:
        for schluessel, wert in ((opt.FORGE_KRAKEN, "smallest"), (opt.FORGE_VOLL_PRUEFEN, True),
                                 (opt.FORGE_BACKPORT_ENTFERNEN, True), (opt.KRAKEN_KERNE, 4)):
            self.app._save_setting(schluessel, wert)
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        a = self.aufrufe[0]
        self.assertEqual(("smallest", True, True, 4), (a["kraken"], a["voll_pruefen"], a["backport_entfernen"], a["kerne"]))
        self.assertIn("jedes Byte geprüft", self.f.protokoll.get("1.0", "end"), "die vollstaendige Pruefung steht im Ergebnis")

    def test_eine_unbekannte_gespeicherte_stufe_faellt_auf_die_schnelle_zurueck(self) -> None:
        self.app._save_setting(opt.FORGE_KRAKEN, "irgendwas")
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual("fast", self.aufrufe[0]["kraken"])

    def test_ein_spielordner_baut_bei_forge_als_paketersteller_mit_forge(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with self._attrappe(), mock.patch.object(wz, "bauen") as lpp:
            self._starten_und_warten()
        lpp.assert_not_called()
        self.assertEqual(ordner, self.aufrufe[0]["quelle"])
        self.assertEqual(["Gamma Spiel [PPSA00003].pkg"], os.listdir(self.ziel))

    def test_ein_spielordner_baut_bei_lpp_weiter_ueber_libprosperopkg(self) -> None:
        self.app._save_setting(opt.BUILDER, "lpp")
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        self.assertEqual("lpp", self.f._bauer_fuer(self.f.aktuell))
        self.assertEqual("forge", self.f._bauer_fuer(self.infos[self._abbild()]), "ein Abbild baut immer Forge")

    def test_fehlt_forge_baut_ein_spielordner_ueber_libprosperopkg_statt_gar_nicht(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self.assertEqual("lpp", self.f._bauer_fuer(self.f.aktuell))

    def test_nur_libprosperopkg_kennt_diese_optionen_und_forge_sagt_es_vor_dem_bau(self) -> None:
        self.app._save_setting(opt.MIN_FW_VERSION, "9.00")
        self.app._save_setting(opt.PATCH_MODUS, True)
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        log = self.f.protokoll.get("1.0", "end")
        self.assertIn(_de("ps5pkg.forge_ignoriert", option=_de("ps5pkg.opt_build_min_fw")), log)
        self.assertIn(_de("ps5pkg.forge_ignoriert", option=_de("ps5pkg.opt_build_patch_modus")), log)
        self.assertNotIn(_de("ps5pkg.opt_build_backport"), log, "was nicht gesetzt ist, wird nicht gemeldet")

    def test_ohne_zielordner_wird_nicht_gebaut(self) -> None:
        self._laden(self._abbild())
        self.f.ziel_var.set(os.path.join(self.ordner, "gibt-es-nicht"))
        with self._attrappe():
            self.f._starten()
        self.assertEqual([], self.aufrufe)
        self.assertEqual(1, len(self.dialoge["fehler"]))

    # ---------------- vorhandenes Paket ----------------
    def test_ein_vorhandenes_paket_gleichen_namens_wird_nur_mit_haken_ersetzt(self) -> None:
        name = "Neun Spiel [PPSA00009].pkg"
        Path(self.ziel, name).write_bytes(b"alt")
        self._laden(self._abbild())
        with self._attrappe(schreibt=b"neu"):
            self.f._starten()
        self.assertEqual([], self.aufrufe, "ohne den Haken wird nicht einmal begonnen")
        self.assertEqual(1, len(self.dialoge["info"]))
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe(schreibt=b"neu"):
            self._starten_und_warten()
        self.assertEqual(b"neu", Path(self.ziel, name).read_bytes())
        self.assertEqual([name], os.listdir(self.ziel))

    def test_scheitert_ein_ersetzender_bau_bleibt_das_alte_paket_unversehrt(self) -> None:
        name = "Neun Spiel [PPSA00009].pkg"
        Path(self.ziel, name).write_bytes(b"alt")
        self._laden(self._abbild())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe(fehler=wz.Fehler("Dump Forge sagt nein")):
            self._starten_und_warten()
        self.assertEqual(b"alt", Path(self.ziel, name).read_bytes())
        self.assertEqual([name], os.listdir(self.ziel), "und kein Arbeitsordner bleibt liegen")

    # ---------------- Fehler und Abbruch ----------------
    def test_ein_fehler_von_forge_steht_im_protokoll_und_hinterlaesst_nichts(self) -> None:
        self._laden(self._abbild())
        with self._attrappe(fehler=wz.Fehler("the output name is too long")):
            self._starten_und_warten()
        f = self.f
        self.assertEqual(_de("ps5pkg.job_failed"), f.auftrag_var.get())
        self.assertIn("the output name is too long", f.protokoll.get("1.0", "end"))
        self.assertEqual([], os.listdir(self.ziel))

    def test_abbrechen_beendet_den_bau_ohne_fehlschlag_und_ohne_reste(self) -> None:
        self._laden(self._abbild())
        begonnen = []

        def warten(abbruch) -> None:
            begonnen.append(True)
            ende = time.monotonic() + 15
            while not abbruch() and time.monotonic() < ende:
                time.sleep(0.02)
            if abbruch():
                raise wz.Fehler("abgebrochen")

        with self._attrappe(warten=warten):
            self.f._starten()
            self.assertTrue(basis._warten(lambda: bool(begonnen), 10), "der Bau laeuft")
            self.f._abbrechen()
            self.assertTrue(basis._warten(lambda: self.f._job is None, 20))
        self.assertEqual(_de("ps4pkg.status_cancelled"), self.f.auftrag_var.get())
        self.assertNotEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())
        self.assertEqual([], os.listdir(self.ziel), "kein Paket, kein Arbeitsordner")

    def test_der_balken_zeigt_die_stufen_in_der_sprache_des_programms(self) -> None:
        self.assertEqual(_de("ps5pkg.forge_stage_compress"), self.f._forge_stufe_text("compress"))
        self.assertEqual("unbekannt", self.f._forge_stufe_text("unbekannt"), "fremde Stufen bleiben, wie sie sind")
        for stufe in fz.FORGE_STUFEN:
            with self.subTest(stufe=stufe):
                for sprache in ("de", "en", "es", "it", "fr"):
                    self.assertTrue(STRINGS["ps5pkg.forge_stage_" + stufe][sprache].strip())

    # ---------------- Ende zu Ende mit der echten Befehlszeile ----------------
    @unittest.skipUnless(fc.werkzeug_suchen([str(PROJEKT)]), "fuer diese Plattform liegt keine Dump-Forge-Befehlszeile bei")
    def test_vom_abbild_bis_zum_paket_mit_der_echten_befehlszeile_durch_das_fenster(self) -> None:
        """Nichts ersetzt: ``forge.lesen`` und ``forge.bauen`` laufen gegen die mitgelieferte Befehlszeile."""
        import json
        import subprocess
        exe = fc.werkzeug_suchen([str(PROJEKT)])
        spiel = os.path.join(self.ordner, "Echtes Spiel")
        os.makedirs(os.path.join(spiel, "sce_sys"))
        param = {"contentId": "EP9999-PPSA99999_00-TESTSPIEL0000001", "titleId": "PPSA99999", "contentVersion": "01.000.000",
                 "masterVersion": "01.00", "applicationCategoryType": 0, "applicationDrmType": "standard",
                 "conceptId": "100000", "requiredSystemSoftwareVersion": "0x0200000000000000",
                 "sdkVersion": "0x0200000000000000",
                 "localizedParameters": {"defaultLanguage": "en-US", "en-US": {"titleName": "Echtes Spiel"}}}
        Path(spiel, "sce_sys", "param.json").write_text(json.dumps(param), encoding="utf-8")
        Path(spiel, "eboot.bin").write_bytes(os.urandom(4096))
        Path(spiel, "daten.bin").write_bytes(b"abc" * 4000)
        bild = os.path.join(self.ordner, "Echtes Spiel.ffpfsc")
        self.assertEqual(0, subprocess.run([exe, "convert", spiel, "--to", "ffpfsc", "-o", bild], capture_output=True).returncode)
        for name in ("lesen", "forge"):
            self._patcher[name].stop()
        self.addCleanup(self._patcher["lesen"].start)
        self.addCleanup(self._patcher["forge"].start)
        f = self.f
        f._pakete_hinzufuegen([bild], waehlen=True)
        self.assertTrue(basis._warten(lambda: f.aktuell is not None and f.aktuell.pfad == bild, 30), "Forge hat das Abbild gelesen")
        self.assertEqual(("PPSA99999", "Echtes Spiel", "ffpfsc"), (f.aktuell.title_id, f.aktuell.titel, f.aktuell.abbild))
        self.assertEqual("pkg", f.format_schluessel)
        self._starten_und_warten(60)
        name = "Echtes Spiel [PPSA99999].pkg"
        self.assertEqual([name], os.listdir(self.ziel))
        with open(os.path.join(self.ziel, name), "rb") as datei:
            self.assertEqual(b"FIH", datei.read(4))
        self.assertEqual(_de("ps5pkg.job_done_build", datei=name), f.auftrag_var.get())
        log = f.protokoll.get("1.0", "end")
        self.assertIn("[OK] Dump Forge:", log)
        self.assertIn("fpkg: verifying", log, "Forges eigene Protokollzeilen kommen durch das Fenster an")

    # ---------------- Emulatoren (DLC EMU, PlayGo) ----------------
    _DLC = dict(dlc_vorhanden=True, dlc_emuliert=False, dlc_merkmal="addcont0")
    _PLAYGO = dict(playgo_merkmal="sce_sys/playgo-scenario.json")

    def _abbild_mit_fakten(self, **fakten) -> str:
        pfad = self._abbild()
        self.infos[pfad].fakten = fc.QuellFakten(**fakten)
        return pfad

    def _fragen(self) -> list:
        return [a for a in self.dialoge["frage"] if a and a[0] == _de("ps5pkg.emu_titel")]

    def test_fehlt_dlc_emu_wird_vor_dem_bau_gefragt_und_mit_ja_gebaut(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._DLC))
        with self._attrappe():
            self._starten_und_warten()
        fragen = self._fragen()
        self.assertEqual(1, len(fragen))
        self.assertIn(_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0"), fragen[0][1])
        self.assertNotIn("• PlayGo:", fragen[0][1], "nur die fehlende Zeile steht in der Liste")
        self.assertEqual(1, len(self.aufrufe), "mit Ja wird gebaut")
        self.assertIn(_de("ps5pkg.emu_log"), self.f.protokoll.get("1.0", "end"))

    def test_fehlt_der_playgo_stub_wird_ebenso_gefragt(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._PLAYGO))
        with self._attrappe():
            self._starten_und_warten()
        fragen = self._fragen()
        self.assertEqual(1, len(fragen))
        self.assertIn(_de("ps5pkg.emu_zeile_playgo", merkmal="sce_sys/playgo-scenario.json"), fragen[0][1])
        self.assertNotIn("• DLC EMU:", fragen[0][1])
        self.assertEqual(1, len(self.aufrufe))

    def test_fehlen_beide_steht_es_in_einer_frage(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._DLC, **self._PLAYGO))
        with self._attrappe():
            self._starten_und_warten()
        fragen = self._fragen()
        self.assertEqual(1, len(fragen), "eine Frage, nicht zwei")
        self.assertIn(_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0"), fragen[0][1])
        self.assertIn(_de("ps5pkg.emu_zeile_playgo", merkmal="sce_sys/playgo-scenario.json"), fragen[0][1])

    def test_mit_nein_wird_nicht_gebaut_und_nichts_bleibt_liegen(self) -> None:
        self._laden(self._abbild_mit_fakten(**self._DLC))
        with self._attrappe(), mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.f._starten()
        frage.assert_called_once()
        self.assertEqual([], self.aufrufe)
        self.assertIsNone(self.f._job)
        self.assertEqual(_de("ps5pkg.emu_abgebrochen"), self.f.status_var.get())
        self.assertEqual([], os.listdir(self.ziel), "kein Arbeitsordner, kein Paket")
        self.assertNotIn(_de("ps5pkg.emu_log"), self.f.protokoll.get("1.0", "end"))

    def test_liegen_die_emulatoren_in_der_quelle_oder_braucht_sie_das_spiel_nicht_keine_frage(self) -> None:
        faelle = {
            "DLC schon emuliert": dict(dlc_vorhanden=True, dlc_emuliert=True, dlc_merkmal="addcont0"),
            "PlayGo-Stub liegt darin": dict(playgo_merkmal="sce_sys/playgo-scenario.json", emulatoren=("playgo",)),
            "weder DLC noch PlayGo": dict(),
            "AMPR fehlt (legt Forge selbst dazu)": dict(ampr_importiert=True, ampr_fehlt=True),
        }
        for name, fakten in faelle.items():
            with self.subTest(fall=name):
                self.dialoge["frage"].clear()
                self.aufrufe.clear()
                self._laden(self._abbild_mit_fakten(**fakten))
                with self._attrappe():
                    self._starten_und_warten()
                self.assertEqual([], self._fragen())
                self.assertEqual(1, len(self.aufrufe))
                for p in os.listdir(self.ziel):
                    os.remove(os.path.join(self.ziel, p))

    def test_ohne_forges_fakten_wird_nicht_gefragt(self) -> None:
        self._laden(self._abbild())
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual([], self._fragen())

    def test_ein_spielordner_wird_vor_dem_bau_von_forge_gelesen_und_das_nur_einmal(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with self._attrappe(), mock.patch.object(fc, "quellfakten_lesen",
                                                 return_value=fc.QuellFakten(**self._DLC)) as lesen:
            self._starten_und_warten()
            self.assertEqual(1, lesen.call_count)
            self.assertEqual(("forge-exe", ordner), lesen.call_args.args)
            self.assertEqual(1, len(self.dialoge["auswahl"]), "ein Spielordner bekommt die Wahl Abbild oder Paket")
            self.assertEqual([], self._fragen(), "und keine Ja/Nein-Frage")
            self.assertIsNotNone(self.f.aktuell.fakten, "die Antwort bleibt an der Quelle")
            for p in os.listdir(self.ziel):
                os.remove(os.path.join(self.ziel, p))
            self._starten_und_warten()
            self.assertEqual(1, lesen.call_count, "ein zweiter Bau liest nicht noch einmal")

    def test_kann_forge_den_spielordner_nicht_lesen_wird_trotzdem_gebaut(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        with self._attrappe(), mock.patch.object(fc, "quellfakten_lesen", return_value=None):
            self._starten_und_warten()
        self.assertEqual([], self._fragen())
        self.assertEqual(1, len(self.aufrufe))

    def test_die_frage_steht_nach_der_platzpruefung_und_vor_dem_ersten_arbeitsordner(self) -> None:
        text = Path(fz.__file__).read_text(encoding="utf-8")
        start = text.index("def _forge_bauen_starten")
        # Seit 17.11.2026 nimmt dieselbe Zeile fuer ein Abbild aus einem Paket den Faktor des Entpackens statt FORGE_PLATZ_FAKTOR.
        platz = text.index("self._platz_reicht(ziel, int(info.groesse * (ENTPACKT_FAKTOR if abbild else FORGE_PLATZ_FAKTOR))", start)
        frage = text.index("self._emulatoren_fragen(info)", start)
        temp = text.index("tempfile.mkdtemp(prefix=\"ps5conv_forge_\"", start)
        self.assertLess(platz, frage)
        self.assertLess(frage, temp, "bei Nein darf kein Arbeitsordner entstehen")

    # ---------------- Zielformat ----------------
    def test_ohne_gespeicherte_wahl_gilt_ffpkg_eine_gespeicherte_bleibt(self) -> None:
        """Bis 16.11.2026 galt ``ffpfsc``; das Programm empfiehlt ``ffpkg`` selbst. Wer gewaehlt hat, behaelt seine Wahl."""
        for gespeichert, erwartet in ((None, "ffpkg"), ("ffpfsc", "ffpfsc"), ("exfat", "exfat"), ("kaputt", "ffpkg")):
            with self.subTest(gespeichert=gespeichert):
                self._schliessen()
                with mock.patch.object(fz.Ps5PkgFenster, "_einstellung",
                                       side_effect=lambda k, v, _g=gespeichert: _g if (k == fz.EINST_FORMAT and _g) else v):
                    self.f = fz.oeffnen(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt)
                self.assertEqual(erwartet, self.f.format_schluessel)

    def test_ffpfsc_und_ffpfs_nennen_das_tempo_ffpkg_und_exfat_und_paket_nicht(self) -> None:
        """Wie im Hauptfenster: Nach der Wahl von ``ffpfsc``/``ffpfs`` steht ein Satz zu Tempo und Empfehlung."""
        self._laden(self._spielordner())
        hinweis = _de("main.pfs_speed_hint")
        for schluessel, erwartet in (("ffpfsc", True), ("ffpfs", True), ("ffpkg", False), ("exfat", False), ("pkg", False)):
            with self.subTest(format=schluessel):
                self.f._status("vorher")
                self.f._format_waehlen(schluessel)
                self.assertEqual(schluessel, self.f.format_schluessel)
                self.assertEqual(hinweis if erwartet else "vorher", self.f.status_var.get())

    # ---------------- Namen ----------------
    def test_der_name_kommt_aus_titel_und_kennung_und_bleibt_in_63_bytes(self) -> None:
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "x.exfat"), typ=wz.TYP_ABBILD, title_id="PPSA12345",
                            titel="Ein sehr langer Spieltitel " * 6)
        name = fz.Ps5PkgFenster._forge_dateiname(info)
        self.assertTrue(name.endswith(" [PPSA12345].pkg"))
        self.assertLessEqual(len(name[:-4].encode("utf-8")), 63)

    def test_ohne_titel_gilt_der_name_der_quelle_ohne_endung(self) -> None:
        info = wz.PaketInfo(pfad=os.path.join(self.ordner, "Mein Abbild.exfat"), typ=wz.TYP_ABBILD, title_id="PPSA12345")
        self.assertEqual("Mein Abbild [PPSA12345].pkg", fz.Ps5PkgFenster._forge_dateiname(info))

    def test_das_ergebnisfeld_zeigt_den_namen_den_das_programm_vergibt(self) -> None:
        self._laden(self._abbild())
        self.assertEqual("Neun Spiel [PPSA00009].pkg", self.f.ergebnis_var["output"].get())


@unittest.skipUnless(basis._TK_DA, "ohne Anzeige kein Fenster")
class EinbauSeiteTests(_ForgeBasis):
    """Seite 7 wie die Aufgaben 1 bis 6 (17.11.2026): Einbau-Karte, Pruefung der Quelle, Rueckfragen vor dem Bau, Umwandeln eines
    Pakets ohne Zwischenordner, Lebenszeichen.

    Die Felder der Karte sind Zwillinge der Felder im Hauptfenster (gleiche Tk-Variablen, gleiche Befehle); die Befehle
    selbst pruefen die Tests der Aufgaben 1 bis 6 - hier zaehlt, dass die Karte sie ruft und ihre Listen und Sperren uebernimmt.
    """

    _DLC = dict(dlc_vorhanden=True, dlc_emuliert=False, dlc_merkmal="addcont0")

    def setUp(self) -> None:
        super().setUp()
        # Die Kaestchen und Felder der Aufgaben 1 bis 6 behalten nach dem Test, was sie vorher hatten.
        app = self.app
        for name in ("ampr_integrate_var", "ampr_playgo_var", "dlc_integrate_var", "backport_integrate_var"):
            var = getattr(app, name)
            self.addCleanup(var.set, var.get())
        for name in ("zstd_level", "worker_count", "mkpfs_verify"):
            self.addCleanup(app._save_setting, name, app._load_setting(name, None))
        self.addCleanup(app._save_setting, fz.EINST_BAUER_GEFRAGT, True)
        # Der Faden, der das PlayGo-Merkmal eines Pakets im Archiv sucht, soll hier nichts starten.
        m = mock.patch.object(wz, "playgo_erklaert_archiv", return_value="")
        m.start()
        self.addCleanup(m.stop)
        self.karte = self.f.einbau
        self.assertIsNotNone(self.karte, "die Seite hat die Einbau-Karte")

    # ---------------- Quellen ----------------
    def _paket(self, name: str = "Alpha.pkg", tid: str = "PPSA00007", titel: str = "Sieben") -> "wz.PaketInfo":
        pfad = os.path.join(self.ordner, name)
        Path(pfad).write_bytes(b"pkg")
        info = basis._info(name, titel, tid, 4096, pfad)
        self.infos[pfad] = info
        self.f.pakete.append(info)
        self.f._paket_waehlen(info, aus_liste=True)
        return info

    def _sichtbare_zeilen(self) -> "list[str]":
        return [text.cget("text") for rahmen, _m, text in self.karte._bericht_zeilen if rahmen.winfo_manager()]

    def _schliessen_nicht_abwarten(self) -> None:
        basis._pumpen(0.1)

    # ---------------- die Karte ----------------
    def test_die_felder_haengen_an_denselben_variablen_wie_in_den_aufgaben_1_bis_6(self) -> None:
        app = self.app
        haken = {"ampr": "ampr_integrate_var", "voll": "_ampr_voll_var", "playgo": "ampr_playgo_var",
                 "dlc": "dlc_integrate_var", "backport": "backport_integrate_var"}
        combos = {"kompression": "compression_level_var", "pruefung": "verify_var", "version": "ampr_version_var",
                  "methode": "ampr_methode_var", "packverfahren": "_ampr_pack_var", "packstufe": "_ampr_stufe_var",
                  "backport_fw": "backport_fw_var"}
        for name, var in haken.items():
            with self.subTest(haken=name):
                self.assertEqual(str(getattr(app, var)), self.karte.felder[name].cget("variable"))
        for name, var in combos.items():
            with self.subTest(combo=name):
                self.assertEqual(str(getattr(app, var)), self.karte.felder[name].cget("textvariable"))
        self.assertIn("worker", self.karte.felder)

    def test_ein_klick_aufs_kaestchen_ist_ein_klick_in_den_aufgaben_1_bis_6(self) -> None:
        app = self.app
        for name, var in (("dlc", "dlc_integrate_var"), ("playgo", "ampr_playgo_var"), ("backport", "backport_integrate_var")):
            with self.subTest(haken=name), mock.patch.object(app, "_on_integration_changed") as befehl:
                vorher = getattr(app, var).get()
                self.karte.felder[name].invoke()
                self.assertEqual(not vorher, getattr(app, var).get(), "dieselbe Variable wie im Hauptfenster")
                befehl.assert_called_once_with()

    def test_eine_wahl_in_einer_liste_ruft_den_befehl_des_hauptfensters(self) -> None:
        befehle = {"kompression": "_on_compression_level_changed", "pruefung": "_on_verify_stufe_changed",
                   "version": "_ampr_version_gewaehlt", "methode": "_ampr_methode_gewaehlt",
                   "packverfahren": "_ampr_pack_gewaehlt", "packstufe": "_ampr_stufe_gewaehlt",
                   "backport_fw": "_backport_fw_gewaehlt"}
        for name, befehl in befehle.items():
            with self.subTest(liste=name), mock.patch.object(self.app, befehl) as m:
                self.karte.felder[name].event_generate("<<ComboboxSelected>>")
                m.assert_called_once()

    def test_die_befehle_der_listen_stehen_im_hauptfenster_und_nicht_mehr_als_lambda(self) -> None:
        """Die Liste im Hauptfenster und die Zwillingsliste hier rufen dieselbe Methode - eine Stelle fuer beide."""
        text = Path(APP.__file__).read_text(encoding="utf-8")
        for name in ("_ampr_version_gewaehlt", "_ampr_methode_gewaehlt", "_backport_fw_gewaehlt"):
            with self.subTest(befehl=name):
                self.assertIn("def %s(self)" % name, text)
                self.assertIn("lambda _e: self.%s()" % name, text)

    def test_die_methode_ruft_wie_bisher_alle_drei_nachfolger(self) -> None:
        """Der Wechsel der Methode prueft die Voraussetzungen, schaltet die Packfelder und bewertet die Zielformat-Liste neu."""
        with mock.patch.object(self.app, "_on_ampr_methode_changed") as a, \
                mock.patch.object(self.app, "_ampr_pack_combo_schalten") as b, \
                mock.patch.object(self.app, "_refresh_target_format_options") as c:
            self.app._ampr_methode_gewaehlt()
        for m in (a, b, c):
            m.assert_called_once_with()

    def test_listen_und_sperren_kommen_aus_dem_hauptfenster(self) -> None:
        app, karte = self.app, self.karte
        alt_werte = tuple(app.ampr_version_combo.cget("values"))
        alt_zustand = str(app.backport_fw_combo.cget("state"))
        self.addCleanup(app.ampr_version_combo.configure, values=alt_werte)
        self.addCleanup(app.backport_fw_combo.configure, state=alt_zustand)
        app.ampr_version_combo.configure(values=("Alpha 1", "Beta 2"))
        app.backport_fw_combo.configure(state="disabled")
        karte.abgleichen(True, True)
        self.assertEqual(("Alpha 1", "Beta 2"), karte.felder["version"].values)
        self.assertEqual("disabled", karte.felder["backport_fw"].cget("state"))
        app.backport_fw_combo.configure(state="readonly")
        karte.abgleichen(True, True)
        self.assertEqual("readonly", karte.felder["backport_fw"].cget("state"))

    def test_die_kompression_ist_nur_beim_container_frei(self) -> None:
        karte = self.karte
        karte.abgleichen(True, False)
        self.assertEqual("disabled", karte.felder["kompression"].cget("state"))
        self.assertEqual(str(self.app.compression_combo.cget("state")), karte.felder["pruefung"].cget("state"),
                         "die Pruefung bleibt wie im Hauptfenster")
        self.f._format_waehlen("ffpfsc")
        self.f._einbau_abgleichen()
        self.assertNotEqual("disabled", karte.felder["kompression"].cget("state"))
        self.f._format_waehlen("exfat")
        self.f._einbau_abgleichen()
        self.assertEqual("disabled", karte.felder["kompression"].cget("state"), "bei .exFAT kennt das Format keine Stufe")

    def test_ein_paket_nimmt_den_einbau_nicht_auf_felder_gesperrt_und_hinweis_steht_da(self) -> None:
        karte = self.karte
        self._laden(self._spielordner())
        self.f._format_waehlen("pkg")
        self.f._einbau_abgleichen()
        felder = [n for n in karte.felder if n != "worker"]
        self.assertTrue(all(str(karte.felder[n].cget("state")) == "disabled" for n in felder), "alle gesperrt")
        self.assertEqual("grid", karte.hinweis.winfo_manager(), "der Hinweis erklaert es")
        self.f._format_waehlen("ffpkg")
        self.f._einbau_abgleichen()
        self.assertEqual("", karte.hinweis.winfo_manager(), "bei einem Abbild steht er nicht da")
        self.assertTrue(any(str(karte.felder[n].cget("state")) != "disabled" for n in felder))

    def test_auch_extrahieren_und_pruefen_nehmen_keinen_einbau(self) -> None:
        self._paket()
        for aktion in ("extrahieren", "pruefen"):
            with self.subTest(aktion=aktion):
                self.f.aktion_var.set(aktion)
                self.assertFalse(self.f._einbau_gilt())
        self.f.aktion_var.set("umwandeln")
        self.f.format_schluessel = "ffpkg"
        self.assertTrue(self.f._einbau_gilt())

    def test_die_zeile_der_asset_packs_erscheint_mit_ampr_emu(self) -> None:
        karte, var = self.karte, self.app.ampr_integrate_var
        var.set(False)
        karte.abgleichen(True, True)
        self.assertEqual("", karte._pack_zeile.winfo_manager())
        var.set(True)
        karte.abgleichen(True, True)
        self.assertEqual("pack", karte._pack_zeile.winfo_manager())
        var.set(False)
        karte.abgleichen(True, True)
        self.assertEqual("", karte._pack_zeile.winfo_manager())

    def test_die_kurzinfos_der_karte_haengen_nicht_am_hauptfenster(self) -> None:
        """``g._tooltip`` haelt jede Kurzinfo samt Feld fuer immer fest - je Fenster blieben 4 GDI-Objekte stehen
        (``test_fenster_leck``, 17.11.2026). Die Karte legt ihre Kurzinfos selbst an."""
        vorher = len(getattr(self.app, "_tooltip_schluessel", []))
        # ``oeffnen`` gibt die vorhandene Seite zurueck - ein zweites, eigenes Fenster baut nur der Konstruktor.
        zweites = fz.Ps5PkgFenster(self.app, APP.UI_SCHRIFT, APP.MONO_SCHRIFT, APP.pt, "")
        try:
            self.assertIsNot(zweites, self.f)
            self.assertGreater(len(zweites.einbau._kurzinfos), 5, "die Karte hat ihre Kurzinfos")
            self.assertEqual(vorher, len(getattr(self.app, "_tooltip_schluessel", [])))
        finally:
            zweites._schliesst = True
            zweites.win.destroy()
            basis._pumpen(0.05)

    def test_die_kurzinfos_mit_wechselndem_text_folgen_dem_hauptfenster(self) -> None:
        app, karte = self.app, self.karte
        alt = app._ampr_pack_tooltip.text
        self.addCleanup(setattr, app._ampr_pack_tooltip, "text", alt)
        app._ampr_pack_tooltip.text = "Gesperrt, weil kein Asset-Pack"
        karte.abgleichen(True, True)
        self.assertEqual("Gesperrt, weil kein Asset-Pack", karte._kurzinfos["packverfahren"].text)

    def test_der_takt_gleicht_ab_aber_nur_wenn_die_seite_zu_sehen_ist(self) -> None:
        with mock.patch.object(self.karte, "abgleichen") as abgleichen:
            self.f._takt_arbeiten()
            abgleichen.assert_called_once()
            abgleichen.reset_mock()
            self.f._rest_sichtbar = False
            try:
                self.f._takt_arbeiten()
            finally:
                self.f._rest_sichtbar = True
            abgleichen.assert_not_called()

    def test_kompression_worker_und_pruefung_stehen_in_der_zeile_des_zielformats(self) -> None:
        self.f._seite_zeigen("umwandeln")
        basis._pumpen(0.3)
        self.f.win.update_idletasks()
        y = self.f.format_box.winfo_rooty()
        for name in ("kompression", "worker", "pruefung"):
            with self.subTest(feld=name):
                feld = self.karte.felder[name]
                self.assertEqual(self.f.format_box.master.master, feld.master.master, "in derselben Zeile")
                self.assertGreater(feld.winfo_rootx(), self.f.format_box.winfo_rootx())
                self.assertLess(abs(feld.winfo_rooty() - y), 12, "auf gleicher Hoehe wie das Zielformat")

    # ---------------- die Pruefung der Quelle ----------------
    def test_die_pruefung_zeigt_alle_fuenf_zeilen_gefaerbt(self) -> None:
        fakten = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True, gepackt="zstd", dlc_vorhanden=True, dlc_merkmal="a0",
                                playgo_merkmal="sce_sys/playgo-chunk.dat", emulatoren=("playgo",), sdk="10.00", firmware="11.20")
        with mock.patch.object(APP.PS5ConverterGUI, "_konsole_fw_bekannt", return_value="7.99"):
            self.f.format_schluessel = "ffpkg"
            self.f._bericht_zeigen(None, fakten)
        zeilen = self._sichtbare_zeilen()
        self.assertEqual(5, len(zeilen))
        self.assertEqual(_de("bericht.ampr_fehlt"), zeilen[0])
        self.assertEqual(_de("bericht.packs_zstd"), zeilen[1])
        self.assertEqual(_de("bericht.playgo_da"), zeilen[2])
        self.assertEqual(_de("bericht.dlc_fehlt", merkmal="a0"), zeilen[3])
        self.assertEqual(_de("bericht.backport_fehlt", spiel="11.20", konsole="7.xx"), zeilen[4])
        farben = [str(m.cget("fg")).lower() for rahmen, m, _t in self.karte._bericht_zeilen if rahmen.winfo_manager()]
        c = self.app._COLORS
        erwartet = [c["fg_warning"], c["fg_success"], c["fg_success"], c["fg_warning"], c["fg_warning"]]
        self.assertEqual([f.lower() for f in erwartet], farben, "fehlt = Warnfarbe, da oder nicht noetig = Erfolgsfarbe")

    def test_ohne_quelle_nicht_pruefbar_oder_ohne_forge_steht_der_grund_da(self) -> None:
        karte = self.karte
        self.assertEqual(_de("bericht.keine_quelle"), karte.status.cget("text"))
        self.assertEqual([], self._sichtbare_zeilen())
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self._laden(self._spielordner())
        self.assertEqual(_de("bericht.keine_forge"), karte.status.cget("text"))
        self.f._bericht_zeigen(self.f.aktuell, None)
        self.assertEqual(_de("bericht.nicht_pruefbar"), karte.status.cget("text"))

    def test_ein_spielordner_wird_im_hintergrund_geprueft_und_der_bau_liest_nicht_noch_einmal(self) -> None:
        def langsam(*a, **k):
            time.sleep(1.5)
            return fc.QuellFakten(**self._DLC)
        ordner = self._spielordner()
        with mock.patch.object(fc, "quellfakten_lesen", side_effect=langsam) as lesen:
            self._laden(ordner)
            info = self.f.aktuell
            self.assertEqual(_de("bericht.laedt"), self.karte.status.cget("text"), "waehrend gelesen wird, steht es da")
            self.assertIsNone(info.fakten)
            fakten = self.f._quellfakten(info)                       # ein Bau, der jetzt startet, wartet auf den Faden
            self.assertIsNotNone(fakten)
            self.assertEqual(1, lesen.call_count, "nicht noch einmal gelesen")
            self.assertTrue(basis._warten(lambda: bool(self._sichtbare_zeilen()), 5))
        self.assertIn(_de("bericht.dlc_fehlt", merkmal="addcont0"), self._sichtbare_zeilen())

    def test_eine_veraltete_antwort_gehoert_nicht_zur_neuen_quelle(self) -> None:
        a, b = self._spielordner("A", "PPSA00011", "Eins"), self._spielordner("B", "PPSA00012", "Zwei")
        def lesen(exe, pfad, **k):
            time.sleep(0.5 if pfad == a else 0.0)
            return fc.QuellFakten(**self._DLC) if pfad == a else fc.QuellFakten()
        with mock.patch.object(fc, "quellfakten_lesen", side_effect=lesen):
            self._laden(a)
            self._laden(b)
            self.assertTrue(basis._warten(lambda: not self.karte.status.cget("text"), 5))
            basis._pumpen(0.8)
        self.assertEqual(_de("bericht.dlc_nicht_noetig"), self._sichtbare_zeilen()[3], "die Antwort der Quelle B steht da")

    def test_bei_einem_paket_von_dump_forge_ist_fehlendes_ampr_nur_ein_hinweis_in_der_karte(self) -> None:
        fakten = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True)
        info = self._spielordner()
        self._laden(info)
        self.f._format_waehlen("pkg")
        self.f._bericht_zeigen(self.f.aktuell, fakten)
        self.assertEqual(_de("bericht.ampr_forge"), self._sichtbare_zeilen()[0])
        self.f._format_waehlen("ffpkg")
        self.f._bericht_zeigen(self.f.aktuell, fakten)
        self.assertEqual(_de("bericht.ampr_fehlt"), self._sichtbare_zeilen()[0], "als Abbild muss es eingebaut werden")

    # ---------------- die Rueckfrage vor dem Paketbau ----------------
    def _auswahl(self, antwort: str):
        return mock.patch.object(APP.PS5ConverterGUI, "_auswahl_dialog", side_effect=lambda _t, *a, **k: (
            self.dialoge["auswahl"].append(a), antwort)[1])

    def test_fehlt_im_spielordner_etwas_geht_der_weg_ueber_ein_abbild_mit_einbau(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        self.f.aktuell.fakten = fc.QuellFakten(**self._DLC)
        gemerkt = self.app._load_setting(fz.EINST_FORMAT, None)
        self.app.dlc_integrate_var.set(False)
        with self._auswahl(_de("ps5pkg.emu_wahl_abbild")), mock.patch.object(self.app, "_launch_task") as a1, \
                self._attrappe(), mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="werkzeug"), \
                mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"):
            self.f._starten()
            self.assertEqual([], self.aufrufe, "es wird kein Paket gebaut")
            self.assertTrue(self.app.dlc_integrate_var.get(), "DLC EMU ist angehakt wie in Aufgabe 1")
            self.assertEqual("ffpkg", self.f.format_schluessel)
            self.assertEqual(gemerkt, self.app._load_setting(fz.EINST_FORMAT, None), "die Formatwahl des Anwenders bleibt")
            self.assertIn(_de("ps5pkg.emu_abbild_log", liste="DLC EMU"), self.f.protokoll.get("1.0", "end"))
            self.assertTrue(basis._warten(lambda: a1.call_count == 1, 5), "der Lauf geht als Abbild an Aufgabe 1")
        self.assertEqual(1, len(self.dialoge["auswahl"]))
        eintraege = self.dialoge["auswahl"][0][1]
        self.assertEqual([_de("ps5pkg.emu_wahl_abbild"), _de("ps5pkg.emu_wahl_paket")], eintraege)
        self.assertIn(_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0"), self.dialoge["auswahl"][0][0])

    def test_wer_trotzdem_als_paket_baut_bekommt_es_und_wer_schliesst_bricht_ab(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        self.f._format_waehlen("pkg")
        self.f.aktuell.fakten = fc.QuellFakten(**self._DLC)
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")), self._attrappe():
            self._starten_und_warten()
        self.assertEqual(1, len(self.aufrufe))
        self.assertIn(_de("ps5pkg.emu_log"), self.f.protokoll.get("1.0", "end"))
        for p in os.listdir(self.ziel):
            os.remove(os.path.join(self.ziel, p))
        self.aufrufe.clear()
        with self._auswahl(""), self._attrappe():
            self.f._starten()
        self.assertEqual([], self.aufrufe)
        self.assertEqual(_de("ps5pkg.emu_abgebrochen"), self.f.status_var.get())
        self.assertEqual([], os.listdir(self.ziel), "kein Arbeitsordner")

    def test_ein_abbild_als_quelle_bietet_den_weg_ueber_ein_abbild_nicht_an(self) -> None:
        """Aus einem Abbild geht hier nur das Paket - Ja/Nein, wie zuvor."""
        pfad = self._abbild()
        self._laden(pfad)
        self.f.aktuell.fakten = fc.QuellFakten(**self._DLC)
        self.assertFalse(self.f._abbild_mit_einbau_moeglich(self.f.aktuell))
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual([], self.dialoge["auswahl"])
        self.assertEqual(1, len([a for a in self.dialoge["frage"] if a and a[0] == _de("ps5pkg.emu_titel")]))

    def test_der_weg_ueber_ein_abbild_ist_gesperrt_solange_aufgabe_1_arbeitet(self) -> None:
        self._laden(self._spielordner())
        with mock.patch.object(self.app, "is_running", True, create=True):
            self.assertFalse(self.f._abbild_mit_einbau_moeglich(self.f.aktuell))
        self.assertTrue(self.f._abbild_mit_einbau_moeglich(self.f.aktuell))

    def test_ampr_fehlt_fragt_ein_werkzeug_mit_arbeitsordner_und_dump_forge_nicht(self) -> None:
        ordner = self._spielordner()
        self._laden(ordner)
        info = self.f.aktuell
        info.fakten = fc.QuellFakten(ampr_importiert=True, ampr_fehlt=True)
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")), mock.patch.object(self.f, "_bauer_fuer", return_value="lpp"):
            self.assertTrue(self.f._emulatoren_fragen(info))
        self.assertEqual(1, len(self.dialoge["auswahl"]), "LibProsperoPkg legt AMPR EMU nicht dazu: gefragt")
        self.assertIn(_de("ps5pkg.emu_zeile_ampr"), self.dialoge["auswahl"][0][0])
        self.dialoge["auswahl"].clear()
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")), mock.patch.object(self.f, "_bauer_fuer", return_value="forge"):
            self.assertTrue(self.f._emulatoren_fragen(info))
        self.assertEqual([], self.dialoge["auswahl"], "Dump Forge legt ihn selbst dazu: keine Frage")
        self.assertIn(_de("bericht.ampr_forge"), self.f.protokoll.get("1.0", "end"))

    def test_der_bericht_steht_auch_dann_im_protokoll_wenn_nichts_fehlt(self) -> None:
        pfad = self._abbild()
        self._laden(pfad)
        self.f.aktuell.fakten = fc.QuellFakten(gepackt="lz4")
        with self._attrappe():
            self._starten_und_warten()
        log = self.f.protokoll.get("1.0", "end")
        for text in (_de("bericht.titel"), "[OK] " + _de("bericht.packs_lz4"), "[OK] " + _de("bericht.playgo_nicht_noetig"),
                     _de("bericht.einbau_paket")):
            with self.subTest(text=text):
                self.assertIn(text, log)
        self.assertEqual([], self.dialoge["auswahl"])

    def test_ein_spielordner_ohne_fakten_schreibt_dass_er_nicht_zu_pruefen_war(self) -> None:
        self._laden(self._spielordner())
        self.f._format_waehlen("pkg")
        with mock.patch.object(fc, "quellfakten_lesen", return_value=None), self._attrappe():
            self._starten_und_warten()
        self.assertIn(_de("bericht.nicht_pruefbar"), self.f.protokoll.get("1.0", "end"))

    def test_die_frage_nach_dem_backport_fragt_nach_der_firmware_nur_einmal(self) -> None:
        self._laden(self._spielordner())
        self.f.aktuell.fakten = fc.QuellFakten(sdk="10.00", firmware="11.20")
        with self._auswahl(_de("ps5pkg.emu_wahl_paket")), \
                mock.patch.object(APP.PS5ConverterGUI, "_backport_plan", return_value=("7.99", 7)) as plan, \
                mock.patch.object(APP.PS5ConverterGUI, "_konsole_fw_bekannt", return_value="7.99"):
            self.assertTrue(self.f._emulatoren_fragen(self.f.aktuell))
        plan.assert_called_once()
        self.assertIn(_de("ps5pkg.emu_zeile_backport", spiel="11.20", konsole="7.xx"), self.dialoge["auswahl"][0][0])

    # ---------------- der Paketersteller ----------------
    def _flag(self, wert) -> None:
        self.app._save_setting(fz.EINST_BAUER_GEFRAGT, wert)

    def test_wer_libprosperopkg_oder_prosperopkgtool_hat_wird_einmal_gefragt(self) -> None:
        for bauer, name in (("lpp", "LibProsperoPkg"), ("ppt", "ProsperoPkgTool")):
            with self.subTest(bauer=bauer):
                self.dialoge["frage"].clear()
                self._flag(False)
                self.app._save_setting(opt.BUILDER, bauer)
                info = self._spielordner(name="O" + bauer)
                self._laden(info)
                self.assertTrue(self.f._bauer_wechseln_fragen(self.f.aktuell), "mit Ja baut Dump Forge")
                self.assertEqual("forge", self.app._load_setting(opt.BUILDER, ""))
                self.assertIs(True, self.app._load_setting(fz.EINST_BAUER_GEFRAGT, False))
                self.assertIn(_de("ps5pkg.ask_bauer", name=name), [a[1] for a in self.dialoge["frage"]])
                self.assertIn(_de("ps5pkg.log_bauer_forge"), self.f.protokoll.get("1.0", "end"))

    def test_mit_nein_bleibt_der_paketersteller_und_es_wird_nie_wieder_gefragt(self) -> None:
        self._flag(False)
        self.app._save_setting(opt.BUILDER, "lpp")
        self._laden(self._spielordner())
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False) as frage:
            self.assertFalse(self.f._bauer_wechseln_fragen(self.f.aktuell))
            frage.assert_called_once()
            self.assertEqual("lpp", self.app._load_setting(opt.BUILDER, ""), "nichts wird still umgestellt")
            self.assertFalse(self.f._bauer_wechseln_fragen(self.f.aktuell))
            frage.assert_called_once()
        self.assertIn(_de("ps5pkg.log_bauer_bleibt", name="LibProsperoPkg"), self.f.protokoll.get("1.0", "end"))

    def test_keine_frage_ohne_dump_forge_oder_bei_einem_abbild_oder_nach_der_antwort(self) -> None:
        self.app._save_setting(opt.BUILDER, "lpp")
        self._laden(self._spielordner())
        folder = self.f.aktuell
        with mock.patch.object(fz.messagebox, "askyesno") as frage:
            self._flag(False)
            with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
                self.assertFalse(self.f._bauer_wechseln_fragen(folder), "ohne Dump Forge gibt es nichts zu wechseln")
            self.assertFalse(self.f._bauer_wechseln_fragen(self._paket()), "nur ein Spielordner wird kopiert")
            self._flag(True)
            self.assertFalse(self.f._bauer_wechseln_fragen(folder))
            frage.assert_not_called()

    def test_der_paketbau_mit_libprosperopkg_fragt_vor_dem_start(self) -> None:
        self._flag(False)
        self.app._save_setting(opt.BUILDER, "lpp")
        self._laden(self._spielordner())
        self.f._format_waehlen("pkg")
        # LibProsperoPkg und .NET sind da (sonst kaeme der Bau gar nicht bis zur Frage); gebaut wird nach "Ja" mit Dump Forge.
        with self._attrappe(), mock.patch.object(fz.Ps5PkgFenster, "_werkzeug", return_value="werkzeug"), \
                mock.patch.object(wz, "dotnet_ordner", return_value="dotnet"):
            self._starten_und_warten()
        fragen = [a[1] for a in self.dialoge["frage"] if len(a) > 1]
        self.assertIn(_de("ps5pkg.ask_bauer", name="LibProsperoPkg"), fragen)
        self.assertEqual(1, len(self.aufrufe), "nach Ja baut Dump Forge - ohne Arbeitsordner des Werkzeugs")
        self.assertEqual("forge", self.app._load_setting(opt.BUILDER, ""))

    # ---------------- ein Paket ohne Zwischenordner in ein Abbild ----------------
    def _umwandeln_vorbereiten(self, format: str = "ffpkg") -> "wz.PaketInfo":
        info = self._paket()
        self.f.aktion_var.set("umwandeln")
        self.f._format_waehlen(format)
        for name in ("ampr_integrate_var", "ampr_playgo_var", "dlc_integrate_var", "backport_integrate_var"):
            getattr(self.app, name).set(False)
        return info

    def test_ein_paket_geht_im_strom_in_das_abbild_ohne_entpacken_und_ohne_arbeitsordner(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        with self._attrappe(), mock.patch.object(wz, "extrahieren") as entpacken, \
                mock.patch.object(self.app, "_launch_task") as aufgabe1, \
                mock.patch.object(fz.tempfile, "mkdtemp", wraps=fz.tempfile.mkdtemp) as ordner_anlegen:
            self._starten_und_warten()
        entpacken.assert_not_called()
        aufgabe1.assert_not_called()
        self.assertEqual(1, len(self.aufrufe))
        aufruf = self.aufrufe[0]
        self.assertEqual("ffpkg", aufruf["format"])
        self.assertEqual(info.pfad, aufruf["quelle"])
        name = "Sieben [PPSA00007].ffpkg"
        self.assertEqual([name], os.listdir(self.ziel))
        self.assertTrue(aufruf["temp_da"])
        self.assertEqual(["ps5conv_forge_"], [c.kwargs["prefix"] for c in ordner_anlegen.call_args_list],
                         "nur der Arbeitsordner neben dem Ziel, nie der Temp-Ordner des Systems")
        self.assertEqual(_de("ps5pkg.job_done_convert"), self.f.auftrag_var.get())
        log = self.f.protokoll.get("1.0", "end")
        self.assertIn(_de("ps5pkg.log_start_abbild", name="Alpha.pkg"), log)
        self.assertIn(_de("ps5pkg.log_done_convert", name=name), log)
        self.assertEqual([], [p for p in os.listdir(self.ziel) if p.startswith("ps5conv_")], "nichts bleibt liegen")

    def test_alle_vier_abbildformate_gehen_direkt_und_die_felder_der_karte_kommen_an(self) -> None:
        self.app._save_setting("zstd_level", 3)
        self.app._save_setting("worker_count", 2)
        self.app._save_setting("mkpfs_verify", "voll")
        for format, endung in (("ffpkg", ".ffpkg"), ("ffpfsc", ".ffpfsc"), ("ffpfs", ".ffpfs"), ("exfat", ".exfat")):
            with self.subTest(format=format):
                self.aufrufe.clear()
                for p in os.listdir(self.ziel):
                    os.remove(os.path.join(self.ziel, p))
                self._umwandeln_vorbereiten(format)
                with self._attrappe():
                    self._starten_und_warten()
                aufruf = self.aufrufe[0]
                self.assertEqual(format, aufruf["format"])
                self.assertEqual((3, 2, True), (aufruf["stufe"], aufruf["kerne"], aufruf["voll_pruefen"]),
                                 "KOMPRESSION, WORKER und PRUEFUNG der Karte")
                self.assertEqual(["Sieben [PPSA00007]" + endung], os.listdir(self.ziel))

    def test_mit_angehaktem_einbau_bleibt_es_beim_entpacken_und_das_protokoll_sagt_warum(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        self.app.ampr_playgo_var.set(True)
        self.assertFalse(self.f._abbild_direkt_moeglich(info))
        self.assertIn(_de("ps5pkg.log_einbau_braucht_ordner", liste="PlayGo"), self.f.protokoll.get("1.0", "end"))

    def test_fehlt_dem_paket_etwas_fragt_das_fenster_ob_entpackt_und_eingebaut_wird(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        info.fakten = fc.QuellFakten(**self._DLC)
        with mock.patch.object(fz.messagebox, "askyesno", return_value=True) as frage:
            self.assertFalse(self.f._abbild_direkt_moeglich(info), "Ja: der Weg ueber den Arbeitsordner und Aufgabe 1")
        self.assertEqual(_de("ps5pkg.emu_frage_entpacken", liste=_de("ps5pkg.emu_zeile_dlc", merkmal="addcont0")),
                         frage.call_args.args[1])
        self.assertTrue(self.app.dlc_integrate_var.get(), "DLC EMU ist angehakt")
        with mock.patch.object(fz.messagebox, "askyesno", return_value=False):
            self.app.dlc_integrate_var.set(False)
            self.assertTrue(self.f._abbild_direkt_moeglich(info), "Nein: direkt, ohne Einbau")
        self.assertFalse(self.app.dlc_integrate_var.get())

    def test_wann_der_strom_nicht_gilt(self) -> None:
        info = self._umwandeln_vorbereiten("ffpkg")
        self.assertTrue(self.f._abbild_direkt_moeglich(info))
        with mock.patch.object(fz.Ps5PkgFenster, "_werkzeug_forge", return_value=""):
            self.assertFalse(self.f._abbild_direkt_moeglich(info), "ohne Dump Forge")
        self.f.format_schluessel = "pkg"
        self.assertFalse(self.f._abbild_direkt_moeglich(info), "kein Abbildformat")
        self.f.format_schluessel = "ffpkg"
        ordner = self._spielordner("Ordner2")
        self._laden(ordner)
        self.assertFalse(self.f._abbild_direkt_moeglich(self.f.aktuell), "ein Spielordner geht an Aufgabe 1")
        stumm = os.path.join(self.ordner, "x.pkg")
        info2 = basis._info("x.pkg", "X", "PPSA00001", 10, stumm)
        self.assertFalse(self.f._abbild_direkt_moeglich(info2), "die Datei gibt es nicht")

    def test_ein_langer_titel_wird_auf_die_grenze_von_forge_gekuerzt(self) -> None:
        info = self._paket("Lang.pkg", "PPSA00008", "Ein langer Spieltitel " * 5)
        self.assertLessEqual(len(os.path.splitext(self.f._forge_abbild_name(info, "ffpkg"))[0].encode("utf-8")), 63)
        self.assertLessEqual(len(os.path.splitext(self.f._forge_abbild_name(info, "ffpfsc"))[0].encode("utf-8")), 58)
        self.assertTrue(self.f._forge_abbild_name(info, "exfat").endswith(".exfat"))

    def test_ein_vorhandenes_abbild_wird_nur_mit_dem_haken_ersetzt(self) -> None:
        self._umwandeln_vorbereiten("ffpkg")
        vorhanden = os.path.join(self.ziel, "Sieben [PPSA00007].ffpkg")
        Path(vorhanden).write_bytes(b"alt")
        self.f.ueberschreiben_var.set(False)
        with self._attrappe():
            self.f._starten()
        self.assertEqual([], self.aufrufe)
        self.assertEqual(_de("ps5pkg.err_exists_abbild", pfad=vorhanden), self.dialoge["info"][-1][1])
        self.assertEqual(b"alt", Path(vorhanden).read_bytes())
        self.f.ueberschreiben_var.set(True)
        with self._attrappe():
            self._starten_und_warten()
        self.assertEqual(b"pkg", Path(vorhanden).read_bytes())

    def test_ein_fehler_von_forge_beim_abbild_hinterlaesst_nichts(self) -> None:
        self._umwandeln_vorbereiten("exfat")
        with self._attrappe(fehler=wz.Fehler("kaputt")):
            self._starten_und_warten()
        self.assertEqual([], os.listdir(self.ziel))
        self.assertIn("kaputt", self.f.protokoll.get("1.0", "end"))
        self.assertEqual(_de("ps5pkg.job_failed"), self.f.auftrag_var.get())

    def test_abbrechen_beim_abbild_raeumt_den_arbeitsordner_weg(self) -> None:
        self._umwandeln_vorbereiten("ffpkg")

        def warten(abbruch):
            self.f._abbruch = True
            raise wz.Fehler("abgebrochen")
        with self._attrappe(warten=warten):
            self._starten_und_warten()
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], self.f._staging)

    # ---------------- das Lebenszeichen ----------------
    def _job(self, art: str, info, laeuft_seit: float, letzte_vor: float) -> None:
        jetzt = time.monotonic()
        self.f._job = {"art": art, "info": info, "ziel": self.ziel, "start": jetzt - laeuft_seit,
                       "letzte": jetzt - letzte_vor, "zeichen": None}

    def test_das_lebenszeichen_nennt_die_dauer_und_das_werkzeug(self) -> None:
        info = self._spielordner()
        self._laden(info)
        self._job("bauen", self.f.aktuell, laeuft_seit=125, letzte_vor=3)
        self.f._lebenszeichen_zeigen()
        self.assertEqual(_de("ps5pkg.lebt_zeit", dauer="2:05", werkzeug="Dump Forge"), self.f.lebt_var.get())

    def test_wird_es_still_sagt_die_seite_seit_wann_nichts_Neues_kam(self) -> None:
        self._laden(self._spielordner())
        self._job("bauen", self.f.aktuell, laeuft_seit=3725, letzte_vor=45)
        self.f._lebenszeichen_zeigen()
        text = self.f.lebt_var.get()
        self.assertIn("1:02:05", text)
        self.assertIn(_de("ps5pkg.lebt_still", still="0:45"), text)
        self._job("bauen", self.f.aktuell, laeuft_seit=3725, letzte_vor=fz.Ps5PkgFenster.STILLE_AB - 2)
        self.f._lebenszeichen_zeigen()
        self.assertNotIn(_de("ps5pkg.lebt_still", still="0:18"), self.f.lebt_var.get(), "erst ab der Grenze")

    def test_ohne_auftrag_ist_die_zeile_leer(self) -> None:
        self.f.lebt_var.set("Rest")
        self.f._job = None
        self.f._lebenszeichen_zeigen()
        self.assertEqual("", self.f.lebt_var.get())

    def test_eine_neue_meldung_oder_ein_neuer_prozentwert_setzt_die_stille_zurueck(self) -> None:
        self._laden(self._spielordner())
        faelle = {"Zeile des Werkzeugs": {"zeilen": ["fpkg: writing"]}, "anderer Prozentwert": {"prozent": 42.0},
                  "andere Dateizeile": {"schritt_text": "data/d001.bin"}}
        for name, aenderung in faelle.items():
            with self.subTest(fall=name):
                self._job("bauen", self.f.aktuell, laeuft_seit=100, letzte_vor=60)
                alt = self.f._job["letzte"]
                with self.f._sperre:
                    self.f._z.update(dict({"zeilen": [], "prozent": None, "schritt_text": None}, **aenderung))
                self.f._takt_arbeiten()
                self.assertGreater(self.f._job["letzte"], alt)

    def test_ohne_neues_bleibt_die_zeit_der_letzten_meldung_stehen(self) -> None:
        self._laden(self._spielordner())
        self._job("bauen", self.f.aktuell, laeuft_seit=100, letzte_vor=60)
        with self.f._sperre:
            self.f._z.update({"zeilen": [], "prozent": 10.0, "schritt_text": "x"})
        self.f._takt_arbeiten()
        gemerkt = self.f._job["letzte"]
        self.f._takt_arbeiten()                       # dasselbe noch einmal: nichts Neues
        self.assertEqual(gemerkt, self.f._job["letzte"])

    def test_das_werkzeug_wird_beim_namen_genannt(self) -> None:
        info = self._spielordner()
        self._laden(info)
        a = self.f.aktuell
        for bauer, name in (("forge", "Dump Forge"), ("lpp", "LibProsperoPkg"), ("ppt", "ProsperoPkgTool")):
            with self.subTest(bauer=bauer), mock.patch.object(self.f, "_bauer_fuer", return_value=bauer):
                self.assertEqual(name, self.f._werkzeug_name("bauen", a))
        self.assertEqual("Dump Forge", self.f._werkzeug_name("abbild", a))
        self.assertEqual("LibProsperoPkg", self.f._werkzeug_name("pruefen", a))
        self.app._save_setting(opt.BUILDER, "ppt")
        self.assertEqual("ProsperoPkgTool", self.f._werkzeug_name("extrahieren", a))

    def test_der_start_nennt_das_werkzeug_und_den_weg_zu_dump_forge(self) -> None:
        """Gemeldet am 17.11.2026: Mit ProsperoPkgTool stand nur "Staging (0/38'497 MiB)" da - woher das kam, sah man nicht."""
        self._laden(self._spielordner())
        a = self.f.aktuell
        with mock.patch.object(self.f, "_bauer_fuer", return_value="ppt"), mock.patch.object(fz.threading, "Thread"):
            self.f._job_starten("bauen", lambda *x: None, a, self.ziel)
        log = self.f.protokoll.get("1.0", "end")
        self.assertIn(_de("ps5pkg.log_bauer", name="ProsperoPkgTool"), log)
        self.assertIn(_de("ps5pkg.log_bauer_tipp"), log)
        self.f._job = None
        self.f.protokoll.configure(state="normal")
        self.f.protokoll.delete("1.0", "end")
        self.f.protokoll.configure(state="disabled")
        with mock.patch.object(self.f, "_bauer_fuer", return_value="forge"), mock.patch.object(fz.threading, "Thread"):
            self.f._job_starten("bauen", lambda *x: None, a, self.ziel)
        log = self.f.protokoll.get("1.0", "end")
        self.assertIn(_de("ps5pkg.log_bauer", name="Dump Forge"), log)
        self.assertNotIn(_de("ps5pkg.log_bauer_tipp"), log, "wer schon Dump Forge hat, braucht den Tipp nicht")

    def test_die_dauer_als_text(self) -> None:
        for sekunden, text in ((0, "0:00"), (59.9, "0:59"), (60, "1:00"), (125, "2:05"), (3599, "59:59"), (3600, "1:00:00"),
                               (3725, "1:02:05"), (-5, "0:00")):
            with self.subTest(sekunden=sekunden):
                self.assertEqual(text, fz.Ps5PkgFenster._dauer_text(sekunden))



if __name__ == "__main__":
    unittest.main()
