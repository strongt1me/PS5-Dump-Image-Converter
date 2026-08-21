"""Regressionstest: Name der eingebetteten Datei im Container.

Gefunden beim Durchtesten aller Aufgaben: Aus
`PPSA16709 Asterix Obelix Heroes (01.000.000).ffpkg` wurde im Container
`PPSA16709.000.000).ffpkg`. Ursache ist mkpfs' Umbenennung, die den Namen über
`Path.suffixes` zerlegt – dort gilt bei `(01.000.000)` jeder Punktabschnitt als
Dateiendung:

    Path("Spiel (01.003.000).exfat").suffixes  →  ['.003', '.000)', '.exfat']

Das Programm packt deshalb mit `--no-rename-inner-image`; der Originalname
bleibt damit erhalten. Der ps5-exfat-builder hat denselben Fehler, weil er das
Flag nicht setzt.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

QUELLDATEI = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
MKPFS_DIR = next(
    (p for p in sorted(PROJEKT.glob("MkPFS-*"), reverse=True) if (p / "mkpfs" / "__init__.py").is_file()),
    None,
)


class FlagImQuelltextTests(unittest.TestCase):
    """Jeder Einzeldatei-Packlauf muss das Flag mitgeben."""

    def setUp(self) -> None:
        self.quelltext = QUELLDATEI.read_text(encoding="utf-8")

    def test_jeder_pack_file_aufruf_setzt_das_flag(self):
        bloecke = self.quelltext.split('"pack", "file",')[1:]
        self.assertGreaterEqual(len(bloecke), 4, "pack-file-Aufrufe nicht gefunden")
        for nummer, block in enumerate(bloecke, start=1):
            with self.subTest(aufruf=nummer):
                # Das Flag muss im Argumentblock stehen, nicht irgendwo spaeter.
                self.assertIn("--no-rename-inner-image", block[:800])

    def test_pack_folder_bekommt_das_flag_nicht(self):
        """Das Flag gibt es nur beim Einzeldatei-Packen – sonst bricht mkpfs ab."""
        for block in self.quelltext.split('"pack", "folder",')[1:]:
            with self.subTest():
                self.assertNotIn("--no-rename-inner-image", block[:600])


@unittest.skipUnless(MKPFS_DIR is not None, "mkpfs nicht verfügbar")
class NamensverhaltenTests(unittest.TestCase):
    """Nachweis am echten Packer."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="innenname_")
        basis = Path(cls._tmp.name)
        cls.quelle = basis / "PPSA19015 Arcade Game Zone (01.003.000).exfat"
        nutzlast = bytearray(1 << 20)
        nutzlast[3:11] = b"EXFAT   "
        cls.quelle.write_bytes(bytes(nutzlast))
        cls.umgebung = dict(os.environ)
        cls.umgebung["PYTHONPATH"] = str(MKPFS_DIR)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _packen(self, *zusatz: str) -> str:
        ziel = Path(self._tmp.name) / f"ziel_{len(zusatz)}.ffpfsc"
        subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "file", "--compress",
             "--no-verify-structure", "--no-adjust-output-file-extension", *zusatz,
             "--version", "PS5", "--inode-bits", "32", "--block-size", "65536",
             str(self.quelle), str(ziel)],
            env=self.umgebung, capture_output=True, check=True, timeout=300,
        )
        sys.path.insert(0, str(MKPFS_DIR))
        from mkpfs.pfs import open_inner_file_view
        geoeffnet = open_inner_file_view(ziel)
        self.assertIsNotNone(geoeffnet)
        _view, handle, innerer_name = geoeffnet
        handle.close()
        return innerer_name

    def test_mit_flag_bleibt_der_originalname(self):
        self.assertEqual(self._packen("--no-rename-inner-image"), self.quelle.name)

    def test_ohne_flag_wird_der_name_verstuemmelt(self):
        """Hält den Fehler fest, gegen den das Flag schützt."""
        self.assertNotEqual(self._packen(), self.quelle.name)

    def test_die_ursache_liegt_in_pathlib(self):
        self.assertEqual(Path("Spiel (01.003.000).exfat").suffixes, [".003", ".000)", ".exfat"])

    def test_sonderzeichen_brechen_den_packlauf_nicht_mehr(self):
        """Folgefehler des Flags: PFS speichert Namen als ASCII.

        `Matchbox™ Driving Adventures (01.000.001).exfat` liess mkpfs mit
        `ValueError: ... contains non-ASCII characters` abbrechen, seit der
        Originalname unveraendert durchgereicht wird.
        """
        quelle = Path(self._tmp.name) / "Matchbox™ Driving Adventures (01.000.001).exfat"
        nutzlast = bytearray(1 << 20)
        nutzlast[3:11] = b"EXFAT   "
        quelle.write_bytes(bytes(nutzlast))
        ziel = Path(self._tmp.name) / "sonderzeichen.ffpfsc"
        ergebnis = subprocess.run(
            [sys.executable, "-m", "mkpfs", "pack", "file", "--compress",
             "--no-verify-structure", "--no-adjust-output-file-extension",
             "--no-rename-inner-image", "--version", "PS5", "--inode-bits", "32",
             "--block-size", "65536", str(quelle), str(ziel)],
            env=self.umgebung, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300,
        )
        self.assertEqual(ergebnis.returncode, 0,
                         f"mkpfs brach ab: {ergebnis.stdout[-600:]}{ergebnis.stderr[-600:]}")
        sys.path.insert(0, str(MKPFS_DIR))
        from mkpfs.pfs import open_inner_file_view
        geoeffnet = open_inner_file_view(ziel)
        self.assertIsNotNone(geoeffnet)
        _view, handle, innerer_name = geoeffnet
        handle.close()
        self.assertEqual(innerer_name, "Matchbox(TM) Driving Adventures (01.000.001).exfat")


@unittest.skipUnless(MKPFS_DIR is not None, "mkpfs nicht verfügbar")
class AsciiFaltungTests(unittest.TestCase):
    """Die Faltung ersetzt nur, was ASCII nicht darstellen kann.

    Sichert zugleich das Verhalten des mitgelieferten mkpfs ab: geht die
    Anpassung bei einem Engine-Update verloren, faellt dieser Test.
    """

    def setUp(self) -> None:
        if str(MKPFS_DIR) not in sys.path:
            sys.path.insert(0, str(MKPFS_DIR))
        from mkpfs.pfs import fold_inner_name_to_ascii, resolve_single_file_inner_name
        self.falten = fold_inner_name_to_ascii
        self.aufloesen = resolve_single_file_inner_name

    def test_reiner_ascii_name_bleibt_unveraendert(self):
        for name in ("pfs_image.dat", "Instant Sports Plus (01.002.001).exfat"):
            with self.subTest(name=name):
                self.assertEqual(self.falten(name), name)

    def test_typografische_zeichen_bekommen_entsprechungen(self):
        self.assertEqual(self.falten("Matchbox™ X.exfat"), "Matchbox(TM) X.exfat")
        self.assertEqual(self.falten("A – B.exfat"), "A - B.exfat")
        self.assertEqual(self.falten("Grüße.exfat"), "Grusse.exfat")

    def test_versionsklammer_ueberlebt_die_faltung(self):
        gefaltet = self.falten("Matchbox™ Driving Adventures (01.000.001).exfat")
        self.assertIn("(01.000.001)", gefaltet)
        self.assertTrue(gefaltet.endswith(".exfat"))

    def test_nicht_faltbares_wird_ersetzt_statt_verworfen(self):
        gefaltet = self.falten("中文.exfat")
        self.assertTrue(gefaltet.isascii())
        self.assertTrue(gefaltet.endswith(".exfat"))
        self.assertTrue(gefaltet.strip("_.exfat") == "" or gefaltet)

    def test_ergebnis_ist_immer_ascii_und_nie_leer(self):
        for name in ("™™™", "  ", "中文タ.exfat", "ok.bin"):
            with self.subTest(name=name):
                gefaltet = self.falten(name)
                self.assertTrue(gefaltet.isascii())
                self.assertTrue(gefaltet)

    def test_keine_pfadtrenner_im_ergebnis(self):
        gefaltet = self.falten("a⁄b.exfat")   # U+2044 zerfaellt zu "/"
        self.assertNotIn("/", gefaltet)
        self.assertNotIn("\\", gefaltet)

    def test_ohne_umbenennen_wird_gefaltet_nicht_umgebaut(self):
        name = "Matchbox™ Driving Adventures (01.000.001).exfat"
        self.assertEqual(
            self.aufloesen(source_name=name, rename_inner_image=False),
            "Matchbox(TM) Driving Adventures (01.000.001).exfat",
        )

    def test_mit_umbenennen_bleibt_das_alte_verhalten(self):
        """Die Umbenennung selbst wird nicht angefasst - nur der Aus-Fall."""
        umbenannt = self.aufloesen(
            source_name="Matchbox™ Driving Adventures (01.000.001).exfat",
            rename_inner_image=True,
        )
        self.assertTrue(umbenannt.isascii())
        self.assertNotIn("(TM)", umbenannt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
