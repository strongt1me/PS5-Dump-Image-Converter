# -*- coding: utf-8 -*-
"""Der exFAT-Leser von MkPFS holt nicht mehr das Vierfache der Nutzdaten vom Datentraeger.

Befund (12.11.2026, Vergleich mit Dump Forge): ``ExfatReader.read_file`` las je Cluster mit seek+read und fragte bei Dateien mit
FAT-Kette vor jedem Cluster die FAT mit seek+read(4). Durch den 128-KiB-Puffer von ``open(..., "rb")`` kostete jedes dieser Lesen
128 KiB: Fuer 64-KiB-Cluster zwei Zugriffe, also das Vierfache (gemessen 315 MB Ausgabe, 1258 MB Lesen; im echten Lauf 596 GB fuer
151 GB). Jetzt wird die FAT einmal geladen und aufeinanderfolgende Cluster in einem Lesen geholt. Die Bytes bleiben dieselben.
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

from mkpfs.exfat import ExfatEntry, ExfatError, ExfatGeometry, ExfatReader      # noqa: E402

CLUSTER = 4096
SEKTOR = 512
SPC = CLUSTER // SEKTOR
FAT_AB_SEKTOR = 1
HEAP_AB_SEKTOR = 16          # 8192: hinter der FAT (264 Bytes bei 64 Clustern)
CLUSTERZAHL = 64
EOC = 0xFFFFFFFF


class _Zaehlend(io.BytesIO):
    """BytesIO, das jedes ``read`` mit Groesse und Stelle mitschreibt."""

    def __init__(self, daten: bytes) -> None:
        super().__init__(daten)
        self.lesevorgaenge: list[tuple[int, int]] = []

    def read(self, groesse: int | None = -1) -> bytes:
        stelle = self.tell()
        daten = super().read(groesse)
        self.lesevorgaenge.append((stelle, len(daten)))
        return daten


def _abbild(kette: list[int], ohne_ende: int = 0) -> bytes:
    """Ein kleines Abbild: Cluster n enthaelt ``bytes([n]) * CLUSTER``; die FAT verkettet ``kette`` der Reihe nach."""
    heap = HEAP_AB_SEKTOR * SEKTOR
    gesamt = heap + (CLUSTERZAHL - 2) * CLUSTER
    abbild = bytearray(gesamt)
    for n in range(2, CLUSTERZAHL):
        stelle = heap + (n - 2) * CLUSTER
        abbild[stelle:stelle + CLUSTER] = bytes([n]) * CLUSTER
    fat = FAT_AB_SEKTOR * SEKTOR
    for a, b in zip(kette, kette[1:] + [EOC]):
        abbild[fat + a * 4:fat + a * 4 + 4] = b.to_bytes(4, "little")
    return bytes(abbild[:gesamt - ohne_ende])


def _leser(abbild: bytes) -> tuple[ExfatReader, _Zaehlend]:
    roh = _Zaehlend(abbild)
    leser = ExfatReader.__new__(ExfatReader)
    leser._fh = roh
    leser._fat = None
    leser._fat_versucht = False
    leser.geometry = ExfatGeometry(
        bytes_per_sector=SEKTOR, sectors_per_cluster=SPC, fat_offset_sectors=FAT_AB_SEKTOR,
        cluster_heap_offset_sectors=HEAP_AB_SEKTOR, cluster_count=CLUSTERZAHL, root_dir_cluster=2, volume_serial=1)
    return leser, roh


def _eintrag(kette: list[int], laenge: int, ohne_kette: bool = False) -> ExfatEntry:
    return ExfatEntry(name="datei", rel_path="datei", is_dir=False, first_cluster=kette[0], length=laenge,
                      no_fat_chain=ohne_kette)


def _soll(kette: list[int], laenge: int) -> bytes:
    return b"".join(bytes([n]) * CLUSTER for n in kette)[:laenge]


class LaufTests(unittest.TestCase):
    KETTE = [5, 6, 7, 20, 21, 3]                                     # zerstueckelt: drei Laeufe

    def _lesen(self, kette, laenge, chunk=3 * CLUSTER, ohne_kette=False, abbild=None):
        leser, roh = _leser(abbild if abbild is not None else _abbild(kette))
        teile = list(leser.read_file(_eintrag(kette, laenge, ohne_kette), chunk_size=chunk))
        return teile, roh

    def test_die_bytes_einer_zerstueckelten_datei_stimmen(self):
        laenge = 6 * CLUSTER - 100
        teile, _roh = self._lesen(self.KETTE, laenge)
        self.assertEqual(_soll(self.KETTE, laenge), b"".join(teile))

    def test_aufeinanderfolgende_cluster_kommen_in_einem_lesen(self):
        teile, roh = self._lesen(self.KETTE, 6 * CLUSTER)
        daten_lesen = [v for v in roh.lesevorgaenge if v[1] > 4 and v[0] >= HEAP_AB_SEKTOR * SEKTOR]
        self.assertEqual(3, len(daten_lesen), "drei Laeufe: [5,6,7] [20,21] [3] - %s" % daten_lesen)
        self.assertEqual([3 * CLUSTER, 2 * CLUSTER, CLUSTER], [v[1] for v in daten_lesen])

    def test_ein_lauf_ist_hoechstens_ein_chunk_gross(self):
        teile, roh = self._lesen(self.KETTE, 6 * CLUSTER, chunk=2 * CLUSTER)
        daten_lesen = [v for v in roh.lesevorgaenge if v[1] > 4 and v[0] >= HEAP_AB_SEKTOR * SEKTOR]
        self.assertEqual([2 * CLUSTER, CLUSTER, 2 * CLUSTER, CLUSTER], [v[1] for v in daten_lesen])
        self.assertTrue(all(len(t) <= 2 * CLUSTER for t in teile))
        self.assertEqual(_soll(self.KETTE, 6 * CLUSTER), b"".join(teile))

    def test_cluster_groesser_als_der_chunk_werden_einzeln_gelesen_und_zerlegt(self):
        teile, roh = self._lesen(self.KETTE, 6 * CLUSTER, chunk=1024)
        self.assertTrue(all(len(t) <= 1024 for t in teile))
        self.assertEqual(_soll(self.KETTE, 6 * CLUSTER), b"".join(teile))

    def test_die_fat_wird_einmal_geladen_nicht_je_eintrag(self):
        _teile, roh = self._lesen(self.KETTE, 6 * CLUSTER)
        fat_lesen = [v for v in roh.lesevorgaenge if FAT_AB_SEKTOR * SEKTOR <= v[0] < HEAP_AB_SEKTOR * SEKTOR]
        self.assertEqual(1, len(fat_lesen), "ein Lesen der ganzen FAT, kein seek+read(4) je Cluster: %s" % fat_lesen)
        self.assertEqual((CLUSTERZAHL + 2) * 4, fat_lesen[0][1])

    def test_ohne_fat_kette_liest_die_datei_zusammenhaengend_in_einem_lauf(self):
        kette = [10, 11, 12, 13]
        leser, roh = _leser(_abbild(kette))
        teile = list(leser.read_file(_eintrag(kette, 4 * CLUSTER - 7, ohne_kette=True), chunk_size=4 * CLUSTER))
        self.assertEqual(_soll(kette, 4 * CLUSTER - 7), b"".join(teile))
        self.assertEqual([], [v for v in roh.lesevorgaenge if FAT_AB_SEKTOR * SEKTOR <= v[0] < HEAP_AB_SEKTOR * SEKTOR],
                         "ohne FAT-Kette wird die FAT nicht angefasst")
        self.assertEqual(1, len([v for v in roh.lesevorgaenge if v[1] > 4 and v[0] >= HEAP_AB_SEKTOR * SEKTOR]))

    def test_eine_leere_datei_liest_nichts_und_folgt_keiner_kette(self):
        leser, roh = _leser(_abbild(self.KETTE))
        self.assertEqual([], list(leser.read_file(_eintrag(self.KETTE, 0))))
        self.assertEqual([], roh.lesevorgaenge, "nicht einmal die FAT wird geladen")

    def test_eine_abgeschnittene_datei_bleibt_ein_fehler(self):
        abbild = _abbild(self.KETTE, ohne_ende=(CLUSTERZAHL - 3 - 0) * CLUSTER)   # Cluster 3.. fehlen am Ende
        leser, _roh = _leser(abbild)
        with self.assertRaises(ExfatError) as ctx:
            list(leser.read_file(_eintrag(self.KETTE, 6 * CLUSTER)))
        self.assertIn("truncated", str(ctx.exception))

    def test_eine_zu_grosse_fat_wird_wie_frueher_je_eintrag_gelesen(self):
        leser, roh = _leser(_abbild(self.KETTE))
        leser._FAT_SPEICHER_MAX = 16
        teile = list(leser.read_file(_eintrag(self.KETTE, 6 * CLUSTER)))
        self.assertEqual(_soll(self.KETTE, 6 * CLUSTER), b"".join(teile))
        kleine = [v for v in roh.lesevorgaenge if v[1] == 4]
        self.assertGreaterEqual(len(kleine), 5, "je Eintrag ein Lesen von vier Bytes")

    def test_eine_fat_die_kuerzer_ist_als_erwartet_faellt_auf_den_alten_weg_zurueck(self):
        abbild = _abbild(self.KETTE)
        leser, roh = _leser(abbild)
        leser.geometry = ExfatGeometry(
            bytes_per_sector=SEKTOR, sectors_per_cluster=SPC, fat_offset_sectors=FAT_AB_SEKTOR,
            cluster_heap_offset_sectors=HEAP_AB_SEKTOR, cluster_count=100000, root_dir_cluster=2, volume_serial=1)
        # Die FAT-Laenge (100002 * 4) ueberragt das Abbild: das Laden liefert weniger -> kein Zwischenspeicher, alter Weg.
        teile = list(leser.read_file(_eintrag(self.KETTE, 6 * CLUSTER)))
        self.assertEqual(_soll(self.KETTE, 6 * CLUSTER), b"".join(teile))
        self.assertIsNone(leser._fat)


class AbbildTests(unittest.TestCase):
    """Mit einem echten, vom Schreiber des Projekts gebauten Abbild: gleiche Bytes, und nur etwa einmal gelesen."""

    @classmethod
    def setUpClass(cls) -> None:
        from mkpfs.exfat_writer import iter_exfat_image
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        spiel = Path(cls._tmp.name) / "spiel"
        (spiel / "sce_sys").mkdir(parents=True)
        (spiel / "eboot.bin").write_bytes(b"ELF" * 100)
        (spiel / "sce_sys" / "param.json").write_bytes(b'{"titleId":"PPSA00000"}')
        cls.gross = bytes((i * 7 + 3) % 251 for i in range(6 * 1024 * 1024 + 12345))
        (spiel / "gross.bin").write_bytes(cls.gross)
        cls.abbild = Path(cls._tmp.name) / "test.exfat"
        with cls.abbild.open("wb") as aus:
            for stueck in iter_exfat_image(spiel, cluster_size=64 * 1024):
                aus.write(stueck)

    def test_die_ausgabe_gleicht_der_quelle(self):
        with self.abbild.open("rb") as fh:
            leser = ExfatReader(fh)
            dateien = {d.rel_path: d for d in leser.iter_files()}
            self.assertEqual(self.gross, b"".join(leser.read_file(dateien["gross.bin"])))
            self.assertEqual(b"ELF" * 100, b"".join(leser.read_file(dateien["eboot.bin"])))

    def test_das_lesen_vom_datentraeger_bleibt_nahe_an_der_ausgabe(self):
        """Mit einem zaehlenden Rohstrom unter dem 128-KiB-Puffer von Python: vorher Faktor 4,0."""
        class Roh(io.RawIOBase):
            def __init__(self, pfad):
                self.f = open(pfad, "rb", buffering=0)
                self.gelesen = 0

            def readable(self):
                return True

            def seekable(self):
                return True

            def seek(self, off, whence=0):
                return self.f.seek(off, whence)

            def tell(self):
                return self.f.tell()

            def readinto(self, b):
                n = self.f.readinto(b)
                self.gelesen += n or 0
                return n

            def close(self):
                self.f.close()
                super().close()

        roh = Roh(self.abbild)
        fh = io.BufferedReader(roh, buffer_size=128 * 1024)
        try:
            leser = ExfatReader(fh)
            gross = next(d for d in leser.iter_files() if d.rel_path == "gross.bin")
            roh.gelesen = 0
            ausgabe = sum(len(c) for c in leser.read_file(gross))
        finally:
            fh.close()
        self.assertEqual(len(self.gross), ausgabe)
        self.assertLessEqual(roh.gelesen, ausgabe * 1.1, "gelesen %.2f-fach" % (roh.gelesen / ausgabe))


if __name__ == "__main__":
    unittest.main()
