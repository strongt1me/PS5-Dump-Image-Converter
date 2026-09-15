# -*- coding: utf-8 -*-
"""Das Packwerk muss laden - und darf nicht verdeckt werden koennen.

Fehlerbericht 15.09.2026 (v1.9.22): Kein Packlauf kam mehr zustande.

    Unable to select compression backend 'zlib-ng': zlib-ng backend is not
    available (cannot import name 'zlib_ng' from 'zlib_ng'
    (...\\AppData\\Roaming\\PS5ImageConverterPro\\runtime_site_packages\\
     zlib_ng\\__init__.py))
    [WARNUNG] mkpfs beendet mit Exit-Code 2

Drei unabhaengige Defekte, jeder haette es allein verhindert:

* Der Rueckfall-Paketordner lag mit einem ``zlib_ng`` fuer Python 3.11 auf
  ``sys.path[0]`` und verdeckte die mitgelieferte Fassung - die
  Programmdatei laeuft auf 3.14.
* Die Festlegung auf ``zlib-ng`` kannte keinen Rueckfall: MkPFS nimmt
  ``--compression-backend`` woertlich und gibt Rueckgabewert 2 zurueck.
* Die Pruefung, die das haette melden koennen, stand hinter einem
  ``return True`` und lief nie mit.
"""
from __future__ import annotations

import importlib.util as _ilu
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault(
    "PS5CONV_KONFIGORDNER", tempfile.mkdtemp(prefix="zlibng_kfg_"))

from ps5_validator.utils import werkzeuge_bereitstellen as wb  # noqa: E402

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")


def _lauf(praefix: str, **zusatz):
    """Ruft laufzeitpakete_sicherstellen mit einem frischen Konfigordner."""
    kfg = tempfile.mkdtemp(prefix=praefix)
    ok = wb.laufzeitpakete_sicherstellen(
        kfg,
        pip_kommando=lambda *a, **k: ["pip"],
        prozess_starten=lambda *a, **k: (0, ""),
        **zusatz)
    return kfg, ok


class LaufzeitordnerTests(unittest.TestCase):
    """Der Rueckfall-Paketordner darf nie die mitgelieferten Module verdecken."""

    def test_der_ordner_traegt_die_python_kennung(self) -> None:
        kfg, ok = _lauf("zlibng_kennung_")
        self.assertTrue(ok)
        eintraege = os.listdir(kfg)
        kennung = sys.implementation.cache_tag or "py"
        self.assertIn(
            "runtime_site_packages_%s" % kennung, eintraege,
            "Ohne Python-Kennung im Namen bleibt ein Ordner aus einer "
            "frueheren Fassung liegen und verdeckt die mitgelieferten "
            "Module: %r" % (eintraege,))

    def test_der_ordner_steht_hinten_im_suchpfad(self) -> None:
        """Angehaengt, nicht vorangestellt - sonst gewinnt er gegen die EXE."""
        kfg, _ = _lauf("zlibng_pfad_")
        treffer = [i for i, p in enumerate(sys.path)
                   if os.path.normcase(kfg) in os.path.normcase(p)]
        self.assertTrue(treffer, "Der Ordner steht gar nicht im Suchpfad.")
        self.assertNotIn(
            0, treffer,
            "Der Rueckfallordner steht auf Platz 0 und verdeckt damit die "
            "Module der Programmdatei - genau der Fehler vom 15.09.2026.")

    def test_die_zlib_ng_pruefung_ist_erreichbar(self) -> None:
        """Sie stand hinter einem ``return True`` und lief nie mit."""
        gemeldet: list[str] = []
        _lauf("zlibng_melde_", melden=gemeldet.append)
        self.assertTrue(
            gemeldet,
            "Die zlib_ng-Pruefung meldet nichts - sie ist wieder toter Code.")


class BackendRueckfallTests(unittest.TestCase):
    """Die Festlegung auf zlib-ng darf keinen Lauf mehr zum Absturz bringen."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as haupt
        cls.haupt = haupt

    def _backend_aus(self, args: list[str]) -> str:
        self.assertIn("--compression-backend", args)
        return args[args.index("--compression-backend") + 1]

    def _mit_ladbar(self, antwort: bool) -> list[str]:
        echt = self.haupt._backend_ladbar
        self.haupt._backend_ladbar = lambda _b: antwort
        try:
            return self.haupt.mkpfs_argumente_mit_backend(
                ["pack", "folder", "quelle", "ziel"])
        finally:
            self.haupt._backend_ladbar = echt

    def test_ohne_ladbares_zlib_ng_wird_auf_zlib_zurueckgefallen(self) -> None:
        self.assertEqual(
            "zlib", self._backend_aus(self._mit_ladbar(False)),
            "Ohne ladbares zlib-ng muss auf zlib zurueckgefallen werden - "
            "sonst bricht mkpfs mit Rueckgabewert 2 ab.")

    def test_mit_ladbarem_zlib_ng_bleibt_es_dabei(self) -> None:
        self.assertEqual("zlib-ng", self._backend_aus(self._mit_ladbar(True)))

    def test_andere_aufrufe_bleiben_unberuehrt(self) -> None:
        """Nur ``pack folder``/``pack file`` kennen den Schalter."""
        for args in (["unpack", "datei"], ["pack", "raw", "q", "z"]):
            self.assertEqual(
                args, self.haupt.mkpfs_argumente_mit_backend(list(args)))

    def test_ein_mitgebrachter_schalter_gewinnt(self) -> None:
        args = ["pack", "folder", "--compression-backend", "isal", "q", "z"]
        self.assertEqual(args,
                         self.haupt.mkpfs_argumente_mit_backend(list(args)))

    @unittest.skipUnless(_ilu.find_spec("zlib_ng"),
                         "zlib_ng liegt auf diesem Rechner nicht")
    def test_die_pruefung_misst_wirklich_den_import(self) -> None:
        """Gegenprobe: hier liegt ein passendes zlib_ng, also muss es laden."""
        self.assertTrue(self.haupt._backend_ladbar("zlib-ng"))

    def test_andere_rechenwerke_werden_durchgelassen(self) -> None:
        self.assertTrue(self.haupt._backend_ladbar("zlib"))

    def test_der_doktor_prueft_das_packwerk_wirklich(self) -> None:
        """Er meldete "Pflichtmodule vollstaendig", waehrend nichts ging."""
        quelle = open(HAUPTDATEI, encoding="utf-8").read()
        self.assertIn(
            "Packwerk zlib-ng", quelle,
            "Der Doktor sieht nur nach, ob Module da sind - nicht, ob das "
            "Packwerk wirklich laedt.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
