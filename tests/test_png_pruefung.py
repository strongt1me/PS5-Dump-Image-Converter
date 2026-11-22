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
