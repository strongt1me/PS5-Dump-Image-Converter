# -*- coding: utf-8 -*-
"""PFS-Lesebaum (``spielbaum.PfsBaum``): ``.ffpfs``/``.ffpfsc`` lesen, ohne zu entpacken (Stufe 3, Etappe 7).

Die Probe am echten Format: Ein Spielordner wird mit MkPFS in alle Bauformen gebracht, die das Programm kennt - flach (mit und ohne
PFSC-Kompression), umhuellend (ein inneres exFAT, mit und ohne Kompression), doppelt umhuellt, PFS in PFS - und der Baum muss
ueberall dieselbe Liste, dieselben Groessen und dieselben Bytes liefern wie der Ordner. Dazu: mehrere Faeden zugleich, der
Stempel, Fehlerfaelle (kein Abbild, abgeschnitten, nicht lesbar) und der Weg bis zum zstd-Pack (Byte-Gleichheit mit dem Pack aus dem Ordner).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("pfsbaum")

from mkpfs import consts                                     # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402
from mkpfs.pfs import build_pfs, build_pfs_stream_single_file   # noqa: E402
from mkpfs.utils import is_ignored_name                      # noqa: E402

from ps5_validator.utils import ampr_zstdpack as z           # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402


def _zufall(n: int, startwert: int = 1) -> bytes:
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


SPIEL = {
    "eboot.bin": _zufall(5000, 1),
    "sce_sys/param.json": b'{"titleId":"PPSA00000"}',
    "sce_sys/icon0.png": _zufall(9000, 2),
    "data/a.pak": _zufall(300_000, 3),                       # mehrere PFSC-Bloecke, nicht komprimierbar
    "data/text.txt": b"Hallo Welt\n" * 40_000,               # gut komprimierbar
    "data/b/c.bin": _zufall(70_000, 4),
    "data/b/leer.txt": b"",
    "Daten/Zebra.dat": _zufall(40_000, 5),
    "readme.ini": b"[x]\na=1\n",
}


def _schreiben(wurzel: str, inhalte: dict[str, bytes]) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)


def _flach(ordner: str, ziel: str, *, komprimiert: bool) -> None:
    build_pfs(source_root=Path(ordner), output_path=Path(ziel), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
              inode_bits=32, case_insensitive=True, signed=False, compress=komprimiert, threshold_gain=0, cpu_count=1,
              zlib_level=6, dry_run=False, verbose=False)


def _huelle(innen: str, ziel: str, *, komprimiert: bool) -> None:
    build_pfs_stream_single_file(
        source_file=Path(innen), output_path=Path(ziel), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
        case_insensitive=True, zlib_level=6, threshold_gain=0, min_file_gain=0, min_compress_size=0, cpu_count=1,
        compress=komprimiert)


def _inhalt(datei: sb.BaumDatei, stueck: int = sb.LESE_STUECK) -> bytes:
    return b"".join(datei.lesen(stueck))


class _Grundlage(unittest.TestCase):
    """Baut die Abbilder einmal je Klasse (ein Aufbau dauert Sekunden)."""

    tmp = ""
    spiel = ""
    abbilder: dict[str, str] = {}

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp(prefix="pfsbaum_")
        cls.spiel = os.path.join(cls.tmp, "spiel")
        _schreiben(cls.spiel, SPIEL)
        os.makedirs(os.path.join(cls.spiel, "savedata_leer"))              # ein Verzeichnis ohne Datei darin
        a = cls.abbilder = {}
        exfat = os.path.join(cls.tmp, "spiel.exfat")
        with open(exfat, "wb") as fh:
            for stueck in iter_exfat_image(Path(cls.spiel)):
                fh.write(stueck)
        a["flach_roh"] = os.path.join(cls.tmp, "flach_roh.ffpfs")
        _flach(cls.spiel, a["flach_roh"], komprimiert=False)
        a["flach_pfsc"] = os.path.join(cls.tmp, "flach_pfsc.ffpfsc")
        _flach(cls.spiel, a["flach_pfsc"], komprimiert=True)
        a["huelle_roh"] = os.path.join(cls.tmp, "huelle_roh.ffpfs")
        _huelle(exfat, a["huelle_roh"], komprimiert=False)
        a["huelle_pfsc"] = os.path.join(cls.tmp, "huelle_pfsc.ffpfsc")
        _huelle(exfat, a["huelle_pfsc"], komprimiert=True)
        a["pfs_in_pfs"] = os.path.join(cls.tmp, "pfs_in_pfs.ffpfsc")
        _huelle(a["flach_pfsc"], a["pfs_in_pfs"], komprimiert=True)
        a["doppelt"] = os.path.join(cls.tmp, "doppelt.ffpfsc")
        _huelle(a["huelle_pfsc"], a["doppelt"], komprimiert=True)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)


class BauformenTests(_Grundlage):
    #: Name -> (Art, Huellen)
    ERWARTET = {
        "flach_roh": ("pfs", 0), "flach_pfsc": ("pfs", 0), "huelle_roh": ("exfat", 1), "huelle_pfsc": ("exfat", 1),
        "pfs_in_pfs": ("pfs", 1), "doppelt": ("exfat", 2),
    }

    def test_liste_groesse_inhalt_in_jeder_bauform(self) -> None:
        for name, pfad in self.abbilder.items():
            with self.subTest(bauform=name), sb.PfsBaum(pfad) as baum:
                dateien = baum.dateien()
                self.assertEqual({d.rel: d.groesse for d in dateien}, {k: len(v) for k, v in SPIEL.items()})
                self.assertEqual([d.rel for d in dateien], sorted(SPIEL))
                self.assertEqual(self.ERWARTET[name], (baum.art, baum.ebenen))
                for d in dateien:
                    self.assertEqual(SPIEL[d.rel], _inhalt(d, 70_001), d.rel)

    def test_wie_der_ordner(self) -> None:
        ordner = sb.OrdnerBaum(self.spiel)
        for name, pfad in self.abbilder.items():
            with self.subTest(bauform=name), sb.PfsBaum(pfad) as baum:
                self.assertEqual([(d.rel, d.groesse) for d in ordner.dateien()], [(d.rel, d.groesse) for d in baum.dateien()])

    def test_stuecke_in_jeder_groesse(self) -> None:
        """Die Stuecke sind hoechstens so gross wie verlangt und ergeben zusammen genau die Datei."""
        for name in ("huelle_pfsc", "flach_pfsc", "flach_roh"):
            with self.subTest(bauform=name), sb.PfsBaum(self.abbilder[name]) as baum:
                gross = next(d for d in baum.dateien() if d.rel == "data/text.txt")
                for stueck in (1000, 4096, 65536, 100_000, sb.LESE_STUECK):
                    teile = list(gross.lesen(stueck))
                    self.assertLessEqual(max(len(t) for t in teile), stueck, stueck)
                    self.assertEqual(SPIEL["data/text.txt"], b"".join(teile))

    def test_leere_verzeichnisse_in_jeder_bauform(self) -> None:
        """Ein exFAT-Abbild kennt leere Verzeichnisse; das flache PFS von MkPFS (``build_pfs``) legt sie gar nicht erst an."""
        mit_leerem = sorted(["Daten", "data", "data/b", "savedata_leer", "sce_sys"])
        ohne_leeres = sorted(["Daten", "data", "data/b", "sce_sys"])
        for name, pfad in self.abbilder.items():
            erwartet = mit_leerem if self.ERWARTET[name][0] == "exfat" else ohne_leeres
            with self.subTest(bauform=name), sb.PfsBaum(pfad) as baum:
                baum.dateien()
                self.assertEqual(erwartet, baum.ordner())

    def test_leere_datei(self) -> None:
        for name in ("flach_pfsc", "huelle_pfsc"):
            with self.subTest(bauform=name), sb.PfsBaum(self.abbilder[name]) as baum:
                leer = baum.suchen()["data/b/leer.txt"]
                self.assertEqual(0, leer.groesse)
                self.assertEqual(b"", _inhalt(leer))

    def test_ignorierte_namen_fallen_weg(self) -> None:
        with sb.PfsBaum(self.abbilder["huelle_pfsc"], ignoriert=lambda t: t == "Daten") as baum:
            self.assertNotIn("Daten/Zebra.dat", baum.suchen())
            self.assertIn("data/a.pak", baum.suchen())

    def test_ausgabe_gleicht_dem_ordner_unter_dem_mkpfs_filter(self) -> None:
        with sb.PfsBaum(self.abbilder["flach_roh"], ignoriert=is_ignored_name) as baum:
            self.assertEqual(sorted(SPIEL), [d.rel for d in baum.dateien()])


class FadenTests(_Grundlage):
    def test_mehrere_faeden_lesen_zugleich(self) -> None:
        for name in ("huelle_pfsc", "flach_pfsc", "doppelt"):
            with self.subTest(bauform=name), sb.PfsBaum(self.abbilder[name]) as baum:
                dateien = baum.dateien()
                fehler: list[str] = []

                def lesen(teil: list) -> None:
                    try:
                        for d in teil:
                            if _inhalt(d, 50_000) != SPIEL[d.rel]:
                                fehler.append(d.rel)
                    except Exception as exc:  # noqa: BLE001
                        fehler.append(repr(exc))

                faeden = [threading.Thread(target=lesen, args=(dateien[i::4],)) for i in range(4)]
                faeden += [threading.Thread(target=lesen, args=(dateien,))]
                for f in faeden:
                    f.start()
                for f in faeden:
                    f.join()
                self.assertEqual([], fehler)

    def test_jeder_faden_oeffnet_seine_datei(self) -> None:
        baum = sb.PfsBaum(self.abbilder["huelle_pfsc"])
        baum.dateien()
        zahl = {"n": 0}

        def lesen() -> None:
            _inhalt(baum.suchen()["eboot.bin"])
            zahl["n"] += 1

        vorher = len(baum._griffe)
        faeden = [threading.Thread(target=lesen) for _ in range(3)]
        for f in faeden:
            f.start()
        for f in faeden:
            f.join()
        self.assertEqual(3, zahl["n"])
        self.assertEqual(vorher + 3, len(baum._griffe))
        baum.schliessen()
        self.assertEqual(0, len(baum._griffe))


class StempelTests(_Grundlage):
    def test_unveraendert_und_geaendert(self) -> None:
        kopie = os.path.join(self.tmp, "stempel.ffpfsc")
        shutil.copyfile(self.abbilder["huelle_pfsc"], kopie)
        self.addCleanup(lambda: os.path.exists(kopie) and os.remove(kopie))
        with sb.PfsBaum(kopie) as baum:
            baum.dateien()
            self.assertTrue(baum.unveraendert())
            self.assertEqual(baum.stempel(), baum.stempel())
            with open(kopie, "ab") as fh:
                fh.write(b"\0")
            self.assertFalse(baum.unveraendert())

    def test_abbild_verschwindet(self) -> None:
        kopie = os.path.join(self.tmp, "weg.ffpfsc")
        shutil.copyfile(self.abbilder["flach_roh"], kopie)
        baum = sb.PfsBaum(kopie)
        baum.dateien()
        baum.schliessen()
        os.remove(kopie)
        self.assertFalse(baum.unveraendert())


class FehlerTests(_Grundlage):
    def _kopie(self, name: str, daten: bytes) -> str:
        pfad = os.path.join(self.tmp, name)
        Path(pfad).write_bytes(daten)
        self.addCleanup(lambda: os.path.exists(pfad) and os.remove(pfad))
        return pfad

    def test_keine_datei(self) -> None:
        with self.assertRaises(sb.BaumFehler):
            sb.PfsBaum(os.path.join(self.tmp, "gibts_nicht.ffpfsc"))

    def test_weder_pfs_noch_exfat(self) -> None:
        pfad = self._kopie("zufall.ffpfsc", _zufall(300_000, 9))
        with self.assertRaises(sb.BaumFehler):
            sb.PfsBaum(pfad).dateien()

    def test_leere_datei(self) -> None:
        pfad = self._kopie("leer.ffpfsc", b"")
        with self.assertRaises(sb.BaumFehler):
            sb.PfsBaum(pfad).dateien()

    def test_abgeschnitten(self) -> None:
        """Ein Abbild, dem hinten etwas fehlt, ist ein Fehler - entweder beim Aufbau oder beim Lesen der Dateien, nie stille Auslassung."""
        for name in ("flach_roh", "huelle_pfsc", "flach_pfsc"):
            voll = Path(self.abbilder[name]).read_bytes()
            pfad = self._kopie("kurz_%s.ffpfsc" % name, voll[: len(voll) // 2])
            with self.subTest(bauform=name):
                with self.assertRaises(sb.BaumFehler):
                    with sb.PfsBaum(pfad) as baum:
                        for d in baum.dateien():
                            _inhalt(d)

    def test_kaputter_pfsc_block(self) -> None:
        """Ein beschaedigter Datenblock wird beim Lesen als BaumFehler gemeldet, nicht als falsche Bytes."""
        voll = bytearray(Path(self.abbilder["huelle_pfsc"]).read_bytes())
        for i in range(len(voll) // 2, len(voll) // 2 + 4000):
            voll[i] ^= 0xFF
        pfad = self._kopie("kaputt.ffpfsc", bytes(voll))
        with self.assertRaises(sb.BaumFehler):
            with sb.PfsBaum(pfad) as baum:
                for d in baum.dateien():
                    _inhalt(d)

    def test_zu_viele_ebenen(self) -> None:
        vorher = sb.PfsBaum.MAX_EBENEN
        sb.PfsBaum.MAX_EBENEN = 1
        self.addCleanup(setattr, sb.PfsBaum, "MAX_EBENEN", vorher)
        with self.assertRaises(sb.BaumFehler):
            sb.PfsBaum(self.abbilder["doppelt"]).dateien()

    def test_geschlossener_baum_liest_nicht_mehr(self) -> None:
        baum = sb.PfsBaum(self.abbilder["huelle_roh"])
        datei = baum.dateien()[0]
        baum.schliessen()
        with self.assertRaises(sb.BaumFehler):
            _inhalt(datei)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class ZstdPackTests(_Grundlage):
    """Der Weg bis zum Pack: Byte-Gleichheit mit dem Pack aus dem Ordner."""

    def _pack(self, baum, name: str) -> dict[str, bytes]:
        auswahl = z.auswahl_aus_liste(sb.einordnen(baum))
        archiv = z.archiv_id_ableiten(auswahl, 3)
        messung = z.messen(baum, auswahl, stufe=3, arbeiter=2, archiv_id=archiv)
        ziel = os.path.join(self.tmp, name)
        z.strom_in_ordner(baum, auswahl, messung, ziel, arbeiter=2)
        aus: dict[str, bytes] = {}
        for rel in sorted(os.listdir(ziel)):
            aus[rel] = Path(ziel, rel).read_bytes()
        shutil.rmtree(ziel)
        return aus

    def test_pack_gleicht_dem_aus_dem_ordner(self) -> None:
        referenz = self._pack(sb.OrdnerBaum(self.spiel), "ref")
        self.assertTrue(referenz)
        for name in ("flach_pfsc", "huelle_pfsc", "doppelt"):
            with self.subTest(bauform=name), sb.PfsBaum(self.abbilder[name]) as baum:
                self.assertEqual(referenz, self._pack(baum, "pack_" + name))


class MkpfsSchnittstelleTests(unittest.TestCase):
    """Wenn MkPFS einmal ersetzt wird und eine der privaten Stellen verschwindet, sagt es dieser Test - nicht erst ein Lauf."""

    def test_benutzte_namen_sind_da(self) -> None:
        from mkpfs import pfs
        for name in ("_LogicalFileView", "parse_image_header", "parse_image_inodes", "parse_superroot_and_indexes",
                     "build_tree_from_uroot", "iter_inode_logical_blocks"):
            self.assertTrue(hasattr(pfs, name), name)
        from mkpfs.compression import CompressionError
        self.assertTrue(issubclass(CompressionError, Exception))


if __name__ == "__main__":
    unittest.main()
