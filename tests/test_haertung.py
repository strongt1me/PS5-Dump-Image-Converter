# -*- coding: utf-8 -*-
"""Haertung (v1.9.79): XML aus dem Netz, Verknuepfungen in Archiven, Lesegrenzen, Mindest-Python.

Jede Pruefung steht gegen einen Fehlerfall, der vorher durchging:

* ``xml_auswerten`` parste jedes Dokument, auch eines mit Entity-Aufblaehung ("Billion Laughs") oder in UTF-16.
* ``archiv_quelle.entpacken`` pruefte die Pfade im ZIP, aber nicht, wohin eine von 7-Zip angelegte Verknuepfung
  zeigt.
* Mehrere ``urlopen``-Stellen lasen die ganze Antwort in den Speicher.
* Doktor und README nannten Python 3.10 als Mindestfassung, obwohl das Packwerkzeug ``tomllib`` (ab 3.11) braucht.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import archiv_quelle as aq  # noqa: E402
from ps5_validator.utils import ps4pkg_updates as upd  # noqa: E402

GUTE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<titlepatch titleid="CUSA00775" status="alive">
  <tag name="CUSA00775_00" mandatory="true">
    <package version="01.09" size="1234567" digest="ABCDEF" manifest_url="http://dl.example/CUSA00775.json"
             content_id="EP0000-CUSA00775_00-TETRISULTIMATE00" system_ver="0x05050000" type="patch"/>
  </tag>
</titlepatch>"""


class XmlAusDemNetz(unittest.TestCase):
    def test_ein_gewoehnliches_dokument_wird_gelesen(self) -> None:
        info = upd.xml_auswerten(GUTE_XML)
        self.assertIsNotNone(info, "Der Wachposten darf das echte Format nicht abweisen.")
        self.assertEqual("01.09", info.version)

    def test_typdeklaration_und_entity_werden_abgewiesen(self) -> None:
        aufblaehung = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY a "aaaaaaaaaa">'
                       '<!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;">]><titlepatch titleid="X">&b;</titlepatch>')
        for text in (aufblaehung, GUTE_XML.replace("<titlepatch", "<!doctype x><titlepatch", 1),
                     GUTE_XML.replace("<titlepatch", '<!ENTITY e "x"><titlepatch', 1)):
            with self.subTest(text=text[:50]):
                self.assertIsNone(upd.xml_auswerten(text))
                self.assertIsNone(upd.xml_auswerten(text.encode("utf-8")))

    def test_utf16_umgeht_die_suche_nicht(self) -> None:
        # In UTF-16 stehen zwischen den Buchstaben NUL-Bytes - die Textsuche saehe "<!DOCTYPE" dort nicht.
        text = GUTE_XML.replace("<titlepatch", "<!DOCTYPE x><titlepatch", 1)
        self.assertIsNone(upd.xml_auswerten(text.encode("utf-16")))


class VerknuepfungenImArchiv(unittest.TestCase):
    def test_ohne_verknuepfungen_keine_beanstandung(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "a").mkdir()
            (Path(basis) / "a" / "datei.bin").write_bytes(b"x")
            aq.verknuepfung_nach_aussen(basis)

    def _mit_nachgebauter_verknuepfung(self, basis: str, link: str, ziel_des_links: str):
        """``os.scandir`` meldet ``link`` als Verknuepfung und loest sie zu ``ziel_des_links`` auf.

        Unter Windows fehlt oft das Recht, echte Verknuepfungen anzulegen - der Test soll trotzdem laufen.
        """
        echt_scandir = os.scandir
        echt_realpath = os.path.realpath
        norm = os.path.normcase

        class _Eintrag:
            def __init__(self, eintrag):
                self._e = eintrag
                self.path = eintrag.path
                self.name = eintrag.name

            def is_symlink(self):
                return norm(self.path) == norm(link)

            def is_dir(self, follow_symlinks=True):
                return self._e.is_dir(follow_symlinks=follow_symlinks)

        def _scandir(pfad="."):
            return [_Eintrag(e) for e in echt_scandir(pfad)]

        def _realpath(pfad, *a, **k):
            return ziel_des_links if norm(str(pfad)) == norm(link) else echt_realpath(pfad, *a, **k)

        return (mock.patch.object(aq.os, "scandir", side_effect=_scandir),
                mock.patch.object(aq.os.path, "realpath", side_effect=_realpath))

    def test_verknuepfung_nach_aussen_ist_ein_fehler(self) -> None:
        with tempfile.TemporaryDirectory() as aussen, tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "spiel").mkdir()
            link = os.path.join(basis, "spiel", "raus")
            Path(link).write_bytes(b"")                       # steht fuer die Verknuepfung
            scandir_patch, realpath_patch = self._mit_nachgebauter_verknuepfung(basis, link, aussen)
            with scandir_patch, realpath_patch:
                with self.assertRaises(aq.ArchivFehler) as ctx:
                    aq.verknuepfung_nach_aussen(basis)
            self.assertIn("raus", str(ctx.exception))

    def test_verknuepfung_nach_innen_ist_erlaubt(self) -> None:
        with tempfile.TemporaryDirectory() as basis:
            (Path(basis) / "a").mkdir()
            ziel = Path(basis) / "a" / "datei.bin"
            ziel.write_bytes(b"x")
            link = os.path.join(basis, "b.bin")
            Path(link).write_bytes(b"")
            scandir_patch, realpath_patch = self._mit_nachgebauter_verknuepfung(basis, link, str(ziel))
            with scandir_patch, realpath_patch:
                aq.verknuepfung_nach_aussen(basis)

    @unittest.skipUnless(hasattr(os, "symlink"), "keine Verknuepfungen")
    def test_echte_verknuepfung_nach_aussen(self) -> None:
        with tempfile.TemporaryDirectory() as aussen, tempfile.TemporaryDirectory() as basis:
            try:
                os.symlink(aussen, os.path.join(basis, "raus"), target_is_directory=True)
            except OSError as fehler:
                self.skipTest("Verknuepfung hier nicht anlegbar: %s" % fehler)
            with self.assertRaises(aq.ArchivFehler):
                aq.verknuepfung_nach_aussen(basis)

    def test_entpacken_ruft_die_pruefung_auf(self) -> None:
        quelle = (PROJEKT / "ps5_validator" / "utils" / "archiv_quelle.py").read_text(encoding="utf-8")
        koerper = quelle[quelle.index("def entpacken("):quelle.index("def verknuepfung_nach_aussen(")]
        self.assertIn("verknuepfung_nach_aussen(ziel)", koerper,
                      "Ohne diesen Aufruf bleibt die Pruefung totes Wissen.")


class Lesegrenzen(unittest.TestCase):
    #: Die einzige Stelle ohne Grenze: der Download der eigenen AMPR-Bauten (Datei, mit Pruefsumme verglichen).
    AUSNAHMEN = ("return antwort.read()",)

    def test_urlopen_im_hauptmodul_liest_nie_unbegrenzt(self) -> None:
        zeilen = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8").splitlines()
        offen = []
        gesehen = 0
        for nummer, zeile in enumerate(zeilen):
            if "urlopen(" not in zeile or zeile.lstrip().startswith("#"):
                continue
            gesehen += 1
            for folge in zeilen[nummer + 1:nummer + 5]:
                if re.search(r"\.read\(\s*\)", folge) and not any(a in folge for a in self.AUSNAHMEN):
                    offen.append("Zeile %d: %s" % (nummer + 1, folge.strip()))
                    break
        self.assertGreaterEqual(gesehen, 8, "Die Suche sieht die Netzzugriffe gar nicht mehr.")
        self.assertEqual([], offen, "Netzantwort ohne Obergrenze gelesen (NETZ_MAX_SEITE/NETZ_MAX_BILD):\n  "
                         + "\n  ".join(offen))

    def test_die_grenzen_gibt_es(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        self.assertRegex(text, r"(?m)^NETZ_MAX_SEITE = \d")
        self.assertRegex(text, r"(?m)^NETZ_MAX_BILD = \d")


class MindestPython(unittest.TestCase):
    def test_doktor_readme_und_tomllib_stimmen_ueberein(self) -> None:
        haupt = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        readme = (PROJEKT / "README.md").read_text(encoding="utf-8")
        werkzeug = (PROJEKT / "AMPR_PackTools-4.0" / "ampr_pack.py").read_text(encoding="utf-8")
        self.assertIn("import tomllib", werkzeug, "Der Anlass dieser Pruefung ist weggefallen - Grenze neu bedenken.")
        self.assertIn("if (haupt, neben) < (3, 11):", haupt)
        self.assertNotIn("3.10 oder neuer", haupt)
        self.assertIn("Python-3.11%2B", readme)
        self.assertIn("Python 3.11+", readme)
        self.assertNotIn("3.10+", readme)


if __name__ == "__main__":
    unittest.main()
