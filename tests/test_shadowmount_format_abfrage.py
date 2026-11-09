# -*- coding: utf-8 -*-
"""ShadowMount+ vor / ab 1.7beta12: die einmalige Frage und die Dateigrenze im Programm.

Nutzerwunsch 09.11.2026: "In der neuen Version von ShadowMountPlus v1.7beta12 wird auch etwas an der config.ini
geaendert. Man soll gefragt werden, welche Version genutzt wird (vor oder ab 1.7beta12), damit die config.ini
korrekt gehandhabt wird." Die reine Uebersetzung steht in ``test_shadowmount_config.py``; hier das Verhalten des
Programms: Frage einmal, Merken, Lesen und Schreiben ueber FTP, Meldungstexte, Fassungserkennung und der echte
Editor mit einer Datei im neuen Format.
"""
from __future__ import annotations

import os
import sys
import time
import unittest
from unittest import mock

PROJEKT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJEKT not in sys.path:
    sys.path.insert(0, PROJEKT)

import pruefumgebung

pruefumgebung.umlenken("shadowmount_format_abfrage")

import ftplib

import PS5ImageConverter_Pro_FINAL_revised as APP
from ps5_validator.utils import shadowmount_config as sc
from ps5_validator.utils import shadowmount_generation as sm_gen
from ps5_validator.utils.ini_config import parse_flat_ini, parse_flat_ini_multi

try:
    import tkinter as tk
    from tkinter import messagebox
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    TK_DA = True
except Exception:                                    # pragma: no cover
    TK_DA = False
    _WURZEL = None

G = APP.PS5ConverterGUI
CONFIG = sc.CONFIG_PFAD
PROFILES = sc.PROFILES_PFAD

V2_CONFIG = """\
[config]
version = 2

# Erklaerung zur Fehlersuche
[general]
debug = on

[scan]
path = /data/homebrew

[emulators]
# update_enabled = on
path = /data/shadowmount/emus

[smb:NAS]
path = smb://192.168.1.10/games
active = on
"""

V1_CONFIG = "# Vorlage\r\ndebug=1\r\nscanpath=/data/homebrew\r\nupdate_emulators=1\r\n"


class _Ftp:
    """Eine Gegenstelle mit mehreren Dateien; fehlende Dateien antworten wie ftpsrv mit 550."""

    def __init__(self, dateien: "dict[str, str]") -> None:
        self.dateien = {k: v.encode("utf-8") for k, v in dateien.items()}
        self.stor: "list[tuple[str, bytes]]" = []

    def connect(self, *a, **k): pass
    def login(self, *a, **k): pass
    def quit(self): pass
    def mkd(self, pfad): pass

    def retrbinary(self, befehl, schreiber):
        pfad = befehl.split(" ", 1)[1]
        if pfad not in self.dateien:
            raise ftplib.error_perm("550 %s: No such file or directory" % pfad)
        schreiber(self.dateien[pfad])

    def storbinary(self, befehl, strom):
        pfad = befehl.split(" ", 1)[1]
        daten = strom.read()
        self.stor.append((pfad, daten))
        self.dateien[pfad] = daten

    def text(self, pfad: str) -> str:
        return self.dateien[pfad].decode("utf-8")

    def geschrieben(self) -> "list[str]":
        return [pfad for pfad, _ in self.stor]


def _gui(einstellungen: "dict[str, object] | None" = None, root=object()):
    """Ein Programmobjekt ohne Fenster, mit gestellten Einstellungen und Rueckfragen."""
    gui = G.__new__(G)
    gui._current_language = "de"
    gui.einstellungen = dict(einstellungen or {})
    gui.protokoll = []
    gui._append_to_log = gui.protokoll.append
    gui._load_setting = lambda schluessel, vorgabe: gui.einstellungen.get(schluessel, vorgabe)
    gui._save_setting = lambda schluessel, wert: gui.einstellungen.__setitem__(schluessel, wert)
    gui._im_hauptfaden = lambda funktion, *a, **k: funktion(*a, **k)
    gui.root = root
    return gui


class FrageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frage = mock.patch.object(APP.messagebox, "askyesno", return_value=True)
        self.info = mock.patch.object(APP.messagebox, "showinfo")
        self.askyesno = self.frage.start()
        self.showinfo = self.info.start()
        self.addCleanup(self.frage.stop)
        self.addCleanup(self.info.stop)

    def test_ja_heisst_ab_beta12_und_wird_gemerkt(self) -> None:
        gui = _gui()
        self.assertEqual(sc.FORMAT_V2, gui._sm_format_klaeren())
        self.assertEqual(sc.FORMAT_V2, gui.einstellungen["shadowmount_config_format"])
        self.assertTrue(any("ab 1.7beta12" in z for z in gui.protokoll), gui.protokoll)

    def test_nein_heisst_vor_beta12(self) -> None:
        self.askyesno.return_value = False
        gui = _gui()
        self.assertEqual(sc.FORMAT_V1, gui._sm_format_klaeren())
        self.assertEqual(sc.FORMAT_V1, gui.einstellungen["shadowmount_config_format"])

    def test_gefragt_wird_nur_einmal(self) -> None:
        gui = _gui()
        gui._sm_format_klaeren()
        gui._sm_format_klaeren()
        gui._sm_format_klaeren(sc.FORMAT_V1)
        self.assertEqual(1, self.askyesno.call_count)

    def test_eine_gespeicherte_wahl_wird_ohne_frage_benutzt(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        self.assertEqual(sc.FORMAT_V2, gui._sm_format_klaeren())
        self.askyesno.assert_not_called()

    def test_die_frage_nennt_beide_fassungen_und_die_beobachtung(self) -> None:
        gui = _gui()
        gui._sm_format_klaeren(sc.FORMAT_V1)
        titel, text = self.askyesno.call_args.args
        self.assertIn("1.7beta12", text)
        self.assertIn("update_emulators=0", text, "das Beispiel der alten Schreibweise")
        self.assertIn("[general]", text, "das Beispiel der neuen Schreibweise")
        self.assertIn("flache Zeilen", text, "Hinweis auf das, was die Datei zeigt")
        self.assertEqual("no", self.askyesno.call_args.kwargs["default"], "flache Datei: Vorbelegung 'Nein'")

    def test_ohne_fenster_und_im_cli_wird_nicht_gefragt(self) -> None:
        gui = _gui(root=None)
        self.assertEqual(sc.FORMAT_V1, gui._sm_format_klaeren())
        self.assertEqual(sc.FORMAT_V2, gui._sm_format_klaeren(sc.FORMAT_V2))
        cli = _gui()
        cli._cli_mode = True
        self.assertEqual(sc.FORMAT_V1, cli._sm_format_klaeren())
        self.askyesno.assert_not_called()
        self.assertNotIn("shadowmount_config_format", gui.einstellungen, "ohne Antwort wird nichts gemerkt")

    def test_wird_das_fenster_geschlossen_bleibt_die_frage_offen(self) -> None:
        gui = _gui()
        gui._sm_ja_nein = lambda *a, **k: None
        self.assertEqual(sc.FORMAT_V1, gui._sm_format_klaeren())
        self.assertNotIn("shadowmount_config_format", gui.einstellungen)

    def test_wieder_fragen_ueber_die_einstellung(self) -> None:
        """Unter EINSTELLUNGEN laesst sich "Noch nicht festgelegt" waehlen - dann kommt die Frage erneut."""
        gui = _gui({"shadowmount_config_format": "v1"})
        gui._sm_format_setzen("")
        self.assertEqual(sc.FORMAT_V2, gui._sm_format_klaeren(), "die Antwort der gestellten Frage ist Ja")
        self.assertEqual(1, self.askyesno.call_count)


class LesenSchreibenTests(unittest.TestCase):
    def setUp(self) -> None:
        self.info = mock.patch.object(APP.messagebox, "showinfo")
        self.showinfo = self.info.start()
        self.addCleanup(self.info.stop)

    def test_format_2_wird_als_ansicht_in_alten_schluesseln_gelesen(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        ftp = _Ftp({CONFIG: V2_CONFIG})
        text = gui._ampr_gen_config_lesen(ftp)
        werte = parse_flat_ini(text)
        self.assertEqual("on", werte["debug"])
        self.assertEqual("/data/shadowmount/emus", werte["emulators_path"])
        self.assertNotIn("update_emulators", werte, "die Vorlage ist auskommentiert")
        self.assertEqual(["/data/homebrew"], parse_flat_ini_multi(text)["scanpath"])

    def test_die_ansicht_gilt_als_neue_fassung(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        text = gui._ampr_gen_config_lesen(_Ftp({CONFIG: V2_CONFIG}))
        befund = sm_gen.generation_erkennen(config_text=text)
        self.assertEqual(sm_gen.NEU, befund["generation"])
        self.assertFalse(befund["widerspruch"])

    def test_format_1_bleibt_wie_es_ist(self) -> None:
        gui = _gui({"shadowmount_config_format": "v1"})
        self.assertEqual(V1_CONFIG, gui._ampr_gen_config_lesen(_Ftp({CONFIG: V1_CONFIG})))

    def test_fehlt_die_datei_kommt_leer_zurueck(self) -> None:
        for fmt in ("v1", "v2"):
            with self.subTest(format=fmt):
                gui = _gui({"shadowmount_config_format": fmt})
                self.assertEqual("", gui._ampr_gen_config_lesen(_Ftp({})))

    def test_die_datei_gewinnt_gegen_die_gemerkte_wahl_und_der_nutzer_erfaehrt_es(self) -> None:
        gui = _gui({"shadowmount_config_format": "v1"})
        text = gui._ampr_gen_config_lesen(_Ftp({CONFIG: V2_CONFIG}))
        self.assertIn("emulators_path=/data/shadowmount/emus", text)
        self.assertEqual("v2", gui.einstellungen["shadowmount_config_format"], "Einstellung angepasst")
        self.assertEqual(1, self.showinfo.call_count, "nicht still: ein Fenster sagt es")
        self.assertIn("ab 1.7beta12", self.showinfo.call_args.args[1])

    def test_schreiben_im_neuen_format_aendert_nur_den_einen_wert(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        ftp = _Ftp({CONFIG: V2_CONFIG})
        text = gui._ampr_gen_config_lesen(ftp)
        gui._ampr_gen_config_schreiben(ftp, text, {"update_emulators": "0"})
        self.assertEqual([CONFIG], ftp.geschrieben(), "profiles.ini bleibt unberuehrt")
        neu = ftp.text(CONFIG)
        self.assertIn("update_enabled = off", neu)
        self.assertIn("# update_enabled = on", neu, "die Vorlage bleibt stehen")
        self.assertIn("[smb:NAS]\npath = smb://192.168.1.10/games", neu, "SMB-Verbindung bleibt")
        self.assertIn("# Erklaerung zur Fehlersuche", neu)
        self.assertNotIn("update_emulators", neu, "der alte Schluessel gehoert nicht in die neue Datei")

    def test_je_spiel_einstellungen_landen_in_profiles_ini(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        ftp = _Ftp({CONFIG: V2_CONFIG})
        text = gui._ampr_gen_config_lesen(ftp)
        gui._ampr_gen_config_schreiben(ftp, text, {"global_fakelib_exclude": ["PPSA12345"]})
        self.assertEqual([PROFILES], ftp.geschrieben(), "die config.ini bleibt unberuehrt")
        self.assertIn("[game:PPSA12345]\nignore_global_fakelib = on", ftp.text(PROFILES))
        self.assertTrue(any("profiles.ini" in z for z in gui.protokoll))
        # und danach wieder lesbar wie bisher
        jetzt = gui._ampr_gen_config_lesen(ftp)
        self.assertEqual(["PPSA12345"], parse_flat_ini_multi(jetzt)["global_fakelib_exclude"])

    def test_schreiben_im_alten_format_wie_bisher(self) -> None:
        gui = _gui({"shadowmount_config_format": "v1"})
        ftp = _Ftp({CONFIG: V1_CONFIG})
        text = gui._ampr_gen_config_lesen(ftp)
        gui._ampr_gen_config_schreiben(ftp, text, {"update_emulators": "0"})
        self.assertEqual([CONFIG], ftp.geschrieben())
        self.assertIn("update_emulators=0", ftp.text(CONFIG))
        self.assertIn("# Vorlage", ftp.text(CONFIG))

    def test_ohne_datei_im_neuen_format_entsteht_eine_neue(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        ftp = _Ftp({})
        text = gui._ampr_gen_config_lesen(ftp)
        gui._ampr_gen_config_schreiben(ftp, text, {"update_emulators": "0"})
        self.assertTrue(ftp.text(CONFIG).startswith("[config]\nversion = 2\n"))
        self.assertIn("[emulators]\nupdate_enabled = off", ftp.text(CONFIG))

    def test_ein_wert_gleich_dem_bestand_schreibt_nichts(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        ftp = _Ftp({CONFIG: V2_CONFIG})
        text = gui._ampr_gen_config_lesen(ftp)
        gui._ampr_gen_config_schreiben(ftp, text, {"debug": "on"})
        self.assertEqual([], ftp.geschrieben())

    def test_der_mitschnitt_stellt_die_alten_werte_im_neuen_format_wieder_her(self) -> None:
        gui = _gui({"shadowmount_config_format": "v2"})
        ftp = _Ftp({CONFIG: V2_CONFIG})
        vorher = gui._ampr_gen_config_lesen(ftp)
        gui._ampr_gen_config_schreiben(ftp, vorher, {"update_emulators": "0"})
        config = {"vorher": vorher, "geschrieben": None, "werte": {"update_emulators": None}}
        self.assertTrue(gui._ampr_mitschnitt_config_zurueck(ftp, config))
        aktiv = [(a.lower(), k.lower()) for a, k, _w in sc.eintraege(ftp.text(CONFIG))]
        self.assertNotIn(("emulators", "update_enabled"), aktiv, "der umgestellte Schluessel ist wieder weg")
        self.assertIn(("emulators", "path"), aktiv, "alles andere bleibt")


class TextTests(unittest.TestCase):
    def test_meldungen_nennen_im_neuen_format_die_neuen_schluessel(self) -> None:
        neu = _gui({"shadowmount_config_format": "v2"})._t("ampr.ng_update_emulators")
        self.assertIn("[emulators] update_enabled=0", neu)
        self.assertNotIn(" update_emulators", neu)
        alt = _gui({"shadowmount_config_format": "v1"})._t("ampr.ng_update_emulators")
        self.assertIn("update_emulators=0", alt)
        offen = _gui()._t("ampr.ng_update_emulators")
        self.assertIn("update_emulators=0", offen, "solange nicht gefragt wurde, bleibt es beim Gewohnten")

    def test_ng_hinweis_fragt_zuerst_und_nennt_dann_die_richtigen_schluessel(self) -> None:
        gui = _gui()
        with mock.patch.object(APP.messagebox, "askyesno", return_value=True) as frage, \
                mock.patch.object(APP.messagebox, "showinfo") as info:
            gui._ampr_ng_hinweis()
        self.assertEqual(1, frage.call_count)
        self.assertIn("[emulators] update_enabled=0", info.call_args.args[1])
        self.assertTrue(any("[emulators] update_enabled=0" in z for z in gui.protokoll))

    def test_die_texte_der_frage_gibt_es_in_jeder_sprache(self) -> None:
        from ps5_validator.utils.i18n import STRINGS
        for schluessel in ("smcfg.frage_titel", "smcfg.frage", "smcfg.hinweis_v1", "smcfg.hinweis_v2", "smcfg.name_v1",
                           "smcfg.name_v2", "smcfg.gewaehlt", "smcfg.abweichung", "smcfg.abweichung_titel",
                           "smcfg.nicht_uebernommen", "smcfg.profiles_geschrieben", "smcfg.editor_v2",
                           "settings_dialog.smcfg_section", "settings_dialog.smcfg_hint",
                           "settings_dialog.smcfg_ungefragt", "settings_dialog.smcfg_v1", "settings_dialog.smcfg_v2"):
            for sprache in ("de", "en", "es", "it", "fr"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache].strip())
        for sprache in ("de", "en", "es", "it", "fr"):
            self.assertIn("{hinweis}", STRINGS["smcfg.frage"][sprache])
            self.assertIn("1.7beta12", STRINGS["smcfg.frage"][sprache])


@unittest.skipUnless(TK_DA, "Ohne Anzeige laesst sich kein Fenster oeffnen")
class EditorFormat2Tests(unittest.TestCase):
    """Das echte Editorfenster mit einer config.ini im neuen Format - nur die FTP-Gegenstelle ist gestellt."""

    VORGABEN = {"debug": "1", "scanpath": "/data/homebrew", "update_emulators": "1", "lvd_ufs_sector_size": "4096",
                "kstuff_delay": "25"}

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._ps5_port_finden = lambda ip, port, art: port
        cls.app._save_setting = lambda *a, **k: None
        cls.app._current_language = "de"

    def setUp(self) -> None:
        self.app.__dict__.pop("_sm_format_cache", None)
        self.app.__dict__.pop("_sm_stand", None)
        self.ftp = _Ftp({CONFIG: V2_CONFIG})
        ftp = self.ftp
        self._echtes_ftp = ftplib.FTP
        ftplib.FTP = lambda: ftp
        self.fragen: "list[str]" = []
        self._echte = (messagebox.askyesno, messagebox.showwarning, messagebox.showinfo)
        messagebox.askyesno = lambda *a, **k: (self.fragen.append(a[1] if len(a) > 1 else "") or True)
        messagebox.showwarning = lambda *a, **k: None
        messagebox.showinfo = lambda *a, **k: None
        vorher = {str(w) for w in _WURZEL.winfo_children()}
        self.app._show_remote_ini_editor("Pruefung", CONFIG, "/data/shadowmount/debug.log",
                                         dict(self.VORGABEN), "pruefung")
        self._ruhen(0.4)
        neu = [w for w in _WURZEL.winfo_children()
               if str(w) not in vorher and isinstance(w, tk.Toplevel) and w.winfo_exists()]
        self.assertTrue(neu, "Es wurde kein Editorfenster geoeffnet")
        self.fenster = neu[-1]
        self._sammle(self.fenster, "Entry")[0].insert(0, "127.0.0.1")
        self.knoepfe = {str(b.cget("text")).upper(): b for b in self._sammle(self.fenster, "Button")}

    def tearDown(self) -> None:
        ftplib.FTP = self._echtes_ftp
        messagebox.askyesno, messagebox.showwarning, messagebox.showinfo = self._echte
        self.app.__dict__.pop("_sm_format_cache", None)
        self.app.__dict__.pop("_sm_stand", None)
        if self.fenster.winfo_exists():
            self.fenster.destroy()

    @classmethod
    def _sammle(cls, widget, art):
        raus = []
        for kind in widget.winfo_children():
            if kind.winfo_class().endswith(art) or kind.__class__.__name__ == art:
                raus.append(kind)
            raus += cls._sammle(kind, art)
        return raus

    @staticmethod
    def _ruhen(sekunden: float) -> None:
        ende = time.perf_counter() + sekunden
        while time.perf_counter() < ende:
            _WURZEL.update()
            time.sleep(0.01)

    def _druecken(self, teil: str) -> None:
        for name, knopf in self.knoepfe.items():
            if teil in name:
                knopf.invoke()
                return
        self.fail("Kein Knopf enthaelt %r - vorhanden: %s" % (teil, sorted(self.knoepfe)))

    def _ablauf(self, *schritte, schrittzeit: float = 1.6) -> None:
        rest = list(schritte)
        notaus = _WURZEL.after(int((len(rest) + 2) * schrittzeit * 1000) + 5000, _WURZEL.quit)

        def _weiter() -> None:
            if rest:
                rest.pop(0)()
                _WURZEL.after(int(schrittzeit * 1000), _weiter)
            else:
                _WURZEL.quit()

        _WURZEL.after(200, _weiter)
        _WURZEL.mainloop()
        try:
            _WURZEL.after_cancel(notaus)
        except Exception:
            pass

    def _tabelle(self):
        baum = self._sammle(self.fenster, "Treeview")[0]
        return {baum.item(i, "values")[0]: baum.item(i, "values")[1] for i in baum.get_children()}

    def test_laden_zeigt_die_neuen_namen_ohne_die_entfallenen_schluessel(self) -> None:
        self._ablauf(lambda: self._druecken("LADEN"))
        tabelle = self._tabelle()
        self.assertIn("[scan] path", tabelle)
        self.assertEqual("on", tabelle["[general] debug"])
        self.assertNotIn("kstuff_delay", tabelle, "gibt es im neuen Format nicht")
        self.assertEqual(1, sum("1.7beta12" in f for f in self.fragen), "die Frage kam genau einmal")

    def test_schreiben_haelt_das_neue_format_ein(self) -> None:
        self._ablauf(lambda: self._druecken("LADEN"), lambda: self._druecken("SCHREIBEN"))
        self.assertIn(CONFIG, self.ftp.geschrieben())
        neu = self.ftp.text(CONFIG)
        self.assertEqual(sc.FORMAT_V2, sc.format_erkennen(neu))
        self.assertTrue(neu.startswith("[config]\nversion = 2"), "die Versionsmarke bleibt vorn")
        self.assertIn("[smb:NAS]", neu, "die SMB-Verbindung ueberlebt")
        self.assertIn("# Erklaerung zur Fehlersuche", neu)
        self.assertNotIn("kstuff", neu)
        self.assertNotIn("update_emulators", neu, "keine alten Schluessel in der neuen Datei")
        self.assertIn("[sectors]", neu, "ein Schluessel aus den Vorgaben wurde im richtigen Abschnitt angelegt")
        self.assertIn("lvd_ufs = 4096", neu)

    def test_ein_zweites_schreiben_bleibt_moeglich(self) -> None:
        self._ablauf(lambda: self._druecken("LADEN"), lambda: self._druecken("SCHREIBEN"),
                     lambda: self._druecken("SCHREIBEN"))
        self.assertGreaterEqual(len(self.ftp.stor), 1)
        self.assertEqual(sc.FORMAT_V2, sc.format_erkennen(self.ftp.text(CONFIG)))

    def test_hat_inzwischen_jemand_die_datei_geaendert_wird_nicht_geschrieben(self) -> None:
        def _fremd_aendern() -> None:
            self.ftp.dateien[PROFILES] = b"[config]\nversion = 2\n\n[game:PPSA00001]\nfakelib = disabled\n"
            self.ftp.stor.clear()

        self._ablauf(lambda: self._druecken("LADEN"), _fremd_aendern, lambda: self._druecken("SCHREIBEN"))
        self.assertEqual([], self.ftp.stor, "profiles.ini hat sich seit dem Laden geaendert - nichts ueberschreiben")


if __name__ == "__main__":
    unittest.main()
