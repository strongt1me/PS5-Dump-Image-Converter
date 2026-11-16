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


@unittest.skipUnless(basis._TK_DA, "ohne Anzeige kein Fenster")
class ForgeFensterTests(unittest.TestCase):

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
            "lesen": mock.patch.object(fc, "lesen", side_effect=lambda exe, pfad, arbeit=None, **k: self.infos[pfad]),
            "ordner_lesen": mock.patch.object(wz, "ordner_lesen",
                                              side_effect=lambda ordner, arbeit=None, **k: self.infos[ordner]),
        }
        for p in self._patcher.values():
            p.start()
            self.addCleanup(p.stop)
        self.dialoge: dict[str, list] = {"info": [], "fehler": [], "frage": []}
        for name, ziel, antwort in (("showinfo", "info", None), ("showerror", "fehler", None), ("askyesno", "frage", True)):
            m = mock.patch.object(fz.messagebox, name, side_effect=lambda *a, _z=ziel, _r=antwort, **k: (
                self.dialoge[_z].append(a), _r)[1])
            m.start()
            self.addCleanup(m.stop)
        for schluessel, wert in ((fz.EINST_AKTION, fz.AKTION_UMWANDELN), (fz.EINST_FORMAT, "ffpfsc"),
                                 (fz.EINST_BIBLIOTHEK, []), (fz.EINST_ZIEL, ""), (opt.BUILDER, "forge"),
                                 (opt.FORGE_KRAKEN, "fast"), (opt.FORGE_VOLL_PRUEFEN, False),
                                 (opt.FORGE_BACKPORT_ENTFERNEN, False), (opt.KRAKEN_KERNE, 0),
                                 (opt.MIN_FW_VERSION, ""), (opt.PATCH_MODUS, False)):
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


if __name__ == "__main__":
    unittest.main()
