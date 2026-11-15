# -*- coding: utf-8 -*-
"""``abbild_journal``: Format 2 mit den Pruefsummen der neuen Bytes (Gesamtpruefung 14.11.2026, E3, U5, U6).

Ein Journal wird nur zurueckgespielt, wenn es zum Abbild gehoert: Jede Verwaltungsstelle muss Sektor fuer Sektor noch alt oder schon
neu sein. So bleibt ein halb geschriebener Lauf reparierbar (auch ein abgerissener Block besteht aus alten und neuen Sektoren), aber
ein anderes Abbild gleichen Namens wird nicht mehr mit fremden Bytes ueberschrieben oder gekuerzt.
"""
from __future__ import annotations

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

from ps5_validator.utils import abbild_journal as aj           # noqa: E402

ALT = bytes(range(256)) * 16                                   # 4096 Bytes
NEU = bytes(255 - (i % 256) for i in range(4096))


class _Abbild(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="journal_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bild = os.path.join(self.tmp, "spiel.exfat")
        Path(self.bild).write_bytes(b"\x11" * 1000 + ALT + b"\x22" * 3000)       # die Stelle beginnt NICHT an einer Sektorgrenze
        self.journal = aj.journal_pfad(self.bild)

    def schreiben_bis(self, n: int) -> None:
        """Schreibt die ersten ``n`` Bytes der neuen Stelle - wie ein Lauf, der mittendrin abbrach."""
        with open(self.bild, "r+b") as fh:
            fh.seek(1000)
            fh.write(NEU[:n])


class ZugehoerigkeitTests(_Abbild):
    def test_alles_noch_alt(self) -> None:
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        self.assertTrue(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])

    def test_alles_schon_neu(self) -> None:
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        self.schreiben_bis(len(NEU))
        self.assertTrue(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])

    def test_abgerissen_an_einer_sektorgrenze_der_datei(self) -> None:
        """Bis zur Sektorgrenze 1536 der Datei neu, dahinter alt: der unterbrochene Lauf - zurueckspielen."""
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        self.schreiben_bis(536)
        self.assertTrue(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])

    def test_ein_anderes_abbild_wird_nicht_angefasst(self) -> None:
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)], laenge_vorher=500)
        anderes = b"\x33" * 1000 + bytes(4096) + b"\x44" * 9000                 # neu gebaut, gleicher Name, laenger
        Path(self.bild).write_bytes(anderes)
        self.assertFalse(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(anderes, Path(self.bild).read_bytes(), "weder ueberschrieben noch gekuerzt")
        self.assertFalse(os.path.exists(self.journal))
        self.assertTrue(os.path.exists(self.journal + aj.FREMD_ENDUNG))

    def test_gegenprobe_ohne_neue_bytes_wie_bisher(self) -> None:
        """Stellen ohne neue Bytes (Dateidaten, Format-1-Aufrufer) werden nicht verglichen - zurueckgespielt wird wie bisher."""
        aj.journal_schreiben(self.journal, [(1000, ALT)])
        Path(self.bild).write_bytes(b"\x33" * 6000)
        self.assertTrue(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])

    def test_format_1_wird_weiter_gelesen(self) -> None:
        import struct
        import zlib
        roh = aj._MAGIC + struct.pack("<Q", 1) + struct.pack("<QII", 1000, len(ALT), zlib.crc32(ALT)) + ALT + aj._ENDE
        Path(self.journal).write_bytes(roh)
        self.schreiben_bis(4096)
        self.assertEqual([(1000, ALT)], aj.journal_lesen(self.journal))
        self.assertTrue(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])


class TeildateiTests(_Abbild):
    def test_vollstaendiges_neu_ohne_undo_wird_zurueckgespielt(self) -> None:
        """U5: Strom weg, bevor das Umbenennen auf der Platte stand - das vollstaendige ``.undo.neu`` gilt als Journal."""
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        os.replace(self.journal, self.journal + ".neu")
        self.schreiben_bis(4096)
        self.assertTrue(aj.journal_zurueckspielen(self.bild))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])
        self.assertFalse(os.path.exists(self.journal + ".neu"))

    def test_halbes_neu_wird_entfernt_und_nichts_geaendert(self) -> None:
        """U6: Ein unvollstaendiges ``.undo.neu`` (der Lauf brach vor dem ersten Schreiben ab) wird beim Oeffnen entfernt."""
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        roh = Path(self.journal).read_bytes()
        os.remove(self.journal)
        Path(self.journal + ".neu").write_bytes(roh[:-7])
        vorher = Path(self.bild).read_bytes()
        self.assertFalse(aj.journal_zurueckspielen(self.bild))
        self.assertFalse(os.path.exists(self.journal + ".neu"))
        self.assertEqual(vorher, Path(self.bild).read_bytes())

    def test_scheitert_das_schreiben_bleibt_kein_neu_liegen(self) -> None:
        """U6: Platte voll beim Schreiben des Journals - die Teildatei verschwindet, die Ausnahme kommt durch."""
        echt = os.fsync
        with mock.patch.object(os, "fsync", side_effect=OSError("Platte voll (gestellt)")):
            with self.assertRaises(OSError):
                aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        self.assertIs(echt, os.fsync)
        self.assertFalse(os.path.exists(self.journal + ".neu"))
        self.assertFalse(os.path.exists(self.journal))


class RueckrufTests(_Abbild):
    def test_neue_bytes_als_rueckruf(self) -> None:
        """R3-J2: Dateidaten liefern ihre neuen Bytes erst beim Schreiben des Journals - nicht alle zugleich im Speicher."""
        gerufen: list = []

        def neu() -> bytes:
            gerufen.append(1)
            return NEU
        aj.journal_schreiben(self.journal, [(1000, ALT, neu), (6000, b"\x22" * 10, lambda: None)])
        self.assertEqual([1], gerufen)
        self.schreiben_bis(4096)
        self.assertEqual(aj.ZURUECKGESPIELT, aj.zurueckspielen(self.bild)[0])
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])


class EigenUndFremdTests(_Abbild):
    def test_die_rueckabwicklung_im_selben_lauf_prueft_nicht(self) -> None:
        """R2-J1: Ein Editor, dessen ``speichern`` mitten im Schreiben scheitert, spielt sein eben geschriebenes Journal immer zurueck."""
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        Path(self.bild).write_bytes(b"\x33" * 6000)                            # weder alt noch neu
        self.assertEqual(aj.FREMD, aj.zurueckspielen(self.bild)[0], "Gegenprobe: ohne ``eigen`` wird es beiseitegelegt")
        aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
        self.assertTrue(aj.journal_zurueckspielen(self.bild, eigen=True))
        self.assertEqual(ALT, Path(self.bild).read_bytes()[1000:5096])

    def test_ein_beiseitegelegtes_journal_wird_nie_ueberschrieben(self) -> None:
        """R2-J3: ein zweites fremdes Journal bekommt einen eigenen Namen, und das Ergebnis sagt, wo es liegt."""
        anderes = b"\x33" * 6000
        Path(self.bild).write_bytes(anderes)
        orte = []
        for _ in range(2):
            aj.journal_schreiben(self.journal, [(1000, ALT, NEU)])
            ergebnis, ort = aj.zurueckspielen(self.bild)
            self.assertEqual(aj.FREMD, ergebnis)
            orte.append(ort)
        self.assertEqual([self.journal + ".fremd", self.journal + ".fremd2"], orte)
        self.assertTrue(all(os.path.exists(o) for o in orte))
        self.assertEqual(anderes, Path(self.bild).read_bytes())
        self.assertEqual((aj.NICHTS, ""), aj.zurueckspielen(self.bild))


class ZusammenfassenTests(unittest.TestCase):
    def test_gegen_eine_einfache_referenz(self) -> None:
        import random
        zufall = random.Random(7)
        for _ in range(200):
            stellen = []
            for _n in range(zufall.randint(1, 12)):
                o = zufall.randint(0, 300)
                stellen.append((o, bytes([zufall.randint(1, 255)]) * zufall.randint(1, 60)))
            bild: "dict[int, int]" = {}
            for o, d in stellen:
                for i, b in enumerate(d):
                    bild[o + i] = b
            zusammen = aj.stellen_zusammenfassen(stellen)
            gesehen: "dict[int, int]" = {}
            for o, d in zusammen:
                for i, b in enumerate(d):
                    gesehen[o + i] = b
            self.assertEqual(bild, gesehen)
            for (o1, d1), (o2, _d2) in zip(zusammen, zusammen[1:]):
                self.assertLess(o1 + len(d1), o2, "getrennt und nicht angrenzend")

    def test_viele_stellen_sind_schnell(self) -> None:
        """R2-J4: 6000 aneinanderliegende FAT-Bloecke brauchten 25 s (jede Stelle gegen alle Bereiche)."""
        import time
        stellen = [(i * 4096, b"\x01" * 4096) for i in range(20000)]
        beginn = time.perf_counter()
        zusammen = aj.stellen_zusammenfassen(stellen)
        self.assertLess(time.perf_counter() - beginn, 3.0)
        self.assertEqual(1, len(zusammen))
        self.assertEqual(20000 * 4096, len(zusammen[0][1]))

    def test_spaetere_stelle_gewinnt_und_nichts_ueberlappt(self) -> None:
        zusammen = aj.stellen_zusammenfassen([(100, b"a" * 100), (150, b"b" * 100), (400, b"c" * 10), (250, b"d" * 10),
                                              (1000, b"e" * 5)])
        self.assertEqual([(100, b"a" * 50 + b"b" * 100 + b"d" * 10), (400, b"c" * 10), (1000, b"e" * 5)], zusammen)

    def test_stuecke_an_den_sektorgrenzen_der_datei(self) -> None:
        self.assertEqual([(0, 24), (24, 536), (536, 600)], aj._stuecke(1000, 600))
        self.assertEqual([(0, 512), (512, 1024)], aj._stuecke(512, 1024))
        self.assertEqual([], aj._stuecke(7, 0))


class _Absturz(BaseException):
    pass


class _AbsturzBeimSchreiben:
    """Leitet alles an die Datei weiter; der ``n``-te ``write`` 'stuerzt ab' (nichts geschrieben)."""

    def __init__(self, fh, n: int) -> None:
        self.fh, self.n, self.zahl = fh, n, 0

    def write(self, b):
        self.zahl += 1
        if self.zahl >= self.n:
            raise _Absturz("Absturz beim %d. write" % self.zahl)
        return self.fh.write(b)

    def __getattr__(self, name):
        return getattr(self.fh, name)


class Ufs2FragmentOrdnerTests(unittest.TestCase):
    """R2-J1: Ein Ordner in einem Fragment (wie bei FreeBSD makefs) - das Journal sicherte einen ganzen Block, und die Nachbarfragmente,
    die derselbe Lauf beschrieb, waren dann "weder alt noch neu": Ein echter Abbruch galt als fremd und blieb halb geschrieben."""

    def test_ein_echter_abbruch_wird_zurueckgespielt(self) -> None:
        import struct as st
        from ps5_validator.utils import ufs2_bearbeiten as ub
        from ps5_validator.utils import ufs2_schreiber as w

        tmp = tempfile.mkdtemp(prefix="journal_ufs2frag_")
        self.addCleanup(shutil.rmtree, tmp, True)
        bild = os.path.join(tmp, "spiel.ffpkg")
        inhalte = {"eboot.bin": b"e", "data/a.bin": b"A" * 10}
        w.planen([(r, len(d), (lambda d=d: iter([d]))) for r, d in inhalte.items()], (),
                 profil=w.Ufs2Profil(4096, 512, 512, 8, 4096)).schreiben(bild)
        with ub.Ufs2Abbild(bild) as a:                                   # "data" in EIN Fragment, nicht am Blockanfang (B+3)
            v = a._verzeichnis("data")
            roh = a._inode(v.ino)
            inhalt512 = bytes(v.roh[:512])
            a._frags_setzen(v.bloecke[0], a.fpb, True)
            b = 848
            if any(a._frag_frei(b + i) is False for i in range(3, 8)):
                self.skipTest("Vorbedingung: Fragmente 851-855 frei")
            a._frags_setzen(b + 3, 1, False)
            st.pack_into("<Q", roh, 0x10, 512)
            st.pack_into("<q", roh, 0x18, 1)
            st.pack_into("<q", roh, 0x70, b + 3)
            a._zaehler_auffrischen()
            a._fh.seek((b + 3) * a.fs)
            a._fh.write(inhalt512)
            for off, neu in a._stellen():
                a._fh.seek(off)
                a._fh.write(neu)
            a._fh.flush()
        with ub.Ufs2Abbild(bild) as a:
            self.assertEqual([], a.pruefen(), "Vorbedingung: das umgebaute Abbild ist in Ordnung")
        quelle = os.path.join(tmp, "x.bin")
        Path(quelle).write_bytes(os.urandom(8192))
        a = ub.Ufs2Abbild(bild)
        a.umbenennen("data/a.bin", "b.bin")
        a.hinzufuegen("x.bin", quelle)
        a._fh = _AbsturzBeimSchreiben(a._fh, len(a._plan.daten[0][0]) + len(a._plan.bloecke) + 1)   # beim ersten Verwaltungs-write
        with mock.patch.object(ub, "journal_zurueckspielen", lambda p, **k: False):                  # harter Absturz
            with self.assertRaises(_Absturz):
                a.speichern()
        a._fh.fh.close()
        self.assertEqual(aj.ZURUECKGESPIELT, aj.zurueckspielen(bild)[0])
        self.assertFalse(os.path.exists(bild + ".undo.fremd"))
        with ub.Ufs2Abbild(bild) as a:
            self.assertEqual([], a.pruefen())
            self.assertEqual(["a.bin"], [n for n, _o, _g in a.auflisten("data")])


class ExfatNeubauGleicherLageTests(unittest.TestCase):
    """R2-J2: MkPFS baut exFAT deterministisch - ein Neubau gleicher Lage traegt an allen Verwaltungsstellen die alten Bytes. Erst die
    neuen Bytes der Datencluster verraten, dass das Journal nicht dazugehoert."""

    def test_der_inhalt_des_neubaus_bleibt(self) -> None:
        from mkpfs.exfat_writer import iter_exfat_image
        from ps5_validator.utils import exfat_bearbeiten as eb
        from ps5_validator.utils import spielbaum as sb

        tmp = tempfile.mkdtemp(prefix="journal_exfatneubau_")
        self.addCleanup(shutil.rmtree, tmp, True)
        bild = os.path.join(tmp, "spiel.exfat")

        def bauen(x: bytes) -> None:
            q = os.path.join(tmp, "quelle")
            shutil.rmtree(q, True)
            for rel, d in {"eboot.bin": b"\x7fELF" + bytes(3000), "data/x.bin": x, "data/y.bin": b"y" * 70000}.items():
                p = os.path.join(q, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                Path(p).write_bytes(d)
            with open(bild, "wb") as fh:
                for stueck in iter_exfat_image(Path(q)):
                    fh.write(stueck)

        v1, v2 = b"1" * 200_000, b"2" * 200_000
        bauen(v1)
        neu = os.path.join(tmp, "neu.bin")
        Path(neu).write_bytes(b"N" * 200_000)
        a = eb.ExfatAbbild(bild)
        a.ersetzen("data/x.bin", neu)
        a._fh = _AbsturzBeimSchreiben(a._fh, 1)
        with mock.patch.object(eb, "journal_zurueckspielen", lambda p, **k: False):
            with self.assertRaises(_Absturz):
                a.speichern()
        a._fh.fh.close()
        self.assertTrue(os.path.exists(aj.journal_pfad(bild)))
        os.remove(bild)
        bauen(v2)                                                        # neu gebaut, gleicher Name, gleiche Lage
        ergebnis, ort = aj.zurueckspielen(bild)
        self.assertEqual(aj.FREMD, ergebnis)
        self.assertTrue(os.path.exists(ort))
        with sb.ExfatBaum(bild) as baum:
            self.assertEqual(v2, b"".join(baum.suchen()["data/x.bin"].lesen()))

    def test_gegenprobe_der_echte_abbruch_wird_zurueckgespielt(self) -> None:
        from mkpfs.exfat_writer import iter_exfat_image
        from ps5_validator.utils import exfat_bearbeiten as eb
        from ps5_validator.utils import spielbaum as sb

        tmp = tempfile.mkdtemp(prefix="journal_exfatabbruch_")
        self.addCleanup(shutil.rmtree, tmp, True)
        q = os.path.join(tmp, "quelle")
        for rel, d in {"eboot.bin": b"\x7fELF" + bytes(3000), "data/x.bin": b"1" * 200_000, "data/y.bin": b"y" * 70000}.items():
            p = os.path.join(q, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Path(p).write_bytes(d)
        bild = os.path.join(tmp, "spiel.exfat")
        with open(bild, "wb") as fh:
            for stueck in iter_exfat_image(Path(q)):
                fh.write(stueck)
        vorher = Path(bild).read_bytes()
        neu = os.path.join(tmp, "neu.bin")
        Path(neu).write_bytes(b"N" * 200_000)
        for n in (2, 3, 5):                                              # mitten in den Datenclustern abgebrochen
            with self.subTest(abbruch_beim_write=n):
                a = eb.ExfatAbbild(bild)
                a.ersetzen("data/x.bin", neu)
                a._fh = _AbsturzBeimSchreiben(a._fh, n)
                with mock.patch.object(eb, "journal_zurueckspielen", lambda p, **k: False):
                    with self.assertRaises(_Absturz):
                        a.speichern()
                a._fh.fh.close()
                self.assertNotEqual(vorher, Path(bild).read_bytes(), "Vorbedingung: es wurde schon geschrieben")
                self.assertEqual(aj.ZURUECKGESPIELT, aj.zurueckspielen(bild)[0])
                self.assertEqual(vorher, Path(bild).read_bytes())
                with sb.ExfatBaum(bild) as baum:
                    self.assertEqual(b"1" * 200_000, b"".join(baum.suchen()["data/x.bin"].lesen()))


class ExfatDateiendeTests(unittest.TestCase):
    """R3-J1: Der letzte Cluster einer Datei wurde in zwei Aufrufen geschrieben (Stueck, dann Nullen) - ein Abbruch dazwischen liess
    einen Sektor halb alt, halb neu, und das Journal hielt sich fuer fremd. Jetzt: an jeder Stelle abgebrochen, immer zurueckgespielt."""

    def test_abbruch_an_jedem_write(self) -> None:
        from mkpfs.exfat_writer import iter_exfat_image
        from ps5_validator.utils import exfat_bearbeiten as eb

        tmp = tempfile.mkdtemp(prefix="journal_exfatende_")
        self.addCleanup(shutil.rmtree, tmp, True)
        q = os.path.join(tmp, "quelle")
        cl = 65536
        for rel, d in {"eboot.bin": b"\x7fELF" + bytes(3000), "data/alt.bin": b"A" * (3 * cl), "data/y.bin": b"y" * 70000}.items():
            p = os.path.join(q, *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            Path(p).write_bytes(d)
        bild = os.path.join(tmp, "spiel.exfat")
        with open(bild, "wb") as fh:
            for stueck in iter_exfat_image(Path(q)):
                fh.write(stueck)
        vorher = Path(bild).read_bytes()
        neu = os.path.join(tmp, "neu.bin")
        Path(neu).write_bytes(b"N" * (2 * cl + 5))                          # das letzte Stueck: 5 Bytes und 65531 Nullen
        n = 1
        while True:
            a = eb.ExfatAbbild(bild)
            a.ersetzen("data/alt.bin", neu)
            a._fh = _AbsturzBeimSchreiben(a._fh, n)
            with mock.patch.object(eb, "journal_zurueckspielen", lambda p, **k: False):
                try:
                    a.speichern()
                    fertig = True
                except _Absturz:
                    fertig = False
            a._fh.fh.close()
            if fertig:
                break
            with self.subTest(abbruch_beim_write=n):
                self.assertEqual(aj.ZURUECKGESPIELT, aj.zurueckspielen(bild)[0])
                self.assertEqual(vorher, Path(bild).read_bytes())
            n += 1
        self.assertGreater(n, 3, "Vorbedingung: mehrere Schreibaufrufe")


class PfsNeuGebautTests(unittest.TestCase):
    """Der Befund am echten Weg: Ein Lauf brach ab, das Spiel wurde danach neu umgewandelt (gleicher Name) - "Direkt aendern" darf das
    neue Abbild nicht mit dem alten Journal zurueckspielen (Format 1 kuerzte es auf die alte Laenge)."""

    def test_neu_gebautes_ffpfs_bleibt_heil(self) -> None:
        from ps5_validator.utils import abbild_direkt
        from ps5_validator.utils import abbild_strom
        from ps5_validator.utils import pfs_bearbeiten as pb

        tmp = tempfile.mkdtemp(prefix="journal_pfs_")
        self.addCleanup(shutil.rmtree, tmp, True)
        ziel = os.path.join(tmp, "spiel.ffpfs")

        def bauen(inhalte: "dict[str, bytes]") -> None:
            if os.path.exists(ziel):
                os.remove(ziel)
            abbild_strom.ffpfs_schreiben([(r, len(d), (lambda d=d: iter([d]))) for r, d in inhalte.items()], ziel, block_size=65536)

        bauen({"eboot.bin": b"e" * 3000, "sce_sys/param.json": b"{}", "a.bin": b"a" * 100000})
        gross = os.path.join(tmp, "gross.bin")
        Path(gross).write_bytes(b"g" * 3_000_000)
        a = pb.PfsAbbild(ziel)
        a.hinzufuegen("gross.bin", gross)
        with mock.patch.object(pb, "journal_zurueckspielen", return_value=False), \
                mock.patch.object(pb.PfsAbbild, "_daten_schreiben", side_effect=KeyboardInterrupt("Strom weg")):
            with self.assertRaises(KeyboardInterrupt):
                a.speichern()
        a.schliessen()
        self.assertTrue(os.path.exists(aj.journal_pfad(ziel)), "Vorbedingung: das Journal blieb liegen")
        bauen({"eboot.bin": b"E" * 5000, "sce_sys/param.json": b"{}", "b.bin": b"b" * 900000, "c.bin": b"c" * 700000})
        neu = Path(ziel).read_bytes()
        abbild_direkt.oeffnen(ziel).schliessen()
        self.assertEqual(neu, Path(ziel).read_bytes(), "das neue Abbild ist unveraendert")
        self.assertTrue(os.path.exists(aj.journal_pfad(ziel) + aj.FREMD_ENDUNG))


if __name__ == "__main__":
    unittest.main(verbosity=2)
