# -*- coding: utf-8 -*-
"""Platz fuer FPKG -> .ffpkg (14.10.2026, LEGO Batman: 31,8 GB Paket, 110 GB entpackt, 124 GB Abbild).

Der entpackte Ordner und das Abbild lagen beide im Temp auf C:; 218 GB frei reichten nicht, UFS2Tool brach bei allen
drei Profilen mit "nicht genug Speicherplatz" ab - erst nach zehn Minuten Entpacken. Geprueft wird:

* Reicht der Temp nicht, baut das Programm auf dem Ziellaufwerk (wenn NTFS/ReFS und dort genug frei ist).
* Reicht beides nicht, bricht es vor dem Bau ab und nennt beide Zahlen.
* Das Entpacken prueft mit der echten entpackten Groesse, bevor es schreibt.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ffpkg_buehne_platz")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz      # noqa: E402

GB = 1024 ** 3


def _frei(belegung: dict):
    def disk_usage(pfad):
        for anfang, frei in belegung.items():
            if os.path.abspath(pfad).startswith(os.path.abspath(anfang)):
                return types.SimpleNamespace(total=frei * 2, used=frei, free=frei)
        return types.SimpleNamespace(total=1, used=0, free=10 ** 15)
    return disk_usage


class BuehneTests(unittest.TestCase):

    def setUp(self) -> None:
        self.ordner = Path(tempfile.mkdtemp(prefix="buehne_test_"))
        self.addCleanup(shutil.rmtree, self.ordner, True)
        self.temp = self.ordner / "temp"
        self.ziel = self.ordner / "ziel"
        self.temp.mkdir()
        self.ziel.mkdir()
        self.buehne = self.temp / "ps5conv_ffpkg_stage_x"
        self.buehne.mkdir()
        self.log: list[str] = []
        self.gui = types.SimpleNamespace(
            _FFPKG_ABBILD_FAKTOR=APP.PS5ConverterGUI._FFPKG_ABBILD_FAKTOR,
            _dateisystem_von=lambda _o: "NTFS",
            _append_to_log=self.log.append,
            _t=lambda schluessel, **w: "%s %s" % (schluessel, w))

    def _waehlen(self, frei_temp: int, frei_ziel: int, quelle: int = 110 * GB) -> str:
        with mock.patch.object(APP.shutil, "disk_usage",
                               side_effect=_frei({str(self.temp): frei_temp, str(self.ziel): frei_ziel})):
            return APP.PS5ConverterGUI._ffpkg_buehne_mit_platz(
                self.gui, str(self.buehne), str(self.ziel / "spiel.ffpkg"), quelle)

    def test_genug_im_temp_bleibt_im_temp(self) -> None:
        self.assertEqual(str(self.buehne), self._waehlen(300 * GB, 0))
        self.assertEqual([], self.log)

    def test_zu_wenig_im_temp_baut_auf_dem_ziellaufwerk(self) -> None:
        neu = self._waehlen(108 * GB, 213 * GB)          # die Zahlen des 14.10.2026
        self.assertTrue(neu.startswith(str(self.ziel)), neu)
        self.assertTrue(os.path.isdir(neu))
        self.assertFalse(self.buehne.exists(), "die leere Buehne im Temp wird weggeraeumt")
        self.assertTrue(any("ffpkg.buehne_auf_ziel" in z for z in self.log), self.log)

    def test_ohne_platz_nirgends_bricht_es_vor_dem_bau_ab(self) -> None:
        self.assertEqual("", self._waehlen(108 * GB, 100 * GB))
        self.assertTrue(any("ffpkg.zu_wenig_platz" in z for z in self.log), self.log)

    def test_ein_ziellaufwerk_mit_fat32_wird_nicht_genommen(self) -> None:
        self.gui._dateisystem_von = lambda _o: "FAT32"
        if sys.platform != "win32":
            self.skipTest("nur unter Windows wird das Dateisystem geprueft")
        self.assertEqual("", self._waehlen(108 * GB, 500 * GB))


class EntpackPlatzTests(unittest.TestCase):

    def test_zu_wenig_platz_fuer_das_entpackte_spiel_bricht_vor_dem_schreiben_ab(self) -> None:
        eintraege = [{"path": "gross.dat", "type": "file", "size": 110 * GB}]
        gesehen: list[int] = []

        def platz(gesamt: int) -> str:
            gesehen.append(gesamt)
            return "zu wenig Platz"

        with tempfile.TemporaryDirectory() as t, mock.patch.object(wz, "baum", return_value=eintraege), \
                mock.patch.object(wz, "laufen") as laufen:
            with self.assertRaises(wz.Fehler) as ctx:
                wz.extrahieren("werkzeug", "x.pkg", os.path.join(t, "ziel"), arbeitsordner=t, platz_pruefen=platz)
            laufen.assert_not_called()
            self.assertEqual([], [n for n in os.listdir(t) if n.startswith("ps5conv_teile_")])
        self.assertEqual([110 * GB], gesehen, "geprueft wird die echte entpackte Groesse")
        self.assertIn("zu wenig Platz", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
