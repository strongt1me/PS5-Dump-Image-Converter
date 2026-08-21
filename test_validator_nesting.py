"""Regressionstests für die Verschachtelungsprüfung des .ffpfsc-Validators.

Hintergrund: Ein korrektes `.ffpfsc` ist zweistufig – außen der Container, darin
genau ein rohes PFS-Image mit den Spieldateien. Fehlt beim inneren Image
``--raw``, schiebt mkpfs ein exFAT-Abbild dazwischen. `mkpfs tree` und
`inspect` zeigen den Unterschied nicht, weil beide nur die äußere Ebene
auflisten.

Die Tests bauen mit der mitgelieferten mkpfs-Engine je eine korrekte und eine
falsch verschachtelte Datei und prüfen, dass der Validator sie unterscheidet.
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

from ps5_validator.core.dispatcher import validate
from ps5_validator.modules.ffpfs_validator import _ensure_mkpfs_importable

MKPFS_DIRS = sorted(PROJEKT.glob("MkPFS-*"), reverse=True)
MKPFS_DIR = next((p for p in MKPFS_DIRS if (p / "mkpfs" / "__init__.py").is_file()), None)


def _mkpfs(*args: str) -> None:
    """Ruft die mitgelieferte mkpfs-Engine auf."""
    umgebung = dict(os.environ)
    umgebung["PYTHONPATH"] = str(MKPFS_DIR)
    ergebnis = subprocess.run(
        [sys.executable, "-m", "mkpfs", *args],
        cwd=str(PROJEKT), env=umgebung, capture_output=True, text=True, timeout=300,
    )
    if ergebnis.returncode != 0:
        raise RuntimeError(f"mkpfs {' '.join(args)} scheiterte:\n{ergebnis.stdout}\n{ergebnis.stderr}")


@unittest.skipUnless(MKPFS_DIR is not None and _ensure_mkpfs_importable(), "mkpfs nicht verfügbar")
class VerschachtelungsTests(unittest.TestCase):
    """Baut echte Container und prüft die Unterscheidung."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="ffpfs_nesting_")
        basis = Path(cls._tmp.name)
        dump = basis / "dump"
        # Vollständiger Mini-Dump: Ohne die Pflichtdateien würde die
        # Vollständigkeitsprüfung anschlagen und die Verschachtelungstests
        # aus einem anderen Grund scheitern lassen (siehe test_incomplete_dump).
        (dump / "sce_sys").mkdir(parents=True)
        (dump / "sce_sys" / "param.json").write_text('{"titleId":"PPSA00001"}', encoding="utf-8")
        (dump / "sce_sys" / "pfs-version.dat").write_bytes(os.urandom(16))
        (dump / "eboot.bin").write_bytes(os.urandom(120_000))
        (dump / "sce_sys" / "icon0.png").write_bytes(os.urandom(40_000))

        gemeinsam = [
            "--no-compress", "--no-verify-structure", "--no-adjust-output-file-extension",
            "--version", "PS5", "--inode-bits", "32", "--block-size", "65536",
        ]
        cls.inner_ok = basis / "inner_ok.pfs"
        cls.inner_defekt = basis / "inner_defekt.pfs"
        # Mit --raw: die Spieldateien liegen direkt im inneren Image (korrekt).
        _mkpfs("pack", "folder", "--raw", *gemeinsam, str(dump), str(cls.inner_ok))
        # Ohne --raw: mkpfs legt von sich aus ein exFAT-Abbild dazwischen.
        _mkpfs("pack", "folder", *gemeinsam, str(dump), str(cls.inner_defekt))

        aussen = [
            "--compress", "--no-verify-structure", "--no-adjust-output-file-extension",
            "--version", "PS5", "--inode-bits", "32", "--block-size", "65536",
        ]
        cls.datei_ok = basis / "ok.ffpfsc"
        cls.datei_defekt = basis / "defekt.ffpfsc"
        _mkpfs("pack", "file", *aussen, str(cls.inner_ok), str(cls.datei_ok))
        _mkpfs("pack", "file", *aussen, str(cls.inner_defekt), str(cls.datei_defekt))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def _pruefen(self, pfad: Path):
        return validate(path=str(pfad), mode="ffpfs", threads=1, resume=False, verbose=False)

    def test_korrekte_datei_wird_akzeptiert(self):
        ergebnis = self._pruefen(self.datei_ok)
        self.assertEqual(ergebnis.status, "OK", ergebnis.errors)
        self.assertIn("in Ordnung", ergebnis.summary["nesting"])
        self.assertGreaterEqual(ergebnis.summary["inner_files"], 3)

    def test_falsch_verschachtelte_datei_faellt_durch(self):
        ergebnis = self._pruefen(self.datei_defekt)
        self.assertEqual(ergebnis.status, "FAILED")
        self.assertIn("falsch verschachtelt", ergebnis.summary["nesting"])
        self.assertEqual(ergebnis.summary["inner_files"], 1)
        self.assertTrue(any("verschachtelt" in e.lower() for e in ergebnis.errors), ergebnis.errors)

    def test_defekt_wird_am_inhalt_erkannt_nicht_am_namen(self):
        """Der Nachweis kommt aus der exFAT-Signatur, nicht aus der Dateiendung."""
        ergebnis = self._pruefen(self.datei_defekt)
        self.assertIn("exFAT-Abbild", ergebnis.summary["nesting"])

    def test_aeussere_ebene_hat_genau_einen_eintrag(self):
        for pfad in (self.datei_ok, self.datei_defekt):
            with self.subTest(datei=pfad.name):
                self.assertEqual(self._pruefen(pfad).summary["outer_files"], 1)

    def test_rohes_inneres_image_gilt_als_flach(self):
        """Wer das innere Image direkt prüft, bekommt einen Hinweis statt eines Fehlers."""
        ergebnis = self._pruefen(self.inner_ok)
        self.assertEqual(ergebnis.status, "WARNING")
        self.assertIn("flach aufgebaut", ergebnis.summary["nesting"])

    def test_eingebettetes_exfat_gilt_als_richtig(self):
        """Aufgabe 3 bettet eine .exfat in einem Schritt ein – das ist Absicht."""
        basis = Path(self._tmp.name)
        roh = basis / "PPSA00001.exfat"
        nutzlast = bytearray(2 * 1024 * 1024)
        nutzlast[3:11] = b"EXFAT   "          # Bootsektor-Kennung
        roh.write_bytes(bytes(nutzlast))
        ziel = basis / "aus_exfat.ffpfsc"
        _mkpfs("pack", "file", "--compress", "--no-verify-structure",
               "--no-adjust-output-file-extension", "--version", "PS5",
               "--inode-bits", "32", "--block-size", "65536", str(roh), str(ziel))
        ergebnis = self._pruefen(ziel)
        self.assertEqual(ergebnis.summary.get("inner_kind"), "exfat")
        self.assertIn("in Ordnung", ergebnis.summary["nesting"])

    def test_eingebettetes_ufs2_gilt_als_richtig(self):
        """Aufgabe 4 bettet eine .ffpkg (UFS2-Abbild) genauso ein."""
        basis = Path(self._tmp.name)
        roh = basis / "PPSA00002.ffpkg"
        nutzlast = bytearray(2 * 1024 * 1024)
        nutzlast[65536 + 1372:65536 + 1376] = (0x19540119).to_bytes(4, "little")
        roh.write_bytes(bytes(nutzlast))
        ziel = basis / "aus_ffpkg.ffpfsc"
        _mkpfs("pack", "file", "--compress", "--no-verify-structure",
               "--no-adjust-output-file-extension", "--version", "PS5",
               "--inode-bits", "32", "--block-size", "65536", str(roh), str(ziel))
        ergebnis = self._pruefen(ziel)
        self.assertEqual(ergebnis.summary.get("inner_kind"), "ffpkg")
        self.assertIn("in Ordnung", ergebnis.summary["nesting"])

    def test_zusaetzliche_pfs_ebene_bleibt_ein_fehler(self):
        """Die Unterscheidung: eine Ebene zu viel ist und bleibt der Fehlerfall."""
        ergebnis = self._pruefen(self.datei_defekt)
        self.assertEqual(ergebnis.summary.get("inner_kind"), "pfs")
        self.assertIn("falsch verschachtelt", ergebnis.summary["nesting"])

    def test_pack_folder_ohne_raw_ist_ein_regulaerer_container(self):
        """``mkpfs pack folder`` ohne ``--raw`` baut Container -> exFAT -> Dateien.

        Das ist kein Fehlbau, sondern der Normalfall dieses Aufrufs: Ohne
        ``--raw`` wickelt mkpfs den Ordner selbst in ein exFAT und komprimiert
        es in einem Zug in den Container. Der Fehlerfall ist erst die
        zusaetzliche PFS-Ebene darueber (siehe
        ``test_zusaetzliche_pfs_ebene_bleibt_ein_fehler``).
        """
        basis = Path(self._tmp.name)
        ziel = basis / "wrapper.ffpfsc"
        _mkpfs("pack", "folder", "--no-compress", "--no-verify-structure",
               "--no-adjust-output-file-extension", "--version", "PS5",
               str(basis / "dump"), str(ziel))
        ergebnis = self._pruefen(ziel)
        self.assertEqual(ergebnis.status, "OK", ergebnis.errors)
        self.assertEqual(ergebnis.summary.get("inner_kind"), "exfat")
        self.assertIn("in Ordnung", ergebnis.summary["nesting"])
        # Die innerste Ebene wird jetzt mitgelesen, nicht nur als "exFAT" abgehakt.
        self.assertGreaterEqual(ergebnis.summary.get("inner_files", 0), 4)
        self.assertEqual(ergebnis.summary.get("critical_files"), "vollstaendig")

    def test_unvollstaendiger_dump_faellt_auch_im_exfat_container_auf(self):
        """Pflichtdateien werden auch innerhalb des exFAT-Abbilds geprueft."""
        basis = Path(self._tmp.name)
        luecke = basis / "luecke"
        (luecke / "sce_sys").mkdir(parents=True, exist_ok=True)
        (luecke / "sce_sys" / "param.json").write_text('{"titleId":"PPSA00009"}', encoding="utf-8")
        (luecke / "sce_sys" / "pfs-version.dat").write_bytes(os.urandom(16))
        (luecke / "irgendwas.dat").write_bytes(os.urandom(20_000))   # kein eboot.bin
        ziel = basis / "luecke.ffpfsc"
        _mkpfs("pack", "folder", "--no-compress", "--no-verify-structure",
               "--no-adjust-output-file-extension", "--version", "PS5",
               str(luecke), str(ziel))
        ergebnis = self._pruefen(ziel)
        self.assertEqual(ergebnis.status, "FAILED")
        self.assertIn("eboot.bin", " ".join(ergebnis.errors))

    def test_pruefung_bleibt_unter_festem_lesebudget(self):
        """Die Tiefenprüfung darf die Datei nicht auspacken.

        Entscheidend ist nicht der Anteil an der Dateigröße, sondern dass der
        Aufwand an der Zahl der Einträge hängt und nicht an den Nutzdaten:
        Kopf, Inode-Tabelle und Verzeichnisblöcke. Gemessen wurden 757 KB bei
        einer 392-MB-Datei mit 93 Einträgen; die kleine Testdatei hier liegt in
        derselben Größenordnung. Das Budget von 8 MB schlägt an, sobald jemand
        wieder anfängt, Nutzdaten zu lesen.
        """
        import mkpfs.pfs as mkpfs_pfs
        from ps5_validator.modules.ffpfs_validator import FfpfsValidator
        from ps5_validator.core.validator_base import ValidationResult

        gelesen = {"bytes": 0}
        original = mkpfs_pfs.read_image_bytes

        def _zaehlen(fh, header, offset, size, **kwargs):
            gelesen["bytes"] += size
            return original(fh, header, offset, size, **kwargs)

        mkpfs_pfs.read_image_bytes = _zaehlen
        try:
            ergebnis = ValidationResult(mode="ffpfs")
            FfpfsValidator()._check_nesting(self.datei_ok, ergebnis)
        finally:
            mkpfs_pfs.read_image_bytes = original

        self.assertIn("in Ordnung", ergebnis.summary["nesting"])
        budget = 8 * 1024 * 1024
        self.assertLess(
            gelesen["bytes"], budget,
            f"Tiefenpruefung las {gelesen['bytes']} Bytes, erlaubt sind {budget}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
