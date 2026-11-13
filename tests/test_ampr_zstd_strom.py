# -*- coding: utf-8 -*-
"""zstd-Packs aus einem Lesebaum ohne Zwischenordner: Messdurchgang und Schreibdurchgang (Stufe 3, Etappe 2).

Massstab ist das bisherige ``packen`` aus einem Ordner: Mit derselben Archiv-ID muss der Strom byteweise dieselben Baender und
denselben Index liefern, auch aus einer ``.exfat`` und bei beliebig geschnittenen Lesestuecken. Dazu die Fehlerfaelle: Aenderung der
Quelle zwischen den Durchgaengen, zu kurze Dateien, Abbruch.
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
pruefumgebung.umlenken("zstd_strom")

from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402

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
    "Media/text.txt": b"Hallo Welt\n" * 100_000,                  # verdichtbar, mehrere Chunks
    "Media/zufall.bin": _zufall(300_000),                         # unverdichtbar
    "data/genau.bin": b"A" * z.CHUNK_SIZE,
    "data/plus_eins.bin": b"B" * (z.CHUNK_SIZE + 1),
    "data/klein.cfg": b"a=1\n",
    "data/leer.bin": b"",
    "data/gross.bin": _zufall(2_200_000, 7),                      # ueber ein Stueck hinaus
}


def _schreiben(wurzel: str, inhalte: dict[str, bytes]) -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)


def _gelesen(ordner: str) -> dict[str, bytes]:
    return {n: Path(ordner, n).read_bytes() for n in sorted(os.listdir(ordner))}


def _in_stuecken(baum: sb.OrdnerBaum, laenge: int) -> sb.OrdnerBaum:
    """Ein Baum, dessen Dateien in unregelmaessig kleinen Stuecken kommen (wie von einem fragmentierten exFAT-Abbild)."""
    neu = []
    for d in baum.dateien():
        def leser(_stueck: int, d=d) -> "iter":
            daten = b"".join(d.lesen())
            pos, schritt = 0, laenge
            while pos < len(daten):
                yield daten[pos:pos + schritt]
                pos += schritt
                schritt = laenge + (pos % 7)                    # nie gleich gross, nie an Chunkgrenzen ausgerichtet
        neu.append(sb.BaumDatei(d.rel, d.groesse, leser))
    baum._dateien = neu
    return baum


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="zstdstrom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.spiel = os.path.join(self.tmp, "spiel")
        _schreiben(self.spiel, SPIEL)
        self.auswahl = z.dateien_auswaehlen(self.spiel)
        self.archiv = z.archiv_id_ableiten(self.auswahl, 3)

    def vergleichspack(self, **kw) -> dict[str, bytes]:
        ziel = os.path.join(self.tmp, "ordnerpack")
        z.packen(self.spiel, ziel, self.auswahl, stufe=3, arbeiter=2, archiv_id=self.archiv, **kw)
        return _gelesen(ziel)

    def strom_ordner(self, baum, name: str = "strompack", arbeiter: int = 3):
        messung = z.messen(baum, self.auswahl, stufe=3, arbeiter=arbeiter, archiv_id=self.archiv)
        ziel = os.path.join(self.tmp, name)
        z.strom_in_ordner(baum, self.auswahl, messung, ziel, arbeiter=arbeiter)
        return messung, ziel


class ByteGleichheitTests(_Grundlage):
    def test_ordnerbaum_wie_packen(self) -> None:
        messung, ziel = self.strom_ordner(sb.OrdnerBaum(self.spiel))
        self.assertEqual(self.vergleichspack(), _gelesen(ziel))
        self.assertEqual(messung.ergebnis.chunks, len(messung.chunkwoerter))

    def test_mehrere_baender(self) -> None:
        with mock.patch.object(z, "VOLUME_LIMIT", 400_000):
            messung, ziel = self.strom_ordner(sb.OrdnerBaum(self.spiel))
            self.assertGreaterEqual(len(messung.baender), 3)
            self.assertEqual(self.vergleichspack(), _gelesen(ziel))
            for name, groesse in messung.dateien():
                self.assertEqual(os.path.getsize(os.path.join(ziel, name)), groesse, name)

    def test_aus_exfat(self) -> None:
        abbild = os.path.join(self.tmp, "spiel.exfat")
        with open(abbild, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        with sb.ExfatBaum(abbild) as baum:
            _messung, ziel = self.strom_ordner(baum)
        self.assertEqual(self.vergleichspack(), _gelesen(ziel))

    def test_beliebig_geschnittene_stuecke(self) -> None:
        baum = _in_stuecken(sb.OrdnerBaum(self.spiel), 70_001)
        _messung, ziel = self.strom_ordner(baum)
        self.assertEqual(self.vergleichspack(), _gelesen(ziel))

    def test_faeden_aendern_nichts(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        _m1, eins = self.strom_ordner(baum, "eins", arbeiter=1)
        _m8, acht = self.strom_ordner(baum, "acht", arbeiter=8)
        self.assertEqual(_gelesen(eins), _gelesen(acht))

    def test_vom_eigenen_leser_pruefbar(self) -> None:
        """Der Strom ist ein gueltiges Pack: ``pruefen`` liest jeden Chunk zurueck und vergleicht mit der Quelle."""
        messung, ziel = self.strom_ordner(sb.OrdnerBaum(self.spiel))
        index = z.pruefen(ziel, self.spiel)
        self.assertEqual(len(messung.baender), len(index.baender))
        self.assertEqual(len(index.dateien), len(messung.eintraege))

    def test_stromstuecke_haben_die_gemessene_laenge(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        laengen: dict[str, int] = {}
        reihenfolge: list[str] = []
        for name, daten in z.strom(baum, self.auswahl, messung):
            laengen[name] = laengen.get(name, 0) + len(daten)
            if not reihenfolge or reihenfolge[-1] != name:
                reihenfolge.append(name)
        self.assertEqual(list(messung.dateien()), [(n, laengen[n]) for n in reihenfolge])


class ArchivIdTests(_Grundlage):
    def test_nur_von_liste_und_stufe_abhaengig(self) -> None:
        self.assertEqual(self.archiv, z.archiv_id_ableiten(z.dateien_auswaehlen(self.spiel), 3))
        self.assertNotEqual(self.archiv, z.archiv_id_ableiten(self.auswahl, 5))
        self.assertEqual(16, len(self.archiv))
        weniger = z.Auswahl(gepackt=self.auswahl.gepackt[1:])
        self.assertNotEqual(self.archiv, z.archiv_id_ableiten(weniger, 3))

    def test_ohne_angabe_zufaellig(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        a = z.messen(baum, self.auswahl, stufe=1).archiv_id
        b = z.messen(baum, self.auswahl, stufe=1).archiv_id
        self.assertNotEqual(a, b)

    def test_reproduzierbar(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        eins = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        zwei = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv, arbeiter=1)
        self.assertEqual(eins.index, zwei.index)
        self.assertEqual(eins.baender, zwei.baender)


class FehlerTests(_Grundlage):
    def test_quelle_zwischen_den_durchgaengen_geaendert(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        voll = os.path.join(self.spiel, "Media", "zufall.bin")
        daten = bytearray(Path(voll).read_bytes())
        daten[150_000] ^= 0xFF                                  # gleiche Groesse, anderer Inhalt
        Path(voll).write_bytes(bytes(daten))
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            list(z.strom(baum, self.auswahl, messung))
        self.assertIn("weicht vom Messdurchgang ab", str(ctx.exception))

    def test_datei_zwischen_den_durchgaengen_gewachsen(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        voll = os.path.join(self.spiel, "data", "klein.cfg")
        Path(voll).write_bytes(b"a=1\nb=2\n")
        baum2 = sb.OrdnerBaum(self.spiel)
        with self.assertRaises(z.ZstdPackFehler):
            list(z.strom(baum2, self.auswahl, messung))

    def test_datei_waehrend_des_messens_geaendert(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        baum.dateien()
        Path(self.spiel, "data", "klein.cfg").write_bytes(b"deutlich laenger als vorher\n")
        with self.assertRaises(z.ZstdPackFehler):
            z.messen(baum, self.auswahl, stufe=3)

    def test_datei_fehlt_in_der_quelle(self) -> None:
        baum = sb.UeberlagerBaum(sb.OrdnerBaum(self.spiel), entfernt=["data/klein.cfg"])
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.messen(baum, self.auswahl, stufe=3)
        self.assertIn("fehlt in der Quelle", str(ctx.exception))

    def test_zu_kurze_datei_im_baum(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        echt = {d.rel: d for d in baum.dateien()}
        zu_kurz = sb.BaumDatei("data/gross.bin", echt["data/gross.bin"].groesse, lambda _s: iter([b"x" * 100]))
        baum._dateien = [zu_kurz if d.rel == "data/gross.bin" else d for d in baum.dateien()]
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.messen(baum, self.auswahl, stufe=3)
        self.assertIn("kuerzer", str(ctx.exception))

    def test_abbruch(self) -> None:
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.messen(sb.OrdnerBaum(self.spiel), self.auswahl, abbruch=lambda: True)
        self.assertEqual("ampr_pack.abgebrochen", str(ctx.exception))

    def test_abbruch_im_schreibdurchgang_laesst_keine_faeden(self) -> None:
        import threading
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        vorher = threading.active_count()
        zaehler = [0]

        def abbruch() -> bool:
            zaehler[0] += 1
            return zaehler[0] > 2

        with self.assertRaises(z.ZstdPackFehler):
            for _ in z.strom(baum, self.auswahl, messung, abbruch=abbruch):
                pass
        self.assertLessEqual(threading.active_count(), vorher + 1)

    def test_nichts_zu_packen(self) -> None:
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.messen(sb.OrdnerBaum(self.spiel), z.Auswahl())
        self.assertEqual("ampr_zstd.nichts_zu_packen", str(ctx.exception))

    def test_dateiliste_weicht_ab(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung = z.messen(baum, self.auswahl, stufe=3, archiv_id=self.archiv)
        weniger = z.Auswahl(gepackt=self.auswahl.gepackt[1:])
        with self.assertRaises(z.ZstdPackFehler):
            list(z.strom(baum, weniger, messung))

    def test_ausgabe_belegt(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        messung, ziel = self.strom_ordner(baum)
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.strom_in_ordner(baum, self.auswahl, messung, ziel)
        self.assertEqual("ampr_zstd.ausgabe_belegt", str(ctx.exception))


class FortschrittTests(_Grundlage):
    def test_fortschritt_waechst_bis_eins(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        werte: list[float] = []
        messung = z.messen(baum, self.auswahl, stufe=1, fortschritt=werte.append)
        self.assertEqual(werte, sorted(werte))
        self.assertAlmostEqual(1.0, werte[-1])
        werte2: list[float] = []
        for _ in z.strom(baum, self.auswahl, messung, fortschritt=werte2.append):
            pass
        self.assertAlmostEqual(1.0, werte2[-1])


if __name__ == "__main__":
    unittest.main()
