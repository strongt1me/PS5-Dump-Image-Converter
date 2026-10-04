# -*- coding: utf-8 -*-
"""App direkt installieren: die Kachel wahlweise unter "Medien" oder "Spiele" (seit v1.9.62).

Wunsch des Nutzers vom 04.10.2026: "Dann trag in die Kachel 65536 ein, damit sie unter
Medien erscheint. Oder noch besser. Man soll waehlen koennen." Die Konsole liest
``applicationCategoryType`` aus der param.json, mit der sich die Anwendung anmeldet:
0 = Spiele, 65536 = Medien. Geprueft wird, was auf der Konsole ankommt - fuer beide
Bauformen - und dass ohne Wahl alles beim Alten bleibt (die bestehenden Tests in
test_app_install rufen ohne Kategorie).
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("app_install_bereich")

from ps5_validator.utils import app_install, i18n           # noqa: E402
from test_app_install import _FtpNachbau, _app_ordner, _gui  # noqa: E402

KLASSE = "PS5ConverterGUI"


class BereichTests(unittest.TestCase):

    def test_medien_ist_65536_spiele_ist_null(self) -> None:
        self.assertEqual(65536, app_install.bereich_kategorie(app_install.BEREICH_MEDIEN))
        self.assertEqual(0, app_install.bereich_kategorie(app_install.BEREICH_SPIELE))

    def test_unbekanntes_wird_medien(self) -> None:
        for wert in ("", None, "irgendwas", "MEDIEN "):
            with self.subTest(wert=wert):
                self.assertEqual(65536, app_install.bereich_kategorie(wert))

    def test_die_systemkategorie_ist_beim_anmelden_verboten(self) -> None:
        with self.assertRaises(ValueError):
            app_install.installfassung({"titleId": "FAKE02932"}, app_install.KATEGORIE_SYSTEM)
        with self.assertRaises(ValueError):
            app_install.deeplink_fassung({"titleId": "FAKE02932"}, app_install.KATEGORIE_SYSTEM)

    def test_installfassung_nimmt_die_wahl(self) -> None:
        vorlage = {"titleId": "FAKE02932", "applicationCategoryType": 0}
        gebaut = app_install.installfassung(vorlage, 65536)
        self.assertEqual(65536, gebaut["applicationCategoryType"])
        self.assertEqual(0, vorlage["applicationCategoryType"], "Vorlage veraendert")

    def test_texte_zweisprachig_und_mit_gleichen_platzhaltern(self) -> None:
        for schluessel in ("appinstall.bereich_label", "appinstall.bereich_medien",
                           "appinstall.bereich_spiele", "appinstall.bereich_hint",
                           "appinstall.log_bereich", "appinstall.confirm_message"):
            with self.subTest(schluessel=schluessel):
                eintrag = i18n.STRINGS[schluessel]
                self.assertTrue(eintrag["de"] and eintrag["en"])
        self.assertIn("{bereich}", i18n.STRINGS["appinstall.confirm_message"]["de"])
        self.assertIn("{bereich}", i18n.STRINGS["appinstall.confirm_message"]["en"])


class ProgrammUebertragungTests(unittest.TestCase):
    """Bauform "eigenes Programm": die Wahl steckt in der param.json unter /user/app."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.angaben = app_install.pruefen(_app_ordner(self.tmp))[0]
        self.ftp = _FtpNachbau()
        self.meldungen: list[str] = []

    def _uebertragen(self, kategorie) -> None:
        gui = _gui()
        echt = app_install.payload_senden
        app_install.payload_senden = lambda *a, **k: "appinst: 'FAKE02932' registriert"
        self.addCleanup(setattr, app_install, "payload_senden", echt)
        gui._appinstall_uebertragen(self.ftp, self.angaben, "10.0.0.5", b"ELF",
                                    self.meldungen.append, kategorie)

    def _kategorie(self, ziel: str) -> int:
        return json.loads(self.ftp.geschrieben[ziel].decode("utf-8"))["applicationCategoryType"]

    def test_medien_meldet_sich_mit_65536_an(self) -> None:
        self._uebertragen(65536)
        self.assertEqual(65536, self._kategorie("/user/app/FAKE02932/sce_sys/param.json"))
        self.assertTrue(any("appinstall.log_bereich" in m for m in self.meldungen), self.meldungen)

    def test_spiele_meldet_sich_mit_null_an(self) -> None:
        self._uebertragen(0)
        self.assertEqual(0, self._kategorie("/user/app/FAKE02932/sce_sys/param.json"))

    def test_die_systemfassung_bleibt_unberuehrt(self) -> None:
        """Der Start aus /system_ex braucht weiter die nachgereichte Systemkategorie."""
        self._uebertragen(65536)
        self.assertEqual(app_install.KATEGORIE_SYSTEM,
                         self._kategorie("/system_ex/app/FAKE02932/sce_sys/param.json"))
        self.assertEqual(self.ftp.reihenfolge[-1], "/system_ex/app/FAKE02932/sce_sys/param.json")


class DeeplinkUebertragungTests(unittest.TestCase):
    """Bauform "Adresse": auch hier gilt die Wahl."""

    def setUp(self) -> None:
        self.angaben = app_install.deeplink_pruefen(
            "PLDM00002", "Testkachel", "http://127.0.0.1:8084/")[0]
        self.ftp = _FtpNachbau()

    def _uebertragen(self, kategorie) -> int:
        gui = _gui()
        echt = app_install.payload_senden
        app_install.payload_senden = lambda *a, **k: "appinst: 'PLDM00002' registriert"
        self.addCleanup(setattr, app_install, "payload_senden", echt)
        gui._appinstall_uebertragen(self.ftp, self.angaben, "10.0.0.5", b"ELF",
                                    lambda _t: None, kategorie)
        roh = self.ftp.geschrieben["/user/app/PLDM00002/sce_sys/param.json"]
        return json.loads(roh.decode("utf-8"))["applicationCategoryType"]

    def test_spiele_wirkt_auch_bei_der_adresskachel(self) -> None:
        self.assertEqual(0, self._uebertragen(0))

    def test_ohne_wahl_bleibt_die_adresskachel_bei_medien(self) -> None:
        self.assertEqual(65536, self._uebertragen(None))


class FensterQuelltextTests(unittest.TestCase):
    """Das Fenster liest die Wahl im Hauptfaden und reicht sie durch."""

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"))
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef) and k.name == KLASSE)
        cls.fenster = next(k for k in klasse.body
                           if isinstance(k, ast.FunctionDef) and k.name == "_show_app_install")

    def test_die_wahl_wird_vor_dem_faden_gelesen_und_durchgereicht(self) -> None:
        installieren = next(k for k in ast.walk(self.fenster)
                            if isinstance(k, ast.FunctionDef) and k.name == "_installieren")
        lauf = next(k for k in ast.walk(installieren)
                    if isinstance(k, ast.FunctionDef) and k.name == "_lauf")
        # Im Faden keine Tk-Variable: bereich_var kommt dort nicht vor.
        self.assertNotIn("bereich_var", ast.unparse(lauf))
        self.assertIn("bereich_kategorie(bereich_var.get())", ast.unparse(installieren))
        self.assertIn("_melden, kategorie)", ast.unparse(lauf))

    def test_die_wahl_wird_gemerkt(self) -> None:
        text = ast.unparse(self.fenster)
        self.assertIn("'appinstall_bereich'", text)
        self.assertIn("_save_setting", text)


if __name__ == "__main__":
    unittest.main()
