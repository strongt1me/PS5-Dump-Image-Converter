# -*- coding: utf-8 -*-
"""Die Lizenz des Programms selbst (MIT) - Datei, Programm und Bau im Gleichklang.

Gemessen am 19.09.2026: Das Repo wurde am 25.06.2026 mit einer ``LICENSE``
angelegt (MIT, strongt1me). Am 06.07.2026 fiel sie beim Aufraeumen von
"Diverses" mit aus dem Repo - danach bezeichnete sich das Programm als
MIT-lizenziert, ohne dass das oeffentliche Repo den Text trug. Der Text, den
das Programm unter Windows in die Registry schreibt, nannte einen anderen
Inhaber und ein Jahr, das mit der Uhr mitlief; unter Linux und macOS meldete
es "MIT-Lizenz liegt bei", obwohl kein Bau sie enthielt.
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
SPECS = ("PS5ImageConverter_Pro.spec", "PS5ImageConverter_Pro_linux.spec",
         "PS5ImageConverter_Pro_macos.spec")


def _datei_text() -> str:
    """Der Text der Datei - Zeilenenden zaehlen nicht, der Wortlaut schon."""
    return DATEI.read_bytes().decode("utf-8").replace("\r\n", "\n")


class DateiTests(unittest.TestCase):
    """Die Datei im Projektordner."""

    def test_die_datei_liegt_im_projektordner(self) -> None:
        self.assertTrue(DATEI.is_file(), "LICENSE fehlt im Projektordner")

    def test_das_programm_traegt_denselben_text(self) -> None:
        self.assertEqual(_datei_text(), eigene_lizenz.TEXT)

    def test_es_ist_die_mit_lizenz(self) -> None:
        text = eigene_lizenz.TEXT
        self.assertTrue(text.startswith("MIT License\n\n"))
        self.assertIn(f"\n{eigene_lizenz.COPYRIGHT}\n", text)
        self.assertIn("Permission is hereby granted, free of charge", text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', text)
        self.assertEqual("MIT", eigene_lizenz.SPDX)

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
            ok, _meldung = APP._register_mit_license_runtime()
        return ok, geschrieben

    def test_eingetragen_wird_der_text_der_datei(self) -> None:
        ok, werte = self._ausfuehren()
        self.assertTrue(ok)
        self.assertEqual(_datei_text(), werte["LicenseText"])
        self.assertEqual("MIT", werte["SPDX"])
        self.assertEqual(hashlib.sha256(_datei_text().encode("utf-8")).hexdigest(),
                         werte["LicenseHashSHA256"])

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
        self.assertIn("MIT", treffer.group(1))

    def test_das_auslieferungsbuendel_nimmt_die_lizenzen_mit(self) -> None:
        text = (PROJEKT / "Build_EXE.ps1").read_text(encoding="utf-8-sig")
        self.assertIn('"LICENSE"', text)
        self.assertIn('"THIRD_PARTY_LICENSES.md"', text)


class DokuTests(unittest.TestCase):
    """Wer das Repo oder die Fremdlizenzen liest, findet die eigene Lizenz."""

    def test_die_readme_verlinkt_die_datei(self) -> None:
        text = (PROJEKT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[MIT-Lizenz](LICENSE)", text)

    def test_die_fremdlizenzen_grenzen_sich_ab(self) -> None:
        text = (PROJEKT / "THIRD_PARTY_LICENSES.md").read_text(encoding="utf-8")
        self.assertIn("[LICENSE](LICENSE)", text)


if __name__ == "__main__":
    unittest.main()
