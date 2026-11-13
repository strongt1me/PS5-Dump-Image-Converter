# -*- coding: utf-8 -*-
"""``.ffpfsc`` als Ausgabe im Strom (Stufe 3, Etappe 8): ein exFAT-Byte-Strom wird in einem Zug in ein komprimiertes PFS geschrieben.

Zwei Ebenen: (1) MkPFS ``build_pfs_stream_from_blocks`` - der aus ``build_pfs_stream_from_exfat`` herausgeloeste Teil - muss
**dasselbe** Abbild schreiben wie der Ordnerweg; (2) ``abbild_strom.ffpfsc_schreiben`` mit Abbruch, Fortschritt, Namen und Aufraeumen,
und das Ergebnis liest der Lesebaum (``PfsBaum``) wieder als Spiel.
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

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ffpfsc_strom")

from mkpfs import consts                                     # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image, iter_exfat_image_liste   # noqa: E402
from mkpfs.pfs import build_pfs_stream_from_blocks, build_pfs_stream_from_exfat, open_inner_file_view   # noqa: E402

from ps5_validator.utils import abbild_strom as ast          # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402


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
    "data/a.pak": _zufall(300_000, 3),
    "data/text.txt": b"Hallo Welt\n" * 60_000,
    "data/b/leer.txt": b"",
    "readme.ini": b"[x]\n",
}


def _schreiben(wurzel: str, inhalte: dict[str, bytes]) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)


def _innen(pfad: str) -> bytes:
    """Das innere Abbild einer .ffpfsc, ganz gelesen."""
    sicht = open_inner_file_view(Path(pfad))
    assert sicht is not None, pfad
    view, fh, _name = sicht
    try:
        view.seek(0)
        return view.read(-1)
    finally:
        fh.close()


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="ffpfscstrom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.spiel = os.path.join(self.tmp, "spiel")
        _schreiben(self.spiel, SPIEL)

    def erzeuger(self):
        return lambda on_layout: iter_exfat_image(Path(self.spiel), on_layout=on_layout)


class MkpfsKernTests(_Grundlage):
    """``build_pfs_stream_from_blocks`` ist der herausgeloeste Teil von ``build_pfs_stream_from_exfat``."""

    PARAMETER = dict(block_size=65536, pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6,
                     threshold_gain=0, cpu_count=1)

    def test_gleiche_datei_wie_der_ordnerweg(self) -> None:
        aus_ordner = os.path.join(self.tmp, "ordner.ffpfsc")
        aus_strom = os.path.join(self.tmp, "strom.ffpfsc")
        with mock.patch("mkpfs.pfs.time.time", return_value=1_700_000_000.0):
            build_pfs_stream_from_exfat(source_root=Path(self.spiel), output_path=Path(aus_ordner), **self.PARAMETER)
            groesse: list[int] = []
            strom = iter_exfat_image(Path(self.spiel), on_layout=groesse.append)
            erstes = next(strom)
            import itertools
            build_pfs_stream_from_blocks(
                payload_stream=itertools.chain([erstes], strom), raw_size=groesse[0], inner_name="PPSA04263.exfat",
                source_label=Path(self.spiel), output_path=Path(aus_strom), **self.PARAMETER)
        self.assertEqual(Path(aus_ordner).read_bytes(), Path(aus_strom).read_bytes())

    def test_falsche_laenge_ist_ein_fehler_ohne_rest(self) -> None:
        ziel = os.path.join(self.tmp, "falsch.ffpfsc")
        groesse: list[int] = []
        strom = iter_exfat_image(Path(self.spiel), on_layout=groesse.append)
        erstes = next(strom)
        import itertools
        with self.assertRaises(Exception):
            build_pfs_stream_from_blocks(
                payload_stream=itertools.chain([erstes], strom), raw_size=groesse[0] + 3 * 65536, inner_name="x.exfat",
                source_label=Path(self.spiel), output_path=Path(ziel), **self.PARAMETER)
        self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("falsch")])

    def test_eine_abweichung_um_wenige_bytes_ist_ein_fehler(self) -> None:
        """Der Kompressor vergleicht nur ganze Bloecke; ein Strom, der um 100 Bytes abweicht, wurde mit Nullen aufgefuellt abgeliefert."""
        import itertools
        for abweichung in (100, -100, 1, -1):
            with self.subTest(abweichung=abweichung):
                ziel = os.path.join(self.tmp, "abw%d.ffpfsc" % abweichung)
                groesse: list[int] = []
                strom = iter_exfat_image(Path(self.spiel), on_layout=groesse.append)
                erstes = next(strom)
                with self.assertRaises(Exception) as ctx:
                    build_pfs_stream_from_blocks(
                        payload_stream=itertools.chain([erstes], strom), raw_size=groesse[0] + abweichung, inner_name="x.exfat",
                        source_label=Path(self.spiel), output_path=Path(ziel), **self.PARAMETER)
                self.assertIn("length", str(ctx.exception).lower())
                self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("abw%d" % abweichung)])

    def test_eigener_fortschritt_statt_terminal(self) -> None:
        from mkpfs.pbar import Progress
        ereignisse: list[tuple] = []
        groesse: list[int] = []
        strom = iter_exfat_image(Path(self.spiel), on_layout=groesse.append)
        erstes = next(strom)
        import itertools
        with mock.patch("sys.stderr") as fehlerausgabe:
            build_pfs_stream_from_blocks(
                payload_stream=itertools.chain([erstes], strom), raw_size=groesse[0], inner_name="x.exfat",
                source_label=Path(self.spiel), output_path=Path(os.path.join(self.tmp, "p.ffpfsc")),
                progress=Progress(enabled=False, listener=lambda *a: ereignisse.append(a)), **self.PARAMETER)
        self.assertFalse(fehlerausgabe.write.called, "Mit Hoerer und enabled=False darf nichts auf das Terminal gehen")
        self.assertTrue(any(e[0] == "step" for e in ereignisse))
        self.assertEqual(groesse[0], max(e[4] for e in ereignisse if e[0] == "step"))


class WaechterTests(unittest.TestCase):
    def test_die_zutat_steht_in_upstream_md(self) -> None:
        """Eine Abweichung von der Vorlage, die nicht in UPSTREAM.md steht, geht beim naechsten Fassungswechsel verloren."""
        text = (ROOT / "MkPFS-1.1.0" / "UPSTREAM.md").read_text(encoding="utf-8")
        self.assertIn("build_pfs_stream_from_blocks", text)
        self.assertIn("test_ffpfsc_strom.py", text)

    def test_die_signatur(self) -> None:
        import inspect
        parameter = inspect.signature(build_pfs_stream_from_blocks).parameters
        for name in ("payload_stream", "raw_size", "inner_name", "source_label", "output_path", "block_size", "pfs_version",
                     "case_insensitive", "zlib_level", "threshold_gain", "cpu_count", "progress", "start_time"):
            self.assertIn(name, parameter, name)

    def test_der_ordnerweg_ruft_den_kern(self) -> None:
        import inspect
        from mkpfs import pfs
        self.assertIn("build_pfs_stream_from_blocks(", inspect.getsource(pfs.build_pfs_stream_from_exfat))


class SchreibenTests(_Grundlage):
    def schreiben(self, name: str = "spiel.ffpfsc", **kw):
        ziel = os.path.join(self.tmp, name)
        return ziel, ast.ffpfsc_schreiben(self.erzeuger(), ziel, quelle_ordner=self.spiel, cpu_count=1, **kw)

    def test_der_lesebaum_liest_das_spiel(self) -> None:
        ziel, stats = self.schreiben()
        self.assertTrue(os.path.isfile(ziel))
        with sb.PfsBaum(ziel) as baum:
            dateien = baum.suchen()
            self.assertEqual(("exfat", 1), (baum.art, baum.ebenen))
            self.assertEqual(sorted(SPIEL), sorted(dateien))
            for rel, daten in SPIEL.items():
                self.assertEqual(daten, b"".join(dateien[rel].lesen()), rel)

    def test_inneres_abbild_gleicht_dem_ordnerweg(self) -> None:
        ziel, _stats = self.schreiben()
        referenz = os.path.join(self.tmp, "referenz.exfat")
        with open(referenz, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        self.assertEqual(Path(referenz).read_bytes(), _innen(ziel))

    def test_name_aus_der_param_json(self) -> None:
        from mkpfs.pfs import inspect_pfs_image
        ziel, _stats = self.schreiben()
        befund = inspect_pfs_image(Path(ziel), verify_payloads=False)
        self.assertEqual(["PPSA04263.exfat"], list(befund.file_inodes))

    def test_name_ohne_param_json_aus_dem_ordnernamen(self) -> None:
        from mkpfs.pfs import inspect_pfs_image
        os.remove(os.path.join(self.spiel, "sce_sys", "param.json"))
        ziel, _stats = self.schreiben()
        befund = inspect_pfs_image(Path(ziel), verify_payloads=False)
        self.assertEqual(["spiel.exfat"], list(befund.file_inodes))

    def test_aus_einer_dateiliste(self) -> None:
        """Der Strom kann auch aus ``iter_exfat_image_liste`` kommen (so liefert ihn der Lesebaum-Weg)."""
        eintraege = [(rel, len(d), (lambda d=d: iter([d]))) for rel, d in SPIEL.items()]
        ziel = os.path.join(self.tmp, "liste.ffpfsc")
        ast.ffpfsc_schreiben(lambda on_layout: iter_exfat_image_liste(eintraege, on_layout=on_layout), ziel,
                             quelle_ordner=self.spiel, cpu_count=2)
        with sb.PfsBaum(ziel) as baum:
            self.assertEqual({k: len(v) for k, v in SPIEL.items()}, {d.rel: d.groesse for d in baum.dateien()})

    def test_fortschritt_endet_bei_der_gesamtgroesse(self) -> None:
        schritte: list[tuple] = []
        groessen: list[int] = []
        self.schreiben(melden=lambda phase, fertig, gesamt, byte_zahl: schritte.append((phase, fertig, gesamt, byte_zahl)),
                       on_layout=groessen.append)
        self.assertTrue(schritte)
        self.assertEqual("compress", schritte[-1][0])
        self.assertEqual(groessen[0], schritte[-1][3])
        self.assertEqual(schritte[-1][1], schritte[-1][2])

    def test_ein_leerer_strom_ist_ein_fehler_kein_abbruch(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            ast.ffpfsc_schreiben(lambda on_layout: iter(()), os.path.join(self.tmp, "leer.ffpfsc"),
                                 quelle_ordner=self.spiel, cpu_count=1)
        self.assertNotIsInstance(ctx.exception, ast.StromAbgebrochen)

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        zaehler = {"n": 0}

        def abbruch() -> bool:
            zaehler["n"] += 1
            return zaehler["n"] > 3

        ziel = os.path.join(self.tmp, "abbruch.ffpfsc")
        with self.assertRaises(ast.StromAbgebrochen):
            ast.ffpfsc_schreiben(self.erzeuger(), ziel, quelle_ordner=self.spiel, cpu_count=1, abbruch=abbruch)
        self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("abbruch")])

    def test_fehler_im_strom_laesst_nichts_zurueck(self) -> None:
        def kaputt(on_layout):
            yield from iter_exfat_image(Path(self.spiel), on_layout=on_layout)
            raise OSError("Platte weg")

        ziel = os.path.join(self.tmp, "kaputt.ffpfsc")
        with self.assertRaises(OSError):
            ast.ffpfsc_schreiben(kaputt, ziel, quelle_ordner=self.spiel, cpu_count=1)
        self.assertEqual([], [n for n in os.listdir(self.tmp) if n.startswith("kaputt")])

    def test_mehrere_kerne_aendern_nichts(self) -> None:
        a, _s = self.schreiben("eins.ffpfsc")
        b = os.path.join(self.tmp, "vier.ffpfsc")
        ast.ffpfsc_schreiben(self.erzeuger(), b, quelle_ordner=self.spiel, cpu_count=4)
        self.assertEqual(_innen(a), _innen(b))


class RechenwerkTests(_Grundlage):
    """Das Rechenwerk der PFSC-Bloecke wird im eigenen Prozess gesetzt (die Kommandozeile bekam es als ``--compression-backend``)."""

    def setUp(self) -> None:
        super().setUp()
        from mkpfs import compression
        self.comp = compression
        vorher = compression.get_backend_name()
        self.addCleanup(compression.set_backend, vorher)

    def test_der_vorgegebene_wird_gesetzt(self) -> None:
        self.comp.set_backend("zlib")                        # jemand hat etwas anderes eingestellt
        ast.ffpfsc_schreiben(lambda on_layout: iter_exfat_image(Path(self.spiel), on_layout=on_layout),
                             os.path.join(self.tmp, "a.ffpfsc"), quelle_ordner=self.spiel, cpu_count=1, backend="zlib-ng")
        self.assertEqual("zlib-ng", self.comp.get_backend_name())

    def test_nicht_ladbar_faellt_auf_zlib_zurueck_und_der_strom_ist_gleich(self) -> None:
        ziel_ng = os.path.join(self.tmp, "ng.ffpfsc")
        ast.ffpfsc_schreiben(self.erzeuger(), ziel_ng, quelle_ordner=self.spiel, cpu_count=1, backend="zlib-ng")
        ziel_z = os.path.join(self.tmp, "z.ffpfsc")
        with mock.patch.object(self.comp, "_load_zlib_ng", side_effect=ImportError("kein Binary")):
            ast.ffpfsc_schreiben(self.erzeuger(), ziel_z, quelle_ordner=self.spiel, cpu_count=1, backend="zlib-ng")
            self.assertEqual("zlib", self.comp.get_backend_name())
        with sb.PfsBaum(ziel_z) as baum:                     # lesbar, gleiches Spiel
            self.assertEqual({k: len(v) for k, v in SPIEL.items()}, {d.rel: d.groesse for d in baum.dateien()})

    def test_ein_unbekanntes_rechenwerk_bricht_nicht_ab(self) -> None:
        ast.ffpfsc_schreiben(self.erzeuger(), os.path.join(self.tmp, "u.ffpfsc"), quelle_ordner=self.spiel, cpu_count=1,
                             backend="gibtsnicht")
        self.assertEqual("zlib", self.comp.get_backend_name())

    def test_das_hauptprogramm_reicht_das_rechenwerk_durch(self) -> None:
        quelle = (ROOT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertIn("backend=MKPFS_BACKEND", quelle)


class PfsPruefenTests(_Grundlage):
    """``abbild_strom.pfs_pruefen``: die Pruefung, die die Kommandozeile nach dem Packen laufen laesst (jeden Block entpacken)."""

    def setUp(self) -> None:
        super().setUp()
        self.ziel = os.path.join(self.tmp, "p.ffpfsc")
        ast.ffpfsc_schreiben(self.erzeuger(), self.ziel, quelle_ordner=self.spiel, cpu_count=1)

    def test_ein_gutes_abbild_besteht(self) -> None:
        fehler, _warnungen = ast.pfs_pruefen(self.ziel)
        self.assertEqual([], fehler)

    def test_ein_beschaedigter_block_faellt_auf(self) -> None:
        daten = bytearray(Path(self.ziel).read_bytes())
        for i in range(len(daten) // 2, len(daten) // 2 + 4000):
            daten[i] ^= 0xFF
        kaputt = os.path.join(self.tmp, "kaputt.ffpfsc")
        Path(kaputt).write_bytes(bytes(daten))
        fehler, _warnungen = ast.pfs_pruefen(kaputt)
        self.assertTrue(fehler, "ein beschaedigter Block muss gemeldet werden")

    def test_ein_abgeschnittenes_abbild_faellt_auf(self) -> None:
        daten = Path(self.ziel).read_bytes()
        kurz = os.path.join(self.tmp, "kurz.ffpfsc")
        Path(kurz).write_bytes(daten[: len(daten) // 2])
        try:
            fehler, _w = ast.pfs_pruefen(kurz)
        except Exception:                                    # noqa: BLE001 - auch eine Ausnahme meldet das Problem
            return
        self.assertTrue(fehler)

    def test_fortschritt_wird_gemeldet(self) -> None:
        schritte: list[tuple[int, int]] = []
        ast.pfs_pruefen(self.ziel, melden=lambda fertig, gesamt: schritte.append((fertig, gesamt)))
        self.assertTrue(schritte)
        self.assertEqual(schritte[-1][0], schritte[-1][1])

    def test_abbruch(self) -> None:
        with self.assertRaises(ast.StromAbgebrochen):
            ast.pfs_pruefen(self.ziel, abbruch=lambda: True)


class PruefungTests(_Grundlage):
    """Die Ruecklese-Pruefung liest die ``.ffpfsc`` ueber ihr inneres exFAT (``huelle=True``)."""

    def setUp(self) -> None:
        super().setUp()
        from ps5_validator.utils import abbild_pruefen as ap
        self.ap = ap
        self.ziel = os.path.join(self.tmp, "p.ffpfsc")
        ast.ffpfsc_schreiben(self.erzeuger(), self.ziel, quelle_ordner=self.spiel, cpu_count=1)
        self.p = ap.Pruefstand.__new__(ap.Pruefstand)
        self.p._t = lambda k, **w: k + " " + " ".join("%s=%s" % kv for kv in sorted(w.items()))
        self.p._extract_embedded_mkpfs = lambda: str(ROOT / "MkPFS-1.1.0")

    def erwartet(self, **abweichung):
        return [(rel, abweichung.get(rel, len(d)), (lambda n, d=d: d[:n])) for rel, d in SPIEL.items()]

    def test_in_ordnung(self) -> None:
        e = self.p._verify_exfat_erwartet(self.ziel, self.erwartet(), huelle=True)
        self.assertTrue(e["checked"] and e["ok"], e)
        self.assertIn("verify.inhalt_ok", e["detail"])

    def test_ohne_huelle_ist_es_kein_exfat(self) -> None:
        """Dieselbe Datei ohne ``huelle`` zu lesen ist ein Lesefehler - die Huelle ist ein PFS, kein exFAT."""
        e = self.p._verify_exfat_erwartet(self.ziel, self.erwartet(), huelle=False)
        self.assertTrue(e.get("lesefehler"), e)

    def test_falsche_groesse_wird_gemeldet(self) -> None:
        e = self.p._verify_exfat_erwartet(self.ziel, self.erwartet(**{"data/a.pak": 1}), huelle=True)
        self.assertFalse(e["ok"])
        self.assertIn("verify.inhalt_groesse", e["detail"])

    def test_anderer_inhalt_wird_gemeldet(self) -> None:
        erwartet = [(rel, g, (lambda n: b"X" * n) if rel == "eboot.bin" else a) for rel, g, a in self.erwartet()]
        e = self.p._verify_exfat_erwartet(self.ziel, erwartet, huelle=True)
        self.assertFalse(e["ok"])
        self.assertIn("verify.inhalt_inhalt", e["detail"])

    def test_fehlende_und_zusaetzliche_dateien(self) -> None:
        weniger = [x for x in self.erwartet() if x[0] != "readme.ini"]
        e = self.p._verify_exfat_erwartet(self.ziel, weniger, huelle=True)
        self.assertIn("verify.inhalt_zuviel", e["detail"])
        mehr = self.erwartet() + [("data/fehlt.bin", 3, None)]
        e = self.p._verify_exfat_erwartet(self.ziel, mehr, huelle=True)
        self.assertIn("verify.inhalt_fehlen", e["detail"])

    def test_kein_abbild(self) -> None:
        kaputt = os.path.join(self.tmp, "k.ffpfsc")
        Path(kaputt).write_bytes(b"kein pfs" * 5000)
        self.assertTrue(self.p._verify_exfat_erwartet(kaputt, self.erwartet(), huelle=True).get("lesefehler"))

    def test_der_lesegriff_ist_danach_zu(self) -> None:
        """Nach der Pruefung laesst sich die Datei umbenennen/ersetzen (unter Windows haelt ein offener Griff sie fest)."""
        self.p._verify_exfat_erwartet(self.ziel, self.erwartet(), huelle=True)
        neu = self.ziel + ".neu"
        os.replace(self.ziel, neu)
        self.assertTrue(os.path.isfile(neu))


if __name__ == "__main__":
    unittest.main()
