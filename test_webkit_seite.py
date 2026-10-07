# -*- coding: utf-8 -*-
""""2. WebKit Autoloader" als Seite rechts in der Ansicht KONSOLE (seit v1.9.63).

Nutzerwunsch vom 04.10.2026: Unter den Fassungen 0.4.0 bis 0.5.2 waehlen koennen;
kommt von itsPLK eine neuere Fassung dazu, soll sie von selbst in die Auswahl.
Das Fenster des WebKit Autoloaders gehoert in die rechte Seite - an die Stelle
der bisherigen Spielstaende-Seite, deren Funktion ganz heraus ist (Garlic laeuft
weiter ueber "Konsole & Payloads").

Ins Netz geht kein Test: Portabfrage, Senden, Hostprozess und Browser sind vorab
durch werfende Attrappen ersetzt, die die Aufraeumrunde von aussen prueft.
"""
from __future__ import annotations

import gc
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("webkit_seite")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_dienste as kd       # noqa: E402
from ps5_validator.utils.i18n import STRINGS                # noqa: E402

try:
    import tkinter as tk
    from tkinter import ttk
    _WURZEL = tk._default_root or tk.Tk()
    _WURZEL.withdraw()
    _TK_DA = True
except Exception:  # noqa: BLE001
    _WURZEL = None
    _TK_DA = False

KLASSE = APP.PS5ConverterGUI
#: Die vier Fassungen, die der Nutzer am 04.10.2026 verlangt hat (neueste zuerst).
FASSUNGEN = ["0.6.0", "0.5.2", "0.5.1", "0.4.0"]   # 0.5.0 entfernt am 07.10.2026 (Dateien defekt)
DATEINAMEN = {"exe": "webkit-autoloader-host_v%s.exe",
              "py": "webkit-autoloader-host_v%s.py",
              "elf": "webkit-autoloader-installer_v%s.elf"}


def _alle(widget):
    for kind in widget.winfo_children():
        yield kind
        yield from _alle(kind)


def _text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except Exception:  # noqa: BLE001
        return ""


def _bis(bedingung, grenze: float = 8.0) -> bool:
    ende = time.monotonic() + grenze
    while time.monotonic() < ende:
        _WURZEL.update()
        if bedingung():
            return True
        time.sleep(0.02)
    return False


def _schleife(grenze: float, bis=None) -> None:
    """Eine echte Hauptschleife fuer hoechstens ``grenze`` Sekunden.

    Rueckrufe aus Arbeitsfaeden (``root.after``) kommen nur an, solange wirklich
    eine Hauptschleife laeuft - ``update()`` allein genuegt nicht (dasselbe Muster
    wie in test_konsole_dienste.ProsperoMgrHinweisTests).
    """
    ende = time.monotonic() + grenze

    def _takt() -> None:
        if (bis is not None and bis()) or time.monotonic() > ende:
            _WURZEL.quit()
        else:
            _WURZEL.after(10, _takt)

    _WURZEL.after(0, _takt)
    _WURZEL.mainloop()


def _gezeigt(widget) -> bool:
    try:
        return bool(widget is not None and widget.winfo_manager() == "grid"
                    and widget.grid_info())
    except Exception:  # noqa: BLE001
        return False


def _ordner_mit(fassungen: dict[str, list[str]]) -> tempfile.TemporaryDirectory:
    """Ein Ordner mit Attrappen: je Fassung die genannten Arten (``exe``/``py``/``elf``)."""
    ordner = tempfile.TemporaryDirectory()
    for nummer, arten in fassungen.items():
        for art in arten:
            (Path(ordner.name) / (DATEINAMEN[art] % nummer)).write_bytes(b"x" * 2048)
    return ordner


def _nackt(ordner: str | None = None):
    """Ein Programmobjekt ohne Aufbau; ``ordner`` ersetzt den mitgelieferten Ordner."""
    objekt = KLASSE.__new__(KLASSE)
    objekt._t = lambda schluessel, **werte: STRINGS[schluessel]["de"].format(**werte)
    objekt._load_setting = lambda _schluessel, vorgabe="": vorgabe
    if ordner is not None:
        objekt._webkit_ordner = lambda: ordner
    return objekt


class FassungenTests(unittest.TestCase):
    """Die Liste der Fassungen entsteht beim Hinsehen aus dem Ordner."""

    def test_die_liste_ist_nach_zahlen_sortiert_neueste_zuerst(self) -> None:
        mit = _ordner_mit({"0.9.0": ["exe", "py", "elf"], "0.10.0": ["elf"], "0.4.0": ["py"]})
        self.addCleanup(mit.cleanup)
        self.assertEqual(["0.10.0", "0.9.0", "0.4.0"], _nackt(mit.name)._webkit_fassungen_liste())

    def test_eine_weitere_fassung_erscheint_ohne_codeaenderung(self) -> None:
        mit = _ordner_mit({"0.5.2": ["exe", "py", "elf"]})
        self.addCleanup(mit.cleanup)
        objekt = _nackt(mit.name)
        self.assertEqual(["0.5.2"], objekt._webkit_fassungen_liste())
        for art in DATEINAMEN:
            (Path(mit.name) / (DATEINAMEN[art] % "0.6.0")).write_bytes(b"x" * 2048)
        self.assertEqual(["0.6.0", "0.5.2"], objekt._webkit_fassungen_liste())

    def test_ohne_ordner_keine_fassung(self) -> None:
        self.assertEqual([], _nackt("")._webkit_fassungen_liste())
        self.assertEqual([], _nackt("X:/gibt/es/nicht")._webkit_fassungen_liste())

    def test_dateien_ohne_nummer_zaehlen_nicht_als_fassung(self) -> None:
        mit = tempfile.TemporaryDirectory()
        self.addCleanup(mit.cleanup)
        (Path(mit.name) / "webkit-autoloader-host_latest.exe").write_bytes(b"x" * 2048)
        objekt = _nackt(mit.name)
        self.assertEqual([], objekt._webkit_fassungen_liste())
        # ... aber ohne Wahl wird die Datei weiter gefunden, wie vor der Auswahl.
        self.assertTrue(objekt._webkit_datei("exe").endswith("host_latest.exe"))

    def test_die_datei_einer_fassung_ist_genau_diese(self) -> None:
        mit = _ordner_mit({"0.5.0": ["exe", "py", "elf"], "0.4.0": ["exe", "py", "elf"]})
        self.addCleanup(mit.cleanup)
        objekt = _nackt(mit.name)
        for art in DATEINAMEN:
            with self.subTest(art=art):
                self.assertEqual(DATEINAMEN[art] % "0.4.0",
                                 Path(objekt._webkit_datei(art, "0.4.0")).name)
                self.assertEqual(DATEINAMEN[art] % "0.5.0",
                                 Path(objekt._webkit_datei(art)).name, "ohne Wahl die neueste")
        self.assertEqual(DATEINAMEN["exe"] % "0.4.0",
                         Path(objekt._webkit_host_pfad("exe", "0.4.0")).name)
        self.assertEqual(DATEINAMEN["py"] % "0.4.0",
                         Path(objekt._webkit_host_pfad("py", "0.4.0")).name)
        self.assertEqual(DATEINAMEN["elf"] % "0.4.0",
                         Path(objekt._webkit_installer_pfad("0.4.0")).name)

    def test_eine_unbekannte_fassung_liefert_nichts_statt_der_neuesten(self) -> None:
        mit = _ordner_mit({"0.5.0": ["exe", "py", "elf"]})
        self.addCleanup(mit.cleanup)
        objekt = _nackt(mit.name)
        for fassung in ("0.9.9", "0.5"):
            with self.subTest(fassung=fassung):
                self.assertEqual("", objekt._webkit_datei("elf", fassung))

    def test_eine_fassung_ist_nur_ziffern_und_punkte(self) -> None:
        """Die Nummer kommt aus der Einstellungsdatei und geht in ein Dateimuster."""
        mit = _ordner_mit({"0.5.0": ["exe", "py", "elf"]})
        self.addCleanup(mit.cleanup)
        objekt = _nackt(mit.name)
        for boese in ("*", "0.*", "../x", "0.5.0/../../x", "0.5.0 ", "v0.5.0", "[0-9]"):
            with self.subTest(fassung=boese):
                self.assertEqual("", objekt._webkit_datei("exe", boese))

    def test_die_gewaehlte_fassung_ist_die_gemerkte_sonst_die_neueste(self) -> None:
        mit = _ordner_mit({"0.5.2": ["exe", "py", "elf"], "0.5.0": ["exe", "py", "elf"]})
        self.addCleanup(mit.cleanup)
        objekt = _nackt(mit.name)
        self.assertEqual("0.5.2", objekt._webkit_gewaehlt(), "ohne Merker die neueste")
        objekt._load_setting = lambda _s, vorgabe="": "0.5.0"
        self.assertEqual("0.5.0", objekt._webkit_gewaehlt())
        objekt._load_setting = lambda _s, vorgabe="": "0.1.0"
        self.assertEqual("0.5.2", objekt._webkit_gewaehlt(), "eine verschwundene Fassung gilt nicht")

    def test_unvollstaendige_fassung_nennt_was_fehlt(self) -> None:
        mit = _ordner_mit({"0.5.0": ["exe", "elf"], "0.4.0": ["exe", "py", "elf"]})
        self.addCleanup(mit.cleanup)
        objekt = _nackt(mit.name)
        info = objekt._webkit_fassung_info("0.5.0")
        self.assertIn(STRINGS["webkit.art_py"]["de"], info)
        self.assertNotIn(STRINGS["webkit.art_exe"]["de"], info)
        self.assertEqual(STRINGS["webkit.fassung_vollstaendig"]["de"],
                         objekt._webkit_fassung_info("0.4.0"))
        self.assertEqual(STRINGS["webkit.keine_fassung"]["de"], objekt._webkit_fassung_info(""))

    def test_die_fassung_aus_dem_dateinamen(self) -> None:
        lesen = KLASSE._webkit_fassung_aus_name
        self.assertEqual("0.5.2", lesen("webkit-autoloader-installer_v0.5.2.elf"))
        self.assertEqual("0.10.0", lesen("webkit-autoloader-host_v0.10.0.exe"),
                         "zweistellige Teile muessen ganz bleiben")
        self.assertEqual("", lesen("webkit-autoloader-installer.elf"))


class MitgelieferteFassungenTests(unittest.TestCase):
    """Was wirklich im Ordner liegt: die vier Fassungen, vollstaendig und echt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.objekt = KLASSE.__new__(KLASSE)

    def test_alle_vier_fassungen_stehen_in_der_liste(self) -> None:
        liste = self.objekt._webkit_fassungen_liste()
        for fassung in FASSUNGEN:
            self.assertIn(fassung, liste, "Fassung %s fehlt im Ordner" % fassung)
        self.assertEqual(FASSUNGEN[0], liste[0], "die neueste steht vorn")

    def test_jede_fassung_hat_alle_drei_dateien(self) -> None:
        for fassung in FASSUNGEN:
            for art, pfad in self.objekt._webkit_fassung_dateien(fassung).items():
                with self.subTest(fassung=fassung, art=art):
                    self.assertTrue(pfad, "%s v%s fehlt" % (art, fassung))
                    self.assertGreater(Path(pfad).stat().st_size, 1024 * 1024 if art != "py" else 100_000)

    def test_der_installer_nennt_innen_seine_fassung(self) -> None:
        """Der Name allein beweist nichts: Gelesen wird der Banner der Datei.

        Am 28.09.2026 trug eine Datei den Namen "v0.4.0" und meldete sich innen
        als 0.4.3-dev. Fuer die mitgelieferten darf das nicht passieren - die
        Auswahl zeigte sonst eine Fassung, die es nicht ist.
        """
        for fassung in FASSUNGEN:
            with self.subTest(fassung=fassung):
                roh = Path(self.objekt._webkit_datei("elf", fassung)).read_bytes()
                banner = re.findall(rb"WebKit Autoloader v(\d+(?:\.\d+)+[0-9A-Za-z.\-]*)", roh)
                self.assertEqual({fassung}, {b.decode() for b in banner})

    def test_host_skript_und_programm_tragen_dieselbe_fassung(self) -> None:
        for fassung in FASSUNGEN:
            muster = rb"(?<![\d.])" + re.escape(fassung.encode()) + rb"(?![\d])"
            for art in ("py", "exe"):
                with self.subTest(fassung=fassung, art=art):
                    roh = Path(self.objekt._webkit_datei(art, fassung)).read_bytes()
                    self.assertTrue(re.search(muster, roh),
                                    "Die Datei nennt ihre Fassung %s nicht" % fassung)


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeitenTests(unittest.TestCase):
    """Die Seite am wirklichen Programm - eine App fuer alle Tests, je Test aufgeraeumt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        gc.collect()
        self.gespeichert: list = []
        self.einstellungen: dict = {}
        offen = mock.Mock(side_effect=AssertionError("Port abgefragt"))
        senden = mock.Mock(side_effect=AssertionError("Payload geschickt"))
        browser = mock.Mock(side_effect=AssertionError("Browser geoeffnet"))
        prozess = mock.Mock(side_effect=AssertionError("Prozess gestartet"))
        for stub in (offen, senden, browser, prozess):
            self.addCleanup(stub.assert_not_called)
        for ziel, name, ersatz in (
                (self.app, "_ps5_ip", lambda: ""),
                (self.app, "_save_setting", self._merken),
                (self.app, "_load_setting", lambda k, v="": self.einstellungen.get(k, v)),
                (self.app, "_set_status_fluechtig", lambda *a, **k: None),
                (self.app, "_send_payload_to_ps5", senden),
                (self.app, "_ps5_port_open", offen),
                (APP.webbrowser, "open", browser),
                (APP.subprocess, "Popen", prozess)):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.app._ansicht_setzen("konsole")
        self.app._konsole_seite_setzen("webkit")
        _WURZEL.update_idletasks()
        # Jeder Test beginnt mit der Ausgangswahl (neueste Fassung): Die App ist
        # fuer alle Tests dieselbe, eine Wahl aus dem vorigen Test darf nicht bleiben.
        self.app._webkit_fassung_var.set("")
        self.app._webkit_fassungen_anzeigen()
        self.app._webkit_status_var.set(self.app._t("webkit.status_idle"))
        self.app._webkit_status_ruhe = True
        self.addCleanup(self._zurueck)
        widgets = list(_alle(self.app._webkit_seite))
        self.feld = next(w for w in widgets if isinstance(w, tk.Entry))
        self.knopf = {_text(w): w for w in widgets
                      if isinstance(w, (ttk.Button, APP.RoundedButton))}

    def _merken(self, schluessel, wert) -> None:
        self.gespeichert.append((schluessel, wert))
        self.einstellungen[schluessel] = wert

    def _zurueck(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln")
        _WURZEL.update()
        gc.collect()

    def _knopf_der_leiste(self, schluessel: str):
        return next(k for k, s in self.app._konsole_knoepfe if s == schluessel)

    def _waehlen(self, nummer: str) -> None:
        """Wie ein Klick in die Auswahl."""
        anzeige = {n: t for t, n in self.app._webkit_anzeige.items()}
        self.app._webkit_fassung_var.set(anzeige[nummer])
        self.app._webkit_fassung_box.event_generate("<<ComboboxSelected>>")
        _WURZEL.update()

    # -- Eine Seite statt eines Fensters ------------------------------------

    def test_knopf_2_zeigt_die_seite_statt_eines_fensters(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        vorher = {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}
        with mock.patch.object(self.app, "_werkzeugfenster_umschalten") as fenster:
            self.app._konsole_knopf_gedrueckt("webkit", "konsole.btn_webkit")
            _WURZEL.update()
        fenster.assert_not_called()
        neu = {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)} - vorher
        self.assertEqual(set(), neu, "Knopf 2 oeffnet wieder ein eigenes Fenster.")
        self.assertTrue(_gezeigt(self.app._webkit_seite))
        lage = self.app._webkit_seite.grid_info()
        self.assertEqual((1, 1), (int(lage["row"]), int(lage["column"])))
        self.assertFalse(_gezeigt(getattr(self.app, "_konsole_tafel", None)))
        c = self.app._COLORS
        self.assertEqual(c["fg_accent"], self._knopf_der_leiste("konsole.btn_webkit")._bg)
        self.assertEqual(c["seitenknopf_bg"], self._knopf_der_leiste("konsole.btn_dienste")._bg)

    def test_der_knopf_heisst_webkit_autoloader_und_steht_an_zweiter_stelle(self) -> None:
        self.assertEqual(("konsole.btn_webkit", "webkit"), KLASSE._KONSOLE_KNOEPFE[1])
        self.assertEqual("2. WebKit Autoloader", self._knopf_der_leiste("konsole.btn_webkit")._text)

    def test_zweiter_druck_bleibt_auf_der_seite(self) -> None:
        """Seit 07.10.2026: kein Zurueckspringen auf den zuvor gewaehlten Knopf."""
        self.app._konsole_knopf_gedrueckt("webkit", "konsole.btn_webkit")
        _WURZEL.update()
        self.assertEqual("webkit", self.app._konsole_seite)
        self.assertTrue(_gezeigt(self.app._webkit_seite))
        self.assertFalse(_gezeigt(self.app._konsole_tafel))

    def test_zurueck_knopf_der_seite(self) -> None:
        self.knopf[self.app._t("konsole.btn_uebersicht")].invoke()
        _WURZEL.update()
        self.assertEqual("uebersicht", self.app._konsole_seite)

    def test_das_zeigen_startet_keinen_faden_und_nichts_im_netz(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        import threading
        vorher = {t.name for t in threading.enumerate()}
        self.app._konsole_knopf_gedrueckt("webkit", "konsole.btn_webkit")
        _WURZEL.update()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertEqual(set(), {n for n in neu if n.startswith(("webkit-", "konsole-"))})

    def test_die_spielstaende_seite_gibt_es_nicht_mehr(self) -> None:
        self.assertNotIn("spielstaende", KLASSE._KONSOLE_SEITENBAU)
        self.assertNotIn("spielstaende", KLASSE._KONSOLE_SEITEN)
        self.assertFalse(hasattr(self.app, "_spielstaende_seite"))
        self.assertIsNotNone(kd.dienst("garlic"), "Garlic bleibt ueber Konsole & Payloads erreichbar")

    # -- Die Auswahl ---------------------------------------------------------

    def test_die_auswahl_nennt_alle_fassungen_die_neueste_vorn(self) -> None:
        werte = list(self.app._webkit_fassung_box.cget("values"))
        self.assertEqual(["v%s" % n for n in FASSUNGEN],
                         [w.replace(" (neueste)", "") for w in werte])
        self.assertEqual("v0.6.0 (neueste)", werte[0])
        self.assertEqual("v0.6.0 (neueste)", self.app._webkit_fassung_var.get())

    def test_waehlen_merkt_die_fassung_und_beschreibt_sie(self) -> None:
        self._waehlen("0.5.1")
        self.assertEqual([("webkit_fassung", "0.5.1")], self.gespeichert)
        self.assertEqual("0.5.1", self.app._webkit_gewaehlt())
        self.assertEqual(STRINGS["webkit.fassung_vollstaendig"]["de"],
                         self.app._webkit_info_var.get())

    def test_die_gemerkte_fassung_gilt_beim_naechsten_aufbau(self) -> None:
        self.einstellungen["webkit_fassung"] = "0.4.0"
        self.app._webkit_fassung_var.set("")
        self.app._webkit_fassungen_anzeigen()
        self.assertEqual("v0.4.0", self.app._webkit_fassung_var.get())

    def test_die_wege_nehmen_die_gewaehlte_fassung(self) -> None:
        self._waehlen("0.5.1")
        self.app._konsole_ip_var().set("192.168.1.50")
        with mock.patch.object(self.app, "_webkit_host_starten") as host, \
                mock.patch.object(self.app, "_webkit_installer_senden") as installer:
            self.knopf[self.app._t("webkit.host_exe")].invoke()
            self.knopf[self.app._t("webkit.host_py")].invoke()
            self.knopf[self.app._t("webkit.installer")].invoke()
        self.assertEqual([mock.call("exe", fassung="0.5.1"), mock.call("py", fassung="0.5.1")],
                         host.call_args_list)
        installer.assert_called_once_with(fassung="0.5.1")
        self.assertIn(("ps5_ip", "192.168.1.50"), self.gespeichert,
                      "Die Adresse im Feld der Seite gilt und wird gemerkt.")

    def test_ohne_brauchbare_adresse_wird_nichts_gesendet(self) -> None:
        self.app._konsole_ip_var().set("")
        with mock.patch.object(self.app, "_webkit_installer_senden") as installer, \
                mock.patch.object(APP, "messagebox") as box:
            self.knopf[self.app._t("webkit.installer")].invoke()
        installer.assert_not_called()
        box.showwarning.assert_called_once()
        self.assertEqual(self.app._t("dienste.need_ip"), box.showwarning.call_args[0][1])

    def test_der_host_startet_die_datei_der_gewaehlten_fassung(self) -> None:
        befehle: list = []

        class _Prozess:
            def __init__(self, befehl, **_kw) -> None:
                befehle.append(list(befehl))

            def wait(self, timeout=None):
                raise APP.subprocess.TimeoutExpired("x", timeout)

        with mock.patch.object(APP.subprocess, "Popen", _Prozess), \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: True), \
                mock.patch.object(APP.messagebox, "showerror", lambda *a, **k: None), \
                mock.patch.object(self.app, "_append_to_log", lambda _t: None):
            self.app._webkit_host_starten("py", fassung="0.4.0")
        self.assertEqual(1, len(befehle))
        self.assertTrue(befehle[0][-1].endswith("webkit-autoloader-host_v0.4.0.py"), befehle[0])

    def test_der_installer_geht_in_der_gewaehlten_fassung_raus(self) -> None:
        gesendet: list = []
        with mock.patch.object(self.app, "_ps5_ip", lambda: "192.168.1.50"), \
                mock.patch.object(self.app, "_ps5_port_open", lambda _ip, _port, timeout=1.5: True), \
                mock.patch.object(self.app, "_send_payload_to_ps5",
                                  lambda ip, pfad, **_k: gesendet.append((ip, pfad)) or (True, "1 B")), \
                mock.patch.object(APP.messagebox, "askyesno", lambda *a, **k: True), \
                mock.patch.object(APP.messagebox, "showinfo", lambda *a, **k: None), \
                mock.patch.object(APP.messagebox, "showerror", lambda *a, **k: None), \
                mock.patch.object(self.app, "_append_to_log", lambda _t: None):
            self.app._webkit_installer_senden(fassung="0.4.0")
            _schleife(8.0, bis=lambda: bool(gesendet))
        self.assertTrue(gesendet, "Der Installer wurde nicht geschickt.")
        self.assertTrue(gesendet[0][1].endswith("webkit-autoloader-installer_v0.4.0.elf"), gesendet)

    def test_ohne_wahl_nehmen_die_wege_weiter_die_neueste(self) -> None:
        """Wie vor der Auswahl: ohne ``fassung`` die hoechste Nummer."""
        self.assertTrue(self.app._webkit_installer_pfad().endswith("installer_v0.6.0.elf"))
        self.assertTrue(self.app._webkit_host_pfad("exe").endswith("host_v0.6.0.exe"))

    # -- Protokoll, Status, Sprache ------------------------------------------

    def test_das_protokoll_der_seite_zeigt_die_zeilen(self) -> None:
        zeilen: list = []
        with mock.patch.object(self.app, "_append_to_log", zeilen.append):
            self.app._webkit_zeile("[OK] Probe\n")
            self.assertTrue(_bis(lambda: "[OK] Probe" in self.app._webkit_protokoll.get("1.0", "end")))
        self.assertEqual(["[OK] Probe\n"], zeilen, "weiter auch ins Hauptprotokoll")

    def test_der_status_steht_auf_der_seite_und_kehrt_zurueck(self) -> None:
        self.app._webkit_status("Konsole wird gesucht…")
        self.assertEqual("Konsole wird gesucht…", self.app._webkit_status_var.get())
        self.app._webkit_status_zuruecksetzen("Konsole wird gesucht…")
        self.assertEqual(STRINGS["webkit.status_idle"]["de"], self.app._webkit_status_var.get())
        self.app._webkit_status("neu")
        self.app._webkit_status_zuruecksetzen("alt")
        self.assertEqual("neu", self.app._webkit_status_var.get(), "Neueres bleibt stehen")

    def test_die_seite_folgt_dem_sprachwechsel(self) -> None:
        self.app._toggle_language()
        self.addCleanup(self.app._toggle_language)
        _WURZEL.update()
        werte = list(self.app._webkit_fassung_box.cget("values"))
        self.assertEqual("v0.6.0 (latest)", werte[0])
        self.assertEqual("v0.6.0 (latest)", self.app._webkit_fassung_var.get())
        self.assertEqual("0.6.0", self.app._webkit_gewaehlt(), "die Wahl bleibt beim Umschalten")
        texte = {_text(w) for w in _alle(self.app._webkit_seite)}
        for schluessel in ("webkit.host_exe", "webkit.host_py", "webkit.installer",
                           "webkit.fassung_label", "webkit.title"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(STRINGS[schluessel]["en"], texte)
        self.assertEqual("Ready.", self.app._webkit_status_var.get())

    def test_das_bild_von_itsplk_sitzt_im_kopf(self) -> None:
        schilder = [w for w in _alle(self.app._webkit_seite)
                    if isinstance(w, tk.Label) and getattr(w, "_bild", None) is not None]
        self.assertEqual(1, len(schilder), "Bild liegt bei, also steht es da")


class QuelltextTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")

    def test_das_fenster_und_sein_titelleistenknopf_sind_weg(self) -> None:
        for name in ("_show_webkit_autoloader", "_btn_webkit_title", "titlebar.webkit",
                     "_webkit_fassungszeile"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.quelle)

    def test_nichts_von_den_spielstaenden_ist_geblieben(self) -> None:
        for name in ("_spielstaende", "spielstaende.", "konsole.btn_spielstaende",
                     "_konsole_ftp_geruest", "RunderBalken"):
            with self.subTest(name=name):
                self.assertNotIn(name, self.quelle)

    def test_der_dank_steht_auf_der_seite(self) -> None:
        self.assertIn('self._t("webkit.credit")', self.quelle)

    def test_die_texte_sind_in_beiden_sprachen_und_haben_dieselben_platzhalter(self) -> None:
        erwartet = {
            "webkit.fassung_neueste": {"version"},
            "webkit.fassung_unvollstaendig": {"fehlt"},
            "webkit.log_gesendet": {"datei", "ip", "groesse"},
            "webkit.log_usb": {"datei", "usb"},
        }
        for schluessel, platzhalter in erwartet.items():
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    text = STRINGS[schluessel][sprache]
                    self.assertEqual(platzhalter, set(re.findall(r"\{(\w+)\}", text)))
        for schluessel in ("konsole.btn_webkit", "webkit.fassung_label", "webkit.fassung_vollstaendig",
                           "webkit.keine_fassung", "webkit.art_exe", "webkit.art_py",
                           "webkit.art_elf", "webkit.status_idle"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel][sprache])

    def test_die_alten_texte_sind_aus_der_tabelle(self) -> None:
        for schluessel in ("titlebar.webkit", "webkit.close", "webkit.version",
                           "webkit.version_mix", "konsole.btn_spielstaende"):
            self.assertNotIn(schluessel, STRINGS)
        self.assertEqual([], [k for k in STRINGS if k.startswith("spielstaende.")])


if __name__ == "__main__":
    unittest.main()
