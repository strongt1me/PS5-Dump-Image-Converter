# -*- coding: utf-8 -*-
"""Handbuch, Anleitungen, FAQ und README gibt es in allen fuenf Sprachen der Oberflaeche (de, en, es, it, fr).

Die deutschen Fassungen sind die Vorlage (06.11.2026 uebersetzt). Dieser Waechter haelt fest:

* jede Sprachfassung ist da (HTML, bei Handbuch und Asset-Pack-Anleitung auch die PDF),
* sie traegt das richtige ``lang`` und dieselbe Struktur wie das Deutsche (Tag-Zahlen, ids, Verweise, ``<code>``/``<pre>``),
* die Programmoberflaeche oeffnet je Sprache die passende Datei und faellt auf Deutsch zurueck, wenn sie fehlt.

Wer das deutsche Dokument aendert, muss die vier Fassungen nachziehen - sonst schlaegt dieser Test an.
"""
from __future__ import annotations

import re
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import PS5ImageConverter_Pro_FINAL_revised as APP   # noqa: E402
from ps5_validator.utils.i18n import SUPPORTED_LANGUAGES   # noqa: E402

FREMDE = tuple(s for s in SUPPORTED_LANGUAGES if s != "de")

#: (Name des deutschen Dokuments, PDF noetig?)
HTML_DOKUMENTE = (
    ("BENUTZERHANDBUCH.html", True),
    ("Anleitungen/AMPR_Asset_Packs_Mitschnitt_Assistent.html", True),
    ("Anleitungen/ShadowMountPlus_fakelib_neue_Methode.html", False),
    ("Anleitungen/ShadowMountPlus_fakelib_alte_Methode.html", False),
)


def _fassung(name: str, sprache: str) -> str:
    stamm, endung = name.rsplit(".", 1)
    return "%s_%s.%s" % (stamm, sprache.upper(), endung)


def _tags(text: str) -> Counter:
    return Counter(re.findall(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)", text))


def _attr(text: str, name: str) -> Counter:
    return Counter(re.findall(r'\b%s="([^"]*)"' % name, text))


def _code(text: str) -> Counter:
    return Counter(re.sub(r"<[^>]+>", "", inhalt).strip()
                   for _, inhalt in re.findall(r"<(code|pre)\b[^>]*>(.*?)</\1>", text, re.S))


class VollstaendigkeitTests(unittest.TestCase):
    def test_die_programmsprachen_sind_de_en_es_it_fr(self) -> None:
        self.assertEqual(("de", "en", "es", "it", "fr"), tuple(SUPPORTED_LANGUAGES))

    def test_jede_fassung_ist_da(self) -> None:
        for name, mit_pdf in HTML_DOKUMENTE:
            for sprache in FREMDE:
                with self.subTest(dokument=name, sprache=sprache):
                    html = PROJEKT / _fassung(name, sprache)
                    self.assertTrue(html.is_file(), html)
                    if mit_pdf:
                        pdf = html.with_suffix(".pdf")
                        self.assertTrue(pdf.is_file(), pdf)
                        self.assertGreater(pdf.stat().st_size, 50_000)

    def test_faq_und_readme_in_allen_sprachen(self) -> None:
        for datei in ("FAQ.html", "FAQ_EN.html", "FAQ_ES.html", "FAQ_IT.html", "FAQ_FR.html",
                      "README.md", "README_EN.md", "README_ES.md", "README_IT.md", "README_FR.md"):
            with self.subTest(datei=datei):
                self.assertTrue((PROJEKT / datei).is_file())


class StrukturTests(unittest.TestCase):
    def test_fassungen_haben_die_struktur_des_deutschen(self) -> None:
        for name, _pdf in HTML_DOKUMENTE:
            de = (PROJEKT / name).read_text(encoding="utf-8")
            for sprache in FREMDE:
                with self.subTest(dokument=name, sprache=sprache):
                    text = (PROJEKT / _fassung(name, sprache)).read_text(encoding="utf-8")
                    self.assertIn('lang="%s"' % sprache, text[:2000])
                    self.assertNotIn("\r", text)
                    self.assertEqual(_tags(de), _tags(text), "Tags weichen vom Deutschen ab")
                    for a in ("id", "class", "src"):
                        self.assertEqual(_attr(de, a), _attr(text, a), a)
                    erwartet = Counter(h.replace("README.md", "README_%s.md" % sprache.upper())
                                       for h in _attr(de, "href").elements())
                    self.assertEqual(erwartet, _attr(text, "href"), "href")
                    # <code>/<pre>: nur die deutschen Randbemerkungen in <pre>-Diagrammen duerfen abweichen
                    fehlt = (_code(de) - _code(text))
                    nur_pre = all(("←" in k or "Spielordner oder Image" in k or "gewählter Speicherort" in k
                                   or k.startswith("Beispiel") or "Beispiel:" in k) for k in fehlt)
                    self.assertTrue(not fehlt or nur_pre, "code/pre weicht ab: %s" % list(fehlt)[:3])

    def test_das_handbuch_verweist_auf_die_readme_der_eigenen_sprache(self) -> None:
        for sprache in FREMDE:
            with self.subTest(sprache=sprache):
                text = (PROJEKT / ("BENUTZERHANDBUCH_%s.html" % sprache.upper())).read_text(encoding="utf-8")
                self.assertIn('href="README_%s.md"' % sprache.upper(), text)
                self.assertNotIn('href="README.md"', text)

    def test_readme_fassungen_verweisen_auf_ihr_handbuch(self) -> None:
        for sprache in FREMDE:
            with self.subTest(sprache=sprache):
                text = (PROJEKT / ("README_%s.md" % sprache.upper())).read_text(encoding="utf-8")
                self.assertIn("BENUTZERHANDBUCH_%s.html" % sprache.upper(), text)
                self.assertNotIn("(BENUTZERHANDBUCH.html)", text)

    def test_kein_dokument_behauptet_das_handbuch_gebe_es_nur_deutsch(self) -> None:
        for datei in ("FAQ_EN.html", "FAQ_ES.html", "FAQ_IT.html", "FAQ_FR.html", "README_EN.md", "README_ES.md",
                      "README_IT.md", "README_FR.md"):
            with self.subTest(datei=datei):
                text = (PROJEKT / datei).read_text(encoding="utf-8").lower()
                for verboten in ("german only", "solo en alemán", "solo in tedesco", "uniquement en allemand",
                                 "currently written in german", "escrito en alemán", "scritto in tedesco",
                                 "rédigé en allemand"):
                    self.assertNotIn(verboten, text)

    def test_kaum_deutscher_fliesstext_in_den_fassungen(self) -> None:
        woerter = re.compile(r"\b(und|oder|nicht|wird|werden|eine|einen|einer|dass|auch|aber|wenn|beim|zum|zur|über|"
                             r"Ordner|Datei|Dateien|Aufgabe|Hinweis|Einstellungen)\b")
        for name, _pdf in HTML_DOKUMENTE:
            for sprache in FREMDE:
                with self.subTest(dokument=name, sprache=sprache):
                    text = (PROJEKT / _fassung(name, sprache)).read_text(encoding="utf-8")
                    text = re.sub(r"<(style|script|code|pre)\b.*?</\1>", " ", text, flags=re.S)
                    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
                    text = re.sub(r"<[^>]+>", " ", text)
                    self.assertLess(len(woerter.findall(text)), 8)


class SprachwahlTests(unittest.TestCase):
    def test_sprachdatei_waehlt_die_fassung_der_sprache(self) -> None:
        gesehen: list[tuple] = []

        def falsch_aber_da(*teile: str) -> str:
            gesehen.append(teile)
            return "/x/" + "/".join(teile)

        with mock.patch.object(APP, "_bundled_resource", side_effect=falsch_aber_da):
            self.assertTrue(APP._sprachdatei("de", "BENUTZERHANDBUCH.html").endswith("BENUTZERHANDBUCH.html"))
            self.assertTrue(APP._sprachdatei("es", "BENUTZERHANDBUCH.html").endswith("BENUTZERHANDBUCH_ES.html"))
            self.assertTrue(APP._sprachdatei("fr", "Anleitungen", "X.html").endswith("Anleitungen/X_FR.html"))
            self.assertTrue(APP._sprachdatei("xx", "BENUTZERHANDBUCH.html").endswith("BENUTZERHANDBUCH.html"))

    def test_fehlt_die_fassung_kommt_deutsch(self) -> None:
        def nur_deutsch(*teile: str) -> str:
            return "" if teile[-1].endswith("_IT.html") else "/x/" + teile[-1]

        with mock.patch.object(APP, "_bundled_resource", side_effect=nur_deutsch):
            self.assertEqual("/x/BENUTZERHANDBUCH.html", APP._sprachdatei("it", "BENUTZERHANDBUCH.html"))

    def test_echte_dateien_werden_gefunden(self) -> None:
        for sprache in SUPPORTED_LANGUAGES:
            with self.subTest(sprache=sprache):
                pfad = APP._sprachdatei(sprache, "BENUTZERHANDBUCH.html")
                self.assertTrue(pfad and Path(pfad).is_file())
                erwartet = "BENUTZERHANDBUCH.html" if sprache == "de" else "BENUTZERHANDBUCH_%s.html" % sprache.upper()
                self.assertEqual(erwartet, Path(pfad).name)

    def test_knoepfe_oeffnen_die_datei_der_sprache(self) -> None:
        for sprache in SUPPORTED_LANGUAGES:
            app = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
            app.root = None
            app._current_language = sprache
            with self.subTest(sprache=sprache), \
                    mock.patch.object(APP, "_system_oeffnen_versuchen", return_value=(True, "")) as oeffnen:
                APP.PS5ConverterGUI._open_benutzerhandbuch(app)
                geoeffnet = Path(str(oeffnen.call_args[0][0])).name
                self.assertEqual("BENUTZERHANDBUCH.html" if sprache == "de"
                                 else "BENUTZERHANDBUCH_%s.html" % sprache.upper(), geoeffnet)
            with self.subTest(sprache=sprache, knopf="asset-pack"), \
                    mock.patch.object(APP, "_system_oeffnen_versuchen", return_value=(True, "")) as oeffnen:
                APP.PS5ConverterGUI._open_assetpack_anleitung(app)
                geoeffnet = Path(str(oeffnen.call_args[0][0])).name
                stamm = "AMPR_Asset_Packs_Mitschnitt_Assistent"
                self.assertEqual(stamm + ".html" if sprache == "de" else "%s_%s.html" % (stamm, sprache.upper()),
                                 geoeffnet)


class EinbettungTests(unittest.TestCase):
    def test_spec_dateien_betten_alle_fassungen_ein(self) -> None:
        for spec in ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec", "PS5ImageConverter_Pro_macos.spec"):
            text = (PROJEKT / spec).read_text(encoding="utf-8")
            for sprache in FREMDE:
                for datei in ("BENUTZERHANDBUCH_%s.html", "README_%s.md", "FAQ_%s.html"):
                    with self.subTest(spec=spec, datei=datei % sprache.upper()):
                        self.assertIn("'%s'" % (datei % sprache.upper()), text)

    def test_bauskript_nimmt_die_pdfs_mit(self) -> None:
        text = (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")
        for sprache in FREMDE:
            for datei in ("BENUTZERHANDBUCH_%s.pdf", "FAQ_%s.pdf", "README_%s.md"):
                with self.subTest(datei=datei % sprache.upper()):
                    self.assertIn('"%s"' % (datei % sprache.upper()), text)

    def test_macos_workflow_beobachtet_die_fassungen(self) -> None:
        text = (PROJEKT / ".github" / "workflows" / "macos-buendel.yml").read_text(encoding="utf-8")
        for sprache in FREMDE:
            for datei in ("BENUTZERHANDBUCH_%s.html", "FAQ_%s.html", "README_%s.md"):
                with self.subTest(datei=datei % sprache.upper()):
                    self.assertIn("'%s'" % (datei % sprache.upper()), text)


if __name__ == "__main__":
    unittest.main()
