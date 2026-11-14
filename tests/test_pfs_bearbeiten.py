# -*- coding: utf-8 -*-
"""Direkt aendern in einem PFS-Abbild (``utils/pfs_bearbeiten.py``, 14.11.2026).

Flache ``.ffpfs`` baut der Strom des Programms (``abbild_strom.ffpfs_schreiben`` -> MkPFS ``build_pfs``, wie ``mkpfs pack folder --raw
--no-compress``). Gemessen wird nach jeder Aenderung:

* mit MkPFS als Zeuge: ``verify_pfs_image(source=Ordner)`` gegen einen Ordner mit denselben Aenderungen (Kopf, Ueberlappungen,
  Inode-Zahl, Baum, Pfadtabelle samt Kollisionen, verwaiste Inodes **und** jeder Dateiinhalt);
* gegen einen **frischen** MkPFS-Bau desselben Baums: Superroot, Pfadtabelle, Kollisionsliste, jeder Ordnerinhalt, Inode-Zahl und
  Verweiszahlen muessen Byte fuer Byte gleich sein - der Editor nummeriert und schreibt die Verwaltung wie MkPFS;
* mit dem Leser des Programms (``spielbaum.PfsBaum``).

Dazu das Journal (Abbruch, liegengebliebenes Journal samt Kuerzen des gewachsenen Abbilds), die Grenzen (leere Ordner, Inode-Tabelle)
und die Huelle um ein exFAT (``oeffnen`` -> ``ExfatAbbild`` mit Versatz; komprimiert wird abgelehnt).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                            # noqa: E402
pruefumgebung.umlenken("pfs_bearbeiten")

from mkpfs import consts                                         # noqa: E402
from mkpfs import pfs as mp                                      # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image                  # noqa: E402

from ps5_validator.utils import abbild_journal as aj              # noqa: E402
from ps5_validator.utils import abbild_strom as ast               # noqa: E402
from ps5_validator.utils import exfat_bearbeiten as eb            # noqa: E402
from ps5_validator.utils import pfs_bearbeiten as pb              # noqa: E402
from ps5_validator.utils import spielbaum as sb                   # noqa: E402


def _zufall(n: int, startwert: int = 1) -> bytes:
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


SPIEL = {
    "eboot.bin": b"\x7fELF" + bytes(2000),
    "sce_sys/param.json": b'{"titleId":"PPSA04263"}',
    "sce_sys/icon0.png": _zufall(9000, 2),
    "Media/text.txt": b"Hallo Welt\n" * 30_000,
    "data/klein.cfg": b"a=1\n",
    "data/leer.bin": b"",
    "data/B0": b"gleicher FPT-Hash wie data/AO",
    "data/gross.bin": _zufall(1_500_000, 5),
}
for _d in range(4):
    for _f in range(20):
        SPIEL["viele_%d/datei_mit_einem_recht_langen_namen_%03d.dat" % (_d, _f)] = _zufall(100 + _f * 37, 100 + _d * 50 + _f)


def _struktur(pfad: str) -> dict:
    """Was ein frischer MkPFS-Bau gleich haben muss."""
    with open(pfad, "rb") as fh:
        kopf = pb._kopf_lesen(fh)
        inodes = pb._inodes_lesen(fh, kopf)
        sr = pb._superroot(fh, kopf)
        fh.seek((1 + kopf.inode_bloecke) * kopf.bs)
        superroot = fh.read(kopf.bs)
        fpt = pb._inhalt(fh, kopf, inodes[sr["flat_path_table"]])
        koll = pb._inhalt(fh, kopf, inodes[sr["collision_resolver"]]) if "collision_resolver" in sr else None
        ordner: "dict[str, bytes]" = {}

        def gehen(nr: int, rel: str) -> None:
            blob = pb._inhalt(fh, kopf, inodes[nr])
            eintraege = pb.dirents_lesen(blob)
            ordner[rel] = blob[:sum(((len(n) + 17 + 7) // 8) * 8 for _i, _t, n in eintraege)]
            for ino, typ, name in eintraege:
                if typ == pb.DIRENT_ORDNER:
                    gehen(ino, (rel + "/" + name) if rel else name)
        gehen(sr["uroot"], "")
        nlink = {i: struct.unpack_from("<H", x.roh, 2)[0] for i, x in enumerate(inodes) if x.modus & pb.INODE_ORDNER}
    return {"anzahl": kopf.inode_anzahl, "superroot": superroot, "fpt": fpt, "koll": koll, "ordner": ordner, "nlink": nlink}


class _Grundlage(unittest.TestCase):
    bs = 65536

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pfsbearbeiten_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.erwartet = dict(SPIEL)
        self.bild = self.bauen(SPIEL)

    def bauen(self, inhalte: "dict[str, bytes]", bs: "int | None" = None) -> str:
        ziel = os.path.join(self.tmp, "spiel_%d.ffpfs" % len(os.listdir(self.tmp)))
        ast.ffpfs_schreiben([(r, len(d), (lambda d=d: iter([d]))) for r, d in inhalte.items()], ziel, block_size=bs or self.bs)
        return ziel

    def datei(self, name: str, daten: bytes) -> str:
        pfad = os.path.join(self.tmp, name)
        Path(pfad).write_bytes(daten)
        return pfad

    def zeugen(self, bild: "str | None" = None, bs: "int | None" = None) -> None:
        """MkPFS gegen einen Ordner, der Leser des Programms, die Pruefung des Editors, der Vergleich mit einem frischen Bau."""
        bild = bild or self.bild
        quelle = os.path.join(self.tmp, "quelle_%d" % len(os.listdir(self.tmp)))
        for rel, daten in self.erwartet.items():
            p = os.path.join(quelle, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Path(p).write_bytes(daten)
        bericht = mp.verify_pfs_image(Path(bild), source=Path(quelle))
        self.assertEqual([], bericht.errors)
        with sb.PfsBaum(bild) as baum:
            gelesen = {d.rel: b"".join(d.lesen(1 << 20)) for d in baum.dateien()}
        self.assertEqual(sorted(self.erwartet), sorted(gelesen))
        self.assertEqual([], [k for k in self.erwartet if gelesen[k] != self.erwartet[k]])
        with pb.PfsAbbild(bild) as a:
            self.assertEqual([], a.pruefen())
        frisch = self.bauen(self.erwartet, bs)
        mein, ihr = _struktur(bild), _struktur(frisch)
        for teil in mein:
            self.assertEqual(ihr[teil], mein[teil], "%s weicht vom frischen MkPFS-Bau ab" % teil)

    def mischung(self, a: pb.PfsAbbild) -> None:
        gross = _zufall(2_000_000, 77)
        klein = _zufall(1234, 78)
        a.umbenennen("data/klein.cfg", "klein_neu.cfg")
        self.erwartet["data/klein_neu.cfg"] = self.erwartet.pop("data/klein.cfg")
        a.umbenennen("viele_1", "Viele_Eins_mit_einem_viel_laengeren_Namen")
        for k in [k for k in self.erwartet if k.startswith("viele_1/")]:
            self.erwartet["Viele_Eins_mit_einem_viel_laengeren_Namen/" + k.split("/", 1)[1]] = self.erwartet.pop(k)
        a.loeschen("viele_2")
        for k in [k for k in self.erwartet if k.startswith("viele_2/")]:
            del self.erwartet[k]
        a.loeschen("data/gross.bin")
        del self.erwartet["data/gross.bin"]
        a.ersetzen("Media/text.txt", self.datei("gross.bin", gross))
        self.erwartet["Media/text.txt"] = gross
        a.ordner_anlegen("neuer_ordner")
        a.hinzufuegen("neuer_ordner/drin.bin", self.datei("klein.bin", klein))
        self.erwartet["neuer_ordner/drin.bin"] = klein
        for i in range(60):
            rel = "viele_0/zusatz_mit_langem_namen_damit_der_ordner_waechst_%03d.bin" % i
            a.hinzufuegen(rel, os.path.join(self.tmp, "klein.bin"))
            self.erwartet[rel] = klein


class FrischTests(_Grundlage):
    def test_ein_frisches_abbild_ist_ohne_befund_und_listet_sich(self) -> None:
        with pb.PfsAbbild(self.bild) as a:
            self.assertEqual([], a.pruefen())
            wurzel = {n: (o, g) for n, o, g in a.auflisten("")}
            self.assertEqual((False, len(SPIEL["eboot.bin"])), wurzel["eboot.bin"])
            self.assertTrue(wurzel["data"][0])
            self.assertTrue(a.waechst)

    def test_ohne_aenderung_wird_nichts_geschrieben(self) -> None:
        vorher = Path(self.bild).read_bytes()
        with pb.PfsAbbild(self.bild) as a:
            a.speichern()
        self.assertEqual(vorher, Path(self.bild).read_bytes())

    def test_kein_pfs(self) -> None:
        anderes = self.datei("x.ffpfs", bytes(100_000))
        self.assertFalse(pb.ist_pfs(anderes))
        self.assertTrue(pb.ist_pfs(self.bild))
        with self.assertRaises(pb.PfsBearbeitenFehler):
            pb.PfsAbbild(anderes)


class AenderungenTests(_Grundlage):
    def test_gemischte_aenderung_in_zwei_blockgroessen(self) -> None:
        for bs in (65536, 16384):
            with self.subTest(bs=bs):
                self.erwartet = dict(SPIEL)
                bild = self.bauen(SPIEL, bs)
                laenge = os.path.getsize(bild)
                with pb.PfsAbbild(bild) as a:
                    self.mischung(a)
                    a.speichern()
                self.assertGreater(os.path.getsize(bild), laenge, "Neue Inhalte kommen hinten an: Das Abbild waechst")
                self.assertFalse(os.path.exists(aj.journal_pfad(bild)))
                self.zeugen(bild, bs)

    def test_vor_dem_speichern_aendert_sich_an_der_datei_nichts(self) -> None:
        vorher = Path(self.bild).read_bytes()
        with pb.PfsAbbild(self.bild) as a:
            self.mischung(a)
        self.assertEqual(vorher, Path(self.bild).read_bytes())

    def test_eine_kollision_der_pfadtabelle_entsteht_und_verschwindet(self) -> None:
        self.assertEqual(pb.fpt_hash("/data/AO", True), pb.fpt_hash("/data/B0", True))
        with pb.PfsAbbild(self.bild) as a:
            a.hinzufuegen("data/AO", self.datei("ao.bin", b"AO"))
            a.speichern()
        self.erwartet["data/AO"] = b"AO"
        self.assertIsNotNone(_struktur(self.bild)["koll"])
        self.zeugen()
        with pb.PfsAbbild(self.bild) as a:
            a.loeschen("data/B0")
            a.speichern()
        del self.erwartet["data/B0"]
        self.assertIsNone(_struktur(self.bild)["koll"])
        self.zeugen()

    def test_die_inode_tabelle_waechst_in_die_verwaltungszone(self) -> None:
        bild = self.bauen(SPIEL, 16384)
        with open(bild, "rb") as fh:
            vorher = pb._kopf_lesen(fh).inode_bloecke
        klein = self.datei("k.bin", b"k")
        with pb.PfsAbbild(bild) as a:
            for i in range(150):
                a.hinzufuegen("data/f%03d.bin" % i, klein)
                self.erwartet["data/f%03d.bin" % i] = b"k"
            a.speichern()
        with open(bild, "rb") as fh:
            self.assertGreater(pb._kopf_lesen(fh).inode_bloecke, vorher)
        self.zeugen(bild, 16384)

    def test_ist_die_verwaltungszone_voll_bleibt_alles_wie_es_war(self) -> None:
        vorher = Path(self.bild).read_bytes()
        klein = self.datei("k.bin", b"k")
        with pb.PfsAbbild(self.bild) as a:
            platz = (a._zone_ende - 2) * (a.bs // pb.INODE_GROESSE)
            for i in range(platz - a.kopf.inode_anzahl + 1):
                a.hinzufuegen("data/f%05d.bin" % i, klein)
            with self.assertRaises(pb.PfsPlatzFehlt):
                a.speichern()
        self.assertEqual(vorher, Path(self.bild).read_bytes())
        self.assertFalse(os.path.exists(aj.journal_pfad(self.bild)))

    def test_leere_ordner_werden_beim_speichern_abgelehnt(self) -> None:
        vorher = Path(self.bild).read_bytes()
        with pb.PfsAbbild(self.bild) as a:
            a.ordner_anlegen("leer")
            with self.assertRaises(pb.PfsBearbeitenFehler):
                a.speichern()
            a.hinzufuegen("leer/jetzt_nicht_mehr.bin", self.datei("j.bin", b"j"))
            a.speichern()
        self.assertNotEqual(vorher, Path(self.bild).read_bytes())
        self.erwartet["leer/jetzt_nicht_mehr.bin"] = b"j"
        self.zeugen()

    def test_zweimal_dieselbe_datei_ersetzen_und_kleine_ersetzungen(self) -> None:
        with pb.PfsAbbild(self.bild) as a:
            a.ersetzen("data/gross.bin", self.datei("eins.bin", _zufall(900_000, 11)))
            a.ersetzen("data/gross.bin", self.datei("zwei.bin", _zufall(70_000, 12)))
            a.ersetzen("eboot.bin", self.datei("e.bin", b"\x7fELF neu"))
            a.ersetzen("data/leer.bin", self.datei("nicht_leer.bin", b"jetzt mit Inhalt"))
            a.ersetzen("data/klein.cfg", self.datei("leer.bin", b""))
            a.speichern()
        self.erwartet.update({"data/gross.bin": _zufall(70_000, 12), "eboot.bin": b"\x7fELF neu", "data/leer.bin": b"jetzt mit Inhalt",
                              "data/klein.cfg": b""})
        self.zeugen()

    def test_freier_platz_aus_dem_letzten_lauf_wird_wieder_benutzt(self) -> None:
        with pb.PfsAbbild(self.bild) as a:
            a.loeschen("data/gross.bin")
            a.speichern()
            self.assertGreaterEqual(a.freie_bytes(), 1_500_000, "Nach dem Speichern ist der Platz eine Luecke")
        del self.erwartet["data/gross.bin"]
        laenge = os.path.getsize(self.bild)
        with pb.PfsAbbild(self.bild) as a:
            a.hinzufuegen("data/wieder.bin", self.datei("w.bin", _zufall(1_000_000, 31)))
            a.speichern()
        self.erwartet["data/wieder.bin"] = _zufall(1_000_000, 31)
        self.assertEqual(laenge, os.path.getsize(self.bild), "Die Luecke reichte: Das Abbild waechst nicht")
        self.zeugen()

    def test_unzulaessige_namen_und_pfade(self) -> None:
        with pb.PfsAbbild(self.bild) as a:
            for name in ("", "a/b", "..", "nicht_ascii_ä.bin", "con", "x" * 256, "frage?.bin"):
                with self.subTest(name=name):
                    with self.assertRaises(pb.PfsBearbeitenFehler):
                        a.umbenennen("data/klein.cfg", name)
            with self.assertRaises(pb.PfsBearbeitenFehler):
                a.umbenennen("data/klein.cfg", "LEER.BIN")
            with self.assertRaises(pb.PfsBearbeitenFehler):
                a.hinzufuegen("fehlt/x.bin", self.datei("x.bin", b"x"))
            with self.assertRaises(pb.PfsBearbeitenFehler):
                a.loeschen("gibt_es_nicht")
            with self.assertRaises(pb.PfsBearbeitenFehler):
                a.ersetzen("data", self.datei("y.bin", b"y"))
            with self.assertRaises(OSError):
                a.hinzufuegen("data/z.bin", os.path.join(self.tmp, "gibt_es_nicht.bin"))
            self.assertNotIn("z.bin", {n for n, _o, _g in a.auflisten("data")})


class JournalTests(_Grundlage):
    def test_ein_fehler_mitten_im_schreiben_laesst_das_abbild_wie_vorher(self) -> None:
        vorher = _struktur(self.bild)
        laenge = os.path.getsize(self.bild)
        with pb.PfsAbbild(self.bild) as a:
            self.mischung(a)
            echt = a._daten_schreiben
            zaehler = {"n": 0}

            def kaputt(k):
                zaehler["n"] += 1
                if zaehler["n"] == 3:
                    raise OSError("Platte voll (gestellt)")
                return echt(k)
            a._daten_schreiben = kaputt
            with self.assertRaises(OSError):
                a.speichern()
            self.assertIn("data", {n for n, _o, _g in a.auflisten("")}, "Der Baum im Speicher bleibt bedienbar")
        self.assertEqual(laenge, os.path.getsize(self.bild), "Das gewachsene Abbild wird wieder gekuerzt")
        self.assertEqual(vorher, _struktur(self.bild))
        self.assertFalse(os.path.exists(aj.journal_pfad(self.bild)))
        self.erwartet = dict(SPIEL)
        self.zeugen()

    def test_ein_liegengebliebenes_journal_wird_beim_oeffnen_zurueckgespielt(self) -> None:
        vorher = _struktur(self.bild)
        laenge = os.path.getsize(self.bild)
        echt = os.fsync
        aufrufe = {"n": 0}

        def strom_weg(fd: int) -> None:
            aufrufe["n"] += 1
            if aufrufe["n"] == 1:
                return echt(fd)
            raise OSError("Strom weg (gestellt)")
        with pb.PfsAbbild(self.bild) as a:
            self.mischung(a)
            with mock.patch.object(pb, "journal_zurueckspielen", return_value=False), \
                    mock.patch.object(os, "fsync", side_effect=strom_weg):
                with self.assertRaises(OSError):
                    a.speichern()
        self.assertTrue(os.path.exists(aj.journal_pfad(self.bild)))
        self.assertGreater(os.path.getsize(self.bild), laenge)
        with pb.PfsAbbild(self.bild) as a:
            self.assertEqual([], a.pruefen())
        self.assertEqual(laenge, os.path.getsize(self.bild))
        self.assertEqual(vorher, _struktur(self.bild))
        self.erwartet = dict(SPIEL)
        self.zeugen()


class HuelleTests(unittest.TestCase):
    """Ein PFS um genau ein exFAT: Das innere Abbild wird ueber den exFAT-Editor geaendert, das PFS bleibt unberuehrt."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="pfshuelle_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        quelle = os.path.join(self.tmp, "quelle")
        self.inhalt = {"eboot.bin": b"\x7fELF" + bytes(3000), "sce_sys/param.json": b'{"titleId":"PPSA00001"}',
                       "data/a.bin": _zufall(300_000, 3), "data/b.bin": _zufall(5000, 4)}
        for rel, daten in self.inhalt.items():
            p = os.path.join(quelle, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Path(p).write_bytes(daten)
        self.exfat = os.path.join(self.tmp, "innen.exfat")
        with open(self.exfat, "wb") as fh:
            for stueck in iter_exfat_image(Path(quelle)):
                fh.write(stueck)

    def huelle(self, komprimiert: bool) -> str:
        ziel = os.path.join(self.tmp, "huelle.ffpfsc" if komprimiert else "huelle.ffpfs")
        mp.build_pfs_stream_single_file(source_file=Path(self.exfat), output_path=Path(ziel), block_size=65536,
                                        pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0,
                                        min_file_gain=0, min_compress_size=0, cpu_count=1, compress=komprimiert)
        return ziel

    def gelesen(self, bild: str) -> "dict[str, bytes]":
        with sb.PfsBaum(bild) as baum:
            return {d.rel: b"".join(d.lesen(1 << 20)) for d in baum.dateien()}

    def test_das_innere_exfat_wird_geaendert_und_das_pfs_bleibt_gueltig(self) -> None:
        bild = self.huelle(False)
        basis, laenge = pb.huelle_um_exfat(bild)
        self.assertEqual(os.path.getsize(self.exfat), laenge)
        kopf_vorher = Path(bild).read_bytes()[:basis]
        editor = pb.oeffnen(bild)
        try:
            self.assertIsInstance(editor, eb.ExfatAbbild)
            self.assertEqual("pfs-exfat", editor.art)
            editor.umbenennen("data/b.bin", "b_neu.bin")
            editor.loeschen("data/a.bin")
            editor.hinzufuegen("data/c.bin", self._quelle(b"neu" * 1000))
            editor.speichern()
            self.assertEqual([], editor.pruefen())
        finally:
            editor.schliessen()
        erwartet = dict(self.inhalt)
        erwartet["data/b_neu.bin"] = erwartet.pop("data/b.bin")
        del erwartet["data/a.bin"]
        erwartet["data/c.bin"] = b"neu" * 1000
        self.assertEqual(erwartet, self.gelesen(bild))
        self.assertEqual(kopf_vorher, Path(bild).read_bytes()[:basis], "Vor dem inneren Abbild aendert sich kein Byte")
        bericht = mp.inspect_pfs_image(Path(bild), verify_payloads=True)
        self.assertEqual([], bericht.errors)

    def _quelle(self, daten: bytes) -> str:
        pfad = os.path.join(self.tmp, "q_%d.bin" % len(os.listdir(self.tmp)))
        Path(pfad).write_bytes(daten)
        return pfad

    def test_ein_liegengebliebenes_journal_der_huelle_nennt_stellen_in_der_aeusseren_datei(self) -> None:
        bild = self.huelle(False)
        vorher = hashlib.sha256(Path(bild).read_bytes()).hexdigest()
        echt = os.fsync
        aufrufe = {"n": 0}

        def strom_weg(fd: int) -> None:
            aufrufe["n"] += 1
            if aufrufe["n"] == 1:
                return echt(fd)
            raise OSError("Strom weg (gestellt)")
        editor = pb.oeffnen(bild)
        try:
            editor.loeschen("data/a.bin")
            editor.ersetzen("data/b.bin", self._quelle(_zufall(200_000, 9)))
            with mock.patch.object(eb, "journal_zurueckspielen", return_value=False), \
                    mock.patch.object(os, "fsync", side_effect=strom_weg):
                with self.assertRaises(OSError):
                    editor.speichern()
        finally:
            editor.schliessen()
        self.assertNotEqual(vorher, hashlib.sha256(Path(bild).read_bytes()).hexdigest())
        self.assertTrue(aj.journal_zurueckspielen(bild))
        self.assertEqual(vorher, hashlib.sha256(Path(bild).read_bytes()).hexdigest())
        self.assertEqual(self.inhalt, self.gelesen(bild))

    def test_eine_komprimierte_huelle_wird_abgelehnt(self) -> None:
        bild = self.huelle(True)
        self.assertIsNone(pb.huelle_um_exfat(bild))
        vorher = Path(bild).read_bytes()
        with self.assertRaises(pb.PfsBearbeitenFehler):
            pb.oeffnen(bild)
        self.assertEqual(vorher, Path(bild).read_bytes())


if __name__ == "__main__":
    unittest.main()
