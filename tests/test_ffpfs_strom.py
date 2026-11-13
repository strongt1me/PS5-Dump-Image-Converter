# -*- coding: utf-8 -*-
"""``.ffpfs`` (flaches, unkomprimiertes PFS) im Strom (Stufe 3, Etappe 11): MkPFS ``build_pfs`` aus einer Dateiliste und ``abbild_strom``.

Massstab ist der bisherige Weg: derselbe Inhalt als Ordner durch ``build_pfs(source_root=...)`` (das ist, was
``mkpfs pack folder --raw --no-compress`` baut) ergibt **byteweise dieselbe Datei** wie die Liste mit Oeffnern - auch wenn die
Oeffner in anderer Reihenfolge gerufen werden und wenn die Packdateien aus dem zstd-Strom kommen.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ffpfs_strom")

from mkpfs import consts                                     # noqa: E402
from mkpfs import exfat_writer as w                          # noqa: E402
from mkpfs.pbar import Progress                              # noqa: E402
from mkpfs.pfs import BuildError, build_pfs                  # noqa: E402

from ps5_validator.utils import abbild_pruefen as ap         # noqa: E402
from ps5_validator.utils import abbild_strom as ast          # noqa: E402
from ps5_validator.utils import ampr_zstdpack as z           # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402

JETZT = 1_700_000_000.0


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
    "Media/zufall.bin": _zufall(300_000, 3),
    "data/genau.bin": b"A" * z.CHUNK_SIZE,
    "data/plus_eins.bin": b"B" * (z.CHUNK_SIZE + 1),
    "data/klein.cfg": b"a=1\n",
    "data/b/leer.txt": b"",
    "data/gross.bin": _zufall(1_500_000, 7),
    "readme.ini": b"[x]\n",
}


def _schreiben(wurzel: str, inhalte: dict[str, bytes]) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)


def _liste(inhalte: dict[str, bytes], zaehler: "dict[str, int] | None" = None) -> list:
    def oeffner(rel: str, d: bytes):
        def lesen():
            if zaehler is not None:
                zaehler[rel] = zaehler.get(rel, 0) + 1
            return iter([d[i:i + 70_000] for i in range(0, len(d), 70_000)])
        return lesen
    return [(rel, len(d), oeffner(rel, d)) for rel, d in inhalte.items()]


def _aus_ordner(ordner: str, ziel: str) -> bytes:
    with mock.patch("mkpfs.pfs.time.time", return_value=JETZT):
        build_pfs(source_root=Path(ordner), output_path=Path(ziel), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
                  inode_bits=32, case_insensitive=True, signed=False, compress=False, threshold_gain=0, cpu_count=1,
                  zlib_level=6, dry_run=False, verbose=False, progress=Progress(enabled=False))
    return Path(ziel).read_bytes()


def _aus_liste(eintraege, ziel: str, **kw) -> bytes:
    with mock.patch("mkpfs.pfs.time.time", return_value=JETZT):
        ast.ffpfs_schreiben(eintraege, ziel, **kw)
    return Path(ziel).read_bytes()


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ffpfsstrom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def pfad(self, name: str) -> str:
        return os.path.join(self.tmp, name)


class MkpfsListeTests(_Grundlage):
    """``build_pfs(eintraege=...)``: dieselbe Datei wie aus dem Ordner."""

    def setUp(self) -> None:
        super().setUp()
        self.ordner = self.pfad("o")
        _schreiben(self.ordner, SPIEL)

    def test_gleiche_datei_wie_der_ordnerweg(self) -> None:
        self.assertEqual(_aus_ordner(self.ordner, self.pfad("a.ffpfs")), _aus_liste(_liste(SPIEL), self.pfad("b.ffpfs")))

    def test_reihenfolge_der_eintraege_und_der_schreibreihenfolge_aendert_nichts(self) -> None:
        soll = _aus_ordner(self.ordner, self.pfad("a.ffpfs"))
        umgekehrt = list(reversed(_liste(SPIEL)))
        self.assertEqual(soll, _aus_liste(umgekehrt, self.pfad("b.ffpfs")))
        self.assertEqual(soll, _aus_liste(_liste(SPIEL), self.pfad("c.ffpfs"),
                                          reihenfolge=["readme.ini", "data/gross.bin", "eboot.bin"]))

    def test_jeder_oeffner_genau_einmal_leere_nie(self) -> None:
        zaehler: dict[str, int] = {}
        _aus_liste(_liste(SPIEL, zaehler), self.pfad("a.ffpfs"))
        self.assertEqual({rel for rel, d in SPIEL.items() if d}, set(zaehler))
        self.assertTrue(all(n == 1 for n in zaehler.values()), zaehler)

    def test_die_schreibreihenfolge_wird_befolgt(self) -> None:
        reihe: list[str] = []

        def beobachtet(inhalte):
            return [(rel, g, (lambda o=o, rel=rel: (reihe.append(rel), o())[1])) for rel, g, o in _liste(inhalte)]
        _aus_liste(beobachtet(SPIEL), self.pfad("a.ffpfs"), reihenfolge=["readme.ini", "data/gross.bin"])
        self.assertEqual(["readme.ini", "data/gross.bin"], reihe[:2])
        self.assertEqual(len([d for d in SPIEL.values() if d]), len(reihe))

    def test_systemdateien_des_betriebssystems_fallen_weg_wie_im_ordnerweg(self) -> None:
        mit = dict(SPIEL, **{".DS_Store": b"x", "data/._klein.cfg": b"y"})
        self.assertEqual(_aus_liste(_liste(SPIEL), self.pfad("a.ffpfs")), _aus_liste(_liste(mit), self.pfad("b.ffpfs")))

    def test_das_ergebnis_liest_der_lesebaum_als_flaches_pfs(self) -> None:
        ziel = self.pfad("a.ffpfs")
        _aus_liste(_liste(SPIEL), ziel)
        with sb.PfsBaum(ziel) as baum:
            dateien = baum.suchen()
            self.assertEqual("pfs", baum.art)
            self.assertEqual({rel for rel in SPIEL}, set(dateien))
            for rel, daten in SPIEL.items():
                self.assertEqual(daten, b"".join(dateien[rel].lesen()), rel)

    def test_gross_und_kleinschreibung_ist_ein_gueltiges_pfs(self) -> None:
        """Namen, die sich nur in der Schreibung unterscheiden, kann kein Ordner auf Windows halten; das PFS hat dafuer die Kollisionstabelle."""
        inhalte = {"A.txt": b"gross", "a.txt": b"klein", "d/X.bin": b"1", "d/x.bin": b"2", "eboot.bin": b"e"}
        ziel = self.pfad("k.ffpfs")
        _aus_liste(_liste(inhalte), ziel)
        with sb.PfsBaum(ziel) as baum:
            gelesen = {rel: b"".join(d.lesen()) for rel, d in baum.suchen().items()}
        self.assertEqual(inhalte, gelesen)

    def test_abgelehnt(self) -> None:
        offen = lambda: iter([b"x"])                              # noqa: E731
        for eintraege, text in [
            ([("ü.bin", 1, offen)], "non-ASCII"),
            ([("a/../b.bin", 1, offen)], "unusable"),
            ([("a//b.bin", 1, offen)], "unusable"),
            ([("a\\b.bin", 1, offen)], "unusable"),
            ([("a.bin", 1, offen), ("a.bin", 1, offen)], "twice"),
            ([("a", 1, offen), ("a/b.bin", 1, offen)], "file and as a directory"),
        ]:
            with self.assertRaises(BuildError, msg=str(eintraege)) as ctx:
                _aus_liste(eintraege, self.pfad("x.ffpfs"))
            self.assertIn(text, str(ctx.exception))
            self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("x.")])

    def test_zu_kurz_und_zu_lang_lassen_nichts_zurueck(self) -> None:
        for angabe, daten in ((10, b"abc"), (2, b"abc")):
            with self.subTest(angabe=angabe):
                with self.assertRaises(BuildError):
                    _aus_liste([("a.bin", angabe, lambda d=daten: iter([d]))], self.pfad("k.ffpfs"))
                self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("k.")])

    def test_nur_flach_unkomprimiert_unsigniert(self) -> None:
        for kw in ({"compress": True}, {"signed": True}, {"encrypted": True}):
            with self.subTest(kw=kw):
                parameter = dict(block_size=65536, pfs_version=consts.PFS_VERSION_PS5, inode_bits=32, case_insensitive=True,
                                 signed=False, compress=False, threshold_gain=0, cpu_count=1, zlib_level=6, dry_run=False,
                                 verbose=False)
                parameter.update(kw)
                with self.assertRaises(BuildError):
                    build_pfs(source_root=Path("x"), output_path=Path(self.pfad("n.ffpfs")), eintraege=_liste(SPIEL),
                              progress=Progress(enabled=False), **parameter)

    def test_eigener_fortschritt_statt_terminal(self) -> None:
        ereignisse: list[tuple] = []
        with mock.patch("sys.stderr") as fehlerausgabe:
            ast.ffpfs_schreiben(_liste(SPIEL), self.pfad("a.ffpfs"),
                                melden=lambda *a: ereignisse.append(a))
        self.assertFalse(fehlerausgabe.write.called)
        schreiben = [e for e in ereignisse if e[0] == "write"]
        self.assertTrue(schreiben)
        # Gezaehlt werden die Nutzdaten samt den Verzeichnisbloecken; am Ende ist alles geschrieben.
        self.assertEqual(schreiben[-1][2], schreiben[-1][3])
        self.assertGreaterEqual(schreiben[-1][3], sum(len(d) for d in SPIEL.values()))


class AbbruchTests(_Grundlage):
    def test_abbruch_vor_dem_start(self) -> None:
        with self.assertRaises(ast.StromAbgebrochen):
            ast.ffpfs_schreiben(_liste(SPIEL), self.pfad("a.ffpfs"), abbruch=lambda: True)
        self.assertEqual([], os.listdir(self.tmp))

    def test_abbruch_mitten_in_einer_grossen_datei(self) -> None:
        gelesen: list[int] = []

        def langsam():
            for i in range(100):
                gelesen.append(i)
                yield b"x" * 1000

        # Der Abbruch kommt, nachdem das erste Stueck gelesen wurde - nicht erst am Ende der Datei.
        with self.assertRaises(ast.StromAbgebrochen):
            ast.ffpfs_schreiben([("gross.bin", 100_000, langsam)], self.pfad("a.ffpfs"), abbruch=lambda: len(gelesen) >= 2)
        self.assertLess(len(gelesen), 10)
        self.assertEqual([], os.listdir(self.tmp))

    def test_fehler_im_strom_laesst_nichts_zurueck_und_schliesst_den_oeffner(self) -> None:
        geschlossen: list[bool] = []

        def kaputt():
            try:
                yield b"abc"
                raise OSError("Platte weg")
            finally:
                geschlossen.append(True)

        with self.assertRaises(OSError):
            ast.ffpfs_schreiben([("a.bin", 100, kaputt)], self.pfad("a.ffpfs"))
        self.assertEqual([True], geschlossen)
        self.assertEqual([], os.listdir(self.tmp))


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class AbbildListeTests(_Grundlage):
    """Lose Dateien aus dem Baum, Packdateien aus dem zstd-Strom: dasselbe wie der Ordnerweg mit ``packen``."""

    def setUp(self) -> None:
        super().setUp()
        self.spiel = self.pfad("spiel")
        _schreiben(self.spiel, SPIEL)
        self.auswahl = z.dateien_auswaehlen(self.spiel)
        self.archiv = z.archiv_id_ableiten(self.auswahl, 3)

    def ordnerabbild(self, behalten: bool = False) -> bytes:
        ziel = self.pfad("ordnerweg")
        os.makedirs(ziel, exist_ok=True)
        gepackt = {r for r, _g in self.auswahl.gepackt}
        for rel, daten in SPIEL.items():
            if behalten or rel not in gepackt:
                _schreiben(ziel, {rel: daten})
        packs = self.pfad("ordnerpacks")
        z.packen(self.spiel, packs, self.auswahl, stufe=3, arbeiter=2, archiv_id=self.archiv)
        for name in os.listdir(packs):
            shutil.copy2(os.path.join(packs, name), os.path.join(ziel, name))
        return _aus_ordner(ziel, self.pfad("ordner.ffpfs"))

    def stromabbild(self, baum, ziel: str, *, behalten: bool = False, **kw) -> bytes:
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        eintraege, reihenfolge, schliessen = ast.abbild_liste(baum, self.auswahl, messung, originale_behalten=behalten, arbeiter=2,
                                                              **kw)
        try:
            return _aus_liste(eintraege, ziel, reihenfolge=reihenfolge)
        finally:
            schliessen()

    def test_wie_der_ordnerweg(self) -> None:
        self.assertEqual(self.ordnerabbild(), self.stromabbild(sb.OrdnerBaum(self.spiel), self.pfad("strom.ffpfs")))

    def test_mit_originalen(self) -> None:
        self.assertEqual(self.ordnerabbild(behalten=True),
                         self.stromabbild(sb.OrdnerBaum(self.spiel), self.pfad("strom.ffpfs"), behalten=True))

    def test_mehrere_baender(self) -> None:
        with mock.patch.object(z, "VOLUME_LIMIT", 400_000):
            ordner = self.ordnerabbild()
            strom = self.stromabbild(sb.OrdnerBaum(self.spiel), self.pfad("strom.ffpfs"))
        self.assertEqual(ordner, strom)

    def test_aus_exfat_quelle(self) -> None:
        quelle = self.pfad("quelle.exfat")
        with open(quelle, "wb") as fh:
            fh.write(b"".join(w.iter_exfat_image(Path(self.spiel))))
        with sb.ExfatBaum(quelle) as baum:
            self.assertEqual(self.ordnerabbild(), self.stromabbild(baum, self.pfad("strom.ffpfs")))

    def test_die_packdateien_kommen_in_stromreihenfolge(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        with mock.patch.object(z, "VOLUME_LIMIT", 400_000):
            messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
            eintraege, reihenfolge, schliessen = ast.abbild_liste(baum, self.auswahl, messung, arbeiter=2)
            self.addCleanup(schliessen)
        namen = [n for n, _g in messung.dateien()]
        self.assertGreater(len(namen), 2)
        self.assertEqual(namen, reihenfolge[-len(namen):])
        self.assertEqual({rel for rel, _g, _o in eintraege}, set(reihenfolge))

    def test_packname_schon_in_der_quelle(self) -> None:
        _schreiben(self.spiel, {"ampr_zstd.index": b"alt"})
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(sb.OrdnerBaum(self.spiel), self.auswahl, stufe=3, archiv_id=self.archiv)
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            ast.abbild_liste(baum, self.auswahl, messung)
        self.assertEqual("ampr_zstd.ausgabe_belegt", str(ctx.exception))

    def test_quelle_geaendert_bricht_ab_und_laesst_nichts_zurueck(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        voll = os.path.join(self.spiel, "Media", "zufall.bin")
        daten = bytearray(Path(voll).read_bytes())
        daten[1000] ^= 1
        Path(voll).write_bytes(bytes(daten))
        eintraege, reihenfolge, schliessen = ast.abbild_liste(baum, self.auswahl, messung, arbeiter=2)
        self.addCleanup(schliessen)
        with self.assertRaises(z.ZstdPackFehler):
            ast.ffpfs_schreiben(eintraege, self.pfad("a.ffpfs"), reihenfolge=reihenfolge)
        self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("a.ffpfs")])

    def test_schliessen_beendet_die_faeden(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        vorher = threading.active_count()
        eintraege, reihenfolge, schliessen = ast.abbild_liste(baum, self.auswahl, messung, arbeiter=2)
        packs = [(r, g, o) for r, g, o in eintraege if z.ist_packname(r)]
        stueck = next(iter(packs[0][2]()))                        # der Strom laeuft an
        self.assertTrue(stueck)
        schliessen()
        schliessen()                                              # mehrfaches Rufen schadet nicht
        for _ in range(50):
            if threading.active_count() <= vorher:
                break
            time.sleep(0.05)
        self.assertLessEqual(threading.active_count(), vorher)

    def test_fortschritt_des_stroms(self) -> None:
        werte: list[float] = []
        self.stromabbild(sb.OrdnerBaum(self.spiel), self.pfad("strom.ffpfs"), fortschritt=werte.append)
        self.assertAlmostEqual(1.0, werte[-1])


class RuecklesenTests(_Grundlage):
    """``abbild_pruefen``: dieselbe Rueckleseprobe liest ein flaches ``.ffpfs``."""

    def setUp(self) -> None:
        super().setUp()
        self.ziel = self.pfad("a.ffpfs")
        _aus_liste(_liste(SPIEL), self.ziel)
        self.pruef = ap.Pruefstand(mkpfs_ordner_holen=lambda: str(PROJEKT / "MkPFS-1.1.0"))

    def erwartet(self, inhalte: dict[str, bytes]):
        return [(rel, len(d), (lambda n, d=d: d[:n])) for rel, d in inhalte.items()]

    def test_in_ordnung(self) -> None:
        befund = self.pruef._verify_exfat_erwartet(self.ziel, self.erwartet(SPIEL), flach=True)
        self.assertTrue(befund["checked"], befund)
        self.assertTrue(befund["ok"], befund)
        self.assertGreater(befund["befund"]["stichprobe_dateien"], 0)

    def test_fehlende_zusaetzliche_und_falsche_groesse(self) -> None:
        soll = dict(SPIEL)
        del soll["readme.ini"]
        soll["neu.bin"] = b"neu"
        soll["data/klein.cfg"] = b"a=1\nlaenger\n"
        befund = self.pruef._verify_exfat_erwartet(self.ziel, self.erwartet(soll), flach=True)
        self.assertFalse(befund["ok"])
        self.assertEqual(["neu.bin"], befund["befund"]["fehlen"])
        self.assertEqual(["readme.ini"], befund["befund"]["zuviel"])
        self.assertEqual(1, len(befund["befund"]["groesse"]))

    def test_anderer_inhalt_wird_gemeldet(self) -> None:
        soll = dict(SPIEL)
        soll["eboot.bin"] = b"\x7fELF" + b"\x01" * 2000                  # gleiche Groesse, anderer Inhalt
        befund = self.pruef._verify_exfat_erwartet(self.ziel, self.erwartet(soll), flach=True)
        self.assertFalse(befund["ok"])
        self.assertIn("eboot.bin", befund["befund"]["inhalt"])

    def test_ein_umhuellendes_abbild_ist_kein_flaches(self) -> None:
        huelle = self.pfad("h.ffpfsc")
        wurzel = self.pfad("spiel")
        _schreiben(wurzel, SPIEL)
        from mkpfs.pfs import build_pfs_stream_from_exfat
        build_pfs_stream_from_exfat(source_root=Path(wurzel), output_path=Path(huelle), block_size=65536,
                                    pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0,
                                    cpu_count=1)
        befund = self.pruef._verify_exfat_erwartet(huelle, self.erwartet(SPIEL), flach=True)
        self.assertTrue(befund.get("lesefehler"), befund)

    def test_kein_abbild(self) -> None:
        Path(self.pfad("kaputt.ffpfs")).write_bytes(b"nichts" * 100)
        befund = self.pruef._verify_exfat_erwartet(self.pfad("kaputt.ffpfs"), self.erwartet(SPIEL), flach=True)
        self.assertTrue(befund.get("lesefehler"), befund)

    def test_der_lesegriff_ist_danach_zu(self) -> None:
        self.pruef._verify_exfat_erwartet(self.ziel, self.erwartet(SPIEL), flach=True)
        os.replace(self.ziel, self.pfad("b.ffpfs"))                 # unter Windows scheitert das mit einem offenen Griff


class WaechterTests(unittest.TestCase):
    def test_die_zutat_steht_in_upstream_md(self) -> None:
        text = (PROJEKT / "MkPFS-1.1.0" / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("scan_liste", text)
        self.assertIn("write_stream_to_offset", text)
        self.assertIn("test_ffpfs_strom.py", text)

    def test_die_signatur(self) -> None:
        import inspect
        from mkpfs import pfs
        parameter = inspect.signature(build_pfs).parameters
        for name in ("eintraege", "reihenfolge", "progress"):
            self.assertIn(name, parameter, name)
        self.assertTrue(callable(pfs.scan_liste))
        self.assertTrue(callable(pfs.write_stream_to_offset))

    def test_der_ordnerweg_hat_dieselbe_schreibschleife(self) -> None:
        """Ordner und Liste teilen sich ``build_pfs``: Ein Oeffner ist nur ein weiterer Fall der Schreibschleife."""
        import inspect
        from mkpfs import pfs
        quelle = inspect.getsource(pfs.build_pfs)
        self.assertIn("write_source_to_offset(", quelle)
        self.assertIn("write_stream_to_offset(", quelle)


if __name__ == "__main__":
    unittest.main()
