# -*- coding: utf-8 -*-
"""exFAT-Abbild mit dem eigenen Leser zurueckgelesen und gegen die Quelle verglichen (nach Dump Forge, Nutzerwahl 13.11.2026).

Dazu: Der Schreiber ist reproduzierbar - dieselbe Quelle ergibt dieselben Bytes, auch bei anderen Dateizeiten.
"""
from __future__ import annotations

import hashlib
import io
import os
import random
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("exfat_ruecklesen")

from mkpfs.exfat import ExfatReader                          # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402
from mkpfs.utils import is_ignored_name                      # noqa: E402

from ps5_validator.utils import abbild_pruefen as ap         # noqa: E402


def _baum(wurzel: Path) -> None:
    (wurzel / "sce_sys").mkdir(parents=True)
    (wurzel / "eboot.bin").write_bytes(b"ELF" * 5000)
    (wurzel / "sce_sys" / "param.json").write_bytes(b'{"titleId":"PPSA00001"}')
    for i in range(30):
        ordner = wurzel / ("d%d" % (i % 3))
        ordner.mkdir(exist_ok=True)
        (ordner / ("f%02d.bin" % i)).write_bytes(bytes([i + 1]) * (i * 997 + 1))


def _bauen(wurzel: Path) -> bytes:
    return b"".join(iter_exfat_image(wurzel, cluster_size=32 * 1024))


def _lesen(abbild: bytes, quelle: Path, **kw):
    return ap.exfat_ruecklesen(ExfatReader(io.BytesIO(abbild)), str(quelle), ignoriert=is_ignored_name,
                               zufall=random.Random(1), **kw)


class RuecklesenTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name) / "Spiel"
        _baum(self.q)
        self.abbild = _bauen(self.q)

    def test_ein_richtiges_abbild_besteht(self):
        e = _lesen(self.abbild, self.q)
        self.assertEqual(32, e["dateien"])
        self.assertEqual([], e["fehlen"] + e["zuviel"] + e["groesse"] + e["inhalt"])
        self.assertEqual(32, e["stichprobe_dateien"], "ein kleiner Titel wird ganz verglichen")

    def test_eine_nachtraeglich_hinzugekommene_quelldatei_fehlt_im_abbild(self):
        (self.q / "d0" / "neu.bin").write_bytes(b"x" * 10)
        self.assertEqual(["d0/neu.bin"], _lesen(self.abbild, self.q)["fehlen"])

    def test_eine_entfernte_quelldatei_ist_im_abbild_zuviel(self):
        os.remove(self.q / "d1" / "f01.bin")
        self.assertEqual(["d1/f01.bin"], _lesen(self.abbild, self.q)["zuviel"])

    def test_eine_andere_groesse_wird_gefunden(self):
        with (self.q / "d2" / "f02.bin").open("ab") as fh:
            fh.write(b"y")
        e = _lesen(self.abbild, self.q)
        self.assertEqual(1, len(e["groesse"]))
        self.assertIn("d2/f02.bin", e["groesse"][0])

    def test_ein_anderer_inhalt_gleicher_groesse_wird_gefunden(self):
        pfad = self.q / "d0" / "f03.bin"
        daten = bytearray(pfad.read_bytes())
        daten[len(daten) // 2] ^= 0xFF
        pfad.write_bytes(bytes(daten))
        self.assertEqual(["d0/f03.bin"], _lesen(self.abbild, self.q)["inhalt"])

    def test_ein_verdorbenes_abbild_wird_gefunden(self):
        """Ein Bit im Datenbereich der eboot.bin: der Leser liefert andere Bytes."""
        leser = ExfatReader(io.BytesIO(self.abbild))
        eintrag = next(e for e in leser.iter_files() if e.rel_path == "eboot.bin")
        offset = leser._cluster_byte_offset(eintrag.first_cluster) + 100
        kaputt = bytearray(self.abbild)
        kaputt[offset] ^= 0x01
        self.assertEqual(["eboot.bin"], _lesen(bytes(kaputt), self.q)["inhalt"])

    def test_was_der_schreiber_weglaesst_ist_kein_befund(self):
        (self.q / "desktop.ini").write_bytes(b"[x]")
        (self.q / "d0" / "Thumbs.db").write_bytes(b"t")
        (self.q / "__MACOSX").mkdir()
        (self.q / "__MACOSX" / "a.bin").write_bytes(b"m")
        e = _lesen(self.abbild, self.q)
        self.assertEqual([], e["fehlen"] + e["zuviel"])

    def test_gross_und_klein_im_namen_zaehlt_nicht_als_fehlend(self):
        os.rename(self.q / "d0" / "f00.bin", self.q / "d0" / "F00.BIN")
        e = _lesen(self.abbild, self.q)
        self.assertEqual([], e["fehlen"] + e["zuviel"])

    def test_pflichtdateien_werden_immer_verglichen(self):
        """Selbst bei Null Budget: eboot.bin und param.json sind in der Stichprobe."""
        alt = (ap.EXFAT_RUECKLESEN_MINDEST, ap.EXFAT_RUECKLESEN_ANTEIL)
        ap.EXFAT_RUECKLESEN_MINDEST, ap.EXFAT_RUECKLESEN_ANTEIL = 0, 0.0
        self.addCleanup(lambda: (setattr(ap, "EXFAT_RUECKLESEN_MINDEST", alt[0]),
                                 setattr(ap, "EXFAT_RUECKLESEN_ANTEIL", alt[1])))
        e = _lesen(self.abbild, self.q)
        self.assertEqual(2, e["stichprobe_dateien"])

    def test_das_budget_begrenzt_die_stichprobe(self):
        ap_mind = ap.EXFAT_RUECKLESEN_MINDEST
        ap.EXFAT_RUECKLESEN_MINDEST = 20_000
        self.addCleanup(lambda: setattr(ap, "EXFAT_RUECKLESEN_MINDEST", ap_mind))
        e = _lesen(self.abbild, self.q)
        self.assertLess(e["stichprobe_dateien"], 32)
        self.assertGreaterEqual(e["stichprobe_bytes"], 20_000)

    def test_ein_abbruch_beendet_die_probe(self):
        e = _lesen(self.abbild, self.q, laeuft=lambda: False)
        self.assertTrue(e["abgebrochen"])
        self.assertEqual(0, e["stichprobe_dateien"])

    def test_grosse_dateien_werden_nur_am_anfang_verglichen(self):
        gross = self.q / "gross.bin"
        n = ap.EXFAT_RUECKLESEN_GANZ_BIS + (1 << 20)
        gross.write_bytes(os.urandom(1 << 20) * (n // (1 << 20) + 1))
        os.truncate(gross, n)
        abbild = _bauen(self.q)
        e = _lesen(abbild, self.q)
        self.assertEqual([], e["inhalt"])
        # Eine Abweichung weit hinten bleibt bei dieser Stichprobe unentdeckt, die Groesse aber stimmt.
        daten = bytearray(gross.read_bytes())
        daten[-5] ^= 0xFF
        gross.write_bytes(bytes(daten))
        self.assertEqual([], _lesen(abbild, self.q)["inhalt"])
        # Eine Abweichung am Anfang nicht.
        daten[10] ^= 0xFF
        gross.write_bytes(bytes(daten))
        self.assertEqual(["gross.bin"], _lesen(abbild, self.q)["inhalt"])


class ReproduzierbarTests(unittest.TestCase):
    """Dieselbe Quelle ergibt dieselben Bytes (Dump Forge: "reproduzierbares Abbild")."""

    def _sha(self, wurzel: Path) -> str:
        h = hashlib.sha256()
        for stueck in iter_exfat_image(wurzel, cluster_size=32 * 1024):
            h.update(stueck)
        return h.hexdigest()

    def test_gleiche_quelle_gleiche_bytes_auch_bei_anderen_dateizeiten(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            _baum(a)
            h1 = self._sha(a)
            time.sleep(1.1)
            self.assertEqual(h1, self._sha(a), "zweiter Bau")
            b = Path(tmp) / "b"
            shutil.copytree(a, b)
            for p in b.rglob("*"):
                if p.is_file():
                    os.utime(p, (1_000_000_000, 1_000_000_000))
            self.assertEqual(h1, self._sha(b), "andere Dateizeiten")

    def test_andere_bytes_ergeben_ein_anderes_abbild(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"
            _baum(a)
            h1 = self._sha(a)
            (a / "d0" / "f00.bin").write_bytes(b"z")
            self.assertNotEqual(h1, self._sha(a))


class RuecklesenAusLesebaumTests(unittest.TestCase):
    """Stufe 3, Etappe 5: Zuruecklesen gegen den Lesebaum und den Strom statt gegen einen Ordner."""

    def setUp(self) -> None:
        from mkpfs.exfat_writer import iter_exfat_image_liste
        from ps5_validator.utils import abbild_strom, spielbaum
        self.abbild_strom, self.spielbaum = abbild_strom, spielbaum
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.q = Path(self._tmp.name) / "Spiel"
        _baum(self.q)
        self.baum = spielbaum.OrdnerBaum(str(self.q))
        self.addCleanup(self.baum.schliessen)
        self.abbild = b"".join(iter_exfat_image_liste(
            [(d.rel, d.groesse, d.lesen) for d in self.baum.dateien()]))

    def _lesen(self, abbild=None, erwartet=None, **kw):
        erwartet = erwartet if erwartet is not None else self.abbild_strom.pruef_eintraege(self.baum, None, None)
        return ap.exfat_ruecklesen_liste(ExfatReader(io.BytesIO(abbild or self.abbild)), erwartet,
                                         zufall=random.Random(1), **kw)

    def test_ein_richtiges_abbild_besteht_und_wird_ganz_verglichen(self):
        e = self._lesen()
        self.assertEqual(32, e["dateien"])
        self.assertEqual([], e["fehlen"] + e["zuviel"] + e["groesse"] + e["inhalt"])
        self.assertEqual(32, e["stichprobe_dateien"])

    def test_ein_verdorbenes_byte_im_abbild_wird_gefunden(self):
        leser = ExfatReader(io.BytesIO(self.abbild))
        eintrag = next(x for x in leser.iter_files() if x.rel_path == "eboot.bin")
        kaputt = bytearray(self.abbild)
        kaputt[leser._cluster_byte_offset(eintrag.first_cluster) + 50] ^= 0x01
        self.assertEqual(["eboot.bin"], self._lesen(bytes(kaputt))["inhalt"])

    def test_eine_nachtraeglich_veraenderte_quelle_wird_gefunden(self):
        pfad = self.q / "d1" / "f04.bin"
        daten = bytearray(pfad.read_bytes())
        daten[len(daten) // 2] ^= 0xFF
        pfad.write_bytes(bytes(daten))
        self.assertEqual(["d1/f04.bin"], self._lesen()["inhalt"])

    def test_dateien_ohne_anfang_zaehlen_bei_liste_und_groesse_aber_nicht_in_der_stichprobe(self):
        erwartet = [(rel, g, None if rel == "d0/f00.bin" else a)
                    for rel, g, a in self.abbild_strom.pruef_eintraege(self.baum, None, None)]
        e = self._lesen(erwartet=erwartet)
        self.assertEqual(31, e["stichprobe_dateien"])
        falsch = [(rel, g + 1 if rel == "d0/f00.bin" else g, a) for rel, g, a in erwartet]
        self.assertEqual(1, len(self._lesen(erwartet=falsch)["groesse"]))
        fehlt = [x for x in erwartet if x[0] != "d0/f00.bin"]
        self.assertEqual(["d0/f00.bin"], self._lesen(erwartet=fehlt)["zuviel"])

    def test_eine_nicht_lesbare_quelle_ist_kein_fehler_des_abbilds(self):
        def kaputt(_n):
            raise self.spielbaum.BaumFehler("weg")
        erwartet = [(rel, g, kaputt) for rel, g, _a in self.abbild_strom.pruef_eintraege(self.baum, None, None)]
        self.assertEqual([], self._lesen(erwartet=erwartet)["inhalt"])

    def test_was_der_schreiber_weglaesst_zaehlt_nicht(self):
        erwartet = self.abbild_strom.pruef_eintraege(self.baum, None, None) + [("desktop.ini", 5, None)]
        e = self._lesen(erwartet=erwartet, ignoriert=is_ignored_name)
        self.assertEqual([], e["fehlen"])

    def test_der_anfang_aus_dem_baum(self):
        datei = next(d for d in self.baum.dateien() if d.rel == "eboot.bin")
        anfang = ap.anfang_aus_baumdatei(datei)
        voll = (self.q / "eboot.bin").read_bytes()
        self.assertEqual(voll[:100], anfang(100))
        self.assertEqual(voll, anfang(10 ** 9), "mehr als da ist: die ganze Datei")
        self.assertEqual(voll[:1], anfang(1))

    def test_pruef_eintraege_mit_packs(self):
        class _Auswahl:
            gepackt = [("d0/f00.bin", 1)]

        class _Messung:
            def dateien(self):
                return [("ampr_zstd-000.pak", 123), ("ampr_zstd.index", 45)]
        mit = {r: (g, a) for r, g, a in self.abbild_strom.pruef_eintraege(self.baum, _Auswahl(), _Messung(), False)}
        self.assertNotIn("d0/f00.bin", mit, "ein gepacktes Original faellt weg")
        self.assertEqual((123, None), mit["ampr_zstd-000.pak"])
        self.assertIsNone(mit["ampr_zstd.index"][1])
        self.assertIsNotNone(mit["eboot.bin"][1])
        behalten = {r for r, _g, _a in self.abbild_strom.pruef_eintraege(self.baum, _Auswahl(), _Messung(), True)}
        self.assertIn("d0/f00.bin", behalten)

    def test_der_pruefstand_urteilt_wie_beim_ordnerweg(self):
        p = ap.Pruefstand.__new__(ap.Pruefstand)
        p._t = lambda k, **w: k + " " + " ".join("%s=%s" % kv for kv in sorted(w.items()))
        p._extract_embedded_mkpfs = lambda: str(ROOT / "MkPFS-1.1.0")
        pfad = Path(self._tmp.name) / "x.exfat"
        pfad.write_bytes(self.abbild)
        erwartet = self.abbild_strom.pruef_eintraege(self.baum, None, None)
        ok = p._verify_exfat_erwartet(str(pfad), erwartet)
        self.assertTrue(ok["checked"] and ok["ok"], ok)
        self.assertIn("verify.inhalt_ok", ok["detail"])
        (self.q / "eboot.bin").write_bytes(b"X" * 15000)                 # gleiche Groesse, anderer Inhalt
        schlecht = p._verify_exfat_erwartet(str(pfad), erwartet)
        self.assertFalse(schlecht["ok"])
        self.assertIn("verify.inhalt_inhalt", schlecht["detail"])
        pfad.write_bytes(b"kein exfat" * 100)
        kaputt = p._verify_exfat_erwartet(str(pfad), erwartet)
        self.assertTrue(kaputt.get("lesefehler"))

    def test_das_hauptprogramm_nutzt_die_stichprobe_im_stromweg(self):
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn('"pruef_eintraege": abbild_strom.pruef_eintraege(', quelle)
        self.assertIn("_verify_exfat_erwartet(exfat_path, pruef,", quelle)


class VerdrahtungTests(unittest.TestCase):
    def test_der_text_steht_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS, SUPPORTED_LANGUAGES
        for schluessel, felder in (("verify.inhalt_fehlen", ("n", "beispiele")),
                                   ("verify.inhalt_zuviel", ("n", "beispiele")),
                                   ("verify.inhalt_groesse", ("n", "beispiele")),
                                   ("verify.inhalt_inhalt", ("n", "beispiele")),
                                   ("verify.inhalt_ok", ("dateien", "stichprobe", "mb")),
                                   ("log.exfat_ruecklesen_ok", ("v0",))):
            for sprache in SUPPORTED_LANGUAGES:
                text = STRINGS[schluessel][sprache]
                for feld in felder:
                    self.assertIn("{%s}" % feld, text, "%s/%s" % (schluessel, sprache))

    def test_das_hauptprogramm_ruft_die_probe_vor_dem_umbenennen(self):
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        start = quelle.index("def _create_exfat_from_folder")
        ende = quelle.index("def _verify_exfat_inhalt")
        ausschnitt = quelle[start:ende]
        self.assertLess(ausschnitt.index("_verify_exfat_inhalt("), ausschnitt.index("_datei_ersetzen(str(teil_path)"))


if __name__ == "__main__":
    unittest.main()
