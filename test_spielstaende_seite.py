# -*- coding: utf-8 -*-
""""2. Spielstaende" als Seite rechts in der Ansicht KONSOLE (seit 26.09.2026).

Nutzer: "ja, hol die Spielstaende auch als Seite nach rechts". Bis dahin ein
eigenes Fenster; jetzt wie "Konsole & Payloads" und die Bibliothek eine Seite
in Zelle (1, 1), die einmal gebaut wird und stehen bleibt. Das Zeigen schickt
nichts ins Netz - geprueft, gestartet und geoeffnet wird auf Knopfdruck. Das
Adressfeld teilt sich die Seite mit "Konsole & Payloads", und Garlic startet
auf demselben schnellen Weg (``_konsole_dienst_starten``).

Ins Netz geht kein Test: Portabfrage, Senden und Browser sind vorab durch
werfende Attrappen ersetzt, die die Aufraeumrunde von aussen prueft.
"""
from __future__ import annotations

import ast
import gc
import os
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("spielstaende_seite")

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


def _gezeigt(widget) -> bool:
    try:
        return bool(widget is not None and widget.winfo_manager() == "grid"
                    and widget.grid_info())
    except Exception:  # noqa: BLE001
        return False


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeitenTests(unittest.TestCase):
    """Die Seite am wirklichen Programm - eine App fuer alle Tests, je Test aufgeraeumt."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        # Vorsorge wie in test_konsole_suche (Sammler im Hauptfaden).
        gc.collect()
        self.gespeichert: list = []
        offen = mock.Mock(side_effect=AssertionError("Port abgefragt"))
        senden = mock.Mock(side_effect=AssertionError("Payload geschickt"))
        browser = mock.Mock(side_effect=AssertionError("Browser geoeffnet"))
        for stub in (offen, senden, browser):
            self.addCleanup(stub.assert_not_called)
        for ziel, name, ersatz in (
                (self.app, "_ps5_ip", lambda: ""),
                (self.app, "_save_setting", lambda k, v: self.gespeichert.append((k, v))),
                (self.app, "_send_payload_to_ps5", senden),
                (kd, "port_offen", offen),
                (APP.webbrowser, "open", browser)):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.app._ansicht_setzen("konsole", speichern=False)
        self.app._konsole_seite_setzen("spielstaende")
        _WURZEL.update_idletasks()
        self.assertTrue(_bis(lambda: not self.app._spielstaende_laeuft["aktiv"]))
        self.app._spielstaende_puffer.clear()
        self.app._spielstaende_gezeigt = 0
        self.app._spielstaende_protokoll.delete("1.0", "end")
        self.app._spielstaende_stand.update(
            pct=0.0, groesse="", status=("spielstaende.status_idle", {}))
        self.app._spielstaende_beschriften()
        self.app._konsole_ip_var().set("")
        self.addCleanup(self._zurueck)
        widgets = list(_alle(self.app._spielstaende_seite))
        self.feld = next(w for w in widgets if isinstance(w, tk.Entry))
        self.knopf = {_text(w): w for w in widgets if isinstance(w, ttk.Button)}

    def _zurueck(self) -> None:
        _bis(lambda: not self.app._spielstaende_laeuft["aktiv"])
        self.app._konsole_seite_setzen("uebersicht")
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()
        gc.collect()

    def _fertig(self) -> bool:
        return (not self.app._spielstaende_laeuft["aktiv"]
                and str(self.knopf[self.app._t("spielstaende.btn_check")].cget("state"))
                == "normal")

    def _protokoll(self) -> str:
        return self.app._spielstaende_protokoll.get("1.0", "end")

    def _knopf_der_leiste(self, schluessel: str):
        return next(k for k, s in self.app._konsole_knoepfe if s == schluessel)

    # -- Eine Seite statt eines Fensters ------------------------------------

    def test_knopf_2_zeigt_die_seite_statt_eines_fensters(self) -> None:
        self.app._konsole_seite_setzen("uebersicht")
        vorher = {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}
        with mock.patch.object(self.app, "_werkzeugfenster_umschalten") as fenster:
            self.app._konsole_knopf_gedrueckt("spielstaende", "konsole.btn_spielstaende")
            _WURZEL.update()
        fenster.assert_not_called()
        neu = {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)} - vorher
        self.assertEqual(set(), neu, "Knopf 2 oeffnet wieder ein eigenes Fenster.")
        self.assertTrue(_gezeigt(self.app._spielstaende_seite))
        lage = self.app._spielstaende_seite.grid_info()
        self.assertEqual((1, 1), (int(lage["row"]), int(lage["column"])))
        self.assertFalse(_gezeigt(getattr(self.app, "_konsole_tafel", None)))
        c = self.app._COLORS
        self.assertEqual(c["fg_accent"], self._knopf_der_leiste("konsole.btn_spielstaende")._bg)
        self.assertEqual(c["bg_card"], self._knopf_der_leiste("konsole.btn_dienste")._bg)

    def test_zweiter_druck_fuehrt_zurueck(self) -> None:
        self.app._konsole_knopf_gedrueckt("spielstaende", "konsole.btn_spielstaende")
        _WURZEL.update()
        self.assertEqual("uebersicht", self.app._konsole_seite)
        self.assertFalse(_gezeigt(self.app._spielstaende_seite))
        self.assertTrue(_gezeigt(self.app._konsole_tafel))

    def test_zurueck_knopf_der_seite(self) -> None:
        self.knopf[self.app._t("konsole.btn_uebersicht")].invoke()
        _WURZEL.update()
        self.assertEqual("uebersicht", self.app._konsole_seite)

    def test_das_zeigen_startet_keinen_faden(self) -> None:
        """Wie beim Fenster: Oeffnen misst nichts - erst der Knopf."""
        self.app._konsole_seite_setzen("uebersicht")
        vorher = {t.name for t in threading.enumerate()}
        self.app._konsole_knopf_gedrueckt("spielstaende", "konsole.btn_spielstaende")
        _WURZEL.update()
        neu = {t.name for t in threading.enumerate()} - vorher
        self.assertEqual(set(), {n for n in neu if n.startswith("konsole-")})

    def test_die_seite_warnt_vor_dem_schreiben(self) -> None:
        texte = [_text(w) for w in _alle(self.app._spielstaende_seite)]
        for schluessel in ("spielstaende.window_title", "spielstaende.subtitle",
                           "spielstaende.usage", "spielstaende.warn_backup",
                           "spielstaende.warn_benutzer", "spielstaende.btn_check",
                           "spielstaende.btn_start", "spielstaende.btn_open",
                           "konsole.btn_uebersicht"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(self.app._t(schluessel), texte)

    def test_ein_adressfeld_fuer_beide_seiten(self) -> None:
        if getattr(self.app, "_konsole_tafel", None) is None:
            self.app._konsole_tafel_bauen()
        variable = self.app._konsole_ip_var()
        self.assertIs(variable, self.app._konsole_tafel_ip)
        tafel_feld = next(w for w in _alle(self.app._konsole_tafel)
                          if isinstance(w, tk.Entry))
        for feld in (self.feld, tafel_feld):
            with self.subTest(feld=str(feld)):
                self.assertEqual(str(variable), str(feld.cget("textvariable")))
        variable.set("10.0.0.9")
        self.assertEqual(("10.0.0.9", "10.0.0.9"), (self.feld.get(), tafel_feld.get()))

    # -- Pruefen, Starten, Oeffnen -----------------------------------------

    def _pruefen(self, antwort) -> list:
        gefragt: list = []

        def _offen(host, port, *_a, **_k):
            gefragt.append((host, port))
            if isinstance(antwort, BaseException):
                raise antwort
            return antwort

        self.feld.insert(0, "10.0.0.9")
        with mock.patch.object(kd, "port_offen", _offen):
            self.knopf[self.app._t("spielstaende.btn_check")].invoke()
            self.assertTrue(_bis(lambda: gefragt and self._fertig()))
        return gefragt

    def test_pruefen_meldet_garlic_mit_adresse(self) -> None:
        gefragt = self._pruefen(True)
        adresse = kd.web_adresse(kd.dienst("garlic"), "10.0.0.9")
        self.assertEqual([("10.0.0.9", 8082)], gefragt)
        self.assertEqual(self.app._t("spielstaende.running", adresse=adresse),
                         self.app._spielstaende_status_var.get())
        self.assertEqual(adresse, self.app._spielstaende_groesse_var.get())
        self.assertEqual(100.0, float(self.app._spielstaende_balken["value"]))
        self.assertIn(("ps5_ip", "10.0.0.9"), self.gespeichert)

    def test_pruefen_meldet_garlic_aus(self) -> None:
        self._pruefen(False)
        self.assertEqual(self.app._t("spielstaende.stopped",
                                     adresse=kd.web_adresse(kd.dienst("garlic"), "10.0.0.9")),
                         self.app._spielstaende_status_var.get())
        self.assertEqual("", self.app._spielstaende_groesse_var.get())
        self.assertEqual(0.0, float(self.app._spielstaende_balken["value"]))

    def test_ein_fehler_beim_pruefen_steht_im_protokoll(self) -> None:
        self._pruefen(OSError("kaputt"))
        self.assertEqual(self.app._t("spielstaende.status_failed"),
                         self.app._spielstaende_status_var.get())
        self.assertIn(self.app._t("log.fehler_zeile", text="kaputt"), self._protokoll())

    def test_ohne_adresse_ein_hinweis_und_kein_faden(self) -> None:
        with mock.patch.object(APP, "messagebox") as box:
            self.knopf[self.app._t("spielstaende.btn_check")].invoke()
        box.showwarning.assert_called_once()
        self.assertEqual(self.app._t("dienste.need_ip"), box.showwarning.call_args[0][1])
        self.assertFalse(self.app._spielstaende_laeuft["aktiv"])

    def test_starten_nimmt_den_weg_von_konsole_und_payloads(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        gestartet: list = []

        def _starten(schluessel, ip, melden=None):
            gestartet.append((schluessel, ip, melden))
            return True

        with mock.patch.object(self.app, "_konsole_dienst_starten", _starten), \
                mock.patch.object(self.app, "_konsole_payload_datei", lambda _m: "garlic.elf"):
            self.knopf[self.app._t("spielstaende.btn_start")].invoke()
            self.assertTrue(_bis(lambda: gestartet and self._fertig()))
        self.assertEqual([("garlic", "10.0.0.9", self.app._spielstaende_melden)], gestartet)
        self.assertEqual(self.app._t("spielstaende.running",
                                     adresse=kd.web_adresse(kd.dienst("garlic"), "10.0.0.9")),
                         self.app._spielstaende_status_var.get())

    def test_starten_liest_kurz_und_fragt_dann_ab(self) -> None:
        """Durch _konsole_dienst_starten hindurch: 3 s Lesezeit, dann den Port fragen."""
        self.feld.insert(0, "10.0.0.9")
        gesendet: list = []
        gewartet: list = []

        def _senden(ip, pfad, *a, **k):
            gesendet.append(k)
            return True, "1 KB"

        with mock.patch.object(self.app, "_send_payload_to_ps5", _senden), \
                mock.patch.object(self.app, "_konsole_payload_datei",
                                  lambda _m: str(Path(__file__))), \
                mock.patch.object(kd, "warten_bis_bereit",
                                  lambda ip, eintrag, **k: gewartet.append(eintrag) or True):
            self.knopf[self.app._t("spielstaende.btn_start")].invoke()
            self.assertTrue(_bis(lambda: gesendet and self._fertig()))
        self.assertEqual([kd.LESEZEIT], [k.get("lesezeit") for k in gesendet])
        self.assertEqual([kd.dienst("garlic")], gewartet)
        name = self.app._t(kd.dienst("garlic").name_schluessel)
        text = self._protokoll()
        self.assertIn(self.app._t("dienste.log_sende", name=name,
                                  datei=os.path.basename(__file__)), text)
        self.assertIn(self.app._t("dienste.log_gestartet", name=name, port=8082), text)

    def test_ohne_garlic_datei_ein_hinweis(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        with mock.patch.object(self.app, "_konsole_payload_datei", lambda _m: ""), \
                mock.patch.object(APP, "messagebox") as box:
            self.knopf[self.app._t("spielstaende.btn_start")].invoke()
        box.showwarning.assert_called_once()
        self.assertEqual(self.app._t("spielstaende.no_file"), box.showwarning.call_args[0][1])
        self.assertFalse(self.app._spielstaende_laeuft["aktiv"])

    def test_oeffnen_zeigt_garlic_im_browser(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        adresse = kd.web_adresse(kd.dienst("garlic"), "10.0.0.9")
        with mock.patch.object(APP.webbrowser, "open") as oeffnen:
            self.knopf[self.app._t("spielstaende.btn_open")].invoke()
        oeffnen.assert_called_once_with(adresse)
        self.assertIn(self.app._t("spielstaende.opened", adresse=adresse), self._protokoll())

    # -- Sprachwechsel -------------------------------------------------------

    def test_die_seite_folgt_dem_sprachwechsel(self) -> None:
        """Die Seite bleibt stehen - also muessen ihre Texte mitwandern."""
        adresse = kd.web_adresse(kd.dienst("garlic"), "10.0.0.9")
        self.app._spielstaende_stand.update(
            status=("spielstaende.running", {"adresse": adresse}))

        def _en(schluessel, **werte):
            return STRINGS[schluessel]["en"].format(**werte)

        self.app._toggle_language()
        self.addCleanup(self.app._toggle_language)
        self.assertEqual("en", self.app._current_language)
        self.assertEqual(_en("spielstaende.running", adresse=adresse),
                         self.app._spielstaende_status_var.get())
        texte = [_text(w) for w in _alle(self.app._spielstaende_seite)]
        for schluessel in ("spielstaende.window_title", "spielstaende.warn_backup",
                           "spielstaende.btn_start", "dienste.ip_label"):
            with self.subTest(schluessel=schluessel):
                self.assertIn(_en(schluessel), texte)


def _baum():
    return ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
                     .read_text(encoding="utf-8"))


def _methode(baum, name: str):
    klasse = next(k for k in baum.body
                  if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    return next(k for k in klasse.body if isinstance(k, ast.FunctionDef) and k.name == name)


class QuelltextTests(unittest.TestCase):

    def test_kein_fenster_mehr(self) -> None:
        klasse = APP.PS5ConverterGUI
        self.assertFalse(hasattr(klasse, "_show_konsole_spielstaende"))
        self.assertNotIn("spielstaende", klasse._KONSOLE_FENSTER)
        self.assertEqual("_konsole_spielstaende_zeigen", klasse._KONSOLE_SEITEN["spielstaende"])
        self.assertEqual(("_spielstaende_seite", "_spielstaende_seite_bauen",
                          "konsole.btn_spielstaende"),
                         klasse._KONSOLE_SEITENBAU["spielstaende"])

    def test_die_faeden_uebersetzen_nicht(self) -> None:
        """Durchsicht H2-13 - wie auf "Konsole & Payloads"."""
        baum = _baum()
        pruefen = [(name, next(k for k in ast.walk(_methode(baum, name))
                               if isinstance(k, ast.FunctionDef) and k.name == "_arbeit"))
                   for name in ("_spielstaende_pruefen", "_spielstaende_starten")]
        pruefen.append(("_spielstaende_ergebnis", _methode(baum, "_spielstaende_ergebnis")))
        for name, knoten in pruefen:
            with self.subTest(funktion=name):
                self.assertEqual([], [k.lineno for k in ast.walk(knoten)
                                      if isinstance(k, ast.Call)
                                      and getattr(k.func, "attr", "") in ("_t", "_modul_texte")])

    def test_der_sprachwechsel_beschriftet_die_seite(self) -> None:
        text = ast.unparse(_methode(_baum(), "_apply_language"))
        self.assertIn("self._spielstaende_beschriften()", text)


class TexteTests(unittest.TestCase):

    def test_der_alte_starttext_ist_weg(self) -> None:
        """Gestartet wird ueber _konsole_dienst_starten - der meldet mit dienste.log_sende."""
        self.assertNotIn("spielstaende.log_start", STRINGS)

    def test_das_handbuch_beschreibt_die_seite(self) -> None:
        handbuch = " ".join((PROJEKT / "BENUTZERHANDBUCH.html")
                            .read_text(encoding="utf-8").split())
        anfang = handbuch.index("<h4>Spielstände</h4>")
        abschnitt = handbuch[anfang:handbuch.index("</p>", anfang)]
        for stelle in ("Die Seite <em>2.&nbsp;Spielstände</em>", "auf Knopfdruck",
                       "Das Adressfeld teilt sie sich", "3&nbsp;Sekunden"):
            with self.subTest(stelle=stelle):
                self.assertIn(stelle, abschnitt)
        self.assertIn("keines der drei Werkzeuge öffnet ein eigenes Fenster", handbuch)


if __name__ == "__main__":
    unittest.main()
