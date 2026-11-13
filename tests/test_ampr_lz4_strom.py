# -*- coding: utf-8 -*-
"""LZ4-Asset-Packs aus einem Lesebaum ohne Zwischenordner (Stufe 3, Etappe 14, Vorbild: Dump Forge).

Massstab ist das Packwerkzeug des Herstellers (``AMPR_PackTools-4.0/ampr_pack.py``): Bei **einer** Spur je Gruppe muss der Strom
byteweise dieselben Baender, dasselbe Manifest, dieselbe Pruefsummenbeilage und dasselbe Laufzeitprofil liefern wie das Werkzeug
aus einem Ordner - auch bei mehreren Baendern und bei beliebig geschnittenen Lesestuecken. Dazu ``verify --root`` des Werkzeugs
gegen die Quelle, die Fehlerfaelle (Quelle aendert sich zwischen den Durchgaengen, Abbruch, Speicherblock) und die Faelle, die der Strom
dem Weg ueber den Ordner ueberlaesst (Anwenderprofil, mehrere Gruppen, Striping).

Dann das Profil aus dem Lesebaum (``ampr_assetpakete.profil_schreiben_aus_baum``, gegen ``profil_schreiben`` aus dem Ordner) und der ganze
Weg im Hauptprogramm-Objekt (``_mode_exfat_umpacken_strom`` mit LZ4), wie ``test_exfat_strom_weg`` es fuer zstd macht.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("lz4_strom")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from mkpfs.exfat_writer import iter_exfat_image              # noqa: E402

from ps5_validator.utils import abbild_strom                 # noqa: E402
from ps5_validator.utils import ampr_assetpakete as ap       # noqa: E402
from ps5_validator.utils import ampr_lz4pack as l4           # noqa: E402
from ps5_validator.utils import spielbaum as sb              # noqa: E402
from ps5_validator.utils.param_manifest import create_default_param   # noqa: E402

GUI = APP.PS5ConverterGUI
NG_LIB = b"MZ-ampr-emu-ng-" + bytes(range(256)) * 8


def _zufall(n: int, startwert: int = 1) -> bytes:
    aus = bytearray()
    zaehler = startwert
    while len(aus) < n:
        aus += hashlib.sha256(str(zaehler).encode()).digest()
        zaehler += 1
    return bytes(aus[:n])


def _sfo(title_id: str) -> bytes:
    """Eine kleine ``param.sfo`` mit nur ``TITLE_ID`` (Aufbau wie ``ampr_assetpakete.title_id_aus_sfo_bytes`` ihn liest)."""
    schluessel = b"TITLE_ID\0"
    daten = title_id.encode("ascii") + b"\0"
    key_off = 0x14 + 16
    data_off = key_off + len(schluessel)
    kopf = b"\x00PSF" + struct.pack("<IIII", 0x101, key_off, data_off, 1)
    eintrag = struct.pack("<HHIII", 0, 0x204, len(daten), len(daten), 0)
    return kopf + eintrag + schluessel + daten


def _schreiben(wurzel: str, inhalte: "dict[str, bytes]") -> None:
    for rel, daten in inhalte.items():
        voll = os.path.join(wurzel, *rel.split("/"))
        os.makedirs(os.path.dirname(voll), exist_ok=True)
        Path(voll).write_bytes(daten)


def _spiel_klein() -> "dict[str, bytes]":
    return {
        "eboot.bin": b"\x7fELF" + bytes(500),
        "sce_sys/param.json": b"{}",
        "Media/text.txt": b"Hallo Welt\n" * 80_000,
        "Media/zufall.bin": _zufall(300_000, 3),
        "data/a.pak": b"A" * 200_000 + _zufall(100_000, 9),
        "data/b.pak": b"A" * 200_000 + _zufall(100_000, 11),                 # teilt Chunks mit a.pak (Dedup)
        "data/klein.cfg": b"a=1\n",
        "data/leer.bin": b"",
        "data/gross.bin": _zufall(2_500_000, 7) + b"x" * 1_000_000,
    }


def _profil_einspurig() -> str:
    """Das Standardprofil mit einer Spur und ohne Auto-Loose - das Layout, das der Strom schreibt."""
    return ap.standardprofil_text(arbeiter=2).replace("pack_count = 4", "pack_count = 1") \
        .replace("auto_loose_large_files = true", "auto_loose_large_files = false")


def _gelesen(ordner: str) -> "dict[str, bytes]":
    return {n: Path(ordner, n).read_bytes() for n in sorted(os.listdir(ordner))}


def _in_stuecken(baum: sb.OrdnerBaum, laenge: int) -> sb.OrdnerBaum:
    """Ein Baum, dessen Dateien in unregelmaessig kleinen Stuecken kommen (wie von einem fragmentierten Abbild)."""
    neu = []
    for d in baum.dateien():
        def leser(_stueck: int, d=d):
            daten = b"".join(d.lesen())
            pos, schritt = 0, laenge
            while pos < len(daten):
                yield daten[pos:pos + schritt]
                pos += schritt
                schritt = laenge + (pos % 7)
        neu.append(sb.BaumDatei(d.rel, d.groesse, leser))
    baum._dateien = neu
    return baum


@unittest.skipUnless(l4.verfuegbar(), "Packwerkzeug oder lz4 fehlt")
class _Grundlage(unittest.TestCase):
    def setUp(self) -> None:
        l4._werkzeug()                                       # legt den Ordner des Packwerkzeugs in sys.path
        import build_ampr_index                              # liegt dort
        self.index_bauen = build_ampr_index.build_index_local
        self.tmp = tempfile.mkdtemp(prefix="lz4strom_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.spiel = os.path.join(self.tmp, "spiel")
        _schreiben(self.spiel, _spiel_klein())
        self.index = os.path.join(self.tmp, "ampr_emu.index")
        self.index_bauen(Path(self.spiel), Path(self.index), False)
        self.profil = os.path.join(self.tmp, "ampr_pack.toml")
        Path(self.profil).write_text(_profil_einspurig(), encoding="utf-8")

    # -- Hilfen -------------------------------------------------------------------------------------------------------------
    def werkzeug(self, profil: "str | None" = None) -> "dict[str, bytes]":
        ziel = os.path.join(self.tmp, "werkzeug")
        shutil.rmtree(ziel, True)
        os.makedirs(ziel)
        ap.packen(self.spiel, self.index, ziel, profil or self.profil, melden=lambda _z: None)
        return _gelesen(ziel)

    def messen(self, baum=None, profil: "str | None" = None, arbeiter: int = 2, **kw):
        baum = baum or sb.OrdnerBaum(self.spiel)
        auswahl = l4.auswaehlen(baum, self.index, profil or self.profil)
        return baum, auswahl, l4.messen(baum, auswahl, arbeiter=arbeiter, **kw)

    def strom_ordner(self, baum, auswahl, messung, name: str = "strom", arbeiter: int = 2, **kw) -> str:
        ziel = os.path.join(self.tmp, name)
        shutil.rmtree(ziel, True)
        os.makedirs(ziel)
        offen: "dict[str, object]" = {}
        try:
            for datei, daten in l4.strom(baum, auswahl, messung, arbeiter=arbeiter, **kw):
                fh = offen.get(datei)
                if fh is None:
                    fh = offen[datei] = open(os.path.join(ziel, datei), "wb")
                fh.write(daten)
        finally:
            for fh in offen.values():
                fh.close()
        return ziel


class ByteGleichheitTests(_Grundlage):
    def test_eine_spur_wie_das_werkzeug(self) -> None:
        baum, auswahl, messung = self.messen()
        ziel = self.strom_ordner(baum, auswahl, messung)
        self.assertEqual(self.werkzeug(), _gelesen(ziel))
        self.assertEqual(messung.ergebnis.chunks, len(messung.chunk_saetze) // l4.CHUNK_EINTRAG)

    def test_mehrere_baender_wie_das_werkzeug(self) -> None:
        profil = os.path.join(self.tmp, "klein.toml")
        Path(profil).write_text(_profil_einspurig().replace('max_pack_size = "8GiB"', 'max_pack_size = "1MiB"'), encoding="utf-8")
        baum, auswahl, messung = self.messen(profil=profil)
        self.assertGreaterEqual(len(messung.baender), 3)
        ziel = self.strom_ordner(baum, auswahl, messung)
        self.assertEqual(self.werkzeug(profil), _gelesen(ziel))
        for name, groesse in messung.dateien():
            self.assertEqual(os.path.getsize(os.path.join(ziel, name)), groesse, name)

    def test_verify_des_werkzeugs_gegen_die_quelle(self) -> None:
        baum, auswahl, messung = self.messen()
        ziel = self.strom_ordner(baum, auswahl, messung, pruefen=True)
        ap.pruefen(os.path.join(ziel, ap.MANIFEST_NAME), app0=self.spiel, melden=lambda _z: None)

    def test_beliebig_geschnittene_stuecke(self) -> None:
        baum = _in_stuecken(sb.OrdnerBaum(self.spiel), 70_001)
        baum, auswahl, messung = self.messen(baum)
        ziel = self.strom_ordner(baum, auswahl, messung)
        self.assertEqual(self.werkzeug(), _gelesen(ziel))

    def test_faeden_aendern_nichts(self) -> None:
        baum, auswahl, m1 = self.messen(arbeiter=1)
        _b, _a, m8 = self.messen(arbeiter=8)
        self.assertEqual(m1.build_id, m8.build_id)
        eins = self.strom_ordner(baum, auswahl, m1, "eins", arbeiter=1)
        acht = self.strom_ordner(baum, auswahl, m8, "acht", arbeiter=8)
        self.assertEqual(_gelesen(eins), _gelesen(acht))

    def test_aus_exfat(self) -> None:
        abbild = os.path.join(self.tmp, "spiel.exfat")
        with open(abbild, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        with sb.ExfatBaum(abbild) as baum:
            baum, auswahl, messung = self.messen(baum)
            ziel = self.strom_ordner(baum, auswahl, messung)
        self.assertEqual(self.werkzeug(), _gelesen(ziel))

    def test_stromstuecke_haben_die_gemessene_laenge(self) -> None:
        baum, auswahl, messung = self.messen()
        laengen: "dict[str, int]" = {}
        reihenfolge: "list[str]" = []
        for name, daten in l4.strom(baum, auswahl, messung):
            laengen[name] = laengen.get(name, 0) + len(daten)
            if not reihenfolge or reihenfolge[-1] != name:
                reihenfolge.append(name)
        self.assertEqual(list(messung.dateien()), [(n, laengen[n]) for n in reihenfolge])
        self.assertEqual(reihenfolge, [n for n, _g in messung.dateien()])

    def test_namen_der_packdateien(self) -> None:
        _b, _a, messung = self.messen()
        for name, _g in messung.dateien():
            self.assertTrue(l4.ist_packname(name), name)
            self.assertTrue(abbild_strom.ist_packname(name), name)
        self.assertFalse(l4.ist_packname("data/a.pak"))
        self.assertFalse(l4.ist_packname("ampr_emu.index"))
        self.assertIs(abbild_strom.packer_der(messung), l4)

    def test_ohne_runtime_im_profil_kein_laufzeitprofil(self) -> None:
        text = _profil_einspurig()
        text = text[:text.index("# Vorgaben der Laufzeit")]
        profil = os.path.join(self.tmp, "ohne.toml")
        Path(profil).write_text(text, encoding="utf-8")
        _b, _a, messung = self.messen(profil=profil)
        self.assertIsNone(messung.laufzeit)
        self.assertEqual([ap.MANIFEST_NAME, ap.PRUEFSUMMEN_NAME], [n for n, _g in messung.dateien()][-2:])


class AuswahlTests(_Grundlage):
    def test_systemdateien_und_filme_bleiben_lose(self) -> None:
        _schreiben(self.spiel, {"movies/film.bin": b"M" * 100_000, "cache/playgo.pgm": b"P" * 100_000})
        self.index_bauen(Path(self.spiel), Path(self.index), False)
        profil = os.path.join(self.tmp, "p.toml")
        ap.profil_schreiben_aus_baum(profil, sb.OrdnerBaum(self.spiel), arbeiter=2)
        auswahl = l4.auswaehlen(sb.OrdnerBaum(self.spiel), self.index, profil)
        gepackt = {rel for rel, _g in auswahl.gepackt}
        self.assertNotIn("movies/film.bin", gepackt)
        self.assertNotIn("cache/playgo.pgm", gepackt)
        self.assertIn("Media/zufall.bin", gepackt)
        self.assertEqual((), ap.systemdateien_aus_dateien(gepackt))

    def test_leere_und_ausgeschlossene_dateien_stehen_als_lose_im_manifest(self) -> None:
        baum, auswahl, messung = self.messen()
        ziel = self.strom_ordner(baum, auswahl, messung)
        zeilen = ap.liste(os.path.join(ziel, ap.MANIFEST_NAME), melden=lambda _z: None)
        lose = {z["path"] for z in zeilen if not z.get("packed")}
        self.assertEqual({"/app0/Media/text.txt", "/app0/data/klein.cfg", "/app0/eboot.bin", "/app0/sce_sys/param.json"}, lose)
        # eine leere Datei fuehrt auch das Werkzeug als gepackte Datei ohne Chunk
        leer = next(z for z in zeilen if z["path"] == "/app0/data/leer.bin")
        self.assertTrue(leer.get("packed"))
        self.assertEqual(len(zeilen), 9)

    def test_nichts_zu_packen(self) -> None:
        schlank = os.path.join(self.tmp, "schlank")
        _schreiben(schlank, {"eboot.bin": b"\x7fELF" + bytes(100), "data/x.txt": b"abc"})
        index = os.path.join(self.tmp, "schlank.index")
        self.index_bauen(Path(schlank), Path(index), False)
        baum = sb.OrdnerBaum(schlank)
        auswahl = l4.auswaehlen(baum, index, self.profil)
        with self.assertRaises(l4.Lz4PackFehler) as ctx:
            l4.messen(baum, auswahl)
        self.assertEqual("ampr_zstd.nichts_zu_packen", str(ctx.exception))

    def test_datei_fehlt_in_der_quelle(self) -> None:
        os.remove(os.path.join(self.spiel, "data", "a.pak"))
        with self.assertRaises(l4.Lz4PackFehler):
            l4.auswaehlen(sb.OrdnerBaum(self.spiel), self.index, self.profil)

    def test_groesse_weicht_vom_index_ab(self) -> None:
        with open(os.path.join(self.spiel, "data", "a.pak"), "ab") as fh:
            fh.write(b"mehr")
        with self.assertRaises(l4.Lz4PackFehler):
            l4.auswaehlen(sb.OrdnerBaum(self.spiel), self.index, self.profil)

    def test_auto_loose_wird_gezaehlt_und_uebergangen(self) -> None:
        profil = os.path.join(self.tmp, "al.toml")
        Path(profil).write_text(_profil_einspurig().replace("auto_loose_large_files = false", "auto_loose_large_files = true")
                                .replace('auto_loose_min_file_size = "64MiB"', 'auto_loose_min_file_size = "1MiB"'), encoding="utf-8")
        _b, auswahl, _m = self.messen(profil=profil)
        self.assertEqual(1, auswahl.auto_loose_uebergangen)                      # data/gross.bin (3,5 MB)
        self.assertIn("data/gross.bin", {rel for rel, _g in auswahl.gepackt})


class NichtImStromTests(_Grundlage):
    def test_mehrere_gruppen(self) -> None:
        text = _profil_einspurig().replace('[[rule]]\naction = "compress"', '[groups.zweite]\npack_count = 1\n'
                                           'assignment = "balanced"\nmax_pack_size = "8GiB"\n\n[[rule]]\naction = "compress"\n'
                                           'include = ["data/**"]\nblock_size = "64KiB"\ngroup = "zweite"\nlayout = "mixed"\n\n'
                                           '[[rule]]\naction = "compress"', 1)
        profil = os.path.join(self.tmp, "zwei.toml")
        Path(profil).write_text(text, encoding="utf-8")
        with self.assertRaises(l4.Lz4NichtImStrom):
            l4.auswaehlen(sb.OrdnerBaum(self.spiel), self.index, profil)
        self.assertIn("2 Gruppen", l4.grund_gegen_strom(profil))

    def test_striping_grosser_dateien(self) -> None:
        text = _profil_einspurig().replace("pack_count = 1", "pack_count = 2").replace(
            "stripe_large_files = false", "stripe_large_files = true")
        profil = os.path.join(self.tmp, "stripe.toml")
        Path(profil).write_text(text, encoding="utf-8")
        self.assertIn("Striping", l4.grund_gegen_strom(profil))

    def test_gewoehnliches_profil_ist_im_strom_moeglich(self) -> None:
        self.assertEqual("", l4.grund_gegen_strom(self.profil))
        Path(self.profil).write_text(ap.standardprofil_text(arbeiter=2), encoding="utf-8")          # pack_count = 4 wie im Programm
        self.assertEqual("", l4.grund_gegen_strom(self.profil))

    def test_unlesbares_profil_ist_kein_grund(self) -> None:
        Path(self.profil).write_text("das ist [kein toml", encoding="utf-8")
        self.assertEqual("", l4.grund_gegen_strom(self.profil))


class FehlerTests(_Grundlage):
    def test_quelle_zwischen_den_durchgaengen_geaendert(self) -> None:
        baum, auswahl, messung = self.messen()
        with open(os.path.join(self.spiel, "Media", "zufall.bin"), "r+b") as fh:
            fh.seek(1000)
            fh.write(b"\xff\xfe\xfd")
        baum = sb.OrdnerBaum(self.spiel)
        with self.assertRaises(l4.Lz4PackFehler) as ctx:
            list(l4.strom(baum, auswahl, messung))
        self.assertIn("weicht vom Messdurchgang ab", str(ctx.exception))

    def test_datei_gewachsen(self) -> None:
        baum, auswahl, messung = self.messen()
        with open(os.path.join(self.spiel, "data", "a.pak"), "ab") as fh:
            fh.write(b"mehr")
        with self.assertRaises(l4.Lz4PackFehler):
            list(l4.strom(sb.OrdnerBaum(self.spiel), auswahl, messung))

    def test_abbruch(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        auswahl = l4.auswaehlen(baum, self.index, self.profil)
        with self.assertRaises(l4.Lz4PackFehler) as ctx:
            l4.messen(baum, auswahl, abbruch=lambda: True)
        self.assertEqual("ampr_pack.abgebrochen", str(ctx.exception))

    def test_abbruch_im_schreibdurchgang(self) -> None:
        baum, auswahl, messung = self.messen()
        zaehler = {"n": 0}

        def abbruch() -> bool:
            zaehler["n"] += 1
            return zaehler["n"] > 5
        with self.assertRaises(l4.Lz4PackFehler) as ctx:
            list(l4.strom(baum, auswahl, messung, abbruch=abbruch))
        self.assertEqual("ampr_pack.abgebrochen", str(ctx.exception))

    def test_dateiliste_weicht_von_der_messung_ab(self) -> None:
        baum, auswahl, messung = self.messen()
        messung.eintraege = messung.eintraege[:-1]
        with self.assertRaises(l4.Lz4PackFehler):
            list(l4.strom(baum, auswahl, messung))

    def test_ein_falsch_verdichteter_block_faellt_auf(self) -> None:
        baum, auswahl, messung = self.messen()
        messung.gespeicherte_summen[3] ^= 1
        with self.assertRaises(l4.Lz4PackFehler) as ctx:
            list(l4.strom(baum, auswahl, messung))
        self.assertIn("anderer", str(ctx.exception))

    def test_zu_kurze_datei_im_baum(self) -> None:
        baum, auswahl, _m = self.messen()
        kurz = [sb.BaumDatei(d.rel, d.groesse, (lambda _s, d=d: iter([b"".join(d.lesen())[:-5]])) if d.rel == "data/a.pak"
                             else d._leser) for d in baum.dateien()]
        baum._dateien = kurz
        with self.assertRaises(l4.Lz4PackFehler):
            l4.messen(baum, auswahl)

    def test_speicherblock_zu_klein(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        auswahl = l4.auswaehlen(baum, self.index, self.profil)
        with self.assertRaises(l4.Lz4SpeicherZuKlein) as ctx:
            l4.messen(baum, auswahl, einpassen=lambda _m, _i, _w: None)
        self.assertGreater(ctx.exception.manifest_bytes, 0)
        self.assertGreater(ctx.exception.index_bytes, 0)
        self.assertIn("decoded_cache_bytes", ctx.exception.bisher)

    def test_caches_werden_in_den_speicherblock_gekuerzt(self) -> None:
        baum = sb.OrdnerBaum(self.spiel)
        auswahl = l4.auswaehlen(baum, self.index, self.profil)
        messung = l4.messen(baum, auswahl, einpassen=lambda _m, _i, werte: dict(werte, decoded_cache_bytes=16 * 1024 * 1024))
        self.assertNotEqual(messung.laufzeit_bisher, messung.laufzeit_werte)
        self.assertEqual(16 * 1024 * 1024, messung.laufzeit_werte["decoded_cache_bytes"])
        ziel = self.strom_ordner(baum, auswahl, messung)
        self.assertEqual(len(messung.laufzeit), os.path.getsize(os.path.join(ziel, ap.LAUFZEIT_NAME)))
        # Das Werkzeug liest den Satz und die gekuerzte Laufzeit
        ap.pruefen(os.path.join(ziel, ap.MANIFEST_NAME), app0=self.spiel, melden=lambda _z: None)


class PruefenImStromTests(_Grundlage):
    def test_voll_entpackt_jeden_block_eine_auswahl_nur_diese(self) -> None:
        baum, auswahl, messung = self.messen()
        _pack, fmt = l4._werkzeug()
        echte = fmt.Lz4Codec.decompress
        aufrufe = []

        def zaehlen(selbst, daten, groesse):
            aufrufe.append(1)
            return echte(selbst, daten, groesse)
        with mock.patch.object(fmt.Lz4Codec, "decompress", zaehlen):
            list(l4.strom(baum, auswahl, messung))
            self.assertEqual(0, len(aufrufe))
            list(l4.strom(baum, auswahl, messung, pruefen=True))
            voll = len(aufrufe)
            self.assertGreater(voll, 10)
            aufrufe.clear()
            gewaehlt, _bytes = l4.stichprobe_chunks(messung, 7)
            list(l4.strom(baum, auswahl, messung, pruefen=gewaehlt))
            self.assertLessEqual(len(aufrufe), len(gewaehlt))
            self.assertLess(len(aufrufe), voll)

    def test_stichprobe_nimmt_erstes_und_letztes(self) -> None:
        _b, _a, messung = self.messen()
        gewaehlt, geprueft = l4.stichprobe_chunks(messung, 5)
        anzahl = len(messung.chunk_saetze) // l4.CHUNK_EINTRAG
        self.assertIn(0, gewaehlt)
        self.assertIn(anzahl - 1, gewaehlt)
        self.assertEqual(gewaehlt, l4.stichprobe_chunks(messung, 5)[0])
        self.assertGreater(geprueft, 0)

    def test_fortschritt_waechst_bis_eins(self) -> None:
        baum, auswahl, _m = self.messen()
        werte: "list[float]" = []
        l4.messen(baum, auswahl, fortschritt=werte.append)
        self.assertEqual(sorted(werte), werte)
        self.assertAlmostEqual(1.0, werte[-1])


# ---------------------------------------------------------------------------------------------------------------------------
# Das Profil aus dem Lesebaum
# ---------------------------------------------------------------------------------------------------------------------------
class ProfilAusBaumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="lz4profil_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.spiel = os.path.join(self.tmp, "spiel")

    def beide(self, inhalte: "dict[str, bytes]", leere: "tuple[str, ...]" = ()) -> "tuple[str, str, str]":
        """``(Bezeichnung, Text aus dem Ordner, Text aus dem Baum)``."""
        shutil.rmtree(self.spiel, True)
        _schreiben(self.spiel, inhalte)
        for ordner in leere:
            os.makedirs(os.path.join(self.spiel, *ordner.split("/")), exist_ok=True)
        aus_ordner = ap.profil_schreiben(os.path.join(self.tmp, "a.toml"), arbeiter=2, app0=self.spiel)
        aus_baum = ap.profil_schreiben_aus_baum(os.path.join(self.tmp, "b.toml"), sb.OrdnerBaum(self.spiel), arbeiter=2)
        return (ap.profil_integriert_fuer(self.spiel)[0], Path(aus_ordner).read_text(encoding="utf-8"),
                Path(aus_baum).read_text(encoding="utf-8"))

    def test_standardprofil_mit_filmen_systemdateien_und_endungen(self) -> None:
        _name, a, b = self.beide({
            "eboot.bin": b"x", "Media/StreamingAssets/Movies/intro.bin": b"m", "cache/PlayGo.pgm": b"p",
            "tex/Logo.PNG": b"p", "tex/Boden.Dds": b"d", "tex/klein.png": b"k", "data/a.pak": b"a"}, leere=("leer/movies",))
        self.assertEqual("", _name)
        self.assertEqual(a, b)
        self.assertIn("Media/StreamingAssets/Movies/**", b)
        self.assertIn("leer/movies/**", b)                                       # auch ein leerer Filmordner
        self.assertIn("cache/PlayGo.pgm", b)
        self.assertIn("*.PNG", b)
        self.assertIn("*.Dds", b)

    def test_unity_wird_erkannt(self) -> None:
        name, a, b = self.beide({"eboot.bin": b"x", "Media/Data/Global-Metadata.dat": b"g", "data/a.pak": b"a"})
        self.assertEqual("Unity", name)
        self.assertEqual(a, b)
        self.assertIn("integriertes Profil fuer Unity", b.splitlines()[0])

    def test_title_id_aus_der_sfo(self) -> None:
        name, a, b = self.beide({"eboot.bin": b"x", "sce_sys/param.sfo": _sfo("PPSA21567"), "data/a.pak": b"a"})
        self.assertEqual("PPSA21567", name)
        self.assertEqual(a, b)
        self.assertIn("PPSA21567", b.splitlines()[0])

    def test_insomniac_an_dag_toc_und_d(self) -> None:
        name, a, b = self.beide({"eboot.bin": b"x", "dag": b"d", "toc": b"t", "d/x.bin": b"x"})
        self.assertEqual("Insomniac", name)
        self.assertEqual(a, b)
        # dag und toc allein, ohne den Ordner d, reichen nicht
        name2, a2, b2 = self.beide({"eboot.bin": b"x", "dag": b"d", "toc": b"t"})
        self.assertEqual("", name2)
        self.assertEqual(a2, b2)

    def test_kaputte_oder_zu_grosse_sfo_ist_kein_grund_zum_abbruch(self) -> None:
        name, a, b = self.beide({"eboot.bin": b"x", "sce_sys/param.sfo": b"kaputt", "data/a.pak": b"a"})
        self.assertEqual("", name)
        self.assertEqual(a, b)

    def test_ein_anwenderprofil_bleibt(self) -> None:
        _schreiben(self.spiel, {"eboot.bin": b"x"})
        ziel = os.path.join(self.tmp, "eigen.toml")
        Path(ziel).write_text("# mein Profil\n", encoding="utf-8")
        self.assertEqual(ziel, ap.profil_schreiben_aus_baum(ziel, sb.OrdnerBaum(self.spiel)))
        self.assertEqual("# mein Profil\n", Path(ziel).read_text(encoding="utf-8"))

    def test_ordnerbaum_ohne_ordner_liste_genuegt(self) -> None:
        """``ordner()`` darf Verzeichnisse mit Dateien auslassen: Filmordner kommen aus den Pfaden der Dateien."""
        _schreiben(self.spiel, {"eboot.bin": b"x", "a/Video/clip.bin": b"c"})

        class Ohne(sb.OrdnerBaum):
            def ordner(self):
                return []
        profil = ap.profil_schreiben_aus_baum(os.path.join(self.tmp, "c.toml"), Ohne(self.spiel))
        self.assertIn("a/Video/**", Path(profil).read_text(encoding="utf-8"))

    def test_kerne_gleich_den_ordnerfunktionen(self) -> None:
        self.assertEqual(("a/Movies/**", "x/video/**"), ap.filmordner_aus_ordnern(["a", "a/Movies", "x/video", "x/Videoclips"]))
        self.assertEqual(("PlayGo.pgm", "x/game.packman"), ap.systemdateien_aus_dateien(["PlayGo.pgm", "x/game.packman", "x/y.bin"]))
        self.assertEqual(("*.PNG",), ap.lose_endungen_aus_dateien(["a/b.PNG", "c.png", "d.xyz", "e/F.Xyz"]))
        self.assertEqual(("Unity", ("data/globalgamemanagers",)), ap.direktleser_aus_dateien(["a.bin", "data/globalgamemanagers"]))
        self.assertEqual("PPSA12345", ap.title_id_aus_sfo_bytes(_sfo("PPSA12345")))
        self.assertEqual("", ap.title_id_aus_sfo_bytes(b""))


# ---------------------------------------------------------------------------------------------------------------------------
# Der ganze Weg im Hauptprogramm
# ---------------------------------------------------------------------------------------------------------------------------
class _Var:
    def __init__(self, wert) -> None:
        self._w = wert

    def get(self):
        return self._w


class _Fortschritt:
    def __getattr__(self, name):
        return lambda *a, **k: None


class _Label:
    def config(self, **_k) -> None:
        pass


class _Wurzel:
    def after(self, _ms, callback) -> None:
        callback()


def _gui(tmp: str, *, weglassen: bool = False, lib: bytes = NG_LIB) -> "GUI":
    g = GUI.__new__(GUI)
    protokoll: "list[str]" = []
    g._log_lines = protokoll
    g._append_to_log = protokoll.append
    g._set_status = lambda text: None
    g._fmt_bytes = lambda n: str(n)
    g.is_running = True
    g.root = _Wurzel()
    g.status_label = _Label()
    g.progress_engine = _Fortschritt()
    g.mkpfs_dir = str((ROOT / "MkPFS-1.1.0").resolve())
    g._extract_embedded_mkpfs = lambda anlegen=True: str((ROOT / "MkPFS-1.1.0").resolve())
    g.task_progress = 0.0
    g.task_total_source_bytes = 0
    g._copy_total_bytes = g._copy_done_bytes = 0
    g._copy_total_exact = True
    g._copy_rate_bps = 0.0
    g._copy_rate_trend = ""
    g._online_nachschlag_erlaubt = lambda: False
    g._ask_yesno_threadsafe = lambda *a, **k: True
    g._notify_param_json_problem = lambda missing: None
    g.wahl = {"ampr_integrate_var": True, "ampr_pack_methode": True, "backport_integrate_var": False}
    g._tk_wert = lambda name, vorgabe=False: g.wahl.get(name, vorgabe)
    g.einstellungen = {}
    g._load_setting = lambda name, vorgabe=None: g.einstellungen.get(name, vorgabe)
    g._ampr_wird_eingebaut = lambda: True
    g._ampr_methode = lambda: APP.AMPR_METHODE_ASSETPACK
    g._ampr_pack_verfahren = lambda: "lz4"
    g._ampr_lz4_stufe = lambda: 9
    g._ampr_pack_arbeiter = lambda: 2
    g._ampr_zstd_arbeiter = lambda: 2
    g._ampr_voll_pruefen = lambda: False
    g._ampr_pack_fortschritt = lambda prozent, phase: None
    g._ampr_pack_konsolenhinweis = lambda ordner: g._append_to_log("KONSOLENHINWEIS")
    g._ampr_originale_weglassen = weglassen
    g._pack_infotext = ""
    g._quellgroesse_mit_meldung = lambda pfad: 1
    g._mkdtemp = lambda prefix, dir_path=None: tempfile.mkdtemp(prefix=prefix, dir=os.path.join(tmp, "temp"))
    g._dump_ordner_basis = lambda dst: None
    g._bauziel_neben_quelle = lambda final: final
    g._bauziel_uebernehmen = lambda ist, final: final
    g._ampr_zstd_regeldatei = lambda: ""

    def integration(ordner: str, **_k) -> str:
        """Nachbildung von ``_integration_ampr`` mit denselben Bausteinen (Bibliothek, Index ueber die Ansicht, Packs messen)."""
        fakelib = os.path.join(ordner, "fakelib")
        os.makedirs(fakelib, exist_ok=True)
        with open(os.path.join(fakelib, "libSceAmpr.sprx"), "wb") as fh:
            fh.write(lib)
        g._ampr_ordner_ist_kopie = True
        index = Path(ordner) / "ampr_emu.index"
        g._build_ampr_index_local(Path(ordner), index)
        return ordner if g._ampr_assetpakete_bauen(ordner, str(index), {"variant": ""}) else ""

    g._integration_anwenden = integration
    return g


def _spiel_hauptmodul() -> "dict[str, bytes]":
    param = json.dumps(create_default_param(title_id="PPSA04263", title="Test Game")).encode("utf-8")
    return {
        "eboot.bin": b"\x7fELF" + bytes(2000),
        "sce_sys/param.json": param,
        "sce_sys/icon0.png": _zufall(5000, 2),
        "fakelib/libSceAmpr.sprx": b"original-lib" * 20,
        "sce_module/libc.prx": b"prx" * 100,
        "Media/text.txt": b"Hallo Welt\n" * 80_000,
        "Media/zufall.bin": _zufall(300_000, 3),
        "data/genau.bin": b"A" * 65536,
        "data/klein.cfg": b"a=1\n",
        "data/leer.bin": b"",
        "movies/film.bin": _zufall(50_000, 5),
    }


@unittest.skipUnless(l4.verfuegbar(), "Packwerkzeug oder lz4 fehlt")
class _HauptGrundlage(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp(prefix="lz4haupt_")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "temp"))
        self.inhalt = _spiel_hauptmodul()
        self.spiel = os.path.join(self.tmp, "spiel")
        _schreiben(self.spiel, self.inhalt)
        self.quelle = os.path.join(self.tmp, "spiel.exfat")
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        self.stempel = (os.path.getsize(self.quelle), os.stat(self.quelle).st_mtime_ns)
        self.ziel = os.path.join(self.tmp, "ziel")
        os.makedirs(self.ziel)

    def lauf(self, quelle: "str | None" = None, **kw):
        arg = {k: kw.pop(k) for k in ("ordner", "ziel") if k in kw}
        g = _gui(self.tmp, **kw)
        return g, g._mode_exfat_umpacken_strom(quelle or self.quelle, self.ziel, **arg)

    def packs_ausgelesen(self, dateien: "dict[str, sb.BaumDatei]") -> str:
        ziel = os.path.join(self.tmp, "gelesen")
        shutil.rmtree(ziel, True)
        os.makedirs(ziel)
        for rel, d in dateien.items():
            if l4.ist_packname(rel):
                Path(ziel, rel).write_bytes(b"".join(d.lesen()))
        return ziel


class StromWegTests(_HauptGrundlage):
    def test_ganzer_weg_aus_exfat(self) -> None:
        g, ok = self.lauf(lib=b"drakmor-ampr-emu-lib" * 30)
        self.assertTrue(ok, "\n".join(g._log_lines))
        ausgabe = os.path.join(self.ziel, "spiel.exfat")
        with sb.ExfatBaum(ausgabe) as neu:
            dateien = neu.suchen()
            self.assertEqual(b"drakmor-ampr-emu-lib" * 30, b"".join(dateien["fakelib/libSceAmpr.sprx"].lesen()))
            self.assertIn("ampr_assets.index", dateien)
            self.assertIn("ampr_assets.index.crc", dateien)
            self.assertIn("ampr_assets.index.runtime", dateien)
            self.assertTrue(any(n.startswith("ampr_assets-") and n.endswith(".pak") for n in dateien))
            # LZ4 laesst die Originale stehen (Riegel des Programmprofils), auch wenn "Originale weglassen" gewaehlt war
            for rel in ("Media/text.txt", "Media/zufall.bin", "data/genau.bin", "movies/film.bin"):
                self.assertEqual(self.inhalt[rel], b"".join(dateien[rel].lesen()), rel)
            gepackt = self.packs_ausgelesen(dateien)
            ap.pruefen(os.path.join(gepackt, ap.MANIFEST_NAME), app0=self.spiel, melden=lambda _z: None)
            zeilen = ap.liste(os.path.join(gepackt, ap.MANIFEST_NAME), melden=lambda _z: None)
            packen = {z["path"][len("/app0/"):] for z in zeilen if z.get("packed")}
            self.assertIn("Media/zufall.bin", packen)
            self.assertIn("data/genau.bin", packen)
            self.assertNotIn("Media/text.txt", packen)                       # .txt bleibt lose (LOSE_MUSTER)
            self.assertNotIn("movies/film.bin", packen)                       # Filmordner bleiben lose
            self.assertNotIn("eboot.bin", packen)
            self.assertNotIn("sce_sys/param.json", packen)
        self.assertEqual([], [z for z in ap.systemdateien_im_pack(zeilen)])

    def test_ng_packt_alles_ausser_den_systemdateien_wie_forge(self) -> None:
        """Mit ampr-emu-ng: Texte, Filme und Konfigs kommen mit in die Baender; Systemwege, ``.ini`` und leere Dateien bleiben."""
        g, ok = self.lauf(weglassen=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            gepackt = self.packs_ausgelesen(dateien)
            manifest = os.path.join(gepackt, ap.MANIFEST_NAME)
            ap.pruefen(manifest, app0=self.spiel, melden=lambda _z: None)
            zeilen = ap.liste(manifest, melden=lambda _z: None)
            packen = {z["path"][len("/app0/"):] for z in zeilen if z.get("packed")}
            for rel in ("Media/text.txt", "movies/film.bin", "Media/zufall.bin", "data/genau.bin", "data/klein.cfg",
                        "Media/text.txt"):
                self.assertIn(rel, packen, rel)
            for rel in ("eboot.bin", "sce_sys/param.json", "sce_sys/icon0.png", "sce_module/libc.prx"):
                self.assertNotIn(rel, packen, rel)
                self.assertIn(rel, dateien, rel)
            # Die gepackten Originale fehlen im Abbild, die losen nicht
            for rel in ("Media/text.txt", "movies/film.bin", "data/klein.cfg"):
                self.assertNotIn(rel, dateien, rel)
        self.assertFalse(any("Video im Band" in z for z in g._log_lines))

    def test_pruefung_vorgabe_stichprobe_und_auf_wunsch_vollstaendig(self) -> None:
        """Die Wahl "Vollstaendige Pruefung" gilt auch bei LZ4: Vorgabe aus = Stichprobe, an = jeder Block."""
        stich, ok = self.lauf()
        self.assertTrue(ok, "\n".join(stich._log_lines))
        text = "\n".join(stich._log_lines)
        self.assertIn("Stichprobe", text)
        self.assertNotIn("Prüfung: vollständig", text)
        voll = _gui(self.tmp)
        voll._ampr_voll_pruefen = lambda: True
        shutil.rmtree(self.ziel)
        os.makedirs(self.ziel)
        ok = voll._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        self.assertTrue(ok, "\n".join(voll._log_lines))
        self.assertIn("Prüfung: vollständig", "\n".join(voll._log_lines))

    def test_ng_laesst_die_gepackten_originale_weg(self) -> None:
        """Mit ampr-emu-ng wie bei zstd und Dump Forge: gepackte Originale kommen nicht ins Abbild, nur in die Baender."""
        g, ok = self.lauf(weglassen=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertTrue(g._ampr_originale_weglassen)
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            for rel in ("Media/zufall.bin", "data/genau.bin", "Media/text.txt", "movies/film.bin", "data/klein.cfg"):
                self.assertNotIn(rel, dateien, rel)
            # Systemdateien und leere Dateien bleiben
            for rel in ("eboot.bin", "sce_sys/param.json", "sce_module/libc.prx", "data/leer.bin"):
                self.assertIn(rel, dateien, rel)
            # Die Baender tragen den Inhalt: das Werkzeug liest sie und vergleicht gegen den Ausgangsordner
            gepackt = self.packs_ausgelesen(dateien)
            ap.pruefen(os.path.join(gepackt, ap.MANIFEST_NAME), app0=self.spiel, melden=lambda _z: None)
        text = "\n".join(g._log_lines)
        self.assertIn("kommen nicht ins neue Abbild", text)
        self.assertIn("update_emulators", text)

    def test_drakmors_laufzeit_laesst_die_originale_stehen(self) -> None:
        """Ohne NG liest die Laufzeit nur ueber AMPR: Der Riegel haelt die Originale fest, auch bei "Originale weglassen"."""
        g, ok = self.lauf(weglassen=True, lib=b"drakmor-ampr-emu-lib" * 30)
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertFalse(g._ampr_originale_weglassen)
        self.assertTrue(any("Originale" in z for z in g._log_lines), "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            self.assertIn("Media/zufall.bin", dateien)
            self.assertIn("data/genau.bin", dateien)

    def test_quelle_unveraendert_kein_rest(self) -> None:
        g, ok = self.lauf()
        self.assertTrue(ok, "\n".join(g._log_lines))
        self.assertEqual(self.stempel, (os.path.getsize(self.quelle), os.stat(self.quelle).st_mtime_ns))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")), "Ueberlagerungsordner nicht weggeraeumt")
        self.assertEqual(["spiel.exfat"], os.listdir(self.ziel))
        self.assertIsNone(g._strom_ansicht)
        self.assertIsNone(g._strom_plan)

    def test_protokoll_und_stufen(self) -> None:
        g, ok = self.lauf()
        self.assertTrue(ok, "\n".join(g._log_lines))
        text = "\n".join(g._log_lines)
        self.assertIn("KONSOLENHINWEIS", text)
        self.assertNotIn("zstd", text.lower())
        self.assertNotIn("{", text.replace("{}", ""), "unersetzter Platzhalter im Protokoll")
        for schluessel in ("phase.ueberlagerung", "phase.integration", "phase.messen", "phase.schreiben", "phase.pruefen"):
            self.assertEqual("fertig", g._stufen.zustand(schluessel), schluessel)

    def test_aus_dem_ordner_ohne_arbeitskopie(self) -> None:
        g, ok = self.lauf(self.spiel, ordner=True)
        self.assertTrue(ok, "\n".join(g._log_lines))
        with sb.ExfatBaum(os.path.join(self.ziel, "spiel.exfat")) as neu:
            dateien = neu.suchen()
            self.assertIn("ampr_assets.index", dateien)
            gepackt = self.packs_ausgelesen(dateien)
            ap.pruefen(os.path.join(gepackt, ap.MANIFEST_NAME), app0=self.spiel, melden=lambda _z: None)
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))

    def test_flache_ffpfs_aus_der_liste(self) -> None:
        g, ok = self.lauf(ziel="ffpfs")
        self.assertTrue(ok, "\n".join(g._log_lines))
        pfad = os.path.join(self.ziel, "spiel.ffpfs")
        self.assertTrue(os.path.isfile(pfad), os.listdir(self.ziel))
        with sb.PfsBaum(pfad, mkpfs_ordner=str(ROOT / "MkPFS-1.1.0")) as neu:
            dateien = neu.suchen()
            self.assertIn("ampr_assets.index", dateien)
            gepackt = self.packs_ausgelesen(dateien)
            ap.pruefen(os.path.join(gepackt, ap.MANIFEST_NAME), app0=self.spiel, melden=lambda _z: None)

    def test_abbruch_laesst_nichts_zurueck(self) -> None:
        g = _gui(self.tmp)

        def abbrechen(prozent, phase):
            g.is_running = False
        g._ampr_pack_fortschritt = abbrechen
        ok = g._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))
        self.assertFalse(any("[FEHLER]" in z and "bgebrochen" in z for z in g._log_lines), "\n".join(g._log_lines))

    def test_quelle_aendert_sich_waehrend_des_laufs(self) -> None:
        g = _gui(self.tmp)
        urspruenglich = g._integration_anwenden

        def integration(ordner, **k):
            erg = urspruenglich(ordner, **k)
            with open(self.quelle, "ab") as fh:
                fh.write(b"\0" * 512)
            return erg
        g._integration_anwenden = integration
        ok = g._mode_exfat_umpacken_strom(self.quelle, self.ziel)
        self.assertFalse(ok)
        self.assertEqual([], os.listdir(self.ziel))

    def test_packs_schon_in_der_quelle_bleibt_beim_alten_weg(self) -> None:
        Path(self.spiel, "ampr_assets.index").write_bytes(b"alt")
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))


class OriginaleKlaerenTests(unittest.TestCase):
    """``_ampr_originale_klaeren``: bei LZ4 mit NG im Strom keine Rueckfrage - die Originale fallen weg."""

    def gui(self, *, variante: str, verfahren: str = "lz4", strom: bool = True) -> "GUI":
        g = GUI.__new__(GUI)
        g._log_lines = []
        g._append_to_log = g._log_lines.append
        g._assetpack_gewaehlt = lambda: True
        g._ampr_pack_verfahren = lambda: verfahren
        g._tk_wert = lambda name, vorgabe="": "NG"
        g._ampr_auswahl_beim_start = lambda: {"NG": {"variant": variante}}
        g._strom_erlaubt = lambda einbau_noetig: strom
        g._cli_mode = False
        g.fragen = []
        return g

    def lauf(self, g) -> bool:
        modus = next(iter(GUI._MODE_TARGET_OPTIONS))
        with mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: g.fragen.append(a) or False):
            g._ampr_originale_klaeren(modus)
        return g._ampr_originale_weglassen

    def test_lz4_mit_ng_im_strom_fragt_nicht(self) -> None:
        g = self.gui(variante="ng")
        self.assertTrue(self.lauf(g))
        self.assertEqual([], g.fragen)
        self.assertTrue(GUI._ampr_ng_lz4_im_strom_gewaehlt(g))

    def test_ng_debug_zaehlt_auch(self) -> None:
        self.assertTrue(self.lauf(self.gui(variante="ng-debug")))

    def test_lz4_mit_drakmor_fragt_weiter(self) -> None:
        g = self.gui(variante="no debug")
        self.assertFalse(self.lauf(g))
        self.assertEqual(1, len(g.fragen))

    def test_ohne_strom_fragt_weiter(self) -> None:
        g = self.gui(variante="ng", strom=False)
        self.assertFalse(self.lauf(g))
        self.assertEqual(1, len(g.fragen))

    def test_zstd_bleibt_wie_es_war(self) -> None:
        g = self.gui(variante="ng", verfahren="zstd")
        self.assertTrue(self.lauf(g))
        self.assertEqual([], g.fragen)
        self.assertFalse(GUI._ampr_ng_lz4_im_strom_gewaehlt(g))


class StromErlaubtTests(unittest.TestCase):
    def pruefen(self, **kw) -> bool:
        g = GUI.__new__(GUI)
        g._load_setting = lambda name, vorgabe=None: vorgabe
        g._ampr_wird_eingebaut = lambda: True
        g._ampr_methode = lambda: APP.AMPR_METHODE_ASSETPACK
        g._ampr_pack_verfahren = lambda: kw.get("verfahren", "lz4")
        g._integration_gewaehlt = lambda: True
        return g._strom_erlaubt(einbau_noetig=False)

    @unittest.skipUnless(l4.verfuegbar(), "Packwerkzeug oder lz4 fehlt")
    def test_lz4_geht_jetzt_im_strom(self) -> None:
        self.assertTrue(self.pruefen())

    def test_ohne_packer_der_alte_weg(self) -> None:
        with mock.patch.object(l4, "verfuegbar", lambda: False):
            self.assertFalse(self.pruefen())

    def test_einstellung_aus_erzwingt_den_alten_weg(self) -> None:
        g = GUI.__new__(GUI)
        g._load_setting = lambda name, vorgabe=None: False if name == "exfat_strom" else vorgabe
        self.assertFalse(g._strom_erlaubt(einbau_noetig=False))


class VorabTests(_HauptGrundlage):
    def gui(self) -> "GUI":
        return _gui(self.tmp)

    def test_ohne_profil_und_ohne_besonderheit_nichts(self) -> None:
        with sb.OrdnerBaum(self.spiel) as baum:
            self.assertEqual("", self.gui()._lz4_strom_vorab(self.spiel, True, baum))

    def test_anwenderprofil_neben_dem_dump_ordner(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        with sb.OrdnerBaum(self.spiel) as baum:
            grund = self.gui()._lz4_strom_vorab(self.spiel, True, baum)
            self.assertIn("Anwenders", grund)
            # Bei einem Abbild als Quelle gibt es keine solche Datei zu holen
            self.assertEqual("", self.gui()._lz4_strom_vorab(self.quelle, False, baum))

    def test_profil_des_programms_neben_dem_ordner_ist_keines_des_anwenders(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text(ap.PROFIL_KENNZEILE + "\n", encoding="utf-8")
        with sb.OrdnerBaum(self.spiel) as baum:
            self.assertEqual("", self.gui()._lz4_strom_vorab(self.spiel, True, baum))

    def test_integriertes_profil_mit_mehreren_gruppen(self) -> None:
        _schreiben(self.spiel, {"sce_sys/param.sfo": _sfo("PPSA23566")})                    # EA Sports UFC 6: drei Gruppen
        with sb.OrdnerBaum(self.spiel) as baum:
            grund = self.gui()._lz4_strom_vorab(self.spiel, True, baum)
        self.assertIn("Gruppen", grund)

    def test_integriertes_profil_mit_einer_gruppe_geht(self) -> None:
        _schreiben(self.spiel, {"sce_sys/param.sfo": _sfo("PPSA21567")})                    # ASTRO BOT: eine Gruppe
        with sb.OrdnerBaum(self.spiel) as baum:
            self.assertEqual("", self.gui()._lz4_strom_vorab(self.spiel, True, baum))

    def test_nur_bei_lz4_mit_asset_pack(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        with sb.OrdnerBaum(self.spiel) as baum:
            g = self.gui()
            g._ampr_pack_verfahren = lambda: "zstd"
            self.assertEqual("", g._lz4_strom_vorab(self.spiel, True, baum))
            g = self.gui()
            g._ampr_methode = lambda: APP.AMPR_METHODE_NORMAL
            self.assertEqual("", g._lz4_strom_vorab(self.spiel, True, baum))

    def test_anwenderprofil_schickt_den_ordner_zum_alten_weg(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        g, ergebnis = self.lauf(self.spiel, ordner=True)
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))
        self.assertTrue(any("Zwischenordner" in z or "intermediate folder" in z for z in g._log_lines), "\n".join(g._log_lines))

    def test_mehrere_gruppen_schicken_ein_abbild_zum_alten_weg(self) -> None:
        _schreiben(self.spiel, {"sce_sys/param.sfo": _sfo("PPSA23566")})
        with open(self.quelle, "wb") as fh:
            for stueck in iter_exfat_image(Path(self.spiel)):
                fh.write(stueck)
        g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis)
        self.assertEqual([], os.listdir(self.ziel))

    def test_spaete_umkehr_wenn_der_strom_das_profil_doch_nicht_schreibt(self) -> None:
        """Erst ``auswaehlen`` sieht, dass mehr als eine Gruppe gepackte Dateien hat: Der Lauf kehrt um, ohne dass etwas liegen bleibt."""
        echt = ap.profil_schreiben_aus_baum

        def zwei_gruppen(ziel, baum, arbeiter=0, stufe=ap.LZ4_STUFE_VORGABE, ng=False):
            echt(ziel, baum, arbeiter, stufe, ng)
            text = Path(ziel).read_text(encoding="utf-8")
            # Die letzte passende Regel gewinnt: eine zweite Gruppe fuer Media/ muss hinter der Hauptregel stehen.
            text += ('\n[groups.zweite]\npack_count = 1\nassignment = "balanced"\nmax_pack_size = "8GiB"\n\n'
                     '[[rule]]\naction = "compress"\ninclude = ["Media/**"]\nblock_size = "64KiB"\n'
                     'group = "zweite"\nlayout = "mixed"\n')
            Path(ziel).write_text(text, encoding="utf-8", newline="\n")
            return ziel
        with mock.patch.object(ap, "profil_schreiben_aus_baum", zwei_gruppen):
            g, ergebnis = self.lauf()
        self.assertIsNone(ergebnis, "\n".join(g._log_lines))
        self.assertEqual([], os.listdir(self.ziel))
        self.assertEqual([], os.listdir(os.path.join(self.tmp, "temp")))
        self.assertTrue(any("2 Gruppen" in z for z in g._log_lines), "\n".join(g._log_lines))
        self.assertIsNone(g._strom_ansicht)


class PlatzSchaetzungTests(_HauptGrundlage):
    """Die Platzpruefung vor dem Start kennt die Faelle, in denen LZ4 doch ueber einen Zwischenordner packt (Nachbesserung zu Etappe 14)."""

    def gui(self, quelle_gb: int = 100) -> "GUI":
        g = _gui(self.tmp)
        g._quellgroesse_ermitteln = lambda src: quelle_gb * 1024 ** 3
        g._estimate_unpack_space_requirement = lambda src: None
        g._integration_gewuenscht = lambda: True
        g._umhuellt_neu_packen = False
        g._integration_gewaehlt = lambda: True
        return g

    def temp_fuer(self, g, src: str) -> int:
        return g._platzbedarf_je_quelle(src, "exfat")[0]

    def test_ordner_ohne_besonderheit_braucht_wenig_temp(self) -> None:
        g = self.gui()
        self.assertLess(self.temp_fuer(g, self.spiel), 10 * 1024 ** 3)

    def test_anwenderprofil_neben_dem_ordner_rechnet_den_zwischenordner(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        g = self.gui()
        self.assertTrue(g._lz4_strom_im_voraus_ausgeschlossen(self.spiel, True))
        self.assertGreater(self.temp_fuer(g, self.spiel), 100 * 1024 ** 3, "der Zwischenordner braucht das ganze Spiel")

    def test_profil_des_programms_neben_dem_ordner_zaehlt_nicht(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text(ap.PROFIL_KENNZEILE + "\n", encoding="utf-8")
        self.assertFalse(self.gui()._lz4_strom_im_voraus_ausgeschlossen(self.spiel, True))

    def test_titelprofil_mit_mehreren_gruppen(self) -> None:
        _schreiben(self.spiel, {"sce_sys/param.sfo": _sfo("PPSA23566")})                  # EA Sports UFC 6: drei Gruppen
        g = self.gui()
        self.assertTrue(g._lz4_strom_im_voraus_ausgeschlossen(self.spiel, True))
        self.assertGreater(self.temp_fuer(g, self.spiel), 100 * 1024 ** 3)

    def test_titelprofil_mit_einer_gruppe_bleibt_im_strom(self) -> None:
        _schreiben(self.spiel, {"sce_sys/param.sfo": _sfo("PPSA21567")})                  # ASTRO BOT
        g = self.gui()
        self.assertFalse(g._lz4_strom_im_voraus_ausgeschlossen(self.spiel, True))
        self.assertLess(self.temp_fuer(g, self.spiel), 10 * 1024 ** 3)

    def test_abbild_als_quelle_bleibt_unentschieden(self) -> None:
        """Ein Abbild muesste geoeffnet werden, um das Profil zu kennen: Die Schaetzung bleibt beim Strom, der Lauf warnt dann selbst."""
        Path(self.quelle + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        self.assertFalse(self.gui()._lz4_strom_im_voraus_ausgeschlossen(self.quelle, False))

    def test_nur_bei_lz4_mit_asset_pack(self) -> None:
        Path(self.spiel + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        g = self.gui()
        g._ampr_pack_verfahren = lambda: "zstd"
        self.assertFalse(g._lz4_strom_im_voraus_ausgeschlossen(self.spiel, True))
        g = self.gui()
        g._ampr_methode = lambda: APP.AMPR_METHODE_NORMAL
        self.assertFalse(g._lz4_strom_im_voraus_ausgeschlossen(self.spiel, True))

    def test_rueckfall_warnt_vor_zu_wenig_platz(self) -> None:
        g = self.gui(quelle_gb=100)
        g._get_runtime_temp_dir = lambda anlegen=True: self.tmp
        g._freier_platz = lambda pfad: 20 * 1024 ** 3
        g._lz4_rueckfall_melden(self.quelle, "Packprofil des Anwenders")
        text = "\n".join(g._log_lines)
        self.assertIn("Zwischenordner", text)
        self.assertIn("Achtung", text)
        self.assertIn(str(int(100 * 1024 ** 3 * g._PLATZFAKTOR_TEMP_MIT_KOPIE)), text)

    def test_rueckfall_ohne_platzmangel_meldet_nur_den_grund(self) -> None:
        g = self.gui(quelle_gb=100)
        g._get_runtime_temp_dir = lambda anlegen=True: self.tmp
        g._freier_platz = lambda pfad: 500 * 1024 ** 3
        g._lz4_rueckfall_melden(self.quelle, "2 Gruppen: a, b")
        text = "\n".join(g._log_lines)
        self.assertIn("2 Gruppen", text)
        self.assertNotIn("Achtung", text)

    def test_rueckfall_im_lauf_warnt(self) -> None:
        """Ein Anwenderprofil neben dem Ordner schickt den Lauf zum alten Weg - mit Warnung, wenn der Arbeitsordner zu klein ist."""
        Path(self.spiel + "_ampr_pack.toml").write_text("# aus Mitschnitten\n", encoding="utf-8")
        g = _gui(self.tmp)
        g._freier_platz = lambda pfad: 1
        g._quellgroesse_ermitteln = lambda src: 5 * 1024 ** 3
        g._get_runtime_temp_dir = lambda anlegen=True: self.tmp
        ergebnis = g._mode_exfat_umpacken_strom(self.spiel, self.ziel, ordner=True)
        self.assertIsNone(ergebnis)
        self.assertTrue(any("Achtung" in z for z in g._log_lines), "\n".join(g._log_lines))


class MessenImHauptmodulTests(_HauptGrundlage):
    """``_ampr_lz4_messen`` mit einer Ansicht aus einem Ordner (ohne Bau des Abbilds): die Riegel des Weges ueber den Ordner."""

    def vorbereiten(self):
        g = _gui(self.tmp)
        baum = sb.OrdnerBaum(self.spiel)
        g._strom_ansicht = mock.Mock()
        g._strom_ansicht.baum = lambda: baum
        g._strom_alter_weg = ""
        index = os.path.join(self.tmp, "arbeit", "ampr_emu.index")
        os.makedirs(os.path.dirname(index))
        g._build_ampr_index_local(Path(self.spiel), Path(index))
        return g, index

    def messen(self, g, index):
        return g._ampr_lz4_messen(os.path.join(self.tmp, "arbeit", "schatten"), index, {"variant": ""})

    def test_plan_mit_auswahl_und_messung(self) -> None:
        g, index = self.vorbereiten()
        self.assertTrue(self.messen(g, index), "\n".join(g._log_lines))
        plan = g._strom_plan
        self.assertIsInstance(plan["auswahl"], l4.Lz4Auswahl)
        self.assertIs(plan["messung"].modul, l4)
        self.assertIn("Gemessen", "\n".join(g._log_lines))

    def test_systemdatei_im_band_ist_ein_riegel(self) -> None:
        _schreiben(self.spiel, {"cache/playgo.pgm": b"P" * 100_000})
        g, index = self.vorbereiten()
        text = ap.standardprofil_text(arbeiter=2)
        text = text.replace("*.packman", "*.nichtda").replace("playgo.pgm", "nichtda.pgm")

        def profil_ohne_ausschluss(ziel, baum, arbeiter=0, stufe=9, ng=False):
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            Path(ziel).write_text(text, encoding="utf-8", newline="\n")
            return ziel
        with mock.patch.object(ap, "profil_schreiben_aus_baum", profil_ohne_ausschluss):
            self.assertFalse(self.messen(g, index))
        self.assertTrue(any("playgo.pgm" in z for z in g._log_lines), "\n".join(g._log_lines))
        self.assertIsNone(getattr(g, "_strom_plan", None))

    def test_harte_grenze_reisst(self) -> None:
        g, index = self.vorbereiten()
        with mock.patch.dict(ap.GRENZEN, {"chunks": 3}):
            self.assertFalse(self.messen(g, index))
        self.assertTrue(any("chunks" in z for z in g._log_lines), "\n".join(g._log_lines))

    def test_speicherblock_zu_klein(self) -> None:
        g, index = self.vorbereiten()
        with mock.patch.object(ap, "POOL_BYTES", 1024 * 1024):
            self.assertFalse(self.messen(g, index))
        self.assertTrue(any("Speicherblock" in z or "memory block" in z.lower() for z in g._log_lines), "\n".join(g._log_lines))

    def test_filme_im_band_sind_nur_eine_warnung(self) -> None:
        _schreiben(self.spiel, {"Media/Videos/x.bin": b"V" * 100_000})
        g, index = self.vorbereiten()

        def profil_ohne_filmordner(ziel, baum, arbeiter=0, stufe=9, ng=False):
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            Path(ziel).write_text(ap.standardprofil_text(arbeiter=2), encoding="utf-8", newline="\n")
            return ziel
        with mock.patch.object(ap, "profil_schreiben_aus_baum", profil_ohne_filmordner):
            self.assertTrue(self.messen(g, index), "\n".join(g._log_lines))
        self.assertTrue(any("Media/Videos/x.bin" in z for z in g._log_lines))

    def test_ein_profil_des_anwenders_geht_zum_alten_weg(self) -> None:
        g, index = self.vorbereiten()

        def anwender(ziel, baum, arbeiter=0, stufe=9, ng=False):
            os.makedirs(os.path.dirname(ziel), exist_ok=True)
            Path(ziel).write_text("# aus Mitschnitten\n", encoding="utf-8")
            return ziel
        with mock.patch.object(ap, "profil_schreiben_aus_baum", anwender):
            self.assertFalse(self.messen(g, index))
        self.assertIn("Anwenders", g._strom_alter_weg)

    def test_ohne_werkzeug(self) -> None:
        g, index = self.vorbereiten()
        with mock.patch.object(l4, "verfuegbar", lambda: False):
            self.assertFalse(self.messen(g, index))


if __name__ == "__main__":
    unittest.main()
