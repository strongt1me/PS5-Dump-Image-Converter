# -*- coding: utf-8 -*-
"""Eigener UFS2-Leser und ``Ufs2Baum`` (Stufe 3, Etappe 10): ``.ffpkg`` lesen ohne UFS2Tool, Dokan und Administratorrechte.

Drei Beweise:

* **echte Abbilder:** Mit dem mitgelieferten UFS2Tool (``newfs -O 2 -D``, wie das Programm es aufruft) werden zwei Abbilder gebaut -
  das Programmprofil (64 KiB Bloecke) und ein kleines mit Fragmenten, zwei Zylindergruppen und doppelt indirekten Bloecken. Der
  Leser muss Liste, Verzeichnisse (auch leere) und jeden Byte gleich dem Quellordner und gleich ``UFS2Tool extract`` liefern.
* **handgebaute Abbilder:** Loecher (Zeiger 0), dreifach indirekte Bloecke, freie Plaetze im Verzeichnis, Verweise.
* **Fehler:** kein UFS2, abgeschnitten, Zeiger hinter dem Ende, Zyklus - alles ein ``Ufs2Fehler``, nie stille Auslassung.

Die Tests mit dem Werkzeug laufen nur, wo es sich ohne Erhoehung starten laesst (Windows: ``__COMPAT_LAYER=RunAsInvoker``).
"""
from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ufs2_dateisystem")

from ps5_validator.utils import ffpkg_support as ffs         # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402
from ps5_validator.utils import ufs2_dateisystem as ul            # noqa: E402


def _zufall(n: int, startwert: int = 1) -> bytes:
    import hashlib
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


SPIEL = {
    "eboot.bin": b"\x7fELF" + _zufall(5000, 1),
    "sce_sys/param.json": b'{"titleId":"PPSA00000"}',
    "sce_sys/icon0.png": _zufall(9000, 2),
    "data/gross.bin": _zufall(3_000_000, 3),                 # ueber 12 Bloecke zu 4 KiB: indirekt, doppelt indirekt
    "data/mittel.bin": _zufall(100_001, 4),                  # kein Vielfaches der Blockgroesse
    "data/b/klein.txt": b"klein\n",
    "data/b/leer.txt": b"",
    "Daten/Zebra.dat": _zufall(40_000, 5),
}
LEERE_ORDNER = ("savedata_leer", "data/cache/tief")


def _werkzeug() -> "str | None":
    if sys.platform != "win32":
        return None                                        # die anderen Plattformen brauchen Ausfuehrrechte und eigene Laufzeit
    pfad = ROOT / "UFS2Tool-4.1" / "win-x64" / "UFS2Tool.exe"
    return str(pfad) if pfad.is_file() else None


def _ausfuehren(befehl: list[str]) -> "subprocess.CompletedProcess[str]":
    umgebung = dict(os.environ, __COMPAT_LAYER="RunAsInvoker")           # kein UAC: ein Abbild in einer Datei braucht keine Rechte
    return subprocess.run(befehl, capture_output=True, text=True, timeout=300, env=umgebung)


def _schreiben(wurzel: str, inhalte: dict[str, bytes]) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)


@unittest.skipUnless(_werkzeug(), "UFS2Tool laesst sich hier nicht ohne Erhoehung starten")
class EchteAbbilderTests(unittest.TestCase):
    PROFILE = {
        "programm": None,                                                                    # primary_newfs_profile()
        "klein": ffs.FfpkgNewfsProfile("test-klein", block_size=4096, fragment_size=512, sector_size=512, inode_density=4096),
    }

    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.mkdtemp(prefix="ufs2leser_")
        cls.quelle = os.path.join(cls.tmp, "quelle")
        _schreiben(cls.quelle, SPIEL)
        for rel in LEERE_ORDNER:
            os.makedirs(os.path.join(cls.quelle, *rel.split("/")), exist_ok=True)
        cls.abbilder: dict[str, str] = {}
        for name, profil in cls.PROFILE.items():
            ziel = os.path.join(cls.tmp, name + ".ffpkg")
            lauf = _ausfuehren(ffs.build_newfs_directory_command(_werkzeug(), cls.quelle, ziel, profile=profil))
            if lauf.returncode != 0 or not os.path.isfile(ziel):
                raise unittest.SkipTest("UFS2Tool newfs scheiterte: %s" % (lauf.stdout or lauf.stderr)[-300:])
            cls.abbilder[name] = ziel

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_liste_ordner_und_inhalt(self) -> None:
        for name, pfad in self.abbilder.items():
            with self.subTest(abbild=name), open(pfad, "rb") as fh:
                leser = ul.Ufs2Leser(fh)
                baum = leser.baum()
                self.assertEqual({k: len(v) for k, v in SPIEL.items()}, {e.rel: e.groesse for e in baum.dateien})
                self.assertEqual([], baum.uebersprungen)
                erwartet_ordner = {"data", "data/b", "data/cache", "data/cache/tief", "Daten", "sce_sys", "savedata_leer"}
                self.assertEqual(sorted(erwartet_ordner), baum.ordner)
                for e in baum.dateien:
                    self.assertEqual(SPIEL[e.rel], b"".join(leser.lesen(leser.inode(e.inode), 70_001)), e.rel)

    def test_bloecke_und_fragmente(self) -> None:
        with open(self.abbilder["klein"], "rb") as fh:
            leser = ul.Ufs2Leser(fh)
        self.assertEqual((4096, 512, 8), (leser.bsize, leser.fsize, leser.frag))
        self.assertGreater(leser.ncg, 1, "mehrere Zylindergruppen")
        with open(self.abbilder["programm"], "rb") as fh:
            leser = ul.Ufs2Leser(fh)
        self.assertEqual((65536, 65536, 1), (leser.bsize, leser.fsize, leser.frag))

    def test_gleich_ufs2tool_extract(self) -> None:
        """Der Massstab: was das Werkzeug selbst herausschreibt, liest der eigene Leser ebenso."""
        for name, pfad in self.abbilder.items():
            with self.subTest(abbild=name):
                ziel = os.path.join(self.tmp, "extract_" + name)
                lauf = _ausfuehren([_werkzeug(), "extract", pfad, ziel])
                self.assertEqual(0, lauf.returncode, lauf.stdout)
                with open(pfad, "rb") as fh:
                    leser = ul.Ufs2Leser(fh)
                    for e in leser.baum().dateien:
                        voll = os.path.join(ziel, *e.rel.split("/"))
                        self.assertEqual(Path(voll).read_bytes(), b"".join(leser.lesen(leser.inode(e.inode))), e.rel)

    def test_der_baum_liest_in_mehreren_faeden(self) -> None:
        with sb.Ufs2Baum(self.abbilder["klein"]) as baum:
            dateien = baum.dateien()
            fehler: list[str] = []

            def lesen(teil: list) -> None:
                try:
                    for d in teil:
                        if b"".join(d.lesen(50_000)) != SPIEL[d.rel]:
                            fehler.append(d.rel)
                except Exception as exc:  # noqa: BLE001
                    fehler.append(repr(exc))
            faeden = [threading.Thread(target=lesen, args=(dateien[i::3],)) for i in range(3)] + [threading.Thread(target=lesen, args=(dateien,))]
            for f in faeden:
                f.start()
            for f in faeden:
                f.join()
            self.assertEqual([], fehler)
            self.assertEqual(sorted(SPIEL), [d.rel for d in dateien])

    def test_baum_wie_ordnerbaum(self) -> None:
        with sb.Ufs2Baum(self.abbilder["programm"]) as ufs, sb.OrdnerBaum(self.quelle) as ordner:
            self.assertEqual([(d.rel, d.groesse) for d in ordner.dateien()], [(d.rel, d.groesse) for d in ufs.dateien()])
            self.assertEqual(ordner.ordner(), ufs.ordner())

    def test_stuecke_sind_hoechstens_so_gross_wie_verlangt(self) -> None:
        with sb.Ufs2Baum(self.abbilder["klein"]) as baum:
            gross = baum.suchen()["data/gross.bin"]
            for stueck in (1000, 65536, 1 << 20):
                teile = list(gross.lesen(stueck))
                # Ein Stueck ist mindestens ein Block; groesser als verlangt (aber nie kleiner als ein Block) darf es nicht werden
                self.assertLessEqual(max(len(t) for t in teile), max(stueck, 4096))
                self.assertEqual(SPIEL["data/gross.bin"], b"".join(teile))

    def test_stempel(self) -> None:
        kopie = os.path.join(self.tmp, "stempel.ffpkg")
        shutil.copyfile(self.abbilder["programm"], kopie)
        self.addCleanup(lambda: os.path.exists(kopie) and os.remove(kopie))
        with sb.Ufs2Baum(kopie) as baum:
            baum.dateien()
            self.assertTrue(baum.unveraendert())
            with open(kopie, "ab") as fh:
                fh.write(b"\0")
            self.assertFalse(baum.unveraendert())


# ------------------------------------------------------------------------------------------------------------------------------
# Handgebaute Abbilder
# ------------------------------------------------------------------------------------------------------------------------------
BSIZE = 4096
NINDIR = BSIZE // 8
IBLKNO = 32                       # Fragmente (= Bloecke bei frag=1): Inode-Tabelle hinter Superblock und Kopf


class Abbildbauer:
    """Baut ein winziges UFS2 (bsize = fsize = 4096, eine Zylindergruppe) mit frei waehlbaren Inodes und Bloecken."""

    def __init__(self, bloecke: int = 4096) -> None:
        self.bloecke = bloecke
        self.daten = bytearray(bloecke * BSIZE)
        self.frei = 64                                          # naechster freier Block (Fragment-Adresse)
        sb_ = bytearray(1376)
        struct.pack_into("<i", sb_, 16, IBLKNO)
        struct.pack_into("<I", sb_, 44, 1)
        struct.pack_into("<i", sb_, 48, BSIZE)
        struct.pack_into("<i", sb_, 52, BSIZE)
        struct.pack_into("<i", sb_, 56, 1)
        struct.pack_into("<I", sb_, 184, 64)                    # Inodes je Gruppe
        struct.pack_into("<i", sb_, 188, bloecke)               # Fragmente je Gruppe
        struct.pack_into("<I", sb_, 1372, ul.UFS2_MAGIC)
        self.daten[ul.SUPERBLOCK_OFFSET:ul.SUPERBLOCK_OFFSET + 1376] = sb_

    def block(self, inhalt: bytes = b"") -> int:
        adresse = self.frei
        self.frei += 1
        self.daten[adresse * BSIZE:adresse * BSIZE + len(inhalt)] = inhalt
        return adresse

    def inode(self, nummer: int, modus: int, groesse: int, direkt=(), indirekt=()) -> None:
        offset = IBLKNO * BSIZE + nummer * ul.INODE_GROESSE
        blob = bytearray(ul.INODE_GROESSE)
        struct.pack_into("<H", blob, 0, modus)
        struct.pack_into("<Q", blob, 16, groesse)
        db = list(direkt) + [0] * (12 - len(direkt))
        struct.pack_into("<12q", blob, 112, *db)
        ib = list(indirekt) + [0] * (3 - len(indirekt))
        struct.pack_into("<3q", blob, 208, *ib)
        self.daten[offset:offset + ul.INODE_GROESSE] = blob

    @staticmethod
    def eintrag(ino: int, typ: int, name: str, reclen: int = 0) -> bytes:
        roh = name.encode()
        laenge = 8 + len(roh) + (-(8 + len(roh)) % 4)
        reclen = reclen or laenge
        return struct.pack("<IHBB", ino, reclen, typ, len(roh)) + roh + bytes(reclen - 8 - len(roh))

    def verzeichnis(self, nummer: int, eintraege: "list[bytes]") -> None:
        inhalt = bytearray(b"".join(eintraege))
        rest = -len(inhalt) % 512
        if rest and eintraege:                                  # der letzte Eintrag fuellt den Rest des 512-Byte-Blocks (wie in echten Abbildern)
            beginn = len(inhalt) - len(eintraege[-1])
            struct.pack_into("<H", inhalt, beginn + 4, len(eintraege[-1]) + rest)
            inhalt += bytes(rest)
        inhalt = bytes(inhalt)
        adresse = self.block(inhalt)
        self.inode(nummer, ul.S_IFDIR | 0o755, len(inhalt), direkt=[adresse])

    def bytes(self) -> bytes:
        return bytes(self.daten)


def _leser(bauer: Abbildbauer) -> ul.Ufs2Leser:
    import io
    return ul.Ufs2Leser(io.BytesIO(bauer.bytes()))


class HandgebauteAbbilderTests(unittest.TestCase):
    def _mit_datei(self, bauer: Abbildbauer, nummer: int, groesse: int, **zeiger) -> None:
        bauer.inode(nummer, ul.S_IFREG | 0o644, groesse, **zeiger)

    def _wurzel(self, bauer: Abbildbauer, *dateien: "tuple[int, str]") -> None:
        e = Abbildbauer.eintrag
        bauer.verzeichnis(2, [e(2, 4, "."), e(2, 4, ".."), *[e(n, 8, name) for n, name in dateien]])

    def test_ein_loch_ist_nullen(self) -> None:
        b = Abbildbauer()
        a0, a2 = b.block(b"A" * BSIZE), b.block(b"C" * 100)
        self._mit_datei(b, 3, 2 * BSIZE + 100, direkt=[a0, 0, a2])                 # Block 1 ist ein Loch
        self._wurzel(b, (3, "loch.bin"))
        leser = _leser(b)
        daten = b"".join(leser.lesen(leser.inode(3)))
        self.assertEqual(b"A" * BSIZE + bytes(BSIZE) + b"C" * 100, daten)

    def test_dreifach_indirekt_mit_loechern(self) -> None:
        """Das Ende einer Datei, die so gross ist, dass nur ein dreifach indirekter Zeiger sie erreicht (der Rest sind Loecher)."""
        b = Abbildbauer()
        blocks = 12 + NINDIR + NINDIR ** 2 + 1                                       # der letzte Block liegt unter dem Dreifach-Zeiger
        daten_block = b.block(b"Z" * 500)
        einfach = b.block(struct.pack("<%dq" % NINDIR, daten_block, *([0] * (NINDIR - 1))))
        doppelt = b.block(struct.pack("<%dq" % NINDIR, einfach, *([0] * (NINDIR - 1))))
        dreifach = b.block(struct.pack("<%dq" % NINDIR, doppelt, *([0] * (NINDIR - 1))))
        groesse = (blocks - 1) * BSIZE + 500
        self._mit_datei(b, 3, groesse, indirekt=[0, 0, dreifach])
        self._wurzel(b, (3, "gross.bin"))
        leser = _leser(b)
        gelesen = 0
        letzter = b""
        for stueck in leser.lesen(leser.inode(3), 1 << 20):
            gelesen += len(stueck)
            letzter = stueck
        self.assertEqual(groesse, gelesen)
        self.assertEqual(b"Z" * 500, letzter[-500:])

    def test_einfach_und_doppelt_indirekt(self) -> None:
        b = Abbildbauer()
        direkt = [b.block(bytes([i]) * BSIZE) for i in range(12)]
        blockdaten = [b.block(bytes([100 + i]) * BSIZE) for i in range(3)]
        einfach = b.block(struct.pack("<%dq" % NINDIR, *blockdaten, *([0] * (NINDIR - 3))))
        unter = b.block(struct.pack("<%dq" % NINDIR, b.block(b"D" * 10), *([0] * (NINDIR - 1))))
        doppelt = b.block(struct.pack("<%dq" % NINDIR, unter, *([0] * (NINDIR - 1))))
        groesse = (12 + NINDIR) * BSIZE + 10
        self._mit_datei(b, 3, groesse, direkt=direkt, indirekt=[einfach, doppelt])
        self._wurzel(b, (3, "x.bin"))
        leser = _leser(b)
        daten = b"".join(leser.lesen(leser.inode(3)))
        self.assertEqual(groesse, len(daten))
        self.assertEqual(b"".join(bytes([i]) * BSIZE for i in range(12)), daten[:12 * BSIZE])
        self.assertEqual(b"".join(bytes([100 + i]) * BSIZE for i in range(3)), daten[12 * BSIZE:15 * BSIZE])
        self.assertEqual(bytes(BSIZE * (NINDIR - 3)), daten[15 * BSIZE:(12 + NINDIR) * BSIZE])      # Loecher bis zum Ende des Einfach-Blocks
        self.assertEqual(b"D" * 10, daten[-10:])

    def test_zusammenhaengende_bloecke_werden_in_einem_lesen_geholt(self) -> None:
        b = Abbildbauer()
        adressen = [b.block(bytes([i]) * BSIZE) for i in range(8)]                    # fortlaufend
        self._mit_datei(b, 3, 8 * BSIZE, direkt=adressen)
        self._wurzel(b, (3, "x.bin"))
        leser = _leser(b)
        stuecke = list(leser.lesen(leser.inode(3), 1 << 20))
        self.assertEqual(1, len(stuecke))
        self.assertEqual(b"".join(bytes([i]) * BSIZE for i in range(8)), stuecke[0])
        klein = list(leser.lesen(leser.inode(3), BSIZE))
        self.assertEqual(8, len(klein))

    def test_verzeichnis_mit_freien_plaetzen_und_langem_namen(self) -> None:
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        a = b.block(b"x")
        self._mit_datei(b, 3, 1, direkt=[a])
        lang = "n" * 255
        b.verzeichnis(2, [e(2, 4, "."), e(2, 4, ".."), e(0, 0, "geloescht", 20), e(3, 8, lang), e(3, 8, "zweiter_name")])
        baum = _leser(b).baum()
        self.assertEqual(sorted([lang, "zweiter_name"]), sorted(d.rel for d in baum.dateien), "ein Hartlink zaehlt als zwei Dateien")

    def test_verweise_und_geraete_werden_gemeldet(self) -> None:
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        b.inode(3, 0o120777, 5)                                                       # Symlink
        b.inode(4, 0o020666, 0)                                                       # Zeichengeraet
        self._wurzel(b, (3, "verweis"), (4, "geraet"))
        baum = _leser(b).baum()
        self.assertEqual([], baum.dateien)
        self.assertEqual(["geraet", "verweis"], baum.uebersprungen)

    def test_unterordner_und_leere_ordner(self) -> None:
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        a = b.block(b"hallo")
        self._mit_datei(b, 4, 5, direkt=[a])
        b.verzeichnis(3, [e(3, 4, "."), e(2, 4, ".."), e(4, 8, "datei.txt")])
        b.verzeichnis(5, [e(5, 4, "."), e(2, 4, "..")])
        b.verzeichnis(2, [e(2, 4, "."), e(2, 4, ".."), e(3, 4, "ordner"), e(5, 4, "leer")])
        baum = _leser(b).baum()
        self.assertEqual(["ordner/datei.txt"], [d.rel for d in baum.dateien])
        self.assertEqual(["leer", "ordner"], baum.ordner)

    def test_stueck_ist_eine_obergrenze_auch_unter_der_blockgroesse(self) -> None:
        """``lesen(inode, stueck)`` liefert nie mehr als ``stueck`` Bytes - auch bei einem ``stueck`` unter einem Block (Pruefbericht 14.11.2026)."""
        b = Abbildbauer()
        adressen = [b.block(bytes([i + 1]) * BSIZE) for i in range(3)]
        self._mit_datei(b, 3, 3 * BSIZE - 7, direkt=adressen)
        self._wurzel(b, (3, "x.bin"))
        leser = _leser(b)
        erwartet = b"".join(bytes([i + 1]) * BSIZE for i in range(3))[:3 * BSIZE - 7]
        for stueck in (1, 7, 1000, BSIZE - 1, BSIZE, BSIZE + 1, 2 * BSIZE, 1 << 20):
            with self.subTest(stueck=stueck):
                teile = list(leser.lesen(leser.inode(3), stueck))
                self.assertTrue(all(0 < len(t) <= stueck for t in teile), [len(t) for t in teile][:5])
                self.assertEqual(erwartet, b"".join(teile))

    def test_verzeichnis_mit_unglaubwuerdiger_groesse_wird_abgelehnt(self) -> None:
        """Ein beschaedigtes Abbild nennt eine riesige Verzeichnisgroesse (Zeiger 0 = Loch = Nullen): kein Speicherfressen, sondern Ufs2Fehler."""
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        b.verzeichnis(2, [e(2, 4, "."), e(2, 4, "..")])
        b.inode(2, ul.S_IFDIR | 0o755, ul.VERZEICHNIS_MAX + 1, direkt=[b.block(b"")])
        leser = _leser(b)
        gelesen = []
        echt = leser.lesen
        leser.lesen = lambda *a, **k: gelesen.append(1) or echt(*a, **k)
        with self.assertRaisesRegex(ul.Ufs2Fehler, "unglaubw"):
            leser.verzeichnis(leser.inode(2))
        self.assertEqual([], gelesen, "Gelesen werden darf nichts: sonst stuende die ganze Groesse als Nullen im Speicher")

    # -- Fehler ---------------------------------------------------------------------------------------------------------------
    def test_kein_ufs2(self) -> None:
        import io
        for daten in (bytes(200_000), b"EXFAT   " * 30_000, b"", bytes(1000)):
            with self.subTest(laenge=len(daten)), self.assertRaises(ul.Ufs2Fehler):
                ul.Ufs2Leser(io.BytesIO(daten))

    def test_unplausibler_superblock(self) -> None:
        import io
        b = Abbildbauer()
        struct.pack_into("<i", b.daten, ul.SUPERBLOCK_OFFSET + 48, 1000)               # Blockgroesse keine Zweierpotenz
        with self.assertRaises(ul.Ufs2Fehler):
            ul.Ufs2Leser(io.BytesIO(b.bytes()))

    def test_ein_zeiger_hinter_dem_ende(self) -> None:
        b = Abbildbauer(bloecke=128)
        self._mit_datei(b, 3, BSIZE, direkt=[999_999])
        self._wurzel(b, (3, "x.bin"))
        leser = _leser(b)
        with self.assertRaises(ul.Ufs2Fehler):
            b"".join(leser.lesen(leser.inode(3)))

    def test_eine_abgeschnittene_datei(self) -> None:
        import io
        b = Abbildbauer()
        a = b.block(b"x" * BSIZE)
        self._mit_datei(b, 3, BSIZE, direkt=[a])
        self._wurzel(b, (3, "x.bin"))
        daten = b.bytes()[:a * BSIZE + 100]                                           # mitten im Datenblock abgeschnitten
        leser = ul.Ufs2Leser(io.BytesIO(daten))
        with self.assertRaises(ul.Ufs2Fehler):
            b"".join(leser.lesen(leser.inode(3)))

    def test_zu_viele_bytes_fuer_die_zeiger(self) -> None:
        b = Abbildbauer()
        a = b.block(b"x" * BSIZE)
        self._mit_datei(b, 3, 40 * BSIZE, direkt=[a])                                  # 40 Bloecke verlangt, nur 12 + Indirekt-Zeiger 0
        self._wurzel(b, (3, "x.bin"))
        leser = _leser(b)
        daten = b"".join(leser.lesen(leser.inode(3)))                                  # Zeiger 0 = Loecher: Nullen, kein Fehler
        self.assertEqual(40 * BSIZE, len(daten))

    def test_ein_zyklus_im_verzeichnisbaum(self) -> None:
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        b.verzeichnis(3, [e(3, 4, "."), e(2, 4, ".."), e(2, 4, "zurueck")])           # zeigt auf die Wurzel
        b.verzeichnis(2, [e(2, 4, "."), e(2, 4, ".."), e(3, 4, "unten")])
        with self.assertRaises(ul.Ufs2Fehler):
            _leser(b).baum()

    def test_ein_kaputter_verzeichniseintrag(self) -> None:
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        b.verzeichnis(2, [e(2, 4, "."), struct.pack("<IHBB", 3, 6, 8, 1) + b"x\0", e(3, 8, "dahinter")])   # reclen 6: kleiner als der Kopf
        with self.assertRaises(ul.Ufs2Fehler):
            _leser(b).baum()

    def test_inode_ausserhalb(self) -> None:
        b = Abbildbauer()
        self._wurzel(b)
        with self.assertRaises(ul.Ufs2Fehler):
            _leser(b).inode(10_000)

    def test_abbruch(self) -> None:
        b = Abbildbauer()
        self._wurzel(b)
        with self.assertRaises(ul.Ufs2Fehler):
            _leser(b).baum(abbruch=lambda: True)

    def test_baum_meldet_ein_nicht_lesbares_abbild_als_baumfehler(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "x.ffpkg")
            Path(pfad).write_bytes(bytes(300_000))
            with self.assertRaises(sb.BaumFehler):
                sb.Ufs2Baum(pfad).dateien()
            with self.assertRaises(sb.BaumFehler):
                sb.Ufs2Baum(os.path.join(tmp, "gibts_nicht.ffpkg"))

    def test_baum_aus_handgebautem_abbild_mit_ignorierten_namen(self) -> None:
        b = Abbildbauer()
        e = Abbildbauer.eintrag
        a = b.block(b"x")
        self._mit_datei(b, 3, 1, direkt=[a])
        self._mit_datei(b, 4, 1, direkt=[a])
        b.verzeichnis(2, [e(2, 4, "."), e(2, 4, ".."), e(3, 8, "spiel.bin"), e(4, 8, ".DS_Store")])
        with tempfile.TemporaryDirectory() as tmp:
            pfad = os.path.join(tmp, "x.ffpkg")
            Path(pfad).write_bytes(b.bytes())
            with sb.Ufs2Baum(pfad, ignoriert=lambda t: t == ".DS_Store") as baum:
                self.assertEqual(["spiel.bin"], [d.rel for d in baum.dateien()])
                self.assertEqual(b"x", b"".join(baum.suchen()["spiel.bin"].lesen()))


if __name__ == "__main__":
    unittest.main()
