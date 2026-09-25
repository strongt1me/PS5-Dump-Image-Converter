# -*- coding: utf-8 -*-
"""Waechter: Jede param.json, die das Programm anlegt oder repariert, traegt
eine Content-ID - und der Online-Nachschlag folgt dem Haken in den
Einstellungen.

Anlass (23.09.2026): Ein Anwender wollte aus Abbildern dieses Programms PKGs
bauen, und jedes Werkzeug brach ab mit "param.json has no Content ID". Die
Ersatzdatei entstand ohne ``contentId``, sobald der Online-Nachschlag nichts
lieferte oder nicht lief; die Reparatur ergaenzte sie nie, und eine sonst
fehlerfreie Datei ohne sie lief ungefragt ins Abbild.

Die echte Kennung steht in keiner Datei eines Backups (gemessen 16.08.2026,
auch nicht in der eboot.bin). Fehlt sie online, kommt ein Platzhalter im
gueltigen Format hinein, und das Protokoll sagt, dass es einer ist.

Kein Test geht ins Netz: Der Nachschlag ist ueberall attrappiert.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("content_id")

from ps5_validator.utils import param_check as pc           # noqa: E402
from ps5_validator.utils.param_manifest import save_param_json  # noqa: E402


def _gui(*, antwort: bool = True, online: dict | None = None, online_erlaubt: bool = True):
    """Ein Programmobjekt ohne Fenster - Rueckfrage und Netz attrappiert."""
    from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

    gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
    gui._current_language = "de"
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui.fragen = []

    def _frage(titel, nachricht, *, online=False, default_yes=True):
        gui.fragen.append((titel, nachricht, default_yes))
        return antwort

    gui._param_frage = _frage
    gui._online_nachschlag_erlaubt = lambda: online_erlaubt
    gui._lookup_param_meta_online = lambda tid: dict(online or {})
    return gui


class ErsatzkennungTests(unittest.TestCase):
    """param_check: Platzhalter bilden, einsetzen, erkennen."""

    def test_platzhalter_hat_das_gueltige_format(self) -> None:
        kennung = pc.content_id_ersatz("PPSA12345", "Arcade Game Zone")
        self.assertEqual(kennung, "UP0000-PPSA12345_00-ARCADEGAMEZONE00")
        self.assertEqual(len(kennung), 36)
        self.assertRegex(kennung, pc.RE_CONTENT_ID)

    def test_kennung_aus_dem_titel_ohne_sonderzeichen(self) -> None:
        self.assertEqual(pc.content_id_ersatz("PPSA12345", "Ölwechsel: Die Rückkehr!")[20:],
                         "LWECHSELDIERCKKE")
        self.assertEqual(pc.content_id_ersatz("PPSA12345")[20:], "0" * 16)

    def test_ohne_gueltige_title_id_kein_platzhalter(self) -> None:
        for falsch in ("", "PPSA1234", "12345PPSA", None):
            with self.subTest(title_id=falsch):
                self.assertEqual(pc.content_id_ersatz(falsch, "Titel"), "")
        self.assertTrue(pc.content_id_ersatz("ppsa12345").startswith("UP0000-PPSA12345_00-"))

    def test_fehlt_erkennt_leer_und_fehlend(self) -> None:
        self.assertTrue(pc.content_id_fehlt({"titleId": "PPSA12345"}))
        self.assertTrue(pc.content_id_fehlt({"contentId": "  "}))
        self.assertFalse(pc.content_id_fehlt({"contentId": "UP0000-PPSA12345_00-0000000000000000"}))
        self.assertFalse(pc.content_id_fehlt("kein Dokument"))

    def test_einsetzen_an_der_alphabetischen_stelle(self) -> None:
        doc = {"applicationCategoryType": 0, "contentBadgeType": 2,
               "contentVersion": "01.000.000", "titleId": "PPSA12345"}
        neu = pc.content_id_einsetzen(doc, "UP0000-PPSA12345_00-0000000000000000")
        self.assertEqual(list(neu), ["applicationCategoryType", "contentBadgeType",
                                     "contentId", "contentVersion", "titleId"])
        self.assertEqual(doc.get("contentId"), None, "Die Vorlage darf unveraendert bleiben")

    def test_reparatur_fuellt_auch_eine_leere_kennung(self) -> None:
        doc = {"titleId": "PPSA12345", "contentId": "", "applicationCategoryType": 0,
               "localizedParameters": {"defaultLanguage": "en-US",
                                       "en-US": {"titleName": "X"}}}
        neu, aenderungen = pc.repariere(doc, content_id="UP0000-PPSA12345_00-X000000000000000")
        self.assertEqual(neu["contentId"], "UP0000-PPSA12345_00-X000000000000000")
        self.assertTrue(any("contentId" in a for a in aenderungen))

    def test_platzhalter_besteht_die_pruefung(self) -> None:
        doc = pc.neu_anlegen(title_id="PPSA12345",
                             content_id=pc.content_id_ersatz("PPSA12345", "Spiel"))
        befund = pc.pruefe_daten(doc)
        self.assertTrue(befund.ok, befund.als_text())
        self.assertFalse([w for w in befund.warnungen if "contentId" in w], befund.warnungen)


class AnlegenTests(unittest.TestCase):
    """_offer_create_param_json: echte Kennung, sonst Platzhalter."""

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.ordner = os.path.join(self.td.name, "PPSA19015-app0")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        self.pfad = os.path.join(self.ordner, "sce_sys", "param.json")

    def tearDown(self) -> None:
        self.td.cleanup()

    def _gelesen(self) -> dict:
        with open(self.pfad, encoding="utf-8") as fh:
            return json.load(fh)

    def test_online_gefundene_kennung_kommt_hinein(self) -> None:
        gui = _gui(online={"title": "Arcade Game Zone",
                           "content_id": "UP8016-PPSA19015_00-0489895718491618"})
        self.assertTrue(gui._offer_create_param_json(self.ordner, missing=True))
        doc = self._gelesen()
        self.assertEqual(doc["contentId"], "UP8016-PPSA19015_00-0489895718491618")
        self.assertEqual(doc["localizedParameters"]["en-US"]["titleName"], "Arcade Game Zone")

    def test_ohne_nachschlag_kommt_ein_platzhalter(self) -> None:
        for erlaubt, online in ((True, {}), (False, None)):
            with self.subTest(online_erlaubt=erlaubt):
                if os.path.exists(self.pfad):
                    os.remove(self.pfad)
                gui = _gui(online=online, online_erlaubt=erlaubt)
                self.assertTrue(gui._offer_create_param_json(self.ordner, missing=True))
                doc = self._gelesen()
                self.assertEqual(doc["contentId"], "UP0000-PPSA19015_00-0000000000000000")
                self.assertTrue(pc.pruefe_daten(doc).ok)
                self.assertTrue(any("Platzhalter" in z for z in gui.protokoll), gui.protokoll)

    def test_frage_ist_mit_ja_vorbelegt_und_nennt_den_dienst(self) -> None:
        gui = _gui(online={})
        gui._offer_create_param_json(self.ordner, missing=True)
        _titel, nachricht, vorbelegt = gui.fragen[0]
        self.assertTrue(vorbelegt)
        self.assertIn("prosperopatches.com", nachricht)

    def test_ps4_kennung_nennt_orbispatches(self) -> None:
        ordner = os.path.join(self.td.name, "CUSA12345-app")
        os.makedirs(os.path.join(ordner, "sce_sys"))
        gui = _gui(online={})
        gui._offer_create_param_json(ordner, missing=True)
        nachricht = gui.fragen[0][1]
        self.assertIn("orbispatches.com", nachricht)
        self.assertNotIn("prosperopatches.com", nachricht)

    def test_unlesbare_datei_wird_vorher_gesichert(self) -> None:
        with open(self.pfad, "w", encoding="utf-8") as fh:
            fh.write('{"titleId": "PPSA19015", "contentId": ')   # abgeschnitten
        gui = _gui(online={})
        self.assertTrue(gui._offer_create_param_json(self.ordner, missing=False))
        with open(self.pfad + ".alt", encoding="utf-8") as fh:
            self.assertIn('"contentId": ', fh.read())
        self.assertIn("contentId", self._gelesen())


class ErgaenzenTests(unittest.TestCase):
    """_content_id_ergaenzen_anbieten und der Weg durch _ensure_param_json."""

    DOC = {"applicationCategoryType": 0, "contentVersion": "01.000.000",
           "localizedParameters": {"defaultLanguage": "en-US",
                                   "en-US": {"titleName": "Test Spiel"}},
           "titleId": "PPSA24680"}

    def setUp(self) -> None:
        self.td = tempfile.TemporaryDirectory()
        self.ordner = os.path.join(self.td.name, "dump")
        os.makedirs(os.path.join(self.ordner, "sce_sys"))
        self.pfad = os.path.join(self.ordner, "sce_sys", "param.json")
        save_param_json(dict(self.DOC), self.pfad)

    def tearDown(self) -> None:
        self.td.cleanup()

    def _gelesen(self) -> dict:
        with open(self.pfad, encoding="utf-8") as fh:
            return json.load(fh)

    def test_ja_traegt_den_platzhalter_ein_und_sichert(self) -> None:
        gui = _gui(antwort=True)
        gui._content_id_ergaenzen_anbieten(self.ordner)
        doc = self._gelesen()
        self.assertEqual(doc["contentId"], "UP0000-PPSA24680_00-TESTSPIEL0000000")
        self.assertEqual(list(doc).index("contentId") + 1, list(doc).index("contentVersion"))
        self.assertTrue(os.path.isfile(self.pfad + ".alt"))
        self.assertIn("UP0000-PPSA24680_00-TESTSPIEL0000000", gui.fragen[0][1])

    def test_nein_laesst_die_datei_unberuehrt(self) -> None:
        vorher = Path(self.pfad).read_bytes()
        gui = _gui(antwort=False)
        gui._content_id_ergaenzen_anbieten(self.ordner)
        self.assertEqual(Path(self.pfad).read_bytes(), vorher)
        self.assertFalse(os.path.exists(self.pfad + ".alt"))
        self.assertTrue(any("nicht eingetragen" in z for z in gui.protokoll), gui.protokoll)

    def test_vorhandene_kennung_bleibt_ohne_frage(self) -> None:
        doc = dict(self.DOC, contentId="EP0001-PPSA24680_00-ECHTEKENNUNG0000")
        save_param_json(doc, self.pfad)
        gui = _gui(antwort=True)
        gui._content_id_ergaenzen_anbieten(self.ordner)
        self.assertEqual(gui.fragen, [])
        self.assertEqual(self._gelesen()["contentId"], "EP0001-PPSA24680_00-ECHTEKENNUNG0000")

    def test_bauweg_bietet_es_an_und_haelt_nie_auf(self) -> None:
        for antwort in (True, False):
            with self.subTest(antwort=antwort):
                save_param_json(dict(self.DOC), self.pfad)
                gui = _gui(antwort=antwort)
                self.assertTrue(gui._ensure_param_json(self.ordner),
                                "Eine fehlende Content-ID darf den Bau nie aufhalten")
                self.assertEqual(len(gui.fragen), 1)
                self.assertEqual("contentId" in self._gelesen(), antwort)

    def test_im_lauf_wird_nur_einmal_gefragt(self) -> None:
        """Eine Sammelkonvertierung mit zwei solchen Dumps: ein Fenster, nicht zwei.

        Die erste Antwort gilt fuer den Rest des Laufs - in beide Richtungen.
        """
        zweiter = os.path.join(self.td.name, "dump2")
        os.makedirs(os.path.join(zweiter, "sce_sys"), exist_ok=True)
        zweiter_pfad = os.path.join(zweiter, "sce_sys", "param.json")
        for antwort in (True, False):
            with self.subTest(antwort=antwort):
                save_param_json(dict(self.DOC), self.pfad)
                save_param_json(dict(self.DOC, titleId="PPSA24681"), zweiter_pfad)
                gui = _gui(antwort=antwort)
                gui.is_running = True
                gui._content_id_antwort = None
                gui._content_id_ergaenzen_anbieten(self.ordner)
                gui._content_id_ergaenzen_anbieten(zweiter)
                self.assertEqual(len(gui.fragen), 1)
                self.assertEqual("contentId" in self._gelesen(), antwort)
                with open(zweiter_pfad, encoding="utf-8") as fh:
                    self.assertEqual("contentId" in json.load(fh), antwort)

    def test_ausserhalb_eines_laufs_wird_jedes_mal_gefragt(self) -> None:
        """Ohne laufende Aufgabe gibt es nichts, wofuer eine Antwort gelten koennte."""
        gui = _gui(antwort=False)
        gui.is_running = False
        gui._content_id_antwort = True       # Rest eines frueheren Laufs
        gui._content_id_ergaenzen_anbieten(self.ordner)
        gui._content_id_ergaenzen_anbieten(self.ordner)
        self.assertEqual(len(gui.fragen), 2)
        self.assertNotIn("contentId", self._gelesen())


class OnlineHakenTests(unittest.TestCase):
    """Der param.json-Nachschlag folgt dem Haken in den Einstellungen."""

    def _gui(self, *, haken: bool, cli: bool = False, schalter: bool = False):
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui._metadaten_online_vorgabe = lambda: haken
        if cli:
            gui._cli_mode = True
            gui._cli_param_online = schalter
        return gui

    def test_fenster_folgt_dem_haken(self) -> None:
        self.assertTrue(self._gui(haken=True)._online_nachschlag_erlaubt())
        self.assertFalse(self._gui(haken=False)._online_nachschlag_erlaubt())

    def test_cli_folgt_dem_haken_und_der_schalter_erzwingt(self) -> None:
        self.assertTrue(self._gui(haken=True, cli=True)._online_nachschlag_erlaubt())
        self.assertFalse(self._gui(haken=False, cli=True)._online_nachschlag_erlaubt())
        self.assertTrue(self._gui(haken=False, cli=True, schalter=True)._online_nachschlag_erlaubt())

    def test_vorgabe_windows_und_linux_an_mac_aus(self) -> None:
        """Nie eingestellt: Windows und Linux ja, Mac nein (Wunsch 23.09.2026)."""
        import PS5ImageConverter_Pro_FINAL_revised as APP
        from PS5ImageConverter_Pro_FINAL_revised import PS5ConverterGUI

        gui = PS5ConverterGUI.__new__(PS5ConverterGUI)
        gui._load_setting = lambda name, vorgabe=None: vorgabe
        alt = APP.IST_MACOS
        try:
            for mac, erwartet in ((False, True), (True, False)):
                with self.subTest(mac=mac):
                    APP.IST_MACOS = mac
                    self.assertEqual(gui._online_nachschlag_erlaubt(), erwartet)
        finally:
            APP.IST_MACOS = alt


if __name__ == "__main__":
    unittest.main()
