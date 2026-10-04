"""Sind Benutzerhandbuch und FAQ aktuell - HTML und PDF, beide Sprachen der FAQ?

Wunsch des Nutzers vom 04.10.2026: Die FAQ "soll automatisch aktualisiert
werden bei Aenderungen am Programm, so wie auch das Benutzerhandbuch (PDF &
HTML inkl.)". Beim Release werden beide nachgefuehrt und die PDFs neu
gedruckt (Skill ``references/release.md``). Dieser Waechter schlaegt an, wenn
das vergessen wurde:

* Jede Datei traegt die Programmversion (``APP_VERSION``).
* Jede Ueberschrift des HTML - beim Handbuch die Kapitel und Abschnitte, bei
  der FAQ jede Frage - steht auch in der PDF. Wer das HTML aendert und die
  PDF nicht neu erzeugt, faellt hier auf; ein neu gedrucktes PDF besteht.

Die PDF wird mit ``pypdf`` gelesen (liegt in der ``.venv``). Verglichen wird
ohne Leerraum, weil die PDF Zeilen anders umbricht als der Browser.
"""
from __future__ import annotations

import html
import re
import sys
import unicodedata
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

try:
    from pypdf import PdfReader
except ImportError:                                   # pragma: no cover - nur ohne .venv
    PdfReader = None

#: (HTML, PDF, welche Ueberschriften muessen in der PDF stehen)
DOKUMENTE = (
    ("BENUTZERHANDBUCH.html", "BENUTZERHANDBUCH.pdf", ("h2", "h3")),
    ("FAQ.html", "FAQ.pdf", ("h2", "h3")),
    ("FAQ_EN.html", "FAQ_EN.pdf", ("h2", "h3")),
)


def _app_version() -> str:
    text = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
    treffer = re.search(r'^APP_VERSION = "(v[\d.]+)"', text, re.M)
    if not treffer:
        raise AssertionError("APP_VERSION nicht gefunden")
    return treffer.group(1)


def _flach(text: str) -> str:
    """Ohne Tags, Entitaeten und Leerraum; Ligaturen aufgeloest (NFKC), ohne Gross/klein.

    Gross/klein faellt weg, weil die PDF zeigt, was das CSS daraus macht: Das
    Inhaltsverzeichnis steht mit ``text-transform:uppercase`` als "CONTENTS" in
    der PDF, im HTML als "Contents" (am 04.10.2026 so aufgefallen).
    """
    text = re.sub(r"<[^>]+>", "", text)
    text = unicodedata.normalize("NFKC", html.unescape(text))
    return re.sub(r"\s+", "", text).casefold()


def _ueberschriften(html_text: str, tags: tuple[str, ...]) -> list[str]:
    gefunden = re.findall(r"<(h[1-6])\b[^>]*>(.*?)</\1>", html_text, re.S)
    return [_flach(inhalt) for tag, inhalt in gefunden if tag in tags and _flach(inhalt)]


class VersionTests(unittest.TestCase):

    def test_jede_html_traegt_die_programmversion(self):
        version = _app_version()
        for html_name, _pdf, _tags in DOKUMENTE:
            with self.subTest(datei=html_name):
                text = (PROJEKT / html_name).read_text(encoding="utf-8")
                titel = re.search(r"<title>(.*?)</title>", text, re.S).group(1)
                self.assertIn(version, titel, "Titel ohne %s" % version)
                self.assertIn("<strong>%s</strong>" % version, text, "Fusszeile ohne %s" % version)


@unittest.skipIf(PdfReader is None, "pypdf fehlt")
class PdfTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.texte = {}
        for _html, pdf_name, _tags in DOKUMENTE:
            leser = PdfReader(str(PROJEKT / pdf_name))
            roh = "".join(seite.extract_text() or "" for seite in leser.pages)
            cls.texte[pdf_name] = (_flach(roh), len(leser.pages), (PROJEKT / pdf_name).read_bytes())

    def test_jede_pdf_traegt_die_programmversion(self):
        version = _app_version()
        for _html, pdf_name, _tags in DOKUMENTE:
            with self.subTest(datei=pdf_name):
                self.assertIn(version, self.texte[pdf_name][0])

    def test_jede_ueberschrift_steht_auch_in_der_pdf(self):
        for html_name, pdf_name, tags in DOKUMENTE:
            ueberschriften = _ueberschriften((PROJEKT / html_name).read_text(encoding="utf-8"), tags)
            with self.subTest(datei=pdf_name):
                self.assertGreater(len(ueberschriften), 5, "Gegenprobe: keine Ueberschriften gelesen")
                fehlend = [u for u in ueberschriften if u not in self.texte[pdf_name][0]]
                self.assertEqual([], fehlend,
                                 "%s ist aelter als %s - PDF neu erzeugen (release.md Punkt 8)"
                                 % (pdf_name, html_name))

    def test_keine_lokalen_verweise(self):
        """Edge druckt relative Links als file:///C:/Users/<Name>/... - oeffentliches Repo."""
        for _html, pdf_name, _tags in DOKUMENTE:
            with self.subTest(datei=pdf_name):
                self.assertNotIn(b"file:///", self.texte[pdf_name][2])


if __name__ == "__main__":
    unittest.main()
