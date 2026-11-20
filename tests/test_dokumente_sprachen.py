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


def _readme(sprache: str) -> str:
    """Name der README einer Sprache. Seit 20.11.2026 (Nutzerwunsch: GitHub Englisch, Deutsch als Option) ist ``README.md`` die englische - die
    Startseite des Repos -, die deutsche heisst ``README_DE.md``; ``README_EN.md`` gibt es nicht mehr."""
    return "README.md" if sprache == "en" else "README_%s.md" % sprache.upper()


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
                      "README.md", "README_DE.md", "README_ES.md", "README_IT.md", "README_FR.md"):
            with self.subTest(datei=datei):
                self.assertTrue((PROJEKT / datei).is_file())
        self.assertFalse((PROJEKT / "README_EN.md").exists(), "die englische README ist README.md - eine zweite Kopie wuerde auseinanderlaufen")

    def test_readme_md_ist_die_englische_und_readme_de_die_deutsche(self) -> None:
        """Nutzerwunsch 20.11.2026: Auf GitHub steht alles Englisch, Deutsch ist eine Option - die Sprachleiste fuehrt in jeder README dorthin."""
        englisch = (PROJEKT / "README.md").read_text(encoding="utf-8")
        deutsch = (PROJEKT / "README_DE.md").read_text(encoding="utf-8")
        self.assertIn("**Convert, unpack and verify PS5 dumps", englisch)
        self.assertIn("**PS5-Dumps und Abbilder umwandeln", deutsch)
        leiste = ("**English: [README.md](README.md) · Deutsch: [README_DE.md](README_DE.md) · Español: [README_ES.md](README_ES.md) · "
                  "Italiano: [README_IT.md](README_IT.md) · Français: [README_FR.md](README_FR.md)**")
        for datei in ("README.md", "README_DE.md", "README_ES.md", "README_IT.md", "README_FR.md"):
            with self.subTest(datei=datei):
                self.assertIn(leiste, (PROJEKT / datei).read_text(encoding="utf-8"), "die Sprachleiste fehlt oder ist alt")
        for datei in ("README.md", "README_ES.md", "README_IT.md", "README_FR.md"):
            with self.subTest(maßgeblich=datei):
                self.assertIn("README_DE.md", (PROJEKT / datei).read_text(encoding="utf-8"), "die deutsche Fassung bleibt die maßgebliche")


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
                    erwartet = Counter(h.replace("README_DE.md", _readme(sprache))
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
                self.assertIn('href="%s"' % _readme(sprache), text)
                self.assertNotIn('href="README_DE.md"', text, "kein Handbuch einer anderen Sprache verweist auf die deutsche README")
                if sprache != "en":
                    self.assertNotIn('href="README.md"', text, "README.md ist die englische")

    def test_das_deutsche_handbuch_verweist_auf_die_deutsche_readme(self) -> None:
        text = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        self.assertIn('href="README_DE.md"', text)
        self.assertNotIn('href="README.md"', text, "README.md ist seit 20.11.2026 die englische")

    def test_readme_fassungen_verweisen_auf_ihr_handbuch(self) -> None:
        for sprache in FREMDE:
            with self.subTest(sprache=sprache):
                text = (PROJEKT / _readme(sprache)).read_text(encoding="utf-8")
                self.assertIn("BENUTZERHANDBUCH_%s.html" % sprache.upper(), text)
                self.assertNotIn("(BENUTZERHANDBUCH.html)", text)

    def test_kein_dokument_behauptet_das_handbuch_gebe_es_nur_deutsch(self) -> None:
        for datei in ("FAQ_EN.html", "FAQ_ES.html", "FAQ_IT.html", "FAQ_FR.html", "README.md", "README_ES.md",
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
                for datei in ("BENUTZERHANDBUCH_%s.html" % sprache.upper(), _readme(sprache), "FAQ_%s.html" % sprache.upper()):
                    with self.subTest(spec=spec, datei=datei):
                        self.assertIn("'%s'" % datei, text)
            with self.subTest(spec=spec, datei="README_DE.md"):
                self.assertIn("'README_DE.md'", text)
                self.assertNotIn("README_EN.md", text)

    def test_bauskript_nimmt_die_pdfs_mit(self) -> None:
        text = (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")
        for sprache in FREMDE:
            for datei in ("BENUTZERHANDBUCH_%s.pdf" % sprache.upper(), "FAQ_%s.pdf" % sprache.upper(), _readme(sprache)):
                with self.subTest(datei=datei):
                    self.assertIn('"%s"' % datei, text)
        self.assertIn('"README_DE.md"', text)
        self.assertNotIn("README_EN.md", text)

    def test_macos_workflow_beobachtet_die_fassungen(self) -> None:
        text = (PROJEKT / ".github" / "workflows" / "macos-buendel.yml").read_text(encoding="utf-8")
        for sprache in FREMDE:
            for datei in ("BENUTZERHANDBUCH_%s.html" % sprache.upper(), "FAQ_%s.html" % sprache.upper(), _readme(sprache)):
                with self.subTest(datei=datei):
                    self.assertIn("'%s'" % datei, text)
        self.assertIn("'README_DE.md'", text)
        self.assertNotIn("README_EN.md", text)


if __name__ == "__main__":
    unittest.main()
