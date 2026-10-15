# -*- coding: utf-8 -*-
"""Die Huelle um ProsperoPkgTool - den zweiten, waehlbaren Paketersteller (``utils/prospero_pkg_tool.py``, seit
12.10.2026).

Die Fortschritts-Zeilenmuster sind an echten Mitschnitten eines Baus gemessen (12.10.2026, Werkzeug-Commit
``f2c91cd7``, win-x64): mit und ohne ``--verbose``, Stufenenden, Fehlerausgabe. ``bauen`` selbst wird mit einer
Attrappe statt des echten Werkzeugs geprueft (``wz.laufen`` ersetzt) - ein Ende-zu-Ende-Lauf mit dem echten
Werkzeug ist von Hand gemessen (``PS5-PKG-Tool/NOTICE_ProsperoPkgTool.md``), nicht Teil der Testreihe.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("prosperopkgtool")

from ps5_validator.utils import prospero_pkg_tool as ppt     # noqa: E402
from ps5_validator.utils import ps5_pkg_werkzeug as wz       # noqa: E402


class WerkzeugSuchenTests(unittest.TestCase):
    def test_ohne_wurzeln_nichts_gefunden(self) -> None:
        self.assertEqual("", ppt.werkzeug_suchen([]))
        self.assertEqual("", ppt.werkzeug_suchen(None))

    def test_findet_die_eigene_datei_im_mitgelieferten_ordner(self) -> None:
        with tempfile.TemporaryDirectory() as wurzel:
            ordner = Path(wurzel, ppt.ORDNER, wz.unterordner())
            ordner.mkdir(parents=True)
            name = "ProsperoPkgTool.exe" if sys.platform == "win32" else "ProsperoPkgTool"
            (ordner / name).write_bytes(b"x")
            self.assertEqual(str(ordner / name), ppt.werkzeug_suchen([wurzel]))

    def test_erste_wurzel_mit_treffer_gewinnt(self) -> None:
        name = "ProsperoPkgTool.exe" if sys.platform == "win32" else "ProsperoPkgTool"
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            ordner_b = Path(b, ppt.ORDNER, wz.unterordner())
            ordner_b.mkdir(parents=True)
            (ordner_b / name).write_bytes(b"x")
            self.assertEqual(str(ordner_b / name), ppt.werkzeug_suchen([a, b]))


class FortschrittTests(unittest.TestCase):
    """Zeilenmuster, wie sie das echte Werkzeug schreibt (12.10.2026 mitgeschnitten)."""

    def test_eine_abgeschlossene_stufe(self) -> None:
        bau = ppt.ProsperoBau()
        ergebnis = bau.zeile("[02:12:05] [+00:00:05.116] [stage 1/5] Inner image complete in 00:00:05.007.")
        self.assertEqual((25, "Inner image"), ergebnis)
        self.assertEqual(1, bau.stufe)

    def test_alle_fuenf_stufen_in_reihenfolge_steigen_an(self) -> None:
        bau = ppt.ProsperoBau()
        namen = ("Inner image", "NAPS", "Outer PFS", "CNT", "Finalize")
        werte = [bau.zeile("[t] [+d] [stage %d/5] %s complete in 1s." % (n, name))[0]
                 for n, name in enumerate(namen, start=1)]
        self.assertEqual(sorted(werte), werte, "jede Stufe meldet mindestens so viel wie die vorige")
        self.assertEqual(99, werte[-1])

    def test_ein_prozentwert_innerhalb_einer_stufe(self) -> None:
        bau = ppt.ProsperoBau()
        bau.zeile("[t] [+d] [stage 3/5] Building and AES-XTS encrypting the outer PFS...")
        prozent, text = bau.zeile("[02:12:08] [+00:00:08.434]      45%  Outer PFS encrypt (3'861/8'578)")
        self.assertEqual("Outer PFS encrypt (3'861/8'578)", text)
        # Stufe 3 deckt 30 bis 75 % ab, 45 % davon liegt dazwischen.
        self.assertGreater(prozent, 30)
        self.assertLess(prozent, 75)

    def test_fortschritt_vor_der_ersten_stufe_zaehlt_als_vorstufe(self) -> None:
        bau = ppt.ProsperoBau()
        prozent, text = bau.zeile("[t] [+d]       6%  Staging (31/618 MiB)  eboot.bin")
        self.assertEqual("Staging (31/618 MiB)  eboot.bin", text)
        self.assertGreaterEqual(prozent, 5)
        self.assertLess(prozent, 25)

    def test_eine_zeile_ohne_fortschritt_gibt_nichts_zurueck(self) -> None:
        bau = ppt.ProsperoBau()
        self.assertIsNone(bau.zeile("[t] [+d] Build started"))
        self.assertIsNone(bau.zeile("[t] [+d] Source folder: C:/Spiel"))

    def test_der_stand_springt_nie_zurueck(self) -> None:
        """Eine Stufe begonnen, aber noch nicht abgeschlossen: die naechste Stufe darf nicht niedriger melden."""
        bau = ppt.ProsperoBau()
        bau.zeile("[t] [+d] [stage 1/5] Inner image complete in 1s.")
        _p1, _ = bau.zeile("[t] [+d]      10%  something")
        bau.zeile("[t] [+d] [stage 2/5] NAPS complete in 1s.")
        p3, _ = bau.zeile("[t] [+d]      10%  something")
        self.assertGreaterEqual(p3, 25)


class BauenTests(unittest.TestCase):
    """``bauen`` ueber eine Attrappe des Werkzeugs (``wz.laufen`` ersetzt) - kein echter Prozess."""

    def test_baut_ohne_passcode_und_meldet_fortschritt(self) -> None:
        aufrufe: list[list[str]] = []

        def laufen(werkzeug, argumente, zeile=None, **_kw):
            aufrufe.append(list(argumente))
            zeile("[t] [+d] Build started")
            zeile("[t] [+d] [stage 1/5] Inner image complete in 1s.")
            zeile("[t] [+d] [stage 5/5] Finalize complete in 1s.")
            return 0, "Build finished in 1s; output 100 bytes.\nOutput: %s\n" % ziel

        with tempfile.TemporaryDirectory() as t:
            ziel = os.path.join(t, "ziel", "x.pkg")
            Path(os.path.dirname(ziel)).mkdir()
            Path(ziel).write_bytes(b"pkg")
            fortschritt, zeilen = [], []
            with mock.patch.object(wz, "laufen", side_effect=laufen):
                pfad = ppt.bauen("werkzeug", os.path.join(t, "quelle"), ziel, content_id="C", title_id="T",
                                 zeile=zeilen.append, fortschritt=lambda p, d: fortschritt.append((p, d)))
        self.assertEqual(ziel, pfad)
        self.assertIn("--no_passcode", aufrufe[0])
        self.assertNotIn("--passcode", aufrufe[0])
        self.assertIn("--content-id", aufrufe[0])
        self.assertIn("C", aufrufe[0])
        self.assertIn("--title-id", aufrufe[0])
        self.assertEqual([(25, "Inner image"), (99, "Finalize")], fortschritt)
        self.assertEqual(["[t] [+d] Build started"], zeilen)

    def test_mit_passcode_geht_er_in_die_argumente(self) -> None:
        aufrufe: list[list[str]] = []

        def laufen(werkzeug, argumente, zeile=None, **_kw):
            aufrufe.append(list(argumente))
            return 0, "Output: %s\n" % ziel

        with tempfile.TemporaryDirectory() as t:
            ziel = os.path.join(t, "x.pkg")
            Path(ziel).write_bytes(b"pkg")
            with mock.patch.object(wz, "laufen", side_effect=laufen):
                ppt.bauen("werkzeug", t, ziel, passcode="x" * 32)
        self.assertIn("--passcode", aufrufe[0])
        self.assertIn("x" * 32, aufrufe[0])
        self.assertNotIn("--no_passcode", aufrufe[0])

    def test_ein_fehler_des_werkzeugs_wird_zu_fehler(self) -> None:
        def laufen(werkzeug, argumente, zeile=None, **_kw):
            zeile("Error: Backup folder does not exist. (Parameter 'options')")
            return 2, "Error: Backup folder does not exist. (Parameter 'options')\n"

        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(wz, "laufen", side_effect=laufen):
                with self.assertRaises(wz.Fehler) as cm:
                    ppt.bauen("werkzeug", "/nicht/da", os.path.join(t, "x.pkg"))
        self.assertIn("Backup folder does not exist", str(cm.exception))

    def test_abbruch_wird_durchgereicht(self) -> None:
        def laufen(werkzeug, argumente, zeile=None, **_kw):
            return -1, ""

        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(wz, "laufen", side_effect=laufen):
                with self.assertRaises(wz.Fehler) as cm:
                    ppt.bauen("werkzeug", t, os.path.join(t, "x.pkg"))
        self.assertEqual("abgebrochen", str(cm.exception))

    def test_erfolg_ohne_ausgabedatei_ist_trotzdem_ein_fehler(self) -> None:
        """Keine stille Aktion: meldet das Werkzeug Erfolg, die Datei liegt aber nicht da, ist das ein Fehler."""
        def laufen(werkzeug, argumente, zeile=None, **_kw):
            return 0, "Output: /nirgendwo/x.pkg\n"

        with tempfile.TemporaryDirectory() as t:
            with mock.patch.object(wz, "laufen", side_effect=laufen):
                with self.assertRaises(wz.Fehler):
                    ppt.bauen("werkzeug", t, os.path.join(t, "x.pkg"))

    def test_der_zielordner_wird_angelegt(self) -> None:
        def laufen(werkzeug, argumente, zeile=None, **_kw):
            ziel = argumente[argumente.index("--out") + 1]
            Path(ziel).write_bytes(b"pkg")
            return 0, "Output: %s\n" % ziel

        with tempfile.TemporaryDirectory() as t:
            ziel = os.path.join(t, "neu", "unter", "x.pkg")
            with mock.patch.object(wz, "laufen", side_effect=laufen):
                pfad = ppt.bauen("werkzeug", t, ziel)
            self.assertTrue(os.path.isfile(pfad))


if __name__ == "__main__":
    unittest.main()
