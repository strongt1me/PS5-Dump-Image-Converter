# -*- coding: utf-8 -*-
"""exFAT-Schreiber aus einer Dateiliste und das Abbild aus Lesebaum + zstd-Strom, ohne Zwischenordner (Stufe 3, Etappe 3).

Massstab ist der bisherige Weg: Dasselbe Spiel als Ordner (lose Dateien + von ``packen`` geschriebene Packdateien) durch
``iter_exfat_image`` ergibt dieselben Bytes wie ``abbild_strom`` - auch aus einer ``.exfat`` als Quelle und mit mehreren Baendern.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("abbild_strom")

from mkpfs import exfat_writer as w                          # noqa: E402

from ps5_validator.utils import abbild_strom as ast          # noqa: E402
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
    "eboot.bin": b"ELF" + bytes(1000),
    "sce_sys/param.json": b'{"titleId":"PPSA99999"}',
    "fakelib/libSceAmpr.sprx": b"x" * 100,
    "dlc_emu.ini": b"[dlc]\n",
    "Media/text.txt": b"Hallo Welt\n" * 100_000,
    "Media/zufall.bin": _zufall(300_000),
    "data/genau.bin": b"A" * z.CHUNK_SIZE,
    "data/plus_eins.bin": b"B" * (z.CHUNK_SIZE + 1),
    "data/klein.cfg": b"a=1\n",
    "data/leer.bin": b"",
    "data/gross.bin": _zufall(1_500_000, 7),
}


def _schreiben(wurzel: str, inhalte: dict[str, bytes]) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)


def _bytes(erzeuger) -> bytes:
    return b"".join(erzeuger)


def _liste(inhalte: dict[str, bytes]) -> list:
    return [(rel, len(d), (lambda d=d: iter([d[i:i + 100_000] for i in range(0, len(d), 100_000)] or [])))
            for rel, d in inhalte.items()]


class ListeSchreiberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="exfatliste_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_wie_der_ordner(self) -> None:
        ordner = os.path.join(self.tmp, "o")
        _schreiben(ordner, SPIEL)
        aus_ordner = _bytes(w.iter_exfat_image(Path(ordner)))
        aus_liste = _bytes(w.iter_exfat_image_liste(_liste(SPIEL)))
        self.assertEqual(hashlib.sha256(aus_ordner).hexdigest(), hashlib.sha256(aus_liste).hexdigest())

    def test_reihenfolge_der_eintraege_ist_gleich(self) -> None:
        eintraege = list(reversed(_liste(SPIEL)))
        a = _bytes(w.iter_exfat_image_liste(_liste(SPIEL)))
        b = _bytes(w.iter_exfat_image_liste(eintraege))
        self.assertEqual(a, b)

    def test_leere_dateien_werden_nie_geoeffnet(self) -> None:
        def nie() -> "iter":
            raise AssertionError("geoeffnet")
        _bytes(w.iter_exfat_image_liste([("a.bin", 3, lambda: iter([b"abc"])), ("leer.bin", 0, nie)]))

    def test_dateireihenfolge(self) -> None:
        eintraege = [("z.bin", 1, None), ("b/x.bin", 1, None), ("B2/y.bin", 1, None), ("a.bin", 1, None), ("leer", 0, None),
                     ("b/a/q.bin", 1, None)]
        # Preorder, je Ordner nach name.lower(): a.bin, b (-> a (-> q.bin), x.bin), B2 (-> y.bin), leer(0 Bytes), z.bin
        self.assertEqual(["a.bin", "b/a/q.bin", "b/x.bin", "B2/y.bin", "z.bin"], w.dateireihenfolge_liste(eintraege))

    def test_abgelehnt(self) -> None:
        offen = lambda: iter([b"x"])                              # noqa: E731
        for eintraege, text in [
            ([("ü.bin", 1, offen)], "non-ASCII"),
            ([("a/../b.bin", 1, offen)], "unusable"),
            ([("a//b.bin", 1, offen)], "unusable"),
            ([("a\\b.bin", 1, offen)], "unusable"),
            ([("a.bin", 1, offen), ("A.BIN", 1, offen)], "collide"),
            ([("d/x.bin", 1, offen), ("D/y.bin", 1, offen)], "collide"),
            ([("a", 1, offen), ("a/b.bin", 1, offen)], "collide"),
        ]:
            with self.assertRaises(w.ExfatBuildError, msg=str(eintraege)) as ctx:
                list(w.iter_exfat_image_liste(eintraege))
            self.assertIn(text, str(ctx.exception))

    def test_systemdateien_des_betriebssystems_fallen_weg(self) -> None:
        offen = lambda: iter([b"x"])                              # noqa: E731
        mit = _bytes(w.iter_exfat_image_liste([("a.bin", 1, offen), (".DS_Store", 1, offen), ("d/._x", 1, offen)]))
        ohne = _bytes(w.iter_exfat_image_liste([("a.bin", 1, offen)]))
        self.assertEqual(mit, ohne)

    def test_zu_kurz_und_zu_lang(self) -> None:
        with self.assertRaises(w.ExfatBuildError):
            _bytes(w.iter_exfat_image_liste([("a.bin", 10, lambda: iter([b"abc"]))]))
        with self.assertRaises(w.ExfatBuildError):
            _bytes(w.iter_exfat_image_liste([("a.bin", 2, lambda: iter([b"abc"]))]))


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class AbbildStromTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="abbildstrom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.spiel = os.path.join(self.tmp, "spiel")
        _schreiben(self.spiel, SPIEL)
        self.auswahl = z.dateien_auswaehlen(self.spiel)
        self.archiv = z.archiv_id_ableiten(self.auswahl, 3)

    def abbild(self, baum, *, behalten: bool = False, **kw) -> bytes:
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        return _bytes(ast.abbild_strom(
            baum, self.auswahl, messung, iter_liste=w.iter_exfat_image_liste, reihenfolge_liste=w.dateireihenfolge_liste,
            originale_behalten=behalten, arbeiter=2, **kw))

    def ordnerabbild(self, behalten: bool = False) -> bytes:
        """Der bisherige Weg: Ordner mit losen Dateien (+ Originalen) und den Packdateien, durch den Ordnerschreiber."""
        ziel = os.path.join(self.tmp, "ordnerweg")
        os.makedirs(ziel, exist_ok=True)
        gepackt = {r for r, _g in self.auswahl.gepackt}
        for rel, daten in SPIEL.items():
            if behalten or rel not in gepackt:
                _schreiben(ziel, {rel: daten})
        packs = os.path.join(self.tmp, "ordnerpacks")
        z.packen(self.spiel, packs, self.auswahl, stufe=3, arbeiter=2, archiv_id=self.archiv)
        for name in os.listdir(packs):
            shutil.copy2(os.path.join(packs, name), os.path.join(ziel, name))
        return _bytes(w.iter_exfat_image(Path(ziel)))

    def test_wie_der_ordnerweg(self) -> None:
        self.assertEqual(self.ordnerabbild(), self.abbild(sb.OrdnerBaum(self.spiel)))

    def test_mit_originalen(self) -> None:
        self.assertEqual(self.ordnerabbild(behalten=True), self.abbild(sb.OrdnerBaum(self.spiel), behalten=True))

    def test_mehrere_baender(self) -> None:
        with mock.patch.object(z, "VOLUME_LIMIT", 400_000):
            ordner = self.ordnerabbild()
            strom = self.abbild(sb.OrdnerBaum(self.spiel))
        self.assertEqual(ordner, strom)

    def test_aus_exfat_quelle_und_wieder_lesbar(self) -> None:
        quelle = os.path.join(self.tmp, "quelle.exfat")
        with open(quelle, "wb") as fh:
            fh.write(_bytes(w.iter_exfat_image(Path(self.spiel))))
        ziel = os.path.join(self.tmp, "ziel.exfat")
        with sb.ExfatBaum(quelle) as baum:
            with open(ziel, "wb") as fh:
                fh.write(self.abbild(baum))
        self.assertEqual(self.ordnerabbild(), Path(ziel).read_bytes())
        # Das neue Abbild ist ein gueltiges Spiel: lose Dateien da, Originale weg, Packs vollstaendig und gleich der Quelle.
        with sb.ExfatBaum(ziel) as neu:
            dateien = neu.suchen()
            self.assertIn("eboot.bin", dateien)
            self.assertNotIn("Media/zufall.bin", dateien)
            self.assertIn("ampr_zstd.index", dateien)
            packs = os.path.join(self.tmp, "gelesene_packs")
            os.makedirs(packs)
            for rel, d in dateien.items():
                if z.ist_packname(rel):
                    Path(packs, rel).write_bytes(b"".join(d.lesen()))
            z.pruefen(packs, self.spiel)

    def test_fortschritt_und_layout(self) -> None:
        layout: list[int] = []
        werte: list[float] = []
        daten = self.abbild(sb.OrdnerBaum(self.spiel), on_layout=layout.append, fortschritt=werte.append)
        self.assertEqual([len(daten)], layout)
        self.assertAlmostEqual(1.0, werte[-1])

    def test_falsche_reihenfolge_vor_dem_ersten_byte(self) -> None:
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            ast.reihenfolge_pruefen(["ampr_zstd.index", "ampr_zstd-000.pak"], ["ampr_zstd-000.pak", "ampr_zstd.index"])
        self.assertIn("Reihenfolge", str(ctx.exception))
        ast.reihenfolge_pruefen(["x", "ampr_zstd-000.pak", "y", "ampr_zstd.index"],
                                ["ampr_zstd-000.pak", "ampr_zstd.index"])           # andere Dateien dazwischen: in Ordnung

    def test_bestehende_packnamen_in_der_quelle(self) -> None:
        _schreiben(self.spiel, {"ampr_zstd.index": b"alt"})
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            self.abbild(sb.OrdnerBaum(self.spiel))
        self.assertEqual("ampr_zstd.ausgabe_belegt", str(ctx.exception))

    def test_quelle_geaendert_bricht_ab(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        voll = os.path.join(self.spiel, "Media", "zufall.bin")
        daten = bytearray(Path(voll).read_bytes())
        daten[1000] ^= 1
        Path(voll).write_bytes(bytes(daten))
        with self.assertRaises(z.ZstdPackFehler):
            _bytes(ast.abbild_strom(baum, self.auswahl, messung, iter_liste=w.iter_exfat_image_liste,
                                    reihenfolge_liste=w.dateireihenfolge_liste))

    def test_abbruch_schliesst_den_strom(self) -> None:
        import threading
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        vorher = threading.active_count()
        erzeuger = ast.abbild_strom(baum, self.auswahl, messung, iter_liste=w.iter_exfat_image_liste,
                                    reihenfolge_liste=w.dateireihenfolge_liste, arbeiter=2)
        for i, _stueck in enumerate(erzeuger):
            if i == 5:
                break
        erzeuger.close()
        self.assertLessEqual(threading.active_count(), vorher + 1)


if __name__ == "__main__":
    unittest.main()
