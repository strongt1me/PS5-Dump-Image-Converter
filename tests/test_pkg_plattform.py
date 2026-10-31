# -*- coding: utf-8 -*-
"""PS4- oder PS5-Paket? (``utils/pkg_plattform.py``, Erkennung der Seite "7. PKG / FPKG" seit 30.10.2026.)

Die Regeln sind an 49 echten Paketen gemessen (36 mit ``\\x7fCNT``, 13 mit ``\\x7fFIH``/``\\x7fLIH``). Hier laufen sie an
selbst gebauten Minimalkoepfen im Temp-Ordner - und, wo die echten Dateien auf dem Rechner liegen, an diesen.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import pkg_plattform as pp  # noqa: E402

#: Echte Pakete auf dem Rechner des Entwicklers (je PS4-Format und PS5-Format); fehlen sie, wird uebersprungen.
ECHT_PS4 = r"F:\PS5\PS5 Hack\PS5 APPS PKG's\Itemzflow v1.14\Itemzflow v1.14.pkg"
ECHT_PS5 = r"F:\PS5\PS5 Hack\PS5 APPS PKG's\Youtube v1.03\PS5_PPSA01650_v1.03.pkg"


def cnt_paket(pfad: str, content_id: str = "UP9000-CUSA00001_00-TESTTITLE0000000", eintraege=(0x1000,)) -> str:
    """Ein CNT-Kopf wie bei den gemessenen Paketen: Magic, Zahl und Lage der Tabelle, Content-ID, dann die Tabelle."""
    kopf = bytearray(0x5A0)
    kopf[0:4] = b"\x7fCNT"
    struct.pack_into(">I", kopf, 0x10, len(eintraege))
    struct.pack_into(">I", kopf, 0x18, 0x5A0)
    kopf[0x40:0x40 + len(content_id)] = content_id.encode("ascii")
    struct.pack_into(">III", kopf, 0x70, 0x0F, 0x1A, 0x0A000000)
    tabelle = b"".join(struct.pack(">IIIIII", kennung, 0, 0, 0, 0x6000, 16) + b"\0" * 8 for kennung in eintraege)
    with open(pfad, "wb") as f:
        f.write(bytes(kopf) + tabelle + b"\0" * 64)
    return pfad


def fih_paket(pfad: str, magic: bytes = b"\x7fFIH") -> str:
    with open(pfad, "wb") as f:
        f.write(magic + b"\x00\x80" + b"\0" * 0x600)
    return pfad


class PaketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="pkgplatt_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)

    def p(self, name: str) -> str:
        return os.path.join(self.ordner, name)

    def test_fih_und_lih_sind_ps5(self) -> None:
        self.assertEqual(pp.PS5, pp.paket_plattform(fih_paket(self.p("a.pkg")))[0])
        self.assertEqual(pp.PS5, pp.paket_plattform(fih_paket(self.p("b.pkg"), b"\x7fLIH"))[0])

    def test_cnt_mit_sfo_ist_ps4_auch_mit_ps5_namen(self) -> None:
        """Die "PS5PKG_..."-Homebrew (Itemzflow, FPKGi, PS5-Xplorer) ist PS4-Format - der Name zaehlt nicht."""
        for name in ("Spiel_CUSA00001.pkg", "PS5PKG_Itemzflow_Game_Manager_v1.14.pkg", "PS5_Xplorer_v1.05.pkg"):
            with self.subTest(name=name):
                plattform, grund = pp.paket_plattform(cnt_paket(self.p(name)))
                self.assertEqual(pp.PS4, plattform)
                self.assertIn("CNT", grund)

    def test_cnt_mit_homebrew_titelkennung_ist_ps4(self) -> None:
        # Gemessen: ED1234-LAPY20011_00-PS4XPLORER200000 und IV0002-ITEM00001_00-STOREUPD00000000 sind CNT = PS4.
        for cid in ("ED1234-LAPY20011_00-PS4XPLORER200000", "IV0002-ITEM00001_00-STOREUPD00000000"):
            with self.subTest(cid=cid):
                self.assertEqual(pp.PS4, pp.paket_plattform(cnt_paket(self.p("x.pkg"), cid))[0])

    def test_cnt_mit_ppsa_in_der_content_id_ist_ps5_meta(self) -> None:
        plattform, _grund = pp.paket_plattform(cnt_paket(self.p("m.pkg"), "UP9000-PPSA01234_00-METAONLY00000000"))
        self.assertEqual(pp.PS5, plattform)

    def test_cnt_mit_json_ohne_sfo_ist_ps5_meta_und_mit_beiden_ps4(self) -> None:
        self.assertEqual(pp.PS5, pp.paket_plattform(cnt_paket(self.p("j.pkg"), eintraege=(0x2000, 0x1200)))[0])
        # Gegenprobe: mit param.sfo daneben bleibt es PS4 (so sahen alle gemessenen CNT-Pakete aus).
        self.assertEqual(pp.PS4, pp.paket_plattform(cnt_paket(self.p("b.pkg"), eintraege=(0x2000, 0x1000)))[0])

    def test_keine_gueltige_magic_ist_nichts(self) -> None:
        for name, inhalt in (("zufall.pkg", os.urandom(0x700)), ("kurz.pkg", b"\x7fCN"), ("leer.pkg", b""),
                             ("text.pkg", b"Das ist keine Paketdatei." * 80),
                             ("zip.pkg", b"PK\x03\x04" + b"\0" * 0x700)):
            with self.subTest(name=name):
                with open(self.p(name), "wb") as f:
                    f.write(inhalt)
                self.assertIsNone(pp.paket_plattform(self.p(name))[0])
        self.assertIsNone(pp.paket_plattform(self.p("gibt-es-nicht.pkg"))[0])

    def test_ein_abgeschnittener_cnt_kopf_bleibt_ps4_ohne_absturz(self) -> None:
        pfad = self.p("kurz_cnt.pkg")
        with open(pfad, "wb") as f:
            f.write(b"\x7fCNT" + b"\0" * 60)
        self.assertEqual(pp.PS4, pp.paket_plattform(pfad)[0])

    @unittest.skipUnless(os.path.isfile(ECHT_PS4), "echtes PS4-Paket nicht vorhanden")
    def test_ein_echtes_ps4_paket(self) -> None:
        self.assertEqual(pp.PS4, pp.paket_plattform(ECHT_PS4)[0])

    @unittest.skipUnless(os.path.isfile(ECHT_PS5), "echtes PS5-Paket nicht vorhanden")
    def test_ein_echtes_ps5_paket(self) -> None:
        self.assertEqual(pp.PS5, pp.paket_plattform(ECHT_PS5)[0])


class ErkennenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="pkgplatt_")
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)

    def p(self, *teile: str) -> str:
        pfad = os.path.join(self.ordner, *teile)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        return pfad

    def test_eine_ps4_datei(self) -> None:
        erg = pp.erkennen([cnt_paket(self.p("a.pkg"))])
        self.assertEqual((pp.PS4, pp.ART_DATEIEN), (erg.plattform, erg.art))
        self.assertFalse(erg.gemischt)

    def test_eine_ps5_datei_hat_keine_ps4_art(self) -> None:
        erg = pp.erkennen(fih_paket(self.p("a.pkg")))             # auch ein einzelner Pfad als Text
        self.assertEqual((pp.PS5, ""), (erg.plattform, erg.art))

    def test_mehrere_ps4_dateien(self) -> None:
        erg = pp.erkennen([cnt_paket(self.p("a.pkg")), cnt_paket(self.p("b.pkg"))])
        self.assertEqual((pp.PS4, pp.ART_DATEIEN, 2, 0), (erg.plattform, erg.art, erg.anzahl_ps4, erg.anzahl_ps5))

    def test_ein_ordner_mit_ps4_paketen(self) -> None:
        cnt_paket(self.p("pkgs", "a.pkg"))
        cnt_paket(self.p("pkgs", "spiel2", "b.pkg"))              # eine Ebene tiefer zaehlt mit
        erg = pp.erkennen([os.path.join(self.ordner, "pkgs")])
        self.assertEqual((pp.PS4, pp.ART_ORDNER, 2), (erg.plattform, erg.art, erg.anzahl_ps4))

    def test_ein_ordner_mit_ps5_paketen(self) -> None:
        fih_paket(self.p("pkgs", "a.pkg"))
        erg = pp.erkennen([os.path.join(self.ordner, "pkgs")])
        self.assertEqual(pp.PS5, erg.plattform)

    def test_ein_gemischter_ordner_geht_in_den_ps4_bereich_mit_hinweis(self) -> None:
        cnt_paket(self.p("m", "a.pkg"))
        fih_paket(self.p("m", "b.pkg"))
        fih_paket(self.p("m", "c.pkg"))
        erg = pp.erkennen([os.path.join(self.ordner, "m")])
        self.assertEqual((pp.PS4, pp.ART_ORDNER), (erg.plattform, erg.art))
        self.assertTrue(erg.gemischt)
        self.assertEqual((1, 2), (erg.anzahl_ps4, erg.anzahl_ps5))

    def test_spielordner_mit_param_json_ist_ps5_mit_nur_param_sfo_ps4(self) -> None:
        os.makedirs(self.p("spiel5", "sce_sys", "x"))
        open(self.p("spiel5", "sce_sys", "param.json"), "w").close()
        os.makedirs(self.p("spiel4", "sce_sys", "x"))
        open(self.p("spiel4", "sce_sys", "param.sfo"), "w").close()
        self.assertEqual(pp.PS5, pp.erkennen([os.path.join(self.ordner, "spiel5")]).plattform)
        erg4 = pp.erkennen([os.path.join(self.ordner, "spiel4")])
        self.assertEqual((pp.PS4, pp.ART_DUMP), (erg4.plattform, erg4.art))
        # Gegenprobe: mit beiden Dateien gewinnt param.json (ein PS5-Spiel traegt sie).
        open(self.p("spiel4", "sce_sys", "param.json"), "w").close()
        self.assertEqual(pp.PS5, pp.erkennen([os.path.join(self.ordner, "spiel4")]).plattform)

    def test_ungueltiges_sagt_warum_und_aendert_nichts(self) -> None:
        leer = self.p("leer", "x.txt")
        open(leer, "w").close()
        erg = pp.erkennen([os.path.dirname(leer)])
        self.assertIsNone(erg.plattform)
        self.assertTrue(erg.grund)
        text = self.p("text.pkg")
        with open(text, "wb") as f:
            f.write(b"nichts" * 200)
        erg2 = pp.erkennen([text])
        self.assertIsNone(erg2.plattform)
        self.assertEqual([text], erg2.pfade, "Die Eingabe bleibt unveraendert.")
        self.assertEqual(b"nichts" * 200, open(text, "rb").read(), "Es wird nichts geschrieben.")
        self.assertIsNone(pp.erkennen([]).plattform)
        self.assertIsNone(pp.erkennen([self.p("gibt-es-nicht")]).plattform)

    def test_eine_ordnerwahl_mit_beliebigem_inhalt_stuerzt_nie_ab(self) -> None:
        for name in ("a.txt", "b.bin"):
            with open(self.p("misch", name), "wb") as f:
                f.write(os.urandom(32))
        self.assertIsNone(pp.erkennen([os.path.join(self.ordner, "misch")]).plattform)


if __name__ == "__main__":
    unittest.main()
