# -*- coding: utf-8 -*-
"""Deutsche und neutrale Texte der Direct-Stream-Oberflaeche (``direct_stream_texte``).

Die Dateien des Werkzeugs bleiben unveraendert; das Programm legt ein Skript davor, das die Texte im
Browser ersetzt. Geprueft wird hier, dass jeder sichtbare Text der Seite (``index.html``) eine deutsche
Fassung hat, dass die neutrale englische Fassung nirgends mehr vom Mac spricht, dass die Muster fuer
Meldungen mit Zahlen greifen und dass das Skript selbst gueltig aufgebaut ist.
"""
from __future__ import annotations

import html
import json
import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils import direct_stream  # noqa: E402
from ps5_validator.utils import direct_stream_texte as texte  # noqa: E402

WEB = PROJEKT / direct_stream.ORDNER / "web"

#: Texte, die auf Deutsch gleich bleiben (Namen, Einheiten, Zahlen, Beispielwerte des Werkzeugs).
GLEICH = re.compile(r"^(?:DIRECT STREAM.*|FOR PLAYSTATION 5|FOR PS5|PS5|Direct Stream|Name|Port|Turbo|Link|"
                    r"[\d.,/ —–-]*(?:MB/s|MiB|GB)?|/data/\S+|https?://\S+)$")


def _seitentexte() -> list[str]:
    """Sichtbare Texte und Beschriftungen aus index.html (ohne Skripte und Stile)."""
    seite = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>", "",
                   (WEB / "index.html").read_text(encoding="utf-8"), flags=re.S)
    gefunden = [html.unescape(t) for t in re.findall(r">([^<>]+)<", seite)]
    gefunden += [html.unescape(t) for t in re.findall(r'(?:placeholder|title|aria-label)="([^"]+)"', seite)]
    return sorted({" ".join(t.split()) for t in gefunden if re.search(r"[A-Za-z]{2,}", t)})


class SeitenTests(unittest.TestCase):
    def test_die_pruefung_findet_ueberhaupt_texte(self) -> None:
        self.assertGreater(len(_seitentexte()), 150)

    def test_jeder_text_der_seite_ist_deutsch(self) -> None:
        offen = [t for t in _seitentexte()
                 if texte.uebersetzen(t, "de") == t and not GLEICH.match(t)]
        self.assertEqual([], offen)

    def test_neutral_spricht_nie_vom_mac(self) -> None:
        mac = [t for t in _seitentexte() if re.search(r"\bMac\b", texte.uebersetzen(t, "en"))]
        self.assertEqual([], mac)

    def test_jeder_neutrale_schluessel_hat_ein_deutsches_gegenstueck(self) -> None:
        self.assertEqual([], [k for k in texte.NEUTRAL if k not in texte.DEUTSCH])

    def test_kein_deutscher_text_spricht_vom_mac(self) -> None:
        self.assertEqual([], [v for v in texte.DEUTSCH.values() if re.search(r"\bMac\b", v)])


class MusterTests(unittest.TestCase):
    def test_meldungen_mit_zahlen(self) -> None:
        for englisch, deutsch in (
                ("3 items", "3 Einträge"),
                ("2 selected", "2 gewählt"),
                ("Resuming at 4096 bytes", "Setze fort bei 4096 Bytes"),
                ("port must be a whole number between 1 and 65535.",
                 "port muss eine ganze Zahl zwischen 1 und 65535 sein."),
                ("Download server returned HTTP 404. Check the direct link or get a fresh one.",
                 "Der Download-Server antwortet mit HTTP 404. Link prüfen oder einen neuen holen.")):
            with self.subTest(englisch=englisch):
                self.assertEqual(deutsch, texte.uebersetzen(englisch, "de"))

    def test_unbekanntes_bleibt_wie_es_ist(self) -> None:
        self.assertEqual("spiel.pkg", texte.uebersetzen("spiel.pkg", "de"))

    def test_jedes_muster_ist_auch_in_javascript_gueltig(self) -> None:
        """Nur Bausteine, die Python und JavaScript gleich verstehen."""
        for muster, _ersatz in texte.DEUTSCH_MUSTER:
            with self.subTest(muster=muster):
                self.assertIsNone(re.search(r"\(\?P|\(\?<[=!]|\\[AZz]|\(\?[aiLmsux]", muster))
                re.compile(muster)


class SkriptTests(unittest.TestCase):
    def test_die_daten_sind_gueltiges_json(self) -> None:
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                skript = texte.skript(sprache)
                roh = re.search(r"var D = (\{.*?\});\n", skript, re.S).group(1)
                daten = json.loads(roh)
                self.assertEqual({"ganz", "muster", "teile"}, set(daten))

    def test_rueckverweise_werden_zu_javascript(self) -> None:
        daten = json.loads(re.search(r"var D = (\{.*?\});\n", texte.skript("de"), re.S).group(1))
        ersatz = [r for _m, r in daten["muster"]]
        self.assertTrue(any("$1" in r for r in ersatz))
        self.assertFalse(any(re.search(r"\\\d", r) for r in ersatz))

    def test_neutral_ohne_deutsch(self) -> None:
        skript = texte.skript("en")
        self.assertNotIn("Übertragungen", skript)
        self.assertIn("Computer-to-PS5", skript)

    def test_kein_ende_eines_skriptblocks_in_den_daten(self) -> None:
        self.assertNotIn("</", re.search(r"var D = (\{.*?\});\n", texte.skript("de"), re.S).group(1))

    def test_die_seite_bekommt_das_skript_einmal_im_kopf(self) -> None:
        seite = (WEB / "index.html").read_text(encoding="utf-8")
        neu = texte.seite_einrichten(seite, "de")
        self.assertEqual(1, neu.count(texte.SKRIPT_PFAD))
        self.assertLess(neu.index(texte.SKRIPT_PFAD), neu.index("/app.js"))
        self.assertIn('<html lang="de">', neu)


if __name__ == "__main__":
    unittest.main()
