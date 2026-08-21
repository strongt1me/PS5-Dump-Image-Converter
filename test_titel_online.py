# -*- coding: utf-8 -*-
"""Tests fuer den Online-Nachschlag von Titel und Content-ID.

Ausgewertet wird ein bereits geladenes HTML-Dokument; das Netz wird hier nie
angefasst. Die Beispiele sind der echten Seite nachgebildet, einschliesslich
des seit August vorangestellten Title-ID-Praefixes im Titel.

Nachgemessen am 16.08.2026 an acht Backups: Content-ID 8/8 exakt, Titel 7/8.
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ps5_validator.utils import titel_online as to
from ps5_validator.utils.param_manifest import create_default_param, save_param_json
from ps5_validator.utils import i18n

HAUPTDATEI = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "PS5ImageConverter_Pro_FINAL_revised.py")

SEITE = """<!doctype html><html><head>
<meta property="og:title" content="PPSA19015: Arcade Game Zone" />
<meta property="og:image" content="https://cdn.prosperopatches.com/titles/x/icon0.webp" />
</head><body>
<h1>PPSA19015: Arcade Game Zone</h1>
<div>Content ID: UP8016-PPSA19015_00-0489895718491618</div>
<div>Publisher View Some Publisher Publisher ID XX</div>
</body></html>"""


class TitleIdTests(unittest.TestCase):
    """Erkennung und Adressbildung."""

    def test_gueltige_ids(self):
        for wert in ("PPSA19015", "ppsa19015", " CUSA12345 "):
            self.assertTrue(to.ist_title_id(wert), wert)

    def test_ungueltige_ids(self):
        for wert in ("", "PPSA1901", "PPSA190155", "12345PPSA", None):
            self.assertFalse(to.ist_title_id(wert), repr(wert))

    def test_ps5_seite(self):
        self.assertEqual(to.seiten_url("PPSA19015"),
                         "https://prosperopatches.com/PPSA19015")

    def test_ps4_seite(self):
        self.assertEqual(to.seiten_url("CUSA12345"),
                         "https://orbispatches.com/CUSA12345")

    def test_kleinschreibung_wird_angehoben(self):
        self.assertEqual(to.seiten_url("ppsa19015"),
                         "https://prosperopatches.com/PPSA19015")

    def test_unbekanntes_praefix_ohne_adresse(self):
        self.assertEqual(to.seiten_url("ABCD12345"), "")
        self.assertEqual(to.seiten_url(""), "")


class TitelTests(unittest.TestCase):
    """titel_aus_html trennt Praefixe und Seitennamen ab."""

    def test_praefix_wird_abgetrennt(self):
        # Kernpunkt: Ohne das waere der Titel "PPSA19015: Arcade Game Zone".
        self.assertEqual(to.titel_aus_html(SEITE, "PPSA19015"), "Arcade Game Zone")

    def test_ohne_title_id_bleibt_das_praefix_stehen(self):
        # Ehrlich so dokumentiert: Ohne Bezugs-ID kann nichts abgetrennt werden.
        self.assertEqual(to.titel_aus_html(SEITE), "PPSA19015: Arcade Game Zone")

    def test_gedankenstrich_als_trenner(self):
        doc = '<meta property="og:title" content="PPSA19015 – Arcade Game Zone">'
        self.assertEqual(to.titel_aus_html(doc, "PPSA19015"), "Arcade Game Zone")

    def test_seitenname_wird_entfernt(self):
        doc = '<meta property="og:title" content="Teardown - Prospero Patches">'
        self.assertEqual(to.titel_aus_html(doc, "PPSA15246"), "Teardown")

    def test_h1_als_rueckfall(self):
        doc = "<html><body><h1>PPSA15246: Teardown</h1></body></html>"
        self.assertEqual(to.titel_aus_html(doc, "PPSA15246"), "Teardown")

    def test_html_entitaeten_werden_aufgeloest(self):
        doc = '<meta property="og:title" content="PPSA00001: Ratchet &amp; Clank">'
        self.assertEqual(to.titel_aus_html(doc, "PPSA00001"), "Ratchet & Clank")

    def test_ohne_titel(self):
        self.assertEqual(to.titel_aus_html("<html></html>", "PPSA19015"), "")
        self.assertEqual(to.titel_aus_html("", "PPSA19015"), "")


class ContentIdTests(unittest.TestCase):
    """content_id_aus_html findet die passende Kennung."""

    def test_einfacher_fall(self):
        self.assertEqual(to.content_id_aus_html(SEITE, "PPSA19015"),
                         "UP8016-PPSA19015_00-0489895718491618")

    def test_passende_wird_bevorzugt(self):
        # Eine Seite kann andere Regionen mitnennen - die gesuchte gewinnt.
        doc = ("EP1234-PPSA99999_00-AAAAAAAAAAAAAAAA "
               "UP8016-PPSA19015_00-0489895718491618")
        self.assertEqual(to.content_id_aus_html(doc, "PPSA19015"),
                         "UP8016-PPSA19015_00-0489895718491618")

    def test_ohne_passende_wird_die_erste_genommen(self):
        doc = "EP1234-PPSA99999_00-AAAAAAAAAAAAAAAA"
        self.assertEqual(to.content_id_aus_html(doc, "PPSA19015"),
                         "EP1234-PPSA99999_00-AAAAAAAAAAAAAAAA")

    def test_buchstabenkennungen(self):
        # Nicht jede Content-ID endet auf Ziffern.
        doc = "UP6856-PPSA15246_00-TRDNBASE00000000"
        self.assertEqual(to.content_id_aus_html(doc, "PPSA15246"),
                         "UP6856-PPSA15246_00-TRDNBASE00000000")

    def test_ohne_treffer(self):
        self.assertEqual(to.content_id_aus_html("nichts hier", "PPSA19015"), "")
        self.assertEqual(to.content_id_aus_html("", ""), "")


class ZusammenTests(unittest.TestCase):
    """metadaten_aus_html liefert beides oder laesst Felder weg."""

    def test_beides(self):
        d = to.metadaten_aus_html(SEITE, "PPSA19015")
        self.assertEqual(d, {"title": "Arcade Game Zone",
                             "content_id": "UP8016-PPSA19015_00-0489895718491618"})

    def test_nur_titel(self):
        doc = '<meta property="og:title" content="PPSA19015: Nur Titel">'
        self.assertEqual(to.metadaten_aus_html(doc, "PPSA19015"), {"title": "Nur Titel"})

    def test_leeres_dokument(self):
        self.assertEqual(to.metadaten_aus_html("", "PPSA19015"), {})


class ParamJsonTests(unittest.TestCase):
    """create_default_param nimmt die nachgeschlagenen Werte auf."""

    def test_ohne_zusatz(self):
        # Bis v1.8.52 entstand hier ein Dokument mit vier Feldern. Seit die
        # inhaltliche Pruefung dazukam, bestand ausgerechnet die selbst
        # erzeugte Datei sie nicht - deshalb ist sie jetzt vollstaendig.
        doc = create_default_param(title_id="PPSA19015")
        self.assertEqual(doc["titleId"], "PPSA19015")
        self.assertNotIn("contentId", doc)
        # Ohne bekannten Titel steht die Title-ID als Platzhalter drin:
        # localizedParameters ist ein Pflichtfeld, leer lassen geht nicht.
        self.assertEqual(doc["localizedParameters"]["en-US"]["titleName"],
                         "PPSA19015")
        self.assertEqual(doc["contentVersion"], "01.000.000")

    def test_mit_content_id_und_titel(self):
        doc = create_default_param(
            title_id="PPSA19015",
            content_id="UP8016-PPSA19015_00-0489895718491618",
            title="Arcade Game Zone")
        self.assertEqual(doc["contentId"], "UP8016-PPSA19015_00-0489895718491618")
        # Der Titel muss dort stehen, wo er auch gelesen wird.
        self.assertEqual(doc["localizedParameters"]["en-US"]["titleName"],
                         "Arcade Game Zone")
        self.assertEqual(doc["localizedParameters"]["defaultLanguage"], "en-US")

    def test_ergebnis_ist_gueltiges_json_und_wieder_lesbar(self):
        tmp = tempfile.mkdtemp(prefix="pj_test_")
        try:
            pfad = os.path.join(tmp, "param.json")
            save_param_json(create_default_param(
                title_id="PPSA19015",
                content_id="UP8016-PPSA19015_00-0489895718491618",
                title="Arcade Game Zone"), pfad)
            with io.open(pfad, encoding="utf-8") as fh:
                gelesen = json.load(fh)
            self.assertEqual(gelesen["titleId"], "PPSA19015")
            self.assertEqual(
                gelesen["localizedParameters"]["en-US"]["titleName"],
                "Arcade Game Zone")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


class VerdrahtungTests(unittest.TestCase):
    """Einbindung im Hauptprogramm."""

    @classmethod
    def setUpClass(cls):
        with io.open(HAUPTDATEI, encoding="utf-8") as fh:
            cls.quelle = fh.read()

    def test_modul_eingebunden(self):
        self.assertIn("from ps5_validator.utils import titel_online", self.quelle)

    def test_abrufmethode_vorhanden(self):
        self.assertIn("def _lookup_param_meta_online(", self.quelle)

    def test_frage_ohne_netz_steht_auf_ja(self):
        self.assertIn('default="yes" if default_yes else "no"', self.quelle)
        self.assertEqual(self._vorbelegung(online_erlaubt=False), True,
                         "Ohne Nachschlag geschieht alles lokal - dann Ja.")

    def test_frage_mit_netz_steht_auf_nein(self):
        # Ein Ja schickt die Title-ID an prosperopatches.com. Ein
        # versehentliches Enter darf das nicht ausloesen.
        #
        # Bis v1.8.52 hatte der Nachschlag eine eigene Frage mit
        # default_yes=False. v1.8.53 legte beide Fragen zusammen - und die
        # verbliebene benutzte die Vorgabe Ja. Gemessen wird deshalb die
        # Vorbelegung selbst, nicht mehr eine Zeichenkette im Quelltext:
        # Die haette den Rueckfall nicht bemerkt.
        self.assertEqual(self._vorbelegung(online_erlaubt=True), False)

    def _vorbelegung(self, *, online_erlaubt: bool):
        """Fragt _offer_create_param_json, mit welcher Vorbelegung es fragt."""
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        gemerkt = []

        def frage(titel, nachricht, *, online=False, default_yes=True):
            gemerkt.append(default_yes)
            return False        # Nein - es wird nichts geschrieben

        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui._append_to_log = lambda *a, **k: None
        gui._online_nachschlag_erlaubt = lambda: online_erlaubt
        gui._param_frage = frage

        with tempfile.TemporaryDirectory() as td:
            ordner = os.path.join(td, "PPSA19015-app0")
            os.makedirs(os.path.join(ordner, "sce_sys"))
            gui._offer_create_param_json(ordner, missing=True)

        self.assertEqual(len(gemerkt), 1, "Es muss genau eine Frage kommen.")
        return gemerkt[0]

    def test_werte_landen_in_der_ersatzdatei(self):
        self.assertIn('content_id=online.get("content_id", "")', self.quelle)
        # Seit v1.8.53 hat der Trophaeen-Container Vorrang vor dem Netz.
        self.assertIn('title=lokal.get("titleName") or online.get("title", "")',
                      self.quelle)

    def test_info_fenster_nutzt_dieselbe_titelauswertung(self):
        # Sonst stuende dort weiterhin "PPSA19015: Arcade Game Zone".
        self.assertIn("titel_online.titel_aus_html(html, tid)", self.quelle)

    def test_reparatur_scheitert_nie_am_nachschlag(self):
        # Der Abruf faengt jede Ausnahme ab und liefert ein leeres Dict.
        stelle = self.quelle.index("def _lookup_param_meta_online(")
        block = self.quelle[stelle:stelle + 1400]
        self.assertIn("except Exception as exc:", block)
        self.assertIn("return {}", block)


class I18nTests(unittest.TestCase):
    """Die neuen Texte liegen in beiden Sprachen vor."""

    SCHLUESSEL = (
        "dialog.title.param_json_online_lookup",
        "dialog.msg.param_json_online_lookup",
        "log.manual.param_json_online_found",
        "log.manual.param_json_online_failed",
    )

    def test_vorhanden(self):
        for k in self.SCHLUESSEL:
            self.assertIn(k, i18n.STRINGS, k)
            for sprache in ("de", "en"):
                self.assertTrue(i18n.STRINGS[k].get(sprache), f"{k}/{sprache}")

    def test_protokollzeilen_enden_mit_umbruch(self):
        for k in ("log.manual.param_json_online_found",
                  "log.manual.param_json_online_failed"):
            for sprache in ("de", "en"):
                self.assertTrue(i18n.STRINGS[k][sprache].endswith("\n"), f"{k}/{sprache}")

    def test_frage_nennt_die_empfaengerseite(self):
        # Der Nutzer soll vor der Zustimmung sehen, wohin die Title-ID geht.
        for sprache in ("de", "en"):
            self.assertIn("prosperopatches.com",
                          i18n.STRINGS["dialog.msg.param_json_online_lookup"][sprache])

    def test_platzhalter_stimmen_zwischen_den_sprachen(self):
        muster = re.compile(r"\{(v\d)\}")
        for k in self.SCHLUESSEL:
            self.assertEqual(set(muster.findall(i18n.STRINGS[k]["de"])),
                             set(muster.findall(i18n.STRINGS[k]["en"])), k)


if __name__ == "__main__":
    unittest.main(verbosity=2)
