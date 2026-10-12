# -*- coding: utf-8 -*-
"""Favoriten auf der Seite „Konsole & Payloads“ - welche Payloads das Programm von selbst an die PS5 sendet.

Nutzerwunsch vom 10.10.2026: „Am besten wäre noch eine Auswahl (Favoriten), wo man wählen kann, was für ein Payload
an die PS5 automatisch gesendet werden (inkl. öffnen von 9021, falls noch nicht geöffnet)“ - und, auf Nachfrage:
„Im Konsole & Payload Bereich meine ich.“

Was gilt:

* Gewählt wird in der **Dienstetabelle** selbst: Die erste Spalte trägt einen Stern (★ Favorit, ☆ möglich); ein Klick
  darauf oder die Leertaste wechselt. Möglich ist, was das Programm selbst senden kann (``payload_muster``, kein Plugin);
  der ELF-Loader braucht keinen Stern - er wird **immer zuerst geöffnet** (Port 9021, bei Bedarf über den Payload
  Manager).
* Ohne eigene Wahl gelten die Favoriten der bisherigen Grundausstattung (ftpsrv, klogsrv) - am Verhalten ändert sich
  für niemanden etwas, der nichts wählt.
* Gesendet wird, was nicht läuft, in der Reihenfolge der Tabelle; ein hängender Dienst wird nicht noch einmal
  geschickt (hilft laut Messung vom 17.08.2026 nicht).
* **Automatisch** beim Programmstart (Haken, Vorgabe an - wie bisher die Grundausstattung) und auf **Favoriten
  senden**. Eine Suche, die der Nutzer selbst anstößt, sendet nichts.

Ins Netz geht kein Test: Abfrage, Loader und Senden sind durch eine Nachbildung der Konsole ersetzt.
"""
from __future__ import annotations

import ast
import gc
import re
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
if str(PROJEKT) not in sys.path:
    sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("konsole_favoriten")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_dienste as kd       # noqa: E402
from ps5_validator.utils import remoteplay                  # noqa: E402
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

#: Dienste, die kein Favorit sein koennen: der Loader (kommt immer zuerst), seine zweite Zeile, ShadowMount+
#: (laeuft ueblicherweise aus dem Autoload - bewusst ohne Senden) und das Plugin DPI v2.
NICHT_MOEGLICH = {"elfldr9021", "elfldr9020", "shadowmount", "dpiv2"}


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


class _Konsole:
    """Eine PS5 im Speicher: Welche Dienste laufen, was gesendet wurde, in welcher Reihenfolge."""

    def __init__(self, laufend=("elfldr9021",), stumm=(), loader_oeffnet: bool = True) -> None:
        self.laufend = set(laufend)
        self.stumm = set(stumm)
        self.loader_oeffnet = loader_oeffnet
        self.aufrufe: list[str] = []

    def pruefen(self, host, *_a, **_k) -> "kd.Uebersicht":
        return kd.Uebersicht(host, [kd.Stand(d, d.schluessel in self.laufend, d.schluessel in self.stumm)
                                    for d in kd.KATALOG])

    def sicherstellen(self, ip, uebersicht, texte):
        """Ersetzt ``_konsole_elfldr_sicherstellen``: oeffnet Port 9021 - oder auch nicht."""
        self.aufrufe.append("loader")
        if self.loader_oeffnet:
            self.laufend.add("elfldr9021")
        return self.pruefen(ip)

    def starten(self, schluessel, ip, melden=None, muster="") -> bool:
        """Ersetzt ``_konsole_dienst_starten``."""
        self.aufrufe.append(schluessel)
        self.laufend.add(schluessel)
        return True


class LogikTests(unittest.TestCase):
    """Der Katalog: wer Favorit sein kann, was ohne Wahl gilt, wie die Einstellung gelesen wird."""

    def test_wer_favorit_sein_kann(self) -> None:
        for d in kd.KATALOG:
            with self.subTest(dienst=d.schluessel):
                soll = d.schluessel not in NICHT_MOEGLICH
                self.assertEqual(soll, kd.favorit_moeglich(d), d.schluessel)
        self.assertFalse(kd.favorit_moeglich(None))

    def test_moeglich_ist_nur_was_das_programm_selbst_senden_kann(self) -> None:
        # Der Grund steht im Katalog: Ohne payload_muster (ShadowMount+, zweiter Loader-Port, DPI v2) schickt das
        # Programm nichts, ein Plugin schickt es nie ueber den ELF-Loader.
        for d in kd.KATALOG:
            if kd.favorit_moeglich(d):
                self.assertTrue(d.payload_muster and not d.ist_plugin and d.gruppe != "elfldr", d.schluessel)

    def test_ohne_wahl_gilt_die_bisherige_grundausstattung(self) -> None:
        self.assertEqual(("ftpsrv", "klogsrv"), kd.FAVORITEN_STANDARD)
        self.assertEqual(["ftpsrv", "klogsrv"], [s for s in kd.GRUNDAUSSTATTUNG if s in kd.FAVORITEN_STANDARD])
        self.assertEqual("elfldr9021", kd.GRUNDAUSSTATTUNG[0], "Der Loader steht vorn - und ist kein Favorit")
        self.assertEqual(list(kd.FAVORITEN_STANDARD), kd.favoriten_lesen(None))

    def test_favoriten_lesen(self) -> None:
        schluessel = [d.schluessel for d in kd.KATALOG if kd.favorit_moeglich(d)]
        for roh in ("abc", 5, 1.5, {"ftpsrv": 1}, True, object()):
            self.assertEqual(list(kd.FAVORITEN_STANDARD), kd.favoriten_lesen(roh), repr(roh))
        self.assertEqual([], kd.favoriten_lesen([]), "Eine leere Liste ist eine bewusste Wahl")
        self.assertEqual([], kd.favoriten_lesen(()))
        # Reihenfolge des Katalogs, nicht der Wahl; doppelte fallen weg
        self.assertEqual(["ftpsrv", "klogsrv", "upload"], kd.favoriten_lesen(["upload", "klogsrv", "ftpsrv", "upload"]))
        # Unbekanntes und Unzulaessiges faellt weg, ohne die uebrigen zu beruehren
        self.assertEqual(["upload"], kd.favoriten_lesen(["gibtesnicht", "elfldr9021", "shadowmount", "dpiv2", 7,
                                                          None, "upload"]))
        self.assertEqual(schluessel, kd.favoriten_lesen(schluessel))
        self.assertEqual(["ftpsrv"], kd.favoriten_lesen(("ftpsrv",)))

    def test_jeder_favorit_hat_eine_datei_im_ordner(self) -> None:
        # Sonst wuerde "Favoriten senden" an einem Favoriten scheitern, den es gar nicht gibt.
        from ps5_validator.utils import werkzeug_updates as wu
        ordner = PROJEKT / "helloworld"
        for d in kd.KATALOG:
            if kd.favorit_moeglich(d):
                treffer = [n.name for n in ordner.glob(d.payload_muster)]
                self.assertTrue(treffer, "%s: keine Datei zu %s" % (d.schluessel, d.payload_muster))
        self.assertIsNotNone(wu.werkzeug("elfldr"))


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeitenTests(unittest.TestCase):
    """Die Seite „Konsole & Payloads“ mit ihren Sternen, dem Haken und dem Knopf."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"
        cls.app._ansicht_setzen("konsole")
        cls.app._konsole_seite_setzen("uebersicht")
        _WURZEL.update_idletasks()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app._konsole_seite_setzen("uebersicht")
        cls.app._ansicht_setzen("umwandeln")

    def _einstellungen_zuruecksetzen(self) -> None:
        # null heisst "nie gewaehlt": favoriten_lesen(None) liefert wieder den Standard.
        self.app._save_setting("konsole_favoriten", None)
        self.app._save_setting("konsole_favoriten_auto", True)

    def setUp(self) -> None:
        gc.collect()
        self._einstellungen_zuruecksetzen()
        self.addCleanup(self._einstellungen_zuruecksetzen)
        app = self.app
        self.hauptprotokoll: list = []
        # Ins Netz geht nichts: Eine werfende Attrappe haelt es an; ob sie kam, prueft die Aufraeumrunde.
        senden = mock.Mock(side_effect=AssertionError("Payload geschickt"))
        self.addCleanup(senden.assert_not_called)
        for ziel, name, ersatz in (
                (app, "_ps5_ip", lambda: ""),
                (app, "_append_to_log", lambda text: self.hauptprotokoll.append(text)),
                (app, "_send_payload_to_ps5", senden),
                (remoteplay, "suchen", mock.Mock(return_value=[]))):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.konsole = _Konsole()
        for ziel, name, ersatz in ((kd, "pruefen", self.konsole.pruefen),
                                   (app, "_konsole_elfldr_sicherstellen", self.konsole.sicherstellen),
                                   (app, "_konsole_dienst_starten", self.konsole.starten)):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        app._ansicht_setzen("konsole")
        app._konsole_seite_setzen("uebersicht")
        _WURZEL.update_idletasks()
        self.assertTrue(_bis(lambda: not app._konsole_tafel_beschaeftigt()))
        app._konsole_tafel_stand = None
        app._konsole_tafel_puffer.clear()
        app._konsole_tafel_gezeigt = 0
        app._konsole_tafel_protokoll.delete("1.0", "end")
        app._konsole_tafel_ip.set("")
        app._konsole_tafel_tabelle.selection_set(())
        app._konsole_start_melden = False
        app._konsole_tafel_beschriften()
        self.addCleanup(self._zurueck)
        self.tabelle = app._konsole_tafel_tabelle
        self.knopf = {_text(w): w for w in _alle(app._konsole_tafel)
                      if isinstance(w, (ttk.Button, APP.RoundedButton))}

    def _zurueck(self) -> None:
        _bis(lambda: not self.app._konsole_tafel_beschaeftigt())
        self.app._ansicht_setzen("umwandeln")
        _WURZEL.update()
        gc.collect()

    def _protokoll(self) -> str:
        self.app._konsole_tafel_protokoll_nachtragen()
        return self.app._konsole_tafel_protokoll.get("1.0", "end")

    def _stern(self, schluessel: str) -> str:
        return str(self.tabelle.set(schluessel, "fav"))

    def _text_label(self) -> str:
        return _text(self.app._konsole_fav_text)

    def _fertig(self) -> None:
        """Warten, bis der Faden fertig ist - und der Takt seinen Endstand uebernommen hat (Warnung ueber Haengendes)."""
        self.assertTrue(_bis(lambda: not self.app._konsole_tafel_beschaeftigt()))
        _WURZEL.update()
        self.app._konsole_tafel_takt()

    def _senden(self) -> None:
        """Der Knopf „Favoriten senden“ mit gefuellter Adresse - und warten, bis er fertig ist."""
        self.app._konsole_tafel_ip.set("10.0.0.9")
        self.knopf[self.app._t("dienste.fav_button")].invoke()
        self._fertig()

    def _name(self, schluessel: str) -> str:
        return self.app._t(kd.dienst(schluessel).name_schluessel)

    # -- Die Tabelle -------------------------------------------------------------

    def test_die_erste_spalte_ist_der_stern(self) -> None:
        self.assertEqual("fav", self.tabelle["columns"][0])
        self.assertEqual("★", self.tabelle.heading("fav", "text"))
        for d in kd.KATALOG:
            with self.subTest(dienst=d.schluessel):
                if d.schluessel in NICHT_MOEGLICH:
                    soll = ""
                else:
                    soll = "★" if d.schluessel in kd.FAVORITEN_STANDARD else "☆"
                self.assertEqual(soll, self._stern(d.schluessel))

    def test_ohne_wahl_stehen_ftpsrv_und_klogsrv_da(self) -> None:
        self.assertEqual(["ftpsrv", "klogsrv"], self.app._konsole_favoriten())
        text = self._text_label()
        self.assertIn(self._name("ftpsrv") + ", " + self._name("klogsrv"), text)
        self.assertTrue(text.startswith("★ Favoriten: "), text)

    def test_der_haken_fuer_das_automatische_senden(self) -> None:
        haken = self.app._konsole_fav_auto_haken
        self.assertEqual("Beim Programmstart automatisch senden", _text(haken))
        self.assertTrue(self.app._konsole_fav_auto.get(), "Vorgabe an - wie bisher die Grundausstattung")
        self.assertTrue(self.app._konsole_favoriten_automatisch())
        haken.invoke()
        self.assertFalse(self.app._konsole_fav_auto.get())
        self.assertFalse(self.app._konsole_favoriten_automatisch(), "Die Wahl steht in der Einstellung")
        haken.invoke()
        self.assertTrue(self.app._konsole_favoriten_automatisch())

    # -- Waehlen ------------------------------------------------------------------

    def test_umschalten_waehlt_speichert_und_zeigt(self) -> None:
        self.app._konsole_favorit_umschalten("upload")
        self.assertEqual(["ftpsrv", "klogsrv", "upload"], self.app._konsole_favoriten())
        self.assertEqual(["ftpsrv", "klogsrv", "upload"], self.app._load_setting("konsole_favoriten", None))
        self.assertEqual("★", self._stern("upload"))
        self.assertIn(self._name("upload"), self._text_label())
        self.app._konsole_favorit_umschalten("ftpsrv")
        self.assertEqual(["klogsrv", "upload"], self.app._konsole_favoriten())
        self.assertEqual("☆", self._stern("ftpsrv"))
        self.assertNotIn(self._name("ftpsrv"), self._text_label())

    def test_die_wahl_steht_in_der_reihenfolge_der_tabelle(self) -> None:
        for schluessel in kd.FAVORITEN_STANDARD:                    # erst die Vorgabe abwaehlen ...
            self.app._konsole_favorit_umschalten(schluessel)
        self.assertEqual([], self.app._konsole_favoriten())
        for schluessel in ("upload", "klogsrv", "pldmgr", "ftpsrv"):    # ... dann in beliebiger Reihenfolge waehlen
            self.app._konsole_favorit_umschalten(schluessel)
        gespeichert = self.app._load_setting("konsole_favoriten", None)
        soll = [d.schluessel for d in kd.KATALOG if d.schluessel in {"upload", "klogsrv", "pldmgr", "ftpsrv"}]
        self.assertEqual(4, len(soll))
        self.assertEqual(soll, gespeichert, "Gespeichert wird in der Reihenfolge des Katalogs, nicht der Wahl")

    def test_alle_abwaehlen_ist_eine_bewusste_wahl(self) -> None:
        for schluessel in list(kd.FAVORITEN_STANDARD):
            self.app._konsole_favorit_umschalten(schluessel)
        self.assertEqual([], self.app._konsole_favoriten())
        self.assertEqual([], self.app._load_setting("konsole_favoriten", None))
        self.assertIn(self.app._t("dienste.fav_keine"), self._text_label())

    def test_ein_klick_in_die_sternspalte_waehlt(self) -> None:
        def klick(spalte: str, region: str = "cell", zeile: str = "upload"):
            ereignis = mock.Mock(x=5, y=5)
            with mock.patch.object(self.tabelle, "identify_region", return_value=region), \
                    mock.patch.object(self.tabelle, "identify_column", return_value=spalte), \
                    mock.patch.object(self.tabelle, "identify_row", return_value=zeile):
                self.app._konsole_tafel_klick(ereignis)

        klick("#2")                                     # der Name: nur die Zeile
        klick("#1", region="heading")                   # die Kopfzeile
        klick("#1", zeile="")                           # unterhalb der Zeilen
        self.assertEqual(["ftpsrv", "klogsrv"], self.app._konsole_favoriten())
        klick("#1")
        self.assertEqual(["ftpsrv", "klogsrv", "upload"], self.app._konsole_favoriten())
        klick("#1")
        self.assertEqual(["ftpsrv", "klogsrv"], self.app._konsole_favoriten())

    def test_die_leertaste_waehlt_die_markierte_zeile(self) -> None:
        self.tabelle.selection_set("pldmgr")
        self.assertEqual("break", self.app._konsole_tafel_leertaste())
        self.assertIn("pldmgr", self.app._konsole_favoriten())
        self.app._konsole_tafel_leertaste()
        self.assertNotIn("pldmgr", self.app._konsole_favoriten())
        self.tabelle.selection_set(())
        self.assertEqual("break", self.app._konsole_tafel_leertaste(), "Ohne Auswahl passiert nichts - und nichts bricht")

    def test_der_stern_haengt_an_der_tabelle_nicht_an_einem_fenster(self) -> None:
        self.assertTrue(self.tabelle.bind("<Button-1>"), "Klick gebunden")
        self.assertTrue(self.tabelle.bind("<space>"), "Leertaste gebunden")

    def test_wo_kein_favorit_moeglich_ist_sagt_das_protokoll_warum(self) -> None:
        self.app._konsole_favorit_umschalten("elfldr9021")
        self.assertIn(self.app._t("dienste.log_fav_loader"), self._protokoll())
        self.app._konsole_favorit_umschalten("shadowmount")
        self.assertIn(self.app._t("dienste.log_fav_nicht", name=self._name("shadowmount")), self._protokoll())
        self.assertEqual(["ftpsrv", "klogsrv"], self.app._konsole_favoriten(), "Die Wahl bleibt, wie sie war")
        self.app._konsole_favorit_umschalten("gibtesnicht")           # kein Fehler, kein Eintrag
        self.assertEqual(["ftpsrv", "klogsrv"], self.app._konsole_favoriten())

    def test_standard_setzt_die_wahl_zurueck(self) -> None:
        self.app._konsole_favorit_umschalten("upload")
        self.app._konsole_favorit_umschalten("ftpsrv")
        self.knopf[self.app._t("dienste.fav_standard")].invoke()
        self.assertEqual(list(kd.FAVORITEN_STANDARD), self.app._konsole_favoriten())
        self.assertEqual("☆", self._stern("upload"))
        self.assertEqual("★", self._stern("ftpsrv"))

    def test_eine_kaputte_einstellung_gilt_als_standard(self) -> None:
        for roh in ("abc", 5, {"a": 1}, None):
            self.app._save_setting("konsole_favoriten", roh)
            self.assertEqual(list(kd.FAVORITEN_STANDARD), self.app._konsole_favoriten(), repr(roh))
        self.app._save_setting("konsole_favoriten", ["gibtesnicht", "upload", 7])
        self.assertEqual(["upload"], self.app._konsole_favoriten())

    def test_die_zeile_folgt_dem_sprachwechsel(self) -> None:
        with mock.patch.object(self.app, "_current_language", "en"):
            self.app._konsole_favoriten_anzeigen()
            text = self._text_label()
        self.assertTrue(text.startswith("★ Favorites: "), text)
        self.assertIn(self.app._t("dienste.fav_zeile", liste="X").split("X")[0][:5], text)
        self.app._konsole_favoriten_anzeigen()
        self.assertTrue(self._text_label().startswith("★ Favoriten: "))

    # -- Senden -------------------------------------------------------------------

    def test_senden_sendet_was_fehlt_der_loader_laeuft_schon(self) -> None:
        self._senden()
        self.assertEqual(["ftpsrv", "klogsrv"], self.konsole.aufrufe, "Kein Loader-Aufruf: Er laeuft")
        protokoll = self._protokoll()
        self.assertIn(self.app._t("dienste.log_laeuft_schon", name=self._name("elfldr9021")), protokoll)

    def test_senden_oeffnet_zuerst_9021_dann_die_favoriten(self) -> None:
        self.konsole.laufend.discard("elfldr9021")
        self._senden()
        self.assertEqual(["loader", "ftpsrv", "klogsrv"], self.konsole.aufrufe)

    def test_laesst_sich_9021_nicht_oeffnen_wird_nichts_gesendet(self) -> None:
        self.konsole.laufend.discard("elfldr9021")
        self.konsole.loader_oeffnet = False
        self._senden()
        self.assertEqual(["loader"], self.konsole.aufrufe)
        self.assertIn(self.app._t("dienste.log_fav_ohne_loader"), self._protokoll())

    def test_ohne_favoriten_wird_nur_der_loader_sichergestellt(self) -> None:
        for schluessel in list(kd.FAVORITEN_STANDARD):
            self.app._konsole_favorit_umschalten(schluessel)
        self.konsole.laufend.discard("elfldr9021")
        self._senden()
        self.assertEqual(["loader"], self.konsole.aufrufe)
        self.assertIn(self.app._t("dienste.log_keine_favoriten"), self._protokoll())

    def test_gesendet_wird_in_der_reihenfolge_der_tabelle(self) -> None:
        for schluessel in ("upload", "pldmgr"):
            self.app._konsole_favorit_umschalten(schluessel)
        self._senden()
        soll = [d.schluessel for d in kd.KATALOG if d.schluessel in {"ftpsrv", "klogsrv", "upload", "pldmgr"}]
        self.assertEqual(soll, self.konsole.aufrufe)

    def test_laufende_und_haengende_werden_nicht_geschickt(self) -> None:
        self.app._konsole_favorit_umschalten("upload")
        self.konsole.laufend.add("ftpsrv")
        self.konsole.stumm.add("klogsrv")
        self._senden()
        self.assertEqual(["upload"], self.konsole.aufrufe)
        protokoll = self._protokoll()
        self.assertIn(self.app._t("dienste.log_laeuft_schon", name=self._name("ftpsrv")), protokoll)
        self.assertIn(self.app._t("dienste.log_stumm", name=self._name("klogsrv"),
                                  port=kd.dienst("klogsrv").port), protokoll)

    def test_nichts_zu_tun_wenn_alles_laeuft(self) -> None:
        self.konsole.laufend.update({"ftpsrv", "klogsrv"})
        self._senden()
        self.assertEqual([], self.konsole.aufrufe)

    def test_ohne_adresse_wird_nichts_gesendet(self) -> None:
        with mock.patch.object(APP, "messagebox") as box:
            self.knopf[self.app._t("dienste.fav_button")].invoke()
        box.showwarning.assert_called_once()
        self.assertEqual([], self.konsole.aufrufe)

    # -- Automatisch beim Programmstart --------------------------------------------

    def _beim_start(self) -> None:
        finder = mock.Mock(return_value=("10.0.0.9", self.konsole.pruefen("10.0.0.9"), None, ""))
        with mock.patch.object(self.app, "_konsole_ps5_finden", finder):
            self.app._konsole_beim_start_verbinden()
            self._fertig()

    def test_beim_programmstart_wird_automatisch_gesendet(self) -> None:
        self.konsole.laufend.discard("elfldr9021")
        self._beim_start()
        self.assertEqual(["loader", "ftpsrv", "klogsrv"], self.konsole.aufrufe)

    def test_die_eigene_wahl_gilt_auch_beim_programmstart(self) -> None:
        self.app._konsole_favorit_umschalten("upload")
        self.app._konsole_favorit_umschalten("klogsrv")
        self._beim_start()
        # Der Loader wird bei jeder Suche geprueft (laeuft er schon, kostet das nichts); danach die Wahl.
        self.assertEqual(["loader", "ftpsrv", "upload"], self.konsole.aufrufe)

    def test_ist_das_automatische_senden_aus_wird_nur_der_loader_geoeffnet(self) -> None:
        self.app._save_setting("konsole_favoriten_auto", False)
        self.konsole.laufend.discard("elfldr9021")
        self._beim_start()
        self.assertEqual(["loader"], self.konsole.aufrufe,
                         "9021 wird auch ohne Favoriten geoeffnet - das war schon immer so")

    def test_eine_selbst_angestossene_suche_sendet_nichts(self) -> None:
        self.app._konsole_favorit_umschalten("upload")
        finder = mock.Mock(return_value=("10.0.0.9", self.konsole.pruefen("10.0.0.9"), None, ""))
        with mock.patch.object(self.app, "_konsole_ps5_finden", finder):
            self.app._konsole_tafel_suchen()
            self._fertig()
        self.assertEqual(["loader"], self.konsole.aufrufe,
                         "Die Suche prueft den Loader (9021) - ein Favorit geht nur beim Programmstart und auf den Knopf raus")


class QuelltextTests(unittest.TestCase):
    """Was sich am laufenden Programm schlecht messen laesst - gemessen am Syntaxbaum."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.quelle = (PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py").read_text(encoding="utf-8")
        cls.baum = ast.parse(cls.quelle)
        cls.klasse = next(k for k in cls.baum.body if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")

    def _methode(self, name: str) -> ast.FunctionDef:
        return next(k for k in self.klasse.body if isinstance(k, ast.FunctionDef) and k.name == name)

    def test_jeder_textschluessel_der_favoriten_ist_uebersetzt(self) -> None:
        schluessel = set(re.findall(r'"(dienste\.(?:fav_[a-z_]+|col_fav|log_keine_favoriten|log_fav_[a-z_]+))"',
                                    self.quelle))
        self.assertGreaterEqual(len(schluessel), 8)
        for s in schluessel:
            self.assertTrue(STRINGS.get(s, {}).get("de") and STRINGS.get(s, {}).get("en"), s)

    def test_die_alte_grundausstattung_ist_ersetzt(self) -> None:
        self.assertNotIn("_konsole_tafel_grundausstattung", self.quelle)
        self.assertNotIn("_konsole_grundausstattung_nachstarten", self.quelle)
        self.assertNotIn("dienste.base_button", self.quelle)
        self.assertNotIn("dienste.base_button", STRINGS)

    def test_gesendet_wird_nur_ueber_nachstarten_und_nie_ohne_loader(self) -> None:
        text = ast.unparse(self._methode("_konsole_favoriten_nachstarten"))
        self.assertIn("uebersicht.laeuft('elfldr9021')", text, "Ohne Loader wird nichts versucht")
        self.assertIn("stand.stumm", text, "Ein haengender Dienst wird nicht noch einmal geschickt")

    def test_der_knopf_oeffnet_9021_bevor_er_sendet(self) -> None:
        methode = self._methode("_konsole_tafel_favoriten")
        arbeit = next(k for k in ast.walk(methode) if isinstance(k, ast.FunctionDef) and k.name == "_arbeit")
        namen = [getattr(k.func, "attr", "") for k in ast.walk(arbeit) if isinstance(k, ast.Call)]
        self.assertLess(namen.index("_konsole_elfldr_sicherstellen"), namen.index("_konsole_favoriten_nachstarten"))

    def test_der_programmstart_prueft_die_einstellung(self) -> None:
        text = ast.unparse(self._methode("_konsole_tafel_suchen"))
        self.assertIn("self._konsole_favoriten_automatisch()", text)
        self.assertIn("self._konsole_favoriten_nachstarten(", text)

    def test_nur_der_programmstart_ruft_suchen_mit_favoriten(self) -> None:
        aufrufe = [k for k in ast.walk(self.baum) if isinstance(k, ast.Call)
                   and getattr(k.func, "attr", "") == "_konsole_tafel_suchen"
                   and any(kw.arg == "favoriten" for kw in k.keywords)]
        self.assertEqual(1, len(aufrufe))
        self.assertEqual("_konsole_beim_start_verbinden",
                         next(m.name for m in self.klasse.body if isinstance(m, ast.FunctionDef)
                              and aufrufe[0] in list(ast.walk(m))))


if __name__ == "__main__":
    unittest.main()
