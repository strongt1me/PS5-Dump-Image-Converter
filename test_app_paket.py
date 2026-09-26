# -*- coding: utf-8 -*-
""""App installieren …" in der Bibliothek: eine Homebrew-App aus ihrem ZIP auf die PS5.

Wunsch des Nutzers vom 26.09.2026: ProsperoEden (Switch-Emulator, App-Ordner
``PPSA99008``) auf die PS5 bringen. Mitgeliefert wird nichts - der Anwender
waehlt das Release-ZIP, die Dateien gehen direkt aus dem Archiv per FTP nach
``/data/homebrew/<ID>``.

Uebertragen wird gegen einen **echten** kleinen FTP-Server (``_FtpStube`` aus
``test_konsole_stufe3``): Was angelegt, geschrieben und nicht geloescht wird,
steht zwischen den Zeilen des Protokolls.
"""
from __future__ import annotations

import ftplib
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("app_paket")

from ps5_validator.utils import app_paket                   # noqa: E402
from ps5_validator.utils import konsole_ftp                 # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402
from test_konsole_stufe3 import _FtpStube                   # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False


def _param(kennung: str = "PPSA99008", titel: str = "ProsperoEden",
           fassung: str = "01.000.010") -> str:
    return json.dumps({"titleId": kennung, "contentVersion": fassung,
                       "localizedParameters": {"defaultLanguage": "en-US",
                                               "en-US": {"titleName": titel}}})


def _app(praefix: str = "PPSA99008/") -> dict:
    """Ein Release-ZIP wie das von ProsperoEden - nur kleiner."""
    return {praefix + "eboot.bin": b"\x4f\x15\x3d\x1d" + b"e" * 5000,
            praefix + "sce_sys/param.json": _param(),
            praefix + "sce_sys/icon0.png": b"\x89PNG" + b"i" * 300,
            praefix + "ui/main.rml": b"<rml>neu</rml>",
            praefix + "README.md": b"# ProsperoEden"}


def _zip(ordner, eintraege: dict, name: str = "app.zip") -> str:
    pfad = os.path.join(str(ordner), name)
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as archiv:
        for eintrag, inhalt in eintraege.items():
            archiv.writestr(eintrag, inhalt)
    return pfad


class PaketLesenTests(unittest.TestCase):
    """Was als App-Paket gilt - und was nicht."""

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="app_paket_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.ordner, ignore_errors=True))

    def _fehler(self, eintraege: dict) -> app_paket.PaketFehler:
        with self.assertRaises(app_paket.PaketFehler) as kontext:
            app_paket.paket_lesen(_zip(self.ordner, eintraege))
        return kontext.exception

    def test_ein_release_zip_wird_erkannt(self) -> None:
        paket = app_paket.paket_lesen(_zip(self.ordner, _app()))
        self.assertEqual("PPSA99008", paket.kennung)
        self.assertEqual("ProsperoEden", paket.titel)
        self.assertEqual("01.000.010", paket.fassung)
        self.assertEqual("/data/homebrew/PPSA99008", paket.ziel)
        self.assertEqual(["README.md", "eboot.bin", "sce_sys/icon0.png",
                          "sce_sys/param.json", "ui/main.rml"],
                         [d.relativ for d in paket.dateien])
        self.assertEqual(sum(len(v) for v in _app().values()), paket.bytes_gesamt)
        self.assertEqual(("assets/keys", "assets/firmware", "assets/roms"),
                         paket.zusatzordner)

    def test_der_app_ordner_darf_eine_ebene_tiefer_liegen(self) -> None:
        paket = app_paket.paket_lesen(_zip(self.ordner, _app("ProsperoEden-v1/PPSA99008/")))
        self.assertEqual("PPSA99008", paket.kennung)
        self.assertIn("eboot.bin", [d.relativ for d in paket.dateien])

    def test_andere_apps_ohne_zusatzordner(self) -> None:
        eintraege = {k.replace("PPSA99008", "PPSA99010"): v for k, v in _app().items()}
        eintraege["PPSA99010/sce_sys/param.json"] = _param("PPSA99010", "Andere")
        self.assertEqual((), app_paket.paket_lesen(_zip(self.ordner, eintraege)).zusatzordner)

    def test_kein_app_ordner(self) -> None:
        self.assertEqual("apppaket.grund_kein_ordner",
                         self._fehler({"README.md": b"nur Text"}).schluessel)

    def test_ohne_param_json_ist_es_keine_app(self) -> None:
        eintraege = _app()
        del eintraege["PPSA99008/sce_sys/param.json"]
        self.assertEqual("apppaket.grund_kein_ordner", self._fehler(eintraege).schluessel)

    def test_zwei_app_ordner(self) -> None:
        eintraege = _app()
        eintraege.update({k.replace("PPSA99008", "PPSA99010"): v for k, v in _app().items()})
        fehler = self._fehler(eintraege)
        self.assertEqual("apppaket.grund_mehrere", fehler.schluessel)
        self.assertEqual("PPSA99008, PPSA99010", fehler.werte["ordner"])

    def test_unzulaessige_pfade_verwerfen_das_ganze_paket(self) -> None:
        for boese in ("../boese.txt", "/absolut.txt", "C:/laufwerk.txt",
                      "PPSA99008/../../weg.txt", "PPSA99008/./punkt.txt"):
            with self.subTest(pfad=boese):
                eintraege = _app()
                eintraege[boese] = b"x"
                fehler = self._fehler(eintraege)
                self.assertEqual("apppaket.grund_unsicherer_pfad", fehler.schluessel)
                self.assertEqual(boese, fehler.werte["pfad"])

    def test_symbolische_verknuepfung_verwirft_das_paket(self) -> None:
        pfad = _zip(self.ordner, _app())
        with zipfile.ZipFile(pfad, "a") as archiv:
            verweis = zipfile.ZipInfo("PPSA99008/verweis")
            verweis.external_attr = 0o120777 << 16
            archiv.writestr(verweis, "/etc/passwd")
        with self.assertRaises(app_paket.PaketFehler) as kontext:
            app_paket.paket_lesen(pfad)
        self.assertEqual("apppaket.grund_unsicherer_pfad", kontext.exception.schluessel)

    def test_kaputte_param_json(self) -> None:
        eintraege = _app()
        eintraege["PPSA99008/sce_sys/param.json"] = b"{kein json"
        self.assertEqual("apppaket.grund_param", self._fehler(eintraege).schluessel)

    def test_andere_kennung_in_der_param_json(self) -> None:
        eintraege = _app()
        eintraege["PPSA99008/sce_sys/param.json"] = _param("PPSA00001")
        fehler = self._fehler(eintraege)
        self.assertEqual("apppaket.grund_kennung", fehler.schluessel)
        self.assertEqual({"ordner": "PPSA99008", "kennung": "PPSA00001"}, fehler.werte)

    def test_kein_zip(self) -> None:
        pfad = os.path.join(self.ordner, "text.zip")
        Path(pfad).write_text("kein Archiv", encoding="utf-8")
        with self.assertRaises(app_paket.PaketFehler) as kontext:
            app_paket.paket_lesen(pfad)
        self.assertEqual("apppaket.grund_kein_zip", kontext.exception.schluessel)

    def test_auf_dem_rechner_wird_nichts_entpackt(self) -> None:
        """Lesen und Senden gehen am Archiv entlang - nie ueber extract."""
        pfad = _zip(self.ordner, _app())
        verboten = AssertionError("entpackt")
        with mock.patch.object(zipfile.ZipFile, "extract", side_effect=verboten), \
                mock.patch.object(zipfile.ZipFile, "extractall", side_effect=verboten):
            paket = app_paket.paket_lesen(pfad)
            with tempfile.TemporaryDirectory() as wurzel, _FtpStube(Path(wurzel)) as stube:
                app_paket.senden("127.0.0.1", paket, stube.port)
        self.assertEqual([os.path.basename(pfad)], os.listdir(self.ordner))


class SendenTests(unittest.TestCase):
    """Die Uebertragung gegen eine echte FTP-Gegenstelle."""

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="app_senden_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.ordner, ignore_errors=True))
        self.konsole = Path(self.ordner) / "konsole"
        self.konsole.mkdir()
        self.paket = app_paket.paket_lesen(_zip(self.ordner, _app()))
        self.app_ordner = self.konsole / "data" / "homebrew" / "PPSA99008"

    def test_die_app_landet_im_ziel(self) -> None:
        with _FtpStube(self.konsole) as stube:
            stand = app_paket.senden("127.0.0.1", self.paket, stube.port)
        self.assertFalse(stand.abgebrochen)
        self.assertEqual((5, 5), (stand.dateien, stand.dateien_gesamt))
        self.assertEqual(self.paket.bytes_gesamt, stand.bytes)
        for name, inhalt in _app().items():
            with self.subTest(datei=name):
                erwartet = inhalt.encode() if isinstance(inhalt, str) else inhalt
                self.assertEqual(erwartet, (self.konsole / "data/homebrew" / name).read_bytes())
        # Ausdruecklich genannt, nicht aus dem Paket gelesen: Waere die Liste
        # dort leer, liefe die Schleife nullmal und pruefte nichts (Gegenprobe
        # vom 26.09.2026 blieb so gruen).
        for ordner in ("assets/keys", "assets/firmware", "assets/roms"):
            with self.subTest(ordner=ordner):
                self.assertTrue((self.app_ordner / ordner).is_dir())
                self.assertEqual([], os.listdir(self.app_ordner / ordner),
                                 "Das Programm legt nur leere Ordner an.")

    def test_eigene_dateien_bleiben_app_dateien_werden_ersetzt(self) -> None:
        (self.app_ordner / "assets" / "keys").mkdir(parents=True)
        (self.app_ordner / "assets" / "keys" / "prod.keys").write_bytes(b"eigene")
        (self.app_ordner / "ui").mkdir(parents=True)
        (self.app_ordner / "ui" / "main.rml").write_bytes(b"<rml>alt</rml>")
        with _FtpStube(self.konsole) as stube:
            app_paket.senden("127.0.0.1", self.paket, stube.port)
        self.assertEqual(b"eigene", (self.app_ordner / "assets/keys/prod.keys").read_bytes())
        self.assertEqual(b"<rml>neu</rml>", (self.app_ordner / "ui/main.rml").read_bytes())

    def test_nichts_wird_geloescht_oder_umbenannt(self) -> None:
        befehle: list = []
        original = ftplib.FTP.putcmd

        def _mitschreiben(verbindung, zeile):
            befehle.append(zeile.split(" ", 1)[0].upper())
            return original(verbindung, zeile)

        with _FtpStube(self.konsole) as stube, \
                mock.patch.object(ftplib.FTP, "putcmd", _mitschreiben):
            app_paket.senden("127.0.0.1", self.paket, stube.port)
        self.assertEqual(5, befehle.count("STOR"))
        self.assertFalse({"DELE", "RMD", "RNFR", "RNTO"} & set(befehle), befehle)

    def test_abbruch_erst_zwischen_zwei_dateien(self) -> None:
        """Der Abbruch greift vor der naechsten Datei; Zusatzordner kommen dann nicht mehr."""
        gefragt: list = []

        def _abbruch() -> bool:
            gefragt.append(True)
            return len(gefragt) > 1          # nach der ersten Datei

        with _FtpStube(self.konsole) as stube:
            stand = app_paket.senden("127.0.0.1", self.paket, stube.port, abbruch=_abbruch)
        self.assertTrue(stand.abgebrochen)
        self.assertEqual(1, stand.dateien)
        erste = self.paket.dateien[0]
        self.assertEqual(erste.groesse, (self.app_ordner / erste.relativ).stat().st_size,
                         "Die laufende Datei kommt vollstaendig an.")
        self.assertFalse((self.app_ordner / "assets").exists())

    def test_ohne_konsole_ein_ftpfehler(self) -> None:
        stube = _FtpStube(self.konsole)
        port = stube.port
        stube.schliessen()
        with self.assertRaises(konsole_ftp.FtpFehler):
            app_paket.senden("127.0.0.1", self.paket, port)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class BibliothekTests(unittest.TestCase):
    """Der Knopf in der PS5-Reihe der Bibliothek und das Uebertragungsfenster."""

    @classmethod
    def setUpClass(cls) -> None:
        import PS5ImageConverter_Pro_FINAL_revised as APP
        cls.APP = APP
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls.app._konfiguration_schreiben({"ansicht": "umwandeln"})
        _WURZEL.update_idletasks()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app._konfiguration_schreiben({"ansicht": "umwandeln"})

    def setUp(self) -> None:
        self.ordner = tempfile.mkdtemp(prefix="app_seite_")
        self.addCleanup(lambda: __import__("shutil").rmtree(self.ordner, ignore_errors=True))
        self.app._ansicht_setzen("konsole", speichern=False)
        self.app._konsole_seite_setzen("bibliothek")
        _WURZEL.update()
        self.zustand = self.app._bibliothek
        self.knopf = next(k for k in self.zustand["knoepfe"]["ps5"]
                          if str(k.cget("text")) == self.app._t("library.btn_app_installieren"))

    def tearDown(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()

    def test_der_knopf_nimmt_ein_zip_und_uebertraegt(self) -> None:
        pfad = _zip(self.ordner, _app())
        with mock.patch.object(self.APP.filedialog, "askopenfilename", return_value=pfad), \
                mock.patch.object(self.app, "_bibliothek_ordner_uebertragen") as uebertragen:
            self.knopf.invoke()
        uebertragen.assert_called_once()
        benannt = uebertragen.call_args.kwargs
        self.assertEqual(("hoch", pfad, "/data/homebrew/PPSA99008"),
                         (benannt["richtung"], benannt["oertlich"], benannt["entfernt"]))
        self.assertEqual("PPSA99008", benannt["paket"].kennung)
        self.assertTrue(callable(benannt["nachher"]))

    def test_ein_ungueltiges_zip_wird_erklaert(self) -> None:
        pfad = _zip(self.ordner, {"README.md": b"nur Text"}, name="quelltext.zip")
        with mock.patch.object(self.APP.filedialog, "askopenfilename", return_value=pfad), \
                mock.patch.object(self.APP.messagebox, "showwarning") as warnung, \
                mock.patch.object(self.app, "_bibliothek_ordner_uebertragen") as uebertragen:
            self.knopf.invoke()
        uebertragen.assert_not_called()
        warnung.assert_called_once()
        self.assertEqual(self.app._t("library.app_kein_paket", datei="quelltext.zip",
                                     grund=self.app._t("apppaket.grund_kein_ordner")),
                         warnung.call_args[0][1])

    def test_ohne_auswahl_geschieht_nichts(self) -> None:
        with mock.patch.object(self.APP.filedialog, "askopenfilename", return_value=""), \
                mock.patch.object(self.APP.messagebox, "showwarning") as warnung, \
                mock.patch.object(self.app, "_bibliothek_ordner_uebertragen") as uebertragen:
            self.knopf.invoke()
        uebertragen.assert_not_called()
        warnung.assert_not_called()

    def test_das_fenster_installiert_und_sucht_danach_neu(self) -> None:
        """Ganzer Weg: Frage, Uebertragung gegen die FTP-Stube, Meldung, Nachgang."""
        konsole = Path(self.ordner) / "konsole"
        konsole.mkdir()
        paket = app_paket.paket_lesen(_zip(self.ordner, _app()))
        gefragt: list = []
        nachher = mock.Mock()
        with _FtpStube(konsole) as stube, \
                mock.patch.object(self.app, "_bibliothek_ps5_adresse", return_value="127.0.0.1"), \
                mock.patch.object(self.app, "_ps5_ftp_port", return_value=stube.port), \
                mock.patch.object(self.app, "_konsole_ftp_bereit", lambda *_a: True), \
                mock.patch.object(self.app, "_im_hauptfaden",
                                  lambda _f, _titel, text, **_k: gefragt.append(text) or True), \
                mock.patch.object(self.APP.messagebox, "showinfo") as info, \
                mock.patch.object(self.APP.messagebox, "showwarning") as warnung:
            vorher = set(_WURZEL.winfo_children())
            self.app._bibliothek_ordner_uebertragen(
                _WURZEL, richtung="hoch", oertlich=paket.zip_pfad, entfernt=paket.ziel,
                paket=paket, nachher=nachher)
            fenster = [w for w in _WURZEL.winfo_children() if w not in vorher][-1]
            ende = time.monotonic() + 15
            while time.monotonic() < ende and not info.called and not warnung.called:
                _WURZEL.update()
                time.sleep(0.05)
        warnung.assert_not_called()
        self.assertEqual(1, len(gefragt))
        self.assertIn("ProsperoEden 01.000.010 (PPSA99008)", gefragt[0])
        text = info.call_args[0][1]
        self.assertIn(self.app._t("library.app_installiert", titel="ProsperoEden", dateien=5,
                                  menge=konsole_ftp.menge_lesbar(paket.bytes_gesamt),
                                  ziel="/data/homebrew/PPSA99008"), text)
        self.assertIn("assets/keys, assets/firmware, assets/roms", text)
        nachher.assert_called_once_with()
        self.assertTrue((konsole / "data/homebrew/PPSA99008/eboot.bin").is_file())
        try:
            self.assertFalse(fenster.winfo_exists())
        except tk.TclError:
            pass

    def test_schon_da_heisst_aktualisieren(self) -> None:
        konsole = Path(self.ordner) / "konsole"
        (konsole / "data/homebrew/PPSA99008/assets/keys").mkdir(parents=True)
        paket = app_paket.paket_lesen(_zip(self.ordner, _app()))
        gefragt: list = []
        with _FtpStube(konsole) as stube, \
                mock.patch.object(self.app, "_bibliothek_ps5_adresse", return_value="127.0.0.1"), \
                mock.patch.object(self.app, "_ps5_ftp_port", return_value=stube.port), \
                mock.patch.object(self.app, "_konsole_ftp_bereit", lambda *_a: True), \
                mock.patch.object(self.app, "_im_hauptfaden",
                                  lambda _f, _titel, text, **_k: gefragt.append(text) or False), \
                mock.patch.object(self.APP.messagebox, "showinfo") as info:
            vorher = set(_WURZEL.winfo_children())
            self.app._bibliothek_ordner_uebertragen(
                _WURZEL, richtung="hoch", oertlich=paket.zip_pfad, entfernt=paket.ziel,
                paket=paket)
            fenster = [w for w in _WURZEL.winfo_children() if w not in vorher][-1]
            ende = time.monotonic() + 15
            while time.monotonic() < ende and fenster.winfo_exists():
                _WURZEL.update()
                time.sleep(0.05)
        self.assertEqual(1, len(gefragt))
        self.assertTrue(gefragt[0].startswith(
            self.app._t("library.app_frage_aktualisieren", ziel="/data/homebrew/PPSA99008",
                        titel="ProsperoEden", fassung="01.000.010", kennung="PPSA99008",
                        dateien=5, menge=konsole_ftp.menge_lesbar(paket.bytes_gesamt),
                        minuten=1)[:60]))
        info.assert_not_called()
        self.assertFalse((konsole / "data/homebrew/PPSA99008/eboot.bin").exists(),
                         "Nein heisst: nichts uebertragen.")


class TexteTests(unittest.TestCase):

    def test_die_texte_gibt_es_in_beiden_sprachen(self) -> None:
        for schluessel in ("library.btn_app_installieren", "library.app_titel",
                           "library.app_zip_waehlen", "library.app_kein_paket",
                           "library.app_frage", "library.app_frage_aktualisieren",
                           "library.app_installiert", "library.app_zusatzordner",
                           "library.app_abgebrochen", "library.app_log_start",
                           "library.app_log_done", "apppaket.grund_kein_zip",
                           "apppaket.grund_unsicherer_pfad", "apppaket.grund_kein_ordner",
                           "apppaket.grund_mehrere", "apppaket.grund_param",
                           "apppaket.grund_kennung"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache))

    def test_jeder_grund_des_moduls_hat_einen_text(self) -> None:
        """Das Modul meldet Schluessel - fehlt einer, stuende er roh in der Meldung."""
        quelle = (PROJEKT / "ps5_validator" / "utils" / "app_paket.py").read_text(encoding="utf-8")
        import re
        gruende = set(re.findall(r'"(apppaket\.grund_[a-z_]+)"', quelle))
        self.assertGreaterEqual(len(gruende), 6)
        self.assertEqual(set(), gruende - set(STRINGS))

    def test_das_handbuch_beschreibt_es(self) -> None:
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        anfang = handbuch.index("<h4>Bibliothek</h4>")
        abschnitt = " ".join(handbuch[anfang:handbuch.index("<h4>", anfang + 4)].split())
        for stelle in ("App installieren …", "Release-ZIP", "/data/homebrew/&lt;ID&gt;",
                       "gelöscht wird nichts", "assets/keys", "entpackt wird auf dem Rechner nichts"):
            with self.subTest(stelle=stelle):
                self.assertIn(stelle, abschnitt)


if __name__ == "__main__":
    unittest.main()
