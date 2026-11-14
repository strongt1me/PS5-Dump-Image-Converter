# -*- coding: utf-8 -*-
"""UFS2-Schreiber (``.ffpkg`` aus einer Dateiliste, Stufe 3, Etappe 13).

Massstab ist UFS2Tool: ``UFS2Tool newfs -D <Ordner>`` und der Schreiber ergeben fuer dieselben Dateien **byteweise dasselbe** Abbild
(nur Zeitstempel und ``fs_id`` gibt UFS2Tool aus Uhr und Prozessnummer vor - sie werden aus dem Referenzabbild uebernommen). Das gilt in
beiden Profilen des Programms (64 KiB/64 KiB mit ``-i 262144``, 32 KiB/4 KiB mit den Vorgaben), mit leeren Verzeichnissen,
Dateien ueber mehreren Zylindergruppen, einfach und zweifach indirekten Bloecken, Fragmenten und mehrblockigen Verzeichnissen.
Daneben pruefen Tests ohne UFS2Tool das Abbild mit dem eigenen Leser (``ufs2_dateisystem``) und die Fehlerfaelle.
"""
from __future__ import annotations

import hashlib
import os
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

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ufs2_schreiber")

from ps5_validator.utils import abbild_strom as ast          # noqa: E402
from ps5_validator.utils import ffpkg_support as ffs         # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402
from ps5_validator.utils import ufs2_schreiber as w          # noqa: E402


def _werkzeug() -> "str | None":
    if sys.platform != "win32":
        return None
    pfad = ROOT / "UFS2Tool-4.1" / "win-x64" / "UFS2Tool.exe"
    return str(pfad) if pfad.is_file() else None


def _zufall(n: int, startwert: int = 1) -> bytes:
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


def _liste(inhalte: "dict[str, bytes]", aufrufe: "list[str] | None" = None) -> list:
    def oeffner(rel: str, d: bytes):
        def lesen():
            if aufrufe is not None:
                aufrufe.append(rel)
            return iter([d[i:i + 70_000] for i in range(0, len(d), 70_000)])
        return lesen
    return [(rel, len(d), oeffner(rel, d)) for rel, d in inhalte.items()]


def _ordner_schreiben(wurzel: str, inhalte: "dict[str, bytes]", leere=()) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        Path(voll).write_bytes(daten)
    for rel in leere:
        os.makedirs(os.path.join(wurzel, *rel.split("/")), exist_ok=True)


SPIEL = {
    "eboot.bin": b"\x7fELF" + bytes(2000),
    "sce_sys/param.json": b'{"titleId":"PPSA04263"}',
    "sce_sys/icon0.png": _zufall(9000, 2),
    "Media/text.txt": b"Hallo Welt\n" * 60_000,
    "data/klein.cfg": b"a=1\n",
    "data/leer.bin": b"",
}


def _viele(ordner: int, je_ordner: int) -> "dict[str, bytes]":
    inh = {"eboot.bin": b"\x7fELF" + bytes(500), "sce_sys/param.json": b"{}"}
    for d in range(ordner):
        for f in range(je_ordner):
            inh["Ordner_%03d/unter_%d/datei_mit_langem_namen_%04d.dat" % (d, d % 3, f)] = _zufall((d * 37 + f * 101) % 5000, 10 + d * 7 + f)
    return inh


PRIMAER = (ffs.primary_newfs_profile(), w.Ufs2Profil(65536, 65536, 4096, 0, 262144))
KOMPAT = (ffs.compatibility_newfs_profile(), w.Ufs2Profil(32768, 4096, 4096, 8, 0))


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ufs2schreiber_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def pfad(self, name: str) -> str:
        return os.path.join(self.tmp, name)

    def bauen(self, inhalte, leere=(), profil=None, **kw) -> str:
        plan = w.planen(_liste(inhalte), leere, profil=profil or PRIMAER[1], **kw)
        ziel = self.pfad("mein_%d.ffpkg" % len(os.listdir(self.tmp)))
        plan.schreiben(ziel)
        return ziel

    def gelesen(self, ziel: str) -> "tuple[dict[str, bytes], list[str]]":
        with sb.Ufs2Baum(ziel) as baum:
            return {d.rel: b"".join(d.lesen()) for d in baum.dateien()}, baum.ordner()


@unittest.skipUnless(_werkzeug(), "UFS2Tool (ohne Erhoehung startbar) fehlt")
class ParitaetMitUfs2ToolTests(_Grundlage):
    """Dasselbe Abbild wie ``UFS2Tool newfs -D`` - Byte fuer Byte."""

    def vergleichen(self, inhalte, leere, profile) -> None:
        newfs_profil, mein_profil = profile
        ordner = self.pfad("spiel")
        _ordner_schreiben(ordner, inhalte, leere)
        ref = self.pfad("ref.ffpkg")
        lauf = subprocess.run(ffs.build_newfs_directory_command(_werkzeug(), ordner, ref, profile=newfs_profil),
                              capture_output=True, text=True, timeout=600, env=dict(os.environ, __COMPAT_LAYER="RunAsInvoker"))
        if lauf.returncode != 0:
            self.skipTest("UFS2Tool newfs scheiterte: %s" % (lauf.stdout or lauf.stderr)[-200:])
        rd = Path(ref).read_bytes()
        sbk = rd[w.SUPERBLOCK_OFFSET:w.SUPERBLOCK_OFFSET + 8192]
        zeit = struct.unpack_from("<q", sbk, 0x430)[0]
        id0, id1 = struct.unpack_from("<II", sbk, 0x90)
        g = w._Geometrie(mein_profil, len(rd))
        wurzel_inode = rd[g.iblkno * g.fs + 2 * 256:g.iblkno * g.fs + 3 * 256]
        zeit_inodes = struct.unpack_from("<q", wurzel_inode, 0x20)[0]
        plan = w.planen(_liste(inhalte), leere, profil=mein_profil, zeit=zeit, zeit_inodes=zeit_inodes, fs_id=(id0, id1))
        mein = self.pfad("mein.ffpkg")
        plan.schreiben(mein)
        md = Path(mein).read_bytes()
        self.assertEqual(len(rd), len(md), "Abbildgroesse")
        if rd != md:
            unterschied = next(i for i in range(len(rd)) if rd[i] != md[i])
            self.fail("Abbild weicht ab ab Byte %d (Fragment %d)" % (unterschied, unterschied // g.fs))

    def test_klein_primaerprofil_mit_leerem_verzeichnis(self) -> None:
        self.vergleichen(SPIEL, ["savedata_leer"], PRIMAER)

    def test_klein_kompatprofil(self) -> None:
        self.vergleichen(SPIEL, ["savedata_leer"], KOMPAT)

    def test_viele_dateien_und_mehrblockige_verzeichnisse(self) -> None:
        self.vergleichen(_viele(40, 25), [], PRIMAER)
        self.vergleichen(_viele(40, 25), [], KOMPAT)

    def test_datei_ueber_mehrere_zylindergruppen_und_einfach_indirekt(self) -> None:
        gross = dict(SPIEL)
        gross["data/gross_a.bin"] = _zufall(3_000_000, 5)                  # ueber 12 Bloecke zu 64 KiB: einfach indirekt
        gross["data/gross_b.bin"] = _zufall(70 * 1024 * 1024, 6)           # 32 MiB je Gruppe: geht ueber Gruppen hinweg
        self.vergleichen(gross, [], PRIMAER)

    def test_zweifach_indirekt_und_fragmente(self) -> None:
        klein = (ffs.FfpkgNewfsProfile("t4k", 4096, 512, 512, 8, 4096).normalized(), w.Ufs2Profil(4096, 512, 512, 8, 4096))
        inh = dict(SPIEL)
        inh["data/doppelt.bin"] = _zufall(12 * 4096 + 512 * 4096 + 700_000, 8)     # 12 direkt + 512 einfach + Rest doppelt
        inh["data/halb.bin"] = _zufall(4096 * 3 + 100, 9)                          # endet mitten im Block: Fragmente
        self.vergleichen(inh, ["a/b/c"], klein)


@unittest.skipUnless(_werkzeug(), "UFS2Tool (ohne Erhoehung startbar) fehlt")
class FsckTests(_Grundlage):
    """Die Pruefung, die das Programm bisher nach jedem Bau machte (``fsck_ufs -n`` von UFS2Tool), besteht auch das selbst geschriebene Abbild."""

    def fsck(self, ziel: str) -> None:
        lauf = subprocess.run([_werkzeug(), "fsck_ufs", "-n", ziel], capture_output=True, text=True, timeout=900,
                              env=dict(os.environ, __COMPAT_LAYER="RunAsInvoker"))
        self.assertEqual(0, lauf.returncode, (lauf.stdout + lauf.stderr)[-400:])

    def test_verschiedene_abbilder(self) -> None:
        zweifach = dict(SPIEL)
        zweifach["data/doppelt.bin"] = _zufall(12 * 4096 + 512 * 4096 + 500_000, 8)
        for name, inhalte, leere, profil in (
                ("primaer klein", SPIEL, ["savedata_leer", "a/b/c"], PRIMAER[1]),
                ("kompat klein", SPIEL, ["x"], KOMPAT[1]),
                ("viele Dateien", _viele(30, 20), [], PRIMAER[1]),
                ("zweifach indirekt 4K/512", zweifach, [], w.Ufs2Profil(4096, 512, 512, 8, 4096)),
                ("nur Wurzeldateien", {"eboot.bin": b"x"}, [], PRIMAER[1])):
            with self.subTest(name):
                self.fsck(self.bauen(inhalte, leere, profil=profil))


class GroesseTests(_Grundlage):
    def test_abbildgroesse_stimmt_mit_dem_plan(self) -> None:
        for inhalte in (SPIEL, _viele(10, 10)):
            for _newfs, profil in (PRIMAER, KOMPAT):
                with self.subTest(dateien=len(inhalte), profil=profil.block_size):
                    plan = w.planen(_liste(inhalte), (), profil=profil)
                    self.assertEqual(plan.groesse, w.abbildgroesse(_liste(inhalte), (), profil))

    def test_mindestgroesse_sechzehn_bloecke(self) -> None:
        plan = w.planen(_liste({"a": b"x"}), (), profil=w.Ufs2Profil(65536, 65536, 4096, 0, 262144))
        self.assertGreaterEqual(plan.groesse, 16 * 65536)

    def test_geplant_wird_ohne_eine_datei_zu_lesen(self) -> None:
        aufrufe: list[str] = []
        w.planen(_liste(SPIEL, aufrufe), ["x"], profil=PRIMAER[1])
        self.assertEqual([], aufrufe)

    def test_verzeichnisbloecke_entstehen_erst_beim_schreiben(self) -> None:
        """Ein Verzeichnisblock (64 KiB, fast nur Leereintraege) liegt nicht als fertige Bytes im Plan: Hunderte Verzeichnisse
        waeren sonst bis zum Ende des Schreibens im Speicher (Pruefbericht 14.11.2026). Das Ergebnis bleibt dasselbe."""
        inhalte = _viele(12, 4)
        profil = PRIMAER[1]
        plan = w.planen(_liste(inhalte), ["leer/unter"], profil=profil)
        gross = [len(d) for _o, d in plan._regionen if isinstance(d, (bytes, bytearray)) and len(d) >= profil.block_size]
        self.assertLessEqual(len(gross), 1, "ausser dem Zusammenfassungsblock der Gruppen (``dblkno``) darf kein Block als Bytes im Plan liegen")
        self.assertGreaterEqual(sum(1 for _o, d in plan._regionen if callable(d)), plan.verzeichnisse)
        ziel = self.pfad("lazy.ffpkg")
        plan.schreiben(ziel)
        gelesen, ordner = self.gelesen(ziel)
        self.assertEqual(inhalte, gelesen)
        self.assertIn("leer/unter", ordner)


class RoundtripTests(_Grundlage):
    """Ohne UFS2Tool: Der eigene Leser liest, was der Schreiber gebaut hat."""

    def test_ein_beim_lesen_geschlossener_griff_ist_ein_baumfehler(self) -> None:
        """Ein Abbruch schliesst die Griffe, waehrend ein Lesefaden noch liest: ``ValueError`` wird ein ``BaumFehler`` (``Ufs2Baum``)."""
        ziel = self.bauen({"eboot.bin": b"\x7fELF", "data/gross.bin": _zufall(300_000, 9)})
        baum = sb.Ufs2Baum(ziel)
        datei = baum.suchen()["data/gross.bin"]
        erzeuger = datei.lesen(4096)
        next(erzeuger)                                          # der Griff dieses Fadens ist offen
        baum.schliessen()
        with self.assertRaises(sb.BaumFehler):
            list(erzeuger)

    def test_inhalt_und_leere_verzeichnisse(self) -> None:
        for name, profil in (("primaer", PRIMAER[1]), ("kompat", KOMPAT[1])):
            with self.subTest(name):
                ziel = self.bauen(SPIEL, ["savedata_leer", "a/b/c"], profil=profil)
                dateien, ordner = self.gelesen(ziel)
                self.assertEqual(SPIEL, dateien)
                for leer in ("savedata_leer", "a", "a/b", "a/b/c"):
                    self.assertIn(leer, ordner)

    def test_grosse_datei_mit_indirekten_bloecken(self) -> None:
        inh = {"eboot.bin": b"\x7fELF", "data/gross.bin": _zufall(13 * 65536 + 12345, 3)}      # 12 direkt + 1 indirekt + Rest
        dateien, _o = self.gelesen(self.bauen(inh))
        self.assertEqual(inh, dateien)

    def test_klein_blockgroesse_mit_doppelt_indirekt(self) -> None:
        profil = w.Ufs2Profil(4096, 512, 512, 8, 4096)
        inh = {"eboot.bin": b"\x7fELF", "d.bin": _zufall(12 * 4096 + 512 * 4096 + 300_000, 4), "h.bin": _zufall(4096 + 77, 5)}
        dateien, _o = self.gelesen(self.bauen(inh, profil=profil))
        self.assertEqual(inh, dateien)

    def test_namen_nur_in_der_schreibung_verschieden_gehen(self) -> None:
        inh = {"A.txt": b"gross", "a.txt": b"klein", "d/X.bin": b"1", "d/x.bin": b"2", "eboot.bin": b"e"}
        dateien, _o = self.gelesen(self.bauen(inh))
        self.assertEqual(inh, dateien)

    def test_gleiches_ergebnis_unabhaengig_von_der_reihenfolge_der_liste(self) -> None:
        zeit = dict(zeit=1_700_000_000, fs_id=(1, 2))
        a = Path(self.bauen(SPIEL, ["x"], **zeit)).read_bytes()
        plan = w.planen(list(reversed(_liste(SPIEL))), ["x"], profil=PRIMAER[1], **zeit)
        ziel = self.pfad("rueckwaerts.ffpkg")
        plan.schreiben(ziel)
        self.assertEqual(a, Path(ziel).read_bytes())

    def test_mehrere_gruppen_viele_dateien(self) -> None:
        inh = _viele(60, 20)
        plan = w.planen(_liste(inh), (), profil=PRIMAER[1])
        self.assertGreater(plan.gruppen, 1)
        ziel = self.pfad("viele.ffpkg")
        plan.schreiben(ziel)
        dateien, _o = self.gelesen(ziel)
        self.assertEqual(inh, dateien)

    def test_die_verwaltungsdaten_ueberlappen_sich_nicht(self) -> None:
        plan = w.planen(_liste(_viele(20, 10)), ["leer"], profil=PRIMAER[1])
        regionen = sorted(((o, d() if callable(d) else d) for o, d in plan._regionen), key=lambda r: r[0])
        for (o1, d1), (o2, _d2) in zip(regionen, regionen[1:]):
            self.assertLessEqual(o1 + len(d1), o2, "Regionen bei %d und %d ueberlappen" % (o1, o2))

    def test_superblock_und_zaehler(self) -> None:
        ziel = self.bauen(SPIEL, ["savedata_leer"], zeit=1_700_000_000, fs_id=(7, 8))
        daten = Path(ziel).read_bytes()
        sbk = daten[65536:65536 + 8192]
        self.assertEqual(0x19540119, struct.unpack_from("<i", sbk, 0x55C)[0])
        self.assertEqual(1_700_000_000, struct.unpack_from("<q", sbk, 0x430)[0])
        self.assertEqual((7, 8), struct.unpack_from("<II", sbk, 0x90))
        verzeichnisse = struct.unpack_from("<q", sbk, 0x3F0)[0]
        self.assertEqual(1 + 3 + 1, verzeichnisse)             # Wurzel, sce_sys, Media, data, savedata_leer
        self.assertEqual(65536, struct.unpack_from("<i", sbk, 0x30)[0])
        self.assertEqual(len(daten) // 65536, struct.unpack_from("<q", sbk, 0x438)[0])


class StromTests(_Grundlage):
    def test_reihenfolge_der_oeffner_ist_vorgebbar_und_jeder_wird_einmal_gerufen(self) -> None:
        aufrufe: list[str] = []
        plan = w.planen(_liste(SPIEL, aufrufe), (), profil=PRIMAER[1])
        plan.schreiben(self.pfad("a.ffpkg"), reihenfolge=["sce_sys/icon0.png", "eboot.bin"])
        self.assertEqual(["sce_sys/icon0.png", "eboot.bin"], aufrufe[:2])
        self.assertEqual(sorted(rel for rel, d in SPIEL.items() if d), sorted(aufrufe))       # die leere Datei nie

    def test_ein_nur_vorwaerts_lesbarer_strom_geht(self) -> None:
        """Wie die zstd-Packdateien: erst alle losen Dateien, dann die Baender in ihrer Reihenfolge."""
        gelesen: list[str] = []
        inh = dict(SPIEL)
        inh["ampr_zstd-000.pak"] = _zufall(300_000, 11)
        inh["ampr_zstd-001.pak"] = _zufall(200_000, 12)
        plan = w.planen(_liste(inh, gelesen), (), profil=PRIMAER[1])
        plan.schreiben(self.pfad("a.ffpkg"), reihenfolge=[r for r in inh if not r.startswith("ampr_")] + ["ampr_zstd-000.pak", "ampr_zstd-001.pak"])
        self.assertEqual(["ampr_zstd-000.pak", "ampr_zstd-001.pak"], gelesen[-2:])
        dateien, _o = self.gelesen(self.pfad("a.ffpkg"))
        self.assertEqual(inh, dateien)

    def test_melden_zaehlt_die_bytes(self) -> None:
        ereignisse: list[tuple] = []
        plan = w.planen(_liste(SPIEL), (), profil=PRIMAER[1])
        plan.schreiben(self.pfad("a.ffpkg"), melden=lambda *a: ereignisse.append(a))
        gesamt = sum(len(d) for d in SPIEL.values())
        self.assertEqual(gesamt, ereignisse[-1][3])
        self.assertEqual(gesamt, ereignisse[-1][2])

    def test_abbruch_mitten_in_einer_grossen_datei(self) -> None:
        gelesen: list[int] = []

        def langsam():
            for i in range(100):
                gelesen.append(i)
                yield b"x" * 1000

        plan = w.planen([("eboot.bin", 3, lambda: iter([b"abc"])), ("gross.bin", 100_000, langsam)], (), profil=PRIMAER[1])
        with self.assertRaises(InterruptedError):
            plan.schreiben(self.pfad("a.ffpkg"), abbruch=lambda: len(gelesen) >= 2)
        self.assertLess(len(gelesen), 10)

    def test_zu_kurz_und_zu_lang(self) -> None:
        for angabe, daten in ((10, b"abc"), (2, b"abc")):
            with self.subTest(angabe=angabe):
                plan = w.planen([("a.bin", angabe, lambda d=daten: iter([d]))], (), profil=PRIMAER[1])
                with self.assertRaises(w.Ufs2SchreibFehler):
                    plan.schreiben(self.pfad("k.ffpkg"))

    def test_oeffner_wird_auch_bei_einem_fehler_geschlossen(self) -> None:
        geschlossen: list[bool] = []

        def kaputt():
            try:
                yield b"abc"
                raise OSError("Platte weg")
            finally:
                geschlossen.append(True)

        plan = w.planen([("a.bin", 100, kaputt)], (), profil=PRIMAER[1])
        with self.assertRaises(OSError):
            plan.schreiben(self.pfad("a.ffpkg"))
        self.assertEqual([True], geschlossen)


class FehlerTests(unittest.TestCase):
    def test_abgelehnt(self) -> None:
        offen = lambda: iter([b"x"])                              # noqa: E731
        for eintraege, text in [
            ([("ü.bin", 1, offen)], "ASCII"),
            ([("a/../b.bin", 1, offen)], "Unbrauchbar"),
            ([("a//b.bin", 1, offen)], "Unbrauchbar"),
            ([("a\\b.bin", 1, offen)], "Unbrauchbar"),
            ([("x" * 256, 1, offen)], "Unbrauchbar"),
            ([("a.bin", 1, offen), ("a.bin", 1, offen)], "doppelt"),
            ([("a", 1, offen), ("a/b.bin", 1, offen)], "zugleich"),
            ([("a.bin", -1, offen)], "Negative"),
        ]:
            with self.assertRaises(w.Ufs2SchreibFehler, msg=str(eintraege)) as ctx:
                w.planen(eintraege, (), profil=PRIMAER[1])
            self.assertIn(text, str(ctx.exception))
            with self.assertRaises(w.Ufs2SchreibFehler):
                w.namen_pruefen(eintraege)

    def test_profil_wird_geprueft(self) -> None:
        for profil in (w.Ufs2Profil(block_size=3000), w.Ufs2Profil(block_size=65536, fragment_size=128),
                       w.Ufs2Profil(block_size=65536, fragment_size=4096), w.Ufs2Profil(min_free_percent=100),
                       w.Ufs2Profil(block_size=4096, fragment_size=512, sector_size=1024)):
            with self.subTest(profil=profil):
                with self.assertRaises(w.Ufs2SchreibFehler):
                    w.planen([("a", 1, lambda: iter([b"x"]))], (), profil=profil)

    def test_zu_grosse_datei_wird_vor_dem_schreiben_abgelehnt(self) -> None:
        """Dreifach indirekte Bloecke kennt UFS2Tool nicht (sein Erzeuger bricht dort ab); der Schreiber meldet es, statt zu beschaedigen."""
        profil = w.Ufs2Profil(4096, 4096, 512, 8, 4096)
        grenze = (12 + 512 + 512 * 512) * 4096
        w.planen([("d.bin", grenze, lambda: iter([]))], (), profil=profil)           # genau an der Grenze: geht (nur planen)
        with self.assertRaises(w.Ufs2SchreibFehler) as ctx:
            w.planen([("d.bin", grenze + 1, lambda: iter([]))], (), profil=profil)
        self.assertIn("dreifach", str(ctx.exception))

    def test_abbruch_beim_planen(self) -> None:
        with self.assertRaises(InterruptedError):
            w.planen(_liste(SPIEL), (), profil=PRIMAER[1], abbruch=lambda: True)

    def test_zu_viele_dateien_fuer_den_platz_wachsen_die_gruppen(self) -> None:
        """UFS2Tool legt bei zu wenigen Inodes mehr Gruppen an; der Schreiber ebenso (kein Fehler, nur ein groesseres Abbild)."""
        inh = {"d/%05d" % i: b"" for i in range(5000)}
        plan = w.planen(_liste(inh), (), profil=PRIMAER[1])
        self.assertGreaterEqual(plan.inodes_belegt, 5003)


class BruecheTests(unittest.TestCase):
    """``abbild_strom``: Planen mit Rueckfall aufs zweite Profil, Schreiben mit Abbruch."""

    def test_profilwahl_und_rueckfall(self) -> None:
        plan, kennung = ast.ufs2_planen(_liste(SPIEL), ["leer"])
        self.assertEqual("newfs-64k-reference", kennung)
        self.assertEqual(65536, plan.profil.block_size)
        echt = w.planen
        aufrufe: list[int] = []

        def erstes_scheitert(*a, **k):
            aufrufe.append(k["profil"].block_size)
            if len(aufrufe) == 1:
                raise w.Ufs2SchreibFehler("zu klein")
            return echt(*a, **k)
        with mock.patch.object(w, "planen", side_effect=erstes_scheitert):
            plan, kennung = ast.ufs2_planen(_liste(SPIEL))
        self.assertEqual([65536, 32768], aufrufe)
        self.assertEqual("newfs-32k-4k-compatibility", kennung)

    def test_scheitern_beide_kommt_der_fehler(self) -> None:
        with mock.patch.object(w, "planen", side_effect=w.Ufs2SchreibFehler("nein")):
            with self.assertRaises(w.Ufs2SchreibFehler):
                ast.ufs2_planen(_liste(SPIEL))

    def test_abbruch_wird_zu_stromabgebrochen(self) -> None:
        with self.assertRaises(ast.StromAbgebrochen):
            ast.ufs2_planen(_liste(SPIEL), abbruch=lambda: True)
        plan, _k = ast.ufs2_planen(_liste(SPIEL))
        tmp = tempfile.mkdtemp(prefix="ufs2br_")
        self.addCleanup(shutil.rmtree, tmp, True)
        with self.assertRaises(ast.StromAbgebrochen):
            ast.ufs2_schreiben(plan, os.path.join(tmp, "a.ffpkg"), abbruch=lambda: True)

    def test_profil_aus_newfs(self) -> None:
        p = w.profil_aus_newfs(ffs.primary_newfs_profile())
        self.assertEqual((65536, 65536, 0, 262144), (p.block_size, p.fragment_size, p.min_free_percent, p.bytes_per_inode))
        k = w.profil_aus_newfs(ffs.compatibility_newfs_profile())
        self.assertEqual((32768, 4096, 8, 0), (k.block_size, k.fragment_size, k.min_free_percent, k.bytes_per_inode))


class GemeinsameKonstantenTests(unittest.TestCase):
    """Schreiber und Leser haben einen Satz Formatkonstanten (Pruefbericht 14.11.2026: vorher standen sie dreimal da)."""

    def test_die_konstanten_sind_dieselben(self) -> None:
        from ps5_validator.utils import ufs2_dateisystem as d
        for name in ("SUPERBLOCK_OFFSET", "UFS2_MAGIC", "INODE_GROESSE", "WURZEL_INODE", "N_DIREKT"):
            self.assertEqual(getattr(d, name), getattr(w, name), name)
        self.assertEqual(d.S_IFDIR, w.IF_DIR)
        self.assertEqual(d.S_IFREG, w.IF_REG)

    def test_der_schreiber_definiert_sie_nicht_selbst(self) -> None:
        quelle = (Path(w.__file__)).read_text(encoding="utf-8")
        for zeile in ("SUPERBLOCK_OFFSET = ", "UFS2_MAGIC = ", "INODE_GROESSE = ", "WURZEL_INODE = ", "N_DIREKT = ",
                      "IF_DIR = ", "IF_REG = "):
            self.assertNotIn("\n" + zeile, quelle, zeile)


class WaechterTests(unittest.TestCase):
    def test_die_lizenz_des_vorbilds_ist_genannt(self) -> None:
        text = (ROOT / "ps5_validator" / "utils" / "ufs2_schreiber.py").read_text(encoding="utf-8")
        self.assertIn("BSD-2-Clause", text)
        self.assertIn("SvenGDK", text)
        lizenzen = (ROOT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("ufs2_schreiber", lizenzen)


if __name__ == "__main__":
    unittest.main()
