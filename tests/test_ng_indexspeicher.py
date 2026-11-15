# -*- coding: utf-8 -*-
"""Tests fuer ``ps5_validator.utils.ng_indexspeicher``: die Rechnung, ob der Indexspeicher von ampr-emu-ng fuer ein Spiel reicht.

Die Grenzen stammen aus dem Quelltext von ampr-emu-ng (0.3.5: 52 + 3 MiB ohne seitenweises Lesen; 0.4.0/beta: 64 MiB, davon
48 MiB Tabellen, Seitenspeicher 16 MiB; ab 0.4.1: 80 MiB fuer alles, kompilierte Ansicht ohne Tabellengrenze). Gemessen an der Konsole
ist keiner der Grenzfaelle - die Tests halten die Rechnung fest.
"""
from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ng_indexspeicher as n   # noqa: E402

PFAD = 60


def _ampridx(dateien: int) -> n.Kopf:
    """Die Groesse eines ``ampr_emu.index`` wie ``_ampr_write_index`` sie schreibt, bei mittleren Pfaden von 60 Bytes."""
    slots = 2
    while slots < 2 * dateien:
        slots *= 2
    laenge = 48 + dateien * 24 + dateien * (6 + PFAD + 1)
    return n.Kopf((laenge + 15) // 16 * 16 + slots * 16, dateien)


def _zstd(dateien: int, gb: float) -> n.Kopf:
    chunks = int(gb * 1e9 / (256 * 1024))
    baender = int(gb * 1e9 / 4.29e9) + 1
    return n.Kopf(128 + dateien * 32 + chunks * 8 + baender * 8 + dateien * PFAD, dateien, chunks, baender)


def _lz4(dateien: int, gb: float) -> n.Kopf:
    chunks = int(gb * 1e9 / (64 * 1024))
    packs = int(gb * 1e9 / 8.5e9) + 4
    return n.Kopf(128 + dateien * 48 + chunks * 12 + packs * 32 + dateien * (PFAD + 1), dateien, chunks, packs)


class ModellTests(unittest.TestCase):
    def test_modell_je_fassung(self) -> None:
        for fassung, soll in (("0.4.0-beta", "0.4.0-beta"), ("0.4.0", "0.4.0"), ("NG 0.4.1", "0.4.1"), ("0.4.2", "0.4.1"),
                              ("0.5.0", "0.4.1"), ("0.3.5", "0.3.5"), ("0.3.4", ""), ("0.2.0", ""), ("", ""),
                              ("0.4.0-Beta", "0.4.0-beta")):
            with self.subTest(fassung):
                self.assertEqual(soll, n.modell_fuer(fassung))

    def test_vor_0_3_5_keine_aussage(self) -> None:
        self.assertIsNone(n.pruefen("0.3.4", _ampridx(1000), "zstd", _zstd(1000, 1)))


class KopfTests(unittest.TestCase):
    def test_die_drei_koepfe(self) -> None:
        idx = b"AMPRIDX3" + struct.pack("<IIQ", 3, 24, 1234) + bytes(32)
        self.assertEqual(n.Kopf(5000, 1234), n.ampridx3_kopf(idx, 5000))
        lz4 = b"AMPRPAK4" + bytes(32) + struct.pack("<QQI", 77, 900, 5) + bytes(68)
        self.assertEqual(n.Kopf(len(lz4), 77, 900, 5), n.lz4_kopf(lz4))
        zst = bytearray(b"AMPRZPK1" + bytes(120))
        struct.pack_into("<I", zst, 20, 3)
        struct.pack_into("<QQ", zst, 40, 91, 6085)
        self.assertEqual(n.Kopf(128, 91, 6085, 3), n.zstd_kopf(bytes(zst)))
        for leser, falsch in ((n.ampridx3_kopf, b"AMPRIDX2" + bytes(40)), (n.lz4_kopf, b"AMPRPAK3" + bytes(80)),
                              (n.zstd_kopf, b"AMPRZPK2" + bytes(80))):
            with self.assertRaises(ValueError):
                leser(falsch)


def _mib_aufgerundet(n_bytes: int) -> int:
    return -(-n_bytes // n.MIB)


class GemeldeteFaelleTests(unittest.TestCase):
    """Gegenprobe an den gemeldeten Faellen von ampr-emu-ng (Zahlen aus den Issue-Kommentaren; die Meldung rundet auf)."""

    def test_demons_souls_lz4_0_4_0(self) -> None:
        """#61: ampr_emu.index 34.358.192 B, 223.180 Dateien; LZ4: 1.513.210 Chunks, 18 Baender. Konsole: "index tables need
        62MiB, over the 48 MiB beside the page cache". Die Laenge des Manifests ist nicht gemeldet - geschaetzt, seitenweise
        gelesen wird es in jedem Fall."""
        idx = n.Kopf(34_358_192, 223_180)
        manifest = n.Kopf(128 + 223_180 * 48 + 1_513_210 * 12 + 18 * 32 + 223_180 * 61, 223_180, 1_513_210, 18)
        befund = n.pruefen("0.4.0", idx, "lz4", manifest)
        self.assertFalse(befund.passt)
        self.assertEqual("ampr_assets.index: Tabellen", befund.engpass)
        self.assertEqual("ganz", befund.belegt["ampr_emu.index"])
        self.assertEqual(62, _mib_aufgerundet(befund.benoetigt))
        self.assertEqual(48 * n.MIB, befund.grenze)
        # beta ab 54d6ac2 (ihr Host-Test nimmt genau diesen Fall): der Index wird seitenweise gelesen, das Manifest passt ganz.
        neu = n.pruefen("0.4.0-beta", idx, "lz4", manifest)
        self.assertTrue(neu.passt, neu)
        self.assertEqual(("seitenweise", "ganz"), (neu.belegt["ampr_emu.index"], neu.belegt["ampr_assets.index"]))

    def test_final_fantasy_xvi_zstd(self) -> None:
        """#53/#67 (Zahlen aus einer anderen Kopie, zstd-Index geschaetzt): 242.436 Dateien, 1.339.356 Chunks, ampr_emu.index
        29,54 MiB, zstd-Index ~32 MiB. Konsole 0.4.0: "49 MiB against 48"; 0.3.5: "index needs 62 MiB, over the 55 MiB cap"."""
        idx = n.Kopf(int(29.54 * n.MIB), 242_436)
        zst = n.Kopf(32 * n.MIB, 242_436, 1_339_356, 72)
        vierzig = n.pruefen("0.4.0", idx, "zstd", zst)
        self.assertFalse(vierzig.passt)
        self.assertEqual("ampr_zstd.index: Tabellen", vierzig.engpass)
        self.assertEqual(49, _mib_aufgerundet(vierzig.benoetigt))
        self.assertEqual(48 * n.MIB, vierzig.grenze)
        self.assertTrue(n.pruefen("0.4.0-beta", idx, "zstd", zst).passt, "mit der beta ab 54d6ac2 passt es nach der Rechnung")
        alt = n.pruefen("0.3.5", idx, "zstd", zst)
        self.assertFalse(alt.passt)
        self.assertEqual("ampr_zstd.index", alt.engpass)
        self.assertEqual(62, _mib_aufgerundet(alt.benoetigt))
        self.assertEqual(55 * n.MIB, alt.grenze)


class Modell035Tests(unittest.TestCase):
    """0.3.5: ein Block von 55 MiB fuer Indexdateien und Tabellen zusammen."""

    def test_ein_mittleres_spiel_passt(self) -> None:
        self.assertTrue(n.pruefen("0.3.5", _ampridx(160_000), "zstd", _zstd(160_000, 60)).passt)
        self.assertTrue(n.pruefen("0.3.5", _ampridx(84_000), "lz4", _lz4(84_000, 100)).passt)

    def test_zu_viel_fuer_55_mib(self) -> None:
        befund = n.pruefen("0.3.5", _ampridx(300_000), "lz4", _lz4(300_000, 100))
        self.assertFalse(befund.passt)
        self.assertEqual("ampr_assets.index", befund.engpass)
        self.assertTrue(n.pruefen("0.3.5", _ampridx(300_000)).passt, "ohne Pack nur der Index: 42 MiB")


class Modell040Tests(unittest.TestCase):
    def test_kleine_und_grosse_spiele(self) -> None:
        for dateien, gb in ((5_000, 10), (84_000, 100), (160_000, 60)):
            for art, pack in (("zstd", _zstd(dateien, gb)), ("lz4", _lz4(dateien, gb)), ("", None)):
                with self.subTest(dateien=dateien, art=art):
                    self.assertTrue(n.pruefen("0.4.0-beta", _ampridx(dateien), art, pack).passt)

    def test_ein_ganz_gelesener_index_kann_dem_manifest_den_platz_nehmen(self) -> None:
        """Rechnung, nicht gemessen: 300.000 Dateien - der ampr_emu.index (42 MiB) passt gerade noch ganz, das zstd-Manifest muss
        dann seitenweise mit 16 MiB Seitenspeicher und findet fuer seine Tabellen keinen Platz mehr. Mit 450.000 Dateien liest NG
        schon den Index seitenweise, und es passt (rt/index.rs read_whole beachtet das Manifest nicht)."""
        befund = n.pruefen("0.4.0", _ampridx(300_000), "zstd", _zstd(300_000, 100))
        self.assertFalse(befund.passt)
        self.assertEqual("ampr_zstd.index: Tabellen", befund.engpass)
        self.assertEqual("ganz", befund.belegt["ampr_emu.index"])
        groesser = n.pruefen("0.4.0", _ampridx(450_000), "zstd", _zstd(450_000, 150))
        self.assertTrue(groesser.passt)
        self.assertEqual("seitenweise", groesser.belegt["ampr_emu.index"])
        # Die beta ab 54d6ac2 schliesst die Luecke: Sie liest den Index gleich seitenweise, wenn sonst das Manifest nicht passt.
        for art, pack in (("zstd", _zstd(300_000, 100)), ("lz4", _lz4(300_000, 100))):
            with self.subTest(art=art):
                beta = n.pruefen("0.4.0-beta", _ampridx(300_000), art, pack)
                self.assertTrue(beta.passt, beta)
                self.assertEqual("seitenweise", beta.belegt["ampr_emu.index"])

    def test_ohne_pack_reicht_es_auch_fuer_sehr_viele_dateien(self) -> None:
        befund = n.pruefen("0.4.0", _ampridx(1_000_000))
        self.assertTrue(befund.passt)
        self.assertEqual("seitenweise", befund.belegt["ampr_emu.index"])

    def test_zstd_kopf_vor_dem_packen_geschaetzt(self) -> None:
        """``ampr_zstdpack.index_kopf_schaetzen`` trifft Laenge, Dateien und Chunks des Index, den der Packer schreibt."""
        from ps5_validator.utils import ampr_zstdpack as z
        gepackt = [("data/a.bin", z.CHUNK_SIZE * 2 + 1), ("Ü/b.txt", 10)]
        laenge, dateien, chunks, baender = z.index_kopf_schaetzen(gepackt)
        self.assertEqual((2, 4, 1), (dateien, chunks, baender))
        self.assertEqual(z.INDEX_HEADER_SIZE + 2 * z.FILE_RECORD_SIZE + 4 * z.CHUNK_RECORD_SIZE + 1 * z.VOLUME_RECORD_SIZE
                         + len("data/a.bin") + len("Ü/b.txt".encode("utf-8")), laenge)

    def test_packindex_ueber_512_mib(self) -> None:
        riesig = n.Kopf(600 * n.MIB, 10, 10, 1)
        self.assertEqual("Pack-Index ueber 512 MiB", n.pruefen("0.4.0-beta", _ampridx(10), "zstd", riesig).engpass)
        self.assertEqual("Pack-Index ueber 512 MiB", n.pruefen("0.4.1", _ampridx(10), "zstd", riesig).engpass)


class Modell041Tests(unittest.TestCase):
    """Ab 0.4.1 (15.11.2026): kompilierte Ansicht, ein Block von 80 MiB fuer alles, keine Tabellengrenze und kein Seitenspeicher.
    Zahlen aus ``rt/index_memory.rs`` (Kommentare) und ``docs/zstd-format.md`` von ampr-emu-ng v0.4.1."""

    def test_ansicht_von_hand_gerechnet(self) -> None:
        """1000 Dateien, Ordnerzahl vorab 1000 // 8 + 1024 = 1149; Hash-Plaetze: Zweierpotenz ab 1,5 x (1500 -> 2048, 1723 -> 2048)."""
        gemeinsam = 24_000 + 32 * 1149 + 4_000 + 4 * 2048 + 4 * 2048 + 4 * 256      # Spalten, Ordner, path_at, beide Platztabellen
        self.assertEqual((gemeinsam, 4_000), n.ansicht_041(1000))
        self.assertEqual(gemeinsam + 4_000, n.ansicht_041(1000, "lz4")[0], "LZ4: dazu die Spalte next")
        self.assertEqual(gemeinsam + 4_000 + 4_000, n.ansicht_041(1000, "zstd")[0])             # next + chunk
        self.assertEqual(4_000 + 8_000, n.ansicht_041(1000, "lz4")[1], "LZ4: dir_of + lz4_hash im Zwischenblock")
        self.assertEqual(90_176, n.ansicht_041(1000, "zstd")[0])

    def test_die_zahlen_der_entwickler(self) -> None:
        """Kommentar in index_memory.rs: bei 300.000 Dateien und der ersten Ordnerzahl 12,6 MiB ohne Pack, 14,9 mit zstd, 16,0 mit
        LZ4 (Haupt- plus Zwischenblock); docs/zstd-format.md: 242.409 Dateien -> 21,74 MiB Ansicht plus Tabellen."""
        for art, soll in (("", 12.6), ("zstd", 14.9), ("lz4", 16.0)):
            with self.subTest(art=art):
                haupt, zwischen = n.ansicht_041(300_000, art)
                self.assertAlmostEqual(soll, (haupt + zwischen) / n.MIB, delta=0.05)
        haupt, _ = n.ansicht_041(242_409, "zstd")
        self.assertAlmostEqual(21.74, (haupt + (1_339_356 + 72) * 8) / n.MIB, delta=0.02)
        # LZ4-Manifest: "223,180 files, 1,513,210 chunks and 18 packs ... 27.5 MiB"
        manifest = n.Kopf(0, 223_180, 1_513_210, 18)
        befund = n.pruefen("0.4.1", n.Kopf(34_358_192, 223_180), "lz4", manifest)
        self.assertAlmostEqual(27.5, befund.belegt["tabellen"] / n.MIB, delta=0.1)

    def test_die_gemeldeten_faelle_passen(self) -> None:
        """Demon's Souls (LZ4, 223.180 Dateien) und Final Fantasy XVI (zstd, 242.436 Dateien) scheiterten mit 0.4.0 an den 48 MiB."""
        ds = n.pruefen("0.4.1", n.Kopf(34_358_192, 223_180), "lz4", n.Kopf(0, 223_180, 1_513_210, 18))
        self.assertTrue(ds.passt, ds)
        ff = n.pruefen("0.4.1", n.Kopf(int(29.54 * n.MIB), 242_436), "zstd", n.Kopf(32 * n.MIB, 242_436, 1_339_356, 72))
        self.assertTrue(ff.passt, ff)
        self.assertEqual(n.MODELL_041, ff.modell)
        self.assertLess(ff.belegt["dauerhaft"], 25 * n.MIB, "21,7 MiB Ansicht und Tabellen, abgerundet auf Seiten")
        self.assertLess(ff.belegt["dauerhaft"], ff.belegt["gesamt"], "der Zwischenblock kostet nur in der Spitze")

    def test_ohne_pack_nur_die_ansicht(self) -> None:
        self.assertTrue(n.pruefen("0.4.1", n.Kopf(0, 1_000_000)).passt)
        zuviel = n.pruefen("0.4.1", n.Kopf(0, 3_000_000))
        self.assertFalse(zuviel.passt)
        self.assertEqual("ampr_emu.index: Ansicht", zuviel.engpass)
        self.assertEqual(80 * n.MIB, zuviel.grenze)

    def test_zstd_tabellen_gegen_den_freien_platz(self) -> None:
        """zstd_mount_join: Tabellen (8 B je Chunk und Band) plus zwei Fenster gegen den Platz, der nach der Ansicht bleibt."""
        gross = n.pruefen("0.4.1", n.Kopf(0, 600_000), "zstd", n.Kopf(0, 600_000, 8_000_000, 100))
        self.assertFalse(gross.passt)
        self.assertEqual("ampr_zstd.index: Tabellen", gross.engpass)
        self.assertEqual(80 * n.MIB, gross.grenze)
        self.assertGreater(gross.benoetigt, gross.grenze, "wie die Meldung der Konsole: belegt plus Anforderung ueber der Kappe")
        self.assertTrue(n.pruefen("0.4.1", n.Kopf(0, 600_000), "zstd", n.Kopf(0, 600_000, 3_000_000, 100)).passt)

    def test_ordnerzahl_wirkt_nur_auf_die_ansicht(self) -> None:
        normal = n.ansicht_041(1000, "zstd")
        viele = n.ansicht_041(1000, "zstd", ordner=5000)
        self.assertGreater(viele[0], normal[0])
        self.assertEqual(normal[1], viele[1])
        self.assertEqual(n.pruefen("0.4.1", n.Kopf(0, 1000), "zstd", n.Kopf(0, 1000, 10, 1)).belegt["ansicht"], normal[0])
        self.assertEqual(viele[0], n.pruefen("0.4.1", n.Kopf(0, 1000), "zstd", n.Kopf(0, 1000, 10, 1), ordner=5000).belegt["ansicht"])

    def test_dauerhaft_ist_ansicht_plus_tabellen_in_seiten(self) -> None:
        haupt, _ = n.ansicht_041(50_000, "zstd")
        befund = n.pruefen("0.4.1", n.Kopf(0, 50_000), "zstd", n.Kopf(0, 50_000, 275_000, 20))
        self.assertTrue(befund.passt)
        self.assertEqual(n._rund(haupt) + n._rund((275_000 + 20) * 8), befund.belegt["dauerhaft"])

    def test_lz4_bitmap_und_manifest_zaehlen(self) -> None:
        befund = n.pruefen("0.4.1", n.Kopf(0, 100_000), "lz4", n.Kopf(0, 100_000, 600_000, 8))
        self.assertTrue(befund.passt)
        soll = n.LZ4_KOPF + 100_000 * 48 + 600_000 * 12 + 8 * n.LZ4_JE_PACK + (100_000 + 1 + 7) // 8
        self.assertEqual(soll, befund.belegt["tabellen"])

    def test_die_beta_bleibt_beim_alten_modell(self) -> None:
        """Die beta (54d6ac2) hat noch die 48-MiB-Grenze: Final Fantasy XVI ging dort nur wegen des seitenweisen Lesens."""
        idx = n.Kopf(int(29.54 * n.MIB), 242_436)
        zst = n.Kopf(32 * n.MIB, 242_436, 1_339_356, 72)
        self.assertEqual(n.MODELL_BETA, n.pruefen("0.4.0-beta", idx, "zstd", zst).modell)
        self.assertEqual(n.MODELL_041, n.pruefen("0.4.1", idx, "zstd", zst).modell)
        self.assertEqual(n.MODELL_041, n.pruefen("0.5.0", idx, "zstd", zst).modell, "neuere Fassungen: so angenommen")


if __name__ == "__main__":
    unittest.main()
