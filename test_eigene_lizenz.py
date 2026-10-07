# -*- coding: utf-8 -*-
"""Die Lizenz des Programms selbst - Datei, Programm, Bau und Doku im Gleichklang.

Seit dem 07.10.2026 GPL-3.0-or-later (Nutzerentscheid; bis v1.9.64 MIT). Die
Datei ``LICENSE`` ist der unveraenderte Text der FSF, der Hinweis "Version 3
oder spaeter" steht in ``eigene_lizenz.HINWEIS``, in der README und in der
Registry.

Gemessen am 19.09.2026 (damals noch MIT): Das Repo wurde am 25.06.2026 mit
einer ``LICENSE`` angelegt. Am 06.07.2026 fiel sie beim Aufraeumen von
"Diverses" mit aus dem Repo - danach nannte das Programm eine Lizenz, ohne dass
das oeffentliche Repo den Text trug. Der Text, den das Programm unter Windows
in die Registry schreibt, nannte einen anderen Inhaber und ein Jahr, das mit
der Uhr mitlief; unter Linux und macOS meldete es "Lizenz liegt bei", obwohl
kein Bau sie enthielt.
"""
from __future__ import annotations

import datetime
import hashlib
import re
import shutil
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("eigene_lizenz")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import eigene_lizenz               # noqa: E402

DATEI = PROJEKT / eigene_lizenz.DATEINAME
#: Dieselbe FSF-Datei liegt seit Langem bei den GPL-3.0-Payloads.
GPL_KOPIE = PROJEKT / "helloworld" / "LICENSE-GPL-3.0.txt"
SPECS = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
         "PS5ImageConverter_Pro_macos.spec")


def _datei_text() -> str:
    """Der Text der Datei - Zeilenenden zaehlen nicht, der Wortlaut schon."""
    return DATEI.read_bytes().decode("utf-8").replace("\r\n", "\n")


class DateiTests(unittest.TestCase):
    """Die Datei im Projektordner."""

    def test_die_datei_liegt_im_projektordner(self) -> None:
        self.assertTrue(DATEI.is_file(), "LICENSE fehlt im Projektordner")

    def test_es_ist_der_unveraenderte_gpl_text(self) -> None:
        """Der Text der FSF darf nicht veraendert werden - auch nicht um einen Satz."""
        text = _datei_text()
        self.assertTrue(text.lstrip().startswith("GNU GENERAL PUBLIC LICENSE"), text[:80])
        self.assertIn("Version 3, 29 June 2007", text[:200])
        self.assertEqual(eigene_lizenz.TEXT_SHA256,
                         hashlib.sha256(text.encode("utf-8")).hexdigest())

    def test_die_datei_gleicht_der_mitgelieferten_gpl_kopie(self) -> None:
        self.assertEqual(GPL_KOPIE.read_bytes().decode("utf-8").replace("\r\n", "\n"),
                         _datei_text())

    def test_kennung_und_hinweis_sagen_version_3_oder_neuer(self) -> None:
        self.assertEqual("GPL-3.0-or-later", eigene_lizenz.SPDX)
        hinweis = eigene_lizenz.HINWEIS
        self.assertIn(f"\n{eigene_lizenz.COPYRIGHT}\n", hinweis)
        self.assertIn("either version 3 of the License, or", hinweis)
        self.assertIn("(at your option) any later version.", hinweis)
        self.assertIn("WITHOUT ANY WARRANTY", hinweis)
        self.assertNotIn("MIT", hinweis)

    @unittest.skipUnless(shutil.which("git") and (PROJEKT / ".git").exists(),
                         "keine Git-Arbeitskopie")
    def test_git_ignoriert_die_datei_nicht(self) -> None:
        """So ging sie verloren: verschoben in einen ignorierten Ordner."""
        lauf = subprocess.run(["git", "check-ignore", "-q", eigene_lizenz.DATEINAME],
                              cwd=PROJEKT, capture_output=True, check=False)
        self.assertEqual(1, lauf.returncode,
                         "git check-ignore: Rueckgabe 0 heisst ignoriert, 128 Fehler")


class _Spaeter(datetime.datetime):
    """Eine Uhr, die im Jahr 2031 steht."""

    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        return datetime.datetime(2031, 5, 1, 12, 0, tzinfo=tz)


class RegistryTests(unittest.TestCase):
    """Was das Programm unter Windows beim Start nach HKCU schreibt."""

    def _ausfuehren(self) -> tuple[bool, dict[str, str]]:
        geschrieben: dict[str, str] = {}
        winreg = types.SimpleNamespace(
            HKEY_CURRENT_USER=object(), REG_SZ=1,
            CreateKey=lambda _wurzel, _pfad: "schluessel",
            SetValueEx=lambda _key, name, _r, _typ, wert: geschrieben.__setitem__(name, wert),
            CloseKey=lambda _key: None)
        with mock.patch.dict(sys.modules, {"winreg": winreg}), \
                mock.patch.object(APP, "IST_WINDOWS", True):
            ok, _meldung = APP._register_license_runtime()
        return ok, geschrieben

    def test_eingetragen_werden_hinweis_und_pruefsumme_der_datei(self) -> None:
        """Der volle Text (35 KB) gehoert nicht in einen Registry-Wert - Hinweis und Pruefsumme schon."""
        ok, werte = self._ausfuehren()
        self.assertTrue(ok)
        self.assertEqual(eigene_lizenz.HINWEIS, werte["LicenseText"])
        self.assertEqual("GPL-3.0-or-later", werte["SPDX"])
        self.assertEqual(eigene_lizenz.NAME, werte["LicenseName"])
        self.assertEqual(hashlib.sha256(_datei_text().encode("utf-8")).hexdigest(),
                         werte["LicenseHashSHA256"])

    def test_die_alte_funktion_gibt_es_nicht_mehr(self) -> None:
        """Ihr Name sagte MIT - wer sie noch aufruft, soll scheitern statt Falsches zu lesen."""
        self.assertFalse(hasattr(APP, "_register_mit_license_runtime"))

    def test_das_jahr_laeuft_nicht_mit_der_uhr_mit(self) -> None:
        """Bis v1.9.28 stand dort das laufende Jahr statt 2026."""
        with mock.patch.object(datetime, "datetime", _Spaeter):
            ok, werte = self._ausfuehren()
        self.assertTrue(ok)
        self.assertTrue(werte["RegisteredAtUTC"].startswith("2031-"),
                        "Anker - die Uhr muss wirklich verstellt sein")
        self.assertIn(eigene_lizenz.COPYRIGHT, werte["LicenseText"])
        self.assertNotIn("2031", werte["LicenseText"])


class BauTests(unittest.TestCase):
    """Die gebauten Fassungen bringen die Datei mit."""

    def test_jeder_bauplan_legt_die_datei_bei(self) -> None:
        for spec in SPECS:
            with self.subTest(spec=spec):
                text = (PROJEKT / spec).read_text(encoding="utf-8")
                self.assertIn("_eigene_lizenz = os.path.join(_here, 'LICENSE')", text)
                self.assertIn("_datas.append((_eigene_lizenz, '.'))", text)

    def test_das_mac_buendel_nennt_denselben_inhaber(self) -> None:
        text = (PROJEKT / "PS5ImageConverter_Pro_macos.spec").read_text(encoding="utf-8")
        treffer = re.search(r"'NSHumanReadableCopyright':\s*'([^']*)'", text)
        self.assertIsNotNone(treffer)
        assert treffer is not None
        self.assertTrue(treffer.group(1).startswith(eigene_lizenz.COPYRIGHT),
                        treffer.group(1))
        self.assertIn(eigene_lizenz.SPDX, treffer.group(1))
        self.assertNotIn("MIT", treffer.group(1))

    def test_das_auslieferungsbuendel_nimmt_die_lizenzen_mit(self) -> None:
        text = (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"LICENSE"', text)
        self.assertIn('"THIRD_PARTY_LICENSES.md"', text)


class DokuTests(unittest.TestCase):
    """Wer das Repo oder die Fremdlizenzen liest, findet die eigene Lizenz."""

    def test_die_readme_verlinkt_die_datei(self) -> None:
        text = (PROJEKT / "README.md").read_text(encoding="utf-8")
        self.assertIn("(GPL-3.0-or-later)](LICENSE)", text)
        # Der Hinweis selbst, denn die Datei LICENSE sagt "oder spaeter" nicht.
        self.assertIn(eigene_lizenz.COPYRIGHT, text)
        self.assertIn("(at your option) any later version.", text)
        self.assertNotIn("[MIT-Lizenz](LICENSE)", text)

    def test_die_fremdlizenzen_grenzen_sich_ab(self) -> None:
        text = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("[LICENSE](LICENSE)", text)
        self.assertIn("(GPL-3.0-or-later)", text)
        self.assertNotIn("Das Programm selbst steht unter der MIT-Lizenz", text)

    def test_handbuch_und_faq_nennen_die_gpl(self) -> None:
        for name, alt in (("BENUTZERHANDBUCH.html", "steht unter der MIT-Lizenz"),
                          ("FAQ.html", "steht unter der <strong>MIT-Lizenz</strong>"),
                          ("FAQ_EN.html", "released under the <strong>MIT license</strong>")):
            with self.subTest(datei=name):
                text = (PROJEKT / name).read_text(encoding="utf-8")
                self.assertIn("GPL-3.0-or-later", text)
                self.assertNotIn(alt, text)

    def test_die_startmeldungen_nennen_nicht_mehr_mit(self) -> None:
        from ps5_validator.utils import i18n
        for schluessel in ("lizenz.registriert", "lizenz.ohne_registry", "lizenz.fehlgeschlagen"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = i18n.STRINGS[schluessel][sprache]
                    self.assertNotIn("MIT", text)
                    self.assertIn("GPL-3.0", text)


if __name__ == "__main__":
    unittest.main()
