# -*- coding: utf-8 -*-
"""Der Debug-PKG-Builder darf nicht blind bauen und nicht einfrieren.

Zwei Befunde aus der Werkzeugpruefung vom 04.09.2026:

**Das PFS-Abbild wurde ueberhaupt nicht geprueft.** Der Dateidialog laesst
alles zu, und der Pfad ging ungeprueft an ``build_debug_pkg``. Nachgemessen:
eine 0-Byte-Datei ergab ein Paket vom Typ ``full_debug`` (67360 Bytes), eine
PNG-Datei ebenso (132896 Bytes) - beide Male mit der Meldung "Debug-.pkg
erstellt". Der Fehlgriff fiel erst an der Konsole auf, wo das Paket nicht
installiert.

**Der Bau lief im Tk-Hauptstrang.** Bei angegebenem PFS-Abbild kopiert
``build_debug_pkg`` die komplette Datei in die ``.pkg``. Bei zig Gigabyte
stand die Oberflaeche minutenlang still, Windows meldete "Keine Rueckmeldung"
- und wer das Programm daraufhin abschoss, tat es mitten im Schreiben.

Geprueft wird beides ohne Fenster: die Bildpruefung an echten Dateien, der
Faden am Syntaxbaum (dass der Bau ueberhaupt in einem eigenen Faden liegt).
"""
from __future__ import annotations

import ast
import os
import struct
import sys
import tempfile
import unittest

PROJEKT = os.path.dirname(os.path.abspath(__file__))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung

pruefumgebung.umlenken("debug_pkg_builder")

import PS5ImageConverter_Pro_FINAL_revised as hauptprogramm

G = hauptprogramm.PS5ConverterGUI
HAUPTDATEI = os.path.join(PROJEKT, "PS5ImageConverter_Pro_FINAL_revised.py")


class BildpruefungTests(unittest.TestCase):
    """Was sicher falsch ist, wird abgelehnt; Zweifelhaftes erfragt."""

    @classmethod
    def setUpClass(cls) -> None:
        # Ohne __init__: Die Pruefung liest nur Dateien, dafuer braucht es
        # keine Oberflaeche. Uebersetzt wird ueber einen Platzhalter, damit
        # der Text nicht am Sprachstand des Anwenders haengt.
        cls.gui = G.__new__(G)
        cls.gui._t = lambda schluessel, **k: "%s %r" % (schluessel, sorted(k))

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="debugpkg_bild_")
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self) -> None:
        import shutil
        shutil.rmtree(self.ordner, ignore_errors=True)

    def _datei(self, name: str, inhalt: bytes) -> str:
        pfad = os.path.join(self.ordner, name)
        with open(pfad, "wb") as datei:
            datei.write(inhalt)
        return pfad

    def _echtes_pfs(self) -> str:
        kopf = bytearray(4096)
        struct.pack_into("<q", kopf, 0x08, G._PFS_MAGIC)
        return self._datei("echt.pfs", bytes(kopf))

    def test_fehlende_datei_wird_abgelehnt(self) -> None:
        fehlt = os.path.join(self.ordner, "gibtsnicht.pfs")
        self.assertTrue(self.gui._debug_pkg_bild_pruefen(fehlt))

    def test_ordner_wird_abgelehnt(self) -> None:
        self.assertTrue(self.gui._debug_pkg_bild_pruefen(self.ordner))

    def test_leere_datei_wird_abgelehnt(self) -> None:
        """Der gemessene Fall: 0 Bytes ergaben ein 67360-Byte-Paket."""
        leer = self._datei("leer.pfs", b"")
        self.assertTrue(self.gui._debug_pkg_bild_pruefen(leer))

    def test_ein_echtes_abbild_geht_durch(self) -> None:
        """Sonst hiesse 'nichts kaputt' auch 'nichts geht mehr'."""
        self.assertEqual("", self.gui._debug_pkg_bild_pruefen(self._echtes_pfs()))
        self.assertTrue(G._sieht_nach_pfs_aus(self._echtes_pfs()))

    def test_eine_png_wird_nicht_abgelehnt_aber_erkannt(self) -> None:
        """Der zweite gemessene Fall - hier wird gefragt, nicht abgewiesen.

        Hart abzulehnen waere zu viel: Der Bauplan kann sich aendern, und ein
        bewusster Sonderfall soll moeglich bleiben. Erkannt werden muss der
        Fehlgriff trotzdem.
        """
        png = self._datei("bild.png", b"\x89PNG\r\n\x1a\n" + b"x" * 200)
        self.assertEqual("", self.gui._debug_pkg_bild_pruefen(png))
        self.assertFalse(G._sieht_nach_pfs_aus(png))

    def test_eine_abgeschnittene_datei_gilt_nicht_als_pfs(self) -> None:
        kurz = self._datei("kurz.pfs", b"\x00" * 8)
        self.assertFalse(G._sieht_nach_pfs_aus(kurz))

    def test_die_magic_stammt_aus_derselben_quelle_wie_der_validator(self) -> None:
        """Zwei Zahlen fuer dasselbe laufen frueher oder spaeter auseinander."""
        from ps5_validator.modules.ffpfs_validator import PFS_MAGIC_VALUE

        self.assertEqual(PFS_MAGIC_VALUE, G._PFS_MAGIC)


class BaufadenTests(unittest.TestCase):
    """Der Bau gehoert in einen eigenen Faden, die Dialoge in den Hauptstrang."""

    @classmethod
    def setUpClass(cls) -> None:
        with open(HAUPTDATEI, encoding="utf-8", errors="replace") as datei:
            cls.baum = ast.parse(datei.read())

    def _fenster(self):
        klasse = next(k for k in self.baum.body
                      if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        return next(k for k in klasse.body
                    if isinstance(k, ast.FunctionDef)
                    and k.name == "_show_debug_pkg_builder")

    def test_der_bau_laeuft_in_einem_faden(self) -> None:
        fenster = self._fenster()
        faeden = [k for k in ast.walk(fenster)
                  if isinstance(k, ast.Call)
                  and getattr(k.func, "attr", "") == "Thread"]
        self.assertTrue(
            faeden,
            "Der Bau laeuft wieder im Hauptstrang - bei einem grossen "
            "PFS-Abbild friert das Fenster minutenlang ein.")

    def test_build_debug_pkg_wird_nicht_direkt_im_fenster_gerufen(self) -> None:
        """Der Aufruf muss innerhalb der Fadenfunktion liegen."""
        fenster = self._fenster()
        arbeit = [f for f in ast.walk(fenster)
                  if isinstance(f, ast.FunctionDef) and f.name == "_arbeit"]
        self.assertEqual(1, len(arbeit), "Die Fadenfunktion fehlt.")
        drin = [k for k in ast.walk(arbeit[0])
                if isinstance(k, ast.Call)
                and getattr(k.func, "id", "") == "build_debug_pkg"]
        self.assertTrue(drin, "build_debug_pkg steht nicht im Arbeitsfaden.")
        # Und nirgends sonst im Fenster.
        alle = [k for k in ast.walk(fenster)
                if isinstance(k, ast.Call)
                and getattr(k.func, "id", "") == "build_debug_pkg"]
        self.assertEqual(len(drin), len(alle),
                         "build_debug_pkg wird auch ausserhalb des Fadens gerufen.")

    def test_das_ergebnis_geht_uebersetzt_ins_protokoll(self) -> None:
        """Frueher landete dort das rohe Python-dict."""
        with open(HAUPTDATEI, encoding="utf-8", errors="replace") as datei:
            quelle = datei.read()
        self.assertNotIn('f"[INFO] Debug-.pkg: {ergebnis}', quelle)
        from ps5_validator.utils.i18n import STRINGS
        for sprache in ("de", "en"):
            self.assertTrue(STRINGS["debug_pkg.log_done"].get(sprache, "").strip())

    def test_die_neuen_meldungen_gibt_es_zweisprachig(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for name in ("debug_pkg.image_missing", "debug_pkg.image_not_a_file",
                     "debug_pkg.image_empty", "debug_pkg.image_unreadable",
                     "debug_pkg.image_odd_title", "debug_pkg.image_odd_message"):
            with self.subTest(schluessel=name):
                self.assertIn(name, STRINGS)
                for sprache in ("de", "en"):
                    self.assertTrue(STRINGS[name].get(sprache, "").strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
