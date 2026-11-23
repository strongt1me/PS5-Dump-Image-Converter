# -*- coding: utf-8 -*-
"""Die Pruefung der PNG in ``sce_sys`` vor dem Bau eines Pakets (22.11.2026).

Anlass: Dump Forge packt ein beschaedigtes ``pic2.png`` unveraendert ins Paket und sagt nichts dazu (gemessen mit Forge 0.5.7); im Dump
``PPSA02195-Trackmania`` liegt eine solche Datei (532 Zufallsbytes ohne PNG-Kennung). Das Programm warnt jetzt im Protokoll und aendert
nichts am Spielordner. Hier: die Pruefung selbst (``ps5_pkg_werkzeug.png_fehler`` / ``bilder_befunde``); die Zeile im Fenster
steht in ``test_ps5_pkg_forge.py``.
"""
from __future__ import annotations

import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import ps5_pkg_werkzeug as wz  # noqa: E402
from ps5_validator.utils.i18n import STRINGS            # noqa: E402


def _block(art: bytes, daten: bytes) -> bytes:
    return struct.pack(">I", len(daten)) + art + daten + struct.pack(">I", zlib.crc32(art + daten) & 0xFFFFFFFF)


def png_bytes(farbe: int = 120, breite: int = 8, hoehe: int = 8) -> bytes:
    """Ein kleines, ganzes Graustufen-PNG (ohne Fremdbibliothek)."""
    kopf = struct.pack(">IIBBBBB", breite, hoehe, 8, 0, 0, 0, 0)
    zeilen = b"".join(b"\x00" + bytes([farbe]) * breite for _ in range(hoehe))
    return (b"\x89PNG\r\n\x1a\n" + _block(b"IHDR", kopf) + _block(b"IDAT", zlib.compress(zeilen)) + _block(b"IEND", b""))


class PngFehlerTests(unittest.TestCase):

    def test_ein_ganzes_png_hat_keinen_befund(self) -> None:
        self.assertEqual("", wz.png_fehler(png_bytes()))

    def test_532_zufallsbytes_haben_keine_png_kennung(self) -> None:
        """Der Fall aus dem Trackmania-Dump: 532 Bytes, die mit etwas anderem als der PNG-Kennung beginnen."""
        daten = bytes(range(256)) * 2 + bytes(20)
        self.assertEqual(532, len(daten))
        self.assertEqual(wz.PNG_KOPF_FEHLT, wz.png_fehler(daten))
        self.assertEqual(wz.PNG_KOPF_FEHLT, wz.png_fehler(b""))

    def test_ein_mitten_im_block_abgeschnittenes_png_hat_eine_defekte_kette(self) -> None:
        ganz = png_bytes()
        nach_ihdr = 8 + 12 + 13                  # Kennung + IHDR-Block (12 Bytes Rahmen, 13 Bytes Inhalt)
        self.assertEqual(wz.PNG_KETTE_DEFEKT, wz.png_fehler(ganz[:nach_ihdr + 14]), "mitten im IDAT-Block")

    def test_ein_verfaelschtes_byte_bricht_die_pruefsumme(self) -> None:
        ganz = bytearray(png_bytes())
        ganz[len(ganz) - 20] ^= 0xFF            # im IDAT-Block
        self.assertEqual(wz.PNG_KETTE_DEFEKT, wz.png_fehler(bytes(ganz)))

    def test_ohne_iend_oder_mit_resten_dahinter_ist_das_ende_defekt(self) -> None:
        ganz = png_bytes()
        self.assertEqual(wz.PNG_ENDE_DEFEKT, wz.png_fehler(ganz[:-12]), "IEND fehlt, abgeschnitten an einer Blockgrenze")
        self.assertEqual(wz.PNG_ENDE_DEFEKT, wz.png_fehler(ganz + b"rest"), "Bytes nach IEND")

    def test_die_pruefung_liest_nur_und_wirft_nie(self) -> None:
        for daten in (b"\x89PNG\r\n\x1a\n", b"\x89PNG\r\n\x1a\n" + b"\xff" * 11, b"\x89PNG\r\n\x1a\n" + b"\xff" * 40, bytes(3)):
            self.assertIn(wz.png_fehler(daten), (wz.PNG_KOPF_FEHLT, wz.PNG_KETTE_DEFEKT, wz.PNG_ENDE_DEFEKT))


class BilderBefundeTests(unittest.TestCase):

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.ordner = tmp.name
        self.sys = os.path.join(self.ordner, "sce_sys")
        os.makedirs(self.sys)

    def _schreiben(self, name: str, daten: bytes) -> None:
        Path(self.sys, name).write_bytes(daten)

    def test_nur_die_beschaedigten_bilder_werden_gemeldet_mit_groesse_und_art(self) -> None:
        self._schreiben("icon0.png", png_bytes())
        self._schreiben("pic0.png", png_bytes(40))
        self._schreiben("pic2.png", bytes(range(256)) * 2 + bytes(20))
        self.assertEqual([("pic2.png", 532, wz.PNG_KOPF_FEHLT)], wz.bilder_befunde(self.ordner))

    def test_mehrere_befunde_stehen_in_der_festen_reihenfolge(self) -> None:
        ganz = png_bytes()
        self._schreiben("pic1.png", ganz[:30])
        self._schreiben("icon0.png", b"kein png")
        self.assertEqual(["icon0.png", "pic1.png"], [b[0] for b in wz.bilder_befunde(self.ordner)])

    def test_dds_und_andere_dateien_zaehlen_nicht(self) -> None:
        self._schreiben("pic2.dds", b"\x00" * 100)
        self._schreiben("param.json", b"{}")
        self.assertEqual([], wz.bilder_befunde(self.ordner))

    def test_fehlende_bilder_und_ein_ordner_ohne_sce_sys_sind_kein_befund(self) -> None:
        self.assertEqual([], wz.bilder_befunde(self.ordner))
        self.assertEqual([], wz.bilder_befunde(os.path.join(self.ordner, "gibt_es_nicht")))

    def test_ein_unlesbares_bild_haelt_die_pruefung_nicht_auf(self) -> None:
        os.makedirs(os.path.join(self.sys, "pic0.png"))        # ein Ordner statt einer Datei
        self._schreiben("pic2.png", b"kein png")
        self.assertEqual(["pic2.png"], [b[0] for b in wz.bilder_befunde(self.ordner)])

    def test_der_spielordner_bleibt_unveraendert(self) -> None:
        self._schreiben("pic2.png", b"kein png")
        vorher = {p.name: p.read_bytes() for p in Path(self.sys).iterdir()}
        wz.bilder_befunde(self.ordner)
        self.assertEqual(vorher, {p.name: p.read_bytes() for p in Path(self.sys).iterdir()})

    def test_die_schreibweise_des_namens_zaehlt_nicht(self) -> None:
        """Gesamtpruefung 23.11.2026: Unter Linux/macOS blieb ``PIC2.PNG`` ungeprueft (gesucht wurde nur ``pic2.png``)."""
        self._schreiben("PIC2.PNG", b"kein png")
        self.assertEqual([("pic2.png", 8, wz.PNG_KOPF_FEHLT)], wz.bilder_befunde(self.ordner))

    def test_ein_zu_grosses_bild_wird_nicht_beurteilt(self) -> None:
        self._schreiben("pic0.png", b"x" * 64)
        with mock.patch.object(wz, "BILD_HOECHSTENS", 32):
            self.assertEqual([], wz.bilder_befunde(self.ordner))
        self.assertEqual(["pic0.png"], [b[0] for b in wz.bilder_befunde(self.ordner)], "Gegenprobe: unter der Grenze gemeldet")

    def test_ein_block_ueber_der_grenze_der_norm_ist_defekt(self) -> None:
        daten = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 0x80000000) + b"IHDR" + bytes(20)
        self.assertEqual(wz.PNG_KETTE_DEFEKT, wz.png_fehler(daten))


class AbbildQuelleTests(unittest.TestCase):
    """Gesamtpruefung 23.11.2026: Die Pruefung lief nur bei einem Spielordner; ein Abbild als Quelle (``.ffpkg``, ``.exfat``, ``.ffpfs``,
    ``.ffpfsc`` in jeder Bauform) packte Forge mit demselben kaputten Bild ohne Hinweis. Jetzt liest ``programm_sdk`` die Bilder aus
    ``sce_sys``, ohne das Abbild zu entpacken."""

    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))
        from mkpfs import consts
        from mkpfs.exfat_writer import iter_exfat_image
        from mkpfs.pfs import build_pfs, build_pfs_stream_single_file
        from ps5_validator.utils import ufs2_schreiber as w

        cls.tmp = tempfile.mkdtemp(prefix="png_abbild_")
        ordner = os.path.join(cls.tmp, "spiel")
        inhalt = {"eboot.bin": b"\x7fELF" + bytes(5000), "sce_sys/param.json": b"{}", "sce_sys/icon0.png": png_bytes(),
                  "sce_sys/pic0.png": png_bytes(40), "sce_sys/pic2.png": bytes(range(256)) * 2 + bytes(20),
                  "sce_sys/pic2.dds": bytes(300), "data/a/x.bin": bytes(70_000), "Media/m.bin": bytes(30_000)}
        for rel, daten in inhalt.items():
            voll = os.path.join(ordner, *rel.split("/"))
            os.makedirs(os.path.dirname(voll), exist_ok=True)
            Path(voll).write_bytes(daten)

        def flach(ziel: str, komprimiert: bool) -> None:
            build_pfs(source_root=Path(ordner), output_path=Path(ziel), block_size=65536, pfs_version=consts.PFS_VERSION_PS5,
                      inode_bits=32, case_insensitive=True, signed=False, compress=komprimiert, threshold_gain=0, cpu_count=1,
                      zlib_level=6, dry_run=False, verbose=False)

        def huelle(innen: str, ziel: str) -> None:
            build_pfs_stream_single_file(source_file=Path(innen), output_path=Path(ziel), block_size=65536,
                                         pfs_version=consts.PFS_VERSION_PS5, case_insensitive=True, zlib_level=6, threshold_gain=0,
                                         min_file_gain=0, min_compress_size=0, cpu_count=1, compress=True)

        a = cls.abbilder = {}
        a["exfat"] = os.path.join(cls.tmp, "s.exfat")
        with open(a["exfat"], "wb") as fh:
            for stueck in iter_exfat_image(Path(ordner)):
                fh.write(stueck)
        a["ffpkg"] = os.path.join(cls.tmp, "s.ffpkg")
        eintraege = [(rel, len(d), (lambda d=d: iter([d]))) for rel, d in inhalt.items()]
        w.planen(eintraege, (), profil=w.Ufs2Profil(65536, 65536, 4096, 0, 262144)).schreiben(a["ffpkg"])
        a["flach_roh"] = os.path.join(cls.tmp, "s.ffpfs")
        flach(a["flach_roh"], False)
        a["flach_pfsc"] = os.path.join(cls.tmp, "s_flach.ffpfsc")
        flach(a["flach_pfsc"], True)
        a["huelle_exfat"] = os.path.join(cls.tmp, "s_exfat.ffpfsc")
        huelle(a["exfat"], a["huelle_exfat"])
        a["huelle_ffpkg"] = os.path.join(cls.tmp, "s_ffpkg.ffpfsc")
        huelle(a["ffpkg"], a["huelle_ffpkg"])

    @classmethod
    def tearDownClass(cls) -> None:
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_jede_bauform_meldet_das_kaputte_bild(self) -> None:
        for form, pfad in self.abbilder.items():
            with self.subTest(bauform=form):
                self.assertEqual([("pic2.png", 532, wz.PNG_KOPF_FEHLT)], wz.bilder_befunde(pfad))

    def test_die_ganzen_bilder_kommen_unveraendert_aus_dem_abbild(self) -> None:
        from ps5_validator.utils import programm_sdk as ps
        for form, pfad in self.abbilder.items():
            with self.subTest(bauform=form):
                bilder = ps.sce_sys_dateien_in_abbild(pfad, wz.SCE_SYS_BILDER)
                self.assertEqual({"icon0.png": png_bytes(), "pic0.png": png_bytes(40),
                                  "pic2.png": bytes(range(256)) * 2 + bytes(20)}, bilder)

    def test_ein_fremdes_oder_fehlendes_abbild_wirft_nie(self) -> None:
        kaputt = os.path.join(self.tmp, "kaputt.ffpkg")
        Path(kaputt).write_bytes(os.urandom(200_000))
        self.assertEqual([], wz.bilder_befunde(kaputt))
        self.assertEqual([], wz.bilder_befunde(os.path.join(self.tmp, "fehlt.exfat")))


class TexteTests(unittest.TestCase):

    def test_jede_art_hat_ihren_text_in_allen_fuenf_sprachen(self) -> None:
        for art in (wz.PNG_KOPF_FEHLT, wz.PNG_KETTE_DEFEKT, wz.PNG_ENDE_DEFEKT):
            eintrag = STRINGS["ps5pkg.bild_grund_" + art]
            for sprache in ("de", "en", "es", "it", "fr"):
                self.assertTrue(eintrag.get(sprache), "%s fehlt in %s" % (art, sprache))

    def test_die_warnzeile_hat_ihre_platzhalter_in_jeder_sprache(self) -> None:
        for sprache, text in STRINGS["ps5pkg.bild_kaputt"].items():
            for platzhalter in ("{datei}", "{grund}", "{groesse}"):
                self.assertIn(platzhalter, text, "%s: %s fehlt" % (sprache, platzhalter))


if __name__ == "__main__":
    unittest.main()
