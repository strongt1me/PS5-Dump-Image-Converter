# -*- coding: utf-8 -*-
""""1. Konsole & Payloads": die PS5 von selbst finden und Dienste zuegig starten.

Wunsch des Nutzers vom 26.09.2026: "Weshalb dauert das Senden der Payloads so
lange ...? Und kannst du hier ebenfalls die PS5 automatisch suchen beim
Druecken auf den Knopf 1. Konsole & Payloads. Damit der Nutzer nicht extra noch
selber verbinden muss."

* Die Suche (``_konsole_ps5_finden``) kommt **ohne FTP** aus - auf die Seite
  kommt man, um ftpsrv erst zu starten: bekannte Adressen mit laufendem
  Dienst, dann der Rundruf der Konsolensuche, dann jede Adresse des eigenen
  Netzes einzeln (``remoteplay.suchen_in``).
* Ein Dienst-Payload wird nur kurz mitgelesen (``konsole_dienste.LESEZEIT``),
  danach wird der Port abgefragt, bis er antwortet (``warten_bis_bereit``).
  Vorher: 30 s Lesezeit - ein Dienst schliesst die Verbindung nie - plus feste
  Anlaufzeit, je Payload.
* Ist Port 9021 zu, laedt die Seite elfldr selbst ueber den Payload Manager
  (zweiter Wunsch vom selben Tag; ``payload_versand.elfldr_laden``, gemessen
  in ``test_elfldr_ablage``) - nach dem Suchen und nach "Konsole pruefen".
* Kein eigenes Fenster mehr: "Ich wollte alles in der rechten Ansicht verlegt
  in einem. Nicht separat." Die Uebersicht rechts und das fruehere Fenster
  sind eine Seite (dritter Wunsch vom selben Tag).
* Beim Programmstart verbindet sich das Programm von selbst: "Somit muss der
  Nutzer nicht manuell seine PS5 IP eingeben" (vierter Wunsch) - samt
  Grundausstattung, aber nur vom echten Programmstart aus.

Gegenstellen sind echte Sockets auf 127.0.0.1 (UDP-Antworter wie eine PS5,
TCP-Horcher als Dienst); ins Netz geht kein Test.
"""
from __future__ import annotations

import ast
import gc
import os
import socket
import sys
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

PROJEKT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJEKT))

import pruefumgebung                                        # noqa: E402
pruefumgebung.umlenken("konsole_suche")

import PS5ImageConverter_Pro_FINAL_revised as APP           # noqa: E402
from ps5_validator.utils import konsole_dienste as kd       # noqa: E402
from ps5_validator.utils import payload_versand as pv       # noqa: E402
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


def _freier_port(art: int = socket.SOCK_STREAM) -> int:
    probe = socket.socket(socket.AF_INET, art)
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return port


class _UdpAntworter:
    """Antwortet auf die Konsolensuche wie eine PS5 - auf 127.0.0.1."""

    def __init__(self, antwort: bytes = b"HTTP/1.1 200 Ok\nhost-name:PS5-TEST\n"
                                        b"host-type:PS5\nsystem-version:12000043\n") -> None:
        self.antwort = antwort
        self.anfragen: list = []

    def __enter__(self) -> "_UdpAntworter":
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(0.2)
        self.port = self.sock.getsockname()[1]
        self.laeuft = True
        self.faden = threading.Thread(target=self._bedienen, daemon=True)
        self.faden.start()
        return self

    def _bedienen(self) -> None:
        while self.laeuft:
            try:
                daten, absender = self.sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                return
            self.anfragen.append(daten)
            try:
                self.sock.sendto(self.antwort, absender)
            except OSError:
                pass

    def __exit__(self, *_rest) -> None:
        self.laeuft = False
        self.faden.join(1.0)
        self.sock.close()


class _TcpHorcher:
    """Ein Dienst: nimmt beliebig viele Verbindungen an - auf Wunsch erst nach ``ab`` s."""

    def __init__(self, ab: float = 0.0, gruss: bytes = b"") -> None:
        self.port = _freier_port()
        self.ab = ab
        self.gruss = gruss
        self.bereit = threading.Event()

    def __enter__(self) -> "_TcpHorcher":
        self.laeuft = True
        self.faden = threading.Thread(target=self._bedienen, daemon=True)
        self.faden.start()
        if not self.ab:
            self.bereit.wait(2.0)
        return self

    def _bedienen(self) -> None:
        time.sleep(self.ab)
        horcher = socket.socket()
        horcher.bind(("127.0.0.1", self.port))
        horcher.listen(8)
        horcher.settimeout(0.1)
        self.bereit.set()
        try:
            while self.laeuft:
                try:
                    verbindung, _ = horcher.accept()
                except socket.timeout:
                    continue
                except OSError:
                    return
                try:
                    if self.gruss:
                        verbindung.sendall(self.gruss)
                    else:
                        time.sleep(0.3)      # still - wie ein Dienst ohne Gruss
                finally:
                    verbindung.close()
        finally:
            horcher.close()

    def __exit__(self, *_rest) -> None:
        self.laeuft = False
        self.faden.join(2.0)


class SuchenInTests(unittest.TestCase):
    """Jede Adresse einzeln fragen - fuer Router, die keinen Rundruf durchlassen."""

    def test_eine_konsole_antwortet(self) -> None:
        with _UdpAntworter() as ps5:
            beginn = time.monotonic()
            gefunden = remoteplay.suchen_in(["127.0.0.1"], zeit=0.8, port=ps5.port)
            dauer = time.monotonic() - beginn
        self.assertEqual(["127.0.0.1"], [k.adresse for k in gefunden])
        self.assertEqual(("PS5-TEST", 200, "12000043"),
                         (gefunden[0].name, gefunden[0].status, gefunden[0].firmware))
        self.assertTrue(ps5.anfragen[0].startswith(b"SRCH * HTTP/1.1"))
        self.assertIn(b"device-discovery-protocol-version:00030010", ps5.anfragen[0])
        self.assertLess(dauer, 2.0)

    def test_stumme_adressen_stoeren_nicht(self) -> None:
        """Unter Windows meldet ein 'unerreichbar' sich beim naechsten Empfang als Fehler."""
        with _UdpAntworter() as ps5:
            gefunden = remoteplay.suchen_in(["127.0.0.2", "127.0.0.1", "127.0.0.3"],
                                            zeit=0.8, port=ps5.port)
        self.assertEqual(["127.0.0.1"], [k.adresse for k in gefunden])

    def test_ohne_konsole_leer(self) -> None:
        self.assertEqual([], remoteplay.suchen_in(
            ["127.0.0.1"], zeit=0.4, port=_freier_port(socket.SOCK_DGRAM)))


class WartenBisBereitTests(unittest.TestCase):
    """Den Port abfragen, bis der Dienst antwortet - statt die Anlaufzeit fest abzuwarten."""

    def test_ein_laufender_dienst_haelt_nicht_auf(self) -> None:
        with _TcpHorcher() as dienst:
            beginn = time.monotonic()
            self.assertTrue(kd.warten_bis_bereit(
                "127.0.0.1", kd.Dienst("klogsrv", dienst.port, anlaufzeit=5.0),
                grenze=4.0, takt=0.1))
            self.assertLess(time.monotonic() - beginn, 1.0)

    def test_ein_dienst_der_spaeter_hochkommt(self) -> None:
        with _TcpHorcher(ab=0.6) as dienst:
            beginn = time.monotonic()
            self.assertTrue(kd.warten_bis_bereit(
                "127.0.0.1", kd.Dienst("klogsrv", dienst.port), grenze=4.0, takt=0.1))
            dauer = time.monotonic() - beginn
        self.assertGreaterEqual(dauer, 0.5)
        self.assertLess(dauer, 3.0, "Die ganze Frist abgewartet statt beim Antworten aufzuhoeren.")

    def test_ein_dienst_der_nicht_kommt(self) -> None:
        beginn = time.monotonic()
        self.assertFalse(kd.warten_bis_bereit(
            "127.0.0.1", kd.Dienst("klogsrv", _freier_port()), grenze=0.6, takt=0.1))
        self.assertGreaterEqual(time.monotonic() - beginn, 0.6)

    def test_ohne_gruss_gilt_ein_gruessender_dienst_nicht(self) -> None:
        """ftpsrv: Port offen, aber stumm = haengt (siehe konsole_dienste.Stand)."""
        with _TcpHorcher() as stumm:
            self.assertFalse(kd.warten_bis_bereit(
                "127.0.0.1", kd.Dienst("ftpsrv", stumm.port, begruessung=True),
                grenze=0.8, takt=0.1, zeit=0.2))
        with _TcpHorcher(gruss=b"220 ftpsrv\r\n") as gut:
            self.assertTrue(kd.warten_bis_bereit(
                "127.0.0.1", kd.Dienst("ftpsrv", gut.port, begruessung=True),
                grenze=2.0, takt=0.1))

    def test_die_frist_ohne_angabe(self) -> None:
        """Mindestens 6 s, sonst das Vierfache der Anlaufzeit - mit einer Uhr im Modul."""
        uhr = [100.0]
        falsche_zeit = types.SimpleNamespace(
            monotonic=lambda: uhr[0], sleep=lambda s: uhr.__setitem__(0, uhr[0] + s))
        with mock.patch.object(kd, "time", falsche_zeit), \
                mock.patch.object(kd, "dienst_pruefen", return_value=(False, False)):
            for anlaufzeit, frist in ((1.0, 6.0), (2.5, 10.0)):
                uhr[0] = 100.0
                with self.subTest(anlaufzeit=anlaufzeit):
                    self.assertFalse(kd.warten_bis_bereit(
                        "x", kd.Dienst("a", 1, anlaufzeit=anlaufzeit), takt=0.5))
                    self.assertAlmostEqual(100.0 + frist, uhr[0], delta=0.6)

    def test_die_lesezeit_ist_kurz(self) -> None:
        """Ein Dienst schliesst die Verbindung nie - 30 s Lesezeit hiess 30 s Warten."""
        self.assertLessEqual(kd.LESEZEIT, 5.0)
        self.assertGreater(kd.LESEZEIT, 0.0)


def _uebersicht(host: str, laufend: tuple = ()) -> kd.Uebersicht:
    return kd.Uebersicht(host, [kd.Stand(d, d.schluessel in laufend) for d in kd.KATALOG])


class FindenTests(unittest.TestCase):
    """_konsole_ps5_finden: bekannte Adresse, Rundruf, jede Adresse einzeln."""

    def _gui(self, adresse: str = ""):
        """Ein Programmobjekt ohne Fenster - FTP darf die Suche nie fragen.

        Die Nebenwirkung haelt einen verbotenen FTP-Aufruf an; ob er kam,
        prueft die Aufraeumrunde von aussen (ein ``except Exception`` in der
        Suche wuerde den AssertionError sonst still schlucken).
        """
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gui._current_language = "de"
        gui._bibliothek_ps5_host = ""
        gui._load_setting = lambda k, v=None: {"ps5_ip": adresse}.get(k, v)
        gui._ampr_gen_profil_adressen = lambda: []
        gui._ampr_gen_eigene_netze = lambda: ["10.0.0"]
        gui._ampr_gen_ist_ps5 = mock.Mock(side_effect=AssertionError("FTP gefragt"))
        self.addCleanup(gui._ampr_gen_ist_ps5.assert_not_called)
        gui._ampr_gen_frage = mock.Mock(return_value="")
        return gui

    def _finden(self, gui, vorgabe="", laufend=None, rundruf=(), einzeln=()):
        """``meldungen`` sammelt ``(schluessel, werte)`` - die Suche uebersetzt nicht."""
        laufend = laufend or {}
        meldungen: list = []
        einzeln_gefragt: list = []

        def _einzeln(adressen, *_a, **_k):
            einzeln_gefragt.append(list(adressen))
            return list(einzeln)

        with mock.patch.object(kd, "pruefen",
                               lambda host, *a, **k: _uebersicht(host, laufend.get(host, ()))), \
                mock.patch.object(remoteplay, "suchen",
                                  mock.Mock(return_value=list(rundruf))) as suchen, \
                mock.patch.object(remoteplay, "suchen_in", _einzeln):
            ergebnis = gui._konsole_ps5_finden(
                None, vorgabe, lambda schluessel, **werte: meldungen.append((schluessel, werte)))
        return ergebnis, meldungen, suchen, einzeln_gefragt

    def test_die_bekannte_adresse_mit_laufendem_dienst(self) -> None:
        gui = self._gui()
        (host, uebersicht, konsole, grund), _m, suchen, _e = self._finden(
            gui, "10.0.0.5", laufend={"10.0.0.5": ("elfldr9021",)})
        self.assertEqual(("10.0.0.5", None, ""), (host, konsole, grund))
        self.assertTrue(uebersicht.laeuft("elfldr9021"))
        suchen.assert_not_called()
        gui._ampr_gen_ist_ps5.assert_not_called()

    def test_ohne_laufenden_dienst_hilft_der_rundruf(self) -> None:
        """Frisch gestartete Konsole ohne Payload: nur die Konsolensuche kennt sie."""
        gui = self._gui()
        ps5 = remoteplay.Konsole(adresse="10.0.0.5", name="PS5-TEST", status=200)
        (host, uebersicht, konsole, _g), meldungen, _s, einzeln = self._finden(
            gui, "10.0.0.5", rundruf=[ps5])
        self.assertEqual("10.0.0.5", host)
        self.assertIs(ps5, konsole)
        self.assertEqual(0, uebersicht.anzahl_laufend)
        self.assertEqual([], einzeln, "Der Rundruf kam durch - kein Einzelfragen noetig.")
        self.assertIn(("dienste.suche_rundruf", {}), meldungen)

    def test_ohne_rundruf_jede_adresse_einzeln(self) -> None:
        gui = self._gui()
        (host, _u, konsole, _g), meldungen, _s, einzeln = self._finden(
            gui, einzeln=[remoteplay.Konsole(adresse="10.0.0.77", name="PS5", status=620)])
        self.assertEqual("10.0.0.77", host)
        self.assertEqual(620, konsole.status)
        self.assertEqual(1, len(einzeln))
        self.assertEqual(["10.0.0.%d" % n for n in range(1, 255)], einzeln[0])
        self.assertIn(("dienste.suche_netz", {"netze": "10.0.0"}), meldungen)

    def test_nichts_gefunden(self) -> None:
        gui = self._gui()
        (host, uebersicht, konsole, grund), _m, _s, _e = self._finden(gui, "10.0.0.5")
        self.assertEqual(("", None, None), (host, uebersicht, konsole))
        self.assertEqual("dienste.suche_nichts", grund, "Ein Schluessel - uebersetzt der Takt.")

    def test_die_suche_uebersetzt_nichts(self) -> None:
        """Jede Meldung ist ein Schluessel mit Werten (Durchsicht H2-13)."""
        gui = self._gui(adresse="10.0.0.6")
        _e, meldungen, _s, _x = self._finden(
            gui, "10.0.0.5", einzeln=[remoteplay.Konsole(adresse="10.0.0.77", status=200)])
        self.assertTrue(meldungen)
        for schluessel, werte in meldungen:
            with self.subTest(schluessel=schluessel):
                self.assertIn(schluessel, STRINGS)
                self.assertIsInstance(werte, dict)

    def test_mehrere_konsolen_fragen(self) -> None:
        gui = self._gui()
        gui._ampr_gen_frage.return_value = "10.0.0.8"
        konsolen = [remoteplay.Konsole(adresse="10.0.0.7", name="A", status=200),
                    remoteplay.Konsole(adresse="10.0.0.8", name="B", status=200)]
        (host, _u, konsole, _g), _m, _s, _e = self._finden(gui, rundruf=konsolen)
        self.assertEqual(("10.0.0.8", "B"), (host, konsole.name))
        optionen = gui._ampr_gen_frage.call_args[0][3]
        self.assertEqual(["10.0.0.7", "10.0.0.8"], [o[0] for o in optionen])
        gui._ampr_gen_frage.return_value = ""
        (host, *_rest), _m, _s, _e = self._finden(gui, rundruf=konsolen)
        self.assertEqual("", host, "Abgebrochen heisst: keine Konsole.")

    def test_eine_bekannte_unter_mehreren_gilt_ohne_frage(self) -> None:
        gui = self._gui()
        konsolen = [remoteplay.Konsole(adresse="10.0.0.7", status=200),
                    remoteplay.Konsole(adresse="10.0.0.8", status=200)]
        (host, *_rest), _m, _s, _e = self._finden(gui, "10.0.0.8", rundruf=konsolen)
        self.assertEqual("10.0.0.8", host)
        gui._ampr_gen_frage.assert_not_called()

    def test_die_gespeicherte_adresse_ist_ein_kandidat(self) -> None:
        gui = self._gui(adresse="10.0.0.6")
        (host, *_rest), meldungen, suchen, _e = self._finden(
            gui, "", laufend={"10.0.0.6": ("ftpsrv",)})
        self.assertEqual("10.0.0.6", host)
        self.assertIn(("dienste.suche_pruefe", {"host": "10.0.0.6"}), meldungen)
        suchen.assert_not_called()


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


@unittest.skipUnless(_TK_DA, "ohne Anzeige kein Fenster")
class SeitenTests(unittest.TestCase):
    """Die Seite "Konsole & Payloads" rechts in der Ansicht KONSOLE (seit 26.09.2026).

    Bis dahin oeffnete Knopf 1 ein eigenes Fenster neben der Uebersicht. Der
    Nutzer: "Ich wollte alles in der rechten Ansicht verlegt in einem. Nicht
    separat." Die Seite wird einmal gebaut und bleibt stehen - jeder Test
    raeumt sie deshalb vorher auf (Feld, Stand, Protokoll, Auswahl).

    Ins Netz geht nichts: Konsolensuche, Dienstabfrage, Senden und das Laden
    von elfldr sind vorab ersetzt; wer davon etwas braucht, flickt es selbst.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.PS5ConverterGUI(_WURZEL)
        cls.app._current_language = "de"

    def setUp(self) -> None:
        # Vorsorge wie in test_durchsicht_runde8-11: Die Fenster frueherer
        # Tests haengen in Referenzzyklen. Raeumt der Sammler sie im
        # Arbeitsfaden weg, wartet dort jede StringVar 1 s auf eine
        # Ereignisschleife, die im Test nie laeuft ("main thread is not in main
        # loop"). Am 26.09.2026 lief "Pruefen" einmal in die Zeitgrenze, im
        # selben Lauf mit genau dieser Warnung; ohne dieses Aufraeumen danach
        # sechsmal nicht wiederholbar - die Ursache ist also nicht belegt.
        gc.collect()
        self.gespeichert: list = []
        self.hauptprotokoll: list = []
        # Werfende Attrappen halten einen verbotenen Netzzugriff an; ob einer
        # kam, prueft die Aufraeumrunde von aussen (ein except Exception im
        # Faden wuerde den AssertionError sonst still schlucken).
        senden = mock.Mock(side_effect=AssertionError("Payload geschickt"))
        laden = mock.Mock(side_effect=AssertionError("elfldr geladen"))
        self.addCleanup(senden.assert_not_called)
        self.addCleanup(laden.assert_not_called)
        for ziel, name, ersatz in (
                (self.app, "_ps5_ip", lambda: ""),
                (self.app, "_save_setting", lambda k, v: self.gespeichert.append((k, v))),
                (self.app, "_append_to_log", lambda text: self.hauptprotokoll.append(text)),
                (self.app, "_send_payload_to_ps5", senden),
                (pv, "elfldr_laden", laden),
                (remoteplay, "suchen", mock.Mock(return_value=[])),
                (kd, "pruefen", lambda host, *a, **k: _uebersicht(host))):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        self.app._ansicht_setzen("konsole", speichern=False)
        self.app._konsole_seite_setzen("uebersicht")
        _WURZEL.update_idletasks()
        self.assertTrue(_bis(lambda: not self.app._konsole_tafel_beschaeftigt()))
        self.app._konsole_tafel_stand = None
        self.app._konsole_tafel_puffer.clear()
        self.app._konsole_tafel_gezeigt = 0
        self.app._konsole_tafel_protokoll.delete("1.0", "end")
        self.app._konsole_tafel_ip.set("")
        self.app._konsole_tafel_tabelle.selection_set(())
        self.app._konsole_start_melden = False
        # Tabelle, Zustand und Status wieder auf "noch nicht geprueft".
        self.app._konsole_tafel_beschriften()
        self.addCleanup(self._zurueck)
        widgets = list(_alle(self.app._konsole_tafel))
        self.feld = next(w for w in widgets if isinstance(w, tk.Entry))
        self.tabelle = self.app._konsole_tafel_tabelle
        self.protokoll = self.app._konsole_tafel_protokoll
        self.knopf = {_text(w): w for w in widgets if isinstance(w, ttk.Button)}

    def _zurueck(self) -> None:
        _bis(lambda: not self.app._konsole_tafel_beschaeftigt())
        self.app._ansicht_setzen("umwandeln", speichern=False)
        _WURZEL.update()
        gc.collect()

    def _laeuft_nichts(self) -> bool:
        return (not self.app._konsole_tafel_beschaeftigt()
                and str(self.knopf[self.app._t("tafel.check")].cget("state")) == "normal")

    def _finder(self, finden) -> None:
        flicken = mock.patch.object(self.app, "_konsole_ps5_finden", finden)
        flicken.start()
        self.addCleanup(flicken.stop)

    def _druecken(self, finden) -> None:
        """Knopf 1 der Seitenleiste - genau der Weg, den der Klick nimmt."""
        self._finder(finden)
        self.app._konsole_knopf_gedrueckt("dienste", "konsole.btn_dienste")

    def _text_protokoll(self) -> str:
        return self.protokoll.get("1.0", "end")

    # -- Eine Seite statt eines Fensters ------------------------------------

    def test_knopf_1_zeigt_die_seite_statt_eines_fensters(self) -> None:
        vorher = {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)}
        with mock.patch.object(self.app, "_werkzeugfenster_umschalten") as fenster:
            self._druecken(mock.Mock(return_value=("", None, None, "dienste.suche_nichts")))
            self.assertTrue(_bis(self._laeuft_nichts))
        fenster.assert_not_called()
        neu = {w for w in _WURZEL.winfo_children() if isinstance(w, tk.Toplevel)} - vorher
        self.assertEqual(set(), neu, "Knopf 1 oeffnet wieder ein eigenes Fenster.")
        lage = self.app._konsole_tafel.grid_info()
        self.assertEqual((1, 1), (int(lage["row"]), int(lage["column"])))
        knopf = next(k for k, s in self.app._konsole_knoepfe if s == "konsole.btn_dienste")
        self.assertEqual(self.app._COLORS["fg_accent"], knopf._bg)

    def test_das_fenster_gibt_es_nicht_mehr(self) -> None:
        klasse = APP.PS5ConverterGUI
        self.assertFalse(hasattr(klasse, "_show_konsole_dienste"))
        self.assertNotIn("dienste", klasse._KONSOLE_FENSTER)
        self.assertEqual("_konsole_dienste_zeigen", klasse._KONSOLE_SEITEN["dienste"])
        self.assertEqual("konsole.btn_dienste", klasse._KONSOLE_SEITENBAU["uebersicht"][2])

    def test_die_seite_zeigt_alles_was_das_fenster_hatte(self) -> None:
        self.assertEqual([d.schluessel for d in kd.KATALOG], list(self.tabelle.get_children()))
        erste = kd.KATALOG[0]
        self.assertEqual([self.app._t(erste.name_schluessel), str(erste.port),
                          self.app._t("dienste.zustand_aus"), self.app._t(erste.zweck_schluessel)],
                         [str(w) for w in self.tabelle.item(erste.schluessel, "values")])
        for schluessel in ("tafel.check", "dienste.start_button", "dienste.base_button",
                           "dienste.web_button"):
            with self.subTest(knopf=schluessel):
                self.assertIn(self.app._t(schluessel), self.knopf)
        texte = [_text(w) for w in _alle(self.app._konsole_tafel)]
        self.assertIn(self.app._t("dienste.hint"), texte)
        self.assertIn(self.app._t("tafel.title"), texte)

    # -- Suchen und Pruefen ------------------------------------------------

    def test_knopf_1_sucht_und_uebernimmt_die_adresse(self) -> None:
        ps5 = remoteplay.Konsole(adresse="10.0.0.9", name="PS5-TEST", status=200,
                                 firmware="12000043")
        finden = mock.Mock(return_value=(
            "10.0.0.9", _uebersicht("10.0.0.9", ("elfldr9021", "ftpsrv")), ps5, ""))
        self._druecken(finden)
        self.assertTrue(_bis(lambda: self.feld.get() == "10.0.0.9" and self._laeuft_nichts()))
        finden.assert_called_once()
        fenster, vorgabe, melden = finden.call_args[0]
        self.assertEqual((self.app.root, ""), (fenster, vorgabe))
        self.assertEqual(self.app._konsole_tafel_schritt, melden)
        self.assertIn(("ps5_ip", "10.0.0.9"), self.gespeichert)
        self.assertIn(("konsole_firmware", "12000043"), self.gespeichert)
        self.assertEqual(self.app._t("dienste.zustand_laeuft"),
                         self.tabelle.set("ftpsrv", "zustand"))
        self.assertEqual(self.app._t("tafel.gefunden", name="PS5-TEST",
                                     zustand=self.app._t("remoteplay.status_an"),
                                     firmware="12000043"),
                         self.app._konsole_tafel_zustand.get())
        text = self._text_protokoll()
        self.assertIn(self.app._t("dienste.log_gefunden", name="PS5-TEST", host="10.0.0.9",
                                  zustand=self.app._t("remoteplay.status_an")), text)
        self.assertIn(self.app._t("dienste.log_adresse_gespeichert", host="10.0.0.9"), text)

    def test_ueber_eine_bekannte_adresse_fragt_die_suche_nach_dem_namen(self) -> None:
        """Gefunden ueber einen laufenden Dienst - Name und Firmware nennt nur UDP 9302."""
        ps5 = remoteplay.Konsole(adresse="10.0.0.9", name="PS5-TEST", status=200,
                                 firmware="12000043")
        with mock.patch.object(remoteplay, "suchen", mock.Mock(return_value=[ps5])) as suche:
            self._druecken(mock.Mock(return_value=(
                "10.0.0.9", _uebersicht("10.0.0.9", ("elfldr9021",)), None, "")))
            self.assertTrue(_bis(lambda: self.feld.get() == "10.0.0.9"
                                 and self._laeuft_nichts()))
        suche.assert_called_once_with("10.0.0.9", zeit=2.0)
        self.assertIn("PS5-TEST", self.app._konsole_tafel_zustand.get())
        self.assertIn(("konsole_firmware", "12000043"), self.gespeichert)

    def test_nicht_gefunden_sagt_es_und_speichert_nichts(self) -> None:
        self._druecken(mock.Mock(return_value=("", None, None, "dienste.suche_nichts")))
        self.assertTrue(_bis(self._laeuft_nichts))
        grund = self.app._t("dienste.suche_nichts")
        self.assertIn(grund, self._text_protokoll())
        self.assertEqual(grund, self.app._konsole_tafel_status.get())
        self.assertEqual(self.app._t("tafel.nicht_gefunden"),
                         self.app._konsole_tafel_zustand.get())
        self.assertEqual("", self.feld.get())
        self.assertEqual([], [e for e in self.gespeichert if e[0] == "ps5_ip"])

    def test_pruefen_ohne_adresse_sucht(self) -> None:
        finden = mock.Mock(return_value=("", None, None, "dienste.suche_nichts"))
        self._finder(finden)
        self.knopf[self.app._t("tafel.check")].invoke()
        self.assertTrue(_bis(lambda: finden.call_count == 1 and self._laeuft_nichts()))

    def test_pruefen_mit_adresse_prueft_dort_und_laesst_das_feld_stehen(self) -> None:
        finden = mock.Mock(side_effect=AssertionError("gesucht statt geprueft"))
        self._finder(finden)
        self.feld.insert(0, "10.0.0.50")
        abgefragt: list = []
        with mock.patch.object(kd, "pruefen",
                               lambda host, *a, **k: abgefragt.append(host) or _uebersicht(host)):
            self.knopf[self.app._t("tafel.check")].invoke()
            self.assertTrue(_bis(lambda: abgefragt and self._laeuft_nichts()))
        finden.assert_not_called()
        remoteplay.suchen.assert_called_once_with("10.0.0.50", zeit=2.0)
        self.assertEqual(["10.0.0.50"], abgefragt)
        self.assertEqual("10.0.0.50", self.feld.get())
        self.assertIn(("ps5_ip", "10.0.0.50"), self.gespeichert)

    # -- Starten und Weboberflaeche ---------------------------------------

    def test_ein_dienst_wird_kurz_gelesen_und_dann_abgefragt(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        gesendet: list = []
        gewartet: list = []

        def _senden(ip, pfad, *a, **k):
            gesendet.append((ip, pfad, a, k))
            return True, "1 KB"

        with mock.patch.object(self.app, "_send_payload_to_ps5", _senden), \
                mock.patch.object(self.app, "_konsole_payload_datei",
                                  lambda _m: str(Path(__file__))), \
                mock.patch.object(kd, "warten_bis_bereit",
                                  lambda ip, eintrag, **k: gewartet.append((ip, eintrag)) or True):
            self.tabelle.selection_set("klogsrv")
            self.knopf[self.app._t("dienste.start_button")].invoke()
            self.assertTrue(_bis(lambda: gesendet and self._laeuft_nichts()))
        self.assertEqual(1, len(gesendet))
        self.assertEqual(kd.LESEZEIT, gesendet[0][3].get("lesezeit"),
                         "Mit der Vorgabe von 30 s wartete jeder Dienst-Start 30 s.")
        self.assertEqual([("10.0.0.9", kd.dienst("klogsrv"))], gewartet)
        name = self.app._t(kd.dienst("klogsrv").name_schluessel)
        self.assertIn(self.app._t("dienste.log_sende", name=name,
                                  datei=os.path.basename(__file__)), self._text_protokoll())
        self.assertEqual(("klogsrv",), self.tabelle.selection(),
                         "Die Auswahl ueberlebt die neue Uebersicht.")

    def test_ohne_adresse_wird_nichts_geschickt(self) -> None:
        with mock.patch.object(APP, "messagebox") as box:
            self.knopf[self.app._t("dienste.base_button")].invoke()
        box.showwarning.assert_called_once()
        self.assertFalse(self.app._konsole_tafel_beschaeftigt())

    def test_ohne_auswahl_wird_nachgefragt(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        with mock.patch.object(APP, "messagebox") as box:
            self.knopf[self.app._t("dienste.start_button")].invoke()
        box.showinfo.assert_called_once()
        self.assertEqual(self.app._t("dienste.need_auswahl"), box.showinfo.call_args[0][1])

    def test_grundausstattung_startet_nur_was_fehlt(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        gestartet: list = []
        with mock.patch.object(kd, "pruefen",
                               lambda host, *a, **k: _uebersicht(host, ("elfldr9021",))), \
                mock.patch.object(self.app, "_konsole_dienst_starten",
                                  lambda schluessel, ip: gestartet.append((schluessel, ip))):
            self.knopf[self.app._t("dienste.base_button")].invoke()
            self.assertTrue(_bis(lambda: len(gestartet) == 2 and self._laeuft_nichts()))
        self.assertEqual([("ftpsrv", "10.0.0.9"), ("klogsrv", "10.0.0.9")], gestartet)
        self.assertIn(self.app._t("dienste.log_laeuft_schon", name=self.app._t(
            kd.dienst("elfldr9021").name_schluessel)), self._text_protokoll())

    def test_weboberflaeche_oeffnet_den_browser(self) -> None:
        self.feld.insert(0, "10.0.0.9")
        self.tabelle.selection_set("pldmgr")
        with mock.patch.object(APP.webbrowser, "open") as oeffnen:
            self.knopf[self.app._t("dienste.web_button")].invoke()
        adresse = kd.web_adresse(kd.dienst("pldmgr"), "10.0.0.9")
        oeffnen.assert_called_once_with(adresse)
        self.assertIn(self.app._t("dienste.log_web", adresse=adresse), self._text_protokoll())

    # -- Port 9021 zu: elfldr ueber den Payload Manager --------------------

    def _elfldr_flicken(self, ablage=None, fehler=None, laufend=("pldmgr", "ftpsrv")):
        """elfldr_laden, Warten und die Abfrage danach - aufgezeichnet, ohne Netz."""
        geladen: list = []
        gewartet: list = []

        def _laden(host, daten, name, **benannt):
            geladen.append((host, daten, name, benannt))
            if fehler is not None:
                raise fehler
            return ablage

        def _pruefen(host, *_a, **_k):
            # Die leere Seite zeigt nichts Laufendes; elfldr laeuft erst,
            # nachdem es geladen wurde.
            if not host:
                return _uebersicht(host)
            return _uebersicht(host, (("elfldr9021",) if geladen else ()) + tuple(laufend))

        for ziel, name, ersatz in (
                (pv, "elfldr_laden", _laden),
                (kd, "warten_bis_bereit",
                 lambda ip, eintrag, **k: gewartet.append((ip, eintrag, k)) or True),
                (kd, "pruefen", _pruefen)):
            flicken = mock.patch.object(ziel, name, ersatz)
            flicken.start()
            self.addCleanup(flicken.stop)
        return geladen, gewartet

    def _elfldr_fall(self, ablage=None, fehler=None, laufend=("pldmgr", "ftpsrv")):
        """Knopf 1 mit einer PS5, auf der Port 9021 zu ist."""
        geladen, gewartet = self._elfldr_flicken(ablage, fehler, laufend)
        self._druecken(mock.Mock(return_value=(
            "10.0.0.9", _uebersicht("10.0.0.9", laufend), None, "")))
        self.assertTrue(_bis(lambda: self.feld.get() == "10.0.0.9" and self._laeuft_nichts()))
        return geladen, gewartet, self._text_protokoll()

    def test_ist_9021_zu_laedt_die_seite_elfldr(self) -> None:
        ablage = pv.ElfldrAblage("/data/pldmgr/payloads/elfldr/" + pv.ELFLDR_NAME,
                                 pv.ABLAGE_FTP)
        geladen, gewartet, text = self._elfldr_fall(ablage)
        elf = (PROJEKT / "helloworld" / pv.ELFLDR_NAME).read_bytes()
        self.assertEqual(1, len(geladen))
        host, daten, name, benannt = geladen[0]
        self.assertEqual(("10.0.0.9", pv.ELFLDR_NAME), (host, name))
        self.assertTrue(daten == elf, "Nicht das mitgelieferte elfldr geschickt.")
        self.assertIn("elfldr_belegt", benannt.get("texte", {}))
        eintrag = kd.dienst("elfldr9021")
        self.assertEqual([("10.0.0.9", eintrag, {"grenze": pv.ELFLDR_WARTEN})], gewartet)
        for zeile in (self.app._t("dienste.log_elfldr_laden"),
                      self.app._t("dienste.log_elfldr_hochgeladen", pfad=ablage.pfad,
                                  groesse=self.app._fmt_bytes(len(elf))),
                      self.app._t("dienste.log_gestartet",
                                  name=self.app._t(eintrag.name_schluessel), port=9021)):
            with self.subTest(zeile=zeile):
                self.assertIn(zeile, text)
        self.assertEqual(self.app._t("dienste.zustand_laeuft"),
                         self.tabelle.set("elfldr9021", "zustand"))

    def test_liegt_elfldr_schon_da_sagt_es_das(self) -> None:
        ablage = pv.ElfldrAblage("/data/pldmgr/payloads/elfldr/" + pv.ELFLDR_NAME,
                                 pv.ABLAGE_VORHANDEN)
        _geladen, _gewartet, text = self._elfldr_fall(ablage)
        self.assertIn(self.app._t("dienste.log_elfldr_vorhanden", pfad=ablage.pfad), text)
        self.assertNotIn(self.app._t("dienste.log_elfldr_hochgeladen", pfad=ablage.pfad,
                                     groesse="").split("(")[0], text)

    def test_ohne_ftp_ueber_die_weboberflaeche(self) -> None:
        _geladen, _gewartet, text = self._elfldr_fall(
            pv.ElfldrAblage("/data/pldmgr/payloads/elfldr/x.elf", pv.ABLAGE_WEB, "kein ftpsrv"))
        self.assertIn(self.app._t("dienste.log_elfldr_web"), text)

    def test_eine_fremde_datei_wird_gemeldet(self) -> None:
        _geladen, gewartet, text = self._elfldr_fall(
            fehler=pv.AblageBelegt("fremde Datei unter /x"))
        self.assertIn(self.app._t("dienste.log_elfldr_fehler", grund="fremde Datei unter /x"),
                      text)
        self.assertEqual([], gewartet, "Nichts geladen - also auch auf nichts warten.")

    def test_ohne_payload_manager_nur_ein_hinweis(self) -> None:
        geladen, _gewartet, text = self._elfldr_fall(
            pv.ElfldrAblage("/x", pv.ABLAGE_FTP), laufend=("ftpsrv",))
        self.assertEqual([], geladen)
        self.assertIn(self.app._t("dienste.log_elfldr_ohne_pldmgr"), text)

    def test_laeuft_elfldr_schon_wird_nichts_geladen(self) -> None:
        geladen, _gewartet, text = self._elfldr_fall(
            pv.ElfldrAblage("/x", pv.ABLAGE_FTP), laufend=("elfldr9021", "pldmgr"))
        self.assertEqual([], geladen)
        self.assertNotIn(self.app._t("dienste.log_elfldr_laden"), text)

    def test_auch_pruefen_laedt_elfldr(self) -> None:
        geladen, _gewartet = self._elfldr_flicken(
            pv.ElfldrAblage("/x/" + pv.ELFLDR_NAME, pv.ABLAGE_VORHANDEN))
        self.feld.insert(0, "10.0.0.50")
        self.knopf[self.app._t("tafel.check")].invoke()
        self.assertTrue(_bis(lambda: geladen and self._laeuft_nichts()))
        self.assertEqual(["10.0.0.50"], [g[0] for g in geladen])

    # -- Verbinden beim Programmstart --------------------------------------

    def test_beim_start_gesucht_samt_grundausstattung(self) -> None:
        with mock.patch.object(self.app, "_konsole_tafel_suchen") as suchen:
            self.app._konsole_beim_start_verbinden()
        suchen.assert_called_once_with(grundausstattung=True)
        self.assertEqual([self.app._t("konsole.start_suche") + "\n"], self.hauptprotokoll)
        self.assertTrue(self.app._konsole_start_melden)

    def test_das_ergebnis_steht_im_hauptprotokoll(self) -> None:
        ps5 = remoteplay.Konsole(adresse="10.0.0.9", name="PS5-TEST", status=200,
                                 firmware="12000043")
        self._finder(mock.Mock(return_value=(
            "10.0.0.9", _uebersicht("10.0.0.9", ("elfldr9021", "ftpsrv", "klogsrv")), ps5, "")))
        self.app._konsole_beim_start_verbinden()
        self.assertTrue(_bis(lambda: len(self.hauptprotokoll) == 2 and self._laeuft_nichts()))
        stand = self.app._konsole_tafel_stand
        self.assertEqual(self.app._t("konsole.start_ergebnis",
                                     zustand=self.app._konsole_tafel_zustandstext(stand),
                                     status=self.app._konsole_tafel_statustext(stand, False))
                         + "\n", self.hauptprotokoll[1])
        self.assertFalse(self.app._konsole_start_melden, "Nur einmal ins Hauptprotokoll.")

    def test_nicht_gefunden_beim_start(self) -> None:
        self._finder(mock.Mock(return_value=("", None, None, "dienste.suche_nichts")))
        self.app._konsole_beim_start_verbinden()
        self.assertTrue(_bis(lambda: len(self.hauptprotokoll) == 2 and self._laeuft_nichts()))
        self.assertEqual(self.app._t("konsole.start_nichts") + "\n", self.hauptprotokoll[1])

    def test_knopf_1_schreibt_nicht_ins_hauptprotokoll(self) -> None:
        self._druecken(mock.Mock(return_value=("", None, None, "dienste.suche_nichts")))
        self.assertTrue(_bis(self._laeuft_nichts))
        self.assertEqual([], self.hauptprotokoll)

    def test_meldungen_werden_im_hauptfaden_uebersetzt(self) -> None:
        eintrag = kd.dienst("klogsrv")
        zeile = ("dienste.log_sende",
                 {"name": self.app._Uebersetzbar(eintrag.name_schluessel), "datei": "k.elf"})
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache), \
                    mock.patch.object(self.app, "_current_language", sprache):
                self.assertEqual(self.app._t("dienste.log_sende",
                                             name=self.app._t(eintrag.name_schluessel),
                                             datei="k.elf"),
                                 self.app._konsole_tafel_zeile(zeile))


class GrundausstattungTests(unittest.TestCase):
    """_konsole_grundausstattung_nachstarten: nur ueber den ELF-Loader, nie Haengendes."""

    def _lauf(self, laufend=(), stumm=()):
        gui = APP.PS5ConverterGUI.__new__(APP.PS5ConverterGUI)
        gestartet: list = []
        gui._konsole_dienst_starten = lambda schluessel, ip: gestartet.append(schluessel)
        uebersicht = kd.Uebersicht("10.0.0.9", [
            kd.Stand(d, d.schluessel in laufend, d.schluessel in stumm) for d in kd.KATALOG])
        danach = _uebersicht("10.0.0.9", kd.GRUNDAUSSTATTUNG)
        with mock.patch.object(kd, "pruefen", return_value=danach):
            ergebnis = gui._konsole_grundausstattung_nachstarten("10.0.0.9", uebersicht)
        return gestartet, ergebnis, uebersicht, danach

    def test_ohne_elf_loader_wird_nichts_versucht(self) -> None:
        gestartet, ergebnis, vorher, _d = self._lauf(laufend=("pldmgr",))
        self.assertEqual([], gestartet)
        self.assertIs(vorher, ergebnis)

    def test_was_fehlt_der_reihe_nach(self) -> None:
        gestartet, ergebnis, _v, danach = self._lauf(laufend=("elfldr9021",))
        self.assertEqual(["ftpsrv", "klogsrv"], gestartet)
        self.assertIs(danach, ergebnis, "Nach dem Starten wird neu abgefragt.")

    def test_ein_haengender_dienst_wird_nicht_neu_geschickt(self) -> None:
        gestartet, _e, _v, _d = self._lauf(laufend=("elfldr9021",), stumm=("ftpsrv",))
        self.assertEqual(["klogsrv"], gestartet)

    def test_laeuft_alles_bleibt_es_still(self) -> None:
        gestartet, ergebnis, vorher, _d = self._lauf(laufend=kd.GRUNDAUSSTATTUNG)
        self.assertEqual([], gestartet)
        self.assertIs(vorher, ergebnis)


def _baum():
    return ast.parse((PROJEKT / "PS5ImageConverter_Pro_FINAL_revised.py")
                     .read_text(encoding="utf-8"))


def _methode(baum, name: str):
    """Die Methode der Programmklasse - sonst die Funktion der obersten Ebene.

    Nicht ueber ``ast.walk``: ``__init__`` gibt es im Modul mehrfach, und das
    erste gehoert nicht dem Programm.
    """
    klasse = next(k for k in baum.body
                  if isinstance(k, ast.ClassDef) and k.name == "PS5ConverterGUI")
    for knoten in klasse.body:
        if isinstance(knoten, ast.FunctionDef) and knoten.name == name:
            return knoten
    return next(k for k in baum.body if isinstance(k, ast.FunctionDef) and k.name == name)


class QuelltextTests(unittest.TestCase):
    """Was sich am laufenden Programm schlecht messen laesst."""

    def test_keine_feste_anlaufzeit_und_kurze_lesezeit(self) -> None:
        """Seit dem 26.09.2026 - und die Spielstaende starten Garlic auf demselben Weg."""
        baum = _baum()
        methode = _methode(baum, "_konsole_dienst_starten")
        text = ast.unparse(methode)
        sends = [k for k in ast.walk(methode) if isinstance(k, ast.Call)
                 and getattr(k.func, "attr", "") == "_send_payload_to_ps5"]
        self.assertNotIn("time.sleep(eintrag.anlaufzeit)", text)
        self.assertIn("warten_bis_bereit", text)
        self.assertTrue(sends)
        for aufruf in sends:
            self.assertEqual(["konsole_dienste.LESEZEIT"],
                             [ast.unparse(k.value) for k in aufruf.keywords
                              if k.arg == "lesezeit"])
        garlic = ast.unparse(_methode(baum, "_spielstaende_starten"))
        self.assertIn("self._konsole_dienst_starten('garlic'", garlic)
        self.assertNotIn("_send_payload_to_ps5", garlic,
                         "Die Spielstaende schicken selbst - an der kurzen Lesezeit vorbei.")

    def test_die_faeden_der_seite_uebersetzen_nicht(self) -> None:
        """Durchsicht H2-13 fuer alle Arbeitsgaenge der Seite.

        Uebersetzt der Faden, friert die Sprache der Messung im Text ein. Die
        Suche selbst darf fuer ihre Rueckfrage (mehrere Konsolen) uebersetzen -
        die erscheint sofort und verschwindet wieder.
        """
        baum = _baum()
        pruefen: list = []
        for name in ("_konsole_tafel_suchen", "_konsole_tafel_pruefen",
                     "_konsole_tafel_starten", "_konsole_tafel_grundausstattung"):
            pruefen.append((name, next(k for k in ast.walk(_methode(baum, name))
                                       if isinstance(k, ast.FunctionDef)
                                       and k.name == "_arbeit")))
        for name in ("_konsole_dienst_starten", "_konsole_elfldr_sicherstellen",
                     "_konsole_grundausstattung_nachstarten"):
            pruefen.append((name, _methode(baum, name)))
        for name, knoten in pruefen:
            with self.subTest(funktion=name):
                self.assertEqual([], [k.lineno for k in ast.walk(knoten)
                                      if isinstance(k, ast.Call)
                                      and getattr(k.func, "attr", "") in ("_t", "_modul_texte")])

    def test_verbunden_wird_nur_beim_echten_programmstart(self) -> None:
        """Tests, Diagnose und Kommandozeile bauen das Programm auch - ohne Netz."""
        baum = _baum()
        block = next(k for k in baum.body if isinstance(k, ast.If)
                     and "__main__" in ast.unparse(k.test))
        text = ast.unparse(block)
        aufruf = "root.after(2000, app._konsole_beim_start_verbinden)"
        self.assertIn(aufruf, text)
        self.assertLess(text.index(aufruf), text.rindex("root.mainloop()"))
        self.assertEqual(1, text.count("_konsole_beim_start_verbinden"))
        for name in ("__init__", "_finish_startup_phase", "_ansicht_beim_start_herstellen",
                     "_run_anzeige_diagnose", "_run_cli", "_ansicht_setzen"):
            funktion = _methode(baum, name)
            with self.subTest(funktion=name):
                self.assertNotIn("_konsole_beim_start_verbinden", ast.unparse(funktion))
                self.assertNotIn("_konsole_tafel_suchen", ast.unparse(funktion))


class TexteTests(unittest.TestCase):

    def test_die_texte_gibt_es_zweisprachig(self) -> None:
        for schluessel in ("dienste.status_suche", "dienste.suche_pruefe",
                           "dienste.suche_rundruf", "dienste.suche_netz",
                           "dienste.suche_nichts", "dienste.log_gefunden",
                           "dienste.log_adresse_gespeichert", "dienste.q_welche_konsole_why",
                           "dienste.konsole_eintrag",
                           "dienste.status_elfldr", "dienste.log_elfldr_laden",
                           "dienste.log_elfldr_vorhanden", "dienste.log_elfldr_hochgeladen",
                           "dienste.log_elfldr_web", "dienste.log_elfldr_ohne_pldmgr",
                           "dienste.log_elfldr_fehler", "payloadmod.elfldr_belegt",
                           "konsole.start_suche", "konsole.start_ergebnis",
                           "konsole.start_nichts", "tafel.title", "tafel.subtitle"):
            for sprache in ("de", "en"):
                with self.subTest(schluessel=schluessel, sprache=sprache):
                    self.assertTrue(STRINGS[schluessel].get(sprache))

    def test_die_seite_heisst_wie_der_knopf(self) -> None:
        """Knopf "1. Konsole & Payloads" zeigt die Seite "Konsole & Payloads"."""
        for sprache in ("de", "en"):
            with self.subTest(sprache=sprache):
                self.assertEqual(STRINGS["konsole.btn_dienste"][sprache].split(" ", 1)[1],
                                 STRINGS["tafel.title"][sprache])
                self.assertIn(STRINGS["tafel.title"][sprache],
                              STRINGS["konsole.btn_uebersicht"][sprache])

    def test_die_texte_des_fensters_sind_weg(self) -> None:
        for schluessel in ("dienste.window_title", "dienste.subtitle",
                           "dienste.check_button", "dienste.status_idle"):
            with self.subTest(schluessel=schluessel):
                self.assertNotIn(schluessel, STRINGS)

    def test_das_handbuch_beschreibt_es(self) -> None:
        handbuch = (PROJEKT / "BENUTZERHANDBUCH.html").read_text(encoding="utf-8")
        anfang = handbuch.index("<h4>Konsole &amp; Payloads (rechte Seite)</h4>")
        abschnitt = " ".join(handbuch[anfang:handbuch.index("<h4>", anfang + 4)].split())
        for stelle in ("Beim Programmstart", "sucht das Programm die PS5 selbst", "Rundruf",
                       "Ein FTP-Dienst muss", "kein eigenes Fenster",
                       "3&nbsp;Sekunden", "30&nbsp;Sekunden",
                       "<code>/data/pldmgr/payloads/elfldr</code>", "nichts hochgeladen",
                       "über die Weboberfläche des Payload-Managers", "bleibt unangetastet",
                       "Grundausstattung"):
            with self.subTest(stelle=stelle):
                self.assertIn(stelle, abschnitt)
        self.assertNotIn("Der Zustand der Konsole (rechte Seite)", handbuch)


if __name__ == "__main__":
    unittest.main()
