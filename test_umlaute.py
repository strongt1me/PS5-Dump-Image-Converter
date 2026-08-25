"""Umlaute in den Benutzertexten - und die Grenze, an der sie aufhoeren.

Seit v1.8.99 stehen in allem, was der Nutzer liest, echte Umlaute: im
Protokoll des Hauptfensters, in den Meldungen des Validators, in der
Anzeigediagnose und im Doktor. Kommentare und Docstrings bleiben bewusst
bei ASCII - sie sind Entwicklertext.

**Die Falle, gegen die dieser Test steht.** Beim Umstellen wurden auch
Platzhalter uebersetzt: aus ``{hoehe}`` wurde ``{höhe}``. Die Zeichenkette
sah danach richtig aus, aber ``format`` fand den Namen nicht mehr - der
Aufrufer uebergibt ``hoehe=...``. Sechzehn Tests fielen um, und in der
Oberflaeche waere statt der Zahl die geschweifte Klammer stehen geblieben.
Ein Platzhaltername ist eine Kennung, keine Sprache.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

from ps5_validator.utils.i18n import STRINGS, translate

#: ``{name}``, ``{name!r}``, ``{name:>4}`` - erfasst wird nur der Name.
PLATZHALTER = re.compile(r"\{([^{}]*?)(?:![rsa])?(?::[^{}]*)?\}")


class PlatzhalterTests(unittest.TestCase):
    """Namen in geschweiften Klammern muessen ASCII-Kennungen bleiben."""

    def test_kein_platzhalter_traegt_einen_umlaut(self) -> None:
        schlecht = []
        for schluessel, sprachen in STRINGS.items():
            for sprache, text in sprachen.items():
                if not isinstance(text, str):
                    continue
                for name in PLATZHALTER.findall(text):
                    if name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",
                                                 name):
                        schlecht.append((schluessel, sprache, name))
        self.assertEqual(schlecht, [], "Platzhalter ist keine Kennung mehr")

    def test_die_bildhinweise_werden_wirklich_gefuellt(self) -> None:
        """Genau hier ging es kaputt - deshalb noch einmal am Ergebnis."""
        for schluessel in ("settings_dialog.background_hint",
                           "settings_dialog.sidebar_background_hint"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    gefuellt = translate(sprache, schluessel,
                                         breite=2560, hoehe=1440)
                    self.assertIn("2560", gefuellt)
                    self.assertIn("1440", gefuellt)
                    self.assertNotIn("{", gefuellt)

    def test_jeder_deutsche_text_laesst_sich_fuellen(self) -> None:
        """Ein uebersehener Platzhalter faellt sonst erst im Betrieb auf."""
        kaputt = []
        for schluessel, sprachen in STRINGS.items():
            text = sprachen.get("de")
            if not isinstance(text, str) or "{" not in text:
                continue
            roh = PLATZHALTER.findall(text)
            # Positionsplatzhalter ({} und {0}) sind zulaessig - sie werden
            # mit Argumenten gefuellt, nicht mit Namen. Geprueft wird hier
            # nur, ob die BENANNTEN noch Kennungen sind.
            if any(n == "" or n.isdigit() for n in roh):
                continue
            namen = set(roh)
            if not all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", n)
                       for n in namen):
                continue
            try:
                text.format(**{n: "x" for n in namen})
            except (KeyError, IndexError) as exc:
                # Nur der fehlende Name zaehlt. Ein ValueError bedeutet
                # bloss, dass die Formatangabe eine Zahl erwartet
                # ({groesse:.1f}) und der Test hier "x" einsetzt - das
                # sagt ueber den Platzhalternamen nichts aus.
                kaputt.append((schluessel, str(exc)))
            except ValueError:
                pass
        self.assertEqual(kaputt, [])


class UmlautTests(unittest.TestCase):
    """Stichproben: Kommt der Umlaut wirklich beim Nutzer an?"""

    #: Wortpaare, die in der Oberflaeche haeufig auftauchen. Steht die
    #: Umschrift noch da, ist die Umstellung an dieser Stelle liegen
    #: geblieben.
    UMSCHRIFT = ("fuer", "ueber", "geprueft", "vollstaendig", "Groesse",
                 "moeglich", "zurueck", "waehrend", "verfuegbar",
                 "gewaehlt", "Schluessel", "ungueltig", "Auffaelligkeit")

    def test_die_deutschen_texte_sind_frei_von_umschrift(self) -> None:
        schlecht = []
        for schluessel, sprachen in STRINGS.items():
            text = sprachen.get("de")
            if not isinstance(text, str):
                continue
            for wort in self.UMSCHRIFT:
                if re.search(r"\b%s\b" % re.escape(wort), text):
                    schlecht.append((schluessel, wort))
        self.assertEqual(schlecht, [], "Umschrift in einem Benutzertext")

    def test_die_anzeigediagnose_schreibt_umlaute(self) -> None:
        from ps5_validator.utils import anzeige_diagnose as ad
        quelle = (PROJEKT / "ps5_validator" / "utils"
                  / "anzeige_diagnose.py").read_text(encoding="utf-8")
        self.assertIn("Auffälligkeit", quelle)
        self.assertTrue(hasattr(ad, "Bildlage"))

    def test_die_umstellung_hat_die_kommentare_nicht_angefasst(self) -> None:
        """Gegenprobe: Getauscht wurden Zeichenketten, nicht Entwicklertext.

        Anders als zuerst angenommen haelt das Projekt seine Kommentare
        **nicht** durchgehend bei ASCII - 468 Kommentarzeilen trugen schon
        vor der Umstellung Umlaute, davor wie danach dieselbe Zahl. Eine
        Obergrenze zu behaupten waere also falsch gewesen.

        Was hier zaehlt, ist das Gegenteil: In den Kommentaren steht die
        Umschrift weiterhin. Waere der Lauf versehentlich ueber sie
        hinweggegangen, waere sie dort verschwunden.
        """
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"
                  ).read_text(encoding="utf-8")
        kommentare = [z.strip() for z in quelle.split(chr(10))
                      if z.strip().startswith("#")]
        self.assertTrue(kommentare, "keine Kommentare gefunden")
        umschrift = sum(1 for z in kommentare
                        if re.search(r"\b(fuer|ueber|waere|laeuft)\b", z))
        self.assertGreater(umschrift, 100,
                           "Die Kommentare wurden mit umgestellt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
