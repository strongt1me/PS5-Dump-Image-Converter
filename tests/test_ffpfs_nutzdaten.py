# -*- coding: utf-8 -*-
"""Der Validator entpackt die Nutzdaten einer .ffpfsc und findet ein gekipptes Byte.

Matrixlauf vom 04.11.2026 (Aufgaben 1-8, alle Formate): In der Mitte einer frisch
gebauten .ffpfsc wurde ein Byte verfaelscht. Der Validator (Aufgabe 8) meldete
``OK`` - er las die Datei nur, pruefte Kopf, Groesse und Aufbau und rechnete das
SHA-256. ``mkpfs verify`` (Fehler: 1) und ``mkpfs unpack --deep`` (zlib:
"incorrect data check") fanden denselben Schaden. Die Gegenprobe an der
unversehrten Datei: ``mkpfs verify`` ohne Fehler, "Files hash-checked: 1".

Jeder Block einer komprimierten Nutzlast traegt seine Adler-32-Pruefsumme; sie
schlaegt erst beim Entpacken an. Dieselbe Pruefung macht das Programm nach jedem
Bau (``abbild_pruefen``), nur der Validator ueberging sie.

Grenzen, die diese Tests ausdruecklich festhalten: Eine unkomprimierte ``.ffpfs``
(und ein Block, den mkpfs unkomprimiert abgelegt hat) traegt keine Pruefwerte -
dort ist ein Bitfehler nicht zu sehen, und der Validator sagt das.
"""
from __future__ import annotations

import io
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))
sys.path.insert(0, str(PROJEKT / "MkPFS-1.1.0"))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("ffpfs_nutzdaten")


def _mkpfs_da() -> bool:
    try:
        import mkpfs  # noqa: F401
    except ImportError:
        return False
    return True


def _mkpfs(*argumente: str) -> str:
    """Ein mkpfs-Lauf; gibt den Fehlertext zurueck (leer = gelungen)."""
    lauf = subprocess.run([sys.executable, "-m", "mkpfs", *argumente], capture_output=True,
                          cwd=str(PROJEKT / "MkPFS-1.1.0"), timeout=300)
    return lauf.stderr.decode("utf-8", "replace") if lauf.returncode else ""


def _dump(wurzel: str, mit_eboot: bool = True) -> str:
    """Ein kleiner, gut komprimierbarer Dump."""
    os.makedirs(os.path.join(wurzel, "sce_sys"))
    with io.open(os.path.join(wurzel, "sce_sys", "param.json"), "wb") as fh:
        fh.write(b'{"titleId":"PPSA99999"}')
    if mit_eboot:
        with io.open(os.path.join(wurzel, "eboot.bin"), "wb") as fh:
            fh.write(b"ELF" + bytes(700_000))
    with io.open(os.path.join(wurzel, "data.bin"), "wb") as fh:
        fh.write(b"".join(b"PS5 Testdaten Zeile %06d\n" % i for i in range(60_000)))
    return wurzel


def _baue_container(arbeit: str, name: str, dump: str) -> str:
    """Dump -> inneres Abbild (roh) -> .ffpfsc, wie das Programm es zweistufig baut."""
    innen = os.path.join(arbeit, name + ".innen")
    aussen = os.path.join(arbeit, name + ".ffpfsc")
    fehler = _mkpfs("pack", "folder", "--raw", "--no-compress", "--no-adjust-output-file-extension",
                    "--version", "PS5", "--inode-bits", "32", "--block-size", "65536", dump, innen)
    if not fehler:
        fehler = _mkpfs("pack", "file", "--no-adjust-output-file-extension", "--no-rename-inner-image",
                        "--version", "PS5", "--inode-bits", "32", innen, aussen)
    if fehler:
        raise unittest.SkipTest("mkpfs konnte den Container nicht bauen: %s" % fehler[:200])
    return aussen


def _komprimierter_block(pfad: str) -> tuple[int, int]:
    """(Anfang, Ende) eines wirklich komprimiert abgelegten Blocks aus der Mitte der Nutzlast."""
    from mkpfs import pfs as p
    ins = p.inspect_pfs_image(Path(pfad), verify_payloads=False)
    assert len(ins.file_inodes) == 1, ins.file_inodes
    inode = ins.inodes[next(iter(ins.file_inodes.values()))]
    assert inode.is_compressed
    basis = inode.db[0] * ins.header.block_size
    with open(pfad, "rb") as fh:
        fh.seek(basis)
        kopf = fh.read(p.consts.PFSC_HEADER_SIZE)
        block, anzahl, tabelle, _daten, _logisch = p._parse_pfsc_header(kopf)
        fh.seek(basis + tabelle)
        offsets = struct.unpack("<%dQ" % (anzahl + 1), fh.read((anzahl + 1) * 8))
    for k in list(range(anzahl // 2, anzahl)) + list(range(0, anzahl // 2)):
        if offsets[k + 1] - offsets[k] < block:
            return basis + offsets[k], basis + offsets[k + 1]
    raise AssertionError("Kein komprimierter Block gefunden - der Aufbau taugt nicht als Probe.")


@unittest.skipUnless(_mkpfs_da(), "mkpfs nicht importierbar")
class NutzdatenTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.arbeit = tempfile.mkdtemp(prefix="ps5conv_nutzdaten_")
        cls.dump = _dump(os.path.join(cls.arbeit, "dump"))
        try:
            cls.heil = _baue_container(cls.arbeit, "spiel", cls.dump)
        except unittest.SkipTest as exc:
            cls.baufehler = str(exc)
        else:
            cls.baufehler = ""

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.arbeit, ignore_errors=True)

    def setUp(self):
        if self.baufehler:
            self.skipTest(self.baufehler)

    def _pruefen(self, pfad, **kwargs):
        from ps5_validator.modules.ffpfs_validator import FfpfsValidator
        return FfpfsValidator(**kwargs).validate(str(pfad))

    def _kopie_mit_gekipptem_byte(self, name: str) -> str:
        ziel = os.path.join(self.arbeit, name)
        shutil.copyfile(self.heil, ziel)
        anfang, ende = _komprimierter_block(ziel)
        stelle = anfang + (ende - anfang) // 2
        with open(ziel, "r+b") as fh:
            fh.seek(stelle)
            wert = fh.read(1)[0]
            fh.seek(stelle)
            fh.write(bytes([wert ^ 0xFF]))
        return ziel

    def test_der_unversehrte_container_besteht(self):
        ergebnis = self._pruefen(self.heil)
        self.assertIn(ergebnis.status, ("OK", "WARNING"), ergebnis.errors)
        self.assertTrue(ergebnis.summary["payload"].startswith("in Ordnung"), ergebnis.summary)
        self.assertIn(os.path.basename(self.heil), ergebnis.hashes)

    def test_ein_gekipptes_byte_in_einem_komprimierten_block_wird_gefunden(self):
        kaputt = self._kopie_mit_gekipptem_byte("gekippt.ffpfsc")
        ergebnis = self._pruefen(kaputt)
        self.assertEqual("CORRUPTED", ergebnis.status, ergebnis.errors)
        self.assertTrue(any("Nutzdaten beschädigt" in e for e in ergebnis.errors), ergebnis.errors)
        self.assertTrue(ergebnis.summary["payload"].startswith("beschädigt"), ergebnis.summary)

    def test_der_befund_nennt_den_block_und_die_ursache(self):
        kaputt = self._kopie_mit_gekipptem_byte("gekippt2.ffpfsc")
        text = " ".join(self._pruefen(kaputt).errors)
        self.assertIn("PFSC block", text)
        self.assertIn("decompress", text)

    def test_die_englische_oberflaeche_bekommt_den_befund_englisch(self):
        from ps5_validator.core import dispatcher
        from ps5_validator.utils.i18n import translate
        texte = {k: translate("en", "validator." + k) for k in dispatcher.MELDUNGEN}
        kaputt = self._kopie_mit_gekipptem_byte("gekippt3.ffpfsc")
        ergebnis = self._pruefen(kaputt, texte=texte)
        self.assertTrue(any(e.startswith("Payload damaged") for e in ergebnis.errors), ergebnis.errors)

    def test_der_abbruch_waehrend_des_entpackens_ist_kein_urteil(self):
        ergebnis = self._pruefen(self.heil, cancel_flag=lambda: True)
        self.assertEqual("SKIPPED", ergebnis.status, ergebnis.errors)
        self.assertEqual({}, ergebnis.hashes)

    def test_der_balken_teilt_sich_zwischen_entpacken_und_sha256(self):
        folge: list[tuple[int, int, str]] = []
        ergebnis = self._pruefen(self.heil, progress_cb=lambda d, t, l: folge.append((d, t, l)))
        self.assertIn(ergebnis.status, ("OK", "WARNING"))
        groesse = os.path.getsize(self.heil)
        self.assertEqual({2 * groesse}, {t for _d, t, _l in folge},
                         "Beide Durchgaenge muessen auf einer Achse laufen.")
        werte = [d for d, _t, _l in folge]
        self.assertEqual(sorted(werte), werte, "Der Balken darf nicht zurueckspringen.")
        self.assertEqual(2 * groesse, werte[-1])
        entpacken = [d for d, _t, l in folge if "entpacken" in l]
        lesen = [d for d, _t, l in folge if "entpacken" not in l]
        self.assertTrue(entpacken and lesen, "Es fehlt einer der beiden Durchgaenge.")
        self.assertLessEqual(max(entpacken), groesse, "Das Entpacken belegt nur die erste Haelfte.")
        self.assertGreaterEqual(min(lesen), groesse, "Das SHA-256 beginnt in der zweiten Haelfte.")

    def test_ein_aufbaubefund_erspart_das_entpacken(self):
        """Was schon beanstandet ist (hier: eboot.bin fehlt), braucht keine Viertelstunde Entpacken."""
        wurzel = os.path.join(self.arbeit, "dump_ohne_eboot")
        _dump(wurzel, mit_eboot=False)
        container = _baue_container(self.arbeit, "ohne_eboot", wurzel)
        from ps5_validator.modules import ffpfs_validator as modul
        with mock.patch.object(modul.FfpfsValidator, "_check_payload",
                               side_effect=AssertionError("darf nicht entpacken")) as entpacken:
            ergebnis = self._pruefen(container)
        # Von aussen pruefen: Ein except im Programm koennte die Ausnahme des Stubs schlucken.
        entpacken.assert_not_called()
        self.assertEqual("FAILED", ergebnis.status, ergebnis.errors)

    def test_ein_zerstoerter_kopf_ist_kein_abbild(self):
        """Matrixlauf 04.11.2026: Die ersten 4096 Bytes auf Null - "BESTANDEN: WARNING"."""
        kopflos = os.path.join(self.arbeit, "kopflos.ffpfsc")
        shutil.copyfile(self.heil, kopflos)
        with open(kopflos, "r+b") as fh:
            fh.write(b"\x00" * 4096)
        ergebnis = self._pruefen(kopflos)
        self.assertEqual("CORRUPTED", ergebnis.status, ergebnis.errors)
        self.assertTrue(any("Unbekannter PFS-Header" in e for e in ergebnis.errors), ergebnis.errors)
        self.assertEqual({}, ergebnis.hashes, "Das Urteil steht - gelesen wird nicht mehr.")

    def test_eine_kurze_datei_mit_fremder_kennung_ist_kein_abbild(self):
        kurz = os.path.join(self.arbeit, "kurz.ffpfsc")
        Path(kurz).write_bytes(b"ABCDEFGH")
        self.assertEqual("CORRUPTED", self._pruefen(kurz).status)

    def test_eine_unkomprimierte_ffpfs_sagt_ehrlich_dass_sie_nicht_pruefbar_ist(self):
        flach = os.path.join(self.arbeit, "flach.ffpfs")
        fehler = _mkpfs("pack", "folder", "--raw", "--no-compress", "--no-adjust-output-file-extension",
                        "--version", "PS5", "--inode-bits", "32", "--block-size", "65536", self.dump, flach)
        if fehler:
            self.skipTest("mkpfs konnte die .ffpfs nicht bauen: %s" % fehler[:200])
        ergebnis = self._pruefen(flach)
        self.assertNotEqual("CORRUPTED", ergebnis.status, ergebnis.errors)
        self.assertTrue(ergebnis.summary["payload"].startswith("nicht prüfbar"), ergebnis.summary)


if __name__ == "__main__":
    unittest.main()
