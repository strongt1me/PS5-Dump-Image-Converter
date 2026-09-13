# -*- coding: utf-8 -*-
"""Aufgabe 4 (.ffpkg -> Ordner/exFAT) muss Dateien > 2 GB entpacken koennen.

Hintergrund (13.09.2026): Der eingebettete UFS2Tool 4.1 liest ueber den
Dokan-Mount keine Dateien > 2 GB (int32-Grenze); der mount-freie
``UFS2Tool extract`` scheiterte an derselben Grenze im Werkzeug. Behoben durch:
* gepatchtes UFS2Tool (Ufs2Image.ReadFileToStream/ExtractFile streamen statt
  byte[]), gebuendelt je Plattform - Integritaet ueber pruefsummen.json;
* ``_extract_ffpkg_to_folder_via_ufs2tool`` leitet Dateien > 2 GB auf den
  mount-freien ``extract`` um, statt sie ueber den Dokan-Mount zu kopieren.

Die Wege selbst sind an einer echten 6,8-GB-Datei byte-genau geprueft; hier
stehen die Regressionswaechter, die das nicht wieder zurueckfallen lassen.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unittest

HIER = os.path.dirname(os.path.abspath(__file__))
HAUPT = os.path.join(HIER, "PS5ImageConverter_Pro_FINAL_revised.py")
I18N = os.path.join(HIER, "ps5_validator", "utils", "i18n.py")
PRUEF = os.path.join(HIER, "UFS2Tool-4.1", "pruefsummen.json")


def _methode(quelle: str, name: str) -> str:
    m = re.search(r"\n    def %s\(.*?(?=\n    def )" % re.escape(name), quelle, re.S)
    assert m, "Methode %s nicht gefunden" % name
    return m.group(0)


class A4GrossdateiRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quelle = open(HAUPT, encoding="utf-8", errors="replace").read()
        cls.rumpf = _methode(cls.quelle, "_extract_ffpkg_to_folder_via_ufs2tool")

    def test_schwelle_ist_2gb_nicht_4gb(self):
        # Die echte Grenze des Werkzeugs ist 2 GB (int32), nicht 4 GB.
        self.assertIn("file_size >= 2 * 1024 ** 3", self.rumpf,
                      "Die >2-GB-Erkennung fehlt oder steht noch auf 4 GB.")
        self.assertNotIn("file_size >= 4 * 1024 ** 3", self.rumpf,
                         "Alte 4-GB-Schwelle noch da - 2-4-GB-Dateien fielen durch.")

    def test_grossdatei_wird_mountfrei_entpackt(self):
        # Im Oversize-Zweig muss auf den mount-freien extract umgeleitet werden.
        self.assertIn("oversize", self.rumpf)
        self.assertIn("_ffpkg_ueber_unterbefehl_entpacken", self.rumpf,
                      "Der Oversize-Zweig leitet nicht auf den mount-freien extract um.")
        self.assertIn("ffpkg.grossdatei_mountfrei", self.rumpf,
                      "Der Umschalt-Hinweis (i18n) fehlt.")

    def test_i18n_schluessel_zweisprachig(self):
        from ps5_validator.utils.i18n import STRINGS
        eintrag = STRINGS.get("ffpkg.grossdatei_mountfrei")
        self.assertIsNotNone(eintrag, "i18n-Schluessel ffpkg.grossdatei_mountfrei fehlt")
        self.assertTrue(eintrag.get("de") and eintrag.get("en"),
                        "de/en fuer ffpkg.grossdatei_mountfrei unvollstaendig")


class UFS2ToolIntegritaet(unittest.TestCase):
    """Die gebuendelten Binaerdateien muessen zu pruefsummen.json passen -
    sonst verweigert die Laufzeit-Integritaetspruefung das Werkzeug."""

    def test_pruefsummen_passen_zu_binaerdateien(self):
        with open(PRUEF, encoding="utf-8") as f:
            daten = json.load(f)
        basis = os.path.join(HIER, "UFS2Tool-4.1")
        geprueft = 0
        for plattform, info in daten["plattformen"].items():
            pfad = os.path.join(basis, plattform, info["datei"])
            if not os.path.isfile(pfad):
                continue  # Plattform-Binaer nicht vorhanden (z.B. nur teils gebaut)
            h = hashlib.sha256()
            with open(pfad, "rb") as fh:
                for brocken in iter(lambda: fh.read(1 << 20), b""):
                    h.update(brocken)
            self.assertEqual(info["sha256"], h.hexdigest(),
                             "%s: Binaer weicht von pruefsummen.json ab" % plattform)
            self.assertEqual(info["bytes"], os.path.getsize(pfad),
                             "%s: Groesse weicht von pruefsummen.json ab" % plattform)
            geprueft += 1
        self.assertGreater(geprueft, 0, "keine UFS2Tool-Binaerdatei gefunden")


if __name__ == "__main__":
    unittest.main(verbosity=2)
