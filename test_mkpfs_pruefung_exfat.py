# -*- coding: utf-8 -*-
"""Die Pruefung nach dem Einhuellen kopiert keine Quelle mehr - und meldet sich.

Zwei Befunde an derselben Stelle, beide aus dem Nachlauf J1 der Pruefmatrix
(Sammelkonvertierung nach .ffpfsc, 12.09.2026), erklaert am 14.09.2026:

**Die Strukturpruefung kopierte die Quelle.** ``mkpfs pack file`` packt eine
Einzeldatei direkt. Fuer die Pruefung danach stellt es die Quelle aber ueber
``_stage_single_file_source_root`` bereit: Hardlink, sonst Symlink, sonst
**vollstaendige Kopie**. exFAT kennt keins von beiden - und exFAT ist das
Dateisystem externer PS5-Platten, auch E: und F: auf dem Pruefrechner.
Gemessen: 64 MB auf exFAT als Kopie in 2,3 s, auf NTFS als Hardlink in
0,003 s. Von der 57-GB-``.ffpkg`` in J1 lagen nach dem Abbruch 24,8 GB neben
der Quelle - fuer eine Pruefung, die den Inhalt gar nicht vergleicht.

**Die Abschlusspruefung schwieg.** ``verify_pfs_image`` dekodiert jeden Block,
meldete dabei aber nichts. Nach zwei Minuten schrieb die Aufhaenger-Erkennung
einen Fehler samt Stapelabzug ins Protokoll eines normalen Laufs.

Die Pruefungen laufen in eigenen Prozessen: Hier kann laengst ein anderes
``mkpfs`` geladen sein (siehe ``test_mkpfs_fassung.py``). Links werden dort
gezielt verweigert, damit NTFS sich wie exFAT verhaelt.
"""
from __future__ import annotations

import ast
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
MKPFS_ORDNER = PROJEKT / "MkPFS-1.0.0"
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("mkpfs_pruefung_exfat")

#: Dieselben Schalter, die das Programm fuer "pack file" setzt.
PACKSCHALTER = ["--compression-backend", "zlib-ng", "--compress",
                "--no-adjust-output-file-extension", "--no-rename-inner-image",
                "--version", "PS5", "--inode-bits", "32", "--cpu-count", "1",
                "--compression-level", "6", "--block-size", "65536"]

KOPF = r'''
import json, os, shutil, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
basis = Path(sys.argv[2])
schalter = json.loads(sys.argv[3])
zusatz = sys.argv[4:]


def ergebnis(daten):
    print("ERGEBNIS:" + json.dumps(daten))


def kein_link(*_a, **_k):
    raise OSError(1, "gestellt: exFAT kennt weder Hardlinks noch Symlinks")


kopien = []
_echte_kopie = shutil.copyfile


def _kopie_zaehlen(quelle, ziel, *a, **k):
    kopien.append(str(ziel))
    return _echte_kopie(quelle, ziel, *a, **k)


def wie_exfat():
    os.link = kein_link
    Path.symlink_to = kein_link
    shutil.copyfile = _kopie_zaehlen
'''

BEREITSTELLEN = r'''
from mkpfs import cli
quelle = basis / "quelle.exfat"
quelle.write_bytes(os.urandom(4 * 1024 * 1024))
wie_exfat()
with cli._stage_single_file_source_root(source_file=quelle, temp_folder=basis,
                                        allow_copy=False) as wurzel:
    ohne = wurzel
kopien_ohne = list(kopien)
with cli._stage_single_file_source_root(source_file=quelle, temp_folder=basis) as wurzel:
    mit = wurzel is not None and (wurzel / quelle.name).is_file()
ergebnis({"ohne_ist_none": ohne is None, "kopien_ohne": kopien_ohne,
          "kopien_gesamt": len(kopien), "mit_kopie": mit,
          "reste": sorted(p.name for p in basis.iterdir() if p.name != "quelle.exfat")})
'''

PACKEN = r'''
from mkpfs import cli
quelle = basis / "spiel.exfat"
quelle.write_bytes(os.urandom(3 * 1024 * 1024))
(basis / "aus").mkdir()
ziel = basis / "aus" / "spiel.ffpfsc"
wie_exfat()
rc = cli.main(["pack", "file", *schalter, *zusatz, str(quelle), str(ziel)])
ergebnis({"rc": rc, "kopien": kopien, "ziel": ziel.is_file(),
          "reste": sorted(p.name for p in basis.iterdir()
                          if p.name not in ("spiel.exfat", "aus"))})
'''

FORTSCHRITT = r'''
from mkpfs import cli, pfs
from mkpfs.pbar import Progress
quelle = basis / "spiel.exfat"
quelle.write_bytes(os.urandom(20 * 1024 * 1024))
ziel = basis / "spiel.ffpfsc"
rc = cli.main(["pack", "file", *schalter, "--no-verify-structure", str(quelle), str(ziel)])
schritte = []
fortschritt = Progress(enabled=False,
                       listener=lambda aktion, *werte: schritte.append([aktion, *werte]))
bericht = pfs.verify_pfs_image(ziel, progress=fortschritt)
ergebnis({"rc": rc, "fehler": list(bericht.errors),
          "phasen": sorted({s[1] for s in schritte if s[0] == "step"}),
          "anzahl": len(schritte)})
'''

PRUEFSTAND = r'''
from mkpfs import cli
sys.path.insert(0, zusatz[0])
from ps5_validator.utils import abbild_pruefen
quelle = basis / "spiel.exfat"
quelle.write_bytes(os.urandom(12 * 1024 * 1024))
ziel = basis / "spiel.ffpfsc"
rc = cli.main(["pack", "file", *schalter, "--no-verify-structure", str(quelle), str(ziel)])
meldungen = []
stand = abbild_pruefen.Pruefstand(
    text=lambda schluessel, **werte: "%s|%s" % (schluessel, werte.get("prozent")),
    mkpfs_ordner_holen=lambda: sys.argv[1],
    status_melden=meldungen.append)
befund = stand._verify_output_artifact("pack_file", str(ziel))
ergebnis({"rc": rc, "ok": befund["ok"], "detail": befund["detail"],
          "meldungen": meldungen})
'''


def _laufen(skript: str, *zusatz: str) -> dict:
    """Fuehrt ein Pruefskript in einem eigenen Prozess aus."""
    with tempfile.TemporaryDirectory(prefix="mkpfs_pruefung_") as basis:
        lauf = subprocess.run(
            [sys.executable, "-c", KOPF + skript, str(MKPFS_ORDNER), basis,
             json.dumps(PACKSCHALTER), *zusatz],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    for zeile in reversed(lauf.stdout.splitlines()):
        if zeile.startswith("ERGEBNIS:"):
            return json.loads(zeile[len("ERGEBNIS:"):])
    raise AssertionError("Kein Ergebnis (Rueckgabe %s):\n%s\n%s"
                         % (lauf.returncode, lauf.stdout[-2000:], lauf.stderr[-2000:]))


class OhneKopieTests(unittest.TestCase):
    """Wo kein Link geht, kopiert nur noch die vollstaendige Pruefung."""

    def test_bereitstellen_ohne_kopie_liefert_none(self):
        r = _laufen(BEREITSTELLEN)
        self.assertTrue(r["ohne_ist_none"])
        self.assertEqual([], r["kopien_ohne"], "Trotz allow_copy=False kopiert.")

    def test_ohne_den_schalter_bleibt_die_vorlage_unveraendert(self):
        """Der Test der Vorlage verlangt weiter die Kopie als letzten Ausweg."""
        r = _laufen(BEREITSTELLEN)
        self.assertTrue(r["mit_kopie"])
        self.assertEqual(1, r["kopien_gesamt"])
        self.assertEqual([], r["reste"], "Ein Bereitstellungsordner bleibt liegen.")

    def test_die_strukturpruefung_kopiert_die_quelle_nicht(self):
        r = _laufen(PACKEN)
        self.assertEqual(0, r["rc"])
        self.assertTrue(r["ziel"])
        self.assertEqual([], r["kopien"],
                         "Die voreingestellte Strukturpruefung kopiert die Quelle "
                         "wieder - bei einer 57-GB-.ffpkg auf exFAT 57 GB.")
        self.assertEqual([], r["reste"])

    def test_die_vollstaendige_pruefung_darf_weiter_kopieren(self):
        """--verify liest den Inhalt der Quelle wirklich - dort bleibt es bei der Vorlage."""
        r = _laufen(PACKEN, "--verify")
        self.assertEqual(0, r["rc"])
        self.assertEqual(1, len(r["kopien"]))


class FortschrittTests(unittest.TestCase):
    """Die Abschlusspruefung meldet, wie weit sie ist."""

    def test_verify_pfs_image_reicht_den_fortschritt_durch(self):
        r = _laufen(FORTSCHRITT)
        self.assertEqual(0, r["rc"])
        self.assertEqual([], r["fehler"])
        self.assertIn("verify", r["phasen"],
                      "verify_pfs_image meldet beim Dekodieren nichts.")
        self.assertGreaterEqual(r["anzahl"], 2)

    def test_der_pruefstand_schreibt_in_die_statuszeile(self):
        r = _laufen(PRUEFSTAND, str(PROJEKT))
        self.assertEqual(0, r["rc"])
        self.assertTrue(r["ok"], r["detail"])
        self.assertTrue(r["meldungen"],
                        "Die Abschlusspruefung laeuft wieder ohne jede Meldung.")
        for meldung in r["meldungen"]:
            schluessel, _, prozent = meldung.partition("|")
            self.assertEqual("status.abschlusspruefung_fortschritt", schluessel)
            self.assertTrue(0 <= int(prozent) <= 100, meldung)

    def test_das_hauptprogramm_gibt_die_statuszeile_mit(self):
        with io.open(PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py", "rb") as fh:
            baum = ast.parse(fh.read().decode("utf-8"))
        knoten = next(k for k in ast.walk(baum)
                      if isinstance(k, ast.FunctionDef) and k.name == "_pruefstand")
        self.assertIn("status_melden=self._set_status", ast.unparse(knoten))


if __name__ == "__main__":
    unittest.main(verbosity=2)
