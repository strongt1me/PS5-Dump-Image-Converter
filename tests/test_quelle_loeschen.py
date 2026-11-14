# -*- coding: utf-8 -*-
"""``quelle_loeschen``: Die Quelle nach einem erfolgreichen Lauf loeschen - nur, wenn alles stimmt (14.11.2026)."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import quelle_loeschen as ql      # noqa: E402


class _Ablage(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.wurzel = Path(tmp.name) / "arbeit" / "tief"
        self.wurzel.mkdir(parents=True)

    def datei(self, name: str, inhalt: bytes = b"daten") -> str:
        pfad = self.wurzel / name
        pfad.parent.mkdir(parents=True, exist_ok=True)
        pfad.write_bytes(inhalt)
        return str(pfad)

    def spiel(self, name: str = "Spiel") -> str:
        ordner = self.wurzel / name
        (ordner / "sce_sys").mkdir(parents=True)
        (ordner / "eboot.bin").write_bytes(b"x" * 100)
        (ordner / "sce_sys" / "param.json").write_bytes(b"{}")
        return str(ordner)


class StempelTests(_Ablage):
    def test_datei_und_ordner(self) -> None:
        d = self.datei("a.exfat", b"x" * 10)
        self.assertEqual(("datei", 10), ql.stempel_nehmen(d)[:2])
        o = self.spiel()
        stand = ql.stempel_nehmen(o)
        self.assertEqual(("ordner", 2, 102), stand[:3])

    def test_unlesbar_ist_none(self) -> None:
        self.assertIsNone(ql.stempel_nehmen(str(self.wurzel / "gibtsnicht")))

    def test_aenderungen_aendern_den_stempel(self) -> None:
        o = self.spiel()
        vorher = ql.stempel_nehmen(o)
        Path(o, "neu.bin").write_bytes(b"1")
        self.assertNotEqual(vorher, ql.stempel_nehmen(o))
        vorher = ql.stempel_nehmen(o)
        Path(o, "neu.bin").unlink()
        self.assertNotEqual(vorher, ql.stempel_nehmen(o))
        vorher = ql.stempel_nehmen(o)
        Path(o, "eboot.bin").write_bytes(b"y" * 100)            # gleiche Groesse, andere Zeit
        os.utime(Path(o, "eboot.bin"), ns=(time.time_ns() + 10 ** 10, time.time_ns() + 10 ** 10))
        self.assertNotEqual(vorher, ql.stempel_nehmen(o))


class PruefenTests(_Ablage):
    def _ok(self) -> "tuple[str, str, tuple]":
        quelle = self.spiel()
        ergebnis = self.datei("aus/Spiel.exfat", b"e" * 50)
        return quelle, ergebnis, ql.stempel_nehmen(quelle)

    def test_alles_stimmt(self) -> None:
        quelle, ergebnis, stempel = self._ok()
        self.assertEqual("", ql.pruefen(quelle, ergebnis, stempel))

    def test_datei_als_quelle(self) -> None:
        quelle = self.datei("alt.ffpfsc", b"q" * 5)
        ergebnis = self.datei("aus/neu.exfat", b"e" * 5)
        self.assertEqual("", ql.pruefen(quelle, ergebnis, ql.stempel_nehmen(quelle)))

    def test_quelle_fehlt(self) -> None:
        _q, ergebnis, stempel = self._ok()
        self.assertEqual("quelle_fehlt", ql.pruefen(str(self.wurzel / "weg"), ergebnis, stempel))
        self.assertEqual("quelle_fehlt", ql.pruefen("", ergebnis, stempel))

    def test_ergebnis_fehlt_oder_ist_leer(self) -> None:
        quelle, _e, stempel = self._ok()
        self.assertEqual("ergebnis_fehlt", ql.pruefen(quelle, str(self.wurzel / "gibtsnicht.exfat"), stempel))
        leer = self.datei("aus/leer.exfat", b"")
        self.assertEqual("ergebnis_fehlt", ql.pruefen(quelle, leer, stempel))
        leerer_ordner = self.wurzel / "aus" / "leererOrdner"
        leerer_ordner.mkdir()
        self.assertEqual("ergebnis_fehlt", ql.pruefen(quelle, str(leerer_ordner), stempel))
        self.assertEqual("ergebnis_fehlt", ql.pruefen(quelle, "", stempel))

    def test_selbst_ziel_ist_derselbe_pfad(self) -> None:
        quelle = self.datei("a.exfat", b"x" * 9)
        self.assertEqual("gleicher_pfad", ql.pruefen(quelle, quelle, ql.stempel_nehmen(quelle)))

    def test_ergebnis_im_quellordner(self) -> None:
        quelle = self.spiel()
        ergebnis = self.datei("Spiel/ergebnis/Spiel.exfat", b"e" * 9)
        self.assertEqual("ergebnis_in_quelle", ql.pruefen(quelle, ergebnis, ql.stempel_nehmen(quelle)))

    def test_quelle_im_ergebnisordner(self) -> None:
        ergebnis_ordner = self.wurzel / "ausgabe"
        quelle = ergebnis_ordner / "Spiel"
        (quelle / "sce_sys").mkdir(parents=True)
        (quelle / "eboot.bin").write_bytes(b"x")
        self.assertEqual("quelle_in_ergebnis", ql.pruefen(str(quelle), str(ergebnis_ordner), ql.stempel_nehmen(str(quelle))))

    def test_aehnlicher_name_ist_nicht_ineinander(self) -> None:
        """Gegenprobe: ``Spiel`` und ``Spiel2`` liegen nebeneinander, nicht ineinander."""
        quelle = self.spiel("Spiel")
        ergebnis = self.datei("Spiel2/aus.exfat", b"e" * 4)
        self.assertEqual("", ql.pruefen(quelle, ergebnis, ql.stempel_nehmen(quelle)))

    def test_ohne_stempel_wird_nicht_geloescht(self) -> None:
        quelle, ergebnis, _s = self._ok()
        self.assertEqual("ohne_stempel", ql.pruefen(quelle, ergebnis, None))

    def test_geaenderte_quelle_bleibt(self) -> None:
        quelle, ergebnis, stempel = self._ok()
        Path(quelle, "dazu.bin").write_bytes(b"jemand war hier")
        self.assertEqual("geaendert", ql.pruefen(quelle, ergebnis, stempel))

    def test_geschuetzte_pfade(self) -> None:
        stempel = ("ordner", 1, 1, 1)
        ergebnis = self.datei("aus/e.exfat", b"e")
        wurzel = os.path.abspath(os.sep)
        heim = os.path.expanduser("~")
        for pfad in (wurzel, heim, os.path.join(heim, "Documents"), os.path.join(heim, "Downloads"), os.path.dirname(heim)):
            with self.subTest(pfad=pfad):
                if not os.path.lexists(pfad):
                    continue
                self.assertEqual("geschuetzt", ql.pruefen(pfad, ergebnis, stempel))

    def test_verknuepfung_wird_nicht_geloescht(self) -> None:
        ziel = self.spiel()
        link = self.wurzel / "link"
        try:
            os.symlink(ziel, str(link), target_is_directory=True)
        except (OSError, NotImplementedError, AttributeError) as exc:
            self.skipTest("Verknuepfung nicht anlegbar: %s" % exc)
        ergebnis = self.datei("aus/e.exfat", b"e")
        self.assertEqual("verknuepfung", ql.pruefen(str(link), ergebnis, ql.stempel_nehmen(str(link))))


class JunctionTests(_Ablage):
    """Eine Junction braucht unter Windows keine besonderen Rechte (anders als eine symbolische Verknuepfung)."""

    @unittest.skipUnless(os.name == "nt", "Junctions gibt es nur unter Windows")
    def test_junction_wird_nicht_geloescht(self) -> None:
        ziel = self.spiel()
        link = self.wurzel / "junction"
        erg = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), ziel], capture_output=True, text=True)
        if erg.returncode != 0 or not link.exists():
            self.skipTest("Junction nicht anlegbar: %s" % (erg.stdout or erg.stderr)[-200:])
        ergebnis = self.datei("aus/e.exfat", b"e")
        self.assertEqual("verknuepfung", ql.pruefen(str(link), ergebnis, ql.stempel_nehmen(str(link))))
        self.assertTrue(os.path.exists(ziel))


class LoeschenTests(_Ablage):
    def test_datei(self) -> None:
        d = self.datei("alt.exfat")
        self.assertEqual("", ql.loeschen(d))
        self.assertFalse(os.path.lexists(d))

    def test_ordner(self) -> None:
        o = self.spiel()
        self.assertEqual("", ql.loeschen(o))
        self.assertFalse(os.path.lexists(o))

    def test_fehler_wird_zurueckgegeben_statt_geworfen(self) -> None:
        d = self.datei("alt.exfat")

        def kaputt(_p: str) -> None:
            raise PermissionError("Zugriff verweigert")
        self.assertIn("Zugriff verweigert", ql.loeschen(d, datei_loeschen=kaputt))
        self.assertTrue(os.path.exists(d))

    def test_bleibt_etwas_liegen_ist_es_ein_fehler(self) -> None:
        d = self.datei("alt.exfat")
        self.assertEqual("bleibt", ql.loeschen(d, datei_loeschen=lambda _p: None))

    def test_ordner_mit_eigenem_loescher(self) -> None:
        o = self.spiel()
        gerufen = []
        import shutil
        self.assertEqual("", ql.loeschen(o, ordner_loeschen=lambda p: (gerufen.append(p), shutil.rmtree(p))))
        self.assertEqual([o], gerufen)


if __name__ == "__main__":
    unittest.main()
