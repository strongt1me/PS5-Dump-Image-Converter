# -*- coding: utf-8 -*-
"""Eine Quelle muss nach ihrer Endung auch ein Abbild sein koennen.

Matrixlauf vom 04.11.2026 (Aufgabe 3): Eine **leere** und eine **Textdatei** mit
der Endung ``.exfat`` wurden "erfolgreich" in einen Container verpackt - Rueckgabe 0,
Abschlusspruefung "MkPFS-Struktur gueltig", ein 0,45-MB-Ergebnis. ``mkpfs pack file``
bettet jede Datei ein. Bei einer leeren oder falschen ``.ffpkg`` kam zwar ein Fehler, aber
erst aus UFS2Tool, und ein leerer Zielordner blieb liegen.

Geprueft werden nur die ersten Bytes (PFS-Kopf, exFAT-Name, UFS2-Magic). Gemessen an 4
fremden ``.ffpfsc``, 20 fremden ``.exfat``, der ``.ffpkg`` von E: und den eigenen Abbildern:
alle bestehen, jede leere oder zerstoerte Probe wird erkannt.

Ausgenommen ist Aufgabe 8 (Validator): Er muss auch ein kaputtes Abbild oeffnen koennen.
"""
from __future__ import annotations

import io
import os
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("quelle_kennung")

from ps5_validator.utils import abbild_pruefen              # noqa: E402
from ps5_validator.utils.i18n import STRINGS, translate     # noqa: E402


def _stand(sprache: str = "de") -> abbild_pruefen.Pruefstand:
    return abbild_pruefen.Pruefstand(text=lambda schluessel, **w: translate(sprache, schluessel).format(**w))


class KennungTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.arbeit = tempfile.mkdtemp(prefix="ps5conv_kennung_")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.arbeit, ignore_errors=True)

    def _datei(self, name: str, inhalt: bytes) -> str:
        pfad = os.path.join(self.arbeit, name)
        with io.open(pfad, "wb") as fh:
            fh.write(inhalt)
        return pfad

    # --- gueltige Anfaenge -------------------------------------------------------------------------
    def test_gueltige_anfaenge_bestehen(self):
        exfat = self._datei("g.exfat", b"\xeb\x76\x90EXFAT   " + bytes(600))
        pfs = self._datei("g.ffpfsc", struct.pack("<qq", 2, 0x1332A0B) + bytes(100))
        pfs1 = self._datei("g.ffpfs", struct.pack("<qq", 1, 0x1332A0B) + bytes(100))
        ufs = bytearray(65536 + 2048)
        struct.pack_into("<I", ufs, 65536 + 1372, 0x19540119)
        ffpkg = self._datei("g.ffpkg", bytes(ufs))
        stand = _stand()
        for pfad in (exfat, pfs, pfs1, ffpkg):
            with self.subTest(datei=os.path.basename(pfad)):
                self.assertEqual("", stand._abbild_kennung_problem(pfad))

    # --- leer, Text, zerstoert -----------------------------------------------------------------------
    def test_eine_leere_datei_ist_kein_abbild(self):
        stand = _stand()
        for endung, art in ((".exfat", "exFAT"), (".ffpkg", "ffpkg"), (".ffpfsc", "ffpfs/ffpfsc"),
                            (".ffpfs", "ffpfs/ffpfsc")):
            with self.subTest(endung=endung):
                text = stand._abbild_kennung_problem(self._datei("leer" + endung, b""))
                self.assertIn("leer", text)
                self.assertIn(art, text)

    def test_eine_textdatei_ist_kein_abbild(self):
        stand = _stand()
        for endung in (".exfat", ".ffpkg", ".ffpfsc", ".ffpfs"):
            with self.subTest(endung=endung):
                text = stand._abbild_kennung_problem(
                    self._datei("text" + endung, ("das ist kein Abbild\n" * 4000).encode()))
                self.assertIn("kein gültiges", text)

    def test_ein_zerstoerter_anfang_ist_kein_abbild(self):
        gut = b"\xeb\x76\x90EXFAT   " + bytes(600)
        kaputt = self._datei("kopf.exfat", b"\x00" * len(gut))
        self.assertIn("kein gültiges", _stand()._abbild_kennung_problem(kaputt))

    def test_ein_abgeschnittenes_exfat_wird_vor_dem_bau_abgelehnt(self):
        """Eine abgebrochene Kopie behaelt ihren Anfang - der Bootsektor nennt die Groesse, die Datei ist kuerzer."""
        boot = bytearray(512)
        boot[0:3] = b"\xeb\x76\x90"
        boot[3:11] = b"EXFAT   "
        struct.pack_into("<Q", boot, 0x48, 4096)          # VolumeLength: 4096 Sektoren
        boot[0x6C] = 9                                     # 512 Byte je Sektor -> 2 097 152 Bytes
        stand = _stand()
        voll = self._datei("voll.exfat", bytes(boot) + bytes(2_097_152 - 512))
        kurz = self._datei("kurz.exfat", bytes(boot) + bytes(1_000_000))
        self.assertEqual("", stand._abbild_kennung_problem(voll))
        text = stand._abbild_kennung_problem(kurz)
        self.assertIn("abgeschnitten", text)
        self.assertIn("2.097.152", text)
        self.assertIn("1.000.512", text)

    def test_eine_abgeschnittene_ffpkg_wird_vor_dem_bau_abgelehnt(self):
        """Matrixlauf 04.11.2026: Aufgabe 4 machte aus einer auf 60 % gekuerzten .ffpkg EINE Datei
        (31 MB statt 191 Dateien) und meldete Erfolg - die Liste der erwarteten Dateien kam aus dem
        beschaedigten Abbild selbst. Der Superblock nennt die Groesse (fs_size * fs_fsize)."""
        def abbild(laenge: int) -> bytes:
            sb = bytearray(laenge)
            struct.pack_into("<i", sb, 65536 + 52, 65536)          # fs_fsize
            struct.pack_into("<q", sb, 65536 + 1080, 100)          # fs_size: 100 Fragmente
            struct.pack_into("<I", sb, 65536 + 1372, 0x19540119)   # fs_magic
            return bytes(sb)
        stand = _stand()
        voll = self._datei("voll.ffpkg", abbild(100 * 65536))
        laenger = self._datei("laenger.ffpkg", abbild(100 * 65536 + 4096))
        kurz = self._datei("kurz.ffpkg", abbild(60 * 65536))
        self.assertEqual("", stand._abbild_kennung_problem(voll))
        self.assertEqual("", stand._abbild_kennung_problem(laenger), "Angehaengte Bytes sind kein Fehler.")
        text = stand._abbild_kennung_problem(kurz)
        self.assertIn("abgeschnitten", text)
        self.assertIn("6.553.600", text)
        self.assertIn("3.932.160", text)

    def test_gegenprobe_andere_endungen_und_ordner_werden_nicht_beurteilt(self):
        stand = _stand()
        self.assertEqual("", stand._abbild_kennung_problem(self._datei("x.txt", b"")))
        self.assertEqual("", stand._abbild_kennung_problem(self.arbeit))
        self.assertEqual("", stand._abbild_kennung_problem(os.path.join(self.arbeit, "gibt_es_nicht.exfat")))

    # --- Einbindung in die Quellpruefung ---------------------------------------------------------------
    def test_die_aufgaben_mit_abbild_quellen_lehnen_eine_leere_datei_ab(self):
        stand = _stand()
        for modus, endung in (("pack_file", ".exfat"), ("unpack_to_exfat", ".ffpfsc"),
                              ("ffpkg_to_ffpfsc", ".ffpkg"), ("batch_convert", ".exfat"),
                              ("universal_convert", ".ffpkg")):
            with self.subTest(modus=modus):
                pfad = self._datei("a_" + modus + endung, b"")
                self.assertIn("leer", stand._validate_source_path(pfad, modus))

    def test_der_validator_darf_auch_ein_kaputtes_abbild_oeffnen(self):
        pfad = self._datei("kaputt.exfat", b"")
        self.assertEqual("", _stand()._validate_source_path(pfad, "dump_validator"))

    def test_ein_gueltiges_abbild_passiert_die_quellpruefung(self):
        pfad = self._datei("ok.exfat", b"\xeb\x76\x90EXFAT   " + bytes(600))
        self.assertEqual("", _stand()._validate_source_path(pfad, "pack_file"))

    # --- Texte -------------------------------------------------------------------------------------------
    def test_die_texte_gibt_es_in_allen_sprachen(self):
        for schluessel in ("srccheck.kein_abbild", "srccheck.kein_abbild_leer"):
            for sprache in ("de", "en", "es", "it", "fr"):
                text = STRINGS[schluessel][sprache]
                self.assertIn("{name}", text, (schluessel, sprache))
                self.assertIn("{art}", text, (schluessel, sprache))
                text.format(name="x", art="y")                   # keine losen Klammern

    # --- Einbindung im Programm (Quelltext) --------------------------------------------------------------
    def test_die_sammelkonvertierung_prueft_jede_quelle_einzeln(self):
        import ast
        with io.open(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py", encoding="utf-8") as fh:
            quelle = fh.read()
        baum = ast.parse(quelle)
        klasse = next(k for k in ast.walk(baum) if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        lauf = next(m for m in klasse.body if isinstance(m, ast.FunctionDef) and m.name == "_run_flexible_conversion")
        text = ast.unparse(lauf)
        i_kennung = text.find("_abbild_kennung_problem")
        i_grund = text.find("_conversion_block_reason")
        self.assertGreater(i_kennung, 0, "Die Schleife prueft die Kennung nicht.")
        self.assertLess(i_kennung, i_grund, "Erst die Kennung: sonst gilt eine leere Datei im Zielformat als 'Ueberspringer'.")
        vorab = next(m for m in klasse.body if isinstance(m, ast.FunctionDef) and m.name == "_validate_requested_conversion")
        self.assertIn("_abbild_kennung_problem", ast.unparse(vorab))


if __name__ == "__main__":
    unittest.main()
