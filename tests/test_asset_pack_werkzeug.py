# -*- coding: utf-8 -*-
"""LZ4-Stufe, lose Endungen, leere Dateien und das Werkzeug fuer fertige Asset-Packs.

Anlass (15.10.2026): Die Konsolen-App LZ4 Compression 1.5.0 wurde Zeile fuer
Zeile gegen dieses Programm gelesen. Gleich waren Format (AMPRPAK4/AMPRDAT3),
Laufzeit (dieselbe ``libSceAmpr.sprx``) und die Stufen der Systemdateien. Anders
waren vier Dinge, die hier abgesichert sind:

* **Stufe.** Das Werkzeug bietet 1 bis 12 (Vorgabe 9); hier stand sie fest auf
  12 - gemessen 1,2- bis 3,6-mal langsamer fuer 0,0 bis 0,6 Prozentpunkte.
* **Lose Endungen.** Schon verdichtete Medien, Bilder, Archive und
  Konfigdateien bleiben im Standardprofil lose.
* **Leere Dateien.** Die PS5 prueft sie ausserhalb des Spiels (Ghost of Yotei:
  Schwarzbild); nach dem Entfernen der Originale werden sie wieder angelegt.
* **Fertige Ordner.** Pruefen und Entpacken eines gepackten Spielordners
  (``Verify LZ4 Packs`` / ``Uncompress LZ4`` der Konsolen-App).

Die Packlaeufe sind echt (``ampr_pack.py`` gegen einen echten
``ampr_emu.index``); eine reine Musterpruefung haette den Fehler vom
07.09.2026 (``eboot.bin`` im Band) nicht gefunden.
"""
from __future__ import annotations

import fnmatch
import importlib.util
import os
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))
sys.path.insert(0, str(PROJEKT / "AMPR_PackTools-4.0"))

from ps5_validator.utils import ampr_assetpakete as ap  # noqa: E402
from ps5_validator.utils.i18n import STRINGS  # noqa: E402

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None


def _lade_hauptprogramm():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPTDATEI)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


def _index_bauen(app0: Path) -> Path:
    import build_ampr_index

    index = app0 / "ampr_emu.index"
    rc = build_ampr_index.build_index_local(app0, index, False)
    if rc != 0:
        raise AssertionError("build_ampr_index.py endete mit %d" % rc)
    return index


def _toml_der_profile() -> dict[str, str]:
    """Die vier mitgelieferten Spielprofile als Text."""
    ordner = Path(ap.PROFIL_ORDNER)
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(ordner.glob("*.toml"))}


# ---------------------------------------------------------------------------
# 1. Die LZ4-Stufe
# ---------------------------------------------------------------------------
class StufeTests(unittest.TestCase):

    def test_unbrauchbares_wird_zur_vorgabe(self):
        for wert in (None, "", "abc", True, False, 0, 13, -1, 99, [], {}):
            with self.subTest(wert=wert):
                self.assertEqual(ap.LZ4_STUFE_VORGABE, ap.lz4_stufe_lesen(wert))

    def test_gueltiges_bleibt(self):
        for wert, soll in ((1, 1), (9, 9), (12, 12), ("7", 7), (5.0, 5)):
            with self.subTest(wert=wert):
                self.assertEqual(soll, ap.lz4_stufe_lesen(wert))

    def test_vorgabe_ist_neun(self):
        """Gemessen am 15.10.2026: 12 spart 0,0-0,6 Punkte bei 1,2- bis 3,6-facher Zeit."""
        self.assertEqual(9, ap.LZ4_STUFE_VORGABE)

    def test_modus_nach_stufe(self):
        """1 bis 4 schnell, ab 5 HC - wie LZ4 Compression und Lazy_AMPR."""
        for stufe in (1, 2, 3, 4):
            self.assertIn('compression_mode = "fast"', ap.kompression_zeilen(stufe))
        for stufe in (5, 9, 12):
            self.assertIn('compression_mode = "hc"', ap.kompression_zeilen(stufe))
        self.assertIn("compression_level = 9", ap.kompression_zeilen(9))

    def test_standardprofil_traegt_die_stufe(self):
        daten = tomllib.loads(ap.standardprofil_text())
        self.assertEqual("hc", daten["pack"]["compression_mode"])
        self.assertEqual(9, daten["pack"]["compression_level"],
                         "Die Vorgabe muss 9 sein, nicht mehr die alte 12")
        schnell = tomllib.loads(ap.standardprofil_text(0, (), 3))
        self.assertEqual("fast", schnell["pack"]["compression_mode"])
        gross = tomllib.loads(ap.standardprofil_text(0, (), 12))
        self.assertEqual(12, gross["pack"]["compression_level"])

    def test_spielprofile_bekommen_die_stufe_und_sonst_nichts(self):
        """Die vier Profile bleiben gleich - bis auf die Kompressionsangaben in [pack]."""
        profile = _toml_der_profile()
        self.assertGreaterEqual(len(profile), 4, "Die Profile fehlen im Ordner")
        for name, text in profile.items():
            for stufe in (3, 9, 12):
                with self.subTest(profil=name, stufe=stufe):
                    neu = tomllib.loads(ap.profil_stufe_einsetzen(text, stufe))
                    alt = tomllib.loads(text)
                    self.assertEqual(stufe, neu["pack"]["compression_level"])
                    self.assertEqual("fast" if stufe <= 4 else "hc",
                                     neu["pack"]["compression_mode"])
                    # Alles andere unveraendert - Regeln, Gruppen, Laufzeit.
                    self.assertEqual(alt.get("rule"), neu.get("rule"))
                    self.assertEqual(alt.get("groups"), neu.get("groups"))
                    self.assertEqual(alt.get("runtime"), neu.get("runtime"))
                    fremd = {k: v for k, v in alt["pack"].items()
                             if k not in ("compression_mode", "compression_level",
                                          "acceleration")}
                    for schluessel, wert in fremd.items():
                        self.assertEqual(wert, neu["pack"][schluessel], schluessel)

    def test_keine_doppelten_schluessel(self):
        """Ein TOML mit zwei ``compression_level`` in [pack] waere ungueltig."""
        for name, text in _toml_der_profile().items():
            neu = ap.profil_stufe_einsetzen(text, 9)
            with self.subTest(profil=name):
                self.assertEqual(1, neu.count("compression_level"))

    def test_profil_ohne_pack_tabelle_bekommt_eine(self):
        neu = tomllib.loads(ap.profil_stufe_einsetzen(
            '[[rule]]\naction = "compress"\ninclude = ["**"]\n', 7))
        self.assertEqual(7, neu["pack"]["compression_level"])
        self.assertEqual(1, len(neu["rule"]))

    def test_regelschluessel_in_rule_bleiben_stehen(self):
        """Nur [pack] wird angefasst; ein Wert in einer Regel gehoert dem Profil."""
        text = ('[pack]\ncompression_level = 12\n\n[[rule]]\naction = "compress"\n'
                'include = ["**"]\ncompression_level = 5\n')
        neu = tomllib.loads(ap.profil_stufe_einsetzen(text, 9))
        self.assertEqual(9, neu["pack"]["compression_level"])
        self.assertEqual(5, neu["rule"][0]["compression_level"])

    def test_profil_des_anwenders_bleibt_unberuehrt(self):
        """Ohne die Kennzeile ist es seins - die Stufe darf es nicht anfassen."""
        with tempfile.TemporaryDirectory() as basis:
            ziel = os.path.join(basis, "ampr_pack.toml")
            eigen = '[pack]\ncompression_level = 4\n\n[[rule]]\naction = "loose"\ninclude = ["**"]\n'
            with open(ziel, "w", encoding="utf-8", newline="\n") as datei:
                datei.write(eigen)
            ap.profil_schreiben(ziel, stufe=12)
            with open(ziel, encoding="utf-8") as datei:
                self.assertEqual(eigen, datei.read())

    def test_profil_schreiben_reicht_die_stufe_durch(self):
        with tempfile.TemporaryDirectory() as basis:
            ziel = os.path.join(basis, "profil.toml")
            ap.profil_schreiben(ziel, stufe=5)
            with open(ziel, "rb") as datei:
                daten = tomllib.load(datei)
            self.assertEqual(5, daten["pack"]["compression_level"])


class StufeImProgrammTests(unittest.TestCase):
    """Die Oberflaeche liest die Stufe aus Kommandozeile oder Einstellung."""

    @classmethod
    def setUpClass(cls):
        cls.quelle = HAUPTDATEI.read_text(encoding="utf-8")

    def test_bau_und_kommandozeile_kennen_die_stufe(self):
        self.assertIn("stufe=stufe)", self.quelle)
        self.assertIn('"--ampr-lz4-stufe"', self.quelle)
        self.assertIn('app._cli_ampr_lz4_stufe = getattr(args, "ampr_lz4_stufe", None)',
                      self.quelle)

    def test_stufe_nicht_im_hauptfenster(self):
        """Die Einbauzeile ist bei Mindestbreite voll - die Stufe lebt in den Einstellungen."""
        anfang = self.quelle.index("def _show_settings_dialog")
        self.assertIn("_AMPR_LZ4_STUFE_SETTING", self.quelle[anfang:anfang + 400000])
        self.assertIn("settings_dialog.lz4_section", self.quelle)

    @unittest.skipUnless(TK_DA, "keine Anzeige")
    def test_lesen_vorrang_und_vorgabe(self):
        haupt = _lade_hauptprogramm()
        app = haupt.PS5ConverterGUI(_WURZEL)
        self.addCleanup(setattr, app, "_cli_ampr_lz4_stufe", None)
        app._cli_ampr_lz4_stufe = None
        with mock.patch.object(app, "_load_setting", return_value=None):
            self.assertEqual(9, app._ampr_lz4_stufe())
        with mock.patch.object(app, "_load_setting", return_value=11):
            self.assertEqual(11, app._ampr_lz4_stufe())
        with mock.patch.object(app, "_load_setting", return_value="kaputt"):
            self.assertEqual(9, app._ampr_lz4_stufe())
        app._cli_ampr_lz4_stufe = 4
        with mock.patch.object(app, "_load_setting", return_value=11):
            self.assertEqual(4, app._ampr_lz4_stufe(), "Die Kommandozeile hat Vorrang")


# ---------------------------------------------------------------------------
# 2. Lose Endungen
# ---------------------------------------------------------------------------
class LoseListeTests(unittest.TestCase):

    def test_stern_trifft_auch_den_schraegstrich(self):
        """Darum steht jede Endung nur einmal da, ohne ``**/``-Doppel.

        Das Werkzeug vergleicht mit ``fnmatch.fnmatchcase`` - dort trifft ``*``
        auch ``/``.
        """
        self.assertTrue(fnmatch.fnmatchcase("logo.png", "*.png"))
        self.assertTrue(fnmatch.fnmatchcase("a/b/logo.png", "*.png"))
        # Ordner dagegen brauchen beide Formen.
        self.assertFalse(fnmatch.fnmatchcase("a/uds/x.bin", "uds/**"))
        self.assertTrue(fnmatch.fnmatchcase("a/uds/x.bin", "**/uds/**"))
        self.assertTrue(fnmatch.fnmatchcase("uds/x.bin", "uds/**"))

    def test_die_muster_stehen_im_standardprofil(self):
        daten = tomllib.loads(ap.standardprofil_text())
        ausschluss = set(daten["rule"][0]["exclude"])
        for muster in ap.LOSE_MUSTER:
            with self.subTest(muster=muster):
                self.assertIn(muster, ausschluss)

    def test_dat_bleibt_gepackt(self):
        """Nur 0,19 GB von 1620 GB - aber das erprobte Verhalten bleibt."""
        self.assertNotIn("dat", ap.LOSE_ENDUNGEN)
        self.assertNotIn("*.dat", ap.LOSE_MUSTER)

    def test_medien_und_konfig_sind_drin(self):
        for endung in ("png", "dds", "zip", "ogg", "wem", "at9", "bk2", "mp4",
                       "json", "ini", "xml", "txt", "utoc"):
            with self.subTest(endung=endung):
                self.assertIn(endung, ap.LOSE_ENDUNGEN)

    def test_alle_endungen_klein_und_ohne_punkt(self):
        for endung in ap.LOSE_ENDUNGEN:
            self.assertEqual(endung, endung.lower())
            self.assertNotIn(".", endung)

    def test_schreibweisen_kommen_aus_dem_baum(self):
        with tempfile.TemporaryDirectory() as basis:
            wurzel = Path(basis)
            (wurzel / "ui").mkdir()
            (wurzel / "ui" / "Logo.PNG").write_bytes(b"x")
            (wurzel / "Intro.Mp4").write_bytes(b"x")
            (wurzel / "klein.png").write_bytes(b"x")
            (wurzel / "nutzdaten.bin").write_bytes(b"x")
            (wurzel / "ohne").write_bytes(b"x")
            self.assertEqual(("*.Mp4", "*.PNG"), ap.lose_endungen_muster(str(wurzel)))

    def test_fehlender_ordner_ist_kein_fehler(self):
        self.assertEqual((), ap.lose_endungen_muster(os.path.join(tempfile.gettempdir(),
                                                                  "gibt_es_nicht_ps5conv")))


@unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
class LoseEndungenImPacklaufTests(unittest.TestCase):

    def test_medien_bleiben_lose_nutzdaten_kommen_ins_band(self):
        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = wurzel / "app0"
            (app0 / "daten").mkdir(parents=True)
            (app0 / "ui").mkdir()
            (app0 / "sce_sys").mkdir()
            fuellung = b"PACKBAR " * 4096
            for name in ("daten/a.bin", "daten/b.pck"):
                (app0 / name).write_bytes(fuellung)
            for name in ("ui/logo.png", "ui/Gross.PNG", "daten/c.json", "daten/ton.ogg",
                         "daten/film.webm", "daten/tex.dds", "daten/pack.zip",
                         "daten/readme.txt"):
                (app0 / name).write_bytes(fuellung)
            (app0 / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 2048)
            (app0 / "sce_sys" / "param.sfo").write_bytes(b"\x00PSF" + b"\x00" * 512)
            index = _index_bauen(app0)

            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"), arbeiter=2,
                                         app0=str(app0))
            ap.packen(str(app0), str(index), str(raus), profil)
            gepackt = {str(z["path"]) for z in
                       ap.liste(str(raus / ap.MANIFEST_NAME)) if z.get("packed")}
            for pflicht in ("daten/a.bin", "daten/b.pck"):
                self.assertIn("/app0/" + pflicht, gepackt, pflicht + " haette Platz im Band")
            for lose in ("ui/logo.png", "ui/Gross.PNG", "daten/c.json", "daten/ton.ogg",
                         "daten/film.webm", "daten/tex.dds", "daten/pack.zip",
                         "daten/readme.txt"):
                self.assertNotIn("/app0/" + lose, gepackt, lose + " haette lose bleiben muessen")
            ap.pruefen(str(raus / ap.MANIFEST_NAME), app0=str(app0))


# ---------------------------------------------------------------------------
# 3. Leere Dateien
# ---------------------------------------------------------------------------
class LeereDateienTests(unittest.TestCase):

    @staticmethod
    def _zeile(pfad, packed=True, groesse=0):
        return {"path": pfad, "packed": packed, "logical_size": groesse}

    def test_fehlende_leere_dateien_werden_angelegt(self):
        with tempfile.TemporaryDirectory() as basis:
            zeilen = [self._zeile("/app0/sprachen/de"), self._zeile("/app0/leer"),
                      self._zeile("/app0/gross.bin", groesse=10),
                      self._zeile("/app0/lose", packed=False)]
            meldungen: list[str] = []
            n = ap.leere_dateien_zurueckschreiben(zeilen, basis, melden=meldungen.append)
            self.assertEqual(2, n)
            self.assertEqual(0, os.path.getsize(os.path.join(basis, "sprachen", "de")))
            self.assertEqual(0, os.path.getsize(os.path.join(basis, "leer")))
            self.assertFalse(os.path.exists(os.path.join(basis, "gross.bin")))
            self.assertFalse(os.path.exists(os.path.join(basis, "lose")))
            self.assertEqual(1, len(meldungen))

    def test_vorhandenes_bleibt_unberuehrt(self):
        with tempfile.TemporaryDirectory() as basis:
            pfad = os.path.join(basis, "leer")
            with open(pfad, "wb") as datei:
                datei.write(b"hat jetzt Inhalt")
            self.assertEqual(0, ap.leere_dateien_zurueckschreiben(
                [self._zeile("/app0/leer")], basis))
            with open(pfad, "rb") as datei:
                self.assertEqual(b"hat jetzt Inhalt", datei.read())

    def test_pfade_aus_dem_manifest_duerfen_nicht_ausbrechen(self):
        with tempfile.TemporaryDirectory() as basis:
            innen = os.path.join(basis, "spiel")
            os.makedirs(innen)
            zeilen = [self._zeile("/app0/../draussen"), self._zeile("/app0/a/../../x"),
                      self._zeile("/app0/C:/windows/x"), self._zeile("/app0/")]
            self.assertEqual(0, ap.leere_dateien_zurueckschreiben(zeilen, innen))
            self.assertEqual(["spiel"], os.listdir(basis))
            self.assertEqual([], os.listdir(innen))

    def test_ohne_zeilen_passiert_nichts(self):
        with tempfile.TemporaryDirectory() as basis:
            self.assertEqual(0, ap.leere_dateien_zurueckschreiben([], basis))


@unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
class LeereDateienNachDemEntfernenTests(unittest.TestCase):

    def test_leere_datei_ist_nach_dem_entfernen_wieder_da(self):
        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            wurzel = Path(basis)
            app0 = wurzel / "app0"
            (app0 / "daten").mkdir(parents=True)
            fuellung = b"PACKBAR " * 4096
            (app0 / "daten" / "a.bin").write_bytes(fuellung)
            (app0 / "daten" / "leer.bin").write_bytes(b"")
            (app0 / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 2048)
            index = _index_bauen(app0)
            raus = wurzel / "packed"
            profil = ap.profil_schreiben(str(wurzel / "profil.toml"), app0=str(app0))
            ap.packen(str(app0), str(index), str(raus), profil)
            manifest = str(raus / ap.MANIFEST_NAME)
            baender = ap.bandnamen(ap.uebersicht(manifest))
            ap.bestand_uebernehmen(str(raus), str(app0), baender=baender)
            manifest = str(app0 / ap.MANIFEST_NAME)
            zeilen = ap.liste(manifest)
            leer_gepackt = any(z.get("packed") and int(z.get("logical_size") or 0) == 0
                               for z in zeilen)

            ap.quellen_entfernen(manifest, str(app0))
            if leer_gepackt:
                self.assertFalse((app0 / "daten" / "leer.bin").exists(),
                                 "Das Werkzeug entfernt gepackte leere Dateien - "
                                 "dann braucht es die Wiederherstellung")
            ap.leere_dateien_zurueckschreiben(zeilen, str(app0))
            self.assertTrue((app0 / "daten" / "leer.bin").is_file())
            self.assertEqual(0, (app0 / "daten" / "leer.bin").stat().st_size)
            self.assertFalse((app0 / "daten" / "a.bin").exists(),
                             "Die Nutzdaten sind entfernt und nur im Band")


# ---------------------------------------------------------------------------
# 4. Fertige Asset-Pack-Ordner: ansehen, pruefen, entpacken
# ---------------------------------------------------------------------------
@unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
class FertigerOrdnerTests(unittest.TestCase):

    def setUp(self):
        self._basis = tempfile.TemporaryDirectory(prefix="ampr_pack_test_")
        self.addCleanup(self._basis.cleanup)
        self.wurzel = Path(self._basis.name)
        self.app0, self.original = self._spiel_bauen()

    def _spiel_bauen(self):
        """Packt einen kleinen Baum und legt den Satz in den Spielordner."""
        app0 = self.wurzel / "app0"
        (app0 / "assets").mkdir(parents=True)
        (app0 / "sce_sys").mkdir()
        (app0 / "ui").mkdir()
        for i in range(4):
            (app0 / "assets" / ("t%d.bin" % i)).write_bytes(
                ((b"ABCDEFGH" * 512) + bytes([i])) * 24)
        (app0 / "assets" / "leer.bin").write_bytes(b"")
        (app0 / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 2048)
        (app0 / "sce_sys" / "param.sfo").write_bytes(b"\x00PSF" + b"\x00" * 512)
        (app0 / "ui" / "logo.png").write_bytes(b"PNGDATA" * 100)
        index = _index_bauen(app0)
        original = {p.relative_to(app0).as_posix(): p.read_bytes()
                    for p in app0.rglob("*") if p.is_file()}
        raus = self.wurzel / "packed"
        profil = ap.profil_schreiben(str(self.wurzel / "profil.toml"), app0=str(app0))
        ap.packen(str(app0), str(index), str(raus), profil)
        baender = ap.bandnamen(ap.uebersicht(str(raus / ap.MANIFEST_NAME)))
        ap.bestand_uebernehmen(str(raus), str(app0), baender=baender)
        ap.bestand_aufraeumen(str(raus), baender, ganz=True)
        return app0, original

    def _originale_entfernen(self):
        ap.quellen_entfernen(str(self.app0 / ap.MANIFEST_NAME), str(self.app0))

    def _pack_namen(self):
        baender = ap.bandnamen(ap.uebersicht(str(self.app0 / ap.MANIFEST_NAME)))
        return {ap.MANIFEST_NAME, ap.LAUFZEIT_NAME, ap.PRUEFSUMMEN_NAME, *baender}

    # -- ansehen -----------------------------------------------------------
    def test_ohne_manifest_keiner(self):
        self.assertEqual("", ap.manifest_im_ordner(str(self.wurzel)))
        with self.assertRaises(ap.PackFehler) as ctx:
            ap.ordner_befund(str(self.wurzel))
        self.assertEqual("ampr_pack.kein_manifest", str(ctx.exception))

    def test_befund_zaehlt_und_sieht_die_originale(self):
        befund = ap.ordner_befund(str(self.app0))
        self.assertTrue(befund["crc_da"])
        self.assertGreaterEqual(befund["gepackt"], 4)
        self.assertEqual(befund["dateien"], befund["gepackt"] + befund["lose"])
        self.assertEqual(0, befund["fehlende_gepackte"], "Die Originale liegen noch da")
        self.assertEqual([], befund["baender_fehlen"])
        # Die Baender sind auf 64-KiB-Seiten ausgerichtet; bei so kleinen
        # Testdaten ist die Platte darum groesser als die logische Summe.
        self.assertGreater(befund["band_bytes"], 0)

    def test_befund_sieht_entfernte_originale(self):
        vorher = ap.ordner_befund(str(self.app0))
        self._originale_entfernen()
        nachher = ap.ordner_befund(str(self.app0))
        self.assertEqual(vorher["gepackt"], nachher["fehlende_gepackte"])
        self.assertEqual(vorher["gepackt_bytes"], nachher["fehlende_gepackte_bytes"])

    def test_platzbedarf_in_ordner_kleiner_als_neuer_ordner(self):
        self._originale_entfernen()
        befund = ap.ordner_befund(str(self.app0))
        im_ordner = ap.entpack_platzbedarf(befund, in_ordner=True)
        neu = ap.entpack_platzbedarf(befund, in_ordner=False)
        self.assertGreaterEqual(im_ordner, befund["fehlende_gepackte_bytes"])
        self.assertGreaterEqual(neu, befund["gesamt_bytes"])
        self.assertGreaterEqual(neu, im_ordner)

    # -- pruefen -----------------------------------------------------------
    def test_pruefen_besteht_und_zaehlt(self):
        ergebnis = ap.ordner_pruefen(str(self.app0))
        self.assertGreaterEqual(int(ergebnis["files"]), 4)
        self.assertGreater(int(ergebnis["raw_bytes"]), int(ergebnis["stored_bytes"]))

    def test_pruefen_nach_dem_entfernen_der_originale(self):
        """Dann gibt es nichts zu vergleichen - die ``.crc`` ist der Massstab."""
        self._originale_entfernen()
        self.assertGreaterEqual(int(ap.ordner_pruefen(str(self.app0))["files"]), 4)

    def test_pruefen_ohne_crc_meldet_es(self):
        os.remove(self.app0 / ap.PRUEFSUMMEN_NAME)
        with self.assertRaises(ap.PackFehler) as ctx:
            ap.ordner_pruefen(str(self.app0))
        self.assertEqual("ampr_pack.crc_fehlt", str(ctx.exception))

    def test_pruefen_findet_ein_beschaedigtes_band(self):
        """Gegenprobe: Eine Pruefung, die nie fehlschlaegt, misst nichts."""
        band = next(n for n in self._pack_namen() if n.endswith(".pak"))
        pfad = self.app0 / band
        roh = bytearray(pfad.read_bytes())
        for i in range(len(roh) // 2, min(len(roh), len(roh) // 2 + 64)):
            roh[i] ^= 0xFF
        pfad.write_bytes(bytes(roh))
        with self.assertRaises(ap.PackFehler):
            ap.ordner_pruefen(str(self.app0))

    def test_pruefen_ohne_manifest(self):
        with self.assertRaises(ap.PackFehler) as ctx:
            ap.ordner_pruefen(str(self.wurzel))
        self.assertEqual("ampr_pack.kein_manifest", str(ctx.exception))

    # -- entpacken in einen neuen Ordner ---------------------------------------
    def test_neuer_ordner_enthaelt_das_ganze_spiel_ohne_bestand(self):
        self._originale_entfernen()
        ziel = self.wurzel / "lose"
        ergebnis = ap.entpacken_in_neuen_ordner(str(self.app0), str(ziel))
        self.assertGreaterEqual(int(ergebnis["files"]), 4)
        pack = {n.lower() for n in self._pack_namen()}
        erwartet = {rel for rel in self.original
                    if rel not in ("ampr_emu.index",)}
        gefunden = {p.relative_to(ziel).as_posix(): p.read_bytes()
                    for p in ziel.rglob("*") if p.is_file()}
        for rel in erwartet:
            self.assertIn(rel, gefunden, rel + " fehlt im entpackten Spiel")
            self.assertEqual(self.original[rel], gefunden[rel], rel + " weicht ab")
        for name in gefunden:
            self.assertNotIn(name.lower(), pack, "Packbestand im Ergebnis: " + name)
        # Der Quellordner bleibt unveraendert (Bestand und Luecken).
        self.assertTrue((self.app0 / ap.MANIFEST_NAME).is_file())
        self.assertFalse((self.app0 / "assets" / "t0.bin").exists())

    def test_neuer_ordner_kopiert_keine_doppelten_originale(self):
        """Liegen die Originale noch da, kommen sie aus den Baendern - nicht doppelt."""
        ziel = self.wurzel / "lose"
        ap.entpacken_in_neuen_ordner(str(self.app0), str(ziel))
        for rel, inhalt in self.original.items():
            if rel == "ampr_emu.index":
                continue
            self.assertEqual(inhalt, (ziel / rel).read_bytes(), rel)

    def test_nicht_leeres_ziel_wird_abgelehnt(self):
        ziel = self.wurzel / "belegt"
        ziel.mkdir()
        (ziel / "fremd.txt").write_text("nicht anfassen")
        with self.assertRaises(ap.PackFehler) as ctx:
            ap.entpacken_in_neuen_ordner(str(self.app0), str(ziel))
        self.assertEqual("ampr_pack.ziel_nicht_leer", str(ctx.exception))
        self.assertEqual(["fremd.txt"], os.listdir(ziel))

    def test_ziel_im_spielordner_wird_abgelehnt(self):
        for ziel in (self.app0, self.app0 / "neu"):
            with self.subTest(ziel=str(ziel)):
                with self.assertRaises(ap.PackFehler) as ctx:
                    ap.entpacken_in_neuen_ordner(str(self.app0), str(ziel))
                self.assertEqual("ampr_pack.ziel_im_quellordner", str(ctx.exception))
        self.assertFalse((self.app0 / "neu").exists())

    def test_abbruch_raeumt_das_ziel_weg(self):
        ziel = self.wurzel / "lose"
        with self.assertRaises(ap.PackFehler) as ctx:
            ap.entpacken_in_neuen_ordner(str(self.app0), str(ziel), abbruch=lambda: True)
        self.assertEqual("ampr_pack.abgebrochen", str(ctx.exception))
        self.assertFalse(ziel.exists(), "Ein halber Ordner bleibt nicht zurueck")

    def test_abbruch_leert_ein_vorhandenes_leeres_ziel_wieder(self):
        ziel = self.wurzel / "lose"
        ziel.mkdir()
        with self.assertRaises(ap.PackFehler):
            ap.entpacken_in_neuen_ordner(str(self.app0), str(ziel), abbruch=lambda: True)
        self.assertTrue(ziel.is_dir())
        self.assertEqual([], os.listdir(ziel))

    # -- entpacken in den Spielordner ------------------------------------------
    def test_in_den_spielordner_stellt_alles_her_und_loescht_den_bestand(self):
        self._originale_entfernen()
        bestand = self._pack_namen()
        ergebnis = ap.entpacken_in_ordner(str(self.app0))
        self.assertGreaterEqual(int(ergebnis["files"]), 4)
        self.assertEqual(len(bestand), ergebnis["entfernt"])
        for name in bestand:
            self.assertFalse((self.app0 / name).exists(), name + " blieb liegen")
        for rel, inhalt in self.original.items():
            self.assertEqual(inhalt, (self.app0 / rel).read_bytes(), rel)
        self.assertEqual("", ap.manifest_im_ordner(str(self.app0)))

    def test_in_den_spielordner_mit_vorhandenen_originalen(self):
        ap.entpacken_in_ordner(str(self.app0))
        for rel, inhalt in self.original.items():
            self.assertEqual(inhalt, (self.app0 / rel).read_bytes(), rel)

    def test_fehlendes_band_haelt_alles_an(self):
        """Fehlt ein Band, wird nichts ausgepackt und nichts geloescht."""
        band = next(n for n in sorted(self._pack_namen()) if n.endswith(".pak"))
        os.remove(self.app0 / band)
        vorher = sorted(os.listdir(self.app0))
        with self.assertRaises(ap.PackFehler) as ctx:
            ap.entpacken_in_ordner(str(self.app0))
        self.assertEqual("ampr_pack.baender_fehlen", str(ctx.exception))
        self.assertEqual(vorher, sorted(os.listdir(self.app0)))

    def test_abbruch_im_spielordner_laesst_den_bestand_stehen(self):
        self._originale_entfernen()
        with self.assertRaises(ap.PackFehler):
            ap.entpacken_in_ordner(str(self.app0), abbruch=lambda: True)
        for name in self._pack_namen():
            self.assertTrue((self.app0 / name).exists(),
                            "Nach einem Abbruch muss der ganze Satz noch da sein")


class MeldungenTests(unittest.TestCase):
    """Alle neuen Texte gibt es auf Deutsch und Englisch, mit gleichen Platzhaltern."""

    NEU = [k for k in STRINGS if k.startswith(("assetpack_tool.", "settings_dialog.lz4_"))
           or k in ("titlebar.asset_pack", "ampr_pack.stufe_hc", "ampr_pack.stufe_schnell",
                    "ampr_pack.leere_zurueck", "ampr_pack.kein_manifest",
                    "ampr_pack.crc_fehlt", "ampr_pack.baender_fehlen",
                    "ampr_pack.entpacken_unvollstaendig", "ampr_pack.ziel_nicht_leer",
                    "ampr_pack.ziel_im_quellordner", "ampr_pack.entpacken_kopiert",
                    "ampr_pack.bestand_bleibt")]

    def test_es_gibt_neue_texte(self):
        self.assertGreater(len(self.NEU), 50)

    def test_beide_sprachen_und_gleiche_platzhalter(self):
        import re
        muster = re.compile(r"\{(\w+)\}")
        for schluessel in self.NEU:
            with self.subTest(schluessel=schluessel):
                eintrag = STRINGS[schluessel]
                self.assertTrue(eintrag.get("de"), "de fehlt")
                self.assertTrue(eintrag.get("en"), "en fehlt")
                self.assertEqual(set(muster.findall(eintrag["de"])),
                                 set(muster.findall(eintrag["en"])))

    def test_fehlerschluessel_des_moduls_gibt_es(self):
        """Jede ``PackFehler("ampr_pack....")`` des Moduls braucht einen Text."""
        import re
        quelle = (PROJEKT / "ps5_validator" / "utils" / "ampr_assetpakete.py").read_text(
            encoding="utf-8")
        for schluessel in set(re.findall(r'PackFehler\("(ampr_pack\.[a-z_]+)"\)', quelle)):
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)


# ---------------------------------------------------------------------------
# 5. Das Fenster
# ---------------------------------------------------------------------------
def _schleife(grenze: float, bis=None) -> None:
    """Eine echte Hauptschleife fuer hoechstens ``grenze`` Sekunden."""
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if (bis is not None and bis()) or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(10, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()


def _widgets(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _widgets(kind)


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.haupt = _lade_hauptprogramm()
        cls.app = cls.haupt.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def _oeffnen(self):
        vorher = set(_WURZEL.winfo_children())
        self.app._show_asset_pack_werkzeug()
        _WURZEL.update_idletasks()
        neu = [w for w in _WURZEL.winfo_children()
               if w not in vorher and isinstance(w, tk.Toplevel)]
        self.assertTrue(neu, "Kein Fenster geoeffnet.")
        fenster = neu[0]
        self.addCleanup(self._schliessen, fenster)
        return fenster

    def _schliessen(self, fenster):
        try:
            if fenster.winfo_exists():
                fenster.destroy()
        except tk.TclError:
            pass
        self.app._asset_pack_win = None

    def _knopf(self, fenster, schluessel):
        text = self.app._t(schluessel)
        for w in _widgets(fenster):
            try:
                if str(w.cget("text")) == text:
                    return w
            except tk.TclError:
                continue
        self.fail("Knopf fehlt: " + text)

    def _protokoll(self, fenster) -> str:
        for w in _widgets(fenster):
            if w.winfo_class() == "Text":
                return w.get("1.0", "end")
        self.fail("Kein Protokollfeld")

    def _fertig(self, fenster, grenze=60.0):
        pruefen = self._knopf(fenster, "assetpack_tool.check_button")
        _schleife(grenze, bis=lambda: str(pruefen.cget("state")) == "normal")
        self.assertEqual("normal", str(pruefen.cget("state")), "Der Lauf endete nicht")

    def _spiel(self, basis: Path) -> Path:
        """Ein gepackter Spielordner, ohne Tk."""
        app0 = basis / "app0"
        (app0 / "assets").mkdir(parents=True)
        for i in range(3):
            (app0 / "assets" / ("t%d.bin" % i)).write_bytes(
                ((b"ABCDEFGH" * 512) + bytes([i])) * 24)
        (app0 / "eboot.bin").write_bytes(b"\x7fELF" + b"\x00" * 2048)
        index = _index_bauen(app0)
        raus = basis / "packed"
        profil = ap.profil_schreiben(str(basis / "profil.toml"), app0=str(app0))
        ap.packen(str(app0), str(index), str(raus), profil)
        baender = ap.bandnamen(ap.uebersicht(str(raus / ap.MANIFEST_NAME)))
        ap.bestand_uebernehmen(str(raus), str(app0), baender=baender)
        ap.bestand_aufraeumen(str(raus), baender, ganz=True)
        return app0

    def test_eintrag_im_werkzeugmenue(self):
        self.assertIn(("titlebar.asset_pack", "_show_asset_pack_werkzeug"),
                      self.haupt.PS5ConverterGUI._MORE_TOOLS_ENTRIES)

    def test_fenster_oeffnet_mit_beiden_knoepfen(self):
        fenster = self._oeffnen()
        self.assertEqual(self.app._t("assetpack_tool.window_title"), fenster.title())
        self.assertEqual("normal", str(self._knopf(
            fenster, "assetpack_tool.check_button").cget("state")))
        self.assertEqual("disabled", str(self._knopf(
            fenster, "assetpack_tool.cancel_button").cget("state")))

    def test_zweiter_aufruf_holt_dasselbe_fenster(self):
        fenster = self._oeffnen()
        vorher = len([w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)])
        self.app._show_asset_pack_werkzeug()
        nachher = len([w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)])
        self.assertEqual(vorher, nachher)
        self.assertTrue(fenster.winfo_exists())

    def test_ohne_ordner_wird_gewarnt_und_nichts_gestartet(self):
        fenster = self._oeffnen()
        with mock.patch.object(self.haupt.messagebox, "showwarning") as warnung:
            self._knopf(fenster, "assetpack_tool.check_button").invoke()
        self.assertEqual(1, warnung.call_count)
        self.assertIn(self.app._t("assetpack_tool.msg_choose_folder"),
                      warnung.call_args[0])

    def test_ordner_ohne_asset_pack_wird_abgewiesen(self):
        fenster = self._oeffnen()
        with tempfile.TemporaryDirectory() as leer:
            entry = next(w for w in _widgets(fenster) if w.winfo_class() in ("Entry", "TEntry"))
            entry.delete(0, "end")
            entry.insert(0, leer)
            with mock.patch.object(self.haupt.messagebox, "showwarning") as warnung:
                self._knopf(fenster, "assetpack_tool.check_button").invoke()
        self.assertEqual(1, warnung.call_count)
        self.assertIn(self.app._t("assetpack_tool.msg_no_pack"), warnung.call_args[0])

    @unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
    def test_pruefen_laeuft_bis_zum_ergebnis(self):
        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            app0 = self._spiel(Path(basis))
            fenster = self._oeffnen()
            with mock.patch.object(self.haupt.filedialog, "askdirectory",
                                   return_value=str(app0)):
                self._knopf(fenster, "action.browse").invoke()
            self._fertig(fenster)
            self._knopf(fenster, "assetpack_tool.check_button").invoke()
            self._fertig(fenster)
            text = self._protokoll(fenster)
            self.assertIn("Prüfung bestanden", text)
            self.assertIn("Laufzeit", text, "Die Laufzeit-Aussage fehlt")
            self.assertIn("fakelib/libSceAmpr.sprx fehlt", text,
                          "Der Testbaum hat keine Bibliothek - das muss als Hinweis erscheinen")
            self.assertNotIn("[FEHLER]", text)

    @unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
    def test_entpacken_in_einen_neuen_ordner(self):
        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            app0 = self._spiel(Path(basis))
            ziel = Path(basis) / "lose"
            fenster = self._oeffnen()
            with mock.patch.object(self.haupt.filedialog, "askdirectory",
                                   side_effect=[str(app0), str(ziel)]), \
                    mock.patch.object(self.haupt.messagebox, "askyesnocancel",
                                      return_value=True):
                self._knopf(fenster, "action.browse").invoke()
                self._fertig(fenster)
                self._knopf(fenster, "assetpack_tool.unpack_button").invoke()
                self._fertig(fenster)
            text = self._protokoll(fenster)
            self.assertNotIn("[FEHLER]", text)
            self.assertTrue((ziel / "assets" / "t0.bin").is_file())
            self.assertFalse((ziel / ap.MANIFEST_NAME).exists())
            self.assertTrue((app0 / ap.MANIFEST_NAME).is_file(),
                            "Der Quellordner bleibt unveraendert")

    @unittest.skipUnless(ap.einsatzbereit()[0], "Packwerkzeug oder lz4 fehlt")
    def test_abbrechen_der_frage_aendert_nichts(self):
        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            app0 = self._spiel(Path(basis))
            vorher = sorted(os.listdir(app0))
            fenster = self._oeffnen()
            entry = next(w for w in _widgets(fenster) if w.winfo_class() in ("Entry", "TEntry"))
            entry.delete(0, "end")
            entry.insert(0, str(app0))
            with mock.patch.object(self.haupt.messagebox, "askyesnocancel", return_value=None):
                self._knopf(fenster, "assetpack_tool.unpack_button").invoke()
            self.assertEqual(vorher, sorted(os.listdir(app0)))

    def test_in_den_spielordner_fragt_vorher_nach(self):
        """Das Loeschen von Manifest und Baendern ist nicht rueckgaengig zu machen."""
        with tempfile.TemporaryDirectory(prefix="ampr_pack_test_") as basis:
            if not ap.einsatzbereit()[0]:
                self.skipTest("Packwerkzeug oder lz4 fehlt")
            app0 = self._spiel(Path(basis))
            vorher = sorted(os.listdir(app0))
            fenster = self._oeffnen()
            entry = next(w for w in _widgets(fenster) if w.winfo_class() in ("Entry", "TEntry"))
            entry.delete(0, "end")
            entry.insert(0, str(app0))
            with mock.patch.object(self.haupt.messagebox, "askyesnocancel", return_value=False), \
                    mock.patch.object(self.haupt.messagebox, "askyesno",
                                      return_value=False) as frage:
                self._knopf(fenster, "assetpack_tool.unpack_button").invoke()
            self.assertEqual(1, frage.call_count, "Die Sicherheitsfrage fehlt")
            self.assertEqual(vorher, sorted(os.listdir(app0)), "Nach Nein bleibt alles stehen")

    def test_schliessen_mitten_im_lauf_fragt_und_bricht_ab(self):
        fenster = self._oeffnen()
        handler = fenster.protocol("WM_DELETE_WINDOW")
        self.assertTrue(handler, "Ohne Handler lief ein Lauf nach dem Schliessen weiter")
        # Ohne Lauf schliesst es ohne Rueckfrage.
        with mock.patch.object(self.haupt.messagebox, "askyesno") as frage:
            fenster.tk.call(handler)
        self.assertEqual(0, frage.call_count)
        self.assertFalse(fenster.winfo_exists())


if __name__ == "__main__":
    unittest.main()
