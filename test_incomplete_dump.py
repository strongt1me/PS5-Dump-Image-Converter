"""Regressionstests für den Umgang mit unvollständigen Dumps.

Ein Dump ohne `eboot.bin` oder `sce_sys/param.json` lässt sich anstandslos in
einen Container packen – das Ergebnis ist formal gültig, startet auf der
Konsole aber nicht. Geprüft wird deshalb an zwei Stellen:

  1. **Vor dem Start** einer Aufgabe warnt der Preflight, wenn Pflichtdateien
     im Quellordner fehlen (Warnung, kein Abbruch – Teilordner sollen weiter
     packbar bleiben).
  2. **Aufgabe 8** meldet dieselben fehlenden Dateien auch dann, wenn nicht der
     Ordner, sondern der daraus gebaute `.ffpfsc`-Container geprüft wird.

Beide Stellen benutzen dieselbe Liste (`dump_validator.CRITICAL_FILES`), damit
Ordner und Container nicht zu verschiedenen Urteilen kommen.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI
from ps5_validator.core.dispatcher import validate
from ps5_validator.modules.dump_validator import CRITICAL_FILES
from ps5_validator.modules.ffpfs_validator import _ensure_mkpfs_importable

MKPFS_DIR = next(
    (p for p in sorted(PROJEKT.glob("MkPFS-*"), reverse=True) if (p / "mkpfs" / "__init__.py").is_file()),
    None,
)


def _dump_anlegen(basis: Path, *, vollstaendig: bool) -> Path:
    """Legt einen Mini-Dump an – wahlweise mit oder ohne eboot.bin."""
    basis.mkdir(parents=True, exist_ok=True)
    (basis / "sce_sys").mkdir(exist_ok=True)
    (basis / "sce_sys" / "param.json").write_text('{"titleId":"PPSA00003"}', encoding="utf-8")
    (basis / "sce_sys" / "pfs-version.dat").write_bytes(os.urandom(16))
    if vollstaendig:
        (basis / "eboot.bin").write_bytes(os.urandom(20_000))
    else:
        (basis / "irgendwas.dat").write_bytes(os.urandom(20_000))
    return basis


class PreflightTests(unittest.TestCase):
    """Warnung vor dem Start einer Aufgabe."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="preflight_")
        self.basis = Path(self._tmp.name)
        # Ohne Tk-Fenster: geprueft wird reine Dateilogik.
        self.gui = PS5ConverterGUI.__new__(PS5ConverterGUI)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_vollstaendiger_ordner_meldet_nichts(self):
        ordner = _dump_anlegen(self.basis / "voll", vollstaendig=True)
        self.assertEqual(self.gui._missing_critical_dump_files("pack_folder", str(ordner)), [])

    def test_fehlende_eboot_wird_gemeldet(self):
        ordner = _dump_anlegen(self.basis / "teil", vollstaendig=False)
        fehlend = self.gui._missing_critical_dump_files("pack_folder", str(ordner))
        self.assertIn("eboot.bin", fehlend)

    def test_liste_stammt_vom_validator(self):
        """Preflight und Aufgabe 8 duerfen nicht auseinanderlaufen."""
        self.assertEqual(tuple(PS5ConverterGUI._critical_dump_files()), tuple(CRITICAL_FILES))

    def test_aufgabe_8_wird_ausgenommen(self):
        """Der Validator meldet fehlende Dateien selbst - keine Doppelmeldung."""
        ordner = _dump_anlegen(self.basis / "teil8", vollstaendig=False)
        self.assertEqual(self.gui._missing_critical_dump_files("dump_validator", str(ordner)), [])

    def test_dateiquellen_werden_uebergangen(self):
        """Nur Ordner haben Pflichtdateien - eine Containerdatei nicht."""
        datei = self.basis / "irgendwas.ffpfsc"
        datei.write_bytes(b"\x00" * 32)
        self.assertEqual(self.gui._missing_critical_dump_files("unpack_to_exfat", str(datei)), [])


@unittest.skipUnless(MKPFS_DIR is not None and _ensure_mkpfs_importable(), "mkpfs nicht verfügbar")
class ContainerTests(unittest.TestCase):
    """Aufgabe 8 auf dem fertigen Container statt auf dem Ordner."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="krit_container_")
        basis = Path(cls._tmp.name)
        umgebung = dict(os.environ)
        umgebung["PYTHONPATH"] = str(MKPFS_DIR)

        def _mkpfs(*args: str) -> None:
            ergebnis = subprocess.run(
                [sys.executable, "-m", "mkpfs", *args],
                cwd=str(PROJEKT), env=umgebung, capture_output=True, text=True, timeout=300,
            )
            if ergebnis.returncode != 0:
                raise RuntimeError(f"mkpfs {' '.join(args)}: {ergebnis.stderr[-400:]}")

        gemeinsam = [
            "--no-compress", "--no-verify-structure", "--no-adjust-output-file-extension",
            "--version", "PS5", "--inode-bits", "32", "--block-size", "65536",
        ]
        cls.container: dict[str, Path] = {}
        for name, vollstaendig in (("voll", True), ("teil", False)):
            ordner = _dump_anlegen(basis / name, vollstaendig=vollstaendig)
            inneres = basis / f"{name}.pfs"
            aussen = basis / f"{name}.ffpfsc"
            _mkpfs("pack", "folder", "--raw", *gemeinsam, str(ordner), str(inneres))
            _mkpfs(
                "pack", "file", "--compress", "--no-verify-structure",
                "--no-adjust-output-file-extension", "--version", "PS5",
                "--inode-bits", "32", "--block-size", "65536", str(inneres), str(aussen),
            )
            cls.container[name] = aussen

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _pruefen(self, name: str):
        return validate(path=str(self.container[name]), mode="ffpfs", threads=1, resume=False, verbose=False)

    def test_vollstaendiger_container_ist_ok(self):
        ergebnis = self._pruefen("voll")
        self.assertEqual(ergebnis.status, "OK", ergebnis.errors)
        self.assertEqual(ergebnis.summary["critical_files"], "vollstaendig")

    def test_unvollstaendiger_container_faellt_durch(self):
        ergebnis = self._pruefen("teil")
        self.assertEqual(ergebnis.status, "FAILED")
        self.assertIn("eboot.bin", ergebnis.summary["critical_missing"])
        self.assertTrue(any("eboot.bin" in e for e in ergebnis.errors), ergebnis.errors)

    def test_urteil_deckt_sich_mit_der_ordnerpruefung(self):
        """Derselbe Inhalt muss als Ordner und als Container gleich bewertet werden."""
        ordner = Path(self._tmp.name) / "teil"
        als_ordner = validate(path=str(ordner), mode="dump", threads=1, resume=False, verbose=False)
        als_container = self._pruefen("teil")
        self.assertEqual(als_ordner.status, "FAILED")
        self.assertEqual(als_container.status, "FAILED")
        self.assertIn("eboot.bin", als_ordner.summary["critical_missing"])
        self.assertIn("eboot.bin", als_container.summary["critical_missing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
