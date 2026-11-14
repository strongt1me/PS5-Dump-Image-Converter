# -*- coding: utf-8 -*-
"""Lesebaum (``spielbaum``): Dateien aus Ordner, ``.exfat`` und Ueberlagerung lesen, ohne zu entpacken (Stufe 3, Etappe 1).

Die Probe am echten Format: Ein Ordner wird mit dem Schreiber von MkPFS zu einer ``.exfat`` gebaut und mit dem Baum zurueckgelesen;
Liste, Groessen und Inhalt muessen dem Ordner entsprechen. Dazu: zwei Faeden lesen zugleich (jeder hat seinen eigenen Leser),
die Ueberlagerung, der Stempel und die Auswahl aus einer Liste gegen den Gang durch den Ordner.
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
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("spielbaum")

from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402
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
    "data/a.pak": _zufall(300_000, 3),                       # mehrere Cluster, ueber ein Stueck hinaus
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


def _inhalt(datei: sb.BaumDatei, stueck: int = sb.LESE_STUECK) -> bytes:
    return b"".join(datei.lesen(stueck))


class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="spielbaum_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ordner = os.path.join(self.tmp, "spiel")
        _schreiben(self.ordner, SPIEL)
        self.abbild = os.path.join(self.tmp, "spiel.exfat")
        with open(self.abbild, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.ordner)):
                fh.write(stueck)


class OrdnerBaumTests(_Grundlage):
    def test_liste_groesse_inhalt(self) -> None:
        with sb.OrdnerBaum(self.ordner) as baum:
            dateien = baum.dateien()
            self.assertEqual({d.rel: d.groesse for d in dateien}, {k: len(v) for k, v in SPIEL.items()})
            self.assertEqual([d.rel for d in dateien], sorted(SPIEL))
            for d in dateien:
                self.assertEqual(_inhalt(d, 4096), SPIEL[d.rel], d.rel)

    def test_verweise_zaehlen_nicht(self) -> None:
        ziel = os.path.join(self.ordner, "data", "a.pak")
        try:
            os.symlink(ziel, os.path.join(self.ordner, "verweis.pak"))
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks nicht erlaubt")
        baum = sb.OrdnerBaum(self.ordner)
        self.assertNotIn("verweis.pak", [d.rel for d in baum.dateien()])
        self.assertEqual(baum.uebersprungen, ["verweis.pak"])

    def test_kein_ordner(self) -> None:
        with self.assertRaises(sb.BaumFehler):
            sb.OrdnerBaum(os.path.join(self.tmp, "gibts_nicht"))

    def test_stempel_aendert_sich_mit_der_datei(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        vorher = baum.stempel()
        self.assertEqual(vorher, baum.stempel())
        with open(os.path.join(self.ordner, "eboot.bin"), "ab") as fh:
            fh.write(b"x")
        self.assertNotEqual(vorher, baum.stempel())

    def test_unveraendert_vor_der_ersten_auflistung(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        self.assertTrue(baum.unveraendert())                    # nichts gemerkt, nichts zu vergleichen

    def test_unveraendert_nach_dem_oeffnen(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        baum.dateien()
        self.assertTrue(baum.unveraendert())
        self.assertTrue(baum.unveraendert())                    # wiederholbar, aendert den gemerkten Stand nicht

    def test_geaenderte_datei(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        baum.dateien()
        with open(os.path.join(self.ordner, "eboot.bin"), "ab") as fh:
            fh.write(b"x")
        self.assertFalse(baum.unveraendert())

    def test_neue_und_fehlende_datei(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        baum.dateien()
        neu = os.path.join(self.ordner, "data", "neu.bin")
        with open(neu, "wb") as fh:
            fh.write(b"n")
        self.assertFalse(baum.unveraendert(), "eine dazugekommene Datei zaehlt als Aenderung")
        os.remove(neu)
        self.assertTrue(baum.unveraendert())
        os.remove(os.path.join(self.ordner, "eboot.bin"))
        self.assertFalse(baum.unveraendert(), "eine fehlende Datei zaehlt als Aenderung")

    def test_ordner_verschwunden(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        baum.dateien()
        shutil.rmtree(self.ordner)
        self.assertFalse(baum.unveraendert())


class LeereOrdnerUndFehlerTests(unittest.TestCase):
    """Leere Verzeichnisse und was ``os.walk`` still verschluckt hat (Befunde der Durchsicht, 13.11.2026)."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="spielbaum_leer_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.ordner = os.path.join(self.tmp, "spiel")
        _schreiben(self.ordner, SPIEL)
        for leer in ("savedata_leer", "data/cache", "data/cache/tief/leer"):
            os.makedirs(os.path.join(self.ordner, *leer.split("/")), exist_ok=True)

    ERWARTET = ["Daten", "data", "data/b", "data/cache", "data/cache/tief", "data/cache/tief/leer", "savedata_leer", "sce_sys"]

    def test_ordnerbaum_kennt_auch_die_leeren(self) -> None:
        with sb.OrdnerBaum(self.ordner) as baum:
            self.assertEqual(sorted(self.ERWARTET), baum.ordner())

    def test_exfatbaum_kennt_auch_die_leeren(self) -> None:
        abbild = os.path.join(self.tmp, "spiel.exfat")
        with open(abbild, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.ordner)):
                fh.write(stueck)
        with sb.ExfatBaum(abbild) as baum:
            self.assertEqual(sorted(self.ERWARTET), baum.ordner())

    def test_ignorierte_ordner_werden_nicht_betreten(self) -> None:
        _schreiben(self.ordner, {"skipme/x.bin": b"x", "skipme/tief/y.bin": b"y"})
        with sb.OrdnerBaum(self.ordner, ignoriert=lambda t: t == "skipme") as baum:
            self.assertNotIn("skipme", baum.ordner())
            self.assertFalse([d for d in baum.dateien() if d.rel.startswith("skipme")])

    def test_ueberlagerung_vereint_die_ordner(self) -> None:
        neu = os.path.join(self.tmp, "neu")
        os.makedirs(os.path.join(neu, "fakelib", "leer"))
        with sb.UeberlagerBaum(sb.OrdnerBaum(self.ordner), sb.OrdnerBaum(neu)) as baum:
            ordner = baum.ordner()
        self.assertIn("fakelib/leer", ordner)
        self.assertIn("savedata_leer", ordner)

    def test_ein_neuer_leerer_ordner_ist_eine_aenderung(self) -> None:
        baum = sb.OrdnerBaum(self.ordner)
        baum.dateien()
        self.assertTrue(baum.unveraendert())
        os.makedirs(os.path.join(self.ordner, "dazu"))
        self.assertFalse(baum.unveraendert())
        os.rmdir(os.path.join(self.ordner, "dazu"))
        self.assertTrue(baum.unveraendert())
        os.rmdir(os.path.join(self.ordner, "savedata_leer"))
        self.assertFalse(baum.unveraendert())

    def test_ein_nicht_lesbarer_ordner_ist_ein_fehler_kein_stilles_weglassen(self) -> None:
        """Bis zur Durchsicht ueberging ``os.walk`` ihn, die Dateien fehlten im Abbild, und die Rueckleseprobe vergass sie ebenso."""
        os.makedirs(os.path.join(self.ordner, "data", "geheim"))
        _schreiben(self.ordner, {"data/geheim/x.bin": b"x"})
        echt = os.scandir

        def scandir(pfad="."):
            if str(pfad).endswith("geheim"):
                raise PermissionError(13, "Zugriff verweigert", str(pfad))
            return echt(pfad)
        with mock.patch.object(os, "scandir", scandir):
            with self.assertRaises(sb.BaumFehler) as ctx:
                sb.OrdnerBaum(self.ordner).dateien()
        self.assertIn("geheim", str(ctx.exception))

    def test_ein_verweis_auf_einen_ordner_wird_gemerkt(self) -> None:
        """Ein Ordner-Symlink steht nicht in ``dirs`` und ``files`` zugleich: Er wurde nirgends gemeldet. Jetzt steht er in ``uebersprungen``."""
        os.makedirs(os.path.join(self.ordner, "verweisordner"))
        _schreiben(self.ordner, {"verweisordner/x.bin": b"x"})
        echt = os.path.islink
        with mock.patch("os.path.islink", side_effect=lambda p: os.fspath(p).endswith("verweisordner") or echt(p)):
            baum = sb.OrdnerBaum(self.ordner)
            baum.dateien()
        self.assertEqual(["verweisordner"], baum.uebersprungen)
        self.assertNotIn("verweisordner", baum.ordner())
        self.assertFalse([d for d in baum.dateien() if d.rel.startswith("verweisordner")])


class ExfatBaumTests(_Grundlage):
    def test_wie_der_ordner(self) -> None:
        ordner = sb.OrdnerBaum(self.ordner)
        with sb.ExfatBaum(self.abbild, ignoriert=is_ignored_name) as baum:
            self.assertEqual([(d.rel, d.groesse) for d in baum.dateien()],
                             [(d.rel, d.groesse) for d in ordner.dateien()])
            for d in baum.dateien():
                self.assertEqual(_inhalt(d), SPIEL[d.rel], d.rel)

    def test_kleine_stuecke(self) -> None:
        with sb.ExfatBaum(self.abbild) as baum:
            gross = baum.suchen()["data/a.pak"]
            stuecke = list(gross.lesen(10_000))
            self.assertTrue(all(len(s) <= 10_000 for s in stuecke))
            self.assertEqual(b"".join(stuecke), SPIEL["data/a.pak"])

    def test_zwei_faeden_zugleich(self) -> None:
        """Jeder Faden hat seinen eigenen Leser: gleichzeitiges Lesen verschiedener Dateien vermischt nichts."""
        fehler: list[str] = []
        with sb.ExfatBaum(self.abbild) as baum:
            dateien = baum.suchen()
            start = threading.Barrier(4)

            def arbeiten(namen: list[str]) -> None:
                try:
                    start.wait(timeout=10)
                    for _ in range(5):
                        for name in namen:
                            if _inhalt(dateien[name], 8192) != SPIEL[name]:
                                fehler.append(name)
                except Exception as exc:                        # noqa: BLE001
                    fehler.append("%s: %r" % (namen, exc))

            gruppen = [["data/a.pak", "eboot.bin"], ["Daten/Zebra.dat", "data/b/c.bin"],
                       ["data/a.pak", "sce_sys/icon0.png"], ["data/b/c.bin", "Daten/Zebra.dat"]]
            faeden = [threading.Thread(target=arbeiten, args=(g,)) for g in gruppen]
            for f in faeden:
                f.start()
            for f in faeden:
                f.join(timeout=60)
        self.assertEqual(fehler, [])

    def test_stempel_der_abbilddatei(self) -> None:
        with sb.ExfatBaum(self.abbild) as baum:
            self.assertTrue(baum.unveraendert())
            with open(self.abbild, "ab") as fh:
                fh.write(b"\0" * 512)
            self.assertFalse(baum.unveraendert())

    def test_nach_dem_schliessen_nicht_mehr_lesbar(self) -> None:
        baum = sb.ExfatBaum(self.abbild)
        datei = baum.suchen()["eboot.bin"]
        baum.schliessen()
        baum.schliessen()                                       # mehrfaches Schliessen schadet nicht
        with self.assertRaises(sb.BaumFehler):
            _inhalt(datei)

    def test_ein_beim_lesen_geschlossener_griff_ist_ein_baumfehler(self) -> None:
        """Ein Abbruch schliesst die Griffe, waehrend ein Lesefaden noch liest: ``ValueError`` ("seek of closed file") wird ein BaumFehler."""
        baum = sb.ExfatBaum(self.abbild)
        datei = baum.suchen()["data/a.pak"]
        erzeuger = datei.lesen(4096)
        next(erzeuger)                                          # der Griff dieses Fadens ist offen und liegt im Leser
        baum.schliessen()
        with self.assertRaises(sb.BaumFehler):
            list(erzeuger)

    def test_kein_exfat(self) -> None:
        kaputt = os.path.join(self.tmp, "kaputt.exfat")
        with open(kaputt, "wb") as fh:
            fh.write(b"\0" * 4096)
        with self.assertRaises(Exception):
            sb.ExfatBaum(kaputt).dateien()


class UeberlagerTests(_Grundlage):
    def test_ersetzen_ergaenzen_entfernen(self) -> None:
        neu = os.path.join(self.tmp, "neu")
        _schreiben(neu, {"eboot.bin": b"gepatcht", "fakelib/libSceAmpr.sprx": b"ampr"})
        with sb.UeberlagerBaum(sb.ExfatBaum(self.abbild), sb.OrdnerBaum(neu), entfernt=["readme.ini"]) as baum:
            dateien = baum.suchen()
            self.assertEqual(_inhalt(dateien["eboot.bin"]), b"gepatcht")
            self.assertEqual(dateien["eboot.bin"].groesse, len(b"gepatcht"))
            self.assertEqual(_inhalt(dateien["fakelib/libSceAmpr.sprx"]), b"ampr")
            self.assertNotIn("readme.ini", dateien)
            self.assertEqual(_inhalt(dateien["data/a.pak"]), SPIEL["data/a.pak"])      # unveraendert aus der Quelle
            erwartet = (set(SPIEL) - {"readme.ini"}) | {"fakelib/libSceAmpr.sprx"}            # +1 ergaenzt, -1 entfernt
            self.assertEqual(sorted(erwartet), sorted(dateien))
            self.assertEqual([d.rel for d in baum.dateien()], sorted(d.rel for d in baum.dateien()))
            self.assertEqual(len(dateien), len(SPIEL))                                  # +1 ergaenzt, -1 entfernt

    def test_entfernt_schlaegt_ueberlager(self) -> None:
        neu = os.path.join(self.tmp, "neu")
        _schreiben(neu, {"readme.ini": b"neu"})
        baum = sb.UeberlagerBaum(sb.OrdnerBaum(self.ordner), sb.OrdnerBaum(neu), entfernt=["readme.ini"])
        self.assertNotIn("readme.ini", baum.suchen())

    def test_stempel_enthaelt_beide(self) -> None:
        neu = os.path.join(self.tmp, "neu")
        _schreiben(neu, {"a.bin": b"1"})
        baum = sb.UeberlagerBaum(sb.OrdnerBaum(self.ordner), sb.OrdnerBaum(neu))
        vorher = baum.stempel()
        with open(os.path.join(neu, "a.bin"), "ab") as fh:
            fh.write(b"2")
        self.assertNotEqual(vorher, baum.stempel())


class BaumDateiTests(unittest.TestCase):
    def test_zu_kurz_und_zu_lang(self) -> None:
        kurz = sb.BaumDatei("x", 10, lambda _s: iter([b"abc"]))
        with self.assertRaises(sb.BaumFehler):
            list(kurz.lesen())
        lang = sb.BaumDatei("x", 2, lambda _s: iter([b"abc"]))
        with self.assertRaises(sb.BaumFehler):
            list(lang.lesen())
        genau = sb.BaumDatei("x", 6, lambda _s: iter([b"abc", b"def"]))
        self.assertEqual(b"".join(genau.lesen()), b"abcdef")


class AuswahlAusListeTests(_Grundlage):
    def _wie_ordner(self, regeln=None) -> None:
        aus_ordner = z.dateien_auswaehlen(self.ordner, regeln=regeln)
        with sb.ExfatBaum(self.abbild) as baum:
            aus_liste = z.auswahl_aus_liste(sb.einordnen(baum), regeln=regeln)
        self.assertEqual(aus_liste.gepackt, aus_ordner.gepackt)
        self.assertEqual(aus_liste.lose, aus_ordner.lose)
        self.assertEqual(aus_liste.leer, aus_ordner.leer)
        self.assertEqual(aus_liste.ungueltig, aus_ordner.ungueltig)
        self.assertEqual(aus_liste.nach_regeln_lose, aus_ordner.nach_regeln_lose)

    def test_ohne_regeln(self) -> None:
        self._wie_ordner()
        self.assertTrue(z.auswahl_aus_liste([("a/b.bin", 5), ("eboot.bin", 9), ("leer", 0)]).gepackt == [("a/b.bin", 5)])

    def test_mit_regeln(self) -> None:
        toml = os.path.join(self.tmp, "regeln.toml")
        with open(toml, "w", encoding="utf-8") as fh:
            fh.write('[pack]\ndefault_action = "compress"\n\n[[rule]]\naction = "loose"\ninclude = "data/b/**"\n')
        self._wie_ordner(z.regeln_laden(toml))

    def test_reihenfolge_wie_os_walk(self) -> None:
        liste = [("b/z.bin", 1), ("a.bin", 2), ("b/a/x.bin", 3), ("c.bin", 4), ("b/a.bin", 5), ("a/q.bin", 6)]
        erwartet = z.auswahl_aus_liste(liste).gepackt
        # os.walk: Wurzel zuerst (a.bin, c.bin), dann a/, dann b/ (a.bin, z.bin), dann b/a/
        self.assertEqual([p for p, _g in erwartet], ["a.bin", "c.bin", "a/q.bin", "b/a.bin", "b/z.bin", "b/a/x.bin"])

    def test_abbruch(self) -> None:
        with self.assertRaises(z.ZstdPackFehler):
            z.auswahl_aus_liste([("a.bin", 1)], abbruch=lambda: True)


if __name__ == "__main__":
    unittest.main()
