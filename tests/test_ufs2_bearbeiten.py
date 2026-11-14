# -*- coding: utf-8 -*-
"""Direkt aendern in einem UFS2-Abbild (``utils/ufs2_bearbeiten.py``, 14.11.2026).

Die Abbilder baut der eigene Schreiber (byteweise wie UFS2Tool ``newfs -D``) in drei Profilen: 64K/64K (das Programm), 32K/4K und
4K/512 (Fragmente, Schwanzfragmente, mehrblockige Ordner). Gemessen wird:

* die eigene Pruefung (:meth:`Ufs2Abbild.pruefen`: Bloecke, Inodes, Bitmaps, Zaehler, Verweiszahlen) - sie ist auf einem frischen Abbild
  leer, das heisst: Der Editor rechnet die Zaehler genau so wie der Schreiber;
* das Zuruecklesen mit dem eigenen Leser (``spielbaum.Ufs2Baum``);
* das Journal (Abbruch mitten im Schreiben, liegengebliebenes Journal);
* mit UFS2Tool als unabhaengigem Zeugen: ``extract`` (eigener Leser von UFS2Tool), ``fsck_ufs -fn`` (dessen Textausgabe: der
  Rueckgabewert ist auch bei Fehlern 0) und die **Fuellprobe** - UFS2Tool legt eine Datei an, die den freien Platz fuellt. Steht ein
  belegter Block faelschlich als frei in der Bitmap, ueberschreibt UFS2Tool ihn, und ``extract`` zeigt es. Beide Zeugen haben eine
  Gegenprobe (sie muessen einen absichtlich eingebauten Fehler finden); ``fsck_ufs`` allein uebersieht einen solchen Block.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                          # noqa: E402
pruefumgebung.umlenken("ufs2_bearbeiten")

from ps5_validator.utils import abbild_journal as aj           # noqa: E402
from ps5_validator.utils import spielbaum as sb                # noqa: E402
from ps5_validator.utils import ufs2_bearbeiten as ub          # noqa: E402
from ps5_validator.utils import ufs2_schreiber as w            # noqa: E402

PROFILE = {
    "64K/64K": w.Ufs2Profil(65536, 65536, 4096, 0, 262144),
    "32K/4K": w.Ufs2Profil(32768, 4096, 4096, 8, 0),
    "4K/512": w.Ufs2Profil(4096, 512, 512, 8, 4096),
}


def _werkzeug() -> "str | None":
    if sys.platform != "win32":
        return None
    pfad = ROOT / "UFS2Tool-4.1" / "win-x64" / "UFS2Tool.exe"
    return str(pfad) if pfad.is_file() else None


def _ufs2tool(*args: str) -> "tuple[int, str]":
    lauf = subprocess.run([_werkzeug(), *args], capture_output=True, text=True, timeout=900,
                          env=dict(os.environ, __COMPAT_LAYER="RunAsInvoker"))
    return lauf.returncode, lauf.stdout + lauf.stderr


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
    "Media/text.txt": b"Hallo Welt\n" * 60_000,
    "data/klein.cfg": b"a=1\n",
    "data/leer.bin": b"",
    "data/gross.bin": _zufall(3_000_000, 5),
}
for _d in range(4):
    for _f in range(25):
        SPIEL["viele_%d/datei_mit_einem_recht_langen_namen_%03d.dat" % (_d, _f)] = _zufall(100 + _f * 37, 100 + _d * 50 + _f)


class _Grundlage(unittest.TestCase):
    profil = PROFILE["64K/64K"]

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ufs2bearbeiten_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.erwartet = dict(SPIEL)
        self.bild = self.bauen(SPIEL, ["leer_ordner"])

    def bauen(self, inhalte: "dict[str, bytes]", leere=(), profil: "w.Ufs2Profil | None" = None) -> str:
        ziel = os.path.join(self.tmp, "spiel_%d.ffpkg" % len(os.listdir(self.tmp)))
        w.planen([(r, len(d), (lambda d=d: iter([d]))) for r, d in inhalte.items()], leere,
                 profil=profil or self.profil).schreiben(ziel)
        return ziel

    def datei(self, name: str, daten: bytes) -> str:
        pfad = os.path.join(self.tmp, name)
        Path(pfad).write_bytes(daten)
        return pfad

    def gelesen(self, bild: "str | None" = None) -> "tuple[dict[str, bytes], list[str]]":
        with sb.Ufs2Baum(bild or self.bild) as baum:
            return {d.rel: b"".join(d.lesen()) for d in baum.dateien()}, baum.ordner()

    def pruefen(self, bild: "str | None" = None) -> None:
        with ub.Ufs2Abbild(bild or self.bild) as a:
            self.assertEqual([], a.pruefen())
        dateien, _ordner = self.gelesen(bild)
        self.assertEqual(sorted(self.erwartet), sorted(dateien))
        for rel, daten in self.erwartet.items():
            self.assertEqual(hashlib.sha256(daten).hexdigest(), hashlib.sha256(dateien[rel]).hexdigest(), rel)

    def mischung(self, a: ub.Ufs2Abbild) -> None:
        """Eine gemischte Aenderung, nach der ``self.erwartet`` stimmt."""
        gross = _zufall(2_500_000, 77)
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
        a.hinzufuegen("data/neu.bin", self.datei("klein.bin", klein))
        self.erwartet["data/neu.bin"] = klein
        a.ordner_anlegen("neuer_ordner")
        a.hinzufuegen("neuer_ordner/drin.bin", os.path.join(self.tmp, "gross.bin"))
        self.erwartet["neuer_ordner/drin.bin"] = gross
        for i in range(30):
            rel = "viele_0/zusatz_mit_langem_namen_damit_der_ordner_waechst_%03d.bin" % i
            a.hinzufuegen(rel, os.path.join(self.tmp, "klein.bin"))
            self.erwartet[rel] = klein


class FrischTests(_Grundlage):
    def test_ein_frisches_abbild_ist_in_allen_profilen_ohne_befund(self) -> None:
        """Die Zaehler, die der Editor aus der Bitmap rechnet, sind byteweise die des Schreibers (sonst gaebe es hier Befunde)."""
        for name, profil in PROFILE.items():
            with self.subTest(name):
                bild = self.bauen(SPIEL, ["leer", "a/b/c"], profil=profil)
                with ub.Ufs2Abbild(bild) as a:
                    self.assertEqual([], a.pruefen())
                    self.assertGreater(a.freie_bytes(), 0, "Die Abbilder des Programms haben freien Platz")

    def test_auflisten(self) -> None:
        with ub.Ufs2Abbild(self.bild) as a:
            wurzel = {n: (o, g) for n, o, g in a.auflisten("")}
            self.assertEqual((False, len(SPIEL["eboot.bin"])), wurzel["eboot.bin"])
            self.assertTrue(wurzel["data"][0])
            self.assertTrue(wurzel["leer_ordner"][0])
            self.assertEqual({"klein.cfg", "leer.bin", "gross.bin"}, {n for n, _o, _g in a.auflisten("data")})

    def test_kein_ufs2(self) -> None:
        anderes = self.datei("x.ffpkg", bytes(200_000))
        with self.assertRaises(ub.Ufs2BearbeitenFehler):
            ub.Ufs2Abbild(anderes)
        self.assertFalse(ub.ist_ufs2(anderes))
        self.assertTrue(ub.ist_ufs2(self.bild))


class AenderungenTests(_Grundlage):
    def test_gemischte_aenderung_in_allen_profilen(self) -> None:
        for name, profil in PROFILE.items():
            with self.subTest(name):
                self.erwartet = dict(SPIEL)
                bild = self.bauen(SPIEL, ["leer_ordner"], profil=profil)
                with ub.Ufs2Abbild(bild) as a:
                    self.mischung(a)
                    a.speichern()
                self.pruefen(bild)
                self.assertFalse(os.path.exists(aj.journal_pfad(bild)))

    def test_vor_dem_speichern_aendert_sich_an_der_datei_nichts(self) -> None:
        vorher = Path(self.bild).read_bytes()
        with ub.Ufs2Abbild(self.bild) as a:
            self.mischung(a)
            self.assertEqual({"klein_neu.cfg", "leer.bin", "neu.bin"}, {n for n, _o, _g in a.auflisten("data")})
        self.assertEqual(vorher, Path(self.bild).read_bytes())

    def test_umbenennen_auf_einen_vergebenen_namen_ohne_gross_klein(self) -> None:
        with ub.Ufs2Abbild(self.bild) as a:
            with self.assertRaises(ub.Ufs2BearbeitenFehler):
                a.umbenennen("data/klein.cfg", "LEER.BIN")
            a.umbenennen("data/klein.cfg", "KLEIN.cfg")                  # nur die Schreibweise: erlaubt
            self.erwartet["data/KLEIN.cfg"] = self.erwartet.pop("data/klein.cfg")
            a.speichern()
        self.pruefen()

    def test_unzulaessige_namen(self) -> None:
        with ub.Ufs2Abbild(self.bild) as a:
            for name in ("", "a/b", "..", "nicht_ascii_ä.bin", "con", "x" * 256, "frage?.bin"):
                with self.subTest(name=name):
                    with self.assertRaises(ub.Ufs2BearbeitenFehler):
                        a.umbenennen("data/klein.cfg", name)
            with self.assertRaises(ub.Ufs2BearbeitenFehler):
                a.hinzufuegen("fehlt/x.bin", self.datei("x.bin", b"x"))
            with self.assertRaises(ub.Ufs2BearbeitenFehler):
                a.loeschen("gibt_es_nicht")
            with self.assertRaises(ub.Ufs2BearbeitenFehler):
                a.ersetzen("data", self.datei("y.bin", b"y"))

    def test_kein_platz_aendert_nichts(self) -> None:
        with ub.Ufs2Abbild(self.bild) as a:
            frei = a.freie_bytes()
            zu_gross = self.datei("zu_gross.bin", bytes(frei + 10 * 65536))
            vorher = (bytes(a.sb), bytes(a.cs), a.auflisten("data"))
            with self.assertRaises(ub.Ufs2PlatzFehlt):
                a.hinzufuegen("data/zu_gross.bin", zu_gross)
            with self.assertRaises(ub.Ufs2PlatzFehlt):
                a.ersetzen("data/klein.cfg", zu_gross)
            self.assertEqual(vorher, (bytes(a.sb), bytes(a.cs), a.auflisten("data")), "Die Transaktion nimmt alles zurueck")
            self.assertEqual(frei, a.freie_bytes())
            a.speichern()
        self.pruefen()

    def test_zweimal_dieselbe_datei_ersetzen(self) -> None:
        """Der erste vorgemerkte Inhalt darf nicht mehr geschrieben werden (seine Bloecke sind wieder frei)."""
        with ub.Ufs2Abbild(self.bild) as a:
            a.ersetzen("data/gross.bin", self.datei("eins.bin", _zufall(1_000_000, 11)))
            a.ersetzen("data/gross.bin", self.datei("zwei.bin", _zufall(700_000, 12)))
            a.hinzufuegen("data/drei.bin", self.datei("drei.bin", _zufall(900_000, 13)))
            a.speichern()
        self.erwartet["data/gross.bin"] = _zufall(700_000, 12)
        self.erwartet["data/drei.bin"] = _zufall(900_000, 13)
        self.pruefen()

    def test_loeschen_und_den_platz_gleich_wieder_nutzen(self) -> None:
        """Reicht der Platz nur mit den Bloecken einer geloeschten Datei, kommen sie dran - und ihr alter Inhalt ins Journal."""
        with ub.Ufs2Abbild(self.bild) as a:
            frei = a.freie_bytes()
            a.loeschen("data/gross.bin")
            neu = _zufall(frei + 1_000_000, 21)
            a.hinzufuegen("data/neu_gross.bin", self.datei("neu_gross.bin", neu))
            gesehen: "list[list]" = []
            echt = aj.journal_schreiben

            def mitschreiben(pfad, stellen, **kw):
                gesehen.append(list(stellen))
                return echt(pfad, stellen, **kw)
            with mock.patch.object(ub, "journal_schreiben", side_effect=mitschreiben):
                a.speichern()
        del self.erwartet["data/gross.bin"]
        self.erwartet["data/neu_gross.bin"] = neu
        self.pruefen()
        gesichert = sum(len(alt) for _o, alt in gesehen[0])
        self.assertGreater(gesichert, 65536, "Der wiederbenutzte Platz der geloeschten Datei muss im Journal stehen")

    def test_ordner_waechst_ueber_zwoelf_bloecke_in_den_indirekten_block(self) -> None:
        bild = self.bauen(SPIEL, [], profil=PROFILE["4K/512"])
        klein = self.datei("k.bin", b"k")
        with ub.Ufs2Abbild(bild) as a:
            for i in range(700):
                rel = "data/ein_ziemlich_langer_dateiname_fuer_einen_grossen_ordner_%04d.bin" % i
                a.hinzufuegen(rel, klein)
                self.erwartet[rel] = b"k"
            a.speichern()
            v = a._verzeichnis("data")
            self.assertGreater(len(v.bloecke), 12)
            self.assertTrue(v.meta, "Ueber zwoelf Bloecke braucht der Ordner einen Zeigerblock")
        self.pruefen(bild)

    def test_hinter_cg_initediblk_werden_inodes_angelegt(self) -> None:
        bild = self.bauen({"eboot.bin": b"x", "sce_sys/param.json": b"{}"}, [], profil=PROFILE["4K/512"])
        self.erwartet = {"eboot.bin": b"x", "sce_sys/param.json": b"{}"}
        klein = self.datei("k.bin", b"inode")
        with ub.Ufs2Abbild(bild) as a:
            vorher = struct.unpack_from("<i", a._cg_kopf(0), 0x78)[0]
            for i in range(40):
                a.hinzufuegen("f%02d.bin" % i, klein)
                self.erwartet["f%02d.bin" % i] = b"inode"
            a.speichern()
            self.assertGreater(struct.unpack_from("<i", a._cg_kopf(0), 0x78)[0], vorher)
        self.pruefen(bild)

    def test_leere_datei_und_ordner_mit_inhalt_loeschen(self) -> None:
        with ub.Ufs2Abbild(self.bild) as a:
            a.loeschen("data/leer.bin")
            a.loeschen("leer_ordner")
            a.hinzufuegen("leer2.bin", self.datei("leer.bin", b""))
            a.speichern()
        del self.erwartet["data/leer.bin"]
        self.erwartet["leer2.bin"] = b""
        self.pruefen()
        self.assertNotIn("leer_ordner", self.gelesen()[1])


def _fingerabdruck(bild: str) -> str:
    """SHA-256 des Abbilds ohne die freien Fragmente: Was in freien Bloecken steht, gehoert zu keinem Zustand des Dateisystems (neue
    Daten kommen bewusst ohne Journal dorthin - zurueckgenommen wird die Bitmap, die sie wieder frei macht)."""
    roh = bytearray(Path(bild).read_bytes())
    with ub.Ufs2Abbild(bild) as a:
        for cg in range(a.ncg):
            kopf = a._cg_kopf(cg)
            off = struct.unpack_from("<i", kopf, 0x60)[0]
            for lokal in range(struct.unpack_from("<i", kopf, 0x14)[0]):
                if kopf[off + (lokal >> 3)] & (1 << (lokal & 7)):
                    frag = cg * a.fpg + lokal
                    roh[frag * a.fs:(frag + 1) * a.fs] = bytes(a.fs)
    return hashlib.sha256(roh).hexdigest()


class JournalTests(_Grundlage):
    def test_ein_fehler_mitten_im_schreiben_laesst_das_abbild_wie_vorher(self) -> None:
        vorher = _fingerabdruck(self.bild)
        with ub.Ufs2Abbild(self.bild) as a:
            self.mischung(a)
            echt = a._daten_schreiben
            zaehler = {"n": 0}

            def kaputt(*args, **kw):
                zaehler["n"] += 1
                if zaehler["n"] == 2:
                    raise OSError("Platte voll (gestellt)")
                return echt(*args, **kw)
            a._daten_schreiben = kaputt
            with self.assertRaises(OSError):
                a.speichern()
        self.assertEqual(vorher, _fingerabdruck(self.bild))
        self.assertFalse(os.path.exists(aj.journal_pfad(self.bild)))
        self.erwartet = dict(SPIEL)
        self.pruefen()

    def test_ein_liegengebliebenes_journal_wird_beim_oeffnen_zurueckgespielt(self) -> None:
        vorher = _fingerabdruck(self.bild)
        echt = os.fsync
        aufrufe = {"n": 0}

        def strom_weg(fd: int) -> None:
            aufrufe["n"] += 1
            if aufrufe["n"] == 1:
                return echt(fd)                                         # das Journal kommt noch auf die Platte
            raise OSError("Strom weg (gestellt)")                       # beim Abbild nicht mehr
        with ub.Ufs2Abbild(self.bild) as a:
            self.mischung(a)
            with mock.patch.object(ub, "journal_zurueckspielen", return_value=False), \
                    mock.patch.object(os, "fsync", side_effect=strom_weg):
                with self.assertRaises(OSError):
                    a.speichern()
        self.assertTrue(os.path.exists(aj.journal_pfad(self.bild)), "Das Journal muss liegen bleiben")
        self.assertNotEqual(vorher, _fingerabdruck(self.bild), "Es wurde schon geschrieben")
        with ub.Ufs2Abbild(self.bild) as a:
            self.assertEqual([], a.pruefen())
        self.assertEqual(vorher, _fingerabdruck(self.bild))
        self.assertFalse(os.path.exists(aj.journal_pfad(self.bild)))
        self.erwartet = dict(SPIEL)
        self.pruefen()


_FSCK_FERTIG = re.compile(r"^\d+ files, \d+ used, \d+ free")


def _fsck_befunde(bild: str) -> "list[str]":
    """Die Fehlerzeilen von ``fsck_ufs -fn`` (der Rueckgabewert ist auch bei Fehlern 0)."""
    rc, aus = _ufs2tool("fsck_ufs", "-fn", bild)
    zeilen = [z.strip() for z in aus.splitlines() if z.strip()]
    befunde = [z for z in zeilen if not z.startswith("**") and not _FSCK_FERTIG.match(z)]
    if rc != 0:
        befunde.append("Rueckgabewert %d" % rc)
    return befunde


@unittest.skipUnless(_werkzeug(), "UFS2Tool (ohne Erhoehung startbar) fehlt")
class Ufs2ToolZeugenTests(_Grundlage):
    """UFS2Tool als unabhaengiger Zeuge: ``fsck_ufs``, ``extract`` und die Fuellprobe."""

    def extrahiert(self, bild: str) -> "dict[str, bytes]":
        raus = os.path.join(self.tmp, "raus_%d" % len(os.listdir(self.tmp)))
        rc, aus = _ufs2tool("extract", bild, raus)
        self.assertEqual(0, rc, aus[-300:])
        gefunden = {}
        for wurzel, _o, dateien in os.walk(raus):
            for d in dateien:
                p = os.path.join(wurzel, d)
                gefunden[os.path.relpath(p, raus).replace("\\", "/")] = Path(p).read_bytes()
        return gefunden

    def fuellprobe(self, bild: str) -> "list[str]":
        """Fuellt den freien Platz mit UFS2Tool ``add`` (ganze Bloecke, ohne die Mindestreserve ``minfree``, abzueglich der Zeigerbloecke)
        und gibt die Dateien zurueck, die danach nicht mehr stimmen."""
        with ub.Ufs2Abbild(bild) as a:
            ganze = sum(struct.unpack_from("<i", a.cs, cg * 16 + 4)[0] for cg in range(a.ncg))
            reserve = struct.unpack_from("<q", a.sb, 0x440)[0] * struct.unpack_from("<i", a.sb, 0x3C)[0] // 100 // a.fpb
            nutzbar = ganze - reserve
            bloecke = max(0, nutzbar - nutzbar // (a.nindir - 1) - 8)
            bs = a.bs
        fueller = _zufall(bloecke * bs, 99)
        rc, aus = _ufs2tool("add", bild, "/fueller_der_probe.bin", self.datei("fueller.bin", fueller))
        self.assertEqual(0, rc, aus[-300:])
        gefunden = self.extrahiert(bild)
        erwartet = dict(self.erwartet, **{"fueller_der_probe.bin": fueller})
        return sorted(k for k in erwartet if gefunden.get(k) != erwartet[k]) + sorted(set(gefunden) - set(erwartet))

    def test_gemischte_aenderung_besteht_alle_zeugen(self) -> None:
        for name, profil in PROFILE.items():
            with self.subTest(name):
                self.erwartet = dict(SPIEL)
                bild = self.bauen(SPIEL, ["leer_ordner"], profil=profil)
                with ub.Ufs2Abbild(bild) as a:
                    self.mischung(a)
                    a.speichern()
                self.assertEqual([], _fsck_befunde(bild))
                gefunden = self.extrahiert(bild)
                self.assertEqual(sorted(self.erwartet), sorted(gefunden))
                self.assertEqual([], [k for k in self.erwartet if gefunden[k] != self.erwartet[k]])
                self.assertEqual([], self.fuellprobe(bild))

    def test_gegenprobe_fsck_findet_falsche_zaehler(self) -> None:
        with ub.Ufs2Abbild(self.bild) as a:
            offset = (a.cblkno) * a.fs + 0x18 + 4                       # cg 0: cs_nbfree
        with open(self.bild, "r+b") as fh:
            fh.seek(offset)
            wert = struct.unpack("<i", fh.read(4))[0]
            fh.seek(offset)
            fh.write(struct.pack("<i", wert + 1))
        self.assertTrue(_fsck_befunde(self.bild), "fsck muss den verfaelschten Zaehler melden")

    def test_gegenprobe_fuellprobe_findet_einen_falsch_freien_block(self) -> None:
        """Ein belegter Block, als frei markiert und mit passenden Zaehlern: ``fsck_ufs`` sieht ihn nicht, die Fuellprobe schon."""
        with ub.Ufs2Abbild(self.bild) as a:
            v = a._verzeichnis("data")
            e = a._finde(v, "gross.bin")
            daten, _m = a._bloecke(a._inode(e.ino))
            a._frags_setzen(daten[5], a.fpb, True)
            a._zaehler_auffrischen()
            for offset, neu in a._stellen():
                a._fh.seek(offset)
                a._fh.write(neu)
            a._fh.flush()
        self.assertEqual([], _fsck_befunde(self.bild), "fsck_ufs uebersieht ihn (deshalb gibt es die Fuellprobe)")
        with ub.Ufs2Abbild(self.bild) as a:
            self.assertTrue(a.pruefen(), "Die eigene Pruefung findet ihn")
        self.assertIn("data/gross.bin", self.fuellprobe(self.bild))


if __name__ == "__main__":
    unittest.main()
