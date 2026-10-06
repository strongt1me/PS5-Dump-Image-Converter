# -*- coding: utf-8 -*-
"""Die Knoepfe 4 bis 7 der Ansicht KONSOLE: Weboberflaeche von Prospero Manager, CoolSysCent-Pro, ShadowMount+ und SMPlusGui.

Nutzerwunsch vom 04.10.2026: "Knopf 6 soll ShadowMount+ heissen und die Weboberflaeche
von Shadowmount starten (wie bei ProsperoManager, einfach ueber Port 10101). Falls der
Payload noch nicht gestartet ist, soll dieser bitte zur PS5 gesendet werden (port 9021).
Ist Port 9021 nicht offen, soll der Port geoeffnet werden ..." - ebenso Knopf 7 (SMPlusGui,
Port 7777). Knopf 5 (CoolSysCent-Pro) kam am 05.10.2026 dazu: die eigene App des Projektinhabers,
das PS5 Cooling & System Center (Port 8086), "wie der Prospero Manager im rechten Bereich die Web UI
oeffnen; laeuft die App noch nicht, die ELF an Port 9021 senden; ist der Port nicht offen, den Port oeffnen".

Alle vier laufen ueber ``_konsole_webdienst_oeffnen``. Ins Netz geht kein Test: Abfrage,
Loader-Sicherung, Senden und Weboberflaeche sind durch Attrappen ersetzt, die festhalten,
was aufgerufen wurde.
"""
from __future__ import annotations

import ast
import re
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("konsole_webdienste")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_dienste as kd       # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

KLASSE = APP.PS5ConverterGUI
#: kennung -> (Dienst im Katalog, Port, erwartetes ELF-Muster beim Senden)
WEBDIENSTE = {
    "prosperomgr": ("prosperomgr", 7070, ""),
    "coolsyscent": ("coolsyscent", 8086, ""),
    "shadowmount": ("shadowmount", 10101, "shadowmountplus_v*.elf"),
    "smplusgui": ("smplusgui", 7777, ""),
}


def _schleife(grenze: float, bis=None, beobachten=None) -> None:
    """Eine echte Hauptschleife fuer hoechstens ``grenze`` Sekunden (Rueckrufe aus Faeden kommen nur so an)."""
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if beobachten is not None:
            beobachten()
        if (bis is not None and bis()) or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(10, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()


def _uebersicht(dienst: str, laeuft: bool):
    u = mock.Mock()
    u.laeuft.side_effect = lambda schluessel: laeuft if schluessel == dienst else False
    return u


class KnoepfeTests(unittest.TestCase):
    """Die acht Knoepfe und ihre Ziele - ohne Fenster."""

    def test_acht_knoepfe_in_dieser_reihenfolge(self) -> None:
        self.assertEqual(["dienste", "webkit", "bibliothek", "prosperomgr",
                          "coolsyscent", "shadowmount", "smplusgui", "directstream"],
                         [k for _s, k in KLASSE._KONSOLE_KNOEPFE])
        for nummer, (schluessel, _kennung) in enumerate(KLASSE._KONSOLE_KNOEPFE, start=1):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].startswith("%d. " % nummer))

    def test_die_namen_der_neuen_knoepfe(self) -> None:
        erwartet = {"konsole.btn_coolsyscent": "5. CoolSysCent-Pro",
                    "konsole.btn_shadowmount": "6. ShadowMount+",
                    "konsole.btn_smplusgui": "7. SMPlusGui",
                    "konsole.btn_directstream": "8. Direct Stream"}
        for schluessel, text in erwartet.items():
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertEqual(text, STRINGS[schluessel][sprache])

    def test_knopf_4_bis_7_sind_direktaktionen_ohne_seite(self) -> None:
        for kennung in ("prosperomgr", "coolsyscent", "shadowmount", "smplusgui"):
            with self.subTest(kennung=kennung):
                self.assertIn(kennung, KLASSE._KONSOLE_AKTIONEN)
                self.assertIn(kennung, KLASSE._KONSOLE_WEBDIENSTE)
                self.assertNotIn(kennung, KLASSE._KONSOLE_SEITEN)
                self.assertNotIn(kennung, KLASSE._KONSOLE_SEITENBAU)
                self.assertTrue(callable(getattr(KLASSE, KLASSE._KONSOLE_AKTIONEN[kennung])))

    def test_knopf_5_ist_das_cooling_center(self) -> None:
        """Seit dem 05.10.2026 hat Knopf 5 eine Funktion: Weboberflaeche des PS5 Cooling & System Center."""
        self.assertIn("coolsyscent", KLASSE._KONSOLE_AKTIONEN)
        self.assertEqual("_konsole_coolsyscent_oeffnen", KLASSE._KONSOLE_AKTIONEN["coolsyscent"])
        self.assertEqual(("coolsyscent", ""), KLASSE._KONSOLE_WEBDIENSTE["coolsyscent"])
        self.assertNotIn("coolsyscent", KLASSE._KONSOLE_FENSTER)
        eintrag = kd.dienst("coolsyscent")
        self.assertEqual(8086, eintrag.port)
        self.assertEqual("PS5_Cooling_System_Center_v*.elf", eintrag.payload_muster,
                         "Der Katalog traegt das Muster - der Knopf muss keines liefern.")

    def test_ports_und_dateien_stimmen_mit_dem_katalog(self) -> None:
        for kennung, (dienst, port, muster) in WEBDIENSTE.items():
            with self.subTest(kennung=kennung):
                eintrag = kd.dienst(dienst)
                self.assertEqual(port, eintrag.port)
                self.assertEqual("/", eintrag.web)
                self.assertEqual((dienst, muster), KLASSE._KONSOLE_WEBDIENSTE[kennung])

    def test_zu_jedem_webdienst_liegt_ein_payload_bei(self) -> None:
        """Das Muster (oder das des Katalogs) muss in ``helloworld`` eine Datei treffen."""
        ordner = PROJEKT / "helloworld"
        for kennung, (dienst, muster) in KLASSE._KONSOLE_WEBDIENSTE.items():
            with self.subTest(kennung=kennung):
                gesucht = muster or kd.dienst(dienst).payload_muster
                self.assertTrue(gesucht, "Weder der Knopf noch der Katalog nennen eine Datei.")
                self.assertTrue(list(ordner.glob(gesucht)), "Keine Datei fuer %s" % gesucht)

    def test_shadowmount_bleibt_im_katalog_ohne_payload_muster(self) -> None:
        """"Ausgewaehltes starten" soll es weiter nicht senden - nur sein eigener Knopf tut es."""
        self.assertEqual("", kd.dienst("shadowmount").payload_muster)

    def test_texte_zweisprachig_mit_denselben_platzhaltern(self) -> None:
        erwartet = {"konsole.webdienst_start": {"name"},
                    "konsole.webdienst_offen": {"name", "adresse"},
                    "konsole.webdienst_kein_port": {"name", "port"},
                    "konsole.webdienst_hinweis_titel": {"name"},
                    "konsole.webdienst_hinweis_text": {"name"},
                    "konsole.shadowmount_loopback": set(),
                    "konsole.coolsyscent_port": set()}
        for schluessel, platzhalter in erwartet.items():
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertTrue(text)
                    self.assertEqual(platzhalter, set(re.findall(r"\{(\w+)\}", text)))

    def test_der_hinweis_zu_shadowmount_nennt_den_schluessel(self) -> None:
        for sprache in ("de", "en"):
            self.assertIn("api_bind_address", STRINGS["konsole.shadowmount_loopback"][sprache])

    def test_der_hinweis_zum_cooling_center_nennt_port_und_einstellungen(self) -> None:
        """Bleibt der Port zu, ist meist ``http_port`` oder ``bind_address`` der App verstellt."""
        for sprache in ("de", "en"):
            text = STRINGS["konsole.coolsyscent_port"][sprache]
            for stueck in ("8086", "http_port", "bind_address"):
                with self.subTest(sprache=sprache, stueck=stueck):
                    self.assertIn(stueck, text)

    def test_die_alten_prospero_texte_sind_aufgegangen(self) -> None:
        self.assertEqual([], [k for k in STRINGS if k.startswith("konsole.prosperomgr_")])


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class AktionTests(unittest.TestCase):
    """Der Ablauf am wirklichen Programm: pruefen, Loader sichern, senden, Weboberflaeche oeffnen."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        app = self.app
        if getattr(app, "_konsole_tafel", None) is None:
            app._konsole_tafel_bauen()
        app._konsole_tafel_ip.set("127.0.0.1")
        app._konsole_webdienst_aktiv = ""
        app._konsole_webdienst_hinweis_schliessen()
        self.protokoll: list = []
        self.gespeichert: list = []
        browser = mock.Mock(side_effect=AssertionError("Browser geoeffnet"))
        self.addCleanup(browser.assert_not_called)
        for ziel, name, ersatz in (
                (app, "_append_to_log", self.protokoll.append),
                (app, "_save_setting", lambda k, v: self.gespeichert.append((k, v))),
                (APP.webbrowser, "open", browser)):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.addCleanup(self._aufraeumen)

    def _aufraeumen(self) -> None:
        self.app._konsole_webdienst_hinweis_schliessen()
        self.app._konsole_webdienst_aktiv = ""

    def _lauf(self, kennung: str, laeuft: bool, start_ok: bool = True, beobachten=None):
        """Drueckt den Knopf (ueber die Aktion) und wartet auf das Ende; liefert die Attrappen."""
        app = self.app
        dienst, _port, _muster = WEBDIENSTE[kennung]
        elfldr = mock.Mock(side_effect=lambda ip, u, texte: (time.sleep(0.25), _uebersicht(dienst, False))[1])
        start = mock.Mock(return_value=start_ok)
        web = mock.Mock()
        with mock.patch.object(APP.konsole_dienste, "pruefen", return_value=_uebersicht(dienst, laeuft)), \
                mock.patch.object(app, "_konsole_elfldr_sicherstellen", elfldr), \
                mock.patch.object(app, "_konsole_dienst_starten", start), \
                mock.patch.object(app, "_webansicht_oeffnen", web):
            getattr(app, KLASSE._KONSOLE_AKTIONEN[kennung])()
            _schleife(6.0, beobachten=beobachten,
                      bis=lambda: not app._konsole_webdienst_aktiv
                      and getattr(app, "_konsole_webdienst_hinweis_fenster", None) is None)
            _schleife(0.2, beobachten=beobachten)         # der Abschluss aus ``finally`` ist dann durch
        return elfldr, start, web

    def test_laeuft_der_dienst_schon_geht_nur_die_weboberflaeche_auf(self) -> None:
        for kennung, (dienst, port, _muster) in WEBDIENSTE.items():
            with self.subTest(kennung=kennung):
                gesehen = {"hinweis": False}

                def _beobachten() -> None:
                    if getattr(self.app, "_konsole_webdienst_hinweis_fenster", None) is not None:
                        gesehen["hinweis"] = True

                elfldr, start, web = self._lauf(kennung, laeuft=True, beobachten=_beobachten)
                elfldr.assert_not_called()
                start.assert_not_called()
                web.assert_called_once_with("http://127.0.0.1:%d/" % port,
                                            kd.dienst(dienst).name_schluessel, "uebersicht")
                self.assertFalse(gesehen["hinweis"], "Der Hinweis gilt nur, wenn gesendet wird.")

    def test_laeuft_er_nicht_wird_erst_der_loader_gesichert_dann_gesendet(self) -> None:
        for kennung, (dienst, port, muster) in WEBDIENSTE.items():
            with self.subTest(kennung=kennung):
                gesehen = {"hinweis": False}

                def _beobachten() -> None:
                    if getattr(self.app, "_konsole_webdienst_hinweis_fenster", None) is not None:
                        gesehen["hinweis"] = True

                elfldr, start, web = self._lauf(kennung, laeuft=False, beobachten=_beobachten)
                elfldr.assert_called_once()
                start.assert_called_once()
                aufruf = start.call_args
                self.assertEqual((dienst, "127.0.0.1"), aufruf.args[:2])
                self.assertEqual(muster, aufruf.kwargs.get("muster"),
                                 "ShadowMount+ traegt kein Muster im Katalog - der Knopf liefert es.")
                self.assertTrue(callable(aufruf.kwargs.get("melden")))
                web.assert_called_once()
                self.assertTrue(gesehen["hinweis"], "Beim Senden erscheint der Hinweis ohne Knopf.")
                self.assertIsNone(self.app._konsole_webdienst_hinweis_fenster, "... und schliesst sich.")

    def test_bleibt_der_port_zu_steht_das_im_protokoll(self) -> None:
        for kennung, (dienst, port, _muster) in WEBDIENSTE.items():
            with self.subTest(kennung=kennung):
                self.protokoll.clear()
                _elfldr, _start, web = self._lauf(kennung, laeuft=False, start_ok=False)
                web.assert_not_called()
                text = "".join(self.protokoll)
                name = STRINGS[kd.dienst(dienst).name_schluessel]["de"]
                self.assertIn("Port %d antwortet nicht" % port, text)
                self.assertIn(name, text, "Der Name des Dienstes, nicht sein Textschluessel.")
                self.assertNotIn(kd.dienst(dienst).name_schluessel, text)
                hinweis = STRINGS["konsole.shadowmount_loopback"]["de"]
                if kennung == "shadowmount":
                    self.assertIn(hinweis, text, "ShadowMount+: Der Grund ist meist api_bind_address.")
                else:
                    self.assertNotIn("api_bind_address", text)
                if kennung == "coolsyscent":
                    self.assertIn(STRINGS["konsole.coolsyscent_port"]["de"], text,
                                  "Cooling Center: Der Grund ist meist ein verstellter http_port.")
                else:
                    self.assertNotIn("http_port", text)

    def test_waehrenddessen_sind_alle_vier_knoepfe_gesperrt(self) -> None:
        app = self.app
        knoepfe = list(app._konsole_webdienst_knoepfe)
        self.assertEqual(4, len(knoepfe))
        stand: list = []

        def _beobachten() -> None:
            if app._konsole_webdienst_aktiv:
                stand.append([str(k.cget("state")) for k in knoepfe])

        self._lauf("coolsyscent", laeuft=False, beobachten=_beobachten)
        self.assertTrue(stand, "Die Aktion wurde nie beobachtet.")
        self.assertIn(["disabled"] * 4, stand)
        self.assertEqual(["normal"] * 4, [str(k.cget("state")) for k in knoepfe], "danach wieder frei")

    def test_eine_zweite_aktion_waehrend_der_ersten_wird_abgewiesen(self) -> None:
        app = self.app
        app._konsole_webdienst_aktiv = "prosperomgr"
        with mock.patch.object(APP.threading, "Thread") as faden:
            app._konsole_webdienst_oeffnen("shadowmount")
        faden.assert_not_called()

    def test_ohne_adresse_ein_hinweis_und_kein_faden(self) -> None:
        app = self.app
        app._konsole_tafel_ip.set("")
        with mock.patch.object(APP, "messagebox") as box, \
                mock.patch.object(APP.threading, "Thread") as faden:
            app._konsole_shadowmount_oeffnen()
        box.showwarning.assert_called_once()
        faden.assert_not_called()
        self.assertFalse(app._konsole_webdienst_aktiv)

    def test_der_name_im_sendeprotokoll_ist_der_des_dienstes(self) -> None:
        """Bis v1.9.62 stand dort der Textschluessel ("dienst.prosperomgr") statt des Namens."""
        app = self.app
        with mock.patch.object(APP.konsole_dienste, "pruefen", return_value=_uebersicht("smplusgui", False)), \
                mock.patch.object(app, "_konsole_elfldr_sicherstellen",
                                  lambda ip, u, t: _uebersicht("smplusgui", False)), \
                mock.patch.object(app, "_send_payload_to_ps5", lambda ip, pfad, **k: (True, "1 KB")), \
                mock.patch.object(APP.konsole_dienste, "warten_bis_bereit", lambda *a, **k: True), \
                mock.patch.object(app, "_webansicht_oeffnen"):
            app._konsole_smplusgui_oeffnen()
            _schleife(6.0, bis=lambda: not app._konsole_webdienst_aktiv)
            _schleife(0.2)
        text = "".join(self.protokoll)
        self.assertIn("SMPlusGui", text)
        self.assertNotIn("dienst.smplusgui", text)
        self.assertIn(app._t("dienste.log_sende", name="SMPlusGui",
                             datei=Path(app._konsole_payload_datei("SMPlusGui_v*.elf")).name), text)

    def test_knopf_5_oeffnet_das_cooling_center_statt_zu_sagen_es_kommt_noch(self) -> None:
        app = self.app
        with mock.patch.object(APP, "messagebox") as box, \
                mock.patch.object(app, "_konsole_webdienst_oeffnen") as weg:
            app._konsole_knopf_gedrueckt("coolsyscent", "konsole.btn_coolsyscent")
        weg.assert_called_once_with("coolsyscent")
        box.showinfo.assert_not_called()

    def test_das_cooling_center_wird_mit_dem_namen_des_katalogs_gemeldet(self) -> None:
        """Im Protokoll steht der Name der App, nicht ihr Textschluessel - und die Adresse mit Port 8086."""
        self.protokoll.clear()
        _elfldr, _start, web = self._lauf("coolsyscent", laeuft=True)
        web.assert_called_once_with("http://127.0.0.1:8086/", "dienst.coolsyscent", "uebersicht")
        text = "".join(self.protokoll)
        self.assertIn("PS5 Cooling & System Center", text)
        self.assertIn("http://127.0.0.1:8086/", text)
        self.assertNotIn("dienst.coolsyscent", text)

    def test_das_cooling_center_wird_mit_seiner_datei_gesendet(self) -> None:
        """Ohne Knopf-Muster nimmt der Sendeweg das des Katalogs - und die Datei liegt in helloworld."""
        _elfldr, start, _web = self._lauf("coolsyscent", laeuft=False)
        start.assert_called_once()
        self.assertEqual(("coolsyscent", "127.0.0.1"), start.call_args.args[:2])
        datei = self.app._konsole_payload_datei(kd.dienst("coolsyscent").payload_muster)
        self.assertTrue(datei, "Zum Muster des Katalogs liegt keine Datei bei.")
        self.assertTrue(Path(datei).name.startswith("PS5_Cooling_System_Center_v"))


class QuelltextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        baum = ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8"))
        klasse = next(k for k in baum.body if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
        cls.methoden = {k.name: k for k in klasse.body if isinstance(k, ast.FunctionDef)}

    def test_das_muster_geht_an_den_sendeweg(self) -> None:
        text = ast.unparse(self.methoden["_konsole_webdienst_oeffnen"])
        self.assertIn("muster=muster", text)
        self.assertIn("_konsole_elfldr_sicherstellen", text,
                      "Ist Port 9021 zu, muss der Loader zuerst gesichert werden.")
        parameter = [a.arg for a in self.methoden["_konsole_dienst_starten"].args.args]
        self.assertIn("muster", parameter)

    def test_die_vier_wrapper_rufen_denselben_weg(self) -> None:
        for name, kennung in (("_konsole_prosperomgr_oeffnen", "prosperomgr"),
                              ("_konsole_coolsyscent_oeffnen", "coolsyscent"),
                              ("_konsole_shadowmount_oeffnen", "shadowmount"),
                              ("_konsole_smplusgui_oeffnen", "smplusgui")):
            with self.subTest(name=name):
                self.assertEqual("self._konsole_webdienst_oeffnen('%s')" % kennung,
                                 ast.unparse(self.methoden[name].body[-1].value))

    def test_nichts_mehr_vom_alten_prospero_zustand(self) -> None:
        quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        for rest in ("_konsole_prosperomgr_laeuft", "_konsole_prosperomgr_knopf",
                     "_konsole_prosperomgr_hinweis", "konsole.prosperomgr_"):
            with self.subTest(rest=rest):
                self.assertNotIn(rest, quelle)


if __name__ == "__main__":
    unittest.main()
