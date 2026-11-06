"""Tests fuer ``ps5_validator.utils.ampr_zstdpack``: zstd-Packs (AMPRZPK1 / AMPRZDT1) fuer ampr-emu-ng.

Das Format ist nach ``docs/zstd.md`` von ps5-dump-forge und dem Indexleser von ampr-emu-ng nachgebaut. Eine Pruefung
gegen die echte Laufzeit auf der Konsole gibt es nicht; die Tests halten deshalb den eigenen Leser an dieselben
Regeln wie der Leser von ampr-emu-ng (``Index::open`` / ``validate``) und lesen jeden Chunk Byte fuer Byte zurueck.
"""

from __future__ import annotations

import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ampr_zstdpack as z   # noqa: E402


def _zufall(n: int, startwert: int = 1) -> bytes:
    """Nicht verdichtbare, reproduzierbare Bytes."""
    import hashlib
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


def _spiel(wurzel: str) -> dict[str, bytes]:
    """Ein kleines Spiel; Rueckgabe: relativer Pfad -> Inhalt (alles, auch die losen Dateien)."""
    inhalt = {
        "eboot.bin": b"ELF" + bytes(1000),
        "sce_sys/param.json": b'{"titleId":"PPSA99999"}',
        "fakelib/libSceAmpr.sprx": b"x" * 100,
        "ampr_emu.index": b"AMPRIDX3" + bytes(50),
        "Media/text.txt": b"Hallo Welt\n" * 100_000,                   # verdichtbar, mehrere Chunks
        "Media/zufall.bin": _zufall(300_000),                          # unverdichtbar, zwei Chunks
        "data/genau.bin": b"A" * z.CHUNK_SIZE,                         # genau ein Chunk
        "data/plus_eins.bin": b"B" * (z.CHUNK_SIZE + 1),               # zwei Chunks, der zweite mit einem Byte
        "data/klein.cfg": b"a=1\n",
        "data/leer.bin": b"",
        "Daten/überraschung.txt": "Grüße ".encode("utf-8") * 5000,
    }
    for rel, daten in inhalt.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        with open(voll, "wb") as fh:
            fh.write(daten)
    return inhalt


class _Ordner(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="zstdpack_test_")
        self.addCleanup(shutil.rmtree, self._tmp, True)
        self.spiel = os.path.join(self._tmp, "spiel")
        self.packs = os.path.join(self._tmp, "packs")
        self.inhalt = _spiel(self.spiel)

    def packen(self, **kw):
        auswahl = z.dateien_auswaehlen(self.spiel)
        return auswahl, z.packen(self.spiel, self.packs, auswahl, **kw)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class FormatTests(unittest.TestCase):
    def test_pfadhash_bekannte_werte(self) -> None:
        self.assertEqual(14695981039346656037, z.pfadhash(b""))
        self.assertEqual(0xAF63DC4C8601EC8C, z.pfadhash(b"a"))       # FNV-1a 64
        self.assertNotEqual(z.pfadhash(b"Data/a"), z.pfadhash(b"data/a"), "die Schreibung zaehlt")

    def test_pfadregeln(self) -> None:
        for gut in ("a", "data/level1.bin", "Ordner/ü.txt"):
            self.assertTrue(z.pfad_gueltig(gut), gut)
        for schlecht in ("", "/a", "a\\b", "a//b", "./a", "a/../b", "a/.", "a\0b", "a/"):
            self.assertFalse(z.pfad_gueltig(schlecht), repr(schlecht))

    def test_namen(self) -> None:
        self.assertEqual("ampr_zstd-000.pak", z.bandname(0))
        self.assertEqual("ampr_zstd-1000.pak", z.bandname(1000))
        self.assertTrue(z.ist_packname("ampr_zstd.index"))
        self.assertTrue(z.ist_packname("ampr_zstd-007.pak"))
        self.assertFalse(z.ist_packname("ampr_zstd-7.pak"))
        self.assertFalse(z.ist_packname("ampr_assets-000.pak"))

    def test_was_lose_bleibt(self) -> None:
        lose = ["eboot.bin", "Sub/EBOOT.BIN", "a.elf", "x/y.PRX", "m.sprx", "SCE_SYS/x", "sce_module/y.prx",
                "fakelib2/a.bin", "ampr_emu.index", "fakelib/libSceAmpr.sprx", "ampr_zstd.index",
                "ampr_zstd-000.pak", "ampr_assets.index", "ampr_emu.log"]
        for rel in lose:
            self.assertTrue(z.bleibt_lose(rel), rel)
        gepackt = ["data/a.bin", "Media/v.mp4", "root.txt", "sce_sys_not/x", "Data/sce_sys/x", "readme.json"]
        for rel in gepackt:
            self.assertFalse(z.bleibt_lose(rel), rel)

    def test_stufe(self) -> None:
        self.assertEqual(7, z.stufe_lesen("7"))
        self.assertEqual(z.STUFE_VORGABE, z.stufe_lesen(0))
        self.assertEqual(z.STUFE_VORGABE, z.stufe_lesen(23))
        self.assertEqual(z.STUFE_VORGABE, z.stufe_lesen("abc"))
        self.assertEqual(22, z.stufe_lesen(22))


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class PackenTests(_Ordner):
    def test_auswahl(self) -> None:
        auswahl = z.dateien_auswaehlen(self.spiel)
        gepackt = {p for p, _g in auswahl.gepackt}
        self.assertEqual({"Media/text.txt", "Media/zufall.bin", "data/genau.bin", "data/plus_eins.bin",
                          "data/klein.cfg", "Daten/überraschung.txt"}, gepackt)
        self.assertIn("data/leer.bin", auswahl.leer)
        lose = {p for p, _g in auswahl.lose}
        for rel in ("eboot.bin", "sce_sys/param.json", "fakelib/libSceAmpr.sprx", "ampr_emu.index", "data/leer.bin"):
            self.assertIn(rel, lose)

    def test_rundreise_byte_fuer_byte(self) -> None:
        auswahl, erg = self.packen(stufe=3, arbeiter=2)
        self.assertEqual(len(auswahl.gepackt), erg.dateien)
        index = z.pruefen(self.packs, self.spiel)           # Chunk fuer Chunk gegen die Quelle
        self.assertEqual(len(auswahl.gepackt), len(index.dateien))
        ziel = os.path.join(self._tmp, "entpackt")
        z.entpacken(self.packs, ziel)
        for rel, _g in auswahl.gepackt:
            self.assertEqual(self.inhalt[rel], Path(ziel, *rel.split("/")).read_bytes(), rel)

    def test_dateien_sind_nach_hash_und_pfad_sortiert(self) -> None:
        self.packen()
        index = z.index_laden(self.packs)
        schluessel = [(d.hash, d.pfad.encode()) for d in index.dateien]
        self.assertEqual(sorted(schluessel), schluessel)
        self.assertEqual(len({s for s in schluessel}), len(schluessel))

    def test_chunkregeln(self) -> None:
        _auswahl, erg = self.packen(stufe=5)
        index = z.index_laden(self.packs)
        self.assertGreater(erg.zstd_chunks, 0)
        self.assertGreater(erg.roh_chunks, 0, "Zufallsdaten muessen roh bleiben")
        with open(os.path.join(self.packs, z.bandname(0)), "rb") as fh:
            for datei in index.dateien:
                for n in range(datei.chunk_zahl):
                    offset, band, gespeichert, codec = index.chunks[datei.erster_chunk + n]
                    entpackt = min(z.CHUNK_SIZE, datei.groesse - n * z.CHUNK_SIZE)
                    if codec == z.CODEC_ROH:
                        self.assertEqual(entpackt, gespeichert, datei.pfad)
                    else:
                        self.assertLess(gespeichert, entpackt, datei.pfad)
                        fh.seek(offset)
                        z.rahmen_pruefen(fh.read(gespeichert), entpackt)   # Inhaltsgroesse, Pruefsumme, Fenster

    def test_der_letzte_chunk_ist_kuerzer(self) -> None:
        self.packen()
        index = z.index_laden(self.packs)
        datei = next(d for d in index.dateien if d.pfad == "data/plus_eins.bin")
        self.assertEqual(2, datei.chunk_zahl)
        _o, _b, gespeichert, codec = index.chunks[datei.erster_chunk + 1]
        self.assertEqual(z.CODEC_ROH, codec, "ein Byte laesst sich nicht verkleinern")
        self.assertEqual(1, gespeichert)

    def test_ergebnis_unabhaengig_von_der_fadenzahl(self) -> None:
        self.packen(arbeiter=1)
        eins = Path(self.packs, z.bandname(0)).read_bytes()[z.VOLUME_HEADER_SIZE:]
        shutil.rmtree(self.packs)
        self.packen(arbeiter=5)
        fuenf = Path(self.packs, z.bandname(0)).read_bytes()[z.VOLUME_HEADER_SIZE:]
        self.assertEqual(eins, fuenf)

    def test_mehrere_baender(self) -> None:
        with mock.patch.object(z, "VOLUME_LIMIT", 270_000):
            _auswahl, erg = self.packen(stufe=1)
            self.assertGreaterEqual(len(erg.baender), 2)
            index = z.pruefen(self.packs, self.spiel)
            self.assertEqual(len(erg.baender), len(index.baender))
            for g in index.baender:
                self.assertLessEqual(g, 270_000)
            for nummer in range(len(index.baender)):
                kopf = Path(self.packs, z.bandname(nummer)).read_bytes()[:z.VOLUME_HEADER_SIZE]
                z.bandkopf_pruefen(kopf, nummer, index)
            ziel = os.path.join(self._tmp, "entpackt")
            z.entpacken(self.packs, ziel)
            self.assertEqual(self.inhalt["Media/zufall.bin"], Path(ziel, "Media", "zufall.bin").read_bytes())

    def test_abbruch(self) -> None:
        auswahl = z.dateien_auswaehlen(self.spiel)
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.packen(self.spiel, self.packs, auswahl, abbruch=lambda: True)
        self.assertEqual("ampr_pack.abgebrochen", str(ctx.exception))

    def test_nichts_zu_packen(self) -> None:
        with self.assertRaises(z.ZstdPackFehler):
            z.packen(self.spiel, self.packs, z.Auswahl())

    def test_belegte_ausgabe_wird_abgelehnt(self) -> None:
        self.packen()
        with self.assertRaises(z.ZstdPackFehler):
            self.packen()


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class BeschaedigungTests(_Ordner):
    def setUp(self) -> None:
        super().setUp()
        self.packen(stufe=3)
        self.band = os.path.join(self.packs, z.bandname(0))
        self.index = os.path.join(self.packs, z.INDEX_NAME)

    def _aendern(self, pfad: str, stelle: int) -> None:
        daten = bytearray(Path(pfad).read_bytes())
        daten[stelle] ^= 0xFF
        Path(pfad).write_bytes(bytes(daten))

    def test_gegenprobe_unbeschaedigt_besteht(self) -> None:
        z.pruefen(self.packs, self.spiel)

    def test_ein_verdorbenes_byte_im_band(self) -> None:
        self._aendern(self.band, z.VOLUME_HEADER_SIZE + 100)
        with self.assertRaises(z.ZstdPackFehler):
            z.pruefen(self.packs, self.spiel)

    def test_ein_verdorbenes_byte_im_index(self) -> None:
        self._aendern(self.index, z.INDEX_HEADER_SIZE + 5)
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.pruefen(self.packs, self.spiel)
        self.assertIn("index_pruefsumme", str(ctx.exception))

    def test_ein_verdorbenes_byte_im_indexkopf(self) -> None:
        self._aendern(self.index, 30)
        with self.assertRaises(z.ZstdPackFehler):
            z.index_laden(self.packs)

    def test_abgeschnittenes_band(self) -> None:
        daten = Path(self.band).read_bytes()
        Path(self.band).write_bytes(daten[:-10])
        with self.assertRaises(z.ZstdPackFehler):
            z.pruefen(self.packs, self.spiel)

    def test_fehlendes_band(self) -> None:
        os.remove(self.band)
        with self.assertRaises(z.ZstdPackFehler):
            z.pruefen(self.packs, self.spiel)

    def test_bandkopf_eines_anderen_archivs(self) -> None:
        self._aendern(self.band, 24)                    # archive_id
        with self.assertRaises(z.ZstdPackFehler):
            z.pruefen(self.packs, self.spiel)

    def test_geaenderte_quelle_wird_bemerkt(self) -> None:
        Path(self.spiel, "data", "klein.cfg").write_bytes(b"b=2\n")        # gleiche Laenge, anderer Inhalt
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.pruefen(self.packs, self.spiel)
        self.assertIn("inhalt_anders", str(ctx.exception))

    def test_unsortierter_index_wird_abgelehnt(self) -> None:
        """Zwei Dateisaetze vertauscht (CRCs neu gerechnet): Der Leser von ampr-emu-ng wuerde ablehnen."""
        daten = bytearray(Path(self.index).read_bytes())
        a = z.INDEX_HEADER_SIZE
        b = a + z.FILE_RECORD_SIZE
        daten[a:a + 32], daten[b:b + 32] = daten[b:b + 32], daten[a:a + 32]
        struct.pack_into("<I", daten, 112, z._crc(bytes(daten[128:])))
        struct.pack_into("<I", daten, 116, z._crc(bytes(daten[:112]) + b"\0" * 8 + bytes(daten[120:128])))
        with self.assertRaises(z.ZstdPackFehler) as ctx:
            z.index_lesen(bytes(daten))
        self.assertIn("index_ungueltig", str(ctx.exception))


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class SpielordnerTests(_Ordner):
    def test_uebernehmen_und_erkennen(self) -> None:
        self.assertFalse(z.ist_gepackt(self.spiel))
        auswahl, _erg = self.packen()
        index = z.pruefen(self.packs, self.spiel)
        z.uebernehmen(self.packs, self.spiel, index)
        self.assertTrue(z.ist_gepackt(self.spiel))
        self.assertEqual([], [n for n in os.listdir(self.packs)])
        z.pruefen(self.spiel, self.spiel)                       # der Satz im Spielordner stimmt mit den Originalen

    def test_originale_entfernen_und_zurueckholen(self) -> None:
        auswahl, _erg = self.packen()
        index = z.pruefen(self.packs, self.spiel)
        z.uebernehmen(self.packs, self.spiel, index)
        ergebnis = z.originale_entfernen(self.spiel, index)
        self.assertEqual(len(auswahl.gepackt), ergebnis["files"])
        self.assertFalse(os.path.exists(os.path.join(self.spiel, "Media")), "leere Ordner verschwinden")
        for rel in ("eboot.bin", "sce_sys/param.json", "fakelib/libSceAmpr.sprx", "ampr_emu.index", "data/leer.bin"):
            self.assertTrue(os.path.isfile(os.path.join(self.spiel, *rel.split("/"))), rel)
        z.entpacken(self.spiel, self.spiel)
        z.packdateien_entfernen(self.spiel)
        self.assertFalse(z.ist_gepackt(self.spiel))
        for rel, daten in self.inhalt.items():
            self.assertEqual(daten, Path(self.spiel, *rel.split("/")).read_bytes(), rel)

    def test_systemdatei_im_index_wird_nie_entfernt(self) -> None:
        """Gegenprobe zu ``originale_entfernen``: Taucht eine Systemdatei im Index auf, bricht es ab."""
        auswahl = z.Auswahl(gepackt=[("eboot.bin", 1003)])
        z.packen(self.spiel, self.packs, auswahl)
        index = z.index_laden(self.packs)
        with self.assertRaises(z.ZstdPackFehler):
            z.originale_entfernen(self.spiel, index)
        self.assertTrue(os.path.isfile(os.path.join(self.spiel, "eboot.bin")))


class RegelTests(_Ordner):
    """Eigene Packregeln (TOML) wie bei Forge: letzte treffende Regel gewinnt, Systemdateien bleiben immer lose."""

    def _regeln(self, text: str) -> "z.Regeln":
        pfad = os.path.join(self._tmp, "regeln.toml")
        Path(pfad).write_text(text, encoding="utf-8")
        return z.regeln_laden(pfad)

    def test_vorgabe_ist_lose_und_die_letzte_regel_gewinnt(self) -> None:
        r = self._regeln('[[rule]]\naction="compress"\ninclude="Media/*"\n[[rule]]\naction="loose"\ninclude="Media/*"\nexclude="*.txt"\n')
        self.assertEqual("loose", r.standard)
        self.assertEqual("compress", r.aktion("Media/text.txt"))
        self.assertEqual("loose", r.aktion("Media/zufall.bin"))
        self.assertEqual("loose", r.aktion("sonstwo.bin"), "keine Regel trifft: Vorgabe")

    def test_gross_klein_zaehlt_und_stern_kreuzt_den_schraegstrich(self) -> None:
        r = self._regeln('[pack]\ndefault_action="loose"\n[[rule]]\ninclude="Daten/*"\n')
        self.assertEqual("compress", r.aktion("Daten/a/b/c.bin"))
        self.assertEqual("loose", r.aktion("daten/a.bin"))

    def test_store_packt_wie_compress_und_unbekannte_schluessel_werden_gemeldet(self) -> None:
        r = self._regeln('[pack]\nworkers=4\ndefault_action="store"\n[groups]\nx=1\n[[rule]]\ninclude=["a","b"]\nhot=true\n')
        self.assertEqual("store", r.standard)
        self.assertEqual({"pack.workers", "rule.hot", "groups"}, set(r.ignoriert))

    def test_fehler_werden_abgelehnt(self) -> None:
        for text in ("kein [toml", '[pack]\ndefault_action="packen"\n', '[[rule]]\naction="zip"\n',
                     '[[rule]]\ninclude=[]\n', '[[rule]]\ninclude_from="x.txt"\n', '[[rule]]\ninclude=3\n'):
            with self.assertRaises(z.ZstdPackFehler, msg=text):
                self._regeln(text)
        with self.assertRaises(z.ZstdPackFehler):
            z.regeln_laden(os.path.join(self._tmp, "gibt_es_nicht.toml"))

    # --- include_from / exclude_from (Forge v0.5.4) -------------------------------------------------------------
    def _muster(self, name: str, text: str) -> None:
        pfad = os.path.join(self._tmp, *name.split("/"))
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        Path(pfad).write_text(text, encoding="utf-8")

    def test_musterdatei_wird_an_include_und_exclude_gehaengt(self) -> None:
        self._muster("liste.txt", "# Kommentar\n\n  Media/a.bin  \nMedia/*.ogg\n")
        self._muster("weg.txt", "Media/laut.ogg\n")
        r = self._regeln('[pack]\ndefault_action="loose"\n[[rule]]\ninclude_from="liste.txt"\nexclude_from=["weg.txt"]\n')
        self.assertEqual("compress", r.aktion("Media/a.bin"), "genauer Pfad aus der Datei, Leerraum getrimmt")
        self.assertEqual("compress", r.aktion("Media/x.ogg"), "Glob aus der Datei")
        self.assertEqual("loose", r.aktion("Media/laut.ogg"), "exclude_from nimmt die Datei wieder heraus")
        self.assertEqual("loose", r.aktion("Anderes/b.bin"), "ohne include gibt es keine Vorgabe **, wenn die Datei Muster hat")
        self.assertEqual([], r.ignoriert, "include_from und exclude_from sind bekannte Schluessel")

    def test_include_und_include_from_ergaenzen_sich(self) -> None:
        self._muster("mehr.txt", "Daten/b.bin\n")
        r = self._regeln('[[rule]]\ninclude=["Daten/a.bin"]\ninclude_from="mehr.txt"\n')
        self.assertEqual("compress", r.aktion("Daten/a.bin"))
        self.assertEqual("compress", r.aktion("Daten/b.bin"))
        self.assertEqual("loose", r.aktion("Daten/c.bin"))

    def test_leere_musterdatei_laesst_die_vorgabe_stern_stehen(self) -> None:
        self._muster("leer.txt", "# nur ein Kommentar\n\n")
        r = self._regeln('[[rule]]\ninclude_from="leer.txt"\n')
        self.assertEqual("compress", r.aktion("irgendwas/datei.bin"))

    def test_include_leer_mit_leerer_musterdatei_ist_ein_fehler(self) -> None:
        self._muster("leer.txt", "\n")
        with self.assertRaises(z.ZstdPackFehler):
            self._regeln('[[rule]]\ninclude=[]\ninclude_from="leer.txt"\n')

    def test_unterordner_ist_erlaubt(self) -> None:
        self._muster("listen/eins.txt", "Media/a.bin\n")
        r = self._regeln('[[rule]]\ninclude_from="listen/eins.txt"\n')
        self.assertEqual("compress", r.aktion("Media/a.bin"))

    def test_unzulaessige_namen_werden_abgelehnt(self) -> None:
        self._muster("ok.txt", "a\n")
        for name in ("../ok.txt", "./ok.txt", "/ok.txt", "C:/ok.txt", "a\\\\ok.txt", "x//ok.txt", "", "fehlt.txt", "listen"):
            with self.subTest(name=name):
                os.makedirs(os.path.join(self._tmp, "listen"), exist_ok=True)
                with self.assertRaises(z.ZstdPackFehler):
                    self._regeln('[[rule]]\ninclude_from=%r\n' % name)

    def test_musterdatei_ueber_der_groessengrenze_und_kein_utf8(self) -> None:
        self._muster("gross.txt", "a\n" * (z.MUSTERDATEI_MAX_BYTES // 2 + 1))
        with self.assertRaises(z.ZstdPackFehler):
            self._regeln('[[rule]]\ninclude_from="gross.txt"\n')
        Path(self._tmp, "kaputt.txt").write_bytes(b"\xff\xfe\x00\x80")
        with self.assertRaises(z.ZstdPackFehler):
            self._regeln('[[rule]]\ninclude_from="kaputt.txt"\n')

    def test_zu_viele_globs_werden_abgelehnt_und_genaue_pfade_gehen_schnell(self) -> None:
        self._muster("globs.txt", "".join("d%d/*.bin\n" % i for i in range(z.MUSTER_MAX_GLOBS + 1)))
        with self.assertRaises(z.ZstdPackFehler):
            self._regeln('[[rule]]\ninclude_from="globs.txt"\n')
        self._muster("viele.txt", "".join("m/%d\n" % i for i in range(50_000)))
        r = self._regeln('[[rule]]\ninclude_from="viele.txt"\n')
        import time
        t0 = time.time()
        for i in range(2000):
            r.aktion("m/%d" % (i * 7))
        self.assertLess(time.time() - t0, 2.0, "genaue Pfade werden in einer Menge gesucht, nicht je Muster")
        self.assertEqual("compress", r.aktion("m/49999"))
        self.assertEqual("loose", r.aktion("m/50000"))

    @unittest.skipUnless(hasattr(os, "symlink"), "keine Verknuepfungen")
    def test_verknuepfung_als_musterdatei_wird_abgelehnt(self) -> None:
        ziel = os.path.join(self._tmp, "echt.txt")
        Path(ziel).write_text("a\n", encoding="utf-8")
        try:
            os.symlink(ziel, os.path.join(self._tmp, "link.txt"))
        except (OSError, NotImplementedError):
            self.skipTest("Verknuepfung nicht anlegbar (Rechte)")
        with self.assertRaises(z.ZstdPackFehler):
            self._regeln('[[rule]]\ninclude_from="link.txt"\n')

    def test_zu_grosse_datei(self) -> None:
        pfad = os.path.join(self._tmp, "gross.toml")
        Path(pfad).write_text("#" * (z.PROFIL_MAX_BYTES + 1), encoding="utf-8")
        with self.assertRaises(z.ZstdPackFehler):
            z.regeln_laden(pfad)

    def test_die_auswahl_meldet_den_durchgang_vorher(self) -> None:
        gemeldet: list[str] = []
        z.dateien_auswaehlen(self.spiel, melden=gemeldet.append)
        self.assertEqual([os.path.abspath(self.spiel)], gemeldet)

    def test_auswahl_mit_regeln_laesst_systemdateien_trotzdem_lose(self) -> None:
        r = self._regeln('[pack]\ndefault_action="compress"\n[[rule]]\naction="loose"\ninclude="Media/*"\n')
        a = z.dateien_auswaehlen(self.spiel, regeln=r)
        gepackt = {p for p, _g in a.gepackt}
        self.assertNotIn("Media/text.txt", gepackt)
        self.assertIn("data/genau.bin", gepackt)
        self.assertNotIn("eboot.bin", gepackt)
        self.assertEqual(2, a.nach_regeln_lose)
        # Eine Regel, die alles packen will, packt trotzdem keine Systemdatei.
        alles = self._regeln('[[rule]]\ninclude="**"\n')
        gepackt2 = {p for p, _g in z.dateien_auswaehlen(self.spiel, regeln=alles).gepackt}
        self.assertNotIn("eboot.bin", gepackt2)
        self.assertNotIn("fakelib/libSceAmpr.sprx", gepackt2)
        self.assertNotIn("data/leer.bin", gepackt2)

    def test_ohne_regeln_bleibt_alles_wie_bisher(self) -> None:
        self.assertEqual(z.dateien_auswaehlen(self.spiel).gepackt, z.dateien_auswaehlen(self.spiel, regeln=None).gepackt)


@unittest.skipUnless(z.verfuegbar(), "zstandard fehlt")
class WerkzeugTests(_Ordner):
    """Die Funktionen hinter dem Asset-Pack-Werkzeug (Pruefen, Entpacken in den Ordner oder eine Kopie)."""

    def setUp(self) -> None:
        super().setUp()
        self.auswahl, _erg = self.packen()
        index = z.pruefen(self.packs, self.spiel)
        z.uebernehmen(self.packs, self.spiel, index)
        z.originale_entfernen(self.spiel, index)

    def test_befund(self) -> None:
        b = z.befund(self.spiel)
        self.assertEqual(len(self.auswahl.gepackt), b["dateien"])
        self.assertEqual(self.auswahl.gepackte_bytes, b["logisch"])
        self.assertEqual(0, b["fehlende_baender"])
        os.remove(os.path.join(self.spiel, z.bandname(0)))
        b = z.befund(self.spiel)
        self.assertEqual(1, b["fehlende_baender"])
        self.assertEqual(z.bandname(0), b["erste_fehlende"])

    def test_platzbedarf(self) -> None:
        im_ordner = z.platzbedarf(self.spiel, True)
        self.assertEqual(self.auswahl.gepackte_bytes, im_ordner)
        self.assertGreater(z.platzbedarf(self.spiel, False), im_ordner)

    def test_in_neuen_ordner(self) -> None:
        ziel = os.path.join(self._tmp, "kopie")
        erg = z.entpacken_in_neuen_ordner(self.spiel, ziel)
        self.assertEqual(len(self.auswahl.gepackt), erg["files"])
        for rel, daten in self.inhalt.items():
            self.assertEqual(daten, Path(ziel, *rel.split("/")).read_bytes(), rel)
        self.assertFalse(any(z.ist_packname(n) for n in os.listdir(ziel)), "keine Packdateien in der Kopie")
        self.assertTrue(z.ist_gepackt(self.spiel), "das Original bleibt gepackt")

    def test_ziel_muss_neu_oder_leer_sein(self) -> None:
        voll = os.path.join(self._tmp, "voll")
        os.makedirs(voll)
        Path(voll, "x").write_bytes(b"1")
        with self.assertRaises(z.ZstdPackFehler):
            z.entpacken_in_neuen_ordner(self.spiel, voll)
        with self.assertRaises(z.ZstdPackFehler):
            z.entpacken_in_neuen_ordner(self.spiel, os.path.join(self.spiel, "innen"))

    def test_im_ordner(self) -> None:
        erg = z.entpacken_in_ordner(self.spiel)
        self.assertEqual(len(self.auswahl.gepackt), erg["files"])
        self.assertFalse(z.ist_gepackt(self.spiel))
        for rel, daten in self.inhalt.items():
            self.assertEqual(daten, Path(self.spiel, *rel.split("/")).read_bytes(), rel)


if __name__ == "__main__":
    unittest.main()
