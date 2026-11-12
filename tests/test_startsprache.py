# -*- coding: utf-8 -*-
"""Sprache beim Programmstart (Nutzerwunsch 12.11.2026).

Hat der Anwender die Sprache nie umgeschaltet, folgt das Programm der Systemsprache. Kennt es die Sprache des Systems nicht,
gilt Englisch. Eine gespeicherte Wahl gilt immer. ``DEFAULT_LANGUAGE`` (Deutsch) bleibt der Rueckfall fuer fehlende
Uebersetzungen.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("startsprache")

from ps5_validator.utils import i18n                        # noqa: E402

UMGEBUNG = i18n.SYSTEMSPRACHE_UMGEBUNG
HAUPT = PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py"

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                            # pragma: no cover
    TK_DA = False


class _Ohne(unittest.TestCase):
    """Raeumt die Umgebungsvariable der Pruefumgebung aus dem Weg und stellt sie nachher wieder her."""

    def setUp(self) -> None:
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop(UMGEBUNG, None)


class KuerzelTests(unittest.TestCase):
    def test_kennungen_werden_auf_zwei_buchstaben_gekuerzt(self):
        for roh, soll in (("de_DE.UTF-8", "de"), ("fr-CA", "fr"), ("EN", "en"), ("es_ES@euro", "es"), (" it ", "it"),
                          ("pt-BR", "pt"), ("zh_CN", "zh"), ("fil_PH", "fil")):
            self.assertEqual(soll, i18n._kuerzel(roh), roh)

    def test_c_posix_und_leeres_ergeben_nichts(self):
        for roh in ("C", "POSIX", "", None, "   ", "1"):
            self.assertEqual("", i18n._kuerzel(roh), repr(roh))


class SystemspracheTests(_Ohne):
    def test_die_umgebungsvariable_gibt_die_sprache_vor(self):
        for roh, soll in (("fr_FR.UTF-8", "fr"), ("DE", "de"), ("es", "es"), ("it-IT", "it"), ("en_GB", "en")):
            os.environ[UMGEBUNG] = roh
            self.assertEqual(soll, i18n.systemsprache(), roh)

    def test_unbekannte_sprachen_ergeben_nichts(self):
        for roh in ("ja_JP", "pt-BR", "ru", "xx", "zh-Hans-CN"):
            os.environ[UMGEBUNG] = roh
            self.assertEqual("", i18n.systemsprache(), roh)

    def test_windows_nimmt_die_anzeigesprache(self):
        for langid, soll in ((0x0407, "de"), (0x0409, "en"), (0x0C0A, "es"), (0x0410, "it"), (0x040C, "fr"),
                             (0x0816, ""), (0x0411, "")):                       # Portugiesisch, Japanisch: nicht im Programm
            fake = types.SimpleNamespace(kernel32=types.SimpleNamespace(GetUserDefaultUILanguage=lambda l=langid: l))
            with mock.patch.object(sys, "platform", "win32"), mock.patch("ctypes.windll", fake, create=True):
                self.assertEqual(soll, i18n.systemsprache(), hex(langid))

    def test_unter_linux_gilt_die_reihenfolge_der_umgebung(self):
        with mock.patch.object(sys, "platform", "linux"):
            os.environ.update({"LANG": "it_IT.UTF-8"})
            for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
                os.environ.pop(name, None)
            self.assertEqual("it", i18n.systemsprache())
            os.environ["LC_ALL"] = "fr_FR.UTF-8"            # LC_ALL schlaegt LANG
            self.assertEqual("fr", i18n.systemsprache())
            os.environ["LANGUAGE"] = "es:en"                # LANGUAGE schlaegt beide, erste Sprache der Liste
            self.assertEqual("es", i18n.systemsprache())

    def test_c_und_posix_unter_linux_fallen_auf_die_locale_zurueck(self):
        with mock.patch.object(sys, "platform", "linux"), mock.patch("locale.getlocale", lambda *a, **k: ("de_DE", "UTF-8")):
            for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
                os.environ.pop(name, None)
            os.environ["LANG"] = "C"
            self.assertEqual("de", i18n.systemsprache())

    def test_ohne_irgendeine_angabe_ist_es_leer_nicht_ein_fehler(self):
        with mock.patch.object(sys, "platform", "linux"), mock.patch("locale.getlocale", lambda *a, **k: (None, None)):
            for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"):
                os.environ.pop(name, None)
            self.assertEqual("", i18n.systemsprache())

    def test_ein_fehler_in_der_systemabfrage_wirft_nichts(self):
        fake = types.SimpleNamespace(kernel32=types.SimpleNamespace(
            GetUserDefaultUILanguage=mock.Mock(side_effect=OSError("nicht da"))))
        with mock.patch.object(sys, "platform", "win32"), mock.patch("ctypes.windll", fake, create=True), \
                mock.patch("locale.getlocale", lambda *a, **k: ("fr_FR", "UTF-8")):
            self.assertEqual("fr", i18n.systemsprache(), "Rueckfall auf die Locale")


class StartspracheTests(_Ohne):
    def test_eine_gespeicherte_wahl_gilt_immer(self):
        os.environ[UMGEBUNG] = "fr"
        for wahl in i18n.SUPPORTED_LANGUAGES:
            self.assertEqual(wahl, i18n.startsprache(wahl))

    def test_ohne_wahl_folgt_das_programm_dem_system(self):
        for roh, soll in (("de_DE", "de"), ("fr", "fr"), ("es-ES", "es"), ("it", "it"), ("en_US", "en")):
            os.environ[UMGEBUNG] = roh
            self.assertEqual(soll, i18n.startsprache(None), roh)

    def test_kennt_das_programm_die_systemsprache_nicht_gilt_englisch(self):
        for roh in ("ja_JP", "pt-BR", "ru", "zh_CN", "nl"):
            os.environ[UMGEBUNG] = roh
            self.assertEqual("en", i18n.startsprache(None), roh)

    def test_ohne_system_angabe_gilt_englisch(self):
        with mock.patch.object(i18n, "_system_kennung", return_value=""):
            self.assertEqual("en", i18n.startsprache(None))

    def test_unbrauchbare_gespeicherte_werte_zaehlen_nicht(self):
        os.environ[UMGEBUNG] = "fr"
        for kaputt in ("", "xx", "klingon", 5, None, ["de"]):
            self.assertEqual("fr", i18n.startsprache(kaputt), repr(kaputt))

    def test_die_standardsprache_ist_englisch_der_rueckfall_fuer_texte_bleibt_deutsch(self):
        self.assertEqual("en", i18n.STANDARD_SPRACHE)
        self.assertEqual("de", i18n.DEFAULT_LANGUAGE)
        self.assertIn(i18n.STANDARD_SPRACHE, i18n.SUPPORTED_LANGUAGES)

    def test_die_pruefumgebung_stellt_deutsch_ein(self):
        """Damit die Testreihe auf jedem Rechner dieselbe Sprache hat."""
        self.assertEqual("de", pruefumgebung_sprache())


def pruefumgebung_sprache() -> str:
    """Die Sprache, die ein Pruefstand nach ``pruefumgebung.umlenken`` sieht (ohne die Aufraeumerei der Testklasse)."""
    import importlib
    gemerkt = os.environ.pop(UMGEBUNG, None)
    try:
        pruefumgebung.umlenken("startsprache")
        return i18n.startsprache(None)
    finally:
        os.environ.pop(UMGEBUNG, None)
        if gemerkt is not None:
            os.environ[UMGEBUNG] = gemerkt


def _lade():
    import importlib.util
    if "hauptprogramm" in sys.modules:
        return sys.modules["hauptprogramm"]
    spec = importlib.util.spec_from_file_location("hauptprogramm", HAUPT)
    modul = importlib.util.module_from_spec(spec)
    sys.modules["hauptprogramm"] = modul
    spec.loader.exec_module(modul)
    return modul


class QuelltextTests(unittest.TestCase):
    def test_der_konstruktor_und_der_hinweis_ohne_fenster_nutzen_die_startsprache(self):
        text = HAUPT.read_text(encoding="utf-8")
        self.assertIn("i18n_startsprache(_saved_language)", text)
        self.assertIn('i18n_startsprache(PS5ConverterGUI._load_setting_static("language", None))', text)
        self.assertNotIn('_load_setting_static("language", DEFAULT_LANGUAGE)', text,
                         "ohne gespeicherte Wahl darf nicht mehr fest Deutsch gelten")


@unittest.skipUnless(TK_DA, "keine Anzeige")
class FensterTests(unittest.TestCase):
    """Das echte Hauptfenster: Startsprache aus der Einstellungsdatei und dem System."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.haupt = _lade()

    def _start(self, einstellungen: dict, system: str) -> str:
        ordner = tempfile.mkdtemp(prefix="startsprache_")
        self.addCleanup(shutil.rmtree, ordner, True)
        if einstellungen is not None:
            Path(ordner, "paths.json").write_text(json.dumps(einstellungen), encoding="utf-8")
        with mock.patch.dict(os.environ, {pruefumgebung.UMGEBUNGSNAME: ordner, UMGEBUNG: system}):
            app = self.haupt.PS5ConverterGUI(_WURZEL)
            sprache = app._current_language
            text = app._t("action.start")
            app._current_language = "de"        # wie jeder Pruefstand: danach steht die Sprache fest (Waechter im Volllauf)
        return "%s|%s" % (sprache, text)

    def test_ohne_gespeicherte_wahl_folgt_das_fenster_dem_system(self):
        self.assertEqual("fr|%s" % i18n.translate("fr", "action.start"), self._start({}, "fr_FR.UTF-8"))

    def test_unbekannte_systemsprache_ergibt_ein_englisches_fenster(self):
        self.assertEqual("en|START", self._start({}, "ja_JP"))

    def test_eine_gespeicherte_wahl_schlaegt_die_systemsprache(self):
        self.assertEqual("es|%s" % i18n.translate("es", "action.start"), self._start({"language": "es"}, "fr"))

    def test_eine_kaputte_gespeicherte_sprache_wird_ersetzt(self):
        self.assertEqual("de|STARTEN", self._start({"language": "klingon"}, "de"))


if __name__ == "__main__":
    unittest.main()
