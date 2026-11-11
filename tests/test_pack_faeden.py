"""Obergrenze der Kompressionsfaeden beim Packen (gemessen 10.11.2026).

Messung an einem echten Dump (12,4 GB, 20 Kerne, Quelle und Ziel auf NVMe, eingebettetes MkPFS mit den Schaltern von
Aufgabe 1, Stufe 9): 4 Faeden 97,5 s, 8 Faeden 63,2 s, 12/16/20 Faeden 62,8/70,0/67,9 s - ab 8 wird es nicht schneller.
Die Obergrenze 4 des Profils ``pack_folder`` (exFAT-Bauform, Faeden im Programmprozess) stieg deshalb auf 8. Die Profile mit
Prozesspool (``pack_file``, ``ffpkg_to_ffpfsc``) blieben bei 4: Dafuer gibt es keine Messung.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP

GIB = 1024 ** 3


def _profil(modus: str, groesse_gib: float, eingestellt: int, stufe: int = 9) -> dict:
    """``_resolve_pack_profile`` ohne Fenster; ``eingestellt`` ist die Worker-Zahl der Einstellung."""
    gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
    gui.zstd_level = stufe
    gui._get_worker_count = lambda _default: eingestellt  # type: ignore[method-assign]
    return APP.PS5ConverterGUI._resolve_pack_profile(gui, modus, int(groesse_gib * GIB))


class OrdnerProfilNutztAchtFaeden(unittest.TestCase):
    def test_die_tabelle_nennt_acht(self) -> None:
        self.assertEqual(8, APP.PACK_PROFILE_MATRIX["pack_folder"]["hard_cap"])

    def test_grosser_rechner_bekommt_acht_statt_vier(self) -> None:
        """Die Einstellung 10 (halbe Kernzahl bei 20 Kernen) ergab bis v1.9.95 vier Faeden."""
        self.assertEqual(8, _profil("pack_folder", 12, 10)["cpu"])
        self.assertEqual(8, _profil("pack_folder", 12, 16)["cpu"])

    def test_ein_kern_bleibt_frei(self) -> None:
        """``min(hard_cap, eingestellt - 1)`` gilt weiter - kleine Rechner merken nichts."""
        self.assertEqual(3, _profil("pack_folder", 12, 4)["cpu"])
        self.assertEqual(1, _profil("pack_folder", 12, 2)["cpu"])
        self.assertEqual(1, _profil("pack_folder", 12, 1)["cpu"])

    def test_niedrige_stufe_nimmt_weniger_faeden(self) -> None:
        """Die Stufe skaliert die Obergrenze (Stufe 1 = halb, Stufe 9 = voll) - unveraendert."""
        self.assertEqual(8, _profil("pack_folder", 12, 16, stufe=9)["cpu"])
        self.assertEqual(4, _profil("pack_folder", 12, 16, stufe=1)["cpu"])

    def test_grosse_quellen_bleiben_gedrosselt_aber_hoeher_als_frueher(self) -> None:
        self.assertEqual(8, _profil("pack_folder", 60, 16)["cpu"])
        self.assertEqual(6, _profil("pack_folder", 100, 16)["cpu"])   # ab 90 GiB / 120 GB; vorher 3
        self.assertEqual(6, _profil("pack_folder", 130, 16)["cpu"])
        self.assertEqual(4, _profil("pack_folder", 170, 16)["cpu"])   # ab 160 GiB; vorher 2
        self.assertEqual(4, _profil("pack_folder", 230, 16)["cpu"])


class ProzesspoolProfileBleibenBeiVier(unittest.TestCase):
    """Gegenprobe: Hier gab es keine Messung, also aendert sich nichts."""

    def test_obergrenze_bleibt_vier(self) -> None:
        for modus in ("pack_file", "ffpkg_to_ffpfsc"):
            with self.subTest(modus=modus):
                self.assertEqual(4, APP.PACK_PROFILE_MATRIX[modus]["hard_cap"])
                self.assertEqual(4, _profil(modus, 12, 16)["cpu"])

    def test_grosse_quellen_bleiben_bei_zwei_bzw_drei(self) -> None:
        self.assertEqual(3, _profil("pack_file", 100, 16)["cpu"])     # ab 80 GB: 3
        self.assertEqual(2, _profil("pack_file", 170, 16)["cpu"])     # ab 160 GB: 2
        self.assertEqual(3, _profil("ffpkg_to_ffpfsc", 100, 16)["cpu"])   # ab 90 GB: 3
        self.assertEqual(2, _profil("ffpkg_to_ffpfsc", 190, 16)["cpu"])   # ab 180 GB: 2


class HinweistextRichtetSichNachDerTabelle(unittest.TestCase):
    def test_wirksames_maximum_folgt_der_groessten_obergrenze(self) -> None:
        self.assertEqual(8, APP.PACK_HARD_CAP_MAX)
        self.assertEqual(APP.PACK_HARD_CAP_MAX + 1, APP.WORKER_WIRKSAM_MAX)


if __name__ == "__main__":
    unittest.main()
