# -*- coding: utf-8 -*-
"""Vorabpruefung vor dem Start: alle Befunde auf einmal (nach Dump Forge, Nutzerwahl 13.11.2026)."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("vorabpruefung")

from mkpfs.utils import is_ignored_name                      # noqa: E402

from ps5_validator.utils import vorabpruefung as vp          # noqa: E402


def _lade():
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", ROOT / "PS5ImageConverter_Pro_FINAL_revised.py")
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


HAUPT = _lade()
GUI = HAUPT.PS5ConverterGUI


def _abtastung(dateien=(), ordner=(), verweise=()):
    a = vp.Abtastung(dateien=[(p, 1) for p in dateien], ordner=list(ordner), verweise=list(verweise))
    a.gesamt = len(a.dateien)
    return a


def _arten(befunde):
    return {b.art: b.schwere for b in befunde}


class ScanTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name) / "Spiel"
        (self.q / "sce_sys").mkdir(parents=True)
        (self.q / "eboot.bin").write_bytes(b"x" * 100)
        (self.q / "sce_sys" / "param.json").write_bytes(b"{}")
        (self.q / "data").mkdir()
        (self.q / "data" / "gross.bin").write_bytes(b"y" * 5000)

    def test_scan_zaehlt_dateien_ordner_und_groessen(self):
        a = vp.scan(str(self.q))
        self.assertEqual({"eboot.bin", "sce_sys/param.json", "data/gross.bin"}, {r for r, _ in a.dateien})
        self.assertEqual({"sce_sys", "data"}, set(a.ordner))
        self.assertEqual(5102, a.gesamt)
        self.assertEqual(5000, a.groesste)
        self.assertTrue(a.vollstaendig)

    def test_was_der_schreiber_weglaesst_zaehlt_nicht(self):
        (self.q / "desktop.ini").write_bytes(b"1")
        (self.q / "__MACOSX").mkdir()
        (self.q / "__MACOSX" / "x.bin").write_bytes(b"2")
        a = vp.scan(str(self.q), ignoriert=is_ignored_name)
        self.assertNotIn("desktop.ini", {r for r, _ in a.dateien})
        self.assertNotIn("__MACOSX", a.ordner)
        self.assertNotIn("__MACOSX/x.bin", {r for r, _ in a.dateien})

    def test_eine_verknuepfung_wird_gemeldet_und_nicht_verfolgt(self):
        ziel = self.q / "data" / "gross.bin"
        link = self.q / "verweis.bin"
        try:
            os.symlink(ziel, link)
        except (OSError, NotImplementedError):
            self.skipTest("keine Rechte fuer symbolische Verknuepfungen")
        a = vp.scan(str(self.q))
        self.assertEqual(["verweis.bin"], a.verweise)
        self.assertNotIn("verweis.bin", {r for r, _ in a.dateien})

    def test_die_zeitgrenze_beendet_die_probe_als_unvollstaendig(self):
        for i in range(600):
            (self.q / "data" / ("f%03d.bin" % i)).write_bytes(b"z")
        a = vp.scan(str(self.q), zeitgrenze=1e-9)
        self.assertFalse(a.vollstaendig)

    def test_der_abbruch_beendet_die_probe(self):
        for i in range(600):
            (self.q / "data" / ("f%03d.bin" % i)).write_bytes(b"z")
        self.assertFalse(vp.scan(str(self.q), laeuft=lambda: False).vollstaendig)

    def test_ein_fehlender_ordner_ergibt_eine_leere_probe(self):
        a = vp.scan(str(self.q / "gibt_es_nicht"))
        self.assertEqual([], a.dateien)

    def test_die_echte_nicht_ascii_quelle_lehnt_der_schreiber_ab_wie_die_pruefung(self):
        """Wächter: Die Pruefung meldet, was ``mkpfs.exfat_writer`` sonst erst nach dem Kopieren ablehnt."""
        from mkpfs.exfat_writer import ExfatBuildError, iter_exfat_image
        (self.q / "data" / "Café.bin").write_bytes(b"c")
        a = vp.scan(str(self.q))
        self.assertIn("nicht_ascii", _arten(vp.quellbefunde(a, "exfat")))
        with self.assertRaises(ExfatBuildError):
            next(iter(iter_exfat_image(self.q)))


class QuellbefundeTests(unittest.TestCase):
    def test_ein_sauberer_baum_hat_keine_befunde(self):
        a = _abtastung(["eboot.bin", "sce_sys/param.json", "data/a.bin"], ["sce_sys", "data"])
        for fmt in vp.ABBILD_FORMATE:
            self.assertEqual([], vp.quellbefunde(a, fmt), fmt)

    def test_ein_ordner_als_ziel_hat_nichts_zu_sagen(self):
        a = _abtastung(["Café.bin", "a.bin", "A.bin"])
        self.assertEqual([], vp.quellbefunde(a, "folder"))
        self.assertEqual([], vp.quellbefunde(a, "pkg"))

    def test_nicht_ascii_ist_bei_exfat_ein_fehler_sonst_eine_warnung(self):
        a = _abtastung(["data/Café.bin"])
        self.assertEqual("fehler", _arten(vp.quellbefunde(a, "exfat"))["nicht_ascii"])
        for fmt in ("ffpkg", "ffpfs", "ffpfsc"):
            self.assertEqual("warnung", _arten(vp.quellbefunde(a, fmt))["nicht_ascii"], fmt)

    def test_ein_nicht_ascii_ordner_zaehlt_mit(self):
        b = vp.quellbefunde(_abtastung(["x.bin"], ["Ünter"]), "exfat")
        self.assertEqual(["Ünter"], b[0].eintraege)

    def test_verknuepfungen_nur_bei_exfat_und_als_fehler(self):
        a = _abtastung(["a.bin"], verweise=["l.bin"])
        self.assertEqual("fehler", _arten(vp.quellbefunde(a, "exfat"))["verweis"])
        self.assertNotIn("verweis", _arten(vp.quellbefunde(a, "ffpkg")))

    def test_verbotene_zeichen_in_exfat(self):
        a = _abtastung(["data/was?.bin", "ok.bin", "ordner/a:b", "steuer\x01.bin"])
        b = [x for x in vp.quellbefunde(a, "exfat") if x.art == "zeichen"][0]
        self.assertEqual("fehler", b.schwere)
        self.assertEqual({"data/was?.bin", "ordner/a:b", "steuer\x01.bin"}, set(b.eintraege))
        self.assertNotIn("zeichen", _arten(vp.quellbefunde(a, "ffpkg")))

    def test_der_pfadtrenner_zaehlt_nicht_als_verbotenes_zeichen(self):
        self.assertNotIn("zeichen", _arten(vp.quellbefunde(_abtastung(["a/b/c.bin"], ["a", "a/b"]), "exfat")))

    def test_gross_klein_kollisionen_werden_gefunden(self):
        a = _abtastung(["data/Textur.bin", "data/textur.bin", "andere.bin"])
        b = [x for x in vp.quellbefunde(a, "exfat") if x.art == "kollision"][0]
        self.assertEqual("fehler", b.schwere)
        self.assertEqual({"data/Textur.bin", "data/textur.bin"}, set(b.eintraege))
        self.assertEqual("warnung", _arten(vp.quellbefunde(a, "ffpfs"))["kollision"])

    def test_gleicher_name_in_verschiedenen_ordnern_ist_keine_kollision(self):
        a = _abtastung(["a/x.bin", "b/X.bin"])
        self.assertNotIn("kollision", _arten(vp.quellbefunde(a, "exfat")))

    def test_die_tiefe_wird_an_der_grenze_geprueft(self):
        ok = "/".join(["d"] * vp.TIEFE_MAX) + "/f.bin"          # 32 Ordner, dann die Datei: erlaubt
        zu_tief = "/".join(["d"] * (vp.TIEFE_MAX + 1)) + "/f.bin"
        self.assertNotIn("tiefe", _arten(vp.quellbefunde(_abtastung([ok]), "exfat")))
        b = [x for x in vp.quellbefunde(_abtastung([zu_tief]), "exfat") if x.art == "tiefe"][0]
        self.assertEqual("warnung", b.schwere)
        self.assertEqual([zu_tief], b.eintraege)

    def test_ein_zu_tiefer_leerer_ordner_zaehlt(self):
        ordner = "/".join(["d"] * (vp.TIEFE_MAX + 1))
        self.assertIn("tiefe", _arten(vp.quellbefunde(_abtastung([], [ordner]), "ffpkg")))
        self.assertNotIn("tiefe", _arten(vp.quellbefunde(_abtastung([], ["/".join(["d"] * vp.TIEFE_MAX)]), "ffpkg")))

    def test_die_liste_ist_gekuerzt_und_zaehlt_den_rest(self):
        a = _abtastung(["n%04d.bin" % i for i in range(vp.LISTE_MAX + 37)] + ["x\xe9.bin"])
        a.dateien = [("é%04d.bin" % i, 1) for i in range(vp.LISTE_MAX + 37)]
        b = vp.quellbefunde(a, "exfat")[0]
        self.assertEqual(vp.LISTE_MAX, len(b.eintraege))
        self.assertEqual(37, b.mehr)
        self.assertEqual(vp.LISTE_MAX + 37, b.anzahl)


class AusgabenameTests(unittest.TestCase):
    def test_die_grenzen(self):
        self.assertEqual(63, vp.name_max("exfat"))
        self.assertEqual(63, vp.name_max("ffpkg"))
        self.assertEqual(63, vp.name_max("ffpfs"))
        self.assertEqual(58, vp.name_max("ffpfsc"))

    def test_ein_name_an_der_grenze_besteht_einer_darueber_nicht(self):
        self.assertIsNone(vp.ausgabename_befund("a" * 63, "exfat"))
        b = vp.ausgabename_befund("a" * 64, "exfat")
        self.assertEqual("warnung", b.schwere)
        self.assertEqual(64, b.zusatz["laenge"])
        self.assertIsNone(vp.ausgabename_befund("a" * 58, "ffpfsc"))
        self.assertIsNotNone(vp.ausgabename_befund("a" * 59, "ffpfsc"))

    def test_gezaehlt_werden_bytes_nicht_zeichen(self):
        self.assertIsNone(vp.ausgabename_befund("\u00e9" * 31, "exfat"))       # 62 Bytes
        self.assertIsNotNone(vp.ausgabename_befund("\u00e9" * 32, "exfat"))    # 64 Bytes

    def test_ordner_und_pkg_haben_keine_grenze(self):
        self.assertIsNone(vp.ausgabename_befund("a" * 200, "folder"))
        self.assertIsNone(vp.ausgabename_befund("a" * 200, "pkg"))


class Fat32Tests(unittest.TestCase):
    GIB = 1 << 30

    def test_ein_abbild_ueber_4_gib_passt_nicht_auf_fat32(self):
        b = vp.fat32_befund("FAT32", "exfat", 10 * self.GIB, 2 * self.GIB, "E:\\")
        self.assertEqual("fehler", b.schwere)
        self.assertEqual(10 * self.GIB, b.zusatz["noetig"])

    def test_ein_ordner_zaehlt_die_groesste_datei(self):
        self.assertIsNone(vp.fat32_befund("FAT32", "folder", 100 * self.GIB, 3 * self.GIB))
        self.assertIsNotNone(vp.fat32_befund("FAT32", "folder", 100 * self.GIB, 5 * self.GIB))

    def test_exfat_und_ntfs_haben_die_grenze_nicht(self):
        for fs in ("exFAT", "NTFS", "ext4", ""):
            self.assertIsNone(vp.fat32_befund(fs, "exfat", 100 * self.GIB, 50 * self.GIB), fs)

    def test_die_grenze_selbst_ist_noch_erlaubt(self):
        self.assertIsNone(vp.fat32_befund("FAT32", "exfat", vp.FAT32_DATEI_MAX, vp.FAT32_DATEI_MAX))
        self.assertIsNotNone(vp.fat32_befund("FAT32", "exfat", vp.FAT32_DATEI_MAX + 1, 1))

    def test_ein_ffpfsc_wird_nicht_beurteilt(self):
        self.assertIsNone(vp.fat32_befund("FAT32", "ffpfsc", 100 * self.GIB, 50 * self.GIB))


class VerdrahtungTests(unittest.TestCase):
    """``_vorab_befunde`` im Hauptprogramm: Texte, Schwere, Protokoll."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name) / "Spiel"
        (self.q / "sce_sys").mkdir(parents=True)
        (self.q / "eboot.bin").write_bytes(b"x" * 10)
        (self.q / "sce_sys" / "param.json").write_bytes(b"{}")
        self.dst = Path(self._tmp.name) / "Ziel"
        self.dst.mkdir()
        self.app = GUI.__new__(GUI)
        self.log: list[str] = []
        self.app._append_to_log = self.log.append
        self.app._t = lambda k, **w: k + " " + " ".join("%s=%s" % kv for kv in sorted(w.items()))
        self.app._fmt_bytes = lambda n: "%d B" % n
        self.app._extract_embedded_mkpfs = lambda: str(ROOT / "MkPFS-1.1.0")

    def _lauf(self, mode="pack_folder", fmt="exfat", src=None):
        return self.app._vorab_befunde(mode, str(src or self.q), str(self.dst), fmt)

    def test_ein_sauberer_spielordner_hat_keine_befunde(self):
        self.assertEqual(([], []), self._lauf())

    def test_nicht_ascii_ist_bei_exfat_ein_fehler_und_steht_im_protokoll(self):
        (self.q / "Café.bin").write_bytes(b"c")
        fehler, warnungen = self._lauf()
        self.assertEqual(1, len(fehler))
        self.assertIn("preflight.vorab_nicht_ascii", fehler[0])
        self.assertIn("n=1", fehler[0])
        self.app._vorab_log_ausgeben()
        self.assertTrue(any("Café.bin" in z for z in self.log), self.log)
        self.assertTrue(any("vorab_liste_kopf" in z for z in self.log))

    def test_bei_ffpkg_ist_derselbe_befund_eine_warnung(self):
        (self.q / "Café.bin").write_bytes(b"c")
        fehler, warnungen = self._lauf(fmt="ffpkg")
        self.assertEqual([], fehler)
        self.assertEqual(1, len(warnungen))

    def test_alle_befunde_kommen_zugleich(self):
        (self.q / "Café.bin").write_bytes(b"c")
        tief = self.q
        for _ in range(vp.TIEFE_MAX + 1):
            tief = tief / "d"
        tief.mkdir(parents=True)
        (tief / "f.bin").write_bytes(b"t")
        fehler, warnungen = self._lauf()
        self.assertEqual(1, len(fehler))
        self.assertEqual(1, len(warnungen))
        self.assertIn("preflight.vorab_tiefe", warnungen[0])

    def test_ein_langer_ordnername_wird_gemeldet(self):
        lang = Path(self._tmp.name) / ("S" * 70)
        (lang / "sce_sys").mkdir(parents=True)
        fehler, warnungen = self._lauf(src=lang)
        self.assertEqual([], fehler)
        self.assertTrue(any("vorab_name_lang" in w and "laenge=70" in w for w in warnungen), warnungen)

    def test_bei_einer_datei_zaehlt_der_name_ohne_endung(self):
        datei = Path(self._tmp.name) / (("S" * 63) + ".ffpfsc")
        datei.write_bytes(b"x")
        _fehler, warnungen = self._lauf(mode="pack_file", fmt="ffpfsc", src=datei)
        self.assertTrue(any("vorab_name_lang" in w for w in warnungen), "63 Bytes sind bei .ffpfsc schon zu lang (58)")
        _fehler, warnungen = self._lauf(mode="pack_file", fmt="exfat", src=datei)
        self.assertEqual([], warnungen)

    def test_die_sammelkonvertierung_prueft_die_namen_aller_quellen(self):
        lang = Path(self._tmp.name) / ("L" * 70)
        lang.mkdir()
        self.app._batch_sources = [str(self.q), str(lang)]
        _fehler, warnungen = self._lauf(mode="batch_convert")
        self.assertEqual(1, len(warnungen))
        self.assertIn("laenge=70", warnungen[0])

    def test_fat32_im_ziel_wird_gemeldet(self):
        (self.q / "gross.bin").write_bytes(b"g")
        with mock.patch.object(HAUPT, "_doktor_dateisystem", lambda _pfad: "FAT32"), \
                mock.patch.object(vp, "FAT32_DATEI_MAX", 0):
            fehler, _warnungen = self._lauf()
        self.assertTrue(any("vorab_fat32" in f for f in fehler), fehler)

    def test_andere_aufgaben_und_zielformate_bleiben_unberuehrt(self):
        (self.q / "Café.bin").write_bytes(b"c")
        self.assertEqual(([], []), self._lauf(mode="inspect"))
        self.assertEqual(([], []), self._lauf(fmt="folder"))
        self.assertEqual(([], []), self._lauf(fmt=""))

    def test_ein_fehler_in_der_probe_verhindert_den_start_nicht(self):
        with mock.patch.object(vp, "scan", side_effect=RuntimeError("kaputt")):
            self.assertEqual(([], []), self._lauf())

    def test_eine_unvollstaendige_probe_rechnet_fuer_ein_abbild_mit_der_bekannten_groesse(self):
        """Nach der Zeitgrenze fehlt ein Teil der Ordner; die Datei ueber 4 GiB koennte dort liegen: Fuer ein Abbild zaehlt die Gesamtgroesse."""
        original = vp.scan

        def kurz(*a, **kw):
            erg = original(*a, **kw)
            erg.vollstaendig = False
            return erg
        self.app._quellgroesse_ermitteln = lambda src: 10 * 1024 ** 3
        with mock.patch.object(vp, "scan", kurz), mock.patch.object(HAUPT, "_doktor_dateisystem", lambda _pfad: "FAT32"):
            fehler, _w = self._lauf(fmt="exfat")
            fehler_ordner, _w2 = self._lauf(fmt="folder")
        self.assertTrue(any("vorab_fat32" in f for f in fehler), fehler)
        self.assertEqual([], fehler_ordner, "fuer einen Ordner zaehlt die groesste Datei, und die kennt die Probe nicht")

    def test_eine_vollstaendige_probe_nimmt_die_bekannte_groesse_nicht(self):
        self.app._quellgroesse_ermitteln = lambda src: 10 * 1024 ** 3
        with mock.patch.object(HAUPT, "_doktor_dateisystem", lambda _pfad: "FAT32"):
            fehler, _w = self._lauf(fmt="exfat")
        self.assertEqual([], fehler)

    def test_die_namensprobe_haelt_den_hauptfaden_nicht_lange_an(self):
        self.assertLessEqual(GUI._VORAB_ZEIT, 10.0)

    def test_aus_einer_abbilddatei_in_einen_ordner_gibt_es_keinen_fat32_befund(self):
        """Die Groesse der Abbilddatei sagt nichts ueber die groesste Datei darin: Dateien im Ordner sind einzeln kleiner."""
        datei = Path(self._tmp.name) / "Spiel.exfat"
        datei.write_bytes(b"x")
        echt = os.path.getsize
        gross = lambda p: 10 * 1024 ** 3 if str(p) == str(datei) else echt(p)          # noqa: E731
        with mock.patch.object(HAUPT, "_doktor_dateisystem", lambda _pfad: "FAT32"), mock.patch("os.path.getsize", gross):
            fehler_abbild, _w = self._lauf(mode="pack_file", fmt="exfat", src=datei)
            fehler_ordner, _w2 = self._lauf(mode="pack_file", fmt="folder", src=datei)
        self.assertTrue(any("vorab_fat32" in f for f in fehler_abbild), "Gegenprobe: ein Abbild ueber 4 GiB passt nicht auf FAT32")
        self.assertEqual([], fehler_ordner)

    def test_die_unvollstaendige_probe_steht_im_protokoll(self):
        original = vp.scan

        def kurz(*a, **kw):
            erg = original(*a, **kw)
            erg.vollstaendig = False
            return erg
        with mock.patch.object(vp, "scan", kurz):
            self._lauf()
        self.app._vorab_log_ausgeben()
        self.assertTrue(any("vorab_unvollstaendig" in z for z in self.log), self.log)

    def test_das_protokoll_wird_nur_einmal_ausgegeben(self):
        (self.q / "Café.bin").write_bytes(b"c")
        self._lauf()
        self.app._vorab_log_ausgeben()
        n = len(self.log)
        self.app._vorab_log_ausgeben()
        self.assertEqual(n, len(self.log))

    def test_der_start_ruft_die_probe_im_vorabbereich_und_gibt_das_protokoll_nach_dem_leeren_aus(self):
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        start = quelle.index("def _launch_task")
        ausschnitt = quelle[start:start + 60000]
        self.assertLess(ausschnitt.index("_run_preflight_checks("), ausschnitt.index("_vorab_log_ausgeben()"))
        self.assertLess(ausschnitt.index('self.console_view.delete("1.0", tk.END)'),
                        ausschnitt.index("_vorab_log_ausgeben()"))

    def test_die_texte_stehen_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        felder = {
            "nicht_ascii": ("n", "beispiele", "format"), "verweis": ("n", "beispiele"),
            "zeichen": ("n", "beispiele"), "kollision": ("n", "beispiele", "format"),
            "tiefe": ("n", "beispiele", "grenze", "format"),
            "name_lang": ("name", "laenge", "grenze", "format"), "fat32": ("ziel", "size"),
            "unvollstaendig": ("sekunden", "dateien"), "liste_kopf": ("art", "n"), "liste_mehr": ("n",),
        }
        for art, namen in felder.items():
            for sprache in SUPPORTED_LANGUAGES:
                text = STRINGS["preflight.vorab_" + art][sprache]
                for feld in namen:
                    self.assertIn("{%s}" % feld, text, "%s/%s" % (art, sprache))
                text.format(**{f: "x" for f in namen})                 # keine losen Klammern


if __name__ == "__main__":
    unittest.main()
