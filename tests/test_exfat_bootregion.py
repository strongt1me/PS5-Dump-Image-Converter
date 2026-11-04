# -*- coding: utf-8 -*-
"""Der exFAT-Validator beanstandet einen zerstoerten Anfang des Abbilds.

Matrixlauf vom 04.11.2026 (Aufgabe 8, schaerfere Negativproben an einem frisch
gebauten Abbild): Ein auf Null gesetzter Bootsektor, ein verfaelschter
Pruefsummen-Sektor und eine Textdatei mit der Endung ``.exfat`` endeten alle
mit "BESTANDEN" (``WARNING`` bzw. ``OK``, Rueckgabewert 0).

* Fehlt der exFAT-Name im Bootsektor, ist es kein exFAT-Abbild (Spezifikation:
  ``FileSystemName`` = "EXFAT   ") - das ist ein Schaden, kein Hinweis.
* Die Sektoren 0-10 der Boot-Region ergeben eine 32-Bit-Pruefsumme; Sektor 11
  wiederholt sie. Gemessen an 20 fremden und einem eigenen Abbild: alle
  bestehen. Die Sicherungsregion (Sektoren 12-23) ist bei 19 der 20 fremden
  leer und wird deshalb **nicht** verglichen (eine Gegenprobe haelt das fest).

Nicht erkennbar bleibt ein Schaden in den Nutzdaten: exFAT traegt dafuer keine
Pruefwerte. Auch das steht hier als Gegenprobe.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("exfat_bootregion")


def _mkpfs_da() -> bool:
    try:
        import mkpfs.exfat_writer  # noqa: F401
    except ImportError:
        return False
    return True


@unittest.skipUnless(_mkpfs_da(), "mkpfs nicht importierbar")
class BootRegionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from mkpfs.exfat_writer import write_exfat_image
        cls.arbeit = tempfile.mkdtemp(prefix="ps5conv_exfat_boot_")
        dump = os.path.join(cls.arbeit, "dump")
        os.makedirs(os.path.join(dump, "sce_sys"))
        with io.open(os.path.join(dump, "sce_sys", "param.json"), "wb") as fh:
            fh.write(b'{"titleId":"PPSA99999"}')
        with io.open(os.path.join(dump, "eboot.bin"), "wb") as fh:
            fh.write(b"ELF" + bytes(300_000))
        cls.heil = os.path.join(cls.arbeit, "spiel.exfat")
        write_exfat_image(Path(dump), Path(cls.heil))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.arbeit, ignore_errors=True)

    def _kopie(self, name: str, aenderung) -> str:
        ziel = os.path.join(self.arbeit, name)
        shutil.copyfile(self.heil, ziel)
        with open(ziel, "r+b") as fh:
            aenderung(fh)
        return ziel

    def _pruefen(self, pfad):
        from ps5_validator.modules.extfat_validator import ExtfatValidator
        return ExtfatValidator().validate(str(pfad))

    def test_das_eigene_abbild_besteht(self):
        ergebnis = self._pruefen(self.heil)
        self.assertEqual("OK", ergebnis.status, ergebnis.errors)
        self.assertEqual("in Ordnung", ergebnis.summary["boot_checksum"])

    def test_ein_verfaelschter_pruefsummen_sektor_wird_gefunden(self):
        def aendern(fh):
            fh.seek(11 * 512)
            fh.write(b"\xaa" * 512)
        ergebnis = self._pruefen(self._kopie("summe.exfat", aendern))
        self.assertEqual("CORRUPTED", ergebnis.status, ergebnis.errors)
        self.assertTrue(any("Prüfsumme der Boot-Region" in e for e in ergebnis.errors), ergebnis.errors)
        self.assertEqual({}, ergebnis.hashes, "Das Urteil steht - gelesen wird nicht mehr.")

    def test_ein_byte_in_der_erweiterten_boot_region_wird_gefunden(self):
        def aendern(fh):
            fh.seek(3 * 512 + 100)
            fh.write(b"\x5a")
        ergebnis = self._pruefen(self._kopie("sektor3.exfat", aendern))
        self.assertEqual("CORRUPTED", ergebnis.status, ergebnis.errors)

    def test_die_veraenderlichen_felder_zaehlen_nicht_mit(self):
        """VolumeFlags (106, 107) und PercentInUse (112) aendern sich im Betrieb."""
        def aendern(fh):
            for stelle, wert in ((106, b"\x02"), (107, b"\x01"), (112, b"\x37")):
                fh.seek(stelle)
                fh.write(wert)
        ergebnis = self._pruefen(self._kopie("flags.exfat", aendern))
        self.assertEqual("OK", ergebnis.status, ergebnis.errors)

    def test_ein_zerstoerter_bootsektor_ist_kein_exfat(self):
        def aendern(fh):
            fh.seek(0)
            fh.write(b"\x00" * 4096)
        ergebnis = self._pruefen(self._kopie("kopf.exfat", aendern))
        self.assertEqual("CORRUPTED", ergebnis.status, ergebnis.errors)
        self.assertTrue(any("Kein exFAT-OEM-Name" in e for e in ergebnis.errors), ergebnis.errors)
        self.assertFalse(ergebnis.summary["exfat_detected"])

    def test_eine_textdatei_und_ein_stummel_sind_kein_exfat(self):
        text = os.path.join(self.arbeit, "text.exfat")
        Path(text).write_text("das ist kein Abbild\n" * 500, encoding="utf-8")
        self.assertEqual("CORRUPTED", self._pruefen(text).status)
        stummel = os.path.join(self.arbeit, "stummel.exfat")
        Path(stummel).write_bytes(b"EXFAT")
        ergebnis = self._pruefen(stummel)
        self.assertEqual("CORRUPTED", ergebnis.status)
        self.assertTrue(any("zu klein" in e for e in ergebnis.errors), ergebnis.errors)

    def test_gegenprobe_die_sicherungsregion_wird_nicht_verglichen(self):
        """Fremde Abbilder lassen sie leer - ein Vergleich wuerde gesunde beanstanden."""
        def aendern(fh):
            fh.seek(12 * 512)
            fh.write(b"\x00" * (12 * 512))
        ergebnis = self._pruefen(self._kopie("ohne_sicherung.exfat", aendern))
        self.assertEqual("OK", ergebnis.status, ergebnis.errors)

    def test_grenze_ein_schaden_in_den_nutzdaten_ist_nicht_erkennbar(self):
        groesse = os.path.getsize(self.heil)

        def aendern(fh):
            fh.seek(groesse - 4096)
            fh.write(b"\xff" * 2048)
        ergebnis = self._pruefen(self._kopie("daten.exfat", aendern))
        self.assertEqual("OK", ergebnis.status,
                         "exFAT hat fuer die Nutzdaten keine Pruefwerte - sieht der Validator hier "
                         "etwas, ist die Grenze verschoben und der Handbuchsatz zu ueberarbeiten.")

    def test_die_texte_gibt_es_in_allen_sprachen(self):
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("validator.exfat_boot_pruefsumme", "validator.exfat_boot_pruefsumme_ok"):
            for sprache in ("de", "en", "es", "it", "fr"):
                self.assertTrue(STRINGS[schluessel].get(sprache), (schluessel, sprache))
        for sprache in ("de", "en", "es", "it", "fr"):
            vorlage = STRINGS["validator.exfat_boot_pruefsumme"][sprache]
            self.assertIn("{soll}", vorlage)
            self.assertIn("{ist}", vorlage)


if __name__ == "__main__":
    unittest.main()
