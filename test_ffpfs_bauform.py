# -*- coding: utf-8 -*-
"""Die .ffpfs wird flach gebaut, nicht geschachtelt.

ShadowMount+ kennt zwei verschiedene Dinge (README 1.7alpha12, Z. 229-233
und 533):

* ``.ffpfsc`` ist ein **Container**. Darin liegt genau ein Abbild, und dessen
  Inhalt sind die Spieldateien. "nested supported image files are scanned".
* ``.ffpfs`` ist ein **Abbild-Spiel**, genau wie ``.ffpkg`` und ``.exfat``:
  "sce_sys/param.json must be at image root (no extra top-level folder)".

Das Programm hat beide gleich behandelt und jede .ffpfs zweistufig gebaut.
In der Wurzel lag dann eine einzige Datei - ``pfs_image.dat`` beim Ordnerweg,
``Spiel.exfat``/``Spiel.ffpkg`` bei den Abbildwegen. ShadowMount+ sucht dort
``sce_sys/param.json``, findet es nicht und meldet "missing/invalid
param.json"; das Spiel erscheint nicht in der Liste.

Am 05.09.2026 mit MkPFS gemessen, beide Bauformen aus demselben Ordner::

    flach (pack folder --raw --no-compress)   zweistufig (der alte Weg)
    /                                         /
    |-- sce_sys                               `-- pfs_image.dat
    |   `-- param.json
    |-- data.bin
    `-- eboot.bin
"""
import ast
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.0.0"))

HAUPTDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"


def _mkpfs_da() -> bool:
    try:
        import mkpfs  # noqa: F401
    except ImportError:
        return False
    return True


class _Quelltext(unittest.TestCase):
    """Gemeinsame Grundlage: der Quelltext als Baum."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()
        cls.baum = ast.parse(cls.quelle)

    def _methode(self, name: str) -> ast.FunctionDef:
        for k in ast.walk(self.baum):
            if isinstance(k, ast.FunctionDef) and k.name == name:
                return k
        self.fail("Methode %s gibt es nicht mehr" % name)

    def _mkpfs_aufrufe(self, knoten) -> list:
        """Alle _execute_mkpfs-Aufrufe mit ihrer Argumentliste als Text."""
        treffer = []
        for k in ast.walk(knoten):
            if (isinstance(k, ast.Call)
                    and getattr(k.func, "attr", "") == "_execute_mkpfs"
                    and k.args):
                treffer.append((k.lineno, ast.dump(k.args[0])))
        return treffer


class BauwegTests(_Quelltext):
    """Der Ordnerweg baut die .ffpfs in einem Zug."""

    def test_unkomprimiert_geht_nicht_mehr_ueber_ein_inneres_abbild(self):
        m = self._methode("_mode_pack_folder_mkpfs")
        # Der zweistufige Weg legt eine Zwischendatei an. Fuer .ffpfs darf er
        # nicht mehr erreicht werden - dafuer gibt es den eigenen Zweig.
        #
        # Geprueft wird der Aufruf, nicht der Name im Text: Beim ersten Anlauf
        # stand hier assertIn auf dem Quelltext der Methode, und die
        # Gegenprobe blieb gruen - der Name kam im erklaerenden Kommentar
        # darueber vor.
        aufrufe = [k for k in ast.walk(m)
                   if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_mode_pack_folder_flach"]
        self.assertTrue(aufrufe, "Der flache Zweig fuer .ffpfs wird nicht gerufen.")
        # ... und zwar in einem Zweig, der an uncompressed haengt.
        bedingungen = [k for k in ast.walk(m)
                       if isinstance(k, ast.If)
                       and "uncompressed" in ast.dump(k.test)
                       and any(getattr(getattr(a, "func", None), "attr", "")
                               == "_mode_pack_folder_flach"
                               for a in ast.walk(k))]
        self.assertTrue(bedingungen,
                        "Der flache Weg haengt nicht mehr an uncompressed - "
                        "dann bekaeme auch die .ffpfsc ihn.")

    def test_der_flache_zweig_packt_direkt_in_die_zieldatei(self):
        m = self._methode("_mode_pack_folder_flach")
        aufrufe = self._mkpfs_aufrufe(m)
        self.assertEqual(1, len(aufrufe),
                         "Genau ein mkpfs-Lauf, sonst ist es wieder zweistufig.")
        _zeile, argumente = aufrufe[0]
        for pflicht in ("'--raw'", "'--no-compress'", "'pack'", "'folder'"):
            self.assertIn(pflicht, argumente,
                          "%s fehlt - ohne das wird nicht flach gebaut." % pflicht)
        # Nur der Rumpf, ohne Docstring: Der erklaert die alte Bauform und
        # nennt pfs_image.dat mit Absicht.
        rumpf = "\n".join(
            ast.get_source_segment(self.quelle, k) or "" for k in m.body
            if not (isinstance(k, ast.Expr) and isinstance(k.value, ast.Constant)))
        self.assertNotIn("pfs_image.dat", rumpf,
                         "Die Zwischendatei ist wieder da.")
        self.assertNotIn('"pack", "file"', rumpf,
                         "Das aeussere Einwickeln ist wieder da.")


class AbbildwegTests(_Quelltext):
    """exFAT und .ffpkg nach .ffpfs gehen ueber den Dump-Ordner."""

    def test_die_verteilung_bettet_abbilder_nicht_mehr_ein(self):
        m = self._methode("_execute_conversion_by_type")
        quelle = ast.get_source_segment(self.quelle, m) or ""
        # _mode_pack_file bettet die Quelldatei als Einzeldatei ein. Fuer
        # .ffpfsc ist das richtig (Container), fuer .ffpfs nicht.
        for zeile in quelle.splitlines():
            if "_mode_pack_file" in zeile:
                self.assertNotIn("uncompressed=True", zeile,
                                 "Ein Abbild wird wieder direkt in eine .ffpfs "
                                 "eingebettet: %s" % zeile.strip())


@unittest.skipUnless(_mkpfs_da(), "mkpfs nicht importierbar")
class GemesseneBauformTests(unittest.TestCase):
    """Nicht am Quelltext gelesen, sondern gebaut und nachgesehen."""

    @classmethod
    def setUpClass(cls):
        cls.arbeit = tempfile.mkdtemp(prefix="ps5conv_ffpfs_bauform_")
        dump = os.path.join(cls.arbeit, "dump")
        os.makedirs(os.path.join(dump, "sce_sys"))
        with io.open(os.path.join(dump, "eboot.bin"), "wb") as fh:
            fh.write(b"ELF-Platzhalter")
        with io.open(os.path.join(dump, "sce_sys", "param.json"), "wb") as fh:
            fh.write(b'{"titleId":"PPSA99999"}')
        cls.dump = dump
        cls.flach = os.path.join(cls.arbeit, "flach.ffpfs")
        lauf = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "folder", "--raw",
             "--no-compress", "--no-adjust-output-file-extension",
             "--version", "PS5", "--inode-bits", "32",
             "--block-size", "65536", dump, cls.flach],
            capture_output=True, cwd=str(PROJEKT / "MkPFS-1.0.0"), timeout=180)
        cls.baufehler = lauf.stderr.decode("utf-8", "replace") if lauf.returncode else ""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.arbeit, ignore_errors=True)

    def setUp(self):
        if self.baufehler:
            self.skipTest("mkpfs konnte nichts bauen: %s" % self.baufehler[:200])

    def test_param_json_liegt_in_der_wurzel(self):
        from ps5_validator.modules.ffpfs_validator import ermittle_bauform
        befund = ermittle_bauform(self.flach)
        self.assertIsNotNone(befund, "Die gebaute Datei ist kein PFS-Abbild.")
        self.assertEqual("flach", befund["bauform"])
        self.assertGreater(befund["aeussere_dateien"], 1,
                           "Genau ein Eintrag hiesse: doch wieder geschachtelt.")

    def test_der_pruefer_haelt_die_flache_ffpfs_fuer_richtig(self):
        from ps5_validator.modules.ffpfs_validator import FfpfsValidator
        ergebnis = FfpfsValidator().validate(Path(self.flach))
        self.assertNotIn("Ungewöhnlicher Aufbau", " ".join(ergebnis.errors),
                         "Eine richtig gebaute .ffpfs wird als fehlerhaft "
                         "gemeldet - genau der Fehlalarm aus dem Befund.")

    def test_der_pruefer_beanstandet_die_geschachtelte_ffpfs(self):
        """Die Gegenrichtung - sonst waere die Weiche oben nur nachsichtig."""
        geschachtelt = os.path.join(self.arbeit, "geschachtelt.ffpfs")
        lauf = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "file", "--no-compress",
             "--no-adjust-output-file-extension", "--no-rename-inner-image",
             "--version", "PS5", "--inode-bits", "32",
             self.flach, geschachtelt],
            capture_output=True, cwd=str(PROJEKT / "MkPFS-1.0.0"), timeout=180)
        if lauf.returncode or not os.path.isfile(geschachtelt):
            self.skipTest("mkpfs konnte den Vergleichsfall nicht bauen")

        from ps5_validator.modules.ffpfs_validator import FfpfsValidator
        ergebnis = FfpfsValidator().validate(Path(geschachtelt))
        self.assertIn("Ungewöhnlicher Aufbau", " ".join(ergebnis.errors),
                      "Eine .ffpfs mit einem eingebetteten Abbild kommt "
                      "durch - das ist die Form, die ShadowMount+ nicht "
                      "registriert.")

    def test_dieselbe_datei_als_ffpfsc_wird_umgekehrt_beurteilt(self):
        """Der Unterschied haengt wirklich an der Endung, nicht am Inhalt."""
        import shutil as _sh
        als_container = os.path.join(self.arbeit, "gleich.ffpfsc")
        _sh.copyfile(self.flach, als_container)

        from ps5_validator.modules.ffpfs_validator import FfpfsValidator
        ergebnis = FfpfsValidator().validate(Path(als_container))
        self.assertIn("Ungewöhnlicher Aufbau", " ".join(ergebnis.errors),
                      "Byte fuer Byte dieselbe Datei: als .ffpfs richtig, "
                      "als .ffpfsc fehlt ihr die Containerebene.")


if __name__ == "__main__":
    unittest.main()
